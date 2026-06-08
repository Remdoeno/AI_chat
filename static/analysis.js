const statusText = document.getElementById("statusText");
const messagesEl = document.getElementById("messages");
const tracePanel = document.getElementById("tracePanel");
const backgroundPanel = document.getElementById("backgroundPanel");
const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("messageInput");
const sendButton = document.getElementById("sendButton");
const stopButton = document.getElementById("stopButton");
const resetButton = document.getElementById("resetButton");
const refreshTraceButton = document.getElementById("refreshTraceButton");
const temperatureInput = document.getElementById("temperatureInput");
const topPInput = document.getElementById("topPInput");
const proxyInput = document.getElementById("proxyInput");
const webSearchInput = document.getElementById("webSearchInput");
const analysisAttachImageButton = document.getElementById("analysisAttachImageButton");
const analysisImageInput = document.getElementById("analysisImageInput");
const analysisAttachmentPreview = document.getElementById("analysisAttachmentPreview");

let sessionId = null;
let activeController = null;
let traceTimer = null;
let pendingAttachments = [];
let userStoppedGeneration = false;
let isMessageComposing = false;
const openTraceKeys = new Set();
const closedTraceKeys = new Set();
const openBackgroundKeys = new Set();
const closedBackgroundKeys = new Set();
const tracePayloadScrollPositions = new Map();
const backgroundPayloadScrollPositions = new Map();
const DEVICE_STORAGE_KEY = "qwen_device_id";
const ANALYSIS_SAMPLING_STORAGE_KEY = "qwen_analysis_sampling_settings";
let deviceId = localStorage.getItem(DEVICE_STORAGE_KEY) || "";

const MAX_ATTACHMENTS = 4;
const MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024;
const IMAGE_COMPRESSION_NOTICE_BYTES = 2 * 1024 * 1024;
const IMAGE_EXTENSION_MIME = {
  avif: "image/avif",
  bmp: "image/bmp",
  gif: "image/gif",
  heic: "image/heic",
  heif: "image/heif",
  ico: "image/x-icon",
  jfif: "image/jpeg",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  pjpeg: "image/jpeg",
  png: "image/png",
  svg: "image/svg+xml",
  tif: "image/tiff",
  tiff: "image/tiff",
  webp: "image/webp",
};

const TRACE_EVENT_LABELS = {
  request: "请求",
  model_prompt: "完整 prompt",
  model_call: "模型调用",
  embedding: "embedding",
  web_search: "联网搜索",
  web_page: "网页读取",
  web_page_error: "网页错误",
  memory_agent: "记忆整理",
  background_job: "后台任务",
};

function setStatus(text) {
  statusText.textContent = text;
}

function hasLargeAttachment(attachments) {
  return (attachments || []).some((attachment) => Number(attachment.size || 0) > IMAGE_COMPRESSION_NOTICE_BYTES);
}

function setAnalysisBusy(busy) {
  sendButton.disabled = busy;
  messageInput.disabled = busy;
  stopButton.hidden = !busy;
  stopButton.disabled = !busy;
}

function isUsableDeviceId(value) {
  return /^[A-Za-z0-9_-]{12,96}$/.test(String(value || "").trim());
}

function ensureDeviceId() {
  if (isUsableDeviceId(deviceId)) {
    return deviceId;
  }
  deviceId = crypto.randomUUID
    ? crypto.randomUUID().replace(/-/g, "")
    : `dev_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 18)}`;
  localStorage.setItem(DEVICE_STORAGE_KEY, deviceId);
  return deviceId;
}

function deviceIdentityHeaders() {
  return { "X-Qwen-Device-Id": ensureDeviceId() };
}

function jsonHeaders() {
  return { "Content-Type": "application/json", ...deviceIdentityHeaders() };
}

function clampNumber(value, min, max, fallback) {
  const parsed = Number.parseFloat(value);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.min(max, Math.max(min, parsed));
}

