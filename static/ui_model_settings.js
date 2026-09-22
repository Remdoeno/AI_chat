/* Progressive disclosure only; model persistence and permission checks stay in app.js. */
(() => {
  const form = document.getElementById('modelSettingsForm');
  if (!form || form.dataset.uiEnhanced) return;
  form.dataset.uiEnhanced = 'true';
  const panels = [...form.querySelectorAll('.model-slot-panel')];
  const nav = document.createElement('div');
  nav.className = 'model-slot-tabs'; nav.setAttribute('role', 'tablist'); nav.setAttribute('aria-label', '模型用途');
  const labels = ['聊天', '后台', '生图'];
  const tabs = [];
  function select(index, focus = false) {
    panels.forEach((panel, n) => {
      panel.hidden = n !== index;
      tabs[n].setAttribute('aria-selected', String(n === index));
      tabs[n].tabIndex = n === index ? 0 : -1;
    });
    if (focus) tabs[index].focus();
  }
  panels.forEach((panel, index) => {
    panel.id = `model-slot-page-${index}`;
    panel.setAttribute('role', 'tabpanel');
    const tab = document.createElement('button');
    tab.type = 'button'; tab.textContent = labels[index]; tab.id = `model-slot-tab-${index}`;
    tab.setAttribute('role', 'tab'); tab.setAttribute('aria-controls', panel.id);
    panel.setAttribute('aria-labelledby', tab.id);
    tab.addEventListener('click', () => select(index));
    tab.addEventListener('keydown', event => {
      let next;
      if (event.key === 'ArrowRight') next = (index + 1) % panels.length;
      if (event.key === 'ArrowLeft') next = (index + panels.length - 1) % panels.length;
      if (event.key === 'Home') next = 0;
      if (event.key === 'End') next = panels.length - 1;
      if (next !== undefined) { event.preventDefault(); select(next, true); }
    });
    tabs.push(tab); nav.append(tab);
    const advanced = document.createElement('details'); advanced.className = 'model-connection-options';
    const summary = document.createElement('summary'); summary.textContent = '连接与代理设置';
    const fields = document.createElement('div'); fields.className = 'model-connection-fields';
    advanced.append(summary, fields);
    ['display_name', 'base_url', 'use_proxy', 'proxy_url'].forEach(field => {
      const node = panel.querySelector(`[data-model-field="${field}"]`)?.closest('label');
      if (node) fields.append(node);
    });
    panel.append(advanced);
  });
  panels[0].before(nav);
  const footer = document.createElement('div'); footer.className = 'model-settings-footer';
  const status = document.getElementById('modelSettingsStatus');
  const actions = form.querySelector('.dialog-actions');
  if (status) { status.setAttribute('aria-live', 'polite'); footer.append(status); }
  if (actions) footer.append(actions);
  form.append(footer);
  // Native validation must reveal a hidden field before the browser attempts to focus it.
  // Keep every field enabled: hidden tabs must still participate in save and validation.
  let invalidCycle = false;
  form.addEventListener('invalid', event => {
    if (invalidCycle) return;
    invalidCycle = true; setTimeout(() => { invalidCycle = false; }, 0);
    const panel = event.target.closest('.model-slot-panel');
    const index = panels.indexOf(panel); if (index >= 0) select(index);
    const disclosure = event.target.closest('details'); if (disclosure) disclosure.open = true;
  }, true);
  select(0);
})();
