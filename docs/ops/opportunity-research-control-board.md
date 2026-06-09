> [!NOTE]
> **HISTORICAL_EVIDENCE** — This document is a historical operational, governance, sprint, product, or live-trial artifact from an earlier project phase.
>
> It may be useful for context, auditing, or traceability, but it does **not** represent current project state, constraints, product direction, or agent instructions.
>
> Current authoritative sources:
> - `docs/canon/PROJECT_BASELINE_CURRENT.md`
> - `docs/canon/BRC_TARGET_SEMANTICS.md`
> - `docs/canon/AGENT_WORKSPACE_RULES.md`
> - `docs/canon/RUNTIME_SAFETY_BOUNDARY.md`
> - `docs/canon/TECH_DEBT_BASELINE.md`
> - `docs/canon/DOCUMENT_GOVERNANCE.md`

> [!WARNING]
> **PARTIALLY STALE**: This control board may contain stale phase labels.
> Current baseline and readiness blockers are maintained in:
> - `docs/ops/knowledge-pack/PROJECT_BASELINE_CURRENT.md`
> - `docs/ops/knowledge-pack/CURRENT_READINESS_BLOCKERS.md`
> Current active target (Owner 2026-05-29): "fast trial-and-review research system for small risk-capital Campaigns".

---

# Opportunity Research Control Board

Last updated: 2026-05-25
Status: Active research board
Phase: `RBC Reset / Opportunity Structure Discovery v0`
Runtime effect: none
Trading permission effect: none

## 1. Current Phase

The active research phase is:

`RBC Reset / Opportunity Structure Discovery v0`

The current project posture is open opportunity-structure research. The project
is not centered on Direction A, BTC+ETH Phase 1, HTF/LTF trend baseline,
Owner-Gated execution, StrategySignalV2, tiny-live, or small-live readiness.

## 2. Active Research Posture

Codex may autonomously advance bounded docs-only and research-only work inside
the research freedom zone, with clear labels and after-the-fact reporting.

Research outputs may become:

- observe-only context;
- manual-event review aids;
- Campaign / capital-shape studies;
- no-long / risk-off context;
- systematic-small studies;
- not-candidate / park decisions.

Research outputs do not become runtime authority.

## 3. Current Allowed Work

Allowed by default:

- update opportunity governance docs;
- update this board;
- update the hypothesis register;
- inspect existing repo/docs/reports;
- draft falsification briefs;
- create docs-only methodology notes;
- later, when selected, run bounded local research scripts or public-data pulls
  under clear `research-only` / `sandbox-only` labels.

## 4. Current Forbidden Work

Forbidden in this board's current state:

- real API key / secret / passphrase use;
- real exchange account action;
- real order placement, cancellation, modification, transfer, or withdrawal;
- paper/testnet/live/tiny-live activation;
- connecting research output to real order flow;
- LLM/Agent trading decisions;
- remote push without Owner confirmation;
- treating any current hypothesis as a strategy candidate;
- creating a Claude implementation task card for strategy/runtime work.

## 5. Opportunity Queue

