"""E3 ingestion: the six sources into the bronze tables (lue_staging.brz_*).

base.py is the framework (US-3.1); s1_pms.py (US-3.2), files.py (US-3.3) and json_weather.py
(US-3.4) are the ingestors; run.py runs them all: python etl/ingest/run.py
"""
