# 工作流优化实施方案 - v3.0

**版本**: v3.0
**最后更新**: 2026-04-04
**状态**: ✅ 已确认，待执行

---

## 📋 讨论成果总结

### 已确认的 5 个关键决策

**决策 1：三阶段工作流拆分** ✅
- 阶段 1：需求沟通（头脑风暴，强制交互式）
- 阶段 2：架构设计 + 开发 + 单元测试（架构设计后暂停等待审查）
- 阶段 3：集成测试 + 代码审查 + 交付（自动收工）

**决策 2：交互式沟通策略** ✅
- 阶段 1（需求沟通）：强制交互式（头脑风暴）
- 阶段 2（架构设计）：可选交互式（用户可跳过对话）

**决策 3：废弃交接 Skill** ✅
- 保留：开工（/kaigong）+ 收工（/shougong）
- 废弃：交接（/handoff）
- 替代方案：暂停关键词触发 + 开工自动读取

**决策 4：前端测试位置** ✅
- 阶段 2：前端组件测试（React Testing Library，与前端开发同步）
- 阶段 3：前端集成测试 + E2E 测试（Mock API + Playwright）

**决策 5：文档爆炸治理（混合方案）** ✅
- Memory MCP：技术决策（永久保留）
- findings.md：临时发现（7 天归档）
- progress.md：进度日志（3 天归档）
- 废弃交接文档

---

## 🎯 最终实施方案

### 一、三阶段工作流设计（完整版）

```
【阶段 1】需求沟通（头脑风暴，强制交互式）

  执行方式：Foreground（用户可见）

  触发命令：/product-manager

  执行步骤：
    1.1 PdM 需求澄清（至少 3 个问题）
    1.2 用户确认需求理解（交互式）
    1.3 PdM 输出 PRD 文档

  输出文档：
    - docs/products/<feature>-brief.md（PRD）
    - Memory MCP（需求背景）

  用户审查点：需求理解确认 ⭐

  暂停触发：用户输入"暂停"/"午休"/"休息"等关键词
    → 自动更新 progress.md + findings.md + Memory MCP
    → Git 提交（不推送）


【阶段 2】架构设计 + 开发 + 单元测试

  执行方式：Foreground（用户可见）

  触发命令：/architect → /pm

  执行步骤：
    2.1 Arch 架构设计（可选交互式）
        - 输出：ADR + 契约表
        - Memory MCP：立即写入架构决策 ⭐
        - ⚠️ 暂停等待用户审查 ⭐⭐⭐

    2.2 用户审查架构方案（交互式）
        - 用户回复"确认" → 继续
        - 用户回复"修改" → 返回 2.1

    2.3 PM 任务分解（自动）
        - 识别并行簇
        - 创建任务依赖（TaskCreate + addBlockedBy）

    2.4 Backend + Frontend 并行开发
        - Foreground 执行（用户可见进度）
        - 使用 Agent 工具并行调度

    2.5 QA 单元测试
        - 后端单元测试（pytest）
        - 前端组件测试（React Testing Library）

    2.6 Reviewer 实时审查（每个模块完成后）

  用户确认点：测试前确认（耗时 30-60 分钟）⭐

  输出文档：
    - 代码文件（src/, web-front/）
    - 单元测试文件（tests/unit/）
    - docs/designs/<feature>-contract.md（契约表）
    - Memory MCP（架构决策）

  暂停触发：用户输入"暂停"/"午休"/"休息"等关键词
    → 自动更新 progress.md + findings.md + Memory MCP
    → Git 提交（不推送）


【阶段 3】集成测试 + 代码审查 + 交付

  执行方式：Foreground（用户可见）

  触发命令：/pm → /shougong

  执行步骤：
    3.1 QA 集成测试
        - 前端+后端 API 交互（Mock API）
        - 数据库集成测试

    3.2 QA E2E 测试
        - Playwright 自动化测试
        - 关键路径覆盖

    3.3 Reviewer 最终审查
        - 架构一致性检查
        - 安全隐患识别（OWASP Top 10）
        - 代码质量评估

    3.4 PM 交付汇报
        - 生成交付报告
        - 汇报完成情况

    3.5 收工（自动）
        - 更新 progress.md + findings.md
        - 写入 Memory MCP（今日总结）
        - Git 提交 + 推送
        - 自动归档旧文档（超过 7 天交接文档，超过 3 天进度日志）

  输出文档：
    - 测试报告（docs/test-reports/）
    - 交付文档（docs/delivery/）
    - Git 推送

  用户验收点：PM 汇报，用户验收 ⭐
```

---

### 二、暂停机制设计（关键词触发）

```python
# 暂停触发流程
用户输入："暂停"、"午休"、"休息"、"临时离开"、"等我回来"
    ↓
Agent 自动检测关键词
    ↓
自动执行暂停流程：
    1. 更新 progress.md（今日工作）
    2. 更新 findings.md（技术发现）
    3. 写入 Memory MCP（关键决策 + 重要发现）
    4. Git 提交（不推送）
    ↓
输出："✅ 文档已更新，下次开工自动读取"
```

