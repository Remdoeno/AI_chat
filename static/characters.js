const statusText = document.getElementById("characterStatus");
const characterSticker = document.getElementById("characterSticker");
const characterChatPanel = document.querySelector(".character-chat-panel");
const messagesEl = document.getElementById("characterMessages");
const chatForm = document.getElementById("characterChatForm");
const messageInput = document.getElementById("characterMessageInput");
const sendButton = document.getElementById("characterSendButton");
const attachImageButton = document.getElementById("attachImageButton");
const drawModeButton = document.getElementById("drawModeButton");
const imageInput = document.getElementById("imageInput");
const attachmentPreview = document.getElementById("attachmentPreview");
const refreshCharactersButton = document.getElementById("refreshCharactersButton");
const characterGrid = document.getElementById("characterGrid");
const characterDialog = document.getElementById("characterDialog");
const characterDialogTitle = document.getElementById("characterDialogTitle");
const characterDialogMeta = document.getElementById("characterDialogMeta");
const characterDialogBody = document.getElementById("characterDialogBody");
const characterDialogClose = document.getElementById("characterDialogClose");
const characterDialogDelete = document.getElementById("characterDialogDelete");
const characterDialogCancel = document.getElementById("characterDialogCancel");
const characterDialogSave = document.getElementById("characterDialogSave");

let sessionId = "";
let pendingAttachments = [];
let activeController = null;
let activeDialogCharacterId = null;
let activeDialogCharacter = null;
let drawModeEnabled = false;
let hasMorePreviousCharacterSessions = false;
let isLoadingPreviousCharacterSession = false;
let isMessageComposing = false;
let messageTouchStartY = 0;
let messageTouchPullDistance = 0;
let messageTouchGestureFired = false;
let previousCharacterSessionArmedAt = 0;
let previousCharacterSessionHideTimer = 0;

const PREVIOUS_CHARACTER_SESSION_ARM_MS = 1500;
const PREVIOUS_CHARACTER_SESSION_MIN_RETRY_MS = 800;
const PREVIOUS_CHARACTER_SESSION_PULL_THRESHOLD = 8;
const PREVIOUS_CHARACTER_SESSION_DESKTOP_TOP_BUFFER = 96;

function setStatus(text) {
  statusText.textContent = text;
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
  return escapeHtml(text)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
}

function renderMarkdown(markdown) {
  const lines = String(markdown || "").replace(/\r\n/g, "\n").split("\n");
  const html = [];
  let inList = false;
  function closeList() {
    if (inList) {
      html.push("</ul>");
      inList = false;
    }
  }
  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    if (!line.trim()) {
      closeList();
      html.push("<br>");
      continue;
    }
    const heading = /^(#{1,4})\s+(.+)$/.exec(line);
    if (heading) {
      closeList();
      const level = Math.min(4, heading[1].length + 2);
      html.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }
    const bullet = /^[-*]\s+(.+)$/.exec(line.trim());
    if (bullet) {
      if (!inList) {
        html.push("<ul>");
        inList = true;
      }
      html.push(`<li>${renderInlineMarkdown(bullet[1])}</li>`);
      continue;
    }
    closeList();
    html.push(`<p>${renderInlineMarkdown(line)}</p>`);
  }
  closeList();
  return html.join("");
}

function setAssistantMarkdown(element, markdown) {
  element.dataset.rawMarkdown = markdown || "";
  element.innerHTML = renderMarkdown(markdown || "");
}

function scrollChatToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function isNearMessageTop() {
  return messagesEl.scrollTop <= 8;
}

function isInPreviousCharacterLoadZone() {
  return messagesEl.scrollTop <= PREVIOUS_CHARACTER_SESSION_DESKTOP_TOP_BUFFER || !canScrollMessages();
}

function canScrollMessages() {
  return messagesEl.scrollHeight > messagesEl.clientHeight + 4;
}

function ensureCharacterHistoryLoadIndicator() {
  let indicator = messagesEl.querySelector(".character-history-load");
  if (!indicator) {
    indicator = document.createElement("button");
    indicator.type = "button";
    indicator.className = "character-history-load is-idle";
    indicator.textContent = "加载上一段对话";
    indicator.addEventListener("click", () => loadPreviousCharacterSession());
    messagesEl.prepend(indicator);
  }
  return indicator;
}

function removeCharacterHistoryLoadIndicator(animated = false) {
  const current = messagesEl.querySelector(".character-history-load");
  if (!current) return;
  window.clearTimeout(previousCharacterSessionHideTimer);
  previousCharacterSessionHideTimer = 0;
  if (!animated) {
    current.className = "character-history-load is-idle";
    current.textContent = "加载上一段对话";
    return;
  }
  current.classList.add("is-hiding");
  window.setTimeout(() => {
    current.className = "character-history-load is-idle";
    current.textContent = "加载上一段对话";
  }, 500);
}

function setCharacterHistoryLoadState(state, text) {
  const indicator = ensureCharacterHistoryLoadIndicator();
  indicator.replaceChildren();
  indicator.className = `character-history-load is-${state}`;
  if (state === "loading") {
    const spinner = document.createElement("span");
    spinner.className = "character-history-load-spinner";
    spinner.setAttribute("aria-hidden", "true");
    const label = document.createElement("span");
    label.textContent = text;
    indicator.append(spinner, label);
  } else {
    indicator.textContent = text;
  }
}