| ID | Opportunity | Current status | Current label | Next action |
|---|---|---|---|---|
| ORH-001 | Perp Crowding / Funding + OI Imbalance | R3 second-slice retest complete | research-only / observe-only flag | Keep as observation flag only; do not promote to manual-event, campaign-shape, systematic-small, or runtime. |
| ORH-002 / OS02 | 1h False Breakout Reversal | Final external kill test complete | research-only / park | Park. External kill test failed because dedup_24h 24h did not beat true_downside_breakdown and path risk remained larger than endpoint. Preserve evidence at `reports/os02-final-external-kill-test/report.md` and `reports/os02-park-or-survive-decision/report.md`. |
| ORH-003 | Relative Strength / Weak Coin Continuation | R0 minimal falsification complete | research-only / park | Keep parked unless a broader local high-liquidity universe becomes available without data-platform work. |
| ORH-004 / old CPM | 4H Trend Regime + 1H Pullback/Reclaim | R0 minimal falsification complete plus downstream family stop | research-only / park | Park old CPM and generic price-failure/reclaim continuation for now; do not revive without a separate new hypothesis and stronger external controls. |
| ORH-005 | 1h Alt Relative Underextension Bounce | L1 independent holdout and baseline comparison complete | research-only / reserve_only_mixed_baseline | Stop promoting `no_chop_no_shock + btc7d_ge_0 + fixed_8h`; do not add more L1 filters next. Preserve broad mechanism notes as reserve context only. |
| ORH-006 / OS06 standalone | 1h Down Volume Climax Bounce | Standalone continuation cooled by adversarial matched-control evidence | research-only / park as standalone; reserve only | No standalone continuation. Reserve only as background downside-exhaustion context if a future non-standalone family audit needs it. |
| ORH-007 | 1h Compression Down Breakout Continuation | SQ02-R1, public-universe holdout, manual semi-auto design, no-order packet sample, semi-auto momentum synthesis, simplified control sheet, readability audit, and business-mainline acceptance complete | research-only / human-review-dry-run-only / docs-only strategy-contract skeleton candidate | Next: draft `SQ02_DOWNSIDE_CONT_V0` as a docs-only `StrategyContract` skeleton under the Personal Leveraged Campaign mainline. V2 no-order control sheet copy cleanup is optional/subordinate. No scanner, alert, watchlist, runtime, order path, paper/testnet/tiny-live/live, real account, position sizing, or leverage framing before separate Owner-gated promotion review. |
| ORH-008 / Campaign Mechanics / CPV0_2 | Personal risk-capital campaign account mechanics | R4 schema v2 and bounded observation packet complete | research-only / bounded_paper_observation_packet_complete | Hold account-mechanics expansion unless a concrete review gap appears; use CPV0_2 only as a paper-only account-mechanics reference. |
| ORH-009 | Exchange Incentive / Funding / OI Pressure Observability | R1 source validation and timestamp alignment complete | research-only / timestamp_alignment_passed_with_boundary_rule | Next: freeze ORH-009-R2 falsification design before any outcome test. No backtest, scanner, API, runtime, strategy, stage, commit, push, deploy, or PR. |

## 6. Decision Queue

| Decision | Needed now? | Owner required? | Notes |
|---|---:|---:|---|
| Accept this board as active research SSOT | Yes | No for local docs patch; Owner may revise later | This patch makes it the active board by pointer. |
| Pick first falsification brief | No | No, unless Owner wants to override priority | This sprint has closed OS02 and opened Campaign Mechanics R0 instead of another market-alpha falsification brief. |
| Promote any hypothesis to runtime/paper/testnet/live | No | Yes | No runtime candidates exist; Campaign Mechanics R0 is research-only account-mechanism work. |
| Use real API keys or real account | No | Yes | Explicitly forbidden by default. |
| Push branch | No | Yes | Local work only. |

## 7. Current Empirical Step

`ORH-001-R1`, `ORH-001-R2`, and `ORH-001-R3` have been run as bounded
`research-only / sandbox-only` studies using public Binance funding/OI data and
local 1h OHLCV.

Current result: R3 retested the R2 crowded-long flush observation on independent
2026-02 and 2026-03 slices, with 2026-04 retained only as reference. The
crowded-long bucket survived 24h/48h episode de-duplication, next-bar lens,
controls, symbol split, and top-event dependency checks strongly enough for the
final R3 verdict `promote_to_observe_only`.

Boundary: this means `research-only observation flag` only. It is not a
manual-event watchlist, not campaign-shape, not systematic-small, and not a
runtime/order-path candidate. The 48h giveback remains mixed: 2026-03 and
2026-04 give back much of the 24h effect, while 2026-02 does not.

Next minimum action: document the observation-flag semantics and inspect
whether it should be used only as a no-long / caution context in future
research reports, without wiring it to runtime.

Sleep-run update on 2026-05-23:

- ORH-002 R0 found positive false-breakout reversal information across
  24h/48h lookbacks and both upside/downside directions, but only as
  observe-only because R0 has no episode de-duplication or slice retest.
