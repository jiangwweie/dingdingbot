from decimal import Decimal

import pytest

from src.domain.validators import (
    coerce_decimal_fields,
    coerce_decimal_list_fields,
    stable_config_hash,
    validate_tp_contract,
)


def test_coerce_decimal_fields_preserves_none_and_existing_decimal():
    payload = {
        "max_loss_percent": Decimal("0.01"),
        "max_total_exposure": None,
    }

    converted = coerce_decimal_fields(payload, ("max_loss_percent", "max_total_exposure"))

    assert converted["max_loss_percent"] == Decimal("0.01")
    assert converted["max_total_exposure"] is None


def test_coerce_decimal_list_fields_supports_empty_list():
    payload = {"tp_ratios": []}

    converted = coerce_decimal_list_fields(payload, ("tp_ratios",))

    assert converted["tp_ratios"] == []


def test_coerce_decimal_list_fields_rejects_non_list_inputs():
    with pytest.raises(TypeError, match="expected list for tp_ratios"):
        coerce_decimal_list_fields({"tp_ratios": "0.5"}, ("tp_ratios",))


def test_validate_tp_contract_rejects_invalid_level_lengths():
    with pytest.raises(ValueError, match="tp_ratios length must match tp_levels"):
        validate_tp_contract(
            tp_levels=0,
            tp_ratios=(Decimal("0.5"),),
            tp_targets=(Decimal("1.0"),),
        )


def test_stable_config_hash_changes_when_schema_version_changes():
    payload = {"profile": {"a": "中文", "b": 2}}

    assert stable_config_hash(payload, schema_version=1) != stable_config_hash(payload, schema_version=2)
