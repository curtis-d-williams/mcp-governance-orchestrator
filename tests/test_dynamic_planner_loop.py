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
_apply_learning_adjustments = _mod._apply_learning_adjustments

# ---------------------------------------------------------------------------
# Original integration test (preserved unchanged)
# ---------------------------------------------------------------------------

# Key artifacts
PORTFOLIO_CSV = Path("tier3_portfolio_report.csv")
AGGREGATE_JSON = Path("tier3_multi_run_aggregate.json")
LOG_FILE = Path("tier3_execution.log")

# Tasks expected from the dynamic planner (must match TASK_REGISTRY)
DYNAMIC_TASKS = [
    "build_portfolio_dashboard",
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
        assert _map_actions_to_tasks(actions) == ["build_portfolio_dashboard"]

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
        # Both action types map to build_portfolio_dashboard; deduplication yields one task.
        actions = [
            self._action("refresh_repo_health"),
            self._action("regenerate_missing_artifact"),
        ]
        result = _map_actions_to_tasks(actions, top_k=2)
        assert result == ["build_portfolio_dashboard"]

    def test_deduplication_preserves_first_occurrence(self):
        # Both map to the same task — only one entry in output
        actions = [
            self._action("refresh_repo_health"),   # → build_portfolio_dashboard
            self._action("rerun_failed_task"),      # → build_portfolio_dashboard (dup)
        ]
        result = _map_actions_to_tasks(actions, top_k=2)
        assert result == ["build_portfolio_dashboard"]

    def test_all_mapped_action_types_covered(self):
        for action_type, expected_task in ACTION_TO_TASK.items():
            result = _map_actions_to_tasks([self._action(action_type)])
            assert result == [expected_task], f"{action_type} should map to {expected_task}"

    def test_build_capability_artifact_maps_to_build_mcp_server_example(self):
        assert _map_actions_to_tasks([self._action("build_capability_artifact")]) == ["build_mcp_server_example"]

    def test_missing_action_type_key_skipped(self):
        actions = [{"priority": 0.9}]  # no action_type key
        assert _map_actions_to_tasks(actions) == []

    def test_order_preserved_for_distinct_mapped_tasks(self):
        # Both action types now map to build_portfolio_dashboard; deduplication yields one task.
        actions = [
            self._action("regenerate_missing_artifact"),  # → build_portfolio_dashboard
            self._action("refresh_repo_health"),          # → build_portfolio_dashboard (dup)
        ]
        result = _map_actions_to_tasks(actions, top_k=2)
        assert result == ["build_portfolio_dashboard"]


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
        mock_run.assert_called_once_with(["build_portfolio_dashboard"], Path("portfolio_state.json"))

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
        mock_run.assert_called_once_with(["build_portfolio_dashboard"], Path("portfolio_state.json"))

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
            "refresh_repo_health",           # → build_portfolio_dashboard
            "regenerate_missing_artifact",   # → build_portfolio_dashboard (dup, deduplicated)
        )
        with unittest.mock.patch.object(_mod, "_fetch_action_queue", return_value=actions), \
             unittest.mock.patch.object(_mod, "run_tasks") as mock_run:
            _mod.main(["--portfolio-state", str(state), "--top-k", "2"])
        tasks = mock_run.call_args[0][0]
        assert tasks == ["build_portfolio_dashboard"]

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

    def test_default_top_k_is_3(self, tmp_path):
        """Default --top-k must be 3: mapped actions in the first window are selected deterministically."""
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        actions = self._actions(
            "refresh_repo_health",              # → build_portfolio_dashboard
            "regenerate_missing_artifact",      # → build_portfolio_dashboard (dup)
            "run_determinism_regression_suite", # → build_portfolio_dashboard (dup)
        )
        with unittest.mock.patch.object(_mod, "_fetch_action_queue", return_value=actions), \
             unittest.mock.patch.object(_mod, "run_tasks") as mock_run:
            _mod.main(["--portfolio-state", str(state)])  # no explicit --top-k
        tasks = mock_run.call_args[0][0]
        assert tasks == ["build_portfolio_dashboard"]

    def test_multi_action_selection_preserves_deterministic_order(self, tmp_path):
        """top-k=3: duplicate mapped actions deduplicate deterministically."""
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        actions = self._actions(
            "regenerate_missing_artifact",      # → build_portfolio_dashboard (1st)
            "refresh_repo_health",              # → build_portfolio_dashboard (dup)
            "run_determinism_regression_suite", # → build_portfolio_dashboard (dup)
        )
        with unittest.mock.patch.object(_mod, "_fetch_action_queue", return_value=actions), \
             unittest.mock.patch.object(_mod, "run_tasks") as mock_run:
            _mod.main(["--portfolio-state", str(state), "--top-k", "3"])
        tasks = mock_run.call_args[0][0]
        assert tasks == ["build_portfolio_dashboard"]

    def test_fallback_unchanged_when_all_three_unmapped(self, tmp_path):
        """Even with top-k=3, all-unmapped queue falls back to ALL_TASKS."""
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        actions = self._actions("unknown_a", "unknown_b", "unknown_c")
        with unittest.mock.patch.object(_mod, "_fetch_action_queue", return_value=actions), \
             unittest.mock.patch.object(_mod, "run_tasks") as mock_run:
            _mod.main(["--portfolio-state", str(state)])
        tasks = mock_run.call_args[0][0]
        assert sorted(tasks) == sorted(ALL_TASKS)


