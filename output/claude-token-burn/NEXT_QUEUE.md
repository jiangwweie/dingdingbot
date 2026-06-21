# Claude Token-Burn 下一步任务队列

Generated: 2026-06-17
Task ID: CLAUDE-FINAL-INDEX-011
Mode: read-only queue — no file modifications except this report

---

## 队列总览

| 分组 | 数量 | 说明 |
|------|------|------|
| Safe Now / docs-only | 2 | 纯文档，零代码变更，可立即 review；执行/提交需主控制器另行授权 |
| Safe Now / output-only planning | 4 | 仅写 output/，不影响 mainline |
| Safe After Mainline Acceptance | 40 | mainline 完成后可安全分发 |
| Decision Required Before Implementation | 14 | 需 Codex 先做决策 |
| Do Not Touch During Mainline Acceptance | 4 | mainline 期间禁止触碰 |

---

## A. Safe Now / docs-only

### Q-001: Commit Agent Authority Cleanup Diff

| Field | Value |
|---|---|
| **Queue ID** | Q-001 |
| **Source report(s)** | TASKPACK-003 CARD-001A, REVIEW-002 |
| **Goal** | 提交 27 文件 agent 指令权威路径重写 |
| **Allowed files** | `.agents/skills/*/SKILL.md`, `.claude/commands/*.md`, `.claude/team/**`（已修改） |
| **Forbidden files** | `src/`, `tests/`, `scripts/`, `deploy/`, `live-config.env`, `.env*` |
| **Tests/verification** | `git diff HEAD --stat -- src/ tests/ scripts/ deploy/` 返回空；`grep -rn "docs/ops/" .agents/skills/ .claude/commands/ .claude/team/ --include="*.md" \| grep -v "Do not recreate"` 返回零 |
| **Risk level** | LOW |
| **Parallelism safety** | solo |

### Q-002: owner-runtime-console Anti-Regression Scanner

| Field | Value |
|---|---|
| **Queue ID** | Q-002 |
| **Source report(s)** | UICARDS-005 UIG-001, AUDIT-001 |
| **Goal** | 在 owner-runtime-console 的 visual:qa 门禁中加入禁止术语自动扫描 |
| **Allowed files** | `owner-runtime-console/scripts/visual-qa.ts`, `owner-runtime-console/package.json` |
| **Forbidden files** | `src/`, `tests/`, `scripts/`(backend), `deploy/`, `trading-console/`, `live-config.env`, `.env*` |
| **Tests/verification** | 当前代码库零违规；注入测试术语能被捕获 |
| **Risk level** | LOW |
| **Parallelism safety** | can-parallelize（与 Q-001 独立） |

---

## B. Safe Now / output-only planning

### Q-003: INDEX.md + NEXT_QUEUE.md（本任务）

| Field | Value |
|---|---|
| **Queue ID** | Q-003 |
| **Source report(s)** | INDEX.md 全部报告 |
| **Goal** | 创建 token-burn 报告索引和下一步任务队列 |
| **Allowed files** | `output/claude-token-burn/INDEX.md`, `output/claude-token-burn/NEXT_QUEUE.md` |
| **Forbidden files** | 所有其他文件 |
| **Tests/verification** | `ls output/claude-token-burn/INDEX.md output/claude-token-burn/NEXT_QUEUE.md`；`git status --short` 确认只改了这两个文件 |
| **Risk level** | NONE |
| **Parallelism safety** | solo |

### Q-020: Local Artifact Hygiene Audit（已完成）

| Field | Value |
|---|---|
| **Queue ID** | Q-020 |
| **Source report(s)** | CLAUDE-FINAL-LOCALARTIFACTS-015 |
| **Goal** | 对 `.playwright-cli/`、`local-archives/`、`output/`、`live-config.env` 做 metadata-only 未跟踪产物清单审计 |
| **Allowed files** | `output/claude-token-burn/CLAUDE-FINAL-LOCALARTIFACTS-015-untracked-artifact-hygiene-audit.md` |
| **Forbidden files** | `live-config.env` 内容、`.env*` 内容、`output/` artifact payload 内容、任何删除/移动/stage/commit/clean 操作 |
| **Tests/verification** | `du -sh .playwright-cli local-archives output`；`git status --short`；不读取 secret 内容 |
| **Risk level** | NONE（metadata-only） |
| **Parallelism safety** | solo |

### Q-089: Script Cleanup Execution Manifest（已完成）

| Field | Value |
|---|---|
| **Queue ID** | Q-089 |
| **Source report(s)** | SCRIPTAUDIT-039~058, DECISIONPACK-046/049/057/059, CHECKLIST-048, TASKPACK-052, SCRIPTMAP-053, INDEX.md, NEXT_QUEUE.md |
| **Goal** | 已完成：生成 post-mainline script slimming 执行 manifest，汇总 protected sets、archive batches、decision-required、hard stops、wave table、JSON `manifest_summary` 与 Codex review checklist |
| **Allowed files** | `output/claude-token-burn/CLAUDE-FINAL-MANIFEST-060-script-cleanup-execution-manifest.md` |
| **Forbidden files** | `src/**`, `tests/**`, `scripts/**`, `deploy/**`, `docs/current/**`, `.github/**`, `owner-runtime-console/**`, `live-config.env`, `.env*` |
| **Requirements** | 已满足：1) output-only；2) JSON 可解析；3) 10 个 archive batches；4) 14 个 decision-required；5) 14 个 hard stops；6) Q-090 已落地为 CHECKLIST-061；future-091~108 仍仅作为 manifest 内建议，未正式入队 |
| **Tests/verification** | JSON parse；`git diff --check`；top-level scripts=176；replay history current count=13；current Markdown total=86 |
| **Risk level** | NONE（output-only） |
| **Parallelism safety** | done |

### Q-090: Archive Batch Preconditions Checklist（已完成）

| Field | Value |
|---|---|
| **Queue ID** | Q-090 |
| **Source report(s)** | MANIFEST-060, SCRIPTAUDIT-039~058, DECISIONPACK-046/049/057/059, TASKPACK-052, SCRIPTMAP-053 |
| **Goal** | 已完成：为 MANIFEST-060 的 10 个 archive batches A~J 生成逐批 read-only preflight checklist，包括命令、pass/fail、hard stops、future post-move tests、allowed/forbidden files 和 max-1 并发约束 |
| **Allowed files** | `output/claude-token-burn/CLAUDE-FINAL-CHECKLIST-061-archive-batch-preconditions-checklist.md` |
| **Forbidden files** | `src/**`, `tests/**`, `scripts/**`, `deploy/**`, `docs/current/**`, `.github/**`, `owner-runtime-console/**`, `live-config.env`, `.env*` |
| **Requirements** | 已满足：1) output-only；2) `checklist_summary` JSON 可解析；3) batch_count=10；4) Batch J 修正为 7 scripts；5) 增加 mandatory non-Python reference sweep，避免 `--type py` 漏掉 docs/frontend/workflow refs；6) TASKPACK-062 已生成 18 张后续草案卡，但 draft IDs 091-108 暂不作为正式队列条目 |
| **Tests/verification** | JSON parse；`git diff --check`；Batch J files exist=7；current Markdown total=86；NEXT_QUEUE formal sections match mentions |
| **Risk level** | NONE（output-only） |
| **Parallelism safety** | done |

---

## C. Safe After Mainline Acceptance

### Q-004: Quarantine Header Cleanup (7 files)

| Field | Value |
|---|---|
| **Queue ID** | Q-004 |
| **Source report(s)** | TASKPACK-003 CARD-002A, CLEANUP-PLAN-001 Group D |
| **Goal** | 删除或重写 7 个 quarantined/superseded 文件的 CAUTION header，指向当前权威链 |
| **Allowed files** | `.claude/AGENTIC-WORKFLOW-GUIDE.md`, `.claude/MCP-ORCHESTRATION.md`, `.claude/TEAM-SETUP-SUMMARY.md`, `.claude/team/QUICKSTART.md`, `.claude/team/QUICK-REFERENCE.md`, `.agents/skills/agentic-workflow/README.md`, `.claude/skills/agentic-workflow/README.md` |
| **Forbidden files** | `src/`, `tests/`, `scripts/`, `deploy/`, `live-config.env`, `.env*`, 任何活跃运行时源码 |
| **Tests/verification** | `grep -rn "docs/canon/" <target files>` 返回零 |
| **Risk level** | LOW |
| **Parallelism safety** | can-parallelize |

### Q-005: Duplicate Skill Copy Alignment

| Field | Value |
|---|---|
| **Queue ID** | Q-005 |
| **Source report(s)** | TASKPACK-003 CARD-002B, REVIEW-002 Class 2 |
| **Goal** | 对齐 `.claude/skills/pua-skill/SKILL.md` 与已更新的 `.agents/skills/pua-skill/SKILL.md` |
| **Allowed files** | `.claude/skills/pua-skill/SKILL.md` |
| **Forbidden files** | `.agents/skills/pua-skill/SKILL.md`（已正确，不修改） |
| **Tests/verification** | `grep -n "docs/ops/" .claude/skills/pua-skill/SKILL.md` 返回零 |
| **Risk level** | LOW |
| **Parallelism safety** | can-parallelize |

### Q-006: Memory Authority Header Fix

| Field | Value |
|---|---|
| **Queue ID** | Q-006 |
| **Source report(s)** | TASKPACK-003 CARD-002C, REVIEW-002 Class 3 |
| **Goal** | 更新 `.claude/memory/project-core-memory.md` 读取规则从 `docs/canon/` 到 `docs/current/*`；更新 MEMORY.md 标题 |
| **Allowed files** | `.claude/memory/project-core-memory.md`, `.claude/memory/MEMORY.md` |
| **Forbidden files** | `.claude/memory/` 以外的任何文件 |
| **Tests/verification** | `grep -n "docs/canon/" .claude/memory/project-core-memory.md` 返回零 |
| **Risk level** | LOW |
| **Parallelism safety** | can-parallelize |

### Q-007: FinalGate Blocker Class Consolidated Test (TESTCARD-004)

| Field | Value |
|---|---|
| **Queue ID** | Q-007 |
| **Source report(s)** | TESTCARDS-004 TESTCARD-004, TEST-MAP-001 Step 8 |
| **Goal** | 为所有 6 个 FinalGate blocker class 编写综合测试（9 个测试用例） |
| **Allowed files** | `tests/unit/test_final_gate_all_blocker_classes.py`（新建） |
| **Forbidden files** | `src/**`, `deploy/`, `live-config.env`, `.env*` |
| **Tests/verification** | `python -m pytest tests/unit/test_final_gate_all_blocker_classes.py -v` |
| **Risk level** | CRITICAL（FinalGate 是最后安全屏障），但 tests-only 无源码变更 |
| **Parallelism safety** | can-parallelize |

### Q-008: Post-Submit Partial Fill + Reconciliation Test (TESTCARD-006)

| Field | Value |
|---|---|
| **Queue ID** | Q-008 |
| **Source report(s)** | TESTCARDS-004 TESTCARD-006, TEST-MAP-001 Step 10 |
| **Goal** | 为 partial fill 结算和 reconciliation mismatch 编写测试（8 个测试用例） |
| **Allowed files** | `tests/unit/test_post_submit_partial_fill_and_reconciliation.py`（新建） |
| **Forbidden files** | `src/**`, `deploy/`, `live-config.env`, `.env*` |
| **Tests/verification** | `python -m pytest tests/unit/test_post_submit_partial_fill_and_reconciliation.py -v` |
| **Risk level** | HIGH（结算错误导致预算漂移），但 tests-only |
| **Parallelism safety** | can-parallelize |

### Q-009: Notification / Review Outcome Test (TESTCARD-007)

| Field | Value |
|---|---|
| **Queue ID** | Q-009 |
| **Source report(s)** | TESTCARDS-004 TESTCARD-007, TEST-MAP-001 Step 11 |
| **Goal** | 为通知交付和 review outcome 传播编写测试（8 个测试用例） |
| **Allowed files** | `tests/unit/test_notification_and_review_propagation.py`（新建） |
| **Forbidden files** | `src/**`, `deploy/`, `live-config.env`, `.env*` |
| **Tests/verification** | `python -m pytest tests/unit/test_notification_and_review_propagation.py -v` |
| **Risk level** | MEDIUM（通知失败 = Owner 盲操作），但 tests-only |
| **Parallelism safety** | can-parallelize |

### Q-021: Real-Order Readiness Matcher Maintenance Pack

| Field | Value |
|---|---|
| **Queue ID** | Q-021 |
| **Source report(s)** | RUNTIMEREVIEW-021, RUNTIMEREVIEW-022, TASKCARD-023, RUNTIMEREVIEW-026, RUNTIMEREVIEW-027 |
| **Goal** | 将 real-order readiness blocker matching 从已关闭 P1 的状态推进到更清晰、可维护的 P2 清理状态 |
| **Allowed files** | `scripts/build_strategygroup_runtime_goal_status.py`, `tests/unit/test_strategygroup_runtime_goal_status.py`, `tests/unit/test_trading_console_readmodels.py`, `owner-runtime-console/scripts/smoke.mjs`, `owner-runtime-console/scripts/state-smoke.mjs` |
| **Forbidden files** | `deploy/`, `live-config.env`, `.env*`, watcher/Tokyo/exchange/network 操作 |
| **Requirements** | 1) 为 `_contains_blocker_family` 添加边界语义注释；2) 将 protection/budget blocker matching 统一到 family matcher；3) 增加 `symbol_*` / `side_*` negative tests；4) 增加 Owner Console readiness 文案 smoke assertion |
| **Tests/verification** | `python3 -m pytest tests/unit/test_strategygroup_runtime_goal_status.py tests/unit/test_trading_console_readmodels.py -k "source_readiness or goal_status" -q`; frontend smoke only after mainline acceptance and with explicit runtime-safe target |
| **Risk level** | P2（维护性 + 回归保护），不属于当前 live-safety blocker |
| **Parallelism safety** | max-1（涉及同一 readiness 链路，避免与主链路并发改同文件） |

### Q-025: Historical Dry-Run Artifact Compatibility Note

| Field | Value |
|---|---|
| **Queue ID** | Q-025 |
| **Source report(s)** | RUNTIMEREVIEW-029 |
| **Goal** | 文档化 `fb2c6f71` 之后 Owner Console dry-run audit source-readiness 对旧 artifact 的兼容性语义 |
| **Allowed files** | `docs/current/MAIN_CONTROL_ROADMAP.md` or `docs/current/OWNER_RUNTIME_CONSOLE_PRODUCT_PROJECTION_CONTRACT.md` |
| **Forbidden files** | `src/**`, `tests/**`, `deploy/**`, `live-config.env`, `.env*`, watcher/Tokyo/exchange/network 操作 |
| **Requirements** | 说明当前 11 项 dry-run required checks 是 current-pilot canonical vocabulary；旧 dry-run artifact 缺少新增 checks 时会显示 `审计演练需检查`，这表示 artifact stale/needs refresh，不等同于实盘安全绕过；`47c159f5` 新增的 `summary` / `required_checks` 是 additive exposure，不改变旧 artifact 降级语义 |
| **Tests/verification** | docs-only；`rg 'dry-run|审计演练|historical|artifact' docs/current/MAIN_CONTROL_ROADMAP.md docs/current/OWNER_RUNTIME_CONSOLE_PRODUCT_PROJECTION_CONTRACT.md` |
| **Risk level** | P2（避免旧证据被误读为新故障） |
| **Parallelism safety** | max-1（docs/current authority 文档，等 mainline acceptance 后处理） |

### Q-027: Owner Console Dry-Run Summary UI Hardening

| Field | Value |
|---|---|
| **Queue ID** | Q-027 |
| **Source report(s)** | RUNTIMEREVIEW-032, RUNTIMEREVIEW-033, RUNTIMEREVIEW-035, RUNTIMEREVIEW-036 |
| **Goal** | 收紧 Owner Console dry-run summary 前端消费、System footer 来源展示、导航样式与 smoke 稳定性注释：空 summary fallback、窄类型、fixture-coupling 注释、桌面导航 hover 恢复、内部 read-model id 中文映射 |
| **Allowed files** | `owner-runtime-console/src/types.ts`, `owner-runtime-console/src/api/ownerSourceReadiness.ts`, `owner-runtime-console/src/console/pages.tsx`, `owner-runtime-console/src/console/chrome.tsx`, `owner-runtime-console/scripts/smoke.mjs`, `owner-runtime-console/scripts/real-backend-smoke.mjs` |
| **Forbidden files** | `src/**`, `tests/**` backend, `deploy/**`, `live-config.env`, `.env*`, watcher/Tokyo/exchange/network 操作 |
| **Requirements** | 1) `summary` 存在但没有可渲染 rows 时显示轻量 Owner 文案或保持显式 fallback；2) 用窄 `DryRunAuditSummary` 类型替代裸 `Record<string, unknown>`；3) 在 smoke 中说明 `7 项通过` 断言绑定当前 fixture scenario count；4) 恢复 inactive desktop sidebar nav 的 hover background；5) 对齐 desktop/mobile active nav styling pattern；6) 将 `owner_console_source_readiness` 等内部 read-model id 映射为中文 Owner 来源标签，或明确放入详情/开发者信息而非主 footer；7) 说明 `waitForTimeout(250)` 仅是 `expectVisible` 后的 settling delay，主同步仍应依赖可观察条件；8) 修补 smoke forbidden-list 缺口，避免内部 `readiness` / read-model 标识绕过 Owner 语言检查 |
| **Tests/verification** | Frontend static/type checks and smoke only after mainline acceptance; do not start browser/dev server in token-burn audit lane |
| **Risk level** | P1/P2（P1 为当前前端 diff 的 hover affordance 回归与内部 read-model id Owner 展示；非 live-safety blocker） |
| **Parallelism safety** | max-1（涉及当前 Owner Console uncommitted/active diff） |

