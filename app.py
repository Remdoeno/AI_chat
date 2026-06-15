from qwen_app.startup.loader import load_namespace

# Compatibility shim: expose the same names that the old monolithic app.py exposed.
globals().update(load_namespace())
