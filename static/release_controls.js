(() => {
  let flags = {}, timer = null, started = 0;
  const status = document.getElementById('statusText');
  const latency = document.createElement('small');
  latency.className = 'release-latency';
  latency.hidden = true;
  status?.insertAdjacentElement('afterend', latency);
  function headers() {
    if (typeof jsonHeaders === 'function') return jsonHeaders();
    return window.WangcaiDeviceIdentity?.jsonHeaders() || {'Content-Type': 'application/json'};
  }
  function enabled(key) { return flags[key] !== false; }
  async function request(url, options = {}) {
    const response = await fetch(url, {...options, headers: headers()});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '请求失败，请重新打开设置');
    return data;
  }
  async function loadPersonalFlags() {
    try { const data=await request('/api/release-features');flags=Object.fromEntries(data.features.map(x=>[x.id,x.enabled])); }
    catch (_) { flags={}; }
  }
  function updateTimer() {
    if (!enabled('live_feedback') || !started) {latency.hidden=true;return;}
    const seconds=Math.floor((performance.now()-started)/1000);
    latency.hidden=false;latency.textContent=`已用时 ${seconds} 秒${seconds>=30 ? ' · 等待较久，可停止后检查模型连接' : ''}`;
  }
  window.addEventListener('wangcai:busy', event => {
    clearInterval(timer);timer=null;
    if(event.detail?.busy){started=performance.now();updateTimer();timer=setInterval(updateTimer,1000);loadPersonalFlags();}
    else {started=0;latency.hidden=true;}
  });
  window.addEventListener('pagehide',()=>{clearInterval(timer);timer=null;});
  window.WangcaiRelease={enabled,refresh:loadPersonalFlags};
  loadPersonalFlags();
})();
