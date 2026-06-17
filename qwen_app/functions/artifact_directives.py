# Hidden artifact-theater directive layer. It turns chat instructions into
# background writing constraints without exposing a separate management UI.

ARTIFACT_DIRECTIVE_TRIGGER_HINTS = (
    "成果",
    "成果库",
    "小剧场",
    "后台写作",
    "后台创作",
    "故事里",
    "故事中",
    "后续故事",
    "以后出现在",
    "时不时出现",
    "偶尔出现",
    "下一篇",
    "下一集",
    "后续让",
    "别再写",
    "不要总是",
    "插入角色",
    "引导剧情",
)

ARTIFACT_DIRECTIVE_TYPES = {
    "character_include",
    "character_avoid",
    "plot_direction",
    "style_rule",
    "series_rule",
    "image_rule",
    "other",
}


def clean_artifact_directive_text(value: object, max_chars: int = 1400) -> str:
    return clean_search_text(str(value or ""), max_chars).strip()


def artifact_directive_key(directive_type: str, subject: str, series_title: str = "") -> str:
    raw = "|".join(
        [
            clean_artifact_directive_text(directive_type, 80).lower(),
            clean_artifact_directive_text(subject, 160).lower(),
            clean_artifact_directive_text(series_title, 160).lower(),
        ]
    )
    compact = re.sub(r"[\s\"'“”‘’《》<>【】\[\]（）()，,。.!！?？:：;；·\-_/\\]+", "", raw)
    if compact:
        return compact[:160]
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:48]


def normalize_directive_type(value: object) -> str:
    text = str(value or "other").strip().lower()
    return text if text in ARTIFACT_DIRECTIVE_TYPES else "other"


def normalize_directive_scope(value: object) -> str:
    text = str(value or "persistent").strip().lower()
    return text if text in {"persistent", "next_artifact"} else "persistent"


def normalize_directive_characters(value: object) -> List[str]:
    raw_items: List[object] = []
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str) and value.strip():
        raw_items = re.split(r"[,，、/|；;]\s*", value)
    result: List[str] = []
    seen = set()
    for item in raw_items:
        text = clean_artifact_directive_text(item, 80)
        key = character_name_key(text) if "character_name_key" in globals() else text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result[:12]


def normalize_artifact_directive_decision(payload: Dict[str, object]) -> Dict[str, object]:
    action = str(payload.get("action") or "noop").strip().lower()
    if action not in {"noop", "upsert"}:
        action = "noop"
    raw_directive = payload.get("directive")
    directive = raw_directive if isinstance(raw_directive, dict) else {}
    directive_type = normalize_directive_type(directive.get("directive_type"))
    subject = clean_artifact_directive_text(directive.get("subject"), 160)
    directive_text = clean_artifact_directive_text(directive.get("directive"), 1400)
    characters = normalize_directive_characters(directive.get("characters"))
    series_title = clean_artifact_directive_text(directive.get("series_title"), 160)
    try:
        priority = int(directive.get("priority") or 50)
    except Exception:
        priority = 50
    priority = max(1, min(100, priority))
    try:
        confidence = float(directive.get("confidence", 0.7))
    except Exception:
        confidence = 0.7
    confidence = max(0.0, min(1.0, confidence))
    if action == "upsert" and not directive_text:
        action = "noop"
    return {
        "action": action,
        "reason": clean_artifact_directive_text(payload.get("reason"), 500),
        "directive": {
            "directive_type": directive_type,
            "subject": subject,
            "directive": directive_text,
            "characters": characters,
            "series_title": series_title,
            "priority": priority,
            "scope": normalize_directive_scope(directive.get("scope")),
            "confidence": confidence,
        },
    }


