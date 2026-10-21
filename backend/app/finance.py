"""账务口径、关联回款、操作撤销和预算。所有金额使用 Decimal。"""
from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.categories import CATEGORY_NAMES
from app.db import Budget, LedgerOperation, Preference, Transaction, utcnow
from app.payments import PAYMENT_NAMES, normalize_payment

ZERO = Decimal("0.00")
KINDS = {
    "expense": "支出", "income": "收入", "refund": "退款", "transfer": "转账",
    "repayment": "信用还款", "lend": "借出", "borrow": "借入", "collection": "收回垫款",
    "loan_repayment": "归还借款", "deposit": "押金",
}
INCOMING = {"income", "refund", "borrow", "collection"}
OUTGOING = {"expense", "repayment", "lend", "loan_repayment", "deposit"}
RELATED = {"refund", "collection", "loan_repayment"}


def lock_ledger(db: Session) -> None:
    """先取写锁再校验可退款/待结清额，防止并发回款超额。"""
    connection = db.connection()
    if connection.dialect.name == "sqlite" and not connection.connection.driver_connection.in_transaction:
        connection.exec_driver_sql("BEGIN IMMEDIATE")


def money(value: Any, *, allow_zero: bool = False) -> Decimal:
    try:
        number = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        raise HTTPException(400, "请输入有效金额") from None
    if not number.is_finite() or number < 0 or (not allow_zero and number == 0) or number > Decimal("9999999999.99"):
        raise HTTPException(400, "金额需大于0且不超过99亿元")
    return number


def personal(row: Transaction) -> Decimal:
    return row.personal_amount if row.personal_amount is not None else row.amount


def expense_value(row: Transaction) -> Decimal:
    if row.kind == "expense":
        return personal(row)
    if row.kind == "refund":
        return -personal(row)
    return ZERO


def cash_value(row: Transaction) -> Decimal:
    if row.kind in INCOMING:
        return row.amount
    if row.kind in OUTGOING:
        return -row.amount
    return ZERO


def enrich(db: Session, rows: list[Transaction]) -> list[Transaction]:
    ids = [r.id for r in rows]
    children = list(db.scalars(select(Transaction).where(
        Transaction.related_id.in_(ids), Transaction.deleted_at.is_(None),
    )).all()) if ids else []
    for row in rows:
        linked = [child for child in children if child.related_id == row.id]
        row._settled = sum((c.amount for c in linked if c.kind in {"collection", "loan_repayment"}), ZERO)
        row._refunded = sum((c.amount for c in linked if c.kind == "refund"), ZERO)
        row._returned_claim = sum((c.recoverable_amount for c in linked if c.kind == "refund"), ZERO)
        row._pending = max(ZERO, row.recoverable_amount - row._settled - row._returned_claim) if row.kind in {"expense", "lend", "deposit", "borrow"} else ZERO
    return rows


def preference_data(db: Session, user_id: int) -> dict[str, Any]:
    pref = db.get(Preference, user_id)
    return {"payment_method": pref.payment_method if pref else "", "rules": json.loads(pref.rules_json) if pref else {}}


def set_preference(db: Session, user_id: int, data: dict[str, Any]) -> dict[str, Any]:
    lock_ledger(db)
    pref = db.get(Preference, user_id)
    if pref is None:
        pref = Preference(user_id=user_id, payment_method="", rules_json="{}")
        db.add(pref)
    if "payment_method" in data:
        value = str(data["payment_method"] or "")
        if value and value not in PAYMENT_NAMES:
            raise HTTPException(400, "请选择有效的默认付款方式")
        pref.payment_method = value
    if "rules" in data:
        rules = data["rules"]
        if not isinstance(rules, dict) or len(rules) > 100 or any(
            not isinstance(k, str) or not k.strip() or len(k) > 128 or v not in CATEGORY_NAMES
            for k, v in rules.items()
        ):
            raise HTTPException(400, "分类规则需要使用已有分类，最多100条")
        pref.rules_json = json.dumps(rules, ensure_ascii=False)
    db.flush()
    return preference_data(db, user_id)


