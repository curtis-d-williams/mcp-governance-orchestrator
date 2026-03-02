import json
import subprocess
import sys
from pathlib import Path


def _run(args):
    return subprocess.run(
        [sys.executable, "-m", "mcp_governance_orchestrator.registry", *args],
        capture_output=True,
        text=True,
    )


def test_run_policy_cli_schema_failure(tmp_path: Path):
    policy = {"select": [], "require": [], "forbid": [], "constraints": {}}
    p = tmp_path / "policy.json"
    p.write_text(json.dumps(policy), encoding="utf-8")

    r = _run(["run-policy", str(p), "."])
    assert r.returncode == 3
    data = json.loads(r.stdout)
    assert data["ok"] is False
    assert data["fail_closed"] is True
    assert data["error_type"] == "policy_schema"
    assert isinstance(data["errors"], list)
    assert data["errors"][0]["path"] == "$.policy_version"


def test_run_policy_cli_policy_fail_does_not_execute(tmp_path: Path):
    # Set an impossible constraint so policy evaluation fails deterministically.
    policy = {"policy_version": 1, "constraints": {"min_selected": 999999}}
    p = tmp_path / "policy.json"
    p.write_text(json.dumps(policy), encoding="utf-8")

    r = _run(["run-policy", str(p), "."])
    assert r.returncode == 2
    data = json.loads(r.stdout)

    # When policy fails, output is the policy plan (same as enforce-policy)
    assert data["policy_path"] == str(p)
    assert data["ok"] is False
    assert data["fail_closed"] is True
    assert "selection" in data
    assert "summary" in data
    assert "constraints" in data
