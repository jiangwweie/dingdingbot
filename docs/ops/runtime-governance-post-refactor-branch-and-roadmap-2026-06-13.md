# Runtime Governance Post-refactor Branch And Roadmap

Last updated: 2026-06-13
Status: CURRENT_POST_REFACTOR_BRANCH_PLAN

## Purpose

This note records the branch, tag, deployment, and next-planning baseline after
the BRC runtime governance refactor completion audit.

It is not a new architecture authority. Canon remains under `docs/canon/*`.
Execution boundary authority remains:

- `docs/ops/agent-current-brc-baseline.md`
- `docs/canon/BRC_TARGET_SEMANTICS.md`
- `docs/canon/RUNTIME_SAFETY_BOUNDARY.md`
- `docs/canon/AGENT_WORKSPACE_RULES.md`

## Version Anchors

| Anchor | Ref | Meaning |
|---|---|---|
| Program branch | `program/live-safe-v1` | Current controller integration branch after completion/deploy docs |
| Dev branch | `dev` | Reviewed integration snapshot, not a scratch branch |
| Release branch | `release/brc-runtime-governance-20260613-r0` | Frozen post-refactor source/documentation snapshot |
| Completion tag | `brc-runtime-governance-refactor-complete-20260613-r0` at `28a8ba03` | Refactor completion milestone |
| Tokyo deploy tag | `deploy/tokyo-runtime-governance-20260613-80da4d67` at `80da4d67` | Deployed code release on Tokyo |

Branches are movable refs. Tags are immutable evidence anchors. The completion
tag intentionally points to the commit that closed the refactor/deploy evidence;
later branch-management documentation commits may advance the program, dev, and
release branches without changing the deployed code tag.

Tokyo current release:

```text
/home/ubuntu/brc-deploy/releases/brc-runtime-governance-80da4d67-20260613Trtf107-cleanup-policy
```

The deployed code commit is `80da4d67`. The later `28a8ba03` commit records
deployment evidence and does not require a redeploy by itself.

## Branch Roles

| Branch type | Rule |
|---|---|
| `program/live-safe-v1` | Main controller integration branch for the active BRC runtime program |
| `dev` | Reviewed integration snapshot only; do not use as scratch |
| `release/*` | Frozen milestone branch, not normal development |
| `codex/*` | Focused task branch from `program/live-safe-v1` |
| Side-agent branch | Must match the task scope and stop after the task card done condition |

Core execution-chain files remain Codex-owned by default. Side agents must not
touch core execution/risk files unless the task card explicitly allows it.

## Post-refactor Mainline

The runtime mainline is now:

```text
strategy signal readiness
-> semantic / runtime selector readiness
-> official prepare / FinalGate / controlled-submit preflight
-> controlled runtime cycle
-> durable execution result
-> post-submit finalize
-> budget / attempt settlement
-> next-attempt gate
```

Historical pre-attempt rehearsal and first-real-submit packet scripts are
replay / recovery / history compatibility surfaces only. They are not runtime
grants, bounded auto-attempt primary gates, or automatic live submit authority.

## Next Planning Baseline

### P0 - Operationalize The Completed Runtime Loop

Goal: run the completed loop in a way that is repeatable, auditable, and not
manual-ID-driven.

Work items:

1. Add an operator runbook for live runtime observation, next-attempt gate
   interpretation, and post-submit finalize recovery.
2. Validate the current live runtime state with read-only account, position,
   open-order, protection, and budget facts.
3. When strategy facts become ready, allow a new attempt to start from a fresh
   strategy signal chain, not from old authorization replay.

Current 2026-06-13 implementation progress:

| Item | Status | Evidence |
|---|---|---|
| P0-A operator runbook | integrated | `docs/ops/runtime-governance-p0-operator-runbook-2026-06-13.md` |
| P0-A live fact validation | integrated | `docs/ops/runtime-governance-p0-live-fact-validation-2026-06-13.md` |
| P0-A operator live fact packet builder | integrated | `scripts/build_runtime_operator_live_fact_packet.py` |
| P0-B fresh attempt readiness guard | integrated | `scripts/build_runtime_fresh_attempt_readiness_packet.py` |
| Current Tokyo next attempt | blocked | active BNB runtime is `waiting_for_position_resolution` |

### P1 - Console Productization

Goal: make the Owner surface match the real runtime state machine.

Work items:

1. Show runtime grant, current gate, active position, protection, and next
   attempt blocker in one operator view.
2. Show post-submit finalize, budget settlement, and attempt outcome facts.
3. Avoid frontend-only ready states that are not backed by runtime evidence.
4. Keep light/dark mode support intact.

Current 2026-06-13 implementation progress:

| Item | Status | Evidence |
|---|---|---|
| P1-A operations cockpit runtime governance read model | integrated | `src/application/readmodels/trading_console.py` |
| P1-A Trading Console runtime governance panel | integrated | `trading-console/src/pages/Dashboard.tsx` |
| P1-A backend/frontend focused verification | integrated | `tests/unit/test_trading_console_readmodels.py`, `npm run lint`, `npm run build` |

### P1 - Strategy Runtime Integration

Goal: continue from proven CPM/BRF and reference strategy semantics into
bounded live observation.

Work items:

1. Keep CPM/BRF as reference implementations, not proven-alpha claims.
2. Require `RequiredFacts` freshness and trusted account facts before candidate
   planning.
3. Preserve right-tail exit semantics: hard stop, TP1 partial, runner/trailing
   metadata, and no automatic compounding or withdrawal assumption.
4. Route RMR/FCO as classifier or backlog inputs until their data model and
   missing-fact behavior are explicit.

Current 2026-06-13 implementation progress:

| Item | Status | Evidence |
|---|---|---|
| P1-B strategy RequiredFacts readiness guard | integrated | `scripts/build_runtime_strategy_required_facts_readiness_packet.py` |
| P1-B operator contract document | integrated | `docs/ops/runtime-governance-p1-strategy-required-facts-readiness-2026-06-13.md` |
| P1-B focused verification | integrated | `tests/unit/test_runtime_strategy_required_facts_readiness_packet.py` |

### P2 - Archive Hygiene

Goal: reduce future confusion without deleting valuable audit/recovery assets.

Work items:

1. Move legacy first-real-submit packet scripts into a replay / recovery /
   history namespace while preserving compatibility wrappers.
2. Keep compatibility tests for historical packet reproduction.
3. Keep `OwnerBoundedExecutionService` available as a one-shot manual path, not
   as the final runtime architecture.

Current 2026-06-13 implementation progress:

| Item | Status | Evidence |
|---|---|---|
| P2 first-real-submit archive namespace | integrated | `scripts/replay_recovery_history/first_real_submit/` |
| P2 legacy wrapper compatibility | integrated | old `scripts/*first_real_submit*` and rehearsal paths remain as wrappers |
| P2 compatibility map | integrated | `docs/ops/runtime-legacy-submit-compatibility-map-2026-06-13.md` |
| P2 focused verification | integrated | `tests/unit/test_runtime_legacy_compatibility_isolation_packet.py`, `tests/unit/test_runtime_first_real_submit_archive_namespace.py` |

## Development Cadence

Each execution-chain stage should use:

```text
local node test
-> local dry-run packet
-> focused regression
-> Tokyo integration probe when deployment matters
-> stage commit
```

Tokyo is for deployment, integration, live account facts, and explicitly gated
real exchange actions. It is not the first-pass debugging environment for new
domain or application nodes.
