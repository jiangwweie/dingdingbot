# 开工技能 - v7.5 智能分层加载版

**触发词**: 开工、开始工作、开始、kaigong

**版本**: v7.5 (智能分层加载 - 总计 9K)

**核心改进** ⭐⭐⭐:
- ✅ 启动极快（3.5K）- 红线规则 + Git + 待办标题 + 决策摘要
- ✅ 用户选择后完整信息（5.5K）- 背景 + 决策 + 方案 + 依赖
- ✅ 总计控制在 10K 内（实际 9K）
- ✅ 核心约束必须加载（红线规则）
- ✅事项背景和技术决策必须加载
- ✅ 交互式引导（用户自主选择待办）

---

## 执行流程（3 阶段智能分层）

### 阶段 1: 极快启动（3.5K）⚡⚡⚡

```python
def startup_fast():
    """极快启动（约 3.5K）"""

    # 1. 读取红线规则（完整版，约 2K）⭐⭐⭐ 核心约束必须
    red_lines = extract_section("CLAUDE.md", "## 🔴 3 条红线")

    # 2. Git 状态检查（约 0.2K）
    branch = git_branch()
    commits = git_log_oneline(3)
    status = git_status_short()

    # 3. 接手交接文档（约 0.3K）⭐
    handoff = find_latest_handoff()
    if handoff:
        # 检查是否已接手
        received_marker = handoff.parent / f".{handoff.name}.received"
        if not received_marker.exists():
            # 读取交接文档的"下一步优先级"章节（仅提取标题）
            todos = extract_todos_titles(handoff)
            # 标记为已接手
            received_marker.touch()
        else:
            print(f"📌 最新交接文档已接手：{handoff.name}")
            todos = extract_todos_titles(handoff)
    else:
        # 无交接文档，从 Git 推断待办
        todos = infer_todos_from_git(commits)

    # 4. 技术决策摘要（约 1K）⭐
    if handoff:
        decisions_summary = extract_decisions_summary(handoff)

    # 总计：2K + 0.2K + 0.3K + 1K = 3.5K
```

**提取待办标题（极简版）**:
```python
def extract_todos_titles(handoff_path: Path) -> list:
    """从交接文档提取待办标题（仅标题 + 依赖）"""

    with open(handoff_path) as f:
        content = f.read()

    # 提取"下一步优先级"章节
    priority_section = extract_section(content, "## 📋 下一步优先级")

    # 解析待办事项（仅提取标题）
    todos = []
    for line in priority_section.split("\n"):
        if line.strip().startswith(("1.", "2.", "3.")):
            # 示例：1. **TEST-2 集成测试 fixture 重构**（预计 3h）
            title = extract_title(line)  # "TEST-2 集成测试 fixture 重构"
            hours = extract_hours(line)  # "3h"
            priority = extract_priority(line)  # "P1"

            # 提取依赖关系（如有）
            blocking = extract_blocking_reason(content, title)

            todos.append({
                "title": title,
                "hours": hours,
                "priority": priority,
                "blocking": blocking,
            })

    return todos
```

**提取技术决策摘要**:
```python
def extract_decisions_summary(handoff_path: Path) -> list:
    """从交接文档提取技术决策摘要（仅标题 + 理由）"""

    with open(handoff_path) as f:
        content = f.read()

    # 提取"技术决策记录"章节
    decisions_section = extract_section(content, "## 💡 技术决策记录")

    # 解析决策（仅提取标题 + 理由）
    decisions = []
    for decision in parse_decisions(decisions_section):
        # 仅保留标题和理由（不展开详细内容）
        summary = {
            "title": decision["title"],
            "reason": decision["reason"][:100]  # 理由摘要（100字）
        }
        decisions.append(summary)

    return decisions[:3]  # 最多 3 个决策摘要
```

