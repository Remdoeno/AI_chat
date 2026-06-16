from qwen_app.startup.loader import load_namespace

# Compatibility shim: expose the same names that the old monolithic app.py exposed.
globals().update(load_namespace())



# !./stop_qwen_web.sh
# !./start_qwen_web.sh

# !curl http://127.0.0.1:7777/api/health

# !netstat -lntp | grep 7777
