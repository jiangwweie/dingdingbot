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

# BNB Third Owner-Bounded Live Trial Post-Live Governance

Date: 2026-06-03

Mode: post-live governance, backend hardening, safety regression. No new live
order, cancel, replace, flatten, credential change, runtime start, or auto
execution action was performed by this governance pass.

## Baseline

- Local branch: `dev`
- Local baseline before this hardening pass: `51f0085b71f8ae4e3e2444da55022bfc9eea3fcb`
- Local tag at baseline: `brc-bnb-prelive-20260601-r35`
- Tokyo checkout: `brc-bnb-prelive-20260601-r35`
- Tokyo HEAD: `51f0085b71f8ae4e3e2444da55022bfc9eea3fcb`
- Code Alembic head: `041`
- Tokyo PG `alembic_version`: `041`
- Tokyo API health: `ok`
- Runtime flags observed through health: `runtime_bound=false`, `live_ready=false`

Rollback anchor before this governance pass:

- Git rollback tag: `brc-bnb-prelive-20260601-r35`
- Commit: `51f0085b71f8ae4e3e2444da55022bfc9eea3fcb`

Governed code baseline:

- Code hardening commit: `cc19d6fd`
- Code hardening tag: `brc-bnb-prelive-20260601-r36`
- Tokyo was checked out to `brc-bnb-prelive-20260601-r36` and backend was restarted
  with API health `ok`.

## Live Action Evidence

Third owner-bounded live action:

- Authorization: `auth-fc17cf5bbb0c42bbbcc231af5413faa0`
- Intent: `intent-e0043f28c99b4456bb14289568afd8ba`
- Carrier: `MI-001-BNB-LONG`
- Symbol: `BNB/USDT:USDT`
- Side: long
- Quantity: `0.01 BNB`
- Max notional: `20 USDT`
- Leverage: `1x`
- Protection: `single_tp_plus_sl`

Execution state recorded in PG:

- Authorization consumed: yes
- ExecutionIntent status: `completed`
- Entry PG order: `26e76738-2513-4cfb-9227-3c5d248f3125`
- Entry exchange order: `91085295446`
- Entry status: `FILLED`
- Entry filled quantity: `0.01`
- Entry average fill: `632.25`
- TP PG order: `b6e8456f-bc31-4945-b05f-399e39c05da9`
- TP exchange order: `91085295597`
- TP status: `OPEN`
- TP price: `638.570`
- SL PG order: `3b43781d-d81b-4288-b1ed-511b41b41f18`
- SL exchange algo/order: `4000001470395922`
- SL status: `OPEN`
- SL trigger: `625.92`
- Review: `review-auth-fc17cf5bbb0c42bbbcc231af5413faa0`
- Review status: `executed`
- Protection status: `protected`

Latest read-only exchange evidence at governance start:

- BNB position: long `0.01`
- Entry price: `632.25`
- Open TP order: `91085295597`, `SELL`, `LIMIT`, `positionSide=LONG`, quantity `0.01`
- Open SL order: `4000001470395922`, `SELL`, `STOP_MARKET`, `positionSide=LONG`, quantity `0.01`

Safety counts:

- ExecutionIntents for authorization: `1`
- Orders for authorization: `3`
- Entry orders: `1`
- TP orders: `1`
- SL orders: `1`
- Review rows: `1`
- Permission or auto-execution true count: `0`

## Audit Finding Repaired

The live PG authorization row was correctly `consumed=true`, but the review
JSON written by the success path recorded:

- `adapter_result.consumed=false`
- `final_state_snapshot.consumed=false`

Root cause: `OwnerBoundedExecutionService.execute_authorization` marked the PG
authorization consumed, then recorded the adapter response before copying the
final consumed state into the response object used by result logging.

Code repair:

- The success path now updates the response to `consumed=true` before writing
  the result/review envelope.
- The execution intent preview text now uses authorization cap/leverage fields
  instead of hard-coded `20 USDT; 1x`.
- The v1 adapter docstring now describes the current generic service plus
  strict v1 carrier mapping, rather than the older non-executable placeholder.

Regression added:

- `test_owner_bounded_execution_result_audit_records_consumed_final_state`
  uses the full `brc_execution_results` table shape and asserts both
  `adapter_result.consumed` and `final_state_snapshot.consumed` are true after
  a fake-gateway protected execution.

The existing Tokyo review row was a historical record written before this code
repair. A metadata-only PG correction was applied after deploying the code fix:

- Target row: `review-auth-fc17cf5bbb0c42bbbcc231af5413faa0`
- Guard condition: matching authorization id, `status='executed'`, and the
  authorization row already `consumed=true`
- Updated rows: `1`
- Before: `adapter_result.consumed=false`,
  `final_state_snapshot.consumed=false`
- After: `adapter_result.consumed=true`,
  `final_state_snapshot.consumed=true`

This correction touched only PG review JSON metadata. It did not touch exchange
orders, open protection orders, runtime permission, or credentials.

## Backend Generalization Audit

Generic and reusable backend surfaces already present:

