---
title: MAIN_CONTROL_ROADMAP
status: CURRENT
authority: docs/current/MAIN_CONTROL_ROADMAP.md
last_verified: 2026-06-17
---

# Main Control Roadmap

## Purpose

This is the short planning table for the main runtime window.

The main goal is still the StrategyGroup runtime pilot:

```text
Owner enables a StrategyGroup.
The system observes, checks, executes inside official boundaries, protects,
reconciles, settles, records, and reports Owner-readable state.
```

The first-stage acceptance target is narrower and more operational:

```text
Complete the first selected StrategyGroup + tiny risk bounded real-order loop
when a fresh signal exists and all official runtime gates pass.
```

Dry-run audit and source readiness are support tracks for that target. Frontend
UI work has been externalized and is no longer part of the main runtime goal.

This file is not a research backlog, frontend design spec, or historical packet
index.

## Current Tracks

| Track | Owner outcome | Current owner | Current status | Next checkpoint |
| --- | --- | --- | --- | --- |
| P0 First Bounded Live Order Closure | First selected StrategyGroup + tiny risk real order completes through official gates, finalize, reconciliation, settlement, and review | Main runtime window | active, waiting for fresh signal | On fresh signal, pause lower tracks and drive RequiredFacts -> candidate/auth -> FinalGate -> Operation Layer -> real submit -> close loop |
| P0 Runtime Product State Repair | Owner Console can read one stable source-readiness state instead of interpreting packets | Main runtime window | mainline implemented | Keep `owner-console-source-readiness.json` / API stable and refresh it from Tokyo watcher packets |
| P0 Runtime Pilot Liveness | Fresh signal can continue to candidate/auth/FinalGate/Operation Layer evidence prep without accidental watcher-side attempt burn | Main runtime window | active | Rerun fresh signal chain through standing-authorized evidence prep, action-time FinalGate, and official Operation Layer only |
| P0 Shared Runtime Pipeline Validation | Prove that execution-chain fixes are shared by all StrategyGroups and not SOR-specific patches | Main runtime window | active | After common chain closes, run cross-StrategyGroup dry-run/admission validation for MPG / TEQ / FBS / PMR / SOR |
| P0 Runtime Dry-Run Audit Chain | Main chain can expose evidence/endpoint/gate breakage without waiting for market opportunity | Main runtime window | deployed | Keep local and Tokyo `runtime-dry-run-audit-chain.json` covering the full non-executing close-loop shape |
| P0 Safe Tokyo Operations | Tokyo watcher stays current, alive, bounded, and auditable | Main runtime window | active | Verify watcher reports and bounded deploys after each runtime-code change |
| P0 Goal Status Summary | Main goal loop can decide waiting vs processing vs deploy/safety blocker from one read-only packet | Main runtime window | active | Refresh `strategygroup-runtime-goal-status.json` after watcher ticks and use it before advancing real-order actions |
| P0.5 Runtime Interaction Optimization | Owner can see what Codex did on Tokyo without reading many SSH fragments | Main runtime window | active | Use one L1 runtime snapshot for routine checks and L3 summaries for deploy/static publish actions |
| P1 Owner Console Mainline Stabilization | External frontend can consume one stable source-readiness/readmodel contract | Main runtime window | paused in mainline | Keep readmodel/API stable; do not maintain static frontend or UI QA in this worktree |
| P1 StrategyGroup Research Handoff | Strategy research enters main control only through reviewed handoff packs | Strategy research window | active separately | Keep research artifacts out of main runtime worktree except reviewed handoff input |
| P2 Historical Debt Reduction | Historical docs/code do not obscure current pilot behavior | Main runtime window | pending | Compress/archive only after P0 source and runtime state are stable |
| P2 LLM Assistance | LLM supports audit/readiness/notification without changing execution authority | Main runtime window | pending | Start with read-only audit summaries and Feishu notification text only |
| P2 External Information Capture | External information can inform research/watch context without becoming execution authority | Strategy/research window first | pending | Treat as research input, not live-submit permission |

## P0 Subgoal: Owner Console Source Readiness Productization

### Current State

Owner Console exploration is no longer treated as an isolated authority source.
The main runtime branch now owns the source-readiness contract and exposes the
machine-readable packet/API that the console consumes.

### Scope

Build one stable Owner Console source-readiness surface from main runtime facts:

```text
StrategyGroup catalog
runtime pilot status
watcher status
live facts readiness
account funds
orders
positions
protection
reconciliation detail state
operation audit detail state
runtime dry-run audit state
StrategyGroup runtime goal status
real-order readiness detail state
```

### Required Artifacts

| Artifact | Path |
| --- | --- |
| Human confirmation | `docs/current/OWNER_CONSOLE_SOURCE_READINESS_CONFIRMATION.md` |
| Machine-readable packet | `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/owner-console-source-readiness.json` |
| API surface | `GET /api/trading-console/owner-console-source-readiness` |
| Watcher refresh hook | `scripts/refresh_strategygroup_runtime_product_state_packets.py` |

### Acceptance

| Requirement | Expected result |
| --- | --- |
| StrategyGroup catalog ready | Owner Console can show MPG / TEQ / FBS / PMR / SOR even if runtime overlay degrades |
| Runtime source reachable | Source status is `ready` or `degraded`, not an empty strategy list |
| Orders source readable and empty | Source status is `ready_empty`, Owner language is `暂无订单` |
| Positions source readable and empty | Source status is `ready_empty`, Owner language is `暂无持仓` |
| Account facts readable | Source status is `ready`, Owner language is `资金正常` |
| Watcher waiting for signal | Owner state is `waiting_for_opportunity`, Owner language is `等待机会` |
| Runtime dry-run audit passed | Source status is `ready`, Owner language is `审计演练正常` |
| Runtime goal status reports liveness or safety degradation | Owner state is `needs_intervention` or `temporarily_unavailable`, not `waiting_for_opportunity` |
| Real-order readiness matrix available | `real_order_readiness` summarizes pass/waiting/blocked counts and submit-blocking keys without requiring raw packet reading |
| Reconciliation/audit detail missing | Detail degrades without hiding StrategyGroups |
| Safety | No order, exchange write, FinalGate bypass, Operation Layer bypass, secret mutation, profile expansion, sizing change, withdrawal, or transfer |

### 2026-06-16 Checkpoint

| Item | Result |
| --- | --- |
| Source-readiness API | Returns `market_opportunity=等待机会`, `funds=资金正常`, `orders=暂无订单`, `positions=暂无持仓`, `protection=保护正常`, `runtime_dry_run_audit=审计演练正常` in the real-backend smoke fixture |
| Owner Console UI | Homepage treats readable funds/orders/positions/protection as business-ready even when candidate-prep details are still progressive; StrategyGroup rows show `等待机会` during no-signal observation |
| System page | Shows `审计演练` as a secondary system-health item, not a homepage gate |
| Visual governance | Strategy rows show one primary health chip plus one Owner-readable summary sentence instead of a four-chip evidence wall |
| Verification | Python source-readiness/dry-run tests, frontend build, real-backend smoke, normal smoke, state smoke, and visual QA passed |
| Runtime goal overlay | Source-readiness API now reads `strategygroup-runtime-goal-status.json`; `runtime_liveness_degraded` overrides the Owner state to `需要介入` so the console does not mislabel liveness repair as market waiting |
| Real-order readiness detail | Source-readiness API now forwards `real_order_readiness` from goal-status so the console can distinguish waiting-for-market from submit-blocking safety conditions through one API |
| Owner Console real-order card | Mainline UI now consumes `real_order_readiness` and shows `实盘边界`, pass/waiting/blocked counts, and one Owner-readable action state without exposing internal gate names on the homepage |

### 2026-06-17 Selected Scope Refresh Checkpoint

| Item | Result |
| --- | --- |
| Selected StrategyGroup scope | Watcher service now carries default `BRC_SELECTED_STRATEGY_GROUP_ID=MPG-001`, `BRC_STRATEGYGROUP_MAX_SYMBOLS=3`, and `BRC_STRATEGYGROUP_STALE_AFTER_SECONDS=180`; `/home/ubuntu/brc-deploy/env/runtime-signal-watcher.env` may override them |
| Product-state refresh | `80-product-state-refresh.conf` now performs signed GET-only live-facts precollection and writes `product-state-refresh-packet.json` before refreshing Owner Console source-readiness |
| Stale drop-in hygiene | Tokyo deploy planner removes legacy `50-product-state-refresh.conf` so old refresh semantics do not race or overwrite current selected-scope packets |
| Resume dispatcher guard | `40-resume-dispatcher.conf` passes the selected StrategyGroup scope to `runtime_signal_watcher_resume_dispatcher.py`; actionable fresh-authorization, FinalGate, or Operation Layer dispatch is blocked unless the packet proves the action belongs to the selected StrategyGroup |
| Safety | This remains readmodel/live-facts GET-only work; it does not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

### 2026-06-17 Runtime Objective Chain Visibility Checkpoint

| Item | Result |
| --- | --- |
| Objective chain segments | `runtime_execution_chain_closure_status.py` projects six target-aligned segments: fresh/mock signal, RequiredFacts, candidate/auth evidence, action-time FinalGate, official Operation Layer evidence handoff, and disabled/dry-run proof |
| Daily monitor | `run_strategygroup_runtime_daily_check.py` now carries goal-chain ready/missing counts separately from lower-level implementation checks |
| Goal progress | `run_strategygroup_runtime_goal_progress_audit.py` now degrades P0.5 engineering rehearsal when any objective chain segment is missing |
| Old deployed packets | Missing `ready_goal_chain_segments` is reported as `unknown`, not as `0 ready / 0 missing` |
| Safety | This is non-executing visibility work only; it does not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

### 2026-06-17 Runtime Objective Chain Deploy Checkpoint

The target-chain visibility change was pushed and deployed to Tokyo through the
standing-authorization git deploy path. The deployment repaired the old Tokyo
monitor gap where `required_facts_readiness_checked` was missing from the
runtime dry-run audit summary.

| Item | Result |
| --- | --- |
| Deployed runtime head | `0e2af29a040159857a29b705c563fff27e651a7b` |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-0e2af29a-objective-chain-progress` |
| Runtime deploy apply | `status=applied`, `interaction.level=L3_bounded_deploy_apply`, `remote_interaction_count=7`, `blockers=[]` |
| Postdeploy snapshot | `status=ready`, `runtime_dry_run_audit_passed=true`, `runtime_execution_chain_closure_status_ready=true`, `watcher_timer_active=true`, `source_readiness_ready=true` |
| Objective chain | `ready_goal_chain_segments=6`, `missing_or_failed_goal_chain_segments=[]` |
| Daily progress | `status=waiting_for_market`, `notification=DONT_NOTIFY`, `目标链路段: 6 ready / 0 missing` |
| Goal progress | `P0=waiting_for_market`, `P0.5=ready`, `blockers=[]`, `product_gaps=[]` |
| Safety | Deploy/postdeploy checks did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

### 2026-06-17 Runtime Monitor Atomic Artifact Checkpoint

The runtime monitor scripts now write their machine-readable artifacts through
same-directory temporary files followed by atomic replacement. This prevents a
parallel reader from seeing an empty or partially-written snapshot during
postdeploy or fresh-signal resume checks.

| Item | Result |
| --- | --- |
| Snapshot output | `probe_tokyo_runtime_snapshot.py --output-json` writes the L1 snapshot atomically |
| Daily check output | `run_strategygroup_runtime_daily_check.py` writes JSON and Owner progress artifacts atomically |
| Goal progress output | `run_strategygroup_runtime_goal_progress_audit.py` writes JSON and Owner progress artifacts atomically |
| Postdeploy verification | Current Tokyo snapshot remains `status=ready`, `ready_goal_chain_segments=6`, `missing_or_failed_goal_chain_segments=[]` |
| Safety | The monitor hardening is file-output-only; it does not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

### 2026-06-17 Runtime Monitor Atomic Deploy Checkpoint

The monitor artifact hardening was pushed and deployed to Tokyo. This ensures
future postdeploy and fresh-signal resume checks can write their local snapshot,
daily-check, and goal-progress artifacts without exposing empty or partially
written JSON to parallel readers.

| Item | Result |
| --- | --- |
| Deployed runtime head | `14f76105efedafdc0be7e2b49d9d8618ad51a0b1` |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-14f76105-monitor-atomic-artifacts` |
| Runtime deploy apply | `status=applied`, `interaction.level=L3_bounded_deploy_apply`, `remote_interaction_count=7`, `blockers=[]` |
| Postdeploy snapshot | `status=ready`, `runtime_dry_run_audit_passed=true`, `runtime_execution_chain_closure_status_ready=true`, `watcher_timer_active=true`, `source_readiness_ready=true` |
| Objective chain | `ready_goal_chain_segments=6`, `missing_or_failed_goal_chain_segments=[]` |
| Daily progress | `status=waiting_for_market`, `notification=DONT_NOTIFY`, `目标链路段: 6 ready / 0 missing` |
| Goal progress | `P0=waiting_for_market`, `P0.5=ready`, `blockers=[]`, `product_gaps=[]` |
| Safety | Deploy/postdeploy checks did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

