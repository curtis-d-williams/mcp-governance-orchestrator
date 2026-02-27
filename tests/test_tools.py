from __future__ import annotations

from mcp_governance_orchestrator.server import run_guardians


def test_run_guardians_fail_closed_on_empty_guardians() -> None:
    out = run_guardians(repo_path="/repos/example", guardians=[])
    assert out["tool"] == "run_guardians"
    assert out["repo_path"] == "/repos/example"
    assert out["ok"] is False
    assert out["fail_closed"] is True
    assert isinstance(out["guardians"], list)
    assert len(out["guardians"]) == 1
    assert out["guardians"][0]["fail_closed"] is True


def test_run_guardians_fail_closed_on_unknown_guardian() -> None:
    out = run_guardians(repo_path="/repos/example", guardians=["unknown:v1"])
    assert out["ok"] is False
    assert out["fail_closed"] is True
    assert len(out["guardians"]) == 1
    assert out["guardians"][0]["guardian_id"] == "unknown:v1"
    assert out["guardians"][0]["invoked"] is False
    assert out["guardians"][0]["fail_closed"] is True
    assert out["guardians"][0]["output"] is None


def test_run_guardians_preserves_input_order() -> None:
    gids = ["unknown-a:v1", "unknown-b:v1"]
    out = run_guardians(repo_path="/repos/example", guardians=gids)
    assert [g["guardian_id"] for g in out["guardians"]] == gids