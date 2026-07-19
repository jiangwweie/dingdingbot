"""Cut active runtime scope to canonical instrument identity generation V2.

Revision ID: 138
Revises: 137
Create Date: 2026-07-19
"""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "138"
down_revision: Union[str, None] = "137"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


MIGRATION_AT_MS = 1784429600000
GENERATION = "identity-v2"
IDENTITY_SCHEMA_VERSION = "v2"
EXPECTED_ACTIVE_SCOPE_COUNT = 22
EXPECTED_ACTIVE_INSTRUMENT_COUNT = 6
LEGACY_ASSET_CLASS = "crypto_usdm_perp"
CANONICAL_ASSET_CLASS = "crypto"
CANONICAL_INSTRUMENT_TYPE = "perpetual"
CANONICAL_SETTLEMENT_ASSET = "USDT"
CANONICAL_MARGIN_ASSET = "USDT"

INSTRUMENT_TABLE = "brc_exchange_instruments"
MAPPING_TABLE = "brc_symbol_instrument_mappings"
CANDIDATE_TABLE = "brc_strategy_group_candidate_scope"
EVENT_BINDING_TABLE = "brc_candidate_scope_event_bindings"
RUNTIME_BINDING_TABLE = "brc_runtime_scope_bindings"


def upgrade() -> None:
    bind = op.get_bind()
    _set_session_timeouts(bind)
    _require_schema(bind)
    state = _load_and_validate_active_generation(bind)
    _reject_live_cutover_conflicts(bind, state)
    _replace_instrument_symbol_uniqueness(bind)
    _retire_legacy_generation(bind, state)
    _insert_canonical_generation(bind, state)
    _invalidate_old_current_projections(bind, state)
    _assert_postconditions(bind, state)


def downgrade() -> None:
    raise RuntimeError("canonical_instrument_identity_cutover_is_forward_only")


def _set_session_timeouts(bind: sa.Connection) -> None:
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
        bind.execute(sa.text("SET LOCAL statement_timeout = '60s'"))


def _require_schema(bind: sa.Connection) -> None:
    required_tables = {
        INSTRUMENT_TABLE,
        MAPPING_TABLE,
        CANDIDATE_TABLE,
        EVENT_BINDING_TABLE,
        RUNTIME_BINDING_TABLE,
        "brc_strategy_side_event_specs",
    }
    missing = sorted(required_tables - set(sa.inspect(bind).get_table_names()))
    if missing:
        raise RuntimeError(
            "canonical_instrument_cutover_schema_missing:" + ",".join(missing)
        )
    required_columns = {
        INSTRUMENT_TABLE: {
            "exchange_instrument_id",
            "exchange_id",
            "exchange_symbol",
            "asset_class",
            "instrument_type",
            "settlement_asset",
            "margin_asset",
            "instrument_identity_schema_version",
            "status",
        },
        CANDIDATE_TABLE: {
            "candidate_scope_id",
            "exchange_instrument_id",
            "asset_class",
            "status",
        },
    }
    for table_name, columns in required_columns.items():
        actual = {
            str(column["name"])
            for column in sa.inspect(bind).get_columns(table_name)
        }
        if not columns <= actual:
            raise RuntimeError(
                f"canonical_instrument_cutover_schema_invalid:{table_name}"
            )


