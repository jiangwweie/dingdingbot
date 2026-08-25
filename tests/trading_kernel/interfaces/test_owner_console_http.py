from __future__ import annotations

from collections.abc import AsyncIterator
from importlib import import_module
from typing import Any, cast

import pyotp
import pytest
import pytest_asyncio
from argon2 import PasswordHasher
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.types import Message, Scope

from src.trading_kernel.application.owner_console.models import (
    CandleQuery,
    CandleSeries,
    CandleView,
    EffectiveEntryScopeFacts,
    EntryScopeFacts,
    EvidenceRef,
    Freshness,
    InstrumentCenterPage,
    InstrumentCenterQuery,
    OverviewEvidenceGap,
    OverviewFacts,
    ReviewCenterFacts,
    ReviewListQuery,
    SignalDetailFacts,
    SignalListQuery,
    SignalPageFacts,
    StrategyObservationPageFacts,
    StrategyObservationQuery,
    StrategyPageFacts,
    StrategySummaryQuery,
    StrategyTicketPageFacts,
    StrategyTicketQuery,
    TradeCausalityFacts,
    TradeListQuery,
    TradePageFacts,
)
from src.trading_kernel.infrastructure import pg_owner_read_repository
from src.trading_kernel.infrastructure.owner_market_data import OwnerMarketData
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from src.trading_kernel.interfaces.owner_console_http import app as app_module
from src.trading_kernel.interfaces.owner_console_http.app import (
    OwnerConsoleSettings,
    create_owner_console_app,
)
from src.trading_kernel.interfaces.owner_console_http.auth import OwnerAuthSettings

_FACTORIES = import_module("tests.trading_kernel.unit.owner_console.factories")
overview_facts = cast(Any, _FACTORIES.overview_facts)
signal_detail_facts = cast(Any, _FACTORIES.signal_detail_facts)
signal_item_facts = cast(Any, _FACTORIES.signal_item_facts)
trade_causality_facts = cast(Any, _FACTORIES.trade_causality_facts)
trade_item_facts = cast(Any, _FACTORIES.trade_item_facts)

PASSWORD = "correct horse"
TOTP_SEED = "JBSWY3DPEHPK3PXP"
BASE_MS = 1_800_000_000_000
PASSWORD_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=1,
    hash_len=32,
    salt_len=16,
)
PASSWORD_HASH = PASSWORD_HASHER.hash(PASSWORD)


class _StartupTransaction:
    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class _StartupConnection:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    async def execution_options(self, **_: object) -> _StartupConnection:
        return self

    async def begin(self) -> _StartupTransaction:
        return _StartupTransaction()

    async def execute(self, _: object) -> None:
        return None

    async def scalar(self, statement: object) -> str:
        return self._values[str(statement)]


class _ConnectionContext:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    async def __aenter__(self) -> _StartupConnection:
        return _StartupConnection(self._values)

    async def __aexit__(
        self,
        _type: object,
        _value: object,
        _traceback: object,
    ) -> None:
        return None


class _ReadOnlyEngine:
    def __init__(
        self,
        *,
        statement_timeout: str = "3s",
        schema_revision: str = CURRENT_SCHEMA_REVISION,
        dispose_error: BaseException | None = None,
    ) -> None:
        self.dispose_calls = 0
        self.transaction_count = 0
        self._dispose_error = dispose_error
        self._values = {
            "SHOW transaction_read_only": "on",
            "SHOW transaction_isolation": "repeatable read",
            "SHOW statement_timeout": statement_timeout,
            "SELECT version_num FROM alembic_version": schema_revision,
        }

    def connect(self) -> _ConnectionContext:
        self.transaction_count += 1
        return _ConnectionContext(self._values)

    async def dispose(self) -> None:
        self.dispose_calls += 1
        if self._dispose_error is not None:
            raise self._dispose_error


