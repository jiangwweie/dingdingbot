# Opportunity Hypothesis Register

Last updated: 2026-05-25
Status: Active lightweight register
Phase: `RBC Reset / Opportunity Structure Discovery v0`
Runtime effect: none
Trading permission effect: none

## Role

This register tracks opportunity hypotheses for coarse screening. Entries here
are not approved research tasks, not strategy candidates, not runtime designs,
and not trading instructions.

All entries start as `research-only` until a later report changes their label.

## Register

| hypothesis_id | opportunity type | mechanism | why asymmetry may exist | possible capital shape | required data | minimal falsification idea | status | label | next action | stop condition |
|---|---|---|---|---|---|---|---|---|---|---|
| ORH-001 | Perp Crowding / Funding + OI Imbalance | Crowded perp positioning may create squeeze, reversal, continuation, or no-long states when funding and OI diverge from price path. | Perp leverage can force nonlinear exits; funding extremes and OI expansion/flush may reveal crowded risk before spot OHLCV does. | observe-only, no-long-risk-control, manual-event-study-only | Public funding, open interest, OHLCV; no API keys | R3 replicated the positive-funding + OI-up crowded-long flush observation on 2026-02 and 2026-03 with 24h/48h de-dup, next-bar lens, controls, symbol split, and top-event dependency checks. | R3 complete | research-only / observe-only flag | Define observation-flag semantics; keep disconnected from runtime/order paths and do not promote to manual-event or systematic-small. | Park or downgrade if future slices show the effect collapses to controls, becomes top-event-only, or cannot be interpreted before the flush window is gone. |
| ORH-002 / OS02 | 1h False Breakout Reversal | Failed breaks of recent 24h/48h highs/lows may trap breakout chasers and create short-horizon reversal pressure. | Stop/trigger clustering around recent high/low levels can create forced reversal when the breakout bar closes back inside range. | formerly observe-only; now park | Local 1h OHLCV; no funding/OI/API keys | Final external kill test failed: dedup_24h 24h did not beat true_downside_breakdown control, and path risk remained larger than endpoint. Evidence: `reports/os02-final-external-kill-test/report.md`; decision: `reports/os02-park-or-survive-decision/report.md`. | final kill test complete | research-only / park | No observe-only restoration, manual-event candidate, systematic-small candidate, or runtime candidate. Preserve evidence paths only. | Remain parked unless a future independent hypothesis changes the mechanism and starts from a new frozen protocol; do not resurrect OS02 from subperiod strength. |
| ORH-003 | Relative Strength / Weak Coin Continuation | Strong/weak ranking might reveal continuation or weak-side persistence across liquid contracts. | Capital may compound faster by choosing the right venue for risk, but this requires stable cross-sectional information beyond BTC/ETH/SOL beta. | not-candidate unless broader universe appears | Local OHLCV; broader universe required for real cross-sectional work | R0 on BTC/ETH/SOL found no stable long-short spread versus random controls. | R0 complete | research-only / park | Keep parked unless a broader local high-liquidity universe is available without data-platform work. | Remain parked if only three-symbol universe is available or spread does not beat random controls. |
| ORH-004 / old CPM | 4H Trend Regime + 1H Pullback/Reclaim | 4H trend context plus 1H reclaim/failure structure might separate useful price-failure events from generic pullbacks. | Trend context may shape which failed local breaks trap participants, but generic EMA pullbacks may be noise. | research-only, possible risk-filter-study | Local 1h OHLCV aggregated to 4h; no funding/OI/API keys | R0 found 4H EMA60 regime itself weak; generic EMA20 pullback/reclaim weak; false-break reclaim had short-window structure but 24h giveback; downstream price-failure/reclaim family is stopped for now. | R0 complete plus family stop | research-only / park | Do not revive old CPM or generic reclaim-family continuation. | Remain parked unless a separate future hypothesis starts with stronger external controls and no old-CPM dependency. |
| ORH-005 | 1h Alt Relative Underextension Bounce | ETH/SOL and broader liquid alts may rebound after underextending versus BTC over a short window, but only if the surrounding tape is not mixed chop or high-vol shock. | Crypto majors often reprice with lag; extreme short-horizon relative weakness may reflect temporary liquidity stress rather than durable information. The latest audits suggest the useful manual gate is broad regime exclusion; the `btc7d_ge_0` refinement improved historical metrics but failed a bounded 2026 independent holdout and did not beat same-symbol/month random 8h exposure. | research-only, relative-range-reversion reserve context only | Local/public 1h OHLCV artifacts only; no API keys | Manual matrix found L1 relative underextension retest as the best long branch. Strict frozen falsification showed `btc_aligned_7d` failed same-parent stress controls; L1 overlay refinement found `no_chop_no_shock` passed same-parent controls across sample/OOS/stress. L1 mechanism/harvest audit found `fixed_8h` remained the best mean-return lens. L1 failure-filter audit found `btc7d_ge_0` improved historical mean return from `0.700%` to `0.960%`, but independent 2026-01 through 2026-04 holdout retest produced 31 filtered events with mean return `-0.227%`, median return `-0.052%`, and falling-knife share `22.581%`. Baseline comparison found same-symbol/month random 8h exposure mean `0.030%`, so actual filtered L1 underperformed random-time by `-0.257%`, while still outperforming same-symbol buy-hold context at `-16.300%`. Evidence: `reports/manual-strategy-frozen-falsification-2026-05-24-v1/`, `reports/l1-overlay-refinement-2026-05-24-v1/`, `reports/l1-mechanism-harvest-audit-2026-05-24-v1/`, `reports/l1-failure-filter-audit-2026-05-24-v1/`, `reports/l1-independent-retest-2026-01-04-v1/`, and `reports/l1-baseline-comparison-2026-holdout-v1/`. | L1 baseline comparison complete | research-only / reserve_only_mixed_baseline | Stop promoting `no_chop_no_shock + btc7d_ge_0 + fixed_8h`; do not add more L1 filters next. If continuing market-alpha research, switch to ORH-007 SQ02-R1 frozen falsification or another not-yet-falsified line. | Park if future work attempts to rescue L1 with more filters, if residual structure remains random-time-equivalent, if benefit remains month/symbol dependent, or if the next useful step would require runtime/order/account work. |
| ORH-006 / OS06 standalone | 1h Down Volume Climax Bounce | Large down 1h candles with high volume may mark forced-selling exhaustion and short-horizon bounce pressure. | Panic selling/liquidation-like flow may exhaust immediate sellers; bounce can exist even when it is not a durable long strategy. | reserve-only downside-exhaustion context | Local BTC/ETH/SOL 1h OHLCV; volume only; no liquidation feed/API keys | Trend/range feasibility scan found EX01 median 24h lens return 0.355%, signal minus matched control 0.495%, positive month rate 58.824% on 635 events; prior OS06-R1 cooled the standalone claim after de-dup and magnitude controls. | R0/R1 mixed evidence; standalone parked | research-only / park as standalone; reserve only | No standalone continuation. Reserve only as background downside-exhaustion context if a future non-standalone family audit needs it. | Remain parked as a standalone line if magnitude-matched controls erase the effect, or if endpoint remains weak after de-dup. |
| ORH-007 | 1h Compression Down Breakout Continuation | Low 72h realized range followed by a 1h downside break may release stored downside pressure. | Range buyers and late support defenders can become trapped when compressed structure breaks downward; the current evidence is asymmetric because up-compression failed. R1 and public-universe retest suggest the effect is not just generic downside breakdown, but April 2026 weakness and reclaim sensitivity keep it research-only. | research-only, trend-from-range study, manual-semi-auto no-order dry run, docs-only strategy-contract skeleton candidate | Local BTC/ETH/SOL 1h OHLCV plus public Binance USD-M monthly OHLCV archives; no API keys | R0 feasibility found SQ02 median 24h lens return `0.199%` on 176 events. SQ02-R1 local falsification produced 110 24h de-duplicated events with 24h median `0.219%`, estimated 12bp-cost median `0.099%`, random control median `-0.088%`, and non-compression downbreak control median `-0.109%`. Public-universe 2026-01 through 2026-04 holdout produced 508 24h de-duplicated events across 35 symbols with 24h median `0.359%`, estimated 12bp-cost median `0.239%`, random control median `0.213%`, and non-compression downbreak control median `0.059%`; no-12h-reclaim events were much stronger than reclaimed events. Manual semi-auto design defines no-order human review packets and review logs only. A no-order 18-packet historical sample was generated with forbidden order/account/sizing fields absent. Event-time priority separated high-priority packets from low-priority packets using only event-time fields. Semi-auto momentum synthesis keeps SQ02 as the primary review branch, slow D1/4H momentum as background context, and ORH-001 as caution/no-long context; a simplified 508-row no-order control sheet was generated. Readability audit found the sheet safe from outcome leakage but recommended V2 copy cleanup because slow-momentum labels may be misread as direction advice. The 2026-05-25 business-mainline decision makes SQ02 the first docs-only `StrategyContract` skeleton candidate, without promoting it to runtime or order use. Evidence: `reports/orh-007-sq02-r1-falsification-20260524/`, `reports/orh-007-sq02-public-universe-retest-20260524/`, `reports/sq02-manual-semi-auto-review-design-20260524/`, `reports/sq02-no-order-packet-sample-20260524/`, `reports/sq02-event-time-priority-audit-20260524/`, `reports/semi-auto-momentum-synthesis-20260524/`, and `reports/semi-auto-control-sheet-readability-audit-20260525/`. | semi-auto readability audit plus mainline acceptance complete | research-only / human-review-dry-run-only / docs-only strategy-contract skeleton candidate | Next: draft `SQ02_DOWNSIDE_CONT_V0` as a docs-only `StrategyContract` skeleton for the Personal Leveraged Campaign mainline. V2 no-order control sheet copy cleanup is optional/subordinate. No scanner, alert, watchlist, runtime, real order path, paper/testnet/tiny-live/live, real account, position sizing, or leverage framing without separate Owner-gated promotion review. | Park or reserve if no-reclaim cannot be reviewed without lookahead, if April weakness dominates, if review labels are inconsistent, if packet fields drift toward order/sizing/leverage, if momentum context is used to override packet quality, if neutral copy cannot prevent signal interpretation, or if promotion would require runtime/order/account work. |
| ORH-008 / Campaign Mechanics / CPV0_2 | Personal risk-capital campaign account mechanics | A bounded campaign needs explicit account-state rules before any alpha thesis matters: loss limits, right-tail preservation, profit giveback prevention, pause, withdrawal, restart, and rule-drift hard locks. | Asymmetry may come from account mechanics rather than market prediction: cap ruin paths, avoid emotional escalation after losses, and retain part of rare upside. | research-only / paper-only account protocol; no market alpha | Synthetic paths only; no trading API, no runtime, no market signal data required | R2 froze `CPV0_2_principal_first_hardlock`; R3 found schema refinement required; R4 schema v2 froze sequence/hash/references/snapshots/review/rule/invariant ids and passed replay expectation freeze with valid pass `1.0000`, invalid detect `1.0000`, hard-lock explanation `1.0000`, schema gaps `0`; bounded observation packet then covered principal-first profit protection and loss-pause-review closure paths. | R4 schema-v2 and bounded observation complete | research-only / bounded_paper_observation_packet_complete | Hold account-mechanics expansion unless a concrete review gap appears; use CPV0_2 only as a paper-only account-mechanics reference. No tiny-live, no strategy, no paper trading account, no position/leverage/live advice, no stage/commit/push/deploy/PR. | Park or revise if schema v2 fails deterministic replay, invalid logs are not detected, hard-lock detection becomes unexplained, accounting snapshots conflict with replay, account-mechanics protection collapses into psychological comfort, or further expansion requires account/runtime/API work. |
| ORH-009 | Exchange Incentive / Funding / OI Pressure Observability | Public exchange mechanics, funding, and open-interest pressure may reveal pre-decision crowded-risk states before price-path confirmation. | Crypto perp leverage, carry pressure, and instrument mechanics can create one-sided forced-flow risk before price-only evidence is clean. | observe-only, no-long-risk-control-study, manual-event-study-only later, reserve-only | Public funding, open interest, instrument metadata, mark/index context, and source timestamp coverage first; no API/account in current scope | Falsification brief, data availability audit, source inventory, R1 public-archive source validation, and no-outcome timestamp-alignment audit completed. R1 downloaded a tiny BTCUSDT April 2026 public archive sample, passed checksum/header/row-count/timestamp validation, and mapped 9 of 10 funding events to nearest-prior OI with 0 lookahead errors; the only miss was an initial boundary gap. | R1 timestamp alignment complete | research-only / timestamp_alignment_passed_with_boundary_rule | Freeze ORH-009-R2 falsification design before any outcome test: pressure definitions, timestamp rule, nearest-prior OI rule, warm-up/boundary exclusion, controls, de-dup, and park/reserve/continue criteria. No backtest, API, scanner, runtime, strategy implementation, stage, commit, push, deploy, or PR. | Park or reserve if the design duplicates ORH-001, requires price confirmation, cannot define pre-decision pressure states, or drifts toward API/backtest/scanner/runtime/trading advice. |

