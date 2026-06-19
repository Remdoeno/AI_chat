const typeFilter = document.getElementById("typeFilter");
const keywordFilter = document.getElementById("keywordFilter");
const seriesFilter = document.getElementById("seriesFilter");
const sortSelect = document.getElementById("sortSelect");
const orderSelect = document.getElementById("orderSelect");
const refreshButton = document.getElementById("refreshButton");
const shuffleButton = document.getElementById("shuffleButton");
const idleToggleButton = document.getElementById("idleToggleButton");
const idleStatusText = document.getElementById("idleStatusText");
const idlePromptInput = document.getElementById("idlePromptInput");
const savePromptButton = document.getElementById("savePromptButton");
const statusText = document.getElementById("statusText");
const artifactCount = document.getElementById("artifactCount");
const artifactList = document.getElementById("artifactList");
const loadMoreButton = document.getElementById("loadMoreButton");
const runCount = document.getElementById("runCount");
const idleProgress = document.getElementById("idleProgress");
const runList = document.getElementById("runList");
const artifactDialog = document.getElementById("artifactDialog");
const artifactDialogShell = artifactDialog ? artifactDialog.querySelector(".artifact-dialog-shell") : null;
const artifactDialogTitle = document.getElementById("artifactDialogTitle");
const artifactDialogMeta = document.getElementById("artifactDialogMeta");
const artifactDialogSummary = document.getElementById("artifactDialogSummary");
const artifactDialogBody = document.getElementById("artifactDialogBody");
const artifactDialogLike = document.getElementById("artifactDialogLike");
const artifactDialogDelete = document.getElementById("artifactDialogDelete");
const artifactDialogClose = document.getElementById("artifactDialogClose");
const artifactCommentCount = document.getElementById("artifactCommentCount");
const artifactComments = document.getElementById("artifactComments");
const artifactCommentForm = document.getElementById("artifactCommentForm");
const artifactCommentInput = document.getElementById("artifactCommentInput");
const artifactCommentSubmit = document.getElementById("artifactCommentSubmit");

const ARTIFACT_PAGE_SIZE = 20;
let artifactOffset = 0;
let artifactTotal = 0;
let artifactLoading = false;
let shuffleSeed = Math.floor(Math.random() * 2147483647);
let activeDialogArtifactId = null;
const artifactsById = new Map();
let likeClickTimer = null;
let idlePaused = false;
let activeArtifactComments = [];

function setStatus(text) {
  statusText.textContent = text;
}

function updateIdleToggle(paused) {
  idlePaused = Boolean(paused);
  idleStatusText.textContent = idlePaused ? "已暂停" : "运行中";
  idleToggleButton.textContent = idlePaused ? "开始生成" : "暂停生成";
  idleToggleButton.classList.toggle("is-paused", idlePaused);
  idleToggleButton.setAttribute("aria-pressed", idlePaused ? "true" : "false");
}

function renderArtifactIdleProgress(progress = {}) {
  if (!idleProgress) return;
  const stage = progress.stage || (idlePaused ? "paused" : "waiting");
  const label = progress.label || (idlePaused ? "已暂停" : "等待开启");
  const percent = Math.max(0, Math.min(100, Number(progress.percent || 0)));
  const watchdog = progress.watchdog || {};
  const warnings = Array.isArray(watchdog.warnings) ? watchdog.warnings : [];
  idleProgress.className = `idle-progress is-${stage}`;
  const detailParts = [
    progress.title ? `任务：${progress.title}` : "",
    progress.reason ? `原因：${progress.reason}` : "",
    progress.updated_at ? `更新：${formatTime(progress.updated_at)}` : "",
    warnings[0] && warnings[0].message ? `诊断：${warnings[0].message}` : "",
  ].filter(Boolean);
  idleProgress.innerHTML = `
    <div class="idle-progress-head">
      <strong>后台进度</strong>
      <span>${escapeHtml(label)} · ${percent}%</span>
    </div>
    <div class="idle-progress-bar"><div class="idle-progress-fill" style="width: ${percent}%"></div></div>
    <div class="idle-progress-detail">${escapeHtml(detailParts.join(" · ") || "等待空闲后自动创作。")}</div>
  `;
}

