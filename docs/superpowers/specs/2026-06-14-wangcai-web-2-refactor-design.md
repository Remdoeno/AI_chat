# Wangcai Web 2.0 Refactor Design

## Goal

在服务器 `/base/home/lizhzh/Project3` 下新建 `wangcai_web`，以当前 `qwen_web` 的线上行为为基线，重构为旺财 2.0 工程。重构后的 `wangcai_web/app.py` 必须保持入口职责，目标不超过 500 行；所有后续开发只进入 `wangcai_web`，不修改现有 `qwen_web`。

## Non-Goals

- 不改动 `/base/home/lizhzh/Project3/qwen_web` 中任何文件。
- 不在本机运行后端测试。
- 不在第一阶段重写模型调用、记忆召回、成果生成、分析模式等业务行为。
- 不在第一阶段破坏或强制转换现有 SQLite 数据库。

## Migration Strategy

采用两阶段兼容迁移。

第一阶段先让 `wangcai_web` 以和 `qwen_web` 完全一致的效果跑起来，同时完成代码结构拆分、配置入口整理、运行路径隔离和测试基线迁移。这个阶段允许继续读取兼容数据库，但所有新配置路径、运行目录和导出目录都按 2.0 结构建立。

第二阶段再把用户数据物理目录化：按用户 ID、设备 ID、故事成果、聊天记录等目录导出或同步数据。第二阶段必须有独立迁移脚本和回滚策略，不能把数据迁移混入入口拆分。

## Target Directory

服务器端目标：

```text
/base/home/lizhzh/Project3/wangcai_web
```

本地规划和文档仍写在当前仓库，实际实现时通过 SSH 在服务器上创建目标目录。`qwen_web` 只作为只读基线。

## Architecture

`wangcai_web` 使用包结构组织业务，入口文件只负责应用组装、生命周期挂载和路由注册。

```text
wangcai_web/
  app.py
  wangcai/
    core/
      config.py
      paths.py
      lifecycle.py
      interfaces.py
      time_utils.py
    web/
      app_factory.py
      static_pages.py
      sse.py
      auth_routes.py
      session_routes.py
    chat/
      routes.py
      service.py
      prompts.py
      attachments.py
      rate_limit.py
    memory/
      routes.py
      service.py
      repository.py
      vector_store.py
      prompts.py
      dedupe.py
      recall.py
    analysis/
      routes.py
      service.py
      trace_repository.py
      formatters.py
    artifacts/
      routes.py
      service.py
      repository.py
      prompts.py
      idle_worker.py
    search/
      service.py
      planner.py
      parsers.py
      ranking.py
    auth/
      service.py
      password_store.py
    persistence/
      sqlite.py
      migrations.py
      legacy_compat.py
    user_data/
      export.py
      device_store.py
      user_store.py
      artifact_store.py
      chat_store.py
    models/
      qwen_client.py
      embedding_client.py
    schemas/
      chat.py
      auth.py
      memory.py
      artifacts.py
      users.py
    static/
    config/
    data/
    logs/
    tests/
```

模块边界按职责拆分：路由只解析 HTTP，请求模型放在 `schemas/`，业务逻辑放在 `service.py`，数据库访问放在 `repository.py` 或 `persistence/`，prompt 文本放到对应领域的 `prompts.py` 或配置文件。

## app.py Contract

`wangcai_web/app.py` 目标职责：

- 读取应用配置。
- 创建 FastAPI app。
- 挂载静态目录。
- 注册各模块 router。
- 暴露 `app` 给 uvicorn。

`app.py` 不直接包含数据库 SQL、prompt、模型调用、业务规则、HTML 解析器、记忆召回算法或后台 worker 细节。

## Configuration Design

所有可配置项拆成 JSON 文件，默认路径为 `wangcai_web/config/`。环境变量只负责覆盖配置文件路径或少量部署入口参数。

```text
config/
  app.json
  models.json
  memory.json
  search.json
  idle_agent.json
  auth.json
  rate_limit.json
  user_data.json
  ui.json
```

职责：

- `app.json`：服务名、版本、host、port、时区、日志级别。
- `models.json`：聊天模型、embedding 模型、base_url、model_name、timeout、max_tokens、temperature、top_p。
- `memory.json`：召回数量、阈值、压缩参数、去重 agent 参数、prompt 模板路径。
- `search.json`：搜索开关、代理、搜索 planner 参数、结果数量、摘要限制。
- `idle_agent.json`：后台创作开关、间隔、token 限制、故事种子、术语替换路径。
- `auth.json`：管理员密码 hash 文件路径、session/cookie 策略。
- `rate_limit.json`：设备级限流窗口、告警策略。
- `user_data.json`：用户数据根目录、导出策略、legacy SQLite 兼容路径。
- `ui.json`：前端版本号、缓存破坏版本、页面标题、可展示名称。

