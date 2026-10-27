"""Step 3 — silver: clean data, standard units, no duplicates and with the evidence flagged?"""

from __future__ import annotations

import pandas as pd
import pytest
from conftest import DATA, ROOT, columns, connect, dbt_test, expected_clean_keys, find_table, ok, truth

HINT = "Run `make silver` (dbt build). The models go in dbt/models/silver/."
REQUIRED = {"asset_id", "ts_utc", "sensor", "value", "unit", "is_outlier"}


@pytest.fixture()
def con():
    c = connect(hint=HINT)
    yield c
    c.close()


@pytest.fixture()
def sr(con):
    t = find_table(con, "sensor_readings", "silver", HINT)
    cols = columns(con, t)
    missing = REQUIRED - set(cols)
    ok(not missing, f"silver.sensor_readings is missing columns: {sorted(missing)}. Contract: {sorted(REQUIRED)} (see guide/03_silver.md).")
    return t


def test_grain_and_nulls(con, sr):
    dup = con.execute(f"select count(*) from (select asset_id, ts_utc, sensor from {sr} group by all having count(*) > 1)").fetchone()[0]
    ok(dup == 0, f"The grain (asset_id, ts_utc, sensor) has {dup:,} repeated combinations. There are duplicates inside a file, between files and because of the time-zone overlap: did you cover them all?")
    nulls = con.execute(f"select count(*) from {sr} where asset_id is null or ts_utc is null or sensor is null or value is null").fetchone()[0]
    ok(nulls == 0, f"There are {nulls:,} rows with nulls in key columns. BAD readings do not enter silver.")


def test_types(con, sr):
    cols = columns(con, sr)
    ok("TIMESTAMP" in cols["ts_utc"].upper(), f"ts_utc should be TIMESTAMP (it is {cols['ts_utc']}).")
    ok(cols["value"].upper() in {"DOUBLE", "FLOAT", "DECIMAL"} or cols["value"].upper().startswith("DECIMAL"), f"value must be numeric (it is {cols['value']}).")
    ok(cols["is_outlier"].upper() == "BOOLEAN", f"is_outlier must be BOOLEAN (it is {cols['is_outlier']}).")


def test_date_format_and_time_zone(con, sr):
    mn = str(con.execute(f"select min(ts_utc) from {sr}").fetchone()[0])
    ok(mn.startswith("2026-05-01 05:00"),
       f"The oldest reading in UTC is {mn} and it should be 2026-05-01 05:00:00.\n"
       "The first files carry the plant's LOCAL time with its offset (e.g. -05:00): you must convert to UTC, not ignore the offset.\n"
       "And note: later the exporter changes format (did you notice in step 1?).")


def test_reasonable_row_count(con, sr):
    expected = expected_clean_keys(str(DATA / "raw"))
    n = con.execute(f"select count(*) from {sr}").fetchone()[0]
    ok(0.985 * expected <= n <= 1.002 * expected,
       f"silver.sensor_readings has {n:,} rows; with the readable raw data, without BAD and without duplicates I would expect ≈ {expected:,} (±1.5 %).\n"
       "If you have too many: duplicates or BAD remain. If you have too few: you are discarding good data.")


def test_standard_units(con, sr):
    units = {r[0]: r[1] for r in con.execute(f"select sensor, list(distinct unit) from {sr} group by 1").fetchall()}
    expected = {"VIB_MM_S": ["mm/s"], "TEMP_BEARING": ["degC"], "PRESS_DISCH": ["kPa"], "CURRENT_A": ["A"], "RUN_STATE": ["bool"]}
    ok({k: sorted(v) for k, v in units.items()} == expected, f"Each sensor must have ONE standard unit. Right now: {units}")
    asset_t, day_t = truth()["special"]["temp_degF"]
    asset_p, day_p = truth()["special"]["press_bar"]
    for asset, sensor, day, tol, what in ((asset_t, "TEMP_BEARING", day_t, 10.0, "°C"), (asset_p, "PRESS_DISCH", day_p, 60.0, "kPa")):
        r = con.execute(
            f"""select
                avg(value) filter (where ts_utc >= timestamp '{day}' - interval 3 day and ts_utc < timestamp '{day}'),
                avg(value) filter (where ts_utc >= timestamp '{day}' + interval 1 day and ts_utc < timestamp '{day}' + interval 4 day)
            from {sr} where asset_id = ? and sensor = ? and not is_outlier""", [asset, sensor]).fetchone()
        ok(abs(r[0] - r[1]) < tol,
           f"{asset} {sensor}: the average jumps from {r[0]:.1f} to {r[1]:.1f} {what} around {day}. "
           "A change like that without a real failure is a sign that a different unit is hiding. Look at the `unit` column of the raw data.")


