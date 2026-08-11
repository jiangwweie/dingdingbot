"""Add product compatibility, instrument catalog, and current Session facts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_tradfi_instrument_center"
down_revision: str | None = "0004_owner_control_plane"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ID = sa.String(160)
SHORT_TEXT = sa.String(96)
LONG_TEXT = sa.String(512)
MONEY = sa.Numeric(38, 18)

_TRADFI_CANDIDATES = (
    "AAPL",
    "GOOGL",
    "MSFT",
    "NVDA",
    "META",
    "AMZN",
    "TSLA",
    "SNDK",
)
_TRADFI_REFERENCES = ("QQQ", "SPY")


def upgrade() -> None:
    _assert_flat_source()
    _upgrade_shadow_observation()
    op.drop_constraint(
        "ck_brc_owner_authorizations_purpose_valid",
        "brc_owner_authorizations",
        type_="check",
    )
    op.create_check_constraint(
        "ck_brc_owner_authorizations_purpose_valid",
        "brc_owner_authorizations",
        "purpose IN ('strategy_pause', 'strategy_resume', 'entry_pause', "
        "'entry_resume', 'owner_flatten_all', 'universe_configure')",
    )
    op.create_table(
        "brc_event_product_compatibility",
        sa.Column("event_spec_id", ID, primary_key=True),
        sa.Column("product_family", SHORT_TEXT, nullable=False),
        sa.Column("asset_class", SHORT_TEXT, nullable=False),
        sa.Column("contract_type", SHORT_TEXT, nullable=False),
        sa.Column("underlying_type", SHORT_TEXT, nullable=False),
        sa.Column("margin_asset", SHORT_TEXT, nullable=False),
        sa.Column("semantic_digest", LONG_TEXT, nullable=False),
        sa.Column("created_at_ms", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_spec_id"],
            ["brc_event_specs.event_spec_id"],
        ),
        sa.CheckConstraint(
            "product_family IN ('crypto_perpetual', 'tradfi_equity_perpetual')",
            name="ck_brc_event_product_compatibility_product_family_valid",
        ),
        sa.CheckConstraint(
            "asset_class IN ('crypto', 'equity')",
            name="ck_brc_event_product_compatibility_asset_class_valid",
        ),
        sa.CheckConstraint(
            "semantic_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_brc_event_product_compatibility_semantic_digest_valid",
        ),
    )
    op.create_table(
        "brc_instrument_product_profiles",
        sa.Column("exchange_instrument_id", ID, primary_key=True),
        sa.Column("product_family", SHORT_TEXT, nullable=False),
        sa.Column("asset_class", SHORT_TEXT, nullable=False),
        sa.Column("contract_type", SHORT_TEXT, nullable=False),
        sa.Column("underlying_type", SHORT_TEXT, nullable=False),
        sa.Column("margin_asset", SHORT_TEXT, nullable=False),
        sa.Column("entry_session_policy", SHORT_TEXT, nullable=False),
        sa.Column("status", SHORT_TEXT, nullable=False),
        sa.Column("semantic_digest", LONG_TEXT, nullable=False),
        sa.Column("updated_at_ms", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "product_family IN ('crypto_perpetual', 'tradfi_equity_perpetual')",
            name="ck_brc_instrument_product_profiles_product_family_valid",
        ),
        sa.CheckConstraint(
            "asset_class IN ('crypto', 'equity')",
            name="ck_brc_instrument_product_profiles_asset_class_valid",
        ),
        sa.CheckConstraint(
            "entry_session_policy IN ('continuous', 'regular_only', 'reference_only')",
            name="ck_brc_instrument_product_profiles_session_policy_valid",
        ),
        sa.CheckConstraint(
            "status IN ('candidate', 'reference', 'active', 'retired')",
            name="ck_brc_instrument_product_profiles_status_valid",
        ),
        sa.CheckConstraint(
            "semantic_digest ~ '^sha256:[0-9a-f]{64}$'",
            name="ck_brc_instrument_product_profiles_semantic_digest_valid",
        ),
    )
    op.create_table(
        "brc_instrument_product_current",
        sa.Column("exchange_instrument_id", ID, primary_key=True),
        sa.Column("product_status", SHORT_TEXT, nullable=False),
        sa.Column("session_state", SHORT_TEXT, nullable=False),
        sa.Column("regular_session_open_ms", sa.BigInteger(), nullable=True),
        sa.Column("regular_session_close_ms", sa.BigInteger(), nullable=True),
        sa.Column("mark_price", MONEY, nullable=True),
        sa.Column("index_price", MONEY, nullable=True),
        sa.Column("funding_rate", MONEY, nullable=True),
        sa.Column("best_bid", MONEY, nullable=True),
        sa.Column("best_ask", MONEY, nullable=True),
        sa.Column("best_bid_quantity", MONEY, nullable=True),
        sa.Column("best_ask_quantity", MONEY, nullable=True),
        sa.Column("corporate_event_status", SHORT_TEXT, nullable=False),
        sa.Column("observed_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("valid_until_ms", sa.BigInteger(), nullable=False),
        sa.Column("source_ref", LONG_TEXT, nullable=False),
        sa.Column("projection_version", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["exchange_instrument_id"],
            ["brc_instrument_product_profiles.exchange_instrument_id"],
        ),
        sa.CheckConstraint(
            "product_status IN ('active', 'inactive', 'temporarily_unavailable')",
            name="ck_brc_instrument_product_current_status_valid",
        ),
        sa.CheckConstraint(
            "session_state IN ('pre_market', 'regular', 'after_market', 'overnight', 'no_trading', 'unavailable')",
            name="ck_brc_instrument_product_current_session_valid",
        ),
        sa.CheckConstraint(
            "corporate_event_status IN ('clear', 'blocked', 'unavailable')",
            name="ck_brc_instrument_product_current_corporate_event_valid",
        ),
        sa.CheckConstraint(
            "valid_until_ms > observed_at_ms",
            name="ck_brc_instrument_product_current_validity_valid",
        ),
        sa.CheckConstraint(
            "(regular_session_open_ms IS NULL AND regular_session_close_ms IS NULL) OR "
            "(regular_session_open_ms IS NOT NULL AND regular_session_close_ms > regular_session_open_ms)",
            name="ck_brc_instrument_product_current_regular_window_valid",
        ),
        sa.CheckConstraint(
            "projection_version > 0",
            name="ck_brc_instrument_product_current_projection_version_positive",
        ),
    )
    op.create_index(
        "ix_brc_instrument_product_current_session_status",
        "brc_instrument_product_current",
        ["session_state", "product_status", "valid_until_ms"],
    )
    _replace_universe_member_guard()
    _seed_product_catalog()


def downgrade() -> None:
    raise RuntimeError("0005_tradfi_instrument_center is fix-forward only")


def _assert_flat_source() -> None:
    connection = op.get_bind()
    checks = {
        "nonterminal_ticket": "SELECT count(*) FROM brc_trade_aggregates WHERE status NOT IN ('terminal', 'leverage_rejected', 'entry_rejected', 'entry_reconciled_absent')",
        "nonflat_position": "SELECT count(*) FROM brc_positions_current WHERE quantity <> 0",
        "active_reservation": "SELECT count(*) FROM brc_budget_reservations WHERE status = 'active'",
        "unresolved_command": "SELECT count(*) FROM brc_exchange_commands WHERE status IN ('prepared', 'claimed', 'dispatch_started', 'outcome_unknown')",
        "open_incident": "SELECT count(*) FROM brc_runtime_incidents WHERE status = 'open'",
    }
    blockers = [
        name
        for name, query in checks.items()
        if int(connection.scalar(sa.text(query)) or 0) != 0
    ]
    if blockers:
        raise RuntimeError(
            "0005 migration requires exact flat source: " + ",".join(blockers)
        )


def _upgrade_shadow_observation() -> None:
    table = "brc_shadow_outcomes_current"
    op.add_column(table, sa.Column("signal_event_id", ID, nullable=True))
    op.add_column(table, sa.Column("source_kind", SHORT_TEXT, nullable=True))
    op.add_column(table, sa.Column("take_profit_price", MONEY, nullable=True))
    op.add_column(
        table,
        sa.Column("opening_range_boundary_price", MONEY, nullable=True),
    )
    op.add_column(
        table,
        sa.Column("session_exit_deadline_ms", sa.BigInteger(), nullable=True),
    )
    op.add_column(table, sa.Column("mark_price", MONEY, nullable=True))
    op.add_column(table, sa.Column("index_price", MONEY, nullable=True))
    op.add_column(table, sa.Column("funding_rate", MONEY, nullable=True))
    op.add_column(table, sa.Column("best_bid_price", MONEY, nullable=True))
    op.add_column(table, sa.Column("best_ask_price", MONEY, nullable=True))
    op.add_column(table, sa.Column("best_bid_quantity", MONEY, nullable=True))
    op.add_column(table, sa.Column("best_ask_quantity", MONEY, nullable=True))
    op.add_column(table, sa.Column("spread_bps", MONEY, nullable=True))
    op.add_column(
        table,
        sa.Column("mark_index_deviation_bps", MONEY, nullable=True),
    )
    op.add_column(table, sa.Column("first_path", SHORT_TEXT, nullable=True))
    op.add_column(
        table,
        sa.Column("first_path_at_ms", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        table,
        sa.Column("observed_bar_count", sa.BigInteger(), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE brc_shadow_outcomes_current AS shadow
               SET signal_event_id = decision.signal_event_id,
                   source_kind = 'portfolio_rejection'
              FROM brc_admission_decisions AS decision
             WHERE decision.admission_decision_id = shadow.admission_decision_id
            """
        )
    )
    connection = op.get_bind()
    unresolved = int(
        connection.scalar(
            sa.text(
                "SELECT count(*) FROM brc_shadow_outcomes_current "
                "WHERE signal_event_id IS NULL OR source_kind IS NULL"
            )
        )
        or 0
    )
    if unresolved:
        raise RuntimeError("0005 cannot bind existing Shadow Outcomes to Signals")
    op.alter_column(table, "signal_event_id", nullable=False)
    op.alter_column(table, "source_kind", nullable=False)
    op.alter_column(table, "admission_decision_id", nullable=True)
    op.alter_column(table, "entry_reference_price", nullable=True)
    op.alter_column(table, "initial_stop_price", nullable=True)
    op.alter_column(table, "initial_risk_per_unit", nullable=True)
    op.create_unique_constraint(
        "uq_brc_shadow_outcomes_current_signal_event_id",
        table,
        ["signal_event_id"],
    )
    for name in (
        "ck_brc_shadow_outcomes_current_evaluation_kind_valid",
        "ck_brc_shadow_outcomes_current_risk_horizon_valid",
        "ck_brc_shadow_outcomes_current_lease_shape_valid",
    ):
        op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(
        "ck_brc_shadow_outcomes_current_source_kind_valid",
        table,
        "(source_kind = 'portfolio_rejection' "
        "AND admission_decision_id IS NOT NULL "
        "AND evaluation_kind = 'fixed_horizon_excursion_v1') OR "
        "(source_kind = 'strategy_observation' "
        "AND admission_decision_id IS NULL "
        "AND evaluation_kind = 'sor_path_observation_v1')",
    )
    op.create_check_constraint(
        "ck_brc_shadow_outcomes_current_evaluation_kind_valid",
        table,
        "evaluation_kind IN ('fixed_horizon_excursion_v1', "
        "'sor_path_observation_v1')",
    )
    op.create_check_constraint(
        "ck_brc_shadow_outcomes_current_risk_horizon_valid",
        table,
        "(initial_risk_per_unit IS NULL OR initial_risk_per_unit >= 0) "
        "AND horizon_end_ms > horizon_start_ms "
        "AND (session_exit_deadline_ms IS NULL "
        "OR session_exit_deadline_ms > horizon_start_ms)",
    )
    op.create_check_constraint(
        "ck_brc_shadow_outcomes_current_path_valid",
        table,
        "first_path IS NULL OR first_path IN ("
        "'tp1_first', 'initial_stop_first', 'ambiguous_same_bar', "
        "'opening_range_failure', 'time_stop', 'session_exit', "
        "'horizon_complete')",
    )
    op.create_check_constraint(
        "ck_brc_shadow_outcomes_current_lease_shape_valid",
        table,
        "(status IN ('pending', 'claimed', 'completed') "
        "AND entry_reference_price IS NOT NULL "
        "AND initial_stop_price IS NOT NULL "
        "AND initial_risk_per_unit IS NOT NULL) OR status = 'unavailable'",
    )
    op.create_check_constraint(
        "ck_brc_shadow_outcomes_current_projection_shape_valid",
        table,
        "(status = 'claimed' AND claim_owner IS NOT NULL "
        "AND claim_token IS NOT NULL AND lease_until_ms IS NOT NULL "
        "AND completed_at_ms IS NULL AND max_favorable_price IS NULL "
        "AND max_adverse_price IS NULL AND mfe_r IS NULL AND mae_r IS NULL "
        "AND observed_through_ms IS NULL AND completion_reason IS NULL "
        "AND first_path IS NULL AND first_path_at_ms IS NULL "
        "AND observed_bar_count IS NULL) OR "
        "(status = 'pending' AND claim_owner IS NULL "
        "AND claim_token IS NULL AND lease_until_ms IS NULL "
        "AND completed_at_ms IS NULL AND max_favorable_price IS NULL "
        "AND max_adverse_price IS NULL AND mfe_r IS NULL AND mae_r IS NULL "
        "AND observed_through_ms IS NULL AND completion_reason IS NULL "
        "AND first_path IS NULL AND first_path_at_ms IS NULL "
        "AND observed_bar_count IS NULL) OR "
        "(status = 'completed' AND claim_owner IS NULL "
        "AND claim_token IS NULL AND lease_until_ms IS NULL "
        "AND completed_at_ms IS NOT NULL AND max_favorable_price IS NOT NULL "
        "AND max_adverse_price IS NOT NULL AND mfe_r IS NOT NULL "
        "AND mae_r IS NOT NULL AND observed_through_ms IS NOT NULL "
        "AND completion_reason IS NOT NULL "
        "AND ((evaluation_kind = 'fixed_horizon_excursion_v1' "
        "AND first_path IS NULL AND first_path_at_ms IS NULL "
        "AND observed_bar_count IS NULL) OR "
        "(evaluation_kind = 'sor_path_observation_v1' "
        "AND first_path IS NOT NULL AND first_path_at_ms IS NOT NULL "
        "AND observed_bar_count > 0))) OR "
        "(status = 'unavailable' AND claim_owner IS NULL "
        "AND claim_token IS NULL AND lease_until_ms IS NULL "
        "AND completed_at_ms IS NOT NULL AND max_favorable_price IS NULL "
        "AND max_adverse_price IS NULL AND mfe_r IS NULL AND mae_r IS NULL "
        "AND observed_through_ms IS NULL AND completion_reason IS NOT NULL "
        "AND first_path IS NULL AND first_path_at_ms IS NULL "
        "AND observed_bar_count IS NULL)",
    )


