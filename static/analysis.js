const statusText = document.getElementById("statusText");
const analysisModelDisplayName = document.getElementById("analysisModelDisplayName");
const messagesEl = document.getElementById("messages");
const tracePanel = document.getElementById("tracePanel");
const backgroundPanel = document.getElementById("backgroundPanel");
const backgroundMoreButton = document.getElementById("backgroundMoreButton");
const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("messageInput");
const sendButton = document.getElementById("sendButton");
const loadPreviousButton = document.getElementById("loadPreviousButton");
const resetButton = document.getElementById("resetButton");
const refreshTraceButton = document.getElementById("refreshTraceButton");
const webSearchInput = document.getElementById("webSearchInput");
const analysisAttachImageButton = document.getElementById("analysisAttachImageButton");
const analysisWebSearchButton = document.getElementById("analysisWebSearchButton");
const analysisDrawButton = document.getElementById("analysisDrawButton");
const analysisImageInput = document.getElementById("analysisImageInput");
const analysisAttachmentPreview = document.getElementById("analysisAttachmentPreview");

window.__qwenAnalysisStarted = true;

window.addEventListener("error", (event) => {
  if (statusText) {
    statusText.textContent = `前端错误：${event.message || "脚本初始化失败"}`;
  }
});

window.addEventListener("unhandledrejection", (event) => {
  if (statusText) {
    const reason = event.reason && event.reason.message ? event.reason.message : String(event.reason || "异步任务失败");
    statusText.textContent = `前端错误：${reason}`;
  }
});

let sessionId = null;
let activeController = null;
let pendingAttachments = [];
let backgroundActivityLimit = 20;
let userStoppedGeneration = false;
let isMessageComposing = false;
let isLoadingPreviousSession = false;
let hasMorePreviousSessions = true;
let analysisDrawEnabled = false;
let panelRefreshTimer = 0;
let panelRefreshPending = false;
let backgroundRefreshPending = false;
let panelRefreshRunning = false;
let panelRefreshWatchTimer = 0;
let panelRefreshWatchUntil = 0;

function updateAnalysisComposerHeight() {
  if (!chatForm || !chatForm.parentElement) {
    return;
  }
  const height = Math.ceil(chatForm.getBoundingClientRect().height);
  chatForm.parentElement.style.setProperty("--analysis-composer-height", `${height}px`);
}

if (window.ResizeObserver && chatForm) {
  const composerResizeObserver = new ResizeObserver(updateAnalysisComposerHeight);
  composerResizeObserver.observe(chatForm);
} else {
  window.addEventListener("resize", updateAnalysisComposerHeight);
}
updateAnalysisComposerHeight();
let previousSessionArmedAt = 0;
let previousSessionHideTimer = 0;
const openTraceKeys = new Set();
const closedTraceKeys = new Set();
const openBackgroundKeys = new Set();
const closedBackgroundKeys = new Set();
const DEVICE_STORAGE_KEY = "qwen_device_id";
const CHAT_SAMPLING_STORAGE_KEY = "qwen_sampling_settings";
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

function setAnalysisModelDisplayName(text) {
  if (analysisModelDisplayName) {
    analysisModelDisplayName.textContent = text || "未知";
  }
}

