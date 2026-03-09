# SPDX-License-Identifier: MIT
"""Regression tests for v0.35 planner run envelope.

Covers:
- no --run-envelope flag preserves existing behavior unchanged
- run envelope is written deterministically
- envelope contents match selected actions
- explain artifact path is recorded correctly
- write_run_envelope unit behavior
- existing planner tests still pass (backward compat smoke)
"""
import importlib.util
import json
import sys
import unittest.mock
from pathlib import Path

import pytest

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


def _run_main(tmp_path, extra_argv=None, patched_actions=None):
    """Run main() with a temp portfolio_state. Returns mock_run call args."""
    state = tmp_path / "state.json"
    state.write_text("{}", encoding="utf-8")
    argv = ["--portfolio-state", str(state)] + (extra_argv or [])
    if patched_actions is None:
        patched_actions = []
    with unittest.mock.patch.object(_mod, "_fetch_action_queue", return_value=patched_actions), \
         unittest.mock.patch.object(_mod, "run_tasks") as mock_run:
        _mod.main(argv)
    return mock_run


class _FakeArgs:
    portfolio_state = None
    ledger = None
    policy = None
    top_k = 3
    exploration_offset = 0
    max_actions = None
    explain = False


# ---------------------------------------------------------------------------
# 1. write_run_envelope and PLANNER_VERSION are importable
# ---------------------------------------------------------------------------

class TestNewSymbolsImportable:
    def test_write_run_envelope_callable(self):
        assert callable(_mod.write_run_envelope)

    def test_planner_version_present(self):
        assert hasattr(_mod, "PLANNER_VERSION")
        assert isinstance(_mod.PLANNER_VERSION, str)
        assert _mod.PLANNER_VERSION == "0.35"


# ---------------------------------------------------------------------------
# 2. No --run-envelope flag preserves default behavior
# ---------------------------------------------------------------------------

class TestNoEnvelopeFlagPreservesDefault:
    def test_no_envelope_no_file_written(self, tmp_path):
        envelope_path = tmp_path / "envelope.json"
        _run_main(tmp_path, [], [])
        assert not envelope_path.exists()

    def test_tasks_unchanged_without_envelope_flag(self, tmp_path):
        actions = _actions("refresh_repo_health", "regenerate_missing_artifact")
        mock_run = _run_main(tmp_path, ["--top-k", "2"], actions)
        tasks = mock_run.call_args[0][0]
        assert "repo_insights_example" in tasks
        assert "build_portfolio_dashboard" in tasks

    def test_no_portfolio_state_no_envelope(self, tmp_path):
        with unittest.mock.patch.object(_mod, "run_tasks"):
            _mod.main([])
        # No envelope file was written anywhere reachable — just verifying no error raised.

    def test_fallback_tasks_returned_without_flag(self, tmp_path):
        mock_run = _run_main(tmp_path, [], [])
        tasks = mock_run.call_args[0][0]
        assert sorted(tasks) == sorted(_mod.ALL_TASKS)


# ---------------------------------------------------------------------------
# 3. Envelope written deterministically
# ---------------------------------------------------------------------------

