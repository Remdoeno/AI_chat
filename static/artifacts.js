const typeFilter = document.getElementById("typeFilter");
const keywordFilter = document.getElementById("keywordFilter");
const seriesFilter = document.getElementById("seriesFilter");
const sortSelect = document.getElementById("sortSelect");
const orderSelect = document.getElementById("orderSelect");
const refreshButton = document.getElementById("refreshButton");
const shuffleButton = document.getElementById("shuffleButton");
const idlePromptInput = document.getElementById("idlePromptInput");
const savePromptButton = document.getElementById("savePromptButton");
const statusText = document.getElementById("statusText");
const artifactCount = document.getElementById("artifactCount");
const artifactList = document.getElementById("artifactList");
const loadMoreButton = document.getElementById("loadMoreButton");
const runCount = document.getElementById("runCount");
const runList = document.getElementById("runList");
const artifactDialog = document.getElementById("artifactDialog");
const artifactDialogTitle = document.getElementById("artifactDialogTitle");
const artifactDialogMeta = document.getElementById("artifactDialogMeta");
const artifactDialogSummary = document.getElementById("artifactDialogSummary");
const artifactDialogBody = document.getElementById("artifactDialogBody");
const artifactDialogLike = document.getElementById("artifactDialogLike");
const artifactDialogDelete = document.getElementById("artifactDialogDelete");
const artifactDialogClose = document.getElementById("artifactDialogClose");

const ARTIFACT_PAGE_SIZE = 20;
let artifactOffset = 0;
let artifactTotal = 0;
let artifactLoading = false;
let shuffleSeed = Math.floor(Math.random() * 2147483647);
let activeDialogArtifactId = null;
const artifactsById = new Map();
let likeClickTimer = null;

function setStatus(text) {
  statusText.textContent = text;
}

function formatTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
}

function clearChildren(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

function escapeHtml(text) {
  return String(text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderInlineMarkdown(text) {
  const codeParts = [];
  let html = escapeHtml(text).replace(/`([^`]+)`/g, (_, code) => {
    const marker = `\u0000CODE${codeParts.length}\u0000`;
    codeParts.push(`<code>${code}</code>`);
    return marker;
  });

  html = html
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (_, label, url) => {
      const href = url.replace(/&amp;/g, "&");
      return `<a href="${href}" target="_blank" rel="noopener noreferrer">${label}</a>`;
    })
    .replace(/\*\*\s*([^*]+?)\s*\*\*/g, "<strong>$1</strong>")
    .replace(/__\s*([^_]+?)\s*__/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
    .replace(/(^|[^_])_([^_\n]+)_/g, "$1<em>$2</em>");

  return html.replace(/\u0000CODE(\d+)\u0000/g, (_, index) => codeParts[Number(index)] || "");
}

function renderMarkdown(markdown) {
  const lines = String(markdown || "").replace(/\r\n/g, "\n").split("\n");
  const html = [];
  let paragraph = [];
  let listStack = [];
  let inCodeBlock = false;
  let codeLines = [];

  function closeParagraph() {
    if (!paragraph.length) {
      return;
    }
    html.push(`<p>${renderInlineMarkdown(paragraph.join(" "))}</p>`);
    paragraph = [];
  }

  function closeListsTo(indent = -1) {
    while (listStack.length && listStack[listStack.length - 1].indent >= indent) {
      html.push(`</${listStack.pop().tag}>`);
    }
  }

  function closeAllLists() {
    closeListsTo(-1);
  }

  for (const rawLine of lines) {
    const line = rawLine.replace(/\s+$/g, "");
    const fence = line.match(/^\s*```/);
    if (fence) {
      closeParagraph();
      closeAllLists();
      if (inCodeBlock) {
        html.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
        codeLines = [];
        inCodeBlock = false;
      } else {
        inCodeBlock = true;
      }
      continue;
    }

    if (inCodeBlock) {
      codeLines.push(rawLine);
      continue;
    }

    if (!line.trim()) {
      closeParagraph();
      closeAllLists();
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      closeParagraph();
      closeAllLists();
      const level = Math.min(6, heading[1].length);
      html.push(`<h${level}>${renderInlineMarkdown(heading[2].trim())}</h${level}>`);
      continue;
    }

    const listItem = line.match(/^(\s*)(?:([-*+])|(\d+)\.)\s+(.+)$/);
    if (listItem) {
      closeParagraph();
      const indent = listItem[1].length;
      const tag = listItem[3] ? "ol" : "ul";
      closeListsTo(indent + 1);
      if (
        listStack.length &&
        listStack[listStack.length - 1].indent === indent &&
        listStack[listStack.length - 1].tag !== tag
      ) {
        closeListsTo(indent);
      }
      const current = listStack[listStack.length - 1];
      if (!current || current.indent < indent || current.tag !== tag) {
        const startAttr = tag === "ol" && listItem[3] ? ` start="${listItem[3]}"` : "";
        html.push(`<${tag}${startAttr}>`);
        listStack.push({ indent, tag });
      }
      html.push(`<li>${renderInlineMarkdown(listItem[4].trim())}</li>`);
      continue;
    }

    closeAllLists();
    paragraph.push(line.trim());
  }

  if (inCodeBlock) {
    html.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
  }
  closeParagraph();
  closeAllLists();
  return html.join("");
}

