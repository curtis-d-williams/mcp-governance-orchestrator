"""
Dynamic Planner-Driven Claude Loop
Selects and submits Tier-3 tasks in real-time with prioritization.
Logs execution, aggregates results, and ensures deterministic outputs.

When --portfolio-state is supplied the loop fetches a prioritized action queue
from list_portfolio_actions.py and maps actions to tasks. When that path is
absent, or when the queue is empty / all actions are unmapped, it falls back to
the deterministic ALL_TASKS ordering.

v0.35: --run-envelope writes a deterministic JSON envelope describing the run.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Ensure the repo root is on sys.path so `from scripts.*` imports work
# whether the script is invoked directly (python3 scripts/this.py) or
# imported via importlib from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ---------------------------------------------------------------------------
# v0.33: Pure scoring logic lives in planner_scoring; re-exported here for
# backward compatibility so all existing imports from this module still work.
# ---------------------------------------------------------------------------
from scripts.planner_scoring import (  # noqa: F401
    CONFIDENCE_THRESHOLD,
    EFFECTIVENESS_CLAMP,
    EFFECTIVENESS_WEIGHT,
    EXPLORATION_CLAMP,
    EXPLORATION_WEIGHT,
    POLICY_TOTAL_ABS_CAP,
    POLICY_WEIGHT_CLAMP,
    SIGNAL_IMPACT_CLAMP,
    SIGNAL_IMPACT_WEIGHT,
    TARGETING_CLAMP,
    TARGETING_WEIGHT,
    PriorityBreakdown,
    _apply_learning_adjustments,
    _build_priority_breakdown,
    _build_scoring_metrics,
    _compute_priority_breakdown,
    compute_confidence_factor,
    compute_exploration_bonus,
    compute_learning_adjustment,
    compute_policy_adjustment,
    compute_weak_signal_targeting_adjustment,
    load_effectiveness_ledger,
    load_planner_policy,
    load_portfolio_signals,
)

# v0.36: version constant for run envelopes
PLANNER_VERSION = "0.36"

# Paths and manifest
MANIFEST_FILE = "portfolio_repos_example.json"
PORTFOLIO_CSV = Path("tier3_portfolio_report.csv")
AGGREGATE_JSON = Path("tier3_multi_run_aggregate.json")
LOG_FILE = Path("tier3_execution.log")
DEFAULT_PORTFOLIO_STATE_OUTPUT = Path("portfolio_state.json")

# Available Tier-3 tasks (must match TASK_REGISTRY in agent_tasks/registry.py)
ALL_TASKS = [
    "artifact_audit_example",
    "build_portfolio_dashboard",
    "failure_recovery_example",
    "planner_determinism_example",
    "repo_insights_example",
]

# Deterministic mapping from portfolio action_type → Tier-3 task name.
# All entries must reference tasks present in TASK_REGISTRY.
ACTION_TO_TASK = {
    "refresh_repo_health": "build_portfolio_dashboard",
    "regenerate_missing_artifact": "build_portfolio_dashboard",
    "rerun_failed_task": "build_portfolio_dashboard",
    "run_determinism_regression_suite": "build_portfolio_dashboard",
    "analyze_repo_insights": "repo_insights_example",
    "recover_failed_workflow": "failure_recovery_example",
    "build_mcp_server": "build_portfolio_dashboard",
    "build_capability_artifact": "build_portfolio_dashboard",
}

def resolve_action_to_task_mapping(default_mapping, mapping_override=None):
    """Return the active action→task mapping for a planner run.

    When mapping_override is None or empty, returns default_mapping unchanged.
    When mapping_override is a flat dict, returns it (complete replacement).
    When mapping_override is a structured dict with "by_action_id"/"by_action_type"
    keys, returns a flat mapping: default_mapping merged with by_action_type entries.
    (Instance-level by_action_id resolution requires resolve_task_for_action.)
    This function is pure and deterministic.

    Args:
        default_mapping:  The default ACTION_TO_TASK dict.
        mapping_override: Optional dict from an experiment config.

    Returns:
        A flat dict mapping action_type strings to task name strings.
    """
    if not mapping_override:
        return default_mapping
    if "by_action_id" in mapping_override or "by_action_type" in mapping_override:
        flat = dict(default_mapping)
        flat.update(mapping_override.get("by_action_type", {}))
        return flat
    return dict(mapping_override)


def resolve_task_for_action(action, mapping_override, default_mapping):
    """Resolve the task name for a single action dict, instance-aware.

    Resolution precedence:
    1. mapping_override["by_action_id"][action_id]  (structured override)
    2. mapping_override["by_action_type"][action_type]  (structured override)
    3. mapping_override[action_type]  (flat override, backward compat)
    4. default_mapping[action_type]  (structured overrides only; not flat)

    For flat overrides (no "by_action_id"/"by_action_type" keys) the override
    completely replaces the default mapping — unmapped actions return None.
    This function is pure and deterministic.

    Args:
        action:          Single action dict with "action_id" and "action_type".
        mapping_override: Raw override dict (flat or structured), or None.
        default_mapping: Flat {action_type: task} dict used as fallback.

    Returns:
        Task name string, or None when the action is unmapped.
    """
    action_type = action.get("action_type", "")
    if not mapping_override:
        return default_mapping.get(action_type)
    if "by_action_id" in mapping_override or "by_action_type" in mapping_override:
        # Structured override — fall through to default_mapping when unmatched.
        action_id = action.get("action_id", "")
        by_id = mapping_override.get("by_action_id", {})
        by_type = mapping_override.get("by_action_type", {})
        if action_id and action_id in by_id:
            return by_id[action_id]
        if action_type in by_type:
            return by_type[action_type]
        return default_mapping.get(action_type)
    # Flat override — replaces default mapping entirely (no fallthrough).
    return mapping_override.get(action_type)


def log(message):
    timestamp = datetime.now().isoformat()
    entry = f"[{timestamp}] {message}\n"
    LOG_FILE.open("a").write(entry)
    print(entry, end="")


def prioritize_tasks(previous_results=None):
    """
    Simple placeholder prioritization.
    Can be extended to prioritize based on past metrics or outputs.
    Currently returns ALL_TASKS in deterministic order.
    """
    return sorted(ALL_TASKS)


def _build_portfolio_state_from_current_artifacts(output_path):
    """
    Build portfolio_state.json from the current CSV + aggregate artifacts.

    Returns True on success, False on any failure. Never raises.
    """
    if not PORTFOLIO_CSV.exists():
        log("Skipping portfolio state build: portfolio CSV missing")
        return False
    if not AGGREGATE_JSON.exists():
        log("Skipping portfolio state build: aggregate JSON missing")
        return False

    cmd = [
        sys.executable,
        "scripts/build_portfolio_state_from_artifacts.py",
        "--report", str(PORTFOLIO_CSV),
        "--aggregate", str(AGGREGATE_JSON),
        "--output", str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        log(f"Portfolio state build failed (rc={result.returncode}): {stderr}")
        return False

    stdout = (result.stdout or "").strip()
    if stdout:
        log(stdout)
    log(f"Portfolio state exists: {output_path}")
    return True


def run_tasks(tasks, portfolio_state_output=DEFAULT_PORTFOLIO_STATE_OUTPUT):
    """
    Run a list of Tier-3 tasks through the portfolio runner safely.
    """
    if not tasks:
        log("No tasks to run")
        return
    cmd = ["python3", "scripts/run_portfolio_task.py", *tasks, MANIFEST_FILE]
    log(f"Running tasks: {tasks}")
    subprocess.run(cmd, check=True)
    log("Portfolio runner completed successfully")

    # Aggregate results
    cmd_agg = ["python3", "scripts/aggregate_multi_run_envelopes.py"]
    subprocess.run(cmd_agg, check=True)
    log("Aggregation completed successfully")

    # Log artifact existence
    if PORTFOLIO_CSV.exists():
        log(f"Portfolio CSV exists: {PORTFOLIO_CSV}")
    else:
        log("ERROR: Portfolio CSV missing!")

    if AGGREGATE_JSON.exists():
        log(f"Aggregate JSON exists: {AGGREGATE_JSON}")
    else:
        log("WARNING: Aggregate JSON missing!")

    _build_portfolio_state_from_current_artifacts(portfolio_state_output)


# ---------------------------------------------------------------------------
# Action-queue helpers (additive — do not touch run_tasks / prioritize_tasks)
# ---------------------------------------------------------------------------

def _fetch_action_queue(portfolio_state_path, ledger_path=None):
    """Invoke list_portfolio_actions.py and return a parsed action list.

    Returns [] on any error so callers can fall back gracefully.
    """
    cmd = [
        sys.executable,
        "scripts/list_portfolio_actions.py",
        "--input", str(portfolio_state_path),
        "--json",
    ]
    if ledger_path is not None:
        cmd += ["--ledger", str(ledger_path)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            log(f"Action queue fetch failed (rc={result.returncode}): {result.stderr.strip()}")
            return []
        return json.loads(result.stdout)
    except Exception as exc:
        log(f"Action queue fetch error: {exc}")
        return []


def _map_actions_to_tasks(actions, top_k=1, action_to_task=None, mapping_override=None):
    """Map the first top_k actions to task names via the active mapping.

    Skips unmapped action types and de-duplicates while preserving first-
    occurrence order. Returns [] when no actions map to known tasks.

    When mapping_override is provided, uses resolve_task_for_action for
    instance-aware resolution (supports by_action_id in structured overrides).

    Args:
        actions:         List of action dicts (each with an action_type key).
        top_k:           Maximum number of actions to consider.
        action_to_task:  Active flat mapping dict. Defaults to ACTION_TO_TASK.
        mapping_override: Raw override dict (flat or structured), or None.
                          When set, resolve_task_for_action is used per action.
    """
    if action_to_task is None:
        action_to_task = ACTION_TO_TASK
    seen = set()
    tasks = []
    for action in actions[:top_k]:
        if mapping_override is not None:
            task = resolve_task_for_action(action, mapping_override, action_to_task)
        else:
            task = action_to_task.get(action.get("action_type", ""))
        if task is None:
            continue
        if task not in seen:
            seen.add(task)
            tasks.append(task)
    return tasks


def _selected_mapped_actions(actions, top_k=1, action_to_task=None, mapping_override=None):
    """Return action dicts from actions[:top_k] whose action_type maps to a task.

    Mirrors _map_actions_to_tasks deduplication: skips subsequent actions that
    resolve to an already-selected task name. Preserves first-occurrence order.

    When mapping_override is provided, uses resolve_task_for_action for
    instance-aware resolution (supports by_action_id in structured overrides).

    Args:
        actions:         List of action dicts (each with an action_type key).
        top_k:           Maximum number of actions to consider.
        action_to_task:  Active flat mapping dict. Defaults to ACTION_TO_TASK.
        mapping_override: Raw override dict (flat or structured), or None.
                          When set, resolve_task_for_action is used per action.
    """
    if action_to_task is None:
        action_to_task = ACTION_TO_TASK
    seen_tasks = set()
    result = []
    for action in actions[:top_k]:
        if mapping_override is not None:
            task = resolve_task_for_action(action, mapping_override, action_to_task)
        else:
            task = action_to_task.get(action.get("action_type", ""))
        if task is None:
            continue
        if task not in seen_tasks:
            seen_tasks.add(task)
            result.append(action)
    return result


def _write_executed_actions(path, actions):
    """Write selected executed actions as JSON. Creates parent dirs as needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(actions, indent=2) + "\n", encoding="utf-8")


