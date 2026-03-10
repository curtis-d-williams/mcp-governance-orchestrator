# SPDX-License-Identifier: MIT
"""Regression tests for health_probe_example agent task.

Covers:
- run() returns OrderedDict with expected keys and fixed signal values
- result is JSON-serializable
- keys are in deterministic order
- repeated calls are deterministic
- TASK_REGISTRY alignment guard
- recent_failures value satisfies build_portfolio_state_from_artifacts.py threshold
"""

import json
from collections import OrderedDict

from agent_tasks.health_probe_example import TASK_NAME, run


class TestRun:
    def test_returns_ordered_dict(self):
        assert isinstance(run(), OrderedDict)

    def test_task_name_correct(self):
        assert run()["task_name"] == "health_probe_example"

    def test_task_name_matches_constant(self):
        assert run()["task_name"] == TASK_NAME

    def test_recent_failures_triggers_action_threshold(self):
        # build_portfolio_state_from_artifacts.py triggers rerun_failed_task when >= 2
        assert run()["recent_failures"] >= 2

    def test_stale_runs_present(self):
        assert "stale_runs" in run()

    def test_determinism_ok_present(self):
        assert "determinism_ok" in run()

    def test_determinism_ok_is_bool(self):
        assert isinstance(run()["determinism_ok"], bool)

    def test_recent_failures_is_int(self):
        assert isinstance(run()["recent_failures"], int)

    def test_stale_runs_is_int(self):
        assert isinstance(run()["stale_runs"], int)

    def test_result_is_json_serializable(self):
        result = run()
        dumped = json.dumps(result)
        assert isinstance(json.loads(dumped), dict)

    def test_keys_deterministic_order(self):
        result = run()
        assert list(result.keys()) == [
            "task_name",
            "recent_failures",
            "stale_runs",
            "determinism_ok",
        ]

    def test_deterministic_repeated_calls(self):
        assert run() == run()

    def test_no_file_outputs(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        run()
        assert list(tmp_path.iterdir()) == []


class TestRegistryAlignmentGuard:
    """TASK_NAME must appear in TASK_REGISTRY with correct metadata."""

    def test_task_name_in_registry(self):
        from agent_tasks.registry import TASK_REGISTRY
        assert TASK_NAME in TASK_REGISTRY

    def test_module_path_correct(self):
        from agent_tasks.registry import TASK_REGISTRY
        assert TASK_REGISTRY[TASK_NAME]["module"] == "agent_tasks.health_probe_example"

    def test_deterministic_flag_set(self):
        from agent_tasks.registry import TASK_REGISTRY
        assert TASK_REGISTRY[TASK_NAME]["deterministic"] is True

    def test_portfolio_safe_flag_set(self):
        from agent_tasks.registry import TASK_REGISTRY
        assert TASK_REGISTRY[TASK_NAME]["portfolio_safe"] is True

    def test_scope_is_local_repo(self):
        from agent_tasks.registry import TASK_REGISTRY
        assert TASK_REGISTRY[TASK_NAME]["scope"] == "local_repo"
