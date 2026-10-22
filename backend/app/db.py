from __future__ import annotations

import datetime as dt
import sqlite3
from contextlib import closing
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    inspect,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class Transaction(Base):
    """资金流水，金额为正数，收支含义由 kind 和个人承担金额决定。"""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    kind: Mapped[str] = mapped_column(String(24), default="expense", index=True)
    personal_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    recoverable_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    settlement_kind: Mapped[str] = mapped_column(String(24), default="")
    counterparty: Mapped[str] = mapped_column(String(128), default="")
    related_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    transfer_to: Mapped[str] = mapped_column(String(128), default="")
    input_fingerprint: Mapped[str] = mapped_column(String(64), default="", index=True)
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    category: Mapped[str] = mapped_column(String(32), index=True)
    merchant: Mapped[str] = mapped_column(String(128), default="")
    note: Mapped[str] = mapped_column(String(512), default="")
    # 付款方式：支付宝 / 微信 / 银行卡 / 信用卡 / 现金 / 其他，空字符串表示未记录
    payment_method: Mapped[str] = mapped_column(String(32), default="", index=True)
    # 自由备注：用户想额外记下的任何信息（"和谁""报销""发票号"…）
    remark: Mapped[str] = mapped_column(String(512), default="")
    items_json: Mapped[str] = mapped_column(Text, default="[]")
    occurred_at: Mapped[dt.datetime] = mapped_column(DateTime, index=True)
    source: Mapped[str] = mapped_column(String(16), default="text")
    raw_input: Mapped[str] = mapped_column(Text, default="")
    image_path: Mapped[str] = mapped_column(String(256), default="")
    event: Mapped[str] = mapped_column(String(64), default="", index=True)
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped[User] = relationship()


class LedgerOperation(Base):
    __tablename__ = "ledger_operations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    before_json: Mapped[str] = mapped_column(Text, default="[]")
    after_json: Mapped[str] = mapped_column(Text, default="[]")
    undone_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("user_id", "month", "category", "event"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    month: Mapped[str] = mapped_column(String(7))
    category: Mapped[str] = mapped_column(String(32), default="")
    event: Mapped[str] = mapped_column(String(64), default="")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))


class Preference(Base):
    __tablename__ = "preferences"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    payment_method: Mapped[str] = mapped_column(String(32), default="")
    rules_json: Mapped[str] = mapped_column(Text, default="{}")


class WechatBinding(Base):
    """微信账号和账本的绑定；凭证及轮询游标加密保存。"""

    __tablename__ = "wechat_bindings"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    revision: Mapped[str] = mapped_column(String(32), unique=True)
    bot_id: Mapped[str] = mapped_column(String(256), unique=True)
    peer_id: Mapped[str] = mapped_column(String(256), unique=True)
    token_cipher: Mapped[str] = mapped_column(Text)
    cursor_cipher: Mapped[str] = mapped_column(Text, default="")
    # 最近一条入站消息的 context_token（加密），主动提醒（备忘录到点推送）靠它发起会话
    last_context_cipher: Mapped[str] = mapped_column(Text, default="")
    base_url: Mapped[str] = mapped_column(String(256))
    state: Mapped[str] = mapped_column(String(24), default="connected")
    last_error: Mapped[str] = mapped_column(String(256), default="")
    last_poll_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    last_message_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class WechatLogin(Base):
    """扫码流程持久化，页面刷新或切换进程后仍可继续。"""

    __tablename__ = "wechat_logins"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    login_id: Mapped[str] = mapped_column(String(32), unique=True)
    qr_cipher: Mapped[str] = mapped_column(Text)
    content_cipher: Mapped[str] = mapped_column(Text)
    code_cipher: Mapped[str] = mapped_column(Text, default="")
    base_url: Mapped[str] = mapped_column(String(256))
    state: Mapped[str] = mapped_column(String(32), default="wait")
    error: Mapped[str] = mapped_column(String(256), default="")
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime)


