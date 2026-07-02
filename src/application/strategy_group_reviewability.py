from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.application.strategy_group_live_readonly_observation import (
    build_strategy_group_live_readonly_observation_v1,
)


class StrategyGroupCandidateEvidence(BaseModel):
    candidate_id: str
    strategy_group_id: str
    symbol: str
    side: str
    review_status: str
    evidence_summary: str
    metrics: dict[str, str] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    confidence_flags: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)


class StrategyGroupReviewabilityItem(BaseModel):
    strategy_group_id: str
    strategy_group_name: str
    plain_language_summary: str
    market_regime_it_eats: str
    market_regime_it_hates: str
    representative_candidates: list[str]
    current_status: str
    evidence_summary: str
    key_risks: list[str] = Field(default_factory=list)
    confidence_flags: list[str] = Field(default_factory=list)
    owner_action_options: list[str] = Field(default_factory=list)
    next_recommended_action: str
    not_allowed_now: list[str] = Field(default_factory=list)
    evidence_reviewability: str
    live_readonly_observation_readiness: str
    bounded_trial_readiness: str
    main_blockers: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    display_model_only: Literal[True] = True
    not_runtime_source_of_truth: Literal[True] = True
    no_execution_permission: Literal[True] = True
    no_order_permission: Literal[True] = True
    no_runtime_start: Literal[True] = True
    no_automatic_strategy_routing: Literal[True] = True


class StrategyGroupReviewabilityResponse(BaseModel):
    generated_from: str = "read_only_strategy_group_reviewability_snapshot"
    primary_groups: list[StrategyGroupReviewabilityItem]
    secondary_groups: list[StrategyGroupReviewabilityItem]
    candidate_evidence: list[StrategyGroupCandidateEvidence]
    observation_chain_summary: dict[str, object] = Field(default_factory=dict)
    non_permissions: dict[str, bool] = Field(default_factory=dict)
    source_refs: list[str] = Field(default_factory=list)
    live_ready: Literal[False] = False