def _load_and_validate_active_generation(
    bind: sa.Connection,
) -> dict[str, object]:
    candidate = _table(bind, CANDIDATE_TABLE)
    mapping = _table(bind, MAPPING_TABLE)
    instrument = _table(bind, INSTRUMENT_TABLE)
    event_binding = _table(bind, EVENT_BINDING_TABLE)
    event_spec = _table(bind, "brc_strategy_side_event_specs")
    runtime_binding = _table(bind, RUNTIME_BINDING_TABLE)

    candidates = tuple(
        dict(row)
        for row in bind.execute(
            sa.select(candidate)
            .where(candidate.c.status == "active")
            .order_by(candidate.c.strategy_group_id, candidate.c.symbol, candidate.c.side)
            .with_for_update()
        ).mappings()
    )
    if len(candidates) != EXPECTED_ACTIVE_SCOPE_COUNT:
        raise RuntimeError("canonical_instrument_cutover_active_scope_count_invalid")
    if any(row.get("asset_class") != LEGACY_ASSET_CLASS for row in candidates):
        raise RuntimeError("canonical_instrument_cutover_legacy_scope_shape_invalid")

    instrument_ids = tuple(
        sorted({str(row.get("exchange_instrument_id") or "") for row in candidates})
    )
    if (
        len(instrument_ids) != EXPECTED_ACTIVE_INSTRUMENT_COUNT
        or any(not value for value in instrument_ids)
    ):
        raise RuntimeError("canonical_instrument_cutover_active_instrument_count_invalid")

    instruments = tuple(
        dict(row)
        for row in bind.execute(
            sa.select(instrument)
            .where(instrument.c.exchange_instrument_id.in_(instrument_ids))
            .where(instrument.c.status == "active")
            .order_by(instrument.c.exchange_instrument_id)
            .with_for_update()
        ).mappings()
    )
    if len(instruments) != EXPECTED_ACTIVE_INSTRUMENT_COUNT:
        raise RuntimeError("canonical_instrument_cutover_registry_count_invalid")
    if any(
        row.get("exchange_id") != "binance_usdm"
        or row.get("asset_class") != LEGACY_ASSET_CLASS
        or row.get("instrument_type") is not None
        or row.get("settlement_asset") is not None
        or row.get("margin_asset") is not None
        for row in instruments
    ):
        raise RuntimeError("canonical_instrument_cutover_legacy_registry_shape_invalid")

    mappings = tuple(
        dict(row)
        for row in bind.execute(
            sa.select(mapping)
            .where(mapping.c.status == "active")
            .order_by(mapping.c.symbol)
            .with_for_update()
        ).mappings()
    )
    if len(mappings) != EXPECTED_ACTIVE_INSTRUMENT_COUNT:
        raise RuntimeError("canonical_instrument_cutover_mapping_count_invalid")
    mapping_by_symbol = {str(row["symbol"]): row for row in mappings}
    if len(mapping_by_symbol) != len(mappings):
        raise RuntimeError("canonical_instrument_cutover_mapping_ambiguous")
    for row in candidates:
        current_mapping = mapping_by_symbol.get(str(row["symbol"]))
        if (
            current_mapping is None
            or current_mapping["exchange_instrument_id"]
            != row["exchange_instrument_id"]
        ):
            raise RuntimeError("canonical_instrument_cutover_scope_mapping_mismatch")

    candidate_ids = tuple(str(row["candidate_scope_id"]) for row in candidates)
    event_bindings = tuple(
        dict(row)
        for row in bind.execute(
            sa.select(event_binding, event_spec.c.event_spec_version)
            .select_from(
                event_binding.join(
                    event_spec,
                    event_spec.c.event_spec_id == event_binding.c.event_spec_id,
                )
            )
            .where(event_binding.c.candidate_scope_id.in_(candidate_ids))
            .where(event_binding.c.status == "active")
            .where(event_spec.c.status == "current")
            .order_by(event_binding.c.candidate_scope_id)
            .with_for_update()
        ).mappings()
    )
    if (
        len(event_bindings) != EXPECTED_ACTIVE_SCOPE_COUNT
        or any(row.get("event_spec_version") != "v2" for row in event_bindings)
    ):
        raise RuntimeError("canonical_instrument_cutover_event_binding_invalid")
    if len({str(row["candidate_scope_id"]) for row in event_bindings}) != len(candidates):
        raise RuntimeError("canonical_instrument_cutover_event_binding_ambiguous")

    runtime_bindings = tuple(
        dict(row)
        for row in bind.execute(
            sa.select(runtime_binding)
            .where(runtime_binding.c.candidate_scope_id.in_(candidate_ids))
            .where(runtime_binding.c.status == "active")
            .order_by(runtime_binding.c.candidate_scope_id)
            .with_for_update()
        ).mappings()
    )
    if (
        len(runtime_bindings) != EXPECTED_ACTIVE_SCOPE_COUNT
        or len({str(row["candidate_scope_id"]) for row in runtime_bindings})
        != len(candidates)
    ):
        raise RuntimeError("canonical_instrument_cutover_runtime_binding_invalid")

    canonical_ids = {
        str(row["exchange_instrument_id"]): _canonical_instrument_id(
            exchange_id=str(row["exchange_id"]),
            exchange_symbol=str(row["exchange_symbol"]),
        )
        for row in instruments
    }
    if len(set(canonical_ids.values())) != EXPECTED_ACTIVE_INSTRUMENT_COUNT:
        raise RuntimeError("canonical_instrument_cutover_canonical_id_collision")
    collision = bind.execute(
        sa.select(instrument.c.exchange_instrument_id)
        .where(instrument.c.exchange_instrument_id.in_(tuple(canonical_ids.values())))
        .limit(1)
    ).first()
    if collision:
        raise RuntimeError("canonical_instrument_cutover_canonical_id_exists")

    return {
        "candidates": candidates,
        "candidate_ids": candidate_ids,
        "instruments": instruments,
        "mappings": mappings,
        "event_bindings": event_bindings,
        "runtime_bindings": runtime_bindings,
        "canonical_ids": canonical_ids,
    }


