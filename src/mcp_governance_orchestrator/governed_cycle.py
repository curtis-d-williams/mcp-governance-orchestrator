# SPDX-License-Identifier: MIT
"""Reusable governed portfolio cycle orchestration primitives.

Extracted from scripts/run_governed_portfolio_cycle.py so that future phases
(e.g., Phase L governance enforcement) can compose or extend these helpers
without touching the CLI entrypoint.

Public API:
    DEFAULT_GOVERNANCE_POLICY
    write_json(path, data)
    validate_manifest_repos(manifest_data) -> list
    work_dir(output_path) -> Path
    artifact_paths(work_dir_path) -> dict
    try_parse_json(text) -> dict | None
    try_read_json(path) -> dict | None
    run_portfolio_tasks(tasks, manifest, work_dir_path) -> CompletedProcess
    run_build_portfolio_state(artifacts) -> CompletedProcess
    resolve_planner_ledger(ledger_arg, artifacts) -> (source, path)
    run_governed_loop(artifacts, top_k, exploration_offset, ...) -> CompletedProcess
    run_execute_governed_actions(artifacts, manifest) -> CompletedProcess
    run_update_execution_history(artifacts) -> CompletedProcess
    run_update_action_effectiveness_from_history(artifacts, mapping=None) -> CompletedProcess
    run_update_cycle_history(artifacts, cycle_artifact_path) -> CompletedProcess
    run_aggregate_cycle_history(artifacts) -> CompletedProcess
    run_detect_cycle_history_regression(artifacts) -> CompletedProcess
    run_enforce_governance_policy(artifacts, policy_file=None) -> CompletedProcess
    run_cycle(args) -> int
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _load_script(script_path, module_name):
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_cap_learn_mod = _load_script(
    _REPO_ROOT / "scripts" / "update_capability_effectiveness_ledger.py",
    "capability_learn",
)
update_capability_effectiveness_ledger = (
    _cap_learn_mod.update_capability_effectiveness_ledger
)

# Action-type → task mapping used by Phase F to derive action_types rows.
# Mirrors ACTION_TO_TASK in scripts/claude_dynamic_planner_loop.py.
# Must remain in sync with that definition when the planner mapping changes.
_ACTION_TO_TASK = {
    "analyze_repo_insights": "repo_insights_example",
    "build_capability_artifact": "build_mcp_server_example",
    "build_mcp_server": "build_mcp_server_example",
    "recover_failed_workflow": "failure_recovery_example",
    "refresh_repo_health": "build_portfolio_dashboard",
    "regenerate_missing_artifact": "build_portfolio_dashboard",
    "rerun_failed_task": "build_portfolio_dashboard",
    "run_determinism_regression_suite": "build_portfolio_dashboard",
}


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def write_json(path, data):
    """Write *data* as deterministic JSON (indent=2, sort_keys, trailing newline)."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def try_parse_json(text):
    """Return parsed JSON from *text*, or None on any parse failure."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def try_read_json(path):
    """Return parsed JSON from *path* if it exists, else None."""
    p = Path(path)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    return None


# ---------------------------------------------------------------------------
# Manifest validation
# ---------------------------------------------------------------------------

def validate_manifest_repos(manifest_data):
    """Return a list of invalid repo entries from *manifest_data*.

    A repo is invalid when:
    - it is missing an "id" key, OR
    - it is missing a "path" key, OR
    - its "path" does not exist on disk.

    Args:
        manifest_data: parsed manifest dict (caller ensures "repos" is a list).

    Returns:
        list of dicts, each with keys "id", "path", and "reason".
        Empty list means all repos are valid.
    """
    invalid = []
    for repo in manifest_data.get("repos", []):
        repo_id = repo.get("id", "")
        repo_path = repo.get("path", "")
        if not repo_id:
            invalid.append({"id": repo_id, "path": repo_path, "reason": "missing id"})
        elif not repo_path:
            invalid.append({"id": repo_id, "path": repo_path, "reason": "missing path"})
        elif not Path(repo_path).exists():
            invalid.append({"id": repo_id, "path": repo_path, "reason": "path does not exist"})
    return invalid


def write_effective_manifest(manifest_data, work_dir_path, repo_ids=None):
    """Write an effective manifest scoped to *repo_ids* if provided.

    Args:
        manifest_data: parsed manifest dict
        work_dir_path: output work dir path
        repo_ids:      list[str] | None

    Returns:
        Path to the effective manifest JSON written inside work_dir_path.
    """
    effective = dict(manifest_data)
    repos = list(manifest_data.get("repos", []))
    if repo_ids:
        repo_id_set = set(repo_ids)
        repos = [repo for repo in repos if repo.get("id") in repo_id_set]
    effective["repos"] = repos
    out_path = Path(work_dir_path) / "effective_portfolio_manifest.json"
    write_json(out_path, effective)
    return out_path


# ---------------------------------------------------------------------------
# Artifact path helpers
# ---------------------------------------------------------------------------

def work_dir(output_path):
    """Return the work directory path adjacent to *output_path*.

    Example:
        output_path = /tmp/governed_portfolio_cycle.json
        work_dir    = /tmp/governed_portfolio_cycle_artifacts/
    """
    p = Path(output_path)
    return p.parent / f"{p.stem}_artifacts"


def artifact_paths(work_dir_path):
    """Return a dict of all expected artifact paths inside *work_dir_path*."""
    wd = Path(work_dir_path)
    return {
        "work_dir": str(wd),
        "report": str(wd / "tier3_portfolio_report.csv"),
        "aggregate": str(wd / "tier3_multi_run_aggregate.json"),
        "portfolio_state": str(wd / "portfolio_state.json"),
        "governed_result": str(wd / "governed_result.json"),
        "execution_result": str(wd / "execution_result.json"),
        "execution_history": str(wd / "execution_history.json"),
        "action_effectiveness_ledger": str(wd / "action_effectiveness_ledger.json"),
        "cycle_history": str(wd / "cycle_history.json"),
        "cycle_history_summary": str(wd / "cycle_history_summary.json"),
        "cycle_history_regression": str(wd / "cycle_history_regression_report.json"),
        "governance_decision": str(wd / "governance_decision.json"),
        "capability_effectiveness_ledger": str(wd / "capability_effectiveness_ledger.json"),
    }


def build_runtime_config(args, ledger_path):
    """Construct a normalized runtime configuration object.

    This prevents configuration sprawl as the system scales
    (multi-repo portfolios, scheduler overrides, etc.).
    """
    return {
        "top_k": args.top_k,
        "exploration_offset": args.exploration_offset,
        "ledger_path": ledger_path,
        "planner_policy": args.policy,
        "max_actions": args.max_actions,
        "explain": args.explain,
        "force": args.force,
        "governance_policy": getattr(args, "governance_policy", None),
        "repo_ids": getattr(args, "repo_ids", None),
        "capability_ledger": getattr(args, "capability_ledger", None),
    }


# ---------------------------------------------------------------------------
# Default governance policy
# ---------------------------------------------------------------------------

DEFAULT_GOVERNANCE_POLICY = {
    "abort_on_signals": ["status_regressed"],
    "allow_if_only": ["action_set_changed"],
    "on_regression": "warn",
}


# ---------------------------------------------------------------------------
# Phase runners
# ---------------------------------------------------------------------------

def run_portfolio_tasks(tasks, manifest, work_dir_path):
    """Phase A: run run_portfolio_task.py with all tasks, cwd=work_dir_path.

    Returns the subprocess.CompletedProcess result.
    Raises subprocess.CalledProcessError on non-zero exit.
    """
    script = str(_REPO_ROOT / "scripts" / "run_portfolio_task.py")
    cmd = ["python3", script] + list(tasks) + [str(manifest)]
    return subprocess.run(
        cmd,
        cwd=str(work_dir_path),
        capture_output=True,
        text=True,
        check=True,
    )


def run_build_portfolio_state(artifacts):
    """Phase B: build portfolio_state.json from task artifacts.

    Returns the subprocess.CompletedProcess result.
    Raises subprocess.CalledProcessError on non-zero exit.
    """
    script = str(_REPO_ROOT / "scripts" / "build_portfolio_state_from_artifacts.py")
    cmd = [
        "python3", script,
        "--report", artifacts["report"],
        "--aggregate", artifacts["aggregate"],
        "--output", artifacts["portfolio_state"],
    ]
    return subprocess.run(cmd, capture_output=True, text=True, check=True)


def resolve_planner_ledger(ledger_arg, artifacts):
    """Determine which ledger file to pass to the governed planner loop.

    Precedence:
      1. Explicit ledger_arg value.
      2. Pre-existing work-dir action_effectiveness_ledger.json.
      3. No ledger.

    Args:
        ledger_arg: explicit ledger path from CLI (str or None).
        artifacts:  artifact paths dict from artifact_paths().

    Returns:
        (source, path) where source is "explicit" | "work_dir" | "none"
        and path is a str path or None.
    """
    if ledger_arg is not None:
        return "explicit", ledger_arg
    work_dir_ledger = artifacts["action_effectiveness_ledger"]
    if Path(work_dir_ledger).exists():
        return "work_dir", work_dir_ledger
    return "none", None


def run_governed_loop(
    artifacts,
    top_k,
    exploration_offset,
    ledger=None,
    capability_ledger=None,
    policy=None,
    max_actions=None,
    explain=False,
    force=False,
):
    """Phase C: run the governed planner loop.

    Returns the subprocess.CompletedProcess result.
    Raises subprocess.CalledProcessError on non-zero exit.
    """
    script = str(_REPO_ROOT / "scripts" / "run_governed_planner_loop.py")
    cmd = [
        "python3", script,
        "--portfolio-state", artifacts["portfolio_state"],
        "--output", artifacts["governed_result"],
        "--top-k", str(top_k),
        "--exploration-offset", str(exploration_offset),
    ]
    if ledger is not None:
        cmd += ["--ledger", ledger]
    if capability_ledger is not None:
        cmd += ["--capability-ledger", capability_ledger]
    if policy is not None:
        cmd += ["--policy", policy]
    if max_actions is not None:
        cmd += ["--max-actions", str(max_actions)]
    if explain:
        cmd.append("--explain")
    if force:
        cmd.append("--force")
    return subprocess.run(cmd, capture_output=True, text=True, check=True)


def run_execute_governed_actions(artifacts, manifest):
    """Phase D: execute the tasks selected by the governed planner loop.

    Returns the subprocess.CompletedProcess result.
    Raises subprocess.CalledProcessError on non-zero exit.
    """
    script = str(_REPO_ROOT / "scripts" / "execute_governed_actions.py")
    cmd = [
        "python3", script,
        "--governed-result", artifacts["governed_result"],
        "--manifest", str(manifest),
        "--output", artifacts["execution_result"],
    ]
    return subprocess.run(cmd, capture_output=True, text=True, check=True)


def run_update_execution_history(artifacts):
    """Phase E: append a normalized execution record to execution_history.json.

    Returns the subprocess.CompletedProcess result.
    Raises subprocess.CalledProcessError on non-zero exit.
    """
    script = str(_REPO_ROOT / "scripts" / "update_execution_history.py")
    cmd = [
        "python3", script,
        "--execution-result", artifacts["execution_result"],
        "--output", artifacts["execution_history"],
    ]
    return subprocess.run(cmd, capture_output=True, text=True, check=True)


def run_update_action_effectiveness_from_history(artifacts, mapping=None):
    """Phase F: aggregate action effectiveness from execution_history.json.

    When mapping is provided, passes --mapping-json so the script also
    derives an action_types array keyed by action_type, enabling downstream
    consumers (list_portfolio_actions, load_effectiveness_ledger) to resolve
    per-action-type effectiveness data.

    Returns the subprocess.CompletedProcess result.
    Raises subprocess.CalledProcessError on non-zero exit.
    """
    script = str(_REPO_ROOT / "scripts" / "update_action_effectiveness_from_history.py")
    cmd = [
        "python3", script,
        "--execution-history", artifacts["execution_history"],
        "--output", artifacts["action_effectiveness_ledger"],
    ]
    if mapping:
        cmd += ["--mapping-json", json.dumps(mapping, sort_keys=True)]
    return subprocess.run(cmd, capture_output=True, text=True, check=True)


def run_update_cycle_history(artifacts, cycle_artifact_path):
    """Phase I: append a normalized cycle record to cycle_history.json.

    Returns the subprocess.CompletedProcess result.
    Raises subprocess.CalledProcessError on non-zero exit.
    """
    script = str(_REPO_ROOT / "scripts" / "update_cycle_history.py")
    cmd = [
        "python3", script,
        "--cycle-artifact", cycle_artifact_path,
        "--output", artifacts["cycle_history"],
    ]
    return subprocess.run(cmd, capture_output=True, text=True, check=True)


def run_aggregate_cycle_history(artifacts):
    """Phase J: compute an aggregate summary from cycle_history.json.

    Returns the subprocess.CompletedProcess result.
    Raises subprocess.CalledProcessError on non-zero exit.
    """
    script = str(_REPO_ROOT / "scripts" / "aggregate_cycle_history.py")
    cmd = [
        "python3", script,
        "--history", artifacts["cycle_history"],
        "--output", artifacts["cycle_history_summary"],
    ]
    return subprocess.run(cmd, capture_output=True, text=True, check=True)


def run_detect_cycle_history_regression(artifacts):
    """Phase K: detect regressions in governed cycle history.

    Returns the subprocess.CompletedProcess result.
    Raises subprocess.CalledProcessError on non-zero exit.
    """
    script = str(_REPO_ROOT / "scripts" / "detect_cycle_history_regression.py")
    cmd = [
        "python3", script,
        "--history", artifacts["cycle_history"],
        "--summary", artifacts["cycle_history_summary"],
        "--output", artifacts["cycle_history_regression"],
    ]
    return subprocess.run(cmd, capture_output=True, text=True, check=True)


def run_enforce_governance_policy(artifacts, policy_file=None):
    """Phase L: evaluate governance policy against cycle history regression.

    If *policy_file* is None, writes DEFAULT_GOVERNANCE_POLICY to
    <work_dir>/_default_governance_policy.json and uses that path.

    Returns the subprocess.CompletedProcess result.
    Raises subprocess.CalledProcessError on non-zero exit.
    """
    if policy_file is None:
        default_path = Path(artifacts["work_dir"]) / "_default_governance_policy.json"
        write_json(default_path, DEFAULT_GOVERNANCE_POLICY)
        policy_file = str(default_path)
    script = str(_REPO_ROOT / "scripts" / "enforce_governance_policy.py")
    cmd = [
        "python3", script,
        "--history", artifacts["cycle_history"],
        "--summary", artifacts["cycle_history_summary"],
        "--policy", policy_file,
        "--output", artifacts["governance_decision"],
    ]
    return subprocess.run(cmd, capture_output=True, text=True, check=True)


# ---------------------------------------------------------------------------
# Main cycle runner
# ---------------------------------------------------------------------------

def run_cycle(args):
    """Execute the full governed portfolio cycle.

    Args:
        args: Parsed argparse namespace with attributes:
            manifest, task, output, ledger, policy, top_k,
            exploration_offset, max_actions, explain, force,
            governance_policy (optional, defaults to None).

    Returns:
        0 on success, 1 on any failure.
    """
    import sys as _sys

    manifest = Path(args.manifest).resolve()

    # Validate manifest.
    try:
        manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _sys.stderr.write(f"error: cannot read manifest: {exc}\n")
        return 1

    if not isinstance(manifest_data.get("repos"), list):
        _sys.stderr.write("error: manifest must contain 'repos' as a list\n")
        return 1

    invalid_repos = validate_manifest_repos(manifest_data)
    if invalid_repos:
        write_json(args.output, {
            "status": "aborted",
            "phase": "manifest_validation",
            "manifest": str(manifest),
            "invalid_repos": invalid_repos,
        })
        return 1

    wd = work_dir(args.output)
    wd.mkdir(parents=True, exist_ok=True)
    arts = artifact_paths(wd)

    repo_ids = getattr(args, "repo_ids", None)
    effective_manifest = (
        write_effective_manifest(manifest_data, wd, repo_ids=repo_ids).resolve()
        if repo_ids
        else manifest
    )

    base_artifact = {
        "manifest": str(manifest),
        "tasks": list(args.task),
        "artifacts": arts,
        "portfolio_task_summary": None,
        "portfolio_state": None,
        "governed_result": None,
        "execution_result": None,
        "execution_history": None,
        "action_effectiveness_ledger": None,
        "cycle_history": None,
        "cycle_history_summary": None,
        "cycle_history_regression": None,
        "governance_decision": None,
        "planner_inputs": None,
    }

    # --- Phase A: portfolio tasks ---
    try:
        proc_a = run_portfolio_tasks(args.task, effective_manifest, wd)
    except subprocess.CalledProcessError as exc:
        cycle = {
            **base_artifact,
            "status": "aborted",
            "phase": "portfolio_task",
            "stdout": exc.stdout,
            "stderr": exc.stderr,
        }
        write_json(args.output, cycle)
        return 1

    portfolio_task_summary = try_parse_json(proc_a.stdout)

    # --- Phase B: build portfolio state ---
    try:
        run_build_portfolio_state(arts)
    except subprocess.CalledProcessError as exc:
        cycle = {
            **base_artifact,
            "status": "aborted",
            "phase": "portfolio_state",
            "portfolio_task_summary": portfolio_task_summary,
            "stdout": exc.stdout,
            "stderr": exc.stderr,
        }
        write_json(args.output, cycle)
        return 1

    portfolio_state = try_read_json(arts["portfolio_state"])

    # Resolve which ledger the planner will consume (before Phase C writes its own).
    ledger_source, ledger_path = resolve_planner_ledger(args.ledger, arts)
    config = build_runtime_config(args, ledger_path)
    base_artifact["planner_inputs"] = {
        "ledger_path": ledger_path,
        "ledger_source": ledger_source,
    }

    # --- Phase C: governed planner loop ---
    governed_result = None
    try:
        run_governed_loop(
            arts,
            top_k=config["top_k"],
            exploration_offset=config["exploration_offset"],
            ledger=config["ledger_path"],
            capability_ledger=config["capability_ledger"],
            policy=config["planner_policy"],
            max_actions=config["max_actions"],
            explain=config["explain"],
            force=config["force"],
        )
    except subprocess.CalledProcessError:
        governed_result = try_read_json(arts["governed_result"])
        cycle = {
            **base_artifact,
            "status": "aborted",
            "phase": "governed_loop",
            "portfolio_task_summary": portfolio_task_summary,
            "portfolio_state": portfolio_state,
            "governed_result": governed_result,
        }
        write_json(args.output, cycle)
        return 1

    governed_result = try_read_json(arts["governed_result"])

    # Persist capability_effectiveness_ledger when a ledger path was provided
    if config.get("capability_ledger"):
        update_capability_effectiveness_ledger(
            ledger_path=config["capability_ledger"],
            cycle_artifact_path=arts["governed_result"],
            output_path=arts["capability_effectiveness_ledger"],
        )

    # --- Phase D: governed execution ---
    if governed_result and governed_result.get("idle") is True:
        execution_result = {
            "resolved_via": "no_action_window",
            "selected_tasks": [],
            "status": "ok",
        }
        write_json(arts["execution_result"], execution_result)
    else:
        try:
            run_execute_governed_actions(arts, effective_manifest)
        except subprocess.CalledProcessError:
            execution_result = try_read_json(arts["execution_result"])
            cycle = {
                **base_artifact,
                "status": "aborted",
                "phase": "governed_execution",
                "portfolio_task_summary": portfolio_task_summary,
                "portfolio_state": portfolio_state,
                "governed_result": governed_result,
                "execution_result": execution_result,
            }
            write_json(args.output, cycle)
            return 1

        execution_result = try_read_json(arts["execution_result"])

    # --- Phase E: execution history ---
    try:
        run_update_execution_history(arts)
    except subprocess.CalledProcessError:
        cycle = {
            **base_artifact,
            "status": "aborted",
            "phase": "execution_history",
            "portfolio_task_summary": portfolio_task_summary,
            "portfolio_state": portfolio_state,
            "governed_result": governed_result,
            "execution_result": execution_result,
        }
        write_json(args.output, cycle)
        return 1

    execution_history = try_read_json(arts["execution_history"])

    # --- Phase F: action effectiveness ---
    try:
        run_update_action_effectiveness_from_history(arts, mapping=_ACTION_TO_TASK)
    except subprocess.CalledProcessError:
        cycle = {
            **base_artifact,
            "status": "aborted",
            "phase": "action_effectiveness",
            "portfolio_task_summary": portfolio_task_summary,
            "portfolio_state": portfolio_state,
            "governed_result": governed_result,
            "execution_result": execution_result,
            "execution_history": execution_history,
        }
        write_json(args.output, cycle)
        return 1

    action_effectiveness_ledger = try_read_json(arts["action_effectiveness_ledger"])

    # Assemble tentative ok cycle artifact (staging write for Phase I to read).
    cycle = {
        **base_artifact,
        "status": "ok",
        "portfolio_task_summary": portfolio_task_summary,
        "portfolio_state": portfolio_state,
        "governed_result": governed_result,
        "execution_result": execution_result,
        "execution_history": execution_history,
        "action_effectiveness_ledger": action_effectiveness_ledger,
        "cycle_history": None,
        "cycle_history_summary": None,
        "cycle_history_regression": None,
        "governance_decision": None,
    }
    write_json(args.output, cycle)

    # --- Phase I: cycle history index ---
    try:
        run_update_cycle_history(arts, args.output)
    except subprocess.CalledProcessError:
        cycle = {**cycle, "status": "aborted", "phase": "cycle_history"}
        write_json(args.output, cycle)
        return 1

    cycle_history = try_read_json(arts["cycle_history"])
    cycle["cycle_history"] = cycle_history

    # --- Phase J: cycle history aggregation ---
    try:
        run_aggregate_cycle_history(arts)
    except subprocess.CalledProcessError:
        cycle = {**cycle, "status": "aborted", "phase": "cycle_history_summary"}
        write_json(args.output, cycle)
        return 1

    cycle_history_summary = try_read_json(arts["cycle_history_summary"])

    # --- Phase K: cycle history regression detection ---
    try:
        run_detect_cycle_history_regression(arts)
    except subprocess.CalledProcessError:
        cycle = {
            **cycle,
            "status": "aborted",
            "phase": "cycle_history_regression",
            "cycle_history_summary": cycle_history_summary,
        }
        write_json(args.output, cycle)
        return 1

    cycle_history_regression = try_read_json(arts["cycle_history_regression"])

    # --- Phase L: governance policy enforcement ---
    try:
        run_enforce_governance_policy(arts, config["governance_policy"])
    except subprocess.CalledProcessError:
        cycle = {
            **cycle,
            "status": "aborted",
            "phase": "governance_enforcement",
            "cycle_history_summary": cycle_history_summary,
            "cycle_history_regression": cycle_history_regression,
        }
        write_json(args.output, cycle)
        return 1

    governance_decision = try_read_json(arts["governance_decision"])

    # Final artifact: governance_decision is an assessment artifact.
    # cycle status reflects actual orchestration success, not governance outcome.
    cycle["cycle_history_summary"] = cycle_history_summary
    cycle["cycle_history_regression"] = cycle_history_regression
    cycle["governance_decision"] = governance_decision
    write_json(args.output, cycle)
    return 0
