const messagesEl = document.getElementById("messages");
const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("messageInput");
const sendButton = document.getElementById("sendButton");
const attachImageButton = document.getElementById("attachImageButton");
const webSearchButton = document.getElementById("webSearchButton");
const imageInput = document.getElementById("imageInput");
const attachmentPreview = document.getElementById("attachmentPreview");
const resetButton = document.getElementById("resetButton");
const statusText = document.getElementById("statusText");
const bunnyLogoButton = document.getElementById("bunnyLogoButton");
const memoryAdminButton = document.getElementById("memoryAdminButton");
const memoryAdminDialog = document.getElementById("memoryAdminDialog");
const memoryAdminLoginForm = document.getElementById("memoryAdminLoginForm");
const memoryAdminPassword = document.getElementById("memoryAdminPassword");
const memoryAdminLoginStatus = document.getElementById("memoryAdminLoginStatus");
const memoryAdminCancelButton = document.getElementById("memoryAdminCancelButton");
const advancedOptions = document.getElementById("advancedOptions");
const temperatureRange = document.getElementById("temperatureRange");
const temperatureValue = document.getElementById("temperatureValue");
const topPRange = document.getElementById("topPRange");
const topPValue = document.getElementById("topPValue");
const webSearchProxyInput = document.getElementById("webSearchProxyInput");
const samplingSummary = document.getElementById("samplingSummary");
const confirmSamplingButton = document.getElementById("confirmSamplingButton");
const searchActivity = document.getElementById("searchActivity");
const searchActivityList = document.getElementById("searchActivityList");

const BUNNY_CLICK_WINDOW_MS = 1000;
const BUNNY_CLICK_TARGET = 4;
const SAMPLING_STORAGE_KEY = "qwen_sampling_settings";
const DEVICE_STORAGE_KEY = "qwen_device_id";
const DEFAULT_SAMPLING_SETTINGS = {
  temperature: 1,
  top_p: 0.95,
  web_search_proxy: "",
};
const MAX_ATTACHMENTS = 4;
const MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024;
const IMAGE_COMPRESSION_NOTICE_BYTES = 2 * 1024 * 1024;
const PREVIOUS_SESSION_ARM_MS = 3600;
const PREVIOUS_SESSION_MIN_RETRY_MS = 1000;
const PREVIOUS_SESSION_TOP_SETTLE_MS = 420;
const PREVIOUS_SESSION_PULL_THRESHOLD = 72;
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

let sessionId = null;
let activeController = null;
let isResetting = false;
let bunnyClickTimes = [];
let samplingSettings = loadSamplingSettings();
let activeAssistantBody = null;
let activeStopButton = null;
let userStoppedGeneration = false;
let pendingAttachments = [];
let webSearchEnabled = false;
let activeSearchQuery = "";
let isMessageComposing = false;
let deviceId = localStorage.getItem(DEVICE_STORAGE_KEY) || "";
let previousSessionArmedAt = 0;
let previousSessionTopReadyAt = Date.now();
let isLoadingPreviousSession = false;
let hasMorePreviousSessions = true;
let touchStartY = 0;
let touchPullDistance = 0;

function isUsableDeviceId(value) {
  return /^[A-Za-z0-9_-]{12,96}$/.test(String(value || "").trim());
}

function setStatus(text) {
  statusText.textContent = text;
}

