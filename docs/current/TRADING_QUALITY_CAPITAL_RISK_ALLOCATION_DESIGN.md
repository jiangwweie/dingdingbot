---
title: TRADING_QUALITY_CAPITAL_RISK_ALLOCATION_DESIGN
status: CURRENT_DESIGN
authority: docs/current/TRADING_QUALITY_CAPITAL_RISK_ALLOCATION_DESIGN.md
last_verified: 2026-07-08
---

# Trading Quality Capital Risk Allocation Design

## Purpose

This document defines the next system layer after the PG-backed pre-trade and
ticket-bound order lifecycle are healthy:

```text
tradeable opportunity
-> capital budget
-> risk unit
-> portfolio exposure
-> ticket reservation
-> protected submit
-> outcome review
-> future budget calibration
```

The objective is not to make the system more conservative by default. The
Owner-provided subaccount remains loss-capable experiment capital. The objective
is to make the system allocate that capital deliberately across multiple
StrategyGroups, symbols, and sides, so the best available fresh signal can use
budget without hidden scope expansion, duplicate exposure, or unmeasured
left-tail risk.

This document does not authorize live profile changes, sizing-default changes,
FinalGate bypass, Operation Layer bypass, exchange writes, withdrawal,
transfer, credential mutation, or unsupported symbol/side expansion.

## Known Objective Facts

| Fact | Evidence |
| --- | --- |
| The current runtime path is PG-backed from candidate scope through ticket and post-submit closure | `docs/current/PRE_TRADE_RUNTIME_CONTRACT.md`, `docs/current/TICKET_BOUND_ORDER_LIFECYCLE_AND_EXIT_PROTECTION_DESIGN.md` |
| Active runtime scope is multi-StrategyGroup, multi-symbol, and side-specific by StrategyGroup event spec | `docs/current/PRE_TRADE_RUNTIME_CONTRACT.md` |
| The Owner operating model says the Owner allocates subaccount budget/profile/scope, and the system executes inside official boundaries | `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md` |
| Current system hard stops are mechanical authority and safety boundaries, not generic reasons to de-risk valid opportunities | `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md`, `docs/current/RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md` |
| Current PG design already contains budget reservations, runtime safety snapshots, ticket identity, submit attempts, lifecycle closure, and review concepts | `docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md` |
| Industry risk practice commonly separates position risk, portfolio exposure, volatility scaling, correlation, stress/tail risk, and post-trade outcome review | CFA Institute volatility-targeting summaries, BIS market-risk framework, CME risk-management education |

## Industry Reference Frame

The design uses industry ideas only as engineering inputs. It does not import
institutional capital rules wholesale.

| Industry idea | Useful part for this system | Not used as |
| --- | --- | --- |
| **Per-trade loss budget / stop-based sizing** | Size a position from maximum tolerated loss at stop, not from arbitrary notional | A fixed public "2%" rule for every strategy |
| **Volatility targeting** | Reduce or expand risk unit when realized/forecast volatility changes | A blind leverage multiplier |
| **Risk parity / risk contribution** | Avoid one volatile symbol or correlated cluster consuming all effective risk | A full institutional optimizer |
| **VaR / Expected Shortfall** | Track tail loss and stress exposure as diagnostics and hard-pause inputs | A precise forecast of crypto tail losses |
| **Fractional Kelly** | Treat edge and payoff asymmetry as allocation multipliers after enough evidence | A live sizing formula before reliable win/loss distribution exists |
| **Drawdown circuit breakers** | Pause, downshift, or require review after loss clusters | A reason to block every bounded-aggressive opportunity |
| **Correlation / cluster limits** | Treat BTC/ETH/SOL/AVAX/SUI/OP crypto beta and same-direction exposure as shared risk | A ban on multiple symbols |
| **Post-trade review** | Feed realized slippage, protection acceptance, fill quality, and stop/TP behavior back into future budget | Manual Owner operation of every trade |

Reference sources:

- CFA Institute summaries describe volatility targeting as scaling exposure
  according to changing expected volatility and note that conventional
  volatility targeting can increase turnover, while conditional approaches
  adjust mostly in extreme volatility regimes.
