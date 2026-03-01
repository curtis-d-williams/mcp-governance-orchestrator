import json

from mcp_governance_orchestrator.server import run_guardians


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def test_tier3_template_is_deterministic_and_non_enforcing():
    out1 = run_guardians(repo_path=".", guardians=["intelligence_layer_template:v1"])
    out2 = run_guardians(repo_path=".", guardians=["intelligence_layer_template:v1"])

    # Determinism: byte-identical canonical JSON
    assert _canonical(out1) == _canonical(out2)

    # Suggestion-only invariant: Tier 3 must not fail-closed
    g = out1["guardians"][0]
    assert g["invoked"] is True
    assert g["ok"] is True
    assert g["fail_closed"] is False

    # Orchestrator should remain ok/fail_closed consistent
    assert out1["ok"] is True
    assert out1["fail_closed"] is False
