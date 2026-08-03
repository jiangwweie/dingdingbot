"""Add portfolio-admission observability projections."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert

revision: str = "0003_portfolio_admission_observability"
down_revision: str | None = "0002_sor_v3_strategy_group_capacity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ID = sa.String(160)
SHORT_TEXT = sa.String(96)
LONG_TEXT = sa.String(512)
MONEY = sa.Numeric(38, 18)
REGISTRY_SEMANTIC_HASH = (
    "sha256:97a5214e5d4b94726ad6b4e9dc91f95ba8964d34de6b1c73d09f814578152723"
)

_REGISTRY_VNEXT_EVENTS = (
    {
        "strategy_group_id": "CPM-RO-001",
        "source_strategy_version_id": "sgv:CPM-RO-001:v2",
        "strategy_version_id": "sgv:CPM-RO-001:v3",
        "version": 3,
        "event_spec_id": "event_spec:CPM-RO-001:CPM-LONG:v3",
        "source_event_spec_id": "event_spec:CPM-RO-001:CPM-LONG:v2",
        "event_id": "CPM-LONG",
        "position_side": "long",
        "timeframe": "1h",
        "freshness_window_ms": 3_600_000,
        "protection_fact_id": "fact:pullback_low_reference:v1",
        "exit_policy_id": "exit-policy:CPM-RO-001:CPM-LONG:portfolio-admission-v1",
        "exit_policy_version": "2026-07-22-v1",
        "event_semantic_hash": (
            "sha256:9b83f84c170686b8bb1aaef886fe5b364580f6bb91cfacfdaae0a2665eb60bb2"
        ),
        "exit_policy_semantic_hash": (
            "sha256:aaf031d95771068434c03ceea83e770bd302c7c1073139e0d16fc02e2148b053"
        ),
        "runner_reference_fact": "pullback_low_reference",
        "runner_structure_rule": "confirmed_higher_low",
        "time_stop_bars": None,
        "facts": (
            ("fact:htf_trend_intact:v1", "htf_trend_intact", "boolean", 3_600_000, "condition"),
            ("fact:reclaim_confirmed:v1", "reclaim_confirmed", "boolean", 3_600_000, "condition"),
            ("fact:pullback_low_reference:v1", "pullback_low_reference", "decimal", 3_600_000, "protection_reference"),
        ),
    },
    {
        "strategy_group_id": "MPG-001",
        "source_strategy_version_id": "sgv:MPG-001:v2",
        "strategy_version_id": "sgv:MPG-001:v3",
        "version": 3,
        "event_spec_id": "event_spec:MPG-001:MPG-LONG:v3",
        "source_event_spec_id": "event_spec:MPG-001:MPG-LONG:v2",
        "event_id": "MPG-LONG",
        "position_side": "long",
        "timeframe": "1h",
        "freshness_window_ms": 3_600_000,
        "protection_fact_id": "fact:momentum_floor_reference:v1",
        "exit_policy_id": "exit-policy:MPG-001:MPG-LONG:portfolio-admission-v1",
        "exit_policy_version": "2026-07-22-v1",
        "event_semantic_hash": (
            "sha256:4a5de575897430b7345c47bb7d30669aeb4b489af4fcb31af5bb0309d1c00a34"
        ),
        "exit_policy_semantic_hash": (
            "sha256:e36d5c92db351f2dbfe480c326e57dfae13f258f11bc9c04b9fe785c37ea1637"
        ),
        "runner_reference_fact": "momentum_floor_reference",
        "runner_structure_rule": "confirmed_higher_low",
        "time_stop_bars": None,
        "facts": (
            ("fact:momentum_persistence_confirmed:v1", "momentum_persistence_confirmed", "boolean", 3_600_000, "condition"),
            ("fact:leader_strength_confirmed:v1", "leader_strength_confirmed", "boolean", 3_600_000, "condition"),
            ("fact:momentum_floor_reference:v1", "momentum_floor_reference", "decimal", 3_600_000, "protection_reference"),
        ),
    },
    {
        "strategy_group_id": "MI-001",
        "source_strategy_version_id": "sgv:MI-001:v2",
        "strategy_version_id": "sgv:MI-001:v3",
        "version": 3,
        "event_spec_id": "event_spec:MI-001:MI-LONG:v3",
        "source_event_spec_id": "event_spec:MI-001:MI-LONG:v2",
        "event_id": "MI-LONG",
        "position_side": "long",
        "timeframe": "1h",
        "freshness_window_ms": 3_600_000,
        "protection_fact_id": "fact:impulse_invalidation_reference:v1",
        "exit_policy_id": "exit-policy:MI-001:MI-LONG:portfolio-admission-v1",
        "exit_policy_version": "2026-07-22-v1",
        "event_semantic_hash": (
            "sha256:2d078dc0b4491a3a8ca46b31d232e8f9f15519b533e0bc9c3702e6cb84557a7c"
        ),
        "exit_policy_semantic_hash": (
            "sha256:70695ea6bcecbbc65411c271e11ab3546ff25bdd07953f9291c23d4c7cc9e3ad"
        ),
        "runner_reference_fact": "impulse_invalidation_reference",
        "runner_structure_rule": "confirmed_higher_low",
        "time_stop_bars": None,
        "facts": (
            ("fact:impulse_confirmed:v1", "impulse_confirmed", "boolean", 3_600_000, "condition"),
            ("fact:relative_strength_confirmed:v1", "relative_strength_confirmed", "boolean", 3_600_000, "condition"),
            ("fact:impulse_invalidation_reference:v1", "impulse_invalidation_reference", "decimal", 3_600_000, "protection_reference"),
        ),
    },
    {
        "strategy_group_id": "SOR-001",
        "source_strategy_version_id": "sgv:SOR-001:v3",
        "strategy_version_id": "sgv:SOR-001:v4",
        "version": 4,
        "event_spec_id": "event_spec:SOR-001:SOR-LONG:v4",
        "source_event_spec_id": "event_spec:SOR-001:SOR-LONG:v3",
        "event_id": "SOR-LONG",
        "position_side": "long",
        "timeframe": "15m",
        "freshness_window_ms": 900_000,
        "protection_fact_id": "fact:opening_range_low_reference_v3:v3",
        "exit_policy_id": "exit-policy:SOR-001:SOR-LONG:portfolio-admission-v1",
        "exit_policy_version": "2026-07-31-sor-v3",
        "event_semantic_hash": (
            "sha256:098e0367328e1041be4ce1ed570f5a72a475a2898191c6f8831e49d0b91de496"
        ),
        "exit_policy_semantic_hash": (
            "sha256:7632a2ce5f7618fcc547cac4c2daf6c6816390449abbf13ae21dc6e8bd2305b6"
        ),
        "runner_reference_fact": "opening_range_low_reference_v3",
        "runner_structure_rule": "confirmed_higher_low",
        "time_stop_bars": 96,
        "facts": (
            ("fact:opening_range_defined_v3:v3", "opening_range_defined_v3", "boolean", 900_000, "condition"),
            ("fact:breakout_edge_crossed_v3:v3", "breakout_edge_crossed_v3", "boolean", 900_000, "condition"),
            ("fact:opening_range_high_reference_v3:v3", "opening_range_high_reference_v3", "decimal", 900_000, "lifecycle_reference"),
            ("fact:opening_range_low_reference_v3:v3", "opening_range_low_reference_v3", "decimal", 900_000, "protection_reference"),
            ("fact:session_start_ms_v3:v3", "session_start_ms_v3", "decimal", 900_000, "identity_reference"),
            ("fact:session_end_ms_v3:v3", "session_end_ms_v3", "decimal", 900_000, "lifecycle_reference"),
        ),
    },
    {
        "strategy_group_id": "SOR-001",
        "source_strategy_version_id": "sgv:SOR-001:v3",
        "strategy_version_id": "sgv:SOR-001:v4",
        "version": 4,
        "event_spec_id": "event_spec:SOR-001:SOR-SHORT:v4",
        "source_event_spec_id": "event_spec:SOR-001:SOR-SHORT:v3",
        "event_id": "SOR-SHORT",
        "position_side": "short",
        "timeframe": "15m",
        "freshness_window_ms": 900_000,
        "protection_fact_id": "fact:opening_range_high_reference_v3:v3",
        "exit_policy_id": "exit-policy:SOR-001:SOR-SHORT:portfolio-admission-v1",
        "exit_policy_version": "2026-07-31-sor-v3",
        "event_semantic_hash": (
            "sha256:bbb50f9b1348b0cdec1834c482c63dd5713b6d6354ff4934af92b429b87698c9"
        ),
        "exit_policy_semantic_hash": (
            "sha256:0b344d752855c951499933794167eeb797cacdf9efecc41ffd802eeec07b9a3a"
        ),
        "runner_reference_fact": "opening_range_high_reference_v3",
        "runner_structure_rule": "confirmed_lower_high",
        "time_stop_bars": 96,
        "facts": (
            ("fact:opening_range_defined_v3:v3", "opening_range_defined_v3", "boolean", 900_000, "condition"),
            ("fact:breakdown_edge_crossed_v3:v3", "breakdown_edge_crossed_v3", "boolean", 900_000, "condition"),
            ("fact:opening_range_low_reference_v3:v3", "opening_range_low_reference_v3", "decimal", 900_000, "lifecycle_reference"),
            ("fact:opening_range_high_reference_v3:v3", "opening_range_high_reference_v3", "decimal", 900_000, "protection_reference"),
            ("fact:session_start_ms_v3:v3", "session_start_ms_v3", "decimal", 900_000, "identity_reference"),
            ("fact:session_end_ms_v3:v3", "session_end_ms_v3", "decimal", 900_000, "lifecycle_reference"),
        ),
    },
    {
        "strategy_group_id": "BRF2-001",
        "source_strategy_version_id": "sgv:BRF2-001:v2",
        "strategy_version_id": "sgv:BRF2-001:v3",
        "version": 3,
        "event_spec_id": "event_spec:BRF2-001:BRF2-SHORT:v3",
        "source_event_spec_id": "event_spec:BRF2-001:BRF2-SHORT:v2",
        "event_id": "BRF2-SHORT",
        "position_side": "short",
        "timeframe": "1h",
        "freshness_window_ms": 3_600_000,
        "protection_fact_id": "fact:rally_high_reference:v1",
        "exit_policy_id": "exit-policy:BRF2-001:BRF2-SHORT:portfolio-admission-v1",
        "exit_policy_version": "2026-07-22-v1",
        "event_semantic_hash": (
            "sha256:94a6ef6b3ae3db0e01d780d3f6d1abea8c27264043657ab6cfcd7ef580d91bb4"
        ),
        "exit_policy_semantic_hash": (
            "sha256:746632f69e3640b6e5604580d25fe872af2a55a9ebdd3a6a804dc034d25ff639"
        ),
        "runner_reference_fact": "rally_high_reference",
        "runner_structure_rule": "confirmed_lower_high",
        "time_stop_bars": None,
        "facts": (
            ("fact:rally_failure_confirmed:v1", "rally_failure_confirmed", "boolean", 3_600_000, "condition"),
            ("fact:short_side_not_disabled:v1", "short_side_not_disabled", "boolean", 3_600_000, "condition"),
            ("fact:rally_high_reference:v1", "rally_high_reference", "decimal", 3_600_000, "protection_reference"),
            ("fact:strong_uptrend_disable:v1", "strong_uptrend_disable", "boolean", 3_600_000, "disable"),
        ),
    },
)


def upgrade() -> None:
    """Add the rising-edge Episode current projection."""

    _install_registry_vnext()
    _upgrade_portfolio_admission_policy_v4()

    op.create_table(
        "brc_exposure_episode_current",
        sa.Column("episode_domain_key", ID, nullable=False),
        sa.Column("event_spec_id", ID, nullable=False),
        sa.Column("exchange_instrument_id", ID, nullable=False),
        sa.Column("position_side", SHORT_TEXT, nullable=False),
        sa.Column("episode_policy", SHORT_TEXT, nullable=False),
        sa.Column("state", SHORT_TEXT, nullable=False),
        sa.Column("exposure_episode_id", ID, nullable=True),
        sa.Column("triggered_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("rearmed_at_ms", sa.BigInteger(), nullable=True),
        sa.Column("last_observed_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("projection_version", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint(
            "episode_domain_key",
            name="pk_brc_exposure_episode_current",
        ),
        sa.ForeignKeyConstraint(
            ["event_spec_id"],
            ["brc_event_specs.event_spec_id"],
            name="fk_brc_episode_event_spec",
        ),
        sa.ForeignKeyConstraint(
            ["exchange_instrument_id"],
            ["brc_instruments.exchange_instrument_id"],
            name="fk_brc_episode_instrument",
        ),
        sa.CheckConstraint(
            "position_side IN ('long', 'short')",
            name="ck_brc_episode_position_side",
        ),
        sa.CheckConstraint(
            "episode_policy = 'rising_edge'",
            name="ck_brc_episode_policy",
        ),
        sa.CheckConstraint(
            "state IN ('armed', 'triggered')",
            name="ck_brc_episode_state",
        ),
        sa.CheckConstraint(
            "projection_version > 0 AND last_observed_at_ms > 0",
            name="ck_brc_episode_version_time",
        ),
        sa.CheckConstraint(
            "rearmed_at_ms IS NULL OR rearmed_at_ms > 0",
            name="ck_brc_episode_rearmed_time",
        ),
        sa.CheckConstraint(
            "(state = 'triggered' AND exposure_episode_id IS NOT NULL "
            "AND triggered_at_ms IS NOT NULL AND triggered_at_ms > 0) OR "
            "(state = 'armed' AND exposure_episode_id IS NULL "
            "AND triggered_at_ms IS NULL)",
            name="ck_brc_episode_state_shape",
        ),
    )
    _create_admission_decisions()
    _create_shadow_outcomes()


def _install_registry_vnext() -> None:
    """Replace only the exact deployed Registry pointers and retain history."""

    bind = op.get_bind()
    groups_table = sa.table(
        "brc_strategy_groups",
        sa.column("strategy_group_id", ID),
        sa.column("display_name", LONG_TEXT),
        sa.column("active_version_id", ID),
        sa.column("status", SHORT_TEXT),
        sa.column("updated_at_ms", sa.BigInteger()),
    )
    versions_table = sa.table(
        "brc_strategy_versions",
        sa.column("strategy_version_id", ID),
        sa.column("strategy_group_id", ID),
        sa.column("version", sa.Integer()),
        sa.column("semantics", JSONB()),
        sa.column("status", SHORT_TEXT),
        sa.column("created_at_ms", sa.BigInteger()),
    )
    events_table = sa.table(
        "brc_event_specs",
        sa.column("event_spec_id", ID),
        sa.column("strategy_version_id", ID),
        sa.column("event_id", SHORT_TEXT),
        sa.column("position_side", SHORT_TEXT),
        sa.column("timeframe", SHORT_TEXT),
        sa.column("freshness_window_ms", sa.BigInteger()),
        sa.column("event_time_authority", SHORT_TEXT),
        sa.column("entry_order_type", SHORT_TEXT),
        sa.column("protection_reference_fact_definition_id", ID),
        sa.column("exit_policy_id", ID),
        sa.column("execution_semantics", JSONB()),
        sa.column("status", SHORT_TEXT),
        sa.column("created_at_ms", sa.BigInteger()),
    )
    policies_table = sa.table(
        "brc_exit_policies",
        sa.column("exit_policy_id", ID),
        sa.column("exit_policy_version", SHORT_TEXT),
        sa.column("event_spec_id", ID),
        sa.column("position_side", SHORT_TEXT),
        sa.column("policy", JSONB()),
        sa.column("semantic_hash", LONG_TEXT),
        sa.column("status", SHORT_TEXT),
        sa.column("created_at_ms", sa.BigInteger()),
    )
    facts_table = sa.table(
        "brc_fact_definitions",
        sa.column("fact_definition_id", ID),
        sa.column("fact_name", SHORT_TEXT),
        sa.column("value_type", SHORT_TEXT),
        sa.column("freshness_ms", sa.BigInteger()),
        sa.column("validation", JSONB()),
    )
    event_facts_table = sa.table(
        "brc_event_required_facts",
        sa.column("event_spec_id", ID),
        sa.column("fact_definition_id", ID),
        sa.column("role", SHORT_TEXT),
        sa.column("required", sa.Boolean()),
    )

    group_rows = (
        bind.execute(
            sa.select(
                groups_table.c.strategy_group_id,
                groups_table.c.active_version_id,
                groups_table.c.status,
                groups_table.c.updated_at_ms,
            ).order_by(groups_table.c.strategy_group_id)
        )
    ).mappings().all()
    if not group_rows:
        return

    expected_source_pointers = {
        "BRF2-001": "sgv:BRF2-001:v2",
        "CPM-RO-001": "sgv:CPM-RO-001:v2",
        "MI-001": "sgv:MI-001:v2",
        "MPG-001": "sgv:MPG-001:v2",
        "SOR-001": "sgv:SOR-001:v3",
    }
    actual_source_pointers = {
        str(row["strategy_group_id"]): str(row["active_version_id"] or "")
        for row in group_rows
        if row["status"] == "active"
    }
    if actual_source_pointers != expected_source_pointers:
        raise RuntimeError("0003 requires the exact certified Registry source")

    source_version_ids = set(expected_source_pointers.values())
    active_version_ids = {
        str(value)
        for value in bind.execute(
            sa.select(versions_table.c.strategy_version_id).where(
                versions_table.c.status == "active"
            )
        ).scalars()
    }
    if active_version_ids != source_version_ids:
        raise RuntimeError("0003 requires the exact active Registry versions")

    source_event_ids = {
        str(event["source_event_spec_id"]) for event in _REGISTRY_VNEXT_EVENTS
    }
    active_source_events = {
        str(value)
        for value in bind.execute(
            sa.select(events_table.c.event_spec_id).where(
                events_table.c.strategy_version_id.in_(source_version_ids),
                events_table.c.status == "active",
            )
        ).scalars()
    }
    if active_source_events != source_event_ids:
        raise RuntimeError("0003 requires the exact active Registry Events")

    active_source_policy_events = {
        str(value)
        for value in bind.execute(
            sa.select(policies_table.c.event_spec_id).where(
                policies_table.c.event_spec_id.in_(source_event_ids),
                policies_table.c.status == "active",
            )
        ).scalars()
    }
    if active_source_policy_events != source_event_ids:
        raise RuntimeError("0003 requires exact active source ExitPolicies")

    source_times = {
        str(row["strategy_group_id"]): int(row["updated_at_ms"])
        for row in group_rows
    }
    version_event_ids: dict[str, list[str]] = {}
    version_groups: dict[str, tuple[str, int]] = {}
    fact_rows: dict[str, dict[str, object]] = {}
    event_fact_rows: list[dict[str, object]] = []
    event_rows: list[dict[str, object]] = []
    policy_rows: list[dict[str, object]] = []
    for event in _REGISTRY_VNEXT_EVENTS:
        strategy_version_id = str(event["strategy_version_id"])
        strategy_group_id = str(event["strategy_group_id"])
        event_spec_id = str(event["event_spec_id"])
        version_event_ids.setdefault(strategy_version_id, []).append(event_spec_id)
        version_groups[strategy_version_id] = (
            strategy_group_id,
            int(event["version"]),
        )
        created_at_ms = source_times[strategy_group_id]
        event_rows.append(
            {
                "event_spec_id": event_spec_id,
                "strategy_version_id": strategy_version_id,
                "event_id": event["event_id"],
                "position_side": event["position_side"],
                "timeframe": event["timeframe"],
                "freshness_window_ms": event["freshness_window_ms"],
                "event_time_authority": "trigger_candle_close_time_ms",
                "entry_order_type": "market",
                "protection_reference_fact_definition_id": event[
                    "protection_fact_id"
                ],
                "exit_policy_id": event["exit_policy_id"],
                "execution_semantics": {
                    "event_semantic_hash": event["event_semantic_hash"],
                    "signal_grade": "trial_grade_signal",
                    "source": "committed_strategy_registry_contract",
                },
                "status": "active",
                "created_at_ms": created_at_ms,
            }
        )
        policy_rows.append(
            {
                "exit_policy_id": event["exit_policy_id"],
                "exit_policy_version": event["exit_policy_version"],
                "event_spec_id": event_spec_id,
                "position_side": event["position_side"],
                "policy": _exit_policy_payload(event),
                "semantic_hash": event["exit_policy_semantic_hash"],
                "status": "active",
                "created_at_ms": created_at_ms,
            }
        )
        for fact_id, fact_name, value_type, freshness_ms, role in event["facts"]:
            fact_rows[str(fact_id)] = {
                "fact_definition_id": fact_id,
                "fact_name": fact_name,
                "value_type": value_type,
                "freshness_ms": freshness_ms,
                "validation": {
                    "satisfaction": (
                        "positive_decimal"
                        if value_type == "decimal"
                        else "boolean"
                    )
                },
            }
            event_fact_rows.append(
                {
                    "event_spec_id": event_spec_id,
                    "fact_definition_id": fact_id,
                    "role": role,
                    "required": True,
                }
            )

    bind.execute(
        pg_insert(facts_table)
        .values(list(fact_rows.values()))
        .on_conflict_do_nothing(index_elements=["fact_definition_id"])
    )
    stored_facts = {
        str(row["fact_definition_id"]): row
        for row in (
            bind.execute(
                sa.select(facts_table).where(
                    facts_table.c.fact_definition_id.in_(fact_rows)
                )
            )
        ).mappings()
    }
    for fact_id, expected in fact_rows.items():
        stored = stored_facts.get(fact_id)
        if stored is None or any(
            stored[key] != expected[key]
            for key in (
                "fact_name",
                "value_type",
                "freshness_ms",
                "validation",
            )
        ):
            raise RuntimeError(f"0003 Registry Fact conflicts: {fact_id}")

    version_rows = [
        {
            "strategy_version_id": strategy_version_id,
            "strategy_group_id": strategy_group_id,
            "version": version,
            "semantics": {
                "event_spec_ids": sorted(version_event_ids[strategy_version_id]),
                "registry_semantic_hash": REGISTRY_SEMANTIC_HASH,
                "source": "committed_strategy_registry_contract",
            },
            "status": "active",
            "created_at_ms": source_times[strategy_group_id],
        }
        for strategy_version_id, (strategy_group_id, version) in sorted(
            version_groups.items()
        )
    ]
    bind.execute(sa.insert(versions_table), version_rows)
    bind.execute(sa.insert(events_table), event_rows)
    bind.execute(sa.insert(policies_table), policy_rows)
    bind.execute(sa.insert(event_facts_table), event_fact_rows)

    bind.execute(
        sa.update(policies_table)
        .where(policies_table.c.event_spec_id.in_(source_event_ids))
        .values(status="retired")
    )
    bind.execute(
        sa.update(events_table)
        .where(events_table.c.event_spec_id.in_(source_event_ids))
        .values(status="retired")
    )
    bind.execute(
        sa.update(versions_table)
        .where(versions_table.c.strategy_version_id.in_(source_version_ids))
        .values(status="retired")
    )
    target_pointers = {
        strategy_group_id: strategy_version_id
        for strategy_version_id, (strategy_group_id, _) in version_groups.items()
    }
    display_names = {
        "BRF2-001": "BRF2 bear rally failure",
        "CPM-RO-001": "CPM reclaim pullback recovery",
        "MI-001": "MI relative strength impulse",
        "MPG-001": "MPG momentum persistence",
        "SOR-001": "SOR opening range breakout and breakdown",
    }
    for strategy_group_id, strategy_version_id in target_pointers.items():
        bind.execute(
            sa.update(groups_table)
            .where(groups_table.c.strategy_group_id == strategy_group_id)
            .values(
                display_name=display_names[strategy_group_id],
                active_version_id=strategy_version_id,
            )
        )


def _exit_policy_payload(event: dict[str, object]) -> dict[str, object]:
    time_stop_bars = event["time_stop_bars"]
    return {
        "exit_policy_id": event["exit_policy_id"],
        "exit_policy_version": event["exit_policy_version"],
        "event_spec_id": event["event_spec_id"],
        "event_id": event["event_id"],
        "position_side": event["position_side"],
        "tp1": {
            "reward_multiple": "1",
            "quantity_fraction": "0.5",
            "execution_style": "limit_gtc",
            "market_fallback_allowed": False,
        },
        "break_even_floor": {
            "exit_fee_basis": "conservative_taker",
            "slippage_buffer_ticks": 2,
            "minimum_improvement_ticks": 2,
        },
        "runner": {
            "kind": "structural_atr",
            "timeframe": event["timeframe"],
            "structure_rule": event["runner_structure_rule"],
            "structure_reference_fact": event["runner_reference_fact"],
            "structure_window_bars": 4,
            "atr_period": 14,
            "atr_buffer_multiple": "0.5",
            "minimum_improvement_ticks": 2,
        },
        "time_stop": (
            None
            if time_stop_bars is None
            else {"max_holding_bars": time_stop_bars}
        ),
    }


def _upgrade_portfolio_admission_policy_v4() -> None:
    """Extend the un-deployed 0003 head with current Policy v4 lineage."""

    op.add_column(
        "brc_owner_policy_current",
        sa.Column(
            "family_ticket_limits",
            JSONB(),
            nullable=True,
        ),
    )
    op.add_column(
        "brc_owner_policy_current",
        sa.Column(
            "directional_stop_risk_limit_fraction",
            MONEY,
            nullable=True,
        ),
    )
    op.add_column(
        "brc_owner_policy_current",
        sa.Column(
            "min_materialization_ratio",
            MONEY,
            nullable=True,
        ),
    )
    op.alter_column(
        "brc_owner_policy_current",
        "max_strategy_group_concurrent_tickets",
        nullable=True,
        server_default=None,
    )
    _backfill_exact_v3_policy_to_v4()
    op.alter_column(
        "brc_owner_policy_current",
        "family_ticket_limits",
        nullable=False,
        server_default=None,
    )
    op.alter_column(
        "brc_owner_policy_current",
        "directional_stop_risk_limit_fraction",
        nullable=False,
        server_default=None,
    )
    op.alter_column(
        "brc_owner_policy_current",
        "min_materialization_ratio",
        nullable=False,
        server_default=None,
    )
    for column_name in (
        "active_strategy_group_ticket_count_at_claim",
        "max_strategy_group_concurrent_tickets",
        "remaining_strategy_group_slots_at_claim",
    ):
        op.alter_column(
            "brc_capacity_claims",
            column_name,
            nullable=True,
            server_default=None,
        )
    for table_name in ("brc_capacity_claims", "brc_trade_tickets"):
        op.add_column(
            table_name,
            sa.Column("exposure_family", SHORT_TEXT, nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("active_family_ticket_count_at_claim", sa.Integer(), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("family_ticket_limit", sa.Integer(), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("directional_risk_at_stop_at_claim", MONEY, nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("directional_stop_risk_limit_fraction", MONEY, nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("min_materialization_ratio", MONEY, nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column("minimum_stop_risk_budget", MONEY, nullable=True),
        )
    _backfill_terminal_exposure_families()
    op.create_index(
        "ix_brc_trade_tickets_active_family",
        "brc_trade_tickets",
        ["venue_id", "account_id", "exposure_family", "terminal_at_ms"],
    )
    op.create_index(
        "ix_brc_trade_tickets_active_directional_risk",
        "brc_trade_tickets",
        ["venue_id", "account_id", "position_side", "terminal_at_ms"],
    )


def _backfill_exact_v3_policy_to_v4() -> None:
    """Migrate only the exact former deployed capacity profile once."""

    op.execute(
        sa.text(
            """
            UPDATE brc_owner_policy_current
               SET policy_version = 4,
                   new_entry_submit_enabled = false,
                   max_strategy_group_concurrent_tickets = NULL,
                   family_ticket_limits =
                       '{"long_continuation": 1, "opening_range": 2, "rally_failure_short": 1}'::jsonb,
                   max_ticket_stop_risk_fraction = 0.02,
                   max_ticket_initial_margin_fraction = 0.30,
                   directional_stop_risk_limit_fraction = 0.04,
                   min_materialization_ratio = 0.50,
                   scope = jsonb_set(
                       scope,
                       '{allowed_event_spec_ids}',
                       '["event_spec:BRF2-001:BRF2-SHORT:v3",'
                       ' "event_spec:CPM-RO-001:CPM-LONG:v3",'
                       ' "event_spec:MI-001:MI-LONG:v3",'
                       ' "event_spec:MPG-001:MPG-LONG:v3",'
                       ' "event_spec:SOR-001:SOR-LONG:v4",'
                       ' "event_spec:SOR-001:SOR-SHORT:v4"]'::jsonb
                   )
             WHERE family_ticket_limits IS NULL
               AND directional_stop_risk_limit_fraction IS NULL
               AND min_materialization_ratio IS NULL
               AND policy_version = 3
               AND enabled = true
               AND max_concurrent_tickets = 3
               AND max_strategy_group_concurrent_tickets = 2
               AND max_ticket_stop_risk_fraction = 0.03
               AND max_gross_stop_risk_fraction = 0.06
               AND max_ticket_initial_margin_fraction = 0.45
               AND max_gross_initial_margin_utilization = 0.90
               AND max_leverage = 10
               AND supported_margin_mode = 'cross'
               AND scope ->> 'runtime_profile_id' = 'tiny-live-v1'
               AND scope -> 'allowed_event_spec_ids' =
                   '["event_spec:BRF2-001:BRF2-SHORT:v2",'
                   ' "event_spec:CPM-RO-001:CPM-LONG:v2",'
                   ' "event_spec:MI-001:MI-LONG:v2",'
                   ' "event_spec:MPG-001:MPG-LONG:v2",'
                   ' "event_spec:SOR-001:SOR-LONG:v3",'
                   ' "event_spec:SOR-001:SOR-SHORT:v3"]'::jsonb
            """
        )
    )
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                      FROM brc_owner_policy_current
                     WHERE family_ticket_limits IS NULL
                        OR directional_stop_risk_limit_fraction IS NULL
                        OR min_materialization_ratio IS NULL
                ) THEN
                    RAISE EXCEPTION
                        '0003 requires the exact certified Policy v3 source';
                END IF;
            END
            $$;
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO brc_owner_policy_events (
                owner_policy_event_id,
                owner_policy_id,
                policy_version,
                operation,
                payload,
                created_at_ms
            )
            SELECT concat(
                       'policy-event', chr(58), owner_policy_id, chr(58), 'v4'
                   ),
                   owner_policy_id,
                   4,
                   'compatible_upgrade_portfolio_admission_v4',
                   jsonb_build_object(
                       'policy_version', policy_version,
                       'enabled', enabled,
                       'new_entry_submit_enabled', new_entry_submit_enabled,
                       'priority_rank', priority_rank,
                       'max_concurrent_tickets', max_concurrent_tickets,
                       'family_ticket_limits', family_ticket_limits,
                       'max_ticket_stop_risk_fraction',
                           max_ticket_stop_risk_fraction::text,
                       'max_gross_stop_risk_fraction',
                           max_gross_stop_risk_fraction::text,
                       'max_ticket_initial_margin_fraction',
                           max_ticket_initial_margin_fraction::text,
                       'max_gross_initial_margin_utilization',
                           max_gross_initial_margin_utilization::text,
                       'directional_stop_risk_limit_fraction',
                           directional_stop_risk_limit_fraction::text,
                       'min_materialization_ratio',
                           min_materialization_ratio::text,
                       'max_leverage', max_leverage,
                       'supported_margin_mode', supported_margin_mode,
                       'post_stop_stress_multiple',
                           post_stop_stress_multiple::text,
                       'max_post_fill_stop_risk_overrun_fraction',
                           max_post_fill_stop_risk_overrun_fraction::text,
                       'scope', scope
                   ),
                   updated_at_ms
              FROM brc_owner_policy_current
             WHERE policy_version = 4
               AND new_entry_submit_enabled = false
            """
        )
    )


