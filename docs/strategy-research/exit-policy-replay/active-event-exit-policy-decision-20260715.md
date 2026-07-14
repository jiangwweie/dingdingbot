# Active Event Exit Policy Decision — 2026-07-15

Status: **OWNER-DELEGATED RECOMMENDATION RECORDED**

Research authority: **research-only evidence; no runtime or exchange authority**

Replay code commit: **`9d93f09f`**

Deterministic replay decision hash: **`a2229fbfacf3ee76017ca1cf58bbcd009bfe0fdd80d8e501851ee699f1084b8c`**

## Owner Decision Record

The Owner explicitly delegated exact parameter selection to Codex and stated
that the recommended values should be written without another confirmation
round. This record satisfies the Release C decision gate for the exact values
below. It does not authorize a deployment that conflicts with an active real
position, open order, unknown exchange outcome, missing protection, or another
action-time safety fact.

Only **future Tickets** may bind these policies. Historical Tickets remain
`legacy_unbound`; no historical exit meaning may be synthesized.

## Known Facts

1. The current release-aligned research review has only **three terminal SOR
   outcomes**. That sample is insufficient for profit optimization or stable
   parameter inference. Source:
   `docs/strategy-research/strategygroup-release-rereview-20260714.md`.
2. Historical SOR research preserves a **72h short-branch exit horizon**.
   Source: `docs/strategy-research/sor-branch-eligibility-time-stop-20260616.md`.
3. Historical MPG research distinguishes a **12h default tradeoff lane** from a
   **72h revival lane**. Source:
   `docs/strategy-research/mpg-member-drawdown-disable-addendum-20260616.md`.
4. The MI handoff records an **8h** time stop, and the BRF2 handoff records a
   **6h** time stop. Sources:
   `research/strategy-candidate-mining-replay-validation/packs/MI-ASIA-RS-IMPULSE-001-handoff-draft.json`
   and
   `research/strategy-candidate-mining-replay-validation/packs/BRF2-QUALITY-BASKET-SHORT-001-handoff-draft.json`.
5. The deterministic path suite validates mechanics, ordering, costs,
   long/short symmetry, and sensitivity only. It is **not historical market-path
   evidence** and is not used as a profitability claim.

## Shared Exact Contract

- **TP1 target:** `1R` from actual entry average fill.
- **TP1 fraction:** `50%` of actual filled quantity.
- **TP1 execution:** `LIMIT_GTC`; market fallback is forbidden.
- **TP1 completion tolerance:** `1` quantity step.
- **Runner floor trigger:** complete TP1 target quantity.
- **Runner floor:** runner-leg cost-adjusted break-even using allocated entry
  fee, certified conservative taker exit fee, and **2 price ticks** of slippage.
- **Minimum stop improvement:** **2 price ticks**.
- **Hard TP2:** none. The remainder is a right-tail runner.
- **Market fact:** final closed candle only.
- **Replacement ordering:** place and confirm the new reduce-only stop before
  canceling the exact PG-linked prior stop.

## Exact Event-Spec Parameters

| StrategyGroup / Event Spec | Side | Evaluation | Structural rule | ATR | Time stop | Native invalidation | Policy hash |
| --- | --- | --- | --- | --- | ---: | --- | --- |
| **CPM-RO-001 / CPM-LONG v2** | long | **1h** | confirmed higher low, **3 bars** | ATR(14) × **0.50** | **24 bars / 24h** | close at/below `reclaim_level` | `25d9ee7a5a30c69ec29aafda9bc1ac50ac5c95fc864bc70228489d857b3a44ee` |
| **MPG-001 / MPG-LONG v2** | long | **1h** | confirmed higher low, **3 bars** | ATR(14) × **0.75** | **12 bars / 12h** | close at/below `momentum_persistence_base` | `647e0701b218cc9f64cd6c1340212838d484a3f209993cd23f4078b56b6f79cc` |
| **MI-001 / MI-LONG v2** | long | **1h** | confirmed higher low, **2 bars** | ATR(14) × **0.50** | **8 bars / 8h** | close at/below `impulse_base` | `7d473c6006bb2a07bd37fae67719f3f591c74fd7c2abab4717300579713a9d8a` |
| **SOR-001 / SOR-LONG v2** | long | **15m** | confirmed higher low, **4 bars** | ATR(14) × **0.50** | **96 bars / 24h** | close at/below `opening_range_high` | `324b2be50b3e1f020837e0f4687e76339a52dd757b272d4336b20de196bef02b` |
| **SOR-001 / SOR-SHORT v2** | short | **15m** | confirmed lower high, **4 bars** | ATR(14) × **0.50** | **288 bars / 72h** | close at/above `opening_range_low` | `c5239928202095ace77c097c43c11281ad7de7896e9d505c4947688757f045e0` |
| **BRF2-001 / BRF2-SHORT v2** | short | **1h** | confirmed lower high, **3 bars** | ATR(14) × **0.75** | **6 bars / 6h** | close at/above `rebound_high` | `5d22e8c70d0f2fac45598e7249a74056fb0f945aed2e6387a97bc5af63ab3d75` |