### 2026-06-17 Deploy Channel Diagnostic Checkpoint

Tokyo deploy readiness now distinguishes deployment channel failures from
runtime gate failures. When the local-to-Tokyo path cannot reach SSH/TCP, the
git owner deploy packet remains blocked and surfaces explicit channel blockers
instead of collapsing into a generic readonly-probe failure.

| Item | Result |
| --- | --- |
| Connectivity probe | `scripts/probe_tokyo_runtime_governance_readonly.py` can build a non-mutating `tokyo_runtime_governance_connectivity_probe` |
| TCP blocker | Unreachable SSH/TCP produces `tokyo_tcp_22_unreachable` |
| Deploy packet | `scripts/build_tokyo_runtime_governance_git_owner_deploy_packet.py` catches readonly probe errors and emits a blocked JSON packet |
| Safety | The diagnostic does not modify remote files, run migrations, restart services, read secrets, create orders, call OrderLifecycle, call exchange APIs, withdraw, or transfer |

Historical observed state for the diagnostic `a9e3e0f2` deploy packet was:

```text
packet_status=blocked
tokyo_connectivity_blockers=tokyo_tcp_22_unreachable
```

That was a deploy-channel diagnostic blocker only. It did not imply that the
StrategyGroup runtime chain, Owner Console source readiness, or dry-run audit
chain failed. Later bounded git deploys reached `postdeploy_accepted`; use the
latest deploy-channel packet or the newest checkpoint below for current state.

### 2026-06-17 Owner Console Deploy Channel Source Checkpoint

Owner Console source readiness now carries deploy-channel health as a
non-critical `sourceHealth` item. This keeps deployment connectivity distinct
from market opportunity, runtime liveness, live facts, and real-order safety.

| Item | Result |
| --- | --- |
| Backend source | `owner-console-source-readiness` reads `BRC_TOKYO_DEPLOY_CHANNEL_STATUS_PATH` or `tokyo-deploy-channel-status.json` under the watcher report directory |
| Default state | Missing deploy-channel packet maps to `ready_empty` / `部署通道未检查` |
| Degraded state | Blocked deploy packet with `tokyo_tcp_22_unreachable` maps to `degraded` / `部署通道暂不可用` |
| Owner UI | The status appears only on the system/source-health page, not as a homepage primary gate |
| Safety | Deploy-channel degradation does not hide StrategyGroups, create orders, call exchange write APIs, bypass FinalGate, or bypass Operation Layer |

## P0.5 Subgoal: Runtime Interaction Optimization

### Purpose

Routine Tokyo checks should not appear as many unrelated server interactions.
The main runtime window should use one compact interaction report whenever
possible:

```text
L1 read-only snapshot
-> Owner-readable current state
-> product gaps or blockers
-> next safe action
```

### 2026-06-17 Checkpoint

| Item | Result |
| --- | --- |
| Interaction taxonomy | `scripts/runtime_interaction_levels.py` defines L0-L5 as a machine-readable policy for local read, read-only remote checks, dry-run rehearsal, bounded server mutation, action-time pre-execution checks, and official tiny real-order actions |
| Unified snapshot | `scripts/probe_tokyo_runtime_snapshot.py` collects runtime release, watcher timer/service, backend service, source-readiness, goal-status, latest-summary, dry-run audit, and execution-chain closure facts through one read-only SSH interaction |
| Interaction labels | Snapshot reports `L1_readonly_snapshot`; deploy executor reports `L1_deploy_plan_only` or `L3_bounded_deploy_apply` |
| Deploy summary | `scripts/execute_tokyo_runtime_governance_git_deploy.py` now emits `owner_summary`, changed/not-changed fields, safety flags, and whether frontend static publishing is included |
| Batched deploy apply | `scripts/plan_tokyo_runtime_governance_git_deploy.py` batches contiguous Tokyo operations so the git deploy path uses 4 direct SSH commands instead of many small server command fragments |
| Deploy interaction count | `scripts/execute_tokyo_runtime_governance_git_deploy.py` writes `interaction.remote_interaction_count`; current git deploy apply budget is 7 counted remote interactions including readonly/postdeploy verifier probes |
| Frontend scope | Static frontend publishing has been removed from the main runtime worktree; future UI work should live in a separate frontend project and consume the stable readmodel/API |
| Deploy session summary | `scripts/run_tokyo_runtime_deploy_session.py` combines runtime deploy and one postdeploy daily check into a single Owner-readable report with highest interaction level, total remote interactions, mutation status, and real-order proximity |
| Tokyo verification | L1 snapshot reports the runtime head, watcher/backend active state, source-readiness, dry-run audit, execution-chain closure status, and safety invariants; it no longer reads nginx or static frontend release files |
| Daily check | `scripts/run_strategygroup_runtime_daily_check.py` consumes one L1 snapshot and returns `waiting_for_market`, `degraded`, or `blocked` with Owner-readable current action and safety invariants |
| Monitor baseline | `docs/current/RUNTIME_MONITOR_BASELINE.json` is the machine-readable SSOT for expected runtime head, low-interaction check modes, and the server-side signal-detection source, so heartbeat automation can run without hardcoded deployment SHAs or accidental extra probes |
| Interaction budget | Daily check defaults to `--max-remote-interactions 1`; if the source snapshot exceeds the budget, the report becomes a `NOTIFY` engineering blocker instead of silently becoming chatty |
| Notification decision | Daily check now emits `notification.decision` as `DONT_NOTIFY` only for healthy `waiting_for_market`; fresh/processing/degraded/blocked states emit `NOTIFY` so automation does not re-interpret raw checks |
| Heartbeat output | `scripts/run_strategygroup_runtime_daily_check.py --auto-cache --heartbeat` renders the same decision as Codex heartbeat XML; fresh cache stays `L0` / 0 remote interactions, while stale cache may refresh one `L1` snapshot |
| Owner progress output | `scripts/run_strategygroup_runtime_daily_check.py --owner-progress` renders the same one-shot check as a concise Owner-readable progress summary, so manual status reviews do not require extra SSH probes or raw JSON/XML inspection |
| Dry-run coverage visibility | Owner progress output includes the runtime dry-run audit scenario count, so a healthy rehearsal loop reads as `审计演练正常` plus `演练场景: 14` instead of a vague green label |
| Execution-chain closure visibility | L1 snapshot and daily-check read `runtime-execution-chain-closure-status.json`, so healthy non-market closure appears as `非市场链路已收口` without rereading raw audit packets |
| Closure segment projection | `runtime-execution-chain-closure-status.json` now projects key dry-run segments such as fresh-signal fast auto-chain, scoped Operation Layer handoff, submit-blocker matrix, shared runtime pipe, and post-submit guards into `projected_checks`, `ready_segments`, and `missing_or_failed_segments` |
| Goal-chain segment projection | Closure status now also maps lower-level checks into six objective-aligned segments: `fresh_or_mock_signal`, `required_facts_readiness`, `candidate_authorization_evidence`, `action_time_finalgate`, `official_operation_layer_evidence_handoff`, and `disabled_dry_run_proof` |
| Closure segment Owner progress | L1 snapshot and daily-check can carry closure segment counts into Owner progress; older deployed packets without segment fields render `链路段: unknown` instead of falsely reporting `0 ready / 0 missing` |
| Local progress cache | `--output-json` and `--output-owner-progress` can persist the latest daily-check report and Owner progress text; `--from-cache --owner-progress` re-renders the default saved report locally with zero Tokyo interaction |
| Auto cache mode | `--auto-cache --owner-progress` first uses a fresh local cache with `L0` / 0 remote interactions; only missing, stale, or schema-stale cache triggers one `L1` snapshot and refreshes the local cache/progress files |
| Read-vs-collection clarity | Cache-only Owner progress separates `本次读取` from `报告采集`, so a local status review shows `本次远端交互次数: 0` while retaining the last L1 snapshot cost as audit context |
| Cache-only guard | `--from-cache --require-fresh-cache --owner-progress` reads only local cache and converts missing or stale cache into an Owner-readable engineering blocker instead of triggering an extra Tokyo probe |
| Cache schema guard | Cache-only progress checks require the current daily-check report schema; old local reports become an Owner-readable engineering blocker instead of mixing new code with stale cached fields |
| Heartbeat cache refresh | `tokyo-runtime-quiet-monitor` should use the baseline check modes: default status review is `--auto-cache`; explicit signal or regression investigation may force one L1 refresh and write `output/runtime-monitor/latest-daily-check.json` plus `output/runtime-monitor/latest-owner-progress.md` |
| Heartbeat SSOT | `docs/current/RUNTIME_MONITOR_BASELINE.json` now records the exact `heartbeat_check` command used by `tokyo-runtime-quiet-monitor`, preventing automation prompt drift from the repository baseline |
| Quiet-monitor drift audit | `scripts/audit_tokyo_runtime_quiet_monitor.py --owner-progress` compares the local heartbeat automation prompt with `RUNTIME_MONITOR_BASELINE.json`, including daily check and goal-progress commands, using `L0` / 0 remote interactions |
| Quiet-monitor drift cache | The same audit writes `output/runtime-monitor/latest-quiet-monitor-audit.json` and `output/runtime-monitor/latest-quiet-monitor-audit.md`, keeping automation drift review local and reusable |
| Cache freshness visibility | Owner progress output includes `报告时间`, `缓存年龄`, and `缓存状态`; the default stale threshold is 35 minutes and can be adjusted with `--max-cache-age-minutes` |
| Goal progress audit | `scripts/run_strategygroup_runtime_goal_progress_audit.py --owner-progress` reads local daily-check cache plus monitor baseline and reports P0/P0.5 track status with `L0` / 0 remote interactions |
| Goal progress cache | The same audit writes `output/runtime-monitor/latest-goal-progress.json` and `output/runtime-monitor/latest-goal-progress.md`, so status reviews can reuse the latest local progress artifact |
| Goal progress evidence table | Goal progress output now includes a compact Evidence table, including dry-run scenario count, closure segment readiness count, missing closure segment count, interaction source, notification state, and forbidden-effect count |
| Deploy-session check mode | `scripts/run_tokyo_runtime_deploy_session.py --run-daily-check` accepts `--daily-check-mode fresh`, `auto-cache`, or `cache`; postdeploy acceptance stays fresh, while routine reviews can reuse cache |
| Deploy-session cache clarity | Cache-only deploy-session reviews report `interaction.level=L0_local_cache_read` and keep the original `collected_interaction_level` inside the step for audit context |
| Deploy-session Owner progress | `scripts/run_tokyo_runtime_deploy_session.py --run-daily-check --daily-check-mode cache --owner-progress` renders a Markdown progress table with current stage, action, risk, interaction count, server mutation, and real-order proximity |
| Homepage-only visual QA | `owner-runtime-console` exposes `npm run visual:qa:home`, so current P1 frontend work verifies the homepage without pulling unfinished tabs into scope |
| Engineering rehearsal check | L1 snapshot now requires the dry-run audit packet to include required checks such as `fresh_signal_fast_auto_chain_checked`, `dangerous_effects_absent`, `disabled_smoke_not_real_execution_proof`, Operation Layer evidence relay, shared runtime pipeline, and StrategyGroup adapter-boundary coverage |
| UI unauthenticated state | Public homepage now maps HTTP 401 to `需要登录` instead of `后端不可用`, while keeping `资金路径保持关闭` |
| Owner visibility classification | The daily check emits `owner_summary.visibility.category`, and the homepage shows `当前阶段` as `等待市场机会`, `系统处理中`, `工程状态暂不可用`, `安全边界阻断`, or `需要介入` without exposing raw gate names |
| Homepage Owner language guard | The homepage now maps internal `fresh signal` and evidence-instruction wording to Owner language such as `等待市场机会`, `真实订单路径保持关闭`, and `无需操作`; smoke checks prevent those internal terms from returning to the homepage |
| Monitor Owner language guard | Healthy waiting notifications say `当前没有可用市场机会`; internal signal terms remain audit/detail concepts instead of the default Owner heartbeat text |
| Signal detection source | Fresh opportunity detection remains Tokyo watcher / Feishu notification driven; local `--auto-cache` status checks are not the only market-opportunity detector |
| Safety | These tools do not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets, live-profile mutation, or order-sizing mutation |

