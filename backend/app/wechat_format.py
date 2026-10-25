"""把已执行的账本结果转换成微信文字，不让模型重新计算金额。"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata
from decimal import Decimal

from app.config import settings
from app.finance import KINDS

CATEGORY_EMOJIS = {"餐饮": "🍜", "交通": "🚕", "购物": "🛍️", "服饰": "👕", "居住": "🏠",
                   "娱乐": "🎮", "医疗": "💊", "教育": "📚", "数码": "💻", "旅行": "🧳", "人情": "🎁"}
KIND_EMOJIS = {"income": "💰", "refund": "↩️", "transfer": "🔄", "repayment": "💳", "lend": "🤝",
               "borrow": "🏦", "collection": "💌", "loan_repayment": "💳", "deposit": "🧷"}
METRIC_LABELS = {"expense": "个人净支出", "income": "收入", "flow": "流水金额", "outstanding": "待结清"}


def _plain(value) -> str:
    return " ".join(str(value or "").split())


def _short(value, width: int = 18) -> str:
    text = _plain(value)
    size = sum(2 if unicodedata.east_asian_width(char) in "WF" else 1 for char in text)
    if size <= width:
        return text
    result, used = [], 0
    for char in text:
        used += 2 if unicodedata.east_asian_width(char) in "WF" else 1
        if used > width - 2:
            break
        result.append(char)
    return "".join(result) + "…"


def _money(value) -> str:
    return f"¥{Decimal(str(value)):,.2f}"


def _date(value) -> str:
    text = str(value or "")[:10]
    try:
        return dt.date.fromisoformat(text).strftime("%Y.%m.%d")
    except ValueError:
        return _plain(value)


def _period(period: dict) -> str:
    start, end = period.get("start"), period.get("end")
    if start and start == end:
        return _date(start)
    if start and end:
        left, right = _date(start), _date(end)
        if left[:4] == right[:4] and re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", right):
            right = right[5:]
        return left + " ～ " + right
    if start:
        return _date(start) + " 起"
    if end:
        return "截至 " + _date(end)
    return "全部时间"


def _icon(row: dict) -> str:
    if row.get("kind") in KIND_EMOJIS:
        return KIND_EMOJIS[row["kind"]]
    label = str(row.get("note") or row.get("merchant") or "")
    if row.get("category") == "餐饮" and any(word in label for word in ("饮料", "奶茶", "咖啡", "果汁")):
        return "☕" if "咖啡" in label else "🥤"
    return CATEGORY_EMOJIS.get(row.get("category"), "🧾")


def _row_lines(row: dict, *, compact: bool, show_kind: bool = True,
               show_payment: bool = False) -> list[str]:
    label = _short(row.get("merchant") or row.get("note") or row.get("category") or "流水", 24)
    details = []
    if not compact or show_kind:
        details.append(KINDS.get(row.get("kind"), "流水"))
    if row.get("category"):
        details.append(_plain(row["category"]))
    amount = "  " + _money(row["amount"])
    if details:
        amount += " · " + " · ".join(dict.fromkeys(details))
    lines = [f"{_icon(row)} {label}", amount]
    if row.get("paymentMethod") and (not compact or show_payment):
        lines.append("  付款：" + _plain(row["paymentMethod"]))
    if row.get("kind") == "expense" and row.get("personalAmount") is not None and row["personalAmount"] != row["amount"]:
        lines.append("  个人承担 " + _money(row["personalAmount"]))
    if row.get("outstandingAmount", 0) > 0:
        lines.append("  " + ("待归还 " if row.get("kind") == "borrow" else "待收回 ") + _money(row["outstandingAmount"]))
    return lines


def _headline(reply: str, payload: dict) -> str:
    """只润色已执行的结果，不让展示文案把澄清、失败或候选误写成成功。"""
    kind = payload.get("kind")
    if kind == "record":
        if reply.startswith("记好了"):
            return f"🧾 记好啦 · {len(payload.get('transactions') or [])}笔"
        return "🧾 " + reply
    if kind == "query":
        return "🔎 帮你翻到账本啦～\n" + reply
    if kind in {"update", "delete"} and payload.get("found") is False:
        return "🔎 还没找到你说的那笔呢～\n" + reply
    if kind == "update":
        return "✏️ 已修改"
    if kind == "delete":
        return "🧹 " + reply
    if kind == "undo":
        return "↩️ " + reply
    if kind == "duplicate":
        return "👀 这笔看起来有点眼熟，先帮你拦一下～\n" + reply
    if kind in {"memo", "memo_query"}:
        return reply if reply.startswith(("📌", "📭", "🌿", "⏰")) else "⏰ " + reply
    if kind == "preference":
        return "🪄 记住啦，以后会按你的习惯记账～"
    if kind == "export":
        return "📦 已帮你整理好账单啦～\n登录网页，从对话里的导出卡片下载CSV。"
    icon = {"error": "🌱", "clarify": "💬", "budget": "🎯", "compare": "📊"}.get(kind, "🌷")
    return icon + " " + reply


def format_reply(reply: str, payload: dict, *, transcript: str = "") -> str:
    kind, period = payload.get("kind"), payload.get("range") or {}
    stats = payload.get("stats") or {}
    if kind == "query" and "display_total" in stats:
        lines = ["📒 账单小结", "📅 " + _period(period), ""]
        if stats.get("count", 0):
            label = METRIC_LABELS.get(stats.get("metric"), "个人净支出")
            lines += [f"{label}  {_money(stats['display_total'])}", f"共 {stats['count']} 笔账单"]
        else:
            lines.append("这个范围里还没有账单哦～")
    else:
        lines = [_headline(reply, payload)]
        if period.get("start") or period.get("end"):
            lines.append("📅 " + _period(period))
    rows = payload.get("transactions") or payload.get("candidates") or payload.get("deleted") or []
    compact = kind in {"query", "compare", "export"}
    payments = {row.get("paymentMethod") for row in rows[:8]}
    dates = {row.get("date") for row in rows[:8] if row.get("date")}
    shared_date = next(iter(dates)) if len(dates) == 1 else ""
    single_day = period.get("start") if period.get("start") == period.get("end") else None
    sort_by = (payload.get("query") or {}).get("sort_by") or payload.get("sort_by")
    if rows:
        if not compact and shared_date and shared_date != single_day:
            lines.append("📅 " + _date(shared_date))
        if compact:
            # 多日查询也不应丢掉“账单明细”标题；日期分组由下面的行循环按天插入。
            # 按金额排序时先说明顺序：微信文本只展示前 8 笔，也就是金额最大的 8 笔。
            if sort_by == "amount_desc":
                lines += ["", "↕ 按金额从大到小排列"]
            elif sort_by == "amount_asc":
                lines += ["", "↕ 按金额从小到大排列"]
            lines += ["", "账单明细"]
    previous_date = single_day if compact else shared_date
    kinds = {row.get("kind") for row in rows[:8]}
    show_kind = len(kinds) != 1 or not kinds.issubset({"expense"})
    for row in rows[:8]:
        lines.append("")
        if row.get("date") and row["date"] != previous_date:
            lines += ["📅 " + _date(row["date"]), ""]
            previous_date = row["date"]
        lines.extend(_row_lines(row, compact=compact, show_kind=show_kind,
                                show_payment=len(payments) > 1))
    more = len(rows) > 8 or bool(payload.get("truncated"))
    if more:
        count = stats.get("count")
        hint = f"已展示 {min(8, len(rows))} / {count} 笔" if count is not None else "这里只展示前 8 笔"
        lines += ["", "📚 " + hint, "其余明细可到完整账本查看"]
    if kind == "duplicate":
        lines += ["", "确实是另一笔？", "10分钟内回复「确认重复记账」"]
    choices = (payload.get("choices") or [])[:6]
    if choices:
        lines.append("")
    for choice in choices:
        lines.append(f"💬 可回复：{choice['text']}")
    for budget in (payload.get("budgets") or [])[:6]:
        lines += ["", f"🎯 {_plain(budget.get('label', '预算'))}", "  预算 " + _money(budget["amount"])]
        if budget.get("spent") is not None:
            lines.append("  已用 " + _money(budget["spent"]))
        remaining = Decimal(str(budget["remaining"]))
        lines.append("  " + ("超支 " if remaining < 0 else "剩余 ") + _money(abs(remaining)))
    if payload.get("preference"):
        preference = payload["preference"]
        lines += ["", f"💳 默认付款方式：{preference.get('payment_method') or '未设置'}"]
        for name, category in list((preference.get("rules") or {}).items())[:5]:
            lines.append(f"{name} → {category}")
    if kind in {"update", "delete"} and payload.get("found") is False:
        lines += ["", "补充商户、金额或日期，就能继续找啦。"]
    if kind in {"record", "update", "delete"} and payload.get("found") is not False:
        lines += ["", "↩️ 可说「撤销上一步」"]
    if transcript:
        lines += ["", "🎙️ 听到你说", _short(transcript, 100)]
    # 日常短回复不重复贴长网址，仅帮助、导出和未展示完的明细提供入口。
    help_reply = kind == "chat" and "你的记账搭子" in reply
    need_link = more or kind == "export" or help_reply
    footer = f"\n\n📖 完整账本  \n{settings.public_url}" if settings.public_url and need_link else ""
    # 为链接保留位置；按 UTF-8 字节截断，避免中文使消息超过通道限制。
    text = "\n".join(lines).strip()
    # 显式硬换行兼容 Markdown 展示，避免标题、日期和明细被合并到同一行。
    text = "\n".join(line.rstrip() + "  " if line.strip() else "" for line in text.splitlines()).strip()
    budget = max(1000, 3800 - len(footer.encode()))
    if len(text.encode()) > budget:
        text = text.encode()[:budget - 60].decode("utf-8", errors="ignore") + "\n更多明细请到网页查看。"
    return text + footer
