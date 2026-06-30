# 策略机会覆盖诊断

## Owner 摘要

- Status: `mainline_no_signal_low_priority_broader_would_enter`
- Owner state: `waiting_for_opportunity`
- 当前判断：主线暂未触发，宽观察面只有低优先级或已停放机会，继续等待更高质量机会。
- Runtime source status: `runtime_summary_missing`
- Broader source: `local_sqlite_read_only` / `local_sqlite_v3_dev_closed_klines_read_only`
- Mainline ready signals: `0`
- Broader would-enter signals: `1`
- Broader actionable would-enter signals: `0`
- Broader low-priority would-enter signals: `1`
- Broader high-priority no-action signals: `4`
- Coverage gap: `False`

## 判断

- Mainline runtime is waiting: `True`
- Broader observe-only shelf has would-enter signals: `True`
- Broader actionable would-enter exists: `False`
- Broader high-priority no-action review available: `True`
- 宽观察信号只用于机会面诊断，不授权 candidate/auth/FinalGate/Operation Layer。

## 主线未触发原因

| Reason | Count |
| --- | --- |
| none | 0 |

## 宽观察 Would-Enter 信号

| StrategyGroup | Symbol | Side | Confidence | Reason |
| --- | --- | --- | --- | --- |
| `RBR-001` | `ADA/USDT:USDT` | `short` | `0.57` | `rbr_range_context, rbr_boundary_rejection_confirmed` |

## 高优先级 No-Action 信号

| StrategyGroup | Symbol | Side | Confidence | Reason |
| --- | --- | --- | --- | --- |
| `BRF-001` | `BTC/USDT:USDT` | `none` | `0.25` | `brf_no_action_no_rally_extension` |
| `BTPC-001` | `AVAX/USDT:USDT` | `none` | `0.25` | `btpc_disable_stale_signal_before_l2_review` |
| `LSR-001` | `XRP/USDT:USDT` | `none` | `0.25` | `lsr_disable_long_preview_conflicts_with_short_revival_lead` |
| `VCB-001` | `LINK/USDT:USDT` | `none` | `0.25` | `vcb_no_action_volume_expansion_missing` |

## 安全边界

- Server interaction: `false`
- Server files mutated: `false`
- FinalGate called: `false`
- Operation Layer called: `false`
- Exchange write called: `false`
- Order created: `false`

## 下一步

- `continue_mainline_and_keep_low_priority_observation_parked`