function enterPreviousCharacterSessionArmed() {
  if (!sessionId || !hasMorePreviousCharacterSessions || isLoadingPreviousCharacterSession || previousCharacterSessionArmedAt) return;
  previousCharacterSessionArmedAt = Date.now();
  window.clearTimeout(previousCharacterSessionHideTimer);
  previousCharacterSessionHideTimer = 0;
  setCharacterHistoryLoadState("armed", "加载上一段对话");
  previousCharacterSessionHideTimer = window.setTimeout(() => {
    if (Date.now() - previousCharacterSessionArmedAt >= PREVIOUS_CHARACTER_SESSION_ARM_MS && !isLoadingPreviousCharacterSession) {
      previousCharacterSessionArmedAt = 0;
      removeCharacterHistoryLoadIndicator(true);
    }
  }, PREVIOUS_CHARACTER_SESSION_ARM_MS);
}

function cancelPreviousCharacterSessionPreparation() {
  if (!previousCharacterSessionArmedAt) return;
  previousCharacterSessionArmedAt = 0;
  removeCharacterHistoryLoadIndicator(true);
}

function armOrLoadPreviousCharacterSession() {
  if (!sessionId || !hasMorePreviousCharacterSessions || isLoadingPreviousCharacterSession) return;
  if (!isInPreviousCharacterLoadZone()) {
    cancelPreviousCharacterSessionPreparation();
    return;
  }
  const now = Date.now();
  if (!previousCharacterSessionArmedAt) {
    enterPreviousCharacterSessionArmed();
    return;
  }
  const elapsed = now - previousCharacterSessionArmedAt;
  if (elapsed < PREVIOUS_CHARACTER_SESSION_MIN_RETRY_MS) {
    setCharacterHistoryLoadState("waiting", "加载上一段对话");
    return;
  }
  if (elapsed <= PREVIOUS_CHARACTER_SESSION_ARM_MS) {
    previousCharacterSessionArmedAt = 0;
    loadPreviousCharacterSession();
    return;
  }
  enterPreviousCharacterSessionArmed();
}

function handleCharacterPreviousSessionWheel(event) {
  if (event.characterHistoryHandled) return;
  event.characterHistoryHandled = true;
  if (event.deltaY >= -4 || !isInPreviousCharacterLoadZone()) return;
  event.preventDefault();
  messagesEl.scrollTop = 0;
  armOrLoadPreviousCharacterSession();
}

function handleCharacterPreviousSessionTouchStart(event) {
  if (event.characterHistoryHandled) return;
  event.characterHistoryHandled = true;
  if (event.touches.length !== 1) return;
  messageTouchStartY = event.touches[0].clientY;
  messageTouchPullDistance = 0;
  messageTouchGestureFired = false;
}

function handleCharacterPreviousSessionTouchMove(event) {
  if (event.characterHistoryHandled) return;
  event.characterHistoryHandled = true;
  if (event.touches.length !== 1) return;
  messageTouchPullDistance = event.touches[0].clientY - messageTouchStartY;
  if (messageTouchPullDistance <= 0 || !isInPreviousCharacterLoadZone()) return;
  event.preventDefault();
  if (messageTouchPullDistance >= PREVIOUS_CHARACTER_SESSION_PULL_THRESHOLD && !messageTouchGestureFired) {
    messageTouchGestureFired = true;
    messagesEl.scrollTop = 0;
    armOrLoadPreviousCharacterSession();
    messageTouchStartY = event.touches[0].clientY;
    messageTouchPullDistance = 0;
  }
}

function jsonHeaders() {
  return { "Content-Type": "application/json" };
}

function appendMessage(role, text = "", attachments = [], options = {}) {
  const beforeHeight = messagesEl.scrollHeight;
  const row = document.createElement("div");
  row.className = `message-row ${role}`;
  const meta = document.createElement("div");
  meta.className = "message-meta";
  meta.textContent = role === "user" ? "你" : "助手";
  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  if (role === "assistant" && options.markdown !== false) {
    bubble.classList.add("markdown-body");
    setAssistantMarkdown(bubble, text);
  } else {
    bubble.textContent = text;
  }
  const visibleAttachments = Array.isArray(attachments) ? attachments : [];
  if (visibleAttachments.length) {
    const images = document.createElement("div");
    images.className = "message-images";
    for (const attachment of visibleAttachments) {
      const img = document.createElement("img");
      img.src = attachment.data_url || attachment.public_url || "";
      img.alt = attachment.name || "image";
      images.append(img);
    }
    bubble.append(images);
  }
  row.append(meta, bubble);
  if (options.prepend) {
    messagesEl.prepend(row);
    messagesEl.scrollTop += messagesEl.scrollHeight - beforeHeight;
  } else {
    messagesEl.append(row);
    if (options.scroll !== false) scrollChatToBottom();
  }
  return bubble;
}

function isAgentReplyText(text) {
  const value = String(text || "").trim();
  return /^(已记录|已更新|已保存|收到|好的|明白|角色库已更新|角色库整理|已取消|已删除|删除失败|保存失败|图片已生成|头像已加入|照片已加入)[：:，,\s]/.test(value);
}

