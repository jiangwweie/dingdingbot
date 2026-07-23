---
name: doc-manager
description: Use when cleaning, consolidating, validating, archiving, or updating repository documentation and current authority references.
---

# Document Manager

## Required Authority

Read:

- `AGENTS.md`
- `docs/current/PROJECT_INFORMATION_ARCHITECTURE.md`
- `docs/current/AI_AGENT_CONSTRAINTS.md`
- `tests/trading_kernel/architecture/test_current_document_authority.py`

## Core Principle

`docs/current` is a tested authority allowlist, not a general filing area.
Documents explain architecture and operating rules; they never become runtime
input or override tracked code, PostgreSQL, or exchange facts.

## Workflow

1. Inspect git state and preserve unrelated user changes.
2. Classify each requested document as current authority, explanatory history,
   or disposable generated output.
3. Write or update authority tests before changing the document set or reference
   rules; confirm the expected RED result.
4. Update the smallest coherent document set.
5. Repair all entry-document and project-Skill references.
6. Run current-document allowlist, reference, retired-semantics, and diff checks.
7. Report moved/deleted files and whether recovery is possible.

## Rules

| Document class | Required treatment |
| --- | --- |
| Current authority | Must be allowlisted, internally consistent, and referenced from approved entry points |
| Historical/provenance | Keep outside `docs/current`; never present it as current truth |
| Generated diagnostics | Disposable and never committed as authority |
| Missing reference | Remove or replace it with an existing current contract |

Do not run automatic scripts that move the whole documentation tree, generate
JSON indexes, or commit without reviewing the exact diff. Do not create new
authority documents when an existing contract can be updated.

## Current Chain Vocabulary

Use this chain consistently when a document describes execution:

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

## Hard Stops

- No production runtime reads from Markdown or generated documentation data.
- No resurrection of retired modules, tables, services, tests, or compatibility
  semantics through documentation.
- No completion claim without fresh architecture tests and `git diff --check`.
