# SPDX-License-Identifier: MIT
"""Regression tests for scripts/inspect_reference_mcp.py.

Covers:
1. Descriptor extraction from server.json.
2. Testability extraction from repo layout.
3. Tooling extraction from tools.go and README/docs.
4. Capability extraction from server configuration files.
5. Consistency signal computation.
6. Deterministic output for identical inputs.
"""

import importlib.util
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SCRIPT = _REPO_ROOT / "scripts" / "inspect_reference_mcp.py"
_spec = importlib.util.spec_from_file_location("inspect_reference_mcp", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

inspect_reference_mcp = _mod.inspect_reference_mcp


def _write_reference_fixture(root: Path):
    (root / "pkg" / "github").mkdir(parents=True, exist_ok=True)
    (root / "internal" / "ghmcp").mkdir(parents=True, exist_ok=True)
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "e2e").mkdir(parents=True, exist_ok=True)

    (root / "server.json").write_text(
        json.dumps(
            {
                "$schema": "https://example.com/server.schema.json",
                "name": "example/reference-mcp",
                "title": "Example",
                "description": "Example reference MCP",
                "repository": {
                    "url": "https://example.com/repo",
                    "source": "github",
                },
                "version": "0.1.0",
                "packages": [
                    {
                        "transport": {"type": "stdio"},
                    }
                ],
                "remotes": [
                    {
                        "type": "streamable-http",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    (root / "pkg" / "github" / "tools.go").write_text(
        '''package github

var (
    ToolsetMetadataAll = inventory.ToolsetMetadata{
        ID:          "all",
        Description: "all",
    }
    ToolsetMetadataDefault = inventory.ToolsetMetadata{
        ID:          "default",
        Description: "default",
    }
    ToolsetMetadataContext = inventory.ToolsetMetadata{
        ID:          "context",
        Description: "context",
        Default:     true,
    }
    ToolsetMetadataRepos = inventory.ToolsetMetadata{
        ID:          "repos",
        Description: "repos",
        Default:     true,
    }
    ToolsetMetadataCopilotSpaces = inventory.ToolsetMetadata{
        ID:          "copilot_spaces",
        Description: "copilot spaces",
    }
)

func AllTools(t any) []inventory.ServerTool {
    return []inventory.ServerTool{
        GetMe(t),
        CreatePullRequest(t),
    }
}

func RemoteOnlyToolsets() []inventory.ToolsetMetadata {
    return []inventory.ToolsetMetadata{
        ToolsetMetadataCopilotSpaces,
    }
}
''',
        encoding="utf-8",
    )

    (root / "README.md").write_text(
        '''# Example

Default toolsets: `context`, `repos`

### Available Toolsets

- `context`
- `repos`
- `copilot_spaces`
- `all`
- `default`

## Tools

- **get_me** - Get current user
- **create_pull_request** - Create a pull request
- **get_copilot_space** - Get copilot space
''',
        encoding="utf-8",
    )

    (root / "docs" / "server-configuration.md").write_text(
        '''# Server Configuration

Supports `--toolsets`, `--tools`, `--exclude-tools`, and `--dynamic-toolsets`.
''',
        encoding="utf-8",
    )

    (root / "pkg" / "github" / "server.go").write_text(
        '''package github

type MCPServerConfig struct {
    EnabledTools []string
    EnabledFeatures []string
    DynamicToolsets bool
    ReadOnly bool
    ExcludeTools []string
    TokenScopes []string
    LockdownMode bool
}

type FeatureFlags struct {
    LockdownMode bool
}
''',
        encoding="utf-8",
    )

    (root / "internal" / "ghmcp" / "server.go").write_text(
        '''package ghmcp

type StdioServerConfig struct {
    EnabledTools []string
    EnabledFeatures []string
    DynamicToolsets bool
    ReadOnly bool
    ExcludeTools []string
    LockdownMode bool
}
''',
        encoding="utf-8",
    )

    (root / "pkg" / "github" / "server_test.go").write_text(
        "package github\n",
        encoding="utf-8",
    )
    (root / "e2e" / "e2e_test.go").write_text(
        "package e2e\n",
        encoding="utf-8",
    )


class TestInspectReferenceMCP:
    def test_descriptor_extraction(self, tmp_path):
        ref = tmp_path / "ref"
        _write_reference_fixture(ref)

        result = inspect_reference_mcp(ref)

        descriptor = result["descriptor"]
        assert descriptor["schema"] == "https://example.com/server.schema.json"
        assert descriptor["name"] == "example/reference-mcp"
        assert descriptor["title"] == "Example"
        assert descriptor["repository_url"] == "https://example.com/repo"
        assert descriptor["package_transports"] == ["stdio"]
        assert descriptor["remote_transports"] == ["streamable-http"]

    def test_testability_extraction(self, tmp_path):
        ref = tmp_path / "ref"
        _write_reference_fixture(ref)

        result = inspect_reference_mcp(ref)

        testability = result["testability"]
        assert testability["has_e2e_tests"] is True
        assert testability["has_server_tests"] is True
        assert testability["test_file_count"] == 2

    def test_tooling_extraction(self, tmp_path):
        ref = tmp_path / "ref"
        _write_reference_fixture(ref)

        result = inspect_reference_mcp(ref)

        tooling = result["tooling"]
        assert "context" in tooling["registered_toolsets"]
        assert "repos" in tooling["default_toolsets"]
        assert tooling["remote_only_toolsets"] == ["copilot_spaces"]
        assert tooling["registered_tool_functions"] == ["CreatePullRequest", "GetMe"]
        assert "context" in tooling["documented_toolsets"]
        assert "create_pull_request" in tooling["documented_tools"]

    def test_capability_extraction(self, tmp_path):
        ref = tmp_path / "ref"
        _write_reference_fixture(ref)

        result = inspect_reference_mcp(ref)

        capabilities = result["capabilities"]
        assert capabilities["supports_dynamic_toolsets"] is True
        assert capabilities["supports_explicit_tools"] is True
        assert capabilities["supports_exclude_tools"] is True
        assert capabilities["supports_read_only"] is True
        assert capabilities["supports_feature_flags"] is True
        assert capabilities["supports_scope_filtering"] is True
        assert capabilities["supports_lockdown_mode"] is True

    def test_consistency_signals(self, tmp_path):
        ref = tmp_path / "ref"
        _write_reference_fixture(ref)

        result = inspect_reference_mcp(ref)

        consistency = result["consistency"]
        assert consistency["documented_default_toolsets_match_registered_defaults"] is True
        assert consistency["documented_toolsets_cover_registered_toolsets"] is True
        assert consistency["documented_tools_present"] is True
        assert consistency["registered_tools_present"] is True

    def test_repeated_calls_identical(self, tmp_path):
        ref = tmp_path / "ref"
        _write_reference_fixture(ref)

        r1 = inspect_reference_mcp(ref)
        r2 = inspect_reference_mcp(ref)

        assert r1 == r2
