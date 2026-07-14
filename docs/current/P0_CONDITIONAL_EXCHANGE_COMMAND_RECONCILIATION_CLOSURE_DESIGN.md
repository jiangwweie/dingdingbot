---
title: P0_CONDITIONAL_EXCHANGE_COMMAND_RECONCILIATION_CLOSURE_DESIGN
status: LOCAL_VERIFIED_DEPLOYMENT_PENDING
authority: docs/current/P0_CONDITIONAL_EXCHANGE_COMMAND_RECONCILIATION_CLOSURE_DESIGN.md
last_verified: 2026-07-14
---

# P0 Conditional Exchange Command Reconciliation Closure Design

## Decision Summary

The current Tokyo Release continues running and may accept new entries under its
existing policy and gates. This design does not pause StrategyGroups, disable
real submit, change a live profile, or intervene in the current server.

The engineering decision is to close one latent durable-command defect:

```text
persisted command role + order type
-> typed lookup request
-> venue-declared regular or conditional lookup
-> typed lookup result with exact view evidence
-> visibility-window decision
-> one durable command transition
-> source-specific domain-hold resolution only after proven truth
```

## Release-Review Remediation — 2026-07-14

Local review found a second inference of the required lookup view in the
application layer. It classified every `SL/RUNNER_SL + stop_market` command as
conditional even when the gateway's existing non-Binance adapter contract
correctly returned a regular client-id view.

The local correction is recorded in
`P0_RELEASE_REVIEW_FINDINGS_REMEDIATION_DESIGN.md`: one pure domain resolver
uses the typed canonical `exchange_id`, role, type, and command kind; both the
application and gateway consume it. A Binance wrong-view result remains a hard
stop, while a supported non-Binance regular-view result is no longer falsely
contradictory. No venue admission, profile, exchange write, migration, or live
policy change is introduced.

For Binance USDT-M, `ENTRY` and `TP1` remain regular-order lookups.
`SL` and `RUNNER_SL` with `order_type=stop_market` use the Algo Order endpoint
through `clientAlgoId`. The design extends the existing gateway and durable
exchange-command authority; it does not create a second reconciliation service,
order table, exchange snapshot, or retry authority.

## Current Authority And Confirmed Gap

The current command row already persists the exact facts required to select a
lookup path:

```text
exchange_id
gateway_symbol
order_role
order_type
client_order_id
command_kind
target_exchange_order_id
netting_domain_key
command_state
```

The current place-command reconciler ignores `order_role` and `order_type` and
calls `find_order_by_client_id(client_order_id, gateway_symbol)` for every
place command. The Binance gateway then supplies only `origClientOrderId` to
CCXT `fetch_order`. Current CCXT routing uses the regular futures order endpoint
unless a conditional flag or conditional identity is supplied.

After the existing 30-second visibility window, a `None` result becomes
`reconciled_absent`. That terminal transition resolves the command's domain
hold. Therefore a regular-view miss for an accepted conditional SL can be
misclassified as authoritative absence.

The defect is a missing required-view invariant, not a reason to redesign
protected submit or add generic retry.

## Target Invariants

1. A place-command lookup consumes the persisted command identity, role, and
   order type; it never guesses the exchange view from caller context.
2. A Binance conditional command is queried through the conditional Algo Order
   view using `clientAlgoId`.
3. A regular lookup never proves a conditional order absent.
4. Network failure, unsupported view, malformed payload, or incomplete identity
   remains `lookup_failed` or `hard_stopped`; it never becomes absence.
5. `reconciled_absent` requires the correct required view to complete after the
   existing visibility window.
6. Every terminal result persists the lookup view, identity kind, observed time,
   and normalized exchange identity in the existing `exchange_result` JSON.
7. A command resolves only its own `NettingDomainKey + source_kind + source_id`
   hold. No result clears another command or lifecycle hold.
8. Reconciliation never resubmits, cancels, replaces, sizes, or creates an
   order.
9. Single-command and bounded batch reconciliation use the same lookup and
   application functions.
10. Current server runtime and live policy remain unchanged until a separately
    approved deployment transition.

## Alternatives

| Option | Benefits | Failure Mode | Decision |
| --- | --- | --- | --- |
| Add `conditional=True` to selected call sites | Small patch | Keeps untyped booleans and duplicate caller inference; future roles can diverge | Reject |
| Scan normal and conditional open-order lists for every unknown command | Reuses existing complete snapshot | Cannot prove triggered, filled, canceled, or closed conditional order identity; adds broad reads | Reject |
| Pass one typed command lookup request into the existing gateway and use the venue-declared direct identity endpoint | Preserves command identity, supports closed/triggered Algo Orders, keeps one authority | Requires focused gateway and reconciliation refactor | Adopt |

## Typed Boundary

The pure models live in
`src/domain/ticket_bound_exchange_command.py` because they describe durable
command observation semantics and contain no I/O:

```python
class ExchangeOrderLookupView(str, Enum):
    REGULAR_ORDER = "regular_order"
    CONDITIONAL_ALGO_ORDER = "conditional_algo_order"
    COMPLETE_OPEN_ORDERS = "complete_open_orders"


class ExchangeOrderLookupStatus(str, Enum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    CANCEL_EFFECT_CONFIRMED = "cancel_effect_confirmed"


class ExchangeOrderLookupRequest(ExchangeCommandModel):
    exchange_id: str
    gateway_symbol: str
    command_kind: str
    order_role: str
    order_type: str
    client_order_id: str
    target_exchange_order_id: str | None = None


class ExchangeOrderLookupResult(ExchangeCommandModel):
    status: ExchangeOrderLookupStatus
    lookup_view: ExchangeOrderLookupView
    identity_kind: str
    observed_at_ms: int
    exchange_order_id: str | None = None
    client_order_id: str
    gateway_symbol: str
    exchange_status: str | None = None
```

`ExchangeOrderLookupResult.NOT_FOUND` means the required view completed and
returned an authoritative not-found response. Exceptions remain exceptions and
never masquerade as a typed not-found result.

## Lookup Selection

| Command kind | Role / type | Binance lookup | Identity | Terminal interpretation |
| --- | --- | --- | --- | --- |
| `place_order` | `ENTRY / market` | Regular futures order | `origClientOrderId` | Found or correct-view not found |
| `place_order` | `TP1 / limit` | Regular futures order | `origClientOrderId` | Found or correct-view not found |
| `place_order` | `SL / stop_market` | Futures Algo Order | `clientAlgoId` | Found or correct-view not found |
| `place_order` | `RUNNER_SL / stop_market` | Futures Algo Order | `clientAlgoId` | Found or correct-view not found |
| `cancel_order` | Any owned target | Complete normal + conditional open-order views | `target_exchange_order_id` | Target absent means cancel effect confirmed |

For non-Binance venues, the gateway retains its existing regular
`clientOrderId` behavior until that venue declares a conditional-order
capability. Unknown venue/type combinations fail closed; they do not silently
fall back to a regular view.

## Gateway Design

`ExchangeGateway.find_order_by_client_id` adopts this typed interface:

```text
find_order_by_client_id(
  request: ExchangeOrderLookupRequest,
  observed_at_ms: int keyword-only
) -> ExchangeOrderLookupResult
```

The Binance adapter uses:

```text
regular -> rest_exchange.fetch_order(
             None,
             gateway_symbol,
             params={"origClientOrderId": client_order_id},
           )

conditional -> rest_exchange.fapiPrivateGetAlgoOrder(
                 {"clientAlgoId": client_order_id}
               )
```

Conditional normalization reuses the field semantics already used by
`fetch_conditional_order_lineage`: `algoId`, `clientAlgoId`, `algoStatus`,
`symbol`, `orderType`, `positionSide`, and `actualOrderId`. The refactor may
extract one private normalizer but must not add another public conditional
repository. The venue contract is the Binance official
[Query Algo Order](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Query-Algo-Order)
endpoint, which accepts the conditional client identity rather than treating a
regular-order miss as conditional absence.

## Reconciliation Decision

`lookup_unknown_exchange_command` creates the typed request from the
persisted command and receives the typed result.

```text
FOUND with matching identity
-> reconciled_submitted

NOT_FOUND before visibility deadline
-> pending_visibility; hold remains

NOT_FOUND after visibility deadline
-> reconciled_absent; resolve this command hold only

required view error or malformed response
-> lookup_failed; command remains outcome_unknown; hold remains

wrong client id / symbol / exchange identity
-> hard_stopped; hard hold remains

CANCEL_EFFECT_CONFIRMED
-> reconciled_submitted for the durable cancel command
```

The visibility deadline remains anchored to the durable command's ambiguous
outcome time. The implementation must not extend the deadline by rewriting
`updated_at_ms` during a read-only lookup.

Both `run_one_unknown_exchange_command_reconciliation` and
`reconcile_unknown_exchange_commands` call the same functions:

```text
select
-> lookup_unknown_exchange_command
-> apply_unknown_exchange_command_decision
```

The duplicate batch-only place-order logic is removed.

## Absence Evidence

No migration is required. The existing `exchange_result` JSON stores:

```json
{
  "lookup_status": "not_found",
  "lookup_view": "conditional_algo_order",
  "identity_kind": "clientAlgoId",
  "client_order_id": "brc-example-client-id",
  "gateway_symbol": "SOL/USDT:USDT",
  "observed_at_ms": 0,
  "visibility_window_elapsed": true
}
```

For a found result it additionally stores `exchange_order_id`, exchange status,
and conditional `actualOrderId` when available. The JSON is command audit
evidence, not a new runtime source; command state remains authoritative.

## Critical Dependency Pin

The current Tokyo environment uses CCXT `4.5.56`, while the Release dependency
declares only `ccxt>=4.2.24`. This package pins:

```text
ccxt==4.5.56
```

The pin preserves the already-running Tokyo version rather than introducing an
upgrade. Focused adapter tests must certify that exact version before any
deployment plan is allowed to proceed. Full-environment lockfile work is out of
scope.

## Affected Files

