import asyncio
import time

from fastapi.testclient import TestClient

from src.application.exchange_credential_preflight import run_exchange_credential_preflight
from src.application.exchange_credential_preflight import (
    binance_api_restriction_summary,
    classify_exchange_credential_error,
    credential_preflight_env_blockers,
    exchange_credential_env_status,
)


def test_exchange_credential_env_status_uses_canonical_names_without_values():
    status = exchange_credential_env_status(
        {
            "TRADING_ENV": "live",
            "EXCHANGE_TESTNET": "false",
            "BRC_EXECUTION_PERMISSION_MAX": "order_allowed",
            "RUNTIME_CONTROL_API_ENABLED": "false",
            "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "false",
            "EXCHANGE_NAME": "binance",
            "EXCHANGE_API_KEY": "real-key",
            "EXCHANGE_API_SECRET": "real-secret",
            "BINANCE_API_KEY": "ignored-key",
        }
    )

    assert status["canonical_credentials_present"] is True
    assert status["binance_alias_credentials_ignored_by_mainline"] is True
    assert "real-key" not in repr(status)
    assert "real-secret" not in repr(status)
    assert credential_preflight_env_blockers(status) == []


def test_credential_preflight_env_blockers_fail_closed():
    status = exchange_credential_env_status(
        {
            "TRADING_ENV": "live",
            "EXCHANGE_TESTNET": "true",
            "EXCHANGE_NAME": "binance",
            "BINANCE_API_KEY": "ignored-key",
            "BINANCE_SECRET_KEY": "ignored-secret",
        }
    )

    assert "exchange_testnet_not_false" in credential_preflight_env_blockers(status)
    assert "exchange_api_key_missing" in credential_preflight_env_blockers(status)
    assert "exchange_api_secret_missing" in credential_preflight_env_blockers(status)
    assert status["binance_alias_credentials_ignored_by_mainline"] is True


def test_classify_exchange_credential_errors_without_raw_message():
    invalid_key = classify_exchange_credential_error(
        'binance {"code":-2008,"msg":"Invalid Api-Key ID."}'
    )
    invalid_permission = classify_exchange_credential_error(
        'binance {"code":-2015,"msg":"Invalid API-key, IP, or permissions for action."}'
    )
    bad_signature = classify_exchange_credential_error(
        'binance {"code":-1022,"msg":"Signature for this request is not valid."}'
    )

    assert invalid_key == {
        "category": "invalid_api_key_id",
        "exchange_error_code": "-2008",
        "error_type": "str",
    }
    assert invalid_permission["category"] == "invalid_api_key_ip_or_permissions"
    assert invalid_permission["exchange_error_code"] == "-2015"
    assert bad_signature["category"] == "secret_mismatch_or_invalid_signature"
    assert bad_signature["exchange_error_code"] == "-1022"
    assert "Invalid Api-Key" not in repr(invalid_key)
    assert "permissions for action" not in repr(invalid_permission)


def test_binance_api_restriction_summary_keeps_only_permission_flags():
    summary = binance_api_restriction_summary(
        {
            "enableReading": True,
            "enableFutures": True,
            "enableSpotAndMarginTrading": False,
            "enableWithdrawals": False,
            "ipRestrict": True,
            "createTime": 123,
        }
    )

    assert summary == {
        "reading_enabled": True,
        "futures_enabled": True,
        "read_only_permission_present": True,
        "futures_trade_permission_present": True,
        "order_permission_distinguished_from_read_only": True,
        "spot_margin_trading_enabled": False,
        "withdrawals_enabled": False,
        "ip_restricted": True,
    }


