"""提醒查询和修改使用实际存储状态；模型只负责理解意图与选定目标。"""
from __future__ import annotations

import datetime as dt
import json
import re

from fastapi import HTTPException
from sqlalchemy import select

from app import memo as rules
from app.db import Memo, utcnow


def _generic_reference(text: str) -> bool:
    """仅让无具体事项名称的简单指令走快捷路径；复杂定位交给模型。"""
    remainder = re.sub(r"现在|目前|当前|已经|设置的|刚才的|这些|这组|这个|这份|所有|全部|我的|"
                       r"提醒计划|提醒|备忘录|备忘|闹钟|计划|是不是|有没有|有哪些|什么时候|下一次|"
                       r"是否|查询|查看|看看|列出|多久|什么|几点|安排|设置|循环|周期|重复|"
                       r"改成|改为|修改为|调整为|设为|设置成|不再|不要|取消|只|不|"
                       r"时间你定|你来定|你看着办|你安排|每天|每日|每周|每星期|每隔|每|隔|"
                       r"请|帮我|把|的|是|有|我|吗|么|吧|一天|一次|天|一|个|为|"
                       r"[\d零一二两三四五六七八九十\s，。！？!?、,]+", "", text)
    return not remainder


def snapshot(db, user_id: int, focus_ids: list[int]) -> dict:
    rows = list(db.scalars(select(Memo).where(Memo.user_id == user_id)
                           .order_by(Memo.status != "active", Memo.id.desc()).limit(50)).all())
    templates = {}
    for row in rows:
        if row.plan_id and row.plan_id not in templates:
            templates[row.plan_id] = json.loads(row.plan_json or "{}")
    return {"items": [rules.serialize_memo(row) for row in rows], "focus_ids": focus_ids,
            "plans": templates}


def control_intent(text: str, pending: dict | None, state: dict) -> dict | None:
    if rules.is_status_question(text) and _generic_reference(text) or (state.get("reminders", {}).get("focus_ids") and re.fullmatch(r"(?:那|现在)?(?:设置|安排)(?:好了|好|成功|生效)了吗[？?]?", text.strip())):
        return {"action": "memo_query", "scope": "all" if re.search(r"所有|全部|有哪些|列出|我的提醒", text) else "focus"}
    repeat = rules.parse_repeat(text)
    independent = re.search(r"花了|花费|支出|收入|(?:午饭|晚饭|早餐|咖啡|打车|买了).*\d", text)
    if pending and not independent and (rules.allows_auto_time(text) or repeat and _generic_reference(text)):
        return {"action": "memo_create", "draft": pending}
    if repeat and _generic_reference(text) and re.search(r"循环|改成|改为|修改|这些|这组|刚才|现在的", text):
        return {"action": "memo_update", "changes": repeat, "scope": "all" if re.search(r"所有|全部", text) else "focus"}
    cancel_target = re.fullmatch(r"(?:请|帮我)?(?:取消|删除|停止|关掉)(?:这组|这个|这份|刚才的|刚才那条|刚才那组|所有|全部|我的)?(?:提醒|提醒计划|计划)(?:吧|了)?[。！!]?", text.strip())
    if re.search(r"取消|删除|停止|关掉", text) and cancel_target and not pending:
        return {"action": "memo_cancel", "scope": "all" if re.search(r"所有|全部", text) else "focus"}
    return None


