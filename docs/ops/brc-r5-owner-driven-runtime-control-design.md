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

# BRC-R5 Owner-Driven Runtime Control Design

Date: 2026-05-26
Status: OWNER_CONFIRMED_DESIGN_BASELINE

## Purpose

BRC-R5 aligns the Bounded Risk Campaign System with the Owner's intended
operating model:

```text
Owner intent -> LLM-assisted explanation and risk advice -> action card
-> Owner decision -> simulation/testnet execution or monitor-state change
-> fast cut-off controls -> full audit -> review.
```

The current priority is full-chain usability and auditability, not strategy
profit validation.

## Confirmed Principles

### 1. Single Trading Environment Boundary

Use one top-level execution environment:

```text
TRADING_ENV=simulation | live
```

Semantics:

- `simulation`: local, testnet, mock, and rehearsal. This is the default.
- `live`: real account, mainnet, and real funds. This is modeled now but not
  enabled by default.

The system should not maintain separate product flows for testnet and future
live. It should use the same control chain and change only the environment,
credentials, confirmation strength, and deployment gates.

For v0 UI, `live` is shown as a disabled modeled boundary, not as a normal
switch.

### 2. No Paper Mainline

Paper mode is not a BRC operating mainline. It may exist later as an isolated
research/backtest tool, but the current BRC route should not require paper
before testnet.

The executable validation path is:

```text
simulation/testnet first -> future live with the same chain.
```

### 3. Owner-Facing Runtime State

The primary UI and API language should focus on what the Owner actually needs:

- current strategy family / playbook;
- current capital bucket and risk state;
- environment boundary state;
- observe vs monitor vs testnet rehearsal;
- current positions and orders;
- latest operation and audit status;
- whether fast cut-off controls are available.

Low-level runtime fields such as profile, startup guard, and GKS remain
developer detail unless they directly explain a blocked action.

The runtime control state vocabulary is:

| State | Meaning |
| --- | --- |
| `observe` | No trading; Owner/system only observes state. |
| `monitor` | A playbook or strategy family is being monitored; no order authority. |
| `testnet_rehearsal` | Controlled rehearsal can execute only in simulation/testnet after preflight and Owner confirmation. |
| `paused` | New entries are paused; existing exposure may still need management. |
| `stopped` | Runtime-driven activity is stopped. |
| `flattening` | Cancel/close flow is in progress. |
| `attention_required` | System cannot prove safe final state; state changes are blocked except stop, flatten, and read-only diagnostics. |

Do not expose bare `trade` in v0. Future live readiness may introduce
`live_trade` after a separate Owner production/deployment authorization.

### 4. Testnet Should Be Open Enough To Expose Problems

Testnet is the current engineering validation path. It should not be blocked by
production-grade approval friction.

The minimal hard gates for testnet/simulation are:

1. `TRADING_ENV=simulation`.
2. The system can prove it is not connected to production/mainnet for the
   requested action.
3. Audit persistence is writable.
4. Fast cut-off controls are available for the action type.
5. Final position/order state can be observed after the workflow.

Other concerns such as weak strategy evidence, frequent switching, recent
losses, or risky market conditions should generally be warnings, not hard
blocks, during simulation/testnet.

### 5. Production Is Modeled, But Default-Off

Live trading is not a separate future rewrite. It is a modeled execution
environment with default-off authority:

```text
TRADING_ENV=simulation
```

Switching to `TRADING_ENV=live` is a separate future Owner decision and
deployment/security task. BRC-R5 does not authorize live trading, mainnet order
placement, withdrawal/transfer, autonomous strategy execution, or automatic
sizing.

### 6. LLM Role

The LLM is not only an intent classifier. It is an:

```text
Owner assistant + risk advisor + audit investigator.
```

Allowed:

- read current system status;
- query campaign/order/audit evidence through controlled read-only tools;
- explain what happened and why;
- normalize Owner intent;
- propose an action card;
- provide risk advice.

