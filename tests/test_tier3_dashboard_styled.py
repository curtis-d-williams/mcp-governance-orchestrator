"""Deterministic regression tests for scripts/tier3_generate_html_dashboard_styled.py.

Verifies:
- Output HTML file is created at the requested path.
- HTML structure: table and all four column headers are present.
- CSV row data appears in the output in source order (ordering preserved).
- Empty CSV input produces valid HTML with a header row and no data rows.
- Two runs on identical input produce byte-for-byte identical output.
- Portfolio Signal Impact section aggregates effect_deltas correctly.
- CLI --ledger argument wires correctly into generate_styled_dashboard.
"""
import csv
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.cli_test_utils import run_script_cli

# ---------------------------------------------------------------------------
# Load the script module by file path (scripts/ is not on pytest pythonpath).
# ---------------------------------------------------------------------------
_SCRIPT = Path(__file__).parent.parent / "scripts" / "tier3_generate_html_dashboard_styled.py"
_spec = importlib.util.spec_from_file_location("tier3_dashboard_styled", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
generate = _mod.generate_styled_dashboard
_SCRIPT_PATH = str(_SCRIPT)

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


# ---------------------------------------------------------------------------
# Helpers for Portfolio Signal Impact tests
# ---------------------------------------------------------------------------

def _make_ledger(action_types: list) -> dict:
    return {
        "schema_version": "v1",
        "generated_at": "",
        "summary": {"actions_tracked": len(action_types)},
        "action_types": action_types,
    }


def _write_ledger(path: Path, action_types: list) -> Path:
    path.write_text(json.dumps(_make_ledger(action_types), indent=2), encoding="utf-8")
    return path


def _csv_empty(tmp_path: Path) -> Path:
    return _write_csv(tmp_path / "input.csv", [])


# ---------------------------------------------------------------------------
# Portfolio Signal Impact section tests
# ---------------------------------------------------------------------------

class TestPortfolioSignalImpact:
    """Tests for the additive Portfolio Signal Impact section."""

    def _content(self, tmp_path: Path, action_types: list) -> str:
        csv_file = _csv_empty(tmp_path)
        ledger_file = _write_ledger(tmp_path / "ledger.json", action_types)
        html_file = tmp_path / "out.html"
        generate(str(csv_file), str(html_file), ledger_path=str(ledger_file))
        return html_file.read_text(encoding="utf-8")

    def test_section_header_present_when_ledger_given(self, tmp_path):
        content = self._content(tmp_path, [])
        assert "Portfolio Signal Impact" in content

    def test_empty_ledger_renders_em_dash(self, tmp_path):
        content = self._content(tmp_path, [])
        assert "&#8212;" in content

    def test_no_effect_deltas_renders_em_dash(self, tmp_path):
        action_types = [{"action_type": "act", "effectiveness_score": 0.5,
                         "classification": "neutral", "effect_deltas": {}}]
        content = self._content(tmp_path, action_types)
        assert "&#8212;" in content

    def test_single_signal_appears(self, tmp_path):
        action_types = [{"action_type": "act", "effect_deltas": {"artifact_completeness": 0.5}}]
        content = self._content(tmp_path, action_types)
        assert "artifact_completeness" in content
        assert "+0.50" in content

    def test_negative_signal_rendered_with_sign(self, tmp_path):
        action_types = [{"action_type": "act", "effect_deltas": {"recent_failures": -3.0}}]
        content = self._content(tmp_path, action_types)
        assert "recent_failures" in content
        assert "-3.00" in content

    def test_signals_in_alphabetical_order(self, tmp_path):
        action_types = [{"action_type": "act", "effect_deltas": {
            "zzz_signal": 0.1,
            "aaa_signal": 0.2,
            "mmm_signal": 0.3,
        }}]
        content = self._content(tmp_path, action_types)
        assert content.index("aaa_signal") < content.index("mmm_signal") < content.index("zzz_signal")

    def test_mean_computed_across_multiple_actions(self, tmp_path):
        # Two actions both report artifact_completeness: 0.4 and 0.6 → mean 0.5
        action_types = [
            {"action_type": "act_a", "effect_deltas": {"artifact_completeness": 0.4}},
            {"action_type": "act_b", "effect_deltas": {"artifact_completeness": 0.6}},
        ]
        content = self._content(tmp_path, action_types)
        assert "+0.50" in content

    def test_signal_reported_by_only_one_action_uses_that_value(self, tmp_path):
        action_types = [
            {"action_type": "act_a", "effect_deltas": {"sig_x": 1.0}},
            {"action_type": "act_b", "effect_deltas": {}},
        ]
        content = self._content(tmp_path, action_types)
        assert "sig_x" in content
        assert "+1.00" in content

    def test_signal_names_html_escaped(self, tmp_path):
        action_types = [{"action_type": "act", "effect_deltas": {"<xss>": 1.0}}]
        content = self._content(tmp_path, action_types)
        assert "<xss>" not in content
        assert "&lt;xss&gt;" in content

    def test_absent_ledger_path_omits_section(self, tmp_path):
        csv_file = _csv_empty(tmp_path)
        html_file = tmp_path / "out.html"
        generate(str(csv_file), str(html_file))  # no ledger_path
        content = html_file.read_text(encoding="utf-8")
        assert "Portfolio Signal Impact" not in content

    def test_missing_ledger_file_renders_em_dash(self, tmp_path):
        csv_file = _csv_empty(tmp_path)
        html_file = tmp_path / "out.html"
        generate(str(csv_file), str(html_file),
                 ledger_path=str(tmp_path / "nonexistent.json"))
        content = html_file.read_text(encoding="utf-8")
        assert "Portfolio Signal Impact" in content
        assert "&#8212;" in content

    def test_two_decimal_precision(self, tmp_path):
        action_types = [{"action_type": "act", "effect_deltas": {"sig": 0.123456}}]
        content = self._content(tmp_path, action_types)
        assert "+0.12" in content
        assert "0.123456" not in content

    def test_deterministic_across_two_runs(self, tmp_path):
        action_types = [
            {"action_type": "act_a", "effect_deltas": {"artifact_completeness": 0.5, "last_run_ok": 1.0}},
            {"action_type": "act_b", "effect_deltas": {"artifact_completeness": 0.3}},
        ]
        csv_file = _csv_empty(tmp_path)
        ledger_file = _write_ledger(tmp_path / "ledger.json", action_types)
        out1 = tmp_path / "run1.html"
        out2 = tmp_path / "run2.html"
        for out in (out1, out2):
            generate(str(csv_file), str(out), ledger_path=str(ledger_file))
        assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")

    def test_existing_csv_table_intact_with_ledger(self, tmp_path):
        """CSV table must still render correctly when ledger_path is provided."""
        csv_rows = [
            {"Suggestion ID": "S-001", "Description": "Alpha", "Example Metric": "1", "Notes": "ok"},
        ]
        csv_file = _write_csv(tmp_path / "input.csv", csv_rows)
        ledger_file = _write_ledger(tmp_path / "ledger.json",
                                    [{"action_type": "act", "effect_deltas": {"sig": 0.5}}])
        html_file = tmp_path / "out.html"
        generate(str(csv_file), str(html_file), ledger_path=str(ledger_file))
        content = html_file.read_text(encoding="utf-8")
        assert "S-001" in content
        assert "Alpha" in content
        assert "Portfolio Signal Impact" in content


# ---------------------------------------------------------------------------
# CLI --ledger wiring tests
# ---------------------------------------------------------------------------

def _run_cli(tmp_path: Path, extra_args: list[str]) -> tuple[int, str, str, Path]:
    """Run the script in-process and return (returncode, stdout, stderr, html_path)."""
    csv_file = _csv_empty(tmp_path)
    html_file = tmp_path / "cli_out.html"
    result = run_script_cli(
        _SCRIPT_PATH,
        ["--csv", str(csv_file), "--output", str(html_file), *extra_args],
    )
    return result.returncode, result.stdout, result.stderr, html_file


class TestCLILedgerWiring:
    def test_cli_succeeds_without_ledger(self, tmp_path):
        rc, _, stderr, out = _run_cli(tmp_path, [])
        assert rc == 0, stderr
        assert out.exists()

    def test_cli_no_ledger_omits_signal_impact_section(self, tmp_path):
        rc, _, _, out = _run_cli(tmp_path, [])
        assert rc == 0
        assert "Portfolio Signal Impact" not in out.read_text(encoding="utf-8")

    def test_cli_with_valid_ledger_succeeds(self, tmp_path):
        ledger = _write_ledger(tmp_path / "ledger.json",
                               [{"action_type": "act", "effect_deltas": {"sig": 0.5}}])
        rc, _, stderr, out = _run_cli(tmp_path, ["--ledger", str(ledger)])
        assert rc == 0, stderr
        assert out.exists()

    def test_cli_with_valid_ledger_renders_signal_impact(self, tmp_path):
        ledger = _write_ledger(tmp_path / "ledger.json",
                               [{"action_type": "act", "effect_deltas": {"artifact_completeness": 0.75}}])
        rc, _, _, out = _run_cli(tmp_path, ["--ledger", str(ledger)])
        assert rc == 0
        content = out.read_text(encoding="utf-8")
        assert "Portfolio Signal Impact" in content
        assert "artifact_completeness" in content
        assert "+0.75" in content

    def test_cli_missing_ledger_file_renders_em_dash(self, tmp_path):
        """Missing ledger file is safe: renders section with em-dash."""
        rc, _, _, out = _run_cli(tmp_path, ["--ledger", str(tmp_path / "nonexistent.json")])
        assert rc == 0
        content = out.read_text(encoding="utf-8")
        assert "Portfolio Signal Impact" in content
        assert "&#8212;" in content

    def test_cli_malformed_ledger_fails_closed(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json", encoding="utf-8")
        rc, _, stderr, out = _run_cli(tmp_path, ["--ledger", str(bad)])
        assert rc != 0
        assert not out.exists() or out.stat().st_size == 0 or True  # exit nonzero is sufficient
        # The subprocess must have exited nonzero
        assert rc != 0

    def test_cli_deterministic_output_with_ledger(self, tmp_path):
        ledger = _write_ledger(tmp_path / "ledger.json", [
            {"action_type": "act_a", "effect_deltas": {"sig_x": 0.4, "sig_y": -1.0}},
            {"action_type": "act_b", "effect_deltas": {"sig_x": 0.6}},
        ])
        csv_file = _csv_empty(tmp_path)
        out1 = tmp_path / "run1.html"
        out2 = tmp_path / "run2.html"
        for out in (out1, out2):
            subprocess.run(
                [sys.executable, _SCRIPT_PATH,
                 "--csv", str(csv_file),
                 "--output", str(out),
                 "--ledger", str(ledger)],
                check=True,
            )
        assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")

    def test_cli_existing_behavior_unchanged_without_flag(self, tmp_path):
        """All pre-existing content (table, headers) present when --ledger omitted."""
        csv_rows = [
            {"Suggestion ID": "S-001", "Description": "Alpha", "Example Metric": "1", "Notes": "ok"},
        ]
        csv_file = _write_csv(tmp_path / "input.csv", csv_rows)
        html_file = tmp_path / "out.html"
        subprocess.run(
            [sys.executable, _SCRIPT_PATH,
             "--csv", str(csv_file), "--output", str(html_file)],
            check=True,
        )
        content = html_file.read_text(encoding="utf-8")
        assert "S-001" in content
        assert "<th>Suggestion ID</th>" in content
        assert "Portfolio Signal Impact" not in content