配置加载顺序：

1. 加载内置默认值。
2. 加载 `config/*.json`。
3. 应用环境变量覆盖。
4. 启动时校验必要路径和字段。

配置对象以不可变 dataclass 或 Pydantic model 传入服务，避免模块直接读取全局环境变量。

## User Data Design

第一阶段建立目录，不强制完成全量迁移。

```text
data/
  legacy/
    chat_history.sqlite3
    admin_auth.json
  users/
    users.json
    <shared_user_id>/
      profile.json
      devices.json
      memories/
        <device_id>.jsonl
      chats/
        <device_id>/
          <session_id>.jsonl
      artifacts/
        index.json
        items/
          <artifact_id>.json
  devices/
    <device_id>.json
  exports/
```

第一阶段通过 `persistence/legacy_compat.py` 保持 SQLite 读写行为不变。`user_data/export.py` 提供只读导出能力，把现有 SQLite 中的聊天、记忆、成果按新结构导出，供第二阶段验证。

第二阶段再将默认写路径切换到目录化用户数据，并保留 SQLite 兼容读取一段时间。

## Behavioral Compatibility

迁移后必须保持以下行为一致：

- URL 路由兼容：`/`、`/auth`、`/memory`、`/memory-admin`、`/warn`、`/artifacts`、`/analysis`。
- API 兼容：现有 `/api/*` 请求和响应字段不改名。
- 静态页面效果兼容：先复制现有 `static/`，只改缓存版本和标题时必须明确记录。
- 数据兼容：默认读取旧 SQLite 数据库副本，不直接修改 `qwen_web/data/chat_history.sqlite3`。
- 启动兼容：`./start_wangcai_web.sh` 默认监听 7777 或另一个明确配置端口；如果和现有服务并行测试，使用不同端口，例如 7788。

## Testing Strategy

遵循项目约束，不在本机运行后端测试。实施时每一步在服务器 `wangcai_web` 下运行远端测试或静态验证。

测试分层：

- 每个模块拆分后先跑对应远端单元测试。
- 路由拆分后跑现有 API 行为测试。
- 静态资源迁移后跑现有静态回归测试。
- 最后启动 `wangcai_web` 到测试端口，执行健康检查和关键页面 curl。

每次运行命令都在本地 `log/` 记录命令、时间和结果摘要。

## Incremental Implementation Order

1. 只读复制服务器 `qwen_web` 到 `wangcai_web`，确认两者文件分离。
2. 新建 `wangcai/` 包和 `create_app()`，让 `app.py` 缩成入口壳。
3. 移动 schemas、streaming、embedding、memory/vector 基础模块。
4. 抽配置系统，先保持默认值等价于现有环境变量。
5. 拆静态页面路由、auth 路由、session/chat 路由。
6. 拆 memory、analysis、artifacts、search 模块。
7. 建立 `data/legacy` 和 `data/users` 结构，并提供只读导出脚本。
8. 增加 `start_wangcai_web.sh`、`stop_wangcai_web.sh`。
9. 远端验证行为一致后，保留 `qwen_web` 原样，后续只改 `wangcai_web`。

## Risks

- `app.py` 当前包含大量隐式全局状态，直接搬动容易改变行为。缓解方式是先移动代码块，不改算法，再逐步注入配置和依赖。
- SQLite schema 和业务逻辑耦合较重，第一阶段不做写路径切换，只做兼容和导出。
- 前端依赖 API 字段和缓存版本，拆路由时必须保持响应结构一致。
- 后台 worker 使用线程和全局状态，拆分时需要先集中到 lifecycle，再考虑服务对象化。

## Acceptance Criteria

- `/base/home/lizhzh/Project3/qwen_web` 文件未改变。
- `/base/home/lizhzh/Project3/wangcai_web/app.py` 不超过 500 行。
- `wangcai_web` 可通过自己的启动脚本启动。
- 关键页面和 API 与 `qwen_web` 行为一致。
- 配置文件存在并覆盖当前主要可配置项。
- 用户数据目录结构存在，并能从 legacy SQLite 导出一份按用户/设备组织的数据快照。
- 远端测试和静态验证记录保存在本地 `log/`。
