# app.py Split Design

## Goal

拆分当前服务器版 `app.py`，让入口文件不再承载一万多行业务代码，同时保持线上行为不变。

## Baseline

本地 `/Users/rem/Documents/Qwen3部署/app.py` 与服务器 `/base/home/lizhzh/Project3/qwen_web/app.py` 的 SHA256 一致，拆分以这个版本为准。

## Approach

第一版采用兼容式拆分：`app.py` 只调用 `qwen_app.startup.loader.load_app()`，加载器按固定顺序把拆分文件执行到同一个命名空间里，再返回原来的 FastAPI `app` 对象。

这样可以先获得清晰目录边界，同时避免一次性把大量函数改成包级 import 导致行为漂移。后续再逐步把共享命名空间替换为真实接口、服务和 repository。

## Target Structure

```text
qwen_app/
  config/
    runtime.py
  prompts/
    system.py
  functions/
    web_search.py
    app_core.py
    persistence.py
    memory.py
    artifacts.py
    workers.py
    chat.py
  startup/
    app_setup.py
    loader.py
  routes/
    pages.py
    api.py
```

## Verification

不在本地跑后端测试。完成后上传服务器临时目录，执行远程 `py_compile` 和导入验证；如环境允许，再跑远程现有测试。