class TestEnvelopeWrittenDeterministically:
    def test_envelope_file_created_when_flag_set(self, tmp_path):
        ep = tmp_path / "run.json"
        _run_main(tmp_path, ["--run-envelope", str(ep)], [])
        assert ep.exists()

    def test_envelope_is_valid_json(self, tmp_path):
        ep = tmp_path / "run.json"
        _run_main(tmp_path, ["--run-envelope", str(ep)], [])
        data = json.loads(ep.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_envelope_deterministic_same_inputs(self, tmp_path):
        ep_a = tmp_path / "a.json"
        ep_b = tmp_path / "b.json"
        actions = _actions("refresh_repo_health")
        for ep in [ep_a, ep_b]:
            _run_main(tmp_path, ["--top-k", "1", "--run-envelope", str(ep)], actions)
        assert ep_a.read_text(encoding="utf-8") == ep_b.read_text(encoding="utf-8")

    def test_envelope_top_level_fields_present(self, tmp_path):
        ep = tmp_path / "run.json"
        _run_main(tmp_path, ["--run-envelope", str(ep)], [])
        data = json.loads(ep.read_text(encoding="utf-8"))
        for field in ("planner_version", "inputs", "selected_actions",
                      "selection_count", "artifacts", "execution"):
            assert field in data, f"Missing top-level field: {field}"

    def test_envelope_inputs_fields_present(self, tmp_path):
        ep = tmp_path / "run.json"
        _run_main(tmp_path, ["--run-envelope", str(ep)], [])
        data = json.loads(ep.read_text(encoding="utf-8"))
        for field in ("portfolio_state", "ledger", "policy", "top_k",
                      "exploration_offset", "max_actions", "explain"):
            assert field in data["inputs"], f"Missing inputs field: {field}"

    def test_envelope_version_matches_constant(self, tmp_path):
        ep = tmp_path / "run.json"
        _run_main(tmp_path, ["--run-envelope", str(ep)], [])
        data = json.loads(ep.read_text(encoding="utf-8"))
        assert data["planner_version"] == _mod.PLANNER_VERSION

    def test_envelope_execution_status_ok(self, tmp_path):
        ep = tmp_path / "run.json"
        _run_main(tmp_path, ["--run-envelope", str(ep)], [])
        data = json.loads(ep.read_text(encoding="utf-8"))
        assert data["execution"]["executed"] is True
        assert data["execution"]["status"] == "ok"


# ---------------------------------------------------------------------------
# 4. Envelope contents match selected actions
# ---------------------------------------------------------------------------

class TestEnvelopeContentsMatchSelectedActions:
    def test_selected_actions_matches_tasks_run(self, tmp_path):
        ep = tmp_path / "run.json"
        actions = _actions("refresh_repo_health")
        mock_run = _run_main(tmp_path, ["--top-k", "1", "--run-envelope", str(ep)], actions)
        expected_tasks = mock_run.call_args[0][0]
        data = json.loads(ep.read_text(encoding="utf-8"))
        assert data["selected_actions"] == expected_tasks

    def test_selection_count_equals_len_selected_actions(self, tmp_path):
        ep = tmp_path / "run.json"
        actions = _actions("refresh_repo_health", "regenerate_missing_artifact")
        _run_main(tmp_path, ["--top-k", "2", "--run-envelope", str(ep)], actions)
        data = json.loads(ep.read_text(encoding="utf-8"))
        assert data["selection_count"] == len(data["selected_actions"])

    def test_fallback_tasks_recorded_in_envelope(self, tmp_path):
        ep = tmp_path / "run.json"
        _run_main(tmp_path, ["--run-envelope", str(ep)], [])
        data = json.loads(ep.read_text(encoding="utf-8"))
        assert isinstance(data["selected_actions"], list)

    def test_max_actions_cap_reflected_in_envelope(self, tmp_path):
        ep = tmp_path / "run.json"
        actions = _actions(
            "refresh_repo_health",
            "regenerate_missing_artifact",
            "run_determinism_regression_suite",
        )
        _run_main(tmp_path, ["--top-k", "3", "--max-actions", "1",
                              "--run-envelope", str(ep)], actions)
        data = json.loads(ep.read_text(encoding="utf-8"))
        assert data["selection_count"] == 1
        assert len(data["selected_actions"]) == 1

    def test_inputs_top_k_recorded(self, tmp_path):
        ep = tmp_path / "run.json"
        _run_main(tmp_path, ["--top-k", "2", "--run-envelope", str(ep)], [])
        data = json.loads(ep.read_text(encoding="utf-8"))
        assert data["inputs"]["top_k"] == 2

    def test_inputs_exploration_offset_recorded(self, tmp_path):
        ep = tmp_path / "run.json"
        _run_main(tmp_path, ["--exploration-offset", "1", "--run-envelope", str(ep)], [])
        data = json.loads(ep.read_text(encoding="utf-8"))
        assert data["inputs"]["exploration_offset"] == 1

    def test_inputs_max_actions_recorded(self, tmp_path):
        ep = tmp_path / "run.json"
        _run_main(tmp_path, ["--max-actions", "2", "--run-envelope", str(ep)], [])
        data = json.loads(ep.read_text(encoding="utf-8"))
        assert data["inputs"]["max_actions"] == 2

    def test_inputs_max_actions_null_when_absent(self, tmp_path):
        ep = tmp_path / "run.json"
        _run_main(tmp_path, ["--run-envelope", str(ep)], [])
        data = json.loads(ep.read_text(encoding="utf-8"))
        assert data["inputs"]["max_actions"] is None


# ---------------------------------------------------------------------------
# 5. Explain artifact path recorded correctly
# ---------------------------------------------------------------------------

class TestExplainArtifactPathRecorded:
    def test_explain_artifact_null_without_explain_flag(self, tmp_path):
        ep = tmp_path / "run.json"
        _run_main(tmp_path, ["--run-envelope", str(ep)], [])
        data = json.loads(ep.read_text(encoding="utf-8"))
        assert data["artifacts"]["explain_artifact"] is None

    def test_explain_artifact_path_set_when_explain_used(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ep = tmp_path / "run.json"
        actions = []
        with unittest.mock.patch.object(_mod, "_fetch_action_queue", return_value=actions), \
             unittest.mock.patch.object(_mod, "run_tasks"), \
             unittest.mock.patch.object(_mod, "log"):
            state = tmp_path / "state.json"
            state.write_text("{}", encoding="utf-8")
            _mod.main(["--portfolio-state", str(state), "--explain",
                       "--run-envelope", str(ep)])
        data = json.loads(ep.read_text(encoding="utf-8"))
        assert data["artifacts"]["explain_artifact"] is not None
        assert "planner_priority_breakdown.json" in data["artifacts"]["explain_artifact"]

    def test_inputs_explain_false_without_flag(self, tmp_path):
        ep = tmp_path / "run.json"
        _run_main(tmp_path, ["--run-envelope", str(ep)], [])
        data = json.loads(ep.read_text(encoding="utf-8"))
        assert data["inputs"]["explain"] is False

    def test_inputs_explain_true_with_flag(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ep = tmp_path / "run.json"
        with unittest.mock.patch.object(_mod, "_fetch_action_queue", return_value=[]), \
             unittest.mock.patch.object(_mod, "run_tasks"), \
             unittest.mock.patch.object(_mod, "log"):
            state = tmp_path / "state.json"
            state.write_text("{}", encoding="utf-8")
            _mod.main(["--portfolio-state", str(state), "--explain",
                       "--run-envelope", str(ep)])
        data = json.loads(ep.read_text(encoding="utf-8"))
        assert data["inputs"]["explain"] is True


# ---------------------------------------------------------------------------
# 6. write_run_envelope unit tests
# ---------------------------------------------------------------------------

class TestWriteRunEnvelopeUnit:
    def test_writes_file_at_given_path(self, tmp_path):
        out = tmp_path / "env.json"
        _mod.write_run_envelope(str(out), _FakeArgs(), ["repo_insights_example"])
        assert out.exists()

    def test_selected_actions_stored(self, tmp_path):
        out = tmp_path / "env.json"
        tasks = ["repo_insights_example", "build_portfolio_dashboard"]
        _mod.write_run_envelope(str(out), _FakeArgs(), tasks)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["selected_actions"] == tasks

    def test_selection_count_correct(self, tmp_path):
        out = tmp_path / "env.json"
        tasks = ["repo_insights_example", "build_portfolio_dashboard"]
        _mod.write_run_envelope(str(out), _FakeArgs(), tasks)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["selection_count"] == 2

    def test_explain_artifact_null_by_default(self, tmp_path):
        out = tmp_path / "env.json"
        _mod.write_run_envelope(str(out), _FakeArgs(), [])
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["artifacts"]["explain_artifact"] is None

    def test_explain_artifact_path_stored(self, tmp_path):
        out = tmp_path / "env.json"
        _mod.write_run_envelope(str(out), _FakeArgs(), [], explain_artifact_path="foo/bar.json")
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["artifacts"]["explain_artifact"] == "foo/bar.json"

    def test_creates_parent_directories(self, tmp_path):
        out = tmp_path / "a" / "b" / "c" / "env.json"
        _mod.write_run_envelope(str(out), _FakeArgs(), [])
        assert out.exists()

    def test_output_deterministic(self, tmp_path):
        out_a = tmp_path / "a.json"
        out_b = tmp_path / "b.json"
        tasks = ["repo_insights_example"]
        _mod.write_run_envelope(str(out_a), _FakeArgs(), tasks)
        _mod.write_run_envelope(str(out_b), _FakeArgs(), tasks)
        assert out_a.read_text(encoding="utf-8") == out_b.read_text(encoding="utf-8")

    def test_empty_tasks_recorded(self, tmp_path):
        out = tmp_path / "env.json"
        _mod.write_run_envelope(str(out), _FakeArgs(), [])
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["selected_actions"] == []
        assert data["selection_count"] == 0

    def test_planner_version_in_output(self, tmp_path):
        out = tmp_path / "env.json"
        _mod.write_run_envelope(str(out), _FakeArgs(), [])
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["planner_version"] == _mod.PLANNER_VERSION


# ---------------------------------------------------------------------------
# 7. Backward compatibility: existing symbols still importable
# ---------------------------------------------------------------------------

class TestBackwardCompatImports:
    def test_scoring_symbols_still_present(self):
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

    def test_v034_symbols_still_present(self):
        from scripts.claude_dynamic_planner_loop import (  # noqa: F401
            load_runtime_context, select_actions,
            run_selected_actions, write_explain_artifact,
        )
