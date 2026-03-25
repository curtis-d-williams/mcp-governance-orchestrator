# SPDX-License-Identifier: MIT
"""Tests for scripts/list_portfolio_actions.py.

All fixtures are built in-process; no real portfolio_state.json files are read.
Output is deterministic across repeated calls with identical inputs.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import importlib.util

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = str(_REPO_ROOT / "scripts" / "list_portfolio_actions.py")

# Import private helpers directly from the script for unit-level tests.
_spec = importlib.util.spec_from_file_location(
    "list_portfolio_actions",
    str(_REPO_ROOT / "scripts" / "list_portfolio_actions.py"),
)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

_collect_actions = _mod._collect_actions
_preconditions_met = _mod._preconditions_met
_fmt_json = _mod._fmt_json
_fmt_text = _mod._fmt_text
_fmt_text_ledger = _mod._fmt_text_ledger
_load_state = _mod._load_state
_load_ledger = _mod._load_ledger
_build_ledger_index = _mod._build_ledger_index
_annotate_with_ledger = _mod._annotate_with_ledger


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_action(
    action_id: str,
    action_type: str,
    priority: float,
    eligible: bool = True,
    blocked_by: list | None = None,
    task_id: str = "some_task",
) -> dict[str, Any]:
    return {
        "action_id": action_id,
        "action_type": action_type,
        "priority": priority,
        "reason": "test reason",
        "eligible": eligible,
        "blocked_by": blocked_by or [],
        "task_binding": {"task_id": task_id, "args": {}},
    }


def _make_state(repos: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "v1",
        "portfolio_id": "portfolio-test",
        "generated_at": "",
        "summary": {
            "repo_count": len(repos),
            "repos_healthy": 0,
            "repos_degraded": 0,
            "repos_failing": 0,
            "repos_stale": 0,
            "open_issues_total": 0,
            "eligible_actions_total": 0,
            "blocked_actions_total": 0,
        },
        "repos": repos,
        "portfolio_recommendations": [],
    }


def _make_repo(
    repo_id: str,
    actions: list[dict[str, Any]],
    status: str = "healthy",
) -> dict[str, Any]:
    return {
        "repo_id": repo_id,
        "status": status,
        "health_score": 1.0,
        "risk_level": "low",
        "signals": {
            "last_run_ok": True,
            "artifact_completeness": 1.0,
            "determinism_ok": True,
            "recent_failures": 0,
            "stale_runs": 0,
        },
        "open_issues": [],
        "recommended_actions": actions,
        "action_history": [],
        "cooldowns": [],
        "escalations": [],
    }


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, _SCRIPT] + args,
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# Unit tests via importable helpers
# ---------------------------------------------------------------------------

class TestLoadState:
    def test_valid_state_loads(self, tmp_path):
        p = tmp_path / "state.json"
        _write_state(p, _make_state([]))
        state = _load_state(p)
        assert state["schema_version"] == "v1"

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(ValueError, match="not found"):
            _load_state(tmp_path / "no_such_file.json")

    def test_malformed_json_raises(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(ValueError, match="malformed"):
            _load_state(p)

    def test_non_object_raises(self, tmp_path):
        p = tmp_path / "arr.json"
        p.write_text("[1,2,3]", encoding="utf-8")
        with pytest.raises(ValueError, match="JSON object"):
            _load_state(p)

    def test_missing_repos_key_raises(self, tmp_path):
        p = tmp_path / "nokey.json"
        p.write_text(json.dumps({"schema_version": "v1"}), encoding="utf-8")
        with pytest.raises(ValueError, match="repos"):
            _load_state(p)


class TestCollectActions:
    def _state_two_repos(self) -> dict:
        return _make_state([
            _make_repo("aaa", [
                _make_action("run_det_aaa", "run_determinism_regression_suite", 0.95),
                _make_action("rerun_aaa", "rerun_failed_task", 0.80),
            ], status="failing"),
            _make_repo("bbb", [
                _make_action("refresh_bbb", "refresh_repo_health", 0.55),
                _make_action("regen_bbb", "regenerate_missing_artifact", 0.70,
                             eligible=False),  # ineligible
            ], status="stale"),
        ])

    def test_returns_only_eligible(self):
        actions = _collect_actions(self._state_two_repos(), None)
        assert all(a["eligible"] for a in actions)

    def test_ineligible_excluded(self):
        actions = _collect_actions(self._state_two_repos(), None)
        ids = [a["action_id"] for a in actions]
        assert "regen_bbb" not in ids

    def test_repo_id_field_added(self):
        actions = _collect_actions(self._state_two_repos(), None)
        for a in actions:
            assert "repo_id" in a

    def test_priority_desc_ordering(self):
        actions = _collect_actions(self._state_two_repos(), None)
        priorities = [a["priority"] for a in actions]
        assert priorities == sorted(priorities, reverse=True)

    def test_repo_filter(self):
        actions = _collect_actions(self._state_two_repos(), "aaa")
        assert all(a["repo_id"] == "aaa" for a in actions)
        assert len(actions) == 2

    def test_repo_filter_unknown_returns_empty(self):
        actions = _collect_actions(self._state_two_repos(), "zzz-no-such")
        assert actions == []

    def test_empty_repos_returns_empty(self):
        actions = _collect_actions(_make_state([]), None)
        assert actions == []

    def test_does_not_mutate_input_state(self):
        state = self._state_two_repos()
        import copy
        original = copy.deepcopy(state)
        _collect_actions(state, None)
        assert state == original


class TestDeterministicOrdering:
    """When priorities tie, sort falls through action_type → action_id → repo_id."""

    def _tied_state(self) -> dict:
        # Two repos, same priority on all actions — tie-breaks must be stable.
        return _make_state([
            _make_repo("zzz", [
                _make_action("zzz_regen", "regenerate_missing_artifact", 0.70),
                _make_action("zzz_refresh", "refresh_repo_health", 0.70),
            ]),
            _make_repo("aaa", [
                _make_action("aaa_regen", "regenerate_missing_artifact", 0.70),
                _make_action("aaa_refresh", "refresh_repo_health", 0.70),
            ]),
        ])

    def test_tied_priority_sorted_by_action_type(self):
        actions = _collect_actions(self._tied_state(), None)
        # "refresh_repo_health" < "regenerate_missing_artifact" alphabetically ('f' < 'g')
        assert actions[0]["action_type"] == "refresh_repo_health"
        assert actions[1]["action_type"] == "refresh_repo_health"

    def test_tied_priority_and_type_sorted_by_action_id(self):
        actions = _collect_actions(self._tied_state(), None)
        # refresh_repo_health comes first in type sort; check aaa before zzz within that type
        refresh = [a for a in actions if a["action_type"] == "refresh_repo_health"]
        assert refresh[0]["action_id"] == "aaa_refresh"
        assert refresh[1]["action_id"] == "zzz_refresh"

    def test_tied_priority_and_id_sorted_by_repo_id(self):
        # Two repos same action_id (different repos) — last tiebreak is repo_id.
        state = _make_state([
            _make_repo("zzz", [_make_action("shared_action", "refresh_repo_health", 0.55)]),
            _make_repo("aaa", [_make_action("shared_action", "refresh_repo_health", 0.55)]),
        ])
        actions = _collect_actions(state, None)
        assert actions[0]["repo_id"] == "aaa"
        assert actions[1]["repo_id"] == "zzz"

    def test_stable_across_repeated_calls(self):
        state = self._tied_state()
        r1 = _collect_actions(state, None)
        r2 = _collect_actions(state, None)
        assert [a["action_id"] for a in r1] == [a["action_id"] for a in r2]


class TestFormatters:
    _ACTIONS = [
        {"action_id": "run_det_aaa", "action_type": "run_determinism_regression_suite",
         "priority": 0.95, "repo_id": "repo-aaa", "eligible": True, "blocked_by": [],
         "reason": "test", "task_binding": {"task_id": "t", "args": {}}},
        {"action_id": "rerun_aaa", "action_type": "rerun_failed_task",
         "priority": 0.80, "repo_id": "repo-aaa", "eligible": True, "blocked_by": [],
         "reason": "test", "task_binding": {"task_id": "t", "args": {}}},
    ]

    def test_text_contains_priority(self):
        out = _fmt_text(self._ACTIONS)
        assert "0.95" in out
        assert "0.80" in out

    def test_text_contains_action_type(self):
        out = _fmt_text(self._ACTIONS)
        assert "run_determinism_regression_suite" in out

    def test_text_contains_repo_id(self):
        out = _fmt_text(self._ACTIONS)
        assert "repo-aaa" in out

    def test_text_empty_actions_message(self):
        out = _fmt_text([])
        assert "no eligible actions" in out

    def test_json_is_valid_array(self):
        out = _fmt_json(self._ACTIONS)
        parsed = json.loads(out)
        assert isinstance(parsed, list)
        assert len(parsed) == 2

    def test_json_preserves_order(self):
        out = _fmt_json(self._ACTIONS)
        parsed = json.loads(out)
        assert parsed[0]["action_id"] == "run_det_aaa"
        assert parsed[1]["action_id"] == "rerun_aaa"

    def test_json_includes_repo_id(self):
        out = _fmt_json(self._ACTIONS)
        parsed = json.loads(out)
        for item in parsed:
            assert "repo_id" in item


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------

class TestCLITextOutput:
    def _state_file(self, tmp_path: Path) -> Path:
        p = tmp_path / "state.json"
        _write_state(p, _make_state([
            _make_repo("repo-alpha", [
                _make_action("run_det_alpha", "run_determinism_regression_suite", 0.95),
                _make_action("rerun_alpha", "rerun_failed_task", 0.80),
            ], status="failing"),
            _make_repo("repo-beta", [
                _make_action("refresh_beta", "refresh_repo_health", 0.55),
            ], status="stale"),
        ]))
        return p

    def test_exits_zero(self, tmp_path):
        p = self._state_file(tmp_path)
        r = _run(["--input", str(p)])
        assert r.returncode == 0

    def test_text_output_has_header(self, tmp_path):
        p = self._state_file(tmp_path)
        r = _run(["--input", str(p)])
        assert "priority" in r.stdout
        assert "action_type" in r.stdout
        assert "repo_id" in r.stdout
        assert "action_id" in r.stdout

    def test_text_output_highest_priority_first(self, tmp_path):
        p = self._state_file(tmp_path)
        r = _run(["--input", str(p)])
        lines = [l for l in r.stdout.splitlines() if "0." in l]
        assert lines[0].strip().startswith("0.95")

    def test_text_output_repo_filter(self, tmp_path):
        p = self._state_file(tmp_path)
        r = _run(["--input", str(p), "--repo-id", "repo-beta"])
        assert "repo-beta" in r.stdout
        assert "repo-alpha" not in r.stdout

    def test_text_output_repo_filter_unknown_shows_no_actions(self, tmp_path):
        p = self._state_file(tmp_path)
        r = _run(["--input", str(p), "--repo-id", "no-such-repo"])
        assert r.returncode == 0
        assert "no eligible actions" in r.stdout


class TestCLIJsonOutput:
    def _state_file(self, tmp_path: Path) -> Path:
        p = tmp_path / "state.json"
        _write_state(p, _make_state([
            _make_repo("repo-alpha", [
                _make_action("run_det_alpha", "run_determinism_regression_suite", 0.95),
                _make_action("blocked_alpha", "rerun_failed_task", 0.80, eligible=False),
            ], status="failing"),
            _make_repo("repo-beta", [
                _make_action("refresh_beta", "refresh_repo_health", 0.55),
            ], status="stale"),
        ]))
        return p

    def test_json_flag_exits_zero(self, tmp_path):
        p = self._state_file(tmp_path)
        r = _run(["--input", str(p), "--json"])
        assert r.returncode == 0

    def test_json_output_is_valid_array(self, tmp_path):
        p = self._state_file(tmp_path)
        r = _run(["--input", str(p), "--json"])
        parsed = json.loads(r.stdout)
        assert isinstance(parsed, list)

    def test_json_output_priority_desc(self, tmp_path):
        p = self._state_file(tmp_path)
        r = _run(["--input", str(p), "--json"])
        parsed = json.loads(r.stdout)
        priorities = [a["priority"] for a in parsed]
        assert priorities == sorted(priorities, reverse=True)

    def test_json_output_excludes_ineligible(self, tmp_path):
        p = self._state_file(tmp_path)
        r = _run(["--input", str(p), "--json"])
        parsed = json.loads(r.stdout)
        ids = [a["action_id"] for a in parsed]
        assert "blocked_alpha" not in ids

    def test_json_output_has_repo_id(self, tmp_path):
        p = self._state_file(tmp_path)
        r = _run(["--input", str(p), "--json"])
        parsed = json.loads(r.stdout)
        for item in parsed:
            assert "repo_id" in item

    def test_json_repo_filter(self, tmp_path):
        p = self._state_file(tmp_path)
        r = _run(["--input", str(p), "--json", "--repo-id", "repo-alpha"])
        parsed = json.loads(r.stdout)
        assert all(a["repo_id"] == "repo-alpha" for a in parsed)

    def test_json_does_not_modify_input_file(self, tmp_path):
        p = self._state_file(tmp_path)
        before = p.read_text(encoding="utf-8")
        _run(["--input", str(p), "--json"])
        after = p.read_text(encoding="utf-8")
        assert before == after


class TestCLIFailClosed:
    def test_missing_input_fails(self, tmp_path):
        r = _run(["--input", str(tmp_path / "no_such.json")])
        assert r.returncode != 0

    def test_malformed_json_fails(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{bad json", encoding="utf-8")
        r = _run(["--input", str(p)])
        assert r.returncode != 0

    def test_missing_repos_key_fails(self, tmp_path):
        p = tmp_path / "nokey.json"
        p.write_text(json.dumps({"schema_version": "v1"}), encoding="utf-8")
        r = _run(["--input", str(p)])
        assert r.returncode != 0

    def test_error_goes_to_stderr(self, tmp_path):
        r = _run(["--input", str(tmp_path / "missing.json")])
        assert r.returncode != 0
        assert r.stderr.strip() != ""
        assert r.stdout.strip() == ""


class TestCLIDeterminism:
    def _state_file(self, tmp_path: Path) -> Path:
        p = tmp_path / "state.json"
        _write_state(p, _make_state([
            _make_repo("zzz", [
                _make_action("zzz_det", "run_determinism_regression_suite", 0.95),
                _make_action("zzz_regen", "regenerate_missing_artifact", 0.70),
            ], status="failing"),
            _make_repo("aaa", [
                _make_action("aaa_det", "run_determinism_regression_suite", 0.95),
                _make_action("aaa_regen", "regenerate_missing_artifact", 0.70),
                _make_action("aaa_refresh", "refresh_repo_health", 0.55),
            ], status="failing"),
        ]))
        return p

    def test_text_byte_identical_two_runs(self, tmp_path):
        p = self._state_file(tmp_path)
        r1 = _run(["--input", str(p)])
        r2 = _run(["--input", str(p)])
        assert r1.stdout == r2.stdout

    def test_json_byte_identical_two_runs(self, tmp_path):
        p = self._state_file(tmp_path)
        r1 = _run(["--input", str(p), "--json"])
        r2 = _run(["--input", str(p), "--json"])
        assert r1.stdout == r2.stdout

    def test_json_ten_calls_all_identical(self, tmp_path):
        p = self._state_file(tmp_path)
        results = [_run(["--input", str(p), "--json"]).stdout for _ in range(10)]
        assert len(set(results)) == 1

    def test_tied_priorities_stable_order(self, tmp_path):
        """With equal priorities the tiebreak (action_type → action_id → repo_id) is stable."""
        p = tmp_path / "state.json"
        _write_state(p, _make_state([
            _make_repo("zzz", [_make_action("zzz_act", "rerun_failed_task", 0.80)]),
            _make_repo("aaa", [_make_action("aaa_act", "rerun_failed_task", 0.80)]),
        ]))
        r1 = _run(["--input", str(p), "--json"])
        r2 = _run(["--input", str(p), "--json"])
        assert r1.stdout == r2.stdout
        parsed = json.loads(r1.stdout)
        # action_type ties → action_id tiebreak → aaa_act < zzz_act
        assert parsed[0]["action_id"] == "aaa_act"
        assert parsed[1]["action_id"] == "zzz_act"


# ---------------------------------------------------------------------------
# Ledger fixture helpers
# ---------------------------------------------------------------------------

def _make_ledger_row(
    action_type: str,
    effectiveness_score: float = 0.5,
    recommended_priority_adjustment: float = 0.0,
    classification: str = "neutral",
) -> dict[str, Any]:
    return {
        "action_type": action_type,
        "times_recommended": 1,
        "times_executed": 1,
        "success_rate": 1.0,
        "avg_risk_delta": 0.0,
        "avg_health_delta": 0.0,
        "effectiveness_score": effectiveness_score,
        "recommended_priority_adjustment": recommended_priority_adjustment,
        "classification": classification,
    }


def _make_ledger(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "v1",
        "generated_at": "",
        "summary": {
            "actions_tracked": len(rows),
            "effective_actions": 0,
            "neutral_actions": 0,
            "ineffective_actions": 0,
        },
        "action_types": rows,
    }


def _write_ledger(path: Path, ledger: dict[str, Any]) -> None:
    path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Unit tests: _load_ledger
# ---------------------------------------------------------------------------

class TestLoadLedger:
    def test_valid_ledger_loads(self, tmp_path):
        p = tmp_path / "ledger.json"
        _write_ledger(p, _make_ledger([]))
        ledger = _load_ledger(p)
        assert ledger["schema_version"] == "v1"

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(ValueError, match="not found"):
            _load_ledger(tmp_path / "no_ledger.json")

    def test_malformed_json_raises(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{bad json", encoding="utf-8")
        with pytest.raises(ValueError, match="malformed"):
            _load_ledger(p)

    def test_non_object_raises(self, tmp_path):
        p = tmp_path / "arr.json"
        p.write_text("[1,2,3]", encoding="utf-8")
        with pytest.raises(ValueError):
            _load_ledger(p)

    def test_missing_action_types_key_raises(self, tmp_path):
        p = tmp_path / "nokey.json"
        p.write_text(json.dumps({"schema_version": "v1"}), encoding="utf-8")
        with pytest.raises(ValueError, match="action_types"):
            _load_ledger(p)

    def test_phase_f_format_rejected(self, tmp_path):
        # Phase F (update_action_effectiveness_from_history.py) writes
        # {"actions": {"task_name": {...}}} — task-keyed, no "action_types" key.
        # _load_ledger must reject this format fail-closed; it carries no
        # annotation fields (recommended_priority_adjustment, etc.) that
        # _annotate_with_ledger consumes.
        p = tmp_path / "phase_f.json"
        p.write_text(json.dumps({
            "actions": {
                "build_portfolio_dashboard": {
                    "total_runs": 5, "success_count": 4,
                    "failure_count": 1, "last_status": "ok",
                }
            }
        }), encoding="utf-8")
        with pytest.raises(ValueError, match="action_types"):
            _load_ledger(p)

    def test_phase_f_new_format_accepted(self, tmp_path):
        # Phase F's new output format includes both "action_types" (list) and
        # "actions" (dict). _load_ledger must accept this format; the live demo
        # confirmed acceptance. This test anchors that behavior as a regression target.
        p = tmp_path / "phase_f_new.json"
        p.write_text(json.dumps({"action_types": [], "actions": {}}), encoding="utf-8")
        result = _load_ledger(p)
        assert "action_types" in result


# ---------------------------------------------------------------------------
# Unit tests: _annotate_with_ledger
# ---------------------------------------------------------------------------

class TestAnnotateWithLedger:
    def _base_actions(self) -> list[dict[str, Any]]:
        return [
            {**_make_action("det_r1", "run_determinism_regression_suite", 0.95),
             "repo_id": "r1"},
            {**_make_action("rerun_r1", "rerun_failed_task", 0.80),
             "repo_id": "r1"},
            {**_make_action("refresh_r2", "refresh_repo_health", 0.55),
             "repo_id": "r2"},
        ]

    def test_fields_added(self):
        actions = self._base_actions()
        index = _build_ledger_index(_make_ledger([
            _make_ledger_row("run_determinism_regression_suite", 0.88, 0.10, "effective"),
        ]))
        result = _annotate_with_ledger(actions, index)
        det = next(a for a in result if a["action_type"] == "run_determinism_regression_suite")
        assert det["effectiveness_score"] == 0.88
        assert det["recommended_priority_adjustment"] == 0.10
        assert det["classification"] == "effective"
        assert det["adjusted_priority"] == round(0.95 + 0.10, 2)

    def test_default_when_action_type_absent(self):
        actions = self._base_actions()
        result = _annotate_with_ledger(actions, {})  # empty index
        for a in result:
            assert a["effectiveness_score"] == 0.0
            assert a["recommended_priority_adjustment"] == 0.0
            assert a["classification"] == "neutral"
            assert a["adjusted_priority"] == a["priority"]

    def test_adjusted_priority_formula(self):
        actions = [{**_make_action("act", "rerun_failed_task", 0.80), "repo_id": "r"}]
        index = _build_ledger_index(_make_ledger([
            _make_ledger_row("rerun_failed_task", 0.88, 0.10, "effective"),
        ]))
        result = _annotate_with_ledger(actions, index)
        assert result[0]["adjusted_priority"] == round(0.80 + 0.10, 2)

    def test_negative_adjustment_reduces_adjusted_priority(self):
        actions = [{**_make_action("act", "refresh_repo_health", 0.55), "repo_id": "r"}]
        index = _build_ledger_index(_make_ledger([
            _make_ledger_row("refresh_repo_health", 0.0, -0.05, "ineffective"),
        ]))
        result = _annotate_with_ledger(actions, index)
        assert result[0]["adjusted_priority"] == round(0.55 - 0.05, 2)

    def test_reorder_by_adjusted_priority(self):
        """A lower-priority action with a big positive adj should move ahead."""
        actions = [
            {**_make_action("high_act", "rerun_failed_task", 0.95), "repo_id": "r"},
            {**_make_action("low_act", "refresh_repo_health", 0.55), "repo_id": "r"},
        ]
        # Give the low-priority action a big enough boost to overtake the high one.
        index = _build_ledger_index(_make_ledger([
            _make_ledger_row("rerun_failed_task", 0.0, -0.40, "ineffective"),
            _make_ledger_row("refresh_repo_health", 0.88, 0.40, "effective"),
        ]))
        result = _annotate_with_ledger(actions, index)
        # rerun: adj=0.55, refresh: adj=0.95 → refresh first
        assert result[0]["action_type"] == "refresh_repo_health"
        assert result[1]["action_type"] == "rerun_failed_task"

    def test_equal_adjusted_priority_tiebreak_by_priority(self):
        """Tie on adjusted_priority → fall back to priority desc."""
        actions = [
            {**_make_action("low_act", "refresh_repo_health", 0.70), "repo_id": "r"},
            {**_make_action("high_act", "rerun_failed_task", 0.80), "repo_id": "r"},
        ]
        # adj = 0.70+0.20=0.90 and 0.80+0.10=0.90 (tied)
        index = _build_ledger_index(_make_ledger([
            _make_ledger_row("refresh_repo_health", 0.88, 0.20, "effective"),
            _make_ledger_row("rerun_failed_task", 0.88, 0.10, "effective"),
        ]))
        result = _annotate_with_ledger(actions, index)
        # adj tied → priority desc → 0.80 before 0.70
        assert result[0]["action_id"] == "high_act"
        assert result[1]["action_id"] == "low_act"

    def test_equal_adj_and_priority_tiebreak_by_action_type(self):
        """Tie on adjusted and priority → fall back to action_type alpha."""
        actions = [
            {**_make_action("act_z", "rerun_failed_task", 0.80), "repo_id": "r"},
            {**_make_action("act_a", "refresh_repo_health", 0.80), "repo_id": "r"},
        ]
        # Same adj adjustment so both get adj=0.80
        index = _build_ledger_index(_make_ledger([]))  # all defaults → adj=priority
        result = _annotate_with_ledger(actions, index)
        # adj tied, priority tied → action_type: "refresh" < "rerun"
        assert result[0]["action_type"] == "refresh_repo_health"
        assert result[1]["action_type"] == "rerun_failed_task"

    def test_does_not_mutate_input_actions(self):
        import copy
        actions = self._base_actions()
        original = copy.deepcopy(actions)
        _annotate_with_ledger(actions, {})
        assert actions == original


# ---------------------------------------------------------------------------
# Unit tests: _fmt_text_ledger
# ---------------------------------------------------------------------------

class TestFmtTextLedger:
    _ACTIONS = [
        {
            "action_id": "det_r1", "action_type": "run_determinism_regression_suite",
            "priority": 0.95, "adjusted_priority": 1.05, "repo_id": "repo-a",
            "classification": "effective", "eligible": True, "blocked_by": [],
            "effectiveness_score": 0.88, "recommended_priority_adjustment": 0.10,
            "reason": "r", "task_binding": {"task_id": "t", "args": {}},
        },
    ]

    def test_header_contains_all_columns(self):
        out = _fmt_text_ledger(self._ACTIONS)
        for col in ("adjusted_priority", "priority", "action_type", "repo_id",
                    "classification", "action_id"):
            assert col in out

    def test_contains_adjusted_priority_value(self):
        out = _fmt_text_ledger(self._ACTIONS)
        assert "1.05" in out

    def test_contains_classification(self):
        out = _fmt_text_ledger(self._ACTIONS)
        assert "effective" in out

    def test_empty_actions_message(self):
        assert "no eligible actions" in _fmt_text_ledger([])


# ---------------------------------------------------------------------------
# CLI tests: --ledger behavior
# ---------------------------------------------------------------------------

class TestCLIWithLedger:
    def _files(self, tmp_path: Path, ledger_rows: list[dict]) -> tuple[Path, Path]:
        state_p = tmp_path / "state.json"
        ledger_p = tmp_path / "ledger.json"
        _write_state(state_p, _make_state([
            _make_repo("repo-alpha", [
                _make_action("det_alpha", "run_determinism_regression_suite", 0.95),
                _make_action("rerun_alpha", "rerun_failed_task", 0.80),
            ], status="failing"),
            _make_repo("repo-beta", [
                _make_action("refresh_beta", "refresh_repo_health", 0.55),
            ], status="stale"),
        ]))
        _write_ledger(ledger_p, _make_ledger(ledger_rows))
        return state_p, ledger_p

    def test_exits_zero_with_valid_ledger(self, tmp_path):
        s, l = self._files(tmp_path, [])
        r = _run(["--input", str(s), "--ledger", str(l)])
        assert r.returncode == 0

    def test_text_header_includes_adjusted_priority(self, tmp_path):
        s, l = self._files(tmp_path, [])
        r = _run(["--input", str(s), "--ledger", str(l)])
        assert "adjusted_priority" in r.stdout
        assert "classification" in r.stdout

    def test_text_header_no_adjusted_priority_without_ledger(self, tmp_path):
        s, _ = self._files(tmp_path, [])
        r = _run(["--input", str(s)])
        assert "adjusted_priority" not in r.stdout
        assert "classification" not in r.stdout

    def test_positive_adj_reorders_action(self, tmp_path):
        """refresh_repo_health (pri=0.55) boosted by +0.45 → adj=1.00 → first."""
        s = tmp_path / "state.json"
        l = tmp_path / "ledger.json"
        _write_state(s, _make_state([
            _make_repo("r", [
                _make_action("det_r", "run_determinism_regression_suite", 0.95),
                _make_action("refresh_r", "refresh_repo_health", 0.55),
            ])
        ]))
        _write_ledger(l, _make_ledger([
            _make_ledger_row("run_determinism_regression_suite", 0.0, -0.45, "ineffective"),
            _make_ledger_row("refresh_repo_health", 0.88, 0.45, "effective"),
        ]))
        r = _run(["--input", str(s), "--ledger", str(l), "--json"])
        assert r.returncode == 0
        parsed = json.loads(r.stdout)
        assert parsed[0]["action_type"] == "refresh_repo_health"
        assert parsed[1]["action_type"] == "run_determinism_regression_suite"

    def test_negative_adj_demotes_action(self, tmp_path):
        """run_det (pri=0.95) penalised by −0.45 → adj=0.50 → after refresh (adj=0.55)."""
        s = tmp_path / "state.json"
        l = tmp_path / "ledger.json"
        _write_state(s, _make_state([
            _make_repo("r", [
                _make_action("det_r", "run_determinism_regression_suite", 0.95),
                _make_action("refresh_r", "refresh_repo_health", 0.55),
            ])
        ]))
        _write_ledger(l, _make_ledger([
            _make_ledger_row("run_determinism_regression_suite", 0.0, -0.45, "ineffective"),
        ]))
        r = _run(["--input", str(s), "--ledger", str(l), "--json"])
        parsed = json.loads(r.stdout)
        assert parsed[0]["action_type"] == "refresh_repo_health"
        assert parsed[1]["action_type"] == "run_determinism_regression_suite"

    def test_default_ledger_values_for_missing_action_type(self, tmp_path):
        """Action type not in ledger gets neutral defaults; adjusted_priority == priority."""
        s = tmp_path / "state.json"
        l = tmp_path / "ledger.json"
        _write_state(s, _make_state([
            _make_repo("r", [_make_action("refresh_r", "refresh_repo_health", 0.55)])
        ]))
        _write_ledger(l, _make_ledger([]))  # empty ledger
        r = _run(["--input", str(s), "--ledger", str(l), "--json"])
        parsed = json.loads(r.stdout)
        assert parsed[0]["adjusted_priority"] == 0.55
        assert parsed[0]["classification"] == "neutral"
        assert parsed[0]["recommended_priority_adjustment"] == 0.0
        assert parsed[0]["effectiveness_score"] == 0.0

    def test_repo_filter_works_with_ledger(self, tmp_path):
        s, l = self._files(tmp_path, [])
        r = _run(["--input", str(s), "--ledger", str(l), "--repo-id", "repo-beta"])
        assert r.returncode == 0
        assert "repo-beta" in r.stdout
        assert "repo-alpha" not in r.stdout

    def test_json_output_contains_ledger_fields(self, tmp_path):
        s = tmp_path / "state.json"
        l = tmp_path / "ledger.json"
        _write_state(s, _make_state([
            _make_repo("r", [_make_action("det_r", "run_determinism_regression_suite", 0.95)])
        ]))
        _write_ledger(l, _make_ledger([
            _make_ledger_row("run_determinism_regression_suite", 0.88, 0.10, "effective"),
        ]))
        r = _run(["--input", str(s), "--ledger", str(l), "--json"])
        parsed = json.loads(r.stdout)
        row = parsed[0]
        assert "effectiveness_score" in row
        assert "recommended_priority_adjustment" in row
        assert "classification" in row
        assert "adjusted_priority" in row
        assert row["effectiveness_score"] == 0.88
        assert row["recommended_priority_adjustment"] == 0.10
        assert row["classification"] == "effective"
        assert row["adjusted_priority"] == round(0.95 + 0.10, 2)

    def test_json_output_without_ledger_lacks_ledger_fields(self, tmp_path):
        s, _ = self._files(tmp_path, [])
        r = _run(["--input", str(s), "--json"])
        parsed = json.loads(r.stdout)
        for item in parsed:
            assert "adjusted_priority" not in item
            assert "classification" not in item

    def test_ineligible_still_excluded_with_ledger(self, tmp_path):
        s = tmp_path / "state.json"
        l = tmp_path / "ledger.json"
        _write_state(s, _make_state([
            _make_repo("r", [
                _make_action("blocked", "rerun_failed_task", 0.80, eligible=False),
                _make_action("ok_act", "refresh_repo_health", 0.55),
            ])
        ]))
        _write_ledger(l, _make_ledger([]))
        r = _run(["--input", str(s), "--ledger", str(l), "--json"])
        parsed = json.loads(r.stdout)
        assert all(a["action_id"] != "blocked" for a in parsed)

    def test_byte_identical_two_runs(self, tmp_path):
        s, l = self._files(tmp_path, [
            _make_ledger_row("run_determinism_regression_suite", 0.88, 0.10, "effective"),
        ])
        r1 = _run(["--input", str(s), "--ledger", str(l), "--json"])
        r2 = _run(["--input", str(s), "--ledger", str(l), "--json"])
        assert r1.stdout == r2.stdout


# ---------------------------------------------------------------------------
# CLI tests: --ledger fail-closed
# ---------------------------------------------------------------------------

class TestCLILedgerFailClosed:
    def test_missing_ledger_file_fails(self, tmp_path):
        s = tmp_path / "state.json"
        _write_state(s, _make_state([]))
        r = _run(["--input", str(s), "--ledger", str(tmp_path / "no_ledger.json")])
        assert r.returncode != 0

    def test_malformed_ledger_json_fails(self, tmp_path):
        s = tmp_path / "state.json"
        l = tmp_path / "ledger.json"
        _write_state(s, _make_state([]))
        l.write_text("{bad json", encoding="utf-8")
        r = _run(["--input", str(s), "--ledger", str(l)])
        assert r.returncode != 0

    def test_ledger_missing_action_types_key_fails(self, tmp_path):
        s = tmp_path / "state.json"
        l = tmp_path / "ledger.json"
        _write_state(s, _make_state([]))
        l.write_text(json.dumps({"schema_version": "v1"}), encoding="utf-8")
        r = _run(["--input", str(s), "--ledger", str(l)])
        assert r.returncode != 0

    def test_ledger_error_to_stderr(self, tmp_path):
        s = tmp_path / "state.json"
        _write_state(s, _make_state([]))
        r = _run(["--input", str(s), "--ledger", str(tmp_path / "missing.json")])
        assert r.returncode != 0
        assert r.stderr.strip() != ""
        assert r.stdout.strip() == ""


# ---------------------------------------------------------------------------
# Ledger ordering: equal adjusted_priority tiebreaks
# ---------------------------------------------------------------------------

class TestLedgerOrdering:
    def test_adj_tie_broken_by_priority_desc(self, tmp_path):
        """adj tied (0.90 each) → higher raw priority wins."""
        s = tmp_path / "state.json"
        l = tmp_path / "ledger.json"
        _write_state(s, _make_state([
            _make_repo("r", [
                _make_action("high_p", "rerun_failed_task", 0.80),   # +0.10 → adj=0.90
                _make_action("low_p", "refresh_repo_health", 0.70),  # +0.20 → adj=0.90
            ])
        ]))
        _write_ledger(l, _make_ledger([
            _make_ledger_row("rerun_failed_task", 0.88, 0.10, "effective"),
            _make_ledger_row("refresh_repo_health", 0.88, 0.20, "effective"),
        ]))
        r = _run(["--input", str(s), "--ledger", str(l), "--json"])
        parsed = json.loads(r.stdout)
        assert parsed[0]["action_id"] == "high_p"   # pri=0.80 > 0.70
        assert parsed[1]["action_id"] == "low_p"

    def test_adj_and_priority_tie_broken_by_action_type(self, tmp_path):
        """adj and priority both tied → action_type alpha."""
        s = tmp_path / "state.json"
        l = tmp_path / "ledger.json"
        _write_state(s, _make_state([
            _make_repo("r", [
                _make_action("act_z", "rerun_failed_task", 0.80),
                _make_action("act_a", "refresh_repo_health", 0.80),
            ])
        ]))
        _write_ledger(l, _make_ledger([]))  # both default adj=0 → adj=0.80
        r = _run(["--input", str(s), "--ledger", str(l), "--json"])
        parsed = json.loads(r.stdout)
        # "refresh" < "rerun" alpha
        assert parsed[0]["action_type"] == "refresh_repo_health"
        assert parsed[1]["action_type"] == "rerun_failed_task"

    def test_adj_priority_type_id_tie_broken_by_repo_id(self, tmp_path):
        """Full tie → repo_id alpha."""
        s = tmp_path / "state.json"
        l = tmp_path / "ledger.json"
        _write_state(s, _make_state([
            _make_repo("zzz", [_make_action("shared", "refresh_repo_health", 0.55)]),
            _make_repo("aaa", [_make_action("shared", "refresh_repo_health", 0.55)]),
        ]))
        _write_ledger(l, _make_ledger([]))
        r = _run(["--input", str(s), "--ledger", str(l), "--json"])
        parsed = json.loads(r.stdout)
        assert parsed[0]["repo_id"] == "aaa"
        assert parsed[1]["repo_id"] == "zzz"

    def test_ordering_stable_across_ten_runs(self, tmp_path):
        s = tmp_path / "state.json"
        l = tmp_path / "ledger.json"
        _write_state(s, _make_state([
            _make_repo("r1", [
                _make_action("det_r1", "run_determinism_regression_suite", 0.95),
                _make_action("regen_r1", "regenerate_missing_artifact", 0.70),
            ]),
            _make_repo("r2", [
                _make_action("rerun_r2", "rerun_failed_task", 0.80),
                _make_action("refresh_r2", "refresh_repo_health", 0.55),
            ]),
        ]))
        _write_ledger(l, _make_ledger([
            _make_ledger_row("run_determinism_regression_suite", 0.88, 0.10, "effective"),
            _make_ledger_row("rerun_failed_task", 0.0, -0.05, "ineffective"),
        ]))
        results = [_run(["--input", str(s), "--ledger", str(l), "--json"]).stdout
                   for _ in range(10)]
        assert len(set(results)) == 1


# ---------------------------------------------------------------------------
# Boosted (effective) actions rank ahead of neutral (unexecuted) ones
# ---------------------------------------------------------------------------

class TestLedgerBoostedAheadOfNeutral:
    """With --ledger, effective (boosted) actions must rank above neutral
    (unexecuted) actions that share the same base priority, deterministically."""

    def test_boosted_ranks_above_neutral_at_same_base_priority(self, tmp_path):
        """adj_priority: 0.70+0.10=0.80 > 0.70+0.00=0.70 → effective first."""
        s = tmp_path / "state.json"
        l = tmp_path / "ledger.json"
        _write_state(s, _make_state([
            _make_repo("r", [
                _make_action("act-neutral", "regenerate_missing_artifact", 0.70),
                _make_action("act-boost", "refresh_repo_health", 0.70),
            ])
        ]))
        _write_ledger(l, _make_ledger([
            _make_ledger_row("refresh_repo_health", 0.88, 0.10, "effective"),
            _make_ledger_row("regenerate_missing_artifact", 0.0, 0.0, "neutral"),
        ]))
        r = _run(["--input", str(s), "--ledger", str(l), "--json"])
        parsed = json.loads(r.stdout)
        assert parsed[0]["action_id"] == "act-boost"
        assert parsed[0]["classification"] == "effective"
        assert parsed[1]["action_id"] == "act-neutral"
        assert parsed[1]["classification"] == "neutral"

    def test_neutral_adjusted_priority_equals_base_priority(self, tmp_path):
        """Neutral action: adjusted_priority == priority (no offset)."""
        s = tmp_path / "state.json"
        l = tmp_path / "ledger.json"
        _write_state(s, _make_state([
            _make_repo("r", [_make_action("act-a", "regenerate_missing_artifact", 0.55)])
        ]))
        _write_ledger(l, _make_ledger([
            _make_ledger_row("regenerate_missing_artifact", 0.0, 0.0, "neutral"),
        ]))
        r = _run(["--input", str(s), "--ledger", str(l), "--json"])
        parsed = json.loads(r.stdout)
        assert parsed[0]["adjusted_priority"] == pytest.approx(0.55)

    def test_boosted_adjusted_priority_equals_base_plus_offset(self, tmp_path):
        """Effective action: adjusted_priority == priority + 0.10."""
        s = tmp_path / "state.json"
        l = tmp_path / "ledger.json"
        _write_state(s, _make_state([
            _make_repo("r", [_make_action("act-b", "refresh_repo_health", 0.55)])
        ]))
        _write_ledger(l, _make_ledger([
            _make_ledger_row("refresh_repo_health", 0.88, 0.10, "effective"),
        ]))
        r = _run(["--input", str(s), "--ledger", str(l), "--json"])
        parsed = json.loads(r.stdout)
        assert parsed[0]["adjusted_priority"] == pytest.approx(0.65)

    def test_ranking_deterministic_across_repeated_calls(self, tmp_path):
        """Identical inputs produce byte-identical JSON output."""
        s = tmp_path / "state.json"
        l = tmp_path / "ledger.json"
        _write_state(s, _make_state([
            _make_repo("r", [
                _make_action("act-neutral", "regenerate_missing_artifact", 0.70),
                _make_action("act-boost", "refresh_repo_health", 0.70),
            ])
        ]))
        _write_ledger(l, _make_ledger([
            _make_ledger_row("refresh_repo_health", 0.88, 0.10, "effective"),
            _make_ledger_row("regenerate_missing_artifact", 0.0, 0.0, "neutral"),
        ]))
        results = [_run(["--input", str(s), "--ledger", str(l), "--json"]).stdout
                   for _ in range(5)]
        assert len(set(results)) == 1


# ---------------------------------------------------------------------------
# Action preconditions (_preconditions_met + _collect_actions integration)
# ---------------------------------------------------------------------------

def _make_repo_with_signals(
    repo_id: str,
    actions: list,
    *,
    last_run_ok: bool = True,
    artifact_completeness: float = 1.0,
    determinism_ok: bool = True,
) -> dict:
    repo = _make_repo(repo_id, actions)
    repo["signals"] = {
        "last_run_ok": last_run_ok,
        "artifact_completeness": artifact_completeness,
        "determinism_ok": determinism_ok,
        "recent_failures": 0,
        "stale_runs": 0,
    }
    return repo


def _action_with_preconditions(preconditions: list, action_id: str = "act-1") -> dict:
    a = _make_action(action_id, "refresh_repo_health", 0.55)
    a["preconditions"] = preconditions
    return a


class TestPreconditionsMet:
    """Unit tests for _preconditions_met()."""

    # --- empty / absent preconditions ---

    def test_empty_preconditions_always_passes(self):
        action = _action_with_preconditions([])
        repo = _make_repo("r", [])
        assert _preconditions_met(action, repo) is True

    def test_absent_preconditions_key_always_passes(self):
        action = _make_action("act", "refresh_repo_health", 0.55)  # no key at all
        repo = _make_repo("r", [])
        assert _preconditions_met(action, repo) is True

    # --- last_run_failed ---

    def test_last_run_failed_satisfied_when_last_run_ok_is_false(self):
        action = _action_with_preconditions(["last_run_failed"])
        repo = _make_repo_with_signals("r", [], last_run_ok=False)
        assert _preconditions_met(action, repo) is True

    def test_last_run_failed_unmet_when_last_run_ok_is_true(self):
        action = _action_with_preconditions(["last_run_failed"])
        repo = _make_repo_with_signals("r", [], last_run_ok=True)
        assert _preconditions_met(action, repo) is False

    # --- artifacts_missing ---

    def test_artifacts_missing_satisfied_when_completeness_below_1(self):
        action = _action_with_preconditions(["artifacts_missing"])
        repo = _make_repo_with_signals("r", [], artifact_completeness=0.5)
        assert _preconditions_met(action, repo) is True

    def test_artifacts_missing_unmet_when_completeness_is_1(self):
        action = _action_with_preconditions(["artifacts_missing"])
        repo = _make_repo_with_signals("r", [], artifact_completeness=1.0)
        assert _preconditions_met(action, repo) is False

    def test_artifacts_missing_unmet_when_completeness_above_1(self):
        action = _action_with_preconditions(["artifacts_missing"])
        repo = _make_repo_with_signals("r", [], artifact_completeness=1.5)
        assert _preconditions_met(action, repo) is False

    # --- determinism_failed ---

    def test_determinism_failed_satisfied_when_determinism_ok_is_false(self):
        action = _action_with_preconditions(["determinism_failed"])
        repo = _make_repo_with_signals("r", [], determinism_ok=False)
        assert _preconditions_met(action, repo) is True

    def test_determinism_failed_unmet_when_determinism_ok_is_true(self):
        action = _action_with_preconditions(["determinism_failed"])
        repo = _make_repo_with_signals("r", [], determinism_ok=True)
        assert _preconditions_met(action, repo) is False

    # --- unknown precondition → fail closed ---

    def test_unknown_precondition_fails_closed(self):
        action = _action_with_preconditions(["no_such_precondition"])
        repo = _make_repo("r", [])
        assert _preconditions_met(action, repo) is False

    def test_unknown_precondition_mixed_with_valid_fails_closed(self):
        """Even when the known precondition is satisfied, unknown one fails closed."""
        action = _action_with_preconditions(["last_run_failed", "no_such_precondition"])
        repo = _make_repo_with_signals("r", [], last_run_ok=False)
        assert _preconditions_met(action, repo) is False

    # --- multiple preconditions ---

    def test_all_preconditions_must_be_satisfied(self):
        action = _action_with_preconditions(["last_run_failed", "artifacts_missing"])
        # last_run_failed met, artifacts_missing not met
        repo = _make_repo_with_signals("r", [], last_run_ok=False, artifact_completeness=1.0)
        assert _preconditions_met(action, repo) is False

    def test_all_preconditions_satisfied_returns_true(self):
        action = _action_with_preconditions(["last_run_failed", "artifacts_missing"])
        repo = _make_repo_with_signals("r", [], last_run_ok=False, artifact_completeness=0.5)
        assert _preconditions_met(action, repo) is True


class TestCollectActionsWithPreconditions:
    """Integration: _collect_actions respects preconditions."""

    def test_action_with_satisfied_preconditions_is_included(self):
        action = _action_with_preconditions(["last_run_failed"])
        repo = _make_repo_with_signals("r", [action], last_run_ok=False)
        result = _collect_actions(_make_state([repo]), None)
        assert len(result) == 1
        assert result[0]["action_id"] == "act-1"

    def test_action_with_unmet_preconditions_is_excluded(self):
        action = _action_with_preconditions(["last_run_failed"])
        repo = _make_repo_with_signals("r", [action], last_run_ok=True)
        result = _collect_actions(_make_state([repo]), None)
        assert result == []

    def test_action_with_unknown_precondition_is_excluded(self):
        action = _action_with_preconditions(["unknown_precondition"])
        repo = _make_repo("r", [action])
        result = _collect_actions(_make_state([repo]), None)
        assert result == []

    def test_action_without_preconditions_included_as_before(self):
        """No preconditions key → legacy behavior unchanged."""
        action = _make_action("act-legacy", "refresh_repo_health", 0.55)
        repo = _make_repo("r", [action])
        result = _collect_actions(_make_state([repo]), None)
        assert len(result) == 1

    def test_mixed_preconditions_only_satisfied_included(self):
        """Two actions: one with met precondition, one with unmet."""
        met = _action_with_preconditions(["artifacts_missing"], action_id="met")
        unmet = _action_with_preconditions(["last_run_failed"], action_id="unmet")
        repo = _make_repo_with_signals(
            "r", [met, unmet],
            artifact_completeness=0.5,  # artifacts_missing satisfied
            last_run_ok=True,           # last_run_failed NOT satisfied
        )
        result = _collect_actions(_make_state([repo]), None)
        ids = [a["action_id"] for a in result]
        assert "met" in ids
        assert "unmet" not in ids

    def test_deterministic_ordering_preserved_with_preconditions(self):
        """Surviving actions are still sorted by priority desc."""
        a_hi = _action_with_preconditions(["artifacts_missing"], action_id="hi")
        a_hi["priority"] = 0.9
        a_lo = _action_with_preconditions(["artifacts_missing"], action_id="lo")
        a_lo["priority"] = 0.5
        repo = _make_repo_with_signals("r", [a_lo, a_hi], artifact_completeness=0.5)
        result = _collect_actions(_make_state([repo]), None)
        assert [a["action_id"] for a in result] == ["hi", "lo"]


class TestPortfolioLevelCapabilityGapSynthesis:
    def test_capability_gap_synthesizes_build_mcp_server(self):
        state = _make_state([])
        state["capability_gaps"] = ["github_repository_management"]

        actions = _collect_actions(state, None)

        synthesized = [
            a for a in actions
            if a["action_type"] == "build_mcp_server"
        ]
        assert len(synthesized) == 1
        assert synthesized[0]["action_id"] == "build-github_repository_management"
        assert synthesized[0]["task_binding"]["task_id"] == "build_mcp_server"
        assert synthesized[0]["task_binding"]["args"] == {
            "capability": "github_repository_management",
        }

    def test_unknown_capability_gap_fails_closed(self):
        state = _make_state([])
        state["capability_gaps"] = ["unknown_capability"]

        actions = _collect_actions(state, None)

        assert actions == []
