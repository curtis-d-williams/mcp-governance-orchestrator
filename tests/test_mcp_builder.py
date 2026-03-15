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
        "artifact_kind": "mcp_server",
        "capability": "github_repository_management",
        "tools": [
            "list_repositories",
            "get_repository",
            "create_issue",
        ],
        "features": [],
        "test_expansion": False,
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
        "features": [],
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

def test_build_mcp_server_exposes_callable_tool_functions():
    repo_root = _mod.REPO_ROOT
    generated = repo_root / "generated_mcp_server_github"

    if generated.exists():
        shutil.rmtree(generated)

    try:
        _mod.build_mcp_server()

        server_text = (generated / "server.py").read_text(encoding="utf-8")

        assert 'from fastmcp import FastMCP' in server_text
        assert 'mcp = FastMCP("generated_mcp_server_github")' in server_text
        assert '@mcp.tool()\ndef list_repositories():' in server_text
        assert '@mcp.tool()\ndef get_repository():' in server_text
        assert '@mcp.tool()\ndef create_issue():' in server_text
        assert 'def main():' in server_text
        assert 'if __name__ == "__main__":' in server_text
    finally:
        if generated.exists():
            shutil.rmtree(generated)

def test_build_mcp_server_generates_callable_wrappers_for_dynamic_tools():
    repo_root = _mod.REPO_ROOT
    generated = repo_root / "generated_mcp_server_github"

    if generated.exists():
        shutil.rmtree(generated)

    try:
        _mod.build_mcp_server(
            tools=[
                "list_repositories",
                "get_repository",
                "create_issue",
                "get_me",
            ]
        )

        server_text = (generated / "server.py").read_text(encoding="utf-8")

        assert "from .tools.get_me import get_me as _get_me" in server_text
        assert "from tools.get_me import get_me as _get_me" in server_text
        assert "def get_me():" in server_text
        assert "return _get_me()" in server_text
    finally:
        if generated.exists():
            shutil.rmtree(generated)

def test_build_mcp_server_renders_enabled_features_in_manifest():
    repo_root = _mod.REPO_ROOT
    generated = repo_root / "generated_mcp_server_github"

    if generated.exists():
        shutil.rmtree(generated)

    try:
        _mod.build_mcp_server(
            features=["supports_dynamic_toolsets"],
        )

        manifest = json.loads((generated / "manifest.json").read_text(encoding="utf-8"))

        assert manifest["features"] == ["supports_dynamic_toolsets"]
    finally:
        if generated.exists():
            shutil.rmtree(generated)

def test_build_mcp_server_renders_enabled_features_in_readme():
    repo_root = _mod.REPO_ROOT
    generated = repo_root / "generated_mcp_server_github"

    if generated.exists():
        shutil.rmtree(generated)

    try:
        _mod.build_mcp_server(
            features=["supports_dynamic_toolsets"],
        )

        readme = (generated / "README.md").read_text(encoding="utf-8")

        assert "Features:" in readme
        assert "- supports_dynamic_toolsets" in readme
    finally:
        if generated.exists():
            shutil.rmtree(generated)

def test_build_mcp_server_generates_additional_test_file_when_test_expansion_enabled():
    repo_root = _mod.REPO_ROOT
    generated = repo_root / "generated_mcp_server_github"

    if generated.exists():
        shutil.rmtree(generated)

    try:
        result = _mod.build_mcp_server(test_expansion=True)

        assert result["test_expansion"] is True
        assert (generated / "tests" / "test_server_smoke.py").is_file()
        assert (generated / "tests" / "test_tools_basic.py").is_file()

        test_text = (generated / "tests" / "test_tools_basic.py").read_text(
            encoding="utf-8"
        )
        assert "def test_all_tools_callable():" in test_text
    finally:
        if generated.exists():
            shutil.rmtree(generated)

def test_build_mcp_server_smoke_test_imports_generated_server_from_artifact_root():
    repo_root = _mod.REPO_ROOT
    generated = repo_root / "generated_mcp_server_github"

    if generated.exists():
        shutil.rmtree(generated)

    try:
        _mod.build_mcp_server()

        smoke_text = (generated / "tests" / "test_server_smoke.py").read_text(
            encoding="utf-8"
        )

        assert "import sys" in smoke_text
        assert "from pathlib import Path" in smoke_text
        assert 'sys.path.insert(0, str(Path(__file__).resolve().parents[1]))' in smoke_text
        assert "import server" in smoke_text
    finally:
        if generated.exists():
            shutil.rmtree(generated)
