"""PostgreSQL authority for immutable ExitProfiles and EventExitBindings."""

from __future__ import annotations

from typing import Literal, cast

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from src.trading_kernel.application.ports import ExitProfileAuthorityConflict
from src.trading_kernel.domain.exit_configuration import ExitConfigurationRecord
from src.trading_kernel.domain.exit_policy import (
    CurrentEventExitBinding,
    EventExitBinding,
    EventExitBindingEvent,
    ExitProfile,
    ExitProfileRecord,
)
from src.trading_kernel.domain.exit_regime import BtcMa50Snapshot
from src.trading_kernel.infrastructure.pg_models import (
    btc_ma50_current,
    btc_ma50_snapshots,
    event_exit_profile_binding_current,
    event_exit_profile_binding_events,
    event_exit_profile_bindings,
    event_specs,
    exit_configuration_current,
    exit_configurations,
    exit_policies,
)

EXIT_PROFILE_AUTHORITY_WRITE_LOCK = 0x455850524F46494C


class PostgresExitProfileAuthorityRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def get_configuration(
        self, configuration_id: str
    ) -> ExitConfigurationRecord | None:
        payload = await self._connection.scalar(
            sa.select(exit_configurations.c.record).where(
                exit_configurations.c.configuration_id == configuration_id
            )
        )
        return (
            None if payload is None else ExitConfigurationRecord.model_validate(payload)
        )

    async def get_current_configuration(
        self, *, venue_id: str, account_id: str
    ) -> ExitConfigurationRecord | None:
        payload = await self._connection.scalar(
            sa.select(exit_configurations.c.record)
            .join(
                exit_configuration_current,
                exit_configurations.c.configuration_id
                == exit_configuration_current.c.configuration_id,
            )
            .where(
                exit_configuration_current.c.product_id == "brc-app-manual-v1",
                exit_configuration_current.c.venue_id == venue_id,
                exit_configuration_current.c.account_id == account_id,
            )
        )
        return (
            None if payload is None else ExitConfigurationRecord.model_validate(payload)
        )

    async def activate_configuration(self, record: ExitConfigurationRecord) -> None:
        await self.acquire_authority_write_lock()
        current = await self.get_current_configuration(
            venue_id=record.intent.venue_id, account_id=record.intent.account_id
        )
        if (
            0 if current is None else current.revision
        ) != record.intent.expected_revision:
            raise ExitProfileAuthorityConflict("EXIT_CONFIGURATION_REVISION_CONFLICT")
        await self._connection.execute(
            sa.insert(exit_configurations).values(
                configuration_id=record.configuration_id,
                product_id=record.intent.product_id,
                venue_id=record.intent.venue_id,
                account_id=record.intent.account_id,
                revision=record.revision,
                owner_authorization_id=record.owner_authorization_id,
                record=record.model_dump(mode="json"),
                created_at_ms=record.created_at_ms,
            )
        )
        for lineage in record.profiles:
            profile = lineage.profile
            await self._connection.execute(
                sa.insert(exit_policies).values(
                    exit_policy_id=profile.exit_profile_id,
                    exit_policy_version=str(profile.exit_profile_version),
                    event_spec_id=None,
                    profile_schema_version=profile.profile_schema_version,
                    position_side=profile.position_side,
                    policy=profile.model_dump(mode="json"),
                    semantic_hash=profile.semantic_hash(),
                    status="active",
                    created_at_ms=record.created_at_ms,
                )
            )
            current_binding = await self.get_current_binding(
                lineage.event_spec_id, for_update=True
            )
            parameters = next(
                e
                for e in record.intent.events
                if e.event_spec_id == lineage.event_spec_id
            )
            if (
                current_binding is None
                or current_binding.exit_binding_id != parameters.expected_binding_id
                or current_binding.projection_version
                != parameters.expected_binding_revision
            ):
                raise ExitProfileAuthorityConflict("EXIT_BINDING_VERSION_CONFLICT")
            previous = await self.get_binding(current_binding.exit_binding_id)
            if previous is None:
                raise ExitProfileAuthorityConflict("EXIT_BINDING_MISSING")
            from src.trading_kernel.domain.exit_policy import build_event_exit_binding

            binding = build_event_exit_binding(
                exit_binding_id=f"exit-binding:{record.configuration_id}:{lineage.event_spec_id}",
                binding_version=previous.binding_version + 1,
                event_spec_id=lineage.event_spec_id,
                exit_profile_id=profile.exit_profile_id,
                exit_profile_semantic_hash=profile.semantic_hash(),
                activation_reason=f"owner configuration {record.configuration_id}",
                created_at_ms=record.created_at_ms,
            )
            await self.switch_current_binding(
                expected_current=current_binding,
                new_binding=binding,
                owner_authorization_id=record.owner_authorization_id,
                reason=binding.activation_reason,
                switched_at_ms=record.created_at_ms,
            )
        statement = pg_insert(exit_configuration_current).values(
            product_id=record.intent.product_id,
            venue_id=record.intent.venue_id,
            account_id=record.intent.account_id,
            configuration_id=record.configuration_id,
            revision=record.revision,
        )
        await self._connection.execute(
            statement.on_conflict_do_update(
                index_elements=[
                    exit_configuration_current.c.product_id,
                    exit_configuration_current.c.venue_id,
                    exit_configuration_current.c.account_id,
                ],
                set_={
                    "configuration_id": record.configuration_id,
                    "revision": record.revision,
                },
            )
        )

    async def get_ma50_snapshot(self) -> BtcMa50Snapshot | None:
        row = (
            (
                await self._connection.execute(
                    sa.select(btc_ma50_current).where(
                        btc_ma50_current.c.venue_id == "binance-usdm"
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None or row["blocked_window_close_ms"] is not None:
            return None
        return BtcMa50Snapshot.model_validate(row["snapshot"])

    async def save_ma50_snapshot(self, snapshot: BtcMa50Snapshot) -> bool:
        await self._connection.execute(
            sa.text("SELECT pg_advisory_xact_lock(73184651031)")
        )
        current = (
            (
                await self._connection.execute(
                    sa.select(btc_ma50_current)
                    .where(btc_ma50_current.c.venue_id == snapshot.venue_id)
                    .with_for_update()
                )
            )
            .mappings()
            .one_or_none()
        )
        if (
            current is not None
            and current["blocked_window_close_ms"] is not None
            and snapshot.latest_close_time_ms <= current["blocked_window_close_ms"]
        ):
            return False
        await self._connection.execute(
            pg_insert(btc_ma50_snapshots)
            .values(
                window_digest=snapshot.window_digest,
                venue_id=snapshot.venue_id,
                latest_close_time_ms=snapshot.latest_close_time_ms,
                snapshot=snapshot.model_dump(mode="json"),
                observed_at_ms=snapshot.observed_at_ms,
            )
            .on_conflict_do_nothing()
        )
        stored = await self._connection.scalar(
            sa.select(btc_ma50_snapshots.c.snapshot)
            .where(
                btc_ma50_snapshots.c.venue_id == snapshot.venue_id,
                btc_ma50_snapshots.c.latest_close_time_ms
                == snapshot.latest_close_time_ms,
            )
            .order_by(
                btc_ma50_snapshots.c.observed_at_ms, btc_ma50_snapshots.c.window_digest
            )
            .limit(1)
        )
        canonical = BtcMa50Snapshot.model_validate(stored)
        if (
            canonical.window_digest != snapshot.window_digest
            or canonical.latest_close != snapshot.latest_close
            or canonical.sma50 != snapshot.sma50
        ):
            await self._connection.execute(
                sa.update(btc_ma50_current)
                .where(btc_ma50_current.c.venue_id == snapshot.venue_id)
                .values(blocked_window_close_ms=snapshot.latest_close_time_ms)
            )
            return False
        snapshot = canonical
        statement = pg_insert(btc_ma50_current).values(
            venue_id=snapshot.venue_id,
            blocked_window_close_ms=None,
            snapshot=snapshot.model_dump(mode="json"),
            latest_close_time_ms=snapshot.latest_close_time_ms,
            observed_at_ms=snapshot.observed_at_ms,
        )
        await self._connection.execute(
            statement.on_conflict_do_update(
                index_elements=[btc_ma50_current.c.venue_id],
                set_={
                    "snapshot": statement.excluded.snapshot,
                    "blocked_window_close_ms": None,
                    "latest_close_time_ms": snapshot.latest_close_time_ms,
                    "observed_at_ms": snapshot.observed_at_ms,
                },
                where=btc_ma50_current.c.observed_at_ms < snapshot.observed_at_ms,
            )
        )

        return True

    async def acquire_authority_write_lock(self) -> None:
        await self._connection.execute(
            sa.text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": EXIT_PROFILE_AUTHORITY_WRITE_LOCK},
        )

    async def get_current_binding(
        self,
        event_spec_id: str,
        *,
        for_update: bool = False,
    ) -> CurrentEventExitBinding | None:
        statement = sa.select(event_exit_profile_binding_current).where(
            event_exit_profile_binding_current.c.event_spec_id == event_spec_id
        )
        if for_update:
            statement = statement.with_for_update(of=event_exit_profile_binding_current)
        row = (await self._connection.execute(statement)).mappings().one_or_none()
        return (
            None if row is None else CurrentEventExitBinding.model_validate(dict(row))
        )

    async def get_binding(self, exit_binding_id: str) -> EventExitBinding | None:
        row = (
            (
                await self._connection.execute(
                    sa.select(event_exit_profile_bindings)
                    .where(
                        event_exit_profile_bindings.c.exit_binding_id == exit_binding_id
                    )
                    .limit(1)
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else EventExitBinding.model_validate(dict(row))

    async def get_profile(
        self,
        *,
        exit_profile_id: str,
        semantic_hash: str,
    ) -> ExitProfileRecord | None:
        row = (
            (
                await self._connection.execute(
                    sa.select(exit_policies)
                    .where(
                        exit_policies.c.exit_policy_id == exit_profile_id,
                        exit_policies.c.semantic_hash == semantic_hash,
                        exit_policies.c.profile_schema_version.in_(
                            ("exit_profile_v1", "exit_profile_v2")
                        ),
                    )
                    .limit(1)
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        profile = ExitProfile.model_validate(row["policy"])
        if profile.exit_profile_id != str(
            row["exit_policy_id"]
        ) or profile.semantic_hash() != str(row["semantic_hash"]):
            raise ExitProfileAuthorityConflict("EXIT_PROFILE_HASH_DRIFT")
        status = str(row["status"])
        if status not in {"active", "retired"}:
            raise ExitProfileAuthorityConflict("EXIT_PROFILE_STATUS_INVALID")
        return ExitProfileRecord(
            profile=profile,
            status=cast(Literal["active", "retired"], status),
        )

    async def switch_current_binding(
        self,
        *,
        expected_current: CurrentEventExitBinding,
        new_binding: EventExitBinding,
        owner_authorization_id: str,
        reason: str,
        switched_at_ms: int,
    ) -> CurrentEventExitBinding:
        current = await self.get_current_binding(
            expected_current.event_spec_id,
            for_update=True,
        )
        if current != expected_current:
            raise ExitProfileAuthorityConflict("EXIT_BINDING_VERSION_CONFLICT")
        previous = await self.get_binding(expected_current.exit_binding_id)
        if previous is None:
            raise ExitProfileAuthorityConflict("EXIT_BINDING_MISSING")
        if (
            new_binding.event_spec_id != current.event_spec_id
            or new_binding.binding_version != previous.binding_version + 1
        ):
            raise ExitProfileAuthorityConflict("EXIT_BINDING_SUCCESSOR_INVALID")
        profile = await self.get_profile(
            exit_profile_id=new_binding.exit_profile_id,
            semantic_hash=new_binding.exit_profile_semantic_hash,
        )
        if profile is None or profile.status != "active":
            raise ExitProfileAuthorityConflict("EXIT_PROFILE_NOT_ACTIVE")
        event_side = await self._connection.scalar(
            sa.select(event_specs.c.position_side).where(
                event_specs.c.event_spec_id == new_binding.event_spec_id
            )
        )
        if event_side != profile.profile.position_side:
            raise ExitProfileAuthorityConflict("EXIT_PROFILE_SIDE_MISMATCH")

        await self._connection.execute(
            sa.insert(event_exit_profile_bindings).values(
                **new_binding.model_dump(mode="python")
            )
        )
        await self._add_binding_event(
            binding=previous,
            operation="RETIRED",
            authorization_source="owner_control",
            owner_authorization_id=owner_authorization_id,
            reason=reason,
            occurred_at_ms=switched_at_ms,
        )
        await self._add_binding_event(
            binding=new_binding,
            operation="ACTIVATED",
            authorization_source="owner_control",
            owner_authorization_id=owner_authorization_id,
            reason=reason,
            occurred_at_ms=switched_at_ms,
        )
        result = await self._connection.execute(
            sa.update(event_exit_profile_binding_current)
            .where(
                event_exit_profile_binding_current.c.event_spec_id
                == current.event_spec_id,
                event_exit_profile_binding_current.c.exit_binding_id
                == current.exit_binding_id,
                event_exit_profile_binding_current.c.binding_semantic_hash
                == current.binding_semantic_hash,
                event_exit_profile_binding_current.c.projection_version
                == current.projection_version,
            )
            .values(
                exit_binding_id=new_binding.exit_binding_id,
                binding_semantic_hash=new_binding.binding_semantic_hash,
                projection_version=current.projection_version + 1,
                activated_at_ms=switched_at_ms,
            )
        )
        if result.rowcount != 1:
            raise ExitProfileAuthorityConflict("EXIT_BINDING_VERSION_CONFLICT")
        return CurrentEventExitBinding(
            event_spec_id=current.event_spec_id,
            exit_binding_id=new_binding.exit_binding_id,
            binding_semantic_hash=new_binding.binding_semantic_hash,
            projection_version=current.projection_version + 1,
            activated_at_ms=switched_at_ms,
        )

    async def retire_profile(
        self,
        *,
        profile: ExitProfile,
        retired_at_ms: int,
    ) -> ExitProfileRecord:
        del retired_at_ms
        record = await self.get_profile(
            exit_profile_id=profile.exit_profile_id,
            semantic_hash=profile.semantic_hash(),
        )
        if record is None or record.status != "active":
            raise ExitProfileAuthorityConflict("EXIT_PROFILE_NOT_ACTIVE")
        active_count = int(
            await self._connection.scalar(
                sa.select(sa.func.count())
                .select_from(event_exit_profile_binding_current)
                .join(
                    event_exit_profile_bindings,
                    event_exit_profile_bindings.c.exit_binding_id
                    == event_exit_profile_binding_current.c.exit_binding_id,
                )
                .where(
                    event_exit_profile_bindings.c.exit_profile_id
                    == profile.exit_profile_id
                )
            )
            or 0
        )
        if active_count:
            raise ExitProfileAuthorityConflict("EXIT_PROFILE_HAS_CURRENT_BINDING")
        result = await self._connection.execute(
            sa.update(exit_policies)
            .where(
                exit_policies.c.exit_policy_id == profile.exit_profile_id,
                exit_policies.c.semantic_hash == profile.semantic_hash(),
                exit_policies.c.status == "active",
            )
            .values(status="retired")
        )
        if result.rowcount != 1:
            raise ExitProfileAuthorityConflict("EXIT_PROFILE_NOT_ACTIVE")
        return ExitProfileRecord(profile=profile, status="retired")

    async def retire_current_bindings_for_events(
        self,
        *,
        event_spec_ids: tuple[str, ...],
        reason: str,
        retired_at_ms: int,
    ) -> None:
        await self.acquire_authority_write_lock()
        for event_spec_id in sorted(event_spec_ids):
            current = await self.get_current_binding(event_spec_id, for_update=True)
            if current is None:
                continue
            binding = await self.get_binding(current.exit_binding_id)
            if binding is None:
                raise ExitProfileAuthorityConflict("EXIT_BINDING_MISSING")
            await self._add_binding_event(
                binding=binding,
                operation="RETIRED",
                authorization_source="system_migration",
                owner_authorization_id=None,
                reason=reason,
                occurred_at_ms=retired_at_ms,
            )
            deleted = await self._connection.execute(
                sa.delete(event_exit_profile_binding_current).where(
                    event_exit_profile_binding_current.c.event_spec_id == event_spec_id,
                    event_exit_profile_binding_current.c.projection_version
                    == current.projection_version,
                )
            )
            if deleted.rowcount != 1:
                raise ExitProfileAuthorityConflict("EXIT_BINDING_VERSION_CONFLICT")

    async def list_profiles(self, *, limit: int) -> tuple[ExitProfileRecord, ...]:
        if not 1 <= limit <= 32:
            raise ValueError("ExitProfile readonly limit must be in [1, 32]")
        rows = (
            (
                await self._connection.execute(
                    sa.select(exit_policies)
                    .where(
                        exit_policies.c.profile_schema_version.in_(
                            ("exit_profile_v1", "exit_profile_v2")
                        )
                    )
                    .order_by(exit_policies.c.exit_policy_id)
                    .limit(limit)
                )
            )
            .mappings()
            .all()
        )
        records = []
        for row in rows:
            profile = ExitProfile.model_validate(row["policy"])
            if (
                profile.exit_profile_id != str(row["exit_policy_id"])
                or profile.semantic_hash() != str(row["semantic_hash"])
            ):
                raise ExitProfileAuthorityConflict("EXIT_PROFILE_HASH_DRIFT")
            status = str(row["status"])
            if status not in {"active", "retired"}:
                raise ExitProfileAuthorityConflict("EXIT_PROFILE_STATUS_INVALID")
            records.append(
                ExitProfileRecord(
                    profile=profile,
                    status=cast(Literal["active", "retired"], status),
                )
            )
        return tuple(records)

    async def list_current_bindings(
        self,
        *,
        event_spec_id: str | None,
        limit: int,
    ) -> tuple[CurrentEventExitBinding, ...]:
        if not 1 <= limit <= 32:
            raise ValueError("current Binding readonly limit must be in [1, 32]")
        statement = sa.select(event_exit_profile_binding_current)
        if event_spec_id is not None:
            statement = statement.where(
                event_exit_profile_binding_current.c.event_spec_id
                == event_spec_id
            )
        rows = (
            await self._connection.execute(
                statement.order_by(
                    event_exit_profile_binding_current.c.event_spec_id
                ).limit(limit)
            )
        ).mappings().all()
        return tuple(
            CurrentEventExitBinding.model_validate(dict(row)) for row in rows
        )

    async def list_binding_events(
        self,
        *,
        event_spec_id: str | None,
        limit: int,
    ) -> tuple[EventExitBindingEvent, ...]:
        if not 1 <= limit <= 50:
            raise ValueError("Binding event readonly limit must be in [1, 50]")
        statement = sa.select(event_exit_profile_binding_events)
        if event_spec_id is not None:
            statement = statement.where(
                event_exit_profile_binding_events.c.event_spec_id == event_spec_id
            )
        rows = (
            await self._connection.execute(
                statement.order_by(
                    event_exit_profile_binding_events.c.created_at_ms.desc(),
                    event_exit_profile_binding_events.c.binding_event_id.desc(),
                ).limit(limit)
            )
        ).mappings().all()
        return tuple(
            EventExitBindingEvent.model_validate(dict(row)) for row in rows
        )

    async def _add_binding_event(
        self,
        *,
        binding: EventExitBinding,
        operation: str,
        authorization_source: str,
        owner_authorization_id: str | None,
        reason: str,
        occurred_at_ms: int,
    ) -> None:
        await self._connection.execute(
            sa.insert(event_exit_profile_binding_events).values(
                binding_event_id=(
                    f"binding-event:{binding.exit_binding_id}:{operation.lower()}"
                ),
                event_spec_id=binding.event_spec_id,
                exit_binding_id=binding.exit_binding_id,
                binding_version=binding.binding_version,
                operation=operation,
                authorization_source=authorization_source,
                owner_authorization_id=owner_authorization_id,
                reason=reason,
                created_at_ms=occurred_at_ms,
            )
        )