def prepare_fields(db: Session, user_id: int, item: dict[str, Any]) -> dict[str, Any]:
    lock_ledger(db)
    if item.get("currency") not in (None, "", "CNY", "人民币"):
        raise HTTPException(400, "请提供人民币实付金额，外币原额可保留在备注中")
    amount = money(item.get("amount"))
    kind = str(item.get("kind") or "expense")
    if kind not in KINDS:
        raise HTTPException(400, "无法识别账务类型，请明确是支出、收入还是资金往来")
    own = money(item.get("personal_amount", amount), allow_zero=True)
    claim = money(item.get("recoverable_amount", 0), allow_zero=True)
    if kind == "expense":
        if "personal_amount" not in item:
            own = amount - claim
        elif "recoverable_amount" not in item:
            claim = amount - own
        if own < 0 or claim < 0 or own + claim != amount:
            raise HTTPException(400, "个人承担与待收回款之和必须等于实际付款")
    elif kind in {"lend", "deposit", "borrow"}:
        own, claim = ZERO, amount
    else:
        own, claim = ZERO, ZERO
    related_id = item.get("related_id")
    if kind in RELATED:
        if not isinstance(related_id, int) or isinstance(related_id, bool):
            raise HTTPException(400, "请先选择关联的原账单")
        target = db.get(Transaction, related_id)
        allowed = {"expense"} if kind == "refund" else {"borrow"} if kind == "loan_repayment" else {"expense", "lend", "deposit"}
        if not target or target.user_id != user_id or target.deleted_at is not None or target.kind not in allowed:
            raise HTTPException(400, "关联账单不存在或不适用于这次操作")
        db.refresh(target)
        if target.deleted_at is not None or target.kind not in allowed:
            raise HTTPException(400, "关联账单状态已变化，请重新选择")
        enrich(db, [target])
        if kind == "refund":
            if amount > target.amount - target._refunded:
                raise HTTPException(400, "退款金额不能超过原账单尚未退款的金额")
            claim = ((amount + target._refunded) * target.recoverable_amount / target.amount).quantize(Decimal("0.01")) - target._returned_claim
            own = amount - claim
            if claim > target._pending:
                raise HTTPException(400, "该账单已有回款，请先核对回款和退款的归属")
        elif amount > target._pending:
            raise HTTPException(400, "回款或还款金额不能超过尚未结清金额")
        item["category"] = target.category
        item["event"] = target.event
        item["counterparty"] = item.get("counterparty") or target.counterparty
    elif related_id is not None:
        raise HTTPException(400, "该类型不能关联原账单")
    return {
        "amount": amount, "kind": kind, "personal_amount": own, "recoverable_amount": claim,
        "settlement_kind": str(item.get("settlement_kind") or ("loan" if kind in {"lend", "borrow"} else "deposit" if kind == "deposit" else ""))[:24],
        "counterparty": str(item.get("counterparty") or "")[:128], "related_id": related_id,
        "transfer_to": str(item.get("transfer_to") or "")[:128],
    }


SNAPSHOT_FIELDS = (
    "amount", "kind", "personal_amount", "recoverable_amount", "settlement_kind", "counterparty",
    "related_id", "transfer_to", "category", "merchant", "note", "payment_method", "remark",
    "event", "occurred_at", "deleted_at",
)


def snapshot(row: Transaction) -> dict[str, Any]:
    result: dict[str, Any] = {"id": row.id}
    for field in SNAPSHOT_FIELDS:
        value = getattr(row, field)
        result[field] = str(value) if isinstance(value, Decimal) else value.isoformat() if isinstance(value, dt.datetime) else value
    return result


def log_operation(db: Session, user_id: int, before: list[dict], rows: list[Transaction]) -> None:
    db.flush()
    after = [snapshot(r) for r in rows]
    if before == after:
        return
    db.add(LedgerOperation(user_id=user_id, before_json=json.dumps(before, ensure_ascii=False),
                           after_json=json.dumps(after, ensure_ascii=False)))


