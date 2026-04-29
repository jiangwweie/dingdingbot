---
title: "开工/收工精简策略分析"
date: 2026-04-03
type: analysis
---

## 🔍 现状分析

### 上下文占用统计

**开工时 AI 读取的文档**：
```
核心文档（必须读取）：
- tasks.json:      1.6K  ← 任务清单（机器可读）
- 交接文档:        2K    ← 最新会话上下文（精简后）
- board.md:        1.8K  ← 状态看板

历史文档（占用大）：
- progress.md:     119K  ⚠️⚠️ 进度日志（最大）
- findings.md:     82K   ⚠️ 技术发现（第二大）
- task_plan.md:    51K   ⚠️ 任务计划（第三大）

Git 检查：
- git status/log:  ~5K

总计：约 252K ⚠️⚠️⚠️
```

**收工时 AI 读取的文档**：
```
Git 检查：
- git status/diff/log:  ~10K

历史文档（读取并更新）：
- progress.md:     119K  ⚠️⚠️
- findings.md:     82K   ⚠️
- task_plan.md:    51K   ⚠️

任务状态更新：
- tasks.json:      1.6K
- board.md:        1.8K

交接文档生成：
- 交接文档:        2K

总计：约 267K ⚠️⚠️⚠️
```

---

## 🎯 核心问题

### 问题 1: 上下文占用过大（252K）

**影响**：
- AI 在开工/收工时需要读取 252K 文档
- 占用大量上下文窗口（可能导致后续任务超限）
- 重要信息被淹没在大量历史记录中

**示例**：
```
AI 开工时读取 progress.md (119K)：
- 包含最近 7 天的详细日志
- 每个会话都记录详细的工作内容（问题发现、根因分析、修复方案、验证结果、Git提交）
- AI 需要读取整个文档才能获取"今日待办"

但真正需要的信息：
- 仅需"今日待办"和"上次会话交接"（约 5K）
- 其余 114K 都是历史信息（不需要）
```

---

### 问题 2: 文档内容重复

**重复信息**：
```
progress.md (119K) 包含：
- 会话时间 + 参与者
- 问题发现 + 根因分析
- 修复方案 + 验证结果
- Git 提交记录
- 任务状态更新

task_plan.md (51K) 包含：
- 任务名称 + 状态
- P0/P1/P2 分级
- 预计工时
- 完成时间

重复部分：
- 任务状态（progress.md 和 task_plan.md 都有）
- 完成时间（progress.md 的 Git 提交和 task_plan.md 的完成时间）
```

**冗余度分析**：
- progress.md 的 119K 中，约 **40%** 信息重复（任务状态、Git提交）
- task_plan.md 的 51K 中，约 **30%** 信息重复（任务状态）

---

### 问题 3: 无法智能提取关键信息

**现状**：
- AI 需要读取整个 progress.md (119K) 才能获取"今日待办"
- AI 需要读取整个 findings.md (82K) 才能获取"相关技术发现"
- AI 无法智能提取当前任务需要的信息

**期望**：
- AI 只读取"今日待办"（5K）
- AI 只读取"相关技术发现"（智能匹配，约 10K）
- AI 不读取历史信息（除非用户明确要求）

---

### 问题 4: 历史文档持续膨胀

**progress.md 膨胀趋势**：
```
当前：119K（最近 7 天）
预计（14 天后）：230K ⚠️⚠️
预计（30 天后）：500K ⚠️⚠️⚠️（已超限）
```

**findings.md 膨胀趋势**：
```
当前：82K（18 个章节）
预计（新增 10 个章节）：130K ⚠️⚠️
预计（新增 20 个章节）：180K ⚠️⚠️⚠️
```

**恶性循环**：
```
文档膨胀 → 开工读取更多 → 占用上下文
→ AI 记忆混乱 → 生成长交接文档
→ 收工写入更多 → 文档进一步膨胀 🔄
```

---

## 💡 精简策略（5 个方案）

### 方案 1: 进度日志分段读取（最小改动）

**核心理念**：progress.md 仅保留最近 3 天详细日志，其余归档。

**改进措施**：
```markdown
progress.md 结构调整：

## 📍 最近 3 天（详细日志）
### 2026-04-03 - DEBT-4 修复
[详细内容...]

### 2026-04-02 - DEBT-3 实现
[详细内容...]

### 2026-04-01 - TEST-1 测试
[详细内容...]

---

## 📦 归档日志（摘要）
- 2026-03-25 至 2026-03-31: 完成 5 个任务（详见 archive/progress-archive.md）

---

## 📌 今日待办（快速访问）
- [x] DEBT-4: 方法重名冲突修复 ✅
- [ ] DEBT-5: asyncio.Lock 事件循环修复
- [ ] TEST-2: 集成测试 fixture 重构
```

