# SPDX-License-Identifier: MIT
"""Tests for scripts/run_autonomous_factory_cycle.py."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SCRIPT = _REPO_ROOT / "scripts" / "run_autonomous_factory_cycle.py"
_spec = importlib.util.spec_from_file_location("run_autonomous_factory_cycle", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_decide_action_returns_idle_for_missing_evaluation():
    assert _mod._decide_action(None) == {"action": "idle", "reason": "no_evaluation"}


def test_decide_action_returns_repair_only_for_high_risk():
    decision = _mod._decide_action({"risk_level": "high_risk"})
    assert decision["action"] == "repair_only"
    assert decision["repair_enabled"] is True
    assert decision["learning_enabled"] is False


def test_decide_action_returns_governed_run_for_low_risk():
    decision = _mod._decide_action({"risk_level": "low_risk"})
    assert decision["action"] == "governed_run"
    assert decision["repair_enabled"] is True
    assert decision["learning_enabled"] is True


def test_run_autonomous_factory_cycle_runs_repair_path_and_writes_artifact(tmp_path, monkeypatch):
    evaluation = {
        "risk_level": "high_risk",
        "reasons": ["persistent collision risk"],
    }
    repair_result = {
        "repair_attempted": True,
        "repair_success": False,
        "status": "repair_no_improvement",
    }

    monkeypatch.setattr(_mod, "evaluate_planner_config", lambda **kwargs: evaluation)
    monkeypatch.setattr(_mod, "run_mapping_repair_cycle", lambda **kwargs: repair_result)

    called = {"governed": False}

    def _unexpected_governed(_args):
        called["governed"] = True
        raise AssertionError("governed path should not run for high_risk evaluation")

    monkeypatch.setattr(_mod, "run_governed_loop", _unexpected_governed)

    output = tmp_path / "autonomous_factory_cycle.json"
    artifact = _mod.run_autonomous_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="action_effectiveness_ledger.json",
        policy="planner_policy.json",
        top_k=4,
        output=str(output),
    )

    assert called["governed"] is False
    assert artifact["decision"]["action"] == "repair_only"
    assert artifact["evaluation"] == evaluation
    assert artifact["cycle_result"] == repair_result
    assert artifact["inputs"] == {
        "portfolio_state": "portfolio_state.json",
        "ledger": "action_effectiveness_ledger.json",
        "policy": "planner_policy.json",
        "top_k": 4,
    }
    assert artifact["status"] == "completed"

    written = _read_json(output)
    assert written == artifact


def test_run_autonomous_factory_cycle_runs_governed_path_and_sets_learning_output(tmp_path, monkeypatch):
    evaluation = {
        "risk_level": "moderate_risk",
        "reasons": [],
    }
    governed_result = {
        "selected_offset": 0,
        "result": {"summary": {"repos_failed": 0}},
    }

    monkeypatch.setattr(_mod, "evaluate_planner_config", lambda **kwargs: evaluation)

    called = {}

    def _capture_governed(args):
        called["runs"] = args.runs
        called["portfolio_state"] = args.portfolio_state
        called["ledger"] = args.ledger
        called["policy"] = args.policy
        called["top_k"] = args.top_k
        called["output"] = args.output
        called["force"] = args.force
        called["exploration_offset"] = args.exploration_offset
        called["max_actions"] = args.max_actions
        called["explain"] = args.explain
        called["envelope_prefix"] = args.envelope_prefix
        called["mapping_override"] = args.mapping_override
        called["mapping_override_path"] = args.mapping_override_path
        called["auto_repair_cycle"] = args.auto_repair_cycle
        called["learn_ledger_output"] = args.learn_ledger_output
        return governed_result

    monkeypatch.setattr(_mod, "run_governed_loop", _capture_governed)

    called["repair"] = False

    def _unexpected_repair(**kwargs):
        called["repair"] = True
        raise AssertionError("repair path should not run for acceptable-risk evaluation")

    monkeypatch.setattr(_mod, "run_mapping_repair_cycle", _unexpected_repair)

    output = tmp_path / "autonomous_factory_cycle.json"
    artifact = _mod.run_autonomous_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="action_effectiveness_ledger.json",
        policy="planner_policy.json",
        top_k=3,
        output=str(output),
    )

    assert called["repair"] is False
    assert artifact["decision"]["action"] == "governed_run"
    assert artifact["evaluation"] == evaluation
    assert artifact["cycle_result"] == governed_result
    assert called["runs"] == 1
    assert called["portfolio_state"] == "portfolio_state.json"
    assert called["ledger"] == "action_effectiveness_ledger.json"
    assert called["policy"] == "planner_policy.json"
    assert called["top_k"] == 3
    assert called["output"] == str(output)
    assert called["force"] is False
    assert called["exploration_offset"] == 0
    assert called["max_actions"] is None
    assert called["explain"] is False
    assert called["envelope_prefix"] == "planner_run_envelope"
    assert called["mapping_override"] is None
    assert called["mapping_override_path"] is None
    assert called["auto_repair_cycle"] is True
    assert called["learn_ledger_output"] == str(
        output.with_name(output.stem + "_learned_ledger.json")
    )

    written = _read_json(output)
    assert written == artifact
