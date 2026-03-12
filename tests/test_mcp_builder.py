# SPDX-License-Identifier: MIT
"""Regression tests for the deterministic MCP builder."""

import json
import shutil
from pathlib import Path

import builder.mcp_builder as _mod


def _read(path):
    return Path(path).read_text(encoding="utf-8")


def test_build_mcp_server_generates_expected_repo_shape():
    repo_root = _mod.REPO_ROOT
    generated = repo_root / "generated_mcp_server_github"

    if generated.exists():
        shutil.rmtree(generated)

    result = _mod.build_mcp_server()

    assert result == {
        "status": "ok",
        "generated_repo": str(generated),
        "tools": [
            "list_repositories",
            "get_repository",
            "create_issue",
        ],
    }

    assert generated.is_dir()
    assert (generated / "README.md").is_file()
    assert (generated / "manifest.json").is_file()
    assert (generated / "server.py").is_file()
    assert (generated / "tools" / "list_repositories.py").is_file()
    assert (generated / "tools" / "get_repository.py").is_file()
    assert (generated / "tools" / "create_issue.py").is_file()
    assert (generated / "tests" / "test_server_smoke.py").is_file()

    manifest = json.loads((generated / "manifest.json").read_text(encoding="utf-8"))
    assert manifest == {
        "name": "generated_mcp_server_github",
        "capability": "github_repository_management",
        "protocol": "model-context-protocol",
        "version": "0.1.0",
        "tools": [
            "list_repositories",
            "get_repository",
            "create_issue",
        ],
    }

    shutil.rmtree(generated)


def test_build_mcp_server_is_deterministic_across_repeated_runs():
    repo_root = _mod.REPO_ROOT
    generated = repo_root / "generated_mcp_server_github"

    if generated.exists():
        shutil.rmtree(generated)

    _mod.build_mcp_server()
    first_snapshot = {
        str(path.relative_to(generated)): _read(path)
        for path in sorted(p for p in generated.rglob("*") if p.is_file())
    }

    _mod.build_mcp_server()
    second_snapshot = {
        str(path.relative_to(generated)): _read(path)
        for path in sorted(p for p in generated.rglob("*") if p.is_file())
    }

    assert first_snapshot == second_snapshot

    shutil.rmtree(generated)


def test_build_mcp_server_rejects_non_mcp_capability():
    try:
        _mod.build_mcp_server(capability="slack_workspace_access")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "slack_workspace_access" in str(exc)
        assert "mcp_server" in str(exc)