### Deploy Interaction Rule

After bounded Tokyo deploys or homepage publishes, the main runtime window should
prefer one deploy-session report instead of narrating each server command. The
normal shape is:

```text
runtime deploy report
+ optional frontend publish report
+ one L1 daily check
-> tokyo_runtime_deploy_session
```

The report must state:

| Field | Meaning |
| --- | --- |
| `interaction.level` | Highest interaction level in the session, for example `L3_bounded_deploy_apply` |
| `interaction.remote_interaction_count` | Total counted remote interactions from the session steps |
| `interaction.mutates_remote_files` | Whether the session changed remote runtime or static frontend files |
| `interaction.approaches_real_order` | Must remain `false` for deploy and frontend publish sessions |
| `owner_summary.current_action` | One Owner-readable next action, usually `继续等待市场机会` when healthy |

This is a communication and tooling optimization only. It does not authorize
FinalGate bypass, Operation Layer bypass, exchange write, live-profile changes,
order-sizing changes, withdrawals, transfers, or stale-fact execution.

### Deploy Tooling Optimization Rule

The default deploy workflow should minimize Tokyo interaction without hiding
safety state:

| Step | Preferred shape | Interaction budget |
| --- | --- | --- |
| Routine status review | `--auto-cache --owner-progress` | `L0` if cache is fresh; otherwise one `L1` refresh |
| Strict no-server status review | `--from-cache --require-fresh-cache --owner-progress` | `L0`, 0 remote interactions |
| Explicit signal/regression investigation | `--json` or one direct L1 snapshot | `L1`, 1 remote interaction |
| Fresh runtime status | One `probe_tokyo_runtime_snapshot.py` collection | `L1`, 1 remote interaction |
| Runtime deploy apply | Batched git deploy phases with explicit remote count | `L3`, 4 direct SSH commands, 7 counted remote interactions |
| Frontend homepage publish | One tar-over-SSH static publish | `L3`, 1 remote interaction |
| Postdeploy acceptance | One daily-check snapshot plus one deploy-session summary | `L1` snapshot, summary local |
| Routine deploy-session review | `--run-daily-check --daily-check-mode auto-cache` | `L0` if cache is fresh; otherwise one `L1` refresh |
| Owner-readable deploy-session review | `--run-daily-check --daily-check-mode cache --owner-progress` | `L0`, 0 remote interactions when cache is fresh |
| Goal progress review | `run_strategygroup_runtime_goal_progress_audit.py --owner-progress` | Local cache/baseline only, 0 Tokyo interactions |
| Quiet-monitor drift review | `audit_tokyo_runtime_quiet_monitor.py --owner-progress` | Local automation/config files only, 0 Tokyo interactions |
| Homepage-only visual QA | `npm run visual:qa:home` | Local browser/dev-server only, 0 Tokyo interactions |

When a tool can reuse a fresh cache or a single snapshot, it must not run extra
Tokyo probes only to restate the same state. When a deploy is necessary, the
report should summarize the whole session instead of narrating each command.

### 2026-06-17 Batched Deploy Interaction Checkpoint

The runtime deploy tool optimization was pushed and deployed to Tokyo. The
server now carries the batched git deploy planner/executor plus the Owner
Console homepage interaction projection.

| Item | Result |
| --- | --- |
| Local head | `83bd0d6aa07c4784fd28e4182c214db4c344efe0` |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-83bd0d6a-batched-deploy-interactions` |
| Runtime deploy apply | `status=applied`, `interaction.level=L3_bounded_deploy_apply`, `remote_interaction_count=7`, `blockers=[]` |
| Postdeploy daily check | `status=waiting_for_market`, `runtime_ready=true`, `watcher_ready=true`, `source_readiness_ready=true`, `runtime_dry_run_audit_passed=true` |
| Deploy session summary | `status=waiting_for_market`, `all_steps_safe_for_deploy_session_summary=true` |
| Monitor baseline | `docs/current/RUNTIME_MONITOR_BASELINE.json` now expects runtime head only |
| Safety | Deploy and postdeploy checks did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

### 2026-06-17 Homepage Visibility Deploy Checkpoint

The low-interaction monitor defaults and Owner Console homepage visibility
changes were pushed and deployed to Tokyo.

| Item | Result |
| --- | --- |
| Deployed runtime head | `7df799e1ee3dbabd69060f92758a6b84ba2a0ae6` |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-7df799e1-homepage-visibility` |
| Runtime deploy apply | `status=applied`, `interaction.level=L3_bounded_deploy_apply`, `remote_interaction_count=7`, `blockers=[]` |
| Frontend homepage publish | `status=applied`, `interaction.level=L3_frontend_static_publish`, `remote_interaction_count=1`, `blockers=[]` |
| Postdeploy daily check | `status=waiting_for_market`, `notification=DONT_NOTIFY`, `blockers=[]`, `product_gaps=[]` |
| Deploy session summary | `status=waiting_for_market`, `remote_interaction_count=9`, `all_steps_safe_for_deploy_session_summary=true` |
| Owner Console homepage | Homepage no longer shows deploy-channel status as a primary operating card; deploy-channel detail remains on the system/source-health surface |
| Visibility coverage | Homepage state smoke now covers waiting for market, processing, engineering blocker, safety blocker, and needs-intervention states |
| Monitor baseline | `docs/current/RUNTIME_MONITOR_BASELINE.json` expects runtime and frontend head `7df799e1ee3dbabd69060f92758a6b84ba2a0ae6` |
| Safety | Deploy, publish, and postdeploy checks did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

## P0 Subgoal: Runtime Liveness Repair

### Current State

The watcher has reached the post-signal boundary where the fresh StrategyGroup
signal, candidate, grant, authorization, and FinalGate preview can exist, but
the official Operation Layer submit path still depends on prepared evidence
IDs. The previous blocker language was still tied to old per-chat Owner
confirmation for attempt consumption and local registration.

### Correct Current Path

```text
fresh signal
-> standing-authorized scoped evidence preparation
-> action-time FinalGate
-> official Operation Layer action only
-> post-submit finalize / reconciliation / budget settlement
```

### Acceptance

| Requirement | Expected result |
| --- | --- |
| Default arm preview | Still stops before attempt consumption |
| Standing evidence prep | Records bounded attempt/local-registration/exchange-arm evidence only when explicitly enabled |
| Local registration blocked | Stops before exchange-submit evidence calls and emits a reviewable blocker instead of noisy `RuntimeExecutionOrderLifecycleAdapterResult not found` 404s |
| Disabled smoke | Can prove the action endpoint without exchange write |
| FinalGate | Must rerun at action time before real Operation Layer action |
| Operation Layer | Must use official endpoint and required evidence IDs |
| Safety | No secret mutation, profile expansion, sizing change, withdrawal, transfer, stale-fact execution, duplicate submit, or conflicting position/order execution |

### Common Pipeline vs StrategyGroup Adaptation

The runtime chain must be validated as one shared execution pipeline. A fresh
signal from MPG, TEQ, FBS, PMR, or SOR should reuse the same common path:

```text
fresh signal
-> RequiredFacts readiness
-> candidate / authorization evidence
-> action-time FinalGate
-> official Operation Layer
-> finalize / reconciliation / settlement / review
```

| Area | Classification | Repeated per StrategyGroup |
| --- | --- | --- |
| Fresh signal -> candidate/auth automatic chain | Common runtime pipeline | No |
| RequiredFacts readiness reading | Common facts/readiness layer | No |
| Attempt renewal / admission | Common runtime admission | No |
| FinalGate call order | Common execution-safety layer | No |
| Operation Layer evidence relay | Common execution layer | No |
| Active position / open order checks | Common account-safety layer | No |
| Protection / budget / duplicate-submit checks | Common protection, budget, idempotency layer | No |
| Post-submit finalize / reconciliation / settlement | Common closed-loop layer | No |
| Owner Console status projection | Common product readmodel | No |
| Supported symbols/sides, signal rule, strategy RequiredFacts, risk defaults, hard stops, conflict policy | StrategyGroup handoff adaptation | Yes |

The expected ratio is roughly:

```text
80% common execution-chain repair
20% StrategyGroup handoff adaptation
```

If a blocker appears in candidate/auth, FinalGate, Operation Layer, account
safety, protection, budget, idempotency, or closed-loop settlement, treat it as
a common pipeline defect first. StrategyGroup-specific work should only define
inputs and boundaries: supported symbols, supported sides, signal-ready rule,
RequiredFacts, risk defaults, hard stops, and conflict policy.

### 2026-06-16 Checkpoint

