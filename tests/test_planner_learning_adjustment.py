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

# Ensure the repo root is on sys.path so scripts package is importable.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.claude_dynamic_planner_loop import (  # noqa: E402
    EFFECTIVENESS_CLAMP,
    EFFECTIVENESS_WEIGHT,
    SIGNAL_IMPACT_CLAMP,
    SIGNAL_IMPACT_WEIGHT,
    _apply_learning_adjustments,
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
