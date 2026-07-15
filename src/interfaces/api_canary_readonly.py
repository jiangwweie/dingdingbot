"""Dedicated loopback-only ASGI surface for read-only deployment canaries."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Literal, Protocol

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from src.infrastructure.canary_readonly_database import CanaryReadonlyDatabase


class LaneKey(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strategy_group_id: str = Field(min_length=1, max_length=160)
    symbol: str = Field(min_length=1, max_length=160)
    side: Literal["long", "short"]


class CandidatePageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_lane_keys: tuple[LaneKey, ...] = Field(min_length=1, max_length=256)
    after_runtime_instance_id: str | None = Field(default=None, max_length=220)
    limit: int = Field(default=16, ge=1, le=100)


class ObservationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["live_market"] = "live_market"
    include_exchange: Literal[False] = False
    allow_action_time_ticket_materialization: Literal[False] = False
    response_projection: Literal["watcher_compact"] = "watcher_compact"
    non_executing: Literal[True] = True
    timeout_seconds: float = Field(default=10.0, gt=0, le=60)


class ReadonlyPort(Protocol):
    async def candidate_page(self, request: CandidatePageRequest) -> dict[str, Any]: ...
    async def observation(self, runtime_instance_id: str) -> dict[str, Any]: ...


class SqlReadonlyPort:
    def __init__(self, database: CanaryReadonlyDatabase) -> None:
        self._database = database

    async def candidate_page(self, request: CandidatePageRequest) -> dict[str, Any]:
        predicates: list[str] = []
        params: dict[str, Any] = {"limit": request.limit + 1}
        for index, lane in enumerate(request.candidate_lane_keys):
            predicates.append(
                f"(strategy_family_id = :group_{index} AND "
                f"replace(replace(symbol, '/', ''), ':USDT', '') = :symbol_{index} "
                f"AND side = :side_{index})"
            )
            params[f"group_{index}"] = lane.strategy_group_id
            params[f"symbol_{index}"] = lane.symbol.replace("/", "").replace(":USDT", "")
            params[f"side_{index}"] = lane.side
        cursor = ""
        if request.after_runtime_instance_id:
            cursor = " AND runtime_instance_id > :cursor"
            params["cursor"] = request.after_runtime_instance_id
        statement = text(
            "SELECT runtime_instance_id, strategy_family_id, "
            "strategy_family_version_id, symbol, side, carrier_id, status "
            "FROM strategy_runtime_instances WHERE status = 'active' AND ("
            + " OR ".join(predicates)
            + ")"
            + cursor
            + " ORDER BY runtime_instance_id ASC LIMIT :limit"
        )
        async with self._database.connection() as conn:
            rows = (await conn.execute(statement, params)).mappings().all()
        has_more = len(rows) > request.limit
        items = [
            {
                "runtime_instance_id": str(row["runtime_instance_id"]),
                "strategy_group_id": str(row["strategy_family_id"]),
                "strategy_group_version_id": str(row["strategy_family_version_id"]),
                "symbol": str(row["symbol"]),
                "side": str(row["side"]),
                "carrier_id": row["carrier_id"],
                "status": "active",
            }
            for row in rows[: request.limit]
        ]
        return {
            "items": items,
            "next_cursor": items[-1]["runtime_instance_id"] if has_more else None,
            "has_more": has_more,
            "excluded_active_count": 0,
            "excluded_active_sample_ids": [],
        }

    async def observation(self, runtime_instance_id: str) -> dict[str, Any]:
        async with self._database.connection() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT runtime_instance_id, strategy_family_id, "
                        "strategy_family_version_id, symbol, side, status "
                        "FROM strategy_runtime_instances "
                        "WHERE runtime_instance_id = :runtime_id AND status = 'active'"
                    ),
                    {"runtime_id": runtime_instance_id},
                )
            ).mappings().one_or_none()
        if row is None:
            raise KeyError(runtime_instance_id)
        return {
            "response_projection": "watcher_compact",
            "scope": "deployment_canary_readonly_observation",
            "status": "waiting_for_signal",
            "runtime_instance_id": runtime_instance_id,
            "signal_artifact": None,
            "blockers": ["canary_does_not_materialize_signal"],
            "warnings": [],
            "safety_invariants": {
                "action_time_ticket_created": False,
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "attempt_counter_mutated": False,
                "runtime_budget_mutated": False,
                "withdrawal_or_transfer_created": False,
            },
        }


_database: CanaryReadonlyDatabase | None = None
_port: ReadonlyPort | None = None


async def get_readonly_port() -> ReadonlyPort:
    if _port is None:
        raise RuntimeError("canary_readonly_port_not_initialized")
    return _port


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    global _database, _port
    _database = CanaryReadonlyDatabase()
    await _database.verify_startup()
    _port = SqlReadonlyPort(_database)
    try:
        yield
    finally:
        _port = None
        await _database.close()
        _database = None


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.post("/api/trading-console/strategy-runtimes/watcher-active-candidate-page")
async def watcher_candidate_page(
    request: CandidatePageRequest,
    port: ReadonlyPort = Depends(get_readonly_port),
) -> dict[str, Any]:
    return await port.candidate_page(request)


@app.post(
    "/api/trading-console/strategy-runtimes/{runtime_instance_id}/next-attempt-observation-cycle"
)
async def next_attempt_observation_cycle(
    runtime_instance_id: str,
    request: ObservationRequest,
    port: ReadonlyPort = Depends(get_readonly_port),
) -> dict[str, Any]:
    try:
        return await port.observation(runtime_instance_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="runtime_not_found") from exc

