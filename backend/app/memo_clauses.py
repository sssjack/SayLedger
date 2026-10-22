"""复合提醒的路由与完整性检查，避免快捷解析只执行半句话。"""
from __future__ import annotations

import datetime as dt
import re

from fastapi import HTTPException

from app import memo as rules

_JOIN = re.compile(r"还有|另外|并且|同时|以及|然后|再(?:把|将|帮我|提醒)|[，,；;。]\s*(?:第|每|后天|明天|把|将|改|取消|不要)")
_STAGE = re.compile(r"第([\d一二两三四五六七八九十]+)天")
_CLAUSES = re.compile(r"[，,；;。]|还有|另外|并且|同时|以及|然后")


def is_compound(text: str) -> bool:
    clocks = list(rules._CLOCK_RE.finditer(text))
    return bool(_JOIN.search(text) or len(clocks) > 1
                or rules.allows_auto_time(text) and (clocks or _STAGE.search(text))
                or clocks and _STAGE.search(text) and re.search(r"循环|重复|每天|每周|每隔", text))


def global_repeat(text: str) -> dict | None:
    """阶段自己的循环设置不能扩散到整份计划。"""
    clauses = _CLAUSES.split(text)
    if len(re.findall(r"提醒我", text)) > 1:
        return None
    repeats = []
    for clause in clauses:
        stage = _STAGE.search(clause)
        common = clause[:stage.start()] if stage else clause
        repeat = rules.parse_repeat(common)
        if repeat and not re.search(r"提醒我.+", common):
            repeats.append(repeat)
    return repeats[-1] if repeats else None


def repeat_is_global(text: str) -> bool:
    return global_repeat(text) is not None


def stage_repeats(text: str) -> dict[int, dict]:
    result = {}
    for clause in _CLAUSES.split(text):
        stages = list(_STAGE.finditer(clause))
        stage = stages[0] if len(stages) == 1 else None
        repeat = rules.parse_repeat(clause[stage.end():]) if stage else None
        if stage and repeat:
            result[rules.cn_int(stage[1])] = repeat
    return result


def _changed_fields(data: dict, state: dict) -> list[tuple[dict, dict]]:
    items = state.get("reminders", {}).get("items", [])
    if data.get("action") == "memo_update":
        selected = data.get("memo_ids") or state.get("reminders", {}).get("focus_ids", [])
        group_ids = {row.get("planId") for row in items if row.get("id") in selected and row.get("planId")}
        if not data.get("memo_ids"):
            selected = [row["id"] for row in items if row["id"] in selected or row.get("planId") in group_ids]
        overrides = {}
        for update in data.get("updates") or []:
            if not isinstance(update, dict):
                continue
            for memo_id in update.get("memo_ids") or []:
                overrides.setdefault(memo_id, {}).update(update.get("changes") or {})
        if not selected:
            selected = list(overrides) or [row["id"] for row in items if row.get("status") == "active"]
        return [(row, {**(data.get("changes") or {}), **overrides.get(row["id"], {})})
                for row in items if row["id"] in selected]
    if data.get("action") in {"memo", "memo_create", "memo_pending", "memo_batch"}:
        draft = data.get("draft") or {}
        raw = data.get("memos") or draft.get("batch") or [data.get("memo") or draft]
        return [(entry, entry) for entry in raw if isinstance(entry, dict)]
    return []


def _repeat_fields(fields: dict) -> dict:
    if not fields.get("recurrence"):
        return {}
    try:
        recurrence, days = rules.repetition(fields)
        return {"recurrence": recurrence, "interval_days": days}
    except HTTPException:
        return {}


def _clock_field(fields: dict) -> str:
    clock = rules.parse_clock(str(fields.get("time") or fields.get("trigger_at") or ""))[0]
    return clock.strftime("%H:%M") if clock else ""


def _stage_of(row: dict) -> int | None:
    day = row.get("stageDay") or row.get("day")
    if day:
        return day
    match = re.search(r"第([\d一二两三四五六七八九十]+)[天单]", str(row.get("content") or ""))
    return rules.cn_int(match[1]) if match else None