class _PublicMarketData:
    def __init__(self, *, close_error: BaseException | None = None) -> None:
        self.close_calls = 0
        self.requests: list[CandleQuery] = []
        self.read_error: Exception | None = None
        self._close_error = close_error

    async def close(self) -> None:
        self.close_calls += 1
        if self._close_error is not None:
            raise self._close_error

    async def read_candles(self, request: CandleQuery) -> CandleSeries:
        self.requests.append(request)
        if self.read_error is not None:
            raise self.read_error
        return CandleSeries(
            candles=(
                CandleView(
                    open_time_ms=request.closed_at_ms - 900_000,
                    close_time_ms=request.closed_at_ms,
                    open="100.00",
                    high="102.00",
                    low="99.00",
                    close="101.00",
                    volume="12.50",
                ),
            )
        )


class _RepositorySpy:
    def __init__(self) -> None:
        self.overview_requests: list[tuple[int, int]] = []
        self.signal_queries: list[SignalListQuery] = []
        self.signal_detail_ids: list[str] = []
        self.trade_queries: list[TradeListQuery] = []
        self.causality_ids: list[str] = []
        self.review_queries: list[ReviewListQuery] = []
        self.strategy_queries: list[StrategySummaryQuery] = []
        self.strategy_ticket_queries: list[StrategyTicketQuery] = []
        self.strategy_observation_queries: list[StrategyObservationQuery] = []
        self.instrument_queries: list[InstrumentCenterQuery] = []
        self.entry_scope_policy_ids: list[str] = []
        self.overview_facts_override: OverviewFacts | None = None

    async def read_overview_facts(
        self,
        day_start_ms: int,
        now_ms: int,
    ) -> OverviewFacts:
        self.overview_requests.append((day_start_ms, now_ms))
        if self.overview_facts_override is not None:
            return self.overview_facts_override
        return overview_facts(observed_at_ms=now_ms)

    async def read_signal_page_facts(
        self,
        query: SignalListQuery,
    ) -> SignalPageFacts:
        self.signal_queries.append(query)
        return SignalPageFacts(
            items=(signal_item_facts(),),
            requested_limit=query.limit,
        )

    async def read_signal_detail_facts(
        self,
        signal_event_id: str,
    ) -> SignalDetailFacts:
        self.signal_detail_ids.append(signal_event_id)
        return signal_detail_facts()

    async def read_trade_page_facts(
        self,
        query: TradeListQuery,
    ) -> TradePageFacts:
        self.trade_queries.append(query)
        return TradePageFacts(
            items=(trade_item_facts(),),
            requested_limit=query.limit,
        )

    async def read_trade_causality_facts(
        self,
        ticket_id: str,
    ) -> TradeCausalityFacts | None:
        self.causality_ids.append(ticket_id)
        return None if ticket_id == "ticket:missing" else trade_causality_facts()

    async def read_review_center_facts(
        self,
        query: ReviewListQuery,
    ) -> ReviewCenterFacts:
        self.review_queries.append(query)
        return ReviewCenterFacts(
            from_ms=query.from_ms,
            to_ms=query.to_ms,
            items=(),
            requested_limit=query.limit,
            requested_strategy_group_id=query.strategy_group_id,
        )

    async def read_strategy_page_facts(
        self,
        query: StrategySummaryQuery,
    ) -> StrategyPageFacts:
        self.strategy_queries.append(query)
        return StrategyPageFacts(
            from_ms=query.from_ms,
            to_ms=query.to_ms,
            view=query.view,
            versions=(),
        )

    async def read_strategy_ticket_page_facts(
        self,
        query: StrategyTicketQuery,
    ) -> StrategyTicketPageFacts:
        self.strategy_ticket_queries.append(query)
        return StrategyTicketPageFacts(items=(), requested_limit=query.limit)

    async def read_strategy_observation_page_facts(
        self,
        query: StrategyObservationQuery,
    ) -> StrategyObservationPageFacts:
        self.strategy_observation_queries.append(query)
        return StrategyObservationPageFacts(items=(), requested_limit=query.limit)

    async def read_instrument_center(
        self,
        query: InstrumentCenterQuery,
    ) -> InstrumentCenterPage:
        self.instrument_queries.append(query)
        return InstrumentCenterPage(
            items=(),
            universes=(),
            candidate_count=0,
            reference_count=0,
            unavailable_count=0,
            regular_session_count=0,
            source_watermark_ms=None,
        )

    async def read_effective_entry_scope_facts(
        self,
        owner_policy_id: str,
    ) -> EffectiveEntryScopeFacts:
        self.entry_scope_policy_ids.append(owner_policy_id)
        return EffectiveEntryScopeFacts(
            owner_policy_id=owner_policy_id,
            policy_version=12,
            policy_enabled=True,
            new_entry_submit_enabled=True,
            runtime_capability_enabled=True,
            max_concurrent_tickets=3,
            active_ticket_count=0,
            scopes=(
                EntryScopeFacts(
                    runtime_scope_id="scope:1",
                    strategy_group_id="SOR-US-EQ-PERP-001",
                    strategy_version_id="strategy-version:1",
                    event_spec_id="event-spec:1",
                    timeframe="15m",
                    exchange_instrument_id="binance-usdm:AAPLUSDT",
                    position_side="long",
                    lifecycle_state="active",
                    entry_enabled=True,
                    strategy_entry_state="enabled",
                    runtime_profile_status="active",
                    readiness_state="signal_absent",
                    readiness_first_blocker=None,
                    product_profile_status="active",
                    entry_session_policy="regular_only",
                    product_status="active",
                    session_state="regular",
                    product_valid_until_ms=BASE_MS + 60_000,
                    scope_updated_at_ms=BASE_MS - 1_000,
                    readiness_updated_at_ms=BASE_MS - 500,
                    product_observed_at_ms=BASE_MS - 200,
                ),
            ),
        )


