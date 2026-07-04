const messagesEl = document.getElementById("messages");
const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("messageInput");
const sendButton = document.getElementById("sendButton");
const quotePreview = document.getElementById("quotePreview");
const quotePreviewText = document.getElementById("quotePreviewText");
const clearQuoteButton = document.getElementById("clearQuoteButton");
const attachImageButton = document.getElementById("attachImageButton");
const webSearchButton = document.getElementById("webSearchButton");
const drawButton = document.getElementById("drawButton");
const imageInput = document.getElementById("imageInput");
const attachmentPreview = document.getElementById("attachmentPreview");
const resetButton = document.getElementById("resetButton");
const statusText = document.getElementById("statusText");
const bunnyLogoButton = document.getElementById("bunnyLogoButton");
const userMemoryBindingButton = document.getElementById("userMemoryBindingButton");
const userMemoryBindingLabel = document.getElementById("userMemoryBindingLabel");
const userMemoryBindingCrown = document.getElementById("userMemoryBindingCrown");
const userMemoryBindingSummary = document.getElementById("userMemoryBindingSummary");
const memoryAdminButton = document.getElementById("memoryAdminButton");
const memoryAdminDialog = document.getElementById("memoryAdminDialog");
const memoryAdminLoginForm = document.getElementById("memoryAdminLoginForm");
const memoryAdminPassword = document.getElementById("memoryAdminPassword");
const memoryAdminLoginStatus = document.getElementById("memoryAdminLoginStatus");
const memoryAdminCancelButton = document.getElementById("memoryAdminCancelButton");
const userMemoryBindingDialog = document.getElementById("userMemoryBindingDialog");
const userMemoryBindingForm = document.getElementById("userMemoryBindingForm");
const userMemoryBindingInput = document.getElementById("userMemoryBindingInput");
const shareChatHistoryCheckbox = document.getElementById("shareChatHistoryCheckbox");
const hostDeviceCheckbox = document.getElementById("hostDeviceCheckbox");
const inheritAssistantProfileCheckbox = document.getElementById("inheritAssistantProfileCheckbox");
const userMemoryBindingStatus = document.getElementById("userMemoryBindingStatus");
const userMemoryBindingCancelButton = document.getElementById("userMemoryBindingCancelButton");
const userMemoryBindingInfoButton = document.getElementById("userMemoryBindingInfoButton");
const userMemoryBindingInfo = document.getElementById("userMemoryBindingInfo");
const advancedOptions = document.getElementById("advancedOptions");
const advancedOptionsForm = document.getElementById("advancedOptionsForm");
const temperatureRange = document.getElementById("temperatureRange");
const temperatureValue = document.getElementById("temperatureValue");
const topPRange = document.getElementById("topPRange");
const topPValue = document.getElementById("topPValue");
const webSearchProxyInput = document.getElementById("webSearchProxyInput");
const samplingSummary = document.getElementById("samplingSummary");
const confirmSamplingButton = document.getElementById("confirmSamplingButton");
const cancelSamplingButton = document.getElementById("cancelSamplingButton");
const searchActivity = document.getElementById("searchActivity");
const searchActivityList = document.getElementById("searchActivityList");
const modelDisplayName = document.getElementById("modelDisplayName");
const openModelSettingsButton = document.getElementById("openModelSettingsButton");
const modelSettingsDialog = document.getElementById("modelSettingsDialog");
const modelSettingsForm = document.getElementById("modelSettingsForm");
const modelSettingsCancelButton = document.getElementById("modelSettingsCancelButton");
const modelSettingsStatus = document.getElementById("modelSettingsStatus");
const localModelServiceButton = document.getElementById("localModelServiceButton");
const localModelServiceStatus = document.getElementById("localModelServiceStatus");

const BUNNY_CLICK_WINDOW_MS = 1000;
const BUNNY_CLICK_TARGET = 4;
const WARN_LONG_PRESS_MS = 4000;
let warnLongPressTimer = 0;
let warnLongPressTriggered = false;
let memoryAdminLongPressTimer = 0;
let memoryAdminLongPressTriggered = false;
let localModelServicePollTimer = 0;
let pendingQuotedMessage = "";
const SAMPLING_STORAGE_KEY = "wangcai_sampling_settings";
const DEVICE_STORAGE_KEY = "wangcai_device_id";
const USER_MEMORY_BINDING_STORAGE_KEY = "wangcai_user_memory_binding";
const OPENING_PROMPT_STORAGE_KEY = "wangcai_opening_prompt";
const LEGACY_SAMPLING_STORAGE_KEY = "qwen_sampling_settings";
const LEGACY_DEVICE_STORAGE_KEY = "qwen_device_id";
const LEGACY_USER_MEMORY_BINDING_STORAGE_KEY = "qwen_user_memory_binding";
const DEFAULT_SAMPLING_SETTINGS = {
  temperature: 0.6,
  top_p: 0.95,
  web_search_proxy: "",
};
const LOCAL_MODEL_DISPLAY_NAME = "qwen3.6";
const MODEL_PROVIDER_PRESETS = {
  local: {
    display_name: LOCAL_MODEL_DISPLAY_NAME,
    base_url: "http://127.0.0.1:8000/v1",
    model: "qwen3.6-35b-a3b-262k",
    use_proxy: false,
    proxy_url: "",
  },
  none: {
    display_name: "未配置",
    base_url: "",
    model: "",
    use_proxy: false,
    proxy_url: "",
  },
  hidream: {
    display_name: "HiDream-O1-Image-Dev-2604",
    base_url: "http://127.0.0.1:8002",
    model: "HiDream-O1-Image-Dev-2604",
    use_proxy: false,
    proxy_url: "",
  },
  openai: {
    display_name: "gpt-5.5",
    base_url: "https://api.openai.com/v1",
    model: "gpt-5.5",
    use_proxy: true,
    proxy_url: "",
  },
  deepseek: {
    display_name: "deepseek-v4-pro",
    base_url: "https://api.deepseek.com/v1",
    model: "deepseek-v4-pro",
    use_proxy: true,
    proxy_url: "",
  },
  zhipu: {
    display_name: "glm-5.2",
    base_url: "https://open.bigmodel.cn/api/paas/v4",
    model: "glm-5.2",
    use_proxy: true,
    proxy_url: "",
  },
  dashscope: {
    display_name: "qwen3.7-max",
    base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    model: "qwen3.7-max",
    use_proxy: true,
    proxy_url: "",
  },
  doubao: {
    display_name: "doubao-seed-2.0-pro",
    base_url: "https://ark.cn-beijing.volces.com/api/v3",
    model: "doubao-seed-2-0-pro-260215",
    use_proxy: true,
    proxy_url: "",
  },
  custom: {
    display_name: "自定义模型",
    base_url: "",
    model: "",
    use_proxy: true,
    proxy_url: "",
  },
};
const MAX_ATTACHMENTS = 4;
const MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024;
const IMAGE_COMPRESSION_NOTICE_BYTES = 2 * 1024 * 1024;
const PREVIOUS_SESSION_ARM_MS = 1500;
const PREVIOUS_SESSION_MIN_RETRY_MS = 800;
const PREVIOUS_SESSION_PULL_THRESHOLD = 72;
const PREVIOUS_SESSION_DESKTOP_TOP_BUFFER = 96;
const TOUCH_TOP_INERTIA_WINDOW_MS = 800;
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

