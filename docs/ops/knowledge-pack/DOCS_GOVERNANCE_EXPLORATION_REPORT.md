# Docs Governance Exploration Report

Date: 2026-05-29
Method: read-only exploration, no file moves, no deletions, no rewrites

---

## 1. Repo state

- **Branch**: `codex/brc-owner-console-v0`
- **Modified tracked files** (4, unstaged):
  - `docs/ops/live-safe-v1-progress.md`
  - `docs/ops/live-safe-v1-task-board.md`
  - `docs/ops/project-roadmap-v2.md`
  - `src/infrastructure/pg_models.py`
- **Untracked docs**: `docs/ops/knowledge-pack/` (8 files)
- **Untracked non-docs affecting docs truth**: 6 migrations (022-027), 60+ domain/infra/app/script/test files
- **Recent 30 commits**: All BRC-prefix (`brc`), no production deployment commits. Latest: `559c95e docs(brc): record R5 admission and read-only state`

---

## 2. Docs inventory

### 2.1 Directory summary

| Directory | .md files | Main topics | Risk level |
|---|---:|---|---|
| `docs/adr/` | 13 | Architecture Decision Records (0001-0013) | LOW — decision records, generally stable |
| `docs/gpt/` | 9 | ChatGPT-generated system audit reports (2026-04-29) | **HIGH** — historical snapshot, not current |
| `docs/ops/` | 153 | Research reports, task cards, plans, designs, diagnostics | **HIGH** — massive volume, stale claims |
| `docs/ops/knowledge-pack/` | 8 | Knowledge pack v0 + truth rebuilds | **MEDIUM** — most honest docs, but v0 still has errors |
| `docs/ops/brc-owner-console-product-design-v0/` | 1 README + 4 SVG wireframes | Console product design | LOW |
| `docs/product/` | 3 | BRC console state, refactor, admission gate | LOW-MEDIUM |
| `docs/schemas/` | 0 .md (JSON only) | Personal campaign JSON schemas | LOW — design contracts |
| `docs/` | 1 README.md | Docs index | **HIGH** — stale mainline pointer |

**Total**: 188 markdown files, ~150+ operational/working docs in `docs/ops/`.

### 2.2 High-risk documents (most likely to mislead)

| Path | Why high risk |
|---|---|
| `docs/README.md` | Points to "Personal Leveraged Campaign Mainline v0" as current — predates 2026-05-29 Owner amendment |
| `docs/ops/project-roadmap-v2.md` | Line 67 still says `RBC Reset / Opportunity Structure Discovery v0`; 2026-05-29 amendment at line 540 |
| `docs/ops/knowledge-pack/PROJECT_OVERVIEW.md` | Uses old positioning; Owner explicitly rejected |
| `docs/ops/knowledge-pack/FACT_REGISTRY.md` | F-011 says "27 migrations"; UF-001/002/003/005/006 overstate integration |
| `docs/ops/knowledge-pack/MODULE_MAP.md` | Sections 4-5 treat untracked files as integrated |
| `docs/ops/knowledge-pack/CURRENT_STATE_AND_NEXT_ACTIONS.md` | §7 says "27 Alembic migrations"; §6 prompt still says "Opportunity Structure Discovery v0" |
| `docs/ops/opportunity-research-control-board.md` | Uses `RBC Reset / Opportunity Structure Discovery v0` as current phase |
| `docs/ops/opportunity-hypothesis-register.md` | Same stale phase label |
| `docs/gpt/1. 全局成熟度判断.md` | Says "系统已不是玩具策略脚本...只适合 Sim-1 / 小资金观察" — predates BRC framework |
| `docs/gpt/实盘执行链路文档.md` | Discusses live execution chain — predates current architecture |
| `docs/ops/project-branch-and-doc-governance-2026-05-25.md` | References `codex/personal-campaign-chain-v0` branch (stale), current branch is different |

### 2.3 Candidate authoritative documents

| Path | Why authoritative |
|---|---|
| `docs/ops/knowledge-pack/CURRENT_POSITION_REBUILD.md` | Owner-corrected positioning, read-only verified against code |
| `docs/ops/knowledge-pack/TRUTH_REBUILD_PASS1.md` | Identifies exactly which knowledge-pack facts are stale |
| `docs/ops/project-roadmap-v2.md` (line 540+) | Contains 2026-05-29 Owner amendment (unstaged) |
| `docs/adr/0009-non-real-live-execution-authorization-boundary.md` | Core safety boundary decision |
| `docs/adr/0012-bounded-risk-campaign-system.md` | Core BRC framework decision |
| `docs/ops/brc-testnet-first-production-blocked-principle.md` | Operating principle |
| `docs/ops/runtime-safety-boundary.md` | Safety boundary doc (updated 2026-05-25) |
| `docs/ops/live-safe-v1-task-board.md` | Current task status |

