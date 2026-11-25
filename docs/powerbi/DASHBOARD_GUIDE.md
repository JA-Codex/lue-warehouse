# Building the three dashboard pages, click by click (E13)

This guide finishes E13 from the team's `powerbi/LUE_Dashboard.pbix`. Its model is already complete and checked:
15 tables, 17 relationships, the date table marked, all 51 measures, and the full-profile data (its totals equal
`docs/evidence/us-13.1/expected_measures.csv`). What is left is the three pages, the checks and the evidence.

Written for Power BI Desktop 2.159 (October 2026). Allow about 4 hours; save often (Ctrl+S).

| Part | What you do | Time |
|---|---|---|
| 0 | Get the latest files | 5 min |
| 1 | Open the file, three quick fixes | 15 min |
| 2 | Page 1: Executive Overview | 60 min |
| 3 | Page 2: Detailed Analysis | 60 min |
| 4 | Page 3: Decision Page | 45 min |
| 5 | Sync the slicers, test the drill-through | 10 min |
| 6 | Validate every number | 20 min |
| 7 | Screenshots, PDF, save | 15 min |
| 8 | Commit and pull request | 10 min |

---

## How to do the five things you will repeat

**A. Add a visual.** Click an empty part of the page (so nothing is selected). In the **Visualizations** pane on the
right, open the **Build visual** tab (the icon of a chart with a pencil) and click the visual's icon; hover over an
icon to see its name. An empty visual appears on the page.

**B. Put fields in it.** With the visual selected, open the **Data** pane (far right). Expand a table and drag a field
into the named box (the *well*) in the Build visual tab: *X-axis*, *Y-axis*, *Column y-axis*, *Line y-axis*,
*Legend*, *Values*, *Rows*, *Columns*, *Field* or *Data*. All measures are in the `_Measures` table at the top of the
Data pane. In this guide, `[Name]` is a measure in `_Measures` and `table[column]` is a column.

**C. Size and place it exactly.** With the visual selected: Visualizations pane, **Format visual** tab (the paintbrush),
**General**, **Properties**, **Size** (Height, Width) and **Position** (Horizontal, Vertical). Type the numbers given
(the page is 1920 x 1080). Every visual in this guide has its numbers, so the pages line up on a clean grid.

**D. Title it.** Format visual, **General**, **Title**: On, type the title in **Text**. Where a subtitle is given:
**Subtitle** On, type it.

**E. Rename a field for one visual.** In the Build visual tab, double-click the field in its well (or click its arrow,
**Rename for this visual**) and type the new name. The table behind it does not change.

---

## Part 0. Get the latest files (PowerShell)

```powershell
cd D:\lue-warehouse
.\.venv\Scripts\Activate.ps1
git checkout main
git pull
```

✅ `git log --oneline -1` shows `user story 13.1 (#27)` and `powerbi\LUE_Dashboard.pbix` exists. Then make your
branch: `git checkout -b e13-dashboard`. (If this guide came to you as a bundle, fetch it as its covering message says.)

Close Power BI Desktop if it is open.

## Part 1. Open the file and make three fixes

1. Double-click `D:\lue-warehouse\powerbi\LUE_Dashboard.pbix`. If a yellow bar offers to refresh or apply changes,
   close it: **do not refresh**. The data inside is already the full profile; a refresh would try the teammate's
   server (`localhost:5433`), and yours is `localhost:5432`.

2. **Switch off Auto date/time** (it added 11 hidden date tables and makes the file 55 MB):
   File, Options and settings, **Options**, left column under *CURRENT FILE*: **Data Load**, untick
   **Auto date/time** (under *Time intelligence*), **OK**. ✅ After the next save the file shrinks to a few MB.

