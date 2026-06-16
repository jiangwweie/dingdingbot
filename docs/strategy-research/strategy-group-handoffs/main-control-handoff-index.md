# Main-Control Strategy Group Handoff Index

Status: HANDOFF_READY_FOR_MAIN_CONTROL_REVIEW
Last updated: 2026-06-16

## Purpose

This index is the main-control entry point for Strategy Research v3
StrategyGroup handoff packs.

It converts research evidence into observable experimental StrategyGroup
candidates and observe-only draft candidates. The files below are not runtime
registration, exchange-write
authority, FinalGate input, Operation Layer input, deploy requests, credential
changes, live-profile changes, or order-sizing defaults.

## Handoff Batch

| Strategy Group | Human Pack | JSON Pack | Primary Role | Default Mode | Sides |
| --- | --- | --- | --- | --- | --- |
| `MPG-001` | `MPG-001/handoff.md` | `MPG-001/handoff.json` | Momentum persistence group over WPR/MFI/PPO/TSI/MHI/DMI | `armed_observation` | `long` |
| `FBS-001` | `FBS-001/handoff.md` | `FBS-001/handoff.json` | Funding/basis stress and TEQ negative-funding squeeze | `armed_observation` | `long`; short as disable/redesign evidence |
| `TEQ-001` | `TEQ-001/handoff.md` | `TEQ-001/handoff.json` | Binance 2026 equity-like momentum | `armed_observation` | `long` |
| `PMR-001` | `PMR-001/handoff.md` | `PMR-001/handoff.json` | Precious-metal short/weakness overlay | `observe_only` | `short`; long as context only |
| `SOR-001` | `SOR-001/handoff.md` | `SOR-001/handoff.json` | Session opening-range / branch-specific right-tail | `armed_observation` | `short`; long as revival only |
| `VCB-001` | `VCB-001/handoff.md` | `VCB-001/handoff.json` | Volatility compression true-breakout classifier draft | `observe_only` | `long` |
| `RSR-001` | `RSR-001/handoff.md` | `RSR-001/handoff.json` | Relative-strength rotation TEQ support scorer draft | `observe_only` | `long` |
| `NLPD-001` | `NLPD-001/handoff.md` | `NLPD-001/handoff.json` | New-listing / contract-event low-history observer draft | `observe_only` | `long`; short as analysis-only |
| `DMI-001` | `DMI-001/handoff.md` | `DMI-001/handoff.json` | ADX/DMI equity ADX-rising directional ignition draft | `observe_only` | `long` |
| `SCF-001` | `SCF-001/handoff.md` | `SCF-001/handoff.json` | Session-confluence TEQ structure-confirmation draft | `observe_only` | `long`; short as support only |
| `MASS-001` | `MASS-001/handoff.md` | `MASS-001/handoff.json` | Mass Index range-expansion reversal draft | `observe_only` | `long`; short as support only |
| `UO-001` | `UO-001/handoff.md` | `UO-001/handoff.json` | Ultimate Oscillator bullish-divergence draft | `observe_only` | `long` |

## Main-Control Consumption Contract

Each `handoff.json` includes the main-control required fields:

| Field | Present In Batch | Main-Control Use |
| --- | ---: | --- |
| `strategy_group_id` | `12/12` | Stable Strategy Picker / admission identifier. |
| `version` | `12/12` | Traceable signal and handoff source version. |
| `supported_symbols` | `12/12` | Research observation universe pending exchange-rule validation. |
| `supported_sides` | `12/12` | Direction scope and disabled/revival-side semantics. |
| `signal_ready_rule` | `12/12` | Fresh-signal readiness semantics. |
| `required_facts` | `12/12` | Runtime readiness, account, market, exchange, and strategy fact requirements. |
| `risk_defaults` | `12/12` | Research risk proposal only; not live order-sizing defaults. |
| `hard_stops` | `12/12` | Strategy-level blockers before observation/candidate preparation/execution review. |
| `sample_signal_packet` | `12/12` | Example fresh signal output. |
| `sample_no_signal_packet` | `12/12` | Example no-signal output. |

All twelve JSON packs also include `sample_stale_signal_packet` and
`sample_conflict_packet`.

## Low-Ambiguity Intake Supplements

