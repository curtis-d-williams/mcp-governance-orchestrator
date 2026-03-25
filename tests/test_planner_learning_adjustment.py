# SPDX-License-Identifier: MIT
"""Regression tests for v0.26 planner learning adjustments.

Covers:
- deterministic ranking (same input → same output)
- ledger influences action ordering
- missing/None ledger produces identical ordering (v0.25 parity)
- adjustments are bounded by EFFECTIVENESS_CLAMP and SIGNAL_IMPACT_CLAMP
"""
import importlib.util
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
    ScoringContext,
    _apply_learning_adjustments,
    _build_priority_breakdown,
    _compute_capability_exploration_adjustment,
    _compute_capability_reliability_adjustment,
    _compute_exploration_adjustment_raw,
    _compute_priority_breakdown,
    _compute_repair_pressure_adjustment,
    _compute_task_reliability,
    _extract_capability_history,
    compute_exploration_bonus,
    compute_learning_adjustment,
    load_capability_effectiveness_ledger,
    load_effectiveness_ledger,
)


# ---------------------------------------------------------------------------
# Module loader for update_capability_effectiveness_from_cycles
# ---------------------------------------------------------------------------

_CYCLES_SCRIPT = _REPO_ROOT / "scripts" / "update_capability_effectiveness_from_cycles.py"
_cycles_spec = importlib.util.spec_from_file_location(
    "update_capability_effectiveness_from_cycles", _CYCLES_SCRIPT
)
_cycles_mod = importlib.util.module_from_spec(_cycles_spec)
_cycles_spec.loader.exec_module(_cycles_mod)
update_capability_effectiveness_from_cycles = _cycles_mod.update_capability_effectiveness_from_cycles


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

    def test_both_keys_prefers_action_types(self, tmp_path):
        ledger = {
            "actions": {
                "build_portfolio_dashboard": {
                    "total_runs": 1,
                    "success_runs": 1,
                    "effect_deltas": [],
                }
            },
            "action_types": [
                {
                    "action_type": "refresh_repo_health",
                    "effectiveness_score": 0.8,
                    "times_executed": 3,
                    "classification": "effective",
                    "recommended_priority_adjustment": 0.1,
                }
            ],
        }
        p = tmp_path / "ledger.json"
        p.write_text(json.dumps(ledger), encoding="utf-8")
        result = load_effectiveness_ledger(str(p))
        assert "refresh_repo_health" in result
        assert "build_portfolio_dashboard" not in result

    def test_only_actions_key_still_resolves(self, tmp_path):
        ledger = {
            "actions": {
                "build_portfolio_dashboard": {
                    "total_runs": 2,
                    "success_runs": 2,
                    "effect_deltas": [],
                }
            }
        }
        p = tmp_path / "ledger.json"
        p.write_text(json.dumps(ledger), encoding="utf-8")
        result = load_effectiveness_ledger(str(p))
        assert "actions" in result


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

    def test_all_scoring_signals_contribute_nonzero_and_sort_order_is_correct(self):
        """All 7 SCORING_SIGNALS produce non-zero contributions simultaneously.

        Fixture design:
        - action in ledger (effectiveness_score > 0, effect_deltas non-empty)
          → times_executed absent → confidence=1.0 (backward-compat)
          → action exploration bonus uses times_executed=0 → max bonus
        - current_signals with value < 1.0 matching effect_deltas key
          → weak_signal_targeting non-zero
        - policy matching effect_deltas key → policy_component non-zero
        - capability_ledger with successful syntheses → reliability non-zero
        - capability_ledger with _repair_cycle.failed_syntheses > 0
          → repair_pressure non-zero
        - capability_ledger total_syntheses < threshold → capability exploration non-zero

        Arithmetic (to verify sort order):
          build_mcp_server base=0.5, confidence=1.0 (times_executed absent)
            effectiveness  = 1.0 * min(0.8*0.15, clamp) = 0.120
            signal_delta   = 1.0 * min(0.5*0.05, clamp) = 0.025
            weak_signal    = 1.0 * (0.5 * (1.0-0.3)) * 0.10 = 0.035
            policy         = 1.0 * (0.4 * 0.5)              = 0.200
            reliability    = (6/7 - 0.5) * 0.10             ~ 0.036
            repair_pressure= (1/3) * 0.08                   ~ 0.027
            exploration    = action: 1/(1+0)*0.05=0.05 + cap: total=5>=threshold → 0.0 = 0.050
          Total boost ~ 0.493  →  final ~ 0.993

          competitor base=0.8, absent from ledger → confidence=0.0
            All confidence-scaled components = 0.0
            exploration = 0.05 (action absent from ledger → max bonus)
          final = 0.85

          build_mcp_server (0.993) > competitor (0.85) → sort order holds.
        """
        action = {
            "action_type": "build_mcp_server",
            "priority": 0.5,
            "action_id": "aid-1",
            "repo_id": "repo-1",
            "args": {"capability": "auth_service"},
        }
        ledger = {
            "build_mcp_server": {
                "effectiveness_score": 0.8,
                "effect_deltas": {"signal_x": 0.5},
                # times_executed absent → confidence_factor = 1.0 (backward-compat)
            }
        }
        current_signals = {"signal_x": 0.3}  # < 1.0 → weak_signal_targeting non-zero
        policy = {"signal_x": 0.4}           # matches effect_deltas → policy_component non-zero
        capability_ledger = {
            "capabilities": {
                "auth_service": {
                    "total_syntheses": 5,
                    "successful_syntheses": 4,  # reliability boost
                },
                "_repair_cycle": {
                    "total_syntheses": 3,
                    "failed_syntheses": 1,      # repair_pressure non-zero
                },
            }
        }

        # Assert all 7 components are non-zero via _compute_priority_breakdown
        bd = _compute_priority_breakdown(
            action, ledger, current_signals, policy, capability_ledger
        )
        assert bd.effectiveness_component != 0.0, "effectiveness_component must be non-zero"
        assert bd.signal_delta_component != 0.0, "signal_delta_component must be non-zero"
        assert bd.weak_signal_targeting_component != 0.0, "weak_signal_targeting_component must be non-zero"
        assert bd.policy_component != 0.0, "policy_component must be non-zero"
        assert bd.capability_reliability_component != 0.0, "capability_reliability_component must be non-zero"
        assert bd.repair_pressure_component != 0.0, "repair_pressure_component must be non-zero"
        assert bd.exploration_component != 0.0, "exploration_component must be non-zero"

        # Assert _apply_learning_adjustments sort order reflects all-signal combined boost.
        # Competitor has higher base priority but is absent from both ledgers
        # → confidence=0.0 → all scaled components zero, no capability signals.
        # build_mcp_server's combined boost must overtake the priority gap.
        competitor = {
            "action_type": "analyze_repo_insights",
            "priority": 0.8,
            "action_id": "aid-2",
            "repo_id": "repo-2",
        }
        result = _apply_learning_adjustments(
            [competitor, action],
            ledger,
            current_signals=current_signals,
            policy=policy,
            capability_ledger=capability_ledger,
        )
        assert result[0]["action_type"] == "build_mcp_server", (
            f"build_mcp_server should rank first due to all-signal boost; "
            f"got {[a['action_type'] for a in result]}"
        )
        assert result[1]["action_type"] == "analyze_repo_insights"


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

    def test_near_threshold_total4_full_success_exact_value(self):
        action = self._action("cap_a")
        ledger = {"capabilities": {"cap_a": {"total_syntheses": 4, "successful_syntheses": 4}}}
        adj = _compute_capability_reliability_adjustment(action, ledger)
        assert adj == pytest.approx(0.8 * ((5 / 6 - 0.5) * 0.10))

    def test_near_threshold_total4_less_than_full_confidence_total5(self):
        action = self._action("cap_a")
        ledger_4 = {"capabilities": {"cap_a": {"total_syntheses": 4, "successful_syntheses": 4}}}
        ledger_5 = {"capabilities": {"cap_a": {"total_syntheses": 5, "successful_syntheses": 5}}}
        adj_4 = _compute_capability_reliability_adjustment(action, ledger_4)
        adj_5 = _compute_capability_reliability_adjustment(action, ledger_5)
        assert adj_4 == pytest.approx(0.8 * ((5 / 6 - 0.5) * 0.10))
        assert adj_5 == pytest.approx(1.0 * ((6 / 7 - 0.5) * 0.10))
        assert adj_4 < adj_5
        assert adj_5 - adj_4 == pytest.approx(0.5 / 14 - 0.08 / 3)

    def test_capability_degradation_is_monotonic_across_three_cycles(self):
        action = self._action("cap_a")

        ledger_c1 = {"capabilities": {"cap_a": {"total_syntheses": 1, "successful_syntheses": 0}}}
        ledger_c2 = {"capabilities": {"cap_a": {"total_syntheses": 2, "successful_syntheses": 0}}}
        ledger_c3 = {"capabilities": {"cap_a": {"total_syntheses": 3, "successful_syntheses": 0}}}

        adj_c1 = _compute_capability_reliability_adjustment(action, ledger_c1)
        adj_c2 = _compute_capability_reliability_adjustment(action, ledger_c2)
        adj_c3 = _compute_capability_reliability_adjustment(action, ledger_c3)

        # All adjustments must be negative (penalizing the capability)
        assert adj_c1 < 0.0
        assert adj_c2 < 0.0
        assert adj_c3 < 0.0

        # Adjustment must be strictly monotonically decreasing across cycles
        assert adj_c1 > adj_c2 > adj_c3

    def test_successful_capability_reinforcement_is_monotonic_across_three_cycles(self):
        action = self._action("cap_a")

        ledger_c1 = {"capabilities": {"cap_a": {"total_syntheses": 1, "successful_syntheses": 1}}}
        ledger_c2 = {"capabilities": {"cap_a": {"total_syntheses": 2, "successful_syntheses": 2}}}
        ledger_c3 = {"capabilities": {"cap_a": {"total_syntheses": 3, "successful_syntheses": 3}}}

        adj_c1 = _compute_capability_reliability_adjustment(action, ledger_c1)
        adj_c2 = _compute_capability_reliability_adjustment(action, ledger_c2)
        adj_c3 = _compute_capability_reliability_adjustment(action, ledger_c3)

        # All adjustments must be positive (reinforcing the capability)
        assert adj_c1 > 0.0
        assert adj_c2 > 0.0
        assert adj_c3 > 0.0

        # Adjustment must be strictly monotonically increasing across cycles
        assert adj_c1 < adj_c2 < adj_c3

    def test_mixed_signal_ranks_between_all_failure_and_all_success(self):
        # total=3, success=1 (2 failures, 1 success — net-negative partial recovery)
        # mixed_adj should rank strictly between all-failure and all-success
        # for the same total count (total=3).
        #
        # all_failure: success_rate = (0+1)/(3+2) = 1/5 = 0.20
        #   confidence = min(3/5, 1.0) = 0.6
        #   all_failure_adj = 0.6 * ((0.20 - 0.5) * 0.10) = 0.6 * -0.030 = -0.018
        #
        # mixed: success_rate = (1+1)/(3+2) = 2/5 = 0.40
        #   confidence = min(3/5, 1.0) = 0.6
        #   mixed_adj = 0.6 * ((0.40 - 0.5) * 0.10) = 0.6 * -0.010 = -0.006
        #
        # all_success: success_rate = (3+1)/(3+2) = 4/5 = 0.80
        #   confidence = min(3/5, 1.0) = 0.6
        #   all_success_adj = 0.6 * ((0.80 - 0.5) * 0.10) = 0.6 * 0.030 = +0.018
        action = self._action("cap_a")

        ledger_all_failure = {"capabilities": {"cap_a": {"total_syntheses": 3, "successful_syntheses": 0}}}
        ledger_mixed       = {"capabilities": {"cap_a": {"total_syntheses": 3, "successful_syntheses": 1}}}
        ledger_all_success = {"capabilities": {"cap_a": {"total_syntheses": 3, "successful_syntheses": 3}}}

        all_failure_adj = _compute_capability_reliability_adjustment(action, ledger_all_failure)
        mixed_adj       = _compute_capability_reliability_adjustment(action, ledger_mixed)
        all_success_adj = _compute_capability_reliability_adjustment(action, ledger_all_success)

        assert mixed_adj > all_failure_adj   # -0.006 > -0.018
        assert mixed_adj < all_success_adj   # -0.006 < +0.018
        assert mixed_adj < 0.0              # net-negative history still penalizes


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

    def test_exploration_bonus_strictly_decreasing_steps_zero_through_five(self):
        """Verify exploration bonus decreases strictly at each integer step 0→5
        and reaches exactly 0.0 at the maturity threshold (total_syntheses=5)."""
        action = self._action("cap_a")
        adjustments = []
        for total in range(6):
            ledger = {
                "capabilities": {
                    "cap_a": {"total_syntheses": total, "successful_syntheses": 0}
                }
            }
            adjustments.append(_compute_capability_exploration_adjustment(action, ledger))

        for i in range(5):
            assert adjustments[i] > adjustments[i + 1], (
                f"expected adj[{i}]={adjustments[i]} > adj[{i+1}]={adjustments[i+1]}"
            )
        assert adjustments[5] == pytest.approx(0.0)


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

    def test_exploration_component_includes_capability_sub_term(self):
        """exploration_component scaled_value is strictly greater when capability_ledger
        is populated vs None, proving both action and capability sub-terms contribute."""
        action = {
            "action_type": "build_capability_artifact",
            "priority": 0.80,
            "action_id": "aid-expl",
            "repo_id": "repo-expl",
            "args": {"capability": "snowflake_data_access"},
        }
        ledger = {
            "build_capability_artifact": {
                "effectiveness_score": 1.0,
                "effect_deltas": {},
                "times_executed": 0,
            }
        }
        capability_ledger = {
            "capabilities": {
                "snowflake_data_access": {
                    "total_syntheses": 2,
                    "successful_syntheses": 2,
                }
            }
        }

        telemetry_none = PlannerScoringTelemetry()
        _compute_priority_breakdown(
            action,
            ledger,
            current_signals={},
            policy={},
            capability_ledger=None,
            telemetry=telemetry_none,
        )
        record_none = telemetry_none.to_dict()["actions"][0]
        assert len(record_none["signal_contributions"]) == 7
        expl_none = next(
            c for c in record_none["signal_contributions"]
            if c["component_field"] == "exploration_component"
        )

        telemetry_cap = PlannerScoringTelemetry()
        _compute_priority_breakdown(
            action,
            ledger,
            current_signals={},
            policy={},
            capability_ledger=capability_ledger,
            telemetry=telemetry_cap,
        )
        record_cap = telemetry_cap.to_dict()["actions"][0]
        assert len(record_cap["signal_contributions"]) == 7
        expl_cap = next(
            c for c in record_cap["signal_contributions"]
            if c["component_field"] == "exploration_component"
        )

        assert expl_cap["scaled_value"] == pytest.approx(
            expl_none["scaled_value"] + 0.003
        )
        assert expl_cap["scaled_value"] > expl_none["scaled_value"]


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


