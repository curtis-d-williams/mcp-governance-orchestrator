# SPDX-License-Identifier: MIT
"""Regression tests for scripts/run_capability_evolution_plan.py."""

import importlib.util
import json
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SCRIPT = _REPO_ROOT / "scripts" / "run_capability_evolution_plan.py"
_spec = importlib.util.spec_from_file_location("run_capability_evolution_plan", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

run_capability_evolution_plan = _mod.run_capability_evolution_plan


def test_run_capability_evolution_plan_rebuilds_compares_and_updates_ledger(
    tmp_path,
    monkeypatch,
):
    plan = tmp_path / "plan.json"
    ledger = tmp_path / "capability_effectiveness_ledger.json"
    output = tmp_path / "execution.json"

    plan.write_text(
        json.dumps(
            {
                "capability_evolution_plan": {
                    "evolution_actions": [
                        {"type": "add_tool", "tool": "create_issue"},
                        {"type": "increase_test_coverage"},
                    ],
                    "action_count": 2,
                }
            }
        ),
        encoding="utf-8",
    )
    ledger.write_text(
        json.dumps(
            {
                "capabilities": {
                    "github_repository_management": {
                        "artifact_kind": "mcp_server",
                        "failed_syntheses": 0,
                        "successful_evolved_syntheses": 0,
                        "successful_syntheses": 1,
                        "total_syntheses": 1,
                        "last_synthesis_source": "planner_request",
                        "last_synthesis_status": "ok",
                        "last_synthesis_used_evolution": False,
                        "similarity_score": 0.50,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    def fake_build_capability_artifact(*, artifact_kind, capability, **kwargs):
        assert artifact_kind == "mcp_server"
        assert capability == "github_repository_management"
        assert kwargs == {
            "tools": ["list_repositories", "create_issue"],
            "test_expansion": True,
        }
        return {
            "status": "ok",
            "artifact_kind": artifact_kind,
            "capability": capability,
            "generated_repo": "generated_mcp_server_github",
            "tools": kwargs["tools"],
        }

    def fake_get_reference_artifact_path(capability):
        assert capability == "github_repository_management"
        return "reference_mcp_github"

    def fake_compare_mcp_servers(generated_path, reference_path, output_path=None):
        assert generated_path == "generated_mcp_server_github"
        assert reference_path == "reference_mcp_github"
        assert output_path is None
        return {
            "generated": generated_path,
            "reference": reference_path,
            "similarity": {"overall_score": 0.74},
        }

    monkeypatch.setattr(_mod, "build_capability_artifact", fake_build_capability_artifact)
    monkeypatch.setattr(_mod, "get_reference_artifact_path", fake_get_reference_artifact_path)
    monkeypatch.setattr(_mod, "compare_mcp_servers", fake_compare_mcp_servers)

    artifact = run_capability_evolution_plan(
        plan_path=str(plan),
        artifact_kind="mcp_server",
        capability="github_repository_management",
        current_tools=["list_repositories"],
        ledger_path=str(ledger),
        output_path=str(output),
    )

    assert artifact["capability_evolution_execution"]["builder_overrides"] == {
        "tools": ["list_repositories", "create_issue"],
        "test_expansion": True,
    }
    assert artifact["synthesis_event"] == {
        "artifact_kind": "mcp_server",
        "capability": "github_repository_management",
        "generated_repo": "generated_mcp_server_github",
        "previous_similarity_score": 0.50,
        "similarity_delta": 0.24,
        "similarity_score": 0.74,
        "source": "planner_request",
        "status": "ok",
        "used_evolution": True,
    }

    row = artifact["capability_effectiveness_ledger"]["capabilities"]["github_repository_management"]
    assert row["successful_evolved_syntheses"] == 1
    assert row["successful_syntheses"] == 2
    assert row["total_syntheses"] == 2
    assert row["similarity_score"] == 0.74
    assert row["previous_similarity_score"] == 0.50
    assert row["similarity_delta"] == 0.24

    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted["synthesis_event"] == artifact["synthesis_event"]


def test_run_capability_evolution_plan_fails_closed_when_no_builder_overrides(
    tmp_path,
):
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "capability_evolution_plan": {
                    "evolution_actions": [],
                    "action_count": 0,
                }
            }
        ),
        encoding="utf-8",
    )

    try:
        run_capability_evolution_plan(
            plan_path=str(plan),
            artifact_kind="mcp_server",
            capability="github_repository_management",
            current_tools=["list_repositories"],
        )
    except ValueError as exc:
        assert str(exc) == "no deterministic builder overrides produced from evolution plan"
    else:
        raise AssertionError("expected fail-closed ValueError")

def test_run_capability_evolution_plan_fails_closed_on_missing_reference_path(
    tmp_path,
    monkeypatch,
):
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "capability_evolution_plan": {
                    "evolution_actions": [
                        {"type": "add_tool", "tool": "create_issue"},
                    ],
                    "action_count": 1,
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        _mod,
        "get_reference_artifact_path",
        lambda capability: None,
    )

    try:
        run_capability_evolution_plan(
            plan_path=str(plan),
            artifact_kind="mcp_server",
            capability="github_repository_management",
            current_tools=["list_repositories"],
        )
    except ValueError as exc:
        assert str(exc) == (
            "missing reference artifact path for capability: "
            "github_repository_management"
        )
    else:
        raise AssertionError("expected fail-closed ValueError")


def test_run_capability_evolution_plan_fails_closed_on_builder_non_ok_status(
    tmp_path,
    monkeypatch,
):
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "capability_evolution_plan": {
                    "evolution_actions": [
                        {"type": "add_tool", "tool": "create_issue"},
                    ],
                    "action_count": 1,
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        _mod,
        "get_reference_artifact_path",
        lambda capability: "reference_mcp_github",
    )

    def fake_build_capability_artifact(*, artifact_kind, capability, **kwargs):
        return {
            "status": "error",
            "artifact_kind": artifact_kind,
            "capability": capability,
        }

    monkeypatch.setattr(
        _mod,
        "build_capability_artifact",
        fake_build_capability_artifact,
    )

    try:
        run_capability_evolution_plan(
            plan_path=str(plan),
            artifact_kind="mcp_server",
            capability="github_repository_management",
            current_tools=["list_repositories"],
        )
    except ValueError as exc:
        assert str(exc) == "builder returned non-ok status: error"
    else:
        raise AssertionError("expected fail-closed ValueError")


def test_stage_3b_smoke_real_fixture_build_evolution_execution():
    """Smoke: build_evolution_execution against real experiments/factory_demo fixture."""
    from src.mcp_governance_orchestrator.capability_evolution_executor import (
        build_evolution_execution,
    )

    fixture_path = _REPO_ROOT / "experiments" / "factory_demo" / "capability_evolution_plan.json"
    plan_artifact = json.loads(fixture_path.read_text(encoding="utf-8"))

    # fixture has no wrapper key — _normalize_plan branch: "evolution_actions" at top level
    assert "evolution_actions" in plan_artifact

    result = build_evolution_execution(
        plan_artifact,
        artifact_kind="mcp_server",
        current_tools=[],
    )

    overrides = result["builder_overrides"]
    assert isinstance(overrides, dict), "builder_overrides must be a dict"
    assert overrides, "builder_overrides must be non-empty for this fixture"

    # 3 add_tool actions → tools list
    assert "tools" in overrides
    assert set(overrides["tools"]) == {"create_pull_request", "get_copilot_space", "get_me"}

    # 6 enable_feature actions → features list
    assert "features" in overrides
    assert len(overrides["features"]) == 6

    # 1 increase_test_coverage action
    assert overrides.get("test_expansion") is True

    # all 10 actions are executable; none deferred
    assert result["executed_action_count"] == 10
    assert result["deferred_action_count"] == 0


def test_stage_3c_smoke_real_fixture_full_script_path(monkeypatch):
    """Smoke: full script path — plan parse → executor → builder → compare → ledger.

    Stubs only compare_mcp_servers (requires a reference MCP directory on disk
    that does not exist in the repo). All other calls (build_evolution_execution,
    get_reference_artifact_path, build_capability_artifact) run against real code.
    """
    import shutil

    fixture_path = _REPO_ROOT / "experiments" / "factory_demo" / "capability_evolution_plan.json"

    captured = {}

    def fake_compare_mcp_servers(generated_path, reference_path, output_path=None):
        captured["generated_path"] = generated_path
        captured["reference_path"] = reference_path
        return {
            "generated": generated_path,
            "reference": reference_path,
            "similarity": {"overall_score": 0.80},
        }

    monkeypatch.setattr(_mod, "compare_mcp_servers", fake_compare_mcp_servers)

    generated_repo = None
    try:
        artifact = run_capability_evolution_plan(
            plan_path=str(fixture_path),
            artifact_kind="mcp_server",
            capability="github_repository_management",
        )
        generated_repo = artifact.get("builder", {}).get("generated_repo")

        # Plan parse + executor: builder_overrides populated by real build_evolution_execution
        overrides = artifact["capability_evolution_execution"]["builder_overrides"]
        assert set(overrides["tools"]) == {"create_pull_request", "get_copilot_space", "get_me"}
        assert overrides.get("test_expansion") is True

        # Builder ran real: compare stub received the real generated_repo path
        assert captured.get("generated_path") == generated_repo
        assert captured.get("reference_path") == "reference_mcp_github_repository_management"

        # Ledger updated in-memory (no prior ledger passed → starts fresh)
        row = artifact["capability_effectiveness_ledger"]["capabilities"]["github_repository_management"]
        assert row["total_syntheses"] == 1
        assert row["successful_evolved_syntheses"] == 1
        assert row["similarity_score"] == 0.80

        # Synthesis event wired through
        assert artifact["synthesis_event"]["used_evolution"] is True
        assert artifact["synthesis_event"]["status"] == "ok"

    finally:
        if generated_repo and Path(generated_repo).exists():
            shutil.rmtree(generated_repo)