---

## 3. Proposed authority classification

### 3.1 Current canon candidates

| Path | Why current canon | Confidence | Caveat |
|---|---|---|---|
| `docs/ops/knowledge-pack/CURRENT_POSITION_REBUILD.md` | Owner-corrected positioning; verified against tracked code | HIGH | Created 2026-05-29, untracked |
| `docs/ops/project-roadmap-v2.md` (§2026-05-29 amendment) | Owner's direct amendment defining new target | HIGH | Amendment is at end of file (line 540+); top of file still has old label |
| `docs/adr/0009-non-real-live-execution-authorization-boundary.md` | Core safety decision | HIGH | Stable |
| `docs/adr/0012-bounded-risk-campaign-system.md` | Core BRC framework decision | HIGH | Stable |
| `docs/ops/brc-testnet-first-production-blocked-principle.md` | Current operating posture | HIGH | Stable |
| `docs/ops/runtime-safety-boundary.md` | Safety boundary | HIGH | Updated 2026-05-25 |
| `docs/ops/live-safe-v1-task-board.md` | Current task state | HIGH | Modified (unstaged) |

### 3.2 Decision records

| Path | Decision covered | Current relevance |
|---|---|---|
| `docs/adr/0001-live-safe-v1-scope.md` | Live-safe v1 scope definition | MEDIUM — superseded by BRC framing but safety principles still valid |
| `docs/adr/0008-personal-leveraged-campaign-business-chain.md` | PLC business chain | MEDIUM — superseded by BRC-0012 for project name, but business chain logic still relevant |
| `docs/adr/0013-brc-r5-002-admission-gate-phase1.md` | Admission gate | HIGH — current implementation |
| All other ADRs (0002-0007, 0010-0011) | Various technical decisions | MEDIUM — stable decision records |

### 3.3 Operational docs

| Path | Use | Current relevance |
|---|---|---|
| `docs/ops/live-safe-v1-progress.md` | Progress log (1893 lines) | HIGH — records all BRC work through 2026-05-29 |
| `docs/ops/live-safe-v1-program.md` | Program definition | MEDIUM — name predates BRC but contains safety rules |
| `docs/ops/brc-r5-002-admission-gate-phase1-state.md` | Admission gate state detail | HIGH — detailed Phase 1-17 state |
| `docs/ops/brc-r5-owner-driven-runtime-control-design.md` | Runtime control design | MEDIUM — design doc |
| `docs/ops/agent-working-rules.md` | Agent working rules | HIGH — governs Codex/Claude split |
| `docs/ops/codex-claude-handoff-template.md` | Handoff template | MEDIUM — operational |

### 3.4 Research archive

| Path | Research topic | Must not be interpreted as |
|---|---|---|
| `docs/ops/cpm-1-*.md` (14 files) | CPM-1 ETH Pinbar Pullback research | Current strategy candidate; CPM-1 is PAUSED/OOS_NEGATIVE |
| `docs/ops/direction-a-*.md` (12 files) | Direction A trend breakout research | Runtime-eligible strategy; classified PAUSE_FRAGILE/NON_RUNTIME |
| `docs/ops/dira-*.md` (6 files) | Direction A additional diagnostics | Production-ready evidence |
| `docs/ops/mtc-*.md` (6 files) | Main Trend Capture framework evaluations | Current capability |
| `docs/ops/ssd-*.md` (4 files) | Short-side breakdown research | Viable short strategy; REJECTED_FROZEN_BASELINE |
| `docs/ops/vei-*.md` (4 files) | VEI volatility expansion research | Independent alpha; all PnL from Direction A echo |
| `docs/ops/nsc-*.md` (14 files) | Next Strategy Candidate series | Current strategy pipeline |
| `docs/ops/te-*.md` (7 files) | Trend Edge validation series | Production-validated evidence |
| `docs/ops/sr-*.md` + `docs/ops/srd-*.md` + `docs/ops/srr-*.md` (6 files) | Strategy research reentry/reset/direction | Current research process |
| `docs/ops/sma-*.md` | Strategy module applicability map | Current capability mapping |
| `docs/ops/ltf-*.md` (2 files) | Low-timeframe data QA | Current data capability |
| `docs/ops/htpa-*.md` (2 files) | Lightweight frozen diagnostic specs | Current methodology |
| `docs/ops/direction-a-cross-asset-*.md` (3 files) | Cross-asset diagnostic | Production evidence |
| `docs/ops/observation-research-reset-*.md` + `docs/ops/btc-eth-*.md` (3 files) | BTC/ETH Phase 1 observation | Current observation capability |

