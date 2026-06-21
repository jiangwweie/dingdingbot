# CODEX-CLEANUP-REVIEW-001 Mainline-Safe Cleanup Notes

Generated: 2026-06-16
Mode: scan/review/record only
Boundary: do not interfere with active mainline close-loop and live acceptance work

## Summary

This note consolidates the Claude token-burn reports and the Codex follow-up
scan into a cleanup queue that should not interfere with the active mainline
runtime work.

The active mainline is still doing final close-loop推进 and live-test
acceptance. Therefore the current cleanup lane must avoid runtime source,
tests, deploy scripts, watcher operations, Tokyo operations, exchange calls,
and any file likely to be touched by the mainline worker.

## Current Artifacts

| Artifact | Purpose | Status |
| --- | --- | --- |
| `CLAUDE-AUDIT-001-owner-language-leakage.md` | Owner/internal language leakage audit | Complete |
| `CLAUDE-AUDIT-002-runtime-safety-redteam.md` | Runtime safety red-team audit | Complete |
| `CLAUDE-TEST-MAP-001-runtime-path-test-coverage.md` | Runtime path test coverage matrix | Complete |
| `CLAUDE-DEBT-001-deletion-consolidation-map.md` | Deletion/consolidation candidate map | Complete |
| `CLAUDE-DOC-DEBT-001-doc-authority-conflict-map.md` | Document authority conflict map | Complete |
| `CLAUDE-SCHEMA-DEBT-001-personal-campaign-schema-usage.md` | Personal campaign schema usage scan | Complete |
| `CLAUDE-CLEANUP-PLAN-001-agent-config-wave1-rewrite-plan.md` | Agent config rewrite plan | Complete |

## Work Already Applied

The first applied cleanup was limited to agent/command instruction files:

- `.agents/skills/{architect,backend,kaigong,pm,pua-skill,qa,reviewer,shougong}/SKILL.md`
- `.claude/commands/{architect,backend,diagnostic,frontend,kaigong,pm,product-manager,qa,reviewer,shougong}.md`
- `.claude/team/{README,WORKFLOW,architect,backend-dev,code-reviewer,diagnostic-analyst,frontend-dev,product-manager,project-manager}`

These edits replace dead `docs/ops/*`, `docs/canon/*`, and `docs/adr/*`
authority references with current authority files:

- `AGENTS.md`
- `CLAUDE.md`
- `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md`
- `docs/current/AI_AGENT_CONSTRAINTS.md`
- `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md`
- `docs/current/MAIN_CONTROL_ROADMAP.md`
- `docs/current/strategy-group-handoffs/main-control-handoff-index.md`

No runtime source, tests, deploy files, scripts, live config, watcher code, or
exchange-facing code were intentionally modified by this cleanup lane.

## Current Process Safety

Codex stopped one short-lived orphaned Claude print process from this cleanup
batch to reduce API concurrency and avoid interfering with mainline work.

The long-running `claude --dangerously-skip-permissions` process was left alone
because it may belong to the active mainline worker or another user-owned
session.

## Remaining Dead References

The remaining scan hits fall into three buckets.

### Bucket A: Historical / Quarantined Docs

These files still mention `docs/canon/*` or old project names:

- `.claude/AGENTIC-WORKFLOW-GUIDE.md`
- `.claude/MCP-ORCHESTRATION.md`
- `.claude/TEAM-SETUP-SUMMARY.md`
- `.claude/team/QUICKSTART.md`
- `.claude/team/QUICK-REFERENCE.md`
- `.agents/skills/agentic-workflow/README.md`
- `.claude/skills/agentic-workflow/README.md`

Recommendation:

- Do not rewrite their full bodies during mainline acceptance.
- Later either archive/delete them or rewrite only the top caution header.
- Treat them as historical workflow material, not current agent authority.

### Bucket B: Duplicate Skill Copy

`.claude/skills/pua-skill/SKILL.md` still references old `docs/ops/*` and old
project naming. The active `.agents/skills/pua-skill/SKILL.md` was already
updated.

