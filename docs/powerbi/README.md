# The LUE dashboard: build guide (E13)

The dashboard is built by hand in Power BI Desktop (Windows) from the files in this folder. Follow the steps in
order; each ends with a ✅ check. The finished files go in `powerbi/` at the root of the repository.

| File | What it is |
|---|---|
| `model.json` | The data model: the 15 tables, their filters, the 17 relationships and the hidden columns |
| `measures.dax` | All 51 measures, pasted into DAX query view in one go (step 4) |
| `validation.dax` | The validation query: every measure for four selections, and the decision texts (step 11) |
| `lue_theme.json` | The colour and text theme (step 7) |
| `../evidence/us-13.1/expected_measures.csv` | The value every measure must show on the full profile, from `scripts/powerbi_expected.py` |

**The team's `powerbi/LUE_Dashboard.pbix` already holds steps 1 to 6** (the model, checked against the recorded
values). To build the pages from it, follow [`DASHBOARD_GUIDE.md`](DASHBOARD_GUIDE.md): click by click, with the
size and position of every visual and the number each one must show. The steps below build the model from scratch.

Produced in `powerbi/`: `LUE_Dashboard.pbix`, `LUE_Dashboard.pdf` (the three pages) and `screenshots/`.

## 0. Before you start

1. Load the **full profile** (the dashboard is judged on it; it takes a while):
   `python scripts/db_reset.py`, then `python etl/run_pipeline.py --profile full`.
2. Run `python scripts/test_powerbi.py` (13 PASS lines) and `python scripts/powerbi_expected.py`. Keep the second
   one's output open: it is the value every card and measure must show.
3. Note the Power BI Desktop version (Help, About): it goes in the evidence.
4. Have the `lue_reader` password from your `.env` (`LUE_READER_PASSWORD`) ready.
5. In Power BI Desktop, File, Options and settings, Options, **Current file**, Data Load: untick
   *Autodetect new relationships after data is loaded* (you create the 17 relationships yourself in step 6).

## 1. Connect as `lue_reader` (US-13.1)

Home, Get data, More, **PostgreSQL database**:

| Field | Value |
|---|---|
| Server | `localhost:5432` (host and port of your PostgreSQL, as `PGHOST` and `PGPORT` in `.env`) |
| Database | `lue_warehouse` |
| Data Connectivity mode | **Import** |

The credentials are on the same page in recent versions (in older ones, a dialog after OK):

