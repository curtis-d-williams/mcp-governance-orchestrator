# SPDX-License-Identifier: MIT
"""Regression tests for v0.31 planner explainability and policy guardrails.

Covers:
- _build_priority_breakdown writes deterministic breakdown output
- all expected fields are present in every entry
- malformed policy degrades safely (non-numeric weights ignored)
- oversized policy normalized deterministically to POLICY_TOTAL_ABS_CAP
- no --explain flag preserves v0.30 ranking behavior (additive, read-only)
- per-weight clamp still enforced after normalization
- existing planner tests still pass (import smoke check)
"""
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.claude_dynamic_planner_loop import (  # noqa: E402
    POLICY_TOTAL_ABS_CAP,
    POLICY_WEIGHT_CLAMP,
    _apply_learning_adjustments,
    _build_priority_breakdown,
    compute_policy_adjustment,
    load_planner_policy,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EXPECTED_FIELDS = {
    "action_type",
    "base_priority",
    "effectiveness_component",
    "signal_delta_component",
    "weak_signal_targeting_component",
    "policy_component",
    "capability_reliability_component",
    "confidence_factor",
    "exploration_component",
    "final_priority",
}


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
# _build_priority_breakdown — field presence and determinism
# ---------------------------------------------------------------------------

class TestBuildPriorityBreakdown:
    def _base_setup(self):
        actions = _make_actions([
            ("type_a", 0.7),
            ("type_b", 0.5),
        ])
        ledger = {
            "type_a": _ledger_entry(
                effectiveness_score=1.0,
                effect_deltas={"sig_x": 0.4},
                times_executed=10,
            ),
            "type_b": _ledger_entry(
                effectiveness_score=0.5,
                effect_deltas={"sig_x": 0.2},
                times_executed=5,
            ),
        }
        return actions, ledger

    def test_returns_one_entry_per_action(self):
        actions, ledger = self._base_setup()
        result = _build_priority_breakdown(actions, ledger, {}, {})
        assert len(result) == 2

    def test_all_expected_fields_present(self):
        actions, ledger = self._base_setup()
        result = _build_priority_breakdown(actions, ledger, {}, {})
        for entry in result:
            assert _EXPECTED_FIELDS == set(entry.keys()), (
                f"Missing/extra fields in entry {entry['action_type']}: {set(entry.keys())}"
            )

    def test_action_type_matches_input(self):
        actions, ledger = self._base_setup()
        result = _build_priority_breakdown(actions, ledger, {}, {})
        assert result[0]["action_type"] == "type_a"
        assert result[1]["action_type"] == "type_b"

    def test_base_priority_matches_action(self):
        actions, ledger = self._base_setup()
        result = _build_priority_breakdown(actions, ledger, {}, {})
        assert result[0]["base_priority"] == pytest.approx(0.7)
        assert result[1]["base_priority"] == pytest.approx(0.5)

    def test_final_priority_equals_sum_of_components(self):
        actions, ledger = self._base_setup()
        result = _build_priority_breakdown(actions, ledger, {}, {})
        for entry in result:
            expected_final = (
                entry["base_priority"]
                + entry["effectiveness_component"]
                + entry["signal_delta_component"]
                + entry["weak_signal_targeting_component"]
                + entry["policy_component"]
                + entry["capability_reliability_component"]
                + entry["exploration_component"]
            )
            assert entry["final_priority"] == pytest.approx(expected_final, rel=1e-5)

    def test_deterministic_repeated_calls(self):
        actions, ledger = self._base_setup()
        r1 = _build_priority_breakdown(actions, ledger, {}, {})
        r2 = _build_priority_breakdown(actions, ledger, {}, {})
        assert r1 == r2

    def test_empty_actions_returns_empty_list(self):
        result = _build_priority_breakdown([], {}, {}, {})
        assert result == []

    def test_empty_ledger_zero_learning_components(self):
        actions = _make_actions([("type_x", 0.6)])
        result = _build_priority_breakdown(actions, {}, {}, {})
        entry = result[0]
        assert entry["effectiveness_component"] == pytest.approx(0.0)
        assert entry["signal_delta_component"] == pytest.approx(0.0)
        assert entry["weak_signal_targeting_component"] == pytest.approx(0.0)
        assert entry["policy_component"] == pytest.approx(0.0)
        assert entry["confidence_factor"] == pytest.approx(0.0)

    def test_confidence_factor_range(self):
        actions, ledger = self._base_setup()
        result = _build_priority_breakdown(actions, ledger, {}, {})
        for entry in result:
            assert 0.0 <= entry["confidence_factor"] <= 1.0

    def test_policy_component_nonzero_when_policy_provided(self):
        actions = _make_actions([("type_a", 0.5)])
        ledger = {
            "type_a": _ledger_entry(effect_deltas={"sig_x": 1.0}, times_executed=10),
        }
        policy = {"sig_x": 2.0}
        result = _build_priority_breakdown(actions, ledger, {}, policy)
        assert result[0]["policy_component"] != pytest.approx(0.0)

    def test_breakdown_preserves_ranked_order(self):
        """Breakdown order matches the input action list order (not re-sorted)."""
        actions = _make_actions([("type_b", 0.5), ("type_a", 0.7)])
        ledger = {
            "type_a": _ledger_entry(times_executed=5),
            "type_b": _ledger_entry(times_executed=5),
        }
        result = _build_priority_breakdown(actions, ledger, {}, {})
        # Preserves input order (type_b first, type_a second)
        assert result[0]["action_type"] == "type_b"
        assert result[1]["action_type"] == "type_a"

    def test_breakdown_does_not_mutate_actions(self):
        actions, ledger = self._base_setup()
        original_types = [a["action_type"] for a in actions]
        _build_priority_breakdown(actions, ledger, {}, {})
        assert [a["action_type"] for a in actions] == original_types


# ---------------------------------------------------------------------------
# load_planner_policy v0.31: non-numeric filtering
# ---------------------------------------------------------------------------

class TestLoadPlannerPolicyNonNumericFilter:
    def test_non_numeric_value_excluded(self, tmp_path):
        p = tmp_path / "policy.json"
        p.write_text(json.dumps({"sig_a": "bad", "sig_b": 1.5}), encoding="utf-8")
        result = load_planner_policy(str(p))
        assert "sig_a" not in result
        assert result["sig_b"] == pytest.approx(1.5)

    def test_null_value_excluded(self, tmp_path):
        p = tmp_path / "policy.json"
        p.write_text(json.dumps({"sig_a": None, "sig_b": 1.0}), encoding="utf-8")
        result = load_planner_policy(str(p))
        assert "sig_a" not in result
        assert "sig_b" in result

    def test_list_value_excluded(self, tmp_path):
        p = tmp_path / "policy.json"
        p.write_text(json.dumps({"sig_a": [1, 2], "sig_b": 2.0}), encoding="utf-8")
        result = load_planner_policy(str(p))
        assert "sig_a" not in result
        assert result["sig_b"] == pytest.approx(2.0)

    def test_all_non_numeric_returns_empty(self, tmp_path):
        p = tmp_path / "policy.json"
        p.write_text(json.dumps({"sig_a": "x", "sig_b": "y"}), encoding="utf-8")
        assert load_planner_policy(str(p)) == {}

    def test_integer_weight_accepted(self, tmp_path):
        p = tmp_path / "policy.json"
        p.write_text(json.dumps({"sig_a": 3}), encoding="utf-8")
        result = load_planner_policy(str(p))
        assert result["sig_a"] == pytest.approx(3.0)

    def test_numeric_weights_within_clamp_unchanged(self, tmp_path):
        p = tmp_path / "policy.json"
        p.write_text(json.dumps({"sig_a": 2.0, "sig_b": -1.5}), encoding="utf-8")
        result = load_planner_policy(str(p))
        assert result["sig_a"] == pytest.approx(2.0)
        assert result["sig_b"] == pytest.approx(-1.5)

    def test_per_weight_clamp_applied_at_load(self, tmp_path):
        p = tmp_path / "policy.json"
        p.write_text(json.dumps({"sig_a": 100.0, "sig_b": -200.0}), encoding="utf-8")
        result = load_planner_policy(str(p))
        assert result["sig_a"] == pytest.approx(POLICY_WEIGHT_CLAMP)
        assert result["sig_b"] == pytest.approx(-POLICY_WEIGHT_CLAMP)


# ---------------------------------------------------------------------------
# load_planner_policy v0.31: total-magnitude normalization
# ---------------------------------------------------------------------------

class TestLoadPlannerPolicyNormalization:
    def test_below_cap_not_normalized(self, tmp_path):
        # Two weights each 5.0 → total abs = 10 < 20 → unchanged
        p = tmp_path / "policy.json"
        p.write_text(json.dumps({"a": 5.0, "b": 5.0}), encoding="utf-8")
        result = load_planner_policy(str(p))
        assert result["a"] == pytest.approx(5.0)
        assert result["b"] == pytest.approx(5.0)

    def test_at_cap_not_normalized(self, tmp_path):
        # Four weights at 5.0 → total abs = 20.0 = cap → unchanged
        p = tmp_path / "policy.json"
        p.write_text(json.dumps({"a": 5.0, "b": 5.0, "c": 5.0, "d": 5.0}), encoding="utf-8")
        result = load_planner_policy(str(p))
        total_abs = sum(abs(v) for v in result.values())
        assert total_abs == pytest.approx(POLICY_TOTAL_ABS_CAP)

    def test_above_cap_normalized_to_cap(self, tmp_path):
        # Five weights at 5.0 → total abs = 25 > 20 → scaled to 20
        p = tmp_path / "policy.json"
        p.write_text(json.dumps({"a": 5.0, "b": 5.0, "c": 5.0, "d": 5.0, "e": 5.0}), encoding="utf-8")
        result = load_planner_policy(str(p))
        total_abs = sum(abs(v) for v in result.values())
        assert total_abs == pytest.approx(POLICY_TOTAL_ABS_CAP)

    def test_normalization_preserves_relative_magnitudes(self, tmp_path):
        # weights 4.0, 8.0 → after clamp: 4.0, 5.0 → total=9 < 20 (no normalization needed)
        # Use values that exceed cap so normalization triggers
        # 5.0 and 5.0 per signal (×5 signals = 25 total) → scale = 20/25 = 0.8
        # Result: each = 5.0 * 0.8 = 4.0
        p = tmp_path / "policy.json"
        p.write_text(json.dumps({"a": 5.0, "b": 5.0, "c": 5.0, "d": 5.0, "e": 5.0}), encoding="utf-8")
        result = load_planner_policy(str(p))
        # All started equal → all remain equal after scaling
        values = list(result.values())
        assert all(v == pytest.approx(values[0]) for v in values)

    def test_normalization_preserves_signs(self, tmp_path):
        # Mixed signs: +5, -5, +5, -5, +5 → total abs = 25 → scale = 0.8
        p = tmp_path / "policy.json"
        p.write_text(json.dumps({"a": 5.0, "b": -5.0, "c": 5.0, "d": -5.0, "e": 5.0}), encoding="utf-8")
        result = load_planner_policy(str(p))
        # Signs must be preserved
        assert result["a"] > 0
        assert result["b"] < 0
        assert result["c"] > 0
        assert result["d"] < 0
        assert result["e"] > 0
        assert sum(abs(v) for v in result.values()) == pytest.approx(POLICY_TOTAL_ABS_CAP)

    def test_normalization_deterministic(self, tmp_path):
        p = tmp_path / "policy.json"
        p.write_text(json.dumps({"a": 5.0, "b": 5.0, "c": 5.0, "d": 5.0, "e": 5.0}), encoding="utf-8")
        r1 = load_planner_policy(str(p))
        r2 = load_planner_policy(str(p))
        assert r1 == r2

    def test_cap_constant_value(self):
        assert POLICY_TOTAL_ABS_CAP == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# Malformed policy degrades safely
# ---------------------------------------------------------------------------

class TestMalformedPolicySafeDegradation:
    def test_none_path_no_effect_on_ordering(self):
        actions = _make_actions([("type_a", 0.7), ("type_b", 0.5)])
        ledger = {
            "type_a": _ledger_entry(effect_deltas={"sig": 1.0}, times_executed=10),
            "type_b": _ledger_entry(effect_deltas={"sig": 0.5}, times_executed=10),
        }
        policy_none = load_planner_policy(None)
        assert policy_none == {}
        result = _apply_learning_adjustments(list(actions), ledger, policy=policy_none)
        assert result[0]["action_type"] == "type_a"

    def test_all_non_numeric_policy_returns_no_adjustment(self):
        ledger = {
            "type_a": _ledger_entry(effect_deltas={"sig": 1.0}, times_executed=10),
        }
        policy = {}  # result of all-non-numeric load
        adj = compute_policy_adjustment("type_a", ledger, policy)
        assert adj == pytest.approx(0.0)

    def test_malformed_json_policy_file_returns_empty(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not valid", encoding="utf-8")
        result = load_planner_policy(str(p))
        assert result == {}

    def test_mixed_malformed_policy_partial_numeric_applied(self, tmp_path):
        p = tmp_path / "policy.json"
        p.write_text(json.dumps({"sig_ok": 2.0, "sig_bad": "nope", "sig_null": None}), encoding="utf-8")
        result = load_planner_policy(str(p))
        assert "sig_ok" in result
        assert result["sig_ok"] == pytest.approx(2.0)
        assert "sig_bad" not in result
        assert "sig_null" not in result


# ---------------------------------------------------------------------------
# No --explain flag preserves v0.30 ranking behavior
# ---------------------------------------------------------------------------

class TestExplainFlagDoesNotAffectRanking:
    """_build_priority_breakdown must be read-only: ranking is unchanged."""

    def _ranked_order(self, actions, ledger, signals=None, policy=None):
        sorted_actions = _apply_learning_adjustments(
            list(actions), ledger, current_signals=signals, policy=policy
        )
        return [a["action_type"] for a in sorted_actions]

    def test_breakdown_does_not_change_ranking(self):
        actions = _make_actions([("type_a", 0.5), ("type_b", 0.7), ("type_c", 0.3)])
        ledger = {
            "type_a": _ledger_entry(effect_deltas={"sig": 0.3}, times_executed=10),
            "type_b": _ledger_entry(effect_deltas={"sig": 0.1}, times_executed=5),
            "type_c": _ledger_entry(effect_deltas={"sig": 0.5}, times_executed=2),
        }
        policy = {"sig": 1.5}
        order_before = self._ranked_order(list(actions), ledger, policy=policy)
        # Call breakdown (simulates --explain path)
        _build_priority_breakdown(list(actions), ledger, {}, policy)
        order_after = self._ranked_order(list(actions), ledger, policy=policy)
        assert order_before == order_after

    def test_ranking_identical_with_and_without_breakdown_call(self):
        actions = _make_actions([("type_z", 0.6), ("type_a", 0.6)])
        ledger = {
            "type_z": _ledger_entry(effectiveness_score=0.5, times_executed=8),
            "type_a": _ledger_entry(effectiveness_score=0.5, times_executed=8),
        }
        order_no_breakdown = self._ranked_order(list(actions), ledger)
        _build_priority_breakdown(list(actions), ledger, {}, {})
        order_with_breakdown = self._ranked_order(list(actions), ledger)
        assert order_no_breakdown == order_with_breakdown

    def test_empty_ledger_ranking_unchanged(self):
        actions = _make_actions([("type_b", 0.7), ("type_a", 0.5)])
        # Empty ledger → _apply_learning_adjustments returns actions unchanged
        result_no_explain = _apply_learning_adjustments(list(actions), {})
        _build_priority_breakdown(list(actions), {}, {}, {})
        result_with_explain = _apply_learning_adjustments(list(actions), {})
        assert result_no_explain is not result_with_explain  # both return unchanged
        assert [a["action_type"] for a in result_no_explain] == \
               [a["action_type"] for a in result_with_explain]


# ---------------------------------------------------------------------------
# Explain artifact written deterministically (integration-level unit test)
# ---------------------------------------------------------------------------

class TestExplainArtifactDeterminism:
    def test_breakdown_json_serializable(self):
        actions = _make_actions([("type_a", 0.8), ("type_b", 0.6)])
        ledger = {
            "type_a": _ledger_entry(effectiveness_score=1.0, effect_deltas={"s": 0.5}, times_executed=10),
            "type_b": _ledger_entry(effectiveness_score=0.5, effect_deltas={"s": 0.2}, times_executed=3),
        }
        breakdown = _build_priority_breakdown(actions, ledger, {}, {})
        serialized = json.dumps(breakdown, indent=2)
        restored = json.loads(serialized)
        assert len(restored) == 2
        assert _EXPECTED_FIELDS == set(restored[0].keys())

    def test_breakdown_written_to_file_is_deterministic(self, tmp_path):
        actions = _make_actions([("type_a", 0.8)])
        ledger = {"type_a": _ledger_entry(effect_deltas={"s": 0.5}, times_executed=5)}
        out = tmp_path / "planner_priority_breakdown.json"

        b1 = _build_priority_breakdown(actions, ledger, {}, {})
        out.write_text(json.dumps(b1, indent=2) + "\n", encoding="utf-8")
        content1 = out.read_text(encoding="utf-8")

        b2 = _build_priority_breakdown(actions, ledger, {}, {})
        out.write_text(json.dumps(b2, indent=2) + "\n", encoding="utf-8")
        content2 = out.read_text(encoding="utf-8")

        assert content1 == content2

    def test_breakdown_entry_values_are_numeric(self):
        actions = _make_actions([("type_a", 1.0)])
        ledger = {"type_a": _ledger_entry(times_executed=5)}
        breakdown = _build_priority_breakdown(actions, ledger, {}, {})
        for key in _EXPECTED_FIELDS - {"action_type"}:
            assert isinstance(breakdown[0][key], (int, float)), (
                f"Field {key} is not numeric: {breakdown[0][key]}"
            )


# ---------------------------------------------------------------------------
# Smoke: v0.26–v0.30 and v0.31 symbols importable
# ---------------------------------------------------------------------------

class TestBackwardCompatImports:
    def test_all_symbols_importable(self):
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
            POLICY_WEIGHT_CLAMP,
            POLICY_TOTAL_ABS_CAP,
            compute_learning_adjustment,
            compute_confidence_factor,
            compute_weak_signal_targeting_adjustment,
            compute_exploration_bonus,
            compute_policy_adjustment,
            load_planner_policy,
            _build_priority_breakdown,
            _apply_learning_adjustments,
        )