def _reject_live_cutover_conflicts(
    bind: sa.Connection,
    state: dict[str, object],
) -> None:
    candidate_ids = tuple(state["candidate_ids"])
    checks = (
        (
            "brc_budget_reservations",
            "status IN ('active', 'consumed')",
            "canonical_instrument_cutover_active_claim_present",
        ),
        (
            "brc_account_exposure_current",
            "exposure_state NOT IN ('flat', 'closed')",
            "canonical_instrument_cutover_nonflat_exposure_present",
        ),
        (
            "brc_promotion_candidates",
            "status IN ('eligible', 'arbitration_pending', 'arbitration_won') "
            "AND closed_at_ms IS NULL",
            "canonical_instrument_cutover_open_promotion_present",
        ),
        (
            "brc_action_time_lane_inputs",
            "status IN ('opened', 'facts_refreshing', 'ticket_pending', 'ticket_created') "
            "AND closed_at_ms IS NULL",
            "canonical_instrument_cutover_open_lane_present",
        ),
        (
            "brc_action_time_tickets",
            "status IN ('created', 'preflight_pending', 'finalgate_ready', 'submitted')",
            "canonical_instrument_cutover_open_ticket_present",
        ),
    )
    tables = set(sa.inspect(bind).get_table_names())
    for table_name, predicate, blocker in checks:
        if table_name not in tables:
            continue
        if int(
            bind.execute(
                sa.text(f"SELECT count(*) FROM {table_name} WHERE {predicate}")
            ).scalar_one()
        ):
            raise RuntimeError(blocker)

    if "brc_action_time_invocations" in tables:
        invocation = _table(bind, "brc_action_time_invocations")
        current_now_ms = _database_now_ms(bind)
        count = bind.execute(
            sa.select(sa.func.count())
            .select_from(invocation)
            .where(invocation.c.candidate_scope_id.in_(candidate_ids))
            .where(invocation.c.closed_at_ms.is_(None))
            .where(invocation.c.expires_at_ms > current_now_ms)
        ).scalar_one()
        if int(count):
            raise RuntimeError("canonical_instrument_cutover_unexpired_invocation_present")

    if "brc_live_signal_events" in tables:
        signal = _table(bind, "brc_live_signal_events")
        count = bind.execute(
            sa.select(sa.func.count())
            .select_from(signal)
            .where(signal.c.candidate_scope_id.in_(candidate_ids))
            .where(signal.c.source_kind == "live_market")
            .where(signal.c.status == "facts_validated")
            .where(signal.c.freshness_state == "fresh")
            .where(signal.c.expires_at_ms > _database_now_ms(bind))
        ).scalar_one()
        if int(count):
            raise RuntimeError("canonical_instrument_cutover_fresh_signal_present")


def _replace_instrument_symbol_uniqueness(bind: sa.Connection) -> None:
    constraint_names = {
        str(item.get("name") or "")
        for item in sa.inspect(bind).get_unique_constraints(INSTRUMENT_TABLE)
    }
    if "uq_brc_exchange_instruments_symbol" in constraint_names:
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table(INSTRUMENT_TABLE, recreate="always") as batch:
                batch.drop_constraint(
                    "uq_brc_exchange_instruments_symbol", type_="unique"
                )
        else:
            op.drop_constraint(
                "uq_brc_exchange_instruments_symbol",
                INSTRUMENT_TABLE,
                type_="unique",
            )


