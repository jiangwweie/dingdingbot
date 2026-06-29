import pytest

from src.domain.required_facts_readiness import (
    RequiredFactDisableSpec,
    RequiredFactObservationSpec,
    RequiredFactSpec,
    assess_required_fact_observation,
    assess_required_fact,
    read_only_required_fact_authority_boundary,
    required_fact_disable_specs_from_rows,
    required_fact_observation_specs_from_rows,
    required_facts_status_for_tradeability,
    required_fact_status,
)


def test_required_fact_status_normalizes_ready_stale_and_missing_sources() -> None:
    spec = RequiredFactSpec(
        key="budget_coverage",
        question="budget coverage",
        ready_status="sufficient",
        stale_status="stale",
        missing_status="insufficient",
    )

    assert (
        required_fact_status(
            spec=spec,
            raw_status="available",
            action_time_check_active=True,
        )
        == "sufficient"
    )
    assert (
        required_fact_status(
            spec=spec,
            raw_status="expired",
            action_time_check_active=True,
        )
        == "stale"
    )
    assert (
        required_fact_status(
            spec=spec,
            raw_status="missing",
            action_time_check_active=True,
        )
        == "insufficient"
    )


def test_required_fact_assessment_blocks_only_when_action_time_active() -> None:
    spec = RequiredFactSpec(
        key="trusted_submit_fact_snapshot",
        question="trusted submit fact snapshot",
        ready_status="ready",
        stale_status="stale",
        missing_status="missing",
    )

    pending = assess_required_fact(
        spec=spec,
        raw_status="pending_action_time",
        action_time_check_active=False,
        check_surface="live_submit",
        owner_wording="等待实时事实",
    )
    blocked = assess_required_fact(
        spec=spec,
        raw_status="stale",
        action_time_check_active=True,
        check_surface="live_submit",
        owner_wording="事实不可用",
    )

    assert pending.status == "pending_action_time"
    assert pending.blocks_live_submit_now is False
    assert pending.blocker is None
    assert blocked.status == "stale"
    assert blocked.blocks_live_submit_now is True
    assert blocked.blocker == "trusted_submit_fact_snapshot:stale"
    assert blocked.as_runtime_safety_row()["owner_wording"] == "事实不可用"


@pytest.mark.parametrize(
    "case",
    [
        {
            "strategy_group_id": "BRF2-001",
            "fact_key": "rally_failure_trigger_state",
            "raw_status": "available",
            "expected_status": "ready",
            "expected_blocker": None,
            "fact_authority": "brf2_runtime_required_fact_mapping",
            "source_is_proxy_reference": False,
        },
        {
            "strategy_group_id": "MPG-001",
            "fact_key": "exchange_account_snapshot",
            "raw_status": "expired",
            "expected_status": "stale",
            "expected_blocker": "exchange_account_snapshot:stale",
            "fact_authority": "mpg_action_time_exchange_read",
            "source_is_proxy_reference": False,
        },
        {
            "strategy_group_id": "SOR-001",
            "fact_key": "session_window_liquidity_state",
            "raw_status": "missing",
            "expected_status": "missing",
            "expected_blocker": "session_window_liquidity_state:missing",
            "fact_authority": "sor_readonly_session_observation",
            "source_is_proxy_reference": True,
        },
    ],
)
def test_required_fact_matrix_classifies_missing_stale_and_authority_across_strategy_groups(
    case,
) -> None:
    spec = RequiredFactSpec(
        key=case["fact_key"],
        question=f"{case['strategy_group_id']} required fact",
        ready_status="ready",
        stale_status="stale",
        missing_status="missing",
    )

    assessment = assess_required_fact(
        spec=spec,
        raw_status=case["raw_status"],
        action_time_check_active=True,
        check_surface="live_submit",
        owner_wording="事实检查",
    )
    authority_boundary = read_only_required_fact_authority_boundary(
        fact_authority=case["fact_authority"],
        source_is_proxy_reference=case["source_is_proxy_reference"],
        proxy_note="proxy reference is observation-only",
        read_only_note="read-only fact can classify market wait only",
    ).as_read_model()

    assert assessment.status == case["expected_status"]
    assert assessment.blocker == case["expected_blocker"]
    assert assessment.blocks_live_submit_now == (case["expected_blocker"] is not None)
    assert authority_boundary["fact_authority"] == case["fact_authority"]
    assert (
        authority_boundary["source_is_brf_reference_row"]
        is case["source_is_proxy_reference"]
    )
    assert authority_boundary["usable_for_armed_observation"] is True
    assert authority_boundary["usable_for_market_wait_classification"] is True
    assert authority_boundary["action_time_required_facts_satisfied"] is False
    assert authority_boundary["usable_for_finalgate"] is False
    assert authority_boundary["usable_for_operation_layer"] is False
    assert authority_boundary["usable_for_exchange_write"] is False


