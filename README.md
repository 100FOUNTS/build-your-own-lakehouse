> **This is the `solution` branch: it contains a reference solution (spoilers).** Build the exercise yourself on `main` first. See [`SOLUTION.md`](SOLUTION.md).

# Predictive-maintenance lakehouse — a build-it-yourself data engineering exercise

An exercise to learn **data engineering by building, not by reading**. You start from dirty raw files of a pumping
plant and end with a complete, tested and automated pipeline that feeds a failure-risk API.

> **Nothing is done here.** You write the ingestion, the cleaning, the features, the model, the orchestration and the API.
> All we give you is the data, a guide that explains the **what, why and what-for** of each step, and automatic
> checks (`make check-N`) that tell you, with data, whether what you built is right.

**Stack:** Python 3.12 · pandas · Parquet · DuckDB · dbt · scikit-learn · Dagster · FastAPI · uv.
Everything runs locally on your laptop; no cloud account and no Docker are needed.

> The guide and the checks are written in English. The *data* was generated with Spanish values in a few places
> (failure modes such as `rodamiento`, `sello`, `cavitacion`, and some free-text fields), as a real plant would have.
> You can also write your notes in Spanish: the step 1 check understands both languages.

## The situation (the real case you are going to solve)

You are a data engineer at a company that operates the **PLT01 pumping plant**: 20 centrifugal pumps that move water
24 hours a day. When a pump fails unexpectedly, the plant stops, service is lost and the urgent repair costs
several times more than a planned one.

Marta, the maintenance manager, asks you for something very concrete:

> *"Every morning tell me which pumps have the highest risk of failing in the **next week**, so I can put them in the
> maintenance plan before they break."*

You have three things:

| What | Where | What it is |
|---|---|---|
| Sensor readings | `data/raw/historian/` | One `.csv.gz` file per day exported by the plant **historian** (each pump has 5 sensors, read every 10 min) |
| Pump master | `data/raw/reference/assets.csv` | Model, criticality and installation of each pump |
| Work orders | `data/raw/reference/work_orders.csv` | Preventive maintenance, inspections and **corrective repairs (= the failures)** |

And a problem: **real data comes dirty**. Part of the exercise is discovering how, because on a job nobody will give you the list.

## What you are going to build

```
 data/raw ──► BRONZE ──► SILVER ──► GOLD ──► MODEL ──► ml.predictions ──► API
 (raw)       (faithful   (clean,     (one row  (will it   (risk per        (GET /assets/
              immutable   trustworthy) per pump  fail in 7  pump and day)    P101/risk)
              copy)                    and day)  days?)
 ◄──────────────────────── orchestrated by Dagster, end to end ───────────────────────────►
```

| Step | What you build | What it is for in a real job | Time |
|---|---|---|---|
| 0 | Ready environment | The project runs the same on your machine and anyone else's | 30 min |
| 1 | **Exploration** of the raw data | Understand before building: every problem you do not see today is a bug tomorrow | 2–3 h |
| 2 | **Bronze**: idempotent ingestion | Faithfully store what arrives and always be able to reprocess | 3–4 h |
| 3 | **Silver** with dbt: cleaning | Data you can trust, with tests | 4–6 h |
| 4 | **Gold** with dbt: features and label | Turn clean data into the table the model uses (without cheating with time) | 3–5 h |
| 5 | Risk **model** | Predict failures with an honest evaluation | 3–4 h |
| 6 | **Orchestration** with Dagster | Everything runs by itself, in order, and can be monitored | 2–3 h |
| 7 | **API** with FastAPI | Other systems (and Marta) can query the result | 1–2 h |
| 8 | What next | Production: Docker, CI, monitoring, streaming | — |

In total about **20–28 hours**. Go at your own pace: it is better to finish one step understanding it than to run through all eight.

## How you work (the cycle of each step)

1. **Read** `guide/0N_….md`. Start with *Why this step exists*: the idea comes before the code.
2. **Ask** Claude Code (mentor mode, optional): `/step N` brings you into the topic with questions, and `/why …` explains any concept.
3. **Build** it yourself. If you get stuck, `/hint N` gives you the next hint, without handing you the solution.
4. **Check**: `make check-N`. If it fails, the message tells you what is not met and why it matters.
5. **Review**: `/review N`. Your mentor reads your code, points out what is wrong or fragile, and asks you 2–3 questions to see whether you understood.
6. **Write** your decisions in `notes/` in your own words. If you cannot explain it, you do not master it yet.

It also works without Claude Code: the guide and the checks are self-sufficient.

## Getting started

Requirements: [uv](https://docs.astral.sh/uv/) (on macOS: `brew install uv`). Python 3.12 is installed by uv.

```bash
git clone https://github.com/100FOUNTS/build-your-own-lakehouse.git
cd build-your-own-lakehouse
make setup          # installs dependencies (uses uv)
make check-0        # is everything ready?
```

And open [`guide/00_start.md`](guide/00_start.md). `make progress` shows which steps are already green.

## Rules of the game

1. **`data/raw/` is never edited.** It is what arrived; if you change it, you lose the evidence. (The check watches it.)
2. **Do not open `checks/_truth.json`** until you finish: it holds the list of problems hidden in the data. If you open it,
   you take the learning out of step 1. (If you use Claude Code, it is blocked for the assistant.)
3. **There is no single solution.** The checks verify results and properties (does it duplicate when repeated? is there
   temporal leakage?), not your style. Your design can differ from the reference and be just as good.
4. **Paths are not written in the code**: use the ones in `src/lakehouse/paths.py` (`LH_*` variables). That way your pipeline
   can run in any folder, which is what a real pipeline does.

## Folder map

```
README.md           this
guide/              the step-by-step guide (start at 00_start.md) + glossary
notes/              YOUR notebook: findings, decisions, learning log (templates to fill in)
src/lakehouse/      YOUR Python code (bronze.py, train.py, definitions.py, api.py) — paths.py is provided
dbt/                YOUR dbt project (silver and gold models)
tests/              YOUR tests (the temporal-leakage one is mandatory)
checks/             the automatic checks of each step (make check-N)
data/raw/           raw data (read-only)
data/incoming/      10 days that will "arrive" with `make arrival`
Makefile            shortcuts: make bronze, silver, gold, train, run, dagster, api, check…
```

## When you finish

Compare your solution with the `solution` branch of this repository and read [`guide/08_next.md`](guide/08_next.md):
improvement challenges, what is missing to take it to production, and how to tell this project in an interview.

## Contributing

Found a typo, an unclear explanation or a check that gives a wrong verdict? Open an issue or a pull request. If you
solved the exercise differently from the reference and a check rejected a valid design, that is especially valuable feedback.
