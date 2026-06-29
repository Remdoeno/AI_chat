# Image generation capability layer. Chat, artifacts, and comments call this
# module instead of talking to a concrete image service directly.

CHAT_DRAW_IMAGE_COUNT = 4
DEFAULT_IMAGE_NEGATIVE_PROMPT = "low quality, blurry, distorted face, extra limbs, bad anatomy, watermark, text, signature"
DISALLOWED_NEGATIVE_PROMPT_TERMS = {
    "adult content",
    "bare skin",
    "erotic",
    "naked",
    "nude",
    "nudity",
    "porn",
    "pornographic",
    "explicit",
    "nsfw",
    "fully nude",
    "sexual",
    "sex act",
    "裸体",
    "裸露",
    "色情",
    "成人内容",
    "性行为",
}
IMAGE_OUTPUT_DIR = STATIC_DIR / "generated_images"
IMAGE_PUBLIC_PREFIX = "/static/generated_images"
IMAGE_STATUS_TIMEOUT = float(os.environ.get("WANGCAI_IMAGE_STATUS_TIMEOUT", "3"))
IMAGE_GENERATION_TIMEOUT = float(os.environ.get("WANGCAI_IMAGE_GENERATION_TIMEOUT", "300"))
IMAGE_PROMPT_TIMEOUT = float(os.environ.get("WANGCAI_IMAGE_PROMPT_TIMEOUT", "45"))
HIDREAM_DEFAULT_IMAGE_SIZE = int(os.environ.get("WANGCAI_HIDREAM_IMAGE_SIZE", "1024"))
LOCAL_IMAGE_PORT_CANDIDATES_FOR_GENERATION = [
    int(port.strip())
    for port in os.environ.get("WANGCAI_LOCAL_IMAGE_PORTS", "8002").split(",")
    if port.strip().isdigit()
]


def chat_draw_image_count(_decision: object = None) -> int:
    return CHAT_DRAW_IMAGE_COUNT


def image_slot_config() -> Dict[str, object]:
    return model_slot_config(MODEL_SLOT_IMAGE)


def public_image_model_status() -> Dict[str, object]:
    status = image_generation_status()
    return {
        "available": bool(status.get("available")),
        "reason": status.get("reason", ""),
        "provider": status.get("provider", ""),
        "model": status.get("model", ""),
        "display_name": status.get("display_name", ""),
        "base_url": status.get("base_url", ""),
        "error": status.get("error", ""),
    }


def image_generation_status() -> Dict[str, object]:
    slot = image_slot_config()
    provider = str(slot.get("provider") or "none").strip().lower()
    base_url = str(slot.get("base_url") or "").strip().rstrip("/")
    model = str(slot.get("model") or "").strip()
    display_name = str(slot.get("display_name") or model or "").strip()
    if provider in {"", "none"} or not base_url or not model:
        detected = detect_local_image_generation_service()
        if detected.get("available"):
            return detected
        return {
            "available": False,
            "reason": "not_configured",
            "provider": provider or "none",
            "model": model,
            "display_name": display_name,
            "base_url": base_url,
            "error": "",
        }
    probe = probe_image_generation_service(slot)
    return {
        "available": bool(probe.get("ok")),
        "reason": "ok" if probe.get("ok") else "unavailable",
        "provider": provider,
        "model": model,
        "display_name": display_name,
        "base_url": base_url,
        "error": str(probe.get("error") or ""),
    }


def detect_local_image_generation_service() -> Dict[str, object]:
    for port in LOCAL_IMAGE_PORT_CANDIDATES_FOR_GENERATION:
        base_url = f"http://127.0.0.1:{int(port)}"
        slot = {
            "provider": "hidream",
            "display_name": IMAGE_MODEL_DISPLAY_NAME,
            "base_url": base_url,
            "model": IMAGE_MODEL_DISPLAY_NAME,
            "api_key": "",
            "use_proxy": False,
            "proxy_url": "",
        }
        probe = probe_image_generation_service(slot)
        if probe.get("ok"):
            return {
                "available": True,
                "reason": "detected_local",
                "provider": "hidream",
                "model": IMAGE_MODEL_DISPLAY_NAME,
                "display_name": IMAGE_MODEL_DISPLAY_NAME,
                "base_url": base_url,
                "error": "",
            }
    return {"available": False}


def image_model_headers(slot: Dict[str, object]) -> Dict[str, str]:
    api_key = str(slot.get("api_key") or "").strip()
    if api_key and api_key != "EMPTY":
        return {"Authorization": f"Bearer {api_key}"}
    return {}


def probe_image_generation_service(slot: Dict[str, object]) -> Dict[str, object]:
    base_url = str(slot.get("base_url") or "").strip().rstrip("/")
    if not base_url:
        return {"ok": False, "error": "image base_url is empty"}
    headers = image_model_headers(slot)
    paths = ["/health", "/v1/models", "/models", "/"]
    last_error = ""
    try:
        with model_http_client(slot, timeout=IMAGE_STATUS_TIMEOUT) as client:
            for path in paths:
                try:
                    resp = client.get(f"{base_url}{path}", headers=headers)
                    if resp.status_code < 400 or resp.status_code in {401, 403}:
                        return {"ok": True, "status_code": resp.status_code, "path": path, "error": ""}
                    last_error = f"{path}: HTTP {resp.status_code}"
                except Exception as exc:
                    last_error = f"{path}: {exc}"
    except Exception as exc:
        last_error = str(exc)
    return {"ok": False, "error": last_error or "image service unavailable"}


