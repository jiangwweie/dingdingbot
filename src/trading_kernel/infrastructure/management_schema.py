"""Current-head management evidence tables; one normalized evidence authority."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


def define_management_tables(metadata):
    raw = sa.Table(
        "brc_management_stream_events",
        metadata,
        sa.Column("event_id", sa.String(160), primary_key=True),
        sa.Column("scope_key", sa.String(160), nullable=False),
        sa.Column("epoch_id", sa.String(160), nullable=False),
        sa.Column("receive_sequence", sa.BigInteger, nullable=False),
        sa.Column("received_at_ms", sa.BigInteger, nullable=False),
        sa.Column("exchange_event_at_ms", sa.BigInteger),
        sa.Column("message_kind", sa.String(96), nullable=False),
        sa.Column("safe_payload", JSONB, nullable=False),
        sa.Column("payload_digest", sa.String(71), nullable=False),
        sa.UniqueConstraint("scope_key", "epoch_id", "receive_sequence"),
        sa.CheckConstraint("receive_sequence>0", name="receive_sequence_positive"),
    )
    sa.Index(
        "ix_brc_management_stream_scope_time",
        raw.c.scope_key,
        raw.c.received_at_ms,
        raw.c.receive_sequence,
    )
    sa.Index('ix_brc_management_stream_child',raw.c.scope_key,raw.c.safe_payload['o']['ai'].astext)
    baseline = sa.Table(
        "brc_order_command_baselines",
        metadata,
        sa.Column("baseline_id", sa.String(160), primary_key=True),
        sa.Column(
            "command_id",
            sa.String(160),
            sa.ForeignKey("brc_exchange_commands.command_id"),
            nullable=False,
        ),
        sa.Column("scope_key", sa.String(160), nullable=False),
        sa.Column("order_namespace", sa.String(96), nullable=False),
        sa.Column("exchange_order_id", sa.String(160), nullable=False),
        sa.Column("confirmed_terms", JSONB, nullable=False),
        sa.Column("evidence_id", sa.String(160), nullable=False),
        sa.Column("confirmed_at_ms", sa.BigInteger, nullable=False),
        sa.UniqueConstraint("scope_key", "order_namespace", "exchange_order_id"),
    )
    sa.Index("ix_brc_order_baseline_command", baseline.c.command_id)
    coverage = sa.Table(
        "brc_management_coverage_events",
        metadata,
        sa.Column("coverage_event_id", sa.String(160), primary_key=True),
        sa.Column("scope_key", sa.String(160), nullable=False),
        sa.Column("epoch_id", sa.String(160), nullable=False),
        sa.Column("kind", sa.String(96), nullable=False),
        sa.Column("from_ms", sa.BigInteger, nullable=False),
        sa.Column("to_ms", sa.BigInteger, nullable=False),
        sa.Column("receive_watermark", sa.BigInteger, nullable=False),
        sa.Column("reason", sa.String(256)),
        sa.Column("occurred_at_ms", sa.BigInteger, nullable=False),
    )
    sa.Index(
        "ix_brc_management_coverage_scope_time",
        coverage.c.scope_key,
        coverage.c.from_ms,
        coverage.c.to_ms,
    )
    feed = sa.Table(
        "brc_management_feed_current",
        metadata,
        sa.Column("scope_key", sa.String(160), primary_key=True),
        sa.Column("epoch_id", sa.String(160), nullable=False),
        sa.Column("owner_worker_id", sa.String(160), nullable=False),
        sa.Column("runtime_commit", sa.String(40), nullable=False),
        sa.Column("schema_revision", sa.String(96), nullable=False),
        sa.Column("lease_until_ms", sa.BigInteger, nullable=False),
        sa.Column("connection_state", sa.String(96), nullable=False),
        sa.Column("persisted_watermark", sa.BigInteger, nullable=False),
        sa.Column("applied_watermark", sa.BigInteger, nullable=False),
        sa.Column("connected_at_ms", sa.BigInteger),
        sa.Column("last_successful_at_ms", sa.BigInteger),
        sa.Column("health_reason", sa.String(256)),
        sa.Column("revision", sa.BigInteger, nullable=False),
    )
    return raw, baseline, coverage, feed
