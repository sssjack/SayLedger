"""短期对话上下文：保留结构化结果，按需找回当前用户最近引用的图片。"""
from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select

from app.config import settings
from app.db import Message, utcnow

CONTEXT_TTL = dt.timedelta(minutes=30)
_REFERENCE = re.compile(r"这(?:张|些|份|件|笔|条)|那(?:张|些|份|件|笔|条)|这个(?!月|星期|周)|那个|"
                        r"刚才|上面|上一(?:张|条|笔|个)|按照|按图|照着|同样|一样|第[\d一二三四五六七八九十]+天")


def needs_context(text: str) -> bool:
    return bool(_REFERENCE.search(text or ""))


def payload_of(row: Message) -> dict:
    try:
        value = json.loads(row.payload_json or "{}")
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def stage_anchor(text: str, today: dt.date) -> dict | None:
    from app.memo import cn_int

    match = re.search(r"(?:今天|现在)(?:已经)?(?:是|算|到)?第([\d一二三四五六七八九十]+)天", text or "")
    day = cn_int(match[1]) if match else None
    return {"date": today.isoformat(), "day": day} if day and 1 <= day <= 60 else None


@dataclass
class DialogueContext:
    history: list[dict] = field(default_factory=list)
    state: dict = field(default_factory=dict)
    images: list[str] = field(default_factory=list)
    followup: bool = False


def load_context(db, user_id: int, text: str, *, channel: str, exclude_current: bool,
                 today: dt.date, pending: dict | None = None) -> DialogueContext:
    from app import main

    rows = list(db.scalars(select(Message).where(Message.user_id == user_id)
                          .order_by(Message.id.desc()).limit(40)).all())
    if exclude_current and rows and rows[0].role == "user":
        rows = rows[1:]
    # 同一账本的数据共用，但“这个、上一张”的短期指代不能串到另一个聊天入口。
    rows = [row for row in rows if payload_of(row).get("channel", "web") == channel
            and row.created_at >= utcnow() - CONTEXT_TTL][:12]
    result = DialogueContext()
    last_assistant = next((row for row in rows if row.role == "assistant"), None)
    last_payload = payload_of(last_assistant) if last_assistant else {}
    unresolved = bool(last_payload.get("kind") in {"clarify", "memo"}
                      and (last_payload.get("missing") or last_payload.get("kind") == "clarify"))
    reference = needs_context(text) or bool(pending and needs_context(str(pending.get("content", ""))))
    independent = bool(re.search(r"查账|账单|预算|花了多少|花多少|花费多少|收入多少", text)
                       or (re.search(r"午饭|晚饭|早餐|咖啡|打车|买了", text) and re.search(r"\d", text)))
    result.followup = reference or (unresolved and len(text) <= 100 and not independent)
    last_action = {key: last_payload[key] for key in ("kind", "missing", "query", "range", "memo", "memos")
                   if key in last_payload}
    if last_payload.get("transactions"):
        last_action["transaction_ids"] = [row["id"] for row in last_payload["transactions"] if "id" in row]
    result.state = {"last_action": last_action, "pending_memo": pending}
    anchor = stage_anchor(text, today)
    if anchor is None and result.followup:
        for row in rows:
            if row.role != "user":
                continue
            local_date = row.created_at.replace(tzinfo=dt.timezone.utc).astimezone(ZoneInfo(settings.timezone)).date()
            anchor = stage_anchor(row.content, local_date)
            if anchor:
                break
    if anchor:
        result.state["stage_anchor"] = anchor
    image_row = None
    if result.followup:
        # 不越过一个明确的新话题去找旧图；最多回溯最近3条用户消息。
        users = [row for row in rows if row.role == "user"][:3]
        for row in users:
            payload = payload_of(row)
            names = payload.get("imageIds") or payload.get("contextImageIds") or []
            if isinstance(names, list) and names:
                image_row = row
                for name in names[:2]:
                    if (isinstance(name, str) and re.fullmatch(r"[0-9a-zA-Z._-]+", name)
                            and name.startswith(f"{user_id}-") and (settings.upload_dir / name).is_file()):
                        result.images.append(name)
                break
            if row is users[0] and last_payload.get("kind") in {"record", "query", "budget", "preference"}:
                break
            if not needs_context(row.content) and len(row.content) > 40:
                break
    for row in reversed(rows):
        content = row.content
        if row is image_row and result.images:
            parts = [{"type": "text", "text": content or "用户此前发来的图片，仅作为对话参考。"}]
            valid = []
            for name in result.images:
                try:
                    parts.append({"type": "image_url", "image_url": {"url": main.image_to_data_url(name), "detail": "high"}})
                    valid.append(name)
                except (HTTPException, OSError):
                    continue
            result.images = valid
            content = parts
        if content:
            result.history.append({"role": row.role, "content": content})
    if reference and not result.images:
        result.state["image_reference_available"] = False
    return result