function isImeCompositionEvent(event) {
  return isMessageComposing || event.isComposing || event.keyCode === 229;
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
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_]+)__/g, "<strong>$1</strong>")
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

  for (const rawLine of lines) {
    const line = rawLine.replace(/\s+$/g, "");
    const fence = line.match(/^\s*```/);
    if (fence) {
      closeParagraph();
      closeListsTo(-1);
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
      continue;
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      closeParagraph();
      closeListsTo(-1);
      const level = heading[1].length + 2;
      html.push(`<h${level}>${renderInlineMarkdown(heading[2].trim())}</h${level}>`);
      continue;
    }

    const listItem = line.match(/^(\s*)(?:([-*+])|(\d+)\.)\s+(.+)$/);
    if (listItem) {
      closeParagraph();
      const indent = listItem[1].length;
      const tag = listItem[3] ? "ol" : "ul";
      while (listStack.length && listStack[listStack.length - 1].indent > indent) {
        html.push(`</${listStack.pop().tag}>`);
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

    closeListsTo(-1);
    paragraph.push(line.trim());
  }

  if (inCodeBlock) {
    html.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
  }
  closeParagraph();
  closeListsTo(-1);
  return html.join("");
}

function setRenderedMarkdown(element, markdown) {
  element.dataset.rawMarkdown = markdown || "";
  element.innerHTML = renderMarkdown(markdown || "");
}

function getRawMarkdown(element) {
  return element.dataset.rawMarkdown || element.textContent || "";
}

function loadAnalysisSamplingSettings() {
  try {
    const raw = localStorage.getItem(ANALYSIS_SAMPLING_STORAGE_KEY);
    if (!raw) {
      return;
    }
    const payload = JSON.parse(raw);
    if (payload && payload.temperature !== undefined) {
      temperatureInput.value = String(clampNumber(payload.temperature, 0, 2, 0.75));
    }
    if (payload && payload.top_p !== undefined) {
      topPInput.value = String(clampNumber(payload.top_p, 0, 1, 0.95));
    }
  } catch {
    localStorage.removeItem(ANALYSIS_SAMPLING_STORAGE_KEY);
  }
}

function saveAnalysisSamplingSettings() {
  const payload = {
    temperature: clampNumber(temperatureInput.value, 0, 2, 0.75),
    top_p: clampNumber(topPInput.value, 0, 1, 0.95),
  };
  localStorage.setItem(ANALYSIS_SAMPLING_STORAGE_KEY, JSON.stringify(payload));
}

function attachmentMime(file) {
  if (file.type && file.type.startsWith("image/")) {
    return file.type;
  }
  const suffix = file.name.split(".").pop().toLowerCase();
  return IMAGE_EXTENSION_MIME[suffix] || "";
}

function readImageAttachment(file) {
  return new Promise((resolve, reject) => {
    const mimeType = attachmentMime(file);
    if (!mimeType) {
      reject(new Error(`不支持的图片格式：${file.name}`));
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      resolve({
        name: file.name || "image",
        mime_type: mimeType,
        data_url: String(reader.result || ""),
        size: file.size,
      });
    };
    reader.onerror = () => reject(new Error(`读取失败：${file.name}`));
    reader.readAsDataURL(file);
  });
}

function renderAttachmentPreview() {
  analysisAttachmentPreview.replaceChildren();
  pendingAttachments.forEach((attachment, index) => {
    const item = document.createElement("button");
    item.className = "analysis-attachment-chip";
    item.type = "button";
    item.title = "点击移除";
    const image = document.createElement("img");
    image.src = attachment.data_url;
    image.alt = attachment.name;
    const label = document.createElement("span");
    label.textContent = attachment.name || `image${index + 1}`;
    item.append(image, label);
    item.addEventListener("click", () => {
      pendingAttachments = pendingAttachments.filter((_, itemIndex) => itemIndex !== index);
      renderAttachmentPreview();
    });
    analysisAttachmentPreview.append(item);
  });
}

async function handleImageFiles(files) {
  const selected = Array.from(files || []);
  if (!selected.length) {
    return;
  }
  const room = Math.max(0, MAX_ATTACHMENTS - pendingAttachments.length);
  const nextFiles = selected.slice(0, room);
  try {
    const nextAttachments = await Promise.all(nextFiles.map(readImageAttachment));
    pendingAttachments = [...pendingAttachments, ...nextAttachments].slice(0, MAX_ATTACHMENTS);
    renderAttachmentPreview();
  } catch (error) {
    setStatus(error.message || "图片读取失败");
  } finally {
    analysisImageInput.value = "";
  }
}

function appendMessage(role, text, attachments = []) {
  const row = document.createElement("article");
  row.className = `analysis-message ${role}`;
  const label = document.createElement("div");
  label.className = "analysis-message-label";
  label.textContent = role === "user" ? "你" : "Qwen";
  const body = document.createElement("div");
  body.className = "analysis-message-body";
  if (role === "assistant") {
    setRenderedMarkdown(body, text);
  } else {
    body.textContent = text;
  }
  if (attachments.length) {
    const images = document.createElement("div");
    images.className = "analysis-message-images";
    attachments.forEach((attachment) => {
      const image = document.createElement("img");
      image.src = attachment.data_url || attachment.image_url || "";
      image.alt = attachment.name || "image_url";
      images.append(image);
    });
    body.append(images);
  }
  row.append(label, body);
  messagesEl.append(row);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return body;
}

async function createSession() {
  const response = await fetch("/api/sessions", {
    method: "POST",
    headers: deviceIdentityHeaders(),
  });
  if (!response.ok) {
    throw new Error("session create failed");
  }
  const data = await response.json();
  sessionId = data.session_id;
  setStatus(`session ${sessionId.slice(0, 8)}`);
  await refreshTraces();
  await startOpeningPrompt(data);
}

async function startOpeningPrompt(payload) {
  if (!sessionId || activeController) {
    return;
  }
  const prompt = String(payload && payload.opening_prompt ? payload.opening_prompt : "").trim();
  if (!prompt) {
    return;
  }
  await sendMessage(prompt, {
    hiddenUser: true,
    showUser: false,
    maxTokens: 512,
    cachedOpening: true,
  });
}

async function resetSession() {
  if (!sessionId) {
    return createSession();
  }
  const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/reset`, {
    method: "POST",
    headers: deviceIdentityHeaders(),
  });
  if (!response.ok) {
    throw new Error("reset failed");
  }
  const data = await response.json();
  sessionId = data.session_id;
  messagesEl.replaceChildren();
  tracePanel.replaceChildren();
  setStatus(`session ${sessionId.slice(0, 8)}`);
  await startOpeningPrompt(data);
}

