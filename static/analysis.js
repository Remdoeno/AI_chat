const statusText = document.getElementById("statusText");
const messagesEl = document.getElementById("messages");
const tracePanel = document.getElementById("tracePanel");
const backgroundPanel = document.getElementById("backgroundPanel");
const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("messageInput");
const sendButton = document.getElementById("sendButton");
const loadPreviousButton = document.getElementById("loadPreviousButton");
const resetButton = document.getElementById("resetButton");
const refreshTraceButton = document.getElementById("refreshTraceButton");
const temperatureInput = document.getElementById("temperatureInput");
const topPInput = document.getElementById("topPInput");
const proxyInput = document.getElementById("proxyInput");
const webSearchInput = document.getElementById("webSearchInput");
const analysisAttachImageButton = document.getElementById("analysisAttachImageButton");
const analysisWebSearchButton = document.getElementById("analysisWebSearchButton");
const analysisImageInput = document.getElementById("analysisImageInput");
const analysisAttachmentPreview = document.getElementById("analysisAttachmentPreview");

let sessionId = null;
let activeController = null;
let traceTimer = null;
let pendingAttachments = [];
let userStoppedGeneration = false;
let isMessageComposing = false;
let isLoadingPreviousSession = false;
let hasMorePreviousSessions = true;
let previousSessionArmedAt = 0;
let previousSessionHideTimer = 0;
const openTraceKeys = new Set();
const closedTraceKeys = new Set();
const openBackgroundKeys = new Set();
const closedBackgroundKeys = new Set();
const tracePayloadScrollPositions = new Map();
const backgroundPayloadScrollPositions = new Map();
const DEVICE_STORAGE_KEY = "qwen_device_id";
const CHAT_SAMPLING_STORAGE_KEY = "qwen_sampling_settings";
const ANALYSIS_SAMPLING_STORAGE_KEY = "qwen_analysis_sampling_settings";
let deviceId = localStorage.getItem(DEVICE_STORAGE_KEY) || "";

const MAX_ATTACHMENTS = 4;
const MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024;
const IMAGE_COMPRESSION_NOTICE_BYTES = 2 * 1024 * 1024;
const PREVIOUS_SESSION_ARM_MS = 1500;
const PREVIOUS_SESSION_MIN_RETRY_MS = 800;
const PREVIOUS_SESSION_DESKTOP_TOP_BUFFER = 96;
const HISTORY_REVEAL_ANIMATION_MS = 420;
const HISTORY_REVEAL_GAP_PX = 14;
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

function ordinalSuffix(day) {
  if (day % 100 >= 11 && day % 100 <= 13) {
    return "th";
  }
  if (day % 10 === 1) {
    return "st";
  }
  if (day % 10 === 2) {
    return "nd";
  }
  if (day % 10 === 3) {
    return "rd";
  }
  return "th";
}

function formatMessageTimestamp(value = new Date()) {
  const date = value instanceof Date ? value : new Date(value || Date.now());
  const safeDate = Number.isNaN(date.getTime()) ? new Date() : date;
  const months = ["Jan.", "Feb.", "Mar.", "Apr.", "May.", "Jun.", "Jul.", "Aug.", "Sep.", "Oct.", "Nov.", "Dec."];
  let hours = safeDate.getHours();
  const minutes = String(safeDate.getMinutes()).padStart(2, "0");
  const period = hours >= 12 ? "PM" : "AM";
  hours = hours % 12 || 12;
  const day = safeDate.getDate();
  return `${String(hours).padStart(2, "0")}:${minutes} ${period}, ${months[safeDate.getMonth()]} ${day}${ordinalSuffix(day)}, ${safeDate.getFullYear()}`;
}

function setAnalysisSendButtonGenerating(generating) {
  sendButton.classList.toggle("is-stopping", generating);
  if (generating) {
    sendButton.textContent = "■";
    sendButton.type = "button";
    sendButton.setAttribute("aria-label", "停止生成");
    sendButton.title = "停止生成";
    return;
  }
  sendButton.textContent = "发送";
  sendButton.type = "submit";
  sendButton.setAttribute("aria-label", "发送消息");
  sendButton.title = "发送消息";
}

function setAnalysisBusy(busy) {
  setAnalysisSendButtonGenerating(Boolean(busy && activeController));
  sendButton.disabled = false;
  messageInput.disabled = busy;
  analysisAttachImageButton.disabled = busy;
  analysisWebSearchButton.disabled = busy;
  syncPreviousAnalysisSessionButton();
}

