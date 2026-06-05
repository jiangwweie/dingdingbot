# Trading Console Runtime-Bound Transition Runbook

Date: 2026-06-04

Status: PREPARED_NOT_EXECUTED

Purpose: provide the controlled command sequence required to move from the
current API-only Trading Console service toward a full runtime-bound validation.

This runbook is not an authorization to execute live orders. It is a staged
runtime metadata and runtime-bound probe procedure. Stop at the first failed
gate.

## Current Baseline

- Server: Tokyo
- Release: `/home/ubuntu/brc-deploy/releases/trading-console-v03-20260604145733`
- Current app path: `/home/ubuntu/brc-deploy/app/current`
- Current production service: `brc-owner-console-backend.service`
- Current production entrypoint: `src.interfaces.api:app`
- Current production port: `127.0.0.1:18080`
- Static root: `/var/www/brc-owner-console`
- Current verdict: `PASS_WITH_CONSTRAINT`

Verified blocker:

- `runtime_profiles` exists in Tokyo PG.
- `count=0`.
- `active_count=0`.
- `profiles=[]`.

Prepared candidate:

- profile name: `prelive_bnb_readonly_runtime`
- config hash: `754a0e60dba3cfef`
- symbol: `BNB/USDT:USDT`
- side: `LONG`
- leverage: `1`
- max total exposure: `10`
- daily max trades: `1`
- action metadata:
  - `live_ready=false`
  - `auto_execution_ready=false`

## Stage 0: Required Approval

Do not continue unless Owner approval explicitly covers this exact metadata
operation:

- PG runtime profile name: `prelive_bnb_readonly_runtime`
- profile hash: `754a0e60dba3cfef`
- profile is active: `true`
- profile is readonly: `true`
- no order permission is granted by this step
- no runtime service switch is included in this seed step
- no live action is included in this seed step

Stop if approval is broader, ambiguous, or changes symbol/side/leverage/notional
scope.

## Stage 1: Pre-Seed Read-Only Inspection

Run from Tokyo:

```bash
cd /home/ubuntu/brc-deploy/app/current
set -a
. /home/ubuntu/brc-deploy/env/live-readonly.env
set +a
PYTHONPATH=$PWD /home/ubuntu/brc-deploy/venvs/brc-bnb-prelive-20260601/bin/python /tmp/inspect_runtime_profiles_readonly.py
```

Expected:

- `runtime_profiles_exists=true`
- `count=0`
- `active_count=0`
- `profiles=[]`
- full `profile_payload` omitted

Stop if:

- an active runtime profile already exists;
- the table is missing;
- the inspection prints full payloads;
- any PG error appears.

## Stage 2: Seed Active Read-Only Profile

Run only after Stage 0 and Stage 1 pass.

```bash
cd /home/ubuntu/brc-deploy/app/current
set -a
. /home/ubuntu/brc-deploy/env/live-readonly.env
set +a
unset RUNTIME_PROFILE
export APPLY=true
export OWNER_APPROVED_RUNTIME_PROFILE_SEED=prelive_bnb_readonly_runtime
export RUNTIME_PROFILE_SEED_EVIDENCE_PATH=/home/ubuntu/brc-deploy/reports/runtime-profile-seed-evidence-prelive_bnb_readonly_runtime-20260604.json
PYTHONPATH=$PWD /home/ubuntu/brc-deploy/venvs/brc-bnb-prelive-20260601/bin/python /tmp/seed_prelive_bnb_readonly_profile.py
```

Expected:

- profile `prelive_bnb_readonly_runtime` seeded successfully
- `active=true`
- `readonly=true`
- `permission grant: none`
- evidence JSON path printed
- evidence safety fields:
  - `profile_payload_omitted=true`
  - `runtime_started=false`
  - `exchange_action_called=false`

Stop if:

- `RUNTIME_PROFILE` is required or set;
- permission cap is not `read_only`;
- runtime control API is enabled;
- test signal injection is enabled;
- existing active profile is not this profile;
- evidence file is not written;
- evidence contains full `profile_payload`.

## Stage 3: Post-Seed Inspection

Run:

```bash
cd /home/ubuntu/brc-deploy/app/current
set -a
. /home/ubuntu/brc-deploy/env/live-readonly.env
set +a
PYTHONPATH=$PWD /home/ubuntu/brc-deploy/venvs/brc-bnb-prelive-20260601/bin/python /tmp/inspect_runtime_profiles_readonly.py
```

Expected:

- `count=1`
- `active_count=1`
- `profiles[0].name=prelive_bnb_readonly_runtime`
- `profiles[0].is_active=true`
- `profiles[0].is_readonly=true`
- safe payload summary shows:
  - `primary_symbol=BNB/USDT:USDT`
  - `allowed_directions=["LONG"]`
  - `max_leverage=1`
  - `max_total_exposure=10`

Stop if any value differs.

## Stage 4: Isolated Runtime-Bound Probe

Run only after Stage 3 passes.

```bash
cd /home/ubuntu/brc-deploy/app/current
set -a
. /home/ubuntu/brc-deploy/env/live-readonly.env
set +a
unset RUNTIME_PROFILE
export RUN_RUNTIME_PROBE=true
export RUNTIME_PROBE_PORT=18082
export RUNTIME_PROBE_TIMEOUT_SECONDS=45
PYTHONPATH=$PWD /home/ubuntu/brc-deploy/venvs/brc-bnb-prelive-20260601/bin/python /tmp/probe_runtime_bound_readonly.py
```

Expected:

- exactly one active PG runtime profile is detected;
- child process starts `python -m src.main`;
- health endpoint returns HTTP 200 on `127.0.0.1:18082`;
- health payload shows runtime-bound service state;
- child process is terminated after inspection.

Stop if:

- probe needs action permission above `read_only`;
- probe enables runtime control or test signal injection;
- health never becomes ready;
- child process logs exchange action attempts;
- child process remains running after probe.

## Stage 5: Production Runtime-Bound Switch Gate

Do not switch production service unless Stage 4 passes.

Before switching, record:

- current unit file or override;
- current service status;
- current `/api/health`;
- rollback command.

Minimum success criteria after switch:

- production `/api/health` returns HTTP 200;
- production reports runtime-bound state;
- `/api/trading-console/*` GET endpoints return 200;
- Trading Console browser scan passes;
- POST/action probes still return 405 unless a separate action scope is
  explicitly approved.

Stop and rollback if any minimum criterion fails.

## Stage 6: Frontend/API Revalidation

Repeat the existing authenticated checks:

- logged-in browser validation across all Trading Console pages;
- API validation for all `/api/trading-console/*` GET endpoints;
- POST/action absence probes;
- ordinary-page technical noise scan;
- enabled real action control scan.

Expected:

- all pages visible;
- GET endpoints 200;
- no old API truth source;
- no enabled real action control unless separately approved;
- Owner-facing pages remain productized.

## Stage 7: Real Action Gate

This runbook does not authorize real action execution.

If action verification remains in scope, create a separate action-specific
approval with:

- exact symbol;
- exact side;
- exact leverage;
- exact notional or amount;
- permitted action set;
- pre/post order, position, protection, review, and audit evidence;
- rollback/stop criteria.

Stop if any action scope is ambiguous.

## Safety Summary

Prepared but not executed in the current acceptance run:

- PG runtime profile seed APPLY.
- Runtime probe run mode.
- Production runtime-bound service switch.
- Any live trading action.

Already executed safely:

- dry-run profile seed;
- read-only runtime profile inspection;
- dry-run runtime-bound probe plan;
- frontend/API read-only validation.
