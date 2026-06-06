# Generic FinalGate Live Action Chain Blocker Record - 2026-06-05

## BlockerRecord

```yaml
id: BR-GF-LIVE-20260605-001
stage: live_action_execution
path: GenericActionSpec -> FinalGate -> Owner authorization -> official API execute -> TP/SL -> Review/Audit
severity: hard_blocker
evidence:
  - Current code/test work proved GenericActionSpec final-gate consumption and fail-closed behavior locally.
  - Current code/test work proved ActionSpec-bound reconciliation, market metadata, TP/SL readiness, and intent/order/review/audit recording readiness gates locally.
  - Latest targeted verification passed: tests/unit/test_exchange_credential_preflight.py, tests/unit/test_trend_execute_server_readiness_probe.py, tests/unit/test_owner_trial_flow.py, tests/unit/test_protection_price_planner.py, tests/unit/test_generic_final_gate_probe.py, tests/unit/test_production_strategy_family_admission.py, tests/unit/test_trading_console_readmodels.py = 154 passed, 2 warnings.
  - Generic FinalGate read-only evidence probe exists at scripts/probe_generic_final_gate_readonly.py and defaults to dry-run with no PG/exchange reads.
  - Official API path is proven locally for Trend/SOL: current -> risk acknowledgement -> authorization draft -> live authorization -> execute preflight 409 without intent/order creation.
  - Targeted Trading Console/admission regression passed inside the 34-test regression group.
  - Alembic heads returned 042 (head).
  - This run did not start runtime.
  - Initial run did not bind current live PG/exchange evidence for the Trend/SOL exact scope.
  - Initial run did not invoke the official execute endpoint.
  - Initial run did not create ExecutionIntent, orders, TP/SL orders, review result, or audit/result rows in live PG.
  - Follow-up guarded probe with RUN_GENERIC_FINAL_GATE_PROBE=true bound live/read-only PG and exchange facts for TF-001-live-readonly-v0.
  - Probe gateway binding reached ready with ExchangeGateway after restoring probe env from .env.local.readonly across api module import.
  - Probe facts clear: active_position, open_order, gks, account_facts, market_metadata, protection_readiness, recording_readiness.
  - Earlier probe reconciliation returned blocked/non-clean before reconciliation was promoted into the GenericActionSpec hard-gate set; that earlier passed probe is no longer sufficient evidence for current code.
  - Final hard blockers after live/read-only probe: startup_guard_runtime_not_started, startup_guard_not_armed, startup_guard_not_started.
  - Non-permissions remained false: execution_intent_created=false, order_created=false, runtime_started=false, exchange_write_api_called=false.
  - Owner API path then created scoped startup-guard clearance clearance-31c76ce42acd4965ad6402115987e80a for authorization auth-f43ecd5901c342deb4b2466c0548ebc4; response remained metadata_only and runtime_started=false, execution_intent_created=false, order_created=false, exchange_write_api_called=false.
  - Follow-up Generic FinalGate read-only probe returned result=passed, hard_blockers=[], owner_trigger_visible=true, owner_trigger_enabled=true.
  - Official execute endpoint was invoked exactly once for authorization auth-f43ecd5901c342deb4b2466c0548ebc4 after final-gate pass.
  - Exchange rejected the live entry order with Binance error -2015: Invalid API-key, IP, or permissions for action.
  - PG evidence after execute attempt: execution_intent intent-76dd2eb6c561447b999d99641a462f19 status=failed, failed_reason=F-011, order_id=6e6aa77e-6995-4b98-9237-3dcb198a18db, exchange_order_id=NULL.
  - PG order evidence after execute attempt: local order 6e6aa77e-6995-4b98-9237-3dcb198a18db status=REJECTED, order_type=MARKET, exchange_order_id=NULL.
  - Authorization remained consumed=false, execution_intent_created=false, order_created=false in authorization metadata; the failed intent/order are audit evidence of the rejected attempt.
  - Post-attempt read-only exchange probe still showed active_position clear and open_order clear for the scoped Trend/SOL path.
  - Later follow-up with explicit process-local read-only probe overrides again bound real PG/exchange facts and initially blocked only on expired/absent startup_guard clearance.
  - PG read-only evidence showed Trend authorization auth-f43ecd5901c342deb4b2466c0548ebc4 still live_authorized=true, consumed=false, live_ready=false, execution_intent_created=false, order_created=false, auto_execution_enabled=false, and not expired.
  - PG read-only evidence showed previous scoped startup_guard clearance clearance-31c76ce42acd4965ad6402115987e80a was expired.
  - Owner API path created a fresh scoped startup-guard clearance clearance-7beac3de88e14b678f86652d24f6685f; response remained metadata_only=true, runtime_started=false, execution_intent_created=false, order_created=false, order_permission_granted=false, execution_permission_granted=false, exchange_write_api_called=false.
  - Follow-up Generic FinalGate read-only probe returned result=passed, gateway_binding=ready, hard_blockers=[], owner_trigger_visible=true, owner_trigger_enabled=true; facts clear: active_position, open_order, gks, startup_guard, account_facts, market_metadata, protection_readiness, recording_readiness. This historical probe predates the latest reconciliation hard-gate binding and must be rerun before any new live action.
  - A subsequent official execute endpoint call was made only to verify retry safety after the existing exchange-rejected attempt; it returned 409 before ExecutionIntent/order creation with execution_intent_created=false and order_created=false.
  - Official execute retry-safety blockers included duplicate_execution_intent_for_authorization and previous_intent_has_order_id; PG read-only evidence after the call still showed exactly one intent and one linked rejected local order for authorization auth-f43ecd5901c342deb4b2466c0548ebc4.
  - API error handling was tightened so HTTPException dict details remain structured; official execute retry-safety response now exposes code=owner_bounded_execution_blocked, blockers=[...], execution_intent_created=false, and order_created=false at top level instead of stringifying the blocker payload.
  - Owner-bounded gateway binding and FinalGate permission checks now separate read-only probe mode from official execute mode: read-only probes still require BRC_EXECUTION_PERMISSION_MAX=read_only, while the official execute endpoint requires/evaluates BRC_EXECUTION_PERMISSION_MAX=order_allowed.
  - Follow-up official execute retry-safety call with process-local BRC_EXECUTION_PERMISSION_MAX=order_allowed no longer reported global_permission_not_order_allowed; it still returned 409 before state creation because gateway initialization failed and the authorization has a previous failed intent/order.
  - Gateway initialization failure reporting was tightened; official execute retry-safety response now exposes gateway_binding_blockers including exchange_gateway_initialization_failed:FatalStartupError and exchange_gateway_initialization_failed:F-004.
bridge:
  - GenericActionSpec now maps into final-gate dry-run requests.
  - FinalGate now validates ActionSpec-bound fact snapshot scope.
  - FinalGate now requires reconciliation facts for ActionSpec paths.
  - FinalGate now requires read-only market metadata for ActionSpec paths.
  - FinalGate now requires TP/SL protection readiness for ActionSpec paths.
  - FinalGate now requires intent/order/review/audit recording readiness for ActionSpec paths.
  - Official execute route collects facts from the Owner authorization scope instead of the old BNB default.
  - Official execute route binds the owner-bounded gateway before fact collection, so market metadata and protection readiness read the same scoped gateway.
  - Trend/SOL official API path now has a regression test proving exact scope propagation into execute preflight.
  - A replayable read-only probe now captures GenericActionSpec final-gate facts when RUN_GENERIC_FINAL_GATE_PROBE=true and live/read-only guards pass.
  - Generic FinalGate probe now snapshots/restores live/read-only env and exchange credential env after api module import, because local api.py loads .env.local with override=True.
  - Market metadata handling now accepts Binance futures amount precision as the amount step when limits.amount.step is absent/zero.
  - Owner trial-flow now exposes a narrow official API endpoint to persist scoped startup-guard clearance metadata for one Owner authorization; it does not start runtime, create execution intents, create orders, grant permissions, or call exchange APIs.
  - Owner bounded execute endpoint now closes the owner-bounded exchange gateway in a finally block to avoid leaking ccxt/aiohttp connections on safe failure paths.
retry_condition:
  - Exchange credential/IP/permission policy must allow the exact bounded Binance futures order action for SOL/USDT:USDT while preserving no-withdrawal and scoped Owner authorization controls.
  - Use a fresh Owner authorization or explicitly resolve the existing failed-intent state before retry; do not retry blindly against auth-f43ecd5901c342deb4b2466c0548ebc4.
  - Generic FinalGate read-only probe must again pass for TF-001-live-readonly-v0.
  - Current live PG and exchange read-only facts must remain clear for TF-001-live-readonly-v0 / SOL/USDT:USDT / long / qty 0.1 / max notional 20 / leverage 1.
  - TP/SL plan, intent/order/review/audit write readiness must pass.
```