class TestExplorationOffset:
    """--exploration-offset shifts the action window deterministically."""

    def _actions(self, *action_types):
        return [{"action_type": at, "priority": 0.9} for at in action_types]

    def _run(self, tmp_path, actions, extra_argv=None):
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        with unittest.mock.patch.object(_mod, "_fetch_action_queue", return_value=actions), \
             unittest.mock.patch.object(_mod, "run_tasks") as mock_run:
            _mod.main(["--portfolio-state", str(state)] + (extra_argv or []))
        return mock_run.call_args[0][0]

    def test_default_offset_zero_preserves_previous_behavior(self, tmp_path):
        """No --exploration-offset → same tasks as offset=0 explicitly."""
        actions = self._actions(
            "regenerate_missing_artifact",      # → build_portfolio_dashboard
            "run_determinism_regression_suite", # → intelligence_layer_example
            "refresh_repo_health",              # → repo_insights_example
        )
        tasks_default = self._run(tmp_path, actions, ["--top-k", "2"])
        tasks_explicit = self._run(tmp_path, actions, ["--top-k", "2", "--exploration-offset", "0"])
        assert tasks_default == tasks_explicit

    def test_offset_shifts_window_to_different_actions(self, tmp_path):
        """offset=0 picks first window; offset=2 picks a later window."""
        actions = self._actions(
            "regenerate_missing_artifact",      # [0] → build_portfolio_dashboard
            "run_determinism_regression_suite", # [1] → build_portfolio_dashboard
            "refresh_repo_health",              # [2] → build_portfolio_dashboard
            "build_capability_artifact",        # [3] → build_mcp_server_example
        )
        tasks_offset0 = self._run(tmp_path, actions, ["--top-k", "2", "--exploration-offset", "0"])
        tasks_offset2 = self._run(tmp_path, actions, ["--top-k", "2", "--exploration-offset", "2"])
        assert "build_portfolio_dashboard" in tasks_offset0
        assert tasks_offset2 == ["build_portfolio_dashboard", "build_mcp_server_example"]

    def test_offset_one_skips_first_action(self, tmp_path):
        """offset=1 skips index 0 and picks from index 1."""
        actions = self._actions(
            "regenerate_missing_artifact",      # [0] → build_portfolio_dashboard
            "refresh_repo_health",              # [1] → build_portfolio_dashboard
            "run_determinism_regression_suite", # [2] → build_portfolio_dashboard
        )
        tasks = self._run(tmp_path, actions, ["--top-k", "1", "--exploration-offset", "1"])
        assert tasks == ["build_portfolio_dashboard"]

    def test_large_offset_clamps_to_last_valid_window(self, tmp_path):
        """offset beyond queue length clamps to the last valid window."""
        # 3 actions, top_k=2 → max valid start = max(0, 3-2) = 1
        actions = self._actions(
            "regenerate_missing_artifact",      # [0] → build_portfolio_dashboard
            "refresh_repo_health",              # [1] → repo_insights_example
            "run_determinism_regression_suite", # [2] → intelligence_layer_example
        )
        tasks_huge = self._run(tmp_path, actions, ["--top-k", "2", "--exploration-offset", "999"])
        tasks_clamped = self._run(tmp_path, actions, ["--top-k", "2", "--exploration-offset", "1"])
        assert tasks_huge == tasks_clamped

    def test_offset_with_top_k_ge_queue_length_always_uses_full_queue(self, tmp_path):
        """When top_k >= queue size, offset is always clamped to 0."""
        actions = self._actions("refresh_repo_health", "regenerate_missing_artifact")
        # top_k=5 > len=2 → max start = max(0, 2-5) = 0 → any offset clamps to 0
        tasks_off0 = self._run(tmp_path, actions, ["--top-k", "5", "--exploration-offset", "0"])
        tasks_off99 = self._run(tmp_path, actions, ["--top-k", "5", "--exploration-offset", "99"])
        assert tasks_off0 == tasks_off99

    def test_offset_in_log_message(self, tmp_path, capsys):
        """Log must include offset and window fields."""
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        actions = self._actions("refresh_repo_health")
        with unittest.mock.patch.object(_mod, "_fetch_action_queue", return_value=actions), \
             unittest.mock.patch.object(_mod, "run_tasks"):
            _mod.main(["--portfolio-state", str(state), "--exploration-offset", "0"])
        out = capsys.readouterr().out
        assert "offset=0" in out
        assert "window=" in out


