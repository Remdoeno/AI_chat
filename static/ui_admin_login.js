/* Shared administrator sign-in feedback; authentication remains on the server. */
(() => {
  const form = document.querySelector('form[data-login-next]');if (!form) return;
  const password = document.getElementById(form.dataset.loginPassword);
  const status = document.getElementById(form.dataset.loginStatus);
  const submit = form.querySelector('[type=submit]');
  let submitting = false;
  form.addEventListener('submit',async e => {
    e.preventDefault();if(submitting || !form.reportValidity())return;
    submitting=true;submit.disabled=true;status.textContent='正在验证…';
    try {
      const response=await fetch('/api/admin/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:password.value}),signal:AbortSignal.timeout(20000)});
      if(!response.ok){status.textContent=response.status===401?'管理员密码不正确，请重新输入。':'暂时无法验证，请稍后重试。';password.focus();password.select();return;}
      status.textContent='验证成功，正在进入…';window.location.href=form.dataset.loginNext;
    }catch(_){status.textContent='连接未完成，密码已保留，请重试。';}
    finally{submitting=false;submit.disabled=false;}
  });
})();
