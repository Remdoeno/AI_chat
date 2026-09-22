from wangcai_app.schedule_receipts import align_weekly_updates, ScheduleContext
"""Adapter from the legacy app namespace to the independent schedule service."""
from wangcai_app.schedule import ScheduleStore, CATEGORIES, calendar_window
from wangcai_app.schedule_memory import ScheduleMemoryBridge, memory_projection
from wangcai_app.prompts.schedule import SCHEDULE_AGENT_PROMPT
from wangcai_app.schedule_conversation import schedule_conversation_messages
from wangcai_app.holidays import HolidayCalendar, fetch_holidays
from pydantic import BaseModel, Field


def schedule_store():
    return ScheduleStore(connect_db, ScheduleMemoryBridge(opening_prompt_cache_key))


def holiday_calendar():
    def fetch(year):
        proxy = get_app_setting("holiday_sync_proxy", "").strip() or load_model_settings().get("web_search_proxy") or WEB_SEARCH_PROXY or None
        return fetch_holidays(year, proxy=proxy)
    return HolidayCalendar(connect_db, fetch)


def run_holiday_sync(stop_event):
    calendar = holiday_calendar()
    while not stop_event.is_set():
        try:
            results = calendar.sync()
            if results:
                record_event(None, "holiday_sync", "", {"results": results})
        except Exception as exc:
            record_event(None, "holiday_sync_retry", "", {"error_type": type(exc).__name__})
        stop_event.wait(60)


def schedule_today():
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()


def schedule_snapshot(owner):
    return {"owner": owner, **calendar_window(schedule_store().list(owner), schedule_today()),
            "holidays": holiday_calendar().window(schedule_today()),
            "categories": [{"id": key, "label": value[0], "color": value[1]} for key, value in CATEGORIES.items()]}


def schedule_agent_decision(context):
    client, http_client, model_slot = openai_client_for_slot(MODEL_SLOT_BACKGROUND, timeout=45)
    try:
        response = client.chat.completions.create(
            **model_completion_kwargs(model_slot),
            messages=schedule_conversation_messages(SCHEDULE_AGENT_PROMPT, context),
            temperature=0.1, max_tokens=model_output_token_limit(model_slot, 4096),
        )
        from wangcai_app.schedule_project_shape import needs_project_repair
        def parse_schedule_response(value):
            _, text = split_think_text(value.choices[0].message.content or "")
            return json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip()))
        initial = parse_schedule_response(response)
        if needs_project_repair(context.get("message", ""), initial):
            response = client.chat.completions.create(
                **model_completion_kwargs(model_slot),
                messages=schedule_conversation_messages(SCHEDULE_AGENT_PROMPT, context) + [
                    {"role": "assistant", "content": json.dumps(initial, ensure_ascii=False)},
                    {"role": "user", "content": "结构校验：你把同一目标的跨日期阶段拆成了普通事项。请合并为一个kind=project及milestones，保留明确的区间、待定窗口和所有其他无关事项；不要猜日期。只返回修正JSON。"}],
                temperature=0.1, max_tokens=model_output_token_limit(model_slot, 6144),
            )
            if needs_project_repair(context.get("message", ""), parse_schedule_response(response)):
                raise ValueError("长期项目结构未整理完整，未保存；请重试或选择长期事项手动添加阶段")
        _, answer = split_think_text(response.choices[0].message.content or "")
        answer = re.sub(r"^```(?:json)?\s*|\s*```$", "", answer.strip())
        decision = json.loads(answer)
        if not isinstance(decision, dict) or not isinstance(decision.get("operations"), list) or not isinstance(decision.get("reply"), str):
            raise ValueError("日程解析结果不完整，请重试或手动编辑")
        return decision
    finally:
        http_client.close()


