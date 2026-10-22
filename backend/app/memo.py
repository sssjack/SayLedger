"""备忘录/提醒：中文自然语言的确定性解析、待确认草稿与提醒文案。

模型对相对日期的换算会漂移，所以日期、时刻、重复规则都由这里算；
模型只负责在图片等场景给出结构化 memo 意图，服务端再校验执行。
草稿缺时刻或缺事件时先存 MemoPending，用户下一句补齐后才真正创建。
"""
from __future__ import annotations

import datetime as dt
import json
import re
import uuid
from typing import Any

from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.db import Memo, MemoPending, utcnow

PENDING_TTL = dt.timedelta(minutes=30)
WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
_WEEKDAY_CHARS = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6,
                  "1": 0, "2": 1, "3": 2, "4": 3, "5": 4, "6": 5, "7": 6}
_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_NUM = r"(?:\d+|[零一二两三四五六七八九十]+)"


def cn_int(raw: str | None) -> int | None:
    """把 '三' '十二' '二十三' 这类中文数字或阿拉伯数字转成 int。"""
    if raw is None:
        return None
    raw = raw.strip()
    if raw.isdigit():
        return int(raw) if len(raw) <= 6 else None
    if raw == "十":
        return 10
    if "十" in raw:
        left, _, right = raw.partition("十")
        tens = _CN_DIGITS.get(left, 1) if left else 1
        ones = _CN_DIGITS.get(right, 0) if right else 0
        if left and left not in _CN_DIGITS:
            return None
        if right and right not in _CN_DIGITS:
            return None
        return tens * 10 + ones
    return _CN_DIGITS.get(raw)


# ---------------------------------------------------------------- 时刻解析

_CLOCK_RE = re.compile(
    r"(凌晨|早晨|早上|上午|中午|下午|傍晚|晚上|夜里)?\s*"
    r"(\d{1,2}|[零一二两三四五六七八九十]+)\s*(?:[:：]\s*(\d{1,2})|点(?:\s*(半)|(?:\s*(\d{1,2}|[零一二两三四五六七八九十]+)\s*分?))?)"
)


def parse_clock(text: str) -> tuple[dt.time | None, str]:
    """从一句话里找出时刻，返回 (time, 命中的原文)。找不到返回 (None, '')。"""
    match = _CLOCK_RE.search(text or "")
    if not match:
        return None, ""
    period, hour_raw, colon_min, half, min_raw = match.groups()
    hour = cn_int(hour_raw)
    if hour is None or hour > 23:
        return None, ""
    minute = 0
    if colon_min is not None:
        minute = int(colon_min)
    elif half:
        minute = 30
    elif min_raw is not None:
        minute = cn_int(min_raw) or 0
    if minute > 59:
        return None, ""
    if period in ("下午", "傍晚", "晚上", "夜里"):
        if hour < 12:
            hour += 12
    elif period == "中午":
        if hour <= 11:
            hour += 12
    elif period in ("凌晨", "早晨", "早上", "上午"):
        if hour == 12:
            hour = 0
    return dt.time(hour, minute), match.group(0)


# ---------------------------------------------------------------- 日期解析

def _next_weekday(today: dt.date, weekday: int, *, week_offset: int) -> dt.date:
    """week_offset=0 本周、1 下周；返回对应星期的日期（本周已过去则仍返回本周那天）。"""
    monday = today - dt.timedelta(days=today.weekday())
    return monday + dt.timedelta(days=week_offset * 7 + weekday)


