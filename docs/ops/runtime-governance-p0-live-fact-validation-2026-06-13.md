# Runtime Governance P0 Live Fact Validation - 2026-06-13

## Validation Scope

This document records a P0-A read-only validation of the current Tokyo runtime
state after the runtime-governance branch reset. It is evidence for operator
visibility and next-attempt gating, not execution authority.

## Sources

| Source | Path or command | Role |
|---|---|---|
| Deployment probe | `scripts/probe_tokyo_runtime_governance_readonly.py` | Current Tokyo deploy, health, migration, mutation safety |
| Account facts | `/home/ubuntu/brc-deploy/reports/rtf052-action-time-bridge/20260613Trtf052-ef89f43d/account-facts-readonly.json` | Read-only account fact coverage |
| Live monitor | `/home/ubuntu/brc-deploy/reports/brc-runtime-governance-b1009096-20260613Trtf099-refresh-flow/rtf099-live-refresh-probe/bnb-live-position-monitor.json` | Position, open order, protection, budget |
| Lifecycle readiness | `/home/ubuntu/brc-deploy/reports/brc-runtime-governance-b1009096-20260613Trtf099-refresh-flow/rtf099-live-refresh-probe/bnb-position-lifecycle-exit-readiness.json` | Position lifecycle and owner-close readiness |
| Continuation refresh | `/home/ubuntu/brc-deploy/reports/brc-runtime-governance-b1009096-20260613Trtf099-refresh-flow/rtf099-live-refresh-probe/live-continuation-refresh-flow.json` | Next continuation routing |
| Continuation selector | `/home/ubuntu/brc-deploy/reports/brc-runtime-governance-b1009096-20260613Trtf099-refresh-flow/rtf099-live-refresh-probe/live-continuation-selector.json` | Operator continuation selection |
| Local packet builder | `scripts/build_runtime_operator_live_fact_packet.py` | Consolidated P0-A operator packet |

## Deployment Facts

| Fact | Value |
|---|---|
| Current Tokyo head | `80da4d670a31ca313ef667d97460d7b6c806c085` |
| Current release realpath | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-80da4d67-20260613Trtf107-cleanup-policy` |
| Migration count | `84` |
| Latest migration | `2026-06-11-084_create_runtime_post_submit_budget_settlements.py` |
| Health status | `ok` |
| Health service | `brc_operator_console` |
| Runtime bound | `true` |
| Live ready | `false` |
| Probe status | `ready_for_controlled_deploy_preflight` |

The first probe attempt used short SHA `80da4d67` as the expected head and
returned a mismatch against the full deployed SHA. The repeated probe using
`80da4d670a31ca313ef667d97460d7b6c806c085` passed.

## Deployment Probe Safety

| Safety invariant | Value |
|---|---:|
| `env_files_read` | `false` |
| `exchange_called` | `false` |
| `execution_intent_created` | `false` |
| `migrations_run` | `false` |
| `order_created` | `false` |
| `order_lifecycle_called` | `false` |
| `remote_files_modified` | `false` |
| `secrets_read` | `false` |
| `services_restarted` | `false` |

## Current Live Runtime Facts

| Fact | Value |
|---|---|
| Runtime instance | `strategy-runtime-e6138ad7c88f` |
| Symbol | `BNB/USDT:USDT` |
| Side | `long` |
| Active position present | `true` |
| Local active position count | `1` |
| Exchange active position count | `1` |
| Current quantity | `0.01` |
| Mark price | `605.45` |
| Local open order count | `1` |
| Exchange open stop order count | `1` |
| Protection status | `hard_stop_only` |
| SL protection present | `true` |
| TP protection present | `false` |
| Hard-stop boundary present | `true` |
| Can continue holding | `true` |
| Attempts remaining | `2` |
| Budget remaining | `8.76158266` |
| Budget reserved | `0.23841734` |

## Current Gate State

| Item | Value |
|---|---|
| Operator packet status | `waiting_for_position_resolution` |
| Missing required fact groups | `[]` |
| Executable submit allowed by packet | `false` |
| Legacy authorization replay allowed | `false` |
| Requires fresh strategy signal | `true` |
| Requires fresh authorization before submit | `true` |
| Operator next step | `continue_read_only_position_monitoring_until_flat_or_reviewed` |

## Current Blockers And Warnings

| Type | Values |
|---|---|
| Blockers | `next_attempt_gate_blocked`, `runtime_max_active_positions_in_use`, `strategy-runtime-e6138ad7c88f:next_attempt_gate_blocked`, two other runtimes waiting on strategy signal |
| Warnings | `current_position_or_protection_open_no_next_attempt`, `missing_tp_protection_right_tail_exit_not_mounted`, `reconciliation_warning_present`, `tp1_partial_quantity_below_min_qty_or_step` |

## Packet Safety

| Safety invariant | Value |
|---|---:|
| `packet_only` | `true` |
| `reads_json_reports_only` | `true` |
| `pg_called_by_builder` | `false` |
| `exchange_called_by_builder` | `false` |
| `exchange_write_called_by_builder` | `false` |
| `order_lifecycle_called_by_builder` | `false` |
| `runtime_state_mutated_by_builder` | `false` |
| `withdrawal_or_transfer_created_by_builder` | `false` |
| `no_forbidden_live_side_effects` | `true` |

## Operator Conclusion

The current runtime is not ready for a fresh attempt because the BNB position is
still active and the runtime active-position slot is in use. The correct P0-A
state is `waiting_for_position_resolution`.

The next fresh attempt must wait for a flat/resolved runtime state or a separate
Owner-authorized reduce-only close path. This packet does not authorize a close,
new entry, exchange submit, withdrawal, transfer, or runtime budget mutation.