async function fetchWithTimeout(url, options = {}, timeoutMs = 15000, timeoutMessage = "请求超时") {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } catch (error) {
    if (error && error.name === "AbortError") {
      throw new Error(timeoutMessage);
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

async function loadAnalysisModelDisplayName() {
  if (!analysisModelDisplayName) {
    return;
  }
  try {
    const response = await fetchWithTimeout("/api/health", { headers: deviceIdentityHeaders() }, 8000, "模型状态读取超时");
    if (!response.ok) {
      throw new Error("模型状态读取失败");
    }
    const payload = await response.json();
    const modelName = String(payload.model_name || "").trim();
    setAnalysisModelDisplayName(modelName || "未知");
  } catch (_error) {
    setAnalysisModelDisplayName("读取失败");
  }
}

async function parseRateLimitPayload(response) {
  try {
    const payload = await response.json();
    const detail = payload && payload.detail ? payload.detail : payload;
    if (detail && detail.code === "rate_limited") {
      return detail;
    }
  } catch (_error) {
    return null;
  }
  return null;
}

function removeEmptyAssistantBubble(assistantBody) {
  const bubble = assistantBody && assistantBody.closest ? assistantBody.closest(".message") : null;
  if (bubble) {
    bubble.remove();
  }
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

function formatWorkerTriggerTime(value) {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  const hh = String(date.getHours()).padStart(2, "0");
  const mm = String(date.getMinutes()).padStart(2, "0");
  const ss = String(date.getSeconds()).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
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
  if (analysisDrawButton) {
    analysisDrawButton.disabled = busy;
  }
  syncPreviousAnalysisSessionButton();
}

function setAnalysisWebSearchEnabled(enabled) {
  webSearchInput.checked = Boolean(enabled);
  analysisWebSearchButton.classList.toggle("is-active", webSearchInput.checked);
  analysisWebSearchButton.setAttribute("aria-pressed", String(webSearchInput.checked));
  analysisWebSearchButton.title = webSearchInput.checked ? "本轮会联网搜索" : "启用联网搜索";
  if (webSearchInput.checked) {
    setAnalysisDrawEnabled(false);
  }
}

function setAnalysisDrawEnabled(enabled) {
  analysisDrawEnabled = Boolean(enabled);
  if (!analysisDrawButton) {
    return;
  }
  analysisDrawButton.classList.toggle("is-active", analysisDrawEnabled);
  analysisDrawButton.setAttribute("aria-pressed", String(analysisDrawEnabled));
  analysisDrawButton.title = analysisDrawEnabled ? "本轮发送会画图" : "启用画图";
  if (analysisDrawEnabled && webSearchInput.checked) {
    webSearchInput.checked = false;
    analysisWebSearchButton.classList.remove("is-active");
    analysisWebSearchButton.setAttribute("aria-pressed", "false");
    analysisWebSearchButton.title = "启用联网搜索";
  }
}

function clearAnalysisDrawModeSelection() {
  setAnalysisDrawEnabled(false);
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

function protectInlineSegments(text) {
  const segments = [];
  function store(html) {
    const marker = `\u0000MDSEG${segments.length}\u0000`;
    segments.push(html);
    return marker;
  }
  let source = String(text || "");
  source = source.replace(/`([^`]+)`/g, (_, code) => store(`<code>${escapeHtml(code)}</code>`));
  source = source.replace(/\\\((.+?)\\\)/g, (_, formula) => store(`<span class="math math-inline">\\(${escapeHtml(formula.trim())}\\)</span>`));
  source = source.replace(/\$([^$\n]+?)\$/g, (_, formula) => store(`<span class="math math-inline">\\(${escapeHtml(formula.trim())}\\)</span>`));
  return { source, segments };
}

function restoreInlineSegments(html, segments) {
  return html.replace(/\u0000MDSEG(\d+)\u0000/g, (_, index) => segments[Number(index)] || "");
}

function renderInlineMarkdown(text) {
  const { source, segments } = protectInlineSegments(text);
  let html = escapeHtml(source);

  html = html
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (_, label, url) => {
      const href = url.replace(/&amp;/g, "&");
      return `<a href="${href}" target="_blank" rel="noopener noreferrer">${label}</a>`;
    })
    .replace(/\*\*\s*([^*]+?)\s*\*\*/g, "<strong>$1</strong>")
    .replace(/__\s*([^_]+?)\s*__/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
    .replace(/(^|[^_])_([^_\n]+)_/g, "$1<em>$2</em>");

  return restoreInlineSegments(html, segments);
}

function normalizeMarkdownTables(markdown) {
  return String(markdown || "")
    .replace(/\r\n/g, "\n")
    .split("\n")
    .flatMap((line) => {
      const looksLikeSquashedTable = line.includes("| |") && /\|\s*:?-{3,}:?\s*\|/.test(line);
      return looksLikeSquashedTable ? line.replace(/\s+\|\s+\|/g, " |\n|").split("\n") : [line];
    })
    .join("\n");
}

function splitTableCells(line) {
  const trimmed = String(line || "").trim();
  const withoutEdges = trimmed.replace(/^\|/, "").replace(/\|$/, "");
  return withoutEdges.split("|").map((cell) => cell.trim());
}

function isTableLine(line) {
  const trimmed = String(line || "").trim();
  return trimmed.startsWith("|") && trimmed.endsWith("|") && splitTableCells(trimmed).length >= 2;
}

function isTableSeparatorLine(line) {
  if (!isTableLine(line)) {
    return false;
  }
  const cells = splitTableCells(line);
  return cells.length >= 2 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function tableAlignments(separatorLine) {
  return splitTableCells(separatorLine).map((cell) => {
    if (cell.startsWith(":") && cell.endsWith(":")) return "center";
    if (cell.endsWith(":")) return "right";
    if (cell.startsWith(":")) return "left";
    return "";
  });
}

function renderMarkdownTable(headerLine, separatorLine, bodyLines) {
  const headers = splitTableCells(headerLine);
  const aligns = tableAlignments(separatorLine);
  const rows = bodyLines.map(splitTableCells);
  const alignAttr = (index) => aligns[index] ? ` style="text-align: ${aligns[index]}"` : "";
  const headHtml = headers
    .map((cell, index) => `<th${alignAttr(index)}>${renderInlineMarkdown(cell)}</th>`)
    .join("");
  const bodyHtml = rows
    .map((row) => `<tr>${headers.map((_, index) => `<td${alignAttr(index)}>${renderInlineMarkdown(row[index] || "")}</td>`).join("")}</tr>`)
    .join("");
  return `<div class="markdown-table-wrap"><table><thead><tr>${headHtml}</tr></thead><tbody>${bodyHtml}</tbody></table></div>`;
}

function renderBlockMath(lines) {
  const formula = lines.join("\n").trim();
  return `<div class="math math-block">\\[${escapeHtml(formula)}\\]</div>`;
}

function typesetMarkdownMath(element) {
  if (window.MathJax && typeof window.MathJax.typesetPromise === "function") {
    window.MathJax.typesetPromise([element]).catch(() => {});
  }
}

function renderMarkdown(markdown) {
  const lines = normalizeMarkdownTables(markdown).split("\n");
  const html = [];
  let paragraph = [];
  let listStack = [];
  let inCodeBlock = false;
  let codeLines = [];
  let inBlockMath = false;
  let blockMathLines = [];

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

  for (let i = 0; i < lines.length; i += 1) {
    const rawLine = lines[i];
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

    const trimmed = line.trim();
    if (inBlockMath) {
      if (trimmed === "$$") {
        html.push(renderBlockMath(blockMathLines));
        blockMathLines = [];
        inBlockMath = false;
      } else {
        blockMathLines.push(rawLine);
      }
      continue;
    }

    if (trimmed === "$$") {
      closeParagraph();
      closeAllLists();
      inBlockMath = true;
      blockMathLines = [];
      continue;
    }

    const oneLineMath = trimmed.match(/^\$\$(.+)\$\$$/);
    if (oneLineMath) {
      closeParagraph();
      closeAllLists();
      html.push(renderBlockMath([oneLineMath[1].trim()]));
      continue;
    }

    if (!trimmed) {
      closeParagraph();
      // blank lines inside lists should not reset ordered numbering
      continue;
    }

    if (/^(-{3,}|_{3,}|\*{3,})$/.test(trimmed)) {
      closeParagraph();
      closeAllLists();
      html.push(`<hr />`);
      continue;
    }

    if (isTableLine(line) && i + 1 < lines.length && isTableSeparatorLine(lines[i + 1])) {
      closeParagraph();
      closeAllLists();
      const headerLine = line;
      const separatorLine = lines[i + 1];
      const bodyLines = [];
      i += 2;
      while (i < lines.length && isTableLine(lines[i]) && !isTableSeparatorLine(lines[i])) {
        bodyLines.push(lines[i]);
        i += 1;
      }
      i -= 1;
      html.push(renderMarkdownTable(headerLine, separatorLine, bodyLines));
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
  if (inBlockMath) {
    html.push(renderBlockMath(blockMathLines));
  }
  closeParagraph();
  closeAllLists();
  return html.join("");
}

function stripModelMessageTimePrefixes(text) {
  let cleaned = String(text || "");
  for (let index = 0; index < 4; index += 1) {
    const next = cleaned.replace(
      /^\s*\[\s*message[\s_-]*time\s*:\s*[^\]\n]*(?:\]|\n)\s*/i,
      "",
    );
    if (next === cleaned) {
      break;
    }
    cleaned = next;
  }
  return cleaned;
}

function setRenderedMarkdown(element, markdown) {
  const cleaned = stripModelMessageTimePrefixes(markdown || "");
  element.dataset.rawMarkdown = cleaned;
  element.innerHTML = renderMarkdown(cleaned);
  typesetMarkdownMath(element);
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
  return readChatSamplingSettings().web_search_proxy;
}

function readChatSamplingSettings() {
  try {
    const raw = localStorage.getItem(CHAT_SAMPLING_STORAGE_KEY);
    if (!raw) {
      return { temperature: 0.6, top_p: 0.95, web_search_proxy: "" };
    }
    const payload = JSON.parse(raw);
    return {
      temperature: clampNumber(payload.temperature, 0, 2, 0.6),
      top_p: clampNumber(payload.top_p, 0, 1, 0.95),
      web_search_proxy: typeof payload.web_search_proxy === "string" ? payload.web_search_proxy.trim() : "",
    };
  } catch {
    return { temperature: 0.6, top_p: 0.95, web_search_proxy: "" };
  }
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

function renderAnalysisGeneratedImageBatch(images, optimizedPrompt = "") {
  const wrapper = document.createElement("div");
  wrapper.className = "analysis-generated-image-batch";
  const grid = document.createElement("div");
  grid.className = "analysis-generated-image-grid";
  const items = Array.isArray(images) ? images : [];
  for (const [index, item] of items.entries()) {
    const url = item && item.public_url ? String(item.public_url) : "";
    if (!url) {
      continue;
    }
    const cell = document.createElement("figure");
    cell.className = "analysis-generated-image-item";
    const image = document.createElement("img");
    image.src = url;
    image.alt = item.short_caption || `生成图片 ${index + 1}`;
    const download = document.createElement("a");
    download.className = "analysis-generated-image-download";
    download.href = url;
    download.download = `wangcai-analysis-draw-${index + 1}`;
    download.textContent = "下载";
    cell.append(image, download);
    grid.appendChild(cell);
  }
  wrapper.appendChild(grid);
  if (optimizedPrompt) {
    const details = document.createElement("details");
    details.className = "analysis-generated-image-prompt";
    const summary = document.createElement("summary");
    summary.textContent = "优化后的 prompt";
    const pre = document.createElement("pre");
    pre.textContent = optimizedPrompt;
    details.append(summary, pre);
    wrapper.appendChild(details);
  }
  return wrapper;
}

function analysisMessageAttachments(message) {
  return Array.isArray(message && message.attachments)
    ? message.attachments.filter((item) => item && typeof item === "object")
    : [];
}

function analysisMessageDrawMetadata(message) {
  return message && message.draw && typeof message.draw === "object" ? message.draw : {};
}

function restoreHistoricalAnalysisAssistantMedia(body, message) {
  const draw = analysisMessageDrawMetadata(message);
  const images = Array.isArray(draw.images) ? draw.images : [];
  if (!images.length) {
    return;
  }
  body.replaceChildren();
  body.appendChild(renderAnalysisGeneratedImageBatch(images, draw.optimized_prompt || ""));
  body.dataset.rawMarkdown = message.content || `已生成 ${images.length} 张图片。`;
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
    const role = message.role === "assistant" ? "assistant" : "user";
    const body = appendMessage(role, message.content || "", analysisMessageAttachments(message), {
      prepend: true,
      scroll: false,
      createdAt: message.created_at,
    });
    if (role === "assistant") {
      restoreHistoricalAnalysisAssistantMedia(body, message);
    }
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
    scheduleAnalysisPanelsRefresh({ delay: 0 });
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
  setStatus("创建会话中");
  const response = await fetchWithTimeout("/api/sessions", {
    method: "POST",
    headers: deviceIdentityHeaders(),
  }, 15000, "创建会话超时");
  if (!response.ok) {
    throw new Error("session create failed");
  }
  const data = await response.json();
  sessionId = data.session_id;
  resetPreviousAnalysisSessionLoadState();
  ensureAnalysisHistoryLoadIndicator();
  syncPreviousAnalysisSessionButton();
  setStatus(`session ${sessionId.slice(0, 8)}`);
  scheduleAnalysisPanelsRefresh({ delay: 0 });
  startOpeningPrompt(data).catch((error) => {
    if (!userStoppedGeneration) {
      setStatus(`开场失败: ${error.message || "生成中断"}`);
    }
  });
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
  stopAnalysisPanelsRefreshWatch();
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

function renderTraceScalar(value) {
  const normalized = value === null || value === undefined ? String(value) : String(value);
  const node = document.createElement(normalized.includes("\n") ? "pre" : "span");
  node.className = "trace-light-scalar";
  node.textContent = normalized;
  return node;
}

function renderTraceLightValue(value) {
  if (Array.isArray(value)) {
    return renderTraceScalar(JSON.stringify(value, null, 2));
  }
  if (value && typeof value === "object") {
    return renderTraceScalar(JSON.stringify(value, null, 2));
  }
  return renderTraceScalar(value);
}

function renderTraceLightObject(payload) {
  const container = document.createElement("div");
  container.className = "trace-light-payload";
  const entries = Object.entries(payload || {});
  if (!entries.length) {
    container.appendChild(renderTraceScalar("{}"));
    return container;
  }
  entries.forEach(([key, value]) => {
    const row = document.createElement("div");
    row.className = "trace-light-row";
    const label = document.createElement("strong");
    label.className = "trace-light-key";
    label.textContent = key;
    row.append(label, renderTraceLightValue(value));
    container.appendChild(row);
  });
  return container;
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

function compactTraceText(value, maxLength = 36) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text) {
    return "";
  }
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}…` : text;
}

function readableTraceModel(model) {
  const raw = String(model || "").trim();
  if (!raw) {
    return "";
  }
  const lower = raw.toLowerCase();
  if (lower.includes("deepseek")) {
    return "DeepSeek";
  }
  if (lower.includes("qwen3.6") || lower.includes("qwen3-") || lower.includes("qwen")) {
    return "Qwen3.6";
  }
  if (lower.includes("gpt-4.1")) {
    return "GPT-4.1";
  }
  if (lower.includes("gpt-4o")) {
    return "GPT-4o";
  }
  if (lower.includes("claude") || lower.includes("opus") || lower.includes("sonnet")) {
    return "Claude";
  }
  return compactTraceText(raw, 22);
}

function traceAgentName(name, payload) {
  const model = readableTraceModel(payload && payload.model);
  return model ? `${name}（${model}）` : name;
}

function traceMessageCount(payload) {
  return Array.isArray(payload && payload.messages) ? payload.messages.length : 0;
}

function traceResultCount(payload, key) {
  const value = payload && payload[key];
  return Array.isArray(value) ? value.length : Number(payload && payload[key]) || 0;
}

function validationCandidateLabel(payload) {
  const decision = payload && payload.decision ? payload.decision : {};
  const corrected = decision && decision.corrected_item ? decision.corrected_item : {};
  if (corrected.label) {
    return String(corrected.label);
  }
  const messages = Array.isArray(payload && payload.messages) ? payload.messages : [];
  const userMessage = messages.find((message) => message && message.role === "user");
  const content = String(userMessage && userMessage.content ? userMessage.content : "");
  const match = content.match(/\blabel:\s*([a-zA-Z_]+)/);
  return match ? match[1] : "";
}

function validationCandidateMemoryText(payload) {
  const messages = Array.isArray(payload && payload.messages) ? payload.messages : [];
  const userMessage = messages.find((message) => message && message.role === "user");
  const content = String(userMessage && userMessage.content ? userMessage.content : "");
  const match = content.match(/\nmemory:\s*([\s\S]*?)\n\n\[最近对话片段\]/);
  return match ? match[1].trim() : "";
}

function correctedMemoryPreviewFromPayload(payload, maxLength = 42) {
  if (payload && payload.corrected_preview) {
    return compactTraceText(payload.corrected_preview, maxLength);
  }
  const decision = payload && payload.decision ? payload.decision : {};
  const correctedItem = (payload && payload.corrected_item) || decision.corrected_item || {};
  if (correctedItem && typeof correctedItem.memory === "string") {
    return compactTraceText(correctedItem.memory, maxLength);
  }
  return "";
}

function normalizedMemoryTraceKey(text) {
  return String(text || "").replace(/\s+/g, "").trim().toLowerCase().slice(0, 180);
}

function readableMemoryLabel(label) {
  const labels = {
    event: "event",
    diary: "diary",
    risk: "risk",
    preference: "preference",
    identity: "identity",
    rule: "rule",
    persona: "persona",
    fact: "fact",
    other: "other",
  };
  return labels[label] || label || "记忆";
}

function readableSkipReason(reason) {
  const reasons = {
    recent_duplicate_memory: "近期重复",
    known_memory_duplicate: "历史召回已覆盖",
    similar_memory_exists: "相似记忆已存在",
    event_live_update_already_handled: "event 已实时维护",
    underspecified_memory: "信息过短",
    assistant_identity_not_user_identity: "助手身份误写",
    not_user_centered: "不是用户事实",
  };
  const raw = String(reason || "").trim();
  if (raw.startsWith("semantic_validation_failed")) {
    return "核验否决";
  }
  return reasons[raw] || raw || "跳过";
}

function memoryDecisionItems(decision) {
  if (!decision || typeof decision !== "object") {
    return [];
  }
  if (Array.isArray(decision.items)) {
    return decision.items;
  }
  return decision.memory ? [decision] : [];
}

function traceTitleParts(item) {
  const payload = item && item.payload && typeof item.payload === "object" ? item.payload : {};
  const step = String(item && item.step_name ? item.step_name : "");
  const eventType = String(item && item.event_type ? item.event_type : "");
  const duration = step === "draw_prompt_optimize" ? "" : formatDuration(item && item.duration_ms);
  let title = "";

  if (step === "analysis_chat_start" || step === "cached_opening_start") {
    const messageChars = String(payload.message || "").length;
    const attachments = Array.isArray(payload.attachments) ? payload.attachments.length : 0;
    const mode = step === "cached_opening_start" ? "开场预缓存" : "收到用户输入";
    const extras = [
      messageChars ? `${messageChars} 字` : "",
      attachments ? `${attachments} 张图` : "",
      payload.web_search ? "联网" : "",
    ].filter(Boolean).join("，");
    title = extras ? `${mode}：${extras}` : mode;
  } else if (step === "main_chat_prompt") {
    const count = traceMessageCount(payload);
    title = `${traceAgentName("聊天 Prompt", payload)}：完整输入${count ? `，${count} 条消息` : ""}`;
  } else if (step === "main_chat_stream") {
    const chars = Number(payload.answer_chars || payload.chars || 0);
    const status = payload.status === "cancelled" ? "已中断" : "回复完成";
    title = `${traceAgentName("聊天 Agent", payload)}：${status}${chars ? `，${chars} 字` : ""}`;
  } else if (step === "draw_memory_gate") {
    const decision = payload.decision || {};
    title = `${traceAgentName("画图记忆路由", payload)}：${decision.needs_memory ? "读取参考记忆" : "无需参考记忆"}`;
  } else if (step === "draw_memory_query_embedding") {
    const candidates = traceResultCount(payload, "candidate_memories");
    const query = compactTraceText(payload.input_preview || (payload.result && payload.result.query), 28);
    title = `画图相似度检索（${readableTraceModel(payload.model) || "embedding"}）：找到 ${candidates} 条候选记忆${query ? `，query「${query}」` : ""}`;
  } else if (step === "draw_memory_text_fallback") {
    const results = traceResultCount(payload, "results");
    title = `画图记忆检索降级：文本匹配 ${results} 条结果`;
  } else if (step === "draw_prompt_translate") {
    const chars = Number(payload.translated_chars || 0);
    title = `${traceAgentName("画图英文直译", payload)}：完整输入${chars ? `，输出 ${chars} 字` : ""}`;
  } else if (step === "draw_prompt_classify") {
    const decision = payload.decision || {};
    const modeNames = {
      natural: "自然语言优化",
      professional: "专业 prompt 直译",
      revision: "基于上一张修改",
    };
    title = `${traceAgentName("画图分类", payload)}：${modeNames[decision.mode] || decision.mode || "未分类"}`;
  } else if (step === "draw_prompt_agent_model") {
    const decision = payload.decision || {};
    const promptMode = payload.prompt_mode || {};
    const modeNames = {
      natural: "自然语言",
      professional: "专业 prompt",
      revision: "续改 prompt",
    };
    const promptChars = String(decision.optimized_prompt || "").length;
    title = `${traceAgentName("画图优化 Agent", payload)}：${modeNames[promptMode.mode] || "生成 prompt"}${promptChars ? `，输出 ${promptChars} 字` : ""}`;
  } else if (step === "draw_prompt_optimize") {
    const summary = payload.decision_summary || {};
    const imageCount = Number(summary.image_count || payload.decision && payload.decision.image_count || 0);
    const selected = Number(payload.memory_debug && payload.memory_debug.selected_count || 0);
    const memoryText = payload.memory_debug && payload.memory_debug.memory_gate === "run" ? `，参考 ${selected} 条记忆` : "";
    title = `画图 Prompt 流程汇总：生成 ${imageCount || 4} 张${memoryText}`;
  } else if (step === "draw_image_generation") {
    const imageCount = Number(payload.image_count || (payload.batch && Array.isArray(payload.batch.images) ? payload.batch.images.length : 0));
    title = eventType === "draw_error"
      ? "图片生成：失败"
      : `图片生成：完成${imageCount ? `，${imageCount} 张` : ""}`;
  } else if (step === "memory_recall_gate") {
    const decision = payload.decision || {};
    const needsMemory = Boolean(decision.needs_memory);
    const needsSelfProfile = Boolean(decision.needs_self_profile);
    let routeSummary = "无需长期记忆";
    if (needsMemory && needsSelfProfile) {
      routeSummary = "读取长期记忆 + 系统资料";
    } else if (needsMemory) {
      routeSummary = "读取长期记忆";
    } else if (needsSelfProfile) {
      routeSummary = "读取系统资料";
    }
    title = `${traceAgentName("记忆路由", payload)}：${routeSummary}`;
  } else if (step === "memory_query_embedding") {
    const candidates = traceResultCount(payload, "candidate_memories");
    const query = compactTraceText(payload.input_preview || (payload.result && payload.result.query), 28);
    title = `相似度检索（${readableTraceModel(payload.model) || "embedding"}）：找到 ${candidates} 条候选记忆${query ? `，query「${query}」` : ""}`;
  } else if (step === "memory_candidate_judge") {
    const candidateCount = Number(payload.candidate_count || 0);
    const selectedCount = Number(payload.selected_count || (payload.decision && Array.isArray(payload.decision.selected_ids) ? payload.decision.selected_ids.length : 0));
    title = `${traceAgentName("记忆筛选", payload)}：${candidateCount} 条候选 → ${selectedCount} 条入选`;
  } else if (step === "memory_text_fallback") {
    const results = traceResultCount(payload, "results");
    title = `记忆检索降级：文本匹配 ${results} 条结果`;
  } else if (step === "memory_agent_queued") {
    title = `记忆整理队列：创建后台任务 #${payload.job_id || "?"}`;
  } else if (step === "memory_agent_prompt") {
    const count = traceMessageCount(payload);
    title = `${traceAgentName("记忆整理 Prompt", payload)}：完整输入${count ? `，${count} 条消息` : ""}`;
  } else if (step === "memory_agent_model") {
    const decision = payload.decision || {};
    const items = memoryDecisionItems(decision);
    if (!decision.important || !items.length) {
      title = `${traceAgentName("记忆整理 Agent", { model: payload.model })}：判定无需写入`;
    } else {
      const labels = [...new Set(items.map((entry) => readableMemoryLabel(entry.label)))].join("、");
      title = `${traceAgentName("记忆整理 Agent", { model: payload.model })}：提取 ${items.length} 条${labels ? ` ${labels}` : ""} 候选`;
    }
  } else if (step === "memory_candidate_validation") {
    const decision = payload.decision || {};
    const label = readableMemoryLabel(validationCandidateLabel(payload));
    if (eventType === "model_call_error") {
      title = `${traceAgentName("记忆核验", payload)}：调用失败`;
    } else if (decision.valid) {
      title = `${traceAgentName("记忆核验", payload)}：通过 ${label} 候选`;
    } else if (decision.corrected_item) {
      const correctedPreview = correctedMemoryPreviewFromPayload(payload);
      title = `${traceAgentName("记忆核验", payload)}：否决 ${label} 候选，建议修正版${correctedPreview ? `「${correctedPreview}」` : ""}`;
    } else {
      title = `${traceAgentName("记忆核验", payload)}：否决 ${label} 候选`;
    }
  } else if (step === "memory_candidate_fast_validation") {
    title = `记忆核验：本地快速通过 ${readableMemoryLabel(payload.label)} 候选`;
  } else if (step === "memory_agent_item_corrected") {
    title = `记忆修正：${readableMemoryLabel(payload.label)} 候选改为可写入版本`;
  } else if (step === "memory_agent_correction_rejected") {
    const reasonNames = {
      same_as_original: "修正版与原文相同",
      not_conservative: "修正版改动过大",
      lacks_user_support: "修正版缺少用户原文支撑",
      not_adopted: "修正版未采用",
    };
    const correctedPreview = correctedMemoryPreviewFromPayload(payload);
    title = `记忆修正未采用：${reasonNames[payload.reason] || readableSkipReason(payload.reason)}${correctedPreview ? `，修正版「${correctedPreview}」` : ""}，候选已跳过`;
  } else if (step === "memory_agent_item_skipped") {
    const label = readableMemoryLabel(payload.label);
    const matched = payload.matched_memory_id ? `，匹配 #${payload.matched_memory_id}` : "";
    title = `记忆写入跳过：${readableSkipReason(payload.reason)}${label ? ` ${label}` : ""}${matched}`;
  } else if (step === "memory_write_embedding") {
    const dim = payload.dim ? `${payload.dim} 维` : "";
    title = `记忆写入 embedding：${readableMemoryLabel(payload.label)}${dim ? `，${dim}` : ""}`;
  } else if (step === "event_memory_updater_prompt") {
    title = `事件维护 Prompt：检查 ${Number(payload.candidate_count || 0)} 个候选日程`;
  } else if (step === "event_memory_updater_model") {
    const decision = payload.decision || {};
    const action = decision.action || "noop";
    const actionText = action === "noop" ? "无需更新" : `${action} #${decision.supersedes_id || "?"}`;
    title = `${traceAgentName("事件维护 Agent", payload)}：${actionText}`;
  } else if (step === "search_planner") {
    const queries = payload.result && Array.isArray(payload.result.queries) ? payload.result.queries.length : 0;
    title = `${traceAgentName("搜索规划", payload)}：生成 ${queries || 1} 条查询`;
  } else if (step === "search_candidates") {
    title = `联网搜索：找到 ${Number(payload.count || 0)} 条候选结果`;
  } else if (step.startsWith("read_page_")) {
    const sourceTitle = compactTraceText(payload.source && payload.source.title, 34);
    const indexText = payload.index && payload.max_pages ? `第 ${payload.index}/${payload.max_pages} 页` : "读取网页";
    title = eventType === "web_page_error"
      ? `网页读取失败：${indexText}${sourceTitle ? `「${sourceTitle}」` : ""}`
      : `网页读取：${indexText}${sourceTitle ? `「${sourceTitle}」` : ""}`;
  } else if (step === "search_context") {
    const sources = traceResultCount(payload, "sources");
    title = `搜索上下文：汇总 ${sources} 个来源`;
  } else if (eventType === "guardrail") {
    title = `安全/时间边界：${step || "已触发"}`;
  } else {
    const label = TRACE_EVENT_LABELS[eventType] || eventType || "trace";
    title = `${step || label}：${label}`;
  }

  return [title, duration].filter(Boolean);
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

function traceDisplayTitle(item) {
  return traceTitleParts(item).join(" · ");
}

function traceIsUserInputTitle(item) {
  return traceDisplayTitle(item).startsWith("收到用户输入");
}

function correctionValidationKey(item, loose = false) {
  const payload = item && item.payload ? item.payload : {};
  const decision = payload.decision || {};
  if (item.step_name !== "memory_candidate_validation" || !decision.corrected_item) {
    return "";
  }
  const traceId = item.trace_id || item.session_id || "default";
  const label = readableMemoryLabel(validationCandidateLabel(payload));
  const memory = normalizedMemoryTraceKey(validationCandidateMemoryText(payload));
  if (!loose && !memory) {
    return "";
  }
  return loose || !memory ? `${traceId}|${label}` : `${traceId}|${label}|${memory}`;
}

function semanticValidationSkipKey(item, loose = false) {
  const payload = item && item.payload ? item.payload : {};
  const reason = String(payload.reason || "");
  if (item.step_name !== "memory_agent_item_skipped" || !reason.startsWith("semantic_validation_failed:")) {
    return "";
  }
  const traceId = item.trace_id || item.session_id || "default";
  const label = readableMemoryLabel(payload.label);
  const memory = normalizedMemoryTraceKey(payload.memory_preview || "");
  if (!loose && !memory) {
    return "";
  }
  return loose || !memory ? `${traceId}|${label}` : `${traceId}|${label}|${memory}`;
}

function filterDuplicateTraceItems(items) {
  const correctionValidationKeys = new Set();
  const looseCorrectionValidationKeys = new Set();
  (items || []).forEach((item) => {
    const key = correctionValidationKey(item);
    if (key) {
      correctionValidationKeys.add(key);
      looseCorrectionValidationKeys.add(correctionValidationKey(item, true));
    }
  });
  const seenUserInputByTrace = new Set();
  return (items || []).filter((item) => {
    const skipKey = semanticValidationSkipKey(item);
    const looseSkipKey = semanticValidationSkipKey(item, true);
    if (
      (skipKey && correctionValidationKeys.has(skipKey))
      || (!skipKey && looseSkipKey && looseCorrectionValidationKeys.has(looseSkipKey))
    ) {
      return false;
    }
    if (!traceIsUserInputTitle(item)) {
      return true;
    }
    const key = item.trace_id || item.session_id || "default";
    if (seenUserInputByTrace.has(key)) {
      return false;
    }
    seenUserInputByTrace.add(key);
    return true;
  });
}

function renderTraceItem(item) {
  const key = traceItemKey(item);
  const card = document.createElement("details");
  card.className = `trace-card trace-${item.event_type}`;
  if (traceIsUserInputTitle(item)) {
    card.classList.add("trace-user-input-card");
  }
  card.dataset.traceKey = key;
  card.open = openTraceKeys.has(key);
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
  summary.textContent = traceDisplayTitle(item);
  summary.title = [
    item.step_name,
    TRACE_EVENT_LABELS[item.event_type] || item.event_type,
    item.visitor_ip,
  ].filter(Boolean).join(" · ");
  const meta = document.createElement("div");
  meta.className = "trace-meta";
  meta.textContent = `${item.created_at} · ${item.trace_id}`;
  const payloadView = renderTraceLightObject(item.payload || {});
  card.append(summary, meta, payloadView);
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
    if (tracePanel && !tracePanel.children.length) {
      tracePanel.textContent = "trace 暂时读取失败";
    }
    return;
  }
  const data = await response.json();
  preserveScrollDuring(() => {
    tracePanel.replaceChildren(...sortTraceItemsNewestFirst(filterDuplicateTraceItems(data.items)).map(renderTraceItem));
  });
}

function notePanelRefreshError(error) {
  const message = error && error.message ? error.message : String(error || "读取失败");
  if (tracePanel && !tracePanel.children.length) {
    tracePanel.textContent = `trace 暂时读取失败：${message}`;
  }
  console.warn("analysis panel refresh failed", error);
}

function selectionTouchesRightPanel() {
  const selection = window.getSelection ? window.getSelection() : null;
  if (!selection || selection.isCollapsed || selection.rangeCount === 0) {
    return false;
  }
  const rightPanel = tracePanel ? tracePanel.closest(".analysis-trace") : null;
  if (!rightPanel) {
    return false;
  }
  for (let index = 0; index < selection.rangeCount; index += 1) {
    const range = selection.getRangeAt(index);
    if (rightPanel.contains(range.commonAncestorContainer)) {
      return true;
    }
  }
  return false;
}

async function flushAnalysisPanelsRefresh(options = {}) {
  const force = Boolean(options.force);
  if (panelRefreshTimer) {
    window.clearTimeout(panelRefreshTimer);
    panelRefreshTimer = 0;
  }
  if (!force && selectionTouchesRightPanel()) {
    return;
  }
  if (panelRefreshRunning) {
    panelRefreshPending = true;
    backgroundRefreshPending = backgroundRefreshPending || Boolean(options.background);
    return;
  }
  if (!panelRefreshPending && !force) {
    return;
  }
  const shouldRefreshBackground = backgroundRefreshPending || Boolean(options.background);
  panelRefreshPending = false;
  backgroundRefreshPending = false;
  panelRefreshRunning = true;
  try {
    await refreshTraces();
    if (shouldRefreshBackground) {
      await refreshBackground();
    }
  } finally {
    panelRefreshRunning = false;
    if (panelRefreshPending && !selectionTouchesRightPanel()) {
      scheduleAnalysisPanelsRefresh({ background: backgroundRefreshPending, delay: 120 });
    }
  }
}

function scheduleAnalysisPanelsRefresh(options = {}) {
  panelRefreshPending = true;
  backgroundRefreshPending = backgroundRefreshPending || Boolean(options.background);
  const delay = Number.isFinite(Number(options.delay)) ? Number(options.delay) : 350;
  const force = Boolean(options.force);
  if (!force && selectionTouchesRightPanel()) {
    return;
  }
  if (panelRefreshTimer) {
    window.clearTimeout(panelRefreshTimer);
  }
  panelRefreshTimer = window.setTimeout(() => {
    flushAnalysisPanelsRefresh({ force, background: Boolean(options.background) })
      .catch(notePanelRefreshError);
  }, delay);
}

function stopAnalysisPanelsRefreshWatch() {
  if (panelRefreshWatchTimer) {
    window.clearTimeout(panelRefreshWatchTimer);
    panelRefreshWatchTimer = 0;
  }
  panelRefreshWatchUntil = 0;
}

function startAnalysisPanelsRefreshWatch(options = {}) {
  const durationMs = Number.isFinite(Number(options.durationMs)) ? Number(options.durationMs) : 180000;
  const intervalMs = Number.isFinite(Number(options.intervalMs)) ? Number(options.intervalMs) : 3000;
  panelRefreshWatchUntil = Math.max(panelRefreshWatchUntil, Date.now() + durationMs);
  if (panelRefreshWatchTimer) {
    return;
  }
  const tick = () => {
    if (Date.now() >= panelRefreshWatchUntil) {
      stopAnalysisPanelsRefreshWatch();
      return;
    }
    scheduleAnalysisPanelsRefresh({ background: true, delay: 0 });
    panelRefreshWatchTimer = window.setTimeout(tick, intervalMs);
  };
  panelRefreshWatchTimer = window.setTimeout(tick, intervalMs);
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
  card.append(summary, metaEl, pre);
  return card;
}

function renderIdleProgress(progress = {}) {
  const stage = progress.stage || "waiting";
  const label = progress.label || "等待开启";
  const percent = Math.max(0, Math.min(100, Number(progress.percent || 0)));
  const card = document.createElement("section");
  card.className = `background-progress is-${stage}`;

  const header = document.createElement("div");
  header.className = "background-progress-header";
  const title = document.createElement("strong");
  title.textContent = "后台任务进度";
  const value = document.createElement("span");
  value.textContent = `${label} · ${percent}%`;
  header.append(title, value);

  const track = document.createElement("div");
  track.className = "background-progress-bar";
  const fill = document.createElement("div");
  fill.className = "background-progress-bar-fill";
  fill.style.width = `${percent}%`;
  track.appendChild(fill);

  const detail = document.createElement("div");
  detail.className = "background-progress-detail";
  detail.textContent = [
    progress.title ? `任务：${progress.title}` : "",
    progress.reason ? `原因：${progress.reason}` : "",
    progress.updated_at ? `更新时间：${progress.updated_at}` : "",
  ].filter(Boolean).join(" · ") || "空闲时会自动进行创作、记忆去重和开场缓存。";

  card.append(header, track, detail);
  return card;
}

function backgroundSortTime(item) {
  const value = item.updated_at || item.created_at || item.finished_at || item.started_at || "";
  const time = Date.parse(value);
  return Number.isNaN(time) ? 0 : time;
}

function formatBackgroundDuration(value) {
  const ms = Number(value || 0);
  if (!Number.isFinite(ms) || ms <= 0) return "";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms / 60000)}min`;
}

function readableWorkerReason(reason) {
  const reasons = {
    active_generation: "正在回复用户，后台任务暂缓",
    memory_agent_busy: "记忆整理正在运行，先不启动其它任务",
    memory_dedupe_agent_running: "记忆去重已经在运行",
    idle_agent_running: "后台写作已经在运行",
    idle_wait: "用户刚刚活动过，等待空闲",
    recent_run: "刚完成过一次写作，等待下次空闲窗口",
    recent_run_exists: "刚完成过一次任务，等待下次空闲窗口",
    recent_prompt_cache: "开场缓存刚刷新过，本轮不用重复刷新",
    recent_memory_dedupe: "记忆去重刚运行过，本轮不用重复去重",
    no_devices: "没有找到需要刷新开场缓存的设备",
    no_candidates: "没有发现足够相似的候选记忆",
    idle_disabled: "后台写作已关闭",
    idle_paused: "后台写作已暂停",
    memory_dedupe_disabled: "记忆去重已关闭",
    refreshed: "已刷新缓存",
    error: "运行出错",
  };
  return reasons[reason] || reason || "无额外原因";
}

function readableWorkerTask(task) {
  const tasks = {
    opening_cache: "开场缓存",
    memory_dedupe: "记忆去重",
    idle_write: "后台写作",
    memory_agent: "记忆整理",
  };
  return tasks[task] || task || "后台任务";
}

function describeDedupeResult(result) {
  const action = result && result.action ? result.action : {};
  const applied = result && result.result ? result.result : {};
  const keepId = action.keep_id || action.target_id || action.memory_id || "";
  const removeIds = Array.isArray(action.remove_ids) ? action.remove_ids : [];
  const kind = action.kind || action.action || "处理";
  if (removeIds.length && keepId) {
    return `将记忆 #${removeIds.join("、#")} 合并/删除到 #${keepId}（${kind}）`;
  }
  if (keepId && applied.rewritten) {
    return `重写了记忆 #${keepId}`;
  }
  if (keepId) {
    return `检查了记忆 #${keepId}（${kind}）`;
  }
  return JSON.stringify(action);
}

