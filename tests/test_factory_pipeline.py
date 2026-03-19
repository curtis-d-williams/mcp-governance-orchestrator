# SPDX-License-Identifier: MIT
"""Regression tests for the governed capability factory pipeline."""

import json
import shutil
from pathlib import Path

import factory_pipeline as _mod


def test_run_factory_cycle_dispatches_generic_capability_builder(tmp_path, monkeypatch):
    calls = {}

    def fake_build_capability_artifact(*, artifact_kind, capability, **kwargs):
        calls["artifact_kind"] = artifact_kind
        calls["capability"] = capability
        calls["kwargs"] = kwargs
        return {
            "status": "ok",
            "artifact_kind": artifact_kind,
            "capability": capability,
            "generated_repo": "/tmp/generated_data_connector_snowflake",
        }

    monkeypatch.setattr(_mod, "build_capability_artifact", fake_build_capability_artifact)

    def fake_evaluate_planner_config(**kwargs):
        return {"risk_level": "low_risk"}

    def fake_run_mapping_repair_cycle(**kwargs):
        raise AssertionError("repair path should not run")

    def fake_run_governed_loop(args):
        return {
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
            }
        }

    output = tmp_path / "factory_cycle.json"

    artifact = _mod.run_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="ledger.json",
        policy="policy.json",
        top_k=3,
        output=str(output),
        evaluate_planner_config=fake_evaluate_planner_config,
        run_mapping_repair_cycle=fake_run_mapping_repair_cycle,
        run_governed_loop=fake_run_governed_loop,
    )

    assert calls == {
        "artifact_kind": "data_connector",
        "capability": "snowflake_data_access",
        "kwargs": {},
    }

    assert artifact["cycle_result"]["builder"] == {
        "status": "ok",
        "artifact_kind": "data_connector",
        "capability": "snowflake_data_access",
        "generated_repo": "/tmp/generated_data_connector_snowflake",
    }

    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted["cycle_result"]["builder"]["capability"] == "snowflake_data_access"


def test_run_factory_cycle_synthesizes_from_portfolio_capability_gaps(tmp_path, monkeypatch):
    calls = {}

    def fake_build_capability_artifact(*, artifact_kind, capability, **kwargs):
        calls["artifact_kind"] = artifact_kind
        calls["capability"] = capability
        calls["kwargs"] = kwargs
        return {
            "status": "ok",
            "artifact_kind": artifact_kind,
            "capability": capability,
            "generated_repo": "/tmp/generated_agent_adapter_slack",
        }

    monkeypatch.setattr(_mod, "build_capability_artifact", fake_build_capability_artifact)

    def fake_evaluate_planner_config(**kwargs):
        return {"risk_level": "low_risk"}

    def fake_run_mapping_repair_cycle(**kwargs):
        raise AssertionError("repair path should not run")

    def fake_run_governed_loop(args):
        return {
            "result": {
                "evaluation_summary": {
                    "runs": [
                        {
                            "selected_actions": [],
                            "selection_detail": {
                                "ranked_action_window": [],
                                "ranked_action_window_detail": [],
                            },
                        }
                    ]
                }
            }
        }

    portfolio_state = tmp_path / "portfolio_state.json"
    portfolio_state.write_text(
        json.dumps(
            {
                "capability_gaps": ["slack_workspace_access"],
            }
        ),
        encoding="utf-8",
    )

    output = tmp_path / "factory_cycle.json"

    artifact = _mod.run_factory_cycle(
        portfolio_state=str(portfolio_state),
        ledger="ledger.json",
        policy="policy.json",
        top_k=3,
        output=str(output),
        evaluate_planner_config=fake_evaluate_planner_config,
        run_mapping_repair_cycle=fake_run_mapping_repair_cycle,
        run_governed_loop=fake_run_governed_loop,
    )

    assert calls == {
        "artifact_kind": "agent_adapter",
        "capability": "slack_workspace_access",
        "kwargs": {},
    }

    assert artifact["cycle_result"]["builder"] == {
        "status": "ok",
        "artifact_kind": "agent_adapter",
        "capability": "slack_workspace_access",
        "generated_repo": "/tmp/generated_agent_adapter_slack",
    }


def test_run_factory_cycle_records_capability_effectiveness_for_planner_requested_build(tmp_path, monkeypatch):
    calls = {}

    def fake_build_capability_artifact(*, artifact_kind, capability, **kwargs):
        calls["artifact_kind"] = artifact_kind
        calls["capability"] = capability
        calls["kwargs"] = kwargs
        return {
            "status": "ok",
            "artifact_kind": artifact_kind,
            "capability": capability,
            "generated_repo": "/tmp/generated_data_connector_snowflake",
        }

    monkeypatch.setattr(_mod, "build_capability_artifact", fake_build_capability_artifact)

    def fake_evaluate_planner_config(**kwargs):
        return {"risk_level": "low_risk"}

    def fake_run_mapping_repair_cycle(**kwargs):
        raise AssertionError("repair path should not run")

    def fake_run_governed_loop(args):
        return {
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
            }
        }

    output = tmp_path / "factory_cycle.json"

    artifact = _mod.run_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="ledger.json",
        policy="policy.json",
        top_k=3,
        output=str(output),
        evaluate_planner_config=fake_evaluate_planner_config,
        run_mapping_repair_cycle=fake_run_mapping_repair_cycle,
        run_governed_loop=fake_run_governed_loop,
    )

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

    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted["capability_effectiveness_ledger"] == artifact["capability_effectiveness_ledger"]


def test_run_factory_cycle_records_capability_effectiveness_for_gap_synthesis(tmp_path, monkeypatch):
    calls = {}

    def fake_build_capability_artifact(*, artifact_kind, capability, **kwargs):
        calls["artifact_kind"] = artifact_kind
        calls["capability"] = capability
        calls["kwargs"] = kwargs
        return {
            "status": "ok",
            "artifact_kind": artifact_kind,
            "capability": capability,
            "generated_repo": "/tmp/generated_agent_adapter_slack",
        }

    monkeypatch.setattr(_mod, "build_capability_artifact", fake_build_capability_artifact)

    def fake_evaluate_planner_config(**kwargs):
        return {"risk_level": "low_risk"}

    def fake_run_mapping_repair_cycle(**kwargs):
        raise AssertionError("repair path should not run")

    def fake_run_governed_loop(args):
        return {
            "result": {
                "evaluation_summary": {
                    "runs": [
                        {
                            "selected_actions": [],
                            "selection_detail": {
                                "ranked_action_window": [],
                                "ranked_action_window_detail": [],
                            },
                        }
                    ]
                }
            }
        }

    portfolio_state = tmp_path / "portfolio_state.json"
    portfolio_state.write_text(
        json.dumps(
            {
                "capability_gaps": ["slack_workspace_access"],
            }
        ),
        encoding="utf-8",
    )

    output = tmp_path / "factory_cycle.json"

    artifact = _mod.run_factory_cycle(
        portfolio_state=str(portfolio_state),
        ledger="ledger.json",
        policy="policy.json",
        top_k=3,
        output=str(output),
        evaluate_planner_config=fake_evaluate_planner_config,
        run_mapping_repair_cycle=fake_run_mapping_repair_cycle,
        run_governed_loop=fake_run_governed_loop,
    )

    assert artifact["capability_effectiveness_ledger"] == {
        "capabilities": {
            "slack_workspace_access": {
                "artifact_kind": "agent_adapter",
                "failed_syntheses": 0,
                "last_synthesis_source": "portfolio_gap",
                "last_synthesis_status": "ok",
                "last_synthesis_used_evolution": False,
                "successful_evolved_syntheses": 0,
                "successful_syntheses": 1,
                "total_syntheses": 1,
            }
        }
    }

    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted["capability_effectiveness_ledger"] == artifact["capability_effectiveness_ledger"]


