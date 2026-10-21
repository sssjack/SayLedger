"""网页与微信共用的对话服务；模型调用不持有数据库写锁。"""
from __future__ import annotations

import datetime as dt
import json
import re
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import AIError, build_system_prompt
from app.config import settings
from app.db import Message, Transaction
from app.finance import budget_progress, enrich, lock_ledger, preference_data
from app.query import load_transactions, serialize

_locks: dict[int, threading.RLock] = {}
_guard = threading.Lock()


@contextmanager
def conversation_lock(user_id: int):
    """同一账本的对话串行处理，保证连续追问和撤销的顺序。"""
    with _guard:
        lock = _locks.setdefault(user_id, threading.RLock())
    with lock:
        yield


@dataclass
class ChatPlan:
    text: str
    images: list[str]
    today: dt.date
    data: dict[str, Any]
    confirm_duplicate: bool = False
    error: str = ""


def prepare_chat(db: Session, user_id: int, body: Any, *, exclude_current: bool = False,
                  channel: str = "web") -> ChatPlan:
    from app import main
    from app.conversation import local_intent

    images = list(dict.fromkeys([*(body.image_ids or []), *([body.image_id] if body.image_id else [])]))
    text = (body.text or "").strip()
    if not text and not images:
        raise HTTPException(400, "说点什么吧")
    for name in images:
        safe = re.sub(r"[^0-9a-zA-Z._-]", "", name)
        if not safe.startswith(f"{user_id}-") or not (settings.upload_dir / safe).exists():
            raise HTTPException(400, "图片无效，请重新上传")
    safe_images = [re.sub(r"[^0-9a-zA-Z._-]", "", name) for name in images]
    today = main.parse_local_date(body.local_date)
    history = main.recent_history(db, user_id, limit=13)
    if exclude_current:
        history = history[:-1]
    recent = enrich(db, list(db.scalars(select(Transaction).where(
        Transaction.user_id == user_id, Transaction.deleted_at.is_(None),
    ).order_by(Transaction.id.desc()).limit(30)).all()))
    queries = db.scalars(select(Message).where(Message.user_id == user_id, Message.role == "assistant")
                         .order_by(Message.id.desc()).limit(20)).all()
    last_query = next((p.get("query") for row in queries
                       if (p := json.loads(row.payload_json or "{}")).get("query")), None)
    context = {"preferences": preference_data(db, user_id), "last_query": last_query,
               "pending": [serialize(row) for row in load_transactions(db, user_id, {"pending": True})[:50]],
               "budgets": budget_progress(db, user_id, today.strftime("%Y-%m"))}
    messages = [{"role": "system", "content": build_system_prompt(today, [serialize(r) for r in recent], context)},
                *history, {"role": "user", "content": main.build_user_content(text, safe_images)}]
    if channel == "wechat":
        messages[0]["content"] += ("\n微信聊天风格：你叫一笔，是温柔可爱的记账搭子。回复简短自然，可用一两处合适的表情，"
            "不用亲昵称呼，不撒娇过度，不评判用户消费。金额、日期和执行结果必须准确；"
            "需要补充信息时温柔追问，失败时明确没有记账，不能把未执行动作说成成功。仍严格只输出JSON对象。")
    plan = ChatPlan(text, safe_images, today, {}, body.confirm_duplicate)
    try:
        plan.data = local_intent(text, today) if not safe_images else None
        if plan.data is None:
            plan.data = main.call_model(messages, max_tokens=3000).data
    except AIError:
        plan.error = "AI暂时不可用，这条消息没有执行记账操作。请稍后重试，或到网页手动记账。"
    return plan


def apply_chat(db: Session, user_id: int, plan: ChatPlan, *, save_user: bool = True,
               channel: str = "web") -> dict[str, Any]:
    """调用方持有写锁并负责提交，以便微信收件箱状态与账本原子保存。"""
    from app import main
    from app.conversation import execute

    lock_ledger(db)
    if save_user:
        main.save_message(db, user_id, "user", plan.text or "（发送了一张图片）",
                          {"channel": channel, "imageIds": plan.images,
                           "images": [f"/api/uploads/{n}" for n in plan.images]})
    if plan.error:
        reply, payload = plan.error, {"kind": "error"}
    else:
        try:
            # 业务校验失败只回滚当前动作，保留输入及待发送的错误说明。
            with db.begin_nested():
                reply, payload = execute(db, user_id, plan.data, plan.text, plan.today,
                                         plan.images[0] if plan.images else "",
                                         "image" if plan.images else "text", plan.confirm_duplicate)
        except HTTPException as exc:
            if exc.status_code == 409 and isinstance(exc.detail, dict) and exc.detail.get("duplicate_ids"):
                rows = enrich(db, list(db.scalars(select(Transaction).where(
                    Transaction.user_id == user_id, Transaction.id.in_(exc.detail["duplicate_ids"]),
                )).all()))
                reply = "这笔可能已经记过了，请核对下面的账单。确实是另一笔可以继续记入。"
                payload = {"kind": "duplicate", "candidates": [serialize(row) for row in rows],
                           "retry": {"text": plan.text, "imageIds": plan.images}}
            else:
                reply, payload = str(exc.detail), {"kind": "clarify"}
    reply = reply[:1000]
    payload["channel"] = channel
    main.save_message(db, user_id, "assistant", reply, payload)
    db.flush()
    return {"reply": reply, "payload": payload}


def process_chat(body: Any, user_id: int, db: Session) -> dict[str, Any]:
    from app.main import save_message

    with conversation_lock(user_id):
        # 保留网页发送后立即显示输入的行为，微信输入则随账本操作一起提交。
        images = list(dict.fromkeys([*(body.image_ids or []), *([body.image_id] if body.image_id else [])]))
        if not (body.text or "").strip() and not images:
            raise HTTPException(400, "说点什么吧")
        for name in images:
            if not re.fullmatch(r"[0-9a-zA-Z._-]+", name) or not name.startswith(f"{user_id}-") or not (settings.upload_dir / name).exists():
                raise HTTPException(400, "图片无效，请重新上传")
        save_message(db, user_id, "user", (body.text or "").strip() or "（发送了一张图片）",
                     {"imageIds": images, "images": [f"/api/uploads/{n}" for n in images]})
        db.commit()
        plan = prepare_chat(db, user_id, body, exclude_current=True)
        db.rollback()
        result = apply_chat(db, user_id, plan, save_user=False)
        db.commit()
        return result
