# BRC Runtime Governance End-to-End Readiness Audit - 2026-06-10

Status: PRE_DEPLOYMENT_READINESS_AUDIT

This audit summarizes the current local readiness for the BRC strategy runtime
governance refactor. It is evidence for an Owner/Codex deployment decision, not
deployment authorization, not live-submit authorization, and not order
authority.

## 1. Scope

Local worktree:

- path: `/Users/jiangwei/Documents/final-sprint6-integration`
- branch: `codex/sprint6-console-runtime-integration`
- audited deployment candidate: `4ab1efd1580ceac337bac7e997a3496b632384a1`
- stage commits:
  - `cfd66143 chore(ops): add gated tokyo deploy executor`
  - readiness audit commit: read from `git log` for the current branch

This document is itself a docs-only evidence commit. If it becomes part of the
deployment target, regenerate the release archive and dry-run plan for the
current HEAD immediately before applying deployment.

Current remote Tokyo fact:

- deployed HEAD: `415d398509872cb25bf969319e29732764f9615b`
- deployed migration count: `44`
- deployed latest migration:
  `2026-06-08-044_create_live_lifecycle_reviews.py`
- health: `status=ok`, `runtime_bound=true`, `live_ready=false`
- conclusion: Tokyo is healthy but still behind the local runtime-governance
  branch. Do not describe local Sprint 5-7 / B0 capabilities as deployed until
  the controlled deployment is applied and verified.

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
| Scheduler handoff | Scheduler readiness and explicit non-executing handoff exist; shadow planning requires `allow_shadow_candidate_creation=true` | local non-executing ready |
| Runtime safety | Promotion and readiness gates require loss, notional, leverage, margin, liquidation buffer, protection, stale-fact, account, active-position, attempt/budget, BRF short-profile, first-submit, and deployment confirmations | local non-executing ready |
| Execution bridge | Runtime intent draft, source-native recorded intent audit, submit authorization, controlled-submit plan/preflight/result, attempt reservation/mutation audit, protection plan, OrderLifecycle handoff draft, adapter preview, submit rehearsal exist | local non-submitting bridge only |
| Console productization | Trading Console exposes runtime governance, strategy observation/planning, promotion/readiness, right-tail review, capital-base/withdrawal-adjusted review, and theme toggle surfaces | local UI/API verified previously |
| Deployment prep | Release prep, Tokyo read-only probe, migration-gap audit, deployment plan, postdeploy verifier, and apply-gated deploy executor exist | local dry-run ready |

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

Local packaging at `4ab1efd1`:

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

Deployment plan:

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

Executor dry-run:

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
warnings=[]
current_head=415d398509872cb25bf969319e29732764f9615b
migration_count=44
health.status=ok
health.runtime_bound=true
health.live_ready=false
```

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

These tests prove the local non-executing planning surface, not deployed runtime
behavior and not live trading behavior.

## 7. Remaining Hard Gates

The following are not complete and must not be silently inferred:

1. Tokyo controlled deployment has not been applied.
2. Tokyo Alembic migration jump `044 -> 064` has not been run.
3. Tokyo postdeploy verifier has not been run against deployed `4ab1efd1`.
4. Strategy scheduler-backed ingestion is not productized on Tokyo.
5. FCO remains blocked until deployment-backed funding/OI/crowding fact coverage
   and Owner-confirmed semantics exist.
6. Runtime profiles are proposals / confirmation evidence only until Owner/Codex
   confirms exact live profile values and materializes the allowed shadow
   runtime path.
7. First real runtime submit still requires explicit confirmations for attempt
   consumption, budget reservation/release/consume, protection failure
   handling, duplicate-submit blocking, account/active-position facts,
   stale-fact behavior, deployment readiness, and explicit Owner real-submit
   authorization.
8. Controlled runtime submit adapter, real OrderLifecycle adapter, and exchange
   order submit remain intentionally unimplemented / disabled for runtime
   governance.
9. No automatic withdrawal or transfer design is allowed.

## 8. Owner Authorization Boundary

Remote deployment apply requires a separate explicit Owner authorization. The
confirmation phrase is:

```text
OWNER_APPROVES_TOKYO_RUNTIME_GOVERNANCE_DEPLOY
```

Without that explicit deployment authorization, do not run:

```bash
/opt/homebrew/bin/python3 scripts/execute_tokyo_runtime_governance_deploy.py \
  --apply \
  --confirmation-phrase OWNER_APPROVES_TOKYO_RUNTIME_GOVERNANCE_DEPLOY
```

Even after deployment, real-funds order placement remains a separate gate.
Deployment is not live-submit authorization.
