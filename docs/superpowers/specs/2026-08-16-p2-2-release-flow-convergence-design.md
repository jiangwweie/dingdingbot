---
title: P2_2_RELEASE_FLOW_CONVERGENCE_DESIGN
status: IMPLEMENTED
date: 2026-08-16
phase: P2.2
---

# P2.2 发布流程收敛设计

## 目标

将一次候选发布收敛为一个可审计的只读计划：**变更分类、精确 Commit、所需认证、受影响服务、唯一当前阶段与首要阻塞点**。它不取代既有 Tokyo 或 Owner Console 发布器，也不新增服务器常驻服务。

```text
git base + exact target commit
-> R0/R1/R2/R3/R4 classification
-> exact certification-manifest requirement
-> Orient / Prepare / Switch / Verify / Activate / Seal
-> existing scoped release executor
```

## 已知事实

1. `scripts/classify_release.py` 已能将路径提升到最重的 **R0–R4**，但该判断未成为候选认证与发布入口的统一契约。
2. Owner Console 已有独立 **R1 static** 与 **R2 API** 发布器；Kernel 发布器只处理 **R3/R4**。
3. P2.1 已定义 `FAST_KERNEL_COMMANDS`、`R1_STATIC_COMMANDS`、`R2_OWNER_API_COMMANDS`、`R3_SAME_SCHEMA_KERNEL_COMMANDS`、`R4_SCHEMA_AUTHORITY_COMMANDS` 与 Periodic Audit；现有 Kernel 认证仍固定使用 R3 完整组合。
4. 生产存在活跃 Ticket 时，不得运行 R3/R4 Switch；本阶段不执行任何 Tokyo 写操作。

来源：`scripts/classify_release.py`、`scripts/trading_kernel/certify_release_candidate.py`、`scripts/owner_console/*`、`MULTI_ASSET_STRATEGYGROUP_ROADMAP.md`。

## 决策

新增一个纯本地 **Release Control Plan**，只负责以下内容：

| 职责 | 单一权威 | 不负责 |
| --- | --- | --- |
| 变更归类 | `classify_release.py` | 猜测策略或风险语义 |
| 候选身份 | 精确 Git Commit | 使用 `HEAD` 的模糊别名作为最终证据 |
| 认证要求 | P2.1 verification portfolios，按实际发布面形成一个或多个精确 Manifest | 重跑已有精确 Manifest |
| 阶段状态 | 一次本地控制命令 stdout | PostgreSQL 运行时事实或新的服务 |
| 执行 | 已有 R1/R2/R3/R4 scoped executor | 绕过正式 Kernel、Owner API 或 Nginx 路径 |

### 阶段语义

| 阶段 | 含义 | 失败后的唯一首要状态 |
| --- | --- | --- |
| `orient` | 固定 base、target、路径与 Release Level | `classification_required` |
| `prepare` | 验证候选 Manifest 或明确其缺失 | `certification_required` |
| `switch` | 调用该 Release Level 唯一 scoped executor | `switch_blocked` |
| `verify` | 执行该 executor 的 scoped smoke / postflight | `verification_failed` |
| `activate` | 仅 R3/R4 的 Entry 最后激活语义；R1/R2 为不适用 | `activation_blocked` |
| `seal` | 输出精确 Commit、阶段耗时和结果 | `seal_required` |

## 边界与失败语义

1. **R0** 不部署，不要求认证 Manifest。
2. **R1** 只允许静态 Owner Console 构建与 HTTPS smoke；不得停止 Kernel Worker 或访问交易所。
3. **R2** 只允许 Owner API 认证与 Unix Socket/HTTPS smoke；不得改 Kernel Runtime Identity。
4. 同一 Candidate 若同时修改 R1 静态前端和 R2 Owner API，必须分别拥有两个同 Commit Manifest；最高 Release Level 不得掩盖较轻发布面的认证。
5. **R3** 必须复用同 Commit 的 Kernel R3 Manifest，且仍由既有执行器要求内外部 flatness。
6. **R4** 必须使用 R4 Command Set；既有停止、空仓、前向 Migration、保存证明和 fix-forward 门禁不变。
7. 任何未知或共享生产路径提升至 **R3**；不允许降级。
8. Manifest 缺失时只报告 `certification_required`，不得自动重跑重型认证。

## 测试与完成条件

1. 路径混合时仅向更重级别提升；
2. 同一 base/target 的计划稳定、精确并包含单一下一阶段；
3. R0–R4 正确映射 Portfolio、Manifest 与受影响服务；
4. 缺失 Manifest 不触发认证或部署；
5. 已认证的精确 Commit 被复用而非重跑；
6. R1/R2 不暴露 Kernel Switch；R3/R4 不绕过既有 flat/Migration 门禁；
7. 无生产 Schema、Worker、Policy、Exchange 或 Tokyo 变更。
