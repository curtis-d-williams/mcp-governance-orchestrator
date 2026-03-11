# SPDX-License-Identifier: MIT
"""Shared runtime for portfolio governance planning and execution."""

import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent
_GOVERNED_CYCLE_SCRIPT = _REPO_ROOT / "scripts" / "run_governed_portfolio_cycle.py"


def _write_json(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json_if_exists(path):
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _repo_summary_path(output_dir, repo_id):
    return Path(output_dir) / repo_id / "summary.json"


def _repo_summary_history_path(output_dir, repo_id):
    return Path(output_dir) / repo_id / "summary_history.json"


def _load_summary_history(output_dir, repo_id):
    data = _load_json_if_exists(_repo_summary_history_path(output_dir, repo_id))
    if isinstance(data, list):
        return data
    return []


def _latest_summary_record(summary, summary_history):
    if summary_history:
        latest = sorted(summary_history, key=lambda r: r.get("timestamp") or "")[-1]
        if isinstance(latest, dict):
            return latest
    return summary if isinstance(summary, dict) else None


def _is_budget_exempt(latest_record):
    if not isinstance(latest_record, dict):
        return False
    if latest_record.get("governance_decision") == "abort":
        return True
    if bool(latest_record.get("regression_detected")):
        return True
    return False


def _attention_priority(summary, latest_record):
    if _is_budget_exempt(latest_record):
        return (-1, 0)

    if summary is None:
        return (5, 0)

    alert_level = summary.get("alert_level")
    governance_decision = summary.get("governance_decision")

    if alert_level == "critical":
        return (0, 0)
    if alert_level == "warning":
        return (1, 0)
    if governance_decision == "abort":
        return (2, 0)
    if governance_decision == "warn":
        return (3, 0)
    return (4, 0)


def build_plan(manifest_path, output_dir, max_repos_per_cycle=None):
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    repos = manifest.get("repos", [])

    provisional = []

    for repo in repos:
        repo_id = repo.get("id")
        if not repo_id:
            continue

        summary = _load_json_if_exists(_repo_summary_path(output_dir, repo_id))
        summary_history = _load_summary_history(output_dir, repo_id)
        latest_record = _latest_summary_record(summary, summary_history)

        if summary is None:
            enabled = True
            reason = "no_prior_run"
        elif (
            summary.get("alert_level") == "none"
            and summary.get("governance_decision") == "continue"
        ):
            enabled = False
            reason = "stable_continue_last_cycle"
        else:
            enabled = True
            reason = "prior_attention_signal"

        provisional.append({
            "enabled": enabled,
            "reason": reason,
            "repo_id": repo_id,
            "_budget_exempt": _is_budget_exempt(latest_record),
            "_priority": _attention_priority(summary, latest_record),
        })

    if max_repos_per_cycle is not None:
        exempt_enabled_count = sum(
            1 for repo in provisional
            if repo["enabled"] and repo["_budget_exempt"]
        )
        remaining_budget = max(0, max_repos_per_cycle - exempt_enabled_count)

        attention_candidates = sorted(
            [
                repo for repo in provisional
                if repo["enabled"]
                and not repo["_budget_exempt"]
                and repo["reason"] in ("prior_attention_signal", "no_prior_run")
            ],
            key=lambda repo: (repo["_priority"], repo["repo_id"]),
        )
        allowed_repo_ids = {
            repo["repo_id"] for repo in attention_candidates[:remaining_budget]
        }

        for repo in provisional:
            if (
                repo["enabled"]
                and not repo["_budget_exempt"]
                and repo["reason"] in ("prior_attention_signal", "no_prior_run")
                and repo["repo_id"] not in allowed_repo_ids
            ):
                repo["enabled"] = False
                repo["reason"] = "attention_budget_exceeded"

    for repo in provisional:
        repo.pop("_priority", None)
        repo.pop("_budget_exempt", None)

    return {"repos": sorted(provisional, key=lambda repo: repo["repo_id"])}


def _build_cycle_cmd(args):
    cmd = [
        sys.executable,
        str(_GOVERNED_CYCLE_SCRIPT),
        "--manifest", args.manifest,
        "--output", args.output,
    ]
    for task in args.task:
        cmd += ["--task", task]
    if args.repo_ids:
        for repo_id in args.repo_ids:
            cmd += ["--repo-id", repo_id]
    if args.top_k is not None:
        cmd += ["--top-k", str(args.top_k)]
    if args.force:
        cmd.append("--force")
    if args.governance_policy is not None:
        cmd += ["--governance-policy", args.governance_policy]
    return cmd


def _derive_timestamp(cycle_data):
    regression = cycle_data.get("cycle_history_regression") or {}
    ts = regression.get("current_cycle_timestamp")
    if ts:
        return ts

    history = cycle_data.get("cycle_history") or {}
    cycles = history.get("cycles") or []
    if cycles:
        return cycles[-1].get("timestamp")

    return None


def _get_planner_selected_tasks(cycle_data):
    execution_result = cycle_data.get("execution_result") or {}
    selected = execution_result.get("selected_tasks")
    if isinstance(selected, list):
        return sorted(selected)
    return []


def _classify_alert_level(cycle_status, governance_decision):
    if cycle_status != "ok":
        return "critical"
    if governance_decision in ("abort", "warn"):
        return "warning"
    return "none"


def _build_summary(cycle_output_path, cycle_data):
    status = cycle_data.get("status", "unknown")

    governance_decision_data = cycle_data.get("governance_decision") or {}
    governance_decision = governance_decision_data.get("decision", "unknown")

    regression_data = cycle_data.get("cycle_history_regression") or {}
    regression_detected = bool(regression_data.get("regression_detected", False))

    history = cycle_data.get("cycle_history") or {}
    cycles = history.get("cycles") or []
    cycle_history_length = len(cycles)

    planner_selected_tasks = _get_planner_selected_tasks(cycle_data)
    timestamp = _derive_timestamp(cycle_data)
    alert_level = _classify_alert_level(status, governance_decision)

    return {
        "alert_level": alert_level,
        "cycle_history_length": cycle_history_length,
        "cycle_output": str(cycle_output_path),
        "governance_decision": governance_decision,
        "planner_selected_tasks": planner_selected_tasks,
        "regression_detected": regression_detected,
        "status": status,
        "timestamp": timestamp,
    }


def _build_alert(cycle_status, governance_decision):
    alert_level = _classify_alert_level(cycle_status, governance_decision)
    alert = alert_level != "none"

    reasons = []
    if cycle_status != "ok":
        reasons.append("cycle_status_aborted")
    if governance_decision == "abort":
        reasons.append("governance_decision_abort")
    elif governance_decision == "warn":
        reasons.append("governance_decision_warn")

    return {
        "alert": alert,
        "alert_level": alert_level,
        "reasons": reasons,
    }


def run_scheduled_cycle(args):
    cmd = _build_cycle_cmd(args)

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(
            f"error: governed cycle subprocess failed (rc={exc.returncode})\n"
        )
        _write_json(args.alert_output, {
            "alert": True,
            "alert_level": "critical",
            "reasons": ["wrapper_subprocess_failed"],
        })
        return 1
    except FileNotFoundError as exc:
        sys.stderr.write(f"error: cannot launch governed cycle: {exc}\n")
        _write_json(args.alert_output, {
            "alert": True,
            "alert_level": "critical",
            "reasons": ["wrapper_subprocess_failed"],
        })
        return 1

    cycle_output_path = Path(args.output)
    try:
        cycle_data = json.loads(cycle_output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(
            f"error: cannot read cycle artifact {args.output}: {exc}\n"
        )
        _write_json(args.alert_output, {
            "alert": True,
            "alert_level": "critical",
            "reasons": ["wrapper_artifact_unreadable"],
        })
        return 1

    cycle_status = cycle_data.get("status", "unknown")
    governance_decision_data = cycle_data.get("governance_decision") or {}
    governance_decision = governance_decision_data.get("decision", "unknown")

    summary = _build_summary(cycle_output_path, cycle_data)
    alert = _build_alert(cycle_status, governance_decision)

    _write_json(args.summary_output, summary)
    _write_json(args.alert_output, alert)

    return 0


def load_manifest(path):
    return json.loads(Path(path).read_text())


def run_repo_cycle(manifest_path, repo_id, tasks, output_dir):
    repo_dir = Path(output_dir) / repo_id
    repo_dir.mkdir(parents=True, exist_ok=True)

    cycle_output = repo_dir / "governed_cycle.json"
    summary_output = repo_dir / "summary.json"
    alert_output = repo_dir / "alert.json"

    cmd = [
        "python3",
        "scripts/run_scheduled_governed_cycle.py",
        "--manifest",
        str(manifest_path),
        "--output",
        str(cycle_output),
        "--summary-output",
        str(summary_output),
        "--alert-output",
        str(alert_output),
        "--repo-id",
        repo_id,
    ]

    for task in tasks:
        cmd.extend(["--task", task])

    subprocess.run(cmd, check=True)

    summary = json.loads(summary_output.read_text())
    alert = json.loads(alert_output.read_text())

    return summary, alert


def aggregate(results):
    summaries = []
    alerts = []

    for summary, alert in results:
        summaries.append(summary)
        alerts.append(alert)

    portfolio_alert = any(a.get("alert") for a in alerts)

    return {
        "repos_total": len(results),
        "alerts_triggered": portfolio_alert,
    }, {
        "alert": portfolio_alert,
    }


def run_portfolio_governance_batch(args):
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    plan_path = output_dir / "portfolio_governance_plan.json"
    plan = build_plan(args.manifest, output_dir)
    _write_json(plan_path, plan)

    repo_ids = [r["repo_id"] for r in plan.get("repos", []) if r.get("enabled")]

    results = []

    for repo_id in repo_ids:
        summary, alert = run_repo_cycle(
            args.manifest,
            repo_id,
            args.task,
            output_dir,
        )
        results.append((summary, alert))

    portfolio_summary, portfolio_alert = aggregate(results)

    _write_json(output_dir / "portfolio_batch_summary.json", portfolio_summary)
    _write_json(output_dir / "portfolio_batch_alert.json", portfolio_alert)

    return 0
