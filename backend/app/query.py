"""查询引擎：把 AI 输出的查询条件翻译成 SQL，并算出聚合结果。

AI 只负责把自然语言变成结构化条件，真正的数字一律由这里算，避免模型算错账。
"""

from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import to_decimal
from app.db import Transaction
from app.finance import cash_value, enrich, expense_value
from app.categories import CATEGORY_BY_NAME, normalize_category
from app.payments import normalize_payment, payment_color


def _parse_date(value: Any) -> dt.date | None:
    if not value:
        return None
    text = str(value).strip()[:10]
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def load_transactions(db: Session, user_id: int, query: dict[str, Any] | None) -> list[Transaction]:
    query = query or {}
    stmt = select(Transaction).where(
        Transaction.user_id == user_id,
        Transaction.deleted_at.is_(None),
    )

    start = _parse_date(query.get("start"))
    end = _parse_date(query.get("end"))
    if start:
        stmt = stmt.where(Transaction.occurred_at >= dt.datetime.combine(start, dt.time.min))
    if end:
        stmt = stmt.where(Transaction.occurred_at < dt.datetime.combine(end + dt.timedelta(days=1), dt.time.min))

    categories = query.get("categories") or []
    if isinstance(categories, str):
        categories = [categories]
    names = [normalize_category(c) for c in categories if c]
    if names:
        stmt = stmt.where(Transaction.category.in_(names))

    min_amount = to_decimal(query.get("min_amount"))
    max_amount = to_decimal(query.get("max_amount"))
    if min_amount is not None:
        stmt = stmt.where(Transaction.amount >= min_amount)
    if max_amount is not None:
        stmt = stmt.where(Transaction.amount <= max_amount)

    event = str(query.get("event") or "").strip()
    if event:
        stmt = stmt.where(Transaction.event.ilike(f"%{event}%"))

    merchant = str(query.get("merchant") or "").strip()
    if merchant:
        stmt = stmt.where(Transaction.merchant.ilike(f"%{merchant}%"))

    payment = normalize_payment(str(query.get("payment_method") or ""))
    if payment:
        stmt = stmt.where(Transaction.payment_method == payment)

    kinds = query.get("kinds") or ([query["kind"]] if query.get("kind") else [])
    if isinstance(kinds, str):
        kinds = [kinds]
    if kinds:
        stmt = stmt.where(Transaction.kind.in_(kinds))
    if query.get("counterparty"):
        stmt = stmt.where(Transaction.counterparty.contains(str(query["counterparty"])))
    if query.get("settlement_kind"):
        stmt = stmt.where(Transaction.settlement_kind == str(query["settlement_kind"]))
    rows = enrich(db, list(db.scalars(stmt.order_by(Transaction.occurred_at.desc(), Transaction.id.desc()).execution_options(populate_existing=True)).all()))
    if query.get("pending"):
        rows = [row for row in rows if row._pending > 0]

    keyword = str(query.get("keyword") or "").strip()
    if keyword:
        # 关键词在 SQL 里跨 JSON 字段匹配不干净，取回后过滤更准确；账本规模下完全够用。
        needle = keyword.lower()
        rows = [
            row
            for row in rows
            if needle in (row.merchant or "").lower()
            or needle in (row.note or "").lower()
            or needle in (row.event or "").lower()
            or needle in (row.category or "").lower()
            or needle in (row.remark or "").lower()
            or needle in (row.counterparty or "").lower()
            or needle in (row.payment_method or "").lower()
            or needle in (row.items_json or "").lower()
        ]
    return rows


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01")))


