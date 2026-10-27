"""Step 6 — orchestration: does a single command run EVERYTHING in order, from scratch, in a clean folder?"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

import duckdb
import pytest
from conftest import DATA, ROOT, SRC, ok

MODULE = "lakehouse.definitions"


def _import_defs():
    import importlib

    err, mod = None, None
    try:
        mod = importlib.import_module(MODULE)
    except Exception as exc:  # noqa: BLE001
        err = exc
    ok(err is None, f"I cannot import src/lakehouse/definitions.py yet ({err!r}).\nIt must expose `defs = Definitions(assets=[...])` (see guide/06_orchestration.md).")
    ok(hasattr(mod, "defs"), "definitions.py must define `defs = Definitions(...)`.")
    return mod


def _graph():
    return _import_defs().defs.resolve_asset_graph()


def _longest_chain(graph) -> int:
    keys = list(graph.get_all_asset_keys())
    parents = {k: list(graph.get(k).parent_keys) for k in keys}
    memo: dict = {}

    def depth(k) -> int:
        if k not in memo:
            memo[k] = 1 + max([depth(p) for p in parents[k] if p in parents] or [0])
        return memo[k]

    return max(depth(k) for k in keys)


def test_the_graph_chains_the_layers():
    g = _graph()
    n = len(list(g.get_all_asset_keys()))
    ok(n >= 4, f"Your graph has {n} asset(s). At least 4 are expected (bronze, silver, gold, predictions).")
    chain = _longest_chain(g)
    ok(chain >= 4, f"The longest dependency chain has {chain} asset(s) and it must be ≥ 4: each layer depends on the previous one (deps=[...]). If you do not declare dependencies, Dagster does not know in which order to run them.")


def test_end_to_end_run_in_a_clean_folder(tmp_path_factory):
    """Materialize the WHOLE graph with Dagster pointing at empty temporary folders (your data is not touched)."""
    _import_defs()  # if it cannot even be imported, the message above already explains it
    tmp = tmp_path_factory.mktemp("e2e")
    shutil.copytree(DATA / "raw" / "reference", tmp / "raw" / "reference")
    # the first 120 days: faster than 150, and they keep all the traps (format, blackout, corrupt file, units)
    days = sorted((DATA / "raw" / "historian").glob("date=*"))
    for d in days[:120]:
        shutil.copytree(d, tmp / "raw" / "historian" / d.name)
    env = {
        **os.environ, "PYTHONPATH": str(SRC), "DAGSTER_HOME": str(tmp / "dagster_home"),
        "LH_RAW_DIR": str(tmp / "raw"), "LH_BRONZE_DIR": str(tmp / "bronze"), "LH_QUARANTINE_DIR": str(tmp / "q"),
        "LH_WAREHOUSE": str(tmp / "wh.duckdb"), "LH_MODELS_DIR": str(tmp / "models"),
    }
    (tmp / "dagster_home").mkdir()
    proc = subprocess.run(
        [sys.executable, "-m", "dagster", "asset", "materialize", "-m", MODULE, "--select", "*"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=900, check=False,
    )
    out = (proc.stdout + proc.stderr).strip().splitlines()
    ok(proc.returncode == 0, "`dagster asset materialize --select '*'` failed. Last lines:\n" + "\n".join(ln[:200] for ln in out[-8:])
       + "\n\nIf it was because of a hard-coded path in your code: use lakehouse.paths (LH_* variables).")
    wh = tmp / "wh.duckdb"
    ok(wh.exists(), "The run finished but did not create the warehouse at the path given by LH_WAREHOUSE: does your dbt (profiles.yml) read the environment variable?")
    con = duckdb.connect(str(wh), read_only=True)
    try:
        n = con.execute("select count(*) from ml.predictions").fetchone()[0]
    finally:
        con.close()
    ok(n > 0, "The full run did not produce ml.predictions.")
    ok((tmp / "models" / "metrics.json").exists(), "The full run did not write metrics.json in LH_MODELS_DIR.")


@pytest.mark.bonus
def test_bonus_asset_check():
    g = _graph()
    checks = list(g.asset_check_keys) if hasattr(g, "asset_check_keys") else []
    ok(checks, "CHALLENGE: add at least one Dagster asset check (for example: 'there are no files in quarantine' or 'the predictions are from today'). Pipelines that fail silently are the worst.")