## Exchange Permission BlockerRecord

```yaml
id: BR-GF-LIVE-20260605-002
stage: official_execute_entry_order
path: GenericActionSpec -> FinalGate -> Owner authorization -> official API execute -> entry order
severity: hard_blocker
evidence:
  - FinalGate returned passed for TF-001-live-readonly-v0.
  - Official execute endpoint was invoked exactly once for auth-f43ecd5901c342deb4b2466c0548ebc4.
  - Binance returned code -2015 with message Invalid API-key, IP, or permissions for action.
  - ExecutionIntent intent-76dd2eb6c561447b999d99641a462f19 was recorded with status=failed and failed_reason=F-011.
  - Local order 6e6aa77e-6995-4b98-9237-3dcb198a18db was recorded with status=REJECTED and exchange_order_id=NULL.
  - TP/SL protection was not created.
  - Post-attempt read-only probe showed no active position and no open order.
bridge:
  - Official GenericActionSpec to execute route is connected and fail-closed at exchange permission failure.
  - The failure is auditable through PG intent/order evidence and the captured execute response.
retry_condition:
  - Binance API key/IP/futures trade permission permits the exact bounded action, with withdrawal disabled.
  - A fresh Owner authorization is created or the existing failed attempt is explicitly resolved by policy.
  - FinalGate passes again and post-failure PG/exchange facts remain non-conflicting.
```