### 3.5 Deprecated / superseded docs

| Path | Problem | Superseded by | Risk if kept unmarked |
|---|---|---|---|
| `docs/ops/knowledge-pack/PROJECT_OVERVIEW.md` | Uses old positioning "BRC Reset / Opportunity Structure Discovery v0" | `CURRENT_POSITION_REBUILD.md` | **HIGH** — Owner explicitly rejected this positioning |
| `docs/ops/knowledge-pack/FACT_REGISTRY.md` F-011 | Claims "27 migrations" | `TRUTH_REBUILD_PASS1.md` §4 | **HIGH** — treats untracked as integrated |
| `docs/ops/knowledge-pack/MODULE_MAP.md` Sections 4-5 | Treats untracked research modules as integrated | `TRUTH_REBUILD_PASS1.md` §4 | **HIGH** — overstates project capabilities |
| `docs/ops/knowledge-pack/CURRENT_STATE_AND_NEXT_ACTIONS.md` §7 | Claims "27 Alembic migrations" | `CURRENT_POSITION_REBUILD.md` §7.2 | MEDIUM — copy-paste propagation |
| `docs/ops/opportunity-research-control-board.md` | Phase label `RBC Reset / Opportunity Structure Discovery v0` | Owner 2026-05-29 amendment | MEDIUM — could be misread as current phase |
| `docs/ops/opportunity-hypothesis-register.md` | Same stale phase label | Same | MEDIUM |
| `docs/README.md` | Points to PLC Mainline v0 as mainline | Needs update for BRC/fast-trial positioning | **HIGH** — entry point for new readers |
| `docs/ops/project-branch-and-doc-governance-2026-05-25.md` | References `codex/personal-campaign-chain-v0` as current branch | Current branch is `codex/brc-owner-console-v0` | LOW — governance note, not high-readership |
| `docs/ops/knowledge-pack/CURRENT_STATE_AND_NEXT_ACTIONS.md` §5-6 prompts | Still reference "Opportunity Structure Discovery v0" | `CURRENT_POSITION_REBUILD.md` | MEDIUM — prompt templates use old label |
| `docs/gpt/` (all 9 files) | Historical ChatGPT audit from 2026-04-29; predates BRC framework entirely | N/A — pure archive | LOW if clearly marked as historical |
| `docs/ops/personal-leveraged-campaign-mainline-v0.md` | PLC framing superseded by BRC | ADR-0012 + roadmap-v2 amendment | MEDIUM — still a valid design document but no longer "current mainline" |

### 3.6 Unknown docs needing manual review

| Path | Why unclear | Suggested review |
|---|---|---|
| `docs/ops/bounded-risk-campaign-r0-r1-plan.md` | Plan doc; status unclear — was it executed? | Check if R0/R1 work is complete or superseded by R5 |
| `docs/ops/brc-r2-low-friction-ops-review-plan.md` | Status says IMPLEMENTING; current state unknown | Check if R2 is still active or parked |
| `docs/ops/brc-r4-api-surface-cleanup-plan.md` | Plan doc; was R4 completed? | Check git commits for R4 completion |
| `docs/ops/brc-pre-deploy-audit-backlog.md` | Audit backlog; still relevant? | Check if items have been resolved |
| `docs/ops/plc-phase5e-*.md` through `plc-phase3-*.md` | PLC phase docs; how do they relate to BRC? | Review if PLC phases map to BRC phases |
| `docs/ops/research-to-runtime-promotion-gate.md` | Promotion gate doc; still the current policy? | Verify alignment with ADR-0012 |
| `docs/ops/tc-tiny-*.md` | Tiny campaign task cards; status? | Check if completed or abandoned |
| `docs/ops/sq02-downside-cont-strategy-contract-skeleton-v0.md` | SQ02 skeleton; kept for future? | Verify status per STRATEGY_RESEARCH_HISTORY |
| `docs/product/brc-owner-console-full-refactor.md` | Console refactor; was it done? | Check if refactor was completed |

---

## 4. Conflict / stale-claim audit