def _targets(db, user_id: int, data: dict, context: dict, *, query: bool) -> list[Memo]:
    rows = list(db.scalars(select(Memo).where(Memo.user_id == user_id).order_by(Memo.next_trigger_at)).all())
    explicit = data.get("memo_ids")
    if explicit is not None:
        if not isinstance(explicit, list) or not explicit or any(type(value) is not int for value in explicit):
            raise HTTPException(400, "请明确要操作的提醒。")
        selected = [row for row in rows if row.id in explicit]
        if len(selected) != len(set(explicit)):
            raise HTTPException(400, "没有找到对应提醒，请重新选择。")
        return selected
    keyword = str(data.get("keyword") or "").strip()
    if keyword:
        rows = [row for row in rows if keyword in row.content]
    if data.get("scope") == "all":
        return [row for row in rows if row.status == "active"]
    focus_ids = context.get("reminders", {}).get("focus_ids", [])
    focused = [row for row in rows if row.id in focus_ids]
    if focused and not keyword:
        plans = {row.plan_id for row in focused if row.plan_id}
        if not query and context.get("memo_focus_kind") == "memo_query" and len({row.plan_id or str(row.id) for row in focused}) > 1:
            raise HTTPException(400, "刚才查到了几份提醒计划。请说明要修改哪一份，或明确说‘所有提醒’。")
        return [row for row in rows if row.id in focus_ids or row.plan_id and row.plan_id in plans]
    active = [row for row in rows if row.status == "active"]
    groups = {row.plan_id or str(row.id) for row in active}
    if len(groups) <= 1:
        return active
    if query:
        return active
    raise HTTPException(400, "找到了几份提醒计划。请告诉我要修改哪件事，或明确说‘所有提醒’。")


def result_reply(rows: list[Memo], title: str) -> str:
    ordered = sorted(rows, key=lambda row: (row.stage_day or 99, row.next_trigger_at))
    labels = {rules.repeat_label(row) or "仅提醒一次" for row in ordered if row.status == "active"}
    lines = [f"📌 {title}"]
    if len(labels) == 1:
        lines += [f"🔁 {next(iter(labels))}"]
    for row in ordered[:8]:
        stage = f"第{row.stage_day}天 · " if row.stage_day else ""
        status = {"done": " · 已完成", "cancelled": " · 已取消"}.get(row.status, "")
        repeat = f" · {rules.repeat_label(row) or '仅一次'}" if len(labels) > 1 else ""
        lines += [f"\n{stage}{row.content[:70]}", f"⏰ {row.next_trigger_at:%m月%d日 %H:%M}{status}{repeat}"]
    if len(rows) > 8:
        lines += [f"\n共{len(rows)}条，完整安排可在网页备忘录查看。"]
    return "\n".join(lines)


def _update_specs(data: dict) -> tuple[dict, dict[int, dict]]:
    common = data.get("changes") or {}
    edits = data.get("updates") or []
    if not isinstance(common, dict) or not isinstance(edits, list) or len(edits) > 8:
        raise HTTPException(400, "每次最多支持8组步骤调整，请说明具体设置。")
    overrides = {}
    for edit in edits:
        if not isinstance(edit, dict) or not isinstance(edit.get("changes"), dict) or not edit["changes"]:
            raise HTTPException(400, "有一项调整缺少具体设置，整份计划还没有修改。")
        ids = edit.get("memo_ids")
        if not isinstance(ids, list) or not ids or any(type(value) is not int for value in ids):
            raise HTTPException(400, "有一项调整没有明确对应提醒，整份计划还没有修改。")
        for memo_id in ids:
            current = overrides.setdefault(memo_id, {})
            if any(key in current and current[key] != value for key, value in edit["changes"].items()):
                raise HTTPException(400, "同一步骤出现了冲突设置，整份计划还没有修改，请确认最终规则。")
            current.update(edit["changes"])
    if not common and not overrides:
        raise HTTPException(400, "请说明要改时间、内容还是循环规则。")
    allowed = {"recurrence", "interval_days", "time", "trigger_at", "content", "status"}
    if any(set(change) - allowed for change in [common, *overrides.values()]):
        raise HTTPException(400, "这次修改包含暂不支持的设置，整份计划还没有修改。请说明时间、内容或循环天数。")
    if any("status" in change and change["status"] != "cancelled" for change in [common, *overrides.values()]):
        raise HTTPException(400, "已结束的步骤不能在修改中重新启用，请明确创建新提醒。")
    return dict(common), overrides


