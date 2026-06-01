# Strategy Trial Architecture Governance Result

## 1. Goal

Consolidate the BNB first-carrier validation into a reusable Strategy Trial architecture without starting live trading, using real funds, creating execution intents, or granting execution permission.

Final target:

- `strategy_trial_architecture_governed`
- `bnb_first_carrier_consolidated`
- `not_live_ready_until_explicit_owner_live_authorization`

## 2. What Changed

- Added a pure application-layer architecture governance model for Strategy Trial carriers.
- Added BNB as the first concrete carrier instance of the generic model.
- Added a pending `BoundedLiveTrialAuthorization` draft shape.
- Added a minimal live trial gate that separates strategy warnings from hard safety blockers.
- Added a read-only Owner Console API surface:
  - `GET /api/brc/strategy-trial-architecture/bnb-first-carrier`
- Added targeted tests for model semantics and API non-executability.

No live order, real-funds action, runtime start, execution intent, or execution permission was created.

## 3. Architecture Boundary Decisions

| concept | decision |
| --- | --- |
| StrategyFamily | Strategy logic identity only. It has no order authority. |
| Carrier | Strategy family plus symbol, side, quantity, leverage, cap, and protection shape. |
| RiskCapProfile | Generic cap shape; concrete values remain carrier-specific. |
| ProtectionPlan | Generic planner/plan semantics; BNB `0.01` currently maps to `single_tp_plus_sl`. |
| OwnerRiskDisclosure | Strategy uncertainty is disclosure. It is not a permanent hard blocker after acknowledgement. |
| OwnerRiskAcknowledgement | Required for strategy warnings, but not equivalent to live order authorization. |
| BoundedLiveTrialAuthorization | Draft/pending model only until explicit Owner live authorization exists. |
| MinimalLiveTrialGate | Requires explicit Owner live authorization, zero hard blockers, and matching authorization scope. |

## 4. What Is Generic Now

- `StrategyTrialCarrierView`
- `StrategyTrialRiskWarning`
- `StrategyTrialHardBlocker`
- `OwnerReviewPacket`
- `BoundedLiveTrialAuthorizationDraft`
- `MinimalLiveTrialGateRequest`
- `MinimalLiveTrialGateResult`
- `evaluate_minimal_live_trial_gate()`

The gate does not require `strategy_warnings.empty`. It blocks on:

- missing explicit Owner live authorization
- symbol / side / carrier mismatch
- cap violation
- protection not executable
- active hard blockers such as GKS, conflicting position/order, logging unavailable, or result recording unavailable

## 5. What Remains Carrier-Specific By Design

| item | classification |
| --- | --- |
| `MI-001-BNB-LONG` carrier profile | carrier-specific by design |
| BNB runtime symbol `BNB/USDT:USDT` | carrier-specific by design |
| BNB testnet runtime profile allowlist | carrier-specific by design |
| Quantity `0.01 BNB` | carrier-specific by design |
| Max notional `20 USDT` | carrier-specific BNB cap instance |
| Protection plan instance `single_tp_plus_sl` | BNB first-carrier instance |

## 6. BNB-Specific Technical Debt

- Controlled testnet runtime endpoints remain BNB-first and allowlisted for this sprint.
- Authorization draft is application/read-model only and is not PG persisted yet.
- Owner Console can consume the API before a polished dedicated live packet UI exists.

These are not current hard blockers for architecture governance.

## 7. BNB Current State After Governance

| item | state |
| --- | --- |
| carrier | `MI-001-BNB-LONG` |
| strategy family | `MI-001` |
| symbol | `BNBUSDT` / `BNB/USDT:USDT` |
| side | `long` |
| quantity | `0.01 BNB` |
| leverage | `1x` draft carrier value, max allowed policy remains `5x` |
| max notional | `20 USDT` |
| protection | `single_tp_plus_sl` |
| testnet rehearsal | `completed_with_valid_protection` |
| live authorization | missing by design |
| authorization draft | `pending_owner_live_authorization` |
| live ready | `false` |
| auto execution ready | `false` |

The Owner review packet includes the completed protected testnet rehearsal evidence:

- entry order `1424453419`, filled `0.01 BNB`
- TP order `1424453440`, accepted then cleanup-canceled/terminalized
- SL order `1000000092441892`, accepted then cleanup-canceled
- cleanup close order `1424454000`, filled
- final local active BNB positions `0`
- final local open BNB orders `0`
- periodic reconciliation `consistent`
- campaign `brc-0dfc16d54418`, ended manual stop

## 8. Files Changed

- `src/application/strategy_trial_architecture_governance.py`
- `src/interfaces/api_brc_console.py`
- `tests/unit/test_strategy_trial_architecture_governance.py`
- `tests/unit/test_brc_console_api_surface.py`
- `reports/directional-opportunity-broad-smoke-20260529/strategy_trial_architecture_governance_result.md`

## 9. Tests Run And Results

Initial focused checks:

- `python3 -m pytest -q tests/unit/test_strategy_trial_architecture_governance.py` -> passed, `8 passed`
- `python3 -m pytest -q tests/unit/test_brc_console_api_surface.py::test_bnb_first_carrier_architecture_governance_api_is_non_executable` -> passed, `1 passed`
- `python3 -m compileall -q src/application/strategy_trial_architecture_governance.py src/interfaces/api_brc_console.py` -> passed

Final validation is recorded in the task summary.

## 10. Safety Proof

| safety item | result |
| --- | --- |
| live order | no |
| real funds | no |
| live execution permission | no |
| execution intent | no |
| order creation | no |
| runtime start | no |
| auto execution | no |
| credential changes | no |
| exchange gateway modified | no |
| observation-to-live-order shortcut | no |
| strategy warning acknowledgement treated as live authorization | no |
| authorization draft treated as order permission | no |

## 11. Final State

`strategy_trial_architecture_governed`

`bnb_first_carrier_consolidated`

The system remains:

- `not_live_ready_until_explicit_owner_live_authorization`
- `not_auto_execution_ready`
- `no_real_funds`
