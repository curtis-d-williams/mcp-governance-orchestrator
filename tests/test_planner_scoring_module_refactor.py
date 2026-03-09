# SPDX-License-Identifier: MIT
"""Regression tests for v0.33 planner scoring module extraction.

Covers:
- scripts.planner_scoring imports work (new module)
- ranking behavior matches v0.32 exactly (no formula change)
- explain output (breakdown dicts) still matches breakdown values
- no-ledger / no-policy behavior preserved
- existing planner tests still pass (backward-compat import smoke)
- scoring results from planner_scoring equal results from the loop re-exports
"""
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ---------------------------------------------------------------------------
# Helpers shared across test classes
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 1. New module imports
# ---------------------------------------------------------------------------

class TestNewModuleImports:
    """All public symbols must be importable directly from planner_scoring."""

    def test_constants_importable(self):
        from scripts.planner_scoring import (  # noqa: F401
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
        )

    def test_dataclass_importable(self):
        from scripts.planner_scoring import PriorityBreakdown  # noqa: F401
        assert PriorityBreakdown is not None

    def test_loaders_importable(self):
        from scripts.planner_scoring import (  # noqa: F401
            load_effectiveness_ledger,
            load_planner_policy,
            load_portfolio_signals,
        )

    def test_helpers_importable(self):
        from scripts.planner_scoring import (  # noqa: F401
            compute_confidence_factor,
            compute_exploration_bonus,
            compute_learning_adjustment,
            compute_policy_adjustment,
            compute_weak_signal_targeting_adjustment,
        )

    def test_builders_importable(self):
        from scripts.planner_scoring import (  # noqa: F401
            _apply_learning_adjustments,
            _build_priority_breakdown,
            _compute_priority_breakdown,
        )


# ---------------------------------------------------------------------------
# 2. Backward-compat: all symbols still importable from loop module
# ---------------------------------------------------------------------------

class TestLoopModuleBackwardCompatImports:
    """Re-exports in claude_dynamic_planner_loop must satisfy all v0.26–v0.32 imports."""

    def test_all_scoring_symbols_re_exported(self):
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

    def test_loop_symbols_still_present(self):
        """Non-scoring loop symbols must still be present."""
        from scripts.claude_dynamic_planner_loop import (  # noqa: F401
            ACTION_TO_TASK,
            ALL_TASKS,
            main,
        )


# ---------------------------------------------------------------------------
# 3. Ranking behavior matches v0.32 exactly
# ---------------------------------------------------------------------------

class TestRankingMatchesV032:
    """Ranking produced by the extracted module must equal v0.32 ranking."""

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
        from scripts.planner_scoring import _apply_learning_adjustments
        actions = _make_actions([("type_low", 0.5), ("type_high", 0.5)])
        result = _apply_learning_adjustments(actions, self._base_ledger())
        assert result[0]["action_type"] == "type_high"
        assert result[1]["action_type"] == "type_low"

    def test_higher_base_priority_ranks_first_when_scores_equal(self):
        from scripts.planner_scoring import _apply_learning_adjustments
        ledger = {
            "type_a": _ledger_entry(times_executed=10),
            "type_b": _ledger_entry(times_executed=10),
        }
        actions = _make_actions([("type_a", 0.5), ("type_b", 0.9)])
        result = _apply_learning_adjustments(actions, ledger)
        assert result[0]["action_type"] == "type_b"

    def test_tiebreaker_alphabetical(self):
        from scripts.planner_scoring import _apply_learning_adjustments
        ledger = {
            "type_b": _ledger_entry(times_executed=10),
            "type_a": _ledger_entry(times_executed=10),
        }
        actions = _make_actions([("type_b", 0.5), ("type_a", 0.5)])
        result = _apply_learning_adjustments(actions, ledger)
        assert result[0]["action_type"] == "type_a"

    def test_empty_ledger_returns_unchanged(self):
        from scripts.planner_scoring import _apply_learning_adjustments
        actions = _make_actions([("type_b", 0.7), ("type_a", 0.5)])
        result = _apply_learning_adjustments(actions, {})
        assert result is actions

    def test_policy_affects_ordering(self):
        from scripts.planner_scoring import _apply_learning_adjustments
        actions = _make_actions([("type_high", 0.5), ("type_low", 0.5)])
        policy = {"artifact_completeness": 5.0}
        result = _apply_learning_adjustments(actions, self._base_ledger(), policy=policy)
        assert result[0]["action_type"] == "type_high"

    def test_negative_policy_inverts_order(self):
        from scripts.planner_scoring import _apply_learning_adjustments
        actions = _make_actions([("type_high", 0.5), ("type_low", 0.5)])
        policy = {"artifact_completeness": -5.0}
        result = _apply_learning_adjustments(list(actions), self._base_ledger(), policy=policy)
        assert result[0]["action_type"] == "type_low"

    def test_scoring_module_and_loop_produce_identical_ranking(self):
        """Both import paths must yield bit-identical ranking."""
        from scripts.planner_scoring import _apply_learning_adjustments as scoring_rank
        from scripts.claude_dynamic_planner_loop import _apply_learning_adjustments as loop_rank
        actions = _make_actions([
            ("type_a", 0.3), ("type_b", 0.7), ("type_c", 0.5),
        ])
        ledger = {
            "type_a": _ledger_entry(effectiveness_score=1.0, times_executed=10),
            "type_b": _ledger_entry(effectiveness_score=0.5, times_executed=10),
            "type_c": _ledger_entry(effectiveness_score=0.0, times_executed=10),
        }
        r_scoring = [a["action_type"] for a in scoring_rank(list(actions), ledger)]
        r_loop = [a["action_type"] for a in loop_rank(list(actions), ledger)]
        assert r_scoring == r_loop


