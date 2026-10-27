# Step 1 — What I found in the raw data

> This is your exploration notebook. Before writing a single line of pipeline, **look at the data** and write down what looks
> odd. Every problem you do not discover now will show up later as a number that does not add up, and it will be much more expensive.
>
> Format (the check reads it): one block per finding, starting with `### H1`, `### H2`… Each one needs
> **Evidence** (the query or code that proves it, inside a ``` block) and **Decision:** (one sentence: what you will do
> and in which layer: bronze, silver or gold).
>
> Replace every `TODO-STUDENT` with your own work. You can write in English or Spanish.

## Findings

### H1 — TODO-STUDENT (a short title for the first thing you found)

**Evidence:**

```sql
-- TODO-STUDENT: the query or code that shows it, and the result you saw
```

**What it means:** TODO-STUDENT (your interpretation: a sensor error? an exporter error? reality?)

**Decision:** TODO-STUDENT (what you will do, and in which layer)

<!-- Copy the block above for H2, H3, … You need at least 6 findings of different types. -->

## My data dictionary

> Describe each source in your own words: what a row is (the *grain*), what each column means, which unit it uses, and which
> values it can take. If you cannot explain it, you do not understand it yet.

### Historian (`data/raw/historian/date=YYYY-MM-DD/readings_YYYYMMDD.csv.gz`)

TODO-STUDENT: grain, columns, units, possible values of `quality`, the 5 sensors of each pump.

### `assets.csv` — pump master

TODO-STUDENT: grain and columns.

### `work_orders.csv` — work orders

TODO-STUDENT: grain and columns. Which values does `wo_type` take, and which of them are the failures you want to predict?