class WechatDelivery(Base):
    """持久消息收件箱和待发送回复；记账结果和处理状态在同一事务内提交。"""

    __tablename__ = "wechat_deliveries"
    __table_args__ = (UniqueConstraint("user_id", "peer_hash", "message_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    revision: Mapped[str] = mapped_column(String(32), index=True)
    peer_hash: Mapped[str] = mapped_column(String(64))
    message_key: Mapped[str] = mapped_column(String(64))
    envelope_cipher: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    reply: Mapped[str] = mapped_column(Text, default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    client_id: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    retry_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str] = mapped_column(String(256), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class WechatWorker(Base):
    """后台消息服务心跳，仅由持有数据目录独占锁的进程更新。"""

    __tablename__ = "wechat_worker"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    heartbeat_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class Memo(Base):
    """备忘录/提醒：一次性或按天/周重复，到点由后台调度推送。"""

    __tablename__ = "memos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    content: Mapped[str] = mapped_column(String(512), default="")
    # 本地时区（LEDGER_TZ）的朴素时间，与 Transaction.occurred_at 口径一致
    next_trigger_at: Mapped[dt.datetime] = mapped_column(DateTime, index=True)
    recurrence: Mapped[str] = mapped_column(String(16), default="none", index=True)  # none|daily|weekly|interval
    interval_days: Mapped[int] = mapped_column(Integer, default=0)
    plan_id: Mapped[str] = mapped_column(String(32), default="")
    plan_json: Mapped[str] = mapped_column(Text, default="{}")
    stage_day: Mapped[int] = mapped_column(Integer, default=0)
    weekday: Mapped[int | None] = mapped_column(Integer, nullable=True)  # weekly 时 0=周一 ... 6=周日
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)  # active|done|cancelled
    source: Mapped[str] = mapped_column(String(16), default="text")
    raw_input: Mapped[str] = mapped_column(Text, default="")
    last_sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    # web_only_no_binding | web_only_no_context | wechat_queued | wechat_failed
    push_status: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class MemoPending(Base):
    """待确认的备忘草稿：缺时刻或缺事件时先存草稿，用户下一句补齐。"""

    __tablename__ = "memo_pending"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    draft_json: Mapped[str] = mapped_column(Text, default="{}")
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class Message(Base):
    """对话历史，用于让 AI 理解上下文与后续追问。"""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text, default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)


engine = create_engine(
    f"sqlite:///{settings.db_path}",
    connect_args={"check_same_thread": False},
    future=True,
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn: Any, _record: Any) -> None:
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


# 老库升级：create_all 不会给已存在的表加列，这里补齐新增字段。
MIGRATIONS: list[tuple[str, str, str]] = [
    ("transactions", "kind", "VARCHAR(24) NOT NULL DEFAULT 'expense'"),
    ("transactions", "personal_amount", "NUMERIC(12, 2)"),
    ("transactions", "recoverable_amount", "NUMERIC(12, 2) NOT NULL DEFAULT 0"),
    ("transactions", "settlement_kind", "VARCHAR(24) NOT NULL DEFAULT ''"),
    ("transactions", "counterparty", "VARCHAR(128) NOT NULL DEFAULT ''"),
    ("transactions", "related_id", "INTEGER"),
    ("transactions", "transfer_to", "VARCHAR(128) NOT NULL DEFAULT ''"),
    ("transactions", "input_fingerprint", "VARCHAR(64) NOT NULL DEFAULT ''"),
    ("transactions", "payment_method", "VARCHAR(32) NOT NULL DEFAULT ''"),
    ("transactions", "remark", "VARCHAR(512) NOT NULL DEFAULT ''"),
    ("transactions", "deleted_at", "DATETIME"),
    ("wechat_bindings", "last_context_cipher", "TEXT NOT NULL DEFAULT ''"),
    ("memos", "interval_days", "INTEGER NOT NULL DEFAULT 0"),
    ("memos", "plan_id", "VARCHAR(32) NOT NULL DEFAULT ''"),
    ("memos", "plan_json", "TEXT NOT NULL DEFAULT '{}'"),
    ("memos", "stage_day", "INTEGER NOT NULL DEFAULT 0"),
]


def _missing_migration_columns(inspector) -> list[tuple[str, str, str]]:
    """返回当前库里还缺的迁移列；表不存在时由 create_all 按最新结构建，不算缺失。"""
    missing: list[tuple[str, str, str]] = []
    tables = set(inspector.get_table_names())
    columns_cache: dict[str, set[str]] = {}
    for table, column, ddl in MIGRATIONS:
        if table not in tables:
            continue
        if table not in columns_cache:
            columns_cache[table] = {c["name"] for c in inspector.get_columns(table)}
        if column not in columns_cache[table]:
            missing.append((table, column, ddl))
    return missing


def migrate() -> None:
    from sqlalchemy import text

    with engine.begin() as conn:
        inspector = inspect(conn)
        for table, column, ddl in _missing_migration_columns(inspector):
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def init_db() -> None:
    # 第一次升级账务结构前，用 SQLite backup API 连同 WAL 一起备份。
    database_path = engine.url.database
    if database_path and database_path != ":memory:":
        with engine.connect() as connection:
            inspector = inspect(connection)
            if inspector.has_table("transactions"):
                if _missing_migration_columns(inspector):
                    backup_dir = Path(database_path).resolve().parent / "backups"
                    backup_dir.mkdir(parents=True, exist_ok=True)
                    backup_path = backup_dir / f"ledger-before-upgrade-{dt.datetime.now(dt.timezone.utc):%Y%m%d-%H%M%S-%f}.db"
                    with closing(sqlite3.connect(str(backup_path))) as target:
                        connection.connection.driver_connection.backup(target)
    Base.metadata.create_all(engine)
    migrate()
    with engine.begin() as connection:
        from sqlalchemy import text
        for column in ("kind", "related_id", "input_fingerprint"):
            connection.execute(text(f"CREATE INDEX IF NOT EXISTS ix_transactions_{column} ON transactions ({column})"))