| ID | Claim | File | Current truth | Risk | Suggested action |
|---|---|---|---|---|---|
| C-001 | Phase is `BRC Reset / Opportunity Structure Discovery v0` | `project-roadmap-v2.md:67` | Owner 2026-05-29: "fast trial-and-review research system for small risk-capital Campaigns" | **HIGH** — contradicts Owner's own amendment in same file | Add deprecation note at line 67; keep amendment at line 540+ as authoritative |
| C-002 | Same phase label | `opportunity-research-control-board.md:5,13` | Same | MEDIUM | Update phase label or add deprecation banner |
| C-003 | Same phase label | `opportunity-hypothesis-register.md:5` | Same | MEDIUM | Same |
| C-004 | "项目当前阶段为 BRC Reset / Opportunity Structure Discovery v0" | `knowledge-pack/FACT_REGISTRY.md:24` (F-001) | Superseded by Owner amendment | MEDIUM | Mark F-001 as SUPERSEDED |
| C-005 | Same phase in prompt templates | `knowledge-pack/CURRENT_STATE_AND_NEXT_ACTIONS.md:69,145` | Same | MEDIUM | Update prompts |
| C-006 | "项目有 27 个 Alembic migration（001-027）" | `knowledge-pack/FACT_REGISTRY.md:34` (F-011) | 21 tracked (001-021) + 6 untracked (022-027) | **HIGH** — treats untracked as integrated | Correct to "21 tracked + 6 untracked" |
| C-007 | "27 Alembic migrations" | `knowledge-pack/CURRENT_STATE_AND_NEXT_ACTIONS.md:153` | Same | MEDIUM | Same |
| C-008 | "27 个 Alembic migration" | `knowledge-pack/MODULE_MAP.md:90,134` | Same | MEDIUM | Same |
| C-009 | Strategy Family Registry PG chain "待确认" (UF-001) | `knowledge-pack/FACT_REGISTRY.md:51` | Not integrated: untracked files, no tracked imports | MEDIUM | Change to "未集成" |
| C-010 | Historical Research Sampling "待确认" (UF-003) | `knowledge-pack/FACT_REGISTRY.md` | Same: untracked, no tracked imports | MEDIUM | Same |
| C-011 | Historical Signal Evaluation "待确认" (UF-005/006) | `knowledge-pack/FACT_REGISTRY.md` | Same | MEDIUM | Same |
| C-012 | knowledge-pack mixes tracked/untracked as project capability | `knowledge-pack/MODULE_MAP.md` Sections 4-5 | All new research modules are untracked | **HIGH** | Add untracked/disclaimer banners |
| C-013 | docs/README.md points to PLC Mainline v0 | `docs/README.md:9` | Mainline is now BRC fast-trial research system | **HIGH** — entry point mismatch | Update README |
| C-014 | Current branch is `codex/personal-campaign-chain-v0` | `project-branch-and-doc-governance-2026-05-25.md:30` | Current branch is `codex/brc-owner-console-v0` | LOW | Add note or supersede |
| C-015 | GPT audit says "系统已不是玩具...只适合 Sim-1" | `docs/gpt/1. 全局成熟度判断.md` | Historical snapshot from 2026-04-29, predates BRC | LOW if marked as archive | Add historical archive banner |
| C-016 | `knowledge-pack/PROJECT_OVERVIEW.md` defines project as "BRC Reset / Opportunity Structure Discovery v0" | `knowledge-pack/PROJECT_OVERVIEW.md:10,14,19` | Owner explicitly rejected this positioning | **HIGH** | Mark SUPERSEDED |
| C-017 | PLC Mainline is "current Owner-facing business mainline" | `docs/README.md:9` + `plc-mainline-v0.md` | Superseded by BRC + fast-trial amendment | MEDIUM | Update README mainline pointer |

---

## 5. Proposed docs structure

### Option A: Minimal-invasive (Recommended)

Add governance layer on top of existing structure. No file moves.

```
docs/
  README.md                           ← UPDATE: new authority map + read order
  GOVERNANCE.md                       ← NEW: doc status policy, authority rules
  CURRENT_BASELINE.md                 ← NEW: single source of truth for current position

  adr/                                ← UNCHANGED: keep as-is
  gpt/                                ← ADD: archive banner to each file
  product/                            ← UNCHANGED

  ops/
    knowledge-pack/
      CURRENT_POSITION_REBUILD.md     ← Mark as CURRENT_CANON
      TRUTH_REBUILD_PASS1.md          ← Mark as CURRENT_CANON
      DOCS_GOVERNANCE_EXPLORATION_REPORT.md  ← This file
      PROJECT_OVERVIEW.md             ← Mark as SUPERSEDED
      FACT_REGISTRY.md                ← Mark with stale warnings
      MODULE_MAP.md                   ← Mark with stale warnings
      CURRENT_STATE_AND_NEXT_ACTIONS.md  ← Mark with stale warnings
      STRATEGY_RESEARCH_HISTORY.md    ← Mark as RESEARCH_ARCHIVE (low risk)
      PROMPT_LIBRARY.md               ← Keep as-is (low risk)

    [all other ops/ files]            ← UNCHANGED: keep in place
```

