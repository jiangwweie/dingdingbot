# Strategy Research Owner Direction Log

Status: ACTIVE_V3_OWNER_DIRECTION_LOG
Last updated: 2026-06-16

## Scope

This log records Owner instructions that change Strategy Research v3 search
space, evaluation semantics, or evidence governance.

All entries are research-only. They carry no order, execution intent,
execution authority, exchange-write authority, deploy authority, credential
authority, live-profile authority, FinalGate authority, OrderLifecycle
authority, exchange gateway authority, or order-sizing authority.

## 2026-06-16: Lightweight Strategy Cabinet Governance

### Instruction

Owner approved a lightweight document-governance pass for the strategy line.
The goal is to add a Strategy Research Guide and a Strategy Cabinet instead of
moving large historical research directories or cleaning raw replay outputs.

### Research Interpretation

1. Strategy research needs a stable guide that defines research goals,
   evidence standards, leverage interpretation, lifecycle statuses, handoff
   requirements, and execution-chain prohibitions.
2. Strategy research also needs a lightweight cabinet that registers strategy
   semantics, current status, blockers, evidence paths, handoff paths, and
   revival conditions.
3. The cabinet must not be treated as a runtime registry, return leaderboard,
   Strategy Picker implementation, FinalGate input, Operation Layer input, or
   order authority.
4. The first cabinet batch should register `MPG-001`, `FBS-001`, `TEQ-001`,
   `PMR-001`, `SOR-001`, `VCB-001`, `NLPD-001`, `RBR-001`, `LCF-001`,
   `RSR-001`, and `MDS-001`.
5. The governance pass should remain lightweight: no broad archive moves, no
   raw CSV cleanup, no execution-chain edits, no deploy, no exchange writes,
   and no main-control worktree changes.

### Current Evidence Hooks

| Artifact | Current Role |
| --- | --- |
| `docs/strategy-research/STRATEGY_RESEARCH_GUIDE.md` | Current strategy research rules and lifecycle guide. |
| `docs/strategy-research/strategy-cabinet/strategy-cabinet.md` | Human-readable Strategy Cabinet. |
| `docs/strategy-research/strategy-cabinet/strategy-cabinet.json` | System-readable Strategy Cabinet. |
| `docs/strategy-research/README.md` | Updated entry map for guide, cabinet, handoff, candidate packets, boundaries, and negative evidence. |

## 2026-06-16: Return Expectation And Strategy Pool Cognition

### Instruction

Owner provided additional material clarifying that the project has a return
expectation, but it is a conditional right-tail expectation rather than a
stable-income or single-strategy alpha expectation. Owner also reinforced that
future work should continue strategy research and expand the strategy pool.

### Research Interpretation

1. Future research should keep expanding StrategyGroup candidates, but each
   candidate must be framed as a bounded, regime-specific right-tail hypothesis.
2. Strong best-window returns are discovery and prioritization evidence, not
   runtime execution evidence.
3. Short-history 2026 Binance TradFi-like and precious-metal evidence remains
   valid for discovery, but blocks promotion until current availability,
   product, session, mark, funding, liquidity, fill, and margin facts exist.
4. Negative evidence must be preserved as disable facts, parking facts, and
   revival conditions instead of being deleted.
5. Strategy research should continue to group candidates by market structure,
   not only by indicator name or replay script.
6. Future handoff candidates should preserve RequiredFacts, activation facts,
   disable facts, leverage downshift rules, hard stops, sample packets, and
   non-execution flags.

### Current Evidence Hooks

| Artifact | Current Role |
| --- | --- |
| `docs/strategy-research/strategy-window-cognition-20260616.md` | Current cognition update for project return semantics, evidence quality, and strategy-pool expansion rules. |
| `docs/strategy-research/strategy-research-v3-goal.md` | Active V3 goal that defines right-tail, regime-specific, non-execution research semantics. |
| `docs/strategy-research/main-control-strategy-research-v3-handoff.md` | Current handoff context and leverage-aware candidate interpretation for main-control review. |

## 2026-06-14: Keep 2026 U.S. Equity And Precious Metals As First-Class Research Symbols

### Instruction

Owner clarified that 2026 Binance-listed U.S. equity-like instruments and
precious-metal instruments should be added to the research target universe.
Although their data history is short, Binance has public data, and the 1h
timeframe is sufficient for early discovery work.

### Research Interpretation

1. `TEQ-001` must continue to include USD-S TradFi equity/ETF perpetuals and
   bStocks spot symbols in discovery, right-tail window scans, classifier
   sweeps, event studies, and revival queues.
2. `PMR-001` must continue to include XAU/XAG/XPT/XPD precious-metal
   perpetuals plus XAUT/PAXG-like gold-token spot context.
3. `COPPERUSDT` remains metal-cycle context rather than PMR core precious-metal
   evidence unless a separate copper-specific hypothesis is created.
4. Binance official activity wording may reference `GOOGUSDT` and `XCUUSDT`;
   the current USD-S `exchangeInfo` research symbols are `GOOGLUSDT` and
   `COPPERUSDT`.
5. Short 2026 history blocks promotion and runtime consideration, but it does
   not block research intake, 1h replay, or candidate resurrection tracking.
6. Leveraged interpretation must carry the product-specific facts for mark
   price, funding, session gaps, liquidity, stop/fill behavior, and real margin.
7. Historical cached 1h rows are research evidence, not current exchange
   availability proof. Runtime-facing interpretation requires a fresh
   `current_exchangeinfo_availability_state` and symbol-mapping check.

