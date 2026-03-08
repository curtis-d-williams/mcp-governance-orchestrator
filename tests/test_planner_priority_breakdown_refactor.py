# SPDX-License-Identifier: MIT
"""Regression tests for v0.32 PriorityBreakdown refactor.

Covers:
- PriorityBreakdown dataclass and _compute_priority_breakdown importable
- final_priority formula is exact (matches manual computation)
- _compute_priority_breakdown values match _build_priority_breakdown dicts
- ranking behavior matches v0.31 (sort order unchanged by refactor)
- deterministic repeated ordering
- no-ledger / no-policy behavior preserved
- breakdown to_dict() schema matches expected fields
- existing planner symbols still importable (backward-compat smoke check)
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
    EXPLORATION_CLAMP,
    EXPLORATION_WEIGHT,
    POLICY_TOTAL_ABS_CAP,
    POLICY_WEIGHT_CLAMP,
    SIGNAL_IMPACT_CLAMP,
    SIGNAL_IMPACT_WEIGHT,
    TARGETING_CLAMP,
    TARGETING_WEIGHT,
    PriorityBreakdown,
    _apply_learning_adjustments,
    _build_priority_breakdown,
    _compute_priority_breakdown,
    compute_confidence_factor,
    compute_exploration_bonus,
    compute_learning_adjustment,
    compute_policy_adjustment,
    compute_weak_signal_targeting_adjustment,
    load_effectiveness_ledger,
    load_planner_policy,
    load_portfolio_signals,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EXPECTED_DICT_FIELDS = {
    "action_type",
    "base_priority",
    "effectiveness_component",
    "signal_delta_component",
    "weak_signal_targeting_component",
    "policy_component",
    "confidence_factor",
    "exploration_component",
    "final_priority",
}


def _make_action(action_type, priority, action_id="aid-0", repo_id="repo-0"):
    return {
        "action_type": action_type,
        "priority": priority,
        "action_id": action_id,
        "repo_id": repo_id,
    }


def _make_actions(specs):
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
# PriorityBreakdown dataclass — structure and field presence
# ---------------------------------------------------------------------------

class TestPriorityBreakdownDataclass:
    def test_importable(self):
        assert PriorityBreakdown is not None

    def test_instantiation(self):
        bd = PriorityBreakdown(
            action_type="test",
            base_priority=1.0,
            effectiveness_component=0.1,
            signal_delta_component=0.05,
            weak_signal_targeting_component=0.02,
            policy_component=0.03,
            confidence_factor=1.0,
            exploration_component=0.04,
            final_priority=1.24,
        )
        assert bd.action_type == "test"
        assert bd.base_priority == pytest.approx(1.0)
        assert bd.final_priority == pytest.approx(1.24)

    def test_to_dict_returns_expected_fields(self):
        bd = PriorityBreakdown(
            action_type="type_a",
            base_priority=0.5,
            effectiveness_component=0.1,
            signal_delta_component=0.05,
            weak_signal_targeting_component=0.02,
            policy_component=0.03,
            confidence_factor=0.8,
            exploration_component=0.04,
            final_priority=0.74,
        )
        d = bd.to_dict()
        assert set(d.keys()) == _EXPECTED_DICT_FIELDS

    def test_to_dict_rounds_to_six_decimal_places(self):
        bd = PriorityBreakdown(
            action_type="type_a",
            base_priority=1.0 / 3.0,
            effectiveness_component=0.0,
            signal_delta_component=0.0,
            weak_signal_targeting_component=0.0,
            policy_component=0.0,
            confidence_factor=1.0,
            exploration_component=0.0,
            final_priority=1.0 / 3.0,
        )
        d = bd.to_dict()
        assert d["base_priority"] == round(1.0 / 3.0, 6)
        assert d["final_priority"] == round(1.0 / 3.0, 6)

    def test_to_dict_action_type_is_string(self):
        bd = PriorityBreakdown(
            action_type="my_type",
            base_priority=0.0,
            effectiveness_component=0.0,
            signal_delta_component=0.0,
            weak_signal_targeting_component=0.0,
            policy_component=0.0,
            confidence_factor=0.0,
            exploration_component=0.0,
            final_priority=0.0,
        )
        assert isinstance(bd.to_dict()["action_type"], str)


# ---------------------------------------------------------------------------
# _compute_priority_breakdown — single-action builder
# ---------------------------------------------------------------------------

class TestComputePriorityBreakdown:
    def _standard_ledger(self):
        return {
            "type_a": _ledger_entry(
                effectiveness_score=1.0,
                effect_deltas={"sig_x": 0.4},
                times_executed=10,
            ),
        }

    def test_returns_priority_breakdown_instance(self):
        action = _make_action("type_a", 0.7)
        ledger = self._standard_ledger()
        result = _compute_priority_breakdown(action, ledger, {}, {})
        assert isinstance(result, PriorityBreakdown)

    def test_action_type_matches_input(self):
        action = _make_action("type_a", 0.7)
        ledger = self._standard_ledger()
        bd = _compute_priority_breakdown(action, ledger, {}, {})
        assert bd.action_type == "type_a"

    def test_base_priority_matches_action(self):
        action = _make_action("type_a", 0.7)
        ledger = self._standard_ledger()
        bd = _compute_priority_breakdown(action, ledger, {}, {})
        assert bd.base_priority == pytest.approx(0.7)

    def test_confidence_factor_range(self):
        action = _make_action("type_a", 0.7)
        ledger = self._standard_ledger()
        bd = _compute_priority_breakdown(action, ledger, {}, {})
        assert 0.0 <= bd.confidence_factor <= 1.0

    def test_final_priority_formula_exact(self):
        """final_priority == base + sum(weighted_components) + exploration."""
        action = _make_action("type_a", 0.7)
        ledger = self._standard_ledger()
        bd = _compute_priority_breakdown(action, ledger, {}, {})
        expected = (
            bd.base_priority
            + bd.effectiveness_component
            + bd.signal_delta_component
            + bd.weak_signal_targeting_component
            + bd.policy_component
            + bd.exploration_component
        )
        assert bd.final_priority == pytest.approx(expected, rel=1e-9)

    def test_no_ledger_zero_learning_components(self):
        action = _make_action("type_x", 0.5)
        bd = _compute_priority_breakdown(action, {}, {}, {})
        assert bd.effectiveness_component == pytest.approx(0.0)
        assert bd.signal_delta_component == pytest.approx(0.0)
        assert bd.weak_signal_targeting_component == pytest.approx(0.0)
        assert bd.policy_component == pytest.approx(0.0)
        assert bd.confidence_factor == pytest.approx(0.0)

    def test_no_ledger_exploration_nonzero(self):
        """Missing ledger entry → times_executed=0 → max exploration bonus."""
        action = _make_action("type_x", 0.5)
        bd = _compute_priority_breakdown(action, {}, {}, {})
        expected_exploration = min(
            max(-EXPLORATION_CLAMP, 1.0 / (1.0 + 0) * EXPLORATION_WEIGHT),
            EXPLORATION_CLAMP,
        )
        assert bd.exploration_component == pytest.approx(expected_exploration)

    def test_no_policy_zero_policy_component(self):
        action = _make_action("type_a", 0.7)
        ledger = self._standard_ledger()
        bd = _compute_priority_breakdown(action, ledger, {}, {})
        assert bd.policy_component == pytest.approx(0.0)

    def test_policy_component_nonzero_when_policy_provided(self):
        action = _make_action("type_a", 0.7)
        ledger = {"type_a": _ledger_entry(effect_deltas={"sig_x": 1.0}, times_executed=10)}
        policy = {"sig_x": 2.0}
        bd = _compute_priority_breakdown(action, ledger, {}, policy)
        assert bd.policy_component != pytest.approx(0.0)

    def test_deterministic_repeated_calls(self):
        action = _make_action("type_a", 0.7)
        ledger = self._standard_ledger()
        bd1 = _compute_priority_breakdown(action, ledger, {}, {})
        bd2 = _compute_priority_breakdown(action, ledger, {}, {})
        assert bd1 == bd2

    def test_does_not_mutate_action(self):
        action = _make_action("type_a", 0.7)
        original_keys = set(action.keys())
        ledger = self._standard_ledger()
        _compute_priority_breakdown(action, ledger, {}, {})
        assert set(action.keys()) == original_keys

    def test_does_not_mutate_ledger(self):
        action = _make_action("type_a", 0.7)
        ledger = self._standard_ledger()
        original_keys = set(ledger.keys())
        _compute_priority_breakdown(action, ledger, {}, {})
        assert set(ledger.keys()) == original_keys


# ---------------------------------------------------------------------------
# Verify _compute_priority_breakdown values match _build_priority_breakdown
# ---------------------------------------------------------------------------

class TestComputeMatchesBuildList:
    """The single-action builder and the list-level breakdown must agree."""

    def _setup(self):
        actions = _make_actions([
            ("type_a", 0.7),
            ("type_b", 0.5),
            ("type_c", 0.3),
        ])
        ledger = {
            "type_a": _ledger_entry(
                effectiveness_score=1.0,
                effect_deltas={"sig_x": 0.4, "sig_y": 0.2},
                times_executed=10,
            ),
            "type_b": _ledger_entry(
                effectiveness_score=0.5,
                effect_deltas={"sig_x": 0.2},
                times_executed=5,
            ),
            "type_c": _ledger_entry(
                effectiveness_score=0.0,
                effect_deltas={},
                times_executed=0,
            ),
        }
        signals = {"sig_x": 0.3, "sig_y": 0.8}
        policy = {"sig_x": 1.5}
        return actions, ledger, signals, policy

    def test_field_values_match_per_action(self):
        actions, ledger, signals, policy = self._setup()
        list_result = _build_priority_breakdown(actions, ledger, signals, policy)
        for i, action in enumerate(actions):
            bd = _compute_priority_breakdown(action, ledger, signals, policy)
            d = bd.to_dict()
            for field in _EXPECTED_DICT_FIELDS:
                assert d[field] == list_result[i][field], (
                    f"Mismatch for {action['action_type']}.{field}: "
                    f"single={d[field]}, list={list_result[i][field]}"
                )

    def test_final_priority_matches_across_both_paths(self):
        actions, ledger, signals, policy = self._setup()
        list_result = _build_priority_breakdown(actions, ledger, signals, policy)
        for i, action in enumerate(actions):
            bd = _compute_priority_breakdown(action, ledger, signals, policy)
            assert round(bd.final_priority, 6) == list_result[i]["final_priority"]

    def test_confidence_factor_matches(self):
        actions, ledger, signals, policy = self._setup()
        list_result = _build_priority_breakdown(actions, ledger, signals, policy)
        for i, action in enumerate(actions):
            bd = _compute_priority_breakdown(action, ledger, signals, policy)
            assert round(bd.confidence_factor, 6) == list_result[i]["confidence_factor"]


# ---------------------------------------------------------------------------
# Ranking behavior matches v0.31 (sort order unchanged by refactor)
# ---------------------------------------------------------------------------

class TestRankingMatchesV031:
    """_apply_learning_adjustments must produce the same order as before the refactor.

    The expected orders below were computed by direct application of the
    v0.31 formulas and are locked as regression anchors.
    """

    def _base_ledger(self):
        return {
            "type_high": _ledger_entry(
                effectiveness_score=1.0,
                effect_deltas={"artifact_completeness": 1.0},
                times_executed=10,
            ),
            "type_low": _ledger_entry(
                effectiveness_score=0.0,
                effect_deltas={"artifact_completeness": 0.1},
                times_executed=10,
            ),
        }

    def test_higher_effectiveness_ranks_first(self):
        actions = _make_actions([("type_low", 0.5), ("type_high", 0.5)])
        ledger = self._base_ledger()
        result = _apply_learning_adjustments(actions, ledger)
        assert result[0]["action_type"] == "type_high"
        assert result[1]["action_type"] == "type_low"

    def test_higher_base_priority_ranks_first_when_ledger_equal(self):
        ledger = {
            "type_a": _ledger_entry(times_executed=10),
            "type_b": _ledger_entry(times_executed=10),
        }
        actions = _make_actions([("type_a", 0.5), ("type_b", 0.9)])
        result = _apply_learning_adjustments(actions, ledger)
        assert result[0]["action_type"] == "type_b"

    def test_policy_weight_affects_ordering(self):
        actions = _make_actions([("type_high", 0.5), ("type_low", 0.5)])
        ledger = self._base_ledger()
        policy = {"artifact_completeness": 5.0}
        result = _apply_learning_adjustments(actions, ledger, policy=policy)
        assert result[0]["action_type"] == "type_high"
        assert result[1]["action_type"] == "type_low"

    def test_negative_policy_inverts_order(self):
        actions = _make_actions([("type_high", 0.5), ("type_low", 0.5)])
        ledger = self._base_ledger()
        # Without policy, type_high ranks first (larger effect delta)
        no_policy = _apply_learning_adjustments(list(actions), ledger)
        assert no_policy[0]["action_type"] == "type_high"
        # With large negative weight, type_high gets penalized more
        policy = {"artifact_completeness": -5.0}
        with_policy = _apply_learning_adjustments(list(actions), ledger, policy=policy)
        assert with_policy[0]["action_type"] == "type_low"

    def test_tiebreaker_alphabetical_action_type(self):
        """Equal priority → tiebreaker is action_type ascending."""
        ledger = {
            "type_b": _ledger_entry(times_executed=10),
            "type_a": _ledger_entry(times_executed=10),
        }
        actions = _make_actions([("type_b", 0.5), ("type_a", 0.5)])
        result = _apply_learning_adjustments(actions, ledger)
        assert result[0]["action_type"] == "type_a"
        assert result[1]["action_type"] == "type_b"

    def test_zero_confidence_policy_no_effect(self):
        """times_executed=0 → confidence=0 → policy_adj scaled to 0 → tiebreak alphabetical."""
        ledger = {
            "type_b": _ledger_entry(effect_deltas={"sig": 10.0}, times_executed=0),
            "type_a": _ledger_entry(effect_deltas={"sig": 0.1}, times_executed=0),
        }
        actions = _make_actions([("type_b", 0.5), ("type_a", 0.5)])
        policy = {"sig": 5.0}
        result = _apply_learning_adjustments(actions, ledger, policy=policy)
        assert result[0]["action_type"] == "type_a"
        assert result[1]["action_type"] == "type_b"

    def test_empty_ledger_returns_unchanged(self):
        actions = _make_actions([("type_b", 0.7), ("type_a", 0.5)])
        result = _apply_learning_adjustments(actions, {})
        assert result is actions

    def test_ranking_consistent_with_compute_final_priority(self):
        """Ranking order must match descending final_priority from _compute_priority_breakdown."""
        actions = _make_actions([
            ("type_a", 0.3),
            ("type_b", 0.7),
            ("type_c", 0.5),
        ])
        ledger = {
            "type_a": _ledger_entry(effectiveness_score=1.0, times_executed=10),
            "type_b": _ledger_entry(effectiveness_score=0.5, times_executed=10),
            "type_c": _ledger_entry(effectiveness_score=0.0, times_executed=10),
        }
        policy = {}
        signals = {}
        sorted_actions = _apply_learning_adjustments(list(actions), ledger, signals, policy)
        finals = [
            _compute_priority_breakdown(a, ledger, signals, policy).final_priority
            for a in sorted_actions
        ]
        # Each successive final_priority must be <= previous
        for i in range(len(finals) - 1):
            assert finals[i] >= finals[i + 1] or (
                # Equal values may be tied and resolved by tiebreaker
                finals[i] == pytest.approx(finals[i + 1])
            )


# ---------------------------------------------------------------------------
# Deterministic repeated ordering
# ---------------------------------------------------------------------------

class TestDeterministicOrdering:
    def test_repeated_ranking_identical(self):
        actions = _make_actions([
            ("type_c", 0.3),
            ("type_a", 0.7),
            ("type_b", 0.5),
        ])
        ledger = {
            "type_a": _ledger_entry(effectiveness_score=0.8, times_executed=7),
            "type_b": _ledger_entry(effectiveness_score=1.0, times_executed=3),
            "type_c": _ledger_entry(effectiveness_score=0.5, times_executed=10),
        }
        policy = {"sig": 1.0}
        order1 = [a["action_type"] for a in _apply_learning_adjustments(
            list(actions), ledger, policy=policy
        )]
        order2 = [a["action_type"] for a in _apply_learning_adjustments(
            list(actions), ledger, policy=policy
        )]
        assert order1 == order2

    def test_repeated_compute_breakdown_identical(self):
        action = _make_action("type_a", 0.7)
        ledger = {"type_a": _ledger_entry(effectiveness_score=1.0, times_executed=5)}
        policy = {"sig": 0.5}
        bd1 = _compute_priority_breakdown(action, ledger, {}, policy)
        bd2 = _compute_priority_breakdown(action, ledger, {}, policy)
        assert bd1 == bd2

    def test_repeated_build_list_identical(self):
        actions = _make_actions([("type_a", 0.8), ("type_b", 0.6)])
        ledger = {
            "type_a": _ledger_entry(effectiveness_score=1.0, times_executed=10),
            "type_b": _ledger_entry(effectiveness_score=0.5, times_executed=5),
        }
        r1 = _build_priority_breakdown(actions, ledger, {}, {})
        r2 = _build_priority_breakdown(actions, ledger, {}, {})
        assert r1 == r2


# ---------------------------------------------------------------------------
# No-ledger / no-policy behavior preserved
# ---------------------------------------------------------------------------

class TestNoLedgerNoPolicyBehavior:
    def test_no_ledger_apply_returns_unchanged(self):
        actions = _make_actions([("type_b", 0.9), ("type_a", 0.1)])
        result = _apply_learning_adjustments(actions, {})
        assert result is actions

    def test_no_ledger_build_breakdown_zero_components(self):
        actions = _make_actions([("type_x", 0.5), ("type_y", 0.3)])
        result = _build_priority_breakdown(actions, {}, {}, {})
        for entry in result:
            assert entry["effectiveness_component"] == pytest.approx(0.0)
            assert entry["signal_delta_component"] == pytest.approx(0.0)
            assert entry["weak_signal_targeting_component"] == pytest.approx(0.0)
            assert entry["policy_component"] == pytest.approx(0.0)
            assert entry["confidence_factor"] == pytest.approx(0.0)

    def test_no_policy_zero_policy_component_in_breakdown(self):
        actions = _make_actions([("type_a", 0.7)])
        ledger = {"type_a": _ledger_entry(effect_deltas={"sig": 1.0}, times_executed=10)}
        result = _build_priority_breakdown(actions, ledger, {}, {})
        assert result[0]["policy_component"] == pytest.approx(0.0)

    def test_no_signals_zero_targeting_component(self):
        actions = _make_actions([("type_a", 0.7)])
        ledger = {"type_a": _ledger_entry(effect_deltas={"sig": 1.0}, times_executed=10)}
        result = _build_priority_breakdown(actions, ledger, {}, {})
        assert result[0]["weak_signal_targeting_component"] == pytest.approx(0.0)

    def test_none_signals_equivalent_to_empty(self):
        action = _make_action("type_a", 0.7)
        ledger = {"type_a": _ledger_entry(effect_deltas={"sig": 1.0}, times_executed=10)}
        bd_empty = _compute_priority_breakdown(action, ledger, {}, {})
        bd_none_via_list = _build_priority_breakdown([action], ledger, None, None)
        assert round(bd_empty.final_priority, 6) == bd_none_via_list[0]["final_priority"]

    def test_empty_actions_returns_empty_list(self):
        result = _build_priority_breakdown([], {}, {}, {})
        assert result == []

    def test_no_ledger_exploration_uses_zero_times_executed(self):
        """Missing ledger → times_executed=0 → exploration = EXPLORATION_WEIGHT (clamped)."""
        action = _make_action("type_x", 0.0)
        bd = _compute_priority_breakdown(action, {}, {}, {})
        expected = min(EXPLORATION_WEIGHT, EXPLORATION_CLAMP)
        assert bd.exploration_component == pytest.approx(expected)

    def test_final_priority_equals_base_plus_exploration_when_no_ledger(self):
        action = _make_action("type_x", 0.5)
        bd = _compute_priority_breakdown(action, {}, {}, {})
        assert bd.final_priority == pytest.approx(bd.base_priority + bd.exploration_component)


# ---------------------------------------------------------------------------
# Backward-compat smoke check: existing symbols still importable
# ---------------------------------------------------------------------------

class TestBackwardCompatImports:
    def test_all_v026_through_v031_symbols_importable(self):
        from scripts.claude_dynamic_planner_loop import (  # noqa: F401
            CONFIDENCE_THRESHOLD,
            EFFECTIVENESS_CLAMP,
            EFFECTIVENESS_WEIGHT,
            EXPLORATION_CLAMP,
            EXPLORATION_WEIGHT,
            POLICY_TOTAL_ABS_CAP,
            POLICY_WEIGHT_CLAMP,
            SIGNAL_IMPACT_CLAMP,
            SIGNAL_IMPACT_WEIGHT,
            TARGETING_CLAMP,
            TARGETING_WEIGHT,
            _apply_learning_adjustments,
            _build_priority_breakdown,
            compute_confidence_factor,
            compute_exploration_bonus,
            compute_learning_adjustment,
            compute_policy_adjustment,
            compute_weak_signal_targeting_adjustment,
            load_effectiveness_ledger,
            load_planner_policy,
            load_portfolio_signals,
        )

    def test_v032_symbols_importable(self):
        from scripts.claude_dynamic_planner_loop import (  # noqa: F401
            PriorityBreakdown,
            _compute_priority_breakdown,
        )