def clean_image_model_json(text: str) -> Dict[str, object]:
    cleaned = str(text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    try:
        payload = json.loads(cleaned)
    except Exception:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        payload = json.loads(match.group(0)) if match else {}
    return payload if isinstance(payload, dict) else {}


def normalize_draw_prompt_decision(payload: object, original_prompt: str) -> Dict[str, object]:
    data = payload if isinstance(payload, dict) else {}
    optimized = str(data.get("optimized_prompt") or data.get("prompt") or original_prompt).strip()
    negative = sanitize_image_negative_prompt(data.get("negative_prompt"))
    aspect_ratio = str(data.get("aspect_ratio") or "1:1").strip() or "1:1"
    style_tags = data.get("style_tags") if isinstance(data.get("style_tags"), list) else []
    short_caption = str(data.get("short_caption") or "").strip()
    return {
        "optimized_prompt": optimized or original_prompt.strip(),
        "negative_prompt": negative,
        "aspect_ratio": aspect_ratio,
        "image_count": CHAT_DRAW_IMAGE_COUNT,
        "style_tags": [str(item).strip() for item in style_tags if str(item).strip()][:12],
        "short_caption": short_caption,
    }


def prompt_contains_cjk(text: object) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", str(text or "")))


def translate_draw_text_to_english(
    text: str,
    apply_fields: bool = True,
    session_id: str = "",
    visitor_ip: str = "local",
    analysis_trace_id: str = "",
    step_name: str = "draw_prompt_translate",
) -> str:
    source = apply_professional_prompt_fields(text) if apply_fields else str(text or "").strip()
    if not source:
        return ""
    if not prompt_contains_cjk(source):
        return source
    client, http_client, model_slot = openai_client_for_slot(MODEL_SLOT_BACKGROUND, timeout=IMAGE_PROMPT_TIMEOUT)
    messages = [
        {"role": "system", "content": PROFESSIONAL_DRAW_PROMPT_TRANSLATION_SYSTEM_PROMPT},
        {"role": "user", "content": source},
    ]
    started = time.perf_counter()
    try:
        resp = client.chat.completions.create(
            **model_completion_kwargs(model_slot),
            messages=messages,
            temperature=0.0,
            top_p=1.0,
            max_tokens=max(1200, min(7000, len(source) * 2)),
        )
        _, answer = split_think_text(resp.choices[0].message.content or "")
        payload = clean_image_model_json(answer)
        translated = str(payload.get("translated_prompt") or payload.get("optimized_prompt") or "").strip()
        if analysis_trace_id:
            record_analysis_trace(
                session_id=session_id,
                trace_id=analysis_trace_id,
                event_type="model_call",
                visitor_ip=visitor_ip,
                step_name=step_name,
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
                payload={
                    "model": model_slot.get("model", MODEL_NAME),
                    "messages": messages,
                    "decision": {"translated_prompt": translated},
                    "source_chars": len(source),
                    "translated_chars": len(translated),
                },
            )
        if translated:
            if prompt_contains_cjk(translated):
                record_event(
                    None,
                    "draw_prompt_translation_still_cjk",
                    "local",
                    {"source_chars": len(source), "translated_chars": len(translated)},
                )
            return translated
        return source
    except Exception as exc:
        if analysis_trace_id:
            record_analysis_trace(
                session_id=session_id,
                trace_id=analysis_trace_id,
                event_type="model_call_error",
                visitor_ip=visitor_ip,
                step_name=step_name,
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
                payload={
                    "model": model_slot.get("model", MODEL_NAME),
                    "messages": messages,
                    "error": str(exc),
                },
            )
        record_event(None, "draw_prompt_translate_error", "local", {"error": str(exc), "prompt_chars": len(source)})
        return source
    finally:
        http_client.close()


def translate_draw_context_to_english(context: Optional[str]) -> str:
    raw_context = str(context or "").strip()
    if not raw_context:
        return ""
    if draw_prompt_context_has_previous_prompt(raw_context):
        optimized_match = re.search(
            r"(?ims)^\s*-\s*optimized_prompt\s*:\s*(.*?)(?=^\s*-\s*(?:negative_prompt|aspect_ratio)\s*:|\Z)",
            raw_context,
        )
        negative_match = re.search(
            r"(?ims)^\s*-\s*negative_prompt\s*:\s*(.*?)(?=^\s*-\s*(?:optimized_prompt|aspect_ratio)\s*:|\Z)",
            raw_context,
        )
        optimized_prompt = str(optimized_match.group(1) if optimized_match else "").strip()
        negative_prompt = str(negative_match.group(1) if negative_match else "").strip()
        if optimized_prompt:
            optimized_prompt = translate_draw_text_to_english(optimized_prompt, apply_fields=False)
        if negative_prompt and prompt_contains_cjk(negative_prompt):
            negative_prompt = translate_draw_text_to_english(negative_prompt, apply_fields=False)
        aspect_ratio = extract_aspect_ratio_from_prompt(raw_context)
        return "\n".join(
            [
                "Previous image result:",
                f"- optimized_prompt: {optimized_prompt}",
                f"- negative_prompt: {negative_prompt}",
                f"- aspect_ratio: {aspect_ratio}",
                "If the classification result is revision, use the previous optimized_prompt as the base and output a complete revised English prompt.",
            ]
        ).strip()
    if not prompt_contains_cjk(raw_context):
        return raw_context
    return translate_draw_text_to_english(raw_context, apply_fields=False)


def sanitize_image_negative_prompt(raw_negative: object) -> str:
    parts = [
        re.sub(r"\s+", " ", str(item or "")).strip()
        for item in re.split(r"[,，;；\n]+", str(raw_negative or ""))
    ]
    cleaned: List[str] = []
    seen = set()
    for part in parts:
        if not part:
            continue
        lowered = part.lower()
        if any(term in lowered for term in DISALLOWED_NEGATIVE_PROMPT_TERMS):
            continue
        if lowered in seen:
            continue
        seen.add(lowered)
        cleaned.append(part)
    return ", ".join(cleaned) or DEFAULT_IMAGE_NEGATIVE_PROMPT


def extract_aspect_ratio_from_prompt(text: str) -> str:
    prompt = str(text or "")
    matches = re.findall(r"(?<!\d)([1-9]\d?)\s*[:：]\s*([1-9]\d?)(?!\d)", prompt)
    if matches:
        width, height = matches[-1]
        return f"{int(width)}:{int(height)}"
    lowered = prompt.lower()
    if any(term in lowered for term in ("9:16", "portrait", "vertical")) or any(term in prompt for term in ("竖式", "竖屏", "竖图", "竖构图")):
        return "9:16"
    if any(term in lowered for term in ("16:9", "landscape", "horizontal", "wide shot")) or any(term in prompt for term in ("横式", "横屏", "横图", "宽屏")):
        return "16:9"
    if any(term in lowered for term in ("1:1", "square")) or any(term in prompt for term in ("方图", "方形", "正方形")):
        return "1:1"
    return "1:1"


def extract_negative_prompt_from_professional_prompt(text: str) -> str:
    prompt = str(text or "")
    pattern = re.compile(
        r"(?:negative\s*prompt|negative|反向提示|负面提示|负面词)\s*[:：]\s*(.+?)(?:\n\s*\n|$)",
        flags=re.I | re.S,
    )
    match = pattern.search(prompt)
    if not match:
        return DEFAULT_IMAGE_NEGATIVE_PROMPT
    negative = match.group(1).strip()
    negative = re.split(r"\n(?:positive\s*prompt|正向提示|prompt)\s*[:：]", negative, maxsplit=1, flags=re.I)[0].strip()
    return sanitize_image_negative_prompt(negative)


def professional_draw_prompt_style_tags(text: str) -> List[str]:
    prompt = str(text or "").lower()
    tag_terms = [
        ("phone snapshot", ("手机", "快照", "snapshot")),
        ("realistic", ("真实", "真人", "realistic", "photo")),
        ("portrait", ("portrait", "竖式", "9:16")),
        ("low light", ("凌晨", "弱光", "low light")),
        ("cinematic lighting", ("边缘光", "轮廓光", "hdr", "景深", "lighting")),
        ("pbr skin", ("pbr", "皮肤质感")),
    ]
    tags: List[str] = []
    for tag, terms in tag_terms:
        if any(term in prompt for term in terms):
            tags.append(tag)
    return tags[:8]


def attachment_value(attachment: object, key: str, default: object = "") -> object:
    if isinstance(attachment, dict):
        return attachment.get(key, default)
    return getattr(attachment, key, default)


def image_attachment_refs_b64(attachments: Optional[List[object]]) -> List[str]:
    refs: List[str] = []
    for attachment in attachments or []:
        mime_type = str(attachment_value(attachment, "mime_type") or "")
        data_url = str(attachment_value(attachment, "data_url") or "").strip()
        if mime_type and not mime_type.startswith("image/"):
            continue
        match = IMAGE_DATA_URL_RE.match(data_url)
        if not match:
            continue
        encoded = match.group(2).replace("\n", "").replace("\r", "").strip()
        if encoded:
            refs.append(encoded)
    return refs[:MAX_CHAT_ATTACHMENTS]


IMAGE_MESSAGE_INCOMPATIBLE_PROVIDERS = {"deepseek"}
IMAGE_MESSAGE_COMPATIBLE_MODEL_MARKERS = (
    "vision",
    "vl",
    "omni",
    "gpt-4o",
    "gpt-4.1",
    "gpt-5",
    "qwen",
    "glm-4v",
)
IMAGE_MESSAGE_INCOMPATIBLE_ERROR_MARKERS = (
    "unknown variant image_url",
    "expected text",
    "image_url",
    "invalid_request_error",
    "invalidrequesterror",
)


def model_slot_likely_accepts_image_messages(slot: Dict[str, object]) -> bool:
    provider = str(slot.get("provider") or "").strip().lower()
    model = str(slot.get("model") or "").strip().lower()
    if provider in {"", "none", "hidream"}:
        return False
    if provider in IMAGE_MESSAGE_INCOMPATIBLE_PROVIDERS:
        return False
    if provider == "local":
        return True
    if any(marker in model for marker in IMAGE_MESSAGE_COMPATIBLE_MODEL_MARKERS):
        return True
    return provider == "custom"


def image_message_error_is_incompatible(exc: Exception) -> bool:
    message = str(exc or "").lower()
    return any(marker in message for marker in IMAGE_MESSAGE_INCOMPATIBLE_ERROR_MARKERS)


def model_slot_signature(slot: Dict[str, object]) -> str:
    return "|".join(
        [
            str(slot.get("provider") or "").strip().lower(),
            str(slot.get("base_url") or "").strip().rstrip("/"),
            str(slot.get("model") or "").strip(),
        ]
    )


def draw_reference_image_analysis_slots() -> List[Tuple[str, Dict[str, object], str]]:
    candidates: List[Tuple[str, Dict[str, object], str]] = []
    seen: set = set()
    for label, slot_name in (
        ("聊天模型", MODEL_SLOT_CHAT),
        ("后台模型", MODEL_SLOT_BACKGROUND),
    ):
        try:
            slot = model_slot_config(slot_name)
        except Exception:
            continue
        signature = model_slot_signature(slot)
        if not signature or signature in seen:
            continue
        seen.add(signature)
        if model_slot_likely_accepts_image_messages(slot):
            candidates.append((label, slot, ""))
    if not any(str(slot.get("provider") or "").strip().lower() == "local" for _, slot, _ in candidates):
        try:
            local_slot = default_model_slot("local")
            signature = model_slot_signature(local_slot)
            if signature and signature not in seen:
                candidates.append(("本地兜底模型", local_slot, "configured slots are not known vision-capable"))
        except Exception:
            pass
    return candidates


def openai_client_for_model_slot_config(slot: Dict[str, object], timeout: float) -> Tuple[OpenAI, httpx.Client, Dict[str, object]]:
    http_client = model_http_client(slot, timeout)
    client_kwargs: Dict[str, object] = {}
    if slot.get("provider") == "local":
        client_kwargs["max_retries"] = 0
    client = OpenAI(
        api_key=model_api_key(slot),
        base_url=str(slot.get("base_url") or BASE_URL).rstrip("/"),
        http_client=http_client,
        **client_kwargs,
    )
    return client, http_client, slot


def draw_reference_trace_messages(user_prompt: str, attachments: Optional[List[object]]) -> List[Dict[str, object]]:
    attachment_summaries = []
    for index, attachment in enumerate(attachments or [], start=1):
        if index > MAX_CHAT_ATTACHMENTS:
            break
        attachment_summaries.append(
            {
                "index": index,
                "name": str(attachment_value(attachment, "name") or "image"),
                "mime_type": str(attachment_value(attachment, "mime_type") or ""),
                "size": int(attachment_value(attachment, "size") or 0),
            }
        )
    return [
        {"role": "system", "content": DRAW_REFERENCE_IMAGE_ANALYSIS_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": {
                "text": f"User drawing request: {str(user_prompt or '').strip()}",
                "attachments": attachment_summaries,
                "note": "image data omitted from trace",
            },
        },
    ]