### Option B: Clean hierarchy

More organized but requires file moves (higher risk, needs Owner approval).

```
docs/
  README.md
  GOVERNANCE.md
  current/
    PROJECT_BASELINE.md
    FACT_REGISTRY.md
    READINESS_BLOCKERS.md
    DOCS_MAP.md
  adr/
  ops/
  research/
    strategy-archive/
    reports/
  archive/
    2026-05-29-knowledge-pack-v0/
    gpt-audit-2026-04-29/
  governance/
    DOCUMENT_GOVERNANCE.md
    DOC_STATUS_POLICY.md
```

### Recommended option

**Option A** — minimal-invasive. The existing `docs/ops/` structure is deep and wide, with 153 files that form a coherent research history. Moving files risks breaking internal references and losing git blame context. Adding governance labels and a new baseline document achieves the goal without disruption.

### Migration map (for Option A, no file moves)

| Current path | Action | Reason |
|---|---|---|
| `docs/README.md` | **UPDATE** — change mainline pointer to BRC/fast-trial, add authority map | Entry point must reflect current positioning |
| `docs/GOVERNANCE.md` | **NEW** — doc status policy, authority order | Governance reference |
| `docs/CURRENT_BASELINE.md` | **NEW** — condensed current facts from CURRENT_POSITION_REBUILD.md | Single authoritative baseline |
| `docs/gpt/*.md` (9 files) | **ADD BANNER** — "Historical ChatGPT audit, 2026-04-29, predates BRC framework" | Prevent misinterpretation |
| `docs/ops/knowledge-pack/PROJECT_OVERVIEW.md` | **ADD BANNER** — "SUPERSEDED by CURRENT_POSITION_REBUILD.md" | Owner rejected this positioning |
| `docs/ops/knowledge-pack/FACT_REGISTRY.md` | **ADD BANNER** — "Partially stale; see TRUTH_REBUILD_PASS1.md" | F-011, UF-001/002/003/005/006 are wrong |
| `docs/ops/knowledge-pack/MODULE_MAP.md` | **ADD BANNER** — same | Sections 4-5 overstate integration |
| `docs/ops/knowledge-pack/CURRENT_STATE_AND_NEXT_ACTIONS.md` | **ADD BANNER** — same | §7 wrong migration count; §5-6 old phase label |
| `docs/ops/opportunity-research-control-board.md` | **ADD NOTE** — "Phase label outdated; see CURRENT_BASELINE.md" | Stale phase label at top |
| `docs/ops/opportunity-hypothesis-register.md` | **ADD NOTE** — same | Same |
| `docs/ops/project-roadmap-v2.md:67` | **ADD NOTE** — "This label is superseded by 2026-05-29 amendment at line 540" | Contradiction within same file |

---

## 6. Proposed front matter policy

### Required fields

All important docs should have (or be given via banner) these fields:

```yaml
---
title: <document title>
status: CURRENT_CANON | ACTIVE_WORKING | DECISION_RECORD | OPERATIONAL |
        RESEARCH_ARCHIVE | HISTORICAL_ARCHIVE | DEPRECATED | SUPERSEDED | DRAFT | UNVERIFIED
authority: owner-confirmed | tracked-code | current-rebuild | historical-report | unverified
last_verified: YYYY-MM-DD
supersedes: [path, ...]      # optional
superseded_by: [path, ...]   # optional
---
```

### Status definitions

| Status | Meaning | Who should read it |
|---|---|---|
| `CURRENT_CANON` | Highest-authority current facts; verified against code and Owner input | Everyone |
| `ACTIVE_WORKING` | Current working doc; not final authority | Active developers |
| `DECISION_RECORD` | Accepted architectural decision | Everyone for context |
| `OPERATIONAL` | Current task/progress tracking | Active developers |
| `RESEARCH_ARCHIVE` | Historical research; does not represent current capability | Researchers only |
| `HISTORICAL_ARCHIVE` | Historical background; predates current architecture | Context-seekers only |
| `DEPRECATED` | Contains known errors; do not use as fact source | Nobody (unless auditing history) |
| `SUPERSEDED` | Replaced by a newer document | Nobody (redirect to replacement) |
| `DRAFT` | Unfinished; may contain errors | Authors only |
| `UNVERIFIED` | Content not verified against code or Owner input | Use with caution |