- ORH-003 R0 was parked: BTC/ETH/SOL relative strength ranking did not beat
  random controls consistently in the local three-symbol universe.
- Cross-ORH synthesis recommends ORH-002-R1 as the next research-only action
  and explicitly forbids scanners, runtime flags, alerts, order-path work, or
  strategy packaging.

Research sprint update on 2026-05-23:

- ORH-002 R1 kept the false-breakout observation at `promote_to_observe_only`
  after 12h/24h episode de-duplication, monthly/quarterly slices, next-bar
  lens, controls, symbol/direction/lookback splits, and top-event checks.
  The result is cooler than R0: upside, especially 48h lookback, is cleaner;
  downside is mixed after de-duplication.
- ORH-002 R2 verdict is `continue_research_only`: mechanism is closest to
  local sweep/failure mean reversion with strong path risk, not a clean
  strategy boundary.
- ORH-004 R0 verdict is `refine_again`: 4H EMA60 regime did not carry positive
  directional lens information by itself, and generic 1H pullback/reclaim did
  not beat controls. False-break reclaim deserves only a narrower retest.
- ORH-001 x ORH-002 sanity check verdict is `refine_again`: intersection was
  directionally positive but too small, with only 6 inside crowded-long false
  upside events across 2026-02 to 2026-04.
- Cross-ORH synthesis v2 lives under `reports/orh-cross-synthesis-v2/`.

Trend/range direction update on 2026-05-23:

- A 1h BTC/ETH/SOL feasibility scan was run as `research-only / sandbox-only`
  under `reports/trend-range-direction-feasibility-001/`, with script
  `scripts/research_sandbox/trend_range_direction_feasibility_001.py`.
- Three directions passed the first-pass `continue_research_only` screen:
  ORH-005 / RR02 alt relative underextension bounce, ORH-006 / EX01 down
  volume climax bounce, and ORH-007 / SQ02 compression down breakout
  continuation.
- ORH-002-like range false upside/downside failures stayed useful as
  `observe_or_refine`, but not enough to create a duplicate new mainline.
- Pure 1h trend breakout continuation was weak in both directions and should
  be parked for now: TR01 uptrend breakout median 24h was -0.305%, and TR02
  downtrend breakdown median 24h was -0.470% under the scan lens.
- Nothing in this update authorizes alerts, scanners, runtime flags, strategy
  packaging, order-path work, or real-account activity.

Research board refresh on 2026-05-24:

- ORH-002 / OS02 is now parked after final external kill test and
  park-or-survive decision artifacts. The preserved evidence paths are
  `reports/os02-final-external-kill-test/report.md` and
  `reports/os02-park-or-survive-decision/report.md`.
- Price-failure / reclaim family continuation is stopped for now. This includes
  ORH-004 / old CPM revival and generic reclaim-family follow-up unless a
  separate future hypothesis is proposed with stronger external controls.
- OS06 standalone is parked with no standalone continuation; DSS D+OI is parked
  as reserve-only context.
- The next active research type is Campaign Mechanics R0: a research-only,
  synthetic account-mechanism study for personal risk-capital campaign rules.
  It is not market alpha, not a trading strategy, and not connected to runtime.

Campaign Mechanics R1 update on 2026-05-24:

- R0 audit found partial hidden optimism: R0 paths were useful but too few and
  favored withdrawal/profit-protection logic; negative-edge, high-variance
  no-edge, edge-decay, and rule-drift coverage were missing.
- Campaign Protocol Candidate v0 is frozen as a paper-only account-mechanism
  candidate under `reports/campaign-protocol-candidate-v0/`.
- Expanded synthetic stress and rule-drift stress live under
  `reports/campaign-mechanics-r1/` and
  `reports/campaign-rule-drift-stress-r0/`.
- Synthesis lives under `reports/campaign-mechanics-synthesis-v1/`.
- Verdict: continue research-only / paper simulation candidate, but
  `candidate_protocol_needs_refine`; tiny-live remains no.

