(() => {
  let flags = {}, snapshot = null, revision = 0, timer = null, started = 0;
  const dialog = document.getElementById('modelSettingsDialog');
  const scopeInput = document.getElementById('modelSettingsScope');
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
  let panel, list, note, probes;
  if (dialog) {
    panel = document.createElement('details'); panel.className = 'release-controls';
    const summary = document.createElement('summary'); summary.textContent = '3.0 体验与逐项回滚';
    const description = document.createElement('p');
    description.textContent = '每个开关即时保存。关闭只回退该项改良；已有聊天、日程和记忆不受影响。模型诊断使用已保存配置。';
    list = document.createElement('div'); list.className = 'release-feature-list';
    probes = document.createElement('div'); probes.className = 'release-probes';
    for (const [slot,title] of [['chat','诊断台前模型'],['background','诊断后台模型']]) {
      const button = document.createElement('button'); button.type = 'button'; button.textContent = title;
      button.className = 'secondary-button compact-button';
      button.addEventListener('click', async () => {
        if (!snapshot) return;
        const current = snapshot; button.disabled = true; note.textContent = '正在检查已保存模型…';
        try {
          const result = await request(`/api/model-settings/probe?scope=${current.scope}`, {method:'POST', body:JSON.stringify({slot,expected_owner:current.owner})});
          if (snapshot !== current) return;
          note.textContent = `${result.ok ? '✓' : '⚠'} ${result.message} · ${result.seconds} 秒`;
        } catch (error) { if (snapshot === current) note.textContent = error.message; }
        finally { button.disabled = false; }
      });
      probes.append(button);
    }
    note = document.createElement('p'); note.className = 'release-note'; note.setAttribute('role','status');
    panel.append(summary,description,list,probes,note);
    document.getElementById('modelSettingsStatus')?.before(panel);
    new MutationObserver(() => { if (dialog.open) loadControls(); }).observe(dialog,{attributes:true,attributeFilter:['open']});
    scopeInput?.addEventListener('change', () => { snapshot = null; list.replaceChildren(); loadControls(); });
  }
  function render(data) {
    list.replaceChildren(); probes.hidden = !data.features.find(x => x.id === 'model_probe')?.enabled;
    for (const feature of data.features) {
      const row = document.createElement('div'); row.className = 'release-feature';
      const label = document.createElement('label');
      const toggle = document.createElement('input'); toggle.type='checkbox'; toggle.checked=feature.enabled;
      const title = document.createElement('strong'); title.textContent=feature.title;
      label.append(toggle,title);
      const description=document.createElement('small'); description.textContent = feature.enabled ? feature.description : feature.rollback;
      const inherit=document.createElement('button'); inherit.type='button'; inherit.className='release-inherit';
      inherit.textContent=data.scope==='user' ? (feature.inherited ? '跟随系统' : '恢复系统默认') : '恢复推荐设置';
      inherit.disabled=data.scope==='user' && feature.inherited;
      async function save(value) {
        toggle.disabled=true; inherit.disabled=true; note.textContent='保存中…';
        const current=snapshot, generation=revision;
        try {
          const result=await request(`/api/release-features?scope=${data.scope}`, {method:'PUT',body:JSON.stringify({expected_owner:data.owner,changes:{[feature.id]:value}})});
          if (revision!==generation || snapshot!==current) return;
          snapshot=result;render(result); note.textContent=`${feature.title}：${value===false ? '已单独回滚' : value===null ? '已恢复默认' : '已启用'}。后续请求生效。`;
          await loadPersonalFlags();
        } catch(error) { if(revision===generation){ note.textContent=error.message;render(data); } }
      }
      toggle.addEventListener('change',()=>save(toggle.checked));
      inherit.addEventListener('click',()=>save(null));
      row.append(label,description,inherit);list.append(row);
    }
  }
  async function loadControls() {
    if (!dialog?.open) return;
    const generation=++revision, scope=scopeInput?.value || 'user';
    note.textContent='读取更新项目…';
    try {
      const data=await request(`/api/release-features?scope=${scope}`);
      if(generation!==revision) return;
      snapshot=data;render(data);note.textContent='';
    } catch(error) { if(generation===revision){snapshot=null;note.textContent=error.message;} }
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