def _retire_legacy_generation(
    bind: sa.Connection,
    state: dict[str, object],
) -> None:
    instrument = _table(bind, INSTRUMENT_TABLE)
    mapping = _table(bind, MAPPING_TABLE)
    candidate = _table(bind, CANDIDATE_TABLE)
    event_binding = _table(bind, EVENT_BINDING_TABLE)
    runtime_binding = _table(bind, RUNTIME_BINDING_TABLE)
    candidate_ids = tuple(state["candidate_ids"])
    instrument_ids = tuple(
        str(row["exchange_instrument_id"]) for row in state["instruments"]
    )
    mapping_ids = tuple(str(row["mapping_id"]) for row in state["mappings"])

    bind.execute(
        event_binding.update()
        .where(event_binding.c.candidate_scope_id.in_(candidate_ids))
        .where(event_binding.c.status == "active")
        .values(status="revoked", valid_until_ms=MIGRATION_AT_MS)
    )
    bind.execute(
        runtime_binding.update()
        .where(runtime_binding.c.candidate_scope_id.in_(candidate_ids))
        .where(runtime_binding.c.status == "active")
        .values(
            status="revoked",
            valid_until_ms=MIGRATION_AT_MS,
            updated_at_ms=MIGRATION_AT_MS,
        )
    )
    bind.execute(
        candidate.update()
        .where(candidate.c.candidate_scope_id.in_(candidate_ids))
        .where(candidate.c.status == "active")
        .values(
            status="revoked",
            valid_until_ms=MIGRATION_AT_MS,
            updated_at_ms=MIGRATION_AT_MS,
        )
    )
    bind.execute(
        mapping.update()
        .where(mapping.c.mapping_id.in_(mapping_ids))
        .where(mapping.c.status == "active")
        .values(status="retired", valid_until_ms=MIGRATION_AT_MS)
    )
    bind.execute(
        instrument.update()
        .where(instrument.c.exchange_instrument_id.in_(instrument_ids))
        .where(instrument.c.status == "active")
        .values(status="retired")
    )


