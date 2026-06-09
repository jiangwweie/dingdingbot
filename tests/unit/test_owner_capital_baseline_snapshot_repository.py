from __future__ import annotations

import time
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.domain.owner_capital_baseline_snapshot import (
    OwnerCapitalBaselineSnapshot,
    OwnerCapitalBaselineSnapshotSource,
)
from src.infrastructure.pg_models import PGOwnerCapitalBaselineSnapshotORM
from src.infrastructure.pg_owner_capital_baseline_snapshot_repository import (
    PgOwnerCapitalBaselineSnapshotRepository,
)
from src.interfaces.operator_auth import create_password_hash


NOW_MS = 1781000000000


@pytest_asyncio.fixture()
async def owner_capital_baseline_repo():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(PGOwnerCapitalBaselineSnapshotORM.__table__.create)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield PgOwnerCapitalBaselineSnapshotRepository(session_maker=session_maker)
    finally:
        await engine.dispose()


def _snapshot(snapshot_id: str = "capital-baseline-1") -> OwnerCapitalBaselineSnapshot:
    return OwnerCapitalBaselineSnapshot(
        snapshot_id=snapshot_id,
        currency="USDT",
        account_equity=Decimal("130"),
        capital_base=Decimal("100"),
        available_balance=Decimal("120"),
        unrealized_pnl=Decimal("-1.5"),
        source=OwnerCapitalBaselineSnapshotSource.OWNER_RECORDED,
        reason="Owner recorded review capital baseline after manual withdrawal.",
        occurred_at_ms=NOW_MS,
        recorded_by="owner",
        evidence_refs=["owner-note://capital-baseline-1"],
        metadata={"source": "unit-test"},
    )


@pytest.mark.asyncio
async def test_owner_capital_baseline_snapshot_repository_roundtrip(owner_capital_baseline_repo):
    saved = await owner_capital_baseline_repo.append(_snapshot())
    loaded = await owner_capital_baseline_repo.get("capital-baseline-1")
    listed = await owner_capital_baseline_repo.list(currency="USDT")

    assert saved.snapshot_id == "capital-baseline-1"
    assert loaded is not None
    assert loaded.account_equity == Decimal("130.000000000000000000")
    assert loaded.capital_base == Decimal("100.000000000000000000")
    assert loaded.available_balance == Decimal("120.000000000000000000")
    assert loaded.unrealized_pnl == Decimal("-1.500000000000000000")
    assert loaded.source == OwnerCapitalBaselineSnapshotSource.OWNER_RECORDED
    assert loaded.evidence_refs == ["owner-note://capital-baseline-1"]
    assert listed[0].snapshot_id == "capital-baseline-1"
    assert loaded.creates_withdrawal_instruction is False
    assert loaded.creates_transfer_instruction is False
    assert loaded.creates_order_instruction is False
    assert loaded.calls_exchange is False
    assert loaded.mutates_runtime_budget is False
    assert loaded.mutates_strategy_pnl is False
    assert loaded.creates_risk_event is False


def test_owner_capital_baseline_snapshot_rejects_execution_flags():
    payload = _snapshot().model_dump()
    payload["calls_exchange"] = True

    with pytest.raises(ValidationError):
        OwnerCapitalBaselineSnapshot(**payload)


class _FakeOwnerCapitalBaselineSnapshotRepo:
    def __init__(self) -> None:
        self.snapshots: list[OwnerCapitalBaselineSnapshot] = []
        self.initialized = False

    async def initialize(self) -> None:
        self.initialized = True

    async def append(
        self,
        snapshot: OwnerCapitalBaselineSnapshot,
    ) -> OwnerCapitalBaselineSnapshot:
        self.snapshots.append(snapshot)
        return snapshot

    async def list(self, *, currency=None, limit=50):
        items = [
            item for item in self.snapshots
            if currency is None or item.currency == currency
        ]
        return items[:limit]


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


def test_owner_capital_baseline_snapshot_api_records_no_action_fact(monkeypatch):
    _configure_auth(monkeypatch)
    fake_repo = _FakeOwnerCapitalBaselineSnapshotRepo()
    from src.interfaces import api as api_module
    from src.interfaces.api import app

    monkeypatch.setattr(
        api_module,
        "_owner_capital_baseline_snapshot_repo",
        fake_repo,
        raising=False,
    )

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        create_response = client.post(
            "/api/brc/owner-capital-baseline-snapshots",
            json={
                "snapshot_id": "api-baseline-1",
                "currency": "USDT",
                "account_equity": "130",
                "capital_base": "100",
                "available_balance": "120",
                "unrealized_pnl": "-1.5",
                "source": "owner_recorded",
                "reason": "Owner recorded baseline after manual withdrawal.",
                "occurred_at_ms": NOW_MS,
                "evidence_refs": ["owner-note://api-baseline-1"],
            },
        )
        list_response = client.get(
            "/api/brc/owner-capital-baseline-snapshots?currency=USDT"
        )

    assert create_response.status_code == 200
    payload = create_response.json()
    assert payload["snapshot"]["snapshot_id"] == "api-baseline-1"
    assert payload["snapshot"]["recorded_by"] == "owner"
    assert payload["snapshot"]["metadata"]["capital_base_review_fact_only"] is True
    assert payload["no_action_guarantee"]["creates_withdrawal_instruction"] is False
    assert payload["no_action_guarantee"]["creates_transfer_instruction"] is False
    assert payload["no_action_guarantee"]["creates_order_instruction"] is False
    assert payload["no_action_guarantee"]["calls_exchange"] is False
    assert payload["no_action_guarantee"]["mutates_runtime_budget"] is False
    assert payload["no_action_guarantee"]["mutates_strategy_pnl"] is False
    assert payload["no_action_guarantee"]["creates_risk_event"] is False
    assert list_response.status_code == 200
    assert list_response.json()["snapshots"][0]["snapshot_id"] == "api-baseline-1"
    assert fake_repo.initialized is True
