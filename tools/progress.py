"""Show which step you are on: run each check quietly and summarize. Usage:  make progress"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STEPS = [
    (0, "Environment", "test_step0_environment.py"),
    (1, "Exploration (notes)", "test_step1_exploration.py"),
    (2, "Bronze", "test_step2_bronze.py"),
    (3, "Silver (dbt)", "test_step3_silver.py"),
    (4, "Gold + temporal leakage", "test_step4_gold.py"),
    (5, "Model", "test_step5_model.py"),
    (6, "Orchestration (Dagster)", "test_step6_orchestration.py"),
    (7, "API", "test_step7_api.py"),
]


def main() -> None:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    first_pending = None
    print("\nYour progress (each step runs its checks; steps 2 and 6 take a while)\n")
    for n, name, file in STEPS:
        t0 = time.time()
        proc = subprocess.run([sys.executable, "-m", "pytest", f"checks/{file}", "-q", "-p", "no:warnings", "--tb=no"],
                              cwd=ROOT, env=env, capture_output=True, text=True, check=False)
        passed = proc.returncode == 0
        icon = "✅" if passed else "⬜"
        if not passed and first_pending is None:
            first_pending = n
        print(f"  {icon}  Step {n}  {name:<28} ({time.time() - t0:4.0f} s)")
    if first_pending is None:
        print("\nYou completed all 8 steps! Read guide/08_next.md.\n")
    else:
        print(f"\nNext: step {first_pending}  →  guide/0{first_pending}_*.md  and  make check-{first_pending}\n")


if __name__ == "__main__":
    main()