CPV0_2 schema-gate update on 2026-05-24:

- Campaign Protocol R2 froze `CPV0_2_principal_first_hardlock` and marked it
  `paper_observation_ready` for abstract paper-only paths only.
- Campaign Protocol R3 event replay then found `needs_protocol_schema_refine`:
  valid case pass rate `1.0000`, invalid case detect rate `1.0000`, hard-lock
  detection rate `0.9000`, rule-drift detection rate `1.0000`, schema gap count
  `6`.
- Current governance label is `research-only / paper_schema_refine_required`.
  The next action is schema refinement and replay expectation freeze, not
  broader observation, market alpha, runtime, API, order path, paper trading
  account, testnet, tiny-live, live, position, or leverage work.
- Sprint artifact:
  `reports/unattended-autonomous-sprint-2026-05-24-cpv02-schema-gate/`.

CPV0_2 schema-v2 refinement update on 2026-05-24:

- Campaign Protocol schema v2 froze deterministic ordering, event hashes,
  trigger references, threshold snapshots, before/after accounting snapshots,
  review provenance, rule version, and invariant attribution fields.
- Replay expectation freeze passed: valid case pass rate `1.0000`, invalid
  case detect rate `1.0000`, expected-family detection rate `1.0000`,
  hard-lock explanation rate `1.0000`, schema gap count `0`.
- Current governance label is
  `research-only / schema_v2_ready_for_bounded_paper_observation`.
  The next action is one bounded abstract paper-only observation packet, not
  market alpha, runtime, API, order path, paper trading account, testnet,
  tiny-live, live, position, leverage, stage, commit, push, deploy, or PR.
- Sprint artifact:
  `reports/campaign-protocol-schema-v2/`.

CPV0_2 bounded paper-only observation update on 2026-05-24:

- The bounded schema-v2 observation packet is complete under
  `reports/cpv02-bounded-paper-observation-packet-v1/`.
- The packet uses abstract campaign events only and covers two bounded
  paper-only paths: principal-first profit protection and loss-pause-review
  closure.
- Current governance label is
  `research-only / bounded_paper_observation_packet_complete`.
  Account-mechanics expansion should now hold unless a concrete review gap
  appears. This does not authorize market alpha, strategy implementation,
  runtime, API, order path, paper trading account, testnet, tiny-live, live,
  position, leverage, stage, commit, push, deploy, or PR.

ORH-009 brief/audit update on 2026-05-24:

- ORH-009 opens exchange incentive / funding / open-interest pressure
  observability as a non-price opportunity-structure research line.
- The falsification brief and data availability audit are complete under
  `reports/orh-009-exchange-funding-oi-observability/`.
- Current governance label is
  `research-only / brief_open; inventory_required_before_any_test`.
  The next allowed action is a public-data inventory sprint only: source,
  field, timestamp, coverage, and credential/account/API requirement mapping.
  No data pull, backtest, scanner, API integration, strategy implementation,
  runtime, account action, stage, commit, push, deploy, or PR is authorized.

ORH-009 public-data inventory update on 2026-05-24:

- Public source inventory is complete under
  `reports/orh-009-public-data-inventory-v1/`.
- Source inspection used public documentation pages and local repo artifacts
  only. It did not call exchange APIs, download historical data, run a
  backtest, use account credentials, or touch runtime/order-path code.
- Current governance label is
  `research-only / source_inventory_complete; protocol_freeze_required`.
  ORH-009 may continue only by freezing one source-validation protocol first:
  venue, fields, symbols, date window, timestamp alignment, duplication guard,
  and stop rules. If the selected route requires API access or a data download,
  it must wait for explicit Owner approval.

ORH-009-R1 source-validation update on 2026-05-24:

- Owner approved public data downloads without additional approval.
- ORH-009-R1 froze a Binance USD-M public archive source-validation protocol
  and downloaded a tiny `data.binance.vision` sample under
  `data/orh_009_r1_public/binance_archive_sample/`.