| Item | Result |
| --- | --- |
| Runtime renewal RCA | New profile-confirmation runtime drafts now reset `attempts_used=0` and `budget_reserved=0` instead of inheriting exhausted proposal counters |
| Fresh signal chain | Tokyo reached `ready_for_action_time_final_gate` for the fresh SOR signal after bounded runtime renewal |
| Operation Layer RCA | Exchange-submit evidence prep was incorrectly continuing after local registration remained blocked; the downstream 404 was a symptom, not the root blocker |
| Flow repair | Arm flow now stops before exchange-submit action/enablement/adapter calls when local registration result is not `registered_created_local_orders` |
| Safety | Blocked local registration remains reviewable project progress, but it is not treated as a real-order green light |
| Attempt mutation boundary | Followup / dry-run / arm preview no longer authorizes attempt or budget mutation; mutation belongs only to the official Operation Layer submit boundary after action-time gates pass |
| Pre-attempt evidence blockers | Shadow-mode, stale trusted-submit facts, missing deployment-readiness evidence, or non-live authorization warnings now block before attempt reservation or mutation |
| Standing evidence prep | Standing prep can be requested as a non-executing proof surface, but its blockers cannot be hidden behind disabled-smoke completion |
| Dispatcher evidence relay | After same-run action-time FinalGate passes, resume dispatcher can run standing-authorized Operation Layer evidence prep, persist the evidence report, recalculate readiness, and only then call the official Operation Layer submit endpoint |
| Reservation warning guard | Attempt reservation warnings that prove shadow-mode, stale facts, missing deployment evidence, or non-live authorization now stop before attempt mutation and budget consumption |
| Live enablement relay | After same-run FinalGate pass, dispatcher can request bounded live-runtime enablement only when hard safety blockers are absent, then rerun Operation Layer evidence prep |
| Operation evidence deferral | Live enablement may defer only downstream Operation Layer evidence IDs that cannot exist until the runtime leaves shadow; safety facts, Owner authorization, deployment, staged-chain, protection, budget, duplicate-submit, active-position, open-order, and scope blockers remain hard blockers |
| Live runtime handoff | A runtime that has left shadow mode and is execution-enabled is no longer eligible for B0 shadow-candidate scheduler planning; it must be handled by Operation Layer evidence/readiness or closed-loop recovery |
| Observation blocker hygiene | Plain `waiting_for_signal` and non-mutating historical attempt/candidate blockers do not create Owner attention; they remain runtime-level audit warnings unless prepare/order/exchange/budget/attempt side effects occurred |

### 2026-06-17 Non-Executing Prepare Auto Bridge Checkpoint

The resume dispatcher now treats `ready_for_non_executing_prepare` as an
actionable common-pipeline checkpoint when `--execute-preflight` is enabled:

```text
fresh selected StrategyGroup signal
-> official non-executing next-attempt prepare
-> prepared authorization / candidate evidence
-> action-time FinalGate preflight
-> Operation Layer evidence readiness
```

| Requirement | Result |
| --- | --- |
| Common-chain execution | The dispatcher calls the existing `runtime_next_attempt_prepare_api_flow.py` prepare wrapper instead of adding StrategyGroup-specific candidate/auth code |
| Safety invariants | Prepare may create bounded pre-submit evidence, but it must not arm local registration, arm exchange submit, call OrderLifecycle, create orders, call exchange write APIs, mutate attempt counters, mutate runtime budget, or create withdrawal/transfer actions |
| Missing input handling | Missing runtime instance or signal/order-candidate input blocks as `missing_fact` before FinalGate |
| Forbidden effect handling | Any forbidden prepare effect blocks as `hard_safety_stop` before FinalGate |
| Cross-StrategyGroup proof | Unit coverage proves the same prepare -> FinalGate bridge works for MPG, TEQ, and SOR with only StrategyGroup/runtime IDs changed |
| Remaining scope | Operation Layer evidence readiness, live boundary enablement, submit, finalize, reconciliation, settlement, and review remain shared runtime stages rather than StrategyGroup adapters |

## P0 Subgoal: Runtime Dry-Run Audit Chain

### Purpose

The real market path should not be the only way to discover evidence relay,
FinalGate, Operation Layer, or source-readiness breakage. A dry-run audit chain
must exercise the same semantics without creating real orders or exchange
writes.

### Target Chain

```text
mock fresh signal
-> RequiredFacts readiness
-> candidate / authorization evidence
-> action-time FinalGate dry-run / preflight
-> Operation Layer evidence prep
-> disabled submit smoke
-> fake or non-executing post-submit finalize / reconciliation / budget settlement / review shape check
-> unified audit packet
```

### Required Artifact

| Artifact | Path |
| --- | --- |
| Local audit packet | `output/strategygroup-runtime-pilot/dry-run-audit-chain/runtime-dry-run-audit-chain.json` |
| Local closure status packet | `output/strategygroup-runtime-pilot/chain-closure-status/runtime-execution-chain-closure-status.json` |
| Tokyo audit packet | `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/runtime-dry-run-audit-chain.json` |

### Current Implementation

The local script is:

```text
scripts/runtime_dry_run_audit_chain.py
scripts/runtime_execution_chain_closure_status.py
```

It currently runs fourteen fixture-backed scenarios and treats expected blocked
states as successful audit coverage when they stop before dangerous actions.
Tokyo refreshes the dry-run audit script as a watcher-adjacent non-executing
audit step. The closure-status script compresses the local dry-run result into
one go/no-go status for main-control progress reviews.

### Scenario Matrix

| Scenario | Expected result |
| --- | --- |
| No signal | `waiting_for_signal`; no candidate, authorization, FinalGate, or Operation Layer |
| Mock fresh signal pass | Evidence IDs connect; dangerous action flags remain false |
| Mock Operation Layer submit/finalize pass | Dispatcher reaches settled and next-attempt-ready with mock responses only |
| RequiredFacts missing | Clear `missing_fact` blocker before Operation Layer |
| Active position or open-order conflict | Clear conflict blocker before FinalGate or Operation Layer action |
| Operation Layer blocker review matrix | Active position, open order, protection, budget, duplicate-submit, and scope mismatches become reviewable blocked packets |
| Selected StrategyGroup dispatch guard | Selected MPG-001 mock fresh signal can reach FinalGate dispatch; out-of-scope StrategyGroup signal is blocked before FinalGate or Operation Layer |

### 2026-06-17 Chain Closure Status Checkpoint

`scripts/runtime_execution_chain_closure_status.py` now converts the full
dry-run audit packet into a compact status packet. This keeps routine progress
reviews from rereading many raw evidence packets while still refusing to treat
mock or disabled-smoke proof as a real-order proof.

| Item | Result |
| --- | --- |
| Non-market status | `non_market_execution_chain_ready` only when the dry-run audit passes, all required checks are true, and no dangerous effect is present |
| Real-order status | Remains `waiting_for_live_action_time_proof` after local dry-run success |
| Missing live proofs | `live_fresh_signal`, `same_run_action_time_finalgate_pass`, `official_operation_layer_real_gateway_action`, and `post_submit_finalize_reconciliation_budget_settlement` |
| Next safe actions | Keep watcher running, rerun dry-run audit after runtime changes, and on fresh signal run same-run FinalGate then official Operation Layer |
| Safety | The closure-status script does not call Tokyo, FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets, live profile, or sizing mutation |

### 2026-06-17 Order-Capable Experiment Profile Checkpoint

The runtime pilot now treats Tokyo as an experimental bounded-capital server:
inside the selected StrategyGroup and tiny-risk boundary, trading permission is
not itself a risk blocker. The system must still fail closed on stale facts,
missing protection, duplicate-submit risk, conflicting active positions or open
orders, FinalGate failure, or Operation Layer failure.

| Item | Result |
| --- | --- |
| SSOT | `docs/current/RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md` |
| Server overlay | `/home/ubuntu/brc-deploy/env/runtime-order-capable.env` |
| Tracked template | `.env.tokyo.experimental-live-order-capable.example` |
| Required env | `TRADING_ENV=live`, `EXCHANGE_TESTNET=false`, `BRC_EXECUTION_PERMISSION_MAX=order_allowed`, `RUNTIME_EXCHANGE_SUBMIT_GATEWAY_BINDING_ENABLED=true` |
| Runtime control/test surfaces | Must remain `RUNTIME_CONTROL_API_ENABLED=false` and `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=false` |
| Watcher systemd | Loads the optional order-capable overlay after `live-readonly.env` |
| Operation Layer mode | Resume dispatcher explicitly uses `--operation-layer-submit-mode real_gateway_action` |
| Credential preflight | Now checks `order_allowed` and gateway-binding env readiness without printing secrets |

### 2026-06-17 Order-Capable Experiment Deploy Checkpoint

The order-capable experiment profile was pushed and deployed to Tokyo through
the git-based standing-authorization deploy path. Tokyo now has a server-only,
non-secret overlay at `/home/ubuntu/brc-deploy/env/runtime-order-capable.env`.

