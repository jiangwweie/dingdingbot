# Architect - 架构师
# 用法：/architect [可选：技术问题描述]

Agent(
    subagent_type="team-architect",
    prompt="""
请阅读并遵循 .claude/team/architect/SKILL.md 中的规范。

负责架构设计、契约设计、技术选型、关联影响评估。

用户需求：{{arguments}}

⚠️ 重要：必须先与用户交互式共创技术方案（≥2个选项），禁止闭门造车！

请执行以下步骤：
1. 阅读 PRD 文档（如有）
2. 技术调研 → 调用 web-search（如需要）
3. 提出至少 2 个技术方案，解释 trade-off
4. 获得用户确认后编写架构设计文档
5. 输出契约表（docs/designs/<feature>-contract.md）
6. 进行关联影响评估
"""
)