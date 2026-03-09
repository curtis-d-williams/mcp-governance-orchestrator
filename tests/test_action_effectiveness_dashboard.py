# SPDX-License-Identifier: MIT
"""Regression tests for scripts/build_action_effectiveness_dashboard.py.

All fixtures are built in tmp_path. No real ledger files are read.
Deterministic: identical inputs produce identical outputs.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = str(_REPO_ROOT / "scripts" / "build_action_effectiveness_dashboard.py")


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_ledger(action_types: list[dict]) -> dict:
    effective = sum(1 for r in action_types if r.get("classification") == "effective")
    neutral = sum(1 for r in action_types if r.get("classification") == "neutral")
    ineffective = sum(1 for r in action_types if r.get("classification") == "ineffective")
    return {
        "schema_version": "v1",
        "generated_at": "",
        "summary": {
            "actions_tracked": len(action_types),
            "effective_actions": effective,
            "neutral_actions": neutral,
            "ineffective_actions": ineffective,
        },
        "action_types": action_types,
    }


def _row(
    action_type: str,
    score: float,
    classification: str,
    times_recommended: int = 1,
    times_executed: int = 1,
    success_rate: float = 1.0,
    avg_risk_delta: float = 0.0,
    avg_health_delta: float = 0.0,
    priority_adj: float = 0.0,
) -> dict:
    return {
        "action_type": action_type,
        "times_recommended": times_recommended,
        "times_executed": times_executed,
        "success_rate": success_rate,
        "avg_risk_delta": avg_risk_delta,
        "avg_health_delta": avg_health_delta,
        "effectiveness_score": score,
        "recommended_priority_adjustment": priority_adj,
        "classification": classification,
    }


def _run_script(tmp_path: Path, ledger: dict) -> tuple[int, str, str, Path]:
    ledger_path = tmp_path / "ledger.json"
    out_path = tmp_path / "dashboard.html"
    ledger_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, _SCRIPT, "--input", str(ledger_path), "--output", str(out_path)],
        capture_output=True, text=True, check=False,
    )
    return result.returncode, result.stdout, result.stderr, out_path


# ---------------------------------------------------------------------------
# Test 1: HTML file is generated
# ---------------------------------------------------------------------------

class TestHtmlGenerated:
    def test_exits_zero(self, tmp_path):
        ledger = _make_ledger([_row("refresh_repo_health", 0.88, "effective")])
        rc, _, stderr, _ = _run_script(tmp_path, ledger)
        assert rc == 0, stderr

    def test_output_file_exists(self, tmp_path):
        ledger = _make_ledger([_row("refresh_repo_health", 0.88, "effective")])
        rc, _, _, out = _run_script(tmp_path, ledger)
        assert rc == 0
        assert out.exists()

    def test_stdout_reports_output_path(self, tmp_path):
        ledger = _make_ledger([_row("refresh_repo_health", 0.88, "effective")])
        rc, stdout, _, out = _run_script(tmp_path, ledger)
        assert rc == 0
        assert str(out) in stdout

    def test_output_is_valid_html(self, tmp_path):
        ledger = _make_ledger([_row("refresh_repo_health", 0.88, "effective")])
        rc, _, _, out = _run_script(tmp_path, ledger)
        assert rc == 0
        content = out.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "<table>" in content
        assert "</html>" in content

    def test_empty_action_types_still_generates_file(self, tmp_path):
        ledger = _make_ledger([])
        rc, _, _, out = _run_script(tmp_path, ledger)
        assert rc == 0
        assert out.exists()

    def test_fail_closed_on_missing_input(self, tmp_path):
        out = tmp_path / "dashboard.html"
        result = subprocess.run(
            [sys.executable, _SCRIPT,
             "--input", str(tmp_path / "nonexistent.json"),
             "--output", str(out)],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode != 0
        assert not out.exists()


# ---------------------------------------------------------------------------
# Test 2: Table rows appear in deterministic order
# ---------------------------------------------------------------------------

class TestDeterministicRowOrder:
    def _content(self, tmp_path: Path, rows: list[dict]) -> str:
        ledger = _make_ledger(rows)
        rc, _, stderr, out = _run_script(tmp_path, ledger)
        assert rc == 0, stderr
        return out.read_text(encoding="utf-8")

    def test_higher_score_appears_before_lower(self, tmp_path):
        rows = [
            _row("refresh_repo_health",   0.50, "neutral"),
            _row("rerun_failed_task",     0.88, "effective"),
        ]
        content = self._content(tmp_path, rows)
        pos_high = content.index("rerun_failed_task")
        pos_low = content.index("refresh_repo_health")
        assert pos_high < pos_low

    def test_equal_score_sorted_by_action_type_alpha(self, tmp_path):
        rows = [
            _row("zzz_action", 0.70, "effective"),
            _row("aaa_action", 0.70, "effective"),
        ]
        content = self._content(tmp_path, rows)
        pos_a = content.index("aaa_action")
        pos_z = content.index("zzz_action")
        assert pos_a < pos_z

    def test_order_stable_across_two_runs(self, tmp_path):
        rows = [
            _row("refresh_repo_health",              0.88, "effective"),
            _row("regenerate_missing_artifact",      0.50, "neutral"),
            _row("run_determinism_regression_suite", 0.00, "ineffective"),
        ]
        ledger = _make_ledger(rows)
        ledger_path = tmp_path / "ledger.json"
        ledger_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")

        out1 = tmp_path / "run1.html"
        out2 = tmp_path / "run2.html"
        for out in (out1, out2):
            subprocess.run(
                [sys.executable, _SCRIPT, "--input", str(ledger_path), "--output", str(out)],
                check=True,
            )
        assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")

    def test_three_rows_all_distinct_scores_ordered(self, tmp_path):
        rows = [
            _row("b_action", 0.65, "effective"),
            _row("a_action", 0.88, "effective"),
            _row("c_action", 0.00, "ineffective"),
        ]
        content = self._content(tmp_path, rows)
        pos_a = content.index("a_action")   # score 0.88 — first
        pos_b = content.index("b_action")   # score 0.65 — second
        pos_c = content.index("c_action")   # score 0.00 — third
        assert pos_a < pos_b < pos_c


# ---------------------------------------------------------------------------
# Test 3: Classification coloring appears in HTML
# ---------------------------------------------------------------------------

class TestClassificationColoring:
    def _content(self, tmp_path: Path, rows: list[dict]) -> str:
        ledger = _make_ledger(rows)
        rc, _, stderr, out = _run_script(tmp_path, ledger)
        assert rc == 0, stderr
        return out.read_text(encoding="utf-8")

    def test_effective_row_has_green_color(self, tmp_path):
        content = self._content(tmp_path, [_row("act", 0.88, "effective")])
        assert "#2e7d32" in content

    def test_neutral_row_has_gray_color(self, tmp_path):
        content = self._content(tmp_path, [_row("act", 0.50, "neutral")])
        assert "#757575" in content

    def test_ineffective_row_has_red_color(self, tmp_path):
        content = self._content(tmp_path, [_row("act", 0.00, "ineffective")])
        assert "#c62828" in content

    def test_all_three_classifications_present(self, tmp_path):
        rows = [
            _row("act_e", 0.88, "effective"),
            _row("act_n", 0.50, "neutral"),
            _row("act_i", 0.00, "ineffective"),
        ]
        content = self._content(tmp_path, rows)
        assert "#2e7d32" in content
        assert "#757575" in content
        assert "#c62828" in content

    def test_html_escaping_in_action_type(self, tmp_path):
        """action_type containing HTML special chars must be escaped."""
        rows = [_row("<script>xss</script>", 0.88, "effective")]
        content = self._content(tmp_path, rows)
        assert "<script>" not in content
        assert "&lt;script&gt;" in content

    def test_summary_section_present(self, tmp_path):
        rows = [
            _row("act_e", 0.88, "effective"),
            _row("act_n", 0.50, "neutral"),
        ]
        content = self._content(tmp_path, rows)
        assert "Actions Tracked" in content
        assert "Effective" in content
        assert "Neutral" in content
        assert "Ineffective" in content


# ---------------------------------------------------------------------------
# Test 4: effect_deltas column renders correctly
# ---------------------------------------------------------------------------

class TestEffectDeltasRendering:
    def _content(self, tmp_path: Path, rows: list[dict]) -> str:
        ledger = _make_ledger(rows)
        rc, _, stderr, out = _run_script(tmp_path, ledger)
        assert rc == 0, stderr
        return out.read_text(encoding="utf-8")

    def _row_with_deltas(self, action_type: str, score: float, classification: str,
                         effect_deltas: dict) -> dict:
        r = _row(action_type, score, classification)
        r["effect_deltas"] = effect_deltas
        return r

    def test_effect_deltas_column_header_present(self, tmp_path):
        rows = [_row("act", 0.88, "effective")]
        content = self._content(tmp_path, rows)
        assert "Effect Deltas" in content

    def test_single_signal_delta_appears(self, tmp_path):
        rows = [self._row_with_deltas("act", 0.88, "effective",
                                      {"artifact_completeness": 0.50})]
        content = self._content(tmp_path, rows)
        assert "artifact_completeness" in content
        assert "+0.50" in content

    def test_negative_delta_rendered_with_sign(self, tmp_path):
        rows = [self._row_with_deltas("act", 0.88, "effective",
                                      {"recent_failures": -3.00})]
        content = self._content(tmp_path, rows)
        assert "recent_failures" in content
        assert "-3.00" in content

    def test_multiple_signals_deterministic_order(self, tmp_path):
        rows = [self._row_with_deltas("act", 0.88, "effective", {
            "zzz_signal": 0.10,
            "aaa_signal": 0.20,
            "mmm_signal": 0.30,
        })]
        content = self._content(tmp_path, rows)
        pos_a = content.index("aaa_signal")
        pos_m = content.index("mmm_signal")
        pos_z = content.index("zzz_signal")
        assert pos_a < pos_m < pos_z

    def test_empty_effect_deltas_renders_without_error(self, tmp_path):
        rows = [self._row_with_deltas("act", 0.50, "neutral", {})]
        rc, _, stderr, _ = _run_script(tmp_path, _make_ledger(rows))
        assert rc == 0, stderr

    def test_empty_effect_deltas_cell_is_empty(self, tmp_path):
        rows = [self._row_with_deltas("act", 0.50, "neutral", {})]
        content = self._content(tmp_path, rows)
        # Empty dict should render an empty <td></td>
        assert "<td></td>" in content

    def test_absent_effect_deltas_key_renders_gracefully(self, tmp_path):
        """Row missing effect_deltas entirely must not crash."""
        rows = [_row("act", 0.88, "effective")]
        rc, _, stderr, _ = _run_script(tmp_path, _make_ledger(rows))
        assert rc == 0, stderr

    def test_effect_deltas_values_html_escaped(self, tmp_path):
        """Signal names with special chars must be HTML-escaped."""
        rows = [self._row_with_deltas("act", 0.88, "effective",
                                      {"<sig>": 1.0})]
        content = self._content(tmp_path, rows)
        assert "<sig>" not in content
        assert "&lt;sig&gt;" in content

    def test_existing_columns_still_present_with_deltas(self, tmp_path):
        """Adding effect_deltas column must not remove any existing column."""
        rows = [self._row_with_deltas("act", 0.88, "effective",
                                      {"artifact_completeness": 0.5})]
        content = self._content(tmp_path, rows)
        for expected in ("Action Type", "Recommended", "Executed",
                         "Success Rate", "Effectiveness", "Classification"):
            assert expected in content, f"Missing column: {expected}"

    def test_two_runs_identical_with_effect_deltas(self, tmp_path):
        """Determinism: two runs with effect_deltas produce identical HTML."""
        rows = [self._row_with_deltas("act_a", 0.88, "effective",
                                      {"artifact_completeness": 0.5, "last_run_ok": 1.0}),
                self._row_with_deltas("act_b", 0.50, "neutral", {})]
        ledger = _make_ledger(rows)
        ledger_path = tmp_path / "ledger.json"
        ledger_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
        out1 = tmp_path / "run1.html"
        out2 = tmp_path / "run2.html"
        for out in (out1, out2):
            subprocess.run(
                [sys.executable, _SCRIPT, "--input", str(ledger_path), "--output", str(out)],
                check=True,
            )
        assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")
