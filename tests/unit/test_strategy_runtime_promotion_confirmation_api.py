from __future__ import annotations

import time

from fastapi.testclient import TestClient

from src.interfaces.operator_auth import create_password_hash


NOW_MS = 1781000000000


def _configure_auth(monkeypatch):
    import src.interfaces.api  # noqa: F401

    monkeypatch.setenv("BRC_OPERATOR_USERNAME", "owner")
    monkeypatch.setenv("BRC_OPERATOR_PASSWORD_HASH", create_password_hash("pw"))
    monkeypatch.setenv("BRC_OPERATOR_TOTP_SECRET", "JBSWY3DPEHPK3PXP")
    monkeypatch.setenv("BRC_OPERATOR_SESSION_SECRET", "session-secret-for-unit-test")


def _totp() -> str:
    from src.interfaces.operator_auth import _hotp

    return _hotp("JBSWY3DPEHPK3PXP", int(time.time() // 30))


def _login(client: TestClient):
    return client.post(
        "/api/auth/login",
        json={"username": "owner", "password": "pw", "totp_code": _totp()},
    )


class _FakePromotionConfirmationRepo:
    def __init__(self) -> None:
        self.records = []

    async def initialize(self) -> None:
        return None

    async def append(self, record):
        self.records.append(record)
        return record

    async def list(
        self,
        *,
        runtime_instance_id=None,
        strategy_family_id=None,
        strategy_family_version_id=None,
        scope=None,
        limit=50,
    ):
        records = [
            record
            for record in self.records
            if (
                runtime_instance_id is None
                or record.runtime_instance_id == runtime_instance_id
            )
            and (
                strategy_family_id is None
                or record.strategy_family_id == strategy_family_id
            )
            and (
                strategy_family_version_id is None
                or record.strategy_family_version_id == strategy_family_version_id
            )
            and (scope is None or record.scope == scope)
        ]
        return list(reversed(records))[:limit]


def _semantic_confirmed() -> dict:
    return {
        "strategy_family_confirmed": True,
        "implementation_source_confirmed": True,
        "required_facts_confirmed": True,
        "entry_policy_confirmed": True,
        "exit_policy_confirmed": True,
        "protection_policy_confirmed": True,
        "eligible_for_runtime_execution_confirmed": True,
        "right_tail_review_metrics_confirmed": True,
    }


def _runtime_confirmed() -> dict:
    return {
        "runtime_profile_confirmed": True,
        "owner_confirmation_mode_confirmed": True,
        "symbol_side_boundary_confirmed": True,
        "max_loss_budget_confirmed": True,
        "max_notional_boundary_confirmed": True,
        "max_active_positions_boundary_confirmed": True,
        "max_leverage_boundary_confirmed": True,
        "margin_usage_boundary_confirmed": True,
        "liquidation_buffer_boundary_confirmed": True,
        "protection_readiness_source_confirmed": True,
        "stale_fact_behavior_confirmed": True,
        "attempt_consumption_rule_confirmed": True,
        "budget_reservation_rule_confirmed": True,
        "trusted_active_position_source_confirmed": True,
        "trusted_account_fact_source_confirmed": True,
    }


def test_promotion_confirmation_api_records_gate_snapshot_without_action(monkeypatch):
    _configure_auth(monkeypatch)
    repo = _FakePromotionConfirmationRepo()
    from src.interfaces import api_brc_console

    monkeypatch.setattr(
        api_brc_console,
        "_strategy_runtime_promotion_confirmation_repository",
        lambda: repo,
    )
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.post(
            "/api/brc/strategy-runtime-promotion-confirmations",
            json={
                "confirmation_id": "promotion-confirmation-api-1",
                "runtime_instance_id": "runtime-cpm-api-1",
                "strategy_family_id": "CPM-RO-001",
                "strategy_family_version_id": "CPM-RO-001-v0",
                "semantic_confirmations": _semantic_confirmed(),
                "runtime_confirmations": _runtime_confirmed(),
                "reason": "Owner confirms bounded 30U experimental capital semantics.",
                "evidence_refs": ["owner-note://promotion-confirmation-api-1"],
                "created_at_ms": NOW_MS,
                "metadata": {"source": "api-unit-test"},
            },
        )
        listed = client.get(
            "/api/brc/strategy-runtime-promotion-confirmations"
            "?runtime_instance_id=runtime-cpm-api-1"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["confirmation"]["confirmation_id"] == "promotion-confirmation-api-1"
    assert payload["confirmation"]["recorded_by"] == "owner"
    assert (
        payload["promotion_gate_result"]["status"]
        == "ready_for_controlled_runtime_execution_design"
    )
    assert payload["confirmation"]["not_execution_authority"] is True
    assert payload["confirmation"]["execution_intent_created"] is False
    assert payload["confirmation"]["order_created"] is False
    assert payload["confirmation"]["exchange_called"] is False
    assert payload["confirmation"]["owner_bounded_execution_called"] is False
    assert payload["confirmation"]["order_lifecycle_called"] is False
    assert payload["confirmation"]["runtime_mutation_created"] is False
    assert payload["no_action_guarantee"]["creates_order"] is False
    assert listed.status_code == 200
    assert listed.json()["confirmations"][0]["confirmation_id"] == (
        "promotion-confirmation-api-1"
    )


def test_promotion_confirmation_api_rejects_execution_metadata(monkeypatch):
    _configure_auth(monkeypatch)
    repo = _FakePromotionConfirmationRepo()
    from src.interfaces import api_brc_console

    monkeypatch.setattr(
        api_brc_console,
        "_strategy_runtime_promotion_confirmation_repository",
        lambda: repo,
    )
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.post(
            "/api/brc/strategy-runtime-promotion-confirmations",
            json={
                "confirmation_id": "promotion-confirmation-api-forbidden",
                "strategy_family_id": "CPM-RO-001",
                "strategy_family_version_id": "CPM-RO-001-v0",
                "semantic_confirmations": _semantic_confirmed(),
                "runtime_confirmations": _runtime_confirmed(),
                "reason": "Forbidden execution metadata must be rejected.",
                "created_at_ms": NOW_MS,
                "metadata": {"nested": {"exchange_order_id": "forbidden"}},
            },
        )

    assert response.status_code == 400
    assert "forbidden execution field" in response.json()["message"]
    assert repo.records == []
