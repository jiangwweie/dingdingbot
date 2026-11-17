"""Verify the stored signed source of trusted-device Owner authorizations."""

import hashlib
import json

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.owner_device_authority import DeviceWriteProof
from src.trading_kernel.infrastructure.owner_device_credentials import (
    verify_device_signature,
)
from src.trading_kernel.infrastructure.pg_models import owner_authorizations as auths
from src.trading_kernel.infrastructure.pg_models import (
    owner_device_registrations as devices,
)
from src.trading_kernel.infrastructure.pg_models import (
    owner_device_write_evidence as writes,
)


def _control_matches(row, proof: DeviceWriteProof) -> bool:
    payload, purpose, scope = row["payload"], row["purpose"], row["target_scope"]
    if purpose in {"entry_pause", "entry_resume"}:
        path = "/api/owner/v1/mobile/controls/global"
        if set(payload) != {"owner_policy_id", "enabled", "expected_version"}:
            return False
        expected_scope = {"owner_policy_id": payload["owner_policy_id"]}
    elif purpose in {"strategy_pause", "strategy_resume"}:
        path = "/api/owner/v1/mobile/controls/strategy"
        if set(payload) != {"strategy_group_id", "enabled", "expected_version"}:
            return False
        expected_scope = {"strategy_group_id": payload["strategy_group_id"]}
    else:
        # Additional operation sources must supply their own exact contract.
        return False
    if (
        proof.method != "POST"
        or proof.path != path
        or scope != expected_scope
        or not isinstance(payload["enabled"], bool)
        or type(payload["expected_version"]) is not int
        or payload["expected_version"] <= 0
        or payload["enabled"] != purpose.endswith("resume")
    ):
        return False
    digest_payload = {
        "purpose": purpose,
        "expected_version": payload["expected_version"],
        "reason": "Owner mobile control",
        "idempotency_key": proof.idempotency_key,
        "target_scope": expected_scope,
    }
    digest = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    return digest == row["request_digest"] and proof.idempotency_key == row["auth_key"]


async def trusted_owner_authorization_matches(
    c: AsyncConnection, authorization_id: str
) -> bool:
    row = (
        (
            await c.execute(
                sa.select(
                    writes,
                    devices.c.public_key,
                    devices.c.registered_at_ms,
                    devices.c.revoked_at_ms,
                    devices.c.owner_identity.label("device_owner"),
                    devices.c.epoch.label("current_epoch"),
                    auths.c.purpose.label("auth_purpose"),
                    auths.c.owner_identity.label("auth_owner"),
                    auths.c.authorized_at_ms.label("auth_at"),
                    auths.c.authentication_strength,
                    auths.c.target_scope,
                    auths.c.request_digest,
                    auths.c.idempotency_key.label("auth_key"),
                )
                .join(devices, devices.c.device_id == writes.c.device_id)
                .join(auths, auths.c.authorization_id == writes.c.authorization_id)
                .where(auths.c.authorization_id == authorization_id)
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return False
    try:
        proof = DeviceWriteProof.model_validate(row["proof"])
        if (
            row["result_kind"] != "authorized"
            or row["authentication_strength"] != "trusted_device_session"
            or row["purpose"] != row["auth_purpose"]
            or row["owner_identity"] != row["auth_owner"]
            or row["device_owner"] != row["auth_owner"]
            or row["authorized_at_ms"] != row["auth_at"]
            or row["current_epoch"] != row["device_epoch"]
            or not row["registered_at_ms"] <= row["auth_at"] < proof.expires_at_ms
            or proof.issued_at_ms > row["auth_at"]
            or row["revoked_at_ms"] is not None
            and row["revoked_at_ms"] <= row["auth_at"]
            or proof.device_id != row["device_id"]
            or proof.device_epoch != row["device_epoch"]
            or proof.body_digest != row["body_digest"]
            or proof.body_digest != canonical_digest(row["payload"])
            or proof.idempotency_key != row["idempotency_key"]
            or canonical_digest(proof.model_dump(mode="json")) != row["evidence_id"]
            or not await _source_matches(c, row, proof)
        ):
            return False
        verify_device_signature(row["public_key"], proof, row["signature"])
    except (ValueError, TypeError, KeyError):
        return False
    return True


async def _source_matches(c, row, proof: DeviceWriteProof) -> bool:
    if row["purpose"] != "position_reduce":
        return _control_matches(row, proof)
    from src.trading_kernel.infrastructure.pg_models import (
        owner_position_operations as operations,
    )

    payload, scope = row["payload"], row["target_scope"]
    if (
        proof.method != "POST"
        or proof.path != "/api/owner/v1/mobile/operations/submit"
        or set(payload) != {"operation_id", "ticket_id", "expected_version"}
        or type(payload["expected_version"]) is not int
        or payload["expected_version"] != 1
    ):
        return False
    op = (
        (
            await c.execute(
                sa.select(operations).where(
                    operations.c.operation_id == payload["operation_id"]
                )
            )
        )
        .mappings()
        .one_or_none()
    )
    if op is None:
        return False
    expected_scope = {
        "operation_id": op["operation_id"],
        "ticket_id": op["ticket_id"],
        "management_revision": op["payload"]["preview"]["management_revision"],
        "device_id": op["device_id"],
        "device_epoch": op["device_epoch"],
    }
    return (
        op["authorization_id"] == row["authorization_id"]
        and op["owner_identity"] == row["owner_identity"]
        and op["kind"] == row["purpose"]
        and op["ticket_id"] == payload["ticket_id"]
        and op["device_id"] == proof.device_id
        and op["device_epoch"] == proof.device_epoch
        and scope == expected_scope
        and row["auth_key"] == "owner-position:" + op["operation_id"]
        and op["payload"]["submit_key"] == proof.idempotency_key
        and row["request_digest"]
        == canonical_digest(
            {"preview": op["request_digest"], "submit_key": proof.idempotency_key}
        )
    )
