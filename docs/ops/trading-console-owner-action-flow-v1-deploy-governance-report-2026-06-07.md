# Trading Console Owner Action Flow v1 Deploy Governance Report - 2026-06-07

## Verdict

PASS_WITH_CONSTRAINT.

Owner Action Flow v1 was pushed and deployed to Tokyo through a clean release.
The authenticated browser smoke remains blocked by absence of a reusable
authenticated Operator browser session in this Codex context; API route presence,
auth guard behavior, service health, deployed asset content, and no-exposure
checks were verified.

## Git

- Branch: `dev`
- Commit deployed: `3bbf46ec feat(trading-console): add owner action flow`
- Push: yes, `origin/dev`
- Force push: no

## Release

- Release path:
  `/home/ubuntu/brc-deploy/releases/trading-console-owner-action-flow-v1-3bbf46ec-20260607`
- `app/current`:
  `/home/ubuntu/brc-deploy/releases/trading-console-owner-action-flow-v1-3bbf46ec-20260607`
- Service: `brc-owner-console-backend.service`
- Active PID cwd:
  `/home/ubuntu/brc-deploy/releases/trading-console-owner-action-flow-v1-3bbf46ec-20260607`
- Frontend backup:
  `/home/ubuntu/brc-deploy/reports/trading-console-owner-action-flow-v1-20260607/frontend-backup-20260607215348`
- Release metadata:
  `/home/ubuntu/brc-deploy/reports/trading-console-owner-action-flow-v1-20260607/release-metadata-3bbf46ec.json`

## Service State

Health:

```json
{"status":"ok","service":"brc_operator_console","runtime_bound":true,"live_ready":false}
```

HTTP / route checks:

- `GET /action-entry` through nginx: `200`
- deployed JS asset `assets/index-B0nu_hzO.js`: `200`
- deployed JS contains `Owner Action Flow`
- OpenAPI contains `/api/trading-console/owner-action-flow`
- unauthenticated `GET /api/trading-console/owner-action-flow`: `401`
  `Operator login required`

## No-Exposure Evidence

Pre-deploy:

`/home/ubuntu/brc-deploy/reports/trading-console-owner-action-flow-v1-20260607/pre-deploy-no-exposure.json`

Post-restart:

`/home/ubuntu/brc-deploy/reports/trading-console-owner-action-flow-v1-20260607/post-restart-no-exposure.json`

Summary:

| Phase | Symbol | PG Open Orders | PG Active Positions | Exchange Positions | Exchange Open Orders | Exchange Stop Orders |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| pre-deploy | `BNB/USDT:USDT` | 0 | 0 | 0 | 0 | 0 |
| pre-deploy | `SOL/USDT:USDT` | 0 | 0 | 0 | 0 | 0 |
| pre-deploy | `ETH/USDT:USDT` | 0 | 0 | 0 | 0 | 0 |
| post-restart | `BNB/USDT:USDT` | 0 | 0 | 0 | 0 | 0 |
| post-restart | `SOL/USDT:USDT` | 0 | 0 | 0 | 0 | 0 |
| post-restart | `ETH/USDT:USDT` | 0 | 0 | 0 | 0 | 0 |

## Verification

Local:

- `python3 -m py_compile src/application/production_strategy_family_admission.py src/application/readmodels/trading_console.py src/interfaces/api_trading_console.py` - PASS
- `python3 -m pytest -q tests/unit/test_production_strategy_family_admission.py tests/unit/test_trading_console_readmodels.py` - PASS, 26 passed
- `python3 -m pytest -q tests/unit/test_production_strategy_family_admission.py tests/unit/test_trading_console_readmodels.py tests/unit/test_owner_trial_flow.py -k "final_gate or bnb_final_gate or trend or retry"` - PASS, 38 selected passed
- `npm run lint` - PASS
- `npm run build` - PASS
- `python3 -m alembic heads` - PASS, `042 (head)`
- `git diff --check` - PASS
- staged secret/action-enable scan - PASS

Tokyo release:

- release HEAD verified as `3bbf46ec`
- release `py_compile` for touched backend modules - PASS
- release Alembic heads - PASS, `042 (head)`

## Blocker Record

```json
{
  "id": "TC-OWNER-ACTION-FLOW-AUTH-BROWSER-SMOKE-20260607",
  "stage": "AuthenticatedBrowserSmoke",
  "path": "Trading Console /action-entry -> authenticated Operator session",
  "evidence": "No reusable authenticated Operator browser session was available in this Codex context. Deployed route and unauthenticated auth guard were verified.",
  "severity": "blocker_for_browser_smoke_only",
  "bridge": "API route presence, nginx route, deployed JS label, auth guard, and no-exposure evidence were verified.",
  "retry_condition": "Open an authenticated Operator browser session against Tokyo and verify /action-entry renders Owner Action Flow with no unsafe action enabled."
}
```

## Safety Proof

- No live action was started.
- No Trading Console POST/action endpoint was added.
- No cancel, replace, flatten, or retry-protection product action was enabled.
- `live_ready=false`.
- BNB/SOL/ETH exposure and open-order counts were zero before and after restart.
- Mean Reversion remains proposal-only and not action-registry-supported.
- Action buttons remain backend-driven and disabled unless official backend
  actionability flags are true.
