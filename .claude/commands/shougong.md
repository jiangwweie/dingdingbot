# 收工技能 - 全套收工 (v4.0 智能精简版)

**触发词**: 收工、结束工作、结束、下班、shougong

**版本**: v4.0 (智能精简 - 减少 92% 上下文占用)

**核心原则**: 全自动执行，无需用户确认，仅在异常时介入

**v4.0 核心改进** ⭐:
- ✅ 自动归档交接文档（超过 7 天）
- ✅ 自动归档进度日志（超过 3 天）
- ✅ 智能更新技术发现（仅追加相关发现）
- ✅ 智能更新任务计划（仅更新当前阶段）
- ✅ 上下文占用从 267K → 20K（减少 92%）

---

## 执行流程 (全自动)

### 阶段 0: 自动归档旧交接文档 ⭐ (v3.1 新增)

```python
from datetime import datetime, timedelta
from pathlib import Path
import shutil

# 1. 创建归档目录
archive_dir = Path("docs/planning/archive")
archive_dir.mkdir(exist_ok=True)

# 2. 找出超过 7 天的交接文档
cutoff_date = datetime.now() - timedelta(days=7)
old_handoffs = [
    f for f in Path("docs/planning").glob("*-handoff.md")
    if datetime.fromtimestamp(f.stat().st_mtime) < cutoff_date
]

# 3. 移动到归档目录
archived_count = 0
for handoff in old_handoffs:
    shutil.move(str(handoff), str(archive_dir / handoff.name))
    archived_count += 1

# 4. 创建归档说明
if archived_count > 0:
    readme = archive_dir / "README.md"
    readme.write_text(f"""# 归档交接文档

归档时间: {datetime.now().strftime('%Y-%m-%d')}
归档数量: {archived_count}

说明：这些交接文档已超过 7 天，已归档以减少上下文占用。
如需查看，请直接打开对应文件。
""")
```

**输出**:
```
📦 归档交接文档：
  - 2026-03-25-001-handoff.md (已归档)
  - 2026-03-26-001-handoff.md (已归档)
  归档数量: 2
```

---

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

### 阶段 2: 智能文档更新 ⭐

#### 2.1 更新 progress.md（智能追加）

**智能追加策略**：仅追加今日日志到顶部，不读取历史日志（114K）

```python
def append_today_progress():
    """智能追加今日日志（仅写入，不读取历史）"""

    # 1. 从 Git 提交推断今日工作
    today_work = infer_from_git_log()

    # 2. 生成今日日志
    today_log = f"""
### {datetime.now().strftime('%Y-%m-%d %H:%M')} - {today_work.title} ✅

**开始时间**: {session_start}
**会话阶段**: {session_stage}
**参与者**: {participants}

#### 完成工作
{today_work.details}

#### Git 提交
{git_commits}
"""

    # 3. 读取 progress.md 的前 50 行（今日待办 + 最近 3 天）
    with open("docs/planning/progress.md") as f:
        header = [f.readline() for _ in range(50)]

    # 4. 插入今日日志到顶部
    updated = header[:10] + [today_log] + header[10:]

    # 5. 写回文件（不读取整个文件）
    with open("docs/planning/progress.md", "w") as f:
        f.writelines(updated)
```

**效果**：不读取 progress.md 的历史日志（114K），仅写入今日日志

---

#### 2.2 更新 findings.md（智能匹配追加）

**智能追加策略**：仅追加相关技术发现，不读取整个 findings.md

```python
def append_relevant_findings(today_decisions: list):
    """智能追加相关技术发现（不读取整个文件）"""

    # 1. 从今日决策提取标签
    tags = []
    for decision in today_decisions:
        tags.extend(extract_tags(decision))

    # 2. 读取 findings.md 的目录（前 30 行）
    with open("docs/planning/findings.md") as f:
        toc = [f.readline() for _ in range(30)]

    # 3. 查找匹配的章节
    matched_sections = find_sections_by_tags(toc, tags)

    # 4. 追加今日发现到匹配章节（或新建章节）
    for decision in today_decisions:
        section = find_or_create_section(decision.tags)
        append_to_section(section, decision)

    # 5. 更新目录（仅修改目录部分）
    update_toc(toc, today_decisions)
```

**效果**：不读取 findings.md 的全部内容（72K），仅读取目录和匹配章节

---

#### 2.3 更新 task_plan.md（仅更新当前阶段）

**智能更新策略**：仅更新"当前阶段任务"章节，不读取已完成任务

