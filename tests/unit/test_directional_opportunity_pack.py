from __future__ import annotations

from src.domain.directional_opportunity_pack import (
    CANONICAL_DIRECTIONAL_SYMBOLS,
    CANONICAL_FORWARD_WINDOWS,
    DIRECTIONAL_PACK_METRICS,
    DirectionalPackCandidateRole,
    btc_eth_sol_bnb_directional_opportunity_pack,
)
from src.domain.strategy_family_signal import SignalSide


def test_directional_opportunity_pack_declares_canonical_research_grid():
    pack = btc_eth_sol_bnb_directional_opportunity_pack()

    assert pack.canonical_symbols == [
        "BTC/USDT:USDT",
        "ETH/USDT:USDT",
        "SOL/USDT:USDT",
        "BNB/USDT:USDT",
    ]
    assert pack.canonical_symbols == CANONICAL_DIRECTIONAL_SYMBOLS
    assert pack.sides == [SignalSide.LONG, SignalSide.SHORT]
    assert pack.forward_windows == ["1h", "4h", "12h", "24h", "72h", "7d"]
    assert pack.forward_windows == CANONICAL_FORWARD_WINDOWS
    assert set(DIRECTIONAL_PACK_METRICS).issubset(set(pack.required_metric_names))


def test_directional_opportunity_pack_declares_family_roles_without_cpm_promotion():
    pack = btc_eth_sol_bnb_directional_opportunity_pack()
    by_id = {candidate.family_id: candidate for candidate in pack.candidate_families}

    assert set(by_id) == {
        "PULLBACK-CONT-001",
        "VB-001",
        "TB-001",
        "BTC-REGIME-RS-001",
        "CPM-RO-001",
    }
    assert DirectionalPackCandidateRole.CAMPAIGN_ENGINE_CANDIDATE in by_id[
        "PULLBACK-CONT-001"
    ].candidate_roles
    assert DirectionalPackCandidateRole.CAMPAIGN_ENGINE_CANDIDATE in by_id["VB-001"].candidate_roles
    assert DirectionalPackCandidateRole.CAMPAIGN_ENGINE_CANDIDATE in by_id["TB-001"].candidate_roles
    assert by_id["BTC-REGIME-RS-001"].candidate_roles == [
        DirectionalPackCandidateRole.REGIME_FILTER
    ]
    assert by_id["CPM-RO-001"].candidate_roles == [
        DirectionalPackCandidateRole.BENCHMARK_COMPONENT,
        DirectionalPackCandidateRole.RESEARCH_REFERENCE,
    ]
    assert DirectionalPackCandidateRole.CAMPAIGN_ENGINE_CANDIDATE not in by_id[
        "CPM-RO-001"
    ].candidate_roles


def test_directional_opportunity_pack_references_no_runtime_order_surface():
    pack_json = btc_eth_sol_bnb_directional_opportunity_pack().model_dump_json().lower()

    forbidden_fragments = [
        "executionintent",
        "execution_intent",
        "order_router",
        "submit_order",
        "cancel_order",
        "place_order",
        "flatten",
        "close_position",
        "leverage",
        "signaloutput",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in pack_json