### Q-010: Handoff Read-Only QA Cards (Phase 1)

| Field | Value |
|---|---|
| **Queue ID** | Q-010 |
| **Source report(s)** | HANDOFFCARDS-006 HQ-001A~HQ-006A, HANDOFFQA-007 |
| **Goal** | 执行 9 个 read-only QA 卡：handoff 完整性、mode 对齐、RequiredFacts 覆盖、conflict policy 可测性、research boundary、provenance、gap matrix、Owner 术语映射 |
| **Allowed files** | `docs/current/strategy-group-handoffs/`（只读） |
| **Forbidden files** | `src/`, `tests/`, `scripts/`, `deploy/`, `live-config.env`, `.env*` |
| **Tests/verification** | 每个 QA 卡有独立验证命令（见 HANDOFFCARDS-006） |
| **Risk level** | LOW（只读审计） |
| **Parallelism safety** | can-parallelize（9 个 QA 卡相互独立） |

### Q-028: Split Trading Console Readmodel

| Field | Value |
|---|---|
| **Queue ID** | Q-028 |
| **Source report(s)** | ARCHDEBT-037 Q-ARCH-001 |
| **Goal** | 拆分 `src/application/readmodels/trading_console.py` 的 Owner Console / trading-console action / lifecycle / helper 职责，降低 8,116 行 readmodel 巨型文件风险 |
| **Allowed files** | `src/application/readmodels/trading_console.py`, `src/application/readmodels/*.py`, `tests/unit/test_trading_console_readmodels.py`, Owner Console smoke scripts（mainline 后） |
| **Forbidden files** | AGENTS.md 中列出的 Codex-owned core files、`deploy/**`, `live-config.env`, `.env*`, watcher/Tokyo/exchange 操作 |
| **Requirements** | 1) public API surface 不变；2) Owner-facing 与 developer/audit readmodel 责任边界清楚；3) 内部 gate/read-model id 不进入 Owner 主界面；4) 每次拆分保持小步、可回滚 |
| **Tests/verification** | `python3 -m pytest tests/unit/test_trading_console_readmodels.py -v`; frontend smoke only after mainline acceptance |
| **Risk level** | HIGH（语义收益高，merge 风险高） |
| **Parallelism safety** | max-1 |

### Q-029: Personal Campaign Legacy Path Audit / Archive

| Field | Value |
|---|---|
| **Queue ID** | Q-029 |
| **Source report(s)** | ARCHDEBT-037 Q-ARCH-002 |
| **Goal** | 审计并在安全时归档 `personal_campaign_*` 应用文件与 `src/domain/personal_campaign.py` |
| **Allowed files** | `src/application/personal_campaign_*.py`, `src/domain/personal_campaign.py`, archive README（如 Codex 批准归档） |
| **Forbidden files** | Codex-owned core files、`deploy/**`, `live-config.env`, `.env*`, watcher/Tokyo/exchange 操作 |
| **Requirements** | 1) 先证明 official runtime path 没有 active import；2) 若仍有 budget/admission/Operation Layer 依赖则只出报告不移动；3) 归档时写明 pre-StrategyGroup 语义 |
| **Tests/verification** | `rg 'personal_campaign' src/application src/domain tests`; targeted tests only after mainline acceptance |
| **Risk level** | MEDIUM |
| **Parallelism safety** | max-1 |

### Q-030: Domain Logger Boundary Fix

| Field | Value |
|---|---|
| **Queue ID** | Q-030 |
| **Source report(s)** | ARCHDEBT-037 Q-ARCH-003 |
| **Goal** | 移除 `src/domain/risk_calculator.py` 与 `src/domain/matching_engine.py` 对 `src.infrastructure.logger` 的依赖 |
| **Allowed files** | `src/domain/risk_calculator.py`, `src/domain/matching_engine.py`, relevant unit tests |
| **Forbidden files** | `src/infrastructure/logger.py`, Codex-owned core files、`deploy/**`, `live-config.env`, `.env*` |
| **Requirements** | 1) domain 不 import infrastructure；2) 不改变日志格式/目的地；3) 行为保持不变 |
| **Tests/verification** | `rg 'from src.infrastructure' src/domain/` 返回零；`python3 -m pytest tests/ -k 'risk_calculator or matching_engine' -v` |
| **Risk level** | LOW |
| **Parallelism safety** | can-parallelize after mainline |

### Q-031: Strategy-Specific Boundary Audit

| Field | Value |
|---|---|
| **Queue ID** | Q-031 |
| **Source report(s)** | ARCHDEBT-037 Q-ARCH-004 |
| **Goal** | 分类 `mi001_*`, `bnb_*`, `binance_*` 相关文件是 active-in-path / archive / boundary-commented，防止策略特例 fork common runtime pipe |
| **Allowed files** | `src/application/mi001_*.py`, `src/application/bnb_live_execution_bridge.py`, `src/domain/mi001_sol_pg_registration.py`, relevant `src/infrastructure/binance_*.py` |
| **Forbidden files** | Codex-owned core files、`src/infrastructure/exchange_gateway.py`, `deploy/**`, `live-config.env`, `.env*` |
| **Requirements** | 1) 每个文件有 active/legacy 分类；2) active 文件说明为何不是 candidate/auth/FinalGate/Operation Layer/finalize fork；3) stale 文件只在 Codex 批准后归档 |
| **Tests/verification** | `rg 'mi001|bnb_live' src/application src/domain src/infrastructure tests`; read-only core import audit first |
| **Risk level** | HIGH |
| **Parallelism safety** | max-1 |

### Q-032: Owner-Language Readmodel Contract Test

| Field | Value |
|---|---|
| **Queue ID** | Q-032 |
| **Source report(s)** | ARCHDEBT-037 Q-ARCH-005, AUDIT-001, RUNTIMEREVIEW-036, QA-038 |
| **Goal** | 增加 backend test-only Owner-facing readmodel 契约测试，断言 `owner-console-source-readiness` response 的 Owner label 字段不包含内部 gate/read-model 术语 |
| **Allowed files** | `tests/unit/test_owner_language_compliance.py`（新建）, `tests/unit/test_trading_console_readmodels.py`（仅复用 fixture pattern 时读取/少量辅助） |
| **Forbidden files** | `src/**`, `deploy/**`, `live-config.env`, `.env*` |
| **Requirements** | 1) 覆盖 `FinalGate`, `Operation Layer`, `RequiredFacts`, `candidate`, `authorization`, `preflight`, `proof`, `route`, `refId`, `blocker code`, `runtime grant`；2) 覆盖 `owner_console_source_readiness`, `runtime_dry_run_audit`, `read_model`, `source_readiness` 等 read-model id 直出；3) 只检查 Owner-facing label 字段：`owner_label`, `owner_summary.*`, `source_health.*.owner_label`, `strategy_groups[].owner_label`, `real_order_readiness.owner_label/detail`；4) 明确允许 `submit_blocking_keys`, `matrix[].key/detail`, `reason`, `scope`, `read_model` field name 作为 audit/detail/internal data；5) 加入 parametrized negative controls 证明注入 forbidden term 会失败；6) test-only，不改源码 |
| **Tests/verification** | `python3 -m pytest tests/unit/test_owner_language_compliance.py -v` |
| **Risk level** | HIGH（防回归价值高，test-only 风险低） |
| **Parallelism safety** | can-parallelize after mainline |

### Q-036: Frontend Forbidden-Term Coverage and Source Label Mapping

| Field | Value |
|---|---|
| **Queue ID** | Q-036 |
| **Source report(s)** | RUNTIMEREVIEW-036, QA-038 |
| **Goal** | 扩展 Owner Console smoke forbidden-list，并将 `read_model` / `projection.source` 内部 id 映射为中文 Owner 来源标签 |
| **Allowed files** | `owner-runtime-console/scripts/smoke.mjs`, `owner-runtime-console/scripts/real-backend-smoke.mjs`, `owner-runtime-console/src/api/ownerSourceReadiness.ts`, optional `owner-runtime-console/src/App.tsx` if sourceLabel mapping lives there |
| **Forbidden files** | `src/**`, backend `tests/**`, `deploy/**`, `live-config.env`, `.env*`, watcher/Tokyo/exchange/network 操作 |
| **Requirements** | 1) forbidden-list 覆盖 `readiness`, `owner_console_source_readiness`, `runtime_dry_run_audit` 等内部 id；2) `projection.source` / footer 来源必须是中文 Owner 标签或明确 mock label，不能是 snake_case read-model id；3) 移除或反转 real-backend smoke 中 `expectVisible(page, \"owner_console_source_readiness\")`；4) 保留 `waitForTimeout(250)` 作为 `expectVisible` 后 settling delay 的注释语义 |
| **Tests/verification** | Frontend smoke only after mainline acceptance; do not start browser/dev server in token-burn audit lane |
| **Risk level** | P1（当前 Owner footer 内部 id 泄漏） |
| **Parallelism safety** | max-1（触碰 active frontend diff） |

### Q-037: Stale-Candidate Archive - Backtest/CPM Research

| Field | Value |
|---|---|
| **Queue ID** | Q-037 |
| **Source report(s)** | SCRIPTAUDIT-039 |
| **Goal** | 在确认零 active import 后，将 backtest/CPM/TE005/TB001/RO001 research scripts 归档到 `scripts/archive/research/` 并写 README |
| **Allowed files** | `scripts/one_day_spot_trend_backtest.py`, `scripts/run_cpm1_2021_oos.py`, `scripts/run_cpm1_2022_oos.py`, `scripts/te005_import_pre2021_klines.py`, `scripts/te005_qa_pre2021_klines.py`, `scripts/analyze_tb001_long_regime_split.py`, `scripts/analyze_tb001_long_year_regime_cross.py`, `scripts/run_cpm_ro001_historical_experiment.py`, `scripts/run_cpm_ro001_regime_split_experiment.py`, `scripts/archive/research/README.md` |
| **Forbidden files** | `src/**`, `deploy/**`, `live-config.env`, `.env*`, watcher/Tokyo/exchange 操作 |
| **Requirements** | 1) 归档前确认 active runtime/import/docs 引用为零；2) README 标注 research-only / not active runtime；3) 不删除，仅移动归档 |
| **Tests/verification** | `rg 'run_cpm1_2021_oos|run_cpm1_2022_oos|one_day_spot_trend|te005_|analyze_tb001|run_cpm_ro001' src tests scripts --glob '*.py'` |
| **Risk level** | LOW |
| **Parallelism safety** | solo（file moves） |

### Q-038: replay_recovery_history README Boundary Marker

| Field | Value |
|---|---|
| **Queue ID** | Q-038 |
| **Source report(s)** | SCRIPTAUDIT-039 |
| **Goal** | 为 `scripts/replay_recovery_history/` 增加 README，标注为 historical first-real-submit proof archive |
| **Allowed files** | `scripts/replay_recovery_history/README.md`（新建） |
| **Forbidden files** | `src/**`, `deploy/**`, 其他 scripts |
| **Requirements** | README 必须写明 historical recovery material only、not active runtime、not deploy-referenced |
| **Tests/verification** | `rg 'historical|not active runtime|not deploy' scripts/replay_recovery_history/README.md` |
| **Risk level** | NONE |
| **Parallelism safety** | can-parallelize |

### Q-039: runtime_official Proof Script Classification

| Field | Value |
|---|---|
| **Queue ID** | Q-039 |
| **Source report(s)** | SCRIPTAUDIT-039, SCRIPTAUDIT-040 |
| **Goal** | 已完成分类：17 个 `runtime_official_*.py` proof scripts 中，`submit_disabled_smoke_from_handoff` 是 active dry-run dependency，`server_prepare_integration_proof` 是 shared proof infrastructure，`exchange_submit_boundary_proof`/`controlled_gateway_action_proof`/`post_submit_finalize_proof` 为 safety-sensitive boundary evidence，其余多为 archive candidates |
| **Allowed files** | `scripts/runtime_official_*.py` read-only, `output/claude-token-burn/` report |
| **Forbidden files** | `src/**`, `deploy/**`, file moves without approval, live-config/env |
| **Requirements** | 后续如需归档，必须先由 Codex 决策 API endpoint exercise gap 是否仍需保留；不得移动/重命名 `runtime_official_submit_disabled_smoke_from_handoff.py`，除非同步更新 `runtime_dry_run_audit_chain.py` import；safety-sensitive proof artifacts 必须标记 mock-only，不得作为真实执行证据 |
| **Tests/verification** | read-only `rg` / `git log` |
| **Risk level** | HIGH（含 exchange-boundary mock artifacts 与 active import dependency） |
| **Parallelism safety** | done / future archive task max-1 |

### Q-040: build_runtime Packet Builder Classification

| Field | Value |
|---|---|
| **Queue ID** | Q-040 |
| **Source report(s)** | SCRIPTAUDIT-039, SCRIPTAUDIT-041 |
| **Goal** | 已完成分类：19 个 `build_runtime_*.py` packet builders 中，1 个 deploy protected、12 个 protected packet builder surface、5 个 first-real-submit compat wrappers 为 archive candidates、2 个 post-close/reduce-only-close builder 因 `ExchangeGateway` / `ReconciliationService` 需 Codex 决策 |
| **Allowed files** | `scripts/build_runtime_*.py` read-only, `output/claude-token-burn/` report |
| **Forbidden files** | `src/**`, `deploy/**`, file moves without approval |
| **Requirements** | 后续如需归档，必须先处理 five first-real-submit compat wrappers 的测试 import 迁移；`build_runtime_post_close_followup_packet.py` 与 `build_runtime_reduce_only_close_owner_packet.py` 需 Codex 决定是否保留为 active packet builders 或移入 guarded archive；未来 `ACTIVE_SCRIPT_MAP.md` 应列出 12 个 protected packet builders |
| **Tests/verification** | read-only `rg` |
| **Risk level** | HIGH（含 exchange/reconciliation connected builders 与 test import compatibility） |
| **Parallelism safety** | done / future archive task max-1 |

### Q-041: seed Profile Seeder Safety Review

| Field | Value |
|---|---|
| **Queue ID** | Q-041 |
| **Source report(s)** | SCRIPTAUDIT-039, SCRIPTAUDIT-042 |
| **Goal** | 已完成分类：6 个 `seed_*.py` 中，`seed_tiny_live_profile.py` 是 live-capable active profile 且缺少强 Owner 守卫，`seed_gks_state.py` 直接写 PG GKS 且无 dry-run，3 个 testnet-only profile seeder 为 archive candidates 但存在测试/预实盘 seeder 常量 imports |
| **Allowed files** | `scripts/seed_*.py` read-only |
| **Forbidden files** | `src/**`, `deploy/**`, running any seed script, `live-config.env`, `.env*` |
| **Requirements** | 后续分为 Q-047/Q-048/Q-049；不得运行 seed；不得读取 env/secret；任何 live/profile/GKS mutation 都需 Codex 明确决策 |
| **Tests/verification** | read-only `nl`/`rg`；Claude read-only classification |
| **Risk level** | HIGH（含 live active profile seeder 与 safety-critical GKS mutation） |
| **Parallelism safety** | done / future mutation or archive task max-1 |

### Q-042: probe/brc Safety Review

| Field | Value |
|---|---|
| **Queue ID** | Q-042 |
| **Source report(s)** | SCRIPTAUDIT-039, SCRIPTAUDIT-043 |
| **Goal** | 已完成分类：10 个 `probe_*`/`brc_*` 中，Tokyo readonly probe 与 Owner Console smoke 为 protected，`probe_trend_execute_server_readiness.py` 具备 guarded real execute POST 能力，`brc_record_scoped_runtime_safety_clearance.py` 写 PG safety metadata，旧 BRC operator/SQLite/full-process probe 为 archive-prep candidates |
| **Allowed files** | `scripts/probe_*.py`, `scripts/brc_*.py` read-only |
| **Forbidden files** | `src/**`, `deploy/**`, running probe/brc scripts, `live-config.env`, `.env*` |
| **Requirements** | 后续分为 Q-050/Q-051/Q-052；不得运行 probe/brc 脚本；不得读取 env/secret；任何 execute-capable 或 PG safety mutation 脚本都需 Codex 明确决策 |
| **Tests/verification** | read-only Claude classification + `rg` |
| **Risk level** | HIGH（含 execute POST capability 与 PG safety metadata mutation） |
| **Parallelism safety** | done / future mutation or archive task max-1 |

### Q-043: ACTIVE_SCRIPT_MAP.md Creation