- Validation passed: one BTCUSDT April 2026 monthly `fundingRate` archive
  produced 90 rows, three daily `metrics` archives produced 288 rows each,
  SHA-256 checksums passed, required headers were present, and timestamps were
  parseable.
- Current governance label is
  `research-only / timestamp_alignment_passed_with_boundary_rule`.
  The no-outcome timestamp-alignment audit mapped 9 of 10 in-scope funding
  events to nearest-prior OI samples, with 9 exact timestamp matches, 1 initial
  boundary gap, and 0 lookahead errors. The next allowed action is freezing an
  ORH-009-R2 falsification design before any outcome test. It must include a
  warm-up/boundary exclusion rule and still must not compute returns, outcome
  windows, entries, exits, scanner outputs, strategy signals, runtime hooks, or
  trading advice.
- R1 artifacts live under `reports/orh-009-r1-source-validation-protocol/`.

Manual strategy matrix and L1 refinement update on 2026-05-24:

- A manual-plus-strategy candidate matrix produced three long-side and three
  short/risk-off research candidates under
  `reports/unattended-autonomous-sprint-2026-05-24-manual-strategy-matrix-v1/`.
- Strict frozen falsification then tested L1 relative underextension and S1
  EMA60 risk-off companion under same-parent controls. Both `btc_aligned_7d`
  L1 and S1 failed the strict control rule, so neither is a frozen-pass
  strategy candidate.
- L1 overlay refinement found one passing manual regime gate:
  `no_chop_no_shock` for `L_ALT_UNDEREXTENSION_BOUNCE + retest_60bp +
  fixed_8h`. It had 1304 events, mean return `0.700%`, matched-control mean
  `-0.290%`, positive-month rate `69.492%`, and positive same-parent control
  separation in sample, OOS, and stress. Evidence lives under
  `reports/l1-overlay-refinement-2026-05-24-v1/`.
- Current label: `research-only / L1 no_chop_no_shock overlay pass`.
  This does not authorize runtime, scanner, alert, watchlist, strategy
  implementation, paper/testnet/tiny-live/live, position/leverage advice,
  stage, commit, push, deploy, or PR.

L1 mechanism/harvest audit update on 2026-05-24:

- The L1 `no_chop_no_shock` event set was compared across available exit
  variants under `reports/l1-mechanism-harvest-audit-2026-05-24-v1/`.
- `fixed_8h` remained the best mean-return lens: 1304 events, mean return
  `0.700%`, median return `0.481%`, win rate `56.518%`, median MAE `-2.281%`,
  and median MFE `2.989%`.
- `tp2_sl2_24h` and `trail2_1p2_48h` reduced path risk but also reduced mean
  return to `0.133%` and `0.113%`, respectively, so they are not currently
  better harvest/protection rules.
- Fixed-8h failure taxonomy: clean wins `35.429%`, harvest-then-giveback
  `19.172%`, falling-knife `21.242%`, and small-noise `24.156%`.
- Current label: `research-only / L1 no_chop_no_shock fixed8h mechanism`.
  Next action is failure-filter audit with pre-entry features only, not runtime
  implementation, scanner, alert, watchlist, strategy packaging, paper/testnet,
  tiny-live/live, position/leverage advice, stage, commit, push, deploy, or PR.

L1 failure-filter audit update on 2026-05-24:

- A pre-entry failure-filter audit ran under
  `reports/l1-failure-filter-audit-2026-05-24-v1/`.
- Best internal filter: `btc7d_ge_0` within `no_chop_no_shock + fixed_8h`.
  It kept 1003 events, improved mean return from `0.700%` to `0.960%`, improved
  median return from `0.481%` to `0.643%`, and reduced falling-knife share from
  `21.242%` to `20.439%`.
- This is not a promotion. The filter overlaps the earlier
  `btc_aligned_no_chop_no_shock` overlay, which failed strict same-parent OOS
  control separation in the overlay audit. The next action must be an
  independent retest/control reconciliation, not implementation.
