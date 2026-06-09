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

# Docs Governance Pass 2 Change Report

Date: 2026-05-29
Method: file moves (mv), new file creation, banner additions; no deletions, no code changes

---

## 1. Summary

Moved 6 superseded knowledge-pack v0 files to `docs/archive/2026-05-29-knowledge-pack-v0/`.
Created archive README. Updated knowledge-pack and docs read orders.
Added historical archive banners to all 9 `docs/gpt/*.md` files.

---

## 2. Files moved to archive

| File | From | To |
|---|---|---|
| `PROJECT_OVERVIEW.md` | `docs/ops/knowledge-pack/` | `docs/archive/2026-05-29-knowledge-pack-v0/` |
| `FACT_REGISTRY.md` | `docs/ops/knowledge-pack/` | `docs/archive/2026-05-29-knowledge-pack-v0/` |
| `MODULE_MAP.md` | `docs/ops/knowledge-pack/` | `docs/archive/2026-05-29-knowledge-pack-v0/` |
| `CURRENT_STATE_AND_NEXT_ACTIONS.md` | `docs/ops/knowledge-pack/` | `docs/archive/2026-05-29-knowledge-pack-v0/` |
| `STRATEGY_RESEARCH_HISTORY.md` | `docs/ops/knowledge-pack/` | `docs/archive/2026-05-29-knowledge-pack-v0/` |
| `PROMPT_LIBRARY.md` | `docs/ops/knowledge-pack/` | `docs/archive/2026-05-29-knowledge-pack-v0/` |

Note: Files were untracked (entire `docs/ops/knowledge-pack/` was `??` in git status), so `mv` was used instead of `git mv`.

---

## 3. Files created

| File | Purpose |
|---|---|
| `docs/archive/2026-05-29-knowledge-pack-v0/README_DEPRECATED.md` | Archive index explaining why files were archived and pointing to current canon |

---

## 4. Files modified

| File | Change |
|---|---|
| `docs/ops/knowledge-pack/README.md` | Replaced "Historical / superseded" section with archive pointer; updated read order to include 8 items + PASS1_5_AUDIT_REPORT |
| `docs/README.md` | Added `CURRENT_POSITION_REBUILD.md` and `TRUTH_REBUILD_PASS1.md` to read order (items 5 and 6) |
| `docs/gpt/1. 全局成熟度判断.md` | Added HISTORICAL_ARCHIVE banner |
| `docs/gpt/风控系统文档.md` | Added HISTORICAL_ARCHIVE banner |
| `docs/gpt/回测引擎文档.md` | Added HISTORICAL_ARCHIVE banner |
| `docs/gpt/日志样本文档.md` | Added HISTORICAL_ARCHIVE banner |
| `docs/gpt/实盘执行链路文档.md` | Added HISTORICAL_ARCHIVE banner |
| `docs/gpt/数据层文档.md` | Added HISTORICAL_ARCHIVE banner |
| `docs/gpt/项目架构图文档.md` | Added HISTORICAL_ARCHIVE banner |
| `docs/gpt/项目目标约束文档.md` | Added HISTORICAL_ARCHIVE banner |
| `docs/gpt/研究任务管理文档.md` | Added HISTORICAL_ARCHIVE banner |

---

## 5. Current canon files remaining in knowledge-pack

| File | Status |
|---|---|
| `PROJECT_BASELINE_CURRENT.md` | CURRENT_CANON |
| `CURRENT_FACT_REGISTRY.md` | CURRENT_CANON |
| `CURRENT_READINESS_BLOCKERS.md` | CURRENT_CANON |
| `DOCUMENT_GOVERNANCE.md` | CURRENT_CANON |
| `CURRENT_POSITION_REBUILD.md` | CURRENT_CANON |
| `TRUTH_REBUILD_PASS1.md` | CURRENT_CANON |
| `DOCS_GOVERNANCE_EXPLORATION_REPORT.md` | CURRENT_CANON |
| `ARCHIVE_INDEX.md` | ACTIVE_WORKING |
| `PASS1_CHANGE_REPORT.md` | ACTIVE_WORKING |
| `PASS1_5_AUDIT_REPORT.md` | ACTIVE_WORKING |
| `PASS2_CHANGE_REPORT.md` | ACTIVE_WORKING (this file) |
| `README.md` | Index |

Total: 12 files. All are current canon, governance, or working documents.

---

## 6. docs/gpt archive banners

All 9 `docs/gpt/*.md` files received the same banner:

```
> [!WARNING]
> HISTORICAL_ARCHIVE: This file is a ChatGPT-generated audit snapshot from 2026-04-29 and predates the current BRC fast trial-and-review research system baseline.
> Do not use it as current project truth. Start from `docs/ops/knowledge-pack/PROJECT_BASELINE_CURRENT.md`.
```

Files bannered:
1. `1. 全局成熟度判断.md`
2. `风控系统文档.md`
3. `回测引擎文档.md`
4. `日志样本文档.md`
5. `实盘执行链路文档.md`
6. `数据层文档.md`
7. `项目架构图文档.md`
8. `项目目标约束文档.md`
9. `研究任务管理文档.md`

---

## 7. Safety self-check

- [x] No files deleted
- [x] Only the 6 old knowledge-pack files moved (plus 1 new README_DEPRECATED.md created in archive)
- [x] No code files modified
- [x] No migrations modified
- [x] No runtime/exchange/PG actions
- [x] Current canon remains in docs/ops/knowledge-pack (12 files)
- [x] Archive README created
- [x] docs/README.md read order updated (7 items, includes rebuild docs)
- [x] docs/gpt/*.md marked historical (9 files)
- [x] No src/ files touched
- [x] knowledge-pack/README.md updated with archive pointer and new read order

---

## 8. Git status after Pass 2

**Modified tracked files** (pre-existing, not from Pass 2):
- `docs/ops/live-safe-v1-progress.md`
- `docs/ops/live-safe-v1-task-board.md`

**Modified tracked files** (from Pass 1 + Pass 2):
- `docs/README.md`
- `docs/ops/project-roadmap-v2.md`
- `docs/ops/opportunity-research-control-board.md`
- 9 `docs/gpt/*.md` files

**New untracked directories**:
- `docs/archive/` (7 files: 6 moved + 1 new README)
- `docs/ops/knowledge-pack/` (12 current canon files)

**No code changes**: `src/` directory unaffected (except pre-existing `pg_models.py` modification).

---

## 9. Recommended Pass 2.5 audit

A Pass 2.5 audit should verify:

1. Archive directory contains exactly 6 old files + README_DEPRECATED.md
2. knowledge-pack contains only current canon files (no old files leaked)
3. All gpt files have HISTORICAL_ARCHIVE banner
4. docs/README.md read order is complete (7 items)
5. knowledge-pack/README.md points to archive correctly
6. No stale claims in current canon files
7. No code files touched