| Document | Purpose |
| --- | --- |
| `main-control-admission-priority.md` | Recommended admission order, default picker visibility, observe-only defaults, and conditional session branches. |
| `main-control-required-facts-map.md` | Maps strategy RequiredFacts to main-control runtime fact categories and missing-fact behavior. |
| `main-control-conflict-policy.md` | Defines same-symbol, direction, mode, facts, stale, and multi-strategy conflict handling. |
| `main-control-watcher-cadence.md` | Recommends watcher poll cadence, business signal validity, and stale behavior by strategy group. |
| `../mpg-member-drawdown-disable-addendum-20260616.md` | P0 supplement for `MPG-001` member drawdown forensics, prefix-safe disable candidates, and 12h/72h horizon separation. |
| `../fbs-derivatives-facts-readiness-split-20260616.md` | P0 supplement for `FBS-001` fresh, partial, stale, missing, and margin-missing derivatives fact behavior. |
| `../teq-current-product-availability-refresh-20260616.md` | P0 supplement for `TEQ-001` current Binance product visibility and cached-research-only behavior. |
| `../pmr-overlay-role-split-20260616.md` | P0 supplement for `PMR-001` target-specific disable/support/context roles and blocked standalone branches. |
| `../sor-branch-eligibility-time-stop-20260616.md` | P0 supplement for `SOR-001` eligible short 72h branches, revival-only branches, and blocked broad ORB branches. |
| `../vcb-signal-time-classifier-boundary-20260616.md` | P1 supplement for `VCB-001` signal-time breakout facts, post-entry label boundary, and observe-only classifier behavior. |
| `../rsr-scorer-standalone-boundary-20260616.md` | P1 supplement for `RSR-001` TEQ support scoring, Strategy Picker rank hints, and standalone activation blockers. |
| `../nlpd-low-history-event-boundary-20260616.md` | P1 supplement for `NLPD-001` listing-event observation, low-history blockers, product class, executable-side, and PMR disable context. |
| `DMI-001/handoff.md` | P2-to-P1 observe-only handoff draft for `DMI-001` equity ADX-rising long directional ignition, 24h time-stop, and cost/fill/session/margin blockers. |
| `SCF-001/handoff.md` | P2-to-P1 observe-only handoff draft for `SCF-001` TEQ session confluence, prefix-safe structure confirmation, 12h time-stop, and fill/session/margin blockers. |
| `MASS-001/handoff.md` | P2-to-P1 observe-only handoff draft for `MASS-001` Mass Index bulge reversal, direction-context requirement, 48h time-stop, and concentration/decay blockers. |
| `UO-001/handoff.md` | P2-to-P1 observe-only handoff draft for `UO-001` Ultimate Oscillator bullish divergence, prior-weakness requirement, 72h review lane, and midline/short-side blockers. |
| `../lcf-facts-pipeline-boundary-20260616.md` | P1 non-handoff supplement for `LCF-001` force-order, liquidation-cluster, OI, positioning, depth, ADL, margin, and facts-missing no-signal behavior. |
| `../mds-target-pairing-boundary-20260616.md` | P1 non-handoff supplement for `MDS-001` NLPD disable tags, TEQ support tags, coverage-missing policies, and standalone-blocked overlay behavior. |

## Admission Interpretation

| Strategy Group | Recommended Main-Control Handling |
| --- | --- |
| `MPG-001` | Admit as experimental momentum-persistence observation candidate; keep 5x disabled, 3x stress-only, and require prefix-safe member disable facts before filtering WPR/TSI or symbols. |
| `FBS-001` | Admit as derivatives stress observer plus TEQ negative-funding long candidate; treat positive-funding shorts as disable/redesign evidence. |
| `TEQ-001` | Admit as long-side equity-like momentum observer; require concentration, session, mark/funding, and product facts before candidate preparation. |
| `PMR-001` | Start as observe-only PMR overlay; allow target-specific disable/support annotations, but keep standalone PMR short and broad metal-long promotion blocked. |
| `SOR-001` | Admit branch-by-branch only; keep TEQ decisive-breakdown short 72h as the narrow candidate lane, PMR short as conditional support, TEQ long as revival-only, and broad ORB blocked. |
| `VCB-001` | Keep observe-only as true-breakout classifier draft; post-entry true/false labels are research targets only, and broad breakout or armed observation stays blocked until signal-time classifier quality improves. |
| `RSR-001` | Keep observe-only as TEQ support scorer and Strategy Picker rank hint; standalone activation remains blocked until decay, session/fill, product, mark/funding, and margin facts improve. |
| `NLPD-001` | Keep observe-only as low-history event observer; listing labels remain research-only and armed observation stays blocked until cohort breadth, survivorship, spread/liquidity, product-risk, and executable-side facts improve. |
| `DMI-001` | Keep observe-only as equity ADX-rising long directional-ignition draft; generic DMI, short-side DMI, and precious-metal generalization stay blocked until cost/fill/session/product and real-margin facts improve. |
| `SCF-001` | Keep observe-only as TEQ session-confluence structure-confirmation draft; PMR short confluence remains support-only, and armed observation stays blocked until prefix-safe facts, fill/session/product, and real-margin evidence improve. |
| `MASS-001` | Keep observe-only as Mass Index bulge-reversal draft; Mass Index itself is non-directional, so direction-context, concentration, decay, fill/session/product, and real-margin facts must improve before armed observation. |
| `UO-001` | Keep observe-only as Ultimate Oscillator bullish-divergence draft; generic midline persistence and short-side UO remain blocked until divergence quality, product/session/fill, and real-margin facts improve. |

