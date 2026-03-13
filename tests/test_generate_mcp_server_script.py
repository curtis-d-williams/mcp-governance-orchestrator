# SPDX-License-Identifier: MIT
"""Regression tests for the generate_mcp_server developer entrypoint."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import builder.mcp_builder as mcp_builder


def test_generate_mcp_server_script_defaults_to_github_poc():
    repo_root = mcp_builder.REPO_ROOT
    generated = repo_root / "generated_mcp_github"

    if generated.exists():
        shutil.rmtree(generated)

    try:
        result = subprocess.run(
            [sys.executable, "scripts/generate_mcp_server.py"],
            cwd=repo_root,
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
            "name": "generated_mcp_github",
            "capability": "github_repository_management",
            "protocol": "model-context-protocol",
            "version": "0.1.0",
            "tools": [
                "list_repositories",
                "get_repository",
                "create_issue",
            ],
        }
    finally:
        if generated.exists():
            shutil.rmtree(generated)
