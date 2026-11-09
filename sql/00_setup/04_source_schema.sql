-- US-1.1 step 4 of 5: source system S1 (LUE-PMS) lives in schema src_pms of database lue_source.
-- Run as a superuser, connected to the "lue_source" database. Safe to re-run.

REVOKE CREATE ON SCHEMA public FROM PUBLIC;

CREATE SCHEMA IF NOT EXISTS src_pms AUTHORIZATION lue_etl;
ALTER SCHEMA src_pms OWNER TO lue_etl;

ALTER ROLE lue_etl IN DATABASE lue_source SET search_path = src_pms, public;
