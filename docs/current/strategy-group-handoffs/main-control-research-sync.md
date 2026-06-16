# Main-Control Research Sync

Status: CURRENT_PILOT_SUPPLEMENT
Last updated: 2026-06-15

## Purpose

This file records the StrategyGroup research handoff that has been reviewed and
synced to the current main-control baseline.

## Source

| Field | Value |
| --- | --- |
| Source worktree | `/Users/jiangwei/Documents/final-strategy-research` |
| Source branch | `codex/strategy-research-20260613-goal` |
| Source commit | `d62ce55727614fcfdb2d12f8fee1d3c226950048` |
| Handoff validator | `pass` |
| Unit test | `pass` |
| Raw research artifacts | Local backed-up, not integrated |

## Main-Control Interpretation

The synced research handoff is accepted as input for the current StrategyGroup
runtime pilot, but it is not a direct runtime expansion.

Current runtime-facing authority remains:

```text
docs/current/strategy-group-handoffs/
```

Detailed research material under `docs/strategy-research/` remains research
provenance unless it is explicitly distilled into `docs/current/`.

## Boundary

The research handoff may inform:

- Strategy Picker options;
- watcher scope;
- RequiredFacts readiness mapping;
- strategy conflict and cadence policy;
- review outcomes such as `promote`, `keep_observing`, `revise`, `park`, or
  `kill`.

The research handoff does not authorize:

- FinalGate bypass;
- Operation Layer bypass;
- exchange submit actions;
- credential or live-profile changes;
- order-sizing default expansion;
- automatic admission of every broader research symbol.