function workerActivitySummary(item) {
  const metadata = item.metadata || {};
  const eventType = item.event_type || "";
  if (eventType === "idle_worker_tick") {
    return { title: "后台巡检开始", meta: "检查是否需要刷新开场、整理记忆或继续写作", details: "这是一轮后台巡检的开始记录。" };
  }
  if (eventType === "idle_worker_tick_done") {
    const completed = metadata.completed_task || "none";
    const taskText = completed === "none" ? "没有需要执行的任务" : `已执行：${readableWorkerTask(completed)}`;
    return { title: `后台巡检完成：${taskText}`, meta: "", details: taskText };
  }
  if (eventType === "idle_worker_skip") {
    const task = readableWorkerTask(metadata.task);
    return {
      title: `${task}：本轮暂不执行`,
      meta: readableWorkerReason(metadata.reason),
      details: `${task}没有启动。原因：${readableWorkerReason(metadata.reason)}。`,
    };
  }
  if (eventType === "idle_worker_error") {
    const task = readableWorkerTask(metadata.task);
    return {
      title: `${task}：运行故障`,
      meta: metadata.error || readableWorkerReason(metadata.reason),
      details: JSON.stringify(metadata, null, 2),
    };
  }
  if (eventType === "opening_cache_idle_refresh") {
    const devices = Array.isArray(metadata.refreshed_devices) ? metadata.refreshed_devices : [];
    const count = Number(metadata.device_count || devices.length || 0);
    const title = count > 0 ? `开场 prompt 缓存：已刷新 ${count} 个设备` : "开场 prompt 缓存：无需刷新";
    const details = count > 0
      ? [`刷新设备：${devices.join("、") || `${count} 个设备`}`]
      : [readableWorkerReason(metadata.reason)];
    return { title, meta: readableWorkerReason(metadata.reason), details: details.join("\n") };
  }
  if (eventType === "opening_cache_refresh_error") {
    return { title: "开场 prompt 缓存：运行故障", meta: metadata.error || "error", details: JSON.stringify(metadata, null, 2) };
  }
  if (eventType === "memory_dedupe_agent_run") {
    const applied = Number(metadata.applied || 0);
    const candidates = Number(metadata.candidate_count || 0);
    const lines = [`检查候选记忆：${candidates} 组`, `实际消除/合并：${applied} 条`];
    if (Array.isArray(metadata.results) && metadata.results.length) {
      metadata.results.slice(0, 8).forEach((result) => lines.push(`- ${describeDedupeResult(result)}`));
    }
    return {
      title: applied > 0 ? `记忆去重：消除/合并 ${applied} 条` : "记忆去重：未发现需要合并的记忆",
      meta: candidates ? `检查了 ${candidates} 组候选` : "没有候选",
      details: lines.join("\n"),
    };
  }
  if (eventType === "memory_dedupe_agent_error") {
    return { title: "记忆去重：运行故障", meta: metadata.error || "error", details: JSON.stringify(metadata, null, 2) };
  }
  if (eventType === "idle_agent_artifact_created") {
    const parts = [
      metadata.title ? `标题：${metadata.title}` : "",
      metadata.artifact_id ? `成果编号：#${metadata.artifact_id}` : "",
      metadata.series_title ? `系列：${metadata.series_title}` : "",
      metadata.episode_index ? `集数：${metadata.episode_index}` : "",
      metadata.summary ? `简介：${metadata.summary}` : "",
    ].filter(Boolean);
    return {
      title: `后台写作：完成《${metadata.title || `#${metadata.artifact_id || "未命名"}`}》`,
      meta: metadata.artifact_type ? `类型：${metadata.artifact_type}` : "已写入成果库",
      details: parts.join("\n") || "已写入成果库。",
    };
  }
  if (eventType === "idle_agent_error") {
    return { title: "后台写作：运行故障", meta: metadata.error || "error", details: JSON.stringify(metadata, null, 2) };
  }
  if (eventType === "warning_idle_worker_watchdog") {
    return { title: "后台 watchdog 告警", meta: metadata.message || metadata.kind || "需要检查", details: JSON.stringify(metadata, null, 2) };
  }
  return {
    title: readableWorkerTask(metadata.task || eventType),
    meta: readableWorkerReason(metadata.reason || metadata.status || metadata.error || ""),
    details: JSON.stringify(metadata, null, 2),
  };
}