**输出示例**:
```
🐶 开工 - 极快启动（v7.5 智能分层加载）

📍 当前分支：dev
📝 最近提交：f8fc137 docs: session handoff 20260403-005
⚠️ 未提交变更：无

---

📌 核心约束（已加载）⭐⭐⭐:

🔴 3 条红线 (违反=P0 问题):
1. 【强制】新需求必须先 brainstorming → Architect 设计 +2 个方案 → 用户确认
2. 【强制】任务分解必须识别并行簇和依赖关系
3. 【强制】测试前必须用户确认 (耗时 30-60 分钟)

---

📌 今日待办（共 3 个）:

  [1] TEST-2: 集成测试 fixture 重构（预计 3h） - [P1]
      ⚠️ 阻塞: 集成测试无法运行

  [2] DEBT-1: 创建 order_audit_logs 表（预计 1.5h） - [P0]
      ⚠️ 阻塞: 审计日志无法持久化

  [3] DEBT-2: 集成交易所 API（预计 2h） - [P0]
      ⚠️ 依赖: DEBT-1 | 阻塞: 实盘功能不完整

---

💡 最近技术决策（摘要）:
  - 两阶段修复 asyncio.Lock（理由：避免死锁）
  - API 依赖注入（理由：改动最小 + 支持测试）
  - 配置 Profile 管理（理由：SQLite 支持事务）

---

📊 上下文统计：
  - 红线规则：2K（核心约束）⭐⭐⭐
  - Git 状态：0.2K
  - 待办清单：0.3K（仅标题）
  - 技术摘要：1K（仅标题+理由）
  - **总计：3.5K** ✅（比 v4.0 减少 85%）

---

💡 请选择要处理的待办事项（输入序号），
   或输入 [D] 查看详细清单，
   或输入 [H] 查看历史交接文档。

选择后将加载：事项背景 + 技术决策详情 + 解决方案 + 依赖关系
```

---

### 阶段 2: 用户选择（交互式）

用户输入序号后，系统响应：

```python
def user_select_todo(todo_id: int):
    """用户选择待办事项后，按需加载详细信息"""

    selected_todo = todos[todo_id - 1]

    print(f"""
✅ 已选择：{selected_todo['title']}

---

正在加载完整信息...
""")

    # 阶段 3: 按需加载详细信息（约 5.5K）
    load_full_info(selected_todo)
```

---

### 阶段 3: 按需加载完整信息（5.5K）⭐⭐⭐

```python
def load_full_info(todo: dict):
    """根据用户选择，按需加载完整信息（约 5.5K）"""

    # 1. 事项背景（约 1K）⭐⭐⭐ 必须要
    background = extract_task_background(todo['title'])

    # 2. 技术决策详情（约 2K）⭐⭐⭐ 必须要
    decisions_detail = extract_decisions_detail(todo['title'])

    # 3. 解决方案（约 2K）
    solution = extract_solution(todo['title'])

    # 4. 依赖关系详情（约 0.5K）
    dependencies = extract_full_dependencies(todo['title'])

    # 总计：1K + 2K + 2K + 0.5K = 5.5K
```

**提取事项背景**:
```python
def extract_task_background(todo_title: str) -> str:
    """从交接文档提取事项背景（约 1K）"""

    handoff = find_latest_handoff()
    with open(handoff) as f:
        content = f.read()

    # 提取任务由来
    # 1. 从"技术决策记录"中提取背景
    decisions_section = extract_section(content, "## 💡 技术决策记录")

    # 匹配相关决策的"背景"字段
    background_parts = []

    for decision in parse_decisions(decisions_section):
        if is_related(todo_title, decision["title"]):
            background_parts.append(f"**{decision['title']}**: {decision['background']}")

    # 2. 从"问题分析"中提取背景
    problems_section = extract_section(content, "## 🔍 问题分析")
    if problems_section:
        background_parts.append(f"**问题背景**: {extract_problems_background(problems_section)}")

    # 3. 从 Git 提交历史提取背景（如有）
    git_background = infer_background_from_git(todo_title)
    if git_background:
        background_parts.append(f"**Git历史**: {git_background}")

    return "\n\n".join(background_parts[:3])  # 最多 3 个背景
```

**提取技术决策详情**:
```python
def extract_decisions_detail(todo_title: str) -> str:
    """从交接文档提取相关技术决策详情（约 2K）"""

    handoff = find_latest_handoff()
    with open(handoff) as f:
        content = f.read()

    # 提取"技术决策记录"章节
    decisions_section = extract_section(content, "## 💡 技术决策记录")

    # 匹配相关决策（多级匹配）
    keywords = extract_keywords(todo_title)
    matched_decisions = []

    for decision in parse_decisions(decisions_section):
        # 任务 ID 匹配（最精准）
        if extract_task_id(todo_title) in decision["title"]:
            matched_decisions.append(decision)
            continue

        # 关键词匹配（中等精准）
        if any(keyword in decision["title"].lower() for keyword in keywords):
            matched_decisions.append(decision)

    # 格式化决策详情（完整版）
    formatted = []
    for decision in matched_decisions[:2]:  # 最多 2 个决策
        formatted.append(f"""
### 决策: {decision['title']}

**背景**: {decision['background']}

**选择方案**: {decision['selected']}

**拒绝方案**: {decision['rejected']}

**理由**: {decision['reason']}

**影响**: {decision['impact']}
""")

    return "\n\n".join(formatted)
```

