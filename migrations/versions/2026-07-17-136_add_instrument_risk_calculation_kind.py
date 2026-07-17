"""Make linear quote-settled pricing explicit and versioned.

Revision ID: 136
Revises: 135
Create Date: 2026-07-17
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "136"
down_revision: Union[str, None] = "135"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RULE_TABLE = "brc_instrument_rule_snapshots"
INSTRUMENT_TABLE = "brc_exchange_instruments"
RESERVATION_TABLE = "brc_budget_reservations"
EXPOSURE_TABLE = "brc_account_exposure_current"
CALCULATION_KIND = "linear_quote_settled"
KIND_CHECK = "ck_brc_instrument_rule_snapshot_calculation_kind"


def upgrade() -> None:
    bind = op.get_bind()
    _require_upgrade_shape(bind)
    _add_columns_and_check(bind)
    target_ids = _materialize_target_rule_ids(bind)
    targets = _load_targets_for_preflight(bind, target_ids)
    _validate_targets(targets)
    clones = _precompute_current_v1_clones(targets)
    _reject_clone_collisions(bind, clones)
    _switch_current_rules(bind, clones)
    _assert_upgrade_postconditions(bind, clones)


def downgrade() -> None:
    bind = op.get_bind()
    _require_upgrade_shape(bind)
    _assert_downgrade_compatible(bind)
    clones = _load_downgrade_clones(bind)
    _restore_legacy_current_rules(bind, clones)
    _assert_downgrade_postconditions(bind, clones)
    _drop_columns_and_check(bind)


def _require_upgrade_shape(bind: sa.Connection) -> None:
    required = (RULE_TABLE, INSTRUMENT_TABLE, RESERVATION_TABLE, EXPOSURE_TABLE)
    inspector = sa.inspect(bind)
    missing = [name for name in required if not inspector.has_table(name)]
    if missing:
        raise RuntimeError("instrument_risk_migration_shape_missing:" + ",".join(missing))
    rule_columns = _columns(bind, RULE_TABLE)
    required_rule_columns = {
        "instrument_rule_snapshot_id", "exchange_instrument_id", "rule_schema_version",
        "price_tick", "quantity_step", "min_qty", "min_notional",
        "contract_multiplier", "exchange_max_leverage_for_claim_notional",
        "source_fact_snapshot_id", "valid_until_ms", "semantic_hash", "status",
    }
    if not required_rule_columns <= rule_columns:
        raise RuntimeError("instrument_risk_migration_rule_shape_invalid")


def _add_columns_and_check(bind: sa.Connection) -> None:
    columns = _columns(bind, RULE_TABLE)
    if "risk_calculation_kind" not in columns:
        op.add_column(RULE_TABLE, sa.Column("risk_calculation_kind", sa.String(64), nullable=True))
    if "supersedes_instrument_rule_snapshot_id" not in columns:
        op.add_column(
            RULE_TABLE,
            sa.Column("supersedes_instrument_rule_snapshot_id", sa.String(192), nullable=True),
        )
    constraints = {str(item.get("name") or "") for item in sa.inspect(bind).get_check_constraints(RULE_TABLE)}
    if KIND_CHECK not in constraints:
        op.create_check_constraint(
            KIND_CHECK,
            RULE_TABLE,
            "risk_calculation_kind IS NULL OR "
            "risk_calculation_kind = 'linear_quote_settled'",
        )


def _materialize_target_rule_ids(bind: sa.Connection) -> tuple[str, ...]:
    rule = _table(bind, RULE_TABLE)
    reservation = _table(bind, RESERVATION_TABLE)
    exposure = _table(bind, EXPOSURE_TABLE)
    ids = set(bind.execute(sa.select(rule.c.instrument_rule_snapshot_id).where(rule.c.status == "current")).scalars())
    ids.update(
        bind.execute(
            sa.select(reservation.c.instrument_rule_snapshot_id).where(
                reservation.c.status.in_(("active", "consumed")),
                reservation.c.instrument_rule_snapshot_id.is_not(None),
            )
        ).scalars()
    )
    nonflat_instruments = tuple(
        bind.execute(
            sa.select(exposure.c.exchange_instrument_id).where(
                exposure.c.exposure_state.not_in(("flat", "closed")),
                exposure.c.exchange_instrument_id.is_not(None),
            )
        ).scalars()
    )
    for instrument_id in sorted(set(nonflat_instruments)):
        current = tuple(
            bind.execute(
                sa.select(rule.c.instrument_rule_snapshot_id).where(
                    rule.c.exchange_instrument_id == instrument_id,
                    rule.c.status == "current",
                )
            ).scalars()
        )
        if len(current) != 1:
            raise RuntimeError("instrument_risk_migration_exposure_current_rule_ambiguous")
        ids.add(current[0])
    if not ids:
        return ()
    return tuple(sorted(str(value) for value in ids if value))


def _load_targets_for_preflight(
    bind: sa.Connection, target_ids: tuple[str, ...]
) -> tuple[dict[str, object], ...]:
    if not target_ids:
        return ()
    rule = _table(bind, RULE_TABLE)
    instrument = _table(bind, INSTRUMENT_TABLE)
    rows = bind.execute(
        sa.select(rule, instrument.c.exchange_id, instrument.c.asset_class,
                  instrument.c.instrument_type, instrument.c.settlement_asset,
                  instrument.c.margin_asset, instrument.c.status.label("instrument_status"))
        .select_from(rule.join(instrument, instrument.c.exchange_instrument_id == rule.c.exchange_instrument_id))
        .where(rule.c.instrument_rule_snapshot_id.in_(target_ids))
        .order_by(rule.c.instrument_rule_snapshot_id)
        .with_for_update()
    ).mappings().all()
    if len(rows) != len(target_ids):
        raise RuntimeError("instrument_risk_migration_target_rule_missing")
    return tuple(dict(row) for row in rows)


def _validate_targets(targets: tuple[dict[str, object], ...]) -> None:
    for row in targets:
        eligible = (
            row.get("instrument_status") == "active"
            and row.get("exchange_id") == "binance_usdm"
            and row.get("asset_class") == "crypto"
            and row.get("instrument_type") in {"perpetual", "future"}
            and bool(str(row.get("settlement_asset") or "").strip())
            and row.get("settlement_asset") == row.get("margin_asset")
            and _positive_decimal(row.get("contract_multiplier"))
        )
        if not eligible:
            raise RuntimeError("instrument_risk_migration_target_not_linear_eligible")


def _precompute_current_v1_clones(
    targets: tuple[dict[str, object], ...]
) -> tuple[dict[str, object], ...]:
    clones: list[dict[str, object]] = []
    for row in targets:
        if row["status"] != "current":
            continue
        if row["rule_schema_version"] != "v1":
            raise RuntimeError("instrument_risk_migration_current_rule_schema_unknown")
        clone = dict(row)
        clone_id = f"{row['instrument_rule_snapshot_id']}:v2"
        if len(clone_id) > 192:
            raise RuntimeError("instrument_risk_migration_clone_id_invalid")
        clone.update({
            "instrument_rule_snapshot_id": clone_id,
            "rule_schema_version": "v2",
            "risk_calculation_kind": CALCULATION_KIND,
            "supersedes_instrument_rule_snapshot_id": row["instrument_rule_snapshot_id"],
            "status": "current",
        })
        clone["semantic_hash"] = _v2_semantic_hash(clone)
        clones.append(clone)
    return tuple(clones)


def _reject_clone_collisions(bind: sa.Connection, clones: tuple[dict[str, object], ...]) -> None:
    if len({str(item["instrument_rule_snapshot_id"]) for item in clones}) != len(clones):
        raise RuntimeError("instrument_risk_migration_clone_id_collision")
    if not clones:
        return
    rule = _table(bind, RULE_TABLE)
    ids = tuple(str(item["instrument_rule_snapshot_id"]) for item in clones)
    if bind.execute(sa.select(rule.c.instrument_rule_snapshot_id).where(rule.c.instrument_rule_snapshot_id.in_(ids))).first():
        raise RuntimeError("instrument_risk_migration_clone_id_collision")


def _switch_current_rules(bind: sa.Connection, clones: tuple[dict[str, object], ...]) -> None:
    if not clones:
        return
    rule = _table(bind, RULE_TABLE)
    predecessor_ids = tuple(str(item["supersedes_instrument_rule_snapshot_id"]) for item in clones)
    changed = bind.execute(
        rule.update().where(
            rule.c.instrument_rule_snapshot_id.in_(predecessor_ids),
            rule.c.status == "current",
            rule.c.rule_schema_version == "v1",
        ).values(status="superseded")
    )
    if int(changed.rowcount or 0) != len(clones):
        raise RuntimeError("instrument_risk_migration_predecessor_changed")
    allowed_columns = _columns(bind, RULE_TABLE)
    for clone in clones:
        bind.execute(rule.insert().values(**{key: value for key, value in clone.items() if key in allowed_columns}))


def _assert_upgrade_postconditions(bind: sa.Connection, clones: tuple[dict[str, object], ...]) -> None:
    rule = _table(bind, RULE_TABLE)
    for clone in clones:
        current = tuple(bind.execute(sa.select(rule.c.rule_schema_version).where(
            rule.c.exchange_instrument_id == clone["exchange_instrument_id"],
            rule.c.status == "current",
        )).scalars())
        if current != ("v2",):
            raise RuntimeError("instrument_risk_migration_postcondition_failed")


def _assert_downgrade_compatible(bind: sa.Connection) -> None:
    reservation = _table(bind, RESERVATION_TABLE)
    if "capacity_claim_schema_version" in reservation.c and bind.execute(
        sa.select(reservation.c.budget_reservation_id).where(
            reservation.c.capacity_claim_schema_version == "v2"
        ).limit(1)
    ).first():
        raise RuntimeError("instrument_risk_history_not_legacy_compatible")
    for clone in _load_downgrade_clones(bind):
        predecessor = clone["predecessor"]
        expected = _expected_clone_from_predecessor(predecessor)
        actual = clone["clone"]
        checks = (
            actual["instrument_rule_snapshot_id"] == expected["instrument_rule_snapshot_id"],
            actual["rule_schema_version"] == "v2",
            actual["risk_calculation_kind"] == CALCULATION_KIND,
            actual["semantic_hash"] == expected["semantic_hash"],
            actual["status"] == "current",
        )
        economic_columns = (
            "exchange_instrument_id", "price_tick", "quantity_step", "min_qty",
            "min_notional", "contract_multiplier",
            "exchange_max_leverage_for_claim_notional", "source_fact_snapshot_id",
            "valid_until_ms",
        )
        if not all(checks) or any(actual[name] != predecessor[name] for name in economic_columns):
            raise RuntimeError("instrument_risk_history_not_legacy_compatible")


def _load_downgrade_clones(bind: sa.Connection) -> tuple[dict[str, dict[str, object]], ...]:
    rule = _table(bind, RULE_TABLE)
    v2_rows = bind.execute(sa.select(rule).where(rule.c.rule_schema_version == "v2").order_by(rule.c.instrument_rule_snapshot_id).with_for_update()).mappings().all()
    result: list[dict[str, dict[str, object]]] = []
    for row in v2_rows:
        predecessor_id = row.get("supersedes_instrument_rule_snapshot_id")
        if not predecessor_id:
            raise RuntimeError("instrument_risk_history_not_legacy_compatible")
        predecessor = bind.execute(sa.select(rule).where(rule.c.instrument_rule_snapshot_id == predecessor_id).with_for_update()).mappings().one_or_none()
        if predecessor is None or predecessor["rule_schema_version"] != "v1" or predecessor["status"] != "superseded":
            raise RuntimeError("instrument_risk_history_not_legacy_compatible")
        result.append({"clone": dict(row), "predecessor": dict(predecessor)})
    return tuple(result)


def _expected_clone_from_predecessor(predecessor: dict[str, object]) -> dict[str, object]:
    clone = dict(predecessor)
    clone.update({
        "instrument_rule_snapshot_id": f"{predecessor['instrument_rule_snapshot_id']}:v2",
        "rule_schema_version": "v2",
        "risk_calculation_kind": CALCULATION_KIND,
        "supersedes_instrument_rule_snapshot_id": predecessor["instrument_rule_snapshot_id"],
        "status": "current",
    })
    clone["semantic_hash"] = _v2_semantic_hash(clone)
    return clone


def _restore_legacy_current_rules(bind: sa.Connection, clones: tuple[dict[str, dict[str, object]], ...]) -> None:
    rule = _table(bind, RULE_TABLE)
    if clones:
        bind.execute(rule.delete().where(rule.c.instrument_rule_snapshot_id.in_(tuple(
            item["clone"]["instrument_rule_snapshot_id"] for item in clones
        ))))
        restored = bind.execute(rule.update().where(rule.c.instrument_rule_snapshot_id.in_(tuple(
            item["predecessor"]["instrument_rule_snapshot_id"] for item in clones
        ))).values(status="current"))
        if int(restored.rowcount or 0) != len(clones):
            raise RuntimeError("instrument_risk_history_not_legacy_compatible")


def _assert_downgrade_postconditions(bind: sa.Connection, clones: tuple[dict[str, dict[str, object]], ...]) -> None:
    rule = _table(bind, RULE_TABLE)
    for item in clones:
        current = tuple(bind.execute(sa.select(rule.c.rule_schema_version).where(
            rule.c.exchange_instrument_id == item["predecessor"]["exchange_instrument_id"],
            rule.c.status == "current",
        )).scalars())
        if current != ("v1",):
            raise RuntimeError("instrument_risk_history_not_legacy_compatible")


def _drop_columns_and_check(bind: sa.Connection) -> None:
    constraints = {str(item.get("name") or "") for item in sa.inspect(bind).get_check_constraints(RULE_TABLE)}
    if KIND_CHECK in constraints:
        op.drop_constraint(KIND_CHECK, RULE_TABLE, type_="check")
    for name in ("supersedes_instrument_rule_snapshot_id", "risk_calculation_kind"):
        if name in _columns(bind, RULE_TABLE):
            op.drop_column(RULE_TABLE, name)


def _table(bind: sa.Connection, name: str) -> sa.Table:
    return sa.Table(name, sa.MetaData(), autoload_with=bind)


def _columns(bind: sa.Connection, name: str) -> set[str]:
    return {str(column["name"]) for column in sa.inspect(bind).get_columns(name)}


def _positive_decimal(value: object) -> bool:
    try:
        return Decimal(str(value)).is_finite() and Decimal(str(value)) > 0
    except Exception:
        return False


def _v2_semantic_hash(row: dict[str, object]) -> str:
    fields = (
        "instrument_rule_snapshot_id", "rule_schema_version", "price_tick",
        "quantity_step", "min_qty", "min_notional", "contract_multiplier",
        "exchange_max_leverage_for_claim_notional", "source_fact_snapshot_id",
        "valid_until_ms", "risk_calculation_kind",
    )
    payload = {
        field: format(Decimal(str(row[field])).normalize(), "f")
        if field in {"price_tick", "quantity_step", "min_qty", "min_notional", "contract_multiplier"}
        else row[field]
        for field in fields
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
