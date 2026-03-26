# Frontend Developer - 前端开发专家
# 用法：/frontend [可选：任务描述]

Agent(
    subagent_type="frontend-dev",
    prompt="""
请阅读并遵循 .claude/team/frontend-dev/SKILL.md 中的规范。

重要：严格遵守文件边界，只修改 web-front/ 目录下的文件！

用户任务：{{arguments}}

请执行以下步骤：
1. 分析前端需求
2. 确认后端 Schema 接口（如需要）
3. 实现 React + TypeScript + TailwindCSS 代码
4. 自测视觉完整性
"""
)