def parse_date(text: str, today: dt.date) -> tuple[dt.date | None, str, str]:
    """找日期表达，返回 (date, 命中的原文, 口语描述如 '下周三')。"""
    match = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})[日号]?", text)
    if match:
        try:
            value = dt.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            return value, match.group(0), f"{value.month}月{value.day}日"
        except ValueError:
            pass
    match = re.search(rf"({_NUM})月({_NUM})[日号]", text)
    if match:
        month, day = cn_int(match.group(1)), cn_int(match.group(2))
        if month and day:
            try:
                value = dt.date(today.year, month, day)
                if value < today:
                    value = value.replace(year=today.year + 1)
                return value, match.group(0), f"{month}月{day}日"
            except ValueError:
                pass
    for word, delta in (("大后天", 3), ("后天", 2), ("明天", 1), ("明早", 1), ("明晚", 1),
                        ("今天", 0), ("今晚", 0), ("今早", 0)):
        if word in text:
            return today + dt.timedelta(days=delta), word, word
    match = re.search(r"(下下周|下周|下个星期|下星期|这周|本周|这个星期|本星期|这星期)([一二三四五六日天1-7])", text)
    if match:
        weekday = _WEEKDAY_CHARS.get(match.group(2))
        if weekday is not None:
            offset = 2 if match.group(1) == "下下周" else 1 if match.group(1).startswith("下") else 0
            value = _next_weekday(today, weekday, week_offset=offset)
            if offset == 0 and value < today:
                value += dt.timedelta(days=7)
            desc = ("下周" if offset == 1 else "下下周" if offset == 2 else "这周") + WEEKDAY_NAMES[weekday][1]
            return value, match.group(0), desc
    match = re.search(r"(?:星期|周)([一二三四五六日天1-7])", text)
    if match:
        weekday = _WEEKDAY_CHARS.get(match.group(1))
        if weekday is not None:
            value = today + dt.timedelta(days=(weekday - today.weekday()) % 7)
            return value, match.group(0), WEEKDAY_NAMES[weekday]
    return None, "", ""


# ---------------------------------------------------------------- 主解析

_MEMO_HINT = re.compile(r"提醒|备忘|闹钟")
_CANCEL_WORDS = {"取消", "算了", "不用了", "不要了", "取消备忘", "取消提醒", "先不记了", "不记了"}


def is_status_question(text: str) -> bool:
    compact = re.sub(r"\s+", "", text or "")
    if not re.search(r"提醒|备忘|闹钟|循环|重复", compact):
        return False
    return bool(re.search(r"(?:现在|目前|当前|已经|设置的|我的|刚才的).*(?:吗|么|是不是|是否|哪些|什么|几|循环|重复)", compact)
                or re.search(r"(?:是不是|是否|有没有|有哪些|查询|查看|看看|列出|什么|多久|下一次).*提醒", compact)
                or re.search(r"提醒.*(?:是什么|有哪些|什么时候|几点|是否|吗|么|？|\?)", compact)) and not bool(re.search(r"改成|改为|修改|帮我改|能不能|可不可以|提醒我|帮我.*提醒", compact))


def allows_auto_time(text: str) -> bool:
    return bool(re.search(r"你看着办|你来定|你定|你决定|自行安排|自己安排|你来安排|你安排|看着安排|帮我选|合适的时间|时间随便|时间你定|就按你说的", text or ""))


def parse_repeat(text: str) -> dict | None:
    # 后面的“改成”可能是在改时间，不能截掉前面已经表达的循环要求。
    candidates = []
    for match in re.finditer(r"不再循环|不要循环|不重复|取消循环|取消重复|只提醒一次", text):
        candidates.append((match.start(), {"recurrence": "none", "interval_days": 0}))
    for match in re.finditer(rf"(?:每隔?|隔)\s*({_NUM})\s*天|({_NUM})\s*天\s*(?:一(?:个|轮|次)?|为(?:一个)?)?\s*(?:循环|周期|重复)", text):
        days = cn_int(match[1] or match[2])
        candidates.append((match.start(), {"recurrence": "interval", "interval_days": days}))
    for pattern, recurrence, days in ((r"每天|每日", "daily", 1), (r"每周|每星期", "weekly", 7)):
        candidates.extend((match.start(), {"recurrence": recurrence, "interval_days": days}) for match in re.finditer(pattern, text))
    if not candidates:
        return None
    repeat = max(candidates, key=lambda candidate: candidate[0])[1]
    repetition(repeat)
    return repeat


def repetition(raw: dict) -> tuple[str, int]:
    recurrence = str(raw.get("recurrence") or "none")
    days = raw.get("interval_days", 0) or 0
    if recurrence not in {"none", "daily", "weekly", "interval"}:
        raise HTTPException(400, "暂不支持这种循环方式，请说明是否每隔几天重复。")
    if recurrence == "interval":
        if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 365:
            raise HTTPException(400, "循环间隔需要是1到365之间的整数天。")
    else:
        expected = {"none": 0, "daily": 1, "weekly": 7}[recurrence]
        if days not in (0, expected):
            raise HTTPException(400, "自定义天数需要选择每隔几天循环。")
        days = expected
    return recurrence, days


