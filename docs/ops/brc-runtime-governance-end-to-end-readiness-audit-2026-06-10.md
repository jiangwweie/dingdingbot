# BRC Runtime Governance End-to-End Readiness Audit - 2026-06-10

Status: POST_DEPLOYMENT_NON_EXECUTING_READINESS_AUDIT

This audit summarizes the current local and Tokyo deployed readiness for the BRC
strategy runtime governance refactor. It is evidence for non-executing runtime
governance readiness, not live-submit authorization and not order authority.

## 1. Scope

Local worktree:

- path: `/Users/jiangwei/Documents/final-sprint6-integration`
- branch: `release/tokyo-runtime-governance-20260610`
- current local baseline before this stage: `3f5dd229`
- audited deployed backend candidate: `ae9b209e33cd287273491f2e93dfdff3b6a814fd`
- stage commits:
  - `cfd66143 chore(ops): add gated tokyo deploy executor`
  - `6533e066 docs(ops): add authenticated tokyo console evidence`
  - `3450c647 feat(brc): hand scheduled observations to shadow planner`
  - `737ca3b8 feat(console): expose scheduled strategy observation run`
  - `30f4a85d feat(brc): add scheduled shadow planning cli wiring`
  - `cbd22c44 feat(brc): resolve runtimes for scheduled signal planning`
  - `3f5dd229 test(brc): add shadow planning rehearsal verifier`

Current local code is ahead of the deployed backend by non-executing
readiness, scheduler handoff, docs, verifier commits, and local live-runtime
enablement persistence support. The actual deployed runtime code remains
`ae9b209e`.

Current remote Tokyo fact:

- deployed backend HEAD: `ae9b209e33cd287273491f2e93dfdff3b6a814fd`
- deployed migration count: `64`
- deployed latest migration:
  `2026-06-10-064_add_runtime_profile_proposal_snapshot.py`
- health: `status=ok`, `runtime_bound=true`, `live_ready=false`
- public URL: `http://43.133.176.150/`
- public listener: nginx port `80`; backend listener: `127.0.0.1:18080`
- conclusion: Tokyo now runs the non-executing runtime-governance deployment,
  but this is still not live-submit authorization.

## 2. Objective Alignment

Current Owner objective:

```text
small experimental risk capital
-> bounded StrategyRuntimeInstance
-> accept small bounded losses / failed experiments
-> capture rare right-tail gains
-> Owner manually withdraws profits outside the system
```

The current local code and docs preserve this direction:

- bounded losses are treated as acceptable if inside runtime boundaries;
- loss of control, unauditable orders, duplicate submits, stale facts, missing
  protection, boundary breach, and uncontrolled leverage/margin/liquidation risk
  remain the failures to prevent;
- CPM / BRF / BTPC / LSR / RBR / VCB are not claimed as proven-alpha
  strategies;
- RMR remains regime evidence, not a hard execution filter;
- FCO remains data-backlog until deployment-backed fact coverage and Owner
  strategy semantics are confirmed;
- Owner withdrawal remains manual. The system may record capital-base
  adjustment facts for review, but must not initiate withdrawal, transfer, or
  fund movement.

## 3. Current Local Capability Evidence

