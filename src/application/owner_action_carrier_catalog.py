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
MR_OWNER_ACTION_CARRIER_ID = "MR-001-live-readonly-v0"
MR_BTC_OWNER_ACTION_CARRIER_ID = "MR-001-BTC-live-readonly-v0"
SUPPORTED_OWNER_ACTION_CARRIER_IDS = [
    BNB_OWNER_ACTION_CARRIER_ID,
    TREND_OWNER_ACTION_CARRIER_ID,
    MR_OWNER_ACTION_CARRIER_ID,
    MR_BTC_OWNER_ACTION_CARRIER_ID,
]

MR_OWNER_ACTION_SYMBOL_CARRIER_IDS = {
    "ETH/USDT:USDT": MR_OWNER_ACTION_CARRIER_ID,
    "BTC/USDT:USDT": MR_BTC_OWNER_ACTION_CARRIER_ID,
}


def supported_owner_action_carrier_ids() -> list[str]:
    return list(SUPPORTED_OWNER_ACTION_CARRIER_IDS)


def owner_action_carrier_id_for_symbol(carrier_id: str | None, symbol: str | None) -> str | None:
    if carrier_id not in {MR_OWNER_ACTION_CARRIER_ID, MR_BTC_OWNER_ACTION_CARRIER_ID}:
        return carrier_id
    if symbol is None:
        return carrier_id
    return MR_OWNER_ACTION_SYMBOL_CARRIER_IDS.get(str(symbol), carrier_id)


def get_owner_action_carrier(carrier_id: str) -> StrategyTrialCarrierView | None:
    if carrier_id == BNB_OWNER_ACTION_CARRIER_ID:
        return build_bnb_strategy_trial_architecture_governance().owner_review_artifact.carrier
    if carrier_id == TREND_OWNER_ACTION_CARRIER_ID:
        return _trend_carrier()
    if carrier_id == MR_OWNER_ACTION_CARRIER_ID:
        return _mr_carrier(
            carrier_id=MR_OWNER_ACTION_CARRIER_ID,
            symbol="ETH/USDT:USDT",
            quantity=Decimal("0.01"),
        )
    if carrier_id == MR_BTC_OWNER_ACTION_CARRIER_ID:
        return _mr_carrier(
            carrier_id=MR_BTC_OWNER_ACTION_CARRIER_ID,
            symbol="BTC/USDT:USDT",
            quantity=Decimal("0.001"),
        )
    return None


def owner_action_risk_warnings(carrier_id: str) -> list[StrategyTrialRiskWarning]:
    if carrier_id == BNB_OWNER_ACTION_CARRIER_ID:
        return list(build_bnb_strategy_trial_architecture_governance().owner_review_artifact.strategy_warnings)
    if carrier_id == TREND_OWNER_ACTION_CARRIER_ID:
        return _trend_warnings()
    if carrier_id in {MR_OWNER_ACTION_CARRIER_ID, MR_BTC_OWNER_ACTION_CARRIER_ID}:
        return _mr_warnings()
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


def _mr_carrier(
    *,
    carrier_id: str,
    symbol: str,
    quantity: Decimal,
    max_notional: Decimal = Decimal("25"),
    target_notional_usdt: Decimal = Decimal("22"),
) -> StrategyTrialCarrierView:
    return StrategyTrialCarrierView(
        carrier_id=carrier_id,
        strategy_family="Mean reversion",
        strategy_id="MR-001-live-readonly-v0",
        candidate_id=carrier_id,
        symbol=symbol,
        runtime_symbol=symbol,
        side="long",
        execution_mode="owner_confirm_each_entry",
        quantity=quantity,
        max_notional=max_notional,
        leverage=Decimal("1"),
        max_leverage_allowed=Decimal("1"),
        protection_plan_type="single_tp_plus_sl",
        sizing_mode="notional_derived",
        target_notional_usdt=target_notional_usdt,
    )


def _mr_warnings() -> list[StrategyTrialRiskWarning]:
    return [
        StrategyTrialRiskWarning(
            warning_id="mr_owner_range_view_not_alpha_proof",
            severity="warning",
            description=(
                "Owner range input is a bounded market view and not proof that the "
                "Mean reversion carrier has profitable live edge."
            ),
        ),
        StrategyTrialRiskWarning(
            warning_id="mr_trend_continuation_against_entry_risk",
            severity="warning",
            description=(
                "Mean reversion entries can fail if a strong trend continues; exact "
                "scope and mandatory TP/SL protection are required."
            ),
        ),
        StrategyTrialRiskWarning(
            warning_id="mr_liquidity_wick_and_slippage_risk",
            severity="warning",
            description=(
                "Range reversals around liquidity wicks can slip through the intended "
                "entry and protection levels."
            ),
        ),
    ]