## Existing Failed Attempt Retry-Safety BlockerRecord

```yaml
id: BR-GF-LIVE-20260605-004
stage: official_execute_retry_safety
path: GenericActionSpec -> FinalGate passed -> official API execute retry-safety check
severity: hard_blocker
evidence:
  - Fresh scoped startup_guard clearance clearance-7beac3de88e14b678f86652d24f6685f was created through the official Owner API path and remained metadata_only.
  - Generic FinalGate read-only probe returned result=passed with hard_blockers=[] for TF-001-live-readonly-v0 after the fresh clearance.
  - Official execute endpoint was called to verify retry safety against authorization auth-f43ecd5901c342deb4b2466c0548ebc4 after the prior Binance -2015 rejected attempt.
  - The endpoint returned 409 before ExecutionIntent/order creation.
  - Blocking evidence included duplicate_execution_intent_for_authorization and previous_intent_has_order_id.
  - Response safety flags remained execution_intent_created=false and order_created=false.
  - PG read-only evidence after the call showed exactly one execution_intent for the authorization: intent-76dd2eb6c561447b999d99641a462f19 status=failed failed_reason=F-011 order_id=6e6aa77e-6995-4b98-9237-3dcb198a18db exchange_order_id=NULL.
  - PG read-only evidence after the call showed exactly one linked local order: 6e6aa77e-6995-4b98-9237-3dcb198a18db status=REJECTED order_type=MARKET exchange_order_id=NULL.
bridge:
  - The official execute path is fail-closed after a prior rejected attempt that created local intent/order evidence.
  - The chain now has replayable proof that FinalGate can pass while retry-safety still prevents duplicate live action on the same authorization.
  - Official execute blocker responses now preserve structured blocker fields for Owner/API audit.
  - Official execute env semantics no longer conflict with read-only probe semantics.
  - Gateway initialization blockers now include the sanitized fatal startup error code for retry triage.
retry_condition:
  - Resolve Binance API key/IP/futures trade permission for the exact bounded action.
  - Use a fresh Owner authorization or an explicit audited failed-attempt resolution policy before any new execution attempt.
  - Re-run read-only FinalGate evidence and verify PG/exchange facts remain non-conflicting.
```

