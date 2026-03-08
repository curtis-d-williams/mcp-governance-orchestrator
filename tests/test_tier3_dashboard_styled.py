"""Deterministic regression tests for scripts/tier3_generate_html_dashboard_styled.py.

Verifies:
- Output HTML file is created at the requested path.
- HTML structure: table and all four column headers are present.
- CSV row data appears in the output in source order (ordering preserved).
- Empty CSV input produces valid HTML with a header row and no data rows.
- Two runs on identical input produce byte-for-byte identical output.
"""
import csv
import importlib.util
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Load the script module by file path (scripts/ is not on pytest pythonpath).
# ---------------------------------------------------------------------------
_SCRIPT = Path(__file__).parent.parent / "scripts" / "tier3_generate_html_dashboard_styled.py"
_spec = importlib.util.spec_from_file_location("tier3_dashboard_styled", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
generate = _mod.generate_styled_dashboard

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------
_HEADERS = ["Suggestion ID", "Description", "Example Metric", "Notes"]


def _write_csv(path: Path, rows: list) -> Path:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_HEADERS)
        writer.writeheader()
        writer.writerows(rows)
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_output_file_is_created(tmp_path):
    csv_file = _write_csv(tmp_path / "input.csv", [
        {"Suggestion ID": "S-001", "Description": "Alpha", "Example Metric": "1", "Notes": "ok"},
    ])
    html_file = tmp_path / "output.html"
    generate(str(csv_file), str(html_file))
    assert html_file.exists(), "HTML output file was not created"


def test_html_table_headers_present(tmp_path):
    csv_file = _write_csv(tmp_path / "input.csv", [])
    html_file = tmp_path / "output.html"
    generate(str(csv_file), str(html_file))
    content = html_file.read_text()
    assert "<table>" in content
    assert "<th>Suggestion ID</th>" in content
    assert "<th>Description</th>" in content
    assert "<th>Example Metric</th>" in content
    assert "<th>Notes</th>" in content


def test_row_data_present_and_ordered(tmp_path):
    rows = [
        {"Suggestion ID": "S-001", "Description": "Alpha", "Example Metric": "10", "Notes": "first"},
        {"Suggestion ID": "S-002", "Description": "Beta",  "Example Metric": "20", "Notes": "second"},
        {"Suggestion ID": "S-003", "Description": "Gamma", "Example Metric": "30", "Notes": "third"},
    ]
    csv_file = _write_csv(tmp_path / "input.csv", rows)
    html_file = tmp_path / "output.html"
    generate(str(csv_file), str(html_file))
    content = html_file.read_text()

    # All data values appear in the output.
    for row in rows:
        assert row["Suggestion ID"] in content
        assert row["Description"] in content
        assert row["Example Metric"] in content
        assert row["Notes"] in content

    # Source order is preserved: S-001 < S-002 < S-003 by position in HTML.
    positions = [content.index(r["Suggestion ID"]) for r in rows]
    assert positions == sorted(positions), "Row order not preserved from CSV input"


def test_empty_csv_produces_valid_html_no_data_rows(tmp_path):
    csv_file = _write_csv(tmp_path / "input.csv", [])
    html_file = tmp_path / "output.html"
    generate(str(csv_file), str(html_file))
    content = html_file.read_text()
    assert "<html>" in content
    assert "</html>" in content
    assert "<table>" in content
    assert "<td>" not in content, "Empty CSV should produce no <td> data cells"


def test_html_special_chars_are_escaped(tmp_path):
    rows = [
        {
            "Suggestion ID": "S-XSS",
            "Description": "<script>alert('xss')</script>",
            "Example Metric": "a&b",
            "Notes": "x>y and x<z",
        },
    ]
    csv_file = _write_csv(tmp_path / "input.csv", rows)
    html_file = tmp_path / "output.html"
    generate(str(csv_file), str(html_file))
    content = html_file.read_text()

    # Raw special characters must not appear inside <td> cells.
    assert "<script>" not in content
    assert "alert('xss')" not in content or "&lt;script&gt;" in content
    assert "a&b" not in content
    assert "x>y" not in content
    assert "x<z" not in content

    # Escaped forms must be present.
    assert "&lt;script&gt;" in content
    assert "a&amp;b" in content
    assert "x&gt;y" in content
    assert "x&lt;z" in content


def test_deterministic_output_same_input(tmp_path):
    rows = [
        {"Suggestion ID": "S-042", "Description": "Stable", "Example Metric": "99", "Notes": "repeat"},
    ]
    csv_file = _write_csv(tmp_path / "input.csv", rows)
    html_a = tmp_path / "run_a.html"
    html_b = tmp_path / "run_b.html"
    generate(str(csv_file), str(html_a))
    generate(str(csv_file), str(html_b))
    assert html_a.read_text() == html_b.read_text(), "Output is not deterministic across two runs on identical input"
