"""API: deliver the failure risk of each pump.

What is here: the app and /health, opening DuckDB read-only, the latest prediction of each pump, and the endpoints
/assets and /assets/{id}/risk (with a 404 for an unknown pump).
The pipeline (steps 2-6) WRITES; the API only READS: whoever queries it does not need to know about DuckDB, dbt or scikit-learn.
Start it with `make api` (http://localhost:8000) and the interactive documentation comes out by itself at /docs.
"""

from contextlib import contextmanager

import duckdb
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from lakehouse.paths import warehouse_path

app = FastAPI(
    title="Pump failure risk",
    description="Probability that each pump fails within the next 7 days, according to the pipeline's model.",
)


# From which risk an alert is raised. 0.5 is the threshold the model was evaluated with (step 5): on the test period it
# detected 9 of 11 failures with it. It is a BUSINESS decision (how much an extra inspection costs compared with a missed
# failure) and maintenance may want another one: that is why it is a named constant and not a number hidden in the code.
ALERT_THRESHOLD = 0.5


class Risk(BaseModel):
    """The shape of the response. FastAPI validates it, documents it in /docs and avoids returning fields by accident."""

    asset_id: str
    as_of: str          # (UTC) date of that pump's most recent prediction
    risk_score: float   # probability of failure within the next 7 days (0 to 1)
    alert: bool         # risk_score >= ALERT_THRESHOLD


@app.get("/health")
def health() -> dict:
    """Is the service alive? It does not touch the database on purpose: it answers even if the pipeline is running.
    Whoever deploys the API (a load balancer, Kubernetes) queries it every few seconds to know whether to restart it."""
    return {"status": "ok"}


@contextmanager
def read_only_connection():
    """Open the warehouse READ-ONLY and close it by itself at the end (used with `with`).

    Read-only: the API never writes. Several reads at once are allowed, but DuckDB does not allow a reader while another
    PROCESS is writing (see the 503 below). It is opened and closed on EVERY request: for this data size it is the
    simplest and safest, and it does not leave the database locked if something fails halfway (the `finally` always closes).
    """
    con = duckdb.connect(str(warehouse_path()), read_only=True)
    try:
        yield con
    finally:
        con.close()


# "The latest prediction of each pump": row_number() numbers the rows of each pump from the most recent (1) to the oldest,
# and we keep number 1. It is the same technique silver used to keep one copy of each reading.
# The most recent date OF EACH PUMP is chosen (not the global maximum date): that way dates are never mixed between pumps.
_LATEST_PREDICTION = """
    select asset_id, cast(feature_date as varchar) as as_of, risk_score
    from (
        select *, row_number() over (partition by asset_id order by feature_date desc) as n
        from ml.predictions
    )
    where n = 1
"""


def latest_predictions(con: duckdb.DuckDBPyConnection, asset_id: str | None = None) -> list[dict]:
    """Latest prediction of each pump, from highest to lowest risk; or only that of `asset_id` if given.

    The `asset_id` comes from the internet, that is, from someone we do not control: it is passed as a PARAMETER (`?`) and
    never pasted into the SQL text, so it cannot sneak in code (SQL injection).
    """
    sql = f"select * from ({_LATEST_PREDICTION})"
    parameters: list = []
    if asset_id is not None:
        sql += " where asset_id = ?"
        parameters.append(asset_id)
    sql += " order by risk_score desc"
    columns = ["asset_id", "as_of", "risk_score"]
    return [dict(zip(columns, row, strict=True)) for row in con.execute(sql, parameters).fetchall()]


def _read_predictions(asset_id: str | None = None) -> list[Risk]:
    """Query the latest predictions and turn them into `Risk`."""
    try:
        with read_only_connection() as con:
            rows = latest_predictions(con, asset_id)
    except duckdb.CatalogException:
        # The table does not exist: the pipeline has not run yet. It is OUR problem, not the caller's -> 503
        # ("service unavailable"), with a generic message: DuckDB's error is not returned, as it could reveal
        # internal paths or names.
        raise HTTPException(status_code=503, detail="There are no predictions yet: the pipeline has not run.") from None
    except duckdb.IOException:
        # DuckDB across processes: ONE writer, or SEVERAL readers, never both. If the pipeline is writing right now
        # (dbt or the model, a few seconds), the database cannot be opened even read-only. It is not the caller's error
        # nor a failure on our side: it is temporary -> 503 and "Retry-After" so the client retries.
        raise HTTPException(
            status_code=503,
            detail="Predictions are being updated. Retry in a few seconds.",
            headers={"Retry-After": "5"},
        ) from None
    return [Risk(**row, alert=row["risk_score"] >= ALERT_THRESHOLD) for row in rows]


@app.get("/assets", response_model=list[Risk])
def list_pumps() -> list[Risk]:
    """The pumps with their latest risk, from highest to lowest risk (the first thing maintenance would want to see)."""
    return _read_predictions()


@app.get("/assets/{asset_id}/risk", response_model=Risk)
def pump_risk(asset_id: str) -> Risk:
    """The latest risk of one pump. If it does not exist: 404 (the error is the caller's), never a 500."""
    found = _read_predictions(asset_id)
    if not found:
        raise HTTPException(status_code=404, detail=f"Pump '{asset_id}' does not exist.")
    return found[0]