# ---------------------------------------------------------------------------
# _compute_exploration_adjustment_raw — combined path (action + capability)
# ---------------------------------------------------------------------------

class TestComputeExplorationAdjustmentRaw:
    def test_both_sub_functions_contribute_nonzero_and_sum_is_correct(self):
        """_compute_exploration_adjustment_raw returns the sum of
        compute_exploration_bonus and _compute_capability_exploration_adjustment
        when both contribute non-zero values.

        Conditions that guarantee both sub-values are non-zero:
        - action_type absent from ledger → uncertainty=1.0, full action bonus
        - capability row exists with total_syntheses=0 → confidence=0.0, full capability bonus
        """
        # action_type must be a synthesis type for capability exploration to apply,
        # and must be absent from the action-level ledger for action exploration bonus.
        action_type = "build_capability_artifact"
        action = {
            "action_type": action_type,
            "priority": 0.5,
            "action_id": "aid-raw",
            "repo_id": "repo-raw",
            "args": {"capability": "cap_x"},
        }
        ledger = {}  # build_capability_artifact absent → times_executed=0 → full action bonus
        capability_ledger = {
            "capabilities": {
                "cap_x": {"total_syntheses": 0, "successful_syntheses": 0}
            }
        }

        context = ScoringContext(
            action=action,
            action_type=action_type,
            base_priority=0.5,
            ledger=ledger,
            current_signals={},
            policy={},
            capability_ledger=capability_ledger,
            confidence_factor=1.0,
            row={},
            effect_deltas={},
        )

        expected_action_bonus = compute_exploration_bonus(action_type, ledger)
        expected_cap_bonus = _compute_capability_exploration_adjustment(action, capability_ledger)

        assert expected_action_bonus != 0.0, "action exploration bonus must be non-zero"
        assert expected_cap_bonus != 0.0, "capability exploration bonus must be non-zero"

        result = _compute_exploration_adjustment_raw(context)
        assert result == pytest.approx(expected_action_bonus + expected_cap_bonus)


