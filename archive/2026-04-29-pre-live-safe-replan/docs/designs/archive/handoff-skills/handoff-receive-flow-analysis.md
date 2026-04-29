---
title: "交接与接手流程设计分析"
date: 2026-04-03
type: design-analysis
---

## 🔍 现状分析

### 当前设计

**交接流程**（`/handoff`）：
1. 用户调用 `/handoff`
2. AI 生成交接文档：`docs/planning/<YYYYMMDD>-<序号>-handoff.md`
3. Git 提交（不推送）

**接手流程**（`/kaigong`）：
1. 用户调用 `/kaigong`
2. AI 读取 `docs/planning/*-handoff.md`（最新交接文档）
3. 继续执行开工流程

---

## ⚠️ 发现的问题

### 问题 1: 如何确定"最新"交接文档？

**现状**：
- 开工时读取 `docs/planning/*-handoff.md`（通配符）
- 可能匹配多个交接文档（如 `20260403-001-handoff.md`、`20260403-002-handoff.md`）

**问题**：
- 哪个是"最新"的？
- 如何排序？（按文件名？按修改时间？）

**示例场景**：
```
docs/planning/
├── 20260403-001-handoff.md  (早上 9:00 生成的交接)
├── 20260403-002-handoff.md  (下午 14:00 生成的交接) ← 最新
└── 20260402-001-handoff.md  (昨天的交接)
```

**AI 应该读取哪个？**
- 按文件名排序：`20260403-002-handoff.md`（序号最大）
- 按修改时间：`20260403-002-handoff.md`（最新修改）

**结论**：两种方式结果相同，但需要明确规则。

---

### 问题 2: 是否需要标记"已接手"状态？

**现状**：
- 交接文档生成后，没有标记是否已被接手
- AI 每次开工都会读取最新的交接文档

**问题**：
- 如果用户今天调用了 `/kaigong` 接手了交接文档，明天再调用 `/kaigong`，还会再次读取同一个交接文档吗？
- 是否需要标记交接文档为"已接手"？

**示例场景**：
```
时间线：
1. 2026-04-03 14:00 - 用户调用 /handoff，生成 20260403-002-handoff.md
2. 2026-04-03 15:00 - 用户调用 /kaigong，读取 20260403-002-handoff.md ✅
3. 2026-04-04 09:00 - 用户调用 /kaigong，再次读取 20260403-002-handoff.md ❌（重复）
```

**潜在问题**：
- 用户可能忘记已经接手过交接文档
- AI 可能重复读取同一个交接文档（浪费上下文）

---

### 问题 3: 是否需要正式的"接手"流程？

**现状**：
- `/kaigong` 自动读取交接文档，没有明确的"接手"步骤
- 用户不知道交接文档是否已被接手

**问题**：
- 是否需要让用户明确"接手"操作？
- 是否需要提示用户"有新的交接文档等待接手"？

---

## 💡 设计方案（3 个选项）

### 方案 1: 自动接手（隐式，推荐）

**核心理念**：开工时自动读取最新交接文档，无需用户手动操作。

**改进措施**：

1. **明确"最新"规则**：
   ```python
   def find_latest_handoff() -> Path:
       """查找最新的交接文档"""

       handoffs = list(Path("docs/planning").glob("*-handoff.md"))

       if not handoffs:
           return None

       # 按文件名排序（YYYYMMDD-序号-handoff.md）
       # 文件名已包含时间和序号，排序即可
       latest = sorted(handoffs)[-1]
       return latest
   ```

2. **标记"已接手"状态**：
   ```python
   def mark_handoff_as_received(handoff_path: Path):
       """标记交接文档为已接手"""

       # 方式 1: 修改文件名（添加 .received 后缀）
       new_name = handoff_path.stem + ".received.md"
       handoff_path.rename(handoff_path.parent / new_name)

       # 方式 2: 在文件中添加元数据
       # （但会改变交接文档内容，不推荐）

       # 方式 3: 创建 .received 标记文件
       # （不改变交接文档，推荐）
       (handoff_path.parent / f".{handoff_path.name}.received").touch()
   ```

