---
name: start-work
description: 开工技能 - 同步 git 状态、加载任务清单、检查待办事项、显示今日目标
license: Proprietary
---

# 🔨 开工技能 (Start Work)

**触发方式**: 用户说「开工」「开始工作」「开始今天的任务」等

---

## 核心职责

1. **同步 git 状态** - 确保代码是最新的
2. **加载任务清单** - 读取 `docs/planning/task_plan.md`
3. **检查待办事项** - 读取 `docs/planning/progress.md`
4. **记录开工时间** - 在 `progress.md` 添加新条目
5. **检查未提交变更** - 避免上下文混淆
6. **显示今日目标** - 从任务计划中提取

---

## 执行步骤

### 步骤 1: 同步 Git 状态

```bash
# 拉取最新代码
git pull

# 检查当前分支
git branch

# 显示最近 3 条 commit
git log --oneline -3
```

### 步骤 2: 检查未提交变更

```bash
# 显示所有未提交修改
git status
```

**如有残留修改**：提醒用户确认是否继续，或先处理变更

### 步骤 3: 加载任务状态

```python
# 读取任务计划文件
with open("docs/planning/task_plan.md") as f:
    task_plan = f.read()

# 读取进度日志
with open("docs/planning/progress.md") as f:
    progress = f.read()
```

### 步骤 4: 解析并显示任务状态

提取以下信息：
- `pending` 任务列表
- `in_progress` 任务列表
- 最近完成的 `completed` 任务

### 步骤 5: 显示最后待办事项

从 `progress.md` 末尾提取「待办」或「TODO」段落

### 步骤 6: 记录开工时间

在 `progress.md` 中添加新条目：

```markdown
---
## {日期} - 开工

**时间**: {HH:MM}

**今日目标**:
- {从 task_plan 提取或用户指定}

---
```

### 步骤 7: 输出开工报告

```markdown
## 🔨 开工报告 ({日期})

### 代码状态
- 当前分支：`{branch}`
- 最近 commit：`{commit_hash} {message}`
- 未提交变更：{有/无}

### 任务状态
| 任务 | 状态 |
|------|------|
| {task} | {status} |

### 待办事项
- {待办 1}
- {待办 2}

### 今日目标
1. {目标 1}
2. {目标 2}

---
**开工时间**: {HH:MM} | 已记录到 `progress.md`
```

---

## 示例输出

```markdown
## 🔨 开工报告 (2026-03-31)

### 代码状态
- 当前分支：`v2`
- 最近 commit：`d4bed5a refactor: 项目目录结构清理`
- 未提交变更：无

### 任务状态
| 任务 | 状态 |
|------|------|
| 实现策略预览接口 | pending |
| 实现递归评估引擎 | pending |
| 前端预览组件开发 | in_progress |

### 待办事项
- 完成前端预览组件的递归渲染
- 等待后端接口对齐后进行联调

### 今日目标
1. 完成前端预览组件开发
2. 与后端接口对齐
3. 编写组件测试用例

---
**开工时间**: 09:30 | 已记录到 `progress.md`
```

---

## 异常处理

| 场景 | 处理方式 |
|------|----------|
| `task_plan.md` 不存在 | 跳过任务加载，询问用户今日目标 |
| `progress.md` 不存在 | 创建新文件 |
| Git 仓库有冲突 | 提醒用户先解决冲突 |
| 有未提交变更 | 显示变更列表，询问是否继续 |

---

## 相关文件

- `docs/planning/task_plan.md` - 任务计划
- `docs/planning/progress.md` - 进度日志
- `docs/planning/findings.md` - 研究发现

---

*让每一天从清晰的状态开始 🐶*
