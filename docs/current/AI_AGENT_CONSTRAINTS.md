---
title: AI_AGENT_CONSTRAINTS
status: CURRENT
last_verified: 2026-07-22
---

# AI Agent Constraints

## Objective

Agents must move the repository toward one production-capable multi-position
kernel, one clean PostgreSQL baseline, one Tokyo deployment, and one controlled
real-funds terminal lifecycle.

## Required Engineering Posture

- Prefer deletion and clean replacement over compatibility.
- Do not patch around missing invariants; close the problem class in the shared
  kernel.
- Do not preserve tests whose expected behavior conflicts with accepted current
  semantics.
- Do not recreate retired modules, tables, commands, status stages, files, or
  deployment units.
- Do not claim a full chain from downstream fixtures that bypass the real
  producer boundary.

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
6. one clean schema baseline;
7. crash-safe and resume-safe destructive cutover;
8. exact Tokyo commit/schema identity;
9. one terminal controlled real-funds Ticket;
10. final requirement-by-requirement audit.