## Probe Environment Guard BlockerRecord

```yaml
id: BR-GF-LIVE-20260605-003
stage: read_only_probe_environment_guard
path: GenericActionSpec -> guarded read-only PG/exchange evidence probe
severity: hard_blocker
evidence:
  - Follow-up live/read-only probe attempted after commit 6493a94c.
  - Probe default dry-run remained safe: creates_authorization=false, creates_execution_intent=false, places_order=false, starts_runtime=false, exchange_write_methods_called=false.
  - Guarded run using .env.local.readonly refused to continue because the process environment contained EXCHANGE_TESTNET=true, BRC_EXECUTION_PERMISSION_MAX=order_allowed, RUNTIME_CONTROL_API_ENABLED=true, and RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=true.
  - No PG read, exchange read, runtime start, authorization creation, execution intent, order, cancel, flatten, retry protection, or credential change was performed by the blocked guarded probe.
bridge:
  - Probe now converts unsafe guard failures into a structured BlockerRecord-shaped JSON result instead of a Python traceback.
  - Guard remains fail-closed before PG/exchange reads.
retry_condition:
  - Provide or export a truly read-only probe environment: TRADING_ENV=live, EXCHANGE_TESTNET=false, BRC_EXECUTION_PERMISSION_MAX=read_only, RUNTIME_CONTROL_API_ENABLED=false, RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=false, CORE_*_BACKEND=postgres, and PG_DATABASE_URL set.
  - Re-run scripts/probe_generic_final_gate_readonly.py with RUN_GENERIC_FINAL_GATE_PROBE=true only after the guard environment is read-only.
```

## Read-Only Exchange Fact Collection BlockerRecord