function hasLargeAttachment(attachments) {
  return (attachments || []).some((attachment) => Number(attachment.size || 0) > IMAGE_COMPRESSION_NOTICE_BYTES);
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

function setBusy(busy) {
  sendButton.disabled = busy;
  resetButton.disabled = isResetting;
  messageInput.disabled = busy || isResetting;
  temperatureRange.disabled = busy || isResetting;
  topPRange.disabled = busy || isResetting;
  webSearchProxyInput.disabled = busy || isResetting;
  confirmSamplingButton.disabled = busy || isResetting;
  attachImageButton.disabled = busy || isResetting;
  webSearchButton.disabled = busy || isResetting;
}

function setWebSearchEnabled(enabled) {
  webSearchEnabled = Boolean(enabled);
  webSearchButton.classList.toggle("is-active", webSearchEnabled);
  webSearchButton.setAttribute("aria-pressed", String(webSearchEnabled));
  webSearchButton.title = webSearchEnabled ? "本轮会联网搜索" : "启用联网搜索";
}

function clearSearchActivity() {
  if (!searchActivity || !searchActivityList) {
    return;
  }
  searchActivityList.replaceChildren();
  searchActivity.hidden = true;
}

function setSearchActivity(text) {
  if (!searchActivity || !searchActivityList) {
    return;
  }
  const item = document.createElement("div");
  item.className = "search-activity-item";
  item.textContent = text;
  searchActivityList.replaceChildren(item);
  searchActivity.hidden = false;
}

function formatSearchTitle(title, fallback = "未命名网页") {
  const text = String(title || "").trim();
  return text.length > 80 ? `${text.slice(0, 79)}…` : text || fallback;
}

function formatSearchUrl(url) {
  const text = String(url || "").trim();
  if (!text) {
    return "";
  }
  try {
    const parsed = new URL(text);
    return parsed.hostname + parsed.pathname.replace(/\/$/, "");
  } catch {
    return text.length > 90 ? `${text.slice(0, 89)}…` : text;
  }
}

function formatSearchExcerpt(excerpt) {
  const text = String(excerpt || "").replace(/\s+/g, " ").trim();
  return text.length > 100 ? `${text.slice(0, 99)}…` : text;
}

function formatSearchTarget(target) {
  if (!target) {
    return "搜索服务";
  }
  try {
    const url = new URL(target);
    return url.hostname || target;
  } catch {
    return String(target);
  }
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

function formatSamplingValue(value) {
  return value.toFixed(2);
}

function loadSamplingSettings() {
  try {
    const raw = localStorage.getItem(SAMPLING_STORAGE_KEY);
    if (!raw) {
      return { ...DEFAULT_SAMPLING_SETTINGS };
    }
    const parsed = JSON.parse(raw);
    return {
      temperature: clampNumber(parsed.temperature, 0, 2, DEFAULT_SAMPLING_SETTINGS.temperature),
      top_p: clampNumber(parsed.top_p, 0.05, 1, DEFAULT_SAMPLING_SETTINGS.top_p),
      web_search_proxy: typeof parsed.web_search_proxy === "string"
        ? parsed.web_search_proxy.trim()
        : DEFAULT_SAMPLING_SETTINGS.web_search_proxy,
    };
  } catch {
    return { ...DEFAULT_SAMPLING_SETTINGS };
  }
}

function saveSamplingSettings(nextSettings) {
  samplingSettings = {
    temperature: clampNumber(nextSettings.temperature, 0, 2, DEFAULT_SAMPLING_SETTINGS.temperature),
    top_p: clampNumber(nextSettings.top_p, 0.05, 1, DEFAULT_SAMPLING_SETTINGS.top_p),
    web_search_proxy: typeof nextSettings.web_search_proxy === "string"
      ? nextSettings.web_search_proxy.trim()
      : DEFAULT_SAMPLING_SETTINGS.web_search_proxy,
  };
  localStorage.setItem(SAMPLING_STORAGE_KEY, JSON.stringify(samplingSettings));
  syncSamplingControlsFromSettings();
}

function updateSamplingSummary() {
  const temperature = clampNumber(temperatureRange.value, 0, 2, DEFAULT_SAMPLING_SETTINGS.temperature);
  const topP = clampNumber(topPRange.value, 0.05, 1, DEFAULT_SAMPLING_SETTINGS.top_p);
  temperatureValue.value = formatSamplingValue(temperature);
  topPValue.value = formatSamplingValue(topP);
  samplingSummary.textContent = `Temp ${formatSamplingValue(temperature)} · Top-p ${formatSamplingValue(topP)}`;
}

function syncSamplingControlsFromSettings() {
  temperatureRange.value = formatSamplingValue(samplingSettings.temperature);
  topPRange.value = formatSamplingValue(samplingSettings.top_p);
  webSearchProxyInput.value = samplingSettings.web_search_proxy;
  updateSamplingSummary();
}

function openAdvancedOptions() {
  syncSamplingControlsFromSettings();
  advancedOptions.hidden = false;
  advancedOptions.classList.add("is-visible");
  temperatureRange.focus();
}

function hideAdvancedOptions() {
  advancedOptions.classList.remove("is-visible");
  advancedOptions.hidden = true;
}

function handleBunnyLogoClick() {
  const now = Date.now();
  bunnyClickTimes = [...bunnyClickTimes, now].filter((time) => now - time <= BUNNY_CLICK_WINDOW_MS);
  if (bunnyClickTimes.length >= BUNNY_CLICK_TARGET) {
    bunnyClickTimes = [];
    openAdvancedOptions();
  }
}

function getSamplingSettings() {
  return { ...samplingSettings };
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function isAtMessagesTop() {
  return messagesEl.scrollTop <= 4;
}

function removeHistoryLoadIndicator(animated = false) {
  const current = messagesEl.querySelector(".history-load");
  if (!current) {
    return;
  }
  if (!animated) {
    current.remove();
    return;
  }
  current.classList.add("is-hiding");
  setTimeout(() => current.remove(), 240);
}

function setHistoryLoadState(state, text) {
  removeHistoryLoadIndicator();
  if (!text) {
    return;
  }
  const indicator = document.createElement("div");
  indicator.className = `history-load is-${state} is-entering`;
  indicator.textContent = text;
  messagesEl.prepend(indicator);
  requestAnimationFrame(() => {
    indicator.classList.remove("is-entering");
  });
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
      // blank lines inside lists should not reset ordered numbering
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

function createBubble(role, content = "", attachments = [], options = {}) {
  const item = document.createElement("article");
  item.className = `message ${role}`;

  const label = document.createElement("div");
  label.className = "message-label";
  label.textContent = role === "user" ? "你" : "Qwen";

  const body = document.createElement("div");
  body.className = "message-body";
  if (attachments.length) {
    if (content) {
      const text = document.createElement("div");
      if (role === "assistant") {
        setRenderedMarkdown(text, content);
      } else {
        text.textContent = content;
      }
      body.appendChild(text);
    }
    const images = document.createElement("div");
    images.className = "message-attachments";
    for (const attachment of attachments) {
      const image = document.createElement("img");
      image.src = attachment.data_url;
      image.alt = attachment.name || "uploaded image";
      images.appendChild(image);
    }
    body.appendChild(images);
  } else if (role === "assistant") {
    setRenderedMarkdown(body, content);
  } else {
    body.textContent = content;
  }

  item.append(label, body);
  if (options.prepend) {
    messagesEl.prepend(item);
  } else {
    messagesEl.appendChild(item);
    if (options.scroll !== false) {
      scrollToBottom();
    }
  }
  return body;
}

function attachInlineStopButton(assistantBody) {
  const item = assistantBody.parentElement;
  const button = document.createElement("button");
  button.className = "message-stop-button";
  button.type = "button";
  button.textContent = "■";
  button.setAttribute("aria-label", "停止生成");
  button.title = "停止生成";
  button.addEventListener("click", stopActiveGeneration);
  item.appendChild(button);
  activeStopButton = button;
}

function removeInlineStopButton() {
  if (activeStopButton) {
    activeStopButton.remove();
    activeStopButton = null;
  }
}

function clearMessages() {
  messagesEl.replaceChildren();
}

function resetPreviousSessionLoadState() {
  previousSessionArmedAt = 0;
  previousSessionTopReadyAt = Date.now();
  isLoadingPreviousSession = false;
  hasMorePreviousSessions = true;
  removeHistoryLoadIndicator();
}

function resetPreviousSessionArmFromScroll() {
  if (!previousSessionArmedAt) {
    return;
  }
  previousSessionArmedAt = 0;
  removeHistoryLoadIndicator(true);
}

function handleMessagesScroll() {
  if (!isAtMessagesTop()) {
    previousSessionTopReadyAt = 0;
    resetPreviousSessionArmFromScroll();
    return;
  }
  if (!previousSessionTopReadyAt) {
    previousSessionTopReadyAt = Date.now() + PREVIOUS_SESSION_TOP_SETTLE_MS;
  }
}

function isPreviousSessionTopReady() {
  return isAtMessagesTop() && previousSessionTopReadyAt > 0 && Date.now() >= previousSessionTopReadyAt;
}

function prependHistoryMessages(messages) {
  const history = Array.isArray(messages) ? messages : [];
  if (!history.length) {
    return;
  }

  removeHistoryLoadIndicator();
  const previousHeight = messagesEl.scrollHeight;
  const previousTop = messagesEl.scrollTop;
  for (const message of [...history].reverse()) {
    createBubble(message.role === "assistant" ? "assistant" : "user", message.content || "", [], {
      prepend: true,
      scroll: false,
    });
  }
  messagesEl.scrollTop = messagesEl.scrollHeight - previousHeight + previousTop;
}

async function loadPreviousSessionContext() {
  if (!sessionId || activeController || isLoadingPreviousSession || !hasMorePreviousSessions) {
    return;
  }

  isLoadingPreviousSession = true;
  setHistoryLoadState("loading", "正在加载上一段对话...");
  setStatus("加载历史中");

  try {
    const response = await fetch(`/api/sessions/${sessionId}/load-previous`, {
      method: "POST",
      headers: deviceIdentityHeaders(),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const payload = await response.json();
    hasMorePreviousSessions = Boolean(payload.has_more);

    if (!payload.loaded) {
      setHistoryLoadState("done", "已经到第一段对话了");
      setStatus("已到最早对话");
      setTimeout(() => removeHistoryLoadIndicator(true), 1400);
      return;
    }

    prependHistoryMessages(payload.messages || []);
    setStatus(hasMorePreviousSessions ? "已加载上一段对话" : "已加载到最早对话");
  } catch (error) {
    setHistoryLoadState("error", `加载失败：${error.message}`);
    setStatus("历史加载失败");
    setTimeout(() => removeHistoryLoadIndicator(true), 1800);
  } finally {
    isLoadingPreviousSession = false;
    previousSessionArmedAt = 0;
  }
}

function armOrLoadPreviousSession() {
  if (activeController || isLoadingPreviousSession || !hasMorePreviousSessions || !sessionId) {
    return;
  }
  if (!isPreviousSessionTopReady()) {
    handleMessagesScroll();
    return;
  }

  const now = Date.now();
  if (previousSessionArmedAt) {
    const elapsed = now - previousSessionArmedAt;
    if (elapsed < PREVIOUS_SESSION_MIN_RETRY_MS) {
      setHistoryLoadState("waiting", "再等一下，再拉/滚一次接上段对话");
      return;
    }
    if (elapsed <= PREVIOUS_SESSION_ARM_MS) {
      previousSessionArmedAt = 0;
      loadPreviousSessionContext();
      return;
    }
  }

  previousSessionArmedAt = now;
  setHistoryLoadState("armed", "再拉/滚一次接上段对话");
  setTimeout(() => {
    if (Date.now() - previousSessionArmedAt >= PREVIOUS_SESSION_ARM_MS && !isLoadingPreviousSession) {
      previousSessionArmedAt = 0;
      removeHistoryLoadIndicator(true);
    }
  }, PREVIOUS_SESSION_ARM_MS + 80);
}

function renderAttachmentPreview() {
  attachmentPreview.replaceChildren();
  for (const [index, attachment] of pendingAttachments.entries()) {
    const chip = document.createElement("div");
    chip.className = "attachment-chip";

    const image = document.createElement("img");
    image.src = attachment.data_url;
    image.alt = attachment.name || "uploaded image";

    const name = document.createElement("span");
    name.className = "attachment-name";
    name.textContent = attachment.name || "image";

    const remove = document.createElement("button");
    remove.className = "attachment-remove";
    remove.type = "button";
    remove.textContent = "×";
    remove.setAttribute("aria-label", `移除 ${attachment.name || "图片"}`);
    remove.addEventListener("click", () => {
      pendingAttachments.splice(index, 1);
      renderAttachmentPreview();
      messageInput.focus();
    });

    chip.append(image, name, remove);
    attachmentPreview.appendChild(chip);
  }
}

function clearPendingAttachments() {
  pendingAttachments = [];
  imageInput.value = "";
  renderAttachmentPreview();
}

async function startOpeningPrompt(payload, openingPrompt = true) {
  if (!openingPrompt || !sessionId || activeController) {
    return;
  }
  const prompt = String(payload && payload.opening_prompt ? payload.opening_prompt : "").trim();
  if (!prompt) {
    return;
  }
  await sendMessage(prompt, [], false, {
    hiddenUser: true,
    showUser: false,
    maxTokens: 512,
    cachedOpening: true,
  });
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => resolve(reader.result));
    reader.addEventListener("error", () => reject(reader.error || new Error("读取图片失败")));
    reader.readAsDataURL(file);
  });
}

function normalizeMimeAlias(mimeType) {
  const normalized = String(mimeType || "").trim().toLowerCase();
  if (normalized === "image/jpg" || normalized === "image/pjpeg") {
    return "image/jpeg";
  }
  if (normalized === "image/x-png") {
    return "image/png";
  }
  return normalized;
}

function getFileExtension(fileName) {
  const match = String(fileName || "").toLowerCase().match(/\.([a-z0-9]+)$/);
  return match ? match[1] : "";
}

function inferImageMime(file) {
  const declared = normalizeMimeAlias(file && file.type);
  if (declared.startsWith("image/")) {
    return declared;
  }
  const extension = getFileExtension(file && file.name);
  return IMAGE_EXTENSION_MIME[extension] || "";
}

function isLikelyImageFile(file) {
  return Boolean(inferImageMime(file));
}

function rewriteDataUrlMime(dataUrl, mimeType) {
  const text = String(dataUrl || "");
  if (!mimeType || !text.startsWith("data:")) {
    return text;
  }
  return text.replace(/^data:[^;,]*(;base64,)/, `data:${mimeType}$1`);
}

function loadImageElement(src) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.addEventListener("load", () => resolve(image), { once: true });
    image.addEventListener("error", () => reject(new Error("浏览器无法解码该图片格式")), { once: true });
    image.src = src;
  });
}

