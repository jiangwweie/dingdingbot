---
title: RUNTIME_CONTROL_STATE_MAINLINE_FILE_IO_MAP
status: CURRENT_DESIGN
authority: docs/current/RUNTIME_CONTROL_STATE_MAINLINE_FILE_IO_MAP.md
last_verified: 2026-07-05
---

# Runtime Control State Mainline File I/O Map

## Purpose

This document records the current **mainline MD/JSON read/write map** for the
StrategyGroup pre-trade runtime.

It exists for one reason:

```text
do not migrate file chaos into PG
```

The target is:

```text
facts/events/diagnostics
-> one owner projector
-> DB current projection
-> JSON/MD export
```

The target is not:

```text
current JSON files
-> JSONB document bucket
-> the same scripts still decide independently
```

## Evidence Scope

This map is based on the current worktree as of 2026-07-04, using direct source
inspection of:

| Area | Files inspected |
| --- | --- |
| systemd watcher service and post-steps | `deploy/systemd/brc-runtime-signal-watcher.service`, `deploy/systemd/brc-runtime-signal-watcher.service.d/*.conf` |
| systemd server monitor service | `deploy/systemd/brc-runtime-monitor.service`, `deploy/systemd/brc-runtime-monitor.timer` |
| pre-trade control builders | `scripts/build_strategygroup_tradeability_decision.py`, `scripts/build_replay_live_parity_audit.py`, `scripts/build_strategy_live_candidate_pool.py`, `scripts/build_daily_live_enablement_table.py`, `scripts/build_single_lane_task_packet.py`, `scripts/build_strategygroup_runtime_goal_status.py` |
| runtime fact builders | `scripts/fetch_binance_usdm_public_facts.py`, `scripts/build_runtime_account_safe_facts.py` |
| detector/fresh-signal builders | `scripts/build_sor_session_scope_detector.py`, `scripts/build_strategy_fresh_signal_action_time_boundary.py`, `scripts/build_mi_trial_admission_decision.py`, `scripts/build_brf2_runtime_signal_facts.py` |
| monitor/product refresh | `scripts/run_tokyo_runtime_server_monitor.py`, `scripts/refresh_strategygroup_runtime_product_state_artifacts.py` |
| watcher/action-time adjacent scripts | `scripts/runtime_signal_watcher_tick.py`, `scripts/build_runtime_signal_watcher_readiness_pack.py`, `scripts/runtime_signal_watcher_resume_dispatcher.py`, `scripts/runtime_dry_run_audit_chain.py`, `scripts/materialize_pg_promotion_action_time_lane.py`, `scripts/materialize_action_time_ticket.py`, `scripts/materialize_ticket_bound_post_submit_closure.py` |

This document focuses on the **Tokyo watcher post-step / pre-trade runtime /
server monitor mainline**. It does not inventory every local diagnostic or
historical research script.

## Mainline Systemd Post-Step Map

