#!/usr/bin/env python3
"""
Run an approved agent task across a deterministic portfolio manifest.
"""

import json
import subprocess
import sys
from pathlib import Path

# Ensure repo root is on sys.path when invoked as a direct script.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agent_tasks.registry import TASK_REGISTRY


def run_portfolio_task(task_name, manifest_path):
    if task_name not in TASK_REGISTRY:
        raise SystemExit(f"Unknown task: {task_name}")

    manifest = json.loads(Path(manifest_path).read_text())

    repos = sorted(manifest["repos"], key=lambda r: r["id"])

    results = []

    for repo in repos:
        repo_id = repo["id"]
        repo_path = repo["path"]

        try:
            proc = subprocess.run(
                ["python3", "-m", "scripts.run_agent_task", task_name],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )

            payload = json.loads(proc.stdout)

            results.append({
                "id": repo_id,
                "ok": True,
                "result": payload
            })

        except Exception as e:
            results.append({
                "id": repo_id,
                "ok": False,
                "error": str(e)
            })

    summary = {
        "repos_total": len(results),
        "repos_ok": sum(1 for r in results if r["ok"]),
        "repos_failed": sum(1 for r in results if not r["ok"]),
    }

    output = {
        "task_name": task_name,
        "repos": results,
        "summary": summary
    }

    print(json.dumps(output, indent=2))


def _run_multi_task(task_names, manifest_path):
    """Run multiple tasks and write per-run artifacts (multi-task entry point).

    Writes:
    - tier3_portfolio_report.csv    (task, repo_id, ok columns)
    - tier3_multi_run_aggregate.json (flat list of {task, repo, ok, result})
    - tier3_run_envelope.json        (same data; consumed by aggregate script)
    """
    import csv as _csv
    import io
    from contextlib import redirect_stdout

    manifest = json.loads(Path(manifest_path).read_text())
    repo_ids = sorted(r["id"] for r in manifest.get("repos", []))

    aggregate = []   # flat list of {task, repo, ok, result}
    csv_rows = []    # list of {task, repo_id, ok}

    for task_name in task_names:
        if task_name not in TASK_REGISTRY:
            # Unknown task: record as failed for each repo.
            for rid in repo_ids:
                aggregate.append({"task": task_name, "repo": rid, "ok": False, "result": {}})
                csv_rows.append({"task": task_name, "repo_id": rid, "ok": "false"})
            print(json.dumps({
                "task_name": task_name,
                "error": "unknown task",
                "repos": [{"id": rid, "ok": False} for rid in repo_ids],
                "summary": {
                    "repos_total": len(repo_ids),
                    "repos_ok": 0,
                    "repos_failed": len(repo_ids),
                },
            }, indent=2))
        else:
            # Capture run_portfolio_task's print output, forward to stdout.
            buf = io.StringIO()
            with redirect_stdout(buf):
                run_portfolio_task(task_name, manifest_path)
            output_text = buf.getvalue()
            sys.stdout.write(output_text)
            try:
                envelope = json.loads(output_text)
            except json.JSONDecodeError:
                envelope = {"task_name": task_name, "repos": [], "summary": {}}
            for repo in envelope.get("repos", []):
                rid = repo.get("id", "")
                ok = repo.get("ok", False)
                aggregate.append({
                    "task": task_name,
                    "repo": rid,
                    "ok": ok,
                    "result": repo.get("result", {}),
                })
                csv_rows.append({
                    "task": task_name,
                    "repo_id": rid,
                    "ok": str(ok).lower(),
                })

    # Write tier3_portfolio_report.csv (task-oriented format).
    with open("tier3_portfolio_report.csv", "w", newline="", encoding="utf-8") as fh:
        writer = _csv.DictWriter(fh, fieldnames=["task", "repo_id", "ok"])
        writer.writeheader()
        writer.writerows(csv_rows)

    # Write tier3_multi_run_aggregate.json for downstream consumers.
    Path("tier3_multi_run_aggregate.json").write_text(
        json.dumps(aggregate, indent=2) + "\n", encoding="utf-8"
    )

    # Write envelope for aggregate_multi_run_envelopes.py (idempotent).
    Path("tier3_run_envelope.json").write_text(
        json.dumps(aggregate, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(
            "Usage: python3 scripts/run_portfolio_task.py <task1> [task2 ...] <manifest.json>"
        )

    # Route both single-task and multi-task through _run_multi_task so the
    # downstream artifact files (tier3_portfolio_report.csv,
    # tier3_multi_run_aggregate.json, tier3_run_envelope.json) are always
    # written.  stdout content is unchanged: _run_multi_task re-emits the
    # same JSON that run_portfolio_task prints.
    _run_multi_task(sys.argv[1:-1], sys.argv[-1])
