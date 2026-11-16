-- E5: what staging needs in lue_audit. Run as lue_etl by scripts/db_deploy.py. Safe to re-run.
-- None of these is in the pack (like etl_watermark, file_load and dq_result):
--   * dq_batch: the bronze batches E4 has validated and when. Staging reads only validated
--     batches and refuses to run while a batch waits for validation (US-5.1).
--   * stg_load: per run and staging table the count bridge (US-5.1, US-5.3). Of the bronze rows
--     read: rejected by E4, unusable (a key column empty after cleaning), superseded by a newer
--     version or a duplicate, and inserted, updated or left unchanged in staging, so
--     bronze_rows_read = rejected + unusable + superseded + inserted + updated + unchanged.
--     rows_deleted: status rows of a ticket copy that lost to another copy. batch_to: the last
--     batch read at watermark_to, so a batch landed in the same second is not skipped.
--   * cleaning_evidence: per run, source and issue the count and a before/after sample (US-5.4).

CREATE TABLE IF NOT EXISTS lue_audit.dq_batch (
    batch_id             BIGINT NOT NULL,
    run_id               BIGINT NOT NULL,
    validated_at         TIMESTAMP NOT NULL,
    CONSTRAINT pk_dq_batch PRIMARY KEY (batch_id)
);

CREATE TABLE IF NOT EXISTS lue_audit.stg_load (
    run_id               BIGINT NOT NULL,
    stg_table            VARCHAR(40) NOT NULL,
    bronze_rows_read     INT NOT NULL,
    rows_rejected        INT NOT NULL,
    rows_unusable        INT NOT NULL,
    rows_superseded      INT NOT NULL,
    rows_inserted        INT NOT NULL,
    rows_updated         INT NOT NULL,
    rows_unchanged       INT NOT NULL,
    rows_deleted         INT NOT NULL,
    watermark_from       TIMESTAMP NOT NULL,
    watermark_to         TIMESTAMP NOT NULL,
    batch_to             BIGINT NOT NULL,
    CONSTRAINT pk_stg_load PRIMARY KEY (run_id, stg_table)
);

CREATE TABLE IF NOT EXISTS lue_audit.cleaning_evidence (
    run_id               BIGINT NOT NULL,
    source_system        VARCHAR(20) NOT NULL,
    stg_table            VARCHAR(40) NOT NULL,
    issue                VARCHAR(40) NOT NULL,
    column_name          VARCHAR(40) NOT NULL,
    rows_affected        INT NOT NULL,
    sample_before        VARCHAR(200),
    sample_after         VARCHAR(200),
    CONSTRAINT pk_cleaning_evidence PRIMARY KEY (run_id, stg_table, issue, column_name)
);