def _insert_canonical_generation(
    bind: sa.Connection,
    state: dict[str, object],
) -> None:
    instrument = _table(bind, INSTRUMENT_TABLE)
    mapping = _table(bind, MAPPING_TABLE)
    candidate = _table(bind, CANDIDATE_TABLE)
    event_binding = _table(bind, EVENT_BINDING_TABLE)
    runtime_binding = _table(bind, RUNTIME_BINDING_TABLE)
    canonical_ids = dict(state["canonical_ids"])

    for legacy in state["instruments"]:
        row = dict(legacy)
        row.update(
            {
                "exchange_instrument_id": canonical_ids[
                    str(legacy["exchange_instrument_id"])
                ],
                "asset_class": CANONICAL_ASSET_CLASS,
                "instrument_type": CANONICAL_INSTRUMENT_TYPE,
                "settlement_asset": CANONICAL_SETTLEMENT_ASSET,
                "margin_asset": CANONICAL_MARGIN_ASSET,
                "instrument_identity_schema_version": IDENTITY_SCHEMA_VERSION,
                "status": "active",
                "created_at_ms": MIGRATION_AT_MS,
            }
        )
        bind.execute(instrument.insert().values(**_filtered_row(instrument, row)))

    mapping_by_symbol = {str(row["symbol"]): dict(row) for row in state["mappings"]}
    candidate_id_map: dict[str, str] = {}
    for legacy in state["candidates"]:
        old_candidate_id = str(legacy["candidate_scope_id"])
        new_candidate_id = _generation_id(old_candidate_id)
        candidate_id_map[old_candidate_id] = new_candidate_id
        instrument_id = canonical_ids[str(legacy["exchange_instrument_id"])]

        candidate_row = dict(legacy)
        metadata = _json_object(candidate_row.get("metadata"))
        metadata.update(
            {
                "instrument_identity_generation": GENERATION,
                "supersedes_candidate_scope_id": old_candidate_id,
            }
        )
        candidate_row.update(
            {
                "candidate_scope_id": new_candidate_id,
                "exchange_instrument_id": instrument_id,
                "asset_class": CANONICAL_ASSET_CLASS,
                "status": "active",
                "valid_from_ms": MIGRATION_AT_MS,
                "valid_until_ms": None,
                "created_at_ms": MIGRATION_AT_MS,
                "updated_at_ms": MIGRATION_AT_MS,
                "metadata": metadata,
            }
        )
        bind.execute(
            candidate.insert().values(**_filtered_row(candidate, candidate_row))
        )

        symbol = str(legacy["symbol"])
        if symbol in mapping_by_symbol:
            mapping_row = mapping_by_symbol.pop(symbol)
            mapping_row.update(
                {
                    "mapping_id": _generation_id(str(mapping_row["mapping_id"])),
                    "exchange_instrument_id": instrument_id,
                    "status": "active",
                    "valid_from_ms": MIGRATION_AT_MS,
                    "valid_until_ms": None,
                    "created_at_ms": MIGRATION_AT_MS,
                }
            )
            bind.execute(
                mapping.insert().values(**_filtered_row(mapping, mapping_row))
            )
    if mapping_by_symbol:
        raise RuntimeError("canonical_instrument_cutover_mapping_clone_incomplete")

    for legacy in state["event_bindings"]:
        row = dict(legacy)
        row.pop("event_spec_version", None)
        row.update(
            {
                "binding_id": _generation_binding_id(
                    candidate_id_map[str(legacy["candidate_scope_id"])],
                    str(legacy["event_spec_id"]),
                ),
                "candidate_scope_id": candidate_id_map[
                    str(legacy["candidate_scope_id"])
                ],
                "status": "active",
                "valid_from_ms": MIGRATION_AT_MS,
                "valid_until_ms": None,
                "created_at_ms": MIGRATION_AT_MS,
            }
        )
        bind.execute(
            event_binding.insert().values(**_filtered_row(event_binding, row))
        )

    for legacy in state["runtime_bindings"]:
        new_candidate_id = candidate_id_map[str(legacy["candidate_scope_id"])]
        row = dict(legacy)
        row.update(
            {
                "runtime_scope_binding_id": (
                    f"runtime_scope:{new_candidate_id}:"
                    f"{legacy['runtime_profile_id']}"
                ),
                "candidate_scope_id": new_candidate_id,
                "status": "active",
                "valid_from_ms": MIGRATION_AT_MS,
                "valid_until_ms": None,
                "created_at_ms": MIGRATION_AT_MS,
                "updated_at_ms": MIGRATION_AT_MS,
            }
        )
        if len(str(row["runtime_scope_binding_id"])) > 160:
            raise RuntimeError("canonical_instrument_cutover_runtime_binding_id_invalid")
        bind.execute(
            runtime_binding.insert().values(**_filtered_row(runtime_binding, row))
        )

    bind.execute(
        sa.text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_brc_exchange_instruments_active_symbol
            ON brc_exchange_instruments (exchange_id, exchange_symbol)
            WHERE status = 'active'
            """
        )
    )
    if "brc_symbols" in sa.inspect(bind).get_table_names():
        symbols = _table(bind, "brc_symbols")
        bind.execute(
            symbols.update()
            .where(symbols.c.status == "active")
            .where(
                symbols.c.symbol.in_(
                    tuple(str(row["symbol"]) for row in state["mappings"])
                )
            )
            .values(asset_class=CANONICAL_ASSET_CLASS)
        )


def _invalidate_old_current_projections(
    bind: sa.Connection,
    state: dict[str, object],
) -> None:
    tables = set(sa.inspect(bind).get_table_names())
    candidate_ids = tuple(state["candidate_ids"])
    if "brc_watcher_runtime_coverage" in tables:
        coverage = _table(bind, "brc_watcher_runtime_coverage")
        if "candidate_scope_id" in coverage.c:
            bind.execute(
                coverage.update()
                .where(coverage.c.candidate_scope_id.in_(candidate_ids))
                .where(coverage.c.is_current.is_(True))
                .values(
                    is_current=False,
                    coverage_state="stale",
                    valid_until_ms=MIGRATION_AT_MS,
                )
            )
    if "brc_pretrade_readiness_rows" in tables:
        readiness = _table(bind, "brc_pretrade_readiness_rows")
        bind.execute(
            readiness.delete().where(readiness.c.candidate_scope_id.in_(candidate_ids))
        )


def _assert_postconditions(
    bind: sa.Connection,
    state: dict[str, object],
) -> None:
    candidate = _table(bind, CANDIDATE_TABLE)
    mapping = _table(bind, MAPPING_TABLE)
    instrument = _table(bind, INSTRUMENT_TABLE)
    event_binding = _table(bind, EVENT_BINDING_TABLE)
    runtime_binding = _table(bind, RUNTIME_BINDING_TABLE)
    active_candidates = tuple(
        bind.execute(
            sa.select(
                candidate.c.candidate_scope_id,
                candidate.c.exchange_instrument_id,
                candidate.c.asset_class,
            ).where(candidate.c.status == "active")
        ).mappings()
    )
    active_instruments = tuple(
        bind.execute(
            sa.select(instrument).where(instrument.c.status == "active")
        ).mappings()
    )
    if len(active_candidates) != EXPECTED_ACTIVE_SCOPE_COUNT:
        raise RuntimeError("canonical_instrument_cutover_post_scope_count_invalid")
    if len(active_instruments) != EXPECTED_ACTIVE_INSTRUMENT_COUNT:
        raise RuntimeError("canonical_instrument_cutover_post_instrument_count_invalid")
    if any(
        row["asset_class"] != CANONICAL_ASSET_CLASS
        or row["instrument_type"] != CANONICAL_INSTRUMENT_TYPE
        or row["settlement_asset"] != CANONICAL_SETTLEMENT_ASSET
        or row["margin_asset"] != CANONICAL_MARGIN_ASSET
        or row["instrument_identity_schema_version"] != IDENTITY_SCHEMA_VERSION
        for row in active_instruments
    ):
        raise RuntimeError("canonical_instrument_cutover_post_identity_invalid")
    active_instrument_ids = {
        str(row["exchange_instrument_id"]) for row in active_instruments
    }
    if any(
        row["asset_class"] != CANONICAL_ASSET_CLASS
        or str(row["exchange_instrument_id"]) not in active_instrument_ids
        or not str(row["candidate_scope_id"]).endswith(f":{GENERATION}")
        for row in active_candidates
    ):
        raise RuntimeError("canonical_instrument_cutover_post_scope_identity_invalid")
    counts = {
        "mapping": bind.execute(
            sa.select(sa.func.count()).select_from(mapping).where(mapping.c.status == "active")
        ).scalar_one(),
        "event": bind.execute(
            sa.select(sa.func.count())
            .select_from(event_binding)
            .where(event_binding.c.status == "active")
        ).scalar_one(),
        "runtime": bind.execute(
            sa.select(sa.func.count())
            .select_from(runtime_binding)
            .where(runtime_binding.c.status == "active")
        ).scalar_one(),
    }
    if counts != {
        "mapping": EXPECTED_ACTIVE_INSTRUMENT_COUNT,
        "event": EXPECTED_ACTIVE_SCOPE_COUNT,
        "runtime": EXPECTED_ACTIVE_SCOPE_COUNT,
    }:
        raise RuntimeError("canonical_instrument_cutover_post_binding_count_invalid")
    if int(
        bind.execute(
            sa.select(sa.func.count())
            .select_from(instrument)
            .where(instrument.c.status == "retired")
            .where(
                instrument.c.exchange_instrument_id.in_(
                    tuple(
                        str(row["exchange_instrument_id"])
                        for row in state["instruments"]
                    )
                )
            )
        ).scalar_one()
    ) != EXPECTED_ACTIVE_INSTRUMENT_COUNT:
        raise RuntimeError("canonical_instrument_cutover_legacy_provenance_missing")


def _canonical_instrument_id(*, exchange_id: str, exchange_symbol: str) -> str:
    payload = {
        "exchange_id": exchange_id,
        "exchange_symbol": exchange_symbol,
        "asset_class": CANONICAL_ASSET_CLASS,
        "instrument_type": CANONICAL_INSTRUMENT_TYPE,
        "settlement_asset": CANONICAL_SETTLEMENT_ASSET,
        "margin_asset": CANONICAL_MARGIN_ASSET,
        "instrument_identity_schema_version": IDENTITY_SCHEMA_VERSION,
    }
    digest = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"exchange_instrument:{IDENTITY_SCHEMA_VERSION}:{digest[:40]}"


def _generation_id(value: str) -> str:
    result = f"{value}:{GENERATION}"
    if len(result) > 192:
        raise RuntimeError("canonical_instrument_cutover_generation_id_invalid")
    return result


def _generation_binding_id(candidate_scope_id: str, event_spec_id: str) -> str:
    result = f"binding:{candidate_scope_id}:{event_spec_id}"
    if len(result) > 192:
        raise RuntimeError("canonical_instrument_cutover_event_binding_id_invalid")
    return result


def _json_object(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(str(value or ""))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _filtered_row(table: sa.Table, row: dict[str, object]) -> dict[str, object]:
    columns = {str(column.name) for column in table.columns}
    return {key: value for key, value in row.items() if key in columns}


def _database_now_ms(bind: sa.Connection) -> int:
    if bind.dialect.name == "postgresql":
        return int(
            bind.execute(
                sa.text(
                    "SELECT (extract(epoch from clock_timestamp()) * 1000)::bigint"
                )
            ).scalar_one()
        )
    import time

    return int(time.time() * 1000)


def _table(bind: sa.Connection, name: str) -> sa.Table:
    return sa.Table(name, sa.MetaData(), autoload_with=bind)
