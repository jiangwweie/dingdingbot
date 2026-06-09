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

# Docs Governance Pass 2.5 Audit Report

Date: 2026-05-29
Method: read-only audit of Pass 2 results; no file changes

---

## 1. Overall verdict

**PASS**

All 6 old knowledge-pack v0 files correctly moved to archive. All current canon files remain in knowledge-pack. Both READMEs point to current canon. All gpt files have HISTORICAL_ARCHIVE banners. No stale claims leak as current facts. No code or migration changes.

---

## 2. Archive move check

| File | In archive | Removed from knowledge-pack | OK |
|---|---|---|---|
| `PROJECT_OVERVIEW.md` | YES | YES | YES |
| `FACT_REGISTRY.md` | YES | YES | YES |
| `MODULE_MAP.md` | YES | YES | YES |
| `CURRENT_STATE_AND_NEXT_ACTIONS.md` | YES | YES | YES |
| `STRATEGY_RESEARCH_HISTORY.md` | YES | YES | YES |
| `PROMPT_LIBRARY.md` | YES | YES | YES |
| `README_DEPRECATED.md` | YES (new) | N/A | YES |

Archive contains 7 files total (6 moved + 1 new README). All correct.

---

## 3. Current canon retention check

| File | Still in knowledge-pack | OK |
|---|---|---|
| `PROJECT_BASELINE_CURRENT.md` | YES | YES |
| `CURRENT_FACT_REGISTRY.md` | YES | YES |
| `CURRENT_READINESS_BLOCKERS.md` | YES | YES |
| `DOCUMENT_GOVERNANCE.md` | YES | YES |
| `ARCHIVE_INDEX.md` | YES | YES |
| `CURRENT_POSITION_REBUILD.md` | YES | YES |
| `TRUTH_REBUILD_PASS1.md` | YES | YES |
| `DOCS_GOVERNANCE_EXPLORATION_REPORT.md` | YES | YES |
| `PASS1_CHANGE_REPORT.md` | YES | YES |
| `PASS1_5_AUDIT_REPORT.md` | YES | YES |
| `PASS2_CHANGE_REPORT.md` | YES | YES |
| `README.md` | YES | YES |

Total: 12 files in knowledge-pack. All current canon and governance files retained.

---

## 4. README / read order check

### docs/README.md

| Item | Present | Position | OK |
|---|---|---|---|
| `PROJECT_BASELINE_CURRENT.md` | YES | #1 | YES |
| `CURRENT_FACT_REGISTRY.md` | YES | #2 | YES |
| `CURRENT_READINESS_BLOCKERS.md` | YES | #3 | YES |
| `DOCUMENT_GOVERNANCE.md` | YES | #4 | YES |
| `CURRENT_POSITION_REBUILD.md` | YES | #5 | YES |
| `TRUTH_REBUILD_PASS1.md` | YES | #6 | YES |
| `DOCS_GOVERNANCE_EXPLORATION_REPORT.md` | YES | #7 | YES |
| PLC Mainline v0 as primary entry | NO (moved to "Historical") | N/A | YES |
| Old knowledge-pack as primary entry | NO | N/A | YES |

**Issues**: None. `PASS1_5_AUDIT_REPORT.md` is not in docs/README.md read order (only in knowledge-pack README), which is acceptable.

### knowledge-pack/README.md

| Item | Present | Position | OK |
|---|---|---|---|
| `PROJECT_BASELINE_CURRENT.md` | YES | #1 | YES |
| `CURRENT_FACT_REGISTRY.md` | YES | #2 | YES |
| `CURRENT_READINESS_BLOCKERS.md` | YES | #3 | YES |
| `DOCUMENT_GOVERNANCE.md` | YES | #4 | YES |
| `CURRENT_POSITION_REBUILD.md` | YES | #5 | YES |
| `TRUTH_REBUILD_PASS1.md` | YES | #6 | YES |
| `DOCS_GOVERNANCE_EXPLORATION_REPORT.md` | YES | #7 | YES |
| `PASS1_5_AUDIT_REPORT.md` | YES | #8 | YES |
| Archive pointer | YES | "Archived knowledge-pack v0" section | YES |

**Issues**: None.

---

## 5. Archive README check

File: `docs/archive/2026-05-29-knowledge-pack-v0/README_DEPRECATED.md`

| Requirement | Present | Notes |
|---|---|---|
| Status: HISTORICAL_ARCHIVE / SUPERSEDED | YES | Line 5 |
| Cannot be used as current project facts | YES | Line 9 |
| Current canon location listed | YES | 6 current canon paths listed |
| Reason 1: Old positioning stale | YES | Line 28 |
| Reason 2: "27 migrations" error | YES | Line 29 |
| Reason 3: 022-027 untracked not integrated | YES | Line 30 |
| Reason 4: Research modules overstated | YES | Line 31 |
| Reason 5: account facts / account_equity confusion | YES | Line 32 |
| Reason 6: Old phase labels in prompts | YES | Line 33 |
| Lists 6 archived files | YES | Lines 37-42 |
| Points to current canon read order | YES | Line 48 |

---

## 6. docs/gpt banner check

| File | Banner present | HISTORICAL_ARCHIVE | Points to PROJECT_BASELINE_CURRENT | OK |
|---|---|---|---|---|
| `1. 全局成熟度判断.md` | YES | YES | YES | YES |
| `风控系统文档.md` | YES | YES | YES | YES |
| `回测引擎文档.md` | YES | YES | YES | YES |
| `日志样本文档.md` | YES | YES | YES | YES |
| `实盘执行链路文档.md` | YES | YES | YES | YES |
| `数据层文档.md` | YES | YES | YES | YES |
| `项目架构图文档.md` | YES | YES | YES | YES |
| `项目目标约束文档.md` | YES | YES | YES | YES |
| `研究任务管理文档.md` | YES | YES | YES | YES |