function setRenderedMarkdown(element, markdown) {
  element.dataset.rawMarkdown = markdown || "";
  element.innerHTML = renderMarkdown(markdown || "");
}

function renderEmpty(target, text) {
  const node = document.createElement("div");
  node.className = "empty";
  node.textContent = text;
  target.appendChild(node);
}

function artifactTypeLabel(type) {
  return {
    novel: "小说",
    poetry: "诗歌",
    script: "剧本",
    worldbuilding: "世界观",
    persona: "自我设定",
    notes: "札记",
    other: "其他",
  }[type] || type || "其他";
}

function excerptText(text, maxLength = 120) {
  const cleaned = String(text || "")
    .replace(/[#*_`>\[\]()]/g, "")
    .replace(/\s+/g, " ")
    .trim();
  if (cleaned.length <= maxLength) return cleaned;
  return `${cleaned.slice(0, maxLength - 1)}…`;
}

function updateLoadMoreButton() {
  loadMoreButton.hidden = artifactOffset >= artifactTotal;
  loadMoreButton.disabled = artifactLoading;
}

function renderLikeButton(item, className = "like-button") {
  const button = document.createElement("button");
  button.className = className;
  button.type = "button";
  button.dataset.artifactId = String(item.id);
  button.innerHTML = `赞 <span class="like-count" data-artifact-id="${item.id}">${Number(item.likes || 0)}</span>`;
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    handleLikeClick(event, item.id);
  });
  return button;
}

function renderDeleteButton(item, className = "delete-artifact-button") {
  const button = document.createElement("button");
  button.className = className;
  button.type = "button";
  button.dataset.artifactId = String(item.id);
  button.innerHTML = `
    <svg class="artifact-delete-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M3 6h18" />
      <path d="M8 6V4h8v2" />
      <path d="M6 6l1 18h10l1-18" />
      <path d="M10 11v7" />
      <path d="M14 11v7" />
    </svg>
  `;
  button.title = "删除成果";
  button.setAttribute("aria-label", `删除成果 ${item.title || item.id}`);
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    deleteArtifact(item.id).catch((error) => setStatus(`删除失败: ${error.message}`));
  });
  return button;
}

function handleLikeClick(event, artifactId) {
  window.clearTimeout(likeClickTimer);
  if (event.detail >= 2) {
    dislikeArtifact(artifactId).catch((error) => setStatus(`减赞失败: ${error.message}`));
    return;
  }
  likeClickTimer = window.setTimeout(() => {
    likeArtifact(artifactId).catch((error) => setStatus(`点赞失败: ${error.message}`));
  }, 220);
}

function renderArtifactCard(item) {
  artifactsById.set(Number(item.id), item);
  const article = document.createElement("article");
  article.className = "artifact-card";
  article.dataset.artifactCardId = String(item.id);
  article.tabIndex = 0;
  article.setAttribute("role", "button");
  article.setAttribute("aria-label", `打开成果 ${item.title || "未命名成果"}`);
  article.addEventListener("click", () => openArtifactDialog(Number(item.id)));
  article.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openArtifactDialog(Number(item.id));
    }
  });

  const pill = document.createElement("span");
  pill.className = "type-pill";
  pill.textContent = artifactTypeLabel(item.artifact_type);

  const cardHead = document.createElement("div");
  cardHead.className = "artifact-card-head";
  cardHead.append(pill, renderDeleteButton(item, "delete-artifact-button artifact-card-delete"));

  const title = document.createElement("h3");
  title.className = "artifact-title";
  title.textContent = item.title || "未命名成果";

  const summary = document.createElement("p");
  summary.className = "artifact-card-summary";
  summary.textContent = excerptText(item.summary || item.content || "", 128) || "没有简介。";

  const meta = document.createElement("div");
  meta.className = "meta";
  const series = item.series_title ? ` · ${item.series_title}` : "";
  const episode = item.episode_index != null ? ` · 第 ${item.episode_index} 集` : "";
  meta.textContent = `#${item.id}${series}${episode} · ${formatTime(item.created_at)}`;

  const footer = document.createElement("div");
  footer.className = "artifact-card-footer";
  footer.append(meta, renderLikeButton(item));

  article.append(cardHead, title, summary, footer);
  return article;
}

