# ADR-0008 Personal Leveraged Campaign Business Chain

## Status

Accepted

Date: 2026-05-25

Runtime effect: none

Trading permission effect: none

## Context

The Owner's current target is a personal small-capital derivatives campaign:
use bounded risk capital, controlled leverage, strategy support, human final
authority, and scheduled or conditional profit withdrawal. The target is not a
fully automatic strategy at this stage.

Recent research showed that manual review sheets and LLM summaries can help
surface opportunity structure, but they cannot carry real trading behavior by
themselves. A tradable workflow still needs a deterministic strategy carrier
that can convert a qualified market state into a bounded trade intent.

The Owner also clarified that risk control should be handled with order
construction and position lifecycle control, not only as a pre-decision filter.

## Decision

The accepted Owner-facing mainline is:

`Data Ingestion -> Market State / Feature Builder -> Strategy Detector -> Mode Router -> Human Arm Gate -> Strategy Contract -> Trade Intent -> Risk-Aware Order Builder -> Execution + Order Lifecycle -> Position / Campaign / Withdrawal Control`

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
- Campaign control: pause, hard-lock, restart, and create withdrawal
  instructions according to campaign rules.

The simplified gate structure is:

1. Campaign/account hard rules.
2. Human arm gate for strategy mode/session.
3. Order-level, position-level, and campaign-level risk checks in the execution
   path.

## Consequences

- Human-review tables are subordinate research and review aids, not the
  business mainline.
- Future design work should first define `StrategyContract`, `TradeIntent`,
  `RiskOrderPlan`, `PositionLifecycleState`, `CampaignState`, and
  `WithdrawalInstruction` schemas before any runtime connection.
- `SQ02_DOWNSIDE_CONT_V0` may be used as the first docs-only strategy-contract
  skeleton candidate because it currently has the strongest semi-auto research
  thread, but it remains disconnected from runtime, paper, testnet, tiny-live,
  live, account, leverage, and real order paths.
- Risk control belongs in the order-building and lifecycle boundary. Front-gate
  filters may reduce bad contexts, but they are not sufficient as risk control.
- Profit withdrawal is part of the campaign lifecycle, not an LLM suggestion and
  not a strategy signal.

## Non-Authorization

This ADR does not authorize real API keys, real exchange account access,
paper/testnet/live/tiny-live trading, order placement, order modification,
order cancellation, transfer, withdrawal, deployment connected to a real
account, runtime profile changes, strategy implementation in the real order
path, leverage advice, or position-sizing advice.
