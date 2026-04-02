# Architect - 架构师
# 用法：/architect [可选：任务描述]

Agent(
    subagent_type="architect",
    prompt="""
请阅读并遵循 .claude/team/architect/SKILL.md 中的规范。

用户任务：{{arguments}}

请执行以下步骤：
1. 分析技术需求
2. 设计架构方案和接口契约
3. 进行技术选型
4. 评估关联影响
5. 输出架构设计文档
"""
)
