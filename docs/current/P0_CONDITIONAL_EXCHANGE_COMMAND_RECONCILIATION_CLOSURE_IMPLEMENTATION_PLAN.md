---
title: P0_CONDITIONAL_EXCHANGE_COMMAND_RECONCILIATION_CLOSURE_IMPLEMENTATION_PLAN
status: LOCAL_VERIFIED_DEPLOYMENT_PENDING
authority: docs/current/P0_CONDITIONAL_EXCHANGE_COMMAND_RECONCILIATION_CLOSURE_IMPLEMENTATION_PLAN.md
last_verified: 2026-07-14
---

# P0 Conditional Exchange Command Reconciliation Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` and execute inline under Codex ownership. Do not
> dispatch subagents. Steps use checkbox syntax for tracking.

**Goal:** Make every durable place/cancel command reconcile through its exact
regular or conditional venue identity without changing current live policy or
creating exchange writes.

**Architecture:** Add typed lookup request/result models to the existing durable
command domain, make the existing gateway select the correct Binance identity
endpoint, and make both reconciliation entry points consume one decision path.
Persist lookup evidence in the existing command JSON and pin the already-running
Tokyo CCXT version.

**Tech Stack:** Python 3, Pydantic v2, SQLAlchemy, PostgreSQL, pytest, CCXT
`4.5.56`, Binance USDT-M read-only order APIs.

## Global Constraints

- The current Tokyo Release continues running during local implementation.
- No Tokyo deploy, service restart, timer change, PG Policy change, or runtime
  mutation is authorized by approval of this implementation plan.
- No real-submit, profile, strategy, symbol, side, leverage, notional, sizing,
  FinalGate, Operation Layer, withdrawal, transfer, or credential change.
- Reconciliation performs exchange reads only; automatic resubmit/cancel/
  replace is forbidden.
- Extend the existing `brc_ticket_bound_exchange_commands` authority; no new
  table, repository, snapshot, report, or sidecar.
- Unknown, malformed, unsupported, or incomplete exchange truth fails closed
  and retains its source-specific hold.
- No production runtime JSON/MD/YAML/JSONL input or output.
- Every production code change follows RED -> GREEN -> REFACTOR.

## Execution Envelope

| Field | Value |
| --- | --- |
| Task ID | `P0-CXR-CLOSURE` |
| Chain Position | `action_time_boundary` |
| Live Enablement State Before | Current server Release running; unknown conditional absence not proven |
| Live Enablement State After | Local release candidate proves typed regular/conditional reconciliation; server remains unchanged |
| Blocker Removed | `conditional_exchange_command_absence_not_proven` locally |
| Capability Unlocked | Correct-view unknown-outcome reconciliation candidate for later deploy |
| Next Engineering Bottleneck | Owner-notification projection and delivery closure |
| Rehearsal Boundary | Mock/read-only exchange responses only; no Tokyo PG mutation or exchange write |
| Owner Confirmation Gate | Satisfied for local implementation |
| Tokyo Deployment Gate | Separate explicit approval after all local tasks pass |

### Task 1: Typed Exchange Lookup Contract

**Owner:** Codex

**Allowed files:**

- `src/domain/ticket_bound_exchange_command.py`
- `tests/unit/test_ticket_bound_exchange_command_reconciliation.py`

**Forbidden files:**

- Migrations
- Live profiles and policy tables
- Execution orchestrator, order lifecycle service, capital protection, and
  reconciliation core outside the listed command module

**Interfaces:**

- Produces `ExchangeOrderLookupView`.
- Produces `ExchangeOrderLookupStatus`.
- Produces `ExchangeOrderLookupRequest`.
- Produces `ExchangeOrderLookupResult`.

- [x] **Step 1: Add failing model tests**

