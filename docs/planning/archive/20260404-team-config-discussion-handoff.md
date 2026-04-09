# 交接文档 - 团队配置与工作流优化讨论（未完成）

**会话 ID**: 20260404-team-config-discussion
**时间**: 2026-04-04
**状态**: 🔄 进行中

---

## 📋 已完成工作

### 1. 团队配置优化决策 ✅

**决策：PM 和 Coordinator 合并，保留 7 个角色**

| 决策项 | 结论 | 理由 |
|--------|------|------|
| PM 和 Coordinator 是否合并 | ✅ 应该合并 | 职责 60% 重叠，合并后简化流程 |
| Product Manager 是否保留 | ✅ 必须保留 | 需求澄清不可或缺 |
| Architect 是否保留 | ✅ 必须保留 | 架构设计不可或缺 |
| 角色总数 | 7 个（原 8 个） | 删除 Coordinator |

**最终角色配置**：

```
决策层（3 个）：
  - Product Manager: 需求决策（需求澄清、PRD 编写、MVP 定义）
  - Architect: 技术决策（架构设计、契约表、trade-off 分析）
  - PM: 执行决策（任务分解、Agent 调度、进度追踪）

执行层（3 个）：
  - Backend Dev: 后端实现 + 单元测试
  - Frontend Dev: 前端实现 + 单元测试
  - QA Tester: 测试策略 + 单元/集成/E2E 测试

支持层（2 个）：
  - Code Reviewer: 代码审查 + 架构一致性检查
  - Diagnostic Analyst: 问题诊断 + 根因分析
```

---

### 2. 已识别但未解决的问题 ⚠️

#### 问题 1：工作流冗余
- 开工/收工/交接功能重叠 50-70%
- 流程冗长（开工 → 工作 → 收工 → 交接）
- 待讨论：是否合并收工和交接？

#### 问题 2：文档爆炸
- progress.md、findings.md、交接文档只增不减
- 对 Agent 上下文消耗大
- 待讨论：自动归档机制？Memory 替代？

#### 问题 3：三阶段拆分
- 用户提出：需求+架构 / 开发 / 测试 三阶段
- 测试阶段必须拆分（耗时长）
- 待讨论：阶段 1 和 2 是否拆分？如何衔接？

#### 问题 4：双设备协同
- MacBook Air + Mac Mini 通过 Git 同步
- 可能存在冲突
- 待讨论：Memory MCP 辅助？

#### 问题 5：background → 子代理模式切换
- 当前：background task（看不到进度）
- 目标：子代理模式（foreground）
- 待讨论：如何切换？工作流如何调整？

---

## 📋 下一步优先级

### P0：立即执行

**任务 1：删除 Coordinator 并合并到 PM**
- 文件：`.claude/team/team-coordinator/SKILL.md`（删除）
- 文件：`.claude/team/project-manager/SKILL.md`（更新）
- 预计工时：1h

**任务 2：更新 settings.json**
- 移除 coordinator subagent
- 保留 7 个 subagents
- 预计工时：0.5h

### P1：后续讨论

**讨论 1：工作流优化**
- 开工/收工/交接 skill 简化
- 文档爆炸治理方案
- 三阶段拆分方案

**讨论 2：Skills 专业性评估**
- 开工 skill（v7.5）是否需要调整？
- 收工 skill 是否集成交接功能？
- 是否需要文档自动归档？

---

## 💡 关键决策记录

### 决策 1：PM 和 Coordinator 合并

**背景**：
- PM 和 Coordinator 职责 60% 重叠
- Coordinator 定义为"兼任 PdM/Arch/PM"，职责过重
- 调用流程：PM → Coordinator → Agent（双重调用）

**选择方案**：
- PM 承担协调职责（任务分解 + Agent 调度 + 进度追踪）
- 删除独立的 Coordinator 角色

**拒绝方案**：
- 方案 B（保留两者）- 职责重叠，调用冗长
- 方案 C（Coordinator 吞并 PM）- 统一入口职责丢失

**理由**：
1. PM 原本就是统一入口，承担协调职责顺理成章
2. 减少 Agent 调用层次（PM → Coordinator → Agent 变为 PM → Agent）
3. 角色数量减少，职责更清晰

**影响**：
- 需要修改 PM SKILL（整合 Coordinator 职责）
- 需要删除 Coordinator SKILL
- 需要更新 settings.json

---

### 决策 2：保留 Product Manager 和 Architect

**背景**：
- 有人建议删除 PdM 和 Arch，让 Coordinator 兼任
- Coordinator 已经过重，不能再兼任

**选择方案**：
- 保留 Product Manager（需求决策）
- 保留 Architect（技术决策）
- PM 只负责执行决策和协调

**理由**：
1. PdM 的需求澄清职责不可或缺
2. Arch 的架构设计职责不可或缺
3. 职责分离，术业有专攻

**影响**：
- 角色配置更清晰
- 决策层（PdM/Arch/PM）各司其职

---

## 🚨 注意事项

### PM 调用流程设计

**推荐方案：自动判断并路由**

```python
用户："我想加个止损功能"

PM 自动判断流程：
  1. 检测为"新功能需求"
  2. 转给 Product Manager 需求澄清
  3. 转给 Architect 设计方案
  4. PM 分解任务
  5. PM 并行调度 Agent 执行
  6. PM 追踪进度并汇报
```

**优势**：
- 用户无需手动切换角色
- PM 作为统一入口，自动协调

---

## 📂 需要修改的文件

### 立即修改（P0）

| 文件 | 操作 | 说明 |
|------|------|------|
| `.claude/team/team-coordinator/SKILL.md` | 删除 | Coordinator 角色删除 |
| `.claude/team/project-manager/SKILL.md` | 更新 | 整合 Coordinator 职责 |
| `.claude/settings.json` | 更新 | 移除 coordinator subagent |

### 后续讨论后修改（P1）

| 文件 | 操作 | 说明 |
|------|------|------|
| `.claude/skills/kaigong/SKILL.md` | 更新 | 根据工作流优化调整 |
| `.claude/skills/shougong/SKILL.md` | 更新 | 可能集成交接功能 |
| `.claude/skills/handoff/SKILL.md` | 更新/删除 | 根据讨论结果决定 |
| `docs/planning/progress.md` | 更新 | 可能添加自动归档 |

---

## 🔗 相关文档

- `.claude/team/README.md` - 团队配置说明
- `.claude/team/WORKFLOW.md` - 工作流配置
- `.claude/settings.json` - 当前配置
- `docs/planning/progress.md` - 进度日志

---

## 💭 未完成讨论清单

### 优先级 P0（必须完成）

- [ ] 修改 PM SKILL（整合 Coordinator 职责）
- [ ] 删除 Coordinator SKILL
- [ ] 更新 settings.json

### 优先级 P1（重要）

- [ ] 工作流优化讨论：
  - 开工/收工/交接 skill 是否合并？
  - 如何简化用户操作流程？

- [ ] 文档爆炸治理方案：
  - 自动归档机制设计
  - Memory 替代方案
  - 上下文控制策略

- [ ] 三阶段拆分方案：
  - 第1阶段：需求 + 架构（是否拆分？）
  - 第2阶段：开发执行
  - 第3阶段：测试 + 审查
  - 阶段衔接机制设计

- [ ] Background → 子代理模式切换：
  - 如何切换？
  - 工作流如何调整？

### 优先级 P2（可选）

- [ ] 双设备协同优化：
  - Memory MCP 使用策略
  - Git 冲突预防机制

---

**下次会话启动方式**：

```
新会话输入："继续团队配置和工作流优化讨论"
```

系统会自动加载此交接文档。