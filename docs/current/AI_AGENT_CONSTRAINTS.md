---
title: AI_AGENT_CONSTRAINTS
status: CURRENT
last_verified: 2026-08-14
---

# AI Agent Constraints

## Objective

Agents must preserve one production-capable multi-position kernel, one
unbranched PostgreSQL authority, one Tokyo runtime, and complete the remaining
controlled real-funds terminal acceptance.

## Required Engineering Posture

- Prefer deletion and clean replacement for wrong runtime semantics. Exact
  data-compatible forward migrations preserve certified terminal lineage;
  runtime compatibility adapters remain forbidden.
- Delete or rewrite code, tests, migrations, fixtures, and deployment branches
  whose semantics are wrong or retired. Historical behavior is not a reason to
  add compatibility debt, preserve misleading names, or weaken current
  invariants.
- Do not patch around missing invariants; close the problem class in the shared
  kernel.
- Do not preserve tests whose expected behavior conflicts with accepted current
  semantics.
- Do not recreate retired modules, tables, commands, status stages, files, or
  deployment units.
- Do not claim a full chain from downstream fixtures that bypass the real
  producer boundary.

## Local-First Failure Discovery

- Prefer exposing defects in local automated verification rather than on the
  Tokyo server.
- Time, concurrency, lease, migration, worker-cadence, deployment-gate, and
  restart behavior must be exercised with production-shaped local tests, not
  synchronized fixtures that remove the real failure condition.
- PostgreSQL behavior uses disposable PostgreSQL; clean-rebuild deployment is
  rehearsed locally from an empty database through schema, seed, Universe
  installation, worker progression, certification, and Entry promotion.
- Recording exchange fakes must prove the exact read and mutation boundary.
  Local certification and warming tests perform zero exchange mutation.
- A server deployment verifies current external facts; it is not the primary
  environment for discovering deterministic program defects.

## Test Portfolio Lifecycle

Tests are a maintained product asset, not an append-only activity log. Every
new test must protect one current contract or production-shaped failure class.
When a behavior, schema generation, fixture path, or deployment branch is
replaced, the same change deletes or consolidates tests that no longer own a
distinct current boundary.

Use four verification tiers:

| Tier | Normal use | Required scope |
| --- | --- | --- |
| Focused | Red/green development and defect repair | Exact changed boundary and one regression |
| Fast | Routine local confidence | Unit, architecture, static analysis, and affected integration slice |
| Release | One frozen exact Kernel candidate | Complete unit, integration, full-chain, architecture, Ruff, Mypy, and diff checks |
| Periodic audit | Explicit final audit or scheduled maintenance | Cross-version migration, clean rebuild, retired-semantics scan, and other expensive whole-program proofs |

Do not run the Release tier after every small edit. Freeze the candidate first,
run the complete certification once, and reuse its exact-commit manifest during
deployment. A material increase in suite duration or fixture volume requires a
test-portfolio review that identifies overlap, obsolete generation coverage,
and opportunities to merge or delete tests; test count is not evidence of
quality.

## Core Boundaries

- Domain code is pure and uses `Decimal`.
- Core inputs are frozen named models with forbidden extra fields.
- PostgreSQL owns current state and append-only lineage.
- External I/O occurs outside open database transactions.
- Every exchange mutation originates from one durable Exchange Command.
- Unknown command outcome blocks redispatch until external truth resolves it.
- ENTRY rejection never creates another ENTRY generation.
- Partial ENTRY fill opens an incident and controlled flatten workflow.
- One active Ticket is allowed per Netting Domain.
- New ENTRY work is globally serialized while existing Ticket lifecycle work
  remains concurrent.

## Runtime Performance

- One no-signal tick creates zero JSON/Markdown files.
- Current facts and readiness are bounded upserts.
- Normal monitor and reconciliation cadence avoids duplicate append-only events.
- Runtime queries use exact keys or bounded actionable selectors.
- Venue, subprocess, SSH, and API calls are timeout-bounded.

## Authorization

The active goal authorizes local database destruction, reviewed Tokyo database
cutover, server operations, and controlled real-funds acceptance. Agents do not
need repeated chat confirmation for in-scope implementation steps.

Agents must still stop before exchange write for wrong identity, stale facts,
missing budget, missing protection, same-domain occupancy, unknown outcome,
account-mode mismatch, schema/code mismatch, credential mutation, withdrawal,
transfer, or a bypass of the official kernel path.

## Completion Evidence

Completion requires current evidence for:

1. multi-position and long/short isolation;
2. global ENTRY serialization;
3. typed live signal to immutable Ticket;
4. durable command, protection, exit, recovery, reconciliation, settlement,
   and review;
5. zero retired production imports and current document references;
6. one unbranched forward schema authority;
7. crash-safe and resume-safe regular release and flat compatible upgrade;
8. exact Tokyo commit/schema identity;
9. one terminal controlled real-funds Ticket;
10. a production-shaped local clean-rebuild rehearsal;
11. final requirement-by-requirement audit.