- BIS market-risk materials emphasize expected shortfall and stressed risk
  measurement for tail-risk capture.
- CME Group education emphasizes defining risk before a trade, stop-based loss
  control, and right-sizing positions under leverage.

## Design Position

### New Layer

Add a first-class **Trading Quality / Capital Risk Allocation Layer** between
Action-Time Ticket creation and FinalGate readiness:

```text
L7 Action-Time Ticket
-> L7.5 Capital Risk Allocation
-> L8 FinalGate / Operation Layer / Protected Submit
-> L9 Protection / Reconciliation / Settlement / Review
```

The layer answers:

```text
Given this exact ticket, how much risk budget may it use right now?
```

It must not answer:

```text
Did the strategy signal happen?
Should this unsupported side exist?
May FinalGate or Operation Layer be bypassed?
```

### Core Invariants

| Invariant | Meaning |
| --- | --- |
| **Risk is measured as loss-at-stop first** | Notional is derived from permitted loss, stop distance, leverage, exchange filters, and min notional |
| **Budget is reserved before real submit** | A ticket cannot reach FinalGate-ready without an active PG budget reservation |
| **One real-submit intent remains** | Multi-candidate allocation does not create multiple simultaneous real-submit lanes in V0 |
| **Strategy side remains semantic** | Long/short availability comes from StrategyGroup event specs, never mechanical mirroring |
| **Portfolio limits are explicit** | Same-symbol, same-cluster, same-side, gross, net, margin, and drawdown limits are checked in PG |
| **Quality adjusts budget; it does not invent signals** | Signal quality may affect size after signal validity is proven |
| **Review updates future policy proposals** | Review outcomes recommend policy/risk changes; they do not mutate current authority by themselves |
| **No file authority** | Runtime decisions use PG/current services, not repo MD/JSON, output exports, or reports |

## Recommended Allocation Model

### Why Not Equal Notional

Equal notional is easy but wrong for this system because symbols have different
volatility, stop distance, liquidity, exchange precision, and strategy path
risk. Equal notional can make a tight-stop ETH setup and a wide-stop OP setup
consume very different actual loss budgets.

### Why Not Full Kelly

Full Kelly needs reliable win-rate, payoff distribution, and independent trial
assumptions. The current project is still a small-capital real-profit
experiment. Kelly-style edge may become a multiplier after enough review data,
but it must not be the first production sizing authority.

### Recommended Rule

Use **hierarchical fractional risk-budget allocation**:

```text
Owner account budget
-> portfolio risk budget
-> StrategyGroup risk sleeve
-> symbol/side/event risk cap
-> ticket risk unit
-> exchange-normalized order size
```

The ticket risk unit is:

```text
risk_at_stop = abs(entry_price - stop_price) * quantity
```

For perpetuals, the materializer must also account for:

- leverage and initial/maintenance margin;
- liquidation buffer;
- taker/maker fee estimate;
- stop trigger slippage budget;
- funding estimate when holding window crosses funding intervals;
- exchange min notional, quantity step, price tick, and reduce-only protection
  feasibility.

The system should compute an intended notional only after it has computed the
allowed loss unit.

## Budget Hierarchy

### Portfolio Budget

Portfolio budget is the maximum loss-capable capital allocated to the
experiment.

Required fields:

| Field | Meaning |
| --- | --- |
| `portfolio_budget_id` | Stable budget policy id |
| `account_id` | Runtime account/subaccount identity |
| `currency` | Usually `USDT` |
| `total_loss_budget` | Owner-approved experiment loss capital |
| `daily_loss_limit` | Loss limit for a runtime day/session |
| `weekly_loss_limit` | Optional rolling loss limit |
| `max_open_risk` | Maximum currently-at-risk loss-at-stop across open tickets |
| `max_gross_notional` | Maximum gross notional across open positions |
| `max_margin_used` | Maximum allowed margin usage |
| `drawdown_state` | `normal`, `reduced`, `pause_new_entries`, or `review_required` |
| `policy_version` | Versioned policy |

### StrategyGroup Sleeve

