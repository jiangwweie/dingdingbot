# Docs Governance Pass 1.5 Audit Report

Date: 2026-05-29
Method: read-only audit of Pass 1 results; no file changes

---

## 1. Overall verdict

**PASS**

All new canon documents are complete, internally consistent, and aligned with `CURRENT_POSITION_REBUILD.md`. All old high-risk documents have correct banners. No stale claims leak into current canon as current facts. No code files were modified. No files were moved or deleted.

---

## 2. Files created check

| File | Exists | Status front matter | Content complete | Issues |
|---|---|---|---|---|
| `PROJECT_BASELINE_CURRENT.md` | YES | YES (CURRENT_CANON, owner-correction) | YES — definition, stage, facts, blockers, not-integrated, disabled, prohibited, next actions, superseded claims, reading order | None |
| `CURRENT_FACT_REGISTRY.md` | YES | YES (CURRENT_CANON, current-position-rebuild) | YES — confirmed facts, blockers, not-integrated, disabled, prohibited, deprecated claims, safety boundaries | None |
| `CURRENT_READINESS_BLOCKERS.md` | YES | YES (CURRENT_CANON, current-position-rebuild) | YES — P0/P1/P2 blockers, not-blockers, trial readiness checklist, next checks | None |
| `DOCUMENT_GOVERNANCE.md` | YES | YES (CURRENT_CANON, owner-correction) | YES — authority order, statuses, tracked-only rule, wording rules, front matter policy, archive/deprecation policies | None |
| `ARCHIVE_INDEX.md` | YES | YES (ACTIVE_WORKING, docs-governance-pass1) | YES — high-risk docs, superseded docs, deprecated claims, research archive, proposed Pass 2 moves | None |
| `README.md` (knowledge-pack) | YES | No YAML front matter (index file) | YES — current canon table, historical table, read order | None — index file does not need front matter |

---

## 3. Banner check

| File | Banner present | Points to correct canon | Original content preserved | Risk after banner | Issues |
|---|---|---|---|---|---|
| `PROJECT_OVERVIEW.md` | YES (WARNING: SUPERSEDED) | YES → `PROJECT_BASELINE_CURRENT.md` | YES | LOW | None |
| `FACT_REGISTRY.md` | YES (WARNING: SUPERSEDED) | YES → `CURRENT_FACT_REGISTRY.md` | YES | LOW | None |
| `MODULE_MAP.md` | YES (WARNING: SUPERSEDED/PARTIALLY STALE) | YES → `PROJECT_BASELINE_CURRENT.md` | YES | LOW | None |
| `CURRENT_STATE_AND_NEXT_ACTIONS.md` | YES (WARNING: PARTIALLY SUPERSEDED) | YES → `CURRENT_READINESS_BLOCKERS.md` | YES | LOW | None |
| `docs/README.md` | YES (IMPORTANT entry block) | YES → 4 current canon docs | YES (PLC section moved to "Historical") | LOW | None |
| `project-roadmap-v2.md` | YES (IMPORTANT: mixed labels) | YES → `PROJECT_BASELINE_CURRENT.md` | YES | LOW | Old label at line 75 remains but banner at top warns |
| `opportunity-research-control-board.md` | YES (WARNING: PARTIALLY STALE) | YES → `PROJECT_BASELINE_CURRENT.md` + `CURRENT_READINESS_BLOCKERS.md` | YES | LOW | Old label at line 14 remains but banner at top warns |

---

## 4. Current canon consistency check

Cross-referenced against required baseline from `CURRENT_POSITION_REBUILD.md`:

