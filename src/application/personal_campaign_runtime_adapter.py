"""Read-only Personal Leveraged Campaign runtime adapter.

This adapter is an inspection bridge only. It does not import runtime I/O,
exchange gateways, execution orchestrators, repositories, or config loaders.
"""

from __future__ import annotations

from src.domain.personal_campaign import (
    CampaignDecision,
    FeatureSnapshot,
    ReadOnlyRuntimeAdapterPreview,
    StrategyContract,
    TradeIntent,
    TradeIntentAction,
)

_READ_ONLY_CAMPAIGN_ID = "read-only-runtime-preview"


def build_read_only_trade_intent_preview(
    *,
    contract: StrategyContract,
    feature_snapshot: FeatureSnapshot,
    runtime_clock_ms: int,
) -> ReadOnlyRuntimeAdapterPreview:
    """Build a read-only TradeIntent preview from closed/prior PLC inputs."""

    rejection_reasons = _validate_read_only_inputs(
        contract=contract,
        feature_snapshot=feature_snapshot,
        runtime_clock_ms=runtime_clock_ms,
    )
    if rejection_reasons:
        intent = _reject_intent(
            contract=contract,
            feature_snapshot=feature_snapshot,
            reason=rejection_reasons[0],
        )
    else:
        intent = _evaluate_contract_preview(
            contract=contract,
            feature_snapshot=feature_snapshot,
        )
        if intent.decision == CampaignDecision.REJECT:
            rejection_reasons.append(intent.trigger_reason)

    return ReadOnlyRuntimeAdapterPreview(
        source_snapshot_id=feature_snapshot.snapshot_id,
        snapshot_feature_timestamp_ms=feature_snapshot.feature_timestamp_ms,
        runtime_clock_ms=runtime_clock_ms,
        strategy_contract_id=contract.strategy_contract_id,
        strategy_contract_status=contract.contract_status,
        trade_intent=intent,
        rejection_reasons=rejection_reasons,
    )


def _validate_read_only_inputs(
    *,
    contract: StrategyContract,
    feature_snapshot: FeatureSnapshot,
    runtime_clock_ms: int,
) -> list[str]:
    reasons: list[str] = []
    if contract.contract_status != "frozen":
        reasons.append("strategy_contract_not_frozen")
    if not contract.disabled_by_default:
        reasons.append("strategy_contract_not_disabled_by_default")
    if contract.runtime_label != "LOCAL_SANDBOX_ONLY_DISABLED_BY_DEFAULT":
        reasons.append("strategy_contract_runtime_label_not_local_only")
    if contract.no_lookahead_rule != "closed_or_prior_inputs_only":
        reasons.append("strategy_contract_no_lookahead_rule_invalid")
    if feature_snapshot.strategy_contract_id != contract.strategy_contract_id:
        reasons.append("feature_snapshot_strategy_mismatch")
    if feature_snapshot.feature_timestamp_ms > runtime_clock_ms:
        reasons.append("feature_snapshot_not_closed_or_prior_to_runtime_clock")
    return reasons


def _evaluate_contract_preview(
    *,
    contract: StrategyContract,
    feature_snapshot: FeatureSnapshot,
) -> TradeIntent:
    base = {
        "strategy_contract_id": contract.strategy_contract_id,
        "campaign_id": _READ_ONLY_CAMPAIGN_ID,
        "session_id": f"readonly-{feature_snapshot.snapshot_id}",
    }
    conditions = feature_snapshot.conditions
    missing_features = [
        key for key in contract.required_feature_snapshot if key not in conditions
    ]
    if missing_features:
        return TradeIntent(
            **base,
            decision=CampaignDecision.REJECT,
            trigger_reason="required_feature_missing",
            invalidation_reason="missing:" + ",".join(missing_features),
        )
    if conditions.get(contract.invalidation_condition_key, False):
        return TradeIntent(
            **base,
            decision=CampaignDecision.REJECT,
            trigger_reason="contract_invalidated",
            invalidation_reason=contract.invalidation_condition_key,
        )
    if not conditions.get(contract.setup_condition_key, False):
        return TradeIntent(
            **base,
            decision=CampaignDecision.REJECT,
            trigger_reason="setup_condition_absent",
            invalidation_reason=contract.setup_condition_key,
        )
    return TradeIntent(
        **base,
        decision=CampaignDecision.ALLOW,
        direction=contract.direction,
        action=contract.entry_action,
        trigger_reason=contract.setup_condition_key,
        evidence_text="read_only_runtime_preview_contract_conditions_satisfied",
    )


def _reject_intent(
    *,
    contract: StrategyContract,
    feature_snapshot: FeatureSnapshot,
    reason: str,
) -> TradeIntent:
    return TradeIntent(
        decision=CampaignDecision.REJECT,
        strategy_contract_id=contract.strategy_contract_id,
        campaign_id=_READ_ONLY_CAMPAIGN_ID,
        session_id=f"readonly-{feature_snapshot.snapshot_id}",
        action=TradeIntentAction.NONE,
        trigger_reason=reason,
        invalidation_reason=reason,
        evidence_text="read_only_runtime_adapter_rejected_before_contract_evaluation",
    )
