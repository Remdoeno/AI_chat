const statusText = document.getElementById("statusText");
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
const temperatureInput = document.getElementById("temperatureInput");
const topPInput = document.getElementById("topPInput");
const proxyInput = document.getElementById("proxyInput");
const analysisUserMemoryBindingButton = document.getElementById("analysisUserMemoryBindingButton");
const analysisUserMemoryBindingCrown = document.getElementById("analysisUserMemoryBindingCrown");
const analysisUserMemoryBindingSummary = document.getElementById("analysisUserMemoryBindingSummary");
const analysisUserMemoryBindingDialog = document.getElementById("analysisUserMemoryBindingDialog");
const analysisUserMemoryBindingForm = document.getElementById("analysisUserMemoryBindingForm");
const analysisUserMemoryBindingInput = document.getElementById("analysisUserMemoryBindingInput");
const analysisShareChatHistoryCheckbox = document.getElementById("analysisShareChatHistoryCheckbox");
const analysisHostDeviceCheckbox = document.getElementById("analysisHostDeviceCheckbox");
const analysisUserMemoryBindingStatus = document.getElementById("analysisUserMemoryBindingStatus");
const analysisUserMemoryBindingCancelButton = document.getElementById("analysisUserMemoryBindingCancelButton");
const analysisUserMemoryBindingInfoButton = document.getElementById("analysisUserMemoryBindingInfoButton");
const analysisUserMemoryBindingInfo = document.getElementById("analysisUserMemoryBindingInfo");
const webSearchInput = document.getElementById("webSearchInput");
const analysisAttachImageButton = document.getElementById("analysisAttachImageButton");
const analysisWebSearchButton = document.getElementById("analysisWebSearchButton");
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
let traceTimer = null;
let pendingAttachments = [];
let backgroundActivityLimit = 20;
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
const USER_MEMORY_BINDING_STORAGE_KEY = "qwen_user_memory_binding";
const CHAT_SAMPLING_STORAGE_KEY = "qwen_sampling_settings";
const ANALYSIS_SAMPLING_STORAGE_KEY = "qwen_analysis_sampling_settings";
let deviceId = localStorage.getItem(DEVICE_STORAGE_KEY) || "";
let userMemoryBindingState = null;

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

function bindingSummaryText(binding) {
  if (!binding || !binding.shared_user_id) {
    return "未绑定共享用户";
  }
  const userId = String(binding.shared_user_id || "").trim();
  const maskedUserId = userId ? `${userId.slice(0, 1)}***` : "";
  const parts = [maskedUserId ? `共享用户：${maskedUserId}` : "已绑定共享用户"];
  parts.push(binding.share_chat_history ? "共享聊天记录" : "仅共享长期记忆");
  if (binding.is_host) {
    parts.push("本设备为主机");
  }
  return parts.join(" · ");
}

function publishUserMemoryBindingState() {
  try {
    localStorage.setItem(USER_MEMORY_BINDING_STORAGE_KEY, JSON.stringify({
      device_id: ensureDeviceId(),
      binding: userMemoryBindingState || {},
      cached_at: Date.now(),
    }));
  } catch (_) {
    // localStorage may be unavailable in strict private contexts.
  }
}

