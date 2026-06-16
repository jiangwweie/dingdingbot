# Strategy Research Document Map

Status: ACTIVE_V3_DOCUMENT_MAP
Last updated: 2026-06-16

## Start Here

Use these documents as the stable entry points for the strategy research line:

| Document | Role |
| --- | --- |
| `STRATEGY_RESEARCH_GUIDE.md` | Current rules for strategy research, evidence grading, leverage boundaries, lifecycle status, and handoff shape. |
| `p0-p1-p2-goal-mode-plan.md` | Active goal-mode execution plan for P0 handoff hardening, P1 next handoff conversion, and P2 strategy-pool expansion. |
| `p0-handoff-hardening-matrix-20260616.md` | P0 matrix for the 5 existing StrategyGroup handoff packs. |
| `p1-next-handoff-queue-20260616.md` | P1 queue for `VCB-001`, `RSR-001`, `NLPD-001`, `LCF-001`, and `MDS-001`. |
| `lcf-liquidation-cascade-requiredfacts-design-20260616.md` | Research-only RequiredFacts design packet for `LCF-001`; not a handoff and not runtime intake. |
| `p2-strategy-pool-expansion-queue-20260616.md` | P2 queue for pool expansion, revival, and parked-strategy governance. |
| `strategy-window-cognition-20260616.md` | Current cognition for project return semantics, evidence quality, and strategy-pool expansion. |
| `strategy-cabinet/README.md` | Strategy Cabinet purpose and non-goals. |
| `strategy-cabinet/strategy-cabinet.md` | Human-readable Strategy Cabinet, listing active, parked, blocked, and handoff-ready strategy semantics. |
| `strategy-cabinet/strategy-cabinet.json` | System-readable Strategy Cabinet for future validators, main-control intake, or Strategy Picker preparation. |
| `strategy-group-handoffs/main-control-handoff-index.md` | Main-control entry point for the first five StrategyGroup handoff packs. |
| `candidate-packets/candidate-packet-index.md` | Research packet index for all V3 candidate packets. |
| `activation-disable-boundary-map.md` | Activation, disable, parking, and revival boundaries. |
| `negative-evidence.md` | Failed, downgraded, biased, cost-sensitive, or parked evidence ledger. |

## Current Authority

The current strategy-research authority is **Strategy Research v3**.

V3 is a research program for **small-capital, regime-specific, right-tail
strategy candidates** over crypto plus Binance-listed TradFi-like instruments
when reproducible public data exists. It does not seek an always-on, full-year
stable alpha strategy. It seeks strategy candidates that can produce large
asymmetric returns in identifiable market states, with explicit activation,
disable, failure, and revival boundaries.

Owner direction on 2026-06-13 and 2026-06-14 explicitly keeps
Binance-listed U.S. equity-like instruments and precious-metal / commodity
instruments inside the research universe. Their short history is acceptable
for 1h discovery and event studies, but it blocks promotion until product-risk,
liquidity, session-gap, mark/funding, and margin facts are attached.

## Active V3 Documents

