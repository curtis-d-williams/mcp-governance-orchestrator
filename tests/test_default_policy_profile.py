import json
import subprocess
import sys
from pathlib import Path


def test_default_policy_profile_fails_without_tier1_2(tmp_path: Path):
    # Use the repo's default policy profile file.
    policy_path = Path("policies/default.json")
    assert policy_path.exists()

    r = subprocess.run(
        [sys.executable, "-m", "mcp_governance_orchestrator.registry", "run-policy", str(policy_path), "."],
        capture_output=True,
        text=True,
    )

    # This repo currently appears to have Tier 3-only templates selected by default,
    # so the default governance profile should fail policy evaluation and MUST NOT execute.
    assert r.returncode == 2
    data = json.loads(r.stdout)

    # When policy fails, run-policy returns the policy plan (same as enforce-policy)
    assert data["policy_path"] == str(policy_path)
    assert data["ok"] is False
    assert data["fail_closed"] is True
    assert "constraints" in data

    # Ensure the failing constraint is the intended one (require_tiers)
    names = [c.get("name") for c in data.get("constraints", [])]
    assert "require_tiers" in names
