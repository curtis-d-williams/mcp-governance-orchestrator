#!/usr/bin/env python3
"""
Tier 3 portfolio HTML dashboard generator.

- Reads deterministic CSV report from Tier 3 analytics
- Generates a simple HTML table dashboard
- Fully read-only; preserves all frozen composition invariants
"""

import csv

def generate_html_dashboard(csv_path="tier3_portfolio_report.csv", html_path="tier3_portfolio_dashboard.html"):
    rows = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    with open(html_path, "w") as f:
        f.write("<html><head><title>Tier 3 Portfolio Dashboard</title></head><body>\n")
        f.write("<h1>Tier 3 Portfolio Dashboard</h1>\n")
        f.write("<table border='1' style='border-collapse: collapse;'>\n")
        f.write("<tr><th>Suggestion ID</th><th>Description</th><th>Example Metric</th><th>Notes</th></tr>\n")
        for row in rows:
            f.write(f"<tr><td>{row['Suggestion ID']}</td><td>{row['Description']}</td><td>{row['Example Metric']}</td><td>{row['Notes']}</td></tr>\n")
        f.write("</table></body></html>\n")
    print(f"HTML dashboard generated at {html_path}")

if __name__ == "__main__":
    generate_html_dashboard()