| Item | Result |
| --- | --- |
| Commit | `bceea34db0317325c368a67514967f824d9694b6` |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-bceea34d-order-capable-experiment` |
| Runtime deploy apply | `status=applied`, `interaction.level=L3_bounded_deploy_apply`, `remote_interaction_count=7`, `blockers=[]` |
| Watcher systemd | `brc-runtime-signal-watcher.timer` active/enabled; service loads `runtime-order-capable.env` after `live-readonly.env` |
| Masked env check | `TRADING_ENV=live`, `EXCHANGE_TESTNET=false`, `BRC_EXECUTION_PERMISSION_MAX=order_allowed`, `RUNTIME_EXCHANGE_SUBMIT_GATEWAY_BINDING_ENABLED=true` |
| Credential preflight | Passed with futures permission present, withdrawals disabled, scoped position count `0`, scoped open order count `0` |
| Daily check | `status=waiting_for_market`, `notification=DONT_NOTIFY`, `blockers=[]`, `product_gaps=[]` |
| Safety | Deploy and checks did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

### 2026-06-17 Goal Status Local Dry-Run Checkpoint

The goal-status packet now accepts the local dry-run audit packet from either
the Tokyo-style report root or the local audit subdirectory:

```text
runtime-dry-run-audit-chain.json
dry-run-audit-chain/runtime-dry-run-audit-chain.json
```

This keeps local P0 audit runs usable without waiting for a market signal or
manually copying packet files.

| Item | Result |
| --- | --- |
| Local dry-run fallback | `strategygroup-runtime-goal-status` reads nested `dry-run-audit-chain/runtime-dry-run-audit-chain.json` |
| Fast auto-chain audit | Goal status treats `fresh_signal_fast_auto_chain_checked=true` as a required dry-run check |
| Submit-blocker review | Active position/open-order conflicts remain submit blockers, but `active_position:missing` and `open_orders:missing` are classified through missing facts instead of fake conflict resolution |
| Budget/protection missing facts | `budget:missing` and `protection:missing` surface as missing-fact submit blockers |
| Safety | This remains read-only packet aggregation; it does not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets, live profile, or sizing mutation |

### 2026-06-17 Local Product-State Refresh Checkpoint

`scripts/refresh_strategygroup_runtime_product_state_packets.py` can now be
used as a local main-control refresh wrapper. When explicitly requested, it
refreshes the non-executing dry-run audit chain and then rebuilds
`strategygroup-runtime-goal-status.json` from the same report directory.

If local operator auth is missing, API readmodel refresh is recorded as a
reviewable blocker, but local dry-run audit and goal-status packets are still
written. This prevents no-signal development turns from stopping only because
the local console server/auth environment is not running.

| Item | Result |
| --- | --- |
| Optional dry-run refresh | `--refresh-dry-run-audit-chain` writes `runtime-dry-run-audit-chain.json` |
| Optional closure-status refresh | `--refresh-chain-closure-status` writes `runtime-execution-chain-closure-status.json` from the current dry-run audit packet |
| Optional goal-status refresh | `--refresh-goal-status` writes `strategygroup-runtime-goal-status.json` |
| Tokyo watcher hook | `80-product-state-refresh.conf` now writes `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/runtime-execution-chain-closure-status.json` after the dry-run audit post-step |
| Local auth missing | Records `operator_cookie_unavailable` and skips API packets instead of aborting the local audit refresh |
| Long local goal mode | `--allow-degraded-local-refresh-success` may return exit code `0` only when operator auth is missing, dry-run audit passed, goal-status refreshed, fallback source-readiness was written, and no forbidden safety effect is present |
| Current local command result | `dry_run_audit_refresh.status=passed`, `scenario_count=14`, `goal_status_refresh.runtime_dry_run_audit_passed=true`, `goal_status_refresh.status=missing_fact` |
| Safety | The wrapper remains readmodel/local-packet only; the degraded-success flag is not installed in Tokyo systemd and does not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets, live profile, or sizing mutation |

### 2026-06-17 Source-Readiness Fallback Checkpoint

When local operator auth is missing, product-state refresh now writes a
degraded `owner-console-source-readiness.json` fallback packet instead of
leaving the source-readiness file absent. The fallback keeps the Owner Console
contract shape but marks account, orders, positions, protection, runtime source,
and watcher as unavailable.

| Item | Result |
| --- | --- |
| Fallback trigger | `operator_cookie_unavailable` while refreshing readmodel APIs |
| Fallback packet | `owner-console-source-readiness.json.status=source_unavailable` |
| Preserved health | `runtime_dry_run_audit=审计演练正常` when the local dry-run audit passed |
| Goal-status effect | `strategygroup-runtime-goal-status` no longer reports `missing_packet:source_readiness`; it still reports `source_readiness_not_ready` and `live_facts_not_ready` until real readmodels/facts are available |
| No fake readiness | Funds, orders, positions, protection, runtime source, and watcher remain unavailable in the fallback |
| Safety | Fallback packet generation is local/read-only and does not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets, live profile, or sizing mutation |

### Evidence Relay Checks

The mock fresh signal pass scenario must prove these handoff checks before a
real signal appears:

| Check | Expected result |
| --- | --- |
| Required Operation Layer evidence IDs | All required IDs are present; no `missing_evidence_id` remains |
| Authorization chain | Operation Layer command, evidence report, and closed-loop shapes use the same fresh authorization |
| Action-time FinalGate | Same-run FinalGate preflight is called and passes before Operation Layer readiness |
| Official Operation Layer endpoint | The selected endpoint is the official first-real-submit action path |
| Legacy local-registration probe | Legacy `RuntimeExecutionOrderLifecycleAdapterResult` probe blocker is tolerated only when adapter result evidence exists |

### Full Close-Loop Shape

The dry-run pass scenario must prove these non-executing shapes exist before the
project waits for a real signal:

| Shape | Expected result |
| --- | --- |
| Post-submit finalize | Runtime can return to a fresh-signal next-attempt gate |
| Reconciliation | No active position, no open order, no mismatch blockers |
| Budget settlement | Reservation is released or accounted |
| Review record | Runtime outcome is recorded without requiring Owner action |

## P0 Subgoal: Shared Runtime Pipeline Validation

### Purpose

The pilot must prove that current blockers are mostly shared runtime-chain
issues, not per-strategy execution implementations. StrategyGroups provide
signal, facts, symbols, side, risk boundary, and hard stops. They must not each
own a separate candidate/auth/FinalGate/Operation Layer/finalize path.

### Validation Model

| Area | Ownership | Repeated per StrategyGroup |
| --- | --- | --- |
| Fresh signal to candidate/auth | Runtime main chain | No |
| RequiredFacts readiness read | Runtime facts layer | No |
| Attempt renewal and admission | Runtime admission | No |
| FinalGate call order | Execution safety | No |
| Operation Layer evidence relay | Execution layer | No |
| Active position / open order / protection / budget / duplicate-submit checks | Account, protection, budget, idempotency layers | No |
| Post-submit finalize / reconciliation / settlement | Closed-loop layer | No |
| Owner Console source state | Product readmodel | No |
| Supported symbols and sides | StrategyGroup handoff | Yes |
| Signal-ready rule | StrategyGroup handoff | Yes |
| Strategy RequiredFacts definition | StrategyGroup handoff | Yes |
| Risk defaults and hard stops | StrategyGroup handoff | Yes |
| Conflict policy | StrategyGroup handoff plus portfolio policy | Yes |

### Acceptance

| Requirement | Expected result |
| --- | --- |
| Shared chain | MPG / TEQ / FBS / PMR / SOR enter the same runtime admission, candidate/auth, FinalGate, Operation Layer, finalize, reconcile, and settle code path |
| Strategy-specific inputs | Each StrategyGroup only changes handoff contract inputs: signal packet, RequiredFacts, symbol, side, risk defaults, hard stops, and conflict rules |
| Dry-run coverage | The dry-run audit chain includes at least one pass-like fixture and one blocked fixture that are not SOR-only |
| No execution fork | No StrategyGroup adds a custom FinalGate, Operation Layer, order lifecycle, exchange gateway, or settlement implementation |
| Owner Console | The UI/readmodel shows StrategyGroup differences as product state, not separate packet-reading workflows |

### 2026-06-17 Checkpoint

| Item | Result |
| --- | --- |
| Dry-run audit artifact | `runtime-dry-run-audit-chain.json` now includes `shared_runtime_pipeline_validation` and `selected_strategygroup_dispatch_guard_checked` |
| StrategyGroups covered | MPG / TEQ / FBS / PMR / SOR |
| Common-chain proof | All five StrategyGroups share the same runtime stages: admission, candidate/auth, RequiredFacts, FinalGate, Operation Layer evidence relay, account/protection/budget/idempotency checks, submit, finalize/reconcile/settle/review, and Owner readmodel |
| Strategy-specific proof | Each handoff only supplies symbols, sides, signal rule, RequiredFacts, risk defaults, hard stops, and sample packets |
| Execution authority proof | Each handoff keeps `candidate_creation_authorized=false`, `final_gate_input=false`, `operation_layer_input=false`, and `real_submit_authorized=false` |
| Goal status guard | `strategygroup-runtime-goal-status` now requires `shared_runtime_pipeline_checked=true`, `common_execution_chain_reuse_checked=true`, `strategygroup_adapter_boundary_checked=true`, and `selected_strategygroup_dispatch_guard_checked=true` before treating dry-run audit as healthy |

### 2026-06-17 80/20 Verification Checkpoint

The current architecture judgment is verified as a runtime audit invariant:

| Share | Scope | Verification result |
| --- | --- | --- |
| 80% | Common runtime pipe | `runtime-dry-run-audit-chain.json` proves MPG / TEQ / FBS / PMR / SOR share the same admission, candidate/auth, RequiredFacts, FinalGate, Operation Layer evidence relay, submit, finalize, reconciliation, settlement, review, and Owner readmodel stages |
| 20% | StrategyGroup adapter | Each handoff only supplies symbols, sides, signal rule, RequiredFacts, tiny risk defaults, hard stops, and sample packets |

Current local validation:

```text
python3 scripts/runtime_dry_run_audit_chain.py \
  --output-dir output/strategygroup-runtime-pilot/dry-run-audit-chain \
  --output-json output/strategygroup-runtime-pilot/dry-run-audit-chain/runtime-dry-run-audit-chain.json

pytest tests/unit/test_runtime_dry_run_audit_chain.py \
  tests/unit/test_strategygroup_runtime_goal_status.py -q
```

Result:

```text
runtime-dry-run-audit-chain.status=passed
scenario_count=14
shared_runtime_pipeline_checked=true
common_execution_chain_reuse_checked=true
strategygroup_adapter_boundary_checked=true
selected_strategygroup_dispatch_guard_checked=true
29 passed
```

This means active position, open order, missing protection, missing budget,
duplicate-submit risk, and symbol/side/notional/leverage mismatch remain
real-submit blockers, but they do not require StrategyGroup-specific execution
forks and do not stop watcher observation or common-chain project progress.

### 2026-06-17 Goal-Status Projection Checkpoint

`strategygroup-runtime-goal-status.json` now projects the required dry-run audit
checks into its top-level `checks` object. Automation and Owner Console
readmodels can distinguish a live-source gap from a shared-chain gap without
digging into the raw dry-run packet.

| Item | Result |
| --- | --- |
| Fast chain projection | `checks.fresh_signal_fast_auto_chain_checked=true` when the local audit proves fresh signal -> authorization -> FinalGate dispatch -> Operation Layer evidence prep |
| Shared pipeline projection | `checks.common_execution_chain_reuse_checked=true` and `checks.strategygroup_adapter_boundary_checked=true` when MPG / TEQ / FBS / PMR / SOR reuse the common runtime pipe |
| Selected-scope projection | `checks.selected_strategygroup_dispatch_guard_checked=true` and `checks.all_selected_strategygroups_reach_finalgate_dispatch_checked=true` when selected StrategyGroup dispatch can reach the action-time FinalGate plan and out-of-scope signals are blocked |
| Current local effect | Local `goal-status` can report `runtime_dry_run_audit_passed=true` while still blocking real submit on `missing_packet:*`, `source_readiness_not_ready`, or `live_facts_not_ready` |
| Safety | This is read-only projection only; it does not call Tokyo, FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets, live profile, or sizing mutation |

### 2026-06-17 Tokyo Deploy Checkpoint

The latest main-control branch head was deployed to Tokyo through the
git-based standing-authorization deploy path.

| Item | Result |
| --- | --- |
| Local / remote branch head | `ee0c248e` |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-ee0c248e-goal-status-projection` |
| Deploy apply | `status=applied`, `commands_executed=18`, `blockers=[]` |
| Postdeploy verifier | `postdeploy_acceptance_passed`; release identity is read from `.brc-release-manifest.json` because the release is a git export, not a git working tree |
| Watcher timer | `brc-runtime-signal-watcher.timer` is enabled and active |
| Current Tokyo goal status | `strategygroup-runtime-goal-status.status=waiting_for_signal` |
| Source readiness | `owner-console-source-readiness.status=ready` |
| Live facts | `strategy-group-live-facts-readiness.status=strategy_group_live_facts_ready_for_armed_observation` |
| Dry-run audit | `runtime-dry-run-audit-chain.status=passed`, `scenario_count=14` |
| Real order boundary | `ready_for_real_order_action=false` because there is no fresh signal |
| Next checkpoint | `continue_watcher_observation` until a fresh selected StrategyGroup signal appears |
| Safety | Deploy and postdeploy checks did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

### 2026-06-17 Local Refresh Evidence Relay Deploy Checkpoint

The local product-state refresh evidence relay fix was pushed and deployed to
Tokyo through the git-based standing-authorization deploy path.

| Item | Result |
| --- | --- |
| Deployed code head | `f8f5482a` |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-f8f5482a-local-refresh-evidence-relay` |
| Deploy apply | `status=applied`, `commands_executed=18`, `blockers=[]` |
| Postdeploy verifier | `postdeploy_acceptance_passed`; current head is `f8f5482aedcf3777fe10ce84a4d2420781d88d7c` |
| Watcher timer | `brc-runtime-signal-watcher.timer` is enabled and active |
| Current Tokyo goal status | `strategygroup-runtime-goal-status.status=waiting_for_signal`, `runtime_dry_run_audit_passed=true` |
| Source readiness | `owner-console-source-readiness.status=ready`; Owner summary reports `等待机会`, `资金正常`, `暂无订单`, `暂无持仓`, and `保护正常` |
| Dry-run audit | `runtime-dry-run-audit-chain.status=passed`, `scenario_count=14`, fast-auto-chain/shared-pipeline/adapter-boundary checks are true |
| Live facts | `strategy-group-live-facts-readiness.status=strategy_group_live_facts_ready_for_armed_observation` |
| Real order boundary | `ready_for_real_order_action=false` because there is no fresh signal |
| Safety | Deploy and postdeploy checks did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

### 2026-06-17 Deploy Channel Status Publish Checkpoint

The git-based deploy plan now writes the watcher-facing deploy-channel status
packet after postdeploy verification succeeds. This prevents Owner Console from
showing `部署通道未检查` immediately after a successful bounded deploy.

| Item | Result |
| --- | --- |
| Deployed code head | `cd61c69d` |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-cd61c69d-deploy-channel-status` |
| Deploy apply | `status=applied`, `commands_executed=19`, `blockers=[]` |
| Postdeploy verifier | `postdeploy_acceptance_passed`; current head is `cd61c69d3421abe23d43c6ab4953403ac72e6258` |
| Deploy-channel packet | `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/tokyo-deploy-channel-status.json` exists with `status=postdeploy_accepted`, `blockers=[]` |
| Owner Console source readiness | `deploy_channel=部署通道正常`, source status `ready`, `connectivity_ready=true` |
| Goal status | `strategygroup-runtime-goal-status.status=waiting_for_signal`, `deploy_channel_blockers=[]`, `fresh_signal_present=false` |
| Dry-run audit | `runtime-dry-run-audit-chain.status=passed` |
| Real order boundary | `ready_for_real_order_action=false` because there is no fresh signal |
| Safety | Deploy-channel status publication is a report-packet write only; deploy/postdeploy checks did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

