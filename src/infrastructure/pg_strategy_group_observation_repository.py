"""PG repository for read-only strategy group observation evidence."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.application.strategy_group_live_readonly_observation import StrategyGroupObservationRecord
from src.infrastructure.database import get_pg_engine, get_pg_session_maker
from src.infrastructure.pg_models import PGBrcStrategyGroupObservationORM


class PgStrategyGroupObservationRepository:
    """Persist observe-only strategy-group signal records.

    This repository writes only observation/evidence metadata. It has no
    dependency on execution intents, orders, runtime start, or exchange writes.
    """

    sink_id = "pg_brc_strategy_group_observations"

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()
        self._uses_injected_session_maker = session_maker is not None

    async def initialize(self) -> None:
        if self._uses_injected_session_maker:
            return
        engine = get_pg_engine()
        async with engine.begin() as conn:
            await conn.run_sync(PGBrcStrategyGroupObservationORM.__table__.create, checkfirst=True)

    async def record(self, record: StrategyGroupObservationRecord) -> StrategyGroupObservationRecord:
        payload = record.model_dump(mode="json")
        async with self._session_maker() as session:
            async with session.begin():
                row = await session.get(
                    PGBrcStrategyGroupObservationORM,
                    record.record_id,
                    with_for_update=True,
                )
                if row is None:
                    row = PGBrcStrategyGroupObservationORM(observation_id=record.record_id)
                    session.add(row)
                self._apply_payload(row, payload)
                await session.flush()
                return self._to_record(row)

    async def get(self, observation_id: str) -> StrategyGroupObservationRecord | None:
        async with self._session_maker() as session:
            row = await session.get(PGBrcStrategyGroupObservationORM, observation_id)
            return self._to_record(row) if row is not None else None

    async def list_recent(self, *, limit: int = 50) -> list[StrategyGroupObservationRecord]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(PGBrcStrategyGroupObservationORM)
                .order_by(
                    PGBrcStrategyGroupObservationORM.observed_at_ms.desc(),
                    PGBrcStrategyGroupObservationORM.created_at_ms.desc(),
                )
                .limit(limit)
            )
            return [self._to_record(row) for row in result.scalars().all()]

    async def find_by_observation_identity(
        self,
        *,
        candidate_id: str,
        symbol: str,
        side: str,
        market_bar_timestamp_ms: int,
    ) -> StrategyGroupObservationRecord | None:
        """Return an existing observe-only row for the same closed-bar identity.

        The scheduled read-only runner uses this before writing so repeated cron
        invocations for the same latest closed bar do not create duplicate
        evidence rows. This identity intentionally excludes order/execution
        concepts.
        """
        async with self._session_maker() as session:
            result = await session.execute(
                select(PGBrcStrategyGroupObservationORM)
                .where(PGBrcStrategyGroupObservationORM.candidate_id == candidate_id)
                .where(PGBrcStrategyGroupObservationORM.symbol == symbol)
                .where(PGBrcStrategyGroupObservationORM.side == side)
                .where(PGBrcStrategyGroupObservationORM.market_bar_timestamp_ms == market_bar_timestamp_ms)
                .order_by(PGBrcStrategyGroupObservationORM.created_at_ms.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            return self._to_record(row) if row is not None else None

    async def list_current_by_candidate(
        self,
        *,
        candidate_ids: list[str],
    ) -> list[StrategyGroupObservationRecord]:
        if not candidate_ids:
            return []
        async with self._session_maker() as session:
            result = await session.execute(
                select(PGBrcStrategyGroupObservationORM)
                .where(PGBrcStrategyGroupObservationORM.candidate_id.in_(candidate_ids))
                .order_by(
                    PGBrcStrategyGroupObservationORM.candidate_id.asc(),
                    PGBrcStrategyGroupObservationORM.observed_at_ms.desc(),
                    PGBrcStrategyGroupObservationORM.created_at_ms.desc(),
                )
            )
            latest: dict[str, StrategyGroupObservationRecord] = {}
            for row in result.scalars().all():
                if row.candidate_id not in latest:
                    latest[row.candidate_id] = self._to_record(row)
            return [latest[candidate_id] for candidate_id in candidate_ids if candidate_id in latest]

    @staticmethod
    def _apply_payload(row: PGBrcStrategyGroupObservationORM, payload: dict) -> None:
        evidence_payload = dict(payload["evidence_payload"])
        if payload.get("runtime_signal_planning_readiness"):
            evidence_payload["_runtime_signal_planning_readiness"] = dict(
                payload["runtime_signal_planning_readiness"]
            )
        if payload.get("strategy_family_version_id"):
            evidence_payload["_strategy_family_version_id"] = payload[
                "strategy_family_version_id"
            ]
        row.observed_at_ms = payload["evaluated_at_ms"]
        row.strategy_group_id = payload["strategy_group_id"]
        row.candidate_id = payload["candidate_id"]
        row.symbol = payload["symbol"]
        row.side = payload["side"]
        row.signal_type = payload["signal_type"]
        row.confidence = Decimal(str(payload["confidence"]))
        row.reason_codes_json = list(payload["reason_codes"])
        row.evidence_payload_json = evidence_payload
        row.signal_snapshot_json = dict(payload["signal_snapshot"])
        row.invalidation_conditions_json = list(payload.get("invalidation_conditions") or [])
        row.human_summary = payload["human_summary"]
        row.source_type = payload["source_type"]
        row.market_source = payload["market_source"]
        row.market_bar_timestamp_ms = payload["market_bar_timestamp_ms"]
        row.market_bar_close = _optional_decimal(payload.get("market_bar_close"))
        row.review_windows_json = list(payload["review_windows"])
        row.review_status_json = dict(payload["review_status_by_window"])
        row.input_refs_json = dict(payload["input_refs"])
        row.not_order = payload["not_order"]
        row.not_execution_intent = payload["not_execution_intent"]
        row.no_execution_permission = payload["no_execution_permission"]
        row.no_order_permission = payload["no_order_permission"]
        row.no_runtime_start = payload["no_runtime_start"]
        row.created_at_ms = payload.get("recorded_at_ms") or payload["evaluated_at_ms"]

    @staticmethod
    def _to_record(row: PGBrcStrategyGroupObservationORM) -> StrategyGroupObservationRecord:
        evidence_payload = dict(row.evidence_payload_json or {})
        runtime_signal_planning_readiness = dict(
            evidence_payload.pop("_runtime_signal_planning_readiness", {}) or {}
        )
        strategy_family_version_id = evidence_payload.pop(
            "_strategy_family_version_id",
            None,
        )
        return StrategyGroupObservationRecord(
            record_id=row.observation_id,
            candidate_id=row.candidate_id,
            strategy_group_id=row.strategy_group_id,
            strategy_family_version_id=strategy_family_version_id,
            symbol=row.symbol,
            side=row.side,
            evaluated_at_ms=row.observed_at_ms,
            recorded_at_ms=row.created_at_ms,
            source="strategy_group_live_readonly_observation_v1",
            source_type=row.source_type,
            market_source=row.market_source,
            market_bar_timestamp_ms=row.market_bar_timestamp_ms,
            market_bar_close=str(row.market_bar_close) if row.market_bar_close is not None else None,
            signal_type=row.signal_type,
            confidence=str(row.confidence),
            reason_codes=list(row.reason_codes_json or []),
            human_summary=row.human_summary,
            evidence_payload=evidence_payload,
            signal_snapshot=dict(row.signal_snapshot_json or {}),
            invalidation_conditions=list(row.invalidation_conditions_json or []),
            review_windows=list(row.review_windows_json or []),
            review_status_by_window=dict(row.review_status_json or {}),
            input_refs=dict(row.input_refs_json or {}),
            runtime_signal_planning_readiness=runtime_signal_planning_readiness,
            sink_status="recorded_pg",
            not_order=True,
            not_execution_intent=True,
            no_execution_permission=True,
            no_order_permission=True,
            no_runtime_start=True,
        )


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))
