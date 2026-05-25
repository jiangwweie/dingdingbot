# ADR-0008 Personal Leveraged Campaign Business Chain

## Status

Accepted

Date: 2026-05-25

Runtime effect: none

Trading permission effect: none

Superseded boundary note: ADR-0009 clarifies that non-real-live runtime,
paper, testnet, tiny-live-style, and exchange-connected work may proceed after
reasonable scoped verification and explicit Owner authorization for the
specific action. Real live trading remains separately prohibited.

## Context

The Owner's current target is a personal small-capital derivatives campaign:
use bounded risk capital, controlled leverage, strategy support, and human
final authority. Profit protection is part of campaign control, but actual
withdrawals are handled manually by the Owner outside the system. The target is
not a fully automatic strategy at this stage.

Recent research showed that manual review sheets and LLM summaries can help
surface opportunity structure, but they cannot carry real trading behavior by
themselves. A tradable workflow still needs a deterministic strategy carrier
that can convert a qualified market state into a bounded trade intent.

The Owner also clarified that risk control should be handled with order
construction and position lifecycle control, not only as a pre-decision filter.

## Decision

The accepted Owner-facing mainline is:

`Data Ingestion -> Market State / Feature Builder -> Strategy Detector -> Mode Router -> Human Arm Gate -> Strategy Contract -> Trade Intent -> Risk-Aware Order Builder -> Execution + Order Lifecycle -> Position / Campaign / Profit Protection Control`

The system roles are:

- LLM: explain, summarize, challenge, and audit. It must not decide buy, sell,
  short, size, or leverage.
- Human gate: arm or pause a bounded strategy mode/session. It should not be a
  per-order click path in the target operating model.
- Strategy contract: carry deterministic trading rules and emit a structured
  trade intent only when its conditions are satisfied.
- Risk-aware order builder: evaluate every trade intent at order construction
  time and either reject, resize, or build a bounded order plan according to
  Owner-fixed risk rules.
- Order lifecycle: protect, reconcile, and audit actual order and position
  state.
- Campaign control: pause, hard-lock, restart, and profit-protection state
  according to campaign rules. It must not create withdrawal instructions.

The simplified gate structure is:

1. Campaign/account hard rules.
2. Human arm gate for strategy mode/session.
3. Order-level, position-level, and campaign-level risk checks in the execution
   path.

## Consequences

- Human-review tables are subordinate research and review aids, not the
  business mainline.
- Future design work should first define `StrategyContract`, `TradeIntent`,
  `RiskOrderPlan`, `PositionLifecycleState`, and `CampaignState` schemas before
  any runtime connection.
- `SQ02_DOWNSIDE_CONT_V0` may be used as the first strategy-contract skeleton
  candidate because it currently has the strongest semi-auto research thread.
  It remains disconnected from runtime, paper, testnet, tiny-live-style,
  account, leverage, and real order paths until a separate ADR-0009 action gate
  approves the specific non-real-live step.
- Risk control belongs in the order-building and lifecycle boundary. Front-gate
  filters may reduce bad contexts, but they are not sufficient as risk control.
- Profit protection is part of the campaign lifecycle. Withdrawal itself is an
  Owner-external manual action and is not a system object, LLM suggestion, or
  strategy signal.

## Execution Boundary

This ADR does not by itself authorize a specific runtime, paper/testnet,
exchange-connected, or account-action execution. Those steps may be requested
after scoped verification and require explicit Owner authorization under
ADR-0009.

This ADR does not authorize real live trading, live real-account order
placement, live order modification/cancellation, transfer, withdrawal,
real-funds deployment, LLM/agent autonomous buy/sell/short/size/leverage
decisions, or withdrawal automation.
