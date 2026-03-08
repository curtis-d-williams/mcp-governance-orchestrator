"""
Dynamic Planner-Driven Claude Loop
Selects and submits Tier-3 tasks in real-time with prioritization.
Logs execution, aggregates results, and ensures deterministic outputs.

When --portfolio-state is supplied the loop fetches a prioritized action queue
from list_portfolio_actions.py and maps actions to tasks. When that path is
absent, or when the queue is empty / all actions are unmapped, it falls back to
the deterministic ALL_TASKS ordering.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Paths and manifest
MANIFEST_FILE = "portfolio_repos_example.json"
PORTFOLIO_CSV = Path("tier3_portfolio_report.csv")
AGGREGATE_JSON = Path("tier3_multi_run_aggregate.json")
LOG_FILE = Path("tier3_execution.log")
DEFAULT_PORTFOLIO_STATE_OUTPUT = Path("portfolio_state.json")

# Available Tier-3 tasks
ALL_TASKS = [
    "build_portfolio_dashboard",
    "repo_insights_example",
    "intelligence_layer_example"
]

# Deterministic mapping from portfolio action_type → Tier-3 task name.
ACTION_TO_TASK = {
    "refresh_repo_health": "repo_insights_example",
    "regenerate_missing_artifact": "build_portfolio_dashboard",
    "rerun_failed_task": "repo_insights_example",
    "run_determinism_regression_suite": "intelligence_layer_example",
}

# ---------------------------------------------------------------------------
# v0.26: Planner learning adjustment constants
# ---------------------------------------------------------------------------

EFFECTIVENESS_WEIGHT = 0.15
EFFECTIVENESS_CLAMP = 0.20

SIGNAL_IMPACT_WEIGHT = 0.05
SIGNAL_IMPACT_CLAMP = 0.15

# ---------------------------------------------------------------------------
# v0.27: Weak-signal targeting constants
# ---------------------------------------------------------------------------

TARGETING_WEIGHT = 0.10
TARGETING_CLAMP = 0.20

# ---------------------------------------------------------------------------
# v0.28: Confidence weighting constants
# ---------------------------------------------------------------------------

CONFIDENCE_THRESHOLD = 5.0

# ---------------------------------------------------------------------------
# v0.29: Uncertainty-driven exploration constants
# ---------------------------------------------------------------------------

EXPLORATION_WEIGHT = 0.05
EXPLORATION_CLAMP = 0.10


# ---------------------------------------------------------------------------
# v0.26: Ledger loading and learning adjustment helpers
# ---------------------------------------------------------------------------

def load_effectiveness_ledger(path):
    """Load ledger JSON and return {action_type: row_dict}.

    Returns an empty dict when:
    - path is None
    - file does not exist (fail-safe)
    - file is unreadable or malformed
    Never raises.
    """
    if path is None:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        rows = data.get("action_types", [])
        return {
            row["action_type"]: row
            for row in rows
            if isinstance(row, dict) and isinstance(row.get("action_type"), str)
        }
    except Exception:
        return {}


def compute_confidence_factor(action_type, ledger):
    """Return a confidence factor in [0.0, 1.0] based on times_executed.

    Logic:
    - action_type absent from ledger → 0.0
    - times_executed key absent from row → 1.0 (backward-compat: legacy entries
      without the field retain full learning effect)
    - invalid (non-numeric) or negative times_executed → 0.0
    - otherwise: min(1.0, times_executed / CONFIDENCE_THRESHOLD)

    Never raises.
    """
    row = ledger.get(action_type)
    if row is None:
        return 0.0
    if "times_executed" not in row:
        return 1.0  # backward-compat: field absent → full confidence
    try:
        te = float(row["times_executed"])
    except (TypeError, ValueError):
        return 0.0
    if te < 0:
        return 0.0
    return min(1.0, te / CONFIDENCE_THRESHOLD)


def compute_learning_adjustment(action_type, ledger):
    """Return the total learning priority adjustment for action_type.

    effectiveness_adj = clamp(effectiveness_score * EFFECTIVENESS_WEIGHT,
                              0.0, EFFECTIVENESS_CLAMP)
    signal_delta_adj  = clamp(sum(abs(effect_deltas)) * SIGNAL_IMPACT_WEIGHT,
                              0.0, SIGNAL_IMPACT_CLAMP)

    Returns 0.0 when action_type is absent from ledger.
    """
    row = ledger.get(action_type, {})

    effectiveness_score = float(row.get("effectiveness_score", 0.0))
    effectiveness_adj = min(
        max(0.0, effectiveness_score * EFFECTIVENESS_WEIGHT),
        EFFECTIVENESS_CLAMP,
    )

    effect_deltas = row.get("effect_deltas", {})
    signal_impact = sum(abs(v) for v in effect_deltas.values()) if effect_deltas else 0.0
    signal_delta_adj = min(
        max(0.0, signal_impact * SIGNAL_IMPACT_WEIGHT),
        SIGNAL_IMPACT_CLAMP,
    )

    return effectiveness_adj + signal_delta_adj


def load_portfolio_signals(portfolio_state_path):
    """Load portfolio-level signal averages from portfolio_state.json.

    Returns {signal_name: float_value} where values are averaged across all
    repos. Non-numeric (e.g. boolean) signal values are ignored.

    Returns {} when:
    - path is None
    - file does not exist (fail-safe)
    - file is unreadable or malformed
    Never raises.
    """
    if portfolio_state_path is None:
        return {}
    p = Path(portfolio_state_path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        repos = data.get("repos", [])
        totals = {}
        counts = {}
        for repo in repos:
            for name, value in repo.get("signals", {}).items():
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    continue
                totals[name] = totals.get(name, 0.0) + float(value)
                counts[name] = counts.get(name, 0) + 1
        return {name: totals[name] / counts[name] for name in totals}
    except Exception:
        return {}


def compute_weak_signal_targeting_adjustment(action_type, ledger, current_signals):
    """Return weak-signal targeting priority adjustment for action_type.

    weakness(signal) = max(0.0, 1.0 - signal_value)
    targeting_score  = sum(max(0.0, delta) * weakness
                           for each signal in effect_deltas)
    adjustment       = clamp(targeting_score * TARGETING_WEIGHT, ±TARGETING_CLAMP)

    Returns 0.0 when:
    - current_signals is empty
    - action_type is absent from ledger
    - effect_deltas is empty or no matching signals in current_signals
    - all deltas are non-positive
    """
    if not current_signals:
        return 0.0
    row = ledger.get(action_type, {})
    if not row:
        return 0.0
    effect_deltas = row.get("effect_deltas", {})
    if not effect_deltas:
        return 0.0
    targeting_score = sum(
        max(0.0, float(delta)) * max(0.0, 1.0 - current_signals[sig])
        for sig, delta in effect_deltas.items()
        if sig in current_signals
    )
    return max(-TARGETING_CLAMP, min(TARGETING_CLAMP, targeting_score * TARGETING_WEIGHT))


def compute_exploration_bonus(action_type, ledger):
    """Return a deterministic exploration bonus for action_type.

    uncertainty = 1 / (1 + times_executed)
    bonus       = clamp(uncertainty * EXPLORATION_WEIGHT, ±EXPLORATION_CLAMP)

    Missing ledger entry assumes times_executed = 0 (maximum uncertainty).
    Missing times_executed field in an existing row assumes times_executed = 0.
    Invalid (non-numeric) or negative times_executed assumes times_executed = 0.
    Never raises.
    """
    row = ledger.get(action_type)
    if row is None:
        times_executed = 0
    else:
        te_raw = row.get("times_executed", 0)
        try:
            te = float(te_raw)
        except (TypeError, ValueError):
            te = 0.0
        times_executed = max(0.0, te)

    uncertainty = 1.0 / (1.0 + times_executed)
    bonus = uncertainty * EXPLORATION_WEIGHT
    return max(-EXPLORATION_CLAMP, min(EXPLORATION_CLAMP, bonus))


def _apply_learning_adjustments(actions, ledger, current_signals=None):
    """Re-sort actions by base_priority + learning_adjustment (deterministic).

    Returns the original list unchanged when ledger is empty.
    Tiebreaker order: action_type asc, action_id asc, repo_id asc.

    current_signals: optional {signal_name: float} portfolio signal averages
        (v0.27). When absent or empty, targeting adjustment is zero and
        v0.26 behavior is preserved.
    """
    if not ledger:
        return actions

    _signals = current_signals or {}

    def _sort_key(a):
        at = a.get("action_type", "")
        confidence = compute_confidence_factor(at, ledger)
        adj = compute_learning_adjustment(at, ledger)
        targeting_adj = compute_weak_signal_targeting_adjustment(at, ledger, _signals)
        exploration_bonus = compute_exploration_bonus(at, ledger)
        learning_priority = (
            a.get("priority", 0.0)
            + confidence * (adj + targeting_adj)
            + exploration_bonus
        )
        return (
            -learning_priority,
            at,
            a.get("action_id", ""),
            a.get("repo_id", ""),
        )

    return sorted(actions, key=_sort_key)


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


def _map_actions_to_tasks(actions, top_k=1):
    """Map the first top_k actions to task names via ACTION_TO_TASK.

    Skips unmapped action types and de-duplicates while preserving first-
    occurrence order. Returns [] when no actions map to known tasks.
    """
    seen = set()
    tasks = []
    for action in actions[:top_k]:
        at = action.get("action_type", "")
        task = ACTION_TO_TASK.get(at)
        if task is None:
            continue
        if task not in seen:
            seen.add(task)
            tasks.append(task)
    return tasks


def _selected_mapped_actions(actions, top_k=1):
    """Return action dicts from actions[:top_k] whose action_type maps to a task.

    Mirrors _map_actions_to_tasks deduplication: skips subsequent actions that
    resolve to an already-selected task name. Preserves first-occurrence order.
    """
    seen_tasks = set()
    result = []
    for action in actions[:top_k]:
        at = action.get("action_type", "")
        task = ACTION_TO_TASK.get(at)
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
    parser.add_argument("--top-k", type=int, default=3, metavar="INT",
                        help="Number of top actions to consider (default: 3).")
    parser.add_argument("--exploration-offset", type=int, default=0, metavar="INT",
                        help="Start index into the action queue window (default: 0, clamped to valid range).")
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

    selected_actions = []
    if args.portfolio_state is not None:
        actions = _fetch_action_queue(args.portfolio_state, args.ledger)
        # v0.26: apply planner-side learning adjustment (no-op when ledger absent).
        # v0.27: load portfolio signals for weak-signal targeting (no-op when absent).
        planner_ledger = load_effectiveness_ledger(args.ledger)
        current_signals = load_portfolio_signals(args.portfolio_state)
        actions = _apply_learning_adjustments(actions, planner_ledger, current_signals)
        # Deterministic window: clamp offset so window always fits within the queue.
        start = max(0, min(args.exploration_offset, max(0, len(actions) - args.top_k)))
        end = start + args.top_k
        window_actions = actions[start:end]
        tasks_to_run = _map_actions_to_tasks(window_actions, args.top_k)
        if tasks_to_run:
            if args.capture_feedback:
                selected_actions = _selected_mapped_actions(window_actions, args.top_k)
            log(
                f"Planner using action-driven selection: "
                f"offset={start}, window={len(window_actions)}, "
                f"actions={[a.get('action_type') for a in window_actions]}, "
                f"tasks={tasks_to_run}"
            )
        else:
            log("Action queue empty or all actions unmapped — falling back to default task selection")
            tasks_to_run = prioritize_tasks()
    else:
        log("Planner using fallback task selection (no portfolio state provided)")
        tasks_to_run = prioritize_tasks()

    run_tasks(tasks_to_run, Path(args.portfolio_state_output))

    if args.capture_feedback:
        _write_executed_actions(args.executed_actions_output, selected_actions)
        _invoke_capture_feedback(args)


if __name__ == "__main__":
    main()
