"""Shared utilities for the checks.

The checks are NOT your enemy: they are a companion that verifies, with data, what each step of the guide says.
When one fails, the message tells you WHAT is not met and WHY it matters; it never gives you the solution.
You do not need to read these files to make progress (and `_truth.json` is a spoiler for step 1: do not open it).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import duckdb
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

DATA = ROOT / "data"


def ok(cond: object, msg: str) -> None:
    """Fail with a clean message (no traceback) if the condition is not met."""
    if not cond:
        pytest.fail("\n\n  " + msg.strip().replace("\n", "\n  ") + "\n", pytrace=False)


@lru_cache
def truth() -> dict:
    return json.loads((ROOT / "checks" / "_truth.json").read_text())


def run_module(module: str, env: dict[str, str] | None = None, timeout: int = 600) -> subprocess.CompletedProcess:
    """Run `python -m <module>` the way you would in the terminal, with optional paths through the environment."""
    full_env = {**os.environ, "PYTHONPATH": str(SRC), **(env or {})}
    return subprocess.run(
        [sys.executable, "-m", module], cwd=ROOT, env=full_env, capture_output=True, text=True, timeout=timeout,
        check=False,
    )


def tail(proc: subprocess.CompletedProcess, n: int = 15) -> str:
    text = (proc.stdout or "") + (proc.stderr or "")
    return "\n".join(text.strip().splitlines()[-n:])


def warehouse_path() -> Path:
    return Path(os.environ.get("LH_WAREHOUSE") or DATA / "warehouse.duckdb")


def connect(path: Path | None = None, hint: str = "") -> duckdb.DuckDBPyConnection:
    p = path or warehouse_path()
    ok(p.exists(), f"{p.relative_to(ROOT) if p.is_relative_to(ROOT) else p} does not exist. {hint}")
    err = None
    try:
        return duckdb.connect(str(p), read_only=True)
    except duckdb.Error as exc:
        err = exc
    ok(False, f"I could not open the database in read mode ({err}).\nDuckDB allows ONE writer: close whatever has it open (dbt, a notebook, the API) and try again.")


def find_table(con: duckdb.DuckDBPyConnection, name: str, schema_endswith: str, hint: str) -> str:
    """Find table `name` in a schema ending in `schema_endswith` (accepts 'silver' or 'main_silver')."""
    rows = con.execute(
        "select table_schema from information_schema.tables where table_name = ? and table_schema like ?",
        [name, f"%{schema_endswith}"],
    ).fetchall()
    ok(rows, f"I cannot find table `{name}` in a '{schema_endswith}' schema. {hint}")
    return f"{rows[0][0]}.{name}"


def columns(con: duckdb.DuckDBPyConnection, fq_table: str) -> dict[str, str]:
    schema, name = fq_table.split(".")
    rows = con.execute(
        "select column_name, data_type from information_schema.columns where table_schema = ? and table_name = ?",
        [schema, name],
    ).fetchall()
    return dict(rows)


# ------------------------------------------------------------------ independent truth computed from the raw data
@lru_cache
def raw_readings(raw_dir: str) -> tuple[pd.DataFrame, list[str]]:
    """Read ALL the readable raw files with pandas (independent of your code).

    Returns (rows, unreadable_files). It tells us how many rows each layer should have.
    """
    frames, bad = [], []
    for f in sorted(Path(raw_dir, "historian").glob("date=*/*.csv.gz")):
        try:
            df = pd.read_csv(f, dtype=str, keep_default_na=False)
        except Exception:  # noqa: BLE001
            bad.append(f.name)
            continue
        df["_file"] = f.name
        frames.append(df)
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()), bad


@lru_cache
def expected_clean_keys(raw_dir: str) -> int:
    """How many unique readings (tag, UTC instant) with GOOD/UNCERTAIN quality should exist after cleaning."""
    df, _ = raw_readings(raw_dir)
    df = df[df["quality"].isin(["GOOD", "UNCERTAIN"])]
    ts = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601")
    return int(pd.DataFrame({"tag": df["tag"].to_numpy(), "ts": ts.to_numpy()}).drop_duplicates().shape[0])


def dbt_test(select: str, env: dict[str, str] | None = None) -> tuple[int, int, str]:
    """Run `dbt test` on a selection and return (exit_code, tests_that_passed, output)."""
    cmd = [sys.executable, "-c", "from dbt.cli.main import cli; cli()", "test", "--project-dir", "dbt",
           "--profiles-dir", "dbt", "--select", select]
    proc = subprocess.run(cmd, cwd=ROOT, env={**os.environ, **(env or {})}, capture_output=True, text=True, check=False)
    out = proc.stdout + proc.stderr
    m = re.search(r"PASS=(\d+)", out)
    return proc.returncode, int(m.group(1)) if m else 0, out