def parse_artifact_directive_agent_json(text: str) -> Dict[str, object]:
    cleaned = str(text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    candidates = [cleaned]
    match = re.search(r"\{.*\}", cleaned, flags=re.S)
    if match:
        candidates.append(match.group(0))
    for candidate in candidates:
        try:
            payload = json.loads(candidate, strict=False)
        except Exception:
            continue
        if isinstance(payload, dict):
            return normalize_artifact_directive_decision(payload)
    return {"action": "noop", "reason": "invalid_json", "directive": {}}


def should_include_artifact_theater_context(message: str) -> bool:
    text = str(message or "").strip()
    if not text:
        return False
    if any(hint in text for hint in ARTIFACT_DIRECTIVE_TRIGGER_HINTS):
        return True
    return bool(
        ("角色" in text and any(token in text for token in ("故事", "出场", "剧情", "下一篇", "以后")))
        or ("写" in text and any(token in text for token in ("故事", "连载", "成果")))
    )


def should_run_artifact_directive_agent(message: str) -> bool:
    return HIDDEN_ARTIFACT_DIRECTIVE_AGENT_ENABLED and should_include_artifact_theater_context(message)


def row_to_artifact_directive(row: sqlite3.Row) -> Dict[str, object]:
    return {
        "id": int(row["id"]),
        "directive_key": str(row["directive_key"] or ""),
        "directive_type": str(row["directive_type"] or "other"),
        "subject": str(row["subject"] or ""),
        "directive": str(row["directive"] or ""),
        "characters": [str(item) for item in json_list(row["characters_json"]) if str(item).strip()],
        "series_title": str(row["series_title"] or ""),
        "scope": str(row["scope"] or "persistent"),
        "status": str(row["status"] or "active"),
        "priority": int(row["priority"] or 50),
        "confidence": float(row["confidence"] or 0.7),
        "source_session_id": str(row["source_session_id"] or ""),
        "source_message_ids": normalize_character_image_ids(json_list(row["source_message_ids_json"]))
        if "normalize_character_image_ids" in globals()
        else [],
        "source_visitor_ip": str(row["source_visitor_ip"] or ""),
        "revision_count": int(row["revision_count"] or 1),
        "created_at": str(row["created_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
    }


def list_active_artifact_directives(limit: int = 50) -> List[Dict[str, object]]:
    max_rows = max(1, min(int(limit), 200))
    with connect_db() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM hidden_artifact_directives
            WHERE status = 'active'
            ORDER BY priority DESC, datetime(updated_at) DESC, id DESC
            LIMIT ?
            """,
            (max_rows,),
        ).fetchall()
    return [row_to_artifact_directive(row) for row in rows]


def upsert_hidden_artifact_directive(
    decision: Dict[str, object],
    session_id: str,
    visitor_ip: str,
    source_message_ids: List[int],
) -> Dict[str, object]:
    directive = decision.get("directive") if isinstance(decision.get("directive"), dict) else {}
    directive_type = normalize_directive_type(directive.get("directive_type"))
    subject = clean_artifact_directive_text(directive.get("subject"), 160)
    series_title = clean_artifact_directive_text(directive.get("series_title"), 160)
    directive_text = clean_artifact_directive_text(directive.get("directive"), 1400)
    if not directive_text:
        return {"status": "skipped", "reason": "missing_directive"}
    key = artifact_directive_key(directive_type, subject or directive_text[:80], series_title)
    characters = normalize_directive_characters(directive.get("characters"))
    message_ids = sorted(set(int(item) for item in source_message_ids if int(item) > 0))
    message_ids_json = json.dumps(message_ids, ensure_ascii=False)
    now = utc_now()
    with connect_db() as conn:
        existing = conn.execute(
            "SELECT * FROM hidden_artifact_directives WHERE directive_key = ? LIMIT 1",
            (key,),
        ).fetchone()
        if existing:
            directive_id = int(existing["id"])
            conn.execute(
                """
                UPDATE hidden_artifact_directives
                SET directive_type = ?, subject = ?, directive = ?,
                    characters_json = ?, series_title = ?, scope = ?,
                    status = 'active', priority = ?, confidence = ?,
                    source_session_id = ?, source_message_ids_json = ?,
                    source_visitor_ip = ?, revision_count = revision_count + 1,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    directive_type,
                    subject,
                    directive_text,
                    json.dumps(characters, ensure_ascii=False),
                    series_title,
                    normalize_directive_scope(directive.get("scope")),
                    int(directive.get("priority") or 50),
                    float(directive.get("confidence") or 0.7),
                    session_id or "",
                    message_ids_json,
                    normalize_visitor_ip(visitor_ip),
                    now,
                    directive_id,
                ),
            )
            event_type = "update"
        else:
            cur = conn.execute(
                """
                INSERT INTO hidden_artifact_directives (
                    directive_key, directive_type, subject, directive,
                    characters_json, series_title, scope, status, priority,
                    confidence, source_session_id, source_message_ids_json,
                    source_visitor_ip, revision_count, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    key,
                    directive_type,
                    subject,
                    directive_text,
                    json.dumps(characters, ensure_ascii=False),
                    series_title,
                    normalize_directive_scope(directive.get("scope")),
                    int(directive.get("priority") or 50),
                    float(directive.get("confidence") or 0.7),
                    session_id or "",
                    message_ids_json,
                    normalize_visitor_ip(visitor_ip),
                    now,
                    now,
                ),
            )
            directive_id = int(cur.lastrowid)
            event_type = "create"
        conn.execute(
            """
            INSERT INTO hidden_artifact_directive_events (
                directive_id, event_type, source_session_id,
                source_message_ids_json, patch_json, reason, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                directive_id,
                event_type,
                session_id or "",
                message_ids_json,
                json.dumps(directive, ensure_ascii=False),
                clean_artifact_directive_text(decision.get("reason"), 500),
                now,
            ),
        )
    return {
        "status": event_type,
        "directive_id": directive_id,
        "directive_type": directive_type,
        "subject": subject,
        "directive": directive_text,
    }


def load_recent_artifact_directive_messages(
    session_id: str,
    limit: int = HIDDEN_ARTIFACT_DIRECTIVE_AGENT_CONTEXT_MESSAGES,
) -> List[Dict[str, object]]:
    max_rows = max(1, min(int(limit), 30))
    with connect_db() as conn:
        rows = conn.execute(
            """
            SELECT id, role, content, created_at
            FROM messages
            WHERE session_id = ?
              AND status = 'completed'
              AND role IN ('user', 'assistant')
              AND NOT (
                role = 'user'
                AND COALESCE(json_extract(metadata_json, '$.hidden'), 0) = 1
              )
            ORDER BY id DESC
            LIMIT ?
            """,
            (session_id, max_rows),
        ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "role": str(row["role"] or ""),
            "content": str(row["content"] or ""),
            "created_at": str(row["created_at"] or ""),
        }
        for row in reversed(rows)
    ]


