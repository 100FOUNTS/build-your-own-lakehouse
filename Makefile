# Shortcuts for the exercise. Requires uv (https://docs.astral.sh/uv/).  Type `make` to see the help.
UV ?= uv
export PYTHONPATH := $(CURDIR)/src
DBT = $(UV) run dbt
DBT_ARGS = --project-dir dbt --profiles-dir dbt
.PHONY: help setup fix-venv bronze silver gold dbt-test train run dagster api arrival check check-0 check-1 check-2 check-3 check-4 check-5 check-6 check-7 progress bonus notebook clean

help:  ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

setup:  ## Install dependencies (once)
	$(UV) sync
	-chflags -R nohidden .venv

fix-venv:  ## macOS: if you see "No module named ..." after a uv sync
	chflags -R nohidden .venv

# ------------------------------------------------------------------ your pipeline
bronze:  ## Step 2: raw -> bronze
	$(UV) run python -m lakehouse.bronze

silver:  ## Step 3: bronze -> silver (dbt build of dbt/models/silver)
	$(DBT) build $(DBT_ARGS) --select path:models/silver --indirect-selection cautious

gold:  ## Step 4: silver -> gold (dbt build of dbt/models/gold)
	$(DBT) build $(DBT_ARGS) --select path:models/gold

train:  ## Step 5: gold -> model + ml.predictions
	$(UV) run python -m lakehouse.train

run: bronze silver gold train  ## The whole pipeline in order (what you automate in step 6)

dagster:  ## Step 6: Dagster UI at http://localhost:3000
	$(UV) run dagster dev -m lakehouse.definitions

api:  ## Step 7: your API at http://localhost:8000/docs
	$(UV) run uvicorn lakehouse.api:app --reload --port 8000

arrival:  ## Simulate 1 new historian file arriving (data/incoming -> data/raw)
	$(UV) run python tools/arrival.py

notebook:  ## JupyterLab to explore (step 1)
	$(UV) run --group notebooks jupyter lab notebooks/

# ------------------------------------------------------------------ checks
check-0:  ## Check that your environment is ready
	$(UV) run pytest checks/test_step0_environment.py
check-1:  ## Check that you documented what you found
	$(UV) run pytest checks/test_step1_exploration.py
check-2:  ## Check your bronze (includes idempotency)
	$(UV) run pytest checks/test_step2_bronze.py
check-3:  ## Check your silver
	$(UV) run pytest checks/test_step3_silver.py
check-4:  ## Check your gold and your temporal-leakage test
	$(UV) run pytest checks/test_step4_gold.py
check-5:  ## Check your model
	$(UV) run pytest checks/test_step5_model.py
check-6:  ## Check your orchestration (runs everything end to end in temporary folders)
	$(UV) run pytest checks/test_step6_orchestration.py
check-7:  ## Check your API
	$(UV) run pytest checks/test_step7_api.py
progress:  ## Summary: which steps are already green
	$(UV) run python tools/progress.py

check:  ## All the steps (the ones you have not done yet fail with a message telling you what is missing)
	$(UV) run pytest checks

bonus:  ## Extra challenges (optional): skipped by `make check`
	$(UV) run pytest checks -m bonus

clean:  ## Delete what you generate (bronze, warehouse, models); does NOT touch data/raw
	rm -rf data/bronze data/quarantine data/warehouse.duckdb data/warehouse.duckdb.wal data/models dbt/target dbt/logs
