(function () {
  const STATE_KEY = "wangcai_tutorial_state_v1";
  const ACTIVE_ID_KEY = "wangcai_tutorial_active_id";
  const COMPLETED_KEY = "wangcai_tutorial_completed_v1";
  const DEVICE_KEY = "wangcai_device_id";
  const ID_PATTERN = /^[A-Za-z0-9_-]{12,96}$/;

  const steps = [
    {
      path: "/",
      title: "认识旺财",
      target: ".brand-block",
      body: "旺财不是只等提问的聊天框。每次打开窗口，它都会结合时间、设备身份和近期生活主动开场；你也可以在聊天里给它重新起名、调整相处方式。",
    },
    {
      path: "/",
      title: "绑定你的用户",
      target: "#userMemoryBindingButton",
      action: "binding",
      requireBinding: true,
      body: "点击高亮的“记忆绑定”。同一个用户可以绑定多台设备，共享长期记忆与聊天上下文；主机设备负责承接主要生活记录。首次绑定时请设置独立密码。",
    },
    {
      path: "/",
      title: "配置模型",
      target: "#bunnyLogoButton",
      action: "models",
      body: "在主页连续点击左上角的兔子 4 次，才会展开高级配置。旺财把聊天、后台整理和画图模型分开配置，支持本地服务和 OpenAI 兼容 API；教程中也可以用下方按钮直接打开模型配置。",
    },
    {
      path: "/",
      title: "主动开场与长期陪伴",
      target: "#messages .message.assistant",
      placement: "below-target",
      body: "这里是旺财的主动开场。它会自然提到近期安排、长期关注和当下状态，而不是每次都从零开始；这些理解来自经过整理的用户记忆，不是把角色设定混进个人画像。",
    },
    {
      path: "/",
      title: "亲手聊一句",
      target: "#messageInput",
      placement: "above-target",
      body: "现在可以在高亮输入框里发一句话，体验引用、图片粘贴、联网和画图等能力。教程中的这段对话只属于临时会话，结束后会清除，也不会触发记忆写入或故事生成。",
    },
    {
      path: "/",
      title: "打开成果库",
      target: "a.sidebar-link[href='/artifacts']",
      requireTargetClick: true,
      body: "请亲自点击高亮的“成果”按钮进入成果库。旺财会把聊天中形成的灵感继续发展成可以长期浏览的图文作品。",
    },
    {
      path: "/artifacts",
      title: "成果库",
      target: "#artifactList",
      body: "旺财会在空闲时把聊天中形成的灵感继续创作成小说、剧本、世界观和配图。成果按用户隔离，也可以把精选作品公开给其他用户点赞和评论。",
    },
    {
      path: "/artifacts",
      title: "现场生成一份图文",
      target: "#artifactList",
      demo: true,
      requireDemo: true,
      body: "输入一个不含真实人物或隐私的创作主题，现场体验后台模型与画图模型如何组合生成图文。结果只显示在本浮窗，不写入成果库、图片目录或长期记忆。",
    },
    {
      path: "/artifacts",
      title: "进入角色库",
      target: ".character-library-link",
      body: "角色库保存角色的外观锚点、性格、关系和创作约束，确保跨作品保持一致。它与用户本人记忆严格分离；教程中只浏览，不修改正式角色。",
    },
    {
      path: "/characters",
      title: "角色库如何工作",
      target: ".character-library-panel",
      body: "角色卡会固定族裔、年龄、发型、体型、面部结构与身份标志；一次性场景只改变动作、服装和环境。正式使用时可以通过左侧对话创建、修改或画角色。",
    },
    {
      path: "/analysis",
      allowPaths: ["/analysis", "/analysis-login"],
      title: "分析模式",
      target: "#analysisMode, .analysis-login-card",
      requireAuth: true,
      body: "分析模式属于当前共享用户，首次进入需要设置独立密码。它展示模型推理过程、检索与后台步骤，适合排查复杂任务；普通聊天仍保持自然、简洁。",
    },
    {
      path: "/memory",
      allowPaths: ["/memory", "/analysis-login"],
      title: "记忆库",
      target: ".memory-shell, .analysis-login-card",
      body: "记忆库同样受用户密码保护。这里能查看整理后的生活事实、偏好、日程与调用记录；角色和成果创作资料不会伪装成用户记忆。",
    },
    {
      path: "/",
      title: "教程完成",
      target: "#tutorialButton",
      body: "你已经走完主要流程。以后可从主页的“新手教程”重新进入；正式聊天会继续形成属于你的长期理解，而本次教程中的临时会话与生成内容现在会被清理。",
      final: true,
    },
  ];

  let state = readState();
  let root = null;
  let highlighted = null;
  let dialogObserver = null;

  function validId(value) {
    return ID_PATTERN.test(String(value || "").trim());
  }

  function isMobileViewport() {
    return window.matchMedia("(max-width: 820px)").matches;
  }

  function showDesktopOnlyNotice() {
    window.alert("新手教程目前仅支持电脑端，请使用电脑浏览器进入。移动端的聊天和其他功能仍可正常使用。");
  }

  function makeId(prefix) {
    const random = window.crypto && crypto.randomUUID
      ? crypto.randomUUID().replace(/-/g, "")
      : `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`;
    return `${prefix}_${random.slice(0, 32)}`;
  }

  function deviceId() {
    let value = "";
    try {
      value = localStorage.getItem(DEVICE_KEY) || "";
      if (!validId(value)) {
        value = makeId("dev");
        localStorage.setItem(DEVICE_KEY, value);
      }
    } catch (_) {
      value = makeId("dev");
    }
    return value;
  }

  function headers(json = false) {
    const result = { "X-Wangcai-Device-Id": deviceId() };
    if (json) result["Content-Type"] = "application/json";
    if (state && validId(state.id)) result["X-Wangcai-Tutorial-Id"] = state.id;
    return result;
  }

  function readState() {
    try {
      const parsed = JSON.parse(localStorage.getItem(STATE_KEY) || "null");
      if (parsed && validId(parsed.id) && Number.isInteger(parsed.step)) return parsed;
    } catch (_) {
      return null;
    }
    return null;
  }

  function saveState() {
    if (!state) return;
    localStorage.setItem(STATE_KEY, JSON.stringify(state));
    localStorage.setItem(ACTIVE_ID_KEY, state.id);
  }

  function routePath() {
    return window.location.pathname.replace(/\/$/, "") || "/";
  }

  function stepAcceptsPath(step) {
    const current = routePath();
    return (step.allowPaths || [step.path]).includes(current);
  }

  function navigateForStep(step) {
    if (stepAcceptsPath(step)) return false;
    window.location.href = step.path;
    return true;
  }

  function clearHighlight() {
    if (highlighted) highlighted.classList.remove("wangcai-tutorial-highlight");
    highlighted = null;
  }

  function findTarget(selector) {
    if (!selector) return null;
    return document.querySelector(selector);
  }

  function positionCard(card, target, step) {
    if (step && step.placement === "above-target" && target) {
      const targetRect = target.getBoundingClientRect();
      const width = Math.min(420, Math.max(280, targetRect.width));
      const left = Math.max(14, Math.min(targetRect.left, window.innerWidth - width - 14));
      card.style.width = `${width}px`;
      card.style.maxHeight = `${Math.max(120, targetRect.top - 32)}px`;
      card.style.left = `${left}px`;
      card.style.right = "auto";
      card.style.top = "auto";
      card.style.bottom = `${window.innerHeight - targetRect.top + 18}px`;
      return;
    }
    if (step && step.placement === "below-target" && target && !window.matchMedia("(max-width: 720px)").matches) {
      const targetRect = target.getBoundingClientRect();
      const composer = document.querySelector(".composer");
      const composerTop = composer ? composer.getBoundingClientRect().top : window.innerHeight;
      const width = Math.min(420, window.innerWidth - targetRect.left - 28);
      const top = targetRect.bottom + 18;
      card.style.width = `${Math.max(300, width)}px`;
      card.style.maxHeight = `${Math.max(120, composerTop - top - 14)}px`;
      card.style.left = `${Math.min(targetRect.left, window.innerWidth - Math.max(300, width) - 14)}px`;
      card.style.right = "auto";
      card.style.top = `${top}px`;
      card.style.bottom = "auto";
      return;
    }
    card.style.width = "";
    card.style.maxHeight = "";
    if (window.matchMedia("(max-width: 720px)").matches || !target) {
      card.style.left = "auto";
      card.style.right = "22px";
      card.style.top = "22px";
      card.style.bottom = "auto";
      return;
    }
    const rect = target.getBoundingClientRect();
    const width = Math.min(420, window.innerWidth - 28);
    const gap = 18;
    let left = rect.right + gap;
    if (left + width > window.innerWidth - 14) left = Math.max(14, rect.left - width - gap);
    let top = Math.max(14, Math.min(rect.top, window.innerHeight - 560));
    card.style.left = `${left}px`;
    card.style.right = "auto";
    card.style.top = `${top}px`;
    card.style.bottom = "auto";
  }

  function savedCardPosition() {
    const positions = state && state.card_positions;
    return positions && positions[String(state.step)] ? positions[String(state.step)] : null;
  }

  function applySavedCardPosition(card) {
    const saved = savedCardPosition();
    if (!saved) return;
    const rect = card.getBoundingClientRect();
    const left = Math.max(8, Math.min(Number(saved.left) || 8, window.innerWidth - rect.width - 8));
    const top = Math.max(8, Math.min(Number(saved.top) || 8, window.innerHeight - Math.min(rect.height, window.innerHeight - 16) - 8));
    card.style.left = `${left}px`;
    card.style.top = `${top}px`;
    card.style.right = "auto";
    card.style.bottom = "auto";
    card.style.maxHeight = `${Math.max(120, window.innerHeight - top - 8)}px`;
  }

  function makeCardDraggable(card, handle) {
    let drag = null;
    handle.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      const rect = card.getBoundingClientRect();
      drag = {
        pointerId: event.pointerId,
        offsetX: event.clientX - rect.left,
        offsetY: event.clientY - rect.top,
      };
      handle.setPointerCapture(event.pointerId);
      event.preventDefault();
    });
    handle.addEventListener("pointermove", (event) => {
      if (!drag || drag.pointerId !== event.pointerId) return;
      const rect = card.getBoundingClientRect();
      const left = Math.max(8, Math.min(event.clientX - drag.offsetX, window.innerWidth - rect.width - 8));
      const top = Math.max(8, Math.min(event.clientY - drag.offsetY, window.innerHeight - 120));
      card.style.left = `${left}px`;
      card.style.top = `${top}px`;
      card.style.right = "auto";
      card.style.bottom = "auto";
      card.style.maxHeight = `${Math.max(120, window.innerHeight - top - 8)}px`;
    });
    const finishDrag = (event) => {
      if (!drag || drag.pointerId !== event.pointerId) return;
      drag = null;
      const rect = card.getBoundingClientRect();
      state.card_positions = state.card_positions || {};
      state.card_positions[String(state.step)] = { left: Math.round(rect.left), top: Math.round(rect.top) };
      saveState();
      if (handle.hasPointerCapture(event.pointerId)) handle.releasePointerCapture(event.pointerId);
    };
    handle.addEventListener("pointerup", finishDrag);
    handle.addEventListener("pointercancel", finishDrag);
  }

  function tutorialDemo(card) {
    const wrap = document.createElement("div");
    wrap.className = "wangcai-tutorial-demo";
    const input = document.createElement("textarea");
    input.placeholder = "例如：雨夜旧书店里，一位陌生人留下一封没有署名的信";
    const generate = document.createElement("button");
    generate.type = "button";
    generate.textContent = "生成临时图文";
    const status = document.createElement("p");
    const result = document.createElement("div");
    result.className = "wangcai-tutorial-result";
    generate.addEventListener("click", async () => {
      const prompt = input.value.trim();
      if (prompt.length < 2) {
        status.textContent = "先写一个简短主题。";
        input.focus();
        return;
      }
      generate.disabled = true;
      status.textContent = "正在调用后台创作与画图模型，可能需要一两分钟…";
      result.replaceChildren();
      try {
        const response = await fetch("/api/tutorial/artifact", {
          method: "POST",
          headers: headers(true),
          body: JSON.stringify({ tutorial_id: state.id, prompt }),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(payload.detail || "临时图文生成失败");
        if (payload.image_data_url) {
          const image = document.createElement("img");
          image.src = payload.image_data_url;
          image.alt = "教程临时生成图片";
          result.appendChild(image);
        }
        const title = document.createElement("h3");
        title.textContent = payload.title || "临时成果";
        const summary = document.createElement("p");
        summary.textContent = payload.summary || payload.content || "";
        result.append(title, summary);
        state.demo_completed = true;
        saveState();
        status.textContent = payload.image_error ? "正文已生成，图片服务本次未返回结果。" : "生成完成。此结果不会保存。";
      } catch (error) {
        status.textContent = error.message || "临时图文生成失败";
      } finally {
        generate.disabled = false;
      }
    });
    wrap.append(input, generate, status, result);
    card.appendChild(wrap);
  }

  function actionArea(step, card) {
    if (!step.action) return;
    const actions = document.createElement("div");
    actions.className = "wangcai-tutorial-actions";
    const button = document.createElement("button");
    button.type = "button";
    if (step.action === "binding") {
      button.textContent = "打开用户绑定";
      button.addEventListener("click", () => document.getElementById("userMemoryBindingButton")?.click());
    } else if (step.action === "models") {
      button.textContent = "打开模型配置";
      button.addEventListener("click", () => {
        if (window.WangcaiApp && window.WangcaiApp.openModelSettingsDialog) {
          window.WangcaiApp.openModelSettingsDialog();
        } else {
          document.getElementById("openModelSettingsButton")?.click();
        }
      });
    }
    actions.appendChild(button);
    card.appendChild(actions);
  }

  function render() {
    if (!state) return;
    const step = steps[Math.max(0, Math.min(state.step, steps.length - 1))];
    state.step = steps.indexOf(step);
    saveState();
    if (navigateForStep(step)) return;
    clearHighlight();
    if (root) root.remove();

    root = document.createElement("div");
    root.className = "wangcai-tutorial-root";
    root.setAttribute("aria-live", "polite");
    const backdrop = document.createElement("div");
    backdrop.className = "wangcai-tutorial-backdrop";
    const card = document.createElement("section");
    card.className = "wangcai-tutorial-card";
    card.setAttribute("role", "dialog");
    card.setAttribute("aria-modal", "false");

    const kicker = document.createElement("p");
    kicker.className = "wangcai-tutorial-kicker";
    kicker.textContent = "WANGCAI GUIDE";
    const progress = document.createElement("p");
    progress.className = "wangcai-tutorial-step";
    progress.textContent = `${state.step + 1} / ${steps.length}`;
    const dragHandle = document.createElement("div");
    dragHandle.className = "wangcai-tutorial-drag-handle";
    dragHandle.title = "拖动教程窗口";
    dragHandle.append(kicker, progress);
    const title = document.createElement("h2");
    title.textContent = step.title;
    const body = document.createElement("p");
    body.textContent = step.body;
    const sandbox = document.createElement("p");
    sandbox.className = "wangcai-tutorial-sandbox";
    sandbox.textContent = "教程保护：本模式产生的聊天、记忆、故事、角色改动和演示成果不会保存。用户绑定与模型配置是你主动确认的正式设置。";
    card.append(dragHandle, title, body, sandbox);
    actionArea(step, card);
    if (step.demo) tutorialDemo(card);

    const feedback = document.createElement("p");
    feedback.className = "wangcai-tutorial-feedback";
    card.appendChild(feedback);
    const nav = document.createElement("div");
    nav.className = "wangcai-tutorial-nav";
    const previous = document.createElement("button");
    previous.type = "button";
    previous.textContent = "上一步";
    previous.disabled = state.step === 0;
    previous.addEventListener("click", () => move(-1));
    const skip = document.createElement("button");
    skip.type = "button";
    skip.className = "tutorial-skip";
    skip.textContent = "跳过教程";
    skip.addEventListener("click", () => finish("skipped"));
    const next = document.createElement("button");
    next.type = "button";
    next.className = "tutorial-primary";
    next.textContent = step.requireTargetClick ? "请点击高亮按钮" : (step.final ? "完成" : "下一步");
    next.disabled = Boolean(step.requireTargetClick);
    next.addEventListener("click", () => step.final ? finish("completed") : advance(step, card));
    nav.append(previous, skip, next);
    card.appendChild(nav);
    root.append(backdrop, card);
    document.body.appendChild(root);

    highlighted = findTarget(step.target);
    if (highlighted) {
      highlighted.classList.add("wangcai-tutorial-highlight");
      if (step.requireTargetClick) {
        highlighted.addEventListener("click", () => {
          if (!state) return;
          state.step = Math.min(steps.length - 1, state.step + 1);
          saveState();
        }, { once: true });
      }
      highlighted.scrollIntoView({
        block: step.placement === "below-target" ? "start" : (step.placement === "above-target" ? "end" : "center"),
        behavior: "smooth",
      });
    }
    makeCardDraggable(card, dragHandle);
    window.setTimeout(() => {
      positionCard(card, highlighted, step);
      applySavedCardPosition(card);
    }, 80);
    observeDialogs();
  }

  function move(delta) {
    if (!state) return;
    state.step = Math.max(0, Math.min(steps.length - 1, state.step + delta));
    saveState();
    render();
  }

  async function advance(step, card) {
    const feedback = card.querySelector(".wangcai-tutorial-feedback");
    if (step.requireTargetClick) {
      feedback.textContent = "请点击页面中高亮的按钮继续。";
      return;
    }
    if (step.requireBinding) {
      try {
        const response = await fetch("/api/tutorial/status", { headers: headers(), cache: "no-store" });
        const payload = await response.json();
        if (!response.ok || !payload.bound) {
          feedback.textContent = "请先完成共享用户绑定并保存，再进入下一步。";
          document.getElementById("userMemoryBindingButton")?.click();
          return;
        }
      } catch (_) {
        feedback.textContent = "暂时无法确认绑定状态，请稍后再试。";
        return;
      }
    }
    if (step.requireDemo && !state.demo_completed) {
      feedback.textContent = "请先生成一次临时图文，体验完整流程。";
      return;
    }
    if (step.requireAuth && document.querySelector(".analysis-login-card")) {
      feedback.textContent = "请先在当前页面设置或输入共享用户密码，进入分析模式后再继续。";
      return;
    }
    move(1);
  }

  async function cleanup() {
    if (!state || !validId(state.id)) return;
    try {
      await fetch("/api/tutorial/complete", {
        method: "POST",
        headers: headers(true),
        body: JSON.stringify({ tutorial_id: state.id }),
        keepalive: true,
      });
    } catch (_) {
      // Expiry cleanup is the fallback if the page closes during this request.
    }
  }

  async function finish(outcome) {
    const oldState = state;
    const stop = window.WangcaiApp?.stopActiveGeneration || window.WangcaiAnalysis?.stopActiveGeneration;
    if (stop) {
      await Promise.resolve(stop());
      await new Promise((resolve) => window.setTimeout(resolve, 200));
    }
    await cleanup();
    clearHighlight();
    if (root) root.remove();
    root = null;
    state = null;
    localStorage.removeItem(STATE_KEY);
    localStorage.removeItem(ACTIVE_ID_KEY);
    localStorage.setItem(COMPLETED_KEY, JSON.stringify({ outcome, at: new Date().toISOString() }));
    if (routePath() !== "/") window.location.href = "/";
    else if (oldState) window.location.reload();
  }

  function start() {
    if (isMobileViewport()) {
      showDesktopOnlyNotice();
      return;
    }
    state = { id: makeId("guide"), step: 0, started_at: new Date().toISOString() };
    saveState();
    render();
  }

  function observeDialogs() {
    if (dialogObserver) return;
    const update = () => {
      if (!root) return;
      const openDialog = document.querySelector("dialog[open]");
      root.classList.toggle("is-dialog-paused", Boolean(openDialog));
    };
    dialogObserver = new MutationObserver(update);
    document.querySelectorAll("dialog").forEach((dialog) => {
      dialogObserver.observe(dialog, { attributes: true, attributeFilter: ["open"] });
      dialog.addEventListener("close", () => window.setTimeout(update, 0));
    });
    update();
  }

  async function initialize() {
    const startButton = document.getElementById("tutorialButton");
    if (startButton) startButton.addEventListener("click", start);
    if (isMobileViewport()) {
      if (state) {
        await cleanup();
        state = null;
        localStorage.removeItem(STATE_KEY);
        localStorage.removeItem(ACTIVE_ID_KEY);
      }
      return;
    }
    if (state) {
      render();
      return;
    }
    if (routePath() !== "/" || localStorage.getItem(COMPLETED_KEY)) return;
    try {
      const response = await fetch("/api/tutorial/status", { headers: headers(), cache: "no-store" });
      const payload = await response.json();
      if (response.ok && payload.is_new_user) start();
    } catch (_) {
      // A tutorial status failure must not block normal chat startup.
    }
  }

  window.WangcaiTutorial = {
    start,
    finish,
    activeId() {
      return state && validId(state.id) ? state.id : "";
    },
    isActive() {
      return Boolean(state);
    },
  };
  window.__wangcaiTutorialReady = new Promise((resolve) => {
    const run = () => initialize().finally(resolve);
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run, { once: true });
    else run();
  });
})();
