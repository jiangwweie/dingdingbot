# BNB Testnet Runtime Gate Check + Controlled Entry Rehearsal

## 1. Summary

This was a testnet-only runtime gate check and controlled entry rehearsal for `MI-001-BNB-LONG`.

Final state:

- verdict: `testnet_rehearsal_completed`
- live readiness: `not_live_ready`
- auto execution readiness: `not_auto_execution_ready`
- real funds used: no
- secrets printed or committed: no

The controlled BNB testnet entry path reached the exchange and filled the entry order. The rehearsal exposed a real testnet defect: TP1/TP2 protection orders split the 0.01 BNB test size into 0.005 BNB child orders, below Binance BNB futures minimum amount precision. The SL protection order was accepted. A carrier-specific controlled testnet close path was then added and used to close the testnet BNB position and terminalize the SL order.

## 2. Starting State

Recent baseline commits verified:

- `8091635a feat(brc): add strategy trial readiness framework`
- `6e6c92fe feat(brc): collect bnb testnet preflight facts`
- `6462d4bf feat(brc): integrate bnb account facts freshness`
- `997fc90b feat(brc): verify bnb testnet readiness gates`
- `6de9abc7 feat(brc): add bnb strategy trial testnet carrier`
- `b4bddd1e feat(brc): seed bnb strategy trial testnet profile`

Unrelated dirty files were left unstaged.

## 3. Runtime / Environment Verification

| check | result | evidence |
|---|---:|---|
| runtime profile | pass | `strategy_trial_bnb_testnet_runtime` resolved from runtime config |
| profile version/hash | pass | version `2`, hash `b2af305c8c8bf3d7` |
| trading env | pass | `TRADING_ENV=testnet` |
| exchange mode | pass | `EXCHANGE_TESTNET=true` |
| symbol scope | pass | exactly `BNB/USDT:USDT` |
| leverage | pass | runtime profile max leverage `1`; carrier fixed at `1x_testnet_fixed` |
| max notional | pass | carrier cap `20` USDT |
| max amount | pass | carrier amount `0.01` BNB |
| runtime control API | pass | enabled for local testnet control |
| test signal injection | pass | enabled for controlled testnet rehearsal |
| credential handling | pass | testnet credential aliases present; no secret printed or committed |
| live profile selected | pass | no live/mainnet profile selected |

Profile repair applied before runtime start:

- `risk.max_total_exposure` was reduced from `20` to `10` to satisfy existing `RiskConfig` validation.
- The dev PG profile was reapplied as version `2`.

## 4. BNB Gate Check Result

| gate | result | notes |
|---|---:|---|
| carrier allowlisted | pass | `MI-001-BNB-LONG` listed by carrier API |
| wrong carrier rejected | covered by existing route resolution/tests |
| symbol fixed | pass | `BNB/USDT:USDT` only |
| side fixed | pass | long only |
| arbitrary leverage rejected | pass | carrier fixed at `1` |
| live ready | false | API returns `live_ready=false` |
| auto execution ready | false | API returns `auto_execution_ready=false` |
| account facts | pass | runtime cached account facts fresh enough during entry gate |
| GKS | pass | `active=False` |
| startup guard | pass | armed through preflight endpoint on runtime-owned guard |
| inventory before entry | pass | BNB exchange/local inventory flat before entry |
| startup reconciliation before entry | pass | clean summary accepted after field mapping fix |

## 5. Controlled Testnet Entry Rehearsal

Entry path:

- endpoint: `POST /api/dev/testnet/brc/carriers/MI-001-BNB-LONG/execute-controlled-entry`
- carrier: `MI-001-BNB-LONG`
- symbol: `BNB/USDT:USDT`
- side: long
- amount: `0.01` BNB
- profile: `strategy_trial_bnb_testnet_runtime`
- live_ready: false

Observed result:

| item | value |
|---|---|
| execution intent | `intent_ef7d091161b5` |
| signal id | `sig_515a7b05e942` |
| entry local order | `ord_90eaa002` |
| entry exchange order | `1423959960` |
| entry status | `FILLED` |
| fill amount | `0.01` BNB |
| fill price | `705.43` |
| BRC attempt status | `blocked` |
| intent final status | `failed` |

Failure detail:

- TP1 and TP2 order quantities were `0.005` BNB each.
- Binance rejected both child TP orders because the amount was below BNB futures minimum amount precision of `0.01`.
- SL order was accepted initially.
- This is a valid rehearsal defect, not a live failure and not a strategy signal result.

## 6. Cleanup Status

