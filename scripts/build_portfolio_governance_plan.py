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

Attention budgeting rule:
- optionally limit the number of enabled repos requiring attention
- prioritize higher-severity repos deterministically
- enable only the first N repos in that ranked set
- mark remaining repos as disabled with reason attention_budget_exceeded

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


def _attention_priority(summary):
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
            "_priority": _attention_priority(summary),
        })

    if max_repos_per_cycle is not None:
        attention_candidates = sorted(
            [
                repo for repo in provisional
                if repo["enabled"] and repo["reason"] in ("prior_attention_signal", "no_prior_run")
            ],
            key=lambda repo: (repo["_priority"], repo["repo_id"]),
        )
        allowed_repo_ids = {
            repo["repo_id"] for repo in attention_candidates[:max_repos_per_cycle]
        }

        for repo in provisional:
            if repo["enabled"] and repo["reason"] in ("prior_attention_signal", "no_prior_run"):
                if repo["repo_id"] not in allowed_repo_ids:
                    repo["enabled"] = False
                    repo["reason"] = "attention_budget_exceeded"

    for repo in provisional:
        repo.pop("_priority", None)

    return {"repos": sorted(provisional, key=lambda repo: repo["repo_id"])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--output-dir", required=True, dest="output_dir")
    parser.add_argument("--max-repos-per-cycle", type=int, default=None)

    args = parser.parse_args()

    plan = build_plan(
        args.manifest,
        args.output_dir,
        max_repos_per_cycle=args.max_repos_per_cycle,
    )
    _write_json(args.output, plan)


if __name__ == "__main__":
    main()
