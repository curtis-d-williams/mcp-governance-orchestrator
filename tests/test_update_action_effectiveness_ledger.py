# SPDX-License-Identifier: MIT
"""Tests for scripts/update_action_effectiveness_ledger.py — times_executed write-path."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SCRIPT = _REPO_ROOT / "scripts" / "update_action_effectiveness_ledger.py"
_spec = importlib.util.spec_from_file_location("update_action_effectiveness_ledger", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def _write_json(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def _governed_artifact():
    """Minimal governed artifact that selects refresh_repo_health."""
    return {
        "result": {
            "evaluation_summary": {
                "runs": [
                    {
                        "selected_actions": ["build_portfolio_dashboard"],
                        "selection_detail": {
                            "ranked_action_window": ["refresh_repo_health"],
                            "active_action_to_task_mapping": {
                                "refresh_repo_health": "build_portfolio_dashboard"
                            },
                        },
                    }
                ]
            },
            "repos": [
                {"summary": {"repos_failed": 0}}
            ],
        }
    }


def test_times_executed_increments_on_governed_cycle(tmp_path):
    """times_executed goes from 2 to 3 in both return value and persisted ledger."""
    ledger = {
        "action_types": [
            {
                "action_type": "refresh_repo_health",
                "times_executed": 2,
                "success_count": 1,
                "failure_count": 1,
                "effectiveness_score": 0.5,
                "effect_deltas": {},
            }
        ]
    }
    ledger_path = tmp_path / "ledger.json"
    artifact_path = tmp_path / "artifact.json"
    output_path = tmp_path / "ledger_out.json"

    _write_json(ledger_path, ledger)
    _write_json(artifact_path, _governed_artifact())

    result = _mod.update_action_effectiveness_ledger(
        ledger_path=str(ledger_path),
        governed_artifact_path=str(artifact_path),
        output_path=str(output_path),
    )

    updates = result.get("updates", [])
    assert len(updates) == 1
    assert updates[0]["action_type"] == "refresh_repo_health"
    assert updates[0]["times_executed"] == 3

    persisted = json.loads(output_path.read_text(encoding="utf-8"))
    rows = {r["action_type"]: r for r in persisted["action_types"]}
    assert rows["refresh_repo_health"]["times_executed"] == 3


def test_times_executed_initializes_from_zero_for_new_action(tmp_path):
    """A new action not in the ledger gets times_executed=1 after its first cycle."""
    ledger = {"action_types": []}
    ledger_path = tmp_path / "ledger.json"
    artifact_path = tmp_path / "artifact.json"
    output_path = tmp_path / "ledger_out.json"

    _write_json(ledger_path, ledger)
    _write_json(artifact_path, _governed_artifact())

    result = _mod.update_action_effectiveness_ledger(
        ledger_path=str(ledger_path),
        governed_artifact_path=str(artifact_path),
        output_path=str(output_path),
    )

    updates = result.get("updates", [])
    assert len(updates) == 1
    assert updates[0]["action_type"] == "refresh_repo_health"
    assert updates[0]["times_executed"] == 1

    persisted = json.loads(output_path.read_text(encoding="utf-8"))
    rows = {r["action_type"]: r for r in persisted["action_types"]}
    assert rows["refresh_repo_health"]["times_executed"] == 1