def build_draw_reference_image_context(
    user_prompt: str,
    attachments: Optional[List[object]],
    session_id: str = "",
    visitor_ip: str = "local",
    analysis_trace_id: str = "",
) -> Dict[str, object]:
    refs_b64 = image_attachment_refs_b64(attachments)
    debug: Dict[str, object] = {
        "reference_count": len(refs_b64),
        "reference_prompt": "",
        "negative_prompt": "",
        "short_caption": "",
        "important_constraints": [],
        "context": "",
        "refs_b64": refs_b64,
    }
    if not refs_b64:
        return debug

    parts: List[Dict[str, object]] = [
        {
            "type": "text",
            "text": (
                "Analyze the uploaded reference image(s) for an image-generation pipeline.\n"
                f"User drawing request: {str(user_prompt or '').strip()}\n"
                "Return only the required JSON."
            ),
        }
    ]
    for attachment in attachments or []:
        data_url = str(attachment_value(attachment, "data_url") or "").strip()
        mime_type = str(attachment_value(attachment, "mime_type") or "")
        if mime_type.startswith("image/") and IMAGE_DATA_URL_RE.match(data_url):
            parts.append({"type": "image_url", "image_url": {"url": data_url}})

    messages = [
        {"role": "system", "content": DRAW_REFERENCE_IMAGE_ANALYSIS_SYSTEM_PROMPT},
        {"role": "user", "content": parts},
    ]
    trace_messages = draw_reference_trace_messages(user_prompt, attachments)
    errors: List[Dict[str, object]] = []
    candidate_slots = draw_reference_image_analysis_slots()
    for slot_label, model_slot, fallback_reason in candidate_slots:
        client = None
        http_client = None
        started = time.perf_counter()
        try:
            client, http_client, model_slot = openai_client_for_model_slot_config(model_slot, timeout=IMAGE_PROMPT_TIMEOUT)
            resp = client.chat.completions.create(
                **model_completion_kwargs(model_slot),
                messages=messages,
                temperature=0.1,
                top_p=0.9,
                max_tokens=1800,
            )
            _, answer = split_think_text(resp.choices[0].message.content or "")
            payload = clean_image_model_json(answer)
            reference_prompt = str(payload.get("reference_prompt") or payload.get("prompt") or answer or "").strip()
            constraints = payload.get("important_constraints") if isinstance(payload.get("important_constraints"), list) else []
            debug.update(
                {
                    "reference_prompt": reference_prompt,
                    "negative_prompt": sanitize_image_negative_prompt(payload.get("negative_prompt")),
                    "short_caption": str(payload.get("short_caption") or "").strip(),
                    "important_constraints": [str(item).strip() for item in constraints if str(item).strip()][:12],
                    "model": model_slot.get("model", MODEL_NAME),
                    "model_provider": model_slot.get("provider", ""),
                    "model_slot": slot_label,
                }
            )
            context_lines = [
                "Reference image analysis:",
                f"- reference_count: {len(refs_b64)}",
                "- priority: Treat this as high-priority visual evidence for the uploaded reference image(s). Preserve visible subject appearance, clothing, style, composition cues, and distinctive details unless the user explicitly asks to change them.",
                f"- reference_prompt: {reference_prompt}",
            ]
            if debug["important_constraints"]:
                context_lines.append("- important_constraints: " + "; ".join(debug["important_constraints"]))
            if debug["negative_prompt"]:
                context_lines.append("- reference_negative_prompt: " + str(debug["negative_prompt"]))
            debug["context"] = "\n".join(context_lines).strip()
            if analysis_trace_id:
                record_analysis_trace(
                    session_id=session_id,
                    trace_id=analysis_trace_id,
                    event_type="model_call",
                    visitor_ip=visitor_ip,
                    step_name="draw_reference_image_parse",
                    duration_ms=round((time.perf_counter() - started) * 1000, 3),
                    payload={
                        "model": model_slot.get("model", MODEL_NAME),
                        "provider": model_slot.get("provider", ""),
                        "model_slot": slot_label,
                        "fallback_reason": fallback_reason,
                        "fallback_errors": errors,
                        "messages": trace_messages,
                        "decision": {
                            "reference_prompt": reference_prompt,
                            "important_constraints": debug["important_constraints"],
                            "negative_prompt": debug["negative_prompt"],
                            "short_caption": debug["short_caption"],
                        },
                        "reference_count": len(refs_b64),
                    },
                )
            return debug
        except Exception as exc:
            error_payload = {
                "model": model_slot.get("model", MODEL_NAME),
                "provider": model_slot.get("provider", ""),
                "model_slot": slot_label,
                "error": str(exc),
            }
            errors.append(error_payload)
            if not image_message_error_is_incompatible(exc) and len(errors) >= len(candidate_slots):
                break
        finally:
            if http_client is not None:
                http_client.close()

    debug["error"] = "; ".join(str(item.get("error") or "") for item in errors if item.get("error")) or "no vision-capable model available"
    record_event(session_id or None, "draw_reference_image_parse_error", visitor_ip, {"error": debug["error"], "reference_count": len(refs_b64)})
    if analysis_trace_id:
        record_analysis_trace(
            session_id=session_id,
            trace_id=analysis_trace_id,
            event_type="model_call_error",
            visitor_ip=visitor_ip,
            step_name="draw_reference_image_parse",
            duration_ms=0,
            payload={
                "model": errors[-1].get("model", MODEL_NAME) if errors else "",
                "messages": trace_messages,
                "error": debug["error"],
                "fallback_errors": errors,
                "reference_count": len(refs_b64),
            },
        )
    return debug


def professional_prompt_header_fields(text: str) -> Dict[str, str]:
    fields: Dict[str, str] = {}
    for raw_line in str(text or "").splitlines()[:16]:
        line = raw_line.strip()
        if not line:
            if fields:
                break
            continue
        match = re.match(r"^([^:：]{1,32})\s*[:：]\s*(.+?)\s*$", line)
        if not match:
            continue
        key = re.sub(r"\s+", "", match.group(1))
        value = match.group(2).strip()
        if key and value:
            fields[key] = value
    return fields


def prompt_field_is_empty_world(value: str) -> bool:
    normalized = re.sub(r"\s+", "", str(value or "").strip().lower())
    return normalized in {"", "无", "🈚", "🈚️", "none", "n/a", "na", "null", "no"}


