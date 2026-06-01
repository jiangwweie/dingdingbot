from __future__ import annotations

from src.application.strategy_group_observation_case_queue import ObservationCaseQueueItem
from src.application.strategy_trial_readiness import (
    RiskCapProfile,
    TrialReadinessPreflightInput,
    bnb_first_carrier_cap_profile,
    bnb_first_carrier_profile,
    build_bnb_strategy_trial_readiness,
    evaluate_strategy_trial_preflight,
)
from src.application.strategy_trial_preflight_facts import TrialPreflightFactCollector


def test_bnb_strategy_trial_readiness_links_observation_without_execution_authority():
    readiness = build_bnb_strategy_trial_readiness(observation_case=_bnb_case())

    assert readiness.strategy_profile.candidate_id == "MI-001-BNB-LONG"
    assert readiness.strategy_profile.execution_mode == "owner_confirm_each_entry"
    assert readiness.observation_case["latest_signal"] == "would_enter"
    assert readiness.risk_cap_profile.profile_status == "present"
    assert readiness.readiness_verdict == "testnet_rehearsal_not_ready_with_explicit_blockers"
    assert readiness.live_ready is False
    assert readiness.auto_execution_ready is False
    assert readiness.non_permissions["no_execution_intent"] is True
    assert readiness.preflight_result.execution_intent_created is False
    assert readiness.preflight_result.order_created is False
    assert "active_position_check_required_before_rehearsal" in readiness.blockers
    assert "account_facts_required_before_rehearsal" in readiness.blockers


def test_preflight_can_reach_ready_pending_owner_authorization_when_safety_facts_clear():
    profile = bnb_first_carrier_profile()
    cap = bnb_first_carrier_cap_profile()
    preflight_input = TrialReadinessPreflightInput(
        requested_symbol="BNBUSDT",
        requested_side="long",
        requested_mode="owner_confirm_each_entry",
        active_conflicting_position_status="clear",
        open_conflicting_order_status="clear",
        gks_status="clear",
        startup_guard_status="clear",
        reconciliation_status="clean",
        account_facts_status="clear",
        owner_authorized_testnet_rehearsal=False,
    )

    preflight = evaluate_strategy_trial_preflight(
        profile=profile,
        risk_cap_profile=cap,
        preflight_input=preflight_input,
    )
    readiness = build_bnb_strategy_trial_readiness(
        observation_case=_bnb_case(),
        preflight_input=preflight_input,
    )

    assert preflight.status == "ready"
    assert "owner_testnet_authorization_missing" in preflight.warnings
    assert readiness.readiness_verdict == "testnet_rehearsal_ready_pending_owner_authorization"
    assert readiness.rehearsal_readiness_state["testnet_rehearsal_status"] == "pending_owner_authorization"
    assert readiness.live_ready is False


def test_preflight_blocks_wrong_symbol_wrong_side_and_live_request():
    profile = bnb_first_carrier_profile()
    preflight = evaluate_strategy_trial_preflight(
        profile=profile,
        risk_cap_profile=bnb_first_carrier_cap_profile(),
        preflight_input=TrialReadinessPreflightInput(
            requested_symbol="SOLUSDT",
            requested_side="short",
            requested_mode="owner_confirm_each_entry",
            live_trading_requested=True,
        ),
    )

    assert preflight.status == "blocked"
    assert "live_trading_requested" in preflight.blockers
    assert "wrong_symbol" in preflight.blockers
    assert "wrong_side" in preflight.blockers
    assert preflight.order_created is False


def test_preflight_reflects_missing_or_invalid_cap_profile():
    profile = bnb_first_carrier_profile()
    missing = evaluate_strategy_trial_preflight(
        profile=profile,
        risk_cap_profile=None,
        preflight_input=TrialReadinessPreflightInput(
            requested_symbol="BNBUSDT",
            requested_side="long",
            requested_mode="owner_confirm_each_entry",
        ),
    )
    invalid_cap = bnb_first_carrier_cap_profile().model_copy(
        update={"max_concurrent_position": 2}
    )
    invalid = evaluate_strategy_trial_preflight(
        profile=profile,
        risk_cap_profile=invalid_cap,
        preflight_input=TrialReadinessPreflightInput(
            requested_symbol="BNBUSDT",
            requested_side="long",
            requested_mode="owner_confirm_each_entry",
        ),
    )

    assert "missing_cap_profile" in missing.blockers
    assert "cap_profile_violation" in invalid.blockers