function backgroundTaskTime(item) {
  const value = item.updated_at || item.created_at || item.finished_at || item.started_at || (item.metadata && item.metadata.started_at) || "";
  const time = Date.parse(value);
  return Number.isNaN(time) ? 0 : time;
}

function formatDurationMs(value) {
  const ms = Number(value || 0);
  if (!Number.isFinite(ms) || ms <= 0) return "";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms / 60000)}min`;
}

function activityTitle(item) {
  const metadata = item.metadata || {};
  const task = metadata.task || item.event_type || "worker";
  const labels = {
    opening_cache: "缓存开场 prompt",
    memory_dedupe: "记忆去重",
    idle_write: "后台创作",
    memory_agent: "记忆整理",
    idle_worker_tick: "worker heartbeat",
    opening_cache_idle_refresh: "缓存开场 prompt",
    memory_dedupe_agent_run: "记忆去重",
    idle_agent_artifact_created: "成果写入",
    warning_idle_worker_watchdog: "worker watchdog",
  };
  return labels[task] || labels[item.event_type] || task;
}

function activityStatus(item) {
  const metadata = item.metadata || {};
  return metadata.status || metadata.reason || metadata.completed_task || item.event_type || "记录";
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

function iconSvg(className, paths) {
  return `
    <svg class="${className}" viewBox="0 0 24 24" aria-hidden="true">
      ${paths}
    </svg>
  `;
}

function likeIconSvg() {
  return iconSvg(
    "artifact-like-icon",
    `
      <path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3" />
      <path d="M7 11l4-8a3 3 0 0 1 3 3v4h5a2 2 0 0 1 2 2l-1 7a3 3 0 0 1-3 3H7z" />
    `,
  );
}

function commentIconSvg() {
  return iconSvg(
    "artifact-comment-icon",
    `
      <path d="M21 12a8 8 0 0 1-8 8H7l-4 3v-5a8 8 0 1 1 18-6z" />
      <path d="M8 11h8" />
      <path d="M8 15h5" />
    `,
  );
}

function renderLikeButton(item, className = "like-button") {
  const button = document.createElement("button");
  button.className = className;
  button.type = "button";
  button.dataset.artifactId = String(item.id);
  button.title = "点赞";
  button.setAttribute("aria-label", `点赞 ${item.title || item.id}`);
  button.innerHTML = `${likeIconSvg()}<span class="like-count" data-artifact-id="${item.id}">${Number(item.likes || 0)}</span>`;
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    handleLikeClick(event, item.id);
  });
  return button;
}

function renderCommentButton(item) {
  const button = document.createElement("button");
  button.className = "comment-count-button";
  button.type = "button";
  button.dataset.artifactId = String(item.id);
  button.title = "评论";
  button.setAttribute("aria-label", `评论 ${item.title || item.id}`);
  button.innerHTML = `${commentIconSvg()}<span class="comment-count" data-artifact-id="${item.id}">${Number(item.comment_count || 0)}</span>`;
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    openArtifactDialog(Number(item.id), { focusComment: true });
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

function artifactImages(item) {
  return Array.isArray(item && item.images) ? item.images : [];
}

function artifactCoverImage(item) {
  return item && item.cover_image ? item.cover_image : artifactImages(item)[0];
}

function renderArtifactImageGrid(images) {
  const grid = document.createElement("div");
  grid.className = "artifact-image-grid";
  for (const [index, imageItem] of artifactImages({ images }).entries()) {
    const url = imageItem && imageItem.public_url ? String(imageItem.public_url) : "";
    if (!url) {
      continue;
    }
    const figure = document.createElement("figure");
    figure.className = "artifact-image-item";
    const image = document.createElement("img");
    image.src = url;
    image.alt = imageItem.plan_title || `成果配图 ${index + 1}`;
    const download = document.createElement("a");
    download.className = "artifact-image-download";
    download.href = url;
    download.download = `wangcai-artifact-${index + 1}`;
    download.textContent = "下载";
    figure.append(image, download);
    grid.appendChild(figure);
  }
  return grid;
}

function renderArtifactInlineImage(imageItem, index) {
  const url = imageItem && imageItem.public_url ? String(imageItem.public_url) : "";
  if (!url) {
    return null;
  }
  const figure = document.createElement("figure");
  figure.className = "artifact-inline-image";
  const image = document.createElement("img");
  image.src = url;
  image.alt = imageItem.plan_title || `成果配图 ${index + 1}`;
  const caption = document.createElement("figcaption");
  caption.textContent = imageItem.plan_title || `配图 ${index + 1}`;
  const download = document.createElement("a");
  download.className = "artifact-image-download";
  download.href = url;
  download.download = `wangcai-artifact-${index + 1}`;
  download.textContent = "下载";
  figure.append(image, caption, download);
  return figure;
}

function paragraphInsertionIndexes(paragraphCount, imageCount) {
  if (paragraphCount <= 0 || imageCount <= 0) {
    return [];
  }
  const indexes = [];
  for (let index = 0; index < imageCount; index += 1) {
    const position = Math.max(0, Math.min(paragraphCount - 1, Math.floor(((index + 1) * paragraphCount) / (imageCount + 1))));
    indexes.push(position);
  }
  return indexes;
}

function renderArtifactBodyInline(content, images) {
  const wrapper = document.createElement("div");
  wrapper.className = "artifact-text-content";
  setRenderedMarkdown(wrapper, content || "");
  const imageItems = artifactImages({ images });
  if (!imageItems.length) {
    return wrapper;
  }
  const blocks = Array.from(wrapper.children).filter((node) => node.matches("p, ul, ol, blockquote, pre, h3, h4, h5, h6"));
  if (!blocks.length) {
    for (const [index, imageItem] of imageItems.entries()) {
      const figure = renderArtifactInlineImage(imageItem, index);
      if (figure) {
        wrapper.appendChild(figure);
      }
    }
    return wrapper;
  }
  const positions = paragraphInsertionIndexes(blocks.length, imageItems.length);
  const buckets = new Map();
  imageItems.forEach((imageItem, index) => {
    const position = positions[index] ?? blocks.length - 1;
    if (!buckets.has(position)) {
      buckets.set(position, []);
    }
    buckets.get(position).push({ imageItem, index });
  });
  for (const [position, entries] of buckets.entries()) {
    let anchor = blocks[position];
    for (const entry of entries) {
      const figure = renderArtifactInlineImage(entry.imageItem, entry.index);
      if (figure && anchor && anchor.parentElement) {
        anchor.insertAdjacentElement("afterend", figure);
        anchor = figure;
      }
    }
  }
  return wrapper;
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
  cardHead.append(pill);
  const imageCount = Number(item.image_count || artifactImages(item).length || 0);
  if (imageCount > 0) {
    const imagePill = document.createElement("span");
    imagePill.className = "type-pill image-count-pill";
    imagePill.textContent = `${imageCount} 图`;
    cardHead.append(imagePill);
  }

  const media = document.createElement("div");
  media.className = "artifact-card-media";
  const cover = artifactCoverImage(item);
  if (cover && cover.public_url) {
    const coverNode = document.createElement("img");
    coverNode.className = "artifact-card-cover";
    coverNode.src = cover.public_url;
    coverNode.alt = item.title || "成果配图";
    media.append(coverNode);
  } else {
    media.classList.add("artifact-card-media-empty");
  }

  const title = document.createElement("h3");
  title.className = "artifact-title";
  title.textContent = item.title || "未命名成果";

  const summary = document.createElement("p");
  summary.className = "artifact-card-summary";
  summary.textContent = excerptText(item.summary || item.content || "", 190) || "没有简介。";

  const meta = document.createElement("div");
  meta.className = "meta artifact-card-meta";
  const series = item.series_title ? ` · ${item.series_title}` : "";
  const episode = item.episode_index != null ? ` · 第 ${item.episode_index} 集` : "";
  meta.textContent = `#${item.id}${series}${episode} · ${formatTime(item.created_at)}`;

  const overlay = document.createElement("div");
  overlay.className = "artifact-card-overlay";
  overlay.append(cardHead, title, summary, meta);
  media.append(overlay);

  const footer = document.createElement("div");
  footer.className = "artifact-card-footer";
  const footerActions = document.createElement("div");
  footerActions.className = "artifact-card-actions";
  footerActions.append(renderCommentButton(item), renderLikeButton(item));
  footer.append(renderDeleteButton(item, "delete-artifact-button artifact-card-delete"), footerActions);

  article.append(media, footer);
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

