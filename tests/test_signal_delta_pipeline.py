# SPDX-License-Identifier: MIT
"""End-to-end signal delta pipeline integration test.

Verifies the full pipeline:
  action execution records
    → build_action_effectiveness_ledger  (effect_deltas per action_type)
    → ledger JSON written to tmp file
    → styled dashboard CLI  (--ledger)
    → Portfolio Signal Impact section in HTML output

All expected values are hand-computed and deterministic.

Fixture design
--------------
Two action types with known signal changes:

  regenerate_missing_artifact (repo r1):
    artifact_completeness : 0.0 → 1.0  delta = +1.0
    recent_failures       : 4   → 0    delta = −4.0

  rerun_failed_task (repo r2):
    artifact_completeness : 0.5 → 1.0  delta = +0.5
    recent_failures       : 2   → 0    delta = −2.0

Portfolio roll-up (mean across action_types per signal):
    artifact_completeness  mean(+1.0, +0.5) = +0.75  → "+0.75"
    recent_failures        mean(−4.0, −2.0) = −3.00  → "−3.00"
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

from tests.cli_test_utils import run_script_cli

# ---------------------------------------------------------------------------
# Locate modules
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DASHBOARD_SCRIPT = str(_REPO_ROOT / "scripts" / "tier3_generate_html_dashboard_styled.py")

sys.path.insert(0, str(_REPO_ROOT / "src"))
from mcp_governance_orchestrator.action_effectiveness import build_action_effectiveness_ledger


# ---------------------------------------------------------------------------
# Fixture helpers — self-contained, independent of other test files
# ---------------------------------------------------------------------------

def _repo(repo_id: str, risk: str, health: float) -> dict:
    return {
        "repo_id": repo_id,
        "status": "failing",
        "health_score": health,
        "risk_level": risk,
        "signals": {},
        "open_issues": [],
        "recommended_actions": [],
        "action_history": [],
        "cooldowns": [],
        "escalations": [],
    }


def _repo_with_signals(
    repo_id: str,
    risk: str,
    health: float,
    *,
    artifact_completeness: float = 1.0,
    recent_failures: int = 0,
) -> dict:
    r = _repo(repo_id, risk, health)
    r["signals"] = {
        "last_run_ok": True,
        "artifact_completeness": artifact_completeness,
        "determinism_ok": True,
        "recent_failures": recent_failures,
        "stale_runs": 0,
    }
    return r


def _state(*repos) -> dict:
    return {
        "schema_version": "v1",
        "portfolio_id": "test",
        "generated_at": "",
        "summary": {},
        "repos": list(repos),
        "portfolio_recommendations": [],
    }


def _rec(before, after, executed) -> dict:
    return {"before_state": before, "after_state": after, "executed_actions": executed}


def _exe(action_type: str, repo_id: str) -> dict:
    return {"action_type": action_type, "repo_id": repo_id}


# ---------------------------------------------------------------------------
# Deterministic records — two action types with known signal deltas
# ---------------------------------------------------------------------------

def _make_records() -> list[dict]:
    """Return the two canonical pipeline test records.

    regenerate_missing_artifact on r1:
        artifact_completeness 0.0 → 1.0  (+1.0)
        recent_failures       4   → 0    (−4.0)

    rerun_failed_task on r2:
        artifact_completeness 0.5 → 1.0  (+0.5)
        recent_failures       2   → 0    (−2.0)
    """
    rec_a = _rec(
        _state(_repo_with_signals("r1", "high", 0.5,
                                   artifact_completeness=0.0, recent_failures=4)),
        _state(_repo_with_signals("r1", "low",  1.0,
                                   artifact_completeness=1.0, recent_failures=0)),
        [_exe("regenerate_missing_artifact", "r1")],
    )
    rec_b = _rec(
        _state(_repo_with_signals("r2", "high", 0.5,
                                   artifact_completeness=0.5, recent_failures=2)),
        _state(_repo_with_signals("r2", "low",  1.0,
                                   artifact_completeness=1.0, recent_failures=0)),
        [_exe("rerun_failed_task", "r2")],
    )
    return [rec_a, rec_b]


def _build_ledger() -> dict:
    return build_action_effectiveness_ledger(_make_records(), generated_at="")


def _ledger_row(ledger: dict, action_type: str) -> dict:
    return next(r for r in ledger["action_types"] if r["action_type"] == action_type)


# ---------------------------------------------------------------------------
# Helpers for CLI tests
# ---------------------------------------------------------------------------

def _write_empty_csv(path: Path) -> Path:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["Suggestion ID", "Description", "Example Metric", "Notes"]
        )
        writer.writeheader()
    return path


def _write_ledger(path: Path, ledger: dict) -> Path:
    path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    return path


def _run_dashboard_cli(
    tmp_path: Path, ledger: dict | None = None
) -> tuple[int, str, str, Path]:
    """Run the styled dashboard CLI and return (rc, stdout, stderr, html_path)."""
    csv_file = _write_empty_csv(tmp_path / "input.csv")
    html_file = tmp_path / "output.html"
    args = [
        "--csv", str(csv_file),
        "--output", str(html_file),
    ]
    if ledger is not None:
        ledger_file = _write_ledger(tmp_path / "ledger.json", ledger)
        args += ["--ledger", str(ledger_file)]
    result = run_script_cli(_DASHBOARD_SCRIPT, args)
    return result.returncode, result.stdout, result.stderr, html_file


# ===========================================================================
# 1. Ledger generation — verify effect_deltas values in the ledger
# ===========================================================================

class TestLedgerGeneration:
    def test_ledger_built_without_error(self):
        ledger = _build_ledger()
        assert isinstance(ledger, dict)
        assert "action_types" in ledger

    def test_both_action_types_present(self):
        ledger = _build_ledger()
        types = {r["action_type"] for r in ledger["action_types"]}
        assert "regenerate_missing_artifact" in types
        assert "rerun_failed_task" in types

    def test_regenerate_artifact_completeness_delta(self):
        row = _ledger_row(_build_ledger(), "regenerate_missing_artifact")
        assert row["effect_deltas"]["artifact_completeness"] == 1.0

    def test_regenerate_recent_failures_delta(self):
        row = _ledger_row(_build_ledger(), "regenerate_missing_artifact")
        assert row["effect_deltas"]["recent_failures"] == -4.0

    def test_rerun_artifact_completeness_delta(self):
        row = _ledger_row(_build_ledger(), "rerun_failed_task")
        assert row["effect_deltas"]["artifact_completeness"] == 0.5

    def test_rerun_recent_failures_delta(self):
        row = _ledger_row(_build_ledger(), "rerun_failed_task")
        assert row["effect_deltas"]["recent_failures"] == -2.0

    def test_effect_deltas_keys_alphabetically_ordered(self):
        for row in _build_ledger()["action_types"]:
            keys = list(row["effect_deltas"].keys())
            assert keys == sorted(keys), f"unordered keys in {row['action_type']}"

    def test_ledger_is_deterministic(self):
        """Two calls with identical input produce identical output."""
        assert _build_ledger() == _build_ledger()


# ===========================================================================
# 2. End-to-end CLI pipeline
# ===========================================================================

class TestEndToEndCLIPipeline:
    def test_cli_exits_zero_with_ledger(self, tmp_path):
        rc, _, stderr, _ = _run_dashboard_cli(tmp_path, _build_ledger())
        assert rc == 0, stderr

    def test_html_file_created(self, tmp_path):
        rc, _, _, out = _run_dashboard_cli(tmp_path, _build_ledger())
        assert rc == 0
        assert out.exists()

    def test_portfolio_signal_impact_section_present(self, tmp_path):
        _, _, _, out = _run_dashboard_cli(tmp_path, _build_ledger())
        assert "Portfolio Signal Impact" in out.read_text(encoding="utf-8")

    def test_artifact_completeness_signal_appears(self, tmp_path):
        _, _, _, out = _run_dashboard_cli(tmp_path, _build_ledger())
        assert "artifact_completeness" in out.read_text(encoding="utf-8")

    def test_recent_failures_signal_appears(self, tmp_path):
        _, _, _, out = _run_dashboard_cli(tmp_path, _build_ledger())
        assert "recent_failures" in out.read_text(encoding="utf-8")

    def test_artifact_completeness_mean_value(self, tmp_path):
        """Portfolio mean of artifact_completeness: (1.0+0.5)/2 = +0.75."""
        _, _, _, out = _run_dashboard_cli(tmp_path, _build_ledger())
        assert "+0.75" in out.read_text(encoding="utf-8")

    def test_recent_failures_mean_value(self, tmp_path):
        """Portfolio mean of recent_failures: (-4.0+-2.0)/2 = -3.00."""
        _, _, _, out = _run_dashboard_cli(tmp_path, _build_ledger())
        assert "-3.00" in out.read_text(encoding="utf-8")

    def test_signals_in_alphabetical_order(self, tmp_path):
        """artifact_completeness must appear before recent_failures."""
        _, _, _, out = _run_dashboard_cli(tmp_path, _build_ledger())
        content = out.read_text(encoding="utf-8")
        assert content.index("artifact_completeness") < content.index("recent_failures")

    def test_two_runs_produce_identical_html(self, tmp_path):
        ledger = _build_ledger()
        csv_file = _write_empty_csv(tmp_path / "input.csv")
        ledger_file = _write_ledger(tmp_path / "ledger.json", ledger)
        out1 = tmp_path / "run1.html"
        out2 = tmp_path / "run2.html"
        for out in (out1, out2):
            result = run_script_cli(
                _DASHBOARD_SCRIPT,
                [
                    "--csv", str(csv_file),
                    "--output", str(out),
                    "--ledger", str(ledger_file),
                ],
            )
            assert result.returncode == 0, result.stderr
        assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")

    def test_no_ledger_omits_signal_impact_section(self, tmp_path):
        """Without --ledger the section must not appear (backward compat)."""
        rc, _, _, out = _run_dashboard_cli(tmp_path, ledger=None)
        assert rc == 0
        assert "Portfolio Signal Impact" not in out.read_text(encoding="utf-8")

    def test_empty_ledger_action_types_renders_em_dash(self, tmp_path):
        """Ledger with no action_types → Portfolio Signal Impact shows em-dash."""
        empty_ledger = {
            "schema_version": "v1", "generated_at": "",
            "summary": {"actions_tracked": 0},
            "action_types": [],
        }
        _, _, _, out = _run_dashboard_cli(tmp_path, empty_ledger)
        content = out.read_text(encoding="utf-8")
        assert "Portfolio Signal Impact" in content
        assert "&#8212;" in content

    def test_values_formatted_as_signed_two_decimal_floats(self, tmp_path):
        """Spot-check that values use signed ±0.00 format (not raw floats)."""
        _, _, _, out = _run_dashboard_cli(tmp_path, _build_ledger())
        content = out.read_text(encoding="utf-8")
        # Neither raw Python float repr nor unsighed plain form should appear
        assert "0.75" in content   # present
        # Confirm the sign is there (i.e. "+0.75" not bare "0.75")
        assert "+0.75" in content