def _replace_universe_member_guard() -> None:
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION brc_enforce_universe_member_limit()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE
                identity_compatible boolean;
            BEGIN
                SELECT
                    i.venue_id = 'binance-usdm'
                    AND i.asset_class IN ('crypto', 'equity')
                    AND i.venue_symbol ~ '^[A-Z0-9]+USDT$'
                    AND i.contract_kind = 'perpetual'
                    AND i.exchange_instrument_id =
                        'binance-usdm' || chr(58) || i.venue_symbol
                        || chr(58) || 'perpetual'
                    AND p.asset_class = i.asset_class
                    AND p.status IN ('candidate', 'active')
                    AND p.entry_session_policy <> 'reference_only'
                    AND p.product_family = c.product_family
                    AND p.asset_class = c.asset_class
                    AND p.contract_type = c.contract_type
                    AND p.underlying_type = c.underlying_type
                    AND p.margin_asset = c.margin_asset
                INTO identity_compatible
                FROM brc_instruments i
                JOIN brc_instrument_product_profiles p
                  ON p.exchange_instrument_id = i.exchange_instrument_id
                JOIN brc_strategy_universe_versions u
                  ON u.universe_version_id = NEW.universe_version_id
                JOIN brc_event_product_compatibility c
                  ON c.event_spec_id = u.event_spec_id
                WHERE i.exchange_instrument_id = NEW.exchange_instrument_id;

                IF identity_compatible IS DISTINCT FROM true THEN
                    RAISE EXCEPTION
                        'strategy universe member product compatibility mismatch'
                        USING ERRCODE = '23514',
                              CONSTRAINT = 'ck_brc_universe_member_product';
                END IF;

                PERFORM 1
                FROM brc_strategy_universe_versions
                WHERE universe_version_id = NEW.universe_version_id
                FOR UPDATE;

                IF (
                    SELECT count(*)
                    FROM brc_strategy_universe_members
                    WHERE universe_version_id = NEW.universe_version_id
                ) >= 10 THEN
                    RAISE EXCEPTION
                        'strategy universe cardinality cannot exceed 10'
                        USING ERRCODE = '23514',
                              CONSTRAINT = 'ck_brc_universe_members_max_ten';
                END IF;
                RETURN NEW;
            END
            $$;
            """
        )
    )


def _seed_product_catalog() -> None:
    connection = op.get_bind()
    now_ms = int(
        connection.scalar(
            sa.text(
                "SELECT floor(extract(epoch FROM clock_timestamp()) * 1000)::bigint"
            )
        )
    )
    existing = connection.execute(
        sa.text(
            "SELECT exchange_instrument_id, asset_class FROM brc_instruments "
            "ORDER BY exchange_instrument_id"
        )
    ).all()
    profiles = [
        _profile(
            exchange_instrument_id=str(row[0]),
            tradfi=str(row[1]) == "equity",
            reference=False,
            updated_at_ms=now_ms,
        )
        for row in existing
    ]
    profiles.extend(
        _profile(
            exchange_instrument_id=f"binance-usdm:{symbol}USDT:perpetual",
            tradfi=True,
            reference=symbol in _TRADFI_REFERENCES,
            updated_at_ms=now_ms,
        )
        for symbol in (*_TRADFI_CANDIDATES, *_TRADFI_REFERENCES)
    )
    table = sa.table(
        "brc_instrument_product_profiles",
        sa.column("exchange_instrument_id"),
        sa.column("product_family"),
        sa.column("asset_class"),
        sa.column("contract_type"),
        sa.column("underlying_type"),
        sa.column("margin_asset"),
        sa.column("entry_session_policy"),
        sa.column("status"),
        sa.column("semantic_digest"),
        sa.column("updated_at_ms"),
    )
    unique = {str(item["exchange_instrument_id"]): item for item in profiles}
    if unique:
        connection.execute(sa.insert(table), list(unique.values()))
    current = sa.table(
        "brc_instrument_product_current",
        sa.column("exchange_instrument_id"),
        sa.column("product_status"),
        sa.column("session_state"),
        sa.column("regular_session_open_ms"),
        sa.column("regular_session_close_ms"),
        sa.column("mark_price"),
        sa.column("index_price"),
        sa.column("funding_rate"),
        sa.column("best_bid"),
        sa.column("best_ask"),
        sa.column("best_bid_quantity"),
        sa.column("best_ask_quantity"),
        sa.column("corporate_event_status"),
        sa.column("observed_at_ms"),
        sa.column("valid_until_ms"),
        sa.column("source_ref"),
        sa.column("projection_version"),
    )
    tradfi_ids = tuple(
        f"binance-usdm:{symbol}USDT:perpetual"
        for symbol in (*_TRADFI_CANDIDATES, *_TRADFI_REFERENCES)
    )
    connection.execute(
        sa.insert(current),
        [
            {
                "exchange_instrument_id": instrument_id,
                "product_status": "temporarily_unavailable",
                "session_state": "unavailable",
                "regular_session_open_ms": None,
                "regular_session_close_ms": None,
                "mark_price": None,
                "index_price": None,
                "funding_rate": None,
                "best_bid": None,
                "best_ask": None,
                "best_bid_quantity": None,
                "best_ask_quantity": None,
                "corporate_event_status": "unavailable",
                "observed_at_ms": now_ms,
                "valid_until_ms": now_ms + 900_000,
                "source_ref": "migration:0005:awaiting_readonly_refresh",
                "projection_version": 1,
            }
            for instrument_id in tradfi_ids
        ],
    )


def _profile(
    *,
    exchange_instrument_id: str,
    tradfi: bool,
    reference: bool,
    updated_at_ms: int,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "exchange_instrument_id": exchange_instrument_id,
        "product_family": (
            "tradfi_equity_perpetual" if tradfi else "crypto_perpetual"
        ),
        "asset_class": "equity" if tradfi else "crypto",
        "contract_type": "TRADIFI_PERPETUAL" if tradfi else "PERPETUAL",
        "underlying_type": "EQUITY" if tradfi else "CRYPTO",
        "margin_asset": "USDT",
        "entry_session_policy": (
            "reference_only"
            if reference
            else "regular_only"
            if tradfi
            else "continuous"
        ),
        "status": "reference" if reference else "candidate",
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return {
        **payload,
        "semantic_digest": f"sha256:{hashlib.sha256(encoded).hexdigest()}",
        "updated_at_ms": updated_at_ms,
    }