_COST_BASELINE = "reports/directional-opportunity-broad-smoke-20260529/cost_baseline_enrichment.md"
_BNB_SOL_REVIEW = "reports/directional-opportunity-broad-smoke-20260529/mi001_bnb_sol_evidence_reviewability.md"
_SHELF_REPORT = "reports/directional-opportunity-broad-smoke-20260529/strategy_group_shelf_result.md"
_TRIAL_CANDIDATES = "reports/directional-opportunity-broad-smoke-20260529/trial_candidate_with_known_risks_v2.md"
_CPM_OOS = "docs/ops/crypto-pullback-module-v1-oos-failure-classification.md"
_CPM_CONTEXT = "docs/ops/cpm-1-readonly-feature-context-extraction-report.md"
def build_strategy_group_reviewability_snapshot() -> StrategyGroupReviewabilityResponse:
    """Return the Owner-reviewable strategy group shelf.

    The snapshot is intentionally read-only and display-oriented. It summarizes
    current report evidence and readiness blockers without becoming a runtime
    strategy registry, trial-start source, execution permission source, or order
    route.
    """

    observation_v1 = build_strategy_group_live_readonly_observation_v1()
    primary_groups = [
        StrategyGroupReviewabilityItem(
            strategy_group_id="MI-001",
            strategy_group_name="Momentum Impulse",
            plain_language_summary="Strong close-to-close momentum impulse followed by possible 72h / 7d continuation in high-beta assets.",
            market_regime_it_eats="Strong trend, right-tail continuation, high-beta follow-through, markets willing to chase winners.",
            market_regime_it_hates="Momentum exhaustion, sharp reversal after crowded moves, fake breakout, thin-liquidity squeeze reversal.",
            representative_candidates=["MI-001 SOL long", "MI-001 BNB long"],
            current_status="primary_chain_candidate / strong_smoke_candidate",
            evidence_summary=(
                "SOL is the current chain sample with continuous 2021-2026 coverage; "
                "BNB coverage was repaired with public Binance UM futures 1h klines and remains a strong review-only observation candidate."
            ),
            key_risks=[
                "high MAE / adverse path risk",
                "right-tail dependence",
                "signal density and dedup still need review",
                "BNB year-split fragility after coverage repair",
            ],
            confidence_flags=[
                "SOL chain sample, not the only primary strategy",
                "SOL high MAE remains a bounded-trial risk disclosure",
                "BNB coverage repaired; review 2025 weakness and top-tail dependence before any admission",
            ],
            owner_action_options=[
                "Review MI-001 SOL current chain sample",
                "Compare BNB repaired-coverage evidence",
                "Keep BNB in MI as a strong observation candidate",
            ],
            next_recommended_action="Owner review of BNB repaired coverage evidence",
            not_allowed_now=[
                "trial start",
                "execution intent creation",
                "order placement",
                "automatic BNB promotion",
                "strategy self-elevation",
            ],
            evidence_reviewability="reviewable_with_known_risks",
            live_readonly_observation_readiness="live_readonly_observation_v1_ready_runner_retired",
            bounded_trial_readiness="SOL chain sample has bounded-trial metadata; BNB remains review-only after coverage repair",
            main_blockers=[
                "MI read-only evaluator glue is wired, but live observation runner/sink is not bound or scheduled",
                "SOL signal density/dedup review remains open",
                "BNB repaired evidence still needs Owner review for 2025 weakness, top-tail dependence, and campaign replay gap",
            ],
            source_refs=[
                "src/application/strategy_group_live_readonly_observation.py",
                _BNB_SOL_REVIEW,
                _COST_BASELINE,
                _TRIAL_CANDIDATES,
                _SHELF_REPORT,
            ],
        ),
        StrategyGroupReviewabilityItem(
            strategy_group_id="VI-001",
            strategy_group_name="Volume Impulse",
            plain_language_summary="Volume expansion plus price impulse, used as a quieter backup observation line rather than the current primary trial chain.",
            market_regime_it_eats="Volume expansion with directional follow-through and participation confirming price continuation.",
            market_regime_it_hates="News spikes, blow-off volume, volume without price confirmation, cost-sensitive short-lived moves.",
            representative_candidates=["VI-001 ETH long"],
            current_status="backup_observation_candidate",
            evidence_summary="ETH long is positive but thinner and cost-sensitive; it is not auto-parked just because costs matter.",
            key_risks=["thin edge after costs", "volume spike chasing", "missing taker/OI/funding confirmation"],
            confidence_flags=["cost-sensitive backup observation", "positive but not current mainline"],
            owner_action_options=["Review ETH evidence", "Keep as backup observation", "Compare against MI after coverage repair"],
            next_recommended_action="Keep as backup observation; do not replace MI automatically.",
            not_allowed_now=["trial start", "automatic MI replacement", "execution path wiring"],
            evidence_reviewability="reviewable_but_cost_sensitive",
            live_readonly_observation_readiness="backup_requires_signal_glue",
            bounded_trial_readiness="not_first_trial_line",
            main_blockers=["VI signal evaluator glue is not wired", "edge is cost-sensitive"],
            source_refs=[_COST_BASELINE, _SHELF_REPORT],
        ),
        StrategyGroupReviewabilityItem(
            strategy_group_id="CPM-RO-001",
            strategy_group_name="Owner Special Observation",
            plain_language_summary="Owner-directed pullback / calmer-market observation line for market validation and bounded review, not proven alpha.",
            market_regime_it_eats="Low-slope, lower-volatility trend continuation after pullback repair.",
            market_regime_it_hates="Aggressive high-slope trend, deep corrections, regime breaks, volatile continuation failure.",
            representative_candidates=["CPM read-only observation"],
            current_status="owner_special_observation",
            evidence_summary="CPM historical OOS 2021/2022 was negative; current status is Owner special observation, not proven alpha.",
            key_risks=["OOS 2021/2022 negative", "not proven alpha", "not runtime eligible by default"],
            confidence_flags=["Owner special observation rationale", "historical OOS negative warning", "not_proven_alpha"],
            owner_action_options=["Read-only observation", "Market validation", "Bounded review only"],
            next_recommended_action="Keep as special read-only observation; do not promote to runtime eligibility.",
            not_allowed_now=["runtime eligibility by default", "trial start", "execution wiring", "alpha claim"],
            evidence_reviewability="reviewable_with_negative_oos_disclosure",
            live_readonly_observation_readiness="live_readonly_observation_v1_ready_runner_retired",
            bounded_trial_readiness="not_runtime_eligible_by_default",
            main_blockers=[
                "negative OOS disclosure",
                "CPM evaluator glue is wired, but live observation runner/sink is not bound or scheduled",
                "not runtime eligible by default",
            ],
            source_refs=[
                "src/application/strategy_group_live_readonly_observation.py",
                _CPM_OOS,
                _CPM_CONTEXT,
                _SHELF_REPORT,
            ],
        ),
        StrategyGroupReviewabilityItem(
            strategy_group_id="TB",
            strategy_group_name="Trend Breakout",
            plain_language_summary="Breakout continuation family kept for future review after MI/VI evidence is settled.",
            market_regime_it_eats="Clean breakout from range into sustained trend and participation follow-through.",
            market_regime_it_hates="False breakouts, range chop, late entries after exhausted moves.",
            representative_candidates=["TB-001", "TB-002"],
            current_status="research_pool / keep_for_later",
            evidence_summary="TB-002 BNB ranked strongly in broad smoke, but this family remains research pool.",
            key_risks=["false breakout", "late entry", "BNB coverage comparability", "missing costs/funding replay"],
            confidence_flags=["future live read-only observation candidate only after frozen evaluator"],
            owner_action_options=["Keep for later review", "Compare after MI/VI work", "Freeze breakout evaluator first"],
            next_recommended_action="Keep in research pool; do not admit yet.",
            not_allowed_now=["trial start", "runtime connection", "parameter optimization"],
            evidence_reviewability="coarse_review_only",
            live_readonly_observation_readiness="live_readonly_candidate_requires_signal_glue",
            bounded_trial_readiness="not_current_trial_candidate",
            main_blockers=["frozen evaluator missing", "not admitted", "coverage/cost replay incomplete"],
            source_refs=[_SHELF_REPORT, _COST_BASELINE],
        ),
        StrategyGroupReviewabilityItem(
            strategy_group_id="PC",
            strategy_group_name="Pullback Continuation",
            plain_language_summary="Trend pullback continuation ideas kept as research pool, separate from CPM rescue.",
            market_regime_it_eats="Trend remains intact, pullback holds structure, continuation resumes without regime damage.",
            market_regime_it_hates="Trend failure, pullback becomes reversal, broad chop, adverse path overlap with CPM issues.",
            representative_candidates=["PC-001", "PC-002"],
            current_status="research_pool",
            evidence_summary="PC-002 SOL appeared in broad smoke but is not a current trial candidate and is not CPM rescue.",
            key_risks=["may drift into long-beta continuation", "MAE risk", "entry timing ambiguity", "CPM overlap risk"],
            confidence_flags=["future observation candidate only after independent frozen hypothesis"],
            owner_action_options=["Keep as later family review", "Review evidence only", "Freeze separate hypothesis before work"],
            next_recommended_action="Park in research pool.",
            not_allowed_now=["CPM rescue", "trial start", "runtime connection", "parameter sweep"],
            evidence_reviewability="coarse_review_only",
            live_readonly_observation_readiness="research_pool_requires_frozen_evaluator",
            bounded_trial_readiness="not_current_trial_candidate",
            main_blockers=["not admitted", "independent hypothesis missing"],
            source_refs=[_SHELF_REPORT],
        ),
        StrategyGroupReviewabilityItem(
            strategy_group_id="VB",
            strategy_group_name="Volatility Breakout",
            plain_language_summary="Volatility expansion family kept as non-pure-momentum comparison pool.",
            market_regime_it_eats="Compression then expansion with directional continuation and clean quality filter.",
            market_regime_it_hates="Late expansion chase, fake squeeze, low-quality volatility spikes.",
            representative_candidates=["VB-001"],
            current_status="research_pool",
            evidence_summary="Positive broad-smoke long rows exist, but below MI/VI/TB reference lines.",
            key_risks=["late expansion chase", "missing volatility-quality filter", "missing funding/OI/cost replay"],
            confidence_flags=["comparison group only", "not admitted"],
            owner_action_options=["Keep as comparison group", "Add quality filter later", "Review broad smoke only"],
            next_recommended_action="Keep for later; no new variant now.",
            not_allowed_now=["trial start", "runtime connection", "Tier 1 download", "execution wiring"],
            evidence_reviewability="coarse_review_only",
            live_readonly_observation_readiness="research_pool_requires_evidence",
            bounded_trial_readiness="not_current_trial_candidate",
            main_blockers=["not admitted", "quality filter missing", "Tier 1 context missing"],
            source_refs=[_SHELF_REPORT],
        ),
    ]

    secondary_groups = [
        StrategyGroupReviewabilityItem(
            strategy_group_id="MR/RB",
            strategy_group_name="Mean Reversion / Range Boundary",
            plain_language_summary="Mean reversion and range-boundary rejection remain secondary because current variants are weak or under-specified.",
            market_regime_it_eats="High-quality range, boundary rejection, controlled overextension then reversion.",
            market_regime_it_hates="Strong trend breakout, boundary failure, adverse trend continuation.",
            representative_candidates=["MR-001", "RB-001"],
            current_status="weak_or_secondary / needs better variant",
            evidence_summary="RB has secondary positive rows; MR lacks a current trial candidate.",
            key_risks=["catching falling knives", "poor boundary quality", "add-to-loser temptation"],
            confidence_flags=["secondary shelf only", "needs better variant"],
            owner_action_options=["Park", "Wait for new hypothesis", "Review as secondary only"],
            next_recommended_action="Park until a better variant is proposed.",
            not_allowed_now=["trial start", "averaging down", "execution connection"],
            evidence_reviewability="secondary_review_only",
            live_readonly_observation_readiness="not_observation_ready",
            bounded_trial_readiness="not_current_trial_candidate",
            main_blockers=["variant hypothesis missing", "adverse-path risk"],
            source_refs=[_SHELF_REPORT],
        ),
        StrategyGroupReviewabilityItem(
            strategy_group_id="Tier1-Data-Families",
            strategy_group_name="Tier 1 Data Families",
            plain_language_summary="Funding, OI, taker flow, long-short, basis/premium, and attention/search data families are request-ready context, not admitted strategies.",
            market_regime_it_eats="Crowding, carry, participation, premium, and attention context that can improve review quality.",
            market_regime_it_hates="Missing data, timestamp mismatch, provider semantics drift, lookahead risk.",
            representative_candidates=[
                "Funding",
                "OI",
                "Taker flow",
                "Long-short ratio",
                "Basis / premium",
                "Attention / search",
            ],
            current_status="data_request_ready / not_downloaded / not_admitted",
            evidence_summary="Tier 1 data requests are ready, but no data is downloaded, ingested, or admitted.",
            key_risks=["provider semantics", "timestamp alignment", "lookahead", "normalization/revision risk"],
            confidence_flags=["request-ready", "not downloaded", "not admitted"],
            owner_action_options=["Review data request", "Authorize data download separately", "Keep unavailable risk label"],
            next_recommended_action="Wait for separate Owner approval before any Tier 1 data download.",
            not_allowed_now=["download data", "write DB", "admit strategy", "execution connection"],
            evidence_reviewability="request_ready_not_observed",
            live_readonly_observation_readiness="not_observation_ready",
            bounded_trial_readiness="not_strategy_family_admitted",
            main_blockers=["data not downloaded", "not admitted", "semantics not validated"],
            source_refs=[_SHELF_REPORT],
        ),
    ]

    candidate_evidence = [
        StrategyGroupCandidateEvidence(
            candidate_id="MI-001-SOL-LONG",
            strategy_group_id="MI-001",
            symbol="SOL/USDT:USDT",
            side="long",
            review_status="current_chain_sample_with_known_risks",
            evidence_summary="Continuous SOL coverage and review chain; costs acceptable, but high MAE and signal density/dedup remain blockers.",
            metrics={
                "signal_count": "8135",
                "mean_72h": "1.9531",
                "positive_rate_72h": "0.5175",
                "mean_7d": "4.7372",
                "positive_rate_7d": "0.5398",
                "net_72h_baseline": "1.5831",
                "net_72h_stress": "1.4181",
                "mae_72h": "-7.8922",
            },
            limitations=["no full campaign replay", "high MAE", "signal density/dedup blocker"],
            confidence_flags=["chain sample", "not the only primary strategy"],
            source_refs=[_COST_BASELINE],
        ),
        StrategyGroupCandidateEvidence(
            candidate_id="MI-001-BNB-LONG",
            strategy_group_id="MI-001",
            symbol="BNB/USDT:USDT",
            side="long",
            review_status="strong_smoke_candidate_with_repaired_coverage",
            evidence_summary="BNB coverage repaired across the 2021-2026 local review span; evidence remains strong but review-only due 2025 weakness, top-tail sensitivity, and campaign replay gap.",
            metrics={
                "signal_count": "4166",
                "mean_24h": "0.8087",
                "positive_rate_24h": "0.4851",
                "mean_72h": "2.4074",
                "positive_rate_72h": "0.5470",
                "mean_7d": "5.4482",
                "positive_rate_7d": "0.5552",
                "net_72h_baseline": "2.0374",
                "net_72h_stress": "1.8724",
                "mae_72h": "-5.9467",
                "mfe_72h": "8.7626",
                "dedup_signal_count": "714",
            },
            limitations=["2025 72h year split negative", "top-tail dependency", "campaign replay missing"],
            confidence_flags=["coverage_repaired_not_runtime_ready", "review_2025_weakness_before_admission"],
            source_refs=[_BNB_SOL_REVIEW, _COST_BASELINE, _TRIAL_CANDIDATES],
        ),
        StrategyGroupCandidateEvidence(
            candidate_id="VI-001-ETH-LONG",
            strategy_group_id="VI-001",
            symbol="ETH/USDT:USDT",
            side="long",
            review_status="backup_observation_candidate",
            evidence_summary="Positive ETH volume impulse backup, but edge is thinner and more cost-sensitive than MI.",
            metrics={
                "signal_count": "1277",
                "mean_72h": "1.1164",
                "positive_rate_72h": "0.5348",
                "mean_7d": "2.2386",
                "positive_rate_7d": "0.5357",
                "net_72h_baseline": "0.7464",
                "net_72h_stress": "0.5814",
                "mae_72h": "-4.60",
            },
            limitations=["cost-sensitive", "thin edge", "backup only"],
            confidence_flags=["not auto-parked by cost sensitivity"],
            source_refs=[_COST_BASELINE],
        ),
        StrategyGroupCandidateEvidence(
            candidate_id="CPM-RO-001",
            strategy_group_id="CPM-RO-001",
            symbol="ETH/USDT:USDT",
            side="long",
            review_status="owner_special_observation_not_proven_alpha",
            evidence_summary="Owner special observation despite negative CPM historical OOS 2021/2022; not runtime eligible by default.",
            metrics={
                "historical_oos_2021_2022": "negative",
                "current_observation_hypothesis": "calmer pullback-continuation validation",
                "useful_validation": "clean no-action/would-enter samples with follow-through review",
            },
            limitations=["not proven alpha", "not runtime eligible by default", "negative OOS disclosure required"],
            confidence_flags=["owner_special_observation", "not_proven_alpha", "oos_negative_warning"],
            source_refs=[_CPM_OOS, _CPM_CONTEXT],
        ),
    ]

    return StrategyGroupReviewabilityResponse(
        primary_groups=primary_groups,
        secondary_groups=secondary_groups,
        candidate_evidence=candidate_evidence,
        observation_chain_summary={
            "can_record_metadata_and_evidence_without_orders": True,
            "active_live_readonly_observation": False,
            "strategy_specific_signal_evaluator_glue_wired": True,
            "legacy_runner_retired": True,
            "observation_sink_wired_for_strategy_specific_events": False,
            "observation_v1_endpoint": "/api/brc/strategy-groups/live-readonly-observation/v1",
            "observation_v1_candidates": [
                candidate.model_dump(mode="json") for candidate in observation_v1.candidates
            ],
            "readiness_status": "observation_v1_ready_runner_retired",
            "execution_intent_created": False,
            "order_created": False,
            "runtime_started": False,
        },
        non_permissions={
            "no_trial_start": True,
            "no_execution_intent": True,
            "no_order_permission": True,
            "no_runtime_start": True,
            "no_automatic_strategy_routing": True,
            "no_symbol_side_leverage_expansion": True,
        },
        source_refs=[_BNB_SOL_REVIEW, _COST_BASELINE, _SHELF_REPORT, _TRIAL_CANDIDATES, _CPM_OOS],
    )