async function normalizeImageFile(file) {
  const inferredMime = inferImageMime(file);
  const originalDataUrl = rewriteDataUrlMime(await readFileAsDataUrl(file), inferredMime);
  if (inferredMime === "image/png") {
    return {
      dataUrl: originalDataUrl,
      mimeType: "image/png",
      size: file.size,
      converted: false,
    };
  }

  try {
    const image = await loadImageElement(originalDataUrl);
    const canvas = document.createElement("canvas");
    canvas.width = image.naturalWidth || image.width;
    canvas.height = image.naturalHeight || image.height;
    if (!canvas.width || !canvas.height) {
      throw new Error("图片尺寸无效");
    }
    const context = canvas.getContext("2d");
    context.drawImage(image, 0, 0);
    const pngDataUrl = canvas.toDataURL("image/png");
    return {
      dataUrl: pngDataUrl,
      mimeType: "image/png",
      size: Math.ceil((pngDataUrl.length - "data:image/png;base64,".length) * 3 / 4),
      converted: true,
    };
  } catch {
    return {
      dataUrl: originalDataUrl,
      mimeType: inferredMime || (String(originalDataUrl).match(/^data:([^;]+);/) || [])[1] || "image/*",
      size: file.size,
      converted: false,
      fallback: true,
    };
  }
}

