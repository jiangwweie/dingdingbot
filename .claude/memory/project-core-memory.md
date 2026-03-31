---
name: 项目核心记忆
description: 项目工作流程、v3 优先级、Phase 完成状态、质量要求
type: project
---

# 项目核心记忆整合

**更新日期**: 2026-03-31
**来源**: `memory/` 目录整合至 `.claude/memory/`

---

## 一、工作流程偏好

**复杂任务必须走全自动工作流**：

```
【阶段 0】需求接收 → 【阶段 1】契约设计 → 【阶段 2】任务分解 → 【阶段 3】并行开发
                                                                    ↓
【阶段 6】提交汇报 ←─【阶段 5】测试执行 ←─【阶段 4】审查验证 ←──────────┘
```

### 核心原则
1. **契约先行**: 先写接口契约表，作为 SSOT（单一事实来源）
2. **并行执行**: 前后端独立任务并行开发
3. **自动审查**: Reviewer 对照契约表检查
4. **无人值守**: 简单问题自解，严重问题标记 blocked 最后汇报

### 通知节点
用户明确要求：**阶段 4 完成，阶段 5 启动前，必须通知用户确认**

### 契约模板
位置：`docs/templates/contract-template.md`

---

## 二、v3 迁移优先级

**核心决策** (2026-03-30):
- v3.0 迁移是当前**唯一首要目标**
- 除 v3 迁移外，所有 P0/P1/P2 待办事项**全部废弃**
- 团队资源集中投入到 v3 迁移

**Phase 1-5 状态** (2026-03-31 更新):
| 阶段 | 名称 | 状态 | 完成日期 |
|------|------|------|----------|
| Phase 1 | 模型筑基 | ✅ 完成 | 2026-03-30 |
| Phase 2 | 撮合引擎 | ✅ 完成 | 2026-03-30 |
| Phase 3 | 风控状态机 | ✅ 完成 | 2026-03-30 |
| Phase 4 | 订单编排 | ✅ 完成 | 2026-03-30 |
| Phase 5 | 实盘集成 | ✅ 完成 | 2026-03-31 |
| Phase 6 | 前端适配 | ⏳ 待启动 | - |

**审查结果**:
- 审查项：57/57 通过 (100%)
- 单元测试：241/241 通过 (100%)

**下一步**: Binance Testnet E2E 集成测试

---

## 三、质量要求与审查红线

### 1. 领域层纯净性
`domain/` 目录**严禁**导入 `ccxt`、`aiohttp`、`requests`、`fastapi`、`yaml` 或任何 I/O 框架。

**检查方式**: `grep -r "import ccxt\|import aiohttp" src/domain/`

### 2. Decimal 精度
所有金额、比率、计算**必须**使用 `decimal.Decimal`。使用 `float` 进行金融计算将被拒绝。

### 3. 类型安全
- **禁用 `Dict[str, Any]`** - 核心参数必须定义具名 Pydantic 类
- **辨识联合** - 多态对象必须使用 `discriminator='type'`
- **自动 Schema** - 接口文档通过模型反射生成

### 4. API 密钥安全
- API 密钥权限：**交易权限 ✅ / 提现权限 ❌**
- 系统启动时校验权限，发现 `withdraw` 权限立即退出 (`F-002`)
- 所有敏感信息必须通过 `mask_secret()` 脱敏后记录日志

### 测试覆盖要求
| 模块 | 覆盖率要求 |
|------|-----------|
| 撮合引擎 | 100% |
| 风控状态机 | 100% |
| 订单编排 | 95% |
| 实盘集成 | 90% |

---

## 四、核心文档索引

### v3 迁移文档
| 文档 | 路径 |
|------|------|
| v3 演进路线图 | `docs/v3/v3-evolution-roadmap.md` |
| 系统进度总览 | `docs/v3/system-progress-summary.md` |
| Phase 1-5 审查报告 | `docs/reviews/phase1-5-comprehensive-review-report.md` |
| Phase 完成报告 | `docs/v3/reports/` |

### 任务计划
| 文档 | 路径 |
|------|------|
| 任务计划 | `docs/planning/task_plan.md` |
| 发现记录 | `docs/planning/findings.md` |
| 进度日志 | `docs/planning/progress.md` |

### 架构规范
| 文档 | 路径 |
|------|------|
| 系统开发规范 | `docs/arch/系统开发规范与红线.md` |
| 重构报告 | `docs/arch/系统重构与架构演进梳理报告.md` |

---

*本文件整合自原 memory/ 目录下的 5 个文件*
*原文件位置：memory/feedback-quality.md, memory/feedback-workflow.md, memory/project-phase1-complete.md, memory/project-v3-priority.md, memory/reference-docs.md*
