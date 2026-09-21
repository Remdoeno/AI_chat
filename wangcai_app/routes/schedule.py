@app.get("/schedule", include_in_schema=False)
def schedule_page():
    return html_response("schedule.html")


@app.get("/api/schedule")
def get_schedule(request: Request, start: str = ""):
    from datetime import date, timedelta
    owner = require_shared_user_for_request(request)
    today = schedule_today()
    if not start:
        return {**schedule_snapshot(owner), "actual_today": today}
    try:
        parsed = date.fromisoformat(start)
        if parsed.isoformat() != start:
            raise ValueError("Use ISO date")
        parsed + timedelta(days=13)
    except (ValueError, OverflowError):
        raise HTTPException(status_code=422, detail="日历开始日期不正确")
    return {"owner": owner, **calendar_window(schedule_store().list(owner), start),
            "actual_today": today, "holidays": holiday_calendar().window(start),
            "categories": [{"id": key, "label": value[0], "color": value[1]} for key, value in CATEGORIES.items()]}


@app.post("/api/schedule/events")
def edit_schedule(payload: ScheduleEditPayload, request: Request):
    owner = require_shared_user_for_request(request)
    try:
        return schedule_store().apply(owner, [payload.operation], payload.request_id, "日历手动编辑")
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.post("/api/schedule/chat")
def schedule_chat(payload: ScheduleChatPayload, request: Request):
    owner = require_shared_user_for_request(request)
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="请输入日程信息")
    cached = schedule_store().cached(owner, payload.request_id)
    if cached:
        return cached
    rate_limit = check_chat_device_rate_limit(visitor_ip(request))
    if not rate_limit["allowed"]:
        raise HTTPException(status_code=429, detail="消息太密了，请稍后重试")
    try:
        return manage_schedule_message(owner, payload.message.strip(), payload.request_id)
    except (ValueError, LookupError, TypeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=502, detail="旺财暂时未能解析日程，未保存变更。请重试或手动编辑。")
