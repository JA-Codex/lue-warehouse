-- US-1.1 step 5 of 5: the four warehouse schemas (decision D2) and their privileges.
-- Run as a superuser, connected to the "lue_warehouse" database. Safe to re-run.
--
--   lue_staging    bronze (brz_*) and silver (stg_*) tables      lue_etl only
--   lue_dw         13 dimensions and 6 facts                     lue_etl only
--   lue_reporting  marts (mart_*), views (vw_*, vw_dim_*)        lue_etl owns, lue_reader reads
--   lue_audit      run log, quarantine, reconciliation, lineage  lue_etl only

-- Nobody but the owner may create objects in public (default since PostgreSQL 15; made explicit).
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

CREATE SCHEMA IF NOT EXISTS lue_staging   AUTHORIZATION lue_etl;
CREATE SCHEMA IF NOT EXISTS lue_dw        AUTHORIZATION lue_etl;
CREATE SCHEMA IF NOT EXISTS lue_reporting AUTHORIZATION lue_etl;
CREATE SCHEMA IF NOT EXISTS lue_audit     AUTHORIZATION lue_etl;

-- Correct the owner if a schema already existed (for example created by a superuser).
ALTER SCHEMA lue_staging   OWNER TO lue_etl;
ALTER SCHEMA lue_dw        OWNER TO lue_etl;
ALTER SCHEMA lue_reporting OWNER TO lue_etl;
ALTER SCHEMA lue_audit     OWNER TO lue_etl;

-- Internal layers: no access for anyone except the owner.
REVOKE ALL ON SCHEMA lue_staging, lue_dw, lue_audit FROM PUBLIC;
REVOKE ALL ON SCHEMA lue_staging, lue_dw, lue_audit FROM lue_reader;

-- Reporting layer: lue_reader may look up and read, never create or write.
REVOKE ALL ON SCHEMA lue_reporting FROM PUBLIC;
GRANT USAGE ON SCHEMA lue_reporting TO lue_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA lue_reporting TO lue_reader;
-- Tables, views and materialized views that lue_etl creates later are readable automatically.
ALTER DEFAULT PRIVILEGES FOR ROLE lue_etl IN SCHEMA lue_reporting
    GRANT SELECT ON TABLES TO lue_reader;

-- Sensible search paths, so unqualified names resolve to the right layer.
ALTER ROLE lue_etl    IN DATABASE lue_warehouse
    SET search_path = lue_dw, lue_staging, lue_audit, lue_reporting, public;
ALTER ROLE lue_reader IN DATABASE lue_warehouse SET search_path = lue_reporting;
