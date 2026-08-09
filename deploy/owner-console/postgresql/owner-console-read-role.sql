\set ON_ERROR_STOP on

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = 'brc_owner_console'
    ) THEN
        CREATE ROLE brc_owner_console
            LOGIN
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOINHERIT;
    END IF;
END
$$;

ALTER ROLE brc_owner_console
    LOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOINHERIT;
ALTER ROLE brc_owner_console SET default_transaction_read_only = on;
ALTER ROLE brc_owner_console SET statement_timeout = '3s';
ALTER ROLE brc_owner_console SET application_name = 'brc_owner_console';

DO $$
BEGIN
    EXECUTE format(
        'GRANT CONNECT ON DATABASE %I TO brc_owner_console',
        current_database()
    );
END
$$;

GRANT USAGE ON SCHEMA public TO brc_owner_console;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO brc_owner_console;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO brc_owner_console;