def _clean_content(text: str) -> str:
    cleaned = text
    for pattern in (
        rf"(?:每隔?|隔)\s*{_NUM}\s*天",
        r"每周[一二三四五六日天1-7]?", r"每个?星期[一二三四五六日天1-7]?", r"每天|每日",
        r"下下周[一二三四五六日天1-7]|下周[一二三四五六日天1-7]|下个?星期[一二三四五六日天1-7]",
        r"这周[一二三四五六日天1-7]|本周[一二三四五六日天1-7]|这个?星期[一二三四五六日天1-7]",
        r"(?:星期|周)[一二三四五六日天1-7]",
        r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日号]?", rf"{_NUM}月{_NUM}[日号]",
        r"大后天|后天|明天|明早|明晚|今天|今晚|今早",
        rf"{_NUM}(?:分钟|小时|天)后|半小时后|半天后",
        r"提醒我|提醒|备忘录?|记一下|记着|闹钟|请|麻烦|帮我|记得|到时候|一下",
    ):
        cleaned = re.sub(pattern, "", cleaned)
    # 时刻表达最后清，避免“点”把日期数字误伤
    cleaned = _CLOCK_RE.sub("", cleaned)
    cleaned = re.sub(r"[\s，。！？!?、；;：:]+", "", cleaned)
    cleaned = cleaned.strip("的了呀呢吧")
    if cleaned.startswith("要"):
        cleaned = cleaned[1:]
    return cleaned[:200]


def _draft_missing(draft: dict[str, Any]) -> list[str]:
    missing = []
    if not draft.get("content"):
        missing.append("content")
    if draft.get("trigger_at"):
        return missing
    if not draft.get("time"):
        missing.append("time")
    if draft.get("recurrence") == "weekly" and draft.get("weekday") is None:
        missing.append("weekday")
    if draft.get("recurrence") == "none" and not draft.get("date") and not draft.get("time_only"):
        missing.append("date")
    return missing


def build_trigger(draft: dict[str, Any], now: dt.datetime) -> dt.datetime | None:
    """草稿信息齐了之后算出下一次触发时间；信息不齐返回 None。"""
    if draft.get("trigger_at"):
        candidate = dt.datetime.fromisoformat(draft["trigger_at"])
        return next_after(candidate, draft["recurrence"], now, draft.get("interval_days", 0)) if candidate <= now and draft.get("recurrence") in {"daily", "weekly", "interval"} else candidate
    if _draft_missing(draft):
        return None
    hour, minute = (int(part) for part in draft["time"].split(":"))
    clock = dt.time(hour, minute)
    recurrence = draft.get("recurrence") or "none"
    if recurrence == "daily":
        candidate = dt.datetime.combine(now.date(), clock)
        if candidate <= now:
            candidate += dt.timedelta(days=1)
        return candidate
    if recurrence == "weekly":
        base = now.date() + dt.timedelta(days=(int(draft["weekday"]) - now.date().weekday()) % 7)
        candidate = dt.datetime.combine(base, clock)
        if candidate <= now:
            candidate += dt.timedelta(days=7)
        return candidate
    if draft.get("date"):
        candidate = dt.datetime.combine(dt.date.fromisoformat(draft["date"]), clock)
        if recurrence == "interval" and candidate <= now:
            candidate = next_after(candidate, recurrence, now, draft.get("interval_days", 0))
        return candidate
    if draft.get("time_only") or recurrence == "interval":
        candidate = dt.datetime.combine(now.date(), clock)
        if candidate <= now:
            candidate += dt.timedelta(days=repetition(draft)[1] or 1)
        return candidate
    return None


