# SPDX-License-Identifier: MIT
"""Regression tests for v0.34 planner orchestration simplification + runtime safety.

Covers:
- --max-actions deterministically caps selected actions
- default behavior unchanged without the flag
- empty queue handled cleanly (no-op)
- missing optional files degrade safely
- load_runtime_context, select_actions, run_selected_actions, write_explain_artifact
  are importable and behave correctly
- existing planner tests are unaffected (backward-compat smoke)
"""
import importlib.util
import json
import sys
import unittest.mock
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Load module under test via importlib (mirrors test_dynamic_planner_loop.py)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SCRIPT = _REPO_ROOT / "scripts" / "claude_dynamic_planner_loop.py"
_spec = importlib.util.spec_from_file_location("claude_dynamic_planner_loop", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _action(action_type, priority=0.9):
    return {"action_type": action_type, "priority": priority}


def _actions(*action_types):
    return [_action(at) for at in action_types]


def _run_main(tmp_path, extra_argv, patched_actions=None):
    """Run main() with a temp portfolio_state and optional mocked action queue.

    Returns the task list passed to run_tasks (via run_selected_actions).
    """
    state = tmp_path / "state.json"
    state.write_text("{}", encoding="utf-8")
    argv = ["--portfolio-state", str(state)] + extra_argv
    if patched_actions is None:
        patched_actions = []
    with unittest.mock.patch.object(_mod, "_fetch_action_queue", return_value=patched_actions), \
         unittest.mock.patch.object(_mod, "run_tasks") as mock_run:
        _mod.main(argv)
    return mock_run.call_args[0][0]


# ---------------------------------------------------------------------------
# 1. New helpers are importable
# ---------------------------------------------------------------------------

class TestNewHelpersImportable:
    def test_load_runtime_context_importable(self):
        assert callable(_mod.load_runtime_context)

    def test_select_actions_importable(self):
        assert callable(_mod.select_actions)

    def test_run_selected_actions_importable(self):
        assert callable(_mod.run_selected_actions)

    def test_write_explain_artifact_importable(self):
        assert callable(_mod.write_explain_artifact)


# ---------------------------------------------------------------------------
# 2. --max-actions caps selected actions deterministically
# ---------------------------------------------------------------------------

class TestMaxActionsFlag:
    """--max-actions is the only behavioral addition in v0.34."""

    def test_max_actions_caps_to_one(self, tmp_path):
        """Three mapped actions → only one when --max-actions 1."""
        actions = _actions(
            "refresh_repo_health",              # → repo_insights_example
            "regenerate_missing_artifact",      # → build_portfolio_dashboard
            "run_determinism_regression_suite", # → intelligence_layer_example
        )
        tasks = _run_main(tmp_path, ["--top-k", "3", "--max-actions", "1"], actions)
        assert len(tasks) == 1
        assert tasks[0] == "repo_insights_example"

    def test_max_actions_caps_to_two(self, tmp_path):
        """Three mapped actions → two when --max-actions 2."""
        actions = _actions(
            "refresh_repo_health",
            "regenerate_missing_artifact",
            "run_determinism_regression_suite",
        )
        tasks = _run_main(tmp_path, ["--top-k", "3", "--max-actions", "2"], actions)
        assert len(tasks) == 2
        assert tasks == ["repo_insights_example", "build_portfolio_dashboard"]

    def test_max_actions_larger_than_queue_does_not_truncate(self, tmp_path):
        """--max-actions 10 with only 2 actions → both returned."""
        actions = _actions("refresh_repo_health", "regenerate_missing_artifact")
        tasks = _run_main(tmp_path, ["--top-k", "2", "--max-actions", "10"], actions)
        assert len(tasks) == 2

    def test_max_actions_zero_produces_empty_list(self, tmp_path):
        """--max-actions 0 → empty task list (no-op run)."""
        actions = _actions("refresh_repo_health", "regenerate_missing_artifact")
        tasks = _run_main(tmp_path, ["--top-k", "2", "--max-actions", "0"], actions)
        assert tasks == []

    def test_max_actions_cap_is_deterministic_across_calls(self, tmp_path):
        """Repeated calls with same inputs produce identical capped lists."""
        actions = _actions(
            "refresh_repo_health",
            "regenerate_missing_artifact",
            "run_determinism_regression_suite",
        )
        tasks_a = _run_main(tmp_path, ["--top-k", "3", "--max-actions", "2"], actions)
        tasks_b = _run_main(tmp_path, ["--top-k", "3", "--max-actions", "2"], actions)
        assert tasks_a == tasks_b

    def test_max_actions_applied_after_ranking_preserves_order(self, tmp_path):
        """Capping preserves first-occurrence order of mapped actions."""
        # Action order matters: regenerate first, then refresh
        actions = _actions(
            "regenerate_missing_artifact",      # → build_portfolio_dashboard (1st)
            "refresh_repo_health",              # → repo_insights_example (2nd)
            "run_determinism_regression_suite", # → intelligence_layer_example (3rd)
        )
        tasks = _run_main(tmp_path, ["--top-k", "3", "--max-actions", "2"], actions)
        assert tasks == ["build_portfolio_dashboard", "repo_insights_example"]

    def test_max_actions_applies_to_fallback_tasks_too(self, tmp_path):
        """--max-actions caps the ALL_TASKS fallback when queue is empty."""
        # Empty action list → fallback to sorted(ALL_TASKS)
        tasks = _run_main(tmp_path, ["--max-actions", "1"], [])
        assert len(tasks) == 1

    def test_max_actions_absent_does_not_cap(self, tmp_path):
        """Without --max-actions, all mapped tasks are returned."""
        actions = _actions(
            "refresh_repo_health",
            "regenerate_missing_artifact",
            "run_determinism_regression_suite",
        )
        tasks = _run_main(tmp_path, ["--top-k", "3"], actions)
        assert len(tasks) == 3


# ---------------------------------------------------------------------------
# 3. Default behavior unchanged without --max-actions
# ---------------------------------------------------------------------------

class TestDefaultBehaviorPreserved:
    """Ensure v0.33 behavior is exactly preserved when --max-actions is absent."""

    def test_fallback_without_flag_returns_all_tasks(self, tmp_path):
        tasks = _run_main(tmp_path, [], [])
        assert sorted(tasks) == sorted(_mod.ALL_TASKS)

    def test_action_driven_without_flag_returns_mapped_tasks(self, tmp_path):
        actions = _actions("refresh_repo_health", "regenerate_missing_artifact")
        tasks = _run_main(tmp_path, ["--top-k", "2"], actions)
        assert "repo_insights_example" in tasks
        assert "build_portfolio_dashboard" in tasks

    def test_top_k_unaffected_by_absence_of_max_actions(self, tmp_path):
        actions = _actions(
            "refresh_repo_health",
            "regenerate_missing_artifact",
            "run_determinism_regression_suite",
        )
        # top-k=2 → two tasks; no cap
        tasks = _run_main(tmp_path, ["--top-k", "2"], actions)
        assert len(tasks) == 2

    def test_no_portfolio_state_uses_fallback_unchanged(self):
        with unittest.mock.patch.object(_mod, "run_tasks") as mock_run:
            _mod.main([])
        tasks = mock_run.call_args[0][0]
        assert sorted(tasks) == sorted(_mod.ALL_TASKS)


# ---------------------------------------------------------------------------
# 4. Empty queue is a clean no-op
# ---------------------------------------------------------------------------

class TestEmptyQueueNoOp:
    def test_empty_queue_falls_back_to_all_tasks(self, tmp_path):
        tasks = _run_main(tmp_path, [], [])
        assert sorted(tasks) == sorted(_mod.ALL_TASKS)

    def test_empty_queue_with_max_actions_still_returns_tasks(self, tmp_path):
        """Empty queue → fallback tasks, then capped by max_actions."""
        tasks = _run_main(tmp_path, ["--max-actions", "2"], [])
        assert len(tasks) == 2

    def test_run_tasks_empty_list_is_noop(self, capsys):
        """run_tasks([]) logs no-tasks and returns without subprocess calls."""
        with unittest.mock.patch.object(_mod.subprocess, "run") as mock_sub, \
             unittest.mock.patch.object(_mod, "log") as mock_log:
            _mod.run_tasks([])
        mock_sub.assert_not_called()
        # log should have been called with the no-tasks message
        calls = [str(c) for c in mock_log.call_args_list]
        assert any("No tasks to run" in c for c in calls)

    def test_select_actions_empty_raw_returns_empty_tasks(self, tmp_path):
        """select_actions with empty raw_actions → empty tasks_to_run."""
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")

        class _FakeArgs:
            top_k = 3
            exploration_offset = 0
            portfolio_state = str(state)
            ledger = None
            policy = None

        tasks, action_dicts, sorted_actions = _mod.select_actions(
            _FakeArgs(), [], {}, {}, {}
        )
        assert tasks == []
        assert action_dicts == []
        assert sorted_actions == []


# ---------------------------------------------------------------------------
# 5. Missing optional files degrade safely
# ---------------------------------------------------------------------------

class TestMissingFilesDegradeSafely:
    def test_missing_ledger_file_does_not_raise(self, tmp_path):
        """load_runtime_context with non-existent ledger path → empty dict."""
        state = tmp_path / "state.json"
        state.write_text('{"repos": []}', encoding="utf-8")

        class _FakeArgs:
            portfolio_state = str(state)
            ledger = str(tmp_path / "nonexistent_ledger.json")
            policy = None

        ledger, signals, policy = _mod.load_runtime_context(_FakeArgs())
        assert ledger == {}
        assert policy == {}

    def test_missing_policy_file_does_not_raise(self, tmp_path):
        state = tmp_path / "state.json"
        state.write_text('{"repos": []}', encoding="utf-8")

        class _FakeArgs:
            portfolio_state = str(state)
            ledger = None
            policy = str(tmp_path / "nonexistent_policy.json")

        ledger, signals, policy = _mod.load_runtime_context(_FakeArgs())
        assert policy == {}

    def test_missing_portfolio_state_signals_returns_empty(self, tmp_path):
        class _FakeArgs:
            portfolio_state = str(tmp_path / "nonexistent_state.json")
            ledger = None
            policy = None

        ledger, signals, policy = _mod.load_runtime_context(_FakeArgs())
        assert signals == {}

    def test_malformed_ledger_file_returns_empty(self, tmp_path):
        bad = tmp_path / "bad_ledger.json"
        bad.write_text("not valid json", encoding="utf-8")

        class _FakeArgs:
            portfolio_state = None
            ledger = str(bad)
            policy = None

        ledger, signals, policy = _mod.load_runtime_context(_FakeArgs())
        assert ledger == {}

    def test_main_with_nonexistent_portfolio_state_falls_back(self, tmp_path):
        """main() with a nonexistent --portfolio-state degrades to fallback."""
        missing = tmp_path / "does_not_exist.json"
        with unittest.mock.patch.object(_mod, "_fetch_action_queue", return_value=[]), \
             unittest.mock.patch.object(_mod, "run_tasks") as mock_run:
            _mod.main(["--portfolio-state", str(missing)])
        tasks = mock_run.call_args[0][0]
        assert sorted(tasks) == sorted(_mod.ALL_TASKS)


# ---------------------------------------------------------------------------
# 6. load_runtime_context correctness
# ---------------------------------------------------------------------------

class TestLoadRuntimeContext:
    def test_returns_three_tuple(self, tmp_path):
        state = tmp_path / "s.json"
        state.write_text('{"repos": []}', encoding="utf-8")

        class _FakeArgs:
            portfolio_state = str(state)
            ledger = None
            policy = None

        result = _mod.load_runtime_context(_FakeArgs())
        assert len(result) == 3

    def test_ledger_loaded_when_present(self, tmp_path):
        ledger_data = {
            "action_types": [
                {"action_type": "refresh_repo_health", "effectiveness_score": 0.8,
                 "effect_deltas": {}, "times_executed": 5}
            ]
        }
        ledger_file = tmp_path / "ledger.json"
        ledger_file.write_text(json.dumps(ledger_data), encoding="utf-8")
        state = tmp_path / "s.json"
        state.write_text('{"repos": []}', encoding="utf-8")

        class _FakeArgs:
            portfolio_state = str(state)
            ledger = str(ledger_file)
            policy = None

        ledger, signals, policy = _mod.load_runtime_context(_FakeArgs())
        assert "refresh_repo_health" in ledger


# ---------------------------------------------------------------------------
# 7. select_actions correctness
# ---------------------------------------------------------------------------

class TestSelectActions:
    def _fake_args(self, top_k=3, exploration_offset=0, state_path=None):
        class _Args:
            pass
        a = _Args()
        a.top_k = top_k
        a.exploration_offset = exploration_offset
        a.portfolio_state = state_path
        return a

    def test_returns_three_tuple(self):
        result = _mod.select_actions(self._fake_args(), [], {}, {}, {})
        assert len(result) == 3

    def test_maps_single_action_to_task(self):
        actions = [_action("refresh_repo_health")]
        tasks, _, sorted_actions = _mod.select_actions(
            self._fake_args(top_k=1), actions, {}, {}, {}
        )
        assert tasks == ["repo_insights_example"]

    def test_sorted_actions_contains_full_list(self):
        actions = [_action("refresh_repo_health"), _action("regenerate_missing_artifact")]
        _, _, sorted_actions = _mod.select_actions(
            self._fake_args(top_k=2), actions, {}, {}, {}
        )
        assert len(sorted_actions) == 2

    def test_top_k_limits_window(self):
        actions = [_action("refresh_repo_health"), _action("regenerate_missing_artifact")]
        tasks, _, _ = _mod.select_actions(self._fake_args(top_k=1), actions, {}, {}, {})
        assert len(tasks) <= 1


# ---------------------------------------------------------------------------
# 8. run_selected_actions delegates to run_tasks
# ---------------------------------------------------------------------------

class TestRunSelectedActions:
    def test_delegates_to_run_tasks(self, tmp_path):
        out = tmp_path / "state.json"
        with unittest.mock.patch.object(_mod, "run_tasks") as mock_run:
            _mod.run_selected_actions(["repo_insights_example"], out)
        mock_run.assert_called_once_with(["repo_insights_example"], out)

    def test_empty_tasks_propagated(self, tmp_path):
        out = tmp_path / "state.json"
        with unittest.mock.patch.object(_mod, "run_tasks") as mock_run:
            _mod.run_selected_actions([], out)
        mock_run.assert_called_once_with([], out)


# ---------------------------------------------------------------------------
# 9. write_explain_artifact
# ---------------------------------------------------------------------------

class TestWriteExplainArtifact:
    def test_writes_json_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # Patch log to avoid writing tier3_execution.log
        with unittest.mock.patch.object(_mod, "log"):
            _mod.write_explain_artifact([], {}, {}, {})
        artifact = tmp_path / "planner_priority_breakdown.json"
        assert artifact.exists()
        data = json.loads(artifact.read_text(encoding="utf-8"))
        assert data == []

    def test_empty_actions_writes_empty_list(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with unittest.mock.patch.object(_mod, "log"):
            _mod.write_explain_artifact([], {}, {}, {})
        data = json.loads((tmp_path / "planner_priority_breakdown.json").read_text())
        assert data == []

    def test_schema_fields_present(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        actions = [_action("refresh_repo_health")]
        ledger = {
            "refresh_repo_health": {
                "effectiveness_score": 0.5,
                "effect_deltas": {},
                "times_executed": 3,
            }
        }
        with unittest.mock.patch.object(_mod, "log"):
            _mod.write_explain_artifact(actions, ledger, {}, {})
        data = json.loads((tmp_path / "planner_priority_breakdown.json").read_text())
        assert len(data) == 1
        expected_fields = {
            "action_type", "base_priority", "effectiveness_component",
            "signal_delta_component", "weak_signal_targeting_component",
            "policy_component", "confidence_factor", "exploration_component",
            "final_priority",
        }
        assert set(data[0].keys()) == expected_fields


# ---------------------------------------------------------------------------
# 10. Backward-compat: existing re-exports still present
# ---------------------------------------------------------------------------

class TestBackwardCompatReExports:
    """Symbols re-exported from planner_scoring must still be importable."""

    def test_scoring_symbols_still_re_exported(self):
        from scripts.claude_dynamic_planner_loop import (  # noqa: F401
            CONFIDENCE_THRESHOLD, EFFECTIVENESS_CLAMP, EFFECTIVENESS_WEIGHT,
            EXPLORATION_CLAMP, EXPLORATION_WEIGHT, POLICY_TOTAL_ABS_CAP,
            POLICY_WEIGHT_CLAMP, SIGNAL_IMPACT_CLAMP, SIGNAL_IMPACT_WEIGHT,
            TARGETING_CLAMP, TARGETING_WEIGHT, PriorityBreakdown,
            _apply_learning_adjustments, _build_priority_breakdown,
            _compute_priority_breakdown, compute_confidence_factor,
            compute_exploration_bonus, compute_learning_adjustment,
            compute_policy_adjustment, compute_weak_signal_targeting_adjustment,
            load_effectiveness_ledger, load_planner_policy, load_portfolio_signals,
        )

    def test_loop_symbols_still_present(self):
        from scripts.claude_dynamic_planner_loop import (  # noqa: F401
            ACTION_TO_TASK, ALL_TASKS, main, run_tasks,
        )