function readCachedUserMemoryBindingState() {
  try {
    const raw = localStorage.getItem(USER_MEMORY_BINDING_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const payload = JSON.parse(raw);
    if (!payload || payload.device_id !== ensureDeviceId()) {
      return null;
    }
    return payload.binding && typeof payload.binding === "object" ? payload.binding : null;
  } catch (_) {
    return null;
  }
}

function applyCachedUserMemoryBindingState() {
  const cached = readCachedUserMemoryBindingState();
  if (!cached) {
    return false;
  }
  applyUserMemoryBindingState(cached, { publish: false });
  return true;
}

function applyUserMemoryBindingState(binding, options = {}) {
  const shouldPublish = options.publish !== false;
  const payload = binding && typeof binding === "object" ? binding : {};
  userMemoryBindingState = {
    shared_user_id: String(payload.shared_user_id || "").trim(),
    share_chat_history: Boolean(payload.share_chat_history),
    is_host: Boolean(payload.is_host),
    host_device_id: String(payload.host_device_id || ""),
  };
  if (analysisUserMemoryBindingButton) {
    analysisUserMemoryBindingButton.classList.toggle("is-host", userMemoryBindingState.is_host);
  }
  if (analysisUserMemoryBindingSummary) {
    analysisUserMemoryBindingSummary.textContent = bindingSummaryText(userMemoryBindingState);
  }
  if (analysisUserMemoryBindingCrown) {
    analysisUserMemoryBindingCrown.hidden = !userMemoryBindingState.is_host;
  }
  if (shouldPublish) {
    publishUserMemoryBindingState();
  }
}

function syncUserMemoryBindingForm() {
  const binding = userMemoryBindingState || {};
  if (!analysisUserMemoryBindingInput) {
    return;
  }
  analysisUserMemoryBindingInput.value = String(binding.shared_user_id || "");
  analysisShareChatHistoryCheckbox.checked = Boolean(binding.share_chat_history);
  analysisHostDeviceCheckbox.checked = Boolean(binding.is_host);
}

function setAnalysisBindingInfoVisible(visible) {
  if (!analysisUserMemoryBindingInfo) {
    return;
  }
  analysisUserMemoryBindingInfo.hidden = !visible;
  if (analysisUserMemoryBindingInfoButton) {
    analysisUserMemoryBindingInfoButton.setAttribute("aria-expanded", visible ? "true" : "false");
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
      temperatureInput.value = String(clampNumber(payload.temperature, 0, 2, 0.6));
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
    temperature: clampNumber(temperatureInput.value, 0, 2, 0.6),
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

async function loadUserMemoryBinding() {
  applyCachedUserMemoryBindingState();
  try {
    const response = await fetch("/api/user-memory-binding", {
      headers: deviceIdentityHeaders(),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const payload = await response.json();
    applyUserMemoryBindingState(payload);
  } catch (error) {
    if (analysisUserMemoryBindingSummary) {
      analysisUserMemoryBindingSummary.textContent = `绑定读取失败：${error.message}`;
    }
  }
}

function openUserMemoryBindingDialog() {
  if (!analysisUserMemoryBindingDialog) {
    return;
  }
  analysisUserMemoryBindingStatus.textContent = "";
  syncUserMemoryBindingForm();
  setAnalysisBindingInfoVisible(false);
  if (typeof analysisUserMemoryBindingDialog.showModal === "function") {
    analysisUserMemoryBindingDialog.showModal();
  } else {
    analysisUserMemoryBindingDialog.setAttribute("open", "");
  }
  analysisUserMemoryBindingInput.focus();
  analysisUserMemoryBindingInput.select();
}

function closeUserMemoryBindingDialog() {
  if (!analysisUserMemoryBindingDialog) {
    return;
  }
  analysisUserMemoryBindingDialog.close();
}

async function saveUserMemoryBinding(event) {
  event.preventDefault();
  const sharedUserId = String(analysisUserMemoryBindingInput.value || "").trim();
  const payload = {
    shared_user_id: sharedUserId,
    share_chat_history: sharedUserId ? Boolean(analysisShareChatHistoryCheckbox.checked) : false,
    is_host: sharedUserId ? Boolean(analysisHostDeviceCheckbox.checked) : false,
  };
  analysisUserMemoryBindingStatus.textContent = "保存中";
  try {
    const response = await fetch("/api/user-memory-binding", {
      method: "PUT",
      headers: jsonHeaders(),
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const result = await response.json();
    applyUserMemoryBindingState(result);
    analysisUserMemoryBindingStatus.textContent = result.shared_user_id ? "已保存共享绑定" : "已关闭共享绑定";
    setStatus(result.shared_user_id ? "共享记忆配置已更新" : "已关闭共享记忆");
    if (result.left_previous_shared_user) {
      window.alert("已退出当前记忆共享。");
    }
    window.setTimeout(() => closeUserMemoryBindingDialog(), 180);
  } catch (error) {
    analysisUserMemoryBindingStatus.textContent = `保存失败：${error.message}`;
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
  if (data.memory_binding) {
    applyUserMemoryBindingState(data.memory_binding);
  }
  resetPreviousAnalysisSessionLoadState();
  ensureAnalysisHistoryLoadIndicator();
  syncPreviousAnalysisSessionButton();
  setStatus(`session ${sessionId.slice(0, 8)}`);
  refreshTraces().catch((error) => setStatus(`trace 读取失败: ${error.message}`));
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
  if (data.memory_binding) {
    applyUserMemoryBindingState(data.memory_binding);
  }
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
  const response = await fetch(`/api/analysis/background?limit=${encodeURIComponent(backgroundActivityLimit)}`);
  if (response.status === 401) {
    window.location.href = "/analysis";
    return;
  }
  if (!response.ok) {
    backgroundPanel.textContent = "后台任务读取失败";
    return;
  }
  const data = await response.json();
  const items = [renderIdleProgress(data.progress || {})];
  const activities = (data.activities || [])
    .slice()
    .sort((left, right) => backgroundSortTime(right) - backgroundSortTime(left));
  compactWorkerActivities(activities).forEach((item) => items.push(renderWorkerActivity(item)));
  collectPayloadScrollPositions(backgroundPanel, "backgroundKey", backgroundPayloadScrollPositions);
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
        temperature: clampNumber(temperatureInput.value, 0, 2, 0.6),
        top_p: clampNumber(topPInput.value, 0, 1, 0.95),
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
if (backgroundMoreButton) {
  backgroundMoreButton.addEventListener("click", () => {
    backgroundActivityLimit += 20;
    refreshBackground().catch((error) => setStatus(`后台任务读取失败: ${error.message}`));
  });
}
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
analysisUserMemoryBindingButton.addEventListener("click", openUserMemoryBindingDialog);
analysisUserMemoryBindingForm.addEventListener("submit", saveUserMemoryBinding);
analysisUserMemoryBindingCancelButton.addEventListener("click", closeUserMemoryBindingDialog);
analysisUserMemoryBindingInput.addEventListener("input", () => {
  const hasValue = Boolean(String(analysisUserMemoryBindingInput.value || "").trim());
  if (!hasValue) {
    analysisShareChatHistoryCheckbox.checked = false;
    analysisHostDeviceCheckbox.checked = false;
  }
});
analysisUserMemoryBindingInfoButton.addEventListener("click", () => {
  setAnalysisBindingInfoVisible(Boolean(analysisUserMemoryBindingInfo.hidden));
});
document.addEventListener("click", (event) => {
  if (!analysisUserMemoryBindingInfo || analysisUserMemoryBindingInfo.hidden) {
    return;
  }
  const target = event.target;
  if (analysisUserMemoryBindingInfoButton.contains(target) || analysisUserMemoryBindingInfo.contains(target)) {
    return;
  }
  setAnalysisBindingInfoVisible(false);
});
window.addEventListener("storage", (event) => {
  if (event.key === USER_MEMORY_BINDING_STORAGE_KEY) {
    if (!applyCachedUserMemoryBindingState()) {
      loadUserMemoryBinding().catch(() => {});
    }
  }
});
window.addEventListener("focus", () => {
  loadUserMemoryBinding().catch(() => {});
});
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) {
    loadUserMemoryBinding().catch(() => {});
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

loadAnalysisSamplingSettings();
setAnalysisWebSearchEnabled(false);
loadUserMemoryBinding().catch(() => {});

setStatus("创建会话中");
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
