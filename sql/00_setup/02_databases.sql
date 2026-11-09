-- US-1.1 step 2 of 5: the two databases (decision D1), owned by lue_etl.
-- Run as a superuser, connected to the "postgres" database.
-- CREATE DATABASE cannot run inside a DO block or a transaction, so the query below *returns* the
-- statements still needed and \gexec runs each one. Nothing is returned (nothing runs) on a re-run.
-- psql runs \gexec natively; scripts/db_setup.py does the same thing for machines without psql.
-- This file holds only that one query, because \gexec must end the file for the CI parse check.

SELECT format('CREATE DATABASE %I OWNER lue_etl ENCODING ''UTF8'' TEMPLATE template0', d)
FROM unnest(ARRAY['lue_source', 'lue_warehouse']) AS d
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = d)
\gexec
