"""Activate the Owner-delegated SOR-LONG future-Ticket exit-policy canary.

Revision ID: 123
Revises: 122
Create Date: 2026-07-15
"""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "123"
down_revision: Union[str, None] = "122"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


POLICY_TABLE = "brc_strategy_exit_policies"
CAPABILITY_TABLE = "brc_runtime_capabilities_current"
TICKET_TABLE = "brc_action_time_tickets"
EVENT_TABLE = "brc_strategy_side_event_specs"
CAPABILITY_ID = "ticket_exit_policy_v1"
EXIT_POLICY_ID = "exit-policy:SOR-001:SOR-LONG:right-tail-v1"
EXIT_POLICY_VERSION = "2026-07-15-v1"
OWNER_APPROVAL_REF = "owner-delegated:2026-07-15:recommended-values"
RESEARCH_DECISION_HASH = (
    "a2229fbfacf3ee76017ca1cf58bbcd009bfe0fdd80d8e501851ee699f1084b8c"
)
APPROVED_AT_MS = 1784044800000

POLICY_PAYLOAD: dict[str, Any] = {
    "exit_policy_id": EXIT_POLICY_ID,
    "exit_policy_version": EXIT_POLICY_VERSION,
    "strategy_group_id": "SOR-001",
    "strategy_version": "sgv:SOR-001:v2",
    "event_spec_id": "event_spec:SOR-001:SOR-LONG:v2",
    "event_spec_version": "v2",
    "side": "long",
    "policy_family": "right_tail_runner",
    "reward_basis": "actual_entry_r",
    "take_profit_legs": [
        {
            "role": "TP1",
            "reward_multiple": "1",
            "quantity_fraction": "0.5",
            "execution_style": "limit_gtc",
            "market_fallback_allowed": False,
        }
    ],
    "tp_completion_tolerance_qty_steps": 1,
    "post_tp1_floor_rule": {
        "kind": "runner_leg_cost_adjusted_break_even",
        "trigger": "tp1_target_quantity_complete",
        "exit_fee_basis": "conservative_taker",
        "slippage_buffer_ticks": 2,
        "minimum_improvement_ticks": 2,
    },
    "invalidation_rules": [
        {
            "kind": "reference_price_cross",
            "rule_id": "SOR-LONG:native-invalidation-v1",
            "trigger": "close_below_or_equal",
            "reference_key": "opening_range_high",
        }
    ],
    "time_stop_rule": {
        "kind": "max_holding_bars",
        "max_holding_bars": 96,
    },
    "runner_rule": {
        "kind": "structural_atr",
        "timeframe": "15m",
        "structure_rule": "confirmed_higher_low",
        "structure_window_bars": 4,
        "atr_period": 14,
        "atr_buffer_multiple": "0.5",
        "minimum_improvement_ticks": 2,
    },
}
POLICY_HASH = "324b2be50b3e1f020837e0f4687e76339a52dd757b272d4336b20de196bef02b"
POLICY_PAYLOAD["payload_hash"] = POLICY_HASH


