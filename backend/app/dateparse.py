"""相对日期解析：用户说的"上个月""昨晚""上周五"由服务端确定性换算。

模型在小票上看得懂绝对日期，但对中文相对时间的换算会漂移，
所以把这段逻辑放在代码里，prompt 里只要求模型原样回填用户说法。
"""

from __future__ import annotations

import datetime as dt
import re

DAY = dt.timedelta(days=1)

CN_NUM = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
          "十一": 11, "十二": 12}


def _weekday_index(word: str | None) -> int | None:
    """返回 0=周一 ... 6=周日。"""
    if not word:
        return None
    table = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6,
             "1": 0, "2": 1, "3": 2, "4": 3, "5": 4, "6": 5, "7": 6}
    return table.get(word)


def resolve_relative(text: str, today: dt.date) -> dt.date | None:
    """把一段自然语言里的相对日期表达解析成具体某天。解析不出返回 None。"""
    if not text:
        return None

    explicit = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", text)
    if explicit:
        try:
            return dt.date(int(explicit.group(1)), int(explicit.group(2)), int(explicit.group(3)))
        except ValueError:
            pass

    short = re.search(r"(?<!\d)(\d{1,2})月(\d{1,2})[日号]", text)
    if short:
        try:
            return dt.date(today.year, int(short.group(1)), int(short.group(2)))
        except ValueError:
            pass

    if "大前天" in text:
        return today - 3 * DAY
    if "前天" in text:
        return today - 2 * DAY
    if "昨天" in text or "昨晚" in text:
        return today - DAY
    if "今天" in text or "今早" in text or "今晚" in text or "刚才" in text or "刚刚" in text:
        return today
    if "明天" in text:
        return today + DAY

    n_days = re.search(r"([0-9一二两三四五六七八九十]+)\s*天前", text)
    if n_days:
        raw = n_days.group(1)
        num = int(raw) if raw.isdigit() else CN_NUM.get(raw)
        if num:
            return today - num * DAY

    n_weeks = re.search(r"([0-9一二两三四五六七八九十]+)\s*(?:个)?(?:星期|周)前", text)
    if n_weeks:
        raw = n_weeks.group(1)
        num = int(raw) if raw.isdigit() else CN_NUM.get(raw)
        if num:
            return today - num * 7 * DAY

    last_weekday = re.search(r"上(?:个)?(?:星期|周)([一二三四五六日天1-7])", text)
    if last_weekday:
        target = _weekday_index(last_weekday.group(1))
        if target is not None:
            delta = (today.weekday() - target) % 7 or 7
            return today - delta * DAY

    this_weekday = re.search(r"(?:这|本)(?:个)?(?:星期|周)([一二三四五六日天1-7])", text)
    if this_weekday:
        target = _weekday_index(this_weekday.group(1))
        if target is not None:
            return today - ((today.weekday() - target) % 7) * DAY

    if "上上个月" in text:
        first = today.replace(day=1)
        prev = (first - DAY).replace(day=1)
        return (prev - DAY).replace(day=1)
    if "上个月" in text or "上月" in text:
        return (today.replace(day=1) - DAY).replace(day=1)
    if "这个月" in text or "本月" in text:
        return today.replace(day=1)

    if "去年" in text:
        return today.replace(year=today.year - 1)

    return None


