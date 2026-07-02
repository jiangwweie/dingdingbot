# BRC Current Documentation

Status: CURRENT_DOC_ENTRY
Last updated: 2026-06-15

## Start Here

Current documentation is intentionally small. Agents and workers must start
from these files:

```text
docs/current/OWNER_RUNTIME_OPERATING_MODEL.md
docs/current/AI_AGENT_CONSTRAINTS.md
docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md
docs/current/strategy-group-handoffs/main-control-handoff-index.md
```

## Current Meaning

The project is a StrategyGroup runtime-governance pilot:

```text
Owner selects a StrategyGroup
-> system admits or rejects it with clear reasons
-> watcher observes the market
-> fresh signal prepares candidate evidence
-> action-time FinalGate runs
-> official Operation Layer is the only real order path
-> post-submit finalize, reconciliation, budget settlement, and review close the loop
```

The Owner should not operate the system by reading raw evidence packets.
Evidence packets are audit and recovery material under the Owner-facing
Strategy Control Board.

## Kept Current Docs

| Path | Role |
| --- | --- |
| `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md` | Owner workflow and standing authorization |
| `docs/current/AI_AGENT_CONSTRAINTS.md` | Agent execution constraints and confirmation minimization |
| `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md` | Owner-facing state and notification contract |
| `docs/current/strategy-group-handoffs/` | Current StrategyGroup handoff packs and main-control intake |
| `docs/schemas/` | Schema contracts still exercised by tests |

## Historical Archive

Older docs were compressed into:

```text
docs/history-archive-2026-06-15-pre-governance.tar.gz
```

The archive is recovery material only. It must not be used as current
instructions, current product truth, or a source of new Owner-confirmation
blockers.

## Removed From Current Authority

The following historical documentation namespaces were removed from the active
tree after compression:

```text
docs/adr
docs/archive
docs/audit
docs/canon
docs/gpt
docs/ops
docs/product
```

Those paths may still appear in legacy code evidence references or older tests.
Such references are provenance strings, not current operating instructions.
