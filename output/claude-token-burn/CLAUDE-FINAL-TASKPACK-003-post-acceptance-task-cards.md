# CLAUDE-FINAL-TASKPACK-003 Post-Acceptance Task Cards

Generated: 2026-06-17
Source: CODEX-CLEANUP-REVIEW-001 + CLAUDE-FINAL-REVIEW-002
Mode: task card pack — no implementation

---

## Group 1: Acceptance-Safe Now

These can land during mainline acceptance without runtime interference.

### CARD-001A: Commit Agent Authority Cleanup Diff

| Field | Value |
|---|---|
| **Task ID** | CARD-001A |
| **Goal** | Commit the 27-file agent instruction authority path rewrite |
| **Why** | Diff is uncommitted; holding it risks merge conflict if mainline touches same files. The rewrite is safe — instruction-only, zero runtime behavior change. |
| **Allowed files** | `.agents/skills/*/SKILL.md`, `.claude/commands/*.md`, `.claude/team/**` (already modified) |
| **Forbidden files** | `src/`, `tests/`, `scripts/`, `deploy/`, `live-config.env`, `.env*` |
| **Requirements** | `git add` the 27 changed files; commit with message referencing this task ID |
| **Tests / Verification** | `git diff HEAD --stat -- src/ tests/ scripts/ deploy/` returns empty; `grep -rn "docs/ops/" .agents/skills/ .claude/commands/ .claude/team/ --include="*.md" \| grep -v "Do not recreate"` returns zero |
| **Done When** | Commit lands on `codex/owner-runtime-console-v1` with zero runtime diffs |
| **Hard Stop** | If `git diff` shows any `src/` or `tests/` changes, abort |
| **Risk** | Low |
| **Depends On** | None |
| **Owner** | Codex |

---

## Group 2: Post-Live-Acceptance P1

Dispatch after mainline acceptance and live-test close.

### CARD-002A: Quarantine Header Cleanup (7 files)

| Field | Value |
|---|---|
| **Task ID** | CARD-002A |
| **Goal** | Delete or rewrite CAUTION headers on 7 quarantined/superseded files to point to current authority chain |
| **Why** | These files still reference `docs/canon/*` which no longer exists. No active agent reads them as primary entrypoint, but stale paths confuse human readers and models scanning file listings. |
| **Allowed files** | `.claude/AGENTIC-WORKFLOW-GUIDE.md`, `.claude/MCP-ORCHESTRATION.md`, `.claude/TEAM-SETUP-SUMMARY.md`, `.claude/team/QUICKSTART.md`, `.claude/team/QUICK-REFERENCE.md`, `.agents/skills/agentic-workflow/README.md`, `.claude/skills/agentic-workflow/README.md` |
| **Forbidden files** | `src/`, `tests/`, `scripts/`, `deploy/`, `live-config.env`, `.env*`, any active runtime source |
| **Requirements** | Either delete files entirely, or replace CAUTION header authority list with `AGENTS.md` + `CLAUDE.md` + `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md` + `docs/current/AI_AGENT_CONSTRAINTS.md` + `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md`. Preserve historical body content if rewriting. |
| **Tests / Verification** | `grep -rn "docs/canon/" <target files>` returns zero |
| **Done When** | All 7 files either deleted or have current authority headers |
| **Hard Stop** | If any file is referenced by active agent routing, do not delete — rewrite header only |
| **Risk** | Low |
| **Depends On** | Mainline acceptance complete |
| **Owner** | Claude |

### CARD-002B: Duplicate Skill Copy Alignment

