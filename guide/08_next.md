# Step 8 — After finishing

If you got here with the seven checks green, **you built an end-to-end data pipeline from scratch**. This is
what you can now say in an interview: idempotent ingestion, medallion layers, dbt with tests, prevention of temporal leakage,
honest evaluation of a model, asset-based orchestration and a service API.

## 1. Compare with the reference (now yes!)

Check out the `solution` branch of this repository (`git fetch origin solution && git diff main..origin/solution`, or
browse it on GitHub) and compare its design with yours. Do not look for "who did it better", look for
**differences of decision**:

- Does the reference detect what was already loaded the same way you do? What limit does its design have?
- Who flags more spikes, and with what rule? What trade-off is there between catching spikes and over-flagging?
- Which features did each one choose? Which contributes more? (Run an experiment: remove a feature and measure the AP.)

Also look at the data generator (`make_data.py` on that branch) and see **which problems were hidden**. Compare them with your
step 1 findings: which ones did you find, which not, and why? That question —*what am I not looking at?*— is the one
that will make you grow the most.

## 2. Improvement tasks (in order of value)

| Challenge | What you learn |
|---|---|
| **Frozen sensor**: detect when a sensor stops varying (`is_stuck`) and make silver flag it | Data quality beyond ranges |
| **Business metrics** (`make bonus`): recall per event and false alerts per 100 healthy days; threshold by cost | Translating a model into a decision |
| **Normalize by pump model** (use `assets.model`) and measure whether it improves | Features with context |
| **Relative deltas**: change versus the own baseline as a proportion, not in absolute units; does it help pumps that work at low pressure? | Feature engineering with domain sense |
| **Cavitation**: which failure mode is detected worst and why? which feature would help it? | Error analysis |
| **Continuous arrival**: `make arrival` and run the full pipeline; what happens with the features of the last days? | Incremental loads end to end |
| **Change the horizon** to 14 days and to 3 days: what changes in the usefulness for maintenance? | Thinking like the business |
| **Dagster**: daily schedule and a sensor that fires when a new file arrives | Real orchestration |

## 3. Taking it to production (what is missing for this to be "for real")

1. **Docker**: package pipeline + API in one image. `docker compose` to bring up dependencies.
2. **CI**: GitHub Actions that runs `ruff`, your tests and `dbt build` on every pull request.
3. **Secrets and configuration**: environment variables, never passwords in the repo.
4. **Observability**: metrics and traces (OpenTelemetry + Grafana), alerts that make sense.
5. **A real warehouse**: Postgres/pgvector, Snowflake or Databricks instead of a DuckDB file.
6. **Streaming**: readings arriving through Kafka/Redpanda instead of daily files.

The `solution` branch includes a worked example of items 1 and 2 (Dockerfile, compose and a CI workflow) if you want to compare.

## 4. How to tell the story (portfolio / interview)

A good description for your CV or GitHub:

> *Predictive-maintenance pipeline over industrial historian data: idempotent ingestion to Parquet,
> transformations with dbt (DuckDB) and tests, features free of temporal leakage verified with an invariance test,
> model evaluated with a temporal split with purge, orchestration with Dagster and API with FastAPI.*

And these three stories, which are what is really asked:
1. "Tell me about a data quality problem you found and how you solved it."
2. "How did you avoid information leakage in your model?"
3. "What happens if your job is retried?"

Your notes in `notes/` are the raw material to answer them with real examples.
