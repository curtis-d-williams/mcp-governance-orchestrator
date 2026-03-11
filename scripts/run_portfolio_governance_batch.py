# SPDX-License-Identifier: MIT
"""Run scheduled governed cycles across every repo in a portfolio manifest.

This script fans out execution so each repo receives its own governed cycle
execution scope. It composes existing scheduled cycle infrastructure.

Outputs:
    <output-dir>/<repo-id>/governed_cycle.json
    <output-dir>/<repo-id>/summary.json
    <output-dir>/<repo-id>/alert.json

Also produces portfolio-level aggregates:

    <output-dir>/portfolio_batch_summary.json
    <output-dir>/portfolio_batch_alert.json
"""

import argparse
import json
import subprocess
from pathlib import Path


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def load_manifest(path):
    return json.loads(Path(path).read_text())


def run_repo_cycle(manifest_path, repo_id, tasks, output_dir):

    repo_dir = output_dir / repo_id
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

    for t in tasks:
        cmd.extend(["--task", t])

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
        "alert": portfolio_alert
    }


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--task", action="append", required=True)

    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    repo_ids = [repo["id"] for repo in manifest.get("repos", [])]

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

    write_json(output_dir / "portfolio_batch_summary.json", portfolio_summary)
    write_json(output_dir / "portfolio_batch_alert.json", portfolio_alert)


if __name__ == "__main__":
    main()