@pytest.fixture
def repository_spy(monkeypatch: pytest.MonkeyPatch) -> _RepositorySpy:
    spy = _RepositorySpy()
    monkeypatch.setattr(
        pg_owner_read_repository,
        "PostgresOwnerReadRepository",
        lambda _connection: spy,
    )
    return spy


@pytest_asyncio.fixture
async def owner_console_app(
    repository_spy: _RepositorySpy,
    market_data_spy: _PublicMarketData,
) -> AsyncIterator[FastAPI]:
    del repository_spy
    engine = _ReadOnlyEngine()
    app = create_owner_console_app(
        OwnerConsoleSettings(
            database_dsn="postgresql+asyncpg://unused",
            account_id="owner-account",
            auth=OwnerAuthSettings(
                username="owner",
                password_hash=PASSWORD_HASH,
                totp_seed=TOTP_SEED,
                session_signing_key="test-signing-key-with-enough-random-looking-material",
            ),
        ),
        engine=cast(AsyncEngine, engine),
        market_data=cast(OwnerMarketData, market_data_spy),
        clock_ms=lambda: BASE_MS,
    )
    async with app.router.lifespan_context(app):
        engine.transaction_count = 0
        yield app


@pytest.fixture
def market_data_spy() -> _PublicMarketData:
    return _PublicMarketData()


