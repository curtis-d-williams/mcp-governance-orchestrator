# SPDX-License-Identifier: MIT
"""Regression tests for action-id-aware mapping repair.

Covers:
1. Duplicate action types in same window — repair must use distinct by_action_id
   entries and must NOT overwrite one remap with another.
2. Structured override resolution precedence:
   by_action_id > by_action_type > default.
3. Backward compatibility — legacy flat override dict still works end-to-end.
4. _compute_risk returns ranked_action_window_detail with correct shape.
5. propose_mapping_repair top-level returns ranked_action_window_detail.
6. run_governed_planner_loop abort artifact uses window_detail when available.
"""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# claude_dynamic_planner_loop
from scripts.claude_dynamic_planner_loop import (
    ACTION_TO_TASK,
    ALL_TASKS,
    _map_actions_to_tasks,
    _selected_mapped_actions,
    resolve_action_to_task_mapping,
    resolve_task_for_action,
)

# analyze_planner_collision_risk
_ANALYZER_SCRIPT = _REPO_ROOT / "scripts" / "analyze_planner_collision_risk.py"
_analyzer_spec = importlib.util.spec_from_file_location(
    "analyze_planner_collision_risk", _ANALYZER_SCRIPT
)
_analyzer_mod = importlib.util.module_from_spec(_analyzer_spec)
_analyzer_spec.loader.exec_module(_analyzer_mod)
_compute_risk = _analyzer_mod._compute_risk

# propose_mapping_repair
_REPAIR_SCRIPT = _REPO_ROOT / "scripts" / "propose_mapping_repair.py"
_repair_spec = importlib.util.spec_from_file_location("propose_mapping_repair", _REPAIR_SCRIPT)
_repair_mod = importlib.util.module_from_spec(_repair_spec)
_repair_spec.loader.exec_module(_repair_mod)
_propose_repair = _repair_mod._propose_repair
propose_mapping_repair = _repair_mod.propose_mapping_repair

# run_governed_planner_loop
_GOVERNED_SCRIPT = _REPO_ROOT / "scripts" / "run_governed_planner_loop.py"
_governed_spec = importlib.util.spec_from_file_location("run_governed_planner_loop", _GOVERNED_SCRIPT)
_governed_mod = importlib.util.module_from_spec(_governed_spec)
_governed_spec.loader.exec_module(_governed_mod)
_build_abort_artifact = _governed_mod._build_abort_artifact
run_governed_loop = _governed_mod.run_governed_loop


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ps(tmp_path, content=None):
    ps = tmp_path / "ps.json"
    ps.write_text(json.dumps(content or {"repos": []}), encoding="utf-8")
    return str(ps)


