---
title: OWNER_EXPLANATION_READ_MODEL_CONTRACT
status: CURRENT_DESIGN
authority: docs/current/OWNER_EXPLANATION_READ_MODEL_CONTRACT.md
last_verified: 2026-07-06
---

# Owner Explanation Read Model Contract

## Purpose

This document defines the backend-owned **Owner Explanation Read Model**.

The model translates PG current state, runtime lineage, account safety,
protection, order lifecycle, review state, and intervention state into
Owner-facing product language.

The goal is:

```text
PG/runtime truth remains authoritative.
Backend projection translates that truth.
Frontend and notifications consume translated Owner state.
Audit keeps technical lineage available.
```

This contract does not authorize live submit, FinalGate bypass, Operation Layer
bypass, exchange writes, live-profile expansion, sizing expansion, credential
mutation, protection bypass, reconciliation mutation, withdrawal, or transfer.

## Authority

### Source Contracts

| Source | Role |
| --- | --- |
| `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md` | Owner role, policy authority, intervention boundary |
| `docs/current/RUNTIME_TERMINOLOGY_OWNER_EXPLANATION_GOVERNANCE.md` | Owner language and technical/audit language split |
| `docs/current/PRE_TRADE_RUNTIME_CONTRACT.md` | L1-L9 pre-trade runtime chain |
| `docs/current/BLOCKER_CLASSIFICATION_CONTRACT.md` | Valid blocker classes and completion rules |
| `docs/current/TRADEABILITY_DECISION_CONTRACT.md` | Can-trade read model and first blocker |
| `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md` | Owner-facing StrategyGroup supervision rows |
| `docs/current/RUNTIME_CONTROL_STATE_DB_ARCHITECTURE.md` | PG-backed current projection boundary |

### Authority Rule

The **Owner Explanation Read Model** is a projection.

It may explain:

1. Current opportunity.
2. Stage reached.
3. No-trade reason.
4. Account and protection safety.
5. Owner intervention requirement.
6. Next system action.
7. Audit lineage.

It must not decide:

1. Strategy policy.
2. Tradeability authority.
3. Runtime Safety State.
4. FinalGate result.
5. Operation Layer submit authority.
6. Exchange order state.
7. Review governance outcome.

## Consumers

| Consumer | Use |
| --- | --- |
| Owner Trading Console frontend | Primary runtime/account/opportunity/intervention display |
| Server-side runtime monitor | Quiet/notify reason and Feishu-ready text |
| Runtime forensics | Recent signal and no-trade explanation |
| Daily Live Enablement table | Owner-readable top-line state |
| Strategy Control Board | Strategy-level supervision summary |
| Audit and diagnostics | Technical lineage and source references |

## Required Fields

Every current projection that is used by Owner-facing UI or notification should
provide this field set directly or through a composed read model.

| Field | Type | Meaning | Required |
| --- | --- | --- | --- |
| `owner_state` | enum | Product state for Owner supervision | yes |
| `has_opportunity` | boolean | Whether a current usable opportunity exists | yes |
| `opportunity_strategy_group` | string/null | StrategyGroup for current opportunity | conditional |
| `opportunity_symbol` | string/null | Symbol for current opportunity | conditional |
| `opportunity_side` | enum/null | `long`, `short`, or `event_specific` | conditional |
| `opportunity_summary` | string | One Owner-readable opportunity sentence | yes |
| `plain_language_stage` | string | Plain-language stage reached | yes |
| `plain_language_reason` | string | Why no trade happened or what is happening | yes |
| `plain_language_next_system_action` | string | What the system will do next | yes |
| `account_safety_summary` | string | Account, margin, budget, position state summary | yes |
| `protection_summary` | string | Protection status for active/pending exposure | yes |
| `risk_summary` | string | Risk boundary and budget summary | yes |
| `owner_action_required` | boolean | Whether Owner action is needed | yes |
| `owner_action_reason` | string/null | Plain action reason when required | conditional |
| `intervention_items` | array | Policy/recovery/review items for Owner surface | yes |
| `technical_stage` | string/null | Internal lifecycle stage for audit/detail | yes |
| `first_blocker_class` | string/null | Contract blocker class when present | conditional |
| `no_trade_reason_code` | string/null | Stable machine reason code for UI filtering | conditional |
| `authority_boundary` | string | Statement of what this model does not authorize | yes |
| `lineage_refs` | array | PG/current projection/event/order refs | yes |
| `audit_refs` | array | Audit detail references | yes |
| `updated_at` | timestamp | Projection update time | yes |

