from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import os
from typing import Any
from zoneinfo import ZoneInfo

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal, User

ALGO = "HS256"


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or base64.b16encode(os.urandom(16)).decode()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000)
    return f"pbkdf2${salt}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt, encoded = stored.split("$", 2)
    except ValueError:
        return False
    if scheme != "pbkdf2":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000)
    return hmac.compare_digest(base64.b64encode(digest).decode(), encoded)


def create_token(user_id: int) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + dt.timedelta(days=settings.token_days),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGO)


def _decode(token: str) -> int | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGO])
        return int(payload["sub"])
    except Exception:
        return None


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get("ledger_token") or ""
    if not token:
        header = request.headers.get("authorization", "")
        if header.lower().startswith("bearer "):
            token = header[7:]
    user_id = _decode(token) if token else None
    if not user_id:
        raise HTTPException(status_code=401, detail="请先登录")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


def ensure_owner(username: str) -> dict[str, str]:
    """首次启动时，用环境变量里的密码创建唯一账户。"""
    db = SessionLocal()
    try:
        existing = db.scalar(select(User).limit(1))
        if existing or not settings.password:
            return {"created": "skipped"}
        db.add(User(username=username, password_hash=hash_password(settings.password)))
        db.commit()
        return {"created": "ok"}
    finally:
        db.close()


def now_local() -> dt.datetime:
    return dt.datetime.now(ZoneInfo(settings.timezone)).replace(tzinfo=None)
