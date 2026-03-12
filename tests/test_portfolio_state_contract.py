# SPDX-License-Identifier: MIT
"""Contract tests for portfolio_state schema v1.

Verifies that build_portfolio_state always emits the exact top-level keys,
repo-object keys, issue shape, and action shape required by the v1 spec.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcp_governance_orchestrator.portfolio_state import (
    SCHEMA_VERSION,
    build_portfolio_state,
)

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

_HEALTHY_SIGNAL = {
    "repo_id": "repo-alpha",
    "last_run_ok": True,
    "artifact_completeness": 1.0,
    "determinism_ok": True,
    "recent_failures": 0,
    "stale_runs": 0,
}

_DEGRADED_SIGNAL = {
    "repo_id": "repo-beta",
    "last_run_ok": False,
    "artifact_completeness": 0.5,
    "determinism_ok": True,
    "recent_failures": 0,
    "stale_runs": 0,
}

_FAILING_SIGNAL = {
    "repo_id": "repo-gamma",
    "last_run_ok": False,
    "artifact_completeness": 0.0,
    "determinism_ok": False,
    "recent_failures": 3,
    "stale_runs": 5,
}

_TOP_LEVEL_KEYS = {
    "schema_version",
    "portfolio_id",
    "generated_at",
    "summary",
    "repos",
    "capability_gaps",
    "portfolio_recommendations",
}

_REPO_KEYS = {
    "repo_id",
    "status",
    "health_score",
    "risk_level",
    "signals",
    "open_issues",
    "recommended_actions",
    "action_history",
    "cooldowns",
    "escalations",
}

_SUMMARY_KEYS = {
    "repo_count",
    "repos_healthy",
    "repos_degraded",
    "repos_failing",
    "repos_stale",
    "open_issues_total",
    "eligible_actions_total",
    "blocked_actions_total",
}

_ISSUE_KEYS = {"issue_type", "severity", "reason", "status"}

_ACTION_KEYS = {"action_id", "action_type", "priority", "reason", "eligible", "blocked_by", "task_binding"}

_TASK_BINDING_KEYS = {"task_id", "args"}


def _build(signals=None, ts=""):
    return build_portfolio_state(signals or [_HEALTHY_SIGNAL], generated_at=ts)


# ---------------------------------------------------------------------------
# Top-level schema contract
# ---------------------------------------------------------------------------

class TestTopLevelSchema:
    def test_top_level_keys_exact(self):
        state = _build()
        assert set(state.keys()) == _TOP_LEVEL_KEYS

    def test_schema_version_is_v1(self):
        state = _build()
        assert state["schema_version"] == "v1"
        assert state["schema_version"] == SCHEMA_VERSION

    def test_portfolio_id_is_string(self):
        state = _build()
        assert isinstance(state["portfolio_id"], str)
        assert state["portfolio_id"].startswith("portfolio-")

    def test_generated_at_passthrough(self):
        ts = "2025-06-15T12:00:00+00:00"
        state = build_portfolio_state([_HEALTHY_SIGNAL], generated_at=ts)
        assert state["generated_at"] == ts

    def test_generated_at_defaults_to_empty_string(self):
        state = build_portfolio_state([_HEALTHY_SIGNAL])
        assert state["generated_at"] == ""

    def test_repos_is_list(self):
        assert isinstance(_build()["repos"], list)

    def test_portfolio_recommendations_is_list(self):
        assert isinstance(_build()["portfolio_recommendations"], list)

    def test_capability_gaps_is_list(self):
        assert isinstance(_build()["capability_gaps"], list)


# ---------------------------------------------------------------------------
# Summary contract
# ---------------------------------------------------------------------------

class TestSummaryContract:
    def test_summary_keys_exact(self):
        state = _build()
        assert set(state["summary"].keys()) == _SUMMARY_KEYS

    def test_summary_types_are_int(self):
        state = _build([_HEALTHY_SIGNAL, _DEGRADED_SIGNAL, _FAILING_SIGNAL])
        for key in _SUMMARY_KEYS:
            assert isinstance(state["summary"][key], int), f"summary.{key} must be int"

    def test_repo_count(self):
        state = _build([_HEALTHY_SIGNAL, _DEGRADED_SIGNAL])
        assert state["summary"]["repo_count"] == 2

    def test_repos_healthy_count(self):
        state = _build([_HEALTHY_SIGNAL])
        assert state["summary"]["repos_healthy"] == 1
        assert state["summary"]["repos_degraded"] == 0
        assert state["summary"]["repos_failing"] == 0
        assert state["summary"]["repos_stale"] == 0

    def test_repos_degraded_count(self):
        state = _build([_DEGRADED_SIGNAL])
        assert state["summary"]["repos_degraded"] == 1

    def test_repos_failing_count(self):
        state = _build([_FAILING_SIGNAL])
        assert state["summary"]["repos_failing"] == 1

    def test_open_issues_total(self):
        # failing signal triggers 4 rules -> 4 issues
        state = _build([_FAILING_SIGNAL])
        assert state["summary"]["open_issues_total"] == 4

    def test_eligible_actions_total_v1_all_eligible(self):
        state = _build([_FAILING_SIGNAL])
        # All v1 actions are eligible
        assert state["summary"]["eligible_actions_total"] == 4

    def test_blocked_actions_total_v1_always_zero(self):
        state = _build([_FAILING_SIGNAL])
        assert state["summary"]["blocked_actions_total"] == 0

    def test_empty_input_summary(self):
        state = build_portfolio_state([], generated_at="")
        assert state["summary"]["repo_count"] == 0
        assert state["summary"]["open_issues_total"] == 0
        assert state["summary"]["eligible_actions_total"] == 0


# ---------------------------------------------------------------------------
# Repo-object schema contract
# ---------------------------------------------------------------------------

class TestRepoObjectSchema:
    def _repo(self, signal):
        return build_portfolio_state([signal], generated_at="")["repos"][0]

    @pytest.mark.parametrize("signal", [_HEALTHY_SIGNAL, _DEGRADED_SIGNAL, _FAILING_SIGNAL])
    def test_repo_keys_exact(self, signal):
        assert set(self._repo(signal).keys()) == _REPO_KEYS

    def test_repo_id_matches_signal(self):
        assert self._repo(_HEALTHY_SIGNAL)["repo_id"] == "repo-alpha"

    def test_health_score_is_float_in_range(self):
        for sig in [_HEALTHY_SIGNAL, _DEGRADED_SIGNAL, _FAILING_SIGNAL]:
            repo = self._repo(sig)
            assert isinstance(repo["health_score"], float)
            assert 0.0 <= repo["health_score"] <= 1.0

    def test_status_is_valid_value(self):
        valid = {"healthy", "degraded", "stale", "failing"}
        for sig in [_HEALTHY_SIGNAL, _DEGRADED_SIGNAL, _FAILING_SIGNAL]:
            assert self._repo(sig)["status"] in valid

    def test_risk_level_is_valid_value(self):
        valid = {"low", "medium", "high", "critical"}
        for sig in [_HEALTHY_SIGNAL, _DEGRADED_SIGNAL, _FAILING_SIGNAL]:
            assert self._repo(sig)["risk_level"] in valid

    def test_action_history_is_empty_list(self):
        assert self._repo(_FAILING_SIGNAL)["action_history"] == []

    def test_cooldowns_is_empty_list(self):
        # v1 spec: cooldowns must be [] not {}
        assert self._repo(_FAILING_SIGNAL)["cooldowns"] == []

    def test_escalations_is_empty_list(self):
        assert self._repo(_FAILING_SIGNAL)["escalations"] == []


# ---------------------------------------------------------------------------
# Issue object contract
# ---------------------------------------------------------------------------

class TestIssueObjectContract:
    def _failing_repo(self):
        return build_portfolio_state([_FAILING_SIGNAL], generated_at="")["repos"][0]

    def test_issue_keys_exact(self):
        repo = self._failing_repo()
        for issue in repo["open_issues"]:
            assert set(issue.keys()) == _ISSUE_KEYS, f"Unexpected issue keys: {set(issue.keys())}"

    def test_issue_no_issue_id_field(self):
        repo = self._failing_repo()
        for issue in repo["open_issues"]:
            assert "issue_id" not in issue

    def test_issue_status_is_open(self):
        repo = self._failing_repo()
        for issue in repo["open_issues"]:
            assert issue["status"] == "open"

    def test_issue_severity_valid_values(self):
        valid = {"critical", "high", "medium", "low"}
        repo = self._failing_repo()
        for issue in repo["open_issues"]:
            assert issue["severity"] in valid

    def test_issue_reason_is_nonempty_string(self):
        repo = self._failing_repo()
        for issue in repo["open_issues"]:
            assert isinstance(issue["reason"], str)
            assert issue["reason"] != ""


# ---------------------------------------------------------------------------
# Action object contract
# ---------------------------------------------------------------------------

class TestActionObjectContract:
    def _failing_repo(self):
        return build_portfolio_state([_FAILING_SIGNAL], generated_at="")["repos"][0]

    def test_action_keys_exact(self):
        repo = self._failing_repo()
        for action in repo["recommended_actions"]:
            assert set(action.keys()) == _ACTION_KEYS, f"Unexpected action keys: {set(action.keys())}"

    def test_action_task_binding_keys_exact(self):
        repo = self._failing_repo()
        for action in repo["recommended_actions"]:
            assert set(action["task_binding"].keys()) == _TASK_BINDING_KEYS

    def test_action_task_binding_args_is_empty_dict(self):
        repo = self._failing_repo()
        for action in repo["recommended_actions"]:
            assert action["task_binding"]["args"] == {}

    def test_action_task_binding_task_id_is_string(self):
        repo = self._failing_repo()
        for action in repo["recommended_actions"]:
            assert isinstance(action["task_binding"]["task_id"], str)
            assert action["task_binding"]["task_id"] != ""

    def test_action_eligible_true_in_v1(self):
        repo = self._failing_repo()
        for action in repo["recommended_actions"]:
            assert action["eligible"] is True

    def test_action_blocked_by_empty_list_in_v1(self):
        repo = self._failing_repo()
        for action in repo["recommended_actions"]:
            assert action["blocked_by"] == []

    def test_action_priority_is_float(self):
        repo = self._failing_repo()
        for action in repo["recommended_actions"]:
            assert isinstance(action["priority"], float)

    def test_action_reason_is_nonempty_string(self):
        repo = self._failing_repo()
        for action in repo["recommended_actions"]:
            assert isinstance(action["reason"], str)
            assert action["reason"] != ""


# ---------------------------------------------------------------------------
# Validation / fail-closed
# ---------------------------------------------------------------------------

class TestValidationFailClosed:
    def test_rejects_non_list(self):
        with pytest.raises(ValueError):
            build_portfolio_state({"repo_id": "x"})  # type: ignore[arg-type]

    def test_rejects_missing_field(self):
        with pytest.raises(ValueError):
            build_portfolio_state([{"repo_id": "x", "last_run_ok": True}])

    def test_rejects_wrong_type(self):
        bad = dict(_HEALTHY_SIGNAL)
        bad["recent_failures"] = "two"
        with pytest.raises(ValueError):
            build_portfolio_state([bad])

    def test_rejects_completeness_out_of_range(self):
        bad = dict(_HEALTHY_SIGNAL)
        bad["artifact_completeness"] = 1.5
        with pytest.raises(ValueError):
            build_portfolio_state([bad])

    def test_empty_list_is_valid(self):
        state = build_portfolio_state([], generated_at="")
        assert state["repos"] == []
        assert state["summary"]["repo_count"] == 0
