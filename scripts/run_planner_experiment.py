# SPDX-License-Identifier: MIT
"""Deterministic planner experiment runner.

Executes the planner N times, collects run envelopes, and produces an
aggregated experiment result via evaluate_planner_runs.evaluate_envelopes.

Usage:
    python scripts/run_planner_experiment.py --runs 3 \\
        --portfolio-state state.json --output experiment_results.json

Envelopes are written as:
    planner_run_envelope_run1.json
    planner_run_envelope_run2.json
    ...
in the same directory as --output.

v0.36 addition. stdlib only (except shared project imports).
"""

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.evaluate_planner_runs import evaluate_envelopes  # noqa: E402


def _envelope_name(run_number):
    """Return deterministic envelope filename for a 1-based run number."""
    return f"planner_run_envelope_run{run_number}.json"


def _build_planner_argv(args, envelope_path):
    """Build argv list for one planner invocation.

    Always includes --run-envelope.  Other flags are passed through only when
    the corresponding arg is set so the planner default behaviour is preserved
    for absent inputs.
    """
    argv = ["--run-envelope", str(envelope_path)]
    if args.portfolio_state is not None:
        argv += ["--portfolio-state", args.portfolio_state]
    if args.ledger is not None:
        argv += ["--ledger", args.ledger]
    if args.policy is not None:
        argv += ["--policy", args.policy]
    argv += ["--top-k", str(args.top_k)]
    argv += ["--exploration-offset", str(args.exploration_offset)]
    if args.max_actions is not None:
        argv += ["--max-actions", str(args.max_actions)]
    if args.explain:
        argv.append("--explain")
    return argv


def run_experiment(args, planner_main=None):
    """Execute the planner args.runs times and return aggregated results.

    Args:
        args:         Parsed CLI namespace (or any object with the same attrs).
        planner_main: Optional callable used instead of the real planner main.
                      Accepts a list of argv strings.  Defaults to
                      scripts.claude_dynamic_planner_loop.main when None.

    Returns:
        A dict with keys: run_count, envelope_paths, evaluation_summary.
    """
    if planner_main is None:
        from scripts.claude_dynamic_planner_loop import main as planner_main  # noqa: PLC0415

    output_path = Path(args.output)
    output_dir = output_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    envelope_paths = []
    for i in range(1, args.runs + 1):
        envelope_path = output_dir / _envelope_name(i)
        argv = _build_planner_argv(args, envelope_path)
        planner_main(argv)
        envelope_paths.append(str(envelope_path))

    loaded = [
        json.loads(Path(p).read_text(encoding="utf-8"))
        for p in envelope_paths
    ]
    evaluation_summary = evaluate_envelopes(loaded)

    result = {
        "run_count": args.runs,
        "envelope_paths": envelope_paths,
        "evaluation_summary": evaluation_summary,
    }
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run a deterministic planner experiment over N runs.",
        add_help=True,
    )
    parser.add_argument("--runs", type=int, default=1, metavar="INT",
                        help="Number of planner runs (default: 1).")
    parser.add_argument("--portfolio-state", default=None, metavar="FILE",
                        help="Path to portfolio_state.json.")
    parser.add_argument("--ledger", default=None, metavar="FILE",
                        help="Path to action_effectiveness_ledger.json.")
    parser.add_argument("--policy", default=None, metavar="FILE",
                        help="Path to planner_policy.json.")
    parser.add_argument("--top-k", type=int, default=3, metavar="INT",
                        help="Number of top actions to consider (default: 3).")
    parser.add_argument("--exploration-offset", type=int, default=0, metavar="INT",
                        help="Exploration offset into action queue (default: 0).")
    parser.add_argument("--max-actions", type=int, default=None, metavar="INT",
                        help="Cap selected actions per run (default: no cap).")
    parser.add_argument("--explain", action="store_true", default=False,
                        help="Pass --explain to each planner run.")
    parser.add_argument("--output", default="experiment_results.json", metavar="FILE",
                        help="Destination for experiment_results.json (default: experiment_results.json).")
    args = parser.parse_args(argv)

    if args.runs < 1:
        parser.error("--runs must be at least 1.")

    result = run_experiment(args)
    sys.stdout.write(
        f"Experiment complete: {result['run_count']} run(s), "
        f"identical={result['evaluation_summary']['identical']}, "
        f"results at {args.output}\n"
    )


if __name__ == "__main__":
    main()
