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

# BRC Push And Clean Release Deploy Governance Report

Date: 2026-06-07

## Verdict

PASS

The local `dev` baseline and approved local-only tags were pushed. Tokyo now
runs from a clean release built from the pushed commit/tag. Post-restart health
and BNB/SOL no-exposure evidence passed. No unauditable live action occurred.

## Pushed Baseline

Branch pushed:

- `dev`: `03a2330f` -> `574bc095`

Pushed tags:

- `brc-trend-action-bridge-20260604-r0 -> 09d56a80`
- `brc-trend-sol-live-governance-20260606-r0 -> 210353b3`
- `brc-trend-sol-full-closure-20260606-r0 -> 4a2819ce`
- `brc-post-close-release-governance-20260606-r0 -> 777b2056`
- `brc-clean-release-push-deploy-governance-20260606-r0 -> 574bc095`

Remote verification:

- `origin/dev`: `574bc095410a0ddfc26770b3ac3bf2e33f19efa7`
- local `HEAD`: `574bc095410a0ddfc26770b3ac3bf2e33f19efa7`
- ahead count after push: `0`
- behind count after push: `0`
- all pushed tags pointed to their expected commits.

Note: a broad `git fetch --tags` hit an unrelated pre-existing local/remote
tag conflict on `v0.3.0-phase3`. This did not affect `origin/dev` or the five
approved BRC tags, which were verified directly.

## Clean Release

Release path:

`/home/ubuntu/brc-deploy/releases/brc-clean-release-574bc095-20260607`

Release source:

- created on Tokyo using `git clone` from origin
- checkout: detached `574bc095410a0ddfc26770b3ac3bf2e33f19efa7`
- tag verified:
  `brc-clean-release-push-deploy-governance-20260606-r0 -> 574bc095410a0ddfc26770b3ac3bf2e33f19efa7`
- release tree status: clean
- metadata:
  `/home/ubuntu/brc-deploy/reports/brc-clean-release-deploy-governance-20260607/release-metadata-574bc095.json`

Static checks in release:

- `/home/ubuntu/brc-deploy/venvs/brc-bnb-prelive-20260601/bin/python -m compileall -q src`: passed
- `/home/ubuntu/brc-deploy/venvs/brc-bnb-prelive-20260601/bin/python -m alembic heads`: `042 (head)`

## Deploy And Restart

Pre-restart:

- no-exposure evidence passed
- `app/current` was atomically repointed to the clean release
- first non-sudo `systemctl restart` attempt failed with interactive
  authentication required
- `sudo -n` was available, so restart proceeded through non-interactive sudo

Post-restart service state:

- service: `brc-owner-console-backend.service`
- status: active
- PID: `2004499`
- active process cwd:
  `/home/ubuntu/brc-deploy/releases/brc-clean-release-574bc095-20260607`
- `app/current`:
  `/home/ubuntu/brc-deploy/releases/brc-clean-release-574bc095-20260607`
- health:

```json
{"status":"ok","service":"brc_operator_console","runtime_bound":true,"live_ready":false}
```

Startup safety signals observed in logs:

- `BRC_EXECUTION_PERMISSION_MAX=read_only`
- startup trading guard not armed
- Global Kill Switch active from PG
- signal executor disabled by BRC execution permission
- startup reconciliation found zero candidate orders and zero recovery tasks
- API key permissions verified with withdraw disabled

## API Smoke

OpenAPI route check:

- `/api/health`: present, GET
- `/api/trading-console/action-entry-readiness`: present, GET
- `/api/trading-console/dashboard-state`: present, GET

HTTP smoke:

- `/api/health`: `200`
- `/api/trading-console/action-entry-readiness`: `401`, expected without
  operator login

The path `/api/trading-console/dashboard` returned `404`; this is not a
contract regression because the actual current route is
`/api/trading-console/dashboard-state`.

## No-Exposure Evidence

Pre-restart evidence:

- server:
  `/home/ubuntu/brc-deploy/reports/brc-clean-release-deploy-governance-20260607/pre-restart-no-exposure.json`
- local:
  `reports/brc-clean-release-deploy-governance-20260607/pre-restart-no-exposure.json`

Post-restart evidence:

- server:
  `/home/ubuntu/brc-deploy/reports/brc-clean-release-deploy-governance-20260607/post-restart-no-exposure.json`
- local:
  `reports/brc-clean-release-deploy-governance-20260607/post-restart-no-exposure.json`

| Phase | Symbol | Exchange Positions | Exchange Open Orders | Exchange Stop Orders | PG Open Orders | PG Active Positions |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| pre-restart | `BNB/USDT:USDT` | 0 | 0 | 0 | 0 | 0 |
| pre-restart | `SOL/USDT:USDT` | 0 | 0 | 0 | 0 | 0 |
| post-restart | `BNB/USDT:USDT` | 0 | 0 | 0 | 0 | 0 |
| post-restart | `SOL/USDT:USDT` | 0 | 0 | 0 | 0 | 0 |

Evidence files remain under `reports/` and are intentionally gitignored.

## Resolved Release Issues

- local push drift resolved: `origin/dev` now includes the pushed baseline.
- approved local-only tags are now on origin.
- `app/current` now points to a clean release.
- active process cwd now matches `app/current`.
- dirty server overlay is no longer the active runtime source.

## Remaining Notes

- Older dirty release directories still exist on disk for history/debug. They
  are not active runtime source.
- The unrelated `v0.3.0-phase3` tag conflict remains a local tag-governance
  cleanup item, not a blocker for this BRC baseline.

## Safety Proof

- No new strategy action was started.
- No order was placed.
- No cancel, replace, flatten, retry protection, or auto-execution was
  performed.
- No PG mutation was performed.
- Service restart occurred only after clean release verification and
  pre-restart no-exposure proof.
- Post-restart no-exposure proof passed.
- No credential values were printed or committed.