Each active StrategyGroup gets a sleeve. A sleeve is not a guarantee that a
trade will be placed. It is a cap and priority input.

| Field | Meaning |
| --- | --- |
| `strategy_group_id` | StrategyGroup id |
| `risk_sleeve_weight` | Relative share of portfolio risk budget |
| `max_ticket_risk` | Maximum loss-at-stop for one ticket |
| `max_open_risk` | Maximum open risk for this StrategyGroup |
| `max_attempts_per_window` | Attempt count cap |
| `cooldown_after_loss_count` | Pause/downshift after loss cluster |
| `quality_multiplier_min/max` | Bounds for evidence-based size adjustment |
| `allowed_signal_grade` | `trial_grade` or `production_grade` |

### Symbol / Side / Event Cap

Symbol and side caps prevent concentration.

| Field | Meaning |
| --- | --- |
| `symbol` | Canonical symbol |
| `side` | Strategy-supported side |
| `event_spec_id` | Event-specific cap |
| `cluster_key` | `btc_beta`, `eth_beta`, `sol_beta`, `alt_beta`, or configured cluster |
| `max_ticket_risk` | Per-ticket loss cap |
| `max_open_risk` | Per symbol/side cap |
| `max_gross_notional` | Per symbol/side notional cap |
| `min_liquidity_score` | Minimum liquidity/market-quality requirement |
| `max_spread_bps` | Maximum spread at action time |
| `max_volatility_regime` | Optional disable threshold |

## Risk Score And Multipliers

The system should use multipliers, not free-form sizing.

```text
base_ticket_risk
* strategy_quality_multiplier
* signal_quality_multiplier
* volatility_multiplier
* drawdown_multiplier
* correlation_multiplier
* liquidity_multiplier
= candidate_ticket_risk
```

Then:

```text
candidate_ticket_risk
-> min(all applicable caps)
-> exchange-normalized quantity
-> final ticket reservation
```

### Multiplier Rules

| Multiplier | Input | Rule |
| --- | --- | --- |
| `strategy_quality_multiplier` | Rolling review evidence by StrategyGroup version | Starts neutral; changes only from structured review |
| `signal_quality_multiplier` | Event-specific facts already validated | May rank/size only after RequiredFacts pass |
| `volatility_multiplier` | Realized/forecast volatility regime | Reduces risk during extreme volatility; may expand only inside policy cap |
| `drawdown_multiplier` | Portfolio and StrategyGroup drawdown state | Downshifts or pauses new entries after loss clusters |
| `correlation_multiplier` | Open exposure cluster and symbol correlation proxy | Reduces size when same cluster already has open risk |
| `liquidity_multiplier` | spread, depth, min notional, slippage proxy | Blocks or reduces when execution quality is poor |

Any multiplier outside configured bounds must fail closed.

## PG Data Model

### `brc_capital_budget_policies`

Purpose: versioned Owner-approved capital budget policy.

| Column | Rule |
| --- | --- |
| `capital_budget_policy_id` | Stable id |
| `account_id` | Runtime account/subaccount |
| `currency` | Budget currency |
| `policy_version` | Version |
| `status` | `draft`, `active`, `retired` |
| `total_loss_budget` | Numeric |
| `daily_loss_limit` | Numeric |
| `weekly_loss_limit` | Numeric nullable |
| `max_open_risk` | Numeric |
| `max_gross_notional` | Numeric |
| `max_margin_used` | Numeric |
| `created_at_ms` | Runtime time |
| `created_by` | `owner_policy` or system migration |

Constraints:

- one active policy per account and currency;
- active policy cannot have negative budgets;
- active policy requires `total_loss_budget > 0`;
- active policy changes invalidate open reservations that exceed the new cap.

### `brc_strategy_risk_sleeves`

Purpose: StrategyGroup-level risk caps and budget weights.

| Column | Rule |
| --- | --- |
| `strategy_risk_sleeve_id` | Stable id |
| `capital_budget_policy_id` | Parent policy |
| `strategy_group_id` | StrategyGroup |
| `strategy_group_version_id` | Version |
| `risk_sleeve_weight` | Numeric, non-negative |
| `max_ticket_risk` | Numeric |
| `max_open_risk` | Numeric |
| `max_attempts_per_window` | Integer |
| `loss_cooldown_window_ms` | Integer |
| `quality_multiplier_min` | Numeric |
| `quality_multiplier_max` | Numeric |
| `status` | `active`, `paused`, `retired` |

