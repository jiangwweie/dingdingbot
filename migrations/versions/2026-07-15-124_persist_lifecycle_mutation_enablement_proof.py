"""Persist lifecycle mutation enablement proof and bounded outcome indexes.

Revision ID: 124
Revises: 123
Create Date: 2026-07-15
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "124"
down_revision: Union[str, None] = "123"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "brc_runtime_capabilities_current",
        sa.Column("proof_schema", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "brc_runtime_capabilities_current",
        sa.Column(
            "proof_payload",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
    )
    op.execute(
        sa.text(
            "UPDATE brc_runtime_capabilities_current "
            "SET status='disabled', "
            "certification_ref='migration-124:proof-required', "
            "proof_schema=NULL, proof_payload=NULL "
            "WHERE capability_id='ticket_lifecycle_durable_mutation'"
        )
    )
    op.create_check_constraint(
        "ck_brc_lifecycle_capability_v2_proof",
        "brc_runtime_capabilities_current",
        "capability_id <> 'ticket_lifecycle_durable_mutation' "
        "OR status <> 'enabled' OR ("
        "certification_ref LIKE 'lifecycle-cert:v2:%' "
        "AND proof_schema = 'brc.lifecycle_mutation_enablement_proof.v2' "
        "AND proof_payload IS NOT NULL)",
    )
    op.create_index(
        "idx_brc_runtime_outcome_lane_process_latest",
        "brc_runtime_process_outcomes",
        [
            "lane_identity_key",
            "process_name",
            sa.text("updated_at_ms DESC"),
            sa.text("process_outcome_id DESC"),
        ],
        unique=False,
        postgresql_where=sa.text("scope_kind = 'runtime_lane'"),
    )
    op.create_index(
        "idx_brc_runtime_outcome_canary_window",
        "brc_runtime_process_outcomes",
        [sa.text("updated_at_ms DESC"), sa.text("process_outcome_id DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_brc_runtime_outcome_canary_window",
        table_name="brc_runtime_process_outcomes",
    )
    op.drop_constraint(
        "ck_brc_lifecycle_capability_v2_proof",
        "brc_runtime_capabilities_current",
        type_="check",
    )
    op.drop_index(
        "idx_brc_runtime_outcome_lane_process_latest",
        table_name="brc_runtime_process_outcomes",
    )
    op.drop_column("brc_runtime_capabilities_current", "proof_payload")
    op.drop_column("brc_runtime_capabilities_current", "proof_schema")
