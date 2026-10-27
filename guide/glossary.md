# Glossary

Words you will see in the guide, explained without jargon. If one is missing, ask your mentor with `/why <word>`.

**API** — A service that other programs send requests to (over the internet or a local network) and that answers with data.
**Artifact** — A file that a process produces and that is kept for reuse (e.g. the trained model).
**Asset** — In Dagster, a piece of data that your pipeline produces (a table, a file, a model) and that is described in code.
**Atomic** — Happens completely or does not happen; it is never left half-way. Renaming a file is atomic.
**Average Precision (AP)** — Metric that tells how well a model *ranks*: do the pumps that will fail end up on top of the list? It is compared with chance (the proportion of positives).
**Bronze / Silver / Gold** — The three layers of the lakehouse: faithful raw / clean and trustworthy / ready to use.
**Incremental load** — Processing only what is new instead of everything each time.
**Censoring (right)** — Not being able to know the outcome yet because the future has not happened (the last 7 days have no label).
**Sentinel** — A "special" value that means "no data" (like -9999). It is not a measurement.
**CTE** — `WITH name AS (...)`: splitting a SQL query into named steps.
**Columnar** — Format that stores data by column (not by row); it lets you read only what you need. Parquet is columnar.
**Contract (data)** — What a table promises: columns, types, units, keys, what happens with nulls.
**Quarantine** — Place where what could not be processed is set aside, with its reason, to be reviewed later. Neither thrown away nor ignored.
**DAG** — Directed acyclic graph: "A before B before C". It is how a pipeline is described.
**dbt** — Tool that organizes SQL transformations as versioned models with tests and documentation.
**DuckDB** — Analytical database that lives in a file, with no server.
**Endpoint** — A URL + method of an API (`GET /assets`).
**Label** — The answer you want to predict (here: will it fail within 7 days?).
**Feature** — A number that describes the situation and that the model uses to predict.
**Data leakage** — When a feature uses data that would not exist at the time of predicting. It makes the model look great in tests and fail in production.
**Grain** — What a row of a table represents. If you cannot say it, you do not understand the table.
**Historian** — Industrial system that stores sensor readings over time.
**Idempotency** — Running something N times leaves the same result as running it once. It is the property that saves retries.
**JSON** — Text format for exchanging structured data.
**Lineage** — Where a piece of data comes from and which transformations it went through.
**Materialize** — Run an asset to produce its data.
**Medallion** — Name of the bronze/silver/gold pattern.
**Rolling median** — The median of the N readings around each point; used to detect absurd readings compared with their neighbors.
**Orchestrator** — Software that runs the pipeline steps in order, retries them, warns about failures and shows the state.
**Outlier** — Value far from what is expected. Here: spurious spikes. They are *flagged*, not deleted.
**Parquet** — Columnar, compressed, typed file format. The lakehouse standard.
**Pipeline** — The chain of steps that takes data from the source to the result.
**Purge** — The gap of days between training and test so that the labels do not overlap.
**Quality** — Label that the historian puts on each reading: GOOD, BAD or UNCERTAIN.
**Rolling window** — A computation over the previous N days or rows.
**Overfitting** — The model memorizes the training set and fails on new data.
**Temporal split** — Dividing the data by date: train with the past and test with the future.
**Tag** — Identifier of a measurement point (PLT01.P101.VIB_MM_S).
**Test (dbt)** — An assertion about the data that is checked automatically.
**UTC** — Universal reference time. Everything is converted to UTC before comparing or deduplicating.
**Window function** — In SQL, a computation that looks at the surrounding rows without collapsing them (`OVER (...)`).