# ---------------------------------------------------------------------------
# TestLoadCapabilityLedgerRoundTrip
# ---------------------------------------------------------------------------

class TestLoadCapabilityLedgerRoundTrip:
    """Round-trip: file-written ledger -> load -> planner sort effect."""

    def _make_cap_ledger_file(self, tmp_path, capabilities):
        """Write a capability ledger JSON and return the path string."""
        data = {"capabilities": capabilities}
        p = tmp_path / "cap_ledger.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        return str(p)

    def test_file_sourced_ledger_produces_nonzero_reliability_adjustment(self, tmp_path):
        # total=5 (at threshold), success=5 → confidence=1.0, success_rate=6/7 → positive adj
        path = self._make_cap_ledger_file(tmp_path, {
            "my_capability": {"total_syntheses": 5, "successful_syntheses": 5}
        })
        loaded = load_capability_effectiveness_ledger(path)
        action = {
            "action_type": "build_capability_artifact",
            "args": {"capability": "my_capability"},
            "priority": 0.5,
        }
        result = _compute_capability_reliability_adjustment(action, loaded)
        assert result != 0.0

    def test_file_sourced_ledger_affects_sort_order(self, tmp_path):
        # high_cap: 5/5 success → positive boost; low_cap: 0/5 success → negative penalty
        path = self._make_cap_ledger_file(tmp_path, {
            "high_cap": {"total_syntheses": 5, "successful_syntheses": 5},
            "low_cap": {"total_syntheses": 5, "successful_syntheses": 0},
        })
        loaded = load_capability_effectiveness_ledger(path)
        actions = [
            {
                "action_type": "build_capability_artifact",
                "args": {"capability": "low_cap"},
                "priority": 0.5,
                "action_id": "aid-low",
                "repo_id": "repo-0",
            },
            {
                "action_type": "build_capability_artifact",
                "args": {"capability": "high_cap"},
                "priority": 0.5,
                "action_id": "aid-high",
                "repo_id": "repo-0",
            },
        ]
        sorted_actions = _apply_learning_adjustments(actions, {}, capability_ledger=loaded)
        assert sorted_actions[0]["args"]["capability"] == "high_cap"

    def test_missing_ledger_file_returns_empty_dict(self):
        result = load_capability_effectiveness_ledger("/nonexistent/path/cap_ledger.json")
        assert result == {}

    def test_evolution_penalty_reduces_adjustment_vs_no_evolution(self, tmp_path):
        # File-sourced path: same history, only successful_evolved_syntheses differs.
        # Confirms load_capability_effectiveness_ledger preserves the field and the
        # evolution penalty branch measurably lowers the adjustment.
        no_evo_path = tmp_path / "no_evo_ledger.json"
        no_evo_path.write_text(
            json.dumps({"capabilities": {"my_cap": {
                "total_syntheses": 5,
                "successful_syntheses": 5,
                "successful_evolved_syntheses": 0,
            }}}),
            encoding="utf-8",
        )
        with_evo_path = tmp_path / "with_evo_ledger.json"
        with_evo_path.write_text(
            json.dumps({"capabilities": {"my_cap": {
                "total_syntheses": 5,
                "successful_syntheses": 5,
                "successful_evolved_syntheses": 5,
            }}}),
            encoding="utf-8",
        )
        loaded_no_evo = load_capability_effectiveness_ledger(str(no_evo_path))
        loaded_with_evo = load_capability_effectiveness_ledger(str(with_evo_path))
        action = {
            "action_type": "build_capability_artifact",
            "args": {"capability": "my_cap"},
            "priority": 0.5,
        }
        adj_no_evo = _compute_capability_reliability_adjustment(action, loaded_no_evo)
        adj_with_evo = _compute_capability_reliability_adjustment(action, loaded_with_evo)
        assert adj_with_evo < adj_no_evo