| Area | Local evidence | Status |
| ---- | -------------- | ------ |
| Strategy semantics gate | `StrategyImplementationBinding`, `RequiredFacts`, `StrategyEvaluationContext`, `EntryPolicy`, `ProtectionPolicy`, `ExitPolicy` exist for B0 reference/backlog strategy families | local shadow/preview ready |
| Strategy signal planning | `RuntimeStrategySignalPlanningService` evaluates raw `StrategyFamilySignalInput` through `RuntimeStrategySignalEvaluationService` and creates only shadow `SignalEvaluation` / `OrderCandidate` when `READY_FOR_SEMANTIC_BINDING` | local non-executing ready |
| CPM/BRF planning | CPM long uses pullback-low or ATR stop; BRF short uses rally-high or ATR stop; both include TP1 1R partial and runner/trailing metadata | local non-executing ready |
| Trusted facts | `StrategyRuntimeFactOverlayService` can replace caller-supplied account/position/market allow facts and block missing trusted sources | local non-executing ready |
| Scheduler handoff | Scheduler readiness and explicit non-executing handoff exist; scheduled observations preserve signal input snapshots and can call the shadow planner only after `allow_shadow_candidate_creation=true` plus a unique ACTIVE shadow runtime resolved from `StrategyRuntimeInstanceService`; the local CLI defaults to observation-only and requires explicit `--shadow-plan` / `--allow-shadow-candidate-creation` flags; Trading Console exposes an operator-auth manual scheduled run POST for this non-executing wiring; a local in-memory rehearsal verifier proves one CPM shadow candidate can be created with all execution/order/exchange flags false | local non-executing ready |
| Runtime safety | Promotion, readiness, and live-enablement preview gates require loss, notional, leverage, margin, liquidation buffer, protection, stale-fact, account, active-position, attempt/budget, BRF short-profile, first-submit, deployment, Owner live-runtime enablement, and Owner real-submit confirmations; a local live-runtime enablement mutation can flip only runtime governance flags after a ready preview and explicit authorization IDs | local runtime-flag mutation ready, no submit |
| Execution bridge | Runtime intent draft, source-native recorded intent audit, submit authorization, controlled-submit plan/preflight/result, attempt reservation/mutation audit, protection plan, OrderLifecycle handoff draft, adapter preview, submit rehearsal exist; local pre-live packet verifier reaches the non-executing submit adapter boundary and now embeds StrategyRuntimeLiveEnablementPreview blockers | local non-submitting bridge only |
| Console productization | Trading Console exposes runtime governance, strategy observation/planning, promotion/readiness, right-tail review, capital-base/withdrawal-adjusted review, and theme toggle surfaces | local UI/API verified previously |
| Deployment | Tokyo backend and Trading Console static frontend are deployed; postdeploy verifier passed with authenticated endpoints expected to require login | deployed non-executing runtime governance |

## 4. Non-Execution Proof

Current local bridge layers are still not execution authority:

- no real exchange order is placed;
- no OrderLifecycle call is made;
- no OwnerBoundedExecution call is made by runtime bridge layers;
- no executable `ExecutionIntent` submit is produced;
- no local order registration is enabled;
- no strategy can self-authorize;
- no withdrawal, transfer, or fund movement is designed or invoked.

The apply-gated Tokyo deploy executor is also not a trading executor. Its dry-run
status at audited HEAD:

```text
status=dry_run_ready
commands_planned=18
commands_executed=0
remote_files_modified=false
database_backup_created=false
migrations_run=false
services_restarted=false
execution_intent_created=false
order_created=false
order_lifecycle_called=false
exchange_called=false
```

## 5. Verified Commands

Historical pre-deployment local packaging at `4ab1efd1`:

```bash
/opt/homebrew/bin/python3 scripts/prepare_tokyo_runtime_governance_release.py \
  --json \
  --write-artifacts
```

Observed result:

```text
status=ready_for_local_packaging
ready_for_packaging=true
tracked_dirty=false
migration_count=64
latest_migration=2026-06-10-064_add_runtime_profile_proposal_snapshot.py
deployed_head_is_ancestor=true
```

Historical pre-deployment plan:

```bash
/opt/homebrew/bin/python3 scripts/plan_tokyo_runtime_governance_deploy.py \
  --json \
  --archive-path output/tokyo-runtime-governance-release/brc-runtime-governance-4ab1efd1-20260610T052753Z/brc-runtime-governance-4ab1efd1-20260610T052753Z.tar.gz \
  --manifest-path output/tokyo-runtime-governance-release/brc-runtime-governance-4ab1efd1-20260610T052753Z/release-readiness-manifest.json \
  --release-name brc-runtime-governance-4ab1efd1-20260610T052753Z
```

Observed result:

```text
status=ready_for_owner_authorized_remote_deploy_plan
ready_for_owner_authorized_remote_deploy=true
blockers=[]
warnings=[]
remote_mutation_requires_confirmation_phrase=OWNER_APPROVES_TOKYO_RUNTIME_GOVERNANCE_DEPLOY
```

