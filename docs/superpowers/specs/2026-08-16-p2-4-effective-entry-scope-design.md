---
title: P2_4_EFFECTIVE_ENTRY_SCOPE_DESIGN
status: IMPLEMENTED
date: 2026-08-16
phase: P2.4
---

# P2.4 Effective Entry Scope

## 目标

提供一个有界的 **`GET /api/owner/v1/entry-scope`**，解释当前哪些策略-标的-方向范围具备进入正式准入的前置条件。

## 已知事实

权威状态已分散在 PostgreSQL 当前投影：**Owner Policy**、**Strategy Entry Control**、**Runtime Scope**、**Readiness**、**Runtime Capability**、**Product Current** 与 **Account Exposure**。这些事实此前分别存在于控制页、标的中心和 Entry Worker 内部，Owner 无法从一个只读视图理解首个阻断点。

## 决策

1. 使用一个短暂、Repeatable Read、只读 PostgreSQL 查询；最多 **100** 个范围。
2. `can_issue_ticket_now=true` 仅表示该范围当前没有范围级阻断，**不是 Ticket 准入承诺**。
3. 首要阻断顺序为：全局 Policy、Runtime Fence、策略暂停、Scope 生命周期、标的产品/时段事实、Readiness。
4. 最终 Signal 有效性、账户实时事实、Netting Domain、容量仲裁与 immutable AdmissionDecision 仍必须在既有 Entry 链中重新核验。

## 不做的事

不新增 Worker、缓存、聚合表、交易所调用、运行时文件或第二条交易路径；不改变任何 Entry、Lifecycle、风险或策略参数。