| Order | Service step | Reads MD/JSON | Writes MD/JSON | Current role | PG target |
| --- | --- | --- | --- | --- | --- |
| 00-A | `runtime_signal_watcher_tick.py --require-database-url` | PG runtime control state candidate scope via `runtime_active_observation_monitor.py`, env files | `latest-status.json`, `watcher-tick.json`, `status-artifact.json`, `supervisor-artifact.json`, `operator-evidence.json`, `wakeup-evidence.json`, `notification-state.json` | Main watcher tick and runtime observation source | Reads DB candidate scope; writes watcher coverage, signal/fact events, diagnostics |
| 00-B | `build_runtime_signal_watcher_readiness_pack.py` | watcher report JSON such as `watcher-tick.json`, `wakeup-evidence.json`, `status-artifact.json`, `notification-state.json` | `deployment-readiness-artifact.json`, `post-signal-resume-pack.json` | Readiness/resume pack builder after watcher tick | Readiness export and action-time lane refs |
| 40 | `runtime_signal_watcher_resume_dispatcher.py` | `post-signal-resume-pack.json` | `resume-dispatch-artifact.json`, optional `operation-layer-arm-evidence.json` | Action-time resume/dispatch bridge after fresh signal | `brc_action_time_lane_inputs`, execution-chain evidence refs, not current goal status |
| 60 | `runtime_dry_run_audit_chain.py` | handoff JSON under `docs/current/strategy-group-handoffs`, `main-control-runtime-tier-policy.json` | `runtime-dry-run-audit-chain.json`, `dry-run-audit-chain/*.json` | Non-executing audit/rehearsal evidence | `brc_legacy_diagnostics` or rehearsal evidence refs; not production authority |
| 70 | `brc-runtime-signal-watcher.service.d/70-goal-status.conf` | none in current worktree | none in current worktree | Retired final Goal Status writer | Must remain no-writer after `brc_goal_status_current` exists |
| 80-A | first product-state sequence | watcher `latest-status.json` for runtime coverage validation, PG `pretrade_public` fact snapshots for detector/fact builders, PG runtime control state for Candidate Pool / Daily Table / Single Lane Packet | server-side public facts export, SOR detector, MI admission, BRF2 facts, Candidate Pool export, Daily Table export, Single Lane Packet export | Rebuilds pre-trade control exports from PG-backed current projections without repo `output/runtime-monitor/latest-*` current inputs | DB fact/event writes plus current projection exports |
| 80-B | `refresh_strategygroup_runtime_product_state_artifacts.py` | operator-authenticated readmodel APIs plus dry-run/closure/deploy diagnostic exports only | source-readiness, pilot status, chain closure, live-closure evidence, product refresh packet | Product-state and closure evidence export refresh; no live-facts precollect and no runtime fact authority | fact/event rows, legacy diagnostics, closure evidence refs |
| 80-C | final product-state sequence | PG account/public/action-time facts and PG runtime control state for Candidate Pool / materializers / Daily Table / Single Lane Packet / Goal Status | server-side account-safe facts export, action-time boundary export, Candidate Pool export, action-time lane materialization export, Action-Time Ticket materialization export, Runtime Safety State export, ticket-bound post-submit closure export, Daily Table export, Single Lane Packet export, Goal Status export | Final same-tick control refresh; validators may read generated server-side exports, but control builders, ticket issuer, Runtime Safety projector, and post-submit closure materializer use PG current state | owner projectors write current projections, Action-Time Ticket rows, Runtime Safety snapshots, and post-submit closure rows; JSON is export only |

## Server Monitor Systemd Map

| Step | Service command | Reads MD/JSON | Writes MD/JSON | Current role | PG target |
| --- | --- | --- | --- | --- | --- |
| monitor pre | none in current `brc-runtime-monitor.service` | none | none | Monitor no longer refreshes public-facts JSON as a prerequisite | Fact refresh belongs to watcher/fact projectors, not monitor |
| monitor main | `run_tokyo_runtime_server_monitor.py --require-database-url` | PG runtime control state and systemd status | `latest-server-side-runtime-monitor.json` export | Production quiet/notify classification | `brc_server_monitor_runs`, `brc_server_monitor_notifications` |

## Current Mainline File Families

### Runtime Fact Files