Historical pre-deployment executor dry-run:

```bash
/opt/homebrew/bin/python3 scripts/execute_tokyo_runtime_governance_deploy.py \
  --json \
  --archive-path output/tokyo-runtime-governance-release/brc-runtime-governance-4ab1efd1-20260610T052753Z/brc-runtime-governance-4ab1efd1-20260610T052753Z.tar.gz \
  --manifest-path output/tokyo-runtime-governance-release/brc-runtime-governance-4ab1efd1-20260610T052753Z/release-readiness-manifest.json \
  --release-name brc-runtime-governance-4ab1efd1-20260610T052753Z
```

Observed result:

```text
status=dry_run_ready
commands_planned=18
commands_executed=0
blockers=[]
```

Tokyo read-only probe:

```bash
/opt/homebrew/bin/python3 scripts/probe_tokyo_runtime_governance_readonly.py --json
```

Observed result:

```text
status=ready_for_controlled_deploy_preflight
blockers=[]
warnings=[remote_release_identity_from_manifest_without_git_status]
current_head=ae9b209e33cd287273491f2e93dfdff3b6a814fd
current_status=release_manifest_without_git_status
migration_count=64
latest_migration=2026-06-10-064_add_runtime_profile_proposal_snapshot.py
health.status=ok
health.runtime_bound=true
health.live_ready=false
```

Local scheduled-observation shadow-planning rehearsal:

```bash
/opt/homebrew/bin/python3 \
  scripts/verify_strategy_observation_shadow_planning_rehearsal.py \
  --json
```

Observed result:

```text
status=rehearsal_passed
shadow_candidate_created_count=1
signal_evaluation_records=1
order_candidate_records=1
forbidden_execution_flags=[]
database_connected=false
exchange_called=false
execution_intent_created=false
order_created=false
order_lifecycle_called=false
owner_bounded_execution_called=false
withdrawal_or_transfer_created=false
```

Local runtime submit rehearsal pre-live packet:

```bash
/opt/homebrew/bin/python3 \
  scripts/verify_runtime_submit_rehearsal_pre_live_packet.py \
  --json
```

Observed result:

```text
status=blocked_before_first_real_submit
technical_rehearsal_passed=true
ready_for_first_real_submit=false
ready_for_live_runtime_enablement_mutation_design=false
technical_blockers=[]
operational_blockers=[
  current_head_not_deployed_to_tokyo,
  owner_real_submit_authorization_missing
]
implementation_blockers=[
  runtime_not_live_execution_enabled,
  controlled_submit_adapter_not_implemented
]
live_enablement_blockers include:
  current_head_not_deployed_to_tokyo,
  owner_live_runtime_enablement_authorization_missing,
  owner_real_submit_authorization_missing,
  controlled_submit_adapter_not_implemented
forbidden_execution_flags=[]
submit_rehearsal_status=ready_for_non_executing_submit_adapter_boundary
submit_adapter_preview_status=inputs_ready_adapter_not_implemented
```

Current deployment-prep Phase 0 is aligned to this Tokyo baseline: the
deployment plan requires local packaging readiness, a `064 -> 065` migration
gap audit with one expected revision, the local scheduled-observation
shadow-planning rehearsal, and the local runtime submit pre-live packet
technical rehearsal before any Owner-authorized remote mutation phase. The
pre-live packet may pass its technical rehearsal while still reporting live
enablement blockers; those blockers are intentional and must not be treated as
deployment blockers unless the task is to perform live-runtime enablement.

## 6. Focused Test Evidence

Deployment safety and script-risk tests:

```bash
/opt/homebrew/bin/pytest -q \
  tests/unit/test_tokyo_runtime_governance_deploy_executor.py \
  tests/unit/test_script_risk_classifier.py \
  tests/unit/test_tokyo_runtime_governance_deploy_plan.py \
  tests/unit/test_tokyo_runtime_governance_postdeploy_verify.py \
  tests/unit/test_tokyo_runtime_governance_readonly_probe.py
```