def test_run_tasks_builds_portfolio_state_after_aggregation(tmp_path):
    output_path = tmp_path / "portfolio_state.json"

    calls = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        class Proc:
            returncode = 0
            stdout = "wrote: " + str(output_path) + "\n"
            stderr = ""
        return Proc()

    with unittest.mock.patch.object(_mod, "log"), \
         unittest.mock.patch.object(_mod.subprocess, "run", side_effect=fake_run), \
         unittest.mock.patch("pathlib.Path.exists", return_value=True):
        _mod.run_tasks(["repo_insights_example"], output_path)

    assert len(calls) == 3
    assert any("run_portfolio_task.py" in str(part) for part in calls[0])
    assert any("aggregate_multi_run_envelopes.py" in str(part) for part in calls[1])
    assert any("build_portfolio_state_from_artifacts.py" in str(part) for part in calls[2])
    assert "--output" in calls[2]
    assert str(output_path) in calls[2]


# ---------------------------------------------------------------------------
# Registry alignment regression guard
# ---------------------------------------------------------------------------

class TestRegistryAlignment:
    """ALL_TASKS and ACTION_TO_TASK must only reference tasks present in TASK_REGISTRY.

    This is a regression guard: if either list drifts out of sync with the registry,
    planner experiments will fail at runtime with 'Unknown task' errors.
    """

    def test_all_tasks_in_registry(self):
        from agent_tasks.registry import TASK_REGISTRY
        for task in ALL_TASKS:
            assert task in TASK_REGISTRY, (
                f"ALL_TASKS references unknown task: {task!r}. "
                "Add it to TASK_REGISTRY or remove it from ALL_TASKS."
            )

    def test_action_to_task_values_in_registry(self):
        from agent_tasks.registry import TASK_REGISTRY
        for action_type, task in ACTION_TO_TASK.items():
            assert task in TASK_REGISTRY, (
                f"ACTION_TO_TASK[{action_type!r}] → unknown task: {task!r}. "
                "Add it to TASK_REGISTRY or update ACTION_TO_TASK."
            )


# ---------------------------------------------------------------------------
# TestCapabilityLedgerRankingEffect
# ---------------------------------------------------------------------------