**效果**：
- progress.md 大小：119K → **30K**（减少 89K）⭐⭐⭐
- AI 开工时仅读取"最近 3 天" + "今日待办"（约 10K）
- 历史日志归档到 `archive/progress-archive.md`（AI 不读取）

**优点**：
- 最小改动（仅调整文件结构）
- 立即见效（减少 89K）
- 保留历史记录（可追溯）

**缺点**：
- 仍需手动归档（每次收工时）
- "今日待办"需要手动维护（可能忘记更新）

---

### 方案 2: 技术发现智能匹配（中等改动）

**核心理念**：findings.md 按主题标签分类，AI 开工时智能匹配相关发现。

**改进措施**：
```markdown
findings.md 结构调整：

## 📑 按主题分类

### asyncio 并发 (asyncio)
- DEBT-4: Python 方法重名覆盖机制
- DEBT-5: asyncio.Lock 事件循环冲突

### API 依赖注入 (api)
- DEBT-3: API 依赖注入方案实现
- T1: 接口拆分方案

### 测试最佳实践 (test)
- TEST-1: 策略参数 API 集成测试
- TEST-2: 集成测试 fixture 重构

### 前端架构 (frontend)
- Phase 6 前端架构
- 订单管理级联展示

---

## 🔍 快速检索

**按任务 ID 查找**：
- DEBT-3 → asyncio 并发
- TEST-1 → 测试最佳实践

**按关键词查找**：
- asyncio → 3 条发现
- API → 5 条发现
```

**AI 开工时智能匹配**：
```python
def match_findings(current_task: str) -> List[str]:
    """根据当前任务智能匹配相关技术发现"""

    # 示例：当前任务是 "DEBT-5: asyncio.Lock 事件循环修复"
    tags = extract_tags(current_task)  # ["asyncio", "concurrent"]

    # 从 findings.md 中匹配相关发现
    relevant_findings = []
    for section in findings_sections:
        if any(tag in section.tags for tag in tags):
            relevant_findings.append(section)

    return relevant_findings  # 仅返回相关的发现（约 10K）
```

**效果**：
- findings.md 大小保持不变（82K）
- AI 开工时仅读取相关发现（约 10K，减少 72K）⭐⭐⭐
- 按主题标签快速定位

**优点**：
- 智能提取（无需读取整个文档）
- 按主题分类（易于维护）
- 快速检索（提高效率）

**缺点**：
- 需要 AI 能力提升（智能匹配）
- 需要手动维护主题标签
- 实现复杂度中等

---

### 方案 3: 任务计划精简版（保守改进）

**核心理念**：task_plan.md 仅保留当前阶段任务，历史任务归档。

**改进措施**：
```markdown
task_plan.md 结构调整：

## 🔥 P0 级 - 当前阶段任务（2026-04-03）

### OpenClaw 集成需求
| ID | 任务 | 预计工时 | 状态 |
|----|------|----------|------|
| OC-1-1 | OpenClaw 技能开发 | 2h | ☐ 待启动 |
| OC-1-2 | 盯盘狗 API 扩展 | 2h | ☐ 待启动 |

### 技术债修复
| ID | 任务 | 预计工时 | 状态 |
|----|------|----------|------|
| DEBT-1 | 创建 order_audit_logs 表 | 1.5h | ☐ 待启动 |
| DEBT-2 | 集成交易所 API | 2h | ☐ 待启动 |

---

## ✅ 已完成任务（归档）
- Phase 8 自动化调参 ✅（2026-03-25）
- 订单管理级联展示 ✅（2026-03-20）
- [其余已完成任务归档到 archive/task-plan-archive.md]

---

## 📋 任务快速检索
- 按 ID 查找：`grep "DEBT-1" task_plan.md`
- 按状态查找：`grep "☐ 待启动" task_plan.md`
```

**效果**：
- task_plan.md 大小：51K → **15K**（减少 36K）⭐⭐
- AI 开工时仅读取"当前阶段任务"（约 10K）
- 已完成任务归档（AI 不读取）

**优点**：
- 保守改进（仅归档已完成任务）
- 聚焦当前阶段（避免历史干扰）
- 保留历史记录（可追溯）

**缺点**：
- 需要手动归档（每次收工时）
- 可能丢失上下文（已完成任务的决策）

---

### 方案 4: AI 智能上下文压缩（根本解决）

**核心理念**：AI 主动识别重要信息，压缩无关信息。

