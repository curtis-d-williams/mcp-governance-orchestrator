# SPDX-License-Identifier: MIT
"""Regression tests for scripts/build_action_effect_attribution_dashboard.py.

All fixtures are built in tmp_path. No real ledger files are read.
All tests are deterministic.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = str(_REPO_ROOT / "scripts" / "build_action_effect_attribution_dashboard.py")


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_row(
    action_type: str,
    effectiveness_score: float,
    classification: str,
    times_executed: int = 1,
    success_rate: float = 1.0,
    observed_effects: list | None = None,
) -> dict:
    return {
        "action_type": action_type,
        "times_executed": times_executed,
        "success_rate": success_rate,
        "effectiveness_score": effectiveness_score,
        "observed_effects": observed_effects if observed_effects is not None else [],
        "classification": classification,
    }


def _make_ledger(rows: list[dict]) -> dict:
    effective = sum(1 for r in rows if r.get("classification") == "effective")
    neutral = sum(1 for r in rows if r.get("classification") == "neutral")
    ineffective = sum(1 for r in rows if r.get("classification") == "ineffective")
    return {
        "schema_version": "v1",
        "generated_at": "",
        "summary": {
            "actions_tracked": len(rows),
            "effective_actions": effective,
            "neutral_actions": neutral,
            "ineffective_actions": ineffective,
        },
        "action_types": rows,
    }


def _run(tmp_path: Path, ledger: dict) -> tuple[int, str, str, Path]:
    ledger_path = tmp_path / "ledger.json"
    out_path = tmp_path / "dashboard.html"
    ledger_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, _SCRIPT,
         "--input", str(ledger_path),
         "--output", str(out_path)],
        capture_output=True, text=True, check=False,
    )
    return result.returncode, result.stdout, result.stderr, out_path


# ---------------------------------------------------------------------------
# 1. HTML file created successfully
# ---------------------------------------------------------------------------

class TestHtmlCreated:
    def test_exits_zero(self, tmp_path):
        ledger = _make_ledger([_make_row("refresh_repo_health", 0.88, "effective")])
        rc, _, stderr, _ = _run(tmp_path, ledger)
        assert rc == 0, stderr

    def test_output_file_exists(self, tmp_path):
        ledger = _make_ledger([_make_row("refresh_repo_health", 0.88, "effective")])
        rc, _, _, out = _run(tmp_path, ledger)
        assert rc == 0
        assert out.exists()

    def test_stdout_names_output_path(self, tmp_path):
        ledger = _make_ledger([_make_row("refresh_repo_health", 0.88, "effective")])
        rc, stdout, _, out = _run(tmp_path, ledger)
        assert rc == 0
        assert str(out) in stdout

    def test_output_is_html(self, tmp_path):
        ledger = _make_ledger([_make_row("refresh_repo_health", 0.88, "effective")])
        rc, _, _, out = _run(tmp_path, ledger)
        assert rc == 0
        content = out.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "<table>" in content
        assert "</html>" in content

    def test_title_is_action_effect_attribution(self, tmp_path):
        ledger = _make_ledger([_make_row("refresh_repo_health", 0.88, "effective")])
        rc, _, _, out = _run(tmp_path, ledger)
        assert rc == 0
        assert "Action Effect Attribution" in out.read_text(encoding="utf-8")

    def test_empty_action_types_still_generates_file(self, tmp_path):
        ledger = _make_ledger([])
        rc, _, _, out = _run(tmp_path, ledger)
        assert rc == 0
        assert out.exists()


# ---------------------------------------------------------------------------
# 2. Deterministic ordering (two identical runs produce identical output)
# ---------------------------------------------------------------------------

class TestDeterministicOrdering:
    def test_higher_score_appears_before_lower(self, tmp_path):
        rows = [
            _make_row("low_score",  0.30, "ineffective"),
            _make_row("high_score", 0.88, "effective"),
        ]
        _, _, _, out = _run(tmp_path, _make_ledger(rows))
        content = out.read_text(encoding="utf-8")
        assert content.index("high_score") < content.index("low_score")

    def test_equal_score_sorted_by_action_type_alpha(self, tmp_path):
        rows = [
            _make_row("zzz_action", 0.65, "effective"),
            _make_row("aaa_action", 0.65, "effective"),
        ]
        _, _, _, out = _run(tmp_path, _make_ledger(rows))
        content = out.read_text(encoding="utf-8")
        assert content.index("aaa_action") < content.index("zzz_action")

    def test_two_runs_produce_identical_output(self, tmp_path):
        rows = [
            _make_row("refresh_repo_health",              0.88, "effective",
                      observed_effects=["artifact_completeness", "last_run_ok"]),
            _make_row("regenerate_missing_artifact",      0.50, "neutral"),
            _make_row("run_determinism_regression_suite", 0.00, "ineffective"),
        ]
        ledger = _make_ledger(rows)
        ledger_path = tmp_path / "ledger.json"
        ledger_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")

        out1 = tmp_path / "run1.html"
        out2 = tmp_path / "run2.html"
        for out in (out1, out2):
            r = subprocess.run(
                [sys.executable, _SCRIPT,
                 "--input", str(ledger_path), "--output", str(out)],
                check=True,
            )
        assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 3. Classification coloring appears
# ---------------------------------------------------------------------------

class TestClassificationColoring:
    def _content(self, tmp_path: Path, rows: list[dict]) -> str:
        rc, _, stderr, out = _run(tmp_path, _make_ledger(rows))
        assert rc == 0, stderr
        return out.read_text(encoding="utf-8")

    def test_effective_row_has_green_background(self, tmp_path):
        content = self._content(tmp_path, [_make_row("act", 0.88, "effective")])
        assert "#e8f5e9" in content

    def test_neutral_row_has_gray_background(self, tmp_path):
        content = self._content(tmp_path, [_make_row("act", 0.50, "neutral")])
        assert "#f5f5f5" in content

    def test_ineffective_row_has_red_background(self, tmp_path):
        content = self._content(tmp_path, [_make_row("act", 0.00, "ineffective")])
        assert "#ffebee" in content

    def test_all_three_colors_present_when_all_classifications_present(self, tmp_path):
        rows = [
            _make_row("act_e", 0.88, "effective"),
            _make_row("act_n", 0.50, "neutral"),
            _make_row("act_i", 0.00, "ineffective"),
        ]
        content = self._content(tmp_path, rows)
        assert "#e8f5e9" in content
        assert "#f5f5f5" in content
        assert "#ffebee" in content


# ---------------------------------------------------------------------------
# 4. Observed effects rendered correctly
# ---------------------------------------------------------------------------

class TestObservedEffectsRendering:
    def _content(self, tmp_path: Path, rows: list[dict]) -> str:
        rc, _, stderr, out = _run(tmp_path, _make_ledger(rows))
        assert rc == 0, stderr
        return out.read_text(encoding="utf-8")

    def test_single_effect_appears_in_table(self, tmp_path):
        rows = [_make_row("act", 0.88, "effective",
                           observed_effects=["artifact_completeness"])]
        assert "artifact_completeness" in self._content(tmp_path, rows)

    def test_multiple_effects_rendered_comma_separated(self, tmp_path):
        rows = [_make_row("act", 0.88, "effective",
                           observed_effects=["artifact_completeness", "last_run_ok"])]
        content = self._content(tmp_path, rows)
        assert "artifact_completeness, last_run_ok" in content

    def test_empty_observed_effects_renders_without_error(self, tmp_path):
        rows = [_make_row("act", 0.50, "neutral", observed_effects=[])]
        rc, _, stderr, _ = _run(tmp_path, _make_ledger(rows))
        assert rc == 0, stderr

    def test_observed_effects_column_header_present(self, tmp_path):
        rows = [_make_row("act", 0.88, "effective")]
        assert "Observed Effects" in self._content(tmp_path, rows)


# ---------------------------------------------------------------------------
# 5. HTML escaping
# ---------------------------------------------------------------------------

class TestHtmlEscaping:
    def test_action_type_with_angle_brackets_escaped(self, tmp_path):
        rows = [_make_row("<script>xss</script>", 0.88, "effective")]
        rc, _, _, out = _run(tmp_path, _make_ledger(rows))
        assert rc == 0
        content = out.read_text(encoding="utf-8")
        assert "<script>" not in content
        assert "&lt;script&gt;" in content

    def test_observed_effect_with_special_chars_escaped(self, tmp_path):
        rows = [_make_row("act", 0.88, "effective",
                           observed_effects=['<b>effect</b>'])]
        rc, _, _, out = _run(tmp_path, _make_ledger(rows))
        assert rc == 0
        content = out.read_text(encoding="utf-8")
        assert "<b>effect</b>" not in content
        assert "&lt;b&gt;" in content


# ---------------------------------------------------------------------------
# 6. Fail closed when ledger missing or malformed
# ---------------------------------------------------------------------------

class TestFailClosed:
    def test_missing_ledger_exits_nonzero(self, tmp_path):
        out = tmp_path / "dashboard.html"
        result = subprocess.run(
            [sys.executable, _SCRIPT,
             "--input", str(tmp_path / "nonexistent.json"),
             "--output", str(out)],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode != 0
        assert not out.exists()

    def test_malformed_json_exits_nonzero(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json", encoding="utf-8")
        out = tmp_path / "dashboard.html"
        result = subprocess.run(
            [sys.executable, _SCRIPT,
             "--input", str(bad), "--output", str(out)],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode != 0

    def test_missing_action_types_key_exits_nonzero(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"schema_version": "v1"}), encoding="utf-8")
        out = tmp_path / "dashboard.html"
        result = subprocess.run(
            [sys.executable, _SCRIPT,
             "--input", str(bad), "--output", str(out)],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode != 0

    def test_action_types_not_a_list_exits_nonzero(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"action_types": "not-a-list"}), encoding="utf-8")
        out = tmp_path / "dashboard.html"
        result = subprocess.run(
            [sys.executable, _SCRIPT,
             "--input", str(bad), "--output", str(out)],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode != 0


# ---------------------------------------------------------------------------
# 7. Works when observed_effects list is empty
# ---------------------------------------------------------------------------

class TestEmptyObservedEffects:
    def test_row_with_empty_effects_renders(self, tmp_path):
        rows = [_make_row("refresh_repo_health", 0.88, "effective", observed_effects=[])]
        rc, _, stderr, out = _run(tmp_path, _make_ledger(rows))
        assert rc == 0, stderr
        assert out.exists()

    def test_row_with_empty_effects_does_not_render_comma(self, tmp_path):
        """Empty list must not produce a stray comma."""
        rows = [_make_row("refresh_repo_health", 0.88, "effective", observed_effects=[])]
        rc, _, _, out = _run(tmp_path, _make_ledger(rows))
        assert rc == 0
        content = out.read_text(encoding="utf-8")
        # The observed_effects cell should be empty — no comma
        assert ",</td>" not in content

    def test_absent_observed_effects_key_renders_gracefully(self, tmp_path):
        """Row missing the observed_effects key entirely must not crash."""
        row = {
            "action_type": "refresh_repo_health",
            "times_executed": 1,
            "success_rate": 0.9,
            "effectiveness_score": 0.75,
            "classification": "effective",
            # deliberately omitting "observed_effects"
        }
        ledger = _make_ledger([])
        ledger["action_types"] = [row]
        rc, _, stderr, out = _run(tmp_path, ledger)
        assert rc == 0, stderr
        assert out.exists()


# ---------------------------------------------------------------------------
# 8. effect_deltas column renders correctly
# ---------------------------------------------------------------------------

def _make_row_with_deltas(
    action_type: str,
    effectiveness_score: float,
    classification: str,
    effect_deltas: dict | None = None,
) -> dict:
    row = _make_row(action_type, effectiveness_score, classification)
    row["effect_deltas"] = effect_deltas if effect_deltas is not None else {}
    return row


class TestEffectDeltasRendering:
    def _content(self, tmp_path: Path, rows: list[dict]) -> str:
        rc, _, stderr, out = _run(tmp_path, _make_ledger(rows))
        assert rc == 0, stderr
        return out.read_text(encoding="utf-8")

    def test_effect_deltas_column_header_present(self, tmp_path):
        rows = [_make_row("act", 0.88, "effective")]
        assert "Effect Deltas" in self._content(tmp_path, rows)

    def test_single_signal_positive_delta(self, tmp_path):
        rows = [_make_row_with_deltas("act", 0.88, "effective",
                                      {"artifact_completeness": 0.50})]
        content = self._content(tmp_path, rows)
        assert "artifact_completeness" in content
        assert "+0.50" in content

    def test_negative_delta_rendered_with_sign(self, tmp_path):
        rows = [_make_row_with_deltas("act", 0.88, "effective",
                                      {"recent_failures": -3.00})]
        content = self._content(tmp_path, rows)
        assert "recent_failures" in content
        assert "-3.00" in content

    def test_multiple_signals_alphabetical_order(self, tmp_path):
        rows = [_make_row_with_deltas("act", 0.88, "effective", {
            "zzz_signal": 0.10,
            "aaa_signal": 0.20,
            "mmm_signal": 0.30,
        })]
        content = self._content(tmp_path, rows)
        assert content.index("aaa_signal") < content.index("mmm_signal") < content.index("zzz_signal")

    def test_empty_dict_renders_em_dash(self, tmp_path):
        rows = [_make_row_with_deltas("act", 0.50, "neutral", {})]
        content = self._content(tmp_path, rows)
        assert "&#8212;" in content

    def test_absent_effect_deltas_key_renders_em_dash(self, tmp_path):
        """Row missing effect_deltas key entirely must render em-dash, not crash."""
        rows = [_make_row("act", 0.88, "effective")]
        content = self._content(tmp_path, rows)
        assert "&#8212;" in content

    def test_signal_names_html_escaped(self, tmp_path):
        rows = [_make_row_with_deltas("act", 0.88, "effective",
                                      {"<xss>": 1.0})]
        content = self._content(tmp_path, rows)
        assert "<xss>" not in content
        assert "&lt;xss&gt;" in content

    def test_existing_columns_intact(self, tmp_path):
        rows = [_make_row_with_deltas("act", 0.88, "effective",
                                      {"artifact_completeness": 0.5})]
        content = self._content(tmp_path, rows)
        for header in ("Action Type", "Times Executed", "Success Rate",
                       "Effectiveness Score", "Observed Effects", "Classification"):
            assert header in content, f"missing column: {header}"

    def test_deterministic_across_two_runs(self, tmp_path):
        rows = [
            _make_row_with_deltas("act_a", 0.88, "effective",
                                  {"artifact_completeness": 0.5, "last_run_ok": 1.0}),
            _make_row_with_deltas("act_b", 0.50, "neutral", {}),
        ]
        ledger = _make_ledger(rows)
        ledger_path = tmp_path / "ledger.json"
        ledger_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
        out1 = tmp_path / "run1.html"
        out2 = tmp_path / "run2.html"
        for out in (out1, out2):
            subprocess.run(
                [sys.executable, _SCRIPT,
                 "--input", str(ledger_path), "--output", str(out)],
                check=True,
            )
        assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")

    def test_two_decimal_precision(self, tmp_path):
        rows = [_make_row_with_deltas("act", 0.88, "effective",
                                      {"sig": 0.123456})]
        content = self._content(tmp_path, rows)
        assert "+0.12" in content
        assert "0.123456" not in content
