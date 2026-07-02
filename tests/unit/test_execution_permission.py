from __future__ import annotations

from src.application.execution_permission import (
    ExecutionPermission,
    ExecutionPermissionResolver,
    parse_execution_permission_max,
    permission_allows,
)
from src.application.runtime_config import RuntimeConfigResolver


def test_execution_permission_ordering_and_min_resolution():
    assert ExecutionPermission.READ_ONLY < ExecutionPermission.SIGNAL_ONLY
    assert ExecutionPermission.SIGNAL_ONLY < ExecutionPermission.INTENT_RECORDING
    assert ExecutionPermission.INTENT_RECORDING < ExecutionPermission.EXECUTION_INTENT_ALLOWED
    assert ExecutionPermission.EXECUTION_INTENT_ALLOWED < ExecutionPermission.ORDER_ALLOWED
    assert min(
        [
            ExecutionPermission.ORDER_ALLOWED,
            ExecutionPermission.INTENT_RECORDING,
            ExecutionPermission.SIGNAL_ONLY,
        ]
    ) == ExecutionPermission.SIGNAL_ONLY
    assert permission_allows("intent_recording", "signal_only") is True
    assert permission_allows("signal_only", "intent_recording") is False


def test_brc_execution_permission_max_defaults_fail_closed_to_read_only():
    resolver = ExecutionPermissionResolver(env={})

    result = resolver.resolve(
        requested_permission=ExecutionPermission.INTENT_RECORDING,
        operation_type="record_trial_trade_intent_from_signal_evaluation",
        operation_permission=ExecutionPermission.INTENT_RECORDING,
        account_facts={
            "source": "exchange_testnet",
            "truth_level": "exchange_read",
            "reconciliation_status": {"status": "clean"},
            "unknown_unmanaged_counts": {"orders": 0, "positions": 0},
        },
        constraints_check={"complete": True, "constraints_snapshot_exists": True},
        campaign_metadata={},
        runtime_summary={"current_runtime_state": "observe", "live_ready": False},
    )

    assert result.configured_max_permission == ExecutionPermission.READ_ONLY
    assert result.final_permission == ExecutionPermission.READ_ONLY
    assert "below requested intent_recording" in result.downgrade_reason


def test_configured_max_signal_only_blocks_intent_recording():
    resolver = ExecutionPermissionResolver(
        configured_max_permission=ExecutionPermission.SIGNAL_ONLY,
    )

    result = resolver.resolve(
        requested_permission=ExecutionPermission.INTENT_RECORDING,
        operation_type="record_trial_trade_intent_from_signal_evaluation",
        operation_permission=ExecutionPermission.INTENT_RECORDING,
        account_facts={
            "source": "exchange_testnet",
            "truth_level": "exchange_read",
            "reconciliation_status": {"status": "clean"},
            "unknown_unmanaged_counts": {"orders": 0, "positions": 0},
        },
        constraints_check={"complete": True, "constraints_snapshot_exists": True},
        campaign_metadata={},
        runtime_summary={"current_runtime_state": "observe", "live_ready": False},
    )

    assert result.final_permission == ExecutionPermission.SIGNAL_ONLY
    assert result.blockers


def test_configured_max_intent_recording_allows_intent_if_other_contributors_allow():
    resolver = ExecutionPermissionResolver(
        configured_max_permission=ExecutionPermission.INTENT_RECORDING,
    )

    result = resolver.resolve(
        requested_permission=ExecutionPermission.INTENT_RECORDING,
        operation_type="record_trial_trade_intent_from_signal_evaluation",
        operation_permission=ExecutionPermission.INTENT_RECORDING,
        account_facts={
            "source": "exchange_testnet",
            "truth_level": "exchange_read",
            "reconciliation_status": {"status": "clean"},
            "unknown_unmanaged_counts": {"orders": 0, "positions": 0},
        },
        constraints_check={"complete": True, "constraints_snapshot_exists": True},
        campaign_metadata={},
        runtime_summary={"current_runtime_state": "observe", "live_ready": False},
    )

    assert result.final_permission == ExecutionPermission.INTENT_RECORDING
    assert not result.blockers


def test_runtime_safety_readiness_blockers_downgrade_intent_recording():
    resolver = ExecutionPermissionResolver(
        configured_max_permission=ExecutionPermission.INTENT_RECORDING,
    )

    result = resolver.resolve(
        requested_permission=ExecutionPermission.INTENT_RECORDING,
        operation_type="record_trial_trade_intent_from_signal_evaluation",
        operation_permission=ExecutionPermission.INTENT_RECORDING,
        account_facts={
            "source": "exchange_testnet",
            "truth_level": "exchange_read",
            "reconciliation_status": {"status": "clean"},
            "unknown_unmanaged_counts": {"orders": 0, "positions": 0},
        },
        constraints_check={"complete": True, "constraints_snapshot_exists": True},
        campaign_metadata={},
        runtime_summary={
            "current_runtime_state": "observe",
            "live_ready": False,
            "runtime_safety_readiness": {
                "status": "blocked",
                "blockers": ["max_loss_budget_present"],
                "missing_boundary_facts": ["max_loss_budget_present"],
                "not_execution_authority": True,
                "execution_intent_created": False,
                "runtime_state_mutated": False,
                "order_created": False,
                "exchange_called": False,
            },
        },
    )

    assert result.runtime_safety_permission == ExecutionPermission.SIGNAL_ONLY
    assert result.final_permission == ExecutionPermission.SIGNAL_ONLY
    assert any(
        "runtime safety readiness blocks intent recording" in blocker
        and "max_loss_budget_present" in blocker
        for blocker in result.blockers
    )


