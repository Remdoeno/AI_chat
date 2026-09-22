"""Validation of long-running schedule entries and their user-defined milestones."""
import uuid
from wangcai_app.schedule_order import order_stages
from datetime import date, datetime


def normalize_progress(data, event):
    kind = data.get('kind') or 'event'
    stages = data.get('milestones', [])
    if kind not in {'event', 'project'}:
        raise ValueError('未知事项类型')
    if not isinstance(stages, list) or len(stages) > 30:
        raise ValueError('最多设置30个阶段')
    if kind == 'event':
        if stages:
            raise ValueError('普通事项不能包含阶段，请选择长期事项')
        return {'kind': kind, 'milestones': []}
    if event['repeat'] != 'none':
        raise ValueError('长期事项暂不支持每周重复')
    if bool(event['date']) != bool(event['end_date']):
        raise ValueError('请同时填写长期事项的开始和结束日期，或都留空')
    normalized, ids = [], set()
    for stage in stages:
        if not isinstance(stage, dict) or set(stage) - {'id', 'title', 'date', 'time', 'done', 'notes', 'start_date', 'important', 'tentative', 'track', 'depends_on'}:
            raise ValueError('阶段字段不正确')
        item = {key: stage.get(key, '') for key in ('title', 'date', 'time', 'notes', 'start_date', 'track')}
        if not all(isinstance(v, str) for v in item.values()):
            raise ValueError('阶段名称、日期与备注必须是文字')
        item = {key: value.strip() for key, value in item.items()}
        if len(item['track']) > 80:
            raise ValueError('子任务路线名称最多80字')
        if not item['title'] or len(item['title']) > 120 or len(item['notes']) > 500:
            raise ValueError('阶段名称需为1–120字，备注最多500字')
        if item['date'] and date.fromisoformat(item['date']).isoformat() != item['date']:
            raise ValueError('阶段日期格式应为YYYY-MM-DD')
        if item['time'] and (not item['date'] or datetime.strptime(item['time'], '%H:%M').strftime('%H:%M') != item['time']):
            raise ValueError('阶段时间需为HH:MM，且先填写日期')
        if event['date'] and item['date'] and not event['date'] <= item['date'] <= event['end_date']:
            raise ValueError('阶段DDL需在长期事项开始与结束日期之间，请同时调整范围')
        if item['start_date']:
            if not item['date'] or date.fromisoformat(item['start_date']).isoformat() != item['start_date'] or item['start_date'] > item['date']:
                raise ValueError('阶段开始日期需有效且不晚于截止日期')
            if event['date'] and item['start_date'] < event['date']:
                raise ValueError('阶段开始日期不能早于项目范围')
        for flag in ('important', 'tentative'):
            item[flag] = stage.get(flag, False)
            if not isinstance(item[flag], bool):
                raise ValueError('节点标记必须为true或false')
        item['done'] = stage.get('done', False)
        if not isinstance(item['done'], bool):
            raise ValueError('阶段完成状态必须为true或false')
        identifier = stage.get('id') or uuid.uuid4().hex
        if not isinstance(identifier, str) or len(identifier) > 64 or identifier in ids:
            raise ValueError('阶段ID不正确或重复')
        ids.add(identifier)
        normalized.append({**item, 'id': identifier, 'depends_on': stage.get('depends_on', [])})
    return {'kind': kind, 'milestones': order_stages(normalized)}


def preserve_stage_tracks(patch, current):
    """Missing group fields preserve membership; an explicit empty string clears it."""
    if not current or not isinstance(patch.get('milestones'), list):
        return patch
    previous = {s['id']: s for s in current.get('milestones', [])}
    retained_ids = {s.get('id') for s in patch['milestones'] if isinstance(s, dict)}
    stages = []
    for stage in patch['milestones']:
        if isinstance(stage, dict):
            old = previous.get(stage.get('id'), {})
            stage = dict(stage)
            stage.setdefault('track', old.get('track', ''))
            # Removed predecessors and regrouped nodes must not leave dangling links.
            if 'depends_on' not in stage:
                tracks = {s.get('id'): s.get('track', previous.get(s.get('id'), {}).get('track', ''))
                          for s in patch['milestones'] if isinstance(s, dict)}
                stage['depends_on'] = [i for i in old.get('depends_on', [])
                                       if i in retained_ids and tracks[i] == stage['track']]
        stages.append(stage)
    return {**patch, 'milestones': stages}
