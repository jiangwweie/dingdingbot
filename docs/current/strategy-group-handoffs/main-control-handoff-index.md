---
title: STRATEGYGROUP_FILE_SOURCE_RETIREMENT_INDEX
status: CURRENT_GOVERNANCE_INDEX
authority: docs/current/strategy-group-handoffs/main-control-handoff-index.md
last_verified: 2026-07-12
---

# StrategyGroup File-Source Retirement Index

Status: CURRENT_GOVERNANCE_INDEX
Last updated: 2026-07-12

## Current Rule

`docs/current/strategy-group-handoffs/` is no longer a StrategyGroup runtime
input directory.

Current StrategyGroup scope, side, event, policy, RequiredFacts, runtime
binding, and live-submit eligibility must come from PG current state:

```text
brc_strategy_groups
brc_strategy_group_versions
brc_strategy_side_event_specs
brc_strategy_group_candidate_scope
brc_candidate_scope_event_bindings
brc_owner_policy_current
brc_runtime_scope_bindings
brc_runtime_fact_snapshots
brc_pretrade_readiness_rows
brc_control_read_model_snapshots_current
brc_goal_status_current
```

## Remaining Current Document

| File | Role | Runtime authority |
| --- | --- | --- |
| `STRATEGYGROUP_REGISTRY_CONTRACT.md` | Explains StrategyGroup registry semantics and the active PG seed contract | None |

## Retired File Families

The following file families were removed from `docs/current` as current inputs:

| Retired family | Current replacement |
| --- | --- |
| `*/handoff.json` | PG StrategyGroup version, event spec, candidate scope, policy, and runtime scope rows |
| `*/replay/*.json` | Research/archive provenance or explicit test fixtures only |
| `main-control-runtime-tier-policy.json` | PG owner policy current projection |
| `owner-pretrade-runtime-authorization-v0.json` | PG owner policy and runtime scope bindings |
| `research-intake-snapshots/*.json` | Strategy governance DB admission data or archive provenance |
| `main-control-*.md` supplement files | Current contracts plus PG current projection; no runtime file input |

## Boundary

Old handoff/replay/policy files must not be used by production code, Owner
read models, watcher scope selection, Tradeability, Candidate Pool, action-time
ticketing, FinalGate preparation, Operation Layer preparation, or server
monitoring.

Historical review may use git history or archive-only provenance. Historical
material must not be wired back into current runtime decisions.

The deployed **P1-TFC Trade Feedback Core Consolidation** baseline consumes only
PG Ticket/lifecycle current rows and typed in-memory decisions. The active
**P1-OFC Opportunity Feedback Calibration** program reuses PG Event Spec
identity and the production evaluator through typed in-memory observations.
Neither program revives StrategyGroup handoff files, replay JSON, or Markdown
as signal, Ticket, recovery, or Owner-state authority.
