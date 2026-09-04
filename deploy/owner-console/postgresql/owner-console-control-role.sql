\set ON_ERROR_STOP on

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'brc_owner_control'
    ) THEN
        CREATE ROLE brc_owner_control
            LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
END
$$;

ALTER ROLE brc_owner_control
    LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
ALTER ROLE brc_owner_control SET statement_timeout = '3s';
ALTER ROLE brc_owner_control SET application_name = 'brc_owner_control';

DO $$
BEGIN
    EXECUTE format(
        'GRANT CONNECT ON DATABASE %I TO brc_owner_control',
        current_database()
    );
END
$$;

GRANT USAGE ON SCHEMA public TO brc_owner_control;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO brc_owner_control;

GRANT INSERT ON TABLE
    brc_owner_authorizations,
    brc_strategy_entry_control_events,
    brc_owner_control_operation_events,
    brc_owner_control_operations_current,
    brc_owner_policy_events,
    brc_event_exit_profile_bindings,
    brc_event_exit_profile_binding_events
TO brc_owner_control;

GRANT UPDATE ON TABLE
    brc_strategy_entry_controls_current,
    brc_owner_control_operations_current,
    brc_owner_policy_current,
    brc_strategy_selection_control_current,
    brc_event_exit_profile_binding_current,
    brc_exit_policies
TO brc_owner_control;