def parse_memo_request(text: str, now: dt.datetime) -> dict[str, Any] | None:
    """解析一句备忘请求；不是备忘意图返回 None，否则返回草稿 dict（含 missing）。"""
    text = (text or "").strip()
    if (not text or not _MEMO_HINT.search(text) or is_status_question(text)
            or re.search(r"看着办|你定|你安排|自行安排|修改|改成|改为|取消|循环|是不是|是否|[吗么？?]|工作日|周末|每月|每个月|小时一次|分钟一次|持续|直到|截止|除了|分别|每天.*[次遍]", text)):
        return None
    today = now.date()
    draft: dict[str, Any] = {"content": "", "trigger_at": None, "date": None, "time": None,
                             "recurrence": "none", "weekday": None, "date_desc": "", "time_only": False,
                             "raw_input": text}

    # 相对偏移：“半小时后”“20分钟后”“2小时后”直接给出完整触发时间
    offset = re.search(rf"({_NUM}|半)\s*(分钟|小时|天)后", text)
    if offset and "提醒" in text:
        raw_num, unit = offset.group(1), offset.group(2)
        num = 0.5 if raw_num == "半" else cn_int(raw_num)
        if num:
            delta = {"分钟": dt.timedelta(minutes=num), "小时": dt.timedelta(hours=num),
                     "天": dt.timedelta(days=num)}[unit]
            trigger = now + delta
            draft.update(trigger_at=trigger.isoformat(timespec="minutes"),
                         date=trigger.date().isoformat(), time=trigger.strftime("%H:%M"),
                         date_desc="稍后")
            draft["content"] = _clean_content(text)
            draft["missing"] = _draft_missing(draft)
            return draft

    weekly = re.search(r"每(?:个)?(?:星期|周)([一二三四五六日天1-7])", text)
    if weekly:
        weekday = _WEEKDAY_CHARS.get(weekly.group(1))
        if weekday is not None:
            draft.update(recurrence="weekly", weekday=weekday, date_desc="每" + WEEKDAY_NAMES[weekday])
    elif "每周" in text or "每星期" in text:
        draft.update(recurrence="weekly", date_desc="每周")
    if "每天" in text or "每日" in text:
        draft.update(recurrence="daily", date_desc="每天")
    interval = parse_repeat(text)
    if interval and interval["recurrence"] == "interval":
        draft.update(interval, date_desc=f"每{interval['interval_days']}天")

    if draft["recurrence"] == "none":
        date_value, _matched, desc = parse_date(text, today)
        if date_value:
            draft.update(date=date_value.isoformat(), date_desc=desc)

    clock, _matched_clock = parse_clock(text)
    if clock:
        draft["time"] = clock.strftime("%H:%M")
        if draft["recurrence"] == "none" and not draft["date"]:
            draft["time_only"] = True

    draft["content"] = _clean_content(text)
    draft["missing"] = _draft_missing(draft)
    return draft