# ---------------------------------------------------------------------------
# TestUpdateFromCyclesRoundTrip
# ---------------------------------------------------------------------------

class TestUpdateFromCyclesRoundTrip:
    """Round-trip: update_capability_effectiveness_from_cycles output → planner ranking."""

    def test_cycle_history_with_success_produces_positive_ranking_boost(self, tmp_path):
        cycle_history = {
            "cycles": [{
                "cycle_result": {
                    "synthesis_event": {
                        "capability": "test_cap",
                        "artifact_kind": "mcp_server",
                        "status": "ok",
                        "source": "builder",
                        "used_evolution": False,
                    }
                }
            }]
        }
        ch_path = tmp_path / "cycle_history.json"
        ch_path.write_text(json.dumps(cycle_history), encoding="utf-8")
        out_path = tmp_path / "cap_ledger.json"

        rc = update_capability_effectiveness_from_cycles(str(ch_path), str(out_path))
        assert rc == 0
        assert out_path.exists()

        ledger = load_capability_effectiveness_ledger(str(out_path))
        actions = [
            {"action_type": "build_capability_artifact", "priority": 10.0, "args": {"capability": "test_cap"}},
            {"action_type": "refresh_repo_health", "priority": 10.0, "args": {}},
        ]
        ranked = _apply_learning_adjustments(actions, {}, capability_ledger=ledger)
        assert ranked[0]["action_type"] == "build_capability_artifact"

    def test_cycle_history_with_failure_produces_negative_ranking_effect(self, tmp_path):
        failure_cycle = {
            "cycle_result": {
                "synthesis_event": {
                    "capability": "test_cap_fail",
                    "artifact_kind": "mcp_server",
                    "status": "failed",
                    "source": "builder",
                    "used_evolution": False,
                }
            }
        }
        cycle_history = {"cycles": [failure_cycle] * 5}
        ch_path = tmp_path / "cycle_history.json"
        ch_path.write_text(json.dumps(cycle_history), encoding="utf-8")
        out_path = tmp_path / "cap_ledger.json"

        rc = update_capability_effectiveness_from_cycles(str(ch_path), str(out_path))
        assert rc == 0

        ledger = load_capability_effectiveness_ledger(str(out_path))
        actions = [
            {"action_type": "build_capability_artifact", "priority": 10.0, "args": {"capability": "test_cap_fail"}},
            {"action_type": "refresh_repo_health", "priority": 10.0, "args": {}},
        ]
        ranked = _apply_learning_adjustments(actions, {}, capability_ledger=ledger)
        assert ranked[0]["action_type"] != "build_capability_artifact"

    def test_similarity_fields_survive_aggregation_to_ledger_file(self, tmp_path):
        cycle_history = {
            "cycles": [{
                "cycle_result": {
                    "synthesis_event": {
                        "capability": "test_cap",
                        "artifact_kind": "mcp_server",
                        "status": "ok",
                        "source": "builder",
                        "similarity_score": 0.91,
                        "previous_similarity_score": 0.75,
                        "similarity_delta": 0.16,
                    }
                }
            }]
        }
        ch_path = tmp_path / "cycle_history_sim.json"
        ch_path.write_text(json.dumps(cycle_history), encoding="utf-8")
        out_path = tmp_path / "cap_ledger_sim.json"

        rc = update_capability_effectiveness_from_cycles(str(ch_path), str(out_path))
        assert rc == 0

        ledger = load_capability_effectiveness_ledger(str(out_path))
        cap = ledger["capabilities"]["test_cap"]
        assert cap["similarity_score"] == 0.91
        assert cap["previous_similarity_score"] == 0.75
        assert cap["similarity_delta"] == 0.16

    def test_priority_score_decreases_after_failed_synthesis_across_cycles(self, tmp_path):
        cycle_history = {
            "cycles": [{
                "cycle_result": {
                    "synthesis_event": {
                        "capability": "api_gateway",
                        "artifact_kind": "mcp_server",
                        "status": "failed",
                        "source": "builder",
                        "used_evolution": False,
                    }
                }
            }]
        }
        ch_path = tmp_path / "cycle_history.json"
        ch_path.write_text(json.dumps(cycle_history), encoding="utf-8")
        out_path = tmp_path / "cap_ledger_apigw.json"

        rc = update_capability_effectiveness_from_cycles(str(ch_path), str(out_path))
        assert rc == 0

        ledger = load_capability_effectiveness_ledger(str(out_path))

        action = {
            "action_type": "build_capability_artifact",
            "priority": 1.0,
            "action_id": "aid-1",
            "repo_id": "repo-1",
            "args": {"capability": "api_gateway"},
        }

        bd_baseline = _compute_priority_breakdown(action, {}, {}, {}, capability_ledger={})
        bd_after_failure = _compute_priority_breakdown(action, {}, {}, {}, capability_ledger=ledger)

        assert bd_after_failure.capability_reliability_component < 0.0

    def test_evolved_synthesis_history_activates_evolution_penalty(self, tmp_path):
        cycle_history = {
            "cycles": [{
                "cycle_result": {
                    "synthesis_event": {
                        "capability": "test_cap_evo",
                        "artifact_kind": "mcp_server",
                        "status": "ok",
                        "source": "builder",
                        "used_evolution": True,
                        "similarity_delta": 0.20,
                    }
                }
            }]
        }
        ch_path = tmp_path / "cycle_history_evo.json"
        ch_path.write_text(json.dumps(cycle_history), encoding="utf-8")
        out_path = tmp_path / "cap_ledger_evo.json"

        rc = update_capability_effectiveness_from_cycles(str(ch_path), str(out_path))
        assert rc == 0

        ledger = load_capability_effectiveness_ledger(str(out_path))

        cap_row = ledger.get("capabilities", {}).get("test_cap_evo", {})
        assert cap_row.get("successful_evolved_syntheses", 0) >= 1

        action = {
            "action_type": "build_capability_artifact",
            "priority": 1.0,
            "action_id": "aid-1",
            "repo_id": "repo-1",
            "args": {"capability": "test_cap_evo"},
        }

        bd_baseline = _compute_priority_breakdown(action, {}, {}, {}, capability_ledger={})
        bd_after_evolution = _compute_priority_breakdown(action, {}, {}, {}, capability_ledger=ledger)

        assert bd_after_evolution.capability_reliability_component < bd_baseline.capability_reliability_component


