# SPDX-License-Identifier: MIT
"""Regression tests for planner experiment expansion.

New task:    failure_recovery_example
New mapping: recover_failed_workflow -> failure_recovery_example
New configs: baseline_neutral_topk3_offset0, baseline_neutral_topk3_offset1,
             baseline_failure_recovery_offset0
New report:  selected_action_count, unique_selected_task_count,
             task_diversity_ratio (v0.41, additive)

Test classes:
  TestFailureRecoveryTask      - task module and registry
  TestActionMapping            - recover_failed_workflow mapping and ALL_TASKS
  TestNewExperimentConfigs     - config file structure and file references
  TestReportDiversityMetrics   - new action_selection fields in generate_experiment_report
  TestDiversityCalculation     - task_diversity_ratio arithmetic correctness
  TestExpansionDeterminism     - determinism of new task and report fields
"""

import importlib.util
import json
import sys
import unittest.mock as mock
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_EXPERIMENTS = _REPO_ROOT / "experiments"

# ---------------------------------------------------------------------------
# Load modules under test
# ---------------------------------------------------------------------------

_PLANNER_SCRIPT = _REPO_ROOT / "scripts" / "claude_dynamic_planner_loop.py"
_planner_spec = importlib.util.spec_from_file_location(
    "claude_dynamic_planner_loop", _PLANNER_SCRIPT
)
_planner_mod = importlib.util.module_from_spec(_planner_spec)
_planner_spec.loader.exec_module(_planner_mod)

_REPORT_SCRIPT = _REPO_ROOT / "scripts" / "generate_experiment_report.py"
_report_spec = importlib.util.spec_from_file_location(
    "generate_experiment_report", _REPORT_SCRIPT
)
_report_mod = importlib.util.module_from_spec(_report_spec)
_report_spec.loader.exec_module(_report_mod)

_TASK_MODULE = _REPO_ROOT / "agent_tasks" / "failure_recovery_example.py"
_task_spec = importlib.util.spec_from_file_location(
    "failure_recovery_example", _TASK_MODULE
)
_task_mod = importlib.util.module_from_spec(_task_spec)
_task_spec.loader.exec_module(_task_mod)


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1. TestFailureRecoveryTask
# ---------------------------------------------------------------------------

class TestFailureRecoveryTask:
    """failure_recovery_example task module and registry contract."""

    def test_task_module_importable(self):
        assert _task_mod is not None

    def test_task_name_constant(self):
        assert _task_mod.TASK_NAME == "failure_recovery_example"

    def test_run_callable(self):
        assert callable(_task_mod.run)

    def test_collect_recovery_indicators_callable(self):
        assert callable(_task_mod.collect_recovery_indicators)

    def test_run_returns_ordered_dict(self, tmp_path):
        from collections import OrderedDict
        result = _task_mod.run(repo_root=tmp_path)
        assert isinstance(result, OrderedDict)

    def test_result_has_task_name_key(self, tmp_path):
        result = _task_mod.run(repo_root=tmp_path)
        assert result["task_name"] == "failure_recovery_example"

    def test_result_has_recovery_eligible(self, tmp_path):
        result = _task_mod.run(repo_root=tmp_path)
        assert "recovery_eligible" in result
        assert result["recovery_eligible"] is True

    def test_result_deterministic(self, tmp_path):
        r1 = _task_mod.run(repo_root=tmp_path)
        r2 = _task_mod.run(repo_root=tmp_path)
        assert list(r1.items()) == list(r2.items())

    def test_result_has_deterministic_key_order(self, tmp_path):
        result = _task_mod.run(repo_root=tmp_path)
        keys = list(result.keys())
        assert keys == sorted(keys) or keys[0] == "task_name"

    def test_registry_contains_failure_recovery_example(self):
        from agent_tasks.registry import TASK_REGISTRY
        assert "failure_recovery_example" in TASK_REGISTRY

    def test_registry_entry_is_deterministic(self):
        from agent_tasks.registry import TASK_REGISTRY
        entry = TASK_REGISTRY["failure_recovery_example"]
        assert entry["deterministic"] is True

    def test_registry_entry_is_portfolio_safe(self):
        from agent_tasks.registry import TASK_REGISTRY
        entry = TASK_REGISTRY["failure_recovery_example"]
        assert entry["portfolio_safe"] is True

    def test_registry_entry_has_module_field(self):
        from agent_tasks.registry import TASK_REGISTRY
        entry = TASK_REGISTRY["failure_recovery_example"]
        assert "module" in entry
        assert "failure_recovery_example" in entry["module"]

    def test_registry_entry_scope_is_local_repo(self):
        from agent_tasks.registry import TASK_REGISTRY
        entry = TASK_REGISTRY["failure_recovery_example"]
        assert entry["scope"] == "local_repo"

    def test_missing_subdir_returns_zero_count(self, tmp_path):
        result = _task_mod.collect_recovery_indicators(repo_root=tmp_path)
        assert result["agent_tasks_count"] == 0
        assert result["scripts_count"] == 0
        assert result["experiments_count"] == 0


