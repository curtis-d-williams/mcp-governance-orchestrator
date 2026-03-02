import json
import subprocess
import sys
from pathlib import Path


def test_run_policy_combined_output_contract(tmp_path: Path):
    # Policy that will pass in this repo (Tier 3 templates exist),
    # so run-policy returns the combined {policy, execution, ...} shape.
    policy = {"policy_version": 1}
    p = tmp_path / "policy.json"
    p.write_text(json.dumps(policy), encoding="utf-8")

    r = subprocess.run(
        [sys.executable, "-m", "mcp_governance_orchestrator.registry", "run-policy", str(p), "."],
        capture_output=True,
        text=True,
    )
    assert r.returncode in (0, 2)  # execution could fail on some machines, but shape must hold

    data = json.loads(r.stdout)

    # Combined envelope keys must be present
    for key in ("ok", "fail_closed", "policy", "execution", "selected_guardians", "policy_path", "repo_path"):
        assert key in data

    assert data["policy_path"] == str(p)
    assert data["repo_path"] == "."

    # Policy sub-shape (frozen)
    policy_obj = data["policy"]
    for key in ("ok", "fail_closed", "selection", "summary", "require", "forbid", "constraints", "policy_path"):
        assert key in policy_obj
    assert policy_obj["policy_path"] == str(p)
    assert isinstance(policy_obj["selection"]["selected_guardians"], list)

    # Execution sub-shape (frozen by server.run_guardians contract)
    exec_obj = data["execution"]
    for key in ("tool", "repo_path", "ok", "fail_closed", "guardians"):
        assert key in exec_obj
    assert exec_obj["tool"] == "run_guardians"
