/* A dialog owns its draft; closing protection is composed around existing save APIs. */
window.WangcaiDialogGuard = (() => {
  function attach(dialog, {read, save, discard, busy = () => false}) {
    let baseline = '', prompt = null;
    const markClean = () => { baseline = JSON.stringify(read()); };
    function dismissPrompt() { if (prompt) { prompt.close(); prompt.remove(); prompt = null; } }
    function requestClose() {
      if (!dialog.open || busy()) return;
      if (JSON.stringify(read()) === baseline) { discard(); return; }
      if (prompt) return;
      prompt = document.createElement('dialog');prompt.className = 'ui-unsaved-dialog';
      const title = document.createElement('h2');title.textContent = '保存本次修改？';title.id = dialog.id + '-unsaved-title';
      prompt.setAttribute('aria-labelledby', title.id);
      const description = document.createElement('p');description.textContent = '内容有改动，保存后再关闭，或放弃这次修改。';
      const status = document.createElement('p');status.setAttribute('role','status');status.className = 'ui-error';
      const actions = document.createElement('div');actions.className = 'ui-unsaved-actions';
      const action = (label, handler, className = '') => { const b = document.createElement('button');b.type='button';b.textContent=label;b.className=className;b.onclick=handler;actions.append(b);return b; };
      action('继续编辑',dismissPrompt);
      action('不保存',() => { dismissPrompt();discard(); });
      action('保存并关闭',async () => {
        if (busy()) return;
        const invalid = dialog.querySelector(':invalid');
        if (invalid) { dismissPrompt(); invalid.dispatchEvent(new Event('invalid', {cancelable:true})); invalid.reportValidity(); return; }
        const current = prompt;actions.querySelectorAll('button').forEach(b => b.disabled = true);
        try { await save(); if (!dialog.open) dismissPrompt(); else status.textContent = '尚未保存，请继续编辑并检查填写内容。'; }
        catch (_) { status.textContent = '保存失败，修改已保留，请重试。'; }
        finally { if (current === prompt) actions.querySelectorAll('button').forEach(b => b.disabled = false); }
      },'ui-save');
      prompt.append(title,description,status,actions);document.body.append(prompt);
      prompt.addEventListener('cancel', e => {e.preventDefault();dismissPrompt();});
      prompt.showModal();
    }
    dialog.addEventListener('cancel',e => {e.preventDefault();requestClose();});
    dialog.addEventListener('click',e => { const r=dialog.getBoundingClientRect();if(e.target===dialog&&(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom))requestClose(); });
    dialog.addEventListener('close',dismissPrompt);
    return {markClean,requestClose,isDirty: () => JSON.stringify(read()) !== baseline};
  }
  return {attach};
})();
