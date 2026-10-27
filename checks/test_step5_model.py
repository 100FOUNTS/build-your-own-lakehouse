"""Step 5 — model: honest evaluation (by time, with a gap), better than chance and predictions saved?"""

from __future__ import annotations

import json

import pandas as pd
import pytest
from conftest import DATA, columns, connect, find_table, ok
from sklearn.metrics import average_precision_score

HINT = "Run `make train`. It must write data/models/metrics.json and the table ml.predictions."
METRIC_KEYS = ["train_end", "test_start", "average_precision", "baseline_average_precision", "n_test_rows", "n_test_positives"]


@pytest.fixture()
def metrics():
    f = DATA / "models" / "metrics.json"
    ok(f.exists(), f"data/models/metrics.json does not exist. {HINT}")
    m = json.loads(f.read_text())
    missing = [k for k in METRIC_KEYS if k not in m]
    ok(not missing, f"metrics.json is missing keys: {missing} (see the contract in guide/05_model.md).")
    return m


@pytest.fixture()
def pred():
    con = connect(hint=HINT)
    try:
        find_table(con, "predictions", "ml", HINT)
        cols = columns(con, "ml.predictions")
        missing = {"asset_id", "feature_date", "risk_score", "split"} - set(cols)
        ok(not missing, f"ml.predictions needs the columns {sorted(missing)} (contract in guide/05_model.md).")
        df = con.execute("select * from ml.predictions").df()
        gold = find_table(con, "asset_daily_features", "gold", "Gold is missing.")
        lab = con.execute(f"select asset_id, cast(feature_date as date) as feature_date, label_failure_7d from {gold}").df()
    finally:
        con.close()
    df["feature_date"] = pd.to_datetime(df["feature_date"])
    lab["feature_date"] = pd.to_datetime(lab["feature_date"])
    return df[["asset_id", "feature_date", "risk_score", "split"]].merge(lab, on=["asset_id", "feature_date"], how="left")


def test_model_saved():
    ok(any((DATA / "models").glob("model.*")), "Save the trained model in data/models/model.<ext> (joblib, pickle…): without an artifact there is no way to reproduce or serve anything.")


def test_temporal_split_with_gap(metrics, pred):
    train_end, test_start = pd.Timestamp(metrics["train_end"]), pd.Timestamp(metrics["test_start"])
    gap = (test_start - train_end).days
    ok(gap >= 7, f"Between the end of training ({train_end.date()}) and the start of test ({test_start.date()}) there are {gap} days; ≥ 7 are needed.\n"
       "The label of a training row looks 7 days into the future: without a gap you would train with answers that fall inside the test period.")
    tr, te = pred[pred["split"] == "train"], pred[pred["split"] == "test"]
    ok(len(tr) > 0 and len(te) > 0, "ml.predictions must mark rows with split = 'train' and split = 'test'.")
    ok(tr["feature_date"].max() <= train_end, "There are 'train' rows after train_end: your split does not match what you report.")
    ok(te["feature_date"].min() >= test_start, "There are 'test' rows before test_start: your split does not match what you report.")
    ok(tr["feature_date"].max() < te["feature_date"].min(), "ALL of training must be earlier than ALL of test (never a random split on time series).")


def test_enough_test_data(metrics):
    ok(metrics["n_test_rows"] >= 400 and metrics["n_test_positives"] >= 25, f"Your test has {metrics['n_test_rows']} rows and {metrics['n_test_positives']} positives: too little to trust a metric. Reserve ≈ 6 weeks.")


def test_better_than_chance_and_honest_metrics(metrics, pred):
    te = pred[(pred["split"] == "test") & pred["label_failure_7d"].notna()]
    ap = average_precision_score(te["label_failure_7d"].astype(int), te["risk_score"])
    base = te["label_failure_7d"].mean()
    ok(abs(ap - metrics["average_precision"]) < 0.02, f"In metrics.json you report AP={metrics['average_precision']:.3f}, but recomputed from ml.predictions it is {ap:.3f}. Metrics are computed on what you actually saved.")
    ok(ap >= max(0.30, 3 * base),
       f"AP on test = {ap:.2f}; chance would give ≈ {base:.2f} (the proportion of positive days). At least {max(0.30, 3 * base):.2f} is expected.\n"
       "Check your features: do they distinguish a degrading pump from a healthy one? Do you normalize for stopped/running?")
    ok(ap < 0.995, "Almost perfect AP: be suspicious. With real data that is usually leakage, not genius.")


def test_todays_scoring(pred):
    ok(pred["risk_score"].between(0, 1).all(), "risk_score must be in [0, 1] (probability).")
    latest = pred["feature_date"].max()
    per_asset = pred.groupby("asset_id")["feature_date"].max()
    ok(len(per_asset) == 20 and (per_asset >= latest - pd.Timedelta(days=1)).all(),
       "There must be a recent prediction for each of the 20 pumps, also for the latest days WITHOUT a label (split='live'): it is the 'today' risk your API will serve.")
    ok((pred["split"] == "live").any(), "Mark with split='live' the recent rows that have no label (the ones you score but cannot evaluate).")


@pytest.mark.bonus
def test_bonus_business_metrics(metrics):
    keys = ["threshold", "event_recall", "false_alerts_per_100_healthy_days"]
    missing = [k for k in keys if k not in metrics]
    ok(not missing, f"CHALLENGE: AP means nothing to the maintenance manager. Also report {keys}: what fraction of the real failures did you warn about in time, and how many false alerts are there per 100 healthy days?")
    ok(0 <= metrics["event_recall"] <= 1, "event_recall must be between 0 and 1")