def continue_pending(text: str, draft: dict[str, Any], now: dt.datetime) -> tuple[str, dict[str, Any]]:
    """用户在有草稿时说的下一句：返回 (create|ask|cancel|unrelated, 新草稿或说明)。"""
    compact = re.sub(r"[\s，。！？!?]", "", text or "")
    if is_status_question(text) or allows_auto_time(text) or re.search(r"循环|重复|修改|改成.*(?:每|循环)", text):
        return "unrelated", draft
    if compact in _CANCEL_WORDS or "取消" in compact and len(compact) <= 8:
        return "cancel", draft
    if (re.search(r"查账|账单|预算|撤销|花了|花多少|多少钱|支出|收入|昨天|上周|上个月", compact)
            or re.search(r"(?:午饭|晚饭|早餐|咖啡|打车|买了).*\d", compact)) and not _MEMO_HINT.search(text):
        return "unrelated", draft
    if isinstance(draft.get("batch"), list):
        entries = [dict(entry) for entry in draft["batch"]]
        incomplete = [index for index, entry in enumerate(entries) if entry.get("missing") or _draft_missing(entry)]
        if len(incomplete) != 1:
            return "unrelated", draft
        kind, updated = continue_pending(text, entries[incomplete[0]], now)
        if kind in {"create", "ask"}:
            entries[incomplete[0]] = updated
            return ("create" if kind == "create" else "ask"), {**draft, "batch": entries}
        return kind, draft
    merged = dict(draft)
    reparsed = parse_memo_request(text, now) if _MEMO_HINT.search(text or "") else None
    clock, _ = parse_clock(text)
    date_value, _, date_desc = parse_date(text, now.date())
    remainder = _clean_content(text)
    remainder = re.sub(r"改成|改到|改为|定在|定为|那就|就|好的|可以|左右|点钟|在", "", remainder)
    temporal_reply = bool(clock or date_value) and not remainder
    if not reparsed and merged.get("content") and (clock or date_value) and not temporal_reply:
        return "unrelated", draft
    if reparsed:
        for key in ("content", "trigger_at", "date", "time", "date_desc"):
            if reparsed.get(key):
                merged[key] = reparsed[key]
        if reparsed.get("recurrence") != "none":
            merged["recurrence"] = reparsed["recurrence"]
            merged["weekday"] = reparsed.get("weekday")
        if reparsed.get("time_only"):
            merged["time_only"] = True
    if clock:
        merged["trigger_at"] = None
        merged["time"] = clock.strftime("%H:%M")
        if merged.get("recurrence") == "none" and not merged.get("date"):
            merged["time_only"] = True
    if date_value and temporal_reply:
        merged.update(date=date_value.isoformat(), date_desc=date_desc, trigger_at=None)
    if not merged.get("content"):
        content = _clean_content(text)
        if content:
            merged["content"] = content
    if merged.get("time"):
        merged["missing"] = _draft_missing(merged)
    else:
        merged["missing"] = _draft_missing(merged)
    if not merged["missing"]:
        return "create", merged
    # 完全没吸收到新信息，多半是新话题（查账、撤销等），把决定权交回正常流程，
    # 草稿不清除，用户之后仍可继续补齐。
    if merged == draft:
        return "unrelated", draft
    return "ask", merged


# ---------------------------------------------------------------- 草稿与追问文案

def date_label(draft: dict[str, Any]) -> str:
    desc = draft.get("date_desc") or ""
    if draft.get("recurrence") in ("daily", "weekly"):
        return desc or ("每天" if draft["recurrence"] == "daily" else "每周")
    if draft.get("date"):
        value = dt.date.fromisoformat(draft["date"])
        base = f"{value.month}月{value.day}日"
        return f"{desc}（{base}）" if desc and desc not in base else base
    return desc or "那天"


def pending_reply(draft: dict[str, Any]) -> str:
    if isinstance(draft.get("batch"), list):
        incomplete = [entry for entry in draft["batch"] if entry.get("missing") or _draft_missing(entry)]
        if len(incomplete) == 1:
            return "这份计划还没有创建提醒。\n" + pending_reply(incomplete[0])
        return "这份计划有几处内容或时间还不清楚，还没有创建提醒。请补充对应的步骤和具体提醒时间。"
    missing = draft.get("missing") or _draft_missing(draft)
    if "stage_anchor" in missing:
        return "这份计划还没有创建提醒。今天是计划的第几天呢？"
    if "future_time" in missing:
        return f"「{draft.get('content') or '这件事'}」的时间已经过去，还没有创建提醒。要改到哪一天、几点呢？"
    if "time" in missing:
        return f"好嘞，先把这件事记在小本本上：{date_label(draft)}提醒你{draft.get('content') or '这件事'}。想让我在{date_label(draft)}几点喊你呢？"
    if "content" in missing:
        when = date_label(draft)
        time_text = f"{draft['time']} " if draft.get("time") else ""
        return f"没问题，{when}{time_text}的提醒时间我记牢啦。那要提醒你什么事呢？告诉我一声，我帮你写进小本本～"
    if "weekday" in missing:
        return "好嘞，那每周的哪一天提醒你呀？"
    if "date" in missing:
        return "好嘞，哪一天提醒你呢？可以说下周三、明天，或者具体的几月几号～"
    return "还差一点点信息，你再补充一下时间或事情吧～"


def created_reply(memo: Memo) -> str:
    when = format_trigger(memo.next_trigger_at)
    repeat = repeat_label(memo)
    suffix = f"，{repeat}" if repeat else ""
    return f"好嘞，备忘录建好啦📌 {when}提醒你：{memo.content}{suffix}。到点我会准时来喊你，放心吧～"


