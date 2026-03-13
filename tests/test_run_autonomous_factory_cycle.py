# SPDX-License-Identifier: MIT
"""Tests for scripts/run_autonomous_factory_cycle.py."""

import importlib.util
import json
import sys
from pathlib import Path

import factory_pipeline as _pipeline
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
        "capability_ledger": None,
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


def test_run_autonomous_factory_cycle_invokes_generic_capability_builder(tmp_path, monkeypatch):
    evaluation = {
        "risk_level": "moderate_risk",
        "reasons": [],
    }
    governed_result = {
        "selected_offset": 0,
        "result": {
            "evaluation_summary": {
                "runs": [
                    {
                        "selected_actions": ["build_capability_artifact"],
                        "selection_detail": {
                            "ranked_action_window": ["build_capability_artifact"],
                            "ranked_action_window_detail": [
                                {
                                    "action_type": "build_capability_artifact",
                                    "task_binding": {
                                        "args": {
                                            "capability": "snowflake_data_access",
                                        }
                                    },
                                }
                            ],
                        },
                    }
                ]
            }
        },
    }

    monkeypatch.setattr(_mod, "evaluate_planner_config", lambda **kwargs: evaluation)
    monkeypatch.setattr(_mod, "run_governed_loop", lambda args: governed_result)

    called = {}

    def _fake_builder(*, artifact_kind, capability, **kwargs):
        called["builder_called"] = True
        called["artifact_kind"] = artifact_kind
        called["capability"] = capability
        called["kwargs"] = kwargs
        return {
            "status": "ok",
            "artifact_kind": artifact_kind,
            "capability": capability,
            "generated_repo": "generated_data_connector_snowflake",
        }

    monkeypatch.setattr(_pipeline, "build_capability_artifact", _fake_builder)

    output = tmp_path / "autonomous_factory_cycle.json"
    artifact = _mod.run_autonomous_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="action_effectiveness_ledger.json",
        policy="planner_policy.json",
        top_k=3,
        output=str(output),
    )

    assert called == {
        "builder_called": True,
        "artifact_kind": "data_connector",
        "capability": "snowflake_data_access",
        "kwargs": {},
    }
    assert artifact["cycle_result"]["builder"] == {
        "status": "ok",
        "artifact_kind": "data_connector",
        "capability": "snowflake_data_access",
        "generated_repo": "generated_data_connector_snowflake",
    }
    assert artifact["cycle_result"]["synthesis_event"] == {
        "capability": "snowflake_data_access",
        "artifact_kind": "data_connector",
        "status": "ok",
        "source": "planner_request",
        "generated_repo": "generated_data_connector_snowflake",
        "used_evolution": False,
    }

    written = _read_json(output)
    assert written == artifact



def test_run_autonomous_factory_cycle_invokes_builder_for_build_mcp_server(tmp_path, monkeypatch):
    evaluation = {
        "risk_level": "moderate_risk",
        "reasons": [],
    }
    governed_result = {
        "selected_offset": 0,
        "result": {
            "evaluation_summary": {
                "runs": [
                    {
                        "selected_actions": ["build_mcp_server"],
                    }
                ]
            }
        },
    }

    monkeypatch.setattr(_mod, "evaluate_planner_config", lambda **kwargs: evaluation)
    monkeypatch.setattr(_mod, "run_governed_loop", lambda args: governed_result)

    called = {}

    def _fake_builder(*, artifact_kind, capability, **kwargs):
        called["builder_called"] = True
        called["artifact_kind"] = artifact_kind
        called["capability"] = capability
        called["kwargs"] = kwargs
        return {
            "status": "ok",
            "artifact_kind": artifact_kind,
            "capability": capability,
            "generated_repo": "generated_mcp_github",
            "tools": [
                "list_repositories",
                "get_repository",
                "create_issue",
            ],
        }

    monkeypatch.setattr(_pipeline, "build_capability_artifact", _fake_builder)

    output = tmp_path / "autonomous_factory_cycle.json"
    artifact = _mod.run_autonomous_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="action_effectiveness_ledger.json",
        policy="planner_policy.json",
        top_k=3,
        output=str(output),
    )

    assert called == {
        "builder_called": True,
        "artifact_kind": "mcp_server",
        "capability": "github_repository_management",
        "kwargs": {},
    }
    assert artifact["cycle_result"]["builder"] == {
        "status": "ok",
        "artifact_kind": "mcp_server",
        "capability": "github_repository_management",
        "generated_repo": "generated_mcp_github",
        "tools": [
            "list_repositories",
            "get_repository",
            "create_issue",
        ],
    }
    assert artifact["cycle_result"]["synthesis_event"] == {
        "capability": "github_repository_management",
        "artifact_kind": "mcp_server",
        "status": "ok",
        "source": "planner_request",
        "generated_repo": "generated_mcp_github",
        "used_evolution": False,
    }

    written = _read_json(output)
    assert written == artifact