def _single_day(text: str, today: dt.date) -> dt.date | None:
    """区间解析的第一步：识别"昨天""上周五""上个月3号"这类只指向某一天的说法。

    只认明确到"日"的表达；"上个月""今年"这类留给后面的区间逻辑，避免误判成整月第 1 天。
    """
    # 上个月3号 / 这个月15日 —— 先落到月初，再换成指定日
    month_day = re.search(r"(上上个月|上个?月|这个月|本月)\s*(\d{1,2})\s*[日号]", text)
    if month_day:
        month_start = resolve_relative(month_day.group(1), today)
        if month_start:
            try:
                return month_start.replace(day=int(month_day.group(2)))
            except ValueError:
                return None

    # 上周五 / 这周三：只有跟着数字或汉字星期的才算单日，"上个星期"仍走整周区间
    weekday = re.search(r"(上|这|本)(?:个)?(?:星期|周)([一二三四五六日天1-7])", text)
    if weekday:
        target = _weekday_index(weekday.group(2))
        if target is not None:
            offset = (today.weekday() - target) % 7
            if weekday.group(1) == "上":
                # 落在本周内就再退一周，保证"上周X"一定在过去
                return today - (offset + 7) * DAY
            return today - offset * DAY

    for word, delta in (("大前天", 3), ("前天", 2), ("昨天", 1), ("昨日", 1), ("昨晚", 1),
                        ("今天", 0), ("今日", 0), ("今晚", 0), ("刚才", 0), ("刚刚", 0)):
        if word in text:
            return today - delta * DAY

    n_days = re.search(r"([0-9一二两三四五六七八九十]+)\s*天前", text)
    if n_days:
        raw = n_days.group(1)
        num = int(raw) if raw.isdigit() else CN_NUM.get(raw)
        if num:
            return today - num * DAY

    explicit = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})[日号]?", text)
    if explicit:
        try:
            return dt.date(int(explicit.group(1)), int(explicit.group(2)), int(explicit.group(3)))
        except ValueError:
            pass

    month_only = re.search(r"(?<!\d)(\d{1,2})月(\d{1,2})[日号]", text)
    if month_only:
        try:
            return dt.date(today.year, int(month_only.group(1)), int(month_only.group(2)))
        except ValueError:
            pass

    return None


def resolve_range(text: str, today: dt.date) -> tuple[dt.date | None, dt.date | None]:
    """把"上个月""今年""昨天""最近一周"等区间表达解析成 [start, end]，用于查询和报告。"""
    if not text:
        return None, None

    # 显式区间优先级最高：2026-10-01 到 10-07 之间不要被别的词抢走
    m = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})[日号]?\s*(?:到|至|-|~)\s*(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", text)
    if m:
        try:
            return (
                dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))),
                dt.date(int(m.group(4)), int(m.group(5)), int(m.group(6))),
            )
        except ValueError:
            pass

    # 跨年省略年份的写法：10月1日到10月7日
    m = re.search(r"(?<!\d)(\d{1,2})月(\d{1,2})[日号]?\s*(?:到|至|-|~)\s*(\d{1,2})月(\d{1,2})[日号]?", text)
    if m:
        try:
            return (
                dt.date(today.year, int(m.group(1)), int(m.group(2))),
                dt.date(today.year, int(m.group(3)), int(m.group(4))),
            )
        except ValueError:
            pass

    # 滚动窗口："最近7天""过去两个星期""近三个月"
    rolling = re.search(r"(?:最近|近|过去)\s*([0-9一二两三四五六七八九十]+)\s*(天|日|周|星期|个月|月)", text)
    if rolling:
        raw = rolling.group(1)
        num = int(raw) if raw.isdigit() else CN_NUM.get(raw)
        if num:
            unit = rolling.group(2)
            if unit in ("周", "星期"):
                num *= 7
            elif unit in ("个月", "月"):
                start = today.replace(day=1)
                for _ in range(num):
                    start = (start - DAY).replace(day=1)
                return start, today
            return today - (num - 1) * DAY, today

    # 单日说法（昨天 / 上周五 / 上个月3号）必须早于整周、整月区间判断
    day = _single_day(text, today)
    if day:
        return day, day

    if "这个月" in text or "本月" in text:
        start = today.replace(day=1)
        nxt = (start + dt.timedelta(days=32)).replace(day=1)
        return start, min(today, nxt - DAY)
    if "上个月" in text or "上月" in text:
        start = (today.replace(day=1) - DAY).replace(day=1)
        return start, today.replace(day=1) - DAY

    monday = today - dt.timedelta(days=today.weekday())
    if "上周" in text or "上上个星期" in text or "上个星期" in text or "上星期" in text:
        return monday - 7 * DAY, monday - DAY
    if "本周" in text or "这周" in text or "这个星期" in text or "本星期" in text:
        return monday, today

    if "今年" in text:
        return today.replace(month=1, day=1), today
    if "去年" in text:
        start = today.replace(year=today.year - 1, month=1, day=1)
        return start, start.replace(month=12, day=31)
    if "最近一周" in text or "近一周" in text:
        return today - 6 * DAY, today
    if "最近一个月" in text or "近一个月" in text or "最近30天" in text:
        return today - 29 * DAY, today

    return None, None
