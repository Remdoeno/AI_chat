from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_wangcai_namespace():
    loader_path = Path(__file__).resolve().parent / "wangcai_app" / "startup" / "loader.py"
    spec = spec_from_file_location("wangcai_loader", loader_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load Wangcai loader: {loader_path}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load_namespace()

# Compatibility shim: expose the same names that the old monolithic app.py exposed.
globals().update(_load_wangcai_namespace())



# !./stop_wangcai_ai.sh
# !./start_wangcai_ai.sh

# !curl http://127.0.0.1:7777/api/health

# !netstat -lntp | grep 7777
