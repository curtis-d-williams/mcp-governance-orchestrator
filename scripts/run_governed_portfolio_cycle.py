# SPDX-License-Identifier: MIT
"""Thin orchestration layer: one full governed portfolio cycle.

Executes three phases in sequence using existing scripts as black-box
subprocesses:

  1. Portfolio task phase  — run_portfolio_task.py
  2. Portfolio state phase — build_portfolio_state_from_artifacts.py
  3. Governed loop phase   — run_governed_planner_loop.py

Emits a single cycle artifact JSON to --output.

Usage:
    python3 scripts/run_governed_portfolio_cycle.py \\
        --manifest manifests/portfolio_manifest.json \\
        --task artifact_audit_example \\
        --task failure_recovery_example \\
        --output governed_portfolio_cycle.json

Exit codes:
    0  — cycle completed (governed planner executed)
    1  — cycle aborted (any phase failure)
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ---------------------------------------------------------------------------
# JSON output helper
# ---------------------------------------------------------------------------

def _write_json(path, data):
    """Write *data* as deterministic JSON (indent=2, sort_keys, trailing newline)."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Manifest validation helper
# ---------------------------------------------------------------------------

def _validate_manifest_repos(manifest_data):
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


# ---------------------------------------------------------------------------
# Artifact path helpers
# ---------------------------------------------------------------------------

def _work_dir(output_path):
    """Return the work directory path adjacent to *output_path*.

    Example:
        output_path = /tmp/governed_portfolio_cycle.json
        work_dir    = /tmp/governed_portfolio_cycle_artifacts/
    """
    p = Path(output_path)
    return p.parent / f"{p.stem}_artifacts"


def _artifact_paths(work_dir):
    """Return a dict of all expected artifact paths inside *work_dir*."""
    wd = Path(work_dir)
    return {
        "work_dir": str(wd),
        "report": str(wd / "tier3_portfolio_report.csv"),
        "aggregate": str(wd / "tier3_multi_run_aggregate.json"),
        "portfolio_state": str(wd / "portfolio_state.json"),
        "governed_result": str(wd / "governed_result.json"),
        "execution_result": str(wd / "execution_result.json"),
    }


# ---------------------------------------------------------------------------
# Phase runners
# ---------------------------------------------------------------------------

def _run_portfolio_tasks(tasks, manifest, work_dir):
    """Phase A: run run_portfolio_task.py with all tasks, cwd=work_dir.

    Returns the subprocess.CompletedProcess result.
    Raises subprocess.CalledProcessError on non-zero exit.
    """
    script = str(_REPO_ROOT / "scripts" / "run_portfolio_task.py")
    cmd = ["python3", script] + list(tasks) + [str(manifest)]
    return subprocess.run(
        cmd,
        cwd=str(work_dir),
        capture_output=True,
        text=True,
        check=True,
    )


def _run_build_portfolio_state(artifacts):
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


def _run_governed_loop(artifacts, args):
    """Phase C: run the governed planner loop.

    Returns the subprocess.CompletedProcess result.
    Raises subprocess.CalledProcessError on non-zero exit.
    """
    script = str(_REPO_ROOT / "scripts" / "run_governed_planner_loop.py")
    cmd = [
        "python3", script,
        "--portfolio-state", artifacts["portfolio_state"],
        "--output", artifacts["governed_result"],
        "--top-k", str(args.top_k),
        "--exploration-offset", str(args.exploration_offset),
    ]
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
    return subprocess.run(cmd, capture_output=True, text=True, check=True)


def _run_execute_governed_actions(artifacts, manifest):
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


# ---------------------------------------------------------------------------
# Artifact readers
# ---------------------------------------------------------------------------

