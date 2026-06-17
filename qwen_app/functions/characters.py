# Character asset layer. The visible character library owns character editing.
# Main chat, analysis, and normal draw can retrieve character memories but do not
# create or update character profiles.

CHARACTER_AGENT_TRIGGER_HINTS = (
    "固定角色",
    "固定这个角色",
    "固定形象",
    "确定形象",
    "保存角色",
    "保存这个角色",
    "角色设定",
    "人设",
    "以后他",
    "以后她",
    "以后它",
    "以后这个角色",
    "这个角色叫",
    "这个人叫",
    "她叫",
    "他叫",
    "它叫",
    "就按这个",
    "就长这样",
    "作为固定",
)

CHARACTER_AGENT_CONTEXT_ROLE_LABELS = {
    "user": "user",
    "assistant": "assistant_context_only",
    "system": "system_context_only",
}


def character_name_key(name: str) -> str:
    text = str(name or "").strip().lower()
    text = re.sub(r"[\s\"'“”‘’《》<>【】\[\]（）()，,。.!！?？:：;；·\-_/\\]+", "", text)
    return text[:120]


def archived_character_name_key(name_key: str, character_id: int) -> str:
    key = str(name_key or "").strip() or "character"
    return f"{key}__archived__{int(character_id)}"


def clean_character_text(value: object, max_chars: int = 1600) -> str:
    return clean_search_text(str(value or ""), max_chars).strip()


def normalize_character_aliases(value: object, canonical_name: str = "") -> List[str]:
    raw_items: List[object] = []
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str) and value.strip():
        raw_items = re.split(r"[,，、/|；;]\s*", value)
    aliases: List[str] = []
    seen = set()
    for item in [canonical_name, *raw_items]:
        alias = clean_character_text(item, 80)
        key = character_name_key(alias)
        if not alias or not key or key in seen:
            continue
        seen.add(key)
        aliases.append(alias)
    return aliases[:12]


def normalize_character_relationships(value: object) -> List[str]:
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str) and value.strip():
        raw_items = re.split(r"[\n；;]\s*", value)
    else:
        raw_items = []
    result: List[str] = []
    seen = set()
    for item in raw_items:
        text = clean_character_text(item, 240)
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result[:16]


def normalize_character_image_ids(value: object) -> List[int]:
    if not isinstance(value, list):
        return []
    ids: List[int] = []
    seen = set()
    for item in value:
        try:
            image_id = int(item)
        except Exception:
            continue
        if image_id <= 0 or image_id in seen:
            continue
        seen.add(image_id)
        ids.append(image_id)
    return ids[:24]


def character_profile_mentioned_in_text(profile: Dict[str, object], text: str) -> bool:
    haystack_raw = str(text or "").strip().lower()
    haystack_key = character_name_key(haystack_raw)
    if not haystack_key:
        return False
    names = [profile.get("canonical_name", ""), *(profile.get("aliases") or [])]
    for name in names:
        raw_name = str(name or "").strip()
        key = character_name_key(raw_name)
        if not key:
            continue
        if len(key) < 2:
            continue
        if re.fullmatch(r"[a-z0-9]+", key) and len(key) < 3:
            continue
        if key in haystack_key:
            return True
        raw_lower = raw_name.lower()
        if len(raw_lower) >= 3 and raw_lower in haystack_raw:
            return True
    return False


def character_profiles_mentioned_in_text(text: str, limit: int = 12) -> List[Dict[str, object]]:
    matches: List[Dict[str, object]] = []
    seen_ids = set()
    for profile in list_active_character_profiles(limit=200):
        profile_id = int(profile.get("id") or 0)
        if profile_id <= 0 or profile_id in seen_ids:
            continue
        if character_profile_mentioned_in_text(profile, text):
            seen_ids.add(profile_id)
            matches.append(profile)
        if len(matches) >= max(1, int(limit)):
            break
    return matches


def merge_character_profile_order(*profile_groups: List[Dict[str, object]]) -> List[Dict[str, object]]:
    merged: List[Dict[str, object]] = []
    seen_ids = set()
    for group in profile_groups:
        for profile in group or []:
            try:
                profile_id = int(profile.get("id") or 0)
            except Exception:
                profile_id = 0
            if profile_id <= 0 or profile_id in seen_ids:
                continue
            seen_ids.add(profile_id)
            merged.append(profile)
    return merged


def parse_character_agent_json(text: str) -> Dict[str, object]:
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
            return normalize_character_agent_decision(payload)
    return {"action": "noop", "reason": "invalid_json", "character": {}}


def normalize_character_agent_decision(payload: Dict[str, object]) -> Dict[str, object]:
    action = str(payload.get("action") or "noop").strip().lower()
    if action not in {"noop", "upsert"}:
        action = "noop"
    raw_character = payload.get("character")
    character = raw_character if isinstance(raw_character, dict) else {}
    canonical_name = clean_character_text(character.get("canonical_name"), 120)
    aliases = normalize_character_aliases(character.get("aliases"), canonical_name)
    try:
        confidence = float(character.get("confidence", 0.7))
    except Exception:
        confidence = 0.7
    confidence = max(0.0, min(1.0, confidence))
    normalized_character = {
        "canonical_name": canonical_name,
        "aliases": aliases,
        "visual_prompt": clean_character_text(character.get("visual_prompt"), 5000),
        "negative_prompt": clean_character_text(character.get("negative_prompt"), 1200),
        "personality": clean_character_text(character.get("personality"), 1800),
        "background": clean_character_text(character.get("background"), 2400),
        "relationships": normalize_character_relationships(character.get("relationships")),
        "reference_image_ids": normalize_character_image_ids(character.get("reference_image_ids")),
        "avatar_image_ids": normalize_character_image_ids(character.get("avatar_image_ids")),
        "confidence": confidence,
    }
    if action == "upsert" and not normalized_character["canonical_name"]:
        action = "noop"
    return {
        "action": action,
        "reason": clean_character_text(payload.get("reason"), 500),
        "character": normalized_character,
    }


def json_list(value: object) -> List[object]:
    parsed = safe_json_loads(str(value or "[]"))
    return parsed if isinstance(parsed, list) else []


