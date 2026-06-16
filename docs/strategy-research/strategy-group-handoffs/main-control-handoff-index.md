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

## Main-Control Consumption Contract

Each `handoff.json` includes the main-control required fields:

| Field | Present In Batch | Main-Control Use |
| --- | ---: | --- |
| `strategy_group_id` | `8/8` | Stable Strategy Picker / admission identifier. |
| `version` | `8/8` | Traceable signal and handoff source version. |
| `supported_symbols` | `8/8` | Research observation universe pending exchange-rule validation. |
| `supported_sides` | `8/8` | Direction scope and disabled/revival-side semantics. |
| `signal_ready_rule` | `8/8` | Fresh-signal readiness semantics. |
| `required_facts` | `8/8` | Runtime readiness, account, market, exchange, and strategy fact requirements. |
| `risk_defaults` | `8/8` | Research risk proposal only; not live order-sizing defaults. |
| `hard_stops` | `8/8` | Strategy-level blockers before observation/candidate preparation/execution review. |
| `sample_signal_packet` | `8/8` | Example fresh signal output. |
| `sample_no_signal_packet` | `8/8` | Example no-signal output. |

All eight JSON packs also include `sample_stale_signal_packet` and
`sample_conflict_packet`.

## Low-Ambiguity Intake Supplements

| Document | Purpose |
| --- | --- |
| `main-control-admission-priority.md` | Recommended admission order, default picker visibility, observe-only defaults, and conditional session branches. |
| `main-control-required-facts-map.md` | Maps strategy RequiredFacts to main-control runtime fact categories and missing-fact behavior. |
| `main-control-conflict-policy.md` | Defines same-symbol, direction, mode, facts, stale, and multi-strategy conflict handling. |
| `main-control-watcher-cadence.md` | Recommends watcher poll cadence, business signal validity, and stale behavior by strategy group. |
| `../fbs-derivatives-facts-readiness-split-20260616.md` | P0 supplement for `FBS-001` fresh, partial, stale, missing, and margin-missing derivatives fact behavior. |

## Admission Interpretation

| Strategy Group | Recommended Main-Control Handling |
| --- | --- |
| `MPG-001` | Admit as experimental momentum-persistence observation candidate; keep 5x disabled and 3x stress-only. |
| `FBS-001` | Admit as derivatives stress observer plus TEQ negative-funding long candidate; treat positive-funding shorts as disable/redesign evidence. |
| `TEQ-001` | Admit as long-side equity-like momentum observer; require concentration, session, mark/funding, and product facts before candidate preparation. |
| `PMR-001` | Start as observe-only PMR short/overlay candidate; upgrade to armed observation only after session/mark facts are present. |
| `SOR-001` | Admit branch-by-branch; do not treat it as broad opening-range alpha. |
| `VCB-001` | Keep observe-only as true-breakout classifier draft; do not admit broad breakout or armed observation until signal-time classifier quality improves. |
| `RSR-001` | Keep observe-only as TEQ support scorer; do not admit standalone armed observation until decay, session/fill, product, mark/funding, and margin facts improve. |
| `NLPD-001` | Keep observe-only as low-history event observer; do not admit armed observation until cohort breadth, survivorship, spread/liquidity, product-risk, and executable-side facts improve. |

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
OK docs/strategy-research/strategy-group-handoffs/FBS-001/handoff.json
OK docs/strategy-research/strategy-group-handoffs/MPG-001/handoff.json
OK docs/strategy-research/strategy-group-handoffs/PMR-001/handoff.json
OK docs/strategy-research/strategy-group-handoffs/SOR-001/handoff.json
OK docs/strategy-research/strategy-group-handoffs/TEQ-001/handoff.json
OK docs/strategy-research/strategy-group-handoffs/VCB-001/handoff.json
OK docs/strategy-research/strategy-group-handoffs/RSR-001/handoff.json
OK docs/strategy-research/strategy-group-handoffs/NLPD-001/handoff.json

FBS-001 complete symbols 9 sides long,short_disable_or_redesign_only
MPG-001 complete symbols 21 sides long
PMR-001 complete symbols 7 sides short,long_context_only
SOR-001 complete symbols 9 sides short,long_revival_only
TEQ-001 complete symbols 10 sides long
VCB-001 complete symbols 7 sides long
RSR-001 complete symbols 15 sides long
NLPD-001 complete symbols 10 sides long,short_analysis_only
```

## Boundary Proof

This batch modifies only strategy-research documents under:

```text
docs/strategy-research/strategy-group-handoffs/
docs/strategy-research/README.md
```

It does not modify OrderLifecycle, FinalGate, Operation Layer, exchange
gateway, live profile, credentials, deploy files, real order paths, or live
order-sizing defaults.
