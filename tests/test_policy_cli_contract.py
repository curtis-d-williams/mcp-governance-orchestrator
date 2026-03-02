import json
import subprocess
import sys
from pathlib import Path


def test_enforce_policy_cli_success(tmp_path: Path):
    policy = {
        "require": [],
        "forbid": [],
        "constraints": {}
    }

    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mcp_governance_orchestrator.registry",
            "enforce-policy",
            str(policy_path),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0

    data = json.loads(result.stdout)

    assert isinstance(data, dict)
    assert data["ok"] is True
    assert data["fail_closed"] is True
    assert data["policy_path"] == str(policy_path)

    # Canonical top-level keys must exist
    for key in ("ok", "fail_closed", "selection", "summary", "require", "forbid", "constraints", "policy_path"):
        assert key in data

    assert "selected_guardians" in data["selection"]
    assert isinstance(data["selection"]["selected_guardians"], list)


def test_enforce_policy_cli_failure(tmp_path: Path):
    policy = {
        "require": [{"tier": 999}]
    }

    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mcp_governance_orchestrator.registry",
            "enforce-policy",
            str(policy_path),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2

    data = json.loads(result.stdout)
    assert data["ok"] is False
    assert data["fail_closed"] is True