def test_runtime_safety_readiness_ready_preserves_intent_recording_cap():
    resolver = ExecutionPermissionResolver(
        configured_max_permission=ExecutionPermission.INTENT_RECORDING,
    )

    result = resolver.resolve(
        requested_permission=ExecutionPermission.INTENT_RECORDING,
        operation_type="record_trial_trade_intent_from_signal_evaluation",
        operation_permission=ExecutionPermission.INTENT_RECORDING,
        account_facts={
            "source": "exchange_testnet",
            "truth_level": "exchange_read",
            "reconciliation_status": {"status": "clean"},
            "unknown_unmanaged_counts": {"orders": 0, "positions": 0},
        },
        constraints_check={"complete": True, "constraints_snapshot_exists": True},
        campaign_metadata={},
        runtime_summary={
            "current_runtime_state": "observe",
            "live_ready": False,
            "runtime_safety_readiness": {
                "status": "ready_for_owner_codex_confirmation",
                "blockers": [],
                "missing_boundary_facts": [],
                "warnings": ["trusted_fact_sources_required"],
                "not_execution_authority": True,
                "execution_intent_created": False,
                "runtime_state_mutated": False,
                "order_created": False,
                "exchange_called": False,
            },
        },
    )

    assert result.runtime_safety_permission == ExecutionPermission.INTENT_RECORDING
    assert result.final_permission == ExecutionPermission.INTENT_RECORDING
    assert not result.blockers


def test_account_facts_unavailable_downgrades_and_blocks_intent_recording():
    resolver = ExecutionPermissionResolver(
        configured_max_permission=ExecutionPermission.INTENT_RECORDING,
    )

    result = resolver.resolve(
        requested_permission=ExecutionPermission.INTENT_RECORDING,
        operation_type="record_trial_trade_intent_from_signal_evaluation",
        operation_permission=ExecutionPermission.INTENT_RECORDING,
        account_facts={"source": "unavailable", "truth_level": "unavailable"},
        constraints_check={"complete": True, "constraints_snapshot_exists": True},
        campaign_metadata={},
        runtime_summary={"current_runtime_state": "observe", "live_ready": False},
    )

    assert result.account_facts_permission == ExecutionPermission.SIGNAL_ONLY
    assert result.final_permission == ExecutionPermission.SIGNAL_ONLY
    assert "account facts unavailable" in result.blockers


def test_unknown_api_key_capability_cannot_produce_order_allowed():
    resolver = ExecutionPermissionResolver(
        configured_max_permission=ExecutionPermission.ORDER_ALLOWED,
    )

    result = resolver.resolve(
        requested_permission=ExecutionPermission.ORDER_ALLOWED,
        operation_type="future_order_operation",
        operation_permission=ExecutionPermission.ORDER_ALLOWED,
        account_facts={
            "source": "exchange_live",
            "truth_level": "reconciled",
            "reconciliation_status": {"status": "clean"},
            "unknown_unmanaged_counts": {"orders": 0, "positions": 0},
        },
        constraints_check={"complete": True, "constraints_snapshot_exists": True},
        campaign_metadata={},
        runtime_summary={"current_runtime_state": "observe", "live_ready": False},
    )

    assert result.api_key_capability == ExecutionPermission.INTENT_RECORDING
    assert result.final_permission == ExecutionPermission.INTENT_RECORDING
    assert "unknown API key capability cannot allow execution intents or orders" in result.blockers


def test_parse_execution_permission_max_accepts_supported_values():
    assert parse_execution_permission_max("read_only") == ExecutionPermission.READ_ONLY
    assert parse_execution_permission_max("signal_only") == ExecutionPermission.SIGNAL_ONLY
    assert parse_execution_permission_max("intent_recording") == ExecutionPermission.INTENT_RECORDING
    assert (
        parse_execution_permission_max("execution_intent_allowed")
        == ExecutionPermission.EXECUTION_INTENT_ALLOWED
    )
    assert parse_execution_permission_max("order_allowed") == ExecutionPermission.ORDER_ALLOWED