All 9 files bannered correctly.

---

## 7. Broken or stale references

References to old file paths (`docs/ops/knowledge-pack/PROJECT_OVERVIEW.md` etc.) found in:

| Location | Type | Risk | Verdict |
|---|---|---|---|
| `PROJECT_BASELINE_CURRENT.md` front matter `supersedes:` | Metadata field pointing to old path | LOW | Acceptable — documents what was superseded |
| `PROJECT_BASELINE_CURRENT.md` §10 "Do not start from" | Warning text | LOW | Acceptable — warns against reading old file |
| `CURRENT_FACT_REGISTRY.md` front matter `supersedes:` | Metadata field | LOW | Acceptable |
| `CURRENT_FACT_REGISTRY.md` §F "from old FACT_REGISTRY.md" | Section header | LOW | Acceptable — historical reference |
| `DOCS_GOVERNANCE_EXPLORATION_REPORT.md` (many references) | Audit report documenting what was analyzed | LOW | Acceptable — historical audit record |
| `ARCHIVE_INDEX.md` (many references) | Index of what was archived | LOW | Acceptable — archive tracking document |
| `PASS1_CHANGE_REPORT.md` | Change record | LOW | Acceptable — historical change record |
| Archive files (`CURRENT_STATE_AND_NEXT_ACTIONS.md`, `PROMPT_LIBRARY.md`) | Internal read order within archived files | LOW | Acceptable — these are historical files in archive |

**No broken references in active read paths.** All old-path references are in metadata, historical records, or warning contexts. No current reader would be directed to a non-existent file as a primary source.

---

## 8. Stale claim leakage check

| Claim | Location | Context | OK |
|---|---|---|---|
| "27 Alembic migrations (001-027)" | `PROJECT_BASELINE_CURRENT.md` §9 | Superseded claims table — explicitly labeled as old/wrong | YES |
| "27 Alembic migrations (001-027)" | `CURRENT_FACT_REGISTRY.md` §F | Deprecated claims table — explicitly labeled as old/wrong | YES |
| "BRC Reset / Opportunity Structure Discovery v0" | `PROJECT_BASELINE_CURRENT.md` §1, §9 | Superseded — explicitly labeled "no longer the formal current positioning" | YES |
| "BRC Reset / Opportunity Structure Discovery v0" | `CURRENT_FACT_REGISTRY.md` §F | Deprecated claims table | YES |
| Old positioning | `project-roadmap-v2.md` line 75 | Historical text in tracked file; IMPORTANT banner at top warns | YES |
| Old positioning | `opportunity-research-control-board.md` lines 14, 22 | Historical text; WARNING banner at top warns | YES |
| Old positioning | `docs/README.md` "Historical Mainline" section | Explicitly labeled as historical | YES |

**No stale claims found being presented as current facts.** All references to old claims are in deprecated/superseded tables, warning banners, or explicitly historical sections.

---

## 9. Safety boundary check

| Check | Result | Evidence |
|---|---|---|
| No code changed by Pass 2 | **PASS** | `git diff --name-only` shows only `src/infrastructure/pg_models.py` — pre-existing change, not from Pass 2 |
| No migrations changed | **PASS** | No files under `migrations/` in git status |
| No files deleted | **PASS** | 6 files moved (not deleted); no `D` entries in git diff |
| Only intended files moved | **PASS** | Archive contains exactly 6 old files + 1 new README |
| Current canon intact | **PASS** | 12 files remain in knowledge-pack |
| Archive README created | **PASS** | `README_DEPRECATED.md` present with all required content |
| No runtime/exchange/PG actions | **PASS** | No runtime-related changes |

---

## 10. Recommended fixes before any Pass 3

Only minimal doc edits found. None are blocking.

| ID | Fix | Severity | Notes |
|---|---|---|---|
| FIX-001 | `ARCHIVE_INDEX.md` §5 still says "Keep in place" for `STRATEGY_RESEARCH_HISTORY.md` and `PROMPT_LIBRARY.md` | LOW | These files were actually moved in Pass 2; ARCHIVE_INDEX should be updated to reflect the move was executed |
| FIX-002 | `docs/README.md` read order could include `PASS1_5_AUDIT_REPORT.md` as #8 | LOW | Not critical; knowledge-pack README already has it |

FIX-001 is the only factual inconsistency: ARCHIVE_INDEX.md was written in Pass 1 before the move was executed, so it says "Keep in place or move" for 2 files that were subsequently moved.

---

## 11. Pass 3 recommendation

**Do not execute Pass 3 yet.** Keep `docs/ops/` historical structure stable.

Reasons:
1. The ~153 operational docs in `docs/ops/` form a coherent research history that is valuable as-is.
2. Moving individual research reports would break internal references and git blame context.
3. The current governance layer (banners + canon + read order) is sufficient to prevent misinterpretation.
4. A front-matter pass on all 153 files would be high effort with low marginal value.

**Only consider targeted fixes:**
- FIX-001: Update ARCHIVE_INDEX.md to reflect executed moves
- FIX-002: Optional read order addition

**Future consideration**: If the project grows significantly, a front-matter pass on `docs/ops/` research docs could add `status: RESEARCH_ARCHIVE` tags. But this is not urgent.
