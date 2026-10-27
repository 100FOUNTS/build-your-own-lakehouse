# Step 1 — What I found in the raw data (reference version)

> Reference findings for the `solution` branch. The step 1 check reads this file, so it is filled in here. Your own
> findings may be organized differently and cover other details; what matters is evidence plus a decision for each one.

## Findings

### H1 — Identical rows copied inside the same file

**Evidence:**

```sql
-- Day 1: 14,472 rows against 14,400 expected (20 pumps x 5 sensors x 144 ten-minute readings): 72 extra rows.
select timestamp, tag, value, unit, quality, count(*) as n
from read_csv('data/raw/historian/date=2026-05-03/*.csv.gz', all_varchar=true)
group by timestamp, tag, value, unit, quality
having count(*) > 1;
-- After removing them, day 1 has exactly 14,400 rows: the copies explain ALL the excess and no reading is missing.
```

**What it means:** the historian retransmits some readings and the same row ends up twice in the file. Counting or averaging
them as they are inflates the counts and biases the means.

**Decision:** in silver, keep a single row per `(timestamp, tag)`. Bronze stores the copies exactly as they arrived, so that we can reprocess if the criterion for "which copy" turns out to be wrong.

### H2 — The last hour of the previous day is re-sent in the next day's file

**Evidence:**

```sql
-- Rows per file (days 1-5): 14472, 14472, 15075, 14472, 15075 -> days 3 and 5 carry ~600 more rows.
-- Day 3's file carries 603 rows with a timestamp before day 3: all from 2026-05-02 23:00 to 23:50.
select timestamp, tag, count(*) as n, count(distinct filename) as files
from read_csv('data/raw/historian/date=2026-05-0[2-3]/*.csv.gz', all_varchar=true, filename=true)
where timestamp >= '2026-05-02T23:00:00-05:00' and timestamp <= '2026-05-02T23:50:00-05:00'
group by timestamp, tag
having count(*) > 1;
-- 600 pairs (100 sensors x 6 instants), all present in BOTH files; 0 pairs with a different value or quality: exact copies.
```

**What it means:** day N's file carries the last hour of day N-1, which was already in its own file. A reading repeats
between files, and a deduplication that only looks inside one file does not see it.

**Decision:** in silver, deduplicate by the key `(timestamp, tag)` over all the files together, not per file. Among copies with different values, prefer GOOD quality, then the first file in order.

### H3 — `quality` comes in upper case ("GOOD"), not "Good"

**Evidence:**

```sql
select quality, count(*) from read_csv('data/raw/historian/date=2026-05-01/*.csv.gz', all_varchar=true) group by quality;
-- GOOD 14314 | BAD 97 | UNCERTAIN 61  (in one file)
-- A filter `quality = 'Good'` would return no rows at all, with no error.
```

**What it means:** a filter written with another capitalization does not fail: it returns an empty table. The model would
train without data, or with whatever is left, and nobody would notice.

**Decision:** in silver, normalize `quality` (upper case, trimmed) before filtering. Keep `UNCERTAIN` with its quality and let gold decide; drop `BAD`.

### H4 — The 2026-07-01 file is truncated (cut gzip)

**Evidence:**

```python
import gzip
good = []
try:
    with gzip.open("data/raw/historian/date=2026-07-01/readings_20260701.csv.gz", "rt") as f:
        for line in f:
            good.append(line)
except EOFError:
    print("the file was cut")   # EOFError: Compressed file ended before the end-of-stream marker was reached
print(len(good))   # 7,954 lines (header + 7,953 readings, of ~14,400 expected)
# Looping over the 150 files reading each completely: 1 broken (this one), 149 healthy.
```

**What it means:** the file was cut during transfer. Only ~55 % of the day can be read, and the last instant is incomplete.
No other file carries what is missing. A `read_csv` with a wildcard over the 150 files fails entirely because of this one.

**Decision:** in bronze, set the WHOLE file aside in quarantine (do not load even the readable rows: nothing half-way), without bringing down the load of the others, and record which file it was, the reason and when. A known gap is better than half data that looks good, and it is reversible if the provider re-sends the file. In gold, 2026-07-01 ends up with no or partial readings.

### H5 — Two sensors change unit halfway through the history (honestly labeled)

**Evidence:**

```sql
select split_part(tag,'.',2) as pump, split_part(tag,'.',3) as sensor, unit, count(*) as n,
       min(filename) as from_file, max(filename) as to_file
from read_csv(<the 149 healthy files>, all_varchar=true, filename=true)
where unit in ('degF','bar') group by all;
-- One pump's TEMP_BEARING comes in degF from 2026-07-10; another pump's PRESS_DISCH comes in bar from 2026-07-30.
-- Medians of the SAME pump: degC 60.55 | degF 141.84 (1.8 x 60.55 + 32 = 141.0); kPa 416.302 | bar 4.163 (ratio 100.0).
```

**What it means:** permanent changes in a single pump each, not noise. Untreated, one series would jump from ~60 to ~140 and the other would fall from ~416 to ~4: the model would see anomalies that do not exist. The `unit` label tells the truth, so rows can be corrected one by one.

**Decision:** in silver, convert according to the `unit` column of each row (not by pump or by date, so it survives other future changes) to canonical units: °C with (°F - 32) / 1.8 and kPa with bar x 100. The conversion goes AFTER replacing the -9999 sentinel with NULL, and a check verifies the range of each sensor is coherent after converting.

### H6 — "No reading" is written two ways: `-9999` and an empty value (both with `BAD`)

**Evidence:**

```sql
-- Rows with value = -9999: 6,880, all quality = BAD, in 80 tags (20 pumps x 4 sensors; RUN_STATE has none).
-- BAD rows by value: '-9999.000' -> 6,880 | empty (NULL) -> 6,769
select quality, count(*) from read_csv(<the 149 healthy files>, all_varchar=true)
where try_cast(value as double) = -9999 group by quality;
```

