/* Shared readable status and input names, without altering business actions. */
(() => {
  const labels={messageInput:'输入消息',characterMessageInput:'告诉旺财如何创建或修改角色',artifactCommentInput:'评论内容',warnPasswordInput:'管理员密码'};
  Object.entries(labels).forEach(([id,label])=>{const node=document.getElementById(id);if(node&&!node.getAttribute('aria-label'))node.setAttribute('aria-label',label);});
  document.querySelectorAll('.status,.dialog-status,.form-status,.analysis-status,.warn-status,#statusText,#characterStatus,#pageStatus').forEach(node=>{node.setAttribute('role','status');node.setAttribute('aria-live','polite');node.setAttribute('aria-atomic','true');});
  document.querySelectorAll('.warn-filter').forEach(button=>{button.setAttribute('aria-pressed',String(button.classList.contains('is-active')));button.addEventListener('click',()=>document.querySelectorAll('.warn-filter').forEach(other=>other.setAttribute('aria-pressed',String(other===button))));});
})();