def test_read_only_required_fact_authority_never_grants_action_time_gates() -> None:
    boundary = read_only_required_fact_authority_boundary(
        fact_authority="runtime_readonly_fact",
        source_is_proxy_reference=False,
        proxy_note="proxy",
        read_only_note="read only",
    ).as_read_model()

    assert boundary["fact_authority"] == "runtime_readonly_fact"
    assert boundary["usable_for_armed_observation"] is True
    assert boundary["usable_for_market_wait_classification"] is True
    assert boundary["action_time_required_facts_satisfied"] is False
    assert boundary["usable_for_finalgate"] is False
    assert boundary["usable_for_operation_layer"] is False
    assert boundary["usable_for_exchange_write"] is False


def test_required_fact_observation_classifies_missing_stale_and_not_satisfied() -> None:
    assert (
        assess_required_fact_observation(
            fact_key="rally_failure_trigger_state",
            fact_present=False,
            raw_status="",
            fresh=False,
            accepted_statuses={"confirmed"},
        ).as_signal_observation_row()
    ) == {
        "fact_key": "rally_failure_trigger_state",
        "state": "missing",
        "raw_state": "",
        "fresh": False,
    }
    assert (
        assess_required_fact_observation(
            fact_key="rally_failure_trigger_state",
            fact_present=True,
            raw_status="confirmed",
            fresh=False,
            accepted_statuses={"confirmed"},
        ).status
        == "stale"
    )
    assert (
        assess_required_fact_observation(
            fact_key="rally_failure_trigger_state",
            fact_present=True,
            raw_status="not_confirmed",
            fresh=True,
            accepted_statuses={"confirmed"},
        ).status
        == "not_satisfied"
    )


def test_required_fact_observation_specs_normalize_rows() -> None:
    rows = [
        {
            "fact_key": "rally_context",
            "accepted_statuses": ["Weak_Rally", "ready", "", "ready"],
        },
        {"fact_key": "", "accepted_statuses": ["ready"]},
        {"fact_key": "ignored_without_statuses", "accepted_statuses": []},
    ]

    assert required_fact_observation_specs_from_rows(rows) == [
        RequiredFactObservationSpec(
            key="rally_context",
            accepted_statuses=("ready", "weak_rally"),
        )
    ]


def test_required_fact_disable_specs_normalize_rows() -> None:
    rows = [
        {
            "fact_key": "short_squeeze_risk_state",
            "active_statuses": ["Red", "unknown", "", "red"],
            "blocker": "squeeze_risk_not_clear",
        },
        {"fact_key": "", "active_statuses": ["active"]},
        {"fact_key": "ignored_without_statuses", "active_statuses": []},
    ]

    assert required_fact_disable_specs_from_rows(rows) == [
        RequiredFactDisableSpec(
            key="short_squeeze_risk_state",
            active_statuses=("red", "unknown"),
            blocker="squeeze_risk_not_clear",
        )
    ]


def test_tradeability_required_facts_status_preserves_current_priority() -> None:
    assert (
        required_facts_status_for_tradeability(
            strategy_group_id="BRF2-001",
            stage="armed_observation",
            armed_observation_ready=True,
            required_facts_mapping_ready=True,
            has_required_facts_draft=False,
            blocker_text="required facts mapping gap",
            has_registry_required_facts_summary=False,
        )
        == "ready"
    )
    assert (
        required_facts_status_for_tradeability(
            strategy_group_id="MPG-001",
            stage="live_submit_ready",
            armed_observation_ready=False,
            required_facts_mapping_ready=False,
            has_required_facts_draft=False,
            blocker_text="",
            has_registry_required_facts_summary=False,
        )
        == "action_time_only"
    )
    assert (
        required_facts_status_for_tradeability(
            strategy_group_id="SOR-001",
            stage="role_only_intake_candidate",
            armed_observation_ready=False,
            required_facts_mapping_ready=False,
            has_required_facts_draft=False,
            blocker_text="",
            has_registry_required_facts_summary=False,
        )
        == "not_applicable"
    )
