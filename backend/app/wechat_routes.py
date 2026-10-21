"""已登录账本用户可管理自己的微信连接；不向浏览器返回 Bot 凭证。"""
from __future__ import annotations

import datetime as dt
import uuid
from io import BytesIO

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.auth import current_user, get_db
from app.config import settings
from app.db import WechatBinding, WechatDelivery, WechatLogin, WechatWorker, utcnow
from app.finance import lock_ledger
from app.wechat_api import API_BASE, WechatError, seal, unseal
from app.wechat_store import scrub_deliveries
from app.wechat_worker import ACTIVE_LOGINS

router = APIRouter(prefix="/api/wechat")


def _enabled():
    if not settings.wechat_enabled:
        raise HTTPException(503, "微信入口尚未启用，请联系服务管理员。")


def _login_view(row: WechatLogin | None):
    if row is None:
        return None
    expired = row.expires_at <= utcnow() and row.state in ACTIVE_LOGINS | {"creating"}
    return {"id": row.login_id, "state": "expired" if expired else row.state,
            "error": "二维码已过期，请重新生成。" if expired else row.error,
            "expires_at": row.expires_at.isoformat() + "Z",
            "verify_pending": bool(row.code_cipher) and row.state == "need_verifycode",
            "qr_available": bool(row.content_cipher) and not expired and row.state in ACTIVE_LOGINS}


@router.get("/status")
def status(user=Depends(current_user), db: Session = Depends(get_db)):
    binding = db.get(WechatBinding, user.id)
    worker = db.get(WechatWorker, 1)
    running = bool(settings.wechat_enabled and worker and worker.heartbeat_at > utcnow() - dt.timedelta(seconds=20))
    counts = dict(db.execute(select(WechatDelivery.state, func.count()).where(
        WechatDelivery.user_id == user.id, WechatDelivery.state.in_(["reply_pending", "failed"]))
        .group_by(WechatDelivery.state)).all())
    return {"enabled": settings.wechat_enabled, "worker_running": running,
            "connected": binding is not None, "state": binding.state if binding else "disconnected",
            "last_error": binding.last_error if binding else "",
            "last_poll_at": binding.last_poll_at.isoformat() + "Z" if binding and binding.last_poll_at else None,
            "last_message_at": binding.last_message_at.isoformat() + "Z" if binding and binding.last_message_at else None,
            "pending_replies": counts.get("reply_pending", 0), "failed_replies": counts.get("failed", 0),
            "login": _login_view(db.get(WechatLogin, user.id))}


@router.post("/login")
async def start_login(request: Request, user=Depends(current_user), db: Session = Depends(get_db)):
    _enabled()
    lock_ledger(db)
    if db.get(WechatBinding, user.id) is not None:
        raise HTTPException(409, "请先断开当前微信连接，再重新扫码。")
    existing = db.get(WechatLogin, user.id)
    if existing and existing.expires_at > utcnow() and existing.state in ACTIVE_LOGINS | {"creating"}:
        return _login_view(existing)
    manager = getattr(request.app.state, "wechat_manager", None)
    if manager is None:
        raise HTTPException(503, "微信后台服务尚未启动，请稍后重试。")
    # 先保存会话标识再请求微信，取消连接能够使正在生成的二维码失效。
    login_id = uuid.uuid4().hex
    if existing is None:
        existing = WechatLogin(user_id=user.id)
        db.add(existing)
    existing.login_id, existing.state = login_id, "creating"
    existing.qr_cipher, existing.content_cipher, existing.code_cipher, existing.error = "", "", "", ""
    existing.base_url, existing.expires_at = API_BASE, utcnow() + dt.timedelta(minutes=5)
    db.commit()
    try:
        data = await manager.api.qr()
        qr_cipher, content_cipher = seal(data["qrcode"]), seal(data["qrcode_img_content"])
    except WechatError as exc:
        db.rollback()
        db.execute(update(WechatLogin).where(WechatLogin.user_id == user.id,
            WechatLogin.login_id == login_id).values(state="error", error=str(exc)))
        db.commit()
        raise HTTPException(502, str(exc)) from None
    # 请求二维码期间用户可能已取消、重新连接；写入前重新读取并串行检查。
    db.rollback()
    lock_ledger(db)
    if db.get(WechatBinding, user.id) is not None:
        raise HTTPException(409, "当前账本已连接微信，请刷新页面。")
    # commit 后身份映射仍可能缓存旧对象，必须实际查询，才能识别另一请求的取消。
    row = db.scalar(select(WechatLogin).where(WechatLogin.user_id == user.id)
                    .execution_options(populate_existing=True))
    if row is None or row.login_id != login_id or row.state != "creating":
        raise HTTPException(409, "本次连接已取消，请重新生成二维码。")
    row.qr_cipher, row.content_cipher = qr_cipher, content_cipher
    row.base_url, row.state, row.error, row.code_cipher = API_BASE, "wait", "", ""
    row.expires_at = utcnow() + dt.timedelta(minutes=5)
    db.commit()
    return _login_view(row)


@router.get("/login/{login_id}/qr")
def login_qr(login_id: str, user=Depends(current_user), db: Session = Depends(get_db)):
    _enabled()
    row = db.get(WechatLogin, user.id)
    if row is None or row.login_id != login_id or not _login_view(row)["qr_available"]:
        raise HTTPException(404, "二维码已失效，请重新生成。")
    try:
        content = unseal(row.content_cipher)
    except WechatError as exc:
        raise HTTPException(409, str(exc)) from None
    buffer = BytesIO()
    qrcode.make(content, box_size=6, border=4).save(buffer, format="PNG")
    return Response(buffer.getvalue(), media_type="image/png",
                    headers={"Cache-Control": "no-store, private", "X-Content-Type-Options": "nosniff"})


class VerifyBody(BaseModel):
    code: str = Field(min_length=1, max_length=12, pattern=r"^[0-9]+$")


@router.post("/login/{login_id}/verify")
def verify_login(login_id: str, body: VerifyBody, user=Depends(current_user), db: Session = Depends(get_db)):
    _enabled()
    lock_ledger(db)
    row = db.get(WechatLogin, user.id)
    if row is None or row.login_id != login_id or row.expires_at <= utcnow():
        raise HTTPException(409, "扫码会话已过期，请重新生成二维码。")
    if row.state != "need_verifycode":
        raise HTTPException(409, "当前无需输入验证数字，请等待扫码结果。")
    if row.code_cipher:
        raise HTTPException(409, "正在验证，请稍候。")
    row.code_cipher, row.error = seal(body.code), ""
    db.commit()
    return {"ok": True}


@router.delete("/connection")
def disconnect(user=Depends(current_user), db: Session = Depends(get_db)):
    lock_ledger(db)
    db.execute(delete(WechatBinding).where(WechatBinding.user_id == user.id))
    db.execute(delete(WechatLogin).where(WechatLogin.user_id == user.id))
    scrub_deliveries(db, user.id)
    db.commit()
    return {"ok": True}


@router.post("/replies/retry")
def retry_replies(user=Depends(current_user), db: Session = Depends(get_db)):
    _enabled()
    lock_ledger(db)
    binding = db.get(WechatBinding, user.id)
    if binding is None or binding.state != "connected":
        raise HTTPException(409, "请先重新连接微信。")
    result = db.execute(update(WechatDelivery).where(WechatDelivery.user_id == user.id,
        WechatDelivery.revision == binding.revision, WechatDelivery.state == "failed").values(
        state="reply_pending", attempts=0, retry_at=None, error=""))
    db.commit()
    return {"ok": True, "count": result.rowcount}