| Field | Value |
|---|---|
| **Task ID** | CARD-002B |
| **Goal** | Align `.claude/skills/pua-skill/SKILL.md` with the updated `.agents/skills/pua-skill/SKILL.md` |
| **Why** | The `.claude/skills/` copy still has dead `docs/ops/live-safe-v1-program.md` and `docs/ops/agent-working-rules.md` references. If agent resolution picks this copy, it reads dead paths. |
| **Allowed files** | `.claude/skills/pua-skill/SKILL.md` |
| **Forbidden files** | `.agents/skills/pua-skill/SKILL.md` (already correct — do not modify) |
| **Requirements** | Copy content from `.agents/skills/pua-skill/SKILL.md` to `.claude/skills/pua-skill/SKILL.md`, or delete the `.claude/skills/` duplicate |
| **Tests / Verification** | `grep -n "docs/ops/" .claude/skills/pua-skill/SKILL.md` returns zero |
| **Done When** | `.claude/skills/pua-skill/SKILL.md` matches `.agents/skills/pua-skill/SKILL.md` or is deleted |
| **Hard Stop** | Do not modify the `.agents/skills/` version |
| **Risk** | Low |
| **Depends On** | Mainline acceptance complete |
| **Owner** | Claude |

### CARD-002C: Memory Authority Header Fix

| Field | Value |
|---|---|
| **Task ID** | CARD-002C |
| **Goal** | Update `.claude/memory/project-core-memory.md` reading rule from `docs/canon/` to `docs/current/*`; update `.claude/memory/MEMORY.md` title and date |
| **Why** | Line 60 says "read docs/canon/ first" — dead path. An agent reading this memory may attempt to access `docs/canon/` and fail. MEMORY.md title is stale (2026-03-31). |
| **Allowed files** | `.claude/memory/project-core-memory.md`, `.claude/memory/MEMORY.md` |
| **Forbidden files** | Any file outside `.claude/memory/` |
| **Requirements** | Replace `docs/canon/` with `docs/current/*` in the reading rule. Update MEMORY.md title to reflect current project phase. Keep all other memory content intact. |
| **Tests / Verification** | `grep -n "docs/canon/" .claude/memory/project-core-memory.md` returns zero |
| **Done When** | Both memory files have current authority references |
| **Hard Stop** | Do not delete or rewrite memory body content — only fix the authority header |
| **Risk** | Low |
| **Depends On** | Mainline acceptance complete |
| **Owner** | Claude |

---

## Group 3: Post-Live-Acceptance P2

Sequence after P1 waves settle.

### CARD-003A: Frontend Surface Classification

| Field | Value |
|---|---|
| **Task ID** | CARD-003A |
| **Goal** | Decide whether `trading-console/` is developer/audit-only or a product surface; document the decision or remove internal terms |
| **Why** | `owner-runtime-console` is Owner-language compliant. `trading-console` leaks internal terms into primary labels. Classification needed before archiving or rewriting. |
| **Allowed files** | `trading-console/` (read only for classification), `docs/current/` (for decision documentation) |
| **Forbidden files** | `src/`, `tests/`, `scripts/`, `deploy/`, `live-config.env`, `.env*` |
| **Requirements** | Codex decision: (a) mark `trading-console/` as developer-only with a README header, or (b) remove internal terms from primary labels, or (c) archive the surface. Document the decision. |
| **Tests / Verification** | If option (b), `grep -rn "packet\|binding\|internal" trading-console/ --include="*.md" --include="*.html"` returns zero on primary labels |
| **Done When** | Decision documented and applied |
| **Hard Stop** | Do not delete `trading-console/` without explicit Codex approval — it may have audit value |
| **Risk** | Medium — product surface semantics involved |
| **Depends On** | Mainline acceptance complete; CARD-002A through CARD-002C landed |
| **Owner** | Codex (decision) + Claude (application) |

### CARD-003B: Schema Hygiene — Dead Model Archive

