---
title: MULTI_STRATEGY_MULTI_SYMBOL_MULTI_SIDE_ACTION_TIME_EVOLUTION_DESIGN
status: CURRENT_DESIGN
authority: docs/current/MULTI_STRATEGY_MULTI_SYMBOL_MULTI_SIDE_ACTION_TIME_EVOLUTION_DESIGN.md
last_verified: 2026-07-06
---

# Multi-Strategy Multi-Symbol Multi-Side Action-Time Evolution Design

## Purpose

This document defines how the system should evolve when multiple strategies,
symbols, and sides produce valid fresh signals at the same time.

The design preserves the current philosophy:

```text
wide observation
-> medium-wide candidate readiness
-> multiple promotion candidates
-> one real-submit action-time lane
-> one Action-Time Ticket
-> one ticket-bound protected submit intent
```

This document does not authorize multiple simultaneous real-submit lanes in the
current V0 runtime.

## Known Objective Facts

| Fact | Evidence |
| --- | --- |
| Current pre-trade contract already allows wide observation, multiple candidates, and one action-time lane | `docs/current/PRE_TRADE_RUNTIME_CONTRACT.md` |
| Active StrategyGroups have multi-symbol scopes and side-specific event specs | `docs/current/PRE_TRADE_RUNTIME_CONTRACT.md`, `docs/current/strategy-group-handoffs/STRATEGYGROUP_REGISTRY_CONTRACT.md` |
| PG table design includes live signals, promotion candidates, action-time lanes, tickets, budget reservations, protection refs, and runtime safety snapshots | `docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md` |
| Current tests already include a multi-candidate arbitration case where MPG wins over SOR | `tests/unit/test_pg_promotion_action_time_lane_materialization.py` |

## Core Invariants

| Invariant | Meaning |
| --- | --- |
| **Observation can be wide** | Many StrategyGroup + symbol + side + event scopes may be watched |
| **Promotion can be multiple** | Several fresh satisfied events may become promotion candidates |
| **Real-submit lane is single** | At most one `lane_scope=real_submit_candidate` is open |
| **Ticket is unique** | FinalGate checks one exact Action-Time Ticket |
| **Submit intent is single** | Operation Layer receives one `ticket_id + finalgate_pass_id` pair |
| **No unsupported mirroring** | Long/short exists only when the strategy has side-specific event specs |
| **No file authority** | JSON/MD exports never select the winner |

## Target Flow

```text
PG event/scope/policy
-> watcher runtime coverage
-> event-specific fact snapshots
-> live_signal_events
-> promotion_candidates
-> PG arbitration
-> one action_time_lane_input
-> budget reservation
-> protection reference
-> Action-Time Ticket
-> FinalGate ticket check
-> Operation Layer ticket handoff
-> protected submit attempt
-> post-submit closure
```

## Data Model Strengthening

### Arbitration Policy

The system should add or formalize a PG-backed arbitration policy object.

| Field | Meaning |
| --- | --- |
| `arbitration_policy_id` | Stable policy ID |
| `policy_version` | Versioned policy |
| `strategy_priority_order` | Ordered StrategyGroup priority |
| `freshness_weight` | Ranking weight or comparator for signal age |
| `signal_quality_weight` | Ranking weight or comparator for signal quality |
| `budget_fit_rule` | How candidate notional/leverage fits available budget |
| `conflict_policy` | Rules for same symbol, opposite side, or active exposure |
| `tie_breaker` | Deterministic final tie-breaker, for example event time then stable ID |
| `created_at_ms` | Version time |

### Promotion Candidate Additions

| Field | Reason |
| --- | --- |
| `event_spec_id` | Prevent generic signals |
| `event_time_ms` | Rank and freshness |
| `signal_quality_score` | Deterministic quality input |
| `conflict_group_key` | Same symbol/opposite side conflict grouping |
| `arbitration_policy_id` | Proves which policy selected or rejected it |
| `arbitration_reason` | Explains won/lost/blocked in plain language |

### Action-Time Lane Additions

| Field | Reason |
| --- | --- |
| `arbitration_winner_id` | Proves the lane came from winner |
| `arbitration_run_id` | Links all competing candidates |
| `lane_conflict_key` | Prevents duplicate lanes for same exposure |
| `single_lane_lock_ref` | Prevents concurrent worker races |

## Arbitration Rules

### Elimination Phase

Candidates are removed before ranking when any of these is true.

| Order | Elimination reason | Plain explanation |
| --- | --- | --- |
| 1 | Unsupported StrategyGroup/symbol/side/event | 这个机会不在允许范围内 |
| 2 | No PG runtime coverage | 服务器没有实际监控这条精确链路 |
| 3 | Stale or invalid signal | 信号过期或不是当前市场事件 |
| 4 | RequiredFacts not satisfied | 市场事实没有满足策略条件 |
| 5 | Missing Owner policy or runtime scope | 授权/运行配置没有覆盖 |
| 6 | Missing budget reservation capability | 预算不能为这笔候选交易预留 |
| 7 | Missing protection reference | 没有可验证的保护/止损依据 |
| 8 | Active position/open-order conflict | 已有持仓或挂单冲突 |
| 9 | Hard safety stop | 安全边界禁止推进 |

### Ranking Phase

Only candidates that survive elimination are ranked.