All six policy versions are **`2026-07-15-v1`** and use the exact strategy/event
registry identities ending in `v2`.

## Analysis And Selection Rationale

### Shared 1R / 50% TP1

The shared first leg realizes one full initial risk unit on half of the actual
fill, while keeping half available for the right tail. It is a reasonable first
canary contract because it is easy to reconcile, does not require a second hard
target, and makes the runner-floor transition observable. It is not asserted to
be the globally optimal profit target.

### Strategy-Specific Horizons

- **MPG 12h**, **MI 8h**, and **BRF2 6h** preserve existing documented semantic
  horizons instead of inventing one universal timeout.
- **SOR-SHORT 72h** preserves the historical short-branch right-tail horizon.
- **SOR-LONG 24h** is intentionally shorter because a failed long opening-range
  continuation should not occupy the single capital slot for the full short
  branch horizon without evidence.
- **CPM 24h** gives the reclaim continuation one daily cycle while allowing
  invalidation and structure to terminate earlier.

### Sensitivity Boundary

The deterministic suite reruns each recommendation with:

- structure window **minus/plus 1 bar**;
- ATR buffer **minus/plus 0.25 ATR**;
- the same conservative fee, slippage, ambiguity, and no-look-ahead rules.

The representative paths do not discriminate stable economic rankings between
the three variants. Therefore the middle recommendation is selected as a
semantic canary, not as an optimized backtest winner. Any future parameter
change requires materially larger historical/live outcome evidence and a new
version/hash.

## Rejected Alternatives

1. **TP1 market order:** rejected because it discards passive limit opportunity
   and increases fee/slippage uncertainty.
2. **Mandatory GTX TP1:** rejected for the first canary because venue capability
   and post-only rejection handling would add a second rollout variable. GTX
   remains an optional later policy version; it never falls back to market.
3. **Hard TP2:** rejected because it caps the system's right-tail objective.
4. **One universal trail/time stop:** rejected because MPG, MI, SOR, CPM, and
   BRF2 have different event horizons and invalidation semantics.
5. **Immediate intrabar structural trail:** rejected because it introduces
   look-ahead and unstable order churn. Only final closed-candle facts may move
   the runner after the immediate TP1 cost floor.

## First Canary And Rollback

The recommended first canary is **`SOR-001 / SOR-LONG v2`**, policy hash
**`324b2be50b3e1f020837e0f4687e76339a52dd757b272d4336b20de196bef02b`**.
It is the closest continuation of the system's existing natural live evidence
and exercises TP1, runner floor, 15m monitoring, invalidation, and time stop
without expanding symbol, side, leverage, notional, capital, or runtime-profile
authority.

Rollback is forward-safe:

1. disable new Ticket binding for this policy version;
2. keep an already active Ticket's frozen policy and exchange-native stop;
3. reconcile exact durable command outcomes;
4. forward-fix the lifecycle;
5. never cancel protection merely to change releases.

## Authority Boundary

```json
{
  "research_only": true,
  "historical_market_path_replay": false,
  "runtime_registry_mutation": false,
  "finalgate_input": false,
  "operation_layer_input": false,
  "exchange_write": false,
  "real_order_authority": false,
  "future_ticket_only": true
}
```
