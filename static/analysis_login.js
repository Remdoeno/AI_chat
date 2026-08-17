const form = document.getElementById("analysisLoginForm");
const password = document.getElementById("analysisPassword");
const passwordConfirm = document.getElementById("analysisPasswordConfirm");
const confirmField = document.getElementById("analysisConfirmField");
const hint = document.getElementById("analysisLoginHint");
const statusText = document.getElementById("analysisLoginStatus");
const returnLink = document.getElementById("analysisReturnLink");
const pageTitle = document.querySelector(".analysis-login-card h1");

let configured = true;
const allowedNextPaths = new Set(["/analysis", "/memory"]);

function nextPath() {
  const requested = new URLSearchParams(window.location.search).get("next") || "";
  if (allowedNextPaths.has(requested)) return requested;
  if (allowedNextPaths.has(window.location.pathname)) return window.location.pathname;
  return "/analysis";
}

if (pageTitle && nextPath().startsWith("/memory")) {
  pageTitle.textContent = "旺财记忆库";
}

function detailMessage(payload, fallback) {
  const detail = payload && payload.detail;
  const messages = {
    "shared user binding required": "请先返回聊天页绑定共享用户。",
    "shared user password is invalid": "共享用户密码错误。",
    "password confirmation does not match": "两次输入的密码不一致。",
  };
  return messages[detail] || (typeof detail === "string" ? detail : fallback);
}

function showSetupMode(isConfigured) {
  configured = Boolean(isConfigured);
  confirmField.hidden = configured;
  passwordConfirm.hidden = configured;
  passwordConfirm.required = !configured;
  password.autocomplete = configured ? "current-password" : "new-password";
}

async function loadStatus() {
  const response = await fetch("/api/analysis/auth/status", {
    headers: WangcaiDeviceIdentity.headers(),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error("共享用户状态读取失败");
  }
  const payload = await response.json();
  if (!payload.bound) {
    hint.textContent = "分析模式按共享用户隔离。当前设备尚未绑定共享用户。";
    returnLink.hidden = false;
    return;
  }
  if (payload.authenticated) {
    window.location.replace(nextPath());
    return;
  }
  showSetupMode(payload.configured);
  hint.textContent = payload.configured
    ? "输入当前共享用户的独立密码，进入该用户自己的分析模式。"
    : "这是该共享用户第一次进入分析模式，请设置独立密码。";
  form.hidden = false;
  password.focus();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!configured && password.value !== passwordConfirm.value) {
    statusText.textContent = "两次输入的密码不一致。";
    return;
  }
  statusText.textContent = configured ? "验证中" : "设置中";
  try {
    const response = await fetch("/api/analysis/login", {
      method: "POST",
      headers: WangcaiDeviceIdentity.jsonHeaders(),
      body: JSON.stringify({
        password: password.value,
        confirm_password: configured ? "" : passwordConfirm.value,
      }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(detailMessage(payload, "验证失败"));
    }
    window.location.replace(nextPath());
  } catch (error) {
    statusText.textContent = error.message || "验证失败";
    password.select();
  }
});

loadStatus().catch((error) => {
  hint.textContent = error.message || "共享用户状态读取失败";
  returnLink.hidden = false;
});