function isLikelyImagePrompt(text) {
  const value = String(text || "").trim();
  if (!value || isAgentReplyText(value)) return false;
  if (value.length >= 120) return true;
  if ((value.match(/[,，]/g) || []).length >= 3) return true;
  return /\b(portrait|photo|photorealistic|realistic|cinematic|illustration|anime|style|lighting|composition|close-up|full-body|character|scene|background|camera|lens|high quality)\b/i.test(value);
}

function promptFromBatch(images, optimizedPrompt = "") {
  if (isLikelyImagePrompt(optimizedPrompt)) return String(optimizedPrompt).trim();
  const items = Array.isArray(images) ? images : [];
  for (const item of items) {
    const candidate = item && item.optimized_prompt ? String(item.optimized_prompt) : "";
    if (isLikelyImagePrompt(candidate)) return candidate.trim();
  }
  return "";
}

function renderGeneratedImageBatch(images, optimizedPrompt = "") {
  const wrapper = document.createElement("div");
  const grid = document.createElement("div");
  grid.className = "generated-grid";
  for (const [index, item] of (Array.isArray(images) ? images : []).entries()) {
    const url = item.public_url || item.url || "";
    if (!url) continue;
    const cell = document.createElement("div");
    cell.className = "generated-item";
    const img = document.createElement("img");
    img.src = url;
    img.alt = item.short_caption || `生成图片 ${index + 1}`;
    const download = document.createElement("a");
    download.href = url;
    download.download = `wangcai-character-${index + 1}`;
    download.textContent = "下载";
    cell.append(img, download);
    grid.append(cell);
  }
  wrapper.append(grid);
  const displayPrompt = promptFromBatch(images, optimizedPrompt);
  if (displayPrompt) {
    const details = document.createElement("details");
    details.className = "prompt-details";
    const summary = document.createElement("summary");
    summary.textContent = "优化后的 prompt";
    const pre = document.createElement("pre");
    pre.textContent = displayPrompt;
    details.append(summary, pre);
    wrapper.append(details);
  }
  return wrapper;
}

function updateDrawModeButton() {
  if (!drawModeButton) return;
  drawModeButton.classList.toggle("is-active", drawModeEnabled);
  drawModeButton.setAttribute("aria-pressed", drawModeEnabled ? "true" : "false");
}

function setBusy(busy) {
  sendButton.disabled = busy;
  attachImageButton.disabled = busy;
  if (drawModeButton) drawModeButton.disabled = busy;
  activeController = busy ? activeController : null;
}

async function createCharacterSession() {
  const response = await fetch("/api/characters/session", { method: "POST" });
  if (!response.ok) throw new Error(await response.text());
  const payload = await response.json();
  sessionId = payload.session_id || "";
  hasMorePreviousCharacterSessions = true;
  localStorage.setItem("wangcai_character_session_id", sessionId);
  appendMessage("assistant", payload.greeting || "今天又来创建或修改角色了嘛~");
}

function appendHistoryMessage(message, options = {}) {
  const attachments = Array.isArray(message.attachments) ? message.attachments : [];
  const bubble = appendMessage(message.role === "user" ? "user" : "assistant", message.content || "", attachments, {
    prepend: Boolean(options.prepend),
    scroll: false,
    markdown: message.role !== "user",
  });
  const draw = message.draw && typeof message.draw === "object" ? message.draw : {};
  const images = Array.isArray(draw.images) ? draw.images : [];
  if (message.role === "assistant" && images.length) {
    const raw = bubble.dataset.rawMarkdown || message.content || "";
    bubble.replaceChildren();
    bubble.append(renderGeneratedImageBatch(images, draw.optimized_prompt || ""));
    if (raw.trim()) {
      const textNode = document.createElement("div");
      textNode.className = "assistant-reply-text markdown-body";
      setAssistantMarkdown(textNode, raw);
      bubble.append(textNode);
    }
  }
}

function prependCharacterHistoryMessages(messages) {
  const history = Array.isArray(messages) ? messages : [];
  if (!history.length) return;

  const indicator = messagesEl.querySelector(".character-history-load");
  if (indicator) indicator.remove();
  const previousHeight = messagesEl.scrollHeight;
  const previousTop = messagesEl.scrollTop;

  for (const message of history.slice().reverse()) {
    appendHistoryMessage(message, { prepend: true });
  }

  ensureCharacterHistoryLoadIndicator();
  messagesEl.scrollTop = messagesEl.scrollHeight - previousHeight + previousTop;
}

