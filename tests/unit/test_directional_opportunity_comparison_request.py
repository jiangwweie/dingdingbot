from __future__ import annotations

import pytest

from src.domain.directional_opportunity_comparison_request import (
    DirectionalOpportunityComparisonRequest,
    build_directional_opportunity_comparison_request,
)
from src.domain.directional_opportunity_pack import (
    DirectionalPackCandidateRole,
    btc_eth_sol_bnb_directional_opportunity_pack,
)
from src.domain.strategy_family_signal import SignalSide


def test_builds_single_directional_opportunity_comparison_request():
    request = build_directional_opportunity_comparison_request(
        spec=btc_eth_sol_bnb_directional_opportunity_pack(),
        candidate_family_id="VB-001",
        symbol="SOL/USDT:USDT",
        side="long",
        base_timeframe="1h",
    )

    assert request.candidate_family_id == "VB-001"
    assert request.candidate_role == DirectionalPackCandidateRole.CAMPAIGN_ENGINE_CANDIDATE
    assert request.symbol == "SOL/USDT:USDT"
    assert request.side == SignalSide.LONG
    assert request.base_timeframe == "1h"
    assert request.forward_windows == {
        "1h": 1,
        "4h": 4,
        "12h": 12,
        "24h": 24,
        "72h": 72,
        "7d": 168,
    }
    assert request.non_persistent is True


def test_builds_cpm_request_without_promoting_cpm_to_campaign_engine():
    request = build_directional_opportunity_comparison_request(
        spec=btc_eth_sol_bnb_directional_opportunity_pack(),
        candidate_family_id="CPM-RO-001",
        symbol="ETH/USDT:USDT",
        side="short",
    )

    assert request.candidate_family_id == "CPM-RO-001"
    assert request.candidate_role == DirectionalPackCandidateRole.BENCHMARK_COMPONENT
    assert request.candidate_roles == [
        DirectionalPackCandidateRole.BENCHMARK_COMPONENT,
        DirectionalPackCandidateRole.RESEARCH_REFERENCE,
    ]
    assert DirectionalPackCandidateRole.CAMPAIGN_ENGINE_CANDIDATE not in request.candidate_roles


def test_rejects_invalid_candidate_family_id():
    with pytest.raises(ValueError, match="candidate_family_id"):
        build_directional_opportunity_comparison_request(
            spec=btc_eth_sol_bnb_directional_opportunity_pack(),
            candidate_family_id="UNKNOWN-001",
            symbol="BTC/USDT:USDT",
            side="long",
        )


def test_rejects_invalid_symbol():
    with pytest.raises(ValueError, match="symbol"):
        build_directional_opportunity_comparison_request(
            spec=btc_eth_sol_bnb_directional_opportunity_pack(),
            candidate_family_id="VB-001",
            symbol="DOGE/USDT:USDT",
            side="long",
        )


def test_rejects_invalid_side():
    with pytest.raises(ValueError, match="side"):
        build_directional_opportunity_comparison_request(
            spec=btc_eth_sol_bnb_directional_opportunity_pack(),
            candidate_family_id="VB-001",
            symbol="BTC/USDT:USDT",
            side="flat",
        )


def test_comparison_request_model_exposes_no_execution_order_fields():
    forbidden_terms = {
        "order",
        "execution",
        "leverage",
        "submit",
        "cancel",
        "flatten",
        "close_position",
    }

    assert not any(
        term in field_name
        for field_name in DirectionalOpportunityComparisonRequest.model_fields
        for term in forbidden_terms
    )

    payload = build_directional_opportunity_comparison_request(
        spec=btc_eth_sol_bnb_directional_opportunity_pack(),
        candidate_family_id="TB-001",
        symbol="BNB/USDT:USDT",
        side=SignalSide.SHORT,
    ).model_dump_json().lower()
    assert not any(term in payload for term in forbidden_terms)