3. **开工时检查并提示**：
   ```python
   def check_unreceived_handoffs() -> list:
       """检查未接手的交接文档"""

       handoffs = list(Path("docs/planning").glob("*-handoff.md"))
       unreceived = []

       for handoff in handoffs:
           # 检查是否存在 .received 标记文件
           received_marker = handoff.parent / f".{handoff.name}.received"
           if not received_marker.exists():
               unreceived.append(handoff)

       return unreceived
   ```

**开工流程调整**：
```
用户调用 /kaigong
↓
检查未接手的交接文档
↓
找到最新未接手的交接文档
↓
读取交接文档（2K）
↓
标记为已接手（创建 .received 标记文件）
↓
继续开工流程...
```

**优点**：
- 用户无需手动操作（自动接手）
- 明确"最新"规则（按文件名排序）
- 避免重复读取（已接手标记）
- 保持交接文档不变（独立标记文件）

**缺点**：
- 可能产生大量 `.received` 标记文件（需要定期清理）
- 用户可能不知道交接文档已被自动接手

---

### 方案 2: 手动接手（显式）

**核心理念**：用户明确选择要接手的交接文档。

**改进措施**：

1. **开工时列出未接手的交接文档**：
   ```
   用户调用 /kaigong
   ↓
   检查未接手的交接文档
   ↓
   找到 2 个未接手的交接文档：
   - 20260403-001-handoff.md (早上 9:00)
   - 20260403-002-handoff.md (下午 14:00) ← 最新

   是否接手最新的交接文档？
   [Y] 接手最新的
   [N] 接手指定的（输入序号）
   [S] 跳过接手
   ```

2. **用户选择后接手**：
   ```python
   def receive_handoff(handoff_path: Path):
       """用户明确接手交接文档"""

       # 读取交接文档
       with open(handoff_path) as f:
           content = f.read()

       # 显示交接文档内容
       print(content)

       # 标记为已接手
       mark_handoff_as_received(handoff_path)
   ```

**优点**：
- 用户明确知道正在接手哪个交接文档
- 可以选择跳过接手（如果不需要）
- 可以选择接手旧的交接文档（回溯历史）

**缺点**：
- 增加用户操作步骤（手动选择）
- 可能打断开工流程（需要等待用户确认）

---

### 方案 3: 混合模式（自动 + 提示）

**核心理念**：自动读取最新交接文档，但提示用户确认。

**改进措施**：

1. **开工时自动读取最新交接文档**：
   ```python
   def read_latest_handoff():
       """自动读取最新交接文档"""

       latest = find_latest_handoff()

       if not latest:
           print("📌 无交接文档，首次会话")
           return

       # 检查是否已接手
       received_marker = latest.parent / f".{latest.name}.received"
       if received_marker.exists():
           print(f"📌 最新交接文档已接手：{latest.name}")
           return

       # 读取交接文档
       with open(latest) as f:
           content = f.read()

       print(f"📌 发现新的交接文档：{latest.name}")
       print(content)

       # 标记为已接手
       received_marker.touch()
   ```

2. **开工输出包含交接文档内容**：
   ```
   🐶 开工 - 准备就绪

   📌 发现新的交接文档：20260403-002-handoff.md

   ## 💡 技术决策记录
   - 决策 1: asyncio.Lock vs Redis 分布式锁
   ...

   ## 🔍 问题分析
   - P0-1: 参数校验缺失
   ...

   ---

   是否继续开工？
   [Y] 继续（默认）
   [R] 重新读取交接文档
   [S] 跳过交接文档

   ---

   📋 任务清单（1.6K）:
   ...
   ```

**优点**：
- 自动接手（减少用户操作）
- 明确提示（用户知道正在接手什么）
- 可以重新读取或跳过（灵活性）

**缺点**：
- 增加一个确认步骤（但可选择跳过）
- 实现复杂度中等

---

## 📊 方案对比

| 方案 | 用户操作 | 明确性 | 避免重复 | 实现难度 | 推荐指数 |
|------|---------|--------|---------|---------|----------|
| 方案 1: 自动接手 | 无 | 低 | ✅ | 低 | ⭐⭐⭐⭐ |
| 方案 2: 手动接手 | 高 | 高 | ✅ | 中 | ⭐⭐⭐ |
| 方案 3: 混合模式 | 中 | 高 | ✅ | 中 | ⭐⭐⭐⭐⭐ |

