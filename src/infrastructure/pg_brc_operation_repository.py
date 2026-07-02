"""PG persistence for BRC Owner Console Operation Layer."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.application.brc_operation_layer import (
    ExecutionResult,
    OperationRecord,
    PreflightSnapshot,
)
from src.infrastructure.database import get_pg_session_maker
from src.infrastructure.pg_models import (
    PGBrcExecutionResultORM,
    PGBrcOperationORM,
    PGBrcPreflightSnapshotORM,
)


class PgBrcOperationRepository:
    """Append-friendly persistence for operation/preflight/result ledgers."""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        try:
            async with self._session_maker() as session:
                await session.execute(select(PGBrcOperationORM.operation_id).limit(1))
                await session.execute(select(PGBrcPreflightSnapshotORM.preflight_id).limit(1))
                await session.execute(select(PGBrcExecutionResultORM.operation_id).limit(1))
        except Exception as exc:
            raise RuntimeError(
                "BRC Operation Layer migration is not applied or the database is unavailable."
            ) from exc

    async def save_operation(self, operation: OperationRecord) -> OperationRecord:
        async with self._session_maker() as session:
            async with session.begin():
                row = await session.get(PGBrcOperationORM, operation.operation_id, with_for_update=True)
                if row is None:
                    row = PGBrcOperationORM(operation_id=operation.operation_id)
                    session.add(row)
                row.operation_type = operation.operation_type
                row.requested_by = operation.requested_by
                row.requested_at_ms = operation.requested_at_ms
                row.source_type = operation.source_type
                row.source_ref = operation.source_ref
                row.input_params_json = dict(operation.input_params)
                row.environment = operation.environment
                row.risk_level = operation.risk_level
                row.status = operation.status
                row.current_preflight_id = operation.current_preflight_id
                row.confirmed_by = operation.confirmed_by
                row.confirmed_at_ms = operation.confirmed_at_ms
                row.executed_at_ms = operation.executed_at_ms
                row.result_status = operation.result_status
                row.result_summary_json = dict(operation.result_summary)
                row.created_audit_refs_json = list(operation.created_audit_refs)
                await session.flush()
                return self._to_operation(row)

    async def get_operation(self, operation_id: str) -> Optional[OperationRecord]:
        async with self._session_maker() as session:
            row = await session.get(PGBrcOperationORM, operation_id)
            return self._to_operation(row) if row is not None else None

    async def list_operations(self, *, limit: int = 50) -> list[OperationRecord]:
        async with self._session_maker() as session:
            stmt = (
                select(PGBrcOperationORM)
                .order_by(PGBrcOperationORM.requested_at_ms.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            return [self._to_operation(row) for row in result.scalars().all()]

    async def save_preflight(self, preflight: PreflightSnapshot) -> PreflightSnapshot:
        async with self._session_maker() as session:
            async with session.begin():
                row = await session.get(PGBrcPreflightSnapshotORM, preflight.preflight_id)
                if row is None:
                    row = PGBrcPreflightSnapshotORM(preflight_id=preflight.preflight_id)
                    session.add(row)
                row.operation_id = preflight.operation_id
                row.operation_type = preflight.operation_type
                row.created_at_ms = preflight.created_at_ms
                row.expires_at_ms = preflight.expires_at_ms
                row.current_state_snapshot_json = dict(preflight.current_state_snapshot)
                row.target_state_json = dict(preflight.target_state)
                row.account_snapshot_json = dict(preflight.account_snapshot)
                row.order_snapshot_json = dict(preflight.order_snapshot)
                row.runtime_snapshot_json = dict(preflight.runtime_snapshot)
                row.campaign_snapshot_json = dict(preflight.campaign_snapshot)
                row.playbook_snapshot_json = dict(preflight.playbook_snapshot)
                row.risk_result_json = dict(preflight.risk_result)
                row.decision = preflight.decision
                row.warnings_json = list(preflight.warnings)
                row.blockers_json = list(preflight.blockers)
                row.confirmation_requirement_json = preflight.confirmation_requirement.model_dump(mode="json")
                row.snapshot_hash = preflight.snapshot_hash
                row.idempotency_key = preflight.idempotency_key
                row.summary = preflight.summary
                row.before_json = dict(preflight.before)
                row.after_json = dict(preflight.after)
                await session.flush()
                return self._to_preflight(row)

    async def get_preflight(self, preflight_id: str) -> Optional[PreflightSnapshot]:
        async with self._session_maker() as session:
            row = await session.get(PGBrcPreflightSnapshotORM, preflight_id)
            return self._to_preflight(row) if row is not None else None

    async def save_execution_result(self, result: ExecutionResult) -> ExecutionResult:
        async with self._session_maker() as session:
            async with session.begin():
                row = await session.get(
                    PGBrcExecutionResultORM,
                    result.operation_id,
                    with_for_update=True,
                )
                if row is None:
                    row = PGBrcExecutionResultORM(operation_id=result.operation_id)
                    session.add(row)
                row.preflight_id = result.preflight_id
                row.status = result.status
                row.rechecked = result.rechecked
                row.recheck_result_json = dict(result.recheck_result)
                row.adapter_result_json = dict(result.adapter_result)
                row.blocked_reason = result.blocked_reason
                row.failed_reason = result.failed_reason
                row.result_summary_json = dict(result.result_summary)
                row.audit_refs_json = list(result.audit_refs)
                row.campaign_refs_json = list(result.campaign_refs)
                row.review_refs_json = list(result.review_refs)
                row.final_state_snapshot_json = dict(result.final_state_snapshot)
                row.occurred_at_ms = result.occurred_at_ms
                await session.flush()
                return self._to_result(row)

    async def get_execution_result(self, operation_id: str) -> Optional[ExecutionResult]:
        async with self._session_maker() as session:
            row = await session.get(PGBrcExecutionResultORM, operation_id)
            return self._to_result(row) if row is not None else None

    @staticmethod
    def _to_operation(row: PGBrcOperationORM) -> OperationRecord:
        return OperationRecord(
            operation_id=row.operation_id,
            operation_type=row.operation_type,
            requested_by=row.requested_by,
            requested_at_ms=row.requested_at_ms,
            source_type=row.source_type,
            source_ref=row.source_ref,
            input_params=dict(row.input_params_json or {}),
            environment=row.environment,
            risk_level=row.risk_level,
            status=row.status,
            current_preflight_id=row.current_preflight_id,
            confirmed_by=row.confirmed_by,
            confirmed_at_ms=row.confirmed_at_ms,
            executed_at_ms=row.executed_at_ms,
            result_status=row.result_status,
            result_summary=dict(row.result_summary_json or {}),
            created_audit_refs=list(row.created_audit_refs_json or []),
        )

    @staticmethod
    def _to_preflight(row: PGBrcPreflightSnapshotORM) -> PreflightSnapshot:
        return PreflightSnapshot(
            preflight_id=row.preflight_id,
            operation_id=row.operation_id,
            operation_type=row.operation_type,
            created_at_ms=row.created_at_ms,
            expires_at_ms=row.expires_at_ms,
            current_state_snapshot=dict(row.current_state_snapshot_json or {}),
            target_state=dict(row.target_state_json or {}),
            account_snapshot=dict(row.account_snapshot_json or {}),
            order_snapshot=dict(row.order_snapshot_json or {}),
            runtime_snapshot=dict(row.runtime_snapshot_json or {}),
            campaign_snapshot=dict(row.campaign_snapshot_json or {}),
            playbook_snapshot=dict(row.playbook_snapshot_json or {}),
            risk_result=dict(row.risk_result_json or {}),
            decision=row.decision,
            warnings=list(row.warnings_json or []),
            blockers=list(row.blockers_json or []),
            confirmation_requirement=dict(row.confirmation_requirement_json or {}),
            snapshot_hash=row.snapshot_hash,
            idempotency_key=row.idempotency_key,
            summary=row.summary,
            before=dict(row.before_json or {}),
            after=dict(row.after_json or {}),
        )

    @staticmethod
    def _to_result(row: PGBrcExecutionResultORM) -> ExecutionResult:
        return ExecutionResult(
            operation_id=row.operation_id,
            preflight_id=row.preflight_id,
            status=row.status,
            rechecked=row.rechecked,
            recheck_result=dict(row.recheck_result_json or {}),
            adapter_result=dict(row.adapter_result_json or {}),
            blocked_reason=row.blocked_reason,
            failed_reason=row.failed_reason,
            result_summary=dict(row.result_summary_json or {}),
            audit_refs=list(row.audit_refs_json or []),
            campaign_refs=list(row.campaign_refs_json or []),
            review_refs=list(row.review_refs_json or []),
            final_state_snapshot=dict(row.final_state_snapshot_json or {}),
            occurred_at_ms=row.occurred_at_ms,
        )
