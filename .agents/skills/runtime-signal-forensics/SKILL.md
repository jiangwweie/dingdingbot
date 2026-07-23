---
name: runtime-signal-forensics
description: Use when explaining recent signals, missed trades, no-trade periods, Ticket progress, runtime blockers, protected positions, reconciliation, or Owner notifications from production evidence.
user-invocable: true
---

# Runtime Signal Forensics

## Required Authority

Read before collecting evidence:

- `AGENTS.md`
- `docs/current/PROJECT_INFORMATION_ARCHITECTURE.md`
- `docs/current/BLOCKER_CLASSIFICATION_CONTRACT.md`
- `docs/current/TRADEABILITY_DECISION_CONTRACT.md`
- `.agents/skills/chain-position/SKILL.md`

Convert relative dates to an absolute window with an explicit timezone.

## Safety Boundary

This workflow is read-only. Do not deploy, restart services, change policy,
mutate PostgreSQL, dispatch commands, or call exchange-write endpoints. Mask
credentials and connection values.

## Evidence Priority

1. Tokyo PostgreSQL current rows and append-only lineage.
2. Exchange readonly account, position, order, and fill truth.
3. Journals for the four persistent workers.
4. Deployed release and schema identity.
5. Current contracts for interpretation only.

Generated JSON, Markdown, caches, archived databases, and old reports cannot
prove current runtime truth. If current PG or exchange facts are unavailable,
report `runtime_data_gap` rather than reconstructing an answer from files.

## Authoritative Chain

```text
Observation
-> StrategySignal
-> Readiness/Authority
-> CapacityClaim
-> immutable Ticket
-> durable Exchange Command
-> protected lifecycle
-> reconciliation
-> settlement
-> review
```

Follow exact identities forward until the first absent, rejected, stale,
occupied, or unresolved transition.

## Bounded Collection

Prefer the committed readonly certification command for identity, table,
capability, active Ticket, command, position, Incident, and Owner projection
summary:

```text
scripts/trading_kernel/certify_readonly.py
```

For a bounded time window or exact identity, query only the relevant current
and lineage tables:

| Question | Primary tables |
| --- | --- |
| What was observed? | `brc_facts_current`, `brc_signal_events`, `brc_signal_fact_snapshots` |
| Why did it not advance? | `brc_readiness_current`, `brc_runtime_scopes_current`, `brc_owner_policy_current` |
| Was capital/action authority built? | `brc_capacity_claims`, `brc_entry_lane_current`, `brc_budget_reservations` |
| Was a trade episode created? | `brc_trade_tickets`, `brc_trade_aggregates`, `brc_trade_events` |
| Was an exchange effect attempted? | `brc_exchange_commands` plus exchange readonly order truth |
| Is exposure protected? | `brc_positions_current`, Ticket aggregate/events, exact exchange protection orders |
| Is recovery blocked? | `brc_runtime_incidents`, unresolved Exchange Commands, Reconciliation events |
| Is closure complete? | terminal Ticket/aggregate, released budget/domain, `brc_trade_reviews` |
| What does the Owner surface say? | `brc_monitor_current`, `brc_monitor_events` |

Use exact IDs and bounded `occurred_at_ms`, `observed_at_ms`, or update windows.
Do not scan full history during routine diagnosis.

Inspect systemd only for these persistent services when process evidence is
needed:

```text
brc-trading-kernel-observation-worker.service
brc-trading-kernel-entry-worker.service
brc-trading-kernel-lifecycle-worker.service
brc-trading-kernel-reconciliation-worker.service
```

An idle worker is healthy when its process remains resident, polls within its
bounded cadence, and journals `no_work` without repeated process creation or
file output.

## Recursive First-Blocker Rule

Do not stop at “no Ticket”, “no order”, or “waiting”. Ask why the immediately
previous authoritative object did not create the next one until one class is
proven:

| Terminal class | Meaning |
| --- | --- |
| `objective_market_condition_not_satisfied` | Observation was healthy and exact Event facts were false |
| `engineering_handoff_gap` | Valid upstream object existed but the next kernel object was not materialized |
| `scope_or_policy_gap` | Strategy, instrument, side, account, profile, or capital policy did not authorize progress |
| `runtime_safety_or_reconciliation_gap` | Lane, domain, protection, command outcome, position, order, or Incident blocked progress |
| `current_projection_gap` | Current rows cannot prove a consistent chain |

`waiting_for_opportunity` is allowed only after every non-market prerequisite
in `BLOCKER_CLASSIFICATION_CONTRACT.md` is current and true.

## Interpretation Rules

- A StrategySignal is observation, not capital or order authority.
- A CapacityClaim is action-time authority, not proof that a Ticket committed.
- A Ticket without an accepted ENTRY is not exposure.
- An accepted ENTRY without accepted Initial Stop is an urgent protection state.
- `position_protected` is an active lifecycle state, not completion.
- A busy ENTRY lane or deterministic arbitration loss is normal serialization.
- Authoritative rejection is terminal; unknown outcome requires reconciliation.
- Notification absence does not prove Signal absence. Compare
  `brc_monitor_current` and `brc_monitor_events` with newer chain events.

## Required Report

```text
## 结论
## 已知客观事实
## 链路位置
## 第一阻塞点
## 市场条件与系统阻塞的区分
## Ticket / Command / Position 状态
## 通知状态
## Owner 是否需要介入
## 证据边界
```

When comparing three or more Events or Tickets, use a table containing Event,
instrument, side, last proven stage, first blocker, exact identity, and Owner
action.

## Required Checks

- Time window and timezone are explicit.
- Observation coverage is proven before claiming no opportunity.
- Signal, Claim, Ticket, Command, position, Incident, Review, and monitor times
  are compared in causal order.
- PostgreSQL and exchange truth agree, or the mismatch is the stated blocker.
- The answer cites exact IDs without exposing secrets.
- The answer states whether Owner action is required.

## Hard Stops

Stop with uncertainty when the requested window lacks current PG lineage,
exchange facts needed for the claim are unavailable, or current rows contradict
each other without an authoritative resolution. Do not fill evidence gaps with
market guesses.
