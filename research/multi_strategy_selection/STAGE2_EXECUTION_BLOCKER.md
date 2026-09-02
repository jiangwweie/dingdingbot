# Stage-2 Full Replay Execution Blocker

## Result

```text
research_status = RUNTIME_REFACTOR_REQUIRED
blocker_code = ENTRY_REFERENCE_DATA_GAP
selector_design_authority = NONE
implementation_authority = NONE
production_authority = NONE
```

Execution stopped after R2 and before market-data acquisition, as required by
the task's Research Code boundary and Event Entry/Stop Authority rules.

## Known code facts

1. Current Detectors are directly reusable pure domain logic and each triggered
   result freezes exactly one `protection_reference` fact.
2. `produce_strategy_signal()` freezes Event identity and facts, but it does not
   contain or derive `entry_reference_price`.
3. `build_capacity_claim()` defines the production entry price from the
   action-time `EntryAdmissionSnapshot`:

   ```text
   long  -> best_ask_price
   short -> best_bid_price
   ```

4. The task's authorized market inputs are 1h/4h Detector Klines plus 15m/1m
   path-resolution Klines. OHLC Klines cannot reproduce an action-time
   best-bid/best-ask observation.
5. The requested immutable 2026-08-30 PostgreSQL snapshot was not found in the
   workspace. `new.zip` is a source-code snapshot. Current Tokyo PostgreSQL
   retains bounded historical lineage and was used only for sanity counts; it
   is not the requested snapshot.

Sources: current tracked code at the frozen dev SHA, especially
`produce_strategy_signal.py:28`, `build_capacity_claim.py:129`, the four
Detector files, and current Tokyo PostgreSQL readonly facts.

## Why execution cannot continue under protocol v1

The Full Replay requires every triggered Event to have exact entry/stop geometry
before first-passage calculation. Stop geometry is available from Detector
facts. Entry geometry is not. Substituting trigger close, next-bar open, candle
midpoint, or an optimistic/pessimistic spread would create a new research
semantic and violate the explicit prohibition against assuming `entry = close`.

Invalidating every Event would leave zero outcome observations and could not
answer the Stage-2 questions. Using production Ticket/Shadow quotes would cover
only a subset of historical production Signals and not the required 24-symbol
point-in-time replay.

## Required Owner decision for a new protocol version

One of these must be explicitly authorized as `protocol_v2`; protocol v1 and
this blocker record must remain retained:

1. Provide a point-in-time official historical best-bid/best-ask source and
   freeze the exact timestamp-selection rule matching Admission semantics.
2. Define a separate research-only Signal-basis entry reference, such as trigger
   close, while explicitly accepting that it tests Detector path quality rather
   than production CapacityClaim geometry.
3. Reduce scope to production historical Signals with persisted Ticket/Shadow
   entry quotes; this is not Full 24-symbol Replay and requires a renamed task.

No option was selected in this task, so R3-R16 were not executed.