```yaml
id: BR-GF-LIVE-20260605-005
stage: read_only_exchange_fact_collection
path: GenericActionSpec -> official execute preflight -> read-only account/position/order/market facts
severity: hard_blocker
evidence:
  - Official execute mode now permits read-only fact collection while BRC_EXECUTION_PERMISSION_MAX=order_allowed; read-only probe mode still requires BRC_EXECUTION_PERMISSION_MAX=read_only.
  - A direct live read-only fact probe for TF-001-live-readonly-v0 / SOL/USDT:USDT reached the live fact-reader branch, but Binance returned code -2008 with message Invalid Api-Key ID during account fact collection.
  - This is a credential/API-key identity blocker for read-only exchange facts, not a strategy-evidence blocker.
  - No new authorization, ExecutionIntent, order, TP/SL, review, audit row, runtime start, cancel, flatten, or retry protection was created by this probe.
  - Code now converts read-only exchange exceptions into sanitized unavailable facts instead of raising a raw traceback.
  - The sanitized unavailable reason preserves only the exception type and exchange error code, for example exchange_read_failed:RuntimeError:exchange_error_code:-2008.
  - Unit regression proves the read-only client is closed after the failed read and that the raw Invalid Api-Key ID text is not returned in the facts payload.
  - Collector regression proves the sanitized exchange error code is preserved in account_facts evidence while active_position/open_order remain fail-closed unavailable blockers and execution_intent_created=false, order_created=false.
bridge:
  - Official execute preflight can evaluate read-only fact collection in order_allowed mode without treating the permission mode itself as unsafe.
  - Read-only exchange errors now fail closed as account_facts/position/open_order unavailability and can be surfaced as precise FinalGate blockers.
  - Raw exchange error messages stay out of the returned fact payload.
  - Preflight fact snapshots now retain safe unavailable reasons in evidence so FinalGate/API audit can distinguish credential/API identity blockers from generic repository absence.
  - FinalGate preview output now exposes generic active_position/open_order aliases and scope-aware Owner trigger text for Trend/SOL instead of BNB-only preview wording; legacy bnb_position/bnb_open_order fields remain for compatibility.
  - Action-chain regression now proves the real Volatility expansion and Mean reversion proposal IDs (VB-001-live-readonly-v0 and MR-001-live-readonly-v0) remain blocked by generic_action_spec_status_not_final_gate_ready, generic_action_spec_not_action_registry_supported, and unsupported_carrier, with no intent/order creation.
  - FinalGate responses now expose non-mutating provenance fields: legacy run() keeps final_gate_input_kind=legacy_request, while run_action_spec() returns final_gate_input_kind=generic_action_spec with the GenericActionSpec status and action-registry flag.
  - Safe fake-exchange regression now proves the Trend/SOL catalog path can close entry -> TP -> SL -> review/result logging with TF-001-live-readonly-v0 / SOL/USDT:USDT / long / qty 0.1 after Generic FinalGate passes.
  - Official API route regression now proves the FastAPI execute endpoint can drive TF-001-live-readonly-v0 through scoped fact collection, Generic FinalGate, OwnerBoundedExecutionService, fake-gateway entry, TP, SL, position projection, authorization consumption, and brc_execution_results logging without touching a real exchange.
  - Official API route regression also proves the existing MI-001-BNB-LONG path remains compatible with the generic action chain by closing the fake-gateway BNB entry -> TP -> SL -> position projection -> authorization consumption -> brc_execution_results path through the same execute endpoint.
  - The Trend/SOL and BNB full-chain route regressions now assert the complete brc_execution_results envelope: recheck_result, adapter_result, result_summary, audit_refs, review_refs, and final_state_snapshot, not just operation_id/status.
  - HTTP metadata-route regression now proves Trend wrong-symbol authorization draft and wrong-side activation fail closed before live authorization, ExecutionIntent, order table, or order state creation.
  - GenericActionSpec FinalGate now requires reconciliation facts as part of ActionSpec-bound preflight evidence; missing or blocked reconciliation facts fail closed before intent/order creation.
  - Reconciliation evidence now includes generic scoped aliases for PG/exchange active-position and open-order counts, while retaining legacy BNB-named fields for compatibility.
  - GenericActionSpec FinalGate now also fails closed when max_attempts, protection_mode, or review_requirement deviates from the exact Owner scope.
  - Recording readiness now requires full execution_intents/orders repository write columns plus a full brc_execution_results review/audit envelope (recheck_result, adapter_result, result_summary, audit_refs, review_refs, final_state_snapshot); minimal placeholder tables no longer satisfy GenericActionSpec live-chain readiness.
  - Protection planning now normalizes sub-step Decimal storage noise before min-amount/step validation, and Owner bounded entry submission uses the exact catalog quantity when the stored authorization quantity is scope-equivalent.
  - PGExecutionIntentORM now uses a SQLite JSON variant for signal/strategy payloads, matching other PG model test variants and allowing full execution-chain ORM tables to be created in local SQLite regression tests without changing the deployed PG JSONB schema.
  - Protection attach failure regressions now assert the full failure brc_execution_results envelope with audit_refs, review_refs, final_state_snapshot, and manual_review_required before any retry is allowed.
retry_condition:
  - Use a valid server-side Binance API key id/secret/IP/futures read/trade permission for the exact live subaccount, while preserving no-withdrawal constraints; the local environment is not considered sufficient for live execution.
  - Run the official execute chain on the server-side API path only after the server environment proves the same read-only facts and hard gates; do not transplant secrets into chat or commit them.
  - Re-run read-only fact collection for TF-001-live-readonly-v0 and verify account facts, active position, open orders, market metadata, TP/SL readiness, recording readiness, and reconciliation are readable and non-conflicting.
  - Use a fresh Owner authorization or an explicit audited failed-attempt resolution policy before any new official execute attempt.
```

