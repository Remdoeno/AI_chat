const memoryCount = document.getElementById("memoryCount");
const retrievalCount = document.getElementById("retrievalCount");
const operationCount = document.getElementById("operationCount");
const refreshButton = document.getElementById("refreshButton");

const memoryKeyword = document.getElementById("memoryKeyword");
const memoryLabel = document.getElementById("memoryLabel");
const retrievalMemoryId = document.getElementById("retrievalMemoryId");
const operationKind = document.getElementById("operationKind");
const operationStatus = document.getElementById("operationStatus");
const operationEventType = document.getElementById("operationEventType");
const newMemoryLabel = document.getElementById("newMemoryLabel");
const newMemoryTimeline = document.getElementById("newMemoryTimeline");
const newMemoryContent = document.getElementById("newMemoryContent");
const createMemoryButton = document.getElementById("createMemoryButton");
const memoryEditStatus = document.getElementById("memoryEditStatus");

const memoryList = document.getElementById("memoryList");
const retrievalList = document.getElementById("retrievalList");
const operationList = document.getElementById("operationList");

const LABELS = ["preference", "identity", "rule", "persona", "artifact", "risk", "diary", "event", "fact", "other"];

const DEVICE_STORAGE_KEY = "qwen_device_id";

function makeDeviceId() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return `dev_${window.crypto.randomUUID().replace(/-/g, "").slice(0, 24)}`;
  }
  return `dev_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 14)}`;
}

function ensureDeviceId() {
  let deviceId = localStorage.getItem(DEVICE_STORAGE_KEY);
  if (!deviceId) {
    deviceId = makeDeviceId();
    localStorage.setItem(DEVICE_STORAGE_KEY, deviceId);
  }
  return deviceId;
}

function deviceIdentityHeaders() {
  return {
    "X-Qwen-Device-Id": ensureDeviceId(),
  };
}

