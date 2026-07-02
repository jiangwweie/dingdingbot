---
name: chain-position
description: Use for live-enablement chain-position work in /Users/jiangwei/Documents/final: replay-live parity, first blocker classification, symbol scope decision, action-time boundary, or daily live-enablement status. This skill must be used whenever a task asks what to do next for real trading progress, why no trade happened, whether a StrategyGroup or symbol should advance, or whether replay/live detector/scope/facts/action-time blockers moved.
user-invocable: true
---

# Chain Position Live Enablement

## Read First

- `AGENTS.md`
- `CLAUDE.md`
- `docs/current/BLOCKER_CLASSIFICATION_CONTRACT.md`
- `docs/current/MAIN_CONTROL_DAILY_LIVE_ENABLEMENT_TABLE_CONTRACT.md`
- `docs/current/WIP_AND_STOP_RULE_CONTRACT.md`
- `docs/current/TRADEABILITY_DECISION_CONTRACT.md`
- `docs/current/MAIN_CONTROL_ROADMAP.md`

## Role

This skill constrains work by trading-chain position, not by expert domain.

Allowed chain positions:

| Chain position | Only question it answers |
| --- | --- |
| `replay_live_parity` | Did replay-observed signal reproduce in live/current detector under the same symbol, timeframe, venue, and fact rules? |
| `pretrade_candidate_readiness` | What is the current readiness and first blocker for this StrategyGroup + candidate symbol? |
| `tradeability_first_blocker` | What is the current first blocker for this StrategyGroup or candidate symbol? |
| `symbol_scope_decision` | Should a symbol move from observed/read-only to scoped promotion or explicit deferral? |
| `fresh_signal_promotion` | Can a fresh satisfied candidate become a promotion candidate or action-time lane input? |
| `action_time_boundary` | If a fresh live signal appears, can one narrowed lane reach candidate/auth, FinalGate, and Operation Layer without manual operation? |
| `daily_live_enablement_status` | Which active StrategyGroup/candidate symbol moved closer to promotion or live submit today, and what is the next single action? |

Do not answer broad strategy, architecture, governance, or documentation
questions inside this skill. Route those only after the chain-position output
proves they are the first blocker.

## Required Output

Every output must fit this shape:

```text
chain_position:
strategy_group_id:
symbol:
stage:
first_blocker:
evidence:
next_action:
stop_condition:
owner_action_required:
authority_boundary:
```

No long narrative, no broad roadmap, no new artifact proposal unless the
artifact removes/reclassifies the first blocker and is consumed by the standard
monitor path.

## Forbidden Outputs

Do not output:

- long-term governance suggestions;
- generic project summaries;
- new packet/projection/readiness layers;
- multiple next actions for one lane;
- `waiting_for_market` unless `market_wait_validated` checklist is proven;
- live profile expansion;
- order-sizing expansion;
- FinalGate bypass;
- Operation Layer bypass;
- exchange-write authority from replay, synthetic, read-only, or audit evidence.

## WIP Discipline

Use `docs/current/WIP_AND_STOP_RULE_CONTRACT.md`.

The active mainline lanes are limited to:

- `CPM-RO-001`;
- `MPG-001`;
- `MI-001`;
- `SOR-001`;
- `BRF2-001`.

Any other StrategyGroup is support-only unless the output explicitly exits an
active lane and admits a replacement under the WIP contract.

## Acceptance

A chain-position task is accepted only when it:

- names one chain position;
- names one StrategyGroup + symbol candidate when symbol-specific;
- names one first blocker;
- provides one evidence reference;
- provides one next engineering or policy action;
- states a stop condition;
- preserves the authority boundary.
