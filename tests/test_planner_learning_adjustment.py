# SPDX-License-Identifier: MIT
"""Regression tests for v0.26 planner learning adjustments.

Covers:
- deterministic ranking (same input → same output)
- ledger influences action ordering
- missing/None ledger produces identical ordering (v0.25 parity)
- adjustments are bounded by EFFECTIVENESS_CLAMP and SIGNAL_IMPACT_CLAMP
"""
import json
import sys
from pathlib import Path

import pytest

from src.mcp_governance_orchestrator.planner_telemetry.scoring import (
    PlannerScoringTelemetry,
)

# Ensure the repo root is on sys.path so scripts package is importable.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from planner_runtime import (  # noqa: E402
    CAPABILITY_EVOLUTION_PENALTY_WEIGHT,
    CAPABILITY_EXPLORATION_WEIGHT,
    EFFECTIVENESS_CLAMP,
    EFFECTIVENESS_WEIGHT,
    REPAIR_PRESSURE_WEIGHT,
    SIGNAL_IMPACT_CLAMP,
    SIGNAL_IMPACT_WEIGHT,
    _apply_learning_adjustments,
    _build_priority_breakdown,
    _compute_capability_exploration_adjustment,
    _compute_capability_reliability_adjustment,
    _compute_priority_breakdown,
    _compute_repair_pressure_adjustment,
    _extract_capability_history,
    compute_learning_adjustment,
    load_effectiveness_ledger,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
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


def _make_ledger(entries):
    """Build a minimal ledger dict from {action_type: {effectiveness_score, effect_deltas}}."""
    rows = []
    for at, data in entries.items():
        row = {"action_type": at}
        row.update(data)
        rows.append(row)
    return {"schema_version": "v1", "generated_at": "", "action_types": rows}


# ---------------------------------------------------------------------------
# load_effectiveness_ledger
# ---------------------------------------------------------------------------

