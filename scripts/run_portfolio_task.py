#!/usr/bin/env python3
"""
Run an approved agent task across a deterministic portfolio manifest.
"""

import json
import subprocess
import sys
from pathlib import Path

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


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(
            "Usage: python3 -m scripts.run_portfolio_task <task_name> <manifest.json>"
        )

    run_portfolio_task(sys.argv[1], sys.argv[2])
