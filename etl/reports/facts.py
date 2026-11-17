"""Every number the Phase 2 reports print, read from the warehouse (and the source for the
reconciliation). Nothing is typed into a report: rerun python etl/reports/build.py after a load
and the reports follow."""

# ruff: noqa: E501  (SQL text: long lines read better)

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from etl.quality import answer_key as e4_key
from etl.quality import engine
from etl.staging import answer_key as e5_key
from etl.staging import evidence, spec


def rows(cur, sql: str, args=None) -> list[tuple]:
    cur.execute(sql, args)
    return cur.fetchall()


def one(cur, sql: str, args=None):
    cur.execute(sql, args)
    return cur.fetchone()


@dataclass
class Facts:
    profile: str = ""
    sizes: dict = field(default_factory=dict)
    seed: int = 0
    window: str = ""
    dq_run: int = 0
    stage_run: int = 0
    volumes: list = field(default_factory=list)  # (source, bronze table, staging table, rows, batches)
    findings: list = field(default_factory=list)  # (source, table, rule, check, severity, rows, example)
    rules: list = field(default_factory=list)  # engine.Rule
    rule_hits: dict = field(default_factory=dict)  # rule id -> rows found
    by_check: list = field(default_factory=list)  # (check, rejected, warned)
    quarantine: list = field(default_factory=list)  # (source, table, check, rows)
    e4: object = None  # etl.quality.answer_key.Comparison
    e5: object = None  # etl.staging.answer_key.Comparison
    column_issues: list = field(default_factory=list)  # (source, table, issue, column, rows, before, after)
    table_counts: dict = field(default_factory=dict)  # table -> {issue: rows}
    bridge: list = field(default_factory=list)
    distinct: list = field(default_factory=list)
    business: list = field(default_factory=list)  # (table, issue, column, rows, before, after)
    allocation: dict = field(default_factory=dict)
    invoiced: list = field(default_factory=list)  # (quarter, source amount, staged amount, source lines, staged lines)
    paid: list = field(default_factory=list)  # (quarter, source amount, staged amount, rejected amount)
    completeness: list = field(default_factory=list)  # (source, table, column(s), rows, missing, pct, handling)
    fks: int = 0
    partitions: int = 0
    dims: list = field(default_factory=list)  # (dimension, members, keys from, to)
    runs: list = field(default_factory=list)  # (step, status, read, inserted, updated, rejected)


