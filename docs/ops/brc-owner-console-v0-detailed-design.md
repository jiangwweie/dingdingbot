> [!NOTE]
> **HISTORICAL_EVIDENCE** — This document is a historical operational, governance, sprint, product, or live-trial artifact from an earlier project phase.
>
> It may be useful for context, auditing, or traceability, but it does **not** represent current project state, constraints, product direction, or agent instructions.
>
> Current authoritative sources:
> - `docs/canon/PROJECT_BASELINE_CURRENT.md`
> - `docs/canon/BRC_TARGET_SEMANTICS.md`
> - `docs/canon/AGENT_WORKSPACE_RULES.md`
> - `docs/canon/RUNTIME_SAFETY_BOUNDARY.md`
> - `docs/canon/TECH_DEBT_BASELINE.md`
> - `docs/canon/DOCUMENT_GOVERNANCE.md`

# BRC Owner Console v0 Detailed Design

Date: 2026-05-26
Status: IMPLEMENTATION_BASELINE

## Purpose

This document turns `brc-owner-console-product-design-v0` into the detailed
implementation baseline for the local Owner Console.

It does not authorize real live, mainnet, withdrawal/transfer, automatic
strategy execution, automatic sizing/leverage/side override, or strategy-pool
execution.

## Backend Contract

`GET /api/brc/readiness` is the v0 console SSOT.

It must include:

- `environment_boundary`;
- `runtime_state`;
- `risk_decision`;
- `risk_account_summary`;
- `strategy_playbook_summary`;
- `action_cards`;
- `global_cutoff_controls`;
- `latest_audit`.

Legacy compatibility fields may remain temporarily, but the v0 frontend should
drive primary pages from the fields above.

### Runtime State

Allowed v0 states:

- `observe`;
- `monitor`;
- `testnet_rehearsal`;
- `paused`;
- `stopped`;
- `flattening`;
- `attention_required`.

Do not expose bare `trade` in v0.

### Risk Decision

Allowed values:

- `ALLOW_READ`;
- `ALLOW_MONITOR`;
- `BLOCK_TESTNET`;
- `ATTENTION_REQUIRED`;
- `BLOCK_ALL_STATE_CHANGE`.

Unknown exposure, unknown order source, unreadable audit facts, or unprovable
flatness should produce at least `ATTENTION_REQUIRED`.

### Action Card

Action cards are application-owned. LLM output is advisory only.

Required fields:

- `action_card_id`;
- `action_type`;
- `authority_source = application_preflight`;
- `fact_snapshot_id`;
- `preflight_result_id`;
- `idempotency_key`;
- `expiry_time`;
- `current_state`;
- `allowed_next_states`;
- `blocked_next_states`;
- `reversible`;
- `final_state_proof_required`;
- `hard_blocks`;
- `advisory_warnings`;
- `confirmation_phrase`;
- `enabled`.

Allowed v0 action types:

- `read_status`;
- `enter_monitor`;
- `testnet_rehearsal`;
- `pause_new_entries`;
- `emergency_stop_runtime`;
- `emergency_flatten`.

## Frontend IA

Primary P0 routes:

- `/command-center`;
- `/llm-copilot`;
- `/strategy-playbook`;
- `/risk-account`;
- `/runtime-control`.

Compatibility redirects:

- `/summary` -> `/command-center`;
- `/markets-orders` -> `/risk-account`;
- `/parameters` -> `/risk-account`;
- `/dashboard` -> `/command-center`.

P1/P2 routes may remain available:

- `/review`;
- `/audit-trail`;
- `/developer`.

## Testnet Acceptance Runbook

The acceptance chain uses the existing fixed BRC ETH/BTC Binance testnet
rehearsal.

Preflight requirements:

- `TRADING_ENV=simulation` or equivalent local simulation posture;
- `EXCHANGE_TESTNET=true`;
- `RUNTIME_PROFILE=brc_btc_eth_testnet_runtime`;
- `RUNTIME_CONTROL_API_ENABLED=true`;
- `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=true`;
- audit persistence writable;
- preflight flatness known;
- Owner confirmation phrase `CONFIRM_BRC_TESTNET_REHEARSAL`.

Expected result:

- workflow id recorded;
- campaign id recorded;
- ETH controlled entry and close recorded;
- BTC controlled entry and close recorded;
- mock profit/loss events recorded;
- third attempt blocked;
- loss-locked switch blocked;
- campaign finalized;
- final inventory `all_flat=true`;
- `withdrawal_executed=false`;
- `live_ready=false`;
- review decision created.

## Review Output

The implementation review must report:

- files changed;
- tests run;
- testnet run result or blocker;
- final inventory proof;
- review decision id if created;
- any residual risks before Owner验收.