3. **Check the measure formats.** Left bar, **Model view** (third icon). In the **Data** pane expand `_Measures`.
   For each row of this table, Ctrl+click its measures, then in the **Properties** pane, **Formatting**, set:

   | Set | Measures |
   |---|---|
   | Format **Custom**, format code `"PKR "#,0` | Billed, Billed to Date, Collected (Cohort), Cash Received, Cash Received PY, Arrears, Arrears (Portfolio), Rent Roll, Avg Contract Rent, Maintenance Cost, Maintenance Cost per Unit-Month, Rent Collected, Management Fee, NOI, Tenant Billed, Tenant Collected, Tenant Arrears |
   | **Percentage**, decimal places 1 | Collection Rate, Collection Rate (Portfolio), Cash Received YoY %, Arrears Ratio, Arrears Ratio (Portfolio), Occupancy %, Occupancy % (Portfolio), SLA Breach %, SLA Breach % (Portfolio), Tenant Arrears Ratio, Late Payment Share |
   | **Whole number**, thousands separator On | Invoice Lines, Unit Days, Occupied Days, Active Leases, Units, Occupied Units, Requests, Resolved Requests, SLA Breaches, Tenants, Chronically Late Tenants |
   | **Decimal number**, decimal places 1 | Avg Vacancy Days, Avg Days to Resolve, Avg Days to Resolve (Portfolio), Trade Avg Days to Resolve, Days vs Trade |

   In the same pane, with all of `_Measures`' measures still listed, hide `Column1` (right-click it, **Hide in
   report view**).

4. **Apply the theme.** Left bar, **Report view** (first icon). Ribbon **View**, **Themes** (the dropdown arrow),
   **Browse for themes**, open `D:\lue-warehouse\docs\powerbi\lue_theme.json`. ✅ The page turns light grey.

5. Ctrl+S.

## Part 2. Page 1: Executive Overview

What it answers: **how is the portfolio doing, and is it getting better?** Four headline numbers, three trends,
and the buildings that owe the most.

1. **Name the page.** Double-click the tab **Page 1** at the bottom, type `Executive Overview`, Enter.

2. **Title.** Ribbon **Insert**, **Text box**. Type `Executive Overview`, select the text, font size **28**, bold.
   Size and position (C): Height 56, Width 1000, Horizontal 24, Vertical 16.

3. **Subtitle.** Insert, Text box: `Lahore Urban Estates: rent collection, occupancy and arrears, July 2023 to June 2026.
   All amounts in PKR.` Font 13, colour grey. Height 36, Width 1000, Horizontal 24, Vertical 68.

4. **Three slicers.** For each: add a **Slicer** visual (A), put the field in **Field** (B), then Format visual,
   **Visual**, **Slicer settings**, **Options**, **Style: Dropdown**; and Format visual, **Visual**, **Slicer header**:
   On, the text below.

   | Field | Header text | Height | Width | Horizontal | Vertical |
   |---|---|---|---|---|---|
   | `vw_dim_date[fiscal_year_label]` | Fiscal year | 72 | 248 | 1120 | 20 |
   | `vw_dim_building[city]` | City | 72 | 248 | 1384 | 20 |
   | `vw_dim_building[building_class]` | Building class | 72 | 248 | 1648 | 20 |

5. **Four KPI cards.** For each: add a **Card** visual (the new card, not *Card (legacy)* or *Multi-row card*), put the
   measure in **Data**, then add the reference label: drag its second measure into **Reference labels** in the Build
   tab (or Format visual, **Visual**, **Reference labels**, **Add**, choose it), and set the label's title text.
   Format visual, **Visual**, **Callout value**: font size 32. Title (D) off: the card shows the measure's name.

   | Data | Reference label (title) | Height | Width | Horizontal | Vertical |
   |---|---|---|---|---|---|
   | `[Cash Received]` | `[Cash Received YoY %]` (vs the year before) | 150 | 456 | 24 | 120 |
   | `[Collection Rate]` | `[Billed]` (billed) | 150 | 456 | 496 | 120 |
   | `[Occupancy %]` | `[Active Leases]` (active leases) | 150 | 456 | 968 | 120 |
   | `[Arrears]` | `[Arrears Ratio]` (of billed to date) | 150 | 456 | 1440 | 120 |

   "Vs the year before" is blank until a fiscal year is chosen: the whole window has no year before it inside the
   data. Format visual, Visual, Reference labels, Values: **Show blank as** `pick a fiscal year`.

   ✅ With no slicer set: **PKR 5,347,289,709**, **94.2%**, **84.5%**, **PKR 329,363,109** (5.8%).

