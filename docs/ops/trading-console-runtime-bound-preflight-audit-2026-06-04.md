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

# Trading Console Runtime-Bound Preflight Audit

Date: 2026-06-04

Scope: server Trading Console full-runtime readiness after authenticated
frontend/API-only acceptance.

Verdict: RUNTIME_BOUND_ISOLATED_PROBE_PASS_PRODUCTION_SWITCH_NOT_DONE

## Current State

- Server frontend is deployed and authenticated browser validation passed.
- Server backend service remains API-only:
  - entrypoint: `src.interfaces.api:app`
  - `/api/health.runtime_bound=false`
  - `/api/health.live_ready=false`
- Full runtime probe on isolated port `18082` now reaches API health with:
  - `runtime_bound=true`
  - `live_ready=false`
- Tokyo PG `runtime_profiles` table exists and has:
  - `count=1`
  - `active_count=1`
  - active profile `prelive_bnb_readonly_runtime`
- Production backend service remains API-only and has not been switched to
  `python -m src.main`.

## Runtime Profile Table Evidence

Tokyo PG `runtime_profiles` schema is present:

- columns:
  - `name`
  - `description`
  - `profile_payload`
  - `is_active`
  - `is_readonly`
  - `created_at`
  - `updated_at`
  - `version`
- primary key:
  - `runtime_profiles_pkey` on `name`
- indexes:
  - `idx_runtime_profiles_active`
  - `idx_runtime_profiles_updated_at`

Profile row `prelive_bnb_readonly_runtime` was inserted/activated during this
audit under explicit Owner approval. Evidence path on Tokyo:

`/home/ubuntu/brc-deploy/reports/trading-console-runtime-bound-20260604/runtime-profile-seed-evidence-prelive_bnb_readonly_runtime.json`

## Candidate Payload Dry-Run

Existing local source payload:

- `scripts/seed_strategy_trial_bnb_profile.py`
- constant: `BNB_STRATEGY_TRIAL_PROFILE`

The existing script is a testnet/inactive profile seed by design:

- profile name: `strategy_trial_bnb_testnet_runtime`
- `is_active=false`
- `is_readonly=true`
- `brc.non_permissions.live_ready=false`
- `brc.non_permissions.auto_execution_ready=false`

A local in-memory resolver dry-run validated the same BNB payload under a
candidate live read-only profile name:

- dry-run/apply tool: `scripts/seed_prelive_bnb_readonly_profile.py`
- candidate profile name: `prelive_bnb_readonly_runtime`
- profile state used by dry-run: `is_active=true`, `is_readonly=true`
- env used by dry-run:
  - `APP_ENV=production`
  - `TRADING_ENV=live`
  - `EXCHANGE_TESTNET=false`
  - `BRC_EXECUTION_PERMISSION_MAX=read_only`
  - `RUNTIME_PROFILE` unset
- resolver: `RuntimeConfigResolver.resolve_startup()`
- result: resolver-compatible
- config hash: `754a0e60dba3cfef`

Resolved business scope:

- primary symbol: `BNB/USDT:USDT`
- symbols: `["BNB/USDT:USDT"]`
- allowed directions: `["LONG"]`
- max leverage: `1`
- max total exposure: `10`
- daily max trades: `1`
- BRC fixed cap:
  - amount: `0.01`
  - max notional: `20`
  - leverage: `1`
- non-permissions:
  - `live_ready=false`
  - `auto_execution_ready=false`
  - `no_arbitrary_symbol=true`
  - `no_arbitrary_side=true`
  - `no_arbitrary_leverage=true`

The candidate was first validated by dry-run, then seeded under explicit Owner
approval. It did not grant order permission, runtime control API, test signal
injection, live readiness, or auto-execution.

## Tooling Prepared

Prepared tool:

- `scripts/seed_prelive_bnb_readonly_profile.py`
- `scripts/inspect_runtime_profiles_readonly.py`
- `scripts/probe_runtime_bound_readonly.py`

Prepared runbook:

- `docs/ops/trading-console-runtime-bound-transition-runbook-2026-06-04.md`

Default behavior:

- prints the candidate profile summary;
- prints SQL-like runtime profile metadata;
- exits without PG mutation.

APPLY guard requires all of the following:

- `APPLY=true`
- `OWNER_APPROVED_RUNTIME_PROFILE_SEED=prelive_bnb_readonly_runtime`
- `TRADING_ENV=live`
- `EXCHANGE_TESTNET=false`
- `BRC_EXECUTION_PERMISSION_MAX=read_only`
- `RUNTIME_CONTROL_API_ENABLED=false`
- `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=false`
- `CORE_EXECUTION_INTENT_BACKEND=postgres`
- `CORE_ORDER_BACKEND=postgres`
- `CORE_POSITION_BACKEND=postgres`
- `PG_DATABASE_URL` set
- `RUNTIME_PROFILE` unset

Additional mutation guards:

- refuses to replace a different active runtime profile;
- refuses to update an existing readonly profile unless
  `OWNER_APPROVED_RUNTIME_PROFILE_UPDATE=prelive_bnb_readonly_runtime` is set.