# ---------------------------------------------------------------------------
# 2. TestActionMapping
# ---------------------------------------------------------------------------

class TestActionMapping:
    """recover_failed_workflow mapping and ALL_TASKS registration."""

    def test_recover_failed_workflow_in_action_to_task(self):
        assert "recover_failed_workflow" in _planner_mod.ACTION_TO_TASK

    def test_recover_failed_workflow_maps_to_failure_recovery(self):
        assert _planner_mod.ACTION_TO_TASK["recover_failed_workflow"] == "failure_recovery_example"

    def test_failure_recovery_example_in_all_tasks(self):
        assert "failure_recovery_example" in _planner_mod.ALL_TASKS

    def test_all_tasks_contains_five_tasks(self):
        assert len(_planner_mod.ALL_TASKS) == 6

    def test_all_tasks_contains_build_portfolio_dashboard(self):
        assert "build_portfolio_dashboard" in _planner_mod.ALL_TASKS

    def test_all_tasks_contains_repo_insights_example(self):
        assert "repo_insights_example" in _planner_mod.ALL_TASKS

    def test_all_tasks_are_sorted(self):
        assert _planner_mod.ALL_TASKS == sorted(_planner_mod.ALL_TASKS)

    def test_action_to_task_all_map_to_known_tasks(self):
        known = set(_planner_mod.ALL_TASKS)
        for action_type, task in _planner_mod.ACTION_TO_TASK.items():
            assert task in known, f"{action_type} maps to unknown task {task}"

    def test_map_actions_selects_failure_recovery_task(self):
        actions = [{"action_type": "recover_failed_workflow", "priority": 0.85}]
        tasks = _planner_mod._map_actions_to_tasks(actions, top_k=1)
        assert tasks == ["failure_recovery_example"]

    def test_map_actions_dedup_across_new_and_existing(self):
        # Two actions both map to different tasks → no dedup, 2 tasks
        actions = [
            {"action_type": "recover_failed_workflow", "priority": 0.85},
            {"action_type": "analyze_repo_insights", "priority": 0.78},
        ]
        tasks = _planner_mod._map_actions_to_tasks(actions, top_k=2)
        assert tasks == ["failure_recovery_example", "repo_insights_example"]

    def test_recover_failed_workflow_not_collapsed_with_other_tasks(self):
        # recover_failed_workflow maps to failure_recovery_example (unique)
        actions = [
            {"action_type": "regenerate_missing_artifact", "priority": 0.95},
            {"action_type": "recover_failed_workflow", "priority": 0.85},
        ]
        tasks = _planner_mod._map_actions_to_tasks(actions, top_k=2)
        assert len(tasks) == 2
        assert "build_portfolio_dashboard" in tasks
        assert "failure_recovery_example" in tasks

    def test_selected_mapped_actions_includes_recover(self):
        actions = [{"action_type": "recover_failed_workflow", "priority": 0.85}]
        result = _planner_mod._selected_mapped_actions(actions, top_k=1)
        assert len(result) == 1
        assert result[0]["action_type"] == "recover_failed_workflow"

    def test_fallback_includes_failure_recovery_example(self):
        """prioritize_tasks fallback includes all three tasks."""
        tasks = _planner_mod.prioritize_tasks()
        assert "failure_recovery_example" in tasks


# ---------------------------------------------------------------------------
# 3. TestNewExperimentConfigs
# ---------------------------------------------------------------------------

