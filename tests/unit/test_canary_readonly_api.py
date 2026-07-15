from __future__ import annotations

import httpx
import inspect
import pytest

from src.interfaces import api_canary_readonly
from src.infrastructure import canary_readonly_database


class FakeReadonlyPort:
    def __init__(self) -> None:
        self.page_calls = 0
        self.observation_calls = 0

    async def candidate_page(self, request):
        self.page_calls += 1
        return {
            "items": [],
            "next_cursor": None,
            "has_more": False,
            "excluded_active_count": 0,
            "excluded_active_sample_ids": [],
        }

    async def observation(self, runtime_instance_id):
        self.observation_calls += 1
        return {
            "response_projection": "watcher_compact",
            "status": "waiting_for_signal",
            "runtime_instance_id": runtime_instance_id,
            "safety_invariants": {"exchange_write_called": False},
        }


def test_canary_route_table_is_exactly_two_post_routes():
    routes = {
        (route.path, tuple(sorted(route.methods or ())))
        for route in api_canary_readonly.app.routes
    }
    assert routes == {
        (
            "/api/trading-console/strategy-runtimes/watcher-active-candidate-page",
            ("POST",),
        ),
        (
            "/api/trading-console/strategy-runtimes/{runtime_instance_id}/next-attempt-observation-cycle",
            ("POST",),
        ),
    }


@pytest.mark.asyncio
async def test_canary_accepts_only_compact_non_executing_observation_shape():
    fake = FakeReadonlyPort()
    api_canary_readonly.app.dependency_overrides[
        api_canary_readonly.get_readonly_port
    ] = lambda: fake
    transport = httpx.ASGITransport(app=api_canary_readonly.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        accepted = await client.post(
            "/api/trading-console/strategy-runtimes/runtime-1/next-attempt-observation-cycle",
            json={
                "source": "live_market",
                "include_exchange": False,
                "allow_action_time_ticket_materialization": False,
                "response_projection": "watcher_compact",
                "non_executing": True,
            },
        )
        rejected = await client.post(
            "/api/trading-console/strategy-runtimes/runtime-1/next-attempt-observation-cycle",
            json={
                "source": "live_market",
                "include_exchange": True,
                "allow_action_time_ticket_materialization": False,
                "response_projection": "watcher_compact",
                "non_executing": True,
            },
        )
    api_canary_readonly.app.dependency_overrides.clear()

    assert accepted.status_code == 200
    assert rejected.status_code == 422
    assert fake.observation_calls == 1


@pytest.mark.asyncio
async def test_canary_candidate_page_rejects_unknown_fields_server_side():
    fake = FakeReadonlyPort()
    api_canary_readonly.app.dependency_overrides[
        api_canary_readonly.get_readonly_port
    ] = lambda: fake
    transport = httpx.ASGITransport(app=api_canary_readonly.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/trading-console/strategy-runtimes/watcher-active-candidate-page",
            json={
                "candidate_lane_keys": [
                    {
                        "strategy_group_id": "SG-1",
                        "symbol": "ETHUSDT",
                        "side": "long",
                    }
                ],
                "execute_submit": True,
            },
        )
    api_canary_readonly.app.dependency_overrides.clear()

    assert response.status_code == 422
    assert fake.page_calls == 0


def test_canary_database_has_no_global_engine_or_write_capability():
    source = inspect.getsource(api_canary_readonly)
    database_source = inspect.getsource(canary_readonly_database)
    assert "src.infrastructure.database" not in source
    assert "get_engine" not in database_source
    assert "RESET ROLE" not in database_source
    assert "SET TRANSACTION READ WRITE" not in database_source
    assert database_source.count("SET LOCAL ROLE pg_read_all_data") == 1
    assert "SET TRANSACTION READ ONLY" in database_source
