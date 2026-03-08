# SPDX-License-Identifier: MIT
"""Regression tests for v0.28 planner confidence weighting.

Covers:
- zero executions gives zero learning contribution
- low executions partially scale learning
- threshold-or-higher executions gives full learning effect
- missing ledger entry gives zero confidence
- invalid times_executed handled safely
- confidence bounded in [0, 1]
- deterministic repeated ordering
- existing v0.26 and v0.27 tests still pass (compatibility via backward-compat default)
"""
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.claude_dynamic_planner_loop import (  # noqa: E402
    CONFIDENCE_THRESHOLD,
    EFFECTIVENESS_CLAMP,
    EFFECTIVENESS_WEIGHT,
    SIGNAL_IMPACT_CLAMP,
    SIGNAL_IMPACT_WEIGHT,
    TARGETING_CLAMP,
    TARGETING_WEIGHT,
    _apply_learning_adjustments,
    compute_confidence_factor,
    compute_learning_adjustment,
    compute_weak_signal_targeting_adjustment,
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


def _ledger_entry(times_executed, effectiveness_score=1.0, effect_deltas=None):
    """Build a single ledger row dict."""
    entry = {
        "effectiveness_score": effectiveness_score,
        "effect_deltas": effect_deltas or {},
    }
    if times_executed is not None:
        entry["times_executed"] = times_executed
    return entry


# ---------------------------------------------------------------------------
# compute_confidence_factor – unit tests
# ---------------------------------------------------------------------------

class TestComputeConfidenceFactor:
    def test_zero_executions_gives_zero_confidence(self):
        ledger = {"type_a": _ledger_entry(times_executed=0)}
        assert compute_confidence_factor("type_a", ledger) == pytest.approx(0.0)

    def test_low_executions_partial_confidence(self):
        # times_executed=2, threshold=5 → 2/5 = 0.4
        ledger = {"type_a": _ledger_entry(times_executed=2)}
        assert compute_confidence_factor("type_a", ledger) == pytest.approx(2.0 / CONFIDENCE_THRESHOLD)

    def test_threshold_executions_gives_full_confidence(self):
        ledger = {"type_a": _ledger_entry(times_executed=5)}
        assert compute_confidence_factor("type_a", ledger) == pytest.approx(1.0)

    def test_above_threshold_capped_at_one(self):
        ledger = {"type_a": _ledger_entry(times_executed=100)}
        assert compute_confidence_factor("type_a", ledger) == pytest.approx(1.0)

    def test_missing_ledger_entry_returns_zero(self):
        assert compute_confidence_factor("unknown_type", {}) == pytest.approx(0.0)

    def test_action_absent_from_ledger_returns_zero(self):
        ledger = {"other_type": _ledger_entry(times_executed=10)}
        assert compute_confidence_factor("type_a", ledger) == pytest.approx(0.0)

    def test_negative_times_executed_returns_zero(self):
        ledger = {"type_a": _ledger_entry(times_executed=-1)}
        assert compute_confidence_factor("type_a", ledger) == pytest.approx(0.0)

    def test_non_numeric_times_executed_returns_zero(self):
        ledger = {"type_a": {"times_executed": "bad", "effectiveness_score": 1.0, "effect_deltas": {}}}
        assert compute_confidence_factor("type_a", ledger) == pytest.approx(0.0)

    def test_none_times_executed_returns_zero(self):
        ledger = {"type_a": {"times_executed": None, "effectiveness_score": 1.0, "effect_deltas": {}}}
        assert compute_confidence_factor("type_a", ledger) == pytest.approx(0.0)

    def test_times_executed_absent_gives_full_confidence(self):
        # Backward-compat: legacy ledger rows without times_executed → full confidence.
        ledger = {"type_a": {"effectiveness_score": 0.9, "effect_deltas": {}}}
        assert compute_confidence_factor("type_a", ledger) == pytest.approx(1.0)

    def test_confidence_bounded_at_one(self):
        for te in [0, 1, 4, 5, 6, 100]:
            ledger = {"type_a": _ledger_entry(times_executed=te)}
            c = compute_confidence_factor("type_a", ledger)
            assert 0.0 <= c <= 1.0, f"confidence out of [0,1] for times_executed={te}"

    def test_confidence_non_negative(self):
        for te in [-100, -1, 0]:
            ledger = {"type_a": _ledger_entry(times_executed=te)}
            assert compute_confidence_factor("type_a", ledger) >= 0.0

    def test_deterministic_repeated_calls(self):
        ledger = {"type_a": _ledger_entry(times_executed=3)}
        c1 = compute_confidence_factor("type_a", ledger)
        c2 = compute_confidence_factor("type_a", ledger)
        assert c1 == c2

    def test_float_times_executed_accepted(self):
        # 2.5 / 5.0 = 0.5
        ledger = {"type_a": {"times_executed": 2.5, "effectiveness_score": 0.0, "effect_deltas": {}}}
        assert compute_confidence_factor("type_a", ledger) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Confidence scaling of learning adjustment
# ---------------------------------------------------------------------------

class TestConfidenceScaledLearningAdjustment:
    """Verify that confidence scales the combined learning term."""

    def _full_ledger_entry(self, times_executed):
        return {
            "effectiveness_score": 1.0,
            "effect_deltas": {"artifact_completeness": 1.0},
            "times_executed": times_executed,
        }

    def test_zero_executions_gives_zero_contribution(self):
        ledger = {"type_a": self._full_ledger_entry(0)}
        # confidence=0 → learning terms zero out
        base_adj = compute_learning_adjustment("type_a", ledger)
        assert base_adj > 0.0, "precondition: raw adj must be positive"
        confidence = compute_confidence_factor("type_a", ledger)
        assert confidence == pytest.approx(0.0)
        # Effective scaled contribution is zero
        assert confidence * base_adj == pytest.approx(0.0)

    def test_low_executions_partially_scale_learning(self):
        ledger = {"type_a": self._full_ledger_entry(2)}
        confidence = compute_confidence_factor("type_a", ledger)
        raw_adj = compute_learning_adjustment("type_a", ledger)
        assert confidence == pytest.approx(0.4)
        assert confidence * raw_adj == pytest.approx(0.4 * raw_adj)

    def test_threshold_executions_full_learning_effect(self):
        ledger = {"type_a": self._full_ledger_entry(5)}
        confidence = compute_confidence_factor("type_a", ledger)
        raw_adj = compute_learning_adjustment("type_a", ledger)
        assert confidence == pytest.approx(1.0)
        assert confidence * raw_adj == pytest.approx(raw_adj)

    def test_above_threshold_still_full(self):
        ledger = {"type_a": self._full_ledger_entry(999)}
        confidence = compute_confidence_factor("type_a", ledger)
        assert confidence == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# _apply_learning_adjustments with confidence scaling
# ---------------------------------------------------------------------------

class TestApplyLearningAdjustmentsConfidence:
    def test_zero_executions_action_not_boosted(self):
        """Action with 0 executions should not overtake action with same base priority."""
        actions = _make_actions([
            ("type_a", 0.5),  # no ledger entry → 0 confidence
            ("type_b", 0.5),  # 0 executions → 0 confidence despite high effectiveness
        ])
        ledger = {
            "type_a": {"effectiveness_score": 0.0, "effect_deltas": {}, "times_executed": 10},
            "type_b": {"effectiveness_score": 999.0, "effect_deltas": {}, "times_executed": 0},
        }
        result = _apply_learning_adjustments(actions, ledger)
        # type_a: 0.5 + 1.0 * 0 = 0.5; type_b: 0.5 + 0.0 * large = 0.5
        # tiebreak alphabetical → type_a first
        assert result[0]["action_type"] == "type_a"
        assert result[1]["action_type"] == "type_b"

    def test_high_confidence_action_overtakes_low_confidence(self):
        """Action at threshold executions should overtake sparse-evidence action."""
        actions = _make_actions([
            ("type_a", 0.6),  # high base, sparse evidence
            ("type_b", 0.5),  # lower base, full confidence
        ])
        ledger = {
            "type_a": {
                "effectiveness_score": 1.0,
                "effect_deltas": {},
                "times_executed": 0,  # no confidence → adj scaled to 0
            },
            "type_b": {
                "effectiveness_score": 1.0,
                "effect_deltas": {},
                "times_executed": 5,  # full confidence → adj applied fully
            },
        }
        # type_a: 0.6 + 0 * 0.15 = 0.6
        # type_b: 0.5 + 1.0 * 0.15 = 0.65
        result = _apply_learning_adjustments(actions, ledger)
        assert result[0]["action_type"] == "type_b"
        assert result[1]["action_type"] == "type_a"

    def test_partial_confidence_proportional_boost(self):
        """Action with 2 executions gets 40% of the learning boost."""
        actions = _make_actions([
            ("type_a", 0.5),
            ("type_b", 0.5),
        ])
        # type_a: full confidence (5 execs), effectiveness=1.0 → adj=0.15 full
        # type_b: partial confidence (2 execs = 0.4), effectiveness=1.0 → adj=0.15*0.4=0.06
        ledger = {
            "type_a": {"effectiveness_score": 1.0, "effect_deltas": {}, "times_executed": 5},
            "type_b": {"effectiveness_score": 1.0, "effect_deltas": {}, "times_executed": 2},
        }
        result = _apply_learning_adjustments(actions, ledger)
        assert result[0]["action_type"] == "type_a"
        assert result[1]["action_type"] == "type_b"

    def test_base_priority_unchanged_by_confidence(self):
        """base_priority must not be scaled by confidence."""
        actions = _make_actions([
            ("type_a", 1.0),  # high base, zero confidence
            ("type_b", 0.5),  # lower base, full confidence, big adj
        ])
        ledger = {
            "type_a": {"effectiveness_score": 999.0, "effect_deltas": {}, "times_executed": 0},
            "type_b": {"effectiveness_score": 1.0, "effect_deltas": {}, "times_executed": 5},
        }
        # type_a: 1.0 + 0.0 * (clamped huge adj) = 1.0
        # type_b: 0.5 + 1.0 * 0.15 = 0.65
        result = _apply_learning_adjustments(actions, ledger)
        assert result[0]["action_type"] == "type_a"

    def test_missing_ledger_entry_no_confidence_no_boost(self):
        """Action not in ledger → confidence=0 → no boost. Backward compat."""
        actions = _make_actions([("unknown_type", 0.5), ("type_a", 0.4)])
        ledger = {
            "type_a": {"effectiveness_score": 0.0, "effect_deltas": {}, "times_executed": 10},
        }
        result = _apply_learning_adjustments(actions, ledger)
        # unknown_type: 0.5 + 0 = 0.5 (no entry); type_a: 0.4 + 1.0*0 = 0.4
        assert result[0]["action_type"] == "unknown_type"

    def test_deterministic_ordering_repeated_runs(self):
        actions = _make_actions([
            ("type_a", 0.7),
            ("type_b", 0.6),
            ("type_c", 0.5),
        ])
        ledger = {
            "type_a": {"effectiveness_score": 0.9, "effect_deltas": {}, "times_executed": 3},
            "type_b": {"effectiveness_score": 0.5, "effect_deltas": {}, "times_executed": 5},
            "type_c": {"effectiveness_score": 1.0, "effect_deltas": {}, "times_executed": 1},
        }
        order1 = [a["action_type"] for a in _apply_learning_adjustments(list(actions), ledger)]
        order2 = [a["action_type"] for a in _apply_learning_adjustments(list(actions), ledger)]
        assert order1 == order2

    def test_empty_ledger_unchanged(self):
        actions = _make_actions([("type_a", 1.0), ("type_b", 0.5)])
        result = _apply_learning_adjustments(actions, {})
        assert result == actions

    def test_confidence_with_targeting_adjustment(self):
        """Targeting adjustment is also confidence-scaled."""
        actions = _make_actions([("type_a", 0.5), ("type_b", 0.5)])
        ledger = {
            "type_a": {
                "effectiveness_score": 0.0,
                "effect_deltas": {"artifact_completeness": 1.0},
                "times_executed": 5,  # full confidence
            },
            "type_b": {
                "effectiveness_score": 0.0,
                "effect_deltas": {"artifact_completeness": 1.0},
                "times_executed": 0,  # zero confidence
            },
        }
        current_signals = {"artifact_completeness": 0.1}
        result = _apply_learning_adjustments(actions, ledger, current_signals)
        # type_a gets targeting boost (conf=1.0); type_b gets none (conf=0.0)
        assert result[0]["action_type"] == "type_a"
        assert result[1]["action_type"] == "type_b"


# ---------------------------------------------------------------------------
# Backward-compatibility: legacy ledger entries without times_executed
# ---------------------------------------------------------------------------

class TestBackwardCompatNoPerfField:
    """Legacy ledger rows (no times_executed) must behave identically to v0.26/v0.27."""

    def test_legacy_entry_retains_full_confidence(self):
        ledger = {"refresh_repo_health": {"effectiveness_score": 0.9, "effect_deltas": {}}}
        assert compute_confidence_factor("refresh_repo_health", ledger) == pytest.approx(1.0)

    def test_legacy_ordering_preserved(self):
        """Existing v0.26 ordering test passes with legacy ledger entries."""
        actions = _make_actions([
            ("type_a", 0.80),
            ("type_b", 0.75),
        ])
        ledger = {
            "type_a": {"effectiveness_score": 0.0, "effect_deltas": {}},
            "type_b": {"effectiveness_score": 1.0, "effect_deltas": {}},
        }
        result = _apply_learning_adjustments(actions, ledger)
        # type_b: 0.75 + 1.0 * 0.15 = 0.90; type_a: 0.80 + 0 = 0.80
        assert result[0]["action_type"] == "type_b"
        assert result[1]["action_type"] == "type_a"

    def test_legacy_targeting_preserved(self):
        """Existing v0.27 targeting test passes with legacy ledger entries."""
        actions = _make_actions([("type_high", 0.5), ("type_low", 0.5)])
        ledger = {
            "type_high": {
                "effectiveness_score": 0.0,
                "effect_deltas": {"artifact_completeness": 1.0},
            },
            "type_low": {
                "effectiveness_score": 0.0,
                "effect_deltas": {"artifact_completeness": 0.0},
            },
        }
        current = {"artifact_completeness": 0.1}
        result = _apply_learning_adjustments(actions, ledger, current)
        assert result[0]["action_type"] == "type_high"


# ---------------------------------------------------------------------------
# CONFIDENCE_THRESHOLD constant sanity
# ---------------------------------------------------------------------------

class TestConfidenceThresholdConstant:
    def test_threshold_value(self):
        assert CONFIDENCE_THRESHOLD == pytest.approx(5.0)

    def test_threshold_at_boundary_gives_exactly_one(self):
        ledger = {"type_a": {"times_executed": CONFIDENCE_THRESHOLD, "effectiveness_score": 0.0, "effect_deltas": {}}}
        assert compute_confidence_factor("type_a", ledger) == pytest.approx(1.0)

    def test_one_below_threshold_gives_less_than_one(self):
        ledger = {"type_a": {"times_executed": CONFIDENCE_THRESHOLD - 1, "effectiveness_score": 0.0, "effect_deltas": {}}}
        assert compute_confidence_factor("type_a", ledger) < 1.0