def _try_parse_json(text):
    """Return parsed JSON from *text*, or None on any parse failure."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def _try_read_json(path):
    """Return parsed JSON from *path* if it exists, else None."""
    p = Path(path)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    return None


# ---------------------------------------------------------------------------
# Main cycle runner
# ---------------------------------------------------------------------------

def run_cycle(args):
    """Execute the full governed portfolio cycle.

    Args:
        args: Parsed argparse namespace.

    Returns:
        0 on success, 1 on any failure.
    """
    manifest = Path(args.manifest)

    # Validate manifest.
    try:
        manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"error: cannot read manifest: {exc}\n")
        return 1

    if not isinstance(manifest_data.get("repos"), list):
        sys.stderr.write("error: manifest must contain 'repos' as a list\n")
        return 1

    invalid_repos = _validate_manifest_repos(manifest_data)
    if invalid_repos:
        _write_json(args.output, {
            "status": "aborted",
            "phase": "manifest_validation",
            "manifest": str(manifest),
            "invalid_repos": invalid_repos,
        })
        return 1

    wd = _work_dir(args.output)
    wd.mkdir(parents=True, exist_ok=True)
    artifacts = _artifact_paths(wd)

    base_artifact = {
        "manifest": str(manifest),
        "tasks": list(args.task),
        "artifacts": artifacts,
        "portfolio_task_summary": None,
        "portfolio_state": None,
        "governed_result": None,
        "execution_result": None,
    }

    # --- Phase A: portfolio tasks ---
    try:
        proc_a = _run_portfolio_tasks(args.task, manifest, wd)
    except subprocess.CalledProcessError as exc:
        cycle = {
            **base_artifact,
            "status": "aborted",
            "phase": "portfolio_task",
            "stdout": exc.stdout,
            "stderr": exc.stderr,
        }
        _write_json(args.output, cycle)
        return 1

    portfolio_task_summary = _try_parse_json(proc_a.stdout)

    # --- Phase B: build portfolio state ---
    try:
        _run_build_portfolio_state(artifacts)
    except subprocess.CalledProcessError as exc:
        cycle = {
            **base_artifact,
            "status": "aborted",
            "phase": "portfolio_state",
            "portfolio_task_summary": portfolio_task_summary,
            "stdout": exc.stdout,
            "stderr": exc.stderr,
        }
        _write_json(args.output, cycle)
        return 1

    portfolio_state = _try_read_json(artifacts["portfolio_state"])

    # --- Phase C: governed planner loop ---
    governed_result = None
    try:
        _run_governed_loop(artifacts, args)
    except subprocess.CalledProcessError:
        governed_result = _try_read_json(artifacts["governed_result"])
        cycle = {
            **base_artifact,
            "status": "aborted",
            "phase": "governed_loop",
            "portfolio_task_summary": portfolio_task_summary,
            "portfolio_state": portfolio_state,
            "governed_result": governed_result,
        }
        _write_json(args.output, cycle)
        return 1

    governed_result = _try_read_json(artifacts["governed_result"])

    # --- Phase D: governed execution ---
    try:
        _run_execute_governed_actions(artifacts, manifest)
    except subprocess.CalledProcessError:
        execution_result = _try_read_json(artifacts["execution_result"])
        cycle = {
            **base_artifact,
            "status": "aborted",
            "phase": "governed_execution",
            "portfolio_task_summary": portfolio_task_summary,
            "portfolio_state": portfolio_state,
            "governed_result": governed_result,
            "execution_result": execution_result,
        }
        _write_json(args.output, cycle)
        return 1

    execution_result = _try_read_json(artifacts["execution_result"])
    cycle = {
        **base_artifact,
        "status": "ok",
        "portfolio_task_summary": portfolio_task_summary,
        "portfolio_state": portfolio_state,
        "governed_result": governed_result,
        "execution_result": execution_result,
    }
    _write_json(args.output, cycle)
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run a full governed portfolio cycle.",
        add_help=True,
    )
    parser.add_argument("--manifest", required=True, metavar="FILE",
                        help="Path to portfolio manifest JSON.")
    parser.add_argument("--task", action="append", required=True, metavar="TASK",
                        help="Task name to run (repeatable; at least one required).")
    parser.add_argument("--output", required=True, metavar="FILE",
                        help="Output path for the cycle artifact JSON.")
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

    args = parser.parse_args(argv)
    sys.exit(run_cycle(args))


if __name__ == "__main__":
    main()
