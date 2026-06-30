from __future__ import annotations

from scripts.build_runtime_strategy_required_facts_readiness_artifact import (
    build_strategy_required_facts_readiness_artifact,
)


def _ready_fact_sources() -> dict:
    return {
        "trusted_account_facts": {
            "status": "available",
            "freshness": "fresh",
            "read_only_guarantee": True,
        },
        "trusted_runtime_boundary": {
            "status": "available",
            "freshness": "fresh",
            "read_only_guarantee": True,
        },
        "trusted_position_projection": {
            "status": "available",
            "freshness": "fresh",
            "read_only_guarantee": True,
        },
        "strategy_market_structure_facts": {
            "status": "available",
            "freshness": "fresh",
        },
        "trusted_market_facts": {
            "status": "available",
            "freshness": "fresh",
            "read_only_guarantee": True,
        },
    }


def test_cpm_and_brf_are_ready_when_required_fact_sources_are_fresh() -> None:
    artifact = build_strategy_required_facts_readiness_artifact(
        fact_sources=_ready_fact_sources(),
        strategies=["CPM-RO-001:CPM-RO-001-v0", "BRF-001:BRF-001-v0"],
        generated_at_ms=1,
    )

    assert artifact["status"] == "ready_for_non_executing_strategy_runtime_planning"
    assert artifact["operator_policy"]["required_facts_readiness_projection_only"] is True
    assert artifact["safety_invariants"]["required_facts_readiness_projection_only"] is True
    assert "packet_only" not in artifact["operator_policy"]
    assert "packet_only" not in artifact["safety_invariants"]
    assert artifact["operator_policy"]["requires_trusted_account_facts"] is True
    assert artifact["operator_policy"]["executable_submit_allowed_by_evidence"] is False
    assert {item["semantic_snapshot"]["strategy_family_id"] for item in artifact["strategies"]} == {
        "CPM-RO-001",
        "BRF-001",
    }
    for strategy in artifact["strategies"]:
        assert strategy["status"] == "ready_for_non_executing_strategy_runtime_planning"
        assert "trusted_account_facts" in strategy["required_trusted_sources"]
        assert "trusted_position_projection" in strategy["required_trusted_sources"]
        assert "trusted_runtime_boundary" in strategy["required_trusted_sources"]


def test_missing_trusted_account_source_blocks_candidate_planning() -> None:
    sources = _ready_fact_sources()
    sources.pop("trusted_account_facts")

    artifact = build_strategy_required_facts_readiness_artifact(
        fact_sources=sources,
        strategies=["CPM-RO-001:CPM-RO-001-v0"],
        generated_at_ms=1,
    )

    assert artifact["status"] == "blocked_strategy_required_facts"
    assert artifact["strategies"][0]["status"] == "blocked_required_facts"
    assert "account_facts_source_missing" in artifact["blockers"]


def test_stale_position_projection_blocks_candidate_planning() -> None:
    sources = _ready_fact_sources()
    sources["trusted_position_projection"]["freshness"] = "stale"

    artifact = build_strategy_required_facts_readiness_artifact(
        fact_sources=sources,
        strategies=["BRF-001:BRF-001-v0"],
        generated_at_ms=1,
    )

    assert artifact["status"] == "blocked_strategy_required_facts"
    assert "position_projection_source_stale" in artifact["blockers"]


def test_rmr_and_fco_remain_non_candidate_semantics() -> None:
    artifact = build_strategy_required_facts_readiness_artifact(
        fact_sources=_ready_fact_sources(),
        strategies=["RMR-001:RMR-001-v0", "FCO-001:FCO-001-v0"],
        generated_at_ms=1,
    )

    statuses = {
        item["semantic_snapshot"]["strategy_family_id"]: item["status"]
        for item in artifact["strategies"]
    }
    assert artifact["status"] == "observe_only_reference_semantics"
    assert statuses == {
        "RMR-001": "observe_only_reference_semantics",
        "FCO-001": "data_backlog_only",
    }
    assert artifact["operator_policy"]["does_not_create_shadow_candidate"] is True


def test_unknown_strategy_binding_blocks_semantics_readiness() -> None:
    artifact = build_strategy_required_facts_readiness_artifact(
        fact_sources=_ready_fact_sources(),
        strategies=["UNKNOWN-001:UNKNOWN-001-v0"],
        generated_at_ms=1,
    )

    assert artifact["status"] == "blocked_strategy_semantics_missing"
    assert artifact["missing_strategy_semantics"][0]["strategy_family_id"] == "UNKNOWN-001"
    assert "strategy_semantics_binding_missing" in artifact["blockers"]


def test_forbidden_side_effects_are_hard_blockers() -> None:
    sources = _ready_fact_sources()
    sources["exchange_write_called"] = True

    artifact = build_strategy_required_facts_readiness_artifact(
        fact_sources=sources,
        strategies=["CPM-RO-001:CPM-RO-001-v0"],
        generated_at_ms=1,
    )

    assert artifact["status"] == "blocked_forbidden_effect"
    assert artifact["safety_invariants"]["no_forbidden_live_side_effects"] is False
    assert artifact["safety_invariants"]["forbidden_effects"] == [
        "exchange_write_called"
    ]
