/* Long-running event presentation and milestone editor; persistence stays in schedule.js. */
window.ScheduleProgress = (() => {
  const el = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; };
  const btn = (text, action, cls) => { const n = el('button', text, cls); n.type = 'button'; n.addEventListener('click', action); return n; };
  const stages = event => event.milestones || [];
  const percent = event => stages(event).length ? Math.round(stages(event).filter(s => s.done).length / stages(event).length * 100) : 0;
  const color = event => ScheduleColors.color(event);
  const range = stage => !stage.date ? '日期待定' : `${stage.start_date && stage.start_date !== stage.date ? stage.start_date.slice(5) + ' — ' : ''}${stage.date.slice(5)}${stage.time ? ' ' + stage.time : ''}${stage.tentative ? ' · 待定窗口' : ''}`;
  const activeOn = (s, day) => s.date && (s.start_date || s.date) <= day && s.date >= day;
  function overdue(stage) {
    if (stage.done || stage.tentative || !stage.date) return false;
    return Date.now() > new Date(`${stage.date}T${stage.time || '23:59'}:59+08:00`).getTime();
  }
  function summary(event, day) {
    const wrap = el('span', undefined, 'project-summary');
    wrap.append(el('span', `${percent(event)}% · ${stages(event).filter(s => s.done).length}/${stages(event).length} 阶段完成`));
    const due = stages(event).filter(s => activeOn(s, day));
    due.forEach(s => wrap.append(el('span', `${s.done ? '✓' : s.important ? '◆' : s.start_date && s.start_date !== s.date ? '进行阶段' : 'DDL'} ${s.title} · ${range(s)}`, overdue(s) ? 'deadline-overdue' : '')));
    return wrap;
  }
  function timeline(target, snapshot, openEvent, selectDay, addDays) {
    target.replaceChildren();
    const projects = snapshot.items.filter(e => e.kind === 'project' && e.date && e.date <= snapshot.end && (e.end_date || e.date) >= snapshot.today);
    target.hidden = !projects.length;
    if (!projects.length) return;
    target.append(el('h2', '长期事项进度', 'progress-heading'));
    const scroll = el('div', undefined, 'timeline-scroll');
    const grid = el('div', undefined, 'project-timeline');
    for (let i = 0; i < 14; i++) {
      const d = addDays(snapshot.today, i), b = el('span', d.slice(5), 'timeline-date');
      b.style.gridColumn = String(i + 1); b.style.gridRow = '1'; grid.append(b);
    }
    projects.forEach((p, i) => {
      const start = Math.max(0, Math.round((new Date(p.date) - new Date(snapshot.today)) / 86400000));
      const end = Math.min(13, Math.round((new Date(p.end_date || p.date) - new Date(snapshot.today)) / 86400000));
      const bar = btn(`▸ ${p.title} · ${percent(p)}%`, () => openEvent(p), `project-bar ${p.status}`);
      bar.style.gridColumn = `${start + 1} / ${end + 2}`; bar.style.gridRow = String(i + 2);
      bar.style.setProperty('--progress', `${percent(p)}%`);
      bar.style.setProperty('--project-color', color(p));
      bar.title = `${p.title} · ${p.date} 至 ${p.end_date} · ${percent(p)}%完成`;
      bar.setAttribute('aria-label', bar.title + '，点击查看阶段和DDL'); grid.append(bar);
    });
    scroll.append(grid); target.append(scroll, el('p', '横条表示持续区间，填充表示已完成阶段比例；点击长条查看横向阶段图。', 'muted form-help'));
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
      input('start_date', 'date', stage.start_date, '阶段开始 可选');
      input('date', 'date', stage.date, '节点日期 / 阶段结束');input('time', 'time', stage.time, '时间 可选');
      input('important', 'checkbox', stage.important, '重要节点');
      input('tentative', 'checkbox', stage.tentative, '日期待确认');
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
  function singleNodes(items, day, windowStart) {
    return items.filter(p => p.kind === 'project').flatMap(p => stages(p).map((s, index) => ({ project: p, stage: s, index })).filter(({stage}) => {
      const start = stage.start_date || stage.date;
      // Show a duration once, at its start or the visible window boundary.
      return start && stage.date >= windowStart && (start < windowStart ? windowStart : start) === day;
    }));
  }
  function nodeCard({project, stage, index}, open) {
    const card = btn('', () => open(project, stage.id), `event-card project-node${stage.done ? ' node-done' : ''}${stage.tentative ? ' tentative' : ''}`);
    card.style.setProperty('--event-color', color(project));card.dataset.project = project.id;card.dataset.stageIndex = index;
    card.append(el('span', `${stage.important ? '◆ 重要节点 · ' : ''}${range(stage)}`, 'event-time'), el('span', `${stage.done ? '✓ ' : ''}${stage.title}`, 'event-title'), el('span', project.title, 'event-meta'));
    if (overdue(stage)) card.append(el('span', '已逾期', 'deadline-overdue'));
    return card;
  }
  function details(project, focusId) {
    const content = el('div', undefined, 'project-detail-content');content.style.setProperty('--project-color', color(project));
    content.append(el('p', `${project.date || '日期待定'}${project.end_date ? ' 至 ' + project.end_date : ''} · ${percent(project)}% · ${stages(project).filter(s => s.done).length}/${stages(project).length}阶段完成`, 'muted'));
    if (project.notes) content.append(el('p', project.notes, 'project-notes'));
    const scroll = el('div', undefined, 'phase-diagram-scroll');
    const diagram = el('div', undefined, 'phase-diagram');
    diagram.setAttribute('role', 'list'); diagram.setAttribute('aria-label', '项目阶段时间轴');
    stages(project).forEach((s, index) => {
      const item = el('section', undefined, `project-phase${s.id === focusId ? ' phase-focus' : ''}`);
      item.setAttribute('role', 'listitem');
      item.append(el('span', s.done ? '✓' : s.important ? '◆' : String(index + 1), 'phase-marker'));
      item.append(el('p', range(s), overdue(s) ? 'deadline-overdue' : 'muted'));
      item.append(el('h3', s.title));
      if (s.start_date && s.start_date !== s.date) item.append(el('div', undefined, 'phase-duration'));
      if (s.notes) item.append(el('p', s.notes, 'phase-note'));
      item.append(el('p', s.done ? '已完成' : s.tentative ? '待确认' : '待完成', 'muted'));
      diagram.append(item);
    });
    scroll.append(diagram);content.append(scroll);
    if (!stages(project).length) content.append(el('p', '尚未添加阶段，点击编辑项目来补充。', 'muted'));
    return content;
  }
  const activeNodes = (items, day) => items.filter(p => p.kind === 'project').flatMap(project => stages(project).map((stage,index) => ({project,stage,index})).filter(({stage}) => activeOn(stage,day)));
  const undatedNodes = items => items.filter(p => p.kind === 'project').flatMap(project => stages(project).map((stage,index) => ({project,stage,index})).filter(({stage}) => !stage.date));
  return { timeline, initEditor, summary, singleNodes, activeNodes, undatedNodes, nodeCard, details, activeOn, color };

})();
