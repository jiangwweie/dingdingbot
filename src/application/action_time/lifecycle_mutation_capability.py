"""PG-current capability gate for ticket lifecycle exchange mutation."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from src.application.readmodels.lifecycle_mutation_enablement_proof import (
    LifecycleMutationEnablementProof,
)


CAPABILITY_ID = "ticket_lifecycle_durable_mutation"
REQUIRED_COMMAND_COLUMNS = {
    "command_kind",
    "command_source",
    "source_command_id",
    "claim_owner",
    "claim_token",
    "claim_expires_at_ms",
    "netting_domain_key",
    "reduce_intent",
}


def lifecycle_mutation_capability_decision(
    conn: sa.engine.Connection,
) -> dict[str, Any]:
    inspector = sa.inspect(conn)
    blockers: list[str] = []
    if not inspector.has_table("brc_runtime_capabilities_current"):
        blockers.append("lifecycle_mutation_capability_projection_missing")
        return _result({}, blockers)
    table = sa.Table(
        "brc_runtime_capabilities_current",
        sa.MetaData(),
        autoload_with=conn,
    )
    row = conn.execute(
        sa.select(table).where(table.c.capability_id == CAPABILITY_ID)
    ).mappings().first()
    capability = dict(row) if row else {}
    if not capability:
        blockers.append("lifecycle_mutation_capability_row_missing")
    elif str(capability.get("status") or "") != "enabled":
        blockers.append("lifecycle_mutation_capability_not_ready")
    else:
        proof_columns = {"proof_schema", "proof_payload"}
        if not proof_columns <= set(table.c.keys()):
            blockers.append("lifecycle_mutation_enablement_proof_schema_missing")
        else:
            try:
                proof = LifecycleMutationEnablementProof.model_validate(
                    capability.get("proof_payload")
                )
                if capability.get("proof_schema") != proof.proof_schema:
                    raise ValueError("proof_schema_mismatch")
                if capability.get("certification_ref") != proof.lifecycle_certification_ref():
                    raise ValueError("proof_ref_mismatch")
            except (TypeError, ValueError):
                blockers.append("lifecycle_mutation_enablement_proof_invalid")
    if not inspector.has_table("brc_ticket_bound_exchange_commands"):
        blockers.append("lifecycle_exchange_command_authority_missing")
    else:
        columns = {
            str(item["name"])
            for item in inspector.get_columns("brc_ticket_bound_exchange_commands")
        }
        if not REQUIRED_COMMAND_COLUMNS <= columns:
            blockers.append("lifecycle_exchange_command_authority_not_extended")
    return _result(capability, blockers)


def set_lifecycle_mutation_capability(
    conn: sa.engine.Connection,
    *,
    enabled: bool,
    certification_ref: str,
    now_ms: int,
    proof: LifecycleMutationEnablementProof | dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_ref = str(certification_ref or "").strip()
    if not normalized_ref:
        raise ValueError("lifecycle_mutation_certification_ref_required")
    if enabled:
        if proof is None:
            raise ValueError("lifecycle_mutation_enablement_proof_required")
        typed_proof = LifecycleMutationEnablementProof.model_validate(proof)
        expected_ref = typed_proof.lifecycle_certification_ref()
        if normalized_ref != expected_ref:
            raise ValueError("lifecycle_mutation_certification_ref_mismatch")
        structural = lifecycle_mutation_capability_decision(conn)
        structural_blockers = [
            blocker
            for blocker in structural["blockers"]
            if blocker != "lifecycle_mutation_capability_not_ready"
        ]
        if structural_blockers:
            raise ValueError(structural_blockers[0])
    table = sa.Table(
        "brc_runtime_capabilities_current",
        sa.MetaData(),
        autoload_with=conn,
    )
    values = {
        "capability_id": CAPABILITY_ID,
        "status": "enabled" if enabled else "disabled",
        "certification_ref": normalized_ref,
        "updated_at_ms": int(now_ms),
    }
    if "proof_schema" in table.c and "proof_payload" in table.c:
        values.update(
            {
                "proof_schema": typed_proof.proof_schema if enabled else None,
                "proof_payload": typed_proof.canonical_payload() if enabled else None,
            }
        )
    elif enabled:
        raise ValueError("lifecycle_mutation_enablement_proof_schema_missing")
    existing = conn.execute(
        sa.select(table.c.capability_id).where(table.c.capability_id == CAPABILITY_ID)
    ).first()
    if existing:
        conn.execute(
            table.update()
            .where(table.c.capability_id == CAPABILITY_ID)
            .values(**values)
        )
    else:
        conn.execute(table.insert().values(**values))
    return lifecycle_mutation_capability_decision(conn)


def _result(capability: dict[str, Any], blockers: list[str]) -> dict[str, Any]:
    return {
        "status": "ready" if not blockers else "not_ready",
        "capability_id": CAPABILITY_ID,
        "enabled": not blockers,
        "capability": capability,
        "first_blocker": blockers[0] if blockers else None,
        "blockers": blockers,
    }
