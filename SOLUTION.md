# Reference solution (one possible solution, not the only one)

> **Spoiler warning.** This branch contains a complete solution of the exercise. If you have not finished the steps
> yourself, go back to `main` and build it first: the learning is in the building.
>
> There is no single correct design. The checks verify results and properties, so yours can differ from this one and be
> just as good. Compare **decisions**, not code (see `guide/08_next.md`).

## What is in this branch

| Path | What it is | Step |
|---|---|---|
| `src/lakehouse/bronze.py` | Idempotent ingestion: one Parquet per raw file, atomic writes, quarantine with a reason | 2 |
| `dbt/` | dbt project: `silver` (3 models + tests) and `gold` (`asset_daily_features`) | 3, 4 |
| `tests/test_no_leakage.py` | Temporal invariance test: delete the future, rebuild gold, compare the features | 4 |
| `src/lakehouse/train.py` | Temporal split with purge, fixed-hyperparameter gradient boosting, AP vs chance | 5 |
| `src/lakehouse/definitions.py` | Dagster graph of four assets + a quarantine asset check | 6 |
| `src/lakehouse/api.py` | FastAPI: `/health`, `/assets`, `/assets/{id}/risk` (404 / 503 handled) | 7 |
| `notes/01_findings.md`, `notes/02_bronze_decisions.md` | Reference findings and bronze decisions (the checks of steps 1 and 2 read them; notes 03-07 stay as templates) | 1, 2 |
| `Dockerfile`, `compose.yaml`, `.dockerignore` | Pipeline and API in one image, data in a volume | 8 |
| `ci/github-actions.yml` | CI workflow (copy to `.github/workflows/ci.yml` to enable it) | 8 |

Run it: `make setup && make run && make check` (the 49 checks of steps 0-7 pass), then `uv run pytest tests`.
`make bonus`: the Dagster asset check and the API lock challenge pass; the step 5 business-metrics challenge (threshold, event recall, false alerts) is intentionally left for you.

## Design decisions worth comparing with yours

**Bronze**
- Idempotency comes from a deterministic destination: the same raw file always maps to the same Parquet path, and a
  file whose Parquet exists is skipped. "Stored" and "marked as loaded" cannot get out of sync.
  *Limit:* it does not notice that an already-loaded file was later corrected by the provider.
- Everything is read as text, by column name; no cleaning. The truncated file goes whole to quarantine with a
  `.reason.txt`, and the other files are still loaded. Only `duckdb.Error` is caught, so a programming error is not disguised as a "broken file".

**Silver**
- One CTE per problem: identifiers and time, sentinels and quality, units, deduplication, spikes.
- Order matters: sentinels become NULL **before** converting units (otherwise `-9999 °F` turns into another number), and
  deduplication happens **after** converting to a UTC instant and **after** dropping BAD readings.
- Spikes are *flagged* (`is_outlier`), never deleted. A spike is a reading far from the median of its neighbors **and**
  from both adjacent readings; the isolation condition keeps real regime changes (a pump stopping) from being flagged.

**Gold**
- One row per pump and day; every aggregate only looks at instants with the pump running.
- All windows look backwards; the own baseline (28 days) excludes the current day.
- The label is `NULL` (not 0) in the last 7 days: right censoring. Those rows are kept and scored as "today".
- Absolute and *relative* deltas against the baseline. The relative ones help pumps that work at low pressure levels.

**Model**
- Chronological split: train · 7-day purge · test (last 36 labeled days) · live. Fixed hyperparameters, never tuned on the test.
- On this data: test AP ≈ 0.90 against ≈ 0.07 for chance (about 13× better). Only about 11 independent failures fall in the
  test window, so treat small differences between runs as noise.

**Orchestration and API**
- dbt runs in a subprocess so DuckDB's single writer is released between assets; failures stop the downstream assets.
- The API opens DuckDB read-only **per request**. DuckDB allows one writer *or* several readers across processes, so while the
  pipeline writes the API answers `503` with `Retry-After` instead of a `500`.

## Known limits (good starting points for the improvement challenges)

- Pump `PLT01-P113` (a low-pressure-level pump) is still hard to detect, and seal failures are detected worse than bearing failures.
- "Latest risk" can mislead right after a failure: the model scores the days *before* a failure, not the day it happens.
- The API does not say when its data is stale (`as_of` is the only hint); there is no freshness check yet.
- No schedule or sensor in Dagster, no alerting, no authentication.