function renderWorkerActivityItem(item) {
  const key = backgroundItemKey("activity", item);
  const metadata = item.metadata || {};
  const duration = formatBackgroundDuration(metadata.duration_ms);
  const triggeredAt = formatWorkerTriggerTime(metadata.started_at || item.created_at);
  const summary = workerActivitySummary(item);
  const meta = [
    triggeredAt ? `触发 ${triggeredAt}` : "",
    summary.meta,
    duration ? `运行 ${duration}` : "",
  ].filter(Boolean).join(" · ");
  return renderBackgroundItem(key, summary.title, meta, summary.details);
}

function isQuietWorkerActivity(item) {
  const metadata = item.metadata || {};
  const eventType = item.event_type || "";
  if (eventType === "idle_worker_tick") {
    return true;
  }
  if (eventType === "idle_worker_tick_done") {
    return !metadata.completed_task || metadata.completed_task === "none";
  }
  if (eventType === "idle_worker_skip") {
    return true;
  }
  if (eventType === "opening_cache_idle_refresh") {
    const count = Number(metadata.device_count || 0);
    return count <= 0;
  }
  return false;
}

function quietWorkerReasonKey(item) {
  const metadata = item.metadata || {};
  if (item.event_type === "idle_worker_tick") {
    return "后台巡检";
  }
  if (item.event_type === "idle_worker_tick_done") {
    return "巡检无任务";
  }
  if (item.event_type === "idle_worker_skip") {
    return `${readableWorkerTask(metadata.task)}暂未执行：${readableWorkerReason(metadata.reason)}`;
  }
  if (item.event_type === "opening_cache_idle_refresh") {
    return `开场缓存暂未刷新：${readableWorkerReason(metadata.reason)}`;
  }
  return readableWorkerReason(metadata.reason || metadata.status || item.event_type || "quiet");
}