Non-handoff P1 interpretation: `LCF-001` should stay in the Strategy Cabinet as
`facts_pipeline_required`. Main control should not treat it as a runtime intake
candidate until force-order, liquidation-cluster, OI, positioning, depth, ADL,
and margin facts reach replay-ready form and a separate handoff pack exists.

Non-handoff P1 interpretation: `MDS-001` should stay in the Strategy Cabinet as
`overlay_candidate`. Main control should not treat it as a standalone Strategy
Group; if consumed later, its first useful shape is target-specific overlay
context, especially `NLPD-001` disable tags and `TEQ-001` support tags.

## Shared Main-Control Hard Stops

The batch expects main-control to block candidate preparation when any of the
following are true:

1. Same-symbol active position or open order exists.
2. Market facts are stale.
3. Exchange symbol rules are missing.
4. Stop-loss or exit plan is missing.
5. Signal packet is stale or conflicting.
6. Leverage request exceeds the research lane.
7. Runtime facts cannot prove symbol availability, min notional, step size, or
   tick size.

## Verification Commands

```bash
for f in docs/strategy-research/strategy-group-handoffs/*/handoff.json; do
  python3 -m json.tool "$f" >/dev/null || exit 1
  echo "OK $f"
done

python3 - <<'PY'
import json, pathlib
required=[
  'strategy_group_id','version','supported_symbols','supported_sides',
  'signal_ready_rule','required_facts','risk_defaults','hard_stops',
  'sample_signal_packet','sample_no_signal_packet'
]
base=pathlib.Path('docs/strategy-research/strategy-group-handoffs')
for p in sorted(base.glob('*/handoff.json')):
    data=json.loads(p.read_text())
    missing=[k for k in required if k not in data]
    print(p.parent.name, 'complete' if not missing else 'missing=' + ','.join(missing))
PY
```

## Current Verification Result

```text
OK docs/strategy-research/strategy-group-handoffs/DMI-001/handoff.json
OK docs/strategy-research/strategy-group-handoffs/FBS-001/handoff.json
OK docs/strategy-research/strategy-group-handoffs/MASS-001/handoff.json
OK docs/strategy-research/strategy-group-handoffs/MPG-001/handoff.json
OK docs/strategy-research/strategy-group-handoffs/NLPD-001/handoff.json
OK docs/strategy-research/strategy-group-handoffs/PMR-001/handoff.json
OK docs/strategy-research/strategy-group-handoffs/RSR-001/handoff.json
OK docs/strategy-research/strategy-group-handoffs/SCF-001/handoff.json
OK docs/strategy-research/strategy-group-handoffs/SOR-001/handoff.json
OK docs/strategy-research/strategy-group-handoffs/TEQ-001/handoff.json
OK docs/strategy-research/strategy-group-handoffs/UO-001/handoff.json
OK docs/strategy-research/strategy-group-handoffs/VCB-001/handoff.json

DMI-001 complete symbols 15 sides long
FBS-001 complete symbols 9 sides long,short_disable_or_redesign_only
MASS-001 complete symbols 15 sides long,short_support_only
MPG-001 complete symbols 21 sides long
NLPD-001 complete symbols 10 sides long,short_analysis_only
PMR-001 complete symbols 7 sides short,long_context_only
RSR-001 complete symbols 15 sides long
SCF-001 complete symbols 14 sides long,short_support_only
SOR-001 complete symbols 9 sides short,long_revival_only
TEQ-001 complete symbols 10 sides long
UO-001 complete symbols 25 sides long
VCB-001 complete symbols 7 sides long
```

## Boundary Proof

This batch modifies only strategy-research documents under:

```text
docs/strategy-research/strategy-group-handoffs/
docs/strategy-research/README.md
docs/strategy-research/strategy-cabinet/
docs/strategy-research/p1-next-handoff-queue-20260616.md
docs/strategy-research/p2-cabinet-extension-batch2-20260616.md
docs/strategy-research/strategy-line-handoff-summary-20260616.md
```

It does not modify OrderLifecycle, FinalGate, Operation Layer, exchange
gateway, live profile, credentials, deploy files, real order paths, or live
order-sizing defaults.