| File | Current writers | Current readers | Current role | PG target | Key issue |
| --- | --- | --- | --- | --- | --- |
| `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/latest-status.json` | watcher service | Candidate Pool, coverage validator, systemd shell | Runtime active monitor / watcher scope export | `brc_watcher_runtime_coverage` | File shape and freshness must not decide production monitor notifications |
| `output/runtime-monitor/latest-binance-usdm-public-facts.json` and `/home/ubuntu/brc-deploy/reports/runtime-monitor/latest-binance-usdm-public-facts.json` | `fetch_binance_usdm_public_facts.py` | human review / diagnostics only | Public market fact snapshot export; production detector builders read PG `pretrade_public` facts | `brc_runtime_fact_snapshots` | Must not be read as runtime input |
| `output/runtime-monitor/latest-binance-usdm-public-facts.md` and server report MD counterpart | `fetch_binance_usdm_public_facts.py` | Owner/agent readability | Human export | Export only | Must not be read for runtime |
| `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/strategy-group-live-facts-input.json` | retired product-state precollect path | none in production mainline | retired readonly live/private fact collector export | `brc_runtime_fact_snapshots` | Server refresh and product-state refresh no longer write or consume this file |
| `/home/ubuntu/brc-deploy/reports/runtime-monitor/latest-account-safe-facts.json` | `build_runtime_account_safe_facts.py` | human review / diagnostics only | Account/open-order/balance safety facts export; production action-time boundary and operator live-fact evidence read PG `account_safe` / `account_mode` snapshots | `brc_runtime_fact_snapshots` / `brc_runtime_safety_state_snapshots` | Must not be read as runtime input |

### Detector And Strategy Fact Files

| File | Current writers | Current readers | Current role | PG target | Key issue |
| --- | --- | --- | --- | --- | --- |
| `output/runtime-monitor/latest-sor-expanded-scope.json/md` | `build_sor_session_scope_detector.py` | diagnostics/Owner progress | SOR scope view | `brc_legacy_diagnostics` or export | Scope view must not become scope authority |
| `output/runtime-monitor/latest-sor-session-detector-facts.json/md` | `build_sor_session_scope_detector.py` | action-time boundary diagnostics and human review exports | SOR detector facts | `brc_live_signal_events`, `brc_runtime_fact_snapshots` | Detector fact output must not become Candidate Pool authority |
| `output/runtime-monitor/latest-mi-trial-admission-decision.json/md` | `build_mi_trial_admission_decision.py` | strategy governance diagnostics and human review exports | MI admission/trial decision | `brc_strategy_governance_decisions`, `brc_admission_decisions`, export | Governance decision is mixed into runtime output |
| `output/runtime-monitor/latest-brf2-runtime-signal-facts.json/md` | `build_brf2_runtime_signal_facts.py` | BRF2 diagnostics and human review exports | BRF2 runtime signal facts | `brc_live_signal_events`, `brc_runtime_fact_snapshots` | Short-side conditional state should not be inferred from latest file |
| `output/runtime-monitor/latest-strategy-fresh-signal-action-time-boundary.json/md` | `build_strategy_fresh_signal_action_time_boundary.py` | action-time diagnostics and human review exports | Fresh-signal/action-time boundary view | `brc_live_signal_events`, `brc_runtime_fact_snapshots`, `brc_promotion_candidates`, `brc_action_time_lane_inputs`, `brc_action_time_tickets`, export | Builder CLI is PG-only; strategy JSON artifacts are not accepted as action-time boundary inputs |

### Control Read Model Files