- when APPLY succeeds, writes pre/post seed evidence to
  `RUNTIME_PROFILE_SEED_EVIDENCE_PATH` or a default
  `reports/runtime-profile-seed-evidence-prelive_bnb_readonly_runtime-*.json`
  path;
- evidence contains before/after read-only runtime profile summaries and omits
  full `profile_payload`.

Runtime-bound probe guard:

- `scripts/probe_runtime_bound_readonly.py` is dry-run by default;
- real probe requires `RUN_RUNTIME_PROBE=true`;
- real probe still requires:
  - exactly one active PG runtime profile;
  - `BRC_EXECUTION_PERMISSION_MAX=read_only`;
  - `RUNTIME_CONTROL_API_ENABLED=false`;
  - `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=false`;
  - `RUNTIME_PROFILE` unset;
  - isolated `BACKEND_PORT` derived from `RUNTIME_PROBE_PORT`, default `18082`;
- the probe starts `python -m src.main` only after guards pass and terminates
  the child process after health inspection.

Validation:

- `python3 scripts/seed_prelive_bnb_readonly_profile.py`
  - dry-run passed;
  - printed `No PG mutation performed`;
  - config hash: `754a0e60dba3cfef`.
- `PYTHONPATH=$PWD python /tmp/inspect_runtime_profiles_readonly.py` on Tokyo
  from `/home/ubuntu/brc-deploy/app/current` with `live-readonly.env`
  - read-only PG inspection passed;
  - full `profile_payload` omitted;
  - pre-seed: `runtime_profiles_exists=true`, `count=0`, `active_count=0`,
    `profiles=[]`;
  - post-seed: `runtime_profiles_exists=true`, `count=1`, `active_count=1`,
    active profile `prelive_bnb_readonly_runtime`.
- `python3 scripts/probe_runtime_bound_readonly.py`
  - local dry-run passed;
  - printed `DRY RUN - no runtime process started`.
- `PYTHONPATH=$PWD python /tmp/probe_runtime_bound_readonly.py` on Tokyo from
  `/home/ubuntu/brc-deploy/app/current` with `live-readonly.env`
  - dry-run passed;
  - printed `DRY RUN - no runtime process started`;
  - plan entrypoint: `python -m src.main`;
  - plan health URL: `http://127.0.0.1:18082/api/health`.
- `RUN_RUNTIME_PROBE=true RUNTIME_PROBE_PORT=18082 PYTHONPATH=/tmp:$PWD python /tmp/scripts/probe_runtime_bound_readonly.py` on Tokyo
  - run passed after process-only placeholder
    `FEISHU_WEBHOOK_URL=https://example.invalid/webhook`;
  - result: `health_ready`;
  - health: `runtime_bound=true`, `live_ready=false`;
  - runtime profile: `prelive_bnb_readonly_runtime`;
  - temp runtime process was terminated after evidence capture.
- `python3 -m pytest -q tests/unit/test_strategy_trial_bnb_profile_seed.py tests/unit/test_environment_contract.py`
  - 32 passed.
- `python3 -m py_compile scripts/seed_prelive_bnb_readonly_profile.py scripts/inspect_runtime_profiles_readonly.py scripts/probe_runtime_bound_readonly.py`
  - passed.

## Required Before Runtime-Bound Switch

The following must be completed before switching production from API-only to
runtime-bound:

1. Production env handling for required full-runtime startup variables,
   especially `FEISHU_WEBHOOK_URL`, without exposing or changing unrelated
   credentials.
2. Confirmation that production env keeps:
   - `RUNTIME_PROFILE` unset
   - `BRC_EXECUTION_PERMISSION_MAX=read_only` unless separately authorized
   - `RUNTIME_CONTROL_API_ENABLED=false`
   - `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=false`
3. Production service switch only after isolated runtime health proves:
   - API binds successfully
   - `runtime_bound=true`
   - no action endpoint is enabled unless separately authorized
   - trading-console GET endpoints still return 200
4. Runtime read-model schema gap review:
   - Tokyo `positions` table currently has `current_qty`, not `quantity`;
   - runtime periodic reconciliation logs `UndefinedColumnError:
     positions.quantity`.
5. Final-gate blockers must be handled through approved safety workflow before
   any live action:
   - GKS active/fail-closed;
   - startup guard absent in production API-only context;
   - BNB PG/exchange reconciliation mismatch.

## Stop Conditions

Stop before mutation if any of these are true:

- proposed profile differs from the approved BNB-only symbol/side/leverage
  scope;
- profile grants order permission or auto-execution by metadata;
- env requires `RUNTIME_PROFILE` to select live scope;
- active PG profile already exists and is not explicitly reviewed;
- full runtime attempts to start with action permission above `read_only`;
- any live order, cancel, flatten, replace, retry protection, or auto-execution
  would be required to continue.

## Safety Proof

- No live order was placed.
- No cancel, replace, flatten, retry protection, or auto-execution was executed.
- No credentials were read into reports.
- One Owner-approved PG profile row was inserted/activated:
  `prelive_bnb_readonly_runtime`.
- Candidate validation used an in-memory repository and dummy secrets.
