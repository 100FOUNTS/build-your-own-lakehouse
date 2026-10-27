"""Step 0 — is your environment ready and did the data arrive?"""

from __future__ import annotations

import importlib
import shutil
import sys

import pytest
from conftest import DATA, ROOT, ok


def test_python_and_uv():
    ok(sys.version_info[:2] == (3, 12), f"Python 3.12 was expected and you have {sys.version.split()[0]}. Use `uv sync`.")
    ok(shutil.which("uv"), "I cannot find `uv`. Install it: https://docs.astral.sh/uv/ (on macOS: brew install uv).")


@pytest.mark.parametrize("module", ["duckdb", "pandas", "pyarrow", "sklearn", "dagster", "fastapi", "dbt.cli.main"])
def test_libraries(module):
    err = None
    try:
        importlib.import_module(module)
    except ImportError as exc:
        err = exc
    ok(err is None, f"`{module}` cannot be imported ({err}).\nRun `make setup` (and `make fix-venv` on macOS).")


def test_raw_data_arrived():
    hist = sorted((DATA / "raw" / "historian").glob("date=*/readings_*.csv.gz"))
    ok(len(hist) >= 150, f"I expected 150 daily files in data/raw/historian and there are {len(hist)}. Did you move or delete something?")
    for name in ("assets.csv", "work_orders.csv"):
        ok((DATA / "raw" / "reference" / name).exists(), f"data/raw/reference/{name} is missing")


def test_notes_folder():
    ok((ROOT / "notes" / "01_findings.md").exists(), "notes/01_findings.md is missing (it is your step 1 notebook).")
