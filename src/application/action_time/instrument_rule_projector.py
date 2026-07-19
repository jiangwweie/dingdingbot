"""Typed PG projector for current Binance USD-M instrument risk rules."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from typing import Any, Sequence

from pydantic import BaseModel, ConfigDict, Field
import sqlalchemy as sa

from src.domain.instrument_risk_identity import (
    InstrumentRiskIdentity,
    InstrumentRuleSnapshotRefV2,
    instrument_rule_snapshot_v2_semantic_hash,
)


class InstrumentRuleProjectionError(RuntimeError):
    """Fail-closed classification for rule source or PG projection defects."""


class ActiveInstrumentRuleTarget(BaseModel):
    """One exact current instrument plus its maximum pre-capacity base notional."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    identity: InstrumentRiskIdentity
    symbol: str = Field(min_length=1, max_length=128)
    claim_notional_ceiling: Decimal = Field(gt=0)


class InstrumentRuleObservation(BaseModel):
    """Read-only venue facts ready for a current V2 PG projection."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: str = Field(min_length=1, max_length=192)
    symbol: str = Field(min_length=1, max_length=128)
    price_tick: Decimal = Field(gt=0)
    quantity_step: Decimal = Field(gt=0)
    min_qty: Decimal = Field(gt=0)
    min_notional: Decimal = Field(gt=0)
    contract_multiplier: Decimal = Field(gt=0)
    exchange_max_leverage_for_claim_notional: int = Field(ge=1, le=125)
    claim_notional_ceiling: Decimal = Field(gt=0)
    observed_at_ms: int = Field(gt=0)
    valid_until_ms: int = Field(gt=0)
    source_ref: str = Field(min_length=1, max_length=512)


class InstrumentRuleProjectionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    target_count: int
    source_fact_inserted_count: int
    rule_inserted_count: int
    rule_unchanged_count: int
    rule_superseded_count: int
    current_rule_ids: tuple[str, ...]


def load_active_instrument_rule_targets(
    conn: sa.Connection,
    *,
    runtime_profile_id: str,
    expected_instrument_count: int | None = None,
) -> tuple[ActiveInstrumentRuleTarget, ...]:
    """Load exact active Candidate Scope identities without symbol remapping."""

    rows = tuple(
        dict(row)
        for row in conn.execute(
            sa.text(
                """
                SELECT candidate.exchange_instrument_id,
                       candidate.symbol,
                       instrument.exchange_id,
                       instrument.exchange_symbol,
                       instrument.asset_class,
                       instrument.instrument_type,
                       instrument.settlement_asset,
                       instrument.margin_asset,
                       instrument.instrument_identity_schema_version,
                       owner_policy.max_notional
                FROM brc_strategy_group_candidate_scope AS candidate
                JOIN brc_runtime_scope_bindings AS runtime
                  ON runtime.candidate_scope_id = candidate.candidate_scope_id
                 AND runtime.status = 'active'
                 AND runtime.runtime_profile_id = :runtime_profile_id
                JOIN brc_exchange_instruments AS instrument
                  ON instrument.exchange_instrument_id = candidate.exchange_instrument_id
                 AND instrument.status = 'active'
                JOIN brc_owner_policy_current AS owner_policy
                  ON owner_policy.policy_current_id = candidate.policy_current_id
                WHERE candidate.status = 'active'
                  AND candidate.scope_state = 'live_submit_allowed'
                ORDER BY candidate.exchange_instrument_id, candidate.symbol
                """
            ),
            {"runtime_profile_id": runtime_profile_id},
        ).mappings()
    )
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        instrument_id = str(row.get("exchange_instrument_id") or "").strip()
        if not instrument_id:
            raise InstrumentRuleProjectionError(
                "active_runtime_scope_instrument_identity_missing"
            )
        grouped.setdefault(instrument_id, []).append(row)
    if not grouped:
        raise InstrumentRuleProjectionError("active_runtime_scope_instrument_set_empty")
    if expected_instrument_count is not None and len(grouped) != expected_instrument_count:
        raise InstrumentRuleProjectionError(
            "active_runtime_scope_instrument_count_invalid"
        )

    targets: list[ActiveInstrumentRuleTarget] = []
    for instrument_id, instrument_rows in sorted(grouped.items()):
        identity_payloads = {
            (
                str(row.get("exchange_id") or ""),
                str(row.get("exchange_symbol") or ""),
                str(row.get("asset_class") or ""),
                str(row.get("instrument_type") or ""),
                str(row.get("settlement_asset") or ""),
                str(row.get("margin_asset") or ""),
                str(row.get("instrument_identity_schema_version") or ""),
            )
            for row in instrument_rows
        }
        symbols = {str(row.get("symbol") or "").strip() for row in instrument_rows}
        if len(identity_payloads) != 1 or len(symbols) != 1 or "" in symbols:
            raise InstrumentRuleProjectionError(
                "active_runtime_scope_instrument_identity_ambiguous"
            )
        try:
            notionals = tuple(_positive_decimal(row.get("max_notional")) for row in instrument_rows)
            identity_values = next(iter(identity_payloads))
            identity = InstrumentRiskIdentity(
                exchange_instrument_id=instrument_id,
                exchange_id=identity_values[0],
                exchange_symbol=identity_values[1],
                asset_class=identity_values[2],
                instrument_type=identity_values[3],
                settlement_asset=identity_values[4],
                margin_asset=identity_values[5],
                instrument_identity_schema_version=identity_values[6],
            )
        except (TypeError, ValueError) as exc:
            raise InstrumentRuleProjectionError(
                "instrument_identity_schema_invalid"
            ) from exc
        if (
            identity.exchange_id != "binance_usdm"
            or identity.asset_class != "crypto"
            or identity.instrument_type != "perpetual"
            or identity.settlement_asset != "USDT"
            or identity.margin_asset != "USDT"
            or identity.instrument_identity_schema_version != "v2"
        ):
            raise InstrumentRuleProjectionError("instrument_identity_schema_invalid")
        targets.append(
            ActiveInstrumentRuleTarget(
                identity=identity,
                symbol=next(iter(symbols)),
                claim_notional_ceiling=max(notionals),
            )
        )
    return tuple(targets)


def parse_binance_usdm_instrument_rule_observations(
    *,
    targets: Sequence[ActiveInstrumentRuleTarget],
    exchange_info_payload: object,
    leverage_bracket_payload: object,
    observed_at_ms: int,
    valid_until_ms: int,
    source_ref: str,
) -> tuple[InstrumentRuleObservation, ...]:
    """Normalize Binance GET payloads with Decimal-only financial parsing."""

    if observed_at_ms <= 0 or valid_until_ms <= observed_at_ms:
        raise InstrumentRuleProjectionError("instrument_rule_validity_invalid")
    if not isinstance(exchange_info_payload, dict):
        raise InstrumentRuleProjectionError("exchange_info_payload_invalid")
    if not isinstance(leverage_bracket_payload, list):
        raise InstrumentRuleProjectionError("leverage_bracket_payload_invalid")
    exchange_by_symbol = {
        str(item.get("symbol") or "").upper(): item
        for item in exchange_info_payload.get("symbols") or []
        if isinstance(item, dict)
    }
    bracket_by_symbol = {
        str(item.get("symbol") or "").upper(): item
        for item in leverage_bracket_payload
        if isinstance(item, dict)
    }

    observations: list[InstrumentRuleObservation] = []
    for target in targets:
        item = exchange_by_symbol.get(target.symbol.upper())
        bracket_row = bracket_by_symbol.get(target.symbol.upper())
        if not isinstance(item, dict) or not isinstance(bracket_row, dict):
            raise InstrumentRuleProjectionError(
                f"instrument_rule_source_missing:{target.symbol}"
            )
        if (
            item.get("status") != "TRADING"
            or item.get("contractType") != "PERPETUAL"
            or item.get("quoteAsset") != "USDT"
            or item.get("marginAsset") != "USDT"
        ):
            raise InstrumentRuleProjectionError(
                f"instrument_rule_contract_shape_invalid:{target.symbol}"
            )
        filters = {
            str(entry.get("filterType") or ""): entry
            for entry in item.get("filters") or []
            if isinstance(entry, dict)
        }
        lot = filters.get("LOT_SIZE") or {}
        market_lot = filters.get("MARKET_LOT_SIZE") or {}
        market_min_qty = _optional_decimal(market_lot.get("minQty"))
        market_step = _optional_decimal(market_lot.get("stepSize"))
        active_lot = (
            market_lot
            if market_min_qty is not None
            and market_min_qty > 0
            and market_step is not None
            and market_step > 0
            else lot
        )
        price_filter = filters.get("PRICE_FILTER") or {}
        notional_filter = filters.get("MIN_NOTIONAL") or filters.get("NOTIONAL") or {}
        leverage = _leverage_for_notional(
            bracket_row.get("brackets"),
            target.claim_notional_ceiling,
        )
        try:
            observation = InstrumentRuleObservation(
                exchange_instrument_id=target.identity.exchange_instrument_id,
                symbol=target.symbol,
                price_tick=_positive_decimal(price_filter.get("tickSize")),
                quantity_step=_positive_decimal(active_lot.get("stepSize")),
                min_qty=_positive_decimal(active_lot.get("minQty")),
                min_notional=_positive_decimal(
                    notional_filter.get("notional")
                    or notional_filter.get("minNotional")
                ),
                contract_multiplier=Decimal("1"),
                exchange_max_leverage_for_claim_notional=leverage,
                claim_notional_ceiling=target.claim_notional_ceiling,
                observed_at_ms=observed_at_ms,
                valid_until_ms=valid_until_ms,
                source_ref=source_ref,
            )
        except (TypeError, ValueError) as exc:
            raise InstrumentRuleProjectionError(
                f"instrument_rule_source_schema_invalid:{target.symbol}"
            ) from exc
        observations.append(observation)
    return tuple(observations)


def project_current_instrument_rules(
    conn: sa.Connection,
    *,
    observations: Sequence[InstrumentRuleObservation],
    runtime_profile_id: str,
    expected_instrument_count: int | None = None,
) -> InstrumentRuleProjectionResult:
    """Atomically append source facts and switch one current V2 rule per instrument."""

    if expected_instrument_count is not None and len(observations) != expected_instrument_count:
        raise InstrumentRuleProjectionError("instrument_rule_projection_count_invalid")
    if len({item.exchange_instrument_id for item in observations}) != len(observations):
        raise InstrumentRuleProjectionError("instrument_rule_projection_duplicate_instrument")
    fact_table = sa.Table(
        "brc_runtime_fact_snapshots", sa.MetaData(), autoload_with=conn
    )
    rule_table = sa.Table(
        "brc_instrument_rule_snapshots", sa.MetaData(), autoload_with=conn
    )
    source_fact_inserted_count = 0
    rule_inserted_count = 0
    rule_unchanged_count = 0
    rule_superseded_count = 0
    current_rule_ids: list[str] = []

    for observation in sorted(observations, key=lambda item: item.exchange_instrument_id):
        source_fact_id = _stable_id(
            "instrument_rule_source_fact",
            observation.exchange_instrument_id,
            str(observation.observed_at_ms),
            observation.source_ref,
        )
        fact_row = {
            "fact_snapshot_id": source_fact_id,
            "strategy_group_id": None,
            "symbol": observation.symbol,
            "side": None,
            "runtime_profile_id": runtime_profile_id,
            "fact_surface": "exchange_metadata",
            "source_kind": "binance_usdm_readonly_get",
            "source_ref": observation.source_ref,
            "computed": True,
            "satisfied": True,
            "freshness_state": "fresh",
            "failed_facts": [],
            "fact_values": {
                "exchange_instrument_id": observation.exchange_instrument_id,
                "price_tick": str(observation.price_tick),
                "quantity_step": str(observation.quantity_step),
                "min_qty": str(observation.min_qty),
                "min_notional": str(observation.min_notional),
                "contract_multiplier": str(observation.contract_multiplier),
                "claim_notional_ceiling": str(observation.claim_notional_ceiling),
                "exchange_max_leverage_for_claim_notional": (
                    observation.exchange_max_leverage_for_claim_notional
                ),
                "risk_calculation_kind": "linear_quote_settled",
            },
            "blocker_class": None,
            "observed_at_ms": observation.observed_at_ms,
            "valid_until_ms": observation.valid_until_ms,
            "created_at_ms": observation.observed_at_ms,
        }
        if conn.execute(
            sa.select(fact_table.c.fact_snapshot_id).where(
                fact_table.c.fact_snapshot_id == source_fact_id
            )
        ).scalar_one_or_none() is None:
            conn.execute(
                fact_table.insert().values(**_filtered_row(fact_table, fact_row))
            )
            source_fact_inserted_count += 1

        rule_id = _stable_id(
            "instrument_rule_snapshot",
            observation.exchange_instrument_id,
            source_fact_id,
            str(observation.valid_until_ms),
            str(observation.price_tick),
            str(observation.quantity_step),
            str(observation.min_qty),
            str(observation.min_notional),
            str(observation.exchange_max_leverage_for_claim_notional),
        )
        rule_values: dict[str, object] = {
            "instrument_rule_snapshot_id": rule_id,
            "exchange_instrument_id": observation.exchange_instrument_id,
            "rule_schema_version": "v2",
            "price_tick": observation.price_tick,
            "quantity_step": observation.quantity_step,
            "min_qty": observation.min_qty,
            "min_notional": observation.min_notional,
            "contract_multiplier": observation.contract_multiplier,
            "exchange_max_leverage_for_claim_notional": (
                observation.exchange_max_leverage_for_claim_notional
            ),
            "source_fact_snapshot_id": source_fact_id,
            "valid_until_ms": observation.valid_until_ms,
            "risk_calculation_kind": "linear_quote_settled",
        }
        rule_values["semantic_hash"] = instrument_rule_snapshot_v2_semantic_hash(
            rule_values
        )
        validated = InstrumentRuleSnapshotRefV2.model_validate(
            {
                key: value
                for key, value in rule_values.items()
                if key != "exchange_instrument_id"
            }
        )
        current_rows = conn.execute(
            sa.select(rule_table)
            .where(
                rule_table.c.exchange_instrument_id
                == observation.exchange_instrument_id
            )
            .where(rule_table.c.status == "current")
            .limit(2)
            .with_for_update()
        ).mappings().all()
        if len(current_rows) > 1:
            raise InstrumentRuleProjectionError(
                "instrument_rule_snapshot_current_ambiguous"
            )
        if current_rows and current_rows[0].get("semantic_hash") == validated.semantic_hash:
            rule_unchanged_count += 1
            current_rule_ids.append(str(current_rows[0]["instrument_rule_snapshot_id"]))
            continue
        supersedes_id = None
        if current_rows:
            supersedes_id = str(current_rows[0]["instrument_rule_snapshot_id"])
            changed = conn.execute(
                rule_table.update()
                .where(rule_table.c.instrument_rule_snapshot_id == supersedes_id)
                .where(rule_table.c.status == "current")
                .values(status="superseded")
            )
            if int(changed.rowcount or 0) != 1:
                raise InstrumentRuleProjectionError(
                    "instrument_rule_snapshot_current_changed"
                )
            rule_superseded_count += 1
        persisted = {
            **rule_values,
            "supersedes_instrument_rule_snapshot_id": supersedes_id,
            "status": "current",
            "created_at_ms": observation.observed_at_ms,
        }
        conn.execute(
            rule_table.insert().values(**_filtered_row(rule_table, persisted))
        )
        rule_inserted_count += 1
        current_rule_ids.append(rule_id)

    return InstrumentRuleProjectionResult(
        target_count=len(observations),
        source_fact_inserted_count=source_fact_inserted_count,
        rule_inserted_count=rule_inserted_count,
        rule_unchanged_count=rule_unchanged_count,
        rule_superseded_count=rule_superseded_count,
        current_rule_ids=tuple(current_rule_ids),
    )


def _leverage_for_notional(value: object, notional: Decimal) -> int:
    if not isinstance(value, list):
        raise InstrumentRuleProjectionError("leverage_bracket_shape_invalid")
    matches: list[int] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        floor = _optional_decimal(item.get("notionalFloor"))
        cap = _optional_decimal(item.get("notionalCap"))
        leverage = item.get("initialLeverage")
        if (
            floor is None
            or cap is None
            or not isinstance(leverage, int)
            or not 1 <= leverage <= 125
        ):
            continue
        if floor <= notional < cap:
            matches.append(leverage)
    if len(matches) != 1:
        raise InstrumentRuleProjectionError("claim_notional_leverage_bracket_invalid")
    return matches[0]


def _positive_decimal(value: object) -> Decimal:
    result = _optional_decimal(value)
    if result is None or result <= 0:
        raise ValueError("positive Decimal required")
    return result


def _optional_decimal(value: object) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def _stable_id(prefix: str, *parts: str) -> str:
    digest = sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:{digest}"


def _filtered_row(table: sa.Table, row: dict[str, Any]) -> dict[str, Any]:
    columns = {str(column.name) for column in table.columns}
    return {key: value for key, value in row.items() if key in columns}
