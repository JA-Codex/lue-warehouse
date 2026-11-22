# Evidence for US-12.2: the indexing and partitioning experiments

Written by `python scripts/benchmark.py --runs 9 --out docs/evidence/us-12.2` on the full profile (seed 3004).

| File | What it shows |
|---|---|
| `summary.csv` | Each query before and after: median time, plan cost, the scans, the verdict, the run ranges and spreads |
| `baseline.csv`, `after.csv` | Every measurement (9 rounds x 2 states, each the fastest of 3 back-to-back runs) |
| `indexes.csv` | Each candidate index: purpose, size, build time, the load cost of its fact (re-load without and with), the queries that used it |
| `run.json` | Settings, tolerance, the baseline's indexes, table sizes |
| `plans/` | The text plan of every query before and after (`EXPLAIN (ANALYZE, BUFFERS)`) |

| Query | Change | Before | After | Cost before to after | Verdict |
|---|---|---|---|---|---|
| B1 Q1, whole window | (due_date_key, unit_key) indexes | 210.8 ms | 223.6 ms | 12,495 to 12,495 | no gain: the planner keeps the sequential scans (it reads every row) |
| B2 Q1, one month | the same | 22.1 ms | 4.1 ms | 8,837 to 4,750 | **improved 5.4-fold** (sequential to bitmap scans) |
| B3 Q7 vacancy | (unit_key, snapshot_date_key) | 765.4 ms | 799.5 ms | 123,173 to 123,173 | no gain: index not used |
| B4 one quarter | monthly partitions against one table | 61.9 ms | 70.0 ms | 27,597 to 7,321 | no gain: pruning works (3 partitions), but the date-first primary key already serves the range |
| B5 one unit, a year | (unit_key, snapshot_date_key) | 17.5 ms | 0.97 ms | 17,043 to 1,319 | **improved 18-fold** (index lookups instead of 12 partition scans) |
| B6 current tenants | partial index on current rows | 1.23 ms | 0.56 ms | 123 to 111 | no gain: chosen, but saves 0.7 ms, under the 1 ms counted |

The plan's acceptance: two queries improved in both time and cost (B2, B5), and four changes that did not help, each
explained in the report. Every index has a measured size and use: the occupancy index is 42.9 MB (26 percent of the
fact), the two date indexes 2.3 and 2.2 MB, the partial index 48 kB.