def test_run_factory_cycle_falls_back_to_portfolio_recommendation_build_request(tmp_path, monkeypatch):
    build_calls = []

    def fake_evaluate_planner_config(**kwargs):
        return {"risk_level": "high_risk", "reasons": []}

    def fake_run_mapping_repair_cycle(**kwargs):
        return {
            "status": "repair_unavailable",
            "repair_attempted": True,
            "repair_success": False,
            "repair_proposal": {"repair_needed": False},
            "baseline_evaluation": {"risk_level": "high_risk"},
            "repaired_evaluation": None,
            "override_artifact": {},
            "override_artifact_path": None,
            "inputs": kwargs,
        }

    def fake_run_governed_loop(args):
        raise AssertionError("governed loop should not run in repair_only path")

    def fake_build_capability_artifact(*, artifact_kind, capability, **kwargs):
        build_calls.append(
            {
                "artifact_kind": artifact_kind,
                "capability": capability,
                "kwargs": kwargs,
            }
        )
        return {
            "status": "ok",
            "artifact_kind": artifact_kind,
            "capability": capability,
            "generated_repo": "/tmp/generated_mcp_server_github",
            "tools": ["list_repositories", "get_repository", "create_issue"],
        }

    monkeypatch.setattr(_mod, "build_capability_artifact", fake_build_capability_artifact)

    portfolio_state = tmp_path / "portfolio_state.json"
    portfolio_state.write_text(
        json.dumps(
            {
                "portfolio_recommendations": [
                    {
                        "action_type": "build_capability_artifact",
                        "task_binding": {
                            "args": {
                                "artifact_kind": "mcp_server",
                                "capability": "github_repository_management",
                            }
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    output = tmp_path / "factory_cycle.json"

    artifact = _mod.run_factory_cycle(
        portfolio_state=str(portfolio_state),
        ledger="ledger.json",
        policy="policy.json",
        top_k=3,
        output=str(output),
        evaluate_planner_config=fake_evaluate_planner_config,
        run_mapping_repair_cycle=fake_run_mapping_repair_cycle,
        run_governed_loop=fake_run_governed_loop,
    )

    assert build_calls == [
        {
            "artifact_kind": "mcp_server",
            "capability": "github_repository_management",
            "kwargs": {},
        }
    ]
    assert artifact["cycle_result"]["builder"]["status"] == "ok"
    assert artifact["cycle_result"]["synthesis_event"]["source"] == "portfolio_gap"



def test_run_factory_cycle_records_reference_comparison_gap_for_real_generated_mcp_build(tmp_path, monkeypatch):
    generated = Path("generated_mcp_server_github")
    if generated.exists():
        shutil.rmtree(generated)

    calls = {}

    def fake_compare_mcp_servers(generated_path, reference_path, output_path=None):
        calls["compare"] = {
            "generated_path": generated_path,
            "reference_path": reference_path,
            "output_path": output_path,
        }
        server_text = (Path(generated_path) / "server.py").read_text(encoding="utf-8")
        get_repository_text = (Path(generated_path) / "tools" / "get_repository.py").read_text(encoding="utf-8")
        create_issue_text = (Path(generated_path) / "tools" / "create_issue.py").read_text(encoding="utf-8")

        assert '@mcp.tool()\ndef get_repository(repo: str):' in server_text
        assert '@mcp.tool()\ndef create_issue(repo: str, title: str, body: str):' in server_text
        assert 'def get_repository(repo):' in get_repository_text
        assert 'def create_issue(repo, title, body):' in create_issue_text

        return {
            "structure": {"generated_capability": "github_repository_management"},
            "tool_surface": {"coverage_ratio": 0.33, "missing_tools": ["create_issue"]},
            "capability_surface": {
                "coverage_ratio": 0.5,
                "missing_enabled": ["supports_dynamic_toolsets"],
            },
            "testability": {"coverage_ratio": 0.25},
        }

    def fake_derive_capability_gaps_from_comparison(comparison):
        return {
            "capability_gaps": [
                {
                    "capability": "github_repository_management",
                    "gap_source": "reference_mcp_comparison",
                    "severity": 0.7,
                }
            ]
        }

    monkeypatch.setattr(_mod, "compare_mcp_servers", fake_compare_mcp_servers, raising=False)
    monkeypatch.setattr(
        _mod,
        "derive_capability_gaps_from_comparison",
        fake_derive_capability_gaps_from_comparison,
        raising=False,
    )

    def fake_evaluate_planner_config(**kwargs):
        return {"risk_level": "low_risk"}

    def fake_run_mapping_repair_cycle(**kwargs):
        raise AssertionError("repair path should not run")

    def fake_run_governed_loop(args):
        return {
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
                                                "capability": "github_repository_management",
                                            }
                                        },
                                    }
                                ],
                            },
                        }
                    ]
                }
            }
        }

    output = tmp_path / "factory_cycle.json"

    try:
        artifact = _mod.run_factory_cycle(
            portfolio_state="portfolio_state.json",
            ledger="ledger.json",
            policy="policy.json",
            top_k=3,
            output=str(output),
            evaluate_planner_config=fake_evaluate_planner_config,
            run_mapping_repair_cycle=fake_run_mapping_repair_cycle,
            run_governed_loop=fake_run_governed_loop,
        )

        assert calls["compare"] == {
            "generated_path": str(generated.resolve()),
            "reference_path": "reference_mcp_github_repository_management",
            "output_path": None,
        }

        comparison = artifact["cycle_result"].get("reference_mcp_comparison")
        assert comparison is not None
        gaps = artifact["cycle_result"].get("reference_mcp_comparison_gaps")
        assert gaps is not None
        assert gaps["capability_gaps"][0]["capability"] == "github_repository_management"
    finally:
        if generated.exists():
            shutil.rmtree(generated)

def test_run_factory_cycle_records_reference_comparison_gap_for_mcp_build(tmp_path, monkeypatch):
    calls = {}

    def fake_build_capability_artifact(*, artifact_kind, capability, **kwargs):
        return {
            "status": "ok",
            "artifact_kind": artifact_kind,
            "capability": capability,
            "generated_repo": "/tmp/generated_mcp_server_github",
        }

    def fake_compare_mcp_servers(generated_path, reference_path, output_path=None):
        calls["compare"] = {
            "generated_path": generated_path,
            "reference_path": reference_path,
            "output_path": output_path,
        }
        return {
            "structure": {"generated_capability": "github_repository_management"},
            "tool_surface": {"coverage_ratio": 0.33, "missing_tools": ["create_issue"]},
            "capability_surface": {
                "coverage_ratio": 0.5,
                "missing_enabled": ["supports_dynamic_toolsets"],
            },
            "testability": {"coverage_ratio": 0.25},
        }

    def fake_update_capability_gaps_from_mcp_comparison(comparison_path, output_path=None):
        calls["gap_update"] = {
            "comparison_path": comparison_path,
            "output_path": output_path,
        }
        return {
            "capability_gaps": [
                {
                    "capability": "github_repository_management",
                    "gap_source": "reference_mcp_comparison",
                    "severity": 0.7,
                }
            ]
        }

    monkeypatch.setattr(_mod, "build_capability_artifact", fake_build_capability_artifact)
    monkeypatch.setattr(_mod, "compare_mcp_servers", fake_compare_mcp_servers, raising=False)
    monkeypatch.setattr(
        _mod,
        "update_capability_gaps_from_mcp_comparison",
        fake_update_capability_gaps_from_mcp_comparison,
        raising=False,
    )

    def fake_evaluate_planner_config(**kwargs):
        return {"risk_level": "low_risk"}

    def fake_run_mapping_repair_cycle(**kwargs):
        raise AssertionError("repair path should not run")

    def fake_run_governed_loop(args):
        return {
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
                                                "capability": "github_repository_management",
                                            }
                                        },
                                    }
                                ],
                            },
                        }
                    ]
                }
            }
        }

    output = tmp_path / "factory_cycle.json"

    artifact = _mod.run_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="ledger.json",
        policy="policy.json",
        top_k=3,
        output=str(output),
        evaluate_planner_config=fake_evaluate_planner_config,
        run_mapping_repair_cycle=fake_run_mapping_repair_cycle,
        run_governed_loop=fake_run_governed_loop,
    )

    assert calls["compare"] == {
        "generated_path": "/tmp/generated_mcp_server_github",
        "reference_path": "reference_mcp_github_repository_management",
        "output_path": None,
    }

    comparison = artifact["cycle_result"].get("reference_mcp_comparison")
    assert comparison is not None
    assert "tool_surface" in comparison

    gaps = artifact["cycle_result"].get("reference_mcp_comparison_gaps")
    assert gaps is not None
    assert gaps["capability_gaps"][0]["capability"] == "github_repository_management"