**暂停关键词列表**：
```python
pause_keywords = [
    "暂停", "午休", "休息", "暂停一下", "我要休息",
    "临时离开", "等我回来", "先停一下", "pause"
]
```

---

### 三、开工智能加载策略（混合方案）

```python
def kaigong_smart_loading():
    """开工智能加载（混合方案）"""

    print("🐶 开工 - 智能加载（v8.0 混合方案）")

    # 1. 读取 Memory MCP（永久决策）
    memory_entities = mcp__memory__read_graph()
    arch_decisions = [e for e in memory_entities
                      if e['entityType'] == 'architecture_decision']

    # 2. 读取红线规则（CLAUDE.md）
    red_lines = extract_section("CLAUDE.md", "## 🔴 3 条红线")

    # 3. 读取 findings.md（最近 7 天）
    recent_findings = read_recent_findings(days=7)

    # 4. 读取 progress.md（最近 3 天）
    recent_progress = read_recent_progress(days=3)

    # 5. Git 状态检查
    git_status = git_status_short()

    # 6. 推断今日待办
    todos = infer_todos_from_progress(recent_progress)

    # 上下文占用统计
    total_context = (
        len(str(arch_decisions)) +  # Memory MCP（不限）
        len(red_lines) +             # 红线规则（2K）
        len(recent_findings) +       # findings（10K）
        len(recent_progress)         # progress（30K）
    )

    # 输出给用户
    print(f"""
    📍 当前分支：{git_status['branch']}
    📝 最近提交：{git_status['commits']}

    ---

    📌 核心约束（红线规则）⭐⭐⭐：
    {red_lines}

    ---

    💡 最近架构决策（Memory MCP）：
    {format_decisions(arch_decisions[:3])}

    ---

    📋 今日待办（共 {len(todos)} 个）：
    {format_todos(todos)}

    ---

    📊 上下文统计：
      - Memory MCP：{len(str(arch_decisions))} 字符
      - 红线规则：{len(red_lines)} 字符（2K）
      - findings.md：{len(recent_findings)} 字符（10K）
      - progress.md：{len(recent_progress)} 字符（30K）
      - 总计：{total_context} 字符（约 42K）

    ---

    准备好开始了吗？
    """)
```

---

### 四、Memory MCP 集成策略

#### 4.1 推荐使用场景（本项目）

**1. 记录项目关键决策**
```python
{
  "name": "Phase 5 实盘集成决策",
  "entityType": "decision",
  "observations": [
    "2026-04-04: MCP 配置修复",
    "PU + Memory 双 MCP 启用",
    "ExchangeGateway 订单接口扩展",
    "并发保护: Asyncio Lock + DB 行锁"
  ]
}
```

**2. 维护架构约束知识库**
```python
{
  "name": "Clean Architecture 约束",
  "entityType": "architecture",
  "observations": [
    "domain/ 禁止 I/O 导入",
    "Decimal everywhere",
    "禁用 Dict[str, Any]",
    "Pydantic v2 强类型"
  ]
}
```

**3. 记录技术踩坑**
```python
{
  "name": "MCP 配置踩坑",
  "entityType": "issue",
  "observations": [
    "settings.json 定义 servers",
    "settings.local.json 启用 servers",
    "需要重启才能生效",
    "enabledMcpjsonServers 必须明确列出"
  ]
}
```

**不推荐场景**：
- ❌ 临时对话上下文：用会话记忆即可
- ❌ 代码片段存储：用文件系统更好
- ❌ 大型文档归档：知识图谱不适合大文本

#### 4.2 写入时机

| 决策类型 | 写入时机 | 写入方式 | 理由 |
|---------|---------|---------|------|
| **架构决策** | Arch 设计后立即写入 | 自动写入 | 关键决策，防止丢失 ⭐ |
| **技术发现** | 暂停/收工时写入 | 自动写入 | 次要发现，批量写入 |
| **今日总结** | 收工时写入 | 自动写入 | 工作记录，每日写入 |

#### 4.2 写入示例

```python
# Arch 设计后立即写入架构决策
def write_architecture_decision(decision: dict):
    """写入架构决策到 Memory MCP"""

    mcp__memory__create_entities(
        entities=[
            {
                "entityType": "architecture_decision",
                "name": f"决策-{decision['title']}",
                "observations": [
                    f"选择方案：{decision['selected']}",
                    f"拒绝方案：{decision['rejected']}",
                    f"理由：{decision['reason']}",
                    f"影响：{decision['impact']}",
                    f"日期：{datetime.now().strftime('%Y-%m-%d')}"
                ]
            }
        ]
    )


# 收工时写入今日总结
def write_daily_summary():
    """写入今日总结到 Memory MCP"""

    mcp__memory__create_entities(
        entities=[
            {
                "entityType": "daily_summary",
                "name": f"总结-{datetime.now().strftime('%Y-%m-%d')}",
                "observations": [
                    f"完成任务：{get_completed_tasks()}",
                    f"修改文件：{get_modified_files()}",
                    f"Git 提交：{get_git_commits()}",
                    f"下一步：{get_next_steps()}"
                ]
            }
        ]
    )
```

