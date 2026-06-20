# Main-Control StrategyGroup Handoff Index

Status: CURRENT_PILOT_SUPPLEMENT
Last updated: 2026-06-20

## Research Sync

Current research handoff source:

```text
branch: codex/strategy-research-20260613-goal
commit: d62ce55727614fcfdb2d12f8fee1d3c226950048
status: reviewed_and_synced_to_main_control_baseline
```

See `docs/current/strategy-group-handoffs/main-control-research-sync.md`.

## Authority Entrypoints

Before interpreting StrategyGroup handoffs, follow:

```text
docs/current/PROJECT_INFORMATION_ARCHITECTURE.md
docs/current/GOAL_MODE_TASK_PACKET_CONTRACT.md
docs/current/strategy-group-handoffs/STRATEGYGROUP_REGISTRY_CONTRACT.md
```

Use the global authority split:

```text
Owner controls policy.
System executes process.
Runtime decides actionability.
Review updates strategy governance.
```

StrategyGroup handoffs and registry rows may support `trial_eligible`, tier
review, and Owner policy decisions. They do not set `actionable_now=true` and
must not turn the Owner into the manual operator of RequiredFacts, fresh signal,
candidate/auth, FinalGate, Operation Layer, replay rows, or no-action rows.

Runtime eligibility tiers are defined in:

```text
docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.md
docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json
```

Strategy asset registry semantics are defined in:

```text
docs/current/strategy-group-handoffs/STRATEGYGROUP_REGISTRY_CONTRACT.md
```

Current StrategyGroup asset baseline rows are generated at:

```text
docs/current/strategy-group-handoffs/strategygroup-registry-baseline.json
docs/current/strategy-group-handoffs/strategygroup-registry-baseline.md
```

Current StrategyGroup tier review rows are generated at:

```text
docs/current/strategy-group-handoffs/strategygroup-tier-review-current.json
docs/current/strategy-group-handoffs/strategygroup-tier-review-current.md
```

Current StrategyGroup quality-governance wave rows are generated at:

```text
docs/current/strategy-group-handoffs/strategygroup-quality-wave-current.json
docs/current/strategy-group-handoffs/strategygroup-quality-wave-current.md
```

Pre-live StrategyGroup decision rows are defined in:

```text
docs/current/STRATEGY_OPPORTUNITY_REVIEW_LEDGER.md
```

## Batch

| StrategyGroup | Role | Default Mode |
| --- | --- | --- |
| `MPG-001` | Momentum persistence | `armed_observation` |
| `TEQ-001` | Equity-like perpetual momentum | `armed_observation` |
| `FBS-001` | Funding / basis stress | `armed_observation` |
| `PMR-001` | Precious-metal overlay | `observe_only` |
| `SOR-001` | Session opening-range structure | `conditional_armed_observation` |

## Expansion Intake

| StrategyGroup | Role | Default Mode | Main-Control Boundary |
| --- | --- | --- | --- |
| `BTPC-001` | Bear trend pullback continuation | `L2 policy: shadow_candidate; handoff: non-executing input` | May support L2 shadow-candidate observation through runtime tier policy only; not L4 real-order scope |
| `VCB-001` | Volatility compression breakout | `L1 policy: observe_only; replay: non-executing review input` | May support L1 no-action / would-enter replay review only; not L2 shadow-candidate or L4 real-order scope |
| `LSR-001` | Liquidity sweep reversal / short-revival rewrite lane | `L1 policy: observe_only; replay: non-executing review input` | May support L1 no-action / would-enter / rewrite-gap replay review only; not L2 shadow-candidate or L4 real-order scope |
| `BRF-001` | Bear rally failure short lane | `L1 policy: observe_only; replay: non-executing review input` | May support L1 no-action / would-enter / squeeze-risk replay review only; not L2 shadow-candidate or L4 real-order scope |

## Boundary

These handoffs are Strategy Picker and watcher-scope inputs only. They are not
order authority, FinalGate pass evidence, Operation Layer evidence, deploy
authority, credential changes, live profile changes, or order-sizing defaults.

High-priority no-action, would-enter, stale, missing-fact, and
classifier-conflict observations from these handoffs should enter the minimal
StrategyGroup Decision Ledger only when they influence keep, revise, promote,
park, kill, go-live, do-not-go-live, or safety-block decisions.