def test_run_factory_cycle_records_capability_evolution_execution_for_mcp_build(
    tmp_path, monkeypatch
):
    def fake_build_capability_artifact(*, artifact_kind, capability, **kwargs):
        return {
            "status": "ok",
            "artifact_kind": artifact_kind,
            "capability": capability,
            "generated_repo": "/tmp/generated_mcp_server_github",
            "tools": ["list_repositories"],
        }

    def fake_compare_mcp_servers(generated_path, reference_path, output_path=None):
        return {
            "structure": {"generated_capability": "github_repository_management"},
            "tool_surface": {
                "coverage_ratio": 0.33,
                "missing_tools": ["create_issue", "get_repository"],
            },
            "capability_surface": {
                "coverage_ratio": 0.5,
                "missing_enabled": ["supports_dynamic_toolsets"],
            },
            "testability": {"coverage_ratio": 0.25},
        }

    def fake_derive_capability_gaps_from_comparison(comparison):
        return {
            "capability_gaps": [
                {
                    "capability": "github_repository_management",
                    "gap_source": "reference_mcp_comparison",
                    "severity": 0.7,
                }
            ]
        }

    monkeypatch.setattr(_mod, "build_capability_artifact", fake_build_capability_artifact)
    monkeypatch.setattr(_mod, "compare_mcp_servers", fake_compare_mcp_servers, raising=False)
    monkeypatch.setattr(
        _mod,
        "derive_capability_gaps_from_comparison",
        fake_derive_capability_gaps_from_comparison,
        raising=False,
    )

    def fake_evaluate_planner_config(**kwargs):
        return {"risk_level": "low_risk"}

    def fake_run_mapping_repair_cycle(**kwargs):
        raise AssertionError("repair path should not run")

    def fake_run_governed_loop(args):
        return {
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
                                                "capability": "github_repository_management",
                                            }
                                        },
                                    }
                                ],
                            },
                        }
                    ]
                }
            }
        }

    output = tmp_path / "factory_cycle.json"

    artifact = _mod.run_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="ledger.json",
        policy="policy.json",
        top_k=3,
        output=str(output),
        evaluate_planner_config=fake_evaluate_planner_config,
        run_mapping_repair_cycle=fake_run_mapping_repair_cycle,
        run_governed_loop=fake_run_governed_loop,
    )

    assert artifact["cycle_result"]["capability_evolution_execution"] == {
        "builder_overrides": {
            "tools": [
                "list_repositories",
                "create_issue",
                "get_repository",
            ],
            "features": [
                "supports_dynamic_toolsets",
            ],
            "test_expansion": True,
        },
        "executable_actions": [
            {"type": "add_tool", "tool": "create_issue"},
            {"type": "add_tool", "tool": "get_repository"},
            {"type": "enable_feature", "feature": "supports_dynamic_toolsets"},
            {"type": "increase_test_coverage"},
        ],
        "deferred_actions": [],
        "executed_action_count": 4,
        "deferred_action_count": 0,
    }
    assert artifact["cycle_result"]["evolution_execution_metadata"] == {
        "builder_overrides_present": True,
        "builder_override_keys": ["features", "test_expansion", "tools"],
        "builder_overrides_applied": True,
    }

    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert (
        persisted["cycle_result"]["capability_evolution_execution"]
        == artifact["cycle_result"]["capability_evolution_execution"]
    )

def test_run_factory_cycle_records_no_evolution_override_metadata_when_comparison_has_no_gaps(
    tmp_path, monkeypatch
):
    def fake_build_capability_artifact(*, artifact_kind, capability, **kwargs):
        return {
            "status": "ok",
            "artifact_kind": artifact_kind,
            "capability": capability,
            "generated_repo": "/tmp/generated_mcp_server_github",
            "tools": ["list_repositories"],
        }

    def fake_compare_mcp_servers(generated_path, reference_path, output_path=None):
        return {
            "structure": {"generated_capability": "github_repository_management"},
            "tool_surface": {
                "coverage_ratio": 1.0,
                "missing_tools": [],
            },
            "capability_surface": {
                "coverage_ratio": 1.0,
                "missing_enabled": [],
            },
            "testability": {"coverage_ratio": 1.0},
        }

    monkeypatch.setattr(_mod, "build_capability_artifact", fake_build_capability_artifact)
    monkeypatch.setattr(_mod, "compare_mcp_servers", fake_compare_mcp_servers, raising=False)

    def fake_evaluate_planner_config(**kwargs):
        return {"risk_level": "low_risk"}

    def fake_run_mapping_repair_cycle(**kwargs):
        raise AssertionError("repair path should not run")

    def fake_run_governed_loop(args):
        return {
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
                                                "capability": "github_repository_management",
                                            }
                                        },
                                    }
                                ],
                            },
                        }
                    ]
                }
            }
        }

    artifact = _mod.run_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="ledger.json",
        policy="policy.json",
        top_k=3,
        output=str(tmp_path / "factory_cycle_no_overrides.json"),
        evaluate_planner_config=fake_evaluate_planner_config,
        run_mapping_repair_cycle=fake_run_mapping_repair_cycle,
        run_governed_loop=fake_run_governed_loop,
    )

    assert artifact["cycle_result"]["capability_evolution_execution"] == {
        "builder_overrides": {},
        "executable_actions": [],
        "deferred_actions": [],
        "executed_action_count": 0,
        "deferred_action_count": 0,
    }
    assert artifact["cycle_result"]["evolution_execution_metadata"] == {
        "builder_overrides_present": False,
        "builder_override_keys": [],
        "builder_overrides_applied": False,
    }
    assert artifact["cycle_result"]["synthesis_event"]["used_evolution"] is False
    assert "evolved_builder" not in artifact["cycle_result"]