Constraints:

- one active sleeve per `(capital_budget_policy_id, strategy_group_id,
  strategy_group_version_id)`;
- `max_ticket_risk <= max_open_risk`;
- multiplier min/max must be positive and bounded by policy.

### `brc_symbol_side_risk_caps`

Purpose: symbol/side/event caps and concentration grouping.

| Column | Rule |
| --- | --- |
| `symbol_side_risk_cap_id` | Stable id |
| `capital_budget_policy_id` | Parent policy |
| `strategy_group_id` | StrategyGroup |
| `symbol` | Canonical symbol |
| `side` | Supported side |
| `event_spec_id` | Event spec |
| `cluster_key` | Correlation/concentration group |
| `max_ticket_risk` | Numeric |
| `max_open_risk` | Numeric |
| `max_gross_notional` | Numeric |
| `max_leverage` | Numeric |
| `min_liquidity_score` | Numeric nullable |
| `max_spread_bps` | Numeric nullable |
| `status` | `active`, `paused`, `retired` |

Constraints:

- active cap must match an active candidate scope event binding;
- unsupported side cannot have an active cap;
- cap cannot expand live profile or leverage beyond Owner policy.

### `brc_portfolio_exposure_snapshots`

Purpose: current portfolio exposure and concentration facts.

| Column | Rule |
| --- | --- |
| `portfolio_exposure_snapshot_id` | Stable id |
| `account_id` | Runtime account |
| `observed_at_ms` | Observation time |
| `valid_until_ms` | Freshness boundary |
| `equity` | Numeric |
| `available_balance` | Numeric |
| `margin_used` | Numeric |
| `gross_notional` | Numeric |
| `net_notional` | Numeric |
| `open_risk_at_stop` | Numeric |
| `cluster_exposures` | JSONB map from cluster to risk/notional |
| `symbol_exposures` | JSONB map from symbol/side to risk/notional |
| `drawdown_state` | `normal`, `reduced`, `pause_new_entries`, `review_required` |
| `source` | `exchange_account_snapshot`, `reconciliation_projection`, or both |

Constraints:

- ticket sizing cannot use stale exposure snapshot;
- snapshot is read-only current fact, not policy.

### `brc_ticket_risk_estimates`

Purpose: deterministic sizing estimate for one Action-Time Ticket.

| Column | Rule |
| --- | --- |
| `ticket_risk_estimate_id` | Stable id from ticket and policy version |
| `ticket_id` | Action-Time Ticket |
| `capital_budget_policy_id` | Policy used |
| `strategy_risk_sleeve_id` | Sleeve used |
| `symbol_side_risk_cap_id` | Cap used |
| `portfolio_exposure_snapshot_id` | Exposure fact |
| `entry_price_ref` | PG action-time price fact |
| `stop_price_ref` | PG protection reference |
| `base_ticket_risk` | Numeric |
| `final_ticket_risk` | Numeric |
| `intended_notional` | Numeric |
| `normalized_quantity` | Numeric |
| `leverage` | Numeric |
| `estimated_fee` | Numeric |
| `estimated_slippage` | Numeric |
| `estimated_funding` | Numeric nullable |
| `liquidation_buffer` | Numeric nullable |
| `multipliers` | JSONB |
| `blockers` | JSONB |
| `status` | `estimated`, `blocked`, `reserved`, `expired`, `superseded` |
| `created_at_ms`, `valid_until_ms` | Runtime time |

Constraints:

- one current non-expired risk estimate per ticket;
- `status=reserved` requires `final_ticket_risk > 0` and no blockers;
- `normalized_quantity` must satisfy exchange precision and min notional;
- estimate must reference ticket, policy, sleeve, cap, and exposure snapshot.

### `brc_budget_reservations`

The existing budget reservation concept should be strengthened rather than
replaced.

