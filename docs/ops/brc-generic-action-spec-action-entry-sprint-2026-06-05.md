# BRC GenericActionSpec and Action Entry Sprint - 2026-06-05

## Verdict

PASS_WITH_CONSTRAINT.

The StrategyFamily `ActionCandidateSpec` layer is now bridged to a read-only
`GenericActionSpec`, action-entry payload contract, and generic final-gate
adapter contract. Trading Console exposes the bridge through a GET-only
`/api/trading-console/action-entry-readiness` read model. No runtime was
started, no Owner execute authorization was created, no execution intent was
created, no order was placed, and no PG mutation was performed.

## Contracts Created

- `GenericActionSpec`
- `ActionEntryPayloadContract`
- `GenericFinalGateAdapterContract`
- `TradingConsoleActionEntryOutput`
- `ActionCandidateSpec -> GenericActionSpec` mapper
- Trading Console `action_entry_readiness` read model

## Current Candidate Semantics

Trend:

- Carrier: `TF-001-live-readonly-v0`
- Generic action status: `valid_blocked_final_gate`
- Symbol: `SOL/USDT:USDT`
- Side: `long`
- Quantity: `0.1`
- Max notional: `20`
- Leverage: `1`
- Max attempts: `1`
- Protection: `single_tp_plus_sl`
- Action registry support: `true`
- Current action state: ready for Owner scope/final-gate review, but not
  executable until all hard gates pass.

Volatility Expansion:

- Carrier: `VB-001-live-readonly-v0`
- Generic action status: `proposal_non_action`
- Action registry support: `false`
- Current action state: proposal only.

Mean Reversion:

- Carrier: `MR-001-live-readonly-v0`
- Generic action status: `proposal_non_action`
- Action registry support: `false`
- Current action state: proposal only.

## Final-Gate Adapter Contract

Hard blockers for live action:

- Missing Owner execute authorization
- Scope mismatch
- PG or exchange exposure unreadable/conflicting
- TP/SL plan unavailable
- Intent/order/review/audit recording unavailable
- Runtime/profile/env/credential guard blocks
- Invalid `GenericActionSpec`

Warnings, not hard blockers:

- Weak strategy evidence
- Incomplete signal markers
- Fee/funding/slippage gaps
- Incomplete review UI
- Non-core read-model degradation

`ExecutionIntent`, entry order, TP/SL, review, and audit remain post-action
acceptance outputs. They are not treated as pre-action strategy proof.

## Trading Console Output

`GET /api/trading-console/action-entry-readiness` returns:

- `generic_final_gate_adapter_contract`
- `generic_action_specs`
- `action_entry_payload_contracts`
- `action_entry_output`
- `candidate_output`

All rows keep:

- `frontend_action_enabled=false`
- `may_execute_live=false`
- `creates_authorization=false`
- `creates_execution_intent=false`
- `places_order=false`
- `mutates_pg=false`

## Blocker Records

Trend remains blocked for actual live execution by final-gate facts:

- Stage: `FinalGateDryRun` / final gate adapter
- Evidence: exact Owner execution authorization, readable non-conflicting
  PG/exchange exposure, valid TP/SL plan, runtime/profile/env/credential guards,
  and intent/order/review/audit recording readiness have not been bound through
  the official executable path in this sprint.
- Retry condition: bind these live facts through the official service/API path
  and re-run the final gate for the exact Trend scope.

## Safety Proof

- Trading Console route added is GET-only.
- `include_exchange=true` was not introduced for the new read model.
- No action API was added.
- No frontend action flag was enabled.
- No auto-execution, cancel, flatten, retry protection, runtime-control, or
  credential path was changed.
- No PG migration was added.