def test_run_factory_cycle_rebuilds_mcp_artifact_with_evolution_overrides(tmp_path, monkeypatch):
    build_calls = []

    def fake_build_capability_artifact(*, artifact_kind, capability, **kwargs):
        build_calls.append(
            {
                "artifact_kind": artifact_kind,
                "capability": capability,
                "kwargs": kwargs,
            }
        )

        if len(build_calls) == 1:
            return {
                "status": "ok",
                "artifact_kind": artifact_kind,
                "capability": capability,
                "generated_repo": "/tmp/generated_mcp_server_github_v1",
                "tools": ["list_repositories"],
            }

        return {
            "status": "ok",
            "artifact_kind": artifact_kind,
            "capability": capability,
            "generated_repo": "/tmp/generated_mcp_server_github_v2",
            "tools": [
                "list_repositories",
                "create_issue",
                "get_repository",
            ],
            "features": ["supports_dynamic_toolsets"],
            "test_expansion": True,
        }

    def fake_compare_mcp_servers(generated_path, reference_path, output_path=None):
        return {
            "structure": {"generated_capability": "github_repository_management"},
            "tool_surface": {
                "coverage_ratio": 0.33,
                "missing_tools": ["create_issue", "get_repository"],
            },
            "capability_surface": {
                "coverage_ratio": 0.5,
                "missing_enabled": ["supports_dynamic_toolsets"],
            },
            "testability": {"coverage_ratio": 0.25},
        }

    def fake_derive_capability_gaps_from_comparison(comparison):
        return {
            "capability_gaps": [
                {
                    "capability": "github_repository_management",
                    "gap_source": "reference_mcp_comparison",
                    "severity": 0.7,
                }
            ]
        }

    monkeypatch.setattr(_mod, "build_capability_artifact", fake_build_capability_artifact)
    monkeypatch.setattr(_mod, "compare_mcp_servers", fake_compare_mcp_servers, raising=False)
    monkeypatch.setattr(
        _mod,
        "derive_capability_gaps_from_comparison",
        fake_derive_capability_gaps_from_comparison,
        raising=False,
    )

    def fake_evaluate_planner_config(**kwargs):
        return {"risk_level": "low_risk"}

    def fake_run_mapping_repair_cycle(**kwargs):
        raise AssertionError("repair path should not run")

    def fake_run_governed_loop(args):
        return {
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
                                                "capability": "github_repository_management",
                                            }
                                        },
                                    }
                                ],
                            },
                        }
                    ]
                }
            }
        }

    output = tmp_path / "factory_cycle.json"

    artifact = _mod.run_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="ledger.json",
        policy="policy.json",
        top_k=3,
        output=str(output),
        evaluate_planner_config=fake_evaluate_planner_config,
        run_mapping_repair_cycle=fake_run_mapping_repair_cycle,
        run_governed_loop=fake_run_governed_loop,
    )

    assert len(build_calls) == 2
    assert build_calls[0] == {
        "artifact_kind": "mcp_server",
        "capability": "github_repository_management",
        "kwargs": {},
    }
    assert build_calls[1] == {
        "artifact_kind": "mcp_server",
        "capability": "github_repository_management",
        "kwargs": {
            "tools": [
                "list_repositories",
                "create_issue",
                "get_repository",
            ],
            "features": ["supports_dynamic_toolsets"],
            "test_expansion": True,
        },
    }

    assert artifact["cycle_result"]["evolved_builder"] == {
        "status": "ok",
        "artifact_kind": "mcp_server",
        "capability": "github_repository_management",
        "generated_repo": "/tmp/generated_mcp_server_github_v2",
        "tools": [
            "list_repositories",
            "create_issue",
            "get_repository",
        ],
        "features": ["supports_dynamic_toolsets"],
        "test_expansion": True,
    }
    assert artifact["cycle_result"]["builder"] == artifact["cycle_result"]["evolved_builder"]
    assert artifact["cycle_result"]["evolution_execution_metadata"] == {
        "builder_overrides_present": True,
        "builder_override_keys": ["features", "test_expansion", "tools"],
        "builder_overrides_applied": True,
    }

    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted["cycle_result"]["evolved_builder"] == artifact["cycle_result"]["evolved_builder"]

def test_run_factory_cycle_records_similarity_progression(tmp_path, monkeypatch):
    def fake_build_capability_artifact(*, artifact_kind, capability, **kwargs):
        return {
            "status": "ok",
            "artifact_kind": artifact_kind,
            "capability": capability,
            "generated_repo": "/tmp/generated_mcp_server_github",
            "tools": ["list_repositories"],
        }

    def fake_compare_mcp_servers(generated_path, reference_path, output_path=None):
        return {
            "similarity": {
                "overall_score": 0.61,
            },
            "structure": {"generated_capability": "github_repository_management"},
            "tool_surface": {"coverage_ratio": 0.61, "missing_tools": []},
            "capability_surface": {"coverage_ratio": 0.61},
            "testability": {"coverage_ratio": 0.61},
        }

    monkeypatch.setattr(_mod, "build_capability_artifact", fake_build_capability_artifact)
    monkeypatch.setattr(_mod, "compare_mcp_servers", fake_compare_mcp_servers, raising=False)

    def fake_evaluate_planner_config(**kwargs):
        return {"risk_level": "low_risk"}

    def fake_run_mapping_repair_cycle(**kwargs):
        raise AssertionError("repair path should not run")

    def fake_run_governed_loop(args):
        return {
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
                                                "capability": "github_repository_management",
                                            }
                                        },
                                    }
                                ],
                            },
                        }
                    ]
                }
            }
        }

    output = tmp_path / "factory_cycle.json"

    artifact = _mod.run_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="ledger.json",
        policy="policy.json",
        top_k=3,
        output=str(output),
        evaluate_planner_config=fake_evaluate_planner_config,
        run_mapping_repair_cycle=fake_run_mapping_repair_cycle,
        run_governed_loop=fake_run_governed_loop,
    )

    row = artifact["capability_effectiveness_ledger"]["capabilities"]["github_repository_management"]

    assert row["similarity_score"] == 0.61
    assert "previous_similarity_score" not in row

    progression = artifact["cycle_result"]["similarity_progression"]
    assert progression["current_score"] == 0.61
    assert "previous_score" not in progression
    assert "delta" not in progression

    persisted = json.loads(output.read_text(encoding="utf-8"))
    persisted_row = persisted["capability_effectiveness_ledger"]["capabilities"]["github_repository_management"]
    persisted_progression = persisted["cycle_result"]["similarity_progression"]

    assert persisted_row["similarity_score"] == 0.61
    assert persisted_progression["current_score"] == 0.61
    assert "previous_score" not in persisted_progression
    assert "delta" not in persisted_progression



def test_run_factory_cycle_records_similarity_progression_from_prior_ledger(tmp_path, monkeypatch):
    prior_ledger = {
        "capabilities": {
            "github_repository_management": {
                "artifact_kind": "mcp_server",
                "failed_syntheses": 0,
                "last_synthesis_source": "planner_request",
                "last_synthesis_status": "ok",
                "last_synthesis_used_evolution": False,
                "similarity_score": 0.37,
                "successful_evolved_syntheses": 0,
                "successful_syntheses": 1,
                "total_syntheses": 1,
            }
        }
    }

    def fake_record_normalized_synthesis_event(ledger, synthesis_event):
        from src.mcp_governance_orchestrator.capability_effectiveness_ledger import record_synthesis_event
        return record_synthesis_event(
            prior_ledger,
            capability=synthesis_event["capability"],
            artifact_kind=synthesis_event["artifact_kind"],
            synthesis_source=synthesis_event["source"],
            synthesis_status=synthesis_event["status"],
            synthesis_used_evolution=synthesis_event.get("used_evolution", False),
            similarity_score=synthesis_event.get("similarity_score"),
            previous_similarity_score=prior_ledger["capabilities"]["github_repository_management"]["similarity_score"],
            similarity_delta=round(
                synthesis_event.get("similarity_score", 0)
                - prior_ledger["capabilities"]["github_repository_management"]["similarity_score"],
                2,
            ),
        )

    monkeypatch.setattr(_mod, "record_normalized_synthesis_event", fake_record_normalized_synthesis_event)
    monkeypatch.setattr(
        "planner_runtime.load_capability_effectiveness_ledger",
        lambda *_args, **_kwargs: prior_ledger,
    )

    def fake_build_capability_artifact(*, artifact_kind, capability, **kwargs):
        return {
            "status": "ok",
            "artifact_kind": artifact_kind,
            "capability": capability,
            "generated_repo": "/tmp/generated_mcp_server_github",
        }

    def fake_compare_mcp_servers(generated_path, reference_path, output_path=None):
        return {
            "similarity": {"overall_score": 0.61},
            "structure": {"generated_capability": "github_repository_management"},
            "tool_surface": {"coverage_ratio": 0.61, "missing_tools": []},
            "capability_surface": {"coverage_ratio": 0.61},
            "testability": {"coverage_ratio": 0.61},
        }

    monkeypatch.setattr(_mod, "build_capability_artifact", fake_build_capability_artifact)
    monkeypatch.setattr(_mod, "compare_mcp_servers", fake_compare_mcp_servers, raising=False)

    def fake_run_governed_loop(args):
        return {
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
                                                "capability": "github_repository_management",
                                            }
                                        },
                                    }
                                ],
                            },
                        }
                    ]
                }
            }
        }

    output = tmp_path / "factory_cycle.json"

    artifact = _mod.run_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="ledger.json",
        policy="policy.json",
        top_k=3,
        output=str(output),
        evaluate_planner_config=lambda **kwargs: {"risk_level": "low_risk"},
        run_mapping_repair_cycle=lambda **kwargs: (_ for _ in ()).throw(AssertionError("repair path should not run")),
        run_governed_loop=fake_run_governed_loop,
    )

    row = artifact["capability_effectiveness_ledger"]["capabilities"]["github_repository_management"]

    assert row["previous_similarity_score"] == 0.37
    assert row["similarity_score"] == 0.61
    assert row["similarity_delta"] == 0.24


