import json
from pathlib import Path

from mcp_governance_orchestrator.registry import validate_registry


def _canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def test_registry_validate_is_deterministic_and_ok_on_repo_registry():
    out1 = validate_registry(repo_root=Path("."))
    out2 = validate_registry(repo_root=Path("."))

    assert _canonical_json(out1) == _canonical_json(out2)
    assert out1["ok"] is True
    assert out1["errors"] == []
    assert isinstance(out1["warnings"], list)
    assert isinstance(out1["count"], int)