Required additions or equivalent fields:

| Field | Meaning |
| --- | --- |
| `ticket_risk_estimate_id` | Risk estimate used |
| `risk_reserved` | Loss-at-stop reserved |
| `notional_reserved` | Intended notional reserved |
| `margin_reserved` | Margin reserved |
| `reservation_scope` | `ticket_real_submit` or other explicit scope |
| `reservation_state` | `active`, `consumed`, `released`, `expired`, `invalidated` |
| `invalidated_by_policy_version` | Policy change ref |

Hard rule:

```text
No active budget reservation
-> no FinalGate-ready ticket
```

### `brc_trade_quality_reviews`

Purpose: post-trade quality feedback into future risk policy proposals.

| Column | Rule |
| --- | --- |
| `trade_quality_review_id` | Stable id |
| `ticket_id` | Ticket |
| `strategy_group_id`, `symbol`, `side` | Identity |
| `strategy_group_version_id`, `event_spec_id` | Version lineage |
| `ticket_risk_estimate_id` | Pre-submit estimate |
| `budget_reservation_id` | Budget reservation |
| `entry_fill_quality` | JSONB |
| `protection_quality` | JSONB |
| `slippage_realized` | Numeric |
| `fee_realized` | Numeric |
| `funding_realized` | Numeric |
| `pnl_realized` | Numeric |
| `r_multiple` | Numeric |
| `max_adverse_excursion` | Numeric nullable |
| `max_favorable_excursion` | Numeric nullable |
| `first_blocker_or_exit_reason` | String |
| `review_outcome` | `keep`, `downshift`, `pause`, `revise`, `promote`, `park`, `kill` |
| `policy_change_request_id` | Nullable |

Constraints:

- review cannot mutate policy directly;
- policy change requires a separate validated policy event.

## Runtime Flow

### Before Ticket

Before an Action-Time Ticket exists, the system may compute coarse readiness
and risk warnings. It must not reserve budget or size an order from loose
StrategyGroup/symbol/side rows.

### Ticket Created

When a ticket is created:

```text
ticket_id
-> load capital budget policy
-> load strategy sleeve
-> load symbol/side/event cap
-> load current exposure snapshot
-> load action-time price/protection refs
-> compute risk estimate
-> reserve budget
-> mark ticket budget_ready
```

If any required input is missing, the ticket remains blocked with a precise
first blocker:

| Missing input | Blocker |
| --- | --- |
| No active capital policy | `policy_scope_missing:capital_budget_policy` |
| No StrategyGroup sleeve | `policy_scope_missing:strategy_risk_sleeve` |
| No symbol/side/event cap | `policy_scope_missing:symbol_side_risk_cap` |
| Stale exposure snapshot | `action_time_fact_stale:portfolio_exposure` |
| Missing stop/protection ref | `protection_reference_missing` |
| Min notional cannot fit risk budget | `budget_min_notional_infeasible` |
| Existing cluster exposure exceeds cap | `portfolio_concentration_limit` |
| Drawdown state pauses entries | `portfolio_drawdown_pause` |

### FinalGate

FinalGate must consume:

```text
ticket_id
ticket_risk_estimate_id
budget_reservation_id
runtime_safety_snapshot_id
```

FinalGate must reject:

- loose strategy/symbol/side sizing input;
- stale risk estimate;
- expired or invalidated reservation;
- reservation whose scope is not `ticket_real_submit`;
- policy version mismatch;
- exchange-normalized quantity drift after reservation.

### Operation Layer

Operation Layer must receive:

```text
ticket_id
finalgate_pass_id
budget_reservation_id
normalized_quantity
intended_notional
leverage
protection ref
```

Operation Layer must not recompute strategy signal, choose a symbol, choose a
side, or silently resize outside the risk estimate. It may only normalize within
the pre-approved exchange-filter tolerance. If the filter change breaks risk
budget, it must fail closed.

### Post-Submit Review

After lifecycle closure:

```text
lifecycle_closed
-> trade_quality_review
-> policy recommendation
-> optional Owner/system policy event
```

Review can recommend:

