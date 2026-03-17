# SPDX-License-Identifier: MIT
"""Regression tests for the generate_mcp_server developer entrypoint."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import builder.mcp_builder as mcp_builder


def test_generate_mcp_server_script_defaults_to_github_poc():
    repo_root = mcp_builder.REPO_ROOT
    generated = repo_root / "generated_mcp_server_github"

    if generated.exists():
        shutil.rmtree(generated)

    try:
        result = subprocess.run(
            [sys.executable, "scripts/generate_mcp_server.py"],
            cwd=repo_root,
            env={**os.environ, "PYTHONPATH": str(repo_root)},
            capture_output=True,
            text=True,
            check=True,
        )

        payload = json.loads(result.stdout)
        assert payload == {
            "status": "ok",
            "generated_repo": str(generated),
            "artifact_kind": "mcp_server",
            "capability": "github_repository_management",
            "tools": {
                "list_repositories": {},
                "get_repository": {"params": ["repo"]},
                "create_issue": {"params": ["repo", "title", "body"]},
            },
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
            "tools": {
                "list_repositories": {},
                "get_repository": {"params": ["repo"]},
                "create_issue": {"params": ["repo", "title", "body"]},
            },
            "features": [],
        }

        server_text = (generated / "server.py").read_text(encoding="utf-8")
        readme_text = (generated / "README.md").read_text(encoding="utf-8")
        smoke_text = (generated / "tests" / "test_server_smoke.py").read_text(
            encoding="utf-8"
        )

        for tool_name in (
            "list_repositories",
            "get_repository",
            "create_issue",
        ):
            assert tool_name in server_text
            assert tool_name in readme_text

        assert "generated_mcp_server_github" in smoke_text or "server" in smoke_text
    finally:
        if generated.exists():
            shutil.rmtree(generated)


def test_mcp_runtime_tool_invocation():
    """Regression: generated server executes tools through the MCP runtime."""
    repo_root = mcp_builder.REPO_ROOT
    generated = repo_root / "generated_mcp_server_github"

    if generated.exists():
        shutil.rmtree(generated)

    try:
        subprocess.run(
            [sys.executable, "scripts/generate_mcp_server.py"],
            cwd=repo_root,
            env={**os.environ, "PYTHONPATH": str(repo_root)},
            capture_output=True,
            text=True,
            check=True,
        )

        result = subprocess.run(
            [
                "fastmcp", "call",
                "--server-spec", str(generated / "server.py"),
                "--target", "list_repositories",
                "--json",
            ],
            cwd=repo_root,
            env={**os.environ, "PYTHONPATH": str(repo_root)},
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, f"fastmcp call failed: {result.stderr}"
        response = json.loads(result.stdout)
        assert response["is_error"] is False
        assert "list_repositories" in response["content"][0]["text"]
    finally:
        if generated.exists():
            shutil.rmtree(generated)
