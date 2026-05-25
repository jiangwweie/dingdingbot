# Personal Leveraged Campaign Mainline v0

Last updated: 2026-05-25

Status: Accepted business mainline / staged execution gate / amended by Playbook Governance R0

Runtime effect: none

Trading permission effect: none

## Purpose

This document fixes the current Owner-facing business direction:

Use small, loss-bounded risk capital for a human-armed, strategy-carried,
risk-controlled derivatives campaign, with explicit pause and profit-protection
mechanics. Withdrawals are Owner-external and are not a system responsibility.

This is not a promise of profit and not live readiness. It is the mainline
architecture target that future research, schemas, local sandbox work, and
authorized non-real-live runtime/testnet work should align to.

## Owner Objective

The intended operating shape is:

- the system detects and explains when a strategy mode may be worth arming;
- Playbook Governance constrains whether the Owner may remain in, switch,
  pause, or review an operating playbook;
- the Owner decides whether to arm, pause, or ignore that mode;
- a deterministic strategy contract carries the actual entry/exit logic inside
  the armed window;
- risk is enforced at order construction, position lifecycle, and campaign
  lifecycle boundaries;
- profit protection can mark reduce/close or pause requirements, while actual
  withdrawals are handled manually by the Owner outside the system.

## Complete Business Chain

| Layer | Responsibility | Output | Must not output |
|---|---|---|---|
| 1. Data Ingestion | Collect allowed market and account-state inputs for the current stage. | Timestamped raw inputs. | Trading decisions. |
| 2. Market State / Feature Builder | Convert raw inputs into reproducible features and state labels. | Feature snapshot. | Buy/sell/short/size/leverage decisions. |
| 3. Strategy Detector | Detect that a known strategy setup may be present. | Candidate setup packet. | Order instructions. |
| 4. Mode Router | Decide which mode deserves Owner attention. | Mode advice. | Mandatory action. |
| 5. Playbook Governance | Govern whether a playbook can be kept, switched, paused, or reviewed. | Playbook registry state, switch decision log, cooldown/hard-lock result. | Trade intent, order instruction, or hidden discretionary automation. |
| 6. Human Arm Gate | Owner arms, pauses, or rejects a bounded mode/session after governance checks. | Human arm decision. | Per-order discretionary overrides hidden as automation. |
| 7. Strategy Contract | Deterministically apply strategy rules inside the armed mode/session. | Trade intent. | Risk-ignored order plans. |
| 8. Trade Intent | Express desired direction/action without exchange side effects. | Structured intent. | Real exchange order. |
| 9. Risk-Aware Order Builder | Check every intent against order, position, and campaign rules. | Reject, resize, or risk order plan. | Unbounded order. |
| 10. Execution + Order Lifecycle | Place, protect, reconcile, and audit orders only in authorized future modes. | Execution receipt and lifecycle state. | Silent or unprotected exposure. |
| 11. Position / Campaign / Profit Protection Control | Manage pause, hard lock, restart, and profit protection. | Campaign state and lifecycle requirements. | Withdrawal instructions or automatic withdrawal behavior. |

## Core Objects

`ModeAdvice`

- why this mode is being surfaced;
- which strategy contract it maps to;
- evidence and caveats;
- default action: observe, arm, pause, or ignore.

`HumanArmDecision`

- Owner decision;
- armed strategy id;
- allowed session window;
- allowed campaign id;
- explicit expiry;
- audit provenance.

`PlaybookContract`

- playbook id and current evidence state;
- operating posture such as observe-only, paper-only, docs-only, or governed
  manual;
- minimum hold and cooldown rules;
- switching conditions and forbidden behaviors;
- associated Strategy Contract id when one exists;
- explicit no-runtime/no-order authority unless separately authorized.

`PlaybookSwitchDecision`

- previous and new playbook ids;
- reason category and required reason text;
- campaign PnL and CPV0_2 state at switch time;
- cooldown and minimum-hold status;
- evidence references;
- risk change direction;
- override provenance when an override is allowed.

`StrategyContract`

- setup conditions;
- invalidation conditions;
- entry intent rules;
- exit intent rules;
- required feature snapshot;
- forbidden data and lookahead rules;
- disabled-by-default runtime label.

