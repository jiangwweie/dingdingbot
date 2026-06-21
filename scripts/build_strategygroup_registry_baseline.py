#!/usr/bin/env python3
"""Build or validate the StrategyGroup registry baseline.

The registry baseline is a governance artifact. It defines StrategyGroup asset
semantics for Owner/Codex review, but it is not runtime state, FinalGate input,
Operation Layer input, exchange-write authority, live-profile authority, or
order-sizing authority.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-registry-baseline.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-registry-baseline.md"
)

ACTIONABLE_NOW_REASON = (
    "runtime_state_only; requires fresh signal, live facts, candidate/auth, "
    "action-time execution gates, official submission path, protection, account, "
    "and exchange facts"
)
AUTHORITY_BOUNDARY = (
    "Registry row is strategy asset governance only. It does not authorize "
    "runtime start, candidate creation, FinalGate, Operation Layer, exchange "
    "write, real order, live-profile mutation, order-sizing mutation, withdrawal, "
    "transfer, or credential mutation."
)
RISK_CLASS_KEYS = [
    "strategy_quality_risk",
    "fact_coverage_risk",
    "economic_risk",
    "execution_safety_risk",
    "authority_risk",
]
REQUIRED_ROW_FIELDS = [
    "strategy_group_id",
    "owner_label",
    "edge_thesis",
    "trade_logic",
    "regime_fit",
    "supported_sides",
    "default_tier",
    "trial_eligible",
    "actionable_now",
    "actionable_now_reason",
    "risk_gaps",
    "hard_blocks",
    "required_facts_summary",
    "promotion_gate",
    "downshift_rule",
    "park_rule",
    "kill_condition",
    "evidence_refs",
    "authority_boundary",
]
EXPECTED_GROUPS = [
    "MPG-001",
    "TEQ-001",
    "FBS-001",
    "SOR-001",
    "PMR-001",
    "BTPC-001",
    "VCB-001",
    "LSR-001",
    "BRF-001",
    "RBR-001",
]


def build_registry_baseline() -> dict[str, Any]:
    rows = [_with_defaults(row) for row in _row_specs()]
    return {
        "schema": "brc.strategygroup_registry_baseline.v1",
        "status": "current_pilot_baseline",
        "scope": "strategygroup_registry_baseline",
        "source_authority": {
            "registry_contract": (
                "docs/current/strategy-group-handoffs/"
                "STRATEGYGROUP_REGISTRY_CONTRACT.md"
            ),
            "tier_policy": (
                "docs/current/strategy-group-handoffs/"
                "main-control-runtime-tier-policy.json"
            ),
            "handoff_index": (
                "docs/current/strategy-group-handoffs/"
                "main-control-handoff-index.md"
            ),
            "decision_ledger_contract": (
                "docs/current/STRATEGY_OPPORTUNITY_REVIEW_LEDGER.md"
            ),
        },
        "actionability_contract": {
            "trial_eligible_source": "registry_plus_owner_policy",
            "actionable_now_source": "runtime_state_only",
            "static_rows_must_not_set_actionable_now_true": True,
            "actionable_now_reason": ACTIONABLE_NOW_REASON,
        },
        "risk_acceptance_policy": {
            "owner_may_accept": [
                "strategy_quality_risk",
                "fact_coverage_risk",
                "economic_risk",
            ],
            "owner_may_not_override": [
                "execution_safety_risk",
                "authority_risk",
            ],
        },
        "safety_invariants": {
            "real_order_authority": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
            "changes_live_profile": False,
            "changes_order_sizing_defaults": False,
            "withdrawal_or_transfer": False,
        },
        "required_row_fields": REQUIRED_ROW_FIELDS,
        "rows": rows,
    }


def build_owner_markdown(packet: dict[str, Any]) -> str:
    rows = _dict_rows(packet.get("rows"))
    lines = [
        "---",
        "title: STRATEGYGROUP_REGISTRY_BASELINE",
        "status: CURRENT_PILOT_BASELINE",
        "authority: docs/current/strategy-group-handoffs/strategygroup-registry-baseline.json",
        "last_verified: 2026-06-20",
        "---",
        "",
        "# StrategyGroup Registry Baseline",
        "",
        "## 目的",
        "",
        "这份基线是 Owner/Codex 共用的 StrategyGroup 策略资产地图，用来说明每个 StrategyGroup 吃什么机会、怎么交易、当前层级、是否具备试运行资格，以及哪些证据会改变 keep / revise / promote / park / kill 决策。",
        "",
        "它不是实时运行状态。`actionable_now` 只能由运行时判断，因此静态 registry 中始终保持 `false`。",
        "",
        "## 总览",
        "",
        _summary_table(rows),
        "",
        "## 风险边界",
        "",
        "| 风险类别 | Owner 是否可在既定策略范围内接受 | Registry 行为 |",
        "| --- | --- | --- |",
        "| `strategy_quality_risk` | 可以 | 策略和 replay 不确定性可用于 keep / revise / park / promote / kill 决策 |",
        "| `fact_coverage_risk` | 观察和复盘层级内可以 | 实盘动作仍需要运行时新鲜事实 |",
        "| `economic_risk` | 既定范围内可以 | 成本和滑点只影响策略判断，不构成提交权限 |",
        "| `execution_safety_risk` | 不可以 | 事实过期、保护缺失、重复提交、冲突敞口必须运行时失败关闭 |",
        "| `authority_risk` | 不可以 | 文档、replay、代理事实、观察证据永远不能授权实盘动作 |",
        "",
        "## 当前策略组",
        "",
    ]
    for row in rows:
        lines.extend(_row_section(row))
    lines.extend(
        [
            "## Boundary Detail",
            "",
            "This registry does not authorize runtime start, candidate creation, FinalGate, Operation Layer, exchange write, real order, live-profile mutation, order-sizing mutation, withdrawal, transfer, or credential mutation.",
            "",
            "A real order remains runtime-only and requires selected StrategyGroup scope, allocated subaccount/profile boundary, fresh signal, fresh facts, candidate/auth evidence, action-time execution checks, official submission path, protection, reconciliation, settlement, and review capture.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def validate_packet(packet: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    rows = _dict_rows(packet.get("rows"))
    groups = [str(row.get("strategy_group_id") or "") for row in rows]
    if groups != EXPECTED_GROUPS:
        errors.append(f"unexpected_strategy_groups:{groups}")
    if packet.get("schema") != "brc.strategygroup_registry_baseline.v1":
        errors.append("schema_mismatch")
    safety = _as_dict(packet.get("safety_invariants"))
    for key in (
        "real_order_authority",
        "calls_finalgate",
        "calls_operation_layer",
        "calls_exchange_write",
        "places_order",
        "changes_live_profile",
        "changes_order_sizing_defaults",
        "withdrawal_or_transfer",
    ):
        if safety.get(key) is not False:
            errors.append(f"safety_invariant_not_false:{key}")
    for row in rows:
        group = str(row.get("strategy_group_id") or "unknown")
        for field in REQUIRED_ROW_FIELDS:
            if field not in row:
                errors.append(f"{group}.missing_field:{field}")
        if row.get("actionable_now") is True:
            errors.append(f"{group}.actionable_now_true")
        if not isinstance(row.get("trial_eligible"), bool):
            errors.append(f"{group}.trial_eligible_not_bool")
        if not _dict_rows(row.get("evidence_refs")):
            errors.append(f"{group}.missing_evidence_refs")
        risks = _as_dict(row.get("risk_gaps"))
        if sorted(risks) != sorted(RISK_CLASS_KEYS):
            errors.append(f"{group}.risk_class_mismatch")
        for non_override in ("execution_safety_risk", "authority_risk"):
            risk = _as_dict(risks.get(non_override))
            if risk.get("owner_can_accept") is not False:
                errors.append(f"{group}.{non_override}.owner_can_accept_not_false")
        if row.get("authority_boundary") != AUTHORITY_BOUNDARY:
            errors.append(f"{group}.authority_boundary_mismatch")
    return errors


def _with_defaults(row: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(row)
    output["actionable_now"] = False
    output["actionable_now_reason"] = ACTIONABLE_NOW_REASON
    output["authority_boundary"] = AUTHORITY_BOUNDARY
    output["risk_gaps"] = _normalize_risk_gaps(output.get("risk_gaps"))
    output["hard_blocks"] = [
        "stale runtime facts",
        "missing protection",
        "duplicate submit risk",
        "conflicting active position or open order",
        "out-of-scope StrategyGroup, symbol, side, profile, notional, or leverage",
        "authority bypass or credential/live-profile/sizing mutation",
    ]
    output["evidence_refs"] = _dedupe_evidence_refs(output.get("evidence_refs"))
    output["safety_invariants"] = {
        "real_order_authority": False,
        "calls_finalgate": False,
        "calls_operation_layer": False,
        "calls_exchange_write": False,
        "places_order": False,
    }
    return output


def _dedupe_evidence_refs(value: Any) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for ref in _dict_rows(value):
        path = str(ref.get("path") or "")
        if not path:
            continue
        kind = str(ref.get("kind") or "evidence")
        key = (path, kind)
        if key in seen:
            continue
        if any(existing.get("path") == path for existing in refs):
            continue
        seen.add(key)
        refs.append({"kind": kind, "path": path})
    return refs


def _normalize_risk_gaps(value: Any) -> dict[str, dict[str, Any]]:
    source = _as_dict(value)
    return {
        "strategy_quality_risk": {
            "owner_can_accept": True,
            "items": [str(item) for item in source.get("strategy_quality_risk") or []],
        },
        "fact_coverage_risk": {
            "owner_can_accept": True,
            "items": [str(item) for item in source.get("fact_coverage_risk") or []],
        },
        "economic_risk": {
            "owner_can_accept": True,
            "items": [str(item) for item in source.get("economic_risk") or []],
        },
        "execution_safety_risk": {
            "owner_can_accept": False,
            "items": [str(item) for item in source.get("execution_safety_risk") or []],
        },
        "authority_risk": {
            "owner_can_accept": False,
            "items": [str(item) for item in source.get("authority_risk") or []],
        },
    }


def _row_specs() -> list[dict[str, Any]]:
    return [
        _main_handoff_row(
            strategy_group_id="MPG-001",
            owner_label="动量延续",
            edge_thesis="Capture clean momentum continuation after member and group-pool confirmation.",
            trade_logic="Long-only continuation lane with exhaustion and concentration disables, protected by stop/exit plan.",
            regime_fit="Directional crypto momentum with clean 1h persistence and acceptable liquidity.",
            supported_sides=["long"],
            default_tier="L4",
            trial_eligible=True,
            required_facts_summary={
                "market": "latest price, recent 1h candles, closed candle timestamp, volume, mark, funding",
                "strategy": "member signal, group-pool selection, persistence, exhaustion disable, body extension, concentration",
                "risk": "fill gap, slippage, protection plan, exit plan",
                "account_exchange": "balance, position, open orders, symbol availability, min notional, step, tick, leverage limit",
            },
            promotion_gate="Already current first live-trial lane; live action still depends on runtime state only.",
            downshift_rule="Downshift if momentum exhaustion, concentration, stale facts, or protection/account conflicts appear.",
            park_rule="Park only after repeated no-edge reviews or Owner selects a different live lane.",
            kill_condition="Kill if live/replay outcomes show persistent false continuation after costs and protection.",
            evidence_refs=[
                _evidence("handoff", "docs/current/strategy-group-handoffs/MPG-001/handoff.json"),
                _evidence("replay", "docs/current/strategy-group-handoffs/MPG-001/replay/mpg-001-replay-corpus.json"),
                _evidence("tier_policy", "docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json"),
            ],
            risk_gaps={
                "strategy_quality_risk": ["false breakout", "fast reversal", "choppy no-trade regime"],
                "fact_coverage_risk": ["closed-candle and member-state freshness remain action-time runtime facts"],
                "economic_risk": ["fee, funding, fill-gap slippage, and min-size friction"],
                "execution_safety_risk": ["missing protection, stale account facts, open-order or active-position conflict"],
                "authority_risk": ["L4 tier still is not direct submit authority"],
            },
            evidence_status="reviewed_handoff_plus_replay",
            required_next_evidence="first allocated-subaccount live outcome when fresh signal and official runtime chain pass",
        ),
        _main_handoff_row(
            strategy_group_id="TEQ-001",
            owner_label="类股权永续动量",
            edge_thesis="Capture theme or basket momentum in equity-like perpetual products.",
            trade_logic="Long-only burst continuation with product eligibility, breadth, and overextension disables.",
            regime_fit="Theme momentum where product/session and concentration risks are acceptable.",
            supported_sides=["long"],
            default_tier="L2",
            trial_eligible=False,
            required_facts_summary={
                "market": "latest price, recent 1h candles, volume, mark, funding",
                "strategy": "theme momentum, basket breadth, concentration, session gap, product eligibility, overextension disable",
                "risk": "mark/funding review, session fill slippage, protection and exit plan",
                "account_exchange": "balance, position, open orders, symbol availability and exchange filters",
            },
            promotion_gate="Post-MPG review or explicit Owner lane change plus replay/live evidence that product/session risk is controlled.",
            downshift_rule="Downshift if product eligibility, breadth, or session gap facts are unavailable.",
            park_rule="Park while theme momentum evidence is thin or concentration risk dominates.",
            kill_condition="Kill if repeated review shows theme bursts fail after session and cost friction.",
            evidence_refs=[
                _evidence("handoff", "docs/current/strategy-group-handoffs/TEQ-001/handoff.json"),
                _evidence("tier_policy", "docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json"),
            ],
            risk_gaps={
                "strategy_quality_risk": ["low-history product momentum", "post-burst overextension", "symbol concentration"],
                "fact_coverage_risk": ["theme breadth, product eligibility, and session gap context"],
                "economic_risk": ["session fill slippage and funding/mark review"],
                "execution_safety_risk": ["runtime account, protection, and exchange filters remain hard stops"],
                "authority_risk": ["L2 shadow candidate evidence cannot create real-order authority"],
            },
            evidence_status="reviewed_handoff_partial_runtime_history",
            required_next_evidence="shadow outcomes and cost/session review before any L4 review",
        ),
        _main_handoff_row(
            strategy_group_id="FBS-001",
            owner_label="资金费率/基差压力",
            edge_thesis="Capture funding, basis, and crowding stress where derivatives pressure creates asymmetric continuation or unwind.",
            trade_logic="Observe derivatives stress; long lane is primary while short side remains disable/redesign-only.",
            regime_fit="Derivative crowding, negative funding, basis/premium stress, and settlement timing regimes.",
            supported_sides=["long", "short_disable_or_redesign_only"],
            default_tier="L3",
            trial_eligible=False,
            required_facts_summary={
                "market": "latest price, 1h candles, mark, funding window, basis/premium window, volume",
                "derivatives": "open interest, global long/short, top-trader ratio, negative funding crowding, settlement timing",
                "risk": "exchange margin/liquidation model, spread/liquidity downshift, mark deviation, protection plan",
                "account_exchange": "balance, position, open orders, symbol availability and exchange filters",
            },
            promotion_gate="Derivatives facts and margin/liquidation mapping must support a Decision Ledger promote/go-live review after P0 closure or Owner lane change.",
            downshift_rule="Downshift if derivatives facts are stale or settlement timing invalidates the setup.",
            park_rule="Park if crowding stress is absent or derivatives source quality is too weak.",
            kill_condition="Kill if stress signals repeatedly fail after funding, basis, and liquidation costs.",
            evidence_refs=[
                _evidence("handoff", "docs/current/strategy-group-handoffs/FBS-001/handoff.json"),
                _evidence("tier_policy", "docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json"),
            ],
            risk_gaps={
                "strategy_quality_risk": ["crowding stress may unwind before runtime capture", "short lane needs redesign"],
                "fact_coverage_risk": ["OI, long/short, top-trader, settlement, and margin/liquidation facts are heavy"],
                "economic_risk": ["funding, basis reversal, spread, and liquidation envelope"],
                "execution_safety_risk": ["protection, account, open-order, and exchange filter facts remain hard stops"],
                "authority_risk": ["L3 armed observation cannot place real orders without separate L4 eligibility"],
            },
            evidence_status="reviewed_handoff_derivatives_heavy",
            required_next_evidence="derivatives source reliability and cost-survival review",
        ),
        _main_handoff_row(
            strategy_group_id="SOR-001",
            owner_label="开盘区间结构",
            edge_thesis="Capture opening-range structure after session-specific breakout or revival conditions.",
            trade_logic="Session-window short lane with long-revival branch only when branch conditions are satisfied.",
            regime_fit="TradFi-linked session opens with closed range bars, trigger bar, and post-open decay control.",
            supported_sides=["short", "long_revival_only"],
            default_tier="L3",
            trial_eligible=False,
            required_facts_summary={
                "market": "latest price, 1h candles, closed open-range bars, closed trigger bar, volume, mark, funding",
                "strategy": "session range, breakout trigger, tradfi session mapping, post-open decay disable, time-stop horizon",
                "risk": "session gap fill, mark/funding session review, protection and exit plan",
                "account_exchange": "balance, position, open orders, symbol availability and exchange filters",
            },
            promotion_gate="Session branch evidence and post-open decay review must support tier review; no L4 before P0 closure or Owner lane change.",
            downshift_rule="Downshift outside valid session/structure window or when trigger bars are not closed.",
            park_rule="Park if session conditions cannot be mapped reliably.",
            kill_condition="Kill if session breakouts repeatedly reverse after gap/fill and time-stop review.",
            evidence_refs=[
                _evidence("handoff", "docs/current/strategy-group-handoffs/SOR-001/handoff.json"),
                _evidence("tier_policy", "docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json"),
            ],
            risk_gaps={
                "strategy_quality_risk": ["session false breakout", "post-open decay", "branch-specific long revival uncertainty"],
                "fact_coverage_risk": ["closed open range, trigger bar, and session mapping must be fresh"],
                "economic_risk": ["session gap fill, mark/funding, slippage around session open"],
                "execution_safety_risk": ["closed-bar freshness, protection, account, and exchange filters remain hard stops"],
                "authority_risk": ["L3 conditional observation is not live submit authority"],
            },
            evidence_status="reviewed_handoff_session_conditional",
            required_next_evidence="session replay/outcome review before any higher-tier decision",
        ),
        _main_handoff_row(
            strategy_group_id="PMR-001",
            owner_label="贵金属制度覆盖",
            edge_thesis="Use precious-metal regime behavior as an overlay or selected directional context.",
            trade_logic="Short lane is primary; long is context-only until target-specific role and facts mature.",
            regime_fit="Commodity-style regimes, silver/gold dominance splits, and regular-session breakdowns.",
            supported_sides=["short", "long_context_only"],
            default_tier="L1",
            trial_eligible=False,
            required_facts_summary={
                "market": "latest price, 1h candles, mark, funding, volume",
                "strategy": "metal role split, XAG dominance, regular breakdown, overlay disable, commodity session gap",
                "risk": "mark deviation, session fill slippage, protection and exit plan",
                "account_exchange": "balance, position, open orders, symbol availability and exchange filters",
            },
            promotion_gate="Clarify target-specific role and attach reliable session/mark facts before L2 review.",
            downshift_rule="Remain observe-only when overlay role or session facts are unclear.",
            park_rule="Park if it only provides context and does not change runtime decisions.",
            kill_condition="Kill if overlay signals fail to improve StrategyGroup decisions or outcomes.",
            evidence_refs=[
                _evidence("handoff", "docs/current/strategy-group-handoffs/PMR-001/handoff.json"),
                _evidence("tier_policy", "docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json"),
            ],
            risk_gaps={
                "strategy_quality_risk": ["overlay may not translate into standalone trade edge", "long side is context-only"],
                "fact_coverage_risk": ["metal role split, XAG dominance, and commodity session gap facts"],
                "economic_risk": ["session fill slippage and mark deviation"],
                "execution_safety_risk": ["account, protection, and exchange facts remain hard stops"],
                "authority_risk": ["L1 observe-only cannot create candidates or orders"],
            },
            evidence_status="reviewed_handoff_observe_overlay",
            required_next_evidence="role-specific replay and fact maturity before tier review",
        ),
        _main_handoff_row(
            strategy_group_id="BTPC-001",
            owner_label="熊市回抽延续",
            edge_thesis="Capture bear-trend pullback continuation when weak rally loses structure and derivatives/crowding context is reviewable.",
            trade_logic="Short-only L2 shadow lane using pullback structure loss, strong-uptrend disable, squeeze review, and derivatives facts.",
            regime_fit="Downtrend continuation after weak rally or pullback, excluding strong upside reclaim regimes.",
            supported_sides=["short"],
            default_tier="L2",
            trial_eligible=False,
            required_facts_summary={
                "market": "price, 1h/4h candles, closed candle timestamp, volume, mark, funding",
                "strategy": "bear trend context, weak rally depth, structure loss, strong uptrend disable, squeeze disable",
                "derivatives": "funding, premium, OI/crowding proxy, squeeze risk, historical OI, long/short, top-trader ratio",
                "risk_account_exchange": "margin/liquidation model, slippage, protection, account state, exchange filters",
            },
            promotion_gate="Complete live derivatives fact-source mapping, classifier review, and Decision Ledger revise resolution before higher-tier review.",
            downshift_rule="Downshift if strong-uptrend conflict, stale signal, squeeze risk, or derivatives facts invalidate review.",
            park_rule="Park if proxy replay or live derivatives source review shows no durable right-tail edge.",
            kill_condition="Kill if bear-pullback would-enter cases fail after derivatives, squeeze, freshness, and cost review.",
            evidence_refs=[
                _evidence("handoff", "docs/current/strategy-group-handoffs/BTPC-001/handoff.json"),
                _evidence("replay", "docs/current/strategy-group-handoffs/BTPC-001/replay/btpc-001-l2-replay-corpus.json"),
                _evidence("decision", "output/runtime-monitor/latest-btpc-l2-keep-revise-fact-source-decision.json"),
                _evidence("ledger", "output/runtime-monitor/latest-strategygroup-decision-ledger.json"),
            ],
            risk_gaps={
                "strategy_quality_risk": ["strong-uptrend conflict", "stale signal handling", "short squeeze classifier quality"],
                "fact_coverage_risk": ["historical OI, global long/short, top-trader ratio, live margin/liquidation model"],
                "economic_risk": ["funding, spread, slippage, leverage survival, liquidation envelope"],
                "execution_safety_risk": ["live facts, protection, account state, and exchange filters remain runtime-only"],
                "authority_risk": ["L2 proxy/replay evidence cannot authorize L4, FinalGate, Operation Layer, or order submit"],
            },
            evidence_status="reviewed_l2_handoff_plus_proxy_replay_decision",
            required_next_evidence="execute BTPC L2 fact-source and classifier review tasks locally",
        ),
        _observe_replay_row(
            strategy_group_id="VCB-001",
            owner_label="波动压缩突破",
            edge_thesis="Capture compression breakout when true breakout evidence survives false-breakout disable review.",
            trade_logic="Observe long-side breakout candidates; revise false-breakout disable and cost review before L2.",
            regime_fit="Volatility compression, breakout close, and volume expansion regimes.",
            supported_sides=["long"],
            default_tier="L1",
            replay_ref="docs/current/strategy-group-handoffs/VCB-001/replay/vcb-001-l1-observe-replay-corpus.json",
            ledger_decision="keep_observing",
            promotion_gate="False-breakout disable and economic replay must remain stable before L2 review.",
            risk_gaps={
                "strategy_quality_risk": ["false breakout reversal", "breakout close confirmation fragility"],
                "fact_coverage_risk": ["compression context, volume expansion, disable state"],
                "economic_risk": ["cost m2m, fee, slippage, funding, fill-slot assumptions"],
                "execution_safety_risk": ["runtime facts and protection remain hard stops"],
                "authority_risk": ["L1 observe-only evidence cannot create shadow candidate or real order"],
            },
        ),
        _observe_replay_row(
            strategy_group_id="LSR-001",
            owner_label="流动性扫盘/短线复活",
            edge_thesis="Capture liquidity sweep or short-revival setups after side-specific rewrite quality is proven.",
            trade_logic="Observe sweep/reclaim cases; keep short-revival rewrite and cost review as promotion prerequisites.",
            regime_fit="Liquidity sweep, reclaim, and short-revival structures where range context is known.",
            supported_sides=["long_observe", "short_revival_review"],
            default_tier="L1",
            replay_ref="docs/current/strategy-group-handoffs/LSR-001/replay/lsr-001-l1-observe-replay-corpus.json",
            ledger_decision="keep_observing",
            promotion_gate="Side-specific classifier rewrite and economic replay must support non-executing L2 review.",
            risk_gaps={
                "strategy_quality_risk": ["lookahead proxy failure", "short-revival classifier fragility", "range context missing"],
                "fact_coverage_risk": ["liquidity sweep confirmation, reclaim context, disable state"],
                "economic_risk": ["fee, slippage, funding, fill-slot, leverage survival"],
                "execution_safety_risk": ["runtime facts and protection remain hard stops"],
                "authority_risk": ["L1 observe-only evidence cannot create shadow candidate or real order"],
            },
        ),
        _observe_replay_row(
            strategy_group_id="BRF-001",
            owner_label="熊市反弹失败",
            edge_thesis="Capture short continuation after a bear-market rally fails instead of shorting early breakdowns.",
            trade_logic="Observe rally failure and squeeze-risk cases; require context and classifier quality before L2.",
            regime_fit="Bear rally failure, rejection, and structure-extreme regimes.",
            supported_sides=["short"],
            default_tier="L1",
            replay_ref="docs/current/strategy-group-handoffs/BRF-001/replay/brf-001-l1-observe-replay-corpus.json",
            ledger_decision="keep_observing",
            promotion_gate="Rally context, squeeze-risk classifier, and cost replay must be attached before L2 review.",
            risk_gaps={
                "strategy_quality_risk": ["rally failure context may be weak", "short squeeze risk"],
                "fact_coverage_risk": ["rally high/rejection context and squeeze-risk classifier"],
                "economic_risk": ["cost/fill/leverage boundary missing"],
                "execution_safety_risk": ["runtime facts and protection remain hard stops"],
                "authority_risk": ["L1 observe-only evidence cannot create shadow candidate or real order"],
            },
        ),
        _observe_replay_row(
            strategy_group_id="RBR-001",
            owner_label="区间边界回归",
            edge_thesis="Range-boundary reversion vocabulary kept only if materially new edge evidence appears.",
            trade_logic="Currently parked vocabulary; do not allocate active review until new evidence changes decision.",
            regime_fit="Calm range boundary rejection regimes, currently weak or negative in review.",
            supported_sides=["short_review"],
            default_tier="L1",
            replay_ref="output/runtime-monitor/latest-strategygroup-decision-ledger.json",
            ledger_decision="park",
            promotion_gate="Materially new positive replay or live-observation evidence is required before unpark.",
            risk_gaps={
                "strategy_quality_risk": ["weak edge evidence", "negative or low-priority review", "range-quality uncertainty"],
                "fact_coverage_risk": ["trend invalidation and range quality facts missing"],
                "economic_risk": ["calm-range m2m failed and cost survival uncertain"],
                "execution_safety_risk": ["runtime facts and protection remain hard stops"],
                "authority_risk": ["parked L1 vocabulary has no candidate or order authority"],
            },
            evidence_status="partial_generated_decision_only",
            required_next_evidence="new edge evidence strong enough to reopen active review",
        ),
    ]


def _main_handoff_row(**kwargs: Any) -> dict[str, Any]:
    return {
        **kwargs,
        "trade_logic": kwargs["trade_logic"],
    }


def _observe_replay_row(
    *,
    strategy_group_id: str,
    owner_label: str,
    edge_thesis: str,
    trade_logic: str,
    regime_fit: str,
    supported_sides: list[str],
    default_tier: str,
    replay_ref: str,
    ledger_decision: str,
    promotion_gate: str,
    risk_gaps: dict[str, list[str]],
    evidence_status: str = "partial_replay_and_decision_evidence",
    required_next_evidence: str = "post-revision stage review before any tier change",
) -> dict[str, Any]:
    return {
        "strategy_group_id": strategy_group_id,
        "owner_label": owner_label,
        "edge_thesis": edge_thesis,
        "trade_logic": trade_logic,
        "regime_fit": regime_fit,
        "supported_sides": supported_sides,
        "default_tier": default_tier,
        "trial_eligible": False,
        "required_facts_summary": {
            "strategy": "partial; see replay corpus and current Decision Ledger evidence",
            "market": "partial; runtime observation facts remain lower-level evidence",
            "risk_account_exchange": "runtime-only before any live or shadow authority",
        },
        "promotion_gate": promotion_gate,
        "downshift_rule": "Keep at L1 or park when replay, facts, classifier, or cost evidence is insufficient.",
        "park_rule": "Park when evidence is weak, negative, low-priority, or not tied to right-tail opportunity.",
        "kill_condition": "Kill if replay/live outcomes repeatedly contradict the edge after facts and costs are reviewed.",
        "evidence_refs": [
            _evidence("replay_or_generated_view", replay_ref),
            _evidence("ledger", "output/runtime-monitor/latest-strategygroup-decision-ledger.json"),
        ],
        "risk_gaps": risk_gaps,
        "evidence_status": evidence_status,
        "required_next_evidence": required_next_evidence,
        "current_decision_ref": ledger_decision,
    }


def _evidence(kind: str, path: str) -> dict[str, str]:
    return {"kind": kind, "path": path}


def _summary_table(rows: list[dict[str, Any]]) -> str:
    output = [
        "| StrategyGroup | 策略含义 | 层级 | 可试运行 | 当前可行动性 `actionable_now` | 证据状态 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        output.append(
            "| `{}` | {} | `{}` | `{}` | `{}` | `{}` |".format(
                row.get("strategy_group_id"),
                row.get("owner_label"),
                row.get("default_tier"),
                str(row.get("trial_eligible")).lower(),
                str(row.get("actionable_now")).lower(),
                row.get("evidence_status"),
            )
        )
    return "\n".join(output)


def _row_section(row: dict[str, Any]) -> list[str]:
    risks = _as_dict(row.get("risk_gaps"))
    risk_summary = "; ".join(
        f"{key}: {', '.join(_as_dict(risks.get(key)).get('items') or []) or 'none'}"
        for key in RISK_CLASS_KEYS
    )
    refs = ", ".join(
        f"`{ref.get('path')}`" for ref in _dict_rows(row.get("evidence_refs"))
    )
    return [
        f"### `{row.get('strategy_group_id')}` {row.get('owner_label')}",
        "",
        f"- 策略边际: {row.get('edge_thesis')}",
        f"- 交易逻辑: {row.get('trade_logic')}",
        f"- 适用市场结构: {row.get('regime_fit')}",
        f"- 层级 / 可试运行: `{row.get('default_tier')}` / `{str(row.get('trial_eligible')).lower()}`",
        "- 当前可行动性: `false`，只能由运行时根据当前实盘状态判断",
        f"- 晋级条件: {row.get('promotion_gate')}",
        f"- 降级 / 停放 / 淘汰: {row.get('downshift_rule')} / {row.get('park_rule')} / {row.get('kill_condition')}",
        f"- 风险缺口: {risk_summary}",
        f"- 下一证据: {row.get('required_next_evidence')}",
        f"- 证据引用: {refs}",
        "",
    ]


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return payload


def _write_files(packet: dict[str, Any], json_path: Path, md_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(build_owner_markdown(packet), encoding="utf-8")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value or [] if isinstance(row, dict)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate existing output files instead of writing them.",
    )
    args = parser.parse_args(argv)

    json_path = Path(args.output_json).expanduser()
    md_path = Path(args.output_md).expanduser()
    expected = build_registry_baseline()
    errors = validate_packet(expected)
    if args.check:
        if not json_path.exists():
            errors.append(f"missing_json:{json_path}")
        if not md_path.exists():
            errors.append(f"missing_markdown:{md_path}")
        if json_path.exists():
            existing = _load_json(json_path)
            if existing != expected:
                errors.append("json_output_drift")
            errors.extend(validate_packet(existing))
        if md_path.exists():
            markdown = md_path.read_text(encoding="utf-8")
            for group in EXPECTED_GROUPS:
                if group not in markdown:
                    errors.append(f"markdown_missing_group:{group}")
            if "actionable_now" not in markdown:
                errors.append("markdown_missing_actionable_boundary")
    else:
        _write_files(expected, json_path, md_path)

    report = {
        "status": "passed" if not errors else "failed",
        "scope": "strategygroup_registry_baseline",
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "row_count": len(expected["rows"]),
        "errors": errors,
        "safety_invariants": expected["safety_invariants"],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