def apply_professional_prompt_fields(text: str) -> str:
    prompt = str(text or "").strip()
    fields = professional_prompt_header_fields(prompt)
    role = (
        fields.get("指定角色")
        or fields.get("角色")
        or fields.get("角色名")
        or fields.get("character")
        or ""
    ).strip()
    world = (
        fields.get("角色所属世界观")
        or fields.get("所属世界观")
        or fields.get("世界观")
        or fields.get("world")
        or ""
    ).strip()

    if role:
        role_world_text = f"{role}角色设定"
        if world and not prompt_field_is_empty_world(world):
            role_world_text = f"{role}所属世界观（{world}）"
        prompt = re.sub(r"\{\s*指定角色\s*\}\s*所属世界观", role_world_text, prompt)
        prompt = re.sub(r"\{\s*角色\s*\}\s*所属世界观", role_world_text, prompt)
        prompt = re.sub(r"\{\s*指定角色\s*\}", role, prompt)
        prompt = re.sub(r"\{\s*角色\s*\}", role, prompt)

    if world:
        world_text = "无特定世界观" if prompt_field_is_empty_world(world) else world
        prompt = re.sub(r"\{\s*角色所属世界观\s*\}", world_text, prompt)
        prompt = re.sub(r"\{\s*所属世界观\s*\}", world_text, prompt)
        prompt = re.sub(r"\{\s*世界观\s*\}", world_text, prompt)

    return prompt


def draw_prompt_context_has_previous_prompt(context: Optional[str]) -> bool:
    return bool(re.search(r"optimized_prompt\s*:", str(context or ""), flags=re.I))


def normalize_draw_prompt_mode(raw_mode: object, has_previous_prompt: bool) -> str:
    mode = str(raw_mode or "natural").strip().lower()
    if mode not in {"natural", "professional", "revision"}:
        mode = "natural"
    if mode == "revision" and not has_previous_prompt:
        return "natural"
    return mode


