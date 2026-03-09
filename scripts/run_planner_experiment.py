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
v0.38: policy_sweep support in config.  When config contains a non-empty
       "policy_sweep" list each entry is run as a separate experiment with
       a materialised policy file; results are aggregated into
       policy_sweep_results.json.  Existing non-sweep behaviour unchanged.
stdlib only (except shared project imports).
"""

import argparse
import importlib.util
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
    "force": False,
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
    _fill(args, "mapping_override",   config.get("mapping_override"))

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
    mapping_override = getattr(args, "mapping_override", None)
    if mapping_override:
        argv += ["--mapping-override-json", json.dumps(mapping_override)]
    return argv


# ---------------------------------------------------------------------------
# v0.39: Pre-flight risk guardrail
# ---------------------------------------------------------------------------

# Cached evaluator module — loaded once on first use.
_evaluator_mod = None


def _load_evaluator_mod():
    """Load evaluate_planner_config as a module (importlib; cached)."""
    global _evaluator_mod
    if _evaluator_mod is None:
        _script = _REPO_ROOT / "scripts" / "evaluate_planner_config.py"
        spec = importlib.util.spec_from_file_location("evaluate_planner_config", _script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _evaluator_mod = mod
    return _evaluator_mod


def _run_preflight_check(args):
    """Compute a risk evaluation for the configured planner run.

    Imports build_evaluation and the underlying risk helpers from
    evaluate_planner_config (no subprocess; no JSON I/O).

    Returns the evaluation dict, or None when portfolio_state is not set
    (fallback mode — no risk assessment possible).
    """
    if getattr(args, "portfolio_state", None) is None:
        return None

    from scripts.planner_scoring import (
        load_effectiveness_ledger,
        load_planner_policy,
        load_portfolio_signals,
    )
    from scripts.claude_dynamic_planner_loop import ACTION_TO_TASK, resolve_action_to_task_mapping

    ev_mod = _load_evaluator_mod()

    ledger = load_effectiveness_ledger(getattr(args, "ledger", None))
    signals = load_portfolio_signals(args.portfolio_state)
    policy = load_planner_policy(getattr(args, "policy", None))
    mapping_override = getattr(args, "mapping_override", None)
    active_mapping = resolve_action_to_task_mapping(ACTION_TO_TASK, mapping_override)

    top_k = getattr(args, "top_k", 3) or 3
    exploration_offset = getattr(args, "exploration_offset", 0) or 0

    raw_actions = ev_mod._fetch_actions(args.portfolio_state, getattr(args, "ledger", None))
    metrics = ev_mod._compute_risk(
        raw_actions, top_k, ledger, signals, policy, active_mapping, exploration_offset,
    )
    return ev_mod.build_evaluation(metrics, top_k)


def _print_preflight_result(evaluation, force, top_k):
    """Print a human-readable pre-flight summary to stderr.

    Returns True when execution should proceed, False when it should abort.
    Never raises.
    """
    risk = evaluation.get("risk_level", "low_risk")
    collision_ratio = evaluation.get("collision_ratio", 0.0)
    unique_tasks = evaluation.get("unique_tasks", 0)

    if risk == "low_risk":
        return True

    level = risk.replace("_risk", "").upper()
    print(f"Planner configuration risk: {level}", file=sys.stderr)
    print(
        f"  collision_ratio: {collision_ratio:.2f}  "
        f"unique_tasks: {unique_tasks} / {top_k}",
        file=sys.stderr,
    )
    for reason in evaluation.get("reasons", []):
        print(f"  Reason: {reason}", file=sys.stderr)

    if risk == "moderate_risk":
        print("  WARNING: continuing with experiment run.", file=sys.stderr)
        return True

    # high_risk
    if force:
        print(
            "  WARNING: high risk override — --force is set, continuing.",
            file=sys.stderr,
        )
        return True

    print("  Use --force to run anyway.", file=sys.stderr)
    return False


def run_experiment(args, planner_main=None, risk_check_fn=None):
    """Execute the planner args.runs times and return aggregated results.

    Args:
        args:          Parsed CLI namespace (or any object with the same attrs).
        planner_main:  Optional callable used instead of the real planner main.
                       Accepts a list of argv strings.  Defaults to
                       scripts.claude_dynamic_planner_loop.main when None.
        risk_check_fn: Optional callable(args) → evaluation dict | None.
                       Defaults to _run_preflight_check.  Inject for testing.

    Returns:
        A dict with keys: run_count, envelope_paths, evaluation_summary.

    Raises:
        SystemExit(1) when the pre-flight check returns high_risk and
        args.force is not set.
    """
    # --- Pre-flight risk guardrail (v0.39) ---
    if risk_check_fn is None:
        risk_check_fn = _run_preflight_check
    evaluation = risk_check_fn(args)
    if evaluation is not None:
        top_k = getattr(args, "top_k", 3) or 3
        force = getattr(args, "force", False)
        if not _print_preflight_result(evaluation, force, top_k):
            raise SystemExit(1)

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


# ---------------------------------------------------------------------------
# Policy sweep helpers (v0.38)
# ---------------------------------------------------------------------------

# Ordered list of all experiment arg attributes.  Used to copy args safely
# regardless of whether the object uses instance or class-level defaults.
_ARGS_ATTRS = (
    "runs", "portfolio_state", "ledger", "policy", "top_k",
    "exploration_offset", "max_actions", "explain", "force", "output",
    "envelope_prefix", "mapping_override",
)


def _sweep_policy_filename(name):
    """Return deterministic policy filename for a named sweep entry."""
    return f"sweep_{name}_policy.json"


def _sweep_result_filename(name):
    """Return deterministic experiment result filename for a named sweep entry."""
    return f"sweep_{name}_experiment_results.json"


def _sweep_envelope_prefix(name):
    """Return deterministic envelope prefix for a named sweep entry."""
    return f"sweep_{name}_envelope"


def _materialize_sweep_policy(output_dir, entry):
    """Write the weights dict for *entry* to a policy JSON file.

    The file is written to *output_dir*/<sweep_policy_filename>.
    Returns the Path of the written file.
    """
    path = output_dir / _sweep_policy_filename(entry["name"])
    weights = entry.get("weights", {})
    path.write_text(
        json.dumps(weights, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def _copy_args(args):
    """Return a shallow copy of *args* containing only known experiment attrs."""
    obj = type("Args", (), {})()
    for attr in _ARGS_ATTRS:
        setattr(obj, attr, getattr(args, attr, None))
    return obj


def run_policy_sweep(sweep_entries, base_args, planner_main=None, risk_check_fn=None):
    """Execute the configured experiment for each policy sweep entry.

    For each entry in *sweep_entries*:
    - materialises a deterministic policy JSON file in the output directory
    - runs the experiment with that policy
    - writes a per-entry experiment result file

    Then writes a top-level aggregate file ``policy_sweep_results.json`` in
    the same output directory.

    Args:
        sweep_entries: list of dicts, each with keys ``name`` (str) and
                       ``weights`` (dict).
        base_args:     Namespace-like object with the same attrs as the args
                       passed to run_experiment (runs, top_k, etc.).
        planner_main:  Optional planner callable injected for testing.

    Returns:
        A dict with keys: sweep_count, entries, aggregate_path.
    """
    if planner_main is None:
        from scripts.claude_dynamic_planner_loop import main as planner_main  # noqa: PLC0415

    output_dir = Path(base_args.output).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    entries = []
    for entry in sweep_entries:
        name = entry["name"]
        weights = entry.get("weights", {})

        policy_path = _materialize_sweep_policy(output_dir, entry)

        sweep_args = _copy_args(base_args)
        sweep_args.policy = str(policy_path)
        sweep_args.output = str(output_dir / _sweep_result_filename(name))
        sweep_args.envelope_prefix = _sweep_envelope_prefix(name)

        result = run_experiment(sweep_args, planner_main=planner_main,
                                risk_check_fn=risk_check_fn)

        entries.append({
            "name": name,
            "weights": weights,
            "experiment_results_path": sweep_args.output,
            "evaluation_summary": result["evaluation_summary"],
            "run_envelope_paths": result["envelope_paths"],
        })

    aggregate = {
        "sweep_count": len(entries),
        "entries": entries,
    }
    aggregate_path = output_dir / "policy_sweep_results.json"
    aggregate_path.write_text(
        json.dumps(aggregate, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "sweep_count": len(entries),
        "entries": entries,
        "aggregate_path": str(aggregate_path),
    }


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
    parser.add_argument("--force", action="store_true", default=False,
                        help="Run even when the pre-flight risk check returns high_risk.")
    args = parser.parse_args(argv)

    config = {}
    if args.config is not None:
        config = _load_config(args.config)

    _apply_config(args, config)

    if args.runs < 1:
        parser.error("--runs must be at least 1.")

    sweep = config.get("policy_sweep") or []
    if sweep:
        result = run_policy_sweep(sweep, args)
        sys.stdout.write(
            f"Policy sweep complete: {result['sweep_count']} entry(s), "
            f"aggregate at {result['aggregate_path']}\n"
        )
    else:
        result = run_experiment(args)
        sys.stdout.write(
            f"Experiment complete: {result['run_count']} run(s), "
            f"identical={result['evaluation_summary']['identical']}, "
            f"results at {args.output}\n"
        )


if __name__ == "__main__":
    main()
