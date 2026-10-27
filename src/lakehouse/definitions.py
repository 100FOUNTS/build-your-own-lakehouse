"""Orchestration with Dagster: the pipeline as a graph of data assets.

What is here: the bronze asset, silver and gold with dbt (which FAIL if dbt fails), the predictions, and a quarantine
asset check. Each asset CALLS the code that already exists (`lakehouse.bronze.run()`...): no logic is copied here, we
only describe what depends on what. Start it with `make dagster` (UI at http://localhost:3000).
"""

import json
import subprocess
import sys

from dagster import (
    AssetCheckResult,
    AssetCheckSeverity,
    AssetExecutionContext,
    Definitions,
    MaterializeResult,
    asset,
    asset_check,
)

from lakehouse import bronze, train
from lakehouse.paths import ROOT, models_dir, quarantine_dir


def _dbt_build(context: AssetExecutionContext, selection: str, indirect_selection: str = "eager") -> None:
    """Run `dbt build` on a selection of models and FAIL if dbt fails.

    It runs in a SUBPROCESS because DuckDB only allows one writer and dbt keeps the file open while its process lives:
    this way it releases it when done and the next asset (the model) can write to the same database.
    The subprocess inherits the LH_* variables (LH_WAREHOUSE, LH_BRONZE_DIR...), which is what lets the check
    run the whole pipeline in temporary folders without touching your data.
    """
    result = subprocess.run(
        [sys.executable, "-c", "from dbt.cli.main import cli; cli()", "build",
         "--project-dir", "dbt", "--profiles-dir", "dbt", "--select", selection, "--indirect-selection", indirect_selection],
        cwd=ROOT, capture_output=True, text=True, check=False,   # the exit code is checked by hand below
    )
    context.log.info(result.stdout[-3000:])   # the end of dbt's output: the PASS / ERROR summary
    if result.returncode != 0:
        # Raising the exception is what turns the asset RED and makes Dagster NOT run the assets that depend on it.
        # A "green" asset that loaded nothing would be worse than a red one.
        raise RuntimeError(f"dbt build ({selection}) failed:\n{(result.stdout + result.stderr)[-2000:]}")


@asset(group_name="lakehouse", description="Raw historian files and reference tables -> Parquet in bronze.")
def bronze_readings() -> MaterializeResult:
    # bronze.run() is already idempotent (it skips loaded files) and succeeds even with broken files: a file in
    # quarantine is a warning, not a failure. That is why we make it VISIBLE here: the number of quarantined files
    # is stored in the asset's metadata and shows in the Dagster UI, not just in the terminal.
    bronze.run()
    quarantined = len(list(quarantine_dir().rglob("*.reason.txt")))
    return MaterializeResult(metadata={"files_in_quarantine": quarantined})


@asset(deps=[bronze_readings], group_name="lakehouse", description="Bronze -> silver: clean readings, no duplicates, in standard units.")
def silver_tables(context: AssetExecutionContext) -> None:
    # "cautious": only the tests whose models are ALL selected run. Without it, dbt would add gold's `relationships`
    # test (which looks at `assets`, from silver) before gold exists, and in a clean folder it would fail.
    _dbt_build(context, "path:models/silver", indirect_selection="cautious")


@asset(deps=[silver_tables], group_name="lakehouse", description="Silver -> gold: one row per pump and day, with features and label.")
def gold_features(context: AssetExecutionContext) -> None:
    _dbt_build(context, "path:models/gold")


@asset(deps=[gold_features], group_name="lakehouse", description="Gold -> trained model, metrics.json and ml.predictions (risk of each pump and day).")
def risk_predictions() -> MaterializeResult:
    # train.run() trains, measures, saves the model and writes ml.predictions. If anything fails, it raises and the asset
    # turns red. Then the metrics it just wrote are read and shown in the UI: seeing whether the model is still good does
    # not require opening files. Each Dagster step runs in its own process, which ends with the asset and releases
    # the DuckDB database.
    train.run()
    metrics = json.loads((models_dir() / "metrics.json").read_text())
    return MaterializeResult(metadata={
        "average_precision": metrics["average_precision"],
        "baseline_average_precision": metrics["baseline_average_precision"],
        "n_test_positives": metrics["n_test_positives"],
    })


@asset_check(asset=bronze_readings, description="There are no historian files set aside in quarantine.")
def no_files_in_quarantine() -> AssetCheckResult:
    """A broken file does NOT make bronze fail (it is a warning, not a programming error), so without this check only
    whoever reads the terminal text would see it. Here it shows in the UI, with the file and the reason.
    WARN severity: it turns yellow, warns, but does not stop the pipeline (the rest of the files did load)."""
    reasons = sorted(quarantine_dir().rglob("*.reason.txt"))
    detail = []
    for reason in reasons:
        first_lines = reason.read_text().splitlines()[:3]       # file, when and error type (without the long detail)
        detail.append(" | ".join(first_lines))
    return AssetCheckResult(
        passed=not reasons,
        severity=AssetCheckSeverity.WARN,
        description="No files in quarantine." if not reasons else f"{len(reasons)} file(s) in quarantine: ask the provider to re-send them.",
        metadata={"files_in_quarantine": len(reasons), "detail": "\n".join(detail) or "none"},
    )


defs = Definitions(
    assets=[bronze_readings, silver_tables, gold_features, risk_predictions],
    asset_checks=[no_files_in_quarantine],
)