@pytest_asyncio.fixture
async def owner_console_client(
    owner_console_app: FastAPI,
) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=owner_console_app),
        base_url="https://owner.example.test",
    ) as client:
        response = await client.post(
            "/api/owner/v1/auth/login",
            json={
                "username": "owner",
                "password": PASSWORD,
                "totp_code": pyotp.TOTP(TOTP_SEED).at(BASE_MS // 1_000),
            },
        )
        assert response.status_code == 204
        yield client


async def test_overview_uses_one_read_transaction_and_envelope(
    owner_console_client: AsyncClient,
    owner_console_app: FastAPI,
) -> None:
    response = await owner_console_client.get("/api/owner/v1/overview")

    assert response.status_code == 200
    assert response.json()["freshness"] in {"fresh", "stale"}
    assert (
        response.json()["data"]["account_snapshot"]["label"]
        == "Latest Admission Snapshot"
    )
    assert (
        response.json()["data"]["account_snapshot"]["wallet_balance"]["value"]
        == "100.00"
    )
    assert response.json()["snapshot_id"].startswith("snap:")
    assert response.json()["generated_at"] == "2027-01-15T08:00:00.000Z"
    assert response.json()["source_watermark"] == "2027-01-15T08:00:00.000Z"
    engine = cast(_ReadOnlyEngine, owner_console_app.state.owner_console_engine)
    assert engine.transaction_count == 1


async def test_effective_entry_scope_uses_one_read_transaction_and_never_claims_admission(
    owner_console_client: AsyncClient,
    owner_console_app: FastAPI,
    repository_spy: _RepositorySpy,
) -> None:
    response = await owner_console_client.get("/api/owner/v1/entry-scope")

    assert response.status_code == 200
    assert response.json()["data"]["can_issue_ticket_now"] is False
    assert response.json()["data"]["first_blocker"] == "signal_absent"
    assert repository_spy.entry_scope_policy_ids == ["policy-main"]
    engine = cast(_ReadOnlyEngine, owner_console_app.state.owner_console_engine)
    assert engine.transaction_count == 1


async def test_instrument_center_is_bounded_and_uses_one_read_snapshot(
    owner_console_client: AsyncClient,
    owner_console_app: FastAPI,
    repository_spy: _RepositorySpy,
) -> None:
    response = await owner_console_client.get(
        "/api/owner/v1/instruments",
        params={
            "product_family": "tradfi_equity_perpetual",
            "session_state": "regular",
            "limit": 20,
        },
    )

    assert response.status_code == 200
    assert response.json()["freshness"] == "unavailable"
    assert repository_spy.instrument_queries == [
        InstrumentCenterQuery(
            product_family="tradfi_equity_perpetual",
            session_state="regular",
            limit=20,
        )
    ]
    engine = cast(_ReadOnlyEngine, owner_console_app.state.owner_console_engine)
    assert engine.transaction_count == 1


async def test_overview_missing_rows_do_not_claim_generated_source_watermark(
    owner_console_client: AsyncClient,
    repository_spy: _RepositorySpy,
) -> None:
    repository_spy.overview_facts_override = overview_facts(
        runtime_freshness=Freshness.UNAVAILABLE,
        freshness_evidence_identity="owner_policy:configured",
        freshness_evidence_at_ms=BASE_MS,
        max_concurrent_tickets=None,
        active_ticket_count=None,
        active_ticket_ids=(),
        latest_capacity_claim_id=None,
        latest_wallet_balance_at_claim=None,
        latest_available_margin_at_claim=None,
        latest_claim_created_at_ms=None,
        monitor_statuses=(),
        monitor_keys=(),
        monitor_updated_at_ms=(),
        today_signal_count=0,
        admitted_signal_count=0,
        rejected_signal_count=0,
        execution_incident_count=None,
        evidence_gaps=(
            OverviewEvidenceGap(
                reason="configured_owner_authority_missing",
                evidence=EvidenceRef(
                    kind="event",
                    identity="owner_policy:configured",
                    occurred_at_ms=BASE_MS,
                ),
            ),
        ),
        evidence=(),
    )

    response = await owner_console_client.get("/api/owner/v1/overview")

    assert response.status_code == 200
    assert response.json()["freshness"] == "unavailable"
    assert response.json()["source_watermark"] is None


async def test_candles_do_not_open_database_transaction(
    owner_console_client: AsyncClient,
    owner_console_app: FastAPI,
) -> None:
    response = await owner_console_client.get(
        "/api/owner/v1/market/candles",
        params={
            "exchange_instrument_id": "binance-usdm:BTCUSDT:perpetual",
            "timeframe": "15m",
            "limit": 300,
            "closed_at_ms": BASE_MS,
        },
    )

    assert response.status_code == 200
    assert response.json()["source_watermark"] == "2027-01-15T08:00:00.000Z"
    engine = cast(_ReadOnlyEngine, owner_console_app.state.owner_console_engine)
    assert engine.transaction_count == 0


@pytest.mark.parametrize(
    "path",
    (
        "/api/owner/v1/signals",
        "/api/owner/v1/tickets",
        "/api/owner/v1/review",
        "/api/owner/v1/strategies/strategy-version:1/tickets",
        "/api/owner/v1/strategies/strategy-version:1/observations",
    ),
)
async def test_list_limit_above_hard_cap_returns_422(
    owner_console_client: AsyncClient,
    path: str,
) -> None:
    response = await owner_console_client.get(
        path,
        params={"limit": 101},
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "path",
    (
        "/api/owner/v1/entry-scope",
        "/api/owner/v1/signals",
        "/api/owner/v1/signals/signal:1",
        "/api/owner/v1/tickets",
        "/api/owner/v1/tickets/ticket:1/causality",
        "/api/owner/v1/review",
        "/api/owner/v1/strategies",
        "/api/owner/v1/strategies/strategy-version:1/tickets",
        "/api/owner/v1/strategies/strategy-version:1/observations",
    ),
)
async def test_each_postgres_data_route_uses_one_read_transaction(
    owner_console_client: AsyncClient,
    owner_console_app: FastAPI,
    path: str,
) -> None:
    response = await owner_console_client.get(path)

    assert response.status_code == 200
    engine = cast(_ReadOnlyEngine, owner_console_app.state.owner_console_engine)
    assert engine.transaction_count == 1


async def test_list_routes_use_clock_derived_default_windows(
    owner_console_client: AsyncClient,
    repository_spy: _RepositorySpy,
) -> None:
    responses = (
        await owner_console_client.get("/api/owner/v1/signals"),
        await owner_console_client.get("/api/owner/v1/tickets"),
        await owner_console_client.get("/api/owner/v1/review"),
        await owner_console_client.get("/api/owner/v1/strategies"),
    )

    assert [response.status_code for response in responses] == [200, 200, 200, 200]
    assert repository_spy.signal_queries == [
        SignalListQuery(from_ms=BASE_MS - 7 * 86_400_000, to_ms=BASE_MS)
    ]
    assert repository_spy.trade_queries == [
        TradeListQuery(from_ms=BASE_MS - 30 * 86_400_000, to_ms=BASE_MS)
    ]
    assert repository_spy.review_queries == [
        ReviewListQuery(from_ms=BASE_MS - 30 * 86_400_000, to_ms=BASE_MS)
    ]
    assert repository_spy.strategy_queries == [
        StrategySummaryQuery(from_ms=BASE_MS - 30 * 86_400_000, to_ms=BASE_MS)
    ]


async def test_shifted_window_is_bounded_to_ninety_days(
    owner_console_client: AsyncClient,
    owner_console_app: FastAPI,
) -> None:
    accepted = await owner_console_client.get(
        "/api/owner/v1/tickets",
        params={"from_ms": BASE_MS - 90 * 86_400_000, "to_ms": BASE_MS},
    )
    rejected = await owner_console_client.get(
        "/api/owner/v1/tickets",
        params={"from_ms": BASE_MS - 90 * 86_400_000 - 1, "to_ms": BASE_MS},
    )

    assert accepted.status_code == 200
    assert rejected.status_code == 422
    engine = cast(_ReadOnlyEngine, owner_console_app.state.owner_console_engine)
    assert engine.transaction_count == 1


async def test_candle_limit_defaults_to_300_and_caps_at_500(
    owner_console_client: AsyncClient,
    market_data_spy: _PublicMarketData,
) -> None:
    defaulted = await owner_console_client.get(
        "/api/owner/v1/market/candles",
        params={
            "exchange_instrument_id": "binance-usdm:BTCUSDT:perpetual",
            "timeframe": "15m",
            "closed_at_ms": BASE_MS,
        },
    )
    capped = await owner_console_client.get(
        "/api/owner/v1/market/candles",
        params={
            "exchange_instrument_id": "binance-usdm:BTCUSDT:perpetual",
            "timeframe": "15m",
            "limit": 501,
            "closed_at_ms": BASE_MS,
        },
    )

    assert defaulted.status_code == 200
    assert market_data_spy.requests[0].limit == 300
    assert capped.status_code == 422
    assert len(market_data_spy.requests) == 1


@pytest.mark.parametrize(
    "failure",
    (TimeoutError("market timeout"), ValueError("malformed response")),
)
async def test_market_failures_use_stable_502_shape(
    owner_console_client: AsyncClient,
    market_data_spy: _PublicMarketData,
    failure: Exception,
) -> None:
    market_data_spy.read_error = failure

    response = await owner_console_client.get(
        "/api/owner/v1/market/candles",
        params={
            "exchange_instrument_id": "binance-usdm:BTCUSDT:perpetual",
            "timeframe": "15m",
            "closed_at_ms": BASE_MS,
        },
    )

    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "code": "market_data_unavailable",
            "message": "Public market data is unavailable",
        }
    }


