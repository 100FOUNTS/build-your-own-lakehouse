# Step 3 — Silver: data you can trust

⏱ 4–6 h · Deliverable: dbt project + `dbt/models/silver/` · Check: `make check-3`

## What you are going to build

A **dbt** project that transforms bronze into three clean tables inside `data/warehouse.duckdb`:

| Table | Grain (a row is…) | What it solves |
|---|---|---|
| `silver.sensor_readings` | one reading of one sensor of one pump at one UTC instant | Everything you found in step 1 |
| `silver.work_orders` | one work order | Normalized types, real dates |
| `silver.assets` | one pump | The master, with correct types |

## Why this step exists

If bronze is "the ingredients as they arrive", silver is **the trust point** of the whole platform: here it is decided
what is true. Any person or model that consumes silver must be able to assume: *one row per measurement, in standard
units, in UTC time, without garbage*. That prevents every analyst from having to rediscover (and reimplement, differently) the
problems in the data.

Two principles you will see here:

- **Flag, do not destroy.** A suspicious value (a spike) is *flagged* with a flag (`is_outlier`), not deleted. Maybe
  tomorrow you find out it was a real failure; if you deleted it, you cannot go back. (BAD readings are excluded: the system
  itself says they are not measurements.)
- **Decisions are versioned, tested code.** That `-9999` means "no data" is not a secret in someone's head:
  it is a line of SQL with a test next to it.

## What it is for in a real job

dbt has become *the* standard for the transformation layer: from startups to banks use it, on
Snowflake, Databricks, BigQuery, Postgres or DuckDB. An "analytics engineer" or "data engineer" position almost always asks for
dbt + advanced SQL (window functions, CTEs). This step is the closest to the day-to-day of that job.

## Concepts you need

### dbt in five ideas
1. **A model is a `SELECT`** saved in a `.sql` file. dbt turns it into a table or view (`materialized`).
2. **`{{ ref('other_model') }}`** references another model; dbt deduces the execution order (the graph) from it.
3. **Tests**: assertions about the data (`not_null`, `unique`, `accepted_values`, or a `SELECT` that must
   return 0 rows). `dbt build` = run models **and** their tests, in order.
4. **`.yml` next to the models**: descriptions and tests. It is documentation that runs.
5. **Configuration**: `dbt_project.yml` (what the project is) and `profiles.yml` (which database it connects to).

### SQL you will need (learn what you do not know, it is part of the step)
- **CTEs** (`WITH ... AS`): split a query into named, readable steps.
- **Window functions** (`OVER (PARTITION BY … ORDER BY … ROWS BETWEEN …)`): compute something "looking at the surrounding
  rows" without collapsing them. With them you detect a spike (compare it to the median of its neighbors) and deduplicate
  (`row_number()`).
- **`QUALIFY`** (DuckDB, Snowflake, BigQuery): filter by the result of a window function.
- **`TRY_CAST`**: convert without blowing up if the text is not a number.
- **Time zones**: `CAST(x AS TIMESTAMPTZ)` understands `-05:00` and `Z`; `… AT TIME ZONE 'UTC'` takes it to UTC.

## The contract (what the checks expect)

**`silver.sensor_readings`**

| Column | Type | Rule |
|---|---|---|
| `asset_id` | text | Same as in `assets.csv` (e.g. `PLT01-P101`). Derived from the `tag` |
| `ts_utc` | TIMESTAMP | Instant **in UTC** (no zone, but already converted). The oldest reading must be `2026-05-01 05:00:00` |
| `sensor` | text | `VIB_MM_S`, `TEMP_BEARING`, `PRESS_DISCH`, `CURRENT_A`, `RUN_STATE` |
| `value` | DOUBLE | **In standard units**: °C, kPa, mm/s, A (0/1 for RUN_STATE) |
| `unit` | text | The standard unit of that sensor (`mm/s`, `degC`, `kPa`, `A`, `bool`) |
| `is_outlier` | BOOLEAN | `true` if the reading is a spurious spike (GOOD quality but absurd relative to its neighborhood) |

- **Unique grain**: no two rows with the same `(asset_id, ts_utc, sensor)`.
- **No `BAD` readings** and no null or sentinel values. (What to do with `UNCERTAIN` is up to you: document it.)
- Between 98.5 % and 100 % of the unique good readings of the raw data (do not discard good data).
- Schema: `silver` (or `main_silver`, which is what dbt generates by default; both are accepted).

**`silver.work_orders`**: `wo_id`, `asset_id`, `wo_type` (**normalized** to `PREVENTIVE`, `CORRECTIVE`, `INSPECTION`),
`opened_at` and `closed_at` as UTC TIMESTAMP, `failure_mode`, `cost_usd`, `downtime_hours`.
**`silver.assets`**: the 20 pumps with correct types.

**dbt tests**: at least 5 in silver (key uniqueness, `not_null`, `accepted_values` and a grain test) and all
pass. The models are described in a `.yml`.

## Your task

1. **Create the dbt project by hand** (not with `dbt init`, which is interactive and creates files outside the project):
   `dbt/dbt_project.yml` and `dbt/profiles.yml`. Understand what each line does. *(Hint 1 if you get stuck with the configuration.)*
