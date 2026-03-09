#!/usr/bin/env python3
"""
Deterministic Tier 3 agent cross-repo aggregation.

- Aggregates Tier 3 outputs across all templates
- Read-only, deterministic
- Preserves frozen composition invariants
"""

import importlib
from collections import OrderedDict

tier3_guardians = [
    "templates.sample_template.server",
    "templates.repo_insights.server",
    "templates.intelligence_layer_template.server",
]

def aggregate_tier3_outputs():
    aggregated = OrderedDict()
    all_outputs = [importlib.import_module(g).main() for g in tier3_guardians]

    for out in all_outputs:
        sid = out["suggestions"]["suggestion_id"]
        metrics = out["suggestions"]["metrics"]
        notes = out["suggestions"]["notes"]

        aggregated[sid] = {
            "description": out["suggestions"].get("description", ""),
            "metrics": metrics,
            "notes": notes,
        }

    return aggregated

if __name__ == "__main__":
    agg = aggregate_tier3_outputs()
    for sid, data in agg.items():
        print(f"[Agent Aggregate] {sid}")
        print(f"Metrics: {data['metrics']}")
        print(f"Notes: {data['notes']}")