```python
def test_conditional_lookup_request_conserves_role_type_and_identity():
    request = ExchangeOrderLookupRequest(
        exchange_id="binance_usdm",
        gateway_symbol="SOL/USDT:USDT",
        command_kind="place_order",
        order_role="SL",
        order_type="stop_market",
        client_order_id="brc-client-sl",
    )
    assert request.order_role == "SL"
    assert request.order_type == "stop_market"


def test_lookup_result_requires_identity_for_found_status():
    with pytest.raises(ValueError):
        ExchangeOrderLookupResult(
            status="found",
            lookup_view="conditional_algo_order",
            identity_kind="clientAlgoId",
            observed_at_ms=1,
            client_order_id="brc-client-sl",
            gateway_symbol="SOL/USDT:USDT",
        )
```

- [x] **Step 2: Run the exact RED tests**

```bash
python3 -m pytest -q \
  tests/unit/test_ticket_bound_exchange_command_reconciliation.py \
  -k 'lookup_request or lookup_result'
```

Expected: collection/import failure because the typed models do not exist.

- [x] **Step 3: Implement the frozen Pydantic models** using the exact names
  and fields in the design. Add a model validator requiring
  `exchange_order_id` when `status=found`.

- [x] **Step 4: Run the RED tests again** and require PASS.

- [x] **Step 5: Commit the independently reviewable domain contract**

```bash
git add src/domain/ticket_bound_exchange_command.py \
  tests/unit/test_ticket_bound_exchange_command_reconciliation.py
git commit -m "feat: type exchange command lookup evidence"
```

**Done When:** The models reject incomplete found identity, preserve
regular/conditional view evidence, and import no I/O framework.

**Hard Stop:** Stop if the model requires a migration, exchange call, or a
second command-state authority.

### Task 2: Venue-Correct Gateway Lookup

**Owner:** Codex; `src/infrastructure/exchange_gateway.py` is a core file.

**Allowed files:**

- `src/infrastructure/exchange_gateway.py`
- `tests/unit/test_phase5e_exchange_gateway_min_notional.py`
- `tests/unit/test_exchange_gateway_open_order_views.py`

**Interfaces:**

- Consumes `ExchangeOrderLookupRequest`.
- Produces `ExchangeOrderLookupResult` from `find_order_by_client_id`.
- Preserves `fetch_all_open_orders` failure propagation.

- [x] **Step 1: Add exact failing routing tests**

```python
@pytest.mark.asyncio
async def test_binance_conditional_client_lookup_uses_algo_order_endpoint():
    result = await gateway.find_order_by_client_id(
        ExchangeOrderLookupRequest(
            exchange_id="binance_usdm",
            gateway_symbol="ETH/USDT:USDT",
            command_kind="place_order",
            order_role="SL",
            order_type="stop_market",
            client_order_id="brc-client-sl",
        ),
        observed_at_ms=10_000,
    )
    assert rest.algo_calls == [{"clientAlgoId": "brc-client-sl"}]
    assert rest.fetch_order_calls == []
    assert result.lookup_view.value == "conditional_algo_order"


@pytest.mark.asyncio
async def test_binance_regular_client_lookup_does_not_call_algo_endpoint():
    result = await gateway.find_order_by_client_id(
        ExchangeOrderLookupRequest(
            exchange_id="binance_usdm",
            gateway_symbol="ETH/USDT:USDT",
            command_kind="place_order",
            order_role="ENTRY",
            order_type="market",
            client_order_id="brc-client-entry",
        ),
        observed_at_ms=10_000,
    )
    assert rest.fetch_order_calls[0][2] == {
        "origClientOrderId": "brc-client-entry"
    }
    assert rest.algo_calls == []
    assert result.lookup_view.value == "regular_order"
```

- [x] **Step 2: Run the exact gateway tests**

```bash
python3 -m pytest -q \
  tests/unit/test_phase5e_exchange_gateway_min_notional.py \
  tests/unit/test_exchange_gateway_open_order_views.py \
  -k 'client_lookup or find_order_by_client_id or complete_open_order'
```

Expected: FAIL because the gateway still accepts two strings and always uses
the regular view.

- [x] **Step 3: Implement exact routing**

