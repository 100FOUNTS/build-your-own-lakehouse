"""Temporal invariance test of gold: does any feature of a day use data from AFTER that day?

Idea: if I delete from silver all the readings after a cutoff date and rebuild gold, the features of the days BEFORE the
cutoff must stay identical. If they change, they used data from the future to be computed (leakage).
The label is excluded from the comparison: it is the only thing that looks into the future on purpose.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import duckdb
import pandas as pd

from lakehouse.paths import ROOT, warehouse_path

CUTOFF = "2026-08-15"                     # in the middle of the data: there is a lot of past and a lot of future to delete
SILVER = "main_silver.sensor_readings"    # dbt concatenates the default schema (main) with the project's one
GOLD = "main_gold.asset_daily_features"
KEYS = ["asset_id", "feature_date"]


def _features_before_cutoff(path: Path) -> pd.DataFrame:
    """The features (without the label) of the days before the cutoff, sorted so they can be compared."""
    con = duckdb.connect(str(path), read_only=True)
    try:
        return (
            con.sql(f"select * exclude (label_failure_7d) from {GOLD} where feature_date < date '{CUTOFF}'")
            .df()
            .sort_values(KEYS)
            .reset_index(drop=True)
        )
    finally:
        con.close()


def test_features_do_not_change_when_the_future_is_deleted(tmp_path):
    # 1. A COPY of the warehouse: the original is never touched.
    copy = tmp_path / "warehouse_without_future.duckdb"
    shutil.copy(warehouse_path(), copy)

    # 2. In the copy, delete the silver readings from the cutoff onwards.
    con = duckdb.connect(str(copy))
    deleted = con.execute(f"select count(*) from {SILVER} where ts_utc >= timestamp '{CUTOFF}'").fetchone()[0]
    con.execute(f"delete from {SILVER} where ts_utc >= timestamp '{CUTOFF}'")
    con.close()
    # If nothing was deleted, the test would pass without testing anything.
    assert deleted > 0, f"There were no readings after {CUTOFF}: the test would not be checking anything."

    # 3. Rebuild gold on the copy. It runs in a SUBPROCESS because DuckDB only lets one process write at a time
    #    and dbt needs to release the file when it finishes. LH_WAREHOUSE tells profiles.yml which database to use.
    proc = subprocess.run(
        [sys.executable, "-c", "from dbt.cli.main import cli; cli()", "run",
         "--project-dir", "dbt", "--profiles-dir", "dbt", "--select", "path:models/gold"],
        cwd=ROOT, env={**os.environ, "LH_WAREHOUSE": str(copy)}, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, "dbt could not rebuild gold on the copy:\n" + (proc.stdout + proc.stderr)[-1500:]

    # 4. Compare the features from before the cutoff: the original database against the one without future.
    full = _features_before_cutoff(warehouse_path())
    truncated = _features_before_cutoff(copy)

    assert len(full) == len(truncated), (
        f"Deleting the future changed the number of rows before the cutoff: {len(full)} -> {len(truncated)}."
    )
    # One column at a time, to say WHICH one leaks. NULLs are treated as equal to each other.
    leaking = []
    for column in full.columns:
        a, b = full[column], truncated[column]
        if pd.api.types.is_numeric_dtype(a):
            same = (a.isna() == b.isna()).all() and ((a - b).abs().fillna(0) < 1e-9).all()
        else:
            same = a.astype(str).equals(b.astype(str))
        if not same:
            leaking.append(column)
    assert not leaking, (
        f"TEMPORAL LEAKAGE: these features change when the data after {CUTOFF} is deleted: {leaking}. "
        "A day's feature can only depend on data up to that day: look for `following` in the windows."
    )
