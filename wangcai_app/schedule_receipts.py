"""Pure calendar mutation checks and factual confirmations from committed changes."""
import re
from copy import deepcopy
from datetime import date, timedelta


class ScheduleContext(str):
    def __new__(cls, context, reply=None):
        value = super().__new__(cls, context)
        value.reply = reply
        return value


def saved_reply(changes, proposed=''):
    if not changes:
        if re.search(r'已.{0,8}(?:改|更新|保存|添加|记录|取消|删除|调整)', proposed):
            return '本轮没有保存日程变更。请补充要修改的事项与时间，或在日程页核对。'
        return proposed
    lines = []
    for change in changes:
        e = change['event']
        action = '已删除' if change['action'] == 'delete' else '已取消' if e['status'] == 'cancelled' else '已保存'
        when = e.get('date') or '日期待定'
        if e.get('repeat') == 'weekly' and e.get('date'):
            when = '每周' + '一二三四五六日'[date.fromisoformat(e['date']).weekday()]
        elif e.get('end_date') and e['end_date'] != e.get('date'):
            when += ' 至 ' + e['end_date']
        hours = e.get('time') or '时间待定'
        if e.get('end_time'):
            hours += '–' + e['end_time']
        lines.append(f"{action}：{e['title']} · {when} {hours}" + ('（整个系列）' if e.get('repeat') == 'weekly' else ''))
    return '\n'.join(lines)


def align_weekly_updates(operations, events, message, today):
    # Only an explicit target weekday, not a queried weekday or a past anecdote.
    matches = re.findall(r'(?:改回|改到|改成|改为|调整到|调整为|调整成|变成)\s*(?:每)?(?:周|星期)([一二三四五六日天])', message)
    if len(set(matches)) != 1:
        return operations
    target = '一二三四五六日'.index(matches[0].replace('天', '日'))
    by_id = {e['id']: e for e in events}
    candidates = [op for op in operations if op.get('action') == 'update' and by_id.get(op.get('id'), {}).get('repeat') == 'weekly']
    if len(candidates) != 1:
        return operations
    if re.search(r'仅这次|只.{0,3}(?:本周|这周|这次|一次)|本次', message):
        raise ValueError('单次改期不能修改每周系列，请在日程中确认修改范围')
    result = deepcopy(operations)
    for op in result:
        if op.get('id') != candidates[0].get('id') or op.get('action') != 'update':
            continue
        current = by_id[op['id']]
        patch = op.setdefault('event', {})
        if patch.get('repeat', 'weekly') != 'weekly':
            continue
        old = date.fromisoformat(patch.get('date') or current['date'])
        if old.weekday() != target:
            start = date.fromisoformat(today)
            patch['date'] = (start + timedelta(days=(target-start.weekday()) % 7)).isoformat()
            if patch.get('end_date', current.get('end_date')):
                patch['end_date'] = patch['date']
        note = patch.get('notes', current.get('notes', ''))
        # Replace only the fixed recurrence sentence; dated historical notes survive.
        note = re.sub(r'每周[一二三四五六日天][^。；\n]*[。；]?', '', note).strip()
        merged = {**current, **patch}
        hours = (merged.get('time') or '') + ('–'+merged['end_time'] if merged.get('end_time') else '')
        patch['notes'] = f"每周{matches[0]} {hours} 固定安排。" + note
    return result