| Field | Value |
|---|---|
| **Queue ID** | Q-043 |
| **Source report(s)** | SCRIPTAUDIT-039, SCRIPTAUDIT-040, SCRIPTAUDIT-041, SCRIPTAUDIT-042, SCRIPTAUDIT-043, SCRIPTAUDIT-044 |
| **Goal** | 创建 `docs/current/ACTIVE_SCRIPT_MAP.md`，成为 scripts 权威地图 |
| **Allowed files** | `docs/current/ACTIVE_SCRIPT_MAP.md`（新建） |
| **Forbidden files** | `src/**`, `scripts/**` mutation, `deploy/**`, live-config/env |
| **Requirements** | 1) 列出 7 个 protected active scripts 和引用；2) 分类 remaining scripts；3) 标出 sensitive-boundary scripts；4) 引用 SCRIPTAUDIT-039~044；5) 将 seed seeder 分类纳入 profile/GKS mutation cluster；6) 将 probe/brc 分类纳入 credential/auth/exchange/PG-mutation cluster；7) 将 runtime_live 分成 protected/bootstrap/position/signal 与 archive-prep 链 |
| **Tests/verification** | `rg 'runtime_signal_watcher_tick.py|runtime_dry_run_audit_chain.py|build_strategygroup_runtime_goal_status.py' docs/current/ACTIVE_SCRIPT_MAP.md` |
| **Risk level** | LOW |
| **Parallelism safety** | max-1（依赖 Q-039~Q-042） |

### Q-044: runtime_live vs Resume Dispatcher Overlap Audit

| Field | Value |
|---|---|
| **Queue ID** | Q-044 |
| **Source report(s)** | SCRIPTAUDIT-039, SCRIPTAUDIT-044 |
| **Goal** | 已完成分类：11 个 `runtime_live_*.py` 中，`runtime_live_bootstrap_api_flow.py` 因 protected bootstrap import 需 active-utility 决策，`runtime_live_position_monitor.py` / `runtime_live_signal_routing_packet.py` / `runtime_live_strategy_signal_selector.py` 仍有独特 active surface，continuation/operator/supervisor/shadow-planning/standalone enablement 多数为 archive-prep candidates |
| **Allowed files** | `scripts/runtime_live_*.py`, `scripts/runtime_signal_watcher_resume_dispatcher.py` read-only |
| **Forbidden files** | `src/**`, `deploy/**`, running scripts |
| **Requirements** | 后续分为 Q-053/Q-054；不得运行 runtime_live/dispatcher 脚本；不得读取 env/secret；active/protected 与 archive-prep 必须分开处理 |
| **Tests/verification** | Claude read-only classification + `rg` |
| **Risk level** | HIGH（含 bootstrap API mutation flow、position monitor exchange read path、standalone enablement mutation script） |
| **Parallelism safety** | done / future archive or mutation task max-1 |

### Q-045: Scripts Codex-Owned Core Import Audit

| Field | Value |
|---|---|
| **Queue ID** | Q-045 |
| **Source report(s)** | SCRIPTAUDIT-039, SCRIPTAUDIT-045 |
| **Goal** | 已完成分类：18 个 scripts 触及 AGENTS.md Codex-owned core modules；`owner_authorized_bnb_close.py`、`runtime_owner_reduce_only_close_flow.py`、`recover_runtime_exchange_*_projection.py`、`probe_exchange_credential_preflight.py` 为高风险 guard-required/decision-required |
| **Allowed files** | `scripts/*.py` read-only, `output/claude-token-burn/` report |
| **Forbidden files** | `src/**`, `deploy/**`, running scripts |
| **Requirements** | 后续分为 Q-055/Q-056/Q-057；任何触及 core module 的脚本不得进入 bulk cleanup；高风险 exchange/order/recovery 脚本需 Codex guard |
| **Tests/verification** | Claude read-only classification + `rg` |
| **Risk level** | HIGH（含 order submit、exchange gateway、position/reconciliation mutation surfaces） |
| **Parallelism safety** | done / future guard or archive task max-1 |

### Q-046: Strategy-Specific Script Boundary Marking

| Field | Value |
|---|---|
| **Queue ID** | Q-046 |
| **Source report(s)** | SCRIPTAUDIT-039, ARCHDEBT-037 |
| **Goal** | 为 strategy-specific scripts 增加 boundary comments，说明它们不得 fork common runtime pipe |
| **Allowed files** | `scripts/analyze_mi001_bnb_sol_evidence_reviewability.py`, `scripts/run_bnb_live_case_forward_review_once.py`, `scripts/reset_bnb_testnet_daily_gate.py`, `scripts/inspect_bnb_final_gate_blockers_readonly.py`, `scripts/owner_authorized_bnb_close.py` |
| **Forbidden files** | `src/**`, `deploy/**`, running scripts |
| **Requirements** | header comment 写明 `STRATEGY-SPECIFIC`，不得 fork candidate/auth/FinalGate/Operation Layer/finalize from common runtime pipe |
| **Tests/verification** | `rg 'STRATEGY-SPECIFIC' <target scripts>` |
| **Risk level** | LOW（comment-only） |
| **Parallelism safety** | can-parallelize |

### Q-047: tiny-live Seeder Guard Hardening or Archive Decision

| Field | Value |
|---|---|
| **Queue ID** | Q-047 |
| **Source report(s)** | SCRIPTAUDIT-042 |
| **Goal** | 决定 `scripts/seed_tiny_live_profile.py` 是否保留为 live metadata utility；若保留，补齐强 Owner 守卫；若不保留，进入 archive-prep |
| **Allowed files** | decision doc only at first, later `scripts/seed_tiny_live_profile.py` only after Codex approval |
| **Forbidden files** | running the seeder, `live-config.env`, `.env*`, deploy/Tokyo/exchange/network 操作 |
| **Requirements** | 1) 不运行 seed；2) 若保留，守卫至少对齐 prelive seeder 的 `OWNER_APPROVED_*`、`TRADING_ENV=live`、`EXCHANGE_TESTNET=false`、read-only permission、active-profile replacement checks；3) 若归档，先确认无 active references；4) 不扩大 live profile 或 order-sizing 默认值 |
| **Tests/verification** | targeted unit/static tests only after implementation approval；read-only `rg` for active references |
| **Risk level** | HIGH（live-capable active profile + weak apply guard） |
| **Parallelism safety** | max-1 |

### Q-048: GKS Seeder Active-Runtime Decision

| Field | Value |
|---|---|
| **Queue ID** | Q-048 |
| **Source report(s)** | SCRIPTAUDIT-042 |
| **Goal** | 判断 `scripts/seed_gks_state.py` 是否仍属于 active runtime safety surface，或已被 StrategyGroup pause/kill 语义取代 |
| **Allowed files** | read-only code/docs analysis; future docs/current script map after decision |
| **Forbidden files** | running the seeder, mutating PG GKS, deploy/Tokyo/exchange/network 操作, `live-config.env`, `.env*` |
| **Requirements** | 1) 追踪 `PgGlobalKillSwitchRepository` active consumers；2) 判断 GKS 与 StrategyGroup pause/kill 的职责边界；3) 若保留，列入 `ACTIVE_SCRIPT_MAP.md` protected safety utility；4) 若归档，必须先有 migration proof |
| **Tests/verification** | read-only `rg 'PgGlobalKillSwitchRepository|global_kill_switch|GlobalKillSwitch' src scripts tests docs` |
| **Risk level** | HIGH（safety-critical mutation surface） |
| **Parallelism safety** | max-1 |

### Q-049: Testnet-only Seeder Archive Prep

| Field | Value |
|---|---|
| **Queue ID** | Q-049 |
| **Source report(s)** | SCRIPTAUDIT-042 |
| **Goal** | 为 `seed_brc_profile.py`、`seed_phase5e_profile.py`、`seed_strategy_trial_bnb_profile.py` 归档做准备，先迁移 test/prelive constant imports 并确认 local-testnet helper 是否已废弃 |
| **Allowed files** | tests/fixtures or tests importing seed constants, later archive README after approval |
| **Forbidden files** | running seed scripts, `live-config.env`, `.env*`, deploy/Tokyo/exchange/network 操作 |
| **Requirements** | 1) `PHASE5E_PROFILE` 不再从 script module 被测试导入；2) `BNB_STRATEGY_TRIAL_PROFILE` 不再被 prelive seeder 从 testnet seeder 直接导入，或 Codex 决定保留 shared fixture；3) 确认 `scripts/start_brc_local_testnet.sh` 是否仍使用；4) 归档前做 import search |
| **Tests/verification** | targeted unit tests for profile payload validation after import migration |
| **Risk level** | MEDIUM（archive-prep; import compatibility） |
| **Parallelism safety** | max-1 |

### Q-050: Trend Execute Readiness CLI Deprecation Decision

| Field | Value |
|---|---|
| **Queue ID** | Q-050 |
| **Source report(s)** | SCRIPTAUDIT-043 |
| **Goal** | 决定 `scripts/probe_trend_execute_server_readiness.py` 是否保留为 protected execute-capable CLI，或明确 deprecated/archive |
| **Allowed files** | decision doc only at first; script changes only after Codex approval |
| **Forbidden files** | running the probe, POSTing execute/authorization endpoints, `live-config.env`, `.env*`, deploy/Tokyo/exchange/network 操作 |
| **Requirements** | 1) 不运行 probe；2) 对 `TREND_EXECUTE_MODE=execute` 和 `OWNER_APPROVED_TREND_BOUNDED_EXECUTION` 做边界评估；3) 若保留，必须在 ACTIVE_SCRIPT_MAP 标为 execute-capable protected script；4) 若归档，先确认 owner-trial-flow API 与 runtime path 已覆盖全部必要用途 |
| **Tests/verification** | read-only code/test search；任何 behavior tests 只能 mock HTTP calls |
| **Risk level** | HIGH（guarded real execute POST capability） |
| **Parallelism safety** | max-1 |

### Q-051: BRC Scoped Runtime Safety Clearance Script Decision

| Field | Value |
|---|---|
| **Queue ID** | Q-051 |
| **Source report(s)** | SCRIPTAUDIT-043 |
| **Goal** | 决定 `scripts/brc_record_scoped_runtime_safety_clearance.py` 是否仍是 active safety utility，或因 trial-specific scope 进入迁移/归档 |
| **Allowed files** | read-only code/docs analysis; future docs/current script map after decision |
| **Forbidden files** | running the script, mutating PG, `live-config.env`, `.env*`, deploy/Tokyo/exchange/network 操作 |
| **Requirements** | 1) 追踪 `brc_scoped_runtime_safety_clearances` active readers/writers；2) 判断 StrategyGroup-era 是否仍需要该表/脚本；3) 若保留，消除或声明 MI-001-BNB-specific scope；4) 若归档，先完成 API/table migration proof |
| **Tests/verification** | read-only `rg 'brc_scoped_runtime_safety_clearances|record_scoped_runtime_safety_clearance' src scripts tests docs` |
| **Risk level** | HIGH（PG safety metadata mutation surface） |
| **Parallelism safety** | max-1 |

### Q-052: Old probe/brc Archive-Prep Pack

| Field | Value |
|---|---|
| **Queue ID** | Q-052 |
| **Source report(s)** | SCRIPTAUDIT-043 |
| **Goal** | 为 `brc_dev_migration_smoke.py`、`brc_operator.py`、`probe_runtime_bound_readonly.py` 建立 archive-prep 迁移计划 |
| **Allowed files** | output report or docs-only plan first; tests/fixtures only after approval |
| **Forbidden files** | running probes, source mutation before approval, `live-config.env`, `.env*`, deploy/Tokyo/exchange/network 操作 |
| **Requirements** | 1) 确认 SQLite smoke 是否仍为任何 dev gate 所需；2) 确认 old BRC operator endpoints 是否仍需 CLI；3) 迁移 `probe_runtime_bound_readonly.py` 的 test imports；4) 归档前执行 import/reference search |
| **Tests/verification** | read-only references first; targeted tests only after migration |
| **Risk level** | MEDIUM（archive-prep; test/import compatibility） |
| **Parallelism safety** | max-1 |

### Q-053: runtime_live Archive-Prep Pack

| Field | Value |
|---|---|
| **Queue ID** | Q-053 |
| **Source report(s)** | SCRIPTAUDIT-044 |
| **Goal** | 为 continuation/operator/supervisor/shadow-planning/standalone enablement runtime_live 脚本建立归档准备计划 |
| **Allowed files** | output report or docs-only plan first; tests/fixtures/import migration only after approval |
| **Forbidden files** | running runtime_live scripts, source mutation before approval, `live-config.env`, `.env*`, deploy/Tokyo/exchange/network 操作 |
| **Requirements** | 1) 把 `runtime_live_attempt_readiness_packet.py`、`runtime_live_continuation_refresh_flow.py`、`runtime_live_continuation_selector_packet.py` 作为 continuation chain 处理；2) 把 `runtime_live_signal_operator_cycle.py`、`runtime_live_signal_operator_supervisor.py`、`runtime_live_signal_shadow_planning_bridge.py` 作为 operator/shadow-planning chain 处理；3) 对 `runtime_live_enablement_api_flow.py` 单独处理 live-enablement mutation 风险；4) 归档前迁移 tests/fixtures/imports 并验证无 active imports |
| **Tests/verification** | read-only reference map first; targeted unit tests after migration |
| **Risk level** | MEDIUM（archive-prep; import compatibility and live-enablement mutation history） |
| **Parallelism safety** | max-1 |

### Q-054: runtime_live Bootstrap Active Utility Decision

| Field | Value |
|---|---|
| **Queue ID** | Q-054 |
| **Source report(s)** | SCRIPTAUDIT-044 |
| **Goal** | 将 `runtime_live_bootstrap_api_flow.py` 明确归类为 protected active utility，或由 Codex 决定迁入当前 StrategyGroup bootstrap 模块 |
| **Allowed files** | docs/current script map or output decision pack first; code movement only after Codex architecture decision |
| **Forbidden files** | running bootstrap flow, changing StrategyGroup bootstrap behavior without approval, `live-config.env`, `.env*`, deploy/Tokyo/exchange/network 操作 |
| **Requirements** | 1) 保留 `bootstrap_strategygroup_runtime_pilot.py` active import 事实；2) 说明该 flow 创建 admission/trial binding/runtime records，但不创建 candidate/ExecutionIntent/order/withdrawal/transfer/exchange submit；3) 明确 env/exchange account facts read boundary；4) 若迁移模块，先做 tests/import compatibility plan |
| **Tests/verification** | read-only imports first; targeted bootstrap API-flow tests after any implementation |
| **Risk level** | HIGH（active bootstrap API mutation flow） |
| **Parallelism safety** | max-1 |

### Q-055: High-Risk Core-Touching Script Guard Map

| Field | Value |
|---|---|
| **Queue ID** | Q-055 |
| **Source report(s)** | SCRIPTAUDIT-045, DECISIONPACK-046 |
| **Goal** | 已完成决策：`owner_authorized_bnb_close.py`、`runtime_owner_reduce_only_close_flow.py`、`recover_runtime_exchange_submit_projection.py`、`recover_runtime_exchange_close_projection.py`、`probe_exchange_credential_preflight.py` 全部为 KEEP-PROTECTED / CODEX-GUARDED，排除 bulk cleanup/archive/comment wave |
| **Allowed files** | output decision pack or docs/current script map first; script comments only after Codex approval |
| **Forbidden files** | running scripts, exchange/network calls, `live-config.env`, `.env*`, source/core mutation, deploy/Tokyo 操作 |
| **Requirements** | 后续只允许进入 ACTIVE_SCRIPT_MAP 或 per-script Codex task card；任何 comment-only 实施也必须保留 DECISIONPACK-046 的 guard 语义，不得弱化真实 exchange/order/recovery/credential 风险 |
| **Tests/verification** | Claude read-only decision pack；未来实现需 targeted static/unit checks |
| **Risk level** | HIGH（core + exchange/order/recovery/credential surfaces） |
| **Parallelism safety** | done / future implementation max-1 |

### Q-056: runtime_official Proof Stub Interface Tracking

| Field | Value |
|---|---|
| **Queue ID** | Q-056 |
| **Source report(s)** | SCRIPTAUDIT-040, SCRIPTAUDIT-045, SCRIPTAUDIT-047 |
| **Goal** | 已完成分类：`runtime_official_*_proof.py` adapter stub interface 已记录；RTF-085/087/088 是 safety-sensitive proof contract，编码 order lifecycle / exchange gateway / position projection / post-submit finalize 合约 |
| **Allowed files** | output report or docs/current ACTIVE_SCRIPT_MAP after Q-043 |
| **Forbidden files** | source/core mutation, running proof scripts without approval, `live-config.env`, `.env*` |
| **Requirements** | 后续分为 Q-058/Q-059；core refactor 前必须对照 proof stub contract；归档 proof scripts 时必须保留 stub/interface contract evidence |
| **Tests/verification** | Claude read-only interface tracking + `rg` |
| **Risk level** | MEDIUM（proof evidence interface drift） |
| **Parallelism safety** | done / future contract/archive task max-1 |

### Q-057: CPM OOS Research Script Archive Prep

