# SQ02 Downside Continuation Strategy Contract Skeleton v0

Last updated: 2026-05-25

Status: Docs-only strategy-contract skeleton

Runtime effect: none

Trading permission effect: none

Default state: disabled by default

## Purpose

This document defines the first docs-only `StrategyContract` skeleton for the
Personal Leveraged Campaign mainline.

Candidate:

- `SQ02_DOWNSIDE_CONT_V0`

This skeleton is a contract-boundary artifact only. It does not promote SQ02 to
scanner, alert, watchlist, runtime, paper, testnet, tiny-live, live, account,
leverage, sizing, position, or real order-path use.

## Contract Identity

| Field | Value |
|---|---|
| `strategy_contract_id` | `SQ02_DOWNSIDE_CONT_V0` |
| `strategy_name` | `SQ02 downside continuation sandbox skeleton` |
| `runtime_label` | `LOCAL_SANDBOX_ONLY_DISABLED_BY_DEFAULT` |
| `disabled_by_default` | `true` |
| `direction` | `SHORT` |
| `entry_action` | `enter` |

## Local Feature Snapshot

The local sandbox skeleton uses intentionally abstract feature keys:

| Feature Key | Meaning | Notes |
|---|---|---|
| `setup_present` | Closed/prior feature snapshot says the setup is present. | Placeholder for future deterministic research-derived features. |
| `setup_invalidated` | Closed/prior feature snapshot says the setup is invalidated. | Must reject before order planning when true. |

This feature snapshot is not a scanner and does not read live market data.

The feature snapshot object is:

- `docs/schemas/personal_campaign/feature_snapshot.schema.json`
- `docs/schemas/personal_campaign/examples/feature_snapshot_sq02_downside_cont_v0.example.json`

Boundary:

- `input_scope` must be `closed_or_prior_inputs_only`;
- `source` must be `local_sandbox_closed_or_prior`;
- `llm_trade_decision_used` must be `false`;
- forbidden data must include lookahead, LLM trade decision, real account
  state, and exchange API state.

## Setup And Invalidation Contract

The current local contract is:

```json
{
  "setup_condition_key": "setup_present",
  "invalidation_condition_key": "setup_invalidated",
  "required_feature_snapshot": ["setup_present", "setup_invalidated"]
}
```

Interpretation:

- if `setup_invalidated=true`, emit a rejected `TradeIntent`;
- if `setup_present=false`, emit a rejected `TradeIntent`;
- if `setup_present=true` and `setup_invalidated=false` inside an armed
  campaign session, emit an allowed local `TradeIntent`;
- the emitted `TradeIntent` has no exchange side effect and must still pass
  `RiskOrderPlan` rules.

## Forbidden Inputs

The skeleton forbids:

- lookahead data;
- LLM trade decisions;
- real account data;
- exchange API state;
- real order, fill, transfer, or withdrawal state;
- withdrawal instruction, amount, schedule, or automation;
- leverage, sizing, or discretionary direction decisions from LLM/agent output.

## Risk Boundary

This skeleton cannot produce an order plan. It can only produce a `TradeIntent`.

Every allowed `TradeIntent` must pass:

- order-plan caps;
- position lifecycle protection checks;
- campaign loss/profit protection checks;
- profit-protect reduce/close checks.

The current rule matrix is:

- `docs/ops/personal-campaign-risk-rule-matrix-v0.md`

## Example Artifacts

Current examples live under:

- `docs/schemas/personal_campaign/examples/strategy_contract_sq02_downside_cont_v0.example.json`
- `docs/schemas/personal_campaign/examples/feature_snapshot_sq02_downside_cont_v0.example.json`
- `docs/schemas/personal_campaign/examples/mode_advice_sq02_downside_cont_v0.example.json`
- `docs/schemas/personal_campaign/examples/human_arm_decision_arm_sq02.example.json`

These examples are parsed by unit tests against local Pydantic models.

## Non-Authorization

This skeleton does not authorize runtime wiring, paper/testnet/live/tiny-live,
real API keys, real account data, real orders, cancellations, transfers,
withdrawals, withdrawal instructions, leverage advice, sizing advice, or direct
research-to-order wiring. Owner handles withdrawals outside this system.
