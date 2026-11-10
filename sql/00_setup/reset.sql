-- US-1.5: wipe the warehouse side so it can be rebuilt from scratch. Run as the superuser
-- postgres in lue_warehouse by scripts/db_reset.py. It never touches lue_source or the roles.
-- After this, scripts/db_reset.py runs db_setup, db_deploy and db_load_reference again.
DROP SCHEMA IF EXISTS lue_staging   CASCADE;
DROP SCHEMA IF EXISTS lue_dw        CASCADE;
DROP SCHEMA IF EXISTS lue_reporting CASCADE;
DROP SCHEMA IF EXISTS lue_audit     CASCADE;