function updateCommentCounts(artifactId, count) {
  const item = artifactsById.get(Number(artifactId));
  if (item) item.comment_count = count;
  document.querySelectorAll(`.comment-count[data-artifact-id="${artifactId}"]`).forEach((node) => {
    node.textContent = String(count);
  });
  if (activeDialogArtifactId === Number(artifactId)) {
    artifactCommentCount.textContent = String(count);
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

function renderCommentDeleteButton(item) {
  const button = document.createElement("button");
  button.className = "comment-delete-button";
  button.type = "button";
  button.title = "删除评论及后续回复";
  button.setAttribute("aria-label", `删除评论 ${item.id}`);
  button.innerHTML = `
    <svg class="artifact-delete-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M3 6h18" />
      <path d="M8 6V4h8v2" />
      <path d="M6 6l1 18h10l1-18" />
      <path d="M10 11v7" />
      <path d="M14 11v7" />
    </svg>
  `;
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    deleteArtifactComment(item.id).catch((error) => setStatus(`删除评论失败: ${error.message}`));
  });
  return button;
}

function renderCommentRow(item, { temporary = false } = {}) {
  const row = document.createElement("article");
  row.className = `comment-row ${item.role === "assistant" ? "assistant-comment" : "user-comment"}`;
  row.dataset.commentId = String(item.id);

  const head = document.createElement("div");
  head.className = "comment-head";
  const meta = document.createElement("span");
  meta.textContent = `${item.role === "assistant" ? "旺财" : item.author || "visitor"} · ${temporary ? "生成中" : formatTime(item.created_at)}`;
  head.appendChild(meta);
  if (!temporary) {
    head.appendChild(renderCommentDeleteButton(item));
  }

  const body = document.createElement("div");
  body.className = "comment-body";
  setRenderedMarkdown(body, item.content || "");

  row.append(head, body);
  return row;
}

