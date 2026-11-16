-- E4 (US-4.1): what the data quality engine needs in lue_audit. Run as lue_etl by
-- scripts/db_deploy.py. Safe to re-run.
--   * lue_audit.dq_result (not in the pack, like etl_watermark and file_load): one row per bronze
--     row and rule that found something, rejections (at most one per row and run) and warnings.
--     The pack's quarantine table keeps its meaning: one row per rejected source row, with a JSON
--     copy of it. Staging (E5) keeps the bronze rows that have no rejection here.
--   * Safe casts used by the rules: NULL instead of an error when a text is not a number, a date
--     or a timestamp. try_date accepts the two formats the sources use, YYYY-MM-DD and DD/MM/YYYY
--     (decision: a day-first date is repaired in staging, US-5.1, not rejected).

CREATE TABLE IF NOT EXISTS lue_audit.dq_result (
    run_id               BIGINT NOT NULL,
    batch_id             BIGINT NOT NULL,
    source_system        VARCHAR(20) NOT NULL,
    source_table         VARCHAR(40) NOT NULL,
    row_id               BIGINT NOT NULL,
    rule_id              VARCHAR(40) NOT NULL,
    check_name           VARCHAR(30) NOT NULL,
    severity             VARCHAR(10) NOT NULL,
    reason               VARCHAR(200) NOT NULL,
    found_at             TIMESTAMP NOT NULL,
    CONSTRAINT pk_dq_result PRIMARY KEY (run_id, source_table, row_id, rule_id),
    CONSTRAINT ck_dq_result_severity CHECK (severity IN ('reject', 'warn'))
);

-- A plain SQL function, so PostgreSQL can inline it (it is called for every amount).
CREATE OR REPLACE FUNCTION lue_audit.try_numeric(value text) RETURNS numeric
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN value ~ '^\s*-?[0-9]+(\.[0-9]+)?\s*$' THEN value::numeric END
$$;

CREATE OR REPLACE FUNCTION lue_audit.try_date(value text) RETURNS date
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    parts text[];
BEGIN
    IF value IS NULL THEN
        RETURN NULL;
    ELSIF value ~ '^\d{4}-\d{2}-\d{2}$' THEN
        parts := regexp_match(value, '^(\d{4})-(\d{2})-(\d{2})$');
        RETURN make_date(parts[1]::int, parts[2]::int, parts[3]::int);
    ELSIF value ~ '^\d{2}/\d{2}/\d{4}$' THEN
        parts := regexp_match(value, '^(\d{2})/(\d{2})/(\d{4})$');
        RETURN make_date(parts[3]::int, parts[2]::int, parts[1]::int);
    END IF;
    RETURN NULL;
EXCEPTION WHEN others THEN
    RETURN NULL;  -- 2025-02-30, month 13 ...
END;
$$;

CREATE OR REPLACE FUNCTION lue_audit.try_timestamp(value text) RETURNS timestamp
LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
    IF value IS NULL OR value !~ '^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?$' THEN
        RETURN NULL;
    END IF;
    RETURN value::timestamp;
EXCEPTION WHEN others THEN
    RETURN NULL;
END;
$$;
