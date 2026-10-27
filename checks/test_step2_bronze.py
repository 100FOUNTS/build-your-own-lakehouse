"""Step 2 — bronze: did you keep everything that arrived, without duplicating on repeat and without breaking on bad files?"""

from __future__ import annotations

import shutil
from pathlib import Path

import duckdb
import pandas as pd
import pytest
from conftest import DATA, ROOT, ok, raw_readings, run_module, tail, truth

RAW_COLS = ["timestamp", "tag", "value", "unit", "quality"]


def _count(bronze: Path, table: str = "readings") -> int:
    files = list((bronze / table).rglob("*.parquet"))
    if not files:
        return 0
    return duckdb.sql(f"select count(*) from read_parquet('{bronze / table}/**/*.parquet')").fetchone()[0]


def _cols(bronze: Path, table: str = "readings") -> set[str]:
    return set(duckdb.sql(f"select * from read_parquet('{bronze / table}/**/*.parquet') limit 0").df().columns)


def _expected_rows(raw: Path) -> int:
    df, _ = raw_readings.__wrapped__(str(raw))  # no cache: the test folder changes between steps
    return len(df)


def test_the_raw_data_is_still_intact():
    """Golden rule of bronze: what arrived is NEVER edited."""
    manifest = truth()["raw_manifest"]
    changed = []
    for rel, size in manifest.items():
        for base in (DATA / "raw", DATA / "incoming"):
            f = base / rel
            if f.exists() and f.stat().st_size != size:
                changed.append(rel)
    ok(not changed, f"These files in data/raw were modified: {changed[:3]}. Bronze is immutable: restore the data (it is never edited).")


def test_your_bronze_has_everything_readable():
    bronze = DATA / "bronze"
    ok(any((bronze / "readings").rglob("*.parquet")) if (bronze / "readings").exists() else False,
       "There is no Parquet in data/bronze/readings. Run `make bronze`.")
    cols = _cols(bronze)
    missing = [c for c in RAW_COLS + ["_source_file", "_ingested_at"] if c not in cols]
    ok(not missing, f"Bronze is missing columns: {missing}. Keep the 5 original ones and add `_source_file` and `_ingested_at` (where and when each row arrived: traceability is the value of bronze).")
    expected, n = _expected_rows(DATA / "raw"), _count(bronze)
    ok(n == expected,
       f"Bronze has {n:,} rows and the readable raw data has {expected:,}.\n"
       "Bronze must keep EVERYTHING as it arrived, including duplicates and BAD readings (cleaning is silver's job).\n"
       f"Difference: {n - expected:+,}. Think: did you read each file by column name? Did any file lose or gain rows?")


def test_reference_tables_in_bronze():
    bronze = DATA / "bronze"
    for name, n_expected in (("assets", 20), ("work_orders", len(pd.read_csv(DATA / "raw/reference/work_orders.csv")))):
        ok(any((bronze / name).rglob("*.parquet")) if (bronze / name).exists() else False,
           f"bronze/{name} is missing: the reference tables also go through bronze (folder data/bronze/{name}/).")
        ok(_count(bronze, name) == n_expected, f"bronze/{name} has {_count(bronze, name)} rows and should have {n_expected}. Did it get duplicated when you ran twice?")


@pytest.fixture(scope="module")
def sandbox(tmp_path_factory):
    """Copy part of the raw data to a temporary folder to test your ingestion without touching your data."""
    tmp = tmp_path_factory.mktemp("bronze_sandbox")
    raw = tmp / "raw"
    (raw / "historian").mkdir(parents=True)
    shutil.copytree(DATA / "raw" / "reference", raw / "reference")
    days = sorted((DATA / "raw" / "historian").glob("date=*"))
    first, later = days[:-3], days[-3:]
    incoming = sorted((DATA / "incoming" / "historian").glob("date=*"))[:2]
    for d in first:
        shutil.copytree(d, raw / "historian" / d.name)
    env = {
        "LH_RAW_DIR": str(raw), "LH_BRONZE_DIR": str(tmp / "bronze"), "LH_QUARANTINE_DIR": str(tmp / "quarantine"),
        "LH_WAREHOUSE": str(tmp / "wh.duckdb"),
    }
    return {"tmp": tmp, "raw": raw, "env": env, "later": later + incoming, "bronze": tmp / "bronze", "quarantine": tmp / "quarantine"}


