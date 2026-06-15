# Main-Control Admission Priority

Status: CURRENT_PILOT_SUPPLEMENT
Last updated: 2026-06-15

## Purpose

This supplement defines the first StrategyGroup picker order for the main
runtime pilot. It is not runtime registration, order authorization, FinalGate
input, Operation Layer input, a deploy request, a credential change, or an
order-sizing default.

## Admission Order

| Rank | StrategyGroup | Default Mode | Main-Control Meaning |
| ---: | --- | --- | --- |
| 1 | `MPG-001` | `armed_observation` | Default live pilot observation group. |
| 2 | `TEQ-001` | `armed_observation` | Equity-like perpetual momentum observer. |
| 3 | `FBS-001` | `armed_observation` | Funding / basis stress observer with higher fact threshold. |
| 4 | `SOR-001` | `conditional_armed_observation` | Session-window observer. |
| 5 | `PMR-001` | `observe_only` | Metals overlay observer until role/session/mark facts pass. |