| File | Current writers | Current readers | Current role | PG target | Key issue |
| --- | --- | --- | --- | --- | --- |
| `output/runtime-monitor/latest-strategygroup-tradeability-decision.json/md` | `build_strategygroup_tradeability_decision.py` | local diagnostics, human review exports, remaining legacy evidence refs | Can-trade / first-blocker read-model export | PG-only read model over registry, policy, facts, safety, readiness current projections | Production CLI rejects repo/output JSON inputs; Tradeability export is not a source |
| `output/runtime-monitor/latest-replay-live-parity-audit.json/md` | `build_replay_live_parity_audit.py` | Tradeability diagnostics, human review exports, remaining legacy evidence refs | Replay/live parity read model | `brc_legacy_diagnostics`, detector parity rows, read-model export | Production Candidate Pool and Daily Table no longer consume this export; replay diagnostics can be mistaken for current live readiness |
| `output/runtime-monitor/latest-strategy-live-candidate-pool.json/md` | `build_strategy_live_candidate_pool.py` | validators and human review exports | Per-symbol readiness and promotion view | `brc_pretrade_readiness_rows`, `brc_promotion_candidates`, `brc_action_time_lane_inputs`, export | Builder CLI is PG-only; latest file is export/diagnostic only |
| `output/runtime-monitor/latest-daily-live-enablement-table.json/md` | `build_daily_live_enablement_table.py` | validators and human review exports | Main control table | `brc_control_read_model_snapshots` export over current projections | Builder CLI is PG-only; latest file is export/diagnostic only |
| `output/runtime-monitor/latest-single-lane-task-packet.json/md` | `build_single_lane_task_packet.py` | agents and human review exports | One-lane task packet | task export only | Builder CLI is PG-only; should never reclassify market waits into engineering closure |
| `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/strategygroup-runtime-goal-status.json` | `build_strategygroup_runtime_goal_status.py` | product-state refresh, server monitor/Owner surfaces | Current goal summary | `brc_goal_status_current` plus export | Goal Status builder is PG-only; Candidate Pool is derived from PG control state, not JSON input |
| `/home/ubuntu/brc-deploy/reports/runtime-monitor/latest-server-side-runtime-monitor.json` | `run_tokyo_runtime_server_monitor.py` | Owner/ops diagnostics | Server monitor run summary | `brc_server_monitor_runs` plus export | Monitor should read DB current projections, not output files |
| `/home/ubuntu/brc-deploy/reports/runtime-monitor/server-monitor-dedupe-state.json` | retired legacy monitor versions | none in current monitor path | Retired notification dedupe file | `brc_server_monitor_notifications` | Current monitor rejects file dedupe state and reads/writes PG notification rows |

### Policy, Registry, And Handoff Files

| File | Current writers | Current readers | Current role | PG target | Key issue |
| --- | --- | --- | --- | --- | --- |
| `docs/current/strategy-group-handoffs/strategygroup-registry-baseline.json` | manual/reviewed docs | Tradeability Decision and strategy tooling | StrategyGroup registry baseline | `brc_strategy_groups`, `brc_strategy_group_versions` | Runtime-facing registry is file-sourced |
| `docs/current/strategy-group-handoffs/owner-pretrade-runtime-authorization-v0.json` | manual/reviewed docs | Candidate Pool | Owner pre-trade authorization | `brc_owner_policy_events`, `brc_owner_policy_current`, `brc_runtime_scope_bindings` | Owner policy is file-sourced |
| `docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json` | manual/reviewed docs | dry-run audit chain and adjacent reviews | Tier policy | `brc_owner_policy_events`, `brc_owner_policy_current` | Tier state can drift from runtime scope |
| `docs/current/strategy-group-handoffs/*/handoff.json` | strategy handoff docs | dry-run audit chain, strategy/intake tooling | Strategy semantics and evidence | `brc_strategy_groups`, `brc_strategy_group_versions`, `brc_required_fact_contracts`, archive refs | Strategy semantics are stored as repo documents |
| `docs/current/strategy-group-handoffs/strategygroup-pre-live-rehearsal-readiness-current.json` | generated/reviewed docs | Runtime Safety State | Pre-live readiness compatibility source | `brc_runtime_safety_state_snapshots`, `brc_legacy_diagnostics` | Rehearsal readiness can act like a runtime source |
| `docs/current/RUNTIME_MONITOR_BASELINE.json` | manual/reviewed docs | local daily/goal monitor paths | Monitor baseline | DB seed or typed config | Should not be production monitor authority |

### Product-State And Closure Evidence Files