function renderArtifactComments(items) {
  activeArtifactComments = items || [];
  clearChildren(artifactComments);
  if (!activeArtifactComments.length) {
    renderEmpty(artifactComments, "还没有评论");
  } else {
    for (const item of activeArtifactComments) {
      artifactComments.appendChild(renderCommentRow(item));
    }
  }
  updateCommentCounts(activeDialogArtifactId, activeArtifactComments.length);
}

async function loadArtifactComments(artifactId) {
  const response = await fetch(`/api/artifacts/${artifactId}/comments`);
  if (!response.ok) throw new Error(`comments ${response.status}`);
  const payload = await response.json();
  renderArtifactComments(payload.items || []);
  return payload;
}

async function deleteArtifactComment(commentId) {
  if (!window.confirm("确认删除这条评论及它后面的 AI 回复/追问？")) {
    return;
  }
  const response = await fetch(`/api/artifact-comments/${commentId}`, { method: "DELETE" });
  if (!response.ok) throw new Error(`comment delete ${response.status}`);
  if (activeDialogArtifactId != null) {
    await loadArtifactComments(activeDialogArtifactId);
  }
  resetArtifactPaging();
  loadData().catch((error) => setStatus(`刷新失败: ${error.message}`));
}

function parseSseBlocks(buffer) {
  const blocks = buffer.split("\n\n");
  return {
    complete: blocks.slice(0, -1),
    rest: blocks[blocks.length - 1] || "",
  };
}