| Document | Role |
| --- | --- |
| `STRATEGY_RESEARCH_GUIDE.md` | Current rules for strategy research, evidence grading, leverage boundaries, lifecycle status, and handoff shape. |
| `p0-p1-p2-goal-mode-plan.md` | Active P0 / P1 / P2 goal-mode execution plan. |
| `p0-handoff-hardening-matrix-20260616.md` | P0 handoff hardening matrix for `MPG-001`, `FBS-001`, `TEQ-001`, `PMR-001`, and `SOR-001`. |
| `p1-next-handoff-queue-20260616.md` | P1 next handoff queue for `VCB-001`, `RSR-001`, `NLPD-001`, `LCF-001`, and `MDS-001`. |
| `lcf-liquidation-cascade-requiredfacts-design-20260616.md` | `LCF-001` liquidation-cascade RequiredFacts design packet and facts-missing no-signal shape. |
| `p2-strategy-pool-expansion-queue-20260616.md` | P2 strategy-pool expansion and revival queue. |
| `strategy-window-cognition-20260616.md` | Current cognition for project return semantics, evidence quality, and strategy-pool expansion. |
| `strategy-cabinet/README.md` | Strategy Cabinet purpose and non-goals. |
| `strategy-cabinet/strategy-cabinet.md` | Human-readable Strategy Cabinet, listing active, parked, blocked, and handoff-ready strategy semantics. |
| `strategy-cabinet/strategy-cabinet.json` | System-readable Strategy Cabinet for future validators, main-control intake, or Strategy Picker preparation. |
| `strategy-research-v3-goal.md` | V3 objective, scope, non-goals, acceptance model. |
| `strategy-research-v3-goal-completion-audit.md` | Requirement-by-requirement completion audit for the active Strategy Research v3 main-control handoff goal. |
| `strategy-group-experimental-candidate-admission.md` | Owner correction for converting research into experimental StrategyGroup candidates; known flaws may be acceptable when bounded, while execution-chain mutation remains out of scope. |
| `strategy-group-handoffs/README.md` | Strategy Group Handoff Pack contract for main-control consumption; defines required fields, packet semantics, and non-execution boundaries. |
| `strategy-group-handoffs/main-control-handoff-index.md` | Main-control entry point for the first five StrategyGroup handoff packs, including verification commands and boundary proof. |
| `strategy-group-handoffs/handoff-validation-report.md` | Validation report proving the first five handoff JSON packs satisfy the main-control field contract. |
| `strategy-group-handoffs/main-control-task-card.md` | Main-control task card for reviewing and consuming StrategyGroup handoff batch 1. |
| `strategy-group-handoffs/MPG-001/handoff.md` | Human-readable `MPG-001` Momentum Persistence StrategyGroup handoff pack for main-control review. |
| `strategy-group-handoffs/MPG-001/handoff.json` | System-readable `MPG-001` handoff contract with supported symbols, signal-ready rule, RequiredFacts, risk proposal, hard stops, and sample packets. |
| `strategy-group-handoffs/FBS-001/handoff.md` | Human-readable `FBS-001` Funding Basis Stress handoff pack for main-control review. |
| `strategy-group-handoffs/FBS-001/handoff.json` | System-readable `FBS-001` handoff contract with funding-stress signal semantics, RequiredFacts, risk proposal, hard stops, and sample packets. |
| `strategy-group-handoffs/TEQ-001/handoff.md` | Human-readable `TEQ-001` Tokenized Equity Momentum handoff pack for main-control review. |
| `strategy-group-handoffs/TEQ-001/handoff.json` | System-readable `TEQ-001` handoff contract with equity-like momentum semantics, RequiredFacts, risk proposal, hard stops, and sample packets. |
| `strategy-group-handoffs/PMR-001/handoff.md` | Human-readable `PMR-001` Precious Metal Regime Overlay handoff pack for main-control review. |
| `strategy-group-handoffs/PMR-001/handoff.json` | System-readable `PMR-001` handoff contract with metal role-split semantics, RequiredFacts, risk proposal, hard stops, and sample packets. |
| `strategy-group-handoffs/SOR-001/handoff.md` | Human-readable `SOR-001` Session Opening-Range Breakout handoff pack for main-control review. |
| `strategy-group-handoffs/SOR-001/handoff.json` | System-readable `SOR-001` handoff contract with session-structure semantics, RequiredFacts, risk proposal, hard stops, and sample packets. |
| `strategy-group-handoffs/VCB-001/handoff.md` | Human-readable observe-only `VCB-001` Volatility Compression Breakout handoff draft. |
| `strategy-group-handoffs/VCB-001/handoff.json` | System-readable observe-only `VCB-001` handoff contract with true-breakout classifier semantics, RequiredFacts, hard stops, and sample packets. |
| `strategy-group-handoffs/RSR-001/handoff.md` | Human-readable observe-only `RSR-001` Relative Strength Rotation scorer handoff draft. |
| `strategy-group-handoffs/RSR-001/handoff.json` | System-readable observe-only `RSR-001` scorer handoff contract with TEQ support semantics, RequiredFacts, hard stops, and sample packets. |
| `strategy-group-handoffs/NLPD-001/handoff.md` | Human-readable observe-only `NLPD-001` new-listing / event-study handoff draft. |
| `strategy-group-handoffs/NLPD-001/handoff.json` | System-readable observe-only `NLPD-001` event-study handoff contract with low-history semantics, RequiredFacts, hard stops, and sample packets. |
| `document-governance-v3.md` | Document authority, supersession rules, and old-document handling. |
| `owner-direction-log.md` | Owner strategy-research instructions that change search space, evaluation semantics, or evidence governance. |
| `community-research-plan.md` | GitHub, Freqtrade, QuantConnect, Reddit/forum, and official-data intake plan. |
| `community-source-intake-20260613.md` | First V3 source-intake batch from official, open-source, and forum sources. |
| `community-source-intake-batch2-20260613.md` | Second V3 source-intake batch for leverage callbacks, controller/executor boundaries, vectorized-scan discipline, and high-leverage community hypotheses. |
| `community-source-intake-batch3-20260613.md` | Third V3 source-intake batch for relative-strength / sector-rotation semantics and `RSR-001`. |
| `community-source-intake-batch4-20260613.md` | Fourth V3 source-intake batch for session opening-range breakout semantics and `SOR-001`. |
| `community-source-intake-batch5-20260614.md` | Fifth V3 source-intake batch for SOR classifier, stop/exit, and controller/executor boundary semantics. |
| `community-source-intake-batch6-20260614.md` | Sixth V3 source-intake batch for funding-stress semantics and `FBS-001` direct replay. |
| `community-source-intake-batch7-20260614.md` | Seventh V3 source-intake batch for VWAP pullback/reclaim and rejection semantics, producing `VPC-001`. |
| `community-source-intake-batch8-20260614.md` | Eighth V3 source-intake batch for session gap continuation/fade semantics, producing `SGC-001`. |
| `community-source-intake-batch9-20260614.md` | Ninth V3 source-intake batch for Fair Value Gap / price-imbalance semantics, producing `FVG-001`. |
| `community-source-intake-batch10-20260614.md` | Tenth V3 source-intake batch for inside-bar / NR7 compression-breakout semantics, producing `IBB-001`. |
| `community-source-intake-batch11-20260614.md` | Eleventh V3 source-intake batch for Keltner/Bollinger squeeze-release breakout semantics, producing `KSB-001`. |
| `community-source-intake-batch12-20260614.md` | Twelfth V3 source-intake batch for SuperTrend / ATR trend-following semantics, producing `STF-001`. |
| `community-source-intake-batch13-20260614.md` | Thirteenth V3 source-intake batch for MACD histogram zero-cross / ignition semantics, producing `MHI-001`. |
| `community-source-intake-batch14-20260614.md` | Fourteenth V3 source-intake batch for ADX / DMI directional-movement ignition semantics, producing `DMI-001`. |
| `community-source-intake-batch15-20260614.md` | Fifteenth V3 source-intake batch for RSI regime-reclaim and failure semantics, producing `RSI-001`. |
| `community-source-intake-batch16-20260614.md` | Sixteenth V3 source-intake batch for CCI trend escape / failure semantics and explicit 2026 Binance TradFi U.S. equity / precious-metal universe confirmation, producing `CCI-001`. |
| `community-source-intake-batch17-20260614.md` | Seventeenth V3 source-intake batch for Aroon trend-emergence semantics, producing `AROON-001` as support/negative evidence. |
| `community-source-intake-batch18-20260614.md` | Eighteenth V3 source-intake batch for Williams %R percent-range reclaim/failure semantics, producing `WPR-001`. |
| `community-source-intake-batch19-20260614.md` | Nineteenth V3 source-intake batch for ROC momentum acceleration/exhaustion semantics, producing `ROC-001`. |
| `community-source-intake-batch20-20260614.md` | Twentieth V3 source-intake batch for MFI money-flow semantics, producing `MFI-001`. |
| `community-source-intake-batch21-20260614.md` | Twenty-first V3 source-intake batch for OBV volume-flow confirmation semantics, producing `OBV-001`. |
| `community-source-intake-batch22-20260614.md` | Twenty-second V3 source-intake batch for CMF accumulation/distribution semantics, producing `CMF-001`. |
| `community-source-intake-batch23-20260614.md` | Twenty-third V3 source-intake batch for PVO volume-expansion confirmation semantics, producing `PVO-001` as support/negative evidence. |
| `community-source-intake-batch24-20260614.md` | Twenty-fourth V3 source-intake batch for PPO percentage-price momentum semantics, producing `PPO-001` as P1 right-tail review evidence. |
| `community-source-intake-batch25-20260614.md` | Twenty-fifth V3 source-intake batch for TSI smoothed-momentum semantics, producing `TSI-001` as window-revival evidence. |
| `community-source-intake-batch26-20260614.md` | Twenty-sixth V3 source-intake batch grouping WPR, MFI, PPO, TSI, MACD histogram, and ADX/DMI into `MPG-001` momentum-persistence strategy-group evidence. |
| `community-source-intake-batch36-20260614.md` | Thirty-sixth V3 source-intake batch for Know Sure Thing multi-cycle momentum semantics, producing `KST-001` as positive-persistence window-revival / negative evidence. |
| `community-source-intake-batch37-20260614.md` | Thirty-seventh V3 source-intake batch for Mass Index range-expansion reversal semantics, producing `MASS-001` as P1 right-tail review evidence. |
| `community-source-intake-batch38-20260614.md` | Thirty-eighth V3 source-intake batch for Elder Force Index price-volume force semantics, producing `EFI-001` as P1 right-tail review evidence for negative-force exhaustion reversal. |
| `community-source-intake-batch39-20260614.md` | Thirty-ninth V3 source-intake batch for Fisher Transform normalized-price reversal/persistence semantics, producing `FISH-001` as window-revival evidence. |
| `community-source-intake-batch40-20260614.md` | Fortieth V3 source-intake batch for Relative Vigor Index open-close vigor semantics, producing `RVI-001` as PMR / short-cross P1 review evidence with broad RVI blockers. |
| `community-source-intake-batch41-20260614.md` | Forty-first V3 source-intake batch for Chaikin Oscillator ADL momentum semantics, producing `CHO-001` as equity/ETF accumulation-trend window-revival evidence. |
| `community-source-intake-batch42-20260614.md` | Forty-second V3 source-intake batch for Chaikin Volatility high-low range expansion semantics, producing `CHV-001` as equity/ETF volatility-expansion window-revival evidence. |
| `community-source-intake-batch43-20260614.md` | Forty-third V3 source-intake batch for Awesome Oscillator midpoint momentum semantics, producing `AO-001` as support/negative revival evidence over Binance 2026 equity and metal futures. |
| `community-source-intake-batch44-20260614.md` | Forty-fourth V3 source-intake batch for Heikin-Ashi smoothed-candle trend semantics, producing `HAT-001` as window-revival / negative evidence over Binance 2026 equity and metal futures. |
| `community-source-intake-batch45-20260614.md` | Forty-fifth V3 source-intake batch refreshing Donchian breakout semantics for `DCB-001` over Binance 2026 TradFi equity/ETF and precious-metal 1h futures; records the TradFi transfer as negative/revival evidence. |
| `community-source-intake-batch46-20260614.md` | Forty-sixth V3 source-intake batch for ATR / True Range expansion breakout semantics, producing `AEB-001` as short-window TEQ revival evidence over Binance 2026 equity and metal futures. |
| `community-hypothesis-ledger.md` | Hypothesis ledger for community and open-source strategy ideas. |
| `community-archetypes/freqtrade-community-archetype-index.md` | Local Freqtrade strategy archetype index from `/Users/jiangwei/Documents/github/quant-strategies`. |
| `community-archetypes/local-external-source-index.md` | Read-only source index for local external repos and Chinese strategy/factor documents under `/Users/jiangwei/Documents/github`. |
| `community-archetypes/open-source-framework-intake.md` | Open-source framework intake for Freqtrade, Hummingbot, Jesse, and vectorbt as hypothesis/tooling sources. |
| `open-source-semantic-shortlist/open-source-semantic-shortlist.md` | Bounded open-source semantic shortlist for trend, breakout, momentum, pullback, range, FBS overlay, and vectorized-scan discipline. |
| `oss-fbs-downshift-overlay/oss-fbs-downshift-overlay-summary.md` | Funding, liquidity, mark-deviation, path-risk, and false-breakout downshift overlay for levered candidates. |
| `oss-rtf-strict-trend-runner/oss-rtf-strict-trend-runner-summary.md` | Strict EMA/ADX trend-runner replay for `OSS-RTF-001`, testing whether cleaner runner exits revive RTF under 2x windows. |
| `oss-thr-momentum-ignition/oss-thr-momentum-ignition-summary.md` | Momentum ignition replay for `OSS-THR-001`, comparing crypto high-beta and Binance 2026 equity-like symbols under slot M2M stress. |
| `oss-thr-post-burst-disable/oss-thr-post-burst-disable-summary.md` | Post-burst disable replay for `OSS-THR-001`, testing overextension, near-high participation, crypto, and Binance TradFi 2026 support lanes. |
| `oss-vcb-true-false-breakout/oss-vcb-true-false-breakout-summary.md` | True/false breakout replay for `OSS-VCB-001`, separating profitable follow-through from false-breakout disable evidence. |
| `oss-vcb-pre-entry-classifier/oss-vcb-pre-entry-classifier-summary.md` | Pre-entry classifier replay for `OSS-VCB-001`, testing fixed closed-candle filters before true-breakout revival. |
| `oss-vcb-volume-compression-cost-m2m/oss-vcb-volume-compression-cost-m2m-summary.md` | Cost and event-slot M2M stress for the narrow `OSS-VCB-001` volume-compression lane. |
| `oss-crr-pullback-reclaim/oss-crr-pullback-reclaim-summary.md` | Pullback/reclaim expansion replay for `OSS-CRR-001`, testing whether larger closed-candle capitulation-rebound samples revive CRR. |
| `oss-rbr-calm-range/oss-rbr-calm-range-summary.md` | Calm-range boundary-fade replay for `OSS-RBR-001`, testing whether stricter range filters revive RBR/CGR semantics. |
| `lsr-unbiased-rewrite/lsr-unbiased-rewrite-summary.md` | Prefix-only shifted prior-extreme rewrite replay for `LSR-001`, preserving a right-tail window while proving full-sequence disable facts are required. |
| `lsr-disable-classifier/lsr-disable-classifier-summary.md` | Signal-time disable classifier replay for `LSR-001`, preserving `lsr_short_upper_range` as a short-side window-revival lead while broad LSR remains failed. |
| `nlpd-new-listing-event-study/nlpd-new-listing-event-study-summary.md` | First low-history event study for `NLPD-001`, using Binance 2026 listing-hint symbols and delayed next-open labels. |
| `bstocks-event-study-refresh/bstocks-event-study-refresh-summary.md` | bStocks-only low-history event-study refresh for first-window continuation, delayed fade, and spot-short executability boundaries. |
| `universe-expansion/binance-extended-universe-manifest.md` | Binance 2026 bStocks, TradFi equity perpetuals, and precious-metal universe manifest; low-history symbols stay research-only with explicit product-risk facts. |
| `universe-expansion/tradfi-asset-universe-20260614.md` | Current Binance USD-S TradFi asset scope; separates `87` equity/ETF perps, `4` precious-metal perps, `1` industrial-metal context perp, and `1` tokenized-gold perp context into replay-readiness lanes. |
| `universe-expansion/current-binance-tradfi-availability-20260614.md` | Current public Binance USD-S `exchangeInfo` availability check for the `93` local TradFi research symbols; separates historical cached 1h research evidence from current symbol visibility before promotion. |
| `hat-stop-reslot/hat-stop-reslot-summary.md` | Fixed-stop re-slot replay for review-critical `HAT-001` classifier pools; preserves right-tail windows but confirms drawdown remains unresolved. |
| `regime-right-tail-evaluation-policy.md` | Regime-first evaluation policy and candidate grading. |
| `right-tail-window-mining-plan.md` | Rolling-window, symbol-attribution, and regime-tagging plan. |
| `strategy-candidate-pool-v2.md` | Candidate pool organized by regime and payoff profile. |
| `activation-disable-boundary-map.md` | Activation, disable, parking, and revival boundary map. |
| `v3-validation-backlog.md` | Concrete validation tasks connecting hypotheses to evidence work. |
| `strategy-research-v3-completion-audit.md` | Requirement-by-requirement completion audit for the v3 reset. |
| `window-mining/right-tail-window-mining-summary.md` | First right-tail window mining report over local evidence. |
| `regime-attribution/regime-attribution-summary.md` | First spot/funding/premium attribution for right-tail windows. |
| `additional-window-mining/additional-right-tail-summary.md` | Additional closed-candle mining for DCB, THR, and CRR candidates. |
| `portfolio-constrained-replay/portfolio-constrained-summary.md` | First max-position and cost/slippage constrained replay for DCB, THR, and CRR. |
| `path-risk-replay/path-risk-summary.md` | First path-risk, MAE, stop, and raw liquidation proxy replay for DCB, THR, and CRR. |
| `mark-to-market-replay/mark-to-market-summary.md` | First slot-based 1x/2x/3x/5x mark-to-market equity replay for DCB, THR, and CRR. |
| `freqtrade-wallet-replay/freqtrade-wallet-summary.md` | Closed-trade realized-equity window replay for RTF and VCB Freqtrade evidence. |
| `local-external-semantic-replay/local-external-semantic-replay-summary.md` | Closed-candle 1h event replay for local external-source semantic variants `DMA-001` and `CGR-001`. |
| `local-external-m2m-replay/local-external-m2m-summary.md` | Slot-based mark-to-market replay for `DMA-001` and `CGR-001`, including accepted/rejected events and 1x/2x/3x/5x stress. |
| `candidate-packets/candidate-packet-index.md` | Packet index for all active V3 candidate packets. |
| `candidate-packets/DCB-001-donchian-expansion-breakout-packet.md` | Donchian expansion breakout right-tail packet. |
| `candidate-packets/THR-001-theme-high-beta-rotation-packet.md` | Theme/high-beta rotation right-tail packet. |
| `candidate-packets/CRR-001-capitulation-rebound-packet.md` | Capitulation rebound keep-testing packet. |
| `candidate-packets/FBS-001-funding-basis-stress-packet.md` | Data-first funding/basis/OI stress packet for leverage overlay research. |
| `btpc-derivatives-reviewability/btpc-derivatives-reviewability-summary.md` | BTPC derivatives reviewability audit proving funding/premium coverage but blocking promotion on missing historical OI, long/short ratio, top-trader positioning, and real margin facts. |
| `fbs-funding-stress-reversal/fbs-funding-stress-reversal-summary.md` | Direct funding-stress replay for `FBS-001`; TEQ negative funding becomes a P1 squeeze candidate while positive-funding short reversal becomes negative/redesign evidence. |
| `fbs-funding-stress-robustness/fbs-funding-stress-robustness-summary.md` | Robustness, concentration, leave-one-symbol, monthly attribution, and stricter signal-time filter audit for the FBS TEQ negative-funding squeeze lead. |
| `candidate-packets/LSR-001-liquidity-sweep-reversal-packet.md` | Liquidity sweep/reclaim window-revival packet after the unbiased closed-candle rewrite. |
| `candidate-packets/TEQ-001-tokenized-equity-momentum-packet.md` | Data-first Binance bStocks and TradFi equity/ETF momentum packet. |
| `candidate-packets/RSR-001-relative-strength-rotation-packet.md` | Relative-strength rotation window-revival packet over Binance 2026 TradFi equity perpetuals. |
| `candidate-packets/SOR-001-session-opening-range-breakout-packet.md` | Session opening-range breakout packet over Binance 2026 TradFi equity and metal perpetuals. |
| `candidate-packets/PMR-001-precious-metal-regime-overlay-packet.md` | Data-first precious-metal token and TradFi commodity overlay packet. |
| `candidate-packets/MRS-001-metal-relative-spread-packet.md` | Parked PMR-adjacent metal relative-spread packet; current simple metal-relative rules are negative/support-only evidence. |
| `candidate-packets/VPC-001-vwap-pullback-continuation-packet.md` | VWAP pullback/rejection window-revival packet; one 90d short-side window clears 100% 2x, but full curve and drawdown block promotion. |
| `candidate-packets/SGC-001-session-gap-continuation-fade-packet.md` | Session gap continuation/fade window-revival packet; gap-up continuation clears one 90d 2x window but full sequence remains negative. |
| `candidate-packets/FVG-001-fair-value-gap-packet.md` | Fair-value-gap / price-imbalance window-revival packet; bull continuation clears one 90d 2x window but full sequence and retest drawdown block promotion. |
| `candidate-packets/IBB-001-inside-nr7-breakout-packet.md` | Inside-bar / NR7 compression-breakout support/revival packet; NR7 long clears one 90d 2x window but full sequence and drawdown block promotion. |
| `candidate-packets/KSB-001-keltner-bollinger-squeeze-packet.md` | Keltner/Bollinger squeeze-release negative/revival packet; no row clears 100% best-90d 2x, but it preserves compression-release vocabulary and TradFi category attribution. |
| `candidate-packets/STF-001-supertrend-followthrough-packet.md` | SuperTrend / ATR trend-following support/negative packet; flip rows are clean but below right-tail threshold, while continuation rows are full-curve unsafe. |
| `candidate-packets/MHI-001-macd-histogram-ignition-packet.md` | MACD histogram ignition P1 right-tail review packet; zero-cross long clears positive full 2x and a large best-90d 2x window, but drawdown and category attribution block promotion. |
| `candidate-packets/DMI-001-adx-directional-ignition-packet.md` | ADX / DMI directional ignition P1 right-tail review packet; trend-strength long clears positive full 2x and large best-90d 2x, while short and metal rows block promotion. |
| `candidate-packets/RSI-001-regime-reclaim-packet.md` | RSI regime-reclaim window-revival packet; midline reclaim has a large best-90d 2x window, but full curve and category attribution block promotion. |
| `candidate-packets/CCI-001-trend-escape-packet.md` | CCI trend escape / failure window-revival packet; precious-metal +100 failure short has positive full 2x and a 100%+ best-90d 2x window, but drawdown and TradFi off-hour facts block promotion. |
| `candidate-packets/AROON-001-trend-emergence-packet.md` | Aroon trend-emergence support/negative packet; broad Aroon rows fail and no rule clears a 100%+ best-90d 2x gate. |
| `candidate-packets/WPR-001-williams-percent-range-packet.md` | Williams %R percent-range right-tail review packet; overbought persistence long has positive full 2x and a 100%+ best-90d 2x window, while generic reversal rows are negative. |
| `candidate-packets/ROC-001-rate-of-change-packet.md` | Rate-of-change acceleration window-revival packet; acceleration long has a 100%+ best-90d 2x window, but full curve and drawdown fail. |
| `candidate-packets/MFI-001-money-flow-index-packet.md` | Money Flow Index right-tail review packet; overbought persistence long has positive full 2x and a 100%+ best-90d 2x window, while generic reversal rows are negative. |
| `candidate-packets/OBV-001-volume-flow-packet.md` | On-Balance Volume window-revival packet; trend-confirmed long has a large best-90d 2x window, but full curve and drawdown fail. |
| `candidate-packets/CMF-001-chaikin-money-flow-packet.md` | Chaikin Money Flow window-revival packet; accumulation-trend long has a large best-90d 2x window, but full curve and drawdown fail. |
| `candidate-packets/PVO-001-percentage-volume-oscillator-packet.md` | Percentage Volume Oscillator support/negative packet; zero-reclaim long is positive full 2x but no rule clears a 100%+ best-90d 2x gate. |
| `candidate-packets/PPO-001-percentage-price-oscillator-packet.md` | Percentage Price Oscillator right-tail review packet; momentum-persistence long has positive full 2x and a 300%+ best-90d 2x window, while generic PPO rows are negative. |
| `candidate-packets/TSI-001-true-strength-index-packet.md` | True Strength Index classifier-review packet; generic momentum-persistence has large windows but fails full sequence, while `tsi_long_equity_tsi_rising` improves to a P1 classifier candidate. |
| `candidate-packets/KST-001-know-sure-thing-packet.md` | Know Sure Thing window-revival packet; positive persistence clears one 100%+ best-90d 2x window, while full sequence and generic cross/short rows fail. |
| `candidate-packets/MASS-001-mass-index-reversal-packet.md` | Mass Index right-tail review packet; long reversal and range-expansion continuation rows clear right-tail gates, while direction-context, decay, concentration, fill/product-risk, and real margin facts block promotion. |
| `candidate-packets/EFI-001-elder-force-index-packet.md` | Elder Force Index right-tail review packet; negative-force exhaustion reversal clears full/best-window gates, while simple impulse/distribution rows and high leverage fail. |
| `candidate-packets/FISH-001-fisher-transform-packet.md` | Fisher Transform window-revival packet; candidate pool has a 180%+ best-90d 2x and 319%+ best-30d 2x window, while full sequence and high leverage fail. |
| `candidate-packets/RVI-001-relative-vigor-packet.md` | Relative Vigor Index right-tail review packet for PMR / short-cross semantics; precious-metal category and short-cross branch work, while broad RVI and TEQ attribution fail. |
| `candidate-packets/CHO-001-chaikin-oscillator-packet.md` | Chaikin Oscillator window-revival packet; equity/ETF accumulation-trend windows work at 30d/60d, while broad CHO, 90d, full sequence, and high leverage fail. |
| `candidate-packets/CHV-001-chaikin-volatility-packet.md` | Chaikin Volatility window-revival packet; equity/ETF range-expansion long clears 30d/60d/90d windows, while full sequence and drawdown fail. |
| `candidate-packets/AO-001-awesome-oscillator-packet.md` | Awesome Oscillator support/negative revival packet; zero-cross long is clean but below the 100%+ best-90d 2x gate, while acceleration long fails full sequence and drawdown. |
| `candidate-packets/HAT-001-heikin-ashi-trend-packet.md` | Heikin-Ashi classifier / stop-reslot packet; clean-combo and regular-proxy rows preserve right-tail evidence but drawdown remains unresolved. |
| `hat-decay-asset-role-classifier/hat-decay-asset-role-classifier-summary.md` | HAT raw-pool classifier replay; clean-combo equity weekday branch reaches full 2x `90.789324%` and best-90d 2x `789.739339%`, but DD remains unresolved. |
| `strategy-groups/MPG-001-momentum-persistence-group.md` | Momentum-persistence strategy-group packet for WPR, MFI, PPO, TSI, MHI, and DMI; group-pool classifier replay preserves right-tail but blocks promotion on drawdown and margin/fill facts. |
| `candidate-packets/NLPD-001-new-listing-price-discovery-packet.md` | Low-history Binance 2026 listing event-study packet for new-listing price discovery. |
| `candidate-packets/DMA-001-dual-ma-trend-exit-packet.md` | Dual-MA trend and partial-exit revival packet from local external-source semantics. |
| `candidate-packets/CGR-001-capped-grid-range-reversion-packet.md` | Capped grid/range reversion revival packet from local external-source semantics. |
| `candidate-packets/EA-001-energy-alignment-screener-packet.md` | Energy-alignment screener window-only replay packet; strong right-tail windows but full-curve wipeout and high-leverage negative vocabulary. |
| `external-data/binance-futures-context-20260613/futures-context-summary.md` | Public read-only Binance futures OI and long/short snapshot. |
| `external-data/binance-extended-universe-1h-20260613/extended-universe-1h-snapshot-summary.md` | Public read-only Binance 1h OHLCV, mark, and funding snapshot for TEQ/PMR. |
| `extended-universe-us-equity-metals-refresh-20260613.md` | Current 102-symbol U.S. equity / precious-metal refresh; supersedes older 33-symbol TEQ/PMR counts for current interpretation. |
| `leverage-aware-candidate-shortlist/leverage-aware-candidate-shortlist-summary.md` | Cross-candidate leverage-aware shortlist separating slot M2M, signal/reference, window-envelope, raw-pool reslot, and overlay evidence models. |
| `extended-universe-window-scan/extended-universe-window-scan-summary.md` | First-pass 1h right-tail window scan for TEQ/PMR extended universe. |
| `extended-universe-margin-stress/extended-universe-margin-stress-summary.md` | Path-risk, mark-deviation, and liquidation-proxy stress for TEQ/PMR windows. |
| `extended-universe-role-analysis/extended-universe-role-concentration-summary.md` | Concentration, basket-confirmation, session-bucket, and role analysis for TEQ/PMR. |
| `extended-universe-regime-leverage/extended-universe-regime-leverage-summary.md` | Low-history, 1h correlation, session context, and leverage-gate review for TEQ/PMR. |
| `extended-universe-leverage-envelope/teq-pmr-leverage-envelope-summary.md` | TEQ/PMR leverage envelope converting proxy liquidation, buffer, mark-deviation, funding, and liquidity facts into allow/downshift/disable research labels. |
| `extended-universe-session-leverage/extended-universe-session-leverage-summary.md` | Session-bucket leverage audit splitting TEQ/PMR evidence into U.S. regular-proxy, weekday off-hours, and weekend starts. |
| `tradfi-session-transfer-replay/tradfi-session-transfer-summary.md` | Closed-candle session-transfer replay over Binance 2026 TradFi equity and precious-metal perps; adds PMR regular-session short as a P1 candidate and TEQ momentum as session-specific revival evidence. |
| `session-transfer-decay-classifier/session-transfer-decay-classifier-summary.md` | Signal-time decay/disable classifier replay over session-transfer raw pools; upgrades TEQ regular stronger momentum to P1 drawdown-unresolved and keeps PMR volume-confirmed short as P1 drawdown-unresolved. |
| `session-transfer-stop-risk/session-transfer-stop-risk-summary.md` | Accepted-only fixed-stop proxy over session-transfer classifier rows; shows stop-risk tradeoff and keeps TEQ/PMR candidates promotion-blocked until fill/gap and re-slot evidence exists. |
| `session-transfer-stop-reslot/session-transfer-stop-reslot-summary.md` | Raw-pool fixed-stop re-slot replay; shows simple fixed stops plus freed-capital re-slot do not yet solve TEQ/PMR stop versus right-tail tradeoff. |
| `extended-universe-basket-role-split/teq-pmr-basket-role-split-summary.md` | TEQ single-name versus basket split and PMR XAG-led role split over Binance 2026 equity and metal symbols. |
| `extended-universe-refresh-readiness/teq-pmr-refresh-readiness-summary.md` | Owner-amplified TEQ/PMR refresh-readiness, leverage gate, and next replay queue for Binance 2026 equity-like and metal symbols. |
| `teq-long-cluster-momentum-replay/teq-long-cluster-momentum-summary.md` | Prefix-safe closed-candle TEQ long-cluster momentum replay; positive support evidence but not a 100%+ right-tail promotion result. |
| `teq-prefix-classifier-sweep/teq-prefix-classifier-sweep-summary.md` | Bounded TEQ prefix-safe classifier sweep over 32 interpretable rules; no 100%+ 90d 2x classifier found, but 5 support classifiers remain keep-testing evidence. |
| `teq-relative-strength-rotation/teq-relative-strength-rotation-summary.md` | Relative-strength / sector-rotation replay over Binance 2026 TradFi equity perpetuals; creates `RSR-001` as a P1 window-revival packet. |
| `rsr-decay-disable-classifier/rsr-decay-disable-classifier-summary.md` | Signal-time rank-priority reslot and decay classifier replay for `RSR-001`; upgrades one row to P1 decay-classifier candidate while preserving promotion blockers. |
| `teq-pmr-session-open-breakout/teq-pmr-session-open-breakout-summary.md` | Session opening-range breakout replay over Binance 2026 TradFi equity and metal perpetuals; creates `SOR-001` as a P1 session right-tail packet. |
| `sor-session-classifier-sweep/sor-session-classifier-sweep-summary.md` | Bounded `SOR-001` pre-entry classifier sweep over 19 interpretable rules; improves PMR short support and TEQ long revival evidence but does not solve second-half decay. |
| `sor-exit-horizon-sweep/sor-exit-horizon-sweep-summary.md` | Fixed time-stop sweep over accepted `SOR-001` base and classifier events; creates a narrow TEQ short 72h time-stop lead while keeping PMR short decay unresolved. |
| `sor-exit-reslot-replay/sor-exit-reslot-replay-summary.md` | Raw-pool fixed time-stop reslot replay for `SOR-001`; narrows TEQ short 72h to one decisive-breakdown lead and downgrades volume-confirmed short to window-revival evidence. |
| `pmr-xag-short-overlay-replay/pmr-xag-short-overlay-summary.md` | Prefix-safe closed-candle PMR XAG-led short/weakness overlay replay; window-only support evidence with promotion blocked by disable-classifier and margin facts. |
| `pmr-short-overlay-classifier-sweep/pmr-short-overlay-classifier-sweep-summary.md` | Bounded PMR short-overlay classifier sweep over 24 interpretable rules; preserves XAG-led window/revival evidence but finds no robust 100%+ 90d 2x overlay candidate. |
| `pmr-metal-dislocation-refresh/pmr-metal-dislocation-refresh-summary.md` | Fixed-rule PMR metal dislocation refresh over XAG/XAU/XPT/XPD/COPPER futures plus XAUT/PAXG gold-token spot context; reinforces short/weakness overlay and broad-long negative evidence. |
| `pmr-metal-relative-spread-replay/pmr-metal-relative-spread-summary.md` | Fixed-rule MRS-001 metal relative-strength, relative-weakness, and XAG/XAU spread replay; parks simple metal-relative rules as negative/support evidence. |
| `vpc-vwap-pullback-continuation/vpc-vwap-pullback-continuation-summary.md` | Fixed-rule VPC-001 VWAP pullback/reclaim and rejection replay over Binance 2026 TradFi equity/metal futures; preserves VWAP as window-revival and negative evidence. |
| `sgc-session-gap-continuation-fade/sgc-session-gap-continuation-fade-summary.md` | Fixed-rule SGC-001 session gap continuation/fade replay over Binance 2026 TradFi equity/metal futures; preserves gap-up continuation as window-revival evidence. |
| `fvg-fair-value-gap-replay/fvg-fair-value-gap-summary.md` | Fixed-rule FVG-001 fair-value-gap continuation/retest replay over Binance 2026 TradFi equity/metal futures; preserves bull continuation and retest as window-revival evidence. |
| `ibb-inside-nr7-breakout-replay/ibb-inside-nr7-breakout-summary.md` | Fixed-rule IBB-001 inside-bar / NR7 compression-breakout replay over Binance 2026 TradFi equity/metal futures; preserves inside long support and NR7 long window-revival evidence. |
| `ksb-keltner-bollinger-squeeze-replay/ksb-keltner-bollinger-squeeze-summary.md` | Fixed-rule KSB-001 Keltner/Bollinger squeeze-release replay over Binance 2026 TradFi equity/metal futures; parks simple squeeze breakouts as negative/revival evidence. |
| `stf-supertrend-followthrough-replay/stf-supertrend-followthrough-summary.md` | Fixed-rule STF-001 SuperTrend flip/follow-through replay over Binance 2026 TradFi equity/metal futures; parks dense continuation rules and preserves flip rows as support evidence. |
| `mhi-macd-histogram-ignition-replay/mhi-macd-histogram-ignition-summary.md` | Fixed-rule MHI-001 MACD histogram zero-cross / acceleration replay over Binance 2026 TradFi equity/metal futures; promotes only zero-cross long to P1 right-tail review. |
| `dmi-adx-directional-ignition-replay/dmi-adx-directional-ignition-summary.md` | Fixed-rule DMI-001 ADX / +DI / -DI replay over Binance 2026 TradFi equity/metal futures; promotes only trend-strength long to P1 right-tail review. |
| `dmi-decay-asset-role-classifier/dmi-decay-asset-role-classifier-summary.md` | Signal-time raw-pool classifier replay for DMI-001; preserves ADX-rising equity and weekday-equity review branches while blocking promotion on drawdown/full-return tradeoffs. |
| `rsi-regime-reclaim-replay/rsi-regime-reclaim-summary.md` | Fixed-rule RSI-001 regime-reclaim replay over Binance 2026 TradFi equity/metal futures; preserves midline reclaim as window-revival evidence and parks generic RSI rows. |
| `cci-trend-escape-replay/cci-trend-escape-summary.md` | Fixed-rule CCI-001 trend escape / failure replay over Binance 2026 TradFi equity/metal futures; broad generic CCI rows are negative. |
| `cci-asset-session-classifier/cci-asset-session-classifier-summary.md` | Raw-pool CCI-001 classifier replay; preserves equity reclaim windows and precious-metal +100 failure-short revival, while blocking promotion on drawdown/off-hour/margin facts. |
| `aroon-trend-emergence-replay/aroon-trend-emergence-summary.md` | Fixed-rule AROON-001 trend-emergence replay over Binance 2026 TradFi equity/metal futures; parks Aroon as support/negative vocabulary. |
| `wpr-percent-range-replay/wpr-percent-range-summary.md` | Fixed-rule WPR-001 Williams %R replay over Binance 2026 TradFi equity/metal futures; promotes only overbought persistence long to P1 right-tail review. |
| `roc-momentum-acceleration-replay/roc-momentum-acceleration-summary.md` | Fixed-rule ROC-001 rate-of-change replay over Binance 2026 TradFi equity/metal futures; preserves acceleration long as window-revival evidence and parks broad ROC rows. |
| `mfi-money-flow-replay/mfi-money-flow-summary.md` | Fixed-rule MFI-001 Money Flow Index replay over Binance 2026 TradFi equity/metal futures; promotes only overbought persistence long to P1 right-tail review and parks generic MFI reversal rows. |
| `obv-volume-flow-replay/obv-volume-flow-summary.md` | Fixed-rule OBV-001 On-Balance Volume replay over Binance 2026 TradFi equity/metal futures; preserves trend-confirmed long as window-revival evidence and parks short-side distribution rows. |
| `cmf-money-flow-replay/cmf-money-flow-summary.md` | Fixed-rule CMF-001 Chaikin Money Flow replay over Binance 2026 TradFi equity/metal futures; preserves accumulation-trend long as window-revival evidence and parks distribution/zero-reject rows. |
| `pvo-volume-oscillator-replay/pvo-volume-oscillator-summary.md` | Fixed-rule PVO-001 Percentage Volume Oscillator replay over Binance 2026 TradFi equity/metal futures; parks generic PVO expansion and keeps zero-reclaim as support-only evidence below the right-tail gate. |
| `ppo-price-oscillator-replay/ppo-price-oscillator-summary.md` | Fixed-rule PPO-001 Percentage Price Oscillator replay over Binance 2026 TradFi equity/metal futures; promotes only momentum-persistence long to P1 right-tail review. |
| `tsi-true-strength-replay/tsi-true-strength-summary.md` | Fixed-rule TSI-001 True Strength Index replay over Binance 2026 TradFi equity/metal futures; preserves momentum-persistence long as P1 window-revival evidence but blocks promotion on full-sequence drawdown. |
| `tsi-decay-asset-role-classifier/tsi-decay-asset-role-classifier-summary.md` | Raw-pool TSI-001 decay/asset-role classifier replay; promotes `tsi_long_equity_tsi_rising` to P1 classifier review while keeping high leverage downshifted. |
| `tsi-exit-horizon-reslot/tsi-exit-horizon-reslot-summary.md` | Raw-pool TSI-001 exit-horizon reslot replay; 12h time-stop improves TSI-rising full/best-window returns and removes 5x proxy liquidation, but leaves DD unresolved. |
| `kst-know-sure-thing-replay/kst-know-sure-thing-summary.md` | Fixed-rule KST-001 Know Sure Thing replay over Binance 2026 TradFi equity/metal futures; preserves positive persistence as a window-revival handle and parks generic KST rows. |
| `mass-index-reversal-replay/mass-index-reversal-summary.md` | Fixed-rule MASS-001 Mass Index replay over Binance 2026 TradFi equity/metal futures; preserves long reversal as P1 review and flags continuation drawdown, June decay, and concentration blockers. |
| `efi-elder-force-index-replay/efi-elder-force-index-summary.md` | Fixed-rule EFI-001 Elder Force Index replay over Binance 2026 TradFi equity/metal futures; preserves negative-force exhaustion reversal as P1 review and flags candidate-level drawdown, short-side failure, and high-leverage blockers. |
| `fish-fisher-transform-replay/fish-fisher-transform-summary.md` | Fixed-rule FISH-001 Fisher Transform replay over Binance 2026 TradFi equity/metal futures; preserves normalized-price reversal/persistence as window-revival evidence and flags full-sequence, drawdown, and leverage blockers. |
| `rvi-relative-vigor-replay/rvi-relative-vigor-summary.md` | Fixed-rule RVI-001 Relative Vigor Index replay over Binance 2026 TradFi equity/metal futures; preserves PMR / short-cross review evidence and flags candidate-level, TEQ, dense-short, and high-leverage blockers. |
| `cho-chaikin-oscillator-replay/cho-chaikin-oscillator-summary.md` | Fixed-rule CHO-001 Chaikin Oscillator replay over Binance 2026 TradFi equity/metal futures; preserves equity/ETF accumulation-trend and zero-reclaim window-revival evidence while rejecting broad CHO promotion. |
| `chv-chaikin-volatility-replay/chv-chaikin-volatility-summary.md` | Fixed-rule CHV-001 Chaikin Volatility replay over Binance 2026 TradFi equity/metal futures; preserves equity/ETF volatility-expansion window-revival evidence while rejecting broad CHV promotion. |
| `momentum-persistence-strategy-group/momentum-persistence-strategy-group-summary.md` | `MPG-001` group evidence over WPR, MFI, PPO, TSI, MHI, and DMI; proves the useful semantic is strength persistence, not generic oscillator reversal. |
| `mpg-group-decay-classifier/mpg-group-decay-classifier-summary.md` | Raw-pool group classifier replay for `MPG-001`; bounded impulse wins the group pool with full 2x `306.759633%` and best-90d 2x `1036.621997%`, but DD blocks promotion. |
| `mpg-exit-horizon-reslot/mpg-exit-horizon-reslot-summary.md` | Group-pool fixed exit-horizon reslot replay for `MPG-001`; 72h bounded impulse preserves the largest right tail, while 12h regular-session proxy becomes the cleaner exit-tradeoff row. |
| `mpg-leverage-horizon-envelope/mpg-leverage-horizon-envelope-summary.md` | Derived 1x/2x/3x/5x leverage-horizon envelope for `MPG-001`; only 12h regular proxy is a 2x tradeoff lane, while 5x is disabled in most useful right-tail rows. |
| `mpg-late-cycle-disable/mpg-late-cycle-disable-summary.md` | Signal-time late-cycle disable replay for `MPG-001`; body-capped bounded impulse strengthens the right tail but still leaves promotion-blocking drawdown. |
| `mpg-drawdown-attribution/mpg-drawdown-attribution-summary.md` | Retrospective drawdown attribution for `MPG-001`; decomposes the current body-capped revival lead by member, symbol, month, and worst events without turning attribution into activation filters. |
| `ea-energy-alignment-screener-replay/ea-energy-alignment-screener-summary.md` | Closed-candle EA-001 energy-alignment screener replay; window-only evidence with catastrophic full-curve drawdown and high-leverage promotion block. |
| `pmr-overlay-target-pairing/pmr-overlay-target-pairing-summary.md` | PMR overlay-target pairing audit for DCB/THR/BTPC coverage plus overlapping 2026 TEQ/NLPD/OSS-THR event outcomes. |
| `pmr-target-specific-overlay-classifier/pmr-target-specific-overlay-classifier-summary.md` | Target-specific PMR overlay classifier; PMR disables NLPD continuation labels but remains a TEQ support tag rather than a universal filter. |
| `derivatives-leverage-requiredfacts-data-plan.md` | Leverage, funding, OI, long/short ratio, premium, and squeeze-risk RequiredFacts plan. |
| `leverage-aware-candidate-shortlist/leverage-aware-candidate-shortlist-summary.md` | Cross-candidate 2x/3x/5x comparison layer; now includes MASS/EFI/UO/TRIX/RVI/HAT stop-reslot rows and blocks runtime-facing interpretation on current availability, fill/gap, product-risk, and real margin facts. |
| `dcb-donchian-tradfi-breakout-replay/dcb-donchian-tradfi-breakout-summary.md` | DCB prior-channel breakout replay over Binance 2026 TradFi equity/ETF and precious-metal 1h futures; no rule clears the 100%+ best-90d 2x gate, so this is negative/revival evidence. |
| `aeb-atr-expansion-breakout-replay/aeb-atr-expansion-breakout-summary.md` | AEB gap-aware ATR / True Range expansion breakout replay over Binance 2026 TradFi equity/ETF and metal futures; preserves an equity ATR24 30d 2x revival window while blocking broad promotion. |
| `main-control-strategy-research-v3-handoff.md` | Main-control handoff for V3 execution batch 1. |

## Historical V1/V2 Documents

V1/V2 documents remain useful as historical evidence, but they are not current
goal authority when they frame strategy research around full-sample economics,
review readiness, or always-on stability.

| Historical Document | Current Status |
| --- | --- |
| `strategy-research-plan-v1.md` | Superseded by `strategy-research-v3-goal.md`. |
| `strategy-research-v2.2-goal-coverage-audit.md` | Historical completion audit only. |
| `evidence-gate-policy.md` | Superseded for research-stage evaluation by `regime-right-tail-evaluation-policy.md`. |
| `evidence-execution-plan.md` | Superseded for research sequencing by `right-tail-window-mining-plan.md`. |
| `strategy-candidate-registry.md` | Historical SRT registry; use `strategy-candidate-pool-v2.md` for current framing. |
| `market-regime-taxonomy.md` | Historical taxonomy; v3 expands it through regime-right-tail evaluation. |

## Boundary

All files in this directory are research artifacts. They carry no order,
execution intent, execution authority, exchange-write authority, deploy
authority, credential authority, live-profile authority, or order-sizing
authority.
