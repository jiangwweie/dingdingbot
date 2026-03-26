# Team Coordinator - 团队协调器
# 用法：/coordinator [可选：任务描述]

请使用 Agent 工具调用 team-coordinator 技能：

Agent(
    subagent_type="team-coordinator",
    prompt="""
请阅读并遵循 .claude/team/team-coordinator/SKILL.md 中的规范。

用户任务：{{arguments}}

请执行以下步骤：
1. 分析任务需求
2. 分解为前端/后端/测试子任务
3. 使用 TaskCreate 创建任务清单
4. 使用 Agent 工具并行调度各角色
5. 汇总输出结果
"""
)
