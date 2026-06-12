const loginPanel = document.getElementById("warnLoginPanel");
const contentPanel = document.getElementById("warnContentPanel");
const loginForm = document.getElementById("warnLoginForm");
const passwordInput = document.getElementById("warnPasswordInput");
const loginStatus = document.getElementById("warnLoginStatus");
const refreshButton = document.getElementById("warnRefreshButton");
const summaryEl = document.getElementById("warnSummary");
const listEl = document.getElementById("warnList");
const filterButtons = Array.from(document.querySelectorAll(".warn-filter"));
let activeKind = "";

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatTime(value) {
  const date = new Date(value || Date.now());
  if (Number.isNaN(date.getTime())) {
    return String(value || "");
  }
  return date.toLocaleString("zh-CN", { hour12: false });
}

function setAuthenticated(authenticated) {
  loginPanel.hidden = authenticated;
  contentPanel.hidden = !authenticated;
  if (!authenticated) {
    passwordInput.focus();
  }
}

function renderEvents(events) {
  listEl.innerHTML = "";
  if (!events.length) {
    listEl.innerHTML = '<div class="warn-item"><strong>暂无记录</strong></div>';
    return;
  }
  for (const item of events) {
    const metadata = JSON.stringify(item.metadata || {}, null, 2);
    const el = document.createElement("article");
    el.className = `warn-item ${item.level || "info"}`;
    el.innerHTML = `
      <div class="warn-item-head">
        <span>${escapeHtml(item.event_type)}</span>
        <span>${escapeHtml(item.level || "info")}</span>
      </div>
      <div class="warn-meta">${escapeHtml(formatTime(item.created_at))} · ${escapeHtml(item.visitor_ip)} · session ${escapeHtml(item.session_id || "-")}</div>
      <pre class="warn-json">${escapeHtml(metadata)}</pre>
    `;
    listEl.appendChild(el);
  }
}

async function loadWarnLogs() {
  summaryEl.textContent = "读取中";
  const params = new URLSearchParams();
  if (activeKind) {
    params.set("kind", activeKind);
  }
  params.set("limit", "200");
  const response = await fetch(`/api/warn/logs?${params.toString()}`);
  if (response.status === 401) {
    setAuthenticated(false);
    loginStatus.textContent = "请先输入管理员密码。";
    return;
  }
  if (!response.ok) {
    summaryEl.textContent = `读取失败：${await response.text()}`;
    return;
  }
  const payload = await response.json();
  setAuthenticated(true);
  renderEvents(payload.events || []);
  summaryEl.textContent = `${payload.events.length} 条记录 · newest first`;
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginStatus.textContent = "验证中";
  const response = await fetch("/api/admin/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password: passwordInput.value }),
  });
  if (!response.ok) {
    loginStatus.textContent = "密码错误";
    return;
  }
  passwordInput.value = "";
  loginStatus.textContent = "";
  await loadWarnLogs();
});

refreshButton.addEventListener("click", loadWarnLogs);
filterButtons.forEach((button) => {
  button.addEventListener("click", () => {
    activeKind = button.dataset.kind || "";
    filterButtons.forEach((item) => item.classList.toggle("is-active", item === button));
    loadWarnLogs();
  });
});

loadWarnLogs().catch((error) => {
  setAuthenticated(false);
  loginStatus.textContent = error.message || "读取失败";
});