def test_first_run_from_scratch(sandbox):
    p = run_module("lakehouse.bronze", sandbox["env"])
    ok(p.returncode == 0, f"`python -m lakehouse.bronze` ended with an error (code {p.returncode}). One bad file must NOT bring down the whole ingestion.\n\n{tail(p)}")
    n, expected = _count(sandbox["bronze"]), _expected_rows(sandbox["raw"])
    ok(n == expected, f"In the test folder you loaded {n:,} rows and {expected:,} were expected.")


def test_corrupt_file_goes_to_quarantine(sandbox):
    q = sandbox["quarantine"]
    ok(q.exists() and any(q.rglob("*")), "A raw file is corrupt (truncated gzip) and I find nothing in your quarantine folder. Do not ignore it silently: store/record it there with the reason.")
    mentioned = any("20260701" in p.name or "2026-07-01" in p.name for p in q.rglob("*")) or any(
        "20260701" in p.read_text(errors="ignore") or "2026-07-01" in p.read_text(errors="ignore")
        for p in q.rglob("*") if p.is_file() and p.stat().st_size < 1_000_000 and p.suffix != ".gz"
    )
    ok(mentioned, "There is something in quarantine, but it does not identify the defective file (readings_20260701.csv.gz). Record which one it was and why.")
    sources = duckdb.sql(f"select distinct _source_file from read_parquet('{sandbox['bronze']}/readings/**/*.parquet')").df()["_source_file"]
    ok(not sources.str.contains("20260701").any(), "There are rows from the corrupt file inside bronze: either it is loaded whole or it is not loaded (nothing half-way).")


def test_repeating_does_not_duplicate(sandbox):
    n0 = _count(sandbox["bronze"])
    p = run_module("lakehouse.bronze", sandbox["env"])
    ok(p.returncode == 0, f"The second run failed:\n{tail(p)}")
    n1 = _count(sandbox["bronze"])
    ok(n1 == n0, f"IDEMPOTENCY: running twice changed the count from {n0:,} to {n1:,}. In production jobs are retried: repeating must NEVER duplicate data.")
    for name in ("assets", "work_orders"):
        ok(_count(sandbox["bronze"], name) > 0, f"After repeating, bronze/{name} ended up empty.")


def test_new_files_arrive_and_only_the_new_ones_are_loaded(sandbox):
    for d in sandbox["later"]:
        shutil.copytree(d, sandbox["raw"] / "historian" / d.name)
    p = run_module("lakehouse.bronze", sandbox["env"])
    ok(p.returncode == 0, f"The run with new files failed:\n{tail(p)}")
    n, expected = _count(sandbox["bronze"]), _expected_rows(sandbox["raw"])
    ok(n == expected, f"After {len(sandbox['later'])} new days arrived you have {n:,} rows and {expected:,} were expected. It must add up exactly the rows of the new files.")
    p = run_module("lakehouse.bronze", sandbox["env"])
    ok(_count(sandbox["bronze"]) == expected, "One more run and the count changed: it is not idempotent.")


def test_you_documented_your_decision():
    adr = ROOT / "notes" / "02_bronze_decisions.md"
    ok(adr.exists() and "TODO-STUDENT" not in adr.read_text() and "TODO-ALUMNO" not in adr.read_text(),
       "Answer the questions in notes/02_bronze_decisions.md (how do you detect what was already loaded? why Parquet? what happens if a file changes?). It is the part most asked about in interviews.")
