"""Create the exact historical Trading Kernel v4 database baseline."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from migrations.trading_kernel.v4_schema import metadata

revision: str = "0001_trading_kernel_baseline_v4"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Build v4 from migration-owned metadata that can never drift with head."""
    metadata.create_all(op.get_bind(), checkfirst=False)
    _create_universe_member_guards()
    _create_instrument_identity_guard()
    _create_universe_activation_entry_fence()
    _create_certification_batch_guards()


def _create_universe_member_guards() -> None:
    """Keep Universe membership canonical, bounded, and append-only in PostgreSQL."""
    op.execute(
        sa.text(
            """
            CREATE FUNCTION brc_enforce_universe_member_limit()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE
                instrument_exists boolean;
                instrument_is_crypto_usdt_perpetual boolean;
            BEGIN
                SELECT
                    true,
                    venue_id = 'binance-usdm'
                    AND asset_class = 'crypto'
                    AND venue_symbol ~ '^[A-Z0-9]+USDT$'
                    AND contract_kind = 'perpetual'
                    AND exchange_instrument_id =
                        'binance-usdm' || chr(58) || venue_symbol
                        || chr(58) || 'perpetual'
                INTO
                    instrument_exists,
                    instrument_is_crypto_usdt_perpetual
                FROM brc_instruments
                WHERE exchange_instrument_id = NEW.exchange_instrument_id;

                IF instrument_exists
                   AND NOT instrument_is_crypto_usdt_perpetual THEN
                    RAISE EXCEPTION
                        'strategy universe member must be a canonical '
                        'Binance USD-M USDT perpetual'
                        USING ERRCODE = '23514',
                              CONSTRAINT = 'ck_brc_universe_member_crypto';
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
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_brc_universe_members_max_ten
            BEFORE INSERT ON brc_strategy_universe_members
            FOR EACH ROW
            EXECUTE FUNCTION brc_enforce_universe_member_limit();
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE FUNCTION brc_reject_universe_member_mutation()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION
                    'strategy universe members are immutable'
                    USING ERRCODE = '23514',
                          CONSTRAINT = 'ck_brc_universe_member_immutable';
            END
            $$;
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_brc_universe_member_immutable
            BEFORE UPDATE OR DELETE ON brc_strategy_universe_members
            FOR EACH ROW
            EXECUTE FUNCTION brc_reject_universe_member_mutation();
            """
        )
    )


def _create_instrument_identity_guard() -> None:
    """Forbid rewriting a referenced instrument into a different identity."""
    op.execute(
        sa.text(
            """
            CREATE FUNCTION brc_reject_instrument_identity_mutation()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION
                    'instrument identity fields are immutable'
                    USING ERRCODE = '23514',
                          CONSTRAINT = 'ck_brc_instrument_identity_immutable';
            END
            $$;
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_brc_instrument_identity_immutable
            BEFORE UPDATE OF
                exchange_instrument_id,
                venue_id,
                asset_class,
                venue_symbol,
                contract_kind
            ON brc_instruments
            FOR EACH ROW
            EXECUTE FUNCTION brc_reject_instrument_identity_mutation();
            """
        )
    )


def _create_universe_activation_entry_fence() -> None:
    op.execute(
        sa.text(
            """
            CREATE FUNCTION brc_fence_universe_pointer_during_entry()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE
                lane_status text;
                blocking_ticket_id text;
                entry_mutation_unresolved boolean;
            BEGIN
                INSERT INTO brc_entry_lane_current (
                    lane_id, ticket_id, signal_event_id, status,
                    claimed_at_ms, lease_until_ms, claim_owner, version
                ) VALUES (
                    'global-entry', NULL, NULL, 'idle', NULL, NULL, NULL, 0
                ) ON CONFLICT (lane_id) DO NOTHING;
                SELECT status, ticket_id
                INTO lane_status, blocking_ticket_id
                FROM brc_entry_lane_current
                WHERE lane_id = 'global-entry'
                FOR UPDATE;
                SELECT EXISTS (
                    SELECT 1
                    FROM brc_exchange_commands
                    WHERE ticket_id = blocking_ticket_id
                      AND command_kind IN ('set_leverage', 'entry')
                      AND status IN ('prepared', 'claimed', 'outcome_unknown')
                ) INTO entry_mutation_unresolved;
                IF lane_status <> 'idle' AND entry_mutation_unresolved THEN
                    RAISE EXCEPTION 'strategy universe activation is fenced by global ENTRY lane ticket %', blocking_ticket_id
                        USING ERRCODE = '55000',
                              CONSTRAINT = 'ck_brc_universe_activation_entry_lane_idle';
                END IF;
                RETURN NULL;
            END
            $$;
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_brc_universe_activation_entry_lane
            BEFORE INSERT OR UPDATE OR DELETE
            ON brc_strategy_universe_current
            FOR EACH STATEMENT
            EXECUTE FUNCTION brc_fence_universe_pointer_during_entry();
            """
        )
    )


def _create_certification_batch_guards() -> None:
    """Allow one pending-to-result transition and reject result rewriting."""

    op.execute(
        sa.text(
            """
            CREATE FUNCTION brc_guard_certification_batch_member_result()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'certification batch members are immutable'
                        USING ERRCODE = '23514',
                              CONSTRAINT = 'ck_brc_certification_batch_member_immutable';
                END IF;
                IF OLD.status <> 'pending'
                   OR NEW.status = 'pending'
                   OR NEW.certification_batch_id <> OLD.certification_batch_id
                   OR NEW.exchange_instrument_id <> OLD.exchange_instrument_id THEN
                    RAISE EXCEPTION 'certification batch member result is immutable'
                        USING ERRCODE = '23514',
                              CONSTRAINT = 'ck_brc_certification_batch_member_immutable';
                END IF;
                RETURN NEW;
            END
            $$;
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_brc_certification_batch_member_result
            BEFORE UPDATE OR DELETE
            ON brc_instrument_certification_batch_members
            FOR EACH ROW
            EXECUTE FUNCTION brc_guard_certification_batch_member_result();
            """
        )
    )
def downgrade() -> None:
    raise RuntimeError("forward-only baseline; rebuild an empty database instead")
