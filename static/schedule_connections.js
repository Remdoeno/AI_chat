/* SVG links are decorative and never intercept card/date clicks. */
window.ScheduleConnections = (() => {
  const NS = 'http://www.w3.org/2000/svg';
  function draw(grid) {
    grid.querySelector('.project-connections')?.remove();
    ScheduleRanges.position(grid);
    if (!grid.classList.contains('single-mode') || !grid.clientWidth) return;
    const svg = document.createElementNS(NS, 'svg');svg.classList.add('project-connections');
    svg.setAttribute('aria-hidden', 'true');svg.setAttribute('width', grid.scrollWidth);svg.setAttribute('height', grid.scrollHeight);
    const bounds = grid.getBoundingClientRect(), groups = new Map();
    grid.querySelectorAll('[data-project]').forEach(card => {
      if (!groups.has(card.dataset.project)) groups.set(card.dataset.project, []);
      groups.get(card.dataset.project).push(card);
    });
    const cellFor = card => card.closest('.day-cell') || grid.querySelector(`.day-cell[data-date="${card.dataset.anchorDate}"]`);
    groups.forEach(cards => {
      cards.sort((a,b) => Number(a.dataset.stageIndex)-Number(b.dataset.stageIndex) || (a.dataset.anchorDate || "").localeCompare(b.dataset.anchorDate || ""));
      for (let i=1;i<cards.length;i++) {
        if (cards[i-1].dataset.stageIndex === cards[i].dataset.stageIndex) continue;
        const a=cards[i-1].getBoundingClientRect(), b=cards[i].getBoundingClientRect();
        const ax=a.right-bounds.left, ay=a.top+a.height*.55-bounds.top;
        const bx=b.left-bounds.left, by=b.top+b.height*.55-bounds.top;
        const path=document.createElementNS(NS,'path');
        let d;
        if (cellFor(cards[i-1]) === cellFor(cards[i])) {
          const x=a.left-bounds.left+10, y=a.bottom-bounds.top, ty=b.top-bounds.top;
          d=`M ${x} ${y} C ${x-10} ${y+8}, ${x-10} ${ty-8}, ${x} ${ty}`;
        } else if (bx>ax) {
          const bend=Math.max(18,(bx-ax)*.45);d=`M ${ax} ${ay} C ${ax+bend} ${ay}, ${bx-bend} ${by}, ${bx} ${by}`;
        } else {
          // Carry a curved continuation through the row gutter on week wrap.
          const cell=cellFor(cards[i-1]).getBoundingClientRect();
          const gutter=cell.bottom-bounds.top-7, right=grid.clientWidth-5;
          d=`M ${ax} ${ay} C ${right} ${ay}, ${right} ${gutter}, ${right-18} ${gutter} L 22 ${gutter} C 5 ${gutter}, 5 ${by}, ${bx} ${by}`;
        }
        path.setAttribute('d',d);path.setAttribute('stroke',getComputedStyle(cards[i]).getPropertyValue('--event-color').trim());
        path.setAttribute('fill','none');path.setAttribute('stroke-width','1.7');path.setAttribute('stroke-linecap','round');svg.append(path);
      }
    });
    grid.prepend(svg);
  }
  let observed;
  function schedule(grid) {
    requestAnimationFrame(() => draw(grid));
    if (!observed && window.ResizeObserver) { observed=new ResizeObserver(() => requestAnimationFrame(() => draw(grid)));observed.observe(grid); }
  }
  return { schedule };
})();
