#!/usr/bin/env python3
"""
Enhanced Tier 3 portfolio HTML dashboard.

- Reads deterministic CSV report from Tier 3 analytics
- Generates a styled HTML table with alternating row colors
- Optionally renders a Portfolio Signal Impact section from the
  action_effectiveness_ledger.json (aggregated effect_deltas roll-up)
- Fully read-only; preserves frozen composition invariants
"""

import csv
import html
import json
from pathlib import Path


def _aggregate_effect_deltas(ledger_path: str) -> dict:
    """Read ledger JSON and compute mean effect_delta per signal across all action_types.

    Returns a dict mapping signal_name -> mean_delta, keys in alphabetical order.
    Returns empty dict on any read/parse error, missing file, or missing field.
    """
    path = Path(ledger_path)
    if not path.exists():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
        ledger = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return {}

    action_types = ledger.get("action_types", [])
    if not isinstance(action_types, list):
        return {}

    accumulated: dict[str, list[float]] = {}
    for row in action_types:
        deltas = row.get("effect_deltas", {})
        if not isinstance(deltas, dict):
            continue
        for sig, delta in deltas.items():
            try:
                accumulated.setdefault(sig, []).append(float(delta))
            except (TypeError, ValueError):
                continue

    return {
        sig: sum(vals) / len(vals)
        for sig, vals in sorted(accumulated.items())
    }


def _render_signal_impact_section(aggregated: dict) -> str:
    """Return HTML string for the Portfolio Signal Impact section."""
    lines: list[str] = []
    lines.append("<h2>Portfolio Signal Impact</h2>")
    if not aggregated:
        lines.append("<p>&#8212;</p>")
        return "\n".join(lines)
    lines.append("<table>")
    lines.append("<tr><th>Signal</th><th>Avg Delta</th></tr>")
    for sig, mean_val in aggregated.items():
        sig_esc = html.escape(sig)
        val_esc = html.escape(f"{mean_val:+.2f}")
        lines.append(f"<tr><td>{sig_esc}</td><td>{val_esc}</td></tr>")
    lines.append("</table>")
    return "\n".join(lines)


def generate_styled_dashboard(
    csv_path="tier3_portfolio_report.csv",
    html_path="tier3_portfolio_dashboard_styled.html",
    ledger_path=None,
):
    rows = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    # Compute signal impact roll-up when a ledger path is provided.
    aggregated: dict = {}
    if ledger_path is not None:
        aggregated = _aggregate_effect_deltas(ledger_path)

    with open(html_path, "w") as f:
        f.write("<html><head><title>Tier 3 Portfolio Dashboard</title>\n")
        f.write("<style>\n")
        f.write("table { border-collapse: collapse; width: 100%; }")
        f.write("th, td { border: 1px solid #333; padding: 8px; text-align: left; }")
        f.write("tr:nth-child(even) { background-color: #f2f2f2; }")
        f.write("th { background-color: #4CAF50; color: white; }\n")
        f.write("</style></head><body>\n")
        f.write("<h1>Tier 3 Portfolio Dashboard</h1>\n")
        f.write("<table>\n")
        f.write("<tr><th>Suggestion ID</th><th>Description</th><th>Example Metric</th><th>Notes</th></tr>\n")
        for row in rows:
            f.write(f"<tr><td>{html.escape(row['Suggestion ID'])}</td><td>{html.escape(row['Description'])}</td><td>{html.escape(row['Example Metric'])}</td><td>{html.escape(row['Notes'])}</td></tr>\n")
        f.write("</table>\n")

        # Portfolio Signal Impact section (additive; only present when ledger_path given).
        if ledger_path is not None:
            f.write(_render_signal_impact_section(aggregated))
            f.write("\n")

        f.write("</body></html>\n")
    print(f"Enhanced HTML dashboard generated at {html_path}")

if __name__ == "__main__":
    generate_styled_dashboard()