class TestCapabilityLedgerRankingEffect:
    """Verify capability_ledger content alters action ranking in _apply_learning_adjustments."""

    _BASE_ACTION = {
        "action_type": "build_capability_artifact",
        "base_priority": 1.0,
        "action_id": "a1",
        "repo_id": "r1",
        "args": {"capability": "test_cap"},
    }
    _PLAIN_ACTION = {
        "action_type": "refresh_repo_health",
        "base_priority": 1.0,
        "action_id": "a2",
        "repo_id": "r1",
    }

    def test_high_success_ledger_boosts_capability_action(self):
        """A high-success capability ledger boosts the capability synthesis action above a plain action."""
        ledger = {"capabilities": {"test_cap": {
            "total_syntheses": 5,
            "successful_syntheses": 5,
            "successful_evolved_syntheses": 0,
        }}}
        # capability action starts second — ledger should lift it to first
        actions = [self._PLAIN_ACTION, self._BASE_ACTION]
        result = _apply_learning_adjustments(actions, {}, capability_ledger=ledger)
        assert result[0]["action_type"] == "build_capability_artifact", (
            f"Expected build_capability_artifact first after high-success ledger boost, got {result[0]['action_type']}"
        )

    def test_high_failure_ledger_demotes_capability_action(self):
        """A high-failure capability ledger demotes the capability synthesis action below a plain action."""
        ledger = {"capabilities": {"test_cap": {
            "total_syntheses": 5,
            "successful_syntheses": 0,
            "successful_evolved_syntheses": 0,
        }}}
        # capability action starts first — ledger should demote it to second
        actions = [self._BASE_ACTION, self._PLAIN_ACTION]
        result = _apply_learning_adjustments(actions, {}, capability_ledger=ledger)
        assert result[0]["action_type"] == "refresh_repo_health", (
            f"Expected refresh_repo_health first after high-failure ledger penalty, got {result[0]['action_type']}"
        )


# ---------------------------------------------------------------------------
# TestEffectivenessLedgerRankingEffect
# ---------------------------------------------------------------------------

class TestEffectivenessLedgerRankingEffect:
    """Verify action_types-format effectiveness ledger alters ranking in _apply_learning_adjustments."""

    _HIGH = {"action_type": "rerun_failed_task",  "base_priority": 1.0, "action_id": "a1", "repo_id": "r1"}
    _LOW  = {"action_type": "refresh_repo_health", "base_priority": 1.0, "action_id": "a2", "repo_id": "r1"}

    def _ledger(self, high_score, low_score):
        # Omit times_executed → confidence=1.0 (backward-compat path, planner_runtime.py:168-169)
        return {
            "rerun_failed_task":   {"effectiveness_score": high_score},
            "refresh_repo_health": {"effectiveness_score": low_score},
        }

    def test_high_effectiveness_action_ranks_first(self):
        """High-effectiveness action type ranks above low-effectiveness type with equal base_priority.

        Without ledger: refresh_repo_health sorts first (alphabetical tiebreaker).
        With ledger: rerun_failed_task (score=1.0) gains effectiveness_component=0.15
        and overtakes the alphabetical default, ranking first.
        """
        ledger = self._ledger(high_score=1.0, low_score=0.0)
        # Place low-effectiveness action first to confirm ledger flips the order.
        result = _apply_learning_adjustments([self._LOW, self._HIGH], ledger)
        assert result[0]["action_type"] == "rerun_failed_task", (
            f"Expected rerun_failed_task first with effectiveness_score=1.0, "
            f"got {result[0]['action_type']}"
        )

    def test_equal_effectiveness_preserves_alphabetical_tiebreaker(self):
        """Equal effectiveness scores preserve deterministic alphabetical tiebreaker."""
        ledger = self._ledger(high_score=0.5, low_score=0.5)
        # Equal adjustments → tiebreaker (action_type asc) decides: refresh < rerun.
        result = _apply_learning_adjustments([self._HIGH, self._LOW], ledger)
        assert result[0]["action_type"] == "refresh_repo_health", (
            f"Expected alphabetical tiebreaker (refresh_repo_health) with equal scores, "
            f"got {result[0]['action_type']}"
        )