def format_artifact_directive_agent_context(session_id: str, user_message: str) -> str:
    lines = [
        ARTIFACT_THEATER_CONTEXT,
        "",
        "当前用户输入：",
        clean_artifact_directive_text(user_message, 1600),
        "",
        "最近对话：",
    ]
    for item in load_recent_artifact_directive_messages(session_id):
        role = "assistant_context_only" if item["role"] == "assistant" else item["role"]
        lines.append(f"[message id={item['id']} role={role} time={item['created_at']}]")
        lines.append(clean_artifact_directive_text(item["content"], 1000))
        lines.append("")
    active = list_active_artifact_directives(limit=20)
    if active:
        lines.append("已有成果小剧场导演指令：")
        for item in active:
            lines.append(
                json.dumps(
                    {
                        "id": item["id"],
                        "type": item["directive_type"],
                        "subject": item["subject"],
                        "directive": item["directive"],
                        "characters": item["characters"],
                        "series_title": item["series_title"],
                        "scope": item["scope"],
                        "priority": item["priority"],
                    },
                    ensure_ascii=False,
                )
            )
    return "\n".join(lines)[:HIDDEN_ARTIFACT_DIRECTIVE_AGENT_MAX_CONTEXT_CHARS]


def call_artifact_directive_agent_model(context: str) -> Dict[str, object]:
    client, http_client, model_slot = openai_client_for_slot(MODEL_SLOT_BACKGROUND, timeout=HIDDEN_ARTIFACT_DIRECTIVE_AGENT_TIMEOUT)
    try:
        resp = client.chat.completions.create(
            **model_completion_kwargs(model_slot),
            messages=[
                {"role": "system", "content": ARTIFACT_DIRECTIVE_AGENT_SYSTEM_PROMPT},
                {"role": "user", "content": context},
            ],
            temperature=HIDDEN_ARTIFACT_DIRECTIVE_AGENT_TEMPERATURE,
            top_p=HIDDEN_ARTIFACT_DIRECTIVE_AGENT_TOP_P,
            max_tokens=HIDDEN_ARTIFACT_DIRECTIVE_AGENT_MAX_TOKENS,
        )
        content = (resp.choices[0].message.content or "").strip()
        _, answer = split_think_text(content)
        decision = parse_artifact_directive_agent_json(answer)
        decision["model"] = str(model_slot.get("model") or MODEL_NAME)
        return decision
    finally:
        http_client.close()