```python
def update_current_tasks(completed_tasks: list):
    """仅更新当前阶段任务状态"""

    # 1. 读取 task_plan.md 的"当前阶段"章节
    with open("docs/planning/task_plan.md") as f:
        content = f.read()

    current_section = extract_section(content, "## 🔥 P0 级 - 当前阶段任务")

    # 2. 更新任务状态
    for task in completed_tasks:
        # 查找任务行
        # 更新状态：☐ 待启动 → ✅ 已完成
        current_section = update_task_status(current_section, task)

    # 3. 写回文件（仅修改当前章节）
    updated_content = replace_section(
        content,
        "## 🔥 P0 级 - 当前阶段任务",
        current_section
    )

    with open("docs/planning/task_plan.md", "w") as f:
        f.write(updated_content)
```

**效果**：不读取 task_plan.md 的已完成任务（36K），仅更新当前阶段

---

#### 2.4 更新 tasks.json（必须）

根据 git 提交和变更文件推断任务完成状态：

```python
import json

# 读取当前 tasks.json
with open("docs/planning/tasks.json") as f:
    tasks = json.load(f)

# 推断规则:
# 1. 新增测试文件 → 对应测试任务 completed
# 2. 新增前端组件 → 对应前端任务 completed
# 3. 提交信息包含任务 ID → 标记对应任务 completed

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

---

#### 2.5 更新 board.md（必须）

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

📦 归档交接文档：
  - {{archived_files}} (已归档)
  归档数量: {{count}}

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

### 阶段 6: 自动归档进度日志 ⭐ (v4.0 新增)

```python
from datetime import datetime, timedelta
from pathlib import Path

def archive_old_progress_logs(days: int = 3):
    """归档超过 N 天的进度日志"""

    planning_dir = Path("docs/planning")
    archive_dir = planning_dir / "archive"
    archive_dir.mkdir(exist_ok=True)

    # 1. 读取 progress.md
    with open(planning_dir / "progress.md") as f:
        lines = f.readlines()

    # 2. 提取最近 3 天日志
    recent_logs = []
    old_logs = []
    cutoff_date = datetime.now() - timedelta(days=days)

    in_recent = False
    for line in lines:
        if line.startswith("### ") and " - " in line:
            # 解析日期：### 2026-04-03 21:30 - DEBT-4 ...
            date_str = line.split(" - ")[0].replace("### ", "").strip()
            log_date = datetime.strptime(date_str.split()[0], "%Y-%m-%d")

            in_recent = log_date >= cutoff_date

        if in_recent:
            recent_logs.append(line)
        else:
            old_logs.append(line)

    # 3. 写回 progress.md（仅保留最近 3 天）
    with open(planning_dir / "progress.md", "w") as f:
        f.write("# 进度日志\n\n")
        f.write("> **说明**: 本文件仅保留最近 3 天的详细进度日志，历史日志已归档。\n\n")
        f.write("---\n\n")
        f.write("## 📍 最近 3 天（详细日志）\n\n")
        f.writelines(recent_logs)
        f.write("\n---\n\n")
        f.write("## 📦 归档日志（摘要）\n\n")
        f.write(f"- 历史日志已归档到 archive/progress-archive.md（{len(old_logs)} 行）\n")

    # 4. 追加旧日志到归档文件
    if old_logs:
        archive_path = archive_dir / "progress-archive.md"
        with open(archive_path, "a") as f:
            f.write(f"\n\n---\n\n## 归档时间: {datetime.now()}\n\n")
            f.writelines(old_logs)

    print(f"📦 归档进度日志：{len(old_logs)} 行已归档")
```

**输出**:
```
📦 归档进度日志：
  - 2026-03-25 至 2026-04-01 日志已归档
  归档数量: 850 行
  progress.md 大小：119K → 30K（减少 89K）
```

**效果**：
- progress.md 大小：119K → **30K**（减少 89K）⭐⭐⭐
- AI 下次开工不读取归档日志（减少上下文占用）

---

### 阶段 7: 清理已接手标记文件 ⭐ (v4.0 新增)

```python
from datetime import datetime, timedelta
from pathlib import Path

def cleanup_old_received_markers(days: int = 7):
    """清理超过 N 天的已接手标记文件"""

    planning_dir = Path("docs/planning")
    cutoff_date = datetime.now() - timedelta(days=days)

    # 找出所有 .received 标记文件
    received_markers = list(planning_dir.glob(".*.received"))

    old_markers = [
        f for f in received_markers
        if datetime.fromtimestamp(f.stat().st_mtime) < cutoff_date
    ]

    # 删除旧的标记文件
    for marker in old_markers:
        marker.unlink()

    if old_markers:
        print(f"🧹 已清理 {len(old_markers)} 个旧的已接手标记文件")
```

**输出**:
```
🧹 已清理 3 个旧的已接手标记文件
```

**效果**：
- 防止标记文件累积
- 保留最近 7 天的接手记录（可追溯）
- 自动清理旧的标记文件

---

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