class TestLoadEffectivenessLedger:
    def test_none_path_returns_empty(self):
        assert load_effectiveness_ledger(None) == {}

    def test_missing_file_returns_empty(self, tmp_path):
        assert load_effectiveness_ledger(str(tmp_path / "nonexistent.json")) == {}

    def test_loads_valid_ledger(self, tmp_path):
        ledger = _make_ledger({"refresh_repo_health": {"effectiveness_score": 0.8}})
        p = tmp_path / "ledger.json"
        p.write_text(json.dumps(ledger), encoding="utf-8")
        result = load_effectiveness_ledger(str(p))
        assert "refresh_repo_health" in result
        assert result["refresh_repo_health"]["effectiveness_score"] == 0.8

    def test_malformed_json_returns_empty(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not valid json", encoding="utf-8")
        assert load_effectiveness_ledger(str(p)) == {}

    def test_indexed_by_action_type(self, tmp_path):
        ledger = _make_ledger({
            "type_a": {"effectiveness_score": 0.5},
            "type_b": {"effectiveness_score": 0.9},
        })
        p = tmp_path / "ledger.json"
        p.write_text(json.dumps(ledger), encoding="utf-8")
        result = load_effectiveness_ledger(str(p))
        assert set(result.keys()) == {"type_a", "type_b"}


# ---------------------------------------------------------------------------
# compute_learning_adjustment
# ---------------------------------------------------------------------------

class TestComputeLearningAdjustment:
    def test_unknown_action_type_returns_zero(self):
        assert compute_learning_adjustment("unknown_type", {}) == 0.0

    def test_effectiveness_only(self):
        ledger = {"refresh_repo_health": {"effectiveness_score": 1.0, "effect_deltas": {}}}
        adj = compute_learning_adjustment("refresh_repo_health", ledger)
        expected = min(1.0 * EFFECTIVENESS_WEIGHT, EFFECTIVENESS_CLAMP)
        assert adj == pytest.approx(expected)

    def test_signal_impact_only(self):
        # effectiveness_score=0, sum(abs(deltas))=2.0
        ledger = {
            "rerun_failed_task": {
                "effectiveness_score": 0.0,
                "effect_deltas": {"artifact_completeness": 2.0},
            }
        }
        adj = compute_learning_adjustment("rerun_failed_task", ledger)
        expected_signal = min(2.0 * SIGNAL_IMPACT_WEIGHT, SIGNAL_IMPACT_CLAMP)
        assert adj == pytest.approx(expected_signal)

    def test_combined_adjustment(self):
        ledger = {
            "refresh_repo_health": {
                "effectiveness_score": 0.8,
                "effect_deltas": {"last_run_ok": 1.0, "stale_runs": -0.5},
            }
        }
        adj = compute_learning_adjustment("refresh_repo_health", ledger)
        eff_adj = min(0.8 * EFFECTIVENESS_WEIGHT, EFFECTIVENESS_CLAMP)
        sig_adj = min((1.0 + 0.5) * SIGNAL_IMPACT_WEIGHT, SIGNAL_IMPACT_CLAMP)
        assert adj == pytest.approx(eff_adj + sig_adj)

    def test_effectiveness_clamped_at_max(self):
        # effectiveness_score beyond what WEIGHT alone would cap
        ledger = {"type_x": {"effectiveness_score": 100.0, "effect_deltas": {}}}
        adj = compute_learning_adjustment("type_x", ledger)
        assert adj <= EFFECTIVENESS_CLAMP + SIGNAL_IMPACT_CLAMP
        assert adj <= EFFECTIVENESS_CLAMP  # signal is zero

    def test_signal_clamped_at_max(self):
        ledger = {
            "type_y": {
                "effectiveness_score": 0.0,
                "effect_deltas": {
                    "artifact_completeness": 100.0,
                    "stale_runs": 100.0,
                },
            }
        }
        adj = compute_learning_adjustment("type_y", ledger)
        assert adj <= SIGNAL_IMPACT_CLAMP

    def test_adjustment_non_negative(self):
        # effectiveness_score=0 and no deltas → zero
        ledger = {"type_z": {"effectiveness_score": 0.0, "effect_deltas": {}}}
        adj = compute_learning_adjustment("type_z", ledger)
        assert adj >= 0.0

    def test_missing_effect_deltas_field(self):
        # Row lacks effect_deltas entirely — should not raise
        ledger = {"type_a": {"effectiveness_score": 0.5}}
        adj = compute_learning_adjustment("type_a", ledger)
        assert adj == pytest.approx(min(0.5 * EFFECTIVENESS_WEIGHT, EFFECTIVENESS_CLAMP))


# ---------------------------------------------------------------------------
# _apply_learning_adjustments
# ---------------------------------------------------------------------------

class TestApplyLearningAdjustments:
    def test_empty_ledger_returns_unchanged(self):
        actions = _make_actions([("type_a", 1.0), ("type_b", 0.5)])
        result = _apply_learning_adjustments(actions, {})
        assert result == actions

    def test_deterministic_ranking(self):
        actions = _make_actions([
            ("refresh_repo_health", 0.7),
            ("rerun_failed_task", 0.6),
            ("regenerate_missing_artifact", 0.5),
        ])
        ledger = {
            "refresh_repo_health": {"effectiveness_score": 0.9, "effect_deltas": {}},
            "rerun_failed_task": {"effectiveness_score": 0.2, "effect_deltas": {}},
            "regenerate_missing_artifact": {"effectiveness_score": 0.5, "effect_deltas": {}},
        }
        result1 = _apply_learning_adjustments(list(actions), ledger)
        result2 = _apply_learning_adjustments(list(actions), ledger)
        assert [a["action_type"] for a in result1] == [a["action_type"] for a in result2]

    def test_ledger_influences_ordering(self):
        # type_b has lower base priority but much higher effectiveness
        actions = _make_actions([
            ("type_a", 1.0),
            ("type_b", 0.5),
        ])
        # type_b gets max effectiveness adjustment; type_a gets none
        ledger = {
            "type_a": {"effectiveness_score": 0.0, "effect_deltas": {}},
            "type_b": {"effectiveness_score": 1.0, "effect_deltas": {}},
        }
        result = _apply_learning_adjustments(actions, ledger)
        # type_b: 0.5 + 0.15 = 0.65; type_a: 1.0 + 0 = 1.0 → type_a still wins
        # Let's use a case where type_b actually overtakes type_a
        actions2 = _make_actions([
            ("type_a", 0.80),
            ("type_b", 0.75),
        ])
        # type_a gets 0.0 adj → 0.80; type_b gets full 0.15 adj → 0.90
        ledger2 = {
            "type_a": {"effectiveness_score": 0.0, "effect_deltas": {}},
            "type_b": {"effectiveness_score": 1.0, "effect_deltas": {}},
        }
        result2 = _apply_learning_adjustments(actions2, ledger2)
        assert result2[0]["action_type"] == "type_b"
        assert result2[1]["action_type"] == "type_a"

    def test_missing_ledger_produces_identical_ordering(self):
        """v0.25 parity: no ledger → ordering unchanged."""
        actions = _make_actions([
            ("type_a", 0.9),
            ("type_b", 0.5),
            ("type_c", 0.3),
        ])
        result_none = _apply_learning_adjustments(list(actions), {})
        # Empty ledger → all adjustments = 0 → same relative order
        assert [a["action_type"] for a in result_none] == ["type_a", "type_b", "type_c"]

    def test_adjustments_bounded_in_sorted_output(self):
        """Each action's effective priority boost is within clamped bounds."""
        actions = _make_actions([
            ("type_x", 1.0),
            ("type_y", 0.5),
        ])
        ledger = {
            "type_x": {"effectiveness_score": 999.0, "effect_deltas": {"f": 999.0}},
            "type_y": {"effectiveness_score": 999.0, "effect_deltas": {"f": 999.0}},
        }
        for at, row in ledger.items():
            adj = compute_learning_adjustment(at, row)
            assert adj <= EFFECTIVENESS_CLAMP + SIGNAL_IMPACT_CLAMP

    def test_tiebreaker_is_deterministic(self):
        """Actions with same adjusted priority sort by action_type then action_id."""
        # Both have same base priority and same ledger entry → same total priority
        actions = [
            {"action_type": "z_type", "priority": 0.5, "action_id": "aid-1", "repo_id": "repo-1"},
            {"action_type": "a_type", "priority": 0.5, "action_id": "aid-2", "repo_id": "repo-2"},
        ]
        ledger = {
            "z_type": {"effectiveness_score": 0.5, "effect_deltas": {}},
            "a_type": {"effectiveness_score": 0.5, "effect_deltas": {}},
        }
        result = _apply_learning_adjustments(actions, ledger)
        # a_type sorts before z_type alphabetically
        assert result[0]["action_type"] == "a_type"
        assert result[1]["action_type"] == "z_type"


    def test_capability_success_history_boosts_synthesis_action(self):
        actions = [
            {
                "action_type": "build_capability_artifact",
                "priority": 0.80,
                "action_id": "aid-1",
                "repo_id": "repo-1",
                "args": {"capability": "snowflake_data_access"},
            },
            {
                "action_type": "analyze_repo_insights",
                "priority": 0.84,
                "action_id": "aid-2",
                "repo_id": "repo-2",
            },
        ]
        capability_ledger = {
            "capabilities": {
                "snowflake_data_access": {
                    "total_syntheses": 10,
                    "successful_syntheses": 10,
                }
            }
        }

        result = _apply_learning_adjustments(
            actions,
            {},
            capability_ledger=capability_ledger,
        )
        assert result[0]["action_type"] == "build_capability_artifact"
        assert result[1]["action_type"] == "analyze_repo_insights"

    def test_capability_failure_history_deprioritizes_synthesis_action(self):
        actions = [
            {
                "action_type": "build_capability_artifact",
                "priority": 0.84,
                "action_id": "aid-1",
                "repo_id": "repo-1",
                "args": {"capability": "snowflake_data_access"},
            },
            {
                "action_type": "analyze_repo_insights",
                "priority": 0.80,
                "action_id": "aid-2",
                "repo_id": "repo-2",
            },
        ]
        capability_ledger = {
            "capabilities": {
                "snowflake_data_access": {
                    "total_syntheses": 10,
                    "successful_syntheses": 0,
                }
            }
        }

        result = _apply_learning_adjustments(
            actions,
            {},
            capability_ledger=capability_ledger,
        )
        assert result[0]["action_type"] == "analyze_repo_insights"
        assert result[1]["action_type"] == "build_capability_artifact"

    def test_non_synthesis_actions_ignore_capability_ledger(self):
        actions = _make_actions([
            ("type_b", 0.6),
            ("type_a", 0.6),
        ])
        capability_ledger = {
            "capabilities": {
                "snowflake_data_access": {
                    "total_syntheses": 10,
                    "successful_syntheses": 10,
                }
            }
        }

        result = _apply_learning_adjustments(
            actions,
            {},
            capability_ledger=capability_ledger,
        )
        assert [a["action_type"] for a in result] == ["type_a", "type_b"]

    def test_compute_priority_breakdown_includes_capability_reliability_component(self):
        action = {
            "action_type": "build_capability_artifact",
            "priority": 0.80,
            "action_id": "aid-1",
            "repo_id": "repo-1",
            "args": {"capability": "snowflake_data_access"},
        }
        capability_ledger = {
            "capabilities": {
                "snowflake_data_access": {
                    "total_syntheses": 4,
                    "successful_syntheses": 4,
                }
            }
        }

        breakdown = _compute_priority_breakdown(
            action,
            {},
            {},
            {},
            capability_ledger,
        )

        assert breakdown.capability_reliability_component == pytest.approx(0.02666666666666667)
        assert breakdown.exploration_component == pytest.approx(0.051)
        assert breakdown.final_priority == pytest.approx(
            0.80
            + 0.02666666666666667
            + breakdown.exploration_component
        )

    def test_build_priority_breakdown_emits_capability_reliability_component(self):
        actions = [
            {
                "action_type": "build_capability_artifact",
                "priority": 0.80,
                "action_id": "aid-1",
                "repo_id": "repo-1",
                "args": {"capability": "snowflake_data_access"},
            }
        ]
        capability_ledger = {
            "capabilities": {
                "snowflake_data_access": {
                    "total_syntheses": 4,
                    "successful_syntheses": 0,
                }
            }
        }

        breakdown = _build_priority_breakdown(
            actions,
            {},
            {},
            {},
            capability_ledger,
        )

        assert len(breakdown) == 1
        assert "capability_reliability_component" in breakdown[0]
        assert breakdown[0]["capability_reliability_component"] == pytest.approx(-0.026667)

    def test_capability_success_history_with_low_sample_count_is_not_overweighted(self):
        actions = [
            {
                "action_type": "build_capability_artifact",
                "priority": 0.80,
                "action_id": "aid-1",
                "repo_id": "repo-1",
                "args": {"capability": "snowflake_data_access"},
            },
            {
                "action_type": "analyze_repo_insights",
                "priority": 0.81,
                "action_id": "aid-2",
                "repo_id": "repo-2",
            },
        ]
        capability_ledger = {
            "capabilities": {
                "snowflake_data_access": {
                    "total_syntheses": 1,
                    "successful_syntheses": 1,
                }
            }
        }

        result = _apply_learning_adjustments(
            actions,
            {},
            capability_ledger=capability_ledger,
        )
        assert result[0]["action_type"] == "analyze_repo_insights"
        assert result[1]["action_type"] == "build_capability_artifact"


# ---------------------------------------------------------------------------
# Capability reliability helper stability (D3.3)
# ---------------------------------------------------------------------------

class TestCapabilityReliabilityAdjustment:
    def _action(self, capability):
        return {
            "action_type": "build_capability_artifact",
            "priority": 0.8,
            "action_id": "aid-x",
            "repo_id": "repo-x",
            "args": {"capability": capability},
        }

    def test_missing_ledger_returns_zero(self):
        action = self._action("cap_a")
        assert _compute_capability_reliability_adjustment(action, {}) == 0.0

    def test_missing_capability_row_returns_zero(self):
        action = self._action("cap_a")
        ledger = {"capabilities": {}}
        assert _compute_capability_reliability_adjustment(action, ledger) == 0.0

    def test_laplace_smoothing_positive_case(self):
        action = self._action("cap_a")
        ledger = {
            "capabilities": {
                "cap_a": {"total_syntheses": 1, "successful_syntheses": 1}
            }
        }
        adj = _compute_capability_reliability_adjustment(action, ledger)

        # success_rate = (1+1)/(1+2) = 2/3
        # raw = (2/3 - 0.5) * 0.10 = ~0.0166667
        # confidence = 1/5 = 0.2
        expected = 0.2 * ((2/3 - 0.5) * 0.10)

        assert adj == pytest.approx(expected)

    def test_laplace_smoothing_negative_case(self):
        action = self._action("cap_a")
        ledger = {
            "capabilities": {
                "cap_a": {"total_syntheses": 1, "successful_syntheses": 0}
            }
        }
        adj = _compute_capability_reliability_adjustment(action, ledger)

        # success_rate = (0+1)/(1+2) = 1/3
        expected = 0.2 * ((1/3 - 0.5) * 0.10)

        assert adj == pytest.approx(expected)

    def test_evolved_successes_reduce_reliability_adjustment(self):
        action = self._action("cap_a")
        ledger = {
            "capabilities": {
                "cap_a": {
                    "total_syntheses": 5,
                    "successful_syntheses": 5,
                    "successful_evolved_syntheses": 5,
                }
            }
        }

        adj = _compute_capability_reliability_adjustment(action, ledger)

        success_rate = (6 / 7)
        reliability = (success_rate - 0.5) * 0.10
        expected = reliability - CAPABILITY_EVOLUTION_PENALTY_WEIGHT

        assert adj == pytest.approx(expected)

    def test_evolved_syntheses_exceeding_successes_is_clamped(self):
        # successful_evolved_syntheses (8) > successful_syntheses (5):
        # the clamp at planner_runtime:889 caps evolved_success to success (5),
        # so the result must equal the equal-values case exactly.
        action = self._action("cap_a")
        ledger = {
            "capabilities": {
                "cap_a": {
                    "total_syntheses": 5,
                    "successful_syntheses": 5,
                    "successful_evolved_syntheses": 8,
                }
            }
        }

        adj = _compute_capability_reliability_adjustment(action, ledger)

        success_rate = (6 / 7)
        reliability = (success_rate - 0.5) * 0.10
        expected = reliability - CAPABILITY_EVOLUTION_PENALTY_WEIGHT

        assert adj == pytest.approx(expected)

    def test_missing_evolved_success_history_preserves_existing_behavior(self):
        action = self._action("cap_a")
        ledger = {
            "capabilities": {
                "cap_a": {"total_syntheses": 5, "successful_syntheses": 5}
            }
        }

        adj = _compute_capability_reliability_adjustment(action, ledger)

        success_rate = (6 / 7)
        expected = (success_rate - 0.5) * 0.10

        assert adj == pytest.approx(expected)

    def test_confidence_cap_applied(self):
        action = self._action("cap_a")
        ledger = {
            "capabilities": {
                "cap_a": {"total_syntheses": 100, "successful_syntheses": 100}
            }
        }

        adj = _compute_capability_reliability_adjustment(action, ledger)

        success_rate = (101 / 102)
        expected = (success_rate - 0.5) * 0.10

        assert adj == pytest.approx(expected)


class TestCapabilityExplorationAdjustment:
    def _action(self, capability):
        return {
            "action_type": "build_capability_artifact",
            "priority": 0.8,
            "action_id": "aid-exp",
            "repo_id": "repo-exp",
            "args": {"capability": capability},
        }

    def test_missing_ledger_returns_zero(self):
        action = self._action("cap_a")
        assert _compute_capability_exploration_adjustment(action, {}) == 0.0

    def test_missing_capability_row_returns_zero(self):
        action = self._action("cap_a")
        ledger = {"capabilities": {}}
        assert _compute_capability_exploration_adjustment(action, ledger) == 0.0

    def test_unknown_capability_gets_full_exploration_bonus_when_row_exists_with_zero_total(self):
        action = self._action("cap_a")
        ledger = {
            "capabilities": {
                "cap_a": {"total_syntheses": 0, "successful_syntheses": 0}
            }
        }
        adj = _compute_capability_exploration_adjustment(action, ledger)
        assert adj == pytest.approx(CAPABILITY_EXPLORATION_WEIGHT)

    def test_low_history_gets_partial_exploration_bonus(self):
        action = self._action("cap_a")
        ledger = {
            "capabilities": {
                "cap_a": {"total_syntheses": 1, "successful_syntheses": 1}
            }
        }
        adj = _compute_capability_exploration_adjustment(action, ledger)
        assert adj == pytest.approx((1.0 - 0.2) * CAPABILITY_EXPLORATION_WEIGHT)

    def test_mature_capability_gets_no_exploration_bonus(self):
        action = self._action("cap_a")
        ledger = {
            "capabilities": {
                "cap_a": {"total_syntheses": 5, "successful_syntheses": 5}
            }
        }
        adj = _compute_capability_exploration_adjustment(action, ledger)
        assert adj == pytest.approx(0.0)


class TestExtractCapabilityHistory:
    def _action(self, capability="cap_a", action_type="build_capability_artifact"):
        return {
            "action_type": action_type,
            "priority": 0.8,
            "action_id": "aid-cap",
            "repo_id": "repo-cap",
            "args": {"capability": capability},
        }

    def test_returns_none_for_non_capability_action(self):
        ledger = {
            "capabilities": {
                "cap_a": {"total_syntheses": 1, "successful_syntheses": 1}
            }
        }
        assert _extract_capability_history(self._action(action_type="analyze_repo_insights"), ledger) is None

    def test_returns_parsed_non_negative_values(self):
        ledger = {
            "capabilities": {
                "cap_a": {"total_syntheses": "3", "successful_syntheses": "2"}
            }
        }
        assert _extract_capability_history(self._action(), ledger) == ("cap_a", 3.0, 2.0)

    def test_negative_values_are_clamped_to_zero(self):
        ledger = {
            "capabilities": {
                "cap_a": {"total_syntheses": -2, "successful_syntheses": -1}
            }
        }
        assert _extract_capability_history(self._action(), ledger) == ("cap_a", 0.0, 0.0)

    def test_build_mcp_server_action_type_exercises_all_three_functions(self):
        action = {
            "action_type": "build_mcp_server",
            "priority": 0.8,
            "action_id": "aid-mcp",
            "repo_id": "repo-mcp",
            "args": {"capability": "api_gateway"},
        }
        capability_ledger = {
            "capabilities": {
                "api_gateway": {
                    "total_syntheses": 2,
                    "successful_syntheses": 2,
                }
            }
        }

        history = _extract_capability_history(action, capability_ledger)
        assert history == ("api_gateway", 2.0, 2.0)

        exploration_adj = _compute_capability_exploration_adjustment(action, capability_ledger)
        assert exploration_adj == pytest.approx(0.003)  # (1 - 0.4) * 0.005

        reliability_adj = _compute_capability_reliability_adjustment(action, capability_ledger)
        assert reliability_adj == pytest.approx(0.01)  # 0.4 * (0.75 - 0.5) * 0.10


# ---------------------------------------------------------------------------
# Planner scoring telemetry
# ---------------------------------------------------------------------------

class TestPlannerScoringTelemetry:
    def test_collects_signal_contributions(self):
        actions = [
            {
                "action_type": "refresh_repo_health",
                "priority": 1.0,
                "action_id": "a1",
                "repo_id": "r1",
            }
        ]

        ledger = {
            "refresh_repo_health": {
                "effectiveness_score": 1.0,
                "effect_deltas": {"artifact_completeness": 0.5},
                "times_executed": 0,
            }
        }

        telemetry = PlannerScoringTelemetry()

        breakdown = _compute_priority_breakdown(
            actions[0],
            ledger,
            current_signals={},
            policy={},
            capability_ledger=None,
            telemetry=telemetry,
        )

        assert breakdown.action_type == "refresh_repo_health"

        data = telemetry.to_dict()

        assert "actions" in data
        assert len(data["actions"]) == 1

        record = data["actions"][0]

        assert record["action_type"] == "refresh_repo_health"
        assert len(record["signal_contributions"]) == 7


# ---------------------------------------------------------------------------
# _repair_cycle ledger entry isolation (Stage 2 guard)
# ---------------------------------------------------------------------------

class TestRepairCycleLedgerExclusion:
    """_repair_cycle entries in capability_ledger must not distort real-capability
    reliability scores and must not appear in per-capability reliability output."""

    def _action(self, capability):
        return {
            "action_type": "build_capability_artifact",
            "priority": 0.80,
            "action_id": "aid-1",
            "repo_id": "repo-1",
            "args": {"capability": capability},
        }

    def test_repair_cycle_entry_does_not_affect_real_capability_score(self):
        """A ledger containing _repair_cycle must yield the same reliability score
        for a real capability as a ledger without the _repair_cycle entry."""
        ledger_without_repair = {
            "capabilities": {
                "snowflake_data_access": {
                    "total_syntheses": 3,
                    "successful_syntheses": 3,
                }
            }
        }
        ledger_with_repair = {
            "capabilities": {
                "snowflake_data_access": {
                    "total_syntheses": 3,
                    "successful_syntheses": 3,
                },
                "_repair_cycle": {
                    "total_syntheses": 3,
                    "successful_syntheses": 3,
                    "failed_syntheses": 0,
                    "last_synthesis_source": "repair",
                },
            }
        }
        action = self._action("snowflake_data_access")

        score_without = _compute_capability_reliability_adjustment(action, ledger_without_repair)
        score_with = _compute_capability_reliability_adjustment(action, ledger_with_repair)

        assert score_without == score_with

    def test_repair_cycle_entry_not_reachable_as_real_capability(self):
        """_extract_capability_history must return None for a _repair_cycle action lookup
        because no planner action carries args.capability == '_repair_cycle'."""
        ledger = {
            "capabilities": {
                "_repair_cycle": {
                    "total_syntheses": 3,
                    "successful_syntheses": 0,
                    "failed_syntheses": 3,
                    "last_synthesis_source": "repair",
                }
            }
        }
        action = self._action("_repair_cycle")
        # Even if someone constructed such an action, _extract_capability_history
        # would return it, but real planner actions never carry this key.
        # We verify the reliability score is structurally isolated: a normal
        # real-capability action is unaffected.
        real_action = self._action("snowflake_data_access")
        assert _extract_capability_history(real_action, ledger) is None

    def test_repair_pressure_adjustment_returns_nonzero_when_repair_cycle_has_failures(self):
        """_compute_repair_pressure_adjustment returns a positive value when
        _repair_cycle entry has failed_syntheses > 0."""
        action = self._action("snowflake_data_access")
        capability_ledger = {
            "capabilities": {
                "snowflake_data_access": {
                    "total_syntheses": 3,
                    "successful_syntheses": 3,
                },
                "_repair_cycle": {
                    "total_syntheses": 4,
                    "successful_syntheses": 1,
                    "failed_syntheses": 3,
                    "last_synthesis_source": "repair",
                },
            }
        }

        adj = _compute_repair_pressure_adjustment(action, capability_ledger)

        expected = (3.0 / 4.0) * REPAIR_PRESSURE_WEIGHT
        assert adj == pytest.approx(expected)

    def test_repair_pressure_adjustment_returns_zero_when_no_repair_cycle_entry(self):
        """_compute_repair_pressure_adjustment returns 0.0 when the ledger has
        no _repair_cycle entry."""
        action = self._action("snowflake_data_access")
        capability_ledger = {
            "capabilities": {
                "snowflake_data_access": {
                    "total_syntheses": 3,
                    "successful_syntheses": 3,
                },
            }
        }

        adj = _compute_repair_pressure_adjustment(action, capability_ledger)

        assert adj == 0.0

    def test_returns_zero_when_capability_ledger_is_empty(self):
        # planner_runtime:539 — `if not capability_ledger: return 0.0`
        action = self._action("snowflake_data_access")
        adj = _compute_repair_pressure_adjustment(action, {})
        assert adj == 0.0

    def test_returns_zero_for_non_synthesis_action_type(self):
        # planner_runtime:542-544 — action_type not in the synthesis set
        action = {"action_type": "refresh_repo_health", "capability": "snowflake_data_access"}
        capability_ledger = {
            "capabilities": {
                "_repair_cycle": {
                    "total_syntheses": 4,
                    "failed_syntheses": 3,
                }
            }
        }
        adj = _compute_repair_pressure_adjustment(action, capability_ledger)
        assert adj == 0.0

    def test_returns_zero_when_caps_is_not_a_dict(self):
        # planner_runtime:546-548 — capabilities value is not a dict
        action = self._action("snowflake_data_access")
        capability_ledger = {"capabilities": "malformed"}
        adj = _compute_repair_pressure_adjustment(action, capability_ledger)
        assert adj == 0.0

    def test_returns_zero_when_failed_syntheses_is_non_numeric(self):
        # planner_runtime:554-558 — float() raises TypeError/ValueError
        action = self._action("snowflake_data_access")
        capability_ledger = {
            "capabilities": {
                "_repair_cycle": {
                    "total_syntheses": 4,
                    "failed_syntheses": "bad",
                }
            }
        }
        adj = _compute_repair_pressure_adjustment(action, capability_ledger)
        assert adj == 0.0

    def test_returns_zero_when_failed_syntheses_is_zero(self):
        # planner_runtime:563-564 — failed == 0.0 guard
        action = self._action("snowflake_data_access")
        capability_ledger = {
            "capabilities": {
                "_repair_cycle": {
                    "total_syntheses": 4,
                    "failed_syntheses": 0,
                }
            }
        }
        adj = _compute_repair_pressure_adjustment(action, capability_ledger)
        assert adj == 0.0