| Field | Value |
|---|---|
| **Queue ID** | Q-057 |
| **Source report(s)** | SCRIPTAUDIT-039, SCRIPTAUDIT-045 |
| **Goal** | 将 `run_cpm1_2021_oos.py` 与 `run_cpm1_2022_oos.py` 作为 research/backtest OOS archive candidates 处理 |
| **Allowed files** | output archive-prep report first; archive move only after explicit approval |
| **Forbidden files** | running OOS scripts, exchange/network calls, strategy parameter changes, `live-config.env`, `.env*` |
| **Requirements** | 1) 确认无 active runtime imports；2) 标注 ExchangeGateway lazy import 仅属于 research/backtest lane；3) 如归档，移动到 research/archive 并写 README；4) 不与 StrategyGroup runtime path 混用 |
| **Tests/verification** | read-only `rg 'run_cpm1_2021_oos|run_cpm1_2022_oos' scripts tests docs` |
| **Risk level** | LOW/MEDIUM（research archive; avoid accidental exchange use） |
| **Parallelism safety** | can-parallelize after mainline acceptance |

### Q-058: Proof Stub Contract Checklist for Core Refactors

| Field | Value |
|---|---|
| **Queue ID** | Q-058 |
| **Source report(s)** | SCRIPTAUDIT-047, CHECKLIST-048 |
| **Goal** | 已完成 checklist：为 `order_lifecycle_service.py`、`exchange_gateway.py`、`position_projection_service.py`、post-submit finalize/reconciliation refactor 建立 proof stub contract checklist，RTF-085/087/088 为 strong-gate proofs |
| **Allowed files** | output decision/checklist or docs/current script map after Q-043 |
| **Forbidden files** | core/source mutation without explicit Codex task, running proof scripts, `live-config.env`, `.env*` |
| **Requirements** | future core-refactor task cards must cite CHECKLIST-048 pre-change / implementation-time / post-change / rollback sections；ACTIVE_SCRIPT_MAP 应列 RTF-085/087/088 为 strong-gate proof |
| **Tests/verification** | Claude read-only checklist；future implementation refactor 后再跑 targeted proof/unit tests |
| **Risk level** | MEDIUM/HIGH（core refactor proof drift） |
| **Parallelism safety** | done / future core-refactor max-1 |

### Q-059: runtime_official Proof Archive Preservation Rule

| Field | Value |
|---|---|
| **Queue ID** | Q-059 |
| **Source report(s)** | SCRIPTAUDIT-040, SCRIPTAUDIT-047, DECISIONPACK-049 |
| **Goal** | 已完成规则：未来归档 `runtime_official_*_proof.py` 必须保留 RTF id、原路径、endpoint coverage gap、stub/interface contract、safety labels；`runtime_official_submit_disabled_smoke_from_handoff.py` 不得归档直到 dry-run chain import 迁移；RTF-085/087/088 需 Codex 决策 |
| **Allowed files** | archive README / output decision pack first |
| **Forbidden files** | deleting/moving proof scripts without approval, running proof scripts, source/core mutation, `live-config.env`, `.env*` |
| **Requirements** | future archive task cards must cite DECISIONPACK-049；archive README 必须保留 stub class/interface table 与 adapter_service injection contract；active dependency / shared infra / safety-sensitive proofs 必须分开处理 |
| **Tests/verification** | Claude read-only decision pack；future archive task 先做 import/reference search |
| **Risk level** | MEDIUM（历史 proof evidence loss） |
| **Parallelism safety** | done / future archive task max-1 |

### Q-060: runtime_dry_run Proof Dependency Migration Map

| Field | Value |
|---|---|
| **Queue ID** | Q-060 |
| **Source report(s)** | SCRIPTAUDIT-040, SCRIPTAUDIT-047, DECISIONPACK-049, SCRIPTAUDIT-050 |
| **Goal** | 已完成迁移图：确认 `runtime_dry_run_audit_chain.py` 只有 1 个 active proof-script import，即 `runtime_official_submit_disabled_smoke_from_handoff.py`；`runtime_current_persisted_source_disabled_smoke_pipeline.py` 与 `verify_runtime_official_submit_action_time_bridge.py` 是独立 consumers |
| **Allowed files** | output audit report only |
| **Forbidden files** | source/script/test mutation, running proof scripts/tests, deploy/Tokyo/watcher/exchange, `live-config.env`, `.env*` |
| **Requirements** | future archive/refactor tasks must cite SCRIPTAUDIT-050 dependency map；`runtime_official_submit_disabled_smoke_from_handoff.py` archive 前必须处理 dry-run chain + 2 independent consumers；`runtime_official_submit_handoff_from_readiness.py` 不属于 dry-run chain dependency |
| **Tests/verification** | Claude read-only dependency trace；future implementation task must run targeted pytest after source changes |
| **Risk level** | MEDIUM（active proof dependency removal risk） |
| **Parallelism safety** | done / future implementation max-1 |

### Q-061: Migrate dry-run chain disabled-smoke dependency

| Field | Value |
|---|---|
| **Queue ID** | Q-061 |
| **Source report(s)** | SCRIPTAUDIT-050 |
| **Goal** | 移除或正式保留 `runtime_dry_run_audit_chain.py` 对 `runtime_official_submit_disabled_smoke_from_handoff.py` 的直接依赖，解除 proof archive 的 active dependency blocker |
| **Allowed files** | `scripts/runtime_dry_run_audit_chain.py`, `tests/unit/test_runtime_dry_run_audit_chain.py` |
| **Forbidden files** | `src/**`, deploy/Tokyo/watcher/exchange, `live-config.env`, `.env*`, unrelated owner-runtime-console changes |
| **Requirements** | Codex 先选择 Option A inline 或 Option C permanent active utility；若 inline，移除 proof-script import 并保持 disabled-smoke status/assertion 语义；不得改变 FinalGate/Operation Layer/live execution semantics |
| **Tests/verification** | `python -m pytest tests/unit/test_runtime_dry_run_audit_chain.py -v`; import search confirms dry-run chain no longer imports proof script if Option A |
| **Risk level** | LOW/MEDIUM（pure refactor but touches active audit chain） |
| **Parallelism safety** | max-1；mainline active acceptance 期间不执行 |

### Q-062: Migrate remaining disabled-smoke consumers

| Field | Value |
|---|---|
| **Queue ID** | Q-062 |
| **Source report(s)** | SCRIPTAUDIT-050 |
| **Goal** | 处理 `runtime_current_persisted_source_disabled_smoke_pipeline.py` 与 `verify_runtime_official_submit_action_time_bridge.py` 对 `runtime_official_submit_disabled_smoke_from_handoff.py` 的独立依赖，作为完整 archive 前置 |
| **Allowed files** | `scripts/runtime_current_persisted_source_disabled_smoke_pipeline.py`, `scripts/verify_runtime_official_submit_action_time_bridge.py`, corresponding targeted tests |
| **Forbidden files** | `src/**`, deploy/Tokyo/watcher/exchange, `live-config.env`, `.env*`, unrelated owner-runtime-console changes |
| **Requirements** | Q-061 后再执行；保留 disabled-smoke safety checks；若 bridge 无 pytest 覆盖，先补最小 test 或保留为 self-verifier protected script；archive 前 `rg 'runtime_official_submit_disabled_smoke_from_handoff' scripts/ tests/ src/ docs/` 需按任务预期收敛 |
| **Tests/verification** | `python -m pytest tests/unit/test_runtime_current_persisted_source_disabled_smoke_pipeline.py -v`；bridge targeted verifier/test 由任务卡明确 |
| **Risk level** | LOW/MEDIUM |
| **Parallelism safety** | max-1；Q-061 后串行 |

### Q-063: Consolidated Active Script Map Draft

| Field | Value |
|---|---|
| **Queue ID** | Q-063 |
| **Source report(s)** | SCRIPTAUDIT-039~050, DECISIONPACK-046, CHECKLIST-048, DECISIONPACK-049, ARCHDEBT-037, SCRIPTAUDIT-051 |
| **Goal** | 已完成 consolidated Active Script Map 草案：把 176 个顶层 scripts 聚合为 ACTIVE-RUNTIME、ACTIVE-DEPLOY-OR-DOCS-PROTECTED、ACTIVE-DRY-RUN-AUDIT、PROTECTED-SAFETY-PROOF、CODEX-GUARDED、DECISION-REQUIRED、ARCHIVE-PREP、DO-NOT-BULK-TOUCH |
| **Allowed files** | output audit report only |
| **Forbidden files** | source/script/test mutation, docs/current mutation during active acceptance, running scripts/tests, deploy/Tokyo/watcher/exchange, `live-config.env`, `.env*` |
| **Requirements** | future cleanup/archive tasks must cite SCRIPTAUDIT-051；DO-NOT-BULK-TOUCH 24 scripts 不得进入批量清理；ARCHIVE-PREP 必须先跑 universal precondition searches 并写 archive README |
| **Tests/verification** | Claude read-only consolidation；future implementation/archive tasks require per-cluster verification |
| **Risk level** | HIGH（脚本清理总入口，防误删 active/protected surfaces） |
| **Parallelism safety** | done / future cleanup max-1 by default |

### Q-064: Promote Active Script Map to docs/current

| Field | Value |
|---|---|
| **Queue ID** | Q-064 |
| **Source report(s)** | SCRIPTAUDIT-051 |
| **Goal** | 在 mainline acceptance 后，将 consolidated map 提炼为 `docs/current/ACTIVE_SCRIPT_MAP.md`，作为脚本清理与 archive 的当前权威入口 |
| **Allowed files** | `docs/current/ACTIVE_SCRIPT_MAP.md`（new） |
| **Forbidden files** | `src/**`, `scripts/**`, `tests/**`, `deploy/**`, `live-config.env`, `.env*`, watcher/Tokyo/exchange |
| **Requirements** | 1) 列出 7 个 ACTIVE-RUNTIME 与 deploy references；2) 列出 DO-NOT-BULK-TOUCH exclusion set；3) 链接 CHECKLIST-048 / DECISIONPACK-049 / SCRIPTAUDIT-051；4) 保留 Deletion/Archive Preconditions；5) 明确哪些分类是 current-read，哪些来自 prior audit |
| **Tests/verification** | docs-only；`rg 'runtime_signal_watcher_tick|runtime_dry_run_audit_chain|DO-NOT-BULK-TOUCH' docs/current/ACTIVE_SCRIPT_MAP.md` |
| **Risk level** | LOW（docs-only，authority surface） |
| **Parallelism safety** | max-1；mainline acceptance 后执行 |

### Q-065: CODEX-GUARDED Script Header Guardrails

| Field | Value |
|---|---|
| **Queue ID** | Q-065 |
| **Source report(s)** | DECISIONPACK-046, SCRIPTAUDIT-051 |
| **Goal** | 为 5 个 CODEX-GUARDED 脚本添加最小保护头，明确 core modules touched、exchange write、PG write、credential risk 与禁止批量清理规则 |
| **Allowed files** | `scripts/owner_authorized_bnb_close.py`, `scripts/runtime_owner_reduce_only_close_flow.py`, `scripts/recover_runtime_exchange_submit_projection.py`, `scripts/recover_runtime_exchange_close_projection.py`, `scripts/probe_exchange_credential_preflight.py` |
| **Forbidden files** | `src/**`, `deploy/**`, unrelated scripts/tests, `live-config.env`, `.env*`, watcher/Tokyo/exchange |
| **Requirements** | comment-only；不得改变任何 runtime behavior、approval env、safety invariant、import order 或 execution path；每个脚本应能独立 review |
| **Tests/verification** | `rg 'CODEX-GUARDED SCRIPT'` over the 5 files；no script execution |
| **Risk level** | LOW/MEDIUM（comment-only but safety-adjacent guarded files） |
| **Parallelism safety** | max-1；mainline acceptance 后执行 |

### Q-066: Research Script Archive Batch

| Field | Value |
|---|---|
| **Queue ID** | Q-066 |
| **Source report(s)** | SCRIPTAUDIT-039, SCRIPTAUDIT-051 |
| **Goal** | 在完成引用搜索后，将 9 个 backtest/CPM research scripts 移入 `scripts/archive/research/` 并创建 README |
| **Allowed files** | 9 个 research scripts from SCRIPTAUDIT-051 section 2.7.1, `scripts/archive/research/README.md` |
| **Forbidden files** | `src/**`, `deploy/**`, `live-config.env`, `.env*`, exchange/Tokyo/watcher operations |
| **Requirements** | 1) 每个脚本先跑 SCRIPTAUDIT-051 section 5.1 universal preconditions；2) move not delete；3) README 保留原路径、archive reason、not active runtime/not deploy-referenced；4) 若任意 active ref 非空则 stop |
| **Tests/verification** | `rg 'run_cpm1_2021_oos|run_cpm1_2022_oos|one_day_spot_trend|te005_|analyze_tb001|run_cpm_ro001' src tests scripts --glob '*.py'` 按任务预期收敛 |
| **Risk level** | LOW（research archive, but file moves） |
| **Parallelism safety** | max-1；mainline acceptance 后执行 |

### Q-067: Script Cleanup Wave Plan and Task Cards

| Field | Value |
|---|---|
| **Queue ID** | Q-067 |
| **Source report(s)** | SCRIPTAUDIT-051, SCRIPTAUDIT-039~050, DECISIONPACK-046, CHECKLIST-048, DECISIONPACK-049 |
| **Goal** | 产出 script cleanup wave plan 和 task card pack (Q-067~Q-073)，将 consolidated script map 转化为可执行的 post-acceptance 波次计划 |
| **Allowed files** | `output/claude-token-burn/CLAUDE-FINAL-TASKPACK-052-script-cleanup-wave-plan-and-taskcards.md` |
| **Forbidden files** | 所有其他文件 |
| **Requirements** | 7 波执行计划（Wave 0~6）+ 决策表 + DO-NOT-BULK-TOUCH 排除列表 + CODEX-GUARDED 详情 + task cards Q-067~Q-073 |
| **Tests/verification** | `ls output/claude-token-burn/CLAUDE-FINAL-TASKPACK-052-*.md`; `git status --short` |
| **Risk level** | NONE（output-only planning） |
| **Parallelism safety** | solo |

### Q-068: ACTIVE_SCRIPT_MAP Promotion Draft

| Field | Value |
|---|---|
| **Queue ID** | Q-068 |
| **Source report(s)** | SCRIPTAUDIT-051, TASKPACK-052, SCRIPTMAP-053 |
| **Goal** | 已完成：产出 `docs/current/ACTIVE_SCRIPT_MAP.md` 的 output-only promotion draft，精简 output-only artifacts 并加入 Codex 权威分类决策前的草案边界 |
| **Allowed files** | `output/claude-token-burn/CLAUDE-FINAL-SCRIPTMAP-053-active-script-map-promotion-draft.md` |
| **Forbidden files** | `src/**`, `scripts/**`, `tests/**`, `deploy/**`, `docs/current/**`, `live-config.env`, `.env*` |
| **Requirements** | 1) 列出 7 个 ACTIVE-RUNTIME scripts；2) 列出 DO-NOT-BULK-TOUCH；3) 链接 CHECKLIST-048/DECISIONPACK-049；4) 标记 DECISION-REQUIRED；5) 包含 Deletion/Archive Preconditions；6) 分离事实与建议；7) 明确 draft 不是 current authority |
| **Tests/verification** | `ls output/claude-token-burn/CLAUDE-FINAL-SCRIPTMAP-053-*.md` |
| **Risk level** | NONE（output-only） |
| **Parallelism safety** | done / future docs promotion max-1 |

### Q-074: Final ACTIVE_SCRIPT_MAP docs/current Promotion

| Field | Value |
|---|---|
| **Queue ID** | Q-074 |
| **Source report(s)** | SCRIPTMAP-053, SCRIPTAUDIT-051, TASKPACK-052 |
| **Goal** | 在 mainline acceptance 完成后，从 SCRIPTMAP-053 创建 `docs/current/ACTIVE_SCRIPT_MAP.md`，作为脚本清理、archive、guard header、proof preservation 的当前权威入口 |
| **Allowed files** | `docs/current/ACTIVE_SCRIPT_MAP.md`（new） |
| **Forbidden files** | `src/**`, `scripts/**`, `tests/**`, `deploy/**`, `live-config.env`, `.env*`, watcher/Tokyo/exchange |
| **Requirements** | 1) 确认 mainline acceptance complete；2) 从 SCRIPTMAP-053 移除 output-only 语气；3) 保留 7 ACTIVE-RUNTIME、24 DO-NOT-BULK-TOUCH、5 CODEX-GUARDED、7 DECISION-REQUIRED；4) 保留 Deletion/Archive Preconditions；5) 标注哪些分类来自 current-read，哪些来自 prior audits；6) 若 Q-064 保留，则 Q-074 应取代或合并 Q-064，避免两个 docs/current promotion 任务并行 |
| **Tests/verification** | `rg 'runtime_signal_watcher_tick|runtime_dry_run_audit_chain|build_strategygroup_runtime_goal_status|DO-NOT-BULK-TOUCH' docs/current/ACTIVE_SCRIPT_MAP.md` |
| **Risk level** | LOW（docs-current authority surface） |
| **Parallelism safety** | max-1；mainline acceptance 后执行 |

### Q-069: Research Archive Batch Execution