| File | Current writers | Current readers | Current role | PG target | Key issue |
| --- | --- | --- | --- | --- | --- |
| `product-state-refresh-packet.json` | product-state refresh | ops/diagnostics | product refresh summary | `brc_control_read_model_snapshots` export | Should not drive runtime |
| `strategy-group-live-facts-readiness.json` | product-state refresh from Trading Console PG-backed readmodel | Owner/product diagnostics only | PG-derived live fact readiness export | `brc_runtime_fact_snapshots`, current safety projection | Goal Status and trading decisions must not read this file; the readmodel itself reads PG fact snapshots |
| `owner-console-source-readiness.json` | product-state refresh | Goal Status | Owner console source readiness | Owner-console read model export | Owner UI readiness is not trading authority |
| `strategygroup-runtime-pilot-status.json` | product-state refresh | Goal Status | legacy pilot/scope alignment | `brc_legacy_diagnostics` | Must not set main current blocker |
| `runtime-execution-chain-closure-status.json` | product-state refresh | product-state/Goal Status adjacent | closure status | execution-chain evidence refs | Closure evidence is not current runtime scope |
| `runtime-live-closure-evidence*.json` | product-state refresh | product-state/ops | live closure evidence | execution/review evidence refs | Evidence should not overwrite current readiness |
| `tokyo-deploy-channel-status.json`, `tokyo-readonly-probe-current.json` | deploy/probe tooling | product-state refresh | deploy/probe diagnostics | deploy evidence refs or `brc_legacy_diagnostics` | Deploy success is not live-submit readiness |

### Action-Time Adjacent Files

| File | Current writers | Current readers | Current role | PG target | Key issue |
| --- | --- | --- | --- | --- | --- |
| `post-signal-resume-pack.json` | watcher/fresh signal path | resume dispatcher, Goal Status | resume input after fresh signal | `brc_promotion_candidates`, `brc_action_time_lane_inputs` refs | Must bind StrategyGroup/symbol/side/profile before submit |
| `resume-dispatch-artifact.json` | resume dispatcher | Goal Status | resume dispatcher outcome | action-time/execution-chain evidence refs | Missing/mismatched names previously produced missing-artifact states |
| `operation-layer-arm-evidence.json` | resume dispatcher when enabled | ops/execution diagnostics | Operation Layer arm evidence | official execution evidence table | Must not bypass FinalGate or Operation Layer |
| `runtime-dry-run-audit-chain.json` | dry-run audit chain | Goal Status, product-state refresh | non-executing rehearsal audit | rehearsal evidence refs, `brc_legacy_diagnostics` | Useful for diagnostics, not production submit authority |
| `action-time-ticket-materialization.json` | `materialize_action_time_ticket.py` | ops/diagnostics, test validators | PG Action-Time Ticket issuer export | `brc_action_time_tickets`, `brc_action_time_ticket_events` | Export only; FinalGate must consume `ticket_id` from PG, not this JSON |

### Retired File-Authority Bridges

| Retired bridge | Previous role | Replacement | Enforcement |
| --- | --- | --- | --- |
| `build_runtime_fresh_attempt_readiness_projection.py` / `runtime_fresh_attempt_readiness_projection` | Built a fresh-attempt readiness decision by aggregating operator evidence, fresh-signal loop, readiness evidence, authorization binding, handoff, and FinalGate JSON reports | PG chain: `brc_live_signal_events` -> `brc_promotion_candidates` -> `brc_action_time_lane_inputs` -> `brc_action_time_tickets` -> ticket-bound FinalGate preflight -> Runtime Safety State | Script and tests are removed; resume dispatcher rejects this retired scope with `blocked_by_retired_file_authority_projection` |
| `build_runtime_strategy_required_facts_readiness_artifact.py` / `runtime_strategy_required_facts_readiness_artifact` | Built RequiredFacts readiness by combining local strategy semantics catalog rows with optional JSON fact-source reports | PG contracts and facts: `brc_required_fact_contracts`, `brc_strategy_event_required_facts`, `brc_runtime_fact_snapshots`, Candidate Pool RequiredFacts readiness fields | Script and tests are removed; production RequiredFacts readiness must come from PG current projections or typed domain services that feed PG |

## Critical Conflict Points