| Required fact | Present in PBC? | Present in CFR? | Present in CRB? | Correct? | Notes |
|---|---|---|---|---|---|
| Project: "fast trial-and-review research system" | YES (§1) | YES (CF-001) | N/A | YES | — |
| Stage: broad screen done, 3 candidates, account_equity blocker | YES (§2) | YES (BLK-001/002) | YES (P0 blockers) | YES | — |
| Real live trading: NO | YES (CF-002, FORBID-001) | YES (CF-003, PA-001) | N/A | YES | — |
| Testnet: YES, controlled + Owner auth | YES (CF-003) | YES (CF-004, SB-002) | N/A | YES | — |
| Auto execution: NO | YES (CF-007/008) | YES (DC-001) | N/A | YES | — |
| auto_within_budget=False | YES (CF-007) | YES (DC-001) | N/A | YES | — |
| auto_execution=False | YES (CF-008) | YES (DC-001) | N/A | YES | — |
| signal-to-order: NO | YES (DC-002) | YES (DC-002) | N/A | YES | — |
| signal-to-intent: PARTIAL | YES (DC-003) | YES (DC-003) | YES (BLK-P0-03) | YES | — |
| account_equity: unavailable | YES (§4, DC-004) | YES (BLK-001, DC-004) | YES (BLK-P0-01) | YES | — |
| wallet_equity/available_margin = not_available | YES (§4) | YES (BLK-001) | YES (BLK-P0-01) | YES | — |
| Migrations 001-021 = tracked | YES (CF-010) | YES (CF-007) | N/A | YES | — |
| Migrations 022-027 = untracked, not integrated | YES (CF-011, §5) | YES (CF-008, NI-001-011) | YES (BLK-P1-01) | YES | — |
| Old knowledge-pack = historical/superseded | YES (§9) | YES (§F) | N/A | YES | — |
| Old positioning "BRC Reset / OSD v0" = superseded | YES (§1, §9) | YES (§F) | N/A | YES | — |

**All 15 required facts are correctly expressed across all new canon documents.**

---

## 5. Remaining stale claim risks

| ID | Claim | File | Why risky | Fix needed? |
|---|---|---|---|---|
| R-001 | `RBC Reset / Opportunity Structure Discovery v0` at line 75 | `project-roadmap-v2.md` | Old label in body text; banner at top warns but reader skipping banner could miss it | No — banner is sufficient; original content preserved per governance policy |
| R-002 | Same label at line 14 | `opportunity-research-control-board.md` | Same | No — banner warns |
| R-003 | Same label at line 22 | `opportunity-research-control-board.md` | Same | No — banner warns |
| R-004 | "27 Alembic migrations" in old knowledge-pack | `FACT_REGISTRY.md`, `MODULE_MAP.md`, `CURRENT_STATE_AND_NEXT_ACTIONS.md` | Banner warns, but old text still present | No — banners added; Pass 2 would move files |
| R-005 | `docs/gpt/*.md` (9 files) have no archive banner | `docs/gpt/` | Historical ChatGPT audit from 2026-04-29 could be read as current | Yes — should be addressed in Pass 2 |

**All remaining risks are mitigated by banners. R-005 is the only item that should be addressed in Pass 2.**

---

## 6. Safety boundary check

| Check | Result | Evidence |
|---|---|---|
| No code changed | **PASS** | `git diff --name-only` shows only `src/infrastructure/pg_models.py` which was pre-existing (not from Pass 1) |
| No files moved | **PASS** | `git status` shows no renamed files |
| No files deleted | **PASS** | No deletions in git status |
| No migration touched | **PASS** | No files under `migrations/` modified |
| No runtime/exchange/PG action | **PASS** | No runtime-related changes |
| Untracked not described as integrated | **PASS** | All references to 022-027 and new modules use "NOT INTEGRATED" or "not integrated" |
| Old errors not quietly corrected | **PASS** | Old documents preserved with banners; new documents explicitly list deprecated claims |

---

## 7. Cross-document consistency checks

### 7.1 ID numbering

