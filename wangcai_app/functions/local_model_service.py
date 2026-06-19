# Local Wangcai model service orchestration. Keep process launching isolated from routes.
import socket
import subprocess


LOCAL_WANGCAI_MODEL_PORT_CANDIDATES = [
    int(port.strip())
    for port in os.environ.get("WANGCAI_LOCAL_MODEL_PORTS", "8000").split(",")
    if port.strip().isdigit()
]
LOCAL_EMBEDDING_PORT_CANDIDATES = [
    int(port.strip())
    for port in os.environ.get("WANGCAI_LOCAL_EMBEDDING_PORTS", "8001").split(",")
    if port.strip().isdigit()
]
LOCAL_IMAGE_PORT_CANDIDATES = [
    int(port.strip())
    for port in os.environ.get("WANGCAI_LOCAL_IMAGE_PORTS", "8002").split(",")
    if port.strip().isdigit()
]
LOCAL_MODEL_SERVICE_LOCK = threading.Lock()


def local_service_script_path(env_name: str, candidates: List[Path]) -> Path:
    configured = str(os.environ.get(env_name) or "").strip()
    if configured:
        return Path(configured)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


LOCAL_WANGCAI_MODEL_START_SCRIPT = local_service_script_path(
    "WANGCAI_LOCAL_MODEL_START_SCRIPT",
    [
        APP_DIR.parent.parent / "start_wangcai_model_35b_2gpu_262k.sh",
        APP_DIR.parent / "start_wangcai_model_35b_2gpu_262k.sh",
        APP_DIR.parent.parent / "start_qwen36_35b_2gpu_262k.sh",
        APP_DIR.parent / "start_qwen36_35b_2gpu_262k.sh",
    ],
)
LOCAL_EMBEDDING_START_SCRIPT = local_service_script_path(
    "WANGCAI_LOCAL_EMBEDDING_START_SCRIPT",
    [
        APP_DIR.parent / "start_wangcai_embedding.sh",
        APP_DIR.parent.parent / "start_wangcai_embedding.sh",
    ],
)
LOCAL_IMAGE_START_SCRIPT = local_service_script_path(
    "WANGCAI_LOCAL_IMAGE_START_SCRIPT",
    [
        APP_DIR.parent.parent / "imggen" / "start_hidream.sh",
        APP_DIR.parent / "start_hidream.sh",
        APP_DIR.parent.parent / "start_hidream.sh",
    ],
)


def local_openai_base_url(port: int) -> str:
    return f"http://127.0.0.1:{int(port)}/v1"


def probe_local_openai_models(base_url: str, timeout: float = 2.0) -> Dict[str, object]:
    try:
        with httpx.Client(trust_env=False, timeout=timeout) as client:
            resp = client.get(f"{str(base_url).rstrip('/')}/models")
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:
        return {"ok": False, "models": [], "error": str(exc)}
    models = [
        str(item.get("id") or "")
        for item in payload.get("data", [])
        if isinstance(item, dict) and item.get("id")
    ]
    return {"ok": True, "models": models, "error": ""}


def local_service_component_status(name: str, ports: List[int], model_name: str) -> Dict[str, object]:
    checked: List[Dict[str, object]] = []
    for port in ports:
        base_url = local_openai_base_url(port)
        probe = probe_local_openai_models(base_url)
        models = list(probe.get("models") or [])
        running = bool(probe.get("ok")) and (not model_name or model_name in models)
        checked.append(
            {
                "port": port,
                "base_url": base_url,
                "ok": bool(probe.get("ok")),
                "models": models,
                "error": str(probe.get("error") or ""),
            }
        )
        if running:
            return {
                "name": name,
                "running": True,
                "port": port,
                "base_url": base_url,
                "model": model_name,
                "models": models,
                "error": "",
                "checked": checked,
            }
    fallback_port = ports[0] if ports else 0
    last_error = checked[-1]["error"] if checked else "no candidate ports"
    return {
        "name": name,
        "running": False,
        "port": fallback_port,
        "base_url": local_openai_base_url(fallback_port) if fallback_port else "",
        "model": model_name,
        "models": [],
        "error": last_error,
        "checked": checked,
    }


def probe_local_image_service(base_url: str, timeout: float = 2.0) -> Dict[str, object]:
    paths = ["/health", "/v1/models", "/models", "/"]
    last_error = ""
    try:
        with httpx.Client(trust_env=False, timeout=timeout) as client:
            for path in paths:
                try:
                    resp = client.get(f"{str(base_url).rstrip('/')}{path}")
                    if resp.status_code < 400 or resp.status_code in {401, 403}:
                        return {"ok": True, "path": path, "error": ""}
                    last_error = f"{path}: HTTP {resp.status_code}"
                except Exception as exc:
                    last_error = f"{path}: {exc}"
    except Exception as exc:
        last_error = str(exc)
    return {"ok": False, "path": "", "error": last_error or "image service unavailable"}