def test_run_autonomous_factory_cycle_records_builder_error(tmp_path, monkeypatch):
    evaluation = {
        "risk_level": "moderate_risk",
        "reasons": [],
    }
    governed_result = {
        "selected_offset": 0,
        "result": {
            "evaluation_summary": {
                "runs": [
                    {
                        "selected_actions": ["build_mcp_server"],
                    }
                ]
            }
        },
    }

    monkeypatch.setattr(_mod, "evaluate_planner_config", lambda **kwargs: evaluation)
    monkeypatch.setattr(_mod, "run_governed_loop", lambda args: governed_result)

    def _failing_builder(*, artifact_kind, capability, **kwargs):
        raise RuntimeError("builder failed deterministically")

    monkeypatch.setattr(_pipeline, "build_capability_artifact", _failing_builder)

    output = tmp_path / "autonomous_factory_cycle.json"
    artifact = _mod.run_autonomous_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="action_effectiveness_ledger.json",
        policy="planner_policy.json",
        top_k=3,
        output=str(output),
    )

    assert artifact["cycle_result"]["builder_error"] == "builder failed deterministically"
    assert artifact["cycle_result"]["synthesis_event"] == {
        "capability": "github_repository_management",
        "artifact_kind": "mcp_server",
        "status": "error",
        "source": "planner_request",
    }

    written = _read_json(output)
    assert written == artifact


def test_run_autonomous_factory_cycle_records_failed_capability_effectiveness_on_builder_error(tmp_path, monkeypatch):
    evaluation = {
        "risk_level": "moderate_risk",
        "reasons": [],
    }
    governed_result = {
        "selected_offset": 0,
        "result": {
            "evaluation_summary": {
                "runs": [
                    {
                        "selected_actions": ["build_capability_artifact"],
                        "selection_detail": {
                            "ranked_action_window": ["build_capability_artifact"],
                            "ranked_action_window_detail": [
                                {
                                    "action_type": "build_capability_artifact",
                                    "task_binding": {
                                        "args": {
                                            "artifact_kind": "data_connector",
                                            "capability": "snowflake_data_access",
                                        }
                                    },
                                }
                            ],
                        },
                    }
                ]
            }
        },
    }

    monkeypatch.setattr(_mod, "evaluate_planner_config", lambda **kwargs: evaluation)
    monkeypatch.setattr(_mod, "run_governed_loop", lambda args: governed_result)

    def _failing_builder(*, artifact_kind, capability, **kwargs):
        raise RuntimeError("builder failed deterministically")

    monkeypatch.setattr(_pipeline, "build_capability_artifact", _failing_builder)

    output = tmp_path / "autonomous_factory_cycle.json"
    artifact = _mod.run_autonomous_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="action_effectiveness_ledger.json",
        policy="planner_policy.json",
        top_k=3,
        output=str(output),
    )

    assert artifact["cycle_result"]["builder_error"] == "builder failed deterministically"
    assert artifact["capability_effectiveness_ledger"] == {
        "capabilities": {
            "snowflake_data_access": {
                "artifact_kind": "data_connector",
                "failed_syntheses": 1,
                "last_synthesis_source": "planner_request",
                "last_synthesis_status": "error",
                "last_synthesis_used_evolution": False,
                "successful_evolved_syntheses": 0,
                "successful_syntheses": 0,
                "total_syntheses": 1,
            }
        }
    }

    written = _read_json(output)
    assert written == artifact


