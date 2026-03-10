# SPDX-License-Identifier: MIT
"""Regression tests for scripts/propose_mapping_repair.py.

Covers:
1. Empty window -> repair_needed False, empty override, reason mentions empty.
2. Already-diverse mapping -> repair_needed False, empty override, reason mentions distinct.
3. Collapsed mapping -> non-empty deterministic override proposed.
4. Proposal does not assign duplicate replacement tasks when avoidable.
5. Output file writing works.
6. Repeated runs produce identical proposal (determinism).
"""

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SCRIPT = _REPO_ROOT / "scripts" / "propose_mapping_repair.py"
_spec = importlib.util.spec_from_file_location("propose_mapping_repair", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

propose_mapping_repair = _mod.propose_mapping_repair
_propose_repair = _mod._propose_repair

# Import ALL_TASKS and ACTION_TO_TASK for test fixtures.
from scripts.claude_dynamic_planner_loop import ALL_TASKS, ACTION_TO_TASK


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_ps(tmp_path, content=None):
    """Write a minimal portfolio_state.json and return its path."""
    ps = tmp_path / "ps.json"
    ps.write_text(
        json.dumps(content or {"repos": []}), encoding="utf-8"
    )
    return str(ps)


# ---------------------------------------------------------------------------
# 1. Empty window -> repair_needed False, empty override
# ---------------------------------------------------------------------------

class TestEmptyWindow:
    def test_repair_not_needed_for_empty_window(self):
        override, reasons = _propose_repair([], [], dict(ACTION_TO_TASK))
        assert override == {}

    def test_reasons_mention_empty(self):
        _, reasons = _propose_repair([], [], dict(ACTION_TO_TASK))
        combined = " ".join(reasons).lower()
        assert "empty" in combined

    def test_propose_repair_returns_repair_needed_false_for_empty_window(self, tmp_path):
        ps = _make_ps(tmp_path)
        with patch.object(_mod, "_fetch_actions", return_value=[]):
            proposal = propose_mapping_repair(
                policy_path=None,
                portfolio_state_path=ps,
                ledger_path=None,
                top_k=3,
                output_path=str(tmp_path / "out.json"),
            )
        assert proposal["repair_needed"] is False
        assert proposal["proposed_mapping_override"] == {}

    def test_ranked_action_window_empty_in_output(self, tmp_path):
        ps = _make_ps(tmp_path)
        with patch.object(_mod, "_fetch_actions", return_value=[]):
            proposal = propose_mapping_repair(
                policy_path=None,
                portfolio_state_path=ps,
                ledger_path=None,
                top_k=3,
                output_path=str(tmp_path / "out.json"),
            )
        assert proposal["ranked_action_window"] == []


# ---------------------------------------------------------------------------
# 2. Already-diverse mapping -> repair_needed False, empty override
# ---------------------------------------------------------------------------

class TestAlreadyDiverse:
    def test_no_repair_when_all_tasks_distinct(self):
        # 3 actions → 3 unique tasks, no collisions.
        window = ["analyze_repo_insights", "recover_failed_workflow", "refresh_repo_health"]
        tasks = ["repo_insights_example", "failure_recovery_example", "build_portfolio_dashboard"]
        override, reasons = _propose_repair(window, tasks, dict(ACTION_TO_TASK))
        assert override == {}

    def test_reasons_mention_distinct(self):
        window = ["analyze_repo_insights", "recover_failed_workflow"]
        tasks = ["repo_insights_example", "failure_recovery_example"]
        _, reasons = _propose_repair(window, tasks, dict(ACTION_TO_TASK))
        combined = " ".join(reasons).lower()
        assert "distinct" in combined or "no repair" in combined

    def test_repair_needed_false_diverse(self, tmp_path):
        ps = _make_ps(tmp_path)
        # Two actions with distinct task mappings.
        actions = [
            {"action_type": "analyze_repo_insights", "priority": 0.9,
             "action_id": "a1", "repo_id": "r1"},
            {"action_type": "recover_failed_workflow", "priority": 0.8,
             "action_id": "a2", "repo_id": "r2"},
        ]
        with patch.object(_mod, "_fetch_actions", return_value=actions):
            proposal = propose_mapping_repair(
                policy_path=None,
                portfolio_state_path=ps,
                ledger_path=None,
                top_k=2,
                output_path=str(tmp_path / "out.json"),
            )
        assert proposal["repair_needed"] is False
        assert proposal["proposed_mapping_override"] == {}


# ---------------------------------------------------------------------------
# 3. Collapsed mapping -> non-empty deterministic override
# ---------------------------------------------------------------------------

class TestCollapsedMapping:
    def _colliding_window(self):
        # All three actions map to "build_portfolio_dashboard" by default.
        return (
            ["refresh_repo_health", "regenerate_missing_artifact", "rerun_failed_task"],
            ["build_portfolio_dashboard", "build_portfolio_dashboard", "build_portfolio_dashboard"],
        )

    def test_override_non_empty_for_collision(self):
        window, tasks = self._colliding_window()
        override, _ = _propose_repair(window, tasks, dict(ACTION_TO_TASK))
        assert len(override) > 0

    def test_repair_needed_true_for_collision(self, tmp_path):
        ps = _make_ps(tmp_path)
        actions = [
            {"action_type": "refresh_repo_health",        "priority": 0.9,
             "action_id": "a1", "repo_id": "r1"},
            {"action_type": "regenerate_missing_artifact","priority": 0.8,
             "action_id": "a2", "repo_id": "r2"},
            {"action_type": "rerun_failed_task",           "priority": 0.7,
             "action_id": "a3", "repo_id": "r3"},
        ]
        with patch.object(_mod, "_fetch_actions", return_value=actions):
            proposal = propose_mapping_repair(
                policy_path=None,
                portfolio_state_path=ps,
                ledger_path=None,
                top_k=3,
                output_path=str(tmp_path / "out.json"),
            )
        assert proposal["repair_needed"] is True
        assert proposal["proposed_mapping_override"] != {}

    def test_first_occurrence_preserved(self):
        """The first action with a colliding task appears in the full override with its original task."""
        window, tasks = self._colliding_window()
        override, _ = _propose_repair(window, tasks, dict(ACTION_TO_TASK))
        # refresh_repo_health is first — it keeps build_portfolio_dashboard in the full override.
        assert "refresh_repo_health" in override
        assert override["refresh_repo_health"] == "build_portfolio_dashboard"

    def test_replacement_is_a_known_task(self):
        window, tasks = self._colliding_window()
        override, _ = _propose_repair(window, tasks, dict(ACTION_TO_TASK))
        for task in override.values():
            assert task in ALL_TASKS

    def test_reasons_non_empty_for_collision(self):
        window, tasks = self._colliding_window()
        _, reasons = _propose_repair(window, tasks, dict(ACTION_TO_TASK))
        assert len(reasons) > 0


# ---------------------------------------------------------------------------
# 4. No duplicate replacement tasks in override when avoidable
# ---------------------------------------------------------------------------

class TestNoDuplicateReplacements:
    def test_replacement_tasks_are_unique(self):
        """Each replacement task should appear at most once in the override values."""
        # All 3 actions collapse to the same task — 2 need reassignment.
        window = ["refresh_repo_health", "regenerate_missing_artifact", "rerun_failed_task"]
        tasks = ["build_portfolio_dashboard"] * 3
        override, _ = _propose_repair(window, tasks, dict(ACTION_TO_TASK))
        values = list(override.values())
        assert len(values) == len(set(values)), (
            f"Duplicate replacement tasks found: {values}"
        )

    def test_replacement_tasks_differ_from_original(self):
        """Replacement tasks for *colliding* (non-first) entries must differ from the original."""
        window = ["regenerate_missing_artifact", "rerun_failed_task"]
        tasks = ["build_portfolio_dashboard", "build_portfolio_dashboard"]
        override, _ = _propose_repair(window, tasks, dict(ACTION_TO_TASK))
        # First action keeps its original task in the full override — skip it.
        # Second action (collision) must be remapped to something else.
        assert override["rerun_failed_task"] != "build_portfolio_dashboard", (
            "'rerun_failed_task' was not remapped away from the colliding task"
        )

    def test_five_action_collapse_unique_replacements(self):
        """With 5 actions all colliding, replacements drawn from distinct pool entries."""
        # Only 5 tasks in ALL_TASKS; first occurrence keeps original, up to 4 need replacements.
        # There are only 4 alternatives (ALL_TASKS minus build_portfolio_dashboard).
        window = [
            "refresh_repo_health", "regenerate_missing_artifact",
            "rerun_failed_task", "run_determinism_regression_suite",
            "analyze_repo_insights",
        ]
        tasks = ["build_portfolio_dashboard"] * 5
        override, _ = _propose_repair(window, tasks, dict(ACTION_TO_TASK))
        values = [v for v in override.values()]
        assert len(values) == len(set(values))


# ---------------------------------------------------------------------------
# 5. Output file writing
# ---------------------------------------------------------------------------

class TestOutputFileWriting:
    def test_file_written_when_output_given(self, tmp_path):
        ps = _make_ps(tmp_path)
        out = tmp_path / "proposal.json"
        with patch.object(_mod, "_fetch_actions", return_value=[]):
            propose_mapping_repair(
                policy_path=None, portfolio_state_path=ps,
                ledger_path=None, top_k=3, output_path=str(out),
            )
        assert out.exists()

    def test_file_is_valid_json(self, tmp_path):
        ps = _make_ps(tmp_path)
        out = tmp_path / "proposal.json"
        with patch.object(_mod, "_fetch_actions", return_value=[]):
            propose_mapping_repair(
                policy_path=None, portfolio_state_path=ps,
                ledger_path=None, top_k=3, output_path=str(out),
            )
        data = json.loads(out.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_file_matches_return_value(self, tmp_path):
        ps = _make_ps(tmp_path)
        out = tmp_path / "proposal.json"
        with patch.object(_mod, "_fetch_actions", return_value=[]):
            result = propose_mapping_repair(
                policy_path=None, portfolio_state_path=ps,
                ledger_path=None, top_k=3, output_path=str(out),
            )
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data == result

    def test_required_keys_present_in_file(self, tmp_path):
        ps = _make_ps(tmp_path)
        out = tmp_path / "proposal.json"
        with patch.object(_mod, "_fetch_actions", return_value=[]):
            propose_mapping_repair(
                policy_path=None, portfolio_state_path=ps,
                ledger_path=None, top_k=3, output_path=str(out),
            )
        data = json.loads(out.read_text(encoding="utf-8"))
        for key in ("ranked_action_window", "current_mapped_tasks",
                    "proposed_mapping_override", "repair_needed", "reasons"):
            assert key in data

    def test_stdout_when_no_output_path(self, tmp_path, capsys):
        ps = _make_ps(tmp_path)
        with patch.object(_mod, "_fetch_actions", return_value=[]):
            propose_mapping_repair(
                policy_path=None, portfolio_state_path=ps,
                ledger_path=None, top_k=3, output_path=None,
            )
        out_text = capsys.readouterr().out
        data = json.loads(out_text)
        assert "repair_needed" in data


# ---------------------------------------------------------------------------
# 6. Determinism — repeated runs produce identical proposals
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_empty_window_deterministic(self):
        for _ in range(3):
            r1 = _propose_repair([], [], dict(ACTION_TO_TASK))
        assert _propose_repair([], [], dict(ACTION_TO_TASK)) == r1

    def test_collision_repair_deterministic(self):
        window = ["refresh_repo_health", "regenerate_missing_artifact", "rerun_failed_task"]
        tasks = ["build_portfolio_dashboard"] * 3
        mapping = dict(ACTION_TO_TASK)
        r1 = _propose_repair(window, tasks, mapping)
        r2 = _propose_repair(window, tasks, mapping)
        assert r1 == r2

    def test_full_propose_repair_deterministic(self, tmp_path):
        ps = _make_ps(tmp_path)
        actions = [
            {"action_type": "refresh_repo_health",        "priority": 0.9,
             "action_id": "a1", "repo_id": "r1"},
            {"action_type": "regenerate_missing_artifact","priority": 0.8,
             "action_id": "a2", "repo_id": "r2"},
        ]
        kwargs = dict(
            policy_path=None, portfolio_state_path=ps,
            ledger_path=None, top_k=2,
            output_path=str(tmp_path / "out.json"),
        )
        with patch.object(_mod, "_fetch_actions", return_value=actions):
            r1 = propose_mapping_repair(**kwargs)
        with patch.object(_mod, "_fetch_actions", return_value=actions):
            r2 = propose_mapping_repair(**kwargs)
        assert r1 == r2


# ---------------------------------------------------------------------------
# 7. Full override covers all window actions
# ---------------------------------------------------------------------------

class TestFullOverride:
    """The proposed_mapping_override must cover every action in the window
    when a repair is needed, so it can be applied without the default mapping."""

    def _colliding_actions(self):
        return [
            {"action_type": "refresh_repo_health",        "priority": 0.9,
             "action_id": "a1", "repo_id": "r1"},
            {"action_type": "regenerate_missing_artifact","priority": 0.8,
             "action_id": "a2", "repo_id": "r2"},
            {"action_type": "rerun_failed_task",           "priority": 0.7,
             "action_id": "a3", "repo_id": "r3"},
        ]

    def test_override_covers_all_window_actions(self, tmp_path):
        """Every action in ranked_action_window must appear as a key in the override."""
        ps = _make_ps(tmp_path)
        with patch.object(_mod, "_fetch_actions", return_value=self._colliding_actions()):
            proposal = propose_mapping_repair(
                policy_path=None, portfolio_state_path=ps,
                ledger_path=None, top_k=3,
                output_path=str(tmp_path / "out.json"),
            )
        window = proposal["ranked_action_window"]
        override = proposal["proposed_mapping_override"]
        assert set(window) == set(override.keys()), (
            f"Override keys {set(override.keys())} != window actions {set(window)}"
        )

    def test_override_keys_match_window_exactly(self):
        """Pure _propose_repair: override keys equal the full window."""
        window = ["refresh_repo_health", "regenerate_missing_artifact", "rerun_failed_task"]
        tasks = ["build_portfolio_dashboard"] * 3
        override, _ = _propose_repair(window, tasks, dict(ACTION_TO_TASK))
        assert set(override.keys()) == set(window)

    def test_all_override_values_are_known_tasks(self):
        """Every value in the full override must be a known task in ALL_TASKS."""
        window = ["refresh_repo_health", "regenerate_missing_artifact", "rerun_failed_task"]
        tasks = ["build_portfolio_dashboard"] * 3
        override, _ = _propose_repair(window, tasks, dict(ACTION_TO_TASK))
        for action, task in override.items():
            assert task in ALL_TASKS, f"{action!r} mapped to unknown task {task!r}"

    def test_empty_window_override_still_empty(self):
        """Full-override change must not affect empty-window behavior."""
        override, _ = _propose_repair([], [], dict(ACTION_TO_TASK))
        assert override == {}

    def test_no_collision_override_still_empty(self):
        """Full-override change must not affect no-repair behavior."""
        window = ["analyze_repo_insights", "recover_failed_workflow"]
        tasks = ["repo_insights_example", "failure_recovery_example"]
        override, _ = _propose_repair(window, tasks, dict(ACTION_TO_TASK))
        assert override == {}

    def test_full_override_deterministic(self):
        """Repeated calls to _propose_repair produce identical full overrides."""
        window = ["refresh_repo_health", "regenerate_missing_artifact", "rerun_failed_task"]
        tasks = ["build_portfolio_dashboard"] * 3
        mapping = dict(ACTION_TO_TASK)
        r1 = _propose_repair(window, tasks, mapping)
        r2 = _propose_repair(window, tasks, mapping)
        assert r1 == r2