| Conflict | Current shape | Impact | Required PG closure |
| --- | --- | --- | --- |
| Goal Status multiple writer history | `70-goal-status.conf` and product-state refresh are retired as Goal Status writers; product-state refresh must not expose a `--refresh-goal-status` CLI or builder hook; final Goal Status is written by the dedicated PG-backed builder in the 80 sequence | Last writer can overwrite current status with older inputs if retired writers return | `brc_goal_status_current` has one owner projector |
| Retired Candidate Pool JSON in Goal Status | `--candidate-pool-json` and local file diagnostic fallback are removed from `build_strategygroup_runtime_goal_status.py` | Reintroducing the option would allow the same Goal Status export to decide from different facts | Goal Status derives Candidate Pool/current readiness from PG control state only |
| Legacy pilot status as blocker | `strategygroup-runtime-pilot-status.json` contains watcher scope alignment | Old scope mismatch can hide fresh/waiting state | Store as `brc_legacy_diagnostics`; cannot set current blocker |
| Tradeability as broad generated source | Tradeability production CLI is PG-only; remaining file readers belong to other diagnostics/builders | Reintroducing broad JSON inputs would let stale optional artifacts alter current tradeability | Tradeability stays a DB-backed read model over typed current projections |
| Replay/live diagnostics as readiness proxy | Replay/live parity audit output is still consumed by Tradeability diagnostics and remaining legacy evidence refs, but not by production Candidate Pool or Daily Table | Historical parity diagnostics can be confused with current live detector coverage | Store parity as diagnostic/read-model rows, separate from watcher coverage current projection |
| Watcher reads Candidate Pool export | Production `runtime_signal_watcher_tick.py` and `runtime_active_observation_monitor.py` reject `--candidate-universe-json` and read PG candidate scope/runtime bindings | A previous-cycle read model must not define the observer universe | Watcher reads `brc_strategy_group_candidate_scope` and runtime scope bindings, not Candidate Pool export |
| Candidate Pool / Daily Table / Packet feedback loop | Candidate Pool, Daily Table, and Single Lane Packet are PG-only | A stale previous export must not influence a new current projection | Candidate Pool, Daily Table, and Single Lane Packet read DB current projections and write exports only |
| File freshness hidden in path names | Files named `latest-*` encode recency by convention | Builders may treat stale latest files as current | Fact/projection rows include `observed_at_ms`, `valid_until_ms`, and `input_watermark` |
| Same fact family in multiple directories | Public facts can exist under both `output/runtime-monitor` and server report dirs | Different consumers can read different snapshots | Fact snapshots are DB rows; file paths are exports |
| Candidate universe duplicated | systemd symbol list, `DEFAULT_CANDIDATE_UNIVERSE`, Owner auth JSON, runtime watcher scope | Different layers can disagree on which symbols are active | `brc_strategy_group_candidate_scope` and `brc_runtime_scope_bindings` become source |
| Governance output mixed with runtime output | MI admission and strategy handoff data live beside runtime facts | Admission state can be confused with live readiness | Strategy governance tables feed registry/policy/scope projections |
| Server monitor as file aggregator | legacy monitor versions read Daily Table, Candidate Pool, facts, watcher status, deploy health, and dedupe JSON | Reintroducing those arguments would make production notification depend on stale files | Current monitor rejects legacy JSON arguments, reads DB projections, and writes monitor/notification tables |
| Action-time evidence as loose files | resume pack, dispatch artifact, operation evidence, dry-run audit are separate JSONs | Hard to prove a single candidate intent | action-time lane, candidate/auth, execution evidence share lane/input refs |
| Fresh-attempt readiness projection as file bridge | old `runtime_fresh_attempt_readiness_projection` aggregated several JSON reports and could dispatch fresh authorization from the aggregate | It could recreate a second authority path between fresh signal and FinalGate | Retired; use PG action-time lane, Action-Time Ticket, ticket-bound FinalGate preflight, and Runtime Safety State |
| RequiredFacts readiness as local projection | old `runtime_strategy_required_facts_readiness_artifact` read local semantics plus optional JSON fact-source reports | It could disagree with PG RequiredFacts contracts and fact snapshots | Retired; use PG RequiredFacts contracts, strategy-event RequiredFacts rows, and runtime fact snapshots |

## PG Route By Mainline Domain