def test_run_exchange_credential_preflight_fake_gateway_passes_without_secrets():
    class FakeRestExchange:
        symbols = ["SOL/USDT:USDT"]

        async def sapi_get_account_apirestrictions(self):
            return {
                "enableReading": True,
                "enableFutures": True,
                "enableWithdrawals": False,
                "ipRestrict": True,
            }

        async def fetch_balance(self, params):
            assert params == {"type": "future"}
            return {"total": {"USDT": "25"}}

    class FakeGateway:
        def __init__(self, **kwargs):
            assert kwargs["api_key"] == "server-key"
            assert kwargs["api_secret"] == "server-secret"
            self.rest_exchange = FakeRestExchange()
            self.closed = False

        async def initialize(self):
            return None

        async def fetch_positions(self, *, symbol=None):
            assert symbol == "SOL/USDT:USDT"
            return []

        async def fetch_open_orders(self, symbol, params=None):
            assert symbol == "SOL/USDT:USDT"
            return []

        async def get_market_info(self, symbol):
            assert symbol == "SOL/USDT:USDT"
            return {
                "min_quantity": "0.1",
                "step_size": "0.1",
                "min_notional": "5",
                "price_precision": 2,
            }

        async def close(self):
            self.closed = True

    env = {
        "TRADING_ENV": "live",
        "EXCHANGE_TESTNET": "false",
        "RUNTIME_CONTROL_API_ENABLED": "false",
        "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "false",
        "EXCHANGE_NAME": "binance",
        "EXCHANGE_API_KEY": "server-key",
        "EXCHANGE_API_SECRET": "server-secret",
    }

    result = asyncio.run(
        run_exchange_credential_preflight(
            env=env,
            gateway_factory=FakeGateway,
            run=True,
        )
    )

    assert result["result"] == "passed"
    assert result["hard_blockers"] == []
    assert len(result["checks"]) == 7
    assert result["checks"][1]["permissions"]["withdrawals_enabled"] is False
    assert "server-key" not in repr(result)
    assert "server-secret" not in repr(result)


def test_run_exchange_credential_preflight_accepts_mr_eth_exact_scope_without_secrets():
    calls: list[tuple[str, object]] = []

    class FakeRestExchange:
        symbols = ["ETH/USDT:USDT"]

        async def sapi_get_account_apirestrictions(self):
            return {
                "enableReading": True,
                "enableFutures": True,
                "enableWithdrawals": False,
                "ipRestrict": True,
            }

        async def fetch_balance(self, params):
            assert params == {"type": "future"}
            return {"total": {"USDT": "25"}}

    class FakeGateway:
        def __init__(self, **kwargs):
            assert kwargs["api_key"] == "server-key"
            assert kwargs["api_secret"] == "server-secret"
            self.rest_exchange = FakeRestExchange()

        async def initialize(self):
            return None

        async def fetch_positions(self, *, symbol=None):
            calls.append(("positions", symbol))
            return []

        async def fetch_open_orders(self, symbol, params=None):
            calls.append(("open_orders", (symbol, params)))
            return []

        async def get_market_info(self, symbol):
            calls.append(("market_info", symbol))
            return {
                "min_quantity": "0.001",
                "step_size": "0.001",
                "min_notional": "20",
                "price_precision": 2,
            }

        async def close(self):
            return None

    result = asyncio.run(
        run_exchange_credential_preflight(
            env={
                "TRADING_ENV": "live",
                "EXCHANGE_TESTNET": "false",
                "RUNTIME_CONTROL_API_ENABLED": "false",
                "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "false",
                "EXCHANGE_NAME": "binance",
                "EXCHANGE_API_KEY": "server-key",
                "EXCHANGE_API_SECRET": "server-secret",
            },
            gateway_factory=FakeGateway,
            symbol="ETH/USDT:USDT",
            run=True,
        )
    )

    assert result["result"] == "passed"
    assert result["hard_blockers"] == []
    assert ("positions", "ETH/USDT:USDT") in calls
    assert ("open_orders", ("ETH/USDT:USDT", None)) in calls
    assert ("open_orders", ("ETH/USDT:USDT", {"stop": True})) in calls
    assert ("market_info", "ETH/USDT:USDT") in calls
    assert "server-key" not in repr(result)
    assert "server-secret" not in repr(result)


