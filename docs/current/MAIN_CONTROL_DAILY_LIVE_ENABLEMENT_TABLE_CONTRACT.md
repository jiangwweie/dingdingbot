---
title: MAIN_CONTROL_DAILY_LIVE_ENABLEMENT_TABLE_CONTRACT
status: CURRENT
authority: docs/current/MAIN_CONTROL_DAILY_LIVE_ENABLEMENT_TABLE_CONTRACT.md
last_verified: 2026-07-01
---

# Main Control Daily Live Enablement Table Contract

## Purpose

This contract defines the daily management summary for the live-enablement
phase. It summarizes the Pre-Trade Runtime defined by
`docs/current/PRE_TRADE_RUNTIME_CONTRACT.md`.

The table exists to answer one management question:

```text
Which active StrategyGroup candidate symbols are closest to promotion or action-time?
```

It replaces broad daily narratives, artifact tours, portfolio-board reading, and
manual Owner interpretation of raw runtime reports. Supporting artifacts remain
available, but the daily management surface is this table.

## Daily Questions

Every daily status pass must answer exactly these five questions before adding
any supporting detail:

| Question | Required answer shape |
| --- | --- |
| Did the live-submit scope have a fresh eligible signal today? | `yes`, `no`, or `unknown_with_reason` |
| If no trade happened, what was the first blocker? | One blocker class from `BLOCKER_CLASSIFICATION_CONTRACT.md` |
| Did the top replay/missed events reproduce in the live detector? | `matched`, `not_matched`, `not_tested`, or concrete mismatch |
| Which StrategyGroup candidate symbol is closest to promotion or action-time? | One row, or `none_with_reason` |
| What one engineering action most reduces real-trade distance next? | One action only |

If a report cannot answer these five questions, it is not the main daily status
surface.

## Required Table

The daily table must contain one strategy-level row per active WIP
StrategyGroup. The expanded per-symbol readiness matrix lives in the
PG-backed Candidate Pool read model and may be exported only through an
explicit diagnostic command.

| Field | Meaning |
| --- | --- |
| `strategy_group_id` | StrategyGroup lane, for example `CPM-RO-001` |
| `symbol` | The currently highest-priority candidate symbol summary for the StrategyGroup |
| `side` | Long/short or strategy-specific side |
| `stage` | Current lane stage: `research`, `intake`, `admission`, `readonly`, `armed`, `market_wait_validated`, `action_time`, `live_submit_ready`, `review` |
| `replay_signal` | `yes`, `no`, `not_applicable`, or `unknown_with_reason` |
| `live_detector` | `matched`, `not_matched`, `not_tested`, `computed_not_satisfied`, or concrete detector state |
| `first_blocker` | One blocker class from `BLOCKER_CLASSIFICATION_CONTRACT.md` |
| `first_blocker_evidence` | One concise artifact/code/runtime reference proving the blocker |
| `owner_action_required` | `yes` only for scoped policy, tier, capital/profile/scope, pause/resume, park/kill, production transition, or abnormal intervention |
| `next_engineering_action` | One action that removes or reclassifies the first blocker |
| `stop_condition` | Concrete condition that stops or exits the lane from mainline WIP |

The table must not include raw proof chains, packet names as primary labels,
large nested evidence, or multiple next actions in one row. It also must not be
interpreted as suppressing fresh-signal promotion from a different candidate
symbol in the same active StrategyGroup.

## Active WIP Rows

The daily table is currently limited to these mainline StrategyGroups unless the
WIP contract admits a replacement:

| Priority | StrategyGroup | Default reason |
| --- | --- | --- |
| `P0` | `CPM-RO-001` | Detector output exists; replay/live parity blocker classification must be corrected |
| `P0` | `MPG-001` | First selected allocated-subaccount live-order lane and action-time boundary lane |
| `P1` | `MI-001` | Trial admission integration gap can move it toward a real lane decision |
| `P1` | `SOR-001` | Armed observation and expanded-symbol action-time reproduction gap |
| `P2` | `BRF2-001` | Short-side lane remains active only while squeeze-disable state and armed observation are decision-relevant |

Other StrategyGroups may appear only in an appendix or support artifact unless
they replace one of the active WIP rows through the WIP contract. Candidate
symbols inside an active StrategyGroup do not consume new WIP StrategyGroup
slots.

## Valid Status Values

Use these lane status values:

| Status | Meaning |
| --- | --- |
| `advanced` | First blocker was removed, or lane moved to a later stage |
| `reclassified` | Broad blocker became precise per-symbol / per-fact blocker |
| `validated_wait` | `market_wait_validated` checklist passed and fresh signal is absent |
| `blocked_owner` | Owner policy decision is the first blocker |
| `blocked_safety` | Hard safety boundary is the first blocker |
| `no_progress` | No blocker moved; must provide stop-condition review if repeated |
| `exit_mainline` | Lane leaves active WIP under `WIP_AND_STOP_RULE_CONTRACT.md` |

Do not use `ready`, `mostly ready`, `looks good`, or generic `waiting` as the
daily row status.

## Artifact Boundary

Daily table rows may cite generated artifacts, but generated artifacts are not
the management unit. Before action-time, the management unit is:

```text
StrategyGroup + symbol + readiness state + first blocker + evidence + next action + stop condition
```

The table must not create live order authority, FinalGate input, Operation Layer
input, live profile expansion, sizing-default expansion, or exchange write.
