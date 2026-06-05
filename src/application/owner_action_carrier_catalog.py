"""Owner-action carrier catalog for bounded production trial paths.

The catalog is metadata only. It centralizes exact carrier scopes used by
owner trial-flow, final-gate dry-run, protection planning, and bounded
execution adapters. It does not create authorizations, execution intents,
orders, runtime transitions, or exchange calls.
"""

from __future__ import annotations

from decimal import Decimal

from src.application.strategy_trial_architecture_governance import (
    StrategyTrialCarrierView,
    StrategyTrialRiskWarning,
    build_bnb_strategy_trial_architecture_governance,
)


BNB_OWNER_ACTION_CARRIER_ID = "MI-001-BNB-LONG"
TREND_OWNER_ACTION_CARRIER_ID = "TF-001-live-readonly-v0"
SUPPORTED_OWNER_ACTION_CARRIER_IDS = [
    BNB_OWNER_ACTION_CARRIER_ID,
    TREND_OWNER_ACTION_CARRIER_ID,
]


def supported_owner_action_carrier_ids() -> list[str]:
    return list(SUPPORTED_OWNER_ACTION_CARRIER_IDS)


def get_owner_action_carrier(carrier_id: str) -> StrategyTrialCarrierView | None:
    if carrier_id == BNB_OWNER_ACTION_CARRIER_ID:
        return build_bnb_strategy_trial_architecture_governance().owner_review_packet.carrier
    if carrier_id == TREND_OWNER_ACTION_CARRIER_ID:
        return _trend_carrier()
    return None


def owner_action_risk_warnings(carrier_id: str) -> list[StrategyTrialRiskWarning]:
    if carrier_id == BNB_OWNER_ACTION_CARRIER_ID:
        return list(build_bnb_strategy_trial_architecture_governance().owner_review_packet.strategy_warnings)
    if carrier_id == TREND_OWNER_ACTION_CARRIER_ID:
        return _trend_warnings()
    return []


def required_owner_action_warning_ids(carrier_id: str) -> list[str]:
    return [
        warning.warning_id
        for warning in owner_action_risk_warnings(carrier_id)
        if warning.owner_ack_required
    ]


def owner_action_warning_rows(carrier_id: str) -> list[dict[str, str | bool]]:
    return [
        {
            "warning_id": warning.warning_id,
            "severity": warning.severity,
            "description": warning.description,
            "owner_ack_required": warning.owner_ack_required,
            "blocks_after_ack": warning.blocks_after_ack,
            "classification": "strategy_warning",
        }
        for warning in owner_action_risk_warnings(carrier_id)
    ]


def _trend_carrier() -> StrategyTrialCarrierView:
    return StrategyTrialCarrierView(
        carrier_id=TREND_OWNER_ACTION_CARRIER_ID,
        strategy_family="Trend Following",
        strategy_id=TREND_OWNER_ACTION_CARRIER_ID,
        candidate_id=TREND_OWNER_ACTION_CARRIER_ID,
        symbol="SOL/USDT:USDT",
        runtime_symbol="SOL/USDT:USDT",
        side="long",
        execution_mode="owner_confirm_each_entry",
        quantity=Decimal("0.1"),
        max_notional=Decimal("20"),
        leverage=Decimal("1"),
        max_leverage_allowed=Decimal("1"),
        protection_plan_type="single_tp_plus_sl",
    )


def _trend_warnings() -> list[StrategyTrialRiskWarning]:
    return [
        StrategyTrialRiskWarning(
            warning_id="tf_owner_market_view_not_alpha_proof",
            severity="warning",
            description=(
                "Owner trend input is a bounded market view and not proof that the "
                "Trend carrier has profitable live edge."
            ),
        ),
        StrategyTrialRiskWarning(
            warning_id="tf_false_continuation_risk",
            severity="warning",
            description=(
                "Trend continuation can fail quickly after entry; the trial must stay "
                "inside exact scope and attach mandatory TP/SL protection."
            ),
        ),
        StrategyTrialRiskWarning(
            warning_id="tf_small_sample_live_history",
            severity="warning",
            description=(
                "The Trend carrier has limited production action history; this is a "
                "risk disclosure and not a hard blocker after Owner acknowledgement."
            ),
        ),
    ]
