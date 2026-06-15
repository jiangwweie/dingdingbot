# BRC StrategyGroup Runtime Governance

Status: CURRENT_ENTRY
Last updated: 2026-06-15

## Current Meaning

This repository is the BRC StrategyGroup runtime-governance pilot.

```text
Owner selects a StrategyGroup
-> system admits or rejects it with clear reasons
-> watcher observes the market
-> fresh signal prepares candidate evidence
-> action-time FinalGate runs
-> official Operation Layer is the only real order path
-> post-submit finalize, reconciliation, budget settlement, and review close the loop
```

The system is not a raw evidence-packet workflow. The Owner-facing product
surface is the Strategy Control Board.

## Start Here

```text
AGENTS.md
docs/README.md
docs/current/OWNER_RUNTIME_OPERATING_MODEL.md
docs/current/AI_AGENT_CONSTRAINTS.md
docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md
docs/current/strategy-group-handoffs/main-control-handoff-index.md
```

## Historical Docs

Historical docs were compressed into:

```text
docs/history-archive-2026-06-15-pre-governance.tar.gz
```

They are recovery material only. They must not be used as current product truth
or as a source of new Owner-confirmation blockers.

## Development Quick Start

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Local backend:

```bash
python src/main.py
```

Frontend:

```bash
cd gemimi-web-front
npm run dev
```

## Safety Boundary

Real order actions are allowed only through:

```text
fresh signal
-> RequiredFacts readiness
-> candidate / authorization evidence
-> action-time FinalGate
-> official Operation Layer
-> post-submit finalize / reconciliation / budget settlement
```

Never bypass FinalGate or Operation Layer. Never create withdrawal or transfer
actions. Never mutate secrets, credentials, live profile, or order-sizing
defaults without a separate explicit task.