def collect(cur, src, data: Path) -> Facts:
    f = Facts()
    import json

    manifest = json.loads((data / "run_manifest.json").read_text(encoding="utf-8"))
    prof = manifest.get("profile", {})
    f.profile, f.seed = prof.get("name", ""), manifest.get("seed", prof.get("seed", 0))
    f.window = f"{prof.get('window_start', '')} to {prof.get('window_end', '')}"
    f.sizes = {k: prof.get(k) for k in ("buildings", "units", "tenants", "owners", "vendors")}
    f.dq_run = one(cur, "SELECT max(run_id) FROM lue_audit.dq_result")[0]
    f.stage_run = one(cur, "SELECT max(run_id) FROM lue_audit.etl_run_log WHERE step = 'stage_reset' AND status = 'Success'")[0]

    for t in spec.TABLES:
        n, b = one(cur, f"SELECT count(*), count(DISTINCT batch_id) FROM lue_staging.{t.bronze}")
        f.volumes.append((t.source_system, t.bronze, t.name, n, b))

    sys_of = {t.bronze: t.source_system for t in spec.TABLES}
    for table, rule, check, sev, n, ex in rows(cur, "SELECT source_table, rule_id, check_name, severity, count(*), min(reason) FROM lue_audit.dq_result WHERE run_id = %s GROUP BY 1, 2, 3, 4 ORDER BY 1, 2", (f.dq_run,)):
        f.findings.append((sys_of.get(table, ""), table, rule, check, sev, n, ex))
    f.rules = engine.load_rules()
    f.rule_hits = {r[2]: r[5] for r in f.findings}
    checks = defaultdict(lambda: [0, 0])
    for _s, _t, _r, check, sev, n, _e in f.findings:
        checks[check[:5]][0 if sev == "reject" else 1] += n
    names = engine.CHECKS
    f.by_check = [(names[k], *checks.get(k, [0, 0])) for k in sorted(names)]
    f.quarantine = rows(cur, "SELECT source_system, source_table, check_name, count(*) FROM lue_audit.quarantine WHERE run_id = %s GROUP BY 1, 2, 3 ORDER BY 1, 2, 3", (f.dq_run,))

    key_file = data / "answer_key" / "defects_answer_key.csv"
    f.e4 = e4_key.compare(cur, key_file, f.dq_run)
    f.e5 = e5_key.compare(cur, data)

    for s, t, issue, col, n, before, after in rows(cur, "SELECT source_system, stg_table, issue, column_name, rows_affected, sample_before, sample_after FROM lue_audit.cleaning_evidence WHERE run_id = %s ORDER BY source_system, stg_table, column_name, issue", (f.stage_run,)):
        if col == "*":
            f.table_counts.setdefault(t, {})[issue] = (n, before, after)
        elif issue in ("derived_allocation", "unmatched_settlement", "unsettled_payment"):
            f.business.append((t, issue, col, n, before, after))
        else:
            f.column_issues.append((s, t, issue, col, n, before, after))
    f.bridge = evidence.bridge(cur)
    f.distinct = evidence.distinct_values(cur)

    a = one(cur, """
        SELECT count(*) FILTER (WHERE status = 'Cleared' AND reversal_of IS NULL AND amount > 0),
               count(*) FILTER (WHERE status = 'Cleared' AND reversal_of IS NULL AND amount > 0 AND allocated_amount = amount),
               count(*) FILTER (WHERE reversal_of IS NOT NULL),
               count(*) FILTER (WHERE reversal_of IS NOT NULL AND allocated_amount = amount),
               count(*) FILTER (WHERE amount > 0 AND allocated_amount > amount)
        FROM lue_staging.stg_payment""")
    lines = one(cur, "SELECT count(*), count(*) FILTER (WHERE allocated_amount > net_amount), count(*) FILTER (WHERE open_balance = 0), count(*) FILTER (WHERE allocated_amount = 0) FROM lue_staging.stg_invoice_line WHERE net_amount > 0")
    d = one(cur, "SELECT count(*), count(DISTINCT payment_reference), coalesce(sum(allocated_amount), 0), round(avg(days_past_due), 1) FROM lue_staging.stg_payment_allocation WHERE allocation_source = 'derived'")
    s1 = one(cur, "SELECT count(*), round(avg(days_past_due), 1) FROM lue_staging.stg_payment_allocation WHERE allocation_source = 'S1'")
    f.allocation = {"cleared": a[0], "cleared_full": a[1], "reversals": a[2], "reversals_full": a[3],
                    "over_paid": a[4], "lines": lines[0], "over_line": lines[1], "lines_paid": lines[2],
                    "lines_unpaid": lines[3], "derived_rows": d[0], "derived_payments": d[1],
                    "derived_amount": d[2], "derived_dpd": d[3], "s1_rows": s1[0], "s1_dpd": s1[1]}  # fmt: skip

    src_inv = dict((q, (amt, n)) for q, amt, n in rows(src, "SELECT to_char(date_trunc('quarter', i.invoice_date::date), 'YYYY-\"Q\"Q'), sum(l.net_amount::numeric), count(*) FROM src_pms.invoice_lines l JOIN src_pms.invoices i USING (invoice_number) GROUP BY 1"))
    stg_inv = dict((q, (amt, n)) for q, amt, n in rows(cur, "SELECT to_char(date_trunc('quarter', i.invoice_date), 'YYYY-\"Q\"Q'), sum(l.net_amount), count(*) FROM lue_staging.stg_invoice_line l JOIN lue_staging.stg_invoice i USING (invoice_number) GROUP BY 1"))
    for q in sorted(set(src_inv) | set(stg_inv)):
        sa, sn = src_inv.get(q, (0, 0))
        ta, tn = stg_inv.get(q, (0, 0))
        f.invoiced.append((q, sa, ta, sn, tn))
    src_pay = dict(rows(src, "SELECT to_char(date_trunc('quarter', paid_at::timestamp), 'YYYY-\"Q\"Q'), sum(amount::numeric) FROM src_pms.payments GROUP BY 1"))
    stg_pay = dict(rows(cur, "SELECT to_char(date_trunc('quarter', paid_at), 'YYYY-\"Q\"Q'), sum(amount) FROM lue_staging.stg_payment GROUP BY 1"))
    for q in sorted(set(src_pay) | set(stg_pay)):
        f.paid.append((q, src_pay.get(q, 0), stg_pay.get(q, 0)))

    handling = {"reject": "row rejected to quarantine", "warn": "kept, flagged"}
    for r in f.rules:
        if r.check != "DQ-01":
            continue
        total = one(cur, f"SELECT count(*) FROM lue_staging.{r.table}")[0]
        n = f.rule_hits.get(r.id, 0)
        f.completeness.append((sys_of.get(r.table, ""), r.table, ", ".join(r.columns), total, n,
                               (100.0 * n / total) if total else 0.0, handling.get(r.severity, r.severity)))  # fmt: skip
    # Declared foreign keys only (conparentid = 0): partitions repeat their parent's constraints.
    f.fks = one(cur, "SELECT count(*) FROM pg_constraint k JOIN pg_namespace n ON n.oid = k.connamespace WHERE n.nspname = 'lue_dw' AND k.contype = 'f' AND k.conparentid = 0")[0]
    f.partitions = one(cur, "SELECT count(*) FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'lue_dw'")[0]
    f.dims = rows(cur, "SELECT 'dim_tenant', count(*) FILTER (WHERE tenant_key > 0), min(tenant_key) FILTER (WHERE tenant_key > 0), max(tenant_key) FROM lue_dw.dim_tenant")
    f.runs = rows(cur, "SELECT step, status, rows_read, rows_inserted, rows_updated, rows_rejected FROM lue_audit.etl_run_log WHERE run_id = %s ORDER BY started_at", (f.stage_run,))
    return f
