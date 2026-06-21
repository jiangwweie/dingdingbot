# Claude Token-Burn 报告索引

Generated: 2026-06-17
Task ID: CLAUDE-FINAL-INDEX-011
Mode: read-only index — no file modifications except this report and NEXT_QUEUE.md

---

## 1. 报告总览

| # | 文件名 | 类型 | 状态 | 最高严重度 | 一句话价值 | 下一步 |
|---|--------|------|------|-----------|-----------|--------|
| 1 | `CLAUDE-AUDIT-001-owner-language-leakage.md` | audit | read-only | HIGH | owner-runtime-console 合规；trading-console 有 62+ 处内部术语泄漏 | 等 Codex 决定 trading-console 定位 |
| 2 | `CLAUDE-AUDIT-002-runtime-safety-redteam.md` | audit | read-only | MEDIUM | 7 项安全发现，无 P0 绕过；stale-fact 和 idempotency 有部分缺口 | 等 mainline 后补充测试 |
| 3 | `CLAUDE-TEST-MAP-001-runtime-path-test-coverage.md` | audit | read-only | HIGH | 11 步运行时路径测试覆盖矩阵；admission 和 notification 最弱 | 等 mainline 后补测试 |
| 4 | `CLAUDE-DEBT-001-deletion-consolidation-map.md` | cleanup-plan | read-only | HIGH | 940MB 非源码质量；35 个 domain 文件链可压缩至 ~15 | 等 mainline 后分 wave 执行 |
| 5 | `CLAUDE-DOC-DEBT-001-doc-authority-conflict-map.md` | docs-fix | docs-applied | HIGH | 19 个 agent 配置文件引用已删除的 docs/canon/* 路径 | Wave 1 已应用（27 文件），Wave 2-5 待定 |
| 6 | `CLAUDE-SCHEMA-DEBT-001-personal-campaign-schema-usage.md` | audit | read-only | LOW | 11 个 schema 全有 Pydantic 模型对应；1 个可归档 | 等 Codex 确认 sandbox 状态 |
| 7 | `CLAUDE-CLEANUP-PLAN-001-agent-config-wave1-rewrite-plan.md` | cleanup-plan | docs-applied | MEDIUM | 35 个文件的 dead-path 重写计划 | Wave 1 已执行（27/35），剩余 8 个 quarantined 文件待处理 |
| 8 | `CODEX-CLEANUP-REVIEW-001-mainline-safe-cleanup-notes.md` | review | read-only | MEDIUM | Codex 对 Claude 报告的整合审查；确认当前清理不影响 mainline | 作为后续 wave 参考 |
| 9 | `CLAUDE-FINAL-REVIEW-002-agent-config-cleanup-safety-review.md` | review | docs-applied | LOW | 确认 27 文件 agent 指令重写安全，不影响 mainline | 可提交或保持 uncommitted |
| 10 | `CLAUDE-FINAL-TASKPACK-003-post-acceptance-task-cards.md` | task-cards | pending-action | HIGH | 5 组 14 个 task card：acceptance-safe → P1 → P2 → deferred → do-not-touch | 按组顺序分发 |
| 11 | `CLAUDE-FINAL-TESTCARDS-004-runtime-safety-test-cards.md` | task-cards | pending-action | CRITICAL | 7 个 P1 测试卡（44 个测试用例）；覆盖 FinalGate、admission、stale-facts、idempotency | 等 mainline 后分发 |
| 12 | `CLAUDE-FINAL-UICARDS-005-owner-console-surface-governance-cards.md` | task-cards | pending-action | HIGH | 8 个 UI 治理卡；owner-runtime-console 合规，trading-console 需决策 | 等 mainline 后分发 |
| 13 | `CLAUDE-FINAL-HANDOFFCARDS-006-strategygroup-handoff-quality-cards.md` | task-cards | pending-action | P1 | 16 个 handoff 质量治理卡（8 个维度） | 等 mainline 后分发 |
| 14 | `CLAUDE-FINAL-HANDOFFQA-007-strategygroup-handoff-readonly-audit.md` | audit | read-only | P1 | 9 个 QA 卡全部执行；发现 SOR-001 模式不一致和 freshness 语义缺口 | 等 Codex 决定 SOR-001 模式 |
| 15 | `CLAUDE-FINAL-CODETRACE-008-handoff-runtime-consumption-audit.md` | code-trace | read-only | P1 | 追踪 HANDOFFQA-007 的 P1 发现到后端代码；确认 conditional_armed_observation 是 phantom mode | 等 Codex 决定 |
| 16 | `CLAUDE-FINAL-DECISIONPACK-009-runtime-semantics-adr-options.md` | decision-pack | decision-needed | P1 | 3 个运行时语义决策选项（SOR-001 mode、freshness、review vocabulary） | 等 Codex 选择方案 |
| 17 | `CLAUDE-FINAL-DOCFIX-010-docs-semantic-cleanup-report.md` | docs-fix | docs-applied | LOW | 4 个 docs/current 文件的语义清理（review mapping、gate class、freshness note） | 已应用，可验证 |
| 18 | `CLAUDE-FINAL-COMMITAUDIT-012-worktree-commit-boundary-audit.md` | review | read-only | MEDIUM | 将脏工作树拆分为 agent cleanup、docs cleanup、token-burn artifacts 与排除项 | 已由 012A 复核当前状态 |
| 19 | `CODEX-COMMITAUDIT-012A-current-state-addendum.md` | review | read-only | LOW | Codex 复核当前 tracked diff，确认 scripts/tests 瞬时观察不再适用 | 已用于提交边界 |
| 20 | `CLAUDE-FINAL-PRECOMMIT-013-safe-local-commit-verification.md` | review | read-only | LOW | 提交前 PASS 校验，确认 27 个 agent 文件与 4 个 docs 文件可拆分提交 | 已应用为 2 个本地提交 |
| 21 | `CLAUDE-FINAL-ARTIFACTAUDIT-014-token-burn-artifact-publication-audit.md` | review | read-only | LOW | 检查 token-burn artifacts 无 secrets / workspace contamination / live data | 已应用为 output artifact 提交 |
| 22 | `CLAUDE-FINAL-LOCALARTIFACTS-015-untracked-artifact-hygiene-audit.md` | audit | read-only | MEDIUM | metadata-only 盘点 648MB / 717 个未跟踪本地产物，形成清理与 .gitignore 建议 | 等 Owner 明确授权后再清理 |
| 23 | `CLAUDE-FINAL-RUNTIMEREVIEW-016-selected-scope-gating-review.md` | review | read-only | P2 | 首次 selected-scope gating 评审（commit 级） | 等 mainline 后实施 |
| 24 | `CLAUDE-FINAL-TESTCARD-017-selected-scope-gating-gap-cards.md` | task-cards | pending-action | P3 | selected-scope gating 测试缺口卡 | 等 mainline 后分发 |
| 25 | `CLAUDE-FINAL-RUNTIMEREVIEW-018-product-state-selected-scope-review.md` | review | read-only | P2 | product-state refresh selected-scope 评审 | 等 mainline 后验证 |
| 26 | `CLAUDE-FINAL-RUNTIMEREVIEW-019-resume-dispatcher-selected-scope-uncommitted-review.md` | review | read-only | P2 | resume-dispatcher selected-scope gating 评审（commit be59c721）；PASS | 等 Codex 决定 blocker_class 分类 |
| 27 | `CLAUDE-FINAL-RUNTIMEREVIEW-020-selected-dispatch-guard-commit-review.md` | review | read-only | P2 | selected-dispatch guard commit 复核；确认 dispatch guard 主路径 PASS | 等 mainline 后继续低风险补测 |
| 28 | `CLAUDE-FINAL-RUNTIMEREVIEW-021-real-order-readiness-matrix-review.md` | review | read-only | P1 | real-order readiness matrix 首轮审查；发现 `open_order_facts_stale` false-positive 风险 | 已由 026/027 复核关闭 |
| 29 | `CLAUDE-FINAL-RUNTIMEREVIEW-022-owner-console-real-order-readiness-consumer-review.md` | review | read-only | P1 | Owner Console consumer propagation 风险审查；确认 producer false-positive 会进入 Owner 状态 | 已由 027 复核关闭 |
| 30 | `CLAUDE-FINAL-TASKCARD-023-readiness-matrix-false-positive-fix-cards.md` | task-cards | pending-action | P1 | 4 张修复卡：producer matching、negative tests、consumer regression、scope hardening | 主要修复已进入 mainline；剩余维护性清理 |
| 31 | `CLAUDE-FINAL-RUNTIMEREVIEW-024-owner-console-frontend-real-order-readiness-review.md` | review | read-only | P2 | Owner Console frontend readiness 文案/位置/烟测审查 | 已由 027 降级为 P3 残余 |
| 32 | `CLAUDE-FINAL-RUNTIMEREVIEW-025-real-order-readiness-chain-closure-audit.md` | review | read-only | P1 | real-order readiness 链路闭环前审查；确认 producer/consumer/frontend 修复优先级 | 已由 027 复核关闭 P1 |
| 33 | `CLAUDE-FINAL-RUNTIMEREVIEW-026-producer-matching-fix-review.md` | review | read-only | P1->P2 | producer matching fix 复核；确认已关闭已知 false-positive，残余为 regex 维护性 | 由 027 确认为 P2 残余 |
| 34 | `CLAUDE-FINAL-RUNTIMEREVIEW-027-post-fix-real-order-readiness-review.md` | review | read-only | P2 | post-fix closure review；确认 021/022 P1 关闭，024 降级 P3，026 降级 P2 | 后续执行 Q-021 |
| 35 | `CLAUDE-FINAL-RUNTIMEREVIEW-028-post-027-follow-up-review.md` | review | read-only | P2 | post-027 follow-up；确认 01fa0b77 family tests PASS，smoke 文案残余由当前 diff 覆盖，修正队列编号冲突 | 等 mainline controller 处理 smoke diff |
| 36 | `CLAUDE-FINAL-RUNTIMEREVIEW-029-owner-console-dry-run-required-checks-review.md` | review | read-only | P2 | Owner Console dry-run required-checks review；确认 fb2c6f71 语义正确，历史旧 artifact 会降级为 P2 残余 | 后续执行 Q-025 文档说明 |
| 37 | `CLAUDE-FINAL-HANDOFFQA-030-current-handoff-readonly-refresh.md` | audit | read-only | P1 | Q-010 handoff read-only QA refresh；确认 SOR-001 mode mismatch 仍为 P1，freshness/review vocabulary/gate mapping 已部分收口 | 先走 Q-011，再决定 Q-026 |
| 38 | `CLAUDE-FINAL-RUNTIMEREVIEW-031-dry-run-audit-summary-review.md` | review | read-only | P3 | 47c159f5 dry-run audit summary exposure review；确认 additive PASS，Q-025 仍需文档化旧 artifact 语义 | 后续执行 Q-025 |
| 39 | `CLAUDE-FINAL-RUNTIMEREVIEW-032-dry-run-readiness-checks-readmodel-review.md` | review | read-only | P2 | 1e58c62b readmodel dry-run checks exposure review；确认 11 项 checks PASS，存在 producer/readmodel drift P2 | 后续 Q-025 / Q-027 |
| 40 | `CLAUDE-FINAL-RUNTIMEREVIEW-033-owner-console-dry-run-summary-card-review.md` | review | read-only | P2 | Owner Console dry-run summary card review；确认 Owner 语言 PASS，残余为空 summary fallback / 类型收窄 / fixture coupling | 后续 Q-027 |
| 41 | `CLAUDE-FINAL-OUTPUTAUDIT-034-token-burn-artifact-consistency-audit.md` | audit | read-only | P2 | token-burn artifact consistency audit；确认 40 report + 2 meta file 一致，修复 NEXT_QUEUE 数量与 Q-003 stale source | 已应用 output-only 元数据修复 |
| 42 | `CLAUDE-FINAL-RUNTIMEREVIEW-035-owner-console-full-frontend-diff-review.md` | review | read-only | P1 | 当前 Owner Console 完整前端 diff 复审；确认 dry-run card 语言 PASS，但 chrome.tsx 移除桌面 nav hover background 为 P1 | 后续 Q-027 修复 |
| 43 | `CLAUDE-FINAL-RUNTIMEREVIEW-036-owner-console-smoke-navigation-review.md` | review | read-only | P1 | smoke/navigation delta 复审；确认 `waitForTimeout(250)` 可接受，但发现内部 `owner_console_source_readiness` 被 Owner UI 直接展示为新 P1 | 后续 Q-027 修复 |
| 44 | `CLAUDE-FINAL-ARCHDEBT-037-runtime-semantics-slimming-audit.md` | architecture-debt | read-only | HIGH | 系统瘦身审计；定位 trading_console / Operation Layer 巨型文件、personal_campaign 遗留、mi001/bnb 特例、双 repo、domain 纯净性和 scripts 泛滥 | 后续 Q-028~Q-035 |
| 45 | `CLAUDE-FINAL-QA-038-owner-language-readmodel-contract-gap-scan.md` | qa | read-only | P1 | Owner-language readmodel contract test gap scan；确认 Q-032 应拆为 backend test-only 与 frontend smoke/source 映射后续 | 后续 Q-032 / Q-036 |
| 46 | `CLAUDE-FINAL-SCRIPTAUDIT-039-active-script-map-and-staleness-audit.md` | audit | read-only | HIGH | scripts active-map 审计；176 个顶层脚本中仅 7 个为 deploy/docs 保护的当前权威入口，剩余按 proof/rehearsal/research/sensitive clusters 分类 | 后续 Q-037~Q-046 |
| 47 | `CLAUDE-FINAL-SCRIPTAUDIT-040-runtime-official-proof-classification.md` | audit | read-only | HIGH | `runtime_official_*` 17 个 proof scripts 分类；确认 1 个 active dry-run dependency、3 个 safety-sensitive boundary proofs、13 个 archive candidates | 后续 Codex 决策是否归档 |
| 48 | `CLAUDE-FINAL-SCRIPTAUDIT-041-build-runtime-packet-builder-classification.md` | audit | read-only | HIGH | `build_runtime_*` 19 个 packet builders 分类；确认 1 个 deploy protected、12 个 protected packet surface、5 个 compat wrapper archive candidates、2 个 exchange/reconciliation decision-required | 后续 Q-040 决策/归档 |
| 49 | `CLAUDE-FINAL-SCRIPTAUDIT-042-seed-profile-seeder-safety-review.md` | audit | read-only | HIGH | `seed_*.py` 6 个 profile/GKS seeder 分类；确认 tiny-live active profile 无强 Owner 守卫、GKS 无 dry-run、3 个 testnet seeder 可归档前需迁移 imports | 后续 Q-047~Q-049 |
| 50 | `CLAUDE-FINAL-SCRIPTAUDIT-043-probe-brc-credential-exchange-auth-safety-review.md` | audit | read-only | HIGH | 10 个 `probe_*`/`brc_*` 分类；确认 trend execute CLI 具备真实 execute POST 能力、scoped safety clearance 会写 PG、Tokyo probe/Owner smoke 为 protected | 后续 Q-050~Q-052 |
| 51 | `CLAUDE-FINAL-SCRIPTAUDIT-044-runtime-live-vs-resume-dispatcher-overlap-audit.md` | audit | read-only | HIGH | 11 个 `runtime_live_*` 与 resume dispatcher 重叠审计；确认 bootstrap/position monitor/signal routing/selector 需 protected，continuation/operator/enablement 链为 archive-prep | 后续 Q-053~Q-054 |
| 52 | `CLAUDE-FINAL-SCRIPTAUDIT-045-codex-owned-core-import-audit.md` | audit | read-only | HIGH | Codex-owned core modules 的 scripts import 地图；确认 18 个脚本触及核心模块，5 个高风险 exchange/order/recovery 脚本需 guard | 后续 Q-055~Q-057 |
| 53 | `CLAUDE-FINAL-DECISIONPACK-046-high-risk-core-touching-script-guard-map.md` | decision-pack | read-only | HIGH | Q-055 决策包；5 个高风险 core-touching 脚本全部 KEEP-PROTECTED / CODEX-GUARDED，排除 bulk cleanup/archive/comment wave | 后续 ACTIVE_SCRIPT_MAP / per-script Codex task |
| 54 | `CLAUDE-FINAL-SCRIPTAUDIT-047-runtime-official-proof-stub-interface-tracking.md` | audit | read-only | MEDIUM | Q-056 proof stub interface 追踪；RTF-085/087/088 编码 OrderLifecycle、ExchangeGateway、PositionProjection、finalize 合约 | 后续 Q-058~Q-059 |
| 55 | `CLAUDE-FINAL-CHECKLIST-048-proof-stub-contract-core-refactor-checklist.md` | checklist | read-only | MEDIUM/HIGH | Q-058 core refactor checklist；将 RTF-085/087/088 设为 core refactor strong-gate proofs，覆盖 pre-change / implementation / post-change / rollback | 后续 ACTIVE_SCRIPT_MAP / core-refactor task card |
| 56 | `CLAUDE-FINAL-DECISIONPACK-049-runtime-official-proof-archive-preservation-rule.md` | decision-pack | read-only | MEDIUM | Q-059 proof archive preservation rule；定义 runtime_official 归档 README、hard stop、顺序、active dependency 与 safety-sensitive proof 保留规则 | 后续 ACTIVE_SCRIPT_MAP / archive task card |
| 57 | `CLAUDE-FINAL-SCRIPTAUDIT-050-runtime-dry-run-proof-dependency-migration-map.md` | audit | read-only | MEDIUM | Q-060 dry-run proof dependency 迁移图；确认 dry-run chain 只有 1 个 active proof-script import，另有 2 个独立 disabled-smoke consumers | 后续 Q-061/Q-062 |
| 58 | `CLAUDE-FINAL-SCRIPTAUDIT-051-consolidated-active-script-map-draft.md` | audit | read-only | HIGH | Q-063 consolidated Active Script Map 草案；Q-078 已并入 SCRIPTAUDIT-055 verify_runtime 重分类，修正 action_time_bridge 测试覆盖误标 | 后续 Q-064/Q-065/Q-066 / Q-077 |
| 59 | `CLAUDE-FINAL-TASKPACK-052-script-cleanup-wave-plan-and-taskcards.md` | task-cards | pending-action | HIGH | Q-067 script cleanup wave plan；7 波执行计划（Wave 0~6）+ 7 个 task cards (Q-067~Q-073)；DO-NOT-BULK-TOUCH 排除列表 + CODEX-GUARDED 详情 + core refactor guardrails | 按波次顺序分发 |
| 60 | `CLAUDE-FINAL-SCRIPTMAP-053-active-script-map-promotion-draft.md` | script-map | read-only | HIGH | Q-068 ACTIVE_SCRIPT_MAP promotion draft；为后续 docs/current 权威化准备 7 active runtime、24 do-not-bulk-touch、5 CODEX-GUARDED 与 archive preconditions | 后续 Q-074 |
| 61 | `CLAUDE-FINAL-SCRIPTAUDIT-054-tokyo-deploy-support-long-tail-audit.md` | audit | read-only | HIGH | Q-071 Tokyo deploy/support 长尾脚本逐个审计；11 个脚本全部 ACTIVE-DEPLOY-PROTECTED，无 archive candidates | 后续 Q-075/Q-076 |
| 62 | `CLAUDE-FINAL-SCRIPTAUDIT-055-verify-runtime-long-tail-audit.md` | audit | read-only | MEDIUM/HIGH | Q-075 verify_runtime 长尾脚本逐个审计；9 个脚本全部 protected，7 个 ACTIVE-RUNTIME-PROTECTED、2 个 ACTIVE-DEPLOY-PROTECTED，无 archive candidates | 后续 Q-077/Q-078 |
| 63 | `CLAUDE-FINAL-SCRIPTAUDIT-056-next-attempt-fresh-active-observation-long-tail-audit.md` | audit | read-only | MEDIUM/HIGH | Q-076 next_attempt/fresh/active_observation 长尾审计；18 个脚本分类，9 active-runtime、2 dry-run、3 verification-dep、1 decision、3 archive-prep；覆盖 Q-072 | 后续 Q-079/Q-080/Q-081 |
| 64 | `CLAUDE-FINAL-DECISIONPACK-057-fresh-authorization-fixture-classification.md` | decision-pack | read-only | MEDIUM | Q-080 fresh authorization fixture 分类决策；推荐 Option B，当前临时保留为 ACTIVE-VERIFICATION-DEPENDENCY，Q-061/Q-062 后再复评 | 后续 Q-082；Q-081 排除此 fixture |
| 65 | `CLAUDE-FINAL-SCRIPTAUDIT-058-remaining-runtime-long-tail-audit.md` | audit | read-only | MEDIUM/HIGH | Q-073 remaining runtime 长尾脚本逐个审计；65 个脚本分类，46 active-runtime、1 dry-run、2 safety-proof、2 codex-guarded、14 archive-prep；完成 176 顶层 scripts 逐个审计闭环 | 后续 Q-083~Q-088 |
| 66 | `CLAUDE-FINAL-DECISIONPACK-059-first-real-submit-shared-infrastructure-decision.md` | decision-pack | read-only | HIGH | Q-087 first-real-submit shared infrastructure 决策包；确认 29 个顶层 importers + 4 个 replay importers + 8 个测试引用，推荐 Option C 分阶段迁移，当前仅 output-only | 后续 T-059-A~F；mainline 后或显式授权再实施 |
| 67 | `CLAUDE-FINAL-MANIFEST-060-script-cleanup-execution-manifest.md` | manifest | read-only | HIGH | Q-089 script cleanup execution manifest；汇总 23 个来源报告，定义 29 个 DO-NOT-BULK-TOUCH、10 个 archive batches、14 个 decision-required、14 个 hard stops 和 future-091~108 后续建议 | 作为 post-mainline script slimming handoff |
| 68 | `CLAUDE-FINAL-CHECKLIST-061-archive-batch-preconditions-checklist.md` | checklist | read-only | HIGH | Q-090 archive batch preconditions checklist；为 10 个 archive batches 生成逐批 read-only preflight 命令、pass/fail、hard stop、post-move tests，并修正 Batch J 为 7 scripts | 作为归档执行前检查手册 |
| 69 | `CLAUDE-FINAL-TASKPACK-062-archive-execution-taskcards.md` | task-cards | read-only | HIGH | TASKPACK-062 archive execution task-card pack；将 MANIFEST-060 / CHECKLIST-061 收束为 18 张未来草案卡，覆盖 ACTIVE_SCRIPT_MAP、CODEX-GUARDED headers、10 个 archive batches、T-059-A~F shared infra 迁移链 | 作为 post-mainline 草案库；暂不正式入队 |
| 70 | `CLAUDE-FINAL-ARCHAUDIT-063-domain-boundary-state-mainline-audit.md` | architecture-audit | read-only | HIGH | ARCHAUDIT-063 domain boundary/state mainline/semantic slimming audit；记录 28 项架构债发现，最高优先级为 readmodels float、console_models float、reconciliation_lock SQLite、bnb bridge dict、mi001/bnb 遗留语义 | 作为 post-mainline architecture slimming evidence |
| 71 | `CLAUDE-FINAL-QATASKPACK-064-architecture-slimming-test-cards.md` | qa-task-cards | read-only | HIGH | QATASKPACK-064 architecture slimming QA task-card pack；把 ARCHAUDIT-063 转成 12 张 post-mainline 测试/扫描任务卡，覆盖 Decimal/string、console_models、reconciliation_lock、bnb bridge、mi001/bnb、personal_campaign、domain purity、Owner-language、dict/Any 等 | 作为 post-mainline QA 草案库；暂不正式入队 |
| 72 | `CLAUDE-FINAL-MODULEMAP-065-application-boundary-dependency-audit.md` | architecture-audit | read-only | HIGH | MODULEMAP-065 application boundary dependency audit；绘制模块依赖与巨型文件地图，确认 5 个 5000+ 行文件、10 项跨层依赖、8 个候选提取边界和 3 个未来架构选项 | 作为 post-mainline module-boundary slimming evidence |
| 73 | `CLAUDE-FINAL-DECISIONPACK-066-module-boundary-slimming-options.md` | decision-pack | read-only | HIGH | DECISIONPACK-066 module-boundary slimming options；基于 ARCHAUDIT/QATASKPACK/MODULEMAP 给出 3 个 post-mainline 架构瘦身选项、非绑定推荐 Option A、受影响文件矩阵、阶段路线、go/no-go gate 和回滚策略 | 作为 Codex 后续架构决策输入 |
| 74 | `CLAUDE-FINAL-INTAKEPACK-067-post-mainline-slimming-intake-sprint.md` | intake-pack | read-only | HIGH | INTAKEPACK-067 post-mainline slimming intake sprint；将 DECISIONPACK-066 Option A 转成 3 个 intake sprint、12 张未来任务骨架、Entry Criteria、RACI、go/no-go gates、风险与回滚策略 | 作为 post-mainline intake planning artifact；暂不正式入队 |
| 75 | `CLAUDE-FINAL-HANDOFFPACK-068-token-burn-artifact-governance-handoff.md` | handoff-pack | read-only | HIGH | HANDOFFPACK-068 token-burn 产物治理交接包；整合 063~067 五份报告为一个 post-mainline intake/控制面，明确已知事实 vs 推荐、治理边界（draft IDs/QA 卡/Sprint 骨架不入正式队列）、Entry Criteria、风险登记簿、Operator/Claude 交接规则和验证命令 | 作为 post-mainline 架构瘦身治理交接入口 |
| 76 | `CLAUDE-FINAL-GOVAUDIT-069-token-burn-artifact-governance-integrity-audit.md` | governance-audit | read-only | LOW | GOVAUDIT-069 token-burn 产物治理完整性审计；验证文件计数、编号连续性、JSON 解析、INDEX/NEXT_QUEUE 一致性、正式队列不变量、draft-ID 边界、元数据漂移；`formal_queue_update=false`，不添加新正式 Q ID | 作为后续治理审计基线 |
| 77 | `CLAUDE-FINAL-DIFFREVIEW-070-current-mainline-diff-source-readiness-risk-review.md` | diff-review | read-only | P3 | DIFFREVIEW-070 deploy-channel readonly probe fallback diff 审查；5 文件 223 行变更，4 项 P3 发现（scope 突变、双包缺失测试、critical 列表、硬编码 scope），无 P0/P1，mainline_safe=true | 作为 mainline controller 风险参考 |
| 78 | `CLAUDE-FINAL-QATASKPACK-071-deploy-channel-fallback-regression-test-cards.md` | qa-task-cards | read-only | P3 | QATASKPACK-071 deploy-channel fallback 回归测试卡；将 DIFFREVIEW-070 的 4 项 P3 发现转为 5 张未来 QA 卡（DCHF-071-A~E），覆盖双包缺失、scope 显式行为、非关键 status 不变量、scope 一致性、Owner 语言中文不变量；`formal_queue_update=false`，不添加正式 Q ID | 作为 post-mainline deploy-channel 回归测试草案库；暂不正式入队 |
| 79 | `CLAUDE-FINAL-PUBAUDIT-072-token-burn-publication-boundary-audit.md` | publication-audit | read-only | LOW | token-burn 发布边界审计；确认脏工作树仅限 output/ 内文件，无 mainline 源码污染，89 正式 Q- 节不变量保持，12/12 JSON 块解析通过，068-071 全部已表示；`formal_queue_update=false`，不添加新 Q ID | 作为后续 staging 前检查基线 |
| 80 | `CLAUDE-FINAL-REFAUDIT-073-token-burn-reference-integrity-audit.md` | ref-audit | read-only | LOW | token-burn 引用完整性审计；验证 INDEX/NEXT_QUEUE 文件引用、孤儿检测、近产物表示、陈旧计数修正；`formal_queue_update=false`，不添加新 Q ID | 作为后续治理审计基线 |
| 81 | `CLAUDE-FINAL-SECRETAUDIT-074-token-burn-sensitive-publication-safety-audit.md` | security-audit | read-only | P3 | token-burn 敏感信息与发布安全审计；扫描 82 个 Markdown 文件的 API key/secret/env 内容/live payload/变异命令/绝对路径/webhook/JSON 负载；0 P0/P1/P2、4 P3（服务端路径）；15/15 JSON 块解析通过；旧版清理命令已改为非执行占位说明；`formal_queue_update=false`，不添加新 Q ID | 作为发布前安全检查基线 |
| 82 | `CLAUDE-FINAL-TASKGRAPH-075-next-queue-dependency-and-parallelism-map.md` | taskgraph | read-only | LOW | 正式队列依赖与并行地图；89 个 Q- section 分组为 5 类（Safe Now 6 / Safe After Mainline 40 / Decision Required 14 / Do Not Touch 4），识别 4 条关键依赖链、8 个推荐执行波次、12 项风险；`formal_queue_update=false`，不添加新 Q ID | 作为 post-mainline 执行调度参考 |
| 83 | `CLAUDE-FINAL-READINESS-076-next-queue-execution-readiness-gates.md` | readiness-gate | read-only | LOW | 正式队列执行就绪门控审计；89 个 Q- section 分为 6 类（Review-Only Now 2 / Output-Only Ready 24 / Blocked by Mainline 51 / Blocked by Codex 11 / Do Not Run Current 4 / Blocked by Pub Hygiene 2；含 5 个重叠项），8 个波次 go/no-go 门控（Wave 0 仅可 review，不授权实施/提交），14 项风险；`formal_queue_update=false`，不添加新 Q ID | 作为 post-mainline 执行调度门控参考 |
| 84 | `CLAUDE-FINAL-CONSISTENCY-077-taskgraph-readiness-alignment-audit.md` | consistency-audit | read-only | LOW | TASKGRAPH-075 / READINESS-076 / INDEX / NEXT_QUEUE 一致性审计；89 正式 Q- section 不变量保持，0 P0/P1/P2 after Codex wording fix、5 P3，draft 边界完整，review-only 语言一致性确认；`formal_queue_update=false`，不添加新 Q ID | 作为后续治理审计基线 |
| 85 | `CLAUDE-FINAL-CONTROLBRIEF-078-post-mainline-governance-control-brief.md` | control-brief | read-only | LOW | Post-mainline 治理控制简报；压缩 TASKGRAPH-075/READINESS-076/CONSISTENCY-077/INDEX/NEXT_QUEUE 为主控制器 ready 控制面；89 正式 Q- section 不变量保持，Wave 0 REVIEW-ONLY，recommendation_is_binding=false，8 波次全部 NO-GO（除 Wave 0）；`formal_queue_update=false`，不添加新 Q ID | 作为主控制器 post-mainline 治理入口 |
| 86 | `INDEX.md` | index | read-only | LOW | token-burn 报告总索引 | 持续补齐 |
| 87 | `NEXT_QUEUE.md` | index/queue | read-only | LOW | token-burn 后续任务队列和 resume prompt | 持续补齐 |
| 88 | `CLAUDE-FINAL-QUEUEGUARD-079-review-only-authorization-drift-audit.md` | authorization-drift-audit | read-only | P3 | review-only 授权漂移审计；扫描 INDEX/NEXT_QUEUE/TASKGRAPH-075/READINESS-076/CONSISTENCY-077/CONTROLBRIEF-078 的陈旧执行语言、wave 授权漂移、draft ID 泄漏；初始 3 项 P2 已由 Codex 修复（READINESS-076 §6.1 与 CONSISTENCY-077 §4.3），当前 0 P0/P1/P2、7 项 P3；drift_fixed_count=3；`formal_queue_update=false`，不添加新 Q ID | 作为后续治理审计基线 |
| 89 | `CLAUDE-FINAL-ISOLATION-080-mainline-interference-worktree-boundary-audit.md` | isolation-audit | read-only | P3 | mainline 干扰隔离与 worktree 边界审计；确认当前可见 non-output modified count=0，token-burn 输出状态条目=68，`docs/current/**`、`src/**`、`tests/**`、`scripts/**`、`deploy/**` 等继续隔离为主链路/其他窗口所有；`formal_queue_update=false`，不添加新 Q ID | 作为 token-burn 线程继续运行时的主链路隔离基线 |
| 90 | `CLAUDE-FINAL-ARTIFACTHEALTH-081-token-burn-artifact-health-refresh.md` | artifact-health-audit | read-only | P3 | token-burn 产物健康刷新；记录 Claude 081 worker 未产出文件后由 Codex 收口，确认当前 90 Markdown、22 JSON blocks、89 正式 Q 段、0 重复、0 草案标题泄漏；`formal_queue_update=false`，不添加新 Q ID | 作为继续 output-only token-burn 的结构健康基线 |
| 91 | `CLAUDE-FINAL-ROADMAPXWALK-082-token-burn-roadmap-crosswalk.md` | roadmap-crosswalk | read-only | P1 | token-burn 到 MAIN_CONTROL_ROADMAP 的路线图映射；覆盖 12 个 roadmap tracks，明确 P0 支持面、P1 Owner Console / handoff 风险、P2 historical debt / LLM assistance 用途，以及 forbidden misuses；Claude 超时但已写出文件，Codex 修正计数为 91 Markdown / 23 JSON blocks；`formal_queue_update=false`，不添加新 Q ID | 作为主控制器把 token-burn 报告接回 roadmap 的只读交叉索引 |
| 92 | `CLAUDE-FINAL-DIFFREVIEW-083-runtime-dry-run-audit-chain-current-diff-review.md` | diff-review | read-only | P1 | `scripts/runtime_dry_run_audit_chain.py` 瞬时 diff review；Claude 审查到 207 insertions / 1 deletion 的 non-executing prepare auto bridge fixture/scenario，安全不变量 PASS，0 P0、1 P1、2 P2、2 P3；Codex 复核时当前脚本 diff 已为空；`formal_queue_update=false`，不添加新 Q ID | 作为主链路 dry-run audit chain 窗口 diff 的 review-only 证据 |
| 93 | `CLAUDE-FINAL-SOURCERISK-084-post-mainline-source-risk-watchlist.md` | source-risk-watchlist | read-only | P1 | post-mainline 源码风险 watchlist；Claude 084 超时未落盘后由 Codex 按同一任务卡 output-only 收口，压缩 ARCHAUDIT-063 / MODULEMAP-065 / DECISIONPACK-066 / INTAKEPACK-067 / ROADMAPXWALK-082 / DIFFREVIEW-083 为 10 项 watchlist、6 项语义瘦身顺序、7 项 drift/risk findings；确认 93 Markdown / 25 JSON blocks / 89 正式 Q 段；`formal_queue_update=false`，不添加新 Q ID | 作为主线后语义瘦身和源码清债的 review-only watchlist |
| 94 | `CLAUDE-FINAL-CHARPLAN-085-post-mainline-characterization-test-plan.md` | characterization-test-plan | read-only | P1 | post-mainline characterization-first 测试计划；Claude 085 正常落盘，基于 SOURCERISK-084 / ARCHAUDIT-063 / QATASKPACK-064 / MODULEMAP-065 / INTAKEPACK-067 生成 12 个候选 characterization checks，覆盖 Decimal/string、console_models、domain purity、reconciliation_lock SQLite、bnb bridge fact shape、legacy vocabulary、Owner terminology、dict/Any density、common pipe boundary、readmodel response shape、coverage gap、goal-status projection；确认 94 Markdown / 26 JSON blocks / 89 正式 Q 段；`formal_queue_update=false`，不添加新 Q ID | 作为主线后“先特征化、后瘦身”的测试规划入口 |
| 95 | `CLAUDE-FINAL-SCORECARD-086-system-sorting-progress-scorecard.md` | scorecard | read-only | P1 | 系统梳理进度评分卡；Claude 086 正常落盘，把 Codex 约 70% 判断拆成 7 维加权模型：inventory/risk 85、queue/governance 90、characterization readiness 55、semantic clarity 70、cleanup readiness 65、actual code slimming 10、mainline/live closure 60；加权分 62，解释为“理解/规划约 77.5%，执行/闭环约 41.7%”；确认 95 Markdown / 27 JSON blocks / 89 正式 Q 段；`formal_queue_update=false`，不添加新 Q ID | 作为 Owner/Codex 判断系统梳理进度和剩余工作比例的 review-only 仪表盘 |
| 96 | `CLAUDE-FINAL-CHARCARDS-087-post-mainline-characterization-taskcards.md` | task-cards | read-only | P1 | post-mainline characterization task-card pack；Claude 087 API 超时未落盘后由 Codex 按同一任务卡 output-only 收口，基于 CHARPLAN-085 生成 12 张 CARD-087-01~12 草案卡和 6 波执行计划，覆盖 Decimal/string、console_models、domain purity、reconciliation_lock SQLite、bnb bridge fact shape、legacy vocabulary、Owner terminology、dict/Any density、common pipe boundary、readmodel response shape、coverage gap、goal-status projection；确认 96 Markdown / 28 JSON blocks / 89 正式 Q 段；`formal_queue_update=false`，不添加新 Q ID | 作为主线后 characterization tests/scanners 的未来任务卡草案库 |
| 97 | `CLAUDE-FINAL-CHARREADINESS-088-characterization-taskcard-readiness-audit.md` | readiness-audit | read-only | P1 | characterization task-card readiness audit；Claude 088 正常落盘，复核 CARD-087-01~12 的 scope/allowed-forbidden/verification/source-risk/mainline-safety/concurrency/preconditions，确认 3 张 first-wave ready（CARD-087-01/02/03）、0 张等待 Codex 决策、2 张需要 fixture prep（CARD-087-05/10），并给出 5-wave 执行建议；确认 97 Markdown / 29 JSON blocks / 89 正式 Q 段；`formal_queue_update=false`，不添加新 Q ID | 作为主线后 characterization task-card 分发前的 readiness gate |
| 98 | `CLAUDE-FINAL-FIRSTWAVE-089-characterization-first-wave-handoff.md` | handoff | read-only | P1 | characterization first-wave handoff；Claude 089 正常落盘，将 CHARREADINESS-088 的 first-wave-ready 卡压成 3 个未来 worker packets：FW-089-A/CARD-087-01 readmodels Decimal/string、FW-089-B/CARD-087-02 console_models type contract、FW-089-C/CARD-087-03 domain purity import scanner；包含未来 allowed files、forbidden files、step-by-step work、minimum assertions、verification commands、done when、hard stop 和 parallelism；确认 98 Markdown / 30 JSON blocks / 89 正式 Q 段；`formal_queue_update=false`，不添加新 Q ID | 作为主线后第一波 characterization workers 的 handoff 包 |
| 99 | `CLAUDE-FINAL-FIRSTWAVEPREFLIGHT-090-characterization-first-wave-preflight-checklist.md` | preflight-checklist | read-only | P1 | characterization first-wave preflight checklist；Claude 090 正常落盘，为 FW-089-A/B/C 三个未来 worker packets 定义启动前门控、文件边界、pre-run checks、future verification command、expected evidence、abort conditions、rollback note 和 post-run evidence capture；确认 99 Markdown / 31 JSON blocks / 89 正式 Q 段；`formal_queue_update=false`，不添加新 Q ID | 作为主线后第一波 characterization workers 执行前的 preflight gate |
| 100 | `CLAUDE-FINAL-MILESTONE-091-token-burn-100-artifact-snapshot.md` | milestone-snapshot | read-only | P1 | token-burn 100 artifact snapshot；Claude 091 正常落盘，汇总 100 个 Markdown / 32 个 JSON block / 89 个正式 Q 的治理里程碑，整理 8 个已组织领域、8 个 ready-but-not-authorized 项、mainline protection boundary、下一步 Claude token 最佳用途和 handoff notes；明确 SCORECARD-086 的系统梳理口径（约 70% 文档覆盖、加权 62、实际代码瘦身 10%）和 085→087→088→089→090 first-wave characterization chain；`formal_queue_update=false`，不添加新 Q ID | 作为 token-burn lane 的 100 产物里程碑交接快照 |
| 101 | `CLAUDE-FINAL-FIRSTWAVEDRAFTS-092-characterization-first-wave-test-draft-pack.md` | test-draft-pack | output-only | P1 | first-wave characterization test draft pack；Claude 092 worker 超时未落盘后由 Codex 按同一边界 output-only 收口，将 FW-089-A/B/C 与 PFC-090-A/B/C 转成 3 个未来测试草案：runtime readmodel Decimal contract、console_models type contract、domain purity import scanner；包含 3 个 future target files、11 个草案测试用例、3 个 fenced Python skeleton、readiness table、JSON `firstwavedrafts_092_summary`；确认 expected 101 Markdown / 33 JSON blocks / 89 正式 Q 段；`formal_queue_update=false`，不添加新 Q ID | 作为主线后 first-wave characterization tests 的代码草案审查包；当前不授权实现、测试、部署、清理、stage、commit 或 push |
| 102 | `CLAUDE-FINAL-FIRSTWAVEFIXTUREMAP-093-characterization-first-wave-fixture-import-map.md` | fixture-import-map | output-only | P1 | first-wave characterization fixture/import map；Claude 093 worker 超时未落盘后由 Codex 按同一边界 output-only 收口，为 FW-089-A/B/C 精确映射 future imports、fixture object shape、field list、assertion focus、likely failure modes、Codex review notes；只读 AST 扫描确认 `src/domain/**` 当前 forbidden-prefix imports 仅 2 个已知 logger 例外（`matching_engine.py:28`、`risk_calculator.py:14`）；确认 expected 102 Markdown / 34 JSON blocks / 89 正式 Q 段；`formal_queue_update=false`，不添加新 Q ID | 作为主线后 first-wave characterization tests 落地前的 fixture/import 审查基线；当前不授权实现、测试、部署、清理、stage、commit 或 push |
| 103 | `CLAUDE-FINAL-FIRSTWAVEEXECPLAN-094-characterization-first-wave-execution-plan.md` | execution-plan | output-only | P1 | characterization first-wave execution plan；Claude 094 正常落盘，将 085→087→088→089→090→092→093 链条压成未来 3 步执行顺序：先 FW-089-B console_models type contract，再 FW-089-A readmodels Decimal/string，再 FW-089-C domain purity scanner；补充 EO-1~EO-5 abort conditions、no-current-authorization statement 和 JSON `firstwaveexecplan_094_summary`；确认 expected 103 Markdown / 35 JSON blocks / 89 正式 Q 段；`formal_queue_update=false`，不添加新 Q ID | 作为主线后 first-wave characterization worker 调度顺序；当前不授权实现、测试、部署、清理、stage、commit 或 push |
| 104 | `CLAUDE-FINAL-FIRSTWAVECARDS-095-characterization-first-wave-codex-taskcards.md` | codex-taskcard-drafts | output-only | P1 | characterization first-wave Codex task-card drafts；Claude 095 worker 超时未落盘后由 Codex 按同一边界 output-only 收口，基于 094 顺序生成 3 张未来可签发任务卡草案：FW-089-B console_models type contract、FW-089-A runtime readmodel Decimal contract、FW-089-C domain purity import scanner；每张卡含 Task ID/Goal/Why/Allowed/Forbidden/Requirements/Tests/Done When/Hard Stop/Parallelism/Evidence；确认 expected 104 Markdown / 36 JSON blocks / 89 正式 Q 段；`formal_queue_update=false`，不添加新 Q ID | 作为主线后 Codex 重新签发 first-wave characterization workers 的草案包；当前不授权实现、测试、部署、清理、stage、commit 或 push |
| 105 | `CLAUDE-FINAL-FIRSTWAVEEVIDENCE-096-characterization-first-wave-evidence-template.md` | evidence-template | output-only | P1 | characterization first-wave evidence template；Claude 096 正常落盘，定义未来 FW-089-B/FW-089-A/FW-089-C worker 完成后的 shared evidence packet、per-worker checklists、Codex acceptance decision table（ACCEPT/NEEDS_FIX/HARD_STOP/DEFER）和 post-run handoff format；Codex 修正 FW-089-C 文件名为 `tests/unit/test_domain_purity_imports.py` 并对齐 forbidden import prefixes；确认 expected 105 Markdown / 37 JSON blocks / 89 正式 Q 段；`formal_queue_update=false`，不添加新 Q ID | 作为主线后 first-wave characterization tests 的验收证据模板；当前不授权实现、测试、部署、清理、stage、commit 或 push |
| 106 | `CLAUDE-FINAL-FIRSTWAVEGATE-097-characterization-first-wave-go-no-go-gate.md` | go-no-go-gate | output-only | P1 | characterization first-wave Go/No-Go gate；Claude 097 正常落盘，为未来 FW-089-B→FW-089-A→FW-089-C 定义 entry criteria、progression criteria、S-1~S-8 stop criteria、code slimming 前 Codex decision checklist 和 no-current-authorization statement；确认 expected 106 Markdown / 38 JSON blocks / 89 正式 Q 段；`formal_queue_update=false`，不添加新 Q ID | 作为主线后 first-wave characterization tests 开跑/推进/停止的门控表；当前不授权实现、测试、部署、清理、stage、commit 或 push |
| 107 | `CLAUDE-FINAL-FIRSTWAVESLIMBRIDGE-098-characterization-to-slimming-decision-bridge.md` | slimming-decision-bridge | output-only | P1 | characterization-to-slimming decision bridge；Claude 098 正常落盘，将未来 FW-089-B/FW-089-A/FW-089-C evidence outcomes 映射到 PROCEED_TO_DECIMAL_STRING_REFACTOR、PROCEED_TO_DOMAIN_IMPORT_CLEANUP、HOLD_FOR_MORE_CHARACTERIZATION、HARD_STOP 四类决策；列出仍禁止触碰的 readmodel/console/domain/reconciliation/FinalGate/Operation Layer 区域；确认 expected 107 Markdown / 39 JSON blocks / 89 正式 Q 段；`formal_queue_update=false`，不添加新 Q ID | 作为主线后 first-wave evidence 到实际 code slimming 授权之间的决策桥；当前不授权实现、测试、部署、清理、stage、commit 或 push |
| 108 | `CLAUDE-FINAL-FIRSTWAVESLIMCARDS-099-characterization-to-slimming-taskcard-drafts.md` | slimming-taskcard-drafts | output-only | P1 | characterization-to-slimming task-card drafts；Claude 099 正常落盘，将 FIRSTWAVESLIMBRIDGE-098 的四类决策转成 4 张未来草案卡：Decimal/string readmodel+console model refactor planning、domain import cleanup planning、additional characterization fallback、hard-stop escalation packet；每张卡含 Trigger/Goal/Why/Allowed/Forbidden/Requirements/Verification/Done When/Hard Stop/Evidence Required；确认 expected 108 Markdown / 40 JSON blocks / 89 正式 Q 段；`formal_queue_update=false`，不添加新 Q ID | 作为 first-wave evidence 被 Codex 接受后的后续 slimming/hold/escalation 草案源；当前不授权实现、测试、重构、清理、stage、commit 或 push |
| 109 | `CLAUDE-FINAL-FIRSTWAVEREADINESS-100-characterization-first-wave-readiness-bundle.md` | readiness-bundle | output-only | P1 | characterization first-wave readiness bundle；Claude 100 正常落盘并由 Codex 修正 JSON artifact_id，汇总 092~099 八份产物为单一 Codex 接手入口，包含 source map、FW-089-B/A/C readiness state、FW-089-B minimal start packet、evidence acceptance checklist、slimming decision continuation summary；确认 expected 109 Markdown / 41 JSON blocks / 89 正式 Q 段；`formal_queue_update=false`，不添加新 Q ID | 作为主线后启动 first-wave characterization 的单页 readiness bundle；当前不授权实现、测试、重构、清理、stage、commit 或 push |

---

## 2. 跨报告发现矩阵

| 主题 | 相关报告 | 发现摘要 | 严重度 | 状态 |
|------|---------|---------|--------|------|
| **Owner-facing 语言泄漏** | AUDIT-001, UICARDS-005 | owner-runtime-console 合规（0 违规）；trading-console 62+ HIGH 违规 | HIGH | 等 Codex 决定 trading-console 定位 |
| **运行时安全 / stale facts / idempotency** | AUDIT-002, TESTCARDS-004, CODETRACE-008 | 7 项安全发现；stale freshness 不阻塞 Operation Layer 确认；idempotency repo 可为 None | MEDIUM | 等 mainline 后补充测试和 Codex 修复 |
| **StrategyGroup handoff 完整性** | HANDOFFQA-007, HANDOFFCARDS-006, HANDOFFQA-030 | 当前 5 组 boundary PASS；SOR-001 模式不一致仍为 P1；source_commit / handoff-level review vocabulary / signal Owner mapping 仍为 P2 | P1 | 先处理 Q-011，再决定 Q-026 |
| **SOR-001 conditional mode** | HANDOFFQA-007, CODETRACE-008, DECISIONPACK-009 | handoff.json 说 `armed_observation`，index/priority 说 `conditional_armed_observation`；runtime 无 session-window gating | P1 | DECISIONPACK-009 推荐 Option B（collapse to armed_observation） |
| **review outcome vocabulary** | HANDOFFQA-007, CODETRACE-008, DECISIONPACK-009 | 后端 emit `promote/revise/park`；board contract 定义 `保留/调整/暂停/停用/待复盘`；无映射层 | P2 | DECISIONPACK-009 推荐 Option C（文档映射表） |
| **agent/Claude 指令权威清理** | DOC-DEBT-001, CLEANUP-PLAN-001, REVIEW-002 | 27 文件已重写（Wave 1）；8 个 quarantined 文件待处理 | MEDIUM | Wave 1 已应用；Wave 2 待 mainline 后 |
| **deletion/consolidation 候选** | DEBT-001 | 940MB 非源码质量；35 个 domain 文件链；9 个旧 SQLite repo；config_manager vs config/ | HIGH | 等 mainline 后分 6 wave 执行 |
| **runtime semantics slimming** | ARCHDEBT-037 | `trading_console.py` 8,116 行、`brc_operation_layer.py` 6,843 行、36 个 runtime_execution domain 文件、189 个 scripts、personal_campaign / mi001 / bnb 遗留路径需要分层清理 | HIGH | 后续执行 Q-028~Q-035 |
| **script active-map / staleness** | SCRIPTAUDIT-039 | 176 个顶层 scripts + 15 个 replay recovery；当前权威活跃脚本只有 7 个，其他多为 proof/rehearsal/audit/research clusters；exchange/credential/profile/core-import scripts 需单独安全分类 | HIGH | 后续执行 Q-037~Q-046 |
| **runtime_official proof chain** | SCRIPTAUDIT-040 | 17 个 `runtime_official_*` 构成 RTF-081~091 proof chain；dry-run chain 覆盖逻辑 shape 但不完全覆盖 API endpoint exercise；`submit_disabled_smoke_from_handoff` 为 active dependency，gateway/submit/finalize 3 类为 safety-sensitive | HIGH | Codex 决策后再归档候选 |
| **build_runtime packet builders** | SCRIPTAUDIT-041 | 19 个 `build_runtime_*` 中 1 个 deploy protected、12 个当前 packet builder surface、5 个 first-real-submit compat wrapper、2 个 ExchangeGateway/ReconciliationService connected decision-required | HIGH | Q-040 classification complete；后续归档/保留需 Codex 决策 |
| **seed profile/GKS seeders** | SCRIPTAUDIT-042 | 6 个 `seed_*.py` 中 `seed_tiny_live_profile.py` 为 live-capable active profile 且缺少强 Owner 守卫；`seed_gks_state.py` 无 dry-run 且直接写 GKS；3 个 testnet-only seeder 可归档但需迁移 imports | HIGH | Q-041 classification complete；后续 Q-047~Q-049 |
| **probe/brc credential/auth/exchange scripts** | SCRIPTAUDIT-043 | 10 个 `probe_*`/`brc_*` 中 `probe_trend_execute_server_readiness.py` 具备真实 execute POST 能力，`brc_record_scoped_runtime_safety_clearance.py` 写 PG safety metadata，Tokyo probe 与 Owner smoke 为 protected surfaces | HIGH | Q-042 classification complete；后续 Q-050~Q-052 |
| **runtime_live vs resume dispatcher** | SCRIPTAUDIT-044 | 11 个 `runtime_live_*` 中 bootstrap/position monitor/signal routing/selector 不应归档；continuation/operator/supervisor/shadow-planning/standalone enablement 多数被 dispatcher/dry-run 当前链路覆盖 | HIGH | Q-044 classification complete；后续 Q-053~Q-054 |
| **Codex-owned core script imports** | SCRIPTAUDIT-045 | 18 个 scripts 触及 AGENTS.md Codex-owned core modules；`owner_authorized_bnb_close.py`、`runtime_owner_reduce_only_close_flow.py`、`recover_runtime_exchange_*_projection.py`、`probe_exchange_credential_preflight.py` 为高风险 guard-required/decision-required | HIGH | Q-045 classification complete；后续 Q-055~Q-057 |
| **high-risk core-touching guard map** | DECISIONPACK-046 | 5 个高风险脚本全部 KEEP-PROTECTED / CODEX-GUARDED；不得进入 bulk cleanup/archive/comment wave；任何变更需 per-script Codex task card 和 targeted tests | HIGH | Q-055 complete；后续进入 ACTIVE_SCRIPT_MAP 或单脚本任务 |
| **runtime_official proof stub interfaces** | SCRIPTAUDIT-047 | RTF-085/087/088 为最敏感 proof 合约，编码 OrderLifecycleService、ExchangeGateway.place_order、PositionProjectionService.project_entry_fill、post-submit finalize/reconciliation/budget settlement 接口形状 | MEDIUM | Q-056 complete；后续 Q-058~Q-059 |
| **core refactor proof checklist** | CHECKLIST-048 | 将 RTF-085/087/088 定义为 core refactor strong-gate proof；覆盖 OrderLifecycleService、ExchangeGateway、OrderPlacementResult、PositionProjectionService、post-submit finalize、reconciliation read model | MEDIUM/HIGH | Q-058 complete；进入 ACTIVE_SCRIPT_MAP / future task cards |
| **runtime_official proof archive preservation** | DECISIONPACK-049 | runtime_official proof 归档必须保留 RTF id、原路径、endpoint coverage gap、stub/interface contract、safety labels；submit_disabled_smoke active dependency 不归档，RTF-085/087/088 需 Codex 决策 | MEDIUM | Q-059 complete；进入 ACTIVE_SCRIPT_MAP / future archive task |
| **runtime_dry_run proof dependency migration** | SCRIPTAUDIT-050 | dry-run chain 仅直接依赖 `runtime_official_submit_disabled_smoke_from_handoff.py` 这 1 个 proof script；`runtime_current_persisted_source_disabled_smoke_pipeline.py` 与 `verify_runtime_official_submit_action_time_bridge.py` 是独立 consumers | MEDIUM | Q-060 complete；后续 Q-061/Q-062 max-1 |
| **consolidated active script map** | SCRIPTAUDIT-051 | 176 个顶层 scripts 被合并到 ACTIVE-RUNTIME、ACTIVE-DEPLOY、ACTIVE-DRY-RUN、PROTECTED-SAFETY-PROOF、CODEX-GUARDED、DECISION-REQUIRED、ARCHIVE-PREP、DO-NOT-BULK-TOUCH 分类；Q-078 已并入 9 个 verify_runtime/related verifier individual classifications | HIGH | Q-063/Q-078 complete；后续 Q-064/Q-065/Q-066 / Q-077 |
| **script cleanup wave plan** | TASKPACK-052 | 将 consolidated script map 转成 Wave 0~6 的 post-acceptance 执行顺序与 Q-067~Q-073 task cards，默认 max-1 并保留 mainline acceptance output-only 边界 | HIGH | Q-067 complete；后续 Q-068~Q-073 |
| **ACTIVE_SCRIPT_MAP promotion draft** | SCRIPTMAP-053 | 将 SCRIPTAUDIT-051 / TASKPACK-052 转成 docs-current-ready 草案；明确当前不是 authority，`docs/current/ACTIVE_SCRIPT_MAP.md` 缺失且只能在 mainline acceptance 后创建 | HIGH | Q-068 complete；后续 Q-074 |
| **Tokyo deploy/support long-tail audit** | SCRIPTAUDIT-054 | 11 个 `tokyo_runtime_governance` deploy/support 脚本逐个审计，全部有近期活动和测试覆盖；execute 类为 HIGH remote-mutation risk，probe 为 LOW-MEDIUM remote-read risk | HIGH | Q-071 complete；Tokyo cluster 无 archive candidate |
| **verify_runtime long-tail audit** | SCRIPTAUDIT-055 | 9 个 `verify_runtime_*`/related verification 脚本逐个审计；7 个 ACTIVE-RUNTIME-PROTECTED、2 个 ACTIVE-DEPLOY-PROTECTED；无 archive candidate，`action_time_bridge` 修正为有测试覆盖 | MEDIUM/HIGH | Q-075 complete；后续 Q-077/Q-078 |
| **next_attempt / fresh / active_observation long-tail audit** | SCRIPTAUDIT-056 | 18 个 `runtime_next_attempt_*` / `runtime_fresh_*` / `runtime_active_observation_*` 脚本逐个审计；9 个 ACTIVE-RUNTIME-PROTECTED、2 个 ACTIVE-DRY-RUN-AUDIT、3 个 ACTIVE-VERIFICATION-DEPENDENCY、1 个 DECISION-REQUIRED、3 个 ARCHIVE-PREP；Q-076 覆盖 Q-072 | MEDIUM/HIGH | Q-076 complete；后续 Q-079/Q-080/Q-081 |
| **fresh authorization fixture classification** | DECISIONPACK-057 | `runtime_fresh_authorization_official_handoff_fixture.py` 决策为 Option B：Q-061/Q-062 完成前临时保留为 ACTIVE-VERIFICATION-DEPENDENCY；不纳入 Q-081 批量归档 | MEDIUM | Q-080 complete；后续 Q-082 |
| **remaining runtime long-tail audit** | SCRIPTAUDIT-058 | 65 个 remaining runtime/top-level scripts 逐个审计；46 个 ACTIVE-RUNTIME-PROTECTED、1 个 ACTIVE-DRY-RUN-AUDIT、2 个 PROTECTED-SAFETY-PROOF、2 个 CODEX-GUARDED、14 个 ARCHIVE-PREP；新增 5 个 DO-NOT-BULK-TOUCH | MEDIUM/HIGH | Q-073 complete；后续 Q-083~Q-088 |
| **first-real-submit shared infrastructure** | DECISIONPACK-059 | `runtime_first_real_submit_api_flow.py` 是 24 行 wrapper 但承载 29 个顶层 importers、4 个 replay importers、8 个测试引用；推荐 Option C：先保护、再建立 helper、再分波迁移，当前不改 `scripts/**` | HIGH | Q-087 decision pack complete；T-059-A~F 待 mainline 后或显式授权 |
| **script cleanup execution manifest** | MANIFEST-060 | 将 SCRIPTAUDIT/DECISIONPACK/TASKPACK/SCRIPTMAP 收束为 post-mainline 执行清单；包含 10 个 archive batches、14 个 hard stops、max-1 wave table、JSON `manifest_summary` 和 Codex review checklist；Codex 已修正 Batch J 为 7 scripts | HIGH | Q-089 complete；Q-090 已落地为 CHECKLIST-061 |
| **archive batch preconditions checklist** | CHECKLIST-061 | 为 Batch A~J 生成归档前 read-only preflight 检查、pass/fail、hard stop、post-move test 建议；补充 mandatory non-Python reference sweep，避免 `--type py` 漏掉 docs/frontend/workflow refs | HIGH | Q-090 complete；future-091~108 可基于此拆正式执行卡 |
| **archive execution task-card pack** | TASKPACK-062 | 将归档和 shared infra 后续工作整理为 18 张草案卡；明确 archive/move task max-1、shared-infra migration max-1，避免和主链路验收并发冲突 | HIGH | TASKPACK-062 complete；draft IDs 091-108 暂留在报告内，不作为 NEXT_QUEUE 正式条目 |
| **domain boundary / state mainline architecture debt** | ARCHAUDIT-063 | 只读审计 domain 纯度、float 金融字段、dict/Any 参数面、SQLite/JSON 过渡存储、mi001/bnb/personal_campaign 胶水和测试缺口；生成 28 项发现与 top-10 post-mainline cleanup queue | HIGH | ARCHAUDIT-063 complete；需要 Codex 清理授权后再拆执行卡 |
| **architecture slimming QA task pack** | QATASKPACK-064 | 将 ARCHAUDIT-063 的 28 项发现转成 12 张未来测试/扫描卡；核心/桥接/存储卡明确 max-1，纯扫描卡可在全局 max-3 内分发，JSON `qa_taskpack_summary.formal_queue_update=false` | HIGH | QATASKPACK-064 complete；QA-064-01~12 留在报告内，不作为 NEXT_QUEUE 正式条目 |
| **module boundary dependency map** | MODULEMAP-065 | 基于当前代码行数与导入扫描，整理 Top 20 巨型文件、10 项跨层依赖、8 个候选提取边界和 3 个瘦身架构选项；推荐增量特征化优先，所有实现 post-mainline / Codex clearance | HIGH | MODULEMAP-065 complete；暂不正式入队 |
| **module boundary slimming options** | DECISIONPACK-066 | 将 MODULEMAP-065 收束为 3 个架构瘦身选项；推荐 Option A 但标记 `recommendation_is_binding=false`，所有选项需 mainline 后或 Codex approval；包含 affected file matrix、phase roadmap、go/no-go gates、hard stops | HIGH | DECISIONPACK-066 complete；暂不正式入队 |
| **post-mainline slimming intake sprint** | INTAKEPACK-067 | 将 DECISIONPACK-066 非绑定 Option A 转成 Sprint 0/1/2 intake 计划；要求 P0 闭环完成或 Owner/Codex 明确暂停后才能启动，包含 12 张任务骨架和 max-3 / max-1 并发规则 | HIGH | INTAKEPACK-067 complete；暂不正式入队 |
| **token-burn 产物治理交接** | HANDOFFPACK-068 | 整合 063~067 五份报告为一个 post-mainline 治理交接包；明确已知事实 vs 推荐、治理边界（draft IDs/QA 卡/Sprint 骨架不入正式队列）、Entry Criteria、风险登记簿、Operator/Claude 交接规则；`formal_queue_update=false`，不添加 Q-091~108/QA-064-01~12/S0/S1/S2 到 NEXT_QUEUE | HIGH | HANDOFFPACK-068 complete；作为 post-mainline 架构瘦身治理交接入口 |
| **token-burn 产物治理完整性审计** | GOVAUDIT-069 | 验证 78 个 .md 文件计数、编号连续性、9+1 个 JSON 块全部解析通过、INDEX/NEXT_QUEUE 一致性、89 个正式 Q- 节无重复无遗漏、draft-ID 边界无泄漏、3 处元数据漂移已修正 | LOW | GOVAUDIT-069 complete；作为后续治理审计基线 |
| **deploy-channel fallback 回归测试卡** | QATASKPACK-071 | 将 DIFFREVIEW-070 的 4 项 P3 发现转为 5 张未来 QA 卡（DCHF-071-A~E）；覆盖双包缺失 ready_empty、scope/source_scope 显式行为、deploy_channel 非关键 status 不变量、硬编码 scope 一致性、Owner 语言中文不变量；`formal_queue_update=false`，不添加正式 Q ID | P3 | QATASKPACK-071 complete；QA 卡留在报告内，不作为 NEXT_QUEUE 正式条目 |
| **本地产物 / 未跟踪输出治理** | LOCALARTIFACTS-015, ARTIFACTAUDIT-014 | 648MB / 717 个未跟踪本地产物；live-config.env 仅识别存在、不读取；output/claude-token-burn 已安全提交 | MEDIUM | 等 Owner 授权后分阶段清理或更新 .gitignore |
| **selected-scope gating** | RUNTIMEREVIEW-016, RUNTIMEREVIEW-018, RUNTIMEREVIEW-019, TESTCARD-017 | resume-dispatcher scope gating 全面评审；PASS；P2 blocker_class 分类 + P3 测试缺口 | P2 | 等 Codex 决定 blocker_class 分类（hard_safety_stop vs deployment_issue） |
| **real-order readiness 闭环** | RUNTIMEREVIEW-021~028, TASKCARD-023 | producer false-positive、consumer propagation、frontend language、matrix submit-blocker closure 已复核；P1 已关闭；01fa0b77 覆盖 submit-blocker families | P2 | 后续做 matcher 注释、budget/protection family 统一、main controller 处理 smoke diff |
| **dry-run audit source-readiness / Owner Console UI** | RUNTIMEREVIEW-029, RUNTIMEREVIEW-031, RUNTIMEREVIEW-032, RUNTIMEREVIEW-033, RUNTIMEREVIEW-035, RUNTIMEREVIEW-036 | fb2c6f71 要求当前 11 项 dry-run sub-check；47c159f5 additive 暴露 producer summary；1e58c62b 暴露 readmodel checks；frontend card Owner 语言 PASS；当前完整前端 diff 存在 desktop nav hover P1，且 System footer 直接展示内部 read-model id 为新 P1 | P1 | 后续执行 Q-025 / Q-027 |
| **Owner-language readmodel contract tests** | ARCHDEBT-037, QA-038, RUNTIMEREVIEW-036 | `frontend_contract` 只声明不泄漏，尚未验证 label 字段；`owner_console_source_readiness` 当前被 real-backend smoke 当作可见文本；需要 backend test-only 与 frontend smoke/source 映射拆分 | P1 | 后续执行 Q-032 / Q-036 |
| **敏感信息与发布安全审计** | SECRETAUDIT-074 | 扫描 82 个 token-burn Markdown 文件；0 P0/P1/P2、4 P3（服务端路径）；无 API key/secret/env 内容/live payload/webhook 泄漏；15/15 JSON 块解析通过；旧版清理命令已改为非执行占位说明；89 正式 Q- 节不变量保持；`formal_queue_update=false` | P3 | 作为发布前安全检查基线；更广泛发布前建议对本地/服务端路径做轻量红线化 |
| **review-only 授权漂移审计** | QUEUEGUARD-079 | 扫描 INDEX/NEXT_QUEUE/TASKGRAPH-075/READINESS-076/CONSISTENCY-077/CONTROLBRIEF-078 的陈旧执行语言、wave 授权漂移、draft ID 泄漏；初始 3 项 P2 已由 Codex 修复（READINESS-076 §6.1 门控矩阵与 CONSISTENCY-077 §4.3 覆盖缺口），当前 0 P0/P1/P2、7 项 P3；drift_fixed_count=3；draft 边界完整；recommendation_is_binding=false；89 正式 Q- 节不变量保持；`formal_queue_update=false` | P3 | 作为后续授权语义漂移审计基线 |
| **主链路干扰隔离审计** | ISOLATION-080 | 当前可见 non-output modified count=0；token-burn lane 仅更新 output/claude-token-burn；`docs/current/**`、`src/**`、`tests/**`、`scripts/**`、`deploy/**`、`owner-runtime-console/src/**`、`.github/**` 继续隔离为主链路/其他窗口所有；不授权实现、测试、部署、清理、stage、commit 或 push | P3 | 作为后续 token-burn 输出-only 工作的边界基线 |
| **token-burn 产物健康刷新** | ARTIFACTHEALTH-081 | Claude 081 worker 未产出文件后由 Codex output-only 收口；当前 90 Markdown、22 JSON blocks、89 正式 Q 段、0 重复、0 草案标题泄漏；无 P0/P1/P2，4 项 P3 均为产物治理/历史元数据/worker 悬挂层面 | P3 | 作为继续 output-only 审计前的结构健康基线 |
| **token-burn roadmap crosswalk** | ROADMAPXWALK-082 | 将 token-burn 报告映射回 MAIN_CONTROL_ROADMAP 的 12 个 track；明确 P0 报告只能支持审计/理解/调度，不能替代 fresh signal 后真实闭环；P1 仍有 SOR-001 mode、Owner Console hover、内部 read-model id 暴露等已知未决项；P2 historical debt / LLM assistance 只能 post-mainline 或 review-only | P1 | 作为后续清债、瘦身和 LLM 协作的路线图交叉索引 |
| **runtime dry-run audit chain 瞬时 diff review** | DIFFREVIEW-083 | 审查 `runtime_dry_run_audit_chain.py` 中 non-executing prepare auto bridge 相关窗口 diff；安全不变量 PASS，无 P0；P1 为 scenario_count=13 合并后测试确认，P2 为 goal-status projection 与跨 StrategyGroup 覆盖；Codex 复核时当前脚本 diff 已为空 | P1 | 作为主控制器 review-only 参考，不授权 token-burn lane 修改脚本或运行测试 |
| **post-mainline source-risk watchlist** | SOURCERISK-084 | 将 063/065/066/067/082/083 的架构债、模块边界、路线图和瞬时 diff review 压缩为源码风险 watchlist；优先级集中在 readmodel 金融字段、Console readmodel/API fan-in、common runtime pipe 边界、goal-status projection drift、dict/Any、transition storage、domain purity、script coupling 和 legacy vocabulary；Claude 084 worker 超时未落盘，由 Codex output-only 收口 | P1 | 作为主线完成后语义瘦身入口；当前不授权实现、测试、部署、清理、stage、commit 或 push |
| **post-mainline characterization test plan** | CHARPLAN-085 | 将 SOURCERISK-084 和架构瘦身报告转成 12 个 characterization-first 检查计划；要求 Decimal/string 先于 money-field refactor、Owner 是 supervisor、evidence packet 是 audit artifact、StrategyGroup 复用 common runtime pipe、无 per-strategy FinalGate/Operation Layer fork；并发规则为全局 <=3，core/bridge/storage max-1 | P1 | 作为主线后安全清债的 tests/scanners 规划；当前不授权实现、测试、部署、清理、stage、commit 或 push |
| **system sorting progress scorecard** | SCORECARD-086 | 将“系统梳理约 70%”拆成 7 维可复核评分；文档/理解/规划维度约 77.5%，执行/闭环维度约 41.7%，实际代码瘦身仅 10%；指出 70% 适合描述 documentation coverage，不适合描述 implementation progress | P1 | 作为后续向 Owner 解释系统梳理进度和剩余工作重心的仪表盘；当前不授权实现、测试、部署、清理、stage、commit 或 push |
| **post-mainline characterization task cards** | CHARCARDS-087 | 将 CHARPLAN-085 的 12 个 checks 转成 CARD-087-01~12 草案任务卡，每张卡含 Goal/Why/Allowed/Forbidden/Requirements/Verification/Done When/Hard Stop/Parallelism，并按 6 波安排 max-3 与 core/bridge/storage max-1 | P1 | 作为主线后 characterization tests/scanners 的 draft task-card library；当前不授权实现、测试、部署、清理、stage、commit 或 push |
| **characterization taskcard readiness audit** | CHARREADINESS-088 | 对 CARD-087-01~12 做 readiness gate 审计，确认 CARD-087-01/02/03 是最安全 first wave，CARD-087-05/10 需要 fixture prep，CARD-087-11 必须作为 synthesis 最后执行；0 张卡等待 Codex 决策，但所有卡仍需 post-mainline 或显式暂停授权 | P1 | 作为未来分发 characterization cards 前的执行门控；当前不授权实现、测试、部署、清理、stage、commit 或 push |
| **characterization first-wave handoff** | FIRSTWAVE-089 | 将 CARD-087-01/02/03 细化为 FW-089-A/B/C 三个未来 worker packets，明确新测试文件路径建议、最小断言、验证命令和 hard stops；这三项可在主线后按全局 max-3 并行执行 | P1 | 作为主线后第一波 characterization workers 的交接包；当前不授权实现、测试、部署、清理、stage、commit 或 push |
| **characterization first-wave preflight** | FIRSTWAVEPREFLIGHT-090 | 为 FW-089-A/B/C 定义未来执行前 checklist：mainline/pause gate、Codex task card、允许文件模式、禁止路径、abort conditions、证据捕获和 rollback note | P1 | 作为主线后第一波 characterization workers 开跑前的 preflight gate；当前不授权实现、测试、部署、清理、stage、commit 或 push |
| **token-burn 100 artifact milestone** | MILESTONE-091 | 汇总 100 个 token-burn Markdown 产物的组织成果、ready-but-not-authorized 项、主线保护边界和下一步 token 使用策略；强调文档治理成熟但实际代码瘦身仍约 10% | P1 | 作为当前 token-burn lane 的里程碑交接快照；当前不授权实现、测试、部署、清理、stage、commit 或 push |
| **characterization first-wave test drafts** | FIRSTWAVEDRAFTS-092 | 将 FW-089-A/B/C 的未来 characterization tests 压成可审查代码草案包：readmodel Decimal/string current behavior、console_models Pydantic type contract、domain purity scanner；草案只在 Markdown 中，不写 `tests/**` | P1 | 作为主线后第一波测试落地前的 Codex review 输入；当前不授权实现、测试、部署、清理、stage、commit 或 push |
| **characterization first-wave fixture/import map** | FIRSTWAVEFIXTUREMAP-093 | 为 092 的三份未来测试草案补齐 imports、fixtures、field list、assertion focus 和失败模式；只读 AST 扫描确认 domain 跨层 import 当前只有 2 个 logger 例外 | P1 | 作为主线后第一波 tests 实施前的 fixture/import 基线；当前不授权实现、测试、部署、清理、stage、commit 或 push |
| **characterization first-wave execution plan** | FIRSTWAVEEXECPLAN-094 | 将 first-wave characterization 链条压成未来执行顺序：FW-089-B → FW-089-A → FW-089-C，并列出顺序理由和 EO-1~EO-5 abort conditions | P1 | 作为主线后 first-wave worker 调度顺序；当前不授权实现、测试、部署、清理、stage、commit 或 push |
| **characterization first-wave Codex task-card drafts** | FIRSTWAVECARDS-095 | 将 094 顺序转成三张未来 Codex 可重签发任务卡草案，补齐 Allowed/Forbidden/Requirements/Tests/Done When/Hard Stop/Parallelism/Evidence 字段 | P1 | 作为主线后 Codex 派发 first-wave characterization workers 的草案源；当前不授权实现、测试、部署、清理、stage、commit 或 push |
| **characterization first-wave evidence template** | FIRSTWAVEEVIDENCE-096 | 为未来 FW-089-B/FW-089-A/FW-089-C 执行结果定义 shared evidence packet、per-worker checklist、Codex ACCEPT/NEEDS_FIX/HARD_STOP/DEFER 决策表和 post-run handoff format | P1 | 作为主线后 first-wave tests 的验收证据模板；当前不授权实现、测试、部署、清理、stage、commit 或 push |
| **characterization first-wave Go/No-Go gate** | FIRSTWAVEGATE-097 | 为 FW-089-B→FW-089-A→FW-089-C 定义 entry/progression/stop criteria，以及 code slimming 前 Codex decision checklist | P1 | 作为主线后 first-wave tests 开跑、推进和停止的门控表；当前不授权实现、测试、部署、清理、stage、commit 或 push |
| **characterization to slimming decision bridge** | FIRSTWAVESLIMBRIDGE-098 | 将 FW-089-B/A/C evidence outcomes 映射到 Decimal/string refactor、domain import cleanup、more characterization 或 hard stop；列出仍 forbidden 的 code areas | P1 | 作为主线后从 characterization evidence 进入 code slimming 授权的决策桥；当前不授权实现、测试、部署、清理、stage、commit 或 push |
| **characterization to slimming task-card drafts** | FIRSTWAVESLIMCARDS-099 | 将 098 的四类决策转成 future task-card drafts：Decimal/string planning、domain cleanup planning、more characterization fallback、hard-stop escalation | P1 | 作为 first-wave evidence acceptance 后的后续任务草案源；当前不授权实现、测试、重构、清理、stage、commit 或 push |
| **characterization first-wave readiness bundle** | FIRSTWAVEREADINESS-100 | 将 092~099 八份产物压成一个 future Codex 接手入口，包含 source map、ready workers、FW-089-B start packet、evidence checklist、slimming continuation summary | P1 | 作为主线后启动 first-wave characterization 的单页 readiness bundle；当前不授权实现、测试、重构、清理、stage、commit 或 push |

---

## 3. 权威文档变更 / 应用映射

### 3.1 当前权威文档已变更

| 文档 | 变更来源 | 变更内容 |
|------|---------|---------|
| `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md` | DOCFIX-010 | 新增 Review Outcome Vocabulary Mapping 小节（6 对映射） |
| `docs/current/AI_AGENT_CONSTRAINTS.md` | DOCFIX-010 | 新增 `hard_safety_stop`→`需要介入`、`review_only_warning`→`运行中` 映射 |
| `docs/current/strategy-group-handoffs/main-control-watcher-cadence.md` | DOCFIX-010 | 新增 Candidate Packet Freshness 是 watcher-side metadata 说明 |
| `docs/current/strategy-group-handoffs/main-control-conflict-policy.md` | DOCFIX-010 | 新增 stale facts 是 upstream status/enum 说明 |
| `.agents/skills/*/SKILL.md` (8 files) | CLEANUP-PLAN-001, REVIEW-002 | dead path 重写为当前权威链 |
| `.claude/commands/*.md` (10 files) | CLEANUP-PLAN-001, REVIEW-002 | dead path 重写为当前权威链 |
| `.claude/team/**` (9 files) | CLEANUP-PLAN-001, REVIEW-002 | dead path 重写为当前权威链 |

### 3.2 task card 来源报告

| 报告 | 产出的 task card |
|------|-----------------|
| AUDIT-001 | UIG-001 ~ UIG-008（via UICARDS-005） |
| AUDIT-002 | TESTCARD-001 ~ TESTCARD-007（via TESTCARDS-004） |
| TEST-MAP-001 | TESTCARD-004 ~ TESTCARD-007（via TESTCARDS-004） |
| HANDOFFQA-007 | HQ-001A ~ HQ-008B（via HANDOFFCARDS-006） |
| CODETRACE-008 | DECISIONPACK-TC-001 ~ TC-010（via DECISIONPACK-009） |
| DOC-DEBT-001 | CARD-002A ~ CARD-002C（via TASKPACK-003） |
| REVIEW-002 | CARD-001A ~ CARD-005D（via TASKPACK-003） |
| DEBT-001 | CARD-005A ~ CARD-005D（via TASKPACK-003） |

### 3.3 只读证据报告

| 报告 | 证据性质 |
|------|---------|
| AUDIT-001 | UI 术语泄漏证据（87 处，12 文件） |
| AUDIT-002 | 运行时安全红队证据（7 项发现，20+ 文件路径） |
| TEST-MAP-001 | 11 步运行时路径测试覆盖证据（297 test files scanned） |
| HANDOFFQA-007 | 5 StrategyGroup handoff 完整性证据（9 QA 卡执行结果） |
| CODETRACE-008 | handoff→runtime 代码消费追踪证据 |
| SCHEMA-DEBT-001 | 11 个 personal_campaign schema 使用证据 |
| LOCALARTIFACTS-015 | 未跟踪本地产物 metadata-only 清单和未来清理门控 |

### 3.4 被后续报告取代的报告

| 早期报告 | 被取代者 | 取代范围 |
|---------|---------|---------|
| AUDIT-001 的 task card 建议 | UICARDS-005 | UICARDS-005 提供了更完整的 8 卡治理方案 |
| AUDIT-002 的 task card 建议 | TESTCARDS-004 | TESTCARDS-004 将发现转化为 7 个可执行测试卡 |
| TEST-MAP-001 的 task card 建议 | TESTCARDS-004 + TASKPACK-003 | 合并为统一的测试卡和 task pack |
| HANDOFFQA-007 的 F-001/F-002 | CODETRACE-008 + DECISIONPACK-009 | CODETRACE 追踪到代码，DECISIONPACK 提供决策选项 |
| CLEANUP-PLAN-001 的执行计划 | REVIEW-002 | REVIEW-002 确认 Wave 1 已应用并评估安全性 |
| CODEX-CLEANUP-REVIEW-001 的 wave 建议 | TASKPACK-003 | TASKPACK-003 将建议转化为 5 组 14 个可执行 task card |

---

## 4. mainline acceptance 期间不触碰清单

| 类别 | 路径 |
|------|------|
| 运行时源码 | `src/**` |
| 测试 | `tests/**` |
| 脚本 | `scripts/**` |
| 部署 | `deploy/**` |
| 实盘配置 | `live-config.env`, `.env*` |
| Watcher/Tokyo | 任何 watcher 或 Tokyo 运维代码 |
| 交易所/凭证 | Exchange gateway, credentials, live profiles |
| owner-runtime-console 源码 | `owner-runtime-console/src/**` |
| quarantined agent 文件 | `.claude/AGENTIC-WORKFLOW-GUIDE.md`, `.claude/MCP-ORCHESTRATION.md`, `.claude/TEAM-SETUP-SUMMARY.md`, `.claude/team/QUICKSTART.md`, `.claude/team/QUICK-REFERENCE.md` |

---

## 5. 验证命令

```bash
# 确认所有报告文件存在
ls -la output/claude-token-burn/*.md | wc -l
# 预期: 88 (86 reports + INDEX.md + NEXT_QUEUE.md)

# 确认 INDEX.md 和 NEXT_QUEUE.md 已创建
ls -la output/claude-token-burn/INDEX.md output/claude-token-burn/NEXT_QUEUE.md

# 确认未修改其他文件
git status --short

# 确认 docs/current 已应用的变更仍在
rg 'promote.*保留|revise.*调整|park.*暂停|kill.*停用|pending.*待复盘' docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md
rg 'hard_safety_stop|review_only_warning' docs/current/AI_AGENT_CONSTRAINTS.md
```

---

*End of INDEX.*
