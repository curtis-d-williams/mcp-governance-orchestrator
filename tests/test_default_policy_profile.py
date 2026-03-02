import json
import subprocess
import sys
from pathlib import Path


def test_default_policy_profile_passes_in_this_repo():
    policy_path = Path("policies/default.json")
    assert policy_path.exists()

    r = subprocess.run(
        [sys.executable, "-m", "mcp_governance_orchestrator.registry", "run-policy", str(policy_path), "."],
        capture_output=True,
        text=True,
    )

    assert r.returncode == 0
    data = json.loads(r.stdout)

    # When policy passes, run-policy executes and returns combined envelope
    assert data["policy_path"] == str(policy_path)
    assert data["ok"] is True
    assert data["fail_closed"] is False
    assert "policy" in data
    assert "execution" in data


def test_default_policy_fails_when_selecting_tier3_only(tmp_path: Path):
    # Force a Tier 3-only selection; the default constraints should fail.
    policy_path = tmp_path / "tier3_only_policy.json"
    policy = {
        "policy_version": 1,
        "select": [{"tier": 3}],
        "constraints": {
            "disallow_tier3_only": True,
            "min_selected": 1,
            "require_tiers": [1, 2],
        },
    }
    policy_path.write_text(json.dumps(policy, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    r = subprocess.run(
        [sys.executable, "-m", "mcp_governance_orchestrator.registry", "run-policy", str(policy_path), "."],
        capture_output=True,
        text=True,
    )

    # Policy should fail; run-policy MUST NOT execute and returns the policy plan (same as enforce-policy)
    assert r.returncode == 2
    data = json.loads(r.stdout)

    assert data["policy_path"] == str(policy_path)
    assert data["ok"] is False
    assert data["fail_closed"] is True
    assert "constraints" in data
    assert "execution" not in data

    names = [c.get("name") for c in data.get("constraints", [])]
    assert "disallow_tier3_only" in names
    assert "require_tiers" in names