def upgrade() -> None:
    conn = op.get_bind()
    if not sa.inspect(conn).has_table(POLICY_TABLE):
        raise RuntimeError("ticket_exit_policy_table_missing_before_canary")
    if not sa.inspect(conn).has_table(CAPABILITY_TABLE):
        raise RuntimeError("runtime_capability_table_missing_before_canary")
    if not sa.inspect(conn).has_table(EVENT_TABLE):
        raise RuntimeError("event_spec_table_missing_before_canary")
    if _canonical_hash(POLICY_PAYLOAD) != POLICY_HASH:
        raise RuntimeError("approved_exit_policy_hash_mismatch")

    policies = sa.Table(POLICY_TABLE, sa.MetaData(), autoload_with=conn)
    capabilities = sa.Table(CAPABILITY_TABLE, sa.MetaData(), autoload_with=conn)
    events = sa.Table(EVENT_TABLE, sa.MetaData(), autoload_with=conn)
    event = conn.execute(
        sa.select(events).where(
            events.c.event_spec_id == POLICY_PAYLOAD["event_spec_id"],
            events.c.strategy_group_version_id == POLICY_PAYLOAD["strategy_version"],
            events.c.event_spec_version == POLICY_PAYLOAD["event_spec_version"],
            events.c.side == POLICY_PAYLOAD["side"],
            events.c.status == "current",
        )
    ).mappings().first()
    if event is None:
        raise RuntimeError("approved_exit_policy_event_spec_not_current")
    existing_scope = list(
        conn.execute(
            sa.select(policies).where(
                policies.c.strategy_group_id == POLICY_PAYLOAD["strategy_group_id"],
                policies.c.strategy_version == POLICY_PAYLOAD["strategy_version"],
                policies.c.event_spec_id == POLICY_PAYLOAD["event_spec_id"],
                policies.c.event_spec_version == POLICY_PAYLOAD["event_spec_version"],
                policies.c.side == POLICY_PAYLOAD["side"],
                policies.c.status == "current",
            )
        ).mappings()
    )
    if existing_scope:
        if len(existing_scope) != 1 or not _is_exact_policy(existing_scope[0]):
            raise RuntimeError("conflicting_current_exit_policy_for_canary_scope")
    else:
        conn.execute(
            policies.insert().values(
                exit_policy_id=EXIT_POLICY_ID,
                exit_policy_version=EXIT_POLICY_VERSION,
                strategy_group_id=POLICY_PAYLOAD["strategy_group_id"],
                strategy_version=POLICY_PAYLOAD["strategy_version"],
                event_spec_id=POLICY_PAYLOAD["event_spec_id"],
                event_spec_version=POLICY_PAYLOAD["event_spec_version"],
                side=POLICY_PAYLOAD["side"],
                policy_family=POLICY_PAYLOAD["policy_family"],
                policy_payload=POLICY_PAYLOAD,
                payload_hash=POLICY_HASH,
                status="current",
                approved_by=OWNER_APPROVAL_REF,
                approved_at_ms=APPROVED_AT_MS,
                created_at_ms=APPROVED_AT_MS,
            )
        )

    capability = conn.execute(
        sa.select(capabilities).where(capabilities.c.capability_id == CAPABILITY_ID)
    ).mappings().first()
    if capability is None:
        raise RuntimeError("ticket_exit_policy_capability_missing_before_canary")
    conn.execute(
        capabilities.update()
        .where(capabilities.c.capability_id == CAPABILITY_ID)
        .values(
            status="enabled",
            certification_ref=(
                f"migration-123:sor-long-canary:{POLICY_HASH}:"
                f"decision:{RESEARCH_DECISION_HASH}"
            ),
            updated_at_ms=APPROVED_AT_MS,
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    policies = sa.Table(POLICY_TABLE, sa.MetaData(), autoload_with=conn)
    capabilities = sa.Table(CAPABILITY_TABLE, sa.MetaData(), autoload_with=conn)
    if sa.inspect(conn).has_table(TICKET_TABLE):
        tickets = sa.Table(TICKET_TABLE, sa.MetaData(), autoload_with=conn)
        active_count = conn.execute(
            sa.select(sa.func.count())
            .select_from(tickets)
            .where(
                tickets.c.exit_policy_id == EXIT_POLICY_ID,
                tickets.c.exit_policy_version == EXIT_POLICY_VERSION,
            )
        ).scalar_one()
        if active_count:
            raise RuntimeError("cannot_downgrade_active_exit_policy_ticket")
    conn.execute(
        capabilities.update()
        .where(capabilities.c.capability_id == CAPABILITY_ID)
        .values(
            status="disabled",
            certification_ref="migration-123-downgrade:future-ticket-canary-disabled",
            updated_at_ms=APPROVED_AT_MS,
        )
    )
    conn.execute(
        policies.delete().where(
            policies.c.exit_policy_id == EXIT_POLICY_ID,
            policies.c.exit_policy_version == EXIT_POLICY_VERSION,
        )
    )


def _is_exact_policy(row: Any) -> bool:
    payload = row["policy_payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return (
        str(row["exit_policy_id"]) == EXIT_POLICY_ID
        and str(row["exit_policy_version"]) == EXIT_POLICY_VERSION
        and str(row["payload_hash"]) == POLICY_HASH
        and payload == POLICY_PAYLOAD
    )


def _canonical_hash(value: Any) -> str:
    def canonical(item: Any) -> Any:
        if isinstance(item, dict):
            return {
                str(key): canonical(child)
                for key, child in sorted(item.items(), key=lambda pair: str(pair[0]))
                if str(key) != "payload_hash"
            }
        if isinstance(item, (list, tuple)):
            return [canonical(child) for child in item]
        return item

    encoded = json.dumps(
        canonical(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(encoded.encode("utf-8")).hexdigest()
