"""随 FastAPI 启停的微信后台服务；文件锁保证同一数据目录仅有一个收发进程。"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
import threading

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.db import SessionLocal, WechatBinding, WechatDelivery, WechatLogin, WechatWorker, utcnow
from app.finance import lock_ledger
from app.wechat_api import WechatAPI, WechatError, seal, trusted_base, unseal
from app.wechat_store import (binding_snapshot, fail_pending, ingest, mark_sent, next_delivery,
                              process_pending, reconcile_legacy_acknowledgements, send_failed, set_binding_error)

logger = logging.getLogger(__name__)
ACTIVE_LOGINS = {"wait", "scaned", "scaned_but_redirect", "need_verifycode"}


class WorkerLease:
    def __init__(self):
        self.stream = None

    def acquire(self) -> bool:
        if self.stream is not None:
            return True
        stream = open(settings.data_dir / "wechat-worker.lock", "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                if stream.seek(0, 2) == 0:
                    stream.write(b"0")
                    stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            stream.close()
            return False
        self.stream = stream
        return True

    def close(self):
        if self.stream is not None:
            self.stream.close()
            self.stream = None


def runtime_rows() -> tuple[list, list]:
    with SessionLocal.begin() as db:
        lock_ledger(db)
        reconcile_legacy_acknowledgements(db)
        worker = db.get(WechatWorker, 1)
        if worker is None:
            db.add(WechatWorker(id=1))
        else:
            worker.heartbeat_at = utcnow()
        logins = [(row.user_id, row.login_id) for row in db.scalars(select(WechatLogin).where(
            WechatLogin.state.in_(ACTIVE_LOGINS))).all()]
        bindings = [(row.user_id, row.revision) for row in db.scalars(select(WechatBinding).where(
            WechatBinding.state == "connected")).all()]
        db.execute(update(WechatDelivery).where(WechatDelivery.state == "sent",
            WechatDelivery.sent_at < utcnow() - dt.timedelta(minutes=10),
            WechatDelivery.payload_json != "{}").values(reply="", payload_json="{}"))
        return logins, bindings


def login_snapshot(user_id: int, login_id: str) -> dict | None:
    with SessionLocal.begin() as db:
        row = db.get(WechatLogin, user_id)
        if row is None or row.login_id != login_id or row.state not in ACTIVE_LOGINS:
            return None
        if row.expires_at <= utcnow():
            row.state, row.qr_cipher, row.content_cipher, row.code_cipher = "expired", "", "", ""
            return None
        return {"base": row.base_url, "qrcode": unseal(row.qr_cipher),
                "code": unseal(row.code_cipher), "state": row.state}


def apply_login_status(user_id: int, login_id: str, data: dict) -> bool:
    """返回是否结束扫码；绑定前再检查登录会话，防止已取消的扫码写回。"""
    import uuid

    with SessionLocal.begin() as db:
        lock_ledger(db)
        row = db.get(WechatLogin, user_id)
        if row is None or row.login_id != login_id or row.state not in ACTIVE_LOGINS:
            return True
        if row.expires_at <= utcnow():
            row.state, row.qr_cipher, row.content_cipher, row.code_cipher = "expired", "", "", ""
            return True
        state = data.get("status")
        if state == "confirmed":
            for key in ("bot_token", "ilink_bot_id", "ilink_user_id"):
                if not isinstance(data.get(key), str) or not data[key] or len(data[key]) > 8192:
                    raise WechatError("微信未返回完整绑定信息，请重新扫码。")
            if len(data["ilink_bot_id"]) > 256 or len(data["ilink_user_id"]) > 256:
                raise WechatError("微信返回的账号信息无效，请重新扫码。")
            base = trusted_base(data.get("baseurl") or row.base_url)
            conflict = db.scalar(select(WechatBinding).where(
                (WechatBinding.bot_id == data["ilink_bot_id"]) | (WechatBinding.peer_id == data["ilink_user_id"])))
            if conflict is not None:
                row.state, row.error = "error", "这个微信已连接到账本，请先断开原连接。"
            elif db.get(WechatBinding, user_id) is not None:
                row.state, row.error = "error", "当前账本已有微信连接，请先断开原连接。"
            else:
                db.add(WechatBinding(user_id=user_id, revision=uuid.uuid4().hex,
                       bot_id=data["ilink_bot_id"], peer_id=data["ilink_user_id"],
                       token_cipher=seal(data["bot_token"]), base_url=base))
                row.state, row.error = "confirmed", ""
            row.qr_cipher, row.content_cipher, row.code_cipher = "", "", ""
            return True
        if state == "scaned_but_redirect":
            host = data.get("redirect_host")
            if not isinstance(host, str) or not host:
                raise WechatError("微信没有返回有效的扫码验证地址，请重新扫码。")
            row.base_url = trusted_base("https://" + host)
        elif state == "need_verifycode":
            row.error = "数字不匹配，请重新输入手机微信显示的数字。" if row.code_cipher else ""
            row.code_cipher = ""
        elif state in {"expired", "verify_code_blocked", "binded_redirect"}:
            row.state = "expired" if state == "expired" else "error"
            row.error = {"expired": "二维码已过期，请重新生成。", "verify_code_blocked": "验证次数过多，请稍后重新生成二维码。",
                         "binded_redirect": "微信已绑定其他实例，请检查微信 ClawBot 连接后重新扫码。"}[state]
            row.qr_cipher, row.content_cipher, row.code_cipher = "", "", ""
            return True
        elif state not in ACTIVE_LOGINS:
            raise WechatError("微信返回未知的扫码状态，请稍后重试。")
        else:
            row.code_cipher, row.error = "", ""
        row.state = state
        return False


def login_error(user_id: int, login_id: str, message: str):
    with SessionLocal.begin() as db:
        db.execute(update(WechatLogin).where(WechatLogin.user_id == user_id,
            WechatLogin.login_id == login_id).values(error=message[:256]))


class WechatManager:
    def __init__(self):
        self.api = WechatAPI()
        self.lease = WorkerLease()
        self.stopped = threading.Event()
        self.jobs: dict[tuple, asyncio.Task] = {}
        self.task = None

    def start(self):
        if settings.wechat_enabled:
            self.task = asyncio.create_task(self.run(), name="wechat-manager")

    async def close(self):
        self.stopped.set()
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        for task in self.jobs.values():
            task.cancel()
        await asyncio.gather(*self.jobs.values(), return_exceptions=True)
        self.lease.close()
        await self.api.close()

    async def run(self):
        while True:
            try:
                if self.lease.acquire():
                    logins, bindings = await asyncio.to_thread(runtime_rows)
                    desired = {("login", u, r) for u, r in logins} | {("binding", u, r) for u, r in bindings}
                    for key in list(self.jobs):
                        task = self.jobs[key]
                        if key not in desired or task.done():
                            if task.done() and not task.cancelled() and task.exception():
                                logger.warning("微信后台任务异常（%s）", type(task.exception()).__name__)
                            task.cancel()
                            await asyncio.gather(task, return_exceptions=True)
                            del self.jobs[key]
                    for key in desired - self.jobs.keys():
                        operation = self.login_loop if key[0] == "login" else self.binding_loop
                        self.jobs[key] = asyncio.create_task(operation(key[1], key[2]))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("微信服务暂时无法更新状态（%s）", type(exc).__name__)
            await asyncio.sleep(2)

    async def login_loop(self, user_id: int, login_id: str):
        failures = 0
        while True:
            try:
                current = await asyncio.to_thread(login_snapshot, user_id, login_id)
                if current is None:
                    return
                if current["state"] == "need_verifycode" and not current["code"]:
                    await asyncio.sleep(1)
                    continue
                data = await self.api.qr_status(current["base"], current["qrcode"], current["code"])
                if await asyncio.to_thread(apply_login_status, user_id, login_id, data):
                    return
                failures = 0
            except WechatError as exc:
                await asyncio.to_thread(login_error, user_id, login_id, str(exc))
                failures += 1
            except IntegrityError:
                await asyncio.to_thread(login_error, user_id, login_id, "该微信已绑定，请先断开原连接。")
                return
            await asyncio.sleep(min(15, 1 + 2 ** min(failures, 3)))

    async def binding_loop(self, user_id: int, revision: str):
        tasks = [asyncio.create_task(self.receive_loop(user_id, revision)),
                 asyncio.create_task(self.processing_loop(user_id, revision)),
                 asyncio.create_task(self.delivery_loop(user_id, revision))]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            errors = [result for result in results if isinstance(result, Exception)]
            if errors:
                logger.warning("微信收发任务异常（%s）", type(errors[0]).__name__)
                await asyncio.to_thread(set_binding_error, user_id, revision,
                                        "微信收发暂时中断，服务正在自动恢复。")

    async def receive_loop(self, user_id: int, revision: str):
        failures = 0
        while True:
            try:
                current = await asyncio.to_thread(binding_snapshot, user_id, revision)
                if current is None:
                    return
                data = await self.api.updates(current["base"], current["token"], current["cursor"])
                await asyncio.to_thread(ingest, user_id, revision, data)
                failures = 0
            except WechatError as exc:
                await asyncio.to_thread(set_binding_error, user_id, revision, str(exc), expired=exc.expired)
                if exc.expired:
                    return
                failures += 1
            await asyncio.sleep(min(30, 1 + 2 ** min(failures, 4)))

    async def processing_loop(self, user_id: int, revision: str):
        # 连续追问依赖上一条执行结果，消息必须按顺序使用各自的原子事务。
        while True:
            current = await asyncio.to_thread(binding_snapshot, user_id, revision)
            if current is None:
                return
            item = await asyncio.to_thread(next_delivery, user_id, revision, state="pending")
            if item is None:
                await asyncio.sleep(1)
                continue
            try:
                await asyncio.to_thread(process_pending, item["id"], self.stopped)
            except Exception as exc:
                logger.warning("微信消息未完成处理（%s）", type(exc).__name__)
                await asyncio.to_thread(fail_pending, item["id"])

    async def delivery_loop(self, user_id: int, revision: str):
        # 已失败回复的退避不能占住队首，新回复仍可正常发送；账务执行顺序由 processing_loop 保证。
        while True:
            current = await asyncio.to_thread(binding_snapshot, user_id, revision)
            if current is None:
                return
            item = await asyncio.to_thread(next_delivery, user_id, revision, state="reply_pending", due_only=True)
            if item is None:
                await asyncio.sleep(1)
                continue
            try:
                context = json.loads(unseal(item["envelope"]))["context"]
                await self.api.send(current["base"], current["token"], current["peer"], context,
                                    item["client_id"], item["reply"])
                await asyncio.to_thread(mark_sent, item["id"])
            except WechatError as exc:
                await asyncio.to_thread(send_failed, item["id"], str(exc))
                if exc.expired:
                    await asyncio.to_thread(set_binding_error, user_id, revision, str(exc), expired=True)
                    return
