# Tutorial sandbox lifecycle and ephemeral generation.

TUTORIAL_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{12,96}$")
TUTORIAL_RETENTION_HOURS = 24
TUTORIAL_ARTIFACT_LIMIT = 3


def normalize_tutorial_id(value: object) -> str:
    tutorial_id = str(value or "").strip()
    return tutorial_id if TUTORIAL_ID_PATTERN.fullmatch(tutorial_id) else ""


def tutorial_request_id(request: Request) -> str:
    return normalize_tutorial_id(request.headers.get("X-Wangcai-Tutorial-Id", ""))


def is_tutorial_request(request: Request) -> bool:
    return bool(tutorial_request_id(request))


def reject_tutorial_persistence(request: Request, feature: str) -> None:
    if is_tutorial_request(request):
        raise HTTPException(
            status_code=409,
            detail=f"tutorial mode is read-only for {feature}",
        )


def register_tutorial_session(tutorial_id: str, session_id: str, device_id: str) -> bool:
    normalized_id = normalize_tutorial_id(tutorial_id)
    normalized_device = normalize_visitor_ip(device_id)
    if not normalized_id or not normalized_device or not session_id:
        return False
    with connect_db() as conn:
        conn.execute(
            """
            INSERT INTO tutorial_sessions (session_id, tutorial_id, device_id, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                tutorial_id = excluded.tutorial_id,
                device_id = excluded.device_id
            """,
            (session_id, normalized_id, normalized_device, utc_now()),
        )
    return True


def tutorial_session_matches(tutorial_id: str, session_id: str, device_id: str) -> bool:
    normalized_id = normalize_tutorial_id(tutorial_id)
    normalized_device = normalize_visitor_ip(device_id)
    if not normalized_id or not normalized_device:
        return False
    with connect_db() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM tutorial_sessions
            WHERE tutorial_id = ? AND session_id = ? AND device_id = ?
            LIMIT 1
            """,
            (normalized_id, session_id, normalized_device),
        ).fetchone()
    return row is not None


def tutorial_status_for_device(device_id: str) -> Dict[str, object]:
    normalized_device = normalize_visitor_ip(device_id)
    if not normalized_device or not is_device_identity(normalized_device):
        return {"is_new_user": True, "bound": False, "session_count": 0}
    cleanup_expired_tutorial_data()
    with connect_db() as conn:
        session_count = int(
            conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM sessions s
                LEFT JOIN tutorial_sessions t ON t.session_id = s.id
                WHERE s.visitor_ip = ? AND t.session_id IS NULL
                """,
                (normalized_device,),
            ).fetchone()["c"]
        )
    bound = bool(shared_user_id_for_device(normalized_device))
    return {
        "is_new_user": not bound and session_count == 0,
        "bound": bound,
        "session_count": session_count,
    }


def tutorial_session_ids(tutorial_id: str, device_id: str = "") -> List[str]:
    normalized_id = normalize_tutorial_id(tutorial_id)
    normalized_device = normalize_visitor_ip(device_id) if device_id else ""
    if not normalized_id:
        return []
    clauses = ["tutorial_id = ?"]
    params: List[object] = [normalized_id]
    if normalized_device:
        clauses.append("device_id = ?")
        params.append(normalized_device)
    with connect_db() as conn:
        rows = conn.execute(
            f"SELECT session_id FROM tutorial_sessions WHERE {' AND '.join(clauses)}",
            params,
        ).fetchall()
    return [str(row["session_id"]) for row in rows]


def cleanup_tutorial_data(tutorial_id: str, device_id: str = "") -> Dict[str, int]:
    session_ids = tutorial_session_ids(tutorial_id, device_id)
    normalized_id = normalize_tutorial_id(tutorial_id)
    if not normalized_id:
        return {"sessions": 0, "images": 0}
    removed_images = 0
    with connect_db() as conn:
        if session_ids:
            placeholders = ",".join("?" for _ in session_ids)
            image_rows = conn.execute(
                f"SELECT id, file_path FROM generated_images WHERE source_type = 'chat' AND source_id IN ({placeholders})",
                session_ids,
            ).fetchall()
            for row in image_rows:
                path = Path(str(row["file_path"] or ""))
                try:
                    if path.is_file() and IMAGE_OUTPUT_DIR.resolve() in path.resolve().parents:
                        path.unlink()
                        removed_images += 1
                except OSError:
                    pass
            conn.execute(
                f"DELETE FROM generated_images WHERE source_type = 'chat' AND source_id IN ({placeholders})",
                session_ids,
            )
            memory_rows = conn.execute(
                f"SELECT id FROM curated_memories WHERE source_session_id IN ({placeholders})",
                session_ids,
            ).fetchall()
            memory_ids = [int(row["id"]) for row in memory_rows]
            if memory_ids:
                memory_placeholders = ",".join("?" for _ in memory_ids)
                conn.execute(f"DELETE FROM curated_memory_vectors WHERE memory_id IN ({memory_placeholders})", memory_ids)
                conn.execute(f"DELETE FROM curated_memories WHERE id IN ({memory_placeholders})", memory_ids)
            for table in ("memory_agent_jobs", "memory_retrieval_logs", "analysis_trace_events", "events", "messages"):
                conn.execute(f"DELETE FROM {table} WHERE session_id IN ({placeholders})", session_ids)
            conn.execute(
                f"DELETE FROM session_context_links WHERE current_session_id IN ({placeholders}) OR source_session_id IN ({placeholders})",
                (*session_ids, *session_ids),
            )
            conn.execute(f"DELETE FROM tutorial_sessions WHERE session_id IN ({placeholders})", session_ids)
            conn.execute(f"DELETE FROM sessions WHERE id IN ({placeholders})", session_ids)
        conn.execute("DELETE FROM tutorial_artifact_runs WHERE tutorial_id = ?", (normalized_id,))
    return {"sessions": len(session_ids), "images": removed_images}


