"""Generic strategy-trial readiness framework.

The framework maps observation cases into a bounded, Owner-reviewable trial
readiness surface. It is deliberately read-only: it cannot create execution
intents, place orders, grant execution permission, or start runtime.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.application.strategy_group_observation_case_queue import (
    ObservationCaseQueueItem,
)


ReadinessVerdict = Literal[
    "testnet_rehearsal_ready_pending_owner_authorization",
    "testnet_rehearsal_not_ready_with_explicit_blockers",
]
PreflightStatus = Literal["ready", "blocked", "unknown"]
OwnerAuthorizationStatus = Literal["missing", "granted_metadata_only"]
TestnetRehearsalStatus = Literal["pending_owner_authorization", "blocked"]


class StrategyProfile(BaseModel):
    strategy_group: str
    strategy_id: str
    candidate_id: str
    symbol: str
    side: str
    execution_mode: Literal["observe_only", "owner_confirm_each_entry", "auto_within_budget"]
    auto_within_budget: Literal[False] = False
    owner_confirm_each_entry: Literal[True] = True
    not_runtime_source_of_truth: Literal[True] = True


class RiskCapProfile(BaseModel):
    cap_profile_id: str
    profile_status: Literal["present", "missing"]
    max_concurrent_position: int
    max_daily_attempts: int
    max_trial_attempts: int
    max_notional_usdt: str
    leverage: str
    no_auto_reentry: bool = True
    no_averaging_down: bool = True
    no_auto_top_up: bool = True
    no_transfer: bool = True
    no_withdrawal: bool = True
    owner_confirm_each_entry: bool = True
    live_ready: Literal[False] = False
    testnet_rehearsal_requires_owner_authorization: Literal[True] = True


class TrialReadinessPreflightInput(BaseModel):
    requested_symbol: str
    requested_side: str
    requested_mode: Literal["observe_only", "owner_confirm_each_entry", "auto_within_budget"]
    live_trading_requested: bool = False
    auto_execution_enabled: bool = False
    owner_authorized_testnet_rehearsal: bool = False
    active_conflicting_position_status: Literal["clear", "blocked", "unknown", "not_checked"] = "not_checked"
    open_conflicting_order_status: Literal["clear", "blocked", "unknown", "not_checked"] = "not_checked"
    gks_status: Literal["clear", "blocking", "unknown", "not_checked"] = "not_checked"
    startup_guard_status: Literal["clear", "blocking", "unknown", "not_checked"] = "not_checked"
    reconciliation_status: Literal["clean", "mismatch", "unknown", "not_checked"] = "not_checked"
    account_facts_status: Literal["clear", "blocked", "unknown", "not_checked"] = "not_checked"


class StrategyTrialPreflightResult(BaseModel):
    status: PreflightStatus
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    evidence: dict[str, str | bool] = Field(default_factory=dict)
    next_owner_action: str
    execution_intent_created: Literal[False] = False
    order_created: Literal[False] = False
    live_order_created: Literal[False] = False
    execution_permission_granted: Literal[False] = False


class StrategyTrialReadinessResponse(BaseModel):
    generated_from: Literal["strategy_trial_readiness_v1"] = "strategy_trial_readiness_v1"
    strategy_profile: StrategyProfile
    observation_case: dict[str, str | int | list[str] | None]
    risk_cap_profile: RiskCapProfile
    preflight_result: StrategyTrialPreflightResult
    owner_decision_state: dict[str, str | bool | list[str]]
    rehearsal_readiness_state: dict[str, str | bool | list[str]]
    fact_checks: dict[str, Any] = Field(default_factory=dict)
    readiness_verdict: ReadinessVerdict
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    evidence: dict[str, str | bool | int | None] = Field(default_factory=dict)
    market_data_architecture: dict[str, str | bool] = Field(default_factory=dict)
    non_permissions: dict[str, bool] = Field(default_factory=lambda: _non_permissions())
    reusable_for_future_profiles: Literal[True] = True
    live_ready: Literal[False] = False
    auto_execution_ready: Literal[False] = False


def bnb_first_carrier_profile() -> StrategyProfile:
    return StrategyProfile(
        strategy_group="MI",
        strategy_id="MI-001",
        candidate_id="MI-001-BNB-LONG",
        symbol="BNBUSDT",
        side="long",
        execution_mode="owner_confirm_each_entry",
    )


def bnb_first_carrier_cap_profile() -> RiskCapProfile:
    return RiskCapProfile(
        cap_profile_id="MI-001-BNB-LONG-testnet-rehearsal-cap-v0",
        profile_status="present",
        max_concurrent_position=1,
        max_daily_attempts=1,
        max_trial_attempts=3,
        max_notional_usdt="tiny_configurable_placeholder_requires_owner_confirmation",
        leverage="1x_testnet_default_or_lower_until_owner_changes",
    )


def build_bnb_strategy_trial_readiness(
    *,
    observation_case: ObservationCaseQueueItem | None = None,
    preflight_input: TrialReadinessPreflightInput | None = None,
    risk_cap_profile: RiskCapProfile | None = None,
    fact_checks: dict[str, Any] | None = None,
) -> StrategyTrialReadinessResponse:
    profile = bnb_first_carrier_profile()
    cap_profile = risk_cap_profile or bnb_first_carrier_cap_profile()
    preflight = evaluate_strategy_trial_preflight(
        profile=profile,
        risk_cap_profile=cap_profile,
        preflight_input=preflight_input
        or TrialReadinessPreflightInput(
            requested_symbol=profile.symbol,
            requested_side=profile.side,
            requested_mode=profile.execution_mode,
        ),
    )
    blockers = list(preflight.blockers)
    warnings = list(preflight.warnings)
    if observation_case is None:
        warnings.append("observation_case_missing_or_pg_unavailable")

    auth_status: OwnerAuthorizationStatus = (
        "granted_metadata_only"
        if (preflight_input and preflight_input.owner_authorized_testnet_rehearsal)
        else "missing"
    )
    ready_except_owner = preflight.status == "ready"
    verdict: ReadinessVerdict = (
        "testnet_rehearsal_ready_pending_owner_authorization"
        if ready_except_owner and auth_status == "missing"
        else "testnet_rehearsal_not_ready_with_explicit_blockers"
    )
    rehearsal_status: TestnetRehearsalStatus = (
        "pending_owner_authorization"
        if verdict == "testnet_rehearsal_ready_pending_owner_authorization"
        else "blocked"
    )
    return StrategyTrialReadinessResponse(
        strategy_profile=profile,
        observation_case=_observation_case_summary(observation_case),
        risk_cap_profile=cap_profile,
        preflight_result=preflight,
        owner_decision_state={
            "owner_authorization_status": auth_status,
            "owner_authorization_required": True,
            "owner_can_authorize_testnet_rehearsal_next": verdict
            == "testnet_rehearsal_ready_pending_owner_authorization",
            "allowed_decisions": [
                "continue_observation_only",
                "prepare_owner_authorized_testnet_rehearsal",
                "wait_for_forward_review",
                "pause_bnb_case",
            ],
        },
        rehearsal_readiness_state={
            "testnet_rehearsal_status": rehearsal_status,
            "live_status": "blocked",
            "auto_execution_status": "disabled",
            "same_path_rehearsal": True,
            "requires_owner_authorization": True,
        },
        fact_checks=dict(fact_checks or {}),
        readiness_verdict=verdict,
        blockers=blockers,
        warnings=warnings,
        evidence={
            "latest_signal": observation_case.signal_type if observation_case else "missing",
            "observation_case_id": observation_case.case_id if observation_case else None,
            "cap_profile_present": cap_profile.profile_status == "present",
            "public_rest_kline_observation_source": True,
            "exchange_gateway_used": False,
            "private_account_api_used": False,
        },
        market_data_architecture={
            "provider_abstraction": "StrategyGroupMarketBarSource",
            "current_provider": "BinancePublicKlineMarketSource / public REST USD-M klines",
            "current_source_is_public_read_only": True,
            "websocket_required_for_this_sprint": False,
            "evaluator_source_agnostic": True,
            "exchange_gateway_market_provider": "future controlled runtime/testnet/live context only",
        },
    )


def evaluate_strategy_trial_preflight(
    *,
    profile: StrategyProfile,
    risk_cap_profile: RiskCapProfile | None,
    preflight_input: TrialReadinessPreflightInput,
) -> StrategyTrialPreflightResult:
    blockers: list[str] = []
    warnings: list[str] = []

    if preflight_input.live_trading_requested:
        blockers.append("live_trading_requested")
    if preflight_input.requested_symbol != profile.symbol:
        blockers.append("wrong_symbol")
    if preflight_input.requested_side != profile.side:
        blockers.append("wrong_side")
    if preflight_input.requested_mode != profile.execution_mode:
        blockers.append("wrong_execution_mode")
    if risk_cap_profile is None or risk_cap_profile.profile_status != "present":
        blockers.append("missing_cap_profile")
    elif not _cap_profile_valid(risk_cap_profile):
        blockers.append("cap_profile_violation")
    if preflight_input.auto_execution_enabled:
        blockers.append("auto_execution_enabled_unexpectedly")
    if preflight_input.active_conflicting_position_status != "clear":
        blockers.append(
            _active_position_blocker(preflight_input.active_conflicting_position_status)
        )
    if preflight_input.open_conflicting_order_status != "clear":
        blockers.append(
            _open_order_blocker(preflight_input.open_conflicting_order_status)
        )
    if preflight_input.gks_status != "clear":
        blockers.append(_gks_blocker(preflight_input.gks_status))
    if preflight_input.startup_guard_status != "clear":
        blockers.append(_startup_guard_blocker(preflight_input.startup_guard_status))
    if preflight_input.reconciliation_status != "clean":
        blockers.append(_reconciliation_blocker(preflight_input.reconciliation_status))
    if preflight_input.account_facts_status != "clear":
        blockers.append(_account_facts_blocker(preflight_input.account_facts_status))

    if not preflight_input.owner_authorized_testnet_rehearsal:
        warnings.append("owner_testnet_authorization_missing")

    return StrategyTrialPreflightResult(
        status="blocked" if blockers else "ready",
        blockers=blockers,
        warnings=warnings,
        evidence={
            "requested_symbol": preflight_input.requested_symbol,
            "requested_side": preflight_input.requested_side,
            "requested_mode": preflight_input.requested_mode,
            "live_trading_requested": preflight_input.live_trading_requested,
            "auto_execution_enabled": preflight_input.auto_execution_enabled,
            "owner_authorized_testnet_rehearsal": preflight_input.owner_authorized_testnet_rehearsal,
            "account_facts_status": preflight_input.account_facts_status,
            "risk_cap_profile_present": risk_cap_profile is not None
            and risk_cap_profile.profile_status == "present",
        },
        next_owner_action=(
            "Authorize BNB testnet same-path rehearsal only after reviewing cap/profile/preflight facts."
            if not blockers
            else "Resolve blockers before Owner can authorize testnet same-path rehearsal."
        ),
    )


def _cap_profile_valid(profile: RiskCapProfile) -> bool:
    return (
        profile.max_concurrent_position == 1
        and profile.max_daily_attempts >= 1
        and profile.max_trial_attempts >= 1
        and profile.no_auto_reentry
        and profile.no_averaging_down
        and profile.owner_confirm_each_entry
        and profile.live_ready is False
    )


def _active_position_blocker(status: str) -> str:
    if status == "blocked":
        return "conflicting_position_exists"
    return "active_position_check_required_before_rehearsal"


def _open_order_blocker(status: str) -> str:
    if status == "blocked":
        return "conflicting_open_order_exists"
    return "open_order_check_required_before_rehearsal"


def _gks_blocker(status: str) -> str:
    if status == "blocking":
        return "gks_blocked"
    return "gks_status_required_before_rehearsal"


def _startup_guard_blocker(status: str) -> str:
    if status == "blocking":
        return "startup_guard_blocked"
    return "startup_guard_status_required_before_rehearsal"


def _reconciliation_blocker(status: str) -> str:
    if status == "mismatch":
        return "reconciliation_not_clean"
    return "reconciliation_status_required_before_rehearsal"


def _account_facts_blocker(status: str) -> str:
    return "account_facts_required_before_rehearsal"


def _observation_case_summary(
    case: ObservationCaseQueueItem | None,
) -> dict[str, str | int | list[str] | None]:
    if case is None:
        return {
            "case_id": None,
            "observation_id": None,
            "latest_signal": "missing",
            "case_status": "missing",
            "completed_review_windows": [],
            "pending_review_windows": [],
        }
    return {
        "case_id": case.case_id,
        "observation_id": case.observation_id,
        "latest_signal": case.signal_type,
        "case_status": case.case_status,
        "market_bar_timestamp_ms": case.market_bar_timestamp_ms,
        "completed_review_windows": list(case.completed_review_windows),
        "pending_review_windows": list(case.pending_review_windows),
    }


def _non_permissions() -> dict[str, bool]:
    return {
        "no_live_order": True,
        "no_real_funds": True,
        "no_withdrawal_or_transfer": True,
        "no_credential_change": True,
        "no_execution_intent": True,
        "no_order_creation": True,
        "no_execution_permission": True,
        "no_runtime_start": True,
        "no_auto_execution": True,
        "would_enter_is_not_order": True,
        "testnet_rehearsal_not_started": True,
        "live_ready_false": True,
    }