### Authority order

When two documents conflict, resolve by:

1. **Owner explicit correction / decision** (highest)
2. Current tracked code
3. Current git status
4. Current verified reports
5. ADR / decision records
6. Historical docs
7. Old knowledge-pack (lowest)

### Critical rules

```
untracked files must never be described as integrated capabilities
exists != integrated
implemented != verified
testnet verified != production-ready
metadata operation != runtime execution
signal_evaluated != trade intent
intent_recorded != order-capable
broad smoke candidate != strategy-ready
account facts read != account_equity available
```

### Examples

For `docs/ops/knowledge-pack/PROJECT_OVERVIEW.md`:
```yaml
---
title: Project Overview (Knowledge Pack v0)
status: SUPERSEDED
authority: historical-report
last_verified: 2026-05-29
superseded_by:
  - docs/ops/knowledge-pack/CURRENT_POSITION_REBUILD.md
notes: Owner explicitly rejected the positioning in this document on 2026-05-29
---
```

For `docs/ops/knowledge-pack/CURRENT_POSITION_REBUILD.md`:
```yaml
---
title: Current Position Rebuild
status: CURRENT_CANON
authority: owner-confirmed
last_verified: 2026-05-29
source_of_truth:
  - docs/ops/project-roadmap-v2.md (2026-05-29 amendment)
  - git status + git log
  - tracked code verification
---
```

---

## 7. Safe implementation plan

### Pass 1: Label and index only

**No file moves. No deletions. Only create new files and add banners to existing files.**

| Action | Files | Risk | Reversible |
|---|---|---|---|
| Create `docs/CURRENT_BASELINE.md` (condensed current facts) | 1 new file | None | Delete file |
| Create `docs/GOVERNANCE.md` (doc status policy) | 1 new file | None | Delete file |
| Update `docs/README.md` (new authority map, BRC mainline) | 1 edit | Low | git restore |
| Add SUPERSEDED banner to `knowledge-pack/PROJECT_OVERVIEW.md` | 1 edit | None | git restore |
| Add stale-warning banners to `knowledge-pack/FACT_REGISTRY.md`, `MODULE_MAP.md`, `CURRENT_STATE_AND_NEXT_ACTIONS.md` | 3 edits | None | git restore |
| Add historical archive banners to `docs/gpt/*.md` | 9 edits | None | git restore |
| Add phase-label outdated note to `opportunity-research-control-board.md`, `opportunity-hypothesis-register.md` | 2 edits | None | git restore |
| Add cross-reference note to `project-roadmap-v2.md` line 67 | 1 edit | None | git restore |

**Total Pass 1**: 2 new files, ~17 banner/note edits. All reversible.

### Pass 2: Archive old knowledge-pack

**Move old knowledge-pack to archive; create redirect.**

| Action | Files | Risk | Reversible |
|---|---|---|---|
| `git mv docs/ops/knowledge-pack/PROJECT_OVERVIEW.md` to `docs/archive/2026-05-29-knowledge-pack-v0/` | 1 move | Low | `git mv` back |
| `git mv docs/ops/knowledge-pack/FACT_REGISTRY.md` to archive | 1 move | Low | Same |
| `git mv docs/ops/knowledge-pack/MODULE_MAP.md` to archive | 1 move | Low | Same |
| `git mv docs/ops/knowledge-pack/CURRENT_STATE_AND_NEXT_ACTIONS.md` to archive | 1 move | Low | Same |
| `git mv docs/ops/knowledge-pack/STRATEGY_RESEARCH_HISTORY.md` to archive | 1 move | Low | Same |
| `git mv docs/ops/knowledge-pack/PROMPT_LIBRARY.md` to archive | 1 move | Low | Same |
| Keep `CURRENT_POSITION_REBUILD.md` and `TRUTH_REBUILD_PASS1.md` in `knowledge-pack/` as current canon | 0 | None | N/A |
| Create `docs/archive/2026-05-29-knowledge-pack-v0/README_REDIRECT.md` | 1 new | None | Delete file |
| Update `docs/README.md` read order | 1 edit | Low | git restore |

**Total Pass 2**: ~6 file moves, 1 new file, 1 edit. All reversible via `git mv` back.

