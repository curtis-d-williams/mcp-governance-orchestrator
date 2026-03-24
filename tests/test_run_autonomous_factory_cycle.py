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
            "generated_repo": "generated_mcp_server_github",
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

    assert called["builder_called"] is True
    assert called["artifact_kind"] == "mcp_server"
    assert called["capability"] == "github_repository_management"
    assert isinstance(called["kwargs"], dict)
    assert artifact["cycle_result"]["builder"] == {
        "status": "ok",
        "artifact_kind": "mcp_server",
        "capability": "github_repository_management",
        "generated_repo": "generated_mcp_server_github",
        "tools": [
            "list_repositories",
            "get_repository",
            "create_issue",
        ],
    }
    synthesis_event = artifact["cycle_result"]["synthesis_event"]
    assert synthesis_event["capability"] == "github_repository_management"
    assert synthesis_event["artifact_kind"] == "mcp_server"
    assert synthesis_event["status"] == "ok"
    assert synthesis_event["source"] == "planner_request"
    assert synthesis_event["generated_repo"] == "generated_mcp_server_github"
    assert isinstance(synthesis_event.get("used_evolution"), bool)

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
            "generated_repo": "generated_mcp_server_github",
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

    assert called["builder_called"] is True
    assert called["artifact_kind"] == "mcp_server"
    assert called["capability"] == "github_repository_management"
    assert isinstance(called["kwargs"], dict)
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

def test_run_autonomous_factory_cycle_generates_real_mcp_artifact(tmp_path, monkeypatch):
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

    output = tmp_path / "autonomous_factory_cycle.json"
    artifact = _mod.run_autonomous_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="action_effectiveness_ledger.json",
        policy="planner_policy.json",
        top_k=3,
        output=str(output),
    )

    generated = Path(artifact["cycle_result"]["builder"]["generated_repo"])

    try:
        assert artifact["cycle_result"]["builder"]["status"] == "ok"
        assert artifact["cycle_result"]["builder"]["artifact_kind"] == "mcp_server"
        assert artifact["cycle_result"]["builder"]["capability"] == "github_repository_management"

        assert generated.is_dir()
        assert (generated / "README.md").is_file()
        assert (generated / "manifest.json").is_file()
        assert (generated / "server.py").is_file()
        assert (generated / "tools" / "list_repositories.py").is_file()
        assert (generated / "tools" / "get_repository.py").is_file()
        assert (generated / "tools" / "create_issue.py").is_file()
        assert (generated / "tests" / "test_server_smoke.py").is_file()
    finally:
        if generated.exists():
            import shutil
            shutil.rmtree(generated)

def test_run_autonomous_factory_cycle_generates_evolved_mcp_artifact_for_missing_tool(
    tmp_path, monkeypatch
):
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

    _compare_calls_missing_tool = []

    def fake_compare_mcp_servers(generated_path, reference_path, output_path=None):
        _compare_calls_missing_tool.append(len(_compare_calls_missing_tool) + 1)
        score = 0.75 if len(_compare_calls_missing_tool) == 1 else 0.85
        return {
            "similarity": {"overall_score": score},
            "structure": {"generated_capability": "github_repository_management"},
            "tool_surface": {
                "coverage_ratio": 0.75,
                "missing_tools": ["get_me"],
            },
            "capability_surface": {
                "coverage_ratio": 1.0,
                "missing_enabled": [],
            },
            "testability": {"coverage_ratio": 1.0},
        }

    def fake_derive_capability_gaps_from_comparison(comparison):
        return {
            "capability_gaps": [
                {
                    "capability": "github_repository_management",
                    "gap_source": "reference_mcp_comparison",
                    "severity": 0.25,
                }
            ]
        }

    monkeypatch.setattr(_pipeline, "compare_mcp_servers", fake_compare_mcp_servers)
    monkeypatch.setattr(
        _pipeline,
        "derive_capability_gaps_from_comparison",
        fake_derive_capability_gaps_from_comparison,
    )

    output = tmp_path / "autonomous_factory_cycle.json"
    artifact = _mod.run_autonomous_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="action_effectiveness_ledger.json",
        policy="planner_policy.json",
        top_k=3,
        output=str(output),
    )

    generated = Path(artifact["cycle_result"]["builder"]["generated_repo"])

    try:
        builder_result = artifact["cycle_result"]["builder"]
        assert builder_result["status"] == "ok"
        assert builder_result["artifact_kind"] == "mcp_server"
        assert builder_result["capability"] == "github_repository_management"
        assert "get_me" in builder_result["tools"]

        assert "evolved_builder" in artifact["cycle_result"]
        assert artifact["cycle_result"]["evolved_builder"] == builder_result

        assert generated.is_dir()
        assert (generated / "tools" / "get_me.py").is_file()

        server_text = (generated / "server.py").read_text(encoding="utf-8")
        assert "from .tools.get_me import get_me as _get_me" in server_text
        assert "def get_me():" in server_text
        assert "return _get_me()" in server_text

        manifest = json.loads((generated / "manifest.json").read_text(encoding="utf-8"))
        assert "get_me" in manifest["tools"]
    finally:
        if generated.exists():
            import shutil
            shutil.rmtree(generated)

def test_run_autonomous_factory_cycle_generates_evolved_mcp_artifact_for_create_pull_request(
    tmp_path, monkeypatch
):
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

    _compare_calls_create_pr = []

    def fake_compare_mcp_servers(generated_path, reference_path, output_path=None):
        _compare_calls_create_pr.append(len(_compare_calls_create_pr) + 1)
        score = 0.75 if len(_compare_calls_create_pr) == 1 else 0.85
        return {
            "similarity": {"overall_score": score},
            "structure": {"generated_capability": "github_repository_management"},
            "tool_surface": {
                "coverage_ratio": 0.75,
                "missing_tools": ["create_pull_request"],
            },
            "capability_surface": {
                "coverage_ratio": 1.0,
                "missing_enabled": [],
            },
            "testability": {"coverage_ratio": 1.0},
        }

    def fake_derive_capability_gaps_from_comparison(comparison):
        return {
            "capability_gaps": [
                {
                    "capability": "github_repository_management",
                    "gap_source": "reference_mcp_comparison",
                    "severity": 0.25,
                }
            ]
        }

    monkeypatch.setattr(_pipeline, "compare_mcp_servers", fake_compare_mcp_servers)
    monkeypatch.setattr(
        _pipeline,
        "derive_capability_gaps_from_comparison",
        fake_derive_capability_gaps_from_comparison,
    )

    output = tmp_path / "autonomous_factory_cycle.json"
    artifact = _mod.run_autonomous_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="action_effectiveness_ledger.json",
        policy="planner_policy.json",
        top_k=3,
        output=str(output),
    )

    generated = Path(artifact["cycle_result"]["builder"]["generated_repo"])

    try:
        builder_result = artifact["cycle_result"]["builder"]
        assert builder_result["status"] == "ok"
        assert builder_result["artifact_kind"] == "mcp_server"
        assert builder_result["capability"] == "github_repository_management"
        assert "create_pull_request" in builder_result["tools"]

        assert "evolved_builder" in artifact["cycle_result"]
        assert artifact["cycle_result"]["evolved_builder"] == builder_result

        assert generated.is_dir()
        assert (generated / "tools" / "create_pull_request.py").is_file()

        server_text = (generated / "server.py").read_text(encoding="utf-8")
        assert (
            "from .tools.create_pull_request import create_pull_request as _create_pull_request"
            in server_text
        )
        assert "def create_pull_request():" in server_text
        assert "return _create_pull_request()" in server_text

        manifest = json.loads((generated / "manifest.json").read_text(encoding="utf-8"))
        assert "create_pull_request" in manifest["tools"]
    finally:
        if generated.exists():
            import shutil
            shutil.rmtree(generated)

def test_run_autonomous_factory_cycle_generates_evolved_mcp_artifact_for_get_copilot_space(
    tmp_path, monkeypatch
):
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

    _compare_calls_copilot = []

    def fake_compare_mcp_servers(generated_path, reference_path, output_path=None):
        _compare_calls_copilot.append(len(_compare_calls_copilot) + 1)
        score = 0.75 if len(_compare_calls_copilot) == 1 else 0.85
        return {
            "similarity": {"overall_score": score},
            "structure": {"generated_capability": "github_repository_management"},
            "tool_surface": {
                "coverage_ratio": 0.75,
                "missing_tools": ["get_copilot_space"],
            },
            "capability_surface": {
                "coverage_ratio": 1.0,
                "missing_enabled": [],
            },
            "testability": {"coverage_ratio": 1.0},
        }

    def fake_derive_capability_gaps_from_comparison(comparison):
        return {
            "capability_gaps": [
                {
                    "capability": "github_repository_management",
                    "gap_source": "reference_mcp_comparison",
                    "severity": 0.25,
                }
            ]
        }

    monkeypatch.setattr(_pipeline, "compare_mcp_servers", fake_compare_mcp_servers)
    monkeypatch.setattr(
        _pipeline,
        "derive_capability_gaps_from_comparison",
        fake_derive_capability_gaps_from_comparison,
    )

    output = tmp_path / "autonomous_factory_cycle.json"
    artifact = _mod.run_autonomous_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="action_effectiveness_ledger.json",
        policy="planner_policy.json",
        top_k=3,
        output=str(output),
    )

    generated = Path(artifact["cycle_result"]["builder"]["generated_repo"])

    try:
        builder_result = artifact["cycle_result"]["builder"]
        assert builder_result["status"] == "ok"
        assert builder_result["artifact_kind"] == "mcp_server"
        assert builder_result["capability"] == "github_repository_management"
        assert "get_copilot_space" in builder_result["tools"]

        assert "evolved_builder" in artifact["cycle_result"]
        assert artifact["cycle_result"]["evolved_builder"] == builder_result

        assert generated.is_dir()
        assert (generated / "tools" / "get_copilot_space.py").is_file()

        server_text = (generated / "server.py").read_text(encoding="utf-8")
        assert (
            "from .tools.get_copilot_space import get_copilot_space as _get_copilot_space"
            in server_text
        )
        assert "def get_copilot_space():" in server_text
        assert "return _get_copilot_space()" in server_text

        manifest = json.loads((generated / "manifest.json").read_text(encoding="utf-8"))
        assert "get_copilot_space" in manifest["tools"]
    finally:
        if generated.exists():
            import shutil
            shutil.rmtree(generated)


