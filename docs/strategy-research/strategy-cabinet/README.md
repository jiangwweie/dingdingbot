# Strategy Cabinet

Status: ACTIVE_STRATEGY_CABINET_README
Last updated: 2026-06-16

## Purpose

The Strategy Cabinet is the lightweight semantic registry for the strategy
research line.

It answers:

1. Which strategy semantics exist?
2. Which ones are active, handoff-ready, observe-only, parked, or blocked?
3. Where is the evidence?
4. Where is the main-control handoff, if one exists?
5. What facts or conditions are required before the candidate can move forward?

## Non-Goals

The Strategy Cabinet is not:

1. A runtime registry.
2. A Strategy Picker implementation.
3. A return leaderboard.
4. An execution authorization source.
5. A FinalGate input.
6. An Operation Layer input.
7. A live-profile or order-sizing configuration.

## Files

| File | Role |
| --- | --- |
| `strategy-cabinet.md` | Human-readable strategy semantic registry. |
| `strategy-cabinet.json` | System-readable strategy semantic registry. |

## Update Rule

Update the cabinet whenever a strategy:

1. Enters the research pool.
2. Gets a candidate packet.
3. Gets a StrategyGroup handoff pack.
4. Is downgraded, parked, killed, or revived.
5. Changes RequiredFacts, blocker, leverage boundary, or main-control status.

Keep raw replay data, large CSVs, and detailed experiment outputs in their
existing research directories. The cabinet should link to summaries and packs,
not duplicate raw evidence.
