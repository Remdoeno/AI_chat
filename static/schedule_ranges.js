/* Calendar range layout. Dates and records remain owned by the schedule store. */
window.ScheduleRanges = (() => {
  const isRange = e => Boolean(e.date && e.end_date && e.end_date > e.date);
  function continuation(card, start, end, visibleStart, visibleEnd = visibleStart) {
    const left = Boolean(start && start < visibleStart), right = Boolean(end && end > visibleEnd);
    card.classList.toggle('continues-left', left);card.classList.toggle('continues-right', right);
    if (card.dataset.rangeLabel === undefined) card.dataset.rangeLabel = card.title || card.textContent;
    const text = [left ? '由前日延续' : '', right ? '延续至后日' : ''].filter(Boolean).join('，');
    card.title = card.dataset.rangeLabel + (text ? `（${text}）` : '');
    card.setAttribute('aria-label', card.title);
    return card;
  }
  function entries(snapshot, mode) {
    const ordinary = snapshot.items.filter(e => e.kind !== 'project' && isRange(e)).map(event => ({
      start: event.date, end: event.end_date, key: event.id, event,
    }));
    if (mode !== 'single') return ordinary;
    return ordinary.concat(snapshot.items.filter(p => p.kind === 'project').flatMap(project => (project.milestones || []).map((stage,index) => ({stage,project,index})).filter(({stage}) => stage.start_date && stage.date > stage.start_date).map(item => ({
      ...item, start:item.stage.start_date, end:item.stage.date, key:`${item.project.id}:${item.stage.id}`,
    }))));
  }
  function render(grid, snapshot, mode, eventCard, openProject) {
    grid.querySelectorAll('.calendar-range,.range-reserve').forEach(n => n.remove());
    const cells = [...grid.querySelectorAll('.day-cell')], ranges = entries(snapshot, mode);
    for (let row=0;row<2;row++) {
      const days = cells.slice(row*7,row*7+7);if (!days.length) continue;
      const first=days[0].dataset.date,last=days[6].dataset.date;
      const segments=ranges.filter(r => r.start <= last && r.end >= first).map(r => ({...r,
        left:Math.max(0, days.findIndex(c => c.dataset.date >= r.start)),
        right:Math.min(6, r.end >= last ? 6 : days.findIndex(c => c.dataset.date === r.end)),
      })).sort((a,b) => a.left-b.left || b.right-a.right || a.key.localeCompare(b.key));
      const lanes=[];
      segments.forEach(s => {
        let lane=lanes.findIndex(end => end < s.left);if (lane < 0) lane=lanes.length;
        lanes[lane]=s.right;
        const bar=s.event ? eventCard(s.event, first) : ScheduleProgress.nodeCard(s,openProject);
        bar.classList.add('calendar-range');bar.dataset.rangeRow=row;bar.dataset.rangeLane=lane;
        bar.dataset.rangeLeft=s.left;bar.dataset.rangeRight=s.right;bar.dataset.anchorDate=days[s.left].dataset.date;
        continuation(bar,s.start,s.end,days[s.left].dataset.date,days[s.right].dataset.date);
        grid.append(bar);
      });
      if (lanes.length) days.forEach(cell => {
        const reserve=document.createElement('div');reserve.className='range-reserve';reserve.style.height=`${lanes.length*48+4}px`;
        cell.querySelector('.day-heading').after(reserve);
      });
    }
    position(grid);
  }
  function position(grid) {
    if (!grid.clientWidth) return;
    const cells=[...grid.querySelectorAll('.day-cell')];
    for (let row=0;row<2;row++) {
      const days=cells.slice(row*7,row*7+7);if (!days.some(c => c.querySelector('.range-reserve'))) continue;
      const headings=days.map(c => c.querySelector('.day-heading'));
      const height=Math.max(...headings.map(h => h.getBoundingClientRect().height));
      headings.forEach(h => { if (h.getBoundingClientRect().height < height-.5) h.style.minHeight=`${height}px`; });
    }
    const bounds=grid.getBoundingClientRect();
    grid.querySelectorAll('.calendar-range').forEach(bar => {
      const row=Number(bar.dataset.rangeRow),left=cells[row*7+Number(bar.dataset.rangeLeft)],right=cells[row*7+Number(bar.dataset.rangeRight)];
      const reserve=left?.querySelector('.range-reserve');if (!reserve || !right) return;
      const a=left.getBoundingClientRect(),b=right.getBoundingClientRect();
      bar.style.left=`${a.left-bounds.left+4}px`;bar.style.width=`${b.right-a.left-8}px`;
      bar.style.top=`${reserve.getBoundingClientRect().top-bounds.top+Number(bar.dataset.rangeLane)*48}px`;
    });
  }
  return {isRange,continuation,render,position};
})();
