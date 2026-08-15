const authForm = document.getElementById("authForm");
const oldPasswordField = document.getElementById("oldPasswordField");
const oldPassword = document.getElementById("oldPassword");
const newPassword = document.getElementById("newPassword");
const confirmPassword = document.getElementById("confirmPassword");
const authHint = document.getElementById("authHint");
const authStatus = document.getElementById("authStatus");

let configured = true;

function setAuthStatus(text) {
  authStatus.textContent = text;
}

async function loadAuthStatus() {
  const response = await fetch("/api/auth/status");
  if (!response.ok) {
    throw new Error(await response.text());
  }
  const payload = await response.json();
  configured = Boolean(payload.configured);
  oldPasswordField.hidden = !configured;
  oldPassword.required = configured;
  authHint.textContent = configured
    ? "输入旧管理员密码后可修改记忆后台、告警和后台观测共用的管理员密码。"
    : "首次启动需要先设置管理员密码，之后才能进入聊天主页。";
  setAuthStatus(configured ? "等待修改" : "等待首次设置");
}

authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const nextPassword = newPassword.value;
  if (nextPassword !== confirmPassword.value) {
    setAuthStatus("两次新密码不一致");
    return;
  }
  setAuthStatus("保存中");
  const response = await fetch("/api/auth/password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      old_password: configured ? oldPassword.value : "",
      new_password: nextPassword,
    }),
  });
  if (!response.ok) {
    setAuthStatus(response.status === 401 ? "旧管理员密码不正确" : await response.text());
    return;
  }
  setAuthStatus("已保存");
  window.location.href = "/";
});

loadAuthStatus().catch((error) => setAuthStatus(`读取失败：${error.message}`));