## Current Notes

- Entries in this register are lightweight research labels only, not strategy
  candidates or runtime permissions.
- ORH-001 now has bounded empirical artifacts under `reports/orh-001-r1/`,
  `reports/orh-001-r2/`, and `reports/orh-001-r3/`.
- ORH-002 artifacts live under `reports/orh-002-r0/`,
  `reports/orh-002-r1/`, `reports/orh-002-r2/`,
  `reports/os02-final-external-kill-test/`, and
  `reports/os02-park-or-survive-decision/`; final status is `park`.
- ORH-003 R0 artifacts live under `reports/orh-003-r0/`.
- ORH-004 R0 artifacts live under `reports/orh-004-r0/`.
- ORH-001 x ORH-002 sanity artifacts live under `reports/orh-x-001002-r0/`.
- Cross-ORH synthesis lives under `reports/cross-orh-synthesis/`.
- Cross-ORH synthesis v2 lives under `reports/orh-cross-synthesis-v2/`.
- Trend/range feasibility artifacts live under
  `reports/trend-range-direction-feasibility-001/`.
- ORH-007 SQ02 falsification and public-universe retest artifacts live under
  `reports/orh-007-sq02-r1-falsification-20260524/` and
  `reports/orh-007-sq02-public-universe-retest-20260524/`; manual semi-auto
  design artifacts live under
  `reports/sq02-manual-semi-auto-review-design-20260524/`; no-order packet
  sample artifacts live under `reports/sq02-no-order-packet-sample-20260524/`;
  readable review-card artifacts live under
  `reports/sq02-readable-review-cards-20260524/`; field utility and blind
  review artifacts live under `reports/sq02-field-utility-audit-20260524/` and
  `reports/sq02-blind-review-cards-20260524/`; event-time priority and no-order
  triage artifacts live under `reports/sq02-event-time-priority-audit-20260524/`,
  `reports/sq02-no-order-triage-design-20260524/`, and
  `reports/sq02-priority-blind-review-cards-20260524/`; semi-auto momentum
  synthesis lives under `reports/semi-auto-momentum-synthesis-20260524/`;
  control-sheet readability audit lives under
  `reports/semi-auto-control-sheet-readability-audit-20260525/`.