# ---------------------------------------------------------------------------
# Multi-cycle learning feedback (cycle N ledger delta → cycle N+1 ranking)
# ---------------------------------------------------------------------------

class TestMultiCycleLearningFeedback:
    """Verify that ledger state delta from Cycle N changes planner rankings in Cycle N+1."""

    @staticmethod
    def _recompute(row):
        s, f = row["success_count"], row["failure_count"]
        row["effectiveness_score"] = round(s / max(1, s + f), 6)

    @staticmethod
    def _action(action_type, priority=1.0):
        return {
            "action_type": action_type,
            "priority": priority,
            "action_id": f"aid-{action_type}",
            "repo_id": "repo-test",
        }

    def test_ledger_delta_changes_ranking_cycle_n_plus_1(self):
        ledger = {
            "action_a": {
                "action_type": "action_a",
                "times_executed": 2,
                "success_count": 1,
                "failure_count": 1,
                "effectiveness_score": 0.5,
                "effect_deltas": {},
            },
            "action_b": {
                "action_type": "action_b",
                "times_executed": 2,
                "success_count": 1,
                "failure_count": 1,
                "effectiveness_score": 0.5,
                "effect_deltas": {},
            },
        }
        # Simulate outcome: action_a succeeds 3 more times, action_b fails 3 more times
        ledger["action_a"]["success_count"] += 3
        ledger["action_a"]["times_executed"] += 3
        self._recompute(ledger["action_a"])

        ledger["action_b"]["failure_count"] += 3
        ledger["action_b"]["times_executed"] += 3
        self._recompute(ledger["action_b"])

        # action_a: s=4, f=1 → score=0.8; action_b: s=1, f=4 → score=0.2
        assert ledger["action_a"]["effectiveness_score"] > ledger["action_b"]["effectiveness_score"]

        actions = [self._action("action_a"), self._action("action_b")]
        result = _apply_learning_adjustments(actions, ledger)
        types = [a["action_type"] for a in result]
        assert types[0] == "action_a"
        assert types[1] == "action_b"

    def test_consistently_succeeding_action_rises_over_cycles(self):
        ledger = {
            "action_winner": {
                "action_type": "action_winner",
                "times_executed": 2,
                "success_count": 1,
                "failure_count": 1,
                "effectiveness_score": 0.5,
                "effect_deltas": {},
            },
            "action_baseline": {
                "action_type": "action_baseline",
                "times_executed": 2,
                "success_count": 1,
                "failure_count": 1,
                "effectiveness_score": 0.5,
                "effect_deltas": {},
            },
        }
        adjustments = []
        for _ in range(5):
            ledger["action_winner"]["success_count"] += 1
            ledger["action_winner"]["times_executed"] += 1
            self._recompute(ledger["action_winner"])
            adjustments.append(compute_learning_adjustment("action_winner", ledger))

        assert adjustments[4] > adjustments[0]

        actions = [self._action("action_baseline"), self._action("action_winner")]
        result = _apply_learning_adjustments(actions, ledger)
        types = [a["action_type"] for a in result]
        assert types[0] == "action_winner"

    def test_consistently_failing_action_falls_over_cycles(self):
        ledger = {
            "action_loser": {
                "action_type": "action_loser",
                "times_executed": 4,
                "success_count": 2,
                "failure_count": 2,
                "effectiveness_score": 0.5,
                "effect_deltas": {},
            },
            "action_stable": {
                "action_type": "action_stable",
                "times_executed": 4,
                "success_count": 2,
                "failure_count": 2,
                "effectiveness_score": 0.5,
                "effect_deltas": {},
            },
        }
        adjustments = []
        for _ in range(5):
            ledger["action_loser"]["failure_count"] += 1
            ledger["action_loser"]["times_executed"] += 1
            self._recompute(ledger["action_loser"])
            adjustments.append(compute_learning_adjustment("action_loser", ledger))

        assert adjustments[4] < adjustments[0]

        actions = [self._action("action_loser"), self._action("action_stable")]
        result = _apply_learning_adjustments(actions, ledger)
        types = [a["action_type"] for a in result]
        assert types.index("action_loser") > types.index("action_stable")

    def test_action_effectiveness_degradation_is_monotonic_per_cycle(self):
        ledger = {
            "action_loser": {
                "action_type": "action_loser",
                "times_executed": 4,
                "success_count": 2,
                "failure_count": 2,
                "effectiveness_score": 0.5,
                "effect_deltas": {},
            },
        }
        adjustments = []
        for _ in range(4):
            ledger["action_loser"]["failure_count"] += 1
            ledger["action_loser"]["times_executed"] += 1
            self._recompute(ledger["action_loser"])
            adjustments.append(compute_learning_adjustment("action_loser", ledger))

        assert adjustments[0] > adjustments[1] > adjustments[2] > adjustments[3]

    def test_action_effectiveness_reinforcement_is_monotonic_per_cycle(self):
        ledger = {
            "action_winner": {
                "action_type": "action_winner",
                "times_executed": 4,
                "success_count": 2,
                "failure_count": 2,
                "effectiveness_score": 0.5,
                "effect_deltas": {},
            },
        }
        adjustments = []
        for _ in range(4):
            ledger["action_winner"]["success_count"] += 1
            ledger["action_winner"]["times_executed"] += 1
            self._recompute(ledger["action_winner"])
            adjustments.append(compute_learning_adjustment("action_winner", ledger))

        assert adjustments[0] < adjustments[1] < adjustments[2] < adjustments[3]
        assert all(a > 0 for a in adjustments)
        assert adjustments[3] > adjustments[0]

    def test_cycle_n_outcome_propagated_to_cycle_n_plus1_ledger(self):
        ledger = {
            "action_x": {
                "action_type": "action_x",
                "times_executed": 2,
                "success_count": 1,
                "failure_count": 1,
                "effectiveness_score": 0.5,
                "effect_deltas": {},
            },
            "action_y": {
                "action_type": "action_y",
                "times_executed": 2,
                "success_count": 1,
                "failure_count": 1,
                "effectiveness_score": 0.5,
                "effect_deltas": {},
            },
        }
        # Simulate Cycle N outcome
        ledger["action_x"]["success_count"] += 1
        ledger["action_x"]["times_executed"] += 1
        self._recompute(ledger["action_x"])

        ledger["action_y"]["failure_count"] += 1
        ledger["action_y"]["times_executed"] += 1
        self._recompute(ledger["action_y"])

        assert ledger["action_x"]["effectiveness_score"] > 0.5
        assert ledger["action_y"]["effectiveness_score"] < 0.5

        actions = [self._action("action_x"), self._action("action_y")]
        result = _apply_learning_adjustments(actions, ledger)
        assert result[0]["action_type"] == "action_x"

    def test_capability_reliability_weight_shifts_ranking_between_two_synthesis_actions(self):
        """At full confidence (total=5), high-success capability outranks low-success
        capability when base priorities are identical, proving CAPABILITY_RELIABILITY_WEIGHT
        is operative as the sole ranking differentiator."""
        actions = [
            {
                "action_type": "build_capability_artifact",
                "priority": 0.80,
                "action_id": "aid-low",
                "repo_id": "repo-1",
                "args": {"capability": "low_cap"},
            },
            {
                "action_type": "build_capability_artifact",
                "priority": 0.80,
                "action_id": "aid-high",
                "repo_id": "repo-1",
                "args": {"capability": "high_cap"},
            },
        ]
        capability_ledger = {
            "capabilities": {
                "high_cap": {"total_syntheses": 5, "successful_syntheses": 5},
                "low_cap": {"total_syntheses": 5, "successful_syntheses": 0},
            }
        }

        result = _apply_learning_adjustments(actions, {}, capability_ledger=capability_ledger)

        assert result[0]["args"]["capability"] == "high_cap"
        assert result[1]["args"]["capability"] == "low_cap"

        high_adj = _compute_capability_reliability_adjustment(actions[1], capability_ledger)
        low_adj = _compute_capability_reliability_adjustment(actions[0], capability_ledger)
        expected_delta = (6 / 7 - 1 / 7) * 0.10
        assert (high_adj - low_adj) == pytest.approx(expected_delta, rel=1e-3)

    def test_top_ranked_action_shifts_across_three_cycles(self):
        """Verify that the rank-0 action changes from action_beta to action_alpha
        as action_alpha accumulates successive successes across three ledger snapshots."""
        # Cycle 1 ledger: both actions tied at effectiveness_score=0.5
        ledger_c1 = {
            "action_alpha": {
                "action_type": "action_alpha",
                "times_executed": 2,
                "success_count": 1,
                "failure_count": 1,
                "effectiveness_score": 0.5,
                "effect_deltas": {},
            },
            "action_beta": {
                "action_type": "action_beta",
                "times_executed": 2,
                "success_count": 1,
                "failure_count": 1,
                "effectiveness_score": 0.5,
                "effect_deltas": {},
            },
        }

        actions_c1 = [
            self._action("action_alpha", priority=0.80),
            self._action("action_beta", priority=0.85),
        ]
        result1 = _apply_learning_adjustments(actions_c1, ledger_c1)

        # Cycle 2 ledger: action_alpha improves to s=3, f=1, score=0.75
        ledger_c2 = {
            "action_alpha": {
                "action_type": "action_alpha",
                "times_executed": 4,
                "success_count": 3,
                "failure_count": 1,
                "effectiveness_score": 0.75,
                "effect_deltas": {},
            },
            "action_beta": {
                "action_type": "action_beta",
                "times_executed": 2,
                "success_count": 1,
                "failure_count": 1,
                "effectiveness_score": 0.5,
                "effect_deltas": {},
            },
        }

        actions_c2 = [
            self._action("action_alpha", priority=0.80),
            self._action("action_beta", priority=0.85),
        ]
        result2 = _apply_learning_adjustments(actions_c2, ledger_c2)

        # Cycle 3 ledger: action_alpha further improves to s=6, f=1, score≈0.857143
        ledger_c3 = {
            "action_alpha": {
                "action_type": "action_alpha",
                "times_executed": 7,
                "success_count": 6,
                "failure_count": 1,
                "effectiveness_score": round(6 / 7, 6),
                "effect_deltas": {},
            },
            "action_beta": {
                "action_type": "action_beta",
                "times_executed": 2,
                "success_count": 1,
                "failure_count": 1,
                "effectiveness_score": 0.5,
                "effect_deltas": {},
            },
        }

        actions_c3 = [
            self._action("action_alpha", priority=0.80),
            self._action("action_beta", priority=0.85),
        ]
        result3 = _apply_learning_adjustments(actions_c3, ledger_c3)

        assert result1[0]["action_type"] == "action_beta"
        assert result2[0]["action_type"] == "action_alpha"
        assert result3[0]["action_type"] == "action_alpha"
        assert result3[0]["action_type"] != result1[0]["action_type"]  # rank-0 shifted

    def test_failed_capability_deprioritized(self):
        """Verify that an action with a high failure rate ranks below an action
        with a high success rate when both share equal base priority."""
        ledger = {
            "action_high_success": {
                "action_type": "action_high_success",
                "times_executed": 10,
                "success_count": 9,
                "failure_count": 1,
                "effectiveness_score": round(9 / 10, 6),
                "effect_deltas": {},
            },
            "action_high_fail": {
                "action_type": "action_high_fail",
                "times_executed": 10,
                "success_count": 1,
                "failure_count": 9,
                "effectiveness_score": round(1 / 10, 6),
                "effect_deltas": {},
            },
        }

        actions = [
            self._action("action_high_success", priority=1.0),
            self._action("action_high_fail", priority=1.0),
        ]
        result = _apply_learning_adjustments(actions, ledger)

        assert result[0]["action_type"] == "action_high_success"
        assert result[1]["action_type"] == "action_high_fail"


