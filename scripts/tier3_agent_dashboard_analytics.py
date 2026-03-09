#!/usr/bin/env python3
"""
Tier 3 agent analytics workflow (fixed).

- Reads Tier 3 dashboard outputs
- Performs deterministic cross-repo computations
- Fully preserves frozen composition invariants
"""

import importlib
from collections import OrderedDict

tier3_guardians = [
    "templates.sample_template.server",
    "templates.repo_insights.server",
    "templates.intelligence_layer_template.server",
]

def run_analytics():
    dashboard = OrderedDict()
    all_outputs = [importlib.import_module(g).main() for g in tier3_guardians]

    for out in all_outputs:
        sid = out["suggestions"]["suggestion_id"]
        dashboard[sid] = {
            "description": out["suggestions"].get("description", ""),
            "metrics": out["suggestions"].get("metrics", {}),
            "notes": out["suggestions"].get("notes", ""),
        }

    # Deterministic cross-repo computations
    total_metric = sum(d["metrics"].get("example_metric", 0) for d in dashboard.values())
    avg_metric = total_metric / len(dashboard) if dashboard else 0

    # Explicit prints to ensure visible output
    print("=== Tier 3 Portfolio Analytics ===")
    print(f"Total example_metric across all templates: {total_metric}")
    print(f"Average example_metric: {avg_metric:.2f}\n")

    for sid, data in dashboard.items():
        print(f"[Analytics] {sid}")
        print(f"Description: {data['description']}")
        print(f"Metrics: {data['metrics']}")
        print(f"Notes: {data['notes']}\n")

if __name__ == "__main__":
    run_analytics()
