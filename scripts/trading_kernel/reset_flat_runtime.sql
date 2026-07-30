-- Reset all Trading Kernel runtime/trade state after the exchange account has
-- been externally verified flat with no open BRC orders.
--
-- This is a psql script. It deliberately preserves Registry, Owner Policy,
-- Runtime Profile/Scope, Runtime Capability, Schema Metadata, and policy-event
-- authority. It does not mark a Ticket settled and does not contact the venue.
--
-- Required invocation variables:
--
--   psql "$TRADING_KERNEL_DATABASE_URL" \
--     -v expected_database=brc_trading_kernel \
--     -v expected_schema_revision=0001_trading_kernel_baseline_v3 \
--     -v expected_runtime_commit=<deployed-git-commit> \
--     -v expected_ticket_id=<ticket-id-that-must-exist> \
--     -v expected_ticket_count=<exact-current-ticket-count> \
--     -v expected_unresolved_command_count=<exact-current-count> \
--     -v confirmation=RESET_BRC_FLAT_RUNTIME \
--     -f scripts/trading_kernel/reset_flat_runtime.sql
--
-- A rerun after a successful reset is intentionally refused because the
-- expected Ticket no longer exists and the expected Ticket count no longer
-- matches. Supply current identities for every later use.

\set ON_ERROR_STOP on

\if :{?expected_database}
\else
  \echo 'ERROR: expected_database is required'
  \quit 3
\endif
\if :{?expected_schema_revision}
\else
  \echo 'ERROR: expected_schema_revision is required'
  \quit 3
\endif
\if :{?expected_runtime_commit}
\else
  \echo 'ERROR: expected_runtime_commit is required'
  \quit 3
\endif
\if :{?expected_ticket_id}
\else
  \echo 'ERROR: expected_ticket_id is required'
  \quit 3
\endif
\if :{?expected_ticket_count}
\else
  \echo 'ERROR: expected_ticket_count is required'
  \quit 3
\endif
\if :{?expected_unresolved_command_count}
\else
  \echo 'ERROR: expected_unresolved_command_count is required'
  \quit 3
\endif
\if :{?confirmation}
\else
  \echo 'ERROR: confirmation is required'
  \quit 3
\endif

BEGIN;

SET LOCAL lock_timeout = '15s';
SET LOCAL statement_timeout = '120s';

SELECT pg_advisory_xact_lock(hashtextextended('brc-flat-runtime-reset', 0));

CREATE TEMP TABLE brc_flat_runtime_reset_input (
    expected_database TEXT NOT NULL,
    expected_schema_revision TEXT NOT NULL,
    expected_runtime_commit TEXT NOT NULL,
    expected_ticket_id TEXT NOT NULL,
    expected_ticket_count INTEGER NOT NULL,
    expected_unresolved_command_count INTEGER NOT NULL,
    confirmation TEXT NOT NULL,
    reset_at_ms BIGINT NOT NULL,
    deleted_rows BIGINT NOT NULL DEFAULT 0
);

INSERT INTO brc_flat_runtime_reset_input (
    expected_database,
    expected_schema_revision,
    expected_runtime_commit,
    expected_ticket_id,
    expected_ticket_count,
    expected_unresolved_command_count,
    confirmation,
    reset_at_ms
)
VALUES (
    :'expected_database',
    :'expected_schema_revision',
    :'expected_runtime_commit',
    :'expected_ticket_id',
    :'expected_ticket_count'::INTEGER,
    :'expected_unresolved_command_count'::INTEGER,
    :'confirmation',
    floor(extract(epoch FROM clock_timestamp()) * 1000)::BIGINT
);

LOCK TABLE
    brc_schema_metadata,
    brc_instrument_rules_current,
    brc_runtime_scopes_current,
    brc_facts_current,
    brc_signal_events,
    brc_signal_fact_snapshots,
    brc_readiness_current,
    brc_entry_lane_current,
    brc_capacity_claims,
    brc_trade_tickets,
    brc_trade_aggregates,
    brc_trade_events,
    brc_exchange_commands,
    brc_positions_current,
    brc_budget_reservations,
    brc_account_exposure_current,
    brc_runtime_incidents,
    brc_trade_reviews,
    brc_monitor_current,
    brc_monitor_events,
    brc_retention_runs
IN ACCESS EXCLUSIVE MODE;

DO $brc_reset_guard$
DECLARE
    cfg brc_flat_runtime_reset_input%ROWTYPE;
    actual_schema_revision TEXT;
    actual_runtime_commit TEXT;
    actual_ticket_count BIGINT;
    unresolved_command_count BIGINT;
    exposure_row_count BIGINT;
    lane_row_count BIGINT;