def test_run_autonomous_factory_cycle_similarity_progression_across_cycles(tmp_path, monkeypatch):
    evaluation = {"risk_level": "moderate_risk", "reasons": []}

    governed_result = {
        "selected_offset": 0,
        "result": {
            "evaluation_summary": {
                "runs": [
                    {
                        "selected_actions": ["build_mcp_server"],
                        "selection_detail": {
                            "ranked_action_window": ["build_mcp_server"],
                            "ranked_action_window_detail": [
                                {
                                    "action_type": "build_mcp_server",
                                    "task_binding": {
                                        "args": {
                                            "capability": "github_repository_management"
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
            "generated_repo": "/tmp/generated_mcp_server_github",
        }

    monkeypatch.setattr(_pipeline, "build_capability_artifact", _fake_builder)

    similarity_values = [0.40, 0.65, 0.78]

    def _fake_compare(generated_path, reference_path, output_path=None):
        return {
            "similarity": {"overall_score": similarity_values.pop(0)},
            "structure": {"generated_capability": "github_repository_management"},
            "tool_surface": {"coverage_ratio": 0.5, "missing_tools": []},
            "capability_surface": {"coverage_ratio": 0.5},
            "testability": {"coverage_ratio": 1.0},
        }

    monkeypatch.setattr(_pipeline, "compare_mcp_servers", _fake_compare, raising=False)

    capability_ledger = tmp_path / "capability_effectiveness_ledger.json"

    # -------- cycle 1 --------

    artifact1 = _mod.run_autonomous_factory_cycle(
        portfolio_state="portfolio_state.json",
        capability_ledger_output=str(capability_ledger),
        policy="planner_policy.json",
        top_k=3,
        output=str(tmp_path / "cycle1.json"),
    )

    row1 = artifact1["capability_effectiveness_ledger"]["capabilities"]["github_repository_management"]

    assert row1["similarity_score"] == 0.40
    assert "previous_similarity_score" not in row1
    assert "similarity_delta" not in row1

    # -------- cycle 2 --------

    _mod.run_autonomous_factory_cycle(
        portfolio_state="portfolio_state.json",
        capability_ledger=str(capability_ledger),
        capability_ledger_output=str(capability_ledger),
        policy="planner_policy.json",
        top_k=3,
        output=str(tmp_path / "cycle2.json"),
    )

    import json

    persisted2 = json.loads(capability_ledger.read_text())
    row2 = persisted2["capabilities"]["github_repository_management"]

    assert row2["previous_similarity_score"] == 0.40
    assert row2["similarity_score"] == 0.65
    assert row2["similarity_delta"] == 0.25

    # -------- cycle 3 --------

    _mod.run_autonomous_factory_cycle(
        portfolio_state="portfolio_state.json",
        capability_ledger=str(capability_ledger),
        capability_ledger_output=str(capability_ledger),
        policy="planner_policy.json",
        top_k=3,
        output=str(tmp_path / "cycle3.json"),
    )

    persisted3 = json.loads(capability_ledger.read_text())
    row3 = persisted3["capabilities"]["github_repository_management"]

    assert row3["previous_similarity_score"] == 0.65
    assert row3["similarity_score"] == 0.78
    assert row3["similarity_delta"] == 0.13



def test_run_autonomous_factory_cycle_updates_capability_artifact_registry_output(tmp_path, monkeypatch):
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

    registry_output = tmp_path / "capability_artifact_registry.json"
    output = tmp_path / "autonomous_factory_cycle.json"

    artifact = _mod.run_autonomous_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="action_effectiveness_ledger.json",
        capability_artifact_registry_output=str(registry_output),
        policy="planner_policy.json",
        top_k=3,
        output=str(output),
    )

    persisted = _read_json(registry_output)

    assert persisted == {
        "capabilities": {
            "snowflake_data_access": {
                "artifact_kind": "data_connector",
                "history": [
                    {
                        "artifact": "generated_data_connector_snowflake",
                        "revision": 1,
                        "source": "planner_request",
                        "status": "ok",
                        "used_evolution": False,
                    }
                ],
                "latest_artifact": "generated_data_connector_snowflake",
                "revision": 1,
            }
        }
    }
    assert artifact["cycle_result"]["synthesis_event"]["generated_repo"] == "generated_data_connector_snowflake"


def test_run_autonomous_factory_cycle_updates_existing_capability_artifact_registry_output(tmp_path, monkeypatch):
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
            "generated_repo": "generated_data_connector_snowflake_v2",
        }

    monkeypatch.setattr(_pipeline, "build_capability_artifact", _fake_builder)

    registry = tmp_path / "capability_artifact_registry.json"
    registry.write_text(
        json.dumps(
            {
                "capabilities": {
                    "snowflake_data_access": {
                        "artifact_kind": "data_connector",
                        "history": [
                            {
                                "artifact": "generated_data_connector_snowflake_v1",
                                "revision": 1,
                                "source": "portfolio_gap",
                                "status": "ok",
                                "used_evolution": False,
                            }
                        ],
                        "latest_artifact": "generated_data_connector_snowflake_v1",
                        "revision": 1,
                    }
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )

    output = tmp_path / "autonomous_factory_cycle.json"

    _mod.run_autonomous_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="action_effectiveness_ledger.json",
        capability_artifact_registry_output=str(registry),
        policy="planner_policy.json",
        top_k=3,
        output=str(output),
    )

    persisted = _read_json(registry)
    row = persisted["capabilities"]["snowflake_data_access"]

    assert row["latest_artifact"] == "generated_data_connector_snowflake_v2"
    assert row["revision"] == 2
    assert len(row["history"]) == 2
    assert row["history"][-1] == {
        "artifact": "generated_data_connector_snowflake_v2",
        "revision": 2,
        "source": "planner_request",
        "status": "ok",
        "used_evolution": False,
    }


# ---------------------------------------------------------------------------
# Regression: build_capability_artifact must not map to null in ACTION_TO_TASK
# ---------------------------------------------------------------------------

def test_build_capability_artifact_not_null_in_action_to_task():
    """evaluate_planner_config must classify the demo portfolio as low_risk → governed_run.

    Root cause guarded: ACTION_TO_TASK was missing 'build_capability_artifact',
    causing mapped_tasks=[null, ...], unique_tasks=1, collision_ratio=0.5,
    entropy_gap=1.0 — all three high_risk thresholds firing simultaneously.
    """
    from factory_pipeline import decide_action
    from scripts.evaluate_planner_config import evaluate_planner_config

    _REPO_ROOT = Path(__file__).resolve().parents[1]
    portfolio_state = str(
        _REPO_ROOT / "experiments" / "factory_demo" / "portfolio_state_missing_github.json"
    )
    ledger = str(
        _REPO_ROOT / "experiments" / "factory_demo" / "action_effectiveness_ledger.json"
    )

    evaluation = evaluate_planner_config(
        portfolio_state_path=portfolio_state,
        ledger_path=ledger,
        policy_path=None,
        top_k=3,
        output_path=None,
    )

    mapped_tasks = evaluation.get("mapped_tasks", [])
    assert None not in mapped_tasks, (
        f"build_capability_artifact maps to null — ACTION_TO_TASK entry missing. "
        f"mapped_tasks={mapped_tasks}"
    )
    assert evaluation.get("risk_level") == "low_risk", (
        f"demo portfolio expected low_risk, got {evaluation.get('risk_level')!r}: "
        f"{evaluation.get('reasons')}"
    )
    assert decide_action(evaluation)["action"] == "governed_run", (
        f"expected governed_run for low_risk evaluation, got: {decide_action(evaluation)}"
    )


def test_run_autonomous_factory_cycle_persists_ledger_when_only_capability_ledger_provided(
    tmp_path, monkeypatch
):
    """Guard fix: ledger update must run when capability_ledger is set but capability_ledger_output is None."""
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

    calls = []

    def _spy_update(ledger_path, cycle_artifact_path, output_path):
        calls.append({
            "ledger_path": ledger_path,
            "cycle_artifact_path": cycle_artifact_path,
            "output_path": output_path,
        })

    monkeypatch.setattr(_mod, "update_capability_effectiveness_ledger", _spy_update)

    capability_ledger = tmp_path / "capability_effectiveness_ledger.json"
    capability_ledger.write_text(json.dumps({"capabilities": {}}), encoding="utf-8")
    output = tmp_path / "autonomous_factory_cycle.json"

    _mod.run_autonomous_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="action_effectiveness_ledger.json",
        capability_ledger=str(capability_ledger),
        capability_ledger_output=None,
        policy="planner_policy.json",
        top_k=3,
        output=str(output),
    )

    assert len(calls) == 1, (
        f"update_capability_effectiveness_ledger should have been called once; calls={calls}"
    )
    assert calls[0]["ledger_path"] == str(capability_ledger)
    assert calls[0]["output_path"] is None


def test_run_autonomous_factory_cycle_skips_ledger_when_both_paths_none(
    tmp_path, monkeypatch
):
    """Silent-skip preserved: ledger update must NOT run when both capability_ledger and capability_ledger_output are None."""
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

    calls = []

    def _spy_update(ledger_path, cycle_artifact_path, output_path):
        calls.append(True)

    monkeypatch.setattr(_mod, "update_capability_effectiveness_ledger", _spy_update)

    output = tmp_path / "autonomous_factory_cycle.json"

    _mod.run_autonomous_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="action_effectiveness_ledger.json",
        capability_ledger=None,
        capability_ledger_output=None,
        policy="planner_policy.json",
        top_k=3,
        output=str(output),
    )

    assert len(calls) == 0, (
        f"update_capability_effectiveness_ledger should NOT have been called; calls={calls}"
    )


def test_multi_cycle_failed_synthesis_lowers_ordinal_rank_in_cycle_2(tmp_path, monkeypatch):
    """After two failed syntheses for cap_x, the planner's learning signal
    deprioritizes cap_x below cap_y (no history).  At total=1 failure the
    exploration bonus (+0.004) outweighs the reliability penalty (-0.003), so
    the signal only activates on the second failure (net -0.007 at total=2).
    The ledger is pre-seeded with one prior failure to put cycle 1 over the
    threshold."""
    import json as _json
    from planner_runtime import _apply_learning_adjustments, load_capability_effectiveness_ledger

    evaluation = {"risk_level": "moderate_risk", "reasons": []}

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
                                            "artifact_kind": "mcp_server",
                                            "capability": "cap_x",
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
            "status": "failed",
            "artifact_kind": artifact_kind,
            "capability": capability,
        }

    monkeypatch.setattr(_pipeline, "build_capability_artifact", _fake_builder)

    capability_ledger = tmp_path / "capability_effectiveness_ledger.json"

    # Pre-seed ledger with one prior failure so cycle 1 pushes total to 2,
    # crossing the threshold where reliability penalty > exploration bonus.
    pre_seed = {
        "capabilities": {
            "cap_x": {
                "capability": "cap_x",
                "total_syntheses": 1,
                "successful_syntheses": 0,
                "failed_syntheses": 1,
                "last_synthesis_status": "error",
            }
        }
    }
    capability_ledger.write_text(_json.dumps(pre_seed), encoding="utf-8")

    # Cycle 1: reads the pre-seeded ledger, fails for cap_x, writes total=2/failed=2.
    _mod.run_autonomous_factory_cycle(
        portfolio_state="portfolio_state.json",
        capability_ledger=str(capability_ledger),
        capability_ledger_output=str(capability_ledger),
        policy="planner_policy.json",
        top_k=3,
        output=str(tmp_path / "cycle1.json"),
    )

    # Verify ledger was written with accumulated failure.
    assert capability_ledger.exists(), "ledger file must be written after cycle 1"
    loaded_ledger = load_capability_effectiveness_ledger(str(capability_ledger))
    caps = loaded_ledger.get("capabilities", {})
    assert "cap_x" in caps, f"cap_x must appear in ledger; got {list(caps.keys())}"
    assert caps["cap_x"]["failed_syntheses"] == 2

    # Assert learning signal: cap_x (2 failures, net -0.007) ranks below
    # cap_y (no history, net 0.0).
    action_cap_x = {
        "action_type": "build_capability_artifact",
        "priority": 10.0,
        "action_id": "aid-x",
        "args": {"capability": "cap_x"},
    }
    action_cap_y = {
        "action_type": "build_capability_artifact",
        "priority": 10.0,
        "action_id": "aid-y",
        "args": {"capability": "cap_y"},
    }

    ranked = _apply_learning_adjustments(
        [action_cap_x, action_cap_y], {}, capability_ledger=loaded_ledger
    )

    assert ranked[-1]["args"]["capability"] == "cap_x", (
        f"cap_x (2 failures) must rank last; got {[a['args']['capability'] for a in ranked]}"
    )
    assert ranked[0]["args"]["capability"] != "cap_x", (
        f"cap_y (no history) must rank first; got {ranked[0]['args']['capability']}"
    )


def test_monotonic_rank_degradation_across_four_cycles(tmp_path, monkeypatch):
    """cap_x accumulates 1 failure per cycle over 3 cycles (pre-seed total=1,
    ending at total=4). At every step the reliability adjustment is strictly
    more negative, so cap_x ranks strictly last vs cap_y (no history) and its
    adjusted score falls monotonically."""
    import json as _json
    from planner_runtime import (
        _apply_learning_adjustments,
        _compute_priority_breakdown,
        load_capability_effectiveness_ledger,
    )

    evaluation = {"risk_level": "moderate_risk", "reasons": []}

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
                                            "artifact_kind": "mcp_server",
                                            "capability": "cap_x",
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
            "status": "failed",
            "artifact_kind": artifact_kind,
            "capability": capability,
        }

    monkeypatch.setattr(_pipeline, "build_capability_artifact", _fake_builder)

    # Pre-seed ledger: cap_x total=1, failed=1.
    capability_ledger = tmp_path / "capability_effectiveness_ledger.json"
    pre_seed = {
        "capabilities": {
            "cap_x": {
                "capability": "cap_x",
                "total_syntheses": 1,
                "successful_syntheses": 0,
                "failed_syntheses": 1,
                "last_synthesis_status": "error",
            }
        }
    }
    capability_ledger.write_text(_json.dumps(pre_seed), encoding="utf-8")

    action_cap_x = {
        "action_type": "build_capability_artifact",
        "priority": 10.0,
        "action_id": "aid-x",
        "args": {"capability": "cap_x"},
    }
    action_cap_y = {
        "action_type": "build_capability_artifact",
        "priority": 10.0,
        "action_id": "aid-y",
        "args": {"capability": "cap_y"},
    }

    prev_cap_x_score = float("inf")
    for cycle_idx in range(1, 4):  # 3 cycles: totals become 2, 3, 4
        _mod.run_autonomous_factory_cycle(
            portfolio_state="portfolio_state.json",
            capability_ledger=str(capability_ledger),
            capability_ledger_output=str(capability_ledger),
            policy="planner_policy.json",
            top_k=3,
            output=str(tmp_path / f"cycle{cycle_idx}.json"),
        )

        loaded_ledger = load_capability_effectiveness_ledger(str(capability_ledger))
        caps = loaded_ledger.get("capabilities", {})
        expected_total = cycle_idx + 1
        assert caps["cap_x"]["total_syntheses"] == expected_total, (
            f"cycle {cycle_idx}: expected total_syntheses={expected_total}, "
            f"got {caps['cap_x']['total_syntheses']}"
        )

        ranked = _apply_learning_adjustments(
            [action_cap_x, action_cap_y], {}, capability_ledger=loaded_ledger
        )
        assert ranked[-1]["args"]["capability"] == "cap_x", (
            f"cycle {cycle_idx}: cap_x must rank last, got "
            f"{[a['args']['capability'] for a in ranked]}"
        )

        # _apply_learning_adjustments sorts by computed final_priority but does
        # not mutate the dict's 'priority' field.  Compute the adjusted score
        # directly so the monotonic assertion tracks the actual learning signal.
        bd = _compute_priority_breakdown(action_cap_x, {}, {}, {}, loaded_ledger)
        cap_x_score = bd.final_priority
        assert cap_x_score < prev_cap_x_score, (
            f"cycle {cycle_idx}: cap_x score {cap_x_score} not strictly below "
            f"prior {prev_cap_x_score}"
        )
        prev_cap_x_score = cap_x_score


def test_monotonic_rank_reinforcement_across_four_cycles(tmp_path, monkeypatch):
    """cap_x accumulates 1 success per cycle over 3 cycles (pre-seed total=1,
    ending at total=4). At every step the reliability adjustment is strictly
    more positive, so cap_x ranks strictly first vs cap_y (no history) and its
    adjusted score rises monotonically."""
    import json as _json
    from planner_runtime import (
        _apply_learning_adjustments,
        _compute_priority_breakdown,
        load_capability_effectiveness_ledger,
    )

    evaluation = {"risk_level": "moderate_risk", "reasons": []}

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
                                            "artifact_kind": "mcp_server",
                                            "capability": "cap_x",
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
        }

    monkeypatch.setattr(_pipeline, "build_capability_artifact", _fake_builder)

    # Pre-seed ledger: cap_x total=1, successful=1.
    capability_ledger = tmp_path / "capability_effectiveness_ledger.json"
    pre_seed = {
        "capabilities": {
            "cap_x": {
                "capability": "cap_x",
                "total_syntheses": 1,
                "successful_syntheses": 1,
                "failed_syntheses": 0,
                "last_synthesis_status": "ok",
            }
        }
    }
    capability_ledger.write_text(_json.dumps(pre_seed), encoding="utf-8")

    action_cap_x = {
        "action_type": "build_capability_artifact",
        "priority": 10.0,
        "action_id": "aid-x",
        "args": {"capability": "cap_x"},
    }
    action_cap_y = {
        "action_type": "build_capability_artifact",
        "priority": 10.0,
        "action_id": "aid-y",
        "args": {"capability": "cap_y"},
    }

    prev_cap_x_score = float("-inf")
    for cycle_idx in range(1, 4):  # 3 cycles: totals become 2, 3, 4
        _mod.run_autonomous_factory_cycle(
            portfolio_state="portfolio_state.json",
            capability_ledger=str(capability_ledger),
            capability_ledger_output=str(capability_ledger),
            policy="planner_policy.json",
            top_k=3,
            output=str(tmp_path / f"cycle{cycle_idx}.json"),
        )

        loaded_ledger = load_capability_effectiveness_ledger(str(capability_ledger))
        caps = loaded_ledger.get("capabilities", {})
        expected_total = cycle_idx + 1
        assert caps["cap_x"]["total_syntheses"] == expected_total, (
            f"cycle {cycle_idx}: expected total_syntheses={expected_total}, "
            f"got {caps['cap_x']['total_syntheses']}"
        )
        assert caps["cap_x"]["successful_syntheses"] == expected_total, (
            f"cycle {cycle_idx}: expected successful_syntheses={expected_total}, "
            f"got {caps['cap_x']['successful_syntheses']}"
        )

        ranked = _apply_learning_adjustments(
            [action_cap_x, action_cap_y], {}, capability_ledger=loaded_ledger
        )
        assert ranked[0]["args"]["capability"] == "cap_x", (
            f"cycle {cycle_idx}: cap_x must rank first, got "
            f"{[a['args']['capability'] for a in ranked]}"
        )

        bd = _compute_priority_breakdown(action_cap_x, {}, {}, {}, loaded_ledger)
        cap_x_score = bd.final_priority
        assert cap_x_score > prev_cap_x_score, (
            f"cycle {cycle_idx}: cap_x score {cap_x_score} not strictly above "
            f"prior {prev_cap_x_score}"
        )
        prev_cap_x_score = cap_x_score


def test_cross_capability_competition_rankings_cross(tmp_path, monkeypatch):
    """cap_y accumulates 3 failed cycles; cap_x accumulates 3 successful cycles.
    After phase 1 (cap_y failures) cap_x already ranks above cap_y via the
    exploration bonus.  After phase 2 (cap_x successes) the gap widens: cap_x
    carries a positive reliability adjustment and cap_y a negative one, with
    cap_x ranked first throughout."""
    import json as _json
    from planner_runtime import (
        _apply_learning_adjustments,
        _compute_capability_reliability_adjustment,
        _compute_priority_breakdown,
        load_capability_effectiveness_ledger,
    )

    evaluation = {"risk_level": "moderate_risk", "reasons": []}
    monkeypatch.setattr(_mod, "evaluate_planner_config", lambda **kwargs: evaluation)

    # Mutable state drives both the governed result and the builder response
    # so that phase 1 and phase 2 differ only in which capability is built and
    # whether the build succeeds.
    state = {"capability": "cap_y", "status": "failed"}

    def _dynamic_governed_result(args):
        return {
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
                                                "artifact_kind": "mcp_server",
                                                "capability": state["capability"],
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

    def _dynamic_builder(*, artifact_kind, capability, **kwargs):
        return {
            "status": state["status"],
            "artifact_kind": artifact_kind,
            "capability": capability,
        }

    monkeypatch.setattr(_mod, "run_governed_loop", _dynamic_governed_result)
    monkeypatch.setattr(_pipeline, "build_capability_artifact", _dynamic_builder)

    capability_ledger = tmp_path / "capability_effectiveness_ledger.json"
    capability_ledger.write_text(_json.dumps({"capabilities": {}}), encoding="utf-8")

    action_cap_x = {
        "action_type": "build_capability_artifact",
        "priority": 10.0,
        "action_id": "aid-x",
        "args": {"capability": "cap_x"},
    }
    action_cap_y = {
        "action_type": "build_capability_artifact",
        "priority": 10.0,
        "action_id": "aid-y",
        "args": {"capability": "cap_y"},
    }

    # --- Phase 1: 3 failure cycles for cap_y ---
    state["capability"] = "cap_y"
    state["status"] = "failed"
    for i in range(1, 4):
        _mod.run_autonomous_factory_cycle(
            portfolio_state="portfolio_state.json",
            capability_ledger=str(capability_ledger),
            capability_ledger_output=str(capability_ledger),
            policy="planner_policy.json",
            top_k=3,
            output=str(tmp_path / f"phase1_cycle{i}.json"),
        )

    ledger_after_p1 = load_capability_effectiveness_ledger(str(capability_ledger))
    caps_p1 = ledger_after_p1.get("capabilities", {})

    assert caps_p1.get("cap_y", {}).get("failed_syntheses") == 3, (
        f"phase 1: expected cap_y failed_syntheses=3, got {caps_p1.get('cap_y')}"
    )
    assert "cap_x" not in caps_p1, (
        f"phase 1: cap_x must not appear in ledger yet; got {list(caps_p1.keys())}"
    )

    # cap_y has negative reliability adjustment; cap_x has exploration bonus only.
    cap_y_adj_p1 = _compute_capability_reliability_adjustment(action_cap_y, ledger_after_p1)
    assert cap_y_adj_p1 < 0.0, (
        f"phase 1: cap_y reliability adjustment must be negative; got {cap_y_adj_p1}"
    )

    ranked_p1 = _apply_learning_adjustments(
        [action_cap_x, action_cap_y], {}, capability_ledger=ledger_after_p1
    )
    assert ranked_p1[0]["args"]["capability"] == "cap_x", (
        f"phase 1: cap_x (exploration bonus) must rank above cap_y (negative adj); "
        f"got {[a['args']['capability'] for a in ranked_p1]}"
    )

    # --- Phase 2: 3 success cycles for cap_x ---
    state["capability"] = "cap_x"
    state["status"] = "ok"
    for i in range(1, 4):
        _mod.run_autonomous_factory_cycle(
            portfolio_state="portfolio_state.json",
            capability_ledger=str(capability_ledger),
            capability_ledger_output=str(capability_ledger),
            policy="planner_policy.json",
            top_k=3,
            output=str(tmp_path / f"phase2_cycle{i}.json"),
        )

    ledger_after_p2 = load_capability_effectiveness_ledger(str(capability_ledger))
    caps_p2 = ledger_after_p2.get("capabilities", {})

    assert caps_p2.get("cap_x", {}).get("successful_syntheses") == 3, (
        f"phase 2: expected cap_x successful_syntheses=3, got {caps_p2.get('cap_x')}"
    )
    assert caps_p2.get("cap_y", {}).get("failed_syntheses") == 3, (
        f"phase 2: cap_y failed_syntheses must remain 3; got {caps_p2.get('cap_y')}"
    )

    # cap_x carries a positive reliability adjustment; cap_y remains negative.
    cap_x_adj_p2 = _compute_capability_reliability_adjustment(action_cap_x, ledger_after_p2)
    cap_y_adj_p2 = _compute_capability_reliability_adjustment(action_cap_y, ledger_after_p2)
    assert cap_x_adj_p2 > 0.0, (
        f"phase 2: cap_x reliability adjustment must be positive; got {cap_x_adj_p2}"
    )
    assert cap_y_adj_p2 < 0.0, (
        f"phase 2: cap_y reliability adjustment must remain negative; got {cap_y_adj_p2}"
    )

    ranked_p2 = _apply_learning_adjustments(
        [action_cap_x, action_cap_y], {}, capability_ledger=ledger_after_p2
    )
    assert ranked_p2[0]["args"]["capability"] == "cap_x", (
        f"phase 2: cap_x (positive adj) must rank above cap_y (negative adj); "
        f"got {[a['args']['capability'] for a in ranked_p2]}"
    )
    assert ranked_p2[-1]["args"]["capability"] == "cap_y", (
        f"phase 2: cap_y must rank last; "
        f"got {[a['args']['capability'] for a in ranked_p2]}"
    )

    # Score gap must have widened from phase 1 to phase 2.
    bd_x_p1 = _compute_priority_breakdown(action_cap_x, {}, {}, {}, ledger_after_p1)
    bd_y_p1 = _compute_priority_breakdown(action_cap_y, {}, {}, {}, ledger_after_p1)
    bd_x_p2 = _compute_priority_breakdown(action_cap_x, {}, {}, {}, ledger_after_p2)
    bd_y_p2 = _compute_priority_breakdown(action_cap_y, {}, {}, {}, ledger_after_p2)
    gap_p1 = bd_x_p1.final_priority - bd_y_p1.final_priority
    gap_p2 = bd_x_p2.final_priority - bd_y_p2.final_priority
    assert gap_p2 > gap_p1 > 0.0, (
        f"score gap must widen across phases: phase1={gap_p1:.6f}, phase2={gap_p2:.6f}"
    )


def test_end_to_end_learning_loop_integrated_sequence(tmp_path, monkeypatch):
    """Validates the complete feedback loop as a single uninterrupted sequence
    starting from a blank ledger.

    Three explicit checkpoints:
      0 — baseline: empty ledger, both capabilities absent, both adj == 0.0
      1 — after cap_x success cycle: ledger updated, reliability_adj > 0,
          cap_x ranks above cap_y
      2 — after cap_y failure cycle: ledger updated, cap_y reliability_adj < 0
          (signal direction confirmed even while exploration partially offsets it),
          cap_x net > cap_y net, cap_x still ranks above cap_y

    Unique coverage: blank-slate start; two capabilities receive interleaved
    opposing signals in the same sequence; reliability component sign is asserted
    directly at each checkpoint.
    """
    import json as _json
    from planner_runtime import (
        _apply_learning_adjustments,
        _compute_capability_reliability_adjustment,
        _compute_priority_breakdown,
        load_capability_effectiveness_ledger,
    )

    evaluation = {"risk_level": "moderate_risk", "reasons": []}
    monkeypatch.setattr(_mod, "evaluate_planner_config", lambda **kwargs: evaluation)

    state = {"capability": "cap_x", "status": "ok"}

    def _dynamic_governed_result(args):
        return {
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
                                                "artifact_kind": "mcp_server",
                                                "capability": state["capability"],
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

    def _dynamic_builder(*, artifact_kind, capability, **kwargs):
        return {
            "status": state["status"],
            "artifact_kind": artifact_kind,
            "capability": capability,
        }

    monkeypatch.setattr(_mod, "run_governed_loop", _dynamic_governed_result)
    monkeypatch.setattr(_pipeline, "build_capability_artifact", _dynamic_builder)

    capability_ledger = tmp_path / "capability_effectiveness_ledger.json"
    capability_ledger.write_text(_json.dumps({"capabilities": {}}), encoding="utf-8")

    action_cap_x = {
        "action_type": "build_capability_artifact",
        "priority": 10.0,
        "action_id": "aid-x",
        "args": {"capability": "cap_x"},
    }
    action_cap_y = {
        "action_type": "build_capability_artifact",
        "priority": 10.0,
        "action_id": "aid-y",
        "args": {"capability": "cap_y"},
    }

    # --- Checkpoint 0: baseline — blank ledger, both adjustments must be zero ---
    ledger_baseline = load_capability_effectiveness_ledger(str(capability_ledger))
    assert _compute_capability_reliability_adjustment(action_cap_x, ledger_baseline) == 0.0, (
        "baseline: cap_x reliability adjustment must be 0.0 with no history"
    )
    assert _compute_capability_reliability_adjustment(action_cap_y, ledger_baseline) == 0.0, (
        "baseline: cap_y reliability adjustment must be 0.0 with no history"
    )
    assert "cap_x" not in ledger_baseline.get("capabilities", {}), (
        "baseline: cap_x must be absent from ledger"
    )
    assert "cap_y" not in ledger_baseline.get("capabilities", {}), (
        "baseline: cap_y must be absent from ledger"
    )

    # --- Cycle 1: cap_x succeeds ---
    state["capability"] = "cap_x"
    state["status"] = "ok"
    _mod.run_autonomous_factory_cycle(
        portfolio_state="portfolio_state.json",
        capability_ledger=str(capability_ledger),
        capability_ledger_output=str(capability_ledger),
        policy="planner_policy.json",
        top_k=3,
        output=str(tmp_path / "cycle1.json"),
    )

    # --- Checkpoint 1: cap_x positive signal recorded and reflected in ranking ---
    ledger_c1 = load_capability_effectiveness_ledger(str(capability_ledger))
    caps_c1 = ledger_c1.get("capabilities", {})

    assert caps_c1.get("cap_x", {}).get("total_syntheses") == 1, (
        f"checkpoint 1: cap_x total_syntheses must be 1; got {caps_c1.get('cap_x')}"
    )
    assert caps_c1.get("cap_x", {}).get("successful_syntheses") == 1, (
        f"checkpoint 1: cap_x successful_syntheses must be 1; got {caps_c1.get('cap_x')}"
    )
    assert "cap_y" not in caps_c1, (
        f"checkpoint 1: cap_y must still be absent from ledger; got {list(caps_c1.keys())}"
    )

    cap_x_rel_c1 = _compute_capability_reliability_adjustment(action_cap_x, ledger_c1)
    assert cap_x_rel_c1 > 0.0, (
        f"checkpoint 1: cap_x reliability_adj must be positive; got {cap_x_rel_c1}"
    )

    ranked_c1 = _apply_learning_adjustments(
        [action_cap_x, action_cap_y], {}, capability_ledger=ledger_c1
    )
    assert ranked_c1[0]["args"]["capability"] == "cap_x", (
        f"checkpoint 1: cap_x must rank above cap_y (no history); "
        f"got {[a['args']['capability'] for a in ranked_c1]}"
    )

    bd_x_c1 = _compute_priority_breakdown(action_cap_x, {}, {}, {}, ledger_c1)
    bd_y_c1 = _compute_priority_breakdown(action_cap_y, {}, {}, {}, ledger_c1)
    assert bd_x_c1.final_priority > bd_y_c1.final_priority, (
        f"checkpoint 1: cap_x final_priority ({bd_x_c1.final_priority:.6f}) must exceed "
        f"cap_y final_priority ({bd_y_c1.final_priority:.6f})"
    )

    # --- Cycle 2: cap_y fails ---
    state["capability"] = "cap_y"
    state["status"] = "failed"
    _mod.run_autonomous_factory_cycle(
        portfolio_state="portfolio_state.json",
        capability_ledger=str(capability_ledger),
        capability_ledger_output=str(capability_ledger),
        policy="planner_policy.json",
        top_k=3,
        output=str(tmp_path / "cycle2.json"),
    )

    # --- Checkpoint 2: cap_y negative reliability signal; cap_x still leads ---
    ledger_c2 = load_capability_effectiveness_ledger(str(capability_ledger))
    caps_c2 = ledger_c2.get("capabilities", {})

    assert caps_c2.get("cap_y", {}).get("total_syntheses") == 1, (
        f"checkpoint 2: cap_y total_syntheses must be 1; got {caps_c2.get('cap_y')}"
    )
    assert caps_c2.get("cap_y", {}).get("failed_syntheses") == 1, (
        f"checkpoint 2: cap_y failed_syntheses must be 1; got {caps_c2.get('cap_y')}"
    )
    assert caps_c2.get("cap_x", {}).get("successful_syntheses") == 1, (
        f"checkpoint 2: cap_x ledger must be unchanged; got {caps_c2.get('cap_x')}"
    )

    # Reliability component is negative even though exploration bonus partially offsets
    # it in the net score at total=1 (exploration bonus > reliability penalty at low total).
    cap_y_rel_c2 = _compute_capability_reliability_adjustment(action_cap_y, ledger_c2)
    assert cap_y_rel_c2 < 0.0, (
        f"checkpoint 2: cap_y reliability_adj must be negative after 1 failure; "
        f"got {cap_y_rel_c2}"
    )

    # cap_x reliability component unchanged.
    cap_x_rel_c2 = _compute_capability_reliability_adjustment(action_cap_x, ledger_c2)
    assert cap_x_rel_c2 == cap_x_rel_c1, (
        f"checkpoint 2: cap_x reliability_adj must be unchanged; "
        f"got {cap_x_rel_c2}, expected {cap_x_rel_c1}"
    )

    ranked_c2 = _apply_learning_adjustments(
        [action_cap_x, action_cap_y], {}, capability_ledger=ledger_c2
    )
    assert ranked_c2[0]["args"]["capability"] == "cap_x", (
        f"checkpoint 2: cap_x must still rank above cap_y; "
        f"got {[a['args']['capability'] for a in ranked_c2]}"
    )

    bd_x_c2 = _compute_priority_breakdown(action_cap_x, {}, {}, {}, ledger_c2)
    bd_y_c2 = _compute_priority_breakdown(action_cap_y, {}, {}, {}, ledger_c2)
    assert bd_x_c2.final_priority > bd_y_c2.final_priority, (
        f"checkpoint 2: cap_x final_priority ({bd_x_c2.final_priority:.6f}) must exceed "
        f"cap_y final_priority ({bd_y_c2.final_priority:.6f})"
    )


def test_exploration_bonus_decays_as_successful_syntheses_accumulate_via_cycle(
    tmp_path, monkeypatch
):
    """cap_x starts with no ledger history (blank slate). Five successful cycles
    are executed via run_autonomous_factory_cycle. After each cycle the
    capability exploration bonus (_compute_capability_exploration_adjustment)
    must be strictly less than the previous value. At cycle 5 (total_syntheses
    == CAPABILITY_CONFIDENCE_THRESHOLD == 5) the bonus must equal exactly 0.0
    (full maturity). Validates the live decay path through the full
    cycle-artifact -> capability_effectiveness_ledger -> planner pipeline.
    """
    import json as _json
    from planner_runtime import (
        _compute_capability_exploration_adjustment,
        _compute_priority_breakdown,
        load_capability_effectiveness_ledger,
        CAPABILITY_CONFIDENCE_THRESHOLD,
        CAPABILITY_EXPLORATION_WEIGHT,
    )

    evaluation = {"risk_level": "moderate_risk", "reasons": []}

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
                                            "artifact_kind": "mcp_server",
                                            "capability": "cap_x",
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
        }

    monkeypatch.setattr(_pipeline, "build_capability_artifact", _fake_builder)

    # Blank ledger: no prior history for cap_x.
    capability_ledger = tmp_path / "capability_effectiveness_ledger.json"
    capability_ledger.write_text(_json.dumps({"capabilities": {}}), encoding="utf-8")

    action_cap_x = {
        "action_type": "build_capability_artifact",
        "priority": 10.0,
        "action_id": "aid-x",
        "args": {"capability": "cap_x"},
    }

    # Maximum theoretical bonus before any history exists (total=0 row absent -> 0.0
    # from _compute_capability_exploration_adjustment, but the theoretical max if a
    # row with total=0 existed would be CAPABILITY_EXPLORATION_WEIGHT). We use
    # CAPABILITY_EXPLORATION_WEIGHT as the starting sentinel because cycle 1
    # (total=1) must produce a strictly smaller value than that maximum.
    prev_exploration_adj = CAPABILITY_EXPLORATION_WEIGHT  # 0.005

    for cycle_idx in range(1, 6):  # 5 cycles: totals become 1, 2, 3, 4, 5
        _mod.run_autonomous_factory_cycle(
            portfolio_state="portfolio_state.json",
            capability_ledger=str(capability_ledger),
            capability_ledger_output=str(capability_ledger),
            policy="planner_policy.json",
            top_k=3,
            output=str(tmp_path / f"cycle{cycle_idx}.json"),
        )

        loaded_ledger = load_capability_effectiveness_ledger(str(capability_ledger))
        caps = loaded_ledger.get("capabilities", {})

        assert caps["cap_x"]["total_syntheses"] == cycle_idx, (
            f"cycle {cycle_idx}: expected total_syntheses={cycle_idx}, "
            f"got {caps['cap_x']['total_syntheses']}"
        )
        assert caps["cap_x"]["successful_syntheses"] == cycle_idx, (
            f"cycle {cycle_idx}: expected successful_syntheses={cycle_idx}, "
            f"got {caps['cap_x']['successful_syntheses']}"
        )

        exploration_adj = _compute_capability_exploration_adjustment(
            action_cap_x, loaded_ledger
        )

        assert exploration_adj < prev_exploration_adj, (
            f"cycle {cycle_idx}: exploration bonus {exploration_adj} must be strictly "
            f"less than previous {prev_exploration_adj}"
        )
        prev_exploration_adj = exploration_adj

        if cycle_idx == 5:
            assert exploration_adj == pytest.approx(0.0), (
                f"cycle {cycle_idx}: at total_syntheses == CAPABILITY_CONFIDENCE_THRESHOLD "
                f"({int(CAPABILITY_CONFIDENCE_THRESHOLD)}), exploration bonus must be 0.0; "
                f"got {exploration_adj}"
            )
            # At maturity the capability exploration component is 0.0; the breakdown's
            # exploration_component must equal the baseline (blank capability ledger),
            # which carries only the action-level exploration portion.
            bd = _compute_priority_breakdown(action_cap_x, {}, {}, {}, loaded_ledger)
            bd_baseline = _compute_priority_breakdown(
                action_cap_x, {}, {}, {}, {"capabilities": {}}
            )
            assert bd.exploration_component == pytest.approx(
                bd_baseline.exploration_component
            ), (
                f"at maturity, capability exploration must be zero; "
                f"bd.exploration_component={bd.exploration_component}, "
                f"baseline={bd_baseline.exploration_component}"
            )


def test_maturity_state_ranking_exploration_removed_reliability_dominates(
    tmp_path, monkeypatch
):
    """cap_x is pre-seeded at full maturity (total=5, success=5, exploration=0.0).
    cap_z starts blank. Phase 1: three cap_z success cycles accumulate
    total=3; cap_z gains a positive exploration bonus (+0.002) but cap_x
    reliability (+0.035714) still dominates — cap_x ranks above. Phase 2: one
    more cap_z success cycle (total=4); cap_z exploration decays to +0.001
    (strictly less than Phase 1); cap_x still ranks above. Validates that
    once exploration is removed at maturity, reliability alone sustains rank
    supremacy against a capability still in its exploration window.
    """
    import json as _json
    from planner_runtime import (
        _apply_learning_adjustments,
        _compute_capability_exploration_adjustment,
        _compute_capability_reliability_adjustment,
        _compute_priority_breakdown,
        load_capability_effectiveness_ledger,
        CAPABILITY_CONFIDENCE_THRESHOLD,
        CAPABILITY_EXPLORATION_WEIGHT,
    )

    evaluation = {"risk_level": "moderate_risk", "reasons": []}
    state = {"capability": "cap_z", "status": "ok"}

    def _dynamic_governed_result(args):
        return {
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
                                                "artifact_kind": "mcp_server",
                                                "capability": state["capability"],
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

    def _dynamic_builder(*, artifact_kind, capability, **kwargs):
        return {
            "status": state["status"],
            "artifact_kind": artifact_kind,
            "capability": capability,
        }

    monkeypatch.setattr(_mod, "evaluate_planner_config", lambda **kwargs: evaluation)
    monkeypatch.setattr(_mod, "run_governed_loop", _dynamic_governed_result)
    monkeypatch.setattr(_pipeline, "build_capability_artifact", _dynamic_builder)

    capability_ledger = tmp_path / "capability_effectiveness_ledger.json"
    pre_seed = {
        "capabilities": {
            "cap_x": {
                "capability": "cap_x",
                "total_syntheses": 5,
                "successful_syntheses": 5,
                "failed_syntheses": 0,
                "last_synthesis_status": "ok",
            }
        }
    }
    capability_ledger.write_text(_json.dumps(pre_seed), encoding="utf-8")

    action_cap_x = {
        "action_type": "build_capability_artifact",
        "priority": 10.0,
        "action_id": "aid-x",
        "args": {"capability": "cap_x"},
    }
    action_cap_z = {
        "action_type": "build_capability_artifact",
        "priority": 10.0,
        "action_id": "aid-z",
        "args": {"capability": "cap_z"},
    }

    # Baseline assertions (before any cycles)
    baseline_ledger = load_capability_effectiveness_ledger(str(capability_ledger))

    cap_x_exploration_baseline = _compute_capability_exploration_adjustment(action_cap_x, baseline_ledger)
    assert cap_x_exploration_baseline == pytest.approx(0.0), (
        f"baseline: cap_x at full maturity must have exploration=0.0; got {cap_x_exploration_baseline}"
    )

    cap_x_reliability_baseline = _compute_capability_reliability_adjustment(action_cap_x, baseline_ledger)
    assert cap_x_reliability_baseline > 0.0, (
        f"baseline: cap_x with all-success history must have positive reliability; got {cap_x_reliability_baseline}"
    )

    ranked_baseline = _apply_learning_adjustments(
        [action_cap_x, action_cap_z], {}, capability_ledger=baseline_ledger
    )
    assert ranked_baseline[0]["args"]["capability"] == "cap_x", (
        f"baseline: cap_x reliability must rank above blank cap_z; "
        f"got {[a['args']['capability'] for a in ranked_baseline]}"
    )

    # Phase 1: three successful cap_z cycles -> total=3, success=3
    state["capability"] = "cap_z"
    state["status"] = "ok"
    for cycle_idx in range(1, 4):
        _mod.run_autonomous_factory_cycle(
            portfolio_state="portfolio_state.json",
            capability_ledger=str(capability_ledger),
            capability_ledger_output=str(capability_ledger),
            policy="planner_policy.json",
            top_k=3,
            output=str(tmp_path / f"phase1_cycle{cycle_idx}.json"),
        )

    ledger_p1 = load_capability_effectiveness_ledger(str(capability_ledger))
    caps_p1 = ledger_p1.get("capabilities", {})

    assert caps_p1.get("cap_z", {}).get("total_syntheses") == 3, (
        f"phase 1: cap_z total_syntheses must be 3; got {caps_p1.get('cap_z')}"
    )
    assert caps_p1.get("cap_z", {}).get("successful_syntheses") == 3, (
        f"phase 1: cap_z successful_syntheses must be 3; got {caps_p1.get('cap_z')}"
    )

    # cap_x ledger unchanged (no cap_x cycles were run)
    assert caps_p1.get("cap_x", {}).get("total_syntheses") == 5, (
        f"phase 1: cap_x total_syntheses must be unchanged at 5; got {caps_p1.get('cap_x')}"
    )

    cap_z_exploration_p1 = _compute_capability_exploration_adjustment(action_cap_z, ledger_p1)
    assert cap_z_exploration_p1 > 0.0, (
        f"phase 1: cap_z must have positive exploration bonus at total=3; got {cap_z_exploration_p1}"
    )

    cap_x_exploration_p1 = _compute_capability_exploration_adjustment(action_cap_x, ledger_p1)
    assert cap_x_exploration_p1 == pytest.approx(0.0), (
        f"phase 1: cap_x exploration must remain 0.0 at full maturity; got {cap_x_exploration_p1}"
    )

    ranked_p1 = _apply_learning_adjustments(
        [action_cap_x, action_cap_z], {}, capability_ledger=ledger_p1
    )
    assert ranked_p1[0]["args"]["capability"] == "cap_x", (
        f"phase 1: cap_x reliability must dominate cap_z exploration+reliability; "
        f"got {[a['args']['capability'] for a in ranked_p1]}"
    )

    bd_x_p1 = _compute_priority_breakdown(action_cap_x, {}, {}, {}, ledger_p1)
    bd_z_p1 = _compute_priority_breakdown(action_cap_z, {}, {}, {}, ledger_p1)
    assert bd_x_p1.final_priority > bd_z_p1.final_priority, (
        f"phase 1: cap_x final_priority ({bd_x_p1.final_priority:.6f}) must exceed "
        f"cap_z final_priority ({bd_z_p1.final_priority:.6f})"
    )

    # Phase 2: one more successful cap_z cycle -> total=4, success=4
    _mod.run_autonomous_factory_cycle(
        portfolio_state="portfolio_state.json",
        capability_ledger=str(capability_ledger),
        capability_ledger_output=str(capability_ledger),
        policy="planner_policy.json",
        top_k=3,
        output=str(tmp_path / "phase2_cycle1.json"),
    )

    ledger_p2 = load_capability_effectiveness_ledger(str(capability_ledger))
    caps_p2 = ledger_p2.get("capabilities", {})

    assert caps_p2.get("cap_z", {}).get("total_syntheses") == 4, (
        f"phase 2: cap_z total_syntheses must be 4; got {caps_p2.get('cap_z')}"
    )

    cap_z_exploration_p2 = _compute_capability_exploration_adjustment(action_cap_z, ledger_p2)
    assert cap_z_exploration_p2 > 0.0, (
        f"phase 2: cap_z must still have positive exploration at total=4; got {cap_z_exploration_p2}"
    )
    assert cap_z_exploration_p2 < cap_z_exploration_p1, (
        f"phase 2: cap_z exploration must decay from phase 1 ({cap_z_exploration_p1}) "
        f"to phase 2 ({cap_z_exploration_p2})"
    )

    cap_x_exploration_p2 = _compute_capability_exploration_adjustment(action_cap_x, ledger_p2)
    assert cap_x_exploration_p2 == pytest.approx(0.0), (
        f"phase 2: cap_x exploration must remain 0.0; got {cap_x_exploration_p2}"
    )

    ranked_p2 = _apply_learning_adjustments(
        [action_cap_x, action_cap_z], {}, capability_ledger=ledger_p2
    )
    assert ranked_p2[0]["args"]["capability"] == "cap_x", (
        f"phase 2: cap_x reliability must still dominate over cap_z; "
        f"got {[a['args']['capability'] for a in ranked_p2]}"
    )

    bd_x_p2 = _compute_priority_breakdown(action_cap_x, {}, {}, {}, ledger_p2)
    bd_z_p2 = _compute_priority_breakdown(action_cap_z, {}, {}, {}, ledger_p2)
    assert bd_x_p2.final_priority > bd_z_p2.final_priority, (
        f"phase 2: cap_x final_priority ({bd_x_p2.final_priority:.6f}) must still exceed "
        f"cap_z final_priority ({bd_z_p2.final_priority:.6f})"
    )


def test_mixed_signal_convergence_reliability_approaches_neutral(tmp_path, monkeypatch):
    """Validates learning-loop equilibrium under interleaved success/failure signals.

    A single capability (cap_x) receives 6 alternating synthesis outcomes:
    ok / failed / ok / failed / ok / failed → total=6, success=3, failed=3.

    At each cycle the reliability adjustment is computed via the live cycle path:
        run_autonomous_factory_cycle → capability_effectiveness_ledger → planner scoring

    Expected per-cycle sign pattern (Laplace smoothing, no evolution penalty):
        cycle 1 (ok):     total=1, success=1, success_rate=2/3,   confidence=0.2 → adj > 0
        cycle 2 (fail):   total=2, success=1, success_rate=2/4,   confidence=0.4 → adj == 0
        cycle 3 (ok):     total=3, success=2, success_rate=3/5,   confidence=0.6 → adj > 0
        cycle 4 (fail):   total=4, success=2, success_rate=3/6,   confidence=0.8 → adj == 0
        cycle 5 (ok):     total=5, success=3, success_rate=4/7,   confidence=1.0 → adj > 0
        cycle 6 (fail):   total=6, success=3, success_rate=4/8,   confidence=1.0 → adj == 0.0 exact

    At cycle 6: Laplace rate = (3+1)/(6+2) = 4/8 = 0.5 exactly.
    reliability_adj = 1.0 * (0.5 - 0.5) * 0.10 = 0.0.
    Confirms the system reaches neutral equilibrium — no compounding bias.
    """
    import json as _json
    from planner_runtime import (
        _compute_capability_exploration_adjustment,
        _compute_capability_reliability_adjustment,
        _compute_priority_breakdown,
        load_capability_effectiveness_ledger,
        CAPABILITY_CONFIDENCE_THRESHOLD,
    )

    evaluation = {"risk_level": "moderate_risk", "reasons": []}
    state = {"capability": "cap_x", "status": "ok"}

    def _dynamic_governed_result(args):
        return {
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
                                                "artifact_kind": "mcp_server",
                                                "capability": state["capability"],
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

    def _dynamic_builder(*, artifact_kind, capability, **kwargs):
        return {
            "status": state["status"],
            "artifact_kind": artifact_kind,
            "capability": capability,
        }

    monkeypatch.setattr(_mod, "evaluate_planner_config", lambda **kwargs: evaluation)
    monkeypatch.setattr(_mod, "run_governed_loop", _dynamic_governed_result)
    monkeypatch.setattr(_pipeline, "build_capability_artifact", _dynamic_builder)

    capability_ledger = tmp_path / "capability_effectiveness_ledger.json"
    capability_ledger.write_text(_json.dumps({"capabilities": {}}), encoding="utf-8")

    action_cap_x = {
        "action_type": "build_capability_artifact",
        "priority": 10.0,
        "action_id": "aid-x",
        "args": {"capability": "cap_x"},
    }

    statuses = ["ok", "failed", "ok", "failed", "ok", "failed"]
    reliability_adjs = []

    for cycle_idx, status in enumerate(statuses, start=1):
        state["status"] = status
        _mod.run_autonomous_factory_cycle(
            portfolio_state="portfolio_state.json",
            capability_ledger=str(capability_ledger),
            capability_ledger_output=str(capability_ledger),
            policy="planner_policy.json",
            top_k=3,
            output=str(tmp_path / f"cycle{cycle_idx}.json"),
        )

        ledger = load_capability_effectiveness_ledger(str(capability_ledger))
        caps = ledger.get("capabilities", {})
        cap_x_row = caps.get("cap_x", {})
        total = cap_x_row.get("total_syntheses", 0)
        success = cap_x_row.get("successful_syntheses", 0)

        rel_adj = _compute_capability_reliability_adjustment(action_cap_x, ledger)
        reliability_adjs.append(rel_adj)

        assert total == cycle_idx, (
            f"cycle {cycle_idx}: total_syntheses must be {cycle_idx}; got {total}"
        )
        assert success == (cycle_idx + 1) // 2, (
            f"cycle {cycle_idx}: successful_syntheses must be {(cycle_idx + 1) // 2}; got {success}"
        )

        # Per-cycle sign assertion: odd cycles end with success > failure → positive adj;
        # even cycles end with equal success/failure → Laplace gives exact 0.5 → adj == 0.
        if cycle_idx % 2 == 1:
            assert rel_adj > 0.0, (
                f"cycle {cycle_idx} (ok): reliability_adj must be positive; got {rel_adj}"
            )
        else:
            assert rel_adj == pytest.approx(0.0), (
                f"cycle {cycle_idx} (fail): reliability_adj must be 0.0 at equal success/failure; "
                f"got {rel_adj}"
            )

    # --- Terminal assertions at cycle 6 ---
    ledger_c6 = load_capability_effectiveness_ledger(str(capability_ledger))
    caps_c6 = ledger_c6.get("capabilities", {})

    assert caps_c6.get("cap_x", {}).get("total_syntheses") == 6, (
        f"terminal: total_syntheses must be 6; got {caps_c6.get('cap_x')}"
    )
    assert caps_c6.get("cap_x", {}).get("successful_syntheses") == 3, (
        f"terminal: successful_syntheses must be 3; got {caps_c6.get('cap_x')}"
    )

    terminal_rel_adj = reliability_adjs[-1]
    assert terminal_rel_adj == pytest.approx(0.0), (
        f"terminal: reliability_adj must be exactly 0.0 at neutral equilibrium "
        f"(total=6, success=3); got {terminal_rel_adj}"
    )

    terminal_exp_adj = _compute_capability_exploration_adjustment(action_cap_x, ledger_c6)
    assert terminal_exp_adj == pytest.approx(0.0), (
        f"terminal: exploration_adj must be 0.0 at full maturity (total=6 >= threshold=5); "
        f"got {terminal_exp_adj}"
    )

    # Confirm no compounding bias: final_priority with full history equals
    # final_priority against blank ledger within float tolerance.
    blank_ledger = {"capabilities": {}}
    bd_blank = _compute_priority_breakdown(action_cap_x, {}, {}, {}, blank_ledger)
    bd_c6 = _compute_priority_breakdown(action_cap_x, {}, {}, {}, ledger_c6)
    assert bd_c6.final_priority == pytest.approx(bd_blank.final_priority), (
        f"terminal: final_priority with neutral history ({bd_c6.final_priority:.8f}) must equal "
        f"final_priority with blank ledger ({bd_blank.final_priority:.8f}) — no compounding bias"
    )


def test_post_maturity_rank_stability_additional_cycles(tmp_path, monkeypatch):
    """Validates that a capability at full maturity sustains stable ranking
    across N>1 additional success cycles with no unbounded compounding.

    cap_x is pre-seeded at full maturity (total=5, success=5). Three additional
    success cycles are run via the live run_autonomous_factory_cycle path.

    Expected behavior (Laplace smoothing, confidence clamped at 1.0):
        pre-seed:  total=5, success=5  → reliability_adj ≈ 0.035714 (baseline)
        cycle 1:   total=6, success=6  → reliability_adj = 0.037500  (> baseline)
        cycle 2:   total=7, success=7  → reliability_adj ≈ 0.038889  (> cycle 1)
        cycle 3:   total=8, success=8  → reliability_adj = 0.040000  (> cycle 2)

    Convergence: monotonically increasing toward asymptote 0.050 (never reached).
    Exploration bonus stays exactly 0.0 at all post-maturity checkpoints.
    Rank over blank-slate competitor is sustained at every checkpoint.
    """
    import json as _json
    from planner_runtime import (
        _apply_learning_adjustments,
        _compute_capability_exploration_adjustment,
        _compute_capability_reliability_adjustment,
        load_capability_effectiveness_ledger,
    )

    evaluation = {"risk_level": "moderate_risk", "reasons": []}
    state = {"capability": "cap_x", "status": "ok"}

    def _dynamic_governed_result(args):
        return {
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
                                                "artifact_kind": "mcp_server",
                                                "capability": state["capability"],
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

    def _dynamic_builder(*, artifact_kind, capability, **kwargs):
        return {
            "status": state["status"],
            "artifact_kind": artifact_kind,
            "capability": capability,
        }

    monkeypatch.setattr(_mod, "evaluate_planner_config", lambda **kwargs: evaluation)
    monkeypatch.setattr(_mod, "run_governed_loop", _dynamic_governed_result)
    monkeypatch.setattr(_pipeline, "build_capability_artifact", _dynamic_builder)

    capability_ledger = tmp_path / "capability_effectiveness_ledger.json"
    pre_seed = {
        "capabilities": {
            "cap_x": {
                "capability": "cap_x",
                "total_syntheses": 5,
                "successful_syntheses": 5,
                "failed_syntheses": 0,
                "last_synthesis_status": "ok",
            }
        }
    }
    capability_ledger.write_text(_json.dumps(pre_seed), encoding="utf-8")

    action_cap_x = {
        "action_type": "build_capability_artifact",
        "priority": 10.0,
        "action_id": "aid-x",
        "args": {"capability": "cap_x"},
    }
    action_cap_z = {
        "action_type": "build_capability_artifact",
        "priority": 10.0,
        "action_id": "aid-z",
        "args": {"capability": "cap_z"},
    }

    # Compute pre-seed baseline reliability before any additional cycles
    baseline_ledger = load_capability_effectiveness_ledger(str(capability_ledger))
    pre_seed_reliability = _compute_capability_reliability_adjustment(
        action_cap_x, baseline_ledger
    )
    assert pre_seed_reliability > 0.0, (
        f"pre-seed: cap_x reliability must be positive at total=5, success=5; "
        f"got {pre_seed_reliability}"
    )
    assert _compute_capability_exploration_adjustment(action_cap_x, baseline_ledger) == pytest.approx(0.0), (
        "pre-seed: exploration bonus must be 0.0 at full maturity (total=5 >= threshold=5)"
    )

    # Run 3 additional success cycles for cap_x
    reliability_adjs = []
    for cycle_idx in range(1, 4):
        _mod.run_autonomous_factory_cycle(
            portfolio_state="portfolio_state.json",
            capability_ledger=str(capability_ledger),
            capability_ledger_output=str(capability_ledger),
            policy="planner_policy.json",
            top_k=3,
            output=str(tmp_path / f"cycle{cycle_idx}.json"),
        )

        ledger = load_capability_effectiveness_ledger(str(capability_ledger))
        caps = ledger.get("capabilities", {})
        cap_x_row = caps.get("cap_x", {})
        total = cap_x_row.get("total_syntheses", 0)
        success = cap_x_row.get("successful_syntheses", 0)

        rel_adj = _compute_capability_reliability_adjustment(action_cap_x, ledger)
        exp_adj = _compute_capability_exploration_adjustment(action_cap_x, ledger)
        reliability_adjs.append(rel_adj)

        assert total == 5 + cycle_idx, (
            f"cycle {cycle_idx}: total_syntheses must be {5 + cycle_idx}; got {total}"
        )
        assert success == 5 + cycle_idx, (
            f"cycle {cycle_idx}: successful_syntheses must be {5 + cycle_idx}; got {success}"
        )

        # Exploration stays at 0.0 post-maturity (primary stability claim)
        assert exp_adj == pytest.approx(0.0), (
            f"cycle {cycle_idx}: exploration_adj must remain 0.0 post-maturity; got {exp_adj}"
        )

        # Reliability grows above pre-seed baseline (positive signal preserved)
        assert rel_adj > pre_seed_reliability, (
            f"cycle {cycle_idx}: reliability_adj ({rel_adj:.8f}) must exceed pre-seed "
            f"baseline ({pre_seed_reliability:.8f})"
        )

        # Reliability stays below asymptote ceiling 0.050 (no unbounded compounding)
        assert rel_adj < 0.050, (
            f"cycle {cycle_idx}: reliability_adj ({rel_adj:.8f}) must stay below "
            f"asymptote ceiling 0.050"
        )

        # Rank over blank-slate cap_z is sustained
        ranked = _apply_learning_adjustments(
            [action_cap_x, action_cap_z], {}, capability_ledger=ledger
        )
        assert ranked[0]["args"]["capability"] == "cap_x", (
            f"cycle {cycle_idx}: cap_x must rank above blank-slate cap_z; "
            f"got {[a['args']['capability'] for a in ranked]}"
        )

    # --- Terminal assertions ---
    ledger_final = load_capability_effectiveness_ledger(str(capability_ledger))
    caps_final = ledger_final.get("capabilities", {})

    assert caps_final.get("cap_x", {}).get("total_syntheses") == 8, (
        f"terminal: total_syntheses must be 8 (pre-seed 5 + 3 cycles); "
        f"got {caps_final.get('cap_x')}"
    )
    assert caps_final.get("cap_x", {}).get("successful_syntheses") == 8, (
        f"terminal: successful_syntheses must be 8; got {caps_final.get('cap_x')}"
    )

    # Strict monotonicity: each post-maturity cycle nudges reliability upward
    assert reliability_adjs[1] > reliability_adjs[0], (
        f"terminal: reliability_adj must increase from cycle 1 ({reliability_adjs[0]:.8f}) "
        f"to cycle 2 ({reliability_adjs[1]:.8f})"
    )
    assert reliability_adjs[2] > reliability_adjs[1], (
        f"terminal: reliability_adj must increase from cycle 2 ({reliability_adjs[1]:.8f}) "
        f"to cycle 3 ({reliability_adjs[2]:.8f})"
    )
    assert reliability_adjs[0] > pre_seed_reliability, (
        f"terminal: cycle 1 reliability_adj ({reliability_adjs[0]:.8f}) must exceed "
        f"pre-seed baseline ({pre_seed_reliability:.8f})"
    )


def test_failure_deprioritization_persists_after_single_recovery_cycle(tmp_path, monkeypatch):
    """Validates that failure-induced deprioritization persists after a single recovery.

    cap_x is pre-seeded with 2 failures (total=2, success=0). One additional
    failure cycle is run (Phase 1: total=3, success=0), establishing a clear
    negative reliability adjustment. One recovery success cycle is then run
    (Phase 2: total=4, success=1).

    Expected values (Laplace smoothing, no evolution penalty):
        Phase 1 end: total=3, success=0 → success_rate=1/5, confidence=0.6
                     reliability_adj = 0.6 * (0.2 - 0.5) * 0.10 = -0.018000
        Phase 2 end: total=4, success=1 → success_rate=2/6, confidence=0.8
                     reliability_adj = 0.8 * (0.333... - 0.5) * 0.10 = -0.013333

    After Phase 2 the adjustment is still strictly negative: recovery is
    directionally correct but the system resists premature promotion.
    cap_x must not rank above blank-slate cap_z at either checkpoint.
    """
    import json as _json
    from planner_runtime import (
        _apply_learning_adjustments,
        _compute_capability_reliability_adjustment,
        load_capability_effectiveness_ledger,
    )

    evaluation = {"risk_level": "moderate_risk", "reasons": []}
    state = {"capability": "cap_x", "status": "failed"}

    def _dynamic_governed_result(args):
        return {
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
                                                "artifact_kind": "mcp_server",
                                                "capability": state["capability"],
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

    def _dynamic_builder(*, artifact_kind, capability, **kwargs):
        return {
            "status": state["status"],
            "artifact_kind": artifact_kind,
            "capability": capability,
        }

    monkeypatch.setattr(_mod, "evaluate_planner_config", lambda **kwargs: evaluation)
    monkeypatch.setattr(_mod, "run_governed_loop", _dynamic_governed_result)
    monkeypatch.setattr(_pipeline, "build_capability_artifact", _dynamic_builder)

    capability_ledger = tmp_path / "capability_effectiveness_ledger.json"
    pre_seed = {
        "capabilities": {
            "cap_x": {
                "capability": "cap_x",
                "total_syntheses": 2,
                "successful_syntheses": 0,
                "failed_syntheses": 2,
                "last_synthesis_status": "failed",
            }
        }
    }
    capability_ledger.write_text(_json.dumps(pre_seed), encoding="utf-8")

    action_cap_x = {
        "action_type": "build_capability_artifact",
        "priority": 10.0,
        "action_id": "aid-x",
        "args": {"capability": "cap_x"},
    }
    action_cap_z = {
        "action_type": "build_capability_artifact",
        "priority": 10.0,
        "action_id": "aid-z",
        "args": {"capability": "cap_z"},
    }

    # --- Phase 1: one additional failure cycle → total=3, success=0 ---
    state["status"] = "failed"
    _mod.run_autonomous_factory_cycle(
        portfolio_state="portfolio_state.json",
        capability_ledger=str(capability_ledger),
        capability_ledger_output=str(capability_ledger),
        policy="planner_policy.json",
        top_k=3,
        output=str(tmp_path / "phase1.json"),
    )

    ledger_p1 = load_capability_effectiveness_ledger(str(capability_ledger))
    caps_p1 = ledger_p1.get("capabilities", {})

    assert caps_p1.get("cap_x", {}).get("total_syntheses") == 3, (
        f"phase 1: total_syntheses must be 3; got {caps_p1.get('cap_x')}"
    )
    assert caps_p1.get("cap_x", {}).get("successful_syntheses") == 0, (
        f"phase 1: successful_syntheses must be 0; got {caps_p1.get('cap_x')}"
    )

    phase1_adj = _compute_capability_reliability_adjustment(action_cap_x, ledger_p1)
    assert phase1_adj < 0.0, (
        f"phase 1: reliability_adj must be negative after 3 failures; got {phase1_adj}"
    )

    ranked_p1 = _apply_learning_adjustments(
        [action_cap_x, action_cap_z], {}, capability_ledger=ledger_p1
    )
    assert ranked_p1[-1]["args"]["capability"] == "cap_x", (
        f"phase 1: cap_x must rank below blank-slate cap_z; "
        f"got {[a['args']['capability'] for a in ranked_p1]}"
    )

    # --- Phase 2: one recovery success cycle → total=4, success=1 ---
    state["status"] = "ok"
    _mod.run_autonomous_factory_cycle(
        portfolio_state="portfolio_state.json",
        capability_ledger=str(capability_ledger),
        capability_ledger_output=str(capability_ledger),
        policy="planner_policy.json",
        top_k=3,
        output=str(tmp_path / "phase2.json"),
    )

    ledger_p2 = load_capability_effectiveness_ledger(str(capability_ledger))
    caps_p2 = ledger_p2.get("capabilities", {})

    assert caps_p2.get("cap_x", {}).get("total_syntheses") == 4, (
        f"phase 2: total_syntheses must be 4; got {caps_p2.get('cap_x')}"
    )
    assert caps_p2.get("cap_x", {}).get("successful_syntheses") == 1, (
        f"phase 2: successful_syntheses must be 1; got {caps_p2.get('cap_x')}"
    )

    phase2_adj = _compute_capability_reliability_adjustment(action_cap_x, ledger_p2)

    # Primary: penalty persists — single recovery does not restore neutral rank
    assert phase2_adj < 0.0, (
        f"phase 2: reliability_adj must remain negative after single recovery; "
        f"got {phase2_adj} (penalty must persist)"
    )

    # Secondary: direction of recovery is correct
    assert phase2_adj > phase1_adj, (
        f"phase 2: reliability_adj ({phase2_adj:.8f}) must be less negative than "
        f"phase 1 ({phase1_adj:.8f}) — recovery direction must be correct"
    )

    # Rank not restored: cap_x still ranks below blank-slate cap_z
    ranked_p2 = _apply_learning_adjustments(
        [action_cap_x, action_cap_z], {}, capability_ledger=ledger_p2
    )
    assert ranked_p2[-1]["args"]["capability"] == "cap_x", (
        f"phase 2: cap_x must still rank below blank-slate cap_z after single recovery; "
        f"got {[a['args']['capability'] for a in ranked_p2]}"
    )


def test_multi_cycle_recovery_converges_to_neutral_then_positive(tmp_path, monkeypatch):
    """Validates multi-cycle recovery convergence arc from negative to neutral to positive.

    cap_x is pre-seeded with total=2, success=0 (2 prior failures).

    Phase 1 (1 failure cycle): total=3, success=0.
        Expected: strictly negative reliability adjustment.

    Phase 2 (5 consecutive recovery success cycles):
        R1: total=4, success=1 → success_rate=2/6, confidence=0.8 → adj < 0 (still negative)
        R2: total=5, success=2 → success_rate=3/7, confidence ≈ 0.857 → adj < 0 (still negative)
        R3: total=6, success=3 → success_rate=4/8=0.5 exact (Laplace), confidence ≈ 0.889
            → adj == 0.0 exactly (neutral crossover)
        R4: total=7, success=4 → success_rate=5/9 > 0.5 → adj > 0 (positive)
        R5: total=8, success=5 → success_rate=6/10=0.6 → adj > 0 (positive, increasing)

    Recovery adjustments must be strictly monotonically increasing across R1..R5.
    """
    import json as _json
    from planner_runtime import (
        _compute_capability_reliability_adjustment,
        load_capability_effectiveness_ledger,
    )

    evaluation = {"risk_level": "moderate_risk", "reasons": []}
    state = {"capability": "cap_x", "status": "failed"}

    def _dynamic_governed_result(args):
        return {
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
                                                "artifact_kind": "mcp_server",
                                                "capability": state["capability"],
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

    def _dynamic_builder(*, artifact_kind, capability, **kwargs):
        return {
            "status": state["status"],
            "artifact_kind": artifact_kind,
            "capability": capability,
        }

    monkeypatch.setattr(_mod, "evaluate_planner_config", lambda **kwargs: evaluation)
    monkeypatch.setattr(_mod, "run_governed_loop", _dynamic_governed_result)
    monkeypatch.setattr(_pipeline, "build_capability_artifact", _dynamic_builder)

    capability_ledger = tmp_path / "capability_effectiveness_ledger.json"
    pre_seed = {
        "capabilities": {
            "cap_x": {
                "total_syntheses": 2,
                "successful_syntheses": 0,
                "failed_syntheses": 2,
            }
        }
    }
    capability_ledger.write_text(_json.dumps(pre_seed), encoding="utf-8")

    action_cap_x = {
        "action_type": "build_capability_artifact",
        "priority": 10.0,
        "action_id": "aid-x",
        "args": {"capability": "cap_x"},
    }

    # --- Phase 1: one failure cycle → total=3, success=0 ---
    state["status"] = "failed"
    _mod.run_autonomous_factory_cycle(
        portfolio_state="portfolio_state.json",
        capability_ledger=str(capability_ledger),
        capability_ledger_output=str(capability_ledger),
        policy="planner_policy.json",
        top_k=3,
        output=str(tmp_path / "phase1.json"),
    )

    ledger_p1 = load_capability_effectiveness_ledger(str(capability_ledger))
    caps = ledger_p1.get("capabilities", {})

    assert caps.get("cap_x", {}).get("total_syntheses") == 3, (
        f"phase 1: total_syntheses must be 3; got {caps.get('cap_x')}"
    )
    assert caps.get("cap_x", {}).get("successful_syntheses") == 0, (
        f"phase 1: successful_syntheses must be 0; got {caps.get('cap_x')}"
    )

    phase1_adj = _compute_capability_reliability_adjustment(action_cap_x, ledger_p1)
    assert phase1_adj < 0.0, (
        f"phase 1: reliability_adj must be negative after 3 failures (0 successes); "
        f"got {phase1_adj}"
    )

    # --- Phase 2: 5 consecutive recovery success cycles ---
    state["status"] = "ok"
    recovery_adjs = []

    for cycle_idx in range(1, 6):
        _mod.run_autonomous_factory_cycle(
            portfolio_state="portfolio_state.json",
            capability_ledger=str(capability_ledger),
            capability_ledger_output=str(capability_ledger),
            policy="planner_policy.json",
            top_k=3,
            output=str(tmp_path / f"recovery{cycle_idx}.json"),
        )

        ledger_r = load_capability_effectiveness_ledger(str(capability_ledger))
        caps = ledger_r.get("capabilities", {})

        assert caps.get("cap_x", {}).get("total_syntheses") == 3 + cycle_idx, (
            f"R{cycle_idx}: total_syntheses must be {3 + cycle_idx}; "
            f"got {caps.get('cap_x')}"
        )
        assert caps.get("cap_x", {}).get("successful_syntheses") == cycle_idx, (
            f"R{cycle_idx}: successful_syntheses must be {cycle_idx}; "
            f"got {caps.get('cap_x')}"
        )

        adj = _compute_capability_reliability_adjustment(action_cap_x, ledger_r)
        recovery_adjs.append(adj)

    import pytest as _pytest

    # R1 starts moving toward phase1_adj (monotonic improvement begins)
    assert recovery_adjs[0] > phase1_adj, (
        f"R1 adj ({recovery_adjs[0]:.8f}) must be greater than phase1_adj "
        f"({phase1_adj:.8f}) — recovery must move in positive direction"
    )

    # R1, R2: still strictly negative
    assert recovery_adjs[0] < 0.0, (
        f"R1 adj ({recovery_adjs[0]:.8f}) must still be negative after 1 recovery"
    )
    assert recovery_adjs[1] < 0.0, (
        f"R2 adj ({recovery_adjs[1]:.8f}) must still be negative after 2 recoveries"
    )

    # R3: exact Laplace neutral (success_rate = 4/8 = 0.5 → adj == 0.0)
    assert recovery_adjs[2] == _pytest.approx(0.0), (
        f"R3 adj ({recovery_adjs[2]:.8f}) must be exactly 0.0 (Laplace 4/8=0.5 neutral); "
        f"got {recovery_adjs[2]}"
    )

    # R4, R5: strictly positive
    assert recovery_adjs[3] > 0.0, (
        f"R4 adj ({recovery_adjs[3]:.8f}) must be positive after 4 recoveries"
    )
    assert recovery_adjs[4] > 0.0, (
        f"R5 adj ({recovery_adjs[4]:.8f}) must be positive after 5 recoveries"
    )

    # Strict monotonic increase throughout R1..R5
    assert all(recovery_adjs[i + 1] > recovery_adjs[i] for i in range(4)), (
        f"recovery adjustments must be strictly monotonically increasing across R1..R5; "
        f"got {[f'{a:.8f}' for a in recovery_adjs]}"
    )


def test_confidence_weighting_moderates_ranking_asymmetric_history():
    """Verify that confidence weighting moderates capability reliability ranking.

    cap_a: total_syntheses=8, successful=3, failed=5.
        confidence=1.0 (mature, >= maturity threshold), success_rate = (3+1)/(8+2) = 0.40.
        adj = -0.01000 (full-confidence negative signal; depth does not rescue poor reliability).

    cap_b: total_syntheses=2, successful=2, failed=0.
        confidence=0.4 (shallow, below maturity threshold), success_rate = (2+1)/(2+2) = 0.75.
        adj = +0.01000 (confidence-moderated but still positive).

    Key insight: confidence weighting means cap_b's smaller-magnitude positive signal (+0.01)
    exactly cancels cap_a's full-confidence negative signal (-0.01); cap_a's depth advantage
    does not rescue it from its poor reliability. Both start at equal base_priority=10.0;
    ranking is determined purely by the capability_reliability_component.
    """
    from planner_runtime import (
        _apply_learning_adjustments,
        _compute_capability_reliability_adjustment,
    )

    capability_ledger = {
        "capabilities": {
            "cap_a": {
                "total_syntheses": 8,
                "successful_syntheses": 3,
                "failed_syntheses": 5,
            },
            "cap_b": {
                "total_syntheses": 2,
                "successful_syntheses": 2,
                "failed_syntheses": 0,
            },
        }
    }

    action_cap_a = {
        "action_type": "build_capability_artifact",
        "priority": 10.0,
        "action_id": "aid-a",
        "args": {"capability": "cap_a"},
    }
    action_cap_b = {
        "action_type": "build_capability_artifact",
        "priority": 10.0,
        "action_id": "aid-b",
        "args": {"capability": "cap_b"},
    }

    # Step 1: verify individual adjustments
    adj_a = _compute_capability_reliability_adjustment(action_cap_a, capability_ledger)
    adj_b = _compute_capability_reliability_adjustment(action_cap_b, capability_ledger)

    assert adj_a < 0.0
    assert adj_b > 0.0

    assert adj_a == pytest.approx(-0.01000), (
        f"cap_a adj: expected -0.01000, got {adj_a}"
    )
    assert adj_b == pytest.approx(+0.01000), (
        f"cap_b adj: expected +0.01000, got {adj_b}"
    )

    # Step 2: verify ranking — shallow-perfect cap_b must rank above deep-poor cap_a
    ranked = _apply_learning_adjustments(
        [action_cap_a, action_cap_b], {}, capability_ledger=capability_ledger
    )
    assert ranked[0]["args"]["capability"] == "cap_b", (
        f"shallow-perfect cap_b must rank first; got {[a['args']['capability'] for a in ranked]}"
    )
    assert ranked[1]["args"]["capability"] == "cap_a", (
        f"deep-poor cap_a must rank second; got {[a['args']['capability'] for a in ranked]}"
    )
