"""Bounded PostgreSQL facts and immutable admission/send evidence for BTC MA50."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from src.trading_kernel.domain.entry_regime import (
    BTC_REGIME_INSTRUMENT,
    FOUR_HOURS_MS,
    BtcMa50Snapshot,
    EntryRegimeControl,
    EntryRegimeEvidence,
    evaluate_btc_ma50,
)
from src.trading_kernel.infrastructure.pg_models import (
    btc_ma50_current,
    entry_regime_current,
    entry_regime_evidence,
    entry_regime_revisions,
)


class PostgresEntryRegimeRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def try_begin_refresh(self, *, now_ms: int, retry_interval_ms: int) -> bool:
        if retry_interval_ms <= 0:
            raise ValueError("BTC refresh retry interval must be positive")
        statement = (
            pg_insert(btc_ma50_current)
            .values(
                exchange_instrument_id=BTC_REGIME_INSTRUMENT,
                latest_close_ms=0,
                snapshot=None,
                retry_not_before_ms=now_ms + retry_interval_ms,
            )
            .on_conflict_do_update(
                index_elements=[btc_ma50_current.c.exchange_instrument_id],
                set_={"retry_not_before_ms": now_ms + retry_interval_ms},
                where=sa.and_(
                    btc_ma50_current.c.retry_not_before_ms <= now_ms,
                    btc_ma50_current.c.latest_close_ms
                    < now_ms // FOUR_HOURS_MS * FOUR_HOURS_MS,
                ),
            )
            .returning(btc_ma50_current.c.exchange_instrument_id)
        )
        return (await self._connection.scalar(statement)) is not None

    async def get_control(
        self, event_spec_id: str, *, lock: bool = False
    ) -> EntryRegimeControl | None:
        query = (
            sa.select(entry_regime_revisions)
            .join(
                entry_regime_current,
                sa.and_(
                    entry_regime_revisions.c.event_spec_id
                    == entry_regime_current.c.event_spec_id,
                    entry_regime_revisions.c.revision
                    == entry_regime_current.c.revision,
                ),
            )
            .where(entry_regime_current.c.event_spec_id == event_spec_id)
        )
        if lock:
            query = query.with_for_update(read=True, of=entry_regime_current)
        row = (await self._connection.execute(query)).mappings().one_or_none()
        return None if row is None else EntryRegimeControl.model_validate(dict(row))

    async def any_enabled(self) -> bool:
        return bool(
            await self._connection.scalar(
                sa.select(
                    sa.exists().where(
                        entry_regime_revisions.c.event_spec_id
                        == entry_regime_current.c.event_spec_id,
                        entry_regime_revisions.c.revision
                        == entry_regime_current.c.revision,
                        entry_regime_revisions.c.enabled.is_(True),
                    )
                )
            )
        )

    async def snapshot(self) -> BtcMa50Snapshot | None:
        data = await self._connection.scalar(
            sa.select(btc_ma50_current.c.snapshot).where(
                btc_ma50_current.c.exchange_instrument_id == BTC_REGIME_INSTRUMENT
            )
        )
        return None if data is None else BtcMa50Snapshot.model_validate(data)

    async def save_snapshot(self, snapshot: BtcMa50Snapshot) -> None:
        await self._connection.execute(
            pg_insert(btc_ma50_current)
            .values(
                exchange_instrument_id=BTC_REGIME_INSTRUMENT,
                latest_close_ms=snapshot.latest_close_ms,
                snapshot=snapshot.model_dump(mode="json"),
                retry_not_before_ms=0,
            )
            .on_conflict_do_update(
                index_elements=[btc_ma50_current.c.exchange_instrument_id],
                set_={
                    "latest_close_ms": snapshot.latest_close_ms,
                    "snapshot": snapshot.model_dump(mode="json"),
                    "retry_not_before_ms": 0,
                },
                where=btc_ma50_current.c.latest_close_ms < snapshot.latest_close_ms,
            )
        )

    async def evaluate(self, event_spec_id: str, *, now_ms: int) -> EntryRegimeEvidence:
        control = await self.get_control(event_spec_id, lock=True)
        snapshot = (
            await self.snapshot() if control is not None and control.enabled else None
        )
        result = (
            "entry_regime_control_missing"
            if control is None
            else evaluate_btc_ma50(snapshot, now_ms=now_ms)
            if control.enabled
            else "disabled"
        )
        return EntryRegimeEvidence(
            event_spec_id=event_spec_id,
            control=control,
            snapshot=snapshot,
            result=result,
            evaluated_at_ms=now_ms,
        )

    async def record(
        self,
        *,
        phase: str,
        identity_key: str,
        ticket_id: str | None,
        evidence: EntryRegimeEvidence,
    ) -> None:
        values = {
            "phase": phase,
            "identity_key": identity_key,
            "ticket_id": ticket_id,
            "evidence": evidence.model_dump(mode="json"),
        }
        await self._connection.execute(
            pg_insert(entry_regime_evidence).values(**values).on_conflict_do_nothing()
        )
        row = (
            (
                await self._connection.execute(
                    sa.select(entry_regime_evidence).where(
                        entry_regime_evidence.c.phase == phase,
                        entry_regime_evidence.c.identity_key == identity_key,
                    )
                )
            )
            .mappings()
            .one()
        )
        if dict(row) != values:
            raise ValueError("regime evidence identity conflict")

    async def lock_controls(self, event_spec_ids: tuple[str, ...]) -> None:
        if event_spec_ids:
            await self._connection.execute(
                sa.select(entry_regime_current)
                .where(entry_regime_current.c.event_spec_id.in_(event_spec_ids))
                .order_by(entry_regime_current.c.event_spec_id)
                .with_for_update()
            )

    async def switch(
        self,
        *,
        event_spec_id: str,
        expected_revision: int,
        enabled: bool,
        authorization_id: str,
        now_ms: int,
    ) -> EntryRegimeControl:
        current = await self.get_control(event_spec_id)
        if current is None or current.revision != expected_revision:
            raise ValueError("entry_regime_revision_conflict")
        new = EntryRegimeControl(
            event_spec_id=event_spec_id,
            revision=expected_revision + 1,
            enabled=enabled,
            authorization_id=authorization_id,
            created_at_ms=now_ms,
        )
        await self._connection.execute(
            sa.insert(entry_regime_revisions).values(**new.model_dump(mode="python"))
        )
        result = await self._connection.execute(
            sa.update(entry_regime_current)
            .where(
                entry_regime_current.c.event_spec_id == event_spec_id,
                entry_regime_current.c.revision == expected_revision,
            )
            .values(revision=new.revision)
        )
        if result.rowcount != 1:
            raise ValueError("entry_regime_revision_conflict")
        return new
