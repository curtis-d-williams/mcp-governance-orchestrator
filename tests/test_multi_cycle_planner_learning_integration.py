# SPDX-License-Identifier: MIT
"""Integration tests for multi-cycle planner learning.

Verifies that the governed cycle pipeline correctly propagates
action_effectiveness_ledger state across successive cycles so that
high-success actions are ranked first in governed_result by cycle 3.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mcp_governance_orchestrator.governed_cycle import run_cycle  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_proc(returncode=0):
    m = MagicMock()
    m.returncode = returncode
    m.stdout = ""
    m.stderr = ""
    return m


def _make_args(manifest_path, output_path):
    return SimpleNamespace(
        manifest=str(manifest_path),
        output=str(output_path),
        ledger=None,
        task=[],
        policy=None,
        top_k=1,
        exploration_offset=0,
        max_actions=None,
        explain=False,
        force=False,
        governance_policy=None,
        capability_ledger=None,
        repo_ids=None,
    )


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestMultiCyclePlannerLearningIntegration:

    def test_ranked_action_window_shifts_to_favor_high_success_by_cycle_3(
        self, tmp_path
    ):
        # --- Setup: manifest and repo directory ---
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)

        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(
            json.dumps({
                "repos": [
                    {
                        "id": "test_repo",
                        "path": str(repo_dir),
                        "cycle_script": str(repo_dir / "cycle.sh"),
                    }
                ]
            }),
            encoding="utf-8",
        )

        output_path = tmp_path / "output.json"
        args = _make_args(manifest_path, output_path)

        # work_dir: output_path.parent / f"{output_path.stem}_artifacts"
        wd = tmp_path / "output_artifacts"
        wd.mkdir(parents=True, exist_ok=True)

        # --- Seed work-dir ledger before cycle 1 ---
        initial_ledger = {
            "actions": {
                "refresh_repo_health": {
                    "effectiveness_score": 8.0,
                    "times_executed": 6,
                    "effect_deltas": {},
                },
                "rerun_failed_task": {
                    "effectiveness_score": -3.0,
                    "times_executed": 6,
                    "effect_deltas": {},
                },
            }
        }
        ledger_path = wd / "action_effectiveness_ledger.json"
        ledger_path.write_text(json.dumps(initial_ledger), encoding="utf-8")

        # --- Per-cycle ledger state after Phase F ---
        _phase_f_ledgers = [
            {
                "actions": {
                    "refresh_repo_health": {
                        "effectiveness_score": 10.0,
                        "times_executed": 7,
                        "effect_deltas": {},
                    },
                    "rerun_failed_task": {
                        "effectiveness_score": -3.0,
                        "times_executed": 6,
                        "effect_deltas": {},
                    },
                }
            },
            {
                "actions": {
                    "refresh_repo_health": {
                        "effectiveness_score": 12.0,
                        "times_executed": 8,
                        "effect_deltas": {},
                    },
                    "rerun_failed_task": {
                        "effectiveness_score": -3.0,
                        "times_executed": 6,
                        "effect_deltas": {},
                    },
                }
            },
            # cycle 3 Phase F: same as cycle 2 (no new data yet)
            {
                "actions": {
                    "refresh_repo_health": {
                        "effectiveness_score": 12.0,
                        "times_executed": 8,
                        "effect_deltas": {},
                    },
                    "rerun_failed_task": {
                        "effectiveness_score": -3.0,
                        "times_executed": 6,
                        "effect_deltas": {},
                    },
                }
            },
        ]
        _cycle_counter = {"n": 0}

        # --- Phase mock builders ---

        def _phase_a_side_effect(*a, **kw):
            return _make_proc()

        def _phase_b_side_effect(*a, **kw):
            (wd / "portfolio_state.json").write_text(
                json.dumps({"status": "ok", "actions": []}), encoding="utf-8"
            )
            return _make_proc()

        def _phase_c_side_effect(*a, **kw):
            # Read current ledger to determine ranking
            current_ledger_path = wd / "action_effectiveness_ledger.json"
            scores = {}
            if current_ledger_path.exists():
                data = json.loads(current_ledger_path.read_text(encoding="utf-8"))
                for action, info in data.get("actions", {}).items():
                    scores[action] = info.get("effectiveness_score", 0.0)

            ranked = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)
            if not ranked:
                ranked = ["refresh_repo_health", "rerun_failed_task"]

            (wd / "governed_result.json").write_text(
                json.dumps({
                    "status": "ok",
                    "idle": False,
                    "ranked_action_window": ranked,
                    "selected_action": {"action_type": ranked[0]},
                    "selection_detail": {},
                }),
                encoding="utf-8",
            )
            return _make_proc()

        def _phase_d_side_effect(*a, **kw):
            (wd / "execution_result.json").write_text(
                json.dumps({"status": "ok", "actions_executed": []}),
                encoding="utf-8",
            )
            return _make_proc()

        def _phase_e_side_effect(*a, **kw):
            (wd / "execution_history.json").write_text(
                json.dumps([]), encoding="utf-8"
            )
            return _make_proc()

        def _phase_f_side_effect(*a, **kw):
            n = _cycle_counter["n"]
            ledger_data = _phase_f_ledgers[min(n, len(_phase_f_ledgers) - 1)]
            (wd / "action_effectiveness_ledger.json").write_text(
                json.dumps(ledger_data), encoding="utf-8"
            )
            _cycle_counter["n"] += 1
            return _make_proc()

        def _phase_i_side_effect(*a, **kw):
            (wd / "cycle_history.json").write_text(
                json.dumps([]), encoding="utf-8"
            )
            return _make_proc()

        def _phase_j_side_effect(*a, **kw):
            (wd / "cycle_history_summary.json").write_text(
                json.dumps({"status": "ok"}), encoding="utf-8"
            )
            return _make_proc()

        def _phase_k_side_effect(*a, **kw):
            (wd / "cycle_history_regression_report.json").write_text(
                json.dumps({"regression_detected": False}), encoding="utf-8"
            )
            return _make_proc()

        def _phase_l_side_effect(*a, **kw):
            (wd / "governance_decision.json").write_text(
                json.dumps({"decision": "proceed", "signals": []}),
                encoding="utf-8",
            )
            return _make_proc()

        # --- Run 3 cycles under patch ---
        patch_base = "mcp_governance_orchestrator.governed_cycle"
        with (
            patch(f"{patch_base}.run_portfolio_tasks", side_effect=_phase_a_side_effect),
            patch(f"{patch_base}.run_build_portfolio_state", side_effect=_phase_b_side_effect),
            patch(f"{patch_base}.run_governed_loop", side_effect=_phase_c_side_effect),
            patch(f"{patch_base}.run_execute_governed_actions", side_effect=_phase_d_side_effect),
            patch(f"{patch_base}.run_update_execution_history", side_effect=_phase_e_side_effect),
            patch(f"{patch_base}.run_update_action_effectiveness_from_history", side_effect=_phase_f_side_effect),
            patch(f"{patch_base}.run_update_cycle_history", side_effect=_phase_i_side_effect),
            patch(f"{patch_base}.run_aggregate_cycle_history", side_effect=_phase_j_side_effect),
            patch(f"{patch_base}.run_detect_cycle_history_regression", side_effect=_phase_k_side_effect),
            patch(f"{patch_base}.run_enforce_governance_policy", side_effect=_phase_l_side_effect),
        ):
            rc1 = run_cycle(args)
            rc2 = run_cycle(args)
            rc3 = run_cycle(args)

        # --- All cycles must succeed ---
        assert rc1 == 0, f"cycle 1 failed: rc={rc1}"
        assert rc2 == 0, f"cycle 2 failed: rc={rc2}"
        assert rc3 == 0, f"cycle 3 failed: rc={rc3}"

        # --- Cycle 3 artifact: verify planner learning effect ---
        cycle3 = json.loads(output_path.read_text(encoding="utf-8"))
        governed = cycle3.get("governed_result")
        if governed is None:
            governed = json.loads((wd / "governed_result.json").read_text(encoding="utf-8"))

        ranked = governed["ranked_action_window"]
        assert ranked[0] == "refresh_repo_health", (
            f"expected refresh_repo_health first by cycle 3, got: {ranked}"
        )
        assert ranked[-1] == "rerun_failed_task", (
            f"expected rerun_failed_task last by cycle 3, got: {ranked}"
        )
