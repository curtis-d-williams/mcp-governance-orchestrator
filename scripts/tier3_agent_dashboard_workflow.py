#!/usr/bin/env python3
"""
Tier 3 agent dashboard workflow entrypoint.

Orchestrates:
  1. Aggregate Tier 3 outputs  (tier3_agent_aggregate)
  2. Write CSV portfolio report (tier3_generate_report)
  3. Generate styled HTML dashboard (tier3_generate_html_dashboard_styled)

Produces deterministic default outputs:
  - tier3_portfolio_report.csv
  - tier3_portfolio_dashboard_styled.html
"""

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from tier3_agent_aggregate import aggregate_tier3_outputs
from tier3_generate_report import write_csv_from_aggregate
from tier3_generate_html_dashboard_styled import generate_styled_dashboard


def run_dashboard_agent_workflow(
    csv_path="tier3_portfolio_report.csv",
    html_path="tier3_portfolio_dashboard_styled.html",
    _aggregate=None,
):
    """
    Orchestrate aggregate -> CSV report -> HTML dashboard.

    _aggregate: optional pre-built OrderedDict; used for deterministic testing.
                If None, calls aggregate_tier3_outputs() from tier3_agent_aggregate.
    """
    aggregated = _aggregate if _aggregate is not None else aggregate_tier3_outputs()
    write_csv_from_aggregate(aggregated, csv_path)
    generate_styled_dashboard(csv_path, html_path)


if __name__ == "__main__":
    run_dashboard_agent_workflow()
