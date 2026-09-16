(() => {
  "use strict";
  const target = document.getElementById("memberHint");
  if (!target) return;
  let generation = 0;
  let signature = "";
  let saving = false;
  const node = (tag, text, className) => {
    const el = document.createElement(tag); el.textContent = text;
    if (className) el.className = className;
    return el;
  };
  async function request(action) {
    const response = await fetch(action ? "/api/memberships/preferences" : "/api/memberships", {
      ...(action ? { method: "POST", body: JSON.stringify({ action }) } : {}),
      headers: WangcaiDeviceIdentity.jsonHeaders(),
    });
    if (!response.ok) { const error = new Error("提示设置未保存，请重试"); error.status = response.status; throw error; }
    return response.json();
  }
  const button = (text, action) => {
    const el = node("button", text); el.type = "button";
    el.onclick = async () => {
      el.disabled = true; saving = true; const current = ++generation;
      try { const data = await request(action); if (current === generation) render(data); }
      catch (_) { if (current === generation) { target.querySelector(".member-hint-error")?.remove(); target.append(node("p", "设置未保存，请重试", "member-hint-error")); } }
      finally { el.disabled = false; saving = false; }
    };
    return el;
  };
  function render(data) {
    const next = JSON.stringify([data.owner, data.preferences, data.hint]);
    if (signature === next) return;
    signature = next; target.replaceChildren();
    target.hidden = !data.hint;
    if (!data.hint) return;
    const top = node("div", "", "member-hint-top");
    const link = node("a", "查看卡包"); link.href = "/memberships";
    const collapsed = Boolean(data.preferences.collapsed);
    const toggle = button(collapsed ? "展开" : "收起", collapsed ? "expand" : "collapse");
    toggle.setAttribute("aria-expanded", String(!collapsed));
    const close = button("×", "dismiss_today");
    close.className = "member-hint-close";
    close.setAttribute("aria-label", "关闭提示，明天再显示");
    close.title = "今天不再显示，明天再提醒";
    top.append(node("span", "▤ 会员卡 · 今日轻提示", "member-hint-label"), link, toggle, close); target.append(top);
    if (!collapsed) {
      const text = node("p", data.hint.text, "member-hint-text"); text.title = data.hint.text;
      const foot = node("div", "", "member-hint-foot");
      foot.append(node("span", "每天换一张，有需要时再用"), button("一个月后再提醒", "snooze"));
      target.append(text, foot);
    }
  }
  async function refresh(clear = false) {
    if (saving && !clear) return;
    const current = ++generation;
    if (clear) { target.hidden = true; target.replaceChildren(); signature = ""; }
    try { const data = await request(); if (current === generation) render(data); }
    catch (_) { if (current === generation) { target.hidden = true; signature = ""; } }
  }
  window.addEventListener("wangcai-binding-changed", () => refresh(true));
  window.addEventListener("wangcai-conversation-started", () => refresh());
  window.addEventListener("storage", (event) => { if (event.key?.includes("binding")) refresh(true); });
  window.addEventListener("focus", () => refresh());
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
  setInterval(() => { if (!document.hidden) refresh(); }, 60000);
  refresh();
})();