## Owner States

Use only these product states for `owner_state`.

| State | Meaning | Owner Action |
| --- | --- | --- |
| `not_enabled` | Strategy or runtime scope is not enabled | Policy action only when requested |
| `running` | Automation is enabled and healthy | No action |
| `waiting_for_opportunity` | System is healthy and waiting for valid market opportunity | No action |
| `processing` | System is handling signal, ticket, submit, protection, reconciliation, settlement, or review | No action unless intervention is separately true |
| `temporarily_unavailable` | Runtime or scope cannot be used right now | Usually no action |
| `needs_intervention` | Owner policy/recovery/review decision is required | Action required |
| `paused` | Owner or system pause is active | Policy action only when requested |
| `completed` | Latest lifecycle is settled and recorded | Review only when requested |

## Data Sources

### Primary Sources

| Information | Source Boundary |
| --- | --- |
| Strategy identity and allowed scope | StrategyGroup registry and policy projection |
| Owner policy state | PG policy events / current policy projection |
| Tradeability and first blocker | Tradeability Decision projection |
| Runtime safety | Runtime Safety State projection |
| Fresh signal and candidate lineage | PG runtime events/current projection |
| Action-time lane and ticket lineage | PG runtime events/current projection |
| FinalGate and Operation Layer results | Official runtime chain events |
| Account, margin, budget, positions, open orders | Account/risk/position/order projections |
| Protection and reconciliation | Protection/reconciliation projections |
| Review state | Strategy asset state / Review Ledger projection |
| Monitor health | Server-side runtime monitor projection |

### Forbidden Sources

The projection must not derive current explanation authority from:

1. Historical archive files.
2. Hand-edited generated output.
3. Chat memory.
4. Frontend mock state.
5. Repo Markdown or JSON when fresher PG/current projection exists.
6. `generated_at` as signal freshness.
7. Replay-only event as live signal.

## L1-L9 Translation Rules

Internal lifecycle terms may be preserved in `technical_stage`, `lineage_refs`,
and audit detail. Primary Owner fields must use product language.

| Internal Stage | Owner Translation |
| --- | --- |
| Candidate universe / observation | 系统正在观察已启用范围 |
| RequiredFacts computed false | 市场条件还没满足 |
| Fresh signal event | 出现新的市场机会 |
| Promotion candidate | 机会可继续推进 |
| Arbitration | 系统正在选择唯一交易前通道 |
| Action-time lane | 交易前处理中 |
| Action-Time Ticket | 候选交易记录已生成 |
| FinalGate | 最终安全检查 |
| Operation Layer | 官方提交路径 |
| Protected submit | 带保护提交 |
| Protection placement | 保护状态记录 |
| Reconciliation | 订单/持仓对账 |
| Settlement / review | 结算与复盘 |

## No-Trade Reason Rules

No-trade explanations must distinguish **market wait**, **engineering gap**,
**policy gap**, **runtime unavailable**, **safety stop**, and **review gap**.

| Case | Required Explanation |
| --- | --- |
| `market_wait_validated` | Say the system is healthy and waiting for valid opportunity |
| `computed_not_satisfied` | Say conditions were computed but market facts did not satisfy |
| `detector_not_attached` / `watcher_tick_missing` | Say monitoring input is pending or stale |
| `scope_not_attached` | Say runtime scope is not connected |
| `policy_scope_missing` | Say Owner policy/risk scope is missing |
| `runtime_profile_scope_missing` | Say runtime profile is incomplete |
| `action_time_preflight_ready` | Say system is processing pre-trade checks |
| `active_position_resolution` | Say position or open order state needs resolution |
| `hard_safety_stop` | Say safety boundary stopped progression |
| `review_only_warning` | Say strategy/outcome requires review |

