"""Tests for PostgreSQL timeout/hardening engine kwargs."""

from src.infrastructure import database


def test_pg_engine_kwargs_defaults(monkeypatch):
    monkeypatch.delenv("PG_COMMAND_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("PG_STATEMENT_TIMEOUT_MS", raising=False)
    monkeypatch.delenv("PG_LOCK_TIMEOUT_MS", raising=False)
    monkeypatch.delenv("PG_IDLE_TX_TIMEOUT_MS", raising=False)
    monkeypatch.delenv("PG_POOL_TIMEOUT_SECONDS", raising=False)

    kwargs = database._build_pg_engine_kwargs()

    assert kwargs["pool_pre_ping"] is True
    assert kwargs["pool_recycle"] == 1800
    assert kwargs["pool_timeout"] == 10
    assert kwargs["connect_args"]["command_timeout"] == 15
    assert kwargs["connect_args"]["server_settings"]["statement_timeout"] == "15000"
    assert kwargs["connect_args"]["server_settings"]["lock_timeout"] == "5000"
    assert kwargs["connect_args"]["server_settings"]["idle_in_transaction_session_timeout"] == "15000"


def test_pg_engine_kwargs_env_overrides(monkeypatch):
    monkeypatch.setenv("PG_COMMAND_TIMEOUT_SECONDS", "22")
    monkeypatch.setenv("PG_STATEMENT_TIMEOUT_MS", "25000")
    monkeypatch.setenv("PG_LOCK_TIMEOUT_MS", "7000")
    monkeypatch.setenv("PG_IDLE_TX_TIMEOUT_MS", "9000")
    monkeypatch.setenv("PG_POOL_TIMEOUT_SECONDS", "12")

    kwargs = database._build_pg_engine_kwargs()

    assert kwargs["pool_timeout"] == 12
    assert kwargs["connect_args"]["command_timeout"] == 22
    assert kwargs["connect_args"]["server_settings"]["statement_timeout"] == "25000"
    assert kwargs["connect_args"]["server_settings"]["lock_timeout"] == "7000"
    assert kwargs["connect_args"]["server_settings"]["idle_in_transaction_session_timeout"] == "9000"


def test_pg_engine_kwargs_invalid_env_falls_back(monkeypatch):
    monkeypatch.setenv("PG_COMMAND_TIMEOUT_SECONDS", "0")
    monkeypatch.setenv("PG_STATEMENT_TIMEOUT_MS", "-1")
    monkeypatch.setenv("PG_LOCK_TIMEOUT_MS", "abc")
    monkeypatch.setenv("PG_IDLE_TX_TIMEOUT_MS", "")
    monkeypatch.setenv("PG_POOL_TIMEOUT_SECONDS", "0")

    kwargs = database._build_pg_engine_kwargs()

    assert kwargs["pool_timeout"] == 10
    assert kwargs["connect_args"]["command_timeout"] == 15
    assert kwargs["connect_args"]["server_settings"]["statement_timeout"] == "15000"
    assert kwargs["connect_args"]["server_settings"]["lock_timeout"] == "5000"
    assert kwargs["connect_args"]["server_settings"]["idle_in_transaction_session_timeout"] == "15000"
