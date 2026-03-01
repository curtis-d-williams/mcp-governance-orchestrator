import json
from pathlib import Path

from mcp_governance_orchestrator.registry import list_registry, list_from_inspected, normalize_registry


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def test_registry_list_is_deterministic_on_repo_registry():
    out1 = list_registry(repo_root=Path("."), where=["tier=3"])
    out2 = list_registry(repo_root=Path("."), where=["tier=3"])
    assert _canon(out1) == _canon(out2)


def test_registry_list_filters_entry_format_and_tier_on_repo_registry():
    out = list_registry(repo_root=Path("."), where=["entry_format=legacy", "tier=3"])
    assert len(out) >= 1
    for row in out:
        assert row["entry_format"] == "legacy"
        assert row["tier"] == 3


def test_registry_list_field_projection_is_deterministic():
    out = list_registry(repo_root=Path("."), where=["tier=3"], fields=["tier"])
    for row in out:
        assert set(row.keys()) == {"guardian_id", "tier"}


def test_registry_list_capabilities_checks_membership_filter_in_memory():
    raw = {
        "x:v1": {
            "module_path": "templates.repo_insights.server",
            "callable": "main",
            "tier": 3,
            "description": "",
            "capabilities": {"checks": ["alpha", "beta"]},
        },
        "y:v1": {
            "module_path": "templates.repo_insights.server",
            "callable": "main",
            "tier": 3,
            "description": "",
            "capabilities": {"checks": ["beta"]},
        },
    }
    inspected = normalize_registry(raw)
    rows = list_from_inspected(inspected, where=["capabilities.checks=alpha"], fields=["tier"])
    assert [r["guardian_id"] for r in rows] == ["x:v1"]
