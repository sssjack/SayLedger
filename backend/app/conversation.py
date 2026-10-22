"""执行对话意图；模型只选动作，系统生成真实执行结果。"""
from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.categories import CATEGORY_NAMES
from app.db import Budget, Transaction
from app.finance import (KINDS, budget_month, budget_progress, enrich, lock_ledger, money, preference_data,
                         save_budget, set_preference, undo)
from app.query import load_transactions, serialize, summarize


def local_intent(text: str, today: dt.date) -> dict[str, Any] | None:
    compact = re.sub(r"[\s，。！？!?]", "", text)
    if compact in {"撤销", "撤销刚才操作", "撤销上一步", "撤销刚才的操作", "恢复刚删的记录", "刚才删错了恢复一下"}:
        return {"action": "undo"}
    if compact in {"预算", "查看预算", "这个月预算还剩多少", "本月预算", "预算还剩多少"}:
        return {"action": "budget_query", "budget": {}}
    match = re.fullmatch(r"(?:这个月|本月)(.*?)(?:预算|控制在)(\d+(?:\.\d{1,2})?)(?:元)?", compact)
    if match and (not match[1] or match[1] in CATEGORY_NAMES):
        return {"action": "budget_set", "budget": {"amount": match[2], "category": match[1]}}
    match = re.fullmatch(r"(?:以后)?(?:没说付款方式就)?默认(?:用)?(微信|支付宝|银行卡|信用卡|现金)(?:付|付款)?", compact)
    if match:
        return {"action": "preference_set", "preference": {"payment_method": match[1]}}
    if compact == "取消默认付款方式":
        return {"action": "preference_set", "preference": {"payment_method": ""}}
    if compact in {"谁还没还我钱", "还有谁没还我", "待收款", "还有多少钱没收回来"}:
        return {"action": "query", "query": {"pending": True, "kinds": ["expense", "lend", "deposit"], "metric": "outstanding"}}
    if compact in {"待报销", "还有多少钱没报销", "公司还有多少钱没报"}:
        return {"action": "query", "query": {"pending": True, "settlement_kind": "reimbursement", "metric": "outstanding"}}
    match = re.fullmatch(r"(退款|结清)账单#(\d+)(?:[，,]金额(\d+(?:\.\d{1,2})?)元)?", text)
    if match:
        return {"action": "refund" if match[1] == "退款" else "settle", "target_id": int(match[2]),
                **({"amount": match[3]} if match[3] else {})}
    return None


def _execute_memo(db: Session, user_id: int, data: dict[str, Any], action: str,
                  text: str, source: str, context: dict | None = None) -> tuple[str, dict[str, Any]]:
    """备忘动作：草稿齐了就建 Memo；缺时刻/事件先存草稿追问，下一句补齐。"""
    from app import memo as memo_mod
    from app.auth import now_local

    now = now_local()
    if action == "memo_cancel_pending":
        memo_mod.clear_pending(db, user_id)
        return "好嘞，那条备忘草稿已经取消啦，不会打扰你～", {"kind": "memo"}
    draft = data.get("draft") if isinstance(data.get("draft"), dict) else None
    anchor = (context or {}).get("stage_anchor")
    if action == "memo_batch" or draft is not None and isinstance(draft.get("batch"), list):
        raw = draft["batch"] if draft is not None else data.get("memos")
        if not isinstance(raw, list) or not 1 <= len(raw) <= 8 or any(not isinstance(entry, dict) for entry in raw):
            raise HTTPException(400, "每份计划支持1到8条提醒，请说明具体步骤和时间。")
        drafts = []
        for entry in raw:
            day = memo_mod.cn_int(str(entry.get("day") or ""))
            if day and anchor and day < anchor["day"]:
                continue
            item = dict(entry) if draft is not None else memo_mod.normalize_ai_memo(entry, now, anchor=anchor)
            item.setdefault("raw_input", text)
            drafts.append(item)
        if not drafts:
            return "这份计划的步骤都在当前阶段之前，还没有创建提醒。请说明接下来要提醒的步骤。", {"kind": "clarify"}
        rows = memo_mod.create_memos(db, user_id, drafts, source=source, now=now)
        if not rows:
            pending = {"batch": drafts}
            memo_mod.save_pending(db, user_id, pending)
            return memo_mod.pending_reply(pending), {"kind": "memo", "missing": ["batch"]}
        memo_mod.clear_pending(db, user_id)
        lines = [f"📌 已安排{len(rows)}条提醒"]
        lines.extend(f"{row.next_trigger_at:%m月%d日 %H:%M} · {row.content[:40]}" for row in rows)
        return "\n".join(lines), {"kind": "memo", "memos": [memo_mod.serialize_memo(row) for row in rows]}
    if draft is None and isinstance(data.get("memo"), dict):
        draft = memo_mod.normalize_ai_memo(data["memo"], now, anchor=anchor)
    if draft is None:
        return "这条备忘我没看明白，可以换个说法再告诉我吗？比如“明天下午3点提醒我开会”。", {"kind": "clarify", "missing": ["memo"]}
    draft = dict(draft)
    draft.setdefault("raw_input", text)
    if source in ("image", "wechat-image"):
        draft.setdefault("source_kind", "image")
    missing = draft.get("missing") or memo_mod._draft_missing(draft)
    draft["missing"] = missing
    if action == "memo_create" or not missing:
        row = memo_mod.create_memo(db, user_id, draft, source="image" if draft.get("source_kind") == "image" else source, now=now)
        if row is None:
            memo_mod.save_pending(db, user_id, draft)
            return memo_mod.pending_reply(draft), {"kind": "memo", "missing": draft.get("missing") or missing}
        memo_mod.clear_pending(db, user_id)
        return memo_mod.created_reply(row), {"kind": "memo", "memo": memo_mod.serialize_memo(row),
                                             "memos": [memo_mod.serialize_memo(row)]}
    memo_mod.save_pending(db, user_id, draft)
    return memo_mod.pending_reply(draft), {"kind": "memo", "missing": missing}


