"""Durable, versioned Owner position intents; never dispatch exchange writes."""

from __future__ import annotations

import secrets
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

from src.trading_kernel.domain.aggregate import TradeAggregate
from src.trading_kernel.domain.commands import ExchangeCommand
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.owner_device_authority import DeviceWriteProof
from src.trading_kernel.domain.owner_position_operation import OwnerPositionPreview
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
        preview: OwnerReductionPreview | OwnerPositionPreview,
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
            "kind": "position_reduce"
            if isinstance(preview, OwnerReductionPreview)
            else preview.kind,
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
        from src.trading_kernel.infrastructure.pg_notice_outbox import (
            enqueue_position_operation_notice,
        )

        await enqueue_position_operation_notice(self.c, row)
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
        initial = await self.get(operation_id)
        if initial is not None:
            await self.c.execute(
                sa.select(aggregates.c.ticket_id)
                .where(aggregates.c.ticket_id == initial["ticket_id"])
                .with_for_update()
            )
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
            "expected_version": row["payload"].get("preview_version", 1),
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
        p: OwnerReductionPreview | OwnerPositionPreview = (
            OwnerReductionPreview.model_validate(row["payload"]["preview"])
            if row["kind"] == "position_reduce"
            else OwnerPositionPreview.model_validate(row["payload"]["preview"])
        )
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
                operations.c.state.notin_(("previewed", "preview_requested")),
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
                purpose=row["kind"],
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
        payload = {
            **row["payload"],
            "submit_key": idempotency_key,
            "started_at_ms": now_ms,
        }
        if isinstance(p, OwnerReductionPreview):
            state = OwnerReductionState(
                operation_id=operation_id,
                preview=p,
                phase=OwnerReductionPhase.PREVIEWED,
                started_at_ms=now_ms,
            )
            payload["reduction_state"] = state.model_dump(mode="json")
        previous_version = row["version"]
        row.update(
            state="accepted",
            version=previous_version + 1,
            authorization_id=auth,
            payload=payload,
            updated_at_ms=now_ms,
            due_at_ms=now_ms,
        )
        await self.c.execute(
            sa.update(operations)
            .where(
                operations.c.operation_id == operation_id,
                operations.c.version == previous_version,
            )
            .values(
                state="accepted",
                version=previous_version + 1,
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

        await PostgresOwnerDeviceRepository(self.c).finish_control(
            proof=proof,
            owner_identity=owner_identity,
            authorization_id=auth,
            result={
                "operation_id": operation_id,
                "ticket_id": row["ticket_id"],
                "state": "accepted",
                "version": row["version"],
            },
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
            completed_at_ms=now_ms
            if state.phase
            in {
                OwnerReductionPhase.WAIT_PRICE,
                OwnerReductionPhase.RUNNER_CONTINUING,
                OwnerReductionPhase.REJECTED,
            }
            else None,
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
                completed_at_ms=row["completed_at_ms"],
            )
        )
        await self._event(row, now_ms)
        from src.trading_kernel.infrastructure.pg_notice_outbox import (
            enqueue_position_operation_notice,
        )

        await enqueue_position_operation_notice(self.c, row)
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

    async def active_for_ticket(self, ticket_id: str) -> dict | None:
        row = (
            (
                await self.c.execute(
                    sa.select(operations).where(
                        operations.c.ticket_id == ticket_id,
                        operations.c.completed_at_ms.is_(None),
                        operations.c.state.notin_(("previewed", "preview_requested")),
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row is not None else None

    async def transition(
        self,
        *,
        operation_id: str,
        expected_version: int,
        state: str,
        payload: dict,
        reason: str | None,
        now_ms: int,
        completed: bool = False,
    ) -> dict:
        row = await self.get(operation_id, for_update=True)
        if (
            row is None
            or row["version"] != expected_version
            or row["completed_at_ms"] is not None
        ):
            raise ValueError("operation_version_conflict")
        if payload.get("preview") != row["payload"]["preview"] or payload.get(
            "submit_key"
        ) != row["payload"].get("submit_key"):
            raise ValueError("operation_authority_changed")
        previous_end=row['payload'].get('end_requested')
        if previous_end is not None and payload.get('end_requested')!=previous_end:
            raise ValueError('operation_end_request_immutable')
        if state == "facts_unavailable":
            failures = int(row["payload"].get("consecutive_fact_failures", 0)) + 1
            payload = {**payload, "consecutive_fact_failures": failures}
            if failures >= 3:
                state = "review_required"
        else:
            payload = {**payload, "consecutive_fact_failures": 0}
        row.update(
            version=expected_version + 1,
            state=state,
            payload=payload,
            first_blocker=reason,
            updated_at_ms=now_ms,
            due_at_ms=now_ms
            + (
                30000
                if state == "review_required"
                else 5000
                if state in {"facts_unavailable", "closure_pending"}
                else 1000
            ),
            completed_at_ms=now_ms if completed else None,
        )
        await self.c.execute(
            sa.update(operations)
            .where(
                operations.c.operation_id == operation_id,
                operations.c.version == expected_version,
            )
            .values(
                **{
                    k: row[k]
                    for k in (
                        "version",
                        "state",
                        "payload",
                        "first_blocker",
                        "updated_at_ms",
                        "due_at_ms",
                        "completed_at_ms",
                    )
                }
            )
        )
        await self._event(row, now_ms)
        from src.trading_kernel.infrastructure.pg_notice_outbox import (
            enqueue_position_operation_notice,
        )

        await enqueue_position_operation_notice(self.c, row)
        return row

    async def authority_current(self, row: dict, *, management_revision: int) -> bool:
        from src.trading_kernel.infrastructure.owner_device_authorization_evidence import (
            trusted_owner_authorization_matches,
        )

        device = (
            (
                await self.c.execute(
                    sa.select(devices).where(devices.c.device_id == row["device_id"])
                )
            )
            .mappings()
            .one_or_none()
        )
        return bool(
            row["authorization_id"]
            and device is not None
            and device["epoch"] == row["device_epoch"]
            and device["revoked_at_ms"] is None
            and row["payload"]["preview"]["management_revision"] == management_revision
            and await trusted_owner_authorization_matches(
                self.c, row["authorization_id"]
            )
        )

    async def command_send_blocker(
        self, command: ExchangeCommand, aggregate: TradeAggregate, *, now_ms: int
    ) -> str | None:
        from src.trading_kernel.domain.commands import ExchangeCommandKind as K

        row = await self.active_for_ticket(aggregate.identity.ticket_id)
        operation_id = (
            command.payload.owner_operation_id
            if hasattr(command.payload, "owner_operation_id")
            else None
        )
        if operation_id is not None:
            from src.trading_kernel.infrastructure.pg_models import (
                runtime_capabilities_current,
            )

            capability = (
                (
                    await self.c.execute(
                        sa.select(runtime_capabilities_current).where(
                            runtime_capabilities_current.c.capability_key
                            == "exchange_commands"
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
            if (
                capability is None
                or not capability["enabled"]
                or capability["certification"].get("owner_cooperation")
                != "owner-cooperation-v1"
            ):
                return "owner_operation_capability_disabled"
            if (
                row is None
                or row["operation_id"] != operation_id
                or command.command_id
                not in row["payload"].get("prepared_command_ids", [])
            ):
                return "owner_operation_command_not_bound"
            if row["payload"].get("end_requested"):
                return "owner_operation_ending_requires_new_confirmation"
            if not await self.authority_current(
                row, management_revision=aggregate.management_revision
            ):
                return "owner_operation_authority_revoked"
            facts = row["payload"].get("facts")
            if facts is None or not int(facts["observed_at_ms"]) <= now_ms < min(
                int(facts["valid_until_ms"]), int(facts["observed_at_ms"]) + 5000
            ):
                return "owner_operation_facts_stale"
            preview = row["payload"]["preview"]
            price = Decimal(str(facts["current_price"]))
            stop = (
                Decimal(str(facts["stop_price"]))
                if facts.get("stop_price") is not None
                else None
            )
            long = preview["side"] == "long"
            if stop is None or (price <= stop if long else price >= stop):
                return "owner_operation_stop_price_crossed"
            if (
                command.kind is K.OWNER_REDUCE
                and preview.get("tp_trigger_price") is not None
            ):
                target = Decimal(preview["tp_trigger_price"])
                if price >= target if long else price <= target:
                    return "owner_reduction_target_reached_before_send"
            from src.trading_kernel.domain.commands import OrderCommandPayload
            from src.trading_kernel.domain.owner_command_prices import (
                owner_command_price_blocker,
            )

            if isinstance(command.payload, OrderCommandPayload):
                new_price_blocker = owner_command_price_blocker(
                    kind=command.kind,
                    payload=command.payload,
                    position_side=preview["side"],
                    current_price=price,
                )
                if new_price_blocker is not None:
                    return new_price_blocker
            if command.kind in {K.OWNER_REDUCE, K.EXIT} and (
                (
                    command.kind is K.OWNER_REDUCE
                    and not row["payload"].get("protection_close_position")
                )
                or aggregate.active_stop_exchange_order_id
                != facts["protection_order_id"]
                or Decimal(str(facts["position_quantity"])) != aggregate.position_qty
                or Decimal(str(facts["protected_quantity"]))
                != Decimal(str(facts["position_quantity"]))
                or facts["reduction_state"] not in {"not_sent"}
                or facts["tp_state"] not in {"cancelled", "absent"}
                or facts["stop_triggered"]
            ):
                return "owner_reduction_preconditions_changed"
        elif row is not None and command.kind in {K.TAKE_PROFIT, K.REPLACE_PROTECTION}:
            if not (
                command.kind is K.TAKE_PROFIT
                and row["state"] == "restoring_original_tp"
                and command.command_id
                in row["payload"].get("restoration_command_ids", [])
            ):
                return "owner_operation_serialization"
            from src.trading_kernel.domain.commands import OrderCommandPayload
            from src.trading_kernel.domain.owner_command_prices import (
                owner_command_price_blocker,
            )

            f = row["payload"].get("facts")
            if f is None or not int(f["observed_at_ms"]) <= now_ms < min(
                int(f["valid_until_ms"]), int(f["observed_at_ms"]) + 5000
            ):
                return "owner_operation_facts_stale"
            if isinstance(command.payload, OrderCommandPayload):
                reason = owner_command_price_blocker(
                    kind=command.kind,
                    payload=command.payload,
                    position_side=aggregate.identity.netting_domain.position_side,
                    current_price=Decimal(str(f["current_price"])),
                )
                if reason is not None:
                    return reason
        return None

    async def request_preview(
        self,
        *,
        ticket_id: str,
        kind: str,
        parameters: dict,
        owner_identity: str,
        device_id: str,
        device_epoch: int,
        idempotency_key: str,
        now_ms: int,
    ) -> dict:
        await self.c.execute(
            sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:k,0))"),
            {"k": "owner-preview:" + owner_identity + ":" + idempotency_key},
        )
        request = {"ticket_id": ticket_id, "kind": kind, **parameters}
        digest = canonical_digest(request)
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
                old["payload"].get("preview_request_digest") != digest
                or old["device_id"] != device_id
                or old["device_epoch"] != device_epoch
            ):
                raise ValueError("idempotency_conflict")
            return dict(old)
        if (
            int(
                await self.c.scalar(
                    sa.select(sa.func.count())
                    .select_from(operations)
                    .where(
                        operations.c.owner_identity == owner_identity,
                        operations.c.authorization_id.is_(None),
                        operations.c.completed_at_ms.is_(None),
                        operations.c.updated_at_ms > now_ms - 60000,
                    )
                )
                or 0
            )
            >= 10
        ):
            raise ValueError("preview_limit")
        row = {
            "operation_id": "owner-op:" + secrets.token_hex(16),
            "ticket_id": ticket_id,
            "kind": kind,
            "owner_identity": owner_identity,
            "device_id": device_id,
            "device_epoch": device_epoch,
            "authorization_id": None,
            "idempotency_key": idempotency_key,
            "request_digest": digest,
            "version": 1,
            "state": "preview_requested",
            "payload": {
                "preview": None,
                "request": request,
                "preview_request_digest": digest,
            },
            "first_blocker": None,
            "created_at_ms": now_ms,
            "updated_at_ms": now_ms,
            "due_at_ms": now_ms,
            "completed_at_ms": None,
        }
        await self.c.execute(sa.insert(operations).values(**row))
        await self._event(row, now_ms)
        from src.trading_kernel.infrastructure.pg_notice_outbox import (
            enqueue_position_operation_notice,
        )

        await enqueue_position_operation_notice(self.c, row)
        return row

    async def ready_preview(
        self,
        row: dict,
        preview: OwnerReductionPreview | OwnerPositionPreview,
        *,
        now_ms: int,
    ) -> None:
        current = await self.get(row["operation_id"], for_update=True)
        if (
            current is None
            or current["version"] != row["version"]
            or current["state"] != "preview_requested"
        ):
            raise ValueError("preview_version_conflict")
        version = row["version"] + 1
        payload = {
            **row["payload"],
            "preview": preview.model_dump(mode="json"),
            "preview_version": version,
        }
        row.update(
            version=version,
            state="previewed",
            payload=payload,
            request_digest=canonical_digest(payload["preview"]),
            due_at_ms=preview.expires_at_ms,
            updated_at_ms=now_ms,
        )
        await self.c.execute(
            sa.update(operations)
            .where(operations.c.operation_id == row["operation_id"])
            .values(
                **{
                    k: row[k]
                    for k in (
                        "version",
                        "state",
                        "payload",
                        "request_digest",
                        "due_at_ms",
                        "updated_at_ms",
                    )
                }
            )
        )
        await self._event(row, now_ms)
