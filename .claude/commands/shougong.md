# 收工技能 - 全套收工 (v3.0 适配版)

**触发词**: 收工、结束工作、结束、下班、shougong

**版本**: v3.0 (适配工作流重构)

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
- 读取 tasks.json 当前状态

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

#### 2.4 更新 tasks.json (必须) ⭐

根据 git 提交和变更文件推断任务完成状态：

```python
import json

# 读取当前 tasks.json
with open("docs/planning/tasks.json") as f:
    tasks = json.load(f)

# 推断规则:
# 1. 新增测试文件 → 对应测试任务 completed
# 2. 新增前端组件 (.tsx/.ts) → 对应前端任务 completed
# 3. 新增后端文件 (.py in src/) → 对应后端任务 completed
# 4. 提交信息包含任务 ID → 标记对应任务 completed

# 示例匹配逻辑:
for commit in today_commits:
    if "T1" in commit or "后端" in commit:
        mark_task_completed("T1")
    if "F1" in commit or "前端" in commit:
        mark_task_completed("F1")

# 写回 tasks.json
with open("docs/planning/tasks.json", "w") as f:
    json.dump(tasks, f, indent=2, ensure_ascii=False)
```

**更新字段**:
- `tasks[].status`: "pending" → "in_progress" → "completed"
- `session`: 根据进度更新阶段
- `last_updated`: 当前时间戳

#### 2.5 更新 board.md (必须) ⭐

根据 tasks.json 中的任务状态更新状态看板：

```python
import json

# 读取 tasks.json
with open("docs/planning/tasks.json") as f:
    tasks = json.load(f)

# 生成 board.md 内容
board = f"""# 状态看板

**功能**: {tasks.get('feature', '未知')}
**最后更新**: {datetime.now().strftime('%Y-%m-%d %H:%M')}
**当前阶段**: {tasks.get('session', 'unknown')}

---

## 📊 任务状态

| 任务 ID | 任务名称 | 角色 | 状态 | 阻塞依赖 |
|---------|----------|------|------|----------|
"""

status_icon = {
    "pending": "☐ 待开始",
    "in_progress": "🔄 进行中",
    "completed": "✅ 已完成",
    "blocked": "🔴 阻塞"
}

for task in tasks.get("tasks", []):
    icon = status_icon.get(task.get("status", "pending"), "☐")
    blocked_by = task.get("blocked_by", [])
    dep = ", ".join(blocked_by) if blocked_by else "无"
    board += f"| {task['id']} | {task['subject']} | {task['role']} | {icon} | {dep} |\n"

# 写入 board.md
with open("docs/planning/board.md", "w") as f:
    f.write(board)
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

### 后端 (src/)
- `src/xxx.py` - 功能说明

### 前端 (web-front/)
- `web-front/src/xxx.tsx` - 功能说明

### 测试 (tests/)
- `tests/test_xxx.py` - 测试说明

### 文档 (docs/)
- `docs/planning/tasks.json` - 任务状态更新
- `docs/planning/board.md` - 看板更新

## 任务状态

| 任务 ID | 任务名称 | 状态变更 |
|---------|----------|----------|
| T1 | xxx | pending → completed |
| T2 | xxx | in_progress → completed |

## 待完成任务
[从 tasks.json 读取 pending 状态的任务]

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
   U docs/planning/tasks.json (任务状态更新)
   U docs/planning/board.md (看板更新)
   A docs/planning/{{YYYY-MM-DD}}-handoff.md
   [其他业务文件变更...]

💾 Git 提交：[短哈希] [提交信息]

📤 已推送到远程仓库

---
🎉 辛苦了！明天继续。

📌 明日优先事项:
   - [P0] [从 tasks.json 读取 pending 任务 1]
   - [P0] [从 tasks.json 读取 pending 任务 2]
   - [P1] [从 tasks.json 读取 pending 任务 3]
```

---

## 异常处理

| 异常场景 | 处理策略 |
|---------|---------|
| git 冲突 | 停止提交，列出冲突文件，请用户手动解决 |
| push 拒绝 | 自动 `git pull --rebase` 后重试，失败则求助 |
| 文档格式异常 | 尝试修复，失败则跳过并警告 |
| tasks.json 不存在 | 警告"未检测到任务清单"，跳过更新 |
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
- 新增测试文件 → 对应测试任务标记 completed
- 新增前端组件 → 对应前端任务标记 completed
- 提交信息含任务 ID → 匹配并标记任务 completed

示例:
test_strategy_optimizer.py 新增
→ 匹配 "T1: Optuna 目标函数单元测试"
→ 标记 ✅ 已完成
```

### 明日优先事项推荐

```python
推荐规则:
1. 优先 P0 级 pending 任务
2. 从 tasks.json 按顺序取 TOP 3
3. 显示任务名称 + 当前状态
```

---

## v3.0 适配要点

| 变更点 | 旧行为 | 新行为 |
|--------|--------|--------|
| 任务状态来源 | 人工推断 | tasks.json 机器可读 ✅ |
| 看板更新 | 无 | board.md 实时更新 ✅ |
| 交接文档 | 固定格式 | 包含任务状态变更表 ✅ |
| 规划文件 | 单一文件 | planning-with-files 三件套 ✅ |

---

## 输出示例

```
🐶 收工完成 - 2026-04-03

📝 变更统计:
   M docs/planning/progress.md
   M docs/planning/findings.md
   U docs/planning/tasks.json
   U docs/planning/board.md
   A docs/planning/2026-04-03-handoff.md
   M src/domain/strategy_optimizer.py
   M web-front/src/pages/Strategy.tsx

💾 Git 提交：91085ca feat(phase8): 集成 Optuna 自动化调参框架

📤 已推送到远程仓库

---
🎉 辛苦了！明天继续。

📌 明日优先事项:
   - [P0] T3: 单元测试编写 (pending)
   - [P0] T4: 集成测试验证 (pending)
   - [P1] F2: UI 组件优化 (pending)
```

---

*版本：v3.0 | 最后更新：2026-04-03*
