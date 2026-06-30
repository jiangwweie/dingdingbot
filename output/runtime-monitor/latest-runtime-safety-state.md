## P0 Runtime Safety Live Submit Readiness

- Status: `live_submit_standby_waiting_for_market`
- Owner status: `waiting_for_opportunity` / 等待机会
- Pre-live rehearsal ready: `True`
- Live submit ready: `False`
- Owner intervention: `False`
- Real order authority: `false`

## Action-Time RequiredFacts

| Fact | Status | Blocks live submit now | Owner wording |
| --- | --- | --- | --- |
| `trusted_submit_fact_snapshot` | `pending_action_time` | `False` | 等待机会 |
| `account_facts` | `pending_action_time` | `False` | 等待机会 |
| `position_open_order_conflict` | `pending_action_time` | `False` | 等待机会 |
| `budget_coverage` | `pending_action_time` | `False` | 等待机会 |
| `protection_template` | `pending_action_time` | `False` | 等待机会 |
| `submit_idempotency_policy` | `pending_action_time` | `False` | 等待机会 |
| `duplicate_submit_guard` | `pending_action_time` | `False` | 等待机会 |
| `protection_failure_policy` | `pending_action_time` | `False` | 等待机会 |
| `exchange_rules` | `pending_action_time` | `False` | 等待机会 |
| `signal_freshness` | `waiting` | `False` | 等待机会 |

## Operation Layer Boundary

- Input shape ready: `true`
- FinalGate pass required before submit: `true`
- Exchange write authority gated: `true`
- Operation Layer called: `false`
