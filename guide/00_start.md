# Step 0 — Getting started: the mental map

⏱ 30 min · No code yet. Read all of it: this is the idea that holds up the seven steps that follow.

## 1. What a "lakehouse" is (and why you are going to build one)

Imagine a restaurant kitchen:

| Kitchen | Data | Layer |
|---|---|---|
| The ingredients **exactly as they arrive from the supplier**, in their boxes, untouched | The historian files, faithfully copied | **Bronze** |
| Ingredients **washed, peeled and cut**; the bad ones discarded | Clean, deduplicated data in standard units | **Silver** |
| The **finished dish** ready to serve | A table with what the model needs: one row per pump and day | **Gold** |
| The customer orders the dish at the window | An API that delivers the risk | **Serving** |

**Why three layers and not a single transformation?** For a very practical reason: **mistakes are discovered late.**
In a month someone will say *"the sensor was badly calibrated those days"* or *"the cleaning rule was wrong"*.
If you kept the raw data faithfully (bronze), you clean again and that is it. If you cleaned by destroying the original,
that data is lost forever. Bronze is your **insurance policy**; silver and gold can be recomputed, so you can
make mistakes in them without fear.

"Lakehouse" is the fashionable name for this idea when the data lives in cheap files (Parquet) with database tools on top
(SQL, tests, catalog). In a job the same structure is called *medallion* and it is used by Databricks, Snowflake,
Microsoft Fabric and almost any modern data team. What you learn here transfers.

## 2. The six ideas you will use in every step

You will meet each one again, with its why, in the step where it matters:

1. **Idempotency** — *running something twice gives the same result as running it once.* In production processes are
   retried (the network dropped, the server restarted). If repeating duplicates data, a small outage becomes a fire.
2. **Grain** — *what a row represents.* "A reading of one sensor at one instant", "a pump on a day". Most
   data errors are grain confusions. If you cannot say the grain of a table, you do not understand it.
3. **Contract** — *what a table promises.* Columns, types, units, what happens with nulls. Tests (dbt tests, pytest)
   are the contract written as code: what is not tested is an opinion.
4. **Lineage / traceability** — *where this number came from.* That is why bronze records which file and when each row arrived.
5. **No temporal leakage** — *when predicting a day, you can only use what you knew up to that day.* It is the most expensive
   mistake in applied machine learning: a model that "sees the future" shines in the lab and fails in production.
6. **Configuration outside the code** — *paths and secrets are not hand-written in scripts.* The same code runs
   on your laptop, in CI and in production; the only thing that changes is environment variables. (That is why `paths.py` exists.)

## 3. The tools and why these

| Tool | What it does here | Why this one and not another |
|---|---|---|
| **Python + pandas** | Ingestion, model, API | pandas is what job offers ask for most. It is the common language of data |
| **Parquet** | Bronze format | Columnar, compressed and typed: much smaller and faster than CSV, and every tool understands it |
| **DuckDB** | The silver and gold database | An analytical database in *one file*, no server. Full SQL and very fast. Ideal for learning and for real medium-size analysis |
| **dbt** | SQL transformations with tests and documentation | It is the industry standard for the transformation layer. A model = a versioned, tested `SELECT` |
| **scikit-learn** | The model | Simple, solid and enough. The challenge here is not the algorithm but evaluating it well |
| **Dagster** | Orchestration | It thinks in *data assets* (tables), not loose tasks: it fits a lakehouse. (Airflow is the other big name) |
| **FastAPI** | The API | Modern, fast to write, with automatic documentation |
| **uv** | Environments and dependencies | Fast and reproducible; a single command installs everything |

You do not need Docker for this exercise. Everything runs on your laptop.

## 4. Prepare the environment

```bash
make setup        # uv sync: installs Python 3.12 and the libraries
make check-0      # checks that everything is ready
```

If you see `No module named …` after installing on macOS: `make fix-venv` (it is a "hidden" flag that macOS puts on the environment).

To see all the commands: `make help`.

## 5. How what you will write is organized

| Step | File(s) you create |
|---|---|
| 1 | `notes/01_findings.md` (and, if you want, a notebook in `notebooks/`) |
| 2 | `src/lakehouse/bronze.py` and `notes/02_bronze_decisions.md` |
| 3 | `dbt/dbt_project.yml`, `dbt/profiles.yml`, `dbt/models/silver/*.sql` + `*.yml` |
| 4 | `dbt/models/gold/*.sql` + `*.yml`, `tests/test_no_leakage.py` |
| 5 | `src/lakehouse/train.py` |
| 6 | `src/lakehouse/definitions.py` |
| 7 | `src/lakehouse/api.py` |

`src/lakehouse/paths.py` is already done: it gives you the paths through environment variables (`LH_RAW_DIR`, `LH_BRONZE_DIR`,
`LH_WAREHOUSE`…). Read it, it is short and explains why.

## 6. How to use Claude Code as a mentor

In this folder, Claude Code is configured **not to write your solution** but to teach you:

| Command | What it does |
|---|---|
| `/step N` | Introduces the step with an analogy and asks you questions to see what you know |
| `/hint N` | Gives you the **next** hint (from less to more help) |
| `/why <topic>` | Explains a concept with an analogy, a real example and a question |
| `/review N` | Runs the check, reads your code and gives you a review like a senior teammate would |

And you can ask it anything: *"explain what a window function is"*, *"why does this error happen?"*.
If one day you want it to write something for you, tell it ("do it for me"); but the idea is that you will not need it.

## 7. Two habits that make the difference

- **Explain it in your own words** in `notes/`. If you cannot write it, you have not understood it; go back to the guide.
- **Always look at the data.** After each step run a `SELECT … LIMIT 20` and eyeball the results. The checks catch
  many things, but your eyes catch the ones nobody thought to check.

## When you are ready

→ [`01_explore.md`](01_explore.md)
