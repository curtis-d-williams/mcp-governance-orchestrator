#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""One-command wrapper for the example governed portfolio cycle pipeline.

Steps executed in order:
  1. Generate manifests/portfolio_manifest_example.json (absolute repo path).
  2. Invoke scripts/run_portfolio_cycles.py with example-safe defaults.

Hardwired example defaults (all overridable via CLI):
  task    : health_probe_example
  ledger  : experiments/action_effectiveness_ledger_synthetic_v2.json
  top-k   : 2  (avoids high_risk when unique_tasks == 1; see evaluate_planner_config.py)
  interval: 0  (no sleep between cycles in the example)
  cycles  : 1

Usage (run from repo root):
    python3 scripts/run_example_governed_cycles.py
    python3 scripts/run_example_governed_cycles.py --cycles 3
    python3 scripts/run_example_governed_cycles.py --cycles 2 --archive-dir my_archives
"""

import argparse
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULT_MANIFEST = str(_REPO_ROOT / "manifests" / "portfolio_manifest_example.json")
_DEFAULT_LEDGER = str(_REPO_ROOT / "experiments" / "action_effectiveness_ledger_synthetic_v2.json")
_DEFAULT_TASK = "health_probe_example"
_DEFAULT_TOP_K = 2
_DEFAULT_INTERVAL = 0
_DEFAULT_CYCLES = 1
_DEFAULT_OUTPUT = "governed_portfolio_cycle.json"
_DEFAULT_ARCHIVE_DIR = "artifacts/cycles"

_MAKE_MANIFEST_SCRIPT = str(_REPO_ROOT / "scripts" / "make_example_manifest.py")
_RUN_CYCLES_SCRIPT = str(_REPO_ROOT / "scripts" / "run_portfolio_cycles.py")


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def run_example_cycles(args, subprocess_run=None):
    """Generate the example manifest then invoke run_portfolio_cycles.py.

    Args:
        args:           Parsed argparse namespace.
        subprocess_run: Callable matching subprocess.run signature; defaults to
                        subprocess.run.  Injected in tests.

    Returns:
        Exit code (int): 0 on success, non-zero on any subprocess failure.
    """
    if subprocess_run is None:
        subprocess_run = subprocess.run

    # Step 1: generate the example manifest.
    result = subprocess_run(
        ["python3", _MAKE_MANIFEST_SCRIPT],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.stderr.write(f"error: make_example_manifest failed:\n{result.stderr}\n")
        return result.returncode
    sys.stdout.write(result.stdout)

    # Step 2: run the portfolio cycles with example defaults.
    cmd = [
        "python3", _RUN_CYCLES_SCRIPT,
        "--manifest", args.manifest,
        "--task", args.task,
        "--ledger", args.ledger,
        "--top-k", str(args.top_k),
        "--interval", str(args.interval),
        "--output", args.output,
        "--archive-dir", args.archive_dir,
    ]
    if args.cycles is not None:
        cmd += ["--cycles", str(args.cycles)]

    result = subprocess_run(cmd, capture_output=False, text=True)
    return result.returncode


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "One-command example: generate manifest and run governed portfolio cycles."
        ),
        add_help=True,
    )
    parser.add_argument(
        "--cycles", type=int, default=_DEFAULT_CYCLES, metavar="INT",
        help=f"Number of cycles to run (default: {_DEFAULT_CYCLES}).",
    )
    parser.add_argument(
        "--interval", type=int, default=_DEFAULT_INTERVAL, metavar="INT",
        help=f"Seconds to sleep between cycles (default: {_DEFAULT_INTERVAL}).",
    )
    parser.add_argument(
        "--archive-dir", default=_DEFAULT_ARCHIVE_DIR, metavar="DIR",
        help=f"Directory for archived cycle artifacts (default: {_DEFAULT_ARCHIVE_DIR}).",
    )
    parser.add_argument(
        "--top-k", type=int, default=_DEFAULT_TOP_K, metavar="INT",
        help=f"Number of top actions to consider (default: {_DEFAULT_TOP_K}).",
    )
    parser.add_argument(
        "--output", default=_DEFAULT_OUTPUT, metavar="FILE",
        help=f"Output path for each cycle artifact (default: {_DEFAULT_OUTPUT}).",
    )
    # Hardwired but overridable for flexibility.
    parser.add_argument(
        "--manifest", default=_DEFAULT_MANIFEST, metavar="FILE",
        help="Path to portfolio manifest JSON (default: manifests/portfolio_manifest_example.json).",
    )
    parser.add_argument(
        "--task", default=_DEFAULT_TASK, metavar="TASK",
        help=f"Agent task name (default: {_DEFAULT_TASK}).",
    )
    parser.add_argument(
        "--ledger", default=_DEFAULT_LEDGER, metavar="FILE",
        help="Path to action effectiveness ledger (default: experiments/action_effectiveness_ledger_synthetic_v2.json).",
    )

    args = parser.parse_args(argv)
    sys.exit(run_example_cycles(args))


if __name__ == "__main__":
    main()
