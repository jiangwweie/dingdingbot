import pytest

from scripts.probe_generic_final_gate_readonly import (
    DEFAULT_CARRIER_ID,
    action_spec_for_carrier,
    build_probe_plan,
    guard_probe_environment,
)


def _safe_env(**override: str) -> dict[str, str]:
    env = {
        "TRADING_ENV": "live",
        "EXCHANGE_TESTNET": "false",
        "BRC_EXECUTION_PERMISSION_MAX": "read_only",
        "RUNTIME_CONTROL_API_ENABLED": "false",
        "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "false",
        "CORE_EXECUTION_INTENT_BACKEND": "postgres",
        "CORE_ORDER_BACKEND": "postgres",
        "CORE_POSITION_BACKEND": "postgres",
        "PG_DATABASE_URL": "postgresql://example.invalid/brc",
    }
    env.update(override)
    return env


def test_generic_final_gate_probe_plan_is_dry_run_by_default():
    plan = build_probe_plan(_safe_env())

    assert plan["mode"] == "dry_run"
    assert plan["carrier_id"] == DEFAULT_CARRIER_ID
    assert plan["safety"]["creates_authorization"] is False
    assert plan["safety"]["creates_execution_intent"] is False
    assert plan["safety"]["places_order"] is False
    assert plan["safety"]["starts_runtime"] is False
    assert plan["safety"]["exchange_write_methods_called"] is False


def test_generic_final_gate_probe_plan_can_be_explicit_run_mode():
    plan = build_probe_plan(
        _safe_env(
            RUN_GENERIC_FINAL_GATE_PROBE="true",
            GENERIC_FINAL_GATE_CARRIER_ID="TF-001-live-readonly-v0",
        )
    )

    assert plan["mode"] == "run"
    assert plan["carrier_id"] == "TF-001-live-readonly-v0"


def test_generic_final_gate_probe_guard_accepts_safe_env():
    guard_probe_environment(_safe_env())


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"BRC_EXECUTION_PERMISSION_MAX": "order_allowed"}, "BRC_EXECUTION_PERMISSION_MAX"),
        ({"RUNTIME_CONTROL_API_ENABLED": "true"}, "RUNTIME_CONTROL_API_ENABLED"),
        ({"RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "true"}, "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED"),
        ({"EXCHANGE_TESTNET": "true"}, "EXCHANGE_TESTNET"),
        ({"PG_DATABASE_URL": ""}, "PG_DATABASE_URL"),
    ],
)
def test_generic_final_gate_probe_guard_rejects_unsafe_env(
    override: dict[str, str],
    message: str,
):
    with pytest.raises(ValueError, match=message):
        guard_probe_environment(_safe_env(**override))


def test_generic_final_gate_probe_builds_exact_trend_action_spec():
    action_spec = action_spec_for_carrier("TF-001-live-readonly-v0")

    assert action_spec.status == "valid_blocked_final_gate"
    assert action_spec.action_registry_supported is True
    assert action_spec.carrier_id == "TF-001-live-readonly-v0"
    assert action_spec.symbol == "SOL/USDT:USDT"
    assert action_spec.side == "long"
    assert action_spec.quantity == "0.1"
    assert action_spec.max_notional == "20"
    assert action_spec.leverage == "1"
    assert action_spec.protection_mode == "single_tp_plus_sl"


def test_generic_final_gate_probe_fails_closed_for_non_catalog_carrier():
    action_spec = action_spec_for_carrier("VE-001-live-readonly-v0")

    assert action_spec.status == "invalid_blocked"
    assert action_spec.action_registry_supported is False
    assert action_spec.hard_blockers == ["unsupported_carrier"]
