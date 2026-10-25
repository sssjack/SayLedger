"""周报：按需查询与每周自动推送共用同一份计算。

周口径：周一到周日。按需查“本周”时区间只到今天（不把未来几天算进去）；
查“上周”时是完整的上一个周一到周日。自动推送固定在周日 20:00，由
MemoManager 每 30 秒扫描触发一次，WeeklyReport 表按（用户，周一）去重，
避免一小时内多次扫描重复发送。
"""
from __future__ import annotations

import datetime as dt
import json
import re
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Message, User, WechatBinding, WechatDelivery, WeeklyReport, utcnow
from app.finance import budget_progress, lock_ledger
from app.query import load_transactions, summarize

CN_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
             "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

# 翻页口令（去掉空白和标点后全量匹配，避免“继续记账”这类带后缀的句子被误判）。
_NEXT_WORDS = {"继续", "继续看", "继续展示", "下一页", "下页", "下一批", "再看",
               "更多", "还有", "还有呢", "剩下的", "继续看下一页", "看下一页", "下一页吧"}
_PREV_WORDS = {"上一页", "上页", "返回上一页", "上一批"}
_FIRST_WORDS = {"第一页"}


def parse_pagination(text: str, last_page: int) -> int | None:
    """返回要跳到的页码；不是翻页口令返回 None。last_page 是上一条查询的页码。"""
    compact = re.sub(r"[\s，。！？!?、]", "", text or "")
    if compact in _NEXT_WORDS:
        return last_page + 1
    if compact in _PREV_WORDS:
        return max(1, last_page - 1)
    if compact in _FIRST_WORDS:
        return 1
    match = re.fullmatch(r"第([0-9一二三四五六七八九十]+)页", compact)
    if match:
        raw = match[1]
        if raw.isdigit():
            return max(1, int(raw))
        if len(raw) == 1 and raw in CN_DIGITS:
            return CN_DIGITS[raw]
        if raw == "十一":
            return 11
    return None


def week_range(today: dt.date, offset: int) -> tuple[dt.date, dt.date]:
    """offset=0 是本周（周一到今天），offset=-1 是上周（完整周一到周日）。"""
    monday = today - dt.timedelta(days=today.weekday())
    start = monday + dt.timedelta(days=offset * 7)
    end = today if offset == 0 else start + dt.timedelta(days=6)
    return start, end


def parse_weekly(text: str, today: dt.date) -> int | None:
    """返回周报的 offset；不是周报请求返回 None。"""
    if not re.search(r"周报|周总结", text or ""):
        return None
    if "上上周" in text:
        return -2
    if "上周" in text or "上一周" in text:
        return -1
    return 0


def _money(value) -> str:
    return f"¥{Decimal(str(value)):,.2f}"


def _period_label(start: dt.date, end: dt.date) -> str:
    left, right = start.strftime("%m.%d"), end.strftime("%m.%d")
    return f"{start.year}.{left}～{right}" if start.year != end.year else f"{left}～{right}"


def _expense_value(row) -> Decimal:
    """个人净支出口径：个人承担金额（无个人承担时用原金额）。"""
    if getattr(row, "_value", None) is not None:
        return Decimal(str(row._value))
    return Decimal(str(getattr(row, "personal_amount", None) or row.amount))


def build_weekly_report(db: Session, user_id: int, start: dt.date, end: dt.date) -> dict[str, Any]:
    """全部数字由后端算：本期支出、收入、分类、付款方式、最大几笔、上期对比、待结清。"""
    # 个人净支出口径：消费的个人承担 − 当期退款的个人部分，与账本口径一致。
    query = {"start": start.isoformat(), "end": end.isoformat(), "metric": "expense",
             "kinds": ["expense", "refund"]}
    rows = load_transactions(db, user_id, query)
    stats = summarize(rows, query)
    income_query = {**query, "kinds": ["income"], "metric": "income"}
    income_stats = summarize(load_transactions(db, user_id, income_query), income_query)
    prev_start, prev_end = start - dt.timedelta(days=7), end - dt.timedelta(days=7)
    prev = summarize(load_transactions(db, user_id, {**query, "start": prev_start.isoformat(), "end": prev_end.isoformat()}), query)
    pending = summarize(load_transactions(db, user_id, {"pending": True}), {"metric": "outstanding"})
    top = sorted((row for row in rows if _expense_value(row) > 0),
                 key=_expense_value, reverse=True)[:3]
    days = max(1, (end - start).days + 1)
    over_budgets = [b for b in budget_progress(db, user_id, end.strftime("%Y-%m"))
                    if b.get("remaining") is not None and Decimal(str(b["remaining"])) < 0]
    return {
        "period_start": start.isoformat(), "period_end": end.isoformat(),
        "total": float(stats["display_total"]), "count": stats["count"],
        "average_per_day": float(Decimal(str(stats["display_total"])) / days),
        "income": float(income_stats["display_total"]), "income_count": income_stats["count"],
        "previous_total": float(prev["display_total"]), "previous_count": prev["count"],
        "pending": float(pending["display_total"]),
        "categories": [{"label": g["label"], "value": float(g["value"])} for g in stats["by_category"][:5]],
        "payments": [{"label": g["label"], "value": float(g["value"])} for g in stats["by_payment"][:5]],
        "top": [{"merchant": row.merchant, "note": row.note, "category": row.category,
                 "amount": float(_expense_value(row)), "date": row.occurred_at.date().isoformat()}
                for row in top],
        "over_budgets": [{"label": b["label"], "remaining": float(b["remaining"])} for b in over_budgets],
    }


