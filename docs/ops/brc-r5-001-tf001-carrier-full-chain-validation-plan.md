# BRC-R5-001 TF-001 Carrier Full-chain Validation Plan

Status: REVIEW

## Goal

Use `TF-001` as a full-chain validation carrier for the BRC Owner Console
governance loop.

This is not a strategy alpha proof, not a profitability claim, not a parameter
optimization task, and not a live-readiness task.

The validation target is:

`Owner input -> LLM advisory context -> Operation preflight -> Owner confirmation -> runtime/testnet carrier -> audit refs -> review/evidence packet`

## Hard Boundaries

- No live/mainnet execution.
- No withdrawal or transfer.
- No arbitrary trading, arbitrary symbol, arbitrary side, or arbitrary size.
- No strategy pool.
- No parameter optimization.
- No claim that TF-001 is profitable or runtime-promoted.
- No LLM authorization or LLM direct execution.
- No actual emergency flatten, order cancel, or position close unless a later
  separate Owner-authorized task designs and approves that capability.

## Acceptance Shape

The carrier validation should prove that the existing Owner Console governance
surfaces can carry a named playbook through the chain while preserving the
Operation Layer as the only authorization source.

Required evidence:

- operation capability snapshot;
- account facts source, truth level, and reconciliation evidence summary;
- preflight summary with operation id, preflight id, idempotency key, and
  confirmation requirement;
- confirm result with audit/campaign/review refs where available;
- runtime-state summary before and after the carrier action;
- review/evidence packet that states `TF-001` was used as a carrier only.

## Task Card For Claude

```markdown
# Task ID
BRC-R5-001B

## Goal
Draft and maintain the TF-001 carrier full-chain validation plan and acceptance
checklist. TF-001 is only a carrier for validating the Owner Console governance
chain.

## Why
The Owner Console v0 and Operation Layer need a named full-chain carrier before
any broader R5 validation. The project must not imply strategy profitability,
strategy-pool construction, or live readiness.

## Allowed files
- docs/ops/brc-r5-001-tf001-carrier-full-chain-validation-plan.md
- docs/ops/live-safe-v1-task-board.md
- docs/ops/live-safe-v1-progress.md
- docs/product/brc-owner-console-current-state.md

## Forbidden files
- src/application/execution_orchestrator.py
- src/application/order_lifecycle_service.py
- src/application/position_projection_service.py
- src/application/capital_protection.py
- src/infrastructure/exchange_gateway.py
- src/application/reconciliation.py
- src/application/startup_reconciliation_service.py
- runtime profiles, exchange credentials, env files, and any trading endpoint

## Requirements
1. State clearly that TF-001 is a carrier, not alpha proof or profitability
   evidence.
2. Preserve Operation Layer as the only Owner Console authorization source.
3. Keep LLM advisory-only.
4. Forbid live/mainnet, withdrawal/transfer, arbitrary trading, strategy pool,
   actual flatten, order cancel, and position close.
5. Define evidence artifacts needed for later implementation.

## Tests
- Documentation review against roadmap and Owner Console current-state docs.
- `git diff --check`.

## Done When
- The plan is decision-complete for a later implementation slice.
- Task board and progress notes reflect BRC-R5-001A/B/C sequencing.
- No product feature, runtime capability, or trading path is added.
```

## Implemented Local Smoke

TF-001 is now present in the BRC playbook catalog as a
`carrier_validation_only` playbook. It is not marked as controlled-testnet
execution authority and does not create strategy-pool, live, withdrawal,
transfer, order cancel, position close, or actual flatten authority.

Repeatable bounded smoke command:

```bash
python3 scripts/brc_owner_console_smoke.py \
  --mode tf001-carrier-full-chain \
  --output /tmp/brc-tf001-carrier-full-chain.json
```

Expected result:

- `completed=true`;
- `select_playbook=executed` through `switch_playbook`;
- Owner confirmation is bound to `operation_id + preflight_id +
  idempotency_key`;
- `monitor=noop` through `enter_strategy_or_monitor`, with no unrestricted
  auto trading;
- `pause=executed` through `enter_pause`;
- `stop=executed` through `emergency_stop_runtime`, with
  `does_not_flatten=true` and `does_not_cancel_orders=true`;
- `review=executed` through `write_review_decision`;
- operation list includes every chain operation;
- campaign playbook after the smoke is `TF-001`;
- safety flags remain false for live, strategy execution, actual flatten,
  order cancel, position close, withdrawal/transfer, and LLM authorization.

## Initial Decision Review

Command:

```bash
python3 scripts/brc_owner_console_smoke.py \
  --mode tf001-carrier-decision-review \
  --output /tmp/brc-tf001-carrier-decision-review.json
```

Expected current verdict:

- `TF-001` switch-playbook readiness is `true`;
- `switch_playbook` preflight recognizes `TF-001` as an allowlisted carrier
  validation playbook;
- `enter_strategy_or_monitor` validates the monitor carrier path as `noop`;
- campaign playbook remains unchanged because this mode reviews readiness only;
- no strategy execution, live/mainnet, withdrawal/transfer, order cancel,
  position close, or actual flatten is executed.
