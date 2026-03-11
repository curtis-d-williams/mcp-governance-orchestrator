# SPDX-License-Identifier: MIT
"""
Phase P: build portfolio governance execution plan.

Reads the portfolio manifest and produces a deterministic plan
for which repositories should run in the current governance cycle.

Output format:

{
  "repos": [
    {
      "repo_id": "repo-name",
      "enabled": true
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


def build_plan(manifest_path):
    manifest = json.loads(Path(manifest_path).read_text())

    repos = manifest.get("repos", [])

    plan = {
        "repos": []
    }

    for repo in repos:
        repo_id = repo.get("id")
        if not repo_id:
            continue

        plan["repos"].append({
            "repo_id": repo_id,
            "enabled": True
        })

    return plan


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)

    args = parser.parse_args()

    plan = build_plan(args.manifest)
    _write_json(args.output, plan)


if __name__ == "__main__":
    main()