def run_artifact_directive_agent(
    session_id: str,
    visitor_ip: str,
    user_message: str,
    source_message_ids: List[int],
    analysis_trace_id: str = "",
) -> Dict[str, object]:
    if not should_run_artifact_directive_agent(user_message):
        return {"status": "skipped", "reason": "not_triggered"}
    context = format_artifact_directive_agent_context(session_id, user_message)
    if analysis_trace_id:
        record_analysis_trace(
            session_id=session_id,
            trace_id=analysis_trace_id,
            event_type="model_prompt",
            visitor_ip=visitor_ip,
            step_name="artifact_directive_agent_prompt",
            payload={
                "model": model_slot_config(MODEL_SLOT_BACKGROUND).get("model", MODEL_NAME),
                "source_message_ids": source_message_ids,
                "context": context,
            },
        )
    started = time.perf_counter()
    decision = call_artifact_directive_agent_model(context)
    duration_ms = round((time.perf_counter() - started) * 1000, 3)
    if analysis_trace_id:
        record_analysis_trace(
            session_id=session_id,
            trace_id=analysis_trace_id,
            event_type="model_call",
            visitor_ip=visitor_ip,
            step_name="artifact_directive_agent_model",
            duration_ms=duration_ms,
            payload={
                "model": decision.get("model") or model_slot_config(MODEL_SLOT_BACKGROUND).get("model", MODEL_NAME),
                "decision": decision,
            },
        )
    if decision.get("action") != "upsert":
        record_event(
            session_id,
            "artifact_directive_agent_skipped",
            visitor_ip,
            {"reason": decision.get("reason", "")},
        )
        return {"status": "skipped", "reason": decision.get("reason", "noop"), "decision": decision}
    result = upsert_hidden_artifact_directive(
        decision,
        session_id=session_id,
        visitor_ip=visitor_ip,
        source_message_ids=source_message_ids,
    )
    record_event(session_id, "hidden_artifact_directive_upserted", visitor_ip, {"result": result})
    if analysis_trace_id:
        record_analysis_trace(
            session_id=session_id,
            trace_id=analysis_trace_id,
            event_type="artifact_directive",
            visitor_ip=visitor_ip,
            step_name="hidden_artifact_directive_write",
            payload={"result": result, "decision": decision},
        )
    return result


def maybe_start_artifact_directive_agent_job(
    session_id: str,
    visitor_ip: str,
    user_message: str,
    source_message_ids: List[int],
    analysis_trace_id: str = "",
) -> bool:
    if not should_run_artifact_directive_agent(user_message):
        return False

    def worker() -> None:
        try:
            run_artifact_directive_agent(
                session_id=session_id,
                visitor_ip=visitor_ip,
                user_message=user_message,
                source_message_ids=source_message_ids,
                analysis_trace_id=analysis_trace_id,
            )
        except Exception as exc:
            record_event(session_id, "artifact_directive_agent_error", visitor_ip, {"error": str(exc)})
            if analysis_trace_id:
                record_analysis_trace(
                    session_id=session_id,
                    trace_id=analysis_trace_id,
                    event_type="model_call_error",
                    visitor_ip=visitor_ip,
                    step_name="artifact_directive_agent_model",
                    payload={"error": str(exc)},
                )

    thread = threading.Thread(target=worker, daemon=True, name=f"artifact-directive-agent-{session_id[:8]}")
    thread.start()
    return True


def format_artifact_theater_context_for_chat(user_message: str) -> str:
    if not should_include_artifact_theater_context(user_message):
        return ""
    directives = list_active_artifact_directives(limit=HIDDEN_ARTIFACT_DIRECTIVE_CHAT_CONTEXT_LIMIT)
    lines = [
        ARTIFACT_THEATER_CONTEXT,
        "如果用户本轮是在给成果小剧场下指令，应自然确认会记录/用于后续成果，不要把“成果故事”误解为用户现实科研成果。",
    ]
    if directives:
        lines.append("")
        lines.append("当前已有成果小剧场导演指令摘要：")
        for item in directives:
            subject = f"{item['subject']}：" if item.get("subject") else ""
            lines.append(f"- [{item['directive_type']}] {subject}{item['directive']}")
    return "\n".join(lines).strip()


def format_hidden_artifact_directives_for_artifacts(
    limit: int = HIDDEN_ARTIFACT_DIRECTIVE_ARTIFACT_CONTEXT_LIMIT,
) -> str:
    directives = list_active_artifact_directives(limit=limit)
    if not directives:
        return ""
    lines = [ARTIFACT_DIRECTIVE_CONTEXT_HEADER, ""]
    for index, item in enumerate(directives, start=1):
        parts = [
            f"[导演指令 {index}] type={item['directive_type']}",
            f"priority={item['priority']}",
            f"scope={item['scope']}",
        ]
        if item.get("subject"):
            parts.append(f"subject={item['subject']}")
        if item.get("series_title"):
            parts.append(f"series={item['series_title']}")
        if item.get("characters"):
            parts.append(f"characters={'、'.join(item['characters'])}")
        lines.append(" ".join(parts))
        lines.append(str(item["directive"]).strip())
        lines.append("")
    return "\n".join(lines).strip()
