# Wave 2 PG Comparative Strength And MPG/MI Certification Design

## Objective

Build one PG-backed comparative-strength capability, certify `MPG-LONG v2`,
then reuse the same capability to certify `MI-LONG v2` without waiting for a
market signal from CPM.

## Authority And Source Model

```text
PG active candidate scopes
-> bounded closed-1h candle fetch for the union of MPG/MI symbols
-> aligned Decimal return/rank computation
-> PG strategy_comparative fact snapshots
-> runtime signal input reads PG fact snapshot
-> event-specific evaluator emits typed fact observations
-> versioned Event Spec authority caps execution eligibility
```

No JSON/MD file, stdout payload, generated artifact, or code candidate-universe
constant may define the comparison universe or current fact.

## Versioned Semantics

### Shared Raw Fact

The shared snapshot records:

- StrategyGroup and candidate symbol;
- active PG universe symbols;
- aligned trigger candle close;
- lookback bars and return percentage for every member;
- deterministic competition rank;
- universe size;
- observed/valid-until time;
- PG/source lineage.

All calculations use `Decimal`. Missing members, unclosed candles, mismatched
close times, insufficient history, or stale snapshots block confirmation.

### MPG-LONG v2

MPG retains its existing 8-bar 1h momentum window. The event requires:

- existing 4h trend and 1h momentum persistence;
- candidate rank `1` inside the active MPG candidate universe;
- positive candidate return;
- existing `momentum_floor_reference` protection.

The evaluator emits:

```text
momentum_persistence_confirmed
leader_strength_confirmed
momentum_floor_reference
```

### MI-LONG v2

MI retains its existing 12h close-to-close impulse and 3% threshold. The event
also requires candidate rank `1` inside the active MI universe. It emits:

```text
impulse_confirmed
relative_strength_confirmed
impulse_invalidation_reference
```

The invalidation reference is the pre-impulse lookback close already present in
the evaluator evidence. No new percentage threshold is introduced.

## Certification Order

1. Build and verify shared PG comparative facts.
2. Migration 108 certifies MPG v2 only.
3. Deploy/observe MPG v2 or complete local cutover acceptance.
4. Migration 109 certifies MI v2 only after proving capability reuse.

Historical v1 Event Specs remain observe-only and readable. Each migration
atomically switches only its StrategyGroup bindings.

## Runtime Cadence And Performance

| Dimension | Decision |
| --- | --- |
| Cadence | Once per watcher tick before strategy evaluation |
| External reads | One 13-candle 1h request per unique MPG/MI symbol; five unique symbols today |
| PG writes | Seven bounded current fact rows per aligned trigger close: four MPG and three MI |
| No-signal JSON/MD writes | `0` |
| CPU | Decimal returns and rank over at most four members per group |
| Disk | No files, reports, or sidecars |
| Timeout | Reuse bounded Binance public market-source timeout |
| Retention | Current PG facts plus existing retention policy; no new archive |

## Safety And Failure Behavior

- Comparative facts never grant execution authority by themselves.
- Event Spec authority remains the upper bound.
- A stale/missing comparative snapshot produces no trial-grade signal.
- At most one real action-time lane remains unchanged.
- No live profile, capital, leverage, notional, symbol, or side expansion.
- Replay/sample comparative contexts never become live PG facts.

## Acceptance

- Universe comes from PG active candidate scopes.
- Five unique symbol candle reads produce seven group-symbol facts.
- Misaligned or missing peer data writes/returns an exact blocked fact state.
- MPG v2 emits all three typed facts and is the only new eligible event in 108.
- MI v2 reuses the same fact producer and is the only new eligible event in 109.
- Other StrategyGroups remain observe-only.
- File-authority and performance audits remain clear.
