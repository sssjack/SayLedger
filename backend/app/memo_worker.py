"""备忘录到点提醒后台调度：约 30 秒扫描一次到期备忘。

到点时做三件事（同一事务）：
1. 写一条 assistant Message，网页端打开就能看到提醒；
2. 用户已绑微信且保存过会话 context 时，造一条 reply_pending 的 WechatDelivery，
   由现有微信 delivery_loop 用最近 context 主动发出（message_key 按备忘 id+触发时间去重）；
3. 一次性备忘置 done；每天/每周的顺延到下一次。

文件锁保证同一数据目录只有一个进程真正发送，和微信后台服务的约定一致。
没有微信绑定或没有有效 context 时如实把 push_status 记为 web_only_*，不谎称已发微信。
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
import uuid

from sqlalchemy import select

from app import memo as memo_mod
from app.auth import now_local
from app.config import settings
from app.db import Memo, SessionLocal, WechatBinding, WechatDelivery
from app.finance import lock_ledger
from app.wechat_api import digest, seal

logger = logging.getLogger(__name__)
SCAN_SECONDS = 30


class _MemoLease:
    """与微信 WorkerLease 相同的独占文件锁，只是锁文件不同。"""

    def __init__(self):
        self.stream = None

    def acquire(self) -> bool:
        if self.stream is not None:
            return True
        stream = open(settings.data_dir / "memo-worker.lock", "a+b")
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


def fire_due_memos(now: dt.datetime | None = None) -> int:
    """处理所有到期备忘，返回本次触发条数。时间口径为本地时区朴素时间。"""
    now = now or now_local()
    fired = 0
    with SessionLocal.begin() as db:
        lock_ledger(db)
        due = list(db.scalars(select(Memo).where(
            Memo.status == "active", Memo.next_trigger_at <= now,
        ).order_by(Memo.next_trigger_at)).all())
        for memo in due:
            trigger = memo.next_trigger_at
            text = memo_mod.build_reminder_text(memo, trigger)
            serialized = memo_mod.serialize_memo(memo)
            from app.main import save_message

            save_message(db, memo.user_id, "assistant", text,
                         {"kind": "memo", "memo": serialized, "fired": True})
            push_status = "web_only_no_binding"
            binding = db.get(WechatBinding, memo.user_id)
            if binding is not None and binding.state == "connected":
                context = ""
                if binding.last_context_cipher:
                    from app.wechat_api import unseal

                    try:
                        context = unseal(binding.last_context_cipher)
                    except Exception:
                        context = ""
                if context:
                    key = digest(f"memo:{memo.id}:{trigger.isoformat()}")
                    exists = db.scalar(select(WechatDelivery.id).where(
                        WechatDelivery.user_id == memo.user_id, WechatDelivery.message_key == key))
                    if exists is None:
                        envelope = json.dumps({"context": context, "proactive": True,
                                                 "memo_id": memo.id}, ensure_ascii=False)
                        db.add(WechatDelivery(
                            user_id=memo.user_id, revision=binding.revision,
                            peer_hash=digest(binding.peer_id), message_key=key,
                            envelope_cipher=seal(envelope), state="reply_pending", reply=text,
                            payload_json=json.dumps({"kind": "memo", "memo_id": memo.id}, ensure_ascii=False),
                            client_id="sayledger-" + uuid.uuid4().hex))
                    push_status = "wechat_queued"
                else:
                    push_status = "web_only_no_context"
            memo.push_status = push_status
            memo.last_sent_at = now
            if memo.recurrence in ("daily", "weekly"):
                memo.next_trigger_at = memo_mod.next_after(trigger, memo.recurrence, now)
            else:
                memo.status = "done"
            fired += 1
    return fired


class MemoManager:
    def __init__(self):
        self.lease = _MemoLease()
        self.task: asyncio.Task | None = None
        self.stopped = False

    def start(self):
        self.task = asyncio.create_task(self.run(), name="memo-manager")

    async def close(self):
        self.stopped = True
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        self.lease.close()

    async def run(self):
        while not self.stopped:
            try:
                if self.lease.acquire():
                    await asyncio.to_thread(fire_due_memos)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("备忘录提醒扫描异常（%s）", type(exc).__name__)
            await asyncio.sleep(SCAN_SECONDS)
