(function () {
  const DEVICE_STORAGE_KEY = "wangcai_device_id";
  const LEGACY_DEVICE_STORAGE_KEY = "qwen_device_id";
  const TUTORIAL_STORAGE_KEY = "wangcai_tutorial_active_id";

  function validDeviceId(value) {
    return /^[A-Za-z0-9_-]{12,96}$/.test(String(value || "").trim());
  }

  function createDeviceId() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return `dev_${window.crypto.randomUUID().replace(/-/g, "").slice(0, 24)}`;
    }
    return `dev_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 18)}`;
  }

  function ensureDeviceId() {
    let deviceId = "";
    try {
      deviceId = localStorage.getItem(DEVICE_STORAGE_KEY) || "";
      if (!validDeviceId(deviceId)) {
        const legacyId = localStorage.getItem(LEGACY_DEVICE_STORAGE_KEY) || "";
        deviceId = validDeviceId(legacyId) ? legacyId : createDeviceId();
        localStorage.setItem(DEVICE_STORAGE_KEY, deviceId);
        localStorage.removeItem(LEGACY_DEVICE_STORAGE_KEY);
      }
    } catch (_) {
      deviceId = createDeviceId();
    }
    return deviceId;
  }

  function headers(extra = {}) {
    const result = { ...extra, "X-Wangcai-Device-Id": ensureDeviceId() };
    try {
      const tutorialId = String(localStorage.getItem(TUTORIAL_STORAGE_KEY) || "").trim();
      if (validDeviceId(tutorialId)) result["X-Wangcai-Tutorial-Id"] = tutorialId;
    } catch (_) {
      // Tutorial headers are optional when localStorage is unavailable.
    }
    return result;
  }

  window.WangcaiDeviceIdentity = {
    ensureDeviceId,
    headers,
    jsonHeaders() {
      return headers({ "Content-Type": "application/json" });
    },
  };
})();
