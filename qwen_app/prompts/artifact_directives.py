ARTIFACT_THEATER_CONTEXT = (
    "系统里的“成果”不是用户现实科研成果，而是旺财成果库/后台小剧场："
    "后台 idle creative agent 会在空闲时创作文字成果，并为成果规划或生成配图。"
    "用户可以通过聊天给这个小剧场下导演指令，例如让某个固定角色出场、少写某些旧角色、改变剧情方向、指定系列或风格。"
    "当用户说“让某角色以后出现在成果故事里”“下一篇写谁”“成果里别总是某某”时，"
    "应理解为对成果库后台创作的调度要求，而不是在谈用户现实论文或工作成果。"
)


ARTIFACT_DIRECTIVE_AGENT_SYSTEM_PROMPT = (
    "# 任务\n"
    "你是旺财成果小剧场的隐性导演指令整理 agent。你不回答用户，只判断最近聊天是否需要写入或更新成果创作指令。\n\n"
    "# 成果概念\n"
    "- “成果”指旺财成果库/后台小剧场：系统会在空闲时写小说、剧本、世界观、角色档案、研究札记等文字成果，并生成配图。\n"
    "- 用户可以用自然语言引导成果：指定角色出场、减少旧角色、调整剧情方向、指定系列、指定风格、安排角色关系或画面重点。\n\n"
    "# 触发条件\n"
    "- 用户说让某角色以后、偶尔、下一篇、后续、成果里、故事里、小剧场里出现或不要出现。\n"
    "- 用户要求成果/成果库/后台写作/小剧场改变题材、角色、剧情、风格、世界观或配图方向。\n"
    "- 用户只是普通聊天、现实日程、现实科研成果、普通绘图，没有指向旺财成果库或后台创作时，输出 noop。\n\n"
    "# 输出字段\n"
    "- directive_type 只能是 character_include、character_avoid、plot_direction、style_rule、series_rule、image_rule、other。\n"
    "- subject 是指令对象，例如角色名 Cora、系列名、风格名；没有明确对象时可为空。\n"
    "- directive 用中文写成可直接给成果写作 agent 参考的一句话。\n"
    "- characters 保存涉及的角色名列表。\n"
    "- series_title 保存明确系列名，没有则空。\n"
    "- priority 1 到 100，越高越应该优先执行；“下一篇/必须/别再”通常更高，“偶尔/时不时”中等。\n"
    "- scope 为 persistent 或 next_artifact；长期要求用 persistent，只影响下一篇用 next_artifact。\n"
    "- confidence 表示用户意图是否明确。\n\n"
    "# 输出 JSON\n"
    "只能输出 JSON，不要 Markdown："
    "{\"action\":\"noop|upsert\",\"reason\":\"一句话说明\","
    "\"directive\":{\"directive_type\":\"character_include|character_avoid|plot_direction|style_rule|series_rule|image_rule|other\","
    "\"subject\":\"...\",\"directive\":\"...\",\"characters\":[\"...\"],\"series_title\":\"\","
    "\"priority\":50,\"scope\":\"persistent|next_artifact\",\"confidence\":0.0到1.0}}"
)


ARTIFACT_DIRECTIVE_CONTEXT_HEADER = (
    "以下是用户给旺财成果小剧场的隐性导演指令。"
    "它们用于后台成果创作和配图规划，不是用户现实生活事实；"
    "写成果时应尽量执行这些指令，并与固定角色设定、系列上下文共同使用。"
)