function renderArtifacts(payload, append = false) {
  if (!append) {
    clearChildren(artifactList);
    artifactsById.clear();
  }
  artifactTotal = Number(payload.total ?? 0);
  artifactCount.textContent = `${artifactOffset}/${artifactTotal}`;

  const items = payload.items || [];
  if (!items.length) {
    if (!append) {
      renderEmpty(artifactList, "暂无成果");
    }
    updateLoadMoreButton();
    return;
  }
  artifactOffset += items.length;
  artifactCount.textContent = `${artifactOffset}/${artifactTotal}`;

  for (const item of items) {
    artifactList.appendChild(renderArtifactCard(item));
  }
  updateLoadMoreButton();
}

function updateLikeCounts(artifactId, likes) {
  const item = artifactsById.get(Number(artifactId));
  if (item) item.likes = likes;
  document.querySelectorAll(`.like-count[data-artifact-id="${artifactId}"]`).forEach((node) => {
    node.textContent = String(likes);
  });
  if (activeDialogArtifactId === Number(artifactId)) {
    const count = artifactDialogLike.querySelector("span");
    if (count) count.textContent = String(likes);
  }
}

async function likeArtifact(artifactId) {
  const response = await fetch(`/api/artifacts/${artifactId}/like`, { method: "POST" });
  if (!response.ok) throw new Error(`like ${response.status}`);
  const payload = await response.json();
  updateLikeCounts(payload.id, payload.likes);
}

async function dislikeArtifact(artifactId) {
  const response = await fetch(`/api/artifacts/${artifactId}/like`, { method: "DELETE" });
  if (!response.ok) throw new Error(`dislike ${response.status}`);
  const payload = await response.json();
  updateLikeCounts(payload.id, payload.likes);
}

function removeDeletedArtifact(artifactId) {
  const safeId = Number(artifactId);
  artifactsById.delete(safeId);
  document.querySelectorAll(`[data-artifact-card-id="${safeId}"]`).forEach((node) => node.remove());
  artifactTotal = Math.max(0, artifactTotal - 1);
  artifactOffset = Math.max(0, Math.min(artifactOffset - 1, artifactTotal));
  artifactCount.textContent = `${artifactOffset}/${artifactTotal}`;
  if (activeDialogArtifactId === safeId && artifactDialog.open) {
    artifactDialog.close();
  }
  if (!artifactList.querySelector(".artifact-card")) {
    clearChildren(artifactList);
    renderEmpty(artifactList, "暂无成果");
  }
  updateLoadMoreButton();
}

async function deleteArtifact(artifactId) {
  const item = artifactsById.get(Number(artifactId));
  const title = item?.title || `#${artifactId}`;
  if (!window.confirm(`确认删除成果「${title}」？此操作不会删除聊天记录。`)) {
    return;
  }
  const response = await fetch(`/api/artifacts/${artifactId}`, { method: "DELETE" });
  if (!response.ok) throw new Error(`delete ${response.status}`);
  const payload = await response.json();
  removeDeletedArtifact(payload.id);
  setStatus("成果已删除");
}

function openArtifactDialog(artifactId) {
  const item = artifactsById.get(Number(artifactId));
  if (!item) return;
  activeDialogArtifactId = Number(artifactId);
  artifactDialogTitle.textContent = item.title || "未命名成果";
  const series = item.series_title ? ` · ${item.series_title}` : "";
  const episode = item.episode_index != null ? ` · 第 ${item.episode_index} 集` : "";
  artifactDialogMeta.textContent = `#${item.id} · ${artifactTypeLabel(item.artifact_type)}${series}${episode} · ${formatTime(item.created_at)}`;
  artifactDialogSummary.textContent = item.summary || "";
  artifactDialogSummary.hidden = !item.summary;
  setRenderedMarkdown(artifactDialogBody, item.content || "");
  artifactDialogLike.dataset.artifactId = String(item.id);
  artifactDialogLike.innerHTML = `赞 <span class="like-count" data-artifact-id="${item.id}">${Number(item.likes || 0)}</span>`;
  artifactDialogDelete.dataset.artifactId = String(item.id);
  if (typeof artifactDialog.showModal === "function") {
    artifactDialog.showModal();
  } else {
    artifactDialog.setAttribute("open", "open");
  }
}