---

### 五、Sub Agent 模式强制要求

#### 5.1 执行模式对比

| 执行模式 | 命令 | 用户可见 | 用户可干预 | 适用场景 |
|---------|------|---------|-----------|---------|
| **Background** | `run_in_background=True` | ❌ 看不到进度 | ❌ 无法干预 | 长时间任务（不推荐） |
| **Foreground** | `Agent()` 默认 | ✅ 可见进度 | ✅ 可干预 | 需要用户确认的场景 ✅ |

#### 5.2 强制使用 Foreground

**所有阶段必须使用 Foreground 执行**：
- 阶段 1：`/product-manager`（Foreground）
- 阶段 2：`/architect` → `/pm`（Foreground）
- 阶段 3：`/pm` → `/shougong`（Foreground）

**禁止使用 Background 模式**：
- ❌ `Agent(..., run_in_background=True)`
- ✅ `Agent(...)`（默认 Foreground）

---

## 📂 需要修改的文件清单

### 立即修改（P0）

| 文件路径 | 操作 | 说明 |
|---------|------|------|
| `.claude/commands/handoff.md` | 删除 | 废弃交接 Skill |
| `.claude/commands/kaigong.md` | 更新 | 增加 Memory MCP 读取 + 暂停关键词检测 |
| `.claude/commands/shougong.md` | 更新 | 增加 Memory MCP 写入（今日总结） |
| `.claude/team/WORKFLOW.md` | 更新 | 三阶段工作流定义 |
| `.claude/team/project-manager/SKILL.md` | 更新 | 增加 Foreground 执行 + 暂停机制 |
| `.claude/team/architect/SKILL.md` | 更新 | 增加 Memory MCP 写入（架构决策） |
| `.claude/team/product-manager/SKILL.md` | 更新 | 增加强制交互式沟通说明 |
| `CLAUDE.md` | 更新 | 更新工作流说明 |

---

## 🚀 实施步骤

### 步骤 1：删除交接 Skill（0.5h）
```bash
rm .claude/commands/handoff.md
```

### 步骤 2：修改开工 Skill（1h）
- 增加 Memory MCP 读取
- 增加暂停关键词检测
- 优化上下文统计

### 步骤 3：修改收工 Skill（0.5h）
- 增加 Memory MCP 写入（今日总结）
- 优化自动归档逻辑

### 步骤 4：修改 WORKFLOW.md（1h）
- 更新阶段定义（阶段 1/2/3）
- 增加暂停机制说明
- 增加 Foreground 执行说明

### 步骤 5：修改角色 SKILL.md（1h）
- PdM：强制交互式沟通说明
- Arch：Memory MCP 写入
- PM：Foreground 执行 + 暂停机制

### 步骤 6：测试验证（1h）
- 测试开工智能加载
- 测试暂停关键词触发
- 测试收工 Memory 写入
- 测试三阶段工作流

**总计工时：约 5 小时**

---

## ✅ 验收标准

### 验收 1：三阶段工作流
- [ ] 阶段 1 启动 PdM，强制交互式沟通
- [ ] 阶段 2 架构设计后暂停，等待用户审查
- [ ] 阶段 3 自动收工 + Git 推送

### 验收 2：暂停机制
- [ ] 用户输入"暂停"关键词，自动更新文档
- [ ] Git 提交（不推送）
- [ ] 下次开工自动读取

### 验收 3：Memory MCP 集成
- [ ] Arch 设计后 Memory 写入架构决策
- [ ] 收工时 Memory 写入今日总结
- [ ] 开工时 Memory 读取最近决策

### 验收 4：Foreground 执行
- [ ] 所有阶段 Foreground 执行（用户可见进度）
- [ ] 不使用 background 模式

### 验收 5：文档治理
- [ ] progress.md 自动归档（超过 3 天）
- [ ] findings.md 自动归档（超过 7 天）
- [ ] 废弃交接文档

---

## 📊 预期收益

| 维度 | 优化前 | 优化后 | 提升 |
|------|--------|--------|------|
| **用户操作** | 手动触发 7 个阶段 | 手动触发 3 个阶段 | 减少 4 次 ✅ |
| **阶段暂停** | 无暂停机制 | 关键点暂停等待审查 | 用户可控 ✅ |
| **上下文占用** | progress.md 119K | 总计 42K | 减少 77K ✅ |
| **决策追溯** | 文档归档后丢失 | Memory MCP 永久保留 | 永久追溯 ✅ |
| **执行可见性** | background 模式看不到进度 | foreground 模式可见进度 | 用户体验 ✅ |

---

## 🔗 相关文档

- `.claude/team/README.md` - 团队配置说明
- `.claude/team/WORKFLOW.md` - 工作流配置（待更新）
- `docs/planning/progress.md` - 进度日志
- `docs/planning/findings.md` - 技术发现

---

**下一步行动**：
1. 用户审查本实施方案
2. 确认无误后，启动 PM 执行修改
3. 测试验证
4. 更新文档

---

*本方案由产品经理角色制定 | 最后更新：2026-04-04*