def test_run_exchange_credential_preflight_blocks_withdrawal_permission():
    class FakeRestExchange:
        symbols = ["SOL/USDT:USDT"]

        async def sapi_get_account_apirestrictions(self):
            return {
                "enableReading": True,
                "enableFutures": True,
                "enableWithdrawals": True,
                "ipRestrict": True,
            }

        async def fetch_balance(self, params):
            return {"total": {"USDT": "25"}}

    class FakeGateway:
        def __init__(self, **_kwargs):
            self.rest_exchange = FakeRestExchange()

        async def initialize(self):
            return None

        async def fetch_positions(self, *, symbol=None):
            return []

        async def fetch_open_orders(self, symbol, params=None):
            return []

        async def get_market_info(self, symbol):
            return {
                "min_quantity": "0.1",
                "step_size": "0.1",
                "min_notional": "5",
                "price_precision": 2,
            }

        async def close(self):
            return None

    result = asyncio.run(
        run_exchange_credential_preflight(
            env={
                "TRADING_ENV": "live",
                "EXCHANGE_TESTNET": "false",
                "RUNTIME_CONTROL_API_ENABLED": "false",
                "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "false",
                "EXCHANGE_NAME": "binance",
                "EXCHANGE_API_KEY": "server-key",
                "EXCHANGE_API_SECRET": "server-secret",
            },
            gateway_factory=FakeGateway,
            run=True,
        )
    )

    assert result["result"] == "blocked"
    assert result["hard_blockers"] == ["withdraw_permission_enabled"]
    assert result["checks"][1]["permissions"]["withdrawals_enabled"] is True
    assert "server-key" not in repr(result)
    assert "server-secret" not in repr(result)


def test_run_exchange_credential_preflight_fail_fast_on_restriction_failure():
    class FakeRestExchange:
        symbols = ["SOL/USDT:USDT"]

        async def sapi_get_account_apirestrictions(self):
            raise RuntimeError(
                'binance {"code":-2015,"msg":"Invalid API-key, IP, or permissions for action."}'
            )

        async def fetch_balance(self, params):
            raise AssertionError("futures account read must not run after restriction failure")

    class FakeGateway:
        def __init__(self, **_kwargs):
            self.rest_exchange = FakeRestExchange()

        async def initialize(self):
            return None

        async def close(self):
            return None

    result = asyncio.run(
        run_exchange_credential_preflight(
            env={
                "TRADING_ENV": "live",
                "EXCHANGE_TESTNET": "false",
                "RUNTIME_CONTROL_API_ENABLED": "false",
                "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "false",
                "EXCHANGE_NAME": "binance",
                "EXCHANGE_API_KEY": "server-key",
                "EXCHANGE_API_SECRET": "server-secret",
            },
            gateway_factory=FakeGateway,
            run=True,
        )
    )

    assert result["result"] == "blocked"
    assert result["hard_blockers"] == [
        "binance_api_restrictions:invalid_api_key_ip_or_permissions"
    ]
    assert [check["name"] for check in result["checks"]] == [
        "load_usdt_m_futures_markets",
        "binance_api_restrictions",
    ]
    assert "Invalid API-key" not in repr(result)


