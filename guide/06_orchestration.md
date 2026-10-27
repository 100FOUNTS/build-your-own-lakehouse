# Step 6 — Orchestration: everything runs by itself, in order and supervised

⏱ 2–3 h · Deliverable: `src/lakehouse/definitions.py` · Check: `make check-6`

## What you are going to build

A file that describes your pipeline as a **graph of data assets** in Dagster:

```
bronze_readings ──► silver_tables ──► gold_features ──► risk_predictions
```

and that allows, with one command or from a web interface, **materializing everything** end to end, in the right order.

## Why this step exists

So far you run four commands by hand (`make bronze`, `silver`, `gold`, `train`). In a job, nobody runs that by hand
at 6 in the morning. Someone (or something) has to: **run it in order**, **retry it if it fails**, **warn if it did not
finish**, **run it when new data arrives** and **show which table is fresh and which is not**. That "someone" is called
an orchestrator.

Think of the conductor of an orchestra: the musicians (your steps) already know how to play; the conductor decides when each one comes in and
notices if someone fell silent.

### And why Dagster?

There are two big families of orchestrators:
- **Task-oriented** (Airflow): "run A, then B, then C".
- **Asset-oriented** (Dagster): "this **table** depends on that one; if the upper one changed, the lower one is stale".

In data, what matters to you are the tables, not the tasks; that is why the asset approach fits well. Airflow is still
the most widespread in job offers, and the concepts (DAG, dependencies, retries, scheduling) are the same: what
you learn here transfers.

## What it is for in a real job

When something breaks at 3 a.m. the first question is *"what ran, what failed and what is stale?"*. An
orchestrator answers on one screen. It is also where you define how often the pipeline runs and what happens if it fails.

## Concepts you need

- **Asset**: a table/file/model that your pipeline produces, described by a Python function decorated with `@asset`.
- **Dependency**: `deps=[other_asset]` or a parameter with the same name. Dagster deduces the order of the graph.
- **Materialize**: run the asset to produce/update the data.
- **Definitions**: the `defs = Definitions(assets=[...])` object that Dagster looks for.
- **Asset check**: a verification attached to an asset ("are there no files in quarantine?"). If it fails, it shows in red.
- **Retry / schedule**: rules about when and how many times to run (you know them, you do not implement them here).

## The contract

**`src/lakehouse/definitions.py`** exposes `defs` (a `dagster.Definitions`) with:

- ≥ 4 chained assets (the longest dependency chain ≥ 4): bronze → silver → gold → predictions.
- Each asset **calls the code you already wrote** (`lakehouse.bronze.run()`, `dbt build`, `lakehouse.train.run()`),
  without duplicating logic.
- It **must work with the `LH_*` variables**: the check runs it in empty temporary folders.

The check runs, equivalent to:
```bash
dagster asset materialize -m lakehouse.definitions --select '*'
```
with 120 days of data in new folders, and verifies that `ml.predictions` and `metrics.json` exist.

## Your task

1. **Draw the graph first** in `notes/` or on paper: which assets, what depends on what, what each one produces.
2. **Write the assets.** For dbt inside an asset you have two reasonable options: run the dbt CLI in a subprocess, or
   use dbt-core's `dbtRunner`. (The `dagster-dbt` package turns each model into an asset: it is the next level.)
3. **Error handling**: if dbt fails, the asset must **fail** (raise an exception), not pass silently.
4. **Start the interface**: `make dagster` → http://localhost:3000. Look at the graph, materialize everything with the button and watch the logs.
5. **Test a failure**: break something on purpose in silver (a column name) and check that Dagster marks the asset red and
   **does not run** gold nor the model. Fix it.
6. **Optional challenge**: add an `@asset_check` (e.g. "there are no files in quarantine" or "the predictions are from today").

## How you will know you are done

```bash
make check-6     # takes ~20–40 s: runs the whole pipeline in temporary folders
```

## Comprehension questions

1. What is the difference between saying "run A, B, C" and saying "C depends on B which depends on A"? What does the second one allow you to do?
2. Your silver asset fails. What should happen to gold, to the model and to the API that keeps serving? What do you *not* want to happen?
3. What does it mean that `materialize` is idempotent? Is your whole pipeline? (Go back to step 2.)
4. What would you see in the UI if no new file arrived today? Should it be an error?
5. Why does the check run your pipeline in a temporary folder instead of on your data?

## Hints

<details><summary>Hint 1 — Skeleton</summary>

```python
from dagster import Definitions, asset

@asset
def bronze_readings() -> None:
    ...   # call your bronze.run()

@asset(deps=[bronze_readings])
def silver_tables() -> None:
    ...   # dbt build --select path:models/silver

defs = Definitions(assets=[bronze_readings, silver_tables, ...])
```
</details>

<details><summary>Hint 2 — dbt from Python</summary>

```python
from dbt.cli.main import dbtRunner
root = paths.ROOT / "dbt"
res = dbtRunner().invoke(["build", "--project-dir", str(root), "--profiles-dir", str(root), "--select", "path:models/silver"])
if not res.success: raise RuntimeError(res.exception)
```
</details>

<details><summary>Hint 3 — "It fails in the check but works in `make dagster`"</summary>

It is almost always a hard-coded path (in your code or in `profiles.yml`) instead of reading `LH_*`. The check changes the paths with
environment variables so it does not touch your data.
</details>

## Common traps

- **Copying the logic** into the assets instead of calling your modules (two versions of the truth).
- **Not declaring dependencies**: the assets run with no guaranteed order.
- **Swallowing dbt errors** (a "green" asset that actually loaded nothing).
- **Hard-coded paths** (this is the third time: it is the number one mistake of this exercise and of real life).

## In a real job

You would add **scheduling** (hourly or when a file arrives, with *sensors*), **alerts** (Slack/PagerDuty when it fails),
**partitions** (reprocess only a range of days), **resources** (the database connection is configured once and injected) and
deployment (Dagster+ or Kubernetes). All of it rests on the graph you just defined.

→ Next: [`07_api.md`](07_api.md)
