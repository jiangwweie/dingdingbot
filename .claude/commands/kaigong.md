# 开工技能 - 全套准备 (v4.0 智能精简版)

**触发词**: 开工、开始工作、开始、kaigong

**版本**: v4.0 (智能精简 - 减少 92% 上下文占用)

**核心改进** ⭐:
- ✅ progress.md 分段读取（仅读取最近 3 天，减少 89K）
- ✅ findings.md 智能匹配（仅读取相关发现，减少 72K）
- ✅ task_plan.md 精简读取（仅读取当前阶段，减少 36K）
- ✅ 上下文占用从 252K → 20K（减少 92%）

---

## 执行流程（4 阶段智能精简）

### 阶段 1: 核心文档读取（5K）

```bash
# 1. 同步 git 状态
git pull origin $(git branch --show-current) 2>/dev/null || echo "无需拉取或已是最新"
git branch --show-current
git log --oneline -3

# 2. 检查未提交变更
git status --short
```

**读取核心文档**：
- `docs/planning/tasks.json` (1.6K) - 任务清单（机器可读）
- `docs/planning/board.md` (1.8K) - 状态看板
- `docs/planning/*-handoff.md` (2K) - 最新交接文档

**总大小**: 约 5.4K

---

### 阶段 2: 智能提取今日待办（5K）⭐

```python
# 仅读取 progress.md 的"今日待办"章节
def extract_today_todos():
    """从 progress.md 提取今日待办（约 5K）"""

    with open("docs/planning/progress.md") as f:
        content = f.read()

    # 提取"今日待办"章节（快速访问）
    if "## 📌 今日待办" in content:
        todos = extract_section(content, "## 📌 今日待办")
        return todos  # 约 5K

    # 回退：提取最近 1 天日志
    recent = extract_recent_logs(days=1)
    return recent  # 约 10K
```

**不读取**：progress.md 的历史日志（114K）

---

### 阶段 3: 智能匹配相关发现（10K）⭐

```python
# 根据当前任务智能匹配 findings.md
def match_relevant_findings(current_tasks: list) -> str:
    """从 findings.md 匹配相关技术发现（约 10K）"""

    # 提取任务标签
    tags = []
    for task in current_tasks:
        tags.extend(extract_tags(task))  # ["asyncio", "api", "test"]

    # 按标签匹配 findings.md 章节
    with open("docs/planning/findings.md") as f:
        findings = parse_findings(f.read())

    relevant = []
    for section in findings.sections:
        if any(tag in section.tags for tag in tags):
            relevant.append(section.content)

    return "\n\n".join(relevant)  # 约 10K
```

**不读取**：findings.md 的不相关章节（72K）

---

### 阶段 4: 读取当前阶段任务（5K）⭐

```python
# 仅读取 task_plan.md 的"当前阶段"章节
def extract_current_tasks():
    """从 task_plan.md 提取当前阶段任务（约 5K）"""

    with open("docs/planning/task_plan.md") as f:
        content = f.read()

    # 提取"当前阶段任务"章节
    if "## 🔥 P0 级 - 当前阶段任务" in content:
        current = extract_section(content, "## 🔥 P0 级 - 当前阶段任务")
        return current  # 约 5K

    # 回退：读取"待办事项总览"
    overview = extract_section(content, "## 📊 待办事项总览")
    return overview  # 约 10K
```

**不读取**：task_plan.md 的已完成任务（36K）

---

## 输出格式（智能精简版）