async function addImageFiles(files) {
  const slots = MAX_ATTACHMENTS - pendingAttachments.length;
  const selected = Array.from(files).slice(0, Math.max(0, slots));
  const beforeCount = pendingAttachments.length;
  if (!selected.length) {
    if (files.length) {
      setStatus(`最多上传 ${MAX_ATTACHMENTS} 张图片`);
    }
    return;
  }

  for (const file of selected) {
    if (!isLikelyImageFile(file)) {
      setStatus("当前只支持图片");
      continue;
    }
    const normalized = await normalizeImageFile(file);
    pendingAttachments.push({
      name: file.name || "image",
      mime_type: normalized.mimeType,
      data_url: normalized.dataUrl,
      size: normalized.size,
    });
    if (normalized.fallback) {
      setStatus("该图片格式无法在浏览器内转码，已尝试按原格式发送");
    }
  }
  renderAttachmentPreview();
  if (pendingAttachments.length > beforeCount) {
    setStatus(`已选择 ${pendingAttachments.length} 张图片，发送时会一起上传`);
  }
  if (files.length > selected.length) {
    setStatus(`最多上传 ${MAX_ATTACHMENTS} 张图片`);
  }
}

async function createSession(options = {}) {
  const { openingPrompt = true } = options;
  const response = await fetch("/api/sessions", {
    method: "POST",
    headers: deviceIdentityHeaders(),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  const payload = await response.json();
  sessionId = payload.session_id;
  resetPreviousSessionLoadState();
  clearMessages();
  clearPendingAttachments();
  setStatus("就绪");
  await startOpeningPrompt(payload, openingPrompt);
}

function closeCurrentSession() {
  if (!sessionId) {
    return;
  }
  const deviceIdQuery = `?device_id=${encodeURIComponent(ensureDeviceId())}`;
  fetch(`/api/sessions/${sessionId}/close${deviceIdQuery}`, {
    method: "POST",
    headers: deviceIdentityHeaders(),
    keepalive: true,
  }).catch(() => {
    if (navigator.sendBeacon) {
      navigator.sendBeacon(`/api/sessions/${sessionId}/close${deviceIdQuery}`, new Blob([], { type: "application/json" }));
    }
  });
}

async function stopActiveGeneration() {
  if (!activeController) {
    return;
  }
  userStoppedGeneration = true;
  if (activeStopButton) {
    activeStopButton.disabled = true;
  }
  try {
    if (sessionId) {
      await fetch(`/api/sessions/${sessionId}/cancel`, {
        method: "POST",
        headers: deviceIdentityHeaders(),
        keepalive: true,
      });
    }
  } catch {
    // If the cancel request fails, still close the browser stream.
  }
  activeController.abort();
  if (activeAssistantBody) {
    activeAssistantBody.parentElement.classList.add("stopped");
    const raw = getRawMarkdown(activeAssistantBody);
    if (!raw.trim()) {
      setRenderedMarkdown(activeAssistantBody, "[已停止]");
    } else {
      setRenderedMarkdown(activeAssistantBody, `${raw}\n\n[已停止]`);
    }
  }
  setStatus("已停止");
}

async function resetChat() {
  if (isResetting) {
    return;
  }
  isResetting = true;
  setStatus("重置中");

  if (activeController) {
    await stopActiveGeneration();
  }

  try {
    if (!sessionId) {
      await createSession();
      return;
    }

    const response = await fetch(`/api/sessions/${sessionId}/reset`, {
      method: "POST",
      headers: deviceIdentityHeaders(),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const payload = await response.json();
    sessionId = payload.session_id;
    resetPreviousSessionLoadState();
    clearMessages();
    clearPendingAttachments();
    setStatus("就绪");
    await startOpeningPrompt(payload, true);
  } catch (error) {
    setStatus("重置失败");
    createBubble("assistant", `重置失败：${error.message}`);
  } finally {
    isResetting = false;
    setBusy(false);
    messageInput.focus();
  }
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

  return {
    event,
    payload: data.length ? JSON.parse(data.join("\n")) : {},
  };
}

async function consumeSse(response, handlers) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  async function dispatchBlock(block) {
    if (!block.trim()) {
      return false;
    }
    const { event, payload } = parseSseBlock(block);
    if (!handlers[event]) {
      return false;
    }
    return handlers[event](payload) === true;
  }

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() || "";

    for (const block of blocks) {
      if (await dispatchBlock(block)) {
        await reader.cancel();
        return;
      }
    }
  }

  const tail = buffer.trim();
  if (tail) {
    await dispatchBlock(tail);
  }
}

async function sendMessage(text, attachments = [], webSearch = false, options = {}) {
  if (!sessionId) {
    await createSession({ openingPrompt: false });
  }

  const {
    hiddenUser = false,
    showUser = true,
    maxTokens = 8192,
    openingPlaceholder = "",
  } = options;
  if (showUser) {
    createBubble("user", text, attachments);
  }
  const assistantBody = createBubble("assistant", openingPlaceholder);
  let hasReceivedToken = false;
  attachInlineStopButton(assistantBody);
  activeAssistantBody = assistantBody;
  userStoppedGeneration = false;
  activeController = new AbortController();
  setBusy(true);
  clearSearchActivity();
  const largeAttachment = hasLargeAttachment(attachments);
  setStatus(largeAttachment ? "图片过大，狠狠压缩中..." : (options.cachedOpening ? "开场生成中" : (webSearch ? "联网搜索中" : "生成中")));

  try {
    const response = await fetch("/api/chat/stream", {
      method: "POST",
      headers: jsonHeaders(),
      signal: activeController.signal,
      body: JSON.stringify({
        session_id: sessionId,
        message: text,
        attachments,
        hidden_user: hiddenUser,
        cached_opening: Boolean(options.cachedOpening),
        web_search: webSearch,
        web_search_proxy: samplingSettings.web_search_proxy,
        max_tokens: maxTokens,
        ...getSamplingSettings(),
      }),
    });

    if (!response.ok || !response.body) {
      throw new Error(await response.text());
    }

    await consumeSse(response, {
      memory: (payload) => {
        if (payload.status === "checking") {
          setSearchActivity(payload.message || "判断是否需要回忆...");
          setStatus("判断回忆中");
        } else if (payload.status === "skipped") {
          setSearchActivity(payload.message || "无需回忆，直接生成");
          setStatus("生成中");
        } else if (payload.status === "running") {
          setSearchActivity(payload.message || "正在回忆");
          setStatus("回忆中");
        } else if (payload.status === "done") {
          setSearchActivity(payload.message || "回忆完成");
          setStatus("生成中");
        }
      },
      search: (payload) => {
        if (payload.stage === "routing" || payload.status === "query") {
          activeSearchQuery = payload.query || text;
          setSearchActivity(`搜索：${activeSearchQuery}`);
          setStatus("联网搜索中");
        } else if (payload.stage === "searching" && payload.status === "candidates") {
          const first = (payload.results || [])[0];
          const firstTitle = first ? `，例如 ${formatSearchTitle(first.title)}` : "";
          setSearchActivity(`搜到候选网页：${payload.result_count || 0} 条${firstTitle}`);
        } else if (payload.stage === "searching" || payload.status === "searching" || payload.status === "running") {
          activeSearchQuery = payload.query || activeSearchQuery || text;
          setSearchActivity(`搜索：${activeSearchQuery}`);
          setStatus("联网搜索中");
        } else if (payload.status === "candidates") {
          const first = (payload.results || [])[0];
          const firstTitle = first ? `，例如 ${formatSearchTitle(first.title)}` : "";
          setSearchActivity(`搜到候选网页：${payload.result_count || 0} 条${firstTitle}`);
        } else if (payload.stage === "reading" && payload.status === "reading") {
          const title = formatSearchTitle(payload.source_title || payload.title);
          const progress = payload.current_index && payload.max_pages
            ? `${payload.current_index}/${payload.max_pages}：`
            : "";
          setSearchActivity(`浏览：${progress}${title}`);
        } else if (payload.status === "page_done") {
          const title = formatSearchTitle(payload.source_title || payload.title);
          const excerpt = formatSearchExcerpt(payload.excerpt);
          setSearchActivity(`已浏览：${title}${excerpt ? ` · ${excerpt}` : ""}`);
        } else if (payload.status === "page_error") {
          setSearchActivity(`读取失败：${formatSearchTitle(payload.source_title || payload.title)}，跳过`);
        } else if (payload.stage === "verified" || payload.status === "verified") {
          setSearchActivity(`已校验来源：${payload.reliable_count || 0} 条可信资料`);
        } else if (payload.stage === "done" || payload.status === "done") {
          setSearchActivity(`搜索完成：${payload.result_count || 0} 条结果`);
          setStatus(`搜索完成：${payload.result_count || 0} 条结果`);
        } else if (payload.status === "error") {
          setSearchActivity("搜索失败，继续生成");
          setStatus("搜索失败，继续生成");
        }
      },
      token: (payload) => {
        if (!hasReceivedToken && openingPlaceholder) {
          setRenderedMarkdown(assistantBody, "");
        }
        hasReceivedToken = true;
        setRenderedMarkdown(assistantBody, getRawMarkdown(assistantBody) + (payload.content || ""));
        scrollToBottom();
      },
      done: () => {
        setStatus("就绪");
        return true;
      },
      error: (payload) => {
        setRenderedMarkdown(assistantBody, payload.message || "模型服务调用失败");
        assistantBody.parentElement.classList.add("error");
        setStatus("错误");
        return true;
      },
      stopped: () => {
        const raw = getRawMarkdown(assistantBody);
        if (!raw.trim()) {
          setRenderedMarkdown(assistantBody, "[已停止]");
        } else if (!raw.includes("[已停止]")) {
          setRenderedMarkdown(assistantBody, `${raw}\n\n[已停止]`);
        }
        assistantBody.parentElement.classList.add("stopped");
        setStatus("已停止");
        clearSearchActivity();
        return true;
      },
    });
  } catch (error) {
    if (error.name === "AbortError" && userStoppedGeneration) {
      setStatus("已停止");
    } else if (error.name !== "AbortError") {
      setRenderedMarkdown(assistantBody, `请求失败：${error.message}`);
      assistantBody.parentElement.classList.add("error");
      setStatus("错误");
    }
  } finally {
    removeInlineStopButton();
    activeController = null;
    activeAssistantBody = null;
    userStoppedGeneration = false;
    setBusy(false);
    messageInput.focus();
  }
}

function openMemoryAdminDialog() {
  memoryAdminLoginStatus.textContent = "";
  memoryAdminPassword.value = "";
  if (typeof memoryAdminDialog.showModal === "function") {
    memoryAdminDialog.showModal();
  } else {
    memoryAdminDialog.setAttribute("open", "");
  }
  memoryAdminPassword.focus();
}

function closeMemoryAdminDialog() {
  memoryAdminDialog.close();
}

async function loginMemoryAdmin(event) {
  event.preventDefault();
  const password = memoryAdminPassword.value;
  memoryAdminLoginStatus.textContent = "验证中";
  try {
    const response = await fetch("/api/admin/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    if (!response.ok) {
      memoryAdminLoginStatus.textContent = "密码错误";
      memoryAdminPassword.select();
      return;
    }
    window.location.href = "/memory-admin";
  } catch (error) {
    memoryAdminLoginStatus.textContent = `验证失败：${error.message}`;
  }
}

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  let text = messageInput.value.trim();
  const attachments = pendingAttachments.map((attachment) => ({ ...attachment }));
  const useWebSearch = webSearchEnabled;
  if ((!text && !attachments.length) || activeController) {
    return;
  }
  if (!text && attachments.length) {
    text = "请描述这张图片。";
  }
  messageInput.value = "";
  clearPendingAttachments();
  await sendMessage(text, attachments, useWebSearch);
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

resetButton.addEventListener("click", resetChat);
attachImageButton.addEventListener("click", () => imageInput.click());
webSearchButton.addEventListener("click", () => {
  setWebSearchEnabled(!webSearchEnabled);
  setStatus(webSearchEnabled ? "联网搜索已开启" : "联网搜索已关闭");
  messageInput.focus();
});
messagesEl.addEventListener("scroll", handleMessagesScroll, { passive: true });
messagesEl.addEventListener("wheel", (event) => {
  if (event.deltaY < -24 && isAtMessagesTop()) {
    event.preventDefault();
    armOrLoadPreviousSession();
  }
}, { passive: false });
messagesEl.addEventListener("touchstart", (event) => {
  if (event.touches.length !== 1) {
    return;
  }
  touchStartY = event.touches[0].clientY;
  touchPullDistance = 0;
}, { passive: true });
messagesEl.addEventListener("touchmove", (event) => {
  if (event.touches.length !== 1 || !isAtMessagesTop()) {
    return;
  }
  touchPullDistance = event.touches[0].clientY - touchStartY;
  if (touchPullDistance > 0) {
    event.preventDefault();
  }
  if (touchPullDistance > PREVIOUS_SESSION_PULL_THRESHOLD) {
    armOrLoadPreviousSession();
    touchStartY = event.touches[0].clientY;
    touchPullDistance = 0;
  }
}, { passive: false });
imageInput.addEventListener("change", async () => {
  try {
    await addImageFiles(imageInput.files || []);
  } catch (error) {
    setStatus(`图片读取失败：${error.message}`);
  } finally {
    imageInput.value = "";
  }
});
memoryAdminButton.addEventListener("click", openMemoryAdminDialog);
memoryAdminLoginForm.addEventListener("submit", loginMemoryAdmin);
memoryAdminCancelButton.addEventListener("click", closeMemoryAdminDialog);
window.addEventListener("pagehide", closeCurrentSession);
bunnyLogoButton.addEventListener("click", handleBunnyLogoClick);
temperatureRange.addEventListener("input", updateSamplingSummary);
topPRange.addEventListener("input", updateSamplingSummary);
confirmSamplingButton.addEventListener("click", () => {
  saveSamplingSettings({
    temperature: temperatureRange.value,
    top_p: topPRange.value,
    web_search_proxy: webSearchProxyInput.value,
  });
  hideAdvancedOptions();
  setStatus(`采样已更新：${samplingSummary.textContent}`);
});
syncSamplingControlsFromSettings();

createSession().catch((error) => {
  setStatus("连接失败");
  createBubble("assistant", `连接失败：${error.message}`);
  setBusy(false);
});
