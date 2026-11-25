# Evidence: US-14.1 — Mine Insights

## Summary

Five insights were mined from the 14 analytical queries run against the small profile (seed 42, full data window FY2023-24 to FY2024-25).  Each insight traces to a planted pattern in the data generator and is backed by one or more Q-numbers from `sql/60_analytics/`.

## Key checks

| Check | Result |
|---|---|
| Five insights each tied to a planted pattern | Pass — I1–I5 all reference generator flags |
| Values spot-checked against SQL for I1 (Q2) | Pass — GLB03 arrears ratio 21.8 % confirmed |
| Values spot-checked against SQL for I2 (Q9) | Pass — VND07 breach rate 42 % confirmed |

## Files

- `docs/evidence/us-14.1/01_insights_shortlist.md` — full shortlist

## Re-check command

```
# Requires a loaded warehouse:
psql -U lue_reader -d lue_warehouse -f sql/60_analytics/analytical.sql
```
