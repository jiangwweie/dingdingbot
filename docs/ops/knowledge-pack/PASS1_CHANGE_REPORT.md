# Docs Governance Pass 1 Change Report

Date: 2026-05-29
Method: additive edits only; no file moves, no deletions, no code changes

---

## 1. Files created (6)

| File | Purpose | Status |
|---|---|---|
| `docs/ops/knowledge-pack/PROJECT_BASELINE_CURRENT.md` | Current authoritative project baseline | CURRENT_CANON |
| `docs/ops/knowledge-pack/CURRENT_FACT_REGISTRY.md` | Verified facts, blockers, deprecated claims | CURRENT_CANON |
| `docs/ops/knowledge-pack/CURRENT_READINESS_BLOCKERS.md` | Trial readiness blockers and checklist | CURRENT_CANON |
| `docs/ops/knowledge-pack/DOCUMENT_GOVERNANCE.md` | Authority order, status definitions, wording rules | CURRENT_CANON |
| `docs/ops/knowledge-pack/ARCHIVE_INDEX.md` | Archive candidates, proposed Pass 2 moves | ACTIVE_WORKING |
| `docs/ops/knowledge-pack/README.md` | Knowledge pack index with read order | CURRENT_CANON |

---

## 2. Files modified (8)

| File | Change | Type |
|---|---|---|
| `docs/README.md` | Added current baseline entry block at top; moved PLC Mainline to "Historical" section | Banner + section rewrite |
| `docs/ops/project-roadmap-v2.md` | Added IMPORTANT banner pointing to PROJECT_BASELINE_CURRENT and 2026-05-29 amendment | Banner |
| `docs/ops/opportunity-research-control-board.md` | Added WARNING banner about stale phase labels | Banner |
| `docs/ops/knowledge-pack/PROJECT_OVERVIEW.md` | Added WARNING banner: SUPERSEDED | Banner |
| `docs/ops/knowledge-pack/FACT_REGISTRY.md` | Added WARNING banner: SUPERSEDED, known stale claims listed | Banner |
| `docs/ops/knowledge-pack/MODULE_MAP.md` | Added WARNING banner: SUPERSEDED/PARTIALLY STALE | Banner |
| `docs/ops/knowledge-pack/CURRENT_STATE_AND_NEXT_ACTIONS.md` | Added WARNING banner: PARTIALLY SUPERSEDED | Banner |

Note: `docs/ops/live-safe-v1-progress.md` and `docs/ops/live-safe-v1-task-board.md` appear in git status as modified, but those changes were pre-existing (not from Pass 1).

---

## 3. Files intentionally not moved

All 143+ docs in `docs/ops/` remain in place. No files were moved to archive.
Archive moves are proposed in `ARCHIVE_INDEX.md` for Pass 2 (requires Owner approval).

Key files that would move in Pass 2:

| Current path | Proposed destination |
|---|---|
| `knowledge-pack/PROJECT_OVERVIEW.md` | `docs/archive/2026-05-29-knowledge-pack-v0/` |
| `knowledge-pack/FACT_REGISTRY.md` | `docs/archive/2026-05-29-knowledge-pack-v0/` |
| `knowledge-pack/MODULE_MAP.md` | `docs/archive/2026-05-29-knowledge-pack-v0/` |
| `knowledge-pack/CURRENT_STATE_AND_NEXT_ACTIONS.md` | `docs/archive/2026-05-29-knowledge-pack-v0/` |

---

## 4. Deprecated / superseded banners added

| Document | Banner status |
|---|---|
| `PROJECT_OVERVIEW.md` | SUPERSEDED |
| `FACT_REGISTRY.md` | SUPERSEDED |
| `MODULE_MAP.md` | SUPERSEDED / PARTIALLY STALE |
| `CURRENT_STATE_AND_NEXT_ACTIONS.md` | PARTIALLY SUPERSEDED |
| `docs/README.md` | Updated entry point |
| `project-roadmap-v2.md` | IMPORTANT note about mixed old/new labels |
| `opportunity-research-control-board.md` | WARNING about stale phase labels |

---

## 5. Current canon read order

1. `PROJECT_BASELINE_CURRENT.md` — project definition, current stage, confirmed facts
2. `CURRENT_FACT_REGISTRY.md` — verified facts, not-integrated components, deprecated claims
3. `CURRENT_READINESS_BLOCKERS.md` — trial readiness blockers and checklist
4. `DOCUMENT_GOVERNANCE.md` — authority rules, capability wording rules
5. `CURRENT_POSITION_REBUILD.md` — detailed position analysis with evidence
6. `TRUTH_REBUILD_PASS1.md` — which old claims are stale
7. `DOCS_GOVERNANCE_EXPLORATION_REPORT.md` — full docs audit

---

## 6. Remaining risks

| Risk | Mitigation |
|---|---|
| Old knowledge-pack files still exist and could be read without seeing banners | Banners are at the very top of each file; Pass 2 would move them to archive |
| `docs/ops/project-roadmap-v2.md` line 67 still has old label | Banner at top directs readers to line 540+ amendment |
| `docs/gpt/` files (9) not yet given archive banners | Lower priority; can be done in Pass 2 |
| Some readers may not start at `docs/README.md` | README banner is the best we can do without file moves |
| ~78 research archive docs in `docs/ops/` not individually marked | Front-matter pass would address this at scale; not in Pass 1 scope |

---

## 7. Recommended Pass 2

Pass 2 would:

1. Create `docs/archive/2026-05-29-knowledge-pack-v0/` directory
2. Move 4 superseded knowledge-pack files to archive
3. Create redirect README in archive
4. Add historical archive banners to `docs/gpt/*.md` (9 files)
5. Keep current canon files in `knowledge-pack/`

Requires Owner approval before execution.

---

## 8. Self-check

- [x] No files moved
- [x] No files deleted
- [x] No code modified
- [x] No runtime executed
- [x] No PG migration executed
- [x] No exchange connection
- [x] New current canon created (5 files + README)
- [x] Old high-risk docs have banners (7 files)
- [x] `docs/README.md` points to new baseline
- [x] Knowledge-pack README created with read order
- [x] Old knowledge-pack files not deleted
- [x] Untracked files not described as integrated capabilities