Because the entry had left a testnet position, a carrier-specific controlled close endpoint was added:

- endpoint: `POST /api/dev/testnet/brc/carriers/MI-001-BNB-LONG/execute-controlled-close`
- scope: finite carrier allowlist only
- symbol: fixed to `BNB/USDT:USDT`
- amount upper bound: `0.01` BNB
- profile gate: `strategy_trial_bnb_testnet_runtime`
- close method: existing reduce-only controlled close

Cleanup result:

| item | value |
|---|---|
| close verdict | `testnet_rehearsal_closed` |
| close local order | `exit_controlled_e4c89314c2c5` |
| close exchange order | `1424031109` |
| close status | `FILLED` |
| close amount | `0.01` BNB |
| average close price | `704.44` |
| terminalized protection orders | `1` |
| runtime campaign state | `closed` after position projection flat proof |
| periodic reconciliation after cleanup | consistent |

Final PG readback:

- BNB position `pos_sig_515a7b05e942`: `is_closed=true`, quantity `0`.
- ENTRY order `ord_90eaa002`: `FILLED`.
- EXIT order `exit_controlled_e4c89314c2c5`: `FILLED`.
- SL order `ord_sl_cc95a188`: `CANCELED`.
- TP1/TP2 local orders remain `CREATED` with no exchange order id; they were never submitted to exchange and are not returned by `get_open_orders`.

## 7. Files Changed

- `scripts/seed_strategy_trial_bnb_profile.py`
  - Adjusted seeded testnet profile risk exposure to existing config bounds.
- `src/interfaces/api_brc_console.py`
  - Exposed authenticated dev/testnet carrier list, entry, and close pass-through routes.
- `src/interfaces/api_console_runtime.py`
  - Accepted startup reconciliation summaries that use `failure_count`.
  - Added flat proof metadata for closed-to-observe reset.
  - Added finite carrier controlled close cleanup endpoint.
- `tests/unit/test_brc_controlled_testnet_endpoints.py`
  - Covered reconciliation count mapping, flat-proof reset, carrier close, and blocked-attempt cleanup close.
- `tests/unit/test_brc_execution_bypass_hardening.py`
  - Updated dev/testnet route allowlist for carrier entry/close.
- `tests/unit/test_strategy_trial_bnb_profile_seed.py`
  - Covered adjusted risk exposure.

## 8. Tests / Validation

Executed:

- `python3 -m pytest -q tests/unit/test_brc_controlled_testnet_endpoints.py tests/unit/test_brc_execution_bypass_hardening.py tests/unit/test_strategy_trial_bnb_profile_seed.py`
  - result: `36 passed`

Runtime validation:

- Started local runtime with testnet profile.
- Armed runtime-owned startup guard via preflight endpoint.
- Listed allowlisted BNB carrier through authenticated dev/testnet API.
- Executed controlled BNB testnet entry.
- Executed controlled BNB testnet close cleanup.
- Queried PG positions/orders/events to verify final testnet state.

## 9. Secret Handling

- No API key or secret was printed.
- No secret was written to this report.
- No secret was staged or committed.
- `.env.local` remains local-only and ignored.

## 10. Safety Proof

| safety item | result |
|---|---:|
| live mode used | no |
| real funds used | no |
| live order placed | no |
| testnet order placed | yes, controlled rehearsal only |
| credential changed | no |
| withdrawal/transfer called | no |
| leverage changed | no |
| arbitrary symbol/side allowed | no |
| Operation Layer bypassed | no |
| live execution permission granted | no |
| auto execution enabled | no |
| observation signal converted to live order | no |

## 11. Remaining Issues

1. TP split sizing is invalid for `0.01` BNB:
   - Current 50/50 TP split creates `0.005` BNB child orders, below Binance minimum amount precision.
   - Next implementation should use a single TP for min-size BNB rehearsals or disable TP splitting below symbol amount precision.

2. BRC attempt remains `blocked` after the entry protection failure:
   - This is correct evidence of the failed protection attach path.
   - Cleanup close restored flat inventory, but the attempt is intentionally not rewritten as a successful closed attempt.

3. Two local TP orders remain `CREATED` with no exchange order id:
   - They were not submitted and are not open exchange orders.
   - A future local hygiene task can terminalize unsubmitted protection-order rows after failed protection attach.

## 12. Final State

Final outcome:

```text
testnet_rehearsal_completed
not_live_ready
not_auto_execution_ready
no_real_funds
```

Next recommended task:

```text
Fix BNB min-size protection order design before the next controlled testnet rehearsal.
```