function parseSseBlock(block) {
  const lines = block.split(/\r?\n/);
  let event = "message";
  const data = [];
  for (const line of lines) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      data.push(line.slice(5).trimStart());
    }
  }
  return { event, data: data.join("\n") };
}

function renderPayload(payload) {
  return JSON.stringify(payload, null, 2);
}

function formatDuration(ms) {
  if (ms === null || ms === undefined) {
    return "";
  }
  if (ms >= 1000) {
    return `${(ms / 1000).toFixed(2)}s`;
  }
  return `${Number(ms).toFixed(1)}ms`;
}

function preserveScrollDuring(callback) {
  const scroller = tracePanel ? tracePanel.closest(".analysis-trace") : null;
  if (!scroller) {
    callback();
    return;
  }
  const scrollTop = scroller.scrollTop;
  callback();
  scroller.scrollTop = scrollTop;
}

function restorePayloadScroll(pre, positions, key) {
  const saved = positions.get(key);
  if (saved === undefined) {
    return;
  }
  const restore = () => {
    pre.scrollTop = saved;
  };
  restore();
  window.requestAnimationFrame(restore);
}

function rememberPayloadScroll(pre, positions, key) {
  pre.addEventListener("scroll", () => {
    positions.set(key, pre.scrollTop);
  });
}

function collectPayloadScrollPositions(container, datasetKey, positions) {
  if (!container) {
    return;
  }
  container.querySelectorAll("details").forEach((card) => {
    const key = card.dataset[datasetKey];
    const payload = card.querySelector("pre, .background-markdown");
    if (key && payload) {
      positions.set(key, payload.scrollTop);
    }
  });
}

function traceItemKey(item) {
  if (item.id !== undefined && item.id !== null) {
    return `id:${item.id}`;
  }
  return [
    item.trace_id || "",
    item.step_name || "",
    item.event_type || "",
    item.created_at || "",
  ].join("|");
}

function isTraceOpenByDefault(item) {
  return item.event_type === "request" || item.event_type === "model_prompt";
}