- Current label: `research-only / L1 filtered candidate needs independent
  retest`. No runtime, scanner, alert, watchlist, strategy packaging,
  paper/testnet/tiny-live/live, position/leverage advice, stage, commit, push,
  deploy, or PR is authorized.

L1 independent holdout retest update on 2026-05-24:

- The filtered L1 branch was retested on a bounded time-forward 2026-01 through
  2026-04 holdout using public Binance USD-M monthly OHLCV archives. Evidence
  lives under `reports/l1-independent-retest-2026-01-04-v1/`.
- `filtered_btc7d_ge_0` produced 31 events with mean return `-0.227%`, median
  return `-0.052%`, win rate `48.387%`, falling-knife share `22.581%`, and
  mean-after-top-month-removed `0.446%`. It beat the small `btc7d_lt_0`
  control on mean return but failed the minimum requirement that the filtered
  branch itself be positive on the independent holdout.
- Interpretation: stop promotion of `btc7d_ge_0` as a filter. Do not treat this
  as proof that the whole L1 mechanism is worthless; keep the broader
  `no_chop_no_shock` relative-underextension evidence as reserve research-only
  context pending a simpler baseline comparison.
- Current label: `research-only / reserve; stop filter promotion`. No runtime,
  scanner, alert, watchlist, strategy packaging, paper/testnet/tiny-live/live,
  position/leverage advice, stage, commit, push, deploy, or PR is authorized.

L1 baseline comparison update on 2026-05-24:

- A same-holdout baseline comparison ran under
  `reports/l1-baseline-comparison-2026-holdout-v1/`.
- The actual filtered L1 branch had 31 events, mean return `-0.227%`, median
  return `-0.052%`, and win rate `48.387%`.
- Same-symbol/same-month random 8h exposure had 1550 sampled rows, mean return
  `0.030%`, median return `-0.120%`, and win rate `47.355%`; actual filtered
  L1 underperformed this random-time baseline by `-0.257%` mean return.
- Same filtered-symbol buy-hold context was much worse at `-16.300%` mean
  return, so the L1 branch still avoided broad holdout downside, but it did
  not beat a simple random 8h exposure benchmark.
- Current label: `research-only / reserve_only_mixed_baseline`. Do not add
  more L1 filters next. If continuing market-alpha research, switch to ORH-007
  SQ02-R1 frozen falsification or another not-yet-falsified line rather than
  rescuing L1.

ORH-007 SQ02-R1 and public-universe update on 2026-05-24:

- SQ02-R1 frozen falsification ran under
  `reports/orh-007-sq02-r1-falsification-20260524/` using the frozen R0
  definition: low 72h range compression, 1h close below the prior 24h low, and
  close near the candle low, with a short-continuation lens.
- Three-symbol local R1 produced 110 24h de-duplicated events. The 24h median
  return was `0.219%`, estimated 12bp-cost median was `0.099%`, random
  same-symbol/month short control median was `-0.088%`, and sampled
  non-compression downside-break control median was `-0.109%`.
- Public-universe holdout retest ran under
  `reports/orh-007-sq02-public-universe-retest-20260524/`, using 2025-10
  through 2025-12 as compression-threshold warmup and 2026-01 through 2026-04
  as holdout. It produced 508 24h de-duplicated events across 35 symbols. The
  24h median return was `0.359%`, estimated 12bp-cost median was `0.239%`,
  random same-symbol/month short control median was `0.213%`, and sampled
  non-compression downside-break control median was `0.059%`.
- Failure-transition audit was directionally meaningful: public holdout events
  with no reclaim above the broken prior low within 12h had 24h median return
  `1.347%`, while reclaimed events had `-1.002%`.
- Current label: `research-only / continue_research_only_public_universe_pass`.
  This is still not a strategy, scanner, alert, watchlist, runtime candidate,
  paper/testnet/tiny-live/live permission, position/leverage advice, stage,
  commit, push, deploy, or PR authorization. The next action is synthesis only
  unless a separate promotion review is explicitly requested.

SQ02 manual semi-auto review design update on 2026-05-24:

