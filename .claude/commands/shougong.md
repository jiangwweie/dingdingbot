# 收工技能 - 全套收工 (自动化增强版)

**触发词**: 收工、结束工作、结束、下班、shougong

**核心原则**: 全自动执行，无需用户确认，仅在异常时介入

---

## 执行流程 (全自动)

### 阶段 1: 状态检查

```bash
git status --short
git diff --stat
git log --since="00:00" --oneline
```

**目的**:
- 识别所有变更文件
- 统计变更行数
- 获取今日提交历史
- 读取三件套规划文件当前状态

---

### 阶段 2: 文档自动更新

#### 2.1 更新 progress.md (必须)

在文件顶部追加今日日志：

```markdown
## {{YYYY-MM-DD}} - 收工

### 完成工作
- [根据 git log 和变更文件自动推断]

### 修改文件
- [变更文件列表 + 简要说明]

### Git 提交
- [今日提交哈希 + 信息]
```

#### 2.2 更新 findings.md (条件)

**触发条件**: 检测到新增文件 或 单文件变更>100 行

```markdown
## {{YYYY-MM-DD}} - 技术发现

### [根据变更内容推断主题]
- [自动生成的技术发现条目]
```

#### 2.3 更新 task_plan.md (条件)

**触发条件**: 检测到任务相关文件完成

```markdown
| 任务名称 | 状态 |
|---------|------|
| [匹配任务] | ✅ 已完成 - {{日期}} |
```

---

### 阶段 3: 交接文档生成

创建 `docs/planning/{{YYYY-MM-DD}}-handoff.md`:

```markdown
# {{YYYY-MM-DD}} 会话交接

## 完成工作
[根据 git diff 推断的详细总结]

## 修改文件清单
[按类型分组：后端/前端/测试/文档]

## 待完成任务
[从 task_plan.md 读取 P0/P1 级任务]

## 相关文件索引
[本次修改涉及的文件路径]
```

---

### 阶段 4: Git 提交与推送

```bash
# 1. 暂存所有变更
git add -A

# 2. 生成 commit message
# 规则:
# - src/**/*.py      → feat/fix:
# - tests/**/*.py    → test:
# - docs/**/*.md     → docs:
# - web-front/**     → feat(frontend):
# - requirements.*   → chore(deps):

# 3. 提交
git commit -m "[自动生成的 message]"

# 4. 推送
git push

# 5. 处理 push 拒绝
# 如果被拒绝 → git pull --rebase → git push
```

---

### 阶段 5: 收工报告输出

```
🐶 收工完成 - {{YYYY-MM-DD}}

📝 变更统计:
   M docs/planning/progress.md
   M docs/planning/findings.md (如有)
   M docs/planning/task_plan.md (如有)
   A docs/planning/{{YYYY-MM-DD}}-handoff.md
   [其他业务文件变更...]

💾 Git 提交：[短哈希] [提交信息]

📤 已推送到远程仓库

---
🎉 辛苦了！明天继续。

📌 明日优先事项:
   - [P0] [任务 1]
   - [P0] [任务 2]
   - [P1] [任务 3]
```

---

## 异常处理

| 异常场景 | 处理策略 |
|---------|---------|
| git 冲突 | 停止提交，列出冲突文件，请用户手动解决 |
| push 拒绝 | 自动 `git pull --rebase` 后重试，失败则求助 |
| 文档格式异常 | 尝试修复，失败则跳过并警告 |
| 无变更 | 仅更新 progress.md 日志后提交 |

---

## 自动化规则

### Commit Message 生成逻辑

```python
变更类型优先级:
1. 有 src/ 变更 → 检查是否有测试文件 → test: 或 feat/fix:
2. 有 web-front/ 变更 → feat(frontend): 或 fix(frontend):
3. 仅 docs/ 变更 → docs:
4. 仅 tests/ 变更 → test:
5. 混合变更 → 按主要变更类型 (行数最多)

示例:
- "feat(phase8): 后端 StrategyOptimizer 实现"
- "docs: 更新进度日志 - Phase 8 完成"
- "test(phase8): 86 个单元测试通过"
```

### 任务完成检测逻辑

```python
检测规则:
- 新增测试文件 → 对应测试任务标记完成
- 新增前端组件 → 对应前端任务标记完成
- 提交信息含关键词 → 匹配 task_plan.md 任务

示例:
test_strategy_optimizer.py 新增
→ 匹配 "T1: Optuna 目标函数单元测试"
→ 标记 ✅ 已完成
```

### 明日优先事项推荐

```python
推荐规则:
1. 优先 P0 级进行中任务
2. 按 task_plan.md 顺序取 TOP 3
3. 显示任务名称 + 状态
```

---

## 输出示例

```
🐶 收工完成 - 2026-04-02

📝 变更统计:
   M docs/planning/progress.md
   M docs/planning/task_plan.md
   A docs/planning/2026-04-02-handoff.md
   M src/domain/strategy_optimizer.py

💾 Git 提交：91085ca feat(phase8): 集成 Optuna 自动化调参框架

📤 已推送到远程仓库

---
🎉 辛苦了！明天继续。

📌 明日优先事项:
   - [P0] Phase 8 集成测试执行
   - [P0] Phase 8 E2E 测试验证
   - [P1] 订单管理级联展示功能
```
