# SPDX-License-Identifier: MIT
"""Contract tests for Action Effectiveness Ledger v1.

Verifies exact output schema, field types, ordering, and CLI behavior.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mcp_governance_orchestrator.action_effectiveness import (
    SCHEMA_VERSION,
    build_action_effectiveness_ledger,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CLI = str(_REPO_ROOT / "scripts" / "build_action_effectiveness_ledger.py")
_TS = "2025-01-01T00:00:00+00:00"

# ---------------------------------------------------------------------------
# Minimal fixture helpers
# ---------------------------------------------------------------------------

def _repo(repo_id: str, risk: str, health: float, actions: list | None = None) -> dict:
    return {
        "repo_id": repo_id,
        "status": "healthy",
        "health_score": health,
        "risk_level": risk,
        "signals": {},
        "open_issues": [],
        "recommended_actions": actions or [],
        "action_history": [],
        "cooldowns": [],
        "escalations": [],
    }


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


def _action(action_type: str, repo_id: str) -> dict:
    return {"action_type": action_type, "repo_id": repo_id}


# ---------------------------------------------------------------------------
# Top-level schema contract
# ---------------------------------------------------------------------------

_TOP_KEYS = {"schema_version", "generated_at", "summary", "action_types"}
_SUMMARY_KEYS = {"actions_tracked", "effective_actions", "ineffective_actions", "neutral_actions"}
_ROW_KEYS = {
    "action_type", "times_recommended", "times_executed", "success_rate",
    "avg_risk_delta", "avg_health_delta", "effectiveness_score",
    "recommended_priority_adjustment", "classification",
    "observed_effects",
}


class TestTopLevelContract:
    def _build(self, records=None):
        return build_action_effectiveness_ledger(records or [], generated_at="")

    def test_top_level_keys_exact(self):
        ledger = self._build()
        assert set(ledger.keys()) == _TOP_KEYS

    def test_schema_version_is_v1(self):
        assert self._build()["schema_version"] == "v1"
        assert self._build()["schema_version"] == SCHEMA_VERSION

    def test_generated_at_passthrough(self):
        ledger = build_action_effectiveness_ledger([], generated_at=_TS)
        assert ledger["generated_at"] == _TS

    def test_generated_at_default_empty_string(self):
        ledger = build_action_effectiveness_ledger([])
        assert ledger["generated_at"] == ""

    def test_summary_keys_exact(self):
        assert set(self._build()["summary"].keys()) == _SUMMARY_KEYS

    def test_summary_types_are_int(self):
        s = self._build()["summary"]
        for k in _SUMMARY_KEYS:
            assert isinstance(s[k], int), f"summary.{k} must be int"

    def test_action_types_is_list(self):
        assert isinstance(self._build()["action_types"], list)

    def test_empty_records_produces_empty_action_types(self):
        ledger = self._build()
        assert ledger["action_types"] == []
        assert ledger["summary"]["actions_tracked"] == 0


class TestActionTypeRowContract:
    def _row(self) -> dict:
        rec = _rec(
            _state(_repo("r1", "critical", 0.4)),
            _state(_repo("r1", "low", 1.0)),
            [_action("run_determinism_regression_suite", "r1")],
        )
        ledger = build_action_effectiveness_ledger([rec], generated_at="")
        return ledger["action_types"][0]

    def test_row_keys_exact(self):
        assert set(self._row().keys()) == _ROW_KEYS

    def test_action_type_is_str(self):
        assert isinstance(self._row()["action_type"], str)

    def test_times_fields_are_int(self):
        row = self._row()
        assert isinstance(row["times_recommended"], int)
        assert isinstance(row["times_executed"], int)

    def test_float_fields_are_float(self):
        row = self._row()
        for k in ("success_rate", "avg_risk_delta", "avg_health_delta",
                  "effectiveness_score", "recommended_priority_adjustment"):
            assert isinstance(row[k], float), f"{k} must be float"

    def test_classification_valid_values(self):
        row = self._row()
        assert row["classification"] in {"effective", "neutral", "ineffective"}


# ---------------------------------------------------------------------------
# Deterministic ordering
# ---------------------------------------------------------------------------

class TestOrdering:
    def _ledger_multi(self) -> dict:
        before = _state(
            _repo("r1", "critical", 0.4),
            _repo("r2", "high", 0.6),
            _repo("r3", "medium", 0.8),
        )
        after = _state(
            _repo("r1", "low", 1.0),
            _repo("r2", "low", 1.0),
            _repo("r3", "low", 1.0),
        )
        executed = [
            _action("run_determinism_regression_suite", "r1"),
            _action("rerun_failed_task", "r2"),
            _action("regenerate_missing_artifact", "r3"),
        ]
        return build_action_effectiveness_ledger([_rec(before, after, executed)], generated_at="")

    def test_action_types_sorted_alphabetically(self):
        rows = self._ledger_multi()["action_types"]
        names = [r["action_type"] for r in rows]
        assert names == sorted(names)

    def test_stable_across_calls(self):
        a = self._ledger_multi()["action_types"]
        b = self._ledger_multi()["action_types"]
        assert [r["action_type"] for r in a] == [r["action_type"] for r in b]


# ---------------------------------------------------------------------------
# Summary counts
# ---------------------------------------------------------------------------

class TestSummaryCounts:
    def test_actions_tracked_equals_len_action_types(self):
        rec = _rec(
            _state(_repo("r1", "critical", 0.4), _repo("r2", "low", 1.0)),
            _state(_repo("r1", "low", 1.0), _repo("r2", "high", 0.5)),
            [_action("run_determinism_regression_suite", "r1"),
             _action("rerun_failed_task", "r2")],
        )
        ledger = build_action_effectiveness_ledger([rec], generated_at="")
        assert ledger["summary"]["actions_tracked"] == len(ledger["action_types"])

    def test_summary_counts_match_classifications(self):
        before = _state(
            _repo("r1", "critical", 0.4),
            _repo("r2", "low", 1.0),
            _repo("r3", "medium", 0.8),
        )
        after = _state(
            _repo("r1", "low", 1.0),   # big improvement → effective
            _repo("r2", "low", 1.0),   # no change → ineffective
            _repo("r3", "low", 1.0),   # small improvement
        )
        executed = [
            _action("run_determinism_regression_suite", "r1"),
            _action("refresh_repo_health", "r2"),
            _action("regenerate_missing_artifact", "r3"),
        ]
        ledger = build_action_effectiveness_ledger([_rec(before, after, executed)], generated_at="")
        eff = sum(1 for r in ledger["action_types"] if r["classification"] == "effective")
        neu = sum(1 for r in ledger["action_types"] if r["classification"] == "neutral")
        ineff = sum(1 for r in ledger["action_types"] if r["classification"] == "ineffective")
        assert ledger["summary"]["effective_actions"] == eff
        assert ledger["summary"]["neutral_actions"] == neu
        assert ledger["summary"]["ineffective_actions"] == ineff
        assert eff + neu + ineff == ledger["summary"]["actions_tracked"]


# ---------------------------------------------------------------------------
# times_recommended counts unrequested recommendations
# ---------------------------------------------------------------------------

class TestTimesRecommended:
    def test_counts_recommendations_in_before_state(self):
        action_obj = {
            "action_id": "run_det_r1",
            "action_type": "run_determinism_regression_suite",
            "priority": 0.95,
            "reason": "test",
            "eligible": True,
            "blocked_by": [],
            "task_binding": {"task_id": "t", "args": {}},
        }
        before = _state(_repo("r1", "critical", 0.4, actions=[action_obj]))
        after = _state(_repo("r1", "low", 1.0))
        # Executed a different action — recommendation still counted.
        rec = _rec(before, after, [_action("rerun_failed_task", "r1")])
        ledger = build_action_effectiveness_ledger([rec], generated_at="")
        rows = {r["action_type"]: r for r in ledger["action_types"]}
        assert rows["run_determinism_regression_suite"]["times_recommended"] == 1
        assert rows["run_determinism_regression_suite"]["times_executed"] == 0

    def test_zero_execution_type_has_zero_success_rate(self):
        action_obj = {
            "action_id": "run_det_r1",
            "action_type": "run_determinism_regression_suite",
            "priority": 0.95,
            "reason": "test",
            "eligible": True,
            "blocked_by": [],
            "task_binding": {"task_id": "t", "args": {}},
        }
        before = _state(_repo("r1", "critical", 0.4, actions=[action_obj]))
        after = _state(_repo("r1", "low", 1.0))
        ledger = build_action_effectiveness_ledger(
            [_rec(before, after, [])], generated_at=""
        )
        row = ledger["action_types"][0]
        assert row["times_executed"] == 0
        assert row["success_rate"] == 0.0
        assert row["effectiveness_score"] == 0.0


# ---------------------------------------------------------------------------
# Fail-closed validation
# ---------------------------------------------------------------------------

class TestFailClosed:
    def test_non_list_input_raises(self):
        with pytest.raises(ValueError):
            build_action_effectiveness_ledger({"bad": "input"})  # type: ignore[arg-type]

    def test_missing_key_raises(self):
        with pytest.raises(ValueError, match="missing key"):
            build_action_effectiveness_ledger([{"before_state": _state()}])

    def test_repo_id_missing_in_before_state_raises(self):
        before = _state(_repo("r1", "low", 1.0))
        after = _state(_repo("r1", "low", 1.0))
        with pytest.raises(ValueError, match="not found in before_state"):
            build_action_effectiveness_ledger(
                [_rec(before, after, [_action("rerun_failed_task", "no-such-repo")])]
            )

    def test_repo_id_missing_in_after_state_raises(self):
        before = _state(_repo("r1", "low", 1.0))
        after = _state(_repo("r2", "low", 1.0))  # r1 absent
        with pytest.raises(ValueError, match="not found in after_state"):
            build_action_effectiveness_ledger(
                [_rec(before, after, [_action("rerun_failed_task", "r1")])]
            )

    def test_executed_action_missing_action_type_raises(self):
        before = _state(_repo("r1", "low", 1.0))
        after = _state(_repo("r1", "low", 1.0))
        with pytest.raises(ValueError):
            build_action_effectiveness_ledger(
                [_rec(before, after, [{"repo_id": "r1"}])]
            )

    def test_executed_action_missing_repo_id_raises(self):
        before = _state(_repo("r1", "low", 1.0))
        after = _state(_repo("r1", "low", 1.0))
        with pytest.raises(ValueError):
            build_action_effectiveness_ledger(
                [_rec(before, after, [{"action_type": "rerun_failed_task"}])]
            )


# ---------------------------------------------------------------------------
# CLI contract
# ---------------------------------------------------------------------------

def _run_cli(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, _CLI] + args,
        capture_output=True, text=True,
    )


class TestCLIContract:
    def _write_records(self, path: Path, records: list) -> None:
        path.write_text(json.dumps(records), encoding="utf-8")

    def test_cli_succeeds_on_valid_input(self, tmp_path):
        inp = tmp_path / "records.json"
        out = tmp_path / "ledger.json"
        before = _state(_repo("r1", "critical", 0.4))
        after = _state(_repo("r1", "low", 1.0))
        self._write_records(inp, [_rec(before, after, [_action("run_determinism_regression_suite", "r1")])])
        r = _run_cli(["--input", str(inp), "--output", str(out)])
        assert r.returncode == 0
        assert out.exists()

    def test_cli_output_schema_version_v1(self, tmp_path):
        inp = tmp_path / "records.json"
        out = tmp_path / "ledger.json"
        self._write_records(inp, [])
        _run_cli(["--input", str(inp), "--output", str(out)])
        ledger = json.loads(out.read_text())
        assert ledger["schema_version"] == "v1"

    def test_cli_generated_at_passthrough(self, tmp_path):
        inp = tmp_path / "records.json"
        out = tmp_path / "ledger.json"
        self._write_records(inp, [])
        _run_cli(["--input", str(inp), "--output", str(out), "--generated-at", _TS])
        assert json.loads(out.read_text())["generated_at"] == _TS

    def test_cli_default_generated_at_empty(self, tmp_path):
        inp = tmp_path / "records.json"
        out = tmp_path / "ledger.json"
        self._write_records(inp, [])
        _run_cli(["--input", str(inp), "--output", str(out)])
        assert json.loads(out.read_text())["generated_at"] == ""

    def test_cli_missing_input_fails(self, tmp_path):
        r = _run_cli(["--input", str(tmp_path / "no.json"), "--output", str(tmp_path / "out.json")])
        assert r.returncode != 0

    def test_cli_malformed_json_fails(self, tmp_path):
        inp = tmp_path / "bad.json"
        inp.write_text("{bad", encoding="utf-8")
        r = _run_cli(["--input", str(inp), "--output", str(tmp_path / "out.json")])
        assert r.returncode != 0

    def test_cli_non_list_input_fails(self, tmp_path):
        inp = tmp_path / "obj.json"
        inp.write_text(json.dumps({"key": "val"}), encoding="utf-8")
        r = _run_cli(["--input", str(inp), "--output", str(tmp_path / "out.json")])
        assert r.returncode != 0

    def test_cli_byte_identical_with_fixed_generated_at(self, tmp_path):
        inp = tmp_path / "records.json"
        before = _state(_repo("r1", "critical", 0.4))
        after = _state(_repo("r1", "low", 1.0))
        self._write_records(inp, [_rec(before, after, [_action("run_determinism_regression_suite", "r1")])])
        out1 = tmp_path / "out1.json"
        out2 = tmp_path / "out2.json"
        for out in (out1, out2):
            _run_cli(["--input", str(inp), "--output", str(out), "--generated-at", _TS])
        assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")

    def test_cli_byte_identical_default_no_clock(self, tmp_path):
        inp = tmp_path / "records.json"
        before = _state(_repo("r1", "critical", 0.4))
        after = _state(_repo("r1", "low", 1.0))
        self._write_records(inp, [_rec(before, after, [_action("run_determinism_regression_suite", "r1")])])
        out1 = tmp_path / "out1.json"
        out2 = tmp_path / "out2.json"
        for out in (out1, out2):
            _run_cli(["--input", str(inp), "--output", str(out)])
        assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")
