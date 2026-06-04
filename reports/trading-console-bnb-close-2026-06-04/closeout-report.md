# Trading Console BNB Closeout + Protection Health Current-Scope Acceptance Report

Date: 2026-06-04

## Result

PASS_WITH_CONSTRAINT

Frontend documentation and Owner read-only page acceptance can continue for the
post-close state. The BNB live closeout scope is complete because the position
was already flat by TP fill before the closeout action; the only remaining
current-scope live action was canceling the residual SL protection order.

## Authorized Scope

- Symbol: `BNB/USDT:USDT`
- Side: `LONG`
- Quantity: `0.01`
- Max attempts: `1`
- Allowed action in this run: close active BNB position or cancel residual
  current-scope protection if the position is already flat.
- No other symbol, side, leverage, notional, runtime action API, or frontend
  action control was enabled.

## Pre-Action State

Evidence:

- `pre-close-trading-console-snapshot.json`
- Tokyo evidence: `/home/ubuntu/brc-deploy/reports/trading-console-bnb-close-20260604/dry-run.json`

Observed:

- PG positions: `[]`
- Exchange positions: `[]`
- Entry order `d791fbde-8498-4d3c-953f-0060b5f3a018` / exchange
  `91128701174`: `FILLED`, qty `0.01`, avg `592.06`.
- TP order `9f7ad378-16ef-4161-86e1-f94ba79d5ef0` / exchange
  `91128701434`: `FILLED`, qty `0.01`, avg `597.98`.
- SL order `c9a4faae-eaa5-45d1-9606-bb3181e5c644` / exchange
  `4000001479555379`: `OPEN`, qty `0.01`, trigger `586.13`.

Decision:

- No market close was sent because both PG and exchange position reads were
  already flat.
- The only scoped live action required was canceling residual current-scope SL
  protection.

## Live Action Record

Evidence:

- `apply.json`
- Tokyo evidence: `/home/ubuntu/brc-deploy/reports/trading-console-bnb-close-20260604/apply.json`

Action executed:

- `cancel_residual_protection`
- Order: `c9a4faae-eaa5-45d1-9606-bb3181e5c644`
- Exchange order: `4000001479555379`
- Old status: `OPEN`
- New status: `CANCELED`
- Exchange result: `CANCELED`
- Audit row: `audit_19063c96`

Safety flags from evidence:

- `places_market_close=false`
- `cancels_residual_protection=true`
- `other_symbol_allowed=false`
- `other_side_allowed=false`
- `max_attempts=1`

## Post-Action State

Evidence:

- `post-close-trading-console-snapshot.json`
- `post-close-audit-sl-order.json`

Observed:

- Runtime health endpoint: `runtime_bound=true`, `live_ready=false`.
- PG positions: `[]`
- Exchange positions: `[]`
- PG open orders: `[]`
- Exchange open orders: `[]`
- Protection health:
  - `status=unknown` because there is no active position to protect.
  - `tp_count=0`
  - `sl_count=0`
  - `current_scope_active_protection=[]`
  - `historical_protection_orders=8`
  - `orphan_protection_orders=[]`
- Order ledger:
  - `orders=15`
  - `groups=5`
  - Current closeout group contains entry filled, TP filled, SL canceled.
- Direct PG audit proof:
  - `audit_19063c96`, `ORDER_CANCELED`, old `OPEN`, new `CANCELED`,
    trigger `USER`.

Constraint:

- `GET /api/trading-console/audit-chain?order_id=c9a4...` currently returns
  the related orders but `audit_events=[]`; the PG `order_audit_logs` row exists.
  This is a remaining read-model aggregation gap for audit-chain event surfacing,
  not a live-action blocker.

## Protection Health Current-Scope Fix

Backend read model now exposes first-class grouping:

- `current_scope_active_protection`
- `current_scope_protection`
- `historical_protection_orders`
- `orphan_protection_orders`
- `active_position_count`
- `historical_tp_count`
- `historical_sl_count`

Primary `tp_count` and `sl_count` count only current-scope active protection.
Historical BNB rows no longer inflate the active protection card.

Frontend Protection Health now:

- renders current active protection as the primary list;
- shows active count `0` after closeout;
- keeps historical protection records in collapsed `历史保护记录`;
- keeps future handling actions collapsed and disabled.

## Frontend Browser Acceptance

Screenshots:

- `screenshots/dashboard.png`
- `screenshots/account.png`
- `screenshots/ledger.png`
- `screenshots/protection.png`
- `screenshots/carrier.png`
- `screenshots/authorization.png`
- `screenshots/execution.png`
- `screenshots/recovery.png`
- `screenshots/review.png`
- `screenshots/audit.png`

Browser render summary:

- File: `screenshots/browser-render-summary.json`
- All 10 pages rendered without redirecting to login in the temporary
  authenticated browser context.
- Automated visible-text check found no matches for the configured technical
  noise terms:
  - `repository unavailable`
  - `repo_unavailable`
  - `source unavailable`
  - `read_model source`
  - `generated_at_ms`
  - `workflow_run_id`
  - `raw_payload_policy`
  - `API source`
  - `Read Model API 读取失败`
  - `部分 read-model 数据源暂不可用`

Page observations:

- Dashboard: account funds visible, positions `0`, open orders `0`,
  decision text stays Owner-facing.
- Account: real read-only account equity visible, positions empty, protection
  status does not display backend technical reasons.
- Ledger: 15 local BNB historical orders visible, mismatches `0`, orphan
  protection `0`, filters and pagination visible.
- Protection: current active protection quantity `0`; history is collapsed.
- Carrier/Authorization/Execution/Recovery/Review/Audit: action surfaces remain
  disabled/read-only; raw/debug material is not default-expanded.

## Deployment Evidence

- Static frontend root: `/var/www/brc-owner-console`
- Nginx `/api/` proxy: `http://127.0.0.1:18080`
- Backend service: `brc-owner-console-backend.service`, active.
- Static assets deployed after build:
  - `assets/index-COhaxRhe.css`
  - `assets/index-xLONhURl.js`

## Checks Run

- `python3 -m py_compile scripts/owner_authorized_bnb_close.py src/application/readmodels/trading_console.py`
- `python3 -m pytest -q tests/unit/test_trading_console_readmodels.py`
  - 12 passed
- `python3 -m pytest -q tests/unit/test_trading_console_readmodels.py tests/unit/test_tiny001d4_controlled_close.py`
  - 16 passed
- `cd trading-console && npm run lint`
  - passed (`tsc --noEmit`)
- `cd trading-console && npm run build`
  - passed

## Files Changed In This Closeout Scope

- `src/application/readmodels/trading_console.py`
- `trading-console/src/pages/ProtectionHealth.tsx`
- `tests/unit/test_trading_console_readmodels.py`
- `scripts/owner_authorized_bnb_close.py`
- `docs/ops/trading-console-backend-dependency-sync-v0.2.md`
- `reports/trading-console-bnb-close-2026-06-04/*`

## Final Safety Proof

- No broad live action API was added.
- No frontend action button was enabled.
- No PG migration was run.
- No credential or permission change was made.
- No other symbol, side, leverage, or notional was touched.
- The only live exchange mutation was canceling the residual current-scope SL
  order after confirming the BNB position was already flat.
- Runtime remains not live-ready for generic execution.
