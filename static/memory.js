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

const memoryList = document.getElementById("memoryList");
const retrievalList = document.getElementById("retrievalList");
const operationList = document.getElementById("operationList");

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

function renderEmpty(target, text) {
  target.replaceChildren(div("empty", text));
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

function renderMemories(payload) {
  memoryCount.textContent = payload.total;
  if (!payload.items.length) {
    renderEmpty(memoryList, "没有匹配的长期记忆");
    return;
  }

  memoryList.replaceChildren(
    ...payload.items.map((item) => {
      const root = div("item");
      const top = div("item-top");
      const tags = div("tag-row");
      const memoryTags = [
        tag(`#${item.id}`),
        tag(item.importance_label),
        item.timeline_at ? tag(`timeline ${formatTime(item.timeline_at)}`) : null,
        item.confidence != null ? tag(`confidence ${Number(item.confidence).toFixed(2)}`) : null,
        item.supersedes_id ? tag(`supersedes #${item.supersedes_id}`) : null,
        tag(item.has_vector ? `vector ${item.vector_dim}` : "no vector"),
      ].filter(Boolean);
      tags.append(...memoryTags);
      top.append(tags, div("time", formatTime(item.updated_at)));
      root.append(top, div("content", item.content));
      return root;
    })
  );
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
      limit: 120,
    });
    const retrievalQuery = buildQuery({
      memory_id: retrievalMemoryId.value.trim(),
      limit: 120,
    });
    const operationQuery = buildQuery({
      kind: operationKind.value,
      status: operationStatus.value,
      event_type: operationEventType.value.trim(),
      limit: 160,
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
refreshAll();