```python
async def find_order_by_client_id(
    self,
    request: ExchangeOrderLookupRequest,
    *,
    observed_at_ms: int,
) -> ExchangeOrderLookupResult:
    if self.exchange_name.lower() == "binance" and (
        request.order_type == "stop_market"
    ):
        raw = await self.rest_exchange.fapiPrivateGetAlgoOrder(
            {"clientAlgoId": request.client_order_id}
        )
        return self._conditional_lookup_result(
            request=request,
            raw=raw,
            observed_at_ms=observed_at_ms,
        )
    params = (
        {"origClientOrderId": request.client_order_id}
        if self.exchange_name.lower() == "binance"
        else {"clientOrderId": request.client_order_id}
    )
    raw = await self.rest_exchange.fetch_order(
        None,
        request.gateway_symbol,
        params=params,
    )
    return self._regular_lookup_result(
        request=request,
        raw=raw,
        observed_at_ms=observed_at_ms,
    )
```

The final implementation must preserve existing exception translation and use
`clientOrderId` rather than `origClientOrderId` for non-Binance venues.

- [x] **Step 4: Add not-found, malformed response, wrong client identity, and
  wrong symbol tests** for both views.

- [x] **Step 5: Run all three focused gateway test files** and require PASS.

- [x] **Step 6: Commit the gateway change**

```bash
git add src/infrastructure/exchange_gateway.py \
  tests/unit/test_phase5e_exchange_gateway_min_notional.py \
  tests/unit/test_exchange_gateway_open_order_views.py
git commit -m "fix: query conditional commands by algo identity"
```

**Done When:** A Binance conditional lookup never calls the regular endpoint,
and a required-view error never returns `NOT_FOUND`.

**Hard Stop:** Stop if the implementation needs raw secret access, order
mutation, a broad new gateway abstraction, or support for an unverified venue.

### Task 3: One Unknown-Outcome Reconciliation Decision Path

**Allowed files:**

- `src/application/action_time/exchange_command_reconciliation.py`
- `src/application/action_time/exchange_command.py` only for a focused existing
  row evidence helper
- `tests/unit/test_ticket_bound_exchange_command_reconciliation.py`

**Interfaces:**

- Consumes typed gateway lookup results.
- Produces existing command states and existing source-specific hold changes.
- Makes `reconcile_unknown_exchange_commands` reuse
  `lookup_unknown_exchange_command` and
  `apply_unknown_exchange_command_decision`.

- [x] **Step 1: Replace the ENTRY-only fixture with a role-aware fixture** named
  `_unknown_place_command(conn, *, order_role: str) -> dict`. Reuse the existing
  protected-submit fixture, select the requested persisted role, transition
  that exact row through `dispatching -> outcome_unknown`, and return the row
  including `order_type` and `client_order_id`. The helper may not write
  production files or invoke a gateway.

- [x] **Step 2: Add parameterized RED coverage**

```python
@pytest.mark.parametrize(
    "order_role,expected_view",
    [
        ("ENTRY", "regular_order"),
        ("TP1", "regular_order"),
        ("SL", "conditional_algo_order"),
        ("RUNNER_SL", "conditional_algo_order"),
    ],
)
@pytest.mark.asyncio
async def test_unknown_place_command_uses_persisted_required_view(
    pg_control_connection,
    order_role,
    expected_view,
):
    command = _unknown_place_command(
        pg_control_connection,
        order_role=order_role,
    )
    report = await reconcile_unknown_exchange_commands(
        pg_control_connection,
        gateway=_TypedLookupGateway.found(expected_view, command),
        now_ms=NOW_MS + 5_000,
        max_commands=10,
    )
    assert report["reconciled_submitted"] == 1
    assert _command_state(pg_control_connection, order_role) == (
        "reconciled_submitted"
    )
```

