# MI-001 BNB Trial Readiness Gap Matrix

Generated: 2026-05-31

Scope: `MI-001-BNB-LONG`, `BNB/USDT:USDT`, long.

This matrix is a review artifact. It is not trial start, testnet rehearsal start, execution intent, order permission, runtime start, or live authorization.

| gate_id | gate_name | current_status | required_for_testnet_rehearsal | required_for_small_live_trial | existing_source_or_code_path | gap | recommended_action | risk_if_skipped | owner_decision_required |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| G01 | Account facts | partially_available_needs_bnb_refresh | yes | yes | `src/application/trial_readiness_account_facts.py`; `live_account_facts_readiness_result.md` | BNB readiness must refresh account equity and available margin at decision time. | Run read-only Binance USDT futures account facts refresh before any rehearsal packet. | Sizing and max-loss assumptions may be stale. | yes |
| G02 | BNB Operation Layer cap | missing_bnb_specific_cap | yes | yes | `src/application/brc_operation_layer.py` | SOL cap exists from prior readiness work; BNB-specific notional/loss cap is not established. | Create metadata-only BNB Operation Layer cap: symbol BNB, long, max leverage 5x, no expansion rules. | Owner could review a signal without a BNB-specific risk ceiling. | yes |
| G03 | GKS | state_must_be_rechecked | yes | yes | `src/application/global_kill_switch.py`; `src/infrastructure/pg_global_kill_switch_repository.py` | Prior SOL GKS state cannot be assumed current for BNB. | Read GKS state and fail closed if unclear. | Blocking safety state could be bypassed conceptually. | yes |
| G04 | Startup guard | runtime_bound_guard_required | yes | yes | `src/application/startup_trading_guard.py`; `src/interfaces/api_console_runtime.py` | Startup guard is process-local runtime-owned state. | Use guard-only preflight/control surface; do not start strategy execution. | Runtime startup check may be skipped. | yes |
| G05 | Execution permission | read_only_by_default | yes | yes | `src/application/execution_permission.py` | Current BNB chain never requests execution permission. | Keep `READ_ONLY` until separate Owner-authorized rehearsal task. | Observation could be mistaken for permission escalation. | yes |
| G06 | Order path | not_touched_by_observation_chain | yes | yes | `src/application/order_lifecycle_service.py`; `src/infrastructure/pg_order_repository.py` | Order path exists but is outside observation/design chain. | Any testnet use must be a separate isolated rehearsal task. | Design artifact could accidentally become an order path. | yes |
| G07 | Risk capital | policy_known_needs_current_value | yes | yes | `mi001_bnb_bounded_trial_design_v0.md` | Dedicated-account equity policy known; current value must be captured. | Compute from fresh read-only account facts; no top-up/transfer/withdrawal. | Size may exceed Owner intended risk capital. | yes |
| G08 | Leverage / max notional | draft_only | yes | yes | `mi001_bnb_bounded_trial_design_v0.md` | Max 5x rule drafted, but BNB cap missing. | Freeze BNB max leverage 5x and notional cap before rehearsal packet. | Allowed notional may be overstated. | yes |
| G09 | Max loss / attempts / position count | draft_only | yes | yes | `mi001_bnb_bounded_trial_design_v0.md` | Max attempts and one-position rule not canonical config. | Record max attempts=3 draft, max simultaneous position=1, max loss bounded by dedicated equity. | Repeated confirmations could create unintended exposure. | yes |
| G10 | Exit / stop model | draft_only_needs_rehearsal_packet | yes | yes | `mi001_bnb_bounded_trial_design_v0.md` | Stops drafted but not operationally proven. | Define time/manual/Operation Layer/invalidation stop procedure. | Position could open without audited exit process. | yes |
| G11 | No-chase / wait-for-confirmation | required_by_case_001_path | yes | yes | `mi001_bnb_live_case_001.md` | 1h/4h adverse path requires confirmation gate. | Keep BNB case in review until later windows or new confirmation case. | Owner could chase local exhaustion. | yes |
| G12 | Active position / open orders | not_checked_for_bnb_current_task | yes | yes | `src/infrastructure/pg_position_repository.py`; `src/infrastructure/pg_order_repository.py` | Must be checked immediately before rehearsal/live. | Read PG/runtime state; block if BNB position/order exists or unknown. | Duplicate/conflicting exposure. | yes |
| G13 | Reconciliation | required_not_proven_for_bnb | yes | yes | `src/application/reconciliation.py`; `src/application/startup_reconciliation_service.py` | Observation chain has not proven BNB account/order reconciliation. | Run read-only reconciliation precheck; block on mismatch. | Local state may diverge from exchange state. | yes |
| G14 | Evidence / audit logging | observation_logging_ready_trial_audit_needed | yes | yes | `brc_strategy_group_observations`; `brc_strategy_group_forward_reviews`; `src/application/brc_operation_layer.py` | Observation persisted; rehearsal/live audit packet not defined. | Require Operation Layer preflight/audit records for handoff. | Owner decisions may be hard to reconstruct. | yes |
| G15 | Observation case queue | available_for_would_enter_review | no | no | `src/application/strategy_group_observation_case_queue.py` | Queue is review-only, not permission source. | Continue using it for signal review and forward status. | Case visibility could be mistaken for actionability. | no |
| G16 | Forward review | 1h_4h_completed_12h_24h_72h_pending | yes | yes | `bnb_live_case_forward_review_continuation.md` | Later windows pending and early path adverse. | Wait for due windows or require new confirmation case before escalation. | Trial design may ignore adverse path risk. | yes |
| G17 | Owner confirmation | design_review_only_no_authorization | yes | yes | `mi001_bnb_owner_decision_checklist.md` | No Owner testnet or small-live final approval exists. | Use explicit checklist and separate final authorization record. | Review artifacts could be misread as start approval. | yes |
| G18 | Testnet rehearsal | design_only_not_started | yes | no | `docs/ops/plc-phase5e-controlled-multi-symbol-testnet-runtime-rehearsal.md`; `scripts/start_brc_local_testnet.sh` | Repo has historical testnet surfaces but no BNB-specific rehearsal packet. | Prepare BNB-specific testnet rehearsal task with isolated testnet config. | Order path could touch wrong environment or symbol. | yes |
| G19 | Small live trial | draft_only_not_authorized | no | yes | `mi001_bnb_small_live_trial_readiness_draft.md` | Small-live requires final Owner approval after prerequisites. | Do not proceed until all gates pass and Owner grants final approval. | Real funds could be used without final decision. | yes |

## Non-permissions

- no trial start
- no testnet rehearsal start
- no small live authorization
- no execution intent
- no order permission
- no execution permission
- no runtime start
- no leverage change
- no transfer / withdrawal
