"""Pure, stable milestone ordering within independent project tracks."""


def order_stages(stages):
    groups = {}
    by_id = {s['id']: s for s in stages}
    for stage in stages:
        dependencies = stage.get('depends_on', [])
        if not isinstance(dependencies, list) or any(not isinstance(i, str) for i in dependencies):
            raise ValueError('前置阶段必须是阶段ID数组')
        if len(dependencies) != len(set(dependencies)):
            raise ValueError('前置阶段不能重复')
        for identifier in dependencies:
            if identifier not in by_id or identifier == stage['id']:
                raise ValueError('前置阶段不存在或指向自身')
            if by_id[identifier].get('track', '') != stage.get('track', ''):
                raise ValueError('独立子任务路线不能互相串联，请调整路线或前置阶段')
        groups.setdefault(stage.get('track', ''), []).append(stage)
    ordered = []
    for group in groups.values():
        remaining = list(enumerate(group))
        emitted = set()
        while remaining:
            ready = [(index, stage) for index, stage in remaining
                     if all(i in emitted for i in stage.get('depends_on', []))]
            if not ready:
                raise ValueError('阶段前后关系形成循环，请调整前置阶段')
            # Timed entries follow their actual start; undated/tied entries stay stable.
            chosen = min(ready, key=lambda pair: (
                pair[1].get('start_date') or pair[1].get('date') or '9999-99-99',
                pair[1].get('time') or '23:59', pair[0]))
            remaining.remove(chosen)
            ordered.append(chosen[1])
            emitted.add(chosen[1]['id'])
    return ordered
