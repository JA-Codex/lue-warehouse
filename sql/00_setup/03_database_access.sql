-- US-1.1 step 3 of 5: database owners and who may connect.
-- Run as a superuser, connected to the "postgres" database. Safe to re-run.

-- Also corrects the owner if a database was created by hand earlier.
ALTER DATABASE lue_source    OWNER TO lue_etl;
ALTER DATABASE lue_warehouse OWNER TO lue_etl;

-- Only the intended roles may connect: lue_reader never sees the source system.
REVOKE ALL ON DATABASE lue_source    FROM PUBLIC;
REVOKE ALL ON DATABASE lue_warehouse FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE lue_source    TO lue_etl;
GRANT CONNECT, TEMPORARY ON DATABASE lue_warehouse TO lue_etl;
GRANT CONNECT            ON DATABASE lue_warehouse TO lue_reader;
