"""把已执行的账本结果转换成微信文字，不让模型重新计算金额。"""
from __future__ import annotations

from app.config import settings
from app.finance import KINDS


def format_reply(reply: str, payload: dict) -> str:
    kind = payload.get("kind")
    lines = [reply]
    period = payload.get("range") or {}
    if period.get("start") or period.get("end"):
        lines.append(f"范围：{period.get('start') or '不限'} 至 {period.get('end') or '不限'}")
    rows = payload.get("transactions") or payload.get("candidates") or payload.get("deleted") or []
    for row in rows[:8]:
        label = row.get("merchant") or row.get("note") or row.get("category") or "流水"
        payment = f" · {row['paymentMethod']}" if row.get("paymentMethod") else ""
        lines.append(f"#{row['id']} {row.get('date', '')} {KINDS.get(row.get('kind'), '流水')} "
                     f"¥{float(row['amount']):.2f} · {str(label)[:60]}{payment}")
    if len(rows) > 8 or payload.get("truncated"):
        lines.append("更多明细可在网页账单页查看。")
    if kind == "duplicate":
        lines.append("如确认是另一笔，请在10分钟内回复「确认重复记账」；不确认不会新增。")
    for choice in (payload.get("choices") or [])[:6]:
        lines.append(f"回复：{choice['text']}")
    for budget in (payload.get("budgets") or [])[:6]:
        lines.append(f"{budget.get('label', '预算')}：预算¥{float(budget['amount']):.2f}，"
                     f"剩余¥{float(budget['remaining']):.2f}")
    if payload.get("preference"):
        preference = payload["preference"]
        lines.append(f"默认付款方式：{preference.get('payment_method') or '未设置'}")
        for name, category in list((preference.get("rules") or {}).items())[:5]:
            lines.append(f"{name} → {category}")
    if kind in {"update", "delete"} and payload.get("found") is False:
        lines.append("请补充商户、金额、日期，或在网页选择账单。")
    if kind == "export":
        lines[0] = "账单已筛选，请登录网页，在对话中的导出卡片下载CSV。"
    if kind in {"record", "update", "delete", "undo"}:
        lines.append("需要恢复可发送「撤销上一步」。")
    footer = f"\n账本：{settings.public_url}" if settings.public_url else ""
    # 为链接保留位置；按 UTF-8 字节截断，避免中文使消息超过通道限制。
    text = "\n".join(lines)
    budget = max(1000, 3800 - len(footer.encode()))
    if len(text.encode()) > budget:
        text = text.encode()[:budget - 60].decode("utf-8", errors="ignore") + "\n更多明细请到网页查看。"
    return text + footer