**压缩策略**：
```python
def compress_planning_docs() -> dict:
    """AI 开工时智能压缩 planning 文档"""

    # 1. 识别当前任务（从 tasks.json）
    current_tasks = read_tasks_json()  # 1.6K

    # 2. 匹配相关技术发现（从 findings.md）
    relevant_findings = match_findings(current_tasks)  # ~10K

    # 3. 提取今日待办（从 progress.md 最近 1 天）
    today_todos = extract_today_todos()  # ~5K

    # 4. 读取最新交接文档
    latest_handoff = read_latest_handoff()  # 2K

    # 5. 读取状态看板
    board = read_board()  # 1.8K

    # 返回压缩后的上下文（总计 ~20K）
    return {
        "current_tasks": current_tasks,
        "relevant_findings": relevant_findings,
        "today_todos": today_todos,
        "latest_handoff": latest_handoff,
        "board": board
    }

    # 不读取：
    # - progress.md 历史（114K）
    # - findings.md 不相关部分（72K）
    # - task_plan.md 已完成任务（36K）
```

**AI 开工流程**：
```
原流程（读取 252K）：
1. 读取 tasks.json (1.6K)
2. 读取 progress.md (119K) ← 大文档
3. 读取 findings.md (82K) ← 大文档
4. 读取 task_plan.md (51K) ← 大文档
5. 读取交接文档 (2K)
6. Git 检查 (5K)

新流程（读取 20K）：
1. 读取 tasks.json (1.6K)
2. 智能匹配 findings.md (10K) ← 仅相关部分
3. 提取今日待办 (5K) ← 仅最近 1 天
4. 读取交接文档 (2K)
5. 读取 board.md (1.8K)
6. Git 检查 (5K)

减少：232K ⭐⭐⭐⭐⭐
```

**效果**：
- 开工上下文：252K → **20K**（减少 92%）⭐⭐⭐⭐⭐
- AI 主动管理上下文（无需手动归档）
- 仅读取相关信息（智能提取）

**优点**：
- 根本解决上下文问题
- 无需手动维护（AI 自动）
- 聚焦当前任务（避免历史干扰）

**缺点**：
- 需要 AI 能力提升（智能匹配/提取）
- 实现复杂度高（需开发智能压缩模块）
- 可能遗漏重要信息（匹配不准确）

---

### 方案 5: 开工/收工流程简化（激进改进）

**核心理念**：删除 progress.md 和 findings.md，仅保留 tasks.json + board.md + 交接文档。

**改进措施**：
```
删除文档：
- ❌ progress.md (119K) → 替代方案：Git 提交记录 + 交接文档摘要
- ❌ findings.md (82K) → 替代方案：交接文档"技术决策记录"章节
- ❌ task_plan.md (51K) → 替代方案：tasks.json + board.md

保留文档：
- ✅ tasks.json (1.6K) - 任务清单（机器可读）
- ✅ board.md (1.8K) - 状态看板
- ✅ 交接文档 (2K) - 会话上下文
```

**开工流程简化**：
```
原流程（7 步）：
1. 同步 git 状态
2. 检查未提交变更
3. 读取交接文档
4. 读取 tasks.json
5. 读取 task_plan.md ← 删除
6. 读取 progress.md ← 删除
7. 读取 findings.md ← 删除

新流程（4 步）：
1. 同步 git 状态
2. 检查未提交变更
3. 读取交接文档（包含技术决策）
4. 读取 tasks.json + board.md

减少：3 步，减少 232K ⭐⭐⭐⭐⭐
```

**收工流程简化**：
```
原流程（5 步）：
1. 状态检查
2. 更新 progress.md ← 删除
3. 更新 findings.md ← 删除
4. 更新 task_plan.md ← 删除
5. 生成交接文档 + Git 提交

新流程（2 步）：
1. Git 检查 + 提交
2. 生成交接文档（包含技术决策）

减少：3 步，减少 201K ⭐⭐⭐⭐⭐
```

**交接文档增强**：
```markdown
# 交接文档（增强版）

## 💡 技术决策记录（替代 findings.md）
### 决策 1: asyncio.Lock vs Redis 分布式锁
- **背景**: MVP 需快速验证
- **选择**: asyncio.Lock
- **理由**: 单进程足够
- **后续**: Phase 6 引入 Redis

---

## 📊 会话统计（替代 progress.md）
- **修改文件**: 5 个（详见 git diff）
- **Git 提交**: 3 次（详见 git log）
- **任务状态**: 2 个完成（详见 board.md）

---

## 📋 今日待办（替代 progress.md）
- [x] DEBT-4: 方法重名冲突修复 ✅
- [ ] DEBT-5: asyncio.Lock 事件循环修复
```

**效果**：
- 开工上下文：252K → **5.4K**（减少 98%）⭐⭐⭐⭐⭐
- 收工上下文：267K → **5.4K**（减少 98%）⭐⭐⭐⭐⭐
- 开工流程：7 步 → 4 步（减少 43%）
- 收工流程：5 步 → 2 步（减少 60%）

