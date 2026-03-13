# SPDX-License-Identifier: MIT
"""Regression tests for scripts/compare_mcp_servers.py.

Covers:
1. Tool surface comparison against normalized reference inspection.
2. Structural comparison against normalized reference descriptor.
3. Capability surface comparison.
4. Testability comparison.
5. Deterministic output for identical inputs.
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

_SCRIPT = _REPO_ROOT / "scripts" / "compare_mcp_servers.py"
_spec = importlib.util.spec_from_file_location("compare_mcp_servers", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

compare_mcp_servers = _mod.compare_mcp_servers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_generated_repo(root, name, capability, tools):
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "name": name,
                "capability": capability,
                "protocol": "model-context-protocol",
                "version": "0.1.0",
                "tools": tools,
            }
        ),
        encoding="utf-8",
    )


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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestToolSurfaceComparison:

    def test_matching_tools(self, tmp_path):
        gen = tmp_path / "gen"
        ref = tmp_path / "ref"

        _write_generated_repo(gen, "gen", "cap", ["get_me", "create_pull_request"])
        _write_reference_fixture(ref)

        result = compare_mcp_servers(gen, ref)

        ts = result["tool_surface"]
        assert ts["matching_tool_count"] == 2
        assert ts["coverage_ratio"] == 2 / 3
        assert ts["missing_tools"] == ["get_copilot_space"]
        assert ts["extra_tools"] == []

    def test_missing_and_extra_tools(self, tmp_path):
        gen = tmp_path / "gen"
        ref = tmp_path / "ref"

        _write_generated_repo(gen, "gen", "cap", ["get_me", "extra_tool"])
        _write_reference_fixture(ref)

        result = compare_mcp_servers(gen, ref)

        ts = result["tool_surface"]
        assert ts["matching_tools"] == ["get_me"]
        assert ts["missing_tools"] == ["create_pull_request", "get_copilot_space"]
        assert ts["extra_tools"] == ["extra_tool"]


class TestStructureComparison:

    def test_protocol_and_version_comparison(self, tmp_path):
        gen = tmp_path / "gen"
        ref = tmp_path / "ref"

        _write_generated_repo(gen, "gen", "github_repository_management", ["get_me"])
        _write_reference_fixture(ref)

        result = compare_mcp_servers(gen, ref)

        structure = result["structure"]
        assert structure["protocol_match"] is True
        assert structure["capability_declared"] is True
        assert structure["version_match"] is True
        assert structure["reference_transports"] == ["stdio", "streamable-http"]

    def test_generated_version_mismatch(self, tmp_path):
        gen = tmp_path / "gen"
        ref = tmp_path / "ref"

        _write_generated_repo(gen, "gen", "cap", ["get_me"])
        _write_reference_fixture(ref)

        manifest = json.loads((gen / "manifest.json").read_text(encoding="utf-8"))
        manifest["version"] = "9.9.9"
        (gen / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        result = compare_mcp_servers(gen, ref)
        assert result["structure"]["version_match"] is False


class TestCapabilitySurface:

    def test_capability_coverage(self, tmp_path):
        gen = tmp_path / "gen"
        ref = tmp_path / "ref"

        _write_generated_repo(gen, "gen", "cap", ["get_me"])
        _write_reference_fixture(ref)

        result = compare_mcp_servers(gen, ref)

        caps = result["capability_surface"]
        assert caps["generated"]["supports_explicit_tools"] is True
        assert caps["reference"]["supports_dynamic_toolsets"] is True
        assert "supports_explicit_tools" in caps["matching_enabled"]
        assert "supports_dynamic_toolsets" in caps["missing_enabled"]


class TestTestSurface:

    def test_detects_tests(self, tmp_path):
        gen = tmp_path / "gen"
        ref = tmp_path / "ref"

        _write_generated_repo(gen, "gen", "cap", ["get_me"])
        _write_reference_fixture(ref)

        tests_dir = gen / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_example.py").write_text("def test_x(): pass")

        result = compare_mcp_servers(gen, ref)

        gen_tests = result["testability"]["generated"]
        assert gen_tests["has_tests"] is True
        assert gen_tests["test_file_count"] == 1
        assert result["testability"]["reference"]["test_file_count"] == 2


class TestDeterminism:

    def test_repeated_calls_identical(self, tmp_path):
        gen = tmp_path / "gen"
        ref = tmp_path / "ref"

        _write_generated_repo(gen, "gen", "cap", ["get_me", "create_pull_request"])
        _write_reference_fixture(ref)

        r1 = compare_mcp_servers(gen, ref)
        r2 = compare_mcp_servers(gen, ref)

        assert r1 == r2