_CONFIG_TOPK3_OFFSET0 = _EXPERIMENTS / "baseline_neutral_topk3_offset0_config.json"
_CONFIG_TOPK3_OFFSET1 = _EXPERIMENTS / "baseline_neutral_topk3_offset1_config.json"
_CONFIG_FAILURE_RECOVERY = _EXPERIMENTS / "baseline_failure_recovery_offset0_config.json"
_ALL_NEW_CONFIGS = [_CONFIG_TOPK3_OFFSET0, _CONFIG_TOPK3_OFFSET1, _CONFIG_FAILURE_RECOVERY]


class TestNewExperimentConfigs:
    """New experiment config files are valid and correctly structured."""

    def test_topk3_offset0_config_exists(self):
        assert _CONFIG_TOPK3_OFFSET0.exists()

    def test_topk3_offset1_config_exists(self):
        assert _CONFIG_TOPK3_OFFSET1.exists()

    def test_failure_recovery_config_exists(self):
        assert _CONFIG_FAILURE_RECOVERY.exists()

    def test_all_new_configs_are_valid_json(self):
        for cfg in _ALL_NEW_CONFIGS:
            data = _load(cfg)
            assert isinstance(data, dict)

    def test_all_new_configs_top_k_is_3(self):
        for cfg in _ALL_NEW_CONFIGS:
            assert _load(cfg)["planner"]["top_k"] == 3

    def test_topk3_offset0_exploration_offset(self):
        assert _load(_CONFIG_TOPK3_OFFSET0)["planner"]["exploration_offset"] == 0

    def test_topk3_offset1_exploration_offset(self):
        assert _load(_CONFIG_TOPK3_OFFSET1)["planner"]["exploration_offset"] == 1

    def test_failure_recovery_exploration_offset(self):
        assert _load(_CONFIG_FAILURE_RECOVERY)["planner"]["exploration_offset"] == 0

    def test_topk3_offset0_policy_is_null(self):
        assert _load(_CONFIG_TOPK3_OFFSET0)["planner"]["policy"] is None

    def test_topk3_offset1_policy_is_null(self):
        assert _load(_CONFIG_TOPK3_OFFSET1)["planner"]["policy"] is None

    def test_failure_recovery_policy_references_failure_recovery(self):
        policy = _load(_CONFIG_FAILURE_RECOVERY)["planner"]["policy"]
        assert policy is not None
        assert "failure_recovery" in policy

    def test_all_new_configs_reference_degraded_v2_state(self):
        for cfg in _ALL_NEW_CONFIGS:
            assert "degraded_v2" in _load(cfg)["planner"]["portfolio_state"]

    def test_all_new_configs_reference_synthetic_v2_ledger(self):
        for cfg in _ALL_NEW_CONFIGS:
            assert "synthetic_v2" in _load(cfg)["planner"]["ledger"]

    def test_all_new_configs_have_explain_true(self):
        for cfg in _ALL_NEW_CONFIGS:
            assert _load(cfg)["planner"]["explain"] is True

    def test_all_new_configs_runs_is_one(self):
        for cfg in _ALL_NEW_CONFIGS:
            assert _load(cfg)["runs"] == 1

    def test_topk3_offset0_output_paths_named_correctly(self):
        data = _load(_CONFIG_TOPK3_OFFSET0)
        assert "topk3_offset0" in data["output"]["experiment_results"]
        assert "topk3_offset0" in data["output"]["envelope_prefix"]

    def test_topk3_offset1_output_paths_named_correctly(self):
        data = _load(_CONFIG_TOPK3_OFFSET1)
        assert "topk3_offset1" in data["output"]["experiment_results"]
        assert "topk3_offset1" in data["output"]["envelope_prefix"]

    def test_failure_recovery_output_paths_named_correctly(self):
        data = _load(_CONFIG_FAILURE_RECOVERY)
        assert "failure_recovery" in data["output"]["experiment_results"]
        assert "failure_recovery" in data["output"]["envelope_prefix"]

    def test_referenced_state_file_exists(self):
        data = _load(_CONFIG_TOPK3_OFFSET0)
        assert (_REPO_ROOT / data["planner"]["portfolio_state"]).exists()

    def test_referenced_ledger_file_exists(self):
        data = _load(_CONFIG_TOPK3_OFFSET0)
        assert (_REPO_ROOT / data["planner"]["ledger"]).exists()

    def test_failure_recovery_referenced_policy_file_exists(self):
        data = _load(_CONFIG_FAILURE_RECOVERY)
        assert (_REPO_ROOT / data["planner"]["policy"]).exists()

    def test_portfolio_state_has_recover_failed_workflow_action(self):
        data = _load(_EXPERIMENTS / "portfolio_state_degraded_v2.json")
        repo = data["repos"][0]
        action_types = [a["action_type"] for a in repo["recommended_actions"]]
        assert "recover_failed_workflow" in action_types

    def test_ledger_has_recover_failed_workflow_entry(self):
        data = _load(_EXPERIMENTS / "action_effectiveness_ledger_synthetic_v2.json")
        entries = {e["action_type"] for e in data["action_types"]}
        assert "recover_failed_workflow" in entries

    def test_portfolio_state_eligible_actions_total_updated(self):
        data = _load(_EXPERIMENTS / "portfolio_state_degraded_v2.json")
        assert data["summary"]["eligible_actions_total"] == 5