def ensure_unlinked(db: Session, user_id: int, ids: list[int]) -> None:
    linked = db.scalar(select(Transaction.id).where(
        Transaction.user_id == user_id, Transaction.related_id.in_(ids), Transaction.deleted_at.is_(None),
        Transaction.id.not_in(ids),
    ).limit(1))
    if linked:
        raise HTTPException(409, "这笔账已有退款或回款，请先撤销关联流水，再修改或删除原账")


def undo(db: Session, user_id: int) -> list[Transaction]:
    lock_ledger(db)
    op = db.scalar(select(LedgerOperation).where(
        LedgerOperation.user_id == user_id, LedgerOperation.undone_at.is_(None),
    ).order_by(LedgerOperation.id.desc()).limit(1))
    if not op:
        raise HTTPException(400, "没有可以撤销的记账操作")
    after = json.loads(op.after_json)
    before = {item["id"]: item for item in json.loads(op.before_json)}
    ids = [item["id"] for item in after]
    rows = list(db.scalars(select(Transaction).where(Transaction.user_id == user_id, Transaction.id.in_(ids)).execution_options(populate_existing=True)).all())
    current = {row.id: row for row in rows}
    if any(item["id"] not in current or snapshot(current[item["id"]]) != item for item in after):
        raise HTTPException(409, "记录已发生变化，无法撤销这次操作")
    ensure_unlinked(db, user_id, ids)
    for row in rows:
        original = before.get(row.id)
        if original is None:
            row.deleted_at = utcnow()
            continue
        for field in SNAPSHOT_FIELDS:
            value = original[field]
            if value is not None and field in {"amount", "personal_amount", "recoverable_amount"}:
                value = Decimal(value)
            if value is not None and field in {"occurred_at", "deleted_at"}:
                value = dt.datetime.fromisoformat(value)
            setattr(row, field, value)
    op.undone_at = utcnow()
    db.flush()
    return enrich(db, rows)


def budget_month(value: Any, today: dt.date) -> str:
    month = str(value or today.strftime("%Y-%m"))
    try:
        dt.date.fromisoformat(month + "-01")
    except ValueError:
        raise HTTPException(400, "预算月份格式应为YYYY-MM") from None
    return month


def save_budget(db: Session, user_id: int, data: dict[str, Any], today: dt.date) -> Budget:
    lock_ledger(db)
    month = budget_month(data.get("month"), today)
    category = str(data.get("category") or "")
    if category and category not in CATEGORY_NAMES:
        raise HTTPException(400, "请选择已有分类")
    event = str(data.get("event") or "")[:64]
    row = db.scalar(select(Budget).where(Budget.user_id == user_id, Budget.month == month,
                                        Budget.category == category, Budget.event == event))
    if not row:
        row = Budget(user_id=user_id, month=month, category=category, event=event)
        db.add(row)
    row.amount = money(data.get("amount"))
    db.flush()
    return row


def budget_progress(db: Session, user_id: int, month: str) -> list[dict[str, Any]]:
    start = dt.date.fromisoformat(month + "-01")
    end = (start.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    budgets = list(db.scalars(select(Budget).where(Budget.user_id == user_id, Budget.month == month)).all())
    rows = list(db.scalars(select(Transaction).where(
        Transaction.user_id == user_id, Transaction.deleted_at.is_(None),
        Transaction.occurred_at >= dt.datetime.combine(start, dt.time.min),
        Transaction.occurred_at < dt.datetime.combine(end, dt.time.min),
    )).all())
    result = []
    for budget in budgets:
        spent = max(ZERO, sum((expense_value(r) for r in rows if (not budget.category or r.category == budget.category)
                               and (not budget.event or r.event == budget.event)), ZERO))
        result.append({"id": budget.id, "month": month, "category": budget.category, "event": budget.event,
                       "label": " · ".join(filter(None, [budget.event, budget.category])) or "总预算",
                       "amount": float(budget.amount), "spent": float(spent), "remaining": float(budget.amount - spent),
                       "percent": round(float(spent / budget.amount * 100), 1)})
    return result