function setAnalysisWebSearchEnabled(enabled) {
  webSearchInput.checked = Boolean(enabled);
  analysisWebSearchButton.classList.toggle("is-active", webSearchInput.checked);
  analysisWebSearchButton.setAttribute("aria-pressed", String(webSearchInput.checked));
  analysisWebSearchButton.title = webSearchInput.checked ? "本轮会联网搜索" : "启用联网搜索";
}

function syncPreviousAnalysisSessionButton() {
  if (!loadPreviousButton) {
    return;
  }
  loadPreviousButton.disabled = Boolean(activeController || isLoadingPreviousSession || !sessionId || !hasMorePreviousSessions);
  loadPreviousButton.textContent = hasMorePreviousSessions ? "加载上一段对话" : "已到第一段";
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

function scrollAnalysisChatToBottom() {
  if (analysisUsesMobileHistoryButton()) {
    window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "auto" });
    return;
  }
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function readChatModeProxyDefault() {
  try {
    const raw = localStorage.getItem(CHAT_SAMPLING_STORAGE_KEY);
    if (!raw) {
      return "";
    }
    const payload = JSON.parse(raw);
    return typeof payload.web_search_proxy === "string" ? payload.web_search_proxy.trim() : "";
  } catch {
    return "";
  }
}

function loadAnalysisSamplingSettings() {
  const chatModeProxy = readChatModeProxyDefault();
  try {
    const raw = localStorage.getItem(ANALYSIS_SAMPLING_STORAGE_KEY);
    if (!raw) {
      proxyInput.value = chatModeProxy;
      return;
    }
    const payload = JSON.parse(raw);
    if (payload && payload.temperature !== undefined) {
      temperatureInput.value = String(clampNumber(payload.temperature, 0, 2, 0.75));
    }
    if (payload && payload.top_p !== undefined) {
      topPInput.value = String(clampNumber(payload.top_p, 0, 1, 0.95));
    }
    proxyInput.value = typeof payload.web_search_proxy === "string" && payload.web_search_proxy.trim()
      ? payload.web_search_proxy.trim()
      : chatModeProxy;
  } catch {
    localStorage.removeItem(ANALYSIS_SAMPLING_STORAGE_KEY);
    proxyInput.value = chatModeProxy;
  }
}