def test_run_factory_cycle_skips_evolved_rebuild_when_prior_similarity_delta_is_negative(tmp_path, monkeypatch):
    prior_ledger = {
        "capabilities": {
            "github_repository_management": {
                "artifact_kind": "mcp_server",
                "failed_syntheses": 0,
                "last_synthesis_source": "planner_request",
                "last_synthesis_status": "ok",
                "last_synthesis_used_evolution": True,
                "similarity_score": 0.61,
                "similarity_delta": -0.12,
                "successful_evolved_syntheses": 1,
                "successful_syntheses": 1,
                "total_syntheses": 1,
            }
        }
    }

    build_calls = []

    def fake_record_normalized_synthesis_event(ledger, synthesis_event):
        from src.mcp_governance_orchestrator.capability_effectiveness_ledger import record_synthesis_event
        return record_synthesis_event(
            prior_ledger,
            capability=synthesis_event["capability"],
            artifact_kind=synthesis_event["artifact_kind"],
            synthesis_source=synthesis_event["source"],
            synthesis_status=synthesis_event["status"],
            synthesis_used_evolution=synthesis_event.get("used_evolution", False),
            similarity_score=synthesis_event.get("similarity_score"),
            previous_similarity_score=prior_ledger["capabilities"]["github_repository_management"]["similarity_score"],
            similarity_delta=round(
                synthesis_event.get("similarity_score", 0)
                - prior_ledger["capabilities"]["github_repository_management"]["similarity_score"],
                2,
            ),
        )

    monkeypatch.setattr(_mod, "record_normalized_synthesis_event", fake_record_normalized_synthesis_event)
    monkeypatch.setattr(
        "planner_runtime.load_capability_effectiveness_ledger",
        lambda *_args, **_kwargs: prior_ledger,
    )

    def fake_build_capability_artifact(*, artifact_kind, capability, **kwargs):
        build_calls.append(
            {
                "artifact_kind": artifact_kind,
                "capability": capability,
                "kwargs": kwargs,
            }
        )
        return {
            "status": "ok",
            "artifact_kind": artifact_kind,
            "capability": capability,
            "generated_repo": "/tmp/generated_mcp_server_github",
            "tools": ["list_repositories"],
        }

    def fake_compare_mcp_servers(generated_path, reference_path, output_path=None):
        return {
            "similarity": {"overall_score": 0.64},
            "structure": {"generated_capability": "github_repository_management"},
            "tool_surface": {
                "coverage_ratio": 0.64,
                "missing_tools": ["create_issue", "get_repository"],
            },
            "capability_surface": {
                "coverage_ratio": 0.64,
                "missing_enabled": ["supports_dynamic_toolsets"],
            },
            "testability": {"coverage_ratio": 0.64},
        }

    monkeypatch.setattr(_mod, "build_capability_artifact", fake_build_capability_artifact)
    monkeypatch.setattr(_mod, "compare_mcp_servers", fake_compare_mcp_servers, raising=False)

    def fake_run_governed_loop(args):
        return {
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
                                                "capability": "github_repository_management",
                                            }
                                        },
                                    }
                                ],
                            },
                        }
                    ]
                }
            }
        }

    output = tmp_path / "factory_cycle.json"

    artifact = _mod.run_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="ledger.json",
        policy="policy.json",
        top_k=3,
        output=str(output),
        evaluate_planner_config=lambda **kwargs: {"risk_level": "low_risk"},
        run_mapping_repair_cycle=lambda **kwargs: (_ for _ in ()).throw(AssertionError("repair path should not run")),
        run_governed_loop=fake_run_governed_loop,
    )

    assert len(build_calls) == 1
    assert build_calls[0] == {
        "artifact_kind": "mcp_server",
        "capability": "github_repository_management",
        "kwargs": {},
    }

    assert artifact["cycle_result"]["capability_evolution_plan"]["action_count"] == 4
    assert artifact["cycle_result"]["capability_evolution_execution"]["executed_action_count"] == 4
    assert artifact["cycle_result"]["evolution_execution_metadata"] == {
        "builder_overrides_present": True,
        "builder_override_keys": ["features", "test_expansion", "tools"],
        "builder_overrides_applied": False,
    }
    assert "evolved_builder" not in artifact["cycle_result"]
    assert artifact["cycle_result"]["evolution_blocked_by_similarity_regression"] is True
    assert artifact["cycle_result"]["builder"]["generated_repo"] == "/tmp/generated_mcp_server_github"
    assert artifact["cycle_result"]["synthesis_event"]["used_evolution"] is False

    row = artifact["capability_effectiveness_ledger"]["capabilities"]["github_repository_management"]
    assert row["previous_similarity_score"] == 0.61
    assert row["similarity_score"] == 0.64
    assert row["similarity_delta"] == 0.03


