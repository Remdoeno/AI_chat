@app.get('/memberships', include_in_schema=False)
def memberships_page():
    return html_response('memberships.html')


@app.get('/api/memberships')
def get_memberships(request: Request):
    return membership_snapshot(require_shared_user_for_request(request))


@app.post('/api/memberships/cards')
def edit_membership(payload: MembershipEditPayload, request: Request):
    owner = require_shared_user_for_request(request)
    try:
        return membership_store().apply(owner, [payload.operation], payload.request_id, '卡包手动编辑')
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.post('/api/memberships/chat')
def membership_chat(payload: MembershipChatPayload, request: Request):
    owner = require_shared_user_for_request(request)
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail='请输入会员卡信息')
    cached = membership_store().cached(owner, payload.request_id)
    if cached:
        return cached
    if not check_chat_device_rate_limit(visitor_ip(request))['allowed']:
        raise HTTPException(status_code=429, detail='消息太密了，请稍后重试')
    try:
        return manage_membership_message(owner, payload.message.strip(), payload.request_id)
    except (ValueError, LookupError, TypeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=502, detail='会员卡未能解析或保存，请重试或手动编辑')


@app.post('/api/memberships/preferences')
def edit_membership_preferences(payload: MembershipPreferencePayload, request: Request):
    owner = require_shared_user_for_request(request)
    patches = {'collapse': {'collapsed': True}, 'expand': {'collapsed': False},
               'snooze': {'snooze_until': next_month(schedule_today())}, 'resume': {'snooze_until': '', 'dismissed_on': ''},
               'dismiss_today': {'dismissed_on': schedule_today()}}
    if payload.action not in patches:
        raise HTTPException(status_code=400, detail='未知提示设置')
    with connect_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        key = 'membership_preferences:' + owner
        row = conn.execute('SELECT value FROM app_settings WHERE key=?', (key,)).fetchone()
        value = json.loads(row[0]) if row else {}
        value.update(patches[payload.action])
        conn.execute('INSERT INTO app_settings VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at',
                     (key, json.dumps(value), utc_now()))
    return membership_snapshot(owner)
