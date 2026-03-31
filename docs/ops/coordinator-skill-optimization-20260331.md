# Team Coordinator 技能优化说明

**优化时间**: 2026-03-31
**提交**: d976aed
**基于会话**: 方案 C 实施经验总结

---

## 优化背景

在本次方案 C 实施过程中，我们经历了完整的诊断→实施→测试→部署流程。基于此经验，发现原 Coordinator 技能缺少两个关键环节：

1. **开工前准备** - 缺少任务规划步骤，容易导致盲目开始
2. **收工总结** - 缺少标准化收工流程，容易遗漏验证和文档

---

## 优化内容

### 1. 新增「阶段 -1: 开工准备」(Pre-Flight Checklist)

**核心步骤**:

```python
# 1. 调用 planning-with-files-zh 创建任务计划
Agent(subagent_type="planning-with-files-zh",
      prompt="为任务 [X] 创建执行计划，输出到 docs/planning/task_plan.md")

# 2. 任务复杂度判断
| 类型 | 处理方式 |
|------|----------|
| 简单任务 (单文件修改) | 直接分配对应角色 |
| 中等任务 (2-3 文件) | 创建简易计划 + 直接执行 |
| 复杂任务 (前端 + 后端 + 测试) | 完整规划 + 全自动流水线 |
```

**检查清单**:
- [ ] 已创建 `docs/planning/task_plan.md`
- [ ] 已识别任务复杂度
- [ ] 已确定需要参与的角色

---

### 2. 新增「阶段 7: 收工总结」(Post-Flight Checklist)

**核心步骤**:

```python
# 1. 运行最终验证
pytest tests/unit/ tests/integration/ -v --tb=short

# 2. 调用 verification-before-completion
Agent(subagent_type="verification-before-completion",
      prompt="验证任务 [X] 已完成，所有测试通过")

# 3. 更新任务计划文件
# docs/planning/progress.md 记录完成状态

# 4. 生成交付报告
# - 已完成任务列表
# - 交付物清单
# - 验证结果

# 5. 提交代码并推送
git add <files>
git commit -m "<conventional commit message>"
git push origin <branch>
```

**检查清单**:
- [ ] 所有测试通过（单元 + 集成）
- [ ] 代码已提交并推送
- [ ] `docs/planning/progress.md` 已更新
- [ ] 交付报告已生成
- [ ] 诊断报告已更新（如适用）

---

### 3. 优化全局技能调度指南

**新增「开工前准备」表格**:

| 场景 | 调用 Skill | 命令 |
|------|-----------|------|
| 复杂任务需要规划 | `planning-with-files-zh` | `Agent(subagent_type="planning-with-files-zh", ...)` |
| 任务计划创建后 | 读取文件 | 从 `docs/planning/task_plan.md` 继续执行 |

**新增「完成阶段 (收工检查)」表格**:

| 场景 | 调用 Skill | 命令 |
|------|-----------|------|
| 完成前最终验证 | `verification-before-completion` | `Agent(subagent_type="verification-before-completion")` |
| 功能完成需要合并 | `finishing-a-development-branch` | `Agent(subagent_type="finishing-a-development-branch")` |
| 请求正式审查 | `requesting-code-review` | `Agent(subagent_type="requesting-code-review")` |
| 更新任务进度 | 读取/写入 `progress.md` | 记录完成状态和后续建议 |

---

## 优化效果

### 优化前流程

```
【阶段 0】需求接收 → 【阶段 1】契约设计 → ... → 【阶段 6】提交汇报
```

**问题**:
- 缺少任务规划，容易盲目开始
- 缺少标准化收工流程
- 文档更新依赖个人习惯

### 优化后流程

```
【阶段 -1】开工准备 → 【阶段 0】需求接收 → ... → 【阶段 6】提交汇报 → 【阶段 7】收工总结
```

**改进**:
- ✅ 开工前强制规划，降低返工风险
- ✅ 收工标准化，确保质量一致性
- ✅ 文档更新纳入流程，知识沉淀更完善

---

## 使用示例

### 场景：实施新功能

```python
# ========== 阶段 -1: 开工准备 ==========
# 调用 planning-with-files-zh 创建计划
Agent(subagent_type="planning-with-files-zh",
      prompt="为策略预览功能创建执行计划")

# 阅读 plan 文件，了解任务分解
Read docs/planning/task_plan.md

# ========== 阶段 0-6: 执行流水线 ==========
# (原有的全自动流水线步骤)

# ========== 阶段 7: 收工总结 ==========
# 运行测试验证
pytest tests/unit/ -v

# 生成交付报告
# - 已完成任务列表
# - 交付物清单
# - 测试通过率

# 更新 progress.md
# - 记录完成时间
# - 记录遇到的问题和解决方案
# - 后续优化建议

# 提交代码
git commit -m "feat: 实现策略预览功能"
git push origin v2
```

---

## 相关文件

- `.claude/team/team-coordinator/SKILL.md` - Coordinator 技能定义（已更新）
- `docs/planning/task_plan.md` - 任务计划模板
- `docs/planning/progress.md` - 进度记录模板

---

## 后续优化建议

1. **自动化检查清单** - 考虑创建脚本自动验证收工检查项
2. **交付报告模板** - 创建标准化交付报告模板
3. **经验回顾机制** - 每次复杂任务后回顾流程，持续优化

---

**优化人员**: Team Coordinator + Backend Dev
**审查人员**: QA Tester
