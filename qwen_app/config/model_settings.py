# Runtime model slot configuration. Keep these helpers pure where possible; DB
# access is isolated to load/save so callers can depend on slot interfaces.
MODEL_SETTINGS_KEY = "model_settings_v1"
MODEL_SLOT_CHAT = "chat"
MODEL_SLOT_BACKGROUND = "background"
MODEL_SLOT_IMAGE = "image"
MODEL_SETTING_SLOTS = (MODEL_SLOT_CHAT, MODEL_SLOT_BACKGROUND, MODEL_SLOT_IMAGE)

LOCAL_MODEL_DISPLAY_NAME = "Qwen3.6"
IMAGE_MODEL_DISPLAY_NAME = "HiDream-O1-Image-Dev-2604"
DEFAULT_MODEL_PROVIDER = "local"
MODEL_PROVIDER_PRESETS: Dict[str, Dict[str, object]] = {
    "none": {
        "display_name": "未配置",
        "base_url": "",
        "model": "",
        "api_key": "",
        "use_proxy": False,
        "proxy_url": "",
    },
    "local": {
        "display_name": LOCAL_MODEL_DISPLAY_NAME,
        "base_url": BASE_URL,
        "model": MODEL_NAME,
        "api_key": MODEL_API_KEY if MODEL_API_KEY != "EMPTY" else "",
        "use_proxy": False,
        "proxy_url": "",
    },
    "openai": {
        "display_name": "GPT-4.1",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4.1",
        "api_key": "",
        "use_proxy": True,
        "proxy_url": "",
    },
    "deepseek": {
        "display_name": "DeepSeek Chat",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "api_key": "",
        "use_proxy": True,
        "proxy_url": "",
    },
    "dashscope": {
        "display_name": "通义千问",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "api_key": "",
        "use_proxy": True,
        "proxy_url": "",
    },
    "custom": {
        "display_name": "自定义模型",
        "base_url": "",
        "model": "",
        "api_key": "",
        "use_proxy": True,
        "proxy_url": "",
    },
    "hidream": {
        "display_name": IMAGE_MODEL_DISPLAY_NAME,
        "base_url": os.environ.get("QWEN_IMAGE_MODEL_BASE_URL", "http://127.0.0.1:8002").strip(),
        "model": os.environ.get("QWEN_IMAGE_MODEL_NAME", IMAGE_MODEL_DISPLAY_NAME).strip(),
        "api_key": os.environ.get("QWEN_IMAGE_MODEL_API_KEY", "").strip(),
        "use_proxy": False,
        "proxy_url": "",
    },
}


def model_provider_preset(provider: str) -> Dict[str, object]:
    key = str(provider or DEFAULT_MODEL_PROVIDER).strip().lower()
    if key not in MODEL_PROVIDER_PRESETS:
        key = "custom"
    return {"provider": key, **MODEL_PROVIDER_PRESETS[key]}


def default_model_slot(provider: str = DEFAULT_MODEL_PROVIDER) -> Dict[str, object]:
    return normalize_model_slot({"provider": provider}, existing=None)


def default_model_settings() -> Dict[str, Dict[str, object]]:
    slot = default_model_slot("local")
    return {
        MODEL_SLOT_CHAT: dict(slot),
        MODEL_SLOT_BACKGROUND: dict(slot),
        MODEL_SLOT_IMAGE: default_model_slot("none"),
    }