- [x] **Step 3: Add RED safety tests** proving:
  - conditional regular-view evidence is rejected;
  - not found before 30 seconds remains pending;
  - correct-view not found after 30 seconds becomes absent;
  - lookup failure keeps `outcome_unknown` and its hold;
  - terminal absence resolves only the matching hold;
  - a cancel target missing from a complete two-view snapshot confirms cancel;
  - single and batch functions return the same decision;
  - no gateway place/cancel method is called.

- [x] **Step 4: Run the reconciliation file and observe RED**

```bash
python3 -m pytest -q \
  tests/unit/test_ticket_bound_exchange_command_reconciliation.py
```

- [x] **Step 5: Implement request construction and one shared decision path**.
  Terminal `exchange_result` must include `lookup_status`, `lookup_view`,
  `identity_kind`, `client_order_id`, `gateway_symbol`, `observed_at_ms`, and
  `visibility_window_elapsed`.

- [x] **Step 6: Run the reconciliation and domain-hold focused suites**

```bash
python3 -m pytest -q \
  tests/unit/test_ticket_bound_exchange_command_reconciliation.py \
  tests/unit/test_ticket_bound_exchange_command.py \
  tests/unit/test_netting_domain_hold.py
```

Expected: PASS with no exchange write and no automatic resubmit.

- [x] **Step 7: Commit the reconciliation closure**

```bash
git add src/application/action_time/exchange_command_reconciliation.py \
  src/application/action_time/exchange_command.py \
  tests/unit/test_ticket_bound_exchange_command_reconciliation.py
git commit -m "fix: conserve conditional command reconciliation truth"
```

**Done When:** Every terminal command result names the completed lookup view;
all incomplete views retain the hold; single and batch logic are identical.

**Hard Stop:** Stop if a test requires clearing all scope holds, retrying an
exchange mutation, or changing a lifecycle state without exact command
identity.

### Task 4: Pin And Certify The Critical CCXT Version

**Allowed files:**

- `requirements.txt`
- `scripts/verify_tokyo_runtime_governance_postdeploy.py`
- `tests/unit/test_tokyo_runtime_governance_postdeploy_verify.py`
- `tests/unit/test_critical_exchange_dependency_pin.py`

- [x] **Step 1: Add a RED dependency assertion** that parses
  `requirements.txt` and requires exactly `ccxt==4.5.56`.

- [x] **Step 2: Run the dependency assertion** and observe failure against
  `ccxt>=4.2.24`.

- [x] **Step 3: Change only the critical exchange dependency**

```text
ccxt==4.5.56
```

- [x] **Step 4: Add a postdeploy read-only command**

```bash
python -c 'import ccxt; assert ccxt.__version__ == "4.5.56"; print(ccxt.__version__)'
```

The verification must print only the version and must not read exchange
credentials.

- [x] **Step 5: Run focused dependency and deploy-plan tests** and require PASS:

```bash
python3 -m pytest -q \
  tests/unit/test_critical_exchange_dependency_pin.py \
  tests/unit/test_tokyo_runtime_governance_postdeploy_verify.py
```

- [x] **Step 6: Commit the pin**

```bash
git add requirements.txt \
  scripts/verify_tokyo_runtime_governance_postdeploy.py \
  tests/unit/test_critical_exchange_dependency_pin.py \
  tests/unit/test_tokyo_runtime_governance_postdeploy_verify.py
git commit -m "build: pin certified ccxt adapter version"
```

**Done When:** Local test runtime, packaged dependency declaration, and planned
postdeploy verification all require `4.5.56`.

**Hard Stop:** Stop if pinning requires changing unrelated dependencies or
upgrading Tokyo before the separate deployment gate.

### Task 5: Package Verification And Merge Readiness

**Allowed files:** Tests and current package documents only.

- [x] **Step 1: Run targeted tests**

```bash
python3 -m pytest -q \
  tests/unit/test_ticket_bound_exchange_command_reconciliation.py \
  tests/unit/test_phase5e_exchange_gateway_min_notional.py \
  tests/unit/test_exchange_gateway_open_order_views.py \
  tests/unit/test_ticket_bound_exchange_command.py \
  tests/unit/test_netting_domain_hold.py \
  tests/unit/test_critical_exchange_dependency_pin.py \
  tests/unit/test_tokyo_runtime_governance_postdeploy_verify.py
```

