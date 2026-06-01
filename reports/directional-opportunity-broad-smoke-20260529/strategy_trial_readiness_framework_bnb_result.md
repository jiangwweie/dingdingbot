# Strategy Trial Readiness Framework Sprint Result

Generated: 2026-06-01

## 1. What Changed

Built a generic `StrategyTrialReadiness` framework and used `MI-001 BNB long` as the first carrier profile.

The new readiness surface connects:

`strategy observation case -> risk cap profile -> minimal safety preflight -> Owner decision state -> testnet same-path rehearsal readiness state`

This remains readiness-only. It does not start testnet rehearsal, start live trading, create execution intents, create or cancel orders, grant execution permission, start runtime, or treat `would_enter` as an order instruction.

## 2. Before vs After

| area | before | after |
| --- | --- | --- |
| Readiness model | BNB-specific gap map plus reports | Generic `StrategyTrialReadiness` model with BNB carrier instance |
| BNB profile | Present in reports | Structured `StrategyProfile` instance: MI / MI-001 / BNBUSDT / long |
| Risk cap | Design draft / gap notes | Structured `RiskCapProfile` with tiny configurable placeholder, max position/attempts, owner-confirm mode |
| Preflight | Gap checklist | Structured `StrategyTrialPreflightResult` with blockers/warnings/evidence |
| Owner state | Checklist report | API field `owner_decision_state` |
| Testnet readiness | Draft-only | API field `rehearsal_readiness_state` |
| Console | BNB gap panel | Adds generic Strategy Trial Readiness Framework panel |

Current result:

`testnet_rehearsal_not_ready_with_explicit_blockers`

Reason: the framework exists and BNB cap profile is present, but current public-observation mode does not safely prove active position, open order, GKS, startup guard, or reconciliation state. Owner authorization is also still missing.

## 3. Files Changed

- `src/application/strategy_trial_readiness.py`
- `src/interfaces/api_brc_console.py`
- `tests/unit/test_strategy_trial_readiness.py`
- `tests/unit/test_brc_console_api_surface.py`
- `gemimi-web-front/src/services/api.ts`
- `gemimi-web-front/src/pages/brc/OwnerConsoleV2.tsx`
- `gemimi-web-front/src/pages/brc/OwnerConsoleV2.test.tsx`
- `reports/directional-opportunity-broad-smoke-20260529/strategy_trial_readiness_framework_bnb_result.md`

## 4. Tests Run

Validation commands and final results are recorded in the assistant final response.

## 5. Current Readiness Result

Current API verdict:

`testnet_rehearsal_not_ready_with_explicit_blockers`

Expected next good state, once safety facts are proven and Owner has not yet authorized:

`testnet_rehearsal_ready_pending_owner_authorization`

The system remains:

- `not_live_ready`
- `not_auto_execution_ready`
- `readiness_only`
- `testnet_rehearsal_pending_owner_authorization`

## 6. Why Still Not Live Ready

Live remains blocked because:

- no final Owner live approval exists;
- no small-live authorization exists;
- active position/open order checks are not satisfied in public-observation mode;
- GKS/startup/reconciliation facts are not proven for BNB in this readiness surface;
- BNB 12h/24h/72h forward review remains pending;
- testnet same-path rehearsal has not been authorized or run;
- `would_enter` remains a review signal only.

## 7. Generic And Reusable

Generic components:

- `StrategyProfile`
- `RiskCapProfile`
- `TrialReadinessPreflightInput`
- `StrategyTrialPreflightResult`
- `StrategyTrialReadinessResponse`
- `evaluate_strategy_trial_preflight`

The model is not BNB-only. Tests verify it can represent a non-BNB profile such as `MI-001 SOL long`.

## 8. BNB-specific

BNB is represented as the first carrier profile:

- strategy group: `MI`
- strategy id: `MI-001`
- candidate id: `MI-001-BNB-LONG`
- symbol: `BNBUSDT`
- side: `long`
- execution mode: `owner_confirm_each_entry`
- auto within budget: `false`

BNB cap profile:

- max concurrent position: `1`
- max daily attempts: `1`
- max trial attempts: `3`
- max notional: `tiny_configurable_placeholder_requires_owner_confirmation`
- leverage: `1x_testnet_default_or_lower_until_owner_changes`
- no auto reentry
- no averaging down
- Owner confirms each entry

## 9. Market Data Architecture

This sprint did not create a new uncontrolled market data path.

Current observation source remains:

- `BinancePublicKlineMarketSource`
- public REST USD-M klines
- latest closed 1h bar
- no API key
- no private account API
- no `exchange_gateway`

The generic readiness API reports the abstraction as:

- `StrategyGroupMarketBarSource`
- current provider: public REST kline provider
- WebSocket not required for this sprint
- future `ExchangeGatewayMarketProvider` only belongs in controlled runtime/testnet/live contexts

## 10. Remaining Blockers Before Testnet Rehearsal

- Owner authorization for BNB testnet same-path rehearsal.
- Active conflicting BNB position check.
- Open conflicting BNB order check.
- GKS state check.
- Startup guard state check.
- Reconciliation status check.
- BNB cap placeholder must be confirmed or concretized.
- Operation Layer cap and audit path must remain enforced.

## 11. Remaining Blockers Before Tiny Live

- All testnet blockers above.
- Successful Owner-reviewed testnet same-path rehearsal.
- Fresh live account facts.
- Final Owner small-live approval.
- Small-live risk cap and notional cap concretized.
- BNB forward review and no-chase / wait-for-confirmation gates reviewed.
- Live preflight must pass without unresolved blockers.

## 12. Safety Proof

| check | result |
| --- | --- |
| live order | not created |
| real funds | not touched |
| credentials | not changed |
| automatic execution | not enabled |
| observation-to-order shortcut | not added |
| execution intent | not created |
| order path | not called |
| exchange gateway | not modified |
| runtime | not started |

## 13. Next Owner Decision

Decide whether to authorize a separate BNB testnet same-path rehearsal preflight task after the required safety facts can be checked.