let sessionId = null;
let activeController = null;
let isResetting = false;
let bunnyClickTimes = [];
let samplingSettings = loadSamplingSettings();
let activeAssistantBody = null;
let userStoppedGeneration = false;
let openingGenerationActive = false;
let activeOpeningId = "";
let pendingAttachments = [];
let webSearchEnabled = false;
let drawEnabled = false;
let activeSearchQuery = "";
let isMessageComposing = false;
let deviceId = readMigratedStorage(DEVICE_STORAGE_KEY, LEGACY_DEVICE_STORAGE_KEY) || "";
let previousSessionArmedAt = 0;
let previousSessionHideTimer = 0;
let isLoadingPreviousSession = false;
let hasMorePreviousSessions = true;
let touchStartY = 0;
let touchPullDistance = 0;
let touchHistoryGestureFired = false;
let wasTouchScrollingTowardTop = false;
let touchHistoryArmOnTop = false;
let touchHistoryClearTimer = 0;
let userMemoryBindingState = null;
let modelSettingsState = null;

function isUsableDeviceId(value) {
  return /^[A-Za-z0-9_-]{12,96}$/.test(String(value || "").trim());
}

function setStatus(text) {
  statusText.textContent = text;
}

function modelField(slot, field) {
  return document.querySelector(`[data-model-slot="${slot}"][data-model-field="${field}"]`);
}

function modelPreset(provider) {
  return MODEL_PROVIDER_PRESETS[provider] || MODEL_PROVIDER_PRESETS.custom;
}

function isProxylessProvider(provider) {
  return ["local", "none", "hidream"].includes(provider);
}

function currentWebSearchProxy() {
  const liveValue = webSearchProxyInput ? webSearchProxyInput.value : "";
  return String(liveValue || samplingSettings.web_search_proxy || "").trim();
}

function setModelDisplayName(settings) {
  const chat = settings && settings.chat ? settings.chat : {};
  const name = chat.provider === "local"
    ? LOCAL_MODEL_DISPLAY_NAME
    : String(chat.model || chat.display_name || "AI模型").trim();
  if (modelDisplayName) {
    modelDisplayName.textContent = name || LOCAL_MODEL_DISPLAY_NAME;
  }
}

function applyProviderPreset(slot) {
  const providerInput = modelField(slot, "provider");
  const provider = providerInput ? providerInput.value : "local";
  const preset = modelPreset(provider);
  const displayInput = modelField(slot, "display_name");
  const baseUrlInput = modelField(slot, "base_url");
  const modelInput = modelField(slot, "model");
  const apiKeyInput = modelField(slot, "api_key");
  const useProxyInput = modelField(slot, "use_proxy");
  const proxyUrlInput = modelField(slot, "proxy_url");

  if (displayInput) {
    displayInput.value = provider === "local" ? LOCAL_MODEL_DISPLAY_NAME : preset.display_name;
    displayInput.disabled = provider === "local" || provider === "none";
  }
  if (baseUrlInput) {
    baseUrlInput.value = preset.base_url;
  }
  if (modelInput) {
    modelInput.value = preset.model;
  }
  if (apiKeyInput) {
    apiKeyInput.value = "";
    apiKeyInput.disabled = isProxylessProvider(provider);
    apiKeyInput.placeholder = provider === "local" || provider === "hidream" ? "本地服务通常不需要 API Key" : "留空则使用后台保存密钥";
  }
  if (useProxyInput) {
    useProxyInput.checked = Boolean(preset.use_proxy) && !isProxylessProvider(provider);
    useProxyInput.disabled = isProxylessProvider(provider);
  }
  if (proxyUrlInput) {
    proxyUrlInput.value = isProxylessProvider(provider) ? "" : (currentWebSearchProxy() || preset.proxy_url);
    proxyUrlInput.disabled = isProxylessProvider(provider);
  }
}

function populateModelSlot(slot, settings) {
  const data = settings && settings[slot] ? settings[slot] : { provider: "local" };
  const providerInput = modelField(slot, "provider");
  if (providerInput) {
    providerInput.value = data.provider || "local";
  }
  for (const field of ["display_name", "base_url", "model", "proxy_url"]) {
    const input = modelField(slot, field);
    if (input) {
      input.value = field === "proxy_url" && !isProxylessProvider(data.provider || "local")
        ? (data[field] || currentWebSearchProxy())
        : (data[field] || "");
    }
  }
  const apiKeyInput = modelField(slot, "api_key");
  if (apiKeyInput) {
    apiKeyInput.value = "";
    const providerKeys = settings && settings.provider_api_keys ? settings.provider_api_keys : {};
    const providerHasKey = Boolean(providerKeys[data.provider || ""]);
    apiKeyInput.placeholder = data.has_api_key || providerHasKey ? "后台已保存密钥，留空继续使用" : "留空则不设置密钥";
  }
  const useProxyInput = modelField(slot, "use_proxy");
  if (useProxyInput) {
    useProxyInput.checked = Boolean(data.use_proxy);
  }
  if ((data.provider || "local") === "local") {
    const displayInput = modelField(slot, "display_name");
    if (displayInput) {
      displayInput.value = LOCAL_MODEL_DISPLAY_NAME;
    }
  }
  if ((data.provider || "") === "none") {
    const displayInput = modelField(slot, "display_name");
    if (displayInput) {
      displayInput.value = "未配置";
    }
  }
  syncModelSlotDisabledState(slot);
}

function syncModelSlotDisabledState(slot) {
  const providerInput = modelField(slot, "provider");
  const provider = providerInput ? providerInput.value : "local";
  const displayInput = modelField(slot, "display_name");
  const baseUrlInput = modelField(slot, "base_url");
  const modelInput = modelField(slot, "model");
  const apiKeyInput = modelField(slot, "api_key");
  const useProxyInput = modelField(slot, "use_proxy");
  const proxyUrlInput = modelField(slot, "proxy_url");
  if (displayInput) {
    displayInput.disabled = provider === "local" || provider === "none";
    if (provider === "local") {
      displayInput.value = LOCAL_MODEL_DISPLAY_NAME;
    } else if (provider === "none") {
      displayInput.value = "未配置";
    }
  }
  if (baseUrlInput) {
    baseUrlInput.disabled = provider === "none";
    if (provider === "none") {
      baseUrlInput.value = "";
    }
  }
  if (modelInput) {
    modelInput.disabled = provider === "none";
    if (provider === "none") {
      modelInput.value = "";
    }
  }
  if (apiKeyInput) {
    apiKeyInput.disabled = isProxylessProvider(provider);
  }
  if (useProxyInput) {
    useProxyInput.disabled = isProxylessProvider(provider);
    if (isProxylessProvider(provider)) {
      useProxyInput.checked = false;
    }
  }
  if (proxyUrlInput) {
    proxyUrlInput.disabled = isProxylessProvider(provider);
    if (isProxylessProvider(provider)) {
      proxyUrlInput.value = "";
    } else if (!proxyUrlInput.value.trim()) {
      proxyUrlInput.value = currentWebSearchProxy();
    }
  }
}

function readModelSlot(slot) {
  const provider = modelField(slot, "provider")?.value || "local";
  const isLocalLike = isProxylessProvider(provider);
  const proxyUrl = isLocalLike ? "" : ((modelField(slot, "proxy_url")?.value || "").trim() || currentWebSearchProxy());
  const payload = {
    provider,
    display_name: provider === "local" ? LOCAL_MODEL_DISPLAY_NAME : (modelField(slot, "display_name")?.value || ""),
    base_url: modelField(slot, "base_url")?.value || "",
    model: modelField(slot, "model")?.value || "",
    use_proxy: !isLocalLike && (Boolean(modelField(slot, "use_proxy")?.checked) || Boolean(proxyUrl)),
    proxy_url: proxyUrl,
  };
  if (provider === "none") {
    payload.display_name = "未配置";
    payload.base_url = "";
    payload.model = "";
  }
  const apiKey = modelField(slot, "api_key")?.value || "";
  if (apiKey.trim()) {
    payload.api_key = apiKey.trim();
  }
  return payload;
}

