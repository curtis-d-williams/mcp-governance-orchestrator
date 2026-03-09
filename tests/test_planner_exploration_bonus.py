# SPDX-License-Identifier: MIT
"""Regression tests for v0.29 planner uncertainty-driven exploration bonus.

Covers:
- zero executions produce highest exploration bonus
- higher executions reduce bonus
- bonus bounded within ±EXPLORATION_CLAMP
- deterministic ordering with exploration bonus
- missing ledger entry assumes times_executed = 0
- existing v0.26, v0.27, v0.28 tests still pass (import check only here;
  full compat verified by running earlier test modules)
"""
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.claude_dynamic_planner_loop import (  # noqa: E402
    EXPLORATION_CLAMP,
    EXPLORATION_WEIGHT,
    _apply_learning_adjustments,
    compute_exploration_bonus,
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


def _ledger_entry(times_executed, effectiveness_score=0.0, effect_deltas=None):
    entry = {
        "effectiveness_score": effectiveness_score,
        "effect_deltas": effect_deltas or {},
    }
    if times_executed is not None:
        entry["times_executed"] = times_executed
    return entry


# ---------------------------------------------------------------------------
# compute_exploration_bonus – unit tests
# ---------------------------------------------------------------------------

class TestComputeExplorationBonus:
    def test_zero_executions_gives_maximum_bonus(self):
        # uncertainty = 1/(1+0) = 1.0; bonus = 1.0 * EXPLORATION_WEIGHT
        ledger = {"type_a": _ledger_entry(times_executed=0)}
        bonus = compute_exploration_bonus("type_a", ledger)
        expected = min(EXPLORATION_CLAMP, 1.0 * EXPLORATION_WEIGHT)
        assert bonus == pytest.approx(expected)

    def test_higher_executions_reduce_bonus(self):
        ledger_0 = {"type_a": _ledger_entry(times_executed=0)}
        ledger_5 = {"type_a": _ledger_entry(times_executed=5)}
        ledger_50 = {"type_a": _ledger_entry(times_executed=50)}
        b0 = compute_exploration_bonus("type_a", ledger_0)
        b5 = compute_exploration_bonus("type_a", ledger_5)
        b50 = compute_exploration_bonus("type_a", ledger_50)
        assert b0 > b5 > b50

    def test_bonus_never_exceeds_clamp(self):
        for te in [0, 1, 2, 5, 10, 100, 1000]:
            ledger = {"type_a": _ledger_entry(times_executed=te)}
            bonus = compute_exploration_bonus("type_a", ledger)
            assert bonus <= EXPLORATION_CLAMP, f"bonus {bonus} exceeds clamp at te={te}"

    def test_bonus_never_below_negative_clamp(self):
        for te in [0, 1, 5, 100]:
            ledger = {"type_a": _ledger_entry(times_executed=te)}
            bonus = compute_exploration_bonus("type_a", ledger)
            assert bonus >= -EXPLORATION_CLAMP

    def test_missing_ledger_entry_assumes_zero_executions(self):
        # Missing entry → times_executed=0 → same bonus as explicit 0
        bonus_missing = compute_exploration_bonus("unknown_type", {})
        ledger = {"type_a": _ledger_entry(times_executed=0)}
        bonus_zero = compute_exploration_bonus("type_a", ledger)
        assert bonus_missing == pytest.approx(bonus_zero)

    def test_missing_times_executed_field_assumes_zero(self):
        # Row present but times_executed key absent → treat as 0
        ledger = {"type_a": {"effectiveness_score": 0.9, "effect_deltas": {}}}
        bonus = compute_exploration_bonus("type_a", ledger)
        ledger_zero = {"type_a": _ledger_entry(times_executed=0)}
        expected = compute_exploration_bonus("type_a", ledger_zero)
        assert bonus == pytest.approx(expected)

    def test_invalid_times_executed_treated_as_zero(self):
        ledger = {"type_a": {"times_executed": "bad", "effectiveness_score": 0.0, "effect_deltas": {}}}
        bonus = compute_exploration_bonus("type_a", ledger)
        ledger_zero = {"type_a": _ledger_entry(times_executed=0)}
        expected = compute_exploration_bonus("type_a", ledger_zero)
        assert bonus == pytest.approx(expected)

    def test_negative_times_executed_treated_as_zero(self):
        ledger = {"type_a": _ledger_entry(times_executed=-5)}
        bonus = compute_exploration_bonus("type_a", ledger)
        ledger_zero = {"type_a": _ledger_entry(times_executed=0)}
        expected = compute_exploration_bonus("type_a", ledger_zero)
        assert bonus == pytest.approx(expected)

    def test_deterministic_repeated_calls(self):
        ledger = {"type_a": _ledger_entry(times_executed=3)}
        b1 = compute_exploration_bonus("type_a", ledger)
        b2 = compute_exploration_bonus("type_a", ledger)
        assert b1 == b2

    def test_bonus_formula_correctness(self):
        # uncertainty = 1/(1+4) = 0.2; bonus = 0.2 * EXPLORATION_WEIGHT
        ledger = {"type_a": _ledger_entry(times_executed=4)}
        bonus = compute_exploration_bonus("type_a", ledger)
        expected = (1.0 / 5.0) * EXPLORATION_WEIGHT
        assert bonus == pytest.approx(expected)

    def test_constants_values(self):
        assert EXPLORATION_WEIGHT == pytest.approx(0.05)
        assert EXPLORATION_CLAMP == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# Ordering with exploration bonus
# ---------------------------------------------------------------------------

class TestExplorationBonusOrdering:
    def test_zero_executions_action_gets_bonus_boost(self):
        """Rarely executed action gets exploration boost that can change ordering."""
        actions = _make_actions([
            ("type_a", 0.50),  # many executions → low bonus
            ("type_b", 0.45),  # zero executions → max bonus
        ])
        # type_a: 50 executions → uncertainty=1/51≈0.0196, bonus≈0.00098
        # type_b: 0 executions  → uncertainty=1/1=1.0,    bonus=0.05
        # Difference: type_b 0.45 + 0.05 = 0.50 vs type_a 0.50 + ~0.001 = 0.501
        # type_a still higher, but adding learning adj shifts things
        # Use a case where bonus clearly changes ordering:
        # type_a: priority=0.50, te=100  → bonus=1/101*0.05≈0.000495
        # type_b: priority=0.50, te=0    → bonus=1/1*0.05=0.05
        actions2 = _make_actions([
            ("type_a", 0.50),
            ("type_b", 0.50),
        ])
        ledger = {
            "type_a": _ledger_entry(times_executed=100),
            "type_b": _ledger_entry(times_executed=0),
        }
        result = _apply_learning_adjustments(actions2, ledger)
        assert result[0]["action_type"] == "type_b"
        assert result[1]["action_type"] == "type_a"

    def test_deterministic_ordering_repeated_runs(self):
        actions = _make_actions([
            ("type_a", 0.7),
            ("type_b", 0.6),
            ("type_c", 0.5),
        ])
        ledger = {
            "type_a": _ledger_entry(times_executed=10),
            "type_b": _ledger_entry(times_executed=0),
            "type_c": _ledger_entry(times_executed=3),
        }
        order1 = [a["action_type"] for a in _apply_learning_adjustments(list(actions), ledger)]
        order2 = [a["action_type"] for a in _apply_learning_adjustments(list(actions), ledger)]
        assert order1 == order2

    def test_exploration_bonus_additive_does_not_break_high_base_priority(self):
        """Exploration bonus is small: a large base_priority gap still dominates."""
        actions = _make_actions([
            ("type_a", 1.0),   # high base, many executions
            ("type_b", 0.1),   # low base, zero executions
        ])
        ledger = {
            "type_a": _ledger_entry(times_executed=100),
            "type_b": _ledger_entry(times_executed=0),
        }
        result = _apply_learning_adjustments(actions, ledger)
        # type_a: 1.0 + 0 + ~0.0005 ≈ 1.0005
        # type_b: 0.1 + 0 + 0.05 = 0.15
        assert result[0]["action_type"] == "type_a"

    def test_missing_ledger_entry_gets_max_exploration(self):
        """Action absent from ledger gets same bonus as times_executed=0."""
        actions = _make_actions([
            ("known_type", 0.50),    # te=50, low bonus
            ("unknown_type", 0.50),  # not in ledger → te=0, max bonus
        ])
        ledger = {
            "known_type": _ledger_entry(times_executed=50),
        }
        result = _apply_learning_adjustments(actions, ledger)
        # unknown_type: 0.50 + 0.05 = 0.55; known_type: 0.50 + ~0.001 = 0.501
        assert result[0]["action_type"] == "unknown_type"

    def test_tiebreak_alphabetical_when_bonuses_equal(self):
        """Equal priorities and equal bonuses → tiebreak by action_type alphabetical."""
        actions = _make_actions([
            ("type_z", 0.5),
            ("type_a", 0.5),
        ])
        # Same times_executed → same bonus
        ledger = {
            "type_z": _ledger_entry(times_executed=5),
            "type_a": _ledger_entry(times_executed=5),
        }
        result = _apply_learning_adjustments(actions, ledger)
        assert result[0]["action_type"] == "type_a"
        assert result[1]["action_type"] == "type_z"