def row_to_character_profile(row: sqlite3.Row) -> Dict[str, object]:
    return {
        "id": int(row["id"]),
        "canonical_name": str(row["canonical_name"] or ""),
        "name_key": str(row["name_key"] or ""),
        "aliases": [str(item) for item in json_list(row["aliases_json"]) if str(item).strip()],
        "visual_prompt": str(row["visual_prompt"] or ""),
        "negative_prompt": str(row["negative_prompt"] or ""),
        "personality": str(row["personality"] or ""),
        "background": str(row["background"] or ""),
        "relationships": [str(item) for item in json_list(row["relationships_json"]) if str(item).strip()],
        "reference_image_ids": normalize_character_image_ids(json_list(row["reference_image_ids_json"])),
        "avatar_image_ids": normalize_character_image_ids(json_list(row["avatar_image_ids_json"])),
        "source_session_id": str(row["source_session_id"] or ""),
        "source_message_ids": normalize_character_image_ids(json_list(row["source_message_ids_json"])),
        "source_visitor_ip": str(row["source_visitor_ip"] or ""),
        "scope": str(row["scope"] or "artifact_public"),
        "status": str(row["status"] or "active"),
        "confidence": float(row["confidence"] or 0.7),
        "revision_count": int(row["revision_count"] or 1),
        "created_at": str(row["created_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
    }


def list_active_character_profiles(limit: int = 80) -> List[Dict[str, object]]:
    max_rows = max(1, min(int(limit), 200))
    with connect_db() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM hidden_character_profiles
            WHERE status = 'active'
            ORDER BY datetime(updated_at) DESC, id DESC
            LIMIT ?
            """,
            (max_rows,),
        ).fetchall()
    return [row_to_character_profile(row) for row in rows]


def generated_images_by_ids(image_ids: List[int]) -> Dict[int, Dict[str, object]]:
    ids = normalize_character_image_ids(image_ids)
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    with connect_db() as conn:
        rows = conn.execute(
            f"""
            SELECT id, batch_id, public_url, original_prompt, optimized_prompt,
                   negative_prompt, aspect_ratio, model_name, created_at
            FROM generated_images
            WHERE id IN ({placeholders})
            """,
            tuple(ids),
        ).fetchall()
    return {int(row["id"]): dict(row) for row in rows}


def character_public_payload(profile: Dict[str, object], include_full: bool = False) -> Dict[str, object]:
    image_ids = normalize_character_image_ids(profile.get("reference_image_ids") or [])
    avatar_image_ids = normalize_character_image_ids(profile.get("avatar_image_ids") or [])
    images_by_id = generated_images_by_ids(merge_character_lists(avatar_image_ids[:8], image_ids[:24], max_items=32))
    images = [images_by_id[image_id] for image_id in image_ids if image_id in images_by_id]
    avatar_images = [images_by_id[image_id] for image_id in avatar_image_ids if image_id in images_by_id]
    total_image_count = len(set(image_ids + avatar_image_ids))
    main_image = images[0] if images else None
    avatar_image = avatar_images[0] if avatar_images else main_image
    payload = {
        "id": int(profile.get("id") or 0),
        "canonical_name": str(profile.get("canonical_name") or ""),
        "aliases": [str(item) for item in profile.get("aliases", []) if str(item).strip()],
        "personality": str(profile.get("personality") or ""),
        "background": str(profile.get("background") or ""),
        "relationships": [str(item) for item in profile.get("relationships", []) if str(item).strip()],
        "main_image": main_image,
        "avatar_image": avatar_image,
        "image_count": total_image_count,
        "avatar_count": len(avatar_images),
        "confidence": float(profile.get("confidence") or 0.7),
        "revision_count": int(profile.get("revision_count") or 1),
        "updated_at": str(profile.get("updated_at") or ""),
        "created_at": str(profile.get("created_at") or ""),
    }
    if include_full:
        profile_names = {
            character_name_key(str(profile.get("canonical_name") or "")),
            *[character_name_key(str(alias)) for alias in profile.get("aliases", [])],
        }
        profile_names.discard("")
        directives = []
        for directive in compact_character_library_directives(limit=120):
            directive_names = {character_name_key(str(directive.get("subject") or ""))}
            directive_names.update(character_name_key(str(item)) for item in directive.get("characters", []) or [])
            directive_names.discard("")
            if profile_names.intersection(directive_names):
                directives.append(directive)
        payload.update(
            {
                "visual_prompt": str(profile.get("visual_prompt") or ""),
                "negative_prompt": str(profile.get("negative_prompt") or ""),
                "reference_images": images,
                "avatar_images": avatar_images,
                "artifact_directives": directives,
                "source_session_id": str(profile.get("source_session_id") or ""),
                "source_message_ids": normalize_character_image_ids(profile.get("source_message_ids") or []),
            }
        )
    return payload


def format_character_global_memory_text(profile: Dict[str, object]) -> str:
    name = clean_character_text(profile.get("canonical_name"), 120) or "未命名角色"
    aliases = [clean_character_text(item, 80) for item in profile.get("aliases", []) if clean_character_text(item, 80)]
    personality = clean_character_text(profile.get("personality"), 900)
    background = clean_character_text(profile.get("background"), 1200)
    relationships = [
        clean_character_text(item, 180)
        for item in profile.get("relationships", [])
        if clean_character_text(item, 180)
    ][:8]
    visual_prompt = clean_character_text(profile.get("visual_prompt"), 1800)
    negative_prompt = clean_character_text(profile.get("negative_prompt"), 500)
    parts = [
        f"旺财成果小剧场全局角色：{name}。",
        "这是可复用的创作角色资产，可在聊天介绍、绘图参考、成果撰写和小剧场剧情中被召回；这不是用户个人隐私记忆。",
    ]
    if aliases:
        parts.append(f"别名/称呼：{'、'.join(aliases)}。")
    if personality:
        parts.append(f"性格与气质：{personality}")
    if background:
        parts.append(f"背景设定：{background}")
    if relationships:
        parts.append(f"关系与剧情线索：{'；'.join(relationships)}。")
    if visual_prompt:
        parts.append(f"图像特征与绘图参考：{visual_prompt}")
    if negative_prompt:
        parts.append(f"绘图负面约束：{negative_prompt}")
    return "\n".join(parts).strip()


def sync_character_global_memory(character_id: int) -> Dict[str, object]:
    try:
        profile = character_profile_by_id(int(character_id))
    except Exception as exc:
        return {"status": "missing_character", "error": str(exc)}
    content = format_character_global_memory_text(profile)
    if not content:
        return {"status": "empty"}
    try:
        memory_id = upsert_global_character_memory(
            int(character_id),
            content,
            confidence=float(profile.get("confidence") or 0.85),
        )
        return {"status": "synced", "memory_id": int(memory_id), "character_id": int(character_id)}
    except Exception as exc:
        record_event(
            None,
            "character_global_memory_sync_error",
            "character_library",
            {"character_id": int(character_id), "error": str(exc)},
        )
        return {"status": "error", "error": str(exc)}


def delete_character_global_memory(character_id: int) -> Dict[str, object]:
    try:
        deleted = delete_global_character_memory(int(character_id))
        return {"status": "deleted", "deleted": int(deleted), "character_id": int(character_id)}
    except Exception as exc:
        record_event(
            None,
            "character_global_memory_delete_error",
            "character_library",
            {"character_id": int(character_id), "error": str(exc)},
        )
        return {"status": "error", "error": str(exc)}


def list_character_library_profiles(limit: int = 200) -> Dict[str, object]:
    profiles = list_active_character_profiles(limit=limit)
    items = [character_public_payload(profile) for profile in profiles]
    avatar_candidates = [
        item.get("avatar_image") or item.get("main_image")
        for item in items
        if item.get("avatar_image") or item.get("main_image")
    ]
    random_avatar = None
    if avatar_candidates:
        random_avatar = avatar_candidates[int(time.time()) % len(avatar_candidates)]
    return {
        "items": items,
        "count": len(profiles),
        "random_avatar": random_avatar,
    }


def get_character_library_profile(character_id: int) -> Dict[str, object]:
    with connect_db() as conn:
        row = conn.execute(
            "SELECT * FROM hidden_character_profiles WHERE id = ? AND status = 'active' LIMIT 1",
            (int(character_id),),
        ).fetchone()
    if not row:
        raise KeyError("character not found")
    return character_public_payload(row_to_character_profile(row), include_full=True)


def normalize_character_card_artifact_directives(value: object, canonical_name: str) -> List[Dict[str, object]]:
    if not isinstance(value, list):
        return []
    normalized: List[Dict[str, object]] = []
    for item in value[:12]:
        if not isinstance(item, dict):
            continue
        try:
            directive_id = int(item.get("id") or 0)
        except Exception:
            directive_id = 0
        try:
            priority = int(item.get("priority") or 50)
        except Exception:
            priority = 50
        priority = max(1, min(100, priority))
        try:
            confidence = float(item.get("confidence", 0.8))
        except Exception:
            confidence = 0.8
        confidence = max(0.0, min(1.0, confidence))
        characters = normalize_directive_characters(item.get("characters")) if "normalize_directive_characters" in globals() else []
        if canonical_name and character_name_key(canonical_name) not in {character_name_key(name) for name in characters}:
            characters.insert(0, canonical_name)
        normalized.append(
            {
                "id": directive_id,
                "directive_type": normalize_directive_type(item.get("directive_type")) if "normalize_directive_type" in globals() else "other",
                "subject": clean_artifact_directive_text(item.get("subject"), 160)
                if "clean_artifact_directive_text" in globals()
                else clean_character_text(item.get("subject"), 160),
                "directive": clean_artifact_directive_text(item.get("directive"), 1400)
                if "clean_artifact_directive_text" in globals()
                else clean_character_text(item.get("directive"), 1400),
                "characters": characters[:12],
                "series_title": clean_artifact_directive_text(item.get("series_title"), 160)
                if "clean_artifact_directive_text" in globals()
                else clean_character_text(item.get("series_title"), 160),
                "scope": normalize_directive_scope(item.get("scope")) if "normalize_directive_scope" in globals() else "persistent",
                "priority": priority,
                "confidence": confidence,
            }
        )
    return normalized


def sync_character_card_artifact_directives(
    character_id: int,
    canonical_name: str,
    raw_directives: object,
    now: str,
) -> List[Dict[str, object]]:
    directives = normalize_character_card_artifact_directives(raw_directives, canonical_name)
    results: List[Dict[str, object]] = []
    for directive in directives:
        directive_id = int(directive.get("id") or 0)
        directive_text = str(directive.get("directive") or "").strip()
        if directive_id > 0:
            with connect_db() as conn:
                row = conn.execute(
                    "SELECT * FROM hidden_artifact_directives WHERE id = ? LIMIT 1",
                    (directive_id,),
                ).fetchone()
                if not row:
                    results.append({"id": directive_id, "status": "not_found"})
                    continue
                if not directive_text:
                    conn.execute(
                        """
                        UPDATE hidden_artifact_directives
                        SET status = 'archived', updated_at = ?, revision_count = revision_count + 1
                        WHERE id = ?
                        """,
                        (now, directive_id),
                    )
                    conn.execute(
                        """
                        INSERT INTO hidden_artifact_directive_events (
                            directive_id, event_type, source_session_id,
                            source_message_ids_json, patch_json, reason, created_at
                        )
                        VALUES (?, 'archive', '', '[]', ?, 'manual character card edit cleared directive', ?)
                        """,
                        (
                            directive_id,
                            json.dumps({"status": "archived", "character_id": int(character_id)}, ensure_ascii=False),
                            now,
                        ),
                    )
                    results.append({"id": directive_id, "status": "archived"})
                    continue
                conn.execute(
                    """
                    UPDATE hidden_artifact_directives
                    SET directive_type = ?, subject = ?, directive = ?,
                        characters_json = ?, series_title = ?, scope = ?,
                        status = 'active', priority = ?, confidence = ?,
                        revision_count = revision_count + 1, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        directive.get("directive_type") or "other",
                        directive.get("subject") or canonical_name,
                        directive_text,
                        json.dumps(directive.get("characters") or [canonical_name], ensure_ascii=False),
                        directive.get("series_title") or "",
                        directive.get("scope") or "persistent",
                        int(directive.get("priority") or 50),
                        float(directive.get("confidence") or 0.8),
                        now,
                        directive_id,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO hidden_artifact_directive_events (
                        directive_id, event_type, source_session_id,
                        source_message_ids_json, patch_json, reason, created_at
                    )
                    VALUES (?, 'manual_update', '', '[]', ?, 'manual character card edit', ?)
                    """,
                    (
                        directive_id,
                        json.dumps(directive, ensure_ascii=False),
                        now,
                    ),
                )
                results.append({"id": directive_id, "status": "updated"})
            continue
        if not directive_text:
            continue
        result = upsert_hidden_artifact_directive(
            {
                "action": "upsert",
                "reason": "manual character card edit",
                "directive": directive,
            },
            session_id="",
            visitor_ip="character_library_ui",
            source_message_ids=[],
        )
        results.append(result)
    return results


def update_hidden_character_profile_fields(character_id: int, payload: Dict[str, object]) -> Dict[str, object]:
    now = utc_now()
    with connect_db() as conn:
        row = conn.execute(
            "SELECT * FROM hidden_character_profiles WHERE id = ? AND status = 'active' LIMIT 1",
            (int(character_id),),
        ).fetchone()
        if not row:
            raise KeyError("character not found")
        existing = row_to_character_profile(row)
        canonical_name = clean_character_text(payload.get("canonical_name"), 120) or str(existing.get("canonical_name") or "")
        aliases = normalize_character_aliases(payload.get("aliases"), canonical_name)
        if not aliases:
            aliases = normalize_character_aliases(existing.get("aliases"), canonical_name)
        relationships = normalize_character_relationships(payload.get("relationships"))
        visual_prompt = clean_character_text(payload.get("visual_prompt"), 5000)
        negative_prompt = clean_character_text(payload.get("negative_prompt"), 1200)
        personality = clean_character_text(payload.get("personality"), 1800)
        background = clean_character_text(payload.get("background"), 2400)
        patch = {
            "canonical_name": canonical_name,
            "aliases": aliases,
            "visual_prompt": visual_prompt,
            "negative_prompt": negative_prompt,
            "personality": personality,
            "background": background,
            "relationships": relationships,
        }
        if isinstance(payload.get("artifact_directives"), list):
            directive_results = sync_character_card_artifact_directives(
                int(character_id),
                canonical_name,
                payload.get("artifact_directives"),
                now,
            )
            patch["artifact_directives"] = directive_results
        conn.execute(
            """
            UPDATE hidden_character_profiles
            SET canonical_name = ?, name_key = ?, aliases_json = ?, visual_prompt = ?,
                negative_prompt = ?, personality = ?, background = ?,
                relationships_json = ?, revision_count = revision_count + 1,
                updated_at = ?
            WHERE id = ?
            """,
            (
                canonical_name,
                character_name_key(canonical_name),
                json.dumps(aliases, ensure_ascii=False),
                visual_prompt,
                negative_prompt,
                personality,
                background,
                json.dumps(relationships, ensure_ascii=False),
                now,
                int(character_id),
            ),
        )
        conn.execute(
            """
            INSERT INTO hidden_character_profile_events (
                character_id, event_type, source_type, source_session_id,
                source_message_ids_json, patch_json, reason, created_at
            )
            VALUES (?, 'manual_update', 'character_library_ui', '', '[]', ?, 'manual card edit', ?)
            """,
            (int(character_id), json.dumps(patch, ensure_ascii=False), now),
        )
    result = get_character_library_profile(int(character_id))
    sync_character_global_memory(int(character_id))
    return result


def delete_hidden_character_profile(character_id: int, session_id: str, reason: str = "") -> bool:
    now = utc_now()
    with connect_db() as conn:
        row = conn.execute(
            "SELECT * FROM hidden_character_profiles WHERE id = ? AND status = 'active' LIMIT 1",
            (int(character_id),),
        ).fetchone()
        if not row:
            return False
        old_name_key = str(row["name_key"] or "")
        conn.execute(
            """
            UPDATE hidden_character_profiles
            SET name_key = ?, status = 'archived', revision_count = revision_count + 1, updated_at = ?
            WHERE id = ?
            """,
            (archived_character_name_key(old_name_key, int(character_id)), now, int(character_id)),
        )
        conn.execute(
            """
            INSERT INTO hidden_character_profile_events (
                character_id, event_type, source_type, source_session_id,
                source_message_ids_json, patch_json, reason, created_at
            )
            VALUES (?, 'archive', 'character_library', ?, '[]', '{}', ?, ?)
            """,
            (int(character_id), session_id or "", clean_character_text(reason, 500), now),
        )
    delete_character_global_memory(int(character_id))
    return True


def save_character_library_uploaded_images(
    attachments: List[ChatAttachment],
    session_id: str,
) -> List[Dict[str, object]]:
    cleaned = validate_chat_attachments(attachments or [])
    if not cleaned:
        return []
    batch_id = str(uuid.uuid4())
    images: List[Dict[str, object]] = []
    for index, attachment in enumerate(cleaned, start=1):
        match = IMAGE_DATA_URL_RE.match(str(attachment.get("data_url") or ""))
        if not match:
            continue
        try:
            image_bytes = base64.b64decode(match.group(2).replace("\n", "").replace("\r", ""), validate=True)
        except Exception:
            continue
        file_path, public_url = save_generated_image_file(image_bytes, batch_id, index)
        item = save_generated_image_record(
            batch_id=batch_id,
            source_type="character_upload",
            source_id=session_id,
            file_path=file_path,
            public_url=public_url,
            original_prompt=f"角色库上传图片：{attachment.get('name') or 'image'}",
            optimized_prompt="",
            negative_prompt="",
            aspect_ratio="",
            model_name="uploaded",
        )
        images.append(item)
    return images


def find_character_profile_for_patch(
    conn: sqlite3.Connection,
    canonical_name: str,
    aliases: List[str],
) -> Optional[Dict[str, object]]:
    keys = {character_name_key(canonical_name)}
    keys.update(character_name_key(alias) for alias in aliases)
    keys.discard("")
    if not keys:
        return None
    direct = conn.execute(
        """
        SELECT *
        FROM hidden_character_profiles
        WHERE status = 'active' AND name_key IN ({})
        ORDER BY datetime(updated_at) DESC, id DESC
        LIMIT 1
        """.format(",".join("?" for _ in keys)),
        tuple(keys),
    ).fetchone()
    if direct:
        return row_to_character_profile(direct)
    rows = conn.execute(
        """
        SELECT *
        FROM hidden_character_profiles
        WHERE status = 'active'
        ORDER BY datetime(updated_at) DESC, id DESC
        LIMIT 200
        """
    ).fetchall()
    for row in rows:
        profile = row_to_character_profile(row)
        profile_keys = {character_name_key(str(profile.get("canonical_name") or ""))}
        profile_keys.update(character_name_key(alias) for alias in profile.get("aliases", []))
        if keys.intersection(profile_keys):
            return profile
    return None


def find_active_character_profile_by_id_for_patch(
    conn: sqlite3.Connection,
    character_id: object,
) -> Optional[Dict[str, object]]:
    try:
        normalized_id = int(character_id or 0)
    except Exception:
        normalized_id = 0
    if normalized_id <= 0:
        return None
    row = conn.execute(
        """
        SELECT *
        FROM hidden_character_profiles
        WHERE id = ? AND status = 'active'
        LIMIT 1
        """,
        (normalized_id,),
    ).fetchone()
    return row_to_character_profile(row) if row else None


def find_archived_character_profile_for_name_key(conn: sqlite3.Connection, name_key: str) -> Optional[Dict[str, object]]:
    key = str(name_key or "").strip()
    if not key:
        return None
    row = conn.execute(
        """
        SELECT *
        FROM hidden_character_profiles
        WHERE status != 'active' AND name_key = ?
        ORDER BY datetime(updated_at) DESC, id DESC
        LIMIT 1
        """,
        (key,),
    ).fetchone()
    return row_to_character_profile(row) if row else None


def merge_character_lists(left: List[object], right: List[object], max_items: int = 24) -> List[object]:
    merged: List[object] = []
    seen = set()
    for item in [*left, *right]:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True) if isinstance(item, (dict, list)) else str(item)
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged[:max_items]


def upsert_hidden_character_profile(
    decision: Dict[str, object],
    session_id: str,
    visitor_ip: str,
    source_message_ids: List[int],
    source_type: str,
) -> Dict[str, object]:
    character = decision.get("character") if isinstance(decision.get("character"), dict) else {}
    # Character image ownership is managed by explicit upload/generation/delete
    # flows. Do not trust model-emitted image id arrays during text upserts:
    # the editor sees other profiles for context and may echo unrelated ids.
    incoming_reference_image_ids = normalize_character_image_ids(character.get("reference_image_ids"))
    incoming_avatar_image_ids = normalize_character_image_ids(character.get("avatar_image_ids"))
    allow_character_image_patch = bool(decision.get("allow_image_patch"))
    canonical_name = clean_character_text(character.get("canonical_name"), 120)
    aliases = normalize_character_aliases(character.get("aliases"), canonical_name)
    name_key = character_name_key(canonical_name or (aliases[0] if aliases else ""))
    if not canonical_name or not name_key:
        return {"status": "skipped", "reason": "missing_name"}

    now = utc_now()
    patch_json = json.dumps(character, ensure_ascii=False)
    message_ids_json = json.dumps(sorted(set(int(item) for item in source_message_ids if int(item) > 0)), ensure_ascii=False)
    with connect_db() as conn:
        existing = find_active_character_profile_by_id_for_patch(conn, decision.get("target_character_id"))
        if not existing:
            existing = find_character_profile_for_patch(conn, canonical_name, aliases)
        restoring_archived = False
        if not existing:
            existing = find_archived_character_profile_for_name_key(conn, name_key)
            restoring_archived = existing is not None
        if existing:
            character_id = int(existing["id"])
            conn.execute(
                """
                UPDATE hidden_character_profiles
                SET name_key = name_key || '__archived__' || id
                WHERE status != 'active' AND name_key = ? AND id != ?
                """,
                (name_key, character_id),
            )
            merged_aliases = normalize_character_aliases(
                merge_character_lists(existing.get("aliases", []), aliases, max_items=12),
                canonical_name or str(existing.get("canonical_name") or ""),
            )
            merged_relationships = merge_character_lists(
                list(existing.get("relationships", [])),
                list(character.get("relationships") or []),
                max_items=16,
            )
            merged_image_ids = merge_character_lists(
                list(existing.get("reference_image_ids", [])),
                incoming_reference_image_ids if allow_character_image_patch else [],
                max_items=24,
            )
            merged_avatar_image_ids = merge_character_lists(
                list(existing.get("avatar_image_ids", [])),
                incoming_avatar_image_ids if allow_character_image_patch else [],
                max_items=12,
            )
            updates = {
                "canonical_name": canonical_name or str(existing.get("canonical_name") or ""),
                "aliases_json": json.dumps(merged_aliases, ensure_ascii=False),
                "visual_prompt": clean_character_text(character.get("visual_prompt"), 5000)
                or str(existing.get("visual_prompt") or ""),
                "negative_prompt": clean_character_text(character.get("negative_prompt"), 1200)
                or str(existing.get("negative_prompt") or ""),
                "personality": clean_character_text(character.get("personality"), 1800)
                or str(existing.get("personality") or ""),
                "background": clean_character_text(character.get("background"), 2400)
                or str(existing.get("background") or ""),
                "relationships_json": json.dumps(merged_relationships, ensure_ascii=False),
                "reference_image_ids_json": json.dumps(merged_image_ids, ensure_ascii=False),
                "avatar_image_ids_json": json.dumps(merged_avatar_image_ids, ensure_ascii=False),
                "source_session_id": session_id or str(existing.get("source_session_id") or ""),
                "source_message_ids_json": message_ids_json,
                "source_visitor_ip": normalize_visitor_ip(visitor_ip),
                "confidence": max(float(existing.get("confidence") or 0.7), float(character.get("confidence") or 0.7)),
                "updated_at": now,
            }
            conn.execute(
                """
                UPDATE hidden_character_profiles
                SET canonical_name = ?, name_key = ?, aliases_json = ?, visual_prompt = ?,
                    negative_prompt = ?, personality = ?, background = ?,
                    relationships_json = ?, reference_image_ids_json = ?,
                    avatar_image_ids_json = ?,
                    source_session_id = ?, source_message_ids_json = ?,
                    source_visitor_ip = ?, confidence = ?, revision_count = revision_count + 1,
                    status = 'active', updated_at = ?
                WHERE id = ?
                """,
                (
                    updates["canonical_name"],
                    name_key,
                    updates["aliases_json"],
                    updates["visual_prompt"],
                    updates["negative_prompt"],
                    updates["personality"],
                    updates["background"],
                    updates["relationships_json"],
                    updates["reference_image_ids_json"],
                    updates["avatar_image_ids_json"],
                    updates["source_session_id"],
                    updates["source_message_ids_json"],
                    updates["source_visitor_ip"],
                    updates["confidence"],
                    updates["updated_at"],
                    character_id,
                ),
            )
            event_type = "restore" if restoring_archived else "update"
        else:
            cur = conn.execute(
                """
                INSERT INTO hidden_character_profiles (
                    canonical_name, name_key, aliases_json, visual_prompt,
                    negative_prompt, personality, background, relationships_json,
                    reference_image_ids_json, avatar_image_ids_json, source_session_id, source_message_ids_json,
                    source_visitor_ip, scope, status, confidence, revision_count,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'artifact_public', 'active', ?, 1, ?, ?)
                """,
                (
                    canonical_name,
                    name_key,
                    json.dumps(aliases, ensure_ascii=False),
                    clean_character_text(character.get("visual_prompt"), 5000),
                    clean_character_text(character.get("negative_prompt"), 1200),
                    clean_character_text(character.get("personality"), 1800),
                    clean_character_text(character.get("background"), 2400),
                    json.dumps(list(character.get("relationships") or []), ensure_ascii=False),
                    json.dumps(incoming_reference_image_ids if allow_character_image_patch else [], ensure_ascii=False),
                    json.dumps(incoming_avatar_image_ids if allow_character_image_patch else [], ensure_ascii=False),
                    session_id or "",
                    message_ids_json,
                    normalize_visitor_ip(visitor_ip),
                    float(character.get("confidence") or 0.7),
                    now,
                    now,
                ),
            )
            character_id = int(cur.lastrowid)
            event_type = "create"
        conn.execute(
            """
            INSERT INTO hidden_character_profile_events (
                character_id, event_type, source_type, source_session_id,
                source_message_ids_json, patch_json, reason, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                character_id,
                event_type,
                source_type or "chat",
                session_id or "",
                message_ids_json,
                patch_json,
                clean_character_text(decision.get("reason"), 500),
                now,
            ),
        )
    sync_character_global_memory(int(character_id))
    return {
        "status": event_type,
        "character_id": character_id,
        "canonical_name": canonical_name,
        "aliases": aliases,
    }


def should_run_hidden_character_agent(message: str, mode: str = "chat", has_draw_batch: bool = False) -> bool:
    return False


def load_recent_character_messages(session_id: str, limit: int = HIDDEN_CHARACTER_AGENT_CONTEXT_MESSAGES) -> List[Dict[str, object]]:
    max_rows = max(1, min(int(limit), 30))
    with connect_db() as conn:
        rows = conn.execute(
            """
            SELECT id, role, content, created_at, metadata_json
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
    result: List[Dict[str, object]] = []
    for row in reversed(rows):
        metadata = safe_json_loads(str(row["metadata_json"] or "{}"))
        result.append(
            {
                "id": int(row["id"]),
                "role": str(row["role"] or ""),
                "content": str(row["content"] or ""),
                "created_at": str(row["created_at"] or ""),
                "metadata": metadata if isinstance(metadata, dict) else {},
            }
        )
    return result


def load_recent_character_images(session_id: str, limit: int = HIDDEN_CHARACTER_AGENT_RECENT_IMAGES) -> List[Dict[str, object]]:
    max_rows = max(1, min(int(limit), 24))
    with connect_db() as conn:
        rows = conn.execute(
            """
            SELECT id, batch_id, public_url, original_prompt, optimized_prompt,
                   negative_prompt, aspect_ratio, model_name, created_at
            FROM generated_images
            WHERE source_type = 'chat'
              AND source_id = ?
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT ?
            """,
            (session_id, max_rows),
        ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "batch_id": str(row["batch_id"] or ""),
            "public_url": str(row["public_url"] or ""),
            "original_prompt": str(row["original_prompt"] or ""),
            "optimized_prompt": str(row["optimized_prompt"] or ""),
            "negative_prompt": str(row["negative_prompt"] or ""),
            "aspect_ratio": str(row["aspect_ratio"] or ""),
            "model_name": str(row["model_name"] or ""),
            "created_at": str(row["created_at"] or ""),
        }
        for row in rows
    ]


def format_hidden_character_agent_context(
    session_id: str,
    user_message: str,
    draw_batch: Optional[Dict[str, object]] = None,
) -> str:
    messages = load_recent_character_messages(session_id)
    images = load_recent_character_images(session_id)
    active_profiles = list_active_character_profiles(limit=40)
    lines = [
        "当前用户输入：",
        clean_character_text(user_message, 1600),
        "",
        "最近对话：",
    ]
    for item in messages:
        role = CHARACTER_AGENT_CONTEXT_ROLE_LABELS.get(str(item.get("role") or ""), str(item.get("role") or ""))
        lines.append(f"[message id={item.get('id')} role={role} time={item.get('created_at')}]")
        lines.append(clean_character_text(item.get("content"), 1200))
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        draw = metadata.get("draw") if isinstance(metadata.get("draw"), dict) else {}
        if draw:
            lines.append(
                "assistant_draw_metadata="
                + json.dumps(
                    {
                        "batch_id": draw.get("batch_id", ""),
                        "optimized_prompt": clean_character_text(draw.get("optimized_prompt"), 1200),
                        "negative_prompt": clean_character_text(draw.get("negative_prompt"), 400),
                        "aspect_ratio": draw.get("aspect_ratio", ""),
                        "image_ids": [
                            image.get("id")
                            for image in draw.get("images", [])
                            if isinstance(image, dict) and image.get("id")
                        ],
                    },
                    ensure_ascii=False,
                )
            )
        lines.append("")
    if images:
        lines.append("最近绘图图片与 prompt：")
        for image in images:
            lines.append(
                json.dumps(
                    {
                        "id": image["id"],
                        "batch_id": image["batch_id"],
                        "url": image["public_url"],
                        "original_prompt": clean_character_text(image["original_prompt"], 900),
                        "optimized_prompt": clean_character_text(image["optimized_prompt"], 1600),
                        "negative_prompt": clean_character_text(image["negative_prompt"], 500),
                        "aspect_ratio": image["aspect_ratio"],
                        "created_at": image["created_at"],
                    },
                    ensure_ascii=False,
                )
            )
        lines.append("")
    if draw_batch:
        lines.append("本轮新生成图片：")
        lines.append(json.dumps(draw_batch, ensure_ascii=False)[:2400])
        lines.append("")
    if active_profiles:
        lines.append("已有隐性固定角色设定：")
        for profile in active_profiles:
            lines.append(
                json.dumps(
                    {
                        "id": profile["id"],
                        "canonical_name": profile["canonical_name"],
                        "aliases": profile["aliases"],
                        "visual_prompt": clean_character_text(profile["visual_prompt"], 1000),
                        "personality": clean_character_text(profile["personality"], 500),
                        "background": clean_character_text(profile["background"], 500),
                        "reference_image_ids": profile["reference_image_ids"],
                        "avatar_image_ids": profile.get("avatar_image_ids", []),
                    },
                    ensure_ascii=False,
                )
            )
    context = "\n".join(lines)
    return context[:HIDDEN_CHARACTER_AGENT_MAX_CONTEXT_CHARS]


def call_hidden_character_agent_model(context: str) -> Dict[str, object]:
    client, http_client, model_slot = openai_client_for_slot(MODEL_SLOT_BACKGROUND, timeout=HIDDEN_CHARACTER_AGENT_TIMEOUT)
    try:
        resp = client.chat.completions.create(
            **model_completion_kwargs(model_slot),
            messages=[
                {"role": "system", "content": HIDDEN_CHARACTER_AGENT_SYSTEM_PROMPT},
                {"role": "user", "content": context},
            ],
            temperature=HIDDEN_CHARACTER_AGENT_TEMPERATURE,
            top_p=HIDDEN_CHARACTER_AGENT_TOP_P,
            max_tokens=HIDDEN_CHARACTER_AGENT_MAX_TOKENS,
        )
        content = (resp.choices[0].message.content or "").strip()
        _, answer = split_think_text(content)
        decision = parse_character_agent_json(answer)
        decision["model"] = str(model_slot.get("model") or MODEL_NAME)
        return decision
    finally:
        http_client.close()


def run_hidden_character_agent(
    session_id: str,
    visitor_ip: str,
    user_message: str,
    source_message_ids: List[int],
    source_type: str = "chat",
    mode: str = "chat",
    draw_batch: Optional[Dict[str, object]] = None,
    analysis_trace_id: str = "",
) -> Dict[str, object]:
    if not should_run_hidden_character_agent(
        user_message,
        mode=mode,
        has_draw_batch=bool(draw_batch and draw_batch.get("images")),
    ):
        return {"status": "skipped", "reason": "not_triggered"}
    started = time.perf_counter()
    context = format_hidden_character_agent_context(session_id, user_message, draw_batch=draw_batch)
    if analysis_trace_id:
        record_analysis_trace(
            session_id=session_id,
            trace_id=analysis_trace_id,
            event_type="model_prompt",
            visitor_ip=visitor_ip,
            step_name="hidden_character_agent_prompt",
            payload={
                "model": model_slot_config(MODEL_SLOT_BACKGROUND).get("model", MODEL_NAME),
                "source_type": source_type,
                "source_message_ids": source_message_ids,
                "context": context,
            },
        )
    decision = call_hidden_character_agent_model(context)
    duration_ms = round((time.perf_counter() - started) * 1000, 3)
    if analysis_trace_id:
        record_analysis_trace(
            session_id=session_id,
            trace_id=analysis_trace_id,
            event_type="model_call",
            visitor_ip=visitor_ip,
            step_name="hidden_character_agent_model",
            duration_ms=duration_ms,
            payload={
                "model": decision.get("model") or model_slot_config(MODEL_SLOT_BACKGROUND).get("model", MODEL_NAME),
                "source_type": source_type,
                "decision": decision,
            },
        )
    if decision.get("action") != "upsert":
        record_event(
            session_id,
            "hidden_character_agent_skipped",
            visitor_ip,
            {"reason": decision.get("reason", ""), "source_type": source_type},
        )
        return {"status": "skipped", "reason": decision.get("reason", "noop"), "decision": decision}
    result = upsert_hidden_character_profile(
        decision,
        session_id=session_id,
        visitor_ip=visitor_ip,
        source_message_ids=source_message_ids,
        source_type=source_type,
    )
    record_event(
        session_id,
        "hidden_character_profile_upserted",
        visitor_ip,
        {
            "result": result,
            "source_type": source_type,
            "source_message_ids": source_message_ids,
        },
    )
    if analysis_trace_id:
        record_analysis_trace(
            session_id=session_id,
            trace_id=analysis_trace_id,
            event_type="character_asset",
            visitor_ip=visitor_ip,
            step_name="hidden_character_profile_write",
            payload={"result": result, "decision": decision},
        )
    return result


def normalize_character_library_decision(payload: Dict[str, object]) -> Dict[str, object]:
    action = str(payload.get("action") or "noop").strip().lower()
    if action not in {"noop", "describe", "upsert_character", "delete_character"}:
        action = "noop"
    target_id_raw = payload.get("target_character_id")
    try:
        target_character_id = int(target_id_raw) if target_id_raw not in (None, "") else None
    except Exception:
        target_character_id = None
    character_decision = normalize_character_agent_decision(
        {
            "action": "upsert" if action == "upsert_character" else "noop",
            "reason": payload.get("reason", ""),
            "character": payload.get("character") if isinstance(payload.get("character"), dict) else {},
        }
    )
    directive_payload = payload.get("artifact_directive") if isinstance(payload.get("artifact_directive"), dict) else {}
    artifact_directive = normalize_artifact_directive_decision(
        {
            "action": "upsert" if directive_payload.get("directive") else "noop",
            "reason": payload.get("reason", ""),
            "directive": directive_payload,
        }
    )
    image_tasks: List[Dict[str, str]] = []
    raw_image_tasks = payload.get("image_tasks") if isinstance(payload.get("image_tasks"), list) else []
    for item in raw_image_tasks[:4]:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip().lower()
        if kind in {"reference", "photo", "portrait", "full_body", "full-body"}:
            kind = "photo"
        if kind not in {"avatar", "photo"}:
            continue
        image_tasks.append(
            {
                "kind": kind,
                "prompt_hint": clean_character_text(item.get("prompt_hint"), 600),
            }
        )
    return {
        "action": action,
        "target_character_id": target_character_id,
        "reply": clean_character_text(payload.get("reply"), 1000),
        "reason": clean_character_text(payload.get("reason"), 500),
        "character": character_decision.get("character", {}),
        "artifact_directive": artifact_directive.get("directive", {}),
        "image_tasks": image_tasks,
    }


def parse_character_library_agent_json(text: str) -> Dict[str, object]:
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
            return normalize_character_library_decision(payload)
    return {
        "action": "noop",
        "target_character_id": None,
        "reply": "我没看懂这次要改哪个角色，可以直接点名角色名再说一遍。",
        "reason": "invalid_json",
        "character": {},
        "artifact_directive": {},
        "image_tasks": [],
    }


def load_recent_character_library_messages(session_id: str, limit: int = 12) -> List[Dict[str, object]]:
    max_rows = max(1, min(int(limit), 30))
    with connect_db() as conn:
        rows = conn.execute(
            """
            SELECT id, role, content, created_at, metadata_json
            FROM messages
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (session_id, max_rows),
        ).fetchall()
    result: List[Dict[str, object]] = []
    for row in reversed(rows):
        metadata = safe_json_loads(str(row["metadata_json"] or "{}"))
        result.append(
            {
                "id": int(row["id"]),
                "role": str(row["role"] or ""),
                "content": str(row["content"] or ""),
                "created_at": str(row["created_at"] or ""),
                "metadata": metadata if isinstance(metadata, dict) else {},
            }
        )
    return result


def character_library_message_row_to_payload(row: sqlite3.Row) -> Dict[str, object]:
    metadata = safe_json_loads(str(row["metadata_json"] or "{}"))
    if not isinstance(metadata, dict):
        metadata = {}
    attachments = metadata.get("attachments") if isinstance(metadata.get("attachments"), list) else []
    draw = metadata.get("draw") if isinstance(metadata.get("draw"), dict) else {}
    return {
        "id": int(row["id"]),
        "role": str(row["role"] or ""),
        "content": str(row["content"] or ""),
        "created_at": str(row["created_at"] or ""),
        "attachments": [item for item in attachments if isinstance(item, dict)],
        "draw": draw,
        "metadata": {
            "character_library": True,
            "has_attachments": bool(attachments),
            "has_draw": bool(draw),
        },
    }


def load_character_library_session_messages(session_id: str) -> List[Dict[str, object]]:
    with connect_db() as conn:
        rows = conn.execute(
            """
            SELECT id, role, content, created_at, metadata_json
            FROM messages
            WHERE session_id = ?
              AND status = 'completed'
              AND role IN ('user', 'assistant')
              AND COALESCE(json_extract(metadata_json, '$.character_library'), 0) = 1
            ORDER BY id ASC
            """,
            (session_id,),
        ).fetchall()
    return [character_library_message_row_to_payload(row) for row in rows]


def character_library_session_has_loadable_messages(conn: sqlite3.Connection, session_id: str) -> bool:
    row = conn.execute(
        """
        SELECT COUNT(*) AS message_count
        FROM messages
        WHERE session_id = ?
          AND status = 'completed'
          AND role IN ('user', 'assistant')
          AND COALESCE(json_extract(metadata_json, '$.character_library'), 0) = 1
        """,
        (session_id,),
    ).fetchone()
    return int(row["message_count"] or 0) > 0 if row else False


def previous_character_library_context_candidate(
    conn: sqlite3.Connection,
    current_session_id: str,
) -> Optional[sqlite3.Row]:
    current = conn.execute(
        "SELECT id FROM sessions WHERE id = ?",
        (current_session_id,),
    ).fetchone()
    if current is None:
        return None

    linked_rows = conn.execute(
        "SELECT source_session_id FROM session_context_links WHERE current_session_id = ?",
        (current_session_id,),
    ).fetchall()
    linked_ids = [str(row["source_session_id"]) for row in linked_rows]
    boundary_ids = [session_start_event_id(conn, current_session_id)]
    boundary_ids.extend(session_start_event_id(conn, source_id) for source_id in linked_ids)
    boundary_ids = [value for value in boundary_ids if value > 0]
    boundary_event_id = min(boundary_ids) if boundary_ids else 1 << 60

    excluded = [current_session_id] + linked_ids
    placeholders = ",".join("?" for _ in excluded)
    rows = conn.execute(
        f"""
        SELECT s.id, s.visitor_ip, s.user_agent, s.started_at, s.ended_at, s.end_reason,
               e.id AS start_event_id
        FROM sessions s
        JOIN events e
          ON e.session_id = s.id
         AND e.event_type = 'session_start'
        WHERE s.id NOT IN ({placeholders})
          AND e.id < ?
          AND EXISTS (
              SELECT 1
              FROM messages m
              WHERE m.session_id = s.id
                AND m.status = 'completed'
                AND m.role IN ('user', 'assistant')
                AND COALESCE(json_extract(m.metadata_json, '$.character_library'), 0) = 1
          )
        ORDER BY e.id DESC
        LIMIT 30
        """,
        [*excluded, boundary_event_id],
    ).fetchall()
    for row in rows:
        if character_library_session_has_loadable_messages(conn, str(row["id"])):
            return row
    return None


def has_previous_character_library_context_session(session_id: str) -> bool:
    with connect_db() as conn:
        return previous_character_library_context_candidate(conn, session_id) is not None


def load_previous_character_library_context(session_id: str) -> Dict[str, object]:
    now = utc_now()
    with connect_db() as conn:
        candidate = previous_character_library_context_candidate(conn, session_id)
        if candidate is None:
            return {"loaded": False, "session": None, "messages": [], "has_more": False}
        source_session_id = str(candidate["id"])
        row = conn.execute(
            "SELECT COALESCE(MAX(order_index), 0) AS max_order FROM session_context_links WHERE current_session_id = ?",
            (session_id,),
        ).fetchone()
        next_order = int(row["max_order"] or 0) + 1
        conn.execute(
            """
            INSERT OR IGNORE INTO session_context_links (
                current_session_id, source_session_id, order_index, loaded_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (session_id, source_session_id, next_order, now),
        )
        source_start_event_id = int(candidate["start_event_id"])
        next_candidate = previous_character_library_context_candidate(conn, session_id)
        has_more = bool(next_candidate is not None and int(next_candidate["start_event_id"]) < source_start_event_id)
    return {
        "loaded": True,
        "session": {
            "id": source_session_id,
            "started_at": str(candidate["started_at"]),
            "ended_at": str(candidate["ended_at"] or ""),
            "end_reason": str(candidate["end_reason"] or ""),
        },
        "messages": load_character_library_session_messages(source_session_id),
        "has_more": has_more,
    }


def compact_character_library_directives(limit: int = 50) -> List[Dict[str, object]]:
    try:
        directives = list_active_artifact_directives(limit=limit)
    except Exception:
        return []
    return [
        {
            "id": item.get("id"),
            "directive_type": item.get("directive_type"),
            "subject": item.get("subject"),
            "directive": item.get("directive"),
            "characters": item.get("characters"),
            "series_title": item.get("series_title"),
            "priority": item.get("priority"),
        }
        for item in directives
    ]


def format_character_library_agent_context(
    session_id: str,
    user_message: str,
    attachments: List[ChatAttachment],
    uploaded_images: Optional[List[Dict[str, object]]] = None,
    draw_batch: Optional[Dict[str, object]] = None,
) -> str:
    all_profiles = list_active_character_profiles(limit=200)
    mentioned_profiles = character_profiles_mentioned_in_text(user_message, limit=30)
    profiles = merge_character_profile_order(mentioned_profiles, all_profiles)
    recent_messages = load_recent_character_library_messages(session_id)
    lines = [
        "当前用户输入：",
        clean_character_text(user_message, 2400),
        "",
        "本轮附件：",
    ]
    for attachment in attachments[:MAX_CHAT_ATTACHMENTS]:
        lines.append(
            json.dumps(
                {
                    "name": attachment.name,
                    "mime_type": attachment.mime_type,
                    "size": attachment.size,
                    "note": "用户上传图片，具体像素内容已进入对话上下文；如用户要求作为参考图，等待生成/保存后的 image id 或使用文字说明更新角色。",
                },
                ensure_ascii=False,
            )
        )
    if not attachments:
        lines.append("[]")
    lines.append("")
    if uploaded_images:
        lines.append("本轮上传图片已保存为角色库图片：")
        lines.append(json.dumps(uploaded_images, ensure_ascii=False)[:4000])
        lines.append("")
    if draw_batch:
        lines.append("本轮新生成图片：")
        lines.append(json.dumps(draw_batch, ensure_ascii=False)[:5000])
        lines.append("")
    lines.append("本轮输入直接提到的角色（必须优先作为 target_character_id 候选）：")
    if mentioned_profiles:
        for profile in mentioned_profiles:
            lines.append(
                json.dumps(
                    {
                        "id": profile.get("id"),
                        "canonical_name": profile.get("canonical_name"),
                        "aliases": profile.get("aliases"),
                        "visual_prompt": clean_character_text(profile.get("visual_prompt"), 2600),
                        "negative_prompt": clean_character_text(profile.get("negative_prompt"), 600),
                        "personality": clean_character_text(profile.get("personality"), 1000),
                        "background": clean_character_text(profile.get("background"), 1400),
                        "relationships": profile.get("relationships"),
                        "reference_image_count": len(normalize_character_image_ids(profile.get("reference_image_ids") or [])),
                        "avatar_image_count": len(normalize_character_image_ids(profile.get("avatar_image_ids") or [])),
                        "updated_at": profile.get("updated_at"),
                    },
                    ensure_ascii=False,
                )
            )
    else:
        lines.append("[]")
    lines.append("")
    lines.append("全量角色名索引（用来判断角色是否存在；不要因为后面的详细资料太长就说角色不存在）：")
    lines.append(
        json.dumps(
            [
                {
                    "id": profile.get("id"),
                    "canonical_name": profile.get("canonical_name"),
                    "aliases": profile.get("aliases"),
                    "updated_at": profile.get("updated_at"),
                }
                for profile in all_profiles
            ],
            ensure_ascii=False,
        )
    )
    lines.append("")
    lines.append("现有角色详细资料（点名角色优先，其后按更新时间）：")
    for profile in profiles:
        lines.append(
            json.dumps(
                {
                    "id": profile.get("id"),
                    "canonical_name": profile.get("canonical_name"),
                    "aliases": profile.get("aliases"),
                    "visual_prompt": clean_character_text(profile.get("visual_prompt"), 1600),
                    "negative_prompt": clean_character_text(profile.get("negative_prompt"), 500),
                    "personality": clean_character_text(profile.get("personality"), 700),
                    "background": clean_character_text(profile.get("background"), 900),
                    "relationships": profile.get("relationships"),
                    "reference_image_count": len(normalize_character_image_ids(profile.get("reference_image_ids") or [])),
                    "avatar_image_count": len(normalize_character_image_ids(profile.get("avatar_image_ids") or [])),
                    "updated_at": profile.get("updated_at"),
                },
                ensure_ascii=False,
            )
        )
    lines.append("")
    directives = compact_character_library_directives()
    lines.append("现有成果小剧场/成果写作指令：")
    lines.append(json.dumps(directives, ensure_ascii=False)[:5000] if directives else "[]")
    lines.append("")
    lines.append("最近角色库对话：")
    for item in recent_messages:
        lines.append(f"[message id={item.get('id')} role={item.get('role')} time={item.get('created_at')}]")
        lines.append(clean_character_text(item.get("content"), 1200))
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        draw = metadata.get("draw") if isinstance(metadata.get("draw"), dict) else {}
        if draw:
            lines.append("draw_metadata=" + json.dumps(draw, ensure_ascii=False)[:2400])
        lines.append("")
    return "\n".join(lines)


def call_character_library_agent_model(context: str) -> Dict[str, object]:
    client, http_client, model_slot = openai_client_for_slot(MODEL_SLOT_BACKGROUND, timeout=HIDDEN_CHARACTER_AGENT_TIMEOUT)
    try:
        resp = client.chat.completions.create(
            **model_completion_kwargs(model_slot),
            messages=[
                {"role": "system", "content": CHARACTER_LIBRARY_AGENT_SYSTEM_PROMPT},
                {"role": "user", "content": context},
            ],
            temperature=HIDDEN_CHARACTER_AGENT_TEMPERATURE,
            top_p=HIDDEN_CHARACTER_AGENT_TOP_P,
            max_tokens=HIDDEN_CHARACTER_AGENT_MAX_TOKENS,
        )
        content = (resp.choices[0].message.content or "").strip()
        _, answer = split_think_text(content)
        decision = parse_character_library_agent_json(answer)
        decision["model"] = str(model_slot.get("model") or MODEL_NAME)
        return decision
    finally:
        http_client.close()


def apply_character_library_agent_decision(
    decision: Dict[str, object],
    session_id: str,
    visitor_ip: str,
    source_message_ids: List[int],
    allowed_image_ids: Optional[List[int]] = None,
) -> Dict[str, object]:
    action = str(decision.get("action") or "noop")
    result: Dict[str, object] = {"action": action, "character": None, "directive": None}
    target_id = decision.get("target_character_id")
    if action == "delete_character" and target_id:
        try:
            profile = get_character_library_profile(int(target_id))
            result["character"] = {
                "status": "delete_confirmation_required",
                "id": int(target_id),
                "canonical_name": str(profile.get("canonical_name") or f"#{target_id}"),
            }
        except Exception:
            result["character"] = {"status": "not_found", "id": int(target_id)}
    elif action == "upsert_character":
        character = decision.get("character") if isinstance(decision.get("character"), dict) else {}
        allowed_image_id_set = set(normalize_character_image_ids(allowed_image_ids or []))
        if allowed_image_id_set:
            filtered_reference_ids = [
                item for item in normalize_character_image_ids(character.get("reference_image_ids")) if item in allowed_image_id_set
            ]
            filtered_avatar_ids = [
                item for item in normalize_character_image_ids(character.get("avatar_image_ids")) if item in allowed_image_id_set
            ]
            character = {
                **character,
                "reference_image_ids": filtered_reference_ids,
                "avatar_image_ids": filtered_avatar_ids,
            }
        else:
            character = {
                **character,
                "reference_image_ids": [],
                "avatar_image_ids": [],
            }
        if target_id and not character.get("canonical_name"):
            try:
                existing = get_character_library_profile(int(target_id))
                character["canonical_name"] = existing.get("canonical_name", "")
                character["aliases"] = existing.get("aliases", [])
            except Exception:
                pass
        upsert_decision = {
            "action": "upsert",
            "reason": decision.get("reason", ""),
            "character": character,
            "target_character_id": target_id,
            "allow_image_patch": bool(allowed_image_id_set),
        }
        result["character"] = upsert_hidden_character_profile(
            upsert_decision,
            session_id=session_id,
            visitor_ip=visitor_ip,
            source_message_ids=source_message_ids,
            source_type="character_library",
        )
        maybe_start_character_avatar_job(result["character"], visitor_ip)
        maybe_start_character_image_tasks(result["character"], decision.get("image_tasks"), visitor_ip)
        maybe_start_character_photo_job_if_missing(result["character"], visitor_ip)
    artifact_directive = decision.get("artifact_directive") if isinstance(decision.get("artifact_directive"), dict) else {}
    if artifact_directive.get("directive"):
        directive_decision = {
            "action": "upsert",
            "reason": decision.get("reason", ""),
            "directive": artifact_directive,
        }
        result["directive"] = upsert_hidden_artifact_directive(
            directive_decision,
            session_id=session_id,
            visitor_ip=visitor_ip,
            source_message_ids=source_message_ids,
        )
    maybe_record_character_operation_memory(decision, result, visitor_ip, session_id=session_id)
    return result


def maybe_start_character_avatar_job(character_result: object, visitor_ip: str) -> None:
    if not isinstance(character_result, dict):
        return
    try:
        character_id = int(character_result.get("character_id") or character_result.get("id") or 0)
    except Exception:
        character_id = 0
    if character_id <= 0:
        return

    def worker() -> None:
        try:
            ensure_character_avatar_image(character_id, visitor_ip)
        except Exception as exc:
            record_event(
                None,
                "character_avatar_generation_error",
                visitor_ip,
                {"character_id": character_id, "error": str(exc)},
            )

    thread = threading.Thread(target=worker, daemon=True, name=f"character-avatar-{character_id}")
    thread.start()


def maybe_start_character_photo_job_if_missing(character_result: object, visitor_ip: str) -> None:
    if not isinstance(character_result, dict):
        return
    try:
        character_id = int(character_result.get("character_id") or character_result.get("id") or 0)
    except Exception:
        character_id = 0
    if character_id <= 0:
        return

    def worker() -> None:
        try:
            profile = character_profile_by_id(character_id)
            if normalize_character_image_ids(profile.get("reference_image_ids") or []):
                return
            if not clean_character_text(profile.get("visual_prompt"), 500):
                return
            generate_character_image(character_id, "photo", visitor_ip)
        except Exception as exc:
            record_event(
                None,
                "character_photo_generation_error",
                visitor_ip,
                {"character_id": character_id, "error": str(exc)},
            )

    thread = threading.Thread(target=worker, daemon=True, name=f"character-photo-{character_id}")
    thread.start()


def character_profile_by_id(character_id: int) -> Dict[str, object]:
    with connect_db() as conn:
        row = conn.execute(
            "SELECT * FROM hidden_character_profiles WHERE id = ? AND status = 'active' LIMIT 1",
            (int(character_id),),
        ).fetchone()
    if not row:
        raise KeyError("character not found")
    return row_to_character_profile(row)


def append_character_image_ids(
    character_id: int,
    image_ids: List[int],
    kind: str,
    source_session_id: str = "",
    source_message_ids: Optional[List[int]] = None,
    reason: str = "manual or automatic character image generation",
) -> Dict[str, object]:
    ids = normalize_character_image_ids(image_ids)
    if not ids:
        return {"status": "skipped", "reason": "no_image_ids"}
    profile = character_profile_by_id(int(character_id))
    field = "avatar_image_ids_json" if kind == "avatar" else "reference_image_ids_json"
    existing_key = "avatar_image_ids" if kind == "avatar" else "reference_image_ids"
    merged = merge_character_lists(
        normalize_character_image_ids(profile.get(existing_key) or []),
        ids,
        max_items=12 if kind == "avatar" else 24,
    )
    now = utc_now()
    with connect_db() as conn:
        conn.execute(
            f"""
            UPDATE hidden_character_profiles
            SET {field} = ?, updated_at = ?
            WHERE id = ? AND status = 'active'
            """,
            (json.dumps(merged, ensure_ascii=False), now, int(character_id)),
        )
        conn.execute(
            """
            INSERT INTO hidden_character_profile_events (
                character_id, event_type, source_type, source_session_id,
                source_message_ids_json, patch_json, reason, created_at
            )
            VALUES (?, ?, 'character_library', ?, ?, ?, ?, ?)
            """,
            (
                int(character_id),
                "avatar_generate" if kind == "avatar" else "photo_generate",
                str(source_session_id or ""),
                json.dumps(normalize_character_image_ids(source_message_ids or []), ensure_ascii=False),
                json.dumps({existing_key: ids}, ensure_ascii=False),
                clean_character_text(reason, 500),
                now,
            ),
        )
    sync_character_global_memory(int(character_id))
    return {"status": "updated", "character_id": int(character_id), "kind": kind, "image_ids": ids}


def attach_character_scene_images(
    prompt_text: str,
    draw_batch: Dict[str, object],
    session_id: str,
    visitor_ip: str,
    source_message_ids: Optional[List[int]] = None,
) -> Dict[str, object]:
    images = draw_batch.get("images") if isinstance(draw_batch.get("images"), list) else []
    image_ids = normalize_character_image_ids([image.get("id") for image in images if isinstance(image, dict)])
    if not image_ids:
        return {"status": "skipped", "reason": "no_image_ids", "characters": [], "image_ids": []}
    optimized_prompt = clean_character_text(draw_batch.get("optimized_prompt"), 4000)
    search_text = "\n".join([str(prompt_text or ""), optimized_prompt])
    profiles = character_profiles_mentioned_in_text(search_text, limit=16)
    if not profiles:
        record_event(
            session_id,
            "character_scene_images_unmatched",
            visitor_ip,
            {"image_ids": image_ids, "prompt_preview": clean_character_text(prompt_text, 300)},
        )
        return {"status": "skipped", "reason": "no_matching_character", "characters": [], "image_ids": image_ids}
    linked: List[Dict[str, object]] = []
    for profile in profiles:
        character_id = int(profile.get("id") or 0)
        if character_id <= 0:
            continue
        append_character_image_ids(
            character_id,
            image_ids,
            "photo",
            source_session_id=session_id,
            source_message_ids=source_message_ids or [],
            reason="character scene image generated from character library chat",
        )
        linked.append(
            {
                "id": character_id,
                "canonical_name": str(profile.get("canonical_name") or ""),
                "image_ids": image_ids,
            }
        )
    record_event(
        session_id,
        "character_scene_images_attached",
        visitor_ip,
        {
            "image_ids": image_ids,
            "characters": linked,
            "prompt_preview": clean_character_text(prompt_text, 300),
        },
    )
    for item in linked:
        try:
            sync_character_global_memory(int(item.get("id") or 0))
        except Exception:
            pass
    return {"status": "updated", "characters": linked, "image_ids": image_ids}


def character_image_prompt(profile: Dict[str, object], kind: str, prompt_hint: str = "") -> str:
    name = clean_character_text(profile.get("canonical_name"), 120) or "character"
    visual_prompt = clean_character_text(profile.get("visual_prompt"), 2200)
    personality = clean_character_text(profile.get("personality"), 600)
    background = clean_character_text(profile.get("background"), 700)
    hint = clean_character_text(prompt_hint, 700)
    if kind == "avatar":
        base = (
            f"Extreme close-up avatar portrait of {name}, face pushed directly toward the camera, big face close to lens. "
            "The face must fill 80-90% of the entire image area, from forehead/hairline to chin, with eyes, nose, mouth, cheeks, hairline, and facial temperament clearly visible. "
            "Tight crop, front-facing or slight three-quarter face, centered headshot, camera very close, no empty background space. "
            "Only show face, hair, ears, neck edge, and at most a tiny hint of collar; do not show shoulders, torso, arms, hands, waist, legs, full outfit, full costume silhouette, standing pose, or wide environmental scene. "
            "Highly recognizable facial features, consistent hairstyle, hair color, eye expression, signature face details, realistic lighting, sharp detailed eyes, high quality."
        )
    else:
        base = (
            f"Full-body or half-body character reference photo of {name}. "
            "Show the character's recognizable outfit, body silhouette, hairstyle, color palette, props, and overall temperament. "
            "Natural pose, coherent environment, high quality, useful as a reusable character reference."
        )
    parts = [base]
    if visual_prompt:
        parts.append(f"Character visual reference: {visual_prompt}")
    if personality:
        parts.append(f"Personality cues: {personality}")
    if background:
        parts.append(f"Background and story cues: {background}")
    if hint:
        parts.append(f"Additional image focus: {hint}")
    if kind == "avatar":
        parts.append(
            "Final avatar crop constraint: this is a big-face headshot only. The face must dominate the frame; crop out body and most clothing. Ignore any full-body, half-body, fashion pose, or environment framing implied elsewhere."
        )
    return " ".join(parts)


def generate_character_image(character_id: int, kind: str, visitor_ip: str, prompt_hint: str = "") -> Dict[str, object]:
    normalized_kind = "avatar" if str(kind or "").strip().lower() == "avatar" else "photo"
    profile = character_profile_by_id(int(character_id))
    status = public_image_model_status()
    if not status.get("available"):
        raise RuntimeError("图像生成模型未配置或不可用，无法生成图片")
    prompt = character_image_prompt(profile, normalized_kind, prompt_hint=prompt_hint)
    negative_prompt = str(profile.get("negative_prompt") or DEFAULT_IMAGE_NEGATIVE_PROMPT)
    if normalized_kind == "avatar":
        negative_prompt = ", ".join(
            item
            for item in [
                negative_prompt,
                "small face",
                "tiny face",
                "distant face",
                "full body",
                "half body",
                "upper body",
                "standing pose",
                "torso",
                "arms",
                "hands",
                "legs",
                "feet",
                "wide shot",
                "medium shot",
                "environmental portrait",
                "large background area",
                "full outfit",
            ]
            if str(item or "").strip()
        )
    decision = {
        "optimized_prompt": prompt,
        "negative_prompt": negative_prompt,
        "aspect_ratio": "1:1",
        "short_caption": f"{profile.get('canonical_name') or '角色'} {'头像' if normalized_kind == 'avatar' else '照片'}",
    }
    batch = generate_image_batch(
        original_prompt=decision["short_caption"],
        decision=decision,
        source_type=f"character_{normalized_kind}",
        source_id=character_id,
        count=1,
    )
    images = batch.get("images") if isinstance(batch.get("images"), list) else []
    image_ids = normalize_character_image_ids([image.get("id") for image in images if isinstance(image, dict)])
    append_result = append_character_image_ids(int(character_id), image_ids, normalized_kind)
    record_event(
        None,
        "character_image_generated",
        visitor_ip,
        {
            "character_id": int(character_id),
            "kind": normalized_kind,
            "image_ids": image_ids,
            "batch_id": batch.get("batch_id", ""),
        },
    )
    return {
        "status": append_result.get("status", "updated"),
        "kind": normalized_kind,
        "batch": batch,
        "image_ids": image_ids,
        "character": get_character_library_profile(int(character_id)),
    }


def maybe_start_character_image_tasks(character_result: object, image_tasks: object, visitor_ip: str) -> None:
    if not isinstance(character_result, dict) or not isinstance(image_tasks, list) or not image_tasks:
        return
    try:
        character_id = int(character_result.get("character_id") or character_result.get("id") or 0)
    except Exception:
        character_id = 0
    if character_id <= 0:
        return

    def worker() -> None:
        for task in image_tasks[:4]:
            if not isinstance(task, dict):
                continue
            kind = str(task.get("kind") or "photo").strip().lower()
            if kind not in {"avatar", "photo"}:
                continue
            try:
                generate_character_image(
                    character_id,
                    kind,
                    visitor_ip,
                    prompt_hint=str(task.get("prompt_hint") or ""),
                )
            except Exception as exc:
                record_event(
                    None,
                    "character_image_task_error",
                    visitor_ip,
                    {"character_id": character_id, "kind": kind, "error": str(exc)},
                )

    thread = threading.Thread(target=worker, daemon=True, name=f"character-image-tasks-{character_id}")
    thread.start()


def delete_character_image(character_id: int, image_id: int, visitor_ip: str) -> Dict[str, object]:
    profile = character_profile_by_id(int(character_id))
    avatar_ids = normalize_character_image_ids(profile.get("avatar_image_ids") or [])
    reference_ids = normalize_character_image_ids(profile.get("reference_image_ids") or [])
    target_id = int(image_id)
    if target_id not in avatar_ids and target_id not in reference_ids:
        raise KeyError("image not found")
    total_images = len(set(avatar_ids + reference_ids))
    if total_images <= 1:
        raise ValueError("角色至少需要保留一张图片")
    new_avatar_ids = [item for item in avatar_ids if item != target_id]
    new_reference_ids = [item for item in reference_ids if item != target_id]
    now = utc_now()
    with connect_db() as conn:
        conn.execute(
            """
            UPDATE hidden_character_profiles
            SET avatar_image_ids_json = ?, reference_image_ids_json = ?,
                revision_count = revision_count + 1, updated_at = ?
            WHERE id = ? AND status = 'active'
            """,
            (
                json.dumps(new_avatar_ids, ensure_ascii=False),
                json.dumps(new_reference_ids, ensure_ascii=False),
                now,
                int(character_id),
            ),
        )
        conn.execute(
            """
            INSERT INTO hidden_character_profile_events (
                character_id, event_type, source_type, source_session_id,
                source_message_ids_json, patch_json, reason, created_at
            )
            VALUES (?, 'image_delete', 'character_library_ui', '', '[]', ?, 'manual image delete', ?)
            """,
            (
                int(character_id),
                json.dumps({"deleted_image_id": target_id}, ensure_ascii=False),
                now,
            ),
        )
    record_event(
        None,
        "character_image_deleted",
        visitor_ip,
        {"character_id": int(character_id), "image_id": target_id},
    )
    sync_character_global_memory(int(character_id))
    return {"ok": True, "character": get_character_library_profile(int(character_id))}


def ensure_character_avatar_image(character_id: int, visitor_ip: str) -> Dict[str, object]:
    try:
        profile = character_profile_by_id(int(character_id))
    except KeyError:
        return {"status": "not_found"}
    if normalize_character_image_ids(profile.get("avatar_image_ids") or []):
        return {"status": "exists"}
    visual_prompt = clean_character_text(profile.get("visual_prompt"), 1800)
    if not visual_prompt:
        return {"status": "missing_visual_prompt"}
    try:
        return generate_character_image(int(character_id), "avatar", visitor_ip)
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def maybe_record_character_operation_memory(
    decision: Dict[str, object],
    result: Dict[str, object],
    visitor_ip: str,
    session_id: str = "",
) -> None:
    action = str(result.get("action") or decision.get("action") or "noop")
    character_result = result.get("character") if isinstance(result.get("character"), dict) else {}
    if action not in {"upsert_character", "delete_character"} or not character_result:
        return
    name = str(character_result.get("canonical_name") or "").strip()
    if not name and character_result.get("id"):
        try:
            profile = get_character_library_profile(int(character_result["id"]))
            name = str(profile.get("canonical_name") or "").strip()
        except Exception:
            name = f"#{character_result.get('id')}"
    if not name:
        return
    status = str(character_result.get("status") or "")
    if status == "delete_confirmation_required":
        return
    verb = "创建" if status == "create" else "删除" if action == "delete_character" else "更新"
    reason = clean_character_text(decision.get("reason"), 260)
    record_event(
        session_id or None,
        "character_library_operation_logged",
        visitor_ip,
        {
            "action": action,
            "status": status,
            "verb": verb,
            "character": name,
            "reason": reason,
        },
    )


def default_character_library_reply(decision: Dict[str, object], result: Dict[str, object]) -> str:
    reply = clean_character_text(decision.get("reply"), 1200)
    if reply:
        return reply
    action = str(decision.get("action") or "noop")
    character = result.get("character") if isinstance(result.get("character"), dict) else {}
    directive = result.get("directive") if isinstance(result.get("directive"), dict) else {}
    if action == "upsert_character" and character.get("canonical_name"):
        return f"已更新 {character.get('canonical_name')} 的角色设定。"
    if action == "delete_character":
        if character.get("status") == "delete_confirmation_required":
            return f"要删除 {character.get('canonical_name') or '这个角色'} 吗？我会先弹窗确认。"
        return "已把这个角色从角色库里隐藏。"
    if directive:
        return "已更新这个角色在成果小剧场里的使用方式。"
    return "我看了一下，这次没有需要写入角色库的改动。"


def maybe_start_hidden_character_agent_job(
    session_id: str,
    visitor_ip: str,
    user_message: str,
    source_message_ids: List[int],
    source_type: str = "chat",
    mode: str = "chat",
    draw_batch: Optional[Dict[str, object]] = None,
    analysis_trace_id: str = "",
) -> bool:
    if not should_run_hidden_character_agent(
        user_message,
        mode=mode,
        has_draw_batch=bool(draw_batch and draw_batch.get("images")),
    ):
        return False

    def worker() -> None:
        try:
            run_hidden_character_agent(
                session_id=session_id,
                visitor_ip=visitor_ip,
                user_message=user_message,
                source_message_ids=source_message_ids,
                source_type=source_type,
                mode=mode,
                draw_batch=draw_batch,
                analysis_trace_id=analysis_trace_id,
            )
        except Exception as exc:
            record_event(
                session_id,
                "hidden_character_agent_error",
                visitor_ip,
                {"error": str(exc), "source_type": source_type},
            )
            if analysis_trace_id:
                record_analysis_trace(
                    session_id=session_id,
                    trace_id=analysis_trace_id,
                    event_type="model_call_error",
                    visitor_ip=visitor_ip,
                    step_name="hidden_character_agent_model",
                    payload={"error": str(exc), "source_type": source_type},
                )

    thread = threading.Thread(target=worker, daemon=True, name=f"hidden-character-agent-{session_id[:8]}")
    thread.start()
    return True


def character_profile_matches_message(profile: Dict[str, object], message: str) -> bool:
    text = str(message or "").lower()
    if not text:
        return False
    names = [str(profile.get("canonical_name") or ""), *[str(alias) for alias in profile.get("aliases", [])]]
    for name in names:
        clean_name = name.strip()
        if clean_name and clean_name.lower() in text:
            return True
    return False


def compact_character_profile(profile: Dict[str, object], max_prompt_chars: int = 900) -> str:
    lines = [f"[固定角色 #{profile.get('id')}] {profile.get('canonical_name') or '未命名角色'}"]
    aliases = [str(item) for item in profile.get("aliases", []) if str(item).strip()]
    if aliases:
        lines.append(f"别名：{'、'.join(aliases[:8])}")
    if profile.get("visual_prompt"):
        lines.append(f"形象 prompt：{clean_character_text(profile.get('visual_prompt'), max_prompt_chars)}")
    if profile.get("negative_prompt"):
        lines.append(f"negative prompt：{clean_character_text(profile.get('negative_prompt'), 360)}")
    if profile.get("personality"):
        lines.append(f"性格：{clean_character_text(profile.get('personality'), 500)}")
    if profile.get("background"):
        lines.append(f"背景：{clean_character_text(profile.get('background'), 700)}")
    relationships = [str(item) for item in profile.get("relationships", []) if str(item).strip()]
    if relationships:
        lines.append(f"关系：{'；'.join(relationships[:6])}")
    image_ids = profile.get("reference_image_ids", [])
    if image_ids:
        lines.append(f"参考图 ID：{', '.join(str(item) for item in image_ids[:8])}")
    avatar_image_ids = profile.get("avatar_image_ids", [])
    if avatar_image_ids:
        lines.append(f"头像图 ID：{', '.join(str(item) for item in avatar_image_ids[:6])}")
    return "\n".join(lines)


def format_hidden_character_context_for_chat(user_message: str, limit: int = HIDDEN_CHARACTER_CHAT_CONTEXT_LIMIT) -> str:
    matched: List[Dict[str, object]] = []
    active_profiles = list_active_character_profiles(limit=80)
    for profile in active_profiles:
        if character_profile_matches_message(profile, user_message):
            matched.append(profile)
        if len(matched) >= max(1, int(limit)):
            break
    if not matched:
        text = str(user_message or "")
        pronoun_reference = any(token in text for token in ("这个角色", "这个人", "这个人设", "她", "他", "它"))
        intro_intent = any(token in text for token in ("介绍", "设定", "人设", "形象", "背景", "性格", "是谁"))
        if pronoun_reference and intro_intent:
            matched = active_profiles[: max(1, min(int(limit), 2))]
    if not matched:
        return ""
    lines = [CHARACTER_CONTEXT_HEADER, ""]
    for profile in matched:
        lines.append(compact_character_profile(profile))
        lines.append("")
    return "\n".join(lines).strip()


def format_hidden_character_context_for_artifacts(limit: int = HIDDEN_CHARACTER_ARTIFACT_CONTEXT_LIMIT) -> str:
    profiles = list_active_character_profiles(limit=max(1, int(limit)))
    if not profiles:
        return ""
    lines = [ARTIFACT_CHARACTER_CONTEXT_HEADER, ""]
    for profile in profiles:
        lines.append(compact_character_profile(profile, max_prompt_chars=700))
        lines.append("")
    return "\n".join(lines).strip()