# ---------------------------------------------------------------------------
# 4. Explain output matches breakdown values (schema + arithmetic)
# ---------------------------------------------------------------------------

class TestExplainOutputMatchesBreakdown:
    """_build_priority_breakdown schema and arithmetic must be unchanged."""

    def _setup(self):
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

    def test_breakdown_dict_has_all_expected_fields(self):
        from scripts.planner_scoring import _build_priority_breakdown
        actions, ledger = self._setup()
        result = _build_priority_breakdown(actions, ledger, {}, {})
        for entry in result:
            assert set(entry.keys()) == _EXPECTED_DICT_FIELDS

    def test_final_priority_equals_sum_of_components(self):
        from scripts.planner_scoring import _build_priority_breakdown
        actions, ledger = self._setup()
        result = _build_priority_breakdown(actions, ledger, {}, {})
        for entry in result:
            expected = (
                entry["base_priority"]
                + entry["effectiveness_component"]
                + entry["signal_delta_component"]
                + entry["weak_signal_targeting_component"]
                + entry["policy_component"]
                + entry["exploration_component"]
            )
            assert entry["final_priority"] == pytest.approx(expected, rel=1e-9)

    def test_single_action_builder_matches_list_builder(self):
        """_compute_priority_breakdown.to_dict() must equal _build_priority_breakdown entry."""
        from scripts.planner_scoring import _build_priority_breakdown, _compute_priority_breakdown
        actions, ledger = self._setup()
        list_result = _build_priority_breakdown(actions, ledger, {}, {})
        for i, action in enumerate(actions):
            bd = _compute_priority_breakdown(action, ledger, {}, {})
            d = bd.to_dict()
            for field in _EXPECTED_DICT_FIELDS:
                assert d[field] == list_result[i][field], (
                    f"Mismatch on {action['action_type']}.{field}: "
                    f"single={d[field]}, list={list_result[i][field]}"
                )

    def test_breakdown_results_identical_from_both_import_paths(self):
        """scoring module and loop re-export must produce identical breakdown."""
        from scripts.planner_scoring import _build_priority_breakdown as scoring_bd
        from scripts.claude_dynamic_planner_loop import _build_priority_breakdown as loop_bd
        actions, ledger = self._setup()
        r_scoring = scoring_bd(actions, ledger, {}, {})
        r_loop = loop_bd(actions, ledger, {}, {})
        assert r_scoring == r_loop


# ---------------------------------------------------------------------------
# 5. No-ledger / no-policy behavior preserved
# ---------------------------------------------------------------------------