def local_image_service_status() -> Dict[str, object]:
    checked: List[Dict[str, object]] = []
    for port in LOCAL_IMAGE_PORT_CANDIDATES:
        base_url = f"http://127.0.0.1:{int(port)}"
        probe = probe_local_image_service(base_url)
        checked.append(
            {
                "port": port,
                "base_url": base_url,
                "ok": bool(probe.get("ok")),
                "path": str(probe.get("path") or ""),
                "error": str(probe.get("error") or ""),
            }
        )
        if probe.get("ok"):
            return {
                "name": "image",
                "running": True,
                "port": port,
                "base_url": base_url,
                "model": IMAGE_MODEL_DISPLAY_NAME,
                "error": "",
                "checked": checked,
            }
    fallback_port = LOCAL_IMAGE_PORT_CANDIDATES[0] if LOCAL_IMAGE_PORT_CANDIDATES else 0
    return {
        "name": "image",
        "running": False,
        "port": fallback_port,
        "base_url": f"http://127.0.0.1:{int(fallback_port)}" if fallback_port else "",
        "model": IMAGE_MODEL_DISPLAY_NAME,
        "error": checked[-1]["error"] if checked else "no candidate ports",
        "checked": checked,
    }


def local_model_service_summary(model_status: Dict[str, object], embedding_status: Dict[str, object], image_status: Optional[Dict[str, object]] = None) -> str:
    model_running = bool(model_status.get("running"))
    embedding_running = bool(embedding_status.get("running"))
    image_running = bool((image_status or {}).get("running"))
    if model_running and embedding_running and image_running:
        return f"已运行：本地模型 {model_status.get('port')} / Embedding {embedding_status.get('port')} / 画图 {image_status.get('port')}"
    missing = []
    if not model_running:
        missing.append("本地模型")
    if not embedding_running:
        missing.append("Embedding")
    if image_status is not None and not image_running:
        missing.append("画图")
    return f"未启动：{'、'.join(missing)}"


def local_model_service_status() -> Dict[str, object]:
    model_status = local_service_component_status(
        "model",
        LOCAL_WANGCAI_MODEL_PORT_CANDIDATES,
        MODEL_NAME,
    )
    embedding_status = local_service_component_status(
        "embedding",
        LOCAL_EMBEDDING_PORT_CANDIDATES,
        embedding_client.EMBEDDING_MODEL,
    )
    image_status = local_image_service_status()
    return {
        "model": model_status,
        "embedding": embedding_status,
        "image": image_status,
        "summary": local_model_service_summary(model_status, embedding_status, image_status),
    }


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", int(port))) != 0


def parse_gpu_used_memory(text: str) -> List[Tuple[int, int]]:
    gpus: List[Tuple[int, int]] = []
    for line in str(text or "").splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 2:
            continue
        try:
            gpus.append((int(parts[0]), int(float(parts[1]))))
        except ValueError:
            continue
    return gpus


def select_local_service_gpus() -> Dict[str, str]:
    try:
        output = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=index,memory.used",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=5,
        )
        gpus = parse_gpu_used_memory(output)
    except Exception:
        gpus = []
    if len(gpus) >= 3:
        ordered = sorted(gpus, key=lambda item: (item[1], -item[0]))
        embedding_gpu = ordered[0][0]
        model_gpus = sorted([ordered[1][0], ordered[2][0]])
        return {"embedding": str(embedding_gpu), "model": ",".join(str(gpu) for gpu in model_gpus)}
    return {"embedding": "5", "model": "6,7"}