| Domain | Current file source | Target DB source | Export retained |
| --- | --- | --- | --- |
| Strategy registry | registry baseline JSON and handoff JSON | `brc_strategy_groups`, `brc_strategy_group_versions`, `brc_required_fact_contracts` | registry export |
| Owner policy and live-submit scope | `owner-pretrade-runtime-authorization-v0.json`, tier policy JSON | `brc_owner_policy_events`, `brc_owner_policy_current` | policy export for audit only |
| Candidate universe | PG candidate scope/runtime bindings in production; code constants, policy JSON, and Candidate Pool export are not production runtime authority | `brc_strategy_group_candidate_scope`, `brc_owner_policy_current`, `brc_runtime_scope_bindings`, event specs | Candidate Pool export for audit/diagnostic only |
| Runtime scope/profile binding | policy JSON, runtime reports | `brc_runtime_scope_bindings`, `runtime_profiles` | Runtime Safety / Candidate Pool export |
| Runtime bootstrap admission | PG candidate scope/runtime bindings only; handoff/intake/Candidate Pool/active-runtime JSON inputs are rejected | `brc_strategy_group_candidate_scope`, `brc_owner_policy_current`, `brc_runtime_scope_bindings` | runtime bootstrap artifact |
| Watcher coverage | watcher `latest-status.json`, active monitor JSON | `brc_watcher_runtime_coverage` | watcher coverage export |
| Public/account/action-time facts | `latest-*facts.json`, live-facts input | `brc_runtime_fact_snapshots` | fact export |
| Strategy signals | detector output JSONs | `brc_live_signal_events` | detector export |
| Tradeability and first blocker | Tradeability JSON | DB-backed Tradeability read model over registry, policy, facts, readiness, safety | Tradeability export |
| Replay/live parity | replay parity JSON | diagnostic/read-model rows with source replay/live detector refs | parity export |
| Readiness and promotion | PG current projection; Candidate Pool JSON is export only | `brc_pretrade_readiness_rows`, `brc_promotion_candidates` | Candidate Pool export |
| Action-time lane | PG promotion/action-time materializer over current control state | `brc_action_time_lane_inputs` | action-time export |
| Action-Time Ticket | PG action-time lane identity | `brc_action_time_tickets`, `brc_action_time_ticket_events` | ticket materialization export |
| Protected submit attempt | submit API response JSON / dispatcher artifact | `brc_ticket_bound_protected_submit_attempts` | submit attempt export |
| Post-submit closure | dispatcher artifact / old authorization finalize output | `brc_ticket_bound_post_submit_closures` | post-submit closure export |
| Goal Status | report-dir goal-status JSON plus legacy artifacts | `brc_goal_status_current` | goal-status export |
| Server monitor and notification | PG current projections plus readonly systemd status | `brc_server_monitor_runs`, `brc_server_monitor_notifications` | monitor export |
| Strategy governance/admission | handoff JSON, MI admission JSON, review snapshots | `brc_strategy_governance_decisions`, admission tables, registry/version tables | governance export |
| Legacy diagnostics | pilot status, deploy/probe reports, dry-run audit files | `brc_legacy_diagnostics` and evidence refs | diagnostic export |

## Migration Rules

### Rule 1: No New Direct Runtime Reads

New production runtime code must not add direct reads from:

- `docs/current/**/*.json`;
- `output/runtime-monitor/latest-*.json`;
- `/home/ubuntu/brc-deploy/reports/**/latest-*.json`;
- local cache files;
- generated MD files.

Temporary reads must go through `RuntimeControlStateRepository` or explicitly
marked seed/import/export tooling.

### Rule 2: One Owner Projector Per Current State

Each current state needs one owner:

