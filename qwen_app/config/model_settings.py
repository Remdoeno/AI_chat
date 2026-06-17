# Runtime model slot configuration. Keep these helpers pure where possible; DB
# access is isolated to load/save so callers can depend on slot interfaces.
MODEL_SETTINGS_KEY = "model_settings_v1"
MODEL_SLOT_CHAT = "chat"
MODEL_SLOT_BACKGROUND = "background"
MODEL_SLOT_IMAGE = "image"
MODEL_SETTING_SLOTS = (MODEL_SLOT_CHAT, MODEL_SLOT_BACKGROUND, MODEL_SLOT_IMAGE)
MODEL_PROVIDER_API_KEYS_KEY = "provider_api_keys"
MODEL_WEB_SEARCH_PROXY_KEY = "web_search_proxy"
MODEL_KEYLESS_PROVIDERS = {"local", "none", "hidream"}

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
        "display_name": "gpt-5.5",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-5.5",
        "api_key": "",
        "use_proxy": True,
        "proxy_url": "",
    },
    "deepseek": {
        "display_name": "deepseek-v4-pro",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-v4-pro",
        "api_key": "",
        "use_proxy": True,
        "proxy_url": "",
    },
    "zhipu": {
        "display_name": "glm-5.2",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-5.2",
        "api_key": "",
        "use_proxy": True,
        "proxy_url": "",
    },
    "dashscope": {
        "display_name": "qwen3.7-max",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen3.7-max",
        "api_key": "",
        "use_proxy": True,
        "proxy_url": "",
    },
    "doubao": {
        "display_name": "doubao-seed-2.0-pro",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "model": "doubao-seed-2-0-pro-260215",
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
        MODEL_PROVIDER_API_KEYS_KEY: {},
        MODEL_WEB_SEARCH_PROXY_KEY: "",
    }


def normalize_model_slot(
    raw: object,
    existing: Optional[Dict[str, object]] = None,
    provider_api_keys: Optional[Dict[str, str]] = None,
    web_search_proxy: str = "",
) -> Dict[str, object]:
    data = raw if isinstance(raw, dict) else {}
    provider = str(data.get("provider") or (existing or {}).get("provider") or DEFAULT_MODEL_PROVIDER).strip().lower()
    preset = model_provider_preset(provider)
    provider = str(preset["provider"])

    base_url = str(data.get("base_url") or preset.get("base_url") or "").strip().rstrip("/")
    model = str(data.get("model") or preset.get("model") or "").strip()
    display_name = str(data.get("display_name") or preset.get("display_name") or model or provider).strip()

    existing_provider = str((existing or {}).get("provider") or "").strip().lower()
    provider_keys = provider_api_keys or {}
    if "api_key" in data and data.get("api_key") is not None:
        api_key = str(data.get("api_key") or "").strip()
    elif provider not in MODEL_KEYLESS_PROVIDERS and provider_keys.get(provider):
        api_key = str(provider_keys.get(provider) or "").strip()
    elif existing is not None and existing_provider == provider:
        api_key = str(existing.get("api_key") or "").strip()
    else:
        api_key = str(preset.get("api_key") or "").strip()

    shared_proxy = str(web_search_proxy or "").strip()
    proxy_url = str(data.get("proxy_url") or shared_proxy or preset.get("proxy_url") or "").strip()
    use_proxy = bool(data.get("use_proxy", preset.get("use_proxy", False)))
    if provider not in MODEL_KEYLESS_PROVIDERS and shared_proxy:
        use_proxy = True

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


def normalize_provider_api_keys(raw: object, existing: object = None) -> Dict[str, str]:
    keys: Dict[str, str] = {}
    for source in (existing, raw):
        data = source if isinstance(source, dict) else {}
        provider_keys = data.get(MODEL_PROVIDER_API_KEYS_KEY, {})
        if isinstance(provider_keys, dict):
            for provider, api_key in provider_keys.items():
                key = str(provider or "").strip().lower()
                value = str(api_key or "").strip()
                if key and value and key not in MODEL_KEYLESS_PROVIDERS:
                    keys[key] = value
        for slot in MODEL_SETTING_SLOTS:
            slot_data = data.get(slot, {})
            if not isinstance(slot_data, dict):
                continue
            provider = str(slot_data.get("provider") or "").strip().lower()
            api_key = str(slot_data.get("api_key") or "").strip()
            if provider and api_key and provider not in MODEL_KEYLESS_PROVIDERS:
                keys[provider] = api_key
    return keys


def normalize_model_web_search_proxy(raw: object, existing: object = None) -> str:
    data = raw if isinstance(raw, dict) else {}
    if MODEL_WEB_SEARCH_PROXY_KEY in data:
        proxy = str(data.get(MODEL_WEB_SEARCH_PROXY_KEY) or "").strip()
        if proxy:
            return proxy
    existing_data = existing if isinstance(existing, dict) else {}
    proxy = str(existing_data.get(MODEL_WEB_SEARCH_PROXY_KEY) or "").strip()
    if proxy:
        return proxy
    for source in (data, existing_data):
        for slot in MODEL_SETTING_SLOTS:
            slot_data = source.get(slot, {}) if isinstance(source, dict) else {}
            if not isinstance(slot_data, dict):
                continue
            provider = str(slot_data.get("provider") or "").strip().lower()
            proxy_url = str(slot_data.get("proxy_url") or "").strip()
            if provider not in MODEL_KEYLESS_PROVIDERS and proxy_url:
                return proxy_url
    return ""


def normalize_model_settings(
    raw: object,
    existing: Optional[Dict[str, Dict[str, object]]] = None,
) -> Dict[str, Dict[str, object]]:
    data = raw if isinstance(raw, dict) else {}
    base = existing or default_model_settings()
    provider_api_keys = normalize_provider_api_keys(data, existing=base)
    web_search_proxy = normalize_model_web_search_proxy(data, existing=base)
    settings: Dict[str, object] = {
        slot: normalize_model_slot(
            data.get(slot, {}),
            existing=base.get(slot),
            provider_api_keys=provider_api_keys,
            web_search_proxy=web_search_proxy,
        )
        for slot in MODEL_SETTING_SLOTS
    }
    settings[MODEL_PROVIDER_API_KEYS_KEY] = provider_api_keys
    settings[MODEL_WEB_SEARCH_PROXY_KEY] = web_search_proxy
    return settings


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
    public: Dict[str, object] = {slot: public_model_slot(data[slot]) for slot in MODEL_SETTING_SLOTS}
    provider_keys = data.get(MODEL_PROVIDER_API_KEYS_KEY, {})
    public[MODEL_PROVIDER_API_KEYS_KEY] = {
        str(provider): True
        for provider, api_key in (provider_keys.items() if isinstance(provider_keys, dict) else [])
        if str(api_key or "").strip()
    }
    public[MODEL_WEB_SEARCH_PROXY_KEY] = str(data.get(MODEL_WEB_SEARCH_PROXY_KEY) or "").strip()
    return public


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
