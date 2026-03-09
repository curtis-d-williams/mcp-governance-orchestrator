"""
Deterministic agent task: build the Tier 3 portfolio dashboard.

This task is a thin approved wrapper around the existing Tier 3 workflow.
"""

from collections import OrderedDict

from scripts.tier3_agent_aggregate import aggregate_tier3_outputs
from scripts.tier3_generate_report import write_csv_from_aggregate
from scripts.tier3_generate_html_dashboard_styled import generate_styled_dashboard


TASK_NAME = "build_portfolio_dashboard"
DEFAULT_CSV_PATH = "tier3_portfolio_report.csv"
DEFAULT_HTML_PATH = "tier3_portfolio_dashboard_styled.html"


def run(csv_path=DEFAULT_CSV_PATH, html_path=DEFAULT_HTML_PATH):
    aggregated = aggregate_tier3_outputs()
    write_csv_from_aggregate(aggregated, filepath=csv_path)
    generate_styled_dashboard(csv_path=csv_path, html_path=html_path)
    return OrderedDict([
        ("task_name", TASK_NAME),
        ("csv_path", csv_path),
        ("html_path", html_path),
        ("suggestion_ids", list(aggregated.keys())),
    ])