def test_run_factory_cycle_reenables_evolved_rebuild_after_blocked_cycle_records_non_negative_similarity_delta(tmp_path, monkeypatch):
    ledger_state = {
        "capabilities": {
            "github_repository_management": {
                "artifact_kind": "mcp_server",
                "failed_syntheses": 0,
                "last_synthesis_source": "planner_request",
                "last_synthesis_status": "ok",
                "last_synthesis_used_evolution": True,
                "similarity_score": 0.61,
                "similarity_delta": -0.12,
                "successful_evolved_syntheses": 1,
                "successful_syntheses": 1,
                "total_syntheses": 1,
            }
        }
    }

    build_calls = []
    similarity_values = [0.64, 0.70, 0.71, 0.71]

    def fake_record_normalized_synthesis_event(_ledger, synthesis_event):
        from src.mcp_governance_orchestrator.capability_effectiveness_ledger import record_synthesis_event

        capability = synthesis_event["capability"]
        prior_row = ledger_state["capabilities"][capability]

        updated = record_synthesis_event(
            ledger_state,
            capability=capability,
            artifact_kind=synthesis_event["artifact_kind"],
            synthesis_source=synthesis_event["source"],
            synthesis_status=synthesis_event["status"],
            synthesis_used_evolution=synthesis_event.get("used_evolution", False),
            similarity_score=synthesis_event.get("similarity_score"),
            previous_similarity_score=prior_row.get("similarity_score"),
            similarity_delta=round(
                synthesis_event.get("similarity_score", 0) - prior_row.get("similarity_score", 0),
                2,
            ) if synthesis_event.get("similarity_score") is not None and prior_row.get("similarity_score") is not None else None,
        )

        ledger_state["capabilities"][capability] = updated["capabilities"][capability]
        return updated

    monkeypatch.setattr(_mod, "record_normalized_synthesis_event", fake_record_normalized_synthesis_event)
    monkeypatch.setattr(
        "planner_runtime.load_capability_effectiveness_ledger",
        lambda *_args, **_kwargs: ledger_state,
    )

    def fake_build_capability_artifact(*, artifact_kind, capability, **kwargs):
        build_calls.append(
            {
                "artifact_kind": artifact_kind,
                "capability": capability,
                "kwargs": kwargs,
            }
        )
        return {
            "status": "ok",
            "artifact_kind": artifact_kind,
            "capability": capability,
            "generated_repo": "/tmp/generated_mcp_server_github",
            "tools": ["list_repositories"],
        }

    def fake_compare_mcp_servers(generated_path, reference_path, output_path=None):
        score = similarity_values.pop(0)
        return {
            "similarity": {"overall_score": score},
            "structure": {"generated_capability": "github_repository_management"},
            "tool_surface": {
                "coverage_ratio": score,
                "missing_tools": ["create_issue", "get_repository"],
            },
            "capability_surface": {
                "coverage_ratio": score,
                "missing_enabled": ["supports_dynamic_toolsets"],
            },
            "testability": {"coverage_ratio": score},
        }

    monkeypatch.setattr(_mod, "build_capability_artifact", fake_build_capability_artifact)
    monkeypatch.setattr(_mod, "compare_mcp_servers", fake_compare_mcp_servers, raising=False)

    def fake_run_governed_loop(args):
        return {
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
                                                "capability": "github_repository_management",
                                            }
                                        },
                                    }
                                ],
                            },
                        }
                    ]
                }
            }
        }

    artifact1 = _mod.run_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="ledger.json",
        policy="policy.json",
        top_k=3,
        output=str(tmp_path / "factory_cycle_1.json"),
        evaluate_planner_config=lambda **kwargs: {"risk_level": "low_risk"},
        run_mapping_repair_cycle=lambda **kwargs: (_ for _ in ()).throw(AssertionError("repair path should not run")),
        run_governed_loop=fake_run_governed_loop,
    )

    assert len(build_calls) == 1
    assert build_calls[0] == {
        "artifact_kind": "mcp_server",
        "capability": "github_repository_management",
        "kwargs": {},
    }
    assert "evolved_builder" not in artifact1["cycle_result"]
    assert artifact1["cycle_result"]["evolution_blocked_by_similarity_regression"] is True
    assert artifact1["cycle_result"]["evolution_regression_signal"] == {
        "prior_similarity_delta": -0.12,
    }
    assert artifact1["cycle_result"]["synthesis_event"]["used_evolution"] is False

    row1 = artifact1["capability_effectiveness_ledger"]["capabilities"]["github_repository_management"]
    assert row1["previous_similarity_score"] == 0.61
    assert row1["similarity_score"] == 0.64
    assert row1["similarity_delta"] == 0.03

    artifact2 = _mod.run_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="ledger.json",
        policy="policy.json",
        top_k=3,
        output=str(tmp_path / "factory_cycle_2.json"),
        evaluate_planner_config=lambda **kwargs: {"risk_level": "low_risk"},
        run_mapping_repair_cycle=lambda **kwargs: (_ for _ in ()).throw(AssertionError("repair path should not run")),
        run_governed_loop=fake_run_governed_loop,
    )

    assert len(build_calls) == 4
    assert build_calls[1] == {
        "artifact_kind": "mcp_server",
        "capability": "github_repository_management",
        "kwargs": {},
    }
    assert build_calls[2] == {
        "artifact_kind": "mcp_server",
        "capability": "github_repository_management",
        "kwargs": {
            "tools": [
                "list_repositories",
                "create_issue",
                "get_repository",
            ],
            "features": ["supports_dynamic_toolsets"],
            "test_expansion": True,
        },
    }

    assert artifact2["cycle_result"]["evolution_blocked_by_similarity_regression"] is False
    assert "evolution_regression_signal" not in artifact2["cycle_result"]
    assert artifact2["cycle_result"]["synthesis_event"]["used_evolution"] is True
    assert artifact2["cycle_result"]["builder"]["generated_repo"] == "/tmp/generated_mcp_server_github"
    assert artifact2["cycle_result"]["evolved_builder"]["generated_repo"] == "/tmp/generated_mcp_server_github"

    row2 = artifact2["capability_effectiveness_ledger"]["capabilities"]["github_repository_management"]
    assert row2["previous_similarity_score"] == 0.64
    assert row2["similarity_score"] == 0.71
    assert row2["similarity_delta"] == 0.07

def test_run_factory_cycle_stops_iterative_evolution_when_improvement_below_threshold(tmp_path, monkeypatch):
    similarity_values = [0.70, 0.704]
    build_calls = []

    monkeypatch.setattr("planner_runtime.load_capability_effectiveness_ledger", lambda *_a, **_k: {"capabilities": {}})
    monkeypatch.setattr(_mod, "build_capability_artifact", lambda *, artifact_kind, capability, **kwargs: (build_calls.append({"artifact_kind": artifact_kind, "capability": capability, "kwargs": kwargs}) or {"status": "ok", "artifact_kind": artifact_kind, "capability": capability, "generated_repo": "/tmp/generated_mcp_server_github", "tools": ["list_repositories"]}))
    monkeypatch.setattr(_mod, "compare_mcp_servers", lambda generated_path, reference_path, output_path=None: {"similarity": {"overall_score": similarity_values.pop(0)}, "structure": {"generated_capability": "github_repository_management"}, "tool_surface": {"coverage_ratio": 0.7, "missing_tools": ["create_issue"]}, "capability_surface": {"coverage_ratio": 0.7, "missing_enabled": []}, "testability": {"coverage_ratio": 0.7}}, raising=False)

    artifact = _mod.run_factory_cycle(
        portfolio_state="portfolio_state.json", ledger="ledger.json", policy="policy.json", top_k=3,
        output=str(tmp_path / "factory_cycle.json"),
        evaluate_planner_config=lambda **kwargs: {"risk_level": "low_risk"},
        run_mapping_repair_cycle=lambda **kwargs: (_ for _ in ()).throw(AssertionError("repair path should not run")),
        run_governed_loop=lambda args: {"result": {"evaluation_summary": {"runs": [{"selected_actions": ["build_mcp_server"], "selection_detail": {"ranked_action_window": ["build_mcp_server"], "ranked_action_window_detail": [{"action_type": "build_mcp_server", "task_binding": {"args": {"capability": "github_repository_management"}}}]}}]}}},
    )

    assert len(build_calls) == 2
    assert len(artifact["cycle_result"]["evolution_iterations"]) == 1
    assert artifact["cycle_result"]["evolution_iterations"][0]["similarity_delta"] == 0.0
    assert artifact["capability_effectiveness_ledger"]["capabilities"]["github_repository_management"]["similarity_score"] == 0.7


def test_run_factory_cycle_records_error_synthesis_event_when_builder_raises(tmp_path, monkeypatch):
    def fake_build_capability_artifact(*, artifact_kind, capability, **kwargs):
        raise RuntimeError("simulated build failure")

    monkeypatch.setattr(_mod, "build_capability_artifact", fake_build_capability_artifact)

    def fake_evaluate_planner_config(**kwargs):
        return {"risk_level": "low_risk"}

    def fake_run_mapping_repair_cycle(**kwargs):
        raise AssertionError("repair path should not run")

    def fake_run_governed_loop(args):
        return {
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
            }
        }

    output = tmp_path / "factory_cycle.json"

    artifact = _mod.run_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="ledger.json",
        policy="policy.json",
        top_k=3,
        output=str(output),
        evaluate_planner_config=fake_evaluate_planner_config,
        run_mapping_repair_cycle=fake_run_mapping_repair_cycle,
        run_governed_loop=fake_run_governed_loop,
    )

    cycle_result = artifact["cycle_result"]
    synthesis_event = cycle_result["synthesis_event"]

    assert synthesis_event["status"] == "error"
    assert synthesis_event["capability"] == "snowflake_data_access"
    assert synthesis_event["artifact_kind"] == "data_connector"
    assert synthesis_event["source"] == "planner_request"
    assert "simulated build failure" in cycle_result["builder_error"]


