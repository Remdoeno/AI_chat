# 旺财1.2 发布日志

时间：2026-06-09

## 版本定位

旺财1.2 是一次缺陷修复和可发布整理版本，重点修复手机端 UI、Analysis mode 调试视图、历史 session 加载、记忆整理上下文和公开部署文档。

## 主要修复

- 聊天气泡：统一“助手/你”和时间戳在同一行展示，修复手机端助手气泡偏右、用户气泡偏左、用户时间戳缺失的问题。
- 发送/停止：普通聊天和 Analysis mode 都改为发送按钮原位切换为深红色停止按钮，减少额外按钮错位。
- 输入区：修复桌面端发送按钮没有与可输入文本框垂直居中的问题，缩短按钮高度并保持工具按钮靠近输入框。
- Analysis mode：移动端恢复可整体滚动的分析布局，保留后台明细；历史加载改为顶部实体按钮。
- 记忆整理：memory agent 输入改为最近最多 3 轮对话，并把 assistant 内容标注为 `assistant_context_only`，只允许从 user 行抽取长期记忆。
- 记忆判据：memory agent 必须输出 rationale；增强对助手语气、开场白、长期互动要求的敏感度。
- 事件与事实：降低第三方人物、公开事实和检索问题被误存为用户 identity 的概率；保留未来 event 的提醒能力。
- 文档：README 升级为 1.2，补充模型 API、embedding、代理、idle agent、管理员密码和私有数据排除说明。

## 验证记录

- 远端服务：已在服务器部署目录重启，`/api/health` 返回 `ok=true`。
- 语法检查：远端 `/opt/conda/bin/python3 -m py_compile app.py` 通过。
- 静态回归：远端 `tests.test_static_regressions` 通过。
- 记忆相关行为：远端针对 memory agent 上下文、assistant context-only、第三方事实过滤、未来 event、用户视角 embedding 等测试通过。

## 未上传内容

本次只上传脱敏代码、测试、公开文档和本发布日志。以下运行期内容不上传：

- 模型权重与 embedding 权重。
- SQLite 数据库、聊天记录、长期记忆、管理员密码 hash。
- 私有故事种子、本地代理地址、本地环境变量。
- 服务运行日志、隧道日志、旧 bundle 和本机临时文件。
