-- US-1.1 step 1 of 5: application roles (run as a superuser, connected to the "postgres" database).
-- Safe to re-run: roles are created only if missing, then their attributes are (re)set.
-- Passwords are NOT stored here (the repository is public). scripts/db_setup.py sets them from .env.
--
--   lue_etl     owns every warehouse schema; used by the pipeline
--   lue_reader  read-only on lue_reporting only; used by Power BI (decision D4)

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lue_etl') THEN
        CREATE ROLE lue_etl LOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lue_reader') THEN
        CREATE ROLE lue_reader LOGIN;
    END IF;
END
$$;

ALTER ROLE lue_etl    LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
ALTER ROLE lue_reader LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;

-- Second line of defence for the reader: every transaction starts read-only.
ALTER ROLE lue_reader SET default_transaction_read_only = on;
