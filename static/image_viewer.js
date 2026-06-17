(function () {
  if (window.__wangcaiImageViewerInstalled) return;
  window.__wangcaiImageViewerInstalled = true;

  const STYLE_ID = "wangcai-image-viewer-style";
  const MIN_SCALE = 0.25;
  const MAX_SCALE = 8;
  const ZOOM_STEP = 1.2;

  function injectStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      .wangcai-image-viewer {
        position: fixed;
        inset: 0;
        z-index: 2147483000;
        width: 100vw;
        height: 100vh;
        height: 100dvh;
        max-width: none;
        max-height: none;
        margin: 0;
        padding: 0;
        border: 0;
        display: none;
        align-items: center;
        justify-content: center;
        background: rgba(3, 5, 10, 0.92);
        color: #fff;
        user-select: none;
      }
      .wangcai-image-viewer::backdrop {
        background: transparent;
      }
      .wangcai-image-viewer.is-open {
        display: flex;
      }
      .wangcai-image-viewer-stage {
        position: absolute;
        inset: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;
        cursor: zoom-in;
      }
      .wangcai-image-viewer-stage.is-draggable {
        cursor: grab;
      }
      .wangcai-image-viewer-stage.is-dragging {
        cursor: grabbing;
      }
      .wangcai-image-viewer-image {
        display: block;
        max-width: 92vw;
        max-height: 88vh;
        border-radius: 8px;
        box-shadow: 0 24px 80px rgba(0, 0, 0, 0.55);
        transform-origin: center center;
        will-change: transform;
        -webkit-user-drag: none;
      }
      .wangcai-image-viewer-close,
      .wangcai-image-viewer-button {
        border: 1px solid rgba(255, 255, 255, 0.22);
        background: rgba(16, 20, 28, 0.78);
        color: #fff;
        font: 800 16px/1 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        cursor: pointer;
        backdrop-filter: blur(12px);
      }
      .wangcai-image-viewer-close {
        position: fixed;
        top: max(14px, env(safe-area-inset-top));
        right: max(14px, env(safe-area-inset-right));
        z-index: 2;
        width: 42px;
        height: 42px;
        border-radius: 50%;
      }
      .wangcai-image-viewer-toolbar {
        position: fixed;
        left: 50%;
        bottom: max(18px, env(safe-area-inset-bottom));
        z-index: 2;
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 8px;
        border: 1px solid rgba(255, 255, 255, 0.16);
        border-radius: 999px;
        background: rgba(8, 11, 18, 0.64);
        transform: translateX(-50%);
        backdrop-filter: blur(14px);
      }
      .wangcai-image-viewer-button {
        min-width: 42px;
        height: 38px;
        border-radius: 999px;
        padding: 0 12px;
      }
      .wangcai-image-viewer-scale {
        min-width: 56px;
        color: rgba(255, 255, 255, 0.86);
        font: 800 13px/1 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        text-align: center;
      }
      body.wangcai-image-viewer-lock {
        overflow: hidden !important;
      }
      img[data-wangcai-image-viewer-ready="true"] {
        cursor: zoom-in;
      }
      @media (max-width: 640px) {
        .wangcai-image-viewer-image {
          max-width: 96vw;
          max-height: 86vh;
          border-radius: 6px;
        }
        .wangcai-image-viewer-toolbar {
          bottom: max(10px, env(safe-area-inset-bottom));
        }
      }
    `;
    document.head.append(style);
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function imageSource(image) {
    return image.currentSrc || image.src || image.getAttribute("src") || "";
  }

  function isEligibleImage(target) {
    if (!target || target.tagName !== "IMG") return false;
    if (target.closest(".wangcai-image-viewer")) return false;
    if (target.closest(".artifact-card, .character-card")) return false;
    if (target.dataset.imageViewerIgnore === "true") return false;
    const src = imageSource(target);
    return Boolean(src && !src.startsWith("blob:null"));
  }

  const state = {
    overlay: null,
    stage: null,
    image: null,
    scaleText: null,
    scale: 1,
    offsetX: 0,
    offsetY: 0,
    dragging: false,
    dragStartX: 0,
    dragStartY: 0,
    dragOriginX: 0,
    dragOriginY: 0,
  };

  function ensureViewer() {
    if (state.overlay) return state.overlay;
    injectStyle();

    const overlay = document.createElement("dialog");
    overlay.className = "wangcai-image-viewer";
    overlay.setAttribute("aria-label", "图片预览");

    const stage = document.createElement("div");
    stage.className = "wangcai-image-viewer-stage";
    const image = document.createElement("img");
    image.className = "wangcai-image-viewer-image";
    image.draggable = false;
    stage.append(image);

    const close = document.createElement("button");
    close.type = "button";
    close.className = "wangcai-image-viewer-close";
    close.textContent = "X";
    close.setAttribute("aria-label", "关闭图片预览");

    const toolbar = document.createElement("div");
    toolbar.className = "wangcai-image-viewer-toolbar";
    const zoomOut = document.createElement("button");
    zoomOut.type = "button";
    zoomOut.className = "wangcai-image-viewer-button";
    zoomOut.textContent = "-";
    zoomOut.setAttribute("aria-label", "缩小");
    const scaleText = document.createElement("span");
    scaleText.className = "wangcai-image-viewer-scale";
    const zoomIn = document.createElement("button");
    zoomIn.type = "button";
    zoomIn.className = "wangcai-image-viewer-button";
    zoomIn.textContent = "+";
    zoomIn.setAttribute("aria-label", "放大");
    const reset = document.createElement("button");
    reset.type = "button";
    reset.className = "wangcai-image-viewer-button";
    reset.textContent = "1:1";
    reset.setAttribute("aria-label", "重置缩放");
    toolbar.append(zoomOut, scaleText, zoomIn, reset);

    overlay.append(stage, close, toolbar);
    document.body.append(overlay);

    overlay.addEventListener("cancel", (event) => {
      event.preventDefault();
      closeViewer();
    });
    close.addEventListener("click", closeViewer);
    zoomOut.addEventListener("click", () => zoomBy(1 / ZOOM_STEP));
    zoomIn.addEventListener("click", () => zoomBy(ZOOM_STEP));
    reset.addEventListener("click", resetTransform);
    stage.addEventListener("click", (event) => {
      if (event.target === stage) closeViewer();
    });
    image.addEventListener("dblclick", () => {
      if (state.scale === 1) {
        setScale(2);
      } else {
        resetTransform();
      }
    });
    overlay.addEventListener("wheel", handleWheel, { passive: false });
    stage.addEventListener("pointerdown", startDrag);
    window.addEventListener("pointermove", drag);
    window.addEventListener("pointerup", endDrag);

    state.overlay = overlay;
    state.stage = stage;
    state.image = image;
    state.scaleText = scaleText;
    return overlay;
  }

  function updateTransform() {
    if (!state.image) return;
    state.image.style.transform = `translate(${state.offsetX}px, ${state.offsetY}px) scale(${state.scale})`;
    state.scaleText.textContent = `${Math.round(state.scale * 100)}%`;
    state.stage.classList.toggle("is-draggable", state.scale > 1);
  }

  function resetTransform() {
    state.scale = 1;
    state.offsetX = 0;
    state.offsetY = 0;
    updateTransform();
  }

  function setScale(nextScale) {
    state.scale = clamp(nextScale, MIN_SCALE, MAX_SCALE);
    if (state.scale <= 1) {
      state.offsetX = 0;
      state.offsetY = 0;
    }
    updateTransform();
  }

  function zoomBy(multiplier) {
    setScale(state.scale * multiplier);
  }

  function handleWheel(event) {
    event.preventDefault();
    zoomBy(event.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP);
  }

  function startDrag(event) {
    if (event.target !== state.image || state.scale <= 1) return;
    state.dragging = true;
    state.dragStartX = event.clientX;
    state.dragStartY = event.clientY;
    state.dragOriginX = state.offsetX;
    state.dragOriginY = state.offsetY;
    state.stage.classList.add("is-dragging");
    event.preventDefault();
  }

  function drag(event) {
    if (!state.dragging) return;
    state.offsetX = state.dragOriginX + event.clientX - state.dragStartX;
    state.offsetY = state.dragOriginY + event.clientY - state.dragStartY;
    updateTransform();
  }

  function endDrag() {
    if (!state.dragging) return;
    state.dragging = false;
    state.stage.classList.remove("is-dragging");
  }

  function openViewer(sourceImage) {
    const overlay = ensureViewer();
    const src = imageSource(sourceImage);
    if (!src) return;
    state.image.src = src;
    state.image.alt = sourceImage.alt || "图片预览";
    resetTransform();
    if (typeof overlay.showModal === "function" && !overlay.open) {
      try {
        overlay.showModal();
      } catch {
        // Fallback to the fixed overlay styling if the browser rejects a nested modal.
      }
    }
    overlay.classList.add("is-open");
    document.body.classList.add("wangcai-image-viewer-lock");
  }

  function closeViewer() {
    if (!state.overlay) return;
    state.overlay.classList.remove("is-open");
    if (typeof state.overlay.close === "function" && state.overlay.open) {
      try {
        state.overlay.close();
      } catch {
        // The overlay may already be closed by a native dialog action.
      }
    }
    document.body.classList.remove("wangcai-image-viewer-lock");
    endDrag();
    state.image.removeAttribute("src");
  }

  document.addEventListener(
    "click",
    (event) => {
      const image = event.target;
      if (!isEligibleImage(image)) return;
      event.preventDefault();
      event.stopPropagation();
      openViewer(image);
    },
    true,
  );

  document.addEventListener("keydown", (event) => {
    if (!state.overlay || !state.overlay.classList.contains("is-open")) return;
    if (event.key === "Escape") {
      event.preventDefault();
      closeViewer();
    } else if (event.key === "+" || event.key === "=") {
      event.preventDefault();
      zoomBy(ZOOM_STEP);
    } else if (event.key === "-" || event.key === "_") {
      event.preventDefault();
      zoomBy(1 / ZOOM_STEP);
    } else if (event.key === "0") {
      event.preventDefault();
      resetTransform();
    }
  });

  document.addEventListener("mouseover", (event) => {
    if (isEligibleImage(event.target)) {
      event.target.dataset.wangcaiImageViewerReady = "true";
    }
  });
})();