---

## 🎯 推荐方案

**推荐方案 3（混合模式）**：

**理由**：
1. **自动 + 提示**：减少用户操作，但明确告知正在接手什么
2. **灵活性**：用户可以重新读取或跳过交接文档
3. **避免重复**：标记已接手状态，防止重复读取
4. **最佳体验**：平衡自动化和用户控制

---

## 🚀 实施细节（方案 3）

### 1. 交接文档命名规范

**强制格式**：`<YYYYMMDD>-<序号>-handoff.md`

**示例**：
- `20260403-001-handoff.md`（当天第一个会话）
- `20260403-002-handoff.md`（当天第二个会话）

**排序规则**：按文件名字典序排序，最后一个为最新

---

### 2. 已接手标记机制

**标记文件**：`.<交接文档名>.received`

**示例**：
```
docs/planning/
├── 20260403-001-handoff.md
├── 20260403-002-handoff.md
├── .20260403-001-handoff.md.received  ← 标记文件（已接手）
└── .20260403-002-handoff.md.received  ← 标记文件（已接手）
```

**优点**：
- 不修改交接文档内容（保持原始状态）
- 独立标记文件（易于管理和清理）
- 可追溯接手历史（查看标记文件创建时间）

---

### 3. 开工流程调整

```python
def kaigong_with_handoff_receive():
    """开工（自动接手交接文档）"""

    # 1. 查找最新交接文档
    latest_handoff = find_latest_handoff()

    if latest_handoff:
        # 2. 检查是否已接手
        received_marker = latest_handoff.parent / f".{latest_handoff.name}.received"

        if received_marker.exists():
            print(f"📌 最新交接文档已接手：{latest_handoff.name}")
        else:
            # 3. 读取交接文档
            with open(latest_handoff) as f:
                handoff_content = f.read()

            print(f"📌 发现新的交接文档：{latest_handoff.name}\n")
            print(handoff_content)
            print("\n---\n")

            # 4. 标记为已接手
            received_marker.touch()

    # 5. 继续开工流程
    # ...
```

---

### 4. 收工时清理标记文件

```python
def cleanup_old_received_markers(days: int = 7):
    """清理超过 N 天的标记文件"""

    planning_dir = Path("docs/planning")
    cutoff_date = datetime.now() - timedelta(days=days)

    old_markers = [
        f for f in planning_dir.glob(".*.received")
        if datetime.fromtimestamp(f.stat().st_mtime) < cutoff_date
    ]

    for marker in old_markers:
        marker.unlink()
        print(f"🧹 已清理标记文件：{marker.name}")
```

---

## 🔄 完整流程示例

### 场景：用户跨会话工作

```
时间线：

【2026-04-03 14:00】会话 1
用户：/handoff
AI：生成 20260403-001-handoff.md
     Git 提交

【2026-04-03 15:00】会话 2（同一用户，同一天）
用户：/kaigong
AI：检查交接文档...
     📌 发现新的交接文档：20260403-001-handoff.md

     ## 💡 技术决策记录
     ...

     ---
     已标记为已接手

     📋 任务清单：
     ...

【2026-04-04 09:00】会话 3（第二天）
用户：/kaigong
AI：检查交接文档...
     📌 最新交接文档已接手：20260403-001-handoff.md
     （不重复读取）

     📋 任务清单：
     ...
```

---

## ✅ 验收标准

- [ ] 明确"最新"交接文档的排序规则
- [ ] 实现已接手标记机制（.received 文件）
- [ ] 开工时自动读取最新未接手的交接文档
- [ ] 标记已接手状态（防止重复读取）
- [ ] 收工时自动清理旧的标记文件
- [ ] 开工输出包含交接文档内容（明确提示）

---

## 💬 用户反馈问题

1. **是否需要在开工时提示"发现新的交接文档"？**
   - 或者静默读取，仅在输出中显示交接文档内容？

2. **是否需要让用户确认"是否继续开工"？**
   - 或者直接继续开工，不等待用户确认？

3. **标记文件是否需要定期清理？**
   - 或者保留所有标记文件（可追溯接手历史）？

---

*设计分析完成（2026-04-03）*