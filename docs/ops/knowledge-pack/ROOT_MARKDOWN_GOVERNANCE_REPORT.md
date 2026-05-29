---
title: ROOT_MARKDOWN_GOVERNANCE_REPORT
status: ACTIVE_WORKING
authority: root-markdown-governance-pass
last_verified: 2026-05-29
---

# Root Markdown Governance Report

Date: 2026-05-29
Method: audit + minimal banner/correction edits; no file moves, no code changes

---

## 1. Scope

Root-level Markdown files (`README.md`, `AGENTS.md`, `CLAUDE.md`, `MEMORY.md`) were audited for stale claims, outdated positioning, and missing pointers to the current docs governance canon established in commit `3df699b`.

---

## 2. Files reviewed

| File | Status before | Action taken | Notes |
|---|---|---|---|
| `README.md` | HIGH stale — "自动化交易系统", "完全动态化", "高并发", "具备自动执行能力", Sim-1 as current stage, no canon pointer | **Modified** — added IMPORTANT banner, replaced header with BRC positioning, replaced core principle, updated evolution stage, updated closing line, added Start Here read order, added historical note to project structure | Most stale root file |
| `AGENTS.md` | MEDIUM stale — "Live-safe v1 replanning" as phase, SSOT pointed to live-safe-v1 docs only, no knowledge-pack reference | **Modified** — updated date/phase, added "Current Document Authority" section, added knowledge-pack canon to SSOT | Red lines and task card rules still valid |
| `CLAUDE.md` | MEDIUM stale — "Live-safe v1 replanning" as phase, Required Context had no knowledge-pack docs | **Modified** — updated date/phase, added 3 knowledge-pack docs to Required Context | Task card rules, core file rules, engineering constraints unchanged |
| `MEMORY.md` | HIGH stale — "Phase 1 完成 → Phase 2 准备中", "v3 迁移进度 1/6", points to old docs/v3/, last updated 2026-03-30 | **Modified** — added IMPORTANT banner with current canon pointer and positioning, marked old content as historical | Old memory entries preserved as historical context |

---

## 3. Stale claims found

| ID | File | Claim | Current truth | Action |
|---|---|---|---|---|
| SC-01 | README.md:3 | "加密货币量化交易自动化系统 - 完全动态化、高并发、强状态一致性的交易信号监控、执行与回测平台" | BRC fast trial-and-review research system | Replaced with BRC header |
| SC-02 | README.md:13 | "Automated Execution（自动执行）- 量化交易自动化平台，支持信号监控、订单执行、仓位管理全流程" | auto_execution_enabled=False, signal-to-order=NO | Replaced with Research-Only Boundary |
| SC-03 | README.md:313 | "本系统为量化交易自动化平台，具备自动执行能力" | Automated execution disabled | Replaced with BRC positioning |
| SC-04 | README.md:300 | "当前阶段：Sim-1 观察期" | BRC fast trial-and-review research | Updated to BRC stage |
| SC-05 | README.md | No "Start here" read order | Knowledge-pack is current canon | Added 6-item read order |
| SC-06 | AGENTS.md:4 | "Current phase: Live-safe v1 replanning" | BRC fast trial-and-review research | Updated |
| SC-07 | AGENTS.md:19-31 | SSOT = live-safe-v1 docs only | Knowledge-pack is current canon | Added canon section |
| SC-08 | CLAUDE.md:4 | "Current phase: Live-safe v1 replanning" | BRC fast trial-and-review research | Updated |
| SC-09 | CLAUDE.md:19-26 | Required Context had no knowledge-pack docs | Knowledge-pack is baseline | Added 3 canon docs |
| SC-10 | MEMORY.md:43 | "Phase 1 完成 → Phase 2 准备中" | BRC fast trial-and-review research | Added IMPORTANT banner marking historical |
| SC-11 | MEMORY.md:44 | "v3 迁移进度: 1/6 阶段完成" | Historical artifact | Marked as historical in banner |
| SC-12 | MEMORY.md:48-55 | Points to docs/v3/ as current docs | docs/ops/knowledge-pack/ is current canon | Added canon pointer to banner |

---

## 4. Files modified

| File | Changes |
|---|---|
| `README.md` | Added IMPORTANT banner (8 lines), replaced header (lines 1-8), replaced core principle (lines 11-14), added project structure note, updated evolution stage (lines 300-304), updated docs section (lines 266-271), replaced closing line (line 313) |
| `AGENTS.md` | Updated date/phase (lines 3-4), added "Current Document Authority" section (13 lines), restructured SSOT section to include knowledge-pack canon |
| `CLAUDE.md` | Updated date/phase (lines 3-4), added 3 knowledge-pack entries to Required Context |
| `MEMORY.md` | Added IMPORTANT banner (10 lines) with current canon pointer, positioned above old content |

---

## 5. Files not modified

| File | Reason |
|---|---|
| `docs/` (all files) | Already governed in docs governance commit 3df699b |
| `src/` | Code — out of scope |
| `migrations/` | Out of scope |
| `scripts/` | Out of scope |
| `tests/` | Out of scope |

---

## 6. Remaining risks

| ID | Risk | Severity | Notes |
|---|---|---|---|
| RR-01 | README.md still contains detailed project structure listing execution modules (execution_orchestrator, order_lifecycle, etc.) | LOW | Historical note added; structure is still accurate for the codebase, just not the current research focus |
| RR-02 | README.md "核心功能" section describes signal strategies, risk calculation, notification, REST API | LOW | These capabilities exist in code; section is accurate but could be misread as "current active features" |
| RR-03 | AGENTS.md "Live-safe v1 Non-goals" section still references Live-safe v1 by name | LOW | Rules are still valid even if the phase label changed |
| RR-04 | MEMORY.md old memory entries (v3, Phase 1/2) are preserved without individual correction | LOW | Banner at top warns these are historical; individual entries would need owner input to update meaningfully |
| RR-05 | `memory/` directory files (user-role.md, etc.) not audited | LOW | These are persistent memory files, not project documentation |

---

## 7. Suggested commit scope

Root markdown governance should be committed as a separate commit from the docs governance commit:

```bash
git add README.md AGENTS.md CLAUDE.md MEMORY.md docs/ops/knowledge-pack/ROOT_MARKDOWN_GOVERNANCE_REPORT.md
```

Commit message:
```
docs(root): update root markdown to current BRC baseline

- Add IMPORTANT banner and BRC positioning to README.md
- Replace stale "自动化交易系统" header with current BRC description
- Add current document authority to AGENTS.md
- Add knowledge-pack canon to CLAUDE.md Required Context
- Add current project pointer banner to MEMORY.md
- Create root markdown governance report

Safety: no code changes, no migration changes.
```

---

## 8. Safety self-check

- [x] Only root Markdown changed (README.md, AGENTS.md, CLAUDE.md, MEMORY.md)
- [x] No code changed (no files under src/)
- [x] No migrations changed (no files under migrations/)
- [x] No scripts/tests changed
- [x] No runtime/exchange/PG action
- [x] No git add/commit/push
- [x] No files moved or deleted
- [x] Old content preserved with historical context (not deleted)
- [x] Current canon pointer added to all 4 files
