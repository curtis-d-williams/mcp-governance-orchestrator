# SPDX-License-Identifier: MIT
"""Narrow regression tests for --capture-feedback integration in
scripts/claude_dynamic_planner_loop.py.

Tests cover:
1. Default behavior unchanged when --capture-feedback is absent.
2. Capture mode fails closed when required args are missing.
3. Capture mode writes executed_actions.json with selected mapped actions only.
4. Capture mode invokes capture_execution_feedback.py with correct args.
5. Unmapped / empty queue fallback writes empty executed_actions.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest.mock as mock
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Load module under test
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "scripts" / "claude_dynamic_planner_loop.py"
_CAPTURE_SCRIPT = str(_REPO_ROOT / "scripts" / "capture_execution_feedback.py")

_spec = importlib.util.spec_from_file_location("claude_dynamic_planner_loop", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_selected_mapped_actions = _mod._selected_mapped_actions
_write_executed_actions = _mod._write_executed_actions
ACTION_TO_TASK = _mod.ACTION_TO_TASK
ALL_TASKS = _mod.ALL_TASKS


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _action(action_type, priority=0.9):
    return {"action_type": action_type, "priority": priority}


def _fake_proc(returncode=0, stdout="", stderr=""):
    m = mock.MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


def _all_capture_args(state_path, tmp_path):
    """Return a full valid set of --capture-feedback CLI args."""
    return [
        "--capture-feedback",
        "--portfolio-state", str(state_path),
        "--executed-actions-output", str(tmp_path / "executed_actions.json"),
        "--feedback-before-output", str(tmp_path / "before.json"),
        "--feedback-after-output", str(tmp_path / "after.json"),
        "--evaluation-output", str(tmp_path / "evaluation_records.json"),
        "--ledger-output", str(tmp_path / "ledger.json"),
    ]


# ---------------------------------------------------------------------------
# 1. Default behavior unchanged when --capture-feedback is absent
# ---------------------------------------------------------------------------

class TestDefaultBehaviorUnchanged:
    """Without --capture-feedback the planner runs exactly as before."""

    def test_no_flag_calls_run_tasks_once(self):
        with mock.patch.object(_mod, "run_tasks") as mock_run, \
             mock.patch.object(_mod, "_fetch_action_queue", return_value=[]):
            _mod.main([])
        mock_run.assert_called_once()

    def test_no_flag_fallback_tasks_are_all_tasks(self):
        with mock.patch.object(_mod, "run_tasks") as mock_run:
            _mod.main([])
        tasks = mock_run.call_args[0][0]
        assert sorted(tasks) == sorted(ALL_TASKS)

    def test_no_flag_no_capture_subprocess_called(self):
        """subprocess.run must not be called for capture_execution_feedback."""
        calls = []

        def fake_run(cmd, *a, **kw):
            calls.append(list(cmd))
            return _fake_proc()

        with mock.patch.object(_mod, "_fetch_action_queue", return_value=[]), \
             mock.patch.object(_mod.subprocess, "run", side_effect=fake_run), \
             mock.patch("pathlib.Path.exists", return_value=True):
            _mod.main([])

        assert not any("capture_execution_feedback" in str(part) for cmd in calls for part in cmd)

    def test_no_flag_with_portfolio_state_uses_action_path(self, tmp_path):
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        actions = [_action("refresh_repo_health")]
        with mock.patch.object(_mod, "_fetch_action_queue", return_value=actions), \
             mock.patch.object(_mod, "run_tasks") as mock_run:
            _mod.main(["--portfolio-state", str(state)])
        tasks = mock_run.call_args[0][0]
        assert tasks == ["repo_insights_example"]

    def test_no_flag_no_executed_actions_file_written(self, tmp_path):
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        executed_out = tmp_path / "executed_actions.json"
        actions = [_action("refresh_repo_health")]
        with mock.patch.object(_mod, "_fetch_action_queue", return_value=actions), \
             mock.patch.object(_mod, "run_tasks"):
            _mod.main(["--portfolio-state", str(state)])
        assert not executed_out.exists()


# ---------------------------------------------------------------------------
# 2. Capture mode fails closed when required args are missing
# ---------------------------------------------------------------------------

class TestCaptureFeedbackFailClosed:
    """--capture-feedback exits nonzero when any required arg is absent."""

    def _base_args(self, tmp_path):
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        return state

    def test_missing_portfolio_state_exits_nonzero(self, tmp_path):
        with pytest.raises(SystemExit) as exc:
            _mod.main([
                "--capture-feedback",
                "--executed-actions-output", str(tmp_path / "e.json"),
                "--feedback-before-output", str(tmp_path / "b.json"),
                "--feedback-after-output", str(tmp_path / "a.json"),
                "--evaluation-output", str(tmp_path / "ev.json"),
                "--ledger-output", str(tmp_path / "l.json"),
            ])
        assert exc.value.code != 0

    def test_missing_executed_actions_output_exits_nonzero(self, tmp_path):
        state = self._base_args(tmp_path)
        with pytest.raises(SystemExit) as exc:
            _mod.main([
                "--capture-feedback",
                "--portfolio-state", str(state),
                "--feedback-before-output", str(tmp_path / "b.json"),
                "--feedback-after-output", str(tmp_path / "a.json"),
                "--evaluation-output", str(tmp_path / "ev.json"),
                "--ledger-output", str(tmp_path / "l.json"),
            ])
        assert exc.value.code != 0

    def test_missing_feedback_before_output_exits_nonzero(self, tmp_path):
        state = self._base_args(tmp_path)
        with pytest.raises(SystemExit) as exc:
            _mod.main([
                "--capture-feedback",
                "--portfolio-state", str(state),
                "--executed-actions-output", str(tmp_path / "e.json"),
                "--feedback-after-output", str(tmp_path / "a.json"),
                "--evaluation-output", str(tmp_path / "ev.json"),
                "--ledger-output", str(tmp_path / "l.json"),
            ])
        assert exc.value.code != 0

    def test_missing_feedback_after_output_exits_nonzero(self, tmp_path):
        state = self._base_args(tmp_path)
        with pytest.raises(SystemExit) as exc:
            _mod.main([
                "--capture-feedback",
                "--portfolio-state", str(state),
                "--executed-actions-output", str(tmp_path / "e.json"),
                "--feedback-before-output", str(tmp_path / "b.json"),
                "--evaluation-output", str(tmp_path / "ev.json"),
                "--ledger-output", str(tmp_path / "l.json"),
            ])
        assert exc.value.code != 0

    def test_missing_evaluation_output_exits_nonzero(self, tmp_path):
        state = self._base_args(tmp_path)
        with pytest.raises(SystemExit) as exc:
            _mod.main([
                "--capture-feedback",
                "--portfolio-state", str(state),
                "--executed-actions-output", str(tmp_path / "e.json"),
                "--feedback-before-output", str(tmp_path / "b.json"),
                "--feedback-after-output", str(tmp_path / "a.json"),
                "--ledger-output", str(tmp_path / "l.json"),
            ])
        assert exc.value.code != 0

    def test_missing_ledger_output_exits_nonzero(self, tmp_path):
        state = self._base_args(tmp_path)
        with pytest.raises(SystemExit) as exc:
            _mod.main([
                "--capture-feedback",
                "--portfolio-state", str(state),
                "--executed-actions-output", str(tmp_path / "e.json"),
                "--feedback-before-output", str(tmp_path / "b.json"),
                "--feedback-after-output", str(tmp_path / "a.json"),
                "--evaluation-output", str(tmp_path / "ev.json"),
            ])
        assert exc.value.code != 0

    def test_error_message_names_missing_args(self, tmp_path, capsys):
        """parser.error message must name the missing flags."""
        with pytest.raises(SystemExit):
            _mod.main(["--capture-feedback"])
        captured = capsys.readouterr()
        # argparse writes errors to stderr
        assert "--portfolio-state" in captured.err


# ---------------------------------------------------------------------------
# 3. Capture mode writes executed_actions.json with selected mapped actions
# ---------------------------------------------------------------------------

class TestExecutedActionsOutput:
    """_write_executed_actions and main() write the correct action subset."""

    # --- unit tests for _selected_mapped_actions ---

    def test_mapped_action_included(self):
        actions = [_action("refresh_repo_health")]
        result = _selected_mapped_actions(actions)
        assert result == [{"action_type": "refresh_repo_health", "priority": 0.9}]

    def test_unmapped_action_excluded(self):
        actions = [_action("no_such_action")]
        assert _selected_mapped_actions(actions) == []

    def test_empty_actions_returns_empty(self):
        assert _selected_mapped_actions([]) == []

    def test_top_k_limits_selection(self):
        actions = [_action("no_such_action"), _action("refresh_repo_health")]
        # top_k=1 only looks at first action, which is unmapped
        assert _selected_mapped_actions(actions, top_k=1) == []

    def test_deduplication_by_task_name(self):
        # Both map to repo_insights_example — only first action dict returned.
        actions = [_action("refresh_repo_health"), _action("rerun_failed_task")]
        result = _selected_mapped_actions(actions, top_k=2)
        assert len(result) == 1
        assert result[0]["action_type"] == "refresh_repo_health"

    def test_preserves_first_occurrence_order(self):
        actions = [
            _action("regenerate_missing_artifact"),  # → build_portfolio_dashboard
            _action("refresh_repo_health"),           # → repo_insights_example
        ]
        result = _selected_mapped_actions(actions, top_k=2)
        assert [r["action_type"] for r in result] == [
            "regenerate_missing_artifact",
            "refresh_repo_health",
        ]

    def test_missing_action_type_key_excluded(self):
        actions = [{"priority": 0.9}]  # no action_type key
        assert _selected_mapped_actions(actions) == []

    # --- _write_executed_actions file output ---

    def test_write_creates_valid_json_file(self, tmp_path):
        actions = [{"action_type": "refresh_repo_health", "priority": 0.9}]
        out = tmp_path / "executed.json"
        _write_executed_actions(out, actions)
        loaded = json.loads(out.read_text(encoding="utf-8"))
        assert loaded == actions

    def test_write_empty_list_produces_valid_json(self, tmp_path):
        out = tmp_path / "executed.json"
        _write_executed_actions(out, [])
        loaded = json.loads(out.read_text(encoding="utf-8"))
        assert loaded == []

    def test_write_creates_parent_dirs(self, tmp_path):
        out = tmp_path / "nested" / "deep" / "executed.json"
        _write_executed_actions(out, [])
        assert out.exists()

    # --- main() integration: file content from action-driven path ---

    def test_main_writes_mapped_actions_only(self, tmp_path):
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        executed_out = tmp_path / "executed_actions.json"
        actions = [
            {"action_type": "refresh_repo_health", "priority": 0.9},
            {"action_type": "no_such_action", "priority": 0.5},
        ]

        with mock.patch.object(_mod, "_fetch_action_queue", return_value=actions), \
             mock.patch.object(_mod, "run_tasks"), \
             mock.patch.object(_mod, "_invoke_capture_feedback"):
            _mod.main(_all_capture_args(state, tmp_path))

        loaded = json.loads(executed_out.read_text(encoding="utf-8"))
        # top_k=1 (default) → only first action examined; it maps → included
        assert loaded == [{"action_type": "refresh_repo_health", "priority": 0.9}]

    def test_main_writes_empty_list_on_fallback(self, tmp_path):
        """When queue is empty / all unmapped, executed_actions must be []."""
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        executed_out = tmp_path / "executed_actions.json"

        with mock.patch.object(_mod, "_fetch_action_queue", return_value=[]), \
             mock.patch.object(_mod, "run_tasks"), \
             mock.patch.object(_mod, "_invoke_capture_feedback"):
            _mod.main(_all_capture_args(state, tmp_path))

        loaded = json.loads(executed_out.read_text(encoding="utf-8"))
        assert loaded == []

    def test_main_deduplicates_selected_actions(self, tmp_path):
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        executed_out = tmp_path / "executed_actions.json"
        actions = [
            {"action_type": "refresh_repo_health", "priority": 0.9},
            {"action_type": "rerun_failed_task", "priority": 0.8},  # same task
        ]

        with mock.patch.object(_mod, "_fetch_action_queue", return_value=actions), \
             mock.patch.object(_mod, "run_tasks"), \
             mock.patch.object(_mod, "_invoke_capture_feedback"):
            _mod.main(_all_capture_args(state, tmp_path) + ["--top-k", "2"])

        loaded = json.loads(executed_out.read_text(encoding="utf-8"))
        assert len(loaded) == 1
        assert loaded[0]["action_type"] == "refresh_repo_health"


# ---------------------------------------------------------------------------
# 4. Capture mode invokes capture_execution_feedback.py with correct args
# ---------------------------------------------------------------------------

class TestCaptureSubprocessInvocation:
    """main() must call capture_execution_feedback.py via subprocess with the
    correct flags after run_tasks completes."""

    def _run_and_capture_calls(self, tmp_path, actions=None, extra_argv=None):
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        if actions is None:
            actions = [_action("refresh_repo_health")]
        capture_calls = []

        def fake_invoke(args):
            capture_calls.append(args)

        with mock.patch.object(_mod, "_fetch_action_queue", return_value=actions), \
             mock.patch.object(_mod, "run_tasks"), \
             mock.patch.object(_mod, "_invoke_capture_feedback", side_effect=fake_invoke):
            argv = _all_capture_args(state, tmp_path) + (extra_argv or [])
            _mod.main(argv)

        return state, capture_calls

    def test_invoke_called_once(self, tmp_path):
        _, calls = self._run_and_capture_calls(tmp_path)
        assert len(calls) == 1

    def test_invoke_receives_portfolio_state(self, tmp_path):
        state, calls = self._run_and_capture_calls(tmp_path)
        assert calls[0].portfolio_state == str(state)

    def test_invoke_receives_executed_actions_output(self, tmp_path):
        _, calls = self._run_and_capture_calls(tmp_path)
        assert calls[0].executed_actions_output == str(tmp_path / "executed_actions.json")

    def test_invoke_receives_feedback_before_output(self, tmp_path):
        _, calls = self._run_and_capture_calls(tmp_path)
        assert calls[0].feedback_before_output == str(tmp_path / "before.json")

    def test_invoke_receives_feedback_after_output(self, tmp_path):
        _, calls = self._run_and_capture_calls(tmp_path)
        assert calls[0].feedback_after_output == str(tmp_path / "after.json")

    def test_invoke_receives_evaluation_output(self, tmp_path):
        _, calls = self._run_and_capture_calls(tmp_path)
        assert calls[0].evaluation_output == str(tmp_path / "evaluation_records.json")

    def test_invoke_receives_ledger_output(self, tmp_path):
        _, calls = self._run_and_capture_calls(tmp_path)
        assert calls[0].ledger_output == str(tmp_path / "ledger.json")

    def test_invoke_called_after_run_tasks(self, tmp_path):
        """_invoke_capture_feedback must always come after run_tasks."""
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        call_order = []

        with mock.patch.object(_mod, "_fetch_action_queue", return_value=[]), \
             mock.patch.object(_mod, "run_tasks", side_effect=lambda *a, **k: call_order.append("run_tasks")), \
             mock.patch.object(_mod, "_invoke_capture_feedback", side_effect=lambda *a: call_order.append("capture")):
            _mod.main(_all_capture_args(state, tmp_path))

        assert call_order == ["run_tasks", "capture"]

    def test_invoke_subprocess_command_contains_capture_script(self, tmp_path):
        """Integration-level: verify the real _invoke_capture_feedback builds
        a command referencing capture_execution_feedback.py."""
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        executed_out = tmp_path / "executed_actions.json"
        _write_executed_actions(executed_out, [])

        captured_cmds = []

        def fake_subprocess_run(cmd, *a, **kw):
            captured_cmds.append(list(cmd))
            return _fake_proc(0)

        with mock.patch.object(_mod, "_fetch_action_queue", return_value=[]), \
             mock.patch.object(_mod, "run_tasks"), \
             mock.patch.object(_mod.subprocess, "run", side_effect=fake_subprocess_run), \
             mock.patch.object(_mod, "log"):
            _mod.main(_all_capture_args(state, tmp_path))

        # At least one subprocess call should reference capture_execution_feedback.py
        assert any(
            "capture_execution_feedback.py" in str(part)
            for cmd in captured_cmds
            for part in cmd
        )

    def test_invoke_subprocess_command_passes_before_source(self, tmp_path):
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        _write_executed_actions(tmp_path / "executed_actions.json", [])
        captured_cmds = []

        def fake_subprocess_run(cmd, *a, **kw):
            captured_cmds.append(list(cmd))
            return _fake_proc(0)

        with mock.patch.object(_mod, "_fetch_action_queue", return_value=[]), \
             mock.patch.object(_mod, "run_tasks"), \
             mock.patch.object(_mod.subprocess, "run", side_effect=fake_subprocess_run), \
             mock.patch.object(_mod, "log"):
            _mod.main(_all_capture_args(state, tmp_path))

        capture_cmd = next(
            cmd for cmd in captured_cmds
            if any("capture_execution_feedback.py" in str(p) for p in cmd)
        )
        assert "--before-source" in capture_cmd
        assert str(state) in capture_cmd


# ---------------------------------------------------------------------------
# 5. Unmapped / empty queue fallback behavior unchanged
# ---------------------------------------------------------------------------

class TestFallbackBehaviorUnchanged:
    """With --capture-feedback, fallback paths still run all tasks correctly."""

    def test_empty_queue_still_runs_all_tasks(self, tmp_path):
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        with mock.patch.object(_mod, "_fetch_action_queue", return_value=[]), \
             mock.patch.object(_mod, "run_tasks") as mock_run, \
             mock.patch.object(_mod, "_invoke_capture_feedback"):
            _mod.main(_all_capture_args(state, tmp_path))
        tasks = mock_run.call_args[0][0]
        assert sorted(tasks) == sorted(ALL_TASKS)

    def test_unmapped_actions_still_run_all_tasks(self, tmp_path):
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        actions = [_action("completely_unknown_action")]
        with mock.patch.object(_mod, "_fetch_action_queue", return_value=actions), \
             mock.patch.object(_mod, "run_tasks") as mock_run, \
             mock.patch.object(_mod, "_invoke_capture_feedback"):
            _mod.main(_all_capture_args(state, tmp_path))
        tasks = mock_run.call_args[0][0]
        assert sorted(tasks) == sorted(ALL_TASKS)

    def test_empty_queue_writes_empty_executed_actions(self, tmp_path):
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        executed_out = tmp_path / "executed_actions.json"
        with mock.patch.object(_mod, "_fetch_action_queue", return_value=[]), \
             mock.patch.object(_mod, "run_tasks"), \
             mock.patch.object(_mod, "_invoke_capture_feedback"):
            _mod.main(_all_capture_args(state, tmp_path))
        loaded = json.loads(executed_out.read_text(encoding="utf-8"))
        assert loaded == []

    def test_unmapped_actions_write_empty_executed_actions(self, tmp_path):
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        executed_out = tmp_path / "executed_actions.json"
        actions = [_action("completely_unknown_action")]
        with mock.patch.object(_mod, "_fetch_action_queue", return_value=actions), \
             mock.patch.object(_mod, "run_tasks"), \
             mock.patch.object(_mod, "_invoke_capture_feedback"):
            _mod.main(_all_capture_args(state, tmp_path))
        loaded = json.loads(executed_out.read_text(encoding="utf-8"))
        assert loaded == []

    def test_capture_invoked_even_on_fallback_path(self, tmp_path):
        """Feedback capture must run even when action queue was empty."""
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        with mock.patch.object(_mod, "_fetch_action_queue", return_value=[]), \
             mock.patch.object(_mod, "run_tasks"), \
             mock.patch.object(_mod, "_invoke_capture_feedback") as mock_invoke:
            _mod.main(_all_capture_args(state, tmp_path))
        mock_invoke.assert_called_once()
