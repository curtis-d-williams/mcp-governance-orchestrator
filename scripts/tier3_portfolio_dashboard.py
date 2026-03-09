#!/usr/bin/env python3
"""
Deterministic Tier 3 portfolio-wide dashboard.

- Aggregates Tier 3 outputs across all templates
- Generates summary table of metrics and notes
- Read-only; preserves all frozen composition invariants
"""

import importlib
from collections import OrderedDict

tier3_guardians = [
    "templates.sample_template.server",
    "templates.repo_insights.server",
    "templates.intelligence_layer_template.server",
]

def build_portfolio_dashboard():
    aggregated = OrderedDict()
    all_outputs = [importlib.import_module(g).main() for g in tier3_guardians]

    for out in all_outputs:
        sid = out["suggestions"]["suggestion_id"]
        aggregated[sid] = {
            "description": out["suggestions"].get("description", ""),
            "metrics": out["suggestions"].get("metrics", {}),
            "notes": out["suggestions"].get("notes", ""),
        }

    return aggregated

if __name__ == "__main__":
    dashboard = build_portfolio_dashboard()
    print("=== Tier 3 Portfolio Dashboard ===")
    for sid, data in dashboard.items():
        print(f"\nSuggestion ID: {sid}")
        print(f"Description: {data['description']}")
        print(f"Metrics: {data['metrics']}")
        print(f"Notes: {data['notes']}")