function compactWorkerActivities(items) {
  const compacted = [];
  let quietGroup = [];
  const flushQuietGroup = () => {
    if (!quietGroup.length) {
      return;
    }
    if (quietGroup.length === 1) {
      compacted.push(quietGroup[0]);
    } else {
      compacted.push({
        __quiet_group: true,
        id: `quiet:${quietGroup[0].id || quietGroup[0].created_at}:${quietGroup[quietGroup.length - 1].id || quietGroup[quietGroup.length - 1].created_at}`,
        items: quietGroup,
        created_at: quietGroup[0].created_at,
        metadata: {
          started_at: quietGroup[quietGroup.length - 1].metadata?.started_at || quietGroup[quietGroup.length - 1].created_at,
          newest_at: quietGroup[0].metadata?.started_at || quietGroup[0].created_at,
          oldest_at: quietGroup[quietGroup.length - 1].metadata?.started_at || quietGroup[quietGroup.length - 1].created_at,
        },
      });
    }
    quietGroup = [];
  };

  items.forEach((item) => {
    if (isQuietWorkerActivity(item)) {
      quietGroup.push(item);
      return;
    }
    flushQuietGroup();
    compacted.push(item);
  });
  flushQuietGroup();
  return compacted;
}

function renderQuietWorkerGroup(group) {
  const items = group.items || [];
  const key = backgroundItemKey("quiet-group", group);
  const newest = formatWorkerTriggerTime(group.metadata?.newest_at || group.created_at);
  const oldest = formatWorkerTriggerTime(group.metadata?.oldest_at || group.created_at);
  const reasonCounts = new Map();
  items.forEach((item) => {
    const keyText = quietWorkerReasonKey(item);
    reasonCounts.set(keyText, (reasonCounts.get(keyText) || 0) + 1);
  });
  const reasons = Array.from(reasonCounts.entries())
    .sort((left, right) => right[1] - left[1])
    .map(([reason, count]) => `${reason} × ${count}`);
  const meta = [
    newest && oldest ? `范围 ${oldest} - ${newest}` : "",
    `${items.length} 条后台自检/未执行记录已合并`,
  ].filter(Boolean).join(" · ");
  const detailLines = [
    "这些记录只是后台巡检、等待空闲、任务忙碌或暂时无事可做；没有真正写入成果或修改记忆。",
    "",
    "合并原因：",
    ...reasons.map((line) => `- ${line}`),
  ];
  return renderBackgroundItem(key, `后台自检/暂未执行：合并 ${items.length} 条`, meta, detailLines.join("\n"));
}

