# Strategy Candidate Mining + Replay Validation

- **Task**: `STRATEGY-CANDIDATE-MINING-REPLAY-VALIDATION-001`
- **Status**: `strategy_candidate_mining_replay_validation_ready_research_only`
- **Generated CST**: `2026-06-30 08:00`
- **Symbols**: `7`
- **Candidates**: `13`
- **Main-control handoff candidates**: `4`
- **Watcher scope candidates**: `0`

## Candidate Ranking

| Rank | Candidate | Status | 30d unique | 30d sum | Median | P75 | P90 | DD |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | `CPM-SOL-SHORT-001` | `main_control_handoff_candidate` | 39 | 24.0316 | 0.3829 | 1.8755 | 3.2926 | -3.0481 |
| 2 | `BRF2-QUALITY-BASKET-SHORT-001` | `main_control_handoff_candidate` | 81 | 58.1762 | 0.6709 | 1.8534 | 3.271 | -9.6442 |
| 3 | `MPG-SOL-HIGH-BETA-LONG-001` | `main_control_handoff_candidate` | 13 | 5.5568 | 0.523 | 1.3074 | 3.1371 | -2.9955 |
| 4 | `MI-ASIA-RS-IMPULSE-001` | `main_control_handoff_candidate` | 8 | 5.0551 | 0.5283 | 0.9463 | 2.3911 | -3.0545 |
| 5 | `RBR2-RANGE-REVERSION-SHORT-001` | `role_candidate` | 68 | -23.0595 | -0.5058 | -0.0486 | 0.5918 | -23.5644 |
| 6 | `BRF2-WEAK-MARKET-SHORT-001` | `classifier_candidate` | 146 | 45.7908 | 0.002 | 1.4796 | 3.0857 | -23.7962 |
| 7 | `CPM-ASIA-SHORT-001` | `park` | 94 | 41.7353 | 0.313 | 1.8503 | 3.2926 | -16.1287 |
| 8 | `MI-RS-IMPULSE-001` | `park` | 49 | -1.4139 | -0.3017 | 0.8202 | 3.2848 | -15.8802 |
| 9 | `CPM-MULTI-SHORT-001` | `park` | 274 | -4.5281 | -0.2681 | 0.9683 | 2.6273 | -58.902 |
| 10 | `EARLY-RECLAIM-LONG-001` | `park` | 223 | -106.0577 | -0.7225 | 0.5204 | 2.0104 | -111.5925 |
| 11 | `MPG-HIGH-BETA-LONG-001` | `park` | 45 | -30.1378 | -0.7853 | 0.7618 | 1.7024 | -32.8501 |
| 12 | `CPM-MULTI-LONG-001` | `park` | 103 | -40.8444 | -0.4325 | 0.176 | 1.165 | -46.5169 |
| 13 | `SOR-MULTI-SESSION-BREAKOUT-001` | `park` | 38 | -18.6169 | -0.3429 | 0.2088 | 0.871 | -22.8296 |

## Direction Summary

| Candidate | Family | Side | Symbols | Absorbability |
| --- | --- | --- | ---: | --- |
| `CPM-SOL-SHORT-001` | `cpm_multi_symbol_pullback_continuation_filtered` | `short` | 1 | Draft handoff pack generated; suitable for Tradeability Decision intake, not live authority. |
| `BRF2-QUALITY-BASKET-SHORT-001` | `bear_rebound_failure_short_filtered` | `short` | 5 | Draft handoff pack generated; suitable for Tradeability Decision intake, not live authority. |
| `MPG-SOL-HIGH-BETA-LONG-001` | `mpg_high_elasticity_expansion_filtered` | `long` | 1 | Draft handoff pack generated; suitable for Tradeability Decision intake, not live authority. |
| `MI-ASIA-RS-IMPULSE-001` | `relative_strength_impulse_filtered` | `long` | 4 | Draft handoff pack generated; suitable for Tradeability Decision intake, not live authority. |
| `RBR2-RANGE-REVERSION-SHORT-001` | `range_mean_reversion` | `short` | 7 | Keep as portfolio role candidate / classifier input. |
| `BRF2-WEAK-MARKET-SHORT-001` | `bear_rebound_failure_short` | `short` | 7 | Absorb as disable/weak-market classifier evidence. |
| `CPM-ASIA-SHORT-001` | `cpm_multi_symbol_pullback_continuation_filtered` | `short` | 7 | Park until new market window or rule revision. |
| `MI-RS-IMPULSE-001` | `relative_strength_impulse` | `long` | 5 | Park until new market window or rule revision. |
| `CPM-MULTI-SHORT-001` | `cpm_multi_symbol_pullback_continuation` | `short` | 7 | Park until new market window or rule revision. |
| `EARLY-RECLAIM-LONG-001` | `early_reclaim_long` | `long` | 7 | Park until new market window or rule revision. |
| `MPG-HIGH-BETA-LONG-001` | `mpg_high_elasticity_expansion` | `long` | 4 | Park until new market window or rule revision. |
| `CPM-MULTI-LONG-001` | `cpm_multi_symbol_pullback_continuation` | `long` | 6 | Park until new market window or rule revision. |
| `SOR-MULTI-SESSION-BREAKOUT-001` | `session_opening_range_breakout` | `long` | 4 | Park until new market window or rule revision. |

## Main-Control Handoff Candidates

- **CPM-SOL-SHORT-001**: 30d and 14d execution-shaped replay show positive center or right-tail with bounded drawdown.
- **BRF2-QUALITY-BASKET-SHORT-001**: 30d and 14d execution-shaped replay show positive center or right-tail with bounded drawdown.
- **MPG-SOL-HIGH-BETA-LONG-001**: 30d and 14d execution-shaped replay show positive center or right-tail with bounded drawdown.
- **MI-ASIA-RS-IMPULSE-001**: 30d and 14d execution-shaped replay show positive center or right-tail with bounded drawdown.

## Watcher Scope Candidates

- None in this run.

## Park / Kill / Role / Classifier

- **RBR2-RANGE-REVERSION-SHORT-001** `role_candidate`: Mean-reversion role can diversify trend strategies, but independent return quality is insufficient.
- **BRF2-WEAK-MARKET-SHORT-001** `classifier_candidate`: Weak-market short evidence is better used as squeeze/failed-rebound classifier unless replay improves.
- **CPM-ASIA-SHORT-001** `park`: Replay evidence is mixed and not strong enough for current intake.
- **MI-RS-IMPULSE-001** `park`: Replay evidence is mixed and not strong enough for current intake.
- **CPM-MULTI-SHORT-001** `park`: Replay evidence is mixed and not strong enough for current intake.
- **EARLY-RECLAIM-LONG-001** `park`: Replay evidence is mixed and not strong enough for current intake.
- **MPG-HIGH-BETA-LONG-001** `park`: Replay evidence is mixed and not strong enough for current intake.
- **CPM-MULTI-LONG-001** `park`: Replay evidence is mixed and not strong enough for current intake.
- **SOR-MULTI-SESSION-BREAKOUT-001** `park`: Replay evidence is mixed and not strong enough for current intake.

## Safety Boundary

```json
{
  "actionable_now": false,
  "exchange_write": false,
  "execution_authority": false,
  "finalgate_input": false,
  "live_profile_change": false,
  "operation_layer_input": false,
  "order_created": false,
  "real_order_authority": false,
  "research_only": true,
  "tier_policy_change": false
}
```
