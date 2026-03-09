# SPDX-License-Identifier: MIT
"""Regression tests for repo_insights_example agent task.

Covers:
- collect_insights returns correct counts for each well-known subdir
- missing subdirs count as 0 (fail-safe)
- subdirectories inside a watched dir are not counted as files
- result is JSON-serializable
- keys are in deterministic order
- run() delegates to collect_insights
- TASK_REGISTRY alignment guard
"""

import json
from collections import OrderedDict
from pathlib import Path

import pytest

from agent_tasks.repo_insights_example import TASK_NAME, collect_insights, run


class TestCollectInsights:
    def test_returns_ordered_dict(self, tmp_path):
        result = collect_insights(tmp_path)
        assert isinstance(result, OrderedDict)

    def test_task_name_correct(self, tmp_path):
        result = collect_insights(tmp_path)
        assert result["task_name"] == "repo_insights_example"

    def test_task_name_constant_matches(self, tmp_path):
        result = collect_insights(tmp_path)
        assert result["task_name"] == TASK_NAME

    def test_counts_scripts_dir(self, tmp_path):
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "a.py").write_text("")
        (scripts / "b.py").write_text("")
        result = collect_insights(tmp_path)
        assert result["scripts_count"] == 2

    def test_counts_tests_dir(self, tmp_path):
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "test_a.py").write_text("")
        result = collect_insights(tmp_path)
        assert result["tests_count"] == 1

    def test_counts_agent_tasks_dir(self, tmp_path):
        at = tmp_path / "agent_tasks"
        at.mkdir()
        (at / "task.py").write_text("")
        (at / "__init__.py").write_text("")
        result = collect_insights(tmp_path)
        assert result["agent_tasks_count"] == 2

    def test_missing_scripts_dir_counts_zero(self, tmp_path):
        result = collect_insights(tmp_path)
        assert result["scripts_count"] == 0

    def test_missing_tests_dir_counts_zero(self, tmp_path):
        result = collect_insights(tmp_path)
        assert result["tests_count"] == 0

    def test_missing_agent_tasks_dir_counts_zero(self, tmp_path):
        result = collect_insights(tmp_path)
        assert result["agent_tasks_count"] == 0

    def test_subdirs_not_counted_as_files(self, tmp_path):
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "subpkg").mkdir()
        result = collect_insights(tmp_path)
        assert result["scripts_count"] == 0

    def test_mixed_files_and_subdirs(self, tmp_path):
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "a.py").write_text("")
        (scripts / "subpkg").mkdir()
        result = collect_insights(tmp_path)
        assert result["scripts_count"] == 1

    def test_result_is_json_serializable(self, tmp_path):
        result = collect_insights(tmp_path)
        dumped = json.dumps(result)
        assert isinstance(json.loads(dumped), dict)

    def test_deterministic_repeated_calls(self, tmp_path):
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "x.py").write_text("")
        r1 = collect_insights(tmp_path)
        r2 = collect_insights(tmp_path)
        assert r1 == r2

    def test_keys_deterministic_order(self, tmp_path):
        result = collect_insights(tmp_path)
        keys = list(result.keys())
        assert keys == ["task_name", "scripts_count", "tests_count", "agent_tasks_count"]

    def test_default_repo_root_uses_cwd(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "scripts").mkdir()
        result = collect_insights()
        assert "scripts_count" in result

    def test_str_path_accepted(self, tmp_path):
        result = collect_insights(str(tmp_path))
        assert result["task_name"] == TASK_NAME

    def test_multiple_subdirs_independent(self, tmp_path):
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "a.py").write_text("")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "t.py").write_text("")
        (tmp_path / "tests" / "u.py").write_text("")
        result = collect_insights(tmp_path)
        assert result["scripts_count"] == 1
        assert result["tests_count"] == 2
        assert result["agent_tasks_count"] == 0


class TestRun:
    def test_run_returns_ordered_dict(self, tmp_path):
        result = run(tmp_path)
        assert isinstance(result, OrderedDict)

    def test_run_matches_collect_insights(self, tmp_path):
        assert run(tmp_path) == collect_insights(tmp_path)

    def test_run_no_args_uses_cwd(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        result = run()
        assert result["task_name"] == TASK_NAME

    def test_run_deterministic(self, tmp_path):
        assert run(tmp_path) == run(tmp_path)


class TestRegistryAlignmentGuard:
    """TASK_NAME must appear in TASK_REGISTRY with correct metadata."""

    def test_task_name_in_registry(self):
        from agent_tasks.registry import TASK_REGISTRY
        assert TASK_NAME in TASK_REGISTRY

    def test_module_path_correct(self):
        from agent_tasks.registry import TASK_REGISTRY
        assert TASK_REGISTRY[TASK_NAME]["module"] == "agent_tasks.repo_insights_example"

    def test_deterministic_flag_set(self):
        from agent_tasks.registry import TASK_REGISTRY
        assert TASK_REGISTRY[TASK_NAME]["deterministic"] is True

    def test_portfolio_safe_flag_set(self):
        from agent_tasks.registry import TASK_REGISTRY
        assert TASK_REGISTRY[TASK_NAME]["portfolio_safe"] is True

    def test_scope_is_local_repo(self):
        from agent_tasks.registry import TASK_REGISTRY
        assert TASK_REGISTRY[TASK_NAME]["scope"] == "local_repo"

    def test_task_in_all_tasks(self):
        from scripts.claude_dynamic_planner_loop import ALL_TASKS
        assert TASK_NAME in ALL_TASKS

    def test_analyze_repo_insights_maps_to_task(self):
        from scripts.claude_dynamic_planner_loop import ACTION_TO_TASK
        assert ACTION_TO_TASK.get("analyze_repo_insights") == TASK_NAME