def launch_shell_command(command: str, cwd: Path) -> None:
    subprocess.Popen(
        command,
        cwd=str(cwd),
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def start_missing_local_model_services(status: Dict[str, object]) -> Dict[str, object]:
    model_status = status.get("model") if isinstance(status.get("model"), dict) else {}
    embedding_status = status.get("embedding") if isinstance(status.get("embedding"), dict) else {}
    image_status = status.get("image") if isinstance(status.get("image"), dict) else {}
    gpu_selection = select_local_service_gpus()
    commands: List[str] = []
    warnings: List[str] = []
    project_dir = APP_DIR.parent.parent
    web_dir_name = APP_DIR.parent.name
    log_dir = APP_DIR.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    if not embedding_status.get("running"):
        embedding_port = int(embedding_status.get("port") or LOCAL_EMBEDDING_PORT_CANDIDATES[0])
        if not port_is_free(embedding_port):
            raise RuntimeError(f"Embedding 端口 {embedding_port} 已被非目标服务占用")
        if not LOCAL_EMBEDDING_START_SCRIPT.exists():
            raise RuntimeError(f"Embedding 启动脚本不存在: {LOCAL_EMBEDDING_START_SCRIPT}")
        command = (
            f"EMBED_GPUS={gpu_selection['embedding']} "
            f"EMBED_PORT={embedding_port} "
            f"LOG_DIR={web_dir_name}/logs "
            f"PID_FILE={web_dir_name}/wangcai_embedding.pid "
            f"{LOCAL_EMBEDDING_START_SCRIPT}"
        )
        launch_shell_command(command, project_dir)
        commands.append(f"embedding:{embedding_port}")

    if not model_status.get("running"):
        model_port = int(model_status.get("port") or LOCAL_WANGCAI_MODEL_PORT_CANDIDATES[0])
        if not port_is_free(model_port):
            raise RuntimeError(f"本地模型端口 {model_port} 已被非目标服务占用")
        if not LOCAL_WANGCAI_MODEL_START_SCRIPT.exists():
            raise RuntimeError(f"本地模型启动脚本不存在: {LOCAL_WANGCAI_MODEL_START_SCRIPT}")
        model_log = log_dir / f"start_wangcai_model_{model_port}_{int(time.time())}.launcher.log"
        command = (
            "nohup env "
            "KILL_OLD=0 "
            "INTERACTIVE=0 "
            f"GPUS={gpu_selection['model']} "
            "TP_SIZE=2 "
            "ENABLE_COT=0 "
            f"PORT={model_port} "
            f"{LOCAL_WANGCAI_MODEL_START_SCRIPT} > {model_log} 2>&1 &"
        )
        launch_shell_command(command, project_dir)
        commands.append(f"model:{model_port}")

    if not image_status.get("running"):
        image_port = int(image_status.get("port") or LOCAL_IMAGE_PORT_CANDIDATES[0])
        if port_is_free(image_port):
            if LOCAL_IMAGE_START_SCRIPT.exists():
                image_log = log_dir / f"start_hidream_{image_port}_{int(time.time())}.launcher.log"
                command = (
                    "nohup env "
                    f"PORT={image_port} "
                    f"{LOCAL_IMAGE_START_SCRIPT} > {image_log} 2>&1 &"
                )
                launch_shell_command(command, project_dir)
                commands.append(f"image:{image_port}")
            else:
                warnings.append(f"图像服务启动脚本不存在: {LOCAL_IMAGE_START_SCRIPT}")
        else:
            warnings.append(f"图像服务端口 {image_port} 已被占用但服务未就绪")

    return {
        "started": bool(commands),
        "commands": commands,
        "warnings": warnings,
        "message": "启动命令已提交" if commands else ("；".join(warnings) if warnings else "services already running"),
    }


def apply_local_model_service_settings(status: Dict[str, object]) -> bool:
    model_status = status.get("model") if isinstance(status.get("model"), dict) else {}
    embedding_status = status.get("embedding") if isinstance(status.get("embedding"), dict) else {}
    image_status = status.get("image") if isinstance(status.get("image"), dict) else {}
    has_core_services = bool(model_status.get("running") and embedding_status.get("running"))
    has_image_service = bool(image_status.get("running"))
    if not has_core_services and not has_image_service:
        return False
    payload: Dict[str, Dict[str, object]] = {}
    if has_core_services:
        model_base_url = str(model_status.get("base_url") or local_openai_base_url(8000)).rstrip("/")
        embedding_base_url = str(embedding_status.get("base_url") or local_openai_base_url(8001)).rstrip("/")
        payload.update(
            {
                MODEL_SLOT_CHAT: {
                    "provider": "local",
                    "display_name": LOCAL_MODEL_DISPLAY_NAME,
                    "base_url": model_base_url,
                    "model": MODEL_NAME,
                    "api_key": "",
                    "use_proxy": False,
                    "proxy_url": "",
                },
                MODEL_SLOT_BACKGROUND: {
                    "provider": "local",
                    "display_name": LOCAL_MODEL_DISPLAY_NAME,
                    "base_url": model_base_url,
                    "model": MODEL_NAME,
                    "api_key": "",
                    "use_proxy": False,
                    "proxy_url": "",
                },
            }
        )
        embedding_client.EMBEDDING_BASE_URL = embedding_base_url
    if has_image_service:
        payload[MODEL_SLOT_IMAGE] = {
            "provider": "hidream",
            "display_name": IMAGE_MODEL_DISPLAY_NAME,
            "base_url": str(image_status.get("base_url") or "http://127.0.0.1:8002").rstrip("/"),
            "model": IMAGE_MODEL_DISPLAY_NAME,
            "api_key": "",
            "use_proxy": False,
            "proxy_url": "",
        }
    save_model_settings(payload)
    return True


def start_local_model_service_and_configure() -> Dict[str, object]:
    with LOCAL_MODEL_SERVICE_LOCK:
        before = local_model_service_status()
        launch = start_missing_local_model_services(before)
        status = before if not launch.get("started") else local_model_service_status()
        settings_updated = apply_local_model_service_settings(status)
        status["launch"] = launch
        status["settings_updated"] = settings_updated
        return status
