# SPDX-License-Identifier: MIT
from mcp_governance_orchestrator.server import run_guardians


def test_fail_closed_propagates() -> None:
    # Deterministic: unknown guardian IDs must fail-closed.
    out = run_guardians(
        repo_path=".",
        guardians=[
            "mcp-repo-hygiene-guardian:v1",
            "unknown-guardian-for-test:v1",
        ],
    )

    assert out["ok"] is False
    assert out["fail_closed"] is True

    # Ensure the unknown guardian is what caused fail-closed.
    g_unknown = [g for g in out["guardians"] if g["guardian_id"] == "unknown-guardian-for-test:v1"][0]
    assert g_unknown["invoked"] is False
    assert g_unknown["ok"] is False
    assert g_unknown["fail_closed"] is True
