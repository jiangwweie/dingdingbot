# 开工技能 - 全套准备 (v3.0 适配版)

**触发词**: 开工、开始工作、开始、kaigong

**版本**: v3.0 (适配工作流重构)

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

### 3. 读取交接文档 (handoff)

读取最新的 `docs/planning/handoff-*.md` 文件（优先 `handoff-latest.md`），提取：
- 上次会话完成的工作详情
- 审查发现的问题清单
- 下一步计划与预计工时

**输出**:
```
📌 上次会话交接 (docs/planning/handoff-*.md):

### 完成工作
- [上次完成的工作摘要]

### 待办事项
- [待办事项列表]
```

### 4. 读取 tasks.json (v3.0 核心) ⭐

读取 `docs/planning/tasks.json`，获取机器可读的任务清单：

```python
import json
with open("docs/planning/tasks.json") as f:
    tasks = json.load(f)

# 提取信息:
# - feature: 功能名称
# - session: 当前阶段 (planning/development/testing)
# - tasks[]: 任务列表 (含状态/依赖/角色)
# - parallel_clusters: 并行簇信息
```

**输出**:
```
📋 任务清单 (docs/planning/tasks.json):

功能：[feature 字段]
当前阶段：[session 字段]

### 待办任务
| ID | 任务 | 角色 | 状态 | 依赖 |
|----|------|------|------|------|
| T1 | xxx | backend | ☐ 待开始 | 无 |
| T2 | xxx | frontend | 🔄 进行中 | T1 |

### 并行簇
- 簇 1: [T1]
- 簇 2: [T2, T3]
```

### 5. 读取 task_plan.md (planning-with-files)

读取 `docs/planning/task_plan.md`，显示：
- 当前进行中的任务阶段
- 任务依赖关系
- 整体进度状态

### 6. 读取进度日志

读取 `docs/planning/progress.md` 最新的进度记录，显示：
- 上次会话的待办事项
- 需要继续关注的问题

### 7. 读取技术发现

读取 `docs/planning/findings.md` 中与会话相关的技术发现：
- 架构决策记录
- 踩坑记录
- 技术债清单

### 8. 更新 board.md 为"会话启动"状态 ⭐

```python
# 读取 board.md
# 更新"最后更新"时间为当前时间
# 标记当前阶段为"开发会话"或"测试会话"
# 写入 board.md
```

**输出**:
```
📊 状态看板已更新：docs/planning/board.md
当前阶段：开发会话 / 测试会话
```

### 9. 记录开工时间

在 `docs/planning/progress.md` 顶部添加：

```markdown
## {{当前日期}} - 开工

**开始时间**: {{当前时间}}
**会话阶段**: [从 tasks.json 读取]
**上次待办**: [从 handoff.md 提取]
```

---

## 输出格式

```
🐶 开工 - 准备就绪

📍 当前分支：dev
📝 最近提交：abc1234 上次提交信息

⚠️ 未提交变更：无 / 有（列表）

📌 上次会话交接 (handoff-*.md):
### 完成工作
- [摘要]

### 待办事项
- [待办列表]

📋 任务清单 (tasks.json):
功能：[功能名称]
当前阶段：[planning/development/testing]

| ID | 任务 | 角色 | 状态 | 依赖 |
|----|------|------|------|------|
| T1 | xxx | backend | ☐ 待开始 | 无 |
| T2 | xxx | frontend | 🔄 进行中 | T1 |

📊 状态看板：board.md 已更新

📋 待办任务 (task_plan.md):
- [任务 1] 状态：pending
- [任务 2] 状态：in_progress

🎯 今日建议：[从任务清单提取优先级最高的 3 个待办]

---
准备好开始了吗？请告诉我今日目标或下一个任务。
```

---

## v3.0 适配要点

| 变更点 | 旧行为 | 新行为 |
|--------|--------|--------|
| 任务来源 | task_plan.md (人工读) | tasks.json (机器可读) ✅ |
| 状态追踪 | 无实时更新 | board.md 会话启动标记 ✅ |
| 交接文档 | 无明确指向 | handoff-*.md ✅ |
| 规划文件 | 单一文件 | planning-with-files 三件套 ✅ |

---

## 异常处理

| 异常场景 | 处理策略 |
|---------|---------|
| tasks.json 不存在 | 提示"未检测到任务清单，建议先运行规划会话" |
| handoff 文档不存在 | 跳过，提示"首次会话，无交接文档" |
| board.md 不存在 | 从模板创建 |
| git 拉取失败 | 继续执行，但警告用户 |

---

*版本：v3.0 | 最后更新：2026-04-03*