function saveAnalysisSamplingSettings() {
  const payload = {
    temperature: clampNumber(temperatureInput.value, 0, 2, 0.75),
    top_p: clampNumber(topPInput.value, 0, 1, 0.95),
    web_search_proxy: proxyInput.value.trim(),
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

function appendMessage(role, text, attachments = [], options = {}) {
  const row = document.createElement("article");
  row.className = `analysis-message ${role}`;
  const label = document.createElement("div");
  label.className = "analysis-message-label";
  label.textContent = role === "user" ? "你" : "助手";
  const timestamp = document.createElement("div");
  timestamp.className = "analysis-message-timestamp";
  timestamp.textContent = formatMessageTimestamp(options.createdAt);
  const meta = document.createElement("div");
  meta.className = "analysis-message-meta";
  meta.append(label, timestamp);
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
  row.append(meta, body);
  if (options.prepend) {
    messagesEl.prepend(row);
  } else {
    messagesEl.append(row);
    if (options.scroll !== false) {
      scrollAnalysisChatToBottom();
    }
  }
  return body;
}

function resetPreviousAnalysisSessionLoadState() {
  previousSessionArmedAt = 0;
  window.clearTimeout(previousSessionHideTimer);
  previousSessionHideTimer = 0;
  isLoadingPreviousSession = false;
  hasMorePreviousSessions = true;
  removeAnalysisHistoryLoadIndicator();
  syncPreviousAnalysisSessionButton();
}

function analysisUsesMobileHistoryButton() {
  return window.matchMedia("(max-width: 760px)").matches;
}

function isNearAnalysisMessagesTop() {
  return messagesEl.scrollTop <= PREVIOUS_SESSION_DESKTOP_TOP_BUFFER;
}

function cancelPreviousAnalysisSessionPreparation() {
  if (!previousSessionArmedAt) {
    return;
  }
  previousSessionArmedAt = 0;
  removeAnalysisHistoryLoadIndicator(true);
}

function ensureAnalysisHistoryLoadIndicator() {
  let indicator = messagesEl.querySelector(".analysis-history-load");
  if (!indicator) {
    indicator = document.createElement("div");
    indicator.className = "analysis-history-load is-idle";
    indicator.textContent = "加载上一段对话";
    messagesEl.prepend(indicator);
  }
  return indicator;
}

function removeAnalysisHistoryLoadIndicator(animated = false) {
  const current = messagesEl.querySelector(".analysis-history-load");
  if (!current) {
    return;
  }
  if (!animated) {
    current.className = "analysis-history-load is-idle";
    current.textContent = "加载上一段对话";
    return;
  }
  current.classList.add("is-hiding");
  window.setTimeout(() => {
    current.className = "analysis-history-load is-idle";
    current.textContent = "加载上一段对话";
  }, 500);
}

function setAnalysisHistoryLoadState(state, text) {
  if (!text) {
    return;
  }
  const indicator = ensureAnalysisHistoryLoadIndicator();
  indicator.replaceChildren();
  indicator.className = `analysis-history-load is-${state}`;
  if (state === "loading") {
    const spinner = document.createElement("span");
    spinner.className = "analysis-history-load-spinner";
    spinner.setAttribute("aria-hidden", "true");
    const label = document.createElement("span");
    label.textContent = text;
    indicator.append(spinner, label);
  } else {
    indicator.textContent = text;
  }
}

function enterPreviousAnalysisSessionArmed() {
  if (
    analysisUsesMobileHistoryButton() ||
    activeController ||
    isLoadingPreviousSession ||
    !hasMorePreviousSessions ||
    !sessionId ||
    previousSessionArmedAt
  ) {
    return;
  }
  window.clearTimeout(previousSessionHideTimer);
  previousSessionHideTimer = 0;
  previousSessionArmedAt = Date.now();
  setAnalysisHistoryLoadState("armed", "加载上一段对话");
  previousSessionHideTimer = window.setTimeout(() => {
    if (Date.now() - previousSessionArmedAt >= PREVIOUS_SESSION_ARM_MS && !isLoadingPreviousSession) {
      previousSessionArmedAt = 0;
      removeAnalysisHistoryLoadIndicator(true);
    }
  }, PREVIOUS_SESSION_ARM_MS);
}

function armOrLoadPreviousAnalysisSession() {
  if (activeController || isLoadingPreviousSession || !hasMorePreviousSessions || !sessionId) {
    return;
  }
  if (!isNearAnalysisMessagesTop()) {
    cancelPreviousAnalysisSessionPreparation();
    return;
  }

  const now = Date.now();
  if (!previousSessionArmedAt) {
    enterPreviousAnalysisSessionArmed();
    return;
  }

  const elapsed = now - previousSessionArmedAt;
  if (elapsed < PREVIOUS_SESSION_MIN_RETRY_MS) {
    setAnalysisHistoryLoadState("waiting", "加载上一段对话");
    return;
  }
  if (elapsed <= PREVIOUS_SESSION_ARM_MS) {
    previousSessionArmedAt = 0;
    loadPreviousAnalysisSessionContext();
    return;
  }

  enterPreviousAnalysisSessionArmed();
}

function handleDesktopPreviousAnalysisSessionWheel(event) {
  if (analysisUsesMobileHistoryButton() || event.deltaY >= -24 || !isNearAnalysisMessagesTop()) {
    return;
  }
  event.preventDefault();
  messagesEl.scrollTop = 0;
  armOrLoadPreviousAnalysisSession();
}

function dampedHistoryScrollProgress(progress) {
  const t = Math.min(1, Math.max(0, progress));
  return 1 - Math.pow(1 - t, 3);
}

function animateHistoryScrollTo(targetTop, duration = HISTORY_REVEAL_ANIMATION_MS) {
  const startTop = messagesEl.scrollTop;
  const maxTop = Math.max(0, messagesEl.scrollHeight - messagesEl.clientHeight);
  const endTop = Math.max(0, Math.min(maxTop, targetTop));
  const delta = endTop - startTop;
  if (Math.abs(delta) < 1) {
    messagesEl.scrollTop = endTop;
    return;
  }

  const startedAt = performance.now();
  function step(now) {
    const progress = (now - startedAt) / duration;
    messagesEl.scrollTop = startTop + delta * dampedHistoryScrollProgress(progress);
    if (progress < 1) {
      window.requestAnimationFrame(step);
    } else {
      messagesEl.scrollTop = endTop;
    }
  }
  window.requestAnimationFrame(step);
}

function revealLastLoadedHistoryMessage(lastItem, preservedTop) {
  if (!lastItem) {
    messagesEl.scrollTop = preservedTop;
    return;
  }

  if (analysisUsesMobileHistoryButton()) {
    const targetTop = Math.max(0, lastItem.getBoundingClientRect().top + window.scrollY - HISTORY_REVEAL_GAP_PX);
    window.scrollTo({ top: targetTop, behavior: "smooth" });
    return;
  }

  const maxTop = Math.max(0, messagesEl.scrollHeight - messagesEl.clientHeight);
  const safePreservedTop = Math.max(0, Math.min(maxTop, preservedTop));
  messagesEl.scrollTop = safePreservedTop;
  const targetTop = Math.max(0, Math.min(safePreservedTop, lastItem.offsetTop - HISTORY_REVEAL_GAP_PX));
  animateHistoryScrollTo(targetTop);
}

function prependAnalysisHistoryMessages(messages) {
  const history = Array.isArray(messages) ? messages : [];
  if (!history.length) {
    return;
  }
  const indicator = messagesEl.querySelector(".analysis-history-load");
  if (indicator) {
    indicator.remove();
  }
  const previousHeight = messagesEl.scrollHeight;
  const previousTop = messagesEl.scrollTop;
  const loadedMessageItems = [];
  for (const message of [...history].reverse()) {
    const body = appendMessage(message.role === "assistant" ? "assistant" : "user", message.content || "", [], {
      prepend: true,
      scroll: false,
      createdAt: message.created_at,
    });
    loadedMessageItems.unshift(body.parentElement);
  }
  ensureAnalysisHistoryLoadIndicator();
  const preservedTop = messagesEl.scrollHeight - previousHeight + previousTop;
  revealLastLoadedHistoryMessage(loadedMessageItems.at(-1), preservedTop);
}

async function loadPreviousAnalysisSessionContext() {
  if (!sessionId || activeController || isLoadingPreviousSession || !hasMorePreviousSessions) {
    return;
  }
  isLoadingPreviousSession = true;
  syncPreviousAnalysisSessionButton();
  setAnalysisHistoryLoadState("loading", "加载上一段对话");
  setStatus("加载历史中");
  try {
    const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/load-previous?analysis_mode=1`, {
      method: "POST",
      headers: deviceIdentityHeaders(),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const payload = await response.json();
    hasMorePreviousSessions = Boolean(payload.has_more);
    if (!payload.loaded) {
      setAnalysisHistoryLoadState("done", "已经到第一段对话了");
      setStatus("已到最早对话");
      hasMorePreviousSessions = false;
      setTimeout(() => removeAnalysisHistoryLoadIndicator(true), 1400);
      return;
    }
    prependAnalysisHistoryMessages(payload.messages || []);
    setStatus(hasMorePreviousSessions ? "已加载上一段对话" : "已加载到最早对话");
    await refreshTraces();
  } catch (error) {
    setAnalysisHistoryLoadState("error", `加载失败：${error.message || error}`);
    setStatus("历史加载失败");
    setTimeout(() => removeAnalysisHistoryLoadIndicator(true), 1800);
  } finally {
    isLoadingPreviousSession = false;
    previousSessionArmedAt = 0;
    window.clearTimeout(previousSessionHideTimer);
    previousSessionHideTimer = 0;
    syncPreviousAnalysisSessionButton();
  }
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
  resetPreviousAnalysisSessionLoadState();
  ensureAnalysisHistoryLoadIndicator();
  syncPreviousAnalysisSessionButton();
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
  resetPreviousAnalysisSessionLoadState();
  messagesEl.replaceChildren();
  ensureAnalysisHistoryLoadIndicator();
  syncPreviousAnalysisSessionButton();
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
  sendButton.disabled = true;
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
  activeController = new AbortController();
  setAnalysisBusy(true);
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

sendButton.addEventListener("click", async (event) => {
  if (!activeController) {
    return;
  }
  event.preventDefault();
  await stopActiveGeneration();
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
temperatureInput.addEventListener("change", saveAnalysisSamplingSettings);
topPInput.addEventListener("change", saveAnalysisSamplingSettings);
proxyInput.addEventListener("change", saveAnalysisSamplingSettings);
temperatureInput.addEventListener("input", saveAnalysisSamplingSettings);
topPInput.addEventListener("input", saveAnalysisSamplingSettings);
proxyInput.addEventListener("input", saveAnalysisSamplingSettings);
analysisAttachImageButton.addEventListener("click", () => analysisImageInput.click());
analysisWebSearchButton.addEventListener("click", () => {
  setAnalysisWebSearchEnabled(!webSearchInput.checked);
  setStatus(webSearchInput.checked ? "联网搜索已开启" : "联网搜索已关闭");
  messageInput.focus();
});
analysisImageInput.addEventListener("change", () => handleImageFiles(analysisImageInput.files));
loadPreviousButton.addEventListener("click", () => loadPreviousAnalysisSessionContext());
messagesEl.addEventListener("wheel", handleDesktopPreviousAnalysisSessionWheel, { passive: false });

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
setAnalysisWebSearchEnabled(false);

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