### 2026-06-17 Readonly Probe Structured Failure Checkpoint

The Tokyo readonly probe now emits a structured JSON packet even when SSH
read-only collection fails. This keeps automation and Owner Console source
readiness from treating deployment-channel failures as opaque runtime failures.

| Item | Result |
| --- | --- |
| Public-key failure | `probe_tokyo_runtime_governance_readonly.py --json` returns `status=blocked` with `tokyo_ssh_publickey_denied` |
| Error preservation | Release-identity fallback preserves underlying SSH stderr so the blocker can be classified |
| Automation contract | JSON output remains parseable on failure; stderr text is no longer the only evidence |
| Historical observed local result | `status=blocked`, `checks.blockers=["tokyo_ssh_publickey_denied"]`; later deploy-channel checks reached `postdeploy_accepted` |
| Safety | Readonly probe failure handling does not modify remote files, read env/secrets, run migrations, restart services, create orders, call OrderLifecycle, call exchange APIs, withdraw, or transfer |

### 2026-06-17 Source Readiness Deploy-Channel Fallback Checkpoint

Owner Console source readiness now uses the readonly probe packet as a
deploy-channel fallback when `tokyo-deploy-channel-status.json` is absent. This
keeps the product surface specific even before the next successful deploy writes
the postdeploy channel packet.

| Item | Result |
| --- | --- |
| Readmodel fallback | `owner-console-source-readiness` reads `BRC_TOKYO_READONLY_PROBE_STATUS_PATH` or `tokyo-readonly-probe-current.json` under the watcher report directory when the deploy-channel packet is missing |
| Product status | `tokyo_ssh_publickey_denied` maps to `deploy_channel=部署通道暂不可用` |
| Local fallback packet | `refresh_strategygroup_runtime_product_state_packets.py` mirrors the same deploy-channel language in source-readiness fallback output |
| Owner UI boundary | The deploy-channel item remains a source-health/system detail and does not become a homepage execution gate |
| Safety | This is read-only state projection; it does not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets, live profile, or sizing mutation |

### 2026-06-17 Source Readiness Fallback Deploy Checkpoint

The latest Owner Console source-readiness fallback repair was deployed to Tokyo
through the standing-authorization git deploy path. Tokyo is current again, and
the watcher/product-state loop is healthy while waiting for a fresh selected
StrategyGroup signal.

| Item | Result |
| --- | --- |
| Deployed code head | `00847a6f` |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-00847a6f-source-readiness-fallback` |
| Deploy apply | `status=applied`, `commands_executed=19`, `blockers=[]` |
| Postdeploy verifier | `postdeploy_acceptance_passed`; current head is `00847a6fe8611c2609726d88ce9c7b3fd276fcab` |
| Watcher timer/service | Timer is enabled and active; latest service tick exited `0/SUCCESS` |
| Current watcher state | `watcher-tick.status=watching_no_signal`; `latest-summary.status=waiting_for_signal` |
| Current goal status | `strategygroup-runtime-goal-status.status=waiting_for_signal`, `fresh_signal_present=false`, `runtime_dry_run_audit_passed=true` |
| Source readiness | `owner-console-source-readiness.status=ready` |
| Live facts | `strategy-group-live-facts-readiness.status=strategy_group_live_facts_ready_for_armed_observation` |
| Dry-run audit | `runtime-dry-run-audit-chain.status=passed` |
| Deploy channel | `tokyo-deploy-channel-status.status=postdeploy_accepted`, `blockers=[]` |
| Real order boundary | `ready_for_real_order_action=false` because there is no fresh signal |
| Safety | Deploy, probe, postdeploy, watcher refresh, and status reads did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

### 2026-06-17 Frontend Externalization Checkpoint

The static Owner Console frontend was removed from the main runtime goal. The
main worktree keeps the source-readiness/readmodel contract for future external
frontends, but frontend build, visual QA, static publishing, and homepage
release checks no longer affect runtime monitoring or first real-order closure.

| Item | Result |
| --- | --- |
| Static frontend publish | Removed from mainline runtime monitoring |
| UI governance docs/assets | Removed from `docs/current` |
| Runtime snapshot | No longer checks nginx or `/var/www/brc-owner-console` release files |
| Daily check | Healthy waiting-for-market can stay quiet without frontend release proof |
| Goal progress audit | No longer contains a homepage publish track |
| Runtime/API contract | Source-readiness and readmodel/API surfaces remain available for a future external frontend |
| Readonly probe | `status=ready_for_controlled_deploy_preflight`, `blockers=[]`, health is `ok`, `live_ready=false` |
| Watcher state | `watcher-tick.status=watching_no_signal`; `latest-summary.status=waiting_for_signal` |
| Goal status | `strategygroup-runtime-goal-status.status=waiting_for_signal`, `fresh_signal_present=false`, `source_readiness_ready=true`, `live_facts_ready=true` |
| Owner summary | `部署通道正常`, `等待机会`, `资金正常`, `暂无订单`, `暂无持仓`, `保护正常`, `审计演练正常` |
| Real order boundary | `ready_for_real_order_action=false` because there is no fresh signal |
| Safety | Smoke, deploy, probe, postdeploy, watcher refresh, and status reads did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

### 2026-06-17 Submit-Blocker Review State Deploy Checkpoint

The submit-blocker review state was pushed and deployed to Tokyo so the
watcher-facing goal-status packet can distinguish normal waiting from
reviewable submit blockers.

| Item | Result |
| --- | --- |
| Deployed code head | `315af1b7` |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-315af1b7-submit-blocker-review` |
| Deploy apply | `status=applied`, `commands_executed=19`, `blockers=[]` |
| Postdeploy verifier | `postdeploy_acceptance_passed`; current head is `315af1b784ae8526f505e6b8e0d577a9728bde7e` |
| Watcher state | `watcher-tick.status=watching_no_signal`; `latest-summary.status=waiting_for_signal`; `resume-dispatch-packet.status=waiting_for_market` |
| Goal status | `strategygroup-runtime-goal-status.status=waiting_for_signal`, `next_safe_checkpoint=continue_watcher_observation`, `ready_for_real_order_action=false` |
| Submit-blocker review | `submit_blocker_review.required=false`, `blocker_keys=[]`; natural no-signal waiting is not a review task |
| Real order boundary | `submit_blocker_keys=["fresh_signal","candidate_authorization","action_time_finalgate","official_operation_layer"]`, but `submit_blocker_review_required=false` because these are waiting states, not blocked rows |
| Safety | Deploy, postdeploy verify, watcher refresh, and status reads did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

### 2026-06-17 Owner Console Submit-Blocker Review Projection Checkpoint

The Owner Console source-readiness readmodel and frontend now consume the
submit-blocker review state instead of forcing the Owner to interpret raw
matrix keys.

