from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.interfaces import api as api_module
from src.interfaces import api_trading_console


class _IntentRepo:
    def __init__(self, value=None, *, error: Exception | None = None) -> None:
        self.value = value
        self.error = error

    async def get_by_order_candidate_id(self, order_candidate_id: str):
        if self.error is not None:
            raise self.error
        return self.value


class _AuthorizationRepo:
    def __init__(self, value=None) -> None:
        self.value = value

    async def get_by_order_candidate_id(self, order_candidate_id: str):
        return self.value


def _status(value: str):
    return SimpleNamespace(value=value)


@pytest.mark.asyncio
async def test_order_candidate_usage_reports_unused_candidate(monkeypatch):
    monkeypatch.setattr(
        api_module,
        "_trading_console_pg_execution_intent_repo",
        _IntentRepo(),
        raising=False,
    )
    monkeypatch.setattr(
        api_module,
        "_trading_console_pg_runtime_submit_authorization_repo",
        _AuthorizationRepo(),
        raising=False,
    )

    usage = await api_trading_console._order_candidate_usage("candidate-1")

    assert usage["candidate_usage_status"] == "unused"
    assert usage["candidate_reusable_for_new_attempt"] is True
    assert usage["reuse_blocker"] is None


@pytest.mark.asyncio
async def test_order_candidate_usage_blocks_candidate_with_recorded_intent(monkeypatch):
    monkeypatch.setattr(
        api_module,
        "_trading_console_pg_execution_intent_repo",
        _IntentRepo(
            SimpleNamespace(
                id="intent-1",
                status=_status("recorded"),
            )
        ),
        raising=False,
    )
    monkeypatch.setattr(
        api_module,
        "_trading_console_pg_runtime_submit_authorization_repo",
        _AuthorizationRepo(),
        raising=False,
    )

    usage = await api_trading_console._order_candidate_usage("candidate-1")

    assert usage["candidate_usage_status"] == "execution_intent_recorded"
    assert usage["execution_intent_id"] == "intent-1"
    assert usage["candidate_reusable_for_new_attempt"] is False
    assert usage["reuse_blocker"] == "order_candidate_already_has_execution_intent"


@pytest.mark.asyncio
async def test_order_candidate_usage_blocks_candidate_with_submit_authorization(monkeypatch):
    monkeypatch.setattr(
        api_module,
        "_trading_console_pg_execution_intent_repo",
        _IntentRepo(
            SimpleNamespace(
                id="intent-1",
                status=_status("recorded"),
            )
        ),
        raising=False,
    )
    monkeypatch.setattr(
        api_module,
        "_trading_console_pg_runtime_submit_authorization_repo",
        _AuthorizationRepo(
            SimpleNamespace(
                authorization_id="auth-1",
                execution_intent_id="intent-1",
                status=_status("approved_pending_controlled_submit"),
            )
        ),
        raising=False,
    )

    usage = await api_trading_console._order_candidate_usage("candidate-1")

    assert usage["candidate_usage_status"] == "submit_authorization_recorded"
    assert usage["submit_authorization_id"] == "auth-1"
    assert usage["candidate_reusable_for_new_attempt"] is False
    assert usage["reuse_blocker"] == "order_candidate_already_has_submit_authorization"


@pytest.mark.asyncio
async def test_order_candidate_usage_accepts_string_status_values(monkeypatch):
    monkeypatch.setattr(
        api_module,
        "_trading_console_pg_execution_intent_repo",
        _IntentRepo(
            SimpleNamespace(
                id="intent-1",
                status="recorded",
            )
        ),
        raising=False,
    )
    monkeypatch.setattr(
        api_module,
        "_trading_console_pg_runtime_submit_authorization_repo",
        _AuthorizationRepo(
            SimpleNamespace(
                authorization_id="auth-1",
                execution_intent_id="intent-1",
                status="approved_pending_controlled_submit",
            )
        ),
        raising=False,
    )

    usage = await api_trading_console._order_candidate_usage("candidate-1")

    assert usage["execution_intent_status"] == "recorded"
    assert (
        usage["submit_authorization_status"]
        == "approved_pending_controlled_submit"
    )


@pytest.mark.asyncio
async def test_order_candidate_usage_fails_closed_when_lookup_errors(monkeypatch):
    monkeypatch.setattr(
        api_module,
        "_trading_console_pg_execution_intent_repo",
        _IntentRepo(error=RuntimeError("db unavailable")),
        raising=False,
    )
    monkeypatch.setattr(
        api_module,
        "_trading_console_pg_runtime_submit_authorization_repo",
        _AuthorizationRepo(),
        raising=False,
    )

    usage = await api_trading_console._order_candidate_usage("candidate-1")

    assert usage["candidate_usage_status"] == "usage_lookup_unavailable"
    assert usage["candidate_reusable_for_new_attempt"] is False
    assert usage["reuse_blocker"] == "candidate_usage_lookup_failed:RuntimeError"
