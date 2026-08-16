---
title: P2_2_RELEASE_FLOW_CONVERGENCE_EXECUTION_PLAN
status: COMPLETED
date: 2026-08-16
phase: P2.2
design: 2026-08-16-p2-2-release-flow-convergence-design.md
---

# P2.2 执行计划

1. 为 Release Level、冻结 Candidate、认证要求和阶段状态建立纯本地模型与 RED 测试。
2. 将 P2.1 的 Command Set 绑定到 R1–R4，而不是在调用方重复硬编码。
3. 为 Kernel R3/R4 Manifest 增加精确 Release Level 身份，并保留对既有 R3 验证入口的确定性行为。
4. 增加 Release Control CLI：默认只输出计划与第一阻塞点；显式执行仍委托现有 scoped executor，P2.2 不调用该执行路径。
5. 运行单元、现有认证、Ruff、Mypy 与架构检查；冻结后仅在本阶段最终候选运行一次比例适当的认证。
6. 将 `verification_portfolios.py` 明确归类为本地认证组合定义；它不改变 Tokyo Kernel 发布面，避免 Owner Console 候选被错误提升为 R3。

禁止范围：Tokyo、Nginx、真实 Exchange、生产 PostgreSQL、Policy、Registry、Worker 和 Schema 变更。