| Field | Value |
|---|---|
| **Task ID** | CARD-003B |
| **Goal** | Archive `read_only_runtime_adapter_preview` if confirmed dead; evaluate sandbox-only personal campaign schemas |
| **Why** | `read_only_runtime_adapter_preview` has no runtime refs — potential dead schema. Personal campaign schemas may be sandbox-only artifacts. |
| **Allowed files** | Domain model files containing these schemas (read only for audit) |
| **Forbidden files** | `src/` active runtime code, `tests/`, `scripts/`, `deploy/`, `live-config.env` |
| **Requirements** | Confirm `read_only_runtime_adapter_preview` has zero runtime callers. If dead, add an `ARCHIVED` marker or remove. Evaluate `paper_observation_packet` and personal campaign schemas for retention. |
| **Tests / Verification** | Grep for schema name across `src/` and `tests/` — zero runtime callers confirms dead |
| **Done When** | Dead schemas archived or removed; live schemas retained with documentation |
| **Hard Stop** | Do not rename domain models — that requires a dedicated task card with Codex approval |
| **Risk** | Low to medium |
| **Depends On** | Mainline acceptance complete |
| **Owner** | Codex (decision) + Claude (audit + application) |

### CARD-003C: doc-manager Skill Dead Directory Cleanup

| Field | Value |
|---|---|
| **Task ID** | CARD-003C |
| **Goal** | Remove `docs/archive/` references from doc-manager skill files |
| **Why** | `docs/archive/` directory does not exist. References are dead but harmless — low urgency. |
| **Allowed files** | `.agents/skills/doc-manager/SKILL.md`, `.agents/skills/doc-manager/references/rules.md`, `.claude/skills/doc-manager/SKILL.md`, `.claude/skills/doc-manager/references/rules.md`, `.claude/skills/SKILL_VERSIONS.md` |
| **Forbidden files** | `src/`, `tests/`, `scripts/`, `deploy/` |
| **Requirements** | Remove or update `docs/archive/` references to current paths |
| **Tests / Verification** | `grep -rn "docs/archive/" <target files>` returns zero |
| **Done When** | All dead directory references removed |
| **Hard Stop** | None — low risk |
| **Risk** | Negligible |
| **Depends On** | None — can land anytime |
| **Owner** | Claude |

---

## Group 4: Deferred Architecture Decisions

These require Codex design decision before implementation. Do not dispatch without explicit Codex card.

### CARD-004A: Stale Facts Confirmation Block

| Field | Value |
|---|---|
| **Task ID** | CARD-004A |
| **Goal** | Add targeted test and Codex-owned fix for `_account_facts_unavailable_reason` stale freshness blocking |
| **Why** | Review finding: the function may not block stale freshness. Needs Codex decision on expected behavior before implementation. |
| **Allowed files** | TBD by Codex (likely `src/application/` domain layer + `tests/`) |
| **Forbidden files** | `deploy/`, `live-config.env`, `.env*`, exchange gateway, credentials |
| **Requirements** | Codex issues specific task card with expected stale-facts blocking behavior |
| **Tests / Verification** | New test confirms stale facts are blocked at admission |
| **Done When** | Codex-decided behavior implemented and tested |
| **Hard Stop** | Do not implement without Codex task card — behavior change affects runtime safety boundary |
| **Risk** | Medium — runtime safety boundary |
| **Depends On** | Codex decision + mainline acceptance complete |
| **Owner** | Codex (decision + review) + Claude (implementation) |

### CARD-004B: Idempotency Degraded Mode Harden

| Field | Value |
|---|---|
| **Task ID** | CARD-004B |
| **Goal** | Verify submit idempotency repository caller blocks on `BLOCKED` status in degraded mode; harden if needed |
| **Why** | Review finding: idempotency repository can be unavailable in degraded mode. Caller must block, not bypass. |
| **Allowed files** | TBD by Codex |
| **Forbidden files** | `deploy/`, `live-config.env`, `.env*`, exchange gateway |
| **Requirements** | Codex issues task card specifying degraded-mode idempotency contract |
| **Tests / Verification** | Test simulates repository unavailability; confirms submit is blocked |
| **Done When** | Degraded mode idempotency contract verified and hardened |
| **Hard Stop** | Do not change idempotency behavior without Codex task card |
| **Risk** | Medium — affects submit safety |
| **Depends On** | Codex decision + mainline acceptance complete |
| **Owner** | Codex (decision + review) + Claude (implementation) |