def test_generic_model_can_represent_non_bnb_profile():
    sol_profile = bnb_first_carrier_profile().model_copy(
        update={"candidate_id": "MI-001-SOL-LONG", "symbol": "SOLUSDT"}
    )
    preflight = evaluate_strategy_trial_preflight(
        profile=sol_profile,
        risk_cap_profile=RiskCapProfile(
            cap_profile_id="MI-001-SOL-LONG-testnet-rehearsal-cap-v0",
            profile_status="present",
            max_concurrent_position=1,
            max_daily_attempts=1,
            max_trial_attempts=1,
            max_notional_usdt="tiny_configurable_placeholder",
            leverage="1x",
        ),
        preflight_input=TrialReadinessPreflightInput(
            requested_symbol="SOLUSDT",
            requested_side="long",
            requested_mode="owner_confirm_each_entry",
            active_conflicting_position_status="clear",
            open_conflicting_order_status="clear",
            gks_status="clear",
            startup_guard_status="clear",
            reconciliation_status="clean",
            account_facts_status="clear",
        ),
    )

    assert sol_profile.candidate_id == "MI-001-SOL-LONG"
    assert preflight.status == "ready"
    assert preflight.execution_permission_granted is False


async def test_fact_collector_unknown_sources_become_concrete_preflight_blockers():
    profile = bnb_first_carrier_profile()
    snapshot = await TrialPreflightFactCollector().collect(profile)
    readiness = build_bnb_strategy_trial_readiness(
        observation_case=_bnb_case(),
        preflight_input=snapshot.to_preflight_input(
            requested_mode=profile.execution_mode,
        ),
        fact_checks=snapshot.to_response_dict(),
    )

    assert readiness.readiness_verdict == "testnet_rehearsal_not_ready_with_explicit_blockers"
    assert "active_position_check_required_before_rehearsal" in readiness.blockers
    assert "open_order_check_required_before_rehearsal" in readiness.blockers
    assert "gks_status_required_before_rehearsal" in readiness.blockers
    assert "startup_guard_status_required_before_rehearsal" in readiness.blockers
    assert "reconciliation_status_required_before_rehearsal" in readiness.blockers
    assert "account_facts_required_before_rehearsal" in readiness.blockers
    assert readiness.fact_checks["candidate_id"] == "MI-001-BNB-LONG"
    assert readiness.live_ready is False
    assert readiness.preflight_result.order_created is False


async def test_fact_collector_clear_facts_reaches_ready_pending_owner_authorization():
    profile = bnb_first_carrier_profile()

    async def empty(_profile):
        return []

    async def gks(_profile):
        return {"active": False, "source": "fake_gks", "updated_at_ms": 1}

    async def startup(_profile):
        return {"armed": True, "source": "fake_startup", "updated_at_ms": 2}

    async def reconciliation(_profile):
        return {"status": "clean", "failed_reconciliations_count": 0}

    async def account(_profile):
        return {
            "freshness_status": "fresh",
            "source_type": "fake_read_only",
            "timestamp_ms": 3,
            "account_equity": "1000",
            "available_margin": "800",
        }

    snapshot = await TrialPreflightFactCollector(
        position_reader=empty,
        open_order_reader=empty,
        gks_reader=gks,
        startup_guard_reader=startup,
        reconciliation_reader=reconciliation,
        account_facts_reader=account,
    ).collect(profile)
    readiness = build_bnb_strategy_trial_readiness(
        observation_case=_bnb_case(),
        preflight_input=snapshot.to_preflight_input(
            requested_mode=profile.execution_mode,
        ),
        fact_checks=snapshot.to_response_dict(),
    )

    assert snapshot.blockers == []
    assert readiness.preflight_result.status == "ready"
    assert readiness.readiness_verdict == "testnet_rehearsal_ready_pending_owner_authorization"
    assert "owner_testnet_authorization_missing" in readiness.warnings
    assert readiness.non_permissions["no_execution_permission"] is True


