# AGENTS.md - BRC Trading Kernel Operating Guide

Last updated: 2026-07-23
Current phase: Tokyo Controlled Real-Funds Acceptance

## Authority Order

When sources disagree, use this order:

1. Owner explicit decisions in the active task.
2. Current tracked code, current git state, and current machine configuration.
3. Current PostgreSQL and exchange readonly facts.
4. `docs/current/*`.
5. Historical material only when recovery is explicitly requested.

Start from:

```text
docs/current/PROJECT_INFORMATION_ARCHITECTURE.md
docs/current/OWNER_RUNTIME_OPERATING_MODEL.md
docs/current/AI_AGENT_CONSTRAINTS.md
docs/current/P0_TRADING_KERNEL_REBUILD_DESIGN.md
docs/current/P0_TRADING_KERNEL_REBUILD_IMPLEMENTATION_PLAN.md
docs/current/MAIN_CONTROL_ROADMAP.md
docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md
docs/current/RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md
docs/current/strategy-group-handoffs/STRATEGYGROUP_REGISTRY_CONTRACT.md
```

## Product Objective

The target is a single-Owner, small-capital, controlled real-profit experiment
system with one readable multi-position trading chain:

```text
Observation
-> StrategySignal
-> Readiness/Authority
-> CapacityClaim
-> immutable Ticket
-> durable Exchange Command
-> protected lifecycle
-> reconciliation
-> settlement
-> review
```

The Owner controls policy. The system performs normal operation. The Owner is
not required to assemble facts, approve each in-scope order, or operate internal
gates.

## Current Production Baseline

- Tokyo runs commit `f9fda21c91482b050e2a630e163f3213386ae6d7`.
- Remote production anchor `tokyo-runtime-2026.07.23.1` points permanently to
  that commit.
- Local certification at the deployed commit is `331 passed`, Ruff clean,
  Mypy clean, and production file-I/O audit clean.
- Runtime cadence is owned by four persistent systemd services: Observation,
  Entry, Lifecycle, and Reconciliation. Do not restore timer-based cold starts.
- Natural `SOR-001 / SOR-SHORT / SOLUSDT` acceptance Ticket
  `ticket:c1ebc24a178a3ae4d87978e2fa1204ae` is in protected lifecycle at the
  verified production snapshot.
- Full runtime policy promotion through `promote-full` remains blocked until
  that Ticket is terminal, exchange-flat, reconciled, settled, reviewed, and
  leaves zero incidents or residual orders.

## Final Business Semantics

- One Exposure Episode owns exactly one Ticket.
- Adding to an existing position is forbidden.
- One Ticket may produce only one ENTRY command generation.
- New ENTRY admission is globally serialized.
- Existing Tickets may protect, exit, reconcile, settle, and review concurrently.
- One active Ticket is allowed per Netting Domain:
  `venue + account + instrument + position_side`.
- Long and short are independent Netting Domains and may coexist by default.
- Supported accounts must expose independent long/short position sides.
- Multi-position capability is architectural; a fixed two-position ceiling is
  not part of the model. Current budget policy may still impose a configured
  capacity.
- Authoritative ENTRY rejection is terminal and is not retried.
- Unknown exchange outcome is never blindly resent.
- Partial ENTRY fill is an incident: cancel the exact remainder, confirm the
  cancellation, controlled-flatten the filled quantity, then release the lane.
- Strategy kill is performed only after exposure is already flat and terminal.

## Current Code Authority

Production execution code belongs only under:

```text
src/trading_kernel/**
```

The database baseline belongs only under:

```text
migrations/trading_kernel/**
```

Do not recreate retired application, domain, infrastructure, stage-table,
packet, proof-file, or compatibility generations. A missing capability must be
added to the kernel or rejected explicitly; it must not create a parallel chain.

## Data Authority

```text
Docs explain.
Registry defines strategy semantics.
Owner policy defines allowed scope and capital.
PostgreSQL stores current runtime truth and append-only lifecycle facts.
Exchange readonly facts reconcile external truth.
Generated output is display-only.
```

Production runtime must not read repository Markdown, JSON reports, local
caches, or output directories as authority. Production no-signal cadence must
create zero JSON/Markdown files.

## Engineering Rules

- Use test-first red/green/refactor for every production behavior.
- Delete tests that encode retired semantics; never weaken the new model to
  satisfy them.
- Keep domain code pure and free of SQLAlchemy, venue clients, filesystem,
  subprocess, and web frameworks.
- Use `decimal.Decimal` for financial values.
- Use frozen named Pydantic models at core boundaries.
- Keep network I/O outside database transactions.
- Persist every exchange write as one durable Exchange Command before dispatch.
- Use exact identities and bounded current-state queries; avoid full-history
  scans in runtime cadence.
- Mask credentials and sensitive values in logs and command output.
- Do not add dual writes, compatibility adapters, schema fallback, or old-table
  readers.

## Standing Authorization

The active rebuild goal authorizes:

- focused `codex/*` branches and local commits;
- destructive local/disposable PostgreSQL operations;
- reviewed Tokyo database cutover operations;
- server service, release, and deployment operations;
- readonly exchange/account/position/order verification;
- controlled in-scope real-funds acceptance after all current hard gates pass.

This authorization does not permit credential mutation, withdrawal, transfer,
scope expansion, sizing-default expansion, or safety-boundary bypass.

## Exchange-Write Hard Stops

Do not write to the exchange when any of these is true:

- wrong account, venue, instrument, side, runtime profile, or policy version;
- account does not expose independent long/short position sides;
- stale, missing, or contradictory action-time facts;
- same Netting Domain already owns a Ticket, position, order, or hold;
- budget or Initial Stop plan is missing;
- duplicate or unknown command outcome is unresolved;
- schema identity and deployed code identity disagree;
- old and new writers are both capable of mutation;
- the requested action would bypass the official kernel path.

## Cutover Rule

Cutover is destructive and forward-only after acceptance. For the completed
Tokyo rebuild, the Owner explicitly authorized deleting the BRC application,
container, PostgreSQL database data, releases, and services without backup,
while preserving every non-quantitative service. The rebuilt baseline is now
the only runtime authority; retired program or database generations must not be
restored.

## Git Discipline

- `dev` is integration, not a scratch branch.
- Rebuild work remains on focused `codex/*` branches until reviewed.
- Preserve unrelated user changes.
- Do not commit generated runtime output.
- Do not claim completion before the active acceptance Ticket is terminal and
  flat, all residual orders are absent, budget is released, Reconciliation,
  Settlement, and Review are complete, incident count is zero, `promote-full`
  is certified, and the final requirement audit passes.
