"""把已执行的账本结果转换成微信文字，不让模型重新计算金额。"""
from __future__ import annotations

from app.config import settings
from app.finance import KINDS

CATEGORY_EMOJIS = {"餐饮": "🍜", "交通": "🚕", "购物": "🛍️", "服饰": "👕", "居住": "🏠",
                   "娱乐": "🎮", "医疗": "💊", "教育": "📚", "数码": "💻", "旅行": "🧳", "人情": "🎁"}
KIND_EMOJIS = {"income": "💰", "refund": "↩️", "transfer": "🔄", "repayment": "💳", "lend": "🤝",
               "borrow": "🏦", "collection": "💌", "loan_repayment": "💳", "deposit": "🧷"}


def _headline(reply: str, payload: dict) -> str:
    """只润色已执行的结果，不让展示文案把澄清、失败或候选误写成成功。"""
    kind = payload.get("kind")
    if kind == "record":
        if reply.startswith("记好了"):
            return f"🧾 记好啦～{len(payload.get('transactions') or [])}笔流水收进小账本！"
        return "🧾 " + reply
    if kind == "query":
        return "🔎 帮你翻到账本啦～\n" + reply
    if kind in {"update", "delete"} and payload.get("found") is False:
        return "🔎 还没找到你说的那笔呢～\n" + reply
    if kind == "update":
        return "✏️ 已修改，帮你改好啦～"
    if kind == "delete":
        return "🧹 " + reply + " 小账本已更新～"
    if kind == "undo":
        return "↩️ " + reply + " 小账本同步好啦～"
    if kind == "duplicate":
        return "👀 这笔看起来有点眼熟，先帮你拦一下～\n" + reply
    if kind == "preference":
        return "🪄 记住啦，以后会按你的习惯记账～"
    if kind == "export":
        return "📦 已帮你整理好账单啦～\n登录网页，从对话里的导出卡片下载CSV。"
    icon = {"error": "🌱", "clarify": "💬", "budget": "🎯", "compare": "📊"}.get(kind, "🌷")
    return icon + " " + reply


def format_reply(reply: str, payload: dict, *, transcript: str = "") -> str:
    kind = payload.get("kind")
    lines = [_headline(reply, payload)]
    if transcript:
        lines.insert(0, "🎙️ 听到你说：" + transcript[:200])
    period = payload.get("range") or {}
    if period.get("start") or period.get("end"):
        lines.append(f"📅 {period.get('start') or '不限'} 至 {period.get('end') or '不限'}")
    rows = payload.get("transactions") or payload.get("candidates") or payload.get("deleted") or []
    for row in rows[:8]:
        label = row.get("merchant") or row.get("note") or row.get("category") or "流水"
        icon = KIND_EMOJIS.get(row.get("kind"), CATEGORY_EMOJIS.get(row.get("category"), "🧾"))
        lines.append(f"{icon} {KINDS.get(row.get('kind'), '流水')} ¥{float(row['amount']):.2f} · {str(label)[:60]}")
        details = [str(value) for value in [row.get("category"), row.get("paymentMethod"), row.get("date")] if value]
        if row.get("kind") == "expense" and row.get("personalAmount") is not None and row["personalAmount"] != row["amount"]:
            details.append(f"个人承担¥{float(row['personalAmount']):.2f}")
        if row.get("outstandingAmount", 0) > 0:
            details.append(f"{'待归还' if row.get('kind') == 'borrow' else '待收回'}¥{float(row['outstandingAmount']):.2f}")
        details.append(f"#{row['id']}")
        lines.append("   " + " · ".join(details))
    if len(rows) > 8 or payload.get("truncated"):
        lines.append("📚 还有更多明细，去网页账单页慢慢翻吧～")
    if kind == "duplicate":
        lines.append("确实是另一笔的话，10分钟内回复「确认重复记账」就好；确认前不会新增哦。")
    for choice in (payload.get("choices") or [])[:6]:
        lines.append(f"💬 可以回复：{choice['text']}")
    for budget in (payload.get("budgets") or [])[:6]:
        lines.append(f"🎯 {budget.get('label', '预算')}：预算¥{float(budget['amount']):.2f}，"
                     f"剩余¥{float(budget['remaining']):.2f}")
    if payload.get("preference"):
        preference = payload["preference"]
        lines.append(f"💳 默认付款方式：{preference.get('payment_method') or '未设置'}")
        for name, category in list((preference.get("rules") or {}).items())[:5]:
            lines.append(f"{name} → {category}")
    if kind in {"update", "delete"} and payload.get("found") is False:
        lines.append("请补充商户、金额、日期，或在网页选择账单。")
    if kind in {"record", "update", "delete", "undo"}:
        lines.append("💡 想恢复的话，告诉我「撤销上一步」就好。")
    footer = f"\n📖 打开小账本：{settings.public_url}" if settings.public_url else ""
    # 为链接保留位置；按 UTF-8 字节截断，避免中文使消息超过通道限制。
    text = "\n".join(lines)
    budget = max(1000, 3800 - len(footer.encode()))
    if len(text.encode()) > budget:
        text = text.encode()[:budget - 60].decode("utf-8", errors="ignore") + "\n更多明细请到网页查看。"
    return text + footer
