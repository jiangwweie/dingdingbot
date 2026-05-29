# Trial Start Facts Collection Result

Generated: 2026-05-29

Scope: `MI-001 SOL/USDT:USDT long` trial start readiness facts collection.

This report is a review artifact only. It does not authorize trial start, execution permission, order placement, runtime start, or exchange API access.

## 1. Summary

Collected the safe facts available for the existing PG-backed `MI-001 SOL/USDT:USDT long` trial start checklist evaluation.

Result: the checklist remains blocked.

No fresh cached account facts were read because the only visible runtime account snapshot helper reads through `_exchange_gateway.get_account_snapshot`; this task did not invoke that path under the standalone safety boundary. No Operation Layer runtime preflight or position read was invoked.

## 2. Path Chosen

Path B: update the read-only checklist evaluator and generate a blocked facts report.

Reason:

- PG registration facts are already available.
- The current account facts path visible in the repo is runtime/exchange-gateway adjacent and was not safe to call in this task.
- Operation Layer cap/gate/startup/no-active-position facts were not available through an injected safe read-only provider.
- GKS state semantics are clear from code: `active=True` blocks all new entries.
- Owner trial-start approval is still missing and must remain missing in this task.

## 3. Account Facts

| fact | status | source | blocking | notes |
| --- | --- | --- | --- | --- |
| cached AccountSnapshot exists | unsafe_to_read | runtime_exchange_gateway_cache_path_not_invoked | yes | `_cached_account_equity_snapshot` in `api_brc_console.py` reads via `_exchange_gateway.get_account_snapshot`; not invoked. |
| wallet/account equity | blocked | not_available | yes | No safe cached/local/PG account facts provider was supplied. |
| available margin | blocked | not_available | yes | No safe cached/local/PG account facts provider was supplied. |
| freshness | blocked | not_available | yes | No timestamped cached AccountSnapshot was available. |
| no external exchange call | pass | code path avoided | no | No exchange gateway method was called by this task. |

## 4. Capital Readiness

| field | value |
| --- | --- |
| current_dedicated_subaccount_equity | blocked |
| available_margin | blocked |
| max_leverage | 5 |
| computed_max_notional_candidate | blocked |
| max_total_loss_rule | current_dedicated_subaccount_equity |

Concrete values were not fabricated. The readiness calculation remains blocked until fresh cached account facts are available through a safe read-only source.

## 5. Operation Layer / Safety Facts

| fact | status | blocking | notes |
| --- | --- | --- | --- |
| Operation Layer gate | missing | yes | No safe facts provider supplied; runtime preflight not invoked. |
| Operation Layer notional cap | missing | yes | No safe cap source available in this task path. |
| startup guard | not_checked | yes | Process-local/runtime state was not inspected or mutated. |
| evidence logging | missing | yes | No Operation Layer readiness fact supplied. |
| no active trial position | not_checked | yes | No runtime/position repository was queried. |
| kill switch state | available | no | PG GKS state was available from the previous checklist generation. |

## 6. GKS Interpretation

`active=True` means the Global Kill Switch blocks all new entries.

Checklist consequence:

- This is a safe fail-closed state.
- It does not grant trial start readiness.
- A future trial start would require separate Owner trial-start approval and a separate authorized safety transition.

## 7. Owner Approval

| approval | status | blocking |
| --- | --- | --- |
| Owner plan-preparation approval | available | no |
| Owner trial-start approval | missing | yes |

Owner trial-start approval was not created by this task.

## 8. Checklist Verdict

Final verdict remains:

`blocked_fresh_account_facts_required`

Other unresolved blockers:

- Operation Layer facts required;
- kill/startup safety facts require a safe readiness path;
- no-active-trial-position fact required;
- Owner trial-start approval required.

## 9. Safety Check

| check | answer |
| --- | --- |
| 是否 push？ | no |
| 是否连接交易所？ | no |
| 是否调用真实账户 API？ | no |
| 是否下单？ | no |
| 是否创建 execution intent？ | no |
| 是否触碰 exchange_gateway？ | no |
| 是否触碰 execution/order/live runner？ | no |
| 是否运行 migration upgrade/downgrade？ | no |
| 是否启动 trial？ | no |
| 是否授予 execution permission？ | no |

## 10. Next Recommended Task

Implement a safe PG/local cached account facts read model for trial readiness, separate from runtime/exchange gateway access.