@scoped_model_call(lambda owner, *args, **kwargs: owner)
def manage_schedule_message(owner, message, request_id, history=None, cancelled=lambda: False):
    store = schedule_store()
    cached = store.cached(owner, request_id)
    if cached:
        return cached
    today = schedule_today()
    events = store.list(owner)
    # Keep undated, future and recently past occurrences available for rescheduling/cancellation.
    recent_start = (datetime.fromisoformat(today) - timedelta(days=30)).date().isoformat()
    relevant = [event for event in events if event.get("repeat") == "weekly" or not event["date"] or (event["end_date"] or event["date"]) >= recent_start]
    if len(relevant) > 500:
        raise ValueError("日程较多，请先在日历中手动编辑目标事项")
    memory_candidates = []
    if re.search(r"导入|整理.*记忆|记忆.*整理|之前.*日程", message):
        devices = shared_user_device_ids(owner)
        if devices:
            memory_candidates = retrieve_future_event_memories(devices[0], limit=30)
    decision = schedule_agent_decision({"now": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "weekday": datetime.fromisoformat(today).strftime("%A"), "today": today,
        "events": relevant, "holidays": holiday_calendar().window(today), "memory_candidates_for_requested_import": memory_candidates,
        "history": history if history is not None else store.history(owner), "message": message})
    operations = align_weekly_updates(decision["operations"], relevant, message, today)
    result = store.apply(owner, operations, request_id, message, decision["reply"][:3000], cancelled)
    return result


def schedule_message_relevant(message, history):
    markers = r"日程|安排|约饭|吃饭|聚餐|约会|会议|开会|组会|社团|面试|宣讲|讲座|活动|预约|截止|报名|出差|旅行|考试|上课|课程|唱歌课|拜访|航班|高铁|火车|婚礼|生日|明天|后天|今天|下周|本周|周[一二三四五六日天]|星期|[0-9]+[月日号点]|\d{1,2}:\d{2}|schedule|calendar|meeting|appointment"
    markers += r"|节假日|放假|调休|补班|国庆|中秋|春节|清明|端午|劳动节|元旦"
    if re.search(markers, message, re.I):
        return True
    return bool(re.search(r"改|取消|删除|确定|确认|参加|不去|去的|那里|那个|这件|推迟|提前|照旧|下午|上午|晚上", message)
                and any(re.search(markers, str(item.get("content", "")), re.I) for item in history[-6:]))


def schedule_context_for_chat(owner, message, request_id, history, cancelled):
    if not owner:
        return "\n日程功能需要先在首页绑定用户；未绑定时不能声称日程已保存。"
    store = schedule_store()
    try:
        result = None
        if schedule_message_relevant(message, history):
            result = manage_schedule_message(owner, message, request_id, history, cancelled)
        snapshot = schedule_snapshot(owner)
        context = "\n【本轮日程执行事实】\n" + json.dumps(
            {"calendar": snapshot, "current_request_id": request_id, "this_turn_result": result}, ensure_ascii=False)
        context += "\n只以本轮实际保存字段为准；旧轮次结果不是本轮操作。没有changes不得声称修改成功。"
        return ScheduleContext(context, result["reply"] if result and result.get("changes") else None)

    except Exception as exc:
        record_event(None, "schedule_chat_error", "", {"error_type": type(exc).__name__})
        return ScheduleContext("\n本轮日程操作失败，没有保存变更。", "本轮日程未保存，请重试或到日程页手动修改。")


class ScheduleEditPayload(BaseModel):
    operation: Dict[str, Any]
    request_id: str = Field(min_length=8, max_length=100)


