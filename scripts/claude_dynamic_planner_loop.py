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
        tasks_to_run = _map_actions_to_tasks(actions, args.top_k)
        if tasks_to_run:
            if args.capture_feedback:
                selected_actions = _selected_mapped_actions(actions, args.top_k)
            log(
                f"Planner using action-driven selection: "
                f"actions={[a.get('action_type') for a in actions[:args.top_k]]}, "
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
