/* Shared memory presentation; stored values and API payloads remain unchanged. */
(() => {
  const labels = Object.freeze({ preference: '偏好', identity: '身份', rule: '约定', persona: '性格', risk: '注意事项', diary: '日记', event: '事项', fact: '事实', other: '其他' });
  function editor(content, fields, actions) {
    const section = document.createElement('div');
    const preview = document.createElement('p');
    preview.className = 'memory-preview';
    preview.textContent = content || '这条记忆没有正文。';
    const details = document.createElement('details');
    details.className = 'memory-editor';
    const summary = document.createElement('summary');
    summary.textContent = '编辑记忆';
    details.append(summary, fields, actions);
    section.append(preview, details);
    return section;
  }
  function showError(container, error) {
    let status = container.querySelector('.memory-action-status');
    if (!status) {
      status = document.createElement('p');
      status.className = 'memory-action-status';
      status.setAttribute('role', 'alert');
      container.prepend(status);
    }
    status.textContent = `操作未完成：${error.message || '请重试'}。输入已保留，可重试。`;
  }
  window.MemoryUI = Object.freeze({ label: value => labels[value] || value || '其他', editor, showError });
  const tabs = [...document.querySelectorAll('.summary-grid [role="tab"]')];
  function activate(tab, focus = false) {
    tabs.forEach(item => {
      const selected = item === tab;
      item.setAttribute('aria-selected', String(selected));
      item.tabIndex = selected ? 0 : -1;
      document.getElementById(item.getAttribute('aria-controls')).hidden = !selected;
    });
    if (focus) tab.focus();
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => activate(tab));
    tab.addEventListener('keydown', event => {
      let next;
      if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
      if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
      if (event.key === 'Home') next = 0;
      if (event.key === 'End') next = tabs.length - 1;
      if (next === undefined) return;
      event.preventDefault();
      activate(tabs[next], true);
    });
  });
})();