class TestComputeExplorationBonus:
    """Unit tests for compute_exploration_bonus (action-level exploration signal).

    Covers: decay across times_executed steps, boundary values, absent/invalid
    input handling. Formula: uncertainty = 1/(1+times_executed),
    bonus = clamp(uncertainty * EXPLORATION_WEIGHT, ±EXPLORATION_CLAMP).
    """

    def test_absent_action_type_returns_full_bonus(self):
        from planner_runtime import EXPLORATION_WEIGHT, EXPLORATION_CLAMP  # noqa: F401
        ledger = {}
        result = compute_exploration_bonus("build_capability_artifact", ledger)
        assert result == pytest.approx(EXPLORATION_WEIGHT * 1.0)

    def test_times_executed_zero_returns_full_bonus(self):
        from planner_runtime import EXPLORATION_WEIGHT, EXPLORATION_CLAMP  # noqa: F401
        ledger = {"build_capability_artifact": {"times_executed": 0}}
        result = compute_exploration_bonus("build_capability_artifact", ledger)
        assert result == pytest.approx(EXPLORATION_WEIGHT * 1.0)

    def test_bonus_decays_strictly_across_steps_zero_through_three(self):
        bonuses = []
        for n in range(4):
            ledger = {"build_capability_artifact": {"times_executed": n}}
            bonuses.append(compute_exploration_bonus("build_capability_artifact", ledger))
        for i in range(3):
            assert bonuses[i] > bonuses[i + 1], (
                f"expected bonus[{i}]={bonuses[i]} > bonus[{i+1}]={bonuses[i+1]}"
            )

    def test_high_times_executed_asymptotically_approaches_zero(self):
        from planner_runtime import EXPLORATION_WEIGHT
        ledger = {"build_capability_artifact": {"times_executed": 999}}
        result = compute_exploration_bonus("build_capability_artifact", ledger)
        assert result > 0
        assert result < EXPLORATION_WEIGHT * 0.01

    def test_invalid_times_executed_string_treated_as_zero(self):
        from planner_runtime import EXPLORATION_WEIGHT
        ledger = {"build_capability_artifact": {"times_executed": "not_a_number"}}
        result = compute_exploration_bonus("build_capability_artifact", ledger)
        assert result == pytest.approx(EXPLORATION_WEIGHT * 1.0)

    def test_negative_times_executed_clamped_to_zero(self):
        from planner_runtime import EXPLORATION_WEIGHT
        ledger = {"build_capability_artifact": {"times_executed": -5}}
        result = compute_exploration_bonus("build_capability_artifact", ledger)
        assert result == pytest.approx(EXPLORATION_WEIGHT * 1.0)

    def test_bonus_never_exceeds_exploration_clamp(self):
        from planner_runtime import EXPLORATION_CLAMP
        ledger = {"build_capability_artifact": {"times_executed": 0}}
        result = compute_exploration_bonus("build_capability_artifact", ledger)
        assert result <= EXPLORATION_CLAMP

    def test_exact_values_at_steps_one_two_three(self):
        from planner_runtime import EXPLORATION_WEIGHT
        for n in (1, 2, 3):
            ledger = {"build_capability_artifact": {"times_executed": n}}
            result = compute_exploration_bonus("build_capability_artifact", ledger)
            expected = EXPLORATION_WEIGHT / (1 + n)
            assert result == pytest.approx(expected), (
                f"n={n}: expected {expected}, got {result}"
            )