def summarize(rows: list[Transaction], query: dict[str, Any] | None = None) -> dict[str, Any]:
    query = query or {}
    total = sum((expense_value(row) for row in rows), Decimal("0"))
    income = sum((row.amount for row in rows if row.kind == "income"), Decimal("0"))
    metric = query.get("metric", "expense")
    def value(row: Transaction) -> Decimal:
        if metric == "income":
            return row.amount if row.kind == "income" else Decimal("0")
        if metric == "outstanding":
            return getattr(row, "_pending", Decimal("0"))
        return row.amount if metric == "flow" else expense_value(row)
    buckets: dict[str, dict[str, Decimal]] = {key: defaultdict(Decimal) for key in ("category", "month", "day", "event", "merchant", "payment")}
    for row in rows:
        amount = value(row)
        if not amount:
            continue
        labels = {"category": row.category, "month": row.occurred_at.strftime("%Y-%m"),
                  "day": row.occurred_at.strftime("%Y-%m-%d"), "event": row.event,
                  "merchant": row.merchant, "payment": row.payment_method or "未记录"}
        for key, label in labels.items():
            if label:
                buckets[key][label] += amount
    def groups(key: str) -> list[dict[str, Any]]:
        return sorted([{"label": k, "value": _money(v)} for k, v in buckets[key].items()], key=lambda i: i["value"], reverse=True)
    ordered = sorted(rows, key=lambda r: r.occurred_at)
    values = [value(row) for row in rows if value(row) > 0]
    display_total = sum((value(r) for r in rows), Decimal("0"))
    return {
        "count": len(rows), "total": _money(total), "income": _money(income),
        "balance": _money(income - total), "cash_flow": _money(sum((cash_value(r) for r in rows), Decimal("0"))),
        "outstanding": _money(sum((getattr(r, "_pending", Decimal("0")) for r in rows if r.kind != "borrow"), Decimal("0"))),
        "payable": _money(sum((getattr(r, "_pending", Decimal("0")) for r in rows if r.kind == "borrow"), Decimal("0"))),
        "display_total": _money(display_total), "metric": metric,
        "average": _money(display_total / len(values)) if values else 0.0,
        "max": _money(max(values, default=Decimal("0"))),
        "first_date": ordered[0].occurred_at.strftime("%Y-%m-%d") if ordered else None,
        "last_date": ordered[-1].occurred_at.strftime("%Y-%m-%d") if ordered else None,
        "by_category": groups("category"), "by_event": groups("event"), "by_payment": groups("payment"),
        "groups": groups(str(query.get("group_by"))) if query.get("group_by") in buckets else [],
        "group_by": query.get("group_by", "none"),
    }


def serialize(row: Transaction) -> dict[str, Any]:
    meta = CATEGORY_BY_NAME.get(row.category, {})
    try:
        items = json.loads(row.items_json or "[]")
    except Exception:
        items = []
    return {
        "id": row.id,
        "amount": float(row.amount),
        "kind": row.kind,
        "personalAmount": float(row.personal_amount if row.personal_amount is not None else row.amount),
        "recoverableAmount": float(row.recoverable_amount),
        "settledAmount": float(getattr(row, "_settled", 0)),
        "outstandingAmount": float(getattr(row, "_pending", row.recoverable_amount)),
        "refundedAmount": float(getattr(row, "_refunded", 0)),
        "settlementKind": row.settlement_kind,
        "counterparty": row.counterparty,
        "relatedId": row.related_id,
        "transferTo": row.transfer_to,
        "expenseAmount": float(expense_value(row)),
        "cashFlow": float(cash_value(row)),
        "currency": row.currency,
        "category": row.category,
        "categoryColor": meta.get("color", "#8C8C8C"),
        "merchant": row.merchant,
        "note": row.note,
        "paymentMethod": row.payment_method or "",
        "paymentColor": payment_color(row.payment_method or ""),
        "remark": row.remark or "",
        "items": items if isinstance(items, list) else [],
        "occurredAt": row.occurred_at.strftime("%Y-%m-%d %H:%M"),
        "date": row.occurred_at.strftime("%Y-%m-%d"),
        "source": row.source,
        "event": row.event,
        "hasImage": bool(row.image_path),
    }


def month_range(day: dt.date) -> tuple[dt.date, dt.date]:
    start = day.replace(day=1)
    if start.month == 12:
        next_month = start.replace(year=start.year + 1, month=1)
    else:
        next_month = start.replace(month=start.month + 1)
    return start, next_month - dt.timedelta(days=1)


def year_range(day: dt.date) -> tuple[dt.date, dt.date]:
    return dt.date(day.year, 1, 1), dt.date(day.year, 12, 31)