| Field | Value |
|---|---|
| **Queue ID** | Q-069 |
| **Source report(s)** | SCRIPTAUDIT-051 section 2.7.1, TASKPACK-052 Wave 3 |
| **Goal** | 执行 Wave 3：将 9 个 backtest/CPM research scripts 移入 `scripts/archive/research/` 并创建 READMEs |
| **Allowed files** | 9 个 research scripts, `scripts/archive/research/README.md`, `scripts/replay_recovery_history/README.md` |
| **Forbidden files** | `src/**`, `deploy/**`, `live-config.env`, `.env*`, 所有其他 scripts, exchange/Tokyo/watcher |
| **Requirements** | 1) 每个脚本跑 SCRIPTAUDIT-051 section 5.1 universal preconditions；2) move not delete；3) README 保留原路径和 archive reason；4) 零 active refs |
| **Tests/verification** | `rg 'run_cpm1_2021_oos\|run_cpm1_2022_oos\|one_day_spot_trend\|te005_\|analyze_tb001\|run_cpm_ro001' src tests scripts --glob '*.py'` |
| **Risk level** | LOW（research archive） |
| **Parallelism safety** | max-1；Wave 1 后执行 |

### Q-070: Proof Archive Prep Execution

| Field | Value |
|---|---|
| **Queue ID** | Q-070 |
| **Source report(s)** | SCRIPTAUDIT-040, SCRIPTAUDIT-047, DECISIONPACK-049, SCRIPTAUDIT-050, SCRIPTAUDIT-051, TASKPACK-052 Wave 4 |
| **Goal** | 执行 Wave 4：准备 `scripts/archive/runtime-official-proofs/`，归档 13 个 archive-candidate proof scripts 并保留 contract evidence |
| **Allowed files** | 13 个 archive-candidate proof scripts, `scripts/archive/runtime-official-proofs/README.md`, corresponding test files |
| **Forbidden files** | `src/**`, `deploy/**`, `live-config.env`, `.env*`, DO-NOT-BULK-TOUCH scripts, exchange/Tokyo/watcher |
| **Requirements** | 1) Q-061/Q-062 先完成；2) Codex 决策 RTF-085/087/088 归档时机；3) Universal preconditions 通过；4) README 保留 RTF id/stub/interface contract/adapter_service injection/safety labels；5) 按 DECISIONPACK-049 反向依赖顺序归档 |
| **Tests/verification** | `rg '<archived_script_names>' scripts/ --glob '*.py'` 归档后返回零 |
| **Risk level** | MEDIUM（proof archive; contract-sensitive） |
| **Parallelism safety** | max-1；Wave 1 + Q-061/Q-062 后执行 |

### Q-071: Long-Tail Cluster Audit — Tokyo Deploy/Support

| Field | Value |
|---|---|
| **Queue ID** | Q-071 |
| **Source report(s)** | SCRIPTAUDIT-039, SCRIPTAUDIT-051, TASKPACK-052 Wave 6, SCRIPTAUDIT-054 |
| **Goal** | 已完成：逐个审计 11 个 Tokyo deploy/support scripts；全部 classified as ACTIVE-DEPLOY-PROTECTED，无 archive candidates |
| **Allowed files** | output audit report only |
| **Forbidden files** | `src/**`, `deploy/**`, `scripts/**` mutation, `live-config.env`, `.env*`, running scripts, watcher/Tokyo/exchange/network operations |
| **Requirements** | 后续不得将 Tokyo deploy/support cluster 放入 bulk archive；execute 类脚本为 HIGH remote-mutation risk；probe 为 LOW-MEDIUM remote-read risk；所有 11 个脚本需保留到 ACTIVE_SCRIPT_MAP protected section |
| **Tests/verification** | Claude read-only `rg` / `sed` / `git log`; no scripts/tests run |
| **Risk level** | HIGH（deploy pipeline protected；read-only audit complete） |
| **Parallelism safety** | done / future Tokyo deploy changes max-1 |

### Q-075: Long-Tail Cluster Audit — verify_runtime_* and related

| Field | Value |
|---|---|
| **Queue ID** | Q-075 |
| **Source report(s)** | SCRIPTAUDIT-039, SCRIPTAUDIT-051, TASKPACK-052 Wave 6, SCRIPTAUDIT-054 follow-up, SCRIPTAUDIT-055 |
| **Goal** | 已完成：逐个审计 9 个 `verify_runtime_*` 及 related verification scripts；7 个 ACTIVE-RUNTIME-PROTECTED、2 个 ACTIVE-DEPLOY-PROTECTED，无 archive candidates |
| **Allowed files** | output audit report only, read-only source inspection |
| **Forbidden files** | `src/**`, `scripts/**` mutation, `tests/**` mutation, `deploy/**` mutation, `live-config.env`, `.env*`, running scripts/tests, watcher/Tokyo/exchange/network operations |
| **Requirements** | 后续不得将本簇放入 bulk archive；`verify_runtime_submit_rehearsal_pre_live_packet.py` 与 `verify_strategy_observation_shadow_planning_rehearsal.py` 需保留到 deploy-protected section；`verify_runtime_official_submit_action_time_bridge.py` 已修正为有测试覆盖 |
| **Tests/verification** | Claude read-only `ls` / `rg` / `sed` / `git log`; no scripts/tests run |
| **Risk level** | MEDIUM/HIGH（read-only audit complete；classification affects future archive decisions） |
| **Parallelism safety** | done / future verify-runtime changes max-1 |

### Q-076: Long-Tail Cluster Audit — next_attempt / fresh / active_observation

| Field | Value |
|---|---|
| **Queue ID** | Q-076 |
| **Source report(s)** | SCRIPTAUDIT-039, SCRIPTAUDIT-051, TASKPACK-052 Wave 6, SCRIPTAUDIT-054 follow-up, SCRIPTAUDIT-056 |
| **Goal** | 已完成：逐个审计 18 个 `runtime_next_attempt_*`、`runtime_fresh_*`、`runtime_active_observation_*` scripts；9 active-runtime、2 dry-run、3 verification-dep、1 decision、3 archive-prep；覆盖 Q-072 |
| **Allowed files** | output audit report only, read-only source inspection |
| **Forbidden files** | `src/**`, `scripts/**` mutation, `tests/**` mutation, `deploy/**` mutation, `live-config.env`, `.env*`, running scripts/tests, watcher/Tokyo/exchange/network operations |
| **Requirements** | 已满足：1) 明确 cluster selection rule；2) 每个脚本检查 import refs、deploy/docs refs、30-day git activity；3) 标出 dispatcher/dry-run/verification overlap；4) archive-prep 建议带 precondition searches |
| **Tests/verification** | Claude read-only `ls` / `rg` / `sed` / `git log`; no scripts/tests run |
| **Risk level** | MEDIUM/HIGH（read-only audit complete；classification affects future archive decisions） |
| **Parallelism safety** | done / future next-attempt/fresh/active-observation changes max-1 |

### Q-077: Verification Chain Contract Documentation

| Field | Value |
|---|---|
| **Queue ID** | Q-077 |
| **Source report(s)** | SCRIPTAUDIT-055 |
| **Goal** | 将 verification chain topology 写入 docs/current，明确 3 节点验证链、4 个独立验证、2 个 deploy 依赖与 dry-run shared dependency |
| **Allowed files** | `docs/current/VERIFY_RUNTIME_CHAIN_MAP.md` (new) |
| **Forbidden files** | `src/**`, `scripts/**` mutation, `tests/**` mutation, `deploy/**` mutation, `live-config.env`, `.env*`, running scripts/tests, watcher/Tokyo/exchange/network operations |
| **Requirements** | 1) 记录 `gate_strategy_planning -> submit_preparation_bridge -> official_submit_action_time_bridge` 链；2) 记录 `disabled_smoke_from_handoff` shared dependency；3) 记录 Tokyo deploy 依赖；4) 使用 protected 分类，不把 verifier 当 archive-prep |
| **Tests/verification** | docs-only `rg` verification；no scripts/tests run |
| **Risk level** | LOW（docs-only；mainline acceptance 后执行） |
| **Parallelism safety** | max-1；depends on Q-075 |

### Q-078: SCRIPTAUDIT-051 Reclassification Update

| Field | Value |
|---|---|
| **Queue ID** | Q-078 |
| **Source report(s)** | SCRIPTAUDIT-055 |
| **Goal** | 已完成：更新 SCRIPTAUDIT-051 consolidated map，把 9 个 verification scripts 纳入 individual classification，并修正 `verify_runtime_official_submit_action_time_bridge.py` 的 no-coverage 误标 |
| **Allowed files** | `output/claude-token-burn/CLAUDE-FINAL-SCRIPTAUDIT-051-consolidated-active-script-map-draft.md` |
| **Forbidden files** | `src/**`, `scripts/**` mutation, `tests/**` mutation, `deploy/**` mutation, `live-config.env`, `.env*`, running scripts/tests, watcher/Tokyo/exchange/network operations |
| **Requirements** | 已满足：1) 7 个 ACTIVE-RUNTIME-PROTECTED verifier 入表；2) 2 个 ACTIVE-DEPLOY-PROTECTED verifier 入表；3) 保留 SCRIPTAUDIT-055 citation；4) 未改变源代码 |
| **Tests/verification** | Claude/Codex output-only `rg` verification；no scripts/tests run |
| **Risk level** | LOW（output-only correction complete） |
| **Parallelism safety** | done / future verify-runtime docs changes max-1 |

### Q-079: ARCHIVE-PREP Test Migration for gate_blocker_classification

| Field | Value |
|---|---|
| **Queue ID** | Q-079 |
| **Source report(s)** | SCRIPTAUDIT-056 |
| **Goal** | 迁移 `test_runtime_operator_live_fact_packet.py` 和 `test_runtime_position_lifecycle_exit_readiness_packet.py` 中对 `runtime_next_attempt_gate_blocker_classification` 的引用，使该脚本满足后续归档前置条件 |
| **Allowed files** | `tests/unit/test_runtime_operator_live_fact_packet.py`, `tests/unit/test_runtime_position_lifecycle_exit_readiness_packet.py` |
| **Forbidden files** | `src/**`, `deploy/**`, `live-config.env`, `.env*`, watcher/Tokyo/exchange/network operations |
| **Requirements** | 1) 确认引用可内联或移除；2) 测试仍通过；3) `rg 'runtime_next_attempt_gate_blocker_classification' tests/ scripts/ src/` 返回零活跃引用 |
| **Tests/verification** | targeted pytest for the two tests after mainline acceptance; no current action during active acceptance |
| **Risk level** | LOW/MEDIUM（test migration） |
| **Parallelism safety** | max-1；depends on Q-076 |

### Q-080: DECISION-REQUIRED Fixture Classification

| Field | Value |
|---|---|
| **Queue ID** | Q-080 |
| **Source report(s)** | SCRIPTAUDIT-056, DECISIONPACK-057 |
| **Goal** | 已完成：Codex 决定 `runtime_fresh_authorization_official_handoff_fixture.py` 采用 Option B；Q-061/Q-062 完成前临时保留为 ACTIVE-VERIFICATION-DEPENDENCY，延后归档复评 |
| **Allowed files** | decision/output document first; script/test changes only after Codex task card |
| **Forbidden files** | `src/**`, `deploy/**`, `live-config.env`, `.env*`, watcher/Tokyo/exchange/network operations |
| **Requirements** | 已满足：1) 评估 fixture 在测试中的必要性；2) 评估与 `disabled_smoke_from_handoff` 的依赖关系；3) 选择延后归档方案；4) 定义 Q-082 复评点 |
| **Tests/verification** | Claude read-only `rg` / `git log`; no scripts/tests run |
| **Risk level** | LOW（decision-only complete） |
| **Parallelism safety** | done / future changes max-1 |

### Q-081: ARCHIVE-PREP Batch Execution — next-attempt/fresh/observation

| Field | Value |
|---|---|
| **Queue ID** | Q-081 |
| **Source report(s)** | SCRIPTAUDIT-056 |
| **Goal** | 归档 3 个 ARCHIVE-PREP 脚本到 `scripts/archive/next-attempt-fresh-observation/` |
| **Allowed files** | `scripts/runtime_next_attempt_gate_blocker_classification.py`, `scripts/runtime_fresh_signal_readiness_fixture.py`, `scripts/runtime_fresh_submit_authorization_resolution_api_flow.py`, `scripts/archive/next-attempt-fresh-observation/README.md`, corresponding tests only after Q-079/Q-080 |
| **Forbidden files** | `src/**`, `deploy/**`, `live-config.env`, `.env*`, DO-NOT-BULK-TOUCH scripts, watcher/Tokyo/exchange/network operations |
| **Requirements** | 1) Q-079 complete；2) Q-080 resolved: `runtime_fresh_authorization_official_handoff_fixture.py` is DEFER and excluded from this batch；3) Universal precondition passes；4) move, do not delete；5) README preserves original paths and archive reasons；6) post-archive zero active refs |
| **Tests/verification** | `rg 'runtime_next_attempt_gate_blocker_classification\|runtime_fresh_signal_readiness_fixture\|runtime_fresh_submit_authorization_resolution_api_flow' scripts/ --glob '*.py'` returns zero active refs after archive |
| **Risk level** | LOW/MEDIUM（file moves after preconditions） |
| **Parallelism safety** | max-1；depends on Q-079/Q-080 |

### Q-082: Post-Migration Re-evaluation of Fresh Authorization Fixture

| Field | Value |
|---|---|
| **Queue ID** | Q-082 |
| **Source report(s)** | DECISIONPACK-057 |
| **Goal** | Q-061/Q-062 完成后，重新评估 `runtime_fresh_authorization_official_handoff_fixture.py`：若 `disabled_smoke_from_handoff` 已迁移且 fresh-authorization→handoff→disabled-smoke 链路已有替代测试覆盖，则转为 ARCHIVE-PREP；否则继续保留为 ACTIVE-VERIFICATION-DEPENDENCY |
| **Allowed files** | read-only decision/output document first; code/test changes only after Codex task card |
| **Forbidden files** | `src/**`, `deploy/**`, `live-config.env`, `.env*`, watcher/Tokyo/exchange/network operations |
| **Requirements** | 1) 确认 Q-061/Q-062 complete；2) 检查 `disabled_smoke_from_handoff` 当前 consumers；3) 评估 fresh authorization 链路替代测试覆盖；4) 若归档，先迁移 `test_runtime_fresh_authorization_official_handoff_fixture.py` |
| **Tests/verification** | read-only `rg` dependency verification first |
| **Risk level** | LOW/MEDIUM（post-migration decision） |
| **Parallelism safety** | max-1；depends on Q-061/Q-062 and Q-080 |

### Q-072: Long-Tail Cluster Audit — runtime_next_attempt / runtime_fresh / runtime_active_observation

| Field | Value |
|---|---|
| **Queue ID** | Q-072 |
| **Source report(s)** | SCRIPTAUDIT-039, SCRIPTAUDIT-051, TASKPACK-052 Wave 6, SCRIPTAUDIT-056 |
| **Goal** | 已覆盖：Q-076 / SCRIPTAUDIT-056 已逐个审计 18 个 `runtime_next_attempt_*`/`runtime_fresh_*`/`runtime_active_observation_*` scripts |
| **Allowed files** | read-only audit first; specific files per Codex task card after classification |
| **Forbidden files** | `src/**`, `deploy/**`, `live-config.env`, `.env*`, running scripts |
| **Requirements** | 由 Q-076 满足；后续使用 SCRIPTAUDIT-056 和 Q-079/Q-080/Q-081，不再重复开新 Q-072 审计 |
| **Tests/verification** | SCRIPTAUDIT-056 read-only evidence |
| **Risk level** | LOW（superseded by Q-076） |
| **Parallelism safety** | done / superseded |

### Q-073: Long-Tail Cluster Audit — verify_runtime / runtime_post_submit / runtime_controlled / runtime_profile / unclassified

| Field | Value |
|---|---|
| **Queue ID** | Q-073 |
| **Source report(s)** | SCRIPTAUDIT-039, SCRIPTAUDIT-051, TASKPACK-052 Wave 6, SCRIPTAUDIT-058 |
| **Goal** | 已完成：逐个审计 65 个 remaining runtime/top-level scripts；46 active-runtime、1 dry-run、2 safety-proof、2 codex-guarded、14 archive-prep；完成 176 顶层 scripts 逐个审计闭环 |
| **Allowed files** | read-only audit first; specific files per Codex task card after classification |
| **Forbidden files** | `src/**`, `deploy/**`, `live-config.env`, `.env*`, running scripts |
| **Requirements** | 由 SCRIPTAUDIT-058 满足；后续使用 Q-083~Q-088 执行 guard/header、archive batch 和 first-real-submit shared infrastructure 决策 |
| **Tests/verification** | SCRIPTAUDIT-058 read-only evidence + Codex consistency repair |
| **Risk level** | LOW（read-only audit first） |
| **Parallelism safety** | done |

### Q-083: post_submit / controlled / profile Core-Touching Script Guard Map

