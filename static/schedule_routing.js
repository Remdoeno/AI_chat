/* Pure orthogonal routing around padded card rectangles; no DOM or shared state. */
window.ScheduleRouting = (() => {
  const pad = 7;
  const inside = (p,r) => p[0]>r.left+.01 && p[0]<r.right-.01 && p[1]>r.top+.01 && p[1]<r.bottom-.01;
  const blocked = (a,b,boxes) => boxes.some(r => a[0]===b[0]
    ? a[0]>r.left+.01 && a[0]<r.right-.01 && Math.max(a[1],b[1])>r.top+.01 && Math.min(a[1],b[1])<r.bottom-.01
    : a[1]>r.top+.01 && a[1]<r.bottom-.01 && Math.max(a[0],b[0])>r.left+.01 && Math.min(a[0],b[0])<r.right-.01);
  const distance = (a,b) => Math.abs(a[0]-b[0])+Math.abs(a[1]-b[1]);
  function simplify(points) {
    const result=[];
    points.forEach(p => {
      if (result.length && distance(result[result.length-1],p)<.01) return;
      while (result.length>1) {
        const a=result[result.length-2],b=result[result.length-1];
        if ((a[0]===b[0] && b[0]===p[0]) || (a[1]===b[1] && b[1]===p[1])) result.pop();else break;
      }
      result.push(p);
    });
    return result;
  }
  function port(point,rect) {
    const sides=[['left',0,-1],['right',0,1],['top',1,-1],['bottom',1,1]];
    sides.sort((a,b)=>Math.abs(point[a[1]]-rect[a[0]])-Math.abs(point[b[1]]-rect[b[0]]));
    const p=[...point],side=sides[0];p[side[1]]+=side[2]*(pad+1);return p;
  }
  function route(preferred, rectangles, width, height) {
    const start=preferred[0],end=preferred[preferred.length-1];
    const at = p => rectangles.findIndex(r => p[0]>=r.left-.1 && p[0]<=r.right+.1 && p[1]>=r.top-.1 && p[1]<=r.bottom+.1);
    const si=at(start),ei=at(end);if(si<0 || ei<0) return null;
    const boxes=rectangles.map(r=>({left:r.left-pad,right:r.right+pad,top:r.top-pad,bottom:r.bottom+pad}));
    const s=port(start,rectangles[si]),e=port(end,rectangles[ei]);
    const validPoint=p=>p[0]>=2 && p[0]<=width-2 && p[1]>=2 && p[1]<=height-2 && !boxes.some(r=>inside(p,r));
    if (!validPoint(s) || !validPoint(e)) return null;
    if (blocked(start,s,boxes.filter((_,i)=>i!==si)) || blocked(e,end,boxes.filter((_,i)=>i!==ei))) return null;
    const xs=[...new Set([2,width-2,s[0],e[0],...boxes.flatMap(r=>[r.left,r.right])])].filter(x=>x>=2 && x<=width-2).sort((a,b)=>a-b);
    const ys=[...new Set([2,height-2,s[1],e[1],...boxes.flatMap(r=>[r.top,r.bottom])])].filter(y=>y>=2 && y<=height-2).sort((a,b)=>a-b);
    const clear=path=>path.every(validPoint) && path.slice(1).every((p,i)=>!blocked(path[i],p,boxes));
    const candidates=[ [s,[s[0],e[1]],e], [s,[e[0],s[1]],e],
      ...ys.map(y=>[s,[s[0],y],[e[0],y],e]), ...xs.map(x=>[s,[x,s[1]],[x,e[1]],e]) ];
    const score=path=>path.slice(1).reduce((sum,p,i)=>sum+distance(path[i],p),0)+(path.length-2)*16;
    const simple=candidates.map(simplify).filter(clear).sort((a,b)=>score(a)-score(b))[0];
    if(simple) return simplify([start,...simple,end]);
    // More crowded layouts need several elbows. Search a grid of obstacle edges.
    const startX=xs.indexOf(s[0]),startY=ys.indexOf(s[1]),endX=xs.indexOf(e[0]),endY=ys.indexOf(e[1]);
    const key=(x,y,d)=>`${x},${y},${d}`, costs=new Map(), heap=[];
    function push(n){heap.push(n);let i=heap.length-1;while(i){const parent=(i-1)>>1;if(heap[parent].f<=n.f)break;heap[i]=heap[parent];i=parent;}heap[i]=n;}
    function pop(){const first=heap[0],last=heap.pop();if(heap.length){let i=0;while(i*2+1<heap.length){let child=i*2+1;if(child+1<heap.length && heap[child+1].f<heap[child].f)child++;if(last.f<=heap[child].f)break;heap[i]=heap[child];i=child;}heap[i]=last;}return first;}
    const initial={x:startX,y:startY,d:0,g:0,f:distance(s,e),parent:null};costs.set(key(startX,startY,0),0);push(initial);
    let visits=0;
    while(heap.length && visits++<5000){
      const n=pop();if(n.g!==costs.get(key(n.x,n.y,n.d)))continue;
      if(n.x===endX && n.y===endY){const path=[];for(let cursor=n;cursor;cursor=cursor.parent)path.push([xs[cursor.x],ys[cursor.y]]);return simplify([start,...path.reverse(),end]);}
      for(const [dx,dy,d] of [[1,0,1],[-1,0,1],[0,1,2],[0,-1,2]]){
        const x=n.x+dx,y=n.y+dy;if(x<0 || y<0 || x>=xs.length || y>=ys.length)continue;
        const a=[xs[n.x],ys[n.y]],b=[xs[x],ys[y]];if(!validPoint(b) || blocked(a,b,boxes))continue;
        const g=n.g+distance(a,b)+(n.d && n.d!==d?16:0),k=key(x,y,d);
        if(g>=(costs.get(k)??Infinity))continue;
        costs.set(k,g);push({x,y,d,g,f:g+distance(b,e),parent:n});
      }
    }
    // Omit an obstructed connection rather than draw through an unrelated card.
    return null;
  }
  return {route};
})();