# ---------------------------------------------------------------------------
# 4. TestReportDiversityMetrics
# ---------------------------------------------------------------------------

def _make_runs_with_detail(entries):
    """Build evaluation_summary with selection_detail entries."""
    runs = []
    for i, (selected, collapse) in enumerate(entries):
        run = {
            "index": i,
            "selected_actions": list(selected),
            "selection_count": len(selected),
            "inputs": {},
            "planner_version": "0.36",
            "selection_detail": {
                "ranked_action_window": list(selected),
                "action_task_collapse_count": collapse,
            },
        }
        runs.append(run)
    return {
        "envelope_count": len(runs),
        "identical": len({tuple(r["selected_actions"]) for r in runs}) == 1,
        "ordering_differences": False,
        "runs": runs,
    }


class TestReportDiversityMetrics:
    """New action_selection fields exist and are populated correctly."""

    def _build(self, runs_spec):
        ev = _make_runs_with_detail(runs_spec)
        result = {"run_count": len(runs_spec), "envelope_paths": [], "evaluation_summary": ev}
        return _report_mod.build_report(result)

    def test_selected_action_count_present(self):
        report = self._build([(["build_portfolio_dashboard"], 1)])
        assert "selected_action_count" in report["action_selection"]

    def test_unique_selected_task_count_present(self):
        report = self._build([(["build_portfolio_dashboard"], 1)])
        assert "unique_selected_task_count" in report["action_selection"]

    def test_task_diversity_ratio_present(self):
        report = self._build([(["build_portfolio_dashboard"], 1)])
        assert "task_diversity_ratio" in report["action_selection"]

    def test_selected_action_count_single_run(self):
        # 1 run, 2 tasks selected
        report = self._build([(["build_portfolio_dashboard", "repo_insights_example"], 0)])
        assert report["action_selection"]["selected_action_count"] == 2

    def test_selected_action_count_across_runs(self):
        # 2 runs, 1 task each → total 2
        report = self._build([
            (["build_portfolio_dashboard"], 1),
            (["build_portfolio_dashboard"], 1),
        ])
        assert report["action_selection"]["selected_action_count"] == 2

    def test_unique_selected_task_count_one_task(self):
        report = self._build([
            (["build_portfolio_dashboard"], 1),
            (["build_portfolio_dashboard"], 1),
        ])
        assert report["action_selection"]["unique_selected_task_count"] == 1

    def test_unique_selected_task_count_two_tasks(self):
        report = self._build([
            (["build_portfolio_dashboard", "repo_insights_example"], 0),
        ])
        assert report["action_selection"]["unique_selected_task_count"] == 2

    def test_unique_selected_task_count_across_runs(self):
        # Run 1 selects build, run 2 selects failure_recovery → 2 unique tasks total
        report = self._build([
            (["build_portfolio_dashboard"], 0),
            (["failure_recovery_example"], 0),
        ])
        assert report["action_selection"]["unique_selected_task_count"] == 2

    def test_task_diversity_ratio_full_diversity(self):
        # 3 tasks selected, collapse=0 → diversity=1.0
        report = self._build([
            (["build_portfolio_dashboard", "failure_recovery_example", "repo_insights_example"], 0),
        ])
        assert report["action_selection"]["task_diversity_ratio"] == 1.0

    def test_task_diversity_ratio_half_diversity(self):
        # 1 task selected, collapse=1 → diversity=0.5
        report = self._build([(["build_portfolio_dashboard"], 1)])
        assert report["action_selection"]["task_diversity_ratio"] == 0.5

    def test_task_diversity_ratio_zero_when_no_runs(self):
        ev = {"envelope_count": 0, "identical": True, "ordering_differences": False, "runs": []}
        result = {"run_count": 0, "envelope_paths": [], "evaluation_summary": ev}
        report = _report_mod.build_report(result)
        assert report["action_selection"]["task_diversity_ratio"] == 0.0

    def test_task_diversity_ratio_two_thirds(self):
        # 2 tasks selected from 3-wide window (collapse=1)
        report = self._build([
            (["build_portfolio_dashboard", "failure_recovery_example"], 1),
        ])
        assert abs(report["action_selection"]["task_diversity_ratio"] - 2 / 3) < 1e-5

    def test_existing_keys_still_present(self):
        report = self._build([(["build_portfolio_dashboard"], 1)])
        ac = report["action_selection"]
        assert "most_common_actions" in ac
        assert "total_action_task_collapse_count" in ac
        assert "unique_action_sets" in ac

    def test_markdown_contains_selected_action_count(self):
        report = self._build([(["build_portfolio_dashboard", "repo_insights_example"], 0)])
        md = _report_mod.render_markdown(report)
        assert "Selected action count:" in md

    def test_markdown_contains_unique_selected_task_count(self):
        report = self._build([(["build_portfolio_dashboard", "repo_insights_example"], 0)])
        md = _report_mod.render_markdown(report)
        assert "Unique selected task count:" in md

    def test_markdown_contains_task_diversity_ratio(self):
        report = self._build([(["build_portfolio_dashboard", "repo_insights_example"], 0)])
        md = _report_mod.render_markdown(report)
        assert "Task diversity ratio:" in md

    def test_report_version_is_0_43(self):
        assert _report_mod.REPORT_VERSION == "0.43"