async def test_unexpected_market_dependency_failure_remains_visible(
    owner_console_client: AsyncClient,
    market_data_spy: _PublicMarketData,
) -> None:
    market_data_spy.read_error = RuntimeError("unexpected adapter regression")

    with pytest.raises(RuntimeError, match="unexpected adapter regression"):
        await owner_console_client.get(
            "/api/owner/v1/market/candles",
            params={
                "exchange_instrument_id": "binance-usdm:BTCUSDT:perpetual",
                "timeframe": "15m",
                "closed_at_ms": BASE_MS,
            },
        )


async def test_missing_ticket_causality_uses_stable_404_shape(
    owner_console_client: AsyncClient,
) -> None:
    response = await owner_console_client.get(
        "/api/owner/v1/tickets/ticket:missing/causality"
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Resource not found"}
    }


async def test_openapi_contains_health_read_and_approved_owner_control_routes(
    owner_console_app: FastAPI,
) -> None:
    paths = set(owner_console_app.openapi()["paths"])

    assert paths == {
        "/healthz",
        "/api/owner/v1/auth/login",
        "/api/owner/v1/auth/logout",
        "/api/owner/v1/auth/session",
        "/api/owner/v1/overview",
        "/api/owner/v1/entry-scope",
        "/api/owner/v1/signals",
        "/api/owner/v1/signals/{signal_event_id}",
        "/api/owner/v1/tickets",
        "/api/owner/v1/tickets/{ticket_id}/causality",
        "/api/owner/v1/review",
        "/api/owner/v1/strategies",
        "/api/owner/v1/strategies/{strategy_version_id}/observations",
        "/api/owner/v1/strategies/{strategy_version_id}/tickets",
        "/api/owner/v1/market/candles",
        "/api/owner/v1/controls",
        "/api/owner/v1/controls/strategies/{strategy_group_id}/pause",
        "/api/owner/v1/controls/strategies/{strategy_group_id}/resume",
        "/api/owner/v1/controls/strategies/{strategy_group_id}/selection/dynamic/activate",
        "/api/owner/v1/controls/entry/pause",
        "/api/owner/v1/controls/entry/resume",
        "/api/owner/v1/controls/exposure/flatten-all/preview",
        "/api/owner/v1/controls/exposure/flatten-all",
        "/api/owner/v1/control-operations/{authorization_id}",
        "/api/owner/v1/control-events",
        "/api/owner/v1/instruments",
        "/api/owner/v1/instruments/refresh",
        "/api/owner/v1/instruments/universes/preview",
        "/api/owner/v1/instruments/universes/apply",
    }
    assert not any(
        method in path_item
        for path_item in owner_console_app.openapi()["paths"].values()
        for method in ("put", "patch", "delete")
    )