def format_trigger(value: dt.datetime) -> str:
    return f"{value.year}年{value.month}月{value.day}日（{WEEKDAY_NAMES[value.weekday()]}）{value:%H:%M}"


def repeat_label(memo: Memo) -> str:
    if memo.recurrence == "interval":
        return f"每{memo.interval_days}天循环"
    if memo.recurrence == "daily":
        return "每天重复"
    if memo.recurrence == "weekly":
        weekday = memo.weekday if memo.weekday is not None else memo.next_trigger_at.weekday()
        return f"每周{WEEKDAY_NAMES[weekday][1]}重复"
    return ""


# ---------------------------------------------------------------- 持久化

def get_pending(db: Session, user_id: int) -> dict[str, Any] | None:
    row = db.get(MemoPending, user_id)
    if row is None:
        return None
    if row.expires_at <= utcnow():
        return None
    try:
        draft = json.loads(row.draft_json or "{}")
        return None if is_status_question(str(draft.get("raw_input") or "")) else draft
    except Exception:
        return None


def save_pending(db: Session, user_id: int, draft: dict[str, Any]) -> None:
    row = db.get(MemoPending, user_id)
    payload = json.dumps(draft, ensure_ascii=False)
    if row is None:
        db.add(MemoPending(user_id=user_id, draft_json=payload, expires_at=utcnow() + PENDING_TTL))
    else:
        row.draft_json = payload
        row.expires_at = utcnow() + PENDING_TTL
    db.flush()


def clear_pending(db: Session, user_id: int) -> None:
    row = db.get(MemoPending, user_id)
    if row is not None:
        db.delete(row)
        db.flush()


def create_memo(db: Session, user_id: int, draft: dict[str, Any], *, source: str, now: dt.datetime) -> Memo | None:
    trigger = build_trigger(draft, now)
    if draft.get("missing") or trigger is None or not draft.get("content"):
        return None
    if trigger <= now:
        draft["missing"] = ["future_time"]
        return None
    memo = Memo(user_id=user_id, content=str(draft["content"])[:512], next_trigger_at=trigger,
                recurrence=draft.get("recurrence") or "none",
                interval_days=repetition(draft)[1],
                weekday=draft.get("weekday") if draft.get("recurrence") == "weekly" else None,
                status="active", source=source, raw_input=str(draft.get("raw_input") or "")[:2000])
    if memo.recurrence == "weekly" and memo.weekday is None:
        memo.weekday = trigger.weekday()
    db.add(memo)
    db.flush()
    return memo


def normalize_ai_memo(raw: Any, now: dt.datetime, *, anchor: dict | None = None) -> dict[str, Any] | None:
    """把模型的 memo 意图收敛成与解析器相同的草稿结构；无效返回 None。"""
    if not isinstance(raw, dict):
        return None
    if any(raw.get(key) is not None for key in ("end_date", "until", "cron", "weekdays", "count", "end_at")):
        raise HTTPException(400, "这种带截止日期或特殊周期的安排还不能完整保存。可以改为具体日期的多条提醒，或每隔几天循环。")
    content = str(raw.get("content") or raw.get("note") or "").strip()[:200]
    recurrence, interval_days = repetition(raw)
    weekday = raw.get("weekday")
    if isinstance(weekday, bool) or not isinstance(weekday, int) or not 0 <= weekday <= 6:
        weekday = None
    draft: dict[str, Any] = {"content": content, "trigger_at": None, "date": None, "time": None,
                             "recurrence": recurrence, "interval_days": interval_days, "weekday": weekday, "date_desc": "",
                             "time_only": False, "raw_input": ""}
    trigger_raw = str(raw.get("trigger_at") or raw.get("remind_at") or "").strip()
    trigger = None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            trigger = dt.datetime.strptime(trigger_raw[:19], fmt)
            break
        except ValueError:
            continue
    if trigger is None and trigger_raw:
        clock, _ = parse_clock(trigger_raw)
        date_value, _m, desc = parse_date(trigger_raw, now.date())
        if date_value and clock:
            trigger = dt.datetime.combine(date_value, clock)
            draft["date_desc"] = desc
    if trigger is not None:
        draft.update(trigger_at=trigger.isoformat(timespec="minutes"), date=trigger.date().isoformat(),
                     time=trigger.strftime("%H:%M"))
        if recurrence == "weekly" and weekday is None:
            draft["weekday"] = trigger.weekday()
    if trigger is None:
        date_raw = str(raw.get("date") or "")
        try:
            draft["date"] = dt.date.fromisoformat(date_raw).isoformat()
        except ValueError:
            pass
        time_raw = str(raw.get("time") or "").strip()
        clock, matched = parse_clock(time_raw)
        if clock and matched.strip() == time_raw:
            draft["time"] = clock.strftime("%H:%M")
    day = cn_int(str(raw.get("day") or ""))
    if day and 1 <= day <= 60:
        draft["day"] = day
    if day and 1 <= day <= 60 and anchor:
        draft["trigger_at"] = None
        draft["date"] = (dt.date.fromisoformat(anchor["date"]) + dt.timedelta(days=day - anchor["day"])).isoformat()
        draft["date_desc"] = f"计划第{day}天"
    if day and not anchor:
        draft["stage_unresolved"] = True
    for key in ("time_window", "before", "any_time"):
        if key in raw:
            draft[key] = raw[key]
    if draft["recurrence"] == "weekly" and draft["weekday"] is not None:
        draft["date_desc"] = "每" + WEEKDAY_NAMES[draft["weekday"]]
    elif draft["recurrence"] == "daily":
        draft["date_desc"] = "每天"
    draft["missing"] = _draft_missing(draft)
    return draft


