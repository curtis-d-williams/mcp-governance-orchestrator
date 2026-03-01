import json

from mcp_governance_orchestrator.server import run_guardians


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def test_tier3_template_is_deterministic_and_non_enforcing():
    out1 = run_guardians(repo_path=".", guardians=["intelligence_layer_template:v1"])
    out2 = run_guardians(repo_path=".", guardians=["intelligence_layer_template:v1"])

    # Determinism: byte-identical canonical JSON
    assert _canonical(out1) == _canonical(out2)

    # Orchestrator wrapper invariants
    assert out1["ok"] is True
    assert out1["fail_closed"] is False
    assert isinstance(out1["guardians"], list) and len(out1["guardians"]) == 1

    g = out1["guardians"][0]
    assert g["invoked"] is True
    assert g["ok"] is True
    assert g["fail_closed"] is False

    # Tier 3 output contract invariants
    inner = g["output"]
    assert isinstance(inner, dict)

    assert "tool" in inner and isinstance(inner["tool"], str) and inner["tool"]
    assert "ok" in inner and isinstance(inner["ok"], bool) and inner["ok"] is True
    assert "fail_closed" in inner and isinstance(inner["fail_closed"], bool) and inner["fail_closed"] is False

    # Tier 3 should emit suggestions payload (shape may evolve, but must exist and be deterministic)
    assert "suggestions" in inner