def classify_draw_prompt_mode(
    user_prompt: str,
    context: Optional[str] = None,
    session_id: str = "",
    visitor_ip: str = "local",
    analysis_trace_id: str = "",
) -> Dict[str, object]:
    raw_prompt = str(user_prompt or "").strip()
    has_previous_prompt = draw_prompt_context_has_previous_prompt(context)
    context_part = str(context or "").strip()
    user_content = "\n".join(
        [
            f"上一版 optimized_prompt 是否可用：{'yes' if has_previous_prompt else 'no'}",
            "",
            "[上下文]",
            context_part if context_part else "无",
            "",
            "[用户本轮输入]",
            raw_prompt,
        ]
    )
    messages = [
        {"role": "system", "content": DRAW_PROMPT_CLASSIFIER_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    client, http_client, model_slot = openai_client_for_slot(MODEL_SLOT_BACKGROUND, timeout=min(IMAGE_PROMPT_TIMEOUT, 20))
    started = time.perf_counter()
    try:
        resp = client.chat.completions.create(
            **model_completion_kwargs(model_slot),
            messages=messages,
            temperature=0.0,
            top_p=1.0,
            max_tokens=260,
        )
        _, answer = split_think_text(resp.choices[0].message.content or "")
        payload = clean_image_model_json(answer)
        mode = normalize_draw_prompt_mode(payload.get("mode"), has_previous_prompt)
        if analysis_trace_id:
            record_analysis_trace(
                session_id=session_id,
                trace_id=analysis_trace_id,
                event_type="model_call",
                visitor_ip=visitor_ip,
                step_name="draw_prompt_classify",
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
                payload={
                    "model": model_slot.get("model", MODEL_NAME),
                    "messages": messages,
                    "decision": {
                        "mode": mode,
                        "reason": str(payload.get("reason") or "").strip(),
                        "has_previous_prompt": has_previous_prompt,
                    },
                },
            )
        return {
            "mode": mode,
            "reason": str(payload.get("reason") or "").strip(),
            "has_previous_prompt": has_previous_prompt,
        }
    except Exception as exc:
        if analysis_trace_id:
            record_analysis_trace(
                session_id=session_id,
                trace_id=analysis_trace_id,
                event_type="model_call_error",
                visitor_ip=visitor_ip,
                step_name="draw_prompt_classify",
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
                payload={
                    "model": model_slot.get("model", MODEL_NAME),
                    "messages": messages,
                    "error": str(exc),
                },
            )
        record_event(None, "draw_prompt_classify_error", "local", {"error": str(exc), "prompt_chars": len(raw_prompt)})
        return {"mode": "natural", "reason": "classifier_error", "has_previous_prompt": has_previous_prompt}
    finally:
        http_client.close()


def translate_professional_draw_prompt(prompt: str) -> str:
    return translate_draw_text_to_english(prompt, apply_fields=True)


def professional_draw_prompt_translation_decision(prompt: str) -> Dict[str, object]:
    processed_prompt = apply_professional_prompt_fields(prompt)
    translated_prompt = translate_professional_draw_prompt(processed_prompt)
    decision = normalize_draw_prompt_decision(
        {
            "optimized_prompt": translated_prompt,
            "negative_prompt": extract_negative_prompt_from_professional_prompt(translated_prompt),
            "aspect_ratio": extract_aspect_ratio_from_prompt(processed_prompt),
            "image_count": CHAT_DRAW_IMAGE_COUNT,
            "style_tags": professional_draw_prompt_style_tags(translated_prompt),
            "short_caption": "",
        },
        translated_prompt,
    )
    return decision


def build_draw_prompt_context(session_id: str, current_message_id: Optional[int] = None) -> str:
    parts: List[str] = []
    try:
        generated = list_generated_images("chat", session_id)
    except Exception:
        generated = []
    recent_generated = [
        item for item in generated
        if str(item.get("optimized_prompt") or "").strip()
    ]
    if recent_generated:
        latest = recent_generated[-1]
        parts.append(
            "\n".join(
                [
                    "最近一次画图结果：",
                    f"- optimized_prompt: {str(latest.get('optimized_prompt') or '').strip()}",
                    f"- negative_prompt: {str(latest.get('negative_prompt') or '').strip()}",
                    f"- aspect_ratio: {str(latest.get('aspect_ratio') or '').strip() or '1:1'}",
                    "如果分类结果为 revision，必须以上一版 optimized_prompt 为基底重新输出完整 prompt。",
                ]
            )
        )
    return "\n\n".join(parts).strip()


def build_draw_memory_context(
    user_message: str,
    session_id: str,
    visitor_ip: str,
    analysis_trace_id: str = "",
    context_messages: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, object]:
    debug: Dict[str, object] = {
        "memory_gate": "skipped",
        "candidate_count": 0,
        "selected_count": 0,
        "retrieval_query": "",
        "context": "",
    }
    memory_gate_messages = [
        {"role": "system", "content": MEMORY_GATE_SYSTEM_PROMPT},
        {"role": "user", "content": build_memory_gate_user_prompt(user_message, context_messages=context_messages)},
    ]
    gate_started = time.perf_counter()
    decision = resolve_memory_gate_decision(
        user_message,
        session_id=session_id,
        visitor_ip=visitor_ip,
        analysis_trace_id="",
        context_messages=context_messages,
    )
    debug["decision"] = decision
    use_memory = bool(decision.get("needs_memory"))
    debug["memory_gate"] = "run" if use_memory else "skipped"
    if analysis_trace_id:
        record_analysis_trace(
            session_id=session_id,
            trace_id=analysis_trace_id,
            event_type="model_call",
            visitor_ip=visitor_ip,
            step_name="draw_memory_gate",
            duration_ms=round((time.perf_counter() - gate_started) * 1000, 3),
            payload={
                "model": model_slot_config(MODEL_SLOT_BACKGROUND).get("model", MODEL_NAME),
                "messages": memory_gate_messages,
                "decision": decision,
                "context_message_count": len(context_messages or []),
            },
        )
    if not use_memory:
        return debug

    retrieval_query = ""
    embedding_started = time.perf_counter()
    try:
        retrieval_query = build_memory_retrieval_query(
            user_message,
            session_id=session_id,
            visitor_ip=visitor_ip,
            analysis_trace_id=analysis_trace_id,
            context_messages=context_messages,
        )
        debug["retrieval_query"] = retrieval_query
        query_vector = embedding_client.embed_text(retrieval_query)
        embedding_duration = (time.perf_counter() - embedding_started) * 1000
        recall_candidates = retrieve_curated_memory_recall_pool(
            query_vector,
            current_session_id=session_id,
            current_visitor_ip=visitor_ip,
            query_text=retrieval_query,
        )
        if analysis_trace_id:
            record_analysis_trace(
                session_id=session_id,
                trace_id=analysis_trace_id,
                event_type="embedding",
                visitor_ip=visitor_ip,
                step_name="draw_memory_query_embedding",
                duration_ms=round(embedding_duration, 3),
                payload={
                    "alias": "embedding1",
                    "model": embedding_client.EMBEDDING_MODEL,
                    "original_message": user_message[:240],
                    "input_preview": retrieval_query[:240],
                    "dim": len(query_vector) if hasattr(query_vector, "__len__") else None,
                    "candidate_memories": analysis_memory_candidate_payload(recall_candidates),
                },
            )
        memories = judge_curated_memories_with_model(
            user_message=user_message,
            retrieval_query=retrieval_query,
            candidates=recall_candidates,
            session_id=session_id,
            visitor_ip=visitor_ip,
            analysis_trace_id=analysis_trace_id,
        )
        record_memory_retrieval(session_id, retrieval_query, memories)
        debug.update(
            {
                "candidate_count": len(recall_candidates),
                "selected_count": len(memories),
                "context": format_curated_memory_context(memories),
            }
        )
        return debug
    except Exception as exc:
        record_event(session_id, "draw_memory_error", visitor_ip, {"error": str(exc)})
        memories = retrieve_curated_memories_by_text(
            retrieval_query or user_message,
            current_session_id=session_id,
            current_visitor_ip=visitor_ip,
        )
        record_memory_retrieval(session_id, retrieval_query or user_message, memories)
        debug.update(
            {
                "retrieval_query": retrieval_query or user_message,
                "candidate_count": len(memories),
                "selected_count": len(memories),
                "context": format_curated_memory_context(memories),
                "error": str(exc),
            }
        )
        if analysis_trace_id:
            record_analysis_trace(
                session_id=session_id,
                trace_id=analysis_trace_id,
                event_type="embedding_error",
                visitor_ip=visitor_ip,
                step_name="draw_memory_query_embedding",
                duration_ms=round((time.perf_counter() - embedding_started) * 1000, 3),
                payload={
                    "alias": "embedding1",
                    "model": embedding_client.EMBEDDING_MODEL,
                    "original_message": user_message[:240],
                    "input_preview": (retrieval_query or user_message)[:240],
                    "error": str(exc),
                },
            )
            if memories:
                record_analysis_trace(
                    session_id=session_id,
                    trace_id=analysis_trace_id,
                    event_type="memory_agent",
                    visitor_ip=visitor_ip,
                    step_name="draw_memory_text_fallback",
                    payload={
                        "query": retrieval_query or user_message,
                        "results": analysis_memory_result_payload(memories),
                    },
                )
        return debug


def optimize_draw_prompt(
    user_prompt: str,
    context: Optional[str] = None,
    session_id: str = "",
    visitor_ip: str = "local",
    analysis_trace_id: str = "",
) -> Dict[str, object]:
    raw_prompt = str(user_prompt or "").strip()
    if not raw_prompt:
        return normalize_draw_prompt_decision({}, "")
    processed_prompt = apply_professional_prompt_fields(raw_prompt)
    english_prompt = translate_draw_text_to_english(
        processed_prompt,
        apply_fields=False,
        session_id=session_id,
        visitor_ip=visitor_ip,
        analysis_trace_id=analysis_trace_id,
    )
    english_context = translate_draw_context_to_english(context)
    classifier_context = english_context if draw_prompt_context_has_previous_prompt(context) else ""
    prompt_mode = classify_draw_prompt_mode(
        english_prompt,
        context=classifier_context,
        session_id=session_id,
        visitor_ip=visitor_ip,
        analysis_trace_id=analysis_trace_id,
    )
    mode = str(prompt_mode.get("mode") or "natural")
    if mode == "professional":
        decision = normalize_draw_prompt_decision(
            {
                "optimized_prompt": english_prompt,
                "negative_prompt": extract_negative_prompt_from_professional_prompt(english_prompt),
                "aspect_ratio": extract_aspect_ratio_from_prompt(processed_prompt),
                "image_count": CHAT_DRAW_IMAGE_COUNT,
                "style_tags": professional_draw_prompt_style_tags(english_prompt),
                "short_caption": "",
            },
            english_prompt,
        )
        return decision
    client, http_client, model_slot = openai_client_for_slot(MODEL_SLOT_BACKGROUND, timeout=IMAGE_PROMPT_TIMEOUT)
    started = time.perf_counter()
    try:
        if english_context and mode == "revision":
            user_content = (
                f"{english_context.strip()}\n\n"
                "Revision classification hard constraint:\n"
                "- The classifier has determined that the current user input supplements, modifies, or continues the previous image prompt.\n"
                "- You must use the optimized_prompt in the previous image result above as the full base prompt.\n"
                "- Apply only the explicit changes from the current user input; preserve the remaining subject, composition, camera, lighting, style, environment, and quality details from the previous prompt.\n"
                "- Do not treat the current short input as a complete prompt by itself; output the complete revised English prompt.\n\n"
                f"Classification reason: {prompt_mode.get('reason') or ''}\n\n"
                f"Current user edit in English:\n{english_prompt}"
            )
        else:
            user_content = english_prompt if not english_context else f"{english_context.strip()}\n\nUser drawing request:\n{english_prompt}"
        resp = client.chat.completions.create(
            **model_completion_kwargs(model_slot),
            messages=[
                {"role": "system", "content": DRAW_PROMPT_AGENT_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.45,
            top_p=0.9,
            max_tokens=900,
        )
        _, answer = split_think_text(resp.choices[0].message.content or "")
        decision = normalize_draw_prompt_decision(clean_image_model_json(answer), english_prompt)
        if str(decision.get("aspect_ratio") or "1:1") == "1:1":
            context_ratio = extract_aspect_ratio_from_prompt(context or "") if mode == "revision" and context else "1:1"
            decision["aspect_ratio"] = context_ratio if context_ratio != "1:1" else extract_aspect_ratio_from_prompt(processed_prompt)
        if analysis_trace_id:
            record_analysis_trace(
                session_id=session_id,
                trace_id=analysis_trace_id,
                event_type="model_call",
                visitor_ip=visitor_ip,
                step_name="draw_prompt_agent_model",
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
                payload={
                    "model": model_slot.get("model", MODEL_NAME),
                    "messages": [
                        {"role": "system", "content": DRAW_PROMPT_AGENT_SYSTEM_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    "prompt_mode": prompt_mode,
                    "decision": decision,
                },
            )
        return decision
    except Exception as exc:
        if analysis_trace_id:
            record_analysis_trace(
                session_id=session_id,
                trace_id=analysis_trace_id,
                event_type="model_call_error",
                visitor_ip=visitor_ip,
                step_name="draw_prompt_agent_model",
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
                payload={
                    "model": model_slot.get("model", MODEL_NAME),
                    "messages": [
                        {"role": "system", "content": DRAW_PROMPT_AGENT_SYSTEM_PROMPT},
                        {"role": "user", "content": user_content if "user_content" in locals() else english_prompt},
                    ],
                    "prompt_mode": prompt_mode,
                    "error": str(exc),
                },
            )
        record_event(None, "draw_prompt_optimize_error", "local", {"error": str(exc), "prompt_chars": len(raw_prompt)})
        return normalize_draw_prompt_decision({}, english_prompt)
    finally:
        http_client.close()


def image_payload_candidates(prompt: str, negative_prompt: str, aspect_ratio: str, count: int, model: str) -> List[Dict[str, object]]:
    base = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "aspect_ratio": aspect_ratio,
        "n": int(count),
        "num_images": int(count),
        "count": int(count),
        "model": model,
    }
    return [
        dict(base),
        {"prompt": prompt, "negative_prompt": negative_prompt, "width": 1024, "height": 1024, "num_images": int(count), "model": model},
        {"prompt": prompt, "negative_prompt": negative_prompt, "size": "1024x1024", "n": int(count), "model": model},
    ]


def hidream_dimensions(aspect_ratio: str) -> Tuple[int, int]:
    size = max(512, min(2048, int(HIDREAM_DEFAULT_IMAGE_SIZE)))
    ratio = str(aspect_ratio or "1:1").strip().lower()
    presets = {
        "1:1": (size, size),
        "square": (size, size),
        "16:9": (size, max(512, int(round(size * 9 / 16 / 64)) * 64)),
        "9:16": (max(512, int(round(size * 9 / 16 / 64)) * 64), size),
        "4:3": (size, max(512, int(round(size * 3 / 4 / 64)) * 64)),
        "3:4": (max(512, int(round(size * 3 / 4 / 64)) * 64), size),
    }
    return presets.get(ratio, presets["1:1"])


def hidream_seed(index: int, batch_seed: int = 0) -> int:
    base = int(batch_seed or 0) % 2147483647
    if base <= 0:
        base = 32
    return ((base + (int(index) * 9973)) % 2147483647) or 32


def request_hidream_flask_images(
    client: httpx.Client,
    base_url: str,
    prompt: str,
    aspect_ratio: str,
    count: int,
    reference_images_b64: Optional[List[str]] = None,
) -> List[bytes]:
    width, height = hidream_dimensions(aspect_ratio)
    images: List[bytes] = []
    batch_seed = int(uuid.uuid4().int % 2147483647) or 32
    refs_b64 = [str(item).strip() for item in reference_images_b64 or [] if str(item).strip()]
    mode = "edit" if len(refs_b64) == 1 else ("subject" if len(refs_b64) >= 2 else "t2i")
    for index in range(int(count)):
        start_resp = client.post(
            f"{base_url}/api/generate/start",
            json={
                "mode": mode,
                "prompt": prompt,
                "width": width,
                "height": height,
                "seed": hidream_seed(index, batch_seed),
                "refs_b64": refs_b64,
                "keep_original_aspect": False,
            },
        )
        if start_resp.status_code == 404:
            raise FileNotFoundError("HiDream Flask generate endpoint not found")
        if start_resp.status_code >= 400:
            raise RuntimeError(f"HiDream start failed: HTTP {start_resp.status_code} {start_resp.text[:240]}")
        job_id = str((start_resp.json() or {}).get("job_id") or "").strip()
        if not job_id:
            raise RuntimeError("HiDream start response missing job_id")
        with client.stream("GET", f"{base_url}/api/generate/stream/{job_id}") as stream:
            stream.raise_for_status()
            for line in stream.iter_lines():
                text = str(line or "").strip()
                if not text.startswith("data:"):
                    continue
                try:
                    event = json.loads(text.split("data:", 1)[1].strip())
                except Exception:
                    continue
                event_type = str(event.get("type") or "")
                if event_type == "done":
                    raw = str(event.get("image") or "")
                    if not raw:
                        raise RuntimeError("HiDream done event missing image")
                    images.append(base64.b64decode(raw))
                    break
                if event_type == "error":
                    raise RuntimeError(str(event.get("message") or "HiDream generation error"))
            else:
                raise RuntimeError("HiDream stream ended without image")
    return images


def extract_generated_image_bytes(payload: object) -> List[bytes]:
    images: List[bytes] = []
    if isinstance(payload, dict):
        candidates = []
        for key in ("images", "data", "outputs", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                candidates.extend(value)
            elif value:
                candidates.append(value)
        if not candidates and (payload.get("image") or payload.get("b64_json") or payload.get("url")):
            candidates.append(payload)
    elif isinstance(payload, list):
        candidates = payload
    else:
        candidates = []
    for item in candidates:
        raw = ""
        if isinstance(item, dict):
            raw = str(item.get("b64_json") or item.get("base64") or item.get("image") or item.get("data_url") or "")
        else:
            raw = str(item or "")
        if raw.startswith("data:"):
            raw = raw.split(",", 1)[-1]
        if not raw:
            continue
        try:
            images.append(base64.b64decode(raw))
        except Exception:
            continue
    return images


def extract_generated_image_urls(payload: object) -> List[str]:
    urls: List[str] = []
    if isinstance(payload, dict):
        candidates = []
        for key in ("images", "data", "outputs", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                candidates.extend(value)
            elif value:
                candidates.append(value)
        if payload.get("url"):
            candidates.append(payload)
    elif isinstance(payload, list):
        candidates = payload
    else:
        candidates = []
    for item in candidates:
        url = ""
        if isinstance(item, dict):
            url = str(item.get("url") or item.get("image_url") or "")
        else:
            value = str(item or "")
            if value.startswith(("http://", "https://")):
                url = value
        if url.startswith(("http://", "https://")):
            urls.append(url)
    return urls


def request_hidream_images(
    prompt: str,
    negative_prompt: str,
    aspect_ratio: str,
    count: int,
    reference_images_b64: Optional[List[str]] = None,
) -> List[bytes]:
    configured_slot = image_slot_config()
    status = image_generation_status()
    if status.get("available") and status.get("base_url"):
        slot = dict(configured_slot)
        slot.update(
            {
                "provider": status.get("provider") or configured_slot.get("provider") or "hidream",
                "display_name": status.get("display_name") or configured_slot.get("display_name") or IMAGE_MODEL_DISPLAY_NAME,
                "base_url": status.get("base_url"),
                "model": status.get("model") or configured_slot.get("model") or IMAGE_MODEL_DISPLAY_NAME,
            }
        )
    else:
        slot = configured_slot
    base_url = str(slot.get("base_url") or "").strip().rstrip("/")
    model = str(slot.get("model") or IMAGE_MODEL_DISPLAY_NAME).strip()
    headers = {"Content-Type": "application/json", **image_model_headers(slot)}
    paths = ["/v1/images/generations", "/generate", "/api/generate", "/txt2img"]
    last_error = ""
    with model_http_client(slot, timeout=IMAGE_GENERATION_TIMEOUT) as client:
        try:
            return request_hidream_flask_images(
                client,
                base_url,
                prompt,
                aspect_ratio,
                count,
                reference_images_b64=reference_images_b64,
            )[:count]
        except FileNotFoundError as exc:
            last_error = str(exc)
        except Exception as exc:
            last_error = f"/api/generate/start: {exc}"
            raise RuntimeError(last_error)
        for path in paths:
            for body in image_payload_candidates(prompt, negative_prompt, aspect_ratio, count, model):
                try:
                    resp = client.post(f"{base_url}{path}", headers=headers, json=body)
                    if resp.status_code >= 400:
                        last_error = f"{path}: HTTP {resp.status_code} {resp.text[:240]}"
                        continue
                    images = extract_generated_image_bytes(resp.json())
                    if images:
                        return images[:count]
                    urls = extract_generated_image_urls(resp.json())
                    if urls:
                        downloaded: List[bytes] = []
                        for url in urls[:count]:
                            image_resp = client.get(url)
                            image_resp.raise_for_status()
                            downloaded.append(image_resp.content)
                        if downloaded:
                            return downloaded
                    last_error = f"{path}: response contained no images"
                except Exception as exc:
                    last_error = f"{path}: {exc}"
    raise RuntimeError(last_error or "image generation failed")


def generated_image_extension(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\x89PNG"):
        return ".png"
    if image_bytes.startswith(b"\xff\xd8"):
        return ".jpg"
    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return ".webp"
    return ".png"


def save_generated_image_file(image_bytes: bytes, batch_id: str, index: int) -> Tuple[str, str]:
    IMAGE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ext = generated_image_extension(image_bytes)
    safe_name = f"{batch_id}_{int(index):02d}{ext}"
    path = IMAGE_OUTPUT_DIR / safe_name
    path.write_bytes(image_bytes)
    return str(path), f"{IMAGE_PUBLIC_PREFIX}/{safe_name}"


def save_generated_image_record(
    batch_id: str,
    source_type: str,
    source_id: object,
    file_path: str,
    public_url: str,
    original_prompt: str,
    optimized_prompt: str,
    negative_prompt: str = "",
    aspect_ratio: str = "1:1",
    model_name: str = "",
    status: str = "completed",
    error: str = "",
) -> Dict[str, object]:
    now = utc_now()
    with connect_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO generated_images (
                batch_id, source_type, source_id, file_path, public_url,
                original_prompt, optimized_prompt, negative_prompt,
                aspect_ratio, model_name, status, error, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(batch_id),
                str(source_type),
                str(source_id),
                str(file_path),
                str(public_url),
                str(original_prompt or ""),
                str(optimized_prompt or ""),
                str(negative_prompt or ""),
                str(aspect_ratio or "1:1"),
                str(model_name or ""),
                str(status or "completed"),
                str(error or ""),
                now,
            ),
        )
        image_id = int(cur.lastrowid)
    return {
        "id": image_id,
        "batch_id": str(batch_id),
        "source_type": str(source_type),
        "source_id": str(source_id),
        "public_url": str(public_url),
        "optimized_prompt": str(optimized_prompt or ""),
        "negative_prompt": str(negative_prompt or ""),
        "aspect_ratio": str(aspect_ratio or "1:1"),
        "model_name": str(model_name or ""),
        "status": str(status or "completed"),
        "error": str(error or ""),
        "created_at": now,
    }


def list_generated_images(source_type: str, source_id: object) -> List[Dict[str, object]]:
    with connect_db() as conn:
        rows = conn.execute(
            """
            SELECT id, batch_id, source_type, source_id, file_path, public_url,
                   original_prompt, optimized_prompt, negative_prompt,
                   aspect_ratio, model_name, status, error, created_at
            FROM generated_images
            WHERE source_type = ? AND source_id = ?
            ORDER BY id
            """,
            (str(source_type), str(source_id)),
        ).fetchall()
    return [dict(row) for row in rows]


def list_artifact_generated_images(artifact_id: int) -> List[Dict[str, object]]:
    with connect_db() as conn:
        rows = conn.execute(
            """
            SELECT g.id, g.batch_id, g.source_type, g.source_id, g.file_path, g.public_url,
                   g.original_prompt, g.optimized_prompt, g.negative_prompt,
                   g.aspect_ratio, g.model_name, g.status, g.error, g.created_at,
                   ai.position, ai.is_cover
            FROM artifact_images ai
            JOIN generated_images g ON g.id = ai.image_id
            WHERE ai.artifact_id = ?
            ORDER BY ai.position, g.id
            """,
            (int(artifact_id),),
        ).fetchall()
    return [dict(row) for row in rows]


def attach_image_to_artifact(artifact_id: int, image_id: int, position: int, is_cover: bool = False) -> None:
    with connect_db() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO artifact_images (artifact_id, image_id, position, is_cover)
            VALUES (?, ?, ?, ?)
            """,
            (int(artifact_id), int(image_id), int(position), 1 if is_cover else 0),
        )


def generate_image_batch(
    original_prompt: str,
    decision: Dict[str, object],
    source_type: str,
    source_id: object,
    count: int,
    reference_images_b64: Optional[List[str]] = None,
) -> Dict[str, object]:
    status = image_generation_status()
    if not status.get("available"):
        raise RuntimeError("图像生成模型未配置或不可用，无法生成图片")
    optimized_prompt = str(decision.get("optimized_prompt") or original_prompt).strip()
    negative_prompt = str(decision.get("negative_prompt") or "").strip()
    aspect_ratio = str(decision.get("aspect_ratio") or "1:1").strip() or "1:1"
    image_bytes_list = request_hidream_images(
        optimized_prompt,
        negative_prompt,
        aspect_ratio,
        int(count),
        reference_images_b64=reference_images_b64,
    )
    batch_id = str(uuid.uuid4())
    model_name = str(status.get("model") or image_slot_config().get("model") or IMAGE_MODEL_DISPLAY_NAME)
    images: List[Dict[str, object]] = []
    for index, image_bytes in enumerate(image_bytes_list, start=1):
        file_path, public_url = save_generated_image_file(image_bytes, batch_id, index)
        item = save_generated_image_record(
            batch_id=batch_id,
            source_type=source_type,
            source_id=source_id,
            file_path=file_path,
            public_url=public_url,
            original_prompt=original_prompt,
            optimized_prompt=optimized_prompt,
            negative_prompt=negative_prompt,
            aspect_ratio=aspect_ratio,
            model_name=model_name,
        )
        item["short_caption"] = str(decision.get("short_caption") or "")
        images.append(item)
    return {
        "batch_id": batch_id,
        "images": images,
        "optimized_prompt": optimized_prompt,
        "negative_prompt": negative_prompt,
        "aspect_ratio": aspect_ratio,
        "model_name": model_name,
    }


def generate_chat_draw_images(user_prompt: str, session_id: str) -> Dict[str, object]:
    decision = optimize_draw_prompt(user_prompt)
    return generate_image_batch(
        original_prompt=user_prompt,
        decision=decision,
        source_type="chat",
        source_id=session_id,
        count=chat_draw_image_count(decision),
    )


def normalize_artifact_image_plan(
    title: str,
    summary: str,
    content: str,
    image_plan: object,
) -> List[Dict[str, str]]:
    plans: List[Dict[str, str]] = []
    if isinstance(image_plan, list):
        for item in image_plan[:4]:
            if not isinstance(item, dict):
                continue
            plan_title = str(item.get("title") or "配图").strip() or "配图"
            brief = str(item.get("brief") or item.get("prompt") or "").strip()
            role = str(item.get("role") or "").strip() or ("cover" if not plans else "inline")
            if brief:
                plans.append({"title": plan_title, "brief": brief, "role": role})
    if not plans:
        source = str(summary or title or content or "").strip()
        plans.append({"title": "封面", "brief": compact_idle_artifact_content(source, 240), "role": "cover"})
    return plans[:4]


def artifact_image_character_names(profile: Dict[str, object]) -> List[str]:
    names = [str(profile.get("canonical_name") or ""), *[str(item) for item in profile.get("aliases", [])]]
    unique: List[str] = []
    for name in names:
        clean = str(name or "").strip()
        if clean and clean not in unique:
            unique.append(clean)
    return unique


ARTIFACT_IMAGE_BAD_PROMPT_MARKERS = (
    "成果标题：",
    "成果摘要：",
    "成果正文摘录",
    "配图主题：",
    "固定角色视觉锚点",
    "Artifact image request:",
    "Character visual anchors",
    "Fixed character visual anchors",
)


def artifact_image_generic_character_label(profile: Dict[str, object], index: int) -> str:
    source = " ".join(
        [
            str(profile.get("visual_prompt") or ""),
            str(profile.get("personality") or ""),
            str(profile.get("background") or ""),
        ]
    ).lower()
    if any(term in source for term in ("robot dog", "quadruped robot", "yellow robot", "antenna", "tail")):
        return "the yellow robot dog"
    if any(term in source for term in ("female", "woman", "girl", "student", "lolita", "dress")):
        return "the young woman"
    if any(term in source for term in ("male", "man", "superhero", "wrestling mask", "bodysuit", "masked")):
        return "the masked man"
    return f"mentioned character {index}"


def scrub_artifact_image_character_names(text: str, names: List[str], replacement: str = "this character") -> str:
    cleaned = str(text or "")
    replacement = str(replacement or "this character").strip() or "this character"
    for name in sorted({item.strip() for item in names if item and item.strip()}, key=len, reverse=True):
        escaped = re.escape(name)
        cleaned = re.sub(rf"\b(named|called)\s+{escaped}\b", "", cleaned, flags=re.I)
        cleaned = re.sub(rf"\b{escaped}'s\b", f"{replacement}'s", cleaned, flags=re.I)
        cleaned = re.sub(escaped, replacement, cleaned, flags=re.I)
    cleaned = re.sub(r"\b(this character|mentioned character)\s+\1\b", r"\1", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+([,.;:，。；：])", r"\1", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\bwoman,\s+exuding\b", "woman exuding", cleaned, flags=re.I)
    cleaned = re.sub(r"\bman,\s+exuding\b", "man exuding", cleaned, flags=re.I)
    return cleaned.strip()


def artifact_image_mentioned_character_profiles(text: str, limit: int = 4) -> List[Dict[str, object]]:
    source = str(text or "").strip()
    if not source:
        return []
    try:
        profiles = list_active_character_profiles(limit=80)
    except Exception as exc:
        record_event(None, "artifact_image_character_context_error", "local", {"error": str(exc)})
        return []
    matched: List[Dict[str, object]] = []
    for profile in profiles:
        try:
            if character_profile_matches_message(profile, source):
                matched.append(profile)
        except Exception:
            continue
        if len(matched) >= max(1, int(limit)):
            break
    return matched


def artifact_image_profiles_for_plan(summary: str, plan: Dict[str, str], limit: int = 4) -> List[Dict[str, object]]:
    plan_text = "\n".join(
        [
            str(plan.get("title") or ""),
            str(plan.get("brief") or ""),
            str(plan.get("role") or ""),
        ]
    ).strip()
    profiles = artifact_image_mentioned_character_profiles(plan_text, limit=limit)
    if profiles:
        return profiles
    summary_text = compact_idle_artifact_content(str(summary or ""), 320)
    return artifact_image_mentioned_character_profiles(summary_text, limit=min(2, max(1, int(limit))))


def scrub_artifact_image_text_for_profiles(text: str, profiles: List[Dict[str, object]]) -> str:
    cleaned = str(text or "")
    for index, profile in enumerate(profiles[:4], start=1):
        cleaned = scrub_artifact_image_character_names(
            cleaned,
            artifact_image_character_names(profile),
            replacement=artifact_image_generic_character_label(profile, index),
        )
    return cleaned.strip()


def artifact_image_character_visual_context(profiles: List[Dict[str, object]]) -> str:
    if not profiles:
        return ""
    lines = [
        "Character visual anchors for this image:",
        "Use only generic labels in the final prompt. Do not output actual character names or aliases.",
        "Preserve ethnicity/region, age, hairstyle, forehead/bangs, body shape, facial structure, temperament, key props, costumes, symbols, and visible identity traits.",
    ]
    for index, profile in enumerate(profiles[:4], start=1):
        names = artifact_image_character_names(profile)
        label = artifact_image_generic_character_label(profile, index)
        visual_prompt = scrub_artifact_image_character_names(
            clean_character_text(profile.get("visual_prompt"), 1800),
            names,
            replacement=label,
        )
        personality = scrub_artifact_image_character_names(
            clean_character_text(profile.get("personality"), 450),
            names,
            replacement=label,
        )
        background = scrub_artifact_image_character_names(
            clean_character_text(profile.get("background"), 550),
            names,
            replacement=label,
        )
        negative_prompt = scrub_artifact_image_character_names(
            clean_character_text(profile.get("negative_prompt"), 320),
            names,
            replacement=label,
        )
        lines.append(f"Character {index}: {label}")
        if visual_prompt:
            lines.append(f"- Visual reference: {visual_prompt}")
        if personality:
            lines.append(f"- Temperament/expression reference: {personality}")
        if background:
            lines.append(f"- Identity/background reference: {background}")
        if negative_prompt:
            lines.append(f"- Character-specific negative constraints: {negative_prompt}")
    return "\n".join(lines).strip()


def artifact_image_prompt_source(title: str, summary: str, content: str, plan: Dict[str, str]) -> str:
    profiles = artifact_image_profiles_for_plan(summary, plan)
    image_title = scrub_artifact_image_text_for_profiles(str(plan.get("title") or "cover image"), profiles)
    visual_brief = scrub_artifact_image_text_for_profiles(str(plan.get("brief") or ""), profiles)
    story_context = scrub_artifact_image_text_for_profiles(
        compact_idle_artifact_content(str(summary or content or title or ""), 320),
        profiles,
    )
    character_context = artifact_image_character_visual_context(profiles)
    sections = [
        "Artifact image request:",
        f"- image_title: {image_title}",
        f"- image_role: {str(plan.get('role') or 'inline').strip() or 'inline'}",
        f"- visual_brief: {visual_brief}",
        f"- story_context: {story_context}",
        "- requirement: Generate one image that matches the visual_brief and story_context. Do not make a text poster, title card, infographic, or page of text.",
    ]
    if character_context:
        sections.extend(["", character_context])
    return "\n".join(sections).strip()


def artifact_image_negative_prompt(profiles: List[Dict[str, object]]) -> str:
    parts = ["low quality, blurry, distorted face, extra limbs, bad anatomy, watermark, text, signature"]
    for profile in profiles[:4]:
        negative = clean_character_text(profile.get("negative_prompt"), 260)
        if negative:
            parts.append(negative)
    return sanitize_image_negative_prompt(", ".join(parts))


def fallback_artifact_image_prompt(prompt_source: str, profiles: List[Dict[str, object]]) -> str:
    source = str(prompt_source or "")
    brief_match = re.search(r"(?m)^-\s*visual_brief:\s*(.+)$", source)
    context_match = re.search(r"(?m)^-\s*story_context:\s*(.+)$", source)
    role_match = re.search(r"(?m)^-\s*image_role:\s*(.+)$", source)
    brief = str(brief_match.group(1) if brief_match else "").strip()
    context = str(context_match.group(1) if context_match else "").strip()
    role = str(role_match.group(1) if role_match else "cover").strip() or "cover"
    lines = [
        f"Photorealistic cinematic {role} image, {brief or context or 'a story scene'}",
        "not a text poster, no captions, no visible writing, realistic materials, detailed textures, natural cinematic lighting",
    ]
    if context and context not in brief:
        lines.append(f"story atmosphere: {context}")
    for index, profile in enumerate(profiles[:3], start=1):
        label = artifact_image_generic_character_label(profile, index)
        visual_prompt = scrub_artifact_image_character_names(
            clean_character_text(profile.get("visual_prompt"), 700),
            artifact_image_character_names(profile),
            replacement=label,
        )
        if visual_prompt:
            lines.append(f"{label}: {visual_prompt}")
    return compact_idle_artifact_content(" ".join(item for item in lines if item), 1800)


def artifact_image_prompt_is_bad(optimized_prompt: str, original_prompt: str) -> bool:
    prompt = str(optimized_prompt or "").strip()
    if not prompt:
        return True
    if prompt == str(original_prompt or "").strip():
        return True
    if any(marker in prompt for marker in ARTIFACT_IMAGE_BAD_PROMPT_MARKERS):
        return True
    if len(prompt) > 3500 and prompt_contains_cjk(prompt):
        return True
    return False


def optimize_artifact_image_prompt(prompt_source: str, profiles: List[Dict[str, object]]) -> Dict[str, object]:
    fallback_prompt = fallback_artifact_image_prompt(prompt_source, profiles)
    fallback_negative = artifact_image_negative_prompt(profiles)
    client, http_client, model_slot = openai_client_for_slot(MODEL_SLOT_BACKGROUND, timeout=IMAGE_PROMPT_TIMEOUT)
    started = time.perf_counter()
    try:
        resp = client.chat.completions.create(
            **model_completion_kwargs(model_slot),
            messages=[
                {"role": "system", "content": ARTIFACT_IMAGE_PROMPT_AGENT_SYSTEM_PROMPT},
                {"role": "user", "content": prompt_source},
            ],
            temperature=0.35,
            top_p=0.9,
            max_tokens=1200,
        )
        _, answer = split_think_text(resp.choices[0].message.content or "")
        decision = normalize_draw_prompt_decision(clean_image_model_json(answer), fallback_prompt)
        if not str(decision.get("negative_prompt") or "").strip():
            decision["negative_prompt"] = fallback_negative
        if artifact_image_prompt_is_bad(str(decision.get("optimized_prompt") or ""), prompt_source):
            record_event(
                None,
                "artifact_image_prompt_fallback",
                "local",
                {
                    "reason": "bad_optimized_prompt",
                    "source_chars": len(prompt_source),
                    "optimized_chars": len(str(decision.get("optimized_prompt") or "")),
                },
            )
            decision["optimized_prompt"] = fallback_prompt
            decision["negative_prompt"] = fallback_negative
        decision["image_count"] = 1
        return decision
    except Exception as exc:
        record_event(
            None,
            "artifact_image_prompt_fallback",
            "local",
            {
                "reason": "model_error",
                "error": str(exc),
                "source_chars": len(prompt_source),
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            },
        )
        return normalize_draw_prompt_decision(
            {
                "optimized_prompt": fallback_prompt,
                "negative_prompt": fallback_negative,
                "aspect_ratio": "1:1",
                "image_count": 1,
                "style_tags": ["artifact", "cinematic realism"],
                "short_caption": "",
            },
            fallback_prompt,
        )
    finally:
        http_client.close()



def generate_artifact_theme_images(
    artifact_id: int,
    title: str,
    summary: str,
    content: str,
    image_plan: object,
) -> Dict[str, object]:
    status = image_generation_status()
    plans = normalize_artifact_image_plan(title, summary, content, image_plan)
    if not status.get("available"):
        record_event(
            None,
            "artifact_image_generation_skipped",
            "local",
            {"artifact_id": int(artifact_id), "reason": status.get("reason"), "error": status.get("error")},
        )
        return {"status": "skipped", "reason": status.get("reason", "unavailable"), "images": []}
    images: List[Dict[str, object]] = []
    errors: List[str] = []
    for position, plan in enumerate(plans):
        prompt_source = artifact_image_prompt_source(title, summary, content, plan)
        try:
            profiles = artifact_image_profiles_for_plan(summary, plan)
            decision = optimize_artifact_image_prompt(prompt_source, profiles)
            batch = generate_image_batch(
                original_prompt=prompt_source,
                decision=decision,
                source_type="artifact",
                source_id=artifact_id,
                count=1,
            )
            batch_images = batch.get("images") if isinstance(batch.get("images"), list) else []
            if batch_images:
                image = batch_images[0]
                attach_image_to_artifact(int(artifact_id), int(image["id"]), position, is_cover=position == 0)
                image["plan_title"] = plan.get("title", "")
                image["plan_role"] = plan.get("role", "")
                images.append(image)
        except Exception as exc:
            errors.append(str(exc))
            record_event(
                None,
                "artifact_image_generation_error",
                "local",
                {"artifact_id": int(artifact_id), "position": position, "error": str(exc), "plan": plan},
            )
    status_name = "completed" if images else "failed"
    record_event(
        None,
        "artifact_image_generation_completed",
        "local",
        {"artifact_id": int(artifact_id), "image_count": len(images), "errors": errors[:3]},
    )
    return {"status": status_name, "images": images, "errors": errors}