| Item | Result |
| --- | --- |
| Deployed code head | `6b615aac` |
| Tokyo release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-6b615aac-console-submit-blocker-review` |
| Deploy apply | `status=applied`, `commands_executed=19`, `blockers=[]` |
| Postdeploy verifier | `postdeploy_acceptance_passed`; current head is `6b615aaca2b6f593d7feaa98ee3f7884ad22b56f` |
| Source-readiness projection | `real_order_readiness.submit_blocker_review.required=false`, `blocker_keys=[]`, `ready_for_real_order_action=false` |
| Current Owner state | `owner_summary.real_order_readiness=等待机会`; no-signal waiting remains a normal waiting state, not a review task |
| Frontend copy | Real submit blockers show `系统审查已记录` and `真实订单保持关闭`; normal waiting does not show that warning |
| Validation | `pytest` readmodel checks passed; `npm run build`, `npm run smoke`, `npm run smoke:states`, `npm run smoke:real`, and `npm run visual:qa` passed |
| Safety | UI/readmodel validation and deploy did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secrets mutation, live profile mutation, or sizing mutation |

### P0 Common Runtime Pipe Reuse Verification

After the first bounded live chain closes, the main controller must verify that
the fixed path is a shared runtime pipe, not an MPG-only or SOR-only special
case. The working hypothesis is:

```text
80% common execution-chain work
20% StrategyGroup adapter work
```

The common pipe owns these stages once:

| Common stage | Owner | StrategyGroup-specific rewrite allowed |
| --- | --- | --- |
| fresh signal to candidate / authorization | runtime mainline | No |
| RequiredFacts readiness read | runtime / facts layer | No |
| attempt renewal / admission | runtime admission | No |
| action-time FinalGate order | execution safety | No |
| Operation Layer evidence handoff | execution layer | No |
| active position / open order checks | account safety | No |
| protection missing check | protection layer | No |
| budget missing check | budget layer | No |
| duplicate submit risk | idempotency / order lifecycle | No |
| post-submit finalize / reconciliation / settlement | closed-loop layer | No |
| Owner Console state projection | product readmodel | No |

Each StrategyGroup may only swap its adapter inputs:

| Adapter input | Example | Purpose |
| --- | --- | --- |
| supported symbols | `MSTR/USDT:USDT`, `XAG/USDT:USDT` | limit observable markets |
| supported sides | `long`, `short` | limit direction |
| signal ready rule | momentum, funding stress, session breakout | decide whether a fresh signal exists |
| RequiredFacts definition | mark, funding, session, OI, position | declare required evidence |
| risk defaults | tiny notional, `1x` | cap risk |
| hard stops | stale signal, conflict, low liquidity | stop unsafe strategy-specific conditions |
| conflict policy | TEQ / MPG same beta concentration | prevent stacked exposure |

The P0 close-loop is accepted only when one real or fully dry-run audited path
proves the common stages above are parameterized by StrategyGroup handoff data.
The verification must then run at least one non-executing adapter replay for a
second StrategyGroup so that a future MPG / TEQ / FBS / SOR / PMR activation does
not require rebuilding candidate, FinalGate, Operation Layer, or finalize logic.

### Mock Dispatcher Close-Loop

The dry-run audit chain also includes a local mock dispatcher close-loop. It
uses mocked API responses to exercise the same dispatcher handoff shape:

```text
Operation Layer submit
-> post-submit finalize
-> budget settlement id
-> review id
-> next-attempt gate ready
```

This scenario may contain simulated exchange-effect fields inside its own
artifact. Those fields are explicitly marked as mock-only and are not accepted
as real execution proof. The global audit packet must still show no actual
exchange write, no actual order creation, no actual order-lifecycle call, and
no withdrawal or transfer.

### Safety

The dry-run chain must not call exchange write, create real orders, mutate
secrets, mutate live profile, expand order sizing, create withdrawals or
transfers, treat disabled smoke as real execution proof, or mark missing
evidence as ready.

## P0 Subgoal: Runtime Goal Status Summary

### Purpose

The active goal loop should not require manually reading several watcher
packets before deciding whether to keep observing or advance toward the first
bounded real order. A read-only summary packet now classifies the current
runtime state from already-written evidence.

### Required Artifact

| Artifact | Path |
| --- | --- |
| Local/generated packet | `output/strategygroup-runtime-pilot/goal-status/strategygroup-runtime-goal-status.json` |
| Tokyo watcher packet | `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/strategygroup-runtime-goal-status.json` |
| Builder | `scripts/build_strategygroup_runtime_goal_status.py` |
| Watcher drop-in | `deploy/systemd/brc-runtime-signal-watcher.service.d/70-goal-status.conf` |

### Classification

| Status | Meaning | Next safe checkpoint |
| --- | --- | --- |
| `waiting_for_signal` | Runtime is healthy and no fresh StrategyGroup signal exists | `continue_watcher_observation` |
| `fresh_signal_processing` | Fresh signal exists but candidate/authorization evidence is not complete | `prepare_candidate_grant_authorization_evidence` |
| `action_time_finalgate_ready` | Candidate/authorization reached action-time gate boundary | `run_official_action_time_finalgate` |
| `operation_layer_ready` | Required evidence is ready for the official Operation Layer path | `call_official_operation_layer_submit_after_action_time_recheck` |
| `deployment_issue` | Tokyo release, deploy channel, or target runtime head is not ready | Repair deploy channel while continuing watcher observation |
| `hard_safety_stop` | Forbidden effect evidence is present | Stop and investigate |

### Safety

The builder only reads local JSON packets. It does not call Tokyo APIs,
FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawals,
transfers, secrets, live profile, or order sizing. It must never mark a real
order action ready unless selected StrategyGroup, tiny risk, fresh signal,
RequiredFacts, candidate/grant/authorization evidence, action-time FinalGate,
and official Operation Layer evidence are all represented by current packets.

The `runtime_dry_run_audit_passed` check is intentionally stricter than
`runtime-dry-run-audit-chain.json.status=passed`. The goal status packet must
also see these dry-run sub-checks as true before treating the runtime chain as
healthy:

| Dry-run sub-check | Purpose |
| --- | --- |
| `required_scenarios_present` | Confirms the no-signal, mock signal, missing fact, conflict, blocker-review, and closed-loop scenarios are all represented. |
| `all_scenarios_passed` | Confirms every dry-run scenario passed. |
| `dangerous_effects_absent` | Confirms no forbidden effect flag escaped the dry-run packet. |
| `disabled_smoke_not_real_execution_proof` | Prevents disabled smoke from being mistaken for real execution evidence. |
| `operation_layer_evidence_relay_checked` | Confirms evidence IDs connect through the Operation Layer handoff shape. |
| `fresh_signal_fast_auto_chain_checked` | Confirms mock fresh signal reaches candidate/authorization readiness, FinalGate dispatch, and Operation Layer evidence readiness without calling real submit. |
| `legacy_local_registration_probe_tolerance_checked` | Confirms old local-registration probe semantics are tolerated only when the new evidence path is present. |
| `mock_operation_layer_closed_loop_checked` | Confirms fake submit/finalize/reconcile/budget/review shape remains covered without exchange write. |
| `operation_layer_blocker_review_policy_checked` | Confirms active position, open order, protection, budget, duplicate-submit, and scope mismatches become reviewable blocked packets rather than project-stopping chat confirmations, while real submit remains forbidden. |
| `common_execution_chain_reuse_checked` | Confirms MPG / TEQ / FBS / PMR / SOR reuse the shared execution chain and remain input-only StrategyGroup adapters. |
| `strategygroup_adapter_boundary_checked` | Confirms each StrategyGroup handoff only supplies symbols, sides, signal rule, RequiredFacts, tiny risk defaults, and hard stops, while candidate/auth, FinalGate, Operation Layer, finalize, reconciliation, settlement, and Owner readmodel remain in the shared runtime pipe. |
| `selected_strategygroup_dispatch_guard_checked` | Confirms selected MPG-001 mock fresh signal can reach FinalGate dispatch while an out-of-scope StrategyGroup signal is blocked before FinalGate or Operation Layer. |

Operation Layer blockers such as active position, open order, missing protection,
missing budget, duplicate-submit risk, and symbol/side/notional/leverage scope
mismatch must not stop project progress or watcher observation. They must
produce an auditable review packet and Owner-readable unavailable/intervention
state, but `real_submit_allowed` must remain false until the blocker is
resolved through the official path.

### 2026-06-17 Readiness Matrix Checkpoint

`strategygroup-runtime-goal-status.json` now includes
`real_order_readiness_matrix`. This read-only matrix lets the active goal loop
and Owner Console detail surfaces distinguish normal market waiting from
submit-blocking safety conditions.

The packet also projects the common readiness decision at stable top-level
fields so automation and UI consumers do not need to know internal packet
nesting:

| Field | Meaning |
| --- | --- |
| `ready_for_real_order_action` | Direct boolean mirror of the common real-order boundary decision. It remains `false` while waiting for market, missing facts, blocked by safety matrix items, or before official Operation Layer readiness. |
| `checks.ready_for_real_order_action` | Machine-check mirror for smoke tests, heartbeat monitors, and readmodel consumers. |
| `next_safe_checkpoint` | Direct Owner/runtime continuation point, such as `continue_watcher_observation` while no fresh signal exists. |

`owner-console-source-readiness` and the product-state refresh script now
prefer these top-level fields first, then fall back to `checks` and the older
`real_order_boundary` shape only for compatibility with historical packets.

| Matrix item | Purpose |
| --- | --- |
| `selected_strategygroup_scope` | Proves the signal/runtime belongs to the selected StrategyGroup before any real-submit boundary. |
| `fresh_signal` | Separates normal market waiting from runtime failure. |
| `required_facts` | Shows whether RequiredFacts / signed live facts are ready. |
| `candidate_authorization` | Shows whether candidate / authorization evidence has reached the action-time boundary. |
| `action_time_finalgate` | Shows whether action-time FinalGate has passed in the same chain. |
| `official_operation_layer` | Shows whether the official Operation Layer path is ready. |
| `active_position_open_order` | Turns active position or open-order conflicts into explicit blocked evidence. |
| `protection` | Shows missing protection as a submit blocker, not a project blocker. |
| `budget` | Shows missing budget as a submit blocker, not a project blocker. |
| `duplicate_submit` | Keeps duplicate-submit risk as a hard submit blocker. |
| `symbol_side_notional_leverage_scope` | Keeps symbol, side, notional, leverage, and exposure scope mismatches out of real submit. |
| `hard_safety` | Summarizes forbidden effects such as exchange write, order creation, bypass flags, withdrawal, or transfer. |

Each item carries `status`, `blocker_class`, `blocks_real_submit`, `detail`,
and `evidence`. Non-pass states can still allow watcher observation and project
progress, but any item with `blocks_real_submit=true` keeps
`ready_for_real_order_action=false`.

### 2026-06-17 False-Positive Hardening Checkpoint

The readiness matrix now uses explicit blocker-family matching for active
position, open order, and symbol/side/notional/leverage scope rows. Stale fact
names such as `open_order_facts_stale` block `required_facts` only; they must
not be misclassified as active position or open-order conflicts. Benign source
errors such as `symbol_read_error` also must not become scope blockers, while
true `scope_mismatch` and out-of-scope StrategyGroup signals still block real
submit.

### 2026-06-17 Submit-Boundary Closure Checkpoint

`Operation Layer evidence ready` is not sufficient by itself to open the real
order boundary. If any `real_order_readiness_matrix` item has
`blocks_real_submit=true`, `ready_for_real_order_action` must remain false and
the packet must record `matrix_submit_blocker:<key>`.

This keeps the project moving while preserving the live-funds boundary:

| Condition | Project behavior | Real submit behavior |
| --- | --- | --- |
| No fresh signal | Continue watcher observation | Closed |
| Fresh signal with candidate/auth/FinalGate progress | Continue automatic evidence chain | Closed until Operation Layer and matrix pass |
| Operation Layer evidence ready but matrix blocker exists | Record submit-blocker review packet | Closed |
| Operation Layer evidence ready and matrix has no submit blockers | Call official Operation Layer only | Open inside selected tiny boundary |

Submit blockers such as active position, open order, missing protection,
missing budget, duplicate-submit risk, and symbol/side/notional/leverage
mismatch therefore become reviewable evidence and Owner-readable status, not
per-strategy execution forks or opaque project-wide chat confirmations.

Regression coverage now exercises the full submit-blocker family while the
packet is otherwise `official_operation_layer_evidence_ready`: active position,
open order, missing protection, missing budget, duplicate submit, and
symbol/side/notional/leverage mismatch all keep
`ready_for_real_order_action=false` and emit `matrix_submit_blocker:<key>`.

`strategygroup-runtime-goal-status.json` also emits an explicit
`submit_blocker_review` object under `evidence` and mirrored fields under
`real_order_boundary`. When these blockers appear, the packet states:

| Field | Meaning |
| --- | --- |
| `submit_blocker_review.required=true` | A submit-blocker review packet should be recorded. |
| `submit_blocker_review.project_progress_allowed=true` | The project can continue with review/repair work instead of waiting for chat confirmation. |
| `submit_blocker_review.continue_observation_allowed=true` | Watcher observation can continue while real submit stays closed. |
| `submit_blocker_review.real_submit_allowed=false` | No real exchange action is allowed until the blocker is resolved through the official path. |

The review object is limited to matrix rows with `status=blocked`. Natural
waiting states such as no fresh signal, candidate/auth not reached yet,
FinalGate not reached yet, or Operation Layer not reached yet keep real submit
closed but do not create a submit-blocker review requirement.

This makes active position, open order, missing protection, missing budget,
duplicate-submit risk, and symbol/side/notional/leverage mismatch reviewable
runtime evidence, not per-StrategyGroup execution forks.

## P0 Subgoal: Common Runtime Pipe Before Strategy-Specific Adapters

### Current Judgment

The current first-real-submit blocker mix is treated as:

| Share | Scope | Meaning |
| --- | --- | --- |
| 80% | Common runtime pipe | Fresh signal, RequiredFacts readiness, candidate/auth, FinalGate, Operation Layer evidence, live boundary enablement, submit, finalize, reconcile, settle, and Owner readmodel are shared infrastructure. |
| 20% | StrategyGroup adapter | Each StrategyGroup supplies signal semantics, RequiredFacts definitions, supported symbol/side, tiny risk defaults, hard stops, and conflict policy. |

### 2026-06-16 Runtime Boundary Repair

The resume dispatcher now includes a bounded runtime live-enablement relay after
same-run action-time FinalGate pass:

```text
FinalGate PASS
-> prepare Operation Layer evidence
-> if blocked only by runtime shadow boundary
-> official live-enablement preview / mutation
-> re-prepare Operation Layer evidence
-> official Operation Layer submit only when evidence is ready
```

This is a common-chain repair. It must apply to MPG / TEQ / FBS / SOR / PMR
through the same dispatcher path and must not be copied into StrategyGroup
specific code.

### Guardrails

| Guardrail | Required behavior |
| --- | --- |
| Hard safety blockers | Active position, open order, duplicate submit, scope mismatch, withdrawal, transfer, and bypass tokens block live enablement relay. |
| Live enablement mutation | May mutate runtime execution state only through the official API; it must not create orders, call OrderLifecycle, call exchange, mutate budget, or create withdrawal/transfer actions. |
| Operation Layer readiness | Missing evidence is never fabricated; after live enablement the dispatcher must re-run evidence prep and re-check readiness. |
| Strategy adapters | StrategyGroup code remains limited to signal/facts/risk/hard-stop inputs. It must not implement custom FinalGate, Operation Layer, gateway, or settlement paths. |

### 2026-06-17 Scoped Dry-Run Proof Tightening

The dry-run audit chain keeps `scenario_count=14` but now strengthens the
`scoped_pipeline_operation_layer_handoff` scenario:

```text
scoped pipeline evidence
-> dispatcher accepts Operation Layer evidence
-> handoff packet is built from the same evidence IDs
-> official first-real-submit endpoint is called in disabled-smoke mode
-> dispatcher can also call the same endpoint in disabled-smoke mode
-> owner_confirmed_for_first_real_submit_action=false
-> no order, no OrderLifecycle call, no exchange write
```

This closes a rehearsal gap between generic mock disabled-smoke proof and the
real pipeline-shaped scoped local-registration evidence. The dispatcher mode is
selected explicitly with `--operation-layer-submit-mode disabled_smoke` and keeps
the existing real gateway action mode as the default. It is still not real
execution proof and does not authorize bypassing action-time FinalGate or the
official Operation Layer.

### 2026-06-17 Watcher Packet Atomic Deploy Checkpoint

Tokyo is now deployed at
`0414db6fd1a3575d27019663fb39bfd91d5175db` through the bounded git deploy path.
This deploy is a runtime/watcher packet durability repair, not a frontend
publish and not a trading action.

| Item | Result |
| --- | --- |
| Release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-0414db6f-watcher-packet-atomic-writes` |
| Deploy apply | `status=applied`, `interaction.level=L3_bounded_deploy_apply`, `remote_interaction_count=7`, `blockers=[]` |
| Atomic packet writes | `runtime-dry-run-audit-chain.json`, `runtime-execution-chain-closure-status.json`, `strategygroup-runtime-goal-status.json`, and `product-state-refresh-packet.json` now use temp-file replacement |
| Postdeploy snapshot | `status=ready`, `runtime_dry_run_audit_passed=true`, `runtime_execution_chain_closure_status_ready=true`, `watcher_timer_active=true`, `source_readiness_ready=true` |
| Objective chain | `ready_goal_chain_segments=6`, `missing_or_failed_goal_chain_segments=[]` |
| Runtime progress | `P0=waiting_for_market`, `P0.5=ready`, `product_gaps=[]`, `blockers=[]` |
| Safety proof | Deploy and postdeploy checks did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secret mutation, live profile mutation, or order-sizing mutation |

