#!/usr/bin/env python3
"""
Tier 3 portfolio report generator.

- Converts deterministic analytics outputs into CSV format
- Read-only; preserves all frozen composition invariants
"""

import importlib
import csv
from collections import OrderedDict

tier3_guardians = [
    "templates.sample_template.server",
    "templates.repo_insights.server",
    "templates.intelligence_layer_template.server",
]

def build_dashboard():
    dashboard = OrderedDict()
    all_outputs = [importlib.import_module(g).main() for g in tier3_guardians]

    for out in all_outputs:
        sid = out["suggestions"]["suggestion_id"]
        dashboard[sid] = {
            "description": out["suggestions"].get("description", ""),
            "metrics": out["suggestions"].get("metrics", {}),
            "notes": out["suggestions"].get("notes", ""),
        }
    return dashboard

def write_csv_report(filepath="tier3_portfolio_report.csv"):
    dashboard = build_dashboard()
    with open(filepath, mode="w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Suggestion ID", "Description", "Example Metric", "Notes"])
        for sid, data in dashboard.items():
            writer.writerow([
                sid,
                data["description"],
                data["metrics"].get("example_metric", 0),
                data["notes"]
            ])
    print(f"Tier 3 portfolio report written to {filepath}")

if __name__ == "__main__":
    write_csv_report()