def format_weekly_report(report: dict[str, Any]) -> str:
    """周报文案：控制在 1000 字以内（apply_chat 会截断回复），不写模型现编的数字。"""
    start = dt.date.fromisoformat(report["period_start"])
    end = dt.date.fromisoformat(report["period_end"])
    lines = [f"📊 周报 {_period_label(start, end)}"]
    count = report["count"]
    if not count and not report["income"]:
        lines.append("这周还没有账单哦～")
        return "\n".join(lines)
    total = Decimal(str(report["total"]))
    lines.append(f"个人净支出 {_money(total)} · 共 {count} 笔 · 日均 {_money(report['average_per_day'])}")
    if report["previous_count"]:
        delta = total - Decimal(str(report["previous_total"]))
        sign = "+" if delta >= 0 else "-"
        lines.append(f"比上周 {sign}{_money(abs(delta))}（上周 {_money(report['previous_total'])}）")
    else:
        lines.append("上周暂无记录")
    if report["income"]:
        lines.append(f"收入 {_money(report['income'])} · {report['income_count']} 笔")
    if report["categories"]:
        lines.append("分类：")
        for item in report["categories"]:
            share = (Decimal(str(item["value"])) / total * 100) if total else Decimal(0)
            lines.append(f"  {item['label']} {_money(item['value'])}（{share:.0f}%）")
    if report["top"]:
        lines.append("最大几笔：")
        for item in report["top"]:
            label = item["merchant"] or item["note"] or item["category"] or "流水"
            lines.append(f"  {label} {_money(item['amount'])}")
    if report["payments"]:
        lines.append("付款：" + " · ".join(f"{item['label']} {_money(item['value'])}" for item in report["payments"]))
    if report["pending"]:
        lines.append(f"待结清（全部） {_money(report['pending'])}")
    for budget in report["over_budgets"]:
        lines.append(f"⚠️ {budget['label']}预算已超支 {_money(abs(Decimal(str(budget['remaining']))))}")
    text = "\n".join(lines)
    return text[:950]


def fire_weekly_reports(now: dt.datetime | None = None) -> int:
    """周日 20:00 触发一次当周周报；返回本次发送的用户数。"""
    from app.auth import now_local
    from app.db import SessionLocal
    from app.wechat_api import digest, seal

    now = now or now_local()
    if now.weekday() != 6 or now.hour != 20:
        return 0
    today = now.date()
    start, _end = week_range(today, 0)
    period_start = start.isoformat()
    sent = 0
    with SessionLocal.begin() as db:
        lock_ledger(db)
        existing = set(db.scalars(
            select(WeeklyReport.user_id).where(WeeklyReport.period_start == period_start)).all())
        bindings = {row.user_id: row for row in db.scalars(select(WechatBinding)).all()}
        for user in list(db.scalars(select(User)).all()):
            if user.id in existing:
                continue
            try:
                report = build_weekly_report(db, user.id, start, today)
                if not report["count"] and not report["income"]:
                    continue
                text = format_weekly_report(report)
                db.add(Message(user_id=user.id, role="assistant", content=text,
                               payload_json=json.dumps(
                                   {"kind": "weekly", "weekly": report,
                                    "range": {"start": report["period_start"], "end": report["period_end"]}},
                                   ensure_ascii=False)))
                push_status = "web_only_no_binding"
                binding = bindings.get(user.id)
                if binding is not None and binding.state == "connected":
                    context = ""
                    if binding.last_context_cipher:
                        from app.wechat_api import unseal

                        try:
                            context = unseal(binding.last_context_cipher)
                        except Exception:
                            context = ""
                    if context:
                        key = digest(f"weekly:{user.id}:{period_start}")
                        envelope = json.dumps(
                            {"context": context, "proactive": True, "weekly_period": period_start},
                            ensure_ascii=False)
                        db.add(WechatDelivery(
                            user_id=user.id, revision=binding.revision,
                            peer_hash=digest(binding.peer_id), message_key=key,
                            envelope_cipher=seal(envelope), state="reply_pending", reply=text,
                            payload_json=json.dumps(
                                {"kind": "weekly", "weekly": report}, ensure_ascii=False),
                            client_id="sayledger-" + uuid.uuid4().hex))
                        push_status = "wechat_queued"
                    else:
                        push_status = "web_only_no_context"
                db.add(WeeklyReport(user_id=user.id, period_start=period_start,
                                    period_end=today.isoformat(), push_status=push_status,
                                    total=Decimal(str(report["total"])), count=report["count"],
                                    sent_at=now, created_at=utcnow()))
                sent += 1
            except Exception:
                import logging

                logging.getLogger(__name__).warning("周报推送失败 user_id=%s", user.id, exc_info=True)
    return sent