### Current Evidence Hooks

| Artifact | Current Role |
| --- | --- |
| `docs/strategy-research/extended-universe-us-equity-metals-refresh-20260613.md` | Current 102-symbol interpretation layer for Binance U.S. equity-like and metals universe. |
| `docs/strategy-research/universe-expansion/binance-extended-universe-manifest.md` | ExchangeInfo-derived manifest covering bStocks, TradFi equity/ETF perpetuals, precious-metal tokens, precious-metal perpetuals, and copper context. |
| `docs/strategy-research/universe-expansion/tradfi-asset-universe-20260614.md` | Current Binance USD-S TradFi scope from `exchangeInfo`; separates `87` equity/ETF perps, `4` precious-metal perps, `1` industrial-metal context perp, and `1` tokenized-gold context symbol into replay-readiness lanes. |
| `docs/strategy-research/universe-expansion/current-binance-tradfi-availability-20260614.md` | Current public USD-S `exchangeInfo` check showing that cached 1h research data and current exchangeInfo visibility must be separate facts before promotion. |
| `docs/strategy-research/external-data/binance-extended-universe-1h-20260613/extended-universe-1h-snapshot-summary.md` | Public 1h OHLCV, mark, and funding snapshot for 102 symbols. |
| `docs/strategy-research/extended-universe-refresh-readiness/teq-pmr-refresh-readiness-summary.md` | Queue that keeps TEQ and PMR refreshes ahead of crypto-only followups. |
| `docs/strategy-research/cci-trend-escape-replay/cci-trend-escape-summary.md` | First CCI replay proving the expanded TradFi equity/metal universe is included in source-derived indicator semantics. |
| `docs/strategy-research/cci-asset-session-classifier/cci-asset-session-classifier-summary.md` | CCI asset/session classifier preserving precious-metal failure-short revival evidence while blocking promotion on drawdown and off-hour facts. |

## 2026-06-13: Binance U.S. Equity And Metals Universe

### Instruction

Owner reinforced that Binance-listed 2026 U.S. equity-like instruments and
precious-metal instruments should be included in the Strategy Research v3
universe even when their history is short.

### Research Interpretation

1. Short 2026 history is acceptable for 1h discovery, event studies, and
   early right-tail window mining.
2. Short history is not acceptable as promotion proof by itself.
3. U.S. equity-like instruments must include bStocks spot symbols and
   USD-S TradFi equity/ETF perpetuals when public 1h data exists.
4. Precious-metal instruments must include XAUt/PAXG-like spot tokens and
   USD-S precious-metal perpetuals when public 1h, mark, and funding data
   exists.
5. Levered interpretation must remain blocked or downshifted until mark,
   funding, liquidity, session-gap, stop/fill, and real margin facts exist.

### Current Evidence Hooks

| Artifact | Current Role |
| --- | --- |
| `docs/strategy-research/extended-universe-us-equity-metals-refresh-20260613.md` | Current 102-symbol interpretation layer for Binance U.S. equity-like and metals universe. |
| `docs/strategy-research/universe-expansion/binance-extended-universe-manifest.md` | Public exchangeInfo-derived manifest. |
| `docs/strategy-research/external-data/binance-extended-universe-1h-20260613/extended-universe-1h-snapshot-summary.md` | Public 1h OHLCV, mark, and funding snapshot. |
| `docs/strategy-research/extended-universe-refresh-readiness/teq-pmr-refresh-readiness-summary.md` | Replay queues for TEQ/PMR refresh work. |

### RequiredFacts Impact

| RequiredFact | Meaning |
| --- | --- |
| `expanded_tradfi_universe_manifest_state` | Dynamic exchangeInfo-derived universe must be refreshed before current TEQ/PMR interpretation. |
| `low_history_dataset_state` | Short-history symbols are allowed for discovery but blocked for promotion. |
| `session_gap_policy` | Equity-like and commodity products need explicit market-hour and 24/7 trading interpretation. |
| `mark_funding_review_state` | TradFi futures need mark/funding review before levered interpretation. |
| `real_margin_model_state` | Proxy liquidation checks cannot authorize promotion. |

## 2026-06-14: U.S. Equity And Metals Stay First-Class

### Instruction

Owner reaffirmed that **2026 Binance-listed U.S. equity-like instruments and
precious-metal instruments** should be added and retained in the replay
universe because Binance has enough 1h data for discovery.

### Research Interpretation

1. The short data history is acceptable for source-derived 1h replay,
   right-tail window mining, low-history event studies, and candidate revival
   tracking.
2. The same short data history blocks promotion, runtime registration, and
   leverage interpretation unless product-specific facts are attached.
3. Future indicator and community-source replays should keep
   `tradfi_equity_perpetual` and `tradfi_precious_metal_perpetual` as
   first-class attribution categories.
4. Leverage views remain research stress transforms only until mark/index,
   funding, session-gap, liquidity, stop/fill, and real exchange-margin facts
   exist.

### Current Evidence Hooks

| Artifact | Current Role |
| --- | --- |
| `docs/strategy-research/efi-elder-force-index-replay/efi-elder-force-index-summary.md` | First replay after this reaffirmation; includes 2026 TradFi equity and precious-metal futures as first-class categories. |
| `docs/strategy-research/candidate-packets/EFI-001-elder-force-index-packet.md` | Candidate packet preserving price-volume force evidence and product-risk blockers. |