async def test_fact_collector_stale_account_facts_block_rehearsal():
    profile = bnb_first_carrier_profile()

    async def empty(_profile):
        return []

    async def gks(_profile):
        return {"active": False}

    async def startup(_profile):
        return {"armed": True}

    async def reconciliation(_profile):
        return {"status": "clean"}

    async def account(_profile):
        return {
            "freshness_status": "stale",
            "source": "cached_account_snapshot",
            "timestamp_ms": 1,
            "account_equity": "1000",
            "available_margin": "800",
        }

    snapshot = await TrialPreflightFactCollector(
        position_reader=empty,
        open_order_reader=empty,
        gks_reader=gks,
        startup_guard_reader=startup,
        reconciliation_reader=reconciliation,
        account_facts_reader=account,
    ).collect(profile)
    readiness = build_bnb_strategy_trial_readiness(
        observation_case=_bnb_case(),
        preflight_input=snapshot.to_preflight_input(
            requested_mode=profile.execution_mode,
        ),
        fact_checks=snapshot.to_response_dict(),
    )

    account_fact = snapshot.fact_map()["account_facts"]
    assert account_fact.status == "stale"
    assert "account_facts_stale" in readiness.blockers
    assert readiness.readiness_verdict == "testnet_rehearsal_not_ready_with_explicit_blockers"


async def test_fact_collector_surfaces_missing_equity_and_margin():
    profile = bnb_first_carrier_profile()

    async def empty(_profile):
        return []

    async def account(_profile):
        return {
            "freshness_status": "fresh",
            "source": "cached_account_snapshot",
            "timestamp_ms": 3,
            "account_equity": "not_available",
            "available_margin": "not_available",
        }

    snapshot = await TrialPreflightFactCollector(
        position_reader=empty,
        open_order_reader=empty,
        gks_reader=lambda profile: {"active": False},
        startup_guard_reader=lambda profile: {"armed": True},
        reconciliation_reader=lambda profile: {"status": "clean"},
        account_facts_reader=account,
    ).collect(profile)
    readiness = build_bnb_strategy_trial_readiness(
        observation_case=_bnb_case(),
        preflight_input=snapshot.to_preflight_input(
            requested_mode=profile.execution_mode,
        ),
        fact_checks=snapshot.to_response_dict(),
    )

    account_fact = snapshot.fact_map()["account_facts"]
    assert account_fact.evidence["equity_available"] is False
    assert account_fact.evidence["available_margin_available"] is False
    assert "account_equity_unavailable" in readiness.blockers
    assert "available_margin_unavailable" in readiness.blockers
    assert readiness.preflight_result.execution_intent_created is False
    assert readiness.preflight_result.order_created is False


async def test_fact_collector_conflicting_position_and_order_block_rehearsal():
    profile = bnb_first_carrier_profile()

    async def one(_profile):
        return [{"id": "existing"}]

    async def gks(_profile):
        return {"active": False}

    async def startup(_profile):
        return {"armed": True}

    async def reconciliation(_profile):
        return {"status": "clean"}

    async def account(_profile):
        return {
            "freshness_status": "fresh",
            "timestamp_ms": 3,
            "account_equity": "1000",
            "available_margin": "800",
        }

    snapshot = await TrialPreflightFactCollector(
        position_reader=one,
        open_order_reader=one,
        gks_reader=gks,
        startup_guard_reader=startup,
        reconciliation_reader=reconciliation,
        account_facts_reader=account,
    ).collect(profile)
    readiness = build_bnb_strategy_trial_readiness(
        observation_case=_bnb_case(),
        preflight_input=snapshot.to_preflight_input(
            requested_mode=profile.execution_mode,
        ),
        fact_checks=snapshot.to_response_dict(),
    )

    assert "conflicting_position_exists" in readiness.blockers
    assert "conflicting_open_order_exists" in readiness.blockers
    assert readiness.readiness_verdict == "testnet_rehearsal_not_ready_with_explicit_blockers"


def _bnb_case() -> ObservationCaseQueueItem:
    return ObservationCaseQueueItem(
        case_id="MI-001-BNB-LONG-live-case-001",
        observation_id="MI-001-BNB-LONG:mi001-5bb8b1c1b14437d7bddbacab:1780196400000",
        strategy_group_id="MI-001",
        candidate_id="MI-001-BNB-LONG",
        symbol="BNB/USDT:USDT",
        side="long",
        signal_type="would_enter",
        case_status="pending_forward_review",
        observed_at_ms=1_780_196_400_000,
        market_bar_timestamp_ms=1_780_196_400_000,
        source_type="live_market_read_only",
        market_source="binance_usdm_public_klines_read_only",
        review_windows=["1h", "4h", "12h", "24h", "72h"],
        completed_review_windows=["1h", "4h"],
        pending_review_windows=["12h", "24h", "72h"],
        risk_tags=["no_chase_required", "wait_for_confirmation_required"],
        reason_codes=["mi001_12h_momentum_impulse"],
        human_summary="MI-001 BNB would-enter live observation.",
        owner_interpretation="Observation only.",
    )