**优点**：
- 最激进改进（彻底解决上下文问题）
- 流程大幅简化（减少步骤）
- 文档数量减少（易于维护）

**缺点**：
- 丢失历史记录（progress.md/findings.md 删除）
- 破坏现有习惯（用户习惯了 3 文档）
- 可能影响追溯（无法查看历史进度）
- 交接文档功能增强（负担增加）

---

## 📊 方案对比

| 方案 | 开工上下文 | 收工上下文 | 实现难度 | 破坏现有习惯 | 推荐指数 |
|------|-----------|-----------|----------|-------------|----------|
| 方案 1: 进度日志分段 | 30K (↓89K) | 30K (↓89K) | 低 | 低 | ⭐⭐⭐⭐（短期） |
| 方案 2: 技术发现匹配 | 20K (↓72K) | 82K (不变) | 中 | 低 | ⭐⭐⭐（中期） |
| 方案 3: 任务计划精简 | 15K (↓36K) | 15K (↓36K) | 低 | 低 | ⭐⭐⭐（中期） |
| 方案 4: AI 智能压缩 | 20K (↓232K) | 20K (↓232K) | 高 | 低 | ⭐⭐⭐⭐⭐（长期） |
| 方案 5: 流程简化 | 5.4K (↓247K) | 5.4K (↓247K) | 低 | 高 | ⭐⭐⭐（激进） |

---

## 🎯 推荐实施方案

### 立即实施（方案 1）

**progress.md 分段读取**：
- 仅保留最近 3 天详细日志
- 其余归档到 `archive/progress-archive.md`
- 新增"今日待办"章节（快速访问）

**效果**：减少 89K，立即可用

---

### 1-2 周后实施（方案 2 + 方案 3）

**findings.md 智能匹配**：
- 按主题标签分类
- AI 开工时智能匹配相关发现

**task_plan.md 精简**：
- 仅保留当前阶段任务
- 已完成任务归档

**效果**：再减少 108K

---

### 1 个月后实施（方案 4）

**AI 智能压缩**：
- AI 主动识别重要信息
- 仅读取当前任务相关内容
- 自动压缩历史信息

**效果**：减少 232K，根本解决

---

## 🚀 立即可执行的改进

**改进 1: progress.md 分段策略**

```markdown
# 进度日志（分段版）

> **说明**: 仅保留最近 3 天详细日志，其余归档。

---

## 📍 最近 3 天（详细日志）

### 2026-04-03 - DEBT-4 方法重名冲突修复 ✅
[详细内容...]

### 2026-04-02 - DEBT-3 API 依赖注入实现 ✅
[详细内容...]

### 2026-04-01 - TEST-1 策略参数 API 测试 ✅
[详细内容...]

---

## 📦 归档日志（摘要）
- 2026-03-25 至 2026-03-31: 完成 5 个任务（详见 archive/progress-archive.md）

---

## 📌 今日待办（快速访问）

### 待启动任务
- [ ] DEBT-1: 创建 order_audit_logs 表 (1.5h)
- [ ] DEBT-2: 集成交易所 API 到批量删除 (2h)
- [ ] DEBT-5: asyncio.Lock 事件循环修复 (1h)

### 进行中任务
- [ ] TEST-2: 集成测试 fixture 重构 (进度 60%)

### 已完成今日任务
- [x] DEBT-4: 方法重名冲突修复 ✅
```

---

**改进 2: /shougong 自动归档 progress.md**

```python
def archive_old_progress_logs():
    """归档超过 3 天的进度日志"""

    # 1. 读取 progress.md
    progress_path = Path("docs/planning/progress.md")

    # 2. 解析最近 3 天日志
    recent_logs = extract_recent_logs(days=3)

    # 3. 提取其余日志
    old_logs = extract_old_logs(days_cutoff=3)

    # 4. 创建归档摘要
    archive_summary = create_archive_summary(old_logs)

    # 5. 写回 progress.md（仅保留最近 3 天）
    write_progress(recent_logs + archive_summary)

    # 6. 写入归档文件
    archive_path = Path("docs/planning/archive/progress-archive.md")
    write_archive(archive_path, old_logs)
```

---

## 💬 用户决策问题

1. **progress.md 分段是否可行？**
   - 仅保留最近 3 天详细日志是否足够？
   - 或者需要最近 7 天？

2. **findings.md 智能匹配是否需要？**
   - AI 能否准确匹配相关技术发现？
   - 或者用户习惯了读取整个 findings.md？

3. **方案 5 是否过于激进？**
   - 删除 progress.md/findings.md 是否影响追溯？
   - 或者用户愿意牺牲历史记录换取极致精简？

---

*深度分析完成（2026-04-03）*