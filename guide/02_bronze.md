# Step 2 — Bronze: faithfully store what arrives

⏱ 3–4 h · Deliverable: `src/lakehouse/bronze.py` + `notes/02_bronze_decisions.md` · Check: `make check-2`

## What you are going to build

A program (`python -m lakehouse.bronze`) that reads the raw historian files and stores them in **Parquet**, so that:

- it does not lose or change a single row (bronze is a **faithful** copy),
- if you run it twice it **duplicates nothing**,
- if new files arrive, it **loads only the new ones**,
- if a file is broken, it **does not crash** nor silently ignores it.

## Why this step exists

Think of a scientist's lab notebook: you write **what was observed**, with a date, without erasing crossed-out lines.
Conclusions are drawn separately. Bronze is that notebook.

Three concrete reasons not to "clean it all at once":

1. **Reprocessing.** You will discover mistakes in your cleaning (you will). With the raw data intact, you fix the rule and
   recompute. Without it, that data is lost.
2. **Audit.** When Marta asks *"where does this 7.3 come from?"*, you must be able to get back to the original file and row.
3. **Decoupling.** The data provider and the data user are different people. Bronze is the border: what comes from outside enters
   as it is; what is inside can change its mind without asking anyone to re-export anything.

And a technical reason: **compressed CSVs are slow and untyped**. Parquet is columnar (it reads only the columns you
need), compressed, and stores types. Going from CSV to Parquet usually gives tables 5–10× smaller and much
faster queries, and every tool reads it (DuckDB, Spark, Databricks, Snowflake, pandas).

## What it is for in a real job

Ingestion is where most incidents happen: the provider changes a format, a duplicate file arrives,
a job is retried three times. Serious data engineers design ingestion thinking **all that is going to happen**.
The keyword is **idempotency** — and it is among the first questions of any data interview.

## Concepts you need

- **Idempotency**: running the operation N times leaves the system the same as running it once. Everyday example: the
  elevator button (pressing it 5 times does not call 5 elevators). Opposite example: "add 100 to the balance".
- **Incremental load**: process only what is new, not everything each time. It needs some **memory** mechanism (what did I already load?).
- **Atomic write**: either the file ends up complete, or it does not exist. If your process dies halfway, a half-written Parquet
  would be worse than none. (Classic trick: write to a temporary name and rename at the end; renaming is atomic.)
- **Quarantine (dead-letter)**: where data that cannot be processed goes. It is not thrown away (you would lose the
  evidence) and not ignored (nobody would find out): it is set aside and someone is told.
- **Ingestion metadata**: columns you add for traceability (`_source_file`, `_ingested_at`).
- **Parquet**: columnar file format with schema and compression.

## The contract (what the checks expect)

| What | Where |
|---|---|
| Program | `src/lakehouse/bronze.py`, executable with `python -m lakehouse.bronze` (or `make bronze`), with exit code 0 even if there are bad files |
| Readings | Parquet under `<LH_BRONZE_DIR>/readings/` (the subfolder structure is yours to decide) |
| Readings columns | the 5 original ones (`timestamp, tag, value, unit, quality`) **plus** `_source_file` and `_ingested_at` |
| References | Parquet under `<LH_BRONZE_DIR>/assets/` and `<LH_BRONZE_DIR>/work_orders/` |
| Quarantine | files or records under `<LH_QUARANTINE_DIR>/` that identify the defective file and the reason |
| Paths | always through `lakehouse.paths` (`raw_dir()`, `bronze_dir()`, `quarantine_dir()`), never hand-written |
| Fidelity | number of rows in bronze = number of rows of the readable raw data. **Nothing cleaned** (no duplicates removed, no BAD readings dropped) |

## Your task

1. **Design before writing.** Answer mentally (and later in `notes/02_bronze_decisions.md`): how will your program know that
   a file was already loaded? What uniquely identifies a file?