def test_plausible_physical_values(con, sr):
    ranges = {"VIB_MM_S": (0, 12), "TEMP_BEARING": (-10, 130), "PRESS_DISCH": (-5, 700), "CURRENT_A": (0, 120)}
    for sensor, (lo, hi) in ranges.items():
        n = con.execute(f"select count(*) from {sr} where sensor = ? and not is_outlier and (value < ? or value > ?)", [sensor, lo, hi]).fetchone()[0]
        ok(n == 0, f"{sensor}: {n:,} values outside [{lo}, {hi}] that are NOT flagged as outliers. Check units, sentinels (-9999) or your outlier rule.")


def test_spikes_flagged_without_flooding(con, sr):
    spikes = pd.DataFrame(truth()["spikes"])
    spikes["ts_utc"] = pd.to_datetime(spikes["ts_utc"], utc=True).dt.tz_localize(None)
    con.register("spikes_df", spikes)
    r = con.execute(
        f"""select count(*) as total,
                   count(*) filter (where s.is_outlier is null or s.is_outlier) as handled
            from spikes_df k left join {sr} s
              on s.asset_id = k.asset_id and s.sensor = k.sensor and s.ts_utc = k.ts_utc"""
    ).fetchone()
    total, handled = r
    ok(handled / total >= 0.85, f"You flagged only {handled} of {total} real spurious spikes as outliers ({handled/total:.0%}); ≥ 85 % is expected. A spike with GOOD quality is not detected by the quality flag: what do you compare it against?")
    n, flagged = con.execute(f"select count(*), count(*) filter (where is_outlier) from {sr}").fetchone()
    ok(flagged / n < 0.02, f"You flag {flagged:,} readings ({flagged/n:.1%}) as outliers. That is too many: a rule that flags 2 % of everything no longer distinguishes anything (and would delete real failures).")
    ok(flagged >= 20, "You hardly flag any readings as outliers.")


def test_reference_tables_in_silver(con):
    wo = find_table(con, "work_orders", "silver", HINT)
    types = {r[0] for r in con.execute(f"select distinct wo_type from {wo}").fetchall()}
    ok(types == {"PREVENTIVE", "CORRECTIVE", "INSPECTION"}, f"wo_type must be normalized to PREVENTIVE/CORRECTIVE/INSPECTION and it has {sorted(types)}. If you do not normalize it, your step 4 label will lose failures.")
    cols = columns(con, wo)
    ok("TIMESTAMP" in cols.get("opened_at", "").upper(), f"work_orders.opened_at must be TIMESTAMP (it is {cols.get('opened_at')}).")
    n_wo = con.execute(f"select count(*) from {wo}").fetchone()[0]
    ok(n_wo == len(pd.read_csv(DATA / "raw/reference/work_orders.csv")), f"work_orders has {n_wo} rows; the raw data has a different number.")
    assets = find_table(con, "assets", "silver", HINT)
    ok(con.execute(f"select count(*) from {assets}").fetchone()[0] == 20, "silver.assets must have the 20 pumps.")


def test_dbt_tests_exist_and_pass():
    ok(list((ROOT / "dbt" / "models" / "silver").glob("*.yml")), "Document your silver models in a .yml (descriptions and tests) inside dbt/models/silver/.")
    rc, passed, out = dbt_test("path:models/silver")
    ok(rc == 0, "`dbt test` on silver fails:\n" + "\n".join(out.strip().splitlines()[-12:]))
    ok(passed >= 5, f"There are only {passed} dbt tests in silver. A layer without tests is a layer nobody can trust: add not_null, accepted_values and a grain test.")