- Personal Leveraged Campaign mainline documents live under
  `docs/ops/personal-leveraged-campaign-mainline-v0.md` and
  `docs/adr/0008-personal-leveraged-campaign-business-chain.md`; ORH-007 /
  `SQ02_DOWNSIDE_CONT_V0` is the first docs-only strategy-contract skeleton
  candidate, not a runtime or order-path candidate.
- Manual strategy matrix and L1 refinement artifacts live under
  `reports/unattended-autonomous-sprint-2026-05-24-manual-strategy-matrix-v1/`,
  `reports/manual-strategy-frozen-falsification-2026-05-24-v1/`, and
  `reports/l1-overlay-refinement-2026-05-24-v1/`, and
  `reports/l1-mechanism-harvest-audit-2026-05-24-v1/`, and
  `reports/l1-failure-filter-audit-2026-05-24-v1/`, and
  `reports/l1-independent-retest-2026-01-04-v1/`, and
  `reports/l1-baseline-comparison-2026-holdout-v1/`.
- Research board refresh artifacts live under
  `reports/research-board-status-refresh/`.
- Campaign Mechanics R0 artifacts live under `reports/campaign-mechanics-r0/`.
- Campaign Mechanics R1 artifacts live under `reports/campaign-mechanics-r1/`,
  `reports/campaign-protocol-candidate-v0/`,
  `reports/campaign-rule-drift-stress-r0/`, and
  `reports/campaign-mechanics-synthesis-v1/`.
- Campaign Protocol R2/R3 artifacts live under `reports/campaign-protocol-r2/`
  and `reports/campaign-protocol-r3-event-replay/`.
- CPV0_2 schema-gate unattended sprint artifact lives under
  `reports/unattended-autonomous-sprint-2026-05-24-cpv02-schema-gate/`.
- CPV0_2 schema-v2 refinement artifacts live under
  `reports/campaign-protocol-schema-v2/`.
- CPV0_2 bounded paper-only observation artifacts live under
  `reports/cpv02-bounded-paper-observation-packet-v1/`.
- ORH-009 falsification brief and data availability audit artifacts live under
  `reports/orh-009-exchange-funding-oi-observability/`.
- ORH-009 public-data inventory artifacts live under
  `reports/orh-009-public-data-inventory-v1/`.
- ORH-009-R1 source-validation artifacts live under
  `reports/orh-009-r1-source-validation-protocol/`; downloaded public archive
  sample lives under `data/orh_009_r1_public/binance_archive_sample/`.
- No strategy implementation, runtime integration, data platform, API key, or
  trading permission is implied.