async function loadPreviousCharacterSession() {
  if (!sessionId || !hasMorePreviousCharacterSessions || isLoadingPreviousCharacterSession) return;
  isLoadingPreviousCharacterSession = true;
  const oldStatus = statusText.textContent;
  window.clearTimeout(previousCharacterSessionHideTimer);
  previousCharacterSessionHideTimer = 0;
  setCharacterHistoryLoadState("loading", "加载上一段对话");
  setStatus("读取上一段角色库对话");
  try {
    const response = await fetch(`/api/characters/sessions/${encodeURIComponent(sessionId)}/load-previous`, {
      method: "POST",
    });
    if (!response.ok) throw new Error(await response.text());
    const payload = await response.json();
    hasMorePreviousCharacterSessions = Boolean(payload.has_more);
    const messages = Array.isArray(payload.messages) ? payload.messages : [];
    if (payload.loaded && messages.length) {
      prependCharacterHistoryMessages(messages);
      setStatus(`已载入上一段角色库对话：${messages.length} 条`);
    } else {
      setCharacterHistoryLoadState("done", "已经到第一段对话了");
      setStatus("没有更早的角色库对话了");
      window.setTimeout(() => removeCharacterHistoryLoadIndicator(true), 1400);
    }
  } catch (error) {
    setCharacterHistoryLoadState("error", `加载失败：${error.message}`);
    setStatus(`历史读取失败：${error.message}`);
    window.setTimeout(() => removeCharacterHistoryLoadIndicator(true), 1800);
  } finally {
    isLoadingPreviousCharacterSession = false;
    previousCharacterSessionArmedAt = 0;
    window.setTimeout(() => {
      if (statusText.textContent.startsWith("已载入") || statusText.textContent.startsWith("没有更早") || statusText.textContent.startsWith("历史读取失败")) {
        setStatus(oldStatus || "角色库就绪");
      }
    }, 1600);
  }
}

function characterExcerpt(item) {
  const text = [item.background, item.personality].filter(Boolean).join(" ");
  const cleaned = text.replace(/\s+/g, " ").trim();
  return cleaned || "还没有详细设定，可以在左侧聊天里补充。";
}

function renderCharacterCard(item) {
  const button = document.createElement("button");
  button.className = "character-card";
  button.type = "button";
  const cover = document.createElement("div");
  cover.className = "character-cover";
  const coverImage = item.avatar_image || item.main_image || null;
  const url = coverImage && coverImage.public_url;
  if (url) {
    const img = document.createElement("img");
    img.src = url;
    img.alt = item.canonical_name || "角色主图";
    cover.append(img);
  } else {
    const placeholder = document.createElement("div");
    placeholder.className = "character-cover-placeholder";
    placeholder.textContent = "无主图";
    cover.append(placeholder);
  }
  const title = document.createElement("h3");
  title.textContent = item.canonical_name || "未命名角色";
  const desc = document.createElement("p");
  desc.textContent = characterExcerpt(item);
  const tags = document.createElement("div");
  tags.className = "character-tags";
  const aliases = Array.isArray(item.aliases) ? item.aliases.slice(0, 3) : [];
  for (const alias of aliases) {
    const tag = document.createElement("span");
    tag.textContent = alias;
    tags.append(tag);
  }
  if (item.image_count) {
    const tag = document.createElement("span");
    tag.textContent = `${item.image_count} 图`;
    tags.append(tag);
  }
  button.append(cover, title, desc, tags);
  button.addEventListener("click", () => openCharacterDialog(item.id));
  return button;
}

async function loadCharacters() {
  setStatus("读取角色中");
  const response = await fetch("/api/characters");
  if (!response.ok) throw new Error(await response.text());
  const payload = await response.json();
  renderCharacterSticker(payload.random_avatar || null);
  characterGrid.replaceChildren();
  const items = Array.isArray(payload.items) ? payload.items : [];
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "还没有固定角色。可以在左侧聊天里创建一个。";
    characterGrid.append(empty);
  } else {
    for (const item of items) {
      characterGrid.append(renderCharacterCard(item));
    }
  }
  setStatus(`已读取 ${items.length} 个角色`);
}

function renderCharacterSticker(image) {
  characterSticker.replaceChildren();
  const url = image && image.public_url;
  if (url) {
    const img = document.createElement("img");
    img.src = url;
    img.alt = "角色头像";
    characterSticker.append(img);
  } else {
    characterSticker.textContent = "角";
  }
}

function detailBlock(label, content) {
  const block = document.createElement("div");
  block.className = "detail-block";
  const strong = document.createElement("strong");
  strong.textContent = label;
  const pre = document.createElement("pre");
  pre.textContent = content || "暂无";
  block.append(strong, pre);
  return block;
}

function editableBlock(label, field, content, rows = 3) {
  const block = document.createElement("label");
  block.className = "detail-block editable-block";
  const strong = document.createElement("strong");
  strong.textContent = label;
  const textarea = document.createElement("textarea");
  textarea.dataset.characterField = field;
  textarea.rows = rows;
  textarea.value = content || "";
  block.append(strong, textarea);
  return block;
}

function editableInputBlock(label, field, content) {
  const block = document.createElement("label");
  block.className = "detail-block editable-block";
  const strong = document.createElement("strong");
  strong.textContent = label;
  const input = document.createElement("input");
  input.dataset.characterField = field;
  input.value = content || "";
  block.append(strong, input);
  return block;
}

