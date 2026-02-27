from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict

import pytest

import mcp_governance_orchestrator.server as server_module
from mcp_governance_orchestrator.server import GUARDIAN_ROUTING_TABLE, run_guardians

POLICY_GID = "mcp-policy-guardian:v1"
RELEASE_GID = "mcp-release-guardian:v1"


# ---- Existing tests (unchanged) ----

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


# ---- New tests: in-process routing ----

def _mock_module(callable_name: str, fn) -> SimpleNamespace:
    """Return a SimpleNamespace that exposes fn under callable_name."""
    return SimpleNamespace(**{callable_name: fn})


def test_success_invoked_true(monkeypatch) -> None:
    """Successful invocation: invoked=True, ok=True, output embedded verbatim."""
    guardian_output: Dict[str, Any] = {
        "tool": "check_repo_policy",
        "ok": True,
        "fail_closed": False,
        "details": "all checks passed",
    }
    _, callable_name = GUARDIAN_ROUTING_TABLE[POLICY_GID]
    mock_mod = _mock_module(callable_name, lambda repo_path: guardian_output)
    monkeypatch.setattr(server_module.importlib, "import_module", lambda _: mock_mod)

    out = run_guardians(repo_path="/repos/example", guardians=[POLICY_GID])

    assert out["ok"] is True
    assert out["fail_closed"] is False
    g = out["guardians"][0]
    assert g["guardian_id"] == POLICY_GID
    assert g["invoked"] is True
    assert g["ok"] is True
    assert g["fail_closed"] is False
    assert g["output"] is guardian_output  # exact same object — verbatim embedding
    assert g["details"] == ""


def test_import_failure(monkeypatch) -> None:
    """importlib.import_module raises → guardian_import_failed, invoked=False."""
    def bad_import(module_path: str):
        raise ImportError("no such module")

    monkeypatch.setattr(server_module.importlib, "import_module", bad_import)

    out = run_guardians(repo_path="/repos/example", guardians=[POLICY_GID])

    g = out["guardians"][0]
    assert g["invoked"] is False
    assert g["fail_closed"] is True
    assert g["output"] is None
    assert g["details"] == "fail-closed: guardian_import_failed"


def test_call_failure(monkeypatch) -> None:
    """callable(repo_path) raises → guardian_call_failed, invoked=False."""
    _, callable_name = GUARDIAN_ROUTING_TABLE[POLICY_GID]

    def raising_fn(repo_path: str):
        raise RuntimeError("guardian exploded")

    mock_mod = _mock_module(callable_name, raising_fn)
    monkeypatch.setattr(server_module.importlib, "import_module", lambda _: mock_mod)

    out = run_guardians(repo_path="/repos/example", guardians=[POLICY_GID])

    g = out["guardians"][0]
    assert g["invoked"] is False
    assert g["fail_closed"] is True
    assert g["output"] is None
    assert g["details"] == "fail-closed: guardian_call_failed"


def test_output_invalid_not_a_dict(monkeypatch) -> None:
    """callable returns a non-dict → guardian_output_invalid, invoked=False."""
    _, callable_name = GUARDIAN_ROUTING_TABLE[POLICY_GID]
    mock_mod = _mock_module(callable_name, lambda _: "not a dict")
    monkeypatch.setattr(server_module.importlib, "import_module", lambda _: mock_mod)

    out = run_guardians(repo_path="/repos/example", guardians=[POLICY_GID])

    g = out["guardians"][0]
    assert g["invoked"] is False
    assert g["output"] is None
    assert g["details"] == "fail-closed: guardian_output_invalid"


def test_output_invalid_missing_tool_key(monkeypatch) -> None:
    """callable returns a dict without 'tool' key → guardian_output_invalid."""
    _, callable_name = GUARDIAN_ROUTING_TABLE[POLICY_GID]
    mock_mod = _mock_module(callable_name, lambda _: {"ok": True, "details": "x"})
    monkeypatch.setattr(server_module.importlib, "import_module", lambda _: mock_mod)

    out = run_guardians(repo_path="/repos/example", guardians=[POLICY_GID])

    g = out["guardians"][0]
    assert g["invoked"] is False
    assert g["details"] == "fail-closed: guardian_output_invalid"


def test_unknown_guardian_not_imported() -> None:
    """IDs absent from KNOWN_GUARDIANS fail with guardian_unknown; no import attempted."""
    out = run_guardians(repo_path="/repos/example", guardians=["completely-unknown:v1"])

    g = out["guardians"][0]
    assert g["invoked"] is False
    assert g["details"] == "fail-closed: guardian_unknown"


def test_order_preservation_with_known_guardians(monkeypatch) -> None:
    """Input order is preserved when multiple known guardians are requested."""
    policy_mod_path, policy_fn_name = GUARDIAN_ROUTING_TABLE[POLICY_GID]
    release_mod_path, release_fn_name = GUARDIAN_ROUTING_TABLE[RELEASE_GID]

    def mock_import(module_path: str) -> SimpleNamespace:
        if module_path == policy_mod_path:
            return _mock_module(policy_fn_name, lambda _: {"tool": "check_repo_policy"})
        if module_path == release_mod_path:
            return _mock_module(release_fn_name, lambda _: {"tool": "check_repo_release"})
        raise ImportError(module_path)

    monkeypatch.setattr(server_module.importlib, "import_module", mock_import)

    gids = [RELEASE_GID, POLICY_GID]
    out = run_guardians(repo_path="/repos/example", guardians=gids)

    assert [g["guardian_id"] for g in out["guardians"]] == gids
    assert out["guardians"][0]["guardian_id"] == RELEASE_GID
    assert out["guardians"][1]["guardian_id"] == POLICY_GID
