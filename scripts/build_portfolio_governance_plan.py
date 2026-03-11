# SPDX-License-Identifier: MIT
"""
Phase Q: build adaptive portfolio governance execution plan.

Reads the portfolio manifest and produces a deterministic plan
for which repositories should run in the current governance cycle.

Adaptive rule:
- enable repos with no prior summary
- disable repos whose last summary is stable:
    alert_level == "none" and governance_decision == "continue"
- enable all others

Output format:

{
  "repos": [
    {
      "enabled": false,
      "reason": "stable_continue_last_cycle",
      "repo_id": "repo-name"
    }
  ]
}
"""

import argparse
import json
from pathlib import Path


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


def build_plan(manifest_path, output_dir):
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    repos = manifest.get("repos", [])

    plan = {"repos": []}

    for repo in repos:
        repo_id = repo.get("id")
        if not repo_id:
            continue

        summary = _load_json_if_exists(_repo_summary_path(output_dir, repo_id))

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

        plan["repos"].append({
            "enabled": enabled,
            "reason": reason,
            "repo_id": repo_id,
        })

    return plan


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--output-dir", required=True, dest="output_dir")

    args = parser.parse_args()

    plan = build_plan(args.manifest, args.output_dir)
    _write_json(args.output, plan)


if __name__ == "__main__":
    main()
