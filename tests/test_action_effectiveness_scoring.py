# SPDX-License-Identifier: MIT
"""Scoring tests for Action Effectiveness Ledger v1.

Verifies exact arithmetic for risk/health deltas, success rate,
effectiveness score, classification thresholds, and priority adjustments.
All expected values are hand-computed from the spec formulas.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mcp_governance_orchestrator.action_effectiveness import build_action_effectiveness_ledger


# ---------------------------------------------------------------------------
# Fixture helpers (shared with contract tests, duplicated to keep files independent)
# ---------------------------------------------------------------------------

def _repo(repo_id: str, risk: str, health: float, actions: list | None = None) -> dict:
    return {
        "repo_id": repo_id,
        "status": "failing",
        "health_score": health,
        "risk_level": risk,
        "signals": {},
        "open_issues": [],
        "recommended_actions": actions or [],
        "action_history": [],
        "cooldowns": [],
        "escalations": [],
    }


def _state(*repos) -> dict:
    return {
        "schema_version": "v1",
        "portfolio_id": "test",
        "generated_at": "",
        "summary": {},
        "repos": list(repos),
        "portfolio_recommendations": [],
    }


def _rec(before, after, executed) -> dict:
    return {"before_state": before, "after_state": after, "executed_actions": executed}


def _exe(action_type: str, repo_id: str) -> dict:
    return {"action_type": action_type, "repo_id": repo_id}


def _build(records) -> dict:
    return build_action_effectiveness_ledger(records, generated_at="")


def _row(ledger: dict, action_type: str) -> dict:
    return next(r for r in ledger["action_types"] if r["action_type"] == action_type)


# ---------------------------------------------------------------------------
# Risk delta
# ---------------------------------------------------------------------------

class TestRiskDelta:
    def test_critical_to_low_risk_delta_minus_3(self):
        """critical(3) → low(0): delta = 0−3 = −3."""
        rec = _rec(
            _state(_repo("r1", "critical", 0.4)),
            _state(_repo("r1", "low", 0.4)),
            [_exe("run_determinism_regression_suite", "r1")],
        )
        row = _row(_build([rec]), "run_determinism_regression_suite")
        assert row["avg_risk_delta"] == -3.0

    def test_low_to_critical_risk_delta_plus_3(self):
        """low(0) → critical(3): delta = 3."""
        rec = _rec(
            _state(_repo("r1", "low", 1.0)),
            _state(_repo("r1", "critical", 0.4)),
            [_exe("rerun_failed_task", "r1")],
        )
        row = _row(_build([rec]), "rerun_failed_task")
        assert row["avg_risk_delta"] == 3.0

    def test_no_risk_change_delta_zero(self):
        rec = _rec(
            _state(_repo("r1", "high", 0.6)),
            _state(_repo("r1", "high", 0.6)),
            [_exe("refresh_repo_health", "r1")],
        )
        row = _row(_build([rec]), "refresh_repo_health")
        assert row["avg_risk_delta"] == 0.0

    def test_avg_risk_delta_across_two_executions(self):
        """Two executions: −3 and −1 → avg = −2.0."""
        rec = _rec(
            _state(_repo("r1", "critical", 0.4), _repo("r2", "high", 0.6)),
            _state(_repo("r1", "low", 1.0), _repo("r2", "medium", 0.7)),
            [_exe("rerun_failed_task", "r1"), _exe("rerun_failed_task", "r2")],
        )
        row = _row(_build([rec]), "rerun_failed_task")
        assert row["avg_risk_delta"] == -2.0

    def test_risk_ranks_all_levels(self):
        """medium(1) → high(2): delta = +1."""
        rec = _rec(
            _state(_repo("r1", "medium", 0.8)),
            _state(_repo("r1", "high", 0.6)),
            [_exe("regenerate_missing_artifact", "r1")],
        )
        row = _row(_build([rec]), "regenerate_missing_artifact")
        assert row["avg_risk_delta"] == 1.0


# ---------------------------------------------------------------------------
# Health delta
# ---------------------------------------------------------------------------

class TestHealthDelta:
    def test_improvement(self):
        """0.4 → 1.0: delta = +0.6."""
        rec = _rec(
            _state(_repo("r1", "critical", 0.4)),
            _state(_repo("r1", "low", 1.0)),
            [_exe("run_determinism_regression_suite", "r1")],
        )
        row = _row(_build([rec]), "run_determinism_regression_suite")
        assert row["avg_health_delta"] == 0.6

    def test_degradation(self):
        """1.0 → 0.65: delta = −0.35."""
        rec = _rec(
            _state(_repo("r1", "low", 1.0)),
            _state(_repo("r1", "high", 0.65)),
            [_exe("refresh_repo_health", "r1")],
        )
        row = _row(_build([rec]), "refresh_repo_health")
        assert row["avg_health_delta"] == -0.35

    def test_no_change(self):
        rec = _rec(
            _state(_repo("r1", "medium", 0.75)),
            _state(_repo("r1", "medium", 0.75)),
            [_exe("refresh_repo_health", "r1")],
        )
        row = _row(_build([rec]), "refresh_repo_health")
        assert row["avg_health_delta"] == 0.0

    def test_avg_health_delta_rounded_to_2(self):
        """Two executions: +0.1 and +0.2 → avg = 0.15."""
        rec = _rec(
            _state(_repo("r1", "high", 0.6), _repo("r2", "high", 0.7)),
            _state(_repo("r1", "high", 0.7), _repo("r2", "high", 0.9)),
            [_exe("rerun_failed_task", "r1"), _exe("rerun_failed_task", "r2")],
        )
        row = _row(_build([rec]), "rerun_failed_task")
        assert row["avg_health_delta"] == 0.15


# ---------------------------------------------------------------------------
# Success rate
# ---------------------------------------------------------------------------

class TestSuccessRate:
    def test_success_when_risk_improves(self):
        """risk decreases → success regardless of health."""
        rec = _rec(
            _state(_repo("r1", "high", 0.5)),
            _state(_repo("r1", "low", 0.5)),   # health unchanged, risk improved
            [_exe("run_determinism_regression_suite", "r1")],
        )
        row = _row(_build([rec]), "run_determinism_regression_suite")
        assert row["success_rate"] == 1.0

    def test_success_when_health_improves(self):
        """health increases → success regardless of risk."""
        rec = _rec(
            _state(_repo("r1", "high", 0.5)),
            _state(_repo("r1", "high", 0.8)),  # risk unchanged, health improved
            [_exe("rerun_failed_task", "r1")],
        )
        row = _row(_build([rec]), "rerun_failed_task")
        assert row["success_rate"] == 1.0

    def test_failure_when_neither_improves(self):
        rec = _rec(
            _state(_repo("r1", "high", 0.6)),
            _state(_repo("r1", "high", 0.6)),
            [_exe("refresh_repo_health", "r1")],
        )
        row = _row(_build([rec]), "refresh_repo_health")
        assert row["success_rate"] == 0.0

    def test_failure_when_both_worsen(self):
        rec = _rec(
            _state(_repo("r1", "low", 1.0)),
            _state(_repo("r1", "critical", 0.4)),
            [_exe("refresh_repo_health", "r1")],
        )
        row = _row(_build([rec]), "refresh_repo_health")
        assert row["success_rate"] == 0.0

    def test_partial_success_rate(self):
        """2 out of 3 executions succeed → 0.67."""
        rec = _rec(
            _state(
                _repo("r1", "high", 0.5),
                _repo("r2", "high", 0.5),
                _repo("r3", "low", 1.0),
            ),
            _state(
                _repo("r1", "low", 0.9),   # improved
                _repo("r2", "medium", 0.7), # risk improved (high→medium)
                _repo("r3", "low", 1.0),   # no change → failure
            ),
            [
                _exe("rerun_failed_task", "r1"),
                _exe("rerun_failed_task", "r2"),
                _exe("rerun_failed_task", "r3"),
            ],
        )
        row = _row(_build([rec]), "rerun_failed_task")
        assert row["success_rate"] == 0.67

    def test_zero_executions_success_rate_zero(self):
        action_obj = {
            "action_id": "act", "action_type": "refresh_repo_health",
            "priority": 0.55, "reason": "r", "eligible": True,
            "blocked_by": [], "task_binding": {"task_id": "t", "args": {}},
        }
        rec = _rec(
            _state(_repo("r1", "medium", 0.8, actions=[action_obj])),
            _state(_repo("r1", "low", 1.0)),
            [],  # nothing executed
        )
        row = _row(_build([rec]), "refresh_repo_health")
        assert row["times_executed"] == 0
        assert row["success_rate"] == 0.0


# ---------------------------------------------------------------------------
# Effectiveness score
# ---------------------------------------------------------------------------

class TestEffectivenessScore:
    def test_perfect_score(self):
        """critical→low (risk_delta=−3), health 0.4→1.0 (+0.6).
        success_rate=1.0, norm_health=0.6, norm_risk=1.0
        score = 0.5*1.0 + 0.3*0.6 + 0.2*1.0 = 0.5+0.18+0.20 = 0.88
        """
        rec = _rec(
            _state(_repo("r1", "critical", 0.4)),
            _state(_repo("r1", "low", 1.0)),
            [_exe("run_determinism_regression_suite", "r1")],
        )
        row = _row(_build([rec]), "run_determinism_regression_suite")
        assert row["effectiveness_score"] == 0.88

    def test_zero_score_no_improvement(self):
        """No change → success_rate=0, deltas=0 → score=0.0."""
        rec = _rec(
            _state(_repo("r1", "high", 0.6)),
            _state(_repo("r1", "high", 0.6)),
            [_exe("refresh_repo_health", "r1")],
        )
        row = _row(_build([rec]), "refresh_repo_health")
        assert row["effectiveness_score"] == 0.0

    def test_zero_executions_score_zero(self):
        action_obj = {
            "action_id": "act", "action_type": "regenerate_missing_artifact",
            "priority": 0.85, "reason": "r", "eligible": True,
            "blocked_by": [], "task_binding": {"task_id": "t", "args": {}},
        }
        rec = _rec(
            _state(_repo("r1", "high", 0.0, actions=[action_obj])),
            _state(_repo("r1", "low", 1.0)),
            [],
        )
        row = _row(_build([rec]), "regenerate_missing_artifact")
        assert row["effectiveness_score"] == 0.0

    def test_health_improvement_only(self):
        """high→high (delta=0), health 0.5→1.0 (+0.5).
        success=1/1=1.0, norm_health=0.5, norm_risk=0.0
        score = 0.5*1.0 + 0.3*0.5 + 0.2*0.0 = 0.5+0.15+0.0 = 0.65
        """
        rec = _rec(
            _state(_repo("r1", "high", 0.5)),
            _state(_repo("r1", "high", 1.0)),
            [_exe("rerun_failed_task", "r1")],
        )
        row = _row(_build([rec]), "rerun_failed_task")
        assert row["effectiveness_score"] == 0.65

    def test_risk_improvement_only(self):
        """critical→low (delta=−3), health unchanged (0.6→0.6).
        success=1 (risk improved), success_rate=1.0, norm_health=clamp(0,0,1)=0.0,
        norm_risk=clamp(3/3,0,1)=1.0
        score = 0.5*1.0 + 0.3*0.0 + 0.2*1.0 = 0.70
        """
        rec = _rec(
            _state(_repo("r1", "critical", 0.6)),
            _state(_repo("r1", "low", 0.6)),
            [_exe("run_determinism_regression_suite", "r1")],
        )
        row = _row(_build([rec]), "run_determinism_regression_suite")
        assert row["effectiveness_score"] == 0.70

    def test_health_degradation_clamped_at_zero(self):
        """Health worsens (−0.3): norm_health = clamp(−0.3, 0, 1) = 0."""
        rec = _rec(
            _state(_repo("r1", "high", 0.9)),
            _state(_repo("r1", "low", 0.6)),   # risk improved, health fell
            [_exe("rerun_failed_task", "r1")],
        )
        row = _row(_build([rec]), "rerun_failed_task")
        # success=1 (risk improved), norm_health=0, norm_risk=clamp(2/3,0,1)≈0.67
        # score = 0.5 + 0 + 0.2*(2/3) = 0.5 + 0.1333... = 0.63 → rounds to 0.63
        assert row["avg_health_delta"] == -0.3
        norm_risk = round(min(2 / 3, 1.0), 10)
        expected = round(0.5 * 1.0 + 0.3 * 0.0 + 0.2 * norm_risk, 2)
        assert row["effectiveness_score"] == expected

    def test_worsened_risk_norm_risk_reduction_clamped_zero(self):
        """Risk worsens (low→critical, delta=+3): norm_risk = clamp(−3/3,0,1) = 0."""
        rec = _rec(
            _state(_repo("r1", "low", 1.0)),
            _state(_repo("r1", "critical", 1.0)),  # health unchanged, risk worsened
            [_exe("refresh_repo_health", "r1")],
        )
        row = _row(_build([rec]), "refresh_repo_health")
        # success=0 (neither improved), score=0.0
        assert row["effectiveness_score"] == 0.0
        assert row["avg_risk_delta"] == 3.0


# ---------------------------------------------------------------------------
# Classification thresholds
# ---------------------------------------------------------------------------

class TestClassificationThresholds:
    def _score_row(self, score: float) -> dict:
        """Build a synthetic ledger row at a known score via health-only improvement."""
        # effectiveness = 0.5*sr + 0.3*nh + 0.2*nr
        # We use: success_rate=1.0, norm_risk=0, and set health_delta = x
        # → score = 0.5 + 0.3*x  → x = (score - 0.5) / 0.3
        # Requires score >= 0.5 for positive health_delta.
        # For score < 0.5 we use zero executions (score=0.0) or worsening.
        if score == 0.0:
            # no change → failure → score 0.0
            rec = _rec(
                _state(_repo("r1", "low", 1.0)),
                _state(_repo("r1", "low", 1.0)),
                [_exe("refresh_repo_health", "r1")],
            )
            ledger = build_action_effectiveness_ledger([rec], generated_at="")
            return _row(ledger, "refresh_repo_health")

        health_before = 0.5
        health_delta = (score - 0.5) / 0.3
        health_after = round(min(health_before + health_delta, 1.0), 4)
        rec = _rec(
            _state(_repo("r1", "high", health_before)),
            _state(_repo("r1", "high", health_after)),
            [_exe("rerun_failed_task", "r1")],
        )
        ledger = build_action_effectiveness_ledger([rec], generated_at="")
        return _row(ledger, "rerun_failed_task")

    def test_effective_at_0_65(self):
        """score=0.65 → effective (boundary inclusive)."""
        # health_delta = (0.65-0.5)/0.3 = 0.5, health_after=1.0
        rec = _rec(
            _state(_repo("r1", "high", 0.5)),
            _state(_repo("r1", "high", 1.0)),
            [_exe("rerun_failed_task", "r1")],
        )
        ledger = build_action_effectiveness_ledger([rec], generated_at="")
        row = _row(ledger, "rerun_failed_task")
        assert row["effectiveness_score"] == 0.65
        assert row["classification"] == "effective"

    def test_effective_at_0_88(self):
        rec = _rec(
            _state(_repo("r1", "critical", 0.4)),
            _state(_repo("r1", "low", 1.0)),
            [_exe("run_determinism_regression_suite", "r1")],
        )
        row = _row(_build([rec]), "run_determinism_regression_suite")
        assert row["effectiveness_score"] == 0.88
        assert row["classification"] == "effective"

    def test_neutral_at_0_5(self):
        """score=0.5 → neutral (>= 0.40, < 0.65)."""
        rec = _rec(
            _state(_repo("r1", "high", 0.5)),
            _state(_repo("r1", "high", 0.5)),   # no change → failure
            [_exe("rerun_failed_task", "r1")],
        )
        # success_rate=0, no delta, score=0.0 → ineffective; need different fixture.
        # Use health_delta=0: success=0/1=0, score=0.0 is not 0.5.
        # For score=0.5 with success_rate=1.0 and zero deltas: score=0.5*1=0.5.
        # health improves by 0 (exactly 0.5 delta = 0 → fails). Use success=1, health=0.
        # success when health_delta>0 OR risk_delta<0. Use risk_delta=-1, health_delta=0:
        # success=1, success_rate=1.0, norm_health=0, norm_risk=1/3
        # score = 0.5 + 0 + 0.2*(1/3) = 0.5 + 0.0667 = 0.57 not 0.5.
        # Easier: success_rate=1.0, health_delta=0, norm_risk=0 → score=0.5
        # high→medium is risk_delta=-1, which counts as success and adds norm_risk.
        # For score exactly 0.5 we need risk stays same, health 0→0 (no improvement,
        # but then success=0).  Use two executions: 1 success, 1 failure, zero deltas avg.
        # success_rate=0.5, norm_health=0, norm_risk=0 → score=0.25 → not neutral.
        # Use success_rate=1.0 via health improvement of exactly 0 is impossible.
        # Use: health improves tiny (> 0 counts as success), avg_health small.
        # health 0.5 → 0.51, delta=0.01. success=1.0. norm_health=0.01.
        # score = 0.5 + 0.3*0.01 + 0 = 0.503 → rounds to 0.50.
        rec2 = _rec(
            _state(_repo("r1", "high", 0.5)),
            _state(_repo("r1", "high", 0.51)),
            [_exe("rerun_failed_task", "r1")],
        )
        ledger = build_action_effectiveness_ledger([rec2], generated_at="")
        row2 = _row(ledger, "rerun_failed_task")
        assert row2["effectiveness_score"] == 0.50
        assert row2["classification"] == "neutral"

    def test_ineffective_at_0_0(self):
        rec = _rec(
            _state(_repo("r1", "high", 0.6)),
            _state(_repo("r1", "high", 0.6)),
            [_exe("refresh_repo_health", "r1")],
        )
        row = _row(_build([rec]), "refresh_repo_health")
        assert row["effectiveness_score"] == 0.0
        assert row["classification"] == "ineffective"

    def test_boundary_just_below_0_65_is_neutral(self):
        """score < 0.65 → neutral if >= 0.40."""
        # health 0.5 → 0.94 gives delta=0.44. success=1.0.
        # score = 0.5 + 0.3*0.44 + 0 = 0.5 + 0.132 = 0.632 → 0.63
        rec = _rec(
            _state(_repo("r1", "high", 0.5)),
            _state(_repo("r1", "high", 0.94)),
            [_exe("rerun_failed_task", "r1")],
        )
        row = _row(_build([rec]), "rerun_failed_task")
        assert row["effectiveness_score"] == 0.63
        assert row["classification"] == "neutral"

    def test_boundary_just_below_0_40_is_ineffective(self):
        """score < 0.40 → ineffective."""
        # success_rate=0, no delta → score=0.0 → ineffective
        rec = _rec(
            _state(_repo("r1", "medium", 0.8)),
            _state(_repo("r1", "medium", 0.8)),
            [_exe("refresh_repo_health", "r1")],
        )
        row = _row(_build([rec]), "refresh_repo_health")
        assert row["classification"] == "ineffective"


# ---------------------------------------------------------------------------
# Priority adjustment thresholds
# ---------------------------------------------------------------------------

class TestPriorityAdjustment:
    def _adj_for_score(self, score: float) -> float:
        if score == 0.0:
            rec = _rec(
                _state(_repo("r1", "low", 1.0)),
                _state(_repo("r1", "low", 1.0)),
                [_exe("refresh_repo_health", "r1")],
            )
            ledger = build_action_effectiveness_ledger([rec], generated_at="")
            return _row(ledger, "refresh_repo_health")["recommended_priority_adjustment"]

        # success_rate=1.0, no risk change, health_delta = (score-0.5)/0.3
        health_delta = (score - 0.5) / 0.3
        health_after = round(0.5 + health_delta, 4)
        rec = _rec(
            _state(_repo("r1", "high", 0.5)),
            _state(_repo("r1", "high", min(health_after, 1.0))),
            [_exe("rerun_failed_task", "r1")],
        )
        ledger = build_action_effectiveness_ledger([rec], generated_at="")
        return _row(ledger, "rerun_failed_task")["recommended_priority_adjustment"]

    def test_adj_plus_0_10_at_score_0_88(self):
        rec = _rec(
            _state(_repo("r1", "critical", 0.4)),
            _state(_repo("r1", "low", 1.0)),
            [_exe("run_determinism_regression_suite", "r1")],
        )
        row = _row(_build([rec]), "run_determinism_regression_suite")
        assert row["effectiveness_score"] == 0.88
        assert row["recommended_priority_adjustment"] == 0.10

    def test_adj_plus_0_05_at_score_0_65(self):
        """score=0.65 is the boundary for +0.05."""
        rec = _rec(
            _state(_repo("r1", "high", 0.5)),
            _state(_repo("r1", "high", 1.0)),
            [_exe("rerun_failed_task", "r1")],
        )
        row = _row(_build([rec]), "rerun_failed_task")
        assert row["effectiveness_score"] == 0.65
        assert row["recommended_priority_adjustment"] == 0.05

    def test_adj_zero_at_score_0_5(self):
        """0.40 <= score < 0.65 → 0.00."""
        rec = _rec(
            _state(_repo("r1", "high", 0.5)),
            _state(_repo("r1", "high", 0.51)),
            [_exe("rerun_failed_task", "r1")],
        )
        row = _row(_build([rec]), "rerun_failed_task")
        assert row["effectiveness_score"] == 0.50
        assert row["recommended_priority_adjustment"] == 0.00

    def test_adj_minus_0_05_at_score_0_0(self):
        rec = _rec(
            _state(_repo("r1", "high", 0.6)),
            _state(_repo("r1", "high", 0.6)),
            [_exe("refresh_repo_health", "r1")],
        )
        row = _row(_build([rec]), "refresh_repo_health")
        assert row["effectiveness_score"] == 0.0
        assert row["recommended_priority_adjustment"] == -0.05

    def test_adj_plus_0_10_boundary_at_0_80(self):
        """score=0.80 exactly → +0.10.
        0.5 + 0.3*x = 0.80 → x = 1.0, health_delta=1.0, health_after=1.5 clamped to 1.0.
        score = 0.5 + 0.3*clamp(1.0,0,1) + 0 = 0.5+0.30 = 0.80.
        """
        rec = _rec(
            _state(_repo("r1", "high", 0.0)),
            _state(_repo("r1", "high", 1.0)),
            [_exe("rerun_failed_task", "r1")],
        )
        row = _row(_build([rec]), "rerun_failed_task")
        assert row["effectiveness_score"] == 0.80
        assert row["recommended_priority_adjustment"] == 0.10


# ---------------------------------------------------------------------------
# Multiple records accumulation
# ---------------------------------------------------------------------------

class TestMultipleRecords:
    def test_two_records_same_action_type_accumulate(self):
        """Two records for same action_type: stats combine across both."""
        rec1 = _rec(
            _state(_repo("r1", "high", 0.5)),
            _state(_repo("r1", "low", 1.0)),
            [_exe("rerun_failed_task", "r1")],
        )
        rec2 = _rec(
            _state(_repo("r1", "high", 0.5)),
            _state(_repo("r1", "high", 0.5)),   # no improvement
            [_exe("rerun_failed_task", "r1")],
        )
        ledger = build_action_effectiveness_ledger([rec1, rec2], generated_at="")
        row = _row(ledger, "rerun_failed_task")
        assert row["times_executed"] == 2
        assert row["success_rate"] == 0.5   # 1 success out of 2

    def test_different_action_types_tracked_separately(self):
        before = _state(_repo("r1", "critical", 0.4), _repo("r2", "high", 0.6))
        after = _state(_repo("r1", "low", 1.0), _repo("r2", "low", 1.0))
        rec = _rec(before, after, [
            _exe("run_determinism_regression_suite", "r1"),
            _exe("rerun_failed_task", "r2"),
        ])
        ledger = build_action_effectiveness_ledger([rec], generated_at="")
        types = {r["action_type"] for r in ledger["action_types"]}
        assert "run_determinism_regression_suite" in types
        assert "rerun_failed_task" in types
        assert len(ledger["action_types"]) == 2

    def test_recommendations_from_all_records_counted(self):
        action_obj = {
            "action_id": "act", "action_type": "refresh_repo_health",
            "priority": 0.55, "reason": "r", "eligible": True,
            "blocked_by": [], "task_binding": {"task_id": "t", "args": {}},
        }
        rec1 = _rec(
            _state(_repo("r1", "medium", 0.8, actions=[action_obj])),
            _state(_repo("r1", "low", 1.0)),
            [],
        )
        rec2 = _rec(
            _state(_repo("r1", "medium", 0.8, actions=[action_obj])),
            _state(_repo("r1", "low", 1.0)),
            [],
        )
        ledger = build_action_effectiveness_ledger([rec1, rec2], generated_at="")
        row = _row(ledger, "refresh_repo_health")
        assert row["times_recommended"] == 2

    def test_empty_records_list(self):
        ledger = build_action_effectiveness_ledger([], generated_at="")
        assert ledger["action_types"] == []
        assert ledger["summary"]["actions_tracked"] == 0
