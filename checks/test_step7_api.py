"""Step 7 — API: does it deliver the latest risk per pump, with clear errors?"""

from __future__ import annotations

import duckdb
import pytest
from conftest import DATA, connect, ok


@pytest.fixture()
def client():
    err, app = None, None
    try:
        from lakehouse.api import app
    except Exception as exc:  # noqa: BLE001
        err = exc
    ok(err is None, f"I cannot import `app` from src/lakehouse/api.py yet ({err!r}).\n`app = FastAPI(...)` must exist (see guide/07_api.md).")
    from fastapi.testclient import TestClient

    connect(hint="Run `make run` first (you need ml.predictions).").close()
    return TestClient(app)


def _latest():
    con = connect()
    try:
        return {a: (str(d), s) for a, d, s in con.execute(
            "select asset_id, cast(feature_date as date), risk_score from ml.predictions qualify row_number() over (partition by asset_id order by feature_date desc) = 1"
        ).fetchall()}
    finally:
        con.close()


def test_health(client):
    r = client.get("/health")
    ok(r.status_code == 200, f"GET /health returned {r.status_code}; 200 is expected (load balancers use it to know whether you are alive).")


def test_list_sorted_by_risk(client):
    r = client.get("/assets")
    ok(r.status_code == 200, f"GET /assets returned {r.status_code}")
    data = r.json()
    ok(len(data) == 20, f"GET /assets returned {len(data)} pumps and there are 20.")
    ok(all({"asset_id", "risk_score", "as_of"} <= set(x) for x in data), "Each element needs asset_id, risk_score and as_of.")
    scores = [x["risk_score"] for x in data]
    ok(scores == sorted(scores, reverse=True), "The list must come sorted from highest to lowest risk: it is the first thing whoever operates the plant wants to see.")


def test_detail_matches_what_the_model_predicted(client):
    latest = _latest()
    for asset, (d, s) in list(latest.items())[:5]:
        r = client.get(f"/assets/{asset}/risk")
        ok(r.status_code == 200, f"GET /assets/{asset}/risk returned {r.status_code}")
        j = r.json()
        ok(j["asset_id"] == asset and abs(j["risk_score"] - s) < 1e-6 and str(j["as_of"])[:10] == d,
           f"{asset}: the API says {j} but ml.predictions has ({d}, {s}). It must return the prediction of the MOST RECENT date.")


def test_unknown_asset_gives_404(client):
    r = client.get("/assets/DOES-NOT-EXIST/risk")
    ok(r.status_code == 404, f"A non-existent asset returned {r.status_code}; it must be 404 with a clear message (not a 500).")


@pytest.mark.bonus
def test_bonus_does_not_leave_the_database_locked(client):
    client.get("/assets")
    try:
        con = duckdb.connect(str(DATA / "warehouse.duckdb"))  # read/write
        con.close()
    except duckdb.Error as exc:
        pytest.fail(f"\n\n  Your API left the database open ({exc}). Open the connection per request and close it (or use read_only=True): otherwise dbt cannot write while the API runs.\n", pytrace=False)