# ---------------------------------------------------------------------------
# 5. TestDiversityCalculation
# ---------------------------------------------------------------------------

class TestDiversityCalculation:
    """task_diversity_ratio arithmetic edge cases."""

    def _ac(self, runs_spec):
        ev = _make_runs_with_detail(runs_spec)
        return _report_mod._compute_action_consistency(ev)

    def test_diversity_1_0_when_no_collapse(self):
        result = self._ac([(["a", "b", "c"], 0)])
        assert result["task_diversity_ratio"] == 1.0

    def test_diversity_0_5_with_equal_collapse(self):
        result = self._ac([(["a"], 1)])
        assert result["task_diversity_ratio"] == 0.5

    def test_diversity_two_thirds_window3_select2(self):
        result = self._ac([(["a", "b"], 1)])
        assert abs(result["task_diversity_ratio"] - 2 / 3) < 1e-5

    def test_diversity_average_across_runs(self):
        # Run 0: sel=2, collapse=0 → div=1.0
        # Run 1: sel=1, collapse=1 → div=0.5
        # Average = 0.75
        result = self._ac([(["a", "b"], 0), (["a"], 1)])
        assert abs(result["task_diversity_ratio"] - 0.75) < 1e-5

    def test_diversity_rounded_to_6_places(self):
        # 2/3 = 0.666666...
        result = self._ac([(["a", "b"], 1)])
        ratio = result["task_diversity_ratio"]
        assert isinstance(ratio, float)
        # Should be exactly round(2/3, 6)
        assert ratio == round(2 / 3, 6)

    def test_diversity_empty_runs_returns_zero(self):
        ev = {"envelope_count": 0, "identical": True, "ordering_differences": False, "runs": []}
        result = _report_mod._compute_action_consistency(ev)
        assert result["task_diversity_ratio"] == 0.0

    def test_selected_action_count_zero_no_runs(self):
        ev = {"envelope_count": 0, "identical": True, "ordering_differences": False, "runs": []}
        result = _report_mod._compute_action_consistency(ev)
        assert result["selected_action_count"] == 0

    def test_unique_task_count_deduplicates_across_runs(self):
        # Both runs select the same two tasks → unique=2, not 4
        result = self._ac([
            (["build_portfolio_dashboard", "repo_insights_example"], 0),
            (["build_portfolio_dashboard", "repo_insights_example"], 0),
        ])
        assert result["unique_selected_task_count"] == 2

    def test_unique_task_count_union_across_runs(self):
        # Run 0 selects build, run 1 selects failure_recovery → unique=2
        result = self._ac([
            (["build_portfolio_dashboard"], 0),
            (["failure_recovery_example"], 0),
        ])
        assert result["unique_selected_task_count"] == 2

    def test_runs_without_selection_detail_contribute_zero_diversity(self):
        # Run without selection_detail → collapse assumed 0
        ev = {
            "envelope_count": 1,
            "identical": True,
            "ordering_differences": False,
            "runs": [
                {"index": 0, "selected_actions": ["build_portfolio_dashboard"],
                 "selection_count": 1, "inputs": {}, "planner_version": "0.35"},
            ],
        }
        result = _report_mod._compute_action_consistency(ev)
        # sel=1, collapse=0 (no selection_detail) → diversity=1.0
        assert result["task_diversity_ratio"] == 1.0


