# SPDX-License-Identifier: MIT
"""Action-selection tests for portfolio_state v1.

Verifies that each rule fires exactly the right issues and actions with the
correct priorities, reasons, and task bindings; that clean signals produce no
output; and that action priority ordering is strictly descending.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcp_governance_orchestrator.portfolio_state import (
    ACTION_TASK_BINDINGS,
    build_portfolio_state,
)


def _build(signals):
    return build_portfolio_state(signals, generated_at="")


def _repo(signals):
    return _build(signals)["repos"][0]


# ---------------------------------------------------------------------------
# Baseline: clean signal → no actions, no issues
# ---------------------------------------------------------------------------

class TestCleanSignal:
    _SIGNAL = {
        "repo_id": "clean-repo",
        "last_run_ok": True,
        "artifact_completeness": 1.0,
        "determinism_ok": True,
        "recent_failures": 0,
        "stale_runs": 0,
    }

    def test_no_issues(self):
        assert _repo([self._SIGNAL])["open_issues"] == []

    def test_no_actions(self):
        assert _repo([self._SIGNAL])["recommended_actions"] == []

    def test_status_healthy(self):
        assert _repo([self._SIGNAL])["status"] == "healthy"

    def test_risk_low(self):
        assert _repo([self._SIGNAL])["risk_level"] == "low"

    def test_health_score_1(self):
        assert _repo([self._SIGNAL])["health_score"] == 1.0

    def test_no_portfolio_recommendations(self):
        assert _build([self._SIGNAL])["portfolio_recommendations"] == []


# ---------------------------------------------------------------------------
# Rule: stale_signals (stale_runs >= 3)
# ---------------------------------------------------------------------------

class TestStaleSignalsRule:
    _BASE = {
        "repo_id": "stale-repo",
        "last_run_ok": True,
        "artifact_completeness": 1.0,
        "determinism_ok": True,
        "recent_failures": 0,
        "stale_runs": 3,
    }

    def test_fires_at_threshold(self):
        types = [a["action_type"] for a in _repo([self._BASE])["recommended_actions"]]
        assert "refresh_repo_health" in types

    def test_does_not_fire_below_threshold(self):
        sig = dict(self._BASE)
        sig["stale_runs"] = 2
        assert _repo([sig])["recommended_actions"] == []

    def test_priority_is_0_55(self):
        action = next(
            a for a in _repo([self._BASE])["recommended_actions"]
            if a["action_type"] == "refresh_repo_health"
        )
        assert action["priority"] == 0.55

    def test_task_binding_task_id(self):
        action = next(
            a for a in _repo([self._BASE])["recommended_actions"]
            if a["action_type"] == "refresh_repo_health"
        )
        assert action["task_binding"]["task_id"] == ACTION_TASK_BINDINGS["refresh_repo_health"]

    def test_task_binding_args_empty(self):
        action = next(
            a for a in _repo([self._BASE])["recommended_actions"]
            if a["action_type"] == "refresh_repo_health"
        )
        assert action["task_binding"]["args"] == {}

    def test_issue_type_stale_signals(self):
        issues = _repo([self._BASE])["open_issues"]
        assert any(i["issue_type"] == "stale_signals" for i in issues)

    def test_issue_severity_medium(self):
        issue = next(i for i in _repo([self._BASE])["open_issues"] if i["issue_type"] == "stale_signals")
        assert issue["severity"] == "medium"

    def test_issue_reason(self):
        issue = next(i for i in _repo([self._BASE])["open_issues"] if i["issue_type"] == "stale_signals")
        assert issue["reason"] == "stale signals for 3 or more runs"

    def test_issue_status_open(self):
        issue = next(i for i in _repo([self._BASE])["open_issues"] if i["issue_type"] == "stale_signals")
        assert issue["status"] == "open"

    def test_action_reason(self):
        action = next(
            a for a in _repo([self._BASE])["recommended_actions"]
            if a["action_type"] == "refresh_repo_health"
        )
        assert action["reason"] == "stale signals for 3 or more runs"

    def test_status_stale(self):
        assert _repo([self._BASE])["status"] == "stale"

    def test_health_score_deduction(self):
        # 1.0 - 0.10 = 0.90
        assert _repo([self._BASE])["health_score"] == 0.90


# ---------------------------------------------------------------------------
# Rule: artifact_incomplete — partial (0 < completeness < 1)
# ---------------------------------------------------------------------------

class TestArtifactIncompletePartial:
    _BASE = {
        "repo_id": "partial-repo",
        "last_run_ok": True,
        "artifact_completeness": 0.5,
        "determinism_ok": True,
        "recent_failures": 0,
        "stale_runs": 0,
    }

    def test_action_fires(self):
        types = [a["action_type"] for a in _repo([self._BASE])["recommended_actions"]]
        assert "regenerate_missing_artifact" in types

    def test_priority_is_0_70(self):
        action = next(
            a for a in _repo([self._BASE])["recommended_actions"]
            if a["action_type"] == "regenerate_missing_artifact"
        )
        assert action["priority"] == 0.70

    def test_severity_medium(self):
        issue = next(
            i for i in _repo([self._BASE])["open_issues"]
            if i["issue_type"] == "artifact_incomplete"
        )
        assert issue["severity"] == "medium"

    def test_issue_reason_partial(self):
        issue = next(
            i for i in _repo([self._BASE])["open_issues"]
            if i["issue_type"] == "artifact_incomplete"
        )
        assert issue["reason"] == "required artifact set is incomplete"

    def test_action_reason_partial(self):
        action = next(
            a for a in _repo([self._BASE])["recommended_actions"]
            if a["action_type"] == "regenerate_missing_artifact"
        )
        assert action["reason"] == "required artifact set is incomplete"

    def test_status_degraded(self):
        assert _repo([self._BASE])["status"] == "degraded"

    def test_health_score_deduction(self):
        # 1.0 - 0.15 = 0.85
        assert _repo([self._BASE])["health_score"] == 0.85

    def test_task_binding_task_id(self):
        action = next(
            a for a in _repo([self._BASE])["recommended_actions"]
            if a["action_type"] == "regenerate_missing_artifact"
        )
        assert action["task_binding"]["task_id"] == ACTION_TASK_BINDINGS["regenerate_missing_artifact"]


# ---------------------------------------------------------------------------
# Rule: artifact_incomplete — zero completeness
# ---------------------------------------------------------------------------

class TestArtifactIncompleteZero:
    _BASE = {
        "repo_id": "zero-artifact-repo",
        "last_run_ok": False,
        "artifact_completeness": 0.0,
        "determinism_ok": True,
        "recent_failures": 0,
        "stale_runs": 0,
    }

    def test_priority_is_0_85(self):
        action = next(
            a for a in _repo([self._BASE])["recommended_actions"]
            if a["action_type"] == "regenerate_missing_artifact"
        )
        assert action["priority"] == 0.85

    def test_severity_high(self):
        issue = next(
            i for i in _repo([self._BASE])["open_issues"]
            if i["issue_type"] == "artifact_incomplete"
        )
        assert issue["severity"] == "high"

    def test_issue_reason_missing(self):
        issue = next(
            i for i in _repo([self._BASE])["open_issues"]
            if i["issue_type"] == "artifact_incomplete"
        )
        assert issue["reason"] == "required artifact set is completely missing"

    def test_action_reason_missing(self):
        action = next(
            a for a in _repo([self._BASE])["recommended_actions"]
            if a["action_type"] == "regenerate_missing_artifact"
        )
        assert action["reason"] == "required artifact set is completely missing"

    def test_health_score_deduction(self):
        # 1.0 - 0.30 = 0.70
        assert _repo([self._BASE])["health_score"] == 0.70

    def test_risk_high(self):
        assert _repo([self._BASE])["risk_level"] == "high"


# ---------------------------------------------------------------------------
# Rule: repeated_failure (recent_failures >= 2)
# ---------------------------------------------------------------------------

class TestRepeatedFailureRule:
    _BASE = {
        "repo_id": "fail-repo",
        "last_run_ok": False,
        "artifact_completeness": 1.0,
        "determinism_ok": True,
        "recent_failures": 2,
        "stale_runs": 0,
    }

    def test_action_fires(self):
        types = [a["action_type"] for a in _repo([self._BASE])["recommended_actions"]]
        assert "rerun_failed_task" in types

    def test_does_not_fire_at_one(self):
        sig = dict(self._BASE)
        sig["recent_failures"] = 1
        assert _repo([sig])["recommended_actions"] == []

    def test_priority_is_0_80(self):
        action = next(
            a for a in _repo([self._BASE])["recommended_actions"]
            if a["action_type"] == "rerun_failed_task"
        )
        assert action["priority"] == 0.80

    def test_severity_high(self):
        issue = next(
            i for i in _repo([self._BASE])["open_issues"]
            if i["issue_type"] == "repeated_failure"
        )
        assert issue["severity"] == "high"

    def test_issue_reason(self):
        issue = next(
            i for i in _repo([self._BASE])["open_issues"]
            if i["issue_type"] == "repeated_failure"
        )
        assert issue["reason"] == "task failed repeatedly in recent runs"

    def test_action_reason(self):
        action = next(
            a for a in _repo([self._BASE])["recommended_actions"]
            if a["action_type"] == "rerun_failed_task"
        )
        assert action["reason"] == "task failed repeatedly in recent runs"

    def test_status_failing(self):
        assert _repo([self._BASE])["status"] == "failing"

    def test_health_score_deduction(self):
        # 1.0 - 0.35 = 0.65
        assert _repo([self._BASE])["health_score"] == 0.65

    def test_task_binding_task_id(self):
        action = next(
            a for a in _repo([self._BASE])["recommended_actions"]
            if a["action_type"] == "rerun_failed_task"
        )
        assert action["task_binding"]["task_id"] == ACTION_TASK_BINDINGS["rerun_failed_task"]


# ---------------------------------------------------------------------------
# Rule: determinism_regression (determinism_ok == false)
# ---------------------------------------------------------------------------

class TestDeterminismRegressionRule:
    _BASE = {
        "repo_id": "nondeterministic-repo",
        "last_run_ok": False,
        "artifact_completeness": 1.0,
        "determinism_ok": False,
        "recent_failures": 0,
        "stale_runs": 0,
    }

    def test_action_fires(self):
        types = [a["action_type"] for a in _repo([self._BASE])["recommended_actions"]]
        assert "run_determinism_regression_suite" in types

    def test_priority_is_0_95(self):
        action = next(
            a for a in _repo([self._BASE])["recommended_actions"]
            if a["action_type"] == "run_determinism_regression_suite"
        )
        assert action["priority"] == 0.95

    def test_severity_critical(self):
        issue = next(
            i for i in _repo([self._BASE])["open_issues"]
            if i["issue_type"] == "determinism_regression"
        )
        assert issue["severity"] == "critical"

    def test_issue_reason(self):
        issue = next(
            i for i in _repo([self._BASE])["open_issues"]
            if i["issue_type"] == "determinism_regression"
        )
        assert issue["reason"] == "determinism regression detected"

    def test_action_reason(self):
        action = next(
            a for a in _repo([self._BASE])["recommended_actions"]
            if a["action_type"] == "run_determinism_regression_suite"
        )
        assert action["reason"] == "determinism regression detected"

    def test_status_failing(self):
        assert _repo([self._BASE])["status"] == "failing"

    def test_risk_critical(self):
        assert _repo([self._BASE])["risk_level"] == "critical"

    def test_health_score_deduction(self):
        # 1.0 - 0.60 = 0.40
        assert _repo([self._BASE])["health_score"] == 0.40

    def test_task_binding_task_id(self):
        action = next(
            a for a in _repo([self._BASE])["recommended_actions"]
            if a["action_type"] == "run_determinism_regression_suite"
        )
        assert action["task_binding"]["task_id"] == ACTION_TASK_BINDINGS["run_determinism_regression_suite"]


# ---------------------------------------------------------------------------
# Priority ordering
# ---------------------------------------------------------------------------

class TestPriorityOrdering:
    """All rules fire simultaneously; actions must be sorted priority desc."""

    _WORST = {
        "repo_id": "worst-repo",
        "last_run_ok": False,
        "artifact_completeness": 0.5,
        "determinism_ok": False,
        "recent_failures": 3,
        "stale_runs": 5,
    }

    def test_actions_sorted_priority_desc(self):
        actions = _repo([self._WORST])["recommended_actions"]
        priorities = [a["priority"] for a in actions]
        assert priorities == sorted(priorities, reverse=True)

    def test_determinism_action_is_first(self):
        actions = _repo([self._WORST])["recommended_actions"]
        assert actions[0]["action_type"] == "run_determinism_regression_suite"

    def test_all_four_actions_present(self):
        types = {a["action_type"] for a in _repo([self._WORST])["recommended_actions"]}
        assert types == {
            "run_determinism_regression_suite",
            "rerun_failed_task",
            "regenerate_missing_artifact",
            "refresh_repo_health",
        }

    def test_all_four_issues_present(self):
        issue_types = {i["issue_type"] for i in _repo([self._WORST])["open_issues"]}
        assert issue_types == {
            "determinism_regression",
            "repeated_failure",
            "artifact_incomplete",
            "stale_signals",
        }

    def test_issues_sorted_severity_desc(self):
        from mcp_governance_orchestrator.portfolio_state import _SEVERITY_RANK
        issues = _repo([self._WORST])["open_issues"]
        ranks = [_SEVERITY_RANK[i["severity"]] for i in issues]
        assert ranks == sorted(ranks, reverse=True)

    def test_health_score_clamped_zero(self):
        # 1.0 - 0.60 - 0.35 - 0.15 - 0.10 = -0.20 → clamped to 0.0
        assert _repo([self._WORST])["health_score"] == 0.0

    def test_priority_order_exact(self):
        # Known exact priority sequence for all-rules-fire scenario.
        actions = _repo([self._WORST])["recommended_actions"]
        priorities = [a["priority"] for a in actions]
        assert priorities == [0.95, 0.80, 0.70, 0.55]


# ---------------------------------------------------------------------------
# v1 eligible / blocked_by contract
# ---------------------------------------------------------------------------

class TestV1EligibilityContract:
    _WORST = {
        "repo_id": "any-repo",
        "last_run_ok": False,
        "artifact_completeness": 0.0,
        "determinism_ok": False,
        "recent_failures": 2,
        "stale_runs": 3,
    }

    def test_all_actions_eligible_true(self):
        for action in _repo([self._WORST])["recommended_actions"]:
            assert action["eligible"] is True

    def test_all_actions_blocked_by_empty(self):
        for action in _repo([self._WORST])["recommended_actions"]:
            assert action["blocked_by"] == []


# ---------------------------------------------------------------------------
# Portfolio recommendations aggregation
# ---------------------------------------------------------------------------

class TestPortfolioRecommendations:
    _SIGNALS = [
        {
            "repo_id": "aaa",
            "last_run_ok": False,
            "artifact_completeness": 1.0,
            "determinism_ok": False,
            "recent_failures": 0,
            "stale_runs": 0,
        },
        {
            "repo_id": "bbb",
            "last_run_ok": False,
            "artifact_completeness": 1.0,
            "determinism_ok": True,
            "recent_failures": 2,
            "stale_runs": 0,
        },
    ]

    def test_portfolio_recommendations_sorted_priority_desc(self):
        recs = _build(self._SIGNALS)["portfolio_recommendations"]
        priorities = [r["priority"] for r in recs]
        assert priorities == sorted(priorities, reverse=True)

    def test_portfolio_recommendations_contain_all_repo_actions(self):
        state = _build(self._SIGNALS)
        repo_action_ids = {
            a["action_id"]
            for repo in state["repos"]
            for a in repo["recommended_actions"]
        }
        rec_ids = {r["action_id"] for r in state["portfolio_recommendations"]}
        assert repo_action_ids == rec_ids

    def test_portfolio_recommendations_action_keys_exact(self):
        _ACTION_KEYS = {"action_id", "action_type", "priority", "reason", "eligible", "blocked_by", "task_binding"}
        state = _build(self._SIGNALS)
        for rec in state["portfolio_recommendations"]:
            assert set(rec.keys()) == _ACTION_KEYS
