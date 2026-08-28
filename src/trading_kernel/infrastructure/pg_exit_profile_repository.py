"""PostgreSQL authority for immutable ExitProfiles and EventExitBindings."""

from __future__ import annotations

from typing import Literal, cast

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

from src.trading_kernel.application.ports import ExitProfileAuthorityConflict
from src.trading_kernel.domain.exit_policy import (
    CurrentEventExitBinding,
    EventExitBinding,
    EventExitBindingEvent,
    ExitProfile,
    ExitProfileRecord,
)
from src.trading_kernel.infrastructure.pg_models import (
    event_exit_profile_binding_current,
    event_exit_profile_binding_events,
    event_exit_profile_bindings,
    event_specs,
    exit_policies,
)

EXIT_PROFILE_AUTHORITY_WRITE_LOCK = 0x455850524F46494C


class PostgresExitProfileAuthorityRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

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
                        exit_policies.c.profile_schema_version == "exit_profile_v1",
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
            await self._connection.execute(
                sa.select(exit_policies)
                .where(exit_policies.c.profile_schema_version == "exit_profile_v1")
                .order_by(exit_policies.c.exit_policy_id)
                .limit(limit)
            )
        ).mappings().all()
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