The static Owner Console frontend has already been removed from this main
runtime worktree. Frontend experiments and future UI implementation remain
external and do not affect watcher, dry-run audit, FinalGate readiness,
Operation Layer evidence preparation, or runtime monitoring.

### 2026-06-17 Local Dry-Run Deploy-Channel Context Checkpoint

`strategygroup-runtime-goal-status` now separates local dry-run goal audit from
deployment-head verification. A degraded `deploy_channel` source-health item is
still recorded as evidence, but it only becomes a `deployment_issue` blocker
when the caller provides an explicit deployment context such as
`--release-manifest` or `--expected-head`.

| Context | Deploy-channel degraded behavior |
| --- | --- |
| Local dry-run / goal rehearsal without deployment baseline | Evidence only; do not turn a healthy dry-run chain into `deployment_issue` |
| Tokyo watcher or explicit release/head verification | Blocking `deployment_issue`; real submit remains closed |
| Real-order boundary | Deploy channel evidence alone never opens submit; fresh signal, live facts, candidate/auth, FinalGate, Operation Layer, budget, protection, idempotency, scope, and safety all still need to pass |

This keeps the non-market rehearsal chain useful when the local machine lacks
Tokyo SSH public-key access, while preserving fail-closed deploy verification on
the server path.

### 2026-06-17 Snapshot Goal-Status Nested Checks Checkpoint

The low-interaction Tokyo snapshot now reads `strategygroup-runtime-goal-status`
checks from the nested `checks` object as well as top-level compatibility
fields. This keeps the Owner progress layer from losing important goal-loop
facts when the packet is produced by the current builder.

| Field | Snapshot behavior |
| --- | --- |
| `checks.fresh_signal_present` | Projected into the compact `goal_status` summary as explicit `true` / `false` |
| `checks.deployment_aligned=false` | Blocks the snapshot as `runtime_goal_status_deployment_not_aligned` |
| `checks.watcher_liveness_healthy=false` | Blocks the snapshot as `watcher_liveness_not_healthy` |

This is a monitoring/readability repair only. It does not call FinalGate,
Operation Layer, exchange write, OrderLifecycle, or any real-order path.

### 2026-06-17 Closure Segment Evidence Map Checkpoint

`runtime-execution-chain-closure-status.json` now includes
`dry_run_chain.goal_chain_segment_evidence`. Each objective segment maps back
to both the required dry-run checks and the specific scenario names that proved
the segment.

| Objective segment | Evidence examples |
| --- | --- |
| `fresh_or_mock_signal` | `fresh_signal_fast_auto_chain_checked`, `mock_fresh_signal_dry_run_pass` |
| `required_facts_readiness` | `required_facts_readiness_checked`, `required_facts_missing` |
| `candidate_authorization_evidence` | `non_executing_prepare_auto_bridge_checked`, `non_executing_prepare_auto_bridge` |
| `action_time_finalgate` | `all_selected_strategygroups_reach_finalgate_dispatch_checked`, `non_executing_prepare_auto_bridge` |
| `official_operation_layer_evidence_handoff` | `operation_layer_evidence_relay_checked`, `scoped_pipeline_operation_layer_handoff` |
| `disabled_dry_run_proof` | `disabled_smoke_not_real_execution_proof`, `mock_operation_layer_submit_finalize_pass` |

This makes the non-market closure proof auditable from one packet without
re-reading all raw dry-run artifacts. It remains non-executing and does not
promote disabled smoke into real execution proof.

### 2026-06-17 Closure Evidence Map Deploy Checkpoint

Tokyo is now deployed at
`6a49b8ba9904a10d21f52e946e84bd33d494af84` through the bounded git deploy
path. This deploy publishes the non-market closure evidence map and the latest
monitoring/readability repairs. It does not publish or depend on a frontend.

| Item | Result |
| --- | --- |
| Release | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-6a49b8ba-closure-evidence-map` |
| Deploy apply | `status=applied`, `interaction.level=L3_bounded_deploy_apply`, `remote_interaction_count=7`, `blockers=[]` |
| Postdeploy snapshot | `status=ready`, `watcher_timer_active=true`, `runtime_dry_run_audit_passed=true`, `runtime_execution_chain_closure_status_ready=true`, `source_readiness_ready=true` |
| Goal status | `waiting_for_signal`, `fresh_signal_present=false`, `ready_for_real_order_action=false` |
| Objective chain | `ready_goal_chain_segments=6`, `missing_or_failed_goal_chain_segments=[]` |
| Safety proof | Deploy and postdeploy checks did not call FinalGate, Operation Layer, exchange write, OrderLifecycle, withdrawal, transfer, secret mutation, live profile mutation, or order-sizing mutation |

The local low-interaction snapshot reader now also projects
`goal_chain_segment_evidence` from the closure packet, so one snapshot can show
which dry-run scenarios proved each objective segment.

### 2026-06-17 Pilot Confidence Floor Checkpoint

The StrategyGroup handoff `confidence_min` floor is aligned with the current
pilot reference evaluators. The previous `0.70` floor could block otherwise
valid pilot ready signals before candidate preparation because current pilot
ready-signal evaluators emit `0.58` to `0.62`.

| Item | Result |
| --- | --- |
| Updated handoffs | `MPG-001`, `TEQ-001`, `FBS-001`, `PMR-001`, `SOR-001` |
| Pilot floor | `confidence_min=0.58` |
| Meaning | Candidate-preparation floor only; not execution authority |
| Execution boundary | FinalGate and Operation Layer still required |
| Safety proof | Local tests and dry-run audit only; no Tokyo call, server mutation, exchange write, OrderLifecycle call, or real order |

This checkpoint removes an internal self-contradiction in the fresh-signal fast
chain without expanding symbol, side, notional, leverage, live profile,
credentials, or order-sizing defaults.

### 2026-06-17 Runtime Exit Hardening Checkpoint

The first live-order pilot treats an active position as protected only when the
system can see an exchange-native reduce-only stop. A local SL record is a
useful intent/projection fact, but it is not sufficient to prove live
runaway-loss protection on the exchange.

| Item | Result |
| --- | --- |
| Exchange-native hard stop | `runtime_live_position_monitor` now requires an exchange reduce-only stop for active-position hard-stop protection |
| Local-only SL | A local SL record without exchange stop evidence produces `active_position_missing_hard_stop` plus `local_sl_record_present_but_exchange_native_stop_missing` |
| Holding rule | `can_continue_holding` requires active position, fresh exchange facts, clean severe reconciliation, and exchange-native hard stop |
| TP1 rule | TP1 remains a right-tail exit-plan review shape: default 50% at 1R; when quantity is below market minimum/step, the system keeps hard-stop-only or routes to full reduce-only close review instead of faking a TP order |
| Runner first-stage rule | Runner management is `structure_invalidation_first`; ATR trailing and time stop are review-only helpers; first stage does not auto-amend stops or create runner exit orders |
| Protection failure rule | Entry fill with protection creation failure remains a recovery state: consume/account attempt, hold/reconcile budget, block new entries, require reconciliation, recovery review, and reduce-only recovery mode |
| Post-submit exit outcome matrix | The dry-run audit now names six non-executing post-submit outcomes: entry filled + protection ok, entry filled + protection failed, partial fill, exchange submit failed before acceptance, active position remains open, and position closed by SL / TP / reduce-only recovery |
| Required-check promotion | `post_submit_exit_outcome_matrix_checked` is now a top-level required dry-run check consumed by goal status, Tokyo snapshot, and chain-closure status |
| Safety proof | Local tests only; no Tokyo call, server mutation, FinalGate call, Operation Layer call, exchange write, OrderLifecycle call, withdrawal, transfer, secret mutation, live profile mutation, sizing mutation, or real order |

### 2026-06-17 StrategyGroup Runtime Tier Policy Checkpoint

StrategyGroup expansion is now separated from first-live-order eligibility.
New strategy groups can enter the catalog or observation layers without
competing with the first selected `MPG-001` tiny real-order loop.

| Item | Result |
| --- | --- |
| Tier model | `L0 catalog_only`, `L1 observe_only`, `L2 shadow_candidate`, `L3 armed_observation`, `L4 tiny_real_order_eligible` |
| Current L4 lane | Only `MPG-001` is `L4` for the first bounded live-order pilot |
| Current non-L4 lanes | `TEQ-001=L2`, `FBS-001=L3`, `SOR-001=L3 conditional`, `PMR-001=L1` |
| New group default | `BRF`, `BTPC`, `VCB`, `LSR`, and `RBR` default to `L1 observe_only` unless reviewed and promoted |
| Safety proof | Tier policy is not execution authority, FinalGate input, Operation Layer input, live-profile change, or sizing default |

## Boundaries

- Keep UI experiments outside mainline; the Owner Console source-readiness
  contract remains mainline-owned in `/Users/jiangwei/Documents/final`.
- Keep strategy research in `/Users/jiangwei/Documents/final-strategy-research`.
- Keep main runtime work in `/Users/jiangwei/Documents/final`.
- Do not expose internal gate names as Owner homepage labels.
- Do not treat weak strategy evidence as a live-safety blocker.
- Do not treat missing audit detail as a reason to hide StrategyGroups.
