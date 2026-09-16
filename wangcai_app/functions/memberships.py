"""App adapter for member-card storage, chat commands, and quiet home hints."""
from wangcai_app.memberships import MembershipStore, next_month, daily_hint
from wangcai_app.membership_memory import MembershipMemoryBridge
from wangcai_app.prompts.memberships import MEMBERSHIP_AGENT_PROMPT


def membership_store():
    return MembershipStore(connect_db, MembershipMemoryBridge(opening_prompt_cache_key))


def membership_preferences(owner):
    try:
        value = json.loads(get_app_setting('membership_preferences:' + owner, '{}'))
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def membership_snapshot(owner):
    cards = membership_store().list(owner)
    preferences = membership_preferences(owner)
    today = schedule_today()
    return {'owner': owner, 'cards': cards, 'preferences': preferences,
            'hint': daily_hint(cards, today, preferences), 'today': today}


def membership_agent_decision(context):
    client, http_client, slot = openai_client_for_slot(MODEL_SLOT_BACKGROUND, timeout=45)
    try:
        response = client.chat.completions.create(**model_completion_kwargs(slot),
            messages=[{'role': 'system', 'content': MEMBERSHIP_AGENT_PROMPT},
                      {'role': 'user', 'content': json.dumps(context, ensure_ascii=False)}],
            temperature=0.1, max_tokens=model_output_token_limit(slot, 4096))
        _, answer = split_think_text(response.choices[0].message.content or '')
        decision = json.loads(re.sub(r'^```(?:json)?\s*|\s*```$', '', answer.strip()))
        if not isinstance(decision, dict) or not isinstance(decision.get('operations'), list) or not isinstance(decision.get('reply'), str):
            raise ValueError('会员卡解析不完整，请重试或在卡包编辑')
        return decision
    finally:
        http_client.close()


@scoped_model_call(lambda owner, *args, **kwargs: owner)
def manage_membership_message(owner, message, request_id, history=None, cancelled=lambda: False):
    store = membership_store()
    cached = store.cached(owner, request_id)
    if cached:
        return cached
    cards = store.list(owner)
    if len(cards) > 300:
        raise ValueError('卡片较多，请到会员卡包编辑具体卡片')
    decision = membership_agent_decision({'now': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
        'cards': cards, 'message': message, 'history': history if history is not None else store.history(owner)})
    return store.apply(owner, decision['operations'], request_id, message, decision['reply'][:3000], cancelled)


def membership_context_for_chat(owner, message, request_id, history, cancelled):
    if not owner:
        return '\n会员卡需要先绑定用户；未绑定时不可声称已保存卡片。'
    markers = r'会员卡|会员余额|储值卡|次卡|卡包|余额|剩余次数|充值|归属地|还剩|用完|剩下.*(?:元|块|次)'
    cards = membership_store().list(owner)
    names = {card['name'] for card in cards}
    names.update(re.split(r'冰激凌|盲人按摩|会员卡|储值卡|KTV|ktv', card['name'])[0].strip() for card in cards)
    named = any(len(name) >= 2 and name in message for name in names)
    related = re.search(markers, message) or named or (re.search(r'用了|用完|还剩|改|删除|暂停|恢复|那张|这张', message) and any(re.search(markers, str(item.get('content', ''))) for item in history[-6:]))
    if not related:
        return '\n会员卡采用首页轻提示方案。用户未问卡包时，不主动在聊天开场或回复中提醒消费。'
    try:
        result = manage_membership_message(owner, message, request_id, history, cancelled)
        return '\n【会员卡数据库事实，以此为准】\n' + json.dumps({'cards': membership_store().list(owner), 'this_turn_result': result}, ensure_ascii=False) + '\n仅changes列出的改动已保存并同步记忆。未保存不可声称记下。不要自行扣款扣次数。'
    except Exception as exc:
        record_event(None, 'membership_chat_error', '', {'error_type': type(exc).__name__})
        return '\n本轮会员卡操作失败，不能声称已保存；请明确让用户重试或到卡包编辑。'


def linked_membership_memory(memory_id):
    with connect_db() as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='membership_memory_links'").fetchone():
            return None
        row = conn.execute('SELECT c.* FROM membership_cards c JOIN membership_memory_links l ON l.card_id=c.id WHERE l.memory_id=?', (memory_id,)).fetchone()
    return (row['owner'], MembershipStore.card(row)) if row else None


def update_membership_from_memory(memory_id, content, visitor_ip=None):
    linked = linked_membership_memory(memory_id)
    if not linked:
        return None
    owner, card = linked
    if visitor_ip is not None and visitor_ip not in shared_user_device_ids(owner):
        raise HTTPException(status_code=409, detail='关联会员卡不能转移给其他用户')
    decision = membership_agent_decision({'now': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(), 'cards': [card], 'history': [],
        'message': '用户在记忆后台编辑这张会员卡。将新内容同步到这一张卡，保留未改变字段，只返回一个update操作：' + content})
    operations = decision['operations']
    if len(operations) != 1 or operations[0].get('action') != 'update' or operations[0].get('id') != card['id']:
        raise HTTPException(status_code=409, detail='无法明确同步，请在会员卡包编辑')
    operations[0]['revision'] = card['revision']
    membership_store().apply(owner, operations, 'memory-card-' + uuid.uuid4().hex, content, decision['reply'])
    return True


def delete_membership_from_memory(memory_id):
    linked = linked_membership_memory(memory_id)
    if not linked:
        return None
    owner, card = linked
    membership_store().apply(owner, [{'action': 'delete', 'id': card['id'], 'revision': card['revision']}],
                             'memory-card-delete-' + uuid.uuid4().hex, '在记忆后台删除关联会员卡')
    return True


class MembershipEditPayload(BaseModel):
    operation: Dict[str, Any]
    request_id: str = Field(min_length=8, max_length=100)


class MembershipChatPayload(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    request_id: str = Field(min_length=8, max_length=100)


class MembershipPreferencePayload(BaseModel):
    action: str
