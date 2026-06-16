# CLAUDE-DOC-DEBT-001 Document Authority Conflict Map

Generated: 2026-06-16
Branch: codex/owner-runtime-console-v1

## Summary

The 2026-06-15 docs-governance compression successfully moved historical docs
into `docs/history-archive-2026-06-15-pre-governance.tar.gz` and established
`docs/current/*` as the authority baseline. However, **widespread stale
references remain** in agent configuration files, skill definitions, memory
indexes, and schema directories. These references point to files that no longer
exist (`docs/canon/`, `docs/adr/`, `docs/ops/`, `docs/gpt/`) and use project
naming (`盯盘狗 v3.0`) that predates the current StrategyGroup runtime-governance
pilot.

The most dangerous conflicts are **not in docs/** but in **agent configuration
layers** (`.claude/`, `.agents/skills/`) that instruct agents to read
non-existent files as authority sources. An agent following these instructions
would fail silently or fall back to cached/hallucinated context.

## Current Authority Baseline

Per `AGENTS.md` and `docs/README.md`, the authority order is:

| Rank | Source |
| --- | --- |
| 1 | Owner explicit correction / decision |
| 2 | Current tracked code + current git status |
| 3 | `docs/current/*` |
| 4 | Current verified runtime reports |
| 5 | Historical archive material only when task explicitly requires recovery |

Current authority files:

| File | Role |
| --- | --- |
| `AGENTS.md` | Agent operating guide, standing authorization, gate behavior |
| `CLAUDE.md` | Claude worker guide, task card requirement, core file rule |
| `docs/README.md` | Doc entry point, lists kept-current and removed namespaces |
| `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md` | Owner workflow SSOT |
| `docs/current/AI_AGENT_CONSTRAINTS.md` | Agent execution constraints |
| `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md` | Owner-facing state contract |
| `docs/current/MAIN_CONTROL_ROADMAP.md` | Planning tracks and subgoals |
| `docs/current/strategy-group-handoffs/` | StrategyGroup handoff packs |
| `docs/current/OWNER_RUNTIME_CONSOLE_UI_*` | UI governance and element contract |
| `docs/current/OWNER_RUNTIME_CONSOLE_PRODUCT_PROJECTION_CONTRACT.md` | Product projection semantics |
| `docs/current/OWNER_CONSOLE_*_HANDOFF.md` | Frontend/backend handoff history |

## Conflict Table

| File/Area | Old Claim | Conflicts With | Severity | Recommended Action | Reason |
| --- | --- | --- | --- | --- | --- |
| `.claude/MCP-ORCHESTRATION.md` | References `docs/canon/AGENT_WORKSPACE_RULES.md`, `docs/canon/PROJECT_BASELINE_CURRENT.md`, `docs/canon/BRC_TARGET_SEMANTICS.md`, `docs/canon/RUNTIME_SAFETY_BOUNDARY.md` as required reading | `AGENTS.md` authority order (docs/canon/ no longer exists) | **HIGH** | Update to reference `AGENTS.md` + `docs/current/*` | Agent bootstrapping will fail or hallucinate if it follows non-existent file paths |
| `.claude/AGENTIC-WORKFLOW-GUIDE.md` | Same four `docs/canon/` references + "盯盘狗 v3.0" project name | `AGENTS.md` + `README.md` (project is now "BRC StrategyGroup Runtime Governance") | **HIGH** | Rewrite or archive; remove all `docs/canon/` and `盯盘狗` references | Misdirects agent context at startup |
| `.claude/TEAM-SETUP-SUMMARY.md` | Same four `docs/canon/` references + "盯盘狗 v3.0" | `AGENTS.md` | **HIGH** | Rewrite or archive | Same as above |
| `.claude/team/QUICKSTART.md` | References `docs/canon/AGENT_WORKSPACE_RULES.md`, `docs/canon/PROJECT_BASELINE_CURRENT.md`, `docs/canon/BRC_TARGET_SEMANTICS.md` | `AGENTS.md` | **HIGH** | Update to `docs/current/*` | Agent onboarding reads dead paths |
| `.claude/team/WORKFLOW.md` | References `docs/ops/live-safe-v1-program.md`, `docs/ops/live-safe-v1-task-board.md`, `docs/ops/live-safe-v1-findings.md`, `docs/ops/live-safe-v1-progress.md`, `docs/agent-working-rules.md`, `docs/adr/` | `docs/README.md` (all removed from authority) | **HIGH** | Rewrite workflow references to use `docs/current/strategy-group-handoffs/` and `docs/current/MAIN_CONTROL_ROADMAP.md` | Workflow steps reference non-existent tracking files |
| `.claude/team/README.md` | References `docs/ops/live-safe-v1-*` | `docs/README.md` | **MEDIUM** | Update or archive | Same dead-path issue |
| `.claude/memory/project-core-memory.md` | "Always read AGENTS.md / CLAUDE.md and docs/canon/ first"; "If memory conflicts with docs/canon, docs/canon wins"; "盯盘狗 v3.0" | `AGENTS.md` authority order (docs/canon/ gone) | **HIGH** | Update reading rule to `docs/current/*`; remove `盯盘狗` references | Memory file instructs agents to read non-existent authority |
| `.claude/memory/MEMORY.md` | "盯盘狗项目记忆系统索引", updated 2026-03-11 | `README.md` project identity | **LOW** | Update title to "BRC Project Memory Index" | Naming confusion only |
| `.claude/MCP-ENV-CONFIG.md` | "盯盘狗 v3.0" | `README.md` | **LOW** | Update project name | Naming confusion only |
| `.claude/MCP-QUICKSTART.md` | "盯盘狗量化项目", "盯盘狗 v3.0" | `README.md` | **LOW** | Update project name | Naming confusion only |
| `.agents/skills/kaigong/SKILL.md` | References `docs/ops/agent-current-brc-baseline.md`, `docs/ops/live-safe-v1-program.md`, `docs/ops/live-safe-v1-task-board.md`, `docs/ops/live-safe-v1-progress.md`, `docs/ops/live-safe-v1-findings.md`, `docs/ops/agent-working-rules.md` | `docs/README.md` | **HIGH** | Rewrite kaigong skill to reference `AGENTS.md` + `docs/current/*` | /kaigong skill bootstraps from dead files |
| `.agents/skills/pm/SKILL.md` | Same `docs/ops/live-safe-v1-*` references | `docs/README.md` | **MEDIUM** | Update references | PM skill reads dead tracking files |
| `.agents/skills/reviewer/SKILL.md` | References `docs/ops/agent-current-brc-baseline.md`, `docs/ops/live-safe-v1-program.md`, `docs/ops/agent-working-rules.md` | `docs/README.md` | **MEDIUM** | Update references | Reviewer skill reads dead files |
| `.agents/skills/backend/SKILL.md` | Same `docs/ops/` references | `docs/README.md` | **MEDIUM** | Update references | Backend skill reads dead files |
| `.agents/skills/architect/SKILL.md` | References `docs/ops/` + `docs/canon/PROJECT_BASELINE_CURRENT.md` | `docs/README.md` | **MEDIUM** | Update references | Architect skill reads dead files |
| `.agents/skills/qa/SKILL.md` | References `docs/ops/live-safe-v1-program.md`, `docs/ops/agent-working-rules.md` | `docs/README.md` | **MEDIUM** | Update references | QA skill reads dead files |
| `.agents/skills/pua-skill/SKILL.md` | References `docs/ops/live-safe-v1-program.md`, `docs/ops/agent-working-rules.md` | `docs/README.md` | **MEDIUM** | Update references | PUA skill reads dead files |
| `.agents/skills/agentic-workflow/README.md` | References `docs/canon/AGENT_WORKSPACE_RULES.md`, `docs/canon/PROJECT_BASELINE_CURRENT.md`, `docs/canon/BRC_TARGET_SEMANTICS.md` | `AGENTS.md` | **MEDIUM** | Update references | Agentic workflow reads dead files |
| `.claude/skills/agentic-workflow/README.md` | Same `docs/canon/` references | `AGENTS.md` | **MEDIUM** | Update references | Duplicate of above |
| `.claude/skills/pua-skill/SKILL.md` | References `docs/ops/live-safe-v1-program.md`, `docs/ops/agent-working-rules.md` | `docs/README.md` | **LOW** | Update references | PUA skill reads dead files |
| `MEMORY.md` (user memory index) | "盯盘狗项目知识图谱", last updated 2026-04-05, references old architecture decisions from pre-governance era | `README.md` project identity | **LOW** | Update title; accept as historical knowledge base | Memory is chronological; old entries are valid history |
| `docs/schemas/personal_campaign/` | 11 schema files + examples for packet-based workflow (`human_arm_decision`, `paper_observation_packet`, `trade_intent`, `mode_advice`, `risk_order_plan`) | `AGENTS.md` ("system is not a raw evidence-packet workflow") | **MEDIUM** | Evaluate which schemas are still exercised by tests; archive unused ones | Schema directory implies packet-as-interface model |
| `src/` (16 files) | `personal_campaign_*` module names | Current StrategyGroup runtime governance naming | **LOW** | No immediate action; rename only during refactoring | Code naming is internal; not visible to Owner |
| `docs/current/OWNER_CONSOLE_ISOLATED_FRONTEND_HANDOFF.md` | References external worktree `/Users/jiangwei/Documents/final-owner-console` | Current mainline ownership | **LOW** | Keep as historical handoff; do not reference as active worktree | Frozen exploration snapshot |
| `docs/current/OWNER_CONSOLE_SOURCE_READINESS_CONFIRMATION.md` | Commit-specific data (`e7c2f400...`) | Living documentation principle | **LOW** | Accept as point-in-time evidence; re-stamp when re-verified | Confirmation is evidence, not living spec |
| `docs/current/OWNER_RUNTIME_CONSOLE_PRODUCT_PROJECTION_CONTRACT.md` | References legacy endpoint `GET /api/owner-runtime-console/product-projection` and `GET /api/owner-runtime-console/readmodel` | Current production target `GET /api/trading-console/owner-console-source-readiness` | **LOW** | Already correctly marked as "not the mainline production target" | Documented transition, not conflict |
| `AGENTS.md` | Mentions `program/live-safe-v1` as "older integration branch name and historical baseline" | Current `codex/*` branch model | **NONE** | No action needed | Correctly contextualized as historical |
| `docs/README.md` | Lists `docs/adr`, `docs/archive`, `docs/audit`, `docs/canon`, `docs/gpt`, `docs/ops`, `docs/product` as "Removed From Current Authority" | Actual state: these directories no longer exist (except `docs/archive/`) | **NONE** | No action needed | Accurate documentation of removal |

## Archive-Only Concepts

These concepts exist only in the historical archive and should **never**
re-enter current authority:

| Concept | Old Location | Why Archive-Only |
| --- | --- | --- |
| Per-deploy chat confirmation | `docs/ops/` | Conflicts with standing authorization in `AGENTS.md` |
| Per-order Owner chat confirmation | `docs/ops/` | Conflicts with "Owner is supervisor, not operator" |
| Evidence-packet-as-Owner-interface | `docs/canon/`, `docs/ops/` | Conflicts with Strategy Control Board contract |
| Manual gate assembly workflow | `docs/canon/` | Conflicts with automated FinalGate + Operation Layer |
| `docs/ops/live-safe-v1-program.md` tracking | `docs/ops/` | Replaced by `docs/current/MAIN_CONTROL_ROADMAP.md` |
| `docs/ops/agent-working-rules.md` | `docs/ops/` | Replaced by `AGENTS.md` + `CLAUDE.md` |
| `docs/ops/agent-current-brc-baseline.md` | `docs/ops/` | Replaced by `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md` |
| `docs/canon/AGENT_WORKSPACE_RULES.md` | `docs/canon/` | Replaced by `AGENTS.md` |
| `docs/canon/PROJECT_BASELINE_CURRENT.md` | `docs/canon/` | Replaced by `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md` |
| `docs/canon/BRC_TARGET_SEMANTICS.md` | `docs/canon/` | Replaced by `AGENTS.md` product objective section |
| `docs/canon/RUNTIME_SAFETY_BOUNDARY.md` | `docs/canon/` | Replaced by `AGENTS.md` safety boundary section |
| `docs/canon/STRATEGYGROUP_RUNTIME_PILOT_OVERLAY.md` | `docs/canon/` | Content folded into `AGENTS.md` StrategyGroup Runtime Path |
| `docs/canon/STRATEGY_RUNTIME_GUIDE.md` | `docs/canon/` | Replaced by `docs/current/` authority files |
| `docs/canon/TECH_DEBT_BASELINE.md` | `docs/canon/` | Historical debt snapshot; not current authority |
| `docs/canon/DOCUMENT_GOVERNANCE.md` | `docs/canon/` | Replaced by `AGENTS.md` authority order |
| `docs/gpt/` (all files) | `docs/gpt/` | GPT-generated research docs; not operational authority |
| `docs/audit/` (all files) | `docs/audit/` | Window-based audit reports; historical evidence only |
| `docs/adr/` (all files) | `docs/adr/` | Architecture decision records; historical provenance |
| `盯盘狗 v3.0` project identity | Various | Replaced by "BRC StrategyGroup Runtime Governance" |

## Current Concepts That Need Stronger Placement

These concepts are defined in `docs/current/` but are repeated across many
files without a single clear SSOT pointer:

| Concept | Current SSOT | Problem |
| --- | --- | --- |
| Owner product state vocabulary (`运行中`, `等待机会`, etc.) | `OWNER_RUNTIME_OPERATING_MODEL.md` | Repeated in 6+ files; agents may read any one of them |
| Forbidden UI terms (`FinalGate`, `Operation Layer`, etc.) | `AI_AGENT_CONSTRAINTS.md` | Repeated in 4+ files |
| Standing authorization list | `AGENTS.md` | Repeated in `CLAUDE.md` and `AI_AGENT_CONSTRAINTS.md` |
| Gate classification (`waiting_for_market`, `missing_fact`, etc.) | `AGENTS.md` | Repeated in `AI_AGENT_CONSTRAINTS.md` |
| Safety boundary (never bypass list) | `AGENTS.md` | Repeated in `CLAUDE.md`, `README.md`, and every handoff file |
| StrategyGroup runtime path chain | `AGENTS.md` | Repeated in `README.md`, `CLAUDE.md`, `OWNER_RUNTIME_OPERATING_MODEL.md` |
| Source health enum (`ready`, `ready_empty`, etc.) | `OWNER_CONSOLE_BACKEND_SOURCE_HANDOFF.md` | Also in `OWNER_RUNTIME_CONSOLE_PRODUCT_PROJECTION_CONTRACT.md` and `OWNER_CONSOLE_ISOLATED_FRONTEND_HANDOFF.md` |

**Recommendation**: Each concept should live in exactly one `docs/current/`
file. Other files should reference it by path rather than duplicating the
content. This reduces drift risk when the concept evolves.

## Files That Should Become Indexes

| File | Current State | Recommended Treatment |
| --- | --- | --- |
| `docs/README.md` | Lists current docs and removed namespaces | Already an index; keep as-is |
| `docs/current/strategy-group-handoffs/main-control-handoff-index.md` | Lists StrategyGroup handoffs | Already an index; keep as-is |
| `.claude/memory/MEMORY.md` | Lists memory files with old project name | Update title; keep as chronological index |
| `MEMORY.md` (user memory) | Lists architecture decisions from 2026-03/04 | Keep as historical knowledge index; update header |

## Files That Should Be Archived/Deleted Later

These files contain references to non-existent authority sources and should
be rewritten or removed in the next cleanup wave:

| File | Reason |
| --- | --- |
| `.claude/MCP-ORCHESTRATION.md` | 4 dead `docs/canon/` references; "盯盘狗 v3.0" |
| `.claude/AGENTIC-WORKFLOW-GUIDE.md` | 4 dead `docs/canon/` references; "盯盘狗 v3.0" |
| `.claude/TEAM-SETUP-SUMMARY.md` | 4 dead `docs/canon/` references; "盯盘狗 v3.0" |
| `.claude/team/QUICKSTART.md` | 3 dead `docs/canon/` references |
| `.claude/team/WORKFLOW.md` | 6 dead `docs/ops/` references + `docs/adr/` |
| `.claude/team/README.md` | 5 dead `docs/ops/` references |
| `.claude/memory/project-core-memory.md` | "docs/canon/" reading rule; "盯盘狗 v3.0" |
| `.claude/MCP-ENV-CONFIG.md` | "盯盘狗 v3.0" |
| `.claude/MCP-QUICKSTART.md` | "盯盘狗 v3.0" |
| `.agents/skills/kaigong/SKILL.md` | 6 dead `docs/ops/` references |
| `.agents/skills/pm/SKILL.md` | 5 dead `docs/ops/` references |
| `.agents/skills/reviewer/SKILL.md` | 3 dead `docs/ops/` references |
| `.agents/skills/backend/SKILL.md` | 3 dead `docs/ops/` references |
| `.agents/skills/architect/SKILL.md` | 4 dead `docs/ops/` + `docs/canon/` references |
| `.agents/skills/qa/SKILL.md` | 2 dead `docs/ops/` references |
| `.agents/skills/pua-skill/SKILL.md` | 2 dead `docs/ops/` references |
| `.agents/skills/agentic-workflow/README.md` | 3 dead `docs/canon/` references |
| `.claude/skills/agentic-workflow/README.md` | 3 dead `docs/canon/` references |
| `.claude/skills/pua-skill/SKILL.md` | 2 dead `docs/ops/` references |
| `docs/archive/2026-05-29-knowledge-pack-v0 2/` | Duplicate directory with space in name |

## Suggested Documentation Cleanup Waves

### Wave 1: Agent Configuration Alignment (HIGH priority)

Fix all `.claude/` and `.agents/skills/` files that reference non-existent
authority paths. This is the highest-risk area because agents bootstrapping
from these files will read dead paths.

**Files**: All 19 files listed in "Files That Should Be Archived/Deleted Later"
**Approach**: Rewrite each file to reference `AGENTS.md` + `docs/current/*` as
authority. Remove "盯盘狗 v3.0" project naming. Remove references to
`docs/canon/`, `docs/adr/`, `docs/ops/`, `docs/gpt/`.
**Risk**: Low — these are agent configuration files, not product code.
**Estimated scope**: ~15 files, ~200 lines changed.

### Wave 2: Schema Directory Evaluation (MEDIUM priority)

Evaluate `docs/schemas/personal_campaign/` to determine which schemas are
still exercised by current tests. Archive unused schemas into the historical
archive.

**Files**: 11 schema files + examples in `docs/schemas/personal_campaign/`
**Approach**: Run `grep -r` against test files to find active schema
references. Move unused schemas to archive.
**Risk**: Low — schemas are documentation, not runtime code.
**Estimated scope**: ~15 files to evaluate, ~10 files potentially archived.

### Wave 3: Current Docs Deduplication (LOW priority)

Reduce content duplication across `docs/current/` files. Establish each
concept in exactly one SSOT file and use cross-references elsewhere.

**Files**: 10 files in `docs/current/`
**Approach**: For each duplicated concept, keep it in the most authoritative
file and replace copies with `See docs/current/<file>.md` references.
**Risk**: Low — current docs are already internally consistent.
**Estimated scope**: ~30 lines of duplication to resolve.

### Wave 4: Memory Index Refresh (LOW priority)

Update `MEMORY.md` (user memory) header from "盯盘狗项目知识图谱" to
"BRC Project Knowledge Graph" and update the last-updated timestamp. Update
`.claude/memory/project-core-memory.md` to remove `docs/canon/` reading rules.

**Files**: 2 memory index files
**Approach**: Header/rule text updates only.
**Risk**: None.
**Estimated scope**: ~10 lines changed.

### Wave 5: Source Code Naming (DEFERRED)

The 16 `src/` files using `personal_campaign_*` naming are internal code
modules. Rename only during natural refactoring — this is not a documentation
debt priority.

**Files**: 16 Python modules in `src/`
**Approach**: Rename during next major refactoring pass.
**Risk**: Medium — requires test updates and import changes.
**Estimated scope**: ~16 files, ~50 import references.

---

*End of report.*
