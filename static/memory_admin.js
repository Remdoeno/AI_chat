const keywordInput = document.getElementById("keywordInput");
const labelFilter = document.getElementById("labelFilter");
const deviceFilter = document.getElementById("deviceFilter");
const refreshButton = document.getElementById("refreshButton");
const statusText = document.getElementById("statusText");
const memoryCount = document.getElementById("memoryCount");
const memoryList = document.getElementById("memoryList");
const newLabel = document.getElementById("newLabel");
const newIp = document.getElementById("newIp");
const newTimeline = document.getElementById("newTimeline");
const newContent = document.getElementById("newContent");
const createButton = document.getElementById("createButton");
const fetch = (input, init = {}) => window.fetch(input, {
  ...init,
  headers: WangcaiDeviceIdentity.headers(init.headers || {}),
});

const LABELS = ["preference", "identity", "rule", "persona", "risk", "diary", "event", "fact", "other"];
let refreshTimer = null;

function setStatus(text) {
  statusText.textContent = text;
}

function clearChildren(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

function formatTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
}

function makeLabelSelect(value) {
  const normalizedValue = LABELS.includes(value) ? value : "other";
  const select = document.createElement("select");
  for (const label of LABELS) {
    const option = document.createElement("option");
    option.value = label;
    option.textContent = label;
    option.selected = label === normalizedValue;
    select.appendChild(option);
  }
  return select;
}

function pad2(value) {
  return String(value).padStart(2, "0");
}

function parseTimelineParts(value) {
  const text = String(value || "").trim();
  if (!text) return null;
  const match = text.match(/(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:[T\s](\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?/);
  if (match) {
    return {
      year: Number(match[1]),
      month: Number(match[2]),
      day: Number(match[3]),
      hour: Number(match[4] || 0),
      minute: Number(match[5] || 0),
      second: Number(match[6] || 0),
    };
  }
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) return null;
  return {
    year: date.getFullYear(),
    month: date.getMonth() + 1,
    day: date.getDate(),
    hour: date.getHours(),
    minute: date.getMinutes(),
    second: date.getSeconds(),
  };
}

function makeTimelinePicker(initialValue = "") {
  const parsed = parseTimelineParts(initialValue);
  const now = new Date();
  const seed = parsed || {
    year: now.getFullYear(),
    month: now.getMonth() + 1,
    day: now.getDate(),
    hour: now.getHours(),
    minute: now.getMinutes(),
    second: now.getSeconds(),
  };
  const root = document.createElement("div");
  root.className = "timeline-picker";
  const dateInput = document.createElement("input");
  dateInput.type = "date";
  dateInput.placeholder = "无日期";
  dateInput.value = parsed ? `${seed.year}-${pad2(seed.month)}-${pad2(seed.day)}` : "";
  const timeInput = document.createElement("input");
  timeInput.type = "time";
  timeInput.step = "1";
  timeInput.value = `${pad2(seed.hour)}:${pad2(seed.minute)}:${pad2(seed.second)}`;
  root.append(dateInput, timeInput);
  return {
    root,
    value() {
      if (!dateInput.value) return "";
      const time = timeInput.value || "00:00:00";
      const normalizedTime = time.length === 5 ? `${time}:00` : time;
      return `${dateInput.value}T${normalizedTime}+08:00`;
    },
  };
}

function makeTimelineEditor(item = {}) {
  const main = makeTimelinePicker(item.timeline_at || "");
  return {
    root: main.root,
    value() {
      return {
        timeline_at: main.value(),
        timeline_start_at: item.timeline_start_at || "",
        timeline_end_at: item.timeline_end_at || "",
        timeline_kind: item.timeline_kind || "",
      };
    },
  };
}

function formatTimelineMain(item) {
  const main = item.timeline_at ? formatTime(item.timeline_at) : "";
  return main ? `timeline ${main}` : "";
}

function renderEmpty() {
  const node = document.createElement("div");
  node.className = "empty";
  node.textContent = "没有匹配的记忆";
  memoryList.appendChild(node);
}

function renderMemories(payload) {
  clearChildren(memoryList);
  memoryCount.textContent = String(payload.total ?? 0);
  const items = payload.items || [];
  if (!items.length) {
    renderEmpty();
    return;
  }

  for (const item of items) {
    const itemLabel = item.importance_label || item.label || "other";
    const card = document.createElement("article");
    card.className = "memory-item";

    const meta = document.createElement("div");
    meta.className = "memory-meta";
    meta.textContent = [
      `#${item.id}`,
      itemLabel,
      formatTimelineMain(item) || null,
      item.confidence != null ? `confidence ${Number(item.confidence).toFixed(2)}` : null,
      item.supersedes_id ? `supersedes #${item.supersedes_id}` : null,
      item.refine_status ? `精简 ${item.refine_status}` : null,
      item.refined_from_id ? `from #${item.refined_from_id}` : null,
      item.device_id || item.visitor_ip ? `device ${item.device_id || item.visitor_ip}` : "global",
      `updated ${formatTime(item.updated_at)}`,
    ].filter(Boolean).join(" · ");

    const editGrid = document.createElement("div");
    editGrid.className = "memory-edit-grid";

    const labelField = document.createElement("label");
    labelField.className = "field";
    const labelTitle = document.createElement("span");
    labelTitle.textContent = "Label";
    const labelSelect = makeLabelSelect(itemLabel);
    labelField.append(labelTitle, labelSelect);

    const timelineField = document.createElement("label");
    timelineField.className = "field timeline-field";
    const timelineTitle = document.createElement("span");
    timelineTitle.textContent = "Timeline";
    const timelinePicker = makeTimelineEditor(item);
    timelineField.append(timelineTitle, timelinePicker.root);

    const deviceField = document.createElement("label");
    deviceField.className = "field";
    const deviceTitle = document.createElement("span");
    deviceTitle.textContent = "Device";
    const deviceInput = document.createElement("input");
    deviceInput.type = "text";
    deviceInput.value = item.device_id || item.visitor_ip || "";
    deviceInput.placeholder = "仅可选择当前共享用户已绑定的设备";
    deviceField.append(deviceTitle, deviceInput);

    const contentField = document.createElement("label");
    contentField.className = "field";
    const contentTitle = document.createElement("span");
    contentTitle.textContent = "内容";
    const textarea = document.createElement("textarea");
    textarea.rows = 5;
    textarea.value = item.content || "";
    contentField.append(contentTitle, textarea);

    editGrid.append(labelField, timelineField, deviceField, contentField);

    const actions = document.createElement("div");
    actions.className = "memory-actions";

    const saveButton = document.createElement("button");
    saveButton.className = "ghost-button";
    saveButton.type = "button";
    saveButton.textContent = "保存";
    saveButton.addEventListener("click", async () => {
      await updateMemory(item.id, textarea.value, labelSelect.value, timelinePicker.value(), deviceInput.value);
    });

    const deleteButton = document.createElement("button");
    deleteButton.className = "danger-button";
    deleteButton.type = "button";
    deleteButton.textContent = "删除";
    deleteButton.addEventListener("click", async () => {
      if (window.confirm(`删除记忆 #${item.id}？`)) {
        await deleteMemory(item.id);
      }
    });

    actions.append(saveButton, deleteButton);
    card.append(meta, editGrid, actions);
    memoryList.appendChild(card);
  }
}

function buildQuery() {
  const params = new URLSearchParams();
  if (keywordInput.value.trim()) params.set("keyword", keywordInput.value.trim());
  if (labelFilter.value) params.set("label", labelFilter.value);
  if (deviceFilter.value.trim()) params.set("device_id_filter", deviceFilter.value.trim());
  params.set("limit", "300");
  return params.toString();
}

async function ensureOk(response) {
  if (response.status === 401) {
    window.location.href = "/analysis-login?next=/memory-admin";
    throw new Error("需要重新登录");
  }
  if (!response.ok) {
    throw new Error(await response.text());
  }
}

async function loadMemories() {
  setStatus("读取中");
  const response = await fetch(`/api/admin/memories?${buildQuery()}`);
  await ensureOk(response);
  renderMemories(await response.json());
  setStatus("已更新");
}

async function createMemory() {
  const content = newContent.value.trim();
  if (!content) {
    setStatus("内容为空");
    return;
  }
  setStatus("新增中");
  const response = await fetch("/api/admin/memories", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      content,
      importance_label: newLabel.value,
      device_id: newIp.value.trim(),
      ...newTimelinePicker.value(),
    }),
  });
  await ensureOk(response);
  newContent.value = "";
  setStatus("已新增");
  await loadMemories();
}