| Field | Value |
|---|---|
| **Queue ID** | Q-083 |
| **Source report(s)** | SCRIPTAUDIT-058 |
| **Goal** | 为 `runtime_post_submit_finalize_probe.py` 和 `runtime_position_lifecycle_exit_readiness_packet.py` 添加 CODEX-GUARDED header（需 Codex task card） |
| **Allowed files** | `scripts/runtime_post_submit_finalize_probe.py`, `scripts/runtime_position_lifecycle_exit_readiness_packet.py` |
| **Forbidden files** | `src/**`, `deploy/**`, `live-config.env`, `.env*` |
| **Requirements** | comment-only；列出 core modules touched、PG repos、禁止 bulk cleanup；不得改变行为 |
| **Tests/verification** | `git diff --check` + targeted static readback |
| **Risk level** | LOW（comment-only） |
| **Parallelism safety** | max-1；mainline acceptance 后执行 |

### Q-084: Analyze/Research Smoke Archive Batch

| Field | Value |
|---|---|
| **Queue ID** | Q-084 |
| **Source report(s)** | SCRIPTAUDIT-058 §4.8 |
| **Goal** | 归档 4 个 analyze/research smoke scripts 到 `scripts/archive/research/` |
| **Allowed files** | `scripts/analyze_broad_directional_smoke.py`, `scripts/analyze_directional_opportunity_smoke.py`, `scripts/analyze_mi001_bnb_sol_evidence_reviewability.py`, `scripts/research_directional_opportunity_smoke.py`, `scripts/archive/research/README.md` |
| **Forbidden files** | `src/**`, `deploy/**`, `live-config.env`, `.env*` |
| **Requirements** | 1) `research_directional_opportunity_smoke.py` 的 importers 全部同属 archive 候选；2) `analyze_mi001_bnb_sol_evidence_reviewability.py` 是 strategy-specific；3) README 标注 research-only；4) move, do not delete |
| **Tests/verification** | universal archive preconditions + zero active refs after move |
| **Risk level** | LOW |
| **Parallelism safety** | max-1；mainline acceptance 后执行 |

### Q-085: Data Pipeline Archive Batch

| Field | Value |
|---|---|
| **Queue ID** | Q-085 |
| **Source report(s)** | SCRIPTAUDIT-058 §4.9 |
| **Goal** | 归档 2 个 data pipeline scripts 到 `scripts/archive/data-pipeline/` |
| **Allowed files** | `scripts/import_binance_um_klines_zips_to_sqlite.py`, `scripts/import_sqlite_klines_to_pg.py`, `scripts/archive/data-pipeline/README.md` |
| **Forbidden files** | `src/**`, `deploy/**`, `live-config.env`, `.env*` |
| **Requirements** | 1) 确认无 active imports；2) README 标注 historical data import utility；3) move, do not delete |
| **Tests/verification** | universal archive preconditions + zero active refs after move |
| **Risk level** | LOW |
| **Parallelism safety** | max-1；mainline acceptance 后执行 |

### Q-086: First-Real-Submit Compat Wrapper Archive Prep

| Field | Value |
|---|---|
| **Queue ID** | Q-086 |
| **Source report(s)** | SCRIPTAUDIT-058 §4.4 |
| **Goal** | 归档 3 个 first-real-submit compat wrappers（不含 `runtime_first_real_submit_api_flow.py`） |
| **Allowed files** | `scripts/runtime_executable_submit_readiness_api_flow.py`, `scripts/runtime_executable_submit_readiness_from_reports.py`, `scripts/runtime_legacy_compatibility_isolation_packet.py`, corresponding test files |
| **Forbidden files** | `src/**`, `deploy/**`, `live-config.env`, `.env*`, `scripts/runtime_first_real_submit_api_flow.py` |
| **Requirements** | 1) 确认 0 active importers；2) 迁移 test refs；3) 归档到 `scripts/archive/first-real-submit-compat-wrappers/`；4) move, do not delete |
| **Tests/verification** | universal archive preconditions + targeted tests that referenced wrappers |
| **Risk level** | LOW |
| **Parallelism safety** | max-1；mainline acceptance 后执行 |

### Q-088: BNB Strategy-Specific / Inspect Archive Batch

| Field | Value |
|---|---|
| **Queue ID** | Q-088 |
| **Source report(s)** | SCRIPTAUDIT-058 §4.10, §4.11 |
| **Goal** | 归档 5 个 strategy-specific / inspect scripts（`inspect_bnb_final_gate_blockers_readonly`, `inspect_owner_bounded_authorization_readonly`, `owner_bounded_api_request`, `reset_bnb_testnet_daily_gate`, `run_bnb_live_case_forward_review_once`） |
| **Allowed files** | 上述 5 个脚本, `scripts/archive/strategy-specific/README.md` |
| **Forbidden files** | `src/**`, `deploy/**`, `live-config.env`, `.env*`, `scripts/inspect_runtime_profiles_readonly.py`（ACTIVE-RUNTIME-PROTECTED，不得归档） |
| **Requirements** | 1) 确认 0 active importers；2) 迁移 test refs（`reset_bnb_testnet_daily_gate` 有 1 test）；3) strategy-specific 脚本需边界注释；4) move, do not delete |
| **Tests/verification** | universal archive preconditions + targeted tests that referenced archived scripts |
| **Risk level** | LOW |
| **Parallelism safety** | max-1；mainline acceptance 后执行 |

### Q-033: Legacy Repository Migration Plan

| Field | Value |
|---|---|
| **Queue ID** | Q-033 |
| **Source report(s)** | ARCHDEBT-037 Q-ARCH-006 |
| **Goal** | 文档化非 PG legacy repositories 的 importers、PG equivalent、行为差异和迁移优先级 |
| **Allowed files** | `docs/current/REPOSITORY_MIGRATION_PLAN.md`（新建）, read-only `src/infrastructure/*.py` |
| **Forbidden files** | source mutation、Codex-owned core files、`src/infrastructure/exchange_gateway.py`, `deploy/**`, `live-config.env`, `.env*` |
| **Requirements** | 1) 每个 legacy repo 列出 importers；2) 标记 PG 等价物；3) 按 import count 和 runtime 风险排序；4) docs-only |
| **Tests/verification** | read-only `rg` / import count commands |
| **Risk level** | MEDIUM |
| **Parallelism safety** | can-parallelize |

### Q-034: Operation Layer Decomposition Decision

| Field | Value |
|---|---|
| **Queue ID** | Q-034 |
| **Source report(s)** | ARCHDEBT-037 Q-ARCH-007 |
| **Goal** | 为 `src/application/brc_operation_layer.py` 拆分 policy / registry / service / preflight helpers 做 Codex 决策与任务卡 |
| **Decision needed** | Codex 批准是否触碰该 6,843 行核心执行边界文件，以及拆分顺序 |
| **Allowed files**（批准后） | `src/application/brc_operation_layer.py`, new focused Operation Layer modules, targeted tests |
| **Forbidden files** | 其他 Codex-owned core files、`src/infrastructure/exchange_gateway.py`, `deploy/**`, `live-config.env`, `.env*` |
| **Requirements** | 1) public API surface 不变；2) 不绕过 FinalGate / Operation Layer；3) 每步有 targeted tests；4) max-1 串行 |
| **Tests/verification** | `python3 -m pytest tests/ -k 'operation_layer or brc_operation' -v` |
| **Risk level** | HIGH |
| **Parallelism safety** | solo / max-1 |

### Q-035: Script Staleness Audit and Active Script Map

| Field | Value |
|---|---|
| **Queue ID** | Q-035 |
| **Source report(s)** | ARCHDEBT-037 Q-ARCH-008 |
| **Goal** | 将 189 个 `scripts/*.py` 分类为 active-runtime / active-research / stale-proof / stale-rehearsal，并产出 active script map |
| **Allowed files** | `scripts/*.py` read-only audit, optional `docs/current/ACTIVE_SCRIPT_MAP.md` or output report |
| **Forbidden files** | source mutation before approval、`deploy/**` mutation、`live-config.env`, `.env*`, watcher/Tokyo/exchange 操作 |
| **Requirements** | 1) 先检查 deploy/systemd/cron/docs 引用；2) 不移动 active scripts；3) stale archive 需要单独 Owner/Codex 批准；4) 先输出地图再执行清理 |
| **Tests/verification** | `rg 'scripts/.*\\.py' deploy docs/current .github`; `git log --since='2026-05-17' --name-only -- scripts/` |
| **Risk level** | MEDIUM |
| **Parallelism safety** | max-1 |

---

## D. Decision Required Before Implementation

### Q-011: SOR-001 Mode Alignment

| Field | Value |
|---|---|
| **Queue ID** | Q-011 |
| **Source report(s)** | DECISIONPACK-009 Topic 1, HANDOFFQA-007 F-001, CODETRACE-008 BF-001 |
| **Goal** | 解析 SOR-001 默认模式：推荐 Option B（collapse to `armed_observation`） |
| **Decision needed** | Codex 选择：A（实现 session-window gating）/ B（collapse to armed_observation）/ C（document as advisory） |
| **推荐方案** | Option B — 安全、即时、对齐文档与运行时行为 |
| **Allowed files**（实施后） | `docs/current/strategy-group-handoffs/main-control-handoff-index.md`, `docs/current/strategy-group-handoffs/main-control-admission-priority.md`, `scripts/build_strategy_group_handoff_intake_packet.py` |
| **Forbidden files** | `src/**`, `tests/**`, `deploy/**`, `live-config.env`, `.env*` |
| **Risk level** | LOW（Option B 仅文档+1 行代码） |
| **Parallelism safety** | max-1（需要先做决策） |

### Q-012: Review Outcome Vocabulary Mapping

| Field | Value |
|---|---|
| **Queue ID** | Q-012 |
| **Source report(s)** | DECISIONPACK-009 Topic 3, HANDOFFQA-007 F-004/F-005, CODETRACE-008 BF-003 |
| **Goal** | 文档化后端英文 review outcome 与 board contract 中文 Owner 词汇的映射 |
| **Decision needed** | Codex 选择：A（前端翻译）/ B（后端 emit 双字段）/ C（文档映射表，推荐） |
| **推荐方案** | Option C — 映射表已在 DOCFIX-010 中应用到 board contract |
| **Allowed files**（实施后） | `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md`（已应用），后续可选手 handoff.json |
| **Risk level** | LOW |
| **Parallelism safety** | can-parallelize（与 Q-011 独立） |

### Q-013: Freshness Semantics Documentation

| Field | Value |
|---|---|
| **Queue ID** | Q-013 |
| **Source report(s)** | DECISIONPACK-009 Topic 2, HANDOFFQA-007 F-002, CODETRACE-008 BF-002 |
| **Goal** | 文档化 Candidate Packet Freshness 120s 是 watcher metadata，非运行时强制门禁 |
| **Decision needed** | Codex 选择：A（保持 upstream enum-only，推荐）/ B（强制 numeric 120s）/ C（per-fact windows） |
| **推荐方案** | Option A — 文档已在 DOCFIX-010 中应用 |
| **Allowed files** | 已应用到 `main-control-watcher-cadence.md` 和 `main-control-conflict-policy.md` |
| **Risk level** | NONE |
| **Parallelism safety** | can-parallelize |

### Q-014: trading-console Developer/Audit Classification

| Field | Value |
|---|---|
| **Queue ID** | Q-014 |
| **Source report(s)** | UICARDS-005 UIG-002, AUDIT-001, TASKPACK-003 CARD-003A |
| **Goal** | Codex 决定 trading-console 是 developer-only、需要 remediation、还是归档 |
| **Decision needed** | Codex 选择：a（标记 developer-only）/ b（Owner surface + remediation）/ c（归档） |
| **Blocked cards** | UIG-003, UIG-004, UIG-008 依赖此决策 |
| **Risk level** | MEDIUM（产品表面语义） |
| **Parallelism safety** | max-1 |

### Q-015: Admission + Post-Settlement Safety Tests (Codex-owned source changes)

| Field | Value |
|---|---|
| **Queue ID** | Q-015 |
| **Source report(s)** | TESTCARDS-004 TESTCARD-001/002/003/005, AUDIT-002 |
| **Goal** | 4 个 Codex-owned 测试卡：stale facts confirmation blocking、idempotency degraded mode、no-safe-executor blocked status、admission stale facts + duplicate guard |
| **Decision needed** | Codex 必须先批准预期行为并落地源码修改，Claude 再写测试 |
| **Blocked by** | mainline acceptance + Codex source changes |
| **Risk level** | MEDIUM-HIGH（运行时安全边界） |
| **Parallelism safety** | max-1（需要 Codex 逐个审批） |

### Q-026: Handoff Metadata Enrichment Decision

| Field | Value |
|---|---|
| **Queue ID** | Q-026 |
| **Source report(s)** | HANDOFFQA-030, HANDOFFQA-007, HANDOFFCARDS-006 |
| **Goal** | 决定是否把 `source_commit`、`review_outcome_vocabulary`、signal status Owner mapping 写入每个 handoff JSON，或继续以 research-sync / board contract / operating model 为唯一权威 |
| **Decision needed** | Codex 选择：A（每个 handoff JSON 内嵌 additive metadata）/ B（保持集中权威文档，handoff JSON 不重复）/ C（只对 sample packets 增加 Owner mapping） |
| **Recommended sequencing** | 先完成 Q-011 SOR-001 mode alignment，再处理本卡，避免在 mode 未决时扩大 handoff JSON 变更 |
| **Allowed files**（实施后） | `docs/current/strategy-group-handoffs/**`, `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md`, `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md` |
| **Forbidden files** | `src/**`, `tests/**`, `scripts/**`, `deploy/**`, `live-config.env`, `.env*`, watcher/Tokyo/exchange/network 操作 |
| **Risk level** | P2（handoff contract clarity，非 live-safety blocker） |
| **Parallelism safety** | max-1（依赖 Q-011 决策） |

### Q-087: First-Real-Submit Shared Infrastructure Decision

| Field | Value |
|---|---|
| **Queue ID** | Q-087 |
| **Source report(s)** | SCRIPTAUDIT-058 §4.4, §6.3 D-4, DECISIONPACK-059 |
| **Goal** | 已完成 decision-pack：`runtime_first_real_submit_api_flow.py` 的未来采用 Option C 分阶段迁移建议；当前仅 output-only，不实施代码变更 |
| **Decision output** | DECISIONPACK-059 推荐 Option C：先保护 wrapper，再建立 `runtime_api_client_helpers.py`，再分 T-059-A~F 迁移 29 个顶层 importers、4 个 replay importers、8 个测试引用 |
| **Allowed files** | decision doc complete；code changes only after mainline acceptance or explicit Codex clearance |
| **Forbidden files** | `src/**`, `deploy/**`, `live-config.env`, `.env*` |
| **Requirements** | 已满足：1) 验证 29 个顶层 importers + 4 个 replay importers；2) 给出 A/B/C 方案；3) 选择 Option C；4) 输出 T-059-A~F；5) 明确当前 token-burn lane 不改 `scripts/**` |
| **Risk level** | HIGH（29 importers） |
| **Parallelism safety** | decision complete；implementation max-1 after mainline acceptance or explicit clearance |

---

## E. Do Not Touch During Mainline Acceptance

### Q-016: Old SQLite Repository Removal (CARD-005A)

| Field | Value |
|---|---|
| **Queue ID** | Q-016 |
| **Source report(s)** | DEBT-001, TASKPACK-003 CARD-005A |
| **Why blocked** | 需要更新所有 importer 到 pg_* 等价物；触及 Codex-owned 核心文件 |
| **Unblock condition** | mainline acceptance 完成 + Codex 确认零活跃 caller + 全测试通过 |

### Q-017: Config System Unification (CARD-005B)

| Field | Value |
|---|---|
| **Queue ID** | Q-017 |
| **Source report(s)** | DEBT-001, TASKPACK-003 CARD-005B |
| **Why blocked** | config_manager.py 被广泛 import；跨切面重构 |
| **Unblock condition** | mainline acceptance 完成 + Codex 专用 task card |

### Q-018: Runtime Domain Chain Rationalization (CARD-005C)

| Field | Value |
|---|---|
| **Queue ID** | Q-018 |
| **Source report(s)** | DEBT-001, TASKPACK-003 CARD-005C |
| **Why blocked** | 35 个 domain 文件的架构决策 |
| **Unblock condition** | mainline acceptance 完成 + Codex 架构决策 |

### Q-019: binding vs linkage Consolidation (CARD-005D)

| Field | Value |
|---|---|
| **Queue ID** | Q-019 |
| **Source report(s)** | DEBT-001, TASKPACK-003 CARD-005D |
| **Why blocked** | domain model 重命名需要 Codex 决定规范术语 |
| **Unblock condition** | mainline acceptance 完成 + Codex 决定 |

---

## F. Local Artifact Hygiene / Requires Explicit Owner Approval

### Q-023: Add .gitignore Rules For Local Artifacts

| Field | Value |
|---|---|
| **Queue ID** | Q-023 |
| **Source report(s)** | LOCALARTIFACTS-015 |
| **Goal** | 在 `.gitignore` 中加入 `live-config.env`、`.playwright-cli/`、`local-archives/` 与非 token-burn output 产物规则 |
| **Decision needed** | Codex/Owner 选择是否保留 `output/claude-token-burn/` 为 tracked exception |
| **Allowed files** | `.gitignore` |
| **Forbidden files** | `live-config.env`、`.env*`、任何 output artifact 内容、任何删除/移动 |
| **Tests/verification** | `git check-ignore -v live-config.env .playwright-cli/ local-archives/ output/playwright/`；确认 `git ls-files output/claude-token-burn` 仍为 tracked |
| **Risk level** | LOW |
| **Parallelism safety** | max-1 |

