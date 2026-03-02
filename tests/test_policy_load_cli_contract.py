import subprocess
import sys
import json


def test_enforce_policy_cli_load_error_is_canonical():
    # /dev/null is an empty file -> json.load fails deterministically.
    r = subprocess.run(
        [sys.executable, "-m", "mcp_governance_orchestrator.registry", "enforce-policy", "/dev/null"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 3
    data = json.loads(r.stdout)
    assert data["ok"] is False
    assert data["fail_closed"] is True
    assert data["error_type"] == "policy_load"
    assert isinstance(data["errors"], list)
    assert data["errors"][0]["path"] == "$"
    assert data["errors"][0]["code"] == "load_error"
