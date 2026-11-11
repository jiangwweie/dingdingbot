"""Append-only diagnostics in the same transaction as the failed decision."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from src.trading_kernel.domain.operational_evidence import FailureDiagnostic
from src.trading_kernel.infrastructure.pg_models import failure_diagnostics


async def record_failure(connection, diagnostic: FailureDiagnostic) -> None:
    await connection.execute(insert(failure_diagnostics).values(
        diagnostic_id=diagnostic.identity(), **diagnostic.model_dump(mode='json')
    ).on_conflict_do_nothing(index_elements=[failure_diagnostics.c.diagnostic_id]))


class PostgresFailureDiagnostics:
    def __init__(self, connection):
        self.connection = connection

    async def record(self, diagnostic: FailureDiagnostic) -> None:
        await record_failure(self.connection, diagnostic)

    async def recent(self, subject_id: str, limit: int = 50):
        if not 1 <= limit <= 100:
            raise ValueError('diagnostic read exceeds bound')
        return (await self.connection.execute(sa.select(failure_diagnostics).where(
            failure_diagnostics.c.subject_id == subject_id).order_by(
            failure_diagnostics.c.occurred_at_ms.desc(),failure_diagnostics.c.diagnostic_id).limit(limit))).mappings().all()