2. **Write `bronze.py`** with a `run()` function and the `if __name__ == "__main__": run()` block.
3. **Read by column name, not by position**, and **as text**: bronze does not interpret, it preserves.
4. **Add `_source_file` and `_ingested_at`** to every row.
5. **Write atomically** and in a way that repeating does not duplicate.
6. **Handle broken files**: they must not bring the run down, they must be set aside with their reason, and the warning must be visible in
   the terminal.
7. **The reference tables** (`assets`, `work_orders`) also go through bronze. Think: they are small "snapshots" of the
   current state; what does it mean for their load to be idempotent?
8. **Test it with the arrival of new data:**
   ```bash
   make bronze          # first load
   make bronze          # second: how many files did it load? (should be 0)
   make arrival         # a new file arrives in data/raw
   make bronze          # does it load exactly 1?
   ```
9. **Look at what you stored**: `duckdb.sql("select count(*) from read_parquet('data/bronze/readings/**/*.parquet')")`
   and compare it with the rows of the raw data.
10. **Answer** `notes/02_bronze_decisions.md`.

## How you will know you are done

```bash
make check-2
```

This check is demanding (it takes from a few seconds to a minute, depending on your code): besides looking at your real bronze, it **copies part of the raw data to a temporary folder**,
runs your program there, repeats it, adds new files and runs it again, counting rows in every round.

## Comprehension questions

1. Why would `drop_duplicates()` in bronze be a mistake even if it "improves" the data?
2. If your process dies right after processing file 80 of 149, what happens when you restart it? And if it dies *while writing* file 80?
3. The provider re-exports an already loaded file with a correction. Does your design detect it? Should it? (There is no single answer: justify.)
4. What do you gain and what do you lose by storing `value` as text in bronze?
5. How would Marta (non-technical) know that there was a file in quarantine today?

## Hints

<details><summary>Hint 1 — How to think about idempotency</summary>

There are two common strategies: (a) **keep a record** of what was already loaded and skip it, or (b) make the
**destination deterministic** (same source → same destination name) so that repeating *overwrites the same thing* instead of adding.
Each has advantages and limits; choose one and you will be able to defend why.
</details>

<details><summary>Hint 2 — Read without pandas "helping"</summary>

`pd.read_csv(path, dtype=str, keep_default_na=False)` reads everything as text and does not turn empties into `NaN`. To detect an
unreadable file, wrap the read in `try/except` and catch the *specific* exception you see (try it by hand first).
</details>

<details><summary>Hint 3 — Atomic write</summary>

Write to `destination.tmp` and when finished `Path.replace(destination)`. If the process dies before the `replace`, there is no half-written file
with the final name (at most a `.tmp` that you ignore or clean).
</details>

<details><summary>Hint 4 — Suggested structure</summary>

`bronze/readings/date=2026-05-01/readings_20260501.parquet` — mirroring the source path in the destination makes it trivial to know what
was already loaded, and keeps the partitioning by file date.
</details>

## Common traps

- **Reading by column position**: if a file carries another order, you mix `tag` with `timestamp` with no error at all.
- **Letting the type be inferred**: an empty field becomes `NaN`, `-9999` becomes a number… and bronze is no longer faithful.
- **Ignoring the broken file with `except: pass`**: the data disappears and nobody knows. Always leave a trace.
- **Hard-coded paths** (`"data/raw"`): the check changes the paths with environment variables and your code will keep looking at yours.
- **Leaving a `.tmp` or a partial Parquet** under `bronze/readings/`: they will be counted as data.

## In a real job

The same idea with other names: Databricks **Auto Loader** (detects new files and ingests incrementally and
idempotently), **Snowpipe** in Snowflake, **Fivetran/Airbyte** for managed ingestion. In the cloud, the destination would be
Delta Lake or Iceberg on S3/ADLS (tables with ACID transactions over Parquet files). The principle —immutable,
traceable, idempotent raw data— is identical.

→ Next: [`03_silver.md`](03_silver.md)