### CARD-004C: No-Safe-Executor Blocked Status

| Field | Value |
|---|---|
| **Task ID** | CARD-004C |
| **Goal** | Change `_execute_no_safe_executor` return from `noop` to explicit blocked status |
| **Why** | Review finding: returning `noop` on missing safe executor is ambiguous. Explicit `blocked` is safer and more observable. |
| **Allowed files** | TBD by Codex (likely the function definition + its test) |
| **Forbidden files** | `deploy/`, `live-config.env`, `.env*` |
| **Requirements** | Codex approves status change; add focused test confirming blocked return |
| **Tests / Verification** | Test calls `_execute_no_safe_executor` and asserts blocked status |
| **Done When** | Return value is explicit blocked; test passes |
| **Hard Stop** | Do not change return semantics without Codex approval — callers may depend on `noop` |
| **Risk** | Medium — behavioral change in execution path |
| **Depends On** | Codex decision + mainline acceptance complete |
| **Owner** | Codex (decision + review) + Claude (implementation) |

### CARD-004D: FinalGate / ExecutionOrchestrator Decoupling Evidence

| Field | Value |
|---|---|
| **Task ID** | CARD-004D |
| **Goal** | Document or add defense-in-depth test for FinalGate preview and ExecutionOrchestrator guard decoupling |
| **Why** | Review finding: these two systems are decoupled. Either document the intentional design or add a test that catches divergence. |
| **Allowed files** | TBD by Codex |
| **Forbidden files** | `deploy/`, `live-config.env`, `.env*` |
| **Requirements** | Codex decides: (a) document decoupling as intentional, or (b) add defense-in-depth test |
| **Tests / Verification** | If option (b): test confirms FinalGate preview matches ExecutionOrchestrator guards |
| **Done When** | Decision documented or test added |
| **Hard Stop** | Do not add coupling without Codex architectural decision |
| **Risk** | Medium |
| **Depends On** | Codex decision + mainline acceptance complete |
| **Owner** | Codex (decision + review) + Claude (implementation) |

### CARD-004E: Weak Test Coverage — Admission + Post-Settlement

| Field | Value |
|---|---|
| **Task ID** | CARD-004E |
| **Goal** | Add focused tests for admission bootstrap and post-settlement notification/review |
| **Why** | Review finding: these are the weakest test coverage areas in the runtime path. |
| **Allowed files** | `tests/` (new test files for these areas) |
| **Forbidden files** | `src/` production code (tests only unless Codex allows source changes) |
| **Requirements** | Write tests covering admission bootstrap edge cases and post-settlement notification/review flows |
| **Tests / Verification** | New tests pass; coverage for target areas increases |
| **Done When** | Tests written and passing |
| **Hard Stop** | Do not modify production source without Codex task card |
| **Risk** | Low — tests only |
| **Depends On** | Mainline acceptance complete |
| **Owner** | Claude |

---

## Group 5: Do-Not-Dispatch Yet

These are blocked on mainline completion and/or require significant architectural sequencing. Hold until Codex explicitly clears.

### CARD-005A: Old SQLite Repository Removal

| Field | Value |
|---|---|
| **Task ID** | CARD-005A |
| **Goal** | Remove old SQLite repository code |
| **Why** | Structural slimming — dead code path. |
| **Allowed files** | TBD by Codex |
| **Forbidden files** | `deploy/`, `live-config.env`, `.env*`, exchange gateway |
| **Requirements** | Confirm zero callers; remove with targeted test coverage |
| **Tests / Verification** | Full test suite passes after removal |
| **Done When** | Old repository code removed; no regressions |
| **Hard Stop** | Do not remove until Codex confirms zero active callers |
| **Risk** | Medium to high — data layer |
| **Depends On** | Codex clearance + mainline acceptance complete + all P1/P2 tests passing |
| **Owner** | Codex (decision + review) + Claude (implementation) |