def test_run_autonomous_factory_cycle_invokes_builder_from_ranked_action_window(tmp_path, monkeypatch):
    evaluation = {
        "risk_level": "moderate_risk",
        "reasons": [],
    }
    governed_result = {
        "selected_offset": 0,
        "result": {
            "evaluation_summary": {
                "runs": [
                    {
                        "selected_actions": [],
                        "selection_detail": {
                            "ranked_action_window": ["build_mcp_server"],
                        },
                    }
                ]
            }
        },
    }

    monkeypatch.setattr(_mod, "evaluate_planner_config", lambda **kwargs: evaluation)
    monkeypatch.setattr(_mod, "run_governed_loop", lambda args: governed_result)

    called = {}

    def _fake_builder(*, artifact_kind, capability, **kwargs):
        called["builder_called"] = True
        called["artifact_kind"] = artifact_kind
        called["capability"] = capability
        called["kwargs"] = kwargs
        return {
            "status": "ok",
            "artifact_kind": artifact_kind,
            "capability": capability,
            "generated_repo": "generated_mcp_github",
            "tools": [
                "list_repositories",
                "get_repository",
                "create_issue",
            ],
        }

    monkeypatch.setattr(_pipeline, "build_capability_artifact", _fake_builder)

    output = tmp_path / "autonomous_factory_cycle.json"
    artifact = _mod.run_autonomous_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="action_effectiveness_ledger.json",
        policy="planner_policy.json",
        top_k=3,
        output=str(output),
    )

    assert called == {
        "builder_called": True,
        "artifact_kind": "mcp_server",
        "capability": "github_repository_management",
        "kwargs": {},
    }
    assert artifact["cycle_result"]["builder"]["status"] == "ok"

    written = _read_json(output)
    assert written == artifact


def test_run_autonomous_factory_cycle_passes_capability_from_ranked_action_window_detail(tmp_path, monkeypatch):
    evaluation = {
        "risk_level": "moderate_risk",
        "reasons": [],
    }
    governed_result = {
        "selected_offset": 0,
        "result": {
            "evaluation_summary": {
                "runs": [
                    {
                        "selected_actions": [],
                        "selection_detail": {
                            "ranked_action_window": ["build_mcp_server"],
                            "ranked_action_window_detail": [
                                {
                                    "action_type": "build_mcp_server",
                                    "task_binding": {
                                        "args": {
                                            "capability": "slack_workspace_access",
                                        }
                                    },
                                }
                            ],
                        },
                    }
                ]
            }
        },
    }

    monkeypatch.setattr(_mod, "evaluate_planner_config", lambda **kwargs: evaluation)
    monkeypatch.setattr(_mod, "run_governed_loop", lambda args: governed_result)

    called = {}

    def _fake_builder(*, artifact_kind, capability, **kwargs):
        called["builder_called"] = True
        called["artifact_kind"] = artifact_kind
        called["capability"] = capability
        called["kwargs"] = kwargs
        return {
            "status": "ok",
            "artifact_kind": artifact_kind,
            "capability": capability,
            "generated_repo": "generated_mcp_slack",
            "tools": [
                "list_channels",
                "get_channel",
                "post_message",
            ],
        }

    monkeypatch.setattr(_pipeline, "build_capability_artifact", _fake_builder)

    output = tmp_path / "autonomous_factory_cycle.json"
    artifact = _mod.run_autonomous_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="action_effectiveness_ledger.json",
        policy="planner_policy.json",
        top_k=3,
        output=str(output),
    )

    assert called == {
        "builder_called": True,
        "artifact_kind": "mcp_server",
        "capability": "slack_workspace_access",
        "kwargs": {},
    }
    assert artifact["cycle_result"]["builder"]["generated_repo"] == "generated_mcp_slack"

    written = _read_json(output)
    assert written == artifact


def test_run_autonomous_factory_cycle_records_capability_ledger_input(tmp_path, monkeypatch):
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
    monkeypatch.setattr(
        _mod,
        "run_governed_loop",
        lambda _args: (_ for _ in ()).throw(AssertionError("governed path should not run")),
    )

    output = tmp_path / "autonomous_factory_cycle.json"
    artifact = _mod.run_autonomous_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="action_effectiveness_ledger.json",
        capability_ledger="capability_effectiveness_ledger.json",
        policy="planner_policy.json",
        top_k=4,
        output=str(output),
    )

    assert artifact["inputs"] == {
        "portfolio_state": "portfolio_state.json",
        "ledger": "action_effectiveness_ledger.json",
        "capability_ledger": "capability_effectiveness_ledger.json",
        "policy": "planner_policy.json",
        "top_k": 4,
    }