2. **`sensor_readings`**, step by step, in named CTEs. Each CTE solves **one** problem from your step 1 list:
   - parse the `tag` into `asset_id` and `sensor`,
   - convert `timestamp` to UTC (two formats!),
   - convert `value` to a number and discard BAD and sentinels,
   - **deduplicate** (what key defines a duplicate? within the file, between files, across the time-format change?),
   - **normalize units**,
   - **flag spikes** with `is_outlier` (compared against what?).
3. **`work_orders` and `assets`**: types and normalization.
4. **Tests and descriptions** in `dbt/models/silver/schema.yml`, including a "singular" grain test (a `.sql` in
   `dbt/tests/` that returns rows only if there is an error).
5. **Run `make silver`** and *look at your data*: how many rows remained, what percentage you flagged as outliers, the
   temperature of the pump with the unit change before and after.
6. **Write down in `notes/`** the decisions you made (what you did with UNCERTAIN, how you defined outlier, why that threshold).

## How you will know you are done

```bash
make silver      # dbt build: models + tests
make check-3     # checks independent from your SQL
```

The check does not look at your SQL: it looks at **your results** and compares them with a truth it computes separately from the raw data
(counts, unit continuity, real spikes flagged without flooding with false positives…).

## Comprehension questions

1. Why is `is_outlier` a column and not a `DELETE`? Give a case in which deleting the spike would have hurt you.
2. A spike is defined "relative to its neighborhood". Why does a global threshold like `vibration > 6` not work, even adjusted?
3. Why do you deduplicate **after** converting to UTC and not before?
4. What would happen to the step 5 model if you had not corrected the unit of the pump that switches to another scale?
5. If tomorrow a new sensor arrives with a unit you do not know, would your tests warn you? (Think about `accepted_values`.)

## Hints

<details><summary>Hint 1 — dbt configuration (this is not what you should learn here)</summary>

`dbt/dbt_project.yml`
```yaml
name: lakehouse
version: "1.0.0"
profile: lakehouse
model-paths: ["models"]
test-paths: ["tests"]
macro-paths: ["macros"]
models:
  lakehouse:
    silver: {+materialized: table, +schema: silver}
```
`dbt/profiles.yml` — note that the path comes from an environment variable, just like in `paths.py`:
```yaml
lakehouse:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: "{{ env_var('LH_WAREHOUSE', 'data/warehouse.duckdb') }}"
```
It is run with `make silver` (the Makefile already passes `--project-dir dbt --profiles-dir dbt`).
</details>

<details><summary>Hint 2 — How to read bronze from dbt</summary>

A model can read Parquet directly with DuckDB:
`from read_parquet('{{ env_var("LH_BRONZE_DIR", "data/bronze") }}/readings/**/*.parquet')`.
(In large projects it is declared as a `source` with its own documentation; to start, this is enough.)
If you get the `main_silver` schema and want `silver`, that is dbt's default behavior: both are accepted.
</details>

<details><summary>Hint 3 — Time zone and duplicates</summary>

DuckDB: `cast("timestamp" as timestamptz)` interprets both `…-05:00` and `…Z`. To go to "zoneless" UTC:
`cast(… at time zone 'UTC' as timestamp)`. And to keep one row per key:
`qualify row_number() over (partition by <key> order by <criterion>) = 1`.
</details>

<details><summary>Hint 4 — Detecting spikes</summary>

Compare each value with the **median of a small window around it** within the same `(asset_id, sensor)`:
`median(value) over (partition by … order by ts_utc rows between 3 preceding and 3 following)`. A value is a spike if it
moves away from that median more than that sensor can legitimately vary in 10 minutes (the threshold depends on the sensor:
vibration in mm/s is not the same as pressure in kPa). Measure how many flags you get: 0.01 %? 2 %? What does that tell you?
</details>

<details><summary>Hint 5 — Units</summary>

Look at the `unit` column of the raw data for each tag over time. There are two known conversions: °F → °C
(`(F − 32) × 5/9`) and bar → kPa (`× 100`). Verify your conversion by checking that the daily average of that pump is continuous
when crossing the date of the change.
</details>

<details><summary>Hint 6 — If a dbt test fails</summary>

`dbt build` tells you which test failed. To see the offending rows, run the test's query by hand against the
warehouse (DuckDB): a failing test is almost always a finding, not a nuisance.
</details>

## Common traps

- **Parsing the time ignoring the offset** (cutting the text to 19 characters): it "works", but it moves every reading 5 hours.
- **Deduplicating by the text of the time** instead of the UTC instant: the same instant written in two formats is not detected.
- **An outlier rule that flags 5 % of everything**: it no longer distinguishes anything and, worse, will flag real failures (vibration rises
  *for real* before a failure).
- **Converting units by sensor instead of by `unit`**: the conversion depends on the declared unit, not on the sensor.
- **Forgetting that DuckDB allows one writer**: if you have a notebook with the warehouse open, dbt will not be able to write.

## In a real job

This is the *staging + intermediate* of a typical dbt project. What changes in a company: the tests run in CI
on every pull request, there are `sources` with *freshness* (alert if data does not arrive), model contracts (`contract: enforced`)
and published documentation (`dbt docs`). Your `schema.yml` is the seed of all that.

→ Next: [`04_gold.md`](04_gold.md)