def execute_control(db, user_id: int, data: dict, text: str, context: dict, now: dt.datetime) -> tuple[str, dict]:
    action = data["action"]
    common, overrides = _update_specs(data) if action == "memo_update" else ({}, {})
    target_data = dict(data)
    if overrides and not common and not data.get("memo_ids"):
        target_data["memo_ids"] = list(overrides)
    # “所有”必须来自用户，模型不能自行扩大修改范围。
    if action != "memo_query" and data.get("scope") == "all" and not re.search(r"所有|全部", text):
        raise HTTPException(400, "请说明要修改哪件事，或明确说‘所有提醒’。")
    rows = _targets(db, user_id, target_data, context, query=action == "memo_query")
    if set(overrides) - {row.id for row in rows}:
        raise HTTPException(400, "有一项调整不属于当前选定的提醒，整份计划还没有修改。")
    if not rows:
        return "📭 没有找到对应的已保存提醒。还在商量中的计划需要补齐信息后才会生效。", {"kind": "memo_query", "memos": []}
    if action == "memo_query":
        requested = rules.parse_repeat(text)
        active = [row for row in rows if row.status == "active"]
        if requested and active:
            recurrence, days = rules.repetition(requested)
            matches = all(row.recurrence == recurrence and (row.interval_days == days if recurrence == "interval" else True) for row in active)
            title = "是的，已按这个循环规则保存" if matches else "目前还没有按你说的循环规则设置"
        else:
            title = "当前保存的提醒安排"
        return result_reply(rows, title), {"kind": "memo_query", "memos": [rules.serialize_memo(row) for row in rows]}
    if action == "memo_cancel":
        changes = [{"id": row.id, "status": "cancelled", "updated_at": utcnow()} for row in rows if row.status == "active"]
        if changes:
            db.bulk_update_mappings(Memo, changes)
        db.expire_all()
        rules.clear_pending(db, user_id)
        return f"🌿 已取消{len(changes)}条提醒，这份安排不会再打扰你啦。", {"kind": "memo", "memos": [rules.serialize_memo(row) for row in rows]}
    from app.memo_clauses import global_repeat, is_compound
    repeat = global_repeat(text) if is_compound(text) else rules.parse_repeat(text)
    if repeat:
        common.update(repeat)
    if "content" in common and len(rows) != 1:
        raise HTTPException(400, "要修改哪一步的内容呢？请说明对应步骤。")
    updates, additions = [], []
    # 先准备全部变更，不在循环里执行数据库写入。
    for row in rows:
        if row.status == "cancelled":
            continue
        changes = {**common, **overrides.get(row.id, {})}
        if not changes:
            continue
        if changes.get("status") == "cancelled":
            updates.append({"id": row.id, "status": "cancelled", "updated_at": utcnow()})
            continue
        draft = {"content": changes.get("content", row.content),
                 "trigger_at": changes.get("trigger_at", row.next_trigger_at.isoformat(timespec="minutes")),
                 "time": row.next_trigger_at.strftime("%H:%M"), "date": row.next_trigger_at.date().isoformat(),
                 "recurrence": changes.get("recurrence", row.recurrence),
                 "interval_days": changes.get("interval_days", 0 if "recurrence" in changes else row.interval_days)}
        if row.plan_id:
            saved_plan = json.loads(row.plan_json or "{}")
            template = saved_plan.get("steps", [])
            original = saved_plan.get("step") or next((step for step in template if step.get("day", 0) == row.stage_day and step.get("content") == row.content), {})
            draft.update({key: original[key] for key in ("time_window", "before", "any_time") if key in original})
        if "time" in changes:
            clock, matched = rules.parse_clock(str(changes["time"]))
            if not clock or matched.strip() != str(changes["time"]).strip():
                raise HTTPException(400, "请提供明确的提醒时刻，例如17:25。")
            draft.update(time=clock.strftime("%H:%M"), trigger_at=None)
        draft = rules.prepare_draft(draft, now, auto_time=rules.allows_auto_time(text), text=text, inherit_repeat=False)
        # 修改循环时保留原来的时间；授权自动选择只用于尚未选定的时间。
        if "time" not in changes and "trigger_at" not in changes:
            draft.update(time=row.next_trigger_at.strftime("%H:%M"), trigger_at=row.next_trigger_at.isoformat(timespec="minutes"), missing=[])
        trigger = rules.build_trigger(draft, now)
        if draft.get("missing") or trigger is None or trigger <= now or not str(draft["content"]).strip():
            raise HTTPException(400, "新的安排缺少有效的未来时间或内容，还没有修改，请补充。")
        updated_plan = json.loads(row.plan_json or "{}")
        if row.plan_id:
            updated_plan["step"] = {**draft, "day": row.stage_day}
        updates.append({"id": row.id, "content": str(draft["content"])[:512], "recurrence": draft["recurrence"],
                        "interval_days": draft["interval_days"], "weekday": trigger.weekday() if draft["recurrence"] == "weekly" else None,
                        "next_trigger_at": trigger, "status": "active", "updated_at": utcnow(),
                        "plan_json": json.dumps(updated_plan, ensure_ascii=False)})
    if not updates:
        raise HTTPException(400, "这些提醒已取消，请重新创建计划。")
    # 完整阶段模板保留已过去的第1天；转成循环计划时补入下一轮。
    plan_ids = {row.plan_id for row in rows if row.plan_id}
    all_plan_rows = list(db.scalars(select(Memo).where(Memo.user_id == user_id, Memo.plan_id.in_(plan_ids))).all()) if plan_ids else []
    for plan_id in plan_ids:
        group = [row for row in all_plan_rows if row.plan_id == plan_id]
        if not all(row.id in {item.id for item in rows} for row in group if row.status == "active"):
            continue
        sample = next((row for row in rows if row.plan_id == plan_id and row.id in {item["id"] for item in updates if "recurrence" in item}), None)
        if sample is None:
            continue
        changed = next(item for item in updates if item["id"] == sample.id)
        if changed["recurrence"] == "none":
            continue
        saved = json.loads(sample.plan_json or "{}")
        for step in saved.get("steps", []):
            if not step.get("day") or any(row.stage_day == step["day"] for row in group):
                continue
            draft = rules.prepare_draft({**step, "recurrence": changed["recurrence"], "interval_days": changed["interval_days"]},
                                         now, auto_time=rules.allows_auto_time(text), text=text, inherit_repeat=False)
            trigger = rules.build_trigger(draft, now)
            if draft.get("missing") or trigger is None:
                raise HTTPException(400, "循环计划还有缺失的步骤时间，还没有修改，请补充或让我选择时间。")
            additions.append(Memo(user_id=user_id, content=draft["content"], next_trigger_at=trigger,
                                  recurrence=draft["recurrence"], interval_days=draft["interval_days"],
                                  weekday=trigger.weekday() if draft["recurrence"] == "weekly" else None,
                                  plan_id=plan_id, plan_json=json.dumps({**saved, "step": draft}, ensure_ascii=False), stage_day=step["day"], source=sample.source))
    db.bulk_update_mappings(Memo, updates)
    db.add_all(additions)
    db.flush()
    db.expire_all()
    rules.clear_pending(db, user_id)
    changed_rows = [row for row in rows if row.id in {item["id"] for item in updates}] + additions
    report_rows = list({row.id: row for row in [*changed_rows, *all_plan_rows]}.values()) if data.get("report_all") else changed_rows
    return result_reply(report_rows, "提醒计划已更新"), {"kind": "memo", "memos": [rules.serialize_memo(row) for row in report_rows]}