def test_run_autonomous_factory_cycle_updates_capability_ledger_output(tmp_path, monkeypatch):
    evaluation = {
        "risk_level": "moderate_risk",
        "reasons": [],
    }
    governed_result = {
        "selected_offset": 0,
        "result": {
            "evaluation_summary": {
                "runs": [
                    {
                        "selected_actions": ["build_capability_artifact"],
                        "selection_detail": {
                            "ranked_action_window": ["build_capability_artifact"],
                            "ranked_action_window_detail": [
                                {
                                    "action_type": "build_capability_artifact",
                                    "task_binding": {
                                        "args": {
                                            "artifact_kind": "data_connector",
                                            "capability": "snowflake_data_access",
                                        }
                                    },
                                }
                            ],
                        },
                    }
                ]
            }
        },
    }

    monkeypatch.setattr(_mod, "evaluate_planner_config", lambda **kwargs: evaluation)
    monkeypatch.setattr(_mod, "run_governed_loop", lambda args: governed_result)

    def _fake_builder(*, artifact_kind, capability, **kwargs):
        return {
            "status": "ok",
            "artifact_kind": artifact_kind,
            "capability": capability,
            "generated_repo": "generated_data_connector_snowflake",
        }

    monkeypatch.setattr(_pipeline, "build_capability_artifact", _fake_builder)

    capability_ledger_output = tmp_path / "capability_effectiveness_ledger.json"
    output = tmp_path / "autonomous_factory_cycle.json"

    artifact = _mod.run_autonomous_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="action_effectiveness_ledger.json",
        capability_ledger_output=str(capability_ledger_output),
        policy="planner_policy.json",
        top_k=3,
        output=str(output),
    )

    persisted = _read_json(capability_ledger_output)

    assert artifact["capability_effectiveness_ledger"] == {
        "capabilities": {
            "snowflake_data_access": {
                "artifact_kind": "data_connector",
                "failed_syntheses": 0,
                "last_synthesis_source": "planner_request",
                "last_synthesis_status": "ok",
                "last_synthesis_used_evolution": False,
                "successful_evolved_syntheses": 0,
                "successful_syntheses": 1,
                "total_syntheses": 1,
            }
        }
    }
    assert persisted == artifact["capability_effectiveness_ledger"]


def test_run_autonomous_factory_cycle_updates_existing_capability_ledger_output(tmp_path, monkeypatch):
    evaluation = {
        "risk_level": "moderate_risk",
        "reasons": [],
    }
    governed_result = {
        "selected_offset": 0,
        "result": {
            "evaluation_summary": {
                "runs": [
                    {
                        "selected_actions": ["build_capability_artifact"],
                        "selection_detail": {
                            "ranked_action_window": ["build_capability_artifact"],
                            "ranked_action_window_detail": [
                                {
                                    "action_type": "build_capability_artifact",
                                    "task_binding": {
                                        "args": {
                                            "artifact_kind": "data_connector",
                                            "capability": "snowflake_data_access",
                                        }
                                    },
                                }
                            ],
                        },
                    }
                ]
            }
        },
    }

    monkeypatch.setattr(_mod, "evaluate_planner_config", lambda **kwargs: evaluation)
    monkeypatch.setattr(_mod, "run_governed_loop", lambda args: governed_result)

    def _fake_builder(*, artifact_kind, capability, **kwargs):
        return {
            "status": "ok",
            "artifact_kind": artifact_kind,
            "capability": capability,
            "generated_repo": "generated_data_connector_snowflake",
        }

    monkeypatch.setattr(_pipeline, "build_capability_artifact", _fake_builder)

    capability_ledger = tmp_path / "existing_capability_effectiveness_ledger.json"
    capability_ledger.write_text(
        json.dumps(
            {
                "capabilities": {
                    "snowflake_data_access": {
                        "artifact_kind": "data_connector",
                        "failed_syntheses": 1,
                        "last_synthesis_source": "portfolio_gap",
                        "last_synthesis_status": "error",
                        "successful_syntheses": 2,
                        "total_syntheses": 3,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    output = tmp_path / "autonomous_factory_cycle.json"

    _mod.run_autonomous_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="action_effectiveness_ledger.json",
        capability_ledger=str(capability_ledger),
        capability_ledger_output=str(capability_ledger),
        policy="planner_policy.json",
        top_k=3,
        output=str(output),
    )

    persisted = _read_json(capability_ledger)
    assert persisted["capabilities"]["snowflake_data_access"]["failed_syntheses"] == 1
    assert persisted["capabilities"]["snowflake_data_access"]["successful_syntheses"] == 3
    assert persisted["capabilities"]["snowflake_data_access"]["total_syntheses"] == 4
    assert persisted["capabilities"]["snowflake_data_access"]["last_synthesis_status"] == "ok"
    assert persisted["capabilities"]["snowflake_data_access"]["last_synthesis_source"] == "planner_request"
