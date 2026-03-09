# SPDX-License-Identifier: MIT
"""Regression baseline for the three validated planner scenarios.

These tests anchor the selection_detail instrumentation results from the
manually validated runs on degraded_v2 + synthetic_ledger_v2:

  Scenario A: neutral policy, top_k=2, exploration_offset=0
    ranked_action_window: [regenerate_missing_artifact, refresh_repo_health]
    selected_tasks:        [build_portfolio_dashboard]
    action_task_collapse_count: 1

  Scenario B: neutral policy, top_k=2, exploration_offset=1
    ranked_action_window: [refresh_repo_health, analyze_repo_insights]
    selected_tasks:        [build_portfolio_dashboard, repo_insights_example]
    action_task_collapse_count: 0

  Scenario C: insights-first policy, top_k=2, exploration_offset=0
    ranked_action_window: [refresh_repo_health, analyze_repo_insights]
    selected_tasks:        [build_portfolio_dashboard, repo_insights_example]
    action_task_collapse_count: 0

Test classes:
  TestBaselineEnvelopeValues    - asserts instrumented envelopes match expected values
  TestBaselineConfigStructure   - asserts config files are valid and correctly structured
  TestBaselineConfigIntegration - asserts configs parse correctly via _apply_config
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_EXPERIMENTS = _REPO_ROOT / "experiments"

_ENVELOPE_A = _EXPERIMENTS / "instrumented_neutral_offset0.json"
_ENVELOPE_B = _EXPERIMENTS / "instrumented_neutral_offset1.json"
_ENVELOPE_C = _EXPERIMENTS / "instrumented_insights_offset0.json"

_CONFIG_A = _EXPERIMENTS / "baseline_neutral_offset0_config.json"
_CONFIG_B = _EXPERIMENTS / "baseline_neutral_offset1_config.json"
_CONFIG_C = _EXPERIMENTS / "baseline_insights_offset0_config.json"

_SCRIPT = _REPO_ROOT / "scripts" / "run_planner_experiment.py"
_spec = importlib.util.spec_from_file_location("run_planner_experiment", _SCRIPT)
_runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_runner)


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1. Baseline envelope value regression
# ---------------------------------------------------------------------------

class TestBaselineEnvelopeValues:
    """Assert instrumented envelopes match the manually validated baseline."""

    # --- Scenario A: neutral, offset=0 ---

    def test_A_ranked_action_window(self):
        env = _load(_ENVELOPE_A)
        assert env["selection_detail"]["ranked_action_window"] == [
            "regenerate_missing_artifact",
            "refresh_repo_health",
        ]

    def test_A_selected_actions(self):
        env = _load(_ENVELOPE_A)
        assert env["selected_actions"] == ["build_portfolio_dashboard"]

    def test_A_action_task_collapse_count(self):
        env = _load(_ENVELOPE_A)
        assert env["selection_detail"]["action_task_collapse_count"] == 1

    def test_A_inputs_top_k(self):
        env = _load(_ENVELOPE_A)
        assert env["inputs"]["top_k"] == 2

    def test_A_inputs_exploration_offset(self):
        env = _load(_ENVELOPE_A)
        assert env["inputs"]["exploration_offset"] == 0

    def test_A_inputs_policy_is_null(self):
        env = _load(_ENVELOPE_A)
        assert env["inputs"]["policy"] is None

    # --- Scenario B: neutral, offset=1 ---

    def test_B_ranked_action_window(self):
        env = _load(_ENVELOPE_B)
        assert env["selection_detail"]["ranked_action_window"] == [
            "refresh_repo_health",
            "analyze_repo_insights",
        ]

    def test_B_selected_actions(self):
        env = _load(_ENVELOPE_B)
        assert env["selected_actions"] == ["build_portfolio_dashboard", "repo_insights_example"]

    def test_B_action_task_collapse_count(self):
        env = _load(_ENVELOPE_B)
        assert env["selection_detail"]["action_task_collapse_count"] == 0

    def test_B_inputs_top_k(self):
        env = _load(_ENVELOPE_B)
        assert env["inputs"]["top_k"] == 2

    def test_B_inputs_exploration_offset(self):
        env = _load(_ENVELOPE_B)
        assert env["inputs"]["exploration_offset"] == 1

    def test_B_inputs_policy_is_null(self):
        env = _load(_ENVELOPE_B)
        assert env["inputs"]["policy"] is None

    # --- Scenario C: insights-first, offset=0 ---

    def test_C_ranked_action_window(self):
        env = _load(_ENVELOPE_C)
        assert env["selection_detail"]["ranked_action_window"] == [
            "refresh_repo_health",
            "analyze_repo_insights",
        ]

    def test_C_selected_actions(self):
        env = _load(_ENVELOPE_C)
        assert env["selected_actions"] == ["build_portfolio_dashboard", "repo_insights_example"]

    def test_C_action_task_collapse_count(self):
        env = _load(_ENVELOPE_C)
        assert env["selection_detail"]["action_task_collapse_count"] == 0

    def test_C_inputs_top_k(self):
        env = _load(_ENVELOPE_C)
        assert env["inputs"]["top_k"] == 2

    def test_C_inputs_exploration_offset(self):
        env = _load(_ENVELOPE_C)
        assert env["inputs"]["exploration_offset"] == 0

    def test_C_inputs_policy_is_not_null(self):
        env = _load(_ENVELOPE_C)
        assert env["inputs"]["policy"] is not None

    # --- Cross-scenario: B and C share the same ranked_action_window ---

    def test_B_and_C_share_ranked_action_window(self):
        b = _load(_ENVELOPE_B)
        c = _load(_ENVELOPE_C)
        assert (
            b["selection_detail"]["ranked_action_window"]
            == c["selection_detail"]["ranked_action_window"]
        )

    def test_B_and_C_share_selected_actions(self):
        b = _load(_ENVELOPE_B)
        c = _load(_ENVELOPE_C)
        assert b["selected_actions"] == c["selected_actions"]

    def test_A_differs_from_B_in_ranked_window(self):
        a = _load(_ENVELOPE_A)
        b = _load(_ENVELOPE_B)
        assert (
            a["selection_detail"]["ranked_action_window"]
            != b["selection_detail"]["ranked_action_window"]
        )


# ---------------------------------------------------------------------------
# 2. Baseline config structure validation
# ---------------------------------------------------------------------------

class TestBaselineConfigStructure:
    """Assert the three baseline config files are valid and correctly formed."""

    def test_A_config_is_valid_json(self):
        data = _load(_CONFIG_A)
        assert isinstance(data, dict)

    def test_B_config_is_valid_json(self):
        data = _load(_CONFIG_B)
        assert isinstance(data, dict)

    def test_C_config_is_valid_json(self):
        data = _load(_CONFIG_C)
        assert isinstance(data, dict)

    def test_A_config_top_k(self):
        assert _load(_CONFIG_A)["planner"]["top_k"] == 2

    def test_B_config_top_k(self):
        assert _load(_CONFIG_B)["planner"]["top_k"] == 2

    def test_C_config_top_k(self):
        assert _load(_CONFIG_C)["planner"]["top_k"] == 2

    def test_A_config_exploration_offset(self):
        assert _load(_CONFIG_A)["planner"]["exploration_offset"] == 0

    def test_B_config_exploration_offset(self):
        assert _load(_CONFIG_B)["planner"]["exploration_offset"] == 1

    def test_C_config_exploration_offset(self):
        assert _load(_CONFIG_C)["planner"]["exploration_offset"] == 0

    def test_A_config_policy_null(self):
        assert _load(_CONFIG_A)["planner"]["policy"] is None

    def test_B_config_policy_null(self):
        assert _load(_CONFIG_B)["planner"]["policy"] is None

    def test_C_config_policy_references_insights_first(self):
        policy = _load(_CONFIG_C)["planner"]["policy"]
        assert policy is not None
        assert "insights" in policy

    def test_all_configs_reference_degraded_v2_state(self):
        for cfg_path in (_CONFIG_A, _CONFIG_B, _CONFIG_C):
            data = _load(cfg_path)
            assert "degraded_v2" in data["planner"]["portfolio_state"]

    def test_all_configs_reference_synthetic_v2_ledger(self):
        for cfg_path in (_CONFIG_A, _CONFIG_B, _CONFIG_C):
            data = _load(cfg_path)
            assert "synthetic_v2" in data["planner"]["ledger"]

    def test_all_configs_have_explain_true(self):
        for cfg_path in (_CONFIG_A, _CONFIG_B, _CONFIG_C):
            data = _load(cfg_path)
            assert data["planner"]["explain"] is True

    def test_all_configs_runs_is_one(self):
        for cfg_path in (_CONFIG_A, _CONFIG_B, _CONFIG_C):
            data = _load(cfg_path)
            assert data["runs"] == 1

    def test_A_config_output_paths_contain_neutral_offset0(self):
        data = _load(_CONFIG_A)
        assert "neutral_offset0" in data["output"]["experiment_results"]
        assert "neutral_offset0" in data["output"]["envelope_prefix"]

    def test_B_config_output_paths_contain_neutral_offset1(self):
        data = _load(_CONFIG_B)
        assert "neutral_offset1" in data["output"]["experiment_results"]
        assert "neutral_offset1" in data["output"]["envelope_prefix"]

    def test_C_config_output_paths_contain_insights_offset0(self):
        data = _load(_CONFIG_C)
        assert "insights_offset0" in data["output"]["experiment_results"]
        assert "insights_offset0" in data["output"]["envelope_prefix"]

    def test_referenced_portfolio_state_file_exists(self):
        data = _load(_CONFIG_A)
        assert (_REPO_ROOT / data["planner"]["portfolio_state"]).exists()

    def test_referenced_ledger_file_exists(self):
        data = _load(_CONFIG_A)
        assert (_REPO_ROOT / data["planner"]["ledger"]).exists()

    def test_C_referenced_policy_file_exists(self):
        data = _load(_CONFIG_C)
        assert (_REPO_ROOT / data["planner"]["policy"]).exists()


# ---------------------------------------------------------------------------
# 3. Config integration: _apply_config parses each config correctly
# ---------------------------------------------------------------------------

class TestBaselineConfigIntegration:
    """Verify configs integrate with run_planner_experiment._apply_config."""

    def _none_args(self):
        obj = type("Args", (), {
            "runs": None, "portfolio_state": None, "ledger": None,
            "policy": None, "top_k": None, "exploration_offset": None,
            "max_actions": None, "explain": None, "output": None,
            "envelope_prefix": None,
        })()
        return obj

    def test_A_config_apply_top_k(self):
        args = self._none_args()
        _runner._apply_config(args, _load(_CONFIG_A))
        assert args.top_k == 2

    def test_A_config_apply_exploration_offset(self):
        args = self._none_args()
        _runner._apply_config(args, _load(_CONFIG_A))
        assert args.exploration_offset == 0

    def test_B_config_apply_exploration_offset(self):
        args = self._none_args()
        _runner._apply_config(args, _load(_CONFIG_B))
        assert args.exploration_offset == 1

    def test_C_config_apply_policy_path(self):
        args = self._none_args()
        _runner._apply_config(args, _load(_CONFIG_C))
        assert args.policy is not None
        assert "insights" in args.policy

    def test_A_config_apply_policy_stays_none(self):
        args = self._none_args()
        _runner._apply_config(args, _load(_CONFIG_A))
        assert args.policy is None

    def test_A_config_apply_output_path(self):
        args = self._none_args()
        _runner._apply_config(args, _load(_CONFIG_A))
        assert "neutral_offset0" in args.output

    def test_A_config_apply_envelope_prefix(self):
        args = self._none_args()
        _runner._apply_config(args, _load(_CONFIG_A))
        assert "neutral_offset0" in args.envelope_prefix

    def test_all_configs_apply_explain_true(self):
        for cfg_path in (_CONFIG_A, _CONFIG_B, _CONFIG_C):
            args = self._none_args()
            _runner._apply_config(args, _load(cfg_path))
            assert args.explain is True

    def test_all_configs_apply_runs_one(self):
        for cfg_path in (_CONFIG_A, _CONFIG_B, _CONFIG_C):
            args = self._none_args()
            _runner._apply_config(args, _load(cfg_path))
            assert args.runs == 1