- `PROJECT_BASELINE_CURRENT.md` uses CF-001 through CF-015, FORBID-001 through FORBID-010
- `CURRENT_FACT_REGISTRY.md` uses CF-001 through CF-020, BLK-001 through BLK-004, NI-001 through NI-011, DC-001 through DC-006, PA-001 through PA-010, SB-001 through SB-008
- **Issue**: CF-001 through CF-015 overlap between the two files but have different facts. `PROJECT_BASELINE_CURRENT.md` CF-001 = "BRC governance framework implemented" while `CURRENT_FACT_REGISTRY.md` CF-001 = "Project target is fast trial-and-review..."

**Severity**: LOW. The two documents are separate canon documents with independent numbering. However, this could cause confusion if someone cross-references by ID.

**Recommendation**: In Pass 2 or a future update, consider prefixing IDs with document initials (e.g., PBC-CF-001 vs CFR-CF-001) or using a shared numbering scheme. Not blocking for Pass 2.

### 7.2 Reading order consistency

- `docs/README.md` reading order: PROJECT_BASELINE_CURRENT → CURRENT_FACT_REGISTRY → CURRENT_READINESS_BLOCKERS → DOCUMENT_GOVERNANCE → DOCS_GOVERNANCE_EXPLORATION_REPORT
- `knowledge-pack/README.md` reading order: PROJECT_BASELINE_CURRENT → CURRENT_FACT_REGISTRY → CURRENT_READINESS_BLOCKERS → DOCUMENT_GOVERNANCE → CURRENT_POSITION_REBUILD → TRUTH_REBUILD_PASS1 → DOCS_GOVERNANCE_EXPLORATION_REPORT
- `PROJECT_BASELINE_CURRENT.md` §10 reading order: PROJECT_BASELINE_CURRENT → CURRENT_FACT_REGISTRY → CURRENT_READINESS_BLOCKERS → DOCUMENT_GOVERNANCE → CURRENT_POSITION_REBUILD → TRUTH_REBUILD_PASS1 → DOCS_GOVERNANCE_EXPLORATION_REPORT

**Issue**: `docs/README.md` omits `CURRENT_POSITION_REBUILD.md` and `TRUTH_REBUILD_PASS1.md` from its read order.

**Severity**: LOW. The knowledge-pack README and PROJECT_BASELINE_CURRENT both include the full 7-step order. The docs/README only lists 5 steps as a quick-start. A reader following docs/README would still reach the exploration report, which references the rebuild docs.

### 7.3 Superseded document references

All new canon documents that reference old documents do so only in:
- "Superseded claims" / "Deprecated claims" tables
- Explicit "Do not start from" warnings
- source_of_truth front matter pointing to CURRENT_POSITION_REBUILD.md

**No new canon document uses an old document as an authoritative source.** PASS.

---

## 8. Recommended fixes before Pass 2

All are minimal doc edits. None are blocking.

| ID | Fix | File | Action | Severity |
|---|---|---|---|---|
| FIX-001 | Add `docs/gpt/*.md` archive banners (9 files) | `docs/gpt/` | Add historical archive banner in Pass 2 | LOW |
| FIX-002 | Consider harmonizing CF-ID numbering between PBC and CFR | Future | Prefix or renumber | LOW |
| FIX-003 | Consider adding rebuild docs to `docs/README.md` read order | `docs/README.md` | Add 2 lines | LOW |

None of these block Pass 2.

---

## 9. Pass 2 readiness

**Is Pass 2 safe to execute now?** YES.

Checklist:
- [x] Overall verdict = PASS
- [x] No code changed
- [x] No files moved (Pass 1 only)
- [x] No stale current-canon conflicts
- [x] PROJECT_BASELINE_CURRENT.md consistent with CURRENT_POSITION_REBUILD.md
- [x] CURRENT_FACT_REGISTRY.md consistent with CURRENT_POSITION_REBUILD.md
- [x] No old positioning / 27 migrations / account_equity available errors in new canon
- [x] All banners correctly placed and pointing to right canon

Pass 2 (archive old knowledge-pack) can proceed when Owner approves.