def prepare_draft(draft: dict, now: dt.datetime, *, auto_time: bool, text: str,
                  inherit_repeat: bool = True) -> dict:
    """保留时间边界；只有用户授权时才选择默认时间。"""
    draft = dict(draft)
    if inherit_repeat:
        from app.memo_clauses import global_repeat, is_compound
        repeat = global_repeat(text) if is_compound(text) else parse_repeat(text)
    else:
        repeat = None
    if repeat:
        draft.update(repeat)
    recurrence, days = repetition(draft)
    draft.update(recurrence=recurrence, interval_days=days)
    if draft.get("trigger_at"):
        try:
            trigger = dt.datetime.fromisoformat(str(draft["trigger_at"]))
            if trigger.tzinfo is not None:
                raise ValueError("timezone")
            draft.update(date=trigger.date().isoformat(), time=trigger.strftime("%H:%M"))
        except ValueError:
            raise HTTPException(400, "提醒时间格式无效，请提供本地日期和时刻。") from None
    start, end = dt.time(0), dt.time(23, 59)
    constrained = False
    window = draft.get("time_window")
    if window:
        if not isinstance(window, dict):
            raise HTTPException(400, "时间范围没看清，请补充开始和结束时刻。")
        start = parse_clock(str(window.get("start") or ""))[0]
        end = parse_clock(str(window.get("end") or ""))[0]
        if start is None or end is None or start > end:
            raise HTTPException(400, "时间范围无效，请给出同一天内的开始和结束时刻。")
        constrained = True
    if draft.get("before"):
        deadline = parse_clock(str(draft["before"]))[0]
        if deadline is None or deadline == dt.time(0):
            raise HTTPException(400, "截止时间无效，请补充具体时刻。")
        end = min(end, (dt.datetime.combine(now.date(), deadline) - dt.timedelta(minutes=1)).time())
        constrained = True
    clock = parse_clock(str(draft.get("time") or ""))[0]
    if constrained and clock and not start <= clock <= end:
        raise HTTPException(400, "提醒时间超出了计划允许的时间范围，还没有保存，请重新选择。")
    explicit_clock = parse_clock(text)[0]
    if (constrained or draft.get("any_time")) and not auto_time and not explicit_clock:
        draft.update(time=None, trigger_at=None)
        clock = None
    if not clock and auto_time:
        low, high = start.hour * 60 + start.minute, end.hour * 60 + end.minute
        if draft.get("date") == now.date().isoformat():
            low = max(low, now.hour * 60 + now.minute + 1)
        if low <= high:
            selected = (low + high) // 2 if window else min(max(9 * 60, low), high)
            if draft.get("before") and not window:
                selected = max(low, min(selected, high - 59))
            draft.update(time=f"{selected // 60:02}:{selected % 60:02}", trigger_at=None)
    draft["missing"] = _draft_missing(draft)
    if draft.get("stage_unresolved"):
        draft["missing"].append("stage_anchor")
    return draft