| Field | Value |
|---|---|
| Authentication kind | **Basic** (in older versions the **Database** tab); not *Organizational account* |
| Username | `lue_reader` |
| Password | `LUE_READER_PASSWORD` in `.env` (`.env.example`'s default: `lue_reader_secure_pass_123`) |
| Privacy Level | **Organizational** |
| Use encrypted connection | **Unticked**: the local PostgreSQL has no SSL, and Power BI refuses with "unable to connect using an encrypted connection" |

Then Next (or Connect). In older versions, if Power BI says the server does not support encryption: File, Options
and settings, Data source settings, select `localhost:5432;lue_warehouse`, Edit Permissions, untick **Encrypt
connections**, OK, and connect again.

✅ The Navigator (*Choose data*) lists the `lue_reporting` views. Only these load: the reader is refused everything
else (`scripts/test_reporting.py` shows the refusals).

## 2. Load the 15 objects

**The four marts are not in the Navigator's list**: they are materialized views, which Power BI's PostgreSQL list
does not show. `lue_reader` can read them; they are added by a short query in part B.

**A. In the Navigator**, tick these 11, then the arrow next to **Load**, **Transform Data** (not Load):

| Role | Objects |
|---|---|
| Dimensions | `vw_dim_date`, `vw_dim_building`, `vw_dim_unit_type`, `vw_dim_vendor`, `vw_dim_maintenance_category`, `vw_dim_owner`, `vw_tenant_analysis` (the tenant and its payer segment) |
| Facts | `vw_tenant_by_building` (the four marts come in part B) |
| Reference (hidden) | `vw_unit_performance`, `vw_monthly_collections` |
| Parameter | `vw_reporting_window` |

`vw_dim_month`, `vw_dim_unit`, `vw_dim_tenant`, `vw_dim_payment_method` and the brief's aliases are not needed.

**B. Add the four marts** in the Power Query Editor, once each:

1. Right-click the empty space under the Queries list, **New Query**, (Other Sources,) **Blank Query**; or Home,
   New Source, Blank Query.
2. Right-click the new query, **Advanced Editor**, replace everything with (for the first mart):

   ```
   let
       Source = PostgreSQL.Database("localhost:5432", "lue_warehouse", [Query = "SELECT * FROM lue_reporting.mart_collections_monthly"])
   in
       Source
   ```
3. Done. If a yellow bar asks for permission: **Edit Permission**, **Run**. If it asks for credentials: as in
   step 1.
4. Rename the query to the mart's name: `mart_collections_monthly`.

Then the same for `mart_occupancy_monthly`, `mart_maintenance_monthly` and `mart_owner_portfolio_monthly`
(change the name in the code and the query's name). A view missed in part A is added the same way with:

```
let
    Source = PostgreSQL.Database("localhost:5432", "lue_warehouse"),
    Data = Source{[Schema = "lue_reporting", Item = "vw_unit_performance"]}[Data]
in
    Data
```

✅ 15 queries on the left.

## 3. Power Query: names and three filters

1. **Rename** every query to the object's own name, without the schema (double-click the query on the left;
   `lue_reporting vw_dim_date` becomes `vw_dim_date`). The measures use these names exactly.
2. **`vw_dim_date`**: Advanced Editor, replace everything with this. It removes the two special rows (1900 dates)
   and keeps the data window, so the table can be marked as a date table:

   ```
   let
       Source = PostgreSQL.Database("localhost:5432", "lue_warehouse"),
       Window = Source{[Schema = "lue_reporting", Item = "vw_reporting_window"]}[Data]{0},
       Dates = Source{[Schema = "lue_reporting", Item = "vw_dim_date"]}[Data],
       Kept = Table.SelectRows(Dates, each [date_key] > 0
           and [full_date] >= Window[window_start] and [full_date] <= Window[window_end])
   in
       Kept
   ```
3. **`vw_dim_building`**: the arrow on the `building_code` column header, untick `N/A` and `Unknown`, OK.
4. **`vw_dim_unit_type`**: the arrow on the `unit_type` column header, untick `Not applicable` and `Unknown`, OK.

   No mart row uses these placeholder buildings or unit types (`scripts/test_powerbi.py` checks it), so no total
   changes; they only stay out of the slicers.
5. Home, **Close & Apply**.

✅ The Data pane shows 15 tables; `vw_dim_date` has 1,096 rows on the full profile (2023-07-01 to 2026-06-30),
`vw_dim_building` has no `N/A` or `Unknown` row. (The code of 3.2 names the server: use the same text as in
step 1.)

## 4. The measures

1. Home, **Enter data**: name the table `_Measures`, leave its one empty column, **Load**.
2. **DAX query view** (the fourth icon on the left), a new query: paste the whole of `measures.dax`, **Run**.
   The result is one row, *Measures defined: 51*.
3. Click **Update model with changes** (the link above `DEFINE`). The 51 measures appear in `_Measures`.
4. Hide `Column1` of `_Measures` (right-click, Hide): the table moves to the top of the Data pane.

If DAX query view is missing (an old Power BI Desktop), create each measure with *New measure* and paste its
expression from `measures.dax` (the part after `MEASURE '_Measures'[Name] =`).

✅ `_Measures` lists 51 measures and none shows a warning triangle.

## 5. Formats (US-13.1)

In **Model view**, expand `_Measures` in the Data pane, Ctrl+click every measure of a group below, then set the
format once in the Properties pane:

| Format | Properties pane | Measures |
|---|---|---|
| PKR | Format *Custom*, `"PKR "#,0` | Billed, Billed to Date, Collected (Cohort), Cash Received, Cash Received PY, Arrears, Rent Roll, Avg Contract Rent, Maintenance Cost, Maintenance Cost per Unit-Month, Rent Collected, Management Fee, NOI, Tenant Billed, Tenant Collected, Tenant Arrears, Arrears (Portfolio) |
| percent | *Percentage*, 1 decimal place | Collection Rate, Cash Received YoY %, Arrears Ratio, Occupancy %, SLA Breach %, Tenant Arrears Ratio, Late Payment Share, Collection Rate (Portfolio), Arrears Ratio (Portfolio), Occupancy % (Portfolio), SLA Breach % (Portfolio) |
| whole number | *Whole number*, thousands separator on | Invoice Lines, Unit Days, Occupied Days, Active Leases, Units, Occupied Units, Requests, Resolved Requests, SLA Breaches, Tenants, Chronically Late Tenants |
| decimal | *Decimal number*, 1 decimal place | Avg Vacancy Days, Avg Days to Resolve, Avg Days to Resolve (Portfolio), Trade Avg Days to Resolve, Days vs Trade |
| text | nothing to set | Data Window, D1 Building, D1 Text, D2 Vendor, D2 Text, D3 Segment, D3 Text |

## 6. Relationships, the date table, hidden columns (US-13.1)

**Model view**, Manage relationships: delete any relationship not in this list, then add each one with *New*:
the first column on the **one** side, the second on the **many** side, *Many to one (\*:1)*, cross-filter direction
**Single**, *Make this relationship active* ticked.

| One side (dimension) | Many side (fact) |
|---|---|
| `vw_dim_date[date_key]` | `mart_collections_monthly[month_key]`, `mart_occupancy_monthly[month_key]`, `mart_maintenance_monthly[month_key]`, `mart_owner_portfolio_monthly[month_key]`, `vw_monthly_collections[month_key]` |
| `vw_dim_building[building_code]` | `mart_collections_monthly[building_code]`, `mart_occupancy_monthly[building_code]`, `mart_maintenance_monthly[building_code]`, `vw_tenant_by_building[building_code]`, `vw_unit_performance[building_code]` |
| `vw_dim_unit_type[unit_type]` | `mart_occupancy_monthly[unit_type]`, `mart_maintenance_monthly[unit_type]`, `vw_unit_performance[unit_type]` |
| `vw_dim_vendor[vendor_key]` | `mart_maintenance_monthly[vendor_key]` |
| `vw_dim_maintenance_category[maint_category_key]` | `mart_maintenance_monthly[maint_category_key]` |
| `vw_dim_owner[owner_key]` | `mart_owner_portfolio_monthly[owner_key]` |
| `vw_tenant_analysis[tenant_key]` | `vw_tenant_by_building[tenant_key]` |

A month key is the date key of the month's first day, so the monthly marts join the daily date table. Every
table is either a dimension or a fact, never both: every filter path is one step, so none is ambiguous.

Then:

1. Select `vw_dim_date`, Table tools, **Mark as date table**, date column `full_date`. ✅ Power BI accepts it.
2. `vw_dim_date[month_name]`: Column tools, *Sort by column* `month_no`.
3. Hide (right-click, Hide in report view): every column of the fact tables (the measures are what the pages use),
   and `vw_dim_date[date_key]`, `vw_dim_vendor[vendor_key]`, `vw_dim_vendor[phone]`, the `effective_from` and
   `effective_to` columns, `vw_dim_maintenance_category[maint_category_key]`, `vw_dim_owner[owner_key]`,
   `vw_tenant_analysis[tenant_key]`, `vw_dim_unit_type[current_units]`. `model.json` lists them.
4. Hide the whole tables `vw_unit_performance` and `vw_monthly_collections`: they are for checking only.

✅ Take the **model view screenshot** (`powerbi/screenshots/01_model.png`): every relationship a 1 to * line.

## 7. Theme

View, Themes, *Browse for themes*: `docs/powerbi/lue_theme.json`. Page size 16:9.

## 8. Page 1: Executive Overview (US-13.2)

Rename the page **Executive Overview**.

| Where | Visual | Fields |
|---|---|---|
| Top row | Three slicers (Dropdown) | `vw_dim_date[fiscal_year_label]`, `vw_dim_building[city]`, `vw_dim_building[building_class]` |
| KPI row | Card: **Cash received** (collections, the brief's revenue KPI) | `[Cash Received]`; reference label `[Cash Received YoY %]`, titled "vs the year before" |
| KPI row | Card: **Collection rate (cohort)** | `[Collection Rate]` |
| KPI row | Card: **Occupancy** | `[Occupancy %]` |
| KPI row | Card: **Arrears** | `[Arrears]`; reference label `[Arrears Ratio]`, titled "of billed" |
| Left | Line chart: **Cash received by month, against the year before** | X `vw_dim_date[year_month]`, Y `[Cash Received]` and `[Cash Received PY]` |
| Right | Line and clustered column chart: **Billed and collection rate by month** | X `vw_dim_date[year_month]`, columns `[Billed]`, line `[Collection Rate]` |
| Bottom | Clustered bar chart: **Arrears ratio by building**, sorted descending | Y `vw_dim_building[building_name]`, X `[Arrears Ratio]` |

Titles say what is shown; the cohort rate's note goes in the line chart's subtitle: "the latest months read lower,
their lines have had the least time to be paid".

View, **Sync slicers**: sync the three slicers to all three pages (visible on each).

✅ With no slicer set, the four cards equal the *Window* column of `powerbi_expected.py`; with FY2024-25 they equal
the *FY2024-25* column; with Lahore, the *Lahore* column. Every visual changes with each slicer. Screenshot:
`powerbi/screenshots/02_executive_overview.png`.

## 9. Page 2: Detailed Analysis (US-13.3)

Rename the page **Detailed Analysis**. Add a fourth slicer, `vw_dim_unit_type[unit_type]`.

| Section | Visual | Fields |
|---|---|---|
| Buildings and unit types (the brief's product analysis) | Clustered bar chart, sorted descending: **Occupancy by building** | Y `vw_dim_building[building_name]`, X `[Occupancy %]` |
| | Matrix: **Building and unit type** | Rows `vw_dim_building[city]` then `vw_dim_building[building_name]` (drill down with the + buttons); columns `vw_dim_unit_type[unit_type]`; values `[Occupancy %]`, `[Avg Vacancy Days]`, `[Rent Roll]`, `[Maintenance Cost per Unit-Month]` |
| Cities (regional analysis) | Clustered bar chart: **Collection rate and occupancy by city** | Y `vw_dim_building[city]`, X `[Collection Rate]` and `[Occupancy %]` |
| Tenant segmentation | Donut chart: **Tenants by payer segment** | Legend `vw_tenant_analysis[payer_segment]`, values `[Tenants]` |
| | Table: **Tenants (whole data window)**, sorted by arrears | `vw_tenant_analysis[tenant_code]`, `[tenant_name]`, `[payer_segment]`, `[Tenant Billed]`, `[Tenant Collected]`, `[Tenant Arrears]`, `[Late Payment Share]` |
| Vendor performance | Table: **Vendors**, sorted by days against the trade, with data bars on the first three values | `vw_dim_vendor[vendor_name]`, `vw_dim_vendor[trade]`, `[Avg Days to Resolve]`, `[Days vs Trade]`, `[SLA Breach %]`, `[Resolved Requests]` |

The tenant visuals cover the whole window (`vw_tenant_by_building` has no date): say so in their titles. Clicking a
bar cross-filters the others (the default; keep it).

**Drill through** from a building to its tenants: with the page selected, drag `vw_dim_building[building_name]`
into *Drill through* in the Visualizations pane (Keep all filters: on). Power BI adds a back button.
On page 1 (or page 3), right-click a building's bar, **Drill through**, Detailed Analysis: the page opens filtered
to that building, and the tenants table lists its tenants only. When the page is opened from its tab, nothing is
filtered.

✅ The three sections are there; the drill-through opens one building's tenants. Screenshots:
`03_detailed_analysis.png` and `04_drill_through.png` (after drilling from page 1's bar for the highest building).

## 10. Page 3: Decision Page (US-13.4)

Rename the page **Decision Page**, title: *Based on the dashboard, what decision should management take?*

Three rows, one per recommendation: the text on the left, its evidence on the right.

| Row | Text (a Table visual with the one measure: Values, *Text wrap* on; Column headers off) | Supporting visual |
|---|---|---|
| 1 | `[D1 Text]` | Line and clustered column chart: X `vw_dim_building[building_name]`, columns `[Arrears Ratio]`, line `[Arrears Ratio (Portfolio)]`; sorted by arrears ratio |
| 2 | `[D2 Text]` | Line and clustered column chart: X `vw_dim_vendor[vendor_name]`, columns `[Avg Days to Resolve]`, line `[Trade Avg Days to Resolve]`; sorted by `[Days vs Trade]`; visual filters `[Resolved Requests]` greater than or equal to 20 and Top N 10 by `[Days vs Trade]` |
| 3 | `[D3 Text]` | Matrix: rows `vw_dim_building[city]`, columns `vw_dim_unit_type[unit_type]`, values `[Occupancy %]` with a background colour scale (lowest red) |

Each text picks its building, vendor or segment from the current selection and states the figure, the action, the
owner and the expected effect, so it follows the fiscal year slicer.

Add a text box **Assumptions and risks**, and a card with `[Data Window]` under it:

- The data is synthetic: generated with a fixed seed, with planted patterns (docs/phase1); the findings show the
  method, not a real portfolio.
- The collection rate is the cohort rate (D17), as of the window end; the latest months read lower.
- The arrears ratio is the arrears at the end of the selection over the amount billed from the window start to
  then (over the whole window it is Q2's ratio).
- Thresholds: a vendor needs 20 resolved requests and a segment 10 units to be ranked; a vendor is compared with
  the vendors of its own trade, since some trades take longer by nature.
- Expected effects are simple estimates (half the arrears recovered; the portfolio's breach or occupancy rate
  reached), not forecasts. The management fee (8 percent) is an assumption.

✅ Each recommendation names a figure, an action, an owner and an expected effect. With no slicer set the three
texts read word for word as the *[Window]* block of `powerbi_expected.py`. Screenshot: `05_decision_page.png`.

## 11. Validate (US-13.5)

1. **DAX query view**, a new query: paste `validation.dax`, Run. Two result tables:
   - every numeric measure (44) for the whole window, the month 2025-03, the fiscal year FY2024-25 and the city
     Lahore: compare each value with `docs/evidence/us-13.1/expected_measures.csv` (the full profile; or the output of
     `python scripts/powerbi_expected.py --out <folder>` on your own load). DAX prints doubles: equal to the CSV's
     six decimals once rounded;
   - the three decision texts for each selection: equal to `decisions.txt`.
2. Screenshot the query result beside the CSV (`06_validation.png`), and fill in
   `docs/evidence/us-13.5/README.md` (the side-by-side table: measure, SQL value, Power BI value, match).
3. Slicers: try fiscal year by city by building class on every page; every visual responds (the tenant visuals
   ignore the fiscal year, as titled). Tooltips: hover a bar on each page.
4. Page load: View, **Performance analyzer**, Start recording, Refresh visuals: each page within a few seconds.

## 12. Save and export

1. File, Save as `powerbi/LUE_Dashboard.pbix`.
2. File, Export, **Export to PDF**: `powerbi/LUE_Dashboard.pdf` (the three pages).
3. Ask two team members to open the PBIX (step 13) and note who did, on which machine.

## 13. Opening the PBIX on another machine

The PBIX holds the imported data, so it opens anywhere. To refresh it from another warehouse: load the warehouse
there (same `.env` roles), then Home, Transform data, **Data source settings**, *Change Source* (server and port),
Edit Permissions, credentials `lue_reader` (untick *Encrypt connections* if needed), then **Refresh**.

## Troubleshooting

| Problem | Fix |
|---|---|
| "The server does not support SSL" or a certificate error | Step 1: untick *Encrypt connections* |
| The marts are not in the Navigator | They are materialized views: add them with a query (step 2, part B) |
| Next stays greyed out, or a *Sign in* button | Authentication kind *Basic* with user and password (step 1), not *Organizational account* |
| "Password authentication failed for user lue_reader" | The password is `LUE_READER_PASSWORD` in `.env`; the roles are set by `python scripts/db_setup.py` |
| A measure shows an error after step 4 | A query was not renamed (step 3.1): the measures need the object names exactly |
| *Mark as date table* refuses `full_date` | The filter of step 3.2 is missing: the special rows repeat 1900 dates |
| A visual shows a "(Blank)" building or unit type | The filter of step 3.3 or 3.4 removed a key that a mart uses: run `python scripts/test_powerbi.py` |
| Refresh fails on privacy levels | File, Options, Privacy: set the source to *Organizational* |