class TestNoLedgerNoPolicyPreserved:
    def test_no_ledger_apply_returns_unchanged(self):
        from scripts.planner_scoring import _apply_learning_adjustments
        actions = _make_actions([("type_b", 0.9), ("type_a", 0.1)])
        result = _apply_learning_adjustments(actions, {})
        assert result is actions

    def test_no_ledger_breakdown_zero_learning_components(self):
        from scripts.planner_scoring import _build_priority_breakdown
        actions = _make_actions([("type_x", 0.5), ("type_y", 0.3)])
        result = _build_priority_breakdown(actions, {}, {}, {})
        for entry in result:
            assert entry["effectiveness_component"] == pytest.approx(0.0)
            assert entry["signal_delta_component"] == pytest.approx(0.0)
            assert entry["weak_signal_targeting_component"] == pytest.approx(0.0)
            assert entry["policy_component"] == pytest.approx(0.0)
            assert entry["confidence_factor"] == pytest.approx(0.0)

    def test_no_ledger_exploration_uses_zero_times_executed(self):
        from scripts.planner_scoring import (
            EXPLORATION_CLAMP, EXPLORATION_WEIGHT, _compute_priority_breakdown,
        )
        action = _make_action("type_x", 0.0)
        bd = _compute_priority_breakdown(action, {}, {}, {})
        expected = min(EXPLORATION_WEIGHT, EXPLORATION_CLAMP)
        assert bd.exploration_component == pytest.approx(expected)

    def test_no_ledger_final_priority_equals_base_plus_exploration(self):
        from scripts.planner_scoring import _compute_priority_breakdown
        action = _make_action("type_x", 0.5)
        bd = _compute_priority_breakdown(action, {}, {}, {})
        assert bd.final_priority == pytest.approx(bd.base_priority + bd.exploration_component)

    def test_no_policy_zero_policy_component(self):
        from scripts.planner_scoring import _build_priority_breakdown
        actions = _make_actions([("type_a", 0.7)])
        ledger = {"type_a": _ledger_entry(effect_deltas={"sig": 1.0}, times_executed=10)}
        result = _build_priority_breakdown(actions, ledger, {}, {})
        assert result[0]["policy_component"] == pytest.approx(0.0)

    def test_no_signals_zero_targeting_component(self):
        from scripts.planner_scoring import _build_priority_breakdown
        actions = _make_actions([("type_a", 0.7)])
        ledger = {"type_a": _ledger_entry(effect_deltas={"sig": 1.0}, times_executed=10)}
        result = _build_priority_breakdown(actions, ledger, {}, {})
        assert result[0]["weak_signal_targeting_component"] == pytest.approx(0.0)

    def test_none_signals_equivalent_to_empty(self):
        from scripts.planner_scoring import _build_priority_breakdown, _compute_priority_breakdown
        action = _make_action("type_a", 0.7)
        ledger = {"type_a": _ledger_entry(effect_deltas={"sig": 1.0}, times_executed=10)}
        bd_empty = _compute_priority_breakdown(action, ledger, {}, {})
        bd_none = _build_priority_breakdown([action], ledger, None, None)
        assert round(bd_empty.final_priority, 6) == bd_none[0]["final_priority"]

    def test_empty_actions_returns_empty_list(self):
        from scripts.planner_scoring import _build_priority_breakdown
        assert _build_priority_breakdown([], {}, {}, {}) == []


# ---------------------------------------------------------------------------
# 6. Determinism across repeated calls
# ---------------------------------------------------------------------------

class TestDeterministicBehavior:
    def test_repeated_ranking_identical(self):
        from scripts.planner_scoring import _apply_learning_adjustments
        actions = _make_actions([("type_c", 0.3), ("type_a", 0.7), ("type_b", 0.5)])
        ledger = {
            "type_a": _ledger_entry(effectiveness_score=0.8, times_executed=7),
            "type_b": _ledger_entry(effectiveness_score=1.0, times_executed=3),
            "type_c": _ledger_entry(effectiveness_score=0.5, times_executed=10),
        }
        order1 = [a["action_type"] for a in _apply_learning_adjustments(list(actions), ledger)]
        order2 = [a["action_type"] for a in _apply_learning_adjustments(list(actions), ledger)]
        assert order1 == order2

    def test_repeated_compute_breakdown_identical(self):
        from scripts.planner_scoring import _compute_priority_breakdown
        action = _make_action("type_a", 0.7)
        ledger = {"type_a": _ledger_entry(effectiveness_score=1.0, times_executed=5)}
        bd1 = _compute_priority_breakdown(action, ledger, {}, {})
        bd2 = _compute_priority_breakdown(action, ledger, {}, {})
        assert bd1 == bd2

    def test_repeated_build_list_identical(self):
        from scripts.planner_scoring import _build_priority_breakdown
        actions = _make_actions([("type_a", 0.8), ("type_b", 0.6)])
        ledger = {
            "type_a": _ledger_entry(effectiveness_score=1.0, times_executed=10),
            "type_b": _ledger_entry(effectiveness_score=0.5, times_executed=5),
        }
        r1 = _build_priority_breakdown(actions, ledger, {}, {})
        r2 = _build_priority_breakdown(actions, ledger, {}, {})
        assert r1 == r2
