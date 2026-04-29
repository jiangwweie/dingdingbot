"""Unit tests for Runtime Events readmodel (GET /api/runtime/events)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.readmodels.runtime_events import RuntimeEventsReadModel


@pytest.fixture
def readmodel():
    return RuntimeEventsReadModel()


# ============================================================
# Source 1: Signals
# ============================================================


class TestSignalEvents:
    async def test_empty_signal_repo_returns_empty(self, readmodel):
        """No signal repo → no signal events."""
        result = await readmodel.build(signal_repo=None)
        assert result.events == []

    async def test_signal_repo_returns_empty_data(self, readmodel):
        """Signal repo with empty data → empty events."""
        repo = AsyncMock()
        repo.get_signals = AsyncMock(return_value={"data": []})
        result = await readmodel.build(signal_repo=repo)
        signal_events = [e for e in result.events if e.category == "SIGNAL"]
        assert signal_events == []

    async def test_signal_maps_to_event(self, readmodel):
        """A fired signal maps to a SIGNAL event with SUCCESS severity."""
        repo = AsyncMock()
        repo.get_signals = AsyncMock(return_value={
            "data": [
                {
                    "id": "sig_001",
                    "symbol": "ETH/USDT:USDT",
                    "timeframe": "1h",
                    "direction": "LONG",
                    "strategy_name": "Alpha_V2",
                    "score": 0.85,
                    "status": "FIRED",
                    "created_at": "2026-04-25T01:00:00Z",
                }
            ]
        })
        result = await readmodel.build(signal_repo=repo)
        signal_events = [e for e in result.events if e.category == "SIGNAL"]
        assert len(signal_events) == 1
        evt = signal_events[0]
        assert evt.id == "sig_sig_001"
        assert evt.category == "SIGNAL"
        assert evt.severity == "SUCCESS"
        assert "Alpha_V2" in evt.message
        assert "LONG" in evt.message
        assert "sig_001" in evt.related_entities

    async def test_signal_repo_exception_returns_empty(self, readmodel):
        """Signal repo raises exception → no signal events, no crash."""
        repo = AsyncMock()
        repo.get_signals = AsyncMock(side_effect=Exception("db error"))
        result = await readmodel.build(signal_repo=repo)
        signal_events = [e for e in result.events if e.category == "SIGNAL"]
        assert signal_events == []

    async def test_signal_missing_fields_no_crash(self, readmodel):
        """Signal with missing fields still produces an event."""
        repo = AsyncMock()
        repo.get_signals = AsyncMock(return_value={
            "data": [{"id": "sig_002"}]
        })
        result = await readmodel.build(signal_repo=repo)
        signal_events = [e for e in result.events if e.category == "SIGNAL"]
        assert len(signal_events) == 1
        assert signal_events[0].message  # has some message


# ============================================================
# Source 2: Order audit logs
# ============================================================


class TestAuditEvents:
    async def test_no_audit_logger_returns_empty(self, readmodel):
        """No audit logger → no execution events."""
        result = await readmodel.build(audit_logger=None)
        assert result.events == []

    async def test_audit_log_maps_to_execution_event(self, readmodel):
        """ORDER_FILLED audit log maps to EXECUTION/SUCCESS event."""
        logger = MagicMock()
        repo = AsyncMock()
        logger._repository = repo

        audit_log = SimpleNamespace(
            id="audit_001",
            order_id="ord_001",
            signal_id="sig_001",
            event_type="ORDER_FILLED",
            new_status="FILLED",
            created_at=int(datetime.now(timezone.utc).timestamp() * 1000),
        )
        repo.query = AsyncMock(return_value=[audit_log])

        result = await readmodel.build(audit_logger=logger)
        exec_events = [e for e in result.events if e.category == "EXECUTION"]
        assert len(exec_events) == 1
        evt = exec_events[0]
        assert evt.severity == "SUCCESS"
        assert "ord_001" in evt.message
        assert "ord_001" in evt.related_entities
        assert "sig_001" in evt.related_entities

    async def test_audit_rejected_maps_to_error(self, readmodel):
        """ORDER_REJECTED maps to EXECUTION/ERROR."""
        logger = MagicMock()
        repo = AsyncMock()
        logger._repository = repo

        audit_log = SimpleNamespace(
            id="audit_002",
            order_id="ord_002",
            signal_id=None,
            event_type="ORDER_REJECTED",
            new_status="REJECTED",
            created_at=int(datetime.now(timezone.utc).timestamp() * 1000),
        )
        repo.query = AsyncMock(return_value=[audit_log])

        result = await readmodel.build(audit_logger=logger)
        exec_events = [e for e in result.events if e.category == "EXECUTION"]
        assert len(exec_events) == 1
        assert exec_events[0].severity == "ERROR"

    async def test_audit_logger_exception_no_crash(self, readmodel):
        """Audit repo raises exception → no execution events, no crash."""
        logger = MagicMock()
        repo = AsyncMock()
        logger._repository = repo
        repo.query = AsyncMock(side_effect=Exception("pg error"))

        result = await readmodel.build(audit_logger=logger)
        exec_events = [e for e in result.events if e.category == "EXECUTION"]
        assert exec_events == []


# ============================================================
# Source 3: Startup reconciliation
# ============================================================


class TestStartupEvents:
    async def test_no_summary_returns_empty(self, readmodel):
        """No startup summary → no RECONCILIATION events."""
        result = await readmodel.build(startup_reconciliation_summary=None)
        recon_events = [e for e in result.events if e.category == "RECONCILIATION"]
        assert recon_events == []

    async def test_successful_reconciliation(self, readmodel):
        """Successful reconciliation → RECONCILIATION/SUCCESS."""
        summary = {
            "total_candidates": 5,
            "failure_count": 0,
            "duration_ms": 120,
        }
        result = await readmodel.build(startup_reconciliation_summary=summary)
        recon_events = [e for e in result.events if e.category == "RECONCILIATION"]
        assert len(recon_events) == 1
        assert recon_events[0].severity == "SUCCESS"

    async def test_failed_reconciliation(self, readmodel):
        """Failed reconciliation → RECONCILIATION/WARN."""
        summary = {
            "total_candidates": 5,
            "failure_count": 2,
            "duration_ms": 120,
        }
        result = await readmodel.build(startup_reconciliation_summary=summary)
        recon_events = [e for e in result.events if e.category == "RECONCILIATION"]
        assert len(recon_events) == 1
        assert recon_events[0].severity == "WARN"

    async def test_pg_recovery_events(self, readmodel):
        """PG recovery counts produce RECOVERY events."""
        summary = {
            "total_candidates": 5,
            "failure_count": 0,
            "duration_ms": 120,
            "pg_recovery_resolved_count": 3,
            "pg_recovery_retrying_count": 1,
            "pg_recovery_failed_count": 2,
        }
        result = await readmodel.build(startup_reconciliation_summary=summary)
        recovery_events = [e for e in result.events if e.category == "RECOVERY"]
        assert len(recovery_events) == 3
        severities = {e.severity for e in recovery_events}
        assert "SUCCESS" in severities
        assert "WARN" in severities
        assert "ERROR" in severities


# ============================================================
# Source 4: Breaker state
# ============================================================


class TestBreakerEvents:
    async def test_no_orchestrator_returns_empty(self, readmodel):
        """No orchestrator → no BREAKER events."""
        result = await readmodel.build(execution_orchestrator=None)
        breaker_events = [e for e in result.events if e.category == "BREAKER"]
        assert breaker_events == []

    async def test_tripped_breaker_produces_event(self, readmodel):
        """Tripped breaker symbol → BREAKER/ERROR event."""
        orchestrator = MagicMock()
        orchestrator.list_circuit_breaker_symbols = MagicMock(return_value=["ETH/USDT:USDT"])

        result = await readmodel.build(execution_orchestrator=orchestrator)
        breaker_events = [e for e in result.events if e.category == "BREAKER"]
        assert len(breaker_events) == 1
        assert breaker_events[0].severity == "ERROR"
        assert "ETH/USDT:USDT" in breaker_events[0].message

    async def test_no_tripped_breakers(self, readmodel):
        """No tripped breakers → no BREAKER events."""
        orchestrator = MagicMock()
        orchestrator.list_circuit_breaker_symbols = MagicMock(return_value=[])

        result = await readmodel.build(execution_orchestrator=orchestrator)
        breaker_events = [e for e in result.events if e.category == "BREAKER"]
        assert breaker_events == []


# ============================================================
# Source 5: Recovery tasks
# ============================================================


class TestRecoveryEvents:
    async def test_no_recovery_repo_returns_empty(self, readmodel):
        """No recovery repo → no RECOVERY events from this source."""
        result = await readmodel.build(execution_recovery_repo=None)
        recovery_from_repo = [e for e in result.events if e.id.startswith("recovery_")]
        assert recovery_from_repo == []

    async def test_pending_recovery_task(self, readmodel):
        """Pending recovery task → RECOVERY/WARN."""
        repo = AsyncMock()
        repo.list_blocking = AsyncMock(return_value=[
            {"id": "task_001", "symbol": "ETH/USDT:USDT", "status": "pending",
             "intent_id": "int_001", "error_message": "", "updated_at": None}
        ])

        result = await readmodel.build(execution_recovery_repo=repo)
        recovery_events = [e for e in result.events if e.id.startswith("recovery_")]
        assert len(recovery_events) == 1
        assert recovery_events[0].severity == "WARN"

    async def test_failed_recovery_task(self, readmodel):
        """Failed recovery task → RECOVERY/ERROR."""
        repo = AsyncMock()
        repo.list_blocking = AsyncMock(return_value=[
            {"id": "task_002", "symbol": "ETH/USDT:USDT", "status": "failed",
             "intent_id": "int_002", "error_message": "timeout",
             "updated_at": int(datetime.now(timezone.utc).timestamp() * 1000)}
        ])

        result = await readmodel.build(execution_recovery_repo=repo)
        recovery_events = [e for e in result.events if e.id.startswith("recovery_")]
        assert len(recovery_events) == 1
        assert recovery_events[0].severity == "ERROR"
        assert "timeout" in recovery_events[0].message

    async def test_recovery_repo_exception_no_crash(self, readmodel):
        """Recovery repo raises exception → no crash."""
        repo = AsyncMock()
        repo.list_blocking = AsyncMock(side_effect=Exception("pg error"))

        result = await readmodel.build(execution_recovery_repo=repo)
        recovery_from_repo = [e for e in result.events if e.id.startswith("recovery_")]
        assert recovery_from_repo == []


# ============================================================
# Cross-source: sorting, limit, empty state
# ============================================================


class TestCrossSource:
    async def test_all_sources_empty(self, readmodel):
        """All sources empty → empty events list."""
        result = await readmodel.build(
            signal_repo=None,
            audit_logger=None,
            startup_reconciliation_summary=None,
            execution_orchestrator=None,
            execution_recovery_repo=None,
        )
        assert result.events == []

    async def test_events_sorted_by_timestamp_desc(self, readmodel):
        """Events are sorted newest-first."""
        repo = AsyncMock()
        repo.get_signals = AsyncMock(return_value={
            "data": [
                {"id": "sig_old", "symbol": "ETH", "direction": "LONG",
                 "strategy_name": "A", "status": "FIRED",
                 "created_at": "2026-04-25T00:00:00Z"},
                {"id": "sig_new", "symbol": "ETH", "direction": "SHORT",
                 "strategy_name": "B", "status": "FIRED",
                 "created_at": "2026-04-25T01:00:00Z"},
            ]
        })
        result = await readmodel.build(signal_repo=repo)
        assert len(result.events) == 2
        # Newest first
        assert result.events[0].id == "sig_sig_new"
        assert result.events[1].id == "sig_sig_old"

    async def test_limit_applied(self, readmodel):
        """Limit truncates the result."""
        repo = AsyncMock()
        repo.get_signals = AsyncMock(return_value={
            "data": [
                {"id": f"sig_{i}", "symbol": "ETH", "direction": "LONG",
                 "strategy_name": "A", "status": "FIRED",
                 "created_at": f"2026-04-25T{i:02d}:00:00Z"}
                for i in range(10)
            ]
        })
        result = await readmodel.build(signal_repo=repo, limit=5)
        assert len(result.events) == 5

    async def test_category_and_severity_values_stable(self, readmodel):
        """All events have category and severity values within the expected enums."""
        repo = AsyncMock()
        repo.get_signals = AsyncMock(return_value={
            "data": [
                {"id": "sig_001", "symbol": "ETH", "direction": "LONG",
                 "strategy_name": "A", "status": "FIRED",
                 "created_at": "2026-04-25T01:00:00Z"},
            ]
        })
        logger = MagicMock()
        audit_repo = AsyncMock()
        logger._repository = audit_repo
        audit_repo.query = AsyncMock(return_value=[
            SimpleNamespace(
                id="audit_001", order_id="ord_001", signal_id=None,
                event_type="ORDER_FILLED", new_status="FILLED",
                created_at=int(datetime.now(timezone.utc).timestamp() * 1000),
            )
        ])

        valid_categories = {"STARTUP", "RECONCILIATION", "BREAKER", "RECOVERY",
                            "WARNING", "ERROR", "SIGNAL", "EXECUTION"}
        valid_severities = {"INFO", "WARN", "ERROR", "SUCCESS"}

        result = await readmodel.build(signal_repo=repo, audit_logger=logger)
        for evt in result.events:
            assert evt.category in valid_categories
            assert evt.severity in valid_severities


# ============================================================
# Route-level: endpoint exists and returns stable structure
# ============================================================


class TestRouteLevel:
    def test_events_endpoint_exists_on_router(self):
        """GET /api/runtime/events is registered on the runtime router."""
        from src.interfaces.api_console_runtime import router

        route_paths = [r.path for r in router.routes]
        assert "/api/runtime/events" in route_paths

    def test_events_endpoint_returns_empty_when_no_deps(self):
        """Endpoint returns { "events": [] } when all dependencies are None."""
        from fastapi.testclient import TestClient
        from src.interfaces.api_console_runtime import router
        import src.interfaces.api_console_runtime as route_mod

        original = route_mod._load_api_module

        fake_api = type("FakeApi", (), {
            "_signal_repo": None,
            "_audit_logger": None,
            "_execution_orchestrator": None,
            "_startup_reconciliation_summary": None,
            "_execution_recovery_repo": None,
        })()
        route_mod._load_api_module = lambda: fake_api

        try:
            from fastapi import FastAPI
            app = FastAPI()
            app.include_router(router)
            client = TestClient(app)

            response = client.get("/api/runtime/events")
            assert response.status_code == 200
            data = response.json()
            assert "events" in data
            assert isinstance(data["events"], list)
            assert len(data["events"]) == 0
        finally:
            route_mod._load_api_module = original

    def test_events_endpoint_calls_readmodel(self):
        """Endpoint delegates to RuntimeEventsReadModel and produces signal events."""
        from fastapi.testclient import TestClient
        from src.interfaces.api_console_runtime import router
        import src.interfaces.api_console_runtime as route_mod

        original_load = route_mod._load_api_module

        fake_repo = AsyncMock()
        fake_repo.get_signals = AsyncMock(return_value={
            "data": [
                {"id": "sig_test", "symbol": "ETH", "direction": "LONG",
                 "strategy_name": "Test", "status": "FIRED",
                 "created_at": "2026-04-25T01:00:00Z"},
            ]
        })
        fake_api = type("FakeApi", (), {
            "_signal_repo": fake_repo,
            "_audit_logger": None,
            "_execution_orchestrator": None,
            "_startup_reconciliation_summary": None,
            "_execution_recovery_repo": None,
        })()
        route_mod._load_api_module = lambda: fake_api

        try:
            from fastapi import FastAPI
            app = FastAPI()
            app.include_router(router)
            client = TestClient(app)

            response = client.get("/api/runtime/events")
            assert response.status_code == 200
            data = response.json()
            assert len(data["events"]) >= 1
            signal_events = [e for e in data["events"] if e["category"] == "SIGNAL"]
            assert len(signal_events) >= 1
            assert "Test" in signal_events[0]["message"]
        finally:
            route_mod._load_api_module = original_load