function renderRuns(payload) {
  clearChildren(runList);
  const items = payload.items || [];
  runCount.textContent = String(items.length);

  if (!items.length) {
    renderEmpty(runList, "暂无后台运行记录");
    return;
  }

  for (const item of items) {
    const row = document.createElement("div");
    row.className = "run";

    const main = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = `${item.title || "idle-agent"} · ${item.task_type || "other"}`;

    const meta = document.createElement("div");
    meta.className = "meta";
    const reason = item.interrupted_reason ? ` · ${item.interrupted_reason}` : "";
    meta.textContent = `${formatTime(item.started_at)}${reason}`;

    const status = document.createElement("span");
    status.className = "run-status";
    status.textContent = item.status || "unknown";

    main.append(title, meta);
    row.append(main, status);
    runList.appendChild(row);
  }
}

function resetArtifactPaging() {
  artifactOffset = 0;
  artifactTotal = 0;
}

async function loadData({ append = false } = {}) {
  if (artifactLoading) return;
  artifactLoading = true;
  setStatus("读取中");
  const params = new URLSearchParams();
  if (typeFilter.value) params.set("artifact_type", typeFilter.value);
  if (keywordFilter.value.trim()) params.set("keyword", keywordFilter.value.trim());
  if (seriesFilter.value.trim()) params.set("series_title", seriesFilter.value.trim());
  params.set("limit", String(ARTIFACT_PAGE_SIZE));
  params.set("offset", String(artifactOffset));
  params.set("sort", sortSelect.value || "created");
  params.set("order", orderSelect.value || "desc");
  params.set("sort_seed", String(shuffleSeed));
  updateLoadMoreButton();

  try {
    const [artifactsResp, runsResp, promptResp] = await Promise.all([
      fetch(`/api/artifacts?${params.toString()}`),
      fetch("/api/artifacts/runs?limit=80"),
      fetch("/api/artifacts/prompt"),
    ]);

    if (!artifactsResp.ok) throw new Error(`artifacts ${artifactsResp.status}`);
    if (!runsResp.ok) throw new Error(`runs ${runsResp.status}`);
    if (!promptResp.ok) throw new Error(`prompt ${promptResp.status}`);

    renderArtifacts(await artifactsResp.json(), append);
    renderRuns(await runsResp.json());
    const promptPayload = await promptResp.json();
    if (document.activeElement !== idlePromptInput) {
      idlePromptInput.value = promptPayload.prompt || "";
    }
    setStatus("已更新");
  } finally {
    artifactLoading = false;
    updateLoadMoreButton();
  }
}

let searchTimer = null;
function scheduleLoad() {
  window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(() => {
    resetArtifactPaging();
    loadData().catch((error) => setStatus(`失败: ${error.message}`));
  }, 250);
}

typeFilter.addEventListener("change", scheduleLoad);
keywordFilter.addEventListener("input", scheduleLoad);
seriesFilter.addEventListener("input", scheduleLoad);
sortSelect.addEventListener("change", () => {
  if (sortSelect.value === "random") {
    shuffleSeed = Math.floor(Math.random() * 2147483647);
  }
  scheduleLoad();
});
orderSelect.addEventListener("change", scheduleLoad);
refreshButton.addEventListener("click", () => {
  resetArtifactPaging();
  loadData().catch((error) => setStatus(`失败: ${error.message}`));
});
shuffleButton.addEventListener("click", () => {
  shuffleSeed = Math.floor(Math.random() * 2147483647);
  sortSelect.value = "random";
  resetArtifactPaging();
  loadData().catch((error) => setStatus(`失败: ${error.message}`));
});
loadMoreButton.addEventListener("click", () => {
  loadData({ append: true }).catch((error) => setStatus(`失败: ${error.message}`));
});
artifactDialogClose.addEventListener("click", () => artifactDialog.close());
artifactDialogLike.addEventListener("click", (event) => {
  if (activeDialogArtifactId != null) {
    handleLikeClick(event, activeDialogArtifactId);
  }
});
artifactDialogDelete.addEventListener("click", (event) => {
  event.stopPropagation();
  if (activeDialogArtifactId != null) {
    deleteArtifact(activeDialogArtifactId).catch((error) => setStatus(`删除失败: ${error.message}`));
  }
});
artifactDialog.addEventListener("close", () => {
  activeDialogArtifactId = null;
});
artifactDialog.addEventListener("click", (event) => {
  if (event.target === artifactDialog) {
    artifactDialog.close();
  }
});
savePromptButton.addEventListener("click", async () => {
  savePromptButton.disabled = true;
  setStatus("保存 Prompt 中");
  try {
    const response = await fetch("/api/artifacts/prompt", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: idlePromptInput.value }),
    });
    if (!response.ok) throw new Error(`prompt ${response.status}`);
    const payload = await response.json();
    idlePromptInput.value = payload.prompt || "";
    setStatus("Prompt 已保存");
  } catch (error) {
    setStatus(`保存失败: ${error.message}`);
  } finally {
    savePromptButton.disabled = false;
  }
});

loadData().catch((error) => setStatus(`失败: ${error.message}`));