**What it means:** `-9999` is a "no reading" sentinel, not a temperature. Almost half of the `BAD` readings arrive with an empty value, so watching only -9999 would leave 6,769 gaps untreated. If -9999 reaches a daily mean it ruins it, and converting it from °F to °C before cleaning disguises it as another number.

**Decision:** in silver, turn both `-9999` and empty values into NULL and exclude the BAD rows from silver (the system itself says they are not measurements); never use sentinels in aggregates.

### H7 — `wo_type` is written in several ways: if not normalized, failures are lost from the label

**Evidence:**

```python
wo = pd.read_csv("data/raw/reference/work_orders.csv", dtype=str)
wo["wo_type"].value_counts(dropna=False)
# INSPECTION 99 | PREVENTIVE 43 | CORRECTIVE 22 | Preventive 13 | Corrective 6 | corrective 2
# -> 6 spellings of 3 types. Real corrective orders: 22 + 6 + 2 = 30; misspelled: 8.
wo["failure_mode"].notna().sum()  # 30 -> matches the 30 corrective orders (two independent ways of counting)
```

**What it means:** a filter `wo_type = 'CORRECTIVE'` returns 22 failures instead of 30: it loses 8 (more than a quarter) with no error. Failures are the label the model must learn. If 8 of them are labeled "no failure", the 7 days before each one (high vibration, rising temperature) become examples of "healthy pump": the model learns that pattern is normal and misses real failures in production. If they are also missing from the test set, the metrics look better than they will be.

**Decision:** bronze keeps `wo_type` as it arrived. In silver, normalize the type (trim and upper case) before using it, and add a test that only the three expected values remain. The gold label is built only from silver.

### H8 — The `timestamp` format changes on 2026-08-04: from local time (`-05:00`) to UTC (`Z`)

**Evidence:**

```sql
select right(timestamp, 6) as zone, length(timestamp) as len, count(*) as n,
       min(filename) as first_file, max(filename) as last_file
from read_csv(<the 149 healthy files>, all_varchar=true, filename=true)
group by 1, 2 order by 1, 2;
-- length 25, ends in '-05:00': 1,357,956 rows, 2026-05-01 to 2026-08-03   (e.g. 2026-05-02T23:00:00-05:00)
-- length 20, ends in 'Z':        ~804,000 rows, 2026-08-04 to 2026-09-27   (e.g. 2026-08-04T04:50:00Z)
```

**What it means:** from August 4th the historian sends instants in UTC; before it sent them in local time (UTC-5). Text comparisons stop being valid, and the same reading written in the two formats has different text, so a `(timestamp, tag)` key as text would not recognize it as a copy across the change. It also changes which day a reading belongs to depending on the zone.

**Decision:** bronze keeps the `timestamp` as text, as it arrived. In silver, convert it to an instant with zone (`timestamptz`, understanding both formats) and use that instant to compare and deduplicate. Use the UTC day in silver and gold. Work orders already come in UTC.

## My data dictionary

### Historian (`data/raw/historian/date=YYYY-MM-DD/readings_YYYYMMDD.csv.gz`)

**Grain:** one row = **one reading of one sensor at one instant** (every 10 minutes). One file per day; 150 days, from
2026-05-01 to 2026-09-27 (one of them truncated, see H4). A complete day is 20 pumps x 5 sensors x 144 readings =
**14,400 rows** (plus the copies from H1 and the repeated hour from H2).

| Column | What it is | Format / values |
|---|---|---|
| `timestamp` | Instant of the reading | ISO 8601 text. Until 2026-08-03 with zone `-05:00` (local plant time); from 2026-08-04 in UTC with `Z` (see H8) |
| `tag` | Which sensor of which pump | `PLT01.<pump>.<sensor>`, e.g. `PLT01.P111.RUN_STATE` |
| `value` | The measurement | Text with 3 decimals; may be empty or `-9999` (no reading, see H6) |
| `unit` | Unit of `value` | `degC`/`degF`, `kPa`/`bar`, `mm/s`, `A`, `bool` (see H5) |
| `quality` | Confidence of the reading | `GOOD`, `BAD`, `UNCERTAIN` (upper case, see H3) |

The 5 sensors of each pump: `VIB_MM_S` (vibration, mm/s), `TEMP_BEARING` (bearing temperature, °C), `PRESS_DISCH` (discharge
pressure, kPa), `CURRENT_A` (motor current, A) and `RUN_STATE` (is it running? 0/1). The `tag` names the pump as `PLT01.P101` (with a dot) while
`assets.csv` calls it `PLT01-P101` (with a hyphen): the identifier must be normalized to join them.

### `assets.csv` — pump master

**Grain:** one row = **one pump** (20 rows, all in plant `PLT01`). Columns: `asset_id` (key), `plant`, `model` (HX-90, CP-200, CP-350),
`install_date`, `criticality` (A, B, C), `rated_flow_m3h`, `rated_kw`.

### `work_orders.csv` — work orders

**Grain:** one row = **one work order** on a pump (185 rows, from 2026-05-07 to 2026-09-27). Columns: `wo_id`, `asset_id`,
`wo_type` (inspection, preventive or corrective; **corrective repairs are the failures** to predict; see H7), `opened_at` / `closed_at`
(in **UTC**, ending in `Z`, unlike the historian), `failure_mode` (`rodamiento`, `sello`, `cavitacion`; only 30 of 185 orders carry it),
`cost_usd`, `downtime_hours`, `description`. Careful when crossing the two sources: the historian was in local time (-05:00) and the orders are in UTC; bring both to the same zone before comparing.
