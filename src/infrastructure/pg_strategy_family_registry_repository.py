"""PG repository for metadata-only strategy family registry."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.strategy_family_registry import (
    StrategyFamilyMetadata,
    StrategyFamilyPlaybookMetadata,
    StrategyFamilyStatus,
    initial_strategy_family_registry_seed,
)
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import (
    PGBrcStrategyFamilyPlaybookORM,
    PGBrcStrategyFamilyRegistryORM,
)


class PgStrategyFamilyRegistryRepository:
    """Persistence for read-only strategy-family registry metadata."""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()
        self._uses_injected_session_maker = session_maker is not None

    async def initialize(self) -> None:
        if self._uses_injected_session_maker:
            return
        await init_pg_core_db()

    async def upsert_family_metadata(
        self,
        metadata: StrategyFamilyMetadata,
    ) -> StrategyFamilyMetadata:
        payload = metadata.model_dump(mode="json")
        async with self._session_maker() as session:
            async with session.begin():
                row = await session.get(
                    PGBrcStrategyFamilyRegistryORM,
                    (metadata.family_id, metadata.version_id),
                    with_for_update=True,
                )
                if row is None:
                    row = PGBrcStrategyFamilyRegistryORM(
                        family_id=metadata.family_id,
                        version_id=metadata.version_id,
                    )
                    session.add(row)
                self._apply_family_payload(row, payload)
                await session.flush()
                return self._to_family_metadata(row)

    async def upsert_playbook_metadata(
        self,
        metadata: StrategyFamilyPlaybookMetadata,
    ) -> StrategyFamilyPlaybookMetadata:
        payload = metadata.model_dump(mode="json")
        async with self._session_maker() as session:
            async with session.begin():
                row = await session.get(
                    PGBrcStrategyFamilyPlaybookORM,
                    metadata.playbook_id,
                    with_for_update=True,
                )
                if row is None:
                    row = PGBrcStrategyFamilyPlaybookORM(playbook_id=metadata.playbook_id)
                    session.add(row)
                self._apply_playbook_payload(row, payload)
                await session.flush()
                return self._to_playbook_metadata(row)

    async def upsert_initial_seed(self, *, now_ms: int) -> None:
        seed = initial_strategy_family_registry_seed(now_ms=now_ms)
        for family in seed.families:
            await self.upsert_family_metadata(family)
        for playbook in seed.playbooks:
            await self.upsert_playbook_metadata(playbook)

    async def get_family_metadata(self, family_id: str) -> Optional[StrategyFamilyMetadata]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(PGBrcStrategyFamilyRegistryORM)
                .where(PGBrcStrategyFamilyRegistryORM.family_id == family_id)
                .order_by(PGBrcStrategyFamilyRegistryORM.updated_at_ms.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            return self._to_family_metadata(row) if row is not None else None

    async def get_family_metadata_version(
        self,
        family_id: str,
        version_id: str,
    ) -> Optional[StrategyFamilyMetadata]:
        async with self._session_maker() as session:
            row = await session.get(PGBrcStrategyFamilyRegistryORM, (family_id, version_id))
            return self._to_family_metadata(row) if row is not None else None

    async def get_playbook_metadata(
        self,
        playbook_id: str,
    ) -> Optional[StrategyFamilyPlaybookMetadata]:
        async with self._session_maker() as session:
            row = await session.get(PGBrcStrategyFamilyPlaybookORM, playbook_id)
            return self._to_playbook_metadata(row) if row is not None else None

    async def list_active_observation_candidates(self) -> list[StrategyFamilyMetadata]:
        return await self._list_families_by_status(
            StrategyFamilyStatus.ACTIVE_OBSERVATION_CANDIDATE
        )

    async def list_registered_hypothesis_only_families(self) -> list[StrategyFamilyMetadata]:
        return await self._list_families_by_status(
            StrategyFamilyStatus.REGISTERED_HYPOTHESIS_ONLY
        )

    async def _list_families_by_status(
        self,
        status: StrategyFamilyStatus,
    ) -> list[StrategyFamilyMetadata]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(PGBrcStrategyFamilyRegistryORM)
                .where(PGBrcStrategyFamilyRegistryORM.status == status.value)
                .order_by(
                    PGBrcStrategyFamilyRegistryORM.updated_at_ms.desc(),
                    PGBrcStrategyFamilyRegistryORM.family_id.asc(),
                )
            )
            return [self._to_family_metadata(row) for row in result.scalars().all()]

    @staticmethod
    def _apply_family_payload(row: PGBrcStrategyFamilyRegistryORM, payload: dict) -> None:
        row.family_name = payload["family_name"]
        row.family_type = payload["family_type"]
        row.status = payload["status"]
        row.hypothesis = payload["hypothesis"]
        row.alpha_claim = payload["alpha_claim"]
        row.carrier_validation = payload["carrier_validation"]
        row.supported_symbols_json = list(payload["supported_symbols"])
        row.primary_timeframe = payload["primary_timeframe"]
        row.context_timeframes_json = list(payload["context_timeframes"])
        row.input_requirements_json = list(payload["input_requirements"])
        row.allowed_signal_types_json = list(payload["allowed_signal_types"])
        row.reason_code_taxonomy_json = dict(payload["reason_code_taxonomy"])
        row.review_metrics_json = list(payload["review_metrics"])
        row.known_failure_modes_json = list(payload["known_failure_modes"])
        row.evidence_requirements_json = list(payload["evidence_requirements"])
        row.notes = payload["notes"]
        row.created_at_ms = payload["created_at_ms"]
        row.updated_at_ms = payload["updated_at_ms"]

    @staticmethod
    def _apply_playbook_payload(row: PGBrcStrategyFamilyPlaybookORM, payload: dict) -> None:
        row.family_id = payload["family_id"]
        row.version_id = payload["version_id"]
        row.playbook_name = payload["playbook_name"]
        row.playbook_status = payload["playbook_status"]
        row.symbol_universe_json = list(payload["symbol_universe"])
        row.primary_timeframe = payload["primary_timeframe"]
        row.context_timeframes_json = list(payload["context_timeframes"])
        row.signal_contract_version = payload["signal_contract_version"]
        row.allowed_signal_types_json = list(payload["allowed_signal_types"])
        row.review_windows_json = list(payload["review_windows"])
        row.review_metrics_json = list(payload["review_metrics"])
        row.input_requirements_json = list(payload["input_requirements"])
        row.evidence_requirements_json = list(payload["evidence_requirements"])
        row.parameter_profile_json = dict(payload["parameter_profile"])
        row.notes = payload["notes"]
        row.created_at_ms = payload["created_at_ms"]
        row.updated_at_ms = payload["updated_at_ms"]

    @staticmethod
    def _to_family_metadata(row: PGBrcStrategyFamilyRegistryORM) -> StrategyFamilyMetadata:
        return StrategyFamilyMetadata(
            family_id=row.family_id,
            family_name=row.family_name,
            family_type=row.family_type,
            status=row.status,
            version_id=row.version_id,
            hypothesis=row.hypothesis,
            alpha_claim=row.alpha_claim,
            carrier_validation=row.carrier_validation,
            supported_symbols=list(row.supported_symbols_json or []),
            primary_timeframe=row.primary_timeframe,
            context_timeframes=list(row.context_timeframes_json or []),
            input_requirements=list(row.input_requirements_json or []),
            allowed_signal_types=list(row.allowed_signal_types_json or []),
            reason_code_taxonomy=dict(row.reason_code_taxonomy_json or {}),
            review_metrics=list(row.review_metrics_json or []),
            known_failure_modes=list(row.known_failure_modes_json or []),
            evidence_requirements=list(row.evidence_requirements_json or []),
            notes=row.notes,
            created_at_ms=row.created_at_ms,
            updated_at_ms=row.updated_at_ms,
        )

    @staticmethod
    def _to_playbook_metadata(row: PGBrcStrategyFamilyPlaybookORM) -> StrategyFamilyPlaybookMetadata:
        return StrategyFamilyPlaybookMetadata(
            playbook_id=row.playbook_id,
            family_id=row.family_id,
            version_id=row.version_id,
            playbook_name=row.playbook_name,
            playbook_status=row.playbook_status,
            symbol_universe=list(row.symbol_universe_json or []),
            primary_timeframe=row.primary_timeframe,
            context_timeframes=list(row.context_timeframes_json or []),
            signal_contract_version=row.signal_contract_version,
            allowed_signal_types=list(row.allowed_signal_types_json or []),
            review_windows=list(row.review_windows_json or []),
            review_metrics=list(row.review_metrics_json or []),
            input_requirements=list(row.input_requirements_json or []),
            evidence_requirements=list(row.evidence_requirements_json or []),
            parameter_profile=dict(row.parameter_profile_json or {}),
            notes=row.notes,
            created_at_ms=row.created_at_ms,
            updated_at_ms=row.updated_at_ms,
        )