**提取解决方案**:
```python
def extract_solution(todo_title: str) -> str:
    """从交接文档或 findings.md 提取解决方案（约 2K）"""

    # 1. 从交接文档的"技术决策"中提取方案
    handoff = find_latest_handoff()
    with open(handoff) as f:
        content = f.read()

    decisions_section = extract_section(content, "## 💡 技术决策记录")
    solution_parts = []

    for decision in parse_decisions(decisions_section):
        if is_related(todo_title, decision["title"]):
            # 提取"选择方案"详细内容
            solution_parts.append(f"""
**方案**: {decision['selected']}

**关键要点**:
- {extract_key_points(decision['selected'])}
""")

    # 2. 从 findings.md 提取技术方案（如有）
    findings_path = Path("docs/planning/findings.md")
    if findings_path.exists():
        findings = extract_related_findings(todo_title, findings_path)
        if findings:
            solution_parts.append(f"**技术方案参考**: {findings}")

    return "\n\n".join(solution_parts)
```

**提取依赖关系详情**:
```python
def extract_full_dependencies(todo_title: str) -> str:
    """提取完整依赖链（约 0.5K）"""

    handoff = find_latest_handoff()
    with open(handoff) as f:
        content = f.read()

    # 提取"阻塞项与依赖"章节
    blocking_section = extract_section(content, "## 🚨 阻塞项与依赖")

    # 解析依赖关系
    dependencies = []

    # 查找任务的直接依赖
    direct_deps = extract_direct_dependencies(blocking_section, todo_title)

    # 递归查找间接依赖
    for dep in direct_deps:
        indirect_deps = extract_indirect_dependencies(blocking_section, dep)
        dependencies.extend(indirect_deps)

    # 格式化依赖链
    if dependencies:
        return f"""
**直接依赖**: {", ".join(direct_deps) or "无"}

**间接依赖**: {", ".join(dependencies) or "无"}

**阻塞项**: {extract_blocking_reason(blocking_section, todo_title)}
"""
    else:
        return "**依赖关系**: 无依赖"
```

**输出示例（用户选择 TEST-2）**:
```
✅ 已选择：TEST-2 集成测试 fixture 重构

---

正在加载完整信息...

---

## 📋 事项背景（1K）⭐

**任务由来**:
- DEBT-3 API 依赖注入实施后，测试 fixture 需要适配
- DEBT-5/DEBT-6 asyncio.Lock 修复后，Repository 初始化逻辑变化

**问题背景**:
- 事件循环冲突（同步 TestClient 和异步 order_repository 不兼容）
- fixture 初始化时序问题（Repository 未调用 initialize()）

**Git 历史**:
- DEBT-3: API 依赖注入方案（d7240f8）
- DEBT-5: asyncio.Lock 修复（31a4ed1）

---

## 💡 技术决策详情（2K）⭐

### 决策 1: API 依赖注入方案（DEBT-3）

**背景**: 测试 fixture 无法注入临时数据库到 OrderRepository

**选择方案**: 添加 `_get_order_repo()` 辅助函数 + `set_dependencies()` 扩展

**拒绝方案**:
- 方案 B（修改所有 API 端点参数）- 改动量大
- 方案 C（全局变量直接访问）- 不利于测试

**理由**: 方案 A 改动最小（0.5h），兼容现有测试，支持未来扩展

**影响**: 5 个订单管理 API 端点支持依赖注入

---

### 决策 2: asyncio.Lock 延迟创建（DEBT-5/DEBT-6）

**背景**: uvicorn --reload 热重载创建新事件循环，旧 lock 无法使用

**选择方案**: `_ensure_lock()` 延迟创建 + 幂等性 `initialize()`

**拒绝方案**: 在 `__init__` 中立即创建 lock（会绑定到旧事件循环）

**理由**: 延迟创建确保 lock 绑定到当前事件循环

**影响**: 所有 Repository 统一使用延迟创建模式

---

## 🔍 解决方案（2K）

**方案**: 使用 httpx.AsyncClient + pytest-asyncio

**代码示例**:
```python
@pytest.fixture
async def async_client():
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        yield client

@pytest.fixture
async def order_repo(test_db):
    repo = OrderRepository(test_db)
    await repo.initialize()  # ⚠️ 必须调用 initialize()
    yield repo
    await repo.close()
```

**关键要点**:
- 使用 AsyncClient（异步）而非 TestClient（同步）
- 必须调用 `repo.initialize()`（Repository 幂等性初始化）
- 使用 `async with` 确保资源清理

---

## 🔗 依赖关系详情（0.5K）

**直接依赖**: 无

**间接依赖**: 无

**阻塞项**: 集成测试无法运行，影响 API 完整流程验证

---

📊 本次加载上下文：约 5.5K

---

准备好开始了吗？
建议先理解技术决策背景，再开始实施。
```

---

## 其他交互选项

### 选项 D: 查看详细清单

