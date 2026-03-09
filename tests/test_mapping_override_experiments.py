# SPDX-License-Identifier: MIT
"""Tests for mapping_override experiment capability.

Covers:
- resolve_action_to_task_mapping: no-override path and override path
- _map_actions_to_tasks: uses action_to_task parameter correctly
- _selected_mapped_actions: uses action_to_task parameter correctly
- collapse counts computed from the active mapping
- active_action_to_task_mapping surfaced in run envelopes
- _build_planner_argv includes --mapping-override-json when set
- all three mapping-regime configs load and have required fields
- high collision regime has lower-or-equal diversity than balanced
- balanced has lower-or-equal diversity than low collision
- run_experiment with mapping_override arg produces consistent results
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Load modules under test via importlib so private helpers are accessible.
def _load_module(name, script_path):
    spec = importlib.util.spec_from_file_location(name, script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_planner_mod = _load_module(
    "claude_dynamic_planner_loop",
    _REPO_ROOT / "scripts" / "claude_dynamic_planner_loop.py",
)
_exp_mod = _load_module(
    "run_planner_experiment",
    _REPO_ROOT / "scripts" / "run_planner_experiment.py",
)
_report_mod = _load_module(
    "generate_experiment_report",
    _REPO_ROOT / "scripts" / "generate_experiment_report.py",
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_DEFAULT_MAPPING = {
    "refresh_repo_health": "build_portfolio_dashboard",
    "regenerate_missing_artifact": "build_portfolio_dashboard",
    "rerun_failed_task": "build_portfolio_dashboard",
    "run_determinism_regression_suite": "build_portfolio_dashboard",
    "analyze_repo_insights": "repo_insights_example",
    "recover_failed_workflow": "failure_recovery_example",
}

_HIGH_COLLISION_MAPPING = {
    "regenerate_missing_artifact": "build_portfolio_dashboard",
    "refresh_repo_health": "build_portfolio_dashboard",
    "rerun_failed_task": "build_portfolio_dashboard",
    "analyze_repo_insights": "repo_insights_example",
    "recover_failed_workflow": "failure_recovery_example",
}

_BALANCED_MAPPING = {
    "regenerate_missing_artifact": "build_portfolio_dashboard",
    "refresh_repo_health": "repo_insights_example",
    "rerun_failed_task": "failure_recovery_example",
    "analyze_repo_insights": "repo_insights_example",
    "recover_failed_workflow": "failure_recovery_example",
}

_LOW_COLLISION_MAPPING = {
    "regenerate_missing_artifact": "build_portfolio_dashboard",
    "refresh_repo_health": "repo_insights_example",
    "rerun_failed_task": "failure_recovery_example",
    "analyze_repo_insights": "planner_determinism_example",
    "recover_failed_workflow": "artifact_audit_example",
}

# The window produced by top_k=3 on portfolio_state_degraded_v2 with default scoring.
_DEGRADED_V2_WINDOW = [
    {"action_type": "regenerate_missing_artifact", "priority": 0.95},
    {"action_type": "recover_failed_workflow", "priority": 0.85},
    {"action_type": "refresh_repo_health", "priority": 0.80},
]


def _make_envelope(selected_actions, ranked_window, collapse_count, mapping=None):
    """Return a minimal run envelope dict for report testing."""
    return {
        "planner_version": "0.36",
        "selected_actions": list(selected_actions),
        "selection_count": len(selected_actions),
        "inputs": {"top_k": 3, "exploration_offset": 0},
        "selection_detail": {
            "action_task_collapse_count": collapse_count,
            "active_action_to_task_mapping": dict(mapping) if mapping else {},
            "ranked_action_window": list(ranked_window),
        },
        "artifacts": {"explain_artifact": None},
        "execution": {"executed": True, "status": "ok"},
    }


def _make_fake_planner_with_mapping(mapping, window):
    """Return a fake planner that writes a deterministic envelope using the given mapping."""

    def fake_main(argv):
        # Derive selected tasks from the mapping over the window.
        seen = set()
        tasks = []
        for action in window:
            task = mapping.get(action["action_type"])
            if task and task not in seen:
                seen.add(task)
                tasks.append(task)
        collapse = len(window) - len(tasks)
        envelope = _make_envelope(tasks, [a["action_type"] for a in window], collapse, mapping)
        for i, arg in enumerate(argv):
            if arg == "--run-envelope" and i + 1 < len(argv):
                ep = Path(argv[i + 1])
                ep.parent.mkdir(parents=True, exist_ok=True)
                ep.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                break

    return fake_main


class _FakeArgs:
    runs = 1
    portfolio_state = None
    ledger = None
    policy = None
    top_k = 3
    exploration_offset = 0
    max_actions = None
    explain = False
    mapping_override = None
    output = "experiment_results.json"


def _make_args(**kwargs):
    args = _FakeArgs()
    for k, v in kwargs.items():
        setattr(args, k, v)
    return args


# ---------------------------------------------------------------------------
# 1. resolve_action_to_task_mapping
# ---------------------------------------------------------------------------

class TestResolveActionToTaskMapping:
    def test_none_override_returns_default(self):
        result = _planner_mod.resolve_action_to_task_mapping(_DEFAULT_MAPPING, None)
        assert result is _DEFAULT_MAPPING

    def test_empty_override_returns_default(self):
        result = _planner_mod.resolve_action_to_task_mapping(_DEFAULT_MAPPING, {})
        assert result is _DEFAULT_MAPPING

    def test_override_returns_override_not_default(self):
        override = {"analyze_repo_insights": "repo_insights_example"}
        result = _planner_mod.resolve_action_to_task_mapping(_DEFAULT_MAPPING, override)
        assert result == override
        assert result is not _DEFAULT_MAPPING

    def test_override_is_deterministic(self):
        override = {"a": "task_a", "b": "task_b"}
        r1 = _planner_mod.resolve_action_to_task_mapping(_DEFAULT_MAPPING, override)
        r2 = _planner_mod.resolve_action_to_task_mapping(_DEFAULT_MAPPING, override)
        assert r1 == r2

    def test_override_does_not_mutate_default(self):
        original_default = dict(_DEFAULT_MAPPING)
        override = {"x": "task_x"}
        _planner_mod.resolve_action_to_task_mapping(_DEFAULT_MAPPING, override)
        assert _DEFAULT_MAPPING == original_default


# ---------------------------------------------------------------------------
# 2. _map_actions_to_tasks with custom action_to_task
# ---------------------------------------------------------------------------

class TestMapActionsToTasksOverride:
    def _action(self, action_type):
        return {"action_type": action_type, "priority": 0.9}

    def test_no_override_uses_default(self):
        actions = [self._action("analyze_repo_insights")]
        result = _planner_mod._map_actions_to_tasks(actions, top_k=1)
        assert result == ["repo_insights_example"]

    def test_override_uses_supplied_mapping(self):
        actions = [self._action("refresh_repo_health")]
        override = {"refresh_repo_health": "repo_insights_example"}
        result = _planner_mod._map_actions_to_tasks(actions, top_k=1, action_to_task=override)
        assert result == ["repo_insights_example"]

    def test_high_collision_collapses_duplicates(self):
        # regenerate -> build, recover -> failure_recovery, refresh -> build (collapse)
        actions = _DEGRADED_V2_WINDOW
        result = _planner_mod._map_actions_to_tasks(actions, top_k=3, action_to_task=_HIGH_COLLISION_MAPPING)
        assert result == ["build_portfolio_dashboard", "failure_recovery_example"]

    def test_balanced_no_collision(self):
        # regenerate -> build, recover -> failure_recovery, refresh -> repo_insights
        actions = _DEGRADED_V2_WINDOW
        result = _planner_mod._map_actions_to_tasks(actions, top_k=3, action_to_task=_BALANCED_MAPPING)
        assert len(result) == 3
        assert len(set(result)) == 3

    def test_low_collision_no_collision(self):
        actions = _DEGRADED_V2_WINDOW
        result = _planner_mod._map_actions_to_tasks(actions, top_k=3, action_to_task=_LOW_COLLISION_MAPPING)
        assert len(result) == 3
        assert len(set(result)) == 3

    def test_default_behavior_unchanged_without_override(self):
        """Calling without override must produce the same result as before."""
        actions = _DEGRADED_V2_WINDOW
        result_explicit = _planner_mod._map_actions_to_tasks(
            actions, top_k=3, action_to_task=_planner_mod.ACTION_TO_TASK)
        result_default = _planner_mod._map_actions_to_tasks(actions, top_k=3)
        assert result_explicit == result_default


# ---------------------------------------------------------------------------
# 3. _selected_mapped_actions with custom action_to_task
# ---------------------------------------------------------------------------

class TestSelectedMappedActionsOverride:
    def test_override_filters_correctly(self):
        override = {"analyze_repo_insights": "planner_determinism_example"}
        actions = [{"action_type": "analyze_repo_insights", "priority": 0.8}]
        result = _planner_mod._selected_mapped_actions(actions, top_k=1, action_to_task=override)
        assert len(result) == 1
        assert result[0]["action_type"] == "analyze_repo_insights"

    def test_collapse_skips_second_same_task(self):
        # Both map to build_portfolio_dashboard under high collision
        actions = [
            {"action_type": "regenerate_missing_artifact", "priority": 0.95},
            {"action_type": "refresh_repo_health", "priority": 0.80},
        ]
        result = _planner_mod._selected_mapped_actions(
            actions, top_k=2, action_to_task=_HIGH_COLLISION_MAPPING)
        assert len(result) == 1
        assert result[0]["action_type"] == "regenerate_missing_artifact"

    def test_no_collapse_when_distinct_tasks(self):
        actions = _DEGRADED_V2_WINDOW
        result = _planner_mod._selected_mapped_actions(
            actions, top_k=3, action_to_task=_LOW_COLLISION_MAPPING)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# 4. Collapse counts derived from active mapping
# ---------------------------------------------------------------------------

class TestCollapseCountsFromMapping:
    def test_high_collision_produces_collapse(self):
        tasks = _planner_mod._map_actions_to_tasks(
            _DEGRADED_V2_WINDOW, top_k=3, action_to_task=_HIGH_COLLISION_MAPPING)
        collapse = len(_DEGRADED_V2_WINDOW) - len(tasks)
        assert collapse == 1

    def test_balanced_produces_no_collapse(self):
        tasks = _planner_mod._map_actions_to_tasks(
            _DEGRADED_V2_WINDOW, top_k=3, action_to_task=_BALANCED_MAPPING)
        collapse = len(_DEGRADED_V2_WINDOW) - len(tasks)
        assert collapse == 0

    def test_low_collision_produces_no_collapse(self):
        tasks = _planner_mod._map_actions_to_tasks(
            _DEGRADED_V2_WINDOW, top_k=3, action_to_task=_LOW_COLLISION_MAPPING)
        collapse = len(_DEGRADED_V2_WINDOW) - len(tasks)
        assert collapse == 0

    def test_high_collapse_gte_balanced_collapse(self):
        high_tasks = _planner_mod._map_actions_to_tasks(
            _DEGRADED_V2_WINDOW, top_k=3, action_to_task=_HIGH_COLLISION_MAPPING)
        bal_tasks = _planner_mod._map_actions_to_tasks(
            _DEGRADED_V2_WINDOW, top_k=3, action_to_task=_BALANCED_MAPPING)
        high_collapse = len(_DEGRADED_V2_WINDOW) - len(high_tasks)
        bal_collapse = len(_DEGRADED_V2_WINDOW) - len(bal_tasks)
        assert high_collapse >= bal_collapse


# ---------------------------------------------------------------------------
# 5. active_action_to_task_mapping in run envelopes
# ---------------------------------------------------------------------------

class TestActiveMappingInEnvelope:
    def test_envelope_has_active_mapping_key(self, tmp_path):
        out = tmp_path / "env.json"
        _planner_mod.write_run_envelope(
            str(out), _FakeArgs(), ["build_portfolio_dashboard"],
            active_action_to_task_mapping=_HIGH_COLLISION_MAPPING,
        )
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "active_action_to_task_mapping" in data["selection_detail"]

    def test_envelope_active_mapping_matches_supplied(self, tmp_path):
        out = tmp_path / "env.json"
        _planner_mod.write_run_envelope(
            str(out), _FakeArgs(), ["build_portfolio_dashboard"],
            active_action_to_task_mapping=_BALANCED_MAPPING,
        )
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["selection_detail"]["active_action_to_task_mapping"] == _BALANCED_MAPPING

    def test_envelope_active_mapping_empty_when_not_supplied(self, tmp_path):
        out = tmp_path / "env.json"
        _planner_mod.write_run_envelope(str(out), _FakeArgs(), [])
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["selection_detail"]["active_action_to_task_mapping"] == {}

    def test_envelope_active_mapping_deterministic(self, tmp_path):
        out_a = tmp_path / "a.json"
        out_b = tmp_path / "b.json"
        for out in [out_a, out_b]:
            _planner_mod.write_run_envelope(
                str(out), _FakeArgs(), ["build_portfolio_dashboard"],
                active_action_to_task_mapping=_HIGH_COLLISION_MAPPING,
            )
        assert out_a.read_text(encoding="utf-8") == out_b.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 6. _build_planner_argv includes --mapping-override-json when set
# ---------------------------------------------------------------------------

class TestBuildPlannerArgvMappingOverride:
    def test_mapping_override_json_in_argv_when_set(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(output=str(output), mapping_override=_HIGH_COLLISION_MAPPING)
        envelope_path = tmp_path / "env.json"
        argv = _exp_mod._build_planner_argv(args, envelope_path)
        assert "--mapping-override-json" in argv

    def test_mapping_override_json_value_is_valid_json(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(output=str(output), mapping_override=_BALANCED_MAPPING)
        envelope_path = tmp_path / "env.json"
        argv = _exp_mod._build_planner_argv(args, envelope_path)
        idx = argv.index("--mapping-override-json")
        parsed = json.loads(argv[idx + 1])
        assert parsed == _BALANCED_MAPPING

    def test_mapping_override_absent_when_none(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(output=str(output), mapping_override=None)
        envelope_path = tmp_path / "env.json"
        argv = _exp_mod._build_planner_argv(args, envelope_path)
        assert "--mapping-override-json" not in argv

    def test_mapping_override_absent_when_not_set(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(output=str(output))
        envelope_path = tmp_path / "env.json"
        argv = _exp_mod._build_planner_argv(args, envelope_path)
        assert "--mapping-override-json" not in argv


# ---------------------------------------------------------------------------
# 7. Experiment configs load and have required fields
# ---------------------------------------------------------------------------

class TestRegimeConfigFiles:
    def _load(self, name):
        path = _REPO_ROOT / "experiments" / name
        return json.loads(path.read_text(encoding="utf-8"))

    def test_high_collision_config_exists(self):
        self._load("mapping_regime_high_collision_config.json")

    def test_balanced_config_exists(self):
        self._load("mapping_regime_balanced_config.json")

    def test_low_collision_config_exists(self):
        self._load("mapping_regime_low_collision_config.json")

    def test_all_configs_have_mapping_override(self):
        for name in (
            "mapping_regime_high_collision_config.json",
            "mapping_regime_balanced_config.json",
            "mapping_regime_low_collision_config.json",
        ):
            config = self._load(name)
            assert "mapping_override" in config, f"missing mapping_override in {name}"
            assert isinstance(config["mapping_override"], dict)
            assert len(config["mapping_override"]) > 0

    def test_high_collision_has_multiple_actions_to_same_task(self):
        config = self._load("mapping_regime_high_collision_config.json")
        mapping = config["mapping_override"]
        task_counts: dict = {}
        for task in mapping.values():
            task_counts[task] = task_counts.get(task, 0) + 1
        assert max(task_counts.values()) >= 2, "high_collision should map multiple actions to same task"

    def test_low_collision_has_all_distinct_tasks(self):
        config = self._load("mapping_regime_low_collision_config.json")
        mapping = config["mapping_override"]
        assert len(set(mapping.values())) == len(mapping), \
            "low_collision should map each action to a distinct task"

    def test_all_configs_use_same_portfolio_state(self):
        expected_state = "experiments/portfolio_state_degraded_v2.json"
        for name in (
            "mapping_regime_high_collision_config.json",
            "mapping_regime_balanced_config.json",
            "mapping_regime_low_collision_config.json",
        ):
            config = self._load(name)
            assert config["planner"]["portfolio_state"] == expected_state

    def test_all_configs_use_topk3(self):
        for name in (
            "mapping_regime_high_collision_config.json",
            "mapping_regime_balanced_config.json",
            "mapping_regime_low_collision_config.json",
        ):
            config = self._load(name)
            assert config["planner"]["top_k"] == 3


# ---------------------------------------------------------------------------
# 8. Diversity ordering across regimes (unit-level, no subprocess)
# ---------------------------------------------------------------------------

class TestDiversityOrdering:
    """Verify that high collision ≤ balanced ≤ low collision in terms of task diversity."""

    def _diversity(self, mapping):
        """Compute task_diversity_ratio for one run over the fixed window."""
        tasks = _planner_mod._map_actions_to_tasks(
            _DEGRADED_V2_WINDOW, top_k=3, action_to_task=mapping)
        window_len = len(_DEGRADED_V2_WINDOW)
        return len(tasks) / window_len if window_len > 0 else 0.0

    def test_high_lte_balanced(self):
        assert self._diversity(_HIGH_COLLISION_MAPPING) <= self._diversity(_BALANCED_MAPPING)

    def test_balanced_lte_low(self):
        assert self._diversity(_BALANCED_MAPPING) <= self._diversity(_LOW_COLLISION_MAPPING)

    def test_high_lte_low(self):
        assert self._diversity(_HIGH_COLLISION_MAPPING) <= self._diversity(_LOW_COLLISION_MAPPING)

    def test_high_is_strictly_below_balanced_for_this_portfolio(self):
        """High collision must show measurable degradation for degraded_v2 window."""
        assert self._diversity(_HIGH_COLLISION_MAPPING) < self._diversity(_BALANCED_MAPPING)


# ---------------------------------------------------------------------------
# 9. run_experiment with mapping_override produces consistent envelopes
# ---------------------------------------------------------------------------

class TestRunExperimentWithMappingOverride:
    def test_high_collision_experiment_deterministic(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(
            runs=3,
            output=str(output),
            mapping_override=_HIGH_COLLISION_MAPPING,
        )
        result = _exp_mod.run_experiment(
            args, planner_main=_make_fake_planner_with_mapping(_HIGH_COLLISION_MAPPING, _DEGRADED_V2_WINDOW))
        assert result["evaluation_summary"]["identical"] is True

    def test_low_collision_experiment_deterministic(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(
            runs=3,
            output=str(output),
            mapping_override=_LOW_COLLISION_MAPPING,
        )
        result = _exp_mod.run_experiment(
            args, planner_main=_make_fake_planner_with_mapping(_LOW_COLLISION_MAPPING, _DEGRADED_V2_WINDOW))
        assert result["evaluation_summary"]["identical"] is True

    def test_high_collision_more_collapse_than_balanced(self, tmp_path):
        def _run_and_get_collapse(mapping, out_dir):
            output = out_dir / "results.json"
            args = _make_args(runs=1, output=str(output), mapping_override=mapping)
            result = _exp_mod.run_experiment(
                args, planner_main=_make_fake_planner_with_mapping(mapping, _DEGRADED_V2_WINDOW))
            runs = result["evaluation_summary"]["runs"]
            return sum(r.get("selection_detail", {}).get("action_task_collapse_count", 0) for r in runs)

        high_collapse = _run_and_get_collapse(_HIGH_COLLISION_MAPPING, tmp_path / "high")
        bal_collapse = _run_and_get_collapse(_BALANCED_MAPPING, tmp_path / "bal")
        assert high_collapse >= bal_collapse

    def test_no_override_preserves_existing_behavior(self, tmp_path):
        """Without mapping_override, run_experiment behaves exactly as before."""
        output = tmp_path / "results.json"
        args = _make_args(runs=2, output=str(output))
        assert args.mapping_override is None
        argv_received = []

        def capture_argv(argv):
            argv_received.append(list(argv))
            _make_fake_planner_with_mapping(_planner_mod.ACTION_TO_TASK, _DEGRADED_V2_WINDOW)(argv)

        _exp_mod.run_experiment(args, planner_main=capture_argv)
        for argv in argv_received:
            assert "--mapping-override-json" not in argv

    def test_mapping_override_passed_through_argv(self, tmp_path):
        output = tmp_path / "results.json"
        args = _make_args(runs=1, output=str(output), mapping_override=_BALANCED_MAPPING)
        argv_received = []

        def capture_argv(argv):
            argv_received.append(list(argv))
            _make_fake_planner_with_mapping(_BALANCED_MAPPING, _DEGRADED_V2_WINDOW)(argv)

        _exp_mod.run_experiment(args, planner_main=capture_argv)
        assert "--mapping-override-json" in argv_received[0]
        idx = argv_received[0].index("--mapping-override-json")
        parsed = json.loads(argv_received[0][idx + 1])
        assert parsed == _BALANCED_MAPPING


# ---------------------------------------------------------------------------
# 10. collision_ratio in report
# ---------------------------------------------------------------------------

class TestCollisionRatioInReport:
    def _build_eval_summary(self, runs_data):
        """Build an evaluation_summary from a list of (selected_actions, window, collapse) tuples."""
        runs = []
        for i, (actions, window, collapse) in enumerate(runs_data):
            runs.append({
                "index": i,
                "selected_actions": list(actions),
                "selection_count": len(actions),
                "inputs": {},
                "planner_version": "0.36",
                "selection_detail": {
                    "action_task_collapse_count": collapse,
                    "ranked_action_window": list(window),
                    "active_action_to_task_mapping": {},
                },
            })
        return {"envelope_count": len(runs), "identical": True, "ordering_differences": False, "runs": runs}

    def test_collision_ratio_present_in_report(self):
        eval_summary = self._build_eval_summary([
            (["build_portfolio_dashboard"], ["regenerate_missing_artifact"], 0),
        ])
        consistency = _report_mod._compute_action_consistency(eval_summary)
        assert "collision_ratio" in consistency

    def test_collision_ratio_zero_when_no_collapse(self):
        eval_summary = self._build_eval_summary([
            (["build_portfolio_dashboard", "repo_insights_example"],
             ["regenerate_missing_artifact", "refresh_repo_health"], 0),
        ])
        consistency = _report_mod._compute_action_consistency(eval_summary)
        assert consistency["collision_ratio"] == 0.0

    def test_collision_ratio_correct_when_one_collapse(self):
        # window=3, collapse=1 → ratio = 1/3
        eval_summary = self._build_eval_summary([
            (["build_portfolio_dashboard", "failure_recovery_example"],
             ["regenerate_missing_artifact", "recover_failed_workflow", "refresh_repo_health"], 1),
        ])
        consistency = _report_mod._compute_action_consistency(eval_summary)
        assert abs(consistency["collision_ratio"] - round(1 / 3, 6)) < 1e-9

    def test_collision_ratio_in_markdown(self):
        eval_summary = self._build_eval_summary([
            (["build_portfolio_dashboard", "failure_recovery_example"],
             ["regenerate_missing_artifact", "recover_failed_workflow", "refresh_repo_health"], 1),
        ])
        report = _report_mod.build_report({"run_count": 1, "evaluation_summary": eval_summary})
        md = _report_mod.render_markdown(report)
        assert "Collision ratio:" in md


# ---------------------------------------------------------------------------
# 11. task_entropy and action_entropy in report (v0.43)
# ---------------------------------------------------------------------------

class TestEntropyInReport:
    def _build_eval_summary(self, runs_data):
        """Build an evaluation_summary from (selected_actions, window, collapse) tuples."""
        runs = []
        for i, (actions, window, collapse) in enumerate(runs_data):
            runs.append({
                "index": i,
                "selected_actions": list(actions),
                "selection_count": len(actions),
                "inputs": {},
                "planner_version": "0.36",
                "selection_detail": {
                    "action_task_collapse_count": collapse,
                    "ranked_action_window": list(window),
                    "active_action_to_task_mapping": {},
                },
            })
        return {"envelope_count": len(runs), "identical": True, "ordering_differences": False, "runs": runs}

    # --- _entropy helper ---

    def test_entropy_zero_for_single_element(self):
        assert _report_mod._entropy({"a": 5}) == 0.0

    def test_entropy_one_for_uniform_binary(self):
        assert abs(_report_mod._entropy({"a": 1, "b": 1}) - 1.0) < 1e-9

    def test_entropy_log2_k_for_k_uniform_elements(self):
        import math
        k = 4
        counts = {str(i): 1 for i in range(k)}
        assert abs(_report_mod._entropy(counts) - math.log2(k)) < 1e-9

    def test_entropy_zero_for_empty(self):
        assert _report_mod._entropy({}) == 0.0

    def test_entropy_zero_for_all_zero_counts(self):
        assert _report_mod._entropy({"a": 0, "b": 0}) == 0.0

    def test_entropy_deterministic(self):
        counts = {"z": 3, "a": 2, "m": 5}
        r1 = _report_mod._entropy(counts)
        r2 = _report_mod._entropy(counts)
        assert r1 == r2

    # --- task_entropy in consistency output ---

    def test_task_entropy_present_in_consistency(self):
        ev = self._build_eval_summary([
            (["build_portfolio_dashboard"], ["regenerate_missing_artifact"], 0),
        ])
        result = _report_mod._compute_action_consistency(ev)
        assert "task_entropy" in result

    def test_action_entropy_present_in_consistency(self):
        ev = self._build_eval_summary([
            (["build_portfolio_dashboard"], ["regenerate_missing_artifact"], 0),
        ])
        result = _report_mod._compute_action_consistency(ev)
        assert "action_entropy" in result

    def test_task_entropy_zero_for_single_task(self):
        ev = self._build_eval_summary([
            (["build_portfolio_dashboard"], ["regenerate_missing_artifact"], 0),
        ])
        result = _report_mod._compute_action_consistency(ev)
        assert result["task_entropy"] == 0.0

    def test_task_entropy_one_for_two_equal_tasks(self):
        ev = self._build_eval_summary([
            (["build_portfolio_dashboard", "repo_insights_example"],
             ["a", "b"], 0),
        ])
        result = _report_mod._compute_action_consistency(ev)
        assert abs(result["task_entropy"] - 1.0) < 1e-9

    def test_task_entropy_higher_with_more_unique_tasks(self):
        ev_two = self._build_eval_summary([
            (["build_portfolio_dashboard", "repo_insights_example"], ["a", "b"], 0),
        ])
        ev_three = self._build_eval_summary([
            (["build_portfolio_dashboard", "repo_insights_example", "failure_recovery_example"],
             ["a", "b", "c"], 0),
        ])
        ent_two = _report_mod._compute_action_consistency(ev_two)["task_entropy"]
        ent_three = _report_mod._compute_action_consistency(ev_three)["task_entropy"]
        assert ent_three > ent_two

    def test_action_entropy_zero_for_single_action_in_window(self):
        ev = self._build_eval_summary([
            (["build_portfolio_dashboard"], ["regenerate_missing_artifact"], 0),
        ])
        result = _report_mod._compute_action_consistency(ev)
        assert result["action_entropy"] == 0.0

    def test_action_entropy_one_for_two_equal_actions(self):
        ev = self._build_eval_summary([
            (["build_portfolio_dashboard", "failure_recovery_example"],
             ["regenerate_missing_artifact", "recover_failed_workflow"], 0),
        ])
        result = _report_mod._compute_action_consistency(ev)
        assert abs(result["action_entropy"] - 1.0) < 1e-9

    def test_task_entropy_in_markdown(self):
        ev = self._build_eval_summary([
            (["build_portfolio_dashboard", "repo_insights_example"], ["a", "b"], 0),
        ])
        report = _report_mod.build_report({"run_count": 1, "evaluation_summary": ev})
        md = _report_mod.render_markdown(report)
        assert "Task entropy:" in md

    def test_action_entropy_in_markdown(self):
        ev = self._build_eval_summary([
            (["build_portfolio_dashboard", "repo_insights_example"], ["a", "b"], 0),
        ])
        report = _report_mod.build_report({"run_count": 1, "evaluation_summary": ev})
        md = _report_mod.render_markdown(report)
        assert "Action entropy:" in md

    def test_entropy_across_multiple_runs_aggregated(self):
        # Two runs, each selecting the same task → single task, entropy=0
        ev = self._build_eval_summary([
            (["build_portfolio_dashboard"], ["regenerate_missing_artifact"], 0),
            (["build_portfolio_dashboard"], ["regenerate_missing_artifact"], 0),
        ])
        result = _report_mod._compute_action_consistency(ev)
        assert result["task_entropy"] == 0.0

    def test_entropy_high_collision_lower_than_low_collision(self):
        """High-collision regime produces fewer unique tasks → lower task entropy."""
        # High: only 1 unique task (both map to same)
        ev_high = self._build_eval_summary([
            (["build_portfolio_dashboard"], ["regenerate_missing_artifact", "refresh_repo_health"], 1),
        ])
        # Low: 2 unique tasks
        ev_low = self._build_eval_summary([
            (["build_portfolio_dashboard", "repo_insights_example"],
             ["regenerate_missing_artifact", "recover_failed_workflow"], 0),
        ])
        ent_high = _report_mod._compute_action_consistency(ev_high)["task_entropy"]
        ent_low  = _report_mod._compute_action_consistency(ev_low)["task_entropy"]
        assert ent_high < ent_low
