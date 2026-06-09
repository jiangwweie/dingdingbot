> [!NOTE]
> **HISTORICAL_EVIDENCE** — This document is a historical operational, governance, sprint, product, or live-trial artifact from an earlier project phase.
>
> It may be useful for context, auditing, or traceability, but it does **not** represent current project state, constraints, product direction, or agent instructions.
>
> Current authoritative sources:
> - `docs/canon/PROJECT_BASELINE_CURRENT.md`
> - `docs/canon/BRC_TARGET_SEMANTICS.md`
> - `docs/canon/AGENT_WORKSPACE_RULES.md`
> - `docs/canon/RUNTIME_SAFETY_BOUNDARY.md`
> - `docs/canon/TECH_DEBT_BASELINE.md`
> - `docs/canon/DOCUMENT_GOVERNANCE.md`

# Trading Console Owner Action Flow v1 Deploy Governance Report - 2026-06-07

> [!IMPORTANT]
> 2026-06-08 scope note:
> This deploy report verifies Owner Action Flow v1's disabled action state for
> that release. It does not define the whole product as read-only. Current
> product authority is `docs/ops/knowledge-pack/CURRENT_PRODUCT_OPERATING_MODEL.md`.

## Verdict

PASS_WITH_CONSTRAINT.

Owner Action Flow v1 was pushed and deployed to Tokyo through a clean release.
Authenticated browser smoke was completed after Owner opened an authenticated
Operator session. API route presence, auth guard behavior, service health,
deployed asset content, no-exposure checks, and Owner-facing page rendering were
verified.

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

Authenticated browser smoke:

- Chrome tab: `http://43.133.176.150/action-entry`
- Authenticated Operator indicator: `登录：jiangwei`
- Page title: `Owner Action Flow`
- Header state: `只读`, `环境：实盘只读`, `部分同步`
- Candidate cards visible:
  - `TF-001-live-readonly-v0` - Registry supported
  - `VB-001-live-readonly-v0` - Registry unsupported
  - `MR-001-live-readonly-v0` - Registry unsupported
- Mean Reversion proposal selection rendered:
  - regime: `mean_reversion`
  - carrier: `MR-001-live-readonly-v0`
  - symbol: `ETH/USDT:USDT`
  - side: `long`
  - quantity: `0.01`
  - max notional: `20`
  - leverage: `1`
  - protection: `single_tp_plus_sl`
- Action state: disabled, `proposal_only`; no enabled execute,
  authorization-create, cancel, flatten, or retry action was present.
- Post-action evidence summary was visible with historical intent, entry,
  TP/SL, review, and audit sections.

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

No active blocker remains for Owner Action Flow v1 authenticated browser smoke.
The earlier authenticated-session blocker was cleared after Owner logged in and
the deployed `/action-entry` page was verified in Chrome.

## Safety Proof

- No live action was started.
- No Trading Console POST/action endpoint was added.
- No cancel, replace, flatten, or retry-protection product action was enabled.
- `live_ready=false`.
- BNB/SOL/ETH exposure and open-order counts were zero before and after restart.
- Mean Reversion remains proposal-only and not action-registry-supported.
- Action buttons remain backend-driven and disabled unless official backend
  actionability flags are true.