def test_run_factory_cycle_records_no_op_synthesis_event_when_build_request_is_none(tmp_path, monkeypatch):
    ledger_calls = []
    base_ledger = {"capabilities": {}}

    def fake_record_normalized_synthesis_event(ledger, synthesis_event):
        ledger_calls.append(synthesis_event)
        return ledger

    monkeypatch.setattr(_mod, "record_normalized_synthesis_event", fake_record_normalized_synthesis_event)

    def fake_evaluate_planner_config(**kwargs):
        return {"risk_level": "low_risk"}

    def fake_run_mapping_repair_cycle(**kwargs):
        raise AssertionError("repair path should not run")

    def fake_run_governed_loop(args):
        # Return a result with no build_capability_artifact action selected
        return {
            "result": {
                "evaluation_summary": {
                    "runs": [
                        {
                            "selected_actions": [],
                            "selection_detail": {
                                "ranked_action_window": [],
                                "ranked_action_window_detail": [],
                            },
                        }
                    ]
                }
            }
        }

    # portfolio_state with no capability_gaps so gap resolver also returns None
    portfolio_state = tmp_path / "portfolio_state.json"
    portfolio_state.write_text(
        json.dumps({}),
        encoding="utf-8",
    )

    output = tmp_path / "factory_cycle.json"

    artifact = _mod.run_factory_cycle(
        portfolio_state=str(portfolio_state),
        ledger="ledger.json",
        policy="policy.json",
        top_k=3,
        output=str(output),
        evaluate_planner_config=fake_evaluate_planner_config,
        run_mapping_repair_cycle=fake_run_mapping_repair_cycle,
        run_governed_loop=fake_run_governed_loop,
    )

    cycle_result = artifact["cycle_result"]
    synthesis_event = cycle_result["synthesis_event"]

    assert synthesis_event["status"] == "no_op"
    assert synthesis_event["source"] == "none"
    assert synthesis_event["capability"] == "none"
    assert synthesis_event["artifact_kind"] == "none"

    # no_op cycles must not update the ledger — idle cycles are not learning signals
    assert len(ledger_calls) == 0

    assert artifact["capability_effectiveness_ledger"] is not None


def test_no_op_synthesis_event_when_no_build_request(tmp_path, monkeypatch):
    """No-build-request path records no_op synthesis_event with sentinel fields
    and does not pollute the capability_effectiveness_ledger."""

    def fake_evaluate_planner_config(**kwargs):
        return {"risk_level": "low_risk"}

    def fake_run_mapping_repair_cycle(**kwargs):
        raise AssertionError("repair path should not run")

    def fake_run_governed_loop(args):
        return {
            "result": {
                "evaluation_summary": {
                    "runs": [
                        {
                            "selected_actions": [],
                            "selection_detail": {
                                "ranked_action_window": [],
                                "ranked_action_window_detail": [],
                            },
                        }
                    ]
                }
            }
        }

    # portfolio_state with no capability_gaps so gap resolver also returns None
    portfolio_state = tmp_path / "portfolio_state.json"
    portfolio_state.write_text(json.dumps({}), encoding="utf-8")

    output = tmp_path / "factory_cycle.json"

    artifact = _mod.run_factory_cycle(
        portfolio_state=str(portfolio_state),
        ledger="ledger.json",
        policy="policy.json",
        top_k=3,
        output=str(output),
        evaluate_planner_config=fake_evaluate_planner_config,
        run_mapping_repair_cycle=fake_run_mapping_repair_cycle,
        run_governed_loop=fake_run_governed_loop,
    )

    cycle_result = artifact["cycle_result"]
    synthesis_event = cycle_result["synthesis_event"]

    assert synthesis_event["status"] == "no_op"
    assert synthesis_event["source"] == "none"
    assert synthesis_event["capability"] == "none"
    assert synthesis_event["artifact_kind"] == "none"

    # no_op cycles must not create a synthetic "none" entry in the ledger
    ledger = artifact["capability_effectiveness_ledger"]
    assert "none" not in ledger["capabilities"]


def test_run_factory_cycle_records_synthesis_source_for_gap_build(tmp_path, monkeypatch):
    """synthesis_source is written into cycle_result when build is triggered by a portfolio gap."""

    def fake_build_capability_artifact(*, artifact_kind, capability, **kwargs):
        return {
            "status": "ok",
            "artifact_kind": artifact_kind,
            "capability": capability,
            "generated_repo": "/tmp/generated_agent_adapter_slack",
        }

    monkeypatch.setattr(_mod, "build_capability_artifact", fake_build_capability_artifact)

    def fake_run_governed_loop(args):
        return {
            "result": {
                "evaluation_summary": {
                    "runs": [
                        {
                            "selected_actions": [],
                            "selection_detail": {
                                "ranked_action_window": [],
                                "ranked_action_window_detail": [],
                            },
                        }
                    ]
                }
            }
        }

    portfolio_state = tmp_path / "portfolio_state.json"
    portfolio_state.write_text(
        json.dumps({"capability_gaps": ["slack_workspace_access"]}),
        encoding="utf-8",
    )

    output = tmp_path / "factory_cycle.json"

    artifact = _mod.run_factory_cycle(
        portfolio_state=str(portfolio_state),
        ledger="ledger.json",
        policy="policy.json",
        top_k=3,
        output=str(output),
        evaluate_planner_config=lambda **kwargs: {"risk_level": "low_risk"},
        run_mapping_repair_cycle=lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("repair path should not run")
        ),
        run_governed_loop=fake_run_governed_loop,
    )

    assert artifact["cycle_result"]["synthesis_source"] == "portfolio_gap"


def test_run_autonomous_factory_cycle_removes_fulfilled_gap_from_portfolio_state(tmp_path, monkeypatch):
    """Post-cycle write-back removes the fulfilled capability from portfolio state capability_gaps."""
    import importlib.util
    import sys

    _REPO_ROOT = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "run_autonomous_factory_cycle",
        _REPO_ROOT / "scripts" / "run_autonomous_factory_cycle.py",
    )
    _rafc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_rafc)

    portfolio_state = tmp_path / "portfolio_state.json"
    portfolio_state.write_text(
        json.dumps({"capability_gaps": ["slack_workspace_access", "github_repo_access"]}),
        encoding="utf-8",
    )

    output = tmp_path / "factory_cycle.json"
    output.write_text(json.dumps({"status": "completed"}), encoding="utf-8")

    fake_artifact = {
        "cycle_result": {
            "synthesis_source": "portfolio_gap",
            "synthesis_event": {
                "status": "ok",
                "capability": "slack_workspace_access",
            },
        }
    }

    monkeypatch.setattr(
        _rafc,
        "run_factory_cycle",
        lambda **kwargs: fake_artifact,
    )
    monkeypatch.setattr(
        _rafc,
        "update_capability_effectiveness_ledger",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        _rafc,
        "update_capability_artifact_registry",
        lambda **kwargs: None,
    )

    _rafc.run_autonomous_factory_cycle(
        portfolio_state=str(portfolio_state),
        ledger=None,
        capability_ledger=None,
        capability_ledger_output=None,
        capability_artifact_registry_output=None,
        policy=None,
        top_k=3,
        output=str(output),
    )

    remaining = json.loads(portfolio_state.read_text(encoding="utf-8"))
    assert "slack_workspace_access" not in remaining["capability_gaps"]
    assert "github_repo_access" in remaining["capability_gaps"]


