# Knowledge Pack Index

Last updated: 2026-06-08
Status: CURRENT_CANON index

---

## Current canon (read these first)

These documents are the authoritative source for the project's current state:

| # | Document | Purpose |
|---|---|---|
| 1 | [`CURRENT_PRODUCT_OPERATING_MODEL.md`](CURRENT_PRODUCT_OPERATING_MODEL.md) | Current product and execution model; Trading Console is Owner operations surface, not merely read-only dashboard |
| 2 | [`PROJECT_BASELINE_CURRENT.md`](PROJECT_BASELINE_CURRENT.md) | Project definition, current stage, confirmed facts, blockers, prohibited actions |
| 3 | [`CURRENT_FACT_REGISTRY.md`](CURRENT_FACT_REGISTRY.md) | Verified facts, not-integrated components, disabled capabilities, deprecated claims |
| 4 | [`CURRENT_READINESS_BLOCKERS.md`](CURRENT_READINESS_BLOCKERS.md) | What blocks a new bounded live action or Owner operations flow |
| 5 | [`DOCUMENT_GOVERNANCE.md`](DOCUMENT_GOVERNANCE.md) | How to read and trust project documents; authority rules; capability wording rules |
| 6 | [`CURRENT_POSITION_REBUILD.md`](CURRENT_POSITION_REBUILD.md) | Historical detailed position analysis with evidence; Owner correction documented |
| 7 | [`TRUTH_REBUILD_PASS1.md`](TRUTH_REBUILD_PASS1.md) | Which old knowledge-pack claims are stale and why |

## Governance and audit

| Document | Purpose |
|---|---|
| [`DOCS_GOVERNANCE_EXPLORATION_REPORT.md`](DOCS_GOVERNANCE_EXPLORATION_REPORT.md) | Full docs audit: 188 files classified, stale claims identified, archive plan |
| [`ARCHIVE_INDEX.md`](ARCHIVE_INDEX.md) | Archive candidates, superseded docs, proposed Pass 2 moves |

## Archived knowledge-pack v0

The original six knowledge-pack v0 files were moved to:

`docs/archive/2026-05-29-knowledge-pack-v0/`

Archived files: `PROJECT_OVERVIEW.md`, `FACT_REGISTRY.md`, `MODULE_MAP.md`, `CURRENT_STATE_AND_NEXT_ACTIONS.md`, `STRATEGY_RESEARCH_HISTORY.md`, `PROMPT_LIBRARY.md`.

They are historical archives only and must not be used as current project facts.
See `docs/archive/2026-05-29-knowledge-pack-v0/README_DEPRECATED.md` for details.

## Read order for new AI assistants

1. `CURRENT_PRODUCT_OPERATING_MODEL.md` — current product and execution model
2. `PROJECT_BASELINE_CURRENT.md` — project definition and current state
3. `CURRENT_FACT_REGISTRY.md` — verified facts, blockers, prohibited actions
4. `CURRENT_READINESS_BLOCKERS.md` — what blocks current bounded live action readiness
5. `DOCUMENT_GOVERNANCE.md` — how to read and trust project documents
6. `CURRENT_POSITION_REBUILD.md` — historical detailed position analysis
7. `TRUTH_REBUILD_PASS1.md` — which old claims are stale and why
8. `DOCS_GOVERNANCE_EXPLORATION_REPORT.md` — full docs audit
9. `PASS1_5_AUDIT_REPORT.md` — Pass 1 audit verification

Then for deeper context:

- `docs/adr/0009-*.md` — non-real-live execution boundary
- `docs/adr/0012-*.md` — BRC system definition
- `docs/ops/project-roadmap-v2.md` — long-term direction (contains both old and new labels; see line 540+)
- `docs/ops/live-safe-v1-task-board.md` — task status
- `docs/ops/live-safe-v1-progress.md` — detailed progress log

**Do not start from** the archived knowledge-pack v0 in `docs/archive/2026-05-29-knowledge-pack-v0/` — those files are superseded.
