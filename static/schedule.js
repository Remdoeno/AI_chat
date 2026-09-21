(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  let snapshot = null;
  let calendarMode = "project";
  let detailProject = null;
  let selectedDate = "";
  let editing = null;
  let loading = false;
  let sending = false;
  let pendingChat = null;
  let pendingEdit = null;
  let previousOwner = "";
  const fields = ["title", "date", "time", "end_date", "end_time", "category", "status", "location", "notes", "repeat"];
  const progressEditor = ScheduleProgress.initEditor($("eventForm"));
  const requestId = () => `schedule-${crypto.randomUUID ? crypto.randomUUID() : Date.now() + "-" + Math.random().toString(36).slice(2)}`;
  const node = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  };
  const button = (text, action, className = "") => {
    const element = node("button", className, text);
    element.type = "button";
    element.addEventListener("click", action);
    return element;
  };
  const dateObject = (value) => new Date(`${value}T12:00:00+08:00`);
  const isWeekend = (day) => [0, 6].includes(dateObject(day).getUTCDay());
  const dateLabel = (value, options) => dateObject(value).toLocaleDateString("zh-CN", { timeZone: "Asia/Shanghai", ...options });
  const addDays = (value, count) => new Date(dateObject(value).getTime() + count * 86400000).toLocaleDateString("sv-SE", { timeZone: "Asia/Shanghai" });
  const occurs = (event, day) => (event.date && event.date <= day && (event.end_date || event.date) >= day) || (event.kind === "project" && event.milestones?.some(s => s.date === day));
  const eventsFor = (day) => snapshot.items.filter((event) => occurs(event, day)).sort((a, b) => (a.time || "99").localeCompare(b.time || "99"));
  const holidayFor = (day) => snapshot.holidays?.days.find((item) => item.date === day);
  function holidayBadge(day, compact = false) {
    const item = holidayFor(day);
    if (!item || item.kind === "workday") return null;
    const short = { holiday: "休", makeup: "班", weekend: "周末", unknown: "待定" }[item.kind];
    const badge = node("span", `holiday-badge ${item.kind}`, compact ? short : [item.name, item.label].filter(Boolean).join(" · "));
    badge.title = [item.name, item.label, item.stale ? "同步异常或缓存较旧，请核对公告" : ""].filter(Boolean).join(" · ");
    return badge;
  }
  function renderHolidayStatus() {
    const target = $("holidayStatus");
    target.replaceChildren();
    const data = snapshot.holidays;
    if (!data) return;
    target.append(node("p", "", data.sync_schedule + "。"));
    data.years.forEach((year) => {
      const state = { published: "已收录公告", pending: "待公布或收录", unavailable: "尚未同步成功" }[year.state];
      const checked = year.checked_at ? new Date(year.checked_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false }) : "暂无";
      target.append(node("p", year.stale ? "holiday-warning" : "", `${year.year}年：${state}；最近成功检查 ${checked}${year.stale ? "；同步异常或缓存较旧，保留上次数据，请核对原文" : ""}`));
    });
    const links = node("p", "holiday-links");
    [data.provider, ...data.papers].forEach((url, index) => {
      const link = node("a", "", index === 0 ? "数据渠道：holiday-cn" : `国务院公告原文 ${index}`);
      link.href = url; link.target = "_blank"; link.rel = "noopener noreferrer"; links.append(link);
    });
    target.append(links, node("p", "", data.scope + "，不会自动改动已约好的事项。"));
  }
  function notice(message, binding = false) {
    const target = $("pageStatus");
    target.replaceChildren(document.createTextNode(message));
    if (binding) {
      const link = node("a", "", " 返回首页绑定用户");
      link.href = "/";
      target.append(link);
    }
    target.hidden = !message;
  }
  async function api(path, options = {}) {
    const response = await window.fetch(path, {
      ...options,
      headers: WangcaiDeviceIdentity.headers({ "Content-Type": "application/json", ...(options.headers || {}) }),
    });
    const data = await response.json();
    if (!response.ok) {
      const binding = data.detail === "shared user binding required";
      const error = new Error(binding ? "先绑定用户，才能保存和同步你的日程。" : typeof data.detail === "string" ? data.detail : "操作失败，请检查填写内容后重试。");
      error.binding = binding;
      error.status = response.status;
      throw error;
    }
    return data;
  }
  function eventCard(event, day = selectedDate) {
    const category = snapshot.categories.find((item) => item.id === event.category);
    const card = button("", () => event.kind === "project" ? openProject(event) : openEvent(event), `event-card ${event.status}`);
    card.style.setProperty("--event-color", event.kind === "project" ? ScheduleProgress.color(event) : category?.color || "#77818e");
    const time = event.kind === "project" ? "长期事项" : event.time ? `${event.time}${event.end_time ? " – " + event.end_time : ""}` : "时间待定";
    card.append(node("span", "event-time", time), node("span", "event-title", event.title));
    if (event.kind === "project") card.append(ScheduleProgress.summary(event, day));
    if (event.end_date && event.end_date !== event.date) card.append(node("span", "event-meta", `${event.date.slice(5)} 至 ${event.end_date.slice(5)}`));
    if (event.location) card.append(node("span", "event-meta", `⌖ ${event.location}`));
    card.append(node("span", "event-status", `${category?.label || "其他"} · ${event.status === "confirmed" ? "已确定" : "待确认"}${event.repeat === "weekly" ? " · 每周" : ""}`));
    card.title = `${event.title}\n${event.date || "日期待定"} ${time}\n${event.notes || ""}`;
    return card;
  }
  function selectDay(day) { selectedDate = day; renderAgenda(); $("mobileAgenda").scrollIntoView({ behavior: "smooth", block: "nearest" }); }
  function renderAgenda() {
    const agenda = $("mobileAgenda");
    agenda.replaceChildren();
    const heading = node("div", "agenda-heading");
    heading.append(node("h2", isWeekend(selectedDate) ? "weekend-date" : "", dateLabel(selectedDate, { month: "long", day: "numeric", weekday: "long" })), button("＋ 添加", () => openEvent(null, selectedDate)));
    agenda.append(heading);
    const holiday = holidayBadge(selectedDate);
    if (holiday) { holiday.classList.add("agenda-holiday"); agenda.append(holiday); }
    const events = eventsFor(selectedDate);
    const agendaCards = calendarMode === "single"
      ? [...events.filter(e => e.kind !== "project").map(e => eventCard(e)), ...ScheduleProgress.activeNodes(snapshot.items, selectedDate).map(item => ScheduleProgress.nodeCard(item, openProject))]
      : events.map(e => eventCard(e));
    if (agendaCards.length) agenda.append(...agendaCards);
    else agenda.append(node("p", "mobile-empty", "这一天还没有安排，留一点自由时间。"));
    $("calendarGrid").querySelectorAll(".day-cell").forEach(cell => cell.classList.toggle("selected-day", cell.dataset.date === selectedDate));
    $("dateStrip").querySelectorAll("button").forEach((element) => element.setAttribute("aria-pressed", String(element.dataset.date === selectedDate)));
  }
  function render() {
    $("dateRange").textContent = `${dateLabel(snapshot.today, { year: "numeric", month: "long", day: "numeric" })} — ${dateLabel(snapshot.end, { month: "long", day: "numeric" })} · 北京时间`;
    const confirmed = snapshot.items.filter((event) => event.status === "confirmed").length;
    $("eventCount").textContent = `${confirmed} 已确定 · ${snapshot.items.length - confirmed} 待确认`;
    $("calendarGrid").replaceChildren();
    $("calendarGrid").classList.toggle("single-mode", calendarMode === "single");
    $("projectMode").setAttribute("aria-pressed", String(calendarMode === "project"));
    $("singleMode").setAttribute("aria-pressed", String(calendarMode === "single"));
    $("modeHint").textContent = calendarMode === "project" ? "展开长条查看阶段与重要节点" : "同色节点属于同一项目，细曲线连接阶段顺序";
    $("dateStrip").replaceChildren();
    for (let index = 0; index < 14; index += 1) {
      const day = addDays(snapshot.today, index);
      const events = eventsFor(day);
      const cell = node("section", `day-cell${index === 0 ? " today" : ""}${isWeekend(day) ? " is-weekend" : ""}`);
      cell.dataset.date = day;
      const heading = node("div", "day-heading");
      heading.append(node("span", "", dateLabel(day, { weekday: "short" })), button(day.slice(8).replace(/^0/, ""), () => selectDay(day), "day-number"), node("span", "", index === 0 ? "今天" : day.slice(5, 7) + "月"));
      const holiday = holidayBadge(day);
      if (holiday) heading.append(holiday);
      cell.append(heading);
      events.filter(event => event.kind !== "project").forEach((event) => cell.append(eventCard(event, day)));
      if (calendarMode === "single") ScheduleProgress.singleNodes(snapshot.items, day, snapshot.today).forEach(item => cell.append(ScheduleProgress.nodeCard(item, openProject)));
      if (!events.length) cell.append(node("p", "day-empty", "—"));
      $("calendarGrid").append(cell);
      const tab = button("", () => { selectedDate = day; renderAgenda(); }, `date-button${index === 0 ? " is-today" : ""}${isWeekend(day) ? " is-weekend" : ""}`);
      tab.dataset.date = day;
      tab.setAttribute("aria-label", dateLabel(day, { month: "long", day: "numeric", weekday: "long" }) + `，${events.length}件事项`);
      tab.append(node("span", "", index === 0 ? "今天" : dateLabel(day, { weekday: "short" })), node("strong", "", day.slice(8).replace(/^0/, "")));
      const compactHoliday = holidayBadge(day, true);
      if (compactHoliday) {
        tab.append(compactHoliday);
        tab.setAttribute("aria-label", tab.getAttribute("aria-label") + "，" + compactHoliday.title);
      }
      const dots = node("span", "date-dots");
      events.slice(0, 3).forEach(() => dots.append(node("i")));
      tab.append(dots);
      $("dateStrip").append(tab);
    }
    $("undatedEvents").replaceChildren();
    const undated = snapshot.items.filter((event) => !event.date && (calendarMode !== "single" || event.kind !== "project" || !event.milestones?.length));
    if (undated.length) undated.forEach((event) => $("undatedEvents").append(eventCard(event)));
    if (calendarMode === "single") ScheduleProgress.undatedNodes(snapshot.items).forEach(item => $("undatedEvents").append(ScheduleProgress.nodeCard(item, openProject)));
    if (!$("undatedEvents").children.length) $("undatedEvents").append(node("p", "empty-note", "暂无日期待定的事项"));
    $("categoryLegend").replaceChildren();
    $("categorySelect").replaceChildren();
    snapshot.categories.forEach((category) => {
      const legend = node("span", "legend-category");
      legend.style.setProperty("--event-color", category.color);
      legend.append(node("i", "legend-dot"), document.createTextNode(category.label));
      $("categoryLegend").append(legend);
      const option = node("option", "", category.label);
      option.value = category.id;
      $("categorySelect").append(option);
    });
    ScheduleProgress.timeline($("projectTimeline"), snapshot, openProject, selectDay, addDays);
    if (calendarMode === "single") $("projectTimeline").hidden = true;
    ScheduleConnections.schedule($("calendarGrid"));
    renderHolidayStatus();
    renderAgenda();
  }
  async function refresh() {
    if (loading || $("eventDialog").open || $("projectDialog").open) return;
    loading = true;
    $("refreshButton").disabled = true;
    try {
      const data = await api("/api/schedule");
      if (previousOwner && previousOwner !== data.owner) {
        $("chatMessages").replaceChildren(node("div", "bubble assistant", "已切换用户，日程已同步。"));
        pendingChat = null;
        $("chatInput").value = "";
      }
      previousOwner = data.owner;
      snapshot = data;
      try { calendarMode = localStorage.getItem(`wangcai-calendar-mode:${data.owner}`) === "single" ? "single" : "project"; } catch (_) { calendarMode = "project"; }
      if (!selectedDate || selectedDate < data.today || selectedDate > data.end) selectedDate = data.today;
      render();
      $("addEvent").disabled = false;
      $("sendChat").disabled = sending;
      notice("");
    } catch (error) {
      notice(error.message, error.binding);
      if (error.binding) {
        snapshot = null;
        $("projectTimeline").replaceChildren();
        $("calendarGrid").replaceChildren(); $("dateStrip").replaceChildren();
        $("mobileAgenda").replaceChildren(); $("undatedEvents").replaceChildren();
        $("chatMessages").replaceChildren();
        $("eventCount").textContent = "";
        $("dateRange").textContent = "绑定后查看未来两周的安排";
        $("addEvent").disabled = true; $("sendChat").disabled = true;
      }
    } finally { loading = false; $("refreshButton").disabled = false; }
  }
  function openProject(project, focusId = "") {
    detailProject = project;
    $("projectTitle").textContent = project.title;
    $("projectDetails").replaceChildren(ScheduleProgress.details(project, focusId));
    $("projectDialog").showModal();
    if (focusId) requestAnimationFrame(() => $("projectDetails").querySelector(".phase-focus")?.scrollIntoView({ block: "nearest" }));
  }
  function setMode(mode) {
    if (!snapshot) return;
    calendarMode = mode;
    try { localStorage.setItem(`wangcai-calendar-mode:${snapshot.owner}`, mode); } catch (_) {}
    render();
  }
  $("projectMode").addEventListener("click", () => setMode("project"));
  $("singleMode").addEventListener("click", () => setMode("single"));
  $("closeProject").addEventListener("click", () => $("projectDialog").close());
  $("editProject").addEventListener("click", () => { $("projectDialog").close(); if (detailProject) openEvent(detailProject); });
  function openEvent(event, day = "") {
    if (!snapshot) return;
    editing = event;
    pendingEdit = null;
    $("eventForm").reset();
    fields.forEach((field) => { $("eventForm").elements[field].value = event?.[field] || (field === "status" ? "tentative" : field === "category" ? "other" : field === "repeat" ? "none" : ""); });
    progressEditor.load(event);
    if (event?.series_date) {
      $("eventForm").elements.date.value = event.series_date;
      if (event.end_date) $("eventForm").elements.end_date.value = event.series_date;
    }
    if (!event && day) $("eventForm").elements.date.value = day;
    $("eventDialogTitle").textContent = event?.repeat === "weekly" ? "修改每周系列" : event ? "查看与修改事项" : "新建事项";
    $("deleteEvent").hidden = !event;
    $("formStatus").textContent = "";
    $("eventDialog").showModal();
  }
  async function save(operation) {
    $("saveEvent").disabled = true; $("deleteEvent").disabled = true;
    const signature = JSON.stringify(operation);
    if (!pendingEdit || pendingEdit.signature !== signature) pendingEdit = { signature, request_id: requestId() };
    try {
      await api("/api/schedule/events", { method: "POST", body: JSON.stringify({ operation, request_id: pendingEdit.request_id }) });
      pendingEdit = null;
      $("eventDialog").close();
      await refresh();
    } catch (error) {
      $("formStatus").textContent = error.message;
      if (error.status) pendingEdit = null;
    } finally { $("saveEvent").disabled = false; $("deleteEvent").disabled = false; }
  }
  $("eventForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const data = Object.fromEntries(fields.map((field) => [field, $("eventForm").elements[field].value]));
    Object.assign(data, progressEditor.read());
    save({ action: editing ? "update" : "create", ...(editing ? { id: editing.id, revision: editing.revision } : {}), event: data });
  });
  $("deleteEvent").addEventListener("click", () => {
    if (editing && window.confirm(`删除“${editing.title}”${editing.repeat === "weekly" ? "的整个每周系列" : ""}？`)) save({ action: "delete", id: editing.id, revision: editing.revision });
  });
  $("closeDialog").addEventListener("click", () => $("eventDialog").close());
  $("addEvent").addEventListener("click", () => openEvent(null));
  $("refreshButton").addEventListener("click", refresh);
  $("todayButton").addEventListener("click", async () => { await refresh(); if (snapshot) { selectedDate = snapshot.today; renderAgenda(); } });
  document.querySelectorAll("[data-example]").forEach((element) => element.addEventListener("click", () => { $("chatInput").value = element.dataset.example; $("chatInput").focus(); }));
  function bubble(text, className) {
    $("chatMessages").append(node("div", `bubble ${className}`, text));
    $("chatMessages").scrollTop = $("chatMessages").scrollHeight;
  }
  $("scheduleChatForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = $("chatInput").value.trim();
    if (!message || sending) return;
    sending = true; $("sendChat").disabled = true; $("sendChat").textContent = "整理中…";
    if (!pendingChat || pendingChat.message !== message) {
      pendingChat = { message, request_id: requestId() };
      bubble(message, "user");
    }
    const submittedText = $("chatInput").value;
    $("chatInput").value = "";
    try {
      const result = await api("/api/schedule/chat", { method: "POST", body: JSON.stringify(pendingChat) });
      bubble(result.reply || "日程已核对。", "assistant");
      if (result.changes.length) {
        bubble(result.changes.map(({ action, event: item }) => `${action === "delete" ? "已删除" : item.status === "cancelled" ? "已取消" : "已保存"}：${item.title} · ${item.date || "日期待定"} ${item.time || "时间待定"}${action !== "delete" && item.status !== "cancelled" ? " · " + (item.status === "confirmed" ? "已确定" : "待确认") : ""}`).join("\n"), "assistant");
      }
      pendingChat = null;
      await refresh();
    } catch (error) {
      if (!$("chatInput").value) $("chatInput").value = submittedText;
      bubble(error.message + (error.status ? "" : " 网络未返回结果；再次发送相同内容会核对原请求，避免重复添加。"), "assistant error");
      if (error.binding) notice(error.message, true);
      if (error.status) pendingChat = null;
    } finally { sending = false; $("sendChat").disabled = !snapshot; $("sendChat").textContent = "发送 ↑"; }
  });
  window.addEventListener("focus", () => { if (!sending) refresh(); });
  document.addEventListener("visibilitychange", () => { if (!document.hidden && !sending) refresh(); });
  window.setInterval(() => { if (!document.hidden && !sending) refresh(); }, 60000);
  $("addEvent").disabled = true;
  refresh();
})();