| File | Responsibility | Change |
| --- | --- | --- |
| `src/domain/ticket_bound_exchange_command.py` | Typed durable-command semantics | Add lookup request/result/view/status models |
| `src/infrastructure/exchange_gateway.py` | Venue read adapter | Route regular versus conditional client identity and normalize results |
| `src/application/action_time/exchange_command_reconciliation.py` | Unknown-outcome decision and hold transition | Consume typed result and unify single/batch paths |
| `src/application/action_time/exchange_command.py` | Durable result persistence | Preserve lookup evidence in existing `exchange_result` only if a focused helper is needed |
| `requirements.txt` | Production critical dependency | Pin CCXT `4.5.56` |
| `tests/unit/test_phase5e_exchange_gateway_min_notional.py` | Direct client-id lookup tests | Cover regular and conditional routing |
| `tests/unit/test_ticket_bound_exchange_command_reconciliation.py` | Durable state/hold tests | Cover four roles, cancel, failures, identity, and visibility |
| `tests/unit/test_exchange_gateway_open_order_views.py` | Complete cancel visibility | Preserve required-view failure propagation |
| `scripts/verify_tokyo_runtime_governance_postdeploy.py` | Exact deployed environment verification | Assert CCXT version without reading secrets |
| `tests/unit/test_tokyo_runtime_governance_postdeploy_verify.py` | Deploy verifier contract | Prove version mismatch blocks acceptance |
| `tests/unit/test_critical_exchange_dependency_pin.py` | Packaged dependency contract | Require one exact CCXT pin |

## Verification Matrix

| Dimension | Required cases |
| --- | --- |
| Role | `ENTRY`, `TP1`, `SL`, `RUNNER_SL` |
| Command kind | Place, cancel |
| Result | Found, not found before window, not found after window, network error, rate limit, malformed response |
| Identity | Exact, wrong client id, wrong symbol, missing exchange id, wrong gateway account/exchange |
| View | Regular, conditional Algo, complete normal + conditional open orders, required-view failure |
| Lifecycle effect | Hold retained, own hold resolved, other hold preserved, lifecycle completion applied once |
| Idempotency | Repeated worker, concurrent single/batch selection, no resubmit, no duplicate transition |
| Dependency | Local and packaged CCXT exactly `4.5.56` |

## Cadence And Performance

| Boundary | Required behavior |
| --- | --- |
| No unknown commands | One bounded PG select; zero gateway calls; zero writes/files |
| Unknown place command | One direct venue identity lookup per worker invocation |
| Unknown Binance cancel | One normal and one conditional open-order read through the existing complete view |
| PG growth | No new table and no per-tick row; one existing command row transition plus existing lifecycle event only on state change |
| Network | Existing explicit per-call and global lifecycle worker deadlines remain authoritative |
| Disk | Zero JSON/MD/YAML/JSONL output |
| Retention | Existing command/event retention only |

## Rollout And Rollback

Document approval authorizes local implementation and verification only. It
does not authorize Tokyo deployment because the current Owner decision is to
keep the present server Release running without intervention.

After a separate deployment approval:

1. Deploy the exact tested commit through the current Tokyo contract.
2. Verify exact CCXT version, service/timer health, and no unexpected active
   unknown commands using read-only checks.
3. Do not create a synthetic production command or exchange order.
4. If the new reader fails, forward-fix or return to the prior code release;
   never delete command rows or clear holds to make rollback appear clean.
5. Any command whose exchange effect may have occurred remains conserved for
   reconciliation.

## Owner And Authority Boundary

- Owner action required for technical design: no.
- Owner action required before local implementation: confirmation of this draft.
- Owner action required before Tokyo deployment: yes, because the current
  explicit instruction is to keep the server's current version running.
- Real-submit policy, capital, leverage, notional, StrategyGroup, symbol, side,
  FinalGate, and Operation Layer are unchanged.
- No `emergency_reduce` authority is added.

## Acceptance

1. Conditional client identity reaches the Binance Algo Order endpoint.
2. A regular-view miss cannot settle a conditional command as absent.
3. Correct-view failure retains `outcome_unknown` and the domain hold.
4. Correct-view absence after the visibility window records typed evidence and
   resolves only the matching hold.
5. Single and batch reconciliation produce identical decisions.
6. Cancel reconciliation uses complete normal + conditional visibility.
7. No reconciliation path calls place, cancel, replace, profile, sizing,
   withdrawal, or transfer APIs.
8. CCXT `4.5.56` is exact in local/package/deploy verification.
9. Production file-I/O risk remains clear.
10. No server change occurs before the separate deploy gate.

## Chain Position

```text
chain_position: action_time_boundary
strategy_group_id: current authorized WIP StrategyGroups
symbol: current authorized live-submit scopes
stage: local_verification_complete_deployment_pending
first_blocker: conditional_exchange_command_absence_not_proven
evidence: persisted order_type and role exist, but the current place lookup uses only the regular client-order view
next_action: retain the current server Release until a separate deployment decision
stop_condition: every regular/conditional unknown outcome reaches one proven exchange truth or retains its exact hard blocker and hold
owner_action_required: separate deployment approval only
authority_boundary: no current-server intervention, no submit/cancel retry, no FinalGate or Operation Layer bypass, no scope/profile/sizing expansion
```
