#!/usr/bin/env python3
"""
run_pipeline.py
────────────────────────────────────────────────────────────────────────────
Single entry point for the full training pipeline.

Usage:
    python run_pipeline.py

Steps (run in order):
    1. build_real_panel.py      — builds ward × month panel from incidents
    2. census_pop_density.py    — adds pop_density feature (Census 2011)
    3. train_model.py           — trains XGBoost, writes model + metrics
    4. build_equity_features.py — Census 2011 SAL → ward equity indicators

Each step prints its own progress. The script stops immediately if any
step fails so errors are caught early.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

STEPS = [
    ("Build real panel",          ROOT / "src" / "pipeline" / "build_real_panel.py"),
    ("Census pop density feature", ROOT / "src" / "pipeline" / "census_pop_density.py"),
    ("Train model",               ROOT / "src" / "modeling"  / "train_model.py"),
    ("Equity features (SAL)",     ROOT / "build_equity_features.py"),
]

def run_step(label: str, script: Path) -> None:
    print(f"\n{'=' * 62}")
    print(f"  STEP: {label}")
    print(f"  {script.relative_to(ROOT)}")
    print(f"{'=' * 62}\n")
    result = subprocess.run([sys.executable, str(script)], cwd=ROOT)
    if result.returncode != 0:
        print(f"\n✗  Step failed: {label}  (exit code {result.returncode})")
        print("   Fix the error above, then re-run run_pipeline.py.")
        sys.exit(result.returncode)
    print(f"\n✓  {label} complete.")

if __name__ == "__main__":
    print("METSI-EWS — Training Pipeline")
    print(f"Working directory: {ROOT}\n")
    for label, script in STEPS:
        run_step(label, script)
    print(f"\n{'=' * 62}")
    print("  All steps complete. Model outputs → data/model_outputs/real/")
    print(f"{'=' * 62}\n")

    print("Launching dashboard …")
    app = ROOT / "app.py"
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(app)], cwd=ROOT)