- Owner clarified the goal is not full automation, but manual plus
  semi-automated research support.
- A docs-only design was written under
  `reports/sq02-manual-semi-auto-review-design-20260524/`. It defines a
  no-order human review workflow, descriptive packet schema, and review log
  template for historical or delayed public-data SQ02 packets.
- Allowed design intent: tools may prepare descriptive no-order packets from
  historical or delayed public OHLCV; humans review structure quality,
  no-reclaim context, known failure flags, and rationale.
- Forbidden: real-time scanner, alert, dashboard, live watchlist
  implementation, order path, exchange API, secrets, account data,
  paper/testnet/tiny-live/live, strategy implementation, position/leverage
  advice, stage, commit, push, deploy, or PR.
- Current label: `research-only / manual-semi-auto-design-only`. The next
  allowed action is an optional no-order historical packet sample; it must not
  include order, size, leverage, account, stop-loss, take-profit, or runtime
  fields.

SQ02 no-order packet sample update on 2026-05-24:

- A small historical no-order packet sample was generated under
  `reports/sq02-no-order-packet-sample-20260524/` from the existing public
  universe 24h de-duplicated SQ02 events.
- The sample has 18 packets and intentionally includes strong no-reclaim
  winners, reclaimed failures, April-2026 cases, and negative historical
  outcomes so the human review process is not trained only on favorable cases.
- Field validation found no forbidden order, account, sizing, stop-loss,
  take-profit, leverage, API, or exchange-account fields. Human review columns
  are blank by design.
- Current label: `research-only / human-review-dry-run-only`. The next action,
  if any, is manual review of a few rows by filling `review_status` and
  `human_rationale`; no automatic action or trading implication is authorized.

SQ02 readable review-card update on 2026-05-24:

- The original no-order packet CSV was too dense for human review, so a
  simplified review sheet and Markdown card view were generated under
  `reports/sq02-readable-review-cards-20260524/`.
- The simplified CSV keeps only human-decision fields: case type, symbol,
  event time, replay net 24h, 12h reclaim, compression-vs-threshold,
  break distance, close position, failure flags, review hint, review status,
  and rationale.
- The Markdown card view groups examples into clean no-reclaim and failure-risk
  cases so manual review can start from readable event cards instead of the
  raw research export.

SQ02 field utility and blind-review update on 2026-05-24:

- A field-utility audit was generated under
  `reports/sq02-field-utility-audit-20260524/`.
- Purpose of the simplified fields: `compression_vs_threshold`,
  `break_distance`, and `close_pos_1h` confirm the event really matches SQ02;
  `failure_flags` keeps bad contexts visible; `reclaim_12h` and
  `net_24h_replay` are replay-only answer fields, not event-time decision
  fields.
- Audit result: replay-only `no_12h_reclaim` was the strongest separator
  with median net 24h `1.227%` versus `-1.122%` for reclaimed events. Among
  event-time fields, deeper breaks above 60bp had median net 24h `1.013%`,
  while tiny breaks below 20bp had `-0.740%`; very tight compression had
  `0.543%`, while near-threshold compression had `-0.312%`.
- To reduce hindsight bias, blind review cards were generated under
  `reports/sq02-blind-review-cards-20260524/`. These hide 12h reclaim and
  historical outcome in the first-stage review sheet, with a separate replay
  answer key for later comparison.

SQ02 event-time priority update on 2026-05-24:

- An event-time priority audit was generated under
  `reports/sq02-event-time-priority-audit-20260524/`.
- It used only event-time visible fields: break distance, compression ratio,
  1h close position, and April-like context risk. Replay-only fields were used
  only for after-the-fact audit.
- High-priority review bucket: 99 events across 33 symbols, median net 24h
  `1.784%`, win rate `77.778%`, 12h reclaim rate `28.283%`, and April share
  `0.000%`. Normal priority had median `0.143%`; low priority had median
  `-0.744%`.
- A no-order triage design was written under
  `reports/sq02-no-order-triage-design-20260524/`.
