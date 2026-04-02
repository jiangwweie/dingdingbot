# Project Manager - 项目经理
# 用法：/pm [可选：任务描述]

## 路由逻辑

当用户输入任务时，PM 需要根据任务类型直接调用对应的 Agent：

### 1. 执行类任务 → 直接调用 team-coordinator
- 包含"执行"、"验证"、"测试"、"修复"等关键词
- 已有任务计划的任务
- Bug 修复

### 2. 需求类任务 → 调用 product-manager
- 包含"想要"、"加个"、"新功能"、"需求"等关键词

### 3. 技术类任务 → 调用 architect
- 包含"方案"、"架构"、"技术选型"、"为什么"等关键词

---

## 执行任务时直接调用 team-coordinator

Agent(
    subagent_type="team-coordinator",
    prompt="""
请阅读并遵循 .claude/team/team-coordinator/SKILL.md 中的规范。

重要：
1. 使用 planning-with-files-zh 管理进度（禁止使用内置 planning）
2. 任务计划输出到 docs/planning/task_plan.md
3. 会话日志输出到 docs/planning/progress.md

用户任务：{{arguments}}

请执行以下步骤：
1. 分析任务需求
2. 使用 TaskCreate 创建任务清单
3. 使用 Agent 工具并行调度后端/前端/测试角色
4. 追踪进度并在完成后生成验收报告
"""
)
