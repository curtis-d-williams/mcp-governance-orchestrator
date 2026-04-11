# SPDX-License-Identifier: MIT
"""
run_multi_cycle_factory_demo.py

Developer-facing demo script: runs N autonomous factory cycles against a
fixed portfolio-state fixture and prints a consolidated portfolio report
after all cycles complete.

Usage (from repo root):
    python3 scripts/run_multi_cycle_factory_demo.py [--cycles N] [--output-dir DIR]

The script accumulates capability-effectiveness state across cycles by
passing the same capability_ledger path as both input and output on every
cycle call. The action-effectiveness ledger is passed read-only and is not
mutated by this script.
"""

import argparse
import importlib.util
import shutil
import sys
import tempfile
from pathlib import Path


# ---------------------------------------------------------------------------
# Repo path bootstrap
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ---------------------------------------------------------------------------
# Dynamic imports via importlib (repo-standard pattern)
# ---------------------------------------------------------------------------

def _load_module(name, relative_script):
    spec = importlib.util.spec_from_file_location(
        name,
        Path(__file__).resolve().parent / relative_script,
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _import_run_cycle():
    mod = _load_module("run_autonomous_factory_cycle", "run_autonomous_factory_cycle.py")
    return mod.run_autonomous_factory_cycle


def _import_portfolio_report():
    mod = _load_module("portfolio_report", "portfolio_report.py")
    return (
        mod.load_ledger,
        mod.print_header,
        mod.print_capability_block,
        mod.print_similarity_summary,
        mod.print_adaptation_summary,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser():
    parser = argparse.ArgumentParser(
        description="Run multiple autonomous factory cycles and print a portfolio report.",
    )
    parser.add_argument(
        "--portfolio-state",
        default=str(
            _REPO_ROOT / "experiments" / "factory_demo" / "portfolio_state_missing_github.json"
        ),
        help="Path to portfolio state fixture (read-only; copied per cycle).",
    )
    parser.add_argument(
        "--ledger",
        default=str(
            _REPO_ROOT / "experiments" / "factory_demo" / "action_effectiveness_ledger.json"
        ),
        help="Path to action effectiveness ledger (passed read-only to cycle runner).",
    )
    parser.add_argument(
        "--capability-ledger",
        default=None,
        help=(
            "Path for the accumulating capability effectiveness ledger. "
            "Defaults to a file inside a temp directory."
        ),
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=2,
        help="Number of factory cycles to run (default: 2).",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for per-cycle output JSON files. Defaults to a temp directory.",
    )
    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = _build_parser()
    args = parser.parse_args()

    # Resolve output directory
    if args.output_dir is None:
        output_dir = Path(tempfile.mkdtemp(prefix="factory_demo_"))
    else:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    # Resolve accumulating capability ledger path
    if args.capability_ledger is None:
        capability_ledger_path = str(output_dir / "capability_effectiveness_ledger.json")
    else:
        capability_ledger_path = args.capability_ledger

    portfolio_state_src = Path(args.portfolio_state)
    ledger_path = args.ledger
    n_cycles = args.cycles

    run_autonomous_factory_cycle = _import_run_cycle()

    # -------------------------------------------------------------------
    # Per-cycle execution
    # -------------------------------------------------------------------

    print("=" * 70)
    print("GOVERNED AUTONOMOUS CAPABILITY FACTORY — MULTI-CYCLE DEMO")
    print("=" * 70)
    print(f"Portfolio state : {portfolio_state_src}")
    print(f"Action ledger   : {ledger_path}")
    print(f"Capability ledger: {capability_ledger_path}")
    print(f"Cycles          : {n_cycles}")
    print(f"Output dir      : {output_dir}")
    print("=" * 70)

    for cycle_num in range(1, n_cycles + 1):
        print(f"\n--- Cycle {cycle_num} of {n_cycles} ---")

        # Copy fixture to a temp path so writeback does not mutate the original
        temp_portfolio = str(output_dir / f"portfolio_state_cycle_{cycle_num}.json")
        shutil.copy2(str(portfolio_state_src), temp_portfolio)

        per_cycle_output = str(output_dir / f"cycle_{cycle_num}.json")

        run_autonomous_factory_cycle(
            portfolio_state=temp_portfolio,
            ledger=ledger_path,
            capability_ledger=capability_ledger_path,
            capability_ledger_output=capability_ledger_path,
            output=per_cycle_output,
        )

        print(f"Cycle {cycle_num} complete. Output: {per_cycle_output}")

    # -------------------------------------------------------------------
    # Portfolio report
    # -------------------------------------------------------------------

    print("\n" + "=" * 70)
    print("PORTFOLIO REPORT")
    print("=" * 70)

    (
        load_ledger,
        print_header,
        print_capability_block,
        print_similarity_summary,
        print_adaptation_summary,
    ) = _import_portfolio_report()

    ledger = load_ledger(capability_ledger_path)
    all_caps = ledger.get("capabilities", {})
    repair = all_caps.get("_repair_cycle")
    capabilities = {k: v for k, v in all_caps.items() if k != "_repair_cycle"}

    print_header(capability_ledger_path, capabilities, repair)
    for name in sorted(capabilities):
        print_capability_block(name, capabilities[name])
    print_similarity_summary(capabilities)
    print_adaptation_summary(capabilities)


if __name__ == "__main__":
    main()
