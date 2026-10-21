"""付款方式：记录钱从哪个渠道出去的。"""

from __future__ import annotations

PAYMENT_METHODS: list[dict[str, str]] = [
    {"name": "支付宝", "color": "#1677FF", "desc": "支付宝、花呗、余额宝"},
    {"name": "微信", "color": "#07C160", "desc": "微信支付、零钱、微信零钱通"},
    {"name": "银行卡", "color": "#FA8C16", "desc": "储蓄卡、借记卡、网银转账"},
    {"name": "信用卡", "color": "#722ED1", "desc": "各类信用卡、花呗分期"},
    {"name": "现金", "color": "#8C8C8C", "desc": "纸币、零钱"},
    {"name": "其他", "color": "#595959", "desc": "礼品卡、积分、代付等"},
]

PAYMENT_NAMES: list[str] = [m["name"] for m in PAYMENT_METHODS]
PAYMENT_BY_NAME: dict[str, dict[str, str]] = {m["name"]: m for m in PAYMENT_METHODS}


def normalize_payment(value: str | None) -> str:
    """把口语说法收敛到固定枚举；认不出来返回空字符串（表示未记录）。"""
    text = (value or "").strip()
    if not text:
        return ""
    if text in PAYMENT_BY_NAME:
        return text
    aliases = {
        "支付宝钱包": "支付宝", "花呗": "支付宝", "余额宝": "支付宝", "阿里": "支付宝", "alipay": "支付宝",
        "微信支付": "微信", "微信零钱": "微信", "零钱": "微信", "wechat": "微信", "weixin": "微信", "微": "微信",
        "银行卡": "银行卡", "储蓄卡": "银行卡", "借记卡": "银行卡", "银联": "银行卡", "网银": "银行卡", "转账": "银行卡", "银行": "银行卡",
        "信用卡": "信用卡", "credit": "信用卡", "贷记卡": "信用卡", "分期": "信用卡",
        "现金": "现金", "现钞": "现金", "cash": "现金", "纸币": "现金",
        "云闪付": "银行卡", "applepay": "银行卡", "Apple Pay": "银行卡",
    }
    for key, name in aliases.items():
        if key.lower() in text.lower():
            return name
    return ""


def payment_color(name: str) -> str:
    return PAYMENT_BY_NAME.get(name, {}).get("color", "#8C8C8C")
