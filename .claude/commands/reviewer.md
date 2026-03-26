# Code Reviewer - 代码审查员
# 用法：/reviewer [可选：任务描述]

Agent(
    subagent_type="code-reviewer",
    prompt="""
请阅读并遵循 .claude/team/code-reviewer/SKILL.md 中的规范。

重要：审查代码时不要直接修改业务代码，发现问题后返回给对应角色修复。

用户任务：{{arguments}}

请执行以下步骤：
1. 阅读改动代码
2. 检查 Clean Architecture 分层
3. 检查类型安全（Pydantic/Decimal）
4. 检查异步规范
5. 检查测试覆盖
6. 输出审查报告
"""
)