function splitListInput(text) {
  return String(text || "")
    .split(/[\n,，、;；]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function artifactDirectivePayloads() {
  return Array.from(characterDialogBody.querySelectorAll(".artifact-directive-editor")).map((editor) => {
    const read = (field) => {
      const element = editor.querySelector(`[data-directive-field="${field}"]`);
      return element ? element.value.trim() : "";
    };
    const deleted = editor.dataset.deleted === "true";
    return {
      id: Number(editor.dataset.directiveId || 0) || null,
      directive_type: read("directive_type") || editor.dataset.directiveType || "other",
      subject: read("subject"),
      directive: deleted ? "" : read("directive"),
      characters: splitListInput(read("characters")),
      series_title: editor.dataset.seriesTitle || "",
      scope: read("scope") || editor.dataset.scope || "persistent",
      priority: Number(editor.dataset.priority || 50),
      confidence: Number(editor.dataset.confidence || 0.8),
    };
  });
}

function characterDialogPayload() {
  const value = (field) => {
    const el = characterDialogBody.querySelector(`[data-character-field="${field}"]`);
    return el ? el.value.trim() : "";
  };
  return {
    canonical_name: value("canonical_name"),
    aliases: splitListInput(value("aliases")),
    personality: value("personality"),
    background: value("background"),
    relationships: splitListInput(value("relationships")),
    visual_prompt: value("visual_prompt"),
    negative_prompt: value("negative_prompt"),
    artifact_directives: artifactDirectivePayloads(),
  };
}

function directiveInput(field, value = "", placeholder = "") {
  const input = document.createElement("input");
  input.dataset.directiveField = field;
  input.value = value || "";
  input.placeholder = placeholder;
  return input;
}

function directiveTextarea(field, value = "", rows = 4, placeholder = "") {
  const textarea = document.createElement("textarea");
  textarea.dataset.directiveField = field;
  textarea.rows = rows;
  textarea.value = value || "";
  textarea.placeholder = placeholder;
  return textarea;
}

function directiveSelect(field, value, options) {
  const select = document.createElement("select");
  select.dataset.directiveField = field;
  for (const option of options) {
    const node = document.createElement("option");
    node.value = option.value;
    node.textContent = option.label;
    if (option.value === value) node.selected = true;
    select.append(node);
  }
  return select;
}

function directiveField(label, control, className = "") {
  const wrapper = document.createElement("label");
  wrapper.className = `artifact-directive-field ${className}`.trim();
  const span = document.createElement("span");
  span.textContent = label;
  wrapper.append(span, control);
  return wrapper;
}

function renderArtifactDirectiveEditor(directive = {}) {
  const editor = document.createElement("div");
  editor.className = "artifact-directive-editor";
  editor.dataset.directiveId = directive.id || "";
  editor.dataset.directiveType = directive.directive_type || "character_include";
  editor.dataset.scope = directive.scope || "persistent";
  editor.dataset.seriesTitle = directive.series_title || "";
  editor.dataset.priority = directive.priority || 50;
  editor.dataset.confidence = directive.confidence || 0.8;

  const type = directiveSelect("directive_type", directive.directive_type || "character_include", [
    { value: "character_include", label: "角色出场" },
    { value: "character_avoid", label: "避免出场" },
    { value: "plot_direction", label: "剧情方向" },
    { value: "style_rule", label: "风格规则" },
    { value: "series_rule", label: "系列规则" },
    { value: "image_rule", label: "配图规则" },
    { value: "other", label: "其他" },
  ]);
  const scope = directiveSelect("scope", directive.scope || "persistent", [
    { value: "persistent", label: "长期生效" },
    { value: "next_artifact", label: "只下一篇" },
  ]);

  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "artifact-directive-delete";
  remove.textContent = "×";
  remove.title = "删除这条指令";
  remove.setAttribute("aria-label", "删除这条指令");
  remove.addEventListener("click", () => {
    if (editor.dataset.directiveId) {
      editor.dataset.deleted = "true";
      editor.classList.add("is-deleted");
      editor.setAttribute("aria-hidden", "true");
    } else {
      editor.remove();
    }
  });

  const main = document.createElement("div");
  main.className = "artifact-directive-main";
  const headLine = document.createElement("div");
  headLine.className = "artifact-directive-row artifact-directive-row-compact";
  headLine.append(directiveField("用途", type), directiveField("有效范围", scope));

  const topLine = document.createElement("div");
  topLine.className = "artifact-directive-row";

  const subject = directiveInput("subject", directive.subject || activeDialogCharacter?.canonical_name || "", "例如：酒吧失恋与训斥场景");
  const characters = directiveInput(
    "characters",
    Array.isArray(directive.characters) && directive.characters.length
      ? directive.characters.join("、")
      : activeDialogCharacter?.canonical_name || "",
    "例如：糯糯、樱井凛",
  );
  topLine.append(directiveField("标题", subject), directiveField("关联角色", characters));

  const text = directiveTextarea("directive", directive.directive || "", 4, "写给成果小剧场的导演指令");
  const textField = directiveField("具体指令", text, "artifact-directive-field-wide");

  main.append(headLine, topLine, textField);
  editor.append(main, remove);
  return editor;
}

function renderArtifactDirectiveBlock(directives) {
  const block = document.createElement("div");
  block.className = "detail-block editable-block artifact-directives-block";
  const strong = document.createElement("strong");
  strong.textContent = "成果小剧场指令";
  const hint = document.createElement("p");
  hint.className = "artifact-directive-hint";
  hint.textContent = "只影响后续成果小剧场的剧情和配图，不改角色本体；删除后点确定才生效。";
  const list = document.createElement("div");
  list.className = "artifact-directive-list";
  for (const directive of directives || []) {
    list.append(renderArtifactDirectiveEditor(directive));
  }
  if (!list.children.length) {
    list.append(renderArtifactDirectiveEditor({ directive_type: "character_include" }));
  }
  const add = document.createElement("button");
  add.type = "button";
  add.className = "secondary-button artifact-directive-add";
  add.textContent = "新增小剧场指令";
  add.addEventListener("click", () => list.append(renderArtifactDirectiveEditor({ directive_type: "character_include" })));
  block.append(strong, hint, list, add);
  return block;
}

function renderManagedImageBlock(label, kind, images) {
  const block = document.createElement("div");
  block.className = `detail-block detail-image-block detail-image-block-${kind}`;
  const strong = document.createElement("strong");
  strong.textContent = label;
  const grid = document.createElement("div");
  grid.className = `detail-images managed-images managed-images-${kind}`;
  for (const image of images) {
    const imageId = image.id;
    const url = image.public_url || "";
    const cell = document.createElement("div");
    cell.className = "managed-image";
    const img = document.createElement("img");
    img.src = url;
    img.alt = `${activeDialogCharacter?.canonical_name || "角色"}${label}`;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "managed-image-delete";
    remove.textContent = "🗑";
    remove.title = "删除图片";
    remove.setAttribute("aria-label", "删除图片");
    remove.addEventListener("click", () => deleteCharacterImage(imageId));
    const download = document.createElement("a");
    download.className = "managed-image-download";
    download.href = url;
    download.download = `wangcai-character-${kind}-${imageId || "image"}`;
    download.textContent = "下载";
    cell.append(img, remove, download);
    grid.append(cell);
  }
  block.append(strong, grid);
  return block;
}

function renderCharacterDialog(item) {
  activeDialogCharacterId = item.id;
  activeDialogCharacter = item;
  characterDialogTitle.textContent = item.canonical_name || "未命名角色";
  characterDialogMeta.textContent = `#${item.id} · 修订 ${item.revision_count || 1} · ${item.updated_at || ""}`;
  characterDialogBody.replaceChildren();
  const imageTools = document.createElement("div");
  imageTools.className = "character-image-tools";
  const avatarButton = document.createElement("button");
  avatarButton.type = "button";
  avatarButton.className = "secondary-button";
  avatarButton.textContent = "创建头像";
  avatarButton.addEventListener("click", () => generateCharacterImage("avatar"));
  const photoButton = document.createElement("button");
  photoButton.type = "button";
  photoButton.className = "secondary-button";
  photoButton.textContent = "创建照片";
  photoButton.addEventListener("click", () => generateCharacterImage("photo"));
  imageTools.append(avatarButton, photoButton);
  characterDialogBody.append(imageTools);

  const avatarImages = Array.isArray(item.avatar_images) ? item.avatar_images : [];
  if (avatarImages.length) {
    characterDialogBody.append(renderManagedImageBlock("头像图", "avatar", avatarImages));
  }
  const images = Array.isArray(item.reference_images) ? item.reference_images : [];
  if (images.length) {
    characterDialogBody.append(renderManagedImageBlock("参考图", "photo", images));
  }
  characterDialogBody.append(
    editableInputBlock("名称", "canonical_name", item.canonical_name || ""),
    editableBlock("别名", "aliases", (item.aliases || []).join("\n"), 2),
    editableBlock("性格", "personality", item.personality || "", 4),
    editableBlock("背景", "background", item.background || "", 5),
    editableBlock("关系", "relationships", (item.relationships || []).join("\n"), 3),
    renderArtifactDirectiveBlock(item.artifact_directives || []),
    editableBlock("形象 Prompt", "visual_prompt", item.visual_prompt || "", 7),
    editableBlock("Negative Prompt", "negative_prompt", item.negative_prompt || "", 3),
  );
}

async function openCharacterDialog(characterId) {
  const response = await fetch(`/api/characters/${encodeURIComponent(characterId)}`);
  if (!response.ok) throw new Error(await response.text());
  const item = await response.json();
  renderCharacterDialog(item);
  characterDialog.showModal();
  characterDialog.scrollTop = 0;
}

async function refreshActiveCharacterDialog() {
  if (!activeDialogCharacterId) return;
  const response = await fetch(`/api/characters/${encodeURIComponent(activeDialogCharacterId)}`);
  if (!response.ok) throw new Error(await response.text());
  const item = await response.json();
  renderCharacterDialog(item);
}

function closeCharacterDialog() {
  characterDialog.close();
  activeDialogCharacterId = null;
  activeDialogCharacter = null;
}

async function saveActiveCharacter() {
  if (!activeDialogCharacterId) return;
  const payload = characterDialogPayload();
  if (!payload.canonical_name) {
    setStatus("角色名称不能为空");
    return;
  }
  characterDialogSave.disabled = true;
  setStatus("保存角色中");
  try {
    const response = await fetch(`/api/characters/${encodeURIComponent(activeDialogCharacterId)}`, {
      method: "PATCH",
      headers: jsonHeaders(),
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error(await response.text());
    const item = await response.json();
    activeDialogCharacter = item;
    characterDialogTitle.textContent = item.canonical_name || "未命名角色";
    characterDialogMeta.textContent = `#${item.id} · 修订 ${item.revision_count || 1} · ${item.updated_at || ""}`;
    closeCharacterDialog();
    await loadCharacters();
    setStatus("角色已保存");
  } catch (error) {
    setStatus(`保存失败：${error.message}`);
  } finally {
    characterDialogSave.disabled = false;
  }
}

async function deleteActiveCharacter() {
  if (!activeDialogCharacterId) return;
  const ok = window.confirm("确定删除这个角色吗？");
  if (!ok) return;
  const response = await fetch(`/api/characters/${encodeURIComponent(activeDialogCharacterId)}`, { method: "DELETE" });
  if (!response.ok) throw new Error(await response.text());
  closeCharacterDialog();
  await loadCharacters();
}

async function generateCharacterImage(kind) {
  if (!activeDialogCharacterId) return;
  setStatus(kind === "avatar" ? "正在创建头像" : "正在创建照片");
  try {
    const response = await fetch(`/api/characters/${encodeURIComponent(activeDialogCharacterId)}/images/generate`, {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify({ kind }),
    });
    if (!response.ok) throw new Error(await response.text());
    const payload = await response.json();
    if (payload.character) renderCharacterDialog(payload.character);
    await loadCharacters();
    setStatus(kind === "avatar" ? "头像已加入角色卡片" : "照片已加入角色卡片");
  } catch (error) {
    setStatus(`图片创建失败：${error.message}`);
  }
}

async function deleteCharacterImage(imageId) {
  if (!activeDialogCharacterId || !imageId) return;
  const ok = window.confirm("确定删除这张图片吗？角色至少需要保留一张图片。");
  if (!ok) return;
  setStatus("正在删除图片");
  try {
    const response = await fetch(
      `/api/characters/${encodeURIComponent(activeDialogCharacterId)}/images/${encodeURIComponent(imageId)}`,
      { method: "DELETE" },
    );
    if (!response.ok) throw new Error(await response.text());
    const payload = await response.json();
    if (payload.character) renderCharacterDialog(payload.character);
    await loadCharacters();
    setStatus("图片已删除");
  } catch (error) {
    setStatus(`图片删除失败：${error.message}`);
  }
}

function consumeSse(response, handlers) {
  const decoder = new TextDecoder();
  let buffer = "";
  const reader = response.body.getReader();

  async function dispatch(block) {
    const lines = block.split("\n");
    let event = "message";
    const data = [];
    for (const line of lines) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    let payload = {};
    try {
      payload = JSON.parse(data.join("\n") || "{}");
    } catch {
      payload = { raw: data.join("\n") };
    }
    const handler = handlers[event];
    if (handler) await handler(payload);
  }

  return (async () => {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() || "";
      for (const block of blocks) {
        if (block.trim()) await dispatch(block);
      }
    }
    if (buffer.trim()) await dispatch(buffer);
  })();
}

async function sendCharacterMessage(text, attachments, mode = "chat") {
  const userText = text || (attachments.length ? "请根据这张图片创建或修改角色。" : "");
  if (!userText) return;
  appendMessage("user", userText, attachments);
  const assistantBody = appendMessage("assistant", "角色库整理中");
  activeController = new AbortController();
  setBusy(true);
  setStatus("角色库整理中");
  try {
    const response = await fetch("/api/characters/chat/stream", {
      method: "POST",
      headers: jsonHeaders(),
      signal: activeController.signal,
      body: JSON.stringify({
        session_id: sessionId,
        message: userText,
        mode,
        attachments,
      }),
    });
    if (!response.ok || !response.body) throw new Error(await response.text());
    let textBuffer = "";
    await consumeSse(response, {
      draw_status: (payload) => {
        setAssistantMarkdown(assistantBody, payload.message || "画图中");
        setStatus(payload.message || "画图中");
      },
      draw_prompt: () => {
        setAssistantMarkdown(assistantBody, "画图 prompt 已优化，正在生成图片。");
        setStatus("HiDream 生成中");
      },
      draw_image_batch: (payload) => {
        assistantBody.replaceChildren();
        assistantBody.append(renderGeneratedImageBatch(payload.images || [], payload.optimized_prompt || ""));
        const linked = Array.isArray(payload.linked_characters) ? payload.linked_characters : [];
        const suffix = linked.length
          ? `，已绑定：${linked.map((item) => item.canonical_name || `#${item.id}`).join("、")}`
          : "";
        setStatus(`图片已生成：${(payload.images || []).length} 张${suffix}`);
        scrollChatToBottom();
      },
      uploaded_images: () => {
        setStatus("上传图片已保存");
      },
      character_status: (payload) => {
        setStatus(payload.message || "角色库整理中");
      },
      character_update: async () => {
        await loadCharacters();
      },
      token: (payload) => {
        textBuffer += payload.content || "";
        const existingImages = assistantBody.querySelector(".generated-grid");
        if (existingImages) {
          let textNode = assistantBody.querySelector(".assistant-reply-text");
          if (!textNode) {
            textNode = document.createElement("div");
            textNode.className = "assistant-reply-text markdown-body";
            assistantBody.append(textNode);
          }
          setAssistantMarkdown(textNode, textBuffer);
        } else {
          setAssistantMarkdown(assistantBody, textBuffer);
        }
        scrollChatToBottom();
      },
      draw_error: (payload) => {
        setAssistantMarkdown(assistantBody, payload.message || "图片生成失败");
        setStatus("图片生成失败");
      },
      error: (payload) => {
        setAssistantMarkdown(assistantBody, payload.message || "角色库处理失败");
        setStatus("角色库处理失败");
      },
      delete_confirmation_required: async (payload) => {
        const characterId = payload.id;
        const name = payload.canonical_name || `#${characterId}`;
        if (!characterId) return;
        window.setTimeout(async () => {
          const ok = window.confirm(`确定删除角色“${name}”吗？`);
          if (!ok) {
            appendMessage("assistant", `已取消删除 ${name}。`);
            setStatus("已取消删除");
            return;
          }
          try {
            const response = await fetch(`/api/characters/${encodeURIComponent(characterId)}`, { method: "DELETE" });
            if (!response.ok) throw new Error(await response.text());
            appendMessage("assistant", `已删除 ${name}。`);
            await loadCharacters();
            setStatus("角色已删除");
          } catch (error) {
            appendMessage("assistant", `删除失败：${error.message}`);
            setStatus("删除失败");
          }
        }, 0);
      },
      done: () => {
        setStatus("角色库已更新");
      },
    });
  } catch (error) {
    setAssistantMarkdown(assistantBody, `请求失败：${error.message}`);
    setStatus("请求失败");
  } finally {
    setBusy(false);
    clearPendingAttachments();
  }
}

function clearPendingAttachments() {
  pendingAttachments = [];
  attachmentPreview.replaceChildren();
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error("图片读取失败"));
    reader.readAsDataURL(file);
  });
}