function formatTime(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function setText(node, text) {
  node.textContent = text == null ? "" : String(text);
}

function div(className, text = "") {
  const node = document.createElement("div");
  node.className = className;
  setText(node, text);
  return node;
}

function tag(text) {
  return div("tag", text);
}

function makeLabelSelect(value) {
  const select = document.createElement("select");
  const normalized = LABELS.includes(value) ? value : "other";
  for (const label of LABELS) {
    const option = document.createElement("option");
    option.value = label;
    option.textContent = label;
    option.selected = label === normalized;
    select.appendChild(option);
  }
  return select;
}

function pad2(value) {
  return String(value).padStart(2, "0");
}

function parseTimelineParts(value) {
  const text = String(value || "").trim();
  if (!text) {
    return null;
  }
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
  if (Number.isNaN(date.getTime())) {
    return null;
  }
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
  const root = div("timeline-picker");
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
      if (!dateInput.value) {
        return "";
      }
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

function renderEmpty(target, text) {
  target.replaceChildren(div("empty", text));
}

function jsonHeaders() {
  return {
    ...deviceIdentityHeaders(),
    "Content-Type": "application/json",
  };
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: deviceIdentityHeaders(),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

async function sendJson(url, method, payload) {
  const response = await fetch(url, {
    method,
    headers: jsonHeaders(),
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

function setMemoryEditStatus(text) {
  memoryEditStatus.textContent = text;
}

function renderMemories(payload) {
  memoryCount.textContent = payload.total;
  if (!payload.items.length) {
    renderEmpty(memoryList, "没有匹配的长期记忆");
    return;
  }

  memoryList.replaceChildren(
    ...payload.items.map((item) => {
      const root = div("item memory-edit-item");
      const top = div("item-top");
      const tags = div("tag-row");
      const memoryTags = [
        tag(`#${item.id}`),
        tag(item.importance_label),
        formatTimelineMain(item) ? tag(formatTimelineMain(item)) : null,
        item.visitor_ip ? tag(`device ${item.visitor_ip}`) : null,
        item.confidence != null ? tag(`confidence ${Number(item.confidence).toFixed(2)}`) : null,
        item.supersedes_id ? tag(`supersedes #${item.supersedes_id}`) : null,
        item.refine_status ? tag(`精简 ${item.refine_status}`) : null,
        item.refined_from_id ? tag(`from #${item.refined_from_id}`) : null,
        tag(item.has_vector ? `vector ${item.vector_dim}` : "no vector"),
      ].filter(Boolean);
      tags.append(...memoryTags);
      top.append(tags, div("time", formatTime(item.updated_at)));
      const editGrid = div("memory-edit-grid");

      const labelField = document.createElement("label");
      labelField.className = "edit-field";
      labelField.append(div("edit-label", "类型"), makeLabelSelect(item.importance_label));

      const timelineField = document.createElement("label");
      timelineField.className = "edit-field timeline-field";
      const timelinePicker = makeTimelineEditor(item);
      timelineField.append(div("edit-label", "Timeline"), timelinePicker.root);

      const contentField = document.createElement("label");
      contentField.className = "edit-field content-field";
      const textarea = document.createElement("textarea");
      textarea.rows = 5;
      textarea.value = item.content || "";
      contentField.append(div("edit-label", "内容"), textarea);

      editGrid.append(labelField, timelineField, contentField);

      const actions = div("memory-actions");
      const saveButton = document.createElement("button");
      saveButton.type = "button";
      saveButton.textContent = "保存";
      saveButton.addEventListener("click", async () => {
        await updateMemory(item.id, textarea.value, labelField.querySelector("select").value, timelinePicker.value());
      });
      const deleteButton = document.createElement("button");
      deleteButton.type = "button";
      deleteButton.className = "danger-button";
      deleteButton.textContent = "删除";
      deleteButton.addEventListener("click", async () => {
        if (window.confirm(`删除记忆 #${item.id}？`)) {
          await deleteMemory(item.id);
        }
      });
      actions.append(saveButton, deleteButton);
      root.append(top, editGrid, actions);
      return root;
    })
  );
}

async function createMemory() {
  const content = newMemoryContent.value.trim();
  if (!content) {
    setMemoryEditStatus("内容为空");
    return;
  }
  createMemoryButton.disabled = true;
  setMemoryEditStatus("新增中，正在更新向量");
  try {
    await sendJson("/api/memory/memories", "POST", {
      content,
      importance_label: newMemoryLabel.value,
      ...newTimelinePicker.value(),
    });
    newMemoryContent.value = "";
    setMemoryEditStatus("已新增并更新向量");
    await refreshAll();
  } finally {
    createMemoryButton.disabled = false;
  }
}

async function updateMemory(id, content, label, timelinePayload) {
  if (!content.trim()) {
    setMemoryEditStatus("内容为空");
    return;
  }
  setMemoryEditStatus(`保存 #${id}，正在更新向量`);
  await sendJson(`/api/memory/memories/${id}`, "PATCH", {
    content,
    importance_label: label,
    ...timelinePayload,
  });
  setMemoryEditStatus(`已保存 #${id} 并更新向量`);
  await refreshAll();
}

async function deleteMemory(id) {
  setMemoryEditStatus(`删除 #${id}`);
  await fetchJson(`/api/memory/memories/${id}`, { method: "DELETE" });
  setMemoryEditStatus(`已删除 #${id}`);
  await refreshAll();
}

function renderRetrievals(payload) {
  retrievalCount.textContent = payload.total;
  if (!payload.items.length) {
    renderEmpty(retrievalList, "没有匹配的调用记录");
    return;
  }

  retrievalList.replaceChildren(
    ...payload.items.map((item) => {
      const root = div("item");
      const top = div("item-top");
      const tags = div("tag-row");
      tags.append(
        tag(`#${item.id}`),
        tag(`session ${item.session_id}`),
        tag(`${item.result_count} hits`)
      );
      top.append(tags, div("time", formatTime(item.created_at)));

      const body = div(
        "content mono",
        [
          `query_hash: ${item.query_hash}`,
          `memory_ids: ${JSON.stringify(item.memory_ids)}`,
          `scores: ${JSON.stringify(item.scores)}`,
          `labels: ${JSON.stringify(item.labels)}`,
        ].join("\n")
      );
      root.append(top, body);
      return root;
    })
  );
}

function renderOperations(payload) {
  operationCount.textContent = payload.total;
  if (!payload.items.length) {
    renderEmpty(operationList, "没有匹配的系统操作");
    return;
  }

  operationList.replaceChildren(
    ...payload.items.map((item) => {
      const root = div("item");
      const top = div("item-top");
      const tags = div("tag-row");
      tags.append(tag(item.kind), tag(`#${item.id}`));
      if (item.status) {
        tags.append(tag(item.status));
      }
      if (item.session_id) {
        tags.append(tag(`session ${item.session_id}`));
      }
      top.append(tags, div("time", formatTime(item.updated_at || item.created_at)));

      const details =
        item.kind === "memory_agent_job"
          ? [
              `operation: ${item.operation}`,
              `message_range: ${JSON.stringify(item.message_range)}`,
              item.error ? `error: ${item.error}` : "",
            ].filter(Boolean)
          : [`event_type: ${item.operation}`, `metadata: ${JSON.stringify(item.metadata)}`];
      root.append(top, div("content mono", details.join("\n")));
      return root;
    })
  );
}

function buildQuery(params) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== "" && value != null) {
      search.set(key, value);
    }
  });
  return search.toString();
}

async function refreshAll() {
  refreshButton.disabled = true;
  try {
    const memoryQuery = buildQuery({
      keyword: memoryKeyword.value.trim(),
      label: memoryLabel.value,
      limit: 240,
    });
    const retrievalQuery = buildQuery({
      memory_id: retrievalMemoryId.value.trim(),
      limit: 240,
    });
    const operationQuery = buildQuery({
      kind: operationKind.value,
      status: operationStatus.value,
      event_type: operationEventType.value.trim(),
      limit: 320,
    });

    const [memories, retrievals, operations] = await Promise.all([
      fetchJson(`/api/memory/memories?${memoryQuery}`),
      fetchJson(`/api/memory/retrievals?${retrievalQuery}`),
      fetchJson(`/api/memory/operations?${operationQuery}`),
    ]);

    renderMemories(memories);
    renderRetrievals(retrievals);
    renderOperations(operations);
  } catch (error) {
    renderEmpty(operationList, `加载失败：${error.message}`);
  } finally {
    refreshButton.disabled = false;
  }
}

let refreshTimer = null;
function scheduleRefresh() {
  window.clearTimeout(refreshTimer);
  refreshTimer = window.setTimeout(refreshAll, 180);
}

[
  memoryKeyword,
  memoryLabel,
  retrievalMemoryId,
  operationKind,
  operationStatus,
  operationEventType,
].forEach((node) => {
  node.addEventListener("input", scheduleRefresh);
  node.addEventListener("change", scheduleRefresh);
});

refreshButton.addEventListener("click", refreshAll);
const newTimelinePicker = makeTimelineEditor({});
newMemoryTimeline.replaceChildren(newTimelinePicker.root);
createMemoryButton.addEventListener("click", () => {
  createMemory().catch((error) => setMemoryEditStatus(`失败：${error.message}`));
});
refreshAll();