async function updateMemory(id, content, label, timelinePayload, deviceId) {
  if (!content.trim()) {
    setStatus("内容为空");
    return;
  }
  setStatus(`保存 #${id}`);
  const response = await fetch(`/api/admin/memories/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      content,
      importance_label: label,
      ...timelinePayload,
      device_id: deviceId.trim(),
    }),
  });
  await ensureOk(response);
  setStatus(`已保存 #${id}`);
  await loadMemories();
}

async function deleteMemory(id) {
  setStatus(`删除 #${id}`);
  const response = await fetch(`/api/admin/memories/${id}`, { method: "DELETE" });
  await ensureOk(response);
  setStatus(`已删除 #${id}`);
  await loadMemories();
}

function scheduleLoad() {
  window.clearTimeout(refreshTimer);
  refreshTimer = window.setTimeout(() => {
    loadMemories().catch((error) => setStatus(`失败: ${error.message}`));
  }, 250);
}

keywordInput.addEventListener("input", scheduleLoad);
labelFilter.addEventListener("change", scheduleLoad);
deviceFilter.addEventListener("input", scheduleLoad);
refreshButton.addEventListener("click", () => {
  loadMemories().catch((error) => setStatus(`失败: ${error.message}`));
});
createButton.addEventListener("click", () => {
  createMemory().catch((error) => setStatus(`失败: ${error.message}`));
});

const newTimelinePicker = makeTimelineEditor({});
newTimeline.replaceChildren(newTimelinePicker.root);
loadMemories().catch((error) => setStatus(`失败: ${error.message}`));