def normalize_model_slot(
    raw: object,
    existing: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    data = raw if isinstance(raw, dict) else {}
    provider = str(data.get("provider") or (existing or {}).get("provider") or DEFAULT_MODEL_PROVIDER).strip().lower()
    preset = model_provider_preset(provider)
    provider = str(preset["provider"])

    base_url = str(data.get("base_url") or preset.get("base_url") or "").strip().rstrip("/")
    model = str(data.get("model") or preset.get("model") or "").strip()
    display_name = str(data.get("display_name") or preset.get("display_name") or model or provider).strip()

    existing_provider = str((existing or {}).get("provider") or "").strip().lower()
    if "api_key" in data and data.get("api_key") is not None:
        api_key = str(data.get("api_key") or "").strip()
    elif existing is not None and existing_provider == provider:
        api_key = str(existing.get("api_key") or "").strip()
    else:
        api_key = str(preset.get("api_key") or "").strip()

    proxy_url = str(data.get("proxy_url") or preset.get("proxy_url") or "").strip()
    use_proxy = bool(data.get("use_proxy", preset.get("use_proxy", False)))

    if provider == "local":
        display_name = LOCAL_MODEL_DISPLAY_NAME
        api_key = ""
        use_proxy = False
        proxy_url = ""
        if not base_url:
            base_url = BASE_URL.rstrip("/")
        if not model:
            model = MODEL_NAME
    elif provider == "none":
        display_name = "未配置"
        base_url = ""
        model = ""
        api_key = ""
        use_proxy = False
        proxy_url = ""
    elif provider == "hidream":
        display_name = display_name or IMAGE_MODEL_DISPLAY_NAME
        model = model or IMAGE_MODEL_DISPLAY_NAME
        use_proxy = False
        proxy_url = ""

    return {
        "provider": provider,
        "display_name": display_name,
        "base_url": base_url,
        "model": model,
        "api_key": api_key,
        "use_proxy": use_proxy,
        "proxy_url": proxy_url,
    }


def normalize_model_settings(
    raw: object,
    existing: Optional[Dict[str, Dict[str, object]]] = None,
) -> Dict[str, Dict[str, object]]:
    data = raw if isinstance(raw, dict) else {}
    base = existing or default_model_settings()
    return {
        slot: normalize_model_slot(data.get(slot, {}), existing=base.get(slot))
        for slot in MODEL_SETTING_SLOTS
    }


def load_model_settings() -> Dict[str, Dict[str, object]]:
    try:
        raw = get_app_setting(MODEL_SETTINGS_KEY, "")
    except sqlite3.OperationalError:
        return default_model_settings()
    if not raw.strip():
        return default_model_settings()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return default_model_settings()
    return normalize_model_settings(payload, existing=default_model_settings())


def save_model_settings(payload: object) -> Dict[str, Dict[str, object]]:
    current = load_model_settings()
    settings = normalize_model_settings(payload, existing=current)
    set_app_setting(MODEL_SETTINGS_KEY, json.dumps(settings, ensure_ascii=False, sort_keys=True))
    return settings


def public_model_slot(slot: Dict[str, object]) -> Dict[str, object]:
    api_key = str(slot.get("api_key") or "").strip()
    return {
        "provider": slot.get("provider", DEFAULT_MODEL_PROVIDER),
        "display_name": slot.get("display_name", LOCAL_MODEL_DISPLAY_NAME),
        "base_url": slot.get("base_url", ""),
        "model": slot.get("model", ""),
        "has_api_key": bool(api_key and api_key != "EMPTY"),
        "use_proxy": bool(slot.get("use_proxy", False)),
        "proxy_url": slot.get("proxy_url", ""),
    }


def public_model_settings(settings: Optional[Dict[str, Dict[str, object]]] = None) -> Dict[str, Dict[str, object]]:
    data = settings or load_model_settings()
    return {slot: public_model_slot(data[slot]) for slot in MODEL_SETTING_SLOTS}


def model_slot_config(slot: str) -> Dict[str, object]:
    key = slot if slot in MODEL_SETTING_SLOTS else MODEL_SLOT_BACKGROUND
    return load_model_settings()[key]


def model_api_key(slot: Dict[str, object]) -> str:
    api_key = str(slot.get("api_key") or "").strip()
    return api_key or "EMPTY"


def model_http_client(slot: Dict[str, object], timeout: float) -> httpx.Client:
    kwargs: Dict[str, object] = {"trust_env": False, "timeout": timeout}
    proxy_url = str(slot.get("proxy_url") or "").strip()
    if slot.get("use_proxy") and proxy_url:
        kwargs["proxy"] = proxy_url
    return httpx.Client(**kwargs)


def openai_client_for_slot(slot_name: str, timeout: float) -> Tuple[OpenAI, httpx.Client, Dict[str, object]]:
    slot = model_slot_config(slot_name)
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


def model_completion_kwargs(slot: Dict[str, object]) -> Dict[str, object]:
    kwargs: Dict[str, object] = {"model": str(slot.get("model") or MODEL_NAME)}
    if slot.get("provider") == "local":
        kwargs["extra_body"] = build_extra_body()
    return kwargs