def _backfill_terminal_exposure_families() -> None:
    """Recover only Family semantics derivable from historical Event identity."""

    family_case = """
        CASE event_specs.event_id
            WHEN 'CPM-LONG' THEN 'long_continuation'
            WHEN 'MPG-LONG' THEN 'long_continuation'
            WHEN 'MI-LONG' THEN 'long_continuation'
            WHEN 'SOR-LONG' THEN 'opening_range'
            WHEN 'SOR-SHORT' THEN 'opening_range'
            WHEN 'BRF2-SHORT' THEN 'rally_failure_short'
        END
    """
    op.execute(
        sa.text(
            f"""
            UPDATE brc_trade_tickets AS target
               SET exposure_family = {family_case}
              FROM brc_event_specs AS event_specs
             WHERE target.exposure_family IS NULL
               AND target.event_spec_id = event_specs.event_spec_id
               AND target.terminal_at_ms IS NOT NULL
               AND event_specs.event_id IN (
                   'CPM-LONG', 'MPG-LONG', 'MI-LONG',
                   'SOR-LONG', 'SOR-SHORT', 'BRF2-SHORT'
               )
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            UPDATE brc_capacity_claims AS target
               SET exposure_family = {family_case}
              FROM brc_event_specs AS event_specs,
                   brc_trade_tickets AS ticket
             WHERE target.exposure_family IS NULL
               AND target.event_spec_id = event_specs.event_spec_id
               AND ticket.ticket_id = target.ticket_id
               AND ticket.terminal_at_ms IS NOT NULL
               AND event_specs.event_id IN (
                   'CPM-LONG', 'MPG-LONG', 'MI-LONG',
                   'SOR-LONG', 'SOR-SHORT', 'BRF2-SHORT'
               )
            """
        )
    )