async function addImageFiles(files) {
  for (const file of Array.from(files || [])) {
    if (!file.type.startsWith("image/")) continue;
    const dataUrl = await fileToDataUrl(file);
    pendingAttachments.push({
      name: file.name || "image",
      mime_type: file.type || "image/png",
      data_url: dataUrl,
      size: file.size || 0,
    });
  }
  renderAttachmentPreview();
}

function renderAttachmentPreview() {
  attachmentPreview.replaceChildren();
  pendingAttachments.forEach((attachment, index) => {
    const chip = document.createElement("div");
    chip.className = "attachment-chip";
    const img = document.createElement("img");
    img.src = attachment.data_url;
    img.alt = attachment.name;
    const label = document.createElement("span");
    label.textContent = attachment.name || "image";
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "×";
    remove.addEventListener("click", () => {
      pendingAttachments.splice(index, 1);
      renderAttachmentPreview();
    });
    chip.append(img, label, remove);
    attachmentPreview.append(chip);
  });
}

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (activeController) return;
  const text = messageInput.value.trim();
  const attachments = pendingAttachments.map((item) => ({ ...item }));
  if (!text && !attachments.length) return;
  messageInput.value = "";
  await sendCharacterMessage(text, attachments, drawModeEnabled ? "draw" : "chat");
});

