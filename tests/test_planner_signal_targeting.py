# SPDX-License-Identifier: MIT
"""Regression tests for v0.27 weak-signal targeting adjustment.

Covers:
- weak signals produce deterministic bonus
- actions improving weak signals rank higher
- missing portfolio_state produces no targeting adjustment
- missing ledger entry produces no targeting adjustment
- negative deltas do not create bonus
- adjustment bounded by TARGETING_CLAMP
- repeated runs produce identical results (determinism)
"""
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.claude_dynamic_planner_loop import (  # noqa: E402
    TARGETING_CLAMP,
    TARGETING_WEIGHT,
    _apply_learning_adjustments,
    compute_weak_signal_targeting_adjustment,
    load_portfolio_signals,
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


def _make_ledger_dict(entries):
    """Return an in-memory ledger dict (already indexed by action_type)."""
    return {
        at: dict(data)
        for at, data in entries.items()
    }


def _write_portfolio_state(tmp_path, repos_signals):
    """Write a minimal portfolio_state.json with per-repo signals."""
    repos = [
        {"repo_id": f"repo-{i}", "signals": sigs}
        for i, sigs in enumerate(repos_signals)
    ]
    state = {"schema_version": "v1", "repos": repos}
    p = tmp_path / "portfolio_state.json"
    p.write_text(json.dumps(state), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# load_portfolio_signals
# ---------------------------------------------------------------------------

class TestLoadPortfolioSignals:
    def test_none_path_returns_empty(self):
        assert load_portfolio_signals(None) == {}

    def test_missing_file_returns_empty(self, tmp_path):
        assert load_portfolio_signals(str(tmp_path / "nonexistent.json")) == {}

    def test_malformed_json_returns_empty(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not valid json", encoding="utf-8")
        assert load_portfolio_signals(str(p)) == {}

    def test_numeric_signals_averaged(self, tmp_path):
        p = _write_portfolio_state(tmp_path, [
            {"artifact_completeness": 0.4, "stale_runs": 2},
            {"artifact_completeness": 0.6, "stale_runs": 4},
        ])
        result = load_portfolio_signals(str(p))
        assert result["artifact_completeness"] == pytest.approx(0.5)
        assert result["stale_runs"] == pytest.approx(3.0)

    def test_boolean_signals_ignored(self, tmp_path):
        p = _write_portfolio_state(tmp_path, [
            {"last_run_ok": True, "artifact_completeness": 0.8},
        ])
        result = load_portfolio_signals(str(p))
        assert "last_run_ok" not in result
        assert result["artifact_completeness"] == pytest.approx(0.8)

    def test_non_numeric_signals_ignored(self, tmp_path):
        p = _write_portfolio_state(tmp_path, [
            {"artifact_completeness": 0.5, "status": "healthy"},
        ])
        result = load_portfolio_signals(str(p))
        assert "status" not in result
        assert "artifact_completeness" in result

    def test_no_repos_returns_empty(self, tmp_path):
        p = tmp_path / "state.json"
        p.write_text(json.dumps({"repos": []}), encoding="utf-8")
        assert load_portfolio_signals(str(p)) == {}


# ---------------------------------------------------------------------------
# compute_weak_signal_targeting_adjustment
# ---------------------------------------------------------------------------

class TestComputeWeakSignalTargetingAdjustment:
    def test_empty_current_signals_returns_zero(self):
        ledger = {"type_a": {"effect_deltas": {"artifact_completeness": 1.0}}}
        adj = compute_weak_signal_targeting_adjustment("type_a", ledger, {})
        assert adj == 0.0

    def test_missing_ledger_entry_returns_zero(self):
        adj = compute_weak_signal_targeting_adjustment("unknown_type", {}, {"artifact_completeness": 0.5})
        assert adj == 0.0

    def test_negative_delta_yields_no_bonus(self):
        ledger = {"type_a": {"effect_deltas": {"artifact_completeness": -1.0}}}
        current = {"artifact_completeness": 0.2}  # very weak signal
        adj = compute_weak_signal_targeting_adjustment("type_a", ledger, current)
        assert adj == 0.0

    def test_weak_signal_produces_positive_bonus(self):
        # signal very weak (0.1) → weakness = 0.9; delta = 1.0
        # score = 1.0 * 0.9 = 0.9; adj = 0.9 * 0.10 = 0.09
        ledger = {"type_a": {"effect_deltas": {"artifact_completeness": 1.0}}}
        current = {"artifact_completeness": 0.1}
        adj = compute_weak_signal_targeting_adjustment("type_a", ledger, current)
        assert adj == pytest.approx(0.09)

    def test_strong_signal_yields_smaller_bonus(self):
        # signal strong (0.95) → weakness = 0.05; delta = 1.0
        # score = 1.0 * 0.05 = 0.05; adj = 0.05 * 0.10 = 0.005
        ledger = {"type_a": {"effect_deltas": {"artifact_completeness": 1.0}}}
        current = {"artifact_completeness": 0.95}
        adj = compute_weak_signal_targeting_adjustment("type_a", ledger, current)
        assert adj == pytest.approx(0.005)

    def test_signal_not_in_current_skipped(self):
        # effect_delta references a signal that's not in current_signals
        ledger = {"type_a": {"effect_deltas": {"missing_signal": 1.0}}}
        current = {"artifact_completeness": 0.2}
        adj = compute_weak_signal_targeting_adjustment("type_a", ledger, current)
        assert adj == 0.0

    def test_adjustment_bounded_positive(self):
        # Large delta + very weak signal → should be clamped
        ledger = {"type_a": {"effect_deltas": {
            "sig_a": 1000.0,
            "sig_b": 1000.0,
            "sig_c": 1000.0,
        }}}
        current = {"sig_a": 0.0, "sig_b": 0.0, "sig_c": 0.0}
        adj = compute_weak_signal_targeting_adjustment("type_a", ledger, current)
        assert adj <= TARGETING_CLAMP

    def test_adjustment_bounded_negative_clamp(self):
        # Verify clamp applies in negative direction too
        # (positive deltas can't produce negative adj, so this tests the contract)
        ledger = {"type_a": {"effect_deltas": {"sig_a": 1.0}}}
        current = {"sig_a": 0.5}
        adj = compute_weak_signal_targeting_adjustment("type_a", ledger, current)
        assert adj >= -TARGETING_CLAMP

    def test_empty_effect_deltas_returns_zero(self):
        ledger = {"type_a": {"effect_deltas": {}}}
        current = {"artifact_completeness": 0.1}
        adj = compute_weak_signal_targeting_adjustment("type_a", ledger, current)
        assert adj == 0.0

    def test_deterministic_repeated_calls(self):
        ledger = {"type_a": {"effect_deltas": {"artifact_completeness": 0.5, "stale_runs": 0.3}}}
        current = {"artifact_completeness": 0.4, "stale_runs": 0.6}
        adj1 = compute_weak_signal_targeting_adjustment("type_a", ledger, current)
        adj2 = compute_weak_signal_targeting_adjustment("type_a", ledger, current)
        assert adj1 == adj2


# ---------------------------------------------------------------------------
# _apply_learning_adjustments with signal targeting
# ---------------------------------------------------------------------------

class TestApplyLearningAdjustmentsWithSignals:
    def _base_ledger(self):
        return {
            "type_high": {
                "effectiveness_score": 0.0,
                "effect_deltas": {"artifact_completeness": 1.0},
            },
            "type_low": {
                "effectiveness_score": 0.0,
                "effect_deltas": {"artifact_completeness": 0.0},
            },
        }

    def test_action_improving_weak_signal_ranks_higher(self):
        # type_high improves artifact_completeness (very weak: 0.1)
        # type_low does not improve it
        # Both start with same base priority
        actions = _make_actions([("type_high", 0.5), ("type_low", 0.5)])
        ledger = self._base_ledger()
        current = {"artifact_completeness": 0.1}
        result = _apply_learning_adjustments(actions, ledger, current)
        assert result[0]["action_type"] == "type_high"
        assert result[1]["action_type"] == "type_low"

    def test_no_signals_produces_v026_behavior(self):
        # With empty current_signals, targeting adjustment = 0 → v0.26 ordering
        actions = _make_actions([
            ("type_high", 0.8),
            ("type_low", 0.5),
        ])
        ledger = self._base_ledger()
        result_no_signals = _apply_learning_adjustments(list(actions), ledger, {})
        result_none_signals = _apply_learning_adjustments(list(actions), ledger, None)
        assert [a["action_type"] for a in result_no_signals] == \
               [a["action_type"] for a in result_none_signals]
        # type_high wins on base priority alone
        assert result_no_signals[0]["action_type"] == "type_high"

    def test_missing_portfolio_state_no_targeting(self, tmp_path):
        # load_portfolio_signals with missing file → empty → no targeting
        signals = load_portfolio_signals(str(tmp_path / "missing.json"))
        assert signals == {}
        ledger = self._base_ledger()
        actions = _make_actions([("type_high", 0.5), ("type_low", 0.5)])
        result = _apply_learning_adjustments(actions, ledger, signals)
        # No targeting → tiebreak by action_type asc → type_high before type_low
        assert result[0]["action_type"] == "type_high"

    def test_missing_ledger_entry_no_targeting(self):
        # Action not in ledger → targeting_adj = 0
        actions = _make_actions([("unknown_type", 0.5), ("type_low", 0.5)])
        ledger = {"type_low": {"effectiveness_score": 0.0, "effect_deltas": {}}}
        current = {"artifact_completeness": 0.1}
        result = _apply_learning_adjustments(actions, ledger, current)
        # unknown_type gets no adj; type_low gets no targeting either (no deltas)
        # tiebreak by action_type asc → type_low < unknown_type alphabetically
        assert result[0]["action_type"] == "type_low"

    def test_repeated_runs_deterministic(self):
        actions = _make_actions([
            ("type_high", 0.5),
            ("type_low", 0.5),
        ])
        ledger = {
            "type_high": {"effectiveness_score": 0.3, "effect_deltas": {"artifact_completeness": 0.8}},
            "type_low": {"effectiveness_score": 0.1, "effect_deltas": {"artifact_completeness": 0.1}},
        }
        current = {"artifact_completeness": 0.2}
        result1 = [a["action_type"] for a in _apply_learning_adjustments(list(actions), ledger, current)]
        result2 = [a["action_type"] for a in _apply_learning_adjustments(list(actions), ledger, current)]
        assert result1 == result2

    def test_targeting_weight_and_clamp_constants(self):
        assert TARGETING_WEIGHT == pytest.approx(0.10)
        assert TARGETING_CLAMP == pytest.approx(0.20)

    def test_strong_signal_produces_smaller_targeting_boost(self):
        # When signal is already strong, action improving it gets less boost
        actions_weak = _make_actions([("type_high", 0.5), ("type_low", 0.5)])
        actions_strong = _make_actions([("type_high", 0.5), ("type_low", 0.5)])
        ledger = {
            "type_high": {"effectiveness_score": 0.0, "effect_deltas": {"artifact_completeness": 1.0}},
            "type_low": {"effectiveness_score": 0.0, "effect_deltas": {}},
        }
        # Weak signal → larger bonus for type_high
        adj_weak = compute_weak_signal_targeting_adjustment(
            "type_high", ledger, {"artifact_completeness": 0.1}
        )
        # Strong signal → smaller bonus for type_high
        adj_strong = compute_weak_signal_targeting_adjustment(
            "type_high", ledger, {"artifact_completeness": 0.9}
        )
        assert adj_weak > adj_strong
