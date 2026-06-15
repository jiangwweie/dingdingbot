# Main-Control RequiredFacts Map

Status: CURRENT_PILOT_SUPPLEMENT
Last updated: 2026-06-15

## Purpose

This supplement maps StrategyGroup handoff facts into main-control readiness
classes. It does not fetch facts, place orders, change risk settings, or bypass
FinalGate.

## Readiness Classes

| Class | Meaning | Missing Behavior |
| --- | --- | --- |
| `market` | Price, closed candles, mark, funding, and volume context. | Block signal or downshift to observe-only. |
| `strategy` | StrategyGroup evaluator state and disable classifiers. | Emit no-signal or conflict. |
| `derivatives` | Funding, basis, crowding, and OI context. | Block FBS candidate prepare; may allow observe-only. |
| `risk` | Protection, exit, mark/fill, and leverage boundary. | Block candidate prepare. |
| `account` | Balance, same-symbol position, and open orders. | Block candidate prepare. |
| `exchange` | Symbol availability, min notional, step, tick, leverage limit. | Block candidate prepare for the affected symbol. |