def resolve_related(db: Session, user_id: int, data: dict[str, Any], action: str) -> tuple[Transaction | None, list[Transaction]]:
    allowed = ["expense"] if action == "refund" else ["expense", "lend", "deposit", "borrow"]
    query = dict(data.get("target_query") or {})
    query["kinds"] = allowed
    if action == "settle":
        query["pending"] = True
    candidates = load_transactions(db, user_id, query)
    target_id = data.get("target_id")
    if target_id is not None:
        candidates = [row for row in candidates if str(row.id) == str(target_id)]
    if action == "refund":
        candidates = [row for row in candidates if row.amount > row._refunded]
    return (candidates[0] if len(candidates) == 1 else None), candidates


def query_conditions(data: dict[str, Any], text: str, today: dt.date) -> dict[str, Any]:
    from app.dateparse import resolve_range
    query = dict(data.get("query") or {})
    start, end = resolve_range(text, today)
    if start and end:
        query.update(start=start.isoformat(), end=end.isoformat())
    kinds = query.get("kinds") or []
    if query.get("pending"):
        query["metric"] = "outstanding"
    elif kinds == ["income"]:
        query["metric"] = "income"
    elif kinds and not set(kinds).intersection({"expense", "refund"}) and not query.get("metric"):
        query["metric"] = "flow"
    return query


