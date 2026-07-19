from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa

from src.application.action_time.instrument_rule_projector import (
    ActiveInstrumentRuleTarget,
    InstrumentRuleProjectionError,
    InstrumentRuleObservation,
    load_active_instrument_rule_targets,
    parse_binance_usdm_instrument_rule_observations,
    project_current_instrument_rules,
)
from src.domain.instrument_risk_identity import (
    InstrumentRiskIdentity,
    build_canonical_exchange_instrument_id,
)


def test_parse_binance_rules_uses_market_entry_quantity_and_claim_bracket() -> None:
    target = _target("BTCUSDT", "BTC/USDT:USDT", Decimal("20"))

    observations = parse_binance_usdm_instrument_rule_observations(
        targets=(target,),
        exchange_info_payload=_exchange_info("BTCUSDT"),
        leverage_bracket_payload=_leverage_brackets("BTCUSDT"),
        observed_at_ms=1000,
        valid_until_ms=2000,
        source_ref="unit:binance-readonly",
    )

    assert observations == (
        InstrumentRuleObservation(
            exchange_instrument_id=target.identity.exchange_instrument_id,
            symbol="BTCUSDT",
            price_tick=Decimal("0.10"),
            quantity_step=Decimal("0.001"),
            min_qty=Decimal("0.001"),
            min_notional=Decimal("5"),
            contract_multiplier=Decimal("1"),
            exchange_max_leverage_for_claim_notional=20,
            claim_notional_ceiling=Decimal("20"),
            observed_at_ms=1000,
            valid_until_ms=2000,
            source_ref="unit:binance-readonly",
        ),
    )


def test_parse_binance_rules_rejects_missing_notional_bracket() -> None:
    target = _target("BTCUSDT", "BTC/USDT:USDT", Decimal("2000"))

    with pytest.raises(
        InstrumentRuleProjectionError,
        match="claim_notional_leverage_bracket_invalid",
    ):
        parse_binance_usdm_instrument_rule_observations(
            targets=(target,),
            exchange_info_payload=_exchange_info("BTCUSDT"),
            leverage_bracket_payload=_leverage_brackets("BTCUSDT"),
            observed_at_ms=1000,
            valid_until_ms=2000,
            source_ref="unit:binance-readonly",
        )


def test_load_targets_uses_exact_candidate_identity_without_symbol_mapping() -> None:
    engine = sa.create_engine("sqlite://")
    target = _target("BTCUSDT", "BTC/USDT:USDT", Decimal("20"))
    with engine.begin() as conn:
        _create_target_tables(conn)
        conn.execute(
            sa.text(
                """INSERT INTO brc_exchange_instruments VALUES
                (:instrument_id, 'binance_usdm', 'BTC/USDT:USDT', 'crypto',
                 'perpetual', 'USDT', 'USDT', 'v2', 'active')"""
            ),
            {"instrument_id": target.identity.exchange_instrument_id},
        )
        conn.execute(
            sa.text(
                """INSERT INTO brc_owner_policy_current VALUES
                ('policy-1', 20)"""
            )
        )
        conn.execute(
            sa.text(
                """INSERT INTO brc_strategy_group_candidate_scope VALUES
                ('scope-1', 'BTCUSDT', :instrument_id, 'policy-1',
                 'live_submit_allowed', 'active')"""
            ),
            {"instrument_id": target.identity.exchange_instrument_id},
        )
        conn.execute(
            sa.text(
                """INSERT INTO brc_runtime_scope_bindings VALUES
                ('scope-1', 'owner-runtime-console-v1', 'active')"""
            )
        )

        loaded = load_active_instrument_rule_targets(
            conn,
            runtime_profile_id="owner-runtime-console-v1",
            expected_instrument_count=1,
        )

    assert loaded == (target,)


def test_rule_projection_is_idempotent_and_supersedes_changed_current() -> None:
    engine = sa.create_engine("sqlite://")
    first = InstrumentRuleObservation(
        exchange_instrument_id="instrument-1",
        symbol="BTCUSDT",
        price_tick=Decimal("0.10"),
        quantity_step=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        min_notional=Decimal("5"),
        contract_multiplier=Decimal("1"),
        exchange_max_leverage_for_claim_notional=20,
        claim_notional_ceiling=Decimal("20"),
        observed_at_ms=1000,
        valid_until_ms=2000,
        source_ref="unit:first",
    )
    changed = first.model_copy(
        update={
            "price_tick": Decimal("0.01"),
            "observed_at_ms": 1100,
            "valid_until_ms": 2100,
            "source_ref": "unit:changed",
        }
    )
    with engine.begin() as conn:
        _create_projection_tables(conn)
        first_result = project_current_instrument_rules(
            conn,
            observations=(first,),
            runtime_profile_id="profile-1",
            expected_instrument_count=1,
        )
        repeated_result = project_current_instrument_rules(
            conn,
            observations=(first,),
            runtime_profile_id="profile-1",
            expected_instrument_count=1,
        )
        changed_result = project_current_instrument_rules(
            conn,
            observations=(changed,),
            runtime_profile_id="profile-1",
            expected_instrument_count=1,
        )
        statuses = conn.execute(
            sa.text(
                """SELECT status, count(*)
                FROM brc_instrument_rule_snapshots
                GROUP BY status ORDER BY status"""
            )
        ).all()
        current = conn.execute(
            sa.text(
                """SELECT price_tick, risk_calculation_kind
                FROM brc_instrument_rule_snapshots
                WHERE status = 'current'"""
            )
        ).one()

    assert first_result.rule_inserted_count == 1
    assert repeated_result.rule_unchanged_count == 1
    assert repeated_result.source_fact_inserted_count == 0
    assert changed_result.rule_inserted_count == 1
    assert changed_result.rule_superseded_count == 1
    assert statuses == [("current", 1), ("superseded", 1)]
    assert Decimal(str(current[0])) == Decimal("0.01")
    assert current[1] == "linear_quote_settled"


