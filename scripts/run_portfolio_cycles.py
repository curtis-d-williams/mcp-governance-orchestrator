# SPDX-License-Identifier: MIT
"""Run governed portfolio cycles repeatedly at a fixed interval.

For each iteration:
  1. Invoke scripts/run_governed_portfolio_cycle.py as a subprocess.
  2. Archive the output artifact if it exists (even when the cycle returns non-zero).
  3. Sleep --interval seconds between iterations.
  4. Stop after --cycles iterations, or loop forever if --cycles is omitted.

Usage:
    python3 scripts/run_portfolio_cycles.py \\
        --manifest manifests/portfolio_manifest.json \\
        --task artifact_audit_example \\
        --interval 300 \\
        --cycles 5

Exit codes:
    0  — requested iterations completed (or loop interrupted).
"""

import argparse
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ---------------------------------------------------------------------------
# Load archive_cycle_artifact helper (importlib; no subprocess overhead)
# ---------------------------------------------------------------------------

_ARCHIVE_SCRIPT = Path(__file__).resolve().parent / "archive_cycle_artifact.py"
_archive_spec = importlib.util.spec_from_file_location("archive_cycle_artifact", _ARCHIVE_SCRIPT)
_archive_mod = importlib.util.module_from_spec(_archive_spec)
_archive_spec.loader.exec_module(_archive_mod)

_archive_artifact = _archive_mod.archive_artifact

_EXPLAIN_ARTIFACT_NAMES = [
    "planner_priority_breakdown.json",
    "planner_scoring_metrics.json",
]


# ---------------------------------------------------------------------------
# Command builder
# ---------------------------------------------------------------------------

def _build_cycle_cmd(args):
    """Return the argv list for one invocation of run_governed_portfolio_cycle.py.

    Args:
        args: Parsed argparse namespace with cycle configuration.

    Returns:
        list[str] — fully-formed subprocess argv.
    """
    script = str(_REPO_ROOT / "scripts" / "run_governed_portfolio_cycle.py")
    cmd = [
        "python3", script,
        "--manifest", args.manifest,
        "--output", args.output,
        "--top-k", str(args.top_k),
        "--exploration-offset", str(args.exploration_offset),
    ]
    for task in args.task:
        cmd += ["--task", task]
    if args.ledger is not None:
        cmd += ["--ledger", args.ledger]
    if args.policy is not None:
        cmd += ["--policy", args.policy]
    if args.max_actions is not None:
        cmd += ["--max-actions", str(args.max_actions)]
    if args.explain:
        cmd.append("--explain")
    if args.force:
        cmd.append("--force")
    if args.governance_policy is not None:
        cmd += ["--governance-policy", args.governance_policy]
    if args.capability_ledger is not None:
        cmd += ["--capability-ledger", args.capability_ledger]
    if args.comparison_gap_artifact is not None:
        cmd += ["--comparison-gap-artifact", args.comparison_gap_artifact]
    return cmd


# ---------------------------------------------------------------------------
# Core loop
# ---------------------------------------------------------------------------

