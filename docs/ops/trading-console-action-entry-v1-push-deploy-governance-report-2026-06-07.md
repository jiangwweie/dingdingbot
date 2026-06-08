# Trading Console Action Entry v1 Push/Deploy Governance Report - 2026-06-07

> [!IMPORTANT]
> 2026-06-08 scope note:
> This deploy report verifies Action Entry v1's disabled action state for that
> release. It does not define the whole product as read-only. Current product
> authority is `docs/ops/knowledge-pack/CURRENT_PRODUCT_OPERATING_MODEL.md`.

## Verdict

PASS_WITH_CONSTRAINT

Trading Console Action Entry v1 was pushed and deployed to Tokyo through a clean
release. Backend health passed, frontend static assets were refreshed, and
read-only smoke verified the Action Entry readiness contract and disabled action
state. No unauditable live action occurred.

Constraint: full authenticated browser interaction was not completed because no
operator browser session was available during this governance run. The deployed
route, auth guard, OpenAPI contract, service read model, and frontend static
bundle were verified.

## Pushed Commits

- `fb46d0fc feat(trading-console): add action entry readiness view`
- `ec79fb61 fix(trading-console): show action entry evidence summary`

Push:

- branch: `dev`
- remote: `origin/dev`
- before: `7f9df07f`
- after: `ec79fb61`
- force push: no

## Local Pre-push Verification

- `python3 -m pytest -q tests/unit/test_trading_console_readmodels.py tests/unit/test_production_strategy_family_admission.py` - PASS, 25 passed
- `npm run lint` in `trading-console` - PASS
- `npm run build` in `trading-console` - PASS
- `python3 -m py_compile src/interfaces/api_trading_console.py src/application/readmodels/trading_console.py` - PASS
- `python3 -m alembic heads` - PASS, `042 (head)`
- `git diff --check` - PASS
- `git diff origin/dev..HEAD --check` - PASS before push
- secret/action-enable scan - PASS

Secret scan note: the broad scan matched only fixed unit-test auth env variable
names and test TOTP fixture values in `tests/unit/test_trading_console_readmodels.py`.
The non-test staged diff had no secret-like matches.

## Clean Release

Release path:

`/home/ubuntu/brc-deploy/releases/brc-action-entry-v1-ec79fb61-20260607`

Release source:

- created on Tokyo using `git clone`
- checkout: `ec79fb61848c5d20031906edf14bdd8c19d53c00`
- release tree status: clean
- metadata:
  `/home/ubuntu/brc-deploy/reports/trading-console-action-entry-v1-deploy-20260607/release-metadata-ec79fb61.json`

Release checks:

- `python -m compileall -q src` - PASS
- `python -m py_compile src/interfaces/api_trading_console.py src/application/readmodels/trading_console.py` - PASS
- `python -m alembic heads` - PASS, `042 (head)`

## Deploy

Frontend:

- previous `/var/www/brc-owner-console` was backed up under:
  `/home/ubuntu/brc-deploy/reports/trading-console-action-entry-v1-deploy-20260607/frontend-backup-*`
- local `trading-console/dist/` was synced to `/var/www/brc-owner-console`
- deployed frontend assets include `assets/index-T8BdzPS_.js`

Backend:

- pre-deploy no-exposure check passed
- `app/current` was atomically repointed to:
  `/home/ubuntu/brc-deploy/releases/brc-action-entry-v1-ec79fb61-20260607`
- service restarted with non-interactive sudo
- active PID cwd after restart:
  `/home/ubuntu/brc-deploy/releases/brc-action-entry-v1-ec79fb61-20260607`

Service health:

```json
{"status":"ok","service":"brc_operator_console","runtime_bound":true,"live_ready":false}
```

## No-exposure Evidence

Pre-deploy evidence:

`/home/ubuntu/brc-deploy/reports/trading-console-action-entry-v1-deploy-20260607/pre-deploy-no-exposure.json`

Post-restart evidence:

`/home/ubuntu/brc-deploy/reports/trading-console-action-entry-v1-deploy-20260607/post-restart-no-exposure.json`

Summary:

| Phase | Symbol | PG Open Orders | PG Active Positions | Exchange Positions | Exchange Open Orders | Exchange Stop Orders |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| pre-deploy | `BNB/USDT:USDT` | 0 | 0 | 0 | 0 | 0 |
| pre-deploy | `SOL/USDT:USDT` | 0 | 0 | 0 | 0 | 0 |
| post-restart | `BNB/USDT:USDT` | 0 | 0 | 0 | 0 | 0 |
| post-restart | `SOL/USDT:USDT` | 0 | 0 | 0 | 0 | 0 |

Exchange key permission preflight in the read-only smoke reported reading and
futures enabled, withdraw disabled, and IP restriction enabled.

## Action Entry Smoke

HTTP:

- `/api/health` on `127.0.0.1:18080` - `200`
- `/api/trading-console/action-entry-readiness?...` without login - `401`, expected auth guard
- `/action-entry` through nginx - `200`

OpenAPI:

- `GET /api/trading-console/action-entry-readiness` exposes:
  `market_regime`, `symbol_preference`, `risk_tier`, `note`, `family`,
  `strategy_family_id`, `carrier_id`, `symbol`, `side`, `quantity`,
  `max_notional`, `leverage`, `max_attempts`, `protection_mode`,
  `review_requirement`

Service read-model smoke:

- `read_model=action_entry_readiness`
- Owner market input `regime=trend`
- selected candidate family `Trend`
- exact scope review `matched`
- weak strategy evidence policy `warning_not_hard_blocker`
- `authorization_draft_path.creates_authorization=false`
- `final_gate_result.may_execute_live=false`
- `action_state.enabled=false`
- `action_state.places_order=false`
- post-action summary includes `intents`, `entry_orders`, `tp_sl_orders`,
  `reviews`, and `audit_events`

Frontend static smoke:

- deployed JS contains current Action Entry Owner-view labels:
  `行动入口`, `Owner 行情输入`, `风险复核`, `授权草案路径`, `最终门禁`,
  `Post-action 状态`, `执行意图`, `TP/SL`, `Raw / Debug`

## BlockerRecord

```json
{
  "id": "TC-ACTION-ENTRY-AUTH-BROWSER-SMOKE-20260607",
  "stage": "authenticated_browser_smoke",
  "path": "Tokyo /action-entry",
  "evidence": "Route returns index.html and backend API enforces 401 without operator login. No authenticated browser session was available in this governance run.",
  "severity": "constraint",
  "bridge": "Verified nginx route, OpenAPI query contract, backend service read-model output, disabled action state, frontend static bundle labels, and post-restart no-exposure evidence.",
  "retry_condition": "Use an authenticated Operator browser session against Tokyo and capture the Action Entry page after login."
}
```

## Safety Proof

- No new strategy action was started.
- No live order was placed.
- No cancel, replace, flatten, retry protection, or auto-execution was
  performed.
- No Trading Console POST/action endpoint was added.
- Action Entry smoke kept `action_state.enabled=false`,
  `may_execute_live=false`, and `places_order=false`.
- Service restart occurred only after BNB/SOL no-exposure proof.
- Post-restart BNB/SOL no-exposure proof passed.
- No credential values were printed, committed, or pushed.

## Push Status

Pushed to `origin/dev`. No force push.