def test_run_factory_cycle_used_evolution_false_when_all_iterations_regress(tmp_path, monkeypatch):
    """When the evolution loop runs but every iteration produces iteration_delta <= 0,
    used_evolution must be False in the synthesis_event."""
    build_calls = []
    # similarity_values: initial build score=0.70, then evolved score=0.65 (regress)
    similarity_values = [0.70, 0.65]

    monkeypatch.setattr(
        "planner_runtime.load_capability_effectiveness_ledger",
        lambda *_a, **_k: {"capabilities": {}},
    )
    monkeypatch.setattr(
        _mod,
        "build_capability_artifact",
        lambda *, artifact_kind, capability, **kwargs: (
            build_calls.append({"artifact_kind": artifact_kind, "capability": capability, "kwargs": kwargs})
            or {
                "status": "ok",
                "artifact_kind": artifact_kind,
                "capability": capability,
                "generated_repo": "/tmp/generated_mcp_server_github",
                "tools": ["list_repositories"],
            }
        ),
    )
    monkeypatch.setattr(
        _mod,
        "compare_mcp_servers",
        lambda generated_path, reference_path, output_path=None: {
            "similarity": {"overall_score": similarity_values.pop(0)},
            "structure": {"generated_capability": "github_repository_management"},
            "tool_surface": {"coverage_ratio": 0.7, "missing_tools": ["create_issue"]},
            "capability_surface": {"coverage_ratio": 0.7, "missing_enabled": []},
            "testability": {"coverage_ratio": 0.7},
        },
        raising=False,
    )

    artifact = _mod.run_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="ledger.json",
        policy="policy.json",
        top_k=3,
        output=str(tmp_path / "factory_cycle.json"),
        evaluate_planner_config=lambda **kwargs: {"risk_level": "low_risk"},
        run_mapping_repair_cycle=lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("repair path should not run")
        ),
        run_governed_loop=lambda args: {
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
                                                "capability": "github_repository_management",
                                            }
                                        },
                                    }
                                ],
                            },
                        }
                    ]
                }
            }
        },
    )

    # Evolution ran (loop entered) but all iterations regressed — used_evolution must be False
    assert len(artifact["cycle_result"]["evolution_iterations"]) == 1
    assert artifact["cycle_result"]["evolution_iterations"][0]["similarity_delta"] == -0.05
    assert artifact["cycle_result"]["synthesis_event"]["used_evolution"] is False


def test_run_factory_cycle_records_repair_only_synthesis_event(tmp_path, monkeypatch):
    """repair_only branch attaches a sentinel synthesis_event and does not write to the ledger."""

    def fake_evaluate_planner_config(**kwargs):
        return {"risk_level": "high_risk"}

    def fake_run_mapping_repair_cycle(**kwargs):
        return {"status": "repair_completed"}

    def fake_run_governed_loop(args):
        raise AssertionError("governed loop should not run in repair_only path")

    # portfolio_state with no capability_gaps so gap resolver also returns None
    portfolio_state = tmp_path / "portfolio_state.json"
    portfolio_state.write_text(json.dumps({}), encoding="utf-8")

    output = tmp_path / "factory_cycle.json"

    artifact = _mod.run_factory_cycle(
        portfolio_state=str(portfolio_state),
        ledger="ledger.json",
        policy="policy.json",
        top_k=3,
        output=str(output),
        evaluate_planner_config=fake_evaluate_planner_config,
        run_mapping_repair_cycle=fake_run_mapping_repair_cycle,
        run_governed_loop=fake_run_governed_loop,
    )

    assert artifact["cycle_result"]["synthesis_event"]["status"] == "ok"
    assert artifact["cycle_result"]["synthesis_event"]["source"] == "repair"
    assert artifact["capability_effectiveness_ledger"]["capabilities"]["_repair_cycle"]["total_syntheses"] == 1
    assert artifact["capability_effectiveness_ledger"]["capabilities"]["_repair_cycle"]["last_synthesis_source"] == "repair"


def test_run_factory_cycle_records_error_synthesis_event_on_builder_exception(tmp_path, monkeypatch):
    def fake_build_capability_artifact(*, artifact_kind, capability, **kwargs):
        raise RuntimeError("build failed")

    monkeypatch.setattr(_mod, "build_capability_artifact", fake_build_capability_artifact)

    def fake_evaluate_planner_config(**kwargs):
        return {"risk_level": "low_risk"}

    def fake_run_mapping_repair_cycle(**kwargs):
        raise AssertionError("repair path should not run")

    def fake_run_governed_loop(args):
        return {
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
                                                "capability": "github_repository_management",
                                            }
                                        },
                                    }
                                ],
                            },
                        }
                    ]
                }
            }
        }

    output = tmp_path / "factory_cycle.json"

    artifact = _mod.run_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="ledger.json",
        policy="policy.json",
        top_k=3,
        output=str(output),
        evaluate_planner_config=fake_evaluate_planner_config,
        run_mapping_repair_cycle=fake_run_mapping_repair_cycle,
        run_governed_loop=fake_run_governed_loop,
    )

    assert artifact["cycle_result"]["builder_error"] == "build failed"
    assert artifact["cycle_result"]["synthesis_event"]["status"] == "error"
    assert artifact["cycle_result"]["synthesis_event"]["capability"] == "github_repository_management"
    assert artifact["capability_effectiveness_ledger"]["capabilities"]["github_repository_management"]["failed_syntheses"] == 1


def test_run_factory_cycle_records_error_synthesis_event_when_repair_raises(tmp_path, monkeypatch):
    """repair_only branch catches exceptions from run_mapping_repair_cycle and
    records an error synthesis_event with failed_syntheses=1."""

    def fake_evaluate_planner_config(**kwargs):
        return {"risk_level": "high_risk"}

    def fake_run_mapping_repair_cycle(**kwargs):
        raise RuntimeError("repair exploded")

    def fake_run_governed_loop(args):
        raise AssertionError("governed loop should not run in repair_only path")

    portfolio_state = tmp_path / "portfolio_state.json"
    portfolio_state.write_text(json.dumps({}), encoding="utf-8")

    output = tmp_path / "factory_cycle.json"

    artifact = _mod.run_factory_cycle(
        portfolio_state=str(portfolio_state),
        ledger="ledger.json",
        policy="policy.json",
        top_k=3,
        output=str(output),
        evaluate_planner_config=fake_evaluate_planner_config,
        run_mapping_repair_cycle=fake_run_mapping_repair_cycle,
        run_governed_loop=fake_run_governed_loop,
    )

    synthesis_event = artifact["cycle_result"]["synthesis_event"]
    assert synthesis_event["status"] == "error"
    assert synthesis_event["capability"] == "_repair_cycle"
    assert synthesis_event["source"] == "repair"

    assert artifact["capability_effectiveness_ledger"]["capabilities"]["_repair_cycle"]["failed_syntheses"] == 1


def test_run_factory_cycle_governed_run_exception_guard(tmp_path, monkeypatch):
    """When run_governed_loop raises, run_factory_cycle must not propagate the
    exception and must record status=error with governed_run_error in cycle_result."""

    def fake_evaluate_planner_config(**kwargs):
        return {"risk_level": "low_risk"}

    def fake_run_governed_loop(args):
        raise RuntimeError("governed exploded")

    def fake_run_mapping_repair_cycle(**kwargs):
        raise AssertionError("wrong branch")

    portfolio_state = tmp_path / "portfolio_state.json"
    portfolio_state.write_text(json.dumps({}), encoding="utf-8")

    output = tmp_path / "factory_cycle.json"

    artifact = _mod.run_factory_cycle(
        portfolio_state=str(portfolio_state),
        ledger="ledger.json",
        policy="policy.json",
        top_k=3,
        output=str(output),
        evaluate_planner_config=fake_evaluate_planner_config,
        run_mapping_repair_cycle=fake_run_mapping_repair_cycle,
        run_governed_loop=fake_run_governed_loop,
    )

    assert artifact["cycle_result"]["status"] == "error"
    assert artifact["cycle_result"]["governed_run_error"] == "governed exploded"