### CARD-005B: Config System Unification

| Field | Value |
|---|---|
| **Task ID** | CARD-005B |
| **Goal** | Unify config system (complete `config_manager.py` migration) |
| **Why** | Structural slimming — multiple config paths create maintenance burden. |
| **Allowed files** | TBD by Codex |
| **Forbidden files** | `deploy/`, `live-config.env`, `.env*`, exchange gateway, credentials, live profiles |
| **Requirements** | Codex issues migration task card with clear before/after state |
| **Tests / Verification** | Full test suite passes; config resolution is unified |
| **Done When** | Single config path; no legacy config references |
| **Hard Stop** | Do not start without Codex task card — config changes affect all runtime paths |
| **Risk** | High — cross-cutting concern |
| **Depends On** | Codex clearance + mainline acceptance complete + dedicated task card |
| **Owner** | Codex (architecture + review) + Claude (implementation) |

### CARD-005C: Runtime Domain Chain Rationalization

| Field | Value |
|---|---|
| **Task ID** | CARD-005C |
| **Goal** | Consolidate `runtime_execution_*` domain chain; fold in `budgeted_autonomy_v01` |
| **Why** | Structural slimming — domain chain is fragmented. |
| **Allowed files** | TBD by Codex |
| **Forbidden files** | `deploy/`, `live-config.env`, `.env*`, exchange gateway |
| **Requirements** | Codex issues domain consolidation task card |
| **Tests / Verification** | Full test suite passes; domain boundaries are clean |
| **Done When** | Domain chain consolidated; `budgeted_autonomy_v01` folded in |
| **Hard Stop** | Do not start without Codex task card — domain changes affect runtime safety boundary |
| **Risk** | High — core domain layer |
| **Depends On** | Codex clearance + mainline acceptance complete + dedicated task card |
| **Owner** | Codex (architecture + review) + Claude (implementation) |

### CARD-005D: `binding` vs `linkage` Consolidation

| Field | Value |
|---|---|
| **Task ID** | CARD-005D |
| **Goal** | Consolidate `binding` and `linkage` terminology in domain models |
| **Why** | Schema debt — two terms for the same concept create confusion. |
| **Allowed files** | TBD by Codex |
| **Forbidden files** | `deploy/`, `live-config.env`, `.env*` |
| **Requirements** | Codex chooses canonical term; rename across domain layer |
| **Tests / Verification** | Full test suite passes; no mixed terminology |
| **Done When** | Single term used consistently |
| **Hard Stop** | Do not rename without Codex decision on canonical term |
| **Risk** | Medium — domain model rename |
| **Depends On** | Codex decision + mainline acceptance complete |
| **Owner** | Codex (decision + review) + Claude (implementation) |

---

## Summary Table

| Group | Cards | Can Dispatch Now? |
|---|---|---|
| 1. Acceptance-Safe Now | CARD-001A | Yes |
| 2. Post-Live-Acceptance P1 | CARD-002A, 002B, 002C | After acceptance |
| 3. Post-Live-Acceptance P2 | CARD-003A, 003B, 003C | After P1 |
| 4. Deferred Architecture Decisions | CARD-004A–004E | After Codex decision |
| 5. Do-Not-Dispatch Yet | CARD-005A–005D | Codex clearance required |

---

## Do-Not-Touch Reminders

| Category | Paths |
|---|---|
| Runtime source | `src/**` |
| Tests | `tests/**` |
| Scripts | `scripts/**` |
| Deploy | `deploy/**` |
| Live config | `live-config.env`, `.env*` |
| Watcher/Tokyo ops | Any watcher or Tokyo operational code |
| Exchange/credential | Exchange gateway, credentials, live profiles |
| Source provenance strings | `docs/ops/*`, `docs/canon/*`, `docs/adr/*` refs inside `src/` and `tests/` |