## Exchange Credential Preflight BlockerRecord

```yaml
id: BR-GF-LIVE-20260606-006
stage: exchange_credential_preflight
path: server Exchange credentials -> Binance restrictions -> USDT-M account facts -> SOL scoped reads -> Generic FinalGate retry
severity: hard_blocker
evidence:
  - Mainline credential loading uses EXCHANGE_API_KEY and EXCHANGE_API_SECRET; BINANCE_API_KEY and BINANCE_SECRET_KEY are not the Trading Console/Owner Console truth-source credentials.
  - Official owner-bounded gateway binding regression proves BINANCE_API_KEY/BINANCE_SECRET_KEY alias-only credentials do not construct an exchange gateway; canonical EXCHANGE_API_KEY/EXCHANGE_API_SECRET remain required.
  - Environment contract confirms EXCHANGE_API_KEY and EXCHANGE_API_SECRET are the canonical server secret names.
  - Added scripts/probe_exchange_credential_preflight.py as a secret-safe credential preflight tool. Default mode is dry-run and performs no PG/exchange reads.
  - Added GET /api/brc/owner-trial-flow/exchange-credential-preflight as the operator-authenticated server-side credential preflight route. Default run=false is dry-run and performs no exchange reads.
  - API regression proves run=true blocks at env guard before gateway construction when canonical server env is missing.
  - API regression proves a fake server gateway can pass load_markets, Binance API restrictions, USDT-M futures balance, SOL position/open-order/stop-order, and market metadata checks without returning secret values.
  - Explicit local run with RUN_EXCHANGE_CREDENTIAL_PREFLIGHT=true returned result=blocked before exchange access because local env lacks TRADING_ENV=live, EXCHANGE_TESTNET=false, RUNTIME_* guards, and canonical EXCHANGE_API_KEY/EXCHANGE_API_SECRET.
  - The local preflight output only reported key/secret presence booleans, env modes, blockers, and safety flags; it did not print credential values.
  - The preflight tool classifies Binance credential failures by sanitized category and error code, including invalid_api_key_id for -2008, invalid_api_key_ip_or_permissions for -2015, and secret_mismatch_or_invalid_signature for -1022.
  - The preflight tool reads Binance API restrictions as sanitized booleans only: reading_enabled, futures_enabled, read_only_permission_present, futures_trade_permission_present, order_permission_distinguished_from_read_only, spot_margin_trading_enabled, withdrawals_enabled, and ip_restricted.
  - The preflight tool never places, cancels, replaces, flattens, or retries orders.
  - Unit tests passed for canonical env handling, alias mismatch detection, sanitized error classification, sanitized Binance API restriction summaries, withdrawal-enabled hard blocking, and non-Trend symbol fail-closed behavior before gateway construction.
  - API regression now proves a Binance -2015 credential/IP/permission failure is returned only as load_usdt_m_futures_markets:invalid_api_key_ip_or_permissions plus exchange_error_code=-2015, without raw Invalid API-key text or credential values.
  - Credential preflight now fails fast after the initial USDT-M market/auth initialization check, Binance API restriction check, or USDT-M futures account read fails, so the root credential/IP/futures blocker is not diluted by cascading generic scoped-read failures.
  - Failed authorization auth-f43ecd5901c342deb4b2466c0548ebc4 remains unsafe to blindly reuse because previous failed intent/order evidence exists.
  - Existing retry policy allows only pre-order failed intents without local/exchange order evidence; failed intents with order_id, exchange_order_id, or local linked order remain blocked.
  - Added GET /api/brc/owner-trial-flow/authorizations/{authorization_id}/execute-readiness as a read-only retry-safety view. It checks authorization state, prior ExecutionIntent/order linkage, and adapter support without collecting facts, creating state, or touching exchange.
  - API regression proves an authorization with a failed ExecutionIntent plus linked local rejected order returns ready=false with duplicate_execution_intent_for_authorization and previous_intent_has_order_id, while execution_intents/orders counts remain unchanged.
  - Added GET /api/brc/owner-trial-flow/authorizations/{authorization_id}/execution-state as a read-only PG evidence view. It returns prior ExecutionIntent, local order, brc_execution_results, retry classification, and safety flags without mutating PG or touching exchange.
  - API regression proves execution-state surfaces failed intent/order/result evidence and preserves execution_intents/orders/brc_execution_results counts unchanged.
  - Added GET /api/brc/owner-trial-flow/authorizations/{authorization_id}/final-gate-dry-run as an authorization-scoped final-gate replay route. Default run=false returns a plan only; run=true collects read-only facts and reruns final gate without creating intent/order state.
  - API regression proves final-gate dry-run plan mode does not collect facts, and run=true with fake facts returns passed for the exact Trend scope while execution_intents/orders/brc_execution_results counts remain zero.
  - API regression proves final-gate dry-run blocks a stale/non-current authorization with authorization_not_current_for_carrier before fact collection and with execution_intent/order/exchange_write safety flags false.
  - Added docs/ops/trend-execute-retry-server-readiness-runbook-2026-06-06.md to define the server-side evidence order before any Trend execute retry.
  - Added scripts/probe_trend_execute_server_readiness.py to call the server API evidence sequence without printing cookies, tokens, credentials, or request headers.
  - The Trend server-readiness probe defaults to evidence-only GET calls and blocks execute unless credential preflight, execution-state retry policy, execute-readiness, and final-gate dry-run all pass.
  - The Trend server-readiness probe requires OWNER_APPROVED_TREND_BOUNDED_EXECUTION=TF-001-live-readonly-v0:SOL/USDT:USDT:LONG:0.1:20:1:max_attempts_1:single_tp_plus_sl before it will send the official execute POST.
  - Local dummy-base run with TREND_EXECUTE_API_BASE=http://127.0.0.1:9 and a dummy session cookie returned transport_error/connection refused, execute_allowed_by_probe=false, and did not create state or perform a live action.
  - Unit regression for scripts/probe_trend_execute_server_readiness.py proves default evidence mode never POSTs even when all GET evidence passes, prepare_authorization mode creates only authorization metadata after credential preflight and exact Owner approval, execute mode does not POST without exact Owner approval, does not POST when execution-state says the authorization is not retryable, returns a non-zero exit code for blocked execute mode, posts only after all evidence responses pass, and redacts session/secret fields without hiding authorization ids.
  - Local repository search did not find an authoritative server API base URL plus usable operator session cookie/token; server credential proof remains external to this local worktree until the server API probe is run in the server-authenticated environment.
bridge:
  - Server-side operators can now run RUN_EXCHANGE_CREDENTIAL_PREFLIGHT=true python3 scripts/probe_exchange_credential_preflight.py to prove credential/IP/futures permission readiness without exposing secrets or creating orders.
  - Server-side operators can also call GET /api/brc/owner-trial-flow/exchange-credential-preflight?run=true through the official operator-authenticated API to produce the same secret-safe readiness evidence.
  - Server-side operators can call GET /api/brc/owner-trial-flow/authorizations/{authorization_id}/execute-readiness before any retry to confirm whether the authorization is blocked by previous intent/order evidence.
  - Server-side operators can call GET /api/brc/owner-trial-flow/authorizations/{authorization_id}/execution-state to capture replayable PG evidence for the failed authorization before deciding whether a fresh authorization or audited resolution policy is required.
  - Server-side operators can call GET /api/brc/owner-trial-flow/authorizations/{authorization_id}/final-gate-dry-run?run=true after credential proof to rerun exact-scope final gate before any execute attempt.
  - The server runbook now states that no audited failed-attempt resolution path currently exists for an authorization with linked local order evidence; use a fresh Owner authorization after credential proof instead of patching PG.
  - The server retry runbook sequences credential preflight, execution-state evidence, execute-readiness, final-gate dry-run, and only then official execute.
  - The server retry runbook now includes the Trend server-readiness probe command and its exact execute approval guard.
  - The server retry runbook now includes a prepare_authorization mode that runs credential preflight first and then uses only the official metadata-only risk acknowledgement, draft, and live authorization activation endpoints to produce a fresh authorization id.
  - The Trend server-readiness probe accepts either a server-side signed operator session from BRC_OPERATOR_* env or a provided TREND_EXECUTE_SESSION_COOKIE/OWNER_BOUNDED_SESSION_COOKIE, and redacts session/cookie/token/secret fields from output.
  - The result separates missing canonical env, ignored Binance alias env, invalid key id, secret/signature mismatch, IP/permission ambiguity, missing futures permission, read-only account-read failure, withdrawal-permission risk, and unsupported preflight symbol.
  - Local development remains blocked for live action and can still validate code/tests/docs without server secrets.
retry_condition:
  - Run the credential preflight on the server API environment with TRADING_ENV=live, EXCHANGE_TESTNET=false, EXCHANGE_NAME=binance, EXCHANGE_API_KEY/EXCHANGE_API_SECRET set, RUNTIME_CONTROL_API_ENABLED=false, and RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=false.
  - Credential preflight must pass Binance restrictions with withdrawals_enabled=false, read_only_permission_present=true, futures_trade_permission_present=true, and scoped SOL/USDT:USDT futures account/position/open-order/market metadata reads available.
  - After server credential proof passes, create a fresh Owner authorization or use an explicit audited failed-attempt resolution policy; do not reuse auth-f43ecd5901c342deb4b2466c0548ebc4 blindly.
  - Before official execute retry, GET /api/brc/owner-trial-flow/authorizations/{authorization_id}/execute-readiness must return ready=true for the selected fresh/resolved authorization.
  - If an old authorization is considered for reuse, GET /api/brc/owner-trial-flow/authorizations/{authorization_id}/execution-state must show no linked local/exchange order evidence and retry_allowed=true; otherwise use a fresh Owner authorization or explicit audited resolution policy.
  - Re-run Generic FinalGate with GET /api/brc/owner-trial-flow/authorizations/{authorization_id}/final-gate-dry-run?run=true for TF-001-live-readonly-v0 / SOL/USDT:USDT / long / qty 0.1 / max notional 20 / leverage 1 / single_tp_plus_sl on server-side read-only facts before any official execute.
  - If using scripts/probe_trend_execute_server_readiness.py, provide TREND_EXECUTE_API_BASE, TREND_EXECUTE_SESSION_COOKIE or server-side BRC_OPERATOR_* session env, TREND_EXECUTE_AUTHORIZATION_ID, and run evidence mode before execute mode.
  - Follow docs/ops/trend-execute-retry-server-readiness-runbook-2026-06-06.md for the complete server evidence sequence and report fields.
```

## Safety Outcome

One official bounded execute endpoint attempt was performed after FinalGate passed. Binance rejected the entry order before any exchange order id was returned. Post-attempt read-only evidence showed no active position and no open order for the scoped Trend/SOL path.

No cancel, replace, flatten, retry protection, runtime start, credential change, PG migration, or push was performed in this run. The only PG mutation in the follow-up was metadata-only scoped startup_guard clearance creation through the official Owner API path; it did not grant order/execution permission and did not create intent/order state. The latest read-only exchange fact blocker was handled as fail-closed preflight evidence and did not create any new live action state.
