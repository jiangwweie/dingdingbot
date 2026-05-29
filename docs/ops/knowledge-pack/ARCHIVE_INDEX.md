---
title: ARCHIVE_INDEX
status: ACTIVE_WORKING
authority: docs-governance-pass1
last_verified: 2026-05-29
source_of_truth:
  - docs/ops/knowledge-pack/DOCS_GOVERNANCE_EXPLORATION_REPORT.md
---

# ARCHIVE_INDEX.md

This document tracks which documents have been archived, are superseded, or are deprecated.
6 files were moved to `docs/archive/2026-05-29-knowledge-pack-v0/` in Pass 2 (2026-05-29).

---

## 1. High-risk stale docs

These documents are most likely to mislead a new reader if read without context:

| Rank | Path | Problem | Recommended action |
|---|---|---|---|
| 1 | `docs/README.md` | Points to PLC Mainline v0 as current mainline | Update entry (done in Pass 1) |
| 2 | `docs/ops/knowledge-pack/PROJECT_OVERVIEW.md` | Uses Owner-rejected positioning | SUPERSEDED banner added; move to archive in Pass 2 |
| 3 | `docs/ops/knowledge-pack/FACT_REGISTRY.md` | "27 migrations", UF-001/002/003/005/006 overstate integration | SUPERSEDED banner added; move to archive in Pass 2 |
| 4 | `docs/ops/knowledge-pack/MODULE_MAP.md` | Treats 60+ untracked files as integrated modules | Stale warning banner added; move to archive in Pass 2 |
| 5 | `docs/ops/opportunity-research-control-board.md` | Stale phase label "BRC Reset / Opportunity Structure Discovery v0" | Warning banner added |
| 6 | `docs/ops/project-roadmap-v2.md` | Contains both old label (line 67) and Owner correction (line 540) | Entry banner added pointing to amendment |

---

## 2. Superseded docs

| Path | Superseded by | Status |
|---|---|---|
| `docs/ops/knowledge-pack/PROJECT_OVERVIEW.md` | `PROJECT_BASELINE_CURRENT.md` | Banner added |
| `docs/ops/knowledge-pack/FACT_REGISTRY.md` | `CURRENT_FACT_REGISTRY.md` | Banner added |
| `docs/ops/knowledge-pack/MODULE_MAP.md` | `PROJECT_BASELINE_CURRENT.md` (for capability claims) | Banner added |
| `docs/ops/knowledge-pack/CURRENT_STATE_AND_NEXT_ACTIONS.md` | `CURRENT_READINESS_BLOCKERS.md` (for blockers) | Banner added |

---

## 3. Deprecated claims (within documents)

| Document | Deprecated claim | Corrected in |
|---|---|---|
| FACT_REGISTRY.md F-001 | "BRC Reset / Opportunity Structure Discovery v0" | CURRENT_FACT_REGISTRY.md CF-001 |
| FACT_REGISTRY.md F-011 | "27 Alembic migrations" | CURRENT_FACT_REGISTRY.md CF-007/008 |
| FACT_REGISTRY.md UF-001 | "Strategy Family Registry PG chain 待确认" | CURRENT_FACT_REGISTRY.md NI-001 |
| FACT_REGISTRY.md UF-002 | "exchange + PG dual path for account facts" | CURRENT_FACT_REGISTRY.md DC-004 |
| MODULE_MAP.md Sections 4-5 | New research modules treated as integrated | CURRENT_FACT_REGISTRY.md NI-001 through NI-011 |
| CURRENT_STATE_AND_NEXT_ACTIONS.md §7 | "27 Alembic migrations" | CURRENT_FACT_REGISTRY.md CF-007/008 |
| PROJECT_OVERVIEW.md | Entire document uses rejected positioning | PROJECT_BASELINE_CURRENT.md |

---

## 4. Research archive docs

These documents are valuable research evidence but must not be interpreted as current capability:

| Category | Files | Count |
|---|---|---|
| CPM-1 ETH Pinbar Pullback | `docs/ops/cpm-1-*.md`, `docs/ops/crypto-pullback-module-v1-*.md` | ~16 |
| Direction A Trend Breakout | `docs/ops/direction-a-*.md`, `docs/ops/dira-*.md` | ~18 |
| Main Trend Capture | `docs/ops/mtc-*.md` | 6 |
| Short-side Breakdown | `docs/ops/ssd-*.md` | 4 |
| VEI Volatility Expansion | `docs/ops/vei-*.md` | 4 |
| Next Strategy Candidate | `docs/ops/nsc-*.md` | 14 |
| Trend Edge validation | `docs/ops/te-*.md` | 7 |
| GPT audit (2026-04-29) | `docs/gpt/*.md` | 9 |

**Total research archive candidates**: ~78 files

These files should be marked `RESEARCH_ARCHIVE` in any future front-matter pass.
They preserve valuable evidence but should not be the first thing a new reader encounters.

---

## 5. Executed Pass 2 moves

These moves were executed in Pass 2 (2026-05-29):

| Original path | Destination | Reason | Status |
|---|---|---|---|
| `docs/ops/knowledge-pack/PROJECT_OVERVIEW.md` | `docs/archive/2026-05-29-knowledge-pack-v0/` | Superseded positioning | **MOVED** |
| `docs/ops/knowledge-pack/FACT_REGISTRY.md` | `docs/archive/2026-05-29-knowledge-pack-v0/` | Stale claims | **MOVED** |
| `docs/ops/knowledge-pack/MODULE_MAP.md` | `docs/archive/2026-05-29-knowledge-pack-v0/` | Overstates integration | **MOVED** |
| `docs/ops/knowledge-pack/CURRENT_STATE_AND_NEXT_ACTIONS.md` | `docs/archive/2026-05-29-knowledge-pack-v0/` | Superseded by readiness blockers | **MOVED** |
| `docs/ops/knowledge-pack/STRATEGY_RESEARCH_HISTORY.md` | `docs/archive/2026-05-29-knowledge-pack-v0/` | Useful archive, moved for consistency | **MOVED** |
| `docs/ops/knowledge-pack/PROMPT_LIBRARY.md` | `docs/archive/2026-05-29-knowledge-pack-v0/` | Useful archive, moved for consistency | **MOVED** |

Pass 2 also:

- Created `docs/archive/2026-05-29-knowledge-pack-v0/README_DEPRECATED.md`
- Kept `CURRENT_POSITION_REBUILD.md`, `TRUTH_REBUILD_PASS1.md`, and all new Pass 1 files in `docs/ops/knowledge-pack/`
- Updated knowledge-pack and docs READMEs with archive pointers and new read orders
- Added HISTORICAL_ARCHIVE banners to all 9 `docs/gpt/*.md` files

---

## 6. Docs not in archive scope

The following document categories should NOT be archived:

| Category | Why |
|---|---|
| ADRs (13 files) | Stable decision records, always relevant for context |
| Live-safe-v1 operational docs | Active progress/task tracking |
| BRC operational docs (R2-R5) | Active implementation tracking |
| BRC console design/acceptance | Active product docs |
| Current canon knowledge-pack files | These are the new authority |
| JSON schemas | Design contracts, stable |