6. **Cash received against the year before.** Add a **Line chart**. X-axis `vw_dim_date[year_month]`; Y-axis
   `[Cash Received]` and `[Cash Received PY]`. Title: `Cash received by month, against the year before`. Subtitle:
   `The year-before line starts in July 2024, the first month with a year of history`. Format visual, Visual, X-axis,
   Type: **Categorical**. Size: Height 380, Width 928, Horizontal 24, Vertical 286.

7. **Billing and the collection rate.** Add a **Line and clustered column chart**. X-axis `vw_dim_date[year_month]`;
   Column y-axis `[Billed]`; Line y-axis `[Collection Rate]`. Title: `Billed and collection rate by month`. Subtitle:
   `Collection rate = paid on the lines due that month (D17); the latest months read lower, their lines have had
   the least time to be paid`. Size: Height 380, Width 928, Horizontal 968, Vertical 286.

8. **The buildings that owe most.** Add a **Clustered bar chart**. Y-axis `vw_dim_building[building_name]`; X-axis
   `[Arrears Ratio]`. Keep it to ten: open the **Filters** pane (the funnel tab left of Visualizations), under
   **Filters on this visual** expand *building_name*, Filter type **Top N**, Show items **Top 10**, drag
   `[Arrears Ratio]` into **By value**, **Apply filter**. Sort: the visual's **...** (More options), **Sort axis**,
   *Arrears Ratio*, **Sort descending**. Format visual, Visual, **Data labels** On. Title: `Top 10 buildings by arrears
   ratio`. Subtitle: `Right-click a bar, Drill through, Detailed Analysis, to see its tenants`.
   Size: Height 374, Width 928, Horizontal 24, Vertical 682.

   ✅ The first bar is **Gulberg Residency 2, 21.8%**.

9. **Occupancy over time.** Add a **Line chart**. X-axis `vw_dim_date[year_month]`; Y-axis `[Occupancy %]`. Title:
   `Occupancy by month`. Format visual, Visual, Y-axis: Minimum `0.7` (so the line is readable). X-axis Type:
   Categorical. Size: Height 374, Width 928, Horizontal 968, Vertical 682.

10. Ctrl+S.

## Part 3. Page 2: Detailed Analysis

