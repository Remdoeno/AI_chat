from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

SOURCE_FILES = (
    "wangcai_app/config/runtime.py",
    "wangcai_app/config/model_settings.py",
    "wangcai_app/prompts/chat.py",
    "wangcai_app/prompts/self_profile.py",
    "wangcai_app/config/settings.py",
    "wangcai_app/prompts/agents.py",
    "wangcai_app/prompts/image_generation.py",
    "wangcai_app/prompts/characters.py",
    "wangcai_app/prompts/artifact_directives.py",
    "wangcai_app/config/state.py",
    "wangcai_app/functions/web_search.py",
    "wangcai_app/startup/app_setup.py",
    "wangcai_app/functions/persistence.py",
    "wangcai_app/functions/sessions.py",
    "wangcai_app/functions/memory.py",
    "wangcai_app/functions/image_generation.py",
    "wangcai_app/functions/local_model_service.py",
    "wangcai_app/functions/characters.py",
    "wangcai_app/functions/artifact_directives.py",
    "wangcai_app/functions/artifacts.py",
    "wangcai_app/functions/workers.py",
    "wangcai_app/functions/chat.py",
    "wangcai_app/routes/pages.py",
    "wangcai_app/routes/api.py",
)

_NAMESPACE_CACHE: Dict[str, Any] | None = None


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _new_namespace(root: Path) -> Dict[str, Any]:
    return {
        "__builtins__": __builtins__,
        "__file__": str(root / "app.py"),
        "__name__": "app",
        "__package__": "",
    }


def _execute_source(namespace: Dict[str, Any], source_path: Path) -> None:
    code = source_path.read_text(encoding="utf-8")
    exec(compile(code, str(source_path), "exec"), namespace)


def load_namespace() -> Dict[str, Any]:
    global _NAMESPACE_CACHE
    if _NAMESPACE_CACHE is not None:
        return _NAMESPACE_CACHE
    root = project_root()
    namespace = _new_namespace(root)
    for relative_path in SOURCE_FILES:
        _execute_source(namespace, root / relative_path)
    if "app" not in namespace:
        raise RuntimeError("Split app sources did not create FastAPI app")
    _NAMESPACE_CACHE = namespace
    return namespace


def load_app() -> Any:
    return load_namespace()["app"]