### Q-024: Owner-Approved Local Artifact Cleanup

| Field | Value |
|---|---|
| **Queue ID** | Q-024 |
| **Source report(s)** | LOCALARTIFACTS-015 |
| **Goal** | 在 Owner 明确授权后分阶段清理 stale tooling/cache 和过期 runtime output |
| **Decision needed** | 每个删除/移动阶段都需要 Owner 明确确认；不得默认删除验收证据 |
| **Allowed files** | 待 Owner 指定；默认 none |
| **Forbidden files** | `live-config.env`、`.env*`、当前 mainline acceptance evidence、未确认的 Tokyo/runtime/playwright evidence |
| **Tests/verification** | 仅 metadata commands；每一步前后 `du -sh` 与 `git status --short` |
| **Risk level** | MEDIUM |
| **Parallelism safety** | solo |

---

## 并发推荐

### 约束

- 最多 3 个 Claude 任务并行
- 避免 owner-runtime-console/mainline 干扰
- tests-only 卡可并行（无源码冲突）
- docs-only 卡可并行（无代码冲突）
- Codex-owned 卡需串行（等待审批）
- local artifact cleanup 必须串行并等待 Owner 明确授权

### 推荐分发波次

**Wave 0（仅 review）— 2 个并行**

| 槽位 | 任务 | 说明 |
|------|------|------|
| 1 | Q-001 | review agent cleanup diff；不在当前 token-burn 线程提交 |
| 2 | Q-002 | review owner-runtime-console anti-regression scanner；不在当前 token-burn 线程实施 |

**Wave 1（mainline 后立即）— 3 个并行**

| 槽位 | 任务 | 说明 |
|------|------|------|
| 1 | Q-004 + Q-005 + Q-006 | agent config cleanup 尾巴（quarantine headers + duplicate skill + memory） |
| 2 | Q-007 | FinalGate blocker class tests（CRITICAL） |
| 3 | Q-008 | post-submit partial fill tests（HIGH） |

**Wave 2（mainline 后 P1）— 3 个并行**

| 槽位 | 任务 | 说明 |
|------|------|------|
| 1 | Q-009 | notification/review tests |
| 2 | Q-010 | handoff read-only QA cards |
| 3 | Q-011 + Q-012 + Q-013 | decision pack 实施（需 Codex 先决策） |

**Wave 3（Codex 决策后）— 串行**

| 槽位 | 任务 | 说明 |
|------|------|------|
| 1 | Q-014 | trading-console 分类决策 |
| 2 | Q-015 | admission safety tests（需 Codex source changes） |

**Wave 4+（长期）**

| 槽位 | 任务 | 说明 |
|------|------|------|
| — | Q-016 ~ Q-019 | structural slimming（需 Codex clearance） |
| — | Q-028 ~ Q-088 | runtime semantics slimming / Owner-language contract / script-map/proof-dependency cleanup waves（mainline 后，默认 max-1） |

---

## Resume Prompt（给下一个 Codex turn）