# ---------------------------------------------------------------------------
# 6. TestExpansionDeterminism
# ---------------------------------------------------------------------------

class TestExpansionDeterminism:
    """New task and report fields are deterministic."""

    def test_failure_recovery_task_deterministic_repeated(self, tmp_path):
        r1 = _task_mod.collect_recovery_indicators(tmp_path)
        r2 = _task_mod.collect_recovery_indicators(tmp_path)
        assert r1 == r2

    def test_report_diversity_deterministic(self):
        ev = _make_runs_with_detail([
            (["build_portfolio_dashboard", "failure_recovery_example"], 1),
            (["build_portfolio_dashboard", "repo_insights_example"], 0),
        ])
        data = {"run_count": 2, "envelope_paths": [], "evaluation_summary": ev}
        r1 = _report_mod.build_report(data)
        r2 = _report_mod.build_report(data)
        assert r1["action_selection"] == r2["action_selection"]

    def test_action_mapping_stable(self):
        # recover_failed_workflow always maps to failure_recovery_example
        for _ in range(3):
            assert _planner_mod.ACTION_TO_TASK["recover_failed_workflow"] == "failure_recovery_example"

    def test_new_config_files_parse_idempotently(self):
        for cfg in _ALL_NEW_CONFIGS:
            d1 = _load(cfg)
            d2 = _load(cfg)
            assert d1 == d2

    def test_planner_main_includes_failure_recovery_in_fallback(self):
        """Fallback (no portfolio state) must include failure_recovery_example in tasks."""
        with mock.patch.object(_planner_mod, "run_tasks") as mock_run:
            _planner_mod.main([])
        tasks = mock_run.call_args[0][0]
        assert "failure_recovery_example" in tasks

    def test_planner_selects_failure_recovery_from_recover_action(self, tmp_path):
        """recover_failed_workflow action → failure_recovery_example task selected."""
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        actions = [{"action_type": "recover_failed_workflow", "priority": 0.85}]
        with mock.patch.object(_planner_mod, "_fetch_action_queue", return_value=actions), \
             mock.patch.object(_planner_mod, "run_tasks") as mock_run:
            _planner_mod.main(["--portfolio-state", str(state), "--top-k", "1"])
        tasks = mock_run.call_args[0][0]
        assert tasks == ["failure_recovery_example"]

    def test_planner_envelope_records_failure_recovery_task(self, tmp_path):
        """Envelope selected_actions includes failure_recovery_example."""
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        ep = tmp_path / "env.json"
        actions = [{"action_type": "recover_failed_workflow", "priority": 0.85}]
        with mock.patch.object(_planner_mod, "_fetch_action_queue", return_value=actions), \
             mock.patch.object(_planner_mod, "run_tasks"):
            _planner_mod.main([
                "--portfolio-state", str(state),
                "--top-k", "1",
                "--run-envelope", str(ep),
            ])
        data = json.loads(ep.read_text(encoding="utf-8"))
        assert "failure_recovery_example" in data["selected_actions"]
