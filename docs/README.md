# BRC Current Documentation

Status: current Trading Kernel authority index

## Current Authority Set

| Document | Responsibility |
| --- | --- |
| `docs/current/PROJECT_INFORMATION_ARCHITECTURE.md` | Source classes, authority order, and document fact ownership |
| `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md` | Owner policy and supervision boundary |
| `docs/current/AI_AGENT_CONSTRAINTS.md` | Agent implementation and safety constraints |
| `docs/current/P0_TRADING_KERNEL_REBUILD_DESIGN.md` | Approved target architecture and invariants |
| `docs/current/P0_TRADING_KERNEL_REBUILD_IMPLEMENTATION_PLAN.md` | Implementation stages and acceptance checklist |
| `docs/current/TRADING_KERNEL_OPERABILITY_REPAIR_DESIGN.md` | Active repair architecture, defect closure, and pending Owner decisions |
| `docs/current/TRADING_KERNEL_OPERABILITY_REPAIR_TEST_SPEC.md` | Production-shaped local verification and Tokyo readonly acceptance |
| `docs/current/TRADING_KERNEL_OPERABILITY_REPAIR_EXECUTION_PLAN.md` | Ordered task cards, clean-rebuild procedure, and phase-aware recovery |
| `docs/current/MAIN_CONTROL_ROADMAP.md` | Sole current production identity, measured state, and critical path |
| `docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md` | Regular release, recovery, and resource contract |
| `docs/current/RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md` | Product objective, experiment-capital premise, and order-capable profile |
| `docs/current/strategy-group-handoffs/STRATEGYGROUP_REGISTRY_CONTRACT.md` | Active StrategyGroup and event semantics |
| `docs/current/STRATEGY_EXPERIMENT_EVALUATION_CONTRACT.md` | Strategy experiment evaluation |
| `docs/current/STRATEGY_ENGINEERING_INTAKE_CONTRACT.md` | Strategy-to-kernel intake boundary |
| `docs/current/TRADEABILITY_DECISION_CONTRACT.md` | Current can-trade decision |
| `docs/current/BLOCKER_CLASSIFICATION_CONTRACT.md` | Exact blocker vocabulary |

Only these files may exist under `docs/current`. Historical documents are not
current instructions and must not be wired into production runtime decisions.

Volatile production facts belong only in `MAIN_CONTROL_ROADMAP.md`. Entry,
architecture, implementation, and deployment documents link to that snapshot
instead of copying its commit, tag, certification count, Ticket identity, or
transient stage.

The P0 rebuild documents own the completed baseline and unchanged kernel
invariants. The three operability-repair documents own the active target,
verification, and execution sequence for the identified scheduling,
certification, promotion, deployment, and capacity defects. Until that repair
is implemented and certified, current tracked code and direct runtime facts
remain higher authority than the target design.
