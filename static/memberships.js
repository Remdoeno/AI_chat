(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const fields = ["name", "balance", "balance_note", "remaining_uses", "location", "expires_on", "status", "notes", "reminder_enabled"];
  const labels = { active: "待使用", issue: "使用问题待处理", used_up: "已用完" };
  let data = null, editing = null, sending = false, saving = false, loading = false, pendingChat = null, pendingEdit = null;
  const id = () => "card-" + (crypto.randomUUID ? crypto.randomUUID() : Date.now() + "-" + Math.random().toString(36).slice(2));
  const node = (tag, text = "", className = "") => { const el = document.createElement(tag); el.textContent = text; el.className = className; return el; };
  const button = (text, action) => { const el = node("button", text); el.type = "button"; el.onclick = action; return el; };
  function notice(text) { $("pageStatus").textContent = text; $("pageStatus").hidden = !text; }
  async function api(path, payload) {
    const response = await fetch(path, { headers: WangcaiDeviceIdentity.jsonHeaders(), ...(payload ? { method: "POST", body: JSON.stringify(payload) } : {}) });
    const result = await response.json();
    if (!response.ok) { const error = new Error(result.detail === "shared user binding required" ? "请先返回首页绑定用户，再使用会员卡包。" : typeof result.detail === "string" ? result.detail : "操作失败，请检查内容后重试。"); error.status = response.status; error.binding = result.detail === "shared user binding required"; throw error; }
    return result;
  }
  function render() {
    $("walletCards").replaceChildren();
    const active = data.cards.filter((card) => card.status !== "used_up");
    $("cardCount").textContent = `${active.length} 张待使用 · 共 ${data.cards.length} 张`;
    const paused = data.preferences.snooze_until && data.preferences.snooze_until > data.today;
    const dismissedToday = data.preferences.dismissed_on === data.today;
    $("hintState").textContent = paused ? `首页提示已延后至 ${data.preferences.snooze_until}` : dismissedToday ? "今日提示已关闭，明天恢复" : "首页每日轮换一张，不插入聊天";
    $("resumeHint").hidden = !paused && !dismissedToday;
    if (!data.cards.length) $("walletCards").append(node("p", "卡包还是空的。添加一张，或告诉旺财你有哪些会员卡。", "wallet-empty"));
    data.cards.forEach((card) => {
      const tile = node("article", "", "wallet-card " + card.status);
      const head = node("div", "", "wallet-card-header"); head.append(node("h2", card.name), node("span", labels[card.status], "wallet-badge"));
      const money = card.balance ? `¥ ${card.balance}` : card.balance_note || "余额待核实";
      tile.append(head, node("p", money + (card.remaining_uses ? ` · ${card.remaining_uses} 次` : ""), "wallet-balance"));
      if (card.balance && card.balance_note) tile.append(node("p", card.balance_note, "wallet-meta"));
      tile.append(node("p", "地点：" + (card.location || "待补充"), "wallet-meta"), node("p", "有效期：" + (card.expires_on || "未知"), "wallet-meta"));
      if (card.notes) tile.append(node("p", card.notes, "wallet-meta"));
      tile.append(node("p", card.status === "used_up" ? "已停止提醒；金额和次数保留为历史记录" : card.reminder_enabled ? "参与首页每日轮换" : "这张卡的提示已暂停", "wallet-meta"));
      const actions = node("div", "", "wallet-actions"); actions.append(button("查看 / 编辑", () => open(card)));
      if (card.status !== "used_up") {
        actions.append(button(card.reminder_enabled ? "暂停提示" : "恢复提示", () => mutate({ action: "update", id: card.id, revision: card.revision, card: { reminder_enabled: !card.reminder_enabled } })));
        actions.append(button("已用完", () => { if (confirm(`将“${card.name}”标为已用完并停止提醒？`)) mutate({ action: "update", id: card.id, revision: card.revision, card: { status: "used_up" } }); }));
      }
      tile.append(actions); $("walletCards").append(tile);
    });
  }
  async function refresh() {
    if (loading || $("cardDialog").open) return;
    loading = true;
    try {
      const next = await api("/api/memberships");
      if (data && next.owner !== data.owner) { $("cardChatMessages").replaceChildren(); $("cardChatInput").value = ""; pendingChat = null; }
      data = next; render(); notice(""); $("newCard").disabled = false; $("sendCardChat").disabled = sending;
    } catch (error) {
      notice(error.message);
      if (error.binding) { data = null; pendingChat = null; $("walletCards").replaceChildren(); $("cardChatMessages").replaceChildren(); $("cardCount").textContent = "请先绑定用户"; $("newCard").disabled = true; $("sendCardChat").disabled = true; }
    } finally { loading = false; }
  }
  function open(card = null) {
    if (!data || saving) return;
    editing = card; pendingEdit = null; $("cardForm").reset();
    fields.forEach((field) => { $("cardForm").elements[field].value = card ? String(card[field]) : field === "status" ? "active" : field === "reminder_enabled" ? "true" : ""; });
    $("cardDialogTitle").textContent = card ? "查看与修改会员卡" : "添加会员卡"; $("deleteCard").hidden = !card; $("cardFormStatus").textContent = ""; $("cardDialog").showModal(); cardGuard.markClean();
  }
  async function mutate(operation) {
    if (saving) return;
    saving = true; $("saveCard").disabled = true; $("deleteCard").disabled = true;
    const signature = JSON.stringify(operation);
    if (!pendingEdit || pendingEdit.signature !== signature) pendingEdit = { signature, payload: { operation, request_id: id() } };
    try {
      await api("/api/memberships/cards", pendingEdit.payload); pendingEdit = null; $("cardDialog").close(); await refresh();
    } catch (error) {
      if ($("cardDialog").open) $("cardFormStatus").textContent = error.message;
      else notice(error.message);
      if (error.status) pendingEdit = null;
    } finally { saving = false; $("saveCard").disabled = false; $("deleteCard").disabled = false; }
  }
  async function saveCardDraft() {
    if (!$("cardForm").reportValidity()) return;
    const card = Object.fromEntries(fields.map((key) => [key, key === "reminder_enabled" ? $("cardForm").elements[key].value === "true" : $("cardForm").elements[key].value]));
    await mutate({ action: editing ? "update" : "create", ...(editing ? { id: editing.id, revision: editing.revision } : {}), card });
  }
  const cardGuard = WangcaiDialogGuard.attach($("cardDialog"), {
    read: () => fields.map(key => [key, $("cardForm").elements[key].value]),
    save: saveCardDraft, discard: () => $("cardDialog").close(), busy: () => saving
  });
  $("cardForm").onsubmit = event => { event.preventDefault(); saveCardDraft(); };
  $("deleteCard").onclick = () => { if (editing && confirm(`删除“${editing.name}”及其关联记忆？`)) mutate({ action: "delete", id: editing.id, revision: editing.revision }); };
  $("closeCard").onclick = cardGuard.requestClose; $("newCard").onclick = () => open(); $("refreshCards").onclick = refresh;
  $("resumeHint").onclick = async () => { try { data = await api("/api/memberships/preferences", { action: "resume" }); render(); notice(""); } catch (error) { notice(error.message); } };
  function bubble(text, kind) { $("cardChatMessages").append(node("div", text, "bubble " + kind)); $("cardChatMessages").scrollTop = $("cardChatMessages").scrollHeight; }
  $("cardChatForm").onsubmit = async (event) => {
    event.preventDefault();
    const input = $("cardChatInput"); const raw = input.value, message = raw.trim();
    if (!message || sending || !data) return;
    sending = true; $("sendCardChat").disabled = true; $("sendCardChat").textContent = "整理中…";
    if (!pendingChat || pendingChat.message !== message) { pendingChat = { message, request_id: id() }; bubble(message, "user"); }
    input.value = "";
    try {
      const result = await api("/api/memberships/chat", pendingChat);
      bubble(result.reply || "卡包已核对。", "assistant");
      if (result.changes.length) bubble(result.changes.map((change) => `${change.action === "delete" ? "已删除" : "已保存"}：${change.card.name}`).join("\n"), "assistant");
      pendingChat = null; await refresh();
    } catch (error) {
      if (!input.value) input.value = raw;
      bubble(error.message + (error.status ? "" : " 网络未返回结果，再次发送同一内容可核对原请求。"), "assistant error");
      if (error.status) pendingChat = null;
    } finally { sending = false; $("sendCardChat").disabled = !data; $("sendCardChat").textContent = "发送 ↑"; }
  };
  window.addEventListener("focus", () => { if (!sending) refresh(); });
  document.addEventListener("visibilitychange", () => { if (!document.hidden && !sending) refresh(); });
  setInterval(() => { if (!document.hidden && !sending) refresh(); }, 60000);
  $("newCard").disabled = true; $("sendCardChat").disabled = true; refresh();
})();
