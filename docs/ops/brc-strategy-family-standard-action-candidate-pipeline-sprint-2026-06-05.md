# BRC StrategyFamily Standard and ActionCandidate Pipeline Sprint - 2026-06-05

## Verdict

PASS_WITH_CONSTRAINT.

The standard onboarding pipeline now exists as read-only backend state and is
exposed through the Trading Console strategy-family admission read model. No live
action was executed, no runtime was started, and no Trading Console action API
was exposed.

## Standards Created

- `StrategyFamilySpec`
- `StrategyGroupSpec`
- `CarrierSpec`
- `RiskDisclosureSpec`
- `ReviewTemplate`
- `ActionCandidateSpec`
- `AdmissionLevel` `L0` through `L4`
- Warning vs hard-blocker policy
- Trading Console `candidate_output`

The standard is available in
`ProductionStrategyFamilyAdmissionState.candidate_pipeline_standard` with
version `brc_strategy_family_action_candidate_standard_v0_1`.

## Admission Levels

- `L0`: archive / rejected / parked; not selectable.
- `L1`: displayable candidate; read-only UI candidate.
- `L2`: action-candidate proposal; can produce proposal-grade
  `ActionCandidateSpec`, but no live action.
- `L3`: Owner-confirmed bounded live candidate; may enter official bounded live
  path only after exact Owner scope, hard gates, TP/SL, recording, and evidence.
- `L4`: budgeted autonomy candidate; design-only unless separately safe and
  auditable.

## Warning vs Hard Blocker Split

Warnings:

- Weak strategy evidence
- Incomplete signal markers
- Incomplete fee / funding / slippage
- Incomplete review UI
- Non-core read-model degradation

Hard blockers for live action:

- Missing Owner execute authorization
- Scope mismatch
- Exposure unreadable or conflicting
- TP/SL plan unavailable
- Intent / order / review / audit recording unavailable
- Runtime / profile / env / credential guard blocks
- Carrier cannot produce valid `ActionCandidate`

Post-action acceptance outputs are `ExecutionIntent`, `Entry`, `TP/SL`,
`Review`, and `Audit`; they are not treated as pre-action strategy proof.

## Examples Added

Trend:

- Strategy family id: `TF-001-live-readonly-v0`
- Admission level: `L3`
- Candidate state: `bounded_live_candidate`
- Carrier scope template: `SOL/USDT:USDT`, `long`, qty `0.1`, max notional
  `20`, leverage `1`, max attempts `1`, `single_tp_plus_sl`
- Action registry support: `true`
- Current action state: blocked by backend final gate and required live evidence.

Volatility Expansion:

- Strategy family id: `VB-001-live-readonly-v0`
- Admission level: `L2`
- Candidate state: `proposal`
- Action registry support: `false`
- Current action state: proposal only.

Mean Reversion:

- Strategy family id: `MR-001-live-readonly-v0`
- Admission level: `L2`
- Candidate state: `proposal`
- Action registry support: `false`
- Current action state: proposal only.

## Trading Console Output

`GET /api/trading-console/strategy-family-admission-state` now includes:

- `candidate_pipeline_standard`
- `strategy_family_specs`
- `strategy_group_specs`
- `carrier_specs`
- `risk_disclosure_specs`
- `review_templates`
- `action_candidate_specs`
- `trading_console_candidate_output`
- concise alias `candidate_output`

All Trading Console candidate rows keep:

- `frontend_action_enabled=false`
- `may_execute_live=false`

## BlockerRecords

Trend remains blocked before live execution:

- Stage: `BoundedLiveAuthorization`
- Bridge: `FinalGateDryRun`
- Evidence: backend final gate has not returned actionable true with full
  official pre-action evidence.
- Retry condition: exact Owner scope, scoped safety clearances/runtime facts,
  readable non-conflicting exposure, valid TP/SL plan, and PG/exchange/review/audit
  recording path must all pass through the official API/service path.

Volatility Expansion remains proposal-only:

- Stage: `CarrierReadinessReport`
- Bridge: `CarrierReadinessReport`
- Retry condition: evaluator/readiness evidence exists and Owner provides
  explicit scoped production authorization.

Mean Reversion remains proposal-only:

- Stage: `CarrierCandidate`
- Bridge: `CarrierCandidate`
- Retry condition: MR evaluator/readiness evidence exists and Owner provides
  explicit scoped production authorization.

## Validation

- `python3 -m py_compile src/application/production_strategy_family_admission.py src/application/readmodels/trading_console.py src/interfaces/api_trading_console.py`
  - PASS
- `python3 -m pytest -q tests/unit/test_production_strategy_family_admission.py tests/unit/test_trading_console_readmodels.py`
  - PASS, `22 passed`
- `git diff --check`
  - PASS

## Safety Proof

- No live order.
- No cancel / replace / flatten / retry protection.
- No runtime start.
- No auto-execution grant.
- No credential or API-key change.
- No PG migration.
- No push.
- Trading Console remains GET-only for this read model.

## Remaining Gaps

- Generic `ActionSpec` model is not yet separated from `ActionCandidateSpec`.
- FinalGate does not yet have a generic StrategyFamily adapter independent of
  BNB/Trend bridge naming.
- Trading Console has no action-entry UI/API; read-only candidate output exists
  for frontend documentation and design.
- Live PG version drift observed in earlier readiness work remains outside this
  sprint unless separately migrated.

## Remaining Generic ActionSpec Gap

The remaining gap is a `GenericActionSpec` plus a generic FinalGate adapter
that consumes `ActionCandidateSpec` and produces an auditable official
action-entry payload for Trading Console, while preserving Owner authorization,
hard gates, TP/SL, PG/review/audit recording, and exchange evidence
requirements. This is gap context only; sequencing remains with the project
controller.