```python
def show_detailed_list():
    """显示详细待办清单（约 1K）"""

    print(f"""
📌 今日待办事项（详细版）:

  [1] TEST-2: 集成测试 fixture 重构
      - 优先级: P1
      - 预计工时: 3h
      - 阻塞说明: 集成测试无法运行，无法验证 API 完整流程
      - 依赖: 无

  [2] DEBT-1: 创建 order_audit_logs 表
      - 优先级: P0
      - 预计工时: 1.5h
      - 阻塞说明: 批量删除订单审计日志无法持久化
      - 依赖: 无

  [3] DEBT-2: 集成交易所 API
      - 优先级: P0
      - 预计工时: 2h
      - 阻塞说明: 实盘功能不完整
      - 依赖: DEBT-1

---

📊 本次加载上下文：约 1K

---

请选择要处理的待办事项（输入序号）。
""")
```

### 选项 H: 查看历史交接文档

```python
def show_history_handoffs():
    """显示历史交接文档列表"""

    handoffs = sorted(Path("docs/planning").glob("*-handoff.md"), reverse=True)

    print(f"""
📜 历史交接文档（最近 7 天）:

  [1] 20260403-005-handoff.md - 全天工作总结（合并模式）
  [2] 20260403-002-handoff.md - DEBT-4 方法重名冲突修复
  [3] 20260402-001-handoff.md - DEBT-3 API 依赖注入实现

请选择要查看的交接文档（输入序号），
或输入 [A] 查看归档文档（超过 7 天）。
""")
```

---

## 异常处理

| 异常场景 | 处理策略 |
|---------|---------|
| 无交接文档 | 从 Git 最近提交推断待办，提示"首次开工，建议先查看项目目标" |
| 交接文档已接手 | 提示"最新交接文档已接手"，询问是否重新读取 |
| 交接文档无"下一步优先级" | 从 Git 提交推断当前任务（如 DEBT-6 → TEST-2） |
| Git 提交无任务信息 | 提示"无法推断当前任务，建议手动指定或查看 CLAUDE.md" |
| 无相关技术决策 | 显示"暂无相关技术决策记录" |
| 无事项背景 | 从 Git 提交历史推断背景 |
| 首次开工（新项目） | 读取 CLAUDE.md 项目目标章节（约 1K） |

---

## 首次开工特殊处理

```python
def startup_first_time():
    """首次开工：读取项目目标"""

    print("📌 首次开工检测")

    # 读取 CLAUDE.md 项目目标
    project_goal = extract_section("CLAUDE.md", "## 项目使命")

    print(f"""
📌 项目目标：

{project_goal}

---

💡 建议首先阅读：
- CLAUDE.md（项目指南）
- docs/v3/v3-evolution-roadmap.md（演进路线图）
- docs/arch/系统开发规范与红线.md（架构规范）

---

准备好后，请告诉我你要做什么。
""")
```

---

## 上下文占用统计（完整流程）

| 场景 | 启动加载 | 按需加载 | 总计 | 对比 v4.0 |
|------|---------|---------|------|---------|
| **首次开工** | 3.5K | 用户选择后 5.5K | **9K** | 减少 62% ✅ |
| **切换待办** | 无需重新启动 | 加载新任务 5.5K | **9K** | 灵活加载 ✅ |
| **查看详细清单** | 3.5K | 选项 D 1K | **4.5K** | 极快 ✅ |
| **查看历史交接** | 3.5K | 选项 H 0.5K | **4K** | 极快 ✅ |

---

## v7.5 核心优势

1. ✅ **启动极快**（3.5K）- 比 v4.0 减少 85%
2. ✅ **核心约束必须加载**（红线规则 2K）- 架构安全、流程合规
3. ✅ **事项背景必须加载**（1K）- 理解任务由来
4. ✅ **技术决策必须加载**（2K）- 完整版决策详情
5. ✅ **用户自主选择**（交互式引导）- 不强迫加载无关信息
6. ✅ **总计控制在 10K内**（实际 9K）- 完全符合要求

---

## 版本对比

| 版本 | 启动 | 按需加载 | 总计 | 核心约束 | 事项背景 | 技术决策 | 推荐度 |
|------|------|---------|------|---------|---------|---------|--------|
| v4.0 | 24K | 无 | 24K | ✅ | ❌ | ⚠️ 摘要 | ⭐⭐⭐ |
| v6.0 极简 | 0.4K | 按需 | 未知 | ❌ ⚠️ | ❌ | ❌ | ⭐⭐ |
| **v7.5** | **3.5K** | **5.5K** | **9K** | **✅** | **✅** | **✅** | **⭐⭐⭐⭐⭐** |

---

*版本：v7.5 智能分层加载版 | 最后更新：2026-04-03*