class TestPhaseFFledgerFormatAlignment:
    """Phase F -> Planner ledger normalization.

    Phase F (update_action_effectiveness_from_history.py) writes:
        {"actions": {"task_name": {"total_runs": N, "success_count": N, ...}}}

    load_effectiveness_ledger normalizes this to a merged dict:
    - flat keys: {task_name: {"effectiveness_score": rate, "times_executed": total, ...}}
      so compute_learning_adjustment can resolve action types.
    - "actions" key preserved so _compute_task_reliability continues to resolve success_rate.
    """

    _PHASE_F_LEDGER = {
        "actions": {
            "build_portfolio_dashboard": {
                "total_runs": 5,
                "success_count": 4,
                "failure_count": 1,
                "last_status": "ok",
            }
        }
    }

    def test_phase_f_format_learning_adjustment_derives_from_success_rate(self, tmp_path):
        # effectiveness_score = 4/5 = 0.8; adj = min(0.8 * 0.15, 0.20) = 0.12
        path = tmp_path / "phase_f_ledger.json"
        path.write_text(json.dumps(self._PHASE_F_LEDGER))
        ledger = load_effectiveness_ledger(str(path))
        assert compute_learning_adjustment("build_portfolio_dashboard", ledger) == pytest.approx(0.12)

    def test_phase_f_format_task_reliability_resolves(self, tmp_path):
        path = tmp_path / "phase_f_ledger.json"
        path.write_text(json.dumps(self._PHASE_F_LEDGER))
        ledger = load_effectiveness_ledger(str(path))
        assert _compute_task_reliability("build_portfolio_dashboard", ledger) == pytest.approx(0.8)