Forbidden:

- write database rows directly;
- modify runtime state directly;
- place, close, resize, or cancel orders directly;
- confirm on behalf of Owner;
- bypass audit persistence;
- bypass `TRADING_ENV`.

LLM risk advice is advisory by default and does not have blocking authority.

### 7. LLM Risk Advice Dimensions

The first version should produce risk advice across these dimensions:

| Dimension | Meaning |
| --- | --- |
| Account risk | Bucket, loss lock, budget, and loss spillover. |
| Position risk | Existing positions, open orders, duplicate exposure. |
| Execution risk | Testnet/live environment, residual orders, fills, close failure, state sync. |
| Strategy risk | Playbook status, applicability boundary, weak evidence, switching frequency. |
| Market risk | Trend/range uncertainty, volatility, event risk. |
| Behavioral risk | Loss-chasing, profit overconfidence, narrative switching. |
| System risk | Runtime health, exchange connectivity, audit availability, emergency controls. |

### 8. Action Card Is Weak Control, Not An Approval Wall

The proposal object should be an Owner-readable action explanation, not a
production-style approval wall.

It should answer:

- what the Owner asked for;
- what the system understood;
- what will change;
- what will not change;
- which risks the LLM sees;
- which gates are hard blocks;
- which warnings are advisory;
- what the Owner can do next.

Hard blocks are reserved for environment/safety impossibilities, such as:

- requested live action while `TRADING_ENV=simulation`;
- production/mainnet ambiguity;
- withdrawal/transfer request;
- LLM trying to write or trade directly;
- audit persistence unavailable for a state-changing action.

### 9. Fast Cut-Off Is First-Class

Owner must be able to quickly cut risk or stop runtime behavior.

Required controls:

| Control | Meaning |
| --- | --- |
| `pause_new_entries` | Stop opening new positions; do not necessarily close existing exposure. |
| `emergency_stop_runtime` | Stop runtime-driven activity. |
| `emergency_flatten` | Cancel open orders and attempt to close exposure in the current `TRADING_ENV`. |

These controls use the same capability model in simulation and live. The
difference is the active `TRADING_ENV` and the strength/clarity of the
confirmation copy.

### 10. Audit Failure Is A Hard Block

Any action that changes system state must be auditable. If the audit write
cannot be persisted, the action must not execute.

This is a hard requirement because BRC depends on full-chain traceability,
explainability, and review.

## Strategy Carrier For R5

Strategy research is not the current priority. R5 should use an existing trend
strategy as a carrier to validate the full chain.

Carrier:

```text
StrategyFamily: Trend Following
Playbook: TF-001
Purpose: carrier validation, not alpha validation
Initial path: monitor -> simulation/testnet rehearsal
```

Do not use R5 to optimize trend parameters, prove profitability, build a
strategy pool, or implement automatic multi-strategy routing.

## Target R5 Chain

```text
Owner text
-> LLM reads status and strategy/playbook registry
-> LLM returns intent + advisory risk advice
-> Action card is created
-> Owner confirms or cancels
-> system enters monitor or simulation/testnet rehearsal path
-> Owner can pause / stop / flatten
-> audit trace is written
-> evidence packet supports review
```

## First Implementation Slice Recommendation

`BRC-R5-001 Trend Playbook Carrier Full-Chain Validation`

Goal:

```text
Use TF-001 as the simplest playbook carrier to validate Owner text, LLM risk
advice, action cards, monitor state, simulation/testnet execution, fast cut-off
controls, audit trace, and review.
```

Non-goals:

- no new strategy research;
- no parameter optimization;
- no strategy pool execution;
- no autonomous live trading;
- no withdrawal/transfer;
- no paper mainline.

## Open Future Work

- Feishu approval and card-based remote control.
- Cloud deployment hardening.
- Secret-manager integration.
- Strategy family registry persistence and query tooling.
- Live deployment gates for `TRADING_ENV=live`.
