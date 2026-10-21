"""备忘录/提醒：中文自然语言的确定性解析、待确认草稿与提醒文案。

模型对相对日期的换算会漂移，所以日期、时刻、重复规则都由这里算；
模型只负责在图片等场景给出结构化 memo 意图，服务端再校验执行。
草稿缺时刻或缺事件时先存 MemoPending，用户下一句补齐后才真正创建。
"""
from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.db import Memo, MemoPending, utcnow

PENDING_TTL = dt.timedelta(minutes=30)
WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
_WEEKDAY_CHARS = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6,
                  "1": 0, "2": 1, "3": 2, "4": 3, "5": 4, "6": 5, "7": 6}
_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_NUM = r"(?:\d{1,2}|[零一二两三四五六七八九十]+)"


def cn_int(raw: str | None) -> int | None:
    """把 '三' '十二' '二十三' 这类中文数字或阿拉伯数字转成 int。"""
    if raw is None:
        return None
    raw = raw.strip()
    if raw.isdigit():
        return int(raw)
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


def _clean_content(text: str) -> str:
    cleaned = text
    for pattern in (
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
        return dt.datetime.fromisoformat(draft["trigger_at"])
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
        return dt.datetime.combine(dt.date.fromisoformat(draft["date"]), clock)
    if draft.get("time_only"):
        candidate = dt.datetime.combine(now.date(), clock)
        if candidate <= now:
            candidate += dt.timedelta(days=1)
        return candidate
    return None


def parse_memo_request(text: str, now: dt.datetime) -> dict[str, Any] | None:
    """解析一句备忘请求；不是备忘意图返回 None，否则返回草稿 dict（含 missing）。"""
    text = (text or "").strip()
    if not text or not _MEMO_HINT.search(text):
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
    if compact in _CANCEL_WORDS or "取消" in compact and len(compact) <= 8:
        return "cancel", draft
    merged = dict(draft)
    reparsed = parse_memo_request(text, now) if _MEMO_HINT.search(text or "") else None
    clock, _ = parse_clock(text)
    if reparsed:
        for key in ("content", "trigger_at", "date", "time", "date_desc"):
            if reparsed.get(key):
                merged[key] = reparsed[key]
        if reparsed.get("recurrence") != "none":
            merged["recurrence"] = reparsed["recurrence"]
            merged["weekday"] = reparsed.get("weekday")
        if reparsed.get("time_only"):
            merged["time_only"] = True
    if clock and not merged.get("trigger_at"):
        merged["time"] = clock.strftime("%H:%M")
        if merged.get("recurrence") == "none" and not merged.get("date"):
            merged["time_only"] = True
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
    missing = draft.get("missing") or _draft_missing(draft)
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
        db.delete(row)
        db.flush()
        return None
    try:
        return json.loads(row.draft_json or "{}")
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
    if trigger is None or not draft.get("content"):
        return None
    memo = Memo(user_id=user_id, content=str(draft["content"])[:512], next_trigger_at=trigger,
                recurrence=draft.get("recurrence") or "none",
                weekday=draft.get("weekday") if draft.get("recurrence") == "weekly" else None,
                status="active", source=source, raw_input=str(draft.get("raw_input") or "")[:2000])
    if memo.recurrence == "weekly" and memo.weekday is None:
        memo.weekday = trigger.weekday()
    db.add(memo)
    db.flush()
    return memo


def normalize_ai_memo(raw: Any, now: dt.datetime) -> dict[str, Any] | None:
    """把模型的 memo 意图收敛成与解析器相同的草稿结构；无效返回 None。"""
    if not isinstance(raw, dict):
        return None
    content = str(raw.get("content") or raw.get("note") or "").strip()[:200]
    recurrence = str(raw.get("recurrence") or "none")
    if recurrence not in ("none", "daily", "weekly"):
        recurrence = "none"
    weekday = raw.get("weekday")
    if isinstance(weekday, bool) or not isinstance(weekday, int) or not 0 <= weekday <= 6:
        weekday = None
    draft: dict[str, Any] = {"content": content, "trigger_at": None, "date": None, "time": None,
                             "recurrence": recurrence, "weekday": weekday, "date_desc": "",
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
    if draft["recurrence"] == "weekly" and draft["weekday"] is not None:
        draft["date_desc"] = "每" + WEEKDAY_NAMES[draft["weekday"]]
    elif draft["recurrence"] == "daily":
        draft["date_desc"] = "每天"
    draft["missing"] = _draft_missing(draft)
    return draft


# ---------------------------------------------------------------- 序列化与提醒文案

def serialize_memo(memo: Memo) -> dict[str, Any]:
    return {
        "id": memo.id,
        "content": memo.content,
        "nextTriggerAt": memo.next_trigger_at.strftime("%Y-%m-%d %H:%M") if memo.next_trigger_at else "",
        "triggerDate": memo.next_trigger_at.strftime("%Y-%m-%d") if memo.next_trigger_at else "",
        "recurrence": memo.recurrence,
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


def next_after(trigger: dt.datetime, recurrence: str, now: dt.datetime) -> dt.datetime:
    """重复备忘顺延到下一次（跳过已经错过的周期，避免补发风暴）。"""
    step = dt.timedelta(days=1) if recurrence == "daily" else dt.timedelta(days=7)
    candidate = trigger + step
    while candidate <= now:
        candidate += step
    return candidate
