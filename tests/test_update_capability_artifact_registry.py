# SPDX-License-Identifier: MIT
"""Tests for scripts/update_capability_artifact_registry.py."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SCRIPT = _REPO_ROOT / "scripts" / "update_capability_artifact_registry.py"
_spec = importlib.util.spec_from_file_location("update_capability_artifact_registry", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
try:
    _spec.loader.exec_module(_mod)
except FileNotFoundError:
    _mod = None


def _require_module():
    if _mod is None:
        pytest.fail("scripts/update_capability_artifact_registry.py does not exist yet")
    return _mod


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _cycle_artifact(
    *,
    capability="github_repository_management",
    artifact_kind="mcp_server",
    source="planner_request",
    status="ok",
    generated_repo="/tmp/generated_mcp_server_github",
    evolved_generated_repo=None,
    used_evolution=False,
):
    cycle = {
        "cycle_result": {
            "builder": {
                "status": status,
                "artifact_kind": artifact_kind,
                "capability": capability,
                "generated_repo": generated_repo,
            },
            "synthesis_event": {
                "capability": capability,
                "artifact_kind": artifact_kind,
                "status": status,
                "source": source,
                "used_evolution": used_evolution,
                "generated_repo": generated_repo,
            },
        }
    }

    if evolved_generated_repo is not None:
        cycle["cycle_result"]["evolved_builder"] = {
            "status": status,
            "artifact_kind": artifact_kind,
            "capability": capability,
            "generated_repo": evolved_generated_repo,
        }
        cycle["cycle_result"]["builder"] = {
            "status": status,
            "artifact_kind": artifact_kind,
            "capability": capability,
            "generated_repo": evolved_generated_repo,
        }
        cycle["cycle_result"]["synthesis_event"]["generated_repo"] = evolved_generated_repo
        cycle["cycle_result"]["synthesis_event"]["used_evolution"] = True

    return cycle


def test_creates_new_registry_entry(tmp_path):
    mod = _require_module()

    registry = tmp_path / "capability_artifact_registry.json"
    cycle = tmp_path / "cycle.json"
    _write_json(cycle, _cycle_artifact())

    rc = mod.update_capability_artifact_registry(
        registry_path=str(registry),
        cycle_artifact_path=str(cycle),
    )

    assert rc == 0

    result = _read_json(registry)
    assert result == {
        "capabilities": {
            "github_repository_management": {
                "artifact_kind": "mcp_server",
                "history": [
                    {
                        "artifact": "/tmp/generated_mcp_server_github",
                        "revision": 1,
                        "source": "planner_request",
                        "status": "ok",
                        "used_evolution": False,
                    }
                ],
                "latest_artifact": "/tmp/generated_mcp_server_github",
                "revision": 1,
            }
        }
    }


def test_prefers_evolved_builder_generated_repo_when_present(tmp_path):
    mod = _require_module()

    registry = tmp_path / "capability_artifact_registry.json"
    cycle = tmp_path / "cycle.json"
    _write_json(
        cycle,
        _cycle_artifact(
            generated_repo="/tmp/generated_mcp_server_github_base",
            evolved_generated_repo="/tmp/generated_mcp_server_github_evolved",
            used_evolution=True,
        ),
    )

    mod.update_capability_artifact_registry(
        registry_path=str(registry),
        cycle_artifact_path=str(cycle),
    )

    result = _read_json(registry)
    row = result["capabilities"]["github_repository_management"]

    assert row["latest_artifact"] == "/tmp/generated_mcp_server_github_evolved"
    assert row["revision"] == 1
    assert row["history"][0]["artifact"] == "/tmp/generated_mcp_server_github_evolved"
    assert row["history"][0]["used_evolution"] is True


def test_appends_revision_history_for_new_accepted_artifact(tmp_path):
    mod = _require_module()

    registry = tmp_path / "capability_artifact_registry.json"
    cycle1 = tmp_path / "cycle1.json"
    cycle2 = tmp_path / "cycle2.json"

    _write_json(
        cycle1,
        _cycle_artifact(generated_repo="/tmp/generated_mcp_server_github_v1"),
    )
    _write_json(
        cycle2,
        _cycle_artifact(generated_repo="/tmp/generated_mcp_server_github_v2"),
    )

    mod.update_capability_artifact_registry(
        registry_path=str(registry),
        cycle_artifact_path=str(cycle1),
    )
    mod.update_capability_artifact_registry(
        registry_path=str(registry),
        cycle_artifact_path=str(cycle2),
    )

    result = _read_json(registry)
    row = result["capabilities"]["github_repository_management"]

    assert row["latest_artifact"] == "/tmp/generated_mcp_server_github_v2"
    assert row["revision"] == 2
    assert row["history"] == [
        {
            "artifact": "/tmp/generated_mcp_server_github_v1",
            "revision": 1,
            "source": "planner_request",
            "status": "ok",
            "used_evolution": False,
        },
        {
            "artifact": "/tmp/generated_mcp_server_github_v2",
            "revision": 2,
            "source": "planner_request",
            "status": "ok",
            "used_evolution": False,
        },
    ]


def test_same_latest_artifact_is_idempotent(tmp_path):
    mod = _require_module()

    registry = tmp_path / "capability_artifact_registry.json"
    cycle = tmp_path / "cycle.json"
    _write_json(cycle, _cycle_artifact(generated_repo="/tmp/generated_mcp_server_github_v1"))

    mod.update_capability_artifact_registry(
        registry_path=str(registry),
        cycle_artifact_path=str(cycle),
    )
    first_text = registry.read_text(encoding="utf-8")

    mod.update_capability_artifact_registry(
        registry_path=str(registry),
        cycle_artifact_path=str(cycle),
    )
    second_text = registry.read_text(encoding="utf-8")

    assert first_text == second_text

    result = _read_json(registry)
    row = result["capabilities"]["github_repository_management"]
    assert row["revision"] == 1
    assert len(row["history"]) == 1


def test_non_ok_synthesis_does_not_update_registry(tmp_path):
    mod = _require_module()

    registry = tmp_path / "capability_artifact_registry.json"
    cycle = tmp_path / "cycle.json"
    _write_json(cycle, _cycle_artifact(status="error"))

    mod.update_capability_artifact_registry(
        registry_path=str(registry),
        cycle_artifact_path=str(cycle),
    )

    result = _read_json(registry)
    assert result == {"capabilities": {}}


def test_existing_invalid_registry_fails_closed(tmp_path):
    mod = _require_module()

    registry = tmp_path / "capability_artifact_registry.json"
    registry.write_text('{"capabilities": []}\n', encoding="utf-8")

    cycle = tmp_path / "cycle.json"
    _write_json(cycle, _cycle_artifact())

    rc = mod.update_capability_artifact_registry(
        registry_path=str(registry),
        cycle_artifact_path=str(cycle),
    )

    assert rc == 1
    assert _read_json(registry) == {"capabilities": []}


def test_missing_cycle_artifact_returns_one_and_does_not_create_output(tmp_path):
    mod = _require_module()

    registry = tmp_path / "capability_artifact_registry.json"
    rc = mod.update_capability_artifact_registry(
        registry_path=str(registry),
        cycle_artifact_path=str(tmp_path / "missing_cycle.json"),
    )

    assert rc == 1
    assert not registry.exists()


def test_registry_update_from_real_factory_cycle_output(tmp_path, monkeypatch):
    """Feed a real run_factory_cycle() output to update_capability_artifact_registry.

    Confirms _extract_registration() correctly navigates the full factory
    envelope (decision, inputs, evaluation, capability_effectiveness_ledger,
    status) and reads only the cycle_result fields it needs.
    """
    mod = _require_module()

    import factory_pipeline as _fp

    def fake_build_capability_artifact(*, artifact_kind, capability, **kwargs):
        return {
            "status": "ok",
            "artifact_kind": artifact_kind,
            "capability": capability,
            "generated_repo": "/tmp/generated_data_connector_snowflake",
        }

    monkeypatch.setattr(_fp, "build_capability_artifact", fake_build_capability_artifact)

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

    _fp.run_factory_cycle(
        portfolio_state="portfolio_state.json",
        ledger="ledger.json",
        policy="policy.json",
        top_k=3,
        output=str(output),
        evaluate_planner_config=fake_evaluate_planner_config,
        run_mapping_repair_cycle=fake_run_mapping_repair_cycle,
        run_governed_loop=fake_run_governed_loop,
    )

    registry_path = tmp_path / "registry.json"
    rc = mod.update_capability_artifact_registry(
        registry_path=str(registry_path),
        cycle_artifact_path=str(output),
    )

    assert rc == 0

    registry = _read_json(registry_path)
    row = registry["capabilities"]["snowflake_data_access"]
    assert row["latest_artifact"] == "/tmp/generated_data_connector_snowflake"
    assert row["revision"] == 1
