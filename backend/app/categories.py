"""消费分类体系：颜色和图标同时提供给前端，保证图表与卡片一致。"""

from __future__ import annotations

CATEGORIES: list[dict[str, str]] = [
    {"name": "餐饮", "icon": "coffee", "color": "#FF7A45", "desc": "三餐、外卖、咖啡、奶茶、零食"},
    {"name": "交通", "icon": "car", "color": "#36A3F7", "desc": "打车、公交、地铁、加油、停车、高铁机票"},
    {"name": "购物", "icon": "bag", "color": "#F759AB", "desc": "日用品、超市、家居、母婴、宠物"},
    {"name": "服饰", "icon": "shirt", "color": "#9254DE", "desc": "衣服、鞋子、包包、配饰、美妆护肤"},
    {"name": "居住", "icon": "home", "color": "#13C2C2", "desc": "房租、物业、水电燃气、宽带"},
    {"name": "娱乐", "icon": "game", "color": "#EB2F96", "desc": "电影、游戏、演出、会员订阅、KTV"},
    {"name": "医疗", "icon": "heart", "color": "#F5222D", "desc": "看病、买药、体检、牙科"},
    {"name": "教育", "icon": "book", "color": "#2F54EB", "desc": "学费、书籍、课程、培训"},
    {"name": "数码", "icon": "device", "color": "#595959", "desc": "手机、电脑、配件、软件"},
    {"name": "旅行", "icon": "plane", "color": "#52C41A", "desc": "酒店、门票、旅游团、签证"},
    {"name": "人情", "icon": "gift", "color": "#FAAD14", "desc": "红包、礼物、请客、随礼"},
    {"name": "其他", "icon": "dots", "color": "#8C8C8C", "desc": "以上都不属于的支出"},
]

CATEGORY_NAMES: list[str] = [c["name"] for c in CATEGORIES]
CATEGORY_BY_NAME: dict[str, dict[str, str]] = {c["name"]: c for c in CATEGORIES}


def normalize_category(value: str | None) -> str:
    text = (value or "").strip()
    if text in CATEGORY_BY_NAME:
        return text
    aliases = {
        "吃饭": "餐饮", "美食": "餐饮", "外卖": "餐饮", "饮料": "餐饮", "咖啡": "餐饮", "聚餐": "餐饮",
        "出行": "交通", "打车": "交通", "地铁": "交通", "机票": "交通", "交通出行": "交通",
        "买东西": "购物", "超市": "购物", "日用": "购物", "生活用品": "购物",
        "服装": "服饰", "鞋子": "服饰", "鞋": "服饰", "衣服": "服饰", "美妆": "服饰", "化妆": "服饰",
        "住房": "居住", "房租": "居住", "水电": "居住", "物业": "居住",
        "游戏": "娱乐", "旅游": "旅行", "酒店": "旅行",
        "健康": "医疗", "医药": "医疗", "学习": "教育", "培训": "教育",
        "电子": "数码", "3C": "数码", "礼品": "人情", "红包": "人情",
    }
    return aliases.get(text, "其他")