What it answers: **where are the problems?** Buildings and unit types (the brief's product analysis), cities
(regional analysis), tenants by payer segment (segmentation), and vendors.

1. **New page.** Click the **+** next to the page tabs; rename it `Detailed Analysis`.

2. **Title and subtitle.** Copy both text boxes from page 1 (select one, Ctrl+C; go to page 2, Ctrl+V: they keep
   their position). Change the title to `Detailed Analysis` and the subtitle to `Where the problems sit: buildings
   and unit types, cities, tenants and vendors. Click any bar or row to filter the rest of the page.`

3. **Four slicers.** Copy the three slicers from page 1 (Ctrl+click all three, Ctrl+C; page 2, Ctrl+V). When Power BI
   asks to **sync** them, choose **Sync**. Then add a fourth for `vw_dim_unit_type[unit_type]` (header `Unit type`).
   Place all four in one row:

   | Slicer | Height | Width | Horizontal | Vertical |
   |---|---|---|---|---|
   | Fiscal year | 72 | 198 | 1056 | 20 |
   | City | 72 | 198 | 1270 | 20 |
   | Building class | 72 | 198 | 1484 | 20 |
   | Unit type | 72 | 198 | 1698 | 20 |

4. **The buildings matrix.** Add a **Matrix**. Rows: `vw_dim_building[city]`, then `vw_dim_building[building_name]`
   under it. Values: `[Occupancy %]`, `[Collection Rate]`, `[Arrears Ratio]`, `[Avg Vacancy Days]`,
   `[Maintenance Cost per Unit-Month]`. Rename the values for this visual (E): `Occupancy`, `Collection rate`,
   `Arrears ratio`, `Vacancy (days)`, `Maintenance per unit-month`.
   Colour the three rates: Format visual, Visual, **Cell elements**, Apply settings to **Arrears ratio**,
   **Background color** On, click **fx**, Format style *Gradient*, Minimum colour light, Maximum colour red-orange
   (`#C8553D`), OK. Do the same for **Occupancy** and **Collection rate**, but with the lowest value in red (Minimum
   `#C8553D`, Maximum light).
   Title: `Buildings: occupancy, collection and arrears`. Subtitle: `Expand a city (+) to see its buildings`.
   Size: Height 440, Width 1100, Horizontal 24, Vertical 120.

   ✅ Expand Lahore: Gulberg Residency 2 stands out in red on Collection rate and Arrears ratio.

5. **Unit types.** Add a **Clustered column chart**. X-axis `vw_dim_unit_type[unit_type]`; Y-axis `[Occupancy %]`.
   Data labels On. Title: `Occupancy by unit type`. Size: Height 212, Width 756, Horizontal 1140, Vertical 120.

6. **Cities.** Add a **Clustered bar chart**. Y-axis `vw_dim_building[city]`; X-axis `[Collection Rate]` and
   `[Occupancy %]`. Data labels On. Title: `Collection rate and occupancy by city`.
   Size: Height 212, Width 756, Horizontal 1140, Vertical 348.

7. **Tenant segments.** Add a **Donut chart**. Legend `vw_tenant_analysis[payer_segment]`; Values `[Tenants]`.
   Format visual, Visual, Detail labels: **Category, percent of total**. Title: `Tenants by payer segment`.
   Subtitle: `Over the whole data window`. Size: Height 480, Width 420, Horizontal 24, Vertical 576.

   ✅ **Chronically late: 846** of 3,455 tenants (hover the slice).

8. **The tenants table.** Add a **Table**. Columns, in this order: `vw_tenant_analysis[tenant_code]`,
   `vw_tenant_analysis[tenant_name]`, `vw_tenant_analysis[payer_segment]`, `[Tenant Billed]`, `[Tenant Collected]`,
   `[Tenant Arrears]`, `[Late Payment Share]`. Rename (E): `Tenant`, `Name`, `Segment`, `Billed`, `Collected`,
   `Arrears`, `Late share`. Click the **Arrears** column header on the visual to sort, again for descending.
   Format visual, Visual, Cell elements, **Arrears**: **Data bars** On.
   Title: `Tenants, by arrears`. Subtitle: `Over the whole data window; filtered by the building you drill from`.
   Size: Height 480, Width 820, Horizontal 460, Vertical 576.

9. **The vendors table.** Add a **Table**. Columns: `vw_dim_vendor[vendor_name]`, `vw_dim_vendor[trade]`,
   `[Resolved Requests]`, `[Avg Days to Resolve]`, `[Days vs Trade]`, `[SLA Breach %]`. Rename: `Vendor`, `Trade`,
   `Resolved`, `Days`, `vs trade`, `SLA breached`. Filters pane, Filters on this visual, **Resolved Requests**:
   *is greater than or equal to* `20`, **Apply filter**. Sort by **vs trade**, descending. Data bars on **vs trade**.
   Title: `Vendors, slowest against their trade`. Subtitle: `vs trade: 2.0 means twice as slow as the trade's average;
   20 or more resolved requests`. Size: Height 480, Width 600, Horizontal 1296, Vertical 576.

   ✅ The first row is **Sheikh Plumbing Works, Plumbing, 2.3**.

10. **The drill-through.** Click an empty part of page 2. In the Build visual tab scroll down to **Drill through**.
    Drag `vw_dim_building[building_name]` into **Add drill-through fields here**. **Keep all filters**: On.
    Power BI adds a back-arrow button at the top left; move it to Horizontal 24, Vertical 16 and the title to
    Horizontal 72.

11. Ctrl+S.

## Part 4. Page 3: Decision Page

What it answers: **so what should management do?** Three recommendations, each with its evidence beside it. The
texts are measures: they choose the building, vendor and segment from the current slicers, and state the figure, the
action, the owner and the expected effect.

1. **New page** `Decision Page`. Copy the title and subtitle; title `Decision Page`; subtitle `Based on the dashboard,
   what decision should management take? Each recommendation updates with the slicers.`
2. **Slicers.** Copy the three slicers from page 1 (Sync when asked), same positions as on page 1.
3. **The three recommendations.** For each: add a **Table**, put the text measure in **Columns**, rename it for this
   visual (E) to the heading below (the column header becomes the heading). Format visual, Visual: **Values**, Text
   wrap **On**, font size 14; **Column headers**, font size 16, bold, Text wrap **On**; **Grid**, horizontal and vertical
   gridlines **Off**. Title (D) off.

   | Measure | Rename to | Height | Width | Horizontal | Vertical |
   |---|---|---|---|---|---|
   | `[D1 Text]` | 1. Collect the arrears where they concentrate | 260 | 900 | 24 | 120 |
   | `[D2 Text]` | 2. Fix the slowest vendor | 260 | 900 | 24 | 396 |
   | `[D3 Text]` | 3. Fill the emptiest segment | 260 | 900 | 24 | 672 |

   If the text is cut off, drag the column's right edge in the visual to the visual's full width.

4. **The evidence beside each.**
   - Row 1: **Line and clustered column chart**. X-axis `vw_dim_building[building_name]`; Column y-axis
     `[Arrears Ratio]`; Line y-axis `[Arrears Ratio (Portfolio)]`. Filters on this visual: building_name Top N 10
     by `[Arrears Ratio]`. Sort descending by Arrears Ratio. Title: `Arrears ratio: the ten highest buildings against
     the portfolio`. Size: Height 260, Width 956, Horizontal 940, Vertical 120.
   - Row 2: **Line and clustered column chart**. X-axis `vw_dim_vendor[vendor_name]`; Column y-axis
     `[Avg Days to Resolve]`; Line y-axis `[Trade Avg Days to Resolve]`. Filters on this visual: Resolved Requests
     greater than or equal to 20, and vendor_name Top N 10 by `[Days vs Trade]`. Sort descending by Days vs Trade
     (More options, Sort axis). Title: `Days to resolve: the ten vendors slowest against their trade (line: their
     trade's average)`. Size: Height 260, Width 956, Horizontal 940, Vertical 396.
   - Row 3: **Matrix**. Rows `vw_dim_building[city]`; Columns `vw_dim_unit_type[unit_type]`; Values `[Occupancy %]`.
     Cell elements, Occupancy, Background color **fx**, Gradient, lowest red (`#C8553D`), highest light. Title:
     `Occupancy by city and unit type`. Size: Height 260, Width 956, Horizontal 940, Vertical 672.

5. **Assumptions and risks.** Insert, Text box, font 11, at Height 108, Width 1440, Horizontal 24, Vertical 948:

   > **Assumptions and risks.** The data is synthetic (fixed seed, planted patterns): the findings show the method,
   > not a real portfolio. Collection rate = paid on lines due in the month (D17), as of the window end; recent months
   > read lower. Arrears ratio = arrears at the end of the selection / billed up to then. A vendor needs 20 resolved
   > requests and a segment 10 units to be ranked; vendors are compared within their trade. Effects are simple
   > estimates, not forecasts; the 8% management fee is an assumption.

6. **The data window.** A **Card**, Data `[Data Window]`, at Height 108, Width 416, Horizontal 1480, Vertical 948.

✅ With no slicer set, the three texts read word for word:
- **1.** "Concentrate arrears follow-up on Gulberg Residency 2 (GLB03). Its arrears ratio is 21.8% against 5.8% for
  the portfolio, and its collection rate of 78.2% trails the portfolio's 94.2% by 16.0 points. ..."
- **2.** "Move urgent Plumbing work away from Sheikh Plumbing Works (V-001). It takes 3.1 days on average to
  resolve a request, 2.3 times the 1.4 days of all Plumbing vendors, ..."
- **3.** "Fill vacant apartments in Karachi. Their occupancy is 78.2% against 84.5% for the portfolio, ..."

All three, in full and for each selection: `docs/evidence/us-13.1/decisions.txt`. Ctrl+S.

## Part 5. Sync the slicers, test the drill-through

1. Ribbon **View**, **Sync slicers**. Click the *Fiscal year* slicer on any page: in the Sync slicers pane tick both
   columns (sync and visible) for all three pages. Same for *City* and *Building class*. *Unit type*: page 2 only.
   Close the pane.
2. **Drill-through.** Page 1, right-click the **Gulberg Residency 2** bar, **Drill through**, **Detailed Analysis**.
   ✅ Page 2 opens filtered to that building: the matrix shows one row, the tenants table only its tenants (top
   arrears first). Ctrl+click the back arrow to return.
3. **Cross-filtering.** Page 2, click the *Chronically late* slice of the donut. ✅ The tenants table shows only
   chronically late tenants. Click it again to clear.

## Part 6. Validate every number (US-13.5)

1. Left bar, **DAX query view** (fourth icon). **+** for a new query tab. Open
   `D:\lue-warehouse\docs\powerbi\validation.dax` in Notepad, Ctrl+A, Ctrl+C, paste, **Run**.
2. Two result tables (tabs under the grid):
   - **Result 1:** 44 measures by Window, Month 2025-03, FY2024-25 and Lahore. Compare with
     `docs\evidence\us-13.1\expected_measures.csv` (open it in Excel): every value equal to six decimals.
   - **Result 2:** the three texts per selection, equal to `decisions.txt`.
3. Back on page 1, check the cards against `docs\evidence\us-13.1\01_expected_values.txt`:

   | Selection | Cash received | Collection rate | Occupancy | Arrears |
   |---|---|---|---|---|
   | None | PKR 5,347,289,709 | 94.2% | 84.5% | PKR 329,363,109 (5.8%) |
   | Fiscal year FY2024-25 | PKR 1,774,998,239 (+8.2% vs the year before) | 93.9% | 85.1% | PKR 207,519,053 (5.7%) |
   | City Lahore | PKR 2,187,307,068 | 93.4% | 85.8% | PKR 153,824,150 (6.6%) |

4. Fill in `docs\evidence\us-13.5\README.md` (open it in Notepad or VS Code): the Power BI column and Match for each
   row, your Power BI version (2.159.883.0), your name and the date.
5. **Speed.** View, **Performance analyzer**, **Start recording**, **Refresh visuals** on each page. ✅ Every visual
   under about a second. Stop.

## Part 7. Screenshots, PDF, save

1. Clear every slicer (hover over a slicer, the eraser icon) so the pages show the whole window.
2. Take each screenshot with **Windows + Shift + S**, drag over the Power BI window, then click the notification, and
   **Save as** in `D:\lue-warehouse\powerbi\screenshots\` with these names:

   | File | What is on screen |
   |---|---|
   | `01_model.png` | Model view |
   | `02_executive_overview.png` | Page 1 |
   | `03_detailed_analysis.png` | Page 2 |
   | `04_drill_through.png` | Page 2 after drilling from Gulberg Residency 2 |
   | `05_decision_page.png` | Page 3 |
   | `06_validation.png` | DAX query view with the validation result, beside the CSV in Excel |

   Delete the old `Screenshot 2026-11-25 123254.png` (it is replaced by `01_model.png`).
3. Return to page 1 (the file opens on the page it is saved on). Ctrl+S.
4. File, **Export**, **Export to PDF**, save as `D:\lue-warehouse\powerbi\LUE_Dashboard.pdf`. ✅ Three pages.

## Part 8. Commit and pull request (PowerShell)

```powershell
cd D:\lue-warehouse
git status
git add powerbi docs/evidence/us-13.5/README.md
git commit -m "Build the three dashboard pages, validate them and export the evidence (US-13.2 to US-13.5)" -m "Executive Overview, Detailed Analysis and Decision Page built from docs/powerbi/DASHBOARD_GUIDE.md on the team's model; Auto date/time off; every measure checked with validation.dax against the recorded values."
git push -u origin e13-dashboard
```

✅ `git status` before the commit lists only `powerbi/...` and the evidence file (never `.env`). Then open a pull
request on GitHub, **Create a merge commit**, delete the branch, and ask two teammates to open the PBIX and add
their names to the evidence file (US-13.5).

## If something goes wrong

| Problem | Fix |
|---|---|
| A visual shows an error or *Can't display the visual* | Click *See details*; usually a field in the wrong well. Remove it and drag again |
| A card shows *(Blank)* | Normal for *Cash Received PY* and *YoY* with no fiscal year: set *Show blank as* (part 2, step 5) |
| The year_month axis shows only a few labels | Format visual, Visual, X-axis, Type **Categorical**; Values font size 9 |
| The D texts are cut off | Widen the table's column to the visual's width; Values text wrap On |
| Power BI asks for credentials or tries to refresh | Cancel: the data is already loaded. To refresh on your machine: Home, Transform data (arrow), Data source settings, change `localhost:5433` to `localhost:5432` on each entry, credentials `lue_reader` (Basic, encryption off) |
| The file is still 55 MB | Auto date/time is still on (part 1, step 2); save again after switching it off |
