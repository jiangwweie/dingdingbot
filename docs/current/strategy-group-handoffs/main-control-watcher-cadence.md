# Main-Control Watcher Cadence

Status: CURRENT_PILOT_SUPPLEMENT
Last updated: 2026-06-15

## Cadence

| StrategyGroup | Poll Cadence | Business Signal Validity | Candidate Packet Freshness |
| --- | --- | --- | --- |
| `MPG-001` | `5-15m` | `15-30m` | `120s` |
| `TEQ-001` | `5-15m` | `15-30m` | `120s` |
| `FBS-001` | `5-15m` | `15-30m` | `120s` |
| `SOR-001` | `5m near session; 15-60m outside` | `5-15m near trigger` | `120s` |
| `PMR-001` | `15-60m` | `30-60m` | `120s` |

**Candidate Packet Freshness note:** The `120s` value is watcher-side packet
freshness metadata in the current baseline. It is not currently a runtime
numeric stale-fact enforcement gate. Runtime stale detection relies on upstream
freshness status enums, not numeric window comparison.

## Pilot Confidence Floor

The current pilot `confidence_min` floor is `0.58`. This is a candidate
preparation floor, not execution authority. It is aligned to the lowest
configured pilot reference evaluator ready-signal confidence so a valid pilot
signal is not blocked by a stale research-hand-off threshold before FinalGate
and Operation Layer run.

Execution still requires selected StrategyGroup scope, tiny risk boundary,
RequiredFacts readiness, candidate and authorization evidence, action-time
FinalGate, and the official Operation Layer path.