- Priority blind review cards were generated under
  `reports/sq02-priority-blind-review-cards-20260524/`. They rank packets for
  human review while keeping 12h reclaim and replay outcome in a separate
  answer key. Priority is review ordering only; it is not an alert, watchlist,
  signal, strategy, order instruction, sizing rule, or leverage rule.

Semi-auto momentum synthesis update on 2026-05-24:

- A docs-only synthesis was written under
  `reports/semi-auto-momentum-synthesis-20260524/`.
- The synthesis reclassifies momentum into two roles: slow D1/4H momentum is
  useful as long-allowed / uncertain / no-long context, while fast 1h/4h
  breakout momentum remains parked as a primary trigger because prior tests
  failed OOS, stress, or standalone robustness checks.
- Current semi-auto ranking: SQ02 high-priority no-order packets first; slow
  momentum as background context second; ORH-001 funding/OI pressure as
  caution/no-long context third; EMA60 alt underextension and false downside
  reclaim remain reserve-only; EMA60 reject short remains reserve-only
  risk-off research.
- A simplified no-order semi-auto control sheet was generated from 508 existing
  SQ02 priority packets under
  `reports/semi-auto-momentum-synthesis-20260524/tables/`, with a card sample
  in `reports/semi-auto-momentum-synthesis-20260524/simplified_control_cards.md`.
  BTC slow-momentum context is included only as a review aid. No scanner,
  alert, watchlist, runtime, order path, paper/testnet/tiny-live/live,
  position, leverage, stage, commit, push, deploy, or PR is authorized.

Semi-auto control sheet readability audit update on 2026-05-25:

- A docs-only readability audit was written under
  `reports/semi-auto-control-sheet-readability-audit-20260525/`.
- Audit verdict: `continue_research_only_with_v2_copy_cleanup`.
- The simplified sheet passed the key safety checks: 508 rows, 13 columns,
  replay outcome and 12h reclaim absent from the first-pass sheet, answer key
  separate, and no order/account/sizing/leverage/stop/take-profit/scanner/
  alert/watchlist/runtime fields present.
- The main issue is language ambiguity. `slow_momentum_supportive` and
  `slow_momentum_no_long_risk` can be misread as direction advice in a SQ02
  downside-review packet. The next action is V2 copy cleanup: rename context
  to neutral BTC tape labels, move `replay_bucket` out of the first-pass sheet,
  and hide row-level BTC numeric context unless used in an audit-only file.
- ORH-007 remains `research-only / human-review-dry-run-only`; no manual
  labeling, scanner, alert, watchlist, runtime, order path,
  paper/testnet/tiny-live/live, position, leverage, stage, commit, push, deploy,
  or PR is authorized.

Personal leveraged campaign mainline update on 2026-05-25:

- Owner accepted the business direction as broadly correct and asked to fix it
  as the project mainline.
- The accepted chain is now documented in
  `docs/ops/personal-leveraged-campaign-mainline-v0.md` and
  `docs/adr/0008-personal-leveraged-campaign-business-chain.md`.
- Research tables and manual review sheets are subordinate aids. The future
  carrier must be a deterministic `StrategyContract`, followed by `TradeIntent`,
  `RiskOrderPlan`, execution lifecycle, campaign control, and withdrawal
  control.
- ORH-007 / `SQ02_DOWNSIDE_CONT_V0` is the first docs-only strategy-contract
  skeleton candidate because it has the strongest current semi-auto research
  chain. This does not authorize scanner, alert, watchlist, runtime, order path,
  paper/testnet/tiny-live/live, real account, position sizing, leverage, stage,
  commit, push, deploy, or PR.

## 8. Runtime Boundary Reminder

Live-safe, OwnerGate, StrategySignalV2, runtime profiles, exchange gateway,
execution orchestrator, order lifecycle, sizing, and real account operations
belong to the runtime safety zone.

Local experiments may be designed or coded later if disabled-by-default and
reported clearly. Nothing in this board authorizes real trading or direct
research-to-order wiring.
