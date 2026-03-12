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