def execute(db: Session, user_id: int, data: dict[str, Any], text: str, today: dt.date,
            image_path: str, source: str, confirm_duplicate: bool, *, context: dict | None = None) -> tuple[str, dict[str, Any]]:
    from app.main import apply_ai_change, create_transactions
    action = str(data.get("action") or "chat")
    if action in {"record", "update", "delete", "undo", "refund", "settle", "budget_set", "budget_delete", "preference_set",
                  "memo", "memo_create", "memo_pending", "memo_cancel_pending", "memo_batch"}:
        lock_ledger(db)
    if action in {"memo", "memo_create", "memo_pending", "memo_cancel_pending", "memo_batch"}:
        return _execute_memo(db, user_id, data, action, text, source, context)
    payload: dict[str, Any] = {"kind": action}
    if action == "record":
        items = data.get("transactions") or []
        if not isinstance(items, list) or any(not isinstance(i, dict) for i in items):
            raise HTTPException(400, "没有识别到有效的记账信息")
        rows = create_transactions(db, user_id, items, source=source, raw_input=text, image_path=image_path,
                                   fallback_date=today, confirm_duplicate=confirm_duplicate)
        payload["transactions"] = [serialize(row) for row in rows]
        return f"记好了，{len(rows)}笔流水。", payload
    if action in {"update", "delete"}:
        result = apply_ai_change(db, user_id, data, action, text)
        payload.update(result)
        if not result.get("found"):
            return "没有唯一定位到那笔账，请选择账单直接编辑，或补充商户、金额和日期。", payload
        return ("已修改。" if action == "update" else "已删除，可以撤销上一步。"), payload
    if action == "undo":
        rows = undo(db, user_id)
        payload.update(transactions=[serialize(row) for row in rows if row.deleted_at is None],
                       deleted=[serialize(row) for row in rows if row.deleted_at is not None])
        return "已撤销上一次记账操作。", payload
    if action in {"refund", "settle"}:
        target, candidates = resolve_related(db, user_id, data, action)
        if target is None:
            return "请说明是哪一笔的退款或回款，可以补充日期、商户或对方姓名。", {
                "kind": "clarify", "missing": ["target"], "candidates": [serialize(row) for row in candidates[:6]],
                "choices": [{"label": f"#{row.id} {row.note or row.merchant or row.counterparty} ¥{row.amount}",
                             "text": f"{('退款' if action == 'refund' else '结清')}账单#{row.id}" + (f"，金额{data['amount']}元" if data.get("amount") is not None else "")}
                            for row in candidates[:6]],
            }
        amount = data.get("amount")
        if amount is None:
            amount = target.amount - target._refunded if action == "refund" else target._pending
        kind = "refund" if action == "refund" else "loan_repayment" if target.kind == "borrow" else "collection"
        rows = create_transactions(db, user_id, [{"amount": amount, "kind": kind, "related_id": target.id,
            "occurred_at": data.get("occurred_at") or today.isoformat(), "payment_method": data.get("payment_method"),
            "note": f"{KINDS[kind]} · {target.note or target.merchant or target.counterparty}",
        }], source=source, raw_input=text, image_path=image_path, fallback_date=today, confirm_duplicate=confirm_duplicate)
        db.flush()
        enrich(db, [target])
        payload.update(kind="record", transactions=[serialize(row) for row in rows], related=[serialize(target)])
        return (f"已记录退款{money(amount)}元。" if action == "refund" else f"已记录{KINDS[kind]}{money(amount)}元，剩余待结清{target._pending}元。"), payload
    if action in {"query", "compare", "export"}:
        query = query_conditions(data, text, today)
        rows = load_transactions(db, user_id, query)
        stats = summarize(rows, query)
        payload.update(query=query, stats=stats, transactions=[serialize(row) for row in rows[:40]],
                       truncated=max(0, len(rows)-40), range={"start": query.get("start"), "end": query.get("end")})
        label = {"expense": "个人净支出", "income": "收入", "flow": "流水金额", "outstanding": "待结清"}.get(stats["metric"], "个人净支出")
        reply = f"共{stats['count']}笔，{label}{stats['display_total']:.2f}元。" if rows else "这个范围内没有符合条件的记录。"
        if action == "export":
            allowed = {"start", "end", "event", "merchant", "keyword", "payment_method", "counterparty", "settlement_kind", "pending", "min_amount", "max_amount"}
            params = {k: v for k, v in query.items() if k in allowed and v is not None}
            for key in ("categories", "kinds"):
                if query.get(key):
                    params[key] = ",".join(query[key]) if isinstance(query[key], list) else query[key]
            payload["download"] = "/api/export?" + urlencode(params)
            return f"已整理{len(rows)}笔账单，可下载CSV。", payload
        if action == "compare":
            try:
                start = dt.date.fromisoformat(query.get("start", ""))
                end = dt.date.fromisoformat(query.get("end", ""))
            except ValueError:
                raise HTTPException(400, "请指定要比较的时间范围，例如这个月比上个等长周期") from None
            span = (end-start).days+1
            if span < 1:
                raise HTTPException(400, "起止日期有误")
            previous_end = start-dt.timedelta(days=1)
            previous_start = previous_end-dt.timedelta(days=span-1)
            previous = summarize(load_transactions(db, user_id, {**query, "start": str(previous_start), "end": str(previous_end)}), query)
            old = {g["label"]: Decimal(str(g["value"])) for g in previous["by_category"]}
            new = {g["label"]: Decimal(str(g["value"])) for g in stats["by_category"]}
            changes = [{"label": k, "value": float(new.get(k, Decimal(0))-old.get(k, Decimal(0)))} for k in new.keys() | old.keys()]
            delta = Decimal(str(stats["display_total"]))-Decimal(str(previous["display_total"]))
            payload["comparison"] = {"start": str(previous_start), "end": str(previous_end), "total": previous["display_total"],
                "delta": float(delta), "categories": sorted(changes, key=lambda i: abs(i["value"]), reverse=True)}
            reply = f"{label}{stats['display_total']:.2f}元，比前一个等长周期{'增加' if delta >= 0 else '减少'}{abs(delta):.2f}元。"
        return reply, payload
    if action.startswith("budget_"):
        budget = dict(data.get("budget") or {})
        month = budget_month(budget.get("month"), today)
        if action == "budget_set":
            save_budget(db, user_id, budget, today)
        elif action == "budget_delete":
            row = db.scalar(select(Budget).where(Budget.user_id == user_id, Budget.month == month,
                Budget.category == str(budget.get("category") or ""), Budget.event == str(budget.get("event") or "")))
            if not row:
                raise HTTPException(400, "没有找到这项预算")
            db.delete(row)
            db.flush()
        elif action != "budget_query":
            raise HTTPException(400, "无法识别预算操作")
        payload.update(kind="budget", budgets=budget_progress(db, user_id, month), month=month)
        return {"budget_set": "预算已保存。", "budget_delete": "预算已取消。", "budget_query": f"这是{month}的预算进度。"}[action], payload
    if action == "preference_set":
        preference = dict(data.get("preference") or {})
        if preference.get("merchant"):
            rules = preference_data(db, user_id)["rules"]
            merchant = str(preference["merchant"]).strip()
            if preference.get("remove"):
                rules.pop(merchant, None)
            else:
                rules[merchant] = preference.get("category")
            preference["rules"] = rules
        value = set_preference(db, user_id, preference)
        payload.update(kind="preference", preference=value)
        return "记住了，以后的新账单会按这项规则处理。", payload
    if action == "clarify":
        return str(data.get("reply") or "请补充金额或说明这笔钱的性质。"), {"kind": "clarify", "missing": data.get("missing") or []}
    return str(data.get("reply") or "可以记录收支、处理退款和回款，也可以查账、设置月预算。"), {"kind": "chat"}
