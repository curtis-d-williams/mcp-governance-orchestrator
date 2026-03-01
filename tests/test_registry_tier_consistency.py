import json
from pathlib import Path

from mcp_governance_orchestrator.server import GUARDIAN_TIERS, run_guardians


def test_registry_tier_consistency():
    registry_path = Path(__file__).resolve().parents[1] / "config" / "guardians.json"
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)

    for guardian_id, entry in data.items():
        assert isinstance(guardian_id, str) and guardian_id

        # Legacy string entries: no explicit tier to validate here (tier is inferred).
        if isinstance(entry, str):
            assert entry
            continue

        # Structured entries must be dicts with module_path
        assert isinstance(entry, dict)
        mp = entry.get("module_path")
        assert isinstance(mp, str) and mp

        tier = entry.get("tier", None)

        # If a structured entry includes tier=3, it must be a templates.* module.
        if tier == 3:
            assert mp.startswith("templates.")

        # If a structured entry points at templates.*, it must explicitly be tier 3.
        # (Prevents mismatches where call convention would be wrong.)
        if mp.startswith("templates."):
            assert tier == 3


def test_all_tier3_guardians_are_suggestion_only():
    # Use orchestrator-resolved tier map (covers both legacy + structured entries).
    tier3_ids = [gid for gid, t in GUARDIAN_TIERS.items() if t == 3]
    assert tier3_ids, "expected at least one tier 3 guardian"

    for gid in tier3_ids:
        out = run_guardians(repo_path=".", guardians=[gid])
        assert out["ok"] is True
        assert out["fail_closed"] is False

        g = out["guardians"][0]
        assert g["invoked"] is True
        assert g["ok"] is True
        assert g["fail_closed"] is False

        inner = g["output"]
        assert isinstance(inner, dict)
        assert "tool" in inner and isinstance(inner["tool"], str) and inner["tool"]
        assert "suggestions" in inner
        assert inner.get("fail_closed") is False