Observed result:

```text
28 passed
```

Strategy Signal -> Shadow Candidate Planning v1 tests:

```bash
/opt/homebrew/bin/pytest -q \
  tests/unit/test_b0_runtime_strategy_signal_planning.py \
  tests/unit/test_runtime_strategy_signal_evaluation_service.py \
  tests/unit/test_b0_strategy_semantics_binding.py \
  tests/unit/test_strategy_candidate_semantics.py \
  tests/unit/test_reference_price_action_evaluators.py \
  tests/unit/test_cpm_historical_evaluator_and_experiment.py \
  tests/unit/test_brf_price_action_evaluator.py
```

Observed result:

```text
45 passed
```

Scheduler / API / trusted-overlay tests:

```bash
/opt/homebrew/bin/pytest -q \
  tests/unit/test_strategy_observation_shadow_planning_rehearsal.py \
  tests/unit/test_strategy_group_observation_script.py \
  tests/unit/test_strategy_group_live_readonly_observation.py \
  tests/unit/test_b0_runtime_strategy_signal_scheduler_assembly.py \
  tests/unit/test_b0_strategy_runtime_fact_overlay.py \
  tests/unit/test_trading_console_readmodels.py
```

Observed result:

```text
89 passed
```

Runtime bridge / FinalGate / promotion readiness tests:

```bash
/opt/homebrew/bin/pytest -q \
  tests/unit/test_td4_runtime_final_gate_preview.py \
  tests/unit/test_td5_runtime_execution_plan.py \
  tests/unit/test_strategy_runtime_safety_readiness.py \
  tests/unit/test_b0_strategy_runtime_promotion_gate.py \
  tests/unit/test_b0_strategy_runtime_promotion_gate_service.py
```

Observed result:

```text
118 passed
```

These tests prove the local non-executing planning, scheduler handoff, runtime
bridge preview, and readiness surfaces. They do not prove live trading behavior.

## 7. Remaining Hard Gates

The following are not complete and must not be silently inferred:

1. Scheduler-backed strategy signal handoff is now productized locally as an
   injectable, non-executing scheduled-observation-to-shadow-planner bridge
   with a runtime-service-backed unique ACTIVE shadow runtime resolver and an
   explicit CLI wiring path plus operator-auth manual Trading Console POST.
   CLI/API defaults remain observation-only; missing trusted account facts
   still block candidate planning. Tokyo autonomous scheduling / triggering is
   still not enabled.
2. Hard authenticated API `200` evidence for each Trading Console endpoint is
   still limited by local Chrome client blocking direct `/api/*` navigation.
   Authenticated UI read-model rendering has been verified; a follow-up should
   use a server-side read-only verifier or temporary read-only validation token
   for endpoint-by-endpoint proof.
3. FCO remains blocked until deployment-backed funding/OI/crowding fact coverage
   and Owner-confirmed semantics exist.
4. Runtime profiles are proposals / confirmation evidence only until Owner/Codex
   confirms exact live profile values and materializes the allowed runtime path.
   Local code can now apply a live-runtime flag mutation after the live
   enablement gate, but Tokyo has not been deployed to that local 065 target.
5. First real runtime submit still requires explicit confirmations for attempt
   consumption, budget reservation/release/consume, protection failure
   handling, duplicate-submit blocking, account/active-position facts,
   stale-fact behavior, deployment readiness, and explicit Owner real-submit
   authorization.
6. Controlled runtime submit adapter, real OrderLifecycle adapter, and exchange
   order submit remain intentionally unimplemented / disabled for runtime
   governance.
7. No automatic withdrawal or transfer design is allowed.

## 8. Owner Authorization Boundary

The 2026-06-10 Tokyo runtime-governance deployment was Owner-authorized and
applied. Deployment remains separate from live-submit authorization.

Real-funds order placement still requires a separate explicit Owner decision at
the action-time trading gate. Do not treat deployment, shadow planning, runtime
profile confirmation, promotion-gate preview, or readiness tests as permission
to submit orders.