async function loadModelSettings() {
  const response = await fetch("/api/model-settings", { headers: deviceIdentityHeaders() });
  if (!response.ok) {
    throw new Error("模型配置读取失败");
  }
  modelSettingsState = await response.json();
  if (typeof modelSettingsState.web_search_proxy === "string") {
    saveSamplingSettings({
      ...samplingSettings,
      web_search_proxy: modelSettingsState.web_search_proxy,
    });
  }
  setModelDisplayName(modelSettingsState);
  return modelSettingsState;
}

function setLocalModelServiceStatus(text, state = "") {
  if (localModelServiceStatus) {
    localModelServiceStatus.textContent = text || "";
  }
  if (localModelServiceButton) {
    localModelServiceButton.dataset.state = state;
  }
}

function localModelServiceSummary(payload) {
  if (!payload || typeof payload !== "object") {
    return "状态未知";
  }
  if (payload.summary) {
    return String(payload.summary);
  }
  const model = payload.model || {};
  const embedding = payload.embedding || {};
  const image = payload.image || {};
  if (model.running && embedding.running && image.running) {
    return `已运行：本地模型 ${model.port || "?"} / Embedding ${embedding.port || "?"} / 画图 ${image.port || "?"}`;
  }
  if (model.running && embedding.running) {
    return `已运行：本地模型 ${model.port || "?"} / Embedding ${embedding.port || "?"} / 画图未就绪`;
  }
  return "未启动";
}

async function loadLocalModelServiceStatus(configure = false) {
  if (!localModelServiceButton) {
    return null;
  }
  try {
    const url = configure ? "/api/local-model-service/status?configure=1" : "/api/local-model-service/status";
    const response = await fetch(url, { headers: deviceIdentityHeaders() });
    if (!response.ok) {
      throw new Error("状态检测失败");
    }
    const payload = await response.json();
    const ready = Boolean(payload.model && payload.model.running && payload.embedding && payload.embedding.running);
    setLocalModelServiceStatus(localModelServiceSummary(payload), ready ? "ready" : "missing");
    if (ready) {
      window.clearTimeout(localModelServicePollTimer);
    }
    if (payload.settings_updated) {
      await loadModelSettings();
    }
    return payload;
  } catch (error) {
    setLocalModelServiceStatus(error.message || "检测失败", "error");
    return null;
  }
}

function pollLocalModelServiceUntilReady(remaining = 60) {
  window.clearTimeout(localModelServicePollTimer);
  if (!localModelServiceButton || remaining <= 0) {
    return;
  }
  localModelServicePollTimer = window.setTimeout(async () => {
    const payload = await loadLocalModelServiceStatus(true);
    const ready = Boolean(payload && payload.model && payload.model.running && payload.embedding && payload.embedding.running);
    if (!ready) {
      setLocalModelServiceStatus("启动中，等待服务就绪", "starting");
      pollLocalModelServiceUntilReady(remaining - 1);
    }
  }, 5000);
}

async function startLocalModelService() {
  if (!localModelServiceButton) {
    return;
  }
  localModelServiceButton.disabled = true;
  setLocalModelServiceStatus("启动中", "starting");
  try {
    const response = await fetch("/api/local-model-service/start", {
      method: "POST",
      headers: jsonHeaders(),
    });
    if (!response.ok) {
      throw new Error("启动请求失败");
    }
    const payload = await response.json();
    if (payload.error) {
      throw new Error(payload.error);
    }
    const ready = Boolean(payload.model && payload.model.running && payload.embedding && payload.embedding.running);
    setLocalModelServiceStatus(localModelServiceSummary(payload), ready ? "ready" : "starting");
    if (payload.settings_updated) {
      await loadModelSettings();
    }
    if (!ready) {
      pollLocalModelServiceUntilReady();
    }
  } catch (error) {
    setLocalModelServiceStatus(error.message || "启动失败", "error");
  } finally {
    localModelServiceButton.disabled = false;
  }
}

async function openModelSettingsDialog() {
  if (!modelSettingsDialog) {
    return;
  }
  modelSettingsStatus.textContent = "读取中";
  try {
    const settings = await loadModelSettings();
    populateModelSlot("chat", settings);
    populateModelSlot("background", settings);
    populateModelSlot("image", settings);
    modelSettingsStatus.textContent = "";
    if (typeof modelSettingsDialog.showModal === "function") {
      modelSettingsDialog.showModal();
    } else {
      modelSettingsDialog.setAttribute("open", "");
    }
  } catch (error) {
    modelSettingsStatus.textContent = error.message || "模型配置读取失败";
  }
}

function closeModelSettingsDialog() {
  if (!modelSettingsDialog) {
    return;
  }
  modelSettingsDialog.close();
}

async function saveModelSettings(event) {
  event.preventDefault();
  modelSettingsStatus.textContent = "保存中";
  try {
    const response = await fetch("/api/model-settings", {
      method: "PUT",
      headers: jsonHeaders(),
      body: JSON.stringify({
        chat: readModelSlot("chat"),
        background: readModelSlot("background"),
        image: readModelSlot("image"),
        web_search_proxy: currentWebSearchProxy(),
      }),
    });
    if (!response.ok) {
      throw new Error("保存失败");
    }
    modelSettingsState = await response.json();
    setModelDisplayName(modelSettingsState);
    modelSettingsStatus.textContent = "已保存";
    closeModelSettingsDialog();
    setStatus(`模型已更新：${modelSettingsState.chat.provider === "local" ? LOCAL_MODEL_DISPLAY_NAME : (modelSettingsState.chat.model || modelSettingsState.chat.display_name || "AI模型")}`);
  } catch (error) {
    modelSettingsStatus.textContent = error.message || "保存失败";
  }
}