`TradeIntent`

- strategy id;
- direction class;
- entry/exit action class;
- trigger reason;
- invalidation reason;
- confidence/evidence text when useful;
- no exchange side effect.

`RiskOrderPlan`

- allow/reject decision;
- risk-rule reasons;
- owner-fixed caps used by the builder;
- planned order structure in a future authorized mode;
- protection requirements;
- rollback and cancellation behavior.

`ExecutionReceipt`

- order ids and exchange acknowledgements in future authorized modes;
- reconciliation references;
- protection status;
- lifecycle status.

`PositionLifecycleState`

- position source of truth;
- protection state;
- reduce/close requirements;
- stale or inconsistent state handling.

`CampaignState`

- capital bucket;
- loss lock;
- profit protection;
- pause and restart state;
- rule version;
- invariant checks.

Withdrawal is explicitly outside the system. The Owner may withdraw manually
based on personal judgment; the system must not generate withdrawal objects,
amounts, schedules, or automation.

## Stage Map

| Stage | Name | Allowed output | Requires Owner confirmation before next stage |
|---|---|---|---|
| 0 | No-order review | Packets, reports, readable review cards. | Promotion to any strategy-contract work that touches runtime. |
| 1 | Playbook Governance R0 | Playbook registry, switch decision log, cooldown/hard-lock rules, CPV0_2 continuity rules. | Any Strategy Contract promotion, runtime wiring, or execution-path use. |
| 2 | Strategy contract skeleton | Docs-only schemas and deterministic contract draft. | Runtime wiring or execution-path use. |
| 3 | Simulated risk order plan | Local sandbox intent-to-plan simulation with no exchange access. | Any exchange, paper, testnet, or real account connection. |
| 4 | Demo portfolio execution | Local demo receipts and lifecycle replay only. | External account or exchange connection. |
| 5 | Read-only exchange sync | Read-only account-state sync after explicit key handling approval. | Any trading permission. |
| 6 | Paper/testnet | Explicit paper/testnet account mode after scoped verification and Owner authorization. | Real trading permission or real live order path. |
| 7 | Tiny-live-style rehearsal | Explicitly authorized non-real-live rehearsal only unless separately upgraded. | Any real-funds activation or expansion in risk, asset, strategy, or withdrawal-related automation. |

## Immediate Mainline

The next docs/design target is:

`Playbook Governance R0`

Reason:

- no current strategy is runtime-eligible;
- the immediate risk is ungoverned human switching between observe-only,
  fragile, parked, or discretionary playbooks;
- playbook switching must not reset CPV0_2 campaign loss/protection state;
- post-loss switching, post-profit risk escalation, and narrative chasing need
  explicit decision logs, cooldowns, and hard-lock rules before further
  Strategy Contract/runtime work.

The next strategy-contract skeleton remains preserved but is no longer the
immediate planning priority:

`SQ02_DOWNSIDE_CONT_V0` as a docs-only `StrategyContract` skeleton.

Reason:

- it is the strongest current semi-auto research line after the May 24-25
  synthesis;
- it already has public-universe retest evidence, no-order packets, event-time
  priority logic, and readability audit artifacts;
- it is suitable for defining a contract boundary without claiming live
  readiness.

This does not automatically promote SQ02 to scanner, alert, watchlist, runtime,
paper, testnet, tiny-live-style, live, position, leverage, or real order use.
Any non-real-live promotion must use the ADR-0009 action gate.

## Next Safe Artifacts

Future work should prefer these design artifacts before implementation:

- `strategy_contract.schema.yaml`
- `trade_intent.schema.json`
- `risk_order_plan.schema.json`
- `campaign_state.schema.json`
- `order_lifecycle_state_machine.md`
- `human_arm_gate.md`
- `forbidden_live_actions.md`

## Execution Boundary

This document does not by itself authorize a specific runtime, paper/testnet,
exchange-connected, or account-action execution. Those steps may be requested
after scoped verification and require explicit Owner authorization under
ADR-0009.

This document does not authorize real live trading, live real-account order
placement, live order cancellation, transfer, withdrawal, real-funds
deployment, LLM/agent autonomous buy/sell/short/size/leverage decisions, or
withdrawal automation.
