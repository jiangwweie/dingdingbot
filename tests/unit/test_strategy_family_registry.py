from __future__ import annotations

import inspect

import pytest

from src.domain.strategy_family_registry import (
    StrategyFamilyMetadata,
    StrategyFamilyPlaybookMetadata,
    StrategyFamilyStatus,
    StrategyFamilyType,
    initial_strategy_family_registry_seed,
)
from src.domain.strategy_family_signal import SignalType
from src.infrastructure.pg_strategy_family_registry_repository import (
    PgStrategyFamilyRegistryRepository,
)


def test_initial_seed_registers_tf_001_as_active_observation_candidate():
    seed = initial_strategy_family_registry_seed(now_ms=1770000000000)
    tf = next(item for item in seed.families if item.family_id == "TF-001-live-readonly-v0")

    assert tf.status == StrategyFamilyStatus.ACTIVE_OBSERVATION_CANDIDATE
    assert tf.family_type == StrategyFamilyType.TREND_FOLLOWING
    assert tf.alpha_claim is False
    assert tf.carrier_validation is True
    assert {"BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"} == set(tf.supported_symbols)
    assert tf.primary_timeframe == "1h"
    assert {"4h", "1d"}.issubset(set(tf.context_timeframes))
    assert SignalType.NO_ACTION in tf.allowed_signal_types
    assert SignalType.WOULD_ENTER in tf.allowed_signal_types
    assert SignalType.INVALID in tf.allowed_signal_types
    assert SignalType.WOULD_EXIT not in tf.allowed_signal_types
    assert SignalType.WOULD_REDUCE not in tf.allowed_signal_types
    assert SignalType.WOULD_CANCEL not in tf.allowed_signal_types


def test_initial_seed_registers_vb_cpm_and_mr_as_hypothesis_only():
    seed = initial_strategy_family_registry_seed(now_ms=1770000000000)
    by_id = {item.family_id: item for item in seed.families}

    assert by_id["VB-001-live-readonly-v0"].status == StrategyFamilyStatus.REGISTERED_HYPOTHESIS_ONLY
    assert by_id["VB-001-live-readonly-v0"].alpha_claim is False
    assert by_id["VB-001-live-readonly-v0"].carrier_validation is False
    assert by_id["VB-001-live-readonly-v0"].family_type == StrategyFamilyType.VOLATILITY_BREAKOUT

    assert by_id["CPM-RO-001"].status == StrategyFamilyStatus.REGISTERED_HYPOTHESIS_ONLY
    assert by_id["CPM-RO-001"].alpha_claim is False
    assert by_id["CPM-RO-001"].carrier_validation is False
    assert "Historical performance is not current alpha proof" in by_id["CPM-RO-001"].notes

    assert by_id["MR-001-live-readonly-v0"].status == StrategyFamilyStatus.REGISTERED_HYPOTHESIS_ONLY
    assert by_id["MR-001-live-readonly-v0"].family_type == StrategyFamilyType.MEAN_REVERSION
    assert by_id["MR-001-live-readonly-v0"].alpha_claim is False
    assert by_id["MR-001-live-readonly-v0"].carrier_validation is False
    assert "no order authority" in by_id["MR-001-live-readonly-v0"].notes


def test_initial_seed_covers_production_admission_sprint_family_types():
    seed = initial_strategy_family_registry_seed(now_ms=1770000000000)
    family_types = {item.family_type for item in seed.families}
    playbooks_by_family_id = {item.family_id: item for item in seed.playbooks}

    assert StrategyFamilyType.TREND_FOLLOWING in family_types
    assert StrategyFamilyType.VOLATILITY_BREAKOUT in family_types
    assert StrategyFamilyType.MEAN_REVERSION in family_types
    assert "TF-001-live-readonly-v0" in playbooks_by_family_id
    assert "VB-001-live-readonly-v0" in playbooks_by_family_id
    assert "MR-001-live-readonly-v0" in playbooks_by_family_id


@pytest.mark.parametrize(
    "field_name",
    [
        "quantity",
        "notional",
        "leverage",
        "order_type",
        "client_order_id",
        "order_id",
        "venue",
        "reduce_only",
        "router_target",
        "cancel_instruction",
        "close_instruction",
        "flatten_instruction",
    ],
)
def test_family_metadata_rejects_forbidden_execution_order_fields(field_name: str):
    payload = initial_strategy_family_registry_seed(now_ms=1770000000000).families[
        0
    ].model_dump(mode="python")
    payload["reason_code_taxonomy"][field_name] = "must_not_exist"

    with pytest.raises(ValueError, match="forbidden execution/order field"):
        StrategyFamilyMetadata.model_validate(payload)


@pytest.mark.parametrize(
    "field_name",
    [
        "quantity",
        "notional",
        "leverage",
        "order_type",
        "client_order_id",
        "order_id",
        "venue",
        "reduce_only",
        "router_target",
        "cancel_instruction",
        "close_instruction",
        "flatten_instruction",
    ],
)
def test_playbook_metadata_rejects_forbidden_parameter_profile_fields(field_name: str):
    payload = initial_strategy_family_registry_seed(now_ms=1770000000000).playbooks[
        0
    ].model_dump(mode="python")
    payload["parameter_profile"][field_name] = "must_not_exist"

    with pytest.raises(ValueError, match="forbidden execution/order field"):
        StrategyFamilyPlaybookMetadata.model_validate(payload)


def test_registry_evidence_requirements_are_string_labels_not_execution_payloads():
    family_payload = initial_strategy_family_registry_seed(now_ms=1770000000000).families[
        0
    ].model_dump(mode="python")
    family_payload["evidence_requirements"] = [{"quantity": "must_not_exist"}]

    with pytest.raises(ValueError):
        StrategyFamilyMetadata.model_validate(family_payload)

    playbook_payload = initial_strategy_family_registry_seed(now_ms=1770000000000).playbooks[
        0
    ].model_dump(mode="python")
    playbook_payload["evidence_requirements"] = [{"order_type": "must_not_exist"}]

    with pytest.raises(ValueError):
        StrategyFamilyPlaybookMetadata.model_validate(playbook_payload)


def test_registry_metadata_serialization_round_trip_preserves_review_fields():
    original = initial_strategy_family_registry_seed(now_ms=1770000000000).families[0]
    dumped = original.model_dump(mode="json")
    restored = StrategyFamilyMetadata.model_validate(dumped)

    assert restored.family_id == original.family_id
    assert restored.version_id == original.version_id
    assert restored.status == original.status
    assert restored.alpha_claim is False
    assert restored.carrier_validation is True
    assert restored.allowed_signal_types == original.allowed_signal_types
    assert restored.review_metrics == original.review_metrics


def test_registry_repository_does_not_expose_execution_or_router_actions():
    public_methods = {
        name
        for name, member in inspect.getmembers(PgStrategyFamilyRegistryRepository)
        if inspect.iscoroutinefunction(member) and not name.startswith("_")
    }

    forbidden_terms = {
        "execution_intent",
        "order",
        "trial_trade_intent",
        "router",
        "route",
        "execute",
        "schedule",
        "select_strategy",
    }
    assert not any(
        term in method_name
        for method_name in public_methods
        for term in forbidden_terms
    )
