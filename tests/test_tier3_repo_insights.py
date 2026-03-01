import json

from mcp_governance_orchestrator.server import run_guardians


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def test_tier3_repo_insights_is_deterministic_and_contract_compliant():
    out1 = run_guardians(repo_path=".", guardians=["repo_insights:v1"])
    out2 = run_guardians(repo_path=".", guardians=["repo_insights:v1"])

    assert _canonical(out1) == _canonical(out2)

    assert out1["ok"] is True
    assert out1["fail_closed"] is False

    g = out1["guardians"][0]
    assert g["invoked"] is True
    assert g["ok"] is True
    assert g["fail_closed"] is False

    inner = g["output"]
    assert isinstance(inner, dict)

    assert "tool" in inner and isinstance(inner["tool"], str) and inner["tool"]
    assert "ok" in inner and isinstance(inner["ok"], bool) and inner["ok"] is True
    assert "fail_closed" in inner and isinstance(inner["fail_closed"], bool) and inner["fail_closed"] is False
    assert "suggestions" in inner
