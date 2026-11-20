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
    brc_review_enrichment_requests,
    brc_directional_risk_events,
    brc_owner_authorizations,
    brc_strategy_entry_control_events,
    brc_owner_control_operation_events,
    brc_owner_control_operations_current,
    brc_owner_policy_events,
    brc_strategy_selection_rollback_baselines,
    brc_selection_rollback_baseline_events,
    brc_strategy_entry_vacuums_current,
    brc_strategy_entry_vacuum_events,
    brc_exit_policies,
    brc_exit_configurations,
    brc_exit_configuration_current,
    brc_event_exit_profile_bindings,
    brc_event_exit_profile_binding_events
TO brc_owner_control;

GRANT EXECUTE ON FUNCTION brc_lock_owner_static_selection_source_v1(text)
TO brc_owner_control;
GRANT EXECUTE ON FUNCTION brc_lock_owner_orb_static_source()
TO brc_owner_control;
GRANT EXECUTE ON FUNCTION brc_lock_owner_pause_vacuum_v1(text,text)
TO brc_owner_control;
GRANT EXECUTE ON FUNCTION brc_lock_owner_static_retry_sources_v1(text,text),
    brc_append_owner_static_reauthorization_v1(text,text,bigint)
TO brc_owner_control;

GRANT UPDATE ON TABLE
    brc_review_enrichment_requests,
    brc_directional_risk_controls,
    brc_strategy_entry_controls_current,
    brc_owner_control_operations_current,
    brc_owner_policy_current,
    brc_strategy_selection_control_current,
    brc_exit_configuration_current,
    brc_event_exit_profile_binding_current,
    brc_exit_policies
TO brc_owner_control;

-- Mobile intents and device sessions; binding grants can only be issued by the
-- independent admin command, never by the Owner API database role.
GRANT INSERT, UPDATE ON TABLE
    brc_owner_device_sessions,
    brc_owner_request_nonces, brc_owner_position_operations, brc_owner_binding_limits
TO brc_owner_control;
GRANT INSERT ON brc_owner_device_registrations, brc_owner_device_write_evidence TO brc_owner_control;
REVOKE UPDATE ON brc_owner_device_registrations, brc_owner_device_write_evidence FROM brc_owner_control;
GRANT UPDATE (revoked_at_ms) ON brc_owner_device_registrations TO brc_owner_control;
GRANT UPDATE (authorization_id,result_kind,result_payload) ON brc_owner_device_write_evidence TO brc_owner_control;
GRANT UPDATE (consumed_at_ms) ON brc_owner_binding_grants TO brc_owner_control;
GRANT INSERT ON brc_owner_position_operation_events TO brc_owner_control;

GRANT DELETE ON brc_owner_binding_limits TO brc_owner_control;

-- SELECT FOR UPDATE on the exact Ticket during mobile intent acceptance.
-- Lifecycle projection fields remain writable exclusively by the Kernel.
GRANT UPDATE (ticket_id) ON TABLE public.brc_trade_aggregates TO brc_owner_control;
