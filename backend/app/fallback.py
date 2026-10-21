"""无 AI 兜底解析：从一句话里抠出金额和分类。

只在模型执意追问、而输入里其实已经写明金额时使用，避免记账被无谓打断。
规则保守——宁可不记，也不乱记。
"""

from __future__ import annotations

import datetime as dt
import re

CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}

CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("餐饮", ("吃", "饭", "餐", "外卖", "咖啡", "奶茶", "面", "汤", "火锅", "烧烤", "零食", "早点", "早餐", "午餐", "晚餐", "食堂", "星巴克", "麦当劳", "肯德基", "瑞幸", "蛋糕", "水果")),
    ("交通", ("打车", "滴滴", "出租车", "地铁", "公交", "高铁", "火车", "机票", "飞机", "加油", "油费", "停车", "过路费", "共享单车", "摩的")),
    ("购物", ("超市", "买", "购物", "日用", "纸巾", "洗衣液", "牛奶", "面包", "母婴", "宠物", "家居", "便利店")),
    ("服饰", ("衣服", "鞋", "裤子", "外套", "裙子", "包包", "背包", "帽子", "袜子", "内衣", "美妆", "化妆", "护肤", "口红", "优衣库", "Nike", "nike", "阿迪", "李宁")),
    ("居住", ("房租", "物业", "水费", "电费", "燃气", "宽带", "房租费", "中介费")),
    ("娱乐", ("电影", "游戏", "KTV", "演唱会", "会员", "订阅", "网飞", "剧本杀", "桌游", "门票")),
    ("医疗", ("看病", "医院", "药", "体检", "牙医", "挂号", "诊所")),
    ("教育", ("学费", "书", "课程", "培训", "考试", "补习")),
    ("数码", ("手机", "电脑", "耳机", "充电器", "键盘", "鼠标", "iPad", "iphone", "iPhone", "数码", "显示器")),
    ("旅行", ("旅行", "酒店", "民宿", "旅游", "签证", "景点", "机票", "度假")),
    ("人情", ("红包", "礼金", "礼物", "随礼", "送礼", "探望")),
]

# 金额：带单位、带货币符号、或"花了 N" 的说法
AMOUNT_PATTERN = re.compile(
    r"(?:¥|￥|RMB|rmb)?\s*(\d+(?:\.\d{1,2})?)\s*(?:元|块钱|块|圆|rmb|RMB)"
    r"|(?:¥|￥)\s*(\d+(?:\.\d{1,2})?)"
    r"|花了\s*(\d+(?:\.\d{1,2})?)"
)

# 裸数字：中文口语经常只说"外套899"，不带到"元"。前面紧跟这些字说明不是金额。
BARE_NUMBER = re.compile(r"(?<![\d./-])(\d+(?:\.\d{1,2})?)(?![\d./-])")
NON_AMOUNT_PREFIX = ("月", "日", "号", "年", "时", "点", ":")
NON_AMOUNT_SUFFIX = ("月", "日", "号", "点", "次", "个", "斤", "克", "件", "张", "%", "楼", "层", "岁", "公里", "km", "折", "人")
TRIGGER_WORDS = ("买", "花", "付", "充", "消费", "吃", "打车", "订", "交了", "一共", "总共", "块")


def _guess_category(text: str, fallback: str = "其他") -> str:
    for name, words in CATEGORY_KEYWORDS:
        if any(word in text for word in words):
            return name
    return fallback


def _clean_note(text: str) -> str:
    cleaned = re.sub(r"[，,。！!？?、\s]+", " ", text).strip()
    return cleaned[:60]


def fallback_transactions(text: str, today: dt.date) -> list[dict[str, object]]:
    """从自由文本里抽金额。抽不到、或金额旁边像数量单位时返回空列表。"""
    if not text:
        return []

    found: list[tuple[int, int, float]] = []

    def collect(start: int, end: int, raw: str | None) -> None:
        if not raw:
            return
        before = text[max(0, start - 2) : start]
        after = text[end : end + 2]
        if any(before.endswith(p) for p in NON_AMOUNT_PREFIX):
            return
        if any(after.startswith(s) for s in NON_AMOUNT_SUFFIX):
            return
        try:
            value = float(raw)
        except ValueError:
            return
        if value <= 0 or value > 100000:
            return
        if all(abs(value - v) > 1e-9 for _, _, v in found):
            found.append((start, end, value))

    for match in AMOUNT_PATTERN.finditer(text):
        collect(match.start(), match.end(), match.group(1) or match.group(2) or match.group(3))

    # 没有带单位的金额时，才用裸数字兜底；并要求句子里有消费动词，避免把件数当钱。
    if not found and any(word in text for word in TRIGGER_WORDS):
        for match in BARE_NUMBER.finditer(text):
            collect(match.start(), match.end(), match.group(1))

    if not found:
        return []

    found.sort()
    values = [value for _, _, value in found]
    # 每个金额单独归类：取它前面最近的半句话，这样"买外套899，吃拉面120"不会都归餐饮。
    segments = [text[max(0, start - 18) : end] for start, end, _ in found]

    # 出现"一共/合计"时，最大金额通常是总价，避免明细和总额重复记账。
    if any(word in text for word in ("一共", "总计", "合计", "总共", "加一起")):
        values = [max(values)]
        segments = [text]

    note = _clean_note(text)
    from app.dateparse import resolve_relative

    occurred = resolve_relative(text, today) or today
    hour = 12
    if "晚" in text or "夜" in text:
        hour = 19
    elif "早" in text:
        hour = 8

    overall = _guess_category(text)
    return [
        {
            "amount": amount,
            "category": _guess_category(segment, fallback=overall),
            "merchant": "",
            "note": note,
            "items": [],
            "occurred_at": dt.datetime.combine(occurred, dt.time(hour, 0)).strftime("%Y-%m-%d %H:%M:%S"),
            "event": "",
        }
        for amount, segment in zip(values, segments)
    ]
