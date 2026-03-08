from pathlib import Path
import importlib.util
import json
import subprocess
import sys
import unittest.mock
import pandas as pd

import pytest

# ---------------------------------------------------------------------------
# Load private helpers from script via importlib
# ---------------------------------------------------------------------------

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "claude_dynamic_planner_loop.py"

_spec = importlib.util.spec_from_file_location("claude_dynamic_planner_loop", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_fetch_action_queue = _mod._fetch_action_queue
_map_actions_to_tasks = _mod._map_actions_to_tasks
ACTION_TO_TASK = _mod.ACTION_TO_TASK
ALL_TASKS = _mod.ALL_TASKS

# ---------------------------------------------------------------------------
# Original integration test (preserved unchanged)
# ---------------------------------------------------------------------------

# Key artifacts
PORTFOLIO_CSV = Path("tier3_portfolio_report.csv")
AGGREGATE_JSON = Path("tier3_multi_run_aggregate.json")
LOG_FILE = Path("tier3_execution.log")

# Tasks expected from the dynamic planner
DYNAMIC_TASKS = [
    "build_portfolio_dashboard",
    "repo_insights_example",
    "intelligence_layer_example"
]

def test_dynamic_planner_loop_execution():
    # Clear previous log
    if LOG_FILE.exists():
        LOG_FILE.unlink()

    # Run the planner-driven dynamic Claude loop
    subprocess.run(
        ["python3", "scripts/claude_dynamic_planner_loop.py"],
        check=True
    )

    # Validate artifacts exist
    assert PORTFOLIO_CSV.exists(), "Portfolio CSV missing after dynamic planner run"
    assert AGGREGATE_JSON.exists(), "Aggregate JSON missing after dynamic planner run"
    assert LOG_FILE.exists(), "Execution log missing after dynamic planner run"

    # Validate CSV is non-empty
    df = pd.read_csv(PORTFOLIO_CSV)
    assert len(df) > 0, "Portfolio CSV is empty"
    for task in DYNAMIC_TASKS:
        assert task in df['task'].values, f"Task {task} missing from portfolio CSV"

    # Validate aggregated JSON contains all tasks
    with AGGREGATE_JSON.open() as f:
        aggregated = json.load(f)
    for task in DYNAMIC_TASKS:
        assert any(entry["task"] == task for entry in aggregated), f"Task {task} missing in aggregate JSON"

    # Validate log contains entries for all tasks
    log_content = LOG_FILE.read_text()
    for task in DYNAMIC_TASKS:
        assert task in log_content, f"Task {task} missing in execution log"


# ---------------------------------------------------------------------------
# _map_actions_to_tasks unit tests
# ---------------------------------------------------------------------------

class TestMapActionsToTasks:
    def _action(self, action_type):
        return {"action_type": action_type, "priority": 0.9}

    def test_single_mapped_action_returns_task(self):
        actions = [self._action("refresh_repo_health")]
        assert _map_actions_to_tasks(actions) == ["repo_insights_example"]

    def test_single_unmapped_action_returns_empty(self):
        actions = [self._action("unknown_action_type")]
        assert _map_actions_to_tasks(actions) == []

    def test_empty_actions_returns_empty(self):
        assert _map_actions_to_tasks([]) == []

    def test_top_k_limits_actions_considered(self):
        # Only first action considered (top_k=1); second would map to something
        actions = [
            self._action("unknown_action_type"),
            self._action("refresh_repo_health"),
        ]
        assert _map_actions_to_tasks(actions, top_k=1) == []

    def test_top_k_two_includes_second_action(self):
        actions = [
            self._action("refresh_repo_health"),
            self._action("regenerate_missing_artifact"),
        ]
        result = _map_actions_to_tasks(actions, top_k=2)
        assert "repo_insights_example" in result
        assert "build_portfolio_dashboard" in result

    def test_deduplication_preserves_first_occurrence(self):
        # Both map to the same task — only one entry in output
        actions = [
            self._action("refresh_repo_health"),   # → repo_insights_example
            self._action("rerun_failed_task"),      # → repo_insights_example (dup)
        ]
        result = _map_actions_to_tasks(actions, top_k=2)
        assert result == ["repo_insights_example"]

    def test_all_mapped_action_types_covered(self):
        for action_type, expected_task in ACTION_TO_TASK.items():
            result = _map_actions_to_tasks([self._action(action_type)])
            assert result == [expected_task], f"{action_type} should map to {expected_task}"

    def test_missing_action_type_key_skipped(self):
        actions = [{"priority": 0.9}]  # no action_type key
        assert _map_actions_to_tasks(actions) == []

    def test_order_preserved_for_distinct_mapped_tasks(self):
        actions = [
            self._action("regenerate_missing_artifact"),  # → build_portfolio_dashboard
            self._action("refresh_repo_health"),          # → repo_insights_example
        ]
        result = _map_actions_to_tasks(actions, top_k=2)
        assert result == ["build_portfolio_dashboard", "repo_insights_example"]


# ---------------------------------------------------------------------------
# _fetch_action_queue unit tests
# ---------------------------------------------------------------------------

class TestFetchActionQueue:
    def _make_proc(self, returncode, stdout="[]", stderr=""):
        m = unittest.mock.MagicMock()
        m.returncode = returncode
        m.stdout = stdout
        m.stderr = stderr
        return m

    def test_returns_parsed_json_on_success(self, tmp_path):
        payload = [{"action_type": "refresh_repo_health", "priority": 0.9}]
        proc = self._make_proc(0, json.dumps(payload))
        with unittest.mock.patch.object(_mod.subprocess, "run", return_value=proc) as mock_run:
            state_path = tmp_path / "portfolio_state.json"
            result = _fetch_action_queue(state_path)
        assert result == payload

    def test_returns_empty_on_nonzero_returncode(self, tmp_path):
        proc = self._make_proc(1, "", "some error")
        with unittest.mock.patch.object(_mod.subprocess, "run", return_value=proc):
            result = _fetch_action_queue(tmp_path / "s.json")
        assert result == []

    def test_returns_empty_on_exception(self, tmp_path):
        with unittest.mock.patch.object(_mod.subprocess, "run", side_effect=OSError("fail")):
            result = _fetch_action_queue(tmp_path / "s.json")
        assert result == []

    def test_cmd_includes_json_flag(self, tmp_path):
        proc = self._make_proc(0, "[]")
        state_path = tmp_path / "portfolio_state.json"
        with unittest.mock.patch.object(_mod.subprocess, "run", return_value=proc) as mock_run:
            _fetch_action_queue(state_path)
        cmd = mock_run.call_args[0][0]
        assert "--json" in cmd
        assert "--input" in cmd
        assert str(state_path) in cmd

    def test_cmd_includes_ledger_flag_when_provided(self, tmp_path):
        proc = self._make_proc(0, "[]")
        state_path = tmp_path / "s.json"
        ledger_path = tmp_path / "ledger.json"
        with unittest.mock.patch.object(_mod.subprocess, "run", return_value=proc) as mock_run:
            _fetch_action_queue(state_path, ledger_path)
        cmd = mock_run.call_args[0][0]
        assert "--ledger" in cmd
        assert str(ledger_path) in cmd

    def test_cmd_omits_ledger_flag_when_not_provided(self, tmp_path):
        proc = self._make_proc(0, "[]")
        with unittest.mock.patch.object(_mod.subprocess, "run", return_value=proc) as mock_run:
            _fetch_action_queue(tmp_path / "s.json")
        cmd = mock_run.call_args[0][0]
        assert "--ledger" not in cmd

    def test_cmd_invokes_list_portfolio_actions_script(self, tmp_path):
        proc = self._make_proc(0, "[]")
        with unittest.mock.patch.object(_mod.subprocess, "run", return_value=proc) as mock_run:
            _fetch_action_queue(tmp_path / "s.json")
        cmd = mock_run.call_args[0][0]
        assert any("list_portfolio_actions.py" in str(c) for c in cmd)


# ---------------------------------------------------------------------------
# main() behavior unit tests
# ---------------------------------------------------------------------------

class TestMainFallback:
    """main() without --portfolio-state uses prioritize_tasks() fallback."""

    def test_no_portfolio_state_uses_fallback(self):
        with unittest.mock.patch.object(_mod, "run_tasks") as mock_run:
            _mod.main([])
        mock_run.assert_called_once()
        tasks = mock_run.call_args[0][0]
        assert sorted(tasks) == sorted(ALL_TASKS)

    def test_fallback_logs_correct_message(self, capsys):
        with unittest.mock.patch.object(_mod, "run_tasks"):
            _mod.main([])
        # log() writes to stdout
        captured = capsys.readouterr()
        assert "fallback task selection" in captured.out


class TestMainActionDriven:
    """main() with --portfolio-state dispatches via action queue."""

    def _actions(self, *action_types):
        return [{"action_type": at, "priority": 0.9} for at in action_types]

    def test_action_driven_selection_without_ledger(self, tmp_path):
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        actions = self._actions("refresh_repo_health")
        with unittest.mock.patch.object(_mod, "_fetch_action_queue", return_value=actions) as mock_fetch, \
             unittest.mock.patch.object(_mod, "run_tasks") as mock_run:
            _mod.main(["--portfolio-state", str(state)])
        mock_fetch.assert_called_once_with(str(state), None)
        mock_run.assert_called_once_with(["repo_insights_example"])

    def test_action_driven_selection_with_ledger(self, tmp_path):
        state = tmp_path / "state.json"
        ledger = tmp_path / "ledger.json"
        state.write_text("{}", encoding="utf-8")
        ledger.write_text("{}", encoding="utf-8")
        actions = self._actions("regenerate_missing_artifact")
        with unittest.mock.patch.object(_mod, "_fetch_action_queue", return_value=actions) as mock_fetch, \
             unittest.mock.patch.object(_mod, "run_tasks") as mock_run:
            _mod.main(["--portfolio-state", str(state), "--ledger", str(ledger)])
        mock_fetch.assert_called_once_with(str(state), str(ledger))
        mock_run.assert_called_once_with(["build_portfolio_dashboard"])

    def test_empty_queue_falls_back_to_all_tasks(self, tmp_path):
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        with unittest.mock.patch.object(_mod, "_fetch_action_queue", return_value=[]), \
             unittest.mock.patch.object(_mod, "run_tasks") as mock_run:
            _mod.main(["--portfolio-state", str(state)])
        tasks = mock_run.call_args[0][0]
        assert sorted(tasks) == sorted(ALL_TASKS)

    def test_unmapped_actions_fall_back_to_all_tasks(self, tmp_path):
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        actions = self._actions("no_such_action")
        with unittest.mock.patch.object(_mod, "_fetch_action_queue", return_value=actions), \
             unittest.mock.patch.object(_mod, "run_tasks") as mock_run:
            _mod.main(["--portfolio-state", str(state)])
        tasks = mock_run.call_args[0][0]
        assert sorted(tasks) == sorted(ALL_TASKS)

    def test_top_k_passed_through(self, tmp_path):
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        actions = self._actions(
            "refresh_repo_health",           # → repo_insights_example
            "regenerate_missing_artifact",   # → build_portfolio_dashboard
        )
        with unittest.mock.patch.object(_mod, "_fetch_action_queue", return_value=actions), \
             unittest.mock.patch.object(_mod, "run_tasks") as mock_run:
            _mod.main(["--portfolio-state", str(state), "--top-k", "2"])
        tasks = mock_run.call_args[0][0]
        assert "repo_insights_example" in tasks
        assert "build_portfolio_dashboard" in tasks

    def test_action_driven_logs_selection_message(self, tmp_path, capsys):
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        actions = self._actions("refresh_repo_health")
        with unittest.mock.patch.object(_mod, "_fetch_action_queue", return_value=actions), \
             unittest.mock.patch.object(_mod, "run_tasks"):
            _mod.main(["--portfolio-state", str(state)])
        captured = capsys.readouterr()
        assert "action-driven selection" in captured.out

    def test_fallback_log_on_empty_queue(self, tmp_path, capsys):
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        with unittest.mock.patch.object(_mod, "_fetch_action_queue", return_value=[]), \
             unittest.mock.patch.object(_mod, "run_tasks"):
            _mod.main(["--portfolio-state", str(state)])
        captured = capsys.readouterr()
        assert "falling back" in captured.out
