# SPDX-License-Identifier: MIT
"""Deterministic planner experiment runner.

Executes the planner N times, collects run envelopes, and produces an
aggregated experiment result via evaluate_planner_runs.evaluate_envelopes.

Usage:
    python scripts/run_planner_experiment.py --runs 3 \\
        --portfolio-state state.json --output experiment_results.json

    python scripts/run_planner_experiment.py --config experiment_config.json

Envelopes are written as:
    planner_run_envelope_run1.json
    planner_run_envelope_run2.json
    ...
in the same directory as --output.

v0.37: --config support for JSON-driven experiment configuration.
       CLI flags override config values when both are supplied.
       Existing CLI-only behaviour unchanged.
stdlib only (except shared project imports).
"""

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.evaluate_planner_runs import evaluate_envelopes  # noqa: E402

# Hard-coded defaults applied after config merging.
_DEFAULTS = {
    "runs": 1,
    "top_k": 3,
    "exploration_offset": 0,
    "explain": False,
    "output": "experiment_results.json",
    "envelope_prefix": "planner_run_envelope",
}


def _load_config(config_path):
    """Load and return experiment config dict from a JSON file."""
    return json.loads(Path(config_path).read_text(encoding="utf-8"))


def _apply_config(args, config):
    """Fill None fields on *args* from *config*, then apply hard defaults.

    Precedence (highest to lowest):
        1. Explicitly supplied CLI flag (non-None value on args)
        2. Config file value
        3. Hard-coded default in _DEFAULTS

    Modifies *args* in place and returns it.
    """
    planner = config.get("planner", {})
    output = config.get("output", {})

    _fill(args, "runs",               config.get("runs"))
    _fill(args, "portfolio_state",    planner.get("portfolio_state"))
    _fill(args, "ledger",             planner.get("ledger"))
    _fill(args, "policy",             planner.get("policy"))
    _fill(args, "top_k",              planner.get("top_k"))
    _fill(args, "exploration_offset", planner.get("exploration_offset"))
    _fill(args, "max_actions",        planner.get("max_actions"))
    _fill(args, "explain",            planner.get("explain"))
    _fill(args, "output",             output.get("experiment_results"))
    _fill(args, "envelope_prefix",    output.get("envelope_prefix"))

    # Apply hard defaults for any field still None.
    for attr, default in _DEFAULTS.items():
        if getattr(args, attr, None) is None:
            setattr(args, attr, default)

    return args


def _fill(args, attr, value):
    """Set *attr* on *args* to *value* only when *attr* is currently None."""
    if getattr(args, attr, None) is None and value is not None:
        setattr(args, attr, value)


def _envelope_name(run_number, prefix="planner_run_envelope"):
    """Return deterministic envelope filename for a 1-based run number."""
    return f"{prefix}_run{run_number}.json"


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

    prefix = getattr(args, "envelope_prefix", "planner_run_envelope")
    envelope_paths = []
    for i in range(1, args.runs + 1):
        envelope_path = output_dir / _envelope_name(i, prefix)
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
    parser.add_argument("--config", default=None, metavar="FILE",
                        help="Path to JSON experiment config file.")
    parser.add_argument("--runs", type=int, default=None, metavar="INT",
                        help="Number of planner runs (default: 1).")
    parser.add_argument("--portfolio-state", default=None, metavar="FILE",
                        help="Path to portfolio_state.json.")
    parser.add_argument("--ledger", default=None, metavar="FILE",
                        help="Path to action_effectiveness_ledger.json.")
    parser.add_argument("--policy", default=None, metavar="FILE",
                        help="Path to planner_policy.json.")
    parser.add_argument("--top-k", type=int, default=None, metavar="INT",
                        help="Number of top actions to consider (default: 3).")
    parser.add_argument("--exploration-offset", type=int, default=None, metavar="INT",
                        help="Exploration offset into action queue (default: 0).")
    parser.add_argument("--max-actions", type=int, default=None, metavar="INT",
                        help="Cap selected actions per run (default: no cap).")
    parser.add_argument("--explain", action="store_true", default=None,
                        help="Pass --explain to each planner run.")
    parser.add_argument("--output", default=None, metavar="FILE",
                        help="Destination for experiment_results.json (default: experiment_results.json).")
    parser.add_argument("--envelope-prefix", default=None, metavar="STR",
                        help="Prefix for envelope filenames (default: planner_run_envelope).")
    args = parser.parse_args(argv)

    config = {}
    if args.config is not None:
        config = _load_config(args.config)

    _apply_config(args, config)

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