def run_cycles(args, subprocess_run=None, sleep_fn=None):
    """Execute governed portfolio cycles per *args*.

    Designed for testability: subprocess_run and sleep_fn can be injected
    without patching module globals.

    Args:
        args:           Parsed argparse namespace.
        subprocess_run: Callable matching subprocess.run signature. Defaults
                        to subprocess.run.
        sleep_fn:       Callable matching time.sleep signature. Defaults to
                        time.sleep.

    Returns:
        Number of iterations completed.
    """
    if subprocess_run is None:
        subprocess_run = subprocess.run
    if sleep_fn is None:
        sleep_fn = time.sleep

    cmd = _build_cycle_cmd(args)
    limit = args.cycles  # None → loop forever

    iteration = 0
    while limit is None or iteration < limit:
        result = subprocess_run(cmd, capture_output=True, text=True)

        output_path = Path(args.output)
        archived_to = None
        if output_path.exists():
            _sidecar_paths = None
            if args.explain:
                _cycle_idle = False
                try:
                    _cd = json.loads(output_path.read_text(encoding="utf-8"))
                    _cycle_idle = (_cd.get("governed_result") or {}).get("idle") is True
                except Exception:
                    pass
                if not _cycle_idle:
                    _sidecar_paths = _EXPLAIN_ARTIFACT_NAMES
            archive_result = _archive_artifact(str(output_path), args.archive_dir,
                                               sidecar_paths=_sidecar_paths)
            archived_to = archive_result.get("archived_to")

        cycle_status = "ok" if result.returncode == 0 else f"FAILED (rc={result.returncode})"
        archive_label = archived_to if archived_to else "no output archived"
        print(f"[cycle {iteration + 1}] {cycle_status} | archived: {archive_label}", flush=True)
        if result.stdout:
            print(result.stdout, end="", flush=True)

        # After each cycle, check whether Phase F wrote a work-dir ledger.
        # If found, pin it into the next iteration's cmd so planner learning
        # carries forward without mutating args.
        work_dir_ledger = (
            Path(args.output).parent
            / f"{Path(args.output).stem}_artifacts"
            / "action_effectiveness_ledger.json"
        )
        if work_dir_ledger.exists():
            cmd = _build_cycle_cmd(args)
            # Replace or append --ledger with the work-dir path.
            if "--ledger" in cmd:
                ledger_idx = cmd.index("--ledger")
                cmd[ledger_idx + 1] = str(work_dir_ledger)
            else:
                cmd += ["--ledger", str(work_dir_ledger)]

        # After each cycle, check whether governed_cycle wrote a work-dir capability ledger.
        # If found, pin it into cmd so capability learning carries forward across cycles.
        work_dir_cap_ledger = (
            Path(args.output).parent
            / f"{Path(args.output).stem}_artifacts"
            / "capability_effectiveness_ledger.json"
        )
        if work_dir_cap_ledger.exists():
            if "--capability-ledger" in cmd:
                cap_idx = cmd.index("--capability-ledger")
                cmd[cap_idx + 1] = str(work_dir_cap_ledger)
            else:
                cmd += ["--capability-ledger", str(work_dir_cap_ledger)]

        iteration += 1
        # Sleep between iterations, not after the last one.
        if limit is None or iteration < limit:
            sleep_fn(args.interval)

    return iteration


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run governed portfolio cycles repeatedly at a fixed interval.",
        add_help=True,
    )
    parser.add_argument("--manifest", required=True, metavar="FILE",
                        help="Path to portfolio manifest JSON.")
    parser.add_argument("--task", action="append", required=True, metavar="TASK",
                        help="Task name to run (repeatable; at least one required).")
    parser.add_argument("--output", default="governed_portfolio_cycle.json", metavar="FILE",
                        help="Output path for each cycle artifact (default: governed_portfolio_cycle.json).")
    parser.add_argument("--ledger", default=None, metavar="FILE",
                        help="Path to action_effectiveness_ledger.json (optional).")
    parser.add_argument("--policy", default=None, metavar="FILE",
                        help="Path to planner_policy.json (optional).")
    parser.add_argument("--top-k", type=int, default=3, metavar="INT",
                        help="Number of top actions to consider (default: 3).")
    parser.add_argument("--exploration-offset", type=int, default=0, metavar="INT",
                        help="Starting exploration offset (default: 0).")
    parser.add_argument("--max-actions", type=int, default=None, metavar="INT",
                        help="Cap selected actions per run (default: no cap).")
    parser.add_argument("--explain", action="store_true", default=False,
                        help="Pass --explain to the governed planner loop.")
    parser.add_argument("--force", action="store_true", default=False,
                        help="Pass --force to the governed planner loop.")
    parser.add_argument("--governance-policy", default=None, metavar="FILE",
                        dest="governance_policy",
                        help="Path to governance_policy.json for Phase L (optional).")
    parser.add_argument("--capability-ledger", default=None, metavar="FILE",
                        dest="capability_ledger",
                        help="Path to capability_effectiveness_ledger.json (optional).")
    parser.add_argument("--comparison-gap-artifact", default=None, metavar="FILE",
                        dest="comparison_gap_artifact",
                        help="Optional comparison-gap artifact JSON to seed capability_gaps (optional).")
    parser.add_argument("--archive-dir", default="artifacts/cycles", metavar="DIR",
                        help="Directory to write cycle archives into (default: artifacts/cycles).")
    parser.add_argument("--interval", type=int, required=True, metavar="INT",
                        help="Seconds to sleep between cycle iterations.")
    parser.add_argument("--cycles", type=int, default=None, metavar="INT",
                        help="Number of cycles to run. Omit to loop forever.")

    args = parser.parse_args(argv)
    run_cycles(args)


if __name__ == "__main__":
    main()
