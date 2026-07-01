---
title: WIP_AND_STOP_RULE_CONTRACT
status: CURRENT
authority: docs/current/WIP_AND_STOP_RULE_CONTRACT.md
last_verified: 2026-07-01
---

# WIP And Stop Rule Contract

## Purpose

This contract limits active live-enablement work so the project stops rewarding
parallel artifact production and starts rewarding blocker removal.

The current management unit is:

```text
StrategyGroup + symbol lane + first blocker + next action
```

## Active WIP Limit

The mainline may carry at most five StrategyGroup lanes:

| Slot | StrategyGroup | Current role |
| --- | --- | --- |
| `P0-A` | `CPM-RO-001` | Replay/live parity and computed-fact blocker reclassification |
| `P0-B` | `MPG-001` | First selected allocated-subaccount live-order and action-time boundary lane |
| `P1-A` | `MI-001` | Trial admission integration and Tradeability Decision closure |
| `P1-B` | `SOR-001` | Armed observation and expanded-symbol action-time reproduction |
| `P2-A` | `BRF2-001` | Short-side armed observation only while disable facts remain decision-relevant |

No new mainline StrategyGroup may be added unless one current lane exits
mainline or the Owner explicitly changes the selected lane set.

## Support-Only StrategyGroups

All non-WIP StrategyGroups are support-only during this phase. They may provide
research context, replay samples, or strategy-review inputs, but they must not
consume mainline planning capacity unless they replace an active WIP lane.

Support-only rows must not be presented as daily mainline progress.

## Stop Rules

Apply these rules every seven calendar days and after any major parity or scope
checkpoint:

| Stop rule | Action |
| --- | --- |
| No blocker moved for seven days | Exit the lane from mainline or replace the next action with a smaller blocker-removal task |
| Artifact produced but next action unchanged | Mark the work `no_progress`; do not count it as completion |
| Replay signal cannot map to live detector after rule/scope review | Do not advance to live-scope proposal; record `replay_live_rule_mismatch` or exit mainline |
| Read-only expansion produces no scoped live proposal or blocker proof | Keep it support-only |
| StrategyGroup cannot name one first blocker | Stop planning work and repair Tradeability Decision classification first |
| Skill output gives broad governance or long-term advice twice in a row | Stop using that prompt shape; rewrite as a chain-position task |
| Owner action is required | Ask only for the scoped policy decision; stop engineering escalation until policy is answered |
| Hard safety is first blocker | Stop live-submit advancement until safety is resolved |

## Seven-Day Review Questions

The seven-day review must answer:

| Question | Required answer |
| --- | --- |
| Which blockers were removed? | List lanes and old/new blocker states |
| Which artifacts changed no decision? | List artifacts and remove them from mainline reporting |
| Which lanes exit mainline? | List StrategyGroup + symbol lanes and reason |
| Which symbols should advance to parity or trial-scope proposal? | List only lanes with evidence |
| Can the project honestly say the market gave no opportunity? | `yes` only when `market_wait_validated` rows pass the checklist |

Do not ask whether the project is more complete, whether documents are cleaner,
or whether artifact volume increased.

## Replacement Rule

A support-only StrategyGroup may replace an active WIP lane only when:

| Requirement | Rule |
| --- | --- |
| First blocker | One blocker class is known |
| Evidence | Replay/live, detector, facts, or scope evidence exists |
| Next action | One engineering action can move the lane |
| Authority boundary | No live profile, sizing, or exchange-write authority is implied |
| Exit target | The lane it replaces is named and exits mainline |

Replacement is a planning decision. It does not authorize real orders.

## Completion Rule

A WIP lane is complete only when it reaches one of:

- `market_wait_validated`;
- `live_submit_ready` after current fresh signal and action-time gates;
- `review_recorded` after a real official action;
- `exit_mainline` under this contract;
- `blocked_owner` for a scoped Owner decision;
- `blocked_safety` for a hard safety stop.

Everything else is intermediate work.
