"""Deterministic regression tests for scripts/tier3_agent_dashboard_workflow.py.

Verifies:
- Both output files (CSV + HTML) are created by the workflow.
- CSV row ordering matches aggregate insertion order.
- HTML row ordering matches CSV row ordering.
- Two identical runs produce byte-for-byte identical CSV and HTML output.
"""
import csv
import importlib.util
from collections import OrderedDict
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Load the workflow module by file path (scripts/ is not on pytest pythonpath).
# ---------------------------------------------------------------------------
_SCRIPT = Path(__file__).parent.parent / "scripts" / "tier3_agent_dashboard_workflow.py"
_spec = importlib.util.spec_from_file_location("tier3_agent_dashboard_workflow", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
run_workflow = _mod.run_dashboard_agent_workflow


# ---------------------------------------------------------------------------
# Shared test fixture: minimal deterministic aggregate (no template imports).
# ---------------------------------------------------------------------------
def _make_aggregate():
    agg = OrderedDict()
    agg["S-001"] = {"description": "Alpha", "metrics": {"example_metric": 10}, "notes": "first"}
    agg["S-002"] = {"description": "Beta",  "metrics": {"example_metric": 20}, "notes": "second"}
    agg["S-003"] = {"description": "Gamma", "metrics": {"example_metric": 30}, "notes": "third"}
    return agg


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_both_output_files_created(tmp_path):
    csv_path = tmp_path / "report.csv"
    html_path = tmp_path / "dashboard.html"
    run_workflow(str(csv_path), str(html_path), _aggregate=_make_aggregate())
    assert csv_path.exists(), "CSV report was not created"
    assert html_path.exists(), "HTML dashboard was not created"


def test_csv_row_ordering_matches_aggregate(tmp_path):
    csv_path = tmp_path / "report.csv"
    html_path = tmp_path / "dashboard.html"
    run_workflow(str(csv_path), str(html_path), _aggregate=_make_aggregate())
    with open(csv_path, newline="") as f:
        rows = list(csv.DictReader(f))
    ids = [r["Suggestion ID"] for r in rows]
    assert ids == ["S-001", "S-002", "S-003"], f"CSV row order not stable: {ids}"


def test_html_row_ordering_matches_csv(tmp_path):
    csv_path = tmp_path / "report.csv"
    html_path = tmp_path / "dashboard.html"
    run_workflow(str(csv_path), str(html_path), _aggregate=_make_aggregate())
    content = html_path.read_text()
    positions = [content.index(sid) for sid in ["S-001", "S-002", "S-003"]]
    assert positions == sorted(positions), "HTML row order does not match CSV row order"


def test_deterministic_output_two_runs(tmp_path):
    """Two runs on identical aggregate input must produce byte-for-byte identical output."""
    agg = _make_aggregate()
    csv_a = tmp_path / "run_a.csv"
    html_a = tmp_path / "run_a.html"
    csv_b = tmp_path / "run_b.csv"
    html_b = tmp_path / "run_b.html"

    run_workflow(str(csv_a), str(html_a), _aggregate=agg)
    run_workflow(str(csv_b), str(html_b), _aggregate=agg)

    assert csv_a.read_text() == csv_b.read_text(), "CSV output not deterministic across two runs"
    assert html_a.read_text() == html_b.read_text(), "HTML output not deterministic across two runs"


def test_csv_contains_all_aggregate_fields(tmp_path):
    csv_path = tmp_path / "report.csv"
    html_path = tmp_path / "dashboard.html"
    run_workflow(str(csv_path), str(html_path), _aggregate=_make_aggregate())
    with open(csv_path, newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 3
    assert rows[0]["Suggestion ID"] == "S-001"
    assert rows[0]["Description"] == "Alpha"
    assert rows[0]["Example Metric"] == "10"
    assert rows[0]["Notes"] == "first"


def test_html_contains_all_suggestion_ids(tmp_path):
    csv_path = tmp_path / "report.csv"
    html_path = tmp_path / "dashboard.html"
    run_workflow(str(csv_path), str(html_path), _aggregate=_make_aggregate())
    content = html_path.read_text()
    for sid in ["S-001", "S-002", "S-003"]:
        assert sid in content, f"Suggestion ID {sid} missing from HTML dashboard"
