"""Step 4 — gold: one row per pump and day, with features free of temporal leakage and a correct label?"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

import duckdb
import pandas as pd
import pytest
from conftest import DATA, ROOT, columns, connect, dbt_test, find_table, ok, warehouse_path

HINT = "Run `make gold` (dbt build). Your model goes in dbt/models/gold/ and is called asset_daily_features."
KEYS = {"asset_id", "feature_date", "label_failure_7d"}


@pytest.fixture()
def con():
    c = connect(hint=HINT)
    yield c
    c.close()


@pytest.fixture()
def gold(con):
    t = find_table(con, "asset_daily_features", "gold", HINT)
    missing = KEYS - set(columns(con, t))
    ok(not missing, f"Gold is missing columns: {sorted(missing)} (see the contract in guide/04_gold.md).")
    return t


def test_grain(con, gold):
    dup = con.execute(f"select count(*) from (select asset_id, feature_date from {gold} group by all having count(*) > 1)").fetchone()[0]
    ok(dup == 0, f"{dup} repeated (asset_id, feature_date) combinations. The grain of gold is: ONE row per pump and day.")
    n_assets = con.execute(f"select count(distinct asset_id) from {gold}").fetchone()[0]
    ok(n_assets == 20, f"There are {n_assets} pumps in gold and there should be 20.")


def test_day_coverage(con, gold):
    sil = find_table(con, "sensor_readings", "silver", "Silver is missing.")
    last = con.execute(f"select max(cast(ts_utc as date)) from {sil}").fetchone()[0]
    expected = con.execute(f"select count(*) from (select distinct asset_id, cast(ts_utc as date) d from {sil}) where d <= ? - 7", [last]).fetchone()[0]
    labeled = con.execute(f"select count(*) from {gold} where label_failure_7d is not null").fetchone()[0]
    ok(labeled >= 0.9 * expected, f"You have {labeled:,} pump-days with a label and silver allows ≈ {expected:,}. Are you losing days (joins that drop rows)?")
    recent = con.execute(f"select count(*) from {gold} where feature_date > ? - 7 and label_failure_7d is not null", [last]).fetchone()[0]
    ok(recent == 0,
       f"There are {recent} rows from the last 7 days with a label. For those days the future has not happened yet: you cannot know whether the pump will fail.\n"
       "The label must be NULL (the row stays so you can score 'today', but without a label).")
    last_day = con.execute(f"select count(distinct asset_id) from {gold} where feature_date >= ? - 1", [last]).fetchone()[0]
    ok(last_day >= 18, "The most recent days are missing in gold: you need them to score TODAY's risk in step 7.")


def test_correct_label(con, gold):
    wo = pd.read_csv(DATA / "raw/reference/work_orders.csv")
    wo = wo[wo["wo_type"].str.lower() == "corrective"].copy()
    wo["d"] = pd.to_datetime(wo["opened_at"], utc=True).dt.tz_localize(None).dt.normalize()
    fails = wo.groupby("asset_id")["d"].apply(list).to_dict()
    df = con.execute(f"select asset_id, cast(feature_date as date) as d, label_failure_7d from {gold} where label_failure_7d is not null").df()
    df["d"] = pd.to_datetime(df["d"])
    expected = df.apply(lambda r: int(any(r["d"] < f <= r["d"] + pd.Timedelta(days=7) for f in fails.get(r["asset_id"], []))), axis=1)
    wrong = int((expected != df["label_failure_7d"].astype(int)).sum())
    ok(wrong == 0,
       f"{wrong} labels do not match the corrective work orders ({len(wo)} in total).\n"
       "Definition: label_failure_7d = 1 if there is a CORRECTIVE order opened between the day after feature_date and 7 days after it.\n"
       "Diagnostic hint: did you normalize the order type (upper/lower case)? Do you count the day of the failure itself?")
    ok(df["label_failure_7d"].sum() >= 100, "There are hardly any positive labels: check your definition.")


def test_enough_features_and_no_obvious_leakage(con, gold):
    df = con.execute(f"select * from {gold} where label_failure_7d is not null").df()
    feats = [c for c in df.columns if c not in KEYS and pd.api.types.is_numeric_dtype(df[c])]
    ok(len(feats) >= 8, f"You only have {len(feats)} numeric features and ≥ 8 are expected. Ideas: mean level, maximum, variability and trend of each sensor, and what part of the day it was running.")
    for c in feats:
        nulls = df[c].isna().mean()
        ok(nulls < 0.5, f"Feature `{c}` is null in {nulls:.0%} of the rows.")
        if df[c].std() > 0:
            corr = abs(df[c].corr(df["label_failure_7d"].astype(float)))
            ok(corr < 0.9, f"Feature `{c}` has correlation {corr:.2f} with the label. That is almost never real: it smells like leakage (does it use information from after feature_date?).")


def test_dbt_tests_in_gold():
    ok(list((ROOT / "dbt" / "models" / "gold").glob("*.yml")), "Document gold in a .yml inside dbt/models/gold/ (description and tests).")
    rc, passed, out = dbt_test("path:models/gold")
    ok(rc == 0, "`dbt test` on gold fails:\n" + "\n".join(out.strip().splitlines()[-12:]))
    ok(passed >= 3, f"There are only {passed} dbt tests in gold: add one for the grain, not_null on the keys and accepted values for the label.")


def test_your_leakage_test_exists_and_passes():
    f = ROOT / "tests" / "test_no_leakage.py"
    ok(f.exists(),
       "tests/test_no_leakage.py is missing.\nWrite a test that proves temporal invariance: if you delete the data after a day D, "
       "the features of the days before D must NOT change. It is THE test that separates a lab model from one that works in production.")
    proc = subprocess.run([sys.executable, "-m", "pytest", str(f), "-q", "-p", "no:cacheprovider", "--rootdir", str(ROOT), "-c", str(ROOT / "pyproject.toml")],
                          cwd=ROOT, capture_output=True, text=True, check=False)
    out = proc.stdout + proc.stderr
    ok("no tests ran" not in out and proc.returncode != 5, "tests/test_no_leakage.py contains no test (a `test_...` function).")
    ok(proc.returncode == 0, "Your tests/test_no_leakage.py fails. Either there is leakage in your features (an important finding!) or the test has an error:\n" + "\n".join(ln[:220] for ln in out.strip().splitlines()[-12:]))


def test_independent_temporal_invariance(tmp_path):
    """The check runs its own version of the test: it deletes the future from silver and rebuilds gold on a COPY.

    If any feature of a day before the cutoff changes, that feature used information from after that day.
    """
    cutoff = "2026-08-15"
    con = connect(hint=HINT)
    try:
        silver = find_table(con, "sensor_readings", "silver", "Silver is missing.")
        gold = find_table(con, "asset_daily_features", "gold", HINT)
    finally:
        con.close()
    copy = tmp_path / "wh.duckdb"
    shutil.copy(warehouse_path(), copy)

    c = duckdb.connect(str(copy))
    c.execute(f"delete from {silver} where ts_utc >= timestamp '{cutoff}'")
    c.close()
    cmd = [sys.executable, "-c", "from dbt.cli.main import cli; cli()", "build", "--project-dir", "dbt", "--profiles-dir", "dbt",
           "--select", "path:models/gold"]
    proc = subprocess.run(cmd, cwd=ROOT, env={**os.environ, "LH_WAREHOUSE": str(copy)}, capture_output=True, text=True, check=False)
    ok(proc.returncode == 0, "I could not rebuild gold on the truncated copy (does your profiles.yml read LH_WAREHOUSE?):\n" + "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-8:]))

    def feats(path):
        k = duckdb.connect(str(path), read_only=True)
        try:
            return k.sql(f"select * exclude (label_failure_7d) from {gold} where feature_date < date '{cutoff}'").df().sort_values(["asset_id", "feature_date"]).reset_index(drop=True)
        finally:
            k.close()

    full, trunc = feats(warehouse_path()), feats(copy)
    ok(len(full) == len(trunc), f"Deleting the future changed the NUMBER of rows before the cutoff ({len(full)} → {len(trunc)}).")
    bad = []
    for c_ in full.columns:
        a, b = full[c_], trunc[c_]
        if pd.api.types.is_numeric_dtype(a):
            same = (a.fillna(-9e9) - b.fillna(-9e9)).abs().lt(1e-6).all()
        else:
            same = a.astype(str).equals(b.astype(str))
        if not same:
            bad.append(c_)
    ok(not bad,
       f"TEMPORAL LEAKAGE: these features change when I delete the data after {cutoff}: {bad}.\n"
       "A day's feature can only depend on data up to the end of THAT day. Check windows (`following`), joins to tables with future dates, and aggregates over the whole table.")