class ScheduleChatPayload(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    request_id: str = Field(min_length=8, max_length=100)


def linked_schedule_memory(memory_id):
    with connect_db() as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='schedule_memory_links'").fetchone():
            return None
        row = conn.execute("""SELECT e.* FROM schedule_events e JOIN schedule_memory_links l ON l.event_id=e.id
                              WHERE l.memory_id=?""", (memory_id,)).fetchone()
    return (row["owner"], ScheduleStore.event(row)) if row else None


def update_schedule_from_memory(memory_id, content, importance_label, timeline_at=None,
                                timeline_start_at=None, timeline_end_at=None, timeline_kind=None, visitor_ip=None):
    linked = linked_schedule_memory(memory_id)
    if not linked:
        return None
    owner, event = linked
    if visitor_ip is not None and visitor_ip not in shared_user_device_ids(owner):
        raise HTTPException(status_code=409, detail="关联日程不能转移到其他用户")
    with connect_db() as conn:
        current = conn.execute("SELECT * FROM curated_memories WHERE id=?", (memory_id,)).fetchone()
    supplied = {"timeline_at": timeline_at, "timeline_start_at": timeline_start_at,
                "timeline_end_at": timeline_end_at, "timeline_kind": timeline_kind}
    changed_times = {key: value for key, value in supplied.items() if value is not None and (value or "") != (current[key] or "")}
    if content.strip() == current["content"] and not changed_times and importance_label == current["importance_label"]:
        return True
    decision = schedule_agent_decision({"now": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "today": schedule_today(), "events": [event], "history": [],
        "message": "用户正在记忆后台编辑此关联日程。将下面新记忆内容与显式修改的时间字段同步到这一条日程，保留其他未改字段。只能返回一个update操作，不得创建新事项。\n" +
            json.dumps({"new_content": content, "changed_time_fields": changed_times, "label": importance_label}, ensure_ascii=False)})
    operations = decision["operations"]
    if len(operations) != 1 or operations[0].get("action") != "update" or operations[0].get("id") != event["id"]:
        raise HTTPException(status_code=409, detail="无法将这次记忆修改明确同步到日程，请在日程页修改该事项")
    operations[0]["revision"] = event["revision"]
    schedule_store().apply(owner, operations, "memory-edit-" + uuid.uuid4().hex, content, decision["reply"])
    return True


def delete_schedule_from_memory(memory_id):
    linked = linked_schedule_memory(memory_id)
    if not linked:
        return None
    owner, event = linked
    schedule_store().apply(owner, [{"action": "delete", "id": event["id"], "revision": event["revision"]}],
                           "memory-delete-" + uuid.uuid4().hex, "在记忆后台删除关联日程")
    return True


def refresh_schedule_memory_indexes():
    """A durable retry queue; text and timeline already committed with the calendar."""
    with connect_db() as conn:
        queued = conn.execute("SELECT * FROM schedule_memory_index_queue ORDER BY updated_at LIMIT 16").fetchall()
    completed = 0
    for item in queued:
        vector = vector_memory.normalize_vector(embedding_client.embed_text(item["content"]))
        with connect_db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            current = conn.execute("""SELECT q.content FROM schedule_memory_index_queue q JOIN curated_memories m ON m.id=q.memory_id
                WHERE q.memory_id=? AND q.content=? AND m.content=q.content""", (item["memory_id"], item["content"])).fetchone()
            if not current:
                continue
            conn.execute("""INSERT INTO curated_memory_vectors (memory_id,dim,vector,model_name,created_at) VALUES (?,?,?,?,?)
                ON CONFLICT(memory_id) DO UPDATE SET dim=excluded.dim,vector=excluded.vector,model_name=excluded.model_name,created_at=excluded.created_at""",
                (item["memory_id"], int(vector.shape[0]), vector.tobytes(), embedding_client.EMBEDDING_MODEL, utc_now()))
            conn.execute("DELETE FROM schedule_memory_index_queue WHERE memory_id=? AND content=?", (item["memory_id"], item["content"]))
            completed += 1
    return completed


def rollover_schedule_memories():
    store = schedule_store()
    with connect_db() as conn:
        rows = conn.execute("""SELECT e.*,m.timeline_at FROM schedule_events e JOIN schedule_memory_links l ON l.event_id=e.id
            JOIN curated_memories m ON m.id=l.memory_id""").fetchall()
        for row in rows:
            event = ScheduleStore.event(row)
            if event.get("repeat") == "weekly" and event["status"] != "cancelled":
                if (row["timeline_at"] or "") != (memory_projection(event)["start"] or ""):
                    store.synchronizer.apply(conn, row["owner"], [{"action": "update", "event": event}])


def run_schedule_memory_maintenance(stop_event):
    while not stop_event.is_set():
        try:
            rollover_schedule_memories()
            refresh_schedule_memory_indexes()
        except Exception as exc:
            record_event(None, "schedule_memory_index_retry", "", {"error_type": type(exc).__name__})
        stop_event.wait(15)
