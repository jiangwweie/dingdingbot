"""Durable, versioned Owner position intents; never dispatch exchange writes."""

from __future__ import annotations

import secrets

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.owner_device_authority import DeviceWriteProof
from src.trading_kernel.domain.owner_reduction import (
    OwnerReductionPhase,
    OwnerReductionPreview,
    OwnerReductionState,
)
from src.trading_kernel.infrastructure.pg_models import (
    owner_authorizations as authorizations,
)
from src.trading_kernel.infrastructure.pg_models import (
    owner_device_registrations as devices,
)
from src.trading_kernel.infrastructure.pg_models import (
    owner_position_operation_events as events,
)
from src.trading_kernel.infrastructure.pg_models import (
    owner_position_operations as operations,
)
from src.trading_kernel.infrastructure.pg_models import (
    trade_aggregates as aggregates,
)


class PostgresOwnerPositionOperations:
    def __init__(self, c: AsyncConnection):
        self.c = c

    async def get(self, operation_id: str, *, for_update: bool = False) -> dict | None:
        q = sa.select(operations).where(operations.c.operation_id == operation_id)
        if for_update:
            q = q.with_for_update()
        r = (await self.c.execute(q)).mappings().one_or_none()
        return None if r is None else dict(r)

    async def _event(self, row: dict, now_ms: int) -> None:
        await self.c.execute(
            sa.insert(events).values(
                operation_id=row["operation_id"],
                version=row["version"],
                state=row["state"],
                payload=row["payload"],
                occurred_at_ms=now_ms,
            )
        )

    async def create_preview(
        self,
        *,
        preview: OwnerReductionPreview,
        owner_identity: str,
        device_id: str,
        device_epoch: int,
        idempotency_key: str,
        now_ms: int,
    ) -> dict:
        digest = canonical_digest(preview.model_dump(mode="json"))
        await self.c.execute(
            sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:k,0))"),
            {"k": "owner-preview:" + owner_identity + ":" + idempotency_key},
        )
        old = (
            (
                await self.c.execute(
                    sa.select(operations).where(
                        operations.c.owner_identity == owner_identity,
                        operations.c.idempotency_key == idempotency_key,
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        if old is not None:
            if (
                old["request_digest"] != digest
                or old["device_id"] != device_id
                or old["device_epoch"] != device_epoch
            ):
                raise ValueError("idempotency_conflict")
            return dict(old)
        if not preview.created_at_ms <= now_ms < preview.expires_at_ms:
            raise ValueError("preview_expired")
        row = {
            "operation_id": "owner-op:" + secrets.token_hex(16),
            "ticket_id": preview.ticket_id,
            "kind": "position_reduce",
            "owner_identity": owner_identity,
            "device_id": device_id,
            "device_epoch": device_epoch,
            "authorization_id": None,
            "idempotency_key": idempotency_key,
            "request_digest": digest,
            "version": 1,
            "state": "previewed",
            "payload": {"preview": preview.model_dump(mode="json")},
            "first_blocker": None,
            "created_at_ms": now_ms,
            "updated_at_ms": now_ms,
            "due_at_ms": preview.expires_at_ms,
            "completed_at_ms": None,
        }
        await self.c.execute(sa.insert(operations).values(**row))
        await self._event(row, now_ms)
        return row

    async def accept(
        self,
        *,
        operation_id: str,
        owner_identity: str,
        device_id: str,
        device_epoch: int,
        idempotency_key: str,
        proof: DeviceWriteProof,
        now_ms: int,
    ) -> dict:
        row = await self.get(operation_id, for_update=True)
        if (
            row is None
            or row["owner_identity"] != owner_identity
            or row["device_id"] != device_id
            or row["device_epoch"] != device_epoch
        ):
            raise ValueError("operation_identity_mismatch")
        from src.trading_kernel.infrastructure.pg_models import (
            owner_device_write_evidence,
        )

        evidence = (
            (
                await self.c.execute(
                    sa.select(owner_device_write_evidence)
                    .where(
                        owner_device_write_evidence.c.evidence_id
                        == canonical_digest(proof.model_dump(mode="json"))
                    )
                    .with_for_update()
                )
            )
            .mappings()
            .one_or_none()
        )
        expected_payload = {
            "operation_id": operation_id,
            "ticket_id": row["ticket_id"],
            "expected_version": 1,
        }
        if (
            evidence is None
            or evidence["owner_identity"] != owner_identity
            or evidence["device_id"] != device_id
            or evidence["device_epoch"] != device_epoch
            or evidence["purpose"] != row["kind"]
            or evidence["idempotency_key"] != idempotency_key
            or evidence["payload"] != expected_payload
            or proof.body_digest != canonical_digest(expected_payload)
            or proof.path != "/api/owner/v1/mobile/operations/submit"
            or proof.method != "POST"
        ):
            raise ValueError("operation_signed_source_missing")
        d = (
            (
                await self.c.execute(
                    sa.select(devices)
                    .where(devices.c.device_id == device_id)
                    .with_for_update()
                )
            )
            .mappings()
            .one_or_none()
        )
        if (
            d is None
            or d["epoch"] != device_epoch
            or d["revoked_at_ms"] is not None
            or d["owner_identity"] != owner_identity
        ):
            raise ValueError("device_revoked")
        if row["state"] != "previewed":
            if row["payload"].get("submit_key") != idempotency_key:
                raise ValueError("operation_already_submitted")
            return row
        p = OwnerReductionPreview.model_validate(row["payload"]["preview"])
        if not p.created_at_ms <= now_ms < p.expires_at_ms:
            raise ValueError("preview_expired")
        a = (
            (
                await self.c.execute(
                    sa.select(aggregates)
                    .where(aggregates.c.ticket_id == p.ticket_id)
                    .with_for_update()
                )
            )
            .mappings()
            .one_or_none()
        )
        if (
            a is None
            or a["version"] != p.aggregate_version
            or a["management_revision"] != p.management_revision
            or a["management_mode"] != "AUTO"
            or a["position_qty"] != p.source_quantity
            or a["active_stop_exchange_order_id"] != p.protection_order_id
            or a["active_stop_price"] != p.stop_price
        ):
            raise ValueError("preview_stale")
        active = await self.c.scalar(
            sa.select(operations.c.operation_id).where(
                operations.c.ticket_id == p.ticket_id,
                operations.c.completed_at_ms.is_(None),
                operations.c.state != "previewed",
            )
        )
        if active is not None:
            raise ValueError("ticket_adjustment_in_progress")
        auth = "owner-auth:" + secrets.token_hex(16)
        scope = {
            "ticket_id": p.ticket_id,
            "operation_id": row["operation_id"],
            "management_revision": p.management_revision,
            "device_id": device_id,
            "device_epoch": device_epoch,
        }
        await self.c.execute(
            sa.insert(authorizations).values(
                authorization_id=auth,
                purpose="position_reduce",
                owner_identity=owner_identity,
                authentication_strength="trusted_device_session",
                request_digest=canonical_digest(
                    {"preview": row["request_digest"], "submit_key": idempotency_key}
                ),
                target_scope=scope,
                idempotency_key="owner-position:" + operation_id,
                authorized_at_ms=now_ms,
            )
        )
        state = OwnerReductionState(
            operation_id=operation_id, preview=p, phase=OwnerReductionPhase.PREVIEWED
        )
        payload = {
            **row["payload"],
            "submit_key": idempotency_key,
            "reduction_state": state.model_dump(mode="json"),
        }
        row.update(
            state="accepted",
            version=2,
            authorization_id=auth,
            payload=payload,
            updated_at_ms=now_ms,
            due_at_ms=now_ms,
        )
        await self.c.execute(
            sa.update(operations)
            .where(operations.c.operation_id == operation_id, operations.c.version == 1)
            .values(
                state="accepted",
                version=2,
                authorization_id=auth,
                payload=payload,
                updated_at_ms=now_ms,
                due_at_ms=now_ms,
            )
        )
        await self._event(row, now_ms)
        from src.trading_kernel.infrastructure.pg_owner_device_repository import (
            PostgresOwnerDeviceRepository,
        )

        await PostgresOwnerDeviceRepository(self.c).link_authorization(
            proof=proof, owner_identity=owner_identity, authorization_id=auth
        )
        return row

    async def save_state(
        self,
        *,
        operation_id: str,
        expected_version: int,
        state: OwnerReductionState,
        reason: str,
        next_check_at_ms: int,
        now_ms: int,
    ) -> dict:
        row = await self.get(operation_id, for_update=True)
        if (
            row is None
            or row["version"] != expected_version
            or row["authorization_id"] is None
        ):
            raise ValueError("operation_version_conflict")
        if state.operation_id != operation_id:
            raise ValueError("operation_identity_mismatch")
        old = OwnerReductionState.model_validate(row["payload"]["reduction_state"])
        if (
            old.preview != state.preview
            or state.actual_reduction_quantity < old.actual_reduction_quantity
        ):
            raise ValueError("operation_facts_regressed")
        payload = {**row["payload"], "reduction_state": state.model_dump(mode="json")}
        row.update(
            version=expected_version + 1,
            state=state.phase.value,
            payload=payload,
            first_blocker=reason,
            updated_at_ms=now_ms,
            due_at_ms=next_check_at_ms,
        )
        await self.c.execute(
            sa.update(operations)
            .where(
                operations.c.operation_id == operation_id,
                operations.c.version == expected_version,
            )
            .values(
                version=row["version"],
                state=row["state"],
                payload=payload,
                first_blocker=reason,
                updated_at_ms=now_ms,
                due_at_ms=next_check_at_ms,
            )
        )
        await self._event(row, now_ms)
        return row

    async def due(self, *, now_ms: int, limit: int = 20) -> tuple[dict, ...]:
        if not 1 <= limit <= 50:
            raise ValueError("operation_query_limit")
        rows = (
            (
                await self.c.execute(
                    sa.select(operations)
                    .where(
                        operations.c.completed_at_ms.is_(None),
                        operations.c.state != "previewed",
                        operations.c.due_at_ms <= now_ms,
                    )
                    .order_by(operations.c.due_at_ms, operations.c.operation_id)
                    .limit(limit)
                )
            )
            .mappings()
            .all()
        )
        return tuple(dict(x) for x in rows)
