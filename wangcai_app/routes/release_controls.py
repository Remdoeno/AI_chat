"""Authenticated, tenant-isolated release controls. Models use saved credentials only."""
def release_control_owner(request, scope):
    if scope == 'system':
        require_admin(request)
        return ''
    if scope != 'user':
        raise HTTPException(status_code=400, detail='配置范围不正确')
    return require_shared_user_for_request(request)


@app.get('/api/release-features')
def get_release_features(request: Request, scope: str = 'user'):
    owner = release_control_owner(request, scope)
    return release_feature_store().public(owner)


@app.put('/api/release-features')
async def update_release_features(request: Request, scope: str = 'user'):
    owner = release_control_owner(request, scope)
    payload = await request.json()
    if not isinstance(payload, dict) or set(payload) - {'changes', 'expected_owner'}:
        raise HTTPException(status_code=422, detail='更新项目格式不正确')
    if payload.get('expected_owner') != owner:
        raise HTTPException(status_code=409, detail='用户已改变，请重新打开设置')
    try:
        return release_feature_store().save(owner, payload.get('changes'))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post('/api/model-settings/probe')
async def probe_saved_model(request: Request, scope: str = 'user'):
    owner = release_control_owner(request, scope)
    payload = await request.json()
    if not isinstance(payload, dict) or set(payload) - {'slot', 'expected_owner'} or payload.get('slot') not in {'chat', 'background'}:
        raise HTTPException(status_code=422, detail='仅可诊断已保存的台前或后台模型')
    if payload.get('expected_owner') != owner:
        raise HTTPException(status_code=409, detail='用户已改变，请重新打开设置')
    if not release_feature_store().values(owner)['model_probe']:
        raise HTTPException(status_code=409, detail='模型诊断已回滚，可在体验与回滚中重新开启')
    def probe():
        with model_owner_scope(owner):
            slot = model_slot_config(payload['slot'])
            started = time.perf_counter()
            http_client = None
            try:
                client, http_client, _ = configured_model_client(slot, 20, task=payload['slot'])
                response = client.chat.completions.create(**model_completion_kwargs(slot),
                    messages=[{'role': 'user', 'content': '请仅回复 OK。'}],
                    max_tokens=model_output_token_limit(slot, 128))
                answer = completion_message_text(response.choices[0].message).strip()
                return {'ok': bool(answer), 'model': slot['model'], 'slot': payload['slot'],
                        'seconds': round(time.perf_counter() - started, 2), 'answer_chars': len(answer),
                        'message': '模型已返回正文' if answer else '模型未返回正文'}
            except Exception as exc:
                error = friendly_error(exc)
                return {'ok': False, 'slot': payload['slot'], 'seconds': round(time.perf_counter() - started, 2),
                        'code': error.code, 'message': str(error)}
            finally:
                if http_client:
                    http_client.close()
    return await asyncio.to_thread(probe)