```text
Context: Claude token-burn reports are indexed at output/claude-token-burn/INDEX.md.
Next queue is at output/claude-token-burn/NEXT_QUEUE.md.
Script cleanup execution manifest is at output/claude-token-burn/CLAUDE-FINAL-MANIFEST-060-script-cleanup-execution-manifest.md.
Archive execution task-card pack is at output/claude-token-burn/CLAUDE-FINAL-TASKPACK-062-archive-execution-taskcards.md.
Architecture debt audit is at output/claude-token-burn/CLAUDE-FINAL-ARCHAUDIT-063-domain-boundary-state-mainline-audit.md.
Architecture slimming QA task-card pack is at output/claude-token-burn/CLAUDE-FINAL-QATASKPACK-064-architecture-slimming-test-cards.md.
Module boundary dependency audit is at output/claude-token-burn/CLAUDE-FINAL-MODULEMAP-065-application-boundary-dependency-audit.md.
Module boundary slimming decision pack is at output/claude-token-burn/CLAUDE-FINAL-DECISIONPACK-066-module-boundary-slimming-options.md.
Post-mainline slimming intake sprint pack is at output/claude-token-burn/CLAUDE-FINAL-INTAKEPACK-067-post-mainline-slimming-intake-sprint.md.
Token-burn artifact governance handoff pack is at output/claude-token-burn/CLAUDE-FINAL-HANDOFFPACK-068-token-burn-artifact-governance-handoff.md.
Token-burn artifact governance integrity audit is at output/claude-token-burn/CLAUDE-FINAL-GOVAUDIT-069-token-burn-artifact-governance-integrity-audit.md.
Source-readiness deploy-channel fallback diff review is at output/claude-token-burn/CLAUDE-FINAL-DIFFREVIEW-070-current-mainline-diff-source-readiness-risk-review.md (complete; adds no formal queue IDs; 5 files reviewed, 4 P3 findings, no P0/P1, mainline_safe=true).
Deploy-channel fallback regression test cards are at output/claude-token-burn/CLAUDE-FINAL-QATASKPACK-071-deploy-channel-fallback-regression-test-cards.md (complete; adds no formal queue IDs; 5 QA cards DCHF-071-A~E covering double-missing ready_empty, scope/source_scope explicit behavior, non-critical status invariant, scope string consistency, Owner-language Chinese invariant; implementation-deferred unless Codex/mainline controller authorizes).
Publication-boundary audit is at output/claude-token-burn/CLAUDE-FINAL-PUBAUDIT-072-token-burn-publication-boundary-audit.md (complete; adds no formal queue IDs; confirms dirty worktree limited to output/ files, no mainline source pollution, 89 formal Q- section invariant maintained, 12/12 JSON blocks parse, 068-071 all represented; formal_queue_update=false).
Reference-integrity audit is at output/claude-token-burn/CLAUDE-FINAL-REFAUDIT-073-token-burn-reference-integrity-audit.md (complete; adds no formal queue IDs; verifies INDEX/NEXT_QUEUE file references, orphan detection, near-artifact representation, stale count correction; formal_queue_update=false).
Sensitive-information and publication-safety audit is at output/claude-token-burn/CLAUDE-FINAL-SECRETAUDIT-074-token-burn-sensitive-publication-safety-audit.md (complete; adds no formal queue IDs; scanned 82 Markdown files for API keys/secrets/env content/live payload/mutating commands/absolute paths/webhooks/JSON payloads; 0 P0/P1/P2, 4 P3; 15/15 JSON blocks parse; old executable cleanup commands replaced with non-executable placeholders; 89 formal Q- section invariant maintained; formal_queue_update=false).
Dependency and parallelism map is at output/claude-token-burn/CLAUDE-FINAL-TASKGRAPH-075-next-queue-dependency-and-parallelism-map.md (complete; adds no formal queue IDs; 89 formal Q- sections mapped to 5 groups, 8 clusters, 4 dependency chains, 8 recommended waves, 12 risks; formal_queue_update=false; current Markdown total=84).
Execution-readiness gate audit is at output/claude-token-burn/CLAUDE-FINAL-READINESS-076-next-queue-execution-readiness-gates.md (complete; adds no formal queue IDs; 89 formal Q- sections classified into 6 readiness classes (Review-Only Now 2 / Output-Only Ready 24 / Blocked by Mainline 51 / Blocked by Codex 11 / Do Not Run Current 4 / Blocked by Pub Hygiene 2; 5 overlap items Q-015/Q-047/Q-048/Q-050/Q-051); 8 wave go/no-go gates (Wave 0 is review-only and does not authorize implementation or commit); 14 risks; formal_queue_update=false; current Markdown total=85).
Taskgraph-readiness alignment audit is at output/claude-token-burn/CLAUDE-FINAL-CONSISTENCY-077-taskgraph-readiness-alignment-audit.md (complete; adds no formal queue IDs; cross-audit of TASKGRAPH-075/READINESS-076/INDEX/NEXT_QUEUE; 89 formal Q- section invariant maintained; 0 P0/P1/P2 after Codex wording fix, 5 P3; draft boundary intact; review-only language consistency confirmed; formal_queue_update=false; current Markdown total=86).
Post-mainline governance control brief is at output/claude-token-burn/CLAUDE-FINAL-CONTROLBRIEF-078-post-mainline-governance-control-brief.md (complete; adds no formal queue IDs; compresses TASKGRAPH-075/READINESS-076/CONSISTENCY-077/INDEX/NEXT_QUEUE into main-controller ready control brief; 89 formal Q- section invariant maintained; Wave 0 is REVIEW-ONLY and does not authorize implementation or commit; recommendation_is_binding=false; all Wave 1-7 are NO-GO pending mainline acceptance; 12 risks; formal_queue_update=false; current Markdown total=87).
Review-only authorization drift audit is at output/claude-token-burn/CLAUDE-FINAL-QUEUEGUARD-079-review-only-authorization-drift-audit.md (complete; adds no formal queue IDs; scans INDEX/NEXT_QUEUE/TASKGRAPH-075/READINESS-076/CONSISTENCY-077/CONTROLBRIEF-078 for stale execution language, wave authorization drift, draft ID leakage; initial 3 P2 findings were fixed by Codex in READINESS-076 §6.1 and CONSISTENCY-077 §4.3; current 0 P0/P1/P2, 7 P3; drift_fixed_count=3; draft boundary intact; recommendation_is_binding=false; 89 formal Q- section invariant maintained; formal_queue_update=false; current Markdown total=88).
Mainline interference worktree boundary audit is at output/claude-token-burn/CLAUDE-FINAL-ISOLATION-080-mainline-interference-worktree-boundary-audit.md (complete; adds no formal queue IDs; confirms current visible non-output modified count=0; token-burn lane remains output-only; docs/current/**, src/**, tests/**, scripts/**, deploy/**, owner-runtime-console/src/**, and .github/** are quarantined as mainline/other-window-owned unless a new explicit Codex task card authorizes otherwise; recommendation_is_binding=false; formal_queue_update=false; current Markdown total=89).
Token-burn artifact health refresh is at output/claude-token-burn/CLAUDE-FINAL-ARTIFACTHEALTH-081-token-burn-artifact-health-refresh.md (complete via Codex reconciliation after the Claude 081 worker produced no report file; adds no formal queue IDs; confirms current Markdown total=90, JSON blocks=22, formal Q sections=89, duplicate Q headings=0, draft heading leaks=0; 0 P0/P1/P2, 4 P3; recommendation_is_binding=false; formal_queue_update=false).
Token-burn roadmap crosswalk is at output/claude-token-burn/CLAUDE-FINAL-ROADMAPXWALK-082-token-burn-roadmap-crosswalk.md (complete after Claude alarm exit 142 wrote the file and Codex corrected count metadata; adds no formal queue IDs; maps 12 MAIN_CONTROL_ROADMAP tracks to token-burn artifact groups; confirms current Markdown total=91, JSON blocks=23, formal Q sections=89; records 3 inherited P1 roadmap risks from existing reports; recommendation_is_binding=false; formal_queue_update=false).
Runtime dry-run audit chain current diff review is at output/claude-token-burn/CLAUDE-FINAL-DIFFREVIEW-083-runtime-dry-run-audit-chain-current-diff-review.md (complete; adds no formal queue IDs; reviews transient scripts/runtime_dry_run_audit_chain.py diff adding non-executing prepare auto bridge fixture/scenario; safety invariants PASS; 0 P0, 1 P1, 2 P2, 2 P3; Codex reconciliation found current script diff empty after Claude completed; recommendation_is_binding=false; formal_queue_update=false).
Post-mainline source-risk watchlist is at output/claude-token-burn/CLAUDE-FINAL-SOURCERISK-084-post-mainline-source-risk-watchlist.md (complete via Codex reconciliation after Claude 084 worker timed out without producing a file; adds no formal queue IDs; compresses 063/065/066/067/082/083 into 10 source-risk watchlist items, 6 semantic-slimming priorities, 7 drift/risk findings; confirms current Markdown total=93, JSON blocks=25, formal Q sections=89; recommendation_is_binding=false; formal_queue_update=false).
Post-mainline characterization test plan is at output/claude-token-burn/CLAUDE-FINAL-CHARPLAN-085-post-mainline-characterization-test-plan.md (complete; adds no formal queue IDs; Claude 085 created the file successfully; converts SOURCERISK-084 / ARCHAUDIT-063 / QATASKPACK-064 / MODULEMAP-065 / INTAKEPACK-067 into 12 characterization-first checks covering Decimal/string money fields, console_models, domain purity, reconciliation_lock SQLite, bnb_bridge fact shape, legacy vocabulary, Owner terminology, dict/Any density, common runtime pipe boundary, readmodel response shape, coverage gaps, and goal-status projection; confirms current Markdown total=94, JSON blocks=26, formal Q sections=89; recommendation_is_binding=false; formal_queue_update=false).
System sorting progress scorecard is at output/claude-token-burn/CLAUDE-FINAL-SCORECARD-086-system-sorting-progress-scorecard.md (complete; adds no formal queue IDs; Claude 086 created the file successfully; makes the ~70% system-sorting estimate auditable through 7 weighted dimensions; calculated weighted score=62, understanding/planning cluster=77.5%, execution/closure cluster=41.7%, actual code slimming=10%; confirms current Markdown total=95, JSON blocks=27, formal Q sections=89; recommendation_is_binding=false; formal_queue_update=false).
Post-mainline characterization task cards are at output/claude-token-burn/CLAUDE-FINAL-CHARCARDS-087-post-mainline-characterization-taskcards.md (complete via Codex reconciliation after Claude 087 API timeout produced no file; adds no formal queue IDs; converts CHARPLAN-085 into 12 draft CARD-087-01~12 task cards and 6 execution waves; covers Decimal/string, console_models, domain purity, reconciliation_lock SQLite, bnb_bridge fact shape, legacy vocabulary, Owner terminology, dict/Any density, common runtime pipe boundary, readmodel response shape, coverage gap, and goal-status projection; confirms current Markdown total=96, JSON blocks=28, formal Q sections=89; recommendation_is_binding=false; formal_queue_update=false).
Characterization taskcard readiness audit is at output/claude-token-burn/CLAUDE-FINAL-CHARREADINESS-088-characterization-taskcard-readiness-audit.md (complete; adds no formal queue IDs; Claude 088 created the file successfully; reviews all 12 CARD-087 draft cards and identifies 3 first-wave-ready cards (CARD-087-01/02/03), 0 cards waiting for Codex decision, 2 cards needing fixture prep (CARD-087-05/10), and CARD-087-11 as final synthesis; confirms current Markdown total=97, JSON blocks=29, formal Q sections=89; recommendation_is_binding=false; formal_queue_update=false).
Characterization first-wave handoff is at output/claude-token-burn/CLAUDE-FINAL-FIRSTWAVE-089-characterization-first-wave-handoff.md (complete; adds no formal queue IDs; Claude 089 created the file successfully; expands the first-wave-ready CARD-087-01/02/03 into FW-089-A/B/C future worker packets for readmodels Decimal/string contract, console_models type contract, and domain purity import scanner; confirms current Markdown total=98, JSON blocks=30, formal Q sections=89; recommendation_is_binding=false; formal_queue_update=false).
Characterization first-wave preflight checklist is at output/claude-token-burn/CLAUDE-FINAL-FIRSTWAVEPREFLIGHT-090-characterization-first-wave-preflight-checklist.md (complete; adds no formal queue IDs; Claude 090 created the file successfully; defines preconditions, file-boundary checks, PFC-090-A/B/C preflight cards, abort conditions, evidence capture, and rollback notes for FW-089-A/B/C; confirms current Markdown total=99, JSON blocks=31, formal Q sections=89; recommendation_is_binding=false; formal_queue_update=false).
Token-burn 100 artifact milestone snapshot is at output/claude-token-burn/CLAUDE-FINAL-MILESTONE-091-token-burn-100-artifact-snapshot.md (complete; adds no formal queue IDs; Claude 091 created the file successfully; summarizes the 100 Markdown / 32 JSON / 89 formal-Q milestone, 8 organized areas, 8 ready-but-not-authorized items, mainline protection boundary, next best Claude-token uses, and the 085->087->088->089->090 characterization chain; recommendation_is_binding=false; formal_queue_update=false).
Characterization first-wave test draft pack is at output/claude-token-burn/CLAUDE-FINAL-FIRSTWAVEDRAFTS-092-characterization-first-wave-test-draft-pack.md (complete via Codex reconciliation after Claude 092 worker was interrupted without producing a file; adds no formal queue IDs; converts FW-089-A/B/C and PFC-090-A/B/C into 3 future test draft sections for readmodel Decimal/string behavior, console_models type contract, and domain purity import scanning; includes 3 fenced Python skeletons, 11 draft test cases, readiness table, and JSON summary; confirms expected current Markdown total=101, JSON blocks=33, formal Q sections=89; recommendation_is_binding=false; formal_queue_update=false).
Characterization first-wave fixture/import map is at output/claude-token-burn/CLAUDE-FINAL-FIRSTWAVEFIXTUREMAP-093-characterization-first-wave-fixture-import-map.md (complete via Codex reconciliation after Claude 093 worker was interrupted without producing a file; adds no formal queue IDs; maps future imports, fixture object shapes, field lists, assertion focus, likely failure modes, and Codex review notes for FW-089-A/B/C; includes read-only AST fact that src/domain currently has exactly 2 forbidden-prefix imports, both known logger exceptions; confirms expected current Markdown total=102, JSON blocks=34, formal Q sections=89; recommendation_is_binding=false; formal_queue_update=false).
Characterization first-wave execution plan is at output/claude-token-burn/CLAUDE-FINAL-FIRSTWAVEEXECPLAN-094-characterization-first-wave-execution-plan.md (complete; adds no formal queue IDs; Claude 094 created the file successfully; recommends future post-mainline execution order FW-089-B -> FW-089-A -> FW-089-C, explains why B lands first, A second, C last, and records EO-1~EO-5 abort conditions plus no-current-authorization statement; confirms expected current Markdown total=103, JSON blocks=35, formal Q sections=89; recommendation_is_binding=false; formal_queue_update=false).
Characterization first-wave Codex task-card drafts are at output/claude-token-burn/CLAUDE-FINAL-FIRSTWAVECARDS-095-characterization-first-wave-codex-taskcards.md (complete via Codex reconciliation after Claude 095 worker was interrupted without producing a file; adds no formal queue IDs; converts 094 execution order into 3 future Codex task-card drafts for FW-089-B, FW-089-A, and FW-089-C, each with Task ID/Goal/Why/Allowed/Forbidden/Requirements/Tests/Done When/Hard Stop/Parallelism/Evidence to Capture; confirms expected current Markdown total=104, JSON blocks=36, formal Q sections=89; recommendation_is_binding=false; formal_queue_update=false).
Characterization first-wave evidence template is at output/claude-token-burn/CLAUDE-FINAL-FIRSTWAVEEVIDENCE-096-characterization-first-wave-evidence-template.md (complete; adds no formal queue IDs; Claude 096 created the file successfully; defines shared evidence packet, FW-089-B/A/C per-worker checklists, Codex ACCEPT/NEEDS_FIX/HARD_STOP/DEFER decision table, and post-run handoff format; Codex corrected FW-089-C filename/prefix details; confirms expected current Markdown total=105, JSON blocks=37, formal Q sections=89; recommendation_is_binding=false; formal_queue_update=false).
Characterization first-wave Go/No-Go gate is at output/claude-token-burn/CLAUDE-FINAL-FIRSTWAVEGATE-097-characterization-first-wave-go-no-go-gate.md (complete; adds no formal queue IDs; Claude 097 created the file successfully; defines entry criteria for starting FW-089-B, progression criteria from FW-089-B to FW-089-A and FW-089-A to FW-089-C, S-1~S-8 hard stops, and Codex decision checklist before code slimming; confirms expected current Markdown total=106, JSON blocks=38, formal Q sections=89; recommendation_is_binding=false; formal_queue_update=false).
Characterization-to-slimming decision bridge is at output/claude-token-burn/CLAUDE-FINAL-FIRSTWAVESLIMBRIDGE-098-characterization-to-slimming-decision-bridge.md (complete; adds no formal queue IDs; Claude 098 created the file successfully; maps FW-089-B/A/C evidence outcomes to PROCEED_TO_DECIMAL_STRING_REFACTOR, PROCEED_TO_DOMAIN_IMPORT_CLEANUP, HOLD_FOR_MORE_CHARACTERIZATION, or HARD_STOP, and lists code areas forbidden until Codex explicitly authorizes slimming; confirms expected current Markdown total=107, JSON blocks=39, formal Q sections=89; recommendation_is_binding=false; formal_queue_update=false).
Characterization-to-slimming task-card drafts are at output/claude-token-burn/CLAUDE-FINAL-FIRSTWAVESLIMCARDS-099-characterization-to-slimming-taskcard-drafts.md (complete; adds no formal queue IDs; Claude 099 created the file successfully; converts FIRSTWAVESLIMBRIDGE-098 decisions into 4 future draft cards for Decimal/string planning, domain import cleanup planning, additional characterization fallback, and hard-stop escalation; confirms expected current Markdown total=108, JSON blocks=40, formal Q sections=89; recommendation_is_binding=false; formal_queue_update=false).
Characterization first-wave readiness bundle is at output/claude-token-burn/CLAUDE-FINAL-FIRSTWAVEREADINESS-100-characterization-first-wave-readiness-bundle.md (complete; adds no formal queue IDs; Claude 100 created the file successfully and Codex corrected JSON artifact_id; bundles reports 092 through 099 into one future Codex readiness entry with source map, FW-089-B/A/C readiness table, FW-089-B minimal start packet, evidence acceptance checklist, and slimming decision continuation summary; confirms expected current Markdown total=109, JSON blocks=41, formal Q sections=89; recommendation_is_binding=false; formal_queue_update=false).

Current branch: codex/owner-runtime-console-v1
Mainline status: active acceptance in progress

Immediate safe review actions (no mainline interference):
- Q-001: Review the 27-file agent instruction cleanup diff; current token-burn thread does not authorize commit
- Q-002: Review the forbidden-term scanner plan for owner-runtime-console visual:qa; current token-burn thread does not authorize implementation
- Q-020: Local artifact hygiene audit is complete; Q-023/Q-024 require explicit Owner approval before .gitignore or cleanup changes
- Q-089: Script cleanup execution manifest is complete; Q-090 preconditions checklist is complete; TASKPACK-062 is complete; ARCHAUDIT-063 is complete; QATASKPACK-064 is complete; MODULEMAP-065 is complete; DECISIONPACK-066 is complete; INTAKEPACK-067 is complete; HANDOFFPACK-068 is complete; GOVAUDIT-069 is complete; QATASKPACK-071 is complete (adds no formal queue IDs); PUBAUDIT-072 is complete (adds no formal queue IDs); REFAUDIT-073 is complete (adds no formal queue IDs); SECRETAUDIT-074 is complete (adds no formal queue IDs; 0 P0/P1/P2, 4 P3); TASKGRAPH-075 is complete (adds no formal queue IDs; dependency/parallelism map for 89 formal Q- sections; 8 recommended execution waves; 12 risks); READINESS-076 is complete (adds no formal queue IDs; readiness gate audit for 89 formal Q- sections; 6 readiness classes (Review Now 2 / Output-Only 24 / Blocked Mainline 51 / Blocked Codex 11 / Do Not Run 4 / Blocked Pub 2; 5 overlap items); 8 wave go/no-go gates; Wave 0 is review-only and does not authorize implementation or commit; 14 risks); CONSISTENCY-077 is complete (adds no formal queue IDs; taskgraph-readiness alignment audit; 0 P0/P1/P2 after Codex wording fix, 5 P3; draft boundary intact; formal_queue_update=false); CONTROLBRIEF-078 is complete (adds no formal queue IDs; governance control brief; Wave 0 REVIEW-ONLY; recommendation_is_binding=false; 12 risks); QUEUEGUARD-079 is complete (adds no formal queue IDs; authorization drift audit; initial 3 P2 findings fixed by Codex; current 0 P0/P1/P2, 7 P3; drift_fixed_count=3; formal_queue_update=false); ISOLATION-080 is complete (adds no formal queue IDs; current non-output modified count=0; token-burn lane remains output-only; mainline/source/docs/scripts/tests/deploy paths quarantined from this lane; formal_queue_update=false); ARTIFACTHEALTH-081 is complete via Codex reconciliation (adds no formal queue IDs; Claude worker produced no report file; current 90 Markdown, 22 JSON blocks, 89 formal Q sections, 0 duplicate Q headings, 0 draft heading leaks; formal_queue_update=false); ROADMAPXWALK-082 is complete (adds no formal queue IDs; Claude alarm exit 142 after writing file; Codex corrected metadata; maps 12 roadmap tracks; current 91 Markdown, 23 JSON blocks, 89 formal Q sections; formal_queue_update=false); DIFFREVIEW-083 is complete (adds no formal queue IDs; transient runtime_dry_run_audit_chain diff review; safety invariants PASS; current script diff empty after Codex reconciliation; 0 P0, 1 P1, 2 P2, 2 P3; formal_queue_update=false); SOURCERISK-084 is complete via Codex reconciliation (adds no formal queue IDs; Claude worker timed out without producing a file; current 93 Markdown, 25 JSON blocks, 89 formal Q sections; 10 source-risk watchlist items; formal_queue_update=false); CHARPLAN-085 is complete (adds no formal queue IDs; Claude worker created the file; current 94 Markdown, 26 JSON blocks, 89 formal Q sections; 12 characterization-first candidate checks; formal_queue_update=false); SCORECARD-086 is complete (adds no formal queue IDs; Claude worker created the file; current 95 Markdown, 27 JSON blocks, 89 formal Q sections; overall estimate=70, weighted score=62, actual code slimming=10; formal_queue_update=false); CHARCARDS-087 is complete via Codex reconciliation (adds no formal queue IDs; Claude worker API timed out without producing a file; current 96 Markdown, 28 JSON blocks, 89 formal Q sections; 12 draft CARD-087 task cards and 6 waves; formal_queue_update=false); CHARREADINESS-088 is complete (adds no formal queue IDs; Claude worker created the file; current 97 Markdown, 29 JSON blocks, 89 formal Q sections; first-wave-ready CARD-087-01/02/03, fixture-prep CARD-087-05/10, final synthesis CARD-087-11; formal_queue_update=false); FIRSTWAVE-089 is complete (adds no formal queue IDs; Claude worker created the file; current 98 Markdown, 30 JSON blocks, 89 formal Q sections; FW-089-A/B/C handoff packets for CARD-087-01/02/03; formal_queue_update=false); FIRSTWAVEPREFLIGHT-090 is complete (adds no formal queue IDs; Claude worker created the file; current 99 Markdown, 31 JSON blocks, 89 formal Q sections; PFC-090-A/B/C preflight cards for FW-089-A/B/C; formal_queue_update=false); MILESTONE-091 is complete (adds no formal queue IDs; Claude worker created the file; current 100 Markdown, 32 JSON blocks, 89 formal Q sections; summarizes 8 organized areas, 8 ready-not-authorized items, and the 085->087->088->089->090 characterization chain; formal_queue_update=false); FIRSTWAVEDRAFTS-092 is complete via Codex reconciliation (adds no formal queue IDs; Claude worker was interrupted without producing a file; current 101 Markdown, 33 JSON blocks, 89 formal Q sections; provides 3 future test draft sections and 3 fenced Python skeletons for FW-089-A/B/C; formal_queue_update=false); FIRSTWAVEFIXTUREMAP-093 is complete via Codex reconciliation (adds no formal queue IDs; Claude worker was interrupted without producing a file; current 102 Markdown, 34 JSON blocks, 89 formal Q sections; maps imports/fixtures/assertions/failure modes for FW-089-A/B/C and records 2 known domain logger import exceptions; formal_queue_update=false); FIRSTWAVEEXECPLAN-094 is complete (adds no formal queue IDs; Claude worker created the file successfully; current 103 Markdown, 35 JSON blocks, 89 formal Q sections; recommends future execution order FW-089-B -> FW-089-A -> FW-089-C and records EO-1~EO-5 abort conditions; formal_queue_update=false); FIRSTWAVECARDS-095 is complete via Codex reconciliation (adds no formal queue IDs; Claude worker was interrupted without producing a file; current 104 Markdown, 36 JSON blocks, 89 formal Q sections; provides 3 future Codex task-card drafts for FW-089-B/FW-089-A/FW-089-C with full required fields; formal_queue_update=false); FIRSTWAVEEVIDENCE-096 is complete (adds no formal queue IDs; Claude worker created the file successfully; current 105 Markdown, 37 JSON blocks, 89 formal Q sections; provides shared evidence packet, per-worker checklists, Codex acceptance decision table, and post-run handoff format for FW-089-B/FW-089-A/FW-089-C; formal_queue_update=false); FIRSTWAVEGATE-097 is complete (adds no formal queue IDs; Claude worker created the file successfully; current 106 Markdown, 38 JSON blocks, 89 formal Q sections; defines entry/progression/stop criteria and code-slimming decision checklist for FW-089-B -> FW-089-A -> FW-089-C; formal_queue_update=false); FIRSTWAVESLIMBRIDGE-098 is complete (adds no formal queue IDs; Claude worker created the file successfully; current 107 Markdown, 39 JSON blocks, 89 formal Q sections; maps first-wave evidence outcomes to Decimal/string refactor, domain import cleanup, more characterization, or hard stop decisions; formal_queue_update=false); FIRSTWAVESLIMCARDS-099 is complete (adds no formal queue IDs; Claude worker created the file successfully; current 108 Markdown, 40 JSON blocks, 89 formal Q sections; provides 4 future task-card drafts for Decimal/string planning, domain cleanup planning, additional characterization fallback, and hard-stop escalation; formal_queue_update=false); FIRSTWAVEREADINESS-100 is complete (adds no formal queue IDs; Claude worker created the file successfully and Codex corrected JSON artifact_id; current 109 Markdown, 41 JSON blocks, 89 formal Q sections; bundles 092~099 into one future readiness entry with source map, ready workers, FW-089-B start packet, evidence checklist, and slimming continuation summary; formal_queue_update=false); draft IDs 091-108 remain inside TASKPACK-062, the twelve QATASKPACK-064 QA cards remain inside QATASKPACK-064, the five DCHF-071-A~E QA cards remain inside QATASKPACK-071, S0/S1/S2 intake task skeletons remain inside INTAKEPACK-067, CARD-087-01~12 remain inside CHARCARDS-087/CHARREADINESS-088/FIRSTWAVE-089/FIRSTWAVEPREFLIGHT-090/FIRSTWAVEDRAFTS-092/FIRSTWAVEFIXTUREMAP-093/FIRSTWAVEEXECPLAN-094/FIRSTWAVECARDS-095/FIRSTWAVEEVIDENCE-096/FIRSTWAVEGATE-097/FIRSTWAVESLIMBRIDGE-098/FIRSTWAVESLIMCARDS-099/FIRSTWAVEREADINESS-100, and none of those draft sets are formal queue entries yet

Pending Codex decisions:
- Q-011: SOR-001 mode (recommended: Option B — collapse to armed_observation)
- Q-012: Review vocabulary (recommended: Option C — mapping table in board contract, already applied)
- Q-013: Freshness semantics (recommended: Option A — keep upstream enum-only, docs already applied)
- Q-014: trading-console classification
- Q-026: Handoff metadata enrichment (source_commit / review_outcome_vocabulary / signal Owner mapping)
- Q-087: First-real-submit shared infrastructure decision pack is complete; implementation tasks T-059-A~F wait for mainline acceptance or explicit clearance

After mainline acceptance:
- Q-004~Q-006: Agent config cleanup tail
- Q-007~Q-009: Safety test cards (FinalGate, partial-fill, notification)
- Q-010: Handoff QA cards
- Q-025: Historical dry-run artifact compatibility note
- Q-027: Owner Console dry-run summary UI hardening
- Q-083~Q-088: Remaining runtime long-tail follow-ups (core-touching guard headers, analyze/research archive, data-pipeline archive, compat wrapper archive, first-real-submit shared infrastructure decision pack complete, BNB/inspect archive)
- MANIFEST-060: Use as the post-mainline script slimming handoff; it contains protected sets, archive batches, hard stops, and a max-1 execution wave table
- TASKPACK-062: Use as the post-mainline draft task-card library for ACTIVE_SCRIPT_MAP promotion, CODEX-GUARDED headers, archive batches A-J, and T-059-A~F shared-infra migration; do not bulk-distribute archive/move cards
- ARCHAUDIT-063: Use as post-mainline architecture slimming evidence for readmodels float, console_models float, reconciliation_lock SQLite, bnb bridge dict/Any, mi001/bnb/personal_campaign semantic debt, and targeted test gaps
- QATASKPACK-064: Use as the post-mainline QA task-card library for ARCHAUDIT-063; keep core/bridge/storage cards max-1 and keep global Claude concurrency <=3
- MODULEMAP-065: Use as post-mainline module-boundary evidence for giant files, cross-layer dependency cleanup, extraction candidates, and architecture options; recommended option remains non-binding until Codex approval
- DECISIONPACK-066: Use as non-binding Codex decision input for module-boundary slimming options; Option A recommendation is post-mainline and `recommendation_is_binding=false`
- INTAKEPACK-067: Use as the post-mainline intake sprint plan after P0 first bounded live-order acceptance is complete or explicitly paused by Owner/Codex; it does not authorize current implementation
- Q-028~Q-088: Runtime semantics slimming, Owner-language contract, script-map queue, proof dependency migration, consolidated Active Script Map, promotion draft, Tokyo deploy/support audit, verify_runtime audit, next_attempt/fresh/active_observation audit, remaining runtime long-tail audit, fresh authorization fixture decision, and script cleanup waves from ARCHDEBT-037 / QA-038 / SCRIPTAUDIT-039~058 / DECISIONPACK-057 / SCRIPTMAP-053 / TASKPACK-052 / DECISIONPACK-046 / CHECKLIST-048 / DECISIONPACK-049

Do NOT touch during mainline: src/**, tests/**, scripts/**, deploy/**, live-config.env, owner-runtime-console/src/**.
```

---

*End of NEXT_QUEUE.*
