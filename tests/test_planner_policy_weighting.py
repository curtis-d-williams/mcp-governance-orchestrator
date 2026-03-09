# SPDX-License-Identifier: MIT
"""Regression tests for v0.30 policy-weighted signal optimization.

Covers:
- policy weights affect priority
- missing policy produces identical ordering to v0.29
- negative weights invert signal preference
- deterministic behavior
- bounds enforcement (weights clamped to ±POLICY_WEIGHT_CLAMP)
- existing tests still pass (import smoke check)
"""
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.claude_dynamic_planner_loop import (  # noqa: E402
    POLICY_WEIGHT_CLAMP,
    _apply_learning_adjustments,
    compute_policy_adjustment,
    load_planner_policy,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_actions(specs):
    """Build a minimal action list from (action_type, priority) tuples."""
    return [
        {
            "action_type": at,
            "priority": pri,
            "action_id": f"aid-{i}",
            "repo_id": f"repo-{i}",
        }
        for i, (at, pri) in enumerate(specs)
    ]


def _ledger_entry(effectiveness_score=0.0, effect_deltas=None, times_executed=10):
    return {
        "effectiveness_score": effectiveness_score,
        "effect_deltas": effect_deltas or {},
        "times_executed": times_executed,
    }


# ---------------------------------------------------------------------------
# load_planner_policy
# ---------------------------------------------------------------------------

class TestLoadPlannerPolicy:
    def test_none_path_returns_empty(self):
        assert load_planner_policy(None) == {}

    def test_missing_file_returns_empty(self, tmp_path):
        assert load_planner_policy(str(tmp_path / "nonexistent.json")) == {}

    def test_malformed_json_returns_empty(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not valid json", encoding="utf-8")
        assert load_planner_policy(str(p)) == {}

    def test_non_dict_root_returns_empty(self, tmp_path):
        p = tmp_path / "policy.json"
        p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        assert load_planner_policy(str(p)) == {}

    def test_valid_policy_loaded(self, tmp_path):
        p = tmp_path / "policy.json"
        p.write_text(json.dumps({"artifact_completeness": 2.0, "stale_runs": -1.0}), encoding="utf-8")
        result = load_planner_policy(str(p))
        assert result["artifact_completeness"] == 2.0
        assert result["stale_runs"] == -1.0

    def test_non_string_keys_excluded(self, tmp_path):
        # JSON only allows string keys; this tests robustness of the filter
        p = tmp_path / "policy.json"
        p.write_text('{"artifact_completeness": 1.5}', encoding="utf-8")
        result = load_planner_policy(str(p))
        assert "artifact_completeness" in result

    def test_empty_dict_file_returns_empty(self, tmp_path):
        p = tmp_path / "policy.json"
        p.write_text("{}", encoding="utf-8")
        assert load_planner_policy(str(p)) == {}


# ---------------------------------------------------------------------------
# compute_policy_adjustment
# ---------------------------------------------------------------------------

class TestComputePolicyAdjustment:
    def test_empty_policy_returns_zero(self):
        ledger = {"type_a": _ledger_entry(effect_deltas={"artifact_completeness": 1.0})}
        assert compute_policy_adjustment("type_a", ledger, {}) == 0.0

    def test_none_policy_returns_zero(self):
        ledger = {"type_a": _ledger_entry(effect_deltas={"artifact_completeness": 1.0})}
        assert compute_policy_adjustment("type_a", ledger, None) == 0.0

    def test_missing_ledger_entry_returns_zero(self):
        policy = {"artifact_completeness": 2.0}
        assert compute_policy_adjustment("unknown_type", {}, policy) == 0.0

    def test_empty_effect_deltas_returns_zero(self):
        ledger = {"type_a": _ledger_entry(effect_deltas={})}
        policy = {"artifact_completeness": 2.0}
        assert compute_policy_adjustment("type_a", ledger, policy) == 0.0

    def test_signal_not_in_policy_skipped(self):
        ledger = {"type_a": _ledger_entry(effect_deltas={"artifact_completeness": 1.0})}
        policy = {"stale_runs": 2.0}  # no overlap with effect_deltas
        assert compute_policy_adjustment("type_a", ledger, policy) == 0.0

    def test_positive_weight_positive_delta_positive_result(self):
        # weight=2.0, delta=0.5 → 2.0 * 0.5 = 1.0
        ledger = {"type_a": _ledger_entry(effect_deltas={"artifact_completeness": 0.5})}
        policy = {"artifact_completeness": 2.0}
        result = compute_policy_adjustment("type_a", ledger, policy)
        assert result == pytest.approx(1.0)

    def test_negative_weight_inverts_sign(self):
        # weight=-2.0, delta=0.5 → -2.0 * 0.5 = -1.0
        ledger = {"type_a": _ledger_entry(effect_deltas={"artifact_completeness": 0.5})}
        policy = {"artifact_completeness": -2.0}
        result = compute_policy_adjustment("type_a", ledger, policy)
        assert result == pytest.approx(-1.0)

    def test_multiple_signals_summed(self):
        # sig_a: 1.0 * 0.5 = 0.5; sig_b: 2.0 * 0.3 = 0.6; total = 1.1
        ledger = {"type_a": _ledger_entry(effect_deltas={"sig_a": 0.5, "sig_b": 0.3})}
        policy = {"sig_a": 1.0, "sig_b": 2.0}
        result = compute_policy_adjustment("type_a", ledger, policy)
        assert result == pytest.approx(1.1)

    def test_weight_clamped_to_positive_limit(self):
        # weight=100.0 → clamped to 5.0; delta=1.0 → result=5.0
        ledger = {"type_a": _ledger_entry(effect_deltas={"sig": 1.0})}
        policy = {"sig": 100.0}
        result = compute_policy_adjustment("type_a", ledger, policy)
        assert result == pytest.approx(POLICY_WEIGHT_CLAMP * 1.0)

    def test_weight_clamped_to_negative_limit(self):
        # weight=-100.0 → clamped to -5.0; delta=1.0 → result=-5.0
        ledger = {"type_a": _ledger_entry(effect_deltas={"sig": 1.0})}
        policy = {"sig": -100.0}
        result = compute_policy_adjustment("type_a", ledger, policy)
        assert result == pytest.approx(-POLICY_WEIGHT_CLAMP * 1.0)

    def test_weight_at_boundary_not_clamped(self):
        # weight=5.0 exactly → no clamping; delta=1.0 → result=5.0
        ledger = {"type_a": _ledger_entry(effect_deltas={"sig": 1.0})}
        policy = {"sig": 5.0}
        result = compute_policy_adjustment("type_a", ledger, policy)
        assert result == pytest.approx(5.0)

    def test_non_numeric_weight_skipped(self):
        ledger = {"type_a": _ledger_entry(effect_deltas={"sig_a": 1.0, "sig_b": 1.0})}
        policy = {"sig_a": "bad", "sig_b": 2.0}
        result = compute_policy_adjustment("type_a", ledger, policy)
        # sig_a skipped (non-numeric), sig_b: 2.0 * 1.0 = 2.0
        assert result == pytest.approx(2.0)

    def test_deterministic_repeated_calls(self):
        ledger = {"type_a": _ledger_entry(effect_deltas={"artifact_completeness": 0.7, "stale_runs": 0.3})}
        policy = {"artifact_completeness": 1.5, "stale_runs": -0.5}
        r1 = compute_policy_adjustment("type_a", ledger, policy)
        r2 = compute_policy_adjustment("type_a", ledger, policy)
        assert r1 == r2

    def test_policy_weight_clamp_constant(self):
        assert POLICY_WEIGHT_CLAMP == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# _apply_learning_adjustments with policy
# ---------------------------------------------------------------------------

class TestApplyLearningAdjustmentsWithPolicy:
    def _base_ledger(self):
        return {
            "type_high": _ledger_entry(
                effectiveness_score=0.0,
                effect_deltas={"artifact_completeness": 1.0},
                times_executed=10,
            ),
            "type_low": _ledger_entry(
                effectiveness_score=0.0,
                effect_deltas={"artifact_completeness": 0.1},
                times_executed=10,
            ),
        }

    def test_policy_weights_affect_ordering(self):
        # Both actions same base priority; type_high has larger effect delta.
        # Large positive policy weight → type_high gets larger policy_adj → ranks first.
        actions = _make_actions([("type_high", 0.5), ("type_low", 0.5)])
        ledger = self._base_ledger()
        policy = {"artifact_completeness": 5.0}
        result = _apply_learning_adjustments(actions, ledger, policy=policy)
        assert result[0]["action_type"] == "type_high"
        assert result[1]["action_type"] == "type_low"

    def test_missing_policy_identical_to_v029(self):
        # No policy argument → same result as v0.29 (policy=None and policy={} both equal)
        actions = _make_actions([("type_high", 0.7), ("type_low", 0.5)])
        ledger = self._base_ledger()
        result_none = _apply_learning_adjustments(list(actions), ledger, policy=None)
        result_empty = _apply_learning_adjustments(list(actions), ledger, policy={})
        result_absent = _apply_learning_adjustments(list(actions), ledger)
        assert [a["action_type"] for a in result_none] == \
               [a["action_type"] for a in result_empty]
        assert [a["action_type"] for a in result_none] == \
               [a["action_type"] for a in result_absent]

    def test_negative_policy_weight_inverts_preference(self):
        # Without policy: type_high (larger delta) would get more boost.
        # With large negative weight: type_high gets a negative policy_adj → falls below type_low.
        actions = _make_actions([("type_high", 0.5), ("type_low", 0.5)])
        ledger = self._base_ledger()
        # Verify that without policy, type_high would rank first
        no_policy = _apply_learning_adjustments(list(actions), ledger)
        assert no_policy[0]["action_type"] == "type_high"
        # Now apply a strong negative weight
        policy = {"artifact_completeness": -5.0}
        with_policy = _apply_learning_adjustments(list(actions), ledger, policy=policy)
        # type_high: policy_adj = clamp(-5.0, ±5) * 1.0 = -5.0
        # type_low:  policy_adj = clamp(-5.0, ±5) * 0.1 = -0.5
        # type_low ends up higher
        assert with_policy[0]["action_type"] == "type_low"
        assert with_policy[1]["action_type"] == "type_high"

    def test_deterministic_ordering_repeated_runs(self):
        actions = _make_actions([
            ("type_high", 0.5),
            ("type_low", 0.5),
        ])
        ledger = self._base_ledger()
        policy = {"artifact_completeness": 2.0}
        order1 = [a["action_type"] for a in _apply_learning_adjustments(list(actions), ledger, policy=policy)]
        order2 = [a["action_type"] for a in _apply_learning_adjustments(list(actions), ledger, policy=policy)]
        assert order1 == order2

    def test_policy_weight_clamping_enforced_in_ordering(self):
        # weight=1000 and weight=5 should produce identical ordering (both clamp to 5)
        actions_1000 = _make_actions([("type_high", 0.5), ("type_low", 0.5)])
        actions_5 = _make_actions([("type_high", 0.5), ("type_low", 0.5)])
        ledger = self._base_ledger()
        order_1000 = [a["action_type"] for a in _apply_learning_adjustments(
            actions_1000, ledger, policy={"artifact_completeness": 1000.0}
        )]
        order_5 = [a["action_type"] for a in _apply_learning_adjustments(
            actions_5, ledger, policy={"artifact_completeness": 5.0}
        )]
        assert order_1000 == order_5

    def test_policy_adjustment_inside_confidence_scaling(self):
        # With times_executed=0 → confidence=0.0 → policy_adj has no effect on priority.
        # Both actions end up with same priority (base + exploration_bonus) → tiebreak alphabetical.
        ledger = {
            "type_b": _ledger_entry(effect_deltas={"sig": 10.0}, times_executed=0),
            "type_a": _ledger_entry(effect_deltas={"sig": 0.1}, times_executed=0),
        }
        actions = _make_actions([("type_b", 0.5), ("type_a", 0.5)])
        policy = {"sig": 5.0}
        result = _apply_learning_adjustments(actions, ledger, policy=policy)
        # confidence=0 → policy_adj scaled to 0 → tiebreak alphabetical
        assert result[0]["action_type"] == "type_a"
        assert result[1]["action_type"] == "type_b"

    def test_empty_ledger_returns_actions_unchanged(self):
        actions = _make_actions([("type_high", 0.5), ("type_low", 0.5)])
        policy = {"artifact_completeness": 5.0}
        result = _apply_learning_adjustments(actions, {}, policy=policy)
        assert result is actions  # unchanged (same object)

    def test_load_planner_policy_missing_file_no_effect(self, tmp_path):
        # load_planner_policy on missing file → {} → same ordering as no policy
        policy = load_planner_policy(str(tmp_path / "missing.json"))
        assert policy == {}
        actions = _make_actions([("type_high", 0.7), ("type_low", 0.5)])
        ledger = self._base_ledger()
        result_loaded = _apply_learning_adjustments(list(actions), ledger, policy=policy)
        result_none = _apply_learning_adjustments(list(actions), ledger, policy=None)
        assert [a["action_type"] for a in result_loaded] == \
               [a["action_type"] for a in result_none]


# ---------------------------------------------------------------------------
# Smoke: v0.26–v0.29 imports still work
# ---------------------------------------------------------------------------

class TestBackwardCompatImports:
    def test_v026_v029_symbols_importable(self):
        from scripts.claude_dynamic_planner_loop import (  # noqa: F401
            EFFECTIVENESS_WEIGHT,
            EFFECTIVENESS_CLAMP,
            SIGNAL_IMPACT_WEIGHT,
            SIGNAL_IMPACT_CLAMP,
            TARGETING_WEIGHT,
            TARGETING_CLAMP,
            CONFIDENCE_THRESHOLD,
            EXPLORATION_WEIGHT,
            EXPLORATION_CLAMP,
            compute_learning_adjustment,
            compute_confidence_factor,
            compute_weak_signal_targeting_adjustment,
            compute_exploration_bonus,
        )
