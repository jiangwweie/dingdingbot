> [!NOTE]
> **HISTORICAL_EVIDENCE** — This document is a historical roadmap, readiness, rehearsal, safety, or phase artifact from an earlier project phase.
>
> It may be useful for context, auditing, or traceability, but it does **not** represent current project state, constraints, product direction, or agent instructions.
>
> Current authoritative sources:
>
> * `docs/canon/PROJECT_BASELINE_CURRENT.md`
> * `docs/canon/BRC_TARGET_SEMANTICS.md`
> * `docs/canon/AGENT_WORKSPACE_RULES.md`
> * `docs/canon/RUNTIME_SAFETY_BOUNDARY.md`
> * `docs/canon/TECH_DEBT_BASELINE.md`
> * `docs/canon/DOCUMENT_GOVERNANCE.md`

# Live-safe v1 Progress

Use this file for session progress and handoff notes.

## 2026-06-13 (RTF-035 Non-runtime Signal Runtime Profile Proposal Local Proof)

- Confirmed current mainline workspace and branch before implementation:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - starting HEAD: `46d79ee4`.
- Added a non-executing profile proposal bridge:
  - `scripts/runtime_non_runtime_signal_profile_proposal.py`;
  - consumes an RTF-034 selector report;
  - selects one `non_runtime_would_enter_signal`;
  - builds the existing `ExperimentalRuntimeProfileProposal`;
  - emits a review packet for Owner/Codex profile decision.
- Local proof used the RTF-034 Tokyo selector report:
  - input report: `output/rtf034-tokyo/runtime-live-signal-selector.json`;
  - output report: `output/rtf035-non-runtime-signal-profile-proposal.json`;
  - source signal: `RBR-001 / RBR-001-v0 / ADA/USDT:USDT / short`;
  - packet status: `ready_for_owner_runtime_profile_decision`;
  - proposal status: `ready_for_owner_codex_confirmation`.
- Proposed runtime boundary preview:
  - profile kind: `small_capital_conservative_short`;
  - capital base: `30`;
  - total loss budget: `6.00`;
  - max loss per attempt: `2.00`;
  - max notional per attempt: `8.00`;
  - max attempts: `3`;
  - max active positions: `1`;
  - max leverage: `1`;
  - allowed symbols: `ADA/USDT:USDT`;
  - allowed sides: `short`;
  - protection required: `true`;
  - review required: `true`;
  - min liquidation stop buffer: `25`.
- Warnings carried by the proposal:
  - `reference_implementation_not_proven_production_strategy`;
  - `strategy_not_proven_alpha_limits_budget_and_autonomy`;
  - `mean_reversion_profile_needs_tighter_attempt_review`;
  - `proposal_is_not_runtime_creation`;
  - `proposal_is_not_execution_authority`;
  - `owner_must_confirm_runtime_profile_before_use`.
- Verification passed:
  - `pytest -q tests/unit/test_runtime_non_runtime_signal_profile_proposal.py tests/unit/test_experimental_runtime_profile_proposal.py`
    with `9 passed`;
  - `python3 -m compileall -q scripts/runtime_non_runtime_signal_profile_proposal.py tests/unit/test_runtime_non_runtime_signal_profile_proposal.py`;
  - `python3 scripts/runtime_non_runtime_signal_profile_proposal.py --help`;
  - `git diff --check -- scripts/runtime_non_runtime_signal_profile_proposal.py tests/unit/test_runtime_non_runtime_signal_profile_proposal.py`.
- Safety:
  - no PG write;
  - no runtime profile mutation;
  - no runtime was created;
  - no runtime was enabled;
  - no SignalEvaluation was created;
  - no OrderCandidate was created;
  - no `ExecutionIntent` was created;
  - no order was created;
  - no `OrderLifecycle` call occurred;
  - no exchange write occurred;
  - no runtime budget was mutated;
  - no position was opened or closed;
  - no withdrawal or transfer occurred.
- Progress estimate:
  - runtime mainline convergence moves from approximately `96%` to `97%`;
  - the next step is to deploy this bridge to Tokyo and run the same proposal
    generation on the server-side RTF-034 selector report, then decide whether
    to create/confirm an ADA/RBR bounded runtime or keep waiting for an
    AVAX/BTPC-compatible signal.

## 2026-06-13 (RTF-035 Tokyo Deploy / Profile Proposal Probe)

- Deployed RTF-035 proposal bridge to Tokyo:
  - release:
    `brc-runtime-governance-1183571b-20260613Trtf035-profile-proposal`;
  - deployed HEAD:
    `1183571b7b15913b71ff810254f8f62b563af353`;
  - previous release:
    `brc-runtime-governance-97339f58-20260613Trtf034-live-signal-selector`;
  - deploy apply status: `applied`;
  - deployment effects recorded:
    - `database_backup_created=true`;
    - `migrations_run=true`;
    - `services_restarted=true`;
    - `exchange_called=false`;
    - `execution_intent_created=false`;
    - `order_created=false`;
    - `order_lifecycle_called=false`.
- Tokyo postdeploy verification passed:
  - read-only probe:
    `output/rtf035-tokyo-readonly-probe-after-1183571b.json`;
  - postdeploy verifier:
    `output/rtf035-tokyo-postdeploy-verify-1183571b.json`;
  - verifier status: `postdeploy_acceptance_passed`;
  - migration count: `84`;
  - latest migration:
    `2026-06-11-084_create_runtime_post_submit_budget_settlements.py`.
- Ran the proposal bridge on Tokyo from the server-side RTF-034 selector report:
  - source selector:
    `/home/ubuntu/brc-deploy/reports/rtf034-live-signal-selector/20260613Trtf034-97339f58/runtime-live-signal-selector.json`;
  - remote report:
    `/home/ubuntu/brc-deploy/reports/rtf035-profile-proposal/20260613Trtf035-1183571b/non-runtime-signal-profile-proposal.json`;
  - copied local report:
    `output/rtf035-tokyo/non-runtime-signal-profile-proposal.json`;
  - packet status: `ready_for_owner_runtime_profile_decision`;
  - proposal status: `ready_for_owner_codex_confirmation`;
  - blockers: `[]`.
- Tokyo proposal boundary:
  - source signal: `RBR-001 / RBR-001-v0 / ADA/USDT:USDT / short`;
  - profile kind: `small_capital_conservative_short`;
  - total loss budget: `6.00`;
  - max loss per attempt: `2.00`;
  - max notional per attempt: `8.00`;
  - max attempts: `3`;
  - max leverage: `1`.
- Safety:
  - `selector_replay_only=true`;
  - `database_write=false`;
  - `runtime_profile_mutated=false`;
  - `runtime_created=false`;
  - `runtime_enabled=false`;
  - `signal_evaluation_created=false`;
  - `order_candidate_created=false`;
  - `execution_intent_created=false`;
  - `executable_execution_intent_created=false`;
  - `order_created=false`;
  - `order_lifecycle_called=false`;
  - `exchange_write_called=false`;
  - `runtime_budget_mutated=false`;
  - `position_opened=false`;
  - `position_closed=false`;
  - `withdrawal_or_transfer_created=false`.
- Progress estimate:
  - runtime mainline convergence remains approximately `97%`;
  - the project now has a server-verified bridge from live non-runtime signal
    evidence to bounded runtime profile proposal. The next mainline step is
    Owner/Codex confirmation and runtime creation/promotion for ADA/RBR, or
    continued observation until the active AVAX/BTPC runtime receives a
    compatible `would_enter`.

## 2026-06-13 (RTF-034 Runtime-compatible Live Signal Selector Local Proof)

- Confirmed current mainline workspace and branch before implementation:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - starting HEAD: `b08bdda5`.
- Added a read-only runtime-compatible strategy signal selector:
  - `scripts/runtime_live_strategy_signal_selector.py`;
  - consumes the existing strategy-group read-only preview;
  - loads the target `StrategyRuntimeInstance`;
  - selects only a `would_enter` signal whose strategy family, version, symbol,
    and side exactly match the runtime profile;
  - writes a `StrategyFamilySignalInput` JSON only when the signal is runtime
    compatible;
  - reports non-runtime `would_enter` signals as profile-mismatch evidence
    instead of using them for the current runtime.
- Live-market observation during this stage found:
  - source: `binance_usdm_public_klines_read_only`;
  - current strategy shelf signals: `8`;
  - `would_enter` count: `1`;
  - current `would_enter`: `RBR-001 / ADA/USDT:USDT / short`;
  - this is not compatible with the current `AVAX/USDT:USDT` BTPC runtime, so
    it requires a separate Owner-confirmed new runtime or runtime-profile
    change before it can be used.
- Selector behavior:
  - runtime-compatible `would_enter`: returns
    `runtime_compatible_would_enter_selected` and writes the signal input JSON;
  - non-runtime `would_enter`: returns
    `would_enter_available_but_not_runtime_compatible`;
  - matching runtime signal with `no_action`: returns
    `runtime_signal_observe_only`.
- Verification passed:
  - `pytest -q tests/unit/test_runtime_live_strategy_signal_selector.py`
    with `3 passed`;
  - `python3 -m compileall -q scripts/runtime_live_strategy_signal_selector.py tests/unit/test_runtime_live_strategy_signal_selector.py`;
  - `python3 scripts/runtime_live_strategy_signal_selector.py --help`;
  - `git diff --check -- scripts/runtime_live_strategy_signal_selector.py tests/unit/test_runtime_live_strategy_signal_selector.py`.
- Safety:
  - no PG write;
  - no runtime profile mutation;
  - no shadow candidate was created;
  - no `ExecutionIntent` was created;
  - no local order was created;
  - no `OrderLifecycle` call occurred;
  - no exchange write occurred;
  - no runtime budget was mutated;
  - no position was opened or closed;
  - no withdrawal or transfer occurred.
- Progress estimate:
  - runtime mainline convergence remains approximately `96%`;
  - the immediate blocker is now more precise: current market has a
    non-runtime-compatible `would_enter`, while the active runtime still needs
    a compatible `would_enter` signal or an Owner-confirmed new runtime/profile
    decision.

## 2026-06-13 (RTF-034 Tokyo Deploy / Live Selector Probe)

- Deployed RTF-034 selector code to Tokyo:
  - release:
    `brc-runtime-governance-97339f58-20260613Trtf034-live-signal-selector`;
  - deployed HEAD:
    `97339f58a1fd06bf99ab0b495e38ccf39a6d5d2e`;
  - previous release:
    `brc-runtime-governance-a8d7808d-20260613Trtf033-full-cycle`;
  - deploy apply status: `applied`;
  - deployment effects recorded:
    - `database_backup_created=true`;
    - `migrations_run=true`;
    - `services_restarted=true`;
    - `exchange_called=false`;
    - `execution_intent_created=false`;
    - `order_created=false`;
    - `order_lifecycle_called=false`.
- Tokyo postdeploy verification passed:
  - read-only probe:
    `output/rtf034-tokyo-readonly-probe-after-97339f58.json`;
  - postdeploy verifier:
    `output/rtf034-tokyo-postdeploy-verify-97339f58.json`;
  - verifier status: `postdeploy_acceptance_passed`;
  - migration count: `84`;
  - latest migration:
    `2026-06-11-084_create_runtime_post_submit_budget_settlements.py`.
- Ran the selector on Tokyo for the active AVAX runtime:
  - runtime: `strategy-runtime-95655873b76c`;
  - remote report:
    `/home/ubuntu/brc-deploy/reports/rtf034-live-signal-selector/20260613Trtf034-97339f58/runtime-live-signal-selector.json`;
  - copied local report:
    `output/rtf034-tokyo/runtime-live-signal-selector.json`;
  - status: `would_enter_available_but_not_runtime_compatible`;
  - blocker: `would_enter_signals_not_runtime_compatible`;
  - selected runtime-compatible signal: `null`;
  - output signal input JSON: `null`.
- Live selector evidence:
  - one live-market `would_enter` exists:
    `RBR-001 / RBR-001-v0 / ADA/USDT:USDT / short`;
  - runtime compatibility blockers:
    - `runtime_strategy_family_mismatch`;
    - `runtime_strategy_family_version_mismatch`;
    - `runtime_symbol_mismatch`;
  - current active runtime is still the AVAX/BTPC runtime, so the selector
    correctly refuses to feed the ADA/RBR signal into the AVAX runtime.
- Safety:
  - `read_only_market_scan=true`;
  - `database_write=false`;
  - `runtime_profile_mutated=false`;
  - `signal_evaluation_created=false`;
  - `order_candidate_created=false`;
  - `execution_intent_created=false`;
  - `executable_execution_intent_created=false`;
  - `order_created=false`;
  - `order_lifecycle_called=false`;
  - `exchange_write_called=false`;
  - `runtime_budget_mutated=false`;
  - `position_opened=false`;
  - `position_closed=false`;
  - `withdrawal_or_transfer_created=false`.
- Progress estimate:
  - runtime mainline convergence remains approximately `96%`;
  - the active blocker is now a product/runtime decision, not a hidden code
    blocker: either wait for an AVAX/BTPC-compatible signal, or explicitly
    create/confirm a bounded ADA/RBR runtime before using the current live
    `would_enter`.

## 2026-06-13 (RTF-033 Tokyo Full-cycle Deploy / Non-executing Probe)

- Confirmed current mainline workspace and branch before deployment:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - deployed HEAD: `a8d7808d`.
- Deployed RTF-032 full-cycle code to Tokyo:
  - release:
    `brc-runtime-governance-a8d7808d-20260613Trtf033-full-cycle`;
  - previous release:
    `brc-runtime-governance-ed88fbb2-20260613Trtf029-post-submit-finalize-api`;
  - deploy apply status: `applied`;
  - deployment backup:
    `/home/ubuntu/brc-deploy/backups/brc-runtime-governance-a8d7808d-20260613Trtf033-full-cycle.pgdump`;
  - deployment effects recorded:
    - `database_backup_created=true`;
    - `migrations_run=true`;
    - `services_restarted=true`;
    - `exchange_called=false`;
    - `execution_intent_created=false`;
    - `order_created=false`;
    - `order_lifecycle_called=false`.
- Tokyo postdeploy verification passed:
  - read-only probe:
    `output/rtf033-tokyo-readonly-probe-after-a8d7808d.json`;
  - postdeploy verifier:
    `output/rtf033-tokyo-postdeploy-verify-a8d7808d.json`;
  - verifier status: `postdeploy_acceptance_passed`;
  - current deployed head:
    `a8d7808d90d9f3dec618f6f280390e7f4519972f`;
  - migration count: `84`;
  - latest migration:
    `2026-06-11-084_create_runtime_post_submit_budget_settlements.py`.
- Ran the full-cycle non-executing Tokyo probe for the active AVAX runtime:
  - runtime: `strategy-runtime-95655873b76c`;
  - reservation:
    `runtime-attempt-reservation-runtime-submit-authorization-intent_rt_6ca3cecd63fafbd1d25760df`;
  - remote report:
    `/home/ubuntu/brc-deploy/reports/rtf033-full-cycle/20260613Trtf033-a8d7808d/full-next-attempt-submit-cycle.json`;
  - copied local report:
    `output/rtf033-tokyo/full-next-attempt-submit-cycle.json`;
  - result status: `waiting_for_signal`;
  - blocker: `strategy_signal_not_would_enter`.
- Probe interpretation:
  - the post-submit / next-attempt cycle can run on Tokyo from current durable
    runtime facts;
  - current supplied AVAX/BTPC signal is observe-only, so the full-cycle script
    stops before executable readiness;
  - no fresh shadow candidate was planned from this signal;
  - no readiness, official handoff, local registration, or submit action was
    executed.
- Safety invariants from the Tokyo report:
  - `non_executing=true`;
  - `runs_executable_readiness=false`;
  - `calls_official_submit_endpoint=false`;
  - `pre_submit_rehearsal_called=false`;
  - `local_registration_armed=false`;
  - `exchange_submit_armed=false`;
  - `exchange_write_called=false`;
  - `execution_intent_created=false`;
  - `executable_execution_intent_created=false`;
  - `order_created=false`;
  - `order_lifecycle_called=false`;
  - `runtime_budget_mutated=false`;
  - `position_opened=false`;
  - `position_closed=false`;
  - `withdrawal_or_transfer_created=false`.
- Progress estimate:
  - runtime mainline convergence moves from approximately `95%` to `96%`;
  - remaining mainline work is to wait for or produce a real
    `would_enter`-class strategy signal, then let the same full-cycle path
    proceed into executable readiness / controlled submit handoff with fresh
    runtime authorization.

## 2026-06-13 (RTF-032 Full Next-attempt Submit-preparation Cycle)

- Confirmed current mainline workspace and branch before implementation:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - starting HEAD: `df7e1ed2`.
- Added the full non-executing next-attempt submit-preparation cycle:
  - `scripts/runtime_full_next_attempt_submit_cycle.py`;
  - composes RTF-030 post-submit next-attempt cycle with RTF-031
    cycle-to-readiness / handoff bridge;
  - supports `--cycle-packet-json` so existing RTF-030 artifacts can be reused
    without rerunning the post-submit / strategy planning half.
- Full-cycle behavior:
  - fresh strategy signal observe-only: returns `waiting_for_signal` and does
    not run executable readiness;
  - strategy planning ready but readiness evidence missing: returns
    `ready_for_final_gate_preflight`;
  - readiness ready but no fresh submit authorization: returns
    `ready_for_fresh_submit_authorization`;
  - readiness ready plus fresh submit authorization: returns
    `ready_for_official_submit_call`;
  - official submit endpoint is never called by this script.
- This stage gives the mainline one repeatable operator/automation entry:
  - `post-submit finalize`;
  - `fresh strategy signal planning`;
  - `executable-submit readiness`;
  - `official-submit handoff preview`;
  - no order/exchange/OrderLifecycle side effect.
- Verification passed:
  - `pytest -q tests/unit/test_runtime_full_next_attempt_submit_cycle.py tests/unit/test_runtime_post_submit_next_attempt_cycle.py tests/unit/test_runtime_cycle_executable_submit_handoff.py tests/unit/test_runtime_executable_submit_readiness_api_flow.py tests/unit/test_runtime_official_submit_handoff_api_flow.py`
    with `21 passed`;
  - `python3 -m compileall -q scripts/runtime_full_next_attempt_submit_cycle.py tests/unit/test_runtime_full_next_attempt_submit_cycle.py`;
  - `git diff --check`;
  - `python3 scripts/runtime_full_next_attempt_submit_cycle.py --help`.
- Deployment:
  - not deployed in this stage;
  - current Tokyo code remains `ed88fbb2`;
  - this stage is local proof plus tracked mainline code.
- Safety:
  - no official submit endpoint was called;
  - no pre-submit rehearsal retry was added;
  - no local registration was armed;
  - no `OrderLifecycle` submit occurred;
  - no exchange write occurred;
  - no order was created or submitted;
  - no runtime budget was mutated by the script;
  - no position was opened or closed;
  - no withdrawal or transfer occurred.
- Progress estimate:
  - runtime mainline convergence moves from approximately `94%` to `95%`;
  - next target is Tokyo deployment / integration verification for the
    full-cycle scripts, then live observation can wait for a real
    `ready_for_final_gate_preflight` signal and continue through the same
    readiness / handoff path.

## 2026-06-13 (RTF-031 Cycle to Executable Readiness / Official Handoff Bridge)

- Confirmed current mainline workspace and branch before implementation:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - starting HEAD: `978c91e8`.
- Added the non-executing bridge from the RTF-030 cycle into the existing
  executable submit preparation chain:
  - `scripts/runtime_cycle_executable_submit_handoff.py`;
  - input: RTF-030 cycle packet plus executable-readiness evidence JSON;
  - output artifacts:
    - extracted strategy-planning packet;
    - executable-readiness API flow report;
    - extracted executable-readiness packet;
    - optional official-submit handoff API flow report.
- Bridge behavior:
  - cycle not `ready_for_final_gate_preflight`: blocks before readiness and does
    not call handoff;
  - cycle ready + readiness blocked: blocks at executable readiness;
  - cycle ready + readiness ready + no fresh submit authorization: returns
    `ready_for_fresh_submit_authorization`;
  - cycle ready + readiness ready + fresh submit authorization: calls the
    non-executing handoff preview and can return
    `ready_for_official_submit_call`.
- This stage connects the repeated strategy-driven loop to the official submit
  handoff path without calling the official submit endpoint itself:
  - `post-submit finalize -> next-attempt strategy cycle`;
  - `ready_for_final_gate_preflight -> executable-submit readiness`;
  - `ready_for_executable_submit -> official-submit handoff preview`.
- Verification passed:
  - `pytest -q tests/unit/test_runtime_cycle_executable_submit_handoff.py tests/unit/test_runtime_post_submit_next_attempt_cycle.py tests/unit/test_runtime_executable_submit_readiness_api_flow.py tests/unit/test_runtime_official_submit_handoff_api_flow.py`
    with `15 passed`;
  - `python3 -m compileall -q scripts/runtime_cycle_executable_submit_handoff.py tests/unit/test_runtime_cycle_executable_submit_handoff.py`;
  - `git diff --check`;
  - `python3 scripts/runtime_cycle_executable_submit_handoff.py --help`.
- Deployment:
  - not deployed in this stage;
  - current Tokyo code remains `ed88fbb2`;
  - this stage is local proof plus tracked mainline code.
- Safety:
  - no official submit endpoint was called;
  - no pre-submit rehearsal retry was added;
  - no local registration was armed;
  - no `OrderLifecycle` submit occurred;
  - no exchange write occurred;
  - no order was created or submitted;
  - no runtime budget was mutated by the script;
  - no position was opened or closed;
  - no withdrawal or transfer occurred.
- Progress estimate:
  - runtime mainline convergence moves from approximately `93%` to `94%`;
  - next target is an end-to-end local/Tokyo proof using real RTF-029/RTF-030
    artifacts and current readiness evidence, followed by deployment when the
    chain is ready to observe a real `ready_for_final_gate_preflight` signal.

## 2026-06-13 (RTF-030 Post-submit Next-attempt Cycle Local Proof)

- Confirmed current mainline workspace and branch before implementation:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - starting HEAD: `dcbab230`.
- Added the repeatable non-executing cycle entry:
  - `scripts/runtime_post_submit_next_attempt_cycle.py`;
  - composes `runtime_post_submit_finalize_api_flow` with
    `runtime_next_attempt_strategy_plan_api_flow`;
  - writes three local artifacts per cycle:
    - post-submit finalize flow report;
    - extracted post-submit finalize packet;
    - next-attempt strategy planning flow report;
  - preserves the post-submit mainline:
    durable submit result -> post-submit finalize ->
    `ready_for_fresh_signal` -> fresh strategy signal planning.
- Cycle behavior:
  - post-submit not ready: returns `blocked` before calling strategy planning;
  - post-submit ready + observe-only signal: returns `waiting_for_signal`;
  - post-submit ready + executable strategy signal: returns
    `ready_for_final_gate_preflight` with `order_candidate_id`;
  - final-gate / submit remains a later official path and is not called by the
    cycle.
- Verification passed:
  - `pytest -q tests/unit/test_runtime_post_submit_next_attempt_cycle.py tests/unit/test_runtime_post_submit_finalize_api_flow.py tests/unit/test_runtime_next_attempt_strategy_plan_api_flow.py tests/unit/test_runtime_next_attempt_strategy_planning.py`
    with `19 passed`;
  - `python3 -m compileall -q scripts/runtime_post_submit_next_attempt_cycle.py tests/unit/test_runtime_post_submit_next_attempt_cycle.py`;
  - `git diff --check`;
  - `python3 scripts/runtime_post_submit_next_attempt_cycle.py --help`.
- Deployment:
  - not deployed in this stage;
  - current Tokyo code remains `ed88fbb2`;
  - this stage is local proof plus tracked mainline code.
- Safety:
  - no pre-submit rehearsal retry was added;
  - no local registration was armed;
  - no first-real-submit action was called;
  - no `OrderLifecycle` submit occurred;
  - no exchange write occurred;
  - no order was created or submitted;
  - no runtime budget was mutated by the script;
  - no position was opened or closed;
  - no withdrawal or transfer occurred.
- Progress estimate:
  - runtime mainline convergence moves from approximately `92%` to `93%`;
  - next target is to deploy or run the cycle against Tokyo when useful, then
    connect its `ready_for_final_gate_preflight` output to the existing
    executable readiness / official submit handoff path.

## 2026-06-13 (RTF-029 Tokyo Post-submit Finalize API + Next-attempt Gate Probe)

- Confirmed current mainline workspace and branch before deployment /
  integration verification:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - deployed code HEAD: `ed88fbb2`;
  - local and remote branch both pointed at `ed88fbb2` before the stage commit.
- Deployed the current program branch to Tokyo using the git-based deploy path:
  - release:
    `brc-runtime-governance-ed88fbb2-20260613Trtf029-post-submit-finalize-api`;
  - current symlink:
    `/home/ubuntu/brc-deploy/app/current`;
  - deploy report:
    `output/rtf029-tokyo/git-deploy-applied-ed88fbb2.json`;
  - deploy effects: database backup created, migrations run, service restarted;
  - deploy safety flags: no exchange call, no order, no `ExecutionIntent`, no
    `OrderLifecycle`, no secret values printed by Codex.
- Verified Tokyo after deployment:
  - read-only probe:
    `output/rtf029-tokyo/readonly-probe-after-ed88fbb2.json`;
  - postdeploy verifier:
    `output/rtf029-tokyo/postdeploy-verify-ed88fbb2.json`;
  - both returned no blockers, current release symlink pointed at `ed88fbb2`,
    and migration count remained `84` with latest migration
    `2026-06-11-084_create_runtime_post_submit_budget_settlements.py`.
- Resolved current runtime submit evidence from Tokyo PG facts:
  - runtime: `strategy-runtime-95655873b76c`;
  - latest submit authorization:
    `runtime-submit-authorization-intent_rt_6ca3cecd63fafbd1d25760df`;
  - latest execution intent:
    `intent_rt_6ca3cecd63fafbd1d25760df`;
  - latest reservation:
    `runtime-attempt-reservation-runtime-submit-authorization-intent_rt_6ca3cecd63fafbd1d25760df`;
  - latest durable execution result:
    `runtime-exchange-submit-execution-result-runtime-submit-authorization-intent_rt_6ca3cecd63fafbd1d25760df`;
  - latest settlement:
    `runtime-post-submit-budget-settlement-runtime-first-real-submit-outcome-accounting-runtime-submit-authorization-intent_rt_6ca3cecd63fafbd1d25760df`;
  - symbol / side: `AVAX/USDT:USDT` / `short`;
  - durable result status: `exchange_submit_orders_submitted`;
  - settlement status: `recorded_reserved_budget_consumed`.
- Ran the Tokyo post-submit finalize API probe:
  - remote report:
    `/home/ubuntu/brc-deploy/reports/rtf029-post-submit-finalize-api/20260613Trtf029-ed88fbb2/post-submit-finalize-api-flow.json`;
  - local copy:
    `output/rtf029-tokyo/post-submit-finalize-api-flow.json`;
  - status: `finalized_ready_for_next_attempt`;
  - next-attempt gate status: `ready_for_fresh_signal`;
  - blockers: none.
- Ran the Tokyo next-attempt strategy planning API probe:
  - remote report:
    `/home/ubuntu/brc-deploy/reports/rtf029-post-submit-finalize-api/20260613Trtf029-ed88fbb2/next-attempt-strategy-plan-api-flow.json`;
  - local copy:
    `output/rtf029-tokyo/next-attempt-strategy-plan-api-flow.json`;
  - status: `waiting_for_signal`;
  - blocker: `strategy_signal_not_would_enter`;
  - signal evaluation ID:
    `runtime-signal-input:strategy-runtime-95655873b76c:BTPC-001:1781179200000`;
  - order candidate ID: none.
- Interpretation:
  - the runtime no longer treats the already submitted attempt as a pre-submit
    rehearsal problem;
  - durable submit result -> existing submit outcome review / settlement ->
    post-submit finalize now reaches `ready_for_fresh_signal`;
  - the chain correctly stops at current strategy semantics because the latest
    AVAX / BTPC signal is observe-only rather than an executable entry signal;
  - this is now a strategy-signal wait state, not an execution-chain blocker.
- Safety:
  - no pre-submit rehearsal retry was used for the already submitted attempt;
  - no local registration was armed;
  - no first-real-submit action was called;
  - no `OrderLifecycle` submit occurred;
  - no exchange write occurred;
  - no order was created or submitted by this stage;
  - no runtime budget was mutated by the probe script;
  - no position was opened or closed;
  - no withdrawal or transfer occurred.
- Progress estimate:
  - runtime mainline convergence moves from approximately `90%` to `92%`;
  - next target is to turn this wait state into the normal loop:
    fresh strategy signal -> shadow candidate -> FinalGate / runtime grant ->
    bounded executable attempt, while preserving post-submit finalize as the
    recurring close-out path.

## 2026-06-13 (RTF-028 Runtime Post-submit Finalize API + Latest Result Resolution)

- Confirmed current mainline workspace and branch before implementation:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - starting HEAD: `f6763785`.
- Added runtime-level post-submit finalize API support:
  - `RuntimePostSubmitFinalizeService.finalize_authorization(...)` now accepts
    an optional `expected_runtime_instance_id` and blocks mismatched durable
    submit-result / review / settlement facts;
  - `RuntimePostSubmitFinalizeService.finalize_latest_for_runtime(...)` resolves
    the latest durable `RuntimeExecutionExchangeSubmitExecutionResult` for a
    runtime and finalizes from that result's authorization ID;
  - missing latest submit-result evidence returns a blocked
    `RuntimePostSubmitFinalizePacket` instead of falling back to pre-submit
    rehearsal.
- Added PG evidence lookup:
  - `PgRuntimeExecutionExchangeSubmitExecutionResultRepository`
    now supports `get_latest_by_runtime_instance_id(...)`;
  - ordering uses `created_at_ms desc` and returns the stored payload as the
    authoritative domain model.
- Added Trading Console endpoint:
  - `POST /api/trading-console/strategy-runtimes/{runtime_instance_id}/post-submit-finalize-packets`;
  - request can provide an explicit `authorization_id` or omit it to use the
    latest durable submit result for the runtime;
  - request requires `reservation_id` because budget settlement still depends
    on the recorded attempt reservation;
  - endpoint reads local position projection for the submit-result symbol and
    supplies trusted `active_positions_count` to the next-attempt gate;
  - endpoint blocks runtime mismatches and does not call exchange,
    `OrderLifecycle`, local registration, close, withdrawal, or transfer.
- Added probe script:
  - `scripts/runtime_post_submit_finalize_api_flow.py`;
  - posts to the new endpoint and returns an audit packet containing the
    `post_submit_finalize_packet`, blockers, next-attempt blockers, warnings,
    and non-executing safety invariants;
  - supports explicit authorization ID or latest-result resolution.
- Verification passed:
  - `pytest -q tests/unit/test_runtime_post_submit_finalize.py tests/unit/test_runtime_post_submit_finalize_probe.py tests/unit/test_runtime_post_submit_finalize_api_flow.py tests/unit/test_runtime_next_attempt_strategy_planning.py tests/unit/test_runtime_next_attempt_strategy_plan_api_flow.py tests/unit/test_runtime_real_signal_pipeline_fixture.py tests/unit/test_runtime_real_signal_scoped_local_registration_pipeline.py tests/unit/test_runtime_official_evidence_chain_from_binding.py tests/unit/test_runtime_scoped_local_registration_proof_from_evidence.py`
    with `39 passed`;
  - `python3 -m compileall src/application/runtime_post_submit_finalize_service.py src/infrastructure/pg_runtime_execution_exchange_submit_execution_result_repository.py src/interfaces/api_trading_console.py scripts/runtime_post_submit_finalize_api_flow.py tests/unit/test_runtime_post_submit_finalize.py tests/unit/test_runtime_post_submit_finalize_api_flow.py`;
  - `git diff --check`.
- Safety:
  - no pre-submit rehearsal was called;
  - no local registration occurred;
  - no first-real-submit action occurred;
  - no `OrderLifecycle` submit occurred;
  - no exchange write occurred;
  - no order was submitted or created;
  - no position close occurred;
  - no runtime-boundary expansion occurred;
  - no withdrawal or transfer occurred.
- Progress estimate:
  - runtime mainline convergence moves from approximately `89%` to `90%`;
  - the next useful target is deploying this API to Tokyo and running the
    post-submit finalize API flow against the current runtime evidence, then
    feeding the returned packet into next-attempt strategy planning.

## 2026-06-13 (RTF-027 Tokyo Real Signal Fixture Deploy + Non-executing Probe)

- Confirmed current mainline workspace and branch before deployment:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - deployed HEAD: `fcbbb327`;
  - remote branch: `origin/program/live-safe-v1` matched local HEAD before
    deploy.
- Release readiness:
  - `prepare_tokyo_runtime_governance_release.py` returned
    `ready_for_local_packaging`;
  - Tokyo baseline was deployed at
    `1707ad58fccacf8fa98e751fd630cf0ef41504dd`;
  - local commit was 6 commits ahead of deployed baseline;
  - migrations matched count `84` and latest
    `2026-06-11-084_create_runtime_post_submit_budget_settlements.py`;
  - tracked tree was clean; untracked files remained outside the git archive.
- Deploy artifacts:
  - `output/rtf027-tokyo/git-deploy-plan-fcbbb327.json`;
  - `output/rtf027-tokyo/owner-git-deploy-packet-fcbbb327.json`;
  - `output/rtf027-tokyo/git-deploy-dry-run-fcbbb327.json`;
  - `output/rtf027-tokyo/git-deploy-applied-fcbbb327.json`;
  - `output/rtf027-tokyo/readonly-probe-after-fcbbb327.json`;
  - `output/rtf027-tokyo/postdeploy-verify-fcbbb327.json`.
- Tokyo deployment:
  - release:
    `brc-runtime-governance-fcbbb327-20260613Trtf027-real-signal-fixture`;
  - apply status: `applied`;
  - remote commands executed: `16`;
  - remote current symlink:
    `/home/ubuntu/brc-deploy/app/current -> /home/ubuntu/brc-deploy/releases/brc-runtime-governance-fcbbb327-20260613Trtf027-real-signal-fixture`;
  - expected deployment effects occurred: remote files modified, database
    backup created, migrations run, services restarted;
  - trading effects stayed false: no exchange call, no order creation, no
    `ExecutionIntent`, and no `OrderLifecycle`.
- Postdeploy verification:
  - read-only probe returned `ready_for_controlled_deploy_preflight`;
  - postdeploy verifier returned `postdeploy_acceptance_passed`;
  - both had no blockers.
- Tokyo non-executing fixture:
  - report path:
    `/home/ubuntu/brc-deploy/reports/rtf027-real-signal-fixture/20260613Trtf027-fcbbb327/fixture-report.json`;
  - status: `ready_real_signal_pipeline_fixture`;
  - pipeline status:
    `ready_for_real_signal_scoped_local_registration_proof`;
  - artifact directory:
    `/home/ubuntu/brc-deploy/reports/rtf027-real-signal-fixture/20260613Trtf027-fcbbb327/fixture-artifacts`.
- Safety:
  - fixture used a fake Trading Console API client;
  - no real server call occurred;
  - no runtime mutation occurred;
  - no local registration was attempted;
  - no first-real-submit action occurred;
  - no `OrderLifecycle` submit occurred;
  - no exchange write occurred;
  - no order was submitted or created;
  - no withdrawal or transfer occurred.
- Progress estimate:
  - runtime mainline convergence moves from approximately `88%` to `89%`;
  - the next useful target is converting the deployed non-executing proof into
    the next runtime mainline step: post-submit finalize / next-attempt gate
    integration without returning consumed authorizations to pre-submit
    rehearsal.

## 2026-06-13 (RTF-026 Local Real Signal Pipeline Report Fixture)

- Confirmed current mainline workspace and branch before implementation:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - starting HEAD: `cc422bbb`.
- Added `scripts/runtime_real_signal_pipeline_fixture.py`:
  - writes local fixture input reports for signal input, FinalGate preview,
    trusted submit facts, submit idempotency, attempt outcome policy,
    protection failure policy, local-registration enablement, exchange-submit
    enablement, exchange action authorization, OrderLifecycle submit enablement,
    exchange adapter enablement, and deployment readiness;
  - runs the real `runtime_real_signal_scoped_local_registration_pipeline`
    with `--auto-readiness-evidence`;
  - uses a fake Trading Console API client, so no server, PG, OrderLifecycle, or
    exchange side effect is possible;
  - proves the local report chain:
    `real signal source -> collector -> readiness -> handoff -> binding ->
    evidence chain -> scoped local-registration dry-run`.
- Fixture artifacts:
  - `fixture-inputs/00-*.json`;
  - `pipeline/02-collected-readiness-evidence.json`;
  - `pipeline/07-scoped-local-registration-proof.json`;
  - optional fixture report via `--output`.
- Expected boundary:
  - the disabled-smoke official evidence chain still records the expected
    local-order-adapter boundary blocker;
  - final pipeline status can still reach
    `ready_for_real_signal_scoped_local_registration_proof` because scoped
    local-registration proof is a dry-run readiness classification.
- Verification passed:
  - `pytest -q tests/unit/test_runtime_real_signal_pipeline_fixture.py`
    with `2 passed`;
  - `pytest -q tests/unit/test_runtime_real_signal_readiness_evidence_resolver.py tests/unit/test_runtime_readiness_evidence_source_map.py tests/unit/test_runtime_early_readiness_fact_collector.py tests/unit/test_runtime_real_signal_scoped_local_registration_pipeline.py tests/unit/test_runtime_real_signal_pipeline_fixture.py tests/unit/test_runtime_official_evidence_chain_from_binding.py tests/unit/test_runtime_scoped_local_order_adapter_boundary_from_evidence.py tests/unit/test_runtime_scoped_local_registration_proof_from_evidence.py`
    with `25 passed`;
  - `python3 -m compileall scripts/runtime_real_signal_pipeline_fixture.py tests/unit/test_runtime_real_signal_pipeline_fixture.py`;
  - `git diff --check`.
- Deployment:
  - not deployed in this local proof stage.
- Safety:
  - no Tokyo action occurred;
  - no real server call occurred;
  - no local registration occurred;
  - no first-real-submit action occurred;
  - no `OrderLifecycle` submit occurred;
  - no exchange write occurred;
  - no runtime mutation occurred;
  - no withdrawal or transfer occurred.
- Progress estimate:
  - runtime mainline convergence moves from approximately `87%` to `88%`;
  - next useful target is Tokyo deployment of the RTF-022 through RTF-026 tool
    chain, followed by a non-executing Tokyo fixture/probe before any real
    exchange action.

## 2026-06-13 (RTF-025 Real Signal Pipeline Collector Integration Local Proof)

- Confirmed current mainline workspace and branch before implementation:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - starting HEAD: `88361a2e`.
- Updated `scripts/runtime_real_signal_scoped_local_registration_pipeline.py`:
  - under `--auto-readiness-evidence`, the pipeline can now accept report JSON
    inputs for FinalGate preview, trusted submit facts, idempotency, attempt
    outcome policy, protection failure policy, local-registration enablement,
    exchange-submit enablement, exchange action authorization, OrderLifecycle
    submit enablement, exchange adapter enablement, and deployment readiness;
  - if any report inputs are supplied, it runs
    `runtime_early_readiness_fact_collector` first;
  - complete report facts write `02-collected-readiness-evidence.json` and feed
    the existing persisted-draft-source readiness preview;
  - incomplete report facts block at
    `blocked_at_early_readiness_fact_collection` before any readiness API call;
  - existing `--readiness-evidence-json` and explicit-field resolver paths
    remain supported.
- Added focused pipeline tests:
  - collector input missing trusted facts blocks before
    `persisted-draft-source-readiness-previews`;
  - complete collector report facts flow through readiness, handoff, binding,
    evidence chain, and scoped local-registration dry-run.
- Verification passed:
  - `pytest -q tests/unit/test_runtime_real_signal_scoped_local_registration_pipeline.py tests/unit/test_runtime_early_readiness_fact_collector.py`
    with `9 passed`;
  - `pytest -q tests/unit/test_runtime_real_signal_readiness_evidence_resolver.py tests/unit/test_runtime_readiness_evidence_source_map.py tests/unit/test_runtime_early_readiness_fact_collector.py tests/unit/test_runtime_real_signal_scoped_local_registration_pipeline.py tests/unit/test_runtime_official_evidence_chain_from_binding.py tests/unit/test_runtime_scoped_local_order_adapter_boundary_from_evidence.py tests/unit/test_runtime_scoped_local_registration_proof_from_evidence.py`
    with `23 passed`;
  - `python3 -m compileall scripts/runtime_real_signal_scoped_local_registration_pipeline.py scripts/runtime_early_readiness_fact_collector.py tests/unit/test_runtime_real_signal_scoped_local_registration_pipeline.py tests/unit/test_runtime_early_readiness_fact_collector.py`;
  - `git diff --check`.
- Deployment:
  - not deployed in this local proof stage.
- Safety:
  - no sample rehearsal fallback was added;
  - no local registration occurred;
  - no first-real-submit action occurred;
  - no `OrderLifecycle` submit occurred;
  - no exchange write occurred;
  - no runtime mutation occurred;
  - no withdrawal or transfer occurred.
- Progress estimate:
  - runtime mainline convergence moves from approximately `86%` to `87%`;
  - the next useful target is a local end-to-end report fixture that proves
    `real signal source -> collector -> readiness -> handoff -> binding ->
    evidence chain -> scoped proof` without hand-transcribed readiness fields.

## 2026-06-13 (RTF-024 Early Readiness Fact Collector Local Proof)

- Confirmed current mainline workspace and branch before implementation:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - starting HEAD: `18ff7327`.
- Added `scripts/runtime_early_readiness_fact_collector.py`:
  - reads existing local JSON reports / snapshots;
  - extracts FinalGate preview pass evidence, runtime grant / Owner submit
    authorization IDs, trusted submit facts, idempotency policy, attempt
    outcome policy, protection failure policy, local-registration enablement,
    exchange-submit enablement, exchange action authorization, OrderLifecycle
    submit enablement, exchange adapter enablement, and deployment readiness;
  - writes `02-collected-readiness-evidence.json` only when all required
    evidence for `RuntimeExecutableSubmitReadinessEvidence` is complete;
  - otherwise returns `blocked_early_readiness_facts_incomplete` with exact
    missing fields.
- Added focused tests:
  - empty input blocks with missing FinalGate, authorization, and trusted fact
    evidence;
  - partial FinalGate / trusted-fact reports extract available facts but do not
    claim readiness;
  - complete report set writes resolver-compatible readiness evidence.
- Verification passed:
  - `pytest -q tests/unit/test_runtime_early_readiness_fact_collector.py`
    with `3 passed`;
  - `pytest -q tests/unit/test_runtime_real_signal_readiness_evidence_resolver.py tests/unit/test_runtime_readiness_evidence_source_map.py tests/unit/test_runtime_early_readiness_fact_collector.py tests/unit/test_runtime_real_signal_scoped_local_registration_pipeline.py`
    with `13 passed`;
  - `python3 -m compileall scripts/runtime_early_readiness_fact_collector.py tests/unit/test_runtime_early_readiness_fact_collector.py`;
  - `git diff --check`.
- Deployment:
  - not deployed in this local proof stage.
- Safety:
  - no API call occurred;
  - no `ExecutionIntent` was created;
  - no order was created;
  - no `OrderLifecycle` call occurred;
  - no exchange write occurred;
  - no runtime mutation occurred;
  - no withdrawal or transfer occurred.
- Progress estimate:
  - runtime mainline convergence moves from approximately `85%` to `86%`;
  - next useful target is wiring this collector into the real-signal pipeline
    so current report artifacts can feed auto-readiness without manual field
    transcription.

## 2026-06-13 (RTF-023 Readiness Evidence Source Map / Circular Dependency Guard)

- Confirmed current mainline workspace and branch before implementation:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - starting HEAD: `b9a9a286`.
- Added `scripts/runtime_readiness_evidence_source_map.py`:
  - classifies each readiness evidence field into source classes:
    `early_current_final_gate_preview`,
    `explicit_runtime_grant_or_owner_authorization`,
    `trusted_current_submit_fact_snapshot`,
    `late_machine_preparable_after_fresh_authorization`,
    `late_machine_preparable_after_execution_intent`,
    scoped local/exchange/OrderLifecycle boundary decisions,
    exchange adapter boundary enablement, deployment readiness, trusted
    protection / position / account facts, and duplicate-submit guard;
  - reads optional RTF-022 resolver reports and optional RTF-016 evidence-chain
    reports;
  - marks evidence found only in post-binding evidence-chain reports as
    `available_only_after_binding`, not as early readiness input;
  - reports `missing_before_readiness` fields explicitly.
- Why this matters:
  - existing first-real-submit evidence preparation can machine-prepare some
    evidence only after fresh authorization / ExecutionIntent context exists;
  - treating those late artifacts as pre-readiness facts would recreate a
    circular dependency;
  - RTF-023 preserves fast progression while preventing fake readiness.
- Verification passed:
  - `pytest -q tests/unit/test_runtime_readiness_evidence_source_map.py`
    with `3 passed`;
  - `python3 -m compileall scripts/runtime_readiness_evidence_source_map.py tests/unit/test_runtime_readiness_evidence_source_map.py`.
- Deployment:
  - not deployed in this local proof stage.
- Safety:
  - no API call occurred;
  - no `ExecutionIntent` was created;
  - no order was created;
  - no `OrderLifecycle` call occurred;
  - no exchange write occurred;
  - no runtime mutation occurred;
  - no withdrawal or transfer occurred.
- Progress estimate:
  - runtime mainline convergence remains approximately `85%`;
  - RTF-023 clarifies the next implementation target: collect or persist early
    readiness facts before the readiness preview, while keeping late
    post-binding evidence on the official evidence-chain side.

## 2026-06-13 (RTF-022 Real Signal Readiness Evidence Resolver Local Proof)

- Confirmed current mainline workspace and branch before implementation:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - starting HEAD: `117b3d3b`.
- Added `scripts/runtime_real_signal_readiness_evidence_resolver.py`:
  - reads a real strategy-signal `intent_draft_source` packet;
  - refuses sources that are not `persisted_ready_intent_draft`;
  - requires explicit trusted readiness evidence for FinalGate, runtime grant
    or Owner submit authorization, trusted submit facts, idempotency, attempt
    outcome policy, protection-failure policy, local-registration enablement,
    exchange-submit enablement, exchange-submit action authorization,
    OrderLifecycle enablement, exchange-adapter enablement, protection
    readiness, active-position trust, fresh account facts, and duplicate-submit
    guard readiness;
  - writes `02-auto-readiness-evidence.json` only when all required trusted
    fields are present;
  - otherwise returns `blocked_readiness_evidence_unresolved` with exact missing
    fields.
- Updated `scripts/runtime_real_signal_scoped_local_registration_pipeline.py`:
  - added `--auto-readiness-evidence`;
  - inserted a `readiness_evidence_resolution` stage between
    `intent_draft_source` and `persisted_draft_source_readiness`;
  - preserved the existing `--readiness-evidence-json` manual path;
  - blocks at `blocked_at_readiness_evidence_resolution` when trusted evidence
    is missing instead of silently continuing or using sample rehearsal.
- Added focused tests:
  - resolver blocks missing trusted evidence;
  - resolver writes evidence only when explicit trusted facts are complete;
  - resolver blocks non-ready intent-draft sources;
  - pipeline auto-readiness blocks before readiness API when facts are missing;
  - pipeline auto-readiness can continue to scoped local-registration dry-run
    when facts are complete.
- Verification passed:
  - `pytest -q tests/unit/test_runtime_real_signal_readiness_evidence_resolver.py tests/unit/test_runtime_real_signal_scoped_local_registration_pipeline.py`
    with `7 passed`;
  - `pytest -q tests/unit/test_runtime_official_evidence_chain_from_binding.py tests/unit/test_runtime_scoped_local_order_adapter_boundary_from_evidence.py tests/unit/test_runtime_scoped_local_registration_proof_from_evidence.py tests/unit/test_runtime_real_signal_readiness_evidence_resolver.py tests/unit/test_runtime_real_signal_scoped_local_registration_pipeline.py`
    with `15 passed`;
  - `python3 -m compileall scripts/runtime_real_signal_readiness_evidence_resolver.py scripts/runtime_real_signal_scoped_local_registration_pipeline.py tests/unit/test_runtime_real_signal_readiness_evidence_resolver.py tests/unit/test_runtime_real_signal_scoped_local_registration_pipeline.py`;
  - `git diff --check`.
- Deployment:
  - not deployed in this local proof stage.
- Safety:
  - no Tokyo action occurred;
  - no sample rehearsal fallback was added;
  - resolver does not call API;
  - no local registration occurred;
  - no first-real-submit action occurred;
  - no `OrderLifecycle` submit occurred;
  - no exchange write occurred;
  - no runtime mutation occurred;
  - no withdrawal or transfer occurred.
- Progress estimate:
  - runtime mainline convergence moved from approximately `84%` to `85%`;
  - remaining primary work is current-fact backed readiness evidence collection,
    controlled local registration proof on the real-signal path, then audited
    OrderLifecycle / exchange submit integration.

## 2026-06-13 (RTF-021 Tokyo Deploy + Real Signal Pipeline Probe)

- Confirmed current mainline workspace and branch before deployment:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - target HEAD: `1707ad58fccacf8fa98e751fd630cf0ef41504dd`.
- Confirmed Tokyo baseline before deployment:
  - current release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-827de813-20260613Trtf019-local-registration-proof`;
  - current manifest head:
    `827de81309e5e085674f881dc1606ece8684d381`;
  - health: `status=ok`, `runtime_bound=true`, `live_ready=false`.
- Built deploy artifacts under:
  - `output/tokyo-git-deploy-1707ad58-rtf021-real-signal-pipeline`;
  - `git-deploy-plan.json`: `ready_for_owner_authorized_remote_git_deploy_plan`;
  - `owner-git-deploy-packet.json`: `ready_for_owner_git_deploy_decision`;
  - `git-deploy-dry-run.json`: `dry_run_ready`.
- Applied Tokyo deploy through the git-based deploy path:
  - release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-1707ad58-20260613Trtf021-real-signal-pipeline`;
  - apply report:
    `output/tokyo-git-deploy-1707ad58-rtf021-real-signal-pipeline/git-deploy-apply-report.json`;
  - status: `applied`;
  - commands: `16/16`;
  - effects: remote files modified, database backup created, migrations run,
    service restarted;
  - no `ExecutionIntent`, no order, no `OrderLifecycle`, no exchange call.
- Postdeploy checks passed:
  - health: `status=ok`, `runtime_bound=true`, `live_ready=false`;
  - read-only probe: `ready_for_controlled_deploy_preflight`;
  - postdeploy verify: `postdeploy_acceptance_passed`.
- Generated current AVAX/BTPC signal input on Tokyo:
  - runtime: `strategy-runtime-95655873b76c`;
  - strategy: `BTPC-001` / `BTPC-001-v0`;
  - symbol: `AVAX/USDT:USDT`;
  - side: `short`;
  - packet:
    `/home/ubuntu/brc-deploy/reports/rtf021-real-signal-pipeline/20260613Trtf021-1707ad58/avax-btpc-current-signal-packet.json`;
  - signal input:
    `/home/ubuntu/brc-deploy/reports/rtf021-real-signal-pipeline/20260613Trtf021-1707ad58/avax-btpc-current-signal-input.json`;
  - status: `observe_only`;
  - evaluation blocker: `strategy_signal_not_would_enter`.
- Ran RTF-020 real-signal pipeline probe:
  - report:
    `/home/ubuntu/brc-deploy/reports/rtf021-real-signal-pipeline/20260613Trtf021-1707ad58/avax-btpc-real-signal-pipeline.json`;
  - status: `blocked_at_strategy_signal_intent_draft_source`;
  - blocked stage: `strategy_signal_intent_draft_source`;
  - blockers:
    `intent_draft_source:strategy_signal_not_would_enter` and
    `intent_draft_source:scheduler_shadow_candidate_not_created`;
  - stage statuses: `intent_draft_source=blocked`.
- Probe safety:
  - sample rehearsal was not used;
  - local registration was not attempted;
  - local registration was not recorded;
  - first-real-submit action was not called;
  - exchange arm stayed disabled;
  - exchange write stayed false;
  - no withdrawal or transfer occurred.

## 2026-06-13 (RTF-020 Real Strategy Signal Scoped Local Registration Pipeline Local Proof)

- Confirmed current mainline workspace and branch before implementation:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - starting HEAD: `17a93db9`.
- Added `scripts/runtime_real_signal_scoped_local_registration_pipeline.py`:
  - accepts a real `StrategyFamilySignalInput` JSON;
  - calls the existing RTF-014 intent-draft-source API flow;
  - calls the existing RTF-015 persisted-draft-source readiness API flow;
  - calls the existing official submit handoff API flow;
  - calls the existing fresh submit authorization binding API flow;
  - calls the existing official evidence chain probe;
  - calls the existing scoped local-registration proof wrapper.
- Pipeline behavior:
  - does not use sample rehearsal fallback;
  - stops at `blocked_at_strategy_signal_intent_draft_source` when the signal
    is not ready;
  - requires explicit readiness evidence only after the signal source is ready;
  - reaches `ready_for_real_signal_scoped_local_registration_proof` in dry-run
    when all upstream official stages are ready;
  - keeps exchange arm disabled and first-real-submit action uncalled.
- Added focused tests:
  - blocked strategy signal stops at the source stage and performs no downstream
    API calls;
  - ready real-signal path reaches scoped local-registration dry-run through
    source, readiness, handoff, binding, evidence chain, and scoped proof.
- Verification passed:
  - `pytest -q tests/unit/test_runtime_real_signal_scoped_local_registration_pipeline.py`
    with `2 passed`;
  - `pytest -q tests/unit/test_runtime_official_evidence_chain_from_binding.py tests/unit/test_runtime_scoped_local_order_adapter_boundary_from_evidence.py tests/unit/test_runtime_scoped_local_registration_proof_from_evidence.py tests/unit/test_runtime_real_signal_scoped_local_registration_pipeline.py`
    with `10 passed`;
  - `python3 -m compileall scripts/runtime_real_signal_scoped_local_registration_pipeline.py tests/unit/test_runtime_real_signal_scoped_local_registration_pipeline.py`;
  - `git diff --check`.
- Deployment:
  - not deployed in this local proof stage.
- Safety:
  - no Tokyo action occurred;
  - no sample rehearsal artifact was used;
  - no exchange write occurred;
  - no first-real-submit action occurred;
  - no real exchange order was submitted;
  - no withdrawal or transfer occurred.

## 2026-06-13 (RTF-019 Tokyo Deploy + RTF-018 Dry-run Probe)

- Confirmed current mainline workspace and branch before deployment:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - target HEAD: `827de81309e5e085674f881dc1606ece8684d381`.
- Confirmed Tokyo baseline before deployment:
  - current release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-842de9bd-20260613Trtf016-evidence-wrapper`;
  - current manifest head:
    `842de9bd50f87295e5091343c98124168177b354`;
  - health: `status=ok`, `runtime_bound=true`, `live_ready=false`.
- Built deploy artifacts under:
  - `output/tokyo-git-deploy-827de813-rtf019-local-registration-proof`;
  - `git-deploy-plan.json`: `ready_for_owner_authorized_remote_git_deploy_plan`;
  - `owner-git-deploy-packet.json`: `ready_for_owner_git_deploy_decision`;
  - `git-deploy-dry-run.json`: `dry_run_ready`.
- Applied Tokyo deploy through the git-based deploy path:
  - release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-827de813-20260613Trtf019-local-registration-proof`;
  - apply report:
    `output/tokyo-git-deploy-827de813-rtf019-local-registration-proof/git-deploy-apply-report.json`;
  - status: `applied`;
  - commands: `16/16`;
  - effects: remote files modified, database backup created, migrations run,
    service restarted;
  - no `ExecutionIntent`, no order, no `OrderLifecycle`, no exchange call.
- Postdeploy checks passed:
  - health: `status=ok`, `runtime_bound=true`, `live_ready=false`;
  - read-only probe: `ready_for_controlled_deploy_preflight`;
  - postdeploy verify: `postdeploy_acceptance_passed`.
- Tokyo RTF-018 dry-run probe reports:
  - directory:
    `/home/ubuntu/brc-deploy/reports/rtf019-scoped-local-registration-proof/20260613Trtf019-827de813`;
  - sample rehearsal:
    `sample-rehearsal-dry-run-blocked.json`;
    status `blocked_scoped_local_registration_proof_dry_run`;
    blockers `sample_rehearsal_local_registration_not_allowed` and
    `sample_rehearsal_execute_not_allowed`;
  - scoped proof dry-run:
    `scoped-local-registration-proof-dry-run-ready.json`;
    status `ready_for_scoped_local_registration_proof_dry_run`.
- Probe safety:
  - local registration was not attempted;
  - local registration was not recorded;
  - first-real-submit action was not called;
  - exchange arm stayed disabled;
  - exchange write stayed false;
  - post-submit accounting was not called;
  - no withdrawal or transfer occurred.

## 2026-06-13 (RTF-018 Scoped Local Registration Proof Orchestrator Local Proof)

- Confirmed current mainline workspace and branch before implementation:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - starting HEAD: `77e124c4`.
- Added `scripts/runtime_scoped_local_registration_proof_from_evidence.py`:
  - runs the RTF-017 boundary classifier first;
  - keeps default mode as dry-run with no API calls;
  - refuses sample rehearsal execution unless explicitly allowed;
  - can run a deliberate `--execute-scoped-local-registration-proof` mode
    that calls the existing official `runtime_first_real_submit_api_flow.py`
    arm path with `--skip-exchange-arm` semantics;
  - still requires the existing
    `OWNER_APPROVED_RUNTIME_LOCAL_REGISTRATION_PREP` confirmation value before
    local registration can occur.
- Execution scope:
  - local-registration-only proof can record the official
    `RuntimeExecutionOrderLifecycleAdapterResult`;
  - exchange arm is disabled;
  - first-real-submit action is not called;
  - post-submit accounting and reconciliation are not called;
  - withdrawal and transfer remain impossible through this wrapper.
- Added focused tests:
  - sample rehearsal dry-run remains blocked without API calls;
  - execute mode blocks when the local registration env confirmation is
    missing;
  - execute mode records scoped local registration when the env confirmation is
    present, without exchange-arm or first-real-submit action calls.
- Verification passed:
  - `pytest -q tests/unit/test_runtime_scoped_local_registration_proof_from_evidence.py tests/unit/test_runtime_scoped_local_order_adapter_boundary_from_evidence.py`
    with `6 passed`;
  - `pytest -q tests/unit/test_runtime_official_evidence_chain_from_binding.py tests/unit/test_runtime_scoped_local_order_adapter_boundary_from_evidence.py tests/unit/test_runtime_scoped_local_registration_proof_from_evidence.py`
    with `8 passed`;
  - `python3 -m compileall scripts/runtime_scoped_local_registration_proof_from_evidence.py tests/unit/test_runtime_scoped_local_registration_proof_from_evidence.py`;
  - `git diff --check`.
- Deployment:
  - not deployed in this local proof stage.
- Safety:
  - no Tokyo action occurred;
  - no live exchange write occurred;
  - no first-real-submit action occurred;
  - no real exchange order was submitted;
  - no withdrawal or transfer occurred.

## 2026-06-13 (RTF-017 Scoped Local Order Adapter Boundary Local Proof)

- Confirmed current mainline workspace and branch before implementation:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - starting HEAD: `0f1e9886`.
- Added `scripts/runtime_scoped_local_order_adapter_boundary_from_evidence.py`:
  - reads an RTF-016 evidence-chain report;
  - verifies required machine evidence IDs:
    `trusted_submit_fact_snapshot_id`, `submit_idempotency_policy_id`, and
    `protection_creation_failure_policy_id`;
  - verifies the chain is stopped at the expected
    `RuntimeExecutionOrderLifecycleAdapterResult` boundary;
  - blocks `sample_rehearsal` by default with
    `blocked_sample_rehearsal_local_registration_not_allowed`;
  - allows an explicitly scoped `scoped_local_registration_proof` to emit
    `ready_for_scoped_local_registration_proof`;
  - emits a local-registration-only command preview with required
    `OWNER_APPROVED_RUNTIME_LOCAL_REGISTRATION_PREP` but does not run it.
- Added focused tests:
  - sample rehearsal cannot proceed to local registration by default;
  - explicit scoped local-registration proof can become ready;
  - missing machine evidence blocks the boundary.
- Verification passed:
  - `pytest -q tests/unit/test_runtime_scoped_local_order_adapter_boundary_from_evidence.py tests/unit/test_runtime_official_evidence_chain_from_binding.py`
    with `5 passed`;
  - `python3 -m compileall scripts/runtime_scoped_local_order_adapter_boundary_from_evidence.py tests/unit/test_runtime_scoped_local_order_adapter_boundary_from_evidence.py`;
  - `git diff --check`.
- Deployment:
  - not deployed in this local proof stage.
- Safety:
  - no API call occurred from the new wrapper;
  - no local order registration occurred;
  - no `OrderLifecycle` call occurred;
  - no exchange write occurred;
  - no runtime budget mutation occurred;
  - no withdrawal or transfer occurred.
- Program cleanup invariant:
  - `RTF-CLEANUP-001` remains mandatory after the repeatable
    strategy-driven runtime main chain is proven and before the runtime mainline
    can be called complete.

## 2026-06-13 (RTF-016 Official Evidence Chain Wrapper Local Proof)

- Confirmed current mainline workspace and branch before implementation:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - starting HEAD: `04e09e0d`.
- Added `scripts/runtime_official_evidence_chain_from_binding.py`:
  - reads an RTF-013 fresh authorization binding report;
  - extracts `fresh_submit_authorization_id` automatically;
  - runs the existing official `runtime_first_real_submit_api_flow.py` in
    `disabled-smoke` mode;
  - keeps `owner_confirmed_for_first_real_submit_action=false`;
  - runs evidence-preparation after the expected official prerequisite block;
  - classifies the result as
    `prepared_machine_evidence_blocked_before_local_order_adapter` when
    machine evidence is prepared and the remaining blocker is
    `RuntimeExecutionOrderLifecycleAdapterResult`.
- Local proof:
  - wrapper prepares/collects `trusted_submit_fact_snapshot_id`,
    `submit_idempotency_policy_id`, and
    `protection_creation_failure_policy_id`;
  - wrapper refuses binding reports that do not contain a fresh submit
    authorization ID;
  - wrapper does not create orders, call OrderLifecycle, call exchange, mutate
    runtime budget, or create withdrawal/transfer.
- Focused verification passed:
  - `pytest -q tests/unit/test_runtime_official_evidence_chain_from_binding.py tests/unit/test_runtime_first_real_submit_api_flow.py -k 'official_evidence_chain_from_binding or disabled_smoke_reports_missing_prerequisite_detail or disabled_smoke_prerequisite_probe_can_be_skipped'`
    with `4 passed, 21 deselected`;
  - `python3 -m compileall -q scripts/runtime_official_evidence_chain_from_binding.py tests/unit/test_runtime_official_evidence_chain_from_binding.py`;
  - `git diff --check`.
- Tokyo fact already observed before this wrapper existed:
  - report:
    `/home/ubuntu/brc-deploy/reports/rtf016-official-evidence-chain/20260613Trtf016-c419e1de/avax-btpc-sample-disabled-smoke-with-evidence-prep.json`;
  - blocker:
    `preview_disabled_first_real_submit_action_http_404`;
  - warning:
    `RuntimeExecutionOrderLifecycleAdapterResult not found`;
  - prepared IDs:
    `trusted_submit_fact_snapshot_id`,
    `submit_idempotency_policy_id`,
    `protection_creation_failure_policy_id`,
    `post_submit_budget_settlement_persistence_evidence_id`.
- Deployment:
  - the wrapper is not yet deployed to Tokyo in this stage.
- Safety:
  - no exchange write occurred;
  - no exchange order submit occurred;
  - no `OrderLifecycle` submit occurred;
  - no local order was created by the wrapper;
  - no runtime state mutation occurred;
  - no withdrawal or transfer occurred.

## 2026-06-13 (RTF-016 Tokyo Deploy + Official Evidence Chain Probe)

- Pushed `program/live-safe-v1` to origin:
  - target commit: `842de9bd50f87295e5091343c98124168177b354`.
- Deployed RTF-016 wrapper to Tokyo with the git-based deploy path:
  - release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-842de9bd-20260613Trtf016-evidence-wrapper`;
  - previous release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-c419e1de-20260612Trtf015-readiness-bridge`;
  - manifest head:
    `842de9bd50f87295e5091343c98124168177b354`;
  - health: `GET http://127.0.0.1:18080/api/health` returned
    `status=ok`, `runtime_bound=true`, `live_ready=false`.
- Deploy proof:
  - local report directory:
    `output/tokyo-git-deploy-842de9bd-rtf016-wrapper`;
  - plan: `git-deploy-plan.json`;
  - owner packet: `owner-git-deploy-packet.json`;
  - dry-run: `git-deploy-dry-run.json`;
  - apply report: `git-deploy-apply-report.json`;
  - apply status: `applied`.
- Tokyo RTF-016 wrapper proof:
  - report:
    `/home/ubuntu/brc-deploy/reports/rtf016-official-evidence-chain/20260613Trtf016-842de9bd/avax-btpc-sample-official-evidence-chain-from-binding.json`;
  - status:
    `prepared_machine_evidence_blocked_before_local_order_adapter`;
  - fresh submit authorization:
    `runtime-submit-authorization-intent_rt_8db0b144cf1b7c4085e5c804`;
  - prepared / available evidence IDs:
    `trusted_submit_fact_snapshot_id`,
    `submit_idempotency_policy_id`,
    `protection_creation_failure_policy_id`,
    `post_submit_budget_settlement_persistence_evidence_id`;
  - remaining blocker:
    `preview_disabled_first_real_submit_action_http_404`;
  - warning:
    `RuntimeExecutionOrderLifecycleAdapterResult not found`;
  - interpretation:
    the chain is no longer blocked by manual evidence-ID movement. It is
    blocked at the expected official local-order adapter boundary.
- Follow-up:
  - added `RTF-017` for scoped local order adapter evidence boundary;
  - do not use sample rehearsal artifacts as if they were a real attempt;
  - proceed through official local registration only for a real ready strategy
    signal or a deliberately scoped non-exchange local-registration proof.
- Safety:
  - no exchange write occurred;
  - no exchange order submit occurred;
  - no `OrderLifecycle` submit occurred;
  - no local order was created by the wrapper;
  - no runtime state mutation occurred;
  - no withdrawal or transfer occurred.

## 2026-06-12 (RTF-015 Persisted Draft Source Readiness Bridge Local Proof)

- Confirmed current mainline workspace and branch before implementation:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - starting HEAD: `2f0d170c`.
- Added `RuntimePersistedDraftSourceReadinessBridgeService`:
  - accepts `RuntimeStrategySignalIntentDraftSourcePacket` from RTF-014;
  - refuses blocked or incomplete draft sources as strategy-planning blockers;
  - materializes an explicit `RuntimeNextAttemptStrategyPlanningPacket`
    compatibility evidence packet only for readiness consumption;
  - marks `source_authorization_id` as `persisted-draft-source:*`, so it is
    not confused with a consumable submit authorization;
  - preserves the existing RTF-013 fresh submit authorization binding boundary.
- Added API and script surfaces:
  - `POST /api/trading-console/strategy-runtimes/{runtime_instance_id}/persisted-draft-source-readiness-previews`;
  - `scripts/runtime_persisted_draft_source_readiness_api_flow.py`.
- Local proof:
  - a persisted ready draft source can produce
    `ready_for_executable_submit` when current readiness evidence is complete;
  - a blocked source remains blocked and carries source blockers through the
    readiness packet;
  - the API rejects runtime mismatches;
  - the script posts a non-executing readiness request and reports safety
    invariants.
- Focused verification passed:
  - `pytest -q tests/unit/test_runtime_persisted_draft_source_readiness_bridge.py tests/unit/test_runtime_strategy_signal_intent_draft_source.py tests/unit/test_runtime_executable_submit_readiness_service_api.py tests/unit/test_trading_console_readmodels.py -k 'persisted_draft_source or intent_draft_source or executable_submit_readiness or trading_console_router_keeps_read_models_get_only_and_posts_allowlisted'`
    with `17 passed, 50 deselected`;
  - `python3 -m compileall -q` for the new bridge service, API, script, and
    test file.
- Deployment:
  - not deployed in this stage.
- Safety:
  - no recorded `ExecutionIntent` was created;
  - no official submit endpoint was called;
  - no `real_gateway_action` was requested;
  - no exchange write occurred;
  - no exchange order submit occurred;
  - no local order was created;
  - no `OrderLifecycle` call occurred;
  - no runtime state mutation occurred;
  - no withdrawal or transfer occurred.

## 2026-06-12 (RTF-015 Tokyo Deploy + Persisted Draft Source Handoff Probe)

- Pushed `program/live-safe-v1` to origin:
  - target commit: `c419e1de51fff3d7b09a3dc1b33329508fc82a11`;
  - included prior docs commit `2f0d170c`.
- Deployed RTF-015 bridge to Tokyo with the git-based deploy path:
  - release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-c419e1de-20260612Trtf015-readiness-bridge`;
  - previous release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-9877fbdc-20260612Trtf015-draft-source-probe`;
  - manifest head:
    `c419e1de51fff3d7b09a3dc1b33329508fc82a11`;
  - health: `GET http://127.0.0.1:18080/api/health` returned
    `status=ok`, `runtime_bound=true`, `live_ready=false`.
- Deploy proof:
  - local report directory:
    `output/tokyo-git-deploy-c419e1de-rtf015-bridge`;
  - plan: `git-deploy-plan.json`;
  - owner packet: `owner-git-deploy-packet.json`;
  - dry-run: `git-deploy-dry-run.json`;
  - apply report: `git-deploy-apply-report.json`;
  - apply status: `applied`.
- Tokyo RTF-015 sample rehearsal proof:
  - report directory:
    `/home/ubuntu/brc-deploy/reports/rtf015-persisted-draft-source/20260612Trtf015-c419e1de`;
  - source:
    `avax-btpc-sample-intent-draft-source.json` from the prior RTF-014 sample
    rehearsal, explicitly marked as not current live alpha;
  - readiness report:
    `avax-btpc-sample-persisted-source-readiness.json`;
  - readiness status: `ready_for_executable_submit`;
  - official handoff report:
    `avax-btpc-sample-official-handoff.json`;
  - handoff status: `ready_for_official_submit_call`;
  - fresh authorization binding report:
    `avax-btpc-sample-fresh-auth-binding.json`;
  - binding status: `created_intent_and_authorization`;
  - created execution intent:
    `intent_rt_8db0b144cf1b7c4085e5c804`;
  - created fresh submit authorization:
    `runtime-submit-authorization-intent_rt_8db0b144cf1b7c4085e5c804`;
  - created from ready draft:
    `runtime-intent-draft-order-candidate-083a16378429`.
- Disabled smoke result:
  - bound-auth handoff report:
    `avax-btpc-sample-official-handoff-bound-auth.json`;
  - disabled smoke report:
    `avax-btpc-sample-disabled-smoke-from-bound-auth.json`;
  - the official endpoint was reached with
    `owner_confirmed_for_first_real_submit_action=false`;
  - result: `blocked`, `http_status=404`;
  - blocker: `RuntimeExecutionOrderLifecycleAdapterResult not found`;
  - interpretation: the sample path stopped at the official local-order
    prerequisite because the readiness evidence used synthetic IDs and no local
    order-lifecycle adapter result was recorded.
- Current live AVAX/BTPC check:
  - report:
    `avax-btpc-current-live-intent-draft-source.json`;
  - status: `blocked`;
  - blockers:
    `strategy_signal_not_would_enter`,
    `scheduler_shadow_candidate_not_created`;
  - no signal evaluation, order candidate, or intent draft was created.
- Follow-up:
  - added `RTF-016` for official evidence-chain generation from the bound
    authorization;
  - do not force local order registration for sample rehearsal artifacts;
  - proceed to official evidence records only when using a real ready strategy
    signal or a deliberately scoped non-exchange local-registration proof.
- Safety:
  - no exchange write occurred;
  - no exchange order submit occurred;
  - no `OrderLifecycle` submit occurred;
  - no runtime state mutation occurred;
  - no withdrawal or transfer occurred;
  - sample RTF-013 binding did create a persisted `ExecutionIntent` and fresh
    submit authorization, but did not create orders or call exchange.

## 2026-06-12 (RTF-014 Persisted Strategy Signal Intent Draft Source Local Proof)

- Confirmed current mainline workspace and branch before implementation:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - starting HEAD: `65c6b407`.
- Added `RuntimeStrategySignalIntentDraftSourceService`:
  - routes current `StrategyFamilySignalInput` through the existing scheduler
    / semantic gate;
  - requires explicit `allow_shadow_candidate_creation=true`;
  - requires explicit `allow_intent_draft_creation=true`;
  - requires `owner_reviewed=true` and `owner_confirmed_for_intent=true`
    before any ready draft is recorded;
  - records a persisted `RuntimeExecutionIntentDraft` from the created shadow
    `OrderCandidate` through the existing `RuntimeExecutionPlanningService`;
  - reports blocked scheduler, missing Owner review, or missing creation flags
    before creating draft records.
- Added API and script surfaces:
  - `POST /api/trading-console/strategy-runtimes/{runtime_instance_id}/strategy-signal-intent-draft-sources`;
  - `scripts/runtime_strategy_signal_intent_draft_source_api_flow.py`;
  - the script accepts either a raw `signal_input` JSON object or an
    observation-cycle report containing `signal_packet.signal_input`.
- Local proof:
  - success path creates persisted shadow `SignalEvaluation`, shadow
    `OrderCandidate`, and ready `RuntimeExecutionIntentDraft`;
  - blocked paths do not create draft records when Owner review/intent
    confirmation or explicit creation flags are missing;
  - blocked scheduler planning does not call the execution planner;
  - API path rejects runtime mismatch.
- Focused verification passed:
  - `pytest -q tests/unit/test_runtime_strategy_signal_intent_draft_source.py tests/unit/test_trading_console_readmodels.py -k 'intent_draft_source or trading_console_router_keeps_read_models_get_only_and_posts_allowlisted'`
    with `8 passed, 50 deselected`;
  - adjacent strategy/scheduler/RTF-013 regression:
    `23 passed, 64 deselected`;
  - `python3 -m compileall -q` for the new service, API, script, and test
    files;
  - `git diff --check`.
- Deployment:
  - not deployed in this stage.
- Safety:
  - no recorded `ExecutionIntent` was created;
  - no official submit endpoint was called;
  - no `real_gateway_action` was requested;
  - no exchange write occurred;
  - no exchange order submit occurred;
  - no local order was created;
  - no `OrderLifecycle` call occurred;
  - no runtime state mutation occurred;
  - no withdrawal or transfer occurred.

## 2026-06-12 (Owner Correction: RTF-CLEANUP-001 Is A Mainline Exit Condition)

- Confirmed correct mainline workspace and branch before the planning update:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - starting HEAD: `9877fbdc`.
- Owner clarified that downgraded isolation cleanup for historical pre-attempt
  / first-real-submit compatibility must not be forgotten after the main
  runtime chain is proven.
- Program update:
  - `RTF-CLEANUP-001` is now recorded as
    `TODO / MANDATORY_AFTER_MAIN_CHAIN`;
  - `docs/ops/live-safe-v1-program.md` now defines it as a runtime mainline
    exit condition;
  - the cleanup remains deferred until the repeatable strategy-driven runtime
    chain is proven, so it does not slow the current real-submit convergence.
- Safety:
  - docs-only planning update;
  - no code change;
  - no deployment;
  - no exchange write;
  - no order submit;
  - no `OrderLifecycle` call;
  - no withdrawal or transfer.

## 2026-06-12 (RTF-013 Tokyo Deploy + Binding Probe)

- Deployed RTF-013 to Tokyo with the git-based deploy path:
  - release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-0afbcbf2-20260612Trtf013-binding-probe`;
  - current symlink:
    `/home/ubuntu/brc-deploy/app/current`;
  - manifest head:
    `0afbcbf229037caedac01f4bd17428f90ef176b4`;
  - service: `brc-owner-console-backend.service` active;
  - health: `GET http://127.0.0.1:18080/api/health` returned
    `status=ok`, `runtime_bound=true`, `live_ready=false`.
- Deploy execution result:
  - status: `applied`;
  - commands executed: `16`;
  - database backup created: `true`;
  - migrations run: `true`;
  - services restarted: `true`.
- Ran RTF-013 fresh authorization binding probe on Tokyo:
  - remote report:
    `/home/ubuntu/brc-deploy/reports/rtf013-fresh-submit-authorization-binding/20260612Trtf013-0afbcbf2/fresh-auth-binding-from-positive-handoff.json`;
  - local mirror:
    `output/rtf013-tokyo/remote-report-20260612Trtf013-0afbcbf2/fresh-auth-binding-from-positive-handoff.json`;
  - input handoff:
    `/home/ubuntu/brc-deploy/reports/rtf010-official-submit-handoff/20260612Trtf010-be9f91fa/handoff-api-positive-disabled-smoke.json`.
- Probe result:
  - `status=blocked`;
  - `http_status=200`;
  - blockers:
    `ready_runtime_execution_intent_draft_not_found`,
    `resolution:fresh_submit_authorization_not_found`;
  - `binding_source=unresolved`;
  - `fresh_submit_authorization_id=null`;
  - `execution_intent_id=null`;
  - `runtime_execution_intent_draft_id=null`;
  - `ready_for_disabled_smoke_call=false`.
- Interpretation:
  - RTF-013 deployed correctly and refused to convert the old RTF-010
    rehearsal handoff into a fake authorization;
  - the RTF-010 positive handoff is still useful compatibility evidence, but
    it is not a persisted mainline candidate/draft source;
  - the next runtime-chain step is not another manual evidence retry. It is a
    persisted strategy-signal / order-candidate / intent-draft source that can
    feed RTF-013 binding.
- Safety:
  - no official submit endpoint was called;
  - no `real_gateway_action` was requested;
  - no exchange write occurred;
  - no exchange order submit occurred;
  - no local order was created;
  - no `OrderLifecycle` call occurred;
  - no runtime state mutation occurred;
  - no withdrawal or transfer occurred.

## 2026-06-12 (RTF-013 Persisted Fresh Authorization Binding Local Proof)

- Confirmed current mainline workspace and branch before implementation:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - starting HEAD: `3956d308`.
- Added `RuntimeFreshSubmitAuthorizationBindingPacket`:
  - binds a ready official-submit handoff to a persisted, non-consumed
    `RuntimeExecutionSubmitAuthorization`;
  - can reuse a resolved existing fresh authorization;
  - can create a fresh submit authorization from an existing recorded
    `ExecutionIntent`;
  - can create a recorded `ExecutionIntent` from the latest ready
    `RuntimeExecutionIntentDraft`, then create the submit authorization;
  - reports missing fresh authorization / intent / ready draft as structured
    blockers instead of asking the Owner to hand-copy evidence IDs.
- Added `RuntimeFreshSubmitAuthorizationBindingService`:
  - resolves fresh authorization first through RTF-012;
  - preserves consumed-source authorization replay-only semantics;
  - keeps the created authorization in the existing submit-authorization
    domain model;
  - does not call the official first-real-submit endpoint.
- Added API and script surfaces:
  - `POST /api/trading-console/strategy-runtimes/{runtime_instance_id}/official-submit-handoff-fresh-authorizations/bind`;
  - `scripts/runtime_fresh_submit_authorization_binding_api_flow.py`.
- Corrected ready-draft status handling:
  - the binding service now checks
    `RuntimeExecutionIntentDraftStatus.READY_FOR_INTENT_CREATION`;
  - the fresh authorization resolution snapshot now carries
    `runtime_execution_intent_draft_id`, `trial_binding_id`,
    `strategy_family_id`, and `strategy_family_version_id`.
- Focused verification passed:
  - `pytest -q tests/unit/test_runtime_fresh_submit_authorization_binding.py tests/unit/test_runtime_fresh_submit_authorization_resolution.py tests/unit/test_trading_console_readmodels.py -k 'fresh_submit_authorization or trading_console_router_keeps_read_models_get_only_and_posts_allowlisted'`
    with `19 passed, 50 deselected`;
  - adjacent handoff / disabled-smoke regression:
    `30 passed, 50 deselected`;
  - `python3 -m compileall -q` for the new domain, service, API, script, and
    test files;
  - `git diff --check`.
- Deployment:
  - later deployed and probed in the RTF-013 Tokyo stage above.
- Safety:
  - no official submit endpoint was called;
  - no `real_gateway_action` was requested;
  - no exchange write occurred;
  - no exchange order submit occurred;
  - no local order was created;
  - no `OrderLifecycle` call occurred;
  - no runtime state mutation occurred;
  - no withdrawal or transfer occurred.

## 2026-06-12 (RTF-012 Tokyo Deploy + Fresh Authorization Resolution Probe)

- Deployed RTF-012 to Tokyo with the git-based deploy path:
  - release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-95d3a365-20260612Trtf012-fresh-auth-resolution-probe`;
  - current symlink:
    `/home/ubuntu/brc-deploy/app/current`;
  - manifest head:
    `95d3a365aaaacd46f870bbb73d3e35b8201fa6b9`;
  - service: `brc-owner-console-backend.service` active;
  - health: `GET http://127.0.0.1:18080/api/health` returned
    `status=ok`, `runtime_bound=true`, `live_ready=false`.
- Deploy execution result:
  - status: `applied`;
  - commands executed: `16`;
  - database backup created: `true`;
  - migrations run: `true`;
  - services restarted: `true`;
  - exchange called: `false`;
  - order created: `false`;
  - `OrderLifecycle` called: `false`;
  - `ExecutionIntent` created: `false`.
- Ran RTF-012 fresh authorization resolution probes on Tokyo:
  - remote report dir:
    `/home/ubuntu/brc-deploy/reports/rtf012-fresh-submit-authorization-resolution/20260612Trtf012-95d3a365`;
  - local mirror:
    `output/rtf012-tokyo/remote-report-20260612Trtf012-95d3a365`;
  - blocked handoff input:
    `fresh-auth-resolution-from-blocked-handoff.json`;
  - positive handoff input:
    `fresh-auth-resolution-from-positive-handoff.json`.
- Probe results:
  - blocked handoff path: `status=blocked`, `http_status=200`,
    blockers include `handoff_not_ready_for_official_submit_call`,
    release-gate blockers, and `fresh_submit_authorization_not_found`;
  - positive handoff path: `status=blocked`, `http_status=200`,
    blockers `["fresh_submit_authorization_not_found"]`,
    `resolution_source=order_candidate_latest`,
    `resolved_fresh_submit_authorization_id=null`,
    `ready_for_disabled_smoke_call=false`;
  - the RTF-011 official endpoint `404` is now correctly represented one step
    earlier as a structured fresh-authorization resolution blocker.
- Follow-up implication:
  - next runtime-chain step is persisted fresh submit authorization creation /
    binding for a ready handoff, while preserving consumed authorization
    replay-only semantics and duplicate-submit protection.
- Safety:
  - the resolution API did not create fresh authorization records;
  - it did not call the official first-real-submit endpoint;
  - no `real_gateway_action` was requested;
  - no exchange write occurred;
  - no exchange order submit occurred;
  - no `OrderLifecycle` call occurred;
  - no `ExecutionIntent` was created;
  - no withdrawal or transfer occurred.

## 2026-06-12 (RTF-012 Fresh Submit Authorization Resolution Local Proof)

- Confirmed current mainline workspace and branch before implementation:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - starting HEAD: `28d4f902`.
- Added `RuntimeFreshSubmitAuthorizationResolutionPacket`:
  - resolves a persisted `RuntimeExecutionSubmitAuthorization` for a ready
    official-submit handoff;
  - validates the fresh authorization is not the consumed source
    authorization;
  - validates runtime, order candidate, signal evaluation, and submit-state
    compatibility;
  - refuses blocked handoffs and `real_gateway_action` handoffs;
  - emits the official disabled-smoke endpoint path using the resolved
    persisted authorization ID;
  - does not create authorizations or call the official submit endpoint.
- Added `RuntimeFreshSubmitAuthorizationResolutionService`:
  - can resolve by explicit requested authorization ID;
  - can resolve by handoff authorization ID;
  - can fall back to latest persisted authorization by `order_candidate_id`;
  - reports missing authorization as a structured blocker instead of treating
    rehearsal IDs as usable.
- Added API and script surfaces:
  - `POST /api/trading-console/strategy-runtimes/{runtime_instance_id}/official-submit-handoff-fresh-authorizations/resolve`;
  - `scripts/runtime_fresh_submit_authorization_resolution_api_flow.py`.
- Focused verification passed:
  - `pytest -q tests/unit/test_runtime_fresh_submit_authorization_resolution.py tests/unit/test_runtime_official_submit_handoff.py tests/unit/test_trading_console_readmodels.py -k 'fresh_submit_authorization or official_submit_handoff or trading_console_router_keeps_read_models_get_only_and_posts_allowlisted'`
    with `18 passed, 50 deselected`;
  - adjacent handoff / disabled-smoke regression:
    `34 passed, 68 deselected`;
  - `python3 -m compileall -q` for the new domain, service, API, script, and
    test files;
  - `git diff --check`.
- Deployment:
  - later deployed and probed in the RTF-012 Tokyo stage above.
- Safety:
  - no fresh authorization is created by the resolver;
  - no official submit endpoint is called by the resolver;
  - no real gateway action is requested;
  - no exchange write occurred;
  - no exchange order submit occurred;
  - no `OrderLifecycle` call occurred;
  - no `ExecutionIntent` was created;
  - no withdrawal or transfer occurred.

## 2026-06-12 (RTF-011 Tokyo Deploy + Disabled Smoke Handoff Probe)

- Deployed RTF-011 to Tokyo with the git-based deploy path:
  - initial release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-36c0f569-20260612Trtf011-disabled-smoke-probe`;
  - report-safety fix release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-b3e68cff-20260612Trtf011-disabled-smoke-probe-fix`;
  - current symlink:
    `/home/ubuntu/brc-deploy/app/current`;
  - manifest head:
    `b3e68cff561dd428c2632731fd2704c3238f785d`;
  - service: `brc-owner-console-backend.service` active;
  - health: `GET http://127.0.0.1:18080/api/health` returned
    `status=ok`, `runtime_bound=true`, `live_ready=false`.
- Deploy execution result for the final fix release:
  - status: `applied`;
  - commands executed: `16`;
  - database backup created: `true`;
  - migrations run: `true`;
  - services restarted: `true`;
  - exchange called: `false`;
  - order created: `false`;
  - `OrderLifecycle` called: `false`;
  - `ExecutionIntent` created: `false`.
- Ran RTF-011 disabled-smoke handoff probes on Tokyo:
  - remote report dir:
    `/home/ubuntu/brc-deploy/reports/rtf011-official-disabled-smoke/20260612Trtf011-b3e68cff`;
  - local mirror:
    `output/rtf011-tokyo/remote-report-20260612Trtf011-b3e68cff`;
  - blocked handoff input:
    `disabled-smoke-from-blocked-handoff.json`;
  - positive handoff input:
    `disabled-smoke-from-positive-handoff.json`.
- Probe results:
  - blocked handoff path: `status=blocked`,
    `blocked_stage=handoff_precondition`, `http_status=0`,
    `calls_official_submit_endpoint=false`;
  - positive handoff path: `status=blocked`,
    `blocked_stage=official_first_real_submit_action`, `http_status=404`,
    blockers `["official_first_real_submit_action_http_404"]`,
    `calls_official_submit_endpoint=true`;
  - positive handoff used a rehearsal fresh authorization ID from RTF-010, so
    the official endpoint was reachable but could not resolve a persisted fresh
    submit authorization.
- Follow-up implication:
  - next runtime-chain step is fresh submit authorization resolution / runtime
    grant binding before a disabled-smoke call can reach
    `exchange_submit_execution_disabled` on Tokyo.
- Safety:
  - no `real_gateway_action` was requested;
  - `owner_confirmed_for_first_real_submit_action=false`;
  - no exchange write occurred;
  - no exchange order submit occurred;
  - no `OrderLifecycle` call occurred;
  - no `ExecutionIntent` was created;
  - no withdrawal or transfer occurred.

## 2026-06-12 (RTF-011 Official Submit Disabled Smoke From Handoff Local Proof)

- Confirmed current mainline workspace and branch before implementation:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - starting HEAD: `cc890a92`.
- Added `scripts/runtime_official_submit_disabled_smoke_from_handoff.py`:
  - consumes a ready `RuntimeOfficialSubmitHandoffPacket`;
  - refuses blocked handoff packets before calling the official endpoint;
  - refuses `real_gateway_action` handoff packets;
  - calls the existing official first-real-submit action endpoint only with
    `owner_confirmed_for_first_real_submit_action=false`;
  - expects the official response status
    `exchange_submit_execution_disabled`;
  - reports unexpected official endpoint status as a blocker.
- Added focused tests:
  - ready disabled-smoke handoff calls the official endpoint with frozen query
    evidence IDs and `owner_confirmed_for_first_real_submit_action=false`;
  - blocked handoff does not call the official endpoint;
  - real-gateway handoff is refused by this disabled-smoke flow;
  - unexpected official endpoint response is reported as blocked;
  - CLI stdout remains JSON-only.
- Focused verification passed:
  - `pytest -q tests/unit/test_runtime_official_submit_disabled_smoke_from_handoff.py tests/unit/test_runtime_official_submit_handoff.py tests/unit/test_runtime_official_submit_handoff_api_flow.py`
    with `14 passed`;
  - `python3 -m compileall -q scripts/runtime_official_submit_disabled_smoke_from_handoff.py tests/unit/test_runtime_official_submit_disabled_smoke_from_handoff.py`.
- Deployment:
  - later deployed and probed in the RTF-011 Tokyo stage above.
- Safety:
  - the script can call the official first-real-submit endpoint only in
    disabled-smoke mode;
  - it does not request `real_gateway_action`;
  - no exchange order submit is enabled;
  - no `OrderLifecycle` call is expected;
  - no `ExecutionIntent` is created;
  - no withdrawal or transfer is created.

## 2026-06-12 (Owner Correction: Legacy Pre-attempt Cleanup Must Not Be Forgotten)

- Owner reiterated that historical pre-attempt / first-real-submit
  compatibility material must be downgraded and isolated after the main runtime
  chain is complete.
- Program interpretation:
  - do not remove these compatibility surfaces in the middle of current
    runtime-chain convergence;
  - do not let them remain as the default mental model after the runtime-level
    bounded-auto-attempt path is proven;
  - track the cleanup as a required follow-up item, not an optional nice-to-have.

## 2026-06-12 (RTF-010 Tokyo Deploy + Official Submit Handoff API Probe)

- Confirmed current mainline workspace and branch before deployment:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - target HEAD: `be9f91fa`.
- Pushed `program/live-safe-v1` from `5f7952f9` to `be9f91fa`.
- Deployed Tokyo with the git-based deploy path:
  - release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-be9f91fa-20260612Trtf010-handoff-api-probe`;
  - current symlink:
    `/home/ubuntu/brc-deploy/app/current`;
  - manifest head:
    `be9f91fa0997364908810ba1b704d1ffe8632ff5`;
  - service: `brc-owner-console-backend.service` active;
  - health: `GET http://127.0.0.1:18080/api/health` returned
    `status=ok`, `runtime_bound=true`, `live_ready=false`.
- Deploy execution result:
  - status: `applied`;
  - commands executed: `16`;
  - database backup created: `true`;
  - migrations run: `true`;
  - services restarted: `true`;
  - exchange called: `false`;
  - order created: `false`;
  - `OrderLifecycle` called: `false`;
  - `ExecutionIntent` created: `false`.
- Ran RTF-010 official submit handoff API probes on Tokyo:
  - remote report dir:
    `/home/ubuntu/brc-deploy/reports/rtf010-official-submit-handoff/20260612Trtf010-be9f91fa`;
  - local mirror:
    `output/rtf010-tokyo/remote-report-20260612Trtf010-be9f91fa`;
  - current BNB blocked path:
    `handoff-api-blocked.json`;
  - positive flat/review/gate-clear rehearsal:
    `handoff-api-positive-disabled-smoke.json`.
- Probe results:
  - blocked path: `status=blocked`, `http_status=200`,
    `ready_for_call=false`, blockers include
    `readiness_not_ready_for_executable_submit`,
    `readiness:strategy_planning_not_ready_for_final_gate_preflight`,
    `readiness:order_candidate_id_missing`, and release-gate blockers;
  - positive path: `status=ready_for_official_submit_call`,
    `http_status=200`, `ready_for_call=true`, blockers `[]`.
- Safety:
  - the RTF-010 API only previews the official submit handoff;
  - it did not call the official first-real-submit endpoint;
  - no exchange write occurred;
  - no exchange order submit occurred;
  - no `OrderLifecycle` call occurred;
  - no `ExecutionIntent` was created;
  - no withdrawal or transfer occurred.

## 2026-06-12 (RTF-009 Official Submit Handoff Local Proof)

- Confirmed current mainline workspace and branch before implementation:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - starting HEAD: `71b2cf51`.
- Added `RuntimeOfficialSubmitHandoffPacket`:
  - bridges a ready `RuntimeExecutableSubmitReadinessPacket` to the existing
    Trading Console official submit endpoint;
  - emits `POST /api/trading-console/runtime-execution-first-real-submit-actions/authorizations/{fresh_submit_authorization_id}`;
  - freezes the official query evidence IDs required by the existing
    `first_real_submit_action_for_authorization(...)` path;
  - blocks when `fresh_submit_authorization_id` is missing;
  - blocks when the fresh submit authorization reuses the consumed/source
    authorization;
  - keeps real gateway mode blocked unless
    `owner_confirmed_for_real_submit_action=true`;
  - does not call the official endpoint.
- Added `scripts/runtime_official_submit_handoff_from_readiness.py`:
  - reads RTF-008 readiness API artifacts;
  - emits a non-executing handoff report and operator action preview;
  - supports `disabled_smoke` and `real_gateway_action` modes.
- Local handoff dry-run artifacts:
  - `output/rtf009-handoff/handoff-blocked.json`:
    current BNB path remained `blocked` because readiness is blocked by
    active-position release / strategy-planning blockers;
  - `output/rtf009-handoff/handoff-positive-disabled-smoke.json`:
    positive flat/review/gate-clear rehearsal returned
    `ready_for_official_submit_call` with
    `owner_confirmed_for_first_real_submit_action=false`.
- Focused verification passed:
  - `pytest -q tests/unit/test_runtime_official_submit_handoff.py tests/unit/test_runtime_official_submit_handoff_from_readiness.py`
    with `9 passed`;
  - `pytest -q tests/unit/test_runtime_official_submit_handoff.py tests/unit/test_runtime_official_submit_handoff_from_readiness.py tests/unit/test_runtime_executable_submit_readiness.py tests/unit/test_runtime_executable_submit_readiness_from_reports.py tests/unit/test_runtime_executable_submit_readiness_service_api.py tests/unit/test_runtime_executable_submit_readiness_api_flow.py tests/unit/test_runtime_order_lifecycle_adapter_result.py -k 'first_real_submit_action_defaults_to_disabled_without_owner_final_action or first_real_submit_action_confirmed_uses_real_gateway_mode or runtime_official_submit_handoff or executable_submit_readiness'`
    with `30 passed, 80 deselected`;
  - `python3 -m compileall -q src/domain/runtime_official_submit_handoff.py scripts/runtime_official_submit_handoff_from_readiness.py tests/unit/test_runtime_official_submit_handoff.py tests/unit/test_runtime_official_submit_handoff_from_readiness.py`;
  - `git diff --check`.
- Deployment:
  - not deployed in this stage;
  - current Tokyo deployed release remains
    `brc-runtime-governance-bb232a32-20260612Trtf008-readiness-api-probe`.
- Safety:
  - no official endpoint call;
  - no PG read/write;
  - no exchange read/write;
  - no exchange order submit;
  - no `ExecutionIntent` creation;
  - no `OrderLifecycle.submit_order`;
  - no order creation/cancel/close;
  - no runtime state mutation;
  - no withdrawal or transfer.

## 2026-06-12 (RTF-008 Tokyo Deploy + Executable Readiness API Probe)

- Confirmed current mainline workspace and branch before deployment:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - target HEAD: `bb232a32`;
  - pushed `program/live-safe-v1` from `75d16acc` to `bb232a32`.
- Generated deploy artifacts:
  - git deploy plan:
    `output/rtf008-tokyo/git-deploy-plan-bb232a32.json`;
  - owner git deploy packet:
    `output/rtf008-tokyo/owner-git-deploy-packet-bb232a32.json`;
  - deploy dry-run:
    `output/rtf008-tokyo/git-deploy-dry-run-bb232a32.json`;
  - deploy apply report:
    `output/rtf008-tokyo/git-deploy-applied-bb232a32.json`.
- Deployed Tokyo with the git-based deploy path:
  - release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-bb232a32-20260612Trtf008-readiness-api-probe`;
  - current symlink:
    `/home/ubuntu/brc-deploy/app/current`;
  - manifest head:
    `bb232a324eb5f3f86aad8e6083051fe9107e7794`;
  - service: `brc-owner-console-backend.service` active;
  - health: `GET http://127.0.0.1:18080/api/health` returned
    `status=ok`, `runtime_bound=true`, `live_ready=false`.
- Deploy execution result:
  - status: `applied`;
  - commands executed: `16`;
  - database backup created: `true`;
  - migrations run: `true`;
  - services restarted: `true`;
  - exchange called: `false`;
  - order created: `false`;
  - `OrderLifecycle` called: `false`;
  - `ExecutionIntent` created: `false`.
- Ran RTF-008 executable readiness API probes on Tokyo:
  - remote report dir:
    `/home/ubuntu/brc-deploy/reports/rtf008-executable-submit-readiness/20260612Trtf008-bb232a32`;
  - local mirror:
    `output/rtf008-tokyo/remote-report-20260612Trtf008-bb232a32`;
  - current BNB blocked path:
    `readiness-api-blocked.json`;
  - positive flat/review/gate-clear rehearsal:
    `readiness-api-positive.json`.
- Probe results:
  - blocked path: `status=blocked`, `http_status=200`,
    blockers include `strategy_planning_not_ready_for_final_gate_preflight`,
    `order_candidate_id_missing`, and release-gate blockers;
  - positive path: `status=ready_for_executable_submit`, `http_status=200`,
    `executable_submit_ready=true`, blockers `[]`;
  - both reports kept `exchange_write_called=false` and
    `order_lifecycle_called=false`.
- Safety:
  - no exchange order submit;
  - no `ExecutionIntent` creation;
  - no `OrderLifecycle.submit_order`;
  - no order creation/cancel/close;
  - no runtime state mutation by readiness probe;
  - no withdrawal or transfer.

## 2026-06-12 (RTF-007 Executable Submit Readiness API Dry-run Proof)

- Confirmed current mainline workspace and branch before implementation:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - starting HEAD: `1cfaeec7`.
- Added `RuntimeExecutableSubmitReadinessService`:
  - builds non-executing readiness previews from a
    `RuntimeNextAttemptStrategyPlanningPacket`;
  - preserves source strategy-planning blockers / warnings;
  - delegates readiness classification to `RuntimeExecutableSubmitReadinessPacket`.
- Added Trading Console API:
  - `POST /api/trading-console/strategy-runtimes/{runtime_instance_id}/executable-submit-readiness-previews`;
  - request body requires a strategy planning packet and readiness evidence;
  - optional legacy first-real-submit packet is accepted as compatibility
    evidence;
  - runtime mismatch is rejected before preview building.
- Added `scripts/runtime_executable_submit_readiness_api_flow.py`:
  - calls the Trading Console readiness preview endpoint;
  - emits a local/Tokyo-friendly JSON artifact;
  - carries explicit no-side-effect safety invariants.
- Focused verification passed:
  - `pytest -q tests/unit/test_runtime_executable_submit_readiness.py tests/unit/test_runtime_executable_submit_readiness_from_reports.py tests/unit/test_runtime_executable_submit_readiness_service_api.py tests/unit/test_runtime_executable_submit_readiness_api_flow.py tests/unit/test_runtime_release_strategy_planning_rehearsal_from_reports.py tests/unit/test_runtime_next_attempt_strategy_planning.py tests/unit/test_runtime_next_attempt_release.py tests/unit/test_runtime_next_attempt_release_from_reports.py tests/unit/test_b0_runtime_strategy_signal_planning.py tests/unit/test_runtime_next_attempt_strategy_plan_api_flow.py tests/unit/test_trading_console_readmodels.py`
    with `101 passed`;
  - `python3 -m compileall -q src/application/runtime_executable_submit_readiness_service.py src/domain/runtime_executable_submit_readiness.py src/interfaces/api_trading_console.py scripts/runtime_executable_submit_readiness_api_flow.py scripts/runtime_executable_submit_readiness_from_reports.py tests/unit/test_runtime_executable_submit_readiness.py tests/unit/test_runtime_executable_submit_readiness_from_reports.py tests/unit/test_runtime_executable_submit_readiness_service_api.py tests/unit/test_runtime_executable_submit_readiness_api_flow.py`;
  - `git diff --check`.
- Deployment:
  - not deployed in this stage;
  - current Tokyo deployed release remains
    `brc-runtime-governance-da84d501-20260612Trtf005-release-strategy-probe`.
- Safety:
  - no PG read/write;
  - no exchange read/write;
  - no exchange order submit;
  - no `ExecutionIntent` creation;
  - no `OrderLifecycle.submit_order`;
  - no order creation/cancel/close;
  - no runtime state mutation;
  - no withdrawal or transfer.

## 2026-06-12 (RTF-006 Executable Submit Readiness Local Proof)

- Confirmed current mainline workspace and branch before implementation:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - starting HEAD: `75d16acc`.
- Added `RuntimeExecutableSubmitReadinessPacket`:
  - consolidates a fresh release-aware strategy planning packet,
    current FinalGate preview evidence, runtime grant / Owner submit
    authorization evidence, trusted submit facts, idempotency evidence,
    local registration enablement, exchange submit enablement, exchange submit
    action authorization, OrderLifecycle submit enablement, exchange adapter
    enablement, protection readiness, active-position trust, account-fact
    freshness, and duplicate-submit guard readiness;
  - classifies readiness into `blocked` or `ready_for_executable_submit`;
  - makes historical `runtime_submit_rehearsal_id` compatibility evidence,
    not a required runtime-level bounded-auto-attempt gate;
  - surfaces blocked legacy first-real-submit packets as warnings when the
    current runtime grant path has complete evidence.
- Added `scripts/runtime_executable_submit_readiness_from_reports.py`:
  - reads prior strategy-planning JSON plus a readiness evidence JSON;
  - optionally reads a legacy first-real-submit packet;
  - emits a non-executing readiness report with explicit no-side-effect
    invariants.
- Focused verification passed:
  - `pytest -q tests/unit/test_runtime_executable_submit_readiness.py tests/unit/test_runtime_executable_submit_readiness_from_reports.py tests/unit/test_runtime_release_strategy_planning_rehearsal_from_reports.py tests/unit/test_runtime_next_attempt_strategy_planning.py tests/unit/test_runtime_next_attempt_release.py tests/unit/test_runtime_next_attempt_release_from_reports.py tests/unit/test_b0_runtime_strategy_signal_planning.py tests/unit/test_runtime_next_attempt_strategy_plan_api_flow.py`
    with `43 passed`;
  - `python3 -m compileall -q src/domain/runtime_executable_submit_readiness.py scripts/runtime_executable_submit_readiness_from_reports.py tests/unit/test_runtime_executable_submit_readiness.py tests/unit/test_runtime_executable_submit_readiness_from_reports.py`;
  - `git diff --check`.
- Deployment:
  - not deployed in this stage;
  - current Tokyo deployed release remains
    `brc-runtime-governance-da84d501-20260612Trtf005-release-strategy-probe`.
- Safety:
  - no PG read/write;
  - no exchange read/write;
  - no exchange order submit;
  - no `ExecutionIntent` creation;
  - no `OrderLifecycle.submit_order`;
  - no order creation/cancel/close;
  - no runtime state mutation;
  - no withdrawal or transfer.

## 2026-06-12 (RTF-005 Tokyo Deploy + Release-aware Strategy Planning Probe)

- Added the non-executing Tokyo rehearsal entry:
  - `scripts/runtime_release_strategy_planning_rehearsal_from_reports.py`;
  - tests:
    `tests/unit/test_runtime_release_strategy_planning_rehearsal_from_reports.py`;
  - focused local verification:
    `pytest -q tests/unit/test_runtime_release_strategy_planning_rehearsal_from_reports.py tests/unit/test_runtime_next_attempt_strategy_planning.py tests/unit/test_runtime_next_attempt_release.py tests/unit/test_runtime_next_attempt_release_from_reports.py tests/unit/test_b0_runtime_strategy_signal_planning.py tests/unit/test_runtime_next_attempt_strategy_plan_api_flow.py`
    with `31 passed`;
  - `python3 -m compileall scripts/runtime_release_strategy_planning_rehearsal_from_reports.py tests/unit/test_runtime_release_strategy_planning_rehearsal_from_reports.py src/application/runtime_next_attempt_strategy_planning_service.py`;
  - `git diff --check`.
- Deployed the current program branch to Tokyo using the git-based deploy path:
  - release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-da84d501-20260612Trtf005-release-strategy-probe`;
  - current symlink:
    `/home/ubuntu/brc-deploy/app/current`;
  - service: `brc-owner-console-backend.service` active;
  - health: `GET /api/health` returned `status=ok`,
    `runtime_bound=true`, `live_ready=false`;
  - deployment execution report:
    `output/rtf005-tokyo/git-deploy-execution-da84d501.json`.
- Ran the RTF-005 Tokyo release-aware strategy planning probe:
  - remote report dir:
    `/home/ubuntu/brc-deploy/reports/rtf005-release-strategy-planning/20260612Trtf005-175720`.
- Current BNB blocked path:
  - source release report: `next-attempt-release-blocked.json`;
  - strategy planning report: `release-strategy-planning-blocked.json`;
  - status: `blocked_by_release_gate`;
  - planner called: `false`;
  - order candidate ID: `null`.
- Positive flat/review/gate-clear rehearsal:
  - source release fixture: `next-attempt-release-ready-fixture.json`;
  - strategy planning report: `release-strategy-planning-positive.json`;
  - status: `ready_for_final_gate_preflight`;
  - planner called: `true`;
  - order candidate ID:
    `rehearsal-order-candidate-eval-rtf005-release-rehearsal`;
  - live submit allowed: `false`;
  - execution intent created: `false`.
- Safety:
  - deploy effects reported no exchange call, no `ExecutionIntent`, no order,
    and no `OrderLifecycle`;
  - both rehearsal packets reported no PG read/write, no exchange write, no
    executable `ExecutionIntent`, no order creation, no `OrderLifecycle`, no
    position open/close, no runtime mutation, and no withdrawal or transfer.

## 2026-06-12 (RTF-005 Release-ready Strategy Planning Local Proof)

- Confirmed current mainline workspace and branch before implementation:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - starting HEAD: `f6297ef6`.
- Extended `RuntimeNextAttemptStrategyPlanningService` with a release-aware
  entry:
  - `plan_from_release_gate(...)`;
  - accepts `RuntimeNextAttemptReleasePacket`;
  - blocks before strategy planning unless release status is
    `ready_for_strategy_signal`;
  - requires strategy observation and shadow candidate planning to both be
    explicitly allowed by the release packet;
  - calls the existing shadow planner only after release readiness is proven.
- Preserved the existing post-submit path:
  - `plan_from_post_submit_gate(...)` remains intact;
  - old consumed authorization remains replay-only;
  - future submit still requires fresh signal, fresh authorization, and
    official FinalGate.
- Focused verification passed:
  - `pytest -q tests/unit/test_runtime_next_attempt_strategy_planning.py tests/unit/test_runtime_next_attempt_release.py tests/unit/test_runtime_next_attempt_release_from_reports.py tests/unit/test_b0_runtime_strategy_signal_planning.py tests/unit/test_runtime_next_attempt_strategy_plan_api_flow.py`
    with `29 passed`;
  - `python3 -m compileall src/application/runtime_next_attempt_strategy_planning_service.py tests/unit/test_runtime_next_attempt_strategy_planning.py`;
  - `git diff --check`.
- Safety:
  - no deployment in this stage;
  - no PG read/write;
  - no exchange read/write;
  - no exchange order submit;
  - no executable `ExecutionIntent`;
  - no `OrderLifecycle.submit_order`;
  - no order creation/cancel/close;
  - no runtime state mutation;
  - no withdrawal or transfer.

## 2026-06-12 (RTF-004 Tokyo Deploy + Release Probe)

- Confirmed current mainline workspace and branch before deployment:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - deployed HEAD: `3be681e1`.
- Deployed the current program branch to Tokyo using the git-based deploy path:
  - release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-3be681e1-20260612Trtf004-release-probe`;
  - current symlink:
    `/home/ubuntu/brc-deploy/app/current`;
  - service: `brc-owner-console-backend.service` active;
  - health: `GET /api/health` returned `status=ok`,
    `runtime_bound=true`, `live_ready=false`;
  - deployment execution report:
    `output/rtf004-tokyo/git-deploy-execution-3be681e1.json`.
- Ran the RTF-004 Tokyo next-attempt release probe:
  - remote report dir:
    `/home/ubuntu/brc-deploy/reports/rtf004-next-attempt-release/20260612Trtf004-174304`;
  - generated reports:
    `live-position-monitor.json`, `position-exit-plan.json`,
    `post-close-followup.json`, `active-position-resolution.json`, and
    `next-attempt-release.json`;
  - active-position resolution status: `hold_with_hard_stop`;
  - next-attempt release status: `waiting_for_position_resolution`;
  - active position present: `true`;
  - next attempt blocked by active position: `true`;
  - strategy signal observation allowed: `false`;
  - shadow candidate planning allowed: `false`;
  - executable submit allowed: `false`;
  - blockers: `[]`;
  - warnings:
    `missing_tp_protection_right_tail_exit_not_mounted`,
    `reconciliation_warning_present`,
    `tp1_partial_quantity_below_min_qty_or_step`.
- Safety:
  - deploy effects reported no exchange call, no `ExecutionIntent`, no order,
    and no `OrderLifecycle`;
  - probe packet reported no PG read, no exchange write, no order creation,
    no `OrderLifecycle`, no position close, no runtime mutation, and no
    withdrawal or transfer.

## 2026-06-12 (RTF-004 Next-attempt Release Local Proof)

- Confirmed current mainline workspace and branch before implementation:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - starting HEAD: `ae05b1d4`.
- Added `RuntimeNextAttemptReleasePacket`:
  - joins `RuntimeActivePositionResolutionPacket` with an optional
    non-executing next-attempt gate packet;
  - classifies release into:
    `waiting_for_position_resolution`, `waiting_for_closed_review`,
    `waiting_for_next_attempt_gate`, `ready_for_strategy_signal`, or
    `blocked`;
  - only allows strategy signal observation / shadow candidate planning when
    active-position resolution is `ready_for_next_attempt_gate` and the
    next-attempt gate is clear;
  - keeps executable submit disabled and still requires fresh strategy signal,
    fresh authorization, and official FinalGate before any future submit.
- Added `scripts/runtime_next_attempt_release_from_reports.py`:
  - reads existing active-position-resolution and next-attempt-gate JSON
    reports;
  - tolerates noisy log lines before JSON payloads;
  - emits a packet-only release decision plus operator command plan.
- Focused verification passed:
  - `pytest -q tests/unit/test_runtime_next_attempt_release.py tests/unit/test_runtime_next_attempt_release_from_reports.py tests/unit/test_runtime_active_position_resolution.py tests/unit/test_runtime_active_position_resolution_from_reports.py tests/unit/test_runtime_post_close_followup.py tests/unit/test_runtime_post_close_followup_script.py tests/unit/test_runtime_next_attempt_gate_packet_script.py`
    with `24 passed`;
  - `python3 -m compileall src/domain/runtime_next_attempt_release.py scripts/runtime_next_attempt_release_from_reports.py tests/unit/test_runtime_next_attempt_release.py tests/unit/test_runtime_next_attempt_release_from_reports.py`;
  - `git diff --check`.
- Safety:
  - no deployment in this stage;
  - no PG read/write;
  - no exchange read/write;
  - no exchange order submit;
  - no `ExecutionIntent` creation;
  - no `OrderLifecycle.submit_order`;
  - no order creation/cancel/close;
  - no runtime state mutation;
  - no withdrawal or transfer.

## 2026-06-12 (RTF-003 Tokyo Deploy + Active Position Resolution Probe)

- Confirmed current mainline workspace and branch before deployment:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - deployed HEAD: `3f9dd1b0`.
- Deployed the current program branch to Tokyo using the git-based deploy path:
  - release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-3f9dd1b0-20260612Trtf003-resolution-probe`;
  - current symlink:
    `/home/ubuntu/brc-deploy/app/current`;
  - service: `brc-owner-console-backend.service` active;
  - health: `GET /api/health` returned `status=ok`,
    `runtime_bound=true`, `live_ready=false`;
  - deployment execution report:
    `output/rtf003-tokyo/git-deploy-execution-3f9dd1b0.json`.
- Ran the RTF-003 Tokyo active-position resolution probe:
  - remote report dir:
    `/home/ubuntu/brc-deploy/reports/rtf003-active-position/20260612Trtf003-173137`;
  - generated reports:
    `live-position-monitor.json`, `position-exit-plan.json`,
    `post-close-followup.json`, and `active-position-resolution.json`;
  - status: `hold_with_hard_stop`;
  - active position present: `true`;
  - can continue holding: `true`;
  - next attempt blocked by active position: `true`;
  - full reduce-only close feasible: `true`;
  - Owner close approval value:
    `runtime-reduce-only-close:strategy-runtime-e6138ad7c88f:BNB/USDT:USDT:long:qty=0.01:owner-authorized`;
  - warnings:
    `missing_tp_protection_right_tail_exit_not_mounted`,
    `reconciliation_warning_present`,
    `tp1_partial_quantity_below_min_qty_or_step`;
  - blockers: `[]`.
- Focused verification before deploy:
  - `pytest -q tests/unit/test_runtime_active_position_resolution.py tests/unit/test_runtime_active_position_resolution_from_reports.py tests/unit/test_runtime_live_position_monitor.py tests/unit/test_runtime_post_close_followup.py`
    with `15 passed`;
  - `python3 -m compileall scripts/runtime_active_position_resolution_from_reports.py src/domain/runtime_active_position_resolution.py`;
  - `git diff --check`.
- Safety:
  - no exchange write;
  - no exchange order submit;
  - no `OrderLifecycle.submit_order`;
  - no local order creation/cancel/close;
  - no runtime state mutation;
  - no closed-review record creation;
  - no withdrawal or transfer.

## 2026-06-12 (RTF-003 Active Position Resolution Local Proof)

- Confirmed current mainline workspace and branch before implementation:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - starting HEAD: `0870f904`.
- Added `RuntimeActivePositionResolutionPacket`:
  - consolidates `RuntimeLivePositionMonitorPacket`,
    `RuntimePositionExitPlan`, and `RuntimePostCloseFollowupPacket`;
  - classifies active-position resolution into:
    `hold_with_hard_stop`, `waiting_for_owner_close_authorization`,
    `ready_for_closed_review`, `ready_for_next_attempt_gate`, or `blocked`;
  - treats protected active positions as holdable under the right-tail
    risk-capital objective while still blocking new attempts when the active
    position slot is in use;
  - exposes optional reduce-only close authorization facts without executing
    the close.
- Added `scripts/runtime_active_position_resolution_from_reports.py`:
  - reads existing monitor / exit-plan / post-close-followup JSON reports;
  - tolerates noisy log lines before JSON payloads;
  - emits one packet-only active-position resolution JSON.
- Tokyo fact evidence used for this stage:
  - remote report dir:
    `/home/ubuntu/brc-deploy/reports/rtf003-active-position/20260612T171853`;
  - local resolution output:
    `output/rtf003-active-position/20260612T171853/active-position-resolution.json`.
- Current BNB runtime resolution:
  - runtime: `strategy-runtime-e6138ad7c88f`;
  - status: `hold_with_hard_stop`;
  - active position present: `true`;
  - can continue holding: `true`;
  - next attempt blocked by active position: `true`;
  - full reduce-only close feasible: `true`;
  - Owner close approval value:
    `runtime-reduce-only-close:strategy-runtime-e6138ad7c88f:BNB/USDT:USDT:long:qty=0.01:owner-authorized`;
  - warnings:
    `missing_tp_protection_right_tail_exit_not_mounted`,
    `reconciliation_warning_present`,
    `tp1_partial_quantity_below_min_qty_or_step`.
- Verification passed:
  - `pytest -q tests/unit/test_runtime_active_position_resolution.py tests/unit/test_runtime_active_position_resolution_from_reports.py tests/unit/test_runtime_live_position_monitor.py tests/unit/test_runtime_post_close_followup.py`
    with `15 passed`;
  - `python3 -m compileall -q src/domain/runtime_active_position_resolution.py scripts/runtime_active_position_resolution_from_reports.py tests/unit/test_runtime_active_position_resolution.py tests/unit/test_runtime_active_position_resolution_from_reports.py`;
  - `git diff --check`.
- Safety:
  - no deployment in this stage;
  - no exchange write;
  - no exchange order submit;
  - no `OrderLifecycle.submit_order`;
  - no local order creation/cancel/close;
  - no runtime state mutation;
  - no closed-review record creation;
  - no withdrawal or transfer.

## 2026-06-12 (RTF-002 Tokyo Deploy + Strategy-plan Probe)

- Confirmed current mainline workspace and branch before deployment:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - deployed HEAD: `10248504`.
- Deployed the current program branch to Tokyo using the git-based deploy path:
  - release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-10248504-20260612Trtf002-strategy-plan-probe`;
  - current symlink:
    `/home/ubuntu/brc-deploy/app/current`;
  - service: `brc-owner-console-backend.service` active;
  - health: `GET /api/health` returned `status=ok`,
    `runtime_bound=true`, `live_ready=false`;
  - deployment execution report:
    `output/rtf002-tokyo/git-deploy-execution-10248504.json`.
- Ran the RTF-002 Tokyo API probe:
  - API script: `scripts/runtime_next_attempt_strategy_plan_api_flow.py`;
  - runtime: `strategy-runtime-e6138ad7c88f`;
  - post-submit packet input:
    `/home/ubuntu/brc-deploy/reports/runtime-next-attempt-strategy-plan/20260612Trtf002-10248504/post-submit-finalize-packet.json`;
  - fresh signal input:
    `/home/ubuntu/brc-deploy/reports/runtime-next-attempt-strategy-plan/20260612Trtf002-10248504/fresh-signal-input.json`;
  - API probe report:
    `/home/ubuntu/brc-deploy/reports/runtime-next-attempt-strategy-plan/20260612Trtf002-10248504/next-attempt-strategy-plan-api-packet.json`.
- Probe result:
  - HTTP status: `200`;
  - status: `blocked_by_post_submit_gate`;
  - blockers:
    `post_submit_finalize_not_ready_for_next_attempt`,
    `post_submit_next_attempt_gate_not_ready`,
    `runtime_active_position_slot_in_use`;
  - `order_candidate_id`: `None`;
  - operator plan: `creates_shadow_candidate=false`,
    `creates_executable_execution_intent=false`, `places_order=false`,
    `calls_order_lifecycle=false`, `live_submit_allowed=false`.
- Interpretation:
  - the deployed RTF-002 API is reachable and uses the new post-submit-gated
    strategy planning path;
  - the API correctly refuses fresh strategy planning while the current BNB
    runtime-owned active position still occupies the active-position slot;
  - no shadow candidate, intent, order, submit, close, withdrawal, or transfer
    was created.

## 2026-06-12 (RTF-002 API / Script Dry-run Entry)

- Confirmed current mainline workspace and branch before implementation:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - starting HEAD: `d0887ec1`.
- Added Trading Console API endpoint:
  - `POST /api/trading-console/strategy-runtimes/{runtime_instance_id}/next-attempt-strategy-plans`;
  - request body includes a `RuntimePostSubmitFinalizePacket` and a fresh
    `StrategyFamilySignalInput`;
  - response is a `RuntimeNextAttemptStrategyPlanningPacket`;
  - the endpoint uses the existing runtime service and the RTF-002
    `RuntimeNextAttemptStrategyPlanningService`.
- Added CLI probe:
  - `scripts/runtime_next_attempt_strategy_plan_api_flow.py`;
  - reads post-submit finalize packet JSON plus signal input JSON;
  - calls the official Trading Console API;
  - preserves JSON-only stdout for automation and Tokyo reports.
- Added verification coverage:
  - API route allowlist updated so the new POST remains an explicit Console
    control-surface exception;
  - endpoint test uses injected runtime/planning services and does not touch PG
    or exchange;
  - CLI tests cover request body, non-executing metadata, HTTP error handling,
    and JSON-only stdout.
- Verification passed:
  - `pytest -q tests/unit/test_runtime_next_attempt_strategy_planning.py tests/unit/test_runtime_next_attempt_strategy_plan_api_flow.py tests/unit/test_trading_console_readmodels.py::test_trading_console_router_keeps_read_models_get_only_and_posts_allowlisted`
    with `9 passed`;
  - `python3 -m compileall -q src/application/runtime_next_attempt_strategy_planning_service.py src/interfaces/api_trading_console.py scripts/runtime_next_attempt_strategy_plan_api_flow.py tests/unit/test_runtime_next_attempt_strategy_planning.py tests/unit/test_runtime_next_attempt_strategy_plan_api_flow.py`;
  - `git diff --check`.
- Safety:
  - no deployment in this stage;
  - no exchange write;
  - no exchange order submit;
  - no `OrderLifecycle.submit_order`;
  - no executable `ExecutionIntent`;
  - no local order creation/cancel/close;
  - no runtime budget / attempt mutation;
  - no withdrawal or transfer.

## 2026-06-12 (RTF-002 Local Next-attempt Strategy Planning Proof)

- Confirmed current mainline workspace and branch before implementation:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - starting HEAD: `49017bd6`.
- Added `RuntimeNextAttemptStrategyPlanningService` as the application-level
  bridge from post-submit finalize to fresh strategy signal planning:
  - requires a `RuntimePostSubmitFinalizePacket`;
  - requires `FINALIZED_READY_FOR_NEXT_ATTEMPT`;
  - requires `READY_FOR_FRESH_SIGNAL` next-attempt gate;
  - refuses runtime mismatches before calling the strategy planner;
  - calls the existing shadow strategy planner only after the post-submit gate
    is ready;
  - records the consumed authorization as replay-only and requires a fresh
    authorization before any future submit path.
- Added `tests/unit/test_runtime_next_attempt_strategy_planning.py` covering:
  - ready post-submit gate calls the shadow planner and returns
    `ready_for_final_gate_preflight`;
  - blocked post-submit gate does not call the planner;
  - observe-only fresh signal waits without creating a candidate;
  - runtime mismatch blocks before planning.
- Verification passed:
  - `pytest -q tests/unit/test_runtime_next_attempt_strategy_planning.py tests/unit/test_runtime_post_submit_finalize.py tests/unit/test_b0_runtime_strategy_signal_planning.py`
    with `22 passed`;
  - `python3 -m compileall -q src/application/runtime_next_attempt_strategy_planning_service.py tests/unit/test_runtime_next_attempt_strategy_planning.py`;
  - `git diff --check`.
- Safety:
  - no deployment in this stage;
  - no exchange write;
  - no exchange order submit;
  - no `OrderLifecycle.submit_order`;
  - no executable `ExecutionIntent`;
  - no local order creation/cancel/close;
  - no withdrawal or transfer.

## 2026-06-12 (RTF-001 Tokyo Deploy + Live-fact Probe)

- Confirmed current mainline workspace and branch before deployment:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - deployed HEAD: `f30eee99`.
- Deployed the current program branch to Tokyo using the git-based deploy path:
  - release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-f30eee99-20260612Tpost-submit-finalize-probe`;
  - current symlink:
    `/home/ubuntu/brc-deploy/app/current`;
  - service: `brc-owner-console-backend.service` active;
  - health: `GET /api/health` returned `status=ok`,
    `runtime_bound=true`, `live_ready=false`.
- Ran the Tokyo live-fact post-submit finalize probe for the latest durable
  runtime submit result:
  - authorization:
    `runtime-submit-authorization-intent_rt_f9ccb55add229b9fdbd62636`;
  - reservation:
    `runtime-attempt-reservation-runtime-submit-authorization-intent_rt_f9ccb55add229b9fdbd62636`;
  - runtime: `strategy-runtime-e6138ad7c88f`;
  - symbol: `BNB/USDT:USDT`;
  - report:
    `/home/ubuntu/brc-deploy/reports/runtime-post-submit-finalize-probe/20260612Tpost-submit-finalize-f30eee99/post-submit-finalize-packet.json`.
- Probe result:
  - status: `finalized_next_attempt_blocked`;
  - next-attempt gate: `blocked`;
  - blocker: `runtime_active_position_slot_in_use`;
  - trusted active-position source: `pg_position_projection`;
  - active positions for the symbol: `1`;
  - runtime-owned active positions: `1`;
  - unknown-runtime active positions: `0`;
  - other-runtime active positions: `0`.
- Interpretation:
  - the already submitted attempt is accepted as post-submit evidence;
  - the old authorization is not retried through pre-submit rehearsal;
  - the runtime loop correctly refuses a new attempt while the current BNB
    runtime-owned active position occupies the active-position slot.
- Safety invariants reported by the probe:
  - no exchange write;
  - no exchange order submit;
  - no `ExecutionIntent` creation;
  - no local order creation/cancel;
  - no `OrderLifecycle.submit_order`;
  - no position close;
  - no withdrawal or transfer.

## 2026-06-12 (RTF-001 Local/Tokyo Probe Entry)

- Confirmed current mainline workspace and branch before implementation:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - starting HEAD: `4de5f19a`.
- Added `scripts/runtime_post_submit_finalize_probe.py` as the standard local
  / Tokyo integration probe entry for RTF-001.
- Probe behavior:
  - resolves durable exchange-submit execution result by `authorization_id`;
  - reads trusted local active-position projection from `PgPositionRepository`;
  - counts all same-symbol active positions conservatively, while reporting
    runtime-owned / unknown-runtime / other-runtime splits;
  - runs `RuntimePostSubmitFinalizeService`;
  - outputs finalize packet, next-attempt gate status, active-position facts,
    blockers, warnings, and explicit no-exchange/no-order safety invariants.
- Added `tests/unit/test_runtime_post_submit_finalize_probe.py` covering:
  - clear next-attempt gate from trusted PG position count `0`;
  - active same-symbol local position blocks the next-attempt gate;
  - missing submit result cannot be bypassed by user-supplied active-position
    facts and blocks with missing trusted facts.
- Verification passed:
  - `pytest -q tests/unit/test_runtime_post_submit_finalize_probe.py tests/unit/test_runtime_post_submit_finalize.py tests/unit/test_runtime_execution_submit_outcome_review.py`
    with `36 passed`;
  - `python3 -m compileall -q scripts/runtime_post_submit_finalize_probe.py tests/unit/test_runtime_post_submit_finalize_probe.py`;
  - `git diff --check`.
- Safety:
  - no deployment in this stage;
  - no exchange write;
  - no order creation/cancel/close;
  - no `OrderLifecycle.submit_order`;
  - no `ExecutionIntent` creation;
  - no withdrawal or transfer.

## 2026-06-12 (RTF-001 Local Post-submit Finalize Proof)

- Confirmed current mainline workspace and branch before implementation:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - starting HEAD: `75428a8f`.
- Added the RTF-001 local finalize artifact:
  - `src/domain/runtime_post_submit_finalize.py`;
  - `src/application/runtime_post_submit_finalize_service.py`;
  - `scripts/runtime_post_submit_finalize_dry_run.py`;
  - `tests/unit/test_runtime_post_submit_finalize.py`.
- RTF-001 semantics now have a local packet/service proof:
  - consumed authorization is `replay-only`;
  - old authorization submit retry is forbidden;
  - pre-submit rehearsal retry is forbidden;
  - local orders are not required to return to `CREATED`;
  - next attempt requires fresh strategy signal and fresh authorization;
  - missing trusted active-position facts block next-attempt readiness;
  - active-position slot usage blocks the next attempt without treating the
    prior submit as a rehearsal failure.
- Tightened existing post-submit accounting idempotency:
  - `RuntimeExecutionIntentAdapterService.record_first_real_submit_outcome_accounting_for_authorization`
    now reuses an existing `RuntimeExecutionSubmitOutcomeReview` for the same
    authorization before creating a new one.
- Verification passed:
  - `pytest -q tests/unit/test_runtime_post_submit_finalize.py tests/unit/test_runtime_execution_submit_outcome_review.py`
    with `33 passed`;
  - `python3 -m compileall -q src/domain/runtime_post_submit_finalize.py src/application/runtime_post_submit_finalize_service.py scripts/runtime_post_submit_finalize_dry_run.py tests/unit/test_runtime_post_submit_finalize.py src/application/runtime_execution_intent_adapter_service.py`;
  - `git diff --check`.
- Safety:
  - no exchange call;
  - no order creation/cancel/close;
  - no `OrderLifecycle.submit_order`;
  - no `ExecutionIntent` creation;
  - no withdrawal or transfer;
  - no Tokyo deployment in this stage.

## 2026-06-12 (Runtime Loop Correction Prep)

- Confirmed current mainline workspace and branch before editing:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - starting HEAD: `dc631552`.
- Adopted the runtime direction correction in planning and agent-facing
  constraints:
  - consumed first-real-submit authorizations are review/replay evidence, not
    candidates for another pre-submit rehearsal;
  - durable `RuntimeExecutionExchangeSubmitExecutionResult` is the primary
    post-submit proof;
  - the mainline should move through post-submit finalize, budget / attempt
    settlement, protection/reconciliation review, and next-attempt gate;
  - fresh attempts must start from fresh strategy signal, candidate, intent,
    and authorization evidence.
- Adopted the engineering cadence correction:
  - local domain test;
  - local application service test;
  - local API / script dry-run artifact;
  - Tokyo deployment / live-fact integration probe;
  - stage commit with path, branch, deployment status, and touched-authority
    summary.
- Updated planning artifacts for the next mainline task:
  - `RTF-001 RuntimePostSubmitFinalize + NextAttemptGate v1`;
  - `RTF-002 Strategy-driven next attempt planning reconnection`.
- Safety:
  - this prep stage changed documentation only;
  - no runtime code, migration, API behavior, exchange order, `OrderLifecycle`
    submit, withdrawal, transfer, or deployment was performed.

## 2026-06-11 (Runtime Exchange Close Projection Recovery)

- Added `RuntimeExchangeCloseProjectionRecoveryService` and
  `scripts/recover_runtime_exchange_close_projection.py` to recover local
  runtime order/position projection from an already-observed exchange close
  trade. This covers the first-real-submit post-close case where exchange is
  flat but local PG still shows an active position and stale SL.
- The recovery path is default dry-run. `--apply` only mutates local PG
  projection: mark the local exit/protection order filled and project the
  position closed/realized PnL through existing `OrderLifecycleService` and
  `PositionProjectionService`.
- Safety boundary: it reads exchange trades only and never submits, cancels,
  amends, or closes exchange orders; it never creates withdrawal or transfer
  instructions.
- Verification passed:
  - `python3 -m pytest -q tests/unit/test_runtime_exchange_close_projection_recovery.py`
  - `python3 -m compileall -q src/domain/runtime_exchange_close_projection_recovery.py src/application/runtime_exchange_close_projection_recovery_service.py scripts/recover_runtime_exchange_close_projection.py`
  - `python3 scripts/recover_runtime_exchange_close_projection.py --help`
  - `git diff --check`

## 2026-06-11 (Runtime Live Position Monitor Console Surface)

- Wired `RuntimeLivePositionMonitorService` into Trading Console as
  `GET /api/trading-console/strategy-runtimes/{runtime_instance_id}/live-position-monitor`.
  The endpoint uses persistent runtime/position/order facts plus optional
  read-only exchange and reconciliation reads; it remains non-mutating and
  returns the packet's no-action flags.
- Added the Runtime page "实盘持仓监控" panel between safety readiness and the
  first-real-submit gate. It surfaces active-position count, SL/TP protection,
  unrealized PnL, attempt/budget state, holdability, and whether the next
  attempt is paused by the active-position slot.
- Verified light/dark mode continuity with Playwright. The local Playwright
  fixture showed `active_protection_warning`, `仅 SL`, `可继续持有`, `新尝试=暂停`,
  and `交易所写入=无`; fixture-only missing read models returned expected
  503/404 outside the new monitor endpoint.
- Verification passed:
  - `python3 -m pytest -q tests/unit/test_runtime_live_position_monitor.py tests/unit/test_trading_console_readmodels.py::test_trading_console_router_keeps_read_models_get_only_and_posts_allowlisted tests/unit/test_trading_console_readmodels.py::test_trading_console_runtime_live_position_monitor_endpoint_surfaces_sl_only_warning`
  - `python3 -m compileall -q src/application/runtime_live_position_monitor_service.py src/interfaces/api_trading_console.py`
  - `npm run lint --prefix trading-console`
  - `npm run build --prefix trading-console`
  - Playwright CLI local login + `/runtime` smoke against a temporary FastAPI
    fixture and Trading Console proxy.

## 2026-06-11 (Runtime Live Position Monitor v1)

- Added a read-only runtime-native live-position monitor packet for the
  post-submit state after first real runtime submit. The packet joins runtime
  attempt/budget boundaries, local active position/open order projection,
  exchange position/stop-order reads, and reconciliation mismatches.
- Preserved the right-tail risk-capital objective: an active position with a
  hard stop but no TP is classified as holdable with an exit-policy warning,
  not as a runaway-risk blocker. New attempts remain blocked while the runtime
  active-position slot is in use.
- Hard safety remains explicit: missing hard stop, missing exchange facts, or a
  severe reconciliation mismatch require Owner action.
- Preserved execution boundaries: this stage does not create, submit, cancel,
  amend, or close orders; does not call OrderLifecycle; does not mutate runtime
  state; and cannot withdraw or transfer funds.
- Verification passed:
  - `python3 -m pytest -q tests/unit/test_runtime_live_position_monitor.py`
  - `python3 -m compileall -q src/domain/runtime_live_position_monitor.py src/application/runtime_live_position_monitor_service.py scripts/runtime_live_position_monitor.py`
  - `git diff --check -- src/domain/runtime_live_position_monitor.py src/application/runtime_live_position_monitor_service.py scripts/runtime_live_position_monitor.py tests/unit/test_runtime_live_position_monitor.py`

## 2026-06-11 (LLM Advisory Asset Replay v1)

- Created `codex/llm-advisory-replay-v1` from the current
  `program/live-safe-v1` integration baseline to replay useful LLM assets
  without merging the stale submit-chain work from
  `codex/llm-advisory-plane-feishu-design`.
- Replayed the non-overlapping advisory assets:
  - LLM advisory domain/event/recommendation models;
  - context packet builder;
  - provider-output safety checks;
  - Feishu push-only card formatting;
  - advisory eval and event auto-publisher helpers;
  - PG advisory repository and Alembic migration `081`;
  - operator-auth `/api/brc/llm/advisory/*` API surface;
  - ADR-0013 and strategy evolution agent plan.
- Explicitly did not merge the old LLM branch's runtime submit-chain commits.
  Trusted submit facts, first-submit packets, gateway readiness, recovery, and
  submit outcome review remain governed by the current mainline implementation
  unless a later gap audit identifies a precise missing slice.
- Preserved execution boundaries: LLM advisory can record events, produce
  recommendations, and optionally push Feishu notifications, but it cannot
  create Owner actions, SignalEvaluation, OrderCandidate, ExecutionIntent,
  orders, exchange calls, transfers, or withdrawals.
- Verification passed:
  - `python3 -m compileall -q src/domain/llm_advisory.py src/application/llm_advisory_cards.py src/application/llm_advisory_eval.py src/application/llm_advisory_plane.py src/application/llm_advisory_safety.py src/application/llm_context_packet_builder.py src/application/llm_event_autopublisher.py src/infrastructure/pg_llm_advisory_repository.py src/infrastructure/pg_models.py src/interfaces/api.py src/interfaces/api_brc_console.py tests/unit/test_llm_advisory_plane.py migrations/versions/2026-06-11-081_create_llm_advisory_plane.py`
  - `pytest -q tests/unit/test_llm_advisory_plane.py` -> 16 passed

## 2026-06-08 (BRC Candidate-to-Action Product Loop Sprint)

- Added backend-owned `CandidateActionProductLoop` contract that composes
  ActionCandidate, authorization draft status, BudgetEnvelope draft status,
  normalized ActionSpec, FinalGate readiness, official Operation Layer
  preflight contract, protection draft, review plan, and post-action readiness
  into one non-live Owner-facing loop.
- Wired `/api/trading-console/action-entry-readiness` and
  `/api/trading-console/owner-action-flow` to expose
  `candidate_action_readiness_loop` and
  `selected_candidate_action_readiness_loop`. The loop covers BNB, Trend/SOL,
  MR/ETH, and Volatility through the same contract: BNB is dry-run/historical,
  Trend is Owner-confirmable, MR is BudgetEnvelope-confirmable, and Volatility
  remains proposal-only.
- Updated Trading Console Action Entry to consume backend loop state for
  candidate cards, four-stage readiness, FinalGate fact bindings, official
  Operation Layer preflight, authorization, budget, protection, review, and
  disabled action state. The screen remains an Owner operations surface rather
  than raw JSON, documentation, or code explanation.
- Preserved execution boundaries: this sprint does not create authorization,
  execution intent, orders, cancels, closes, PG mutation from readmodel paths,
  exchange writes, runtime start, profile changes, credential changes, or
  deployment.
- Verification passed:
  - `python3 -m pytest -q tests/unit/test_candidate_action_product_loop.py tests/unit/test_action_spec_final_gate_adapter.py tests/unit/test_production_strategy_family_admission.py tests/unit/test_trading_console_readmodels.py tests/unit/test_brc_operation_layer.py::test_runtime_state_operations_execute_or_degrade_safely tests/unit/test_brc_operation_layer.py::test_runtime_transition_unavailable_when_adapter_missing tests/unit/test_brc_operation_layer.py::test_revoke_budget_preflight_and_confirmation_persist_effective_state tests/unit/test_brc_operation_layer.py::test_revoke_budget_repeated_confirm_is_idempotent_noop tests/unit/test_brc_operation_layer.py::test_revoke_budget_blocks_when_no_current_budget_authorization`
  - `python3 -m pytest -q tests/unit/test_brc_console_api_surface.py`
  - `python3 -m py_compile src/application/candidate_action_product_loop.py src/application/action_spec_final_gate_adapter.py src/application/production_strategy_family_admission.py src/application/readmodels/trading_console.py src/interfaces/api_trading_console.py`
  - `npm run lint --prefix trading-console`
  - `npm run build --prefix trading-console`
  - `python3 -m alembic heads`
  - temporary clean SQLite `alembic upgrade head`
  - `git diff --check`
- Migration status: no migration added; Alembic remains at single head `043`.
  Deployment deferred per Owner preference for local integration.

## 2026-06-08 (BRC ActionSpec FinalGate Adapter Contract Sprint)

- Added a strategy-independent, non-live
  `ActionSpecFinalGateAdapterService` boundary for ActionCandidate input,
  normalized ActionSpec draft validation, FinalGate preview/status output,
  warning/hard-blocker classification, and explicit no-action guarantees.
- Integrated adapter results into the product backbone and Trading Console
  action-entry readiness payload as backend-provided contract data. BNB,
  Trend/SOL, MR/ETH, and Volatility now pass through the same adapter surface:
  BNB is dry-run/historical, Trend needs Owner authorization, MR needs
  BudgetEnvelope authorization, and Volatility remains proposal-only.
- Preserved execution boundaries: official FinalGate remains the execution
  gate; this sprint does not create authorization, execution intent, order
  placement/cancel/close, PG mutation, exchange write, runtime start, profile
  change, credential change, or deployment.
- Verification passed:
  - `python3 -m pytest -q tests/unit/test_action_spec_final_gate_adapter.py`
  - `python3 -m pytest -q tests/unit/test_production_strategy_family_admission.py tests/unit/test_trading_console_readmodels.py tests/unit/test_brc_operation_layer.py::test_runtime_state_operations_execute_or_degrade_safely tests/unit/test_brc_operation_layer.py::test_runtime_transition_unavailable_when_adapter_missing tests/unit/test_brc_operation_layer.py::test_revoke_budget_preflight_and_confirmation_persist_effective_state tests/unit/test_brc_operation_layer.py::test_revoke_budget_repeated_confirm_is_idempotent_noop tests/unit/test_brc_operation_layer.py::test_revoke_budget_blocks_when_no_current_budget_authorization`
  - `python3 -m pytest -q tests/unit/test_brc_console_api_surface.py`
  - `python3 -m py_compile src/application/action_spec_final_gate_adapter.py src/application/production_strategy_family_admission.py src/application/readmodels/trading_console.py`
  - `python3 -m alembic heads`
  - temporary clean SQLite `alembic upgrade head`
  - `git diff --check`
- Migration status: no migration added; Alembic remains at single head `043`.
  Frontend was not touched, so frontend lint/build was not run.

## 2026-06-08 (BRC Product Backbone Acceptance Pass)

- Performed local integration acceptance on the product backbone introduced in
  `3e64e0b4`: StrategyFamily / Carrier, ActionCandidate, RiskDisclosure,
  Admission L0-L4, warning vs hard blocker policy, Generic ActionSpec,
  FinalGate preview/input, ProtectionTemplate, ReviewTemplate, and Trading
  Console Action Entry.
- Result: the backbone is locally integrated as a non-mutating read-model and
  action-entry handoff surface, not frontend-only fake UI. BNB historical proof,
  Trend/SOL, MR/ETH, and Volatility proposal samples are represented through
  the same product model. Volatility remains proposal/dry-run and is not live
  enabled.
- Added regression coverage for:
  - no-exact-match Owner input returning nearest candidates and blockers instead
    of an empty Action Entry dead end;
  - v0.2 cockpit top-level pause/revoke state fields remaining exposed.
- Migration hygiene: fixed SQLite clean-chain compatibility in existing
  revisions `020`, `036`, and `038` by keeping PostgreSQL constraint/default
  behavior and skipping unsupported SQLite ALTER operations. No new migration
  was added. `043` remains the single Alembic head.
- Verification passed:
  - `python3 -m py_compile src/application/production_strategy_family_admission.py src/application/readmodels/trading_console.py src/interfaces/api_trading_console.py`
  - `python3 -m pytest -q tests/unit/test_production_strategy_family_admission.py tests/unit/test_trading_console_readmodels.py`
  - `npm run lint --prefix trading-console`
  - `npm run build --prefix trading-console`
  - `python3 -m alembic heads`
  - temporary clean SQLite `alembic upgrade head`
- Safety boundary preserved: no deployment, no live action, no exchange write,
  no order placement/cancel/close, no funds transfer/withdrawal, no credential
  change, no runtime profile change, and no Operation Layer or FinalGate bypass.

## 2026-06-08 (BRC Product Backbone Local Sprint)

- Implemented the local BRC candidate/action product backbone in the Trading Console read-model path: `ProductBackboneReadModel`, first-class warnings, candidate actionability, protection templates, FinalGate preview inputs, and candidate/action-entry surface policy.
- Represented BNB historical bounded-live proof, Trend/SOL, MR/ETH budget-envelope-compatible candidate, and Volatility dry-run proposal through the same product chain shape. BNB remains historical regression evidence only and does not grant fresh authorization.
- Wired `/api/trading-console/action-entry-readiness` and `/api/trading-console/owner-action-flow` to expose `product_backbone`, `candidate_actionability`, `final_gate_preview_inputs`, `protection_templates`, warning records, hard blockers, and the Trading Console candidate/action read model.
- Updated Trading Console Action Entry so the first screen is an Owner action-entry surface: product chain, candidate examples, candidate actionability, authorization handoff, FinalGate preview, disabled reasons, and post-action evidence. It is not presented as a documentation page, passive status page, or code explanation surface.
- Safety boundary preserved: no live action, no order placement, no exchange write, no PG mutation from the Trading Console GET path, no runtime profile change, no credential change, no deployment.
- Targeted verification passed:
  - `python3 -m py_compile src/application/production_strategy_family_admission.py src/application/readmodels/trading_console.py src/interfaces/api_trading_console.py`
  - `python3 -m pytest -q tests/unit/test_production_strategy_family_admission.py`
  - `python3 -m pytest -q tests/unit/test_trading_console_readmodels.py`
  - `npm run lint --prefix trading-console`
  - `npm run build --prefix trading-console`
  - `python3 -m alembic heads`
- Migration status: `python3 -m alembic heads` reports single head `043`. Temporary clean SQLite upgrade-to-head was attempted separately from the dirty local dev DB and failed at revision `020` on SQLite `ALTER TABLE brc_campaigns ALTER COLUMN metadata DROP DEFAULT`; this is a SQLite migration-chain compatibility issue before `043`, distinct from the previously known dirty local SQLite `orders` table conflict. No new migration was added in this sprint. Before any server release, validate the migration chain against the target environment and resolve the SQLite clean-chain hygiene issue if SQLite remains a release validation target.
- Deployment deferred: no coherent release candidate deployed and Owner preference is less frequent deployment.

## 2026-04-29

- Archived pre-live-safe docs, tests, scripts, and generated artifacts.
- Established new program-scoped planning model under `docs/ops/`.
- Adopted Codex-led, Claude-bounded execution workflow.

## 2026-04-30

- Landed `Decision Trace Backbone v0` as a minimal, non-blocking trace backbone for risk decision JSONL output.
- Added `ADR-0002` to document Decision Trace Backbone v0 semantics, scope, and non-goals.
- Landed `LS-001` so the main runtime starts isolated order-watch tasks and exchange order updates can enter the local lifecycle path in real time.
- Landed `LS-002` so runtime daily risk limits now update from projected exit deltas and full position lifecycle closes.
- Kept scope tight: no `api.py` order-watch coverage, no trace expansion, no strategy/risk/profile changes.
- Deferred known follow-ups instead of expanding scope: duplicate `watch_orders` definition cleanup and re-evaluation of one-task-per-symbol if runtime symbol count grows.

## Next

- Keep the live-safe backbone thin; do not widen trace or order-watch into larger subsystems yet.
- Use the post-merge hardening ADR and task board entries as the backlog for the next iteration:
  - trace boundary cleanup
  - multi-symbol order-watch hardening
  - daily stats persistence before live expansion

## 2026-05-06

- Started LS-002b / LS-107 implementation after Owner approved the task card.
- Implemented direction: PG aggregate + event ledger, fixed `scope_key="runtime:default"`, no-new-entry fail-closed on daily stats persistence restore/write-through failure.
- Preserved LS-002 daily stats semantics and documented the accepted non-transactional crash/write window in ADR-0004.
- Targeted tests pass for LS-002b, LS-002 daily limits, and TM-002 exit projection observability.
- Alembic revision graph has single head `008` (LS-002b = 007, LS-003d = 008); local `alembic upgrade head` is blocked by existing SQLite schema/version drift at old revision `002`, before the LS-002b migration runs.
- Implemented LS-003d periodic reconciliation read model persistence as dedicated PG read-only report + mismatch tables. Consistent, mismatch, and fetch-failure reports persist best-effort; persistence failure remains report-only and does not affect runtime behavior. ADR-0007 accepted.
- Drafted CPM-CRITERIA-001 as a planning-only CPM-1 promotion/rejection/pause/observation criteria document; no code, experiment, runtime, risk, or strategy changes.

## 2026-05-06 (CPM-OOS)

- Ran CPM-OOS-RUN-001: 2022 full-year OOS backtest on frozen CPM-1 baseline.
- Result (from result.json ground truth): -971.71 USDT (-9.72%), 61 trades, WR 31.1%, PF 0.624, MaxDD 10.48%, Sharpe -1.399, Sortino -0.414.
- Classification: OOS_NEGATIVE — Require additional evidence (caveated: PnL clean, cost composition unreliable).
- 2022 is an extreme bear year; result is consistent with failure hypothesis but does not disprove profit hypothesis for bull/sideways markets.
- Codex verification found metric misalignment between report and result.json; report revised to use result.json top-level as ground truth. Exit classification now derived from close_events[] with explicit derivation scope labels. Runtime overrides clarified (5 effective, 3 legacy/no-op). Slippage=0 anomaly flagged as reproducibility ambiguity. Small-live Candidate judgment was deferred at this point; this was later superseded by CPM-OOS-FAILURE-CLASSIFY-001, which paused CPM-1 and blocked candidate review.
- CPM-OOS-RECON-001: Resolved slippage=0 anomaly. Root cause: backtester.py:1805-1813 re-derives same slippage formula as matching engine, yielding zero. Slippage IS applied to execution prices and IS reflected in total_pnl. Estimated slippage impact ~644 USDT (largest single cost component). Evidence classification upgraded from "reproducibility ambiguity" to "caveated evidence — PnL clean, cost composition unreliable." No rerun required. No change to OOS_NEGATIVE classification or Require additional evidence conclusion.
- CPM-BT-METRIC-001: Fixed slippage cost tracking metric in backtester.py. Replaced self-referencing derivation (always-zero) with unslipped base price comparison for all order types (MARKET entry, STOP_MARKET SL, LIMIT TP, TRAILING_STOP). Added trailing exit slippage tracking. 16 unit tests pass. No trade outcomes changed. No rerun of 2022 OOS required.
- No runtime, profile, strategy, or risk rule changes.
- Artifacts: reports/oos_runs/cpm1_2022_oos/ (local-only, .gitignored), docs/ops/crypto-pullback-module-v1-2022-oos-report.md (version-controlled), docs/ops/crypto-pullback-module-v1-2022-oos-reconciliation-note.md (version-controlled).

## 2026-05-06 (CPM-OOS-2021-PLAN)

- Created CPM-OOS-2021-PLAN-001: 2021 OOS gate inspect plan for CPM-1.
- 2021 is positioned as the complementary bull-year OOS candidate to 2022's bear-year evidence.
- Pre-run data check: ETH 1h 8,760 candles, 4h 2,190 candles — complete, no gaps, no duplicates.
- Open items: exchange outage verification during May 2021 crash, Binance contract rule stability, funding model choice.
- No 2021 OOS was run. No runtime, profile, strategy, or risk rule changes.
- Artifact: docs/ops/crypto-pullback-module-v1-2021-oos-gate-inspect-plan.md (version-controlled).
- CPM-OOS-2021-PLAN-001 finalized: fixed Section 6 Decision Matrix row 3 (broken Markdown table), added caveat to Section 5.1 (negative result classification before equating with module hypothesis failure).

## 2026-05-06 (CPM-OOS-2021-RUN)

- Ran CPM-OOS-2021-RUN-001: 2021 full-year OOS backtest on frozen CPM-1 baseline.
- Result: -21.54% return, 74 positions (88 trades), WR 29.5%, PF 0.466, MaxDD 22.18%, Sharpe -2.466, Sortino -0.759.
- Corrected total_slippage_cost: 1,040.85 USDT (CPM-BT-METRIC-001 fix active, non-zero).
- Classification: OOS_NEGATIVE — Pause CPM-1 for classification. 2021 (bull year) result is worse than 2022 (bear year), directly challenging the profit hypothesis.
- Fixed TP_ROLES NameError in backtester.py (CPM-BT-METRIC-001 leftover bug: undefined TP_ROLES constant replaced with inline [OrderRole.TP1..TP5] list). No trade outcomes changed.
- No runtime, profile, strategy, or risk rule changes.
- Artifacts: reports/oos_runs/cpm1_2021_oos/ (local-only, .gitignored), docs/ops/crypto-pullback-module-v1-2021-oos-report.md (version-controlled), scripts/run_cpm1_2021_oos.py (version-controlled).

## 2026-05-06 (CPM-OOS-FAILURE-CLASSIFY)

- Completed CPM-OOS-FAILURE-CLASSIFY-001: 2021 OOS failure classification / RCA.
- Primary classification: Favorable-regime profit hypothesis failure + loss-concentration issue.
- 2021 gross edge is negative (-573.84 USDT) — cost drag amplifies but does not cause the loss.
- 2021 and 2022 failures are not isomorphic: 2022 is cost-dominated in an unfavorable regime (consistent with failure hypothesis); 2021 is signal-level in a favorable regime (contradicts profit hypothesis).
- Final state: Pause CPM-1. Small-live Candidate review blocked. Baseline remains frozen. No runtime, profile, strategy, or risk rule changes. runtime_auto_change: No.
- Artifact: docs/ops/crypto-pullback-module-v1-oos-failure-classification.md (version-controlled).

## 2026-05-06 (Strategy Candidate Gate Status)

- Live-safe Foundation can continue as the system safety foundation: trusted order state, protection state, daily risk persistence, reconciliation read models, circuit-break behavior, and replayable observability remain valid system work.
- CPM-1 did not pass the OOS gate for strategy candidacy. The frozen baseline is paused, the promotion path is stopped, and CPM-1 is not a Small-live Candidate or canary-live candidate.
- Current strategy candidate inventory: none. The project does not currently have a deployable small-live strategy candidate.
- This gate status does not trigger runtime/profile/strategy/risk changes. runtime_auto_change: No.

## 2026-05-06 (NSC-001)

- Created NSC-001: CPM-2 Candidate Direction Inspect as a docs-only, inspect-only task.
- Scope inspected only `docs/ops/**`, `archive/**`, and `reports/**`.
- Drafted CPM-2 direction report focused on ETH 1h pullback-continuation with a different entry confirmation mechanism; no Pinbar parameter rescue path.
- Candidate families identified for later Owner-approved experiment planning: one-bar continuation reclaim, Donchian-location pullback confirmation, and a low-density two-candle pullback-end pattern.
- No backtests, strategy implementation, runtime/profile changes, risk rule changes, or promotion conclusions.
- Current state remains: no deployable small-live strategy candidate; small-live readiness gate unmet until a new candidate module passes a minimum evidence gate.

## 2026-05-06 (NSC-002)

- Created NSC-002: CPM-2 Minimal Experiment Plan Draft as Proposed / Experiment Plan Only.
- Drafted minimal experiment plans for Candidate A (One-Bar Continuation Reclaim) and Candidate B (Donchian-Location Pullback Confirmation).
- Candidate C remains reserve-only and does not enter the first experiment round unless A/B are rejected or paused and Owner approves a new plan.
- Plan defines frozen rules, one allowed sensitivity check per candidate, required windows, cost model, same-bar policy, required metrics, trade-count floors, pass/pause/reject gates, anti-overfit rules, and failure classification format.
- Explicitly constrained Candidate A away from reclaim-rule combination search and Candidate B away from E4 hard-filter revival / Donchian breakout interpretation.
- No backtests, strategy implementation, runtime/profile changes, risk rule changes, research-engine changes, or promotion conclusions.
- Current state remains: no deployable small-live strategy candidate; small-live readiness gate unmet until a new candidate module passes an Owner-approved minimum evidence gate.

## 2026-05-09 (Observation + Research Methodology Reset)

- Confirmed current phase label: `Observation + Research Methodology Reset`.
- Confirmed current mainline: Direction A BTC+ETH Phase 1 observation design only.
- Reaffirmed SRR-002 as the guiding methodology for future analysis; acceptance is docs-only and does not authorize experiments, parameter optimization, runtime, or small-live.
- Produced a docs-only roadmap reconciliation snapshot for Owner review.
- Local git state shows one untracked research doc, not 21 visible untracked research docs: `docs/ops/direction-a-btc-eth-phase1-observation-design-consolidation.md`.
- No strategy, experiment, execution, paper/testnet/live trading, portfolio/router, SOL Phase 2, CPM, or short-side action was started.
- Added the docs-only reconciliation snapshot and concise BTC+ETH Phase 1 Owner review brief. After creating those Owner-review artifacts, local visible untracked docs are three: BTC+ETH consolidation, reconciliation snapshot, and Owner review brief.

## 2026-05-25 (PLC-001 Local Campaign Sandbox)

- Implemented the first Personal Leveraged Campaign local sandbox loop:
  `ModeAdvice -> HumanArmDecision -> StrategyContract -> TradeIntent -> RiskOrderPlan -> ExecutionReceipt -> PositionLifecycleState -> CampaignState`.
- Added disabled-by-default local domain contracts, deterministic sandbox functions, and an explicit `CampaignSandboxSettings(enabled=False)` runner guard only; no runtime profile, exchange gateway, execution orchestrator, real API, account, order, transfer, or withdrawal path is touched.
- Added targeted tests for allow/reject, pause, hard-lock, loss-lock, profit-protect reduce/close, default-disabled, no-side-effect, repeatable scenario-catalog cases, and trace invariant pass/fail checks.
- Recorded the docs/design boundary in `docs/ops/personal-leveraged-campaign-local-sandbox-v0.md`.

## 2026-05-25 (PLC-GOV-001 Branch And Document Governance)

- Added current branch/document governance note aligned to `docs/ops/project-roadmap-v2.md` and the accepted Personal Leveraged Campaign mainline.
- Classified local branches into active, protected, frozen research evidence, stale duplicate labels, and deletion candidates; no branch was deleted.
- Classified docs into current SSOT, active governance, active research context, runtime safety foundation, and historical evidence; no documents were physically moved.

## 2026-05-25 (PLC-SCHEMA-001 Schemas And Promotion Checklist)

- Added local JSON schemas for `ModeAdvice`, `HumanArmDecision`, `StrategyContract`, `TradeIntent`, `RiskOrderPlan`, `ExecutionReceipt`, `PositionLifecycleState`, and `CampaignState`.
- Added risk rule matrix covering order-plan, position-lifecycle, campaign, and profit-protection enforcement boundaries.
- Added promotion checklist confirming no runtime, paper, testnet, live, tiny-live, real account, real order, or real withdrawal candidate exists.
- Added schema-doc tests for parseability and disabled/local-only safety fields.

## 2026-05-25 (PLC-SQ02-001 SQ02 Contract Skeleton)

- Added docs-only `SQ02_DOWNSIDE_CONT_V0` StrategyContract skeleton.
- Added SQ02 schema examples for StrategyContract, ModeAdvice, HumanArmDecision, TradeIntent, RiskOrderPlan, and CampaignState.
- Added schema-example tests that parse examples through local campaign Pydantic models and verify default-disabled, no-exchange-side-effect, protection, and Owner-confirmation boundaries.

## 2026-05-25 (PLC-SCOPE-001 Withdrawal Out Of Scope)

- Owner clarified that withdrawals are handled manually by Owner and should not be modeled by the system.
- Removed active `WithdrawalInstruction` model, schema, example, sandbox generation path, and tests.
- Reframed the local chain endpoint as `CampaignState` with profit-protect reduce/close requirements only.

## 2026-05-25 (PLC-FEATURE-001 Feature Snapshot Boundary)

- Added local `FeatureSnapshot` model, JSON schema, and SQ02 example.
- Routed sandbox `StrategyContract` evaluation through `FeatureSnapshot` instead of a bare conditions dict.
- Added tests for closed/prior-only snapshot parsing, LLM decision rejection, and strategy-contract mismatch rejection.

## 2026-05-25 (PLC Local Chain Verification)

- Verified the local PLC mock/sandbox chain end to end through the repeatable scenario catalog:
  `allow_open_protected`, `reject_contract_invalidated`, `reject_order_caps`,
  `pause_blocks_session`, `hard_lock_missing_protection`, and
  `profit_protect_reduce`.
- Local smoke summary: all six scenarios produced invariant report `pass` with
  `runtime_effect=none`, `trading_permission_effect=none`, and no exchange,
  account, order, transfer, or withdrawal side effect.
- Targeted tests passed:
  `pytest -q tests/unit/test_personal_campaign_sandbox.py tests/unit/test_personal_campaign_schema_docs.py tests/unit/test_personal_campaign_schema_examples.py`
  -> 28 passed.
- Extended boundary tests passed:
  `pytest -q tests/unit/test_tiny001d1a_controlled_signal_injection.py tests/unit/test_tiny001d4_once_per_session_guard.py tests/unit/test_personal_campaign_sandbox.py tests/unit/test_personal_campaign_schema_docs.py tests/unit/test_personal_campaign_schema_examples.py`
  -> 61 passed.
- `python3 -m compileall -q src/domain/personal_campaign.py src/application/personal_campaign_sandbox.py`
  passed.
- `git diff --check` passed.
- No core execution files, runtime profiles, env files, exchange gateway, real
  account path, testnet order path, or credentials were modified.
- Testnet smoke was not executed in this PLC verification because, at that
  point, the PLC mainline was still treated as docs/design/sandbox only and
  `TC-TINY-001D-1` was still a separate Owner-approval boundary for first
  testnet ENTRY. ADR-0009 later clarified that non-real-live testnet work may
  be requested after scoped verification and explicit Owner authorization.

## 2026-05-25 (ADR-0009 Non-Real-Live Boundary Clarification)

- Owner clarified the execution boundary: except for real live trading, all
  development and research work may proceed after reasonable scoped testing and
  explicit Owner authorization for the specific action.
- Added ADR-0009 to distinguish non-real-live runtime/paper/testnet/
  tiny-live-style work from prohibited real live trading.
- Updated roadmap, Live-safe program, runtime safety boundary, promotion gate,
  PLC mainline, PLC checklist, PLC sandbox note, task board, and AGENTS.md to
  use the new action gate.
- No runtime code, runtime profile, env file, exchange gateway, credentials, or
  order path was changed by this boundary clarification.

## 2026-05-27 (BRC-R5-002 Admission Gate Phase 1)

- Added ADR-0013 and Phase 1 state doc for BRC-R5-002 Strategy Family Trial Admission Gate.
- Framed Admission Gate as funded validation admission, not strict strategy approval; default decision bias is `admit_with_constraints`.
- Added PG-backed admission facts, repository, RiskCapitalAdapter interface, evaluation skeleton, BRC admission APIs, Owner risk acceptance persistence, and focused tests.
- Phase 1 explicitly does not implement runtime execution, live enablement, trading endpoints, auto execution, `create_gated_trial_from_admission`, campaign/trial creation, withdrawal/transfer, or LLM direct execution.

## 2026-05-27 (BRC-R5-002 Admission Gate Phase 2)

- Added `BrcAdmissionRiskCapitalAdapter` as the default Phase 2 resolution adapter while keeping `PendingRiskCapitalAdapter` available for unresolved/fail-safe behavior.
- Defined the installable constraint contract in `trial_constraint_snapshot.constraints_json`, including source, risk profile, execution mode, env/stage, account facts status, budgets/notional/leverage/attempts, allowed symbols/timeframes, review requirements, cooldowns, blockers, warnings, and limitations.
- Testnet development validation can now produce conservative `fallback_policy` installable constraints marked non-live. Live funded validation remains strict: unavailable account facts, reconciliation mismatch, or unknown unmanaged exposure block; missing concrete risk/capital resolution stays pending.
- Owner risk acceptance remains limited to installable constraints only. Phase 2 still does not create campaigns/trials, install runtime constraints, add trading endpoints, enable live, or implement auto execution.

## 2026-05-27 (BRC-R5-002 Admission Gate Phase 3)

- Added `create_gated_trial_from_admission` to Operation Layer as a preflight-only Admission readiness check.
- Preflight validates admissible decision, non-expired/installable constraint snapshot, Owner risk acceptance for funded validation, playbook pinning, account facts ref, live funded account facts boundaries, audit writability, and active-campaign conflict when checkable.
- Preflight response now exposes admission, strategy family, constraints, risk acceptance, env/stage, execution mode, and next-step summaries.
- Confirm remains disabled/not implemented and persists a blocked result confirming no trial, campaign, runtime carrier, runtime constraints, order, live execution, withdrawal, or transfer was created.

## 2026-05-27 (BRC-R5-002 Admission Gate Phase 4)

- Added `brc_admission_trial_bindings` as the admission-to-future-carrier binding skeleton.
- Upgraded `create_gated_trial_from_admission` from preflight-only to binding-reservation-only: capability status is `binding_reservation_available`, confirm phrase is `CONFIRM_RESERVE_ADMISSION_BINDING`, and confirm can persist `binding_reserved` only.
- Preflight now blocks an existing active admission-trial binding for the same admission decision and states that no runtime trial will start, no campaign will be created, no runtime constraints will be installed, and no orders will be placed.
- Confirm returns binding/audit refs and explicitly records no campaign creation, runtime carrier creation, runtime constraint installation, order placement, live execution, withdrawal, or transfer.

## 2026-05-27 (BRC-R5-002 Admission Gate Phase 5)

- Added a separate `create_campaign_from_admission_binding` Operation for campaign carrier shell creation, keeping binding reservation and campaign shell creation distinct in audit and idempotency semantics.
- Added BRC campaign metadata for admission-created carrier shells: admission binding, decision, strategy family version, playbook, constraint snapshot, env/stage, execution mode, and explicit non-runtime flags.
- Confirm can create only a BRC campaign shell and advance the binding to `campaign_created`; it does not install runtime constraints, switch runtime carrier, start strategy execution, place orders, enable live, withdraw, or transfer.
- Preflight blocks missing/non-reserved bindings, pending constraints, missing or mismatched funded risk acceptance, rejected/parked admissions, live funded account fact blockers, duplicate campaign creation, and active campaign conflicts.

## 2026-05-27 (BRC-R5-002 Admission Gate Phase 6)

- Added `install_runtime_constraints_from_admission_campaign` as a metadata-only Operation for campaign-created admission bindings.
- Confirm installs the installable constraint snapshot into campaign metadata and advances the binding to `runtime_constraints_installed`.
- This state remains not runtime started, not strategy active, not trial started, not live enabled, not auto execution, and not order-capable.

## 2026-05-27 (BRC-R5-002 Admission Gate Phase 7)

- Added `prepare_runtime_carrier_from_admission_campaign` as a metadata-only Operation for constraints-installed admission campaigns.
- Confirm writes `carrier_ready=true`, `runtime_status=carrier_ready_not_started`, preparation refs, and explicit false runtime/strategy/trial/order flags.
- `carrier_ready` is not runtime started, not strategy active, not trial started, not live enabled, not `auto_within_budget`, and not order-capable.

## 2026-05-27 (BRC-R5-002 Admission Gate Phase 8)

- Added `prepare_runtime_start_from_admission_carrier` as a metadata-only Operation for carrier-ready admission campaigns.
- Confirm writes `runtime_start_ready=true`, `runtime_status=runtime_start_ready_not_started`, start-readiness refs, and explicit false runtime/strategy/trial/order flags.
- `runtime_start_ready` is not runtime started, not strategy active, not trial started, not live enabled, and not order-capable. Observe-only/no-entry enforcement and auto-within-budget execution remain future phases.

## 2026-05-27 (BRC-R5-002 Admission Gate Phase 9)

- Added `evaluate_trial_trade_intent` as an Operation-backed execution-mode enforcement contract.
- Added `brc_trial_trade_intents` as a PG-backed non-executable evidence ledger for observe_only/no_entry decisions.
- `observe_only` records would-have-traded evidence, `no_entry` blocks entry/increase while allowing non-executable exit/reduce evidence, `auto_within_budget` checks constraints completeness only, and `owner_confirm_each_entry` remains unavailable.
- No runtime start, strategy activation, order, execution intent, live path, auto execution, cancel/close/flatten, withdrawal, or transfer is added.

## 2026-05-27 (BRC-R5-002 Admission Gate Phase 10)

- Added `prepare_runtime_handoff_from_admission_campaign` as a metadata-only Operation for runtime-start-ready admission campaigns.
- Confirm writes `runtime_handoff_ready=true`, `runtime_status=runtime_handoff_ready_not_started`, handoff-readiness refs, and explicit false runtime/strategy/trial/order flags.
- `runtime_handoff_ready` is not runtime started, not strategy active, not trial started, not live enabled, and not order-capable. Actual runtime start and auto-within-budget execution remain future phases.

## 2026-05-27 (BRC-R5-002 Admission Gate Phase 11)

- Added preflight-only `start_runtime_from_admission_handoff` for handoff-ready admission campaigns.
- Capability is `operation_preflight_available` with `executable_through_operation=false`; confirm is disabled/not implemented and returns blocked semantics.
- Preflight checks runtime handoff readiness, false runtime/strategy/trial/order flags, installed constraints, execution-mode contract availability, account facts freshness, audit writability, runtime profile/env safety, and conflicting runtime/hard-lock conditions.
- Phase 11 does not start runtime, set `runtime_started=true`, activate strategy, enable auto execution, create orders, create execution intents, or change the latest actual campaign state beyond `runtime_handoff_ready_not_started`.

## 2026-05-27 (BRC-R5-002 Admission Gate Phase 12)

- Upgraded `start_runtime_from_admission_handoff` from preflight-only to runtime-state-only execution.
- Confirm writes `runtime_started=true`, `runtime_status=runtime_started_strategy_inactive`, runtime-start refs, and explicit false strategy/trial/order/auto flags.
- New operations against an already `runtime_started_strategy_inactive` campaign return noop semantics rather than duplicating the transition.
- Runtime started is not strategy active, not trial started, not live enabled, not auto-execution-enabled, and not order-capable. Strategy activation and execution-mode runtime enforcement remain future phases.

## 2026-05-27 (BRC-R5-002 Admission Gate Phase 12.5)

- Completed runtime state alignment review without adding operations or changing runtime execution.
- Clarified that binding status remains `runtime_constraints_installed`; runtime state is expressed by campaign metadata.
- Hardened tests around `runtime_started_strategy_inactive`: strategy/trial/order/auto/live flags remain false and no execution-intent or order surface is added.
- At the Phase 12.5 checkpoint, strategy activation readiness was still future work; `auto_within_budget` actual execution remains a later runtime-enforcement phase.

## 2026-05-27 (BRC-R5-002 Admission Gate Phase 13)

- Added `prepare_strategy_activation_from_admission_runtime` as metadata-only strategy activation readiness.
- Confirm writes `strategy_activation_ready=true`, `runtime_status=strategy_activation_ready_not_active`, readiness refs, and explicit false strategy/trial/order/auto/signal-loop/live flags.
- `strategy_activation_ready` is not strategy active, not trial started, not signal-loop active, not auto-execution-enabled, and not order-capable.
- Actual strategy activation and `auto_within_budget` actual execution remain future explicitly authorized runtime phases.

## 2026-05-27 (BRC-R5-002 Admission Gate Phase 14)

- Added `activate_strategy_from_admission_runtime` as metadata-only non-execution strategy state activation.
- Confirm writes `strategy_state=strategy_active_no_execution`, `strategy_activation_state=active_no_execution`, `runtime_status=strategy_active_no_execution`, activation refs, and explicit false execution/signal-loop/trial/order/auto/live flags.
- `strategy_active_no_execution` is not order-capable strategy, not signal-loop active, not trial started, not auto-execution-enabled, and not live enabled.
- Signal loop / observe-gate enablement and `auto_within_budget` actual execution remain future explicitly authorized runtime phases.

## 2026-05-27 (BRC-R5-002 Admission Gate Phase 15)

- Added `prepare_signal_loop_from_admission_strategy` as metadata-only signal loop readiness.
- Confirm writes `signal_loop_ready=true`, `runtime_status=signal_loop_ready_not_started`, readiness refs, and explicit false signal-generation/trade-intent/execution-intent/order/auto/trial/live flags.
- `signal_loop_ready` is not signal-loop started, not signal generation, not observe-only/no-entry intent behavior, not auto execution, and not order-capable.
- Signal loop start, observe-gate runtime integration, and `auto_within_budget` actual execution remain future explicitly authorized runtime phases.

## 2026-05-27 (BRC-R5-002 Admission Gate Phase 16)

- Added `start_signal_loop_from_admission_strategy` as metadata-only signal loop start state.
- Confirm writes `signal_loop_started=true`, `signal_loop_enabled=true`, `signal_loop_enabled_scope=non_trading_loop_state`, `runtime_status=signal_loop_started_no_signal`, start refs, and explicit false signal-generation/trade-intent/execution-intent/order/auto/trial/live flags.
- `signal_loop_started_no_signal` is not signal generation, not observe-only/no-entry actual intent behavior, not auto execution, not trial started, and not order-capable.
- Signal generation/evaluation, executable observe-only/no-entry runtime integration, and `auto_within_budget` actual execution remain future explicitly authorized runtime phases.

## 2026-05-27 (BRC-R5-002 Admission Gate Phase 17)

- Added `evaluate_signal_from_admission_strategy` as metadata-only signal evaluation.
- Confirm writes `signal_evaluated=true`, `signal_generated=true`, `runtime_status=signal_evaluated_no_intent`, evaluation refs, signal snapshot/evaluation summary metadata, and explicit false trade-intent/execution-intent/order/auto/trial/live flags.
- `signal_evaluated_no_intent` is not a trade intent, not an execution intent, not an order-capable state, not auto execution, and not trial started.
- Signal-to-trial-trade-intent conversion, executable observe-only/no-entry runtime integration, and `auto_within_budget` actual execution remain future explicitly authorized runtime phases.

## 2026-05-25 (BRC-R0/R1 Bounded Risk Campaign Implementation)

- Accepted ADR-0012 and reframed PLC from "Strategy Execution Platform" toward
  `Bounded Risk Campaign System`: isolated risk bucket, Owner-selected
  playbook, bounded attempts, hard risk envelope, profit-protect/loss-lock, and
  final outcome evidence.
- Implemented pure BRC domain objects and service logic for campaign creation,
  playbook switch decisions, ETH/BTC attempt sequence, mock PnL events,
  profit-protect, loss-lock, evidence packet, and final outcome.
- Added PG persistence and Alembic revision `012` for `brc_campaigns`,
  `brc_playbook_switch_decisions`, `brc_campaign_events`, and
  `brc_mock_pnl_events`.
- Added controlled `brc_btc_eth_testnet_runtime` profile seed with fixed
  ETH/BTC caps, max attempts `2`, max simultaneous positions `1`, and program
  withdrawal disabled. It was initially seeded conservatively; later local
  acceptance defaults make this profile the testnet-first BRC validation path.
- Added local/internal BRC test endpoints under `/api/runtime/test/brc/*`.
  They require runtime control enabled, testnet, and the BRC profile; mutation
  endpoints also require test signal injection enabled. Request bodies cannot
  override controlled entry/close amount, side, leverage, SL, or TP.
- Mock PnL is BRC business-state evidence only. It does not mutate exchange
  fills, account balance, daily risk stats, or withdrawals.
- Targeted local tests were added for BRC service rules and BRC API acceptance
  flow. Binance testnet smoke remains the final acceptance gate.
- BRC-R0/R1 Binance testnet smoke passed after one repair cycle:
  - first BTC retry was blocked by account-level daily trade count because the
    same-day runtime trade count was already `10` and profile cap was `10`;
  - repaired BRC entry handling so blocked/failed execution intents do not
    record attempt entry;
  - set BRC testnet profile `daily_max_trades=20` while keeping BRC max attempts
    at `2`;
  - final retry completed ETH controlled entry/close, mock profit,
    BTC controlled entry/close, mock loss, third-attempt block, loss-locked
    switch block, evidence packet, and final outcome
    `ended_testnet_rehearsal_complete_loss_locked`;
  - GKS restored active, startup guard blocked, runtime state closed-safe,
    runtime stopped, and port `8001` released.

## 2026-05-26 (BRC-R2-001 Low-Friction Review Layer)

- Opened `BRC-R2-001` as the next BRC mainline step after the successful
  R0/R1 testnet rehearsal.
- Added the R2 plan in
  `docs/ops/brc-r2-low-friction-ops-review-plan.md`.
- Scope remains read-only for this slice: campaign review packet,
  next-campaign eligibility gate, local operator helper, and narrow
  text-to-read-action draft. No new order path, withdrawal/transfer endpoint,
  real-live authority, automatic sizing, strategy implementation, or
  natural-language auto-execution is introduced.

## 2026-05-26 (BRC-R2-002 Owner-Confirmed Read-Only Runner)

- Extended the BRC operator medium from draft-only to
  `draft -> plan -> confirmed read-only run`.
- The runner requires `CONFIRM_READ_ONLY_BRC`, executes only
  review/eligibility/evidence read actions, and marks run results with
  `mutation_executed=false`, `withdrawal_executed=false`, and
  `live_ready=false`.
- No new testnet order path, withdrawal/transfer endpoint, real-live
  authority, automatic sizing, strategy implementation, or natural-language
  auto-execution is introduced.

## 2026-05-26 (BRC-R2-003 Operator Action Ledger Persistence)

- Added the operator action ledger as the database fact source for
  `Owner text -> persisted plan -> action_id -> confirmed read-only run`.
- `/operator/plan` persists a ledger row and returns `action_id`; canonical
  run uses `/operator/actions/{action_id}/run`; compatibility `/operator/run`
  creates a ledger row internally.
- Confirmation failures and unknown text are persisted as `blocked`; executed
  rows preserve `mutation_executed=false`, `withdrawal_executed=false`, and
  `live_ready=false`.
- No new order path, withdrawal/transfer endpoint, real-live authority,
  automatic sizing, strategy implementation, or natural-language
  auto-execution is introduced.

## 2026-05-26 (BRC-R2-004 Review Decision Governance)

- Added persisted Owner review decisions as the final operation-governance
  ledger after read-only operator runs.
- Review decisions record campaign id, optional source action id, decision,
  reason, and next recommended task; they do not create campaigns or mutate
  runtime/exchange/account state.
- Review decision rows enforce `testnet_only=true`,
  `real_live_authorized=false`, `withdrawal_authorized=false`, and
  `strategy_execution_authorized=false`.

## 2026-05-26 (BRC-R3 LangGraph LLM Operator Gateway)

- Added a LangGraph-shaped BRC operator workflow:
  `Owner text -> normalized intent -> policy validation -> persisted workflow
  -> Owner confirmation -> allowed action -> persisted result`.
- Added `brc_llm_intents` and `brc_workflow_runs` as the durable fact source
  for LLM-normalized intents and workflow state. LangGraph checkpointing is
  orchestration-only and does not replace PG audit tables.
- Added OpenAI-compatible LLM provider configuration through environment
  variables only. API keys are not persisted or logged.
- Allowed actions are limited to read review packet, read next eligibility,
  read evidence, and the fixed BRC ETH -> BTC controlled testnet rehearsal.
  Forbidden live/mainnet, withdrawal/transfer, strategy execution, autonomous
  order, sizing/leverage/side override, and broader multi-symbol requests are
  blocked before execution.
- Added internal API and CLI wrappers for LLM workflow create/get/list/confirm.
  Read-only confirmation remains `CONFIRM_READ_ONLY_BRC`; controlled testnet
  rehearsal confirmation is `CONFIRM_BRC_TESTNET_REHEARSAL`.

## 2026-05-26 (BRC External Audit Backlog Alignment)

- External audit immediate fixes were completed in commit `bc7e2ad`:
  GKS constructor fail-closed, campaign transition owner-review/flat-proof
  enforcement, explicit trigger requirement for terminal runtime states,
  ended-campaign mock PnL guard, fixed testnet rehearsal result validation,
  loss-locked next-campaign creation gate, and LLM testnet intent upgrade
  guard.
- Recorded deferred audit/deployment items in
  `docs/ops/brc-pre-deploy-audit-backlog.md`.
- Deferred items are intentionally tied to later gates:
  Feishu callback integration, cloud deployment, Web mutation controls, and
  strategy-pool construction. They are not prerequisites for continuing the
  current local-only BRC operation-governance loop.
- Recommended next capability is `BRC-R4-001 Local Operator Console`: a
  local-only Web surface for current campaign state, review packet,
  next-campaign eligibility, LLM/operator plan, explicit confirmation,
  action/workflow ledger, review decision, and next gate.
- Boundary preserved: no real live/mainnet, no withdrawal/transfer endpoint,
  no autonomous strategy execution, no automatic sizing/leverage/side decision,
  no auto-filled confirmation phrase, and no new order path beyond existing
  fixed BRC testnet workflow.

## 2026-05-26 (BRC-R4 API Surface Cleanup Planning)

- Inspected the current backend API surface before Web implementation.
- Current route inventory:
  - `src/interfaces/api.py`: 79 legacy monolith routes;
  - `src/interfaces/api_console_runtime.py`: 47 runtime/BRC/test routes;
  - `src/interfaces/api_console_research.py`: 6 read-only research routes;
  - `src/interfaces/api_research_jobs.py`: 10 research job/candidate routes;
  - `src/interfaces/api_v1_config.py`: 42 broad config routes;
  - `src/interfaces/api_profile_endpoints.py`: 8 profile routes.
- Added `docs/ops/brc-r4-api-surface-cleanup-plan.md`.
- Planning conclusion: BRC Web should depend on a BRC-first API contract, not
  on the current legacy API surface. The target split is BRC campaign,
  BRC operator, BRC LLM workflows, runtime read, runtime control, dev-testnet
  BRC, and later research/strategy-pool routers.
- Recommended implementation order:
  contract freeze -> router split without behavior change -> dependency
  cleanup to `RuntimeContext` -> Web console implementation -> pre-deploy
  security gate.
- No API code, frontend code, runtime profile, exchange path, testnet action,
  real live action, withdrawal/transfer, strategy execution, or automatic
  sizing path was changed.

## 2026-05-25 (TC-TINY-001D-1 Authorization Package)

- Prepared ADR-0009 action request for one controlled Binance testnet
  order-lifecycle smoke:
  `docs/ops/tc-tiny-001d-1-adr0009-authorization-request.md`.
- Updated the older `docs/ops/TC-TINY-001D-1-proposal.md` to mark it as
  superseded for execution authorization and to reflect that the controlled
  endpoint already exists.
- Verified current controlled endpoint tests:
  `pytest -q tests/unit/test_tiny001d1a_controlled_signal_injection.py tests/unit/test_tiny001d4_once_per_session_guard.py`
  -> 33 passed.
- Verified `python3 -m compileall -q src/interfaces/api_console_runtime.py` and
  `git diff --check` passed.
- No runtime, testnet, account, credential, or order action was executed. The
  next step is explicit Owner authorization for the exact ADR-0009 action.

## 2026-05-25 (TC-TINY-001D-1 Authorized Testnet Smoke)

- Owner authorized the ADR-0009 action for one Binance testnet controlled
  order-lifecycle smoke under `sim1_eth_runtime`, max `0.01 ETH`, with GKS
  restore and runtime stop required after verification.
- Preflight verified `.env` / `.env.local` effective safety fields without
  printing secrets: `EXCHANGE_TESTNET=true`, `RUNTIME_PROFILE=sim1_eth_runtime`,
  and Binance testnet API key/secret present but masked.
- Initial runtime start failed because local PG was not accepting connections;
  after Owner started PG in Docker, runtime started and reached `SYSTEM READY`.
- Executed exactly one controlled endpoint call:
  `POST /api/runtime/test/smoke/execute-controlled-entry`.
- Controlled endpoint completed with:
  `intent_f45649feb9fd`, `signal_id=sig_fec09157c3cc`, `amount=0.01`,
  `testnet=true`, `profile=sim1_eth_runtime`, `attempt_locked=true`,
  `notional=20.9347`, and `min_notional=20`.
- Exchange testnet ENTRY filled:
  local order `ord_e1331c9f`, exchange order `8728148126`.
- Exchange-native protection orders were mounted:
  TP1 `ord_TP1_2730d882` / `8728148137`,
  TP2 `ord_TP2_9f28da89` / `8728148143`,
  SL `ord_sl_11671362` / `1000000084871663`.
- Risk decision audit recorded startup guard allow, GKS allow, and
  `control.test_signal_injection` executed for the controlled intent.
- GKS was restored active immediately after the controlled endpoint returned.
- Direct Binance testnet cleanup closed the residual `0.01 ETH` position with
  reduce-only market order `8728150129`; direct exchange verification reported
  `positionAmt=0.000` and zero target open protection orders.
- Runtime `/api/runtime/positions` was initially stale after direct cleanup,
  then periodic reconciliation cleared positions and produced an external close
  marker.
- PG `positions` for `sig_fec09157c3cc` was marked closed with quantity `0`,
  but the local TP1, TP2, and SL order rows remained `OPEN` and were classified
  as `stale_after_external_close` / `manual_data_hygiene_required`.
- Daily risk stats did not update for this controlled close because the cleanup
  was an external reduce-only order with `pnl_status=unresolved_no_reliable_fill`.
- Runtime was stopped after verification; no `src.main` process remained and
  local port `8000` was no longer listening.
- Observations for review:
  - periodic reconciliation after external cleanup reported `total=3825`,
    `severe=830`, and `warning=2995`;
  - protection health set a critical
    `PROTECTION_LOCAL_SL_MISSING_ON_EXCHANGE` block with count `829`;
  - SL STOP_MARKET `fetch_order` confirmation returned a Binance testnet
    "Order does not exist" response immediately after submission, while
    order-watch later observed the SL as open;
  - local stale protection-order hygiene remains open before this can be treated
    as a fully clean lifecycle smoke.
- Added follow-up `TC-TINY-001D-2` for external-close local order hygiene design
  before any implementation. Existing code is intentionally conservative:
  external close projection marks positions closed unresolved, blocks new
  entries, and preserves stale protection-order evidence instead of silently
  rewriting local order state.

## 2026-05-25 (TC-TINY-001D-2 External-Close Local Order Hygiene)

- Owner authorized continuing the follow-up with minimal manual involvement and
  allowed direct cleanup of historical local data.
- Implemented local-only external-close hygiene:
  - after reconciliation proves exchange-flat and position projection marks a
    local position unresolved-closed, active local TP/SL rows for the same
    signal are terminalized to `CANCELED`;
  - terminalization is system-triggered, does not call the exchange, sets
    `exit_reason=EXTERNAL_CLOSE_LOCAL_HYGIENE`, and records audit metadata;
  - startup and periodic reconciliation refresh the read model after
    external-close state changes before protection-health evaluation.
- Cleaned historical local PG data for `ETH/USDT:USDT`:
  - before cleanup: 2174 active local protection rows without an active local
    position;
  - cleanup action: local PG-only status transition to `CANCELED` with
    `exit_reason=EXTERNAL_CLOSE_LOCAL_HYGIENE_HISTORICAL`;
  - audit rows written: 2174;
  - after cleanup: 0 active local protection rows without an active local
    position.
- Binance testnet read-only verification after cleanup:
  `positionAmt=0.000`, open orders `0`.
- Scoped verification passed:
  `pytest -q tests/unit/test_tiny001d1b_external_close_monitor.py tests/unit/test_ls003b_periodic_reconciliation.py tests/unit/test_order_lifecycle_service_pending_updates.py tests/unit/test_ls003a_reconciliation_read_model.py tests/unit/test_tiny001c_protection_health_monitor.py tests/unit/test_tiny001d1a_controlled_signal_injection.py tests/unit/test_tiny001d4_once_per_session_guard.py`
  -> 79 passed.
- Compile verification passed:
  `python3 -m compileall -q src/application/external_close_monitor.py src/application/order_lifecycle_service.py src/application/periodic_reconciliation.py src/main.py`.

## 2026-05-25 (TC-TINY-001D-2 Testnet Follow-up Verification)

- Executed a second authorized Binance testnet controlled smoke to validate the
  hygiene path after implementation:
  - runtime profile: `sim1_eth_runtime`;
  - exchange mode: `EXCHANGE_TESTNET=true`;
  - controlled endpoint call count: 1;
  - amount: `0.01 ETH`;
  - intent: `intent_55db456b02ac`;
  - signal: `sig_d191164ff9bc`;
  - controlled response: `status=completed`, `attempt_locked=true`,
    `notional=20.9779`, `min_notional=20`.
- ENTRY and protection evidence:
  - ENTRY local order `ord_3691e21f`, exchange order `8728201255`;
  - SL local order `ord_sl_78c9954c`, exchange order `1000000084892721`;
  - TP1 local order `ord_TP1_b582d57c`, exchange order `8728201272`;
  - TP2 local order `ord_TP2_3be90dae`, exchange order `8728201281`.
- GKS was restored active immediately after the endpoint returned.
- Direct Binance testnet cleanup closed the `0.01 ETH` position with reduce-only
  market order `8728202891`; read-only verification reported
  `positionAmt=0.000` and open orders `0`.
- Follow-up runtime startup reconciliation closed the local position,
  projected realized PnL `0.472000000000000000`, and updated daily risk stats
  to realized PnL `0.951700000000000000`, trade count `2`.
- Extended local hygiene terminalized the remaining local protection rows:
  `ord_sl_78c9954c`, `ord_TP1_b582d57c`, and `ord_TP2_3be90dae` ->
  `CANCELED` with `exit_reason=EXTERNAL_CLOSE_LOCAL_HYGIENE`.
- Added healed-read-model clearing for stale protection-health blocks.
- Periodic reconciliation after the fix reported `total=821`, `severe=0`,
  `warning=821`; warnings are historical `local_order_missing_on_exchange`
  noise, not protection-health critical blocks.
- Final state:
  - runtime stopped;
  - no `src.main` process and no local `8000` listener;
  - Binance testnet `positionAmt=0.000`, open orders `0`;
  - active local protection rows without active local position: `0`.
- Scoped verification passed:
  `pytest -q tests/unit/test_tiny001d1b_external_close_monitor.py tests/unit/test_ls003b_periodic_reconciliation.py tests/unit/test_order_lifecycle_service_pending_updates.py tests/unit/test_ls003a_reconciliation_read_model.py tests/unit/test_tiny001c_protection_health_monitor.py tests/unit/test_tiny001d1a_controlled_signal_injection.py tests/unit/test_tiny001d4_once_per_session_guard.py`
  -> 82 passed.
- `python3 -m compileall -q src/application/protection_health_monitor.py src/application/external_close_monitor.py src/application/order_lifecycle_service.py src/application/periodic_reconciliation.py src/main.py`
  passed.
- `git diff --check` passed.

## 2026-05-25 (Post-Smoke Planning Snapshot)

- Added a current planning snapshot to
  `docs/ops/live-safe-v1-task-board.md`.
- Short-term priorities:
  - clean remaining historical `local_order_missing_on_exchange` warning noise
    after query proof and without exchange mutation;
  - design a runtime-managed controlled close smoke to replace direct exchange
    cleanup;
  - harden STOP_MARKET confirmation fallback for Binance testnet timing quirks;
  - specify the first read-only PLC runtime adapter;
  - refresh the LS-003 structured-runtime-logs task card around the new
    reconciliation/protection-health events.
- Long-term priorities:
  - PLC promotion ladder from local sandbox to read-only runtime, paper,
    testnet, tiny-live-style rehearsal, and only later real-live review;
  - durable campaign risk state machine;
  - account risk state machine and liquidation/margin safety checks;
  - multi-symbol runtime readiness;
  - evidence-to-strategy-contract pipeline that keeps research output separate
    from runtime authority.
- Real live trading remains out of scope unless separately and explicitly
  authorized.

## 2026-05-25 (Short-Term Task Completion Pass)

- TC-TINY-001D-3: completed local PG-only historical warning cleanup.
  - Proof before cleanup: 821 `ETH/USDT:USDT` `OPEN` ENTRY rows and 0 active
    positions.
  - Backup table: `ops_backup_orders_tiny001d3_20260525` with 821 rows.
  - Mutation: terminalized 821 stale ENTRY rows to `CANCELED` with
    `HISTORICAL_LOCAL_ENTRY_WARNING_CLEANUP`.
  - Audit: inserted 821 `ORDER_CANCELED` rows with
    `historical_local_entry_warning_cleanup` metadata.
  - Proof after cleanup: no active `SUBMITTED` / `OPEN` /
    `PARTIALLY_FILLED` ETH orders and stale ENTRY count 0.
  - Scope: local PG only; no exchange mutation.
- TC-TINY-001D-5: hardened STOP_MARKET confirmation fallback in
  `ExchangeGateway.confirm_order_exists`.
  - Recent order-watch evidence is checked before REST confirmation.
  - After a `fetch_order` miss, conditional `fetch_open_orders` is retried
    with bounded delays before fail-closed.
  - Targeted tests:
    `pytest -q tests/unit/test_tiny001d1b_sl_confirmation.py tests/unit/test_tiny001d1b_sl_metadata_validation.py`
    passed with 9 tests.
- TC-TINY-001D-4: completed design document
  `docs/ops/tc-tiny-001d-4-runtime-managed-close-smoke-design.md`.
  No runtime close endpoint was added yet because lifecycle-close semantics
  should be Codex-owned before exchange-connected testnet execution.
- PLC-RUNTIME-001: completed read-only runtime adapter spec in
  `docs/ops/plc-runtime-001-read-only-runtime-adapter-spec.md`.
- LS-003: refreshed Claude task card in
  `docs/ops/ls-003-structured-runtime-logs-task-card.md`.
- Verification:
  - `pytest -q tests/unit/test_tiny001d1b_sl_confirmation.py tests/unit/test_tiny001d1b_sl_metadata_validation.py tests/unit/test_tiny001d1b_external_close_monitor.py tests/unit/test_ls003b_periodic_reconciliation.py tests/unit/test_order_lifecycle_service_pending_updates.py tests/unit/test_ls003a_reconciliation_read_model.py tests/unit/test_tiny001c_protection_health_monitor.py tests/unit/test_tiny001d1a_controlled_signal_injection.py tests/unit/test_tiny001d4_once_per_session_guard.py`
    passed with 91 tests.
  - `python3 -m compileall -q src/infrastructure/exchange_gateway.py src/interfaces/api_console_runtime.py src/application/external_close_monitor.py src/application/order_lifecycle_service.py src/application/protection_health_monitor.py`
    passed.
  - `git diff --check` passed.
  - Binance testnet read-only check for `ETH/USDT:USDT` returned active
    positions `[]` and open orders count `0`.

## 2026-05-25 (PLC Phased Upgrade Phase 1)

- Committed the prior short-term Live-safe follow-up batch:
  `28e97c8 chore: complete short-term live-safe followups`.
- Added PLC phased upgrade ladder:
  `docs/ops/plc-phased-upgrade-v0.md`.
- Implemented Phase 1 read-only runtime adapter:
  `src/application/personal_campaign_runtime_adapter.py`.
- Added `ReadOnlyRuntimeAdapterPreview` to the PLC domain contracts.
- Added read-only adapter schema and SQ02 example:
  - `docs/schemas/personal_campaign/read_only_runtime_adapter_preview.schema.json`
  - `docs/schemas/personal_campaign/examples/read_only_runtime_adapter_preview_sq02.example.json`
- Adapter behavior:
  - closed/prior snapshot plus frozen contract can produce an allowed
    read-only `TradeIntent` preview;
  - future/current snapshots are rejected;
  - non-frozen contracts are rejected;
  - contract/snapshot mismatches are rejected;
  - output carries `read_only_no_order_authority` and has no order/exchange id.
- Verification:
  `pytest -q tests/unit/test_personal_campaign_runtime_adapter.py tests/unit/test_personal_campaign_sandbox.py tests/unit/test_personal_campaign_schema_docs.py tests/unit/test_personal_campaign_schema_examples.py`
  passed with 35 tests.

## 2026-05-25 (PLC Phased Upgrade Phase 2)

- Implemented Phase 2 paper observation packet:
  `src/application/personal_campaign_paper_observation.py`.
- Added `PaperObservationPacket` and `PaperObservationReviewStatus` to the PLC
  domain contracts.
- Added paper observation packet schema and SQ02 example:
  - `docs/schemas/personal_campaign/paper_observation_packet.schema.json`
  - `docs/schemas/personal_campaign/examples/paper_observation_packet_sq02.example.json`
- Packet behavior:
  - wraps only read-only runtime previews;
  - carries `paper_observation_no_order_authority`;
  - stores review status, operator notes, and optional review provenance;
  - reviewed packets require `reviewed_by` and `reviewed_at_ms`;
  - exported packet dict is JSON-ready without writing files or calling
    services.
- Verification:
  `pytest -q tests/unit/test_personal_campaign_paper_observation.py tests/unit/test_personal_campaign_runtime_adapter.py tests/unit/test_personal_campaign_schema_docs.py tests/unit/test_personal_campaign_schema_examples.py`
  passed with 24 tests.

## 2026-05-25 (PLC Phased Upgrade Phase 3 Design)

- Added bounded testnet rehearsal design:
  `docs/ops/plc-phase3-testnet-rehearsal-design.md`.
- Added draft ADR-0009 authorization request:
  `docs/ops/plc-phase3-adr0009-authorization-request.md`.
- Phase 3 verdict:
  `phase3_design_ready / execution_blocked`.
- Execution blockers:
  - runtime-managed controlled close is not implemented yet;
  - campaign risk state machine remains TODO;
  - account risk/liquidation safety checks remain TODO;
  - no specific Owner authorization has been requested or granted for one PLC
    Phase 3 rehearsal cycle.
- The design prefers the installed Binance official plugin for read-only
  market/testnet state checks when available, but explicitly forbids using it
  to bypass the runtime lifecycle for order placement, cancellation, or cleanup.

## 2026-05-25 (PLC Phase 3 Blocker Closure)

- Implemented the runtime-managed controlled close path for `TC-TINY-001D-4`:
  - added explicit `OrderRole.EXIT` support and PG/ORM constraint migration;
  - added `ExecutionOrchestrator.execute_controlled_close()`;
  - added `POST /api/runtime/test/smoke/execute-controlled-close`;
  - keeps the close reduce-only, `sim1_eth_runtime` only, Binance testnet only,
    max `0.01 ETH`, local/internal only, empty-body only, and once per runtime
    session.
- Added controlled close tests covering:
  - reduce-only market close through the gateway;
  - exit projection and daily stats callback;
  - protection-order exchange cancel plus local terminalization;
  - endpoint once-per-session guard and orchestrator delegation.
- Added Phase 3 safety specs:
  - `docs/ops/plc-campaign-risk-state-machine-spec.md`;
  - `docs/ops/plc-account-risk-liquidation-safety-spec.md`.
- Updated Phase 3 verdict:
  `phase3_pre_execution_review / authorization_required`.
- Remaining before testnet execution:
  - exact ADR-0009 Owner authorization for one rehearsal cycle.
- Verification completed:
  - `pytest -q tests/unit/test_tiny001d4_controlled_close.py tests/unit/test_tiny001d4_once_per_session_guard.py tests/unit/test_tiny001d1a_controlled_signal_injection.py tests/unit/test_tiny001d1b_external_close_monitor.py tests/unit/test_ls003b_periodic_reconciliation.py tests/unit/test_order_lifecycle_service_pending_updates.py tests/unit/test_ls003a_reconciliation_read_model.py tests/unit/test_tiny001c_protection_health_monitor.py tests/unit/test_personal_campaign_paper_observation.py tests/unit/test_personal_campaign_runtime_adapter.py tests/unit/test_personal_campaign_sandbox.py tests/unit/test_personal_campaign_schema_docs.py tests/unit/test_personal_campaign_schema_examples.py`
    passed with 126 tests.
  - `python3 -m compileall -q ...` passed for touched modules.
  - `git diff --check` passed.
- PG preflight completed:
  - backed up 3706 historical active local order rows to
    `ops_backup_orders_plc_phase3_20260525`;
  - terminalized 3706 historical active local order rows locally with audit
    metadata and no exchange mutation;
  - local active orders are now `0`;
  - `orders.ck_orders_order_role` now allows `EXIT`.
- Binance preflight completed:
  - official Binance plugin public futures ticker check for `ETHUSDT` passed;
  - project read-only Binance testnet check for `ETH/USDT:USDT` returned no
    nonzero positions and open orders `0`.

## 2026-05-25 (PLC Phase 3 Attempt 1)

- Owner authorized one ADR-0009 Binance testnet controlled rehearsal cycle.
- Runtime start evidence:
  - commit: `14f4a2f`;
  - profile: `sim1_eth_runtime`;
  - `exchange_testnet=true`;
  - startup reconciliation candidates `0`;
  - startup guard manually armed;
  - GKS temporarily set inactive for the authorized cycle.
- Controlled entry succeeded:
  - intent id: `intent_b8b65ad0e745`;
  - signal id: `sig_c205e2c08e64`;
  - amount: `0.01`;
  - entry exchange order id: `8728367551`;
  - local ENTRY status: `FILLED`;
  - local protection orders mounted: SL `1000000084961186`, TP1
    `8728367554`, TP2 `8728367574`.
- Controlled close placed and filled the reduce-only `EXIT`:
  - local EXIT id: `exit_controlled_cbcef6060340`;
  - exchange order id: `8728368262`;
  - status: `FILLED`;
  - average execution price: `2102.72`;
  - realized PnL: `-0.0085`;
  - daily risk stats updated to cumulative PnL `0.9432`, trade count `3`.
- Attempt 1 did not fully pass acceptance because the close endpoint returned
  HTTP 500 after the EXIT fill. Root cause: Binance had already removed or
  expired at least one protection order after the reduce-only close, and
  `_cancel_remaining_protection_orders_after_controlled_close()` treated
  `OrderNotFoundError` during cleanup as fatal.
- Safety restoration:
  - read-only Binance testnet check after close returned no nonzero
    `ETH/USDT:USDT` position and open orders `0`;
  - GKS was restored active before cleanup review;
  - runtime process was stopped;
  - three local stale protection rows for `sig_c205e2c08e64` were terminalized
    locally with audit metadata and no exchange mutation;
  - local active orders are `0`.
- Follow-up patch:
  - controlled close cleanup now treats `OrderNotFoundError` for protection
    order cancellation as idempotent after the close is already confirmed;
  - other cancellation failures still fail the close path;
  - targeted verification passed: 65 tests, `compileall`, and
    `git diff --check`.
- Current verdict:
  `attempt1_safe_flat_but_not_acceptance_pass / retry_authorization_required`.

## 2026-05-25 (PLC Phase 3 Retry Completion)

- Owner authorized one additional bounded ADR-0009 Binance testnet retry.
- Preflight:
  - commit: `d8ade02`;
  - local active orders: `0`;
  - local active positions: `0`;
  - GKS active before start;
  - Binance testnet read-only check for `ETH/USDT:USDT`: no nonzero position,
    open orders `0`;
  - `tests/unit/test_tiny001d4_controlled_close.py` passed with 4 tests before
    retry.
- Runtime start evidence:
  - profile: `sim1_eth_runtime`;
  - `exchange_testnet=true`;
  - startup reconciliation candidates `0`, failures `0`;
  - startup guard manually armed for the retry;
  - GKS temporarily set inactive only for the authorized cycle.
- Controlled entry succeeded:
  - intent id: `intent_656a68bcc2c5`;
  - signal id: `sig_ab0a0a0b495c`;
  - amount: `0.01`;
  - entry exchange order id: `8728378151`;
  - local ENTRY status: `FILLED`;
  - protection orders mounted: SL `1000000084965165`, TP1 `8728378170`,
    TP2 `8728378187`.
- Patched controlled close succeeded:
  - response status: `FILLED`;
  - local EXIT id: `exit_controlled_4d0c9fe3059e`;
  - exchange order id: `8728378402`;
  - amount: `0.01`;
  - average execution price: `2101.62`;
  - terminalized protection orders: `3`;
  - endpoint returned success instead of HTTP 500.
- Projection and daily stats evidence:
  - local position `pos_sig_ab0a0a0b495c` is closed with quantity `0`;
  - realized PnL: `-0.0027`;
  - daily risk stats aggregate for `runtime:default` / `2026-05-25`:
    realized PnL `0.9405`, trade count `4`;
  - latest daily risk event key:
    `daily-risk:v1:runtime:default:2026-05-25:pos_sig_ab0a0a0b495c:exit_controlled_4d0c9fe3059e:0.01`.
- Final safety evidence:
  - GKS restored active with reason `PLC Phase 3 retry complete - restore GKS`;
  - local active orders: `0`;
  - local active positions: `0`;
  - Binance testnet final read-only check: no nonzero `ETH/USDT:USDT`
    position and open orders `0`;
  - manual bounded reconciliation read-model refresh persisted
    `1779690282549:ETH/USDT:USDT` with severe `0`, warning `0`, total `0`,
    consistent `true`;
  - runtime was stopped after verification.
- Current verdict:
  `phase3_complete_testnet_rehearsal_passed / phase4_still_blocked`.

## 2026-05-25 (PLC Phase 4 Readiness Review)

- Owner authorized Phase 4.
- Interpreted under the current PLC ladder as tiny-live-style readiness review
  only, not real-live trading authorization.
- Added `docs/ops/plc-phase4-tiny-live-style-readiness-review.md`.
- Phase 4 verdict:
  `phase4_review_complete / real_live_not_authorized / continue_non_real_live_hardening`.
- Blocking gaps before any real-live readiness can be reconsidered:
  - account risk and liquidation safety are still design-only;
  - campaign risk state machine is still design-only;
  - conditional SL visibility still creates temporary protection-health severe
    noise during active testnet exposure;
  - runtime control lifecycle needs explicit startup-guard reset and clean
    shutdown/port-release verification;
  - no strategy contract is promoted to real-live use.
- Added next non-real-live hardening tasks P4-001 through P4-005 to the task
  board.

## 2026-05-25 (PLC Phase 4 Local Hardening)

- Implemented P4-001 through P4-004 as non-real-live local hardening:
  - account risk/liquidation gate now blocks new entries fail-closed before
    CapitalProtection when account balance, positions, mark price, or
    liquidation distance are unavailable/degraded/critical;
  - campaign runtime state now persists in PG via `runtime_campaign_state`,
    exposes local/internal owner-control API, and allows new entries only in
    `armed`;
  - reconciliation now fetches normal open orders plus Binance conditional
    STOP_MARKET open-order views to reduce false protection-health severe
    noise when exchange-native SL exists;
  - startup guard now has explicit block/reset API and runtime shutdown paths
    reset it to `RUNTIME_SHUTDOWN_RESET`.
- Added migration `010_create_runtime_campaign_state`.
- Local PG verification:
  - attempted Alembic against the configured local PG and found the older
    migration chain is not clean-install safe because `002_create_orders_positions`
    references `signals` before the clean schema has `signals`;
  - cleared local PG historical schema under the previously approved
    disposable-data boundary;
  - restored runtime PG schema with `PGCoreBase.metadata.create_all()`;
  - verified `CampaignStateService` creates/restores `runtime:default` as
    `observe` from PG.
- Targeted verification:
  - `pytest -q tests/unit/test_p4_account_risk_service.py tests/unit/test_p4_campaign_state_service.py tests/unit/test_gks_v0_global_kill_switch.py tests/unit/test_ls003a_reconciliation_read_model.py tests/unit/test_tiny001d1b_sl_confirmation.py tests/unit/test_rtg002_ws_api_task_lifecycle.py`
    passed with 75 tests.
  - `python3 -m compileall -q ...` passed for touched runtime/API/infra/tests.
  - `git diff --check` passed.
- No real-live trading, real-funds operation, real runtime profile change, or
  real account mutation was performed.
- Current verdict:
  `phase4_hardening_local_complete / real_live_not_authorized / runtime_smoke_pending`.

## 2026-05-25 (PLC Phase 4 Runtime/Testnet Smoke Completion)

- Repaired the clean PG Alembic path after clearing disposable local PG data:
  - migration `002_create_orders_positions` no longer references `signals`
    before `signals` exists on a clean schema;
  - migration `009_add_exit_order_role` now drops either historical
    `ck_orders_order_role` or `check_orders_order_role` before recreating the
    order-role constraint;
  - clean local PG `alembic upgrade head` reached `010 (head)`.
- Restored runtime PG schema/profile state after the clean migration proof:
  - `PGCoreBase.metadata.create_all()` initialized the current runtime tables;
  - `sim1_eth_runtime` was reseeded as the active read-only runtime profile;
  - GKS was seeded active with reason
    `P4 lifecycle smoke default safe state`;
  - `CampaignStateService` restored `runtime:default` as `observe`.
- Fixed runtime lifecycle shutdown:
  - signal handlers now request shutdown only; cleanup is centralized in
    `run_application()`;
  - the embedded uvicorn server gets `should_exit=True` and a bounded await;
  - `SignalPipeline`, `ConfigManager`, runtime repositories, PG engines,
    SQLite pooled connections, and the event-loop default executor are closed;
  - startup guard is reset to `RUNTIME_SHUTDOWN_RESET` during shutdown.
- No-order testnet lifecycle smoke passed:
  - health check `ok`;
  - startup guard initial `armed=false`;
  - GKS `active=true`;
  - campaign state `observe`;
  - manual startup-guard arm then block worked;
  - runtime exited naturally after SIGTERM;
  - port `8001` released;
  - no `Runtime shutdown non-daemon threads` warning;
  - no `PROTECTION_ORPHAN_REDUCE_ONLY_ORDER` block.
- Active-position Binance testnet smoke passed after fixing conditional order
  cancellation:
  - controlled ENTRY succeeded: `intent_4e135118e8be`,
    `sig_5faab5666eeb`, amount `0.01`, notional `21.086`;
  - during active exposure, direct read-only testnet check showed position qty
    `0.01`, normal open orders `2`, conditional stop open orders `1`, and
    stop reduce-only count `1`;
  - periodic reconciliation reported `consistent` while the exchange-native SL
    was active;
  - no protection-health missing/orphan block appeared in the runtime log;
  - controlled close returned `FILLED` with EXIT
    `exit_controlled_f46d6fb36279`, exchange order `8728507418`, and
    terminalized protection orders `3`;
  - runtime close canceled the Binance conditional SL through the stop-order
    fallback path;
  - final direct read-only testnet check showed position qty `0`, normal open
    orders `0`, and conditional stop open orders `0`;
  - GKS was restored active, campaign state reset to `observe`, startup guard
    blocked, runtime exited naturally, and port `8001` released.
- Additional finding during smoke:
  - Binance testnet conditional SL cancellation can return not found through
    the normal cancel endpoint while the order is still visible under
    `fetch_open_orders(..., params={"stop": True})`;
  - `ExchangeGateway.cancel_order()` now falls back to the stop-order view and
    cancels with `params={"stop": True}` after matching the same exchange id;
  - Binance may return `status=None` for that cancel response, which is now
    treated as `canceled`.
- Final targeted verification:
  - `pytest -q tests/unit/test_p4_account_risk_service.py tests/unit/test_p4_campaign_state_service.py tests/unit/test_gks_v0_global_kill_switch.py tests/unit/test_ls003a_reconciliation_read_model.py tests/unit/test_tiny001d1b_sl_confirmation.py tests/unit/test_rtg002_ws_api_task_lifecycle.py tests/unit/test_tiny001d4_controlled_close.py`
    passed with 81 tests;
  - compileall passed for touched runtime/API/gateway/migration/test files;
  - `git diff --check` passed;
  - final Binance testnet read-only check for `ETH/USDT:USDT` showed position
    qty `0`, normal open orders `0`, and conditional stop open orders `0`.
- No real-live trading, real-funds operation, real runtime profile change, or
  real account mutation was performed.
- Current verdict:
  `phase4_p4_001_to_p4_004_non_real_live_smoke_complete / real_live_not_authorized / strategy_promotion_still_blocked`.

## 2026-05-25 (ARCH-P4-001 Runtime/API Composition Root Governance)

- Added ADR-0010 for runtime/API ownership:
  - `src/main.py` is the only execution-runtime composition root;
  - embedded API receives the main-owned runtime through `RuntimeContext` bound
    to `app.state.runtime`;
  - standalone `uvicorn src.interfaces.api:app` is degraded to
    HTTP/config/read-only mode and must not create exchange/orchestrator
    runtime wiring.
- Added `src/application/runtime_context.py` as the explicit runtime container
  for exchange, repositories, services, orchestrator, startup summary, runtime
  tasks, and embedded API handles, with `start()` / `shutdown()` owner-state
  methods.
- Updated API runtime control reads to prefer the bound context while retaining
  module-global compatibility for existing endpoints/tests.
- Acceptance repair closed two governance gaps before commit:
  - `RuntimeContext` now maps legacy `_signal_repo` / `_repository` reads to
    `signal_repository`, and `_account_getter` to `get_account_snapshot`;
  - `clear_runtime_context()` clears the compatibility globals populated by
    `bind_runtime_context()`, so a process without bound context no longer
    retains stale exchange/orchestrator/control handles.
- Verification after acceptance repair:
  - targeted architecture/API/control/Phase 4 regression tests passed with
    87 tests;
  - compileall and `git diff --check` passed;
  - no-order testnet lifecycle smoke started embedded API with the bound
    context, read startup guard successfully, exited naturally on SIGTERM,
    released port `8001`, and logged no non-daemon thread warning.
- No strategy logic, runtime profile, trading parameters, credentials, or
  real-live permissions were changed.

## 2026-05-25 (PLC Phase 5A Small-Scale Rehearsal Readiness)

- Owner approved the recommended 1/2/3 path and authorized bounded testnet.
- Kept `dev` as the current unpushed integration candidate; no remote push was
  performed.
- Added `docs/ops/plc-phase5-small-scale-rehearsal-design.md` and updated the
  PLC ladder/task board to show Phase 5A as the next non-real-live readiness
  step after Phase 4.
- Implemented first Phase 5A gates:
  - account-risk now prefers account-scope position fetches and can block a new
    entry because another symbol has critical liquidation distance;
  - account-risk computes total account exposure and blocks if exposure exceeds
    the configured balance multiple;
  - campaign state service exposes runtime-event transitions for
    `entry_filled`, `profit_protect_triggered`, `stop_loss_filled`,
    `position_closed`, and `risk_critical`;
  - Strategy Contract promotion gate accepts only reviewed paper-observation
    packets into the next non-order gate and preserves
    `promotion_review_no_order_authority`.
- Verification:
  - compileall passed for touched application/test modules;
  - new/local gate tests passed with 16 tests;
  - Phase 4/ARCH regression target passed with 95 tests;
  - PLC promotion/schema target passed with 28 tests.
- Bounded Binance testnet smoke passed:
  - controlled ENTRY succeeded: `intent_99fdcaa96287`,
    `sig_3d42cc1b8bf0`, amount `0.01`, notional `21.1324`;
  - mid-smoke runtime positions count was `1`;
  - controlled close returned `FILLED` with
    `exit_controlled_48409f3fc46a`, exchange order `8728597319`, and
    terminalized protection orders `3`;
  - final runtime positions `0`;
  - final local active orders `0`;
  - GKS restored active, campaign state restored `observe`, startup guard
    blocked/reset;
  - runtime exited naturally, port `8001` released, and no non-daemon thread
    warning appeared;
  - no `PROTECTION_ORPHAN_REDUCE_ONLY_ORDER` or `PROTECTION_MISSING_STOP_LOSS`
    block appeared in the smoke log.
- No real-live trading, real-funds operation, runtime profile change,
  credential change, strategy-parameter change, transfer, or withdrawal was
  performed.
- Current verdict:
  `phase5a_first_gates_smoked_on_testnet / real_live_not_authorized / repeated_rehearsal_still_separate_gate`.

## 2026-05-25 (PLC Phase 5B Repeated Testnet Rehearsal)

- Owner authorized Phase 5B.
- Added `docs/ops/plc-phase5b-repeated-testnet-rehearsal.md`.
- Started Phase 5B with a bounded scope:
  - repeated controlled Binance testnet cycles;
  - symbol-isolation hardening before any multi-symbol runtime discussion;
  - explicit continued block on real live and multi-symbol runtime.
- Implemented first symbol-isolation hardening:
  - `ExchangeGateway` keeps symbol-specific order-watch running state while
    preserving the legacy global shutdown flag for compatibility;
  - recent order-update evidence is now indexed by symbol before order
    confirmation, reducing same-id cross-symbol contamination risk;
  - added `runtime_symbol_isolation_audit` as a pure audit snapshot that marks
    order-watch/cache checks as pass, reconciliation/read-model checks as
    review, and multi-symbol runtime as blocked.
- Local verification:
  - compileall passed for touched exchange/audit/test modules;
  - symbol-isolation/order-watch/STOP_MARKET-adjacent tests passed with
    18 tests.
- Integration verification:
  - Phase 4/ARCH/PLC/Phase 5B target regression passed with 107 tests;
  - `git diff --check` passed.
- Repeated Binance testnet rehearsal passed:
  - Cycle 1 controlled ENTRY `intent_3c08be13f081`,
    `sig_0a7446591611`, amount `0.01`, notional `21.1515`;
  - Cycle 1 controlled close `FILLED`, `exit_controlled_67c1002181d4`,
    exchange order `8728615333`, terminalized protection orders `3`;
  - Cycle 2 controlled ENTRY `intent_a931c7dbf03b`,
    `sig_226d23b1c6d1`, amount `0.01`, notional `21.1607`;
  - Cycle 2 controlled close `FILLED`, `exit_controlled_7e1641a544ef`,
    exchange order `8728616546`, terminalized protection orders `3`;
  - both cycles started with pre positions `0`, observed mid positions `1`,
    ended with final positions `0` and final active local orders `0`;
  - both cycles restored GKS active, campaign state `observe`, and startup
    guard blocked/reset;
  - both cycles exited naturally, released port `8001`, and logged no
    non-daemon thread warning, missing-stop block, or orphan protection block.
- No real-live trading, real-funds operation, runtime profile change,
  credential change, strategy-parameter change, transfer, withdrawal, or
  multi-symbol runtime action was performed.
- Current verdict:
  `phase5b_repeated_testnet_passed / multi_symbol_runtime_blocked / real_live_not_authorized`.

## 2026-05-25 (PLC Phase 5C Two-Symbol Synthetic Fixture Proof)

- Continued from Phase 5B without changing runtime profile, credentials,
  strategy parameters, or real-live permissions.
- Added `docs/ops/plc-phase5c-two-symbol-synthetic-fixture-proof.md`.
- Implemented local BTC/ETH synthetic fixture proof:
  - reconciliation `build_read_model(ETH)` excludes BTC mismatches;
  - runtime orders read model filters by symbol;
  - runtime execution-intents read model now accepts a symbol filter;
  - runtime positions read model and `/api/runtime/positions` now accept a
    symbol filter;
  - `/api/runtime/execution/intents` now accepts a symbol filter;
  - portfolio remains account-level aggregation and includes both BTC and ETH.
- Updated `runtime_symbol_isolation_audit` with a Phase 5C verdict:
  `two_symbol_synthetic_fixture_passed / multi_symbol_runtime_still_blocked`.
- Verification:
  - compileall passed for touched read-model/API/audit/test modules;
  - local Phase 5B/5C symbol-isolation tests passed with 8 tests.
- No Binance testnet action was performed for Phase 5C because the task is a
  local synthetic proof. No real-live trading, real-funds operation, runtime
  profile change, credential change, transfer, withdrawal, or multi-symbol
  runtime action was performed.
- Current verdict:
  `phase5c_two_symbol_synthetic_fixture_passed / multi_symbol_runtime_still_blocked / real_live_not_authorized`.

## 2026-05-25 (PLC Phase 5D Two-Symbol Exchange Read-Only Rehearsal)

- Owner authorized the next step after Phase 5C.
- Added `docs/ops/plc-phase5d-two-symbol-exchange-readonly-rehearsal.md`.
- Added `src/application/two_symbol_exchange_rehearsal.py`:
  - read-only BTC/ETH ticker, positions, normal open orders, and conditional
    open-order probes;
  - explicit `exchange_connected_read_only_no_order_authority`;
  - fails if any symbol has nonzero position, normal open orders, or
    conditional open orders.
- Added tests for pass/fail read-only rehearsal behavior.
- Used the official Binance plugin for public USDS futures book ticker:
  `ETHUSDT` and `BTCUSDT` both returned bid/ask data.
- Initial project Binance testnet read-only rehearsal:
  - ETH position `0`, normal open orders `0`, conditional open orders `0`;
  - BTC position `0`, normal open orders `0`, conditional open orders `6`;
  - verdict `phase5d_two_symbol_exchange_readonly_needs_cleanup`.
- Bounded BTC testnet cleanup:
  - verified BTC position `0` and normal open orders `0`;
  - verified all 6 BTC conditional orders were reduce-only;
  - canceled exchange orders `1000000047775774`, `1000000047775957`,
    `1000000047779744`, `1000000047779975`, `1000000048741712`,
    `1000000048741904`;
  - final BTC position `0`, normal open orders `0`, conditional open orders
    `0`.
- Final project Binance testnet read-only rehearsal passed:
  - ETH ticker visible, position `0`, normal open orders `0`, conditional open
    orders `0`;
  - BTC ticker visible, position `0`, normal open orders `0`, conditional open
    orders `0`;
  - verdict `phase5d_two_symbol_exchange_readonly_passed`.
- Local verification:
  - Phase 5B/C/D local tests passed with 10 tests;
  - compileall and `git diff --check` passed before the final integration
    target.
- No real-live trading, real-funds operation, runtime profile change,
  credential change, strategy-parameter change, transfer, withdrawal, or
  multi-symbol runtime action was performed.
- Current verdict:
  `phase5d_two_symbol_exchange_readonly_passed / multi_symbol_runtime_still_blocked / real_live_not_authorized`.

## 2026-05-25 (PLC Phase 5E Design Start)

- Added `docs/ops/plc-phase5e-controlled-multi-symbol-testnet-runtime-rehearsal.md`
  as a design/Owner-review package only.
- Proposed a new readonly testnet runtime profile
  `phase5e_btc_eth_testnet_runtime`; `sim1_eth_runtime` must remain unchanged.
- Identified current blockers: runtime market scope is still single-symbol and
  controlled endpoints are hard-coded to ETH plus `sim1_eth_runtime`.
- Recommended first 5E rehearsal shape: one runtime process, BTC/ETH market
  scope, sequential ETH then BTC controlled testnet exposure, no simultaneous
  BTC+ETH position, and no portfolio/router expansion.
- Set proposed caps: ETH `0.01 ETH` / `25 USDT`, BTC exchange-minimum viable
  quantity with `130 USDT` ceiling, combined open exposure cap `130 USDT`
  because only one symbol may be open at a time, and max `5` order submissions
  per symbol.
- Recorded stop conditions and rollback path covering profile/config rollback,
  GKS/startup/campaign restoration, runtime shutdown, final BTC/ETH flat and
  open-orders `0`, and Owner-gated direct testnet cleanup only if runtime close
  fails.
- No implementation, profile/config mutation, runtime start, Binance testnet
  order, cleanup, cancellation, credential change, or real live action was
  executed.

## 2026-05-25 (PLC Phase 5E Implementation And Bounded Testnet)

- Owner authorized continuing PLC and bounded Phase 5E testnet.
- Implemented minimal multi-symbol runtime profile support:
  - optional `symbols` in `MarketRuntimeConfig`, defaulting to
    `[primary_symbol]` for legacy profiles;
  - validation that `primary_symbol` is included and symbols are unique;
  - subscribed pairs now cover every symbol/timeframe pair.
- Added dry-run-by-default `scripts/seed_phase5e_profile.py` and seeded
  readonly inactive profile `phase5e_btc_eth_testnet_runtime`.
- Added Phase 5E server-controlled ETH/BTC endpoints under
  `/api/runtime/test/phase5e/{eth|btc}/...`; legacy `sim1_eth_runtime`
  controlled endpoints remain intact.
- Local verification before runtime:
  - Phase 5E config/endpoint tests passed with 11 tests;
  - affected controlled endpoint / Phase 5C / Phase 5D / account-risk
    regression passed with 42 tests;
  - compileall and `git diff --check` passed.
- Read-only Binance testnet preflight passed: ETH/BTC positions `0`, normal
  open orders `0`, conditional open orders `0`.
- Runtime startup:
  - wrapper launch was required because `src.main` loads `.env.local` with
    override; direct shell `RUNTIME_PROFILE=...` was overwritten by
    `.env.local`;
  - 5E runtime resolved profile version `2`, hash `8c0f633708379804`;
  - BTC/ETH warmup loaded `4/4` pairs;
  - order-watch started for both symbols;
  - startup reconciliation candidates/failures were `0`.
- ETH leg passed:
  - controlled entry `intent_fca06be68891`, signal `sig_39cb35ab8b3e`,
    amount `0.01`, notional `21.1736`;
  - controlled close `exit_controlled_18ff201e1ec3`, exchange order
    `8728698638`, average execution price `2117.18`;
  - runtime terminalized 3 protection orders and daily risk stats trade count
    advanced from `7` to `8`.
- BTC leg was blocked before order placement:
  - fixed `0.001 BTC` notional was `77.5506`, below min_notional default
    `100`;
  - cap was not raised and no BTC order or position was opened.
- Final cleanup:
  - GKS active;
  - startup guard blocked;
  - campaign state `observe`;
  - direct Binance testnet read-only final state flat/no-open-orders for ETH
    and BTC;
  - PG active positions `[]`, PG ETH/BTC open orders `[]`;
  - runtime stopped naturally and port `8001` released.
- Observation: `/api/runtime/positions` briefly showed stale ETH exposure after
  close because account snapshot cache had not refreshed; direct exchange
  inventory and PG repositories were flat.
- Current verdict:
  `phase5e_eth_leg_passed / phase5e_btc_leg_blocked_by_min_notional_without_order / final_exchange_flat / real_live_not_authorized`.

## 2026-05-25 (PLC Phase 5E Feasibility Preflight Hardening)

- Continued PLC after Phase 5E without starting runtime or executing another
  testnet order.
- Added pure `src/application/phase5e_rehearsal_feasibility.py` for
  fixed-symbol cap/min-notional assessment.
- Added read-only API endpoint:
  `GET /api/runtime/test/phase5e/{eth|btc}/feasibility`.
- Changed Phase 5E controlled entry to reuse the same feasibility result before
  constructing the signal/order path.
- The endpoint can report the observed BTC blocker as
  `NOTIONAL_BELOW_MIN_NOTIONAL` before opening a GKS/startup/campaign entry
  window.
- Verification:
  - compileall passed for the new feasibility module and touched API/tests;
  - targeted tests passed with 43 tests;
  - `git diff --check` passed.
- No runtime start, exchange call, testnet order, profile cap increase, real
  live action, commit, or push was performed.

## 2026-05-25 (PLC Phase 5E Exchange MinNotional Metadata)

- Continued Phase 5E hardening without starting runtime or making exchange
  calls.
- Added `ExchangeGateway.get_min_notional(symbol)` as a synchronous read of
  already-loaded market metadata.
- The method reads `limits.cost.min` first, then Binance `MIN_NOTIONAL` /
  `NOTIONAL` filter values from market `info.filters`.
- Phase 5E feasibility now gets exchange metadata when available and falls back
  to conservative defaults only when metadata is unavailable.
- Verification:
  - compileall passed for touched exchange/test files;
  - targeted tests passed with 23 tests;
  - `git diff --check` passed.
- No runtime start, testnet order, cap increase, real live action, commit, or
  push was performed.

## 2026-05-25 (PLC Phase 5E BTC Blocker Decision Evidence)

- Continued Phase 5E BTC blocker handling without starting runtime or making
  exchange calls.
- Added next-viable BTC decision evidence to the pure feasibility model and
  read-only Phase 5E feasibility endpoint:
  - `next_viable_amount`;
  - `next_viable_notional`;
  - `cap_shortfall`.
- The Phase 5E BTC spec now supplies the controlled exchange-step assumption
  `amount_step=0.001` for decision evidence. It still keeps fixed order amount
  `0.001 BTC` and max notional `130 USDT`.
- For the observed blocked price `77550.6`, feasibility reports next viable
  amount `0.002 BTC`, estimated notional `155.1012 USDT`, and cap shortfall
  `25.1012 USDT`.
- This does not increase BTC cap, change live/runtime profile defaults, resize
  an order, start runtime, place a testnet order, or authorize real live.
- Verification:
  - `pytest -q tests/unit/test_phase5e_rehearsal_feasibility.py tests/unit/test_phase5e_controlled_multi_symbol_endpoints.py`
    passed with 14 tests.
  - broader Phase 5E/tiny controlled-close/Phase 5C/Phase 5D/account-risk
    targeted regression passed with 70 tests.
  - compileall and `git diff --check` passed for touched files.

## 2026-05-25 (PLC Phase 5E BTC Testnet Retry Authorization)

- Owner approved Binance testnet operations without the prior minimum-capital
  limitation.
- Interpreted scope: testnet-only permission to raise Phase 5E BTC controlled
  amount/cap enough to satisfy Binance testnet min-notional. This does not
  authorize real live, mainnet, real funds, withdrawal, transfer, or generic
  strategy sizing changes.
- Updated Phase 5E BTC controlled spec:
  - amount `0.002 BTC`;
  - max controlled notional `250 USDT`;
  - amount step remains `0.001 BTC`;
  - sequential one-symbol exposure remains required.
- Next action: run local verification, then one bounded BTC testnet retry with
  preflight, feasibility, controlled entry, runtime-managed close, final
  exchange/PG flatness checks, and restored controls.

## 2026-05-25 (PLC Phase 5E BTC Testnet Retry Passed)

- Local verification before retry:
  - compileall passed for touched runtime/config/API/readmodel/test files;
  - targeted Phase 5E/Phase 5C/Phase 5D/tiny/account-risk regression passed
    with 70 tests;
  - `git diff --check` passed.
- Read-only direct Binance testnet preflight:
  - ETH position `0`, normal open orders `0`, conditional open orders `0`;
  - BTC position `0`, normal open orders `0`, conditional open orders `0`;
  - BTC ticker `77403.4`, min_notional `50.0`.
- Started one runtime process on port `8001` with
  `RUNTIME_PROFILE=phase5e_btc_eth_testnet_runtime`, `EXCHANGE_TESTNET=true`,
  `RUNTIME_CONTROL_API_ENABLED=true`, and
  `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=true`.
- Runtime resolved profile version `2`, hash `8c0f633708379804`, and safe
  summary showed ETH/BTC symbols with testnet mode.
- BTC feasibility before entry:
  - amount `0.002`;
  - price `77392.5`;
  - notional `154.7850`;
  - min_notional `50.0`, source `get_min_notional`;
  - max_notional `250`;
  - reason `OK`.
- Controls for entry window:
  - startup guard armed;
  - GKS disabled only for the bounded entry window;
  - campaign state set to `armed`.
- Controlled BTC entry succeeded:
  - intent `intent_ed2c999769bd`;
  - signal `sig_929aabc7d2ce`;
  - amount `0.002`;
  - entry price `77391.8`;
  - notional `154.7836`;
  - status `completed`.
- After entry, BTC active exposure was `0.002` with three reduce-only
  protection orders (`TP1`, `TP2`, `SL`).
- Controlled BTC runtime close succeeded:
  - close order `exit_controlled_657fa92707ee`;
  - exchange order `13192655923`;
  - amount `0.002`;
  - average execution price `77396.67`;
  - terminalized protection orders `3`.
- Daily risk stats updated to trade_count `9` and cumulative realized PnL
  `-0.015260000000000000000`.
- Final state:
  - direct Binance testnet ETH/BTC positions `0`;
  - direct Binance testnet ETH/BTC normal open orders `0`;
  - direct Binance testnet ETH/BTC conditional open orders `0`;
  - PG active positions `[]`;
  - PG ETH/BTC open orders `[]`;
  - GKS active;
  - startup guard blocked;
  - campaign state `observe`;
  - runtime stopped via SIGTERM shutdown path and port `8001` released.
- Additional read-model fix from evidence review:
  - console order/execution-intent side mapping now handles enum directions
    such as `Direction.LONG`, avoiding a false `SELL` display fallback.
- No real live, mainnet, real-funds, withdrawal, transfer, commit, or push was
  performed.

## 2026-05-25 (PLC Phase 5E Positions Snapshot Freshness Hardening)

- Continued PLC after Phase 5E without starting runtime or making exchange
  calls.
- Hardened `/api/runtime/positions` read-model behavior after the Phase 5E
  stale snapshot observation.
- New behavior: when `position_repo.list_active(...)` succeeds, PG active
  positions are the source of truth for whether a position exists; account
  snapshot rows only enrich those active PG rows with mark price/PnL/leverage.
- This prevents a stale account snapshot from showing a snapshot-only position
  after runtime-managed close has already made PG active positions flat.
- Added regression coverage in the Phase 5C two-symbol read-model fixture.
- No runtime start, exchange call, testnet order, cap increase, real live
  action, commit, or push was performed.

## 2026-05-25 (PLC Daily Risk Scope Decision Lock)

- Continued PLC after Phase 5E without starting runtime or making exchange
  calls.
- Decision: daily risk stats remain account-level with fixed
  `scope_key="runtime:default"` across runtime profiles.
- Rationale: daily loss and daily trade count are account risk controls; making
  them profile-scoped or session-scoped would let repeated profiles bypass the
  account-level day budget.
- Phase rehearsal order/session isolation should remain in dedicated controls:
  endpoint once guards, fixed exposure caps, order-count caps, GKS/startup
  guard/campaign state, and explicit Owner authorization.
- Added `resolve_daily_risk_stats_scope_key(profile_name=...)` as a small code
  policy point and wired runtime startup through it.
- Added regression coverage proving `sim1_eth_runtime` and
  `phase5e_btc_eth_testnet_runtime` resolve to the same account-level scope.
- No runtime start, exchange call, testnet order, cap increase, real live
  action, commit, or push was performed.

## 2026-05-25 (PLC Phase 5E Inventory Preflight Read Model)

- Continued PLC after Phase 5E without starting runtime or making exchange
  calls.
- Added read-only Phase 5E inventory endpoint:
  `GET /api/runtime/test/phase5e/inventory`.
- The endpoint requires the Phase 5E runtime scope and testnet mode, then
  reports per-symbol counts for:
  - exchange nonzero positions;
  - exchange normal open orders;
  - exchange conditional open orders;
  - PG active positions;
  - PG open orders.
- The response includes per-symbol `flat` and account-level `all_flat`.
- This standardizes future preflight/final flatness evidence and remains
  read-only: no order placement, close, cancel, resize, or cleanup mutation.
- Verification:
  - `pytest -q tests/unit/test_phase5e_controlled_multi_symbol_endpoints.py`
    passed with 11 tests.
- No runtime start, exchange call, testnet order, cap increase, real live
  action, commit, or push was performed.

## 2026-05-25 (PLC Long-Term Capability Roadmap)

- Continued PLC in planning mode after Phase 5E without starting runtime or
  making exchange calls.
- Added `docs/ops/plc-long-term-capability-roadmap-v1.md` as the long-term
  capability roadmap for the Owner goal:
  `controlled testnet tool -> reliable personal strategy execution platform`.
- The roadmap separates the next durable capability tracks:
  - campaign risk state machine;
  - account-level risk state machine;
  - multi-symbol runtime foundation;
  - Strategy Contract promotion pipeline;
  - runtime evidence, stop, and rollback packet.
- Planning verdict: the next recommended task is local
  `PLC-STATE-001 - Campaign Risk State Machine transition table and replay
  proof` before more exchange-connected rehearsal.
- No runtime profile default, strategy parameter, order sizing, exchange call,
  testnet action, real live action, commit, or push was performed.

## 2026-05-25 (PLC-STATE-001 Campaign Transition Table And Replay Proof)

- Continued PLC after Phase 5E under Owner testnet authorization, but this task
  stayed local because the requested core capability does not require another
  exchange-connected rehearsal.
- Implemented table-driven campaign state transitions in
  `src/application/campaign_state_service.py`:
  - explicit `CampaignTransitionTrigger` values for Owner control, entry fill,
    profit-protect, stop-loss, position close, and risk-critical events;
  - `CampaignTransitionRule` rows with owner-review, flat-proof, and
    risk-reducing-close flags;
  - `CampaignTransitionRecord` audit records with sequence number, previous
    state, target/next state, trigger, reason, updated_by, strategy/session
    ids, and context metadata such as symbol/profile/position/signal/order;
  - `replay_campaign_transitions(...)` for deterministic local replay proof.
- Hardened runtime event semantics: `entry_filled` can confirm an already
  `armed` campaign, but cannot arm a campaign from `observe`; Owner arm remains
  the only table path from `observe` to `armed`.
- Added targeted unit coverage in `tests/unit/test_p4_campaign_state_service.py`
  for transition-table contents, accepted replay, rejected replay stop,
  invalid observe-entry runtime arming, and service audit metadata.
- Verification:
  - `pytest -q tests/unit/test_p4_campaign_state_service.py` passed with 11
    tests.
- No runtime start, exchange call, testnet order, migration, runtime profile
  default change, strategy parameter change, real live action, commit, or push
  was performed.

## 2026-05-25 (PLC-STATE-002/003/004 Durable Ledger, Runtime Wiring, Replay Evidence)

- Continued from PLC-STATE-001 to complete the next campaign state-machine
  capabilities.
- PLC-STATE-002:
  - added migration `011_create_runtime_campaign_state_transitions`;
  - added PG ORM/repository support for `runtime_campaign_state_transitions`;
  - successful state transitions now update snapshot and append ledger in one
    repository transaction when using PG;
  - rejected transitions are also appended to the ledger;
  - `CampaignStateService.build_replay_evidence()` replays the ledger and
    verifies replay final state against the durable snapshot.
- PLC-STATE-003:
  - wired `ExecutionOrchestrator` entry-fill callback to `entry_filled`;
  - wired TP fill/progress to `profit_protect_triggered`;
  - wired SL fill/progress to `stop_loss_filled`;
  - wired closed position projection to `position_closed`;
  - campaign event write failures are logged without blocking protection mount
    or risk-reducing close flow.
- PLC-STATE-004:
  - added read-only internal evidence endpoint
    `GET /api/runtime/control/campaign-state/replay-evidence`;
  - response reports replay final state, snapshot match, transition counts,
    rejected transition count, and transition records;
  - future bounded testnet rehearsals can collect this packet as audit
    evidence.
- Verification:
  - compileall passed for touched campaign/orchestrator/repository/API/test
    files;
  - `pytest -q tests/unit/test_p4_campaign_state_service.py
    tests/unit/test_plc_state_runtime_event_wiring.py
    tests/unit/test_gks_v0_global_kill_switch.py -k 'campaign_state or
    plc_state or runtime_event_wiring or CampaignState'` passed with 20
    selected tests.
  - `pytest -q tests/unit/test_tiny001d4_controlled_close.py
    tests/unit/test_phase5e_controlled_multi_symbol_endpoints.py
    tests/unit/test_phase5c_two_symbol_fixture.py` passed with 20 tests.
  - `alembic heads` reported `011 (head)`.
  - `git diff --check` passed.
- No runtime start, exchange call, testnet order, migration execution against
  live PG, runtime profile change, strategy parameter change, or real live
  action was performed.

## 2026-05-25 (Playbook Governance R0 Planning Alignment)

- Owner accepted the PLC roadmap review conclusion with amendments:
  Playbook Governance R0 should be inserted before Human Arm Gate and Strategy
  Contract/runtime work.
- Added ADR-0011:
  `docs/adr/0011-playbook-governance-before-strategy-contract.md`.
- Added R0 planning artifact:
  `docs/ops/playbook-governance-r0-plan.md`.
- Updated PLC SSOT docs so the current chain is now:
  `Mode Router -> Playbook Governance -> Human Arm Gate -> Strategy Contract`.
- Accepted R0 as paper-only/docs-governance only:
  playbook registry, switch decision log, switching gate rules, cooldown/review
  governance, CPV0_2 continuity, and dry-run review.
- Standardized the initial playbook catalog:
  - `PB-000-OBSERVE-ONLY` as default safe state;
  - `PB-001-DIRECTION-A-PAPER` as pause-fragile observe-only;
  - `PB-002-SQ02-DOWNSIDE-PAPER` as docs-only skeleton;
  - `PB-003-MANUAL-DISCRETIONARY` as highest-risk governed manual posture.
- Standardized the default switching constraints:
  loss cluster 48h hard-lock plus 24h override delay, profit-response risk
  increase 7-day hold plus review, 14-day minimum playbook hold, and max 3
  switches per rolling 90 days for narrative chasing.
- Deferred execution-oriented work: Tracks B-E runtime implementation,
  Phase 5H-8 runtime work, Strategy Contract v2 implementation,
  LifecycleStrategy/ExitMonitor runtime, and further paper/testnet runtime.
- No runtime start, exchange call, order path, strategy implementation, testnet
  action, real live action, commit, or push was performed.

## 2026-05-26 (BRC-R4 API Surface Cleanup + Local Operator Console)

- Implemented BRC-R4 as the current local operation-governance console slice.
- Backend:
  - slimmed `src/interfaces/api.py` into a BRC-first FastAPI app assembly;
  - added single-Owner operator auth with username, PBKDF2 password hash,
    Google Authenticator-compatible TOTP, and signed HttpOnly session cookie;
  - added helper script `scripts/brc_auth_setup.py`;
  - mounted only auth, BRC, operator, LLM workflow, runtime safety, and
    dev/testnet BRC routers in the main API app;
  - legacy research/config/runtime routes are no longer mounted by the main
    control-console API.
- Frontend:
  - rebuilt `gemimi-web-front` as `BRC Operator Console`;
  - kept the compact workbench visual style;
  - removed legacy runtime/research/config pages and unused dependencies;
  - added login, dashboard, operator, workflow, review, ledger, and runtime
    safety pages;
  - added human-readable chain explanations, blocked-state reasons, stage/next
    step/global planning panels, and expandable JSON/evidence details.
- Boundaries preserved:
  - no user table;
  - no real live/mainnet;
  - no withdrawal/transfer;
  - no automatic strategy execution;
  - no automatic sizing/leverage/side override;
  - no strategy pool implementation;
  - no testnet order was executed by this implementation update.
- Verification completed:
  - targeted backend auth/API/runtime-context tests passed;
  - frontend `npm run lint` passed;
  - frontend `npm run build` passed.

## 2026-05-26 (BRC-R4.1 Delivery Owner Guide)

- Upgraded the local console from engineering status pages toward a
  delivery-grade Owner operation guide.
- Added readonly `GET /api/brc/readiness` as the product-state translation
  layer. It summarizes current conclusion, reasons, account impact, next step,
  available actions, disabled actions, latest campaign, review summary,
  runtime summary, and developer details without mutating campaign/runtime/
  exchange state.
- Changed the frontend default route from dashboard to `/guide`. The Guide
  page is now the primary Owner story entry: current conclusion, why, account
  impact, next step, action cards, latest campaign/review summaries, and
  folded developer detail.
- Productized existing pages around readiness:
  - Runtime Safety translates Runtime/GKS/Startup Guard/Profile into Owner
    language and shows the overall conclusion.
  - Operator Plan disables plan creation when readiness says BRC read actions
    are unavailable and shows a confirmation card before read-only execution.
  - Workflow distinguishes read-only, controlled testnet, and forbidden
    intent; testnet confirmation is disabled until all readiness gates pass.
  - Review auto-binds the latest campaign and no longer asks Owner to hand-type
    Campaign ID by default.
  - Ledger shows operation summaries first and keeps JSON under developer
    detail.
- Boundaries preserved: no new order path, no new testnet authority, no real
  live/mainnet, no withdrawal/transfer, no automatic strategy execution, no
  automatic sizing/leverage/side override, and no strategy-pool execution.
- Verification completed:
  - `python3 -m py_compile src/interfaces/api_brc_console.py src/interfaces/api_runtime_safety.py`
  - `pytest -q tests/unit/test_brc_console_api_surface.py` -> 6 passed
  - `pytest -q tests/unit/test_brc_controlled_testnet_endpoints.py` -> 8 passed
  - `npm run lint`
  - `npm run build`
  - `git diff --check`

## 2026-05-26 (BRC Local Testnet Acceptance Defaults)

- Updated local-only acceptance defaults so BRC testnet rehearsal no longer
  requires manual env toggling before Owner UI验收.
- `.env.local` is configured locally with:
  - `EXCHANGE_TESTNET=true`
  - `RUNTIME_PROFILE=brc_btc_eth_testnet_runtime`
  - `RUNTIME_CONTROL_API_ENABLED=true`
  - `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=true`
  - corrected `BRC_LLM_TIMEOUT_SECONDS`
- Added `scripts/start_brc_local_testnet.sh` as the local acceptance launcher.
  It sources `.env` and `.env.local`, forces the BRC testnet acceptance
  defaults, seeds the BRC runtime profile, starts `src/main.py`, and starts the
  Vite console with `VITE_API_BASE_URL` pointed at the local backend.
- Updated `.env.local.example` to show BRC testnet as the local acceptance
  profile by default.
- Boundary: this is local/dev convenience only. Production/cloud deployment
  must explicitly reset mutation gates and reintroduce stricter approval,
  replay, secret, and deployment controls. No real live/mainnet, withdrawal,
  transfer, automatic strategy execution, automatic sizing, or strategy-pool
  execution is authorized by this default.

## 2026-05-26 (BRC Testnet-First / Production-Blocked Alignment)

- Owner clarified that the BRC system should not be constrained to paper-only
  operation at the current stage. The current executable validation path should
  be the fixed Binance testnet rehearsal, while stricter gating should block
  production/live/mainnet, withdrawal/transfer, autonomous strategy execution,
  automatic sizing/leverage/side override, and strategy-pool execution.
- Added `docs/ops/brc-testnet-first-production-blocked-principle.md`.
- Updated ADR-0012, project roadmap, task board, and BRC R0/R1 plan to use the
  unified operating posture:
  `testnet-first for local acceptance; production-blocked by explicit env gates`.
- Implementation implication recorded for the next cleanup: readiness and
  workflow gates should stop presenting testnet as a suspicious or unavailable
  path when local acceptance defaults are active. They should instead verify
  testnet/profile/caps/flatness/Owner-confirmation and reserve fail-closed
  behavior for production authority.
- No code, env, runtime profile, exchange call, testnet order, real-live action,
  withdrawal/transfer path, strategy execution, or commit/push was performed by
  this documentation alignment.

## 2026-05-26 (BRC-R5 Owner-Driven Runtime Control + Strategy Family Baseline)

- Consolidated the Owner-confirmed BRC-R5 design principles into
  `docs/ops/brc-r5-owner-driven-runtime-control-design.md`.
- Confirmed operating model:
  - single `TRADING_ENV=simulation|live` switch;
  - no paper mainline;
  - v0 Owner-facing runtime states:
    `observe`, `monitor`, `testnet_rehearsal`, `paused`, `stopped`,
    `flattening`, `attention_required`;
  - bare `trade` is reserved out of v0; future live readiness may introduce
    `live_trade` after separate Owner production authorization;
  - `live` is modeled as a disabled environment boundary in v0, not as a switch;
  - testnet/simulation should be open enough to expose engineering problems,
    with hard gates limited to non-production proof, audit availability,
    cut-off availability, and final state observability;
  - live is modeled now but default-off and unauthorized until a future
    Owner production/deployment task;
  - LLM is an Owner assistant, risk advisor, and audit investigator. It can
    query controlled read-only facts and provide advisory risk advice, but it
    cannot write, trade, confirm, or bypass `TRADING_ENV`;
  - action cards are weak control/explanation objects, not approval walls;
  - fast cut-off controls are first-class:
    `pause_new_entries`, `emergency_stop_runtime`, `emergency_flatten`;
  - audit write failure is a hard block for state-changing actions.
- Added `docs/ops/strategy-family-map-v0.md`.
- Strategy-family baseline:
  - the project should use multiple bounded playbook candidates wrapped by BRC,
    not chase one universal strategy;
  - `TF-001` Trend Following is the first carrier-validation playbook;
  - `CPM-1` is reclassified as Pullback Continuation / Conditional Candidate,
    not a universal failed strategy or direct runtime candidate;
  - `VB-001` is Reserve, `MTF-001` is Filter Candidate,
    Funding/OI/Event is Watchlist, and ML/HFT are Rejected for Now.
- Added task-board entries for `BRC-R5-000`, `STRAT-FAMILY-000`, and the
  recommended next slice `BRC-R5-001 Trend playbook carrier full-chain
  validation`.
- No code, env, runtime profile, exchange call, testnet order, live order,
  withdrawal/transfer path, strategy execution, or commit/push was performed.

## 2026-05-26 (BRC Owner Console v0 Design Freeze)

- Added `docs/ops/brc-owner-console-product-design-v0/` with a product-design
  README and low-fidelity SVG wireframes.
- Accepted review verdict: `APPROVE_WITH_REQUIRED_REVISIONS`.
- Froze v0 primary IA:
  `Command Center`, `LLM Copilot`, `Strategy / Playbook`, `Risk & Account`,
  and `Runtime Control`.
- Folded `Markets & Orders` / `Positions & Orders` into `Risk & Account`.
- Removed `Parameters` from the v0 primary nav; risk-envelope values remain
  readonly inside `Risk & Account`.
- Confirmed application-owned Action Card semantics:
  `authority_source=application_preflight`, fact snapshot, preflight result,
  idempotency key, expiry, allowed/blocked next states, and final-state proof.
- Confirmed implementation order: first local console v0, then later R5
  TF-001 carrier validation. Current testnet acceptance remains the fixed BRC
  ETH/BTC rehearsal, not a new TF-001 execution path.

## 2026-05-26 (BRC Owner Console v0 Implementation And Acceptance Review)

- Implemented the v0 Owner Console IA:
  `Command Center`, `LLM Copilot`, `Strategy / Playbook`, `Risk & Account`,
  and `Runtime Control`.
- Frontend default route is now `/command-center`.
  `/summary` redirects to `/command-center`;
  `/markets-orders` and `/parameters` redirect to `/risk-account`;
  `/ai-investigator` redirects to `/llm-copilot`.
- `/api/brc/readiness` now exposes the v0 SSOT fields:
  environment boundary, runtime state, risk decision, risk/account summary,
  strategy/playbook summary, application-owned action cards, global cut-off
  controls, and latest audit.
- Action Card UI is application-owned. LLM Copilot can create advisory
  workflow intent, but confirm remains separate and requires Owner phrase.
- Frontend copy was simplified toward Owner language while keeping useful
  English terms such as `testnet`, `LLM Copilot`, `Action Card`, and `live`.
  Technical IDs such as fact snapshot, preflight, and idempotency are folded
  under expandable technical data.
- Verification completed:
  - `python3 -m py_compile src/interfaces/api_brc_console.py`
  - `pytest -q tests/unit/test_brc_console_api_surface.py tests/unit/test_brc_operator_workflow.py tests/unit/test_brc_controlled_testnet_endpoints.py` -> 25 passed
  - `npm run lint`
  - `npm run build`
  - Browser smoke passed for all five P0 pages.
- Local testnet startup succeeded with:
  `BRC_BACKEND_PORT=8011 BRC_FRONTEND_PORT=3011 scripts/start_brc_local_testnet.sh`.
  Runtime reached `SYSTEM READY` on profile `brc_btc_eth_testnet_runtime`.
- New fixed testnet rehearsal rerun was intentionally stopped by the campaign
  gate after Owner confirmation phrase:
  workflow `brc-wf-5b07c9a504a8` failed with
  `active BRC campaign already exists: brc-267d6efee3b0`.
  This run kept `mutation_executed=false`, `withdrawal_executed=false`, and
  `live_ready=false`.
- This blocker was superseded by the follow-up cleanup and rerun recorded below.
- Prior full-chain evidence remains available:
  workflow `brc-wf-8e3155486b24`, campaign `brc-4e83f98ccb4a`,
  ETH entry/close, BTC entry/close, mock profit/loss-lock, finalize, review
  `brc-review-dff0efa77cf0`, `withdrawal_executed=false`, `live_ready=false`.
- Added `docs/ops/brc-owner-console-v0-acceptance-review.md`.
- No real live/mainnet, withdrawal/transfer, strategy-pool execution, or
  automatic sizing/leverage authority was added.

## 2026-05-26 (BRC Owner Console v0 Testnet Rerun Follow-up)

- Owner authorized resolving the stale active campaign and rerunning the fixed
  ETH/BTC Binance testnet rehearsal.
- Cleaned stale campaigns only through testnet finalize/review APIs; no direct
  database override was used.
- Fixed the LLM testnet workflow failure path:
  - entry responses with `attempt_locked=false` now stop the workflow before
    close;
  - stale runtime gates are closed only with `all_flat=true` proof;
  - entry-not-locked attempts are marked `blocked` before manual-stop finalize;
  - ended campaign invariant now checks that no active attempt remains.
- Verification:
  - `python3 -m py_compile src/interfaces/api_console_runtime.py src/application/bounded_risk_campaign_service.py`
  - `pytest -q tests/unit/test_brc_controlled_testnet_endpoints.py` -> 10 passed
- Rerun result:
  - workflow `brc-wf-59ad10e73dd7`;
  - campaign `brc-9167363bf771`;
  - stopped at ETH entry because Binance testnet returned `-1007` timeout with
    execution status unknown;
  - campaign ended as `ended_manual_stop`;
  - ETH attempt marked `blocked`;
  - final inventory `all_flat=true`;
  - review `brc-review-970ba0da4197` recorded as `needs_followup`;
  - `withdrawal_executed=false`, `live_ready=false`.
- Current acceptance status:
  `APPROVE_UI_AND_API_WITH_TESTNET_BLOCKER_RECORDED`.

## 2026-05-27 (BRC-R5-001A/B/C Evidence Hardening)

- Implemented `BRC-R5-001A` as a bounded Owner Console smoke evidence mode:
  `python3 scripts/brc_owner_console_smoke.py --mode runtime-bound-evidence --output /tmp/brc-owner-console-evidence.json`.
- The evidence mode stays in a bounded runtime-bound service context and covers
  capabilities, account facts evidence summary, `switch_playbook`
  preflight/confirm refs, operation get/list, emergency stop runtime envelope,
  and emergency flatten dry-run record only.
- Implemented `BRC-R5-001B` as
  `docs/ops/brc-r5-001-tf001-carrier-full-chain-validation-plan.md`.
  TF-001 remains a carrier validation object only; it is not alpha proof,
  profitability evidence, strategy-pool construction, or live readiness.
- Implemented `BRC-R5-001C` as read-only account facts/reconciliation evidence
  hardening. `/api/brc/account/facts` now exposes evidence refs, checked
  sources, source snapshots, reconciliation timestamp, mismatch count, and
  unknown/unmanaged counts for Owner Console display and Operation preflight
  summaries.
- No live/mainnet, actual flatten, order cancel/close, withdrawal/transfer,
  arbitrary trading, strategy-pool execution, or LLM direct execution authority
  was added.

## 2026-05-27 (BRC-R5-001D TF-001 Carrier Decision Review)

- Added bounded TF-001 decision-review smoke:
  `python3 scripts/brc_owner_console_smoke.py --mode tf001-carrier-decision-review --output /tmp/brc-tf001-carrier-decision-review.json`.
- Current validation verdict:
  - `switch_playbook` to `TF-001` is blocked because `TF-001` is not yet in the
    BRC playbook allowlist;
  - `enter_strategy_or_monitor` confirms as `noop` monitor carrier and does not
    enable strategy execution;
  - the campaign playbook remains unchanged.
- This is the expected safe result for the first TF-001 validation step. A
  later implementation slice must explicitly design any TF-001 catalog entry or
  Operation semantics before `switch_playbook` can target it.
- No live/mainnet, strategy-pool, order cancel/close, actual flatten,
  withdrawal/transfer, or LLM direct execution authority was added.

## 2026-05-27 (BRC-R5-001E TF-001 Carrier Full-chain Smoke)

- Added `TF-001` to the BRC playbook catalog as
  `carrier_validation_only`. It is not controlled-testnet authority, alpha
  proof, strategy-pool construction, live readiness, withdrawal/transfer
  authority, or arbitrary trading authority.
- Added bounded full-chain smoke:
  `python3 scripts/brc_owner_console_smoke.py --mode tf001-carrier-full-chain --output /tmp/brc-tf001-carrier-full-chain.json`.
- Validation result:
  - `select_playbook=executed` through Operation-backed `switch_playbook`;
  - Owner confirmation is bound to operation/preflight/idempotency ids;
  - `monitor=noop` through `enter_strategy_or_monitor`;
  - `pause=executed` through `enter_pause`;
  - `stop=executed` through Operation-backed `emergency_stop_runtime`;
  - `review=executed` through Operation-backed `write_review_decision`;
  - operation list includes all five chain operations;
  - campaign playbook after the smoke is `TF-001`;
  - review decision count is `1`.
- The smoke output records campaign/audit/review/runtime refs and clean
  account facts evidence (`source=mixed`, `truth_level=reconciled`,
  `reconciliation_status=clean`).
- Safety result remains bounded: no live/mainnet, no strategy execution, no
  actual flatten, no order cancel, no position close, no withdrawal/transfer,
  and no LLM authorization.

## 2026-05-29 (BRC-R5-003 Broad OHLCV-only Directional Smoke)

- Owner reframed the current goal as a fast trial-and-review research system
  for small risk-capital Campaigns, not a fully automated general strategy
  system.
- The next research priority is broad coarse screening rather than deeper
  TB-001 year/regime digging or full cost/baseline/campaign machinery.
- Extended the one-off OHLCV smoke screen from 3 to 9 fixed variants:
  `TB-001`, `TB-002`, `VB-001`, `PC-001`, `PC-002`, `MR-001`, `RB-001`,
  `VI-001`, and `MI-001`.
- Ran BTC/ETH/SOL/BNB 1h local-data long/short screening and wrote:
  - `reports/directional-opportunity-broad-smoke-20260529/evidence.md`
  - `reports/directional-opportunity-broad-smoke-20260529/ranked_summary.md`
  - `reports/directional-opportunity-broad-smoke-20260529/trial_candidate_with_known_risks.md`
- Selected 3 `trial_candidate_with_known_risks` for next review:
  `MI-001 BNB long`, `MI-001 SOL long`, and `VI-001 ETH long`.
- Current evidence is historical OHLCV-only and intentionally incomplete:
  no cost/slippage/funding/liquidation modeling, no random/buy-hold baseline,
  no rolling campaign ruin-rate, and no Owner-reviewed event examples yet.
- This work did not persist to PG, create admission/campaign facts, start
  runtime, call an exchange, authorize live, or widen symbol/side/leverage
  authority.

## 2026-06-11 (Runtime Close Projection Recovery / Tokyo Deploy)

- Deployed `program/live-safe-v1` commit
  `1f801c0e06808d94d9ade80576fe8a5453bd8507` to Tokyo via the git-based
  runtime-governance deploy path:
  `brc-runtime-governance-1f801c0e-20260611T0906Z`.
- Tokyo health after deploy:
  `{"status":"ok","service":"brc_operator_console","runtime_bound":true,"live_ready":false}`.
- Applied local PG projection recovery for the already-observed AVAX runtime
  close trade only. The recovery used exchange read-only trade facts for
  trade `1386754188` and did not submit, cancel, amend, or close any exchange
  order.
- Recovered local order/position projection:
  - runtime `strategy-runtime-95655873b76c`;
  - SL order `rtod-a194d1ef363c12c3df-sl` marked `FILLED`;
  - exit price `6.635`;
  - local position `pos_signal-evaluation-adabffa08945` marked closed with
    `current_qty=0` and `realized_pnl=-0.0400`.
- Post-recovery reconciliation for `AVAX/USDT:USDT` reported
  `is_consistent=true`, `severe_count=0`, `warning_count=0`, and
  `mismatch_count=0`.
- Runtime live-position monitor for `strategy-runtime-95655873b76c` now reports
  `flat_review_required`, `active_position_present=false`,
  `attempts_used=1`, `attempts_remaining=2`, and
  `review_required_before_next_attempt=true`.
- This stage did not authorize or create a new live entry. The next runtime
  attempt should proceed only after the stopped-out first attempt is reviewed
  and the runtime profile remains inside the Owner-approved budget.

## 2026-06-11 (Runtime Closed Trade Review / Tokyo Deploy)

- Added and deployed `program/live-safe-v1` commit
  `d0bcce7c9dea5824a83cd3b3820f14896353dedb` via the git-based Tokyo deploy
  path:
  `brc-runtime-governance-d0bcce7c-20260611T0920Z`.
- Added `RuntimeClosedTradeLifecycleReviewService` plus
  `scripts/create_runtime_closed_trade_review.py` to generate a
  `brc_live_lifecycle_reviews` closed-review record from already-resolved
  runtime order / position / reconciliation facts.
- Local verification:
  - `python3 -m pytest -q tests/unit/test_runtime_closed_trade_lifecycle_review.py tests/unit/test_runtime_semantic_review_packet.py tests/unit/test_right_tail_review.py`
    passed with `11 passed`;
  - `python3 -m pytest -q tests/unit/test_brc_live_lifecycle_review_endpoints.py tests/unit/test_runtime_live_position_monitor.py tests/unit/test_runtime_execution_submit_outcome_review.py`
    passed with `34 passed`;
  - compile and `git diff --check` passed.
- Tokyo postdeploy acceptance passed and health remained:
  `{"status":"ok","service":"brc_operator_console","runtime_bound":true,"live_ready":false}`.
- Applied the closed-review writer for runtime
  `strategy-runtime-95655873b76c`, entry
  `rtod-a194d1ef363c12c3df-entry`, and SL
  `rtod-a194d1ef363c12c3df-sl`.
- Recorded review:
  - review id
    `live-review-runtime-review:strategy-runtime-95655873b76c-closed-reviewed-rtod-a194d1ef363c12c3df-sl`;
  - lifecycle/review status `closed_reviewed`;
  - strategy outcome `small_bounded_loss`;
  - realized PnL `-0.0400`;
  - max-loss budget basis `0.087764740000000000`;
  - R multiple `-0.4558`;
  - stop effectiveness `effective_bounded_loss`;
  - attempt continuation quality `continue_after_small_loss`.
- The writer is idempotent for the recorded review id. A follow-up dry-run
  returned `already_recorded`.
- Safety result:
  - exchange facts were read-only;
  - no exchange write, order create/cancel/amend, position close,
    ExecutionIntent creation, runtime-budget mutation, withdrawal, or transfer
    was performed;
  - only the live lifecycle review ledger was written.
- Known residual trace gap: the review record preserved runtime / trial /
  strategy / signal / order-candidate IDs, but `execution_intent_id` is still
  missing from this recovered local order chain, so the semantic review packet
  reports `runtime_semantic_trace_incomplete`.

## 2026-06-11 (Runtime Closed Review Next-Attempt Gate)

- Added and pushed `program/live-safe-v1` commit
  `3ba4158f6559389eb53bf1f8d1fd893242c38d26`.
- The change connects closed-trade review state to the Trading Console
  post-action / next-attempt backend gate:
  - `closed_from_pg_exit_order` with runtime live-lifecycle evidence is now
    treated as `closed_trade_review_required`;
  - only `brc_live_lifecycle_reviews.lifecycle_status=closed_reviewed` plus
    `review_status=closed_reviewed` clears the next attempt to
    `clear_for_preflight`;
  - legacy historical closed one-shot orders without runtime live-lifecycle
    review evidence remain uncoupled from the new runtime review gate.
- Safety result:
  - no order, ExecutionIntent, OrderLifecycle, exchange, withdrawal, transfer,
    or runtime-budget mutation path was added;
  - frontend state continues to be backend-owned and cannot infer submit
    permission from a filled TP/SL alone.
- Verification:
  - `python3 -m pytest -q tests/unit/test_trading_console_readmodels.py`
    passed with `48 passed`;
  - `python3 -m pytest -q tests/unit/test_budgeted_autonomy.py tests/unit/test_runtime_closed_trade_lifecycle_review.py tests/unit/test_runtime_semantic_review_packet.py tests/unit/test_right_tail_review.py`
    passed with `19 passed`;
  - compile and `git diff --check` passed.
- Deployment status: Tokyo is still deployed at
  `d0bcce7c9dea5824a83cd3b3820f14896353dedb`
  (`brc-runtime-governance-d0bcce7c-20260611T0920Z`) and health is still
  `{"status":"ok","service":"brc_operator_console","runtime_bound":true,"live_ready":false}`.
  This gate has not yet been deployed because the server is not in active
  external use and per-stage deploys are not required.

## 2026-06-11 (Strategy Signal -> Shadow Candidate Planning v1 Verified)

- Current `program/live-safe-v1` code already contains the B0 strategy signal
  planning bridge:
  `RuntimeStrategySignalEvaluationService -> StrategyEvaluationContext ->
  StrategySemanticsShadowBindingService -> shadow SignalEvaluation /
  OrderCandidate`, with optional scheduler handoff and explicit shadow-plan
  API/CLI entry points.
- Verified behavior:
  - CPM / BRF evaluator outputs must pass the B0 semantics gate before shadow
    candidate creation;
  - `READY_FOR_SEMANTIC_BINDING` is the only evaluator status that may create
    shadow records;
  - trusted runtime fact overlay can replace caller-supplied account and active
    position facts; missing trusted facts block candidate planning;
  - generated proposals include entry price, structure/ATR stop reference,
    runtime notional/leverage/loss preview, TP1 1R partial, and runner/trailing
    metadata for CPM long / BRF short style planning;
  - RMR and FCO remain non-trading / backlog semantics and do not become
    execution authority.
- Verification:
  - `python3 -m pytest -q tests/unit/test_b0_runtime_strategy_signal_planning.py tests/unit/test_runtime_strategy_signal_evaluation_service.py tests/unit/test_b0_strategy_runtime_fact_overlay.py tests/unit/test_b0_runtime_strategy_signal_scheduler_assembly.py tests/unit/test_strategy_observation_shadow_planning_rehearsal.py`
    passed with `39 passed`;
  - `python3 scripts/verify_strategy_observation_shadow_planning_rehearsal.py --json`
    returned `status=rehearsal_passed`, created one shadow SignalEvaluation and
    one shadow OrderCandidate, and reported no forbidden execution flags.
- This stage did not create ExecutionIntent records, orders, OrderLifecycle
  calls, exchange calls, withdrawal/transfer instructions, or runtime-budget
  mutations.
- Current next mainline gap: use the verified shadow planning path and reviewed
  first live attempt state to decide the next controlled runtime attempt path,
  including whether to deploy the latest gate code before the next Tokyo
  rehearsal/live attempt.

## 2026-06-11 (Tokyo Git Deploy 0e80bc5b)

- Deployed `program/live-safe-v1` commit
  `0e80bc5b345f3f4bce2c5a574a09c6f28de9aee0` to Tokyo via the git-based
  runtime-governance deploy path:
  `brc-runtime-governance-0e80bc5b-20260611T0947Z`.
- The release includes:
  - `3ba4158f6559389eb53bf1f8d1fd893242c38d26`
    (`feat(console): require closed runtime review before retry`);
  - `0e80bc5b345f3f4bce2c5a574a09c6f28de9aee0`
    (`docs(ops): record strategy shadow planning verification`).
- Deploy preflight:
  - owner deploy packet status `ready_for_owner_git_deploy_decision`;
  - git deploy plan status `ready_for_owner_authorized_remote_git_deploy_plan`;
  - executor dry-run status `dry_run_ready`;
  - first-real-submit remained blocked in the deploy packet;
  - no new migrations were required (`084 -> 084`).
- Apply result:
  - `execute_tokyo_runtime_governance_git_deploy.py --apply` completed with
    status `applied`;
  - `commands_executed=16`, `commands_planned=16`;
  - Tokyo `app/current` now points to
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-0e80bc5b-20260611T0947Z`.
- Postdeploy verification:
  - HTTP health:
    `{"status":"ok","service":"brc_operator_console","runtime_bound":true,"live_ready":false}`;
  - `scripts/verify_tokyo_runtime_governance_postdeploy.py --json` returned
    `postdeploy_acceptance_passed`;
  - `scripts/probe_tokyo_runtime_governance_readonly.py --json` returned
    `ready_for_controlled_deploy_preflight`.
- Authenticated read-only Trading Console verification for
  `AVAX/USDT:USDT` showed:
  - `review_ledger.lifecycle_status=closed_reviewed`;
  - `review_decision.status=closed_reviewed`;
  - `strategy_outcome=small_bounded_loss`;
  - `next_attempt_gate.gate=clear_for_next_preflight`;
  - `next_attempt_gate.next_attempt_allowed_by_lifecycle=true`;
  - `next_attempt_gate.action_allowed=false`;
  - `next_attempt_gate.may_execute_live=false`;
  - `review-state.right_tail_review.status=reviewed`;
  - `small_loss_count=1`, `tail_win_count=0`, and
    `max_r_multiple=-0.4558`.
- Safety result:
  - deployment did not create orders, ExecutionIntent records, OrderLifecycle
    calls, exchange orders, withdrawal/transfer instructions, or runtime
    budget mutations;
  - the console now recognizes the first live attempt as a reviewed small
    bounded loss and permits only the next preflight path, not direct trading.

## 2026-06-11 (First-real-submit Flow Next-attempt Gate)

- Added a next-attempt lifecycle/review gate check to
  `scripts/runtime_first_real_submit_api_flow.py`.
- The guarded API flow now checks Trading Console
  `/api/trading-console/owner-action-flow` before `prepare`, `arm`, or
  `execute` when a symbol is available:
  - with `--signal-input-json`, the symbol and strategy ids can be derived from
    the signal input;
  - with existing candidate / authorization ids, the operator can provide
    `--next-attempt-symbol` plus optional side / family ids;
  - if no symbol is available, the script records
    `next_attempt_gate_check_skipped_symbol_missing` as a warning and continues
    rather than inventing a new hard gate.
- If the backend-owned `next_attempt_gate.status` is not
  `clear_for_preflight`, or
  `next_attempt_allowed_by_lifecycle` is not true, the flow stops before
  creating an intent draft, submit authorization, local registration,
  exchange-submit action authorization, or first-real-submit action.
- Verification:
  - `python3 -m pytest -q tests/unit/test_runtime_first_real_submit_api_flow.py`
    passed with `7 passed`;
  - `python3 -m py_compile scripts/runtime_first_real_submit_api_flow.py`
    passed;
  - `git diff --check` passed.
- Safety result:
  - no exchange calls, orders, ExecutionIntent records, OrderLifecycle calls,
    withdrawal/transfer instructions, or runtime-budget mutations were made by
    this code change or verification;
  - the first-real-submit operator flow now carries machine-readable evidence
    that the previous bounded-live attempt was cleared for the next preflight
    before proceeding.

## 2026-06-11 (OrderCandidate Usage Guard)

- Tokyo read-only inspection found the current active AVAX runtime
  `strategy-runtime-95655873b76c` and candidate
  `order-candidate-d0c432b4d869`.
- PG read-only inspection showed that this candidate is already tied to
  `ExecutionIntent` `intent_rt_9564b635726f404b6a38c997` and submit
  authorization
  `runtime-submit-authorization-intent_rt_9564b635726f404b6a38c997`.
  Therefore it must be treated as a used first-attempt candidate, not as the
  fresh candidate for the next attempt.
- Added read-only candidate usage fields to Trading Console
  `/api/trading-console/order-candidates` and
  `/api/trading-console/order-candidates/{order_candidate_id}`:
  - `execution_intent_id`;
  - `execution_intent_status`;
  - `submit_authorization_id`;
  - `submit_authorization_status`;
  - `candidate_usage_status`;
  - `candidate_reusable_for_new_attempt`;
  - `reuse_blocker`.
- Added repository lookups by `order_candidate_id` for ExecutionIntent and
  runtime submit authorization records.
- Updated `scripts/runtime_first_real_submit_api_flow.py` so prepare / arm /
  execute from an existing `order_candidate_id` first checks candidate usage
  and blocks before intent draft creation when the candidate already has an
  ExecutionIntent or submit authorization.
- Verification:
  - `python3 -m pytest -q tests/unit/test_runtime_first_real_submit_api_flow.py tests/unit/test_order_candidate_usage_readmodel.py`
    passed with `12 passed`;
  - `python3 -m pytest -q tests/unit/test_trading_console_readmodels.py`
    passed with `48 passed`;
  - `python3 -m py_compile scripts/runtime_first_real_submit_api_flow.py src/interfaces/api_trading_console.py src/infrastructure/pg_execution_intent_repository.py src/infrastructure/pg_runtime_execution_submit_authorization_repository.py`
    passed;
  - `git diff --check` passed.
- Safety result:
  - all Tokyo checks were read-only;
  - no exchange calls, order creation, OrderLifecycle calls, ExecutionIntent
    creation, submit authorization creation, withdrawal/transfer instructions,
    or runtime-budget mutations were performed;
  - the next bounded-live attempt now requires a fresh shadow candidate instead
    of reusing the already-authorized first-attempt candidate.

## 2026-06-11 (Tokyo Deploy c2e7ac6d Candidate Usage Guard)

- Deployed `program/live-safe-v1` commit
  `c2e7ac6de0242b55c6a38dd635bbb08af063bd7f` to Tokyo via the git-based
  runtime-governance deploy path:
  `brc-runtime-governance-c2e7ac6d-20260611T1015Z`.
- This deployment includes:
  - `ad175e93` first-real-submit flow next-attempt gate;
  - `d14548a8` OrderCandidate usage guard and read-model fields;
  - `c2e7ac6d` hotfix for string-vs-enum usage status compatibility.
- Deploy evidence:
  - owner deploy packet status `ready_for_owner_git_deploy_decision`;
  - git deploy plan status `ready_for_owner_authorized_remote_git_deploy_plan`;
  - executor dry-run status `dry_run_ready`;
  - apply status `applied`, with `commands_executed=16` and
    `commands_planned=16`;
  - Tokyo `app/current` now points to
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-c2e7ac6d-20260611T1015Z`;
  - health remains
    `{"status":"ok","service":"brc_operator_console","runtime_bound":true,"live_ready":false}`;
  - postdeploy acceptance returned `postdeploy_acceptance_passed`;
  - readonly probe returned `ready_for_controlled_deploy_preflight`.
- Remote candidate usage acceptance:
  - active runtime candidate `order-candidate-d0c432b4d869` now reports
    `candidate_usage_status=submit_authorization_recorded`,
    `candidate_reusable_for_new_attempt=false`, and
    `reuse_blocker=order_candidate_already_has_submit_authorization`;
  - it is linked to `ExecutionIntent`
    `intent_rt_9564b635726f404b6a38c997` and submit authorization
    `runtime-submit-authorization-intent_rt_9564b635726f404b6a38c997`;
  - therefore the next AVAX attempt must use a fresh candidate instead of this
    first-attempt candidate.
- Safety result:
  - deploy and acceptance did not create orders, create ExecutionIntent
    records, call OrderLifecycle, call exchange, create withdrawal/transfer
    instructions, or mutate runtime budget;
  - the only remote mutation was the code deploy / service restart / Alembic
    no-op head check through the existing deployment path.

## 2026-06-11 (First-real-submit Arm Evidence Ordering Fix)

- Tokyo fresh-candidate path created the next active-runtime AVAX short shadow
  candidate:
  - runtime `strategy-runtime-95655873b76c`;
  - candidate `order-candidate-44cd97753e3e`;
  - signal evaluation `signal-evaluation-2037e48d00b3`;
  - symbol `AVAX/USDT:USDT`, side `short`, intended notional `8`.
- Prepare recorded:
  - `ExecutionIntent` `intent_rt_6ca3cecd63fafbd1d25760df`;
  - submit authorization
    `runtime-submit-authorization-intent_rt_6ca3cecd63fafbd1d25760df`;
  - status `approved_pending_controlled_submit`.
- Tokyo arm-state inspection found:
  - no local `orders` row for the new candidate / intent;
  - no `runtime_execution_order_lifecycle_adapter_results` row;
  - no exchange-submit action authorization;
  - no exchange-submit adapter result;
  - no exchange-submit execution result;
  - no submit-outcome review or post-submit settlement;
  - `ExecutionIntent` remains `recorded`.
- Important finding:
  - the previous arm attempt recorded an attempt reservation and applied an
    attempt mutation before trusted submit facts were fresh;
  - trusted submit facts were blocked by
    `trusted_reconciliation_fact_stale` and
    `trusted_submit_facts_not_fresh_enough`;
  - runtime attempts therefore moved from `attempts_used=1` to
    `attempts_used=2` even though no real submit occurred.
- Fix:
  - updated `scripts/runtime_first_real_submit_api_flow.py` so arm may tolerate
    the expected pre-adapter blocker
    `runtimeexecutionorderlifecycleadapterresult_not_found`, but stops before
    attempt reservation / attempt mutation when trusted submit facts or
    reconciliation blockers are present;
  - added unit coverage proving stale trusted facts block before attempt
    reservation, attempt mutation, local registration authorization, and
    exchange-submit authorization.
- Verification:
  - `pytest -q tests/unit/test_runtime_first_real_submit_api_flow.py` passed
    with `9 passed`;
  - `python3 -m py_compile scripts/runtime_first_real_submit_api_flow.py tests/unit/test_runtime_first_real_submit_api_flow.py`
    passed;
  - `git diff --check` passed.
- Safety result:
  - this local fix did not call exchange, create orders, call OrderLifecycle,
    create withdrawal/transfer instructions, or submit a real order;
  - Tokyo remote inspection confirms the current authorization has not reached
    exchange submit execution;
  - do not execute first-real-submit from this authorization until
    reconciliation facts are refreshed and the new evidence snapshot is clean.

## 2026-06-11 (Tokyo First-real-submit AVAX Short)

- Deployed `program/live-safe-v1` commit
  `918d0632c24e340e2f199de81e0c74668ee14715` to Tokyo via the git-based
  runtime-governance deploy path:
  `brc-runtime-governance-918d0632-20260611T102708Z`.
- Deploy verification:
  - Tokyo `app/current` points to the new release;
  - release manifest head is `918d0632c24e340e2f199de81e0c74668ee14715`;
  - postdeploy acceptance returned `postdeploy_acceptance_passed`;
  - readonly probe returned `ready_for_controlled_deploy_preflight`;
  - service health remained
    `{"status":"ok","service":"brc_operator_console","runtime_bound":true,"live_ready":false}`.
- Refreshed AVAX reconciliation read model before submit:
  - symbol `AVAX/USDT:USDT`;
  - status `recorded`;
  - severe mismatches `0`;
  - warning mismatches `0` before submit.
- Re-ran the fixed arm flow for authorization
  `runtime-submit-authorization-intent_rt_6ca3cecd63fafbd1d25760df`:
  - blockers `[]`;
  - trusted submit facts fresh;
  - local order registration result recorded;
  - exchange submit adapter result recorded;
  - first-real-submit packet status `ready_for_owner_final_review`;
  - existing attempt policy was reused, so no second attempt mutation was
    created by the re-arm.
- Executed the Owner-authorized first real runtime submit with the exact env
  confirmation value for this authorization.
- Exchange result:
  - entry local order `rtod-c4439560677fbd165a-entry`;
  - entry exchange order `39006512474`;
  - entry status `FILLED`;
  - filled quantity `1.0` AVAX;
  - average execution price `6.566`;
  - protection local order `rtod-c4439560677fbd165a-sl`;
  - protection exchange order `4000001548436778`;
  - protection status `OPEN`;
  - stop trigger price `6.639`;
  - no withdrawal or transfer instructions were created.
- Immediate post-submit issue:
  - outcome review first saw `entry_order_still_open_no_fill_unresolved`
    because local projection had not yet caught up to the exchange fill;
  - runtime monitor showed exchange active position `1` while local active
    position was still `0`, producing severe reconciliation mismatches.
- Applied local projection recovery from read-only exchange facts:
  - script `scripts/recover_runtime_exchange_submit_projection.py` dry-run
    returned `dry_run_ready`;
  - apply returned `applied`;
  - projected position id `pos_signal-evaluation-2037e48d00b3`;
  - recovery safety invariants reported exchange read-only and no exchange
    write / cancel / amend / close / withdrawal / transfer.
- Final monitor after recovery:
  - status `active_protection_warning`;
  - local active position count `1`;
  - exchange active position count `1`;
  - local open order count `1`;
  - exchange open stop order count `1`;
  - hard stop present `true`;
  - current quantity `1.0`;
  - entry price `6.566`;
  - mark price around `6.55965069` at the check;
  - unrealized PnL around `0.00634931` at the check;
  - reconciliation severe count `0`;
  - reconciliation warning count `1` for `missing_tp_protection`;
  - monitor blocker `runtime_max_active_positions_in_use` correctly blocks new
    entries while the active position is open.
- Outcome accounting after recovery:
  - submit outcome review status `classified_ready_for_attempt_outcome_policy`;
  - observed outcome `submitted_full_fill`;
  - first-real-submit outcome accounting status
    `ready_for_attempt_budget_outcome_accounting`;
  - post-submit budget settlement status `recorded_reserved_budget_consumed`;
  - budget action `confirm_reserved_budget_consumed`;
  - attempts used remain `2`, attempts remaining `1`;
  - budget reserved remains `0.166864220000000000`, budget remaining
    `5.833135780000000000`.
- Known warning / follow-up:
  - no TP order is mounted; current position is hard-stop-only;
  - this is an exit-policy / right-tail runner warning, not an immediate
    runaway-loss blocker, because the SL hard stop is present;
  - next work should monitor the open position and decide whether to add a
    bounded TP1 / runner-management action or keep it as a hard-stop-only
    first submit evidence sample.

## 2026-06-11 (Runtime Active-position Exit-plan Probe)

- Added and deployed a read-only runtime exit-management probe:
  - local commit `aa30b26616cbe2b7cbe315365800330265b7907f`
    added `scripts/runtime_position_exit_plan.py`;
  - follow-up commit `c261b81e54e20f8bd0b92bc6d4d3e95f622aa25c`
    fixed runtime probe env loading so env files are loaded before PG
    infrastructure imports snapshot `PG_DATABASE_URL`;
  - both commits were pushed to `origin/program/live-safe-v1`;
  - Tokyo now runs
    `brc-runtime-governance-c261b81e-20260611Topsprobe2`.
- Verification before deploy:
  - `pytest -q tests/unit/test_runtime_ops_scripts.py tests/unit/test_runtime_live_position_monitor.py tests/unit/test_trading_console_readmodels.py::test_trading_console_runtime_active_position_exit_plan_surfaces_tp1_feasibility`
    passed with `11 passed`;
  - `python3 -m py_compile scripts/runtime_live_position_monitor.py scripts/runtime_position_exit_plan.py tests/unit/test_runtime_ops_scripts.py`
    passed;
  - `git diff --check` passed.
- Tokyo deploy acceptance:
  - `verify_tokyo_runtime_governance_postdeploy.py` returned
    `postdeploy_acceptance_passed`;
  - `probe_tokyo_runtime_governance_readonly.py` returned
    `ready_for_controlled_deploy_preflight`;
  - deployed head is
    `c261b81e54e20f8bd0b92bc6d4d3e95f622aa25c`;
  - migration count remains `84`;
  - latest migration remains
    `2026-06-11-084_create_runtime_post_submit_budget_settlements.py`;
  - service health remained
    `{"status":"ok","service":"brc_operator_console","runtime_bound":true,"live_ready":false}`.
- Remote live-position monitor for
  `strategy-runtime-95655873b76c`:
  - status `active_protection_warning`;
  - symbol `AVAX/USDT:USDT`;
  - side `short`;
  - runtime status `active`;
  - current quantity `1.0`;
  - entry price `6.566`;
  - mark price around `6.57`;
  - local active position count `1`;
  - exchange active position count `1`;
  - local open order count `1`;
  - exchange open stop order count `1`;
  - SL protection present `true`;
  - TP protection present `false`;
  - hard stop boundary present `true`;
  - liquidation price reported around `36.81301033`;
  - reconciliation severe count `0`;
  - reconciliation warning count `1` for `missing_tp_protection`;
  - attempts used `2`, attempts remaining `1`, max attempts `3`;
  - budget reserved `0.166864220000000000`;
  - budget remaining `5.833135780000000000`;
  - new entries remain blocked by `runtime_max_active_positions_in_use`.
- Remote active-position exit plan:
  - status `ready_for_owner_review`;
  - action kind `tp1_partial_plus_runner_review`;
  - active position present `true`;
  - hard stop boundary present `true`;
  - existing TP protection present `false`;
  - stop price reference `6.639000000000000000`;
  - risk per unit `0.073000000000000000`;
  - TP1 price reference `6.493000000000000000`;
  - requested TP1 quantity `0.50`;
  - step-aligned TP1 quantity `0.0`;
  - runner quantity reference `1.0`;
  - reduce-only side would be `buy`;
  - market min quantity `1.0`;
  - market quantity step `1.0`;
  - TP1 quantity feasible `false`;
  - warning `tp1_partial_quantity_below_min_qty_or_step`;
  - recommended Owner decision
    `keep_hard_stop_only_or_authorize_different_reduce_only_exit_shape`.
- Safety proof:
  - both runtime monitor and exit-plan probe reported exchange read-only facts;
  - exchange write called `false`;
  - order created / cancelled / amended `false`;
  - position closed `false`;
  - runtime state mutated `false`;
  - withdrawal or transfer created `false`;
  - `RuntimePositionExitPlan` remains explicitly not an order, not an
    execution intent, and not execution authority.

## 2026-06-11 (Runtime Exit-plan Reduce-only Close Option)

- Added and deployed `program/live-safe-v1` commit
  `6454b4003c6f07d10462b4cee36dac399e1856a6` to Tokyo as
  `brc-runtime-governance-6454b400-20260611Texitoption`.
- Extended the non-executing `RuntimePositionExitPlan` so the active-position
  review surface now distinguishes:
  - TP1 partial + runner feasibility;
  - full reduce-only close feasibility;
  - full reduce-only close notional reference;
  - the fact that a full reduce-only close is risk-reducing but still requires
    explicit Owner authorization before any exchange write.
- Fixed post-close operational scripts so env files are loaded before PG /
  exchange infrastructure imports:
  - `scripts/recover_runtime_exchange_close_projection.py`;
  - `scripts/create_runtime_closed_trade_review.py`.
  This prevents the same `PG_DATABASE_URL` snapshot issue that affected the
  runtime monitor / exit-plan probes.
- Local verification:
  - `pytest -q tests/unit/test_runtime_live_position_monitor.py tests/unit/test_runtime_ops_scripts.py tests/unit/test_trading_console_readmodels.py::test_trading_console_runtime_active_position_exit_plan_surfaces_tp1_feasibility`
    passed with `12 passed`;
  - `python3 -m py_compile src/domain/runtime_position_exit_plan.py scripts/runtime_position_exit_plan.py scripts/runtime_live_position_monitor.py scripts/recover_runtime_exchange_close_projection.py scripts/create_runtime_closed_trade_review.py tests/unit/test_runtime_ops_scripts.py tests/unit/test_runtime_live_position_monitor.py`
    passed;
  - `git diff --check` passed.
- Tokyo deploy acceptance:
  - postdeploy acceptance returned `postdeploy_acceptance_passed`;
  - readonly probe returned `ready_for_controlled_deploy_preflight`;
  - deployed head is
    `6454b4003c6f07d10462b4cee36dac399e1856a6`;
  - health remained
    `{"status":"ok","service":"brc_operator_console","runtime_bound":true,"live_ready":false}`.
- Remote exit-plan verification for
  `strategy-runtime-95655873b76c`:
  - status `ready_for_owner_review`;
  - symbol `AVAX/USDT:USDT`;
  - side `short`;
  - current quantity `1.0`;
  - entry price `6.566`;
  - stop price reference `6.639000000000000000`;
  - TP1 price reference `6.493000000000000000`;
  - TP1 quantity requested `0.50`;
  - TP1 step-aligned quantity `0.0`;
  - TP1 feasible `false`;
  - full reduce-only close quantity `1.0`;
  - full reduce-only close notional reference around `6.571937910`;
  - full reduce-only close feasible `true`;
  - full reduce-only close requires Owner authorization `true`;
  - recommended Owner decision
    `keep_hard_stop_only_or_owner_authorize_full_reduce_only_close`;
  - no blockers; warning remains `tp1_partial_quantity_below_min_qty_or_step`.
- Safety proof:
  - the deployed change does not submit, cancel, amend, or close exchange
    orders;
  - exit-plan remains not an order, not an execution intent, and not execution
    authority;
  - remote probe reported exchange write called `false`, order created
    `false`, position closed `false`, runtime state mutated `false`, and no
    withdrawal / transfer.

## 2026-06-11 (Runtime Reduce-only Close Owner Packet)

- Added and deployed `program/live-safe-v1` commit
  `df5c4050f324c15c529059766689f2e8de03d96e` to Tokyo as
  `brc-runtime-governance-df5c4050-20260611Tclosepacket`.
- Added a non-executing Owner authorization packet for active runtime
  reduce-only close review:
  - domain model
    `src/domain/runtime_reduce_only_close_authorization.py`;
  - CLI
    `scripts/build_runtime_reduce_only_close_owner_packet.py`;
  - tests
    `tests/unit/test_runtime_reduce_only_close_authorization.py`.
- The packet converts the current `RuntimePositionExitPlan` into a reviewable
  Owner authorization surface. It exposes:
  - runtime / symbol / side;
  - reduce-only close side;
  - close quantity;
  - notional reference;
  - source monitor / exit-plan IDs;
  - exact Owner approval env var and value.
- Local verification:
  - `pytest -q tests/unit/test_runtime_reduce_only_close_authorization.py tests/unit/test_runtime_live_position_monitor.py tests/unit/test_runtime_ops_scripts.py`
    passed with `13 passed`;
  - `python3 -m py_compile src/domain/runtime_reduce_only_close_authorization.py scripts/build_runtime_reduce_only_close_owner_packet.py tests/unit/test_runtime_reduce_only_close_authorization.py`
    passed;
  - `git diff --check` passed.
- Tokyo deploy acceptance:
  - postdeploy acceptance returned `postdeploy_acceptance_passed`;
  - readonly probe returned `ready_for_controlled_deploy_preflight`;
  - deployed head is
    `df5c4050f324c15c529059766689f2e8de03d96e`;
  - health remained
    `{"status":"ok","service":"brc_operator_console","runtime_bound":true,"live_ready":false}`.
- Remote Owner close packet for
  `strategy-runtime-95655873b76c`:
  - status `ready_for_owner_authorization`;
  - symbol `AVAX/USDT:USDT`;
  - side `short`;
  - reduce-only side `buy`;
  - close quantity `1.0`;
  - close notional reference around `6.5730`;
  - entry price `6.566`;
  - stop price reference `6.639000000000000000`;
  - blockers `[]`;
  - warning `tp1_partial_quantity_below_min_qty_or_step`;
  - Owner approval env
    `OWNER_APPROVED_RUNTIME_REDUCE_ONLY_CLOSE`;
  - Owner approval value
    `runtime-reduce-only-close:strategy-runtime-95655873b76c:AVAX/USDT:USDT:short:qty=1.0:owner-authorized`.
- Safety proof:
  - this stage did not submit, cancel, amend, or close any exchange order;
  - it did not create an order, ExecutionIntent, withdrawal, or transfer;
  - it did not mutate runtime state;
  - the packet is explicitly not an order, not an execution intent, and not
    execution authority.
- Remaining live action:
  - a real reduce-only close still requires a separate explicit Owner action
    using the exact approval value above, followed by fresh fact revalidation.

## 2026-06-11 (Owner-gated Runtime Reduce-only Close Flow)

- Added and deployed `program/live-safe-v1` commit
  `624ca044488c7e656d8a7f502013dac01d66c597` to Tokyo as
  `brc-runtime-governance-624ca044-20260611Tcloseflow`.
- Added `scripts/runtime_owner_reduce_only_close_flow.py`:
  - default mode is dry-run;
  - it rebuilds the reduce-only close Owner packet from fresh PG / exchange /
    reconciliation facts;
  - real close requires both:
    - exact env var
      `OWNER_APPROVED_RUNTIME_REDUCE_ONLY_CLOSE`;
    - explicit CLI flag `--execute-real-close`;
  - before any exchange write it revalidates that the active local position
    count is exactly `1` and the current quantity still matches the fresh
    Owner packet.
- Updated `ExecutionOrchestrator.execute_controlled_close()` with a `scope`
  metadata parameter so the same reduce-only close primitive can preserve
  `runtime_owner_reduce_only_close` semantics instead of pretending to be a
  testnet smoke.
- Local verification:
  - `pytest -q tests/unit/test_runtime_owner_reduce_only_close_flow.py tests/unit/test_tiny001d4_controlled_close.py tests/unit/test_runtime_reduce_only_close_authorization.py`
    passed with `8 passed`;
  - `python3 -m py_compile scripts/runtime_owner_reduce_only_close_flow.py src/application/execution_orchestrator.py tests/unit/test_runtime_owner_reduce_only_close_flow.py tests/unit/test_tiny001d4_controlled_close.py`
    passed;
  - `git diff --check` passed.
- Tokyo deploy acceptance:
  - postdeploy acceptance returned `postdeploy_acceptance_passed`;
  - readonly probe returned `ready_for_controlled_deploy_preflight`;
  - deployed head is
    `624ca044488c7e656d8a7f502013dac01d66c597`;
  - health remained
    `{"status":"ok","service":"brc_operator_console","runtime_bound":true,"live_ready":false}`.
- Remote dry-run on `strategy-runtime-95655873b76c`:
  - status `ready_for_owner_authorization`;
  - executed `false`;
  - reduce-only close side `buy`;
  - close quantity `1.0`;
  - close notional reference around `6.581158740`;
  - blockers only
    `OWNER_APPROVED_RUNTIME_REDUCE_ONLY_CLOSE_missing_or_wrong`;
  - required approval value remained
    `runtime-reduce-only-close:strategy-runtime-95655873b76c:AVAX/USDT:USDT:short:qty=1.0:owner-authorized`.
- Safety proof:
  - dry-run rebuilt fresh facts and then stopped before exchange write;
  - exchange write called `false`;
  - order created `false`;
  - position closed `false`;
  - runtime state mutated `false`;
  - no withdrawal / transfer.
- Remaining live action:
  - if Owner explicitly authorizes the exact value above, the next step can run
    the same script with `--execute-real-close`, then verify projection,
    reconciliation, closed review, and next-attempt gate.

## 2026-06-11 (Runtime Post-close Follow-up Packet)

- Added and deployed `program/live-safe-v1` commits:
  - `3f28b1f60c9a90b9894fb3e52c25d0bc83450efd`
    `feat(runtime): add post-close follow-up packet`;
  - `524c869ea36bb8c65712fe8075185da335c5700c`
    `fix(runtime): keep post-close follow-up CLI JSON clean`.
- Added a non-executing post-close follow-up packet:
  - domain model `src/domain/runtime_post_close_followup.py`;
  - CLI `scripts/build_runtime_post_close_followup_packet.py`;
  - tests
    `tests/unit/test_runtime_post_close_followup.py` and
    `tests/unit/test_runtime_post_close_followup_script.py`.
- The packet keeps the close aftermath explicit:
  - active position still present -> wait for Owner reduce-only close
    authorization or continue holding;
  - after flat -> verify reconciliation, record closed trade review, then
    verify next-attempt gate;
  - flat with review gate clear -> post-close follow-up complete.
- Local verification:
  - `pytest -q tests/unit/test_runtime_post_close_followup.py tests/unit/test_runtime_post_close_followup_script.py tests/unit/test_runtime_reduce_only_close_authorization.py tests/unit/test_runtime_live_position_monitor.py`
    passed with `13 passed`;
  - `python3 -m py_compile src/domain/runtime_post_close_followup.py scripts/build_runtime_post_close_followup_packet.py tests/unit/test_runtime_post_close_followup.py tests/unit/test_runtime_post_close_followup_script.py`
    passed;
  - `git diff --check` passed.
- Tokyo deploy acceptance for final deployed head
  `524c869ea36bb8c65712fe8075185da335c5700c`:
  - postdeploy acceptance returned `postdeploy_acceptance_passed`;
  - readonly probe returned `ready_for_controlled_deploy_preflight`;
  - deployed release is
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-524c869e-20260611Tfollowup-json`;
  - migration count remained `84`;
  - latest migration remained
    `2026-06-11-084_create_runtime_post_submit_budget_settlements.py`;
  - health remained
    `{"status":"ok","service":"brc_operator_console","runtime_bound":true,"live_ready":false}`.
- Remote post-close follow-up packet for
  `strategy-runtime-95655873b76c`:
  - status `waiting_for_owner_close_authorization`;
  - active position present `true`;
  - symbol `AVAX/USDT:USDT`;
  - owner close packet status `ready_for_owner_authorization`;
  - blockers `[]`;
  - warnings:
    `missing_tp_protection_right_tail_exit_not_mounted`,
    `reconciliation_warning_present`;
  - required steps include exact Owner authorization, reduce-only close flow,
    flat monitor verification, reconciliation severe-count verification,
    closed trade review, and next-attempt gate verification;
  - Owner approval value remains
    `runtime-reduce-only-close:strategy-runtime-95655873b76c:AVAX/USDT:USDT:short:qty=1.0:owner-authorized`.
- Safety proof:
  - this stage did not execute a close;
  - exchange write called `false`;
  - order created / cancelled / amended `false`;
  - position closed `false`;
  - runtime state mutated `false`;
  - no withdrawal / transfer.
- Remaining live action:
  - the real reduce-only close is still not executed;
  - it still requires the exact Owner approval value above plus the explicit
    `--execute-real-close` flag, followed by flat / reconciliation / review /
    next-attempt verification.

## 2026-06-11 (Runtime Closed-review Facts Resolver)

- Added and deployed `program/live-safe-v1` commit
  `7a59d64b2425d8a46f331c84cdd84abd3ad458ae`
  `feat(runtime): resolve closed review facts`.
- Tightened the real reduce-only close audit chain:
  - `ExecutionOrchestrator.execute_controlled_close()` now makes the generated
    EXIT order inherit runtime semantic IDs from the active position or entry
    order;
  - this preserves `runtime_instance_id`, trial binding, strategy family,
    strategy family version, signal evaluation, and order candidate IDs on the
    terminal close order.
- Added a read-only closed-review facts resolver:
  - domain packet `src/domain/runtime_closed_trade_review_facts.py`;
  - application service
    `src/application/runtime_closed_trade_review_facts_service.py`;
  - CLI `scripts/build_runtime_closed_trade_review_facts_packet.py`;
  - tests
    `tests/unit/test_runtime_closed_trade_review_facts.py` and
    `tests/unit/test_runtime_closed_trade_review_facts_script.py`.
- The resolver bridges close -> review by identifying the entry and terminal
  exit order IDs that should be passed to
  `scripts/create_runtime_closed_trade_review.py`.
- It remains non-executing:
  - no review record is created;
  - no exchange is called;
  - no order is created, cancelled, amended, or submitted;
  - no runtime state is mutated;
  - no withdrawal / transfer is created.
- Local verification:
  - `pytest -q tests/unit/test_runtime_closed_trade_review_facts.py tests/unit/test_runtime_closed_trade_review_facts_script.py tests/unit/test_tiny001d4_controlled_close.py tests/unit/test_runtime_closed_trade_lifecycle_review.py tests/unit/test_runtime_owner_reduce_only_close_flow.py`
    passed with `16 passed`;
  - `python3 -m py_compile src/domain/runtime_closed_trade_review_facts.py src/application/runtime_closed_trade_review_facts_service.py scripts/build_runtime_closed_trade_review_facts_packet.py src/application/execution_orchestrator.py tests/unit/test_runtime_closed_trade_review_facts.py tests/unit/test_runtime_closed_trade_review_facts_script.py tests/unit/test_tiny001d4_controlled_close.py`
    passed;
  - `git diff --check` passed.
- Tokyo deploy acceptance:
  - postdeploy acceptance returned `postdeploy_acceptance_passed`;
  - readonly probe returned `ready_for_controlled_deploy_preflight`;
  - deployed release is
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-7a59d64b-20260611Treviewfacts`;
  - deployed head is
    `7a59d64b2425d8a46f331c84cdd84abd3ad458ae`;
  - health remained
    `{"status":"ok","service":"brc_operator_console","runtime_bound":true,"live_ready":false}`.
- Remote closed-review facts packet for
  `strategy-runtime-95655873b76c`:
  - status `waiting_for_close`;
  - active position count `1`;
  - resolved entry order id `rtod-c4439560677fbd165a-entry`;
  - terminal exit order id `None`;
  - blockers `[]`;
  - safety invariants reported `pg_read_only=true`, `exchange_called=false`,
    `exchange_write_called=false`, `review_record_created=false`,
    `order_created=false`, `position_closed=false`, and
    `runtime_state_mutated=false`.
- Remaining live action:
  - real reduce-only close is still not executed;
  - after close, rerun the resolver; expected next status is
    `ready_for_closed_review` with entry / exit order IDs and the dry-run
    review command args.

## 2026-06-11 (Post-close Follow-up Carries Review Facts)

- Added and deployed `program/live-safe-v1` commit
  `c89ce4f0c71a95f4c075e029ed8b0d16fbebbdd7`
  `feat(runtime): attach closed review facts to follow-up`.
- `RuntimePostCloseFollowupPacket` now carries the read-only closed-review
  facts summary:
  - `closed_review_facts_status`;
  - resolved `closed_review_entry_order_id`;
  - resolved `closed_review_exit_order_id`;
  - `closed_review_command_args` for
    `scripts/create_runtime_closed_trade_review.py` once the runtime is flat.
- `scripts/build_runtime_post_close_followup_packet.py` now builds and returns
  `closed_review_facts_packet` alongside the monitor and Owner close packet.
- Local verification:
  - `pytest -q tests/unit/test_runtime_post_close_followup.py tests/unit/test_runtime_post_close_followup_script.py tests/unit/test_runtime_closed_trade_review_facts.py tests/unit/test_runtime_closed_trade_review_facts_script.py tests/unit/test_runtime_owner_reduce_only_close_flow.py`
    passed with `13 passed`;
  - `python3 -m py_compile src/domain/runtime_post_close_followup.py scripts/build_runtime_post_close_followup_packet.py tests/unit/test_runtime_post_close_followup.py`
    passed;
  - `git diff --check` passed.
- Tokyo deploy acceptance:
  - postdeploy acceptance returned `postdeploy_acceptance_passed`;
  - readonly probe returned `ready_for_controlled_deploy_preflight`;
  - deployed release is
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-c89ce4f0-20260611Tfollowup-reviewfacts`;
  - deployed head is
    `c89ce4f0c71a95f4c075e029ed8b0d16fbebbdd7`;
  - health remained
    `{"status":"ok","service":"brc_operator_console","runtime_bound":true,"live_ready":false}`.
- Remote post-close follow-up packet for
  `strategy-runtime-95655873b76c`:
  - status `waiting_for_owner_close_authorization`;
  - active position present `true`;
  - `closed_review_facts_status=waiting_for_close`;
  - closed-review facts packet status `waiting_for_close`;
  - resolved entry order id `rtod-c4439560677fbd165a-entry`;
  - terminal exit order id `None`;
  - Owner close approval value remains
    `runtime-reduce-only-close:strategy-runtime-95655873b76c:AVAX/USDT:USDT:short:qty=1.0:owner-authorized`;
  - blockers `[]`.
- Safety proof:
  - `closed_review_facts_pg_read_only=true`;
  - exchange write called `false`;
  - review record created `false`;
  - order created / cancelled / amended `false`;
  - position closed `false`;
  - runtime state mutated `false`;
  - no withdrawal / transfer.
- Remaining live action:
  - real reduce-only close is still not executed;
  - after close, this same post-close follow-up packet should progress from
    close authorization to closed-review command args and next-attempt gate
    verification.

## 2026-06-11 (Post-close Operator Command Plan)

- Added and deployed `program/live-safe-v1` commit
  `cca3efdee0518dabb9df8c889a0eb92491b83099`
  `feat(runtime): include post-close operator command plan`.
- `scripts/build_runtime_post_close_followup_packet.py` now includes a
  non-executing `operator_command_plan` in its JSON output.
- The command plan carries:
  - refresh follow-up command args;
  - Owner reduce-only close dry-run command args;
  - Owner reduce-only close execute command args;
  - required Owner approval env/value;
  - closed-review facts refresh command args;
  - closed-review command args when the runtime is flat and review facts are
    ready;
  - the expected post-close sequence from refresh -> Owner authorization ->
    close -> flat verification -> review -> next-attempt gate.
- Local verification:
  - `pytest -q tests/unit/test_runtime_post_close_followup_script.py tests/unit/test_runtime_post_close_followup.py tests/unit/test_runtime_closed_trade_review_facts.py tests/unit/test_runtime_owner_reduce_only_close_flow.py`
    passed with `12 passed`;
  - `python3 -m py_compile scripts/build_runtime_post_close_followup_packet.py tests/unit/test_runtime_post_close_followup_script.py`
    passed;
  - `git diff --check` passed.
- Tokyo deploy acceptance:
  - postdeploy acceptance returned `postdeploy_acceptance_passed`;
  - readonly probe returned `ready_for_controlled_deploy_preflight`;
  - deployed release is
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-cca3efde-20260611Tcommandplan`;
  - deployed head is
    `cca3efdee0518dabb9df8c889a0eb92491b83099`;
  - health remained
    `{"status":"ok","service":"brc_operator_console","runtime_bound":true,"live_ready":false}`.
- Remote post-close follow-up packet for
  `strategy-runtime-95655873b76c`:
  - status `waiting_for_owner_close_authorization`;
  - closed-review facts status `waiting_for_close`;
  - resolved entry order id `rtod-c4439560677fbd165a-entry`;
  - Owner close approval value remains
    `runtime-reduce-only-close:strategy-runtime-95655873b76c:AVAX/USDT:USDT:short:qty=1.0:owner-authorized`;
  - operator execute args are present but not executed:
    `scripts/runtime_owner_reduce_only_close_flow.py --runtime-instance-id strategy-runtime-95655873b76c --env-file /home/ubuntu/brc-deploy/env/live-readonly.env --execute-real-close`.
- Safety proof:
  - command plan reported `command_plan_only=true`;
  - exchange write called `false`;
  - review record created `false`;
  - order created `false`;
  - position closed `false`;
  - runtime state mutated `false`;
  - no withdrawal / transfer.
- Remaining live action:
  - real reduce-only close is still not executed;
  - the next live step still requires exact Owner authorization before running
    the execute command with the approval env value.

## 2026-06-11 (Trading Console Post-close Follow-up API)

- Added and deployed `program/live-safe-v1` commit
  `03229c7877d44003b2fb76263434ea22d80ed212`
  `feat(console): expose runtime post-close follow-up`.
- Added authenticated read-only Trading Console endpoint:
  - `GET /api/trading-console/strategy-runtimes/{runtime_instance_id}/post-close-follow-up`.
- The endpoint returns the same non-executing post-close payload shape used by
  the operator script:
  - monitor packet;
  - Owner close packet;
  - closed-review facts packet;
  - operator command plan;
  - no-write safety invariants.
- The endpoint uses existing runtime monitor / exit plan services plus the
  closed-review facts resolver. It does not place, cancel, amend, or submit
  orders; it does not write a review record; it does not mutate runtime state.
- Local verification:
  - `pytest -q tests/unit/test_trading_console_readmodels.py -k "post_close_followup or live_position_monitor or active_position_exit_plan or requires_operator_session or router_keeps_read_models"`
    passed with `5 passed`;
  - `python3 -m py_compile src/interfaces/api_trading_console.py tests/unit/test_trading_console_readmodels.py`
    passed;
  - `git diff --check` passed.
- Tokyo deploy acceptance:
  - postdeploy acceptance returned `postdeploy_acceptance_passed`;
  - readonly probe returned `ready_for_controlled_deploy_preflight`;
  - deployed release is
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-03229c78-20260611Tpostcloseapi`;
  - deployed head is
    `03229c7877d44003b2fb76263434ea22d80ed212`;
  - health remained
    `{"status":"ok","service":"brc_operator_console","runtime_bound":true,"live_ready":false}`.
- Remote API smoke:
  - unauthenticated GET to the new endpoint returned `401 Operator login
    required`, proving the endpoint is not exposed outside the Operator session;
  - remote script path still returned
    `waiting_for_owner_close_authorization`,
    `closed_review_facts=waiting_for_close`, and
    `command_plan_only=true`.
- Remaining live action:
  - real reduce-only close is still not executed;
  - the Trading Console can now read the post-close plan, but actual close still
    requires exact Owner authorization and the explicit execute flag.

## 2026-06-11 (Trading Console Post-close Follow-up Panel)

- Added a Trading Console runtime page panel for the authenticated
  post-close follow-up API.
- The panel surfaces:
  - current post-close status;
  - active-position / flat state;
  - Owner exact reduce-only close approval env and value as evidence only;
  - resolved closed-review entry / exit order facts;
  - completed and required follow-up steps;
  - operator command plan as non-executing command evidence;
  - no-write safety invariants.
- UI safety boundary:
  - no close button;
  - no auto-filled execution action;
  - no order submit / cancel / amend affordance;
  - no review write action from this panel;
  - no withdrawal / transfer affordance.
- Local verification:
  - `npm run lint` passed in `trading-console`;
  - `npm run build` passed in `trading-console`;
  - `pytest -q tests/unit/test_trading_console_readmodels.py -k "post_close_followup or live_position_monitor or active_position_exit_plan or requires_operator_session or router_keeps_read_models"`
    passed with `5 passed`;
  - `git diff --check` passed.
- Playwright verification:
  - opened `http://127.0.0.1:3016/runtime` through the Trading Console
    frontend proxy;
  - used a local mock read-only API upstream, not exchange or Tokyo writes;
  - confirmed the page rendered the new `平仓后跟进` panel with
    `等待 Owner 平仓授权`, `控制台不执行平仓`, `仅计划`, and
    `交易所写入 无`;
  - toggled from dark mode to light mode and confirmed the runtime page remained
    rendered without console runtime errors.
- Remaining live action:
  - real reduce-only close is still not executed;
  - current panel is an operator evidence surface only.

## 2026-06-11 (Strategy Shadow Planning Current-HEAD Reverification)

- Re-entered the backend strategy integration line after the Trading Console
  post-close follow-up panel stage.
- Current mainline remains `program/live-safe-v1`.
- Verified that Strategy Signal -> Shadow Candidate Planning v1 is already
  integrated in tracked code on the current mainline:
  - `RuntimeStrategySignalEvaluationService` routes CPM / BRF / P1-P3
    reference price-action signals through the semantics gate;
  - only `READY_FOR_SEMANTIC_BINDING` can proceed to shadow candidate
    planning;
  - CPM long and BRF short produce shadow-only candidate proposals with entry,
    structure stop, notional / leverage / margin / max-loss preview, TP1 1R
    partial, and runner / trailing metadata;
  - CPM short mismatch blocks before shadow records;
  - RMR / FCO remain non-trading in this stage;
  - missing trusted account facts or trusted active-position projection block
    before shadow records are created.
- Current verification:
  - `pytest -q tests/unit/test_b0_runtime_strategy_signal_planning.py tests/unit/test_runtime_strategy_signal_evaluation_service.py tests/unit/test_reference_price_action_evaluators.py tests/unit/test_brf_price_action_evaluator.py tests/unit/test_strategy_candidate_semantics.py tests/unit/test_b0_strategy_runtime_fact_overlay.py tests/unit/test_b0_runtime_strategy_signal_scheduler_assembly.py tests/unit/test_strategy_observation_shadow_planning_rehearsal.py`
    passed with `50 passed`;
  - `python3 scripts/verify_strategy_observation_shadow_planning_rehearsal.py --json`
    returned `status=rehearsal_passed`;
  - rehearsal safety invariants were all false:
    `exchange_called=false`, `execution_intent_created=false`,
    `order_created=false`, `order_lifecycle_called=false`,
    `owner_bounded_execution_called=false`, and
    `withdrawal_or_transfer_created=false`.
- Assessment:
  - no immediate backend patch is required for Strategy Signal -> Shadow
    Candidate Planning v1;
  - the next mainline move should not add more planning gates by default;
  - either deploy the current UI/API commit when useful, or proceed to the
    Owner-authorized reduce-only close / closed-review loop before unlocking
    the next bounded runtime attempt.

## 2026-06-11 (Tokyo Deploy 24d3e580 + Public Smoke)

- Deployed current mainline commit
  `24d3e5800d8a5f93f28bb8850eb4cdb4b1562fe9` from
  `program/live-safe-v1` to Tokyo.
- Release identity:
  - release path:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-24d3e580-20260611Tpostcloseui`;
  - previous release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-03229c78-20260611Tpostcloseapi`;
  - database backup:
    `/home/ubuntu/brc-deploy/backups/brc-runtime-governance-24d3e580-20260611Tpostcloseui.pgdump`.
- Backend deploy result:
  - deployment script returned `status=applied`;
  - `current` symlink points at the 24d3e580 release;
  - service health returned
    `{"status":"ok","service":"brc_operator_console","runtime_bound":true,"live_ready":false}`;
  - postdeploy acceptance returned `postdeploy_acceptance_passed`.
- Frontend static deploy:
  - nginx public root is `/var/www/brc-owner-console`;
  - the git release deploy does not automatically refresh that static root, so
    the Trading Console was built on Tokyo from the deployed release and synced
    atomically to nginx static root;
  - public bundle now references `assets/index-MSAucmV7.js` and
    `assets/index-DTVIUMuM.css`;
  - previous static root backup:
    `/home/ubuntu/brc-deploy/backups/brc-owner-console-static-24d3e580-20260611T122042Z`.
- Public smoke:
  - `http://43.133.176.150/` returned 200 and referenced the new JS/CSS assets;
  - `http://43.133.176.150/assets/index-MSAucmV7.js` returned 200;
  - `http://43.133.176.150/assets/index-DTVIUMuM.css` returned 200;
  - `http://43.133.176.150/api/health` returned ok with `live_ready=false`;
  - unauthenticated post-close follow-up API returned 401
    `Operator login required`.
- Safety:
  - this deployment did not execute the real reduce-only close;
  - no exchange order, OrderLifecycle submit, withdrawal, or transfer was
    performed in this deploy stage.

## 2026-06-11 (Owner-authorized AVAX Runtime Reduce-only Close)

- Owner authorized the exact live close value:
  `runtime-reduce-only-close:strategy-runtime-95655873b76c:AVAX/USDT:USDT:short:qty=1.0:owner-authorized`.
- Scope:
  - runtime: `strategy-runtime-95655873b76c`;
  - symbol: `AVAX/USDT:USDT`;
  - side: short;
  - authorized reduce-only close quantity: `1.0`;
  - no new entry, withdrawal, transfer, or strategy self-authorization was
    authorized.
- First execute attempt:
  - dry-run produced the same required approval value and was
    `ready_for_owner_authorization`;
  - the first real close attempt was rejected by Binance with `-4061`
    `Order's position side does not match user's setting`;
  - the root cause was that runtime controlled close did not pass Binance
    hedge-mode `position_side=SHORT` for the short reduce-only close;
  - the failure path also exposed a local lifecycle issue where a CREATED local
    close order was being marked REJECTED, which is not a valid state-machine
    transition.
- Fix:
  - committed and pushed `59c69006 fix(runtime): send hedge position side on
    controlled close`;
  - `ExecutionOrchestrator.execute_controlled_close` now passes
    `position_side=LONG/SHORT` only for Binance;
  - placement failures before exchange submit now terminalize the local CREATED
    close order as CANCELED instead of masking the original exchange rejection
    with a state transition error.
- Tests:
  - `pytest -q tests/unit/test_tiny001d4_controlled_close.py tests/unit/test_runtime_reduce_only_close_authorization.py tests/unit/test_runtime_post_close_followup.py tests/unit/test_runtime_owner_reduce_only_close_flow.py`
    passed with `13 passed`.
- Tokyo deploy:
  - deployed `59c69006add2701d5be73477c5b95c7ff10ad951` to
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-59c69006-20260611Tclosefix`;
  - deploy result was `status=applied`;
  - postdeploy acceptance returned `postdeploy_acceptance_passed`;
  - health remained `runtime_bound=true`, `live_ready=false`.
- Successful close:
  - refreshed dry-run after deploy still required the exact Owner approval
    value above;
  - real reduce-only close executed with status `executed_reduce_only_close`;
  - exit order: `exit_controlled_c03b446704fa`;
  - exchange exit order: `39007184328`;
  - filled quantity: `1.0`;
  - average exit price: `6.512`;
  - projected realized PnL: `0.0540`;
  - remaining SL protection order `rtod-c4439560677fbd165a-sl` /
    `4000001548436778` was canceled.
- Cleanup:
  - local residual close order from the failed first attempt
    `exit_controlled_1ad998f2aae9` had no exchange order id and was
    terminalized to CANCELED with reason
    `cleanup_failed_owner_reduce_only_close_attempt_no_exchange_order`.
- Post-close facts:
  - PG active positions for `AVAX/USDT:USDT`: `0`;
  - exchange active positions from the runtime monitor: `0`;
  - local open orders: `0`;
  - exchange open stop orders: `0`;
  - reconciliation severe count: `0`;
  - reconciliation warning count: `0`.
- Closed review:
  - dry-run status was `ready_to_record`;
  - applied closed lifecycle review:
    `live-review-runtime-review:strategy-runtime-95655873b76c-closed-reviewed-exit_controlled_c03b446704fa`;
  - review status: `closed_reviewed`;
  - lifecycle status: `closed_reviewed`;
  - strategy outcome: `ordinary_win`;
  - R multiple: `0.3236`;
  - review write did not create an ExecutionIntent, place an order, mutate
    runtime budget, or create withdrawal / transfer instructions.
- Remaining follow-up:
  - post-close follow-up still renders `ready_for_closed_review` after the
    review record exists because it resolves entry / exit facts but does not
    yet check for an existing lifecycle review record;
  - this is a read-model/product-state issue, not an exchange safety issue, and
    should be fixed before relying on the panel as the sole next-attempt
    operator signal.

## 2026-06-11 (Post-close Complete + Next-attempt Gate)

- Post-close read-model fix:
  - committed and pushed `ae0c0ad6 fix(console): complete runtime post-close
    after review`;
  - the Trading Console post-close follow-up now checks the latest
    `brc_live_lifecycle_reviews` record for
    `runtime-review:{runtime_instance_id}` and marks the packet
    `post_close_complete` when the runtime is flat and the lifecycle review is
    `closed_reviewed`;
  - the operator plan no longer suggests a duplicate closed-review command
    after review is recorded.
- Ops script parity fix:
  - committed and pushed `a638dfc8 fix(ops): complete post-close followup
    script after review`;
  - `scripts/build_runtime_post_close_followup_packet.py` now reads the same
    lifecycle-review fact and returns `post_close_complete` for the AVAX runtime
    after the closed review exists.
- Tokyo deploys:
  - deployed `ae0c0ad6` to
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-ae0c0ad6-20260611Tpostclosecomplete`;
  - deployed `a638dfc8` to
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-a638dfc8-20260611Tpostclisync`;
  - both deployments returned `status=applied` and postdeploy acceptance
    passed.
- Post-close script verification on Tokyo:
  - `scripts/build_runtime_post_close_followup_packet.py --runtime-instance-id
    strategy-runtime-95655873b76c --env-file
    /home/ubuntu/brc-deploy/env/live-readonly.env` returned
    `post_close_complete`;
  - `closed_review_recorded=true`;
  - closed review id:
    `live-review-runtime-review:strategy-runtime-95655873b76c-closed-reviewed-exit_controlled_c03b446704fa`;
  - required sequence is now only `verify_next_attempt_gate`.
- Next-attempt gate packet:
  - committed and pushed `e6b90dbb feat(ops): add runtime next-attempt gate
    packet`;
  - added `scripts/verify_runtime_next_attempt_gate_packet.py`, a read-only
    ops packet that signs a local operator session and calls the official
    Trading Console `owner-action-flow` next-attempt gate;
  - the packet reads runtime context from PG, can include exchange read-only
    facts, and explicitly does not create an ExecutionIntent, order, runtime
    mutation, withdrawal, or transfer.
- Tests:
  - `pytest -q tests/unit/test_runtime_next_attempt_gate_packet_script.py
    tests/unit/test_runtime_post_close_followup_script.py
    tests/unit/test_runtime_post_close_followup.py` passed with `13 passed`.
- Tokyo deploy:
  - deployed `e6b90dbb693dcaa74eb48a6ab78254497ec7b96a` to
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-e6b90dbb-20260611Tnextattemptgate`;
  - deploy result was `status=applied`;
  - postdeploy acceptance returned `postdeploy_acceptance_passed`;
  - public health remained
    `{"status":"ok","service":"brc_operator_console","runtime_bound":true,"live_ready":false}`.
- AVAX runtime next-attempt gate verification:
  - runtime: `strategy-runtime-95655873b76c`;
  - lifecycle classification: `closed_reviewed`;
  - PG active position count: `0`;
  - PG open order count: `0`;
  - exchange position count: `0`;
  - exchange open protection count: `0`;
  - gate: `clear_for_next_preflight`;
  - status: `clear_for_preflight`;
  - blockers: none;
  - JIT lifecycle audit decision: `continue_to_owner_budget_final_gate`;
  - `can_continue_to_authorization=true`;
  - `can_execute_live=false`.
- Safety:
  - this stage only proves the runtime may move into fresh Owner/Budget
    authorization and official FinalGate preflight;
  - it does not authorize live submit, create an ExecutionIntent, place an
    order, call OrderLifecycle, withdraw funds, or transfer funds.

## 2026-06-11 (Runtime Next-attempt Prepare Wrapper)

- Added and pushed `85b340ce feat(ops): add runtime next-attempt prepare flow`.
- New script:
  `scripts/runtime_next_attempt_prepare_api_flow.py`.
- Purpose:
  - provide a clearly named next-attempt prepare entrypoint after a runtime has
    passed the post-close / closed-review / next-attempt gate;
  - reuse the existing official `runtime_first_real_submit_api_flow.py`
    prepare mode instead of creating a separate execution path;
  - make the second-and-later attempt path explicit for operators and future
    agents.
- Allowed effects:
  - may create the next attempt's shadow candidate when given a strategy signal
    input;
  - may create `RuntimeExecutionIntentDraft`, recorded `ExecutionIntent`,
    protection plan, and submit authorization records through the official
    Trading Console API.
- Forbidden effects:
  - no local registration arm;
  - no exchange submit arm;
  - no attempt reservation / mutation;
  - no OrderLifecycle call;
  - no exchange write;
  - no order creation;
  - no withdrawal or transfer.
- Output semantics:
  - success status is `ready_for_final_gate_preflight`;
  - the next step is `run_official_final_gate_preflight`;
  - `live_submit_allowed=false`;
  - explicit Owner real-submit authorization remains required for any later
    real gateway action.
- Tests:
  - `pytest -q tests/unit/test_runtime_next_attempt_prepare_api_flow.py
    tests/unit/test_runtime_next_attempt_gate_packet_script.py
    tests/unit/test_runtime_first_real_submit_api_flow.py` passed with
    `19 passed`;
  - `python3 -m py_compile scripts/runtime_next_attempt_prepare_api_flow.py`
    passed.
- Deployment:
  - not deployed in this stage;
  - deploy only when the wrapper is needed on Tokyo for an actual next-attempt
    prepare run.

## 2026-06-11 (Runtime Strategy Signal Input Packet)

- Added and pushed `28b9cc20 feat(ops): add runtime strategy signal input
  packet`.
- New script:
  `scripts/build_runtime_strategy_signal_input_packet.py`.
- Purpose:
  - build one `StrategyFamilySignalInput` for an existing active runtime;
  - default to Binance USD-M public closed candles through a read-only source;
  - evaluate the signal through `RuntimeStrategySignalEvaluationService`;
  - output a signal-input JSON file that can feed the next-attempt prepare
    wrapper only when the evaluator reaches `READY_FOR_SEMANTIC_BINDING`.
- Safety model:
  - account facts inside the generated signal input are explicit placeholders;
  - candidate planning must replace them through the trusted runtime fact
    overlay before any shadow candidate can be created;
  - the script does not create `SignalEvaluation`, `OrderCandidate`,
    `ExecutionIntent`, orders, runtime mutations, withdrawals, or transfers.
- Tests:
  - `pytest -q tests/unit/test_runtime_strategy_signal_input_packet_script.py
    tests/unit/test_runtime_next_attempt_prepare_api_flow.py
    tests/unit/test_runtime_next_attempt_gate_packet_script.py
    tests/unit/test_runtime_strategy_signal_evaluation_service.py
    tests/unit/test_reference_price_action_evaluators.py` passed with
    `24 passed`;
  - `python3 -m py_compile
    scripts/build_runtime_strategy_signal_input_packet.py
    scripts/runtime_next_attempt_prepare_api_flow.py` passed.
- Tokyo deploy:
  - deployed `28b9cc20dbb56d844482acada1034676a5958250` to
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-28b9cc20-20260611Tsignalinput`;
  - deploy result was `status=applied`;
  - postdeploy acceptance returned `postdeploy_acceptance_passed`;
  - public health remained
    `{"status":"ok","service":"brc_operator_console","runtime_bound":true,"live_ready":false}`.
- AVAX/BTPC live read-only signal check:
  - runtime: `strategy-runtime-95655873b76c`;
  - strategy: `BTPC-001` / `BTPC-001-v0`;
  - source: `binance_usdm_public_klines_read_only`;
  - output signal input path:
    `/home/ubuntu/brc-deploy/reports/runtime-strategy-signal-input/avax-btpc-next-attempt-signal-input.json`;
  - status: `observe_only`;
  - evaluator: `BTPC001PriceActionEvaluator`;
  - reason: `strategy_signal_not_would_enter`;
  - evaluator output signal type: `no_action`;
  - reason code: `btpc_no_action_no_bear_pullback_continuation`;
  - market state: `UNCERTAIN`;
  - BTPC did not confirm bear-trend pullback continuation on the latest closed
    candle.
- Safety:
  - no shadow candidate was created;
  - no execution intent was created;
  - no order or OrderLifecycle call occurred;
  - no exchange write, withdrawal, transfer, or runtime state mutation
    occurred.
- Product implication:
  - the repeat-attempt chain is now connected up to real read-only market
    signal evaluation;
  - because the current BTPC signal is observe-only, the correct next runtime
    behavior is to wait for the next closed bar or evaluate another eligible
    strategy/runtime rather than forcing a candidate.

## 2026-06-12 (Active Runtime Observation + Non-executing Prepare Watch)

- Added and pushed the active observation packet/status chain:
  - `6f9f02e9 feat(ops): summarize active observation packets`;
  - `0107d99d feat(ops): write active observation status packets`;
  - `4995b0f5 fix(ops): surface prepare-ready observation followup`;
  - `908bd28e fix(ops): allow direct active observation supervisor execution`;
  - `2635c75f fix(ops): refresh active observation status each loop`;
  - `bb40a7ea fix(ops): include latest active observation iteration`.
- Latest verification-only commit:
  - `aad19669 test(ops): prove ready observation followup stays disabled`.
- New/updated scripts:
  - `scripts/runtime_active_observation_monitor.py`;
  - `scripts/runtime_active_observation_loop.py`;
  - `scripts/runtime_active_observation_supervisor.py`;
  - `scripts/runtime_active_observation_followup.py`;
  - `scripts/runtime_active_observation_status.py`;
  - `scripts/verify_runtime_observation_api_prepare_ready_rehearsal.py`;
  - `scripts/verify_strategy_observation_shadow_planning_rehearsal.py`.
- Purpose:
  - continuously observe current ACTIVE strategy runtimes through the official
    Trading Console/API path;
  - stop the loop when a real strategy signal reaches `ready_for_prepare` or
    `ready_for_final_gate_preflight`;
  - allow explicitly authorized non-executing prepare records, FinalGate/arm
    preview, and disabled first-real-submit smoke only after the earlier
    non-executing prerequisites are present;
  - keep real exchange submit, OrderLifecycle submit, executable
    first-real-submit, withdrawal, and transfer outside the authorized scope.
- Local rehearsal evidence:
  - `python3 scripts/verify_runtime_observation_api_prepare_ready_rehearsal.py`
    returned `rehearsal_passed`;
  - `python3 scripts/verify_strategy_observation_shadow_planning_rehearsal.py`
    returned `rehearsal_passed`;
  - ready signal without `allow_prepare_records` stops at `ready_for_prepare`
    and creates no prepare records;
  - ready signal with explicit prepare permission reaches
    `ready_for_final_gate_preflight` through shadow/prepare records only;
  - forbidden execution flags remained empty.
- Focused tests:
  - `pytest -q tests/unit/test_runtime_observation_api_prepare_ready_rehearsal.py
    tests/unit/test_runtime_active_observation_followup.py
    tests/unit/test_runtime_active_observation_status.py
    tests/unit/test_runtime_active_observation_loop.py
    tests/unit/test_runtime_active_observation_supervisor.py
    tests/unit/test_runtime_next_attempt_observation_api_prepare_flow.py`
    passed with `28 passed`;
  - `pytest -q tests/unit/test_runtime_active_observation_followup.py
    tests/unit/test_runtime_order_lifecycle_adapter_result.py::test_api_first_real_submit_action_controls_gateway_injection
    tests/unit/test_strategy_runtime_live_enablement.py` passed with
    `14 passed`;
  - `pytest -q tests/unit/test_runtime_active_observation_supervisor.py
    tests/unit/test_runtime_active_observation_loop.py
    tests/unit/test_runtime_active_observation_followup.py
    tests/unit/test_runtime_active_observation_status.py` passed with
    `23 passed`.
- Tokyo deploys:
  - deployed `4995b0f5` to
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-4995b0f5-20260612Tobs-status`;
  - deployed `908bd28e` to
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-908bd28e-20260612Tsupervisor-import`;
  - deployed `2635c75f` to
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-2635c75f-20260612Tstatus-refresh`;
  - deployed `bb40a7ea` to
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-bb40a7ea-20260612Tstatus-iteration`.
- Current Tokyo observation run:
  - report directory:
    `/home/ubuntu/brc-deploy/reports/runtime-active-observation-loop/20260612Tovernight-bb40a7ea`;
  - process command includes `--allow-prepare-records`,
    `--allow-arm-preview`, and `--allow-disabled-smoke`;
  - latest verified status: `waiting_for_signal`;
  - latest verified iteration: `3`;
  - `packet_stale=false`;
  - `forbidden_effects=[]`.
- Current runtime signal summaries:
  - `strategy-runtime-95655873b76c`, `AVAX/USDT:USDT`, short,
    `BTPC-001-v0`: `observe_only`, `no_action`,
    `btpc_no_action_no_bear_pullback_continuation`;
  - `strategy-runtime-e6138ad7c88f`, `BNB/USDT:USDT`, long,
    `CPM-001-v0`: `observe_only`, `no_action`,
    `cpm_no_action_no_reclaim` with `cpm_long_htf_trend_intact`.
- Safety:
  - no shadow candidate has been created from the live observation run yet;
  - no prepare authorization record has been created from the live observation
    run yet;
  - no exchange order, OrderLifecycle submit, executable first-real-submit,
    withdrawal, transfer, attempt mutation, or runtime-budget mutation occurred;
  - real exchange order placement remains blocked pending a separate explicit
    Owner authorization after prepare/preflight evidence exists.
- Product implication:
  - the current system is now waiting on a real strategy signal rather than a
    missing execution skeleton;
  - when a real signal becomes `ready_for_prepare`, the authorized path is
    shadow prepare -> FinalGate/arm preview -> disabled first-real-submit smoke;
  - actual exchange submit remains a later Owner-gated action point.

## 2026-06-12 (Runtime + Strategy-group Signal Watch Evidence)

- Added and pushed:
  - `fc059ee4 feat(ops): add strategy group readonly preview`;
  - `75e7eee4 feat(ops): add runtime strategy signal watch packet`.
- New scripts:
  - `scripts/preview_strategy_group_readonly_observation.py`;
  - `scripts/build_runtime_strategy_signal_watch_packet.py`.
- Purpose:
  - provide a pure preview command for the broader strategy-group signal shelf
    without login, PG writes, runtime resolver calls, shadow candidate creation,
    ExecutionIntent creation, order paths, or runtime mutation;
  - combine the ACTIVE runtime observation packet with the broader strategy
    preview so the operator can distinguish "execution chain blocked" from
    "market/strategy signals are simply not firing".
- Focused tests:
  - `pytest -q tests/unit/test_strategy_group_readonly_preview_script.py
    tests/unit/test_strategy_group_live_readonly_observation.py
    tests/unit/test_strategy_group_observation_script.py` passed with
    `25 passed`;
  - `pytest -q tests/unit/test_runtime_strategy_signal_watch_packet.py
    tests/unit/test_strategy_group_readonly_preview_script.py
    tests/unit/test_runtime_active_observation_status.py` passed with
    `11 passed`;
  - `python3 -m py_compile
    scripts/preview_strategy_group_readonly_observation.py
    scripts/build_runtime_strategy_signal_watch_packet.py` passed.
- Live public-market preview evidence:
  - source: `binance_usdm_public_klines_read_only`;
  - candidate count: `8`;
  - current signal count: `8`;
  - would-enter signal count: `0`;
  - no-action signal count: `8`;
  - invalid signal count: `0`;
  - forbidden effects: none.
- Runtime + strategy watch evidence built from the Tokyo ACTIVE observation
  status packet and live public klines:
  - watch status: `watching_no_signal`;
  - active runtime count: `2`;
  - latest runtime observation iteration: `6`;
  - runtime ready signal count: `0`;
  - strategy-group would-enter signal count: `0`;
  - strategy-group no-action signal count: `8`;
  - next step: `continue_active_runtime_observation`.
- Safety:
  - no PG observation row was written by the preview/watch packet;
  - no runtime resolver was called;
  - no shadow candidate, SignalEvaluation, ExecutionIntent, order, or
    OrderLifecycle action was created;
  - no exchange write, attempt counter mutation, runtime budget mutation,
    withdrawal, or transfer occurred.
- Product implication:
  - the current no-action state is now an evidence-backed market/strategy
    signal conclusion across both ACTIVE runtimes and the broader strategy
    shelf;
  - if this persists through the observation window, the next product question
    is strategy/runtime coverage review, not forcing execution.

## 2026-06-12 (Ready-Prepare Owner Gate + Tokyo Current-head Deploy)

- Added and pushed:
  - `c492f240 feat(ops): surface runtime prepare watch context`;
  - `5b815934 fix(ops): propagate observation preview forbidden effects`;
  - `77cae7a2 feat(ops): add ready prepare rehearsal owner gate`.
- Watch/observation improvements:
  - `scripts/build_runtime_strategy_signal_watch_packet.py` now surfaces
    `runtime_prepare_context`, including ready-for-prepare count,
    ready-for-final-gate-preflight count, prepared authorization ID, shadow
    candidate ID, allowed non-executing follow-ups, and forbidden follow-ups;
  - `scripts/runtime_active_observation_supervisor.py` now propagates arm
    preview forbidden effects and direct real-submit / execution-intent /
    OrderLifecycle flags from child packets into the supervisor packet;
  - `scripts/verify_runtime_observation_api_prepare_ready_rehearsal.py` now
    emits an Owner-readable ready-prepare rehearsal packet with `owner_gate`,
    `operator_command_plan`, right-tail objective context, and `--output-json`.
- Focused verification:
  - `pytest -q tests/unit/test_runtime_strategy_signal_watch_packet.py
    tests/unit/test_strategy_group_readonly_preview_script.py
    tests/unit/test_runtime_active_observation_status.py` passed with
    `13 passed`;
  - `pytest -q tests/unit/test_runtime_active_observation_supervisor.py
    tests/unit/test_runtime_active_observation_followup.py
    tests/unit/test_runtime_active_observation_status.py
    tests/unit/test_runtime_strategy_signal_watch_packet.py` passed with
    `27 passed`;
  - `pytest -q tests/unit/test_runtime_observation_api_prepare_ready_rehearsal.py
    tests/unit/test_runtime_next_attempt_observation_api_prepare_flow.py
    tests/unit/test_runtime_active_observation_followup.py
    tests/unit/test_runtime_strategy_signal_watch_packet.py` passed with
    `22 passed`;
  - `python3 -m py_compile` passed for the touched observation/watch/rehearsal
    scripts.
- Tokyo git deploy:
  - deployed current branch head `77cae7a2` to
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-77cae7a2-20260612Tready-prepare-owner-gate`;
  - `/home/ubuntu/brc-deploy/app/current` now points to that release;
  - deploy execution status: `applied`;
  - command count: `16/16`;
  - database backup created: `true`;
  - migrations run: `true`;
  - services restarted: `true`;
  - health: `{"status":"ok","service":"brc_operator_console","runtime_bound":true,"live_ready":false}`;
  - postdeploy acceptance: `postdeploy_acceptance_passed`;
  - exchange called: `false`;
  - execution intent created: `false`;
  - order created: `false`;
  - OrderLifecycle called: `false`.
- Active observation after deploy:
  - the existing overnight observation process remains running from the older
    `bb40a7ea` release path, so the deploy did not interrupt the observation
    loop;
  - current-head status script read the same report directory and reported
    `waiting_for_signal`, latest iteration `9`, `stop_reason=running`,
    `observation_running=true`, and `forbidden_effects=[]`;
  - no prepared authorization ID and no shadow candidate ID exist yet.
- Deployed ready-prepare rehearsal:
  - running the new deployed script from `/home/ubuntu/brc-deploy/app/current`
    produced `rehearsal_passed`;
  - dry run stops at `ready_for_prepare` before records;
  - explicit prepare permission reaches `ready_for_final_gate_preflight`;
  - generated prepared authorization ID in rehearsal:
    `auth-ready-rehearsal`;
  - `real_submit_authorized=false`;
  - allowed after a real ready signal: shadow SignalEvaluation, shadow
    OrderCandidate, prepare authorization record, FinalGate preview, arm
    preview, and disabled first-real-submit smoke;
  - still requires separate Owner authorization for executable
    first-real-submit, exchange order placement, and OrderLifecycle submit.
- Safety:
  - this deployment and rehearsal did not place exchange orders;
  - it did not call OrderLifecycle;
  - it did not authorize executable first-real-submit;
  - it did not create withdrawal or transfer instructions;
  - right-tail small-risk-capital semantics remain expressed as bounded
    experimentation: small bounded losses are allowed, but unbounded or
    unreviewable execution is forbidden.

## 2026-06-12 (Active Observation Switched To Current Release)

- Operational change:
  - stopped the older overnight observation supervisor/loop that was still
    running from
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-bb40a7ea-20260612Tstatus-iteration`;
  - before stopping, old observation status was `waiting_for_signal`, latest
    iteration `10`, `forbidden_effects=[]`, no prepared authorization ID, and
    no shadow candidate ID;
  - started a new overnight observation supervisor from current deployed
    release
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-77cae7a2-20260612Tready-prepare-owner-gate`;
  - new report directory:
    `/home/ubuntu/brc-deploy/reports/runtime-active-observation-loop/20260612Tovernight-77cae7a2`;
  - new supervisor PID: `4016306`.
- New current-release observation status:
  - status: `waiting_for_signal`;
  - latest iteration: `1`;
  - iterations requested: `87`;
  - iterations remaining: `86`;
  - stop reason: `running`;
  - packet stale: `false`;
  - prepared authorization ID: `null`;
  - shadow candidate ID: `null`;
  - forbidden effects: `[]`.
- Current-release runtime + strategy watch packet:
  - watch status: `watching_no_signal`;
  - active runtime count: `2`;
  - runtime ready signal count: `0`;
  - strategy-group would-enter signal count: `0`;
  - strategy-group no-action signal count: `8`;
  - allowed next action: `continue_active_runtime_observation`;
  - allowed non-executing follow-ups if a real ready signal appears:
    shadow SignalEvaluation, shadow OrderCandidate, prepare authorization
    record, FinalGate preview, arm preview, and disabled first-real-submit
    smoke;
  - forbidden follow-ups remain executable ExecutionIntent, OrderLifecycle
    submit, executable first-real-submit, exchange order placement, withdrawal,
    and transfer.
- Safety:
  - no parallel active observation loop remains for the old report directory;
  - the switch did not create a shadow candidate, prepare record,
    ExecutionIntent, order, OrderLifecycle submit, exchange write, attempt
    mutation, runtime-budget mutation, withdrawal, or transfer;
  - the current live observation path now uses the latest deployed
    non-executing prepare/watch/supervisor audit behavior.

## 2026-06-12 (Night Non-executing Observation Authorization + Operator Packet Deploy)

- Owner night authorization scope:
  - allowed continued live read-only observation for current ACTIVE runtimes;
  - allowed shadow SignalEvaluation, shadow OrderCandidate, and prepare
    authorization records only when a real strategy signal becomes
    `ready_for_prepare`;
  - allowed FinalGate preview, arm preview, and disabled first-real-submit
    smoke;
  - still forbids real exchange orders, OrderLifecycle submit, executable
    first-real-submit, withdrawal, and transfer.
- Added and pushed before deployment:
  - `0f190f95 feat(ops): add no-signal diagnostic packet`;
  - `190ac471 feat(ops): add observation operator packet`.
- Tokyo git deploy:
  - deployed branch head `190ac471` to
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-190ac471-20260612Toperator-packet`;
  - `/home/ubuntu/brc-deploy/app/current` now points to that release;
  - deploy execution status: `applied`;
  - command count: `16/16`;
  - database backup created: `true`;
  - migrations run: `true`;
  - services restarted: `true`;
  - health smoke passed at `/api/health` with
    `{"status":"ok","service":"brc_operator_console","runtime_bound":true,"live_ready":false}`;
  - postdeploy read-only acceptance passed;
  - exchange called: `false`;
  - execution intent created: `false`;
  - order created: `false`;
  - OrderLifecycle called: `false`;
  - secrets read by Codex: `false`.
- Active overnight observation after deploy:
  - stopped the prior `77cae7a2` observation loop after confirming status
    `waiting_for_signal`, latest iteration `10`, prepared authorization ID
    `null`, shadow candidate ID `null`, and `forbidden_effects=[]`;
  - started a new overnight observation supervisor from
    `/home/ubuntu/brc-deploy/app/current` (`190ac471`) so the live night
    observation command includes `--allow-prepare-records`,
    `--allow-arm-preview`, and `--allow-disabled-smoke`;
  - new report directory:
    `/home/ubuntu/brc-deploy/reports/runtime-active-observation-loop/20260612Tovernight-190ac471`;
  - new supervisor PID: `4031504`;
  - status packet: `waiting_for_signal`;
  - latest iteration: `1`;
  - iterations requested: `77`;
  - iterations remaining: `76`;
  - stop reason: `running`;
  - prepared authorization ID: `null`;
  - shadow candidate ID: `null`;
  - forbidden effects: `[]`.
- Deployed operator packet evidence:
  - output path:
    `/home/ubuntu/brc-deploy/reports/runtime-active-observation-loop/20260612Tovernight-190ac471/operator-packet.json`;
  - status: `observation_running_no_signal`;
  - watch status: `watching_no_signal`;
  - diagnostic status: `no_signal_observation_running`;
  - active runtime count: `2`;
  - active runtime families: `BTPC-001`, `CPM-001`;
  - broader strategy preview families: `BRF-001`, `BTPC-001`,
    `CPM-RO-001`, `LSR-001`, `MI-001`, `RBR-001`, `VCB-001`;
  - runtime ready signal count: `0`;
  - strategy-group would-enter signal count: `0`;
  - strategy-group no-action signal count: `8`;
  - allowed next action: `continue_active_runtime_observation`.
- Safety:
  - the operator packet is read-only and does not write PG observation rows;
  - it does not call runtime resolver;
  - it does not create shadow candidate, SignalEvaluation, ExecutionIntent,
    order, OrderLifecycle submit, exchange write, withdrawal, or transfer;
  - current no-signal state is an observation result, not a strategy failure
    and not a reason to force entry.

## 2026-06-12 (Owner Wake-up Observation Handoff Packet)

- Added a local non-executing Owner wake-up packet builder:
  - `scripts/build_runtime_observation_wakeup_packet.py`;
  - `tests/unit/test_runtime_observation_wakeup_packet.py`.
- Purpose:
  - consume an existing runtime observation operator packet;
  - summarize whether Owner attention is needed now, whether observation can
    continue while Owner is away, and which actions still require Owner before
    any real submit;
  - keep no-signal as a valid observation state, not as a reason to force
    entry.
- Current Tokyo operator-packet input produced:
  - status: `owner_sleep_safe_observation_running`;
  - owner attention: `no_owner_action_needed_now`;
  - next step: `continue_active_runtime_observation`;
  - active runtime count: `2`;
  - runtime ready signal count: `0`;
  - strategy-group would-enter signal count: `0`;
  - strategy-group no-action signal count: `8`;
  - prepared authorization ID: `null`;
  - shadow candidate ID: `null`;
  - source forbidden effects: `[]`.
- Focused verification:
  - `pytest -q tests/unit/test_runtime_observation_wakeup_packet.py
    tests/unit/test_runtime_observation_operator_packet.py
    tests/unit/test_runtime_no_signal_diagnostic_packet.py` passed with
    `13 passed`;
  - `python3 -m py_compile
    scripts/build_runtime_observation_wakeup_packet.py
    scripts/build_runtime_observation_operator_packet.py
    scripts/build_runtime_no_signal_diagnostic_packet.py` passed.
- Safety:
  - the wake-up packet reads JSON only;
  - it does not call APIs, connect to PG, resolve runtimes, create shadow
    candidates, create ExecutionIntents, create orders, call OrderLifecycle,
    call exchange, mutate attempts/budget, withdraw, or transfer;
  - executable first-real-submit, exchange order placement, OrderLifecycle
    submit, withdrawal, and transfer remain Owner-authorized-only.

## 2026-06-12 (Wake-up Packet Tokyo Deploy + Remote Handoff Evidence)

- Tokyo git deploy:
  - deployed branch head `e70e318c` to
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-e70e318c-20260612Twakeup-packet`;
  - `/home/ubuntu/brc-deploy/app/current` now points to that release;
  - deploy execution status: `applied`;
  - command count: `16/16`;
  - database backup created: `true`;
  - migrations run: `true`;
  - services restarted: `true`;
  - exchange called: `false`;
  - execution intent created: `false`;
  - order created: `false`;
  - OrderLifecycle called: `false`;
  - secrets read by Codex: `false`.
- Remote observation status at handoff-packet build time:
  - source report directory:
    `/home/ubuntu/brc-deploy/reports/runtime-active-observation-loop/20260612Tovernight-190ac471`;
  - status: `waiting_for_signal`;
  - latest iteration: `10`;
  - iterations remaining: `67`;
  - stop reason: `running`;
  - prepared authorization ID: `null`;
  - shadow candidate ID: `null`;
  - forbidden effects: `[]`.
- Remote packets generated from current deployed release:
  - operator packet:
    `/home/ubuntu/brc-deploy/reports/runtime-active-observation-loop/20260612Tovernight-190ac471/operator-packet-e70e318c.json`;
  - wake-up packet:
    `/home/ubuntu/brc-deploy/reports/runtime-active-observation-loop/20260612Tovernight-190ac471/wakeup-packet-e70e318c.json`.
- Remote wake-up packet conclusion:
  - status: `owner_sleep_safe_observation_running`;
  - owner attention: `no_owner_action_needed_now`;
  - next step: `continue_active_runtime_observation`;
  - active runtime count: `2`;
  - runtime ready signal count: `0`;
  - strategy-group would-enter signal count: `0`;
  - strategy-group no-action signal count: `8`;
  - allowed while Owner is away: `continue_active_runtime_observation`;
  - source forbidden effects: `[]`.
- Safety:
  - this deployment and packet generation did not create shadow candidates,
    prepare authorization records, ExecutionIntents, orders, OrderLifecycle
    submits, exchange writes, withdrawals, or transfers;
  - first-real-submit remains blocked until a separate explicit Owner action
    authorization and live submit evidence review.

## 2026-06-12 (Runtime Coverage Review Packet)

- Added a local non-executing ACTIVE runtime coverage review packet builder:
  - `scripts/build_runtime_coverage_review_packet.py`;
  - `tests/unit/test_runtime_coverage_review_packet.py`.
- Purpose:
  - consume an existing runtime observation operator packet;
  - compare ACTIVE runtime strategy/symbol coverage with the broader
    read-only strategy preview shelf;
  - summarize no-action reason codes and whether a no-signal window should
    lead to coverage review;
  - explicitly avoid starting runtimes, changing strategy parameters, creating
    candidates, creating ExecutionIntents, placing orders, calling
    OrderLifecycle, or moving funds.
- Current Tokyo-derived coverage review input:
  - source operator packet:
    `/home/ubuntu/brc-deploy/reports/runtime-active-observation-loop/20260612Tovernight-190ac471/operator-packet-3d2e744c.json`;
  - observation iteration: `21/77`;
  - runtime ready signal count: `0`;
  - strategy-group would-enter signal count: `0`;
  - strategy-group no-action signal count: `8`;
  - active runtime families: `BTPC-001`, `CPM-001`;
  - broader preview families: `BRF-001`, `BTPC-001`, `CPM-RO-001`,
    `LSR-001`, `MI-001`, `RBR-001`, `VCB-001`;
  - coverage ratio: `2/7`;
  - uncovered preview families: `BRF-001`, `CPM-RO-001`, `LSR-001`,
    `MI-001`, `RBR-001`, `VCB-001`;
  - packet status: `coverage_review_observation_running`;
  - allowed next actions: continue active runtime observation and review
    coverage if no-signal persists;
  - source forbidden effects: `[]`.
- Focused verification:
  - `pytest -q tests/unit/test_runtime_coverage_review_packet.py
    tests/unit/test_runtime_observation_operator_packet.py
    tests/unit/test_runtime_no_signal_diagnostic_packet.py` passed with
    `13 passed`;
  - `python3 -m py_compile
    scripts/build_runtime_coverage_review_packet.py
    scripts/build_runtime_observation_operator_packet.py
    scripts/build_runtime_no_signal_diagnostic_packet.py` passed.
- Safety:
  - the coverage review packet reads JSON only;
  - it does not call APIs, connect to PG, start runtimes, resolve runtimes,
    change strategy parameters, create shadow candidates, create
    ExecutionIntents, create orders, call OrderLifecycle, call exchange,
    mutate attempts/budget, withdraw, or transfer;
  - future runtime coverage expansion remains an Owner/Codex review decision,
    not an automatic side effect of a no-signal window.

## 2026-06-13 (RTF-036 Runtime Profile Decision Packet)

- Added a local non-mutating Owner/Codex runtime profile decision packet
  builder:
  - `scripts/runtime_profile_decision_packet.py`;
  - `tests/unit/test_runtime_profile_decision_packet.py`.
- Purpose:
  - consume the RTF-035 non-runtime signal profile proposal packet;
  - freeze the selected `ExperimentalRuntimeProfileProposal` into a
    promotion-confirmation request template;
  - preview the existing strategy runtime promotion gate;
  - emit the follow-up runtime-draft API request template;
  - avoid manual JSON assembly for the future Owner/Codex confirmation step.
- Current local artifact:
  - input proposal:
    `output/rtf035-tokyo/non-runtime-signal-profile-proposal.json`;
  - output decision packet:
    `output/rtf036-local/runtime-profile-decision-packet.json`;
  - status: `ready_for_owner_codex_runtime_profile_confirmation`;
  - strategy: `RBR-001` / `RBR-001-v0`;
  - symbol / side: `ADA/USDT:USDT` / `short`;
  - promotion gate preview:
    `ready_for_controlled_runtime_execution_design`;
  - trial binding supplied: `false`.
- Profile-boundary preview:
  - capital base: `30`;
  - total loss budget: `6.00`;
  - max loss per attempt: `2.00`;
  - max notional per attempt: `8.00`;
  - max attempts: `3`;
  - max active positions: `1`;
  - max leverage: `1`;
  - protection / review required: `true`.
- Fixed a confirmation-key gap:
  - short-side profile proposals now expose
    `short_side_conservative_profile_confirmed`;
  - RTF-036 also upgrades older RTF-035 JSON artifacts that were produced
    before that key existed.
- Focused verification:
  - `pytest -q tests/unit/test_experimental_runtime_profile_proposal.py
    tests/unit/test_runtime_non_runtime_signal_profile_proposal.py
    tests/unit/test_runtime_profile_decision_packet.py
    tests/unit/test_strategy_runtime_promotion_confirmation_api.py`
    passed with `20 passed`.
- Safety:
  - RTF-036 creates no promotion confirmation record;
  - it does not write PG;
  - it does not create or enable a runtime;
  - it does not create `SignalEvaluation`, `OrderCandidate`,
    `ExecutionIntent`, local orders, or exchange orders;
  - it does not call `OrderLifecycle`, exchange write APIs, withdrawals, or
    transfers.

## 2026-06-13 (RTF-037 Runtime Profile Confirmation Apply Packet)

- Added a local non-mutating runtime profile confirmation apply packet builder:
  - `scripts/runtime_profile_confirmation_apply_packet.py`;
  - `tests/unit/test_runtime_profile_confirmation_apply_packet.py`.
- Purpose:
  - consume the RTF-036 runtime profile decision packet;
  - derive the exact Owner confirmation value required for the RBR/ADA short
    runtime profile;
  - require a concrete `trial_binding_id` before any runtime-draft API request
    can be considered ready;
  - prepare the two official API requests needed after Owner/Codex confirmation:
    1. `POST /api/brc/strategy-runtime-promotion-confirmations`;
    2. `POST /api/brc/strategy-runtime-promotion-confirmations/{id}/runtime-drafts`;
  - avoid manual request assembly for profile confirmation and shadow runtime
    draft creation.
- Current local artifact:
  - input decision packet:
    `output/rtf036-local/runtime-profile-decision-packet.json`;
  - output apply packet:
    `output/rtf037-local/runtime-profile-confirmation-apply-packet.json`;
  - status: `waiting_for_owner_runtime_profile_confirmation`;
  - required Owner confirmation value:
    `runtime-profile-confirm:RBR-001:RBR-001-v0:ADA/USDT:USDT:short:budget=6.00:notional=8.00:attempts=3:owner-authorized`;
  - API apply plan: `null` until the confirmation value matches and a
    `trial_binding_id` is supplied.
- Focused verification:
  - `pytest -q tests/unit/test_runtime_profile_decision_packet.py
    tests/unit/test_runtime_profile_confirmation_apply_packet.py
    tests/unit/test_strategy_runtime_promotion_confirmation_api.py`
    passed with `16 passed`.
- Safety:
  - RTF-037 creates no promotion confirmation record;
  - it does not write PG;
  - it does not create, enable, or activate a runtime;
  - it does not create `SignalEvaluation`, `OrderCandidate`,
    `ExecutionIntent`, local orders, or exchange orders;
  - it does not call `OrderLifecycle`, exchange write APIs, withdrawals, or
    transfers.

## 2026-06-13 (RTF-038 Trial Binding Apply Readiness)

- Added a local read-only trial-binding resolver and apply-readiness packet
  builder:
  - `scripts/runtime_profile_trial_binding_apply_readiness.py`;
  - `tests/unit/test_runtime_profile_trial_binding_apply_readiness.py`.
- Purpose:
  - consume the RTF-037 profile-confirmation packet;
  - resolve a compatible `AdmissionTrialBinding` from a read-only trial-binding
    list;
  - carry the existing Owner confirmation value into the RTF-037 apply packet;
  - produce an apply-ready two-step API plan only when both the binding and
    confirmation are present;
  - avoid manual binding/request assembly before promotion confirmation and
    shadow runtime draft creation.
- RTF-037 continuity fix:
  - RTF-037 now carries `source_decision_packet` so downstream tools can
    recover the original promotion-confirmation and runtime-draft templates;
  - RTF-038 accepts either the original RTF-036 decision packet or an RTF-037
    apply packet with embedded source decision.
- Current local artifact:
  - input apply packet:
    `output/rtf037-local/runtime-profile-confirmation-apply-packet.json`;
  - input local proof binding fixture:
    `output/rtf038-local/trial-bindings-fixture.json`;
  - output readiness packet:
    `output/rtf038-local/runtime-profile-trial-binding-apply-readiness.json`;
  - status: `ready_for_runtime_profile_apply_with_trial_binding`;
  - selected proof binding:
    `trial-binding-rbr-ada-short-local-proof`;
  - nested apply packet status:
    `ready_for_owner_authorized_runtime_profile_apply`.
- Focused verification:
  - `pytest -q tests/unit/test_runtime_profile_confirmation_apply_packet.py
    tests/unit/test_runtime_profile_trial_binding_apply_readiness.py
    tests/unit/test_strategy_runtime_promotion_confirmation_api.py`
    passed with `17 passed`.
- Safety:
  - RTF-038 reads binding JSON only;
  - it does not call APIs or write PG;
  - it does not create a promotion confirmation record;
  - it does not create, enable, or activate a runtime;
  - it does not create `SignalEvaluation`, `OrderCandidate`,
    `ExecutionIntent`, local orders, or exchange orders;
  - it does not call `OrderLifecycle`, exchange write APIs, withdrawals, or
    transfers.

## 2026-06-13 (RTF-039 Runtime Profile Apply Plan Dry-run)

- Added a guarded runtime profile apply plan executor:
  - `scripts/execute_runtime_profile_apply_plan.py`;
  - `tests/unit/test_execute_runtime_profile_apply_plan.py`.
- Purpose:
  - consume an RTF-038 apply-readiness packet;
  - dry-run the two official API requests required to record a promotion
    confirmation and create an execution-disabled shadow runtime draft;
  - require `--mode apply --execute` before any API call can occur;
  - reject apply plans with extra requests, non-POST methods, exchange paths,
    missing ready status, or order/exchange side effects.
- Current local artifact:
  - input readiness packet:
    `output/rtf038-local/runtime-profile-trial-binding-apply-readiness.json`;
  - output dry-run report:
    `output/rtf039-local/runtime-profile-apply-plan-dry-run.json`;
  - status: `dry_run_runtime_profile_apply_plan_ready`;
  - planned request count: `2`;
  - API called: `false`;
  - runtime created: `false`;
  - exchange write called: `false`.
- Focused verification:
  - `pytest -q tests/unit/test_execute_runtime_profile_apply_plan.py
    tests/unit/test_runtime_profile_trial_binding_apply_readiness.py
    tests/unit/test_strategy_runtime_promotion_confirmation_api.py`
    passed with `17 passed`.
- Safety:
  - default mode is dry-run and performs no API call;
  - apply mode requires `--execute`;
  - allowed apply requests are limited to:
    1. `POST /api/brc/strategy-runtime-promotion-confirmations`;
    2. `POST /api/brc/strategy-runtime-promotion-confirmations/{id}/runtime-drafts`;
  - it does not call `OrderLifecycle`, exchange write APIs, withdrawals, or
    transfers.

## 2026-06-13 (RTF-040 Tokyo Deploy And Real Trial-Binding Probe)

- Pushed `program/live-safe-v1` to origin at commit `9637e861`.
- Deployed Tokyo git release:
  - release name:
    `brc-runtime-governance-9637e861-20260613Trtf040-profile-apply-dryrun`;
  - remote release path:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-9637e861-20260613Trtf040-profile-apply-dryrun`;
  - deployment execution status: `applied`;
  - remote deploy commands executed: `16`.
- Postdeploy read-only probe:
  - output:
    `output/rtf040-local/postdeploy-readonly-probe.json`;
  - status: `ready_for_controlled_deploy_preflight`;
  - current deployed head: `9637e861`;
  - health HTTP status: `200`;
  - migration count: `84`;
  - latest migration:
    `2026-06-11-084_create_runtime_post_submit_budget_settlements.py`;
  - blockers: `[]`.
- Read Tokyo real trial bindings through authenticated read-only API:
  - output:
    `output/rtf040-tokyo/trial-bindings.json`;
  - HTTP status: `200`;
  - count: `4`.
- Real trial-binding readiness result:
  - output:
    `output/rtf040-tokyo/runtime-profile-trial-binding-apply-readiness.json`;
  - status: `waiting_for_matching_trial_binding`;
  - blocker: `matching_trial_binding_not_found`;
  - observed versions:
    - `BTPC-001-v0`;
    - `CPM-001-v0`;
  - required version for the RBR/ADA profile:
    `RBR-001-v0`.
- Tokyo RTF-039 dry-run result:
  - output:
    `output/rtf040-tokyo/runtime-profile-apply-plan-dry-run.json`;
  - status: `blocked_runtime_profile_apply_plan`;
  - blockers:
    - `api_apply_plan_not_ready`;
    - `rtf038_apply_readiness_packet_not_ready`;
  - API called: `false`;
  - runtime created: `false`;
  - exchange write called: `false`.
- Executor cleanup:
  - `scripts/execute_runtime_profile_apply_plan.py` now reports missing
    apply-plan state as `api_apply_plan_not_ready` without noisy side-effect
    shape blockers.
- Focused verification:
  - `pytest -q tests/unit/test_execute_runtime_profile_apply_plan.py
    tests/unit/test_runtime_profile_trial_binding_apply_readiness.py
    tests/unit/test_strategy_runtime_promotion_confirmation_api.py`
    passed with `18 passed`.
- Safety:
  - RTF-040 deployment did not create `SignalEvaluation`, `OrderCandidate`,
    `ExecutionIntent`, orders, or exchange requests;
  - Tokyo trial-binding read used authenticated read-only API access;
  - no promotion confirmation was recorded;
  - no runtime draft was created because the matching `RBR-001-v0` trial
    binding is absent;
  - no `OrderLifecycle`, exchange write, withdrawal, or transfer path was
    called.

## 2026-06-13 (RTF-041 RBR Trial Binding Reservation)

- Added `binding-only` mode to `scripts/runtime_live_bootstrap_api_flow.py`.
- Purpose:
  - create / confirm BRC admission facts and reserve an
    `AdmissionTrialBinding`;
  - stop immediately after binding reservation;
  - avoid runtime profile proposal preview, promotion confirmation creation,
    runtime draft creation, runtime activation, order candidates,
    ExecutionIntents, orders, OrderLifecycle, exchange writes, withdrawals,
    or transfers.
- Local verification:
  - `pytest -q tests/unit/test_runtime_live_bootstrap_api_flow.py`
    passed with `7 passed`;
  - `python3 -m py_compile scripts/runtime_live_bootstrap_api_flow.py`
    passed.
- Deployed Tokyo git release:
  - release name:
    `brc-runtime-governance-7fa42bbb-20260613Trtf041-binding-only`;
  - deployment execution status: `applied`;
  - remote deploy commands executed: `16`;
  - postdeploy probe status: `ready_for_controlled_deploy_preflight`;
  - deployed head: `7fa42bbb`;
  - health HTTP status: `200`.
- Ran Tokyo binding-only flow for the RBR/ADA profile:
  - output:
    `output/rtf041-tokyo/rbr-binding-only-flow.json`;
  - strategy: `RBR-001` / `RBR-001-v0`;
  - symbol / side: `ADA/USDT:USDT` / `short`;
  - blockers: `[]`;
  - ready for trial binding: `true`;
  - created trial binding:
    `admission-binding-e1115c1e2c6f`;
  - runtime instance ID: `null`;
  - creates runtime: `false`;
  - creates order: `false`.
- Re-read Tokyo real trial bindings:
  - output:
    `output/rtf041-tokyo/trial-bindings.json`;
  - HTTP status: `200`;
  - count: `5`;
  - `RBR-001-v0` now exists.
- Re-ran RTF-038 / RTF-039 against Tokyo facts:
  - readiness output:
    `output/rtf041-tokyo/runtime-profile-trial-binding-apply-readiness.json`;
  - readiness status:
    `ready_for_runtime_profile_apply_with_trial_binding`;
  - selected binding:
    `admission-binding-e1115c1e2c6f`;
  - dry-run output:
    `output/rtf041-tokyo/runtime-profile-apply-plan-dry-run.json`;
  - dry-run status:
    `dry_run_runtime_profile_apply_plan_ready`;
  - planned request count: `2`;
  - API called: `false`;
  - runtime created: `false`;
  - exchange write called: `false`.
- Safety:
  - RTF-041 created admission / trial-binding records through official API
    surfaces only;
  - no promotion confirmation was recorded;
  - no runtime draft was created;
  - no runtime was enabled or activated;
  - no `SignalEvaluation`, `OrderCandidate`, `ExecutionIntent`, local order,
    exchange order, `OrderLifecycle`, withdrawal, or transfer path was called.

## 2026-06-13 (RTF-042 Shadow Runtime Draft Apply And Probe)

- Executed the guarded Tokyo runtime profile apply plan from the RTF-041
  readiness packet.
- Apply input:
  - `output/rtf041-tokyo/runtime-profile-trial-binding-apply-readiness.json`;
  - selected trial binding:
    `admission-binding-e1115c1e2c6f`.
- Apply output:
  - `output/rtf042-tokyo/runtime-profile-apply-execution.json`;
  - status: `runtime_profile_apply_plan_applied`;
  - blockers: `[]`;
  - mode: `apply`;
  - execute requested: `true`.
- Official API requests executed:
  1. `POST /api/brc/strategy-runtime-promotion-confirmations`;
  2. `POST /api/brc/strategy-runtime-promotion-confirmations/{id}/runtime-drafts`.
- Created / confirmed Tokyo PG records:
  - promotion confirmation:
    `promotion-confirmation-rbr-001-rbr-001-v0-ada-usdt-usdt-short`;
  - strategy runtime draft:
    `strategy-runtime-rbr-001-rbr-001-v0-ada-usdt-usdt-short`.
- Runtime profile recorded:
  - strategy: `RBR-001` / `RBR-001-v0`;
  - symbol / side: `ADA/USDT:USDT` / `short`;
  - total loss budget: `6.00`;
  - max notional per attempt: `8.00`;
  - max attempts: `3`;
  - max active positions: `1`;
  - max leverage: `1`;
  - protection required: `true`;
  - review required: `true`.
- Ran Tokyo post-creation probe:
  - remote report:
    `/home/ubuntu/brc-deploy/app/current/reports/rtf042-post-creation/20260613Trtf042/post-creation-probe.json`;
  - local copy:
    `output/rtf042-tokyo/post-creation-probe.json`;
  - status: `rtf042_post_creation_probe_passed`;
  - blockers: `[]`;
  - runtime status: `draft`;
  - execution enabled: `false`;
  - shadow mode: `true`;
  - matching promotion confirmations: `1`;
  - safety readiness status: `blocked`;
  - live enablement preview status: `blocked`.
- Expected blockers while the runtime remains draft:
  - safety readiness blocks on `runtime_status_active`;
  - live enablement preview blocks on `runtime_not_active` and missing
    first-real-submit / final submit-chain evidence;
  - these blockers confirm the draft cannot silently become executable.
- Safety:
  - RTF-042 created only the promotion confirmation and execution-disabled
    shadow runtime draft through official API surfaces;
  - the post-creation probe was read-only;
  - no live runtime enablement mutation was applied;
  - no `SignalEvaluation`, `OrderCandidate`, `ExecutionIntent`, local order,
    exchange order, `OrderLifecycle`, withdrawal, or transfer path was called;
  - no exchange write occurred.

## 2026-06-13 (RTF-043 Shadow Runtime Activation And Planning Gate Probe)

- Executed the official runtime lifecycle API to activate the RBR/ADA runtime
  as a shadow runtime.
- Activation report:
  - remote report:
    `/home/ubuntu/brc-deploy/app/current/reports/rtf043-shadow-activation/20260613Trtf043/shadow-activation-probe.json`;
  - local copy:
    `output/rtf043-tokyo/shadow-activation-probe.json`;
  - status: `rtf043_shadow_runtime_activation_passed`;
  - blockers: `[]`;
  - before status: `draft`;
  - after status: `active`;
  - execution enabled: `false`;
  - shadow mode: `true`.
- Runtime activated:
  - runtime:
    `strategy-runtime-rbr-001-rbr-001-v0-ada-usdt-usdt-short`;
  - strategy: `RBR-001` / `RBR-001-v0`;
  - symbol / side: `ADA/USDT:USDT` / `short`.
- Post-activation readiness:
  - safety readiness status: `ready_for_owner_codex_confirmation`;
  - safety readiness blockers: `[]`;
  - live enablement preview status: `blocked`;
  - live enablement remains blocked because first-real-submit / final
    submit-chain evidence has not been supplied for this runtime.
- Ran the current-market live strategy signal selector:
  - remote report:
    `/home/ubuntu/brc-deploy/app/current/reports/rtf043-shadow-activation/20260613Trtf043/live-signal-selector.json`;
  - local copy:
    `output/rtf043-tokyo/live-signal-selector.json`;
  - status: `no_would_enter_signal_available`;
  - inspected signal count: `8`;
  - would-enter signal count: `0`;
  - selected signal: `null`;
  - expected blocker:
    `runtime_strategy_signal_not_found_in_strategy_shelf`.
- Built a current closed-candle signal input for the active runtime:
  - remote report:
    `/home/ubuntu/brc-deploy/app/current/reports/rtf043-shadow-activation/20260613Trtf043/current-signal-input-packet.json`;
  - local copy:
    `output/rtf043-tokyo/current-signal-input-packet.json`;
  - status: `observe_only`;
  - evaluation blocker: `strategy_signal_not_would_enter`;
  - output signal input:
    `/home/ubuntu/brc-deploy/app/current/reports/rtf043-shadow-activation/20260613Trtf043/current-rbr-ada-signal-input.json`.
- Called the Trading Console shadow-planning API with the current signal input:
  - remote report:
    `/home/ubuntu/brc-deploy/app/current/reports/rtf043-shadow-activation/20260613Trtf043/shadow-planning-gate-probe.json`;
  - local copy:
    `output/rtf043-tokyo/shadow-planning-gate-probe.json`;
  - status: `rtf043_shadow_planning_gate_probe_passed`;
  - HTTP status: `200`;
  - planning status: `observe_only`;
  - planning blocker: `strategy_signal_not_would_enter`;
  - planner call performed: `false`;
  - signal evaluation created: `false`;
  - order candidate created: `false`;
  - candidate planning result present: `false`.
- Safety:
  - RTF-043 mutated only the runtime shadow lifecycle status from `draft` to
    `active`;
  - runtime execution remains disabled;
  - current-market observation and signal-input building were read-only;
  - the shadow-planning API proved the semantic gate blocks observe-only input
    before candidate creation;
  - no `SignalEvaluation`, `OrderCandidate`, `ExecutionIntent`, local order,
    exchange order, `OrderLifecycle`, withdrawal, or transfer path was called;
  - no exchange write occurred.

## 2026-06-13 (RTF-044 Runtime Observation API Prepare Waiting State)

- Ran the official Trading Console runtime next-attempt observation API wrapper
  for the active RBR/ADA shadow runtime.
- Runtime:
  - `strategy-runtime-rbr-001-rbr-001-v0-ada-usdt-usdt-short`;
  - strategy: `RBR-001` / `RBR-001-v0`;
  - symbol / side: `ADA/USDT:USDT` / `short`;
  - runtime status before the probe: `active`;
  - execution enabled: `false`;
  - shadow mode: `true`.
- Tokyo observation API prepare flow:
  - remote report:
    `/home/ubuntu/brc-deploy/app/current/reports/rtf044-shadow-candidate-planning/20260613Trtf044/observation-api-prepare-flow.json`;
  - local copy:
    `output/rtf044-tokyo/observation-api-prepare-flow.json`;
  - status: `waiting_for_signal`;
  - blocked stage: `strategy_signal`;
  - blocker:
    `strategy_signal_not_ready_for_shadow_candidate_prepare`;
  - signal input JSON:
    `/home/ubuntu/brc-deploy/app/current/reports/rtf044-shadow-candidate-planning/20260613Trtf044/rbr-ada-observation-signal-input.json`.
- Meaning:
  - the active shadow runtime is reachable through the official observation API;
  - the strategy signal path is connected;
  - current market data does not produce a runtime-compatible `would_enter`
    signal;
  - the system correctly waits instead of creating a shadow candidate.
- Safety:
  - `allow_prepare_records`: `false`;
  - prepare records created: `false`;
  - shadow candidate created: `false`;
  - runtime execution intent draft created: `false`;
  - recorded execution intent created: `false`;
  - submit authorization created: `false`;
  - protection plan created: `false`;
  - local registration armed: `false`;
  - exchange submit armed: `false`;
  - execute real submit: `false`;
  - no order, `OrderLifecycle`, exchange write, position open/close,
    withdrawal, transfer, attempt counter mutation, or runtime budget mutation
    occurred.
- Focused local verification:
  - `pytest -q tests/unit/test_runtime_next_attempt_observation_api_prepare_flow.py
    tests/unit/test_runtime_next_attempt_observation_cycle_api.py
    tests/unit/test_runtime_next_attempt_observation_cycle.py`;
  - result: `15 passed`.

## 2026-06-13 (RTF-045 Ready Signal Monitor)

- Reused the existing runtime next-attempt observation monitor as the
  repeatable ready-signal capture loop for the active RBR/ADA shadow runtime.
- Runtime:
  - `strategy-runtime-rbr-001-rbr-001-v0-ada-usdt-usdt-short`;
  - strategy: `RBR-001` / `RBR-001-v0`;
  - symbol / side: `ADA/USDT:USDT` / `short`;
  - runtime status: `active`;
  - execution enabled: `false`;
  - shadow mode: `true`.
- Local proof:
  - `pytest -q tests/unit/test_runtime_next_attempt_observation_monitor.py
    tests/unit/test_runtime_next_attempt_observation_api_prepare_flow.py
    tests/unit/test_runtime_next_attempt_observation_cycle_api.py`;
  - result: `15 passed`.
- Tokyo monitor probe:
  - remote report:
    `/home/ubuntu/brc-deploy/app/current/reports/rtf045-ready-signal-monitor/20260613Trtf045/ready-signal-monitor.json`;
  - local copy:
    `output/rtf045-tokyo/ready-signal-monitor.json`;
  - status: `waiting_for_signal`;
  - cycles requested: `3`;
  - cycles completed: `3`;
  - ready for prepare: `false`;
  - ready for final gate preflight: `false`;
  - latest blocker:
    `strategy_signal_not_ready_for_shadow_candidate_prepare`.
- Cycle summaries:
  - cycle `1`: `waiting_for_signal`;
  - cycle `2`: `waiting_for_signal`;
  - cycle `3`: `waiting_for_signal`.
- Meaning:
  - the active shadow runtime can be monitored repeatedly through the official
    observation API path;
  - the monitor will stop when a runtime-compatible ready signal appears;
  - current market data still does not produce a ready RBR/ADA short signal;
  - the system correctly waits instead of creating candidate or submit records.
- Safety:
  - `allow_prepare_records`: `false`;
  - monitor only: `true`;
  - prepare records created: `false`;
  - shadow candidate created: `false`;
  - runtime execution intent draft created: `false`;
  - recorded execution intent created: `false`;
  - submit authorization created: `false`;
  - protection plan created: `false`;
  - local registration armed: `false`;
  - exchange submit armed: `false`;
  - execute real submit: `false`;
  - no order, `OrderLifecycle`, exchange write, position open/close,
    withdrawal, transfer, attempt counter mutation, or runtime budget mutation
    occurred.

## 2026-06-13 (RTF-046 Ready Prepare Rehearsal)

- Reused the existing ready-signal prepare rehearsal verifier:
  - `scripts/verify_runtime_observation_api_prepare_ready_rehearsal.py`.
- Purpose:
  - prove that a ready observation payload stops at `ready_for_prepare` when
    prepare records are not explicitly allowed;
  - prove that the same ready observation can reach
    `ready_for_final_gate_preflight` when prepare records are explicitly
    allowed;
  - prove the path still does not submit, call `OrderLifecycle`, call exchange,
    mutate attempts or budget, or move funds.
- Local rehearsal artifact:
  - `output/rtf046-local/ready-prepare-rehearsal.json`;
  - status: `rehearsal_passed`;
  - prepared authorization ID: `auth-ready-rehearsal`;
  - real submit authorized: `false`.
- Tokyo rehearsal artifact:
  - remote report:
    `/home/ubuntu/brc-deploy/app/current/reports/rtf046-ready-prepare-rehearsal/20260613Trtf046/ready-prepare-rehearsal.json`;
  - local copy:
    `output/rtf046-tokyo/ready-prepare-rehearsal.json`;
  - status: `rehearsal_passed`;
  - prepared authorization ID: `auth-ready-rehearsal`;
  - real submit authorized: `false`.
- Checks:
  - ready signal rehearsed: `true`;
  - ready without allow stops before prepare: `true`;
  - explicit prepare permission reaches final gate preflight: `true`;
  - prepared authorization ID present: `true`;
  - forbidden execution flags: `[]`.
- Focused local verification:
  - `pytest -q tests/unit/test_runtime_observation_api_prepare_ready_rehearsal.py
    tests/unit/test_runtime_next_attempt_observation_api_prepare_flow.py
    tests/unit/test_runtime_next_attempt_observation_monitor.py`;
  - result: `13 passed`.
- Safety:
  - rehearsal is local / in-memory only;
  - database connected: `false`;
  - HTTP network called: `false`;
  - exchange called: `false`;
  - order created: `false`;
  - `OrderLifecycle` called: `false`;
  - real submit authorized: `false`;
  - withdrawal or transfer created: `false`;
  - attempt counter mutation and runtime budget mutation remain forbidden in
    the prepare rehearsal path.

## 2026-06-13 (RTF-047 Ready Shadow Candidate Boundary)

- Added local verifier:
  - `scripts/verify_runtime_ready_shadow_candidate_boundary.py`.
- Purpose:
  - prove the strategy signal planning node locally before Tokyo integration;
  - prove `READY_FOR_SEMANTIC_BINDING` strategy output can create only shadow
    `SignalEvaluation` / `OrderCandidate` records;
  - prove candidate planning includes entry, structure stop, TP1 partial,
    runner / trailing metadata, notional, quantity, leverage, margin, max-loss,
    liquidation reference, and liquidation-stop buffer previews;
  - prove non-trading strategy modes do not silently create candidates.
- Local artifact:
  - `output/rtf047-local/ready-shadow-candidate-boundary.json`;
  - status: `rtf047_ready_shadow_candidate_boundary_passed`;
  - scenario count: `5`.
- Scenarios:
  - `cpm-long-eth`: `CPM-RO-001` / `CPM-RO-001-v0`,
    `ETH/USDT:USDT`, `long`, `shadow_candidate_created`;
  - `brf-short-btc`: `BRF-001` / `BRF-001-v0`,
    `BTC/USDT:USDT`, `short`, `shadow_candidate_created`;
  - `cpm-short-mismatch`: blocked before candidate creation;
  - `rmr-classifier-no-trade`: observe-only, no candidate;
  - `fco-data-backlog-no-trade`: blocked, no candidate.
- Focused local verification:
  - `pytest -q tests/unit/test_runtime_ready_shadow_candidate_boundary.py
    tests/unit/test_b0_runtime_strategy_signal_planning.py
    tests/unit/test_runtime_strategy_signal_evaluation_service.py`;
  - result: `21 passed`.
- Safety:
  - local in-memory only: `true`;
  - database connected: `false`;
  - HTTP network called: `false`;
  - exchange write called: `false`;
  - `OrderLifecycle` called: `false`;
  - execution intent created: `false`;
  - order created: `false`;
  - withdrawal or transfer created: `false`.
- Deployment:
  - not deployed in this stage;
  - Tokyo remains for later integration probe / live-fact validation, not
    first-pass node debugging.

## 2026-06-13 (RTF-048 Runtime Post-submit Finalize Loop)

- Added local verifier:
  - `scripts/verify_runtime_post_submit_finalize_loop.py`.
- Purpose:
  - prove the runtime-level post-submit correction path locally;
  - resolve latest durable `RuntimeExecutionExchangeSubmitExecutionResult`
    by runtime without manually supplying the old authorization ID;
  - freeze the consumed authorization as replay-only evidence;
  - prevent the old attempt from going back through pre-submit rehearsal,
    local `CREATED` order checks, local order re-creation, or submit retry;
  - produce the next-attempt gate from post-submit facts.
- Local artifact:
  - `output/rtf048-local/post-submit-finalize-loop.json`;
  - status: `rtf048_runtime_post_submit_finalize_loop_passed`;
  - scenario count: `3`.
- Scenarios:
  - `latest-result-ready-for-fresh-signal`:
    `finalized_ready_for_next_attempt`,
    next gate `ready_for_fresh_signal`;
  - `latest-result-active-position-blocks-next-attempt`:
    `finalized_next_attempt_blocked`,
    next gate blocker `runtime_active_position_slot_in_use`;
  - `latest-result-missing-blocks-finalize`:
    `blocked`,
    blocker `latest_exchange_submit_execution_result_not_found`.
- Focused local verification:
  - `pytest -q tests/unit/test_runtime_post_submit_finalize_loop_verifier.py
    tests/unit/test_runtime_post_submit_finalize.py
    tests/unit/test_runtime_post_submit_finalize_probe.py
    tests/unit/test_runtime_post_submit_finalize_api_flow.py`;
  - result: `18 passed`.
- Safety:
  - local in-memory only: `true`;
  - database connected: `false`;
  - HTTP network called: `false`;
  - exchange write called: `false`;
  - pre-submit rehearsal called: `false`;
  - `OrderLifecycle` called: `false`;
  - execution intent created: `false`;
  - order created: `false`;
  - withdrawal or transfer created: `false`.
- Deployment:
  - not deployed in this stage;
  - Tokyo integration should only validate deployed code, PG facts, active
    position facts, and live-account facts after local node proof.

## 2026-06-13 (RTF-049 Next-attempt Gate Strategy Planning)

- Added local verifier:
  - `scripts/verify_runtime_next_attempt_gate_strategy_planning.py`.
- Purpose:
  - prove `RuntimePostSubmitFinalizePacket(next gate ready)` can enter fresh
    strategy-signal planning;
  - prove a ready post-submit gate plus fresh CPM signal reaches
    `ready_for_final_gate_preflight` with a shadow `OrderCandidate`;
  - prove a blocked post-submit next-attempt gate stops before strategy
    planning and does not call the planner;
  - prove observe-only strategy modes return `waiting_for_signal` instead of
    creating candidates.
- Local artifact:
  - `output/rtf049-local/next-attempt-gate-strategy-planning.json`;
  - status: `rtf049_next_attempt_gate_strategy_planning_passed`;
  - scenario count: `3`.
- Scenarios:
  - `ready-cpm-long`: post-submit gate `ready_for_fresh_signal`,
    strategy planning `ready_for_final_gate_preflight`,
    shadow candidate created;
  - `blocked-active-position`: post-submit gate blocked by
    `runtime_active_position_slot_in_use`, planner calls `0`;
  - `waiting-rmr-observe-only`: post-submit gate ready, planner called,
    strategy planning `waiting_for_signal`, no candidate.
- Focused local verification:
  - `pytest -q tests/unit/test_runtime_next_attempt_gate_strategy_planning_verifier.py
    tests/unit/test_runtime_next_attempt_strategy_planning.py
    tests/unit/test_runtime_post_submit_next_attempt_cycle.py
    tests/unit/test_runtime_ready_shadow_candidate_boundary.py`;
  - result: `15 passed`.
- Safety:
  - local in-memory only: `true`;
  - database connected: `false`;
  - HTTP network called: `false`;
  - exchange write called: `false`;
  - pre-submit rehearsal called: `false`;
  - `OrderLifecycle` called: `false`;
  - executable execution intent created: `false`;
  - order created: `false`;
  - withdrawal or transfer created: `false`.
- Execution semantics:
  - consumed authorization remains replay-only;
  - next submit still requires fresh strategy signal, fresh authorization,
    official FinalGate, and official submit path;
  - no one-shot first-real-submit retry is used in this stage.
- Deployment:
  - not deployed in this stage;
  - Tokyo should validate this only after local proof and selected deploy.

## 2026-06-13 (RTF-050 Next-attempt Submit-preparation Bridge)

- Added local verifier:
  - `scripts/verify_runtime_next_attempt_submit_preparation_bridge.py`.
- Purpose:
  - compose the RTF-049 next-attempt strategy-planning packet with the
    existing executable-submit readiness and official-submit handoff domain
    services;
  - prove a ready CPM next-attempt planning packet can reach
    `ready_for_executable_submit`;
  - prove a fresh submit authorization is still required before official
    submit handoff can become ready;
  - prove the handoff can prepare both disabled-smoke and real-gateway-action
    previews without calling the official submit endpoint;
  - prove active-position blocked and observe-only planning scenarios stop
    before readiness / handoff.
- Local artifact:
  - `output/rtf050-local/next-attempt-submit-preparation-bridge.json`;
  - status: `rtf050_next_attempt_submit_preparation_bridge_passed`;
  - scenario count: `3`.
- Scenarios:
  - `ready-cpm-long-submit-preparation`: strategy planning
    `ready_for_final_gate_preflight`, readiness
    `ready_for_executable_submit`, disabled handoff
    `ready_for_official_submit_call`;
  - `blocked-active-position-submit-preparation-blocked`: readiness not run,
    handoff not run, blocker `runtime_active_position_slot_in_use`;
  - `waiting-rmr-observe-only-submit-preparation-blocked`: readiness not run,
    handoff not run, observe-only strategy does not create a candidate.
- Focused local verification:
  - `pytest -q tests/unit/test_runtime_next_attempt_submit_preparation_bridge_verifier.py
    tests/unit/test_runtime_next_attempt_gate_strategy_planning_verifier.py
    tests/unit/test_runtime_executable_submit_readiness.py
    tests/unit/test_runtime_official_submit_handoff.py`;
  - result: `19 passed`.
- Safety:
  - local in-memory only: `true`;
  - database connected: `false`;
  - HTTP network called: `false`;
  - official submit endpoint called: `false`;
  - exchange write called: `false`;
  - pre-submit rehearsal called: `false`;
  - `OrderLifecycle` called: `false`;
  - execution intent created: `false`;
  - executable execution intent created: `false`;
  - order created: `false`;
  - runtime state mutated: `false`;
  - withdrawal or transfer created: `false`.
- Execution semantics:
  - old authorization remains consumed / replay-only;
  - historical pre-attempt rehearsal is compatibility evidence, not a current
    requirement;
  - durable execution result is treated as post-submit evidence only;
  - the next real submit still requires fresh authorization, current
    FinalGate/readiness evidence, and the official auditable submit path.
- Deployment:
  - not deployed in this stage;
  - this is local submit-preparation proof before Tokyo integration.

## 2026-06-13 (RTF-051 Official Submit Action-time Bridge)

- Added local verifier:
  - `scripts/verify_runtime_official_submit_action_time_bridge.py`.
- Purpose:
  - start from the RTF-050 official-submit handoff packet;
  - drive the existing disabled-smoke official first-real-submit flow with a
    fake API client;
  - prove the action-time `POST` method, official endpoint path, query evidence
    IDs, and `owner_confirmed_for_first_real_submit_action=false` contract;
  - prove disabled-smoke refuses a real-gateway-action handoff before any
    official endpoint call;
  - prove a disabled-smoke response that unexpectedly reports exchange submit
    enabled is blocked.
- Local artifact:
  - `output/rtf051-local/official-submit-action-time-bridge.json`;
  - status: `rtf051_official_submit_action_time_bridge_passed`;
  - scenario count: `3`.
- Scenarios:
  - `disabled-smoke-action-time-from-rtf050-handoff`: official endpoint
    contract exercised once through a fake client, status
    `disabled_smoke_passed`;
  - `real-gateway-handoff-refused-by-disabled-smoke`: blocked before endpoint
    call with `disabled_smoke_refuses_real_gateway_handoff`;
  - `disabled-smoke-enabled-response-blocked`: endpoint contract exercised
    once, then blocked by `disabled_smoke_response_enabled_exchange_submit`.
- Focused local verification:
  - `pytest -q tests/unit/test_runtime_official_submit_action_time_bridge_verifier.py
    tests/unit/test_runtime_next_attempt_submit_preparation_bridge_verifier.py
    tests/unit/test_runtime_official_submit_disabled_smoke_from_handoff.py
    tests/unit/test_runtime_first_real_submit_api_flow.py -k
    'official_submit_action_time_bridge or next_attempt_submit_preparation_bridge
    or disabled_smoke_from_handoff or disabled_smoke'`;
  - result: `13 passed, 19 deselected`.
- Safety:
  - local fake client only: `true`;
  - database connected: `false`;
  - HTTP network called: `false`;
  - official submit endpoint contract exercised: `true`;
  - real gateway action requested: `false`;
  - Owner confirmed real submit action: `false`;
  - exchange write called: `false`;
  - `OrderLifecycle` called: `false`;
  - execution intent created: `false`;
  - order created: `false`;
  - runtime state mutated: `false`;
  - withdrawal or transfer created: `false`.
- Execution semantics:
  - RTF-051 proves action-time input shape and disabled-smoke behavior only;
  - it does not execute real gateway submit;
  - the real submit path remains the official runtime / Operation Layer path
    with current action-time gates, fresh authorization, protection, idempotency,
    trusted facts, and deployment evidence.
- Deployment:
  - not deployed in this stage;
  - the next deployment should be a selected Tokyo integration probe, not
    first-pass node debugging.

## 2026-06-13 (RTF-052 Tokyo Integration Probe)

- Confirmed current mainline workspace and branch before deployment:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - local / remote head: `ef89f43d1dea518f4851d352f1f6634fa25ac846`.
- Confirmed Tokyo baseline before deployment:
  - deployed head:
    `7fa42bbb776902e7494785a77d8e7b431743998f`;
  - deployed release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-7fa42bbb-20260613Trtf041-binding-only`;
  - migration count: `84`;
  - latest migration:
    `2026-06-11-084_create_runtime_post_submit_budget_settlements.py`;
  - health: `status=ok`, `runtime_bound=true`, `live_ready=false`.
- Built deploy artifacts under `output/rtf052-tokyo`:
  - `git-deploy-plan-ef89f43d.json`:
    `ready_for_owner_authorized_remote_git_deploy_plan`;
  - `owner-git-deploy-packet-ef89f43d.json`:
    `ready_for_owner_git_deploy_decision`;
  - `git-deploy-dry-run-ef89f43d.json`: `dry_run_ready`.
- Applied Tokyo deployment through the git-based deploy path:
  - release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-ef89f43d-20260613Trtf052-action-time-bridge`;
  - backup:
    `/home/ubuntu/brc-deploy/backups/brc-runtime-governance-ef89f43d-20260613Trtf052-action-time-bridge.pgdump`;
  - deploy report:
    `output/rtf052-tokyo/git-deploy-applied-ef89f43d.json`;
  - apply status: `applied`;
  - commands executed: `16/16`;
  - deployment effects: remote files modified, PG backup created, migrations
    run, backend service restarted;
  - forbidden effects: no exchange call, no order, no `ExecutionIntent`, no
    `OrderLifecycle`, no secret values printed.
- Postdeploy verification:
  - read-only probe:
    `output/rtf052-tokyo/readonly-probe-after-ef89f43d.json`;
  - postdeploy verifier:
    `output/rtf052-tokyo/postdeploy-verify-ef89f43d.json`;
  - read-only probe status: `ready_for_controlled_deploy_preflight`;
  - postdeploy verifier status: `postdeploy_acceptance_passed`;
  - current deployed head:
    `ef89f43d1dea518f4851d352f1f6634fa25ac846`;
  - migration count / latest migration remained `84` /
    `2026-06-11-084_create_runtime_post_submit_budget_settlements.py`.
- Ran deployed non-executing RTF-049 / RTF-050 / RTF-051 probes on Tokyo:
  - remote directory:
    `/home/ubuntu/brc-deploy/reports/rtf052-action-time-bridge/20260613Trtf052-ef89f43d`;
  - local mirror:
    `output/rtf052-tokyo/remote-report-20260613Trtf052-ef89f43d`;
  - `rtf049-next-attempt-gate-strategy-planning.json`:
    `rtf049_next_attempt_gate_strategy_planning_passed`;
  - `rtf050-next-attempt-submit-preparation-bridge.json`:
    `rtf050_next_attempt_submit_preparation_bridge_passed`;
  - `rtf051-official-submit-action-time-bridge.json`:
    `rtf051_official_submit_action_time_bridge_passed`.
- Read live runtime / account / position facts:
  - active runtimes report:
    `active-runtimes-readonly.json`;
  - active runtime count: `3`;
  - all active runtimes remained `execution_enabled=false` and
    `shadow_mode=true`;
  - account facts report:
    `account-facts-readonly.json`;
  - Binance USDT futures read-only account equity:
    `30.45108810`;
  - available margin: `29.24480471`;
  - account facts source:
    `binance_usdt_futures_read_only`;
  - live-position monitor reports:
    `live-position-monitor-strategy-runtime-rbr-001-rbr-001-v0-ada-usdt-usdt-short.json`,
    `live-position-monitor-strategy-runtime-e6138ad7c88f.json`,
    `live-position-monitor-strategy-runtime-95655873b76c.json`;
  - `ADA/USDT:USDT` `RBR-001` short runtime:
    `flat_no_review_required`;
  - `AVAX/USDT:USDT` `BTPC-001` short runtime:
    `flat_review_required`;
  - `BNB/USDT:USDT` `CPM-001` long runtime:
    `active_protection_warning`, blocker `runtime_max_active_positions_in_use`,
    warning `missing_tp_protection_right_tail_exit_not_mounted`.
- Safety:
  - no real submit was requested;
  - no exchange write was called;
  - no order was created;
  - no `OrderLifecycle` submit was called;
  - no `ExecutionIntent` was created by the probes;
  - no withdrawal or transfer was created;
  - exchange access was limited to read-only account / position facts.
- Execution semantics:
  - RTF-052 proves the deployed server can run the RTF-049/050/051
    strategy-driven next-attempt chain and action-time disabled-smoke contract;
  - the deployed active runtimes are still shadow / execution-disabled;
  - before a real strategy-driven attempt, the BNB active-position/protection
    warning must be treated as a current action-time blocker for that runtime,
    while flat runtimes can proceed only through fresh signal, fresh
    authorization, FinalGate, protection, and official submit gates.

## 2026-06-13 (RTF-053 Real Strategy-driven Attempt Readiness)

- Confirmed current mainline workspace and branch:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - latest tracked head before this stage:
    `f6c9967f docs(runtime): record tokyo action-time bridge deployment`.
- Purpose:
  - select a real deployed runtime candidate from current Tokyo facts;
  - avoid forcing a trade when no runtime-compatible fresh signal exists;
  - distinguish action-time blockers from normal observe-only strategy state;
  - preserve the right-tail small-capital objective without inventing alpha or
    bypassing strategy semantics.
- Remote report directory:
  - `/home/ubuntu/brc-deploy/reports/rtf053-real-attempt-readiness/20260613Trtf053-f6c9967f`.
- Local mirror:
  - `output/rtf053-tokyo/remote-report-20260613Trtf053-f6c9967f`.
- Summary artifact:
  - `rtf053-summary.json`;
  - status: `waiting_for_fresh_runtime_signal`;
  - real submit candidate ready: `false`;
  - prepare records created: `false`;
  - official submit called: `false`.
- Signal selector results for flat runtimes:
  - `live-signal-selector-strategy-runtime-rbr-001-rbr-001-v0-ada-usdt-usdt-short.json`:
    `no_would_enter_signal_available`;
  - `live-signal-selector-strategy-runtime-95655873b76c.json`:
    `no_would_enter_signal_available`;
  - inspected strategy-shelf signal count: `8`;
  - non-runtime-compatible `would_enter` count: `0`.
- Observation cycle results:
  - `ADA/USDT:USDT` `RBR-001` short:
    - runtime:
      `strategy-runtime-rbr-001-rbr-001-v0-ada-usdt-usdt-short`;
    - next-attempt gate: `clear_for_next_attempt_preflight`;
    - strategy signal: `observe_only`;
    - status: `waiting_for_signal`;
    - no shadow candidate / prepare records created.
  - `AVAX/USDT:USDT` `BTPC-001` short:
    - runtime: `strategy-runtime-95655873b76c`;
    - next-attempt gate: `clear_for_next_attempt_preflight`;
    - strategy signal: `observe_only`;
    - status: `waiting_for_signal`;
    - no shadow candidate / prepare records created.
  - `BNB/USDT:USDT` `CPM-001` long:
    - runtime: `strategy-runtime-e6138ad7c88f`;
    - status: `blocked`;
    - blocked stage: `next_attempt_gate`;
    - lifecycle classification: `still_open_protected`;
    - current lifecycle status: `protected_open_from_pg_orders`;
    - exchange position count: `1`;
    - exchange open protection count: `1`;
    - required next step:
      `wait_for_current_tp_or_sl_then_reconcile_and_review`;
    - no strategy signal evaluation was attempted.
- Safety:
  - signal selection was read-only;
  - no prepare records were created;
  - no `ExecutionIntent` was created;
  - no order was created;
  - no `OrderLifecycle` was called;
  - no exchange write was called;
  - no withdrawal or transfer was created.
- Execution semantics:
  - `ADA` and `AVAX` are structurally eligible for future attempts because
    their next-attempt gates are clear, but they currently have no
    `would_enter` signal;
  - `BNB` is not eligible for a new attempt while the current protected
    lifecycle remains open;
  - current state is not a blocker to the architecture, but it is a valid
    no-trade decision under the strategy semantics gate;
  - next runtime progression should be observation until a fresh
    runtime-compatible `would_enter` signal appears, then prepare records may
    be created through the official API path.

## 2026-06-13 (RTF-054 Filtered Runtime Observation Loop)

- Confirmed current mainline workspace and branch:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - code commit:
    `f58651a5 feat(runtime): filter active observation runtimes`.
- Purpose:
  - keep the active observation loop focused on flat runtimes that can wait
    for a fresh strategy signal;
  - prevent the still-open protected `BNB/USDT:USDT` runtime from making the
    aggregate ADA / AVAX observation window look blocked;
  - preserve non-executing prepare semantics while allowing the operator loop
    to create shadow prepare records only when a fresh signal is ready.
- Local code changes:
  - `scripts/runtime_active_observation_monitor.py` now accepts repeatable
    `--runtime-instance-id` filters;
  - the aggregate packet records `requested_runtime_instance_ids` and
    `selected_runtime_instance_ids`;
  - requested runtimes that are not active or not found are reported as
    warnings, not submit blockers;
  - `scripts/runtime_active_observation_supervisor.py` passes the same
    filters to the loop / monitor chain.
- Local verification:
  - `python3 -m py_compile scripts/runtime_active_observation_monitor.py scripts/runtime_active_observation_supervisor.py scripts/runtime_active_observation_loop.py`;
  - `pytest -q tests/unit/test_runtime_active_observation_monitor.py tests/unit/test_runtime_active_observation_supervisor.py tests/unit/test_runtime_active_observation_loop.py`;
  - result: `22 passed`.
- Tokyo deployment:
  - target head:
    `f58651a53aad4509fb16323e86cfdcea7d9ce7a1`;
  - release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-f58651a5-20260613Trtf054-runtime-filter`;
  - plan artifact:
    `output/rtf054-tokyo/git-deploy-plan-f58651a5.json`;
  - owner packet artifact:
    `output/rtf054-tokyo/owner-git-deploy-packet-f58651a5.json`;
  - apply artifact:
    `output/rtf054-tokyo/git-deploy-applied-f58651a5.json`;
  - postdeploy verification:
    `output/rtf054-tokyo/postdeploy-verify-f58651a5.json`;
  - postdeploy status:
    `postdeploy_acceptance_passed`;
  - deployed head:
    `f58651a53aad4509fb16323e86cfdcea7d9ce7a1`.
- Filtered Tokyo observation:
  - remote report directory:
    `/home/ubuntu/brc-deploy/reports/rtf054-observation-loop/20260613Trtf054-f58651a5-filtered`;
  - local mirror:
    `output/rtf054-tokyo/remote-report-20260613Trtf054-f58651a5-filtered`;
  - selected runtimes:
    `strategy-runtime-rbr-001-rbr-001-v0-ada-usdt-usdt-short`,
    `strategy-runtime-95655873b76c`;
  - active runtime count: `3`;
  - monitored runtime count: `2`;
  - supervisor status: `supervisor_completed`;
  - loop status: `waiting_for_signal`;
  - loop stop reason: `max_iterations_exhausted`;
  - follow-up status: `observation_window_complete_no_signal`.
- Current strategy signal state:
  - `ADA/USDT:USDT` `RBR-001` short:
    `strategy_signal_not_ready_for_shadow_candidate_prepare`;
  - `AVAX/USDT:USDT` `BTPC-001` short:
    `strategy_signal_not_ready_for_shadow_candidate_prepare`;
  - no shadow `SignalEvaluation`, shadow `OrderCandidate`, prepare
    authorization, executable `ExecutionIntent`, order, or exchange submit was
    created.
- Safety:
  - no exchange write was called;
  - no order was created;
  - no `OrderLifecycle` was called;
  - no attempt counter was mutated;
  - no runtime budget was mutated;
  - no withdrawal or transfer was created;
  - `BNB/USDT:USDT` active protected lifecycle was deliberately excluded from
    this filtered flat-runtime observation, not marked safe for a new attempt.
- Execution semantics:
  - RTF-054 fixes the observation loop granularity issue discovered after
    RTF-053;
  - flat runtimes can now be watched independently for fresh strategy signals;
  - the system remains in a valid no-trade waiting state until a runtime-
    compatible `would_enter` signal appears;
  - next mainline progress should move from observation-only waiting into the
    post-submit finalize / next-attempt runtime loop, while keeping the old
    pre-attempt rehearsal path as compatibility evidence rather than the
    primary runtime loop.

## 2026-06-13 (RTF-055 Post-submit Reservation Evidence Resolution)

- Confirmed current mainline workspace and branch:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - code commit:
    `099918d2 feat(runtime): resolve post-submit reservation evidence`.
- Purpose:
  - remove the normal-path need for Owner / operator to manually supply
    `reservation_id` during post-submit finalize;
  - keep the already-submitted authorization in replay-only / reviewable
    semantics;
  - let the runtime-level post-submit loop resolve durable evidence from
    persisted exchange submit result, submit outcome review, budget settlement,
    and attempt reservation facts.
- Local code changes:
  - `RuntimePostSubmitFinalizeService.finalize_authorization(...)` and
    `finalize_latest_for_runtime(...)` now accept optional `reservation_id`;
  - when a post-submit budget settlement already exists, it is reused without
    requiring a reservation id;
  - when settlement is missing, the service resolves reservation evidence by
    `authorization_id` through the attempt reservation repository;
  - `PgRuntimeExecutionAttemptReservationRepository` now supports
    `get_by_authorization_id(...)` using the existing authorization/time index;
  - `RuntimePostSubmitFinalizeRequest`, `runtime_post_submit_finalize_api_flow.py`,
    `runtime_post_submit_next_attempt_cycle.py`, and
    `runtime_full_next_attempt_submit_cycle.py` no longer require
    `--reservation-id`.
- Local verification:
  - `python3 -m py_compile src/application/runtime_post_submit_finalize_service.py src/infrastructure/pg_runtime_execution_attempt_reservation_repository.py src/interfaces/api_trading_console.py scripts/runtime_post_submit_finalize_api_flow.py scripts/runtime_post_submit_next_attempt_cycle.py scripts/runtime_full_next_attempt_submit_cycle.py`;
  - `pytest -q tests/unit/test_runtime_post_submit_finalize.py tests/unit/test_runtime_post_submit_finalize_api_flow.py tests/unit/test_runtime_post_submit_next_attempt_cycle.py tests/unit/test_runtime_full_next_attempt_submit_cycle.py tests/unit/test_runtime_post_submit_finalize_loop_verifier.py tests/unit/test_runtime_next_attempt_gate_strategy_planning_verifier.py tests/unit/test_runtime_next_attempt_submit_preparation_bridge_verifier.py tests/unit/test_runtime_executable_submit_readiness_api_flow.py tests/unit/test_runtime_official_submit_handoff_api_flow.py`;
  - result: `37 passed`.
- Tokyo deployment:
  - target head:
    `099918d22f04219d2a4bd07d0e3111c1902df0d5`;
  - release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-099918d2-20260613Trtf055-post-submit-reservation`;
  - plan artifact:
    `output/rtf055-tokyo/git-deploy-plan-099918d2.json`;
  - owner packet artifact:
    `output/rtf055-tokyo/owner-git-deploy-packet-099918d2.json`;
  - apply artifact:
    `output/rtf055-tokyo/git-deploy-applied-099918d2.json`;
  - postdeploy verification:
    `output/rtf055-tokyo/postdeploy-verify-099918d2.json`;
  - postdeploy status:
    `postdeploy_acceptance_passed`.
- Tokyo post-submit finalize evidence:
  - remote report directory:
    `/home/ubuntu/brc-deploy/reports/rtf055-post-submit-reservation/20260613Trtf055-099918d2`;
  - local mirror:
    `output/rtf055-tokyo/remote-report-20260613Trtf055-099918d2`;
  - runtime:
    `strategy-runtime-95655873b76c`;
  - report:
    `avax-post-submit-finalize-auto-reservation.json`;
  - request mode:
    omitted `reservation_id`;
  - status:
    `finalized_ready_for_next_attempt`;
  - authorization:
    `runtime-submit-authorization-intent_rt_6ca3cecd63fafbd1d25760df`;
  - blockers: `[]`;
  - next-attempt blockers: `[]`;
  - server reused existing submit outcome review and post-submit budget
    settlement.
- Tokyo post-submit -> next-attempt cycle evidence:
  - report:
    `avax-post-submit-next-attempt-auto-reservation-cycle.json`;
  - request mode:
    omitted `reservation_id`;
  - post-submit stage:
    `finalized_ready_for_next_attempt`;
  - cycle status:
    `waiting_for_signal`;
  - blocker:
    `strategy_signal_not_would_enter`;
  - signal evaluation:
    `runtime-signal-input:strategy-runtime-95655873b76c:BTPC-001:1781290800000`;
  - order candidate:
    `None`.
- Safety:
  - no pre-submit rehearsal was called;
  - no local registration was armed;
  - no exchange submit was armed;
  - no exchange write was called;
  - no order was created;
  - no `OrderLifecycle` was called;
  - no attempt counter was mutated by the scripts;
  - no runtime budget was mutated by the scripts;
  - no withdrawal or transfer was created.
- Execution semantics:
  - RTF-055 removes another manual evidence-id step from the runtime loop;
  - the server can now finalize latest runtime submit evidence without
    requiring `reservation_id` in the operator command;
  - the AVAX runtime is ready for a future strategy-driven attempt once a fresh
    runtime-compatible signal appears;
  - the current no-trade result is caused by strategy semantics
    (`strategy_signal_not_would_enter`), not by post-submit evidence plumbing.

## 2026-06-13 (RTF-056 Fresh Signal Prepare Loop)

- Confirmed current mainline workspace and branch:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - code commit:
    `651c2d83 feat(runtime): add fresh signal prepare loop`.
- Purpose:
  - provide one non-executing operator entry for the runtime mainline after a
    submitted attempt;
  - require post-submit finalize before fresh-signal observation / prepare;
  - allow shadow prepare records only when a fresh runtime-compatible signal is
    ready and `--allow-prepare-records` is explicitly supplied;
  - avoid manually running separate finalize, observation, and prepare commands
    in the normal loop.
- Local code changes:
  - added `scripts/runtime_fresh_signal_prepare_loop.py`;
  - added `tests/unit/test_runtime_fresh_signal_prepare_loop.py`;
  - the loop composes:
    `runtime_post_submit_finalize_api_flow.py`
    -> `runtime_next_attempt_observation_api_prepare_flow.py`;
  - the loop writes separate post-submit, observation/prepare, and signal-input
    artifacts under one output directory.
- Local verification:
  - `python3 -m py_compile scripts/runtime_fresh_signal_prepare_loop.py tests/unit/test_runtime_fresh_signal_prepare_loop.py`;
  - `pytest -q tests/unit/test_runtime_fresh_signal_prepare_loop.py tests/unit/test_runtime_next_attempt_observation_api_prepare_flow.py tests/unit/test_runtime_next_attempt_observation_monitor.py tests/unit/test_runtime_post_submit_finalize_api_flow.py`;
  - result: `21 passed`;
  - adjacent regression:
    `pytest -q tests/unit/test_runtime_post_submit_next_attempt_cycle.py tests/unit/test_runtime_full_next_attempt_submit_cycle.py tests/unit/test_runtime_active_observation_monitor.py tests/unit/test_runtime_active_observation_loop.py tests/unit/test_runtime_active_observation_supervisor.py tests/unit/test_runtime_active_observation_followup.py tests/unit/test_runtime_active_observation_status.py`;
  - result: `52 passed`.
- Tokyo deployment:
  - target head:
    `651c2d83056e375067b916a9086453745d5a45bb`;
  - release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-651c2d83-20260613Trtf056-fresh-signal-loop`;
  - plan artifact:
    `output/rtf056-tokyo/git-deploy-plan-651c2d83.json`;
  - owner packet artifact:
    `output/rtf056-tokyo/owner-git-deploy-packet-651c2d83.json`;
  - apply artifact:
    `output/rtf056-tokyo/git-deploy-applied-651c2d83.json`;
  - postdeploy verification:
    `output/rtf056-tokyo/postdeploy-verify-651c2d83.json`;
  - postdeploy status:
    `postdeploy_acceptance_passed`.
- Tokyo fresh-signal loop evidence:
  - remote report directory:
    `/home/ubuntu/brc-deploy/reports/rtf056-fresh-signal-prepare-loop/20260613Trtf056-651c2d83`;
  - local mirror:
    `output/rtf056-tokyo/remote-report-20260613Trtf056-651c2d83`;
  - runtime:
    `strategy-runtime-95655873b76c`;
  - report:
    `avax-fresh-signal-prepare-loop.json`;
  - command mode:
    `--allow-prepare-records` supplied, but prepare records are conditional on
    a ready strategy signal;
  - loop status:
    `waiting_for_signal`;
  - post-submit status:
    `finalized_ready_for_next_attempt`;
  - post-submit authorization:
    `runtime-submit-authorization-intent_rt_6ca3cecd63fafbd1d25760df`;
  - observation status:
    `waiting_for_signal`;
  - signal evaluation status:
    `observe_only`;
  - signal evaluation:
    `runtime-signal-input:strategy-runtime-95655873b76c:BTPC-001:1781290800000`;
  - blocker:
    `strategy_signal_not_ready_for_shadow_candidate_prepare`;
  - prepared authorization:
    `None`.
- Safety:
  - no pre-submit rehearsal was called;
  - no local registration was armed;
  - no exchange submit was armed;
  - no exchange write was called;
  - no order was created;
  - no `OrderLifecycle` was called;
  - no attempt counter was mutated by the script;
  - no runtime budget was mutated by the script;
  - no shadow candidate, runtime intent draft, recorded execution intent,
    submit authorization, or protection plan was created because the signal was
    not ready;
  - no withdrawal or transfer was created.
- Execution semantics:
  - RTF-056 turns post-submit finalize plus fresh signal observation into a
    single repeatable runtime loop entry;
  - current AVAX state remains a valid no-trade decision under strategy
    semantics;
  - once the signal becomes `ready_for_prepare`, the same loop can either stop
    for review or create shadow prepare records when explicitly allowed;
  - real submit still remains downstream of official FinalGate, readiness,
    action-time evidence, protection, and official submit path.

## 2026-06-13 (RTF-057 Fresh Signal Readiness Bridge)

- Confirmed current mainline workspace and branch:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`.
- Purpose:
  - connect an RTF-056 `runtime_fresh_signal_prepare_loop` packet to the
    existing non-executing readiness path;
  - preserve strategy-driven planning as the source of readiness evidence;
  - avoid forcing old pre-submit rehearsal or manual evidence-ID movement back
    into the mainline.
- Local code changes:
  - added `scripts/runtime_fresh_signal_readiness_bridge.py`;
  - added `tests/unit/test_runtime_fresh_signal_readiness_bridge.py`;
  - the bridge consumes a fresh-signal loop packet and, only when the loop is
    `ready_for_prepare` or `ready_for_final_gate_preflight`, runs:
    `runtime_next_attempt_strategy_plan_api_flow.py`
    -> `runtime_cycle_executable_submit_handoff.py`;
  - when the loop is `waiting_for_signal`, the bridge returns
    `waiting_for_signal` and does not call strategy planning or readiness;
  - when readiness evidence is missing, the bridge returns
    `ready_for_readiness_evidence` before planning, so it does not create
    partial planning side effects that cannot be completed.
- Local verification:
  - `python3 -m py_compile scripts/runtime_fresh_signal_readiness_bridge.py tests/unit/test_runtime_fresh_signal_readiness_bridge.py`;
  - `pytest -q tests/unit/test_runtime_fresh_signal_readiness_bridge.py tests/unit/test_runtime_fresh_signal_prepare_loop.py tests/unit/test_runtime_cycle_executable_submit_handoff.py tests/unit/test_runtime_next_attempt_observation_api_prepare_flow.py tests/unit/test_runtime_next_attempt_strategy_plan_api_flow.py`;
  - result: `23 passed`;
  - adjacent readiness regression:
    `pytest -q tests/unit/test_runtime_executable_submit_readiness_api_flow.py tests/unit/test_runtime_executable_submit_readiness_from_reports.py tests/unit/test_runtime_persisted_draft_source_readiness_bridge.py`;
  - result: `11 passed`.
- Safety:
  - no official submit endpoint is called;
  - no pre-submit rehearsal is called;
  - no local registration is armed;
  - no exchange submit is armed;
  - no exchange write is called;
  - no order is created;
  - no `OrderLifecycle` is called;
  - no attempt counter or runtime budget is mutated by the script;
  - no position is opened or closed;
  - no withdrawal or transfer is created.
- Execution semantics:
  - RTF-057 makes the fresh-signal loop actionable once a real runtime-compatible
    signal appears;
  - the next submit path still requires strategy planning readiness, FinalGate
    / executable readiness evidence, fresh submit authorization, and official
    submit action-time confirmation;
  - historical pre-attempt / first-real-submit compatibility remains deferred
    to mandatory cleanup after the main runtime-level chain is proven.

### RTF-057 Tokyo Deployment And Non-executing Probe

- Code commit:
  `88c1d8e0 feat(runtime): bridge fresh signals to readiness`.
- Git deployment:
  - target head:
    `88c1d8e0d7cadb9b6520954a3d65080849548fb8`;
  - release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-88c1d8e0-20260613Trtf057-fresh-readiness-bridge`;
  - plan artifact:
    `output/rtf057-tokyo/git-deploy-plan-88c1d8e0.json`;
  - owner packet artifact:
    `output/rtf057-tokyo/owner-git-deploy-packet-88c1d8e0.json`;
  - dry-run artifact:
    `output/rtf057-tokyo/git-deploy-dry-run-88c1d8e0.json`;
  - apply artifact:
    `output/rtf057-tokyo/git-deploy-applied-88c1d8e0.json`;
  - apply status:
    `applied`;
  - commands:
    `16/16`;
  - postdeploy artifact:
    `output/rtf057-tokyo/postdeploy-verify-88c1d8e0.json`;
  - postdeploy status:
    `postdeploy_acceptance_passed`.
- Tokyo health:
  - `status=ok`;
  - `runtime_bound=true`;
  - `live_ready=false`.
- Tokyo RTF-057 probe:
  - remote report:
    `/home/ubuntu/brc-deploy/reports/rtf057-fresh-signal-readiness-bridge/20260613Trtf057-88c1d8e0/avax-fresh-signal-readiness-bridge.json`;
  - local mirror:
    `output/rtf057-tokyo/remote-report-20260613Trtf057-88c1d8e0/avax-fresh-signal-readiness-bridge.json`;
  - runtime:
    `strategy-runtime-95655873b76c`;
  - status:
    `waiting_for_signal`;
  - blocker:
    `strategy_signal_not_ready_for_shadow_candidate_prepare`;
  - strategy planning:
    `None`;
  - readiness handoff:
    `None`;
  - exchange write:
    `False`;
  - order created:
    `False`;
  - `OrderLifecycle` called:
    `False`.

## 2026-06-13 (RTF-058 Ready Signal Readiness Fixture)

- Confirmed current mainline workspace and branch:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`.
- Purpose:
  - prove the ready-signal path without waiting for the live market to emit a
    runtime-compatible signal;
  - ensure the RTF-056 / RTF-057 mainline can move from a ready fresh-signal
    loop packet into strategy planning and executable readiness;
  - keep the proof local and repeatable before Tokyo or live-fact integration.
- Local code changes:
  - added `scripts/runtime_fresh_signal_readiness_fixture.py`;
  - added `tests/unit/test_runtime_fresh_signal_readiness_fixture.py`;
  - the fixture creates a ready RTF-056-style fresh-signal loop packet, trusted
    readiness evidence, and signal input;
  - it calls the real `runtime_fresh_signal_readiness_bridge.py` with fixture
    strategy-planning and handoff builders;
  - it proves two boundaries:
    `ready_for_fresh_submit_authorization` without a fresh authorization and
    `ready_for_official_submit_call` with a fixture fresh authorization.
- Local verification:
  - `python3 -m py_compile scripts/runtime_fresh_signal_readiness_fixture.py tests/unit/test_runtime_fresh_signal_readiness_fixture.py`;
  - `pytest -q tests/unit/test_runtime_fresh_signal_readiness_fixture.py tests/unit/test_runtime_fresh_signal_readiness_bridge.py tests/unit/test_runtime_full_next_attempt_submit_cycle.py tests/unit/test_runtime_real_signal_pipeline_fixture.py tests/unit/test_runtime_cycle_executable_submit_handoff.py`;
  - result: `22 passed`;
  - adjacent readiness regression:
    `pytest -q tests/unit/test_runtime_next_attempt_strategy_plan_api_flow.py tests/unit/test_runtime_executable_submit_readiness_api_flow.py tests/unit/test_runtime_official_submit_handoff_api_flow.py tests/unit/test_runtime_persisted_draft_source_readiness_bridge.py`;
  - result: `14 passed`.
- Local fixture artifact:
  - report:
    `output/rtf058-ready-signal-fixture/fixture-report.json`;
  - status:
    `ready_fresh_signal_readiness_fixture`;
  - bridge status:
    `ready_for_fresh_submit_authorization`;
  - planning calls:
    `1`;
  - handoff calls:
    `1`;
  - exchange write:
    `False`;
  - order created:
    `False`;
  - `OrderLifecycle` called:
    `False`.
- Safety:
  - no server is called by the fixture;
  - no official submit endpoint is called;
  - no local registration is armed;
  - no exchange submit is armed;
  - no exchange write is called;
  - no order is created;
  - no `OrderLifecycle` is called;
  - no runtime budget is mutated;
  - no position is opened or closed;
  - no withdrawal or transfer is created.
- Execution semantics:
  - RTF-058 closes the local proof gap for the ready-signal branch of the
    current runtime mainline;
  - current live AVAX state can still remain `waiting_for_signal`, but the
    ready path is now reproducible without hand-built packet surgery;
  - the next live move is to connect a real runtime-compatible signal to the
    same bridge and then resolve fresh submit authorization / action-time
    official submit preview.

## 2026-06-13 (RTF-059 Fresh Authorization / Official Handoff Fixture)

- Confirmed current mainline workspace and branch:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`.
- Purpose:
  - prove the downstream path after executable readiness is ready;
  - ensure the consumed submit authorization is not reused;
  - bind or create a fresh submit authorization, generate a valid official
    handoff, and touch the existing official submit endpoint only in
    disabled-smoke mode.
- Local code changes:
  - added `scripts/runtime_fresh_authorization_official_handoff_fixture.py`;
  - added
    `tests/unit/test_runtime_fresh_authorization_official_handoff_fixture.py`;
  - the fixture composes existing helpers:
    `runtime_official_submit_handoff_from_readiness.py`
    -> `runtime_fresh_submit_authorization_binding_api_flow.py`
    -> `runtime_official_submit_handoff_from_readiness.py`
    -> `runtime_official_submit_disabled_smoke_from_handoff.py`;
  - the binding and disabled-smoke API clients are local fakes, so the fixture
    is repeatable without server state.
- Local verification:
  - `python3 -m py_compile scripts/runtime_fresh_authorization_official_handoff_fixture.py tests/unit/test_runtime_fresh_authorization_official_handoff_fixture.py`;
  - `pytest -q tests/unit/test_runtime_fresh_authorization_official_handoff_fixture.py tests/unit/test_runtime_fresh_submit_authorization_binding.py tests/unit/test_runtime_fresh_submit_authorization_resolution.py tests/unit/test_runtime_official_submit_handoff.py tests/unit/test_runtime_official_submit_handoff_api_flow.py tests/unit/test_runtime_official_submit_disabled_smoke_from_handoff.py`;
  - result: `36 passed`;
  - adjacent ready-signal bridge regression:
    `pytest -q tests/unit/test_runtime_fresh_signal_readiness_fixture.py tests/unit/test_runtime_fresh_authorization_official_handoff_fixture.py tests/unit/test_runtime_fresh_signal_readiness_bridge.py`;
  - result: `13 passed`.
- Local fixture artifact:
  - report:
    `output/rtf059-fresh-authorization-official-handoff/fixture-report.json`;
  - status:
    `ready_fresh_authorization_official_handoff_fixture`;
  - stage statuses:
    - initial handoff:
      `blocked`;
    - binding:
      `created_intent_and_authorization`;
    - final handoff:
      `ready_for_official_submit_call`;
    - disabled smoke:
      `disabled_smoke_passed`;
  - fresh submit authorization:
    `fresh-submit-auth-rtf059`;
  - exchange submit execution enabled:
    `False`;
  - exchange write:
    `False`;
  - `OrderLifecycle` called:
    `False`.
- Safety:
  - official endpoint is called only by the disabled-smoke stage;
  - `owner_confirmed_for_first_real_submit_action=false`;
  - no real gateway action is requested;
  - no exchange submit is enabled;
  - no exchange write is called;
  - no order is created;
  - no `OrderLifecycle` is called;
  - no runtime budget is mutated;
  - no withdrawal or transfer is created.
- Execution semantics:
  - RTF-059 proves the ready branch can advance from executable readiness to
    fresh authorization and official handoff preview without replaying the
    consumed authorization;
  - the next real live step still requires a real runtime-compatible signal,
    real persisted records, official FinalGate/readiness evidence, and
    action-time real-submit confirmation;
  - this proof moves the mainline closer to runtime-level bounded attempts
    while preserving one-shot compatibility as historical/recovery surface.

## 2026-06-13 (RTF-060 Tokyo Fresh Authorization / Disabled-smoke Integration)

- Confirmed current mainline workspace and branch:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - deploy target commit:
    `3d62ed7a2075e3e6f953fd2c44a054da3393bf9a`.
- Purpose:
  - deploy the RTF-058 / RTF-059 fixture tooling to Tokyo;
  - prove the deployed release can run the fresh-authorization official-handoff
    fixture;
  - probe the current official disabled-smoke endpoint against an existing
    persisted sample handoff without enabling real gateway action.
- Tokyo deployment:
  - previous release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-88c1d8e0-20260613Trtf057-fresh-readiness-bridge`;
  - new release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-3d62ed7a-20260613Trtf060-fresh-auth-handoff`;
  - plan artifact:
    `output/rtf060-tokyo/git-deploy-plan-3d62ed7a.json`;
  - owner packet artifact:
    `output/rtf060-tokyo/owner-git-deploy-packet-3d62ed7a.json`;
  - dry-run artifact:
    `output/rtf060-tokyo/git-deploy-dry-run-3d62ed7a.json`;
  - apply artifact:
    `output/rtf060-tokyo/git-deploy-applied-3d62ed7a.json`;
  - apply status:
    `applied`;
  - commands:
    `16/16`;
  - postdeploy artifact:
    `output/rtf060-tokyo/postdeploy-verify-3d62ed7a.json`;
  - postdeploy status:
    `postdeploy_acceptance_passed`.
- Tokyo health:
  - `status=ok`;
  - `runtime_bound=true`;
  - `live_ready=false`.
- Tokyo RTF-060 fixture probe:
  - remote report:
    `/home/ubuntu/brc-deploy/reports/rtf060-fresh-authorization-official-handoff/20260613Trtf060-3d62ed7a/fresh-authorization-official-handoff-fixture.json`;
  - local mirror:
    `output/rtf060-tokyo/remote-report-20260613Trtf060-3d62ed7a/fresh-authorization-official-handoff-fixture.json`;
  - status:
    `ready_fresh_authorization_official_handoff_fixture`;
  - stage statuses:
    - initial handoff:
      `blocked`;
    - binding:
      `created_intent_and_authorization`;
    - final handoff:
      `ready_for_official_submit_call`;
    - disabled smoke:
      `disabled_smoke_passed`;
  - fresh submit authorization:
    `fresh-submit-auth-rtf060`;
  - exchange submit execution enabled:
    `False`;
  - exchange write:
    `False`;
  - order created:
    `False`;
  - `OrderLifecycle` called:
    `False`.
- Tokyo actual-service disabled-smoke probe:
  - source handoff:
    `/home/ubuntu/brc-deploy/reports/rtf015-persisted-draft-source/20260612Trtf015-c419e1de/avax-btpc-sample-official-handoff-bound-auth.json`;
  - remote report:
    `/home/ubuntu/brc-deploy/reports/rtf060-fresh-authorization-official-handoff/20260613Trtf060-3d62ed7a/actual-service-disabled-smoke-from-rtf015-bound-handoff.json`;
  - local mirror:
    `output/rtf060-tokyo/remote-report-20260613Trtf060-3d62ed7a/actual-service-disabled-smoke-from-rtf015-bound-handoff.json`;
  - status:
    `blocked`;
  - blocked stage:
    `official_first_real_submit_action`;
  - blocker:
    `official_first_real_submit_action_http_404`;
  - official endpoint called:
    `True`;
  - real gateway requested:
    `False`;
  - exchange submit execution enabled:
    `False`;
  - exchange write:
    `False`;
  - order created:
    `False`;
  - `OrderLifecycle` called:
    `False`.
- Interpretation:
  - the deployed RTF-060 fixture path is ready;
  - the actual-service disabled-smoke probe reached the official endpoint but
    hit an expected historical sample-path prerequisite gap;
  - the gap is not a real order/exchange failure and does not authorize or
    attempt live submit;
  - the next mainline step should use a real current runtime-compatible ready
    signal / persisted draft source instead of replaying the old RTF-015 sample
    handoff.

## 2026-06-13 (RTF-061 Current Runtime Persisted Source Disabled-smoke Pipeline)

- Confirmed current mainline workspace and branch:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`.
- Purpose:
  - stop using historical RTF-015 sample handoff replay as the main disabled-smoke
    source;
  - add a current runtime-compatible persisted source pipeline that starts from a
    real StrategySignal input shape;
  - keep the path non-executing until the official disabled-smoke endpoint.
- Added:
  - `scripts/runtime_current_persisted_source_disabled_smoke_pipeline.py`;
  - `tests/unit/test_runtime_current_persisted_source_disabled_smoke_pipeline.py`.
- Pipeline shape:
  - StrategySignal input;
  - persisted shadow `SignalEvaluation` / `OrderCandidate` /
    `RuntimeExecutionIntentDraft` source through the official Trading Console
    API flow;
  - executable readiness from the persisted draft source;
  - initial handoff intentionally blocked without a fresh submit authorization;
  - fresh submit authorization binding from latest ready draft / existing intent;
  - final handoff rebuilt with the fresh submit authorization;
  - official disabled-smoke endpoint call with
    `owner_confirmed_for_first_real_submit_action=false`.
- Local tests:
  - command:
    `pytest -q tests/unit/test_runtime_current_persisted_source_disabled_smoke_pipeline.py tests/unit/test_runtime_fresh_authorization_official_handoff_fixture.py tests/unit/test_runtime_real_signal_scoped_local_registration_pipeline.py`;
  - result:
    `14 passed`.
- Compile check:
  - command:
    `python3 -m compileall -q scripts/runtime_current_persisted_source_disabled_smoke_pipeline.py`;
  - result:
    passed.
- Direct local CLI observation:
  - command attempted the new script against `http://fixture` without operator
    auth env;
  - result:
    blocked by `BRC-AUTH-CONFIG-MISSING`;
  - interpretation:
    this is an expected operator-auth environment requirement for the real
    `UrlLibApiClient`, not a fake-client pipeline logic failure.
- Safety:
  - uses current runtime persisted source rather than the historical RTF-015
    sample handoff;
  - may create non-executing shadow/persisted source records and fresh submit
    authorization when run against a real service;
  - does not request real gateway action;
  - does not enable exchange submit execution;
  - does not create local orders;
  - does not call `OrderLifecycle`;
  - does not mutate runtime budget;
  - does not open or close positions;
  - does not create withdrawal or transfer.
- Mainline impact:
  - RTF-061 provides the current-source replacement for the RTF-060 blocked
    actual-service disabled-smoke probe;
  - next Tokyo integration should run this pipeline with a current
    runtime-compatible signal input and trusted readiness evidence, instead of
    replaying old RTF-015 handoff JSON.

## 2026-06-13 (RTF-062 Tokyo Deploy / Current-source Actual-service Blocked Probe)

- Confirmed current mainline workspace and branch:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - target commit:
    `9d96ed916ad802739cb8abff99bca76b68e605ef`.
- Deployment:
  - previous release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-3d62ed7a-20260613Trtf060-fresh-auth-handoff`;
  - new release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-9d96ed91-20260613Trtf062-current-source-smoke`;
  - plan artifact:
    `output/rtf062-tokyo/git-deploy-plan-9d96ed91.json`;
  - owner packet artifact:
    `output/rtf062-tokyo/owner-git-deploy-packet-9d96ed91.json`;
  - dry-run artifact:
    `output/rtf062-tokyo/git-deploy-dry-run-9d96ed91.json`;
  - apply artifact:
    `output/rtf062-tokyo/git-deploy-applied-9d96ed91.json`;
  - apply status:
    `applied`;
  - commands:
    `16/16`;
  - backup:
    `/home/ubuntu/brc-deploy/backups/brc-runtime-governance-9d96ed91-20260613Trtf062-current-source-smoke.pgdump`;
  - migration state:
    `084`;
  - postdeploy status:
    `postdeploy_acceptance_passed`.
- Tokyo health after deployment:
  - `status=ok`;
  - `runtime_bound=true`;
  - `live_ready=false`;
  - manifest head:
    `9d96ed916ad802739cb8abff99bca76b68e605ef`.
- RTF-062 live signal selector:
  - remote report:
    `/home/ubuntu/brc-deploy/reports/rtf062-current-source-disabled-smoke/20260613Trtf062-9d96ed91/live-signal-selector.json`;
  - local mirror:
    `output/rtf062-tokyo/remote-report-20260613Trtf062-9d96ed91/live-signal-selector.json`;
  - status:
    `no_would_enter_signal_available`;
  - blocker:
    `runtime_strategy_signal_not_found_in_strategy_shelf`;
  - inspected signals:
    `8`;
  - `would_enter` count:
    `0`.
- RTF-062 fresh-signal prepare loop:
  - remote report:
    `/home/ubuntu/brc-deploy/reports/rtf062-current-source-disabled-smoke/20260613Trtf062-9d96ed91/fresh-signal-prepare-loop.json`;
  - local mirror:
    `output/rtf062-tokyo/remote-report-20260613Trtf062-9d96ed91/fresh-signal-prepare-loop.json`;
  - status:
    `waiting_for_signal`;
  - blocker:
    `strategy_signal_not_ready_for_shadow_candidate_prepare`;
  - post-submit finalize:
    `finalized_ready_for_next_attempt`;
  - next attempt gate:
    `ready_for_fresh_signal`;
  - attempts remaining:
    `1`;
  - budget remaining:
    `5.833135780000000000`;
  - active positions count:
    `0`.
- RTF-061 current-source pipeline on Tokyo:
  - remote report:
    `/home/ubuntu/brc-deploy/reports/rtf062-current-source-disabled-smoke/20260613Trtf062-9d96ed91/current-source-pipeline-report.json`;
  - local mirror:
    `output/rtf062-tokyo/remote-report-20260613Trtf062-9d96ed91/current-source-pipeline-report.json`;
  - status:
    `blocked_at_strategy_signal_intent_draft_source`;
  - blocked stage:
    `strategy_signal_intent_draft_source`;
  - blockers:
    `intent_draft_source:strategy_signal_not_would_enter`,
    `intent_draft_source:scheduler_shadow_candidate_not_created`;
  - fresh submit authorization:
    `null`;
  - official submit endpoint called:
    `False`.
- Safety:
  - no historical RTF-015 sample handoff was used;
  - no fresh submit authorization was created;
  - no official submit endpoint call was made by the current-source pipeline;
  - no real gateway action was requested;
  - no exchange write occurred;
  - no order was created;
  - no `OrderLifecycle` call occurred;
  - no runtime budget mutation occurred;
  - no position was opened or closed;
  - no withdrawal or transfer was created.
- Interpretation:
  - deployment is current and healthy;
  - the current runtime is post-submit finalized and ready for a fresh signal;
  - current market did not produce a runtime-compatible `would_enter`;
  - the actual-service current-source pipeline correctly blocked before
    persisted candidate / readiness / handoff instead of replaying old sample
    handoff or faking readiness;
  - next runtime progress requires a genuine runtime-compatible `would_enter`
    or an Owner-approved new runtime/profile for a different strategy signal.

## 2026-06-13 (RTF-063 Current-source Observation Continuation)

- Confirmed current mainline workspace and branch:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`.
- Purpose:
  - compose the post-submit / fresh-signal prepare loop with the current
    persisted-source disabled-smoke pipeline;
  - stop manually pushing no-action signals through the current-source pipeline;
  - wait for a genuine runtime-compatible ready signal before creating
    persisted source records or fresh submit authorization;
  - keep the flow non-executing unless a later explicit real-submit gate is
    opened.
- Added:
  - `scripts/runtime_current_source_observation_continuation.py`;
  - `tests/unit/test_runtime_current_source_observation_continuation.py`.
- Continuation behavior:
  - runs the fresh-signal prepare loop first;
  - returns `waiting_for_signal` without invoking the current-source pipeline
    when the runtime has no genuine ready signal;
  - returns `ready_for_current_source_pipeline_evidence` when the prepare loop
    reaches `ready_for_final_gate_preflight` but readiness evidence is absent;
  - runs the current persisted-source disabled-smoke pipeline only after the
    ready signal and readiness evidence are both available;
  - propagates current-source blockers such as
    `strategy_signal_not_would_enter` without faking readiness.
- Local tests:
  - command:
    `pytest -q tests/unit/test_runtime_current_source_observation_continuation.py tests/unit/test_runtime_current_persisted_source_disabled_smoke_pipeline.py tests/unit/test_runtime_next_attempt_observation_monitor.py`;
  - result:
    `16 passed`.
- Compile and diff checks:
  - command:
    `python3 -m compileall -q scripts/runtime_current_source_observation_continuation.py`;
  - result:
    passed;
  - command:
    `git diff --check`;
  - result:
    passed.
- Safety:
  - no historical RTF-015 sample handoff is introduced;
  - no real gateway action is requested;
  - no exchange write occurs;
  - no order is created;
  - no `OrderLifecycle` call occurs;
  - no runtime budget mutation occurs;
  - no position is opened or closed;
  - no withdrawal or transfer is created.
- Mainline impact:
  - RTF-063 turns the current-source path into a repeatable observation
    continuation rather than a manual no-action signal probe;
  - the next Tokyo integration can run one script against the active runtime:
    it should either keep waiting for a real signal or progress into the
    current-source disabled-smoke pipeline when the signal is ready.

## 2026-06-13 (RTF-064 Tokyo Current-source Observation Continuation Integration)

- Confirmed current mainline workspace and branch:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - target commit:
    `56cf5d19e129fa81c220dbfdf2cf02900d3fc98f`.
- Pre-deploy read-only probe:
  - current head:
    `9d96ed916ad802739cb8abff99bca76b68e605ef`;
  - current release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-9d96ed91-20260613Trtf062-current-source-smoke`;
  - status:
    `ready_for_controlled_deploy_preflight`;
  - blockers:
    none.
- Deployment:
  - new release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-56cf5d19-20260613Trtf064-current-source-continuation`;
  - plan artifact:
    `output/rtf064-tokyo/git-deploy-plan-56cf5d19.json`;
  - owner packet artifact:
    `output/rtf064-tokyo/owner-git-deploy-packet-56cf5d19.json`;
  - dry-run artifact:
    `output/rtf064-tokyo/git-deploy-dry-run-56cf5d19.json`;
  - apply artifact:
    `output/rtf064-tokyo/git-deploy-applied-56cf5d19.json`;
  - apply status:
    `applied`;
  - commands:
    `16/16`;
  - backup:
    `/home/ubuntu/brc-deploy/backups/brc-runtime-governance-56cf5d19-20260613Trtf064-current-source-continuation.pgdump`;
  - migration state:
    `084`;
  - postdeploy status:
    `postdeploy_acceptance_passed`.
- Tokyo health after deployment:
  - `status=ok`;
  - `runtime_bound=true`;
  - `live_ready=false`;
  - manifest head:
    `56cf5d19e129fa81c220dbfdf2cf02900d3fc98f`.
- RTF-064 current-source observation continuation:
  - remote report:
    `/home/ubuntu/brc-deploy/reports/rtf064-current-source-observation-continuation/20260613Trtf064-56cf5d19/current-source-observation-continuation.json`;
  - local mirror:
    `output/rtf064-tokyo/remote-report-20260613Trtf064-56cf5d19/current-source-observation-continuation.json`;
  - status:
    `waiting_for_signal`;
  - blocker:
    `strategy_signal_not_ready_for_shadow_candidate_prepare`;
  - operator next step:
    `continue_observation_until_genuine_would_enter`;
  - current-source pipeline invoked:
    `false`;
  - readiness evidence required:
    `false`;
  - real-submit gate required:
    `false`.
- Safety:
  - no historical RTF-015 sample handoff was used;
  - no prepare records were created;
  - no shadow candidate was created;
  - no runtime execution intent draft was created;
  - no submit authorization was created;
  - no official submit endpoint was called;
  - no real gateway action was requested;
  - no exchange write occurred;
  - no order was created;
  - no `OrderLifecycle` call occurred;
  - no runtime budget mutation occurred;
  - no position was opened or closed;
  - no withdrawal or transfer was created.
- Interpretation:
  - RTF-063 code is now deployed and verified on Tokyo;
  - the current runtime remains post-submit finalized and ready to observe a
    fresh signal;
  - because the live strategy signal is not ready, the continuation correctly
    waits instead of forcing candidate planning or replaying historical handoff
    data;
  - next mainline progress should focus on producing or discovering a genuine
    runtime-compatible ready signal for the current runtime or an explicitly
    approved new runtime/profile.

## 2026-06-13 (RTF-065 Live Signal Routing Packet / Strategy Signal Planning Proof)

- Confirmed current mainline workspace and branch:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`.
- Purpose:
  - reduce the current no-signal stall into a clear non-executing routing
    decision;
  - avoid manually stitching together live selector output, non-runtime profile
    proposal, and runtime prepare commands;
  - preserve the rule that readiness must come from a genuine strategy signal,
    not from a forced sample or old handoff replay.
- Added:
  - `scripts/runtime_live_signal_routing_packet.py`;
  - `tests/unit/test_runtime_live_signal_routing_packet.py`.
- Routing behavior:
  - `runtime_compatible_would_enter_selected` becomes
    `ready_for_current_runtime_signal_prepare`;
  - `would_enter_available_but_not_runtime_compatible` creates only a
    non-executing Owner/Codex runtime-profile proposal packet;
  - no runtime-compatible signal becomes
    `waiting_for_runtime_compatible_signal`.
- Local routing tests:
  - command:
    `pytest -q tests/unit/test_runtime_live_signal_routing_packet.py tests/unit/test_runtime_non_runtime_signal_profile_proposal.py tests/unit/test_runtime_live_strategy_signal_selector.py`;
  - result:
    `10 passed`.
- Local strategy planning proof:
  - command:
    `pytest -q tests/unit/test_b0_runtime_strategy_signal_planning.py tests/unit/test_reference_price_action_evaluators.py tests/unit/test_runtime_strategy_signal_evaluation_service.py tests/unit/test_runtime_next_attempt_observation_api_prepare_flow.py`;
  - result:
    `28 passed`.
- Compile and diff checks:
  - command:
    `python3 -m compileall -q scripts/runtime_live_signal_routing_packet.py`;
  - result:
    passed;
  - command:
    `git diff --check`;
  - result:
    passed.
- Safety:
  - no runtime is created;
  - no runtime profile is mutated;
  - no shadow candidate is created by the routing packet;
  - no `ExecutionIntent` is created;
  - no order is created;
  - no `OrderLifecycle` call occurs;
  - no exchange write occurs;
  - no runtime budget mutation occurs;
  - no position is opened or closed;
  - no withdrawal or transfer is created.
- Interpretation:
  - RTF-065 provides the missing operator routing surface between live signal
    discovery and Strategy Signal -> Shadow Candidate Planning v1;
  - CPM/BRF/reference price-action strategy semantics are locally proven through
    the existing B0 strategy planning tests;
  - the next Tokyo step is to deploy this routing packet and run it against the
    active runtime so the system can report whether to wait, prepare the current
    runtime, or propose a new bounded runtime profile from a non-runtime signal.

## 2026-06-13 (RTF-066 Tokyo Live Signal Routing Integration)

- Confirmed current mainline workspace and branch:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - target commit:
    `2e6fabd7c0fec38c760b325c63c74057c6d03dc8`.
- Pre-deploy read-only probe:
  - current head:
    `56cf5d19e129fa81c220dbfdf2cf02900d3fc98f`;
  - current release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-56cf5d19-20260613Trtf064-current-source-continuation`;
  - status:
    `ready_for_controlled_deploy_preflight`;
  - blockers:
    none.
- Deployment:
  - new release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-2e6fabd7-20260613Trtf066-live-signal-routing`;
  - plan artifact:
    `output/rtf066-tokyo/git-deploy-plan-2e6fabd7.json`;
  - owner packet artifact:
    `output/rtf066-tokyo/owner-git-deploy-packet-2e6fabd7.json`;
  - dry-run artifact:
    `output/rtf066-tokyo/git-deploy-dry-run-2e6fabd7.json`;
  - apply artifact:
    `output/rtf066-tokyo/git-deploy-applied-2e6fabd7.json`;
  - apply status:
    `applied`;
  - commands:
    `16/16`;
  - backup:
    `/home/ubuntu/brc-deploy/backups/brc-runtime-governance-2e6fabd7-20260613Trtf066-live-signal-routing.pgdump`;
  - migration state:
    `084`;
  - postdeploy status:
    `postdeploy_acceptance_passed`.
- Tokyo health after deployment:
  - `status=ok`;
  - `runtime_bound=true`;
  - `live_ready=false`;
  - manifest head:
    `2e6fabd7c0fec38c760b325c63c74057c6d03dc8`.
- RTF-066 live signal routing packet:
  - remote report:
    `/home/ubuntu/brc-deploy/reports/rtf066-live-signal-routing/20260613Trtf066-2e6fabd7/live-signal-routing-packet.json`;
  - local mirror:
    `output/rtf066-tokyo/remote-report-20260613Trtf066-2e6fabd7/live-signal-routing-packet.json`;
  - status:
    `waiting_for_runtime_compatible_signal`;
  - source selector status:
    `no_would_enter_signal_available`;
  - blocker:
    `runtime_strategy_signal_not_found_in_strategy_shelf`;
  - selected signal:
    `null`;
  - non-runtime would-enter count:
    `0`;
  - signal input json:
    `null`;
  - operator next step:
    `continue_live_signal_observation_without_forcing_entry`.
- Safety:
  - no runtime was created;
  - no runtime profile was mutated;
  - no shadow candidate was created;
  - no `ExecutionIntent` was created;
  - no order was created;
  - no `OrderLifecycle` call occurred;
  - no exchange write occurred;
  - no runtime budget mutation occurred;
  - no position was opened or closed;
  - no withdrawal or transfer was created.
- Interpretation:
  - RTF-065 code is now deployed and verified on Tokyo;
  - the system can now distinguish current-runtime ready signal, non-runtime
    would-enter profile proposal, and no-signal wait in one operator packet;
  - live market currently has no runtime-compatible or non-runtime would-enter
    signal in the strategy shelf, so the correct next state is continued
    observation rather than forced candidate planning.

## 2026-06-13 (RTF-067 Live Signal Operator Cycle)

- Confirmed current mainline workspace and branch:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`.
- Purpose:
  - make the live-signal route repeatable as a single operator cycle;
  - combine RTF-065 live routing with the official next-attempt prepare entry;
  - keep default mode record-free while allowing explicit non-executing prepare
    records only after a genuine current-runtime ready signal.
- Added:
  - `scripts/runtime_live_signal_operator_cycle.py`;
  - `tests/unit/test_runtime_live_signal_operator_cycle.py`.
- Cycle behavior:
  - `waiting_for_runtime_compatible_signal` returns a wait packet and does not
    call prepare;
  - `ready_for_owner_runtime_profile_decision` returns the profile proposal
    packet and does not create a runtime;
  - `ready_for_current_runtime_signal_prepare` returns `ready_for_prepare`
    unless `--allow-prepare-records` is supplied;
  - with `--allow-prepare-records`, the cycle calls the official
    `runtime_next_attempt_prepare_api_flow` and may produce only non-executing
    prepare records.
- Local operator-cycle tests:
  - command:
    `pytest -q tests/unit/test_runtime_live_signal_operator_cycle.py tests/unit/test_runtime_live_signal_routing_packet.py tests/unit/test_runtime_next_attempt_observation_api_prepare_flow.py tests/unit/test_runtime_next_attempt_prepare_api_flow.py`;
  - result:
    `19 passed`.
- Local strategy semantics regression:
  - command:
    `pytest -q tests/unit/test_b0_runtime_strategy_signal_planning.py tests/unit/test_reference_price_action_evaluators.py tests/unit/test_runtime_strategy_signal_evaluation_service.py tests/unit/test_runtime_live_strategy_signal_selector.py`;
  - result:
    `26 passed`.
- Compile and diff checks:
  - command:
    `python3 -m compileall -q scripts/runtime_live_signal_operator_cycle.py`;
  - result:
    passed;
  - command:
    `git diff --check`;
  - result:
    passed.
- Safety:
  - default mode creates no prepare records;
  - prepare flow runs only with explicit `--allow-prepare-records`;
  - no runtime is created;
  - no runtime profile is mutated;
  - no local registration is armed;
  - no exchange submit adapter is armed;
  - no real submit is executed;
  - no order is created;
  - no `OrderLifecycle` call occurs;
  - no exchange write occurs;
  - no runtime budget mutation occurs;
  - no position is opened or closed;
  - no withdrawal or transfer is created.
- Interpretation:
  - RTF-067 converts the previous one-off route checks into a repeatable
    operator cycle;
  - this stage still does not solve market no-signal state by itself;
  - the next Tokyo step is to deploy the cycle and run it against the active
    runtime, expecting the current live state to remain waiting unless a
    genuine runtime-compatible ready signal appears.

## 2026-06-13 (RTF-068 Tokyo Live Signal Operator Cycle Integration)

- Confirmed current mainline workspace and branch:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - target commit:
    `f834100bc1a7422b0b935c059cd210d8637cc8d2`.
- Pre-deploy read-only probe:
  - current head:
    `2e6fabd7c0fec38c760b325c63c74057c6d03dc8`;
  - current release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-2e6fabd7-20260613Trtf066-live-signal-routing`;
  - status:
    `ready_for_controlled_deploy_preflight`;
  - blockers:
    none.
- Deployment:
  - new release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-f834100b-20260613Trtf068-live-signal-operator-cycle`;
  - plan artifact:
    `output/rtf068-tokyo/git-deploy-plan-f834100b.json`;
  - owner packet artifact:
    `output/rtf068-tokyo/owner-git-deploy-packet-f834100b.json`;
  - dry-run artifact:
    `output/rtf068-tokyo/git-deploy-dry-run-f834100b.json`;
  - apply artifact:
    `output/rtf068-tokyo/git-deploy-applied-f834100b.json`;
  - apply status:
    `applied`;
  - commands:
    `16/16`;
  - backup:
    `/home/ubuntu/brc-deploy/backups/brc-runtime-governance-f834100b-20260613Trtf068-live-signal-operator-cycle.pgdump`;
  - migration state:
    `084`;
  - postdeploy status:
    `postdeploy_acceptance_passed`.
- Tokyo health after deployment:
  - `status=ok`;
  - `runtime_bound=true`;
  - `live_ready=false`;
  - manifest head:
    `f834100bc1a7422b0b935c059cd210d8637cc8d2`.
- RTF-068 default live signal operator cycle:
  - remote report:
    `/home/ubuntu/brc-deploy/reports/rtf068-live-signal-operator-cycle/20260613Trtf068-f834100b/live-signal-operator-cycle.json`;
  - local mirror:
    `output/rtf068-tokyo/remote-report-20260613Trtf068-f834100b/live-signal-operator-cycle.json`;
  - status:
    `waiting_for_runtime_compatible_signal`;
  - blocker:
    `runtime_strategy_signal_not_found_in_strategy_shelf`;
  - routing status:
    `waiting_for_runtime_compatible_signal`;
  - routing source selector status:
    `no_would_enter_signal_available`;
  - signal input json:
    `null`;
  - prepare packet:
    `null`;
  - operator next step:
    `continue_live_signal_observation_without_forcing_entry`.
- Safety:
  - prepare flow was not called;
  - no prepare records were created;
  - no runtime was created;
  - no runtime profile was mutated;
  - no shadow candidate was created;
  - no recorded `ExecutionIntent` was created;
  - no submit authorization was created;
  - no order was created;
  - no `OrderLifecycle` call occurred;
  - no exchange write occurred;
  - no runtime budget mutation occurred;
  - no position was opened or closed;
  - no withdrawal or transfer was created.
- Interpretation:
  - RTF-067 code is now deployed and verified on Tokyo;
  - the default operator cycle is usable as the repeatable no-submit loop;
  - current live market still has no runtime-compatible or non-runtime
    would-enter signal, so the correct result remains waiting rather than
    forced prepare.

## 2026-06-13 (RTF-069 Live Signal Operator Supervisor)

- Confirmed current mainline workspace and branch:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`.
- Purpose:
  - turn one-off live signal operator cycles into a repeatable supervisor loop;
  - continue automatically while the result is waiting;
  - stop for Owner/Codex review on runtime profile proposal;
  - stop for prepare review on current-runtime ready signal;
  - stop for FinalGate review after explicit non-executing prepare records.
- Added:
  - `scripts/runtime_live_signal_operator_supervisor.py`;
  - `tests/unit/test_runtime_live_signal_operator_supervisor.py`.
- Supervisor behavior:
  - `waiting_for_runtime_compatible_signal` continues until `max_cycles`;
  - `ready_for_owner_runtime_profile_decision` stops with
    `supervisor_profile_review_required`;
  - `ready_for_prepare` stops with `supervisor_prepare_review_required`;
  - `ready_for_final_gate_preflight` stops with
    `supervisor_final_gate_review_required`;
  - any forbidden effect such as order creation, exchange write, budget
    mutation, or `OrderLifecycle` call blocks the supervisor.
- Local supervisor tests:
  - command:
    `pytest -q tests/unit/test_runtime_live_signal_operator_supervisor.py tests/unit/test_runtime_live_signal_operator_cycle.py tests/unit/test_runtime_live_signal_routing_packet.py`;
  - result:
    `15 passed`.
- Local strategy / prepare regression:
  - command:
    `pytest -q tests/unit/test_b0_runtime_strategy_signal_planning.py tests/unit/test_reference_price_action_evaluators.py tests/unit/test_runtime_strategy_signal_evaluation_service.py tests/unit/test_runtime_next_attempt_prepare_api_flow.py tests/unit/test_runtime_next_attempt_observation_api_prepare_flow.py`;
  - result:
    `33 passed`.
- Compile and diff checks:
  - command:
    `python3 -m compileall -q scripts/runtime_live_signal_operator_supervisor.py`;
  - result:
    passed;
  - command:
    `git diff --check`;
  - result:
    passed.
- Safety:
  - no runtime is created;
  - no runtime profile is mutated;
  - no local registration is armed;
  - no exchange submit adapter is armed;
  - no real submit is executed;
  - no order is created;
  - no `OrderLifecycle` call occurs;
  - no exchange write occurs;
  - no runtime budget mutation occurs;
  - no position is opened or closed;
  - no withdrawal or transfer is created.
- Interpretation:
  - RTF-069 creates the missing repeatable observation loop around the
    live-signal operator cycle;
  - it preserves review stops instead of turning readiness into automatic
    execution;
  - the next Tokyo step is to deploy the supervisor and run it against the
    active runtime with a small `max_cycles` window.

## 2026-06-13 (RTF-070 Tokyo Live Signal Operator Supervisor Integration)

- Confirmed current mainline workspace and branch:
  - workspace: `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch: `program/live-safe-v1`;
  - target commit:
    `9e15b81fa5aeed5f47f9e22ee8c3b65e964b01f1`.
- Pre-deploy read-only probe:
  - current head:
    `f834100bc1a7422b0b935c059cd210d8637cc8d2`;
  - current release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-f834100b-20260613Trtf068-live-signal-operator-cycle`;
  - status:
    `ready_for_controlled_deploy_preflight`;
  - blockers:
    none.
- Deployment:
  - new release:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-9e15b81f-20260613Trtf070-live-signal-supervisor`;
  - plan artifact:
    `output/rtf070-tokyo/git-deploy-plan-9e15b81f.json`;
  - owner packet artifact:
    `output/rtf070-tokyo/owner-git-deploy-packet-9e15b81f.json`;
  - dry-run artifact:
    `output/rtf070-tokyo/git-deploy-dry-run-9e15b81f.json`;
  - apply artifact:
    `output/rtf070-tokyo/git-deploy-applied-9e15b81f.json`;
  - apply status:
    `applied`;
  - commands:
    `16/16`;
  - backup:
    `/home/ubuntu/brc-deploy/backups/brc-runtime-governance-9e15b81f-20260613Trtf070-live-signal-supervisor.pgdump`;
  - migration state:
    `084`;
  - postdeploy status:
    `postdeploy_acceptance_passed`.
- Tokyo health after deployment:
  - `status=ok`;
  - `runtime_bound=true`;
  - `live_ready=false`;
  - manifest head:
    `9e15b81fa5aeed5f47f9e22ee8c3b65e964b01f1`.
- RTF-070 live signal operator supervisor:
  - remote report:
    `/home/ubuntu/brc-deploy/reports/rtf070-live-signal-supervisor/20260613Trtf070-9e15b81f/live-signal-operator-supervisor.json`;
  - local mirror:
    `output/rtf070-tokyo/remote-report-20260613Trtf070-9e15b81f/live-signal-operator-supervisor.json`;
  - runtime:
    `strategy-runtime-95655873b76c`;
  - max cycles:
    `2`;
  - status:
    `supervisor_waiting_for_signal`;
  - stop reason:
    `max_cycles_reached`;
  - cycles completed:
    `2`;
  - latest cycle status:
    `waiting_for_runtime_compatible_signal`;
  - operator next step:
    `continue_live_signal_operator_supervision`.
- Cycle facts:
  - cycle 1 status:
    `waiting_for_runtime_compatible_signal`;
  - cycle 1 selector:
    `no_would_enter_signal_available`;
  - cycle 1 blocker:
    `runtime_strategy_signal_not_found_in_strategy_shelf`;
  - cycle 2 status:
    `waiting_for_runtime_compatible_signal`;
  - cycle 2 selector:
    `no_would_enter_signal_available`;
  - cycle 2 blocker:
    `runtime_strategy_signal_not_found_in_strategy_shelf`.
- Safety:
  - no forbidden effect was detected;
  - prepare flow was not called;
  - no prepare records were created;
  - no shadow candidate was created;
  - no recorded `ExecutionIntent` was created;
  - no submit authorization was created;
  - no order was created;
  - no `OrderLifecycle` call occurred;
  - no real submit was executed;
  - no exchange write occurred;
  - no runtime budget mutation occurred;
  - no position was opened or closed;
  - no withdrawal or transfer was created.
- Interpretation:
  - RTF-069 code is now deployed and verified on Tokyo;
  - the supervisor can repeatedly run the operator cycle and remain safe in a
    no-signal market;
  - the mainline is now waiting for a genuine strategy signal rather than a
    missing orchestration primitive.

## 2026-06-13 (RTF-071 No-signal Operator Summary)

- Worktree:
  `/Users/jiangwei/Documents/final-sprint6-integration`.
- Branch:
  `program/live-safe-v1`.
- Purpose:
  convert the RTF-069/070 live signal operator supervisor packet into an
  Owner/operator-readable read-only status summary.
- Added:
  `scripts/build_runtime_supervisor_operator_summary.py`.
- Added tests:
  `tests/unit/test_runtime_supervisor_operator_summary.py`.
- Summary statuses:
  - `operator_waiting_for_signal`;
  - `operator_profile_review_required`;
  - `operator_prepare_review_required`;
  - `operator_final_gate_review_required`;
  - `operator_supervisor_blocked`;
  - `operator_summary_needs_review`.
- Local proof against mirrored RTF-070 Tokyo supervisor report:
  - source:
    `output/rtf070-tokyo/remote-report-20260613Trtf070-9e15b81f/live-signal-operator-supervisor.json`;
  - output:
    `output/rtf071-supervisor-summary/local-summary-from-rtf070.json`;
  - status:
    `operator_waiting_for_signal`;
  - runtime:
    `strategy-runtime-95655873b76c`;
  - source supervisor status:
    `supervisor_waiting_for_signal`;
  - stop reason:
    `max_cycles_reached`;
  - cycles completed:
    `2`;
  - no-signal window:
    `true`;
  - selector status counts:
    `no_would_enter_signal_available=2`;
  - blocker counts:
    `runtime_strategy_signal_not_found_in_strategy_shelf=2`;
  - next step:
    `continue_live_signal_operator_supervision`.
- Right-tail objective context:
  - no-signal is not failure;
  - forcing entry without a genuine signal remains forbidden;
  - small bounded losses are acceptable only after a real signal is ready and
    runtime boundaries pass;
  - Owner withdrawal remains manual;
  - automatic withdrawal and automatic compounding are not assumed.
- Verification:
  - `pytest -q tests/unit/test_runtime_supervisor_operator_summary.py tests/unit/test_runtime_live_signal_operator_supervisor.py tests/unit/test_runtime_live_signal_operator_cycle.py tests/unit/test_runtime_live_signal_routing_packet.py`;
  - result:
    `21 passed`.
- Safety:
  - packet-read only;
  - no PG write;
  - no runtime creation;
  - no runtime profile mutation;
  - no shadow candidate;
  - no recorded `ExecutionIntent`;
  - no submit authorization;
  - no order;
  - no `OrderLifecycle`;
  - no real submit;
  - no exchange write;
  - no runtime budget mutation;
  - no position open/close;
  - no withdrawal or transfer.

## 2026-06-13 (RTF-072 Tokyo Supervisor Summary Integration)

- Worktree:
  `/Users/jiangwei/Documents/final-sprint6-integration`.
- Branch:
  `program/live-safe-v1`.
- Commit deployed:
  `09cadf270d29ecb434beae9a045fd1f131e47897`.
- Previous Tokyo head:
  `9e15b81fa5aeed5f47f9e22ee8c3b65e964b01f1`.
- New Tokyo release:
  `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-09cadf27-20260613Trtf072-supervisor-summary`.
- Deploy artifacts:
  - plan:
    `output/rtf072-tokyo/git-deploy-plan-09cadf27.json`;
  - owner packet:
    `output/rtf072-tokyo/owner-git-deploy-packet-09cadf27.json`;
  - dry-run:
    `output/rtf072-tokyo/git-deploy-dry-run-09cadf27.json`;
  - apply:
    `output/rtf072-tokyo/git-deploy-applied-09cadf27.json`.
- Deploy result:
  - status:
    `applied`;
  - blockers:
    `[]`;
  - commands:
    `16/16`;
  - backup:
    `/home/ubuntu/brc-deploy/backups/brc-runtime-governance-09cadf27-20260613Trtf072-supervisor-summary.pgdump`;
  - migrations:
    alembic command executed, migration count remained `84`;
  - service:
    restarted.
- Postdeploy read-only facts:
  - artifact:
    `output/rtf072-tokyo/readonly-probe-after-deploy.json`;
  - status:
    `ready_for_controlled_deploy_preflight`;
  - blockers:
    `[]`;
  - current head:
    `09cadf270d29ecb434beae9a045fd1f131e47897`;
  - health:
    `status=ok`, `runtime_bound=true`, `live_ready=false`.
- Postdeploy acceptance:
  - artifact:
    `output/rtf072-tokyo/postdeploy-acceptance-09cadf27.json`;
  - status:
    `postdeploy_acceptance_passed`;
  - blockers:
    `[]`.
- Remote summary verification:
  - input:
    `/home/ubuntu/brc-deploy/reports/rtf070-live-signal-supervisor/20260613Trtf070-9e15b81f/live-signal-operator-supervisor.json`;
  - remote output:
    `/home/ubuntu/brc-deploy/reports/rtf072-supervisor-summary/20260613Trtf072-09cadf27/supervisor-operator-summary.json`;
  - local mirror:
    `output/rtf072-tokyo/remote-report-20260613Trtf072-09cadf27/supervisor-operator-summary.json`;
  - validation artifact:
    `output/rtf072-tokyo/remote-summary-validation.txt`;
  - validation:
    `remote_summary_validation=passed`;
  - status:
    `operator_waiting_for_signal`;
  - runtime:
    `strategy-runtime-95655873b76c`;
  - no-signal window:
    `true`;
  - next step:
    `continue_live_signal_operator_supervision`;
  - selector status:
    `no_would_enter_signal_available=2`;
  - blocker count:
    `runtime_strategy_signal_not_found_in_strategy_shelf=2`.
- Safety:
  - deployment did not authorize real runtime submit;
  - summary verification read an existing packet and wrote a report artifact
    only;
  - no runtime creation;
  - no runtime profile mutation;
  - no shadow candidate;
  - no recorded `ExecutionIntent`;
  - no submit authorization;
  - no order;
  - no `OrderLifecycle`;
  - no real submit;
  - no exchange write;
  - no runtime budget mutation;
  - no position open/close;
  - no withdrawal or transfer.
- Interpretation:
  - RTF-071 is now deployed and verified on Tokyo;
  - the operator can consume supervisor output as a readable no-signal status;
  - the mainline remains ready to continue live signal supervision until a
    genuine runtime-compatible strategy signal appears.

## 2026-06-13 (RTF-073 Live Signal Shadow Planning Bridge)

- Worktree:
  `/Users/jiangwei/Documents/final-sprint6-integration`.
- Branch:
  `program/live-safe-v1`.
- Added:
  `scripts/runtime_live_signal_shadow_planning_bridge.py`.
- Added tests:
  `tests/unit/test_runtime_live_signal_shadow_planning_bridge.py`.
- Purpose:
  bridge an RTF-067 operator cycle or RTF-069 supervisor packet into the
  existing `next-attempt-strategy-plans` API flow only after the live signal
  path has reached current-runtime `ready_for_prepare`.
- Status handling:
  - `waiting_for_runtime_compatible_signal` /
    `supervisor_waiting_for_signal`:
    return `waiting_for_signal` and continue live signal supervision;
  - `ready_for_owner_runtime_profile_decision` /
    `supervisor_profile_review_required`:
    return `profile_review_required` and stop for runtime profile review;
  - `ready_for_prepare` / `supervisor_prepare_review_required`:
    call the non-executing next-attempt strategy planning flow;
  - `ready_for_final_gate_preflight` /
    `supervisor_final_gate_review_required`:
    preserve the existing FinalGate-ready path and do not re-plan;
  - forbidden source effects:
    block before strategy planning.
- Local fixture proof:
  - output:
    `output/rtf073-local/bridge-report.json`;
  - status:
    `ready_for_final_gate_preflight`;
  - order candidate:
    `order-candidate-rtf073-fixture`;
  - creates shadow candidate:
    `true`;
  - places order:
    `false`;
  - exchange write:
    `false`.
- Verification:
  - `pytest -q tests/unit/test_runtime_live_signal_shadow_planning_bridge.py tests/unit/test_runtime_next_attempt_strategy_plan_api_flow.py tests/unit/test_runtime_post_submit_next_attempt_cycle.py tests/unit/test_runtime_live_signal_operator_cycle.py tests/unit/test_runtime_live_signal_operator_supervisor.py`;
  - result:
    `25 passed`;
  - `pytest -q tests/unit/test_b0_runtime_strategy_signal_planning.py tests/unit/test_runtime_next_attempt_strategy_planning.py tests/unit/test_runtime_next_attempt_observation_api_prepare_flow.py`;
  - result:
    `24 passed`;
  - `python3 -m compileall -q scripts/runtime_live_signal_shadow_planning_bridge.py`;
  - `git diff --check`.
- Safety:
  - no prepare records are created by the bridge;
  - no recorded `ExecutionIntent`;
  - no submit authorization;
  - no local registration arm;
  - no exchange submit arm;
  - no order;
  - no `OrderLifecycle`;
  - no real submit;
  - no exchange write;
  - no runtime budget mutation;
  - no position open/close;
  - no withdrawal or transfer.
- Interpretation:
  - the live signal operator path can now re-enter strategy-driven shadow
    candidate planning without jumping directly into prepare/submit;
  - no-signal remains a normal waiting state;
  - the next mainline step is to deploy this bridge and run Tokyo integration
    in the current no-signal state, then continue observation until a genuine
    runtime-compatible signal appears.

## 2026-06-13 (RTF-074 Tokyo Shadow Planning Bridge No-signal Integration)

- Worktree:
  `/Users/jiangwei/Documents/final-sprint6-integration`.
- Branch:
  `program/live-safe-v1`.
- Commit deployed:
  `bcbd328308aedbaebd73129b634d51b088513ac4`.
- Previous Tokyo head:
  `09cadf270d29ecb434beae9a045fd1f131e47897`.
- New Tokyo release:
  `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-bcbd3283-20260613Trtf074-shadow-planning-bridge`.
- Deploy artifacts:
  - plan:
    `output/rtf074-tokyo/git-deploy-plan-bcbd3283.json`;
  - owner packet:
    `output/rtf074-tokyo/owner-git-deploy-packet-bcbd3283.json`;
  - dry-run:
    `output/rtf074-tokyo/git-deploy-dry-run-bcbd3283.json`;
  - apply:
    `output/rtf074-tokyo/git-deploy-applied-bcbd3283.json`.
- Deploy result:
  - status:
    `applied`;
  - blockers:
    `[]`;
  - commands:
    `16/16`;
  - backup:
    `/home/ubuntu/brc-deploy/backups/brc-runtime-governance-bcbd3283-20260613Trtf074-shadow-planning-bridge.pgdump`;
  - migrations:
    alembic command executed, migration count remained `84`;
  - service:
    restarted.
- Postdeploy read-only facts:
  - artifact:
    `output/rtf074-tokyo/readonly-probe-after-deploy.json`;
  - status:
    `ready_for_controlled_deploy_preflight`;
  - blockers:
    `[]`;
  - current head:
    `bcbd328308aedbaebd73129b634d51b088513ac4`;
  - health:
    `status=ok`, `runtime_bound=true`, `live_ready=false`.
- Postdeploy acceptance:
  - artifact:
    `output/rtf074-tokyo/postdeploy-acceptance-bcbd3283.json`;
  - status:
    `postdeploy_acceptance_passed`;
  - blockers:
    `[]`.
- Remote bridge verification:
  - input:
    `/home/ubuntu/brc-deploy/reports/rtf070-live-signal-supervisor/20260613Trtf070-9e15b81f/live-signal-operator-supervisor.json`;
  - remote output:
    `/home/ubuntu/brc-deploy/reports/rtf074-shadow-planning-bridge/20260613Trtf074-bcbd3283/live-signal-shadow-planning-bridge.json`;
  - local mirror:
    `output/rtf074-tokyo/remote-report-20260613Trtf074-bcbd3283/live-signal-shadow-planning-bridge.json`;
  - validation:
    `remote_bridge_validation=passed`;
  - status:
    `waiting_for_signal`;
  - runtime:
    `strategy-runtime-95655873b76c`;
  - next step:
    `continue_live_signal_operator_supervision`;
  - strategy planning flow:
    `null`;
  - uses official strategy planning API:
    `false`.
- Safety:
  - no strategy planning API call in no-signal state;
  - no prepare records;
  - no recorded `ExecutionIntent`;
  - no submit authorization;
  - no local registration arm;
  - no exchange submit arm;
  - no order;
  - no `OrderLifecycle`;
  - no real submit;
  - no exchange write;
  - no runtime budget mutation;
  - no position open/close;
  - no withdrawal or transfer.
- Interpretation:
  - RTF-073 is now deployed and verified on Tokyo;
  - the current no-signal market state safely bypasses shadow planning;
  - the bridge is ready to route a future runtime-compatible ready signal into
    shadow planning without crossing into prepare/submit.

## 2026-06-13 (RTF-075 Ready-signal Shadow Planning Contract Fixture)

- Worktree:
  `/Users/jiangwei/Documents/final-sprint6-integration`.
- Branch:
  `program/live-safe-v1`.
- Added:
  `scripts/runtime_ready_signal_shadow_planning_contract_fixture.py`.
- Added tests:
  `tests/unit/test_runtime_ready_signal_shadow_planning_contract_fixture.py`.
- Purpose:
  prove a deterministic ready-signal contract from live operator packet into
  real local shadow planning services, without waiting for live market signals
  and without entering prepare/submit.
- Contract path:
  - ready operator packet;
  - `runtime_live_signal_shadow_planning_bridge.py`;
  - real `RuntimeNextAttemptStrategyPlanningService`;
  - real `RuntimeStrategySignalPlanningService`;
  - shadow `SignalEvaluation`;
  - shadow `OrderCandidate`.
- Fixture:
  - strategy:
    `CPM-RO-001 / CPM-RO-001-v0`;
  - side:
    `long`;
  - runtime:
    `runtime-rtf075-cpm-long`;
  - symbol:
    `ETH/USDT:USDT`;
  - facts:
    trusted local position projection with `0` active positions and trusted
    cached account facts with clean reconciliation.
- Artifacts:
  - contract report:
    `output/rtf075-ready-signal-contract/contract-report.json`;
  - bridge report:
    `output/rtf075-ready-signal-contract/bridge-report.json`;
  - strategy planning flow:
    `output/rtf075-ready-signal-contract/bridge-artifacts/rtf075-ready-signal-strategy-planning-flow.json`;
  - signal input:
    `output/rtf075-ready-signal-contract/signal-input.json`;
  - operator packet:
    `output/rtf075-ready-signal-contract/operator-ready.json`;
  - post-submit finalize packet:
    `output/rtf075-ready-signal-contract/post-submit-finalize.json`.
- Contract result:
  - status:
    `ready_signal_shadow_planning_contract_passed`;
  - bridge status:
    `ready_for_final_gate_preflight`;
  - order candidate:
    `order-candidate-rtf075-contract`;
  - entry:
    `104.2`;
  - stop:
    `99.60`;
  - stop source:
    `cpm_pullback_low`;
  - intended notional:
    `10`;
  - leverage:
    `1`;
  - take-profit / runner:
    `tp1_partial` plus `runner`;
  - right-tail runner:
    `right_tail_capture=true`.
- Verification:
  - `python3 scripts/runtime_ready_signal_shadow_planning_contract_fixture.py --output-dir output/rtf075-ready-signal-contract`;
  - result:
    `ready_signal_shadow_planning_contract_passed`;
  - `pytest -q tests/unit/test_runtime_ready_signal_shadow_planning_contract_fixture.py tests/unit/test_runtime_live_signal_shadow_planning_bridge.py tests/unit/test_runtime_next_attempt_strategy_plan_api_flow.py`;
  - result:
    `13 passed`;
  - `pytest -q tests/unit/test_b0_runtime_strategy_signal_planning.py tests/unit/test_runtime_next_attempt_strategy_planning.py tests/unit/test_runtime_next_attempt_observation_api_prepare_flow.py`;
  - result:
    `24 passed`;
  - `python3 -m compileall -q scripts/runtime_ready_signal_shadow_planning_contract_fixture.py scripts/runtime_live_signal_shadow_planning_bridge.py`;
  - `git diff --check`.
- Safety:
  - fixture only;
  - no live exchange;
  - no prepare records;
  - no recorded `ExecutionIntent`;
  - no submit authorization;
  - no local registration arm;
  - no exchange submit arm;
  - no order;
  - no `OrderLifecycle`;
  - no real submit;
  - no exchange write;
  - no runtime budget mutation;
  - no position open/close;
  - no withdrawal or transfer.
- Interpretation:
  - the local contract now proves that a genuine ready signal can create a
    strategy-driven shadow candidate with entry/protection/exit/sizing
    semantics;
  - the path still stops before prepare/submit authority;
  - the next mainline step is to deploy this contract fixture to Tokyo and run
    it there as a deterministic ready-branch proof independent of current
    market no-signal conditions.

## 2026-06-13 (RTF-076 Tokyo Ready-signal Shadow Planning Contract Integration)

- Worktree:
  `/Users/jiangwei/Documents/final-sprint6-integration`.
- Branch:
  `program/live-safe-v1`.
- Deployed commit:
  `c09ac0b87a8a14895b999e3cd625cbf83f983c08`
  (`c09ac0b8`).
- Previous Tokyo head:
  `bcbd328308aedbaebd73129b634d51b088513ac4`
  (`bcbd3283`).
- Tokyo release:
  `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-c09ac0b8-20260613Trtf076-ready-signal-contract`.
- Deploy artifacts:
  - predeploy readonly probe:
    `output/rtf076-tokyo/readonly-probe-before-deploy.json`;
  - plan:
    `output/rtf076-tokyo/git-deploy-plan-c09ac0b8.json`;
  - owner packet:
    `output/rtf076-tokyo/owner-git-deploy-packet-c09ac0b8.json`;
  - dry-run:
    `output/rtf076-tokyo/git-deploy-dry-run-c09ac0b8.json`;
  - apply:
    `output/rtf076-tokyo/git-deploy-applied-c09ac0b8.json`.
- Deploy result:
  - status:
    `applied`;
  - blockers:
    `[]`;
  - commands:
    `16/16`;
  - backup:
    `/home/ubuntu/brc-deploy/backups/brc-runtime-governance-c09ac0b8-20260613Trtf076-ready-signal-contract.pgdump`;
  - migrations:
    alembic command executed, migration count remained `84`;
  - service:
    restarted.
- Postdeploy readonly facts:
  - artifact:
    `output/rtf076-tokyo/readonly-probe-after-deploy.json`;
  - status:
    `ready_for_controlled_deploy_preflight`;
  - blockers:
    `[]`;
  - warnings:
    `remote_release_identity_from_manifest_without_git_status`;
  - current head:
    `c09ac0b87a8a14895b999e3cd625cbf83f983c08`;
  - current realpath:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-c09ac0b8-20260613Trtf076-ready-signal-contract`;
  - migration count:
    `84`;
  - latest migration:
    `2026-06-11-084_create_runtime_post_submit_budget_settlements.py`.
- Postdeploy acceptance:
  - artifact:
    `output/rtf076-tokyo/postdeploy-acceptance-c09ac0b8.json`;
  - status:
    `postdeploy_acceptance_passed`;
  - blockers:
    `[]`;
  - warning:
    `release_identity_from_manifest_without_git_status`;
  - release identity:
    `c09ac0b87a8a14895b999e3cd625cbf83f983c08`
    from release manifest.
- Remote ready-signal contract fixture:
  - remote path:
    `/home/ubuntu/brc-deploy/reports/rtf076-ready-signal-contract/20260613Trtf076-c09ac0b8`;
  - local mirror:
    `output/rtf076-tokyo/remote-report-20260613Trtf076-c09ac0b8/`;
  - contract report:
    `output/rtf076-tokyo/remote-report-20260613Trtf076-c09ac0b8/contract-report.json`;
  - bridge report:
    `output/rtf076-tokyo/remote-report-20260613Trtf076-c09ac0b8/bridge-report.json`;
  - planning flow:
    `output/rtf076-tokyo/remote-report-20260613Trtf076-c09ac0b8/rtf075-ready-signal-strategy-planning-flow.json`;
  - stdout mirror:
    `output/rtf076-tokyo/remote-report-20260613Trtf076-c09ac0b8/contract-fixture.stdout.json`.
- Contract result:
  - status:
    `ready_signal_shadow_planning_contract_passed`;
  - bridge status:
    `ready_for_final_gate_preflight`;
  - order candidate:
    `order-candidate-rtf075-contract`;
  - strategy:
    `CPM-RO-001 / CPM-RO-001-v0`;
  - side:
    `long`;
  - entry:
    `104.2`;
  - stop:
    `99.60`;
  - stop source:
    `cpm_pullback_low`;
  - intended notional:
    `10`;
  - leverage:
    `1`;
  - take-profit / runner:
    `tp1_partial` plus `runner`;
  - right-tail runner:
    `right_tail_capture=true`.
- Verification:
  - remote fixture command:
    `/home/ubuntu/brc-deploy/venvs/brc-bnb-prelive-20260601/bin/python scripts/runtime_ready_signal_shadow_planning_contract_fixture.py --output-dir ...`;
  - remote validation:
    `remote_ready_contract_validation=passed`;
  - remote status:
    `ready_signal_shadow_planning_contract_passed`;
  - remote bridge status:
    `ready_for_final_gate_preflight`.
- Safety:
  - fixture-only ready branch proof;
  - trusted fixture facts;
  - no prepare records;
  - no recorded `ExecutionIntent`;
  - no submit authorization;
  - no local registration arm;
  - no exchange submit arm;
  - no order;
  - no `OrderLifecycle`;
  - no real submit;
  - no exchange write;
  - no runtime budget mutation;
  - no position open/close;
  - no withdrawal or transfer.
- Interpretation:
  - RTF-075 is now deployed and verified on Tokyo;
  - Tokyo can execute the deterministic ready-signal shadow planning contract
    and produce a strategy-driven shadow `OrderCandidate`;
  - the verified path reaches `ready_for_final_gate_preflight` and still stops
    before prepare, submit authorization, `ExecutionIntent`, order lifecycle,
    or exchange writes;
  - the next mainline gap is the controlled handoff from verified shadow
    candidate planning into prepare / FinalGate preflight without reviving
    one-shot manual evidence handling as the normal runtime loop.

## 2026-06-13 (RTF-077 Ready-signal Prepare Handoff Local Contract)

- Worktree:
  `/Users/jiangwei/Documents/final-sprint6-integration`.
- Branch:
  `program/live-safe-v1`.
- Added:
  `scripts/runtime_ready_signal_prepare_handoff_contract.py`.
- Added tests:
  `tests/unit/test_runtime_ready_signal_prepare_handoff_contract.py`.
- Purpose:
  prove a local contract from ready-signal shadow candidate planning into the
  official next-attempt prepare wrapper, stopping at FinalGate preflight shape
  before Tokyo integration or real submit.
- Contract path:
  - `runtime_ready_signal_shadow_planning_contract_fixture.py`;
  - ready operator packet;
  - `runtime_live_signal_shadow_planning_bridge.py`;
  - real `RuntimeNextAttemptStrategyPlanningService`;
  - real `RuntimeStrategySignalPlanningService`;
  - shadow `SignalEvaluation`;
  - shadow `OrderCandidate`;
  - official `runtime_next_attempt_prepare_api_flow.py` wrapper;
  - fake Console API client;
  - prepare-shape `RuntimeExecutionIntentDraft`;
  - prepare-shape `ExecutionIntent`;
  - prepare-shape protection plan;
  - prepare-shape submit authorization;
  - `ready_for_final_gate_preflight`.
- Artifacts:
  - stdout:
    `output/rtf077-ready-signal-prepare-handoff-contract.stdout.json`;
  - contract report:
    `output/rtf077-ready-signal-prepare-handoff-contract/contract-report.json`;
  - shadow contract mirror:
    `output/rtf077-ready-signal-prepare-handoff-contract/shadow-contract-report.json`;
  - prepare packet:
    `output/rtf077-ready-signal-prepare-handoff-contract/prepare-packet.json`;
  - nested shadow planning artifacts:
    `output/rtf077-ready-signal-prepare-handoff-contract/shadow-planning/`.
- Contract result:
  - status:
    `ready_signal_prepare_handoff_contract_passed`;
  - runtime:
    `runtime-rtf075-cpm-long`;
  - signal evaluation:
    `eval-rtf075-cpm-long`;
  - order candidate:
    `order-candidate-rtf075-contract`;
  - runtime execution intent draft:
    `draft-rtf077-prepare-handoff`;
  - execution intent:
    `intent-rtf077-prepare-handoff`;
  - protection plan:
    `protection-rtf077-prepare-handoff`;
  - prepared authorization:
    `auth-rtf077-prepare-handoff`;
  - next operator step:
    `run_official_final_gate_preflight`.
- Checks:
  - shadow contract passed:
    `true`;
  - shadow candidate created:
    `true`;
  - right-tail runner preserved:
    `true`;
  - prepare ready for FinalGate preflight:
    `true`;
  - next-attempt gate checked:
    `true`;
  - order candidate usage checked:
    `true`;
  - runtime execution intent draft shape created:
    `true`;
  - execution intent shape created:
    `true`;
  - protection plan shape created:
    `true`;
  - submit authorization shape created:
    `true`;
  - prepared authorization ID present:
    `true`.
- Verification:
  - `pytest -q tests/unit/test_runtime_ready_signal_prepare_handoff_contract.py tests/unit/test_runtime_ready_signal_shadow_planning_contract_fixture.py tests/unit/test_runtime_next_attempt_prepare_api_flow.py tests/unit/test_runtime_live_signal_shadow_planning_bridge.py`;
  - result:
    `19 passed`;
  - `python3 -m compileall -q scripts/runtime_ready_signal_prepare_handoff_contract.py tests/unit/test_runtime_ready_signal_prepare_handoff_contract.py`;
  - local dry-run:
    `python3 scripts/runtime_ready_signal_prepare_handoff_contract.py --output-dir output/rtf077-ready-signal-prepare-handoff-contract > output/rtf077-ready-signal-prepare-handoff-contract.stdout.json`;
  - dry-run result:
    `ready_signal_prepare_handoff_contract_passed`.
- Safety:
  - local contract only;
  - fake Console API client only;
  - no PG write;
  - no live exchange;
  - no local registration arm;
  - no exchange submit arm;
  - no real submit;
  - no exchange write;
  - no order;
  - no `OrderLifecycle`;
  - no attempt counter mutation;
  - no runtime budget mutation;
  - no position open/close;
  - no withdrawal or transfer.
- Interpretation:
  - the verified shadow `OrderCandidate` can now be handed into the official
    prepare wrapper contract and reach FinalGate preflight shape locally;
  - this is not Tokyo integration and not a real PG mutation claim;
  - the next mainline gap is to deploy this RTF-077 contract and verify the same
    prepare handoff shape on Tokyo before continuing toward executable runtime
    handoff.

## 2026-06-13 (RTF-078 Tokyo Ready-signal Prepare Handoff Integration)

- Worktree:
  `/Users/jiangwei/Documents/final-sprint6-integration`.
- Branch:
  `program/live-safe-v1`.
- Deployed commit:
  `026b690a2a53517272c0bca731260c47b5e9b2f8`
  (`026b690a`).
- Previous Tokyo head:
  `c09ac0b87a8a14895b999e3cd625cbf83f983c08`
  (`c09ac0b8`).
- Tokyo release:
  `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-026b690a-20260613Trtf078-prepare-handoff-contract`.
- Deploy artifacts:
  - predeploy readonly probe:
    `output/rtf078-tokyo-precheck-readonly.json`;
  - plan:
    `output/rtf078-tokyo/git-deploy-plan-026b690a.json`;
  - owner packet:
    `output/rtf078-tokyo/owner-git-deploy-packet-026b690a.json`;
  - dry-run:
    `output/rtf078-tokyo/git-deploy-dry-run-026b690a.json`;
  - apply:
    `output/rtf078-tokyo/git-deploy-applied-026b690a.json`.
- Deploy result:
  - status:
    `applied`;
  - blockers:
    `[]`;
  - commands:
    `16/16`;
  - backup:
    `/home/ubuntu/brc-deploy/backups/brc-runtime-governance-026b690a-20260613Trtf078-prepare-handoff-contract.pgdump`;
  - migrations:
    alembic command executed, migration count remained `84`;
  - service:
    restarted.
- Postdeploy readonly facts:
  - artifact:
    `output/rtf078-tokyo/readonly-probe-after-deploy.json`;
  - status:
    `ready_for_controlled_deploy_preflight`;
  - blockers:
    `[]`;
  - warning:
    `remote_release_identity_from_manifest_without_git_status`;
  - current head:
    `026b690a2a53517272c0bca731260c47b5e9b2f8`;
  - current realpath:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-026b690a-20260613Trtf078-prepare-handoff-contract`;
  - migration count:
    `84`;
  - latest migration:
    `2026-06-11-084_create_runtime_post_submit_budget_settlements.py`.
- Postdeploy acceptance:
  - artifact:
    `output/rtf078-tokyo/postdeploy-acceptance-026b690a.json`;
  - status:
    `postdeploy_acceptance_passed`;
  - blockers:
    `[]`;
  - warning:
    `release_identity_from_manifest_without_git_status`;
  - release identity:
    `026b690a2a53517272c0bca731260c47b5e9b2f8`
    from release manifest.
- Remote ready-signal prepare handoff contract:
  - remote path:
    `/home/ubuntu/brc-deploy/reports/rtf078-ready-signal-prepare-handoff/20260613Trtf078-026b690a`;
  - local mirror:
    `output/rtf078-tokyo/remote-report-20260613Trtf078-026b690a/`;
  - contract report:
    `output/rtf078-tokyo/remote-report-20260613Trtf078-026b690a/contract-report.json`;
  - prepare packet:
    `output/rtf078-tokyo/remote-report-20260613Trtf078-026b690a/prepare-packet.json`;
  - shadow contract report:
    `output/rtf078-tokyo/remote-report-20260613Trtf078-026b690a/shadow-contract-report.json`;
  - shadow planning contract report:
    `output/rtf078-tokyo/remote-report-20260613Trtf078-026b690a/shadow-planning-contract-report.json`;
  - stdout mirror:
    `output/rtf078-tokyo/remote-report-20260613Trtf078-026b690a/contract.stdout.json`.
- Contract result:
  - status:
    `ready_signal_prepare_handoff_contract_passed`;
  - runtime:
    `runtime-rtf075-cpm-long`;
  - signal evaluation:
    `eval-rtf075-cpm-long`;
  - order candidate:
    `order-candidate-rtf075-contract`;
  - runtime execution intent draft:
    `draft-rtf077-prepare-handoff`;
  - execution intent:
    `intent-rtf077-prepare-handoff`;
  - protection plan:
    `protection-rtf077-prepare-handoff`;
  - prepared authorization:
    `auth-rtf077-prepare-handoff`;
  - next operator step:
    `run_official_final_gate_preflight`.
- Checks:
  - shadow contract passed:
    `true`;
  - shadow candidate created:
    `true`;
  - right-tail runner preserved:
    `true`;
  - prepare ready for FinalGate preflight:
    `true`;
  - next-attempt gate checked:
    `true`;
  - order candidate usage checked:
    `true`;
  - runtime execution intent draft shape created:
    `true`;
  - execution intent shape created:
    `true`;
  - protection plan shape created:
    `true`;
  - submit authorization shape created:
    `true`;
  - prepared authorization ID present:
    `true`.
- Verification:
  - remote command:
    `/home/ubuntu/brc-deploy/venvs/brc-bnb-prelive-20260601/bin/python scripts/runtime_ready_signal_prepare_handoff_contract.py --output-dir ...`;
  - remote validation:
    `remote_prepare_handoff_validation=passed`;
  - remote status:
    `ready_signal_prepare_handoff_contract_passed`;
  - remote next step:
    `run_official_final_gate_preflight`.
- Safety:
  - remote contract uses fake Console API client;
  - no PG write by contract;
  - no live exchange;
  - no local registration arm;
  - no exchange submit arm;
  - no real submit;
  - no exchange write;
  - no order;
  - no `OrderLifecycle`;
  - no attempt counter mutation;
  - no runtime budget mutation;
  - no position open/close;
  - no withdrawal or transfer.
- Interpretation:
  - RTF-077 is now deployed and verified on Tokyo;
  - Tokyo can execute the deterministic ready-signal prepare handoff contract
    and reach FinalGate preflight shape;
  - this still proves a contract shape, not a real PG prepare mutation;
  - the next mainline gap is to replace the fake Console API contract boundary
    with an official server-side prepare integration proof while preserving the
    same no-submit safety invariants.

## 2026-06-13 (RTF-079 Official Server-side Prepare Integration Proof)

- Scope:
  - replace the fake Console API contract boundary from RTF-077 / RTF-078 with
    an in-process official server-side proof;
  - call the real Trading Console `FastAPI` routes through `TestClient`;
  - use real application services with in-memory repositories;
  - preserve the non-executing prepare boundary.
- Branch / worktree:
  - worktree:
    `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch:
    `program/live-safe-v1`.
- Added:
  - script:
    `scripts/runtime_official_server_prepare_integration_proof.py`;
  - tests:
    `tests/unit/test_runtime_official_server_prepare_integration_proof.py`.
- Local proof:
  - output dir:
    `output/rtf079-official-server-prepare-integration/`;
  - contract report:
    `output/rtf079-official-server-prepare-integration/contract-report.json`;
  - prepare packet:
    `output/rtf079-official-server-prepare-integration/prepare-packet.json`;
  - prepare report:
    `output/rtf079-official-server-prepare-integration/prepare-report.json`;
  - shadow contract report:
    `output/rtf079-official-server-prepare-integration/shadow-contract-report.json`;
  - stdout mirror:
    `output/rtf079-official-server-prepare-integration.stdout.json`.
- Contract result:
  - status:
    `official_server_prepare_integration_passed`;
  - runtime:
    `runtime-rtf075-cpm-long`;
  - signal evaluation:
    `signal-eval-rtf075-contract`;
  - order candidate:
    `order-candidate-rtf075-contract`;
  - runtime execution intent draft:
    `runtime-intent-draft-order-candidate-rtf075-contract`;
  - execution intent:
    `intent_rt_e23ebb969e9d27f79df197dc`;
  - protection plan:
    `runtime-protection-plan-intent_rt_e23ebb969e9d27f79df197dc`;
  - prepared authorization:
    `runtime-submit-authorization-intent_rt_e23ebb969e9d27f79df197dc`;
  - next operator step:
    `run_official_final_gate_preflight`.
- Official-route proof:
  - next-attempt gate checked through `/api/trading-console/owner-action-flow`;
  - order candidate usage checked through the official order-candidate route;
  - intent draft recorded through the official runtime execution intent draft
    route;
  - execution intent recorded through the official draft-to-intent route;
  - protection plan recorded through the official protection-plan route;
  - submit authorization recorded through the official submit-authorization
    route;
  - evidence preparation called through the official first-real-submit evidence
    preparation route.
- Evidence preparation:
  - status:
    `prepared_packet_blocked`;
  - packet created:
    `true`;
  - dependency blocked:
    `false`;
  - interpretation:
    the official first-real-submit packet can now be built in the in-process
    service proof, and remains blocked by live-action prerequisites rather than
    missing local service / repository dependencies.
- Checks:
  - shadow contract passed:
    `true`;
  - right-tail runner preserved:
    `true`;
  - official FastAPI routes used:
    `true`;
  - fake Console API used:
    `false`;
  - official prepare wrapper used:
    `true`;
  - next-attempt gate checked:
    `true`;
  - evidence preparation packet created:
    `true`;
  - evidence preparation dependency blocked:
    `false`;
  - prepare ready for FinalGate preflight:
    `true`;
  - trusted submit facts prepared:
    `true`;
  - submit idempotency prepared:
    `true`;
  - protection failure policy prepared:
    `true`.
- Verification:
  - focused tests:
    `pytest -q tests/unit/test_runtime_official_server_prepare_integration_proof.py tests/unit/test_runtime_ready_signal_shadow_planning_contract_fixture.py tests/unit/test_runtime_first_real_submit_api_flow.py`;
  - result:
    `29 passed`;
  - compile check:
    `python3 -m compileall -q scripts/runtime_official_server_prepare_integration_proof.py tests/unit/test_runtime_official_server_prepare_integration_proof.py`;
  - local dry-run:
    `python3 scripts/runtime_official_server_prepare_integration_proof.py --output-dir output/rtf079-official-server-prepare-integration`.
- Safety:
  - no PG write;
  - no live exchange;
  - no local registration arm;
  - no exchange submit arm;
  - no real submit;
  - no exchange write;
  - no order;
  - no `OrderLifecycle`;
  - no attempt counter mutation;
  - no runtime budget mutation;
  - no position open/close;
  - no withdrawal or transfer.
- Interpretation:
  - RTF-079 removes the fake Console API boundary for the prepare proof;
  - the prepare path now exercises official server routes and real application
    services under in-memory isolation;
  - this is still a local official-route integration proof, not Tokyo
    deployment and not real submit authorization;
  - the next mainline gap is Tokyo execution of the same official server-side
    prepare proof.

## 2026-06-13 (RTF-080 Tokyo Official Server-side Prepare Integration)

- Scope:
  - deploy the official server-side prepare proof to Tokyo;
  - run the same official `FastAPI` / `TestClient` prepare proof on the
    deployed release;
  - verify the server release, health, migration state, and non-executing proof
    invariants.
- Branch / worktree:
  - worktree:
    `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch:
    `program/live-safe-v1`.
- Deployment correction:
  - first apply attempt for `4a232a3d` failed during
    `2_owner_authorized_git_fetch_and_export`;
  - root cause:
    the git deploy plan compared `readlink -f app/current` absolute output to
    the short `previous_release` name;
  - fix:
    `scripts/plan_tokyo_runtime_governance_git_deploy.py` now expands a short
    previous release name to
    `/home/ubuntu/brc-deploy/releases/<release>`;
  - regression test:
    `test_git_deploy_plan_expands_short_previous_release_for_current_symlink_check`;
  - failed partial release cleanup:
    removed
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-4a232a3d-20260613Trtf080-official-server-prepare-proof`
    after confirming `app/current` still pointed to the RTF-078 release.
- Stage commit:
  - commit:
    `d0bfc271506e2418b23038f0128a146c345e4e61`;
  - message:
    `fix(deploy): normalize previous release symlink check`;
  - pushed:
    `origin/program/live-safe-v1`.
- Predeploy evidence:
  - readonly probe:
    `output/rtf080-predeploy-readonly.json`;
  - status:
    `ready_for_controlled_deploy_preflight`;
  - blockers:
    `[]`;
  - migration count:
    `84`.
- Deploy artifacts:
  - plan:
    `output/rtf080-tokyo/git-deploy-plan-d0bfc271.json`;
  - owner packet:
    `output/rtf080-tokyo/owner-git-deploy-packet-d0bfc271.json`;
  - dry-run:
    `output/rtf080-tokyo/git-deploy-dry-run-d0bfc271.json`;
  - apply:
    `output/rtf080-tokyo/git-deploy-applied-d0bfc271.json`.
- Deploy result:
  - status:
    `applied`;
  - blockers:
    `[]`;
  - commands:
    `16/16`;
  - release:
    `brc-runtime-governance-d0bfc271-20260613Trtf080-official-server-prepare-proof`;
  - release path:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-d0bfc271-20260613Trtf080-official-server-prepare-proof`;
  - migrations:
    alembic command executed, migration count remained `84`;
  - service:
    restarted.
- Postdeploy evidence:
  - verifier:
    `output/rtf080-tokyo/postdeploy-verify-d0bfc271.json`;
  - readonly probe:
    `output/rtf080-tokyo/readonly-probe-after-deploy.json`;
  - acceptance packet:
    `output/rtf080-tokyo/postdeploy-acceptance-d0bfc271.json`;
  - acceptance status:
    `postdeploy_acceptance_ready`;
  - blockers:
    `[]`;
  - warning:
    `release_identity_from_manifest_without_git_status`;
  - current head:
    `d0bfc271506e2418b23038f0128a146c345e4e61`;
  - health:
    `status=ok`, `runtime_bound=true`, `live_ready=false`;
  - migration count:
    `84`;
  - latest migration:
    `2026-06-11-084_create_runtime_post_submit_budget_settlements.py`.
- Remote official server-side prepare proof:
  - remote path:
    `/home/ubuntu/brc-deploy/reports/rtf080-official-server-prepare-proof/20260613Trtf080-d0bfc271`;
  - local mirror:
    `output/rtf080-tokyo/remote-report-20260613Trtf080-d0bfc271/`;
  - contract report:
    `output/rtf080-tokyo/remote-report-20260613Trtf080-d0bfc271/contract-report.json`;
  - prepare packet:
    `output/rtf080-tokyo/remote-report-20260613Trtf080-d0bfc271/prepare-packet.json`;
  - prepare report:
    `output/rtf080-tokyo/remote-report-20260613Trtf080-d0bfc271/prepare-report.json`;
  - shadow contract report:
    `output/rtf080-tokyo/remote-report-20260613Trtf080-d0bfc271/shadow-contract-report.json`;
  - stdout mirror:
    `output/rtf080-tokyo/remote-report-20260613Trtf080-d0bfc271/contract.stdout.json`.
- Contract result:
  - status:
    `official_server_prepare_integration_passed`;
  - runtime:
    `runtime-rtf075-cpm-long`;
  - signal evaluation:
    `signal-eval-rtf075-contract`;
  - order candidate:
    `order-candidate-rtf075-contract`;
  - runtime execution intent draft:
    `runtime-intent-draft-order-candidate-rtf075-contract`;
  - execution intent:
    `intent_rt_e23ebb969e9d27f79df197dc`;
  - protection plan:
    `runtime-protection-plan-intent_rt_e23ebb969e9d27f79df197dc`;
  - prepared authorization:
    `runtime-submit-authorization-intent_rt_e23ebb969e9d27f79df197dc`;
  - next operator step:
    `run_official_final_gate_preflight`.
- Evidence preparation:
  - status:
    `prepared_packet_blocked`;
  - packet created:
    `true`;
  - packet status:
    `blocked`;
  - dependency blocked:
    `false`;
  - blockers:
    `[]`.
- Checks:
  - shadow contract passed:
    `true`;
  - right-tail runner preserved:
    `true`;
  - official FastAPI routes used:
    `true`;
  - fake Console API used:
    `false`;
  - official prepare wrapper used:
    `true`;
  - next-attempt gate checked:
    `true`;
  - order candidate usage checked:
    `true`;
  - evidence preparation route called:
    `true`;
  - evidence preparation packet created:
    `true`;
  - evidence preparation dependency blocked:
    `false`;
  - prepare ready for FinalGate preflight:
    `true`;
  - trusted submit facts prepared:
    `true`;
  - submit idempotency prepared:
    `true`;
  - protection failure policy prepared:
    `true`.
- Safety:
  - proof uses official FastAPI routes;
  - proof does not use fake Console API;
  - proof uses in-memory repositories;
  - no PG write by proof;
  - no live exchange;
  - no local registration arm;
  - no exchange submit arm;
  - no real submit;
  - no exchange write;
  - no order;
  - no `OrderLifecycle`;
  - no attempt counter mutation;
  - no runtime budget mutation;
  - no position open/close;
  - no withdrawal or transfer.
- Verification:
  - local focused tests:
    `pytest -q tests/unit/test_tokyo_runtime_governance_git_deploy.py tests/unit/test_runtime_official_server_prepare_integration_proof.py`;
  - result:
    `13 passed`;
  - remote proof command:
    `/home/ubuntu/brc-deploy/venvs/brc-bnb-prelive-20260601/bin/python scripts/runtime_official_server_prepare_integration_proof.py --output-dir ...`;
  - remote status:
    `official_server_prepare_integration_passed`;
  - remote evidence status:
    `prepared_packet_blocked`.
- Interpretation:
  - RTF-080 deploys and verifies the official server-side prepare proof on
    Tokyo;
  - the fake Console API boundary from RTF-078 is no longer the server-side
    prepare proof boundary;
  - the next mainline gap is to move from prepare proof to official FinalGate
    preflight and then post-submit finalize / next-attempt gate convergence.

## 2026-06-13 (RTF-081 Official FinalGate Preflight Proof)

- Scope:
  - extend the RTF-079 official server-side prepare proof into official
    FinalGate preflight;
  - call official Trading Console `FastAPI` routes through `TestClient`;
  - prove the prepared authorization can reach `ready_for_controlled_submit_adapter`;
  - preserve non-executing boundaries.
- Branch / worktree:
  - worktree:
    `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch:
    `program/live-safe-v1`.
- Added:
  - script:
    `scripts/runtime_official_final_gate_preflight_proof.py`;
  - tests:
    `tests/unit/test_runtime_official_final_gate_preflight_proof.py`.
- Local proof:
  - output dir:
    `output/rtf081-official-final-gate-preflight/`;
  - contract report:
    `output/rtf081-official-final-gate-preflight/contract-report.json`;
  - preflight packet:
    `output/rtf081-official-final-gate-preflight/preflight-packet.json`;
  - FinalGate preview:
    `output/rtf081-official-final-gate-preflight/final-gate-preview.json`;
  - controlled submit plan:
    `output/rtf081-official-final-gate-preflight/controlled-submit-plan.json`;
  - controlled submit preflight:
    `output/rtf081-official-final-gate-preflight/controlled-submit-preflight.json`;
  - stdout mirror:
    `output/rtf081-official-final-gate-preflight.stdout.json`.
- Contract result:
  - status:
    `official_final_gate_preflight_passed`;
  - runtime:
    `runtime-rtf075-cpm-long`;
  - signal evaluation:
    `signal-eval-rtf075-contract`;
  - order candidate:
    `order-candidate-rtf075-contract`;
  - authorization:
    `runtime-submit-authorization-intent_rt_e23ebb969e9d27f79df197dc`;
  - execution intent:
    `intent_rt_e23ebb969e9d27f79df197dc`;
  - controlled submit plan:
    `runtime-controlled-submit-plan-runtime-submit-authorization-intent_rt_e23ebb969e9d27f79df197dc`;
  - controlled submit preflight:
    `runtime-controlled-submit-preflight-runtime-submit-authorization-intent_rt_e23ebb969e9d27f79df197dc`.
- Official-route proof:
  - Runtime FinalGate preview called through the official
    `/runtime-final-gate-preview/order-candidates/{order_candidate_id}` route;
  - controlled submit plan called through the official
    `/runtime-execution-controlled-submit-plans/authorizations/{authorization_id}`
    route;
  - controlled submit preflight called through the official
    `/runtime-execution-controlled-submit-preflights/authorizations/{authorization_id}`
    route.
- FinalGate / preflight result:
  - FinalGate verdict:
    `PASS`;
  - FinalGate blockers:
    `[]`;
  - controlled submit plan status:
    `ready_for_controlled_submit_adapter`;
  - controlled submit preflight status:
    `ready_for_controlled_submit_adapter`;
  - preflight final gate verdict:
    `PASS`;
  - preflight preview only:
    `true`;
  - preflight blockers:
    `[]`.
- Checks:
  - shadow contract passed:
    `true`;
  - right-tail runner preserved:
    `true`;
  - prepare authorization created:
    `true`;
  - FinalGate preview route called:
    `true`;
  - FinalGate verdict pass:
    `true`;
  - controlled submit plan route called:
    `true`;
  - controlled submit plan ready:
    `true`;
  - controlled submit preflight route called:
    `true`;
  - controlled submit preflight ready:
    `true`;
  - official FastAPI routes used:
    `true`;
  - fake Console API used:
    `false`.
- Verification:
  - focused tests:
    `pytest -q tests/unit/test_runtime_official_final_gate_preflight_proof.py tests/unit/test_runtime_official_server_prepare_integration_proof.py`;
  - result:
    `6 passed`;
  - compile check:
    `python3 -m compileall -q scripts/runtime_official_final_gate_preflight_proof.py tests/unit/test_runtime_official_final_gate_preflight_proof.py`;
  - local dry-run:
    `python3 scripts/runtime_official_final_gate_preflight_proof.py --output-dir output/rtf081-official-final-gate-preflight`.
- Safety:
  - no PG write;
  - no live exchange;
  - no local registration arm;
  - no exchange submit arm;
  - no real submit;
  - no exchange write;
  - no order;
  - no `OrderLifecycle`;
  - no attempt counter mutation;
  - no runtime budget mutation;
  - no position open/close;
  - no withdrawal or transfer.
- Interpretation:
  - RTF-081 proves the official server-side prepare output can pass Runtime
    FinalGate and controlled submit preflight locally;
  - this is still an in-memory official-route proof, not Tokyo deployment;
  - the next mainline gap is Tokyo verification of the same FinalGate preflight
    proof, then non-executing submit adapter preview / local registration
    boundary convergence.

## 2026-06-13 (RTF-082 Tokyo Official FinalGate Preflight Integration)

- Scope:
  - deploy the RTF-081 official FinalGate preflight proof to Tokyo;
  - run the same proof on the deployed release;
  - verify FinalGate `PASS` and controlled submit preflight readiness on Tokyo;
  - preserve non-executing boundaries.
- Branch / worktree:
  - worktree:
    `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch:
    `program/live-safe-v1`.
- Predeploy evidence:
  - readonly probe:
    `output/rtf082-predeploy-readonly.json`;
  - status:
    `ready_for_controlled_deploy_preflight`;
  - blockers:
    `[]`;
  - migration count:
    `84`.
- Deploy artifacts:
  - plan:
    `output/rtf082-tokyo/git-deploy-plan-afd8b214.json`;
  - Owner packet:
    `output/rtf082-tokyo/owner-git-deploy-packet-afd8b214.json`;
  - dry-run:
    `output/rtf082-tokyo/git-deploy-dry-run-afd8b214.json`;
  - apply:
    `output/rtf082-tokyo/git-deploy-applied-afd8b214.json`.
- Deploy result:
  - status:
    `applied`;
  - blockers:
    `[]`;
  - commands executed:
    `16/16`;
  - release:
    `brc-runtime-governance-afd8b214-20260613Trtf082-final-gate-preflight-proof`;
  - release path:
    `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-afd8b214-20260613Trtf082-final-gate-preflight-proof`;
  - migrations:
    alembic command executed and migration count remained `84`;
  - service:
    restarted.
- Postdeploy evidence:
  - verifier:
    `output/rtf082-tokyo/postdeploy-verify-afd8b214.json`;
  - readonly probe:
    `output/rtf082-tokyo/readonly-probe-after-deploy.json`;
  - acceptance packet:
    `output/rtf082-tokyo/postdeploy-acceptance-afd8b214.json`;
  - acceptance:
    `postdeploy_acceptance_ready`;
  - blockers:
    `[]`;
  - warning:
    `release_identity_from_manifest_without_git_status`;
  - current head:
    `afd8b214c3e57e42e0d3397c9b957291bcb424d1`;
  - health:
    `status=ok`, `runtime_bound=true`, `live_ready=false`;
  - migration count:
    `84`;
  - latest migration:
    `2026-06-11-084_create_runtime_post_submit_budget_settlements.py`.
- Remote official FinalGate preflight proof:
  - remote path:
    `/home/ubuntu/brc-deploy/reports/rtf082-official-final-gate-preflight/20260613Trtf082-afd8b214`;
  - local mirror:
    `output/rtf082-tokyo/remote-report-20260613Trtf082-afd8b214/`;
  - contract report:
    `output/rtf082-tokyo/remote-report-20260613Trtf082-afd8b214/contract-report.json`;
  - preflight packet:
    `output/rtf082-tokyo/remote-report-20260613Trtf082-afd8b214/preflight-packet.json`;
  - FinalGate preview:
    `output/rtf082-tokyo/remote-report-20260613Trtf082-afd8b214/final-gate-preview.json`;
  - controlled submit plan:
    `output/rtf082-tokyo/remote-report-20260613Trtf082-afd8b214/controlled-submit-plan.json`;
  - controlled submit preflight:
    `output/rtf082-tokyo/remote-report-20260613Trtf082-afd8b214/controlled-submit-preflight.json`.
- Contract result:
  - status:
    `official_final_gate_preflight_passed`;
  - runtime:
    `runtime-rtf075-cpm-long`;
  - signal evaluation:
    `signal-eval-rtf075-contract`;
  - order candidate:
    `order-candidate-rtf075-contract`;
  - authorization:
    `runtime-submit-authorization-intent_rt_e23ebb969e9d27f79df197dc`;
  - execution intent:
    `intent_rt_e23ebb969e9d27f79df197dc`;
  - controlled submit plan:
    `runtime-controlled-submit-plan-runtime-submit-authorization-intent_rt_e23ebb969e9d27f79df197dc`;
  - controlled submit preflight:
    `runtime-controlled-submit-preflight-runtime-submit-authorization-intent_rt_e23ebb969e9d27f79df197dc`;
  - next operator step:
    `build_non_executing_submit_adapter_preview`.
- FinalGate / preflight result:
  - FinalGate verdict:
    `PASS`;
  - FinalGate blockers:
    `[]`;
  - controlled submit plan status:
    `ready_for_controlled_submit_adapter`;
  - controlled submit preflight status:
    `ready_for_controlled_submit_adapter`;
  - preflight preview only:
    `true`;
  - preflight blockers:
    `[]`.
- Safety:
  - official FastAPI routes used:
    `true`;
  - fake Console API used:
    `false`;
  - no PG write by proof;
  - no live exchange;
  - no local registration arm;
  - no exchange submit arm;
  - no real submit;
  - no exchange write;
  - no order;
  - no `OrderLifecycle`;
  - no attempt counter mutation;
  - no runtime budget mutation;
  - no position open/close;
  - no withdrawal or transfer.
- Interpretation:
  - RTF-082 deploys and verifies official FinalGate preflight on Tokyo;
  - the current deployed server version is now `afd8b214`;
  - the next mainline gap is non-executing submit adapter preview / local
    registration boundary convergence.

## 2026-06-13 (RTF-083 Official Submit Adapter Preview / Local Registration Boundary Proof)

- Scope:
  - extend the official FinalGate preflight proof through official submit
    adapter preview;
  - prove attempt reservation / attempt mutation budget semantics with the
    right-tail max-loss budget model;
  - prove OrderLifecycle handoff and local order registration draft readiness;
  - keep local registration, OrderLifecycle, exchange submit, withdrawal, and
    transfer disabled.
- Branch / worktree:
  - worktree:
    `/Users/jiangwei/Documents/final-sprint6-integration`;
  - branch:
    `program/live-safe-v1`.
- Added:
  - script:
    `scripts/runtime_official_submit_adapter_preview_proof.py`;
  - tests:
    `tests/unit/test_runtime_official_submit_adapter_preview_proof.py`.
- Local proof:
  - output dir:
    `output/rtf083-official-submit-adapter-preview/`;
  - contract report:
    `output/rtf083-official-submit-adapter-preview/contract-report.json`;
  - boundary packet:
    `output/rtf083-official-submit-adapter-preview/submit-adapter-boundary-packet.json`;
  - submit adapter preview:
    `output/rtf083-official-submit-adapter-preview/submit-adapter-preview.json`;
  - attempt reservation preview:
    `output/rtf083-official-submit-adapter-preview/attempt-reservation-preview.json`;
  - attempt reservation:
    `output/rtf083-official-submit-adapter-preview/attempt-reservation.json`;
  - attempt mutation:
    `output/rtf083-official-submit-adapter-preview/attempt-mutation.json`;
  - OrderLifecycle handoff:
    `output/rtf083-official-submit-adapter-preview/order-lifecycle-handoff.json`;
  - OrderLifecycle adapter preview:
    `output/rtf083-official-submit-adapter-preview/order-lifecycle-adapter-preview.json`;
  - order registration draft preview:
    `output/rtf083-official-submit-adapter-preview/order-registration-draft-preview.json`.
- Contract result:
  - status:
    `official_submit_adapter_preview_passed`;
  - runtime:
    `runtime-rtf075-cpm-long`;
  - signal evaluation:
    `signal-eval-rtf075-contract`;
  - order candidate:
    `order-candidate-rtf075-contract`;
  - authorization:
    `runtime-submit-authorization-intent_rt_e23ebb969e9d27f79df197dc`;
  - execution intent:
    `intent_rt_e23ebb969e9d27f79df197dc`;
  - submit adapter preview:
    `runtime-submit-adapter-preview-runtime-submit-authorization-intent_rt_e23ebb969e9d27f79df197dc`;
  - attempt reservation:
    `runtime-attempt-reservation-runtime-submit-authorization-intent_rt_e23ebb969e9d27f79df197dc`;
  - attempt mutation:
    `runtime-attempt-mutation-runtime-attempt-reservation-runtime-submit-authorization-intent_rt_e23ebb969e9d27f79df197dc`;
  - OrderLifecycle handoff:
    `runtime-order-lifecycle-handoff-runtime-submit-authorization-intent_rt_e23ebb969e9d27f79df197dc`;
  - order registration draft preview:
    `runtime-order-registration-draft-preview-runtime-submit-authorization-intent_rt_e23ebb969e9d27f79df197dc`.
- Official-route proof:
  - submit adapter preview route called through:
    `/api/trading-console/runtime-execution-submit-adapter-previews/authorizations/{authorization_id}`;
  - attempt reservation preview route called through:
    `/api/trading-console/runtime-execution-attempt-reservation-previews/authorizations/{authorization_id}`;
  - attempt reservation route called through:
    `/api/trading-console/runtime-execution-attempt-reservations/authorizations/{authorization_id}`;
  - attempt mutation route called through:
    `/api/trading-console/runtime-execution-attempt-mutations/reservations/{reservation_id}`;
  - OrderLifecycle handoff route called through:
    `/api/trading-console/runtime-execution-order-lifecycle-handoff-drafts/authorizations/{authorization_id}`;
  - OrderLifecycle adapter preview route called through:
    `/api/trading-console/runtime-execution-order-lifecycle-adapter-previews/authorizations/{authorization_id}`;
  - order registration draft preview route called through:
    `/api/trading-console/runtime-execution-order-registration-draft-previews/authorizations/{authorization_id}`.
- Status chain:
  - FinalGate:
    `PASS`;
  - controlled submit preflight:
    `ready_for_controlled_submit_adapter`;
  - submit adapter preview:
    `inputs_ready_adapter_not_implemented`;
  - attempt reservation preview:
    `ready_to_reserve_attempt`;
  - attempt reservation:
    `pending_runtime_mutation`;
  - attempt mutation:
    `applied`;
  - OrderLifecycle handoff:
    `ready_for_order_lifecycle_adapter`;
  - OrderLifecycle adapter preview:
    `inputs_ready_registration_not_enabled`;
  - order registration draft preview:
    `inputs_ready_registration_draft_only`.
- Runtime budget semantics:
  - intended notional:
    `10`;
  - budget reservation basis:
    `max_loss_reference`;
  - budget reservation amount:
    `0.44145873`;
  - attempts used before / after:
    `0 -> 1`;
  - budget reserved before / after:
    `0 -> 0.44145873`;
  - this preserves the right-tail risk-capital objective: small bounded
    attempt loss budget is reserved without treating the whole notional as
    realized loss budget.
- Local registration boundary:
  - registration draft count:
    `2`;
  - entry registration draft count:
    `1`;
  - protection registration draft count:
    `1`;
  - local order registration enabled:
    `false`;
  - OrderLifecycle adapter implemented:
    `false`;
  - preview only:
    `true`.
- Verification:
  - focused tests:
    `pytest -q tests/unit/test_runtime_official_submit_adapter_preview_proof.py tests/unit/test_runtime_official_final_gate_preflight_proof.py`;
  - result:
    `6 passed`;
  - compile check:
    `python3 -m compileall -q scripts/runtime_official_submit_adapter_preview_proof.py tests/unit/test_runtime_official_submit_adapter_preview_proof.py`;
  - local dry-run:
    `python3 scripts/runtime_official_submit_adapter_preview_proof.py --output-dir output/rtf083-official-submit-adapter-preview`.
- Safety:
  - official FastAPI routes used:
    `true`;
  - fake Console API used:
    `false`;
  - no PG write by proof;
  - no live exchange;
  - no local registration execution;
  - no exchange submit arm;
  - no real submit;
  - no exchange write;
  - no order;
  - no `OrderLifecycle`;
  - no position open/close;
  - no withdrawal or transfer.
- Interpretation:
  - RTF-083 proves the runtime chain can advance from FinalGate preflight into
    submit adapter preview and local registration draft readiness without using
    the old server-side first-real-submit rehearsal as the main proof surface;
  - attempt consumption is explicit and budgeted by max-loss reference, not
    hidden inside a manual evidence step;
  - the next mainline gap is a scoped local-registration enablement / real
    adapter boundary that can move from draft-only to actual local CREATED
    order registration without calling exchange.