def create_memos(db: Session, user_id: int, drafts: list[dict], *, source: str, now: dt.datetime,
                 template: list[dict] | None = None, anchor: dict | None = None) -> list[Memo]:
    """先验证整份计划，再一次性新增；缺信息时不安排部分步骤。"""
    rows = []
    plan_id = uuid.uuid4().hex
    for draft in drafts:
        trigger = build_trigger(draft, now)
        if draft.get("missing") or trigger is None or not draft.get("content"):
            continue
        if trigger <= now:
            draft["missing"] = ["future_time"]
            continue
        rows.append(Memo(user_id=user_id, content=draft["content"][:512], next_trigger_at=trigger,
                         recurrence=draft.get("recurrence") or "none", interval_days=repetition(draft)[1],
                         weekday=trigger.weekday() if draft.get("recurrence") == "weekly" else None,
                         plan_id=plan_id, plan_json=json.dumps({"steps": template or drafts, "anchor": anchor, "step": draft}, ensure_ascii=False), stage_day=draft.get("day", 0),
                         status="active", source=source, raw_input=str(draft.get("raw_input") or "")[:2000]))
    if len(rows) != len(drafts):
        return []
    db.add_all(rows)
    db.flush()
    return rows


# ---------------------------------------------------------------- 序列化与提醒文案

def serialize_memo(memo: Memo) -> dict[str, Any]:
    return {
        "id": memo.id,
        "content": memo.content,
        "nextTriggerAt": memo.next_trigger_at.strftime("%Y-%m-%d %H:%M") if memo.next_trigger_at else "",
        "triggerDate": memo.next_trigger_at.strftime("%Y-%m-%d") if memo.next_trigger_at else "",
        "recurrence": memo.recurrence,
        "intervalDays": memo.interval_days,
        "planId": memo.plan_id,
        "stageDay": memo.stage_day,
        "recurrenceLabel": repeat_label(memo),
        "weekday": memo.weekday,
        "status": memo.status,
        "source": memo.source,
        "pushStatus": memo.push_status or "",
        "lastSentAt": memo.last_sent_at.strftime("%Y-%m-%d %H:%M") if memo.last_sent_at else None,
        "createdAt": memo.created_at.strftime("%Y-%m-%d %H:%M") if memo.created_at else "",
    }


REMINDER_TEMPLATES = [
    "⏰ 叮咚！你的小闹钟上线啦：{time} 到咯，该{content}啦，别让它在备忘录里孤单等待哟～",
    "🧚 备忘小精灵敲门啦：现在是 {time}，说好要{content}的，就是现在，冲鸭！",
    "🐰 蹦蹦跳跳来报时：{content}的时间到啦（{time}），快行动起来，做完奖励自己一朵小红花～",
    "📣 提醒广播开始啦：{time}，记得{content}哦。我负责喊，你负责做到，完美配合！",
    "🌟 星星眨眨眼提醒你：{time} 啦，该{content}咯，磨蹭的小蜗牛也要出发啦～",
    "🍀 幸运提醒送到：{time}，别忘了{content}。做完这件事，今天又是元气满满的一天！",
]


def build_reminder_text(memo: Memo, when: dt.datetime) -> str:
    template = REMINDER_TEMPLATES[(memo.id or 0) % len(REMINDER_TEMPLATES)]
    text = template.format(time=when.strftime("%H:%M"), content=memo.content)
    repeat = repeat_label(memo)
    if repeat:
        text += f"（这是{repeat}的小提醒）"
    return text


def next_after(trigger: dt.datetime, recurrence: str, now: dt.datetime, interval_days: int = 0) -> dt.datetime:
    """重复备忘顺延到下一次（跳过已经错过的周期，避免补发风暴）。"""
    _, days = repetition({"recurrence": recurrence, "interval_days": interval_days})
    if not days:
        raise ValueError("一次性提醒没有下一个周期")
    step = dt.timedelta(days=days)
    return trigger + step * max(1, (now - trigger) // step + 1)