def test_run_exchange_credential_preflight_fail_fast_on_futures_account_failure():
    class FakeRestExchange:
        symbols = ["SOL/USDT:USDT"]

        async def sapi_get_account_apirestrictions(self):
            return {
                "enableReading": True,
                "enableFutures": True,
                "enableWithdrawals": False,
                "ipRestrict": True,
            }

        async def fetch_balance(self, params):
            raise RuntimeError('binance {"code":-2015,"msg":"Futures permission missing."}')

    class FakeGateway:
        def __init__(self, **_kwargs):
            self.rest_exchange = FakeRestExchange()

        async def initialize(self):
            return None

        async def fetch_positions(self, *, symbol=None):
            raise AssertionError("scoped reads must not run after futures account failure")

        async def close(self):
            return None

    result = asyncio.run(
        run_exchange_credential_preflight(
            env={
                "TRADING_ENV": "live",
                "EXCHANGE_TESTNET": "false",
                "RUNTIME_CONTROL_API_ENABLED": "false",
                "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "false",
                "EXCHANGE_NAME": "binance",
                "EXCHANGE_API_KEY": "server-key",
                "EXCHANGE_API_SECRET": "server-secret",
            },
            gateway_factory=FakeGateway,
            run=True,
        )
    )

    assert result["result"] == "blocked"
    assert result["hard_blockers"] == [
        "usdt_m_futures_account_read:invalid_api_key_ip_or_permissions"
    ]
    assert [check["name"] for check in result["checks"]] == [
        "load_usdt_m_futures_markets",
        "binance_api_restrictions",
        "usdt_m_futures_account_read",
    ]


def test_run_exchange_credential_preflight_blocks_unsupported_symbol_before_gateway():
    class GatewayMustNotConstruct:
        def __init__(self, **_kwargs):
            raise AssertionError("gateway must not be constructed for unsupported symbol")

    result = asyncio.run(
        run_exchange_credential_preflight(
            env={
                "TRADING_ENV": "live",
                "EXCHANGE_TESTNET": "false",
                "RUNTIME_CONTROL_API_ENABLED": "false",
                "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "false",
                "EXCHANGE_NAME": "binance",
                "EXCHANGE_API_KEY": "server-key",
                "EXCHANGE_API_SECRET": "server-secret",
            },
            gateway_factory=GatewayMustNotConstruct,
            symbol="BTC/USDT:USDT",
            run=True,
        )
    )

    assert result["result"] == "blocked"
    assert result["hard_blockers"] == ["unsupported_preflight_symbol"]
    assert result["checks"] == []


def test_exchange_credential_preflight_api_dry_run(monkeypatch):
    from src.interfaces.api import app
    from src.interfaces.operator_auth import OperatorSession, require_operator_session

    app.dependency_overrides[require_operator_session] = lambda: OperatorSession(
        username="owner",
        expires_at=int(time.time()) + 3600,
    )
    try:
        with TestClient(app) as client:
            response = client.get("/api/brc/owner-trial-flow/exchange-credential-preflight")
        assert response.status_code == 200
        payload = response.json()
        assert payload["mode"] == "dry_run"
        assert payload["result"] == "dry_run"
        assert payload["safety"]["places_order"] is False
        assert payload["safety"]["prints_secrets"] is False
        assert payload["checks"] == []
    finally:
        app.dependency_overrides.pop(require_operator_session, None)


