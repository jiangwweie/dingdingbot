# Main-Control Watcher Cadence

Status: HANDOFF_SUPPLEMENT_READY
Last updated: 2026-06-14

## Purpose

This document gives watcher cadence recommendations for the first
StrategyGroup handoff batch.

The recommendations are business cadence and signal-validity guidance for
main-control. They do not implement watcher scheduling and do not authorize
execution.

## Freshness Levels

The handoff JSON files use:

```text
freshness_window_seconds: 120
```

That value means action-time packet freshness for candidate preparation. It is
not the full business observation interval.

Main-control can separate:

| Freshness Layer | Meaning |
| --- | --- |
| `watcher_poll_cadence` | How often main-control checks whether the strategy group has a new state. |
| `business_signal_validity` | How long a closed-candle signal remains reviewable before refresh. |
| `candidate_prepare_packet_freshness` | Short action-time window before preparing a candidate packet; current handoff default is `120` seconds. |

## Recommended Cadence

| Strategy Group | Watcher Poll Cadence | Business Signal Validity | Candidate Packet Freshness | Stale Behavior |
| --- | ---: | ---: | ---: | --- |
| `MPG-001` | `5-15m` | `15-30m` | `120s` | Emit no candidate; require refresh. |
| `FBS-001` | `5-15m` | `15-30m` | `120s` | Require funding/mark refresh before armed candidate. |
| `TEQ-001` | `5-15m` | `15-30m` | `120s` | Emit no candidate; require session/product facts refresh. |
| `PMR-001` | `15-60m` | `30-60m` | `120s` | Remain observe-only unless role/session/mark facts refresh. |
| `SOR-001` | `5m near session window; 15-60m outside` | `5-15m near trigger` | `120s` | Block if session window or trigger is stale. |

## Strategy-Specific Notes

### `MPG-001`

Use a normal 1h-candle watcher cadence. More frequent checks are useful only
around newly closed candles or when multiple MPG member states compete.

Recommended scope:

```text
poll: every 5-15m
on_new_closed_1h_candle: evaluate immediately
stale_after_business_window: no candidate
```

### `FBS-001`

Use a normal 1h watcher plus derivatives facts refresh. Funding, mark, and
crowding facts must be fresher than the signal decision.

Recommended scope:

```text
poll: every 5-15m
required_refresh: funding_rate_window, mark_price_state
stale_after_business_window: require refresh
```

### `TEQ-001`

Use a normal 1h watcher, but keep session/product context visible. The strategy
is concentration-sensitive, so same-symbol duplicate candidate preparation
should remain blocked.

Recommended scope:

```text
poll: every 5-15m
on_new_closed_1h_candle: evaluate immediately
stale_after_business_window: no candidate
```

### `PMR-001`

Use a slower observe-only cadence by default. Increase cadence only when PMR is
explicitly upgraded to armed observation for XAG-led short/weakness branches.

Recommended scope:

```text
poll: every 15-60m
armed_upgrade_poll: every 5-15m during active metal move
stale_after_business_window: observe only
```

### `SOR-001`

Use session-aware polling. The strategy should become more active around the
opening-range construction and trigger window, then downshift outside that
window.

Recommended scope:

```text
pre_session_window: poll every 15m
range_build_and_trigger_window: poll every 5m
outside_session_window: poll every 15-60m or observe only
stale_after_business_window: block candidate preparation
```

## Watcher Output Expectations

| Output | Meaning |
| --- | --- |
| `no_signal` | Strategy was evaluated and no signal exists. |
| `ready_for_shadow_candidate_prepare` | Signal exists and RequiredFacts are sufficiently fresh for candidate preparation review. |
| `stale_signal` | Signal exists but action-time packet freshness or business validity expired. |
| `signal_conflict` | Signal conflicts with account, exchange, facts, side, or another strategy group. |
| `observe_only_state` | Strategy has useful context but should not prepare a candidate. |

## Boundary

Watcher cadence is a strategy-research recommendation. Main-control owns actual
watcher implementation, notification routing, runtime state, candidate
preparation, FinalGate, Operation Layer, budget, settlement, reconciliation,
and review.
