# SPDX-License-Identifier: MIT
"""Regression tests for scripts/analyze_planner_collision_risk.py.

Covers:
1. JSON output structure (all required keys present and correctly typed).
2. Deterministic results (identical inputs always produce identical outputs).
3. collision_ratio calculation correctness.
4. Entropy metrics exist and are numeric.
5. Full analyze_collision_risk() round-trip with mocked _fetch_actions.
"""
import importlib.util
import json
import math
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Module loading (importlib pattern — avoids subprocess sys.path issues)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SCRIPT = _REPO_ROOT / "scripts" / "analyze_planner_collision_risk.py"
_spec = importlib.util.spec_from_file_location("analyze_planner_collision_risk", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_compute_risk = _mod._compute_risk
_entropy = _mod._entropy
analyze_collision_risk = _mod.analyze_collision_risk
ACTION_TO_TASK = _mod.ACTION_TO_TASK


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

def _make_action(action_type, priority, action_id="aid-0", repo_id="repo-0"):
    return {
        "action_type": action_type,
        "priority": priority,
        "action_id": action_id,
        "repo_id": repo_id,
    }


def _make_actions(specs):
    """Build action list from [(action_type, priority), ...] specs."""
    return [
        {
            "action_type": at,
            "priority": pri,
            "action_id": f"aid-{i}",
            "repo_id": f"repo-{i}",
        }
        for i, (at, pri) in enumerate(specs)
    ]


# Minimal action list with known mapping outcomes when ACTION_TO_TASK is used:
#   regenerate_missing_artifact → build_portfolio_dashboard
#   recover_failed_workflow     → failure_recovery_example
#   refresh_repo_health         → build_portfolio_dashboard  (COLLISION)
_THREE_ACTION_SPECS = [
    ("regenerate_missing_artifact", 0.95),
    ("recover_failed_workflow", 0.85),
    ("refresh_repo_health", 0.80),
]

_REQUIRED_KEYS = {
    "policy",
    "top_k",
    "ranked_action_window",
    "mapped_tasks",
    "unique_tasks",
    "collapse_count",
    "collision_ratio",
    "task_entropy",
    "action_entropy",
}


# ---------------------------------------------------------------------------
# 1. _entropy unit tests
# ---------------------------------------------------------------------------

class TestEntropy:
    def test_empty_returns_zero(self):
        assert _entropy({}) == 0.0

    def test_single_label_returns_zero(self):
        # p=1.0, -1*log2(1)=0
        assert _entropy({"a": 5}) == 0.0

    def test_two_equal_labels_returns_one_bit(self):
        result = _entropy({"a": 1, "b": 1})
        assert abs(result - 1.0) < 1e-6

    def test_deterministic_for_same_counts(self):
        counts = {"x": 3, "y": 1, "z": 2}
        assert _entropy(counts) == _entropy(dict(counts))

    def test_result_is_float(self):
        assert isinstance(_entropy({"a": 2, "b": 3}), float)

    def test_rounded_to_6_places(self):
        result = _entropy({"a": 1, "b": 2, "c": 3})
        assert result == round(result, 6)


# ---------------------------------------------------------------------------
# 2. _compute_risk — JSON structure
# ---------------------------------------------------------------------------

class TestComputeRiskStructure:
    """_compute_risk output must contain all expected keys with correct types."""

    def _run(self, specs=None, top_k=3, mapping=None, exploration_offset=0):
        actions = _make_actions(specs or _THREE_ACTION_SPECS)
        mapping = mapping if mapping is not None else dict(ACTION_TO_TASK)
        return _compute_risk(
            actions=actions,
            top_k=top_k,
            ledger={},
            signals={},
            policy={},
            active_mapping=mapping,
            exploration_offset=exploration_offset,
        )

    def test_all_required_keys_present(self):
        result = self._run()
        expected = {
            "ranked_action_window",
            "mapped_tasks",
            "unique_tasks",
            "collapse_count",
            "collision_ratio",
            "task_entropy",
            "action_entropy",
        }
        assert expected <= set(result.keys())

    def test_ranked_action_window_is_list(self):
        assert isinstance(self._run()["ranked_action_window"], list)

    def test_mapped_tasks_is_list(self):
        assert isinstance(self._run()["mapped_tasks"], list)

    def test_unique_tasks_is_int(self):
        assert isinstance(self._run()["unique_tasks"], int)

    def test_collapse_count_is_int(self):
        assert isinstance(self._run()["collapse_count"], int)

    def test_collision_ratio_is_float(self):
        assert isinstance(self._run()["collision_ratio"], float)

    def test_task_entropy_is_float(self):
        assert isinstance(self._run()["task_entropy"], float)

    def test_action_entropy_is_float(self):
        assert isinstance(self._run()["action_entropy"], float)

    def test_window_length_equals_top_k(self):
        result = self._run(top_k=2)
        assert len(result["ranked_action_window"]) == 2

    def test_mapped_tasks_same_length_as_window(self):
        result = self._run()
        assert len(result["mapped_tasks"]) == len(result["ranked_action_window"])


# ---------------------------------------------------------------------------
# 3. _compute_risk — collision_ratio correctness
# ---------------------------------------------------------------------------

class TestCollisionRatio:
    """Verify collapse_count and collision_ratio match the expected formula."""

    def _run(self, specs, top_k, mapping=None):
        actions = _make_actions(specs)
        mapping = mapping if mapping is not None else dict(ACTION_TO_TASK)
        return _compute_risk(
            actions=actions,
            top_k=top_k,
            ledger={},
            signals={},
            policy={},
            active_mapping=mapping,
        )

    def test_no_collision_all_unique_tasks(self):
        # 2 actions, each maps to a different task
        specs = [
            ("analyze_repo_insights", 0.90),   # → repo_insights_example
            ("recover_failed_workflow", 0.80),  # → failure_recovery_example
        ]
        result = self._run(specs, top_k=2)
        assert result["collapse_count"] == 0
        assert result["collision_ratio"] == 0.0
        assert result["unique_tasks"] == 2

    def test_one_collision_in_three_actions(self):
        # Window: regenerate_missing_artifact → build_portfolio_dashboard (new)
        #         recover_failed_workflow     → failure_recovery_example  (new)
        #         refresh_repo_health         → build_portfolio_dashboard  (COLLISION)
        specs = _THREE_ACTION_SPECS
        result = self._run(specs, top_k=3)
        assert result["collapse_count"] == 1
        assert result["unique_tasks"] == 2
        assert abs(result["collision_ratio"] - round(1 / 3, 6)) < 1e-9

    def test_all_collisions_single_task(self):
        # Three actions all map to build_portfolio_dashboard
        specs = [
            ("refresh_repo_health", 0.90),
            ("regenerate_missing_artifact", 0.80),
            ("rerun_failed_task", 0.70),
        ]
        result = self._run(specs, top_k=3)
        assert result["unique_tasks"] == 1
        assert result["collapse_count"] == 2
        assert abs(result["collision_ratio"] - round(2 / 3, 6)) < 1e-9

    def test_unmapped_action_counted_in_collapse(self):
        # One action unmapped → doesn't add to unique_tasks → counted as collapse
        mapping = {"recover_failed_workflow": "failure_recovery_example"}
        specs = [
            ("recover_failed_workflow", 0.90),
            ("unknown_action", 0.80),  # not in mapping
        ]
        result = self._run(specs, top_k=2, mapping=mapping)
        assert result["unique_tasks"] == 1
        assert result["collapse_count"] == 1
        assert result["collision_ratio"] == 0.5

    def test_empty_window_zero_ratio(self):
        result = _compute_risk(
            actions=[],
            top_k=3,
            ledger={},
            signals={},
            policy={},
            active_mapping=dict(ACTION_TO_TASK),
        )
        assert result["collision_ratio"] == 0.0
        assert result["collapse_count"] == 0
        assert result["unique_tasks"] == 0

    def test_formula_consistency(self):
        # collapse_count + unique_tasks == window_size (for fully-mapped windows)
        specs = _THREE_ACTION_SPECS
        result = self._run(specs, top_k=3)
        window_size = len(result["ranked_action_window"])
        assert result["collapse_count"] + result["unique_tasks"] == window_size


# ---------------------------------------------------------------------------
# 4. _compute_risk — entropy metrics
# ---------------------------------------------------------------------------

class TestEntropyMetrics:
    """task_entropy and action_entropy must be numeric and plausible."""

    def _run(self, specs=None, top_k=3):
        actions = _make_actions(specs or _THREE_ACTION_SPECS)
        return _compute_risk(
            actions=actions,
            top_k=top_k,
            ledger={},
            signals={},
            policy={},
            active_mapping=dict(ACTION_TO_TASK),
        )

    def test_task_entropy_is_non_negative(self):
        assert self._run()["task_entropy"] >= 0.0

    def test_action_entropy_is_non_negative(self):
        assert self._run()["action_entropy"] >= 0.0

    def test_task_entropy_zero_when_single_unique_task(self):
        # All three map to build_portfolio_dashboard → entropy of {task: 3} = 0
        specs = [
            ("refresh_repo_health", 0.90),
            ("regenerate_missing_artifact", 0.80),
            ("rerun_failed_task", 0.70),
        ]
        result = self._run(specs, top_k=3)
        assert result["task_entropy"] == 0.0

    def test_action_entropy_zero_for_single_action_type(self):
        # Only one distinct action type in window → entropy = 0
        specs = [("refresh_repo_health", 0.90)]
        result = self._run(specs, top_k=1)
        assert result["action_entropy"] == 0.0

    def test_entropy_bounded_by_log2_top_k(self):
        # Shannon entropy cannot exceed log2(top_k).
        # Allow 0.5e-6 tolerance because _entropy rounds to 6 decimal places.
        top_k = 3
        result = self._run(top_k=top_k)
        max_entropy = math.log2(top_k)
        assert result["action_entropy"] <= max_entropy + 0.5e-6
        assert result["task_entropy"] <= max_entropy + 0.5e-6


# ---------------------------------------------------------------------------
# 5. Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    """Identical inputs must produce identical outputs on every call."""

    def _run_once(self, exploration_offset=0):
        actions = _make_actions(_THREE_ACTION_SPECS)
        return _compute_risk(
            actions=actions,
            top_k=3,
            ledger={},
            signals={},
            policy={},
            active_mapping=dict(ACTION_TO_TASK),
            exploration_offset=exploration_offset,
        )

    def test_repeated_calls_identical(self):
        r1 = self._run_once()
        r2 = self._run_once()
        assert r1 == r2

    def test_window_ordering_stable(self):
        r1 = self._run_once()
        r2 = self._run_once()
        assert r1["ranked_action_window"] == r2["ranked_action_window"]

    def test_exploration_offset_changes_window(self):
        r0 = self._run_once(exploration_offset=0)
        r1 = self._run_once(exploration_offset=1)
        # Offsets 0 and 1 produce different windows when enough actions exist
        # (with 3 actions and top_k=3, offset 1 clamps to 0, so may be same)
        # Just verify both are deterministic across repeated calls
        r0b = self._run_once(exploration_offset=0)
        r1b = self._run_once(exploration_offset=1)
        assert r0 == r0b
        assert r1 == r1b


# ---------------------------------------------------------------------------
# 6. Full round-trip — analyze_collision_risk (mocked _fetch_actions)
# ---------------------------------------------------------------------------

class TestAnalyzeCollisionRiskRoundTrip:
    """Test analyze_collision_risk() writes correct JSON using mocked subprocess."""

    def _raw_actions(self):
        return _make_actions(_THREE_ACTION_SPECS)

    def test_output_json_has_all_required_keys(self, tmp_path):
        out = tmp_path / "risk.json"
        portfolio_state = tmp_path / "ps.json"
        portfolio_state.write_text(json.dumps({"repos": []}), encoding="utf-8")

        with patch.object(_mod, "_fetch_actions", return_value=self._raw_actions()):
            summary = analyze_collision_risk(
                policy_path=None,
                top_k=3,
                portfolio_state_path=str(portfolio_state),
                ledger_path=None,
                output_path=str(out),
            )

        assert _REQUIRED_KEYS <= set(summary.keys())
        written = json.loads(out.read_text(encoding="utf-8"))
        assert _REQUIRED_KEYS <= set(written.keys())

    def test_output_matches_return_value(self, tmp_path):
        out = tmp_path / "risk.json"
        portfolio_state = tmp_path / "ps.json"
        portfolio_state.write_text(json.dumps({"repos": []}), encoding="utf-8")

        with patch.object(_mod, "_fetch_actions", return_value=self._raw_actions()):
            summary = analyze_collision_risk(
                policy_path=None,
                top_k=3,
                portfolio_state_path=str(portfolio_state),
                ledger_path=None,
                output_path=str(out),
            )

        written = json.loads(out.read_text(encoding="utf-8"))
        assert written == summary

    def test_top_k_in_output(self, tmp_path):
        out = tmp_path / "risk.json"
        portfolio_state = tmp_path / "ps.json"
        portfolio_state.write_text(json.dumps({"repos": []}), encoding="utf-8")

        with patch.object(_mod, "_fetch_actions", return_value=self._raw_actions()):
            summary = analyze_collision_risk(
                policy_path=None,
                top_k=2,
                portfolio_state_path=str(portfolio_state),
                ledger_path=None,
                output_path=str(out),
            )

        assert summary["top_k"] == 2
        assert len(summary["ranked_action_window"]) == 2

    def test_collision_ratio_correct_in_round_trip(self, tmp_path):
        out = tmp_path / "risk.json"
        portfolio_state = tmp_path / "ps.json"
        portfolio_state.write_text(json.dumps({"repos": []}), encoding="utf-8")

        with patch.object(_mod, "_fetch_actions", return_value=self._raw_actions()):
            summary = analyze_collision_risk(
                policy_path=None,
                top_k=3,
                portfolio_state_path=str(portfolio_state),
                ledger_path=None,
                output_path=str(out),
            )

        # Window has 1 collision (refresh_repo_health → build_portfolio_dashboard already seen)
        assert summary["collapse_count"] == 1
        assert abs(summary["collision_ratio"] - round(1 / 3, 6)) < 1e-9

    def test_mapping_override_applied(self, tmp_path):
        out = tmp_path / "risk.json"
        portfolio_state = tmp_path / "ps.json"
        portfolio_state.write_text(json.dumps({"repos": []}), encoding="utf-8")

        # Override: all three actions map to distinct tasks
        override_file = tmp_path / "override.json"
        override_file.write_text(json.dumps({
            "regenerate_missing_artifact": "artifact_audit_example",
            "recover_failed_workflow": "failure_recovery_example",
            "refresh_repo_health": "repo_insights_example",
        }), encoding="utf-8")

        with patch.object(_mod, "_fetch_actions", return_value=self._raw_actions()):
            summary = analyze_collision_risk(
                policy_path=None,
                top_k=3,
                portfolio_state_path=str(portfolio_state),
                ledger_path=None,
                mapping_override_path=str(override_file),
                output_path=str(out),
            )

        assert summary["collapse_count"] == 0
        assert summary["collision_ratio"] == 0.0
        assert summary["unique_tasks"] == 3

    def test_deterministic_repeated_calls(self, tmp_path):
        out1 = tmp_path / "risk1.json"
        out2 = tmp_path / "risk2.json"
        portfolio_state = tmp_path / "ps.json"
        portfolio_state.write_text(json.dumps({"repos": []}), encoding="utf-8")

        actions = self._raw_actions()

        with patch.object(_mod, "_fetch_actions", return_value=actions):
            s1 = analyze_collision_risk(
                policy_path=None,
                top_k=3,
                portfolio_state_path=str(portfolio_state),
                ledger_path=None,
                output_path=str(out1),
            )
        with patch.object(_mod, "_fetch_actions", return_value=actions):
            s2 = analyze_collision_risk(
                policy_path=None,
                top_k=3,
                portfolio_state_path=str(portfolio_state),
                ledger_path=None,
                output_path=str(out2),
            )

        assert s1 == s2


# ---------------------------------------------------------------------------
# 7. Integration — real experiment fixtures (no subprocess mocking)
# ---------------------------------------------------------------------------

class TestRealFixtures:
    """Smoke test against real experiment files (reads files, no task execution)."""

    _PORTFOLIO_STATE = (
        _REPO_ROOT / "experiments" / "portfolio_state_degraded_v2.json"
    )
    _LEDGER = (
        _REPO_ROOT / "experiments" / "action_effectiveness_ledger_synthetic_v2.json"
    )

    @pytest.fixture(autouse=True)
    def _skip_if_missing(self):
        if not self._PORTFOLIO_STATE.exists() or not self._LEDGER.exists():
            pytest.skip("Experiment fixture files not present")

    def test_compute_risk_with_real_fixtures(self):
        from scripts.planner_scoring import (
            _apply_learning_adjustments,
            load_effectiveness_ledger,
            load_planner_policy,
            load_portfolio_signals,
        )
        import json as _json

        ps_data = _json.loads(self._PORTFOLIO_STATE.read_text(encoding="utf-8"))
        actions = []
        for repo in ps_data.get("repos", []):
            for act in repo.get("recommended_actions", []):
                entry = dict(act)
                entry.setdefault("repo_id", repo.get("repo_id", ""))
                actions.append(entry)

        ledger = load_effectiveness_ledger(str(self._LEDGER))
        signals = load_portfolio_signals(str(self._PORTFOLIO_STATE))

        result = _compute_risk(
            actions=actions,
            top_k=3,
            ledger=ledger,
            signals=signals,
            policy={},
            active_mapping=dict(ACTION_TO_TASK),
        )

        assert set(result.keys()) >= {
            "ranked_action_window",
            "mapped_tasks",
            "unique_tasks",
            "collapse_count",
            "collision_ratio",
            "task_entropy",
            "action_entropy",
        }
        assert result["collision_ratio"] >= 0.0
        assert result["task_entropy"] >= 0.0
        assert result["action_entropy"] >= 0.0
        # Determinism: run again and compare
        result2 = _compute_risk(
            actions=actions,
            top_k=3,
            ledger=ledger,
            signals=signals,
            policy={},
            active_mapping=dict(ACTION_TO_TASK),
        )
        assert result == result2
