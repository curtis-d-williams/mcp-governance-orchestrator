# SPDX-License-Identifier: MIT
"""Regression tests for the governed capability factory pipeline."""

import json

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
                "successful_syntheses": 1,
                "total_syntheses": 1,
            }
        }
    }

    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted["capability_effectiveness_ledger"] == artifact["capability_effectiveness_ledger"]


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

    comparison = artifact["cycle_result"].get("reference_mcp_comparison")
    assert comparison is not None
    assert comparison["capability_gaps"][0]["capability"] == "github_repository_management"


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
            ]
        },
        "executable_actions": [
            {"type": "add_tool", "tool": "create_issue"},
            {"type": "add_tool", "tool": "get_repository"},
        ],
        "deferred_actions": [
            {"type": "enable_feature", "feature": "supports_dynamic_toolsets"},
            {"type": "increase_test_coverage"},
        ],
        "executed_action_count": 2,
        "deferred_action_count": 2,
    }

    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert (
        persisted["cycle_result"]["capability_evolution_execution"]
        == artifact["cycle_result"]["capability_evolution_execution"]
    )