- keep same sleeve;
- downshift StrategyGroup multiplier;
- reduce symbol cap;
- pause after execution-quality failure;
- promote multiplier after enough high-quality outcomes;
- kill or park strategy if review proves the loss envelope is not expressible.

Review must not directly change live policy.

## Multi-Strategy / Multi-Symbol / Multi-Side Behavior

### Simultaneous Fresh Signals

If several promotion candidates are valid, arbitration should consider risk
allocation after safety elimination.

Ranking inputs:

| Input | Meaning |
| --- | --- |
| `policy_scope` | Candidate is authorized for this StrategyGroup/symbol/side/event |
| `risk_fit` | Candidate can reserve budget without violating caps |
| `signal_quality` | Event-specific quality score after RequiredFacts pass |
| `portfolio_concentration` | Same symbol/cluster exposure |
| `strategy_priority` | Current Owner/system StrategyGroup priority |
| `freshness` | Event time within freshness window |
| `review_multiplier` | Structured strategy outcome history |

The winner is still only one real-submit lane/ticket in V0.

### Long And Short

Long/short are separate event specs. The risk layer does not mirror a side.

| Case | Required result |
| --- | --- |
| Strategy has only long spec | Short risk cap cannot become active |
| Strategy has only short spec | Long risk cap cannot become active |
| SOR has long and short specs | Each side gets its own cap and conflict rule |
| Same symbol long and short both fresh | Conflict policy decides one or none; no dual submit |

### Correlated Crypto Cluster

The initial cluster model should be simple and explicit:

| Cluster | Symbols |
| --- | --- |
| `btc_beta` | `BTCUSDT` |
| `eth_beta` | `ETHUSDT` |
| `sol_beta` | `SOLUSDT`, `SUIUSDT`, `OPUSDT` |
| `avax_beta` | `AVAXUSDT` |
| `alt_beta` | remaining high-beta alts when added |

This is a policy input, not a statistical claim of stable correlation. It
exists so the system does not accidentally treat several high-beta crypto longs
as independent risk.

## Owner-Facing Explanation

The Owner should see the plain-language outcome:

| Internal state | Owner wording |
| --- | --- |
| `risk_estimate_blocked:min_notional` | 这笔机会按当前止损距离和预算算出来太小，达不到交易所最小下单额 |
| `portfolio_concentration_limit` | 当前同类风险已经够多，这笔不再叠加 |
| `portfolio_drawdown_pause` | 最近亏损触发暂停新开仓，等待复盘或冷却 |
| `budget_reserved` | 这笔候选交易已经锁定预算，正在进入最终安全门 |
| `reservation_expired` | 预算预留过期，不能用旧价格/旧事实下单 |
| `review_downshift_recommended` | 这类交易最近质量下降，系统建议降低后续预算 |

The Owner should not be asked to interpret raw risk-estimate JSON, VaR, ES,
or Kelly values during normal operation.

## Implementation Plan

### Batch A - Design And Policy Tables

| Item | Requirement |
| --- | --- |
| Migrations | Add capital budget policy, strategy sleeve, symbol/side cap, exposure snapshot, ticket risk estimate, and trade quality review tables |
| Constraints | Active policy uniqueness, non-negative numeric fields, supported symbol/side/event cap binding, reservation linkage |
| Tests | Unsupported side cap rejected, missing active policy blocks risk estimate, stale exposure snapshot blocks ticket readiness |

### Batch B - Risk Estimate Materializer

| Item | Requirement |
| --- | --- |
| Input | `ticket_id` only |
| Reads | PG ticket, policy, sleeve, cap, exposure snapshot, protection ref, instrument filters |
| Writes | `brc_ticket_risk_estimates`, strengthened `brc_budget_reservations` |
| Tests | Stop-distance sizing, min-notional infeasible, exchange precision, volatility/downshift multipliers |

### Batch C - FinalGate / Operation Layer Binding

| Item | Requirement |
| --- | --- |
| FinalGate | Require active reservation and current risk estimate |
| Operation Layer | Consume quantity/notional/leverage from risk estimate |
| Tests | Loose sizing rejected, expired reservation rejected, policy-version mismatch rejected, normalization drift rejected |

