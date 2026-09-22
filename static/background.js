(() => {
"use strict";
function formatNumber(value) {
  return new Intl.NumberFormat("zh-CN").format(Number(value || 0));
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = bytes;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function formatMs(value) {
  const ms = Number(value || 0);
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`;
  return `${ms.toFixed(0)}ms`;
}

function byId(id) {
  return document.getElementById(id);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function table(headers, rows) {
  const body = rows.length ? rows.join("") : `<tr><td colspan="${headers.length}" class="muted">暂无数据</td></tr>`;
  return `<table><thead><tr>${headers.map((item) => `<th class="${item.numeric ? "number" : ""}">${item.label}</th>`).join("")}</tr></thead><tbody>${body}</tbody></table>`;
}

function windowCell(windowData) {
  const item = windowData || {};
  return `<div class="usage-cell">
    <strong>${formatNumber(item.calls)} 次调用</strong>
    <span>平均 ${formatMs(item.avg_duration_ms)}</span>
    <span class="usage-failure">失败 ${formatNumber(item.failures)} 次</span>
    <details><summary>用量明细</summary>
      <span>总耗时 ${formatMs(item.total_duration_ms)}</span>
      <span>Token ${formatNumber(item.total_tokens)}</span>
      <span>输入 ${formatNumber(item.input_tokens)} · 输出 ${formatNumber(item.output_tokens)}</span>
    </details>
  </div>`;
}

function selectedWindow() {
  const value = byId("statsWindow").value;
  return ["hour", "day", "month"].includes(value) ? value : "day";
}

function windowLabel(key) {
  return {hour: "最近 1 小时", day: "最近 24 小时", month: "最近 30 天"}[key];
}

function byFailures(rows, key) {
  return [...(rows || [])].sort((a, b) => Number(b[key]?.failures || 0) - Number(a[key]?.failures || 0));
}

function renderSummary(summary, resource, windows) {
  const memory = resource.memory || {};
  const disk = resource.disk || {};
  const current = resource.current_process || {};
  const day = (windows || []).find((item) => item.seconds === 86400) || {};
  const items = [
    ["消息", summary.messages],
    ["记忆", summary.memories],
    ["成果", summary.artifacts],
    ["图片", summary.images],
    ["DB", formatBytes(summary.db_size_bytes)],
    ["本服务 RSS", formatBytes(current.rss_bytes)],
    ["24h 消息", day.messages || 0],
    ["24h 事件", day.events || 0],
  ];
  byId("summaryGrid").innerHTML = items
    .map(([label, value]) => `<div class="summary-card"><span>${label}</span><strong>${escapeHtml(value)}</strong></div>`)
    .join("");
  byId("statusStrip").textContent = `更新于 ${summary.generated_at || ""} · 内存 ${memory.used_percent ?? 0}% · 磁盘 ${disk.used_percent ?? 0}%`;
}

function renderAgentRows(rows) {
  const key = selectedWindow();
  const htmlRows = byFailures(rows, key).map((row) => `<tr class="${Number(row[key]?.failures) > 0 ? "has-failures" : ""}">
    <td><strong>${escapeHtml(row.description || row.step_name)}</strong>
      <details><summary class="muted">调用标识与时间</summary><div class="muted">${escapeHtml(row.step_name)}</div><div class="muted">${escapeHtml(row.last_seen_at || "")}</div></details>
    </td><td>${windowCell(row[key])}</td></tr>`);
  byId("agentRows").innerHTML = table([{label: "调用任务"}, {label: windowLabel(key)}], htmlRows);
  const totals = (rows || []).reduce((result, row) => {
    const item = row[key] || {};
    result.calls += Number(item.calls || 0);
    result.failures += Number(item.failures || 0);
    result.duration += Number(item.total_duration_ms || 0);
    return result;
  }, {calls: 0, failures: 0, duration: 0});
  const health = byId("statsHealth");
  health.textContent = `${windowLabel(key)} · ${totals.calls ? `${formatNumber(totals.calls)} 次调用 · 失败 ${formatNumber(totals.failures)} 次 · 平均 ${formatMs(totals.duration / totals.calls)}` : "暂无调用记录"}`;
  health.classList.toggle("danger", totals.failures > 0);
}

function renderModelRows(rows) {
  const key = selectedWindow();
  const htmlRows = byFailures(rows, key).map((row) => `<tr class="${Number(row[key]?.failures) > 0 ? "has-failures" : ""}">
    <td><strong>${escapeHtml(row.model)}</strong><div class="muted">${escapeHtml(row.description || "")}</div>
      <details><summary class="muted">最近调用</summary><div class="muted">${escapeHtml(row.last_seen_at || "")}</div></details>
    </td><td>${windowCell(row[key])}</td></tr>`);
  byId("modelRows").innerHTML = table([{label: "模型"}, {label: windowLabel(key)}], htmlRows);
}

function renderTableStats(rows) {
  const key = selectedWindow();
  const recentKey = {hour: "recent_1h", day: "recent_24h", month: "recent_30d"}[key];
  const htmlRows = (rows || [])
    .slice(0, 26)
    .map((row) => `
      <tr>
        <td><strong>${escapeHtml(row.name)}</strong><div class="muted">${escapeHtml(row.description)}</div></td>
        <td class="number">${formatNumber(row.rows)}</td>
        <td class="number">${formatNumber(row[recentKey])}</td>
        <td class="number">${formatBytes(row.size_bytes)}</td>
      </tr>
    `);
  byId("tableStats").innerHTML = table(
    [
      { label: "表 / 用途" },
      { label: "行数", numeric: true },
      { label: windowLabel(key), numeric: true },
      { label: "规模", numeric: true },
    ],
    htmlRows
  );
}

function renderResource(resource, windows) {
  const memory = resource.memory || {};
  const disk = resource.disk || {};
  const cpu = resource.cpu || {};
  const current = resource.current_process || {};
  const imageStorage = resource.image_storage || {};
  const windowRows = (windows || [])
    .map((item) => `<div class="metric-row"><span>${escapeHtml(item.label)}</span><strong>${formatNumber(item.events)} 事件 · ${formatNumber(item.messages)} 消息 · QPS ${item.event_qps}</strong></div>`)
    .join("");
  byId("resourceView").innerHTML = `
    <div class="resource-block">
      <h3>CPU / 内存 / 磁盘</h3>
      <div class="metric-row"><span>CPU</span><strong>${formatNumber(cpu.cpu_count)} cores · load ${(cpu.load_average || []).join(" / ")}</strong></div>
      <div class="metric-row"><span>内存</span><strong>${memory.used_percent ?? 0}% · ${formatBytes(memory.used_bytes)} / ${formatBytes(memory.total_bytes)}</strong></div>
      <div class="metric-row"><span>磁盘</span><strong>${disk.used_percent ?? 0}% · ${formatBytes(disk.used_bytes)} / ${formatBytes(disk.total_bytes)}</strong></div>
      <div class="metric-row"><span>图片目录</span><strong>${formatBytes(imageStorage.total_bytes)} · ${formatNumber(imageStorage.file_count)} 张 · ${escapeHtml(imageStorage.public_prefix || "/static/generated_images")}</strong></div>
    </div>
    <div class="resource-block">
      <h3>本服务</h3>
      <div class="metric-row"><span>PID</span><strong>${current.pid || 0}</strong></div>
      <div class="metric-row"><span>RSS</span><strong>${formatBytes(current.rss_bytes)}</strong></div>
      <div class="metric-row"><span>线程</span><strong>${formatNumber(current.threads)}</strong></div>
    </div>
    <div class="resource-block">
      <h3>近期活动</h3>
      ${windowRows}
    </div>
  `;
  renderGpuDeployment(resource.gpus || {});
}

function renderGpuDeployment(gpu) {
  const rows = gpu.available
    ? (gpu.gpus || []).map((item) => `
      <div class="resource-block">
        <h3>${escapeHtml(item.role || "本地模型服务")} · GPU ${escapeHtml(item.index)}</h3>
        <div class="metric-row"><span>利用率</span><strong>${item.utilization_percent}%</strong></div>
        <div class="metric-row"><span>显存</span><strong>${formatNumber(item.memory_used_mb)} / ${formatNumber(item.memory_total_mb)} MB · ${item.memory_used_percent}%</strong></div>
      </div>
    `).join("")
    : `<div class="resource-block"><h3>GPU</h3><div class="metric-row"><span>状态</span><strong class="muted">${escapeHtml(gpu.error || "不可用")}</strong></div></div>`;
  byId("gpuDeployment").innerHTML = rows || `<div class="resource-block"><h3>GPU</h3><div class="metric-row"><span>状态</span><strong class="muted">${escapeHtml(gpu.selection || "未检测到本地模型服务 GPU")}</strong></div></div>`;
}

let overviewSnapshot = null;

async function refresh() {
  const button = byId("refreshButton");
  if (button.disabled) return;
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  const status = byId("statusStrip");
  status.classList.remove("is-error");
  status.textContent = "正在更新统计…";
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch("/api/background/overview", { cache: "no-store", signal: controller.signal });
    if (response.status === 401) {
      window.location.href = "/background";
      return;
    }
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    data.summary = {...(data.summary || {}), generated_at: data.generated_at};
    overviewSnapshot = data;
    renderSummary(data.summary || {}, data.resource || {}, data.recent_windows || []);
    renderAgentRows(data.agent_rows || []);
    renderModelRows(data.model_rows || []);
    renderResource(data.resource || {}, data.recent_windows || []);
    renderTableStats(data.table_stats || []);
  } catch (error) {
    status.classList.add("is-error");
    status.textContent = overviewSnapshot ? "暂时无法更新，已保留上次数据。请点击刷新重试。" : "暂时无法加载统计，请点击刷新重试。";
  } finally {
    window.clearTimeout(timeout);
    button.disabled = false;
    button.removeAttribute("aria-busy");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  byId("refreshButton").addEventListener("click", refresh);
  byId("statsWindow").addEventListener("change", () => {
    if (!overviewSnapshot) return;
    renderAgentRows(overviewSnapshot.agent_rows || []);
    renderModelRows(overviewSnapshot.model_rows || []);
    renderTableStats(overviewSnapshot.table_stats || []);
  });
  refresh();
});

})();
