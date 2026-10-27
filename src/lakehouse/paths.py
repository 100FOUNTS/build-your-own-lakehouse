"""Project paths (already done, just use it).

Why it exists: in a real job the same code runs on your laptop, in CI and in production, and each place stores the data
somewhere different. So paths are NOT written inside the code: they are read from environment variables with a default
value. The checks of this exercise (and Dagster) change the paths so that your code can run in temporary folders without
touching your data. If you hard-code a path in your code, the checks will fail.

    LH_RAW_DIR         raw files from the historian         (default data/raw)
    LH_BRONZE_DIR      bronze layer (Parquet)               (default data/bronze)
    LH_QUARANTINE_DIR  files that could not be read         (default data/quarantine)
    LH_WAREHOUSE       DuckDB database (silver, gold, ml)   (default data/warehouse.duckdb)
    LH_MODELS_DIR      trained model and metrics            (default data/models)
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _get(var: str, default: str) -> Path:
    value = os.environ.get(var)
    return Path(value) if value else ROOT / default


def raw_dir() -> Path:
    return _get("LH_RAW_DIR", "data/raw")


def bronze_dir() -> Path:
    return _get("LH_BRONZE_DIR", "data/bronze")


def quarantine_dir() -> Path:
    return _get("LH_QUARANTINE_DIR", "data/quarantine")


def warehouse_path() -> Path:
    return _get("LH_WAREHOUSE", "data/warehouse.duckdb")


def models_dir() -> Path:
    return _get("LH_MODELS_DIR", "data/models")