def _create_admission_decisions() -> None:
    op.create_table(
        "brc_admission_decisions",
        sa.Column("admission_decision_id", ID, nullable=False),
        sa.Column("signal_event_id", ID, nullable=False),
        sa.Column("exposure_episode_id", ID, nullable=False),
        sa.Column("strategy_group_id", ID, nullable=False),
        sa.Column("strategy_version_id", ID, nullable=False),
        sa.Column("event_spec_id", ID, nullable=False),
        sa.Column("universe_version_id", ID, nullable=False),
        sa.Column("universe_semantic_digest", sa.String(512), nullable=False),
        sa.Column("runtime_profile_id", ID, nullable=False),
        sa.Column("runtime_scope_id", ID, nullable=False),
        sa.Column("runtime_scope_version", sa.BigInteger(), nullable=False),
        sa.Column("owner_policy_id", ID, nullable=False),
        sa.Column("owner_policy_version", sa.BigInteger(), nullable=False),
        sa.Column("venue_id", ID, nullable=False),
        sa.Column("account_id", ID, nullable=False),
        sa.Column("exchange_instrument_id", ID, nullable=False),
        sa.Column("position_side", SHORT_TEXT, nullable=False),
        sa.Column("exposure_family", SHORT_TEXT, nullable=False),
        sa.Column("candidate_rank", sa.Integer(), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("candidate_set_digest", sa.String(512), nullable=False),
        sa.Column("candidate_set_summary", JSONB(), nullable=False),
        sa.Column("portfolio_usage", JSONB(), nullable=False),
        sa.Column("decision_status", SHORT_TEXT, nullable=False),
        sa.Column("first_blocker", sa.String(512), nullable=True),
        sa.Column("binding_constraint", sa.String(512), nullable=True),
        sa.Column("capacity_claim_id", ID, nullable=True),
        sa.Column("ticket_id", ID, nullable=True),
        sa.Column(
            "entry_admission_snapshot_digest",
            sa.String(512),
            nullable=True,
        ),
        sa.Column("decision_digest", sa.String(512), nullable=False),
        sa.Column("decided_at_ms", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint(
            "admission_decision_id",
            name="pk_brc_admission_decisions",
        ),
        sa.UniqueConstraint(
            "signal_event_id",
            name="uq_brc_admission_decisions_signal",
        ),
        sa.ForeignKeyConstraint(
            ["signal_event_id"],
            ["brc_signal_events.signal_event_id"],
            name="fk_brc_admission_signal",
        ),
        sa.ForeignKeyConstraint(
            ["capacity_claim_id"],
            ["brc_capacity_claims.capacity_claim_id"],
            name="fk_brc_admission_claim",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["brc_trade_tickets.ticket_id"],
            name="fk_brc_admission_ticket",
        ),
        sa.CheckConstraint(
            "position_side IN ('long', 'short')",
            name="ck_brc_admission_side",
        ),
        sa.CheckConstraint(
            "exposure_family IN ('long_continuation', 'opening_range', "
            "'rally_failure_short')",
            name="ck_brc_admission_family",
        ),
        sa.CheckConstraint(
            "candidate_rank > 0 AND candidate_count BETWEEN 1 AND 64 "
            "AND candidate_rank <= candidate_count",
            name="ck_brc_admission_candidate",
        ),
        sa.CheckConstraint(
            "decision_status IN ('admitted', 'rejected')",
            name="ck_brc_admission_status",
        ),
        sa.CheckConstraint(
            "(decision_status = 'admitted' AND first_blocker IS NULL "
            "AND capacity_claim_id IS NOT NULL AND ticket_id IS NOT NULL "
            "AND entry_admission_snapshot_digest IS NOT NULL) OR "
            "(decision_status = 'rejected' AND first_blocker IS NOT NULL "
            "AND capacity_claim_id IS NULL AND ticket_id IS NULL)",
            name="ck_brc_admission_shape",
        ),
        sa.CheckConstraint(
            "candidate_set_digest ~ '^sha256:[0-9a-f]{64}$' "
            "AND decision_digest ~ '^sha256:[0-9a-f]{64}$' "
            "AND universe_semantic_digest ~ '^sha256:[0-9a-f]{64}$' "
            "AND (entry_admission_snapshot_digest IS NULL OR "
            "entry_admission_snapshot_digest ~ '^sha256:[0-9a-f]{64}$')",
            name="ck_brc_admission_digest",
        ),
    )
    op.create_index(
        "ix_brc_admission_decisions_decided_at_ms",
        "brc_admission_decisions",
        ["decided_at_ms"],
    )
    op.create_index(
        "ix_brc_admission_decisions_first_blocker_decided_at_ms",
        "brc_admission_decisions",
        ["first_blocker", "decided_at_ms"],
    )
    op.create_index(
        "ix_brc_admission_decisions_strategy_event_decided",
        "brc_admission_decisions",
        ["strategy_group_id", "event_spec_id", "decided_at_ms"],
    )


def _create_shadow_outcomes() -> None:
    op.create_table(
        "brc_shadow_outcomes_current",
        sa.Column("shadow_outcome_id", ID, nullable=False),
        sa.Column("admission_decision_id", ID, nullable=False),
        sa.Column("status", SHORT_TEXT, nullable=False),
        sa.Column("evaluation_kind", SHORT_TEXT, nullable=False),
        sa.Column("exchange_instrument_id", ID, nullable=False),
        sa.Column("position_side", SHORT_TEXT, nullable=False),
        sa.Column("timeframe", SHORT_TEXT, nullable=False),
        sa.Column("entry_reference_price", MONEY, nullable=False),
        sa.Column("initial_stop_price", MONEY, nullable=False),
        sa.Column("initial_risk_per_unit", MONEY, nullable=False),
        sa.Column("horizon_start_ms", sa.BigInteger(), nullable=False),
        sa.Column("horizon_end_ms", sa.BigInteger(), nullable=False),
        sa.Column("claim_owner", ID, nullable=True),
        sa.Column("claim_token", ID, nullable=True),
        sa.Column("lease_until_ms", sa.BigInteger(), nullable=True),
        sa.Column("max_favorable_price", MONEY, nullable=True),
        sa.Column("max_adverse_price", MONEY, nullable=True),
        sa.Column("mfe_r", MONEY, nullable=True),
        sa.Column("mae_r", MONEY, nullable=True),
        sa.Column("observed_through_ms", sa.BigInteger(), nullable=True),
        sa.Column("completion_reason", LONG_TEXT, nullable=True),
        sa.Column("projection_version", sa.BigInteger(), nullable=False),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("completed_at_ms", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint(
            "shadow_outcome_id",
            name="pk_brc_shadow_outcomes_current",
        ),
        sa.UniqueConstraint(
            "admission_decision_id",
            name="uq_brc_shadow_outcomes_current_admission_decision_id",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'claimed', 'completed', 'unavailable')",
            name="ck_brc_shadow_outcomes_current_status_valid",
        ),
        sa.CheckConstraint(
            "evaluation_kind = 'fixed_horizon_excursion_v1'",
            name="ck_brc_shadow_outcomes_current_evaluation_kind_valid",
        ),
        sa.CheckConstraint(
            "position_side IN ('long', 'short')",
            name="ck_brc_shadow_outcomes_current_side_valid",
        ),
        sa.CheckConstraint(
            "timeframe IN ('15m', '1h')",
            name="ck_brc_shadow_outcomes_current_timeframe_valid",
        ),
        sa.CheckConstraint(
            "initial_risk_per_unit >= 0 AND horizon_end_ms > horizon_start_ms",
            name="ck_brc_shadow_outcomes_current_risk_horizon_valid",
        ),
        sa.CheckConstraint(
            "(status = 'claimed' AND claim_owner IS NOT NULL "
            "AND claim_token IS NOT NULL AND lease_until_ms IS NOT NULL "
            "AND completed_at_ms IS NULL AND max_favorable_price IS NULL "
            "AND max_adverse_price IS NULL AND mfe_r IS NULL AND mae_r IS NULL "
            "AND observed_through_ms IS NULL AND completion_reason IS NULL) OR "
            "(status = 'pending' AND claim_owner IS NULL "
            "AND claim_token IS NULL AND lease_until_ms IS NULL "
            "AND completed_at_ms IS NULL AND max_favorable_price IS NULL "
            "AND max_adverse_price IS NULL AND mfe_r IS NULL AND mae_r IS NULL "
            "AND observed_through_ms IS NULL AND completion_reason IS NULL) OR "
            "(status = 'completed' AND claim_owner IS NULL "
            "AND claim_token IS NULL AND lease_until_ms IS NULL "
            "AND completed_at_ms IS NOT NULL AND max_favorable_price IS NOT NULL "
            "AND max_adverse_price IS NOT NULL AND mfe_r IS NOT NULL "
            "AND mae_r IS NOT NULL AND observed_through_ms IS NOT NULL "
            "AND completion_reason IS NOT NULL) OR "
            "(status = 'unavailable' AND claim_owner IS NULL "
            "AND claim_token IS NULL AND lease_until_ms IS NULL "
            "AND completed_at_ms IS NOT NULL AND max_favorable_price IS NULL "
            "AND max_adverse_price IS NULL AND mfe_r IS NULL AND mae_r IS NULL "
            "AND observed_through_ms IS NULL AND completion_reason IS NOT NULL)",
            name="ck_brc_shadow_outcomes_current_lease_shape_valid",
        ),
    )
    op.create_index(
        "ix_brc_shadow_outcomes_current_due",
        "brc_shadow_outcomes_current",
        ["status", "horizon_end_ms", "lease_until_ms"],
    )


def downgrade() -> None:
    raise RuntimeError("0003 downgrade is forbidden; use fix-forward")