- `OwnerBoundedExecutionService` loads PG authorization by id and owns:
  authorization reuse checks, duplicate intent classification, final gate
  recheck, protection plan readiness, result/review logging, and consumed state.
- `OwnerBoundedExecutionRegistry` maps carrier ids to execution adapters.
- `BoundedOrderExecutor` is a protocol; the API binds `ExchangeGateway` through
  `ExchangeGatewayBoundedOrderExecutor`.
- `ProtectionPlannerService` is config-driven by carrier id and persists
  auditable pre-entry and post-fill plans.
- Order/review binding uses authorization id, signal id, intent id, order ids,
  protection order ids, and PG result envelopes.
- Exchange order writes remain centralized through `ExchangeGateway`.

Intentionally v1-scoped surfaces:

- Registered live execution adapter: `MI-001-BNB-LONG` only.
- Protection planner default config: `MI-001-BNB-LONG` only.
- Final hard gate read model and read-only account fact source are BNB-named
  and use BNB symbol variants.
- `/owner-trial-flow/live-execution-bridge/dry-run` still returns the BNB
  final-gate response model.
- API route for execute is generic by authorization id, but the fact collector
  currently uses the BNB strategy profile for the v1 live path.

Classified coupling:

- Safe v1 boundary: carrier registry only exposes `MI-001-BNB-LONG`; unsupported
  BTC/ETH/SOL carriers fail closed before intent/order creation.
- Must generalize before future carrier live enablement: final-gate fact source,
  symbol conflict gate, scoped GKS/startup evidence mapping, and carrier
  protection config registration.
- Documentation-only in this pass: Owner Console frontend remains out of scope.

## Safety Regression Coverage

Covered by targeted tests and/or current read-only evidence:

- Consumed authorization reuse blocks before new intent/order.
- Duplicate execution intent blocks unless classified as retryable pre-order
  no-fill failure.
- Final hard gate failure blocks before intent/order.
- Scope mismatch and unsupported carrier block before intent/order.
- Missing protection price source blocks before intent/order.
- Protection success path records entry, TP, SL, fill-based protection plan, and
  consumed authorization.
- TP failure and SL failure record partial state and do not consume
  authorization.
- API converts unexpected owner-bounded execution exceptions to safe business
  status instead of raw 500.
- PG result/review write failure is reported as
  `execution_result_logging_failed` instead of silent success.
- Binance hedge-mode payload governance keeps exchange writes through
  `ExchangeGateway`.
- Permission and auto-execution flags remain false.

Current live protected-position state also proves repeat execution is blocked
by live read-only fact conflict:

- BNB position exists.
- BNB TP/SL open orders exist.
- Current owner flow has no unconsumed authorization.
- Final gate reports missing authorization plus position/open-order conflict.

## Commands And Results

Local:

- `git status -sb` showed `dev...origin/dev` plus this governance worktree.
- `python3 -m alembic heads` -> `041 (head)`
- `python3 -m pytest -q tests/unit/test_owner_trial_flow.py -k "owner_bounded_execution"` -> `17 passed, 35 deselected, 1 warning`
- `python3 -m compileall -q src scripts && python3 -m pytest -q tests/unit/test_owner_trial_flow.py tests/unit/test_protection_price_planner.py tests/unit/test_tiny001d1b_sl_metadata_validation.py tests/unit/test_execution_permission.py && python3 -m alembic heads && git diff --check` -> `81 passed, 1 warning`; Alembic `041 (head)`; diff check passed

Tokyo read-only:

- `git describe --tags --exact-match HEAD` -> `brc-bnb-prelive-20260601-r35`
- `git rev-parse HEAD` -> `51f0085b71f8ae4e3e2444da55022bfc9eea3fcb`
- `python -m alembic heads` -> `041 (head)`
- PG `alembic_version` -> `041`
- `GET /api/health` -> `ok`
- Live read-only facts showed BNB long `0.01` with TP and SL open.
- Deployment update: Tokyo checkout moved to `brc-bnb-prelive-20260601-r36`,
  HEAD `cc19d6f`; backend restarted and `GET /api/health` returned `ok`.
- Metadata correction: `brc_execution_results` review row updated from
  consumed false to consumed true in both `adapter_result` and
  `final_state_snapshot`.

## Remaining Risks / Non-Blockers

- Current live TP/SL remains open as intended protected state; it is background
  safety state, not a blocker for governance.
- The final-gate module is still BNB v1 named and should not be reused for
  BTC/ETH/SOL live execution until the fact collector and conflict gate are
  generalized.
- `brc-bnb-prelive-20260601-r36` contains the code fix and the first version of
  this governance report. A later documentation-only tag may point to the final
  report text that includes the completed Tokyo metadata correction.

## Safety Proof

- No new live order was placed during this governance pass.
- No live order was canceled, replaced, or flattened.
- No credential, API key, withdrawal, transfer, runtime start, or auto-execution
  setting was changed.
- Exchange access used for governance was read-only.
- The code change affects local PG result/review recording semantics and test
  coverage only.
