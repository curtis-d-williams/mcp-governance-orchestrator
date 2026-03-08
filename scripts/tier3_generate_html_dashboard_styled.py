#!/usr/bin/env python3
"""
Enhanced Tier 3 portfolio HTML dashboard.

- Reads deterministic CSV report from Tier 3 analytics
- Generates a styled HTML table with alternating row colors
- Fully read-only; preserves frozen composition invariants
"""

import csv
import html

def generate_styled_dashboard(csv_path="tier3_portfolio_report.csv", html_path="tier3_portfolio_dashboard_styled.html"):
    rows = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

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
        f.write("</table></body></html>\n")
    print(f"Enhanced HTML dashboard generated at {html_path}")

if __name__ == "__main__":
    generate_styled_dashboard()
