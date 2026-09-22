/* Responsive view controls retain mounted panels and their input/scroll state. */
(() => {
  'use strict';
  document.querySelectorAll('[data-workspace]').forEach((root) => {
    const media = window.matchMedia(`(max-width: ${Number(root.dataset.breakpoint) || 900}px)`);
    const buttons = [...root.querySelectorAll('[data-workspace-target]')];
    const panels = [...root.querySelectorAll('[data-workspace-panel]')];
    let selected = root.dataset.defaultPanel || buttons[0]?.dataset.workspaceTarget;
    const render = () => {
      root.classList.toggle('workspace-compact', media.matches);
      for (const panel of panels) panel.hidden = media.matches && panel.dataset.workspacePanel !== selected;
      for (const container of root.querySelectorAll('[data-workspace-container]')) {
        container.hidden = media.matches && [...container.querySelectorAll('[data-workspace-panel]')].every((panel) => panel.hidden);
      }
      for (const button of buttons) button.setAttribute('aria-pressed', String(button.dataset.workspaceTarget === selected));
      // Existing visualizers observe resize to recalculate panels after revealing them.
      window.dispatchEvent(new Event('resize'));
    };
    for (const button of buttons) button.addEventListener('click', () => {
      selected = button.dataset.workspaceTarget;
      render();
    });
    media.addEventListener('change', render);
    render();
  });
})();