| Current projection | Owner projector | Must not be written by |
| --- | --- | --- |
| Tradeability current/export | Tradeability read-model projector | Candidate Pool, Daily Table, strategy governance importers |
| Replay/live parity export | parity diagnostic projector | Candidate Pool, Tradeability, runtime coverage collector |
| Candidate Pool current | Candidate readiness projector | detector builders, Daily Table, Goal Status |
| Daily Table current/export | Daily Table read-model projector | Candidate Pool, Single Lane Packet |
| Single Lane Packet export | task packet exporter | Candidate Pool, Goal Status |
| Goal Status current | Goal Status projector | product-state refresh, legacy 70 post-step, server monitor |
| Runtime Safety State | Runtime Safety projector | Candidate Pool, Goal Status |
| Protected Submit Attempt | ticket-bound protected submit adapter | dispatcher, reconciliation, settlement, review |
| Post-submit closure | ticket-bound post-submit closure materializer | Candidate Pool, Daily Table, Goal Status, old authorization finalize |
| Server monitor current | server monitor runner | local heartbeat, local monitor sequence |

### Rule 3: Legacy Files Become Diagnostics

Legacy files may be kept only as diagnostics or provenance:

- `strategygroup-runtime-pilot-status.json`;
- dry-run audit chains;
- deploy/probe reports;
- historical output snapshots;
- old handoff packs after import.

They must not set current blockers when DB-backed current projections are fresh.

### Rule 4: Exports Must Carry Lineage

Every generated JSON export should carry:

- `schema`;
- `projection_run_id`;
- `owner_projector`;
- `input_watermark`;
- `source_priority`;
- `generated_at_ms`;
- release head or code version;
- authority boundary.

## Implementation Batches

| Batch | Goal | Main files retired as sources | DB/projection target |
| --- | --- | --- | --- |
| P0-A | freeze direct file-source expansion | new direct `docs/current` / `output` reads | source-ban validator |
| P0-B | introduce repository boundary | direct file reads inside watcher tick, Tradeability, replay/live parity, Candidate Pool, Daily Table, Goal Status, server monitor | `RuntimeControlStateRepository`; server monitor production path is PG-only |
| P0-C | close projection ownership | goal-status and latest output feedback loops | `brc_projection_runs`, `brc_current_projection_ownership`, `brc_goal_status_current` |
| P0-D | migrate policy/scope | Owner auth JSON, tier policy JSON, candidate constants | owner policy, candidate scope, runtime bindings |
| P0-E | migrate coverage/facts | watcher status JSON, public/account fact JSON | watcher coverage and fact snapshots |
| P1-A | migrate readiness/promotion/action-time/ticket | Candidate Pool, action-time boundary, resume pack, loose prepare identity | readiness, promotion, action-time lane, Action-Time Ticket tables |
| P1-B | migrate strategy governance | handoff packs, MI admission, review snapshots | strategy governance, admission, registry/version tables |
| P1-C | convert monitor and output to exports | server monitor JSON and output snapshots; legacy dedupe JSON retired | monitor runs/notifications and export snapshots |

## Completion Criteria

This map is satisfied only when:

| Requirement | Done when |
| --- | --- |
| Mainline inventory | Every current mainline MD/JSON source and writer is classified |
| Single writer | Each current projection has one owner projector |
| No generated-view feedback | Candidate Pool, Daily Table, Single Lane Packet, Goal Status, and server monitor do not read each other's latest JSON as authority |
| DB current source | policy, scope, coverage, facts, readiness, promotion, action-time, goal status, and monitor state are DB-backed |
| Export-only files | JSON/MD files remain reproducible exports or diagnostics only |
| Safety unchanged | No FinalGate bypass, Operation Layer bypass, exchange write, profile mutation, sizing mutation, stale-fact submit, or missing-protection submit |

## Chain Position

```text
chain_position: runtime_control_state_file_io_map
strategy_group_id: active WIP StrategyGroups
symbol: active candidate universe
stage: db_source_boundary_design
first_blocker: mainline runtime still has transitional MD/JSON source and export feedback paths
next_action: implement source-ban validator, repository boundary, and current projection ownership closure
stop_condition: production runtime reads DB/code/API current projections and JSON/MD is export-only
owner_action_required: no
authority_boundary: file I/O governance is non-executing and must not call FinalGate, Operation Layer, or exchange write
```