def _make_args(tmp_path, **kwargs):
    defaults = dict(
        runs=1,
        portfolio_state=None,
        ledger=None,
        policy=None,
        top_k=3,
        exploration_offset=0,
        max_actions=None,
        explain=False,
        force=False,
        output=str(tmp_path / "governed_result.json"),
        envelope_prefix="planner_run_envelope",
        mapping_override=None,
        mapping_override_path=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# 1. resolve_task_for_action — structured override precedence
# ---------------------------------------------------------------------------

class TestResolveTaskForAction:
    """resolve_task_for_action must honour by_action_id > by_action_type > default."""

    def test_by_action_id_wins_over_by_action_type(self):
        action = {"action_id": "aid-1", "action_type": "regenerate_missing_artifact"}
        override = {
            "by_action_id": {"aid-1": "artifact_audit_example"},
            "by_action_type": {"regenerate_missing_artifact": "failure_recovery_example"},
        }
        result = resolve_task_for_action(action, override, ACTION_TO_TASK)
        assert result == "artifact_audit_example"

    def test_by_action_type_wins_over_default(self):
        action = {"action_id": "aid-2", "action_type": "regenerate_missing_artifact"}
        override = {
            "by_action_type": {"regenerate_missing_artifact": "failure_recovery_example"},
        }
        result = resolve_task_for_action(action, override, ACTION_TO_TASK)
        assert result == "failure_recovery_example"

    def test_falls_through_to_default_when_id_absent(self):
        action = {"action_id": "unknown-id", "action_type": "regenerate_missing_artifact"}
        override = {
            "by_action_id": {"aid-99": "artifact_audit_example"},
            "by_action_type": {},
        }
        # Neither by_action_id nor by_action_type matches → fall through to default.
        result = resolve_task_for_action(action, override, ACTION_TO_TASK)
        assert result == ACTION_TO_TASK["regenerate_missing_artifact"]

    def test_flat_override_no_fallthrough(self):
        """Flat override must not fall through to default for unmapped types."""
        action = {"action_id": "aid-1", "action_type": "regenerate_missing_artifact"}
        flat_override = {"recover_failed_workflow": "failure_recovery_example"}
        result = resolve_task_for_action(action, flat_override, ACTION_TO_TASK)
        # Not in flat_override → None (no fallthrough for flat)
        assert result is None

    def test_flat_override_returns_mapped_task(self):
        action = {"action_id": "aid-1", "action_type": "recover_failed_workflow"}
        flat_override = {"recover_failed_workflow": "artifact_audit_example"}
        result = resolve_task_for_action(action, flat_override, ACTION_TO_TASK)
        assert result == "artifact_audit_example"

    def test_no_override_uses_default(self):
        action = {"action_id": "aid-1", "action_type": "analyze_repo_insights"}
        result = resolve_task_for_action(action, None, ACTION_TO_TASK)
        assert result == ACTION_TO_TASK["analyze_repo_insights"]


# ---------------------------------------------------------------------------
# 2. resolve_action_to_task_mapping — structured override returns flat
# ---------------------------------------------------------------------------

class TestResolveActionToTaskMapping:
    def test_structured_override_merges_by_action_type(self):
        override = {
            "by_action_id": {"aid-1": "artifact_audit_example"},
            "by_action_type": {"regenerate_missing_artifact": "failure_recovery_example"},
        }
        flat = resolve_action_to_task_mapping(ACTION_TO_TASK, override)
        assert flat["regenerate_missing_artifact"] == "failure_recovery_example"
        # Other defaults preserved.
        assert "recover_failed_workflow" in flat

    def test_flat_override_replaces_mapping(self):
        flat_override = {"recover_failed_workflow": "artifact_audit_example"}
        result = resolve_action_to_task_mapping(ACTION_TO_TASK, flat_override)
        assert result == flat_override

    def test_none_override_returns_default(self):
        result = resolve_action_to_task_mapping(ACTION_TO_TASK, None)
        assert result is ACTION_TO_TASK


# ---------------------------------------------------------------------------
# 3. _map_actions_to_tasks — instance-aware resolution
# ---------------------------------------------------------------------------

class TestMapActionsToTasksInstanceAware:
    """With a structured mapping_override, two same-type actions get distinct tasks."""

    def _make_dup_actions(self):
        """Two regenerate_missing_artifact actions with different action_ids."""
        return [
            {"action_type": "regenerate_missing_artifact", "action_id": "aid-1", "repo_id": "r1", "priority": 0.9},
            {"action_type": "regenerate_missing_artifact", "action_id": "aid-2", "repo_id": "r2", "priority": 0.8},
        ]

    def test_structured_override_maps_distinct_tasks_per_id(self):
        override = {
            "by_action_id": {
                "aid-1": "artifact_audit_example",
                "aid-2": "failure_recovery_example",
            },
        }
        actions = self._make_dup_actions()
        tasks = _map_actions_to_tasks(actions, top_k=2,
                                      action_to_task=ACTION_TO_TASK,
                                      mapping_override=override)
        assert "artifact_audit_example" in tasks
        assert "failure_recovery_example" in tasks
        assert len(tasks) == 2

    def test_no_override_deduplicates_same_type(self):
        """Without override, both same-type actions collapse to same task."""
        actions = self._make_dup_actions()
        tasks = _map_actions_to_tasks(actions, top_k=2)
        # Both map to build_portfolio_dashboard → dedup → only 1 task.
        assert len(tasks) == 1

    def test_flat_override_backward_compat(self):
        """Flat override still works with mapping_override param."""
        actions = [
            {"action_type": "recover_failed_workflow", "action_id": "a1", "priority": 0.9},
        ]
        flat = {"recover_failed_workflow": "artifact_audit_example"}
        tasks = _map_actions_to_tasks(actions, top_k=1,
                                      action_to_task=ACTION_TO_TASK,
                                      mapping_override=flat)
        assert tasks == ["artifact_audit_example"]


# ---------------------------------------------------------------------------
# 4. _propose_repair — duplicate action types use by_action_id
# ---------------------------------------------------------------------------

class TestProposeRepairDuplicateTypes:
    """Core fix: duplicate action_types in window must produce by_action_id entries."""

    def _make_window_detail(self):
        return [
            {"action_id": "aid-1", "action_type": "regenerate_missing_artifact", "repo_id": "r1"},
            {"action_id": "aid-2", "action_type": "regenerate_missing_artifact", "repo_id": "r2"},
            {"action_id": "aid-3", "action_type": "rerun_failed_task", "repo_id": "r3"},
        ]

    def test_duplicate_type_override_uses_by_action_id(self):
        """Repair for duplicate action_type window must put overrides under by_action_id."""
        window = ["regenerate_missing_artifact", "regenerate_missing_artifact", "rerun_failed_task"]
        # All three collapse to build_portfolio_dashboard by default.
        tasks = ["build_portfolio_dashboard", "build_portfolio_dashboard", "build_portfolio_dashboard"]
        detail = self._make_window_detail()

        override, reasons = _propose_repair(window, tasks, dict(ACTION_TO_TASK),
                                            window_detail=detail)

        assert "by_action_id" in override, "Expected by_action_id key in structured override"
        by_id = override["by_action_id"]
        # Both aid-1 and aid-2 must have distinct entries (no overwrite).
        assert "aid-1" in by_id
        assert "aid-2" in by_id
        assert by_id["aid-1"] != by_id["aid-2"], (
            "Duplicate action_type instances must not remap to the same task"
        )

    def test_no_overwrite_of_second_instance(self):
        """The second instance must get a different task than the first."""
        window = ["regenerate_missing_artifact", "regenerate_missing_artifact"]
        tasks = ["build_portfolio_dashboard", "build_portfolio_dashboard"]
        detail = [
            {"action_id": "aid-1", "action_type": "regenerate_missing_artifact", "repo_id": "r1"},
            {"action_id": "aid-2", "action_type": "regenerate_missing_artifact", "repo_id": "r2"},
        ]

        override, reasons = _propose_repair(window, tasks, dict(ACTION_TO_TASK),
                                            window_detail=detail)

        assert "by_action_id" in override
        by_id = override["by_action_id"]
        assert by_id.get("aid-1") != by_id.get("aid-2"), (
            "aid-1 and aid-2 must not map to the same task"
        )
        all_tasks = list(by_id.values())
        assert len(all_tasks) == len(set(all_tasks)), "Tasks in by_action_id must be distinct"

    def test_repair_needed_true_with_window_detail(self):
        window = ["regenerate_missing_artifact", "regenerate_missing_artifact", "rerun_failed_task"]
        tasks = ["build_portfolio_dashboard", "build_portfolio_dashboard", "build_portfolio_dashboard"]
        detail = self._make_window_detail()

        override, _ = _propose_repair(window, tasks, dict(ACTION_TO_TASK),
                                      window_detail=detail)
        assert bool(override), "repair_needed should be True when collisions exist"

    def test_unique_types_use_by_action_type(self):
        """Unique action_types in window_detail go under by_action_type."""
        window = ["analyze_repo_insights", "rerun_failed_task", "rerun_failed_task"]
        # rerun_failed_task duplicates; analyze_repo_insights is unique.
        # Map: analyze_repo_insights → repo_insights_example (unique),
        #      rerun_failed_task → build_portfolio_dashboard (collision x2)
        tasks = ["repo_insights_example", "build_portfolio_dashboard", "build_portfolio_dashboard"]
        detail = [
            {"action_id": "aid-0", "action_type": "analyze_repo_insights", "repo_id": "r0"},
            {"action_id": "aid-1", "action_type": "rerun_failed_task", "repo_id": "r1"},
            {"action_id": "aid-2", "action_type": "rerun_failed_task", "repo_id": "r2"},
        ]

        override, _ = _propose_repair(window, tasks, dict(ACTION_TO_TASK),
                                      window_detail=detail)

        # analyze_repo_insights is unique → by_action_type
        if "by_action_type" in override:
            assert "analyze_repo_insights" in override["by_action_type"]
        # rerun_failed_task is duplicate → by_action_id
        if "by_action_id" in override:
            id_keys = set(override["by_action_id"].keys())
            assert "aid-1" in id_keys or "aid-2" in id_keys

    def test_window_detail_none_falls_back_to_flat(self):
        """Without window_detail, _propose_repair uses flat action_type keys (old behavior)."""
        window = ["refresh_repo_health", "regenerate_missing_artifact", "rerun_failed_task"]
        tasks = ["build_portfolio_dashboard"] * 3
        override, _ = _propose_repair(window, tasks, dict(ACTION_TO_TASK),
                                      window_detail=None)
        # Flat format: keys are action_type strings.
        assert set(override.keys()) == set(window), (
            "Flat (no window_detail) override must have action_type keys"
        )

    def test_repair_reasons_reference_action_id(self):
        """Reasons for remapped duplicate-type actions must mention action_id."""
        window = ["regenerate_missing_artifact", "regenerate_missing_artifact"]
        tasks = ["build_portfolio_dashboard", "build_portfolio_dashboard"]
        detail = [
            {"action_id": "aid-A", "action_type": "regenerate_missing_artifact", "repo_id": "rA"},
            {"action_id": "aid-B", "action_type": "regenerate_missing_artifact", "repo_id": "rB"},
        ]
        _, reasons = _propose_repair(window, tasks, dict(ACTION_TO_TASK),
                                     window_detail=detail)
        combined = " ".join(reasons)
        assert "aid-B" in combined, "Reasons must reference the action_id of the remapped action"

    def test_all_by_action_id_values_are_known_tasks(self):
        window = ["regenerate_missing_artifact", "regenerate_missing_artifact", "rerun_failed_task"]
        tasks = ["build_portfolio_dashboard"] * 3
        detail = self._make_window_detail()
        override, _ = _propose_repair(window, tasks, dict(ACTION_TO_TASK),
                                      window_detail=detail)
        for section in ("by_action_id", "by_action_type"):
            for task in override.get(section, {}).values():
                assert task in ALL_TASKS, f"Unknown task in override: {task!r}"

    def test_deterministic_with_window_detail(self):
        window = ["regenerate_missing_artifact", "regenerate_missing_artifact"]
        tasks = ["build_portfolio_dashboard", "build_portfolio_dashboard"]
        detail = [
            {"action_id": "aid-1", "action_type": "regenerate_missing_artifact", "repo_id": "r1"},
            {"action_id": "aid-2", "action_type": "regenerate_missing_artifact", "repo_id": "r2"},
        ]
        r1 = _propose_repair(window, tasks, dict(ACTION_TO_TASK), window_detail=detail)
        r2 = _propose_repair(window, tasks, dict(ACTION_TO_TASK), window_detail=detail)
        assert r1 == r2


# ---------------------------------------------------------------------------
# 5. _compute_risk — ranked_action_window_detail shape
# ---------------------------------------------------------------------------

class TestComputeRiskDetail:
    """_compute_risk must return ranked_action_window_detail with correct shape."""

    def _run(self, actions, top_k=3, mapping_override=None):
        return _compute_risk(
            actions=actions,
            top_k=top_k,
            ledger={},
            signals={},
            policy={},
            active_mapping=dict(ACTION_TO_TASK),
            mapping_override=mapping_override,
        )

    def test_detail_key_present(self):
        actions = [
            {"action_type": "recover_failed_workflow", "action_id": "a1", "repo_id": "r1", "priority": 0.9},
        ]
        result = self._run(actions, top_k=1)
        assert "ranked_action_window_detail" in result

    def test_detail_length_matches_window(self):
        actions = [
            {"action_type": "recover_failed_workflow", "action_id": "a1", "repo_id": "r1", "priority": 0.9},
            {"action_type": "analyze_repo_insights", "action_id": "a2", "repo_id": "r2", "priority": 0.8},
        ]
        result = self._run(actions, top_k=2)
        assert len(result["ranked_action_window_detail"]) == len(result["ranked_action_window"])

    def test_detail_entry_has_required_keys(self):
        actions = [
            {"action_type": "recover_failed_workflow", "action_id": "a1", "repo_id": "r1", "priority": 0.9},
        ]
        result = self._run(actions, top_k=1)
        entry = result["ranked_action_window_detail"][0]
        assert "action_id" in entry
        assert "action_type" in entry
        assert "repo_id" in entry

    def test_detail_action_type_matches_window(self):
        actions = [
            {"action_type": "recover_failed_workflow", "action_id": "a1", "repo_id": "r1", "priority": 0.9},
            {"action_type": "analyze_repo_insights", "action_id": "a2", "repo_id": "r2", "priority": 0.8},
        ]
        result = self._run(actions, top_k=2)
        for detail, at in zip(result["ranked_action_window_detail"], result["ranked_action_window"]):
            assert detail["action_type"] == at

    def test_instance_aware_mapping_reduces_collapse(self):
        """Structured override via mapping_override param reduces collapse count."""
        actions = [
            {"action_type": "regenerate_missing_artifact", "action_id": "a1",
             "repo_id": "r1", "priority": 0.9},
            {"action_type": "regenerate_missing_artifact", "action_id": "a2",
             "repo_id": "r2", "priority": 0.8},
        ]
        # Without override: both collapse to build_portfolio_dashboard.
        base = self._run(actions, top_k=2, mapping_override=None)
        assert base["collapse_count"] == 1

        # With structured by_action_id override: distinct tasks.
        override = {
            "by_action_id": {
                "a1": "artifact_audit_example",
                "a2": "failure_recovery_example",
            }
        }
        repaired = self._run(actions, top_k=2, mapping_override=override)
        assert repaired["collapse_count"] == 0
        assert repaired["unique_tasks"] == 2


# ---------------------------------------------------------------------------
# 6. propose_mapping_repair — top-level returns ranked_action_window_detail
# ---------------------------------------------------------------------------

class TestProposeMappingRepairTopLevel:
    def test_proposal_includes_detail(self, tmp_path):
        ps = _make_ps(tmp_path)
        actions = [
            {"action_type": "regenerate_missing_artifact", "action_id": "a1",
             "repo_id": "r1", "priority": 0.9},
            {"action_type": "regenerate_missing_artifact", "action_id": "a2",
             "repo_id": "r2", "priority": 0.8},
            {"action_type": "rerun_failed_task", "action_id": "a3",
             "repo_id": "r1", "priority": 0.7},
        ]
        with patch.object(_repair_mod, "_fetch_actions", return_value=actions):
            proposal = propose_mapping_repair(
                policy_path=None,
                portfolio_state_path=ps,
                ledger_path=None,
                top_k=3,
                output_path=str(tmp_path / "out.json"),
            )

        assert "ranked_action_window_detail" in proposal
        detail = proposal["ranked_action_window_detail"]
        assert isinstance(detail, list)
        assert len(detail) == len(proposal["ranked_action_window"])

    def test_duplicate_types_produce_by_action_id(self, tmp_path):
        """When two same-type actions appear, proposed_mapping_override has by_action_id."""
        ps = _make_ps(tmp_path)
        actions = [
            {"action_type": "regenerate_missing_artifact", "action_id": "a1",
             "repo_id": "r1", "priority": 0.9},
            {"action_type": "regenerate_missing_artifact", "action_id": "a2",
             "repo_id": "r2", "priority": 0.8},
            {"action_type": "rerun_failed_task", "action_id": "a3",
             "repo_id": "r1", "priority": 0.7},
        ]
        with patch.object(_repair_mod, "_fetch_actions", return_value=actions):
            proposal = propose_mapping_repair(
                policy_path=None,
                portfolio_state_path=ps,
                ledger_path=None,
                top_k=3,
                output_path=str(tmp_path / "out.json"),
            )

        assert proposal["repair_needed"] is True
        override = proposal["proposed_mapping_override"]
        # Must have by_action_id since regenerate_missing_artifact appears twice.
        assert "by_action_id" in override, (
            f"Expected by_action_id in override, got: {override}"
        )
        by_id = override["by_action_id"]
        assert "a1" in by_id
        assert "a2" in by_id
        assert by_id["a1"] != by_id["a2"], "Duplicate action_type instances must remap distinctly"


# ---------------------------------------------------------------------------
# 7. Backward compatibility — flat override still resolves correctly
# ---------------------------------------------------------------------------

class TestBackwardCompatFlatOverride:
    """Legacy flat override dict must still work as action-type override."""

    def test_flat_override_threads_through_resolve_action_to_task_mapping(self):
        flat = {
            "regenerate_missing_artifact": "artifact_audit_example",
            "rerun_failed_task": "failure_recovery_example",
        }
        result = resolve_action_to_task_mapping(ACTION_TO_TASK, flat)
        assert result == flat

    def test_flat_override_used_by_map_actions_to_tasks(self):
        actions = [
            {"action_type": "regenerate_missing_artifact", "action_id": "a1",
             "repo_id": "r1", "priority": 0.9},
            {"action_type": "rerun_failed_task", "action_id": "a2",
             "repo_id": "r2", "priority": 0.8},
        ]
        flat = {
            "regenerate_missing_artifact": "artifact_audit_example",
            "rerun_failed_task": "failure_recovery_example",
        }
        tasks = _map_actions_to_tasks(actions, top_k=2, action_to_task=flat)
        assert tasks == ["artifact_audit_example", "failure_recovery_example"]

    def test_flat_override_does_not_fall_through_to_default(self):
        """An action_type absent from flat override must return None, not default."""
        action = {"action_type": "analyze_repo_insights", "action_id": "a1"}
        flat = {"regenerate_missing_artifact": "artifact_audit_example"}
        result = resolve_task_for_action(action, flat, ACTION_TO_TASK)
        assert result is None

    def test_flat_propose_repair_no_window_detail(self):
        """_propose_repair with no window_detail still produces flat dict override."""
        window = ["refresh_repo_health", "regenerate_missing_artifact"]
        tasks = ["build_portfolio_dashboard", "build_portfolio_dashboard"]
        override, _ = _propose_repair(window, tasks, dict(ACTION_TO_TASK),
                                      window_detail=None)
        # Flat format: keys are action_type strings, not by_action_id/by_action_type.
        assert "by_action_id" not in override
        assert "by_action_type" not in override
        for key in override:
            assert key in window


# ---------------------------------------------------------------------------
# 8. _build_abort_artifact — passes window_detail to _propose_repair
# ---------------------------------------------------------------------------

class TestAbortArtifactWindowDetail:
    """Abort artifact must include structured by_action_id when window has dups."""

    def test_abort_artifact_structured_repair_with_detail(self, tmp_path):
        evaluation = {
            "ranked_action_window": [
                "regenerate_missing_artifact",
                "regenerate_missing_artifact",
                "rerun_failed_task",
            ],
            "ranked_action_window_detail": [
                {"action_id": "a1", "action_type": "regenerate_missing_artifact", "repo_id": "r1"},
                {"action_id": "a2", "action_type": "regenerate_missing_artifact", "repo_id": "r2"},
                {"action_id": "a3", "action_type": "rerun_failed_task", "repo_id": "r1"},
            ],
            "mapped_tasks": [
                "build_portfolio_dashboard",
                "build_portfolio_dashboard",
                "build_portfolio_dashboard",
            ],
            "risk_level": "high_risk",
        }
        args = _make_args(tmp_path)
        attempts = [{"offset": 0, "risk_level": "high_risk", "collision_ratio": 0.67, "unique_tasks": 1}]

        artifact = _build_abort_artifact(args, attempts, evaluation)

        assert artifact["repair_proposal"] is not None
        override = artifact["repair_proposal"]["proposed_mapping_override"]
        assert "by_action_id" in override, (
            f"Expected by_action_id in structured repair proposal: {override}"
        )
        by_id = override["by_action_id"]
        assert by_id.get("a1") != by_id.get("a2"), (
            "a1 and a2 must map to different tasks in the repair proposal"
        )

    def test_abort_artifact_flat_repair_without_detail(self, tmp_path):
        """Without ranked_action_window_detail, repair proposal uses flat dict."""
        evaluation = {
            "ranked_action_window": [
                "refresh_repo_health",
                "regenerate_missing_artifact",
                "rerun_failed_task",
            ],
            # No ranked_action_window_detail key.
            "mapped_tasks": [
                "build_portfolio_dashboard",
                "build_portfolio_dashboard",
                "build_portfolio_dashboard",
            ],
            "risk_level": "high_risk",
        }
        args = _make_args(tmp_path)
        attempts = [{"offset": 0, "risk_level": "high_risk", "collision_ratio": 0.67, "unique_tasks": 1}]

        artifact = _build_abort_artifact(args, attempts, evaluation)

        assert artifact["repair_proposal"] is not None
        override = artifact["repair_proposal"]["proposed_mapping_override"]
        # Flat format: action_type keys (not by_action_id/by_action_type).
        assert "by_action_id" not in override
        assert "by_action_type" not in override
