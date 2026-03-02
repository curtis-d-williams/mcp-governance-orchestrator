import json
import subprocess
import sys


def test_run_policy_default_alias_matches_direct_call():
    # Direct invocation
    direct = subprocess.run(
        [
            sys.executable,
            "-m",
            "mcp_governance_orchestrator.registry",
            "run-policy",
            "policies/default.json",
            ".",
        ],
        capture_output=True,
        text=True,
    )

    # Alias invocation
    alias = subprocess.run(
        [
            sys.executable,
            "-m",
            "mcp_governance_orchestrator.registry",
            "run-policy-default",
            ".",
        ],
        capture_output=True,
        text=True,
    )

    assert direct.returncode == alias.returncode
    assert json.loads(direct.stdout) == json.loads(alias.stdout)