def test_runtime_config_parses_trading_env_and_brc_execution_permission_max():
    resolver = RuntimeConfigResolver(
        profile_repository=object(),
        env={
            "PG_DATABASE_URL": "postgresql://example",
            "CORE_EXECUTION_INTENT_BACKEND": "postgres",
            "CORE_ORDER_BACKEND": "postgres",
            "CORE_POSITION_BACKEND": "postgres",
            "TRADING_ENV": "live",
            "EXCHANGE_NAME": "binance",
            "EXCHANGE_TESTNET": "false",
            "BRC_EXECUTION_PERMISSION_MAX": "intent_recording",
            "EXCHANGE_API_KEY": "key",
            "EXCHANGE_API_SECRET": "secret",
            "FEISHU_WEBHOOK_URL": "https://example.invalid/hook",
            "BACKEND_PORT": "8000",
        },
    )

    environment = resolver._resolve_environment()

    assert environment.trading_env == "live"
    assert environment.exchange_testnet is False
    assert environment.brc_execution_permission_max == ExecutionPermission.INTENT_RECORDING


def test_runtime_config_allows_missing_feishu_webhook_for_no_notification_runtime():
    resolver = RuntimeConfigResolver(
        profile_repository=object(),
        env={
            "PG_DATABASE_URL": "postgresql://example",
            "CORE_EXECUTION_INTENT_BACKEND": "postgres",
            "CORE_ORDER_BACKEND": "postgres",
            "CORE_POSITION_BACKEND": "postgres",
            "TRADING_ENV": "live",
            "EXCHANGE_NAME": "binance",
            "EXCHANGE_TESTNET": "false",
            "BRC_EXECUTION_PERMISSION_MAX": "read_only",
            "EXCHANGE_API_KEY": "key",
            "EXCHANGE_API_SECRET": "secret",
            "BACKEND_PORT": "8000",
        },
    )

    environment = resolver._resolve_environment()

    assert environment.trading_env == "live"
    assert environment.exchange_testnet is False
    assert environment.brc_execution_permission_max == ExecutionPermission.READ_ONLY
    assert environment.feishu_webhook_url is None


def test_runtime_config_rejects_non_postgres_mainline_storage_backend():
    resolver = RuntimeConfigResolver(
        profile_repository=object(),
        env={
            "PG_DATABASE_URL": "postgresql://example",
            "CORE_EXECUTION_INTENT_BACKEND": "postgres",
            "CORE_ORDER_BACKEND": "sqlite",
            "CORE_POSITION_BACKEND": "postgres",
            "TRADING_ENV": "testnet",
            "EXCHANGE_NAME": "binance",
            "EXCHANGE_TESTNET": "true",
            "BRC_EXECUTION_PERMISSION_MAX": "intent_recording",
            "EXCHANGE_API_KEY": "key",
            "EXCHANGE_API_SECRET": "secret",
            "FEISHU_WEBHOOK_URL": "https://example.invalid/hook",
        },
    )

    try:
        resolver._resolve_environment()
    except ValueError as exc:
        assert "mainline runtime requires PostgreSQL core backends" in str(exc)
        assert "CORE_ORDER_BACKEND=sqlite" in str(exc)
    else:
        raise AssertionError("expected non-postgres mainline backend to be rejected")


def test_live_runtime_config_accepts_order_capable_ceiling_env():
    resolver = RuntimeConfigResolver(
        profile_repository=object(),
        env={
            "PG_DATABASE_URL": "postgresql://example",
            "CORE_EXECUTION_INTENT_BACKEND": "postgres",
            "CORE_ORDER_BACKEND": "postgres",
            "CORE_POSITION_BACKEND": "postgres",
            "TRADING_ENV": "live",
            "EXCHANGE_NAME": "binance",
            "EXCHANGE_TESTNET": "false",
            "BRC_EXECUTION_PERMISSION_MAX": "order_allowed",
            "EXCHANGE_API_KEY": "key",
            "EXCHANGE_API_SECRET": "secret",
            "FEISHU_WEBHOOK_URL": "https://example.invalid/hook",
        },
    )

    resolved = resolver._resolve_environment()

    assert resolved.brc_execution_permission_max == ExecutionPermission.ORDER_ALLOWED


def test_live_runtime_config_rejects_generic_execution_intent_allowed_env():
    resolver = RuntimeConfigResolver(
        profile_repository=object(),
        env={
            "PG_DATABASE_URL": "postgresql://example",
            "CORE_EXECUTION_INTENT_BACKEND": "postgres",
            "CORE_ORDER_BACKEND": "postgres",
            "CORE_POSITION_BACKEND": "postgres",
            "TRADING_ENV": "live",
            "EXCHANGE_NAME": "binance",
            "EXCHANGE_TESTNET": "false",
            "BRC_EXECUTION_PERMISSION_MAX": "execution_intent_allowed",
            "EXCHANGE_API_KEY": "key",
            "EXCHANGE_API_SECRET": "secret",
            "FEISHU_WEBHOOK_URL": "https://example.invalid/hook",
        },
    )

    try:
        resolver._resolve_environment()
    except ValueError as exc:
        assert "TRADING_ENV=live cannot use generic execution_intent_allowed" in str(exc)
    else:
        raise AssertionError("expected live generic execution intent permission to be rejected")
