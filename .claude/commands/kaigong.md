# 开工技能 - 全套准备 (增强版)

**触发词**: 开工、开始工作、开始、kaigong

---

## 执行流程

### 1. 同步 git 状态

```bash
git pull origin $(git branch --show-current) 2>/dev/null || echo "无需拉取或已是最新"
git branch --show-current
git log --oneline -3
```

### 2. 检查未提交变更

```bash
git status --short
```

如果有未提交的变更，显示提醒：
> ⚠️ 发现未提交的变更，请先处理残留修改

### 3. 读取交接文档 (handoff.md)

读取最新的 `docs/planning/*-handoff.md` 文件，提取：
- 上次会话完成的工作详情
- 审查发现的问题清单
- 下一步计划与预计工时

**输出**:
```
📌 上次会话交接 (docs/planning/YYYY-MM-DD-handoff.md):

### 完成工作
- [上次完成的工作摘要]

### 审查发现的问题
- [问题清单]

### 下一步计划
- [待办事项]
```

### 4. 加载任务清单

读取 `docs/planning/task_plan.md`，显示：
- 当前进行中的任务（in_progress）
- 待办任务（pending）
- 任务依赖关系

### 5. 检查待办事项

读取 `docs/planning/progress.md` 最新的进度记录，显示：
- 上次会话的待办事项
- 需要继续关注的问题

### 6. 记录开工时间

在 `docs/planning/progress.md` 顶部添加：

```markdown
## {{当前日期}} - 开工

**开始时间**: {{当前时间}}
**会话目标**: [待用户指定]
**上次待办**: [从 handoff.md 提取]
```

### 7. 读取核心记忆

加载 `.claude/memory/project-core-memory.md` 中的：
- 工作流程偏好
- v3 迁移优先级
- 审查红线

### 8. 显示今日目标提示

如果 `task_plan.md` 中有明确的下一阶段目标，显示出来。

---

## 输出格式

```
🐶 开工 - 准备就绪

📍 当前分支：dev
📝 最近提交：abc1234 上次提交信息

⚠️ 未提交变更：无 / 有（列表）

📌 上次会话交接 (YYYY-MM-DD):
### 完成工作
- [摘要]

### 待办事项
- [从 handoff.md 提取]

📋 待办任务：
- [任务 1] 状态：pending
- [任务 2] 状态：in_progress

🎯 今日建议：[从任务清单提取]

---
准备好开始了吗？请告诉我今日目标或下一个任务。
```