def omissions(text: str, data: dict, state: dict) -> list[str]:
    """对可独立核对的日期阶段、时刻和循环要求逐项检查；遗漏时只重做规划。"""
    if not is_compound(text) or data.get("action") == "clarify":
        return []
    independent = re.search(r"查账|账单|预算|午饭|晚饭|咖啡|花了|收入|支出", text)
    pending_followup = state.get("pending_memo") and not independent and (
        rules.allows_auto_time(text) or re.search(r"那就|时间|点|循环|重复|取消", text))
    reminder_request = bool(re.search(r"提醒|备忘|闹钟|循环", text) or pending_followup
                            or _STAGE.search(text) and state.get("reminders", {}).get("focus_ids"))
    if not reminder_request:
        return []
    if data.get("action") == "memo_query" and rules.is_status_question(text):
        return []
    if data.get("action") not in {"memo", "memo_create", "memo_pending", "memo_batch", "memo_update", "memo_cancel", "memo_query"}:
        return ["整句话包含提醒要求，不能只返回聊天回复或其他动作"]
    if data.get("action") == "memo_update":
        if not isinstance(data.get("changes") or {}, dict) or not isinstance(data.get("updates") or [], list):
            return ["changes和updates需要是有效的修改对象与列表"]
        if data.get("memo_ids") is not None and not isinstance(data["memo_ids"], list):
            return ["memo_ids需要是提醒编号列表"]
        if any(not isinstance(edit, dict) or not isinstance(edit.get("changes"), dict)
               or not isinstance(edit.get("memo_ids"), list) for edit in data.get("updates") or []):
            return ["每一步调整必须有memo_ids列表和changes对象"]
    if data.get("action") == "memo_batch" and not isinstance(data.get("memos"), list):
        return ["多项提醒需要memos列表"]
    changes = _changed_fields(data, state)
    missing = []
    if state.get("independent_reminder") and (data.get("action") in {"memo_update", "memo_cancel", "memo_query"}
            or any(row.get("day") for row, _ in changes)):
        missing.append("这是独立新建事项，请用今天日期换算date+time或trigger_at，不能使用旧计划的day、阶段锚点或修改旧提醒")
    clauses = _CLAUSES.split(text)
    if any(re.search(r"(?:花了|支出|收入|记账).*\d|(?:午饭|晚饭|咖啡|打车)\s*\d", clause)
           and not re.search(r"提醒|备忘|闹钟", clause) for clause in clauses) and re.search(r"提醒|备忘|闹钟", text):
        missing.append("这句话同时包含记账和提醒，当前不能在一个动作里完整保存，必须clarify请用户分开发送，并明确整句尚未执行")
    pending_steps = (state.get("pending_memo") or {}).get("batch") or []
    if pending_steps and not state.get("independent_reminder") and rules.allows_auto_time(text) and data.get("action") in {"memo", "memo_create", "memo_pending", "memo_batch"}:
        expected = {step.get("day") for step in pending_steps if step.get("day")}
        actual = {_stage_of(row) for row, _ in changes}
        if len(changes) < len(pending_steps) or not expected.issubset(actual):
            missing.append("正在补齐多步骤草稿，不能只创建其中一步；必须返回原草稿全部步骤及这次修改")
    if re.search(r"每个?月|工作日|节假日|每隔?[\d一二两三四五六七八九十]+(?:小时|分钟)|持续|直到|截止后", text) and data.get("action") not in {"memo_query", "clarify"}:
        missing.append("有暂不支持的按月、小时、工作日或截止规则，应明确说明整句未执行，不能丢掉该规则后保存前半句")
    if len(re.findall(r"提醒我", text)) > 1 and data.get("action") != "memo_query":
        if len(changes) < len(re.findall(r"提醒我", text)):
            missing.append("不同事情的多条提醒被合并了，需要逐条保留内容和日期时刻")
    repeat = global_repeat(text)
    if repeat and repeat_is_global(text) and data.get("action") == "memo_update":
        if _repeat_fields(data.get("changes") or {}) != repeat:
            missing.append("整份计划的循环规则遗漏，必须放在共同changes中：" + str(repeat))
        items = state.get("reminders", {}).get("items", [])
        selected_ids = {row["id"] for row, _ in changes}
        plans = {row.get("planId") for row in items if row.get("id") in selected_ids and row.get("planId")}
        if any(row["status"] == "active" and row.get("planId") in plans and row["id"] not in selected_ids for row in items):
            missing.append("循环要求针对整份计划，不能只选择其中一个步骤")
    clock_days, repeat_days = set(), set()
    for clause in clauses:
        stages = list(_STAGE.finditer(clause))
        stage = stages[0] if len(stages) == 1 else None
        clocks = list(rules._CLOCK_RE.finditer(clause))
        if stage is not None and re.search(r"取消|删除|停止|关掉", clause):
            day = rules.cn_int(stage[1])
            matching = [fields for row, fields in changes if _stage_of(row) == day]
            if not matching or any(fields.get("status") != "cancelled" for fields in matching):
                missing.append(f"取消第{day}天提醒的要求遗漏")
        step_repeat = rules.parse_repeat(clause[stage.end():]) if stage else None
        if stage is not None and step_repeat:
            day = rules.cn_int(stage[1])
            repeat_days.add(day)
            matching = [fields for row, fields in changes if _stage_of(row) == day]
            expected = step_repeat
            if data.get("action") == "memo_update" and (not matching or any(_repeat_fields(fields) != expected for fields in matching)):
                missing.append(f"第{day}天自己的循环规则遗漏，不能被其他步骤覆盖")
        if stage is None or len(clocks) != 1 or re.search(r"前|之后|以后|之间|以内", clause):
            continue
        day = rules.cn_int(stage[1])
        clock_days.add(day)
        clock = rules.parse_clock(clause)[0]
        if clock is None:
            continue
        matching = [fields for row, fields in changes if _stage_of(row) == day]
        requested = clock.strftime("%H:%M")
        if not matching or any(_clock_field(fields) != requested for fields in matching):
            missing.append(f"第{day}天的具体时刻{requested}遗漏，需要独立设置该步骤，其他步骤不能跟着改时间")
    if data.get("action") == "memo_update":
        if clock_days and any(_stage_of(row) not in clock_days and ("time" in fields or "trigger_at" in fields) for row, fields in changes):
            missing.append("只要求调整指定步骤的时刻，不得把同一时间应用到其他步骤")
        if repeat_days and not repeat_is_global(text) and any(_stage_of(row) not in repeat_days and "recurrence" in fields for row, fields in changes):
            missing.append("循环设置只针对指定步骤，不能扩大到整份计划")
    # 明确说了两次“提醒我”的新事项按原文顺序核对，避免两件事串用日期/时刻。
    if len(re.findall(r"提醒我", text)) > 1 and data.get("action") == "memo_batch":
        clauses = [clause for clause in _CLAUSES.split(text) if "提醒我" in clause]
        now = dt.datetime.fromisoformat(state["now"])
        for clause, (_, fields) in zip(clauses, changes):
            clock = rules.parse_clock(clause)[0]
            date = rules.parse_date(clause, now.date())[0]
            actual_clock = _clock_field(fields)
            actual_date = str(fields.get("date") or fields.get("trigger_at") or "")[:10]
            anchor = state.get("stage_anchor")
            if not actual_date and anchor and fields.get("day"):
                day = rules.cn_int(str(fields["day"]))
                if day:
                    actual_date = (dt.date.fromisoformat(anchor["date"]) + dt.timedelta(days=day-anchor["day"])).isoformat()
            if clock and actual_clock != clock.strftime("%H:%M") or date and actual_date != date.isoformat():
                missing.append("多个新事项必须分别保留原句指定的日期和时刻，不能互相串用")
            repeat = rules.parse_repeat(clause)
            if repeat:
                effective = {**(data.get("repeat") or {}), **fields}
                if _repeat_fields(effective) != repeat:
                    missing.append("不同事项自己的重复规则遗漏，不能把最后一项的规则套到全部事项上")
    return missing
