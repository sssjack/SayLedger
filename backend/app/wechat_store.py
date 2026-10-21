"""微信消息持久化和原子执行。网络重试只重发已保存的回复。"""
from __future__ import annotations

import datetime as dt
import json
import uuid
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select, update

from app.auth import now_local
from app.chat_service import ChatPlan, apply_chat, conversation_lock, prepare_chat
from app.config import settings
from app.db import SessionLocal, WechatBinding, WechatDelivery, utcnow
from app.finance import lock_ledger
from app.wechat_api import WechatError, digest, seal, unseal
from app.wechat_format import format_reply
from app.wechat_media import WechatInput, WechatMediaError, discard_images, prepare_input

HELP = ("一笔 · 你的记账搭子\n\n"
        "🧾 记账，很简单\n"
        "文字：午饭28元，微信付的\n"
        "图片：发小票或付款截图\n"
        "语音：按住说话，直接告诉我\n\n"
        "🔎 查账，也能随时改\n"
        "「昨天花了多少」\n"
        "「把刚才那笔改成32元」\n"
        "「撤销上一步」\n\n"
        "⏰ 备忘提醒，也可以\n"
        "「下周三提醒我交房租」（我会再问你几点）\n"
        "「每周三下午3点提醒我交水电费」\n"
        "「半小时后提醒我吃药」\n\n"
        "📎 小提示\n"
        "图片 ≤4张 · 每张 ≤8MB\n"
        "语音 ≤2分钟\n"
        "看不清或没听清，我会先问你～")

LEGACY_ACK_ERROR = "微信未确认回复已发送，服务会自动重试。"


def reconcile_legacy_acknowledgements(db) -> int:
    """修正旧版已被接口接受却因缺少 ret 而误判的发送状态，不重发或重做账务。"""
    result = db.execute(update(WechatDelivery).where(
        WechatDelivery.state.in_(["reply_pending", "failed"]),
        WechatDelivery.error == LEGACY_ACK_ERROR,
    ).values(state="sent", sent_at=utcnow(), retry_at=None, error="", envelope_cipher=""))
    return result.rowcount


def binding_snapshot(user_id: int, revision: str) -> dict | None:
    with SessionLocal() as db:
        row = db.get(WechatBinding, user_id)
        if row is None or row.revision != revision or row.state != "connected":
            return None
        return {"user_id": user_id, "revision": revision, "peer": row.peer_id,
                "token": unseal(row.token_cipher), "cursor": unseal(row.cursor_cipher), "base": row.base_url}


def set_binding_error(user_id: int, revision: str, message: str, *, expired: bool = False):
    with SessionLocal.begin() as db:
        values = {"last_error": message[:256]}
        if expired:
            values["state"] = "expired"
        db.execute(update(WechatBinding).where(WechatBinding.user_id == user_id,
                   WechatBinding.revision == revision).values(**values))


def ingest(user_id: int, revision: str, data: dict) -> int:
    """收件箱和游标一起提交；过滤非绑定发送者、群聊、历史重放和未完成消息。"""
    messages = data.get("msgs", [])
    cursor = data.get("get_updates_buf")
    if not isinstance(messages, list) or len(messages) > 1000 or (cursor is not None and not isinstance(cursor, str)):
        raise WechatError("微信消息格式异常，未推进接收位置，服务会自动重试。")
    with SessionLocal.begin() as db:
        lock_ledger(db)
        binding = db.get(WechatBinding, user_id)
        if binding is None or binding.revision != revision or binding.state != "connected":
            return 0
        peer_hash = digest(binding.peer_id)
        known = set(db.scalars(select(WechatDelivery.message_key).where(
            WechatDelivery.user_id == user_id, WechatDelivery.peer_hash == peer_hash,
            WechatDelivery.message_key.in_([digest(str(m.get("message_id") or m.get("client_id")))
                                          for m in messages if isinstance(m, dict)]))).all())
        incoming = []
        last_context = ""
        for message in messages:
            if not isinstance(message, dict) or message.get("from_user_id") != binding.peer_id:
                continue
            if message.get("message_type") != 1 or message.get("group_id") or message.get("message_state") in (0, 1):
                continue
            if message.get("delete_time_ms"):
                continue
            created = message.get("create_time_ms")
            if created is not None:
                try:
                    stamp = dt.datetime.fromtimestamp(int(created) / 1000, dt.timezone.utc).replace(tzinfo=None)
                except (ValueError, TypeError, OverflowError, OSError):
                    continue
                if stamp < binding.created_at - dt.timedelta(seconds=10) or stamp > utcnow() + dt.timedelta(minutes=5):
                    continue
            identity = message.get("message_id") or message.get("client_id")
            if not identity or not isinstance(identity, (str, int)):
                continue
            key = digest(str(identity))
            if key in known:
                continue
            items = message.get("item_list")
            context = message.get("context_token")
            if not isinstance(items, list) or not isinstance(context, str) or not context:
                continue
            envelope = json.dumps({"items": items, "context": context, "created": created}, ensure_ascii=False)
            if len(envelope.encode()) > 256 * 1024:
                continue
            incoming.append(WechatDelivery(user_id=user_id, revision=revision, peer_hash=peer_hash,
                            message_key=key, envelope_cipher=seal(envelope), client_id="sayledger-" + uuid.uuid4().hex))
            known.add(key)
            last_context = context
        db.add_all(incoming)
        if last_context:
            # 主动提醒（备忘录到点推送）需要用最近一次会话上下文发起发送
            binding.last_context_cipher = seal(last_context)
        added = len(incoming)
        if cursor:
            binding.cursor_cipher = seal(cursor)
        binding.last_poll_at = utcnow()
        binding.last_error = ""
        if added:
            binding.last_message_at = utcnow()
        return added


