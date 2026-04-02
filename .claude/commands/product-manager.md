# Product Manager - 产品经理
# 用法：/product-manager [可选：任务描述]

Agent(
    subagent_type="product-manager",
    prompt="""
请阅读并遵循 .claude/team/product-manager/SKILL.md 中的规范。

用户任务：{{arguments}}

请执行以下步骤：
1. 收集和分析用户需求
2. 编写用户故事和 PRD
3. 定义 MVP 范围和优先级
4. 输出需求文档
"""
)
