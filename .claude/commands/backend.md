# Backend Developer - 后端开发专家
# 用法：/backend [可选：任务描述]

Agent(
    subagent_type="backend-dev",
    prompt="""
请阅读并遵循 .claude/team/backend-dev/SKILL.md 中的规范。

重要：严格遵守文件边界，只修改 src/ 和 config/ 目录下的文件！

用户任务：{{arguments}}

请执行以下步骤：
1. 阅读相关子任务文档
2. 设计领域模型（Pydantic）
3. 实现业务逻辑
4. 编写单元测试
5. 运行 pytest 验证
"""
)
