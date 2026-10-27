"""Model: estimate the probability that a pump fails within the next 7 days.

What is here: read gold, choose the features, split time into train / gap / test / live and train a model; measure
with AP on train and test against chance; save the model, metrics.json and the ml.predictions table with the risk of
each pump and day.
`run()` is what `make train` runs (`python -m lakehouse.train`).
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import joblib
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score

from lakehouse.paths import models_dir, warehouse_path

GOLD = "main_gold.asset_daily_features"   # dbt concatenates the default schema (main) with the project's one
LABEL = "label_failure_7d"
KEYS = ["asset_id", "feature_date"]

# Split decisions. They are expressed in DAYS and not in fixed dates: when new data arrives (step 6), the cutoff is
# recomputed by itself and we do not end up training with an outdated past.
TEST_DAYS = 36   # ~11 independent failures in the test; more days = more stable metric, less data to learn from
GAP_DAYS = 7     # = how many days ahead the label looks: with no gap, the training labels already "see" the test


def read_gold() -> pd.DataFrame:
    """Read the whole gold table. READ-ONLY connection: it does not lock the warehouse for other processes."""
    con = duckdb.connect(str(warehouse_path()), read_only=True)
    try:
        df = con.sql(f"select * from {GOLD}").df()
    finally:
        con.close()
    df["feature_date"] = pd.to_datetime(df["feature_date"])
    return df


def choose_features(df: pd.DataFrame) -> list[str]:
    """The numeric columns that are NOT the label nor the keys.

    The label is the answer (copying it would be cheating). The keys would make the model memorize pumps or dates
    instead of learning the behavior of a degrading pump.
    """
    numeric = df.select_dtypes("number").columns
    return [c for c in numeric if c != LABEL and c not in KEYS]


def split_in_time(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Timestamp, pd.Timestamp]:
    """Add the `split` column (train / purge / test / live) and return the cutoff dates.

    train_end and test_start come from the data: the test is the last TEST_DAYS days WITH a label, and before it
    GAP_DAYS days are discarded (`purge`). The rows without a label (last 7 days) are `live`: they cannot be
    evaluated, but they are the ones scored "today".
    """
    labeled = df[LABEL].notna()
    last_labeled = df.loc[labeled, "feature_date"].max()
    test_start = last_labeled - pd.Timedelta(days=TEST_DAYS - 1)
    train_end = test_start - pd.Timedelta(days=GAP_DAYS + 1)

    df = df.copy()
    df["split"] = "live"
    df.loc[labeled & (df["feature_date"] <= train_end), "split"] = "train"
    df.loc[labeled & (df["feature_date"] > train_end) & (df["feature_date"] < test_start), "split"] = "purge"
    df.loc[labeled & (df["feature_date"] >= test_start), "split"] = "test"
    return df, train_end, test_start


def fit_model(train: pd.DataFrame, features: list[str]) -> HistGradientBoostingClassifier:
    """Train a gradient boosting with FIXED values (not tuned by looking at the test, which would get "spent").

    HistGradientBoostingClassifier accepts NULL directly: it learns what to do when a value is missing, without us
    having to invent it with a mean. Small trees and slow learning curb overfitting.
    """
    model = HistGradientBoostingClassifier(max_depth=4, learning_rate=0.05, max_iter=200, random_state=0)
    model.fit(train[features], train[LABEL].astype(int))
    return model


def evaluate(model: HistGradientBoostingClassifier, df: pd.DataFrame, features: list[str]) -> dict:
    """Measure with average precision (AP) on train and test, and compare it with chance.

    AP summarizes how well the model RANKS the rows: do the ones that will fail end up on top? It is used instead of
    accuracy because with ~7 % positives, always saying "it will not fail" would be right 93 % of the time and detect
    nothing. Chance gives an AP equal to the proportion of positives: that is the yardstick.
    """
    train = df[df["split"] == "train"]
    test = df[df["split"] == "test"]
    y_test = test[LABEL].astype(int)

    return {
        "average_precision": average_precision_score(y_test, model.predict_proba(test[features])[:, 1]),
        "train_average_precision": average_precision_score(
            train[LABEL].astype(int), model.predict_proba(train[features])[:, 1]
        ),
        "baseline_average_precision": y_test.mean(),   # what guessing at random would give
        "n_test_rows": len(test),
        "n_test_positives": int(y_test.sum()),
    }


def score(model: HistGradientBoostingClassifier, df: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    """The risk (probability between 0 and 1) of EVERY gold row, including the `live` ones that have no label yet."""
    predictions = df[KEYS + ["split"]].copy()
    predictions["risk_score"] = model.predict_proba(df[features])[:, 1]
    predictions["feature_date"] = predictions["feature_date"].dt.date   # DATE in DuckDB, not TIMESTAMP
    return predictions[KEYS + ["risk_score", "split"]]


def _write_atomically(path: Path, write) -> None:
    """Write to a .tmp and rename it: either the final file appears complete or it does not appear (same as in bronze)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    write(temp)
    temp.replace(path)


def save_model(model: HistGradientBoostingClassifier, features: list[str]) -> Path:
    """Save the model together with the list of features IN ORDER: whoever uses it (the API, step 7) needs to know
    which columns it was trained with, or might pass them in another order and get meaningless risks."""
    path = models_dir() / "model.joblib"
    _write_atomically(path, lambda tmp: joblib.dump({"model": model, "features": features}, tmp))
    return path


def save_metrics(metrics: dict) -> Path:
    path = models_dir() / "metrics.json"
    _write_atomically(path, lambda tmp: tmp.write_text(json.dumps(metrics, indent=2, ensure_ascii=False)))
    return path


def save_predictions(predictions: pd.DataFrame) -> None:
    """Replace `ml.predictions` in the warehouse. The WRITE connection is opened here, at the end, and closed right
    away: DuckDB only allows one writer, so we lock as little as possible."""
    con = duckdb.connect(str(warehouse_path()))
    try:
        con.execute("create schema if not exists ml")
        con.register("predictions_df", predictions)
        con.execute("create or replace table ml.predictions as select * from predictions_df")
    finally:
        con.close()


def run() -> None:
    df = read_gold()
    features = choose_features(df)
    df, train_end, test_start = split_in_time(df)

    print(f"Features ({len(features)}): {features}")
    print(f"train_end = {train_end.date()} | test_start = {test_start.date()}")
    print(df.groupby("split")[LABEL].agg(rows="size", positives="sum").to_string())

    model = fit_model(df[df["split"] == "train"], features)
    print(f"Model trained: {model.n_iter_} trees.")

    metrics = evaluate(model, df, features)
    chance = metrics["baseline_average_precision"]
    print(f"Train AP: {metrics['train_average_precision']:.3f}")
    print(f"Test AP:  {metrics['average_precision']:.3f}  (chance = {chance:.3f}, "
          f"{metrics['average_precision'] / chance:.1f}x better)")

    # The split dates are saved in the same file as the AP: that way you can check where each number comes from.
    metrics = {
        "train_end": str(train_end.date()),
        "test_start": str(test_start.date()),
        **{key: float(value) if key.endswith("precision") else int(value) for key, value in metrics.items()},
        "features": features,
    }
    model_path = save_model(model, features)
    metrics_path = save_metrics(metrics)
    predictions = score(model, df, features)
    save_predictions(predictions)
    print(f"Saved: {model_path.name}, {metrics_path.name} and ml.predictions ({len(predictions):,} rows).")


if __name__ == "__main__":
    run()