messageInput.addEventListener("compositionstart", () => {
  isMessageComposing = true;
});

messageInput.addEventListener("compositionend", () => {
  isMessageComposing = false;
});

messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing && !isMessageComposing) {
    event.preventDefault();
    chatForm.requestSubmit();
  }
});

messagesEl.addEventListener("scroll", () => {
  if (isInPreviousCharacterLoadZone()) {
    return;
  }
  cancelPreviousCharacterSessionPreparation();
});

messagesEl.addEventListener("wheel", handleCharacterPreviousSessionWheel, { passive: false });
messagesEl.addEventListener("touchstart", handleCharacterPreviousSessionTouchStart, { passive: true });
messagesEl.addEventListener("touchmove", handleCharacterPreviousSessionTouchMove, { passive: false });
if (characterChatPanel) {
  characterChatPanel.addEventListener("wheel", handleCharacterPreviousSessionWheel, { passive: false });
  characterChatPanel.addEventListener("touchstart", handleCharacterPreviousSessionTouchStart, { passive: true });
  characterChatPanel.addEventListener("touchmove", handleCharacterPreviousSessionTouchMove, { passive: false });
}

attachImageButton.addEventListener("click", () => imageInput.click());
if (drawModeButton) {
  drawModeButton.addEventListener("click", () => {
    drawModeEnabled = !drawModeEnabled;
    updateDrawModeButton();
  });
}
imageInput.addEventListener("change", async () => {
  try {
    await addImageFiles(imageInput.files || []);
  } catch (error) {
    setStatus(`图片读取失败：${error.message}`);
  } finally {
    imageInput.value = "";
  }
});

refreshCharactersButton.addEventListener("click", loadCharacters);
characterDialogClose.addEventListener("click", closeCharacterDialog);
characterDialogCancel.addEventListener("click", closeCharacterDialog);
characterDialogSave.addEventListener("click", saveActiveCharacter);
characterDialog.addEventListener("click", (event) => {
  if (event.target === characterDialog) closeCharacterDialog();
});
characterDialogDelete.addEventListener("click", async () => {
  try {
    await deleteActiveCharacter();
  } catch (error) {
    setStatus(`删除失败：${error.message}`);
  }
});

(async function init() {
  try {
    updateDrawModeButton();
    await createCharacterSession();
    await loadCharacters();
    messageInput.focus();
  } catch (error) {
    setStatus(`初始化失败：${error.message}`);
  }
})();
