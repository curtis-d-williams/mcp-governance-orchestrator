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

    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert (
        persisted["cycle_result"]["capability_evolution_execution"]
        == artifact["cycle_result"]["capability_evolution_execution"]
    )

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
    similarity_values = [0.64, 0.70]

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

    assert len(build_calls) == 3
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
    assert row2["similarity_score"] == 0.70
    assert row2["similarity_delta"] == 0.06
