from __future__ import annotations

import time

from fastapi.testclient import TestClient

from src.interfaces.operator_auth import create_password_hash


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


class _FakeLiveLifecycleReviewRepo:
    def __init__(self) -> None:
        self.records = []

    async def initialize(self) -> None:
        return None

    async def append(self, record):
        self.records.append(record)
        return record

    async def get_latest(self, *, authorization_id=None, symbol=None):
        for record in reversed(self.records):
            if authorization_id is not None and record.authorization_id != authorization_id:
                continue
            if symbol is not None and record.symbol != symbol:
                continue
            return record
        return None

    async def list(self, *, authorization_id=None, symbol=None, limit=50):
        records = [
            item for item in self.records
            if (authorization_id is None or item.authorization_id == authorization_id)
            and (symbol is None or item.symbol == symbol)
        ]
        return list(reversed(records))[:limit]


def test_live_lifecycle_pending_open_review_endpoint_records_no_action_ledger(monkeypatch):
    _configure_auth(monkeypatch)
    repo = _FakeLiveLifecycleReviewRepo()
    from src.interfaces import api_brc_console

    monkeypatch.setattr(api_brc_console, "_live_lifecycle_review_repository", lambda: repo)
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.post(
            "/api/brc/live-lifecycle-reviews/pending-open",
            json={
                "authorization_id": "auth-1",
                "carrier_id": "MR-001-live-readonly-v0",
                "strategy_family_id": "MR-001",
                "strategy_family_version_id": "MR-001-v0",
                "runtime_instance_id": "runtime-1",
                "trial_binding_id": "trial-binding-1",
                "signal_evaluation_id": "signal-evaluation-1",
                "order_candidate_id": "order-candidate-1",
                "symbol": "ETH/USDT:USDT",
                "side": "long",
                "quantity": "0.014",
                "max_notional": "25",
                "leverage": "1",
                "max_attempts": 1,
                "final_gate_result": "passed",
                "protection_status": "matched_tp_sl",
                "entry_order_id": "entry-1",
                "entry_exchange_order_id": "exchange-entry-1",
                "tp_order_ids": ["tp-1"],
                "tp_exchange_order_ids": ["exchange-tp-1"],
                "sl_order_id": "sl-1",
                "sl_exchange_order_id": "exchange-sl-1",
                "owner_risk_acceptance": "owner_accepted_l3_bounded_live",
                "evidence_refs": ["/tmp/evidence.json"],
            },
        )
        latest = client.get(
            "/api/brc/live-lifecycle-reviews/latest?authorization_id=auth-1"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["review"]["review_status"] == "pending_open"
    assert payload["review"]["lifecycle_status"] == "protected_open"
    assert payload["review"]["strategy_family_version_id"] == "MR-001-v0"
    assert payload["review"]["runtime_instance_id"] == "runtime-1"
    assert payload["review"]["trial_binding_id"] == "trial-binding-1"
    assert payload["review"]["signal_evaluation_id"] == "signal-evaluation-1"
    assert payload["review"]["order_candidate_id"] == "order-candidate-1"
    assert payload["review"]["places_order"] is False
    assert payload["review"]["mutates_exchange"] is False
    assert payload["no_action_guarantee"]["places_order"] is False
    assert latest.status_code == 200
    assert latest.json()["review"]["review_id"] == "live-review-auth-1-pending-open"


def test_live_lifecycle_closed_reviewed_endpoint_records_terminal_review(monkeypatch):
    _configure_auth(monkeypatch)
    repo = _FakeLiveLifecycleReviewRepo()
    from src.interfaces import api_brc_console

    monkeypatch.setattr(api_brc_console, "_live_lifecycle_review_repository", lambda: repo)
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.post(
            "/api/brc/live-lifecycle-reviews/closed-reviewed",
            json={
                "authorization_id": "auth-closed",
                "carrier_id": "MR-001-live-readonly-v0",
                "strategy_family_id": "MR-001",
                "strategy_family_version_id": "MR-001-v0",
                "runtime_instance_id": "runtime-closed",
                "trial_binding_id": "trial-binding-closed",
                "signal_evaluation_id": "signal-evaluation-closed",
                "order_candidate_id": "order-candidate-closed",
                "symbol": "ETH/USDT:USDT",
                "side": "long",
                "quantity": "0.014",
                "max_notional": "25",
                "leverage": "1",
                "max_attempts": 1,
                "final_gate_result": "passed",
                "protection_status": "tp_filled_sibling_sl_canceled",
                "entry_order_id": "entry-closed",
                "entry_exchange_order_id": "exchange-entry-closed",
                "tp_order_ids": ["tp-closed"],
                "tp_exchange_order_ids": ["exchange-tp-closed"],
                "sl_order_id": "sl-canceled",
                "sl_exchange_order_id": "exchange-sl-canceled",
                "owner_risk_acceptance": "owner_accepted_l3_bounded_live",
                "review_decision": "park",
                "strategy_outcome": "closed_reviewed",
                "close_reason": "take_profit_filled",
                "cleanup_evidence_ref": "/tmp/cleanup.json",
                "evidence_refs": ["/tmp/cleanup.json"],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["review"]["review_status"] == "closed_reviewed"
    assert payload["review"]["lifecycle_status"] == "closed_reviewed"
    assert payload["review"]["strategy_family_version_id"] == "MR-001-v0"
    assert payload["review"]["runtime_instance_id"] == "runtime-closed"
    assert payload["review"]["trial_binding_id"] == "trial-binding-closed"
    assert payload["review"]["signal_evaluation_id"] == "signal-evaluation-closed"
    assert payload["review"]["order_candidate_id"] == "order-candidate-closed"
    assert payload["review"]["metadata"]["review_decision"] == "park"
    assert payload["review"]["metadata"]["cleanup_evidence_ref"] == "/tmp/cleanup.json"
    assert payload["review"]["places_order"] is False
    assert payload["review"]["mutates_exchange"] is False
