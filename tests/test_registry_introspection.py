import json
from pathlib import Path

from mcp_governance_orchestrator.registry import load_registry, inspect_registry


def _canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def test_registry_introspection_is_deterministic_and_sorted():
    """
    The introspection output must be deterministic across runs and sorted by guardian_id.
    """
    out1 = inspect_registry(repo_root=Path("."))
    out2 = inspect_registry(repo_root=Path("."))

    assert _canonical_json(out1) == _canonical_json(out2)

    keys = list(out1.keys())
    assert keys == sorted(keys)


def test_registry_introspection_schema_and_backward_compat():
    """
    Every entry must contain the required normalized keys.
    Introspection must support both legacy string and structured registry formats.
    """
    raw = load_registry(repo_root=Path("."))

    out = inspect_registry(repo_root=Path("."))

    required = {"module_path", "callable", "tier", "description", "capabilities", "entry_format"}

    for guardian_id, meta in out.items():
        assert set(meta.keys()) == required
        assert isinstance(meta["module_path"], str)
        assert isinstance(meta["callable"], str)
        assert isinstance(meta["tier"], int)
        assert isinstance(meta["description"], str)
        assert isinstance(meta["capabilities"], dict)
        assert meta["entry_format"] in ("legacy", "structured")

        # Backward compatibility sanity: if raw is legacy string, introspection reports legacy.
        if isinstance(raw.get(guardian_id), str):
            assert meta["entry_format"] == "legacy"