```
🐶 开工 - 准备就绪（智能精简模式）

📍 当前分支：dev
📝 最近提交：abc1234 上次提交信息

⚠️ 未提交变更：无 / 有（列表）

---

📌 上次会话交接（2K）:
### 技术决策
- [决策摘要]

### 问题分析
- [P0 问题列表]

---

📋 任务清单（1.6K）:
功能：[功能名称]
当前阶段：[planning/development/testing]

| ID | 任务 | 角色 | 状态 | 依赖 |
|----|------|------|------|------|
| T1 | xxx | backend | ☐ 待开始 | 无 |
| T2 | xxx | frontend | 🔄 进行中 | T1 |

---

📌 今日待办（5K）:
### 待启动任务
- [ ] DEBT-1: 创建 order_audit_logs 表 (1.5h)
- [ ] DEBT-2: 集成交易所 API (2h)

### 进行中任务
- [ ] TEST-2: 集成测试 fixture 重构 (进度 60%)

---

💡 相关技术发现（10K）:
### asyncio 并发
- DEBT-4: Python 方法重名覆盖机制
- DEBT-5: asyncio.Lock 事件循环冲突

### API 依赖注入
- DEBT-3: API 依赖注入方案实现

---

📊 状态看板：board.md 已更新

🎯 今日建议：[从任务清单提取优先级最高的 3 个待办]

---

**上下文统计**:
- 核心文档：5.4K
- 今日待办：5K
- 相关发现：10K
- **总计：20.4K** ✅（减少 92%）

---

准备好开始了吗？请告诉我今日目标或下一个任务。
```

---

## v4.0 智能精简对比

| 项目 | v3.0 全量读取 | v4.0 智能精简 | 减少 |
|------|-------------|-------------|------|
| 核心文档 | tasks.json + handoff (3.6K) | 同左 (3.6K) | 0K |
| 进度日志 | progress.md **(119K)** | 今日待办 **(5K)** | **114K** ⭐⭐⭐ |
| 技术发现 | findings.md **(82K)** | 相关发现 **(10K)** | **72K** ⭐⭐⭐ |
| 任务计划 | task_plan.md **(51K)** | 当前阶段 **(5K)** | **46K** ⭐⭐⭐ |
| Git 检查 | 5K | 5K | 0K |
| **总计** | **252K** ⚠️⚠️⚠️ | **20K** ✅ | **232K (92%)** ⭐⭐⭐⭐⭐ |

**核心改进**：
- AI 不再读取历史日志（仅读取今日待办）
- AI 不再读取不相关发现（智能匹配标签）
- AI 不再读取已完成任务（仅读取当前阶段）

---

## 异常处理

| 异常场景 | 处理策略 |
|---------|---------|
| tasks.json 不存在 | 提示"未检测到任务清单，建议先运行规划会话" |
| handoff 文档不存在 | 跳过，提示"首次会话，无交接文档" |
| progress.md 无"今日待办"章节 | 回退：读取最近 1 天日志 |
| findings.md 无标签匹配 | 回退：读取"按主题分类"目录 |
| task_plan.md 无"当前阶段"章节 | 回退：读取"待办事项总览" |
| board.md 不存在 | 从模板创建 |
| git 拉取失败 | 继续执行，但警告用户 |

---

## 智能提取实现细节

### 提取今日待办

```python
def extract_section(content: str, section_title: str) -> str:
    """从 Markdown 文档提取指定章节"""

    lines = content.split("\n")
    in_section = False
    section_lines = []

    for line in lines:
        if line.startswith(section_title):
            in_section = True
            continue
        if in_section and line.startswith("## "):
            # 遇到下一个二级标题，结束
            break
        if in_section:
            section_lines.append(line)

    return "\n".join(section_lines)
```

### 智能匹配标签

```python
def extract_tags(task: dict) -> list:
    """从任务描述提取标签"""

    tags = []

    # 任务 ID 标签
    if "DEBT" in task.get("id", ""):
        tags.append("asyncio")
        tags.append("api")
    if "TEST" in task.get("id", ""):
        tags.append("test")

    # 任务描述关键词
    description = task.get("subject", "").lower()
    if "asyncio" in description or "lock" in description:
        tags.append("asyncio")
    if "api" in description or "endpoint" in description:
        tags.append("api")
    if "test" in description or "fixture" in description:
        tags.append("test")

    return tags
```

### 读取当前阶段任务

```python
def extract_current_stage_tasks() -> str:
    """从 task_plan.md 提取当前阶段任务"""

    with open("docs/planning/task_plan.md") as f:
        content = f.read()

    # 优先读取"当前阶段"章节
    current_section = extract_section(content, "## 🔥 P0 级 - 当前阶段任务")

    if current_section:
        return current_section

    # 回退：读取"待办事项总览"
    overview = extract_section(content, "## 📊 待办事项总览")
    return overview
```

---

*版本：v4.0 智能精简版 | 最后更新：2026-04-03*
