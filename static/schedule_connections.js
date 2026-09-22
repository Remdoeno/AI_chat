/* Short rounded elbows in the space between cards. Never capture interaction. */
window.ScheduleConnections = (() => {
  const NS = 'http://www.w3.org/2000/svg';
  function rounded(points, radius=4) {
    let d=`M ${points[0][0]} ${points[0][1]}`;
    for (let i=1;i<points.length-1;i++) {
      const a=points[i-1],b=points[i],c=points[i+1];
      const before=Math.hypot(b[0]-a[0],b[1]-a[1]),after=Math.hypot(c[0]-b[0],c[1]-b[1]);
      if (!before || !after) continue;
      const r=Math.min(radius,before/2,after/2);
      const p=[b[0]+(a[0]-b[0])*r/before,b[1]+(a[1]-b[1])*r/before];
      const q=[b[0]+(c[0]-b[0])*r/after,b[1]+(c[1]-b[1])*r/after];
      d+=` L ${p[0]} ${p[1]} Q ${b[0]} ${b[1]} ${q[0]} ${q[1]}`;
    }
    const last=points[points.length-1];return d+` L ${last[0]} ${last[1]}`;
  }
  function draw(grid) {
    grid.querySelector('.project-connections')?.remove();
    ScheduleRanges.position(grid);
    if (!grid.classList.contains('single-mode') || !grid.clientWidth) return;
    const svg=document.createElementNS(NS,'svg');svg.classList.add('project-connections');
    svg.setAttribute('aria-hidden','true');svg.setAttribute('width',grid.scrollWidth);svg.setAttribute('height',grid.scrollHeight);
    const bounds=grid.getBoundingClientRect(),groups=new Map();
    const rect = n => { const r=n.getBoundingClientRect();return {left:r.left-bounds.left,right:r.right-bounds.left,top:r.top-bounds.top,bottom:r.bottom-bounds.top,cx:(r.left+r.right)/2-bounds.left,cy:(r.top+r.bottom)/2-bounds.top}; };
    const obstacles=[...grid.querySelectorAll('.event-card,.day-heading')].map(rect);
    const cellFor=card => card.closest('.day-cell') || grid.querySelector(`.day-cell[data-date="${card.dataset.anchorDate}"]`);
    grid.querySelectorAll('[data-project]').forEach(card => {
      const key = JSON.stringify([card.dataset.project, card.dataset.track || '']);
      if (!groups.has(key)) groups.set(key,[]);
      groups.get(key).push(card);
    });
    groups.forEach(cards => {
      cards.sort((a,b) => Number(a.dataset.stageIndex)-Number(b.dataset.stageIndex) || (a.dataset.anchorDate || '').localeCompare(b.dataset.anchorDate || ''));
      for (let i=1;i<cards.length;i++) {
        if (cards[i-1].dataset.stageIndex===cards[i].dataset.stageIndex) continue;
        const a=rect(cards[i-1]),b=rect(cards[i]),ca=rect(cellFor(cards[i-1])),cb=rect(cellFor(cards[i]));
        const source=cards[i-1];
        if (source.dataset.rangeRight !== undefined) {
          const endCell=grid.querySelectorAll('.day-cell')[Number(source.dataset.rangeRow)*7+Number(source.dataset.rangeRight)];
          ca.right=rect(endCell).right;
        }
        let points;
        if (Math.abs(ca.top-cb.top)>2) {
          // Cross-week links use the nearest column gutters and the gap between rows.
          const forward=ca.top<cb.top, gap=forward ? (ca.bottom+cb.top)/2 : (cb.bottom+ca.top)/2;
          const gx=Math.min(grid.clientWidth-4,ca.right-3),hx=Math.max(4,cb.left+3);
          points=[[a.right,a.cy],[gx,a.cy],[gx,gap],[hx,gap],[hx,b.cy],[b.left,b.cy]];
        } else if (Math.min(a.right,b.right)>Math.max(a.left,b.left)) {
          // Overlapping date spans occupy separate lanes: connect across their small gap.
          const top=a.top<b.top?a:b, bottom=a.top<b.top?b:a;
          const left=Math.max(a.left,b.left),right=Math.min(a.right,b.right);
          const x1=left+(right-left)*.62,x2=left+(right-left)*.38,mid=(top.bottom+bottom.top)/2;
          points=[[x1,top.bottom],[x1,mid],[x2,mid],[x2,bottom.top]];
        } else {
          const forward=a.cx<b.cx,ax=forward?a.right:a.left,bx=forward?b.left:b.right,middle=(ax+bx)/2;
          points=[[ax,a.cy],[middle,a.cy],[middle,b.cy],[bx,b.cy]];
        }
        const routed=ScheduleRouting.route(points,obstacles,grid.clientWidth,grid.scrollHeight);
        if (!routed) continue;
        const path=document.createElementNS(NS,'path');path.setAttribute('d',rounded(routed));
        path.setAttribute('stroke',getComputedStyle(cards[i]).getPropertyValue('--event-color').trim());
        path.setAttribute('fill','none');path.setAttribute('stroke-width','1.8');path.setAttribute('stroke-linecap','round');svg.append(path);
      }
    });
    grid.prepend(svg);
  }
  let observed;
  function schedule(grid) {
    requestAnimationFrame(() => draw(grid));
    if (!observed && window.ResizeObserver) { observed=new ResizeObserver(() => requestAnimationFrame(() => draw(grid)));observed.observe(grid); }
  }
  return {schedule};
})();
