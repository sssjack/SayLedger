"""把已执行的账本结果转换成微信文字，不让模型重新计算金额。"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata
from decimal import Decimal

from app.config import settings
from app.finance import KINDS

CATEGORY_EMOJIS = {"餐饮": "🍜", "交通": "🚕", "购物": "🛍️", "服饰": "👕", "居住": "🏠",
                   "娱乐": "🎮", "医疗": "💊", "教育": "📚", "数码": "💻", "旅行": "🧳", "人情": "🎁"}
KIND_EMOJIS = {"income": "💰", "refund": "↩️", "transfer": "🔄", "repayment": "💳", "lend": "🤝",
               "borrow": "🏦", "collection": "💌", "loan_repayment": "💳", "deposit": "🧷"}
METRIC_LABELS = {"expense": "个人净支出", "income": "收入", "flow": "流水金额", "outstanding": "待结清"}


def _plain(value) -> str:
    return " ".join(str(value or "").split())


def _short(value, width: int = 18) -> str:
    text = _plain(value)
    size = sum(2 if unicodedata.east_asian_width(char) in "WF" else 1 for char in text)
    if size <= width:
        return text
    result, used = [], 0
    for char in text:
        used += 2 if unicodedata.east_asian_width(char) in "WF" else 1
        if used > width - 2:
            break
        result.append(char)
    return "".join(result) + "…"


def _money(value) -> str:
    return f"¥{Decimal(str(value)):,.2f}"


def _date(value) -> str:
    text = str(value or "")[:10]
    try:
        return dt.date.fromisoformat(text).strftime("%Y.%m.%d")
    except ValueError:
        return _plain(value)


def _period(period: dict) -> str:
    start, end = period.get("start"), period.get("end")
    if start and start == end:
        return _date(start)
    if start and end:
        left, right = _date(start), _date(end)
        if left[:4] == right[:4] and re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", right):
            right = right[5:]
        return left + " ～ " + right
    if start:
        return _date(start) + " 起"
    if end:
        return "截至 " + _date(end)
    return "全部时间"


def _icon(row: dict) -> str:
    if row.get("kind") in KIND_EMOJIS:
        return KIND_EMOJIS[row["kind"]]
    label = str(row.get("note") or row.get("merchant") or "")
    if row.get("category") == "餐饮" and any(word in label for word in ("饮料", "奶茶", "咖啡", "果汁")):
        return "☕" if "咖啡" in label else "🥤"
    return CATEGORY_EMOJIS.get(row.get("category"), "🧾")


def _row_lines(row: dict, *, compact: bool, shared_date: str = "", show_kind: bool = True,
               show_payment: bool = False) -> list[str]:
    label = _short(row.get("merchant") or row.get("note") or row.get("category") or "流水", 16 if compact else 24)
    name = (KINDS.get(row.get("kind"), "流水") + " · ") if compact and show_kind else ""
    first = f"{_icon(row)} {name}{label}  {_money(row['amount'])}"
    if compact:
        first += f"  #{row['id']}"
    details = []
    if not compact:
        details = [_plain(value) for value in [KINDS.get(row.get("kind"), "流水"), row.get("category"), row.get("paymentMethod")] if value]
        if row.get("date") and row["date"] != shared_date:
            details.append(_date(row["date"]))
        details.append(f"#{row['id']}")
    elif row.get("paymentMethod") and show_payment:
        details.append(_plain(row["paymentMethod"]))
    lines = [first]
    if details:
        lines.append("  " + " · ".join(dict.fromkeys(details)))
    if row.get("kind") == "expense" and row.get("personalAmount") is not None and row["personalAmount"] != row["amount"]:
        lines.append("  个人承担 " + _money(row["personalAmount"]))
    if row.get("outstandingAmount", 0) > 0:
        lines.append("  " + ("待归还 " if row.get("kind") == "borrow" else "待收回 ") + _money(row["outstandingAmount"]))
    return lines


def _headline(reply: str, payload: dict) -> str:
    """只润色已执行的结果，不让展示文案把澄清、失败或候选误写成成功。"""
    kind = payload.get("kind")
    if kind == "record":
        if reply.startswith("记好了"):
            return f"🧾 记好啦 · {len(payload.get('transactions') or [])}笔"
        return "🧾 " + reply
    if kind == "query":
        return "🔎 帮你翻到账本啦～\n" + reply
    if kind in {"update", "delete"} and payload.get("found") is False:
        return "🔎 还没找到你说的那笔呢～\n" + reply
    if kind == "update":
        return "✏️ 已修改 · 改好啦"
    if kind == "delete":
        return "🧹 " + reply
    if kind == "undo":
        return "↩️ " + reply
    if kind == "duplicate":
        return "👀 这笔看起来有点眼熟，先帮你拦一下～\n" + reply
    if kind == "preference":
        return "🪄 记住啦，以后会按你的习惯记账～"
    if kind == "export":
        return "📦 已帮你整理好账单啦～\n登录网页，从对话里的导出卡片下载CSV。"
    icon = {"error": "🌱", "clarify": "💬", "budget": "🎯", "compare": "📊"}.get(kind, "🌷")
    return icon + " " + reply


def format_reply(reply: str, payload: dict, *, transcript: str = "") -> str:
    kind, period = payload.get("kind"), payload.get("range") or {}
    stats = payload.get("stats") or {}
    if kind == "query" and "display_total" in stats:
        lines = ["📒 账单小结", "📅 " + _period(period), ""]
        if stats.get("count", 0):
            lines += [METRIC_LABELS.get(stats.get("metric"), "个人净支出"),
                      f"{_money(stats['display_total'])}  ·  共{stats['count']}笔"]
        else:
            lines.append("这个范围里还没有账单哦～")
    else:
        lines = [_headline(reply, payload)]
        if period.get("start") or period.get("end"):
            lines.append("📅 " + _period(period))
    rows = payload.get("transactions") or payload.get("candidates") or payload.get("deleted") or []
    compact = kind == "query"
    payments = {row.get("paymentMethod") for row in rows[:8]}
    dates = {row.get("date") for row in rows[:8] if row.get("date")}
    shared_date = next(iter(dates)) if len(dates) == 1 else ""
    if rows:
        if not compact and shared_date:
            lines.append("📅 " + _date(shared_date))
        lines += ["", "— 明细 —"] if compact else [""]
    previous_date = period.get("start") if period.get("start") == period.get("end") else None
    kinds = {row.get("kind") for row in rows[:8]}
    show_kind = len(kinds) != 1 or not kinds.issubset({"expense"})
    for index, row in enumerate(rows[:8]):
        if compact and row.get("date") and row["date"] != previous_date:
            if index:
                lines.append("")
            lines.append("📅 " + _date(row["date"]))
            previous_date = row["date"]
        elif not compact and index:
            lines.append("")
        lines.extend(_row_lines(row, compact=compact, shared_date=shared_date, show_kind=show_kind,
                                show_payment=len(payments) > 1))
    more = len(rows) > 8 or bool(payload.get("truncated"))
    if more:
        count = stats.get("count")
        hint = f"已展示{min(8, len(rows))}笔 / 共{count}笔" if count is not None else "这里只展示前8笔"
        lines += ["", "📚 " + hint + "，完整明细见账本"]
    if kind == "duplicate":
        lines += ["", "确实是另一笔？", "10分钟内回复「确认重复记账」"]
    for choice in (payload.get("choices") or [])[:6]:
        lines.append(f"💬 可回复：{choice['text']}")
    if payload.get("budgets"):
        lines.append("")
    for budget in (payload.get("budgets") or [])[:6]:
        lines += [f"🎯 {_plain(budget.get('label', '预算'))}",
                  f"  预算 {_money(budget['amount'])} · 剩余 {_money(budget['remaining'])}"]
    if payload.get("preference"):
        preference = payload["preference"]
        lines.append(f"💳 默认付款方式：{preference.get('payment_method') or '未设置'}")
        for name, category in list((preference.get("rules") or {}).items())[:5]:
            lines.append(f"{name} → {category}")
    if kind in {"update", "delete"} and payload.get("found") is False:
        lines += ["", "补充商户、金额或日期，就能继续找啦。"]
    if kind in {"record", "update", "delete"} and payload.get("found") is not False:
        lines += ["", "↩️ 可说「撤销上一步」"]
    if transcript:
        lines += ["", "🎙️ 听到你说：" + _short(transcript, 100)]
    # 日常短回复不重复贴长网址，仅帮助、导出和未展示完的明细提供入口。
    help_reply = kind == "chat" and "你的记账搭子" in reply
    need_link = more or kind == "export" or help_reply
    footer = f"\n\n📖 完整账本\n{settings.public_url}" if settings.public_url and need_link else ""
    # 为链接保留位置；按 UTF-8 字节截断，避免中文使消息超过通道限制。
    text = "\n".join(lines).strip()
    budget = max(1000, 3800 - len(footer.encode()))
    if len(text.encode()) > budget:
        text = text.encode()[:budget - 60].decode("utf-8", errors="ignore") + "\n更多明细请到网页查看。"
    return text + footer