The projection must not collapse all absent trades into **waiting for market**.

## Intervention Rules

`owner_action_required` may be `true` only when the next step is genuinely an
Owner policy, recovery, or review decision.

| Intervention Type | Owner Meaning |
| --- | --- |
| `policy_gap` | Owner must decide scope, budget, profile, tier, or eligibility |
| `scope_gap` | Owner must approve narrowing or review expansion |
| `budget_gap` | Owner must adjust or confirm budget/risk boundary |
| `runtime_unavailable` | Owner must decide pause/retry only if system cannot self-recover |
| `safety_stop` | Owner must review abnormal safety stop or policy change |
| `recovery_review` | Owner must review an abnormal recovery proposal |
| `strategy_review` | Owner must keep, revise, promote, park, or kill strategy |

Ordinary no-signal, computed-not-satisfied market conditions, normal pre-trade
processing, monitor cache refresh, and detail/audit availability must not create
Owner intervention.

## Account Safety Rules

Account information is first-class, not secondary diagnostics.

The projection should summarize:

1. Equity and available balance.
2. Budget limit, used budget, and reserved budget.
3. Open positions and conflicting exposure.
4. Open orders and duplicate-submit risk.
5. Margin / leverage boundary.
6. Protection coverage.
7. Reconciliation state.

The summary must be connected to runtime state. It must not become a generic
exchange account dashboard detached from strategy opportunity, ticket,
protection, and review.

## Next System Action Rules

`plain_language_next_system_action` must describe the next **system-owned**
step unless `owner_action_required=true`.

| State | Example Next System Action |
| --- | --- |
| `waiting_for_opportunity` | 继续观察已启用策略和币种 |
| `processing` with opportunity | 继续交易前检查或生成候选交易记录 |
| `processing` after submit | 继续保护、对账、结算或复盘 |
| `temporarily_unavailable` | 等待系统刷新或自动恢复 |
| `needs_intervention` | 等待 Owner 决定策略、范围、预算或恢复方案 |

The field must not ask the Owner to manually inspect raw RequiredFacts, assemble
evidence, approve every in-boundary candidate, or operate FinalGate / Operation
Layer.

## Audit And Lineage Rules

`lineage_refs` and `audit_refs` should be available for detail views and
incident review.

They may include:

1. StrategyGroup id.
2. Symbol, side, event spec.
3. Fact snapshot ref.
4. Signal event ref.
5. Promotion ref.
6. Arbitration ref.
7. Lane ref.
8. Ticket id.
9. FinalGate pass/fail ref.
10. Operation Layer command/result ref.
11. Order/protection/reconciliation/review refs.

Audit references must not become Owner operating requirements on primary
surfaces.

## Frontend Integration Boundary

The frontend should consume this model as a read model.

The frontend must not:

1. Recompute `owner_state`.
2. Reclassify `first_blocker_class`.
3. Infer `owner_action_required`.
4. Infer live-submit safety from opportunity or ticket presence.
5. Infer no-trade reason from raw chain objects.
6. Treat mock local state as PG/runtime truth.

## Acceptance Tests

Backend implementation of this contract should include snapshot or fixture
coverage for:

| Case | Expected Owner Explanation |
| --- | --- |
| No signal, all non-market blockers closed | Waiting for opportunity, no Owner action |
| Computed facts not satisfied | Market conditions not met, no Owner action |
| Detector missing | Monitoring input not connected, engineering/system next action |
| Policy scope missing | Owner action required with policy reason |
| Fresh signal promoted but no ticket | Opportunity exists, pre-trade processing not complete |
| Ticket exists but FinalGate not passed | Final safety check not passed, no bypass |
| Operation Layer blocked | Official submit path stopped, no bypass |
| Hard safety stop | Safety stop, Owner action only when recovery/policy decision is needed |
| Protected submit accepted | Submitted with protection and awaits protection/reconciliation/settlement |
| Reconciliation mismatch | Needs intervention only if recovery review is required |

## Chain Position

```text
chain_position: owner_explanation_projection
frontend_dependency: owner_trading_console_read_model
```