def test_exchange_credential_preflight_api_run_blocks_on_env_before_gateway(monkeypatch):
    from src.interfaces import api_brc_console
    from src.interfaces.api import app
    from src.interfaces.operator_auth import OperatorSession, require_operator_session

    for name in (
        "TRADING_ENV",
        "EXCHANGE_TESTNET",
        "RUNTIME_CONTROL_API_ENABLED",
        "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED",
        "EXCHANGE_API_KEY",
        "EXCHANGE_API_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)

    class GatewayMustNotConstruct:
        def __init__(self, **_kwargs):
            raise AssertionError("gateway must not be constructed when env is blocked")

    monkeypatch.setattr(api_brc_console, "ExchangeGateway", GatewayMustNotConstruct)
    app.dependency_overrides[require_operator_session] = lambda: OperatorSession(
        username="owner",
        expires_at=int(time.time()) + 3600,
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/brc/owner-trial-flow/exchange-credential-preflight?run=true"
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["result"] == "blocked"
        assert "exchange_api_key_missing" in payload["hard_blockers"]
        assert payload["checks"] == []
        assert payload["safety"]["places_order"] is False
    finally:
        app.dependency_overrides.pop(require_operator_session, None)


def test_exchange_credential_preflight_api_run_with_fake_gateway(monkeypatch):
    from src.interfaces import api_brc_console
    from src.interfaces.api import app
    from src.interfaces.operator_auth import OperatorSession, require_operator_session

    class FakeRestExchange:
        symbols = ["SOL/USDT:USDT"]

        async def sapi_get_account_apirestrictions(self):
            return {
                "enableReading": True,
                "enableFutures": True,
                "enableWithdrawals": False,
                "ipRestrict": True,
            }

        async def fetch_balance(self, params):
            return {"total": {"USDT": "25"}}

    class FakeGateway:
        def __init__(self, **_kwargs):
            self.rest_exchange = FakeRestExchange()
            self.place_order_called = False
            self.closed = False

        async def initialize(self):
            return None

        async def fetch_positions(self, *, symbol=None):
            return []

        async def fetch_open_orders(self, symbol, params=None):
            return []

        async def get_market_info(self, symbol):
            return {
                "min_quantity": "0.1",
                "step_size": "0.1",
                "min_notional": "5",
                "price_precision": 2,
            }

        async def close(self):
            self.closed = True

    monkeypatch.setenv("TRADING_ENV", "live")
    monkeypatch.setenv("EXCHANGE_TESTNET", "false")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false")
    monkeypatch.setenv("EXCHANGE_NAME", "binance")
    monkeypatch.setenv("EXCHANGE_API_KEY", "server-key")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "server-secret")
    monkeypatch.setattr(api_brc_console, "ExchangeGateway", FakeGateway)
    app.dependency_overrides[require_operator_session] = lambda: OperatorSession(
        username="owner",
        expires_at=int(time.time()) + 3600,
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/brc/owner-trial-flow/exchange-credential-preflight?run=true"
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["result"] == "passed"
        assert payload["hard_blockers"] == []
        assert payload["checks"][1]["permissions"]["withdrawals_enabled"] is False
        assert "server-key" not in repr(payload)
        assert "server-secret" not in repr(payload)
    finally:
        app.dependency_overrides.pop(require_operator_session, None)


def test_exchange_credential_preflight_api_sanitizes_binance_permission_failure(monkeypatch):
    from src.interfaces import api_brc_console
    from src.interfaces.api import app
    from src.interfaces.operator_auth import OperatorSession, require_operator_session

    class FakeGateway:
        def __init__(self, **_kwargs):
            self.closed = False

        async def initialize(self):
            raise RuntimeError(
                'binance {"code":-2015,"msg":"Invalid API-key, IP, or permissions for action."}'
            )

        async def close(self):
            self.closed = True

    monkeypatch.setenv("TRADING_ENV", "live")
    monkeypatch.setenv("EXCHANGE_TESTNET", "false")
    monkeypatch.setenv("RUNTIME_CONTROL_API_ENABLED", "false")
    monkeypatch.setenv("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false")
    monkeypatch.setenv("EXCHANGE_NAME", "binance")
    monkeypatch.setenv("EXCHANGE_API_KEY", "server-key")
    monkeypatch.setenv("EXCHANGE_API_SECRET", "server-secret")
    monkeypatch.setattr(api_brc_console, "ExchangeGateway", FakeGateway)
    app.dependency_overrides[require_operator_session] = lambda: OperatorSession(
        username="owner",
        expires_at=int(time.time()) + 3600,
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/brc/owner-trial-flow/exchange-credential-preflight?run=true"
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["result"] == "blocked"
        assert payload["hard_blockers"] == [
            "load_usdt_m_futures_markets:invalid_api_key_ip_or_permissions"
        ]
        assert payload["checks"][0]["error"] == {
            "category": "invalid_api_key_ip_or_permissions",
            "exchange_error_code": "-2015",
            "error_type": "RuntimeError",
        }
        assert "Invalid API-key" not in repr(payload)
        assert "permissions for action" not in repr(payload)
        assert "server-key" not in repr(payload)
        assert "server-secret" not in repr(payload)
    finally:
        app.dependency_overrides.pop(require_operator_session, None)
