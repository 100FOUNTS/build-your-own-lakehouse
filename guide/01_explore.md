# Step 1 — Explore the raw data

⏱ 2–3 h · Deliverable: `notes/01_findings.md` · Check: `make check-1` (plus `/review 1` with your mentor)

## What you are going to do

Open the historian files **before writing any pipeline** and document, with evidence, everything you find
odd. You build nothing yet: you investigate.

## Why this step exists

> *"80 % of a data engineer's work is understanding the data; the remaining 20 % is fixing what they did not understand
> at the beginning."*

Real plant data **never comes clean**: sensors fail, exporters change configuration, someone restarts a server in the
middle of the day. Those problems give no warning: they sneak into the model and become wrong predictions that nobody can explain.

Look at the economics of it:

| When you discover a problem | What it costs to fix |
|---|---|
| Today, looking at the data | Writing one line in your pipeline |
| When the model gives odd results | Days of debugging without knowing where to start |
| When Marta has already made decisions with your numbers | Loss of trust (and of service) |

That is why this step is the most important of the exercise, and why we do it first: **each finding you make today becomes
a design decision** in bronze, silver or gold.

## What it is for in a real job

When you arrive at a new project, the first thing they ask is *"explain this data to me"*. Whoever answers precisely
(grain, units, quality, known gaps) builds trust from day one. It is also how you know what
questions to ask the data owner: *"I saw that from July 5th…, did something change in the exporter?"*.

## The data you have

**`data/raw/historian/date=YYYY-MM-DD/readings_YYYYMMDD.csv.gz`** — 150 files, one per day, exported by the plant's
historian. Five columns:

| Column | What it is |
|---|---|
| `timestamp` | Instant of the reading (text) |
| `tag` | Name of the measurement point: `PLANT.PUMP.SENSOR` |
| `value` | Measured value (text, may come empty) |
| `unit` | Unit in which the value comes |
| `quality` | Quality declared by the system: `GOOD`, `BAD`, `UNCERTAIN` |

Each pump has 5 sensors: vibration, bearing temperature, discharge pressure, motor current and an indicator of whether
the pump is running.

**`data/raw/reference/assets.csv`** (the master of the 20 pumps) and **`work_orders.csv`** (the work orders).

## Concepts you need

- **Historian**: the plant system that stores sensor readings over time (PI, Ignition, etc.).
  It exports files; it is not designed for analytics.
- **Tag**: the identifier of a sensor. A real historian has hundreds of thousands.
- **Grain**: what a row represents. Here: *a reading of one tag at one instant*. Everything else is defined from there.
- **Sentinel value**: a "special" number that means "there is no data" (like `-9999`). If you treat it as a real measurement,
  a pump's average can come out negative.
- **Time zone / UTC**: local time depends on where you are; UTC is the universal reference. A time-zone error
  moves data from one day to another and gives no visible error.
- **Late data**: a reading that arrives in a file later than the one it belonged to.

## Your task

### 1. First contact (30 min)
Read **one** file with pandas (`pd.read_csv("…csv.gz", dtype=str)`) or with DuckDB
(`duckdb.sql("select * from read_csv('…') limit 20")`). Look at the first rows, the size, the distinct values of
`unit` and `quality`, and the tags that exist.

### 2. Detective questions (1–2 h)
A good exploratory analysis is guided by questions. Answer each one **with a query**, not with intuition:

- How many rows should a complete day have (20 pumps × 5 sensors × readings per day)? Do all the files have them? And the smallest ones, why?
- Are there repeated rows? Within the same file? Between different files?
- Does each tag always come with the same `unit`? And over time?
- Which numeric values go with each value of `quality`? Are there numbers that cannot be measurements?
- Are the values of each sensor in a physically possible range? Are there readings that stand out *relative to their neighbors* even though the system says they are `GOOD`?
- How is the time written? Is it the same in all the files? What offset does it carry?
- Can all the files be opened? Do they all have the same columns, in the same order?
- Does each file cover exactly 24 h? Are there hours without data from any pump?
- Are there sensors whose value stops changing for hours or days?
- In the work orders: how many types are there? Are they all written the same way? How many are failures?
- What does a *healthy* pump look like compared to one about to fail? (Plot the vibration of a pump that had a corrective
  failure, 3 weeks before and after.)

> You do not have to be exhaustive with every question: you have to **find** at least six different types of problem,
> prove them and decide what you will do about them.

### 3. Document (1 h)
In `notes/01_findings.md`, for each finding (`### H1`, `### H2`…):

- **Evidence**: the query or code (in a ``` block) that proves it, with the result you saw.
- **What it means**: how you interpret it (a sensor error? an exporter error? reality?).
- **Decision:** what you will do and in which layer: do you keep it in bronze and fix it in silver? Do you flag it? Do you discard it?

And fill in the **My data dictionary** section: grain, columns, units and possible values of each source.

## How you will know you are done

```bash
make check-1
```

This check verifies that your document exists, that every finding has evidence and a decision, and that it covers several types of
problem. **It cannot know whether your findings are correct** — that is what `/review 1` with your mentor does: it knows what
is in the data and will tell you which categories you are missing without giving you the direct answer.

## Comprehension questions (answer them in your notes)

1. Why did you not clean anything in the original files while you explored?
2. Of the problems you found, which would *silently break* the model (without giving an error)? Which would give a visible error? Which is worse and why?
3. If the provider changes the file format again tomorrow, how would you find out? (Keep that idea: you will use it in bronze.)
4. What would you ask the plant's instrumentation engineer after seeing your findings?

## Hints (open them only if you are stuck)

<details><summary>Hint 1 — How to read many files at once</summary>

DuckDB reads a file pattern at once: `read_csv('data/raw/historian/*/*.csv.gz', ...)`. With pandas, a loop over
`Path(...).glob("date=*/*.csv.gz")`. If something fails when reading *everything together*, ask yourself why: that is already a finding.
</details>

<details><summary>Hint 2 — If you do not know where to start</summary>

Make a summary table per file: name, number of rows, first and last time, columns it carries. The "odd" files
jump out when you compare 150 summary rows.
</details>

<details><summary>Hint 3 — To see the spikes</summary>

A spike cannot be seen with a global limit (legitimate vibration also rises when a pump degrades). Compare each
reading with the **median of its neighbors** of the same tag, or plot one sensor for a week.
</details>

<details><summary>Hint 4 — If you already have 4–5 findings and see no more</summary>

Look at what is *not there*: hours without data, a file with only a header. Also look at what *changes over time*:
compare the first files with those after day 90.
</details>

## Common traps

- **Reading with automatic types.** pandas converts columns on its own and can hide the problem (for example,
  turn an empty value into `NaN`). Read everything as text (`dtype=str`) while you explore.
- **Trusting `quality`.** It is what the system *declares*; reality may be different.
- **Fixing while you explore.** Write it down, do not correct: corrections go to bronze/silver with their own code and tests.

## In a real job

This document is what you would call "data profiling" or "discovery". Many companies formalize it in a *data
catalog* (DataHub, Unity Catalog, dbt docs). Your data dictionary is the small version of that.

→ Next: [`02_bronze.md`](02_bronze.md)