def _invoke_capture_feedback(args):
    """Call capture_execution_feedback.py as a subprocess. Exits on failure."""
    cmd = [
        sys.executable,
        "scripts/capture_execution_feedback.py",
        "--before-source", args.portfolio_state,
        "--report", str(PORTFOLIO_CSV),
        "--aggregate", str(AGGREGATE_JSON),
        "--executed-actions", args.executed_actions_output,
        "--before-output", args.feedback_before_output,
        "--after-output", args.feedback_after_output,
        "--evaluation-output", args.evaluation_output,
        "--ledger-output", args.ledger_output,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    stdout = (result.stdout or "").strip()
    if stdout:
        log(stdout)
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        log(f"Feedback capture failed (rc={result.returncode}): {stderr}")
        sys.exit(result.returncode)
    log("Feedback capture completed")


# ---------------------------------------------------------------------------
# v0.34: Orchestration helpers
# ---------------------------------------------------------------------------

def load_runtime_context(args):
    """Load ledger, portfolio signals, and policy from CLI args.

    Returns (ledger, signals, policy) — all degrade safely to empty dicts
    when the corresponding files are absent or unreadable.
    """
    ledger = load_effectiveness_ledger(args.ledger)
    signals = load_portfolio_signals(args.portfolio_state)
    policy = load_planner_policy(args.policy)
    return ledger, signals, policy


def select_actions(args, raw_actions, ledger, signals, policy, mapping_override=None):
    """Apply ranking, compute exploration window, and map actions to tasks.

    Args:
        args:             parsed CLI namespace (reads top_k, exploration_offset).
        raw_actions:      unranked action list from _fetch_action_queue.
        ledger:           effectiveness ledger dict.
        signals:          portfolio signal averages dict.
        policy:           planner policy weight dict.
        mapping_override: optional dict overriding ACTION_TO_TASK for this run.
                          When None, ACTION_TO_TASK is used unchanged.

    Returns:
        (tasks_to_run, selected_action_dicts, sorted_actions)
        - tasks_to_run:           list of Tier-3 task names.
        - selected_action_dicts:  action dicts for feedback capture (empty
                                  when no tasks are mapped).
        - sorted_actions:         full ranked list (for explain artifact).
    """
    active_mapping = resolve_action_to_task_mapping(ACTION_TO_TASK, mapping_override)
    actions = _apply_learning_adjustments(raw_actions, ledger, signals, policy)
    start = max(0, min(args.exploration_offset, max(0, len(actions) - args.top_k)))
    end = start + args.top_k
    window = actions[start:end]
    tasks_to_run = _map_actions_to_tasks(
        window, args.top_k, action_to_task=active_mapping, mapping_override=mapping_override
    )
    selected_action_dicts = _selected_mapped_actions(
        window, args.top_k, action_to_task=active_mapping, mapping_override=mapping_override
    ) if tasks_to_run else []
    return tasks_to_run, selected_action_dicts, actions


def run_selected_actions(tasks, portfolio_state_output):
    """Delegate to run_tasks. Provided as an explicit orchestration entry point."""
    run_tasks(tasks, portfolio_state_output)


def write_explain_artifact(explain_actions, ledger, signals, policy):
    """Write explain-mode planner scoring artifacts.

    Read-only with respect to ranking — does not affect planner behavior.
    """
    breakdown = _build_priority_breakdown(explain_actions, ledger, signals, policy)
    Path("planner_priority_breakdown.json").write_text(
        json.dumps(breakdown, indent=2) + "\n", encoding="utf-8"
    )

    scoring_metrics = _build_scoring_metrics(explain_actions, ledger, signals, policy)
    Path("planner_scoring_metrics.json").write_text(
        json.dumps(scoring_metrics, indent=2) + "\n", encoding="utf-8"
    )

    log(f"Explain mode: wrote planner_priority_breakdown.json ({len(breakdown)} entries)")
    log(
        "Explain mode: wrote planner_scoring_metrics.json "
        f"({len(scoring_metrics.get('actions', []))} entries)"
    )


# ---------------------------------------------------------------------------
# v0.35: Run envelope
# ---------------------------------------------------------------------------

_EXPLAIN_ARTIFACT_NAME = "planner_priority_breakdown.json"


def write_run_envelope(path, args, tasks_to_run, explain_artifact_path=None,
                       ranked_action_window=None, action_task_collapse_count=None,
                       active_action_to_task_mapping=None):
    """Write a deterministic JSON envelope describing this planner run.

    Args:
        path:                        Destination file path (str or Path).
        args:                        Parsed CLI namespace.
        tasks_to_run:                Final list of task names selected for execution.
        explain_artifact_path:       Path to explain artifact if --explain was used,
                                     else None.
        ranked_action_window:        Ordered list of action_type strings from the
                                     exploration window used for task selection.
                                     Empty list when fallback mode was used.
        action_task_collapse_count:  Number of window actions that did not
                                     contribute a unique new task (due to
                                     action_type collision or unmapped type).
                                     0 when fallback mode was used.
        active_action_to_task_mapping: The mapping dict actually used for this run.
                                     Empty dict when not in action-driven mode.
                                     Additive — does not affect planner behavior.

    No-op if path is None. Creates parent directories as needed.
    Behavior is additive: calling this has no effect on planner ranking or
    task execution.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    envelope = {
        "planner_version": PLANNER_VERSION,
        "inputs": {
            "exploration_offset": getattr(args, "exploration_offset", 0),
            "explain": getattr(args, "explain", False),
            "ledger": getattr(args, "ledger", None),
            "max_actions": getattr(args, "max_actions", None),
            "policy": getattr(args, "policy", None),
            "portfolio_state": getattr(args, "portfolio_state", None),
            "top_k": getattr(args, "top_k", 3),
        },
        "selected_actions": list(tasks_to_run),
        "selection_count": len(tasks_to_run),
        "selection_detail": {
            "action_task_collapse_count": action_task_collapse_count if action_task_collapse_count is not None else 0,
            "active_action_to_task_mapping": dict(active_action_to_task_mapping) if active_action_to_task_mapping else {},
            "ranked_action_window": list(ranked_action_window) if ranked_action_window is not None else [],
        },
        "artifacts": {
            "explain_artifact": explain_artifact_path,
        },
        "execution": {
            "executed": True,
            "status": "ok",
        },
    }
    path.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Dynamic planner-driven Claude loop.",
        add_help=True,
    )
    parser.add_argument("--portfolio-state", default=None, metavar="FILE",
                        help="Path to portfolio_state.json for action-driven selection.")
    parser.add_argument("--ledger", default=None, metavar="FILE",
                        help="Path to action_effectiveness_ledger.json (optional).")
    parser.add_argument("--policy", default=None, metavar="FILE",
                        help="Path to planner_policy.json for governance signal weights (optional).")
    parser.add_argument("--top-k", type=int, default=3, metavar="INT",
                        help="Number of top actions to consider (default: 3).")
    parser.add_argument("--exploration-offset", type=int, default=0, metavar="INT",
                        help="Start index into the action queue window (default: 0, clamped to valid range).")
    parser.add_argument("--max-actions", type=int, default=None, metavar="INT",
                        help="Cap selected actions to at most this many (default: no cap). "
                             "When present, selected tasks are clamped to min(top_k, max_actions).")
    parser.add_argument("--portfolio-state-output", default=str(DEFAULT_PORTFOLIO_STATE_OUTPUT), metavar="FILE",
                        help="Destination path for post-run portfolio_state.json.")
    # Feedback capture (additive — disabled by default)
    parser.add_argument("--capture-feedback", action="store_true", default=False,
                        help="Enable execution feedback capture after task run.")
    parser.add_argument("--executed-actions-output", default=None, metavar="FILE",
                        help="Destination for executed_actions.json (requires --capture-feedback).")
    parser.add_argument("--feedback-before-output", default=None, metavar="FILE",
                        help="Destination for before-state snapshot (requires --capture-feedback).")
    parser.add_argument("--feedback-after-output", default=None, metavar="FILE",
                        help="Destination for after-state snapshot (requires --capture-feedback).")
    parser.add_argument("--evaluation-output", default=None, metavar="FILE",
                        help="Destination for evaluation_records.json (requires --capture-feedback).")
    parser.add_argument("--ledger-output", default=None, metavar="FILE",
                        help="Destination for action_effectiveness_ledger.json (requires --capture-feedback).")
    # v0.31: explainability flag
    parser.add_argument("--explain", action="store_true", default=False,
                        help="Write planner_priority_breakdown.json with per-action scoring components. "
                             "Read-only: does not affect ranking or planner behavior.")
    # v0.35: run envelope
    parser.add_argument("--run-envelope", default=None, metavar="FILE",
                        help="Write a deterministic JSON run envelope to this path. "
                             "Omitting this flag preserves default behavior unchanged.")
    # mapping override: experimental input, does not affect default behavior
    parser.add_argument("--mapping-override-json", default=None, metavar="JSON",
                        help="JSON string overriding the action→task mapping for this run. "
                             "When absent, ACTION_TO_TASK is used unchanged.")
    args = parser.parse_args(argv)

    # Fail closed: validate all required args when capture-feedback is enabled.
    if args.capture_feedback:
        missing = []
        if not args.portfolio_state:
            missing.append("--portfolio-state")
        if not args.executed_actions_output:
            missing.append("--executed-actions-output")
        if not args.feedback_before_output:
            missing.append("--feedback-before-output")
        if not args.feedback_after_output:
            missing.append("--feedback-after-output")
        if not args.evaluation_output:
            missing.append("--evaluation-output")
        if not args.ledger_output:
            missing.append("--ledger-output")
        if missing:
            parser.error(f"--capture-feedback requires: {', '.join(missing)}")

    # Parse mapping override JSON (fail closed on invalid JSON).
    _mapping_override = None
    if args.mapping_override_json:
        try:
            _mapping_override = json.loads(args.mapping_override_json)
        except json.JSONDecodeError as exc:
            parser.error(f"--mapping-override-json is not valid JSON: {exc}")

    selected_actions = []
    _explain_actions = []
    _explain_ledger = {}
    _explain_signals = {}
    _explain_policy = {}

    # v0.36: selection_detail — populated in action-driven mode, defaults for fallback.
    _action_window_types = []
    _action_task_collapse_count = 0
    _active_mapping = resolve_action_to_task_mapping(ACTION_TO_TASK, _mapping_override)

    if args.portfolio_state is not None:
        raw_actions = _fetch_action_queue(args.portfolio_state, args.ledger)
        _explain_ledger, _explain_signals, _explain_policy = load_runtime_context(args)
        tasks_to_run, action_dicts, _explain_actions = select_actions(
            args, raw_actions, _explain_ledger, _explain_signals, _explain_policy,
            mapping_override=_mapping_override,
        )
        # v0.36: compute window slice for selection_detail (additive, no ranking effect).
        _start = max(0, min(args.exploration_offset, max(0, len(_explain_actions) - args.top_k)))
        _window = _explain_actions[_start:_start + args.top_k]
        _action_window_types = [a.get("action_type", "") for a in _window]
        _action_task_collapse_count = len(_action_window_types) - len(tasks_to_run)
        if tasks_to_run:
            if args.capture_feedback:
                selected_actions = action_dicts
            log(
                f"Planner using action-driven selection: "
                f"offset={_start}, window={min(args.top_k, len(_explain_actions) - _start)}, "
                f"actions={_action_window_types}, "
                f"tasks={tasks_to_run}"
            )
        else:
            log("Action queue empty or all actions unmapped — falling back to default task selection")
            tasks_to_run = prioritize_tasks()
    else:
        log("Planner using fallback task selection (no portfolio state provided)")
        tasks_to_run = prioritize_tasks()

    # v0.34: optional runtime safety cap — deterministically limits selected actions.
    if args.max_actions is not None:
        tasks_to_run = tasks_to_run[:args.max_actions]

    # v0.35: record explain artifact path before writing, so envelope can reference it.
    _envelope_explain_path = None
    if args.explain:
        _envelope_explain_path = _EXPLAIN_ARTIFACT_NAME

    # v0.31: write explain artifact before running tasks (read-only, no ranking effect)
    if args.explain:
        write_explain_artifact(_explain_actions, _explain_ledger, _explain_signals, _explain_policy)

    run_selected_actions(tasks_to_run, Path(args.portfolio_state_output))

    # v0.35/v0.36: write run envelope (additive, no ranking effect)
    if args.run_envelope is not None:
        write_run_envelope(args.run_envelope, args, tasks_to_run,
                           explain_artifact_path=_envelope_explain_path,
                           ranked_action_window=_action_window_types,
                           action_task_collapse_count=_action_task_collapse_count,
                           active_action_to_task_mapping=_active_mapping if args.portfolio_state else {})

    if args.capture_feedback:
        _write_executed_actions(args.executed_actions_output, selected_actions)
        _invoke_capture_feedback(args)


if __name__ == "__main__":
    main()