| Rank input | Meaning | Rule |
| --- | --- | --- |
| `live_submit_scope` | Whether candidate may become real-submit lane | Real-submit eligible beats rehearsal-only |
| `strategy_priority` | Owner/system priority order | Configured PG policy |
| `signal_freshness` | More recent valid event | Freshest within window wins when priority permits |
| `signal_quality` | Event-specific quality facts | Used for tie/rank, not as hidden strategy optimization |
| `budget_fit` | Candidate can fit reserved budget cleanly | Better fit wins over partial/blocked fit |
| `conflict_status` | Active exposure or opposite-side conflict | Conflicted candidate loses or blocks |
| `deterministic_id` | Stable tie-breaker | Prevents non-deterministic winner |

## Conflict Rules

| Scenario | Required behavior |
| --- | --- |
| Same StrategyGroup, same symbol, same side, same event time | Treat as duplicate and keep one deterministic signal |
| Same StrategyGroup, same symbol, opposite side | Reject both or select one only if event specs define supersession; never create two real-submit lanes |
| Different StrategyGroups, same symbol, same side | Arbitration may choose one; losing candidate stays `arbitration_lost` |
| Different StrategyGroups, same symbol, opposite side | Active exposure conflict rules decide; no dual submit |
| Existing active position/open order | Candidate may remain for review, but cannot create real-submit ticket |
| Rehearsal-only candidate versus real-submit candidate | Rehearsal cannot block valid real-submit winner |

## Example Scenarios

### CPM ETH Long And MPG SOL Long Both Signal

| Step | Expected result |
| --- | --- |
| Both live signal events are valid | Two promotion candidates exist |
| Both have runtime coverage and facts | Both enter arbitration |
| MPG has higher current priority or fresher/stronger signal | MPG wins |
| CPM loses arbitration | CPM row records `arbitration_lost`, not engineering failure |
| One lane opens | Only MPG creates real-submit lane/ticket path |

### SOR Long And SOR Short Same Session

| Step | Expected result |
| --- | --- |
| Both events appear for same symbol/session | Conflict group catches same-session opposite-side conflict |
| One side supersedes by event spec rule | Winner may proceed |
| No supersession rule exists | Both blocked for conflict / review |
| No dual submit | Only one or none can create ticket |

### BRF2 Short While Existing Long Position Exists

| Step | Expected result |
| --- | --- |
| BRF2 signal validates | Promotion candidate may exist |
| Account facts show active long conflict | Candidate eliminated before real-submit lane |
| Review still records event | Strategy learning can keep the signal |
| No ticket | Active exposure conflict blocks ticket |

### Stale High-Priority Signal Versus Fresh Lower-Priority Signal

| Step | Expected result |
| --- | --- |
| High-priority signal expired | Eliminated before ranking |
| Lower-priority signal fresh and valid | May win |
| Explanation | Not "priority ignored"; stale signal cannot compete |

## Projection Behavior

| Projection | Required display |
| --- | --- |
| Candidate Pool | All promotion candidates and arbitration result |
| Daily Table | Closest candidate and whether the winner is waiting, processing, or blocked |
| Goal Status | Active lane/ticket lineage if one exists |
| Server Monitor | Notify on fresh signal, ticket created, hard safety, or Owner action needed |
| Forensics | Explain winner, losers, and why no trade happened |

Projection layers must not independently rank or create real-submit winners.
They display PG arbitration results.

## Implementation Plan

### Batch A - Arbitration Policy Schema

| Item | Requirement |
| --- | --- |
| Tables | Add/strengthen arbitration policy and arbitration run records |
| Readers | Candidate Pool / lane materializer |
| Tests | Duplicate, stale, unsupported, active-conflict, tie-breaker cases |

### Batch B - Promotion Candidate Ranking

| Item | Requirement |
| --- | --- |
| Inputs | PG live signals, facts, scope, policy, budget/protection readiness |
| Output | `arbitration_pending`, `arbitration_won`, `arbitration_lost`, `blocked` |
| Forbidden | JSON exports, code side fallback, generated time |

### Batch C - Single Lane Lock

| Item | Requirement |
| --- | --- |
| Constraint | One open real-submit lane |
| Race handling | Two workers cannot both create a real-submit lane |
| Tests | Concurrent insert or retry simulation |

### Batch D - Ticket Creation From Winner Only

| Item | Requirement |
| --- | --- |
| Input | `arbitration_won` promotion only |
| Output | Action-Time Ticket with full lineage |
| Tests | `arbitration_lost`, expired, blocked, unsupported candidate cannot create ticket |

## Acceptance Tests

```text
multiple fresh valid candidates create multiple promotion_candidates
only one promotion_candidate becomes arbitration_won
only arbitration_won can create real_submit_candidate lane
only real_submit_candidate lane can create Action-Time Ticket
unsupported side cannot participate in arbitration
stale signal cannot win over fresh valid signal
same symbol opposite side cannot create two real-submit lanes
JSON Candidate Pool export cannot select winner
```

## Chain Position

```text
chain_position: multi_candidate_action_time_evolution
strategy_group_id: active WIP StrategyGroups
symbol: active candidate universe
stage: arbitration_design
first_blocker: multi-fresh-signal arbitration policy is not yet fully first-class and Owner-readable
evidence: current Pre-Trade Runtime Contract and PG table design
next_action: implement PG arbitration policy/run records and winner-only lane/ticket creation tests
stop_condition: multiple valid promotions can coexist, but exactly one real-submit lane and one ticket are created
owner_action_required: no
authority_boundary: arbitration only; no FinalGate bypass, Operation Layer bypass, exchange write, profile mutation, or sizing mutation
```