Recommendation:

- Later align `.claude/skills/pua-skill/SKILL.md` with the updated
`.agents/skills/pua-skill/SKILL.md`.
- Low risk, but not urgent while mainline is active.

### Bucket C: Memory Headers

`.claude/memory/project-core-memory.md` still says to read `docs/canon/` first.
`.claude/memory/MEMORY.md` still has the old project title.

Recommendation:

- Later update the memory rule to `AGENTS.md` + `docs/current/*`.
- Keep historical memory content; only fix the current authority header.

## Do Not Touch During Mainline Acceptance

The following cleanup ideas should be deferred until the main close-loop and
live acceptance work is complete:

- `src/` runtime source cleanup
- `tests/` cleanup or test relocation
- `scripts/` archival or deletion
- `reports/`, `output/`, `archive/`, `local-archives/` bulk moves
- old SQLite repository removal
- `config_manager.py` migration
- `runtime_execution_*` domain chain consolidation
- `trading-console/` archival or route removal
- any deploy, Tokyo, watcher, exchange, credential, or live config operation

## High-Value Review Findings To Revisit Later

These are review findings only, not current cleanup actions:

| Area | Finding | Suggested Later Action |
| --- | --- | --- |
| Runtime safety | `brc_operation_layer._account_facts_unavailable_reason` may not block stale freshness | Add targeted test and Codex-owned fix after acceptance |
| Runtime safety | Submit idempotency repository can be unavailable in degraded mode | Verify caller blocks on `BLOCKED`, then harden if needed |
| Runtime safety | `_execute_no_safe_executor` returns `noop` instead of explicit blocked status | Consider changing to blocked with a focused test |
| Architecture | FinalGate preview and ExecutionOrchestrator guards are decoupled | Document decision or add defense-in-depth test |
| Owner UI | `owner-runtime-console` is compliant; `trading-console` leaks internal terms | Decide whether `trading-console` is developer-only or archive candidate |
| Test coverage | Weakest areas are admission bootstrap, post-settlement notification/review | Add focused tests after live acceptance |
| Schema debt | `read_only_runtime_adapter_preview` has no runtime refs | Archive later if domain model is confirmed dead |
| Schema debt | `paper_observation_packet` keeps packet terminology | Rename only in a dedicated domain cleanup wave |

## Suggested Cleanup Waves After Mainline Acceptance

### Wave 1: Finish Agent Authority Cleanup

Scope:

- historical/quarantined headers
- duplicate `.claude/skills/pua-skill/SKILL.md`
- `.claude/memory/project-core-memory.md`
- `.claude/memory/MEMORY.md` title

Risk: low.

### Wave 2: Classify Frontend Surfaces

Scope:

- decide whether `trading-console/` remains developer/audit only
- if yes, document that classification
- if no, remove internal terms from primary labels or archive the surface

Risk: medium, because product surface semantics are involved.

### Wave 3: Schema Hygiene

Scope:

- archive `read_only_runtime_adapter_preview` if confirmed dead
- decide whether sandbox-only personal campaign schemas are still needed
- do not rename domain models until a dedicated task card exists

Risk: low to medium.

### Wave 4: Runtime Safety Follow-Up Tests

Scope:

- stale facts confirmation block
- idempotency degraded mode
- no-safe-executor behavior
- FinalGate/ExecutionOrchestrator decoupling evidence

Risk: medium. Codex-owned review required.

### Wave 5: Structural Slimming

Scope:

- old SQLite repository removal
- `binding` vs `linkage` consolidation
- `budgeted_autonomy_v01` fold-in
- config system unification
- runtime domain chain rationalization

Risk: medium to high. Should be sequenced after acceptance, with targeted tests.

## Validation Snapshot

Current modified files in this cleanup lane are limited to agent instruction
files. Untracked output reports live under `output/claude-token-burn/`.

Known unrelated/mainline-sensitive state:

- A long-running `claude --dangerously-skip-permissions` process remains and was not touched.
- No source/test/deploy cleanup should proceed while mainline acceptance is active.
