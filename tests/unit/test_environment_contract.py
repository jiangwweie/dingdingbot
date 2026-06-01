from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.database import validate_pg_core_configuration


REPO_ROOT = Path(__file__).resolve().parents[2]


def _valid_env(**overrides: str) -> dict[str, str]:
    env = {
        "APP_ENV": "development",
        "TRADING_ENV": "testnet",
        "EXCHANGE_TESTNET": "true",
        "PG_DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
        "CORE_EXECUTION_INTENT_BACKEND": "postgres",
        "CORE_ORDER_BACKEND": "postgres",
        "CORE_POSITION_BACKEND": "postgres",
        "BRC_EXECUTION_PERMISSION_MAX": "intent_recording",
        "EXCHANGE_API_KEY": "key",
        "EXCHANGE_API_SECRET": "secret",
    }
    env.update(overrides)
    return env


def test_validate_pg_core_configuration_accepts_testnet_rehearsal_profile():
    validate_pg_core_configuration(
        _valid_env(
            RUNTIME_PROFILE="brc_btc_eth_testnet_runtime",
            RUNTIME_CONTROL_API_ENABLED="true",
            RUNTIME_TEST_SIGNAL_INJECTION_ENABLED="true",
        )
    )


def test_validate_pg_core_configuration_rejects_non_postgres_backend():
    with pytest.raises(ValueError, match="主线核心后端必须使用 postgres"):
        validate_pg_core_configuration(_valid_env(CORE_ORDER_BACKEND="sqlite"))


def test_validate_pg_core_configuration_rejects_live_global_order_permission():
    with pytest.raises(ValueError, match="全局授予 execution/order 权限"):
        validate_pg_core_configuration(
            _valid_env(
                APP_ENV="production",
                TRADING_ENV="live",
                EXCHANGE_TESTNET="false",
                BRC_EXECUTION_PERMISSION_MAX="order_allowed",
            )
        )


def test_validate_pg_core_configuration_rejects_live_runtime_profile_selector():
    with pytest.raises(ValueError, match="RUNTIME_PROFILE"):
        validate_pg_core_configuration(
            _valid_env(
                APP_ENV="production",
                TRADING_ENV="live",
                EXCHANGE_TESTNET="false",
                RUNTIME_PROFILE="tiny_live_50u_eth",
            )
        )


def test_validate_pg_core_configuration_rejects_live_test_signal_injection():
    with pytest.raises(ValueError, match="RUNTIME_TEST_SIGNAL_INJECTION_ENABLED"):
        validate_pg_core_configuration(
            _valid_env(
                APP_ENV="production",
                TRADING_ENV="live",
                EXCHANGE_TESTNET="false",
                RUNTIME_TEST_SIGNAL_INJECTION_ENABLED="true",
            )
        )


def test_production_template_is_conservative_and_non_secret():
    text = (REPO_ROOT / ".env.production.example").read_text()

    assert "TRADING_ENV=live" in text
    assert "BRC_EXECUTION_PERMISSION_MAX=read_only" in text
    assert "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=false" in text
    assert "RUNTIME_CONTROL_API_ENABLED=false" in text
    assert "RUNTIME_PROFILE=" not in text
    assert "order_allowed" not in text
    assert "BINANCE_SECRET_KEY" not in text
    assert "<set_on_server>" in text


def test_testnet_template_allows_controlled_rehearsal_but_uses_pg_backends():
    text = (REPO_ROOT / ".env.local.testnet.example").read_text()

    assert "TRADING_ENV=testnet" in text
    assert "EXCHANGE_TESTNET=true" in text
    assert "CORE_EXECUTION_INTENT_BACKEND=postgres" in text
    assert "CORE_ORDER_BACKEND=postgres" in text
    assert "CORE_POSITION_BACKEND=postgres" in text
    assert "RUNTIME_PROFILE=brc_btc_eth_testnet_runtime" in text
    assert "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=true" in text
    assert "BRC_EXECUTION_PERMISSION_MAX=intent_recording" in text


def test_legacy_tiny_live_template_is_read_only_by_default():
    text = (REPO_ROOT / ".env.tiny-live.example").read_text()

    assert "RUNTIME_PROFILE=" not in text
    assert "BRC_EXECUTION_PERMISSION_MAX=read_only" in text
    assert "RUNTIME_CONTROL_API_ENABLED=false" in text
    assert "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=false" in text