- [x] **Step 2: Run lifecycle certification impact tests**

```bash
python3 -m pytest -q \
  tests/unit/test_ticket_bound_production_lifecycle_certification.py \
  tests/unit/test_ticket_bound_lifecycle_maintenance_service.py \
  tests/unit/test_ticket_bound_lifecycle_scheduler.py
```

- [x] **Step 3: Run the full suite** after focused tests pass and after the
  Owner's confirmation of this execution specification:

```bash
python3 -m pytest -q
```

- [x] **Step 4: Run mandatory audits**

```bash
python3 scripts/validate_current_docs_authority.py
python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked
python3 scripts/audit_production_runtime_file_io.py --fail-on-risk
python3 -m compileall -q src scripts tests
git diff --check
```

- [x] **Step 5: Review exact diff and test skips**. Any skipped conditional,
  hold, or unknown-outcome scenario is a package failure.

- [x] **Step 6: Commit verification evidence only in this plan's checkbox/
  evidence section after commands pass**. Do not write generated evidence files.

**Done When:** Targeted, impact, full, docs, output, file-I/O, compilation, and
diff checks pass with no unexplained skip and no runtime file artifact.

### Local Verification Evidence — 2026-07-14

| Scope | Evidence |
| --- | --- |
| Task 1 | `bea61438` — typed lookup contract |
| Task 2 | `278bc12c` — read-only regular/conditional venue routing |
| Task 3 | `ca3f80de` — shared unknown-outcome decision path and source-specific hold conservation |
| Task 4 | `97312d9e` — `ccxt==4.5.56` and read-only postdeploy version verification |
| Package tests | Certified local environment: `3085 passed, 1 skipped, 3 warnings, 0 failed` in `666.38s` |
| Certified adapter | `/tmp/brc-p0-cxr-certified-venv`: `ccxt.__version__ == 4.5.56` |
| Runtime boundaries | Current-doc, output-scope, production file-I/O, compilation, and diff checks passed; no production JSON/MD output added |
| Server boundary | No Tokyo SSH, deploy, restart, policy mutation, or exchange write was performed |

The one skipped full-suite test is in `test_trading_console_readmodels`; no
conditional-command, hold, or unknown-outcome scenario was skipped.

### Task 6: Deployment Preparation And Mandatory Stop

**Allowed actions:** Produce a deploy plan/dry-run and read-only preflight only.

- [ ] **Step 1: Generate the official Tokyo deploy dry-run** for the exact
  tested commit without applying it.

- [ ] **Step 2: Run read-only Tokyo preflight** for current head, migration
  count, health, timer state, and current CCXT version without reading secrets.

- [ ] **Step 3: Record the planned postdeploy checks**:
  - exact release head;
  - `ccxt==4.5.56`;
  - backend, watcher, monitor, and lifecycle timer health;
  - no new runtime files;
  - no synthetic signal, Ticket, command, or exchange write;
  - unknown commands and holds remain conserved.

- [ ] **Step 4: STOP before deploy apply, service restart, or server file
  change**. Wait for an explicit Owner instruction that supersedes
  `server_current_release_continues_live_operation`.

**Done When:** A deterministic deploy plan exists and the current server is
unchanged.

**Hard Stop:** No Tokyo apply, push-to-production transition, timer restart,
policy mutation, or exchange write is permitted in this plan's current draft
state.

## Package Done When

The local branch contains typed regular/conditional lookup evidence; Binance
SL/Runner commands use `clientAlgoId`; correct-view absence is the only absence
proof; single/batch reconciliation and domain holds are consistent; CCXT is
pinned to the existing Tokyo version; all tests and audits pass; and execution
stops with the current Tokyo Release unchanged pending a separate deployment
decision.