function renderWorkerActivity(activity) {
  if (activity && activity.__quiet_group) {
    return renderQuietWorkerGroup(activity);
  }
  return renderWorkerActivityItem(activity);
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
  body.appendChild(contentEl);

  card.append(summary, metaEl, body);
  return card;
}

async function refreshBackground() {
  if (!backgroundPanel) {
    return;
  }
  const response = await fetch(`/api/analysis/background?limit=${encodeURIComponent(backgroundActivityLimit)}`);
  if (response.status === 401) {
    window.location.href = "/analysis";
    return;
  }
  if (!response.ok) {
    if (!backgroundPanel.children.length) {
      backgroundPanel.textContent = "后台任务暂时读取失败";
    }
    return;
  }
  const data = await response.json();
  const items = [renderIdleProgress(data.progress || {})];
  const activities = (data.activities || [])
    .slice()
    .sort((left, right) => backgroundSortTime(right) - backgroundSortTime(left));
  compactWorkerActivities(activities).forEach((item) => items.push(renderWorkerActivity(item)));
  preserveScrollDuring(() => {
    backgroundPanel.replaceChildren(...items);
  });
  if (backgroundMoreButton) {
    const count = Array.isArray(data.activities) ? data.activities.length : 0;
    backgroundMoreButton.hidden = count < backgroundActivityLimit;
    backgroundMoreButton.textContent = `显示更多（当前 ${count} 条）`;
  }
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
    drawMode = false,
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
  setStatus(hasLargeAttachment(attachmentsForMessage) ? "图片过大，狠狠压缩中..." : (drawMode ? "画图 prompt 优化中" : "生成中"));
  const sampling = readChatSamplingSettings();
  try {
    const response = await fetch("/api/chat/stream", {
      method: "POST",
      headers: jsonHeaders(),
      signal: activeController.signal,
      body: JSON.stringify({
        session_id: sessionId,
        message: text,
        mode: drawMode ? "draw" : "chat",
        attachments: attachmentsForMessage,
        hidden_user: hiddenUser,
        cached_opening: Boolean(options.cachedOpening),
        web_search: drawMode ? false : webSearchInput.checked,
        web_search_proxy: sampling.web_search_proxy,
        temperature: sampling.temperature,
        top_p: sampling.top_p,
        max_tokens: maxTokens,
        analysis_mode: true,
      }),
    });
    if (response.status === 429) {
      const detail = await parseRateLimitPayload(response);
      removeEmptyAssistantBubble(assistantBody);
      setStatus((detail && detail.message) || "发送太快了，请稍后再试");
      return;
    }
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
        } else if (parsed.event === "draw_status") {
          setStatus(payload.message || "画图中");
        } else if (parsed.event === "draw_prompt") {
          setStatus("HiDream 生成中");
          if (payload.optimized_prompt) {
            assistantMarkdown = "画图 prompt 已优化，正在生成图片。";
            setRenderedMarkdown(assistantBody, assistantMarkdown);
          }
        } else if (parsed.event === "draw_image_batch") {
          const images = Array.isArray(payload.images) ? payload.images : [];
          assistantBody.replaceChildren();
          assistantBody.appendChild(renderAnalysisGeneratedImageBatch(images, payload.optimized_prompt || ""));
          assistantBody.dataset.rawMarkdown = `已生成 ${images.length} 张图片。`;
          assistantMarkdown = assistantBody.dataset.rawMarkdown;
          setStatus(`图片已生成：${images.length} 张`);
          messagesEl.scrollTop = messagesEl.scrollHeight;
        } else if (parsed.event === "draw_error") {
          assistantMarkdown = payload.message || "图片生成失败";
          setRenderedMarkdown(assistantBody, assistantMarkdown);
          setStatus("图片生成失败");
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
          if (payload.skipped_empty && !assistantMarkdown.trim()) {
            removeEmptyAssistantBubble(assistantBody);
          } else if (payload.content && !assistantMarkdown.trim()) {
            assistantMarkdown = payload.content;
            setRenderedMarkdown(assistantBody, assistantMarkdown);
          }
          setStatus(`session ${sessionId.slice(0, 8)}`);
        }
      }
      scheduleAnalysisPanelsRefresh();
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
    scheduleAnalysisPanelsRefresh({ background: true, delay: 100 });
    startAnalysisPanelsRefreshWatch({ durationMs: 180000, intervalMs: 3000 });
  }
}

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = messageInput.value.trim();
  if ((!text && !pendingAttachments.length) || !sessionId || activeController) {
    return;
  }
  messageInput.value = "";
  const drawMode = analysisDrawEnabled;
  await sendMessage(text || "请分析这张图片。", { drawMode });
  setAnalysisDrawEnabled(analysisDrawEnabled);
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
  clearAnalysisDrawModeSelection();
  if (activeController) {
    await stopActiveGeneration();
  }
  await resetSession();
});

