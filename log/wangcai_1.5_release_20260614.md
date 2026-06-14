# 旺财1.5 Release Log

日期：2026-06-14

## 主要变化

- 记录并保留用户亲自调整的主 `SYSTEM_PROMPT`，后续工程约束不再覆盖主 prompt。
- 聊天页和分析模式会隐藏模型误复述的内部 `[message_time: ...]` 前缀。
- 黑暗模式下“助手 / 你”发言者标签改为更明亮颜色，避免黑金主题里看不清。
- 记忆写入引入语义 validation agent，替代 `assistant_context_leak` 的逐字启发式误判。
- 记忆整理 agent 提高默认输出预算，并增加 JSON 修复 agent，降低后台记忆任务因格式截断失败的概率。
- README 更新为旺财1.5，并把配置系统整理顺延为 1.6 计划。

## 验证

- 服务器部署目录 `/base/home/lizhzh/Project3/qwen_web` 已同步关键文件。
- 远端 `/opt/conda/bin/python3 -m py_compile app.py schemas.py embedding_client.py memory.py vector_memory.py streaming_utils.py` 通过。
- 远端 `http://127.0.0.1:7777/api/health` 返回模型和数据库正常。

## 隐私

- 未上传数据库、日志、模型权重、`.env`、管理员密码或私有运行参数。
