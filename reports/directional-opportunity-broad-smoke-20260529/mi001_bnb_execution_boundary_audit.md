# MI-001 BNB Execution / Order Boundary Audit

Generated: 2026-05-31

## 1. Summary

This audit checks whether the current MI-001 BNB observation / case queue / readiness-gap chain touches execution or order paths.

Conclusion: current BNB chain is read-only review/design. It does not create execution intents, place/cancel orders, grant execution permission, start runtime, or modify exchange gateway.

## 2. Concrete Code Paths

| boundary | code_path | current_assessment | BNB chain touches path | required_control |
| --- | --- | --- | --- | --- |
| Observation signal evaluator | `src/application/strategy_group_live_readonly_observation.py` | Produces `no_action` / `would_enter` / `invalid` observe-only records. | yes | Keep `would_enter` as review signal only. |
| Observation case queue | `src/application/strategy_group_observation_case_queue.py` | Promotes `would_enter` rows into Owner review cases. | yes | Never convert case item to intent/order. |
| BNB readiness gap API | `src/application/mi001_bnb_trial_readiness_gap.py`; `src/interfaces/api_brc_console.py` | Read-only review map. | yes | Display only; no state mutation. |
| Execution permission resolver | `src/application/execution_permission.py` | Exists and defaults to read-only unless contributors allow more. | no | Future rehearsal needs separate resolver pass. |
| ExecutionIntent repository | `src/infrastructure/pg_execution_intent_repository.py`; `src/domain/execution_intent.py` | Exists for execution intent persistence. | no | Separate Owner authorization required before use. |
| Order lifecycle | `src/application/order_lifecycle_service.py` | Order lifecycle path exists. | no | Forbidden for this BNB readiness task. |
| Order repository | `src/infrastructure/pg_order_repository.py`; `src/infrastructure/order_repository.py` | Order persistence exists. | no | Only read for active/open-order checks in future preflight. |
| Exchange gateway | `src/infrastructure/exchange_gateway.py` | Order/account gateway exists. | no | Not modified; future testnet/live use needs separate authorization. |
| Runtime control | `src/interfaces/api_console_runtime.py` | Startup guard/GKS/runtime controls exist. | no | Guard/GKS checks must be explicit and scoped. |

## 3. Current API / Service Reachability

- `GET /api/brc/strategy-groups/live-readonly-observation/v1`: observation preview/history, no execution/order.
- `GET /api/brc/strategy-groups/observation-cases/v1`: Owner review queue, no execution/order.
- `GET /api/brc/readiness/mi001-bnb/trial-gap`: readiness gap map, no execution/order.
- Existing order/runtime endpoints are separate surfaces and are not called by the BNB observation/case/readiness flow.

## 4. Boundary Risks

- Testnet scripts and runtime control endpoints exist; they must not be invoked by a readiness review.
- ExecutionIntent and order repositories exist; readiness artifacts must not import or call them.
- `would_enter` naming can be misunderstood; UI/API must keep non-permission flags visible.

## 5. Non-permissions

- no trial start
- no execution intent
- no order
- no order permission
- no execution permission
- no runtime start
- no exchange gateway modification