if (refreshTraceButton) {
  refreshTraceButton.addEventListener("click", () => {
    clearAnalysisDrawModeSelection();
    scheduleAnalysisPanelsRefresh({ force: true, background: true, delay: 0 });
  });
}
if (backgroundMoreButton) {
  backgroundMoreButton.addEventListener("click", () => {
    backgroundActivityLimit += 20;
    refreshBackground().catch(notePanelRefreshError);
  });
}
analysisAttachImageButton.addEventListener("click", () => analysisImageInput.click());
analysisWebSearchButton.addEventListener("click", () => {
  setAnalysisWebSearchEnabled(!webSearchInput.checked);
  setStatus(webSearchInput.checked ? "联网搜索已开启" : "联网搜索已关闭");
  messageInput.focus();
});
if (analysisDrawButton) {
  analysisDrawButton.addEventListener("click", () => {
    setAnalysisDrawEnabled(!analysisDrawEnabled);
    setStatus(analysisDrawEnabled ? "画图已开启" : "画图已关闭");
    messageInput.focus();
  });
}
analysisImageInput.addEventListener("change", () => handleImageFiles(analysisImageInput.files));
loadPreviousButton.addEventListener("click", () => loadPreviousAnalysisSessionContext());
messagesEl.addEventListener("wheel", handleDesktopPreviousAnalysisSessionWheel, { passive: false });
document.addEventListener("selectionchange", () => {
  if (panelRefreshPending && !selectionTouchesRightPanel()) {
    scheduleAnalysisPanelsRefresh({ background: backgroundRefreshPending, delay: 120 });
  }
});

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
window.addEventListener("pageshow", clearAnalysisDrawModeSelection);

setAnalysisWebSearchEnabled(false);
clearAnalysisDrawModeSelection();
loadAnalysisModelDisplayName().catch(() => {});

setStatus("创建会话中");
createSession()
  .then(() => {
    scheduleAnalysisPanelsRefresh({ background: true, delay: 0 });
  })
  .catch((error) => {
    setStatus(error.message || "初始化失败");
  });

window.addEventListener("pagehide", () => {
  if (panelRefreshTimer) {
    window.clearTimeout(panelRefreshTimer);
    panelRefreshTimer = 0;
  }
  stopAnalysisPanelsRefreshWatch();
});