def cleanup_expired_tutorial_data() -> Dict[str, int]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=TUTORIAL_RETENTION_HOURS)).isoformat()
    with connect_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT tutorial_id, device_id FROM tutorial_sessions WHERE created_at < ?",
            (cutoff,),
        ).fetchall()
        conn.execute("DELETE FROM tutorial_artifact_runs WHERE created_at < ?", (cutoff,))
    totals = {"sessions": 0, "images": 0}
    for row in rows:
        result = cleanup_tutorial_data(str(row["tutorial_id"]), str(row["device_id"]))
        totals["sessions"] += int(result["sessions"])
        totals["images"] += int(result["images"])
    return totals


def parse_tutorial_artifact_response(raw: str, prompt: str) -> Dict[str, str]:
    _, visible = split_think_text(str(raw or ""))
    text = visible.strip()
    fenced = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
    start, end = fenced.find("{"), fenced.rfind("}")
    parsed: Dict[str, object] = {}
    if start >= 0 and end > start:
        try:
            candidate = json.loads(fenced[start:end + 1])
            if isinstance(candidate, dict):
                parsed = candidate
        except json.JSONDecodeError:
            parsed = {}
    title = str(parsed.get("title") or "教程里的临时小剧场").strip()[:120]
    summary = str(parsed.get("summary") or f"围绕“{prompt[:80]}”生成的教程示例。 ").strip()[:500]
    content = str(parsed.get("content") or text or summary).strip()[:8000]
    image_prompt = str(parsed.get("image_prompt") or f"Cinematic editorial illustration about {prompt[:300]}, no text, no watermark").strip()[:2000]
    return {"title": title, "summary": summary, "content": content, "image_prompt": image_prompt}


def generate_tutorial_artifact(tutorial_id: str, device_id: str, prompt: str) -> Dict[str, object]:
    normalized_id = normalize_tutorial_id(tutorial_id)
    normalized_device = normalize_visitor_ip(device_id)
    clean_prompt = str(prompt or "").strip()
    if not normalized_id or not normalized_device:
        raise ValueError("invalid tutorial scope")
    now = utc_now()
    with connect_db() as conn:
        recent_count = int(
            conn.execute(
                "SELECT COUNT(*) AS c FROM tutorial_artifact_runs WHERE tutorial_id = ? AND device_id = ?",
                (normalized_id, normalized_device),
            ).fetchone()["c"]
        )
        if recent_count >= TUTORIAL_ARTIFACT_LIMIT:
            raise ValueError("tutorial artifact generation limit reached")
        cursor = conn.execute(
            """
            INSERT INTO tutorial_artifact_runs (tutorial_id, device_id, status, created_at, updated_at)
            VALUES (?, ?, 'running', ?, ?)
            """,
            (normalized_id, normalized_device, now, now),
        )
        run_id = int(cursor.lastrowid)
    http_client: Optional[httpx.Client] = None
    try:
        client, http_client, slot = openai_client_for_slot(MODEL_SLOT_BACKGROUND, timeout=REQUEST_TIMEOUT)
        response = client.chat.completions.create(
            **model_completion_kwargs(slot),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你在生成一个不会保存的新手教程示例。根据用户主题写一篇短小、完整、适合展示成果库的中文图文小剧场。"
                        "只返回 JSON 对象，字段为 title、summary、content、image_prompt。"
                        "content 约 500 至 900 字；image_prompt 必须是英文视觉描述，不含文字海报要求。"
                        "不得引用真实用户资料、角色库、长期记忆或既有成果。"
                    ),
                },
                {"role": "user", "content": clean_prompt},
            ],
            temperature=0.8,
            top_p=0.9,
            max_tokens=1800,
            stream=False,
        )
        raw = response.choices[0].message.content or ""
        artifact = parse_tutorial_artifact_response(raw, clean_prompt)
        image_data_url = ""
        image_error = ""
        try:
            images = request_hidream_images(
                artifact["image_prompt"],
                "low quality, blurry, distorted anatomy, watermark, text, signature",
                "16:9",
                1,
            )
            if images:
                image_bytes = images[0]
                mime = "image/jpeg" if image_bytes.startswith(b"\xff\xd8") else "image/png"
                image_data_url = f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"
        except Exception as exc:
            image_error = str(exc)[:240]
        with connect_db() as conn:
            conn.execute(
                "UPDATE tutorial_artifact_runs SET status = 'completed', updated_at = ? WHERE id = ?",
                (utc_now(), run_id),
            )
        return {**artifact, "image_data_url": image_data_url, "image_error": image_error, "saved": False}
    except Exception:
        with connect_db() as conn:
            conn.execute(
                "UPDATE tutorial_artifact_runs SET status = 'failed', updated_at = ? WHERE id = ?",
                (utc_now(), run_id),
            )
        raise
    finally:
        if http_client is not None:
            http_client.close()