async def test_login_sets_strict_secure_http_only_cookie(
    owner_console_app: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=owner_console_app),
        base_url="https://owner.example.test",
    ) as client:
        response = await client.post(
            "/api/owner/v1/auth/login",
            json={
                "username": "owner",
                "password": PASSWORD,
                "totp_code": pyotp.TOTP(TOTP_SEED).at(BASE_MS // 1_000),
            },
        )

    assert response.status_code == 204
    cookie = response.headers["set-cookie"]
    assert "brc_owner_session=" in cookie
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=strict" in cookie


async def test_unauthenticated_session_and_data_share_one_401_shape(
    owner_console_app: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=owner_console_app),
        base_url="https://owner.example.test",
    ) as client:
        session = await client.get("/api/owner/v1/auth/session")
        overview = await client.get("/api/owner/v1/overview")

    assert session.status_code == 401
    assert overview.status_code == 401
    assert session.json()["error"] == {
        "code": "unauthorized",
        "message": "Authentication required",
    }
    assert overview.json()["error"] == session.json()["error"]


async def test_session_and_logout_require_the_cookie_and_invalidate_it(
    owner_console_app: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=owner_console_app),
        base_url="https://owner.example.test",
    ) as client:
        login = await client.post(
            "/api/owner/v1/auth/login",
            json={
                "username": "owner",
                "password": PASSWORD,
                "totp_code": pyotp.TOTP(TOTP_SEED).at(BASE_MS // 1_000),
            },
        )
        session = await client.get("/api/owner/v1/auth/session")
        logout = await client.post("/api/owner/v1/auth/logout")
        expired = await client.get("/api/owner/v1/auth/session")

    assert login.status_code == 204
    assert session.status_code == 200
    assert session.json() == {"authenticated": True}
    assert logout.status_code == 204
    assert "Max-Age=0" in logout.headers["set-cookie"]
    assert expired.status_code == 401


async def test_healthz_is_available_only_on_the_unix_socket(
    owner_console_app: FastAPI,
) -> None:
    unix_status = await _asgi_status(
        owner_console_app,
        path="/healthz",
        server=("/tmp/brc-owner-console.sock", None),
    )
    tcp_status = await _asgi_status(
        owner_console_app,
        path="/healthz",
        server=("127.0.0.1", 8000),
    )

    assert unix_status == 200
    assert tcp_status == 404


async def test_lifespan_cleans_each_resource_when_startup_fails() -> None:
    engine = _ReadOnlyEngine(
        statement_timeout="1s",
        dispose_error=OSError("engine dispose failed"),
    )
    market_data = _PublicMarketData(close_error=OSError("market close failed"))
    app = create_owner_console_app(
        _settings(),
        engine=cast(AsyncEngine, engine),
        market_data=cast(OwnerMarketData, market_data),
    )

    with pytest.raises(RuntimeError, match="read transaction verification failed"):
        async with app.router.lifespan_context(app):
            pass

    assert engine.dispose_calls == 1
    assert market_data.close_calls == 1


async def test_lifespan_rejects_an_incompatible_owner_api_schema() -> None:
    engine = _ReadOnlyEngine(schema_revision="0003_portfolio_admission_observability")
    app = create_owner_console_app(
        _settings(),
        engine=cast(AsyncEngine, engine),
        market_data=cast(OwnerMarketData, _PublicMarketData()),
    )

    with pytest.raises(RuntimeError, match="schema revision differs"):
        async with app.router.lifespan_context(app):
            pass


async def test_lifespan_disposes_the_engine_when_market_construction_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _ReadOnlyEngine()

    def raise_market_construction(_: OwnerConsoleSettings) -> OwnerMarketData:
        raise RuntimeError("market construction failed")

    monkeypatch.setattr(
        app_module,
        "_build_owner_market_data",
        raise_market_construction,
    )
    app = create_owner_console_app(
        _settings(),
        engine=cast(AsyncEngine, engine),
    )

    with pytest.raises(RuntimeError, match="market construction failed"):
        async with app.router.lifespan_context(app):
            pass

    assert engine.dispose_calls == 1


async def test_market_construction_uses_explicit_console_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(market_timeout_seconds=7.5)
    captured: list[dict[str, object]] = []

    class PublicExchange:
        def close(self) -> None:
            return None

    def build_exchange(config: dict[str, object]) -> PublicExchange:
        captured.append(config)
        return PublicExchange()

    monkeypatch.setattr(app_module.ccxt_async, "binanceusdm", build_exchange)
    market_data = app_module._build_owner_market_data(settings)
    await market_data.close()

    assert captured == [
        {
            "enableRateLimit": True,
            "timeout": 7_500,
            "options": {
                "defaultType": "future",
                "adjustForTimeDifference": True,
            },
        }
    ]


async def _asgi_status(
    app: FastAPI,
    *,
    path: str,
    server: tuple[str, int | None],
) -> int:
    messages: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        messages.append(message)

    await app(
        cast(
            Scope,
            {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.3"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": path,
                "raw_path": path.encode("ascii"),
                "query_string": b"",
                "headers": [],
                "client": None,
                "server": server,
            },
        ),
        receive,
        send,
    )
    return next(
        cast(int, message["status"])
        for message in messages
        if message["type"] == "http.response.start"
    )


def _settings(**overrides: object) -> OwnerConsoleSettings:
    values: dict[str, object] = {
        "database_dsn": "postgresql+asyncpg://unused",
        "account_id": "owner-account",
        "auth": OwnerAuthSettings(
            username="owner",
            password_hash=PASSWORD_HASH,
            totp_seed=TOTP_SEED,
            session_signing_key="test-signing-key-with-enough-random-looking-material",
        ),
    }
    values.update(overrides)
    return OwnerConsoleSettings(**values)  # type: ignore[arg-type]
