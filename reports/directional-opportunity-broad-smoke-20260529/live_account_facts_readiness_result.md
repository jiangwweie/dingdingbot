# Live Account Facts Readiness Result

Generated: 2026-05-29

Scope: `MI-001 SOL/USDT:USDT long` trial readiness account facts.

This report is a review artifact only. It is not runtime source of truth and does not authorize trial start.

## 1. Summary

Connected a real read-only Binance USDT futures balance query to the MI-001 SOL trial readiness checklist through a balance-only account facts source.

The read succeeded and supplied account equity, available margin, timestamp/freshness, account type, and read-only boundary evidence. The checklist account-facts blocker is cleared.

No trial was started. No order was created. No execution intent was created. No leverage, transfer, withdrawal, runtime, or live runner path was invoked.

## 2. Path Chosen

Path B: minimal read-only adapter/facade.

Reason:

- The existing `ExchangeGateway` object is mixed read/write and was not used.
- The new source exposes only `fetch_balance` and `close` through a restricted client protocol.
- The checklist generator already accepts an injected account facts source, so no execution/order/runtime integration was needed.

## 3. Account Facts Read Result

| field | value |
| --- | --- |
| method | `BinanceUsdtFuturesAccountFactsSource` via `CcxtBinanceUsdtFuturesBalanceClient.fetch_balance({"type": "future"})` |
| exchange | Binance |
| account type | USDT futures |
| environment | `.env.local`: `TRADING_ENV=live`, `EXCHANGE_TESTNET=false` |
| external_call_performed | yes |
| external_call_type | `read_only_account_query` |
| account_equity source | Binance futures `totalMarginBalance`, fallback to USDT total |
| available_margin source | Binance futures `availableBalance`, fallback to USDT free |
| account_equity | `4661.34666567` |
| available_margin | `3650.39404603` |
| timestamp_ms | `1780060099041` |
| freshness | `fresh` |
| read_only_guarantee | true |
| readiness blockers from account facts | none |

The exchange response did not include a top-level timestamp, so the checklist used the local read timestamp from the successful read-only balance query.

## 4. Checklist Impact

The checklist moved from:

`blocked_fresh_account_facts_required`

to:

`blocked_operation_layer_facts_required`

Account facts are now available and capital readiness can be calculated:

| field | value |
| --- | --- |
| current_dedicated_subaccount_equity | `4661.34666567` |
| available_margin | `3650.39404603` |
| max_leverage | `5` |
| computed_max_notional_candidate | `18251.97023015` |
| max_total_loss_rule | `current_dedicated_subaccount_equity` |

This is a readiness calculation only. It was not persisted as execution config and does not grant permission to trade.

Remaining blockers:

- Operation Layer gate facts missing.
- Operation Layer notional cap facts missing.
- Startup guard state not checked.
- Evidence logging readiness not checked.
- No-active-trial-position fact not checked.
- Owner separate trial-start approval is still missing.
- GKS is readable and currently `active=True`, which means fail-closed for new entries.

## 5. Safety Check

| check | answer |
| --- | --- |
| 是否 push？ | no |
| 是否连接交易所？ | yes |
| 是否调用真实账户 API？ | yes |
| 是否调用真实账户 API 的类型是 read-only？ | yes |
| 是否下单？ | no |
| 是否取消订单？ | no |
| 是否修改杠杆？ | no |
| 是否 set_leverage？ | no |
| 是否转账？ | no |
| 是否提现？ | no |
| 是否创建 execution intent？ | no |
| 是否启动 trial？ | no |
| 是否授予 execution permission？ | no |
| 是否修改 exchange_gateway？ | no |
| 是否触碰 execution/order/live runner？ | no |

## 6. Next Recommended Task

Verify Operation Layer cap / GKS / startup guard facts for MI-001 SOL trial readiness.
