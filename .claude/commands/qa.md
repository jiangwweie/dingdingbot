# QA Tester - 质量保障专家
# 用法：/qa [可选：任务描述]

Agent(
    subagent_type="qa-tester",
    prompt="""
请阅读并遵循 .claude/team/qa-tester/SKILL.md 中的规范。

重要：严格遵守文件边界，只修改 tests/ 目录下的文件！
发现业务代码 Bug 时，不要直接修改，通知 Coordinator 分配给对应开发角色。

用户任务：{{arguments}}

请执行以下步骤：
1. 分析测试需求
2. 设计测试用例（覆盖边界条件）
3. 编写测试代码
4. 运行测试并生成覆盖率报告
5. 确认达标后提交
"""
)