function traceSortValue(item) {
  if (Number.isFinite(Number(item.id))) {
    return Number(item.id);
  }
  const createdAt = Date.parse(item.created_at || "");
  if (Number.isFinite(createdAt)) {
    return createdAt;
  }
  return 0;
}

function sortTraceItemsNewestFirst(items) {
  return [...(items || [])].sort((left, right) => {
    const valueDiff = traceSortValue(right) - traceSortValue(left);
    if (valueDiff) {
      return valueDiff;
    }
    return String(right.trace_id || "").localeCompare(String(left.trace_id || ""));
  });
}

function renderTraceItem(item) {
  const key = traceItemKey(item);
  const card = document.createElement("details");
  card.className = `trace-card trace-${item.event_type}`;
  card.dataset.traceKey = key;
  card.open = openTraceKeys.has(key) || (!closedTraceKeys.has(key) && isTraceOpenByDefault(item));
  card.addEventListener("toggle", () => {
    if (card.open) {
      openTraceKeys.add(key);
      closedTraceKeys.delete(key);
    } else {
      closedTraceKeys.add(key);
      openTraceKeys.delete(key);
    }
  });
  const summary = document.createElement("summary");
  const duration = formatDuration(item.duration_ms);
  summary.textContent = [
    item.step_name,
    TRACE_EVENT_LABELS[item.event_type] || item.event_type,
    item.visitor_ip,
    duration,
  ].filter(Boolean).join(" · ");
  const meta = document.createElement("div");
  meta.className = "trace-meta";
  meta.textContent = `${item.created_at} · ${item.trace_id}`;
  const pre = document.createElement("pre");
  pre.textContent = renderPayload(item.payload);
  restorePayloadScroll(pre, tracePayloadScrollPositions, key);
  rememberPayloadScroll(pre, tracePayloadScrollPositions, key);
  card.append(summary, meta, pre);
  return card;
}

async function refreshTraces() {
  if (!sessionId) {
    return;
  }
  const url = `/api/analysis/traces?session_id=${encodeURIComponent(sessionId)}&limit=500`;
  const response = await fetch(url);
  if (response.status === 401) {
    window.location.href = "/analysis";
    return;
  }
  if (!response.ok) {
    setStatus("trace 读取失败");
    return;
  }
  const data = await response.json();
  collectPayloadScrollPositions(tracePanel, "traceKey", tracePayloadScrollPositions);
  preserveScrollDuring(() => {
    tracePanel.replaceChildren(...sortTraceItemsNewestFirst(data.items).map(renderTraceItem));
  });
}

function backgroundItemKey(kind, item) {
  return `${kind}:${item.id || item.run_id || item.title || item.created_at || ""}`;
}

function renderBackgroundItem(key, title, meta, content) {
  const card = document.createElement("details");
  card.className = "background-card";
  card.dataset.backgroundKey = key;
  card.open = openBackgroundKeys.has(key) && !closedBackgroundKeys.has(key);
  card.addEventListener("toggle", () => {
    if (card.open) {
      openBackgroundKeys.add(key);
      closedBackgroundKeys.delete(key);
    } else {
      closedBackgroundKeys.add(key);
      openBackgroundKeys.delete(key);
    }
  });
  const summary = document.createElement("summary");
  summary.textContent = title;
  const metaEl = document.createElement("div");
  metaEl.className = "trace-meta";
  metaEl.textContent = meta;
  const pre = document.createElement("pre");
  pre.textContent = content || "";
  restorePayloadScroll(pre, backgroundPayloadScrollPositions, key);
  rememberPayloadScroll(pre, backgroundPayloadScrollPositions, key);
  card.append(summary, metaEl, pre);
  return card;
}

