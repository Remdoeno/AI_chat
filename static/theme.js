(function () {
  const DEVICE_STORAGE_KEY = "qwen_device_id";
  const THEME_EVENT = "qwen-theme-change";

  function makeDeviceId() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return `dev_${window.crypto.randomUUID().replace(/-/g, "").slice(0, 24)}`;
    }
    return `dev_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 14)}`;
  }

  function ensureDeviceId() {
    try {
      let deviceId = localStorage.getItem(DEVICE_STORAGE_KEY);
      if (!deviceId) {
        deviceId = makeDeviceId();
        localStorage.setItem(DEVICE_STORAGE_KEY, deviceId);
      }
      return deviceId;
    } catch (_) {
      return "device_unavailable";
    }
  }

  function storageKey() {
    return `qwen_theme_${ensureDeviceId()}`;
  }

  function readTheme() {
    try {
      const saved = localStorage.getItem(storageKey());
      return saved === "dark" ? "dark" : "light";
    } catch (_) {
      return "light";
    }
  }

  function applyTheme(theme) {
    const normalized = theme === "dark" ? "dark" : "light";
    document.documentElement.dataset.theme = normalized;
    document.documentElement.style.colorScheme = normalized;
    window.dispatchEvent(new CustomEvent(THEME_EVENT, { detail: { theme: normalized } }));
    updateButtons(normalized);
  }

  function setTheme(theme) {
    const normalized = theme === "dark" ? "dark" : "light";
    try {
      localStorage.setItem(storageKey(), normalized);
    } catch (_) {
      // Theme is visual preference only; ignore storage failures.
    }
    applyTheme(normalized);
  }

  function updateButtons(theme) {
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
      const isDark = theme === "dark";
      button.setAttribute("aria-pressed", String(isDark));
      button.dataset.themeState = theme;
      const label = isDark ? "切换光明模式" : "切换黑暗模式";
      button.setAttribute("aria-label", label);
      button.title = label;
      const text = button.querySelector("[data-theme-toggle-text]");
      if (text) {
        text.textContent = isDark ? "光明模式" : "黑暗模式";
      } else {
        button.textContent = isDark ? "光明模式" : "黑暗模式";
      }
    });
  }

  window.QwenTheme = {
    get: readTheme,
    set: setTheme,
    toggle() {
      setTheme(readTheme() === "dark" ? "light" : "dark");
    },
  };

  applyTheme(readTheme());

  document.addEventListener("DOMContentLoaded", () => {
    updateButtons(readTheme());
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
      button.addEventListener("click", () => window.QwenTheme.toggle());
    });
  });
})();