def process_pending(delivery_id: int, stopped=None):
    """媒体和 AI 不持有写锁；账本和待发送回复在同一事务内保存。"""
    with SessionLocal() as db:
        item = db.get(WechatDelivery, delivery_id)
        if item is None or item.state != "pending":
            return
        user_id, revision = item.user_id, item.revision
    with conversation_lock(user_id):
        with SessionLocal() as db:
            item = db.get(WechatDelivery, delivery_id)
            binding = db.get(WechatBinding, user_id)
            if (item is None or item.state != "pending" or binding is None
                    or binding.revision != revision or binding.state != "connected"):
                return
            envelope = json.loads(unseal(item.envelope_cipher))
        prepared, error, committed = WechatInput(), "", False
        try:
            try:
                prepared = prepare_input(envelope, user_id, delivery_id)
            except WechatMediaError as exc:
                prepared.text = "（微信消息未能完整识别）"
                error = str(exc) + " 这条消息没有记账。"
            body = SimpleNamespace(text=prepared.text, image_id=None, image_ids=prepared.images,
                                   local_date=None, confirm_duplicate=False)
            if envelope.get("created"):
                sent = dt.datetime.fromtimestamp(int(envelope["created"]) / 1000, dt.timezone.utc)
                body.local_date = sent.astimezone(ZoneInfo(settings.timezone)).date().isoformat()
            with SessionLocal() as db:
                if prepared.text == "确认重复记账" and not error and not prepared.images:
                    previous = db.scalar(select(WechatDelivery).where(WechatDelivery.user_id == user_id,
                        WechatDelivery.revision == revision, WechatDelivery.id < delivery_id,
                        WechatDelivery.state.in_(["reply_pending", "sent", "failed"]))
                        .order_by(WechatDelivery.id.desc()).limit(1))
                    payload = json.loads(previous.payload_json) if previous else {}
                    retry = payload.get("retry") or {}
                    if (previous and previous.created_at >= utcnow() - dt.timedelta(minutes=10)
                            and payload.get("kind") == "duplicate" and (retry.get("text") or retry.get("imageIds"))):
                        body.text, body.image_ids = retry.get("text", ""), retry.get("imageIds") or []
                        body.confirm_duplicate = True
                    else:
                        error = "没有可确认的重复账单，或确认已超过10分钟。这条消息没有记账，请重新发送原记账说明。"
                if error:
                    plan = ChatPlan(prepared.text, [], now_local().date(), {}, error=error)
                elif prepared.text in {"帮助", "使用说明", "help"} and not prepared.images:
                    plan = ChatPlan(prepared.text, [], now_local().date(), {"action": "chat", "reply": HELP})
                else:
                    plan = prepare_chat(db, user_id, body, channel="wechat")
            if stopped is not None and stopped.is_set():
                return
            with SessionLocal.begin() as db:
                lock_ledger(db)
                binding = db.get(WechatBinding, user_id)
                item = db.get(WechatDelivery, delivery_id)
                if (item is None or item.state != "pending" or binding is None
                        or binding.revision != revision or binding.state != "connected"):
                    return
                result = apply_chat(db, user_id, plan, channel="wechat")
                item.reply = format_reply(result["reply"], result["payload"], transcript=prepared.transcript)
                item.payload_json = json.dumps(result["payload"], ensure_ascii=False)
                item.state = "reply_pending"
            committed = True
        finally:
            if not committed:
                discard_images(prepared.images)


def fail_pending(delivery_id: int):
    with SessionLocal.begin() as db:
        lock_ledger(db)
        row = db.get(WechatDelivery, delivery_id)
        if row is not None and row.state == "pending":
            row.state = "reply_pending"
            row.reply = "🌱 这条消息还没处理好，也没有记入账本。稍后再试一次，或到网页手动记录吧。"


def next_delivery(user_id: int, revision: str, *, state: str | None = None,
                  due_only: bool = False) -> dict | None:
    with SessionLocal() as db:
        query = select(WechatDelivery).where(WechatDelivery.user_id == user_id,
            WechatDelivery.revision == revision,
            WechatDelivery.state.in_([state] if state else ["pending", "reply_pending"]))
        if due_only:
            query = query.where(or_(WechatDelivery.retry_at.is_(None), WechatDelivery.retry_at <= utcnow()))
        row = db.scalar(query.order_by(WechatDelivery.id).limit(1))
        if row is None:
            return None
        return {"id": row.id, "state": row.state, "reply": row.reply, "client_id": row.client_id,
                "retry_at": row.retry_at, "envelope": row.envelope_cipher}


def mark_sent(delivery_id: int):
    with SessionLocal.begin() as db:
        row = db.get(WechatDelivery, delivery_id)
        if row is not None and row.state == "reply_pending":
            row.state, row.sent_at, row.error, row.retry_at = "sent", utcnow(), "", None
            # 已发送消息仅短期保留确认重复记账所需的结果，清除回复上下文和原始输入。
            row.envelope_cipher = ""


def send_failed(delivery_id: int, error: str):
    with SessionLocal.begin() as db:
        row = db.get(WechatDelivery, delivery_id)
        if row is not None and row.state == "reply_pending":
            row.attempts += 1
            row.error = error[:256]
            row.retry_at = utcnow() + dt.timedelta(seconds=min(300, 2 ** row.attempts))
            if row.attempts >= 8:
                row.state = "failed"


def scrub_deliveries(db, user_id: int):
    """解绑清除消息内容和待发送回复，保留去重指纹防止重新连接后重复入账。"""
    db.execute(update(WechatDelivery).where(WechatDelivery.user_id == user_id).values(
        envelope_cipher="", reply="", payload_json="{}", error="", state="discarded"))