function parseSseBlock(block) {
  let event = "message";
  const dataLines = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }
  const rawData = dataLines.join("\n");
  let data = {};
  if (rawData) {
    try {
      data = JSON.parse(rawData);
    } catch {
      data = { content: rawData };
    }
  }
  return { event, data };
}

async function submitArtifactComment(content) {
  if (activeDialogArtifactId == null) return;
  const parentId = activeArtifactComments.length
    ? activeArtifactComments[activeArtifactComments.length - 1].id
    : null;
  const response = await fetch(`/api/artifacts/${activeDialogArtifactId}/comments/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      content,
      parent_id: parentId,
      author: "visitor",
    }),
  });
  if (!response.ok || !response.body) throw new Error(`comment stream ${response.status}`);

  const decoder = new TextDecoder();
  const reader = response.body.getReader();
  let buffer = "";
  let assistantDraft = null;
  let assistantText = "";
  clearChildren(artifactComments);
  for (const item of activeArtifactComments) {
    artifactComments.appendChild(renderCommentRow(item));
  }

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parsed = parseSseBlocks(buffer);
    buffer = parsed.rest;
    for (const block of parsed.complete) {
      const { event, data } = parseSseBlock(block);
      if (event === "user_comment") {
        activeArtifactComments.push(data);
        artifactComments.appendChild(renderCommentRow(data));
        updateCommentCounts(activeDialogArtifactId, activeArtifactComments.length + 1);
      } else if (event === "token") {
        if (!assistantDraft) {
          assistantDraft = {
            id: "assistant-draft",
            role: "assistant",
            author: "旺财",
            content: "",
            created_at: "",
          };
          artifactComments.appendChild(renderCommentRow(assistantDraft, { temporary: true }));
        }
        assistantText += data.content || "";
        assistantDraft.content = assistantText;
        const body = artifactComments.querySelector('[data-comment-id="assistant-draft"] .comment-body');
        if (body) setRenderedMarkdown(body, assistantText);
      } else if (event === "done") {
        await loadArtifactComments(activeDialogArtifactId);
        resetArtifactPaging();
        loadData().catch((error) => setStatus(`刷新失败: ${error.message}`));
      } else if (event === "error") {
        throw new Error(data.message || "评论失败");
      }
    }
  }
}

function openArtifactDialog(artifactId, options = {}) {
  const item = artifactsById.get(Number(artifactId));
  if (!item) return;
  activeDialogArtifactId = Number(artifactId);
  activeArtifactComments = [];
  artifactDialog.scrollTop = 0;
  if (artifactDialogShell) artifactDialogShell.scrollTop = 0;
  artifactDialogTitle.textContent = item.title || "未命名成果";
  const series = item.series_title ? ` · ${item.series_title}` : "";
  const episode = item.episode_index != null ? ` · 第 ${item.episode_index} 集` : "";
  artifactDialogMeta.textContent = `#${item.id} · ${artifactTypeLabel(item.artifact_type)}${series}${episode} · ${formatTime(item.created_at)}`;
  artifactDialogSummary.textContent = item.summary || "";
  artifactDialogSummary.hidden = !item.summary;
  artifactDialogBody.replaceChildren();
  const images = artifactImages(item);
  artifactDialogBody.appendChild(renderArtifactBodyInline(item.content || "", images));
  artifactDialogLike.dataset.artifactId = String(item.id);
  artifactDialogLike.innerHTML = `${likeIconSvg()}<span class="like-count" data-artifact-id="${item.id}">${Number(item.likes || 0)}</span>`;
  artifactDialogDelete.dataset.artifactId = String(item.id);
  artifactCommentInput.value = "";
  clearChildren(artifactComments);
  renderEmpty(artifactComments, "读取评论中");
  artifactCommentCount.textContent = String(Number(item.comment_count || 0));
  if (typeof artifactDialog.showModal === "function") {
    artifactDialog.showModal();
  } else {
    artifactDialog.setAttribute("open", "open");
  }
  artifactDialog.scrollTop = 0;
  if (artifactDialogShell) artifactDialogShell.scrollTop = 0;
  loadArtifactComments(Number(item.id))
    .then(() => {
      if (options.focusComment) artifactCommentInput.focus();
    })
    .catch((error) => {
      clearChildren(artifactComments);
      renderEmpty(artifactComments, `评论读取失败: ${error.message}`);
    });
}

function renderRuns(payload) {
  clearChildren(runList);
  renderArtifactIdleProgress(payload.progress || {});
  const runs = (payload.items || []).slice(0, 3);
  runCount.textContent = String(runs.length);

  if (!runs.length) {
    renderEmpty(runList, "暂无后台写作记录");
    return;
  }

  for (const item of runs) {
    const row = document.createElement("div");
    row.className = "run";

    const main = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = `${item.title || "idle-agent"} · ${item.task_type || "other"}`;
    const meta = document.createElement("div");
    meta.className = "meta";
    const duration = formatDurationMs(item.duration_ms);
    const reason = item.interrupted_reason ? `原因：${item.interrupted_reason}` : "";
    meta.textContent = [
      `开始：${formatTime(item.started_at)}`,
      item.finished_at ? `结束：${formatTime(item.finished_at)}` : "",
      duration ? `用时：${duration}` : "",
      reason,
    ].filter(Boolean).join(" · ");

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
    const [artifactsResp, runsResp, promptResp, idleStatusResp] = await Promise.all([
      fetch(`/api/artifacts?${params.toString()}`),
      fetch("/api/artifacts/runs?limit=3"),
      fetch("/api/artifacts/prompt"),
      fetch("/api/artifacts/idle-status"),
    ]);

    if (!artifactsResp.ok) throw new Error(`artifacts ${artifactsResp.status}`);
    if (!runsResp.ok) throw new Error(`runs ${runsResp.status}`);
    if (!promptResp.ok) throw new Error(`prompt ${promptResp.status}`);
    if (!idleStatusResp.ok) throw new Error(`idle-status ${idleStatusResp.status}`);

    renderArtifacts(await artifactsResp.json(), append);
    renderRuns(await runsResp.json());
    const promptPayload = await promptResp.json();
    if (document.activeElement !== idlePromptInput) {
      idlePromptInput.value = promptPayload.prompt || "";
    }
    updateIdleToggle((await idleStatusResp.json()).paused);
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
idleToggleButton.addEventListener("click", async () => {
  idleToggleButton.disabled = true;
  const nextPaused = !idlePaused;
  setStatus(nextPaused ? "暂停后台创作中" : "恢复后台创作中");
  try {
    const response = await fetch("/api/artifacts/idle-status", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paused: nextPaused }),
    });
    if (!response.ok) throw new Error(`idle-status ${response.status}`);
    const payload = await response.json();
    updateIdleToggle(payload.paused);
    setStatus(payload.paused ? "后台创作已暂停" : "后台创作已开始");
  } catch (error) {
    setStatus(`切换失败: ${error.message}`);
  } finally {
    idleToggleButton.disabled = false;
  }
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
  activeArtifactComments = [];
});
artifactDialog.addEventListener("click", (event) => {
  if (event.target === artifactDialog) {
    artifactDialog.close();
  }
});
artifactCommentInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    artifactCommentForm.requestSubmit();
  }
});
artifactCommentForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const content = artifactCommentInput.value.trim();
  if (!content) {
    artifactCommentInput.focus();
    return;
  }
  artifactCommentSubmit.disabled = true;
  artifactCommentInput.disabled = true;
  setStatus("AI 正在回复评论");
  try {
    artifactCommentInput.value = "";
    await submitArtifactComment(content);
    setStatus("评论已回复");
  } catch (error) {
    setStatus(`评论失败: ${error.message}`);
  } finally {
    artifactCommentSubmit.disabled = false;
    artifactCommentInput.disabled = false;
    artifactCommentInput.focus();
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
