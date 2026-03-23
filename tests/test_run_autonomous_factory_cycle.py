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