def _target(
    symbol: str,
    exchange_symbol: str,
    claim_notional_ceiling: Decimal,
) -> ActiveInstrumentRuleTarget:
    instrument_id = build_canonical_exchange_instrument_id(
        exchange_id="binance_usdm",
        exchange_symbol=exchange_symbol,
        asset_class="crypto",
        instrument_type="perpetual",
        settlement_asset="USDT",
        margin_asset="USDT",
    )
    return ActiveInstrumentRuleTarget(
        identity=InstrumentRiskIdentity(
            exchange_instrument_id=instrument_id,
            exchange_id="binance_usdm",
            exchange_symbol=exchange_symbol,
            asset_class="crypto",
            instrument_type="perpetual",
            settlement_asset="USDT",
            margin_asset="USDT",
            instrument_identity_schema_version="v2",
        ),
        symbol=symbol,
        claim_notional_ceiling=claim_notional_ceiling,
    )


def _exchange_info(symbol: str) -> dict[str, object]:
    return {
        "symbols": [
            {
                "symbol": symbol,
                "status": "TRADING",
                "contractType": "PERPETUAL",
                "quoteAsset": "USDT",
                "marginAsset": "USDT",
                "filters": [
                    {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                    {
                        "filterType": "LOT_SIZE",
                        "minQty": "0.01",
                        "stepSize": "0.01",
                    },
                    {
                        "filterType": "MARKET_LOT_SIZE",
                        "minQty": "0.001",
                        "stepSize": "0.001",
                    },
                    {"filterType": "MIN_NOTIONAL", "notional": "5"},
                ],
            }
        ]
    }


def _leverage_brackets(symbol: str) -> list[dict[str, object]]:
    return [
        {
            "symbol": symbol,
            "brackets": [
                {
                    "notionalFloor": 0,
                    "notionalCap": 1000,
                    "initialLeverage": 20,
                }
            ],
        }
    ]


def _create_target_tables(conn: sa.Connection) -> None:
    for statement in (
        """CREATE TABLE brc_exchange_instruments (
        exchange_instrument_id TEXT, exchange_id TEXT, exchange_symbol TEXT,
        asset_class TEXT, instrument_type TEXT, settlement_asset TEXT,
        margin_asset TEXT, instrument_identity_schema_version TEXT, status TEXT)""",
        """CREATE TABLE brc_owner_policy_current (
        policy_current_id TEXT, max_notional NUMERIC)""",
        """CREATE TABLE brc_strategy_group_candidate_scope (
        candidate_scope_id TEXT, symbol TEXT, exchange_instrument_id TEXT,
        policy_current_id TEXT, scope_state TEXT, status TEXT)""",
        """CREATE TABLE brc_runtime_scope_bindings (
        candidate_scope_id TEXT, runtime_profile_id TEXT, status TEXT)""",
    ):
        conn.execute(sa.text(statement))


def _create_projection_tables(conn: sa.Connection) -> None:
    conn.execute(
        sa.text(
            """CREATE TABLE brc_runtime_fact_snapshots (
            fact_snapshot_id TEXT PRIMARY KEY, strategy_group_id TEXT,
            symbol TEXT, side TEXT, runtime_profile_id TEXT, fact_surface TEXT,
            source_kind TEXT, source_ref TEXT, computed BOOLEAN,
            satisfied BOOLEAN, freshness_state TEXT, failed_facts JSON,
            fact_values JSON, blocker_class TEXT, observed_at_ms BIGINT,
            valid_until_ms BIGINT, created_at_ms BIGINT)"""
        )
    )
    conn.execute(
        sa.text(
            """CREATE TABLE brc_instrument_rule_snapshots (
            instrument_rule_snapshot_id TEXT PRIMARY KEY,
            exchange_instrument_id TEXT, rule_schema_version TEXT,
            price_tick NUMERIC, quantity_step NUMERIC, min_qty NUMERIC,
            min_notional NUMERIC, contract_multiplier NUMERIC,
            exchange_max_leverage_for_claim_notional INTEGER,
            source_fact_snapshot_id TEXT, valid_until_ms BIGINT,
            risk_calculation_kind TEXT, semantic_hash TEXT,
            supersedes_instrument_rule_snapshot_id TEXT, status TEXT,
            created_at_ms BIGINT)"""
        )
    )