BEGIN
    SELECT * INTO STRICT cfg FROM brc_flat_runtime_reset_input;

    IF cfg.confirmation <> 'RESET_BRC_FLAT_RUNTIME' THEN
        RAISE EXCEPTION 'confirmation token mismatch';
    END IF;
    IF cfg.expected_ticket_count <= 0 THEN
        RAISE EXCEPTION 'expected_ticket_count must be positive';
    END IF;
    IF cfg.expected_unresolved_command_count < 0 THEN
        RAISE EXCEPTION 'expected_unresolved_command_count must be nonnegative';
    END IF;
    IF current_database() <> cfg.expected_database THEN
        RAISE EXCEPTION 'database mismatch: expected %, actual %',
            cfg.expected_database,
            current_database();
    END IF;

    SELECT metadata_value
      INTO actual_schema_revision
      FROM brc_schema_metadata
     WHERE metadata_key = 'schema_revision';
    IF actual_schema_revision IS DISTINCT FROM cfg.expected_schema_revision THEN
        RAISE EXCEPTION 'schema revision mismatch: expected %, actual %',
            cfg.expected_schema_revision,
            actual_schema_revision;
    END IF;

    SELECT metadata_value
      INTO actual_runtime_commit
      FROM brc_schema_metadata
     WHERE metadata_key = 'runtime_commit';
    IF actual_runtime_commit IS DISTINCT FROM cfg.expected_runtime_commit THEN
        RAISE EXCEPTION 'runtime commit mismatch: expected %, actual %',
            cfg.expected_runtime_commit,
            actual_runtime_commit;
    END IF;

    SELECT count(*) INTO actual_ticket_count FROM brc_trade_tickets;
    IF actual_ticket_count <> cfg.expected_ticket_count THEN
        RAISE EXCEPTION 'Ticket count mismatch: expected %, actual %',
            cfg.expected_ticket_count,
            actual_ticket_count;
    END IF;
    IF NOT EXISTS (
        SELECT 1
          FROM brc_trade_tickets
         WHERE ticket_id = cfg.expected_ticket_id
    ) THEN
        RAISE EXCEPTION 'expected Ticket is absent: %', cfg.expected_ticket_id;
    END IF;

    SELECT count(*)
      INTO unresolved_command_count
      FROM brc_exchange_commands
     WHERE status IN (
        'prepared',
        'claimed',
        'dispatch_started',
        'outcome_unknown'
     );
    IF unresolved_command_count <> cfg.expected_unresolved_command_count THEN
        RAISE EXCEPTION
            'unresolved Exchange Command count mismatch: expected %, actual %',
            cfg.expected_unresolved_command_count,
            unresolved_command_count;
    END IF;

    SELECT count(*) INTO exposure_row_count
      FROM brc_account_exposure_current;
    IF exposure_row_count <> 1 THEN
        RAISE EXCEPTION 'reset requires exactly one account exposure row, found %',
            exposure_row_count;
    END IF;

    SELECT count(*) INTO lane_row_count
      FROM brc_entry_lane_current
     WHERE lane_id = 'global-entry';
    IF lane_row_count <> 1 THEN
        RAISE EXCEPTION 'global-entry lane is absent or duplicated';
    END IF;
END
$brc_reset_guard$;

UPDATE brc_flat_runtime_reset_input
   SET deleted_rows =
       (SELECT count(*) FROM brc_instrument_rules_current)
     + (SELECT count(*) FROM brc_facts_current)
     + (SELECT count(*) FROM brc_signal_events)
     + (SELECT count(*) FROM brc_signal_fact_snapshots)
     + (SELECT count(*) FROM brc_readiness_current)
     + (SELECT count(*) FROM brc_capacity_claims)
     + (SELECT count(*) FROM brc_trade_tickets)
     + (SELECT count(*) FROM brc_trade_aggregates)
     + (SELECT count(*) FROM brc_trade_events)
     + (SELECT count(*) FROM brc_exchange_commands)
     + (SELECT count(*) FROM brc_positions_current)
     + (SELECT count(*) FROM brc_budget_reservations)
     + (SELECT count(*) FROM brc_runtime_incidents)
     + (SELECT count(*) FROM brc_trade_reviews)
     + (SELECT count(*) FROM brc_monitor_current)
     + (SELECT count(*) FROM brc_monitor_events);

TRUNCATE TABLE
    brc_instrument_rules_current,
    brc_facts_current,
    brc_signal_events,
    brc_signal_fact_snapshots,
    brc_readiness_current,
    brc_capacity_claims,
    brc_trade_tickets,
    brc_trade_aggregates,
    brc_trade_events,
    brc_exchange_commands,
    brc_positions_current,
    brc_budget_reservations,
    brc_runtime_incidents,
    brc_trade_reviews,
    brc_monitor_current,
    brc_monitor_events;