function renderArtifactItem(artifact) {
  const key = backgroundItemKey("artifact", artifact);
  const card = document.createElement("details");
  card.className = "background-card background-artifact-card";
  card.dataset.backgroundKey = key;
  card.open = openBackgroundKeys.has(key) && !closedBackgroundKeys.has(key);
  card.addEventListener("toggle", () => {
    if (card.open) {
      openBackgroundKeys.add(key);
      closedBackgroundKeys.delete(key);
    } else {
      closedBackgroundKeys.add(key);
      openBackgroundKeys.delete(key);
    }
  });

  const summary = document.createElement("summary");
  summary.textContent = `artifact #${artifact.id} · ${artifact.title || artifact.artifact_type || "作品"}`;

  const metaEl = document.createElement("div");
  metaEl.className = "trace-meta";
  metaEl.textContent = [
    artifact.artifact_type,
    artifact.series_title,
    artifact.episode_index ? `EP ${artifact.episode_index}` : "",
    artifact.created_at,
    artifact.run_status ? `run: ${artifact.run_status}` : "",
  ].filter(Boolean).join(" · ");

  const body = document.createElement("div");
  body.className = "background-markdown";
  if (artifact.summary) {
    const summaryEl = document.createElement("div");
    summaryEl.className = "background-artifact-summary";
    summaryEl.textContent = artifact.summary;
    body.appendChild(summaryEl);
  }

  const contentEl = document.createElement("div");
  contentEl.className = "background-artifact-content";
  setRenderedMarkdown(contentEl, artifact.content || "");
  restorePayloadScroll(body, backgroundPayloadScrollPositions, key);
  rememberPayloadScroll(body, backgroundPayloadScrollPositions, key);
  body.appendChild(contentEl);

  card.append(summary, metaEl, body);
  return card;
}

async function refreshBackground() {
  if (!backgroundPanel) {
    return;
  }
  const response = await fetch("/api/analysis/background");
  if (response.status === 401) {
    window.location.href = "/analysis";
    return;
  }
  if (!response.ok) {
    backgroundPanel.textContent = "后台写作读取失败";
    return;
  }
  const data = await response.json();
  const items = [];
  (data.runs || []).slice(0, 8).forEach((run) => {
    const key = backgroundItemKey("run", run);
    items.push(
      renderBackgroundItem(
        key,
        `run #${run.id} · ${run.title || run.task_type || "idle"}`,
        [run.status, run.started_at, run.finished_at || run.updated_at].filter(Boolean).join(" · "),
        JSON.stringify(run, null, 2),
      ),
    );
  });
  (data.artifacts || []).slice(0, 8).forEach((artifact) => {
    items.push(renderArtifactItem(artifact));
  });
  collectPayloadScrollPositions(backgroundPanel, "backgroundKey", backgroundPayloadScrollPositions);
  preserveScrollDuring(() => {
    backgroundPanel.replaceChildren(...items);
  });
}

