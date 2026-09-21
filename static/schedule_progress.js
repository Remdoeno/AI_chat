/* Long-running event presentation and milestone editor; persistence stays in schedule.js. */
window.ScheduleProgress = (() => {
  const el = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; };
  const btn = (text, action, cls) => { const n = el('button', text, cls); n.type = 'button'; n.addEventListener('click', action); return n; };
  const stages = event => event.milestones || [];
  const percent = event => stages(event).length ? Math.round(stages(event).filter(s => s.done).length / stages(event).length * 100) : 0;
  function overdue(stage) {
    if (stage.done || !stage.date) return false;
    return Date.now() > new Date(`${stage.date}T${stage.time || '23:59'}:59+08:00`).getTime();
  }
  function summary(event, day) {
    const wrap = el('span', undefined, 'project-summary');
    wrap.append(el('span', `${percent(event)}% · ${stages(event).filter(s => s.done).length}/${stages(event).length} 阶段完成`));
    const due = stages(event).filter(s => s.date === day);
    due.forEach(s => wrap.append(el('span', `${s.done ? '✓ 已完成' : 'DDL'} ${s.time || ''} ${s.title}`, overdue(s) ? 'deadline-overdue' : '')));
    return wrap;
  }
  function timeline(target, snapshot, openEvent, selectDay, addDays) {
    target.replaceChildren();
    const projects = snapshot.items.filter(e => e.kind === 'project' && e.date);
    target.hidden = !projects.length;
    if (!projects.length) return;
    target.append(el('h2', '长期事项进度', 'progress-heading'));
    const scroll = el('div', undefined, 'timeline-scroll');
    const grid = el('div', undefined, 'project-timeline');
    for (let i = 0; i < 14; i++) {
      const d = addDays(snapshot.today, i), b = btn(d.slice(5), () => selectDay(d), 'timeline-date');
      b.style.gridColumn = String(i + 1); b.style.gridRow = '1'; grid.append(b);
    }
    projects.forEach((p, i) => {
      const start = Math.max(0, Math.round((new Date(p.date) - new Date(snapshot.today)) / 86400000));
      const end = Math.min(13, Math.round((new Date(p.end_date || p.date) - new Date(snapshot.today)) / 86400000));
      const bar = btn(`${p.title} · ${percent(p)}%`, () => openEvent(p), `project-bar ${p.status}`);
      bar.style.gridColumn = `${start + 1} / ${end + 2}`; bar.style.gridRow = String(i + 2);
      bar.style.setProperty('--progress', `${percent(p)}%`);
      const color = snapshot.categories.find(c => c.id === p.category)?.color || '#6862b8';
      bar.style.setProperty('--project-color', color);
      bar.title = `${p.title} · ${p.date} 至 ${p.end_date} · ${percent(p)}%完成`;
      bar.setAttribute('aria-label', bar.title + '，点击查看阶段和DDL'); grid.append(bar);
    });
    scroll.append(grid); target.append(scroll, el('p', '横条表示持续区间，填充表示已完成阶段比例；点日期查看当天DDL。', 'muted form-help'));
  }
  function initEditor(form) {
    const box = document.getElementById('milestoneRows');
    const kind = form.elements.kind;
    function update() {
      const active = kind.value === 'project';
      document.getElementById('progressEditor').hidden = !active;
      form.elements.repeat.disabled = active;
      if (active) form.elements.repeat.value = 'none';
      box.querySelectorAll('[data-stage-title]').forEach(n => n.required = active);
    }
    function row(stage = {}) {
      const r = el('div', undefined, 'milestone-row');r.dataset.id = stage.id || '';
      const input = (key, type, value, label) => {
        const l = el('label', label), n = el('input'); n.type = type; n.dataset.stage = key;
        if (type === 'checkbox') n.checked = Boolean(value); else n.value = value || '';
        l.append(n); r.append(l); return n;
      };
      input('done', 'checkbox', stage.done, '完成');
      const title = input('title', 'text', stage.title, '阶段名称');title.maxLength = 120;title.dataset.stageTitle = '';title.required = true;
      input('date', 'date', stage.date, '截止日期');input('time', 'time', stage.time, '时间 可选');
      const note = input('notes', 'text', stage.notes, '阶段备注');note.maxLength = 500;
      const actions = el('div', undefined, 'stage-actions');
      actions.append(btn('上移', () => { if (r.previousElementSibling) box.insertBefore(r, r.previousElementSibling); }), btn('移除', () => { if (window.confirm('移除这个阶段？保存后生效。')) r.remove(); }));
      r.append(actions); box.append(r);update();
    }
    kind.addEventListener('change', update);
    document.getElementById('addMilestone').addEventListener('click', () => { if (box.children.length < 30) row(); });
    document.getElementById('travelMilestones').addEventListener('click', () => {
      if (box.children.length && !window.confirm('用旅行模板替换当前阶段？日期和完成状态会重置，保存后生效。')) return;
      box.replaceChildren(); ['定行程', '买票', '收拾行李', '购买物资', '正式出行'].forEach(title => row({ title }));
      form.elements.category.value = 'travel';
    });
    return {
      load(event) { box.replaceChildren();kind.value = event?.kind || 'event';stages(event || {}).forEach(row);update(); },
      read() { return {kind: kind.value, milestones: kind.value === 'project' ? [...box.children].map(r => {
        const s = {};if (r.dataset.id) s.id = r.dataset.id;
        r.querySelectorAll('[data-stage]').forEach(n => s[n.dataset.stage] = n.type === 'checkbox' ? n.checked : n.value);
        return s;
      }) : []}; },
    };
  }
  return { timeline, initEditor, summary };
})();