### Pass 3: Restructure docs

**Requires larger Owner confirmation. Not recommended until Pass 1+2 are validated.**

| Action | Files | Risk | Reversible |
|---|---|---|---|
| Create `docs/current/` directory for active baselines | New dir | Low | Delete dir |
| Move CURRENT_POSITION_REBUILD.md to `docs/current/` | 1 move | Medium | `git mv` back |
| Consolidate research archive under `docs/research/` | ~60 file moves | **High** | Complex |
| Rename files for consistency | ~20 renames | **High** | May break references |
| Delete clearly obsolete files | ~5-10 deletes | **High** | `git checkout` recovery |

**Pass 3 is NOT recommended in the current phase.**

---

## 8. Follow-up prompts

### Prompt A — Pass 1 label/index only

```text
## Task
Execute Pass 1 of the docs governance plan. Read-only safety applies except for the specific files listed below.

## Allowed actions
1. Create `docs/CURRENT_BASELINE.md`:
   - Condensed version of CURRENT_POSITION_REBUILD.md §7 (one-line positioning, 12 core facts, forbidden actions, next steps)
   - Status: CURRENT_CANON, authority: owner-confirmed
   - Keep under 200 lines

2. Create `docs/GOVERNANCE.md`:
   - Doc status definitions (CURRENT_CANON through UNVERIFIED)
   - Authority order (Owner > tracked code > git status > verified reports > ADR > historical docs > old knowledge-pack)
   - Critical rules (exists != integrated, testnet verified != production-ready, etc.)
   - Keep under 150 lines

3. Update `docs/README.md`:
   - Change mainline pointer from "Personal Leveraged Campaign Mainline v0" to BRC fast-trial research system
   - Add read order: CURRENT_BASELINE.md first, then ADR-0009, ADR-0012, roadmap-v2
   - Add authority hierarchy note

4. Add banners (prepend 5-10 lines) to:
   - `docs/ops/knowledge-pack/PROJECT_OVERVIEW.md`: SUPERSEDED banner
   - `docs/ops/knowledge-pack/FACT_REGISTRY.md`: partially stale warning
   - `docs/ops/knowledge-pack/MODULE_MAP.md`: partially stale warning
   - `docs/ops/knowledge-pack/CURRENT_STATE_AND_NEXT_ACTIONS.md`: partially stale warning
   - `docs/gpt/*.md` (9 files): historical archive banner
   - `docs/ops/opportunity-research-control-board.md`: phase label outdated note
   - `docs/ops/opportunity-hypothesis-register.md`: phase label outdated note
   - `docs/ops/project-roadmap-v2.md`: add note near line 67 pointing to line 540 amendment

## Safety
- Only create/edit the files listed above
- Do not move or delete any files
- Do not modify any code files
- Do not git commit or push
- All changes are additive (banners/notes) or new files

## Done when
- All listed files have been created or updated
- No other files were modified
```

### Prompt B — Pass 2 archive old knowledge pack

```text
## Task
Execute Pass 2 of the docs governance plan. Move stale knowledge-pack v0 documents to archive.

## Prerequisites
- Pass 1 must be completed first (banners already added)

## Allowed actions
1. Create directory `docs/archive/2026-05-29-knowledge-pack-v0/`
2. Move (via git mv) the following files:
   - `docs/ops/knowledge-pack/PROJECT_OVERVIEW.md`
   - `docs/ops/knowledge-pack/FACT_REGISTRY.md`
   - `docs/ops/knowledge-pack/MODULE_MAP.md`
   - `docs/ops/knowledge-pack/CURRENT_STATE_AND_NEXT_ACTIONS.md`
   - `docs/ops/knowledge-pack/STRATEGY_RESEARCH_HISTORY.md`
   - `docs/ops/knowledge-pack/PROMPT_LIBRARY.md`
3. Keep in `docs/ops/knowledge-pack/`:
   - `CURRENT_POSITION_REBUILD.md` (current canon)
   - `TRUTH_REBUILD_PASS1.md` (current canon)
4. Create `docs/archive/2026-05-29-knowledge-pack-v0/README_REDIRECT.md`:
   - List all archived files
   - Point readers to CURRENT_POSITION_REBUILD.md as replacement
   - Explain why these were archived (stale positioning, wrong migration counts, overestimated integration)
5. Update `docs/README.md` read order if needed

## Safety
- Only move the 6 files listed above
- Do not delete any files
- Do not modify any code files
- Do not modify the content of moved files (banners from Pass 1 stay)
- Do not git commit or push
- All moves are reversible via `git mv` back

## Done when
- 6 files are in `docs/archive/2026-05-29-knowledge-pack-v0/`
- README_REDIRECT.md exists
- `docs/ops/knowledge-pack/` contains only the 2 current canon files + this report
```

---

## 9. Owner decisions needed

| ID | Decision | Options | Recommended | Why |
|---|---|---|---|---|
| D-001 | Accept `CURRENT_POSITION_REBUILD.md` as highest current baseline? | A: Yes / B: Revise first / C: Create new condensed version | A or C | It already reflects Owner's 2026-05-29 correction and is code-verified |
| D-002 | Mark old knowledge-pack v0 (6 files) as SUPERSEDED/DEPRECATED? | A: Yes, add banners / B: Move to archive / C: Leave as-is | A first, then B | Banners are zero-risk; archive is low-risk but needs confirmation |
| D-003 | Adopt tracked-only rule for capability claims? | A: Yes / B: Allow mixed but label clearly | A | Prevents repeating the "27 migrations" error |
| D-004 | Label 022-027 migration and related modules as "not integrated"? | A: Yes / B: Label as "draft, pending integration" / C: Leave as-is | A | They have zero tracked imports; "not integrated" is the factual state |
| D-005 | Create `docs/CURRENT_BASELINE.md` as single-line entry point? | A: Yes / B: Use CURRENT_POSITION_REBUILD.md directly | A | A 150-line baseline is more accessible than a 275-line rebuild report |
| D-006 | Create `docs/GOVERNANCE.md` with doc status policy? | A: Yes / B: Defer | A | Prevents future drift; low cost |
| D-007 | Update `docs/README.md` mainline pointer? | A: Yes, now / B: After Pass 1 | A | README is the entry point; stale pointer misleads new readers |
| D-008 | Start with Pass 1 only (banners + new files), defer Pass 2 (archive)? | A: Yes / B: Do both / C: Skip to Pass 2 | A | Pass 1 is zero-risk and immediately improves discoverability |

---

## 10. Appendix: high-risk docs

### 10.1 Docs that will mislead a new AI reader

1. **`docs/README.md`** — Says mainline is "Personal Leveraged Campaign Mainline v0". A new AI would start there and learn the wrong framing.

2. **`docs/ops/knowledge-pack/PROJECT_OVERVIEW.md`** — The most "overview-like" document, but uses rejected positioning. A new AI reading this first would form a wrong project model.

3. **`docs/ops/knowledge-pack/FACT_REGISTRY.md`** — Claims to be a fact registry but has known wrong facts (F-011, UF-001/002/003/005/006). A new AI would trust these.

4. **`docs/ops/knowledge-pack/MODULE_MAP.md`** — Treats 60+ untracked files as project modules. A new AI would think the project has capabilities it doesn't.

5. **`docs/ops/opportunity-research-control-board.md`** — Top-line phase label is wrong. First thing a reader sees.

6. **`docs/ops/project-roadmap-v2.md`** — Contains BOTH the old label (line 67) and the Owner correction (line 540). A reader stopping at line 67 gets the wrong answer.

### 10.2 Docs that are safe to trust

1. **`docs/adr/0009-*.md`** — Clear, stable, unambiguous
2. **`docs/adr/0012-*.md`** — Clear, stable, unambiguous
3. **`docs/ops/brc-testnet-first-production-blocked-principle.md`** — Clear operating principle
4. **`docs/ops/knowledge-pack/CURRENT_POSITION_REBUILD.md`** — Code-verified, Owner-corrected
5. **`docs/ops/knowledge-pack/TRUTH_REBUILD_PASS1.md`** — Identifies exactly what's stale
6. **`docs/ops/live-safe-v1-progress.md`** — Detailed factual log (but long)

### 10.3 Quantitative summary

| Category | Count | Percentage |
|---|---:|---:|
| ADR (decision records) | 13 | 7% |
| GPT historical audit | 9 | 5% |
| Knowledge pack | 8 | 4% |
| Product docs | 3 | 2% |
| Research reports (CPM, Direction A, MTC, SSD, VEI, etc.) | ~60 | 32% |
| BRC operational docs (plans, designs, state docs) | ~25 | 13% |
| Task cards and proposals | ~30 | 16% |
| Strategy research governance | ~20 | 11% |
| Other operational | ~20 | 11% |
| **Total** | **~188** | **100%** |

The core problem: ~60% of docs are research archives or operational history that should not be read as current capability statements. Only ~10% of docs (ADR + current canon) should be trusted without verification.