async function stopActiveGeneration() {
  if (!activeController) {
    return;
  }
  userStoppedGeneration = true;
  stopButton.disabled = true;
  try {
    if (sessionId) {
      await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/cancel`, {
        method: "POST",
        headers: deviceIdentityHeaders(),
        keepalive: true,
      });
    }
  } catch {
    // Still abort the browser stream immediately if the cancel request fails.
  }
  activeController.abort();
  setStatus("已停止");
}

async function sendMessage(text, options = {}) {
  const {
    hiddenUser = false,
    showUser = true,
    maxTokens = 8192,
  } = options;
  const attachmentsForMessage = hiddenUser ? [] : [...pendingAttachments];
  if (!hiddenUser) {
    pendingAttachments = [];
    renderAttachmentPreview();
  }
  if (showUser) {
    appendMessage("user", text, attachmentsForMessage);
  }
  const assistantBody = appendMessage("assistant", "");
  let assistantMarkdown = "";
  userStoppedGeneration = false;
  setAnalysisBusy(true);
  activeController = new AbortController();
  setStatus(hasLargeAttachment(attachmentsForMessage) ? "图片过大，狠狠压缩中..." : "生成中");
  try {
    const response = await fetch("/api/chat/stream", {
      method: "POST",
      headers: jsonHeaders(),
      signal: activeController.signal,
      body: JSON.stringify({
        session_id: sessionId,
        message: text,
        attachments: attachmentsForMessage,
        hidden_user: hiddenUser,
        cached_opening: Boolean(options.cachedOpening),
        web_search: webSearchInput.checked,
        web_search_proxy: proxyInput.value.trim(),
        temperature: clampNumber(temperatureInput.value, 0, 2, 0.75),
        top_p: clampNumber(topPInput.value, 0, 1, 0.95),
        max_tokens: maxTokens,
        analysis_mode: true,
      }),
    });
    if (!response.ok || !response.body) {
      throw new Error(await response.text());
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() || "";
      for (const block of blocks) {
        const parsed = parseSseBlock(block);
        if (!parsed.data) {
          continue;
        }
        const payload = JSON.parse(parsed.data);
        if (parsed.event === "token") {
          assistantMarkdown += payload.content || "";
          setRenderedMarkdown(assistantBody, assistantMarkdown);
          messagesEl.scrollTop = messagesEl.scrollHeight;
        } else if (parsed.event === "memory") {
          setStatus(payload.message || "回忆中");
        } else if (parsed.event === "search") {
          setStatus(payload.query ? `搜索 ${payload.query}` : `${payload.stage || "search"}`);
        } else if (parsed.event === "error") {
          assistantMarkdown += payload.message || "error";
          setRenderedMarkdown(assistantBody, assistantMarkdown);
        } else if (parsed.event === "stopped") {
          if (!assistantMarkdown.trim()) {
            assistantMarkdown = "[已停止]";
          } else if (!assistantMarkdown.includes("[已停止]")) {
            assistantMarkdown += "\n\n[已停止]";
          }
          setRenderedMarkdown(assistantBody, assistantMarkdown);
          setStatus("已停止");
          return;
        } else if (parsed.event === "done") {
          setStatus(`session ${sessionId.slice(0, 8)}`);
        }
      }
      await refreshTraces();
    }
  } catch (error) {
    if (error.name === "AbortError" && userStoppedGeneration) {
      if (!assistantMarkdown.trim()) {
        setRenderedMarkdown(assistantBody, "[已停止]");
      }
      setStatus("已停止");
    } else if (error.name !== "AbortError") {
      setRenderedMarkdown(assistantBody, `请求失败：${error.message || error}`);
      setStatus("错误");
    }
  } finally {
    activeController = null;
    setAnalysisBusy(false);
    messageInput.focus();
    await refreshTraces();
  }
}

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = messageInput.value.trim();
  if ((!text && !pendingAttachments.length) || !sessionId || activeController) {
    return;
  }
  messageInput.value = "";
  await sendMessage(text || "请分析这张图片。");
});

messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !isImeCompositionEvent(event)) {
    event.preventDefault();
    chatForm.requestSubmit();
  }
});

messageInput.addEventListener("compositionstart", () => {
  isMessageComposing = true;
});

messageInput.addEventListener("compositionend", () => {
  setTimeout(() => {
    isMessageComposing = false;
  }, 0);
});

resetButton.addEventListener("click", async () => {
  if (activeController) {
    await stopActiveGeneration();
  }
  await resetSession();
});

refreshTraceButton.addEventListener("click", refreshTraces);
stopButton.addEventListener("click", stopActiveGeneration);
temperatureInput.addEventListener("change", saveAnalysisSamplingSettings);
topPInput.addEventListener("change", saveAnalysisSamplingSettings);
temperatureInput.addEventListener("input", saveAnalysisSamplingSettings);
topPInput.addEventListener("input", saveAnalysisSamplingSettings);
analysisAttachImageButton.addEventListener("click", () => analysisImageInput.click());
analysisImageInput.addEventListener("change", () => handleImageFiles(analysisImageInput.files));

window.addEventListener("beforeunload", () => {
  if (sessionId) {
    const deviceIdQuery = `?device_id=${encodeURIComponent(ensureDeviceId())}`;
    fetch(`/api/sessions/${encodeURIComponent(sessionId)}/close${deviceIdQuery}`, {
      method: "POST",
      headers: deviceIdentityHeaders(),
      keepalive: true,
    }).catch(() => {
      navigator.sendBeacon(`/api/sessions/${encodeURIComponent(sessionId)}/close${deviceIdQuery}`);
    });
  }
});

loadAnalysisSamplingSettings();

createSession()
  .then(() => {
    refreshBackground();
    traceTimer = window.setInterval(() => {
      refreshTraces();
      refreshBackground();
    }, 1500);
  })
  .catch((error) => {
    setStatus(error.message || "初始化失败");
  });

window.addEventListener("pagehide", () => {
  if (traceTimer) {
    window.clearInterval(traceTimer);
  }
});