async function syncModelProxySettingToServer() {
  try {
    const settings = modelSettingsState || await loadModelSettings();
    const response = await fetch("/api/model-settings", {
      method: "PUT",
      headers: jsonHeaders(),
      body: JSON.stringify({
        chat: settings.chat || readModelSlot("chat"),
        background: settings.background || readModelSlot("background"),
        image: settings.image || readModelSlot("image"),
        web_search_proxy: currentWebSearchProxy(),
      }),
    });
    if (response.ok) {
      modelSettingsState = await response.json();
      setModelDisplayName(modelSettingsState);
    }
  } catch (_error) {
    // Proxy sync is best-effort; chat requests still carry the current proxy.
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
  if (binding.inherit_assistant_profile) {
    parts.push("继承助手设定");
  } else if (binding.profile_owner_device_id) {
    parts.push("继承其他设备设定");
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
    const raw = readMigratedStorage(USER_MEMORY_BINDING_STORAGE_KEY, LEGACY_USER_MEMORY_BINDING_STORAGE_KEY);
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
    inherit_assistant_profile: Boolean(payload.inherit_assistant_profile),
    profile_owner_device_id: String(payload.profile_owner_device_id || ""),
  };
  if (userMemoryBindingLabel) {
    userMemoryBindingLabel.textContent = userMemoryBindingState.shared_user_id ? "已绑定" : "记忆绑定";
  }
  if (userMemoryBindingSummary) {
    userMemoryBindingSummary.textContent = bindingSummaryText(userMemoryBindingState);
  }
  if (userMemoryBindingCrown) {
    userMemoryBindingCrown.hidden = !userMemoryBindingState.is_host;
  }
  if (userMemoryBindingButton) {
    userMemoryBindingButton.classList.toggle("is-host", userMemoryBindingState.is_host);
  }
  if (shouldPublish) {
    publishUserMemoryBindingState();
  }
}

function syncUserMemoryBindingForm() {
  if (!userMemoryBindingInput) {
    return;
  }
  const binding = userMemoryBindingState || {};
  userMemoryBindingInput.value = String(binding.shared_user_id || "");
  shareChatHistoryCheckbox.checked = Boolean(binding.share_chat_history);
  hostDeviceCheckbox.checked = Boolean(binding.is_host);
  inheritAssistantProfileCheckbox.checked = Boolean(binding.inherit_assistant_profile);
}

function setUserMemoryBindingInfoVisible(visible) {
  if (!userMemoryBindingInfo) {
    return;
  }
  userMemoryBindingInfo.hidden = !visible;
  if (userMemoryBindingInfoButton) {
    userMemoryBindingInfoButton.setAttribute("aria-expanded", visible ? "true" : "false");
  }
}

function hasLargeAttachment(attachments) {
  return (attachments || []).some((attachment) => Number(attachment.size || 0) > IMAGE_COMPRESSION_NOTICE_BYTES);
}

function readMigratedStorage(currentKey, legacyKey) {
  try {
    const current = localStorage.getItem(currentKey);
    if (current) {
      return current;
    }
    const legacy = legacyKey ? localStorage.getItem(legacyKey) : "";
    if (legacy) {
      localStorage.setItem(currentKey, legacy);
      localStorage.removeItem(legacyKey);
      return legacy;
    }
  } catch (_) {
    return "";
  }
  return "";
}

function openingPromptStorageKey() {
  return `${OPENING_PROMPT_STORAGE_KEY}:${ensureDeviceId()}`;
}

function storeCachedOpeningPrompt(prompt) {
  const text = String(prompt || "").trim();
  if (!text) {
    return;
  }
  try {
    localStorage.setItem(openingPromptStorageKey(), text);
  } catch (_) {
    // localStorage can be unavailable in strict private contexts.
  }
}

function readCachedOpeningPrompt() {
  try {
    return String(localStorage.getItem(openingPromptStorageKey()) || "").trim();
  } catch (_) {
    return "";
  }
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
  return { "X-Wangcai-Device-Id": ensureDeviceId() };
}

function jsonHeaders() {
  return { "Content-Type": "application/json", ...deviceIdentityHeaders() };
}

function setSendButtonGenerating(generating) {
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

function setBusy(busy) {
  setSendButtonGenerating(Boolean(busy && activeController));
  sendButton.disabled = isResetting && !activeController;
  resetButton.disabled = isResetting;
  messageInput.disabled = busy || isResetting;
  temperatureRange.disabled = busy || isResetting;
  topPRange.disabled = busy || isResetting;
  webSearchProxyInput.disabled = busy || isResetting;
  confirmSamplingButton.disabled = busy || isResetting;
  attachImageButton.disabled = busy || isResetting;
  webSearchButton.disabled = busy || isResetting;
  if (drawButton) {
    drawButton.disabled = busy || isResetting;
  }
}

function setWebSearchEnabled(enabled) {
  webSearchEnabled = Boolean(enabled);
  webSearchButton.classList.toggle("is-active", webSearchEnabled);
  webSearchButton.setAttribute("aria-pressed", String(webSearchEnabled));
  webSearchButton.title = webSearchEnabled ? "本轮会联网搜索" : "启用联网搜索";
}

function setDrawEnabled(enabled) {
  drawEnabled = Boolean(enabled);
  if (!drawButton) {
    return;
  }
  drawButton.classList.toggle("is-active", drawEnabled);
  drawButton.setAttribute("aria-pressed", String(drawEnabled));
  drawButton.title = drawEnabled ? "本轮发送会画图" : "启用画图";
  if (drawEnabled && webSearchEnabled) {
    setWebSearchEnabled(false);
  }
}

function clearDrawModeSelection() {
  setDrawEnabled(false);
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

function formatSamplingValue(value) {
  return value.toFixed(2);
}

function loadSamplingSettings() {
  try {
    const raw = readMigratedStorage(SAMPLING_STORAGE_KEY, LEGACY_SAMPLING_STORAGE_KEY);
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
  if (typeof advancedOptions.showModal === "function") {
    advancedOptions.showModal();
  } else {
    advancedOptions.setAttribute("open", "");
  }
  advancedOptions.classList.add("is-visible");
  loadLocalModelServiceStatus();
  temperatureRange.focus();
}

function closeAdvancedOptions() {
  advancedOptions.classList.remove("is-visible");
  if (typeof advancedOptions.close === "function") {
    advancedOptions.close();
  } else {
    advancedOptions.removeAttribute("open");
  }
}

function hideAdvancedOptions() {
  closeAdvancedOptions();
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

function isNearMessagesTop() {
  return messagesEl.scrollTop <= PREVIOUS_SESSION_DESKTOP_TOP_BUFFER;
}

function removeHistoryLoadIndicator(animated = false) {
  const current = messagesEl.querySelector(".history-load");
  if (!current) {
    return;
  }
  window.clearTimeout(previousSessionHideTimer);
  previousSessionHideTimer = 0;
  if (!animated) {
    current.className = "history-load is-idle";
    current.textContent = "加载上一段对话";
    return;
  }
  current.classList.add("is-hiding");
  window.setTimeout(() => {
    current.className = "history-load is-idle";
    current.textContent = "加载上一段对话";
  }, 500);
}

function setHistoryLoadState(state, text) {
  if (!text) {
    return;
  }
  const indicator = ensureHistoryLoadIndicator();
  indicator.replaceChildren();
  indicator.className = `history-load is-${state}`;
  if (state === "loading") {
    const spinner = document.createElement("span");
    spinner.className = "history-load-spinner";
    spinner.setAttribute("aria-hidden", "true");
    const label = document.createElement("span");
    label.textContent = text;
    indicator.append(spinner, label);
  } else {
    indicator.textContent = text;
  }
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

const MESSAGE_COPY_ICON = `
  <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <rect x="8" y="8" width="12" height="12" rx="2.5" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"></rect>
    <path d="M4 15.5V6.5A2.5 2.5 0 0 1 6.5 4h9" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"></path>
  </svg>
`;

const MESSAGE_COPY_DONE_ICON = `
  <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <path d="M5 12.5l4.2 4.2L19 7" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"></path>
  </svg>
`;

const MESSAGE_QUOTE_ICON = `
  <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"></circle>
    <path d="M9.2 9.2c-1.1.9-1.7 1.9-1.7 3.2v2.2h3.4v-3.2H9.2c.1-.7.6-1.3 1.4-1.9L9.2 9.2Z" fill="currentColor"></path>
    <path d="M15.2 9.2c-1.1.9-1.7 1.9-1.7 3.2v2.2h3.4v-3.2h-1.7c.1-.7.6-1.3 1.4-1.9L15.2 9.2Z" fill="currentColor"></path>
  </svg>
`;

function setMessageCopyButtonState(button, copied = false) {
  button.innerHTML = copied ? MESSAGE_COPY_DONE_ICON : MESSAGE_COPY_ICON;
  button.classList.toggle("is-copied", copied);
  button.setAttribute("aria-label", copied ? "已复制" : "复制消息");
  button.title = copied ? "已复制" : "复制消息";
}

function fallbackCopyText(text) {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  textarea.style.top = "0";
  document.body.appendChild(textarea);
  textarea.select();
  textarea.setSelectionRange(0, textarea.value.length);
  try {
    return document.execCommand("copy");
  } finally {
    textarea.remove();
  }
}

async function copyTextToClipboard(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return true;
  }
  return fallbackCopyText(text);
}

function truncateQuotePreview(text) {
  const normalized = String(text || "").replace(/\s+/g, " ").trim();
  return normalized.length > 180 ? `${normalized.slice(0, 180)}...` : normalized;
}

function trimQuoteForRequest(text) {
  const normalized = String(text || "").trim();
  return normalized.length > 6000 ? `${normalized.slice(0, 6000)}\n[引用内容过长，已截断]` : normalized;
}

function nodeInsideElement(node, element) {
  if (!node || !element) {
    return false;
  }
  return element.contains(node.nodeType === Node.TEXT_NODE ? node.parentNode : node);
}

function selectedTextInsideElement(element) {
  const selection = window.getSelection ? window.getSelection() : null;
  if (!selection || selection.isCollapsed) {
    return "";
  }
  if (!nodeInsideElement(selection.anchorNode, element) || !nodeInsideElement(selection.focusNode, element)) {
    return "";
  }
  return selection.toString().trim();
}

function clearPendingQuote() {
  pendingQuotedMessage = "";
  if (quotePreview) {
    quotePreview.hidden = true;
  }
  if (quotePreviewText) {
    quotePreviewText.textContent = "";
  }
}

function setPendingQuote(text) {
  const quote = trimQuoteForRequest(text);
  if (!quote) {
    setStatus("没有可引用内容");
    return;
  }
  pendingQuotedMessage = quote;
  if (quotePreview && quotePreviewText) {
    quotePreviewText.textContent = truncateQuotePreview(quote);
    quotePreview.hidden = false;
  }
  setStatus("已引用，下一条消息会优先参考这段内容");
  messageInput.focus();
}

function createMessageActions(body) {
  const actions = document.createElement("div");
  actions.className = "message-actions";

  const copyButton = document.createElement("button");
  copyButton.type = "button";
  copyButton.className = "message-action-button message-copy-button";
  setMessageCopyButtonState(copyButton, false);
  copyButton.addEventListener("click", async () => {
    const text = getRawMarkdown(body).trim();
    if (!text) {
      setStatus("没有可复制内容");
      return;
    }
    try {
      const copied = await copyTextToClipboard(text);
      if (!copied) {
        throw new Error("copy command failed");
      }
      setMessageCopyButtonState(copyButton, true);
      window.setTimeout(() => setMessageCopyButtonState(copyButton, false), 1200);
    } catch (_) {
      copyButton.title = "复制失败";
      setStatus("复制失败");
    }
  });
  actions.append(copyButton);

  const quoteButton = document.createElement("button");
  quoteButton.type = "button";
  quoteButton.className = "message-action-button message-quote-button";
  quoteButton.innerHTML = MESSAGE_QUOTE_ICON;
  quoteButton.setAttribute("aria-label", "引用消息");
  quoteButton.title = "引用消息";
  quoteButton.addEventListener("click", () => {
    const selected = selectedTextInsideElement(body);
    const text = selected || getRawMarkdown(body).trim();
    setPendingQuote(text);
    quoteButton.classList.add("is-active");
    window.setTimeout(() => quoteButton.classList.remove("is-active"), 900);
  });
  actions.append(quoteButton);
  return actions;
}

function createBubble(role, content = "", attachments = [], options = {}) {
  const item = document.createElement("article");
  item.className = `message ${role}`;

  const label = document.createElement("div");
  label.className = "message-label";
  label.textContent = role === "user" ? "你" : "助手";

  const body = document.createElement("div");
  body.className = "message-body";
  const timestamp = document.createElement("div");
  timestamp.className = "message-timestamp";
  timestamp.textContent = formatMessageTimestamp(options.createdAt);
  const meta = document.createElement("div");
  meta.className = "message-meta";
  meta.append(label, timestamp);
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

  item.append(meta, body);
  if (role === "assistant" || role === "user") {
    item.append(createMessageActions(body));
  }
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

function renderGeneratedImageBatch(images, optimizedPrompt = "") {
  const wrapper = document.createElement("div");
  wrapper.className = "generated-image-batch";
  const grid = document.createElement("div");
  grid.className = "generated-image-grid";
  const items = Array.isArray(images) ? images : [];
  for (const [index, item] of items.entries()) {
    const url = item && item.public_url ? String(item.public_url) : "";
    if (!url) {
      continue;
    }
    const cell = document.createElement("figure");
    cell.className = "generated-image-item";
    const image = document.createElement("img");
    image.src = url;
    image.alt = item.short_caption || `生成图片 ${index + 1}`;
    const download = document.createElement("a");
    download.className = "generated-image-download";
    download.href = url;
    download.download = `wangcai-draw-${index + 1}`;
    download.textContent = "下载";
    cell.append(image, download);
    grid.appendChild(cell);
  }
  wrapper.appendChild(grid);
  if (optimizedPrompt) {
    const details = document.createElement("details");
    details.className = "generated-image-prompt";
    const summary = document.createElement("summary");
    summary.textContent = "优化后的 prompt";
    const pre = document.createElement("pre");
    pre.textContent = optimizedPrompt;
    details.append(summary, pre);
    wrapper.appendChild(details);
  }
  return wrapper;
}

function messageAttachments(message) {
  return Array.isArray(message && message.attachments)
    ? message.attachments.filter((item) => item && typeof item === "object")
    : [];
}

function messageDrawMetadata(message) {
  return message && message.draw && typeof message.draw === "object" ? message.draw : {};
}

function restoreHistoricalAssistantMedia(body, message) {
  const draw = messageDrawMetadata(message);
  const images = Array.isArray(draw.images) ? draw.images : [];
  if (!images.length) {
    return;
  }
  body.replaceChildren();
  body.appendChild(renderGeneratedImageBatch(images, draw.optimized_prompt || ""));
  body.dataset.rawMarkdown = message.content || `已生成 ${images.length} 张图片。`;
}

function clearMessages() {
  messagesEl.replaceChildren();
  ensureHistoryLoadIndicator();
}

function resetPreviousSessionLoadState() {
  previousSessionArmedAt = 0;
  window.clearTimeout(previousSessionHideTimer);
  previousSessionHideTimer = 0;
  isLoadingPreviousSession = false;
  hasMorePreviousSessions = true;
  removeHistoryLoadIndicator();
}

function cancelPreviousSessionPreparation() {
  if (!previousSessionArmedAt) {
    return;
  }
  previousSessionArmedAt = 0;
  removeHistoryLoadIndicator(true);
}

function ensureHistoryLoadIndicator() {
  let indicator = messagesEl.querySelector(".history-load");
  if (!indicator) {
    indicator = document.createElement("div");
    indicator.className = "history-load is-idle";
    indicator.textContent = "加载上一段对话";
    messagesEl.prepend(indicator);
  }
  return indicator;
}

function enterPreviousSessionArmed() {
  if (activeController || isLoadingPreviousSession || !hasMorePreviousSessions || !sessionId || previousSessionArmedAt) {
    return;
  }
  window.clearTimeout(previousSessionHideTimer);
  previousSessionHideTimer = 0;
  previousSessionArmedAt = Date.now();
  setHistoryLoadState("armed", "加载上一段对话");
  previousSessionHideTimer = window.setTimeout(() => {
    if (Date.now() - previousSessionArmedAt >= PREVIOUS_SESSION_ARM_MS && !isLoadingPreviousSession) {
      previousSessionArmedAt = 0;
      removeHistoryLoadIndicator(true);
    }
  }, PREVIOUS_SESSION_ARM_MS);
}

function handleMessagesScroll() {
  if (isAtMessagesTop() && touchHistoryArmOnTop && wasTouchScrollingTowardTop && !touchHistoryGestureFired) {
    touchHistoryGestureFired = true;
    touchHistoryArmOnTop = false;
    window.clearTimeout(touchHistoryClearTimer);
    touchHistoryClearTimer = 0;
    armOrLoadPreviousSession();
    return;
  }
  if (!isAtMessagesTop()) {
    cancelPreviousSessionPreparation();
  }
}

function scheduleTouchHistoryStateClear() {
  window.clearTimeout(touchHistoryClearTimer);
  touchHistoryClearTimer = window.setTimeout(() => {
    wasTouchScrollingTowardTop = false;
    touchHistoryArmOnTop = false;
    touchHistoryClearTimer = 0;
  }, TOUCH_TOP_INERTIA_WINDOW_MS);
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

  const maxTop = Math.max(0, messagesEl.scrollHeight - messagesEl.clientHeight);
  const safePreservedTop = Math.max(0, Math.min(maxTop, preservedTop));
  messagesEl.scrollTop = safePreservedTop;
  const targetTop = Math.max(0, Math.min(safePreservedTop, lastItem.offsetTop - HISTORY_REVEAL_GAP_PX));
  animateHistoryScrollTo(targetTop);
}

function prependHistoryMessages(messages) {
  const history = Array.isArray(messages) ? messages : [];
  if (!history.length) {
    return;
  }

  const indicator = messagesEl.querySelector(".history-load");
  if (indicator) {
    indicator.remove();
  }
  const previousHeight = messagesEl.scrollHeight;
  const previousTop = messagesEl.scrollTop;
  const loadedMessageItems = [];
  for (const message of [...history].reverse()) {
    const role = message.role === "assistant" ? "assistant" : "user";
    const body = createBubble(role, message.content || "", messageAttachments(message), {
      prepend: true,
      scroll: false,
      createdAt: message.created_at,
    });
    if (role === "assistant") {
      restoreHistoricalAssistantMedia(body, message);
    }
    loadedMessageItems.unshift(body.parentElement);
  }
  ensureHistoryLoadIndicator();
  const preservedTop = messagesEl.scrollHeight - previousHeight + previousTop;
  revealLastLoadedHistoryMessage(loadedMessageItems.at(-1), preservedTop);
}

async function loadPreviousSessionContext() {
  if (!sessionId || activeController || isLoadingPreviousSession || !hasMorePreviousSessions) {
    return;
  }

  isLoadingPreviousSession = true;
  setHistoryLoadState("loading", "加载上一段对话");
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
  if (!isAtMessagesTop()) {
    cancelPreviousSessionPreparation();
    return;
  }

  const now = Date.now();
  if (!previousSessionArmedAt) {
    enterPreviousSessionArmed();
    return;
  }

  const elapsed = now - previousSessionArmedAt;
  if (elapsed < PREVIOUS_SESSION_MIN_RETRY_MS) {
    setHistoryLoadState("waiting", "加载上一段对话");
    return;
  }
  if (elapsed <= PREVIOUS_SESSION_ARM_MS) {
    previousSessionArmedAt = 0;
    loadPreviousSessionContext();
    return;
  }

  enterPreviousSessionArmed();
}

function handleDesktopPreviousSessionWheel(event) {
  if (event.deltaY >= -24 || !isNearMessagesTop()) {
    return;
  }
  event.preventDefault();
  messagesEl.scrollTop = 0;
  armOrLoadPreviousSession();
}

function handleMobilePreviousSessionPull(event) {
  if (event.touches.length !== 1) {
    return;
  }
  touchPullDistance = event.touches[0].clientY - touchStartY;
  wasTouchScrollingTowardTop = touchPullDistance > 0;
  if (touchPullDistance <= 0) {
    return;
  }
  touchHistoryArmOnTop = true;
  if (!isNearMessagesTop()) {
    return;
  }
  event.preventDefault();
  if (touchPullDistance > 8 && !touchHistoryGestureFired) {
    touchHistoryGestureFired = true;
    messagesEl.scrollTop = 0;
    armOrLoadPreviousSession();
    touchStartY = event.touches[0].clientY;
    touchPullDistance = 0;
  }
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

async function startOpeningPrompt(payload, openingPrompt = true, openingTiming = null) {
  if (!openingPrompt || !sessionId || activeController) {
    return;
  }
  const prompt = String(payload && payload.opening_prompt ? payload.opening_prompt : "").trim();
  if (!prompt) {
    return;
  }
  const clientTiming = openingTiming ? {
    session_fetch_ms: Number(openingTiming.sessionFetchMs || 0),
    session_json_ms: Number(openingTiming.sessionJsonMs || 0),
    session_to_opening_send_ms: Number(performance.now() - openingTiming.sessionStartMs),
    opening_prompt_chars: prompt.length,
  } : {};
  openingGenerationActive = true;
  try {
    await sendMessage(prompt, [], false, {
      hiddenUser: true,
      showUser: false,
      maxTokens: 512,
      cachedOpening: true,
      clientTiming,
    });
  } finally {
    openingGenerationActive = false;
  }
}

async function startFastOpeningPrompt(openingPrompt) {
  const prompt = String(openingPrompt || "").trim();
  if (!prompt || activeController) {
    return false;
  }
  activeOpeningId = crypto.randomUUID
    ? crypto.randomUUID().replace(/-/g, "")
    : `opening_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 12)}`;
  openingGenerationActive = true;
  userStoppedGeneration = false;
  activeController = new AbortController();
  const assistantBody = createBubble("assistant", "");
  activeAssistantBody = assistantBody;
  setBusy(true);
  setStatus("开场生成中");

  try {
    const response = await fetch("/api/opening/stream", {
      method: "POST",
      headers: jsonHeaders(),
      signal: activeController.signal,
      body: JSON.stringify({
        opening_id: activeOpeningId,
        opening_prompt: prompt,
        cached_opening: true,
        max_tokens: 512,
        ...getSamplingSettings(),
      }),
    });
    if (!response.ok || !response.body) {
      throw new Error(await response.text());
    }
    await consumeSse(response, {
      token: (payload) => {
        setRenderedMarkdown(assistantBody, getRawMarkdown(assistantBody) + (payload.content || ""));
        scrollToBottom();
      },
      done: (payload) => {
        if (payload && payload.content && !getRawMarkdown(assistantBody).trim()) {
          setRenderedMarkdown(assistantBody, payload.content);
        }
        setStatus("就绪");
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
        return true;
      },
      error: (payload) => {
        setRenderedMarkdown(assistantBody, payload.message || "模型服务调用失败");
        assistantBody.parentElement.classList.add("error");
        setStatus("错误");
        return true;
      },
    });
    return true;
  } catch (error) {
    if (error.name === "AbortError" && userStoppedGeneration) {
      setStatus("已停止");
    } else if (error.name !== "AbortError") {
      setRenderedMarkdown(assistantBody, `请求失败：${error.message}`);
      assistantBody.parentElement.classList.add("error");
      setStatus("错误");
    }
    return false;
  } finally {
    activeController = null;
    activeAssistantBody = null;
    activeOpeningId = "";
    openingGenerationActive = false;
    userStoppedGeneration = false;
    setBusy(false);
    messageInput.focus();
  }
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
  const { openingPrompt = true, clearExisting = true } = options;
  const sessionStartMs = performance.now();
  const response = await fetch("/api/sessions", {
    method: "POST",
    headers: deviceIdentityHeaders(),
  });
  const responseMs = performance.now();
  if (!response.ok) {
    throw new Error(await response.text());
  }
  const payload = await response.json();
  const jsonMs = performance.now();
  sessionId = payload.session_id;
  if (payload.memory_binding) {
    applyUserMemoryBindingState(payload.memory_binding);
  }
  storeCachedOpeningPrompt(payload.opening_prompt);
  if (clearExisting) {
    resetPreviousSessionLoadState();
    clearMessages();
    clearPendingAttachments();
  }
  setStatus("就绪");
  await startOpeningPrompt(payload, openingPrompt, {
    sessionStartMs,
    sessionFetchMs: responseMs - sessionStartMs,
    sessionJsonMs: jsonMs - responseMs,
  });
}

function closeCurrentSession() {
  if (!sessionId) {
    return;
  }
  const deviceIdQuery = `?device_id=${encodeURIComponent(ensureDeviceId())}`;
  const closePath = `/api/sessions/${sessionId}/close${deviceIdQuery}`;
  if (navigator.sendBeacon) {
    navigator.sendBeacon(closePath, new Blob([], { type: "application/json" }));
    return;
  }
  fetch(closePath, {
    method: "POST",
    headers: deviceIdentityHeaders(),
    keepalive: true,
  }).catch(() => {});
}

function handlePageHide() {
  if (activeOpeningId) {
    const cancelPath = `/api/opening/cancel/${activeOpeningId}?device_id=${encodeURIComponent(ensureDeviceId())}`;
    if (navigator.sendBeacon) {
      navigator.sendBeacon(cancelPath, new Blob([], { type: "application/json" }));
    } else {
      fetch(cancelPath, {
        method: "POST",
        headers: deviceIdentityHeaders(),
        keepalive: true,
      }).catch(() => {});
    }
  }
  closeCurrentSession();
}

async function stopActiveGeneration() {
  if (!activeController) {
    return;
  }
  userStoppedGeneration = true;
  sendButton.disabled = true;
  try {
    if (activeOpeningId) {
      await fetch(`/api/opening/cancel/${activeOpeningId}`, {
        method: "POST",
        headers: deviceIdentityHeaders(),
        keepalive: true,
      });
    } else if (sessionId) {
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
  clearDrawModeSelection();

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
    if (payload.memory_binding) {
      applyUserMemoryBindingState(payload.memory_binding);
    }
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
    drawMode = false,
  } = options;
  if (showUser) {
    createBubble("user", text, attachments);
  }
  const assistantBody = createBubble("assistant", openingPlaceholder);
  let hasReceivedToken = false;
  activeAssistantBody = assistantBody;
  userStoppedGeneration = false;
  activeController = new AbortController();
  setBusy(true);
  clearSearchActivity();
  const largeAttachment = hasLargeAttachment(attachments);
  setStatus(largeAttachment ? "图片过大，狠狠压缩中..." : (drawMode ? "画图 prompt 优化中" : (options.cachedOpening ? "开场生成中" : (webSearch ? "联网搜索中" : "生成中"))));

  try {
    const response = await fetch("/api/chat/stream", {
      method: "POST",
      headers: jsonHeaders(),
      signal: activeController.signal,
      body: JSON.stringify({
        session_id: sessionId,
        message: text,
        quoted_message: options.quotedMessage || "",
        mode: drawMode ? "draw" : "chat",
        attachments,
        hidden_user: hiddenUser,
        cached_opening: Boolean(options.cachedOpening),
        client_timing: options.clientTiming || {},
        web_search: drawMode ? false : webSearch,
        web_search_proxy: samplingSettings.web_search_proxy,
        max_tokens: maxTokens,
        ...getSamplingSettings(),
      }),
    });

    if (response.status === 429) {
      const detail = await parseRateLimitPayload(response);
      removeEmptyAssistantBubble(assistantBody);
      setStatus((detail && detail.message) || "发送太快了，请稍后再试");
      clearSearchActivity();
      return;
    }
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
      draw_status: (payload) => {
        setSearchActivity(payload.message || "画图中");
        setStatus(payload.message || "画图中");
      },
      draw_prompt: (payload) => {
        setSearchActivity("画图 prompt 已优化");
        setStatus("HiDream 生成中");
        if (payload.optimized_prompt) {
          setRenderedMarkdown(assistantBody, "画图 prompt 已优化，正在生成图片。");
        }
      },
      draw_image_batch: (payload) => {
        const images = Array.isArray(payload.images) ? payload.images : [];
        assistantBody.replaceChildren();
        assistantBody.appendChild(renderGeneratedImageBatch(images, payload.optimized_prompt || ""));
        assistantBody.dataset.rawMarkdown = `已生成 ${images.length} 张图片。`;
        setSearchActivity(`图片已生成：${images.length} 张`);
        setStatus("图片已生成");
        scrollToBottom();
      },
      draw_error: (payload) => {
        setRenderedMarkdown(assistantBody, payload.message || "图片生成失败");
        assistantBody.parentElement.classList.add("error");
        setStatus("图片生成失败");
        return true;
      },
      token: (payload) => {
        if (!hasReceivedToken && openingPlaceholder) {
          setRenderedMarkdown(assistantBody, "");
        }
        hasReceivedToken = true;
        setRenderedMarkdown(assistantBody, getRawMarkdown(assistantBody) + (payload.content || ""));
        scrollToBottom();
      },
      done: (payload) => {
        if (payload && payload.skipped_empty && !hasReceivedToken) {
          removeEmptyAssistantBubble(assistantBody);
        } else if (payload && payload.content && !hasReceivedToken && !getRawMarkdown(assistantBody).trim()) {
          hasReceivedToken = true;
          setRenderedMarkdown(assistantBody, payload.content);
        }
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

function openMemoryAdminPage() {
  window.location.href = "/memory-admin";
}

function openUserMemoryPage() {
  window.location.href = "/memory";
}

function handleMemoryAdminLongPressStart() {
  memoryAdminLongPressTriggered = false;
  window.clearTimeout(memoryAdminLongPressTimer);
  memoryAdminLongPressTimer = window.setTimeout(() => {
    memoryAdminLongPressTriggered = true;
    window.location.href = "/memory-admin";
  }, WARN_LONG_PRESS_MS);
}

function clearMemoryAdminLongPress() {
  window.clearTimeout(memoryAdminLongPressTimer);
  memoryAdminLongPressTimer = 0;
}

function handleBunnyWarnLongPressStart() {
  warnLongPressTriggered = false;
  window.clearTimeout(warnLongPressTimer);
  warnLongPressTimer = window.setTimeout(() => {
    warnLongPressTriggered = true;
    window.location.href = "/warn";
  }, WARN_LONG_PRESS_MS);
}

function clearBunnyWarnLongPress() {
  window.clearTimeout(warnLongPressTimer);
  warnLongPressTimer = 0;
}

function closeMemoryAdminDialog() {
  memoryAdminDialog.close();
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
    if (userMemoryBindingSummary) {
      userMemoryBindingSummary.textContent = `绑定读取失败：${error.message}`;
    }
  }
}

function openUserMemoryBindingDialog() {
  if (!userMemoryBindingDialog) {
    return;
  }
  userMemoryBindingStatus.textContent = "";
  syncUserMemoryBindingForm();
  setUserMemoryBindingInfoVisible(false);
  if (typeof userMemoryBindingDialog.showModal === "function") {
    userMemoryBindingDialog.showModal();
  } else {
    userMemoryBindingDialog.setAttribute("open", "");
  }
  userMemoryBindingInput.focus();
  userMemoryBindingInput.select();
}

function closeUserMemoryBindingDialog() {
  if (!userMemoryBindingDialog) {
    return;
  }
  userMemoryBindingDialog.close();
}

async function saveUserMemoryBinding(event) {
  event.preventDefault();
  const sharedUserId = String(userMemoryBindingInput.value || "").trim();
  const payload = {
    shared_user_id: sharedUserId,
    share_chat_history: sharedUserId ? Boolean(shareChatHistoryCheckbox.checked) : false,
    is_host: sharedUserId ? Boolean(hostDeviceCheckbox.checked) : false,
    inherit_assistant_profile: sharedUserId ? Boolean(inheritAssistantProfileCheckbox.checked) : false,
  };
  userMemoryBindingStatus.textContent = "保存中";
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
    userMemoryBindingStatus.textContent = result.shared_user_id ? "已保存共享绑定" : "已关闭共享绑定";
    setStatus(result.shared_user_id ? "共享记忆配置已更新" : "已关闭共享记忆");
    if (result.left_previous_shared_user) {
      window.alert("已退出当前记忆共享。");
    }
    window.setTimeout(() => closeUserMemoryBindingDialog(), 180);
  } catch (error) {
    userMemoryBindingStatus.textContent = `保存失败：${error.message}`;
  }
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
  const useDraw = drawEnabled;
  const useWebSearch = useDraw ? false : webSearchEnabled;
  const quotedMessage = useDraw ? "" : pendingQuotedMessage;
  if ((!text && !attachments.length) || activeController) {
    return;
  }
  if (!text && attachments.length) {
    text = "请描述这张图片。";
  }
  messageInput.value = "";
  clearPendingAttachments();
  clearPendingQuote();
  await sendMessage(text, attachments, useWebSearch, { drawMode: useDraw, quotedMessage });
  setDrawEnabled(drawEnabled);
});

clearQuoteButton?.addEventListener("click", () => {
  clearPendingQuote();
  messageInput.focus();
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

resetButton.addEventListener("click", resetChat);
attachImageButton.addEventListener("click", () => imageInput.click());
webSearchButton.addEventListener("click", () => {
  setWebSearchEnabled(!webSearchEnabled);
  if (webSearchEnabled) {
    setDrawEnabled(false);
  }
  setStatus(webSearchEnabled ? "联网搜索已开启" : "联网搜索已关闭");
  messageInput.focus();
});
if (drawButton) {
  drawButton.addEventListener("click", () => {
    setDrawEnabled(!drawEnabled);
    setStatus(drawEnabled ? "画图已开启" : "画图已关闭");
    messageInput.focus();
  });
}
messagesEl.addEventListener("scroll", handleMessagesScroll, { passive: true });
messagesEl.addEventListener("wheel", handleDesktopPreviousSessionWheel, { passive: false });
messagesEl.addEventListener("touchstart", (event) => {
  if (event.touches.length !== 1) {
    return;
  }
  touchStartY = event.touches[0].clientY;
  touchPullDistance = 0;
  touchHistoryGestureFired = false;
  wasTouchScrollingTowardTop = false;
  touchHistoryArmOnTop = false;
  window.clearTimeout(touchHistoryClearTimer);
  touchHistoryClearTimer = 0;
}, { passive: true });
messagesEl.addEventListener("touchmove", handleMobilePreviousSessionPull, { passive: false });
messagesEl.addEventListener("touchend", scheduleTouchHistoryStateClear, { passive: true });
imageInput.addEventListener("change", async () => {
  try {
    await addImageFiles(imageInput.files || []);
  } catch (error) {
    setStatus(`图片读取失败：${error.message}`);
  } finally {
    imageInput.value = "";
  }
});
userMemoryBindingButton.addEventListener("click", openUserMemoryBindingDialog);
userMemoryBindingForm.addEventListener("submit", saveUserMemoryBinding);
userMemoryBindingCancelButton.addEventListener("click", closeUserMemoryBindingDialog);
userMemoryBindingInput.addEventListener("input", () => {
  const hasValue = Boolean(String(userMemoryBindingInput.value || "").trim());
  if (!hasValue) {
    shareChatHistoryCheckbox.checked = false;
    hostDeviceCheckbox.checked = false;
    inheritAssistantProfileCheckbox.checked = false;
  }
});
userMemoryBindingInfoButton.addEventListener("click", () => {
  setUserMemoryBindingInfoVisible(Boolean(userMemoryBindingInfo.hidden));
});
document.addEventListener("click", (event) => {
  if (!userMemoryBindingInfo || userMemoryBindingInfo.hidden) {
    return;
  }
  const target = event.target;
  if (userMemoryBindingInfoButton.contains(target) || userMemoryBindingInfo.contains(target)) {
    return;
  }
  setUserMemoryBindingInfoVisible(false);
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
window.addEventListener("pageshow", clearDrawModeSelection);
memoryAdminButton.addEventListener("pointerdown", handleMemoryAdminLongPressStart);
memoryAdminButton.addEventListener("pointerup", clearMemoryAdminLongPress);
memoryAdminButton.addEventListener("pointerleave", clearMemoryAdminLongPress);
memoryAdminButton.addEventListener("pointercancel", clearMemoryAdminLongPress);
memoryAdminButton.addEventListener("click", (event) => {
  if (memoryAdminLongPressTriggered) {
    event.preventDefault();
    memoryAdminLongPressTriggered = false;
    return;
  }
  openUserMemoryPage();
});
memoryAdminLoginForm.addEventListener("submit", loginMemoryAdmin);
memoryAdminCancelButton.addEventListener("click", closeMemoryAdminDialog);
window.addEventListener("pagehide", handlePageHide);
bunnyLogoButton.addEventListener("pointerdown", handleBunnyWarnLongPressStart);
bunnyLogoButton.addEventListener("pointerup", clearBunnyWarnLongPress);
bunnyLogoButton.addEventListener("pointerleave", clearBunnyWarnLongPress);
bunnyLogoButton.addEventListener("pointercancel", clearBunnyWarnLongPress);
bunnyLogoButton.addEventListener("click", (event) => {
  if (warnLongPressTriggered) {
    event.preventDefault();
    warnLongPressTriggered = false;
    return;
  }
  handleBunnyLogoClick();
});
temperatureRange.addEventListener("input", updateSamplingSummary);
topPRange.addEventListener("input", updateSamplingSummary);
confirmSamplingButton.addEventListener("click", () => {
  saveSamplingSettings({
    temperature: temperatureRange.value,
    top_p: topPRange.value,
    web_search_proxy: webSearchProxyInput.value,
  });
  syncModelProxySettingToServer();
  closeAdvancedOptions();
  setStatus(`采样已更新：${samplingSummary.textContent}`);
});
if (cancelSamplingButton) {
  cancelSamplingButton.addEventListener("click", closeAdvancedOptions);
}
if (advancedOptions) {
  advancedOptions.addEventListener("click", (event) => {
    if (event.target === advancedOptions) {
      closeAdvancedOptions();
    }
  });
}
if (advancedOptionsForm) {
  advancedOptionsForm.addEventListener("submit", (event) => {
    event.preventDefault();
  });
}
if (openModelSettingsButton) {
  openModelSettingsButton.addEventListener("click", openModelSettingsDialog);
}
if (localModelServiceButton) {
  localModelServiceButton.addEventListener("click", startLocalModelService);
}
if (modelSettingsForm) {
  modelSettingsForm.addEventListener("submit", saveModelSettings);
}
if (modelSettingsCancelButton) {
  modelSettingsCancelButton.addEventListener("click", closeModelSettingsDialog);
}
document.querySelectorAll("[data-model-field=\"provider\"]").forEach((input) => {
  input.addEventListener("change", () => applyProviderPreset(input.dataset.modelSlot));
});
syncSamplingControlsFromSettings();

loadModelSettings().catch(() => {});
loadLocalModelServiceStatus();
loadUserMemoryBinding().catch(() => {});
clearDrawModeSelection();

function bootChatSession() {
  const cachedOpeningPrompt = readCachedOpeningPrompt();
  if (cachedOpeningPrompt) {
    resetPreviousSessionLoadState();
    clearMessages();
    clearPendingAttachments();
    startFastOpeningPrompt(cachedOpeningPrompt).finally(() => {
      createSession({ openingPrompt: false, clearExisting: false }).catch((error) => {
        setStatus("会话准备失败");
        createBubble("assistant", `会话准备失败：${error.message}`);
      });
    });
    return;
  }
  createSession().catch((error) => {
    setStatus("连接失败");
    createBubble("assistant", `连接失败：${error.message}`);
    setBusy(false);
  });
}

bootChatSession();