### Batch D - Portfolio Exposure And Drawdown Projector

| Item | Requirement |
| --- | --- |
| Projector | Build current exposure snapshot from account, positions, open orders, reservations, and stop refs |
| Cadence | Action-time and server monitor; no-signal cadence bounded |
| Tests | Same-cluster exposure cap, active reservation counted, stale exchange facts blocked |

### Batch E - Review Feedback

| Item | Requirement |
| --- | --- |
| Review | Create structured trade quality review after lifecycle closure |
| Policy | Review may create policy change request, not direct mutation |
| Tests | Review downshift request does not change active budget until policy event applies |

## Acceptance Tests

```text
ticket_without_active_capital_policy_cannot_reach_finalgate
ticket_without_strategy_risk_sleeve_cannot_reserve_budget
unsupported_side_cannot_have_active_risk_cap
stop_distance_zero_or_missing_blocks_sizing
min_notional_above_budget_blocks_ticket
volatility_extreme_downshifts_or_blocks_by_policy
same_cluster_open_risk_reduces_or_blocks_new_ticket
drawdown_pause_blocks_new_entries
expired_budget_reservation_blocks_finalgate
operation_layer_rejects_loose_quantity_override
review_recommendation_cannot_mutate_policy_directly
json_or_markdown_export_cannot_create_risk_estimate
```

## Cadence And Performance

| Area | Target |
| --- | --- |
| No-signal tick | No risk estimate rows and no reservations |
| Fresh promotion without ticket | No budget reservation |
| Ticket created | At most one current risk estimate and one active reservation |
| Exposure snapshot | Action-time only plus bounded monitor refresh; no heavy full-history scans |
| PG row growth | One risk estimate per ticket version; one reservation per active ticket; one review per closed ticket |
| CPU-heavy work | Correlation and drawdown windows use precomputed snapshots, not per-tick full replay |
| Disk | No recurring JSON/MD reports; exports are diagnostic only |
| Retention | Never delete policy, ticket, reservation, submit, lifecycle, review lineage; compact stale rejected estimates after audit window |

## Chain Position

```text
chain_position: trading_quality_capital_risk_allocation
strategy_group_id: active WIP StrategyGroups
symbol: active candidate universe
stage: architecture_design
first_blocker: capital/risk allocation is not yet a first-class PG gate between Action-Time Ticket and FinalGate
evidence: current PG ticket lifecycle is healthy, but sizing/risk budget remains split across policy, runtime safety, and execution code
next_action: implement PG capital policy, risk estimate, budget reservation strengthening, and FinalGate/Operation Layer binding
stop_condition: every real-submit ticket has a PG risk estimate and active budget reservation before FinalGate, and review feeds future policy proposals without direct mutation
owner_action_required: no for design; yes only when setting or changing actual capital budget policy
authority_boundary: no FinalGate bypass / no Operation Layer bypass / no exchange write / no live profile or sizing-default mutation
```

## Sources

- CFA Institute Research and Policy Center, **The Impact of Volatility
  Targeting**:
  `https://rpc.cfainstitute.org/research/cfa-digest/2019/07/dig-v49-7-2`
- CFA Institute Research and Policy Center, **Conditional Volatility
  Targeting**:
  `https://rpc.cfainstitute.org/research/financial-analysts-journal/2020/conditional-volatility-targeting`
- Bank for International Settlements, **Revised market risk framework -
  Executive Summary**:
  `https://www.bis.org/fsi/fsisummaries/rmrf.htm`
- Bank for International Settlements, **MAR33 - Internal models approach:
  capital requirements calculation**:
  `https://www.bis.org/basel_framework/chapter/MAR/33.htm`
- CME Group, **Trade and Risk Management**:
  `https://www.cmegroup.com/education/courses/trade-and-risk-management`
- CME Group, **Position and Risk Management**:
  `https://www.cmegroup.com/education/courses/things-to-know-before-trading-cme-futures/position-and-risk-management`
- CME Group, **The 2% Rule**:
  `https://www.cmegroup.com/education/courses/trade-and-risk-management/the-2-percent-rule`