UPDATE brc_entry_lane_current
   SET ticket_id = NULL,
       signal_event_id = NULL,
       status = 'idle',
       claimed_at_ms = NULL,
       lease_until_ms = NULL,
       claim_owner = NULL,
       version = version + 1
 WHERE lane_id = 'global-entry';

UPDATE brc_account_exposure_current
   SET gross_notional = 0,
       gross_risk_at_stop = 0,
       active_ticket_count = 0,
       projection_version = projection_version + 1,
       updated_at_ms = (SELECT reset_at_ms FROM brc_flat_runtime_reset_input);

UPDATE brc_runtime_scopes_current
   SET observation_due_at_ms = (
           SELECT reset_at_ms FROM brc_flat_runtime_reset_input
       ),
       observation_lease_until_ms = NULL,
       observation_claim_owner = NULL,
       updated_at_ms = (
           SELECT reset_at_ms FROM brc_flat_runtime_reset_input
       );

INSERT INTO brc_retention_runs (
    retention_run_id,
    scope,
    deleted_rows,
    started_at_ms,
    completed_at_ms
)
SELECT
    'retention:flat-runtime-reset:' || reset_at_ms,
    'flat_runtime_reset:' || expected_ticket_id,
    deleted_rows,
    reset_at_ms,
    reset_at_ms
FROM brc_flat_runtime_reset_input;

DO $brc_reset_verify$
DECLARE
    remaining_rows BIGINT;
    exposure_is_zero BOOLEAN;
    lane_is_idle BOOLEAN;
    observation_lease_count BIGINT;
BEGIN
    SELECT
        (SELECT count(*) FROM brc_instrument_rules_current)
      + (SELECT count(*) FROM brc_facts_current)
      + (SELECT count(*) FROM brc_signal_events)
      + (SELECT count(*) FROM brc_signal_fact_snapshots)
      + (SELECT count(*) FROM brc_readiness_current)
      + (SELECT count(*) FROM brc_capacity_claims)
      + (SELECT count(*) FROM brc_trade_tickets)
      + (SELECT count(*) FROM brc_trade_aggregates)
      + (SELECT count(*) FROM brc_trade_events)
      + (SELECT count(*) FROM brc_exchange_commands)
      + (SELECT count(*) FROM brc_positions_current)
      + (SELECT count(*) FROM brc_budget_reservations)
      + (SELECT count(*) FROM brc_runtime_incidents)
      + (SELECT count(*) FROM brc_trade_reviews)
      + (SELECT count(*) FROM brc_monitor_current)
      + (SELECT count(*) FROM brc_monitor_events)
      INTO remaining_rows;
    IF remaining_rows <> 0 THEN
        RAISE EXCEPTION 'runtime reset verification found % remaining rows',
            remaining_rows;
    END IF;

    SELECT count(*) = 1
       AND bool_and(
            gross_notional = 0
        AND gross_risk_at_stop = 0
        AND active_ticket_count = 0
       )
      INTO exposure_is_zero
      FROM brc_account_exposure_current;
    IF exposure_is_zero IS NOT TRUE THEN
        RAISE EXCEPTION 'account exposure reset verification failed';
    END IF;

    SELECT count(*) = 1
       AND bool_and(
            status = 'idle'
        AND ticket_id IS NULL
        AND signal_event_id IS NULL
        AND lease_until_ms IS NULL
        AND claim_owner IS NULL
       )
      INTO lane_is_idle
      FROM brc_entry_lane_current
     WHERE lane_id = 'global-entry';
    IF lane_is_idle IS NOT TRUE THEN
        RAISE EXCEPTION 'global ENTRY lane reset verification failed';
    END IF;

    SELECT count(*)
      INTO observation_lease_count
      FROM brc_runtime_scopes_current
     WHERE observation_lease_until_ms IS NOT NULL
        OR observation_claim_owner IS NOT NULL;
    IF observation_lease_count <> 0 THEN
        RAISE EXCEPTION 'runtime scope lease reset verification failed';
    END IF;
END
$brc_reset_verify$;

COMMIT;

SELECT
    current_database() AS database_name,
    expected_ticket_id AS cleared_ticket_id,
    deleted_rows,
    reset_at_ms,
    (
        SELECT new_entry_submit_enabled
          FROM brc_owner_policy_current
         WHERE owner_policy_id = 'policy-main'
    ) AS new_entry_submit_enabled_preserved
FROM brc_flat_runtime_reset_input;
