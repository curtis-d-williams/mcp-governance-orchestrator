# tests/test_schema_aware_tools.py

import pytest
pytest.importorskip("generated_mcp_server_github", reason="generated_mcp_server_github not present — run factory pipeline first")
from generated_mcp_server_github.tools.list_repositories import list_repositories
from generated_mcp_server_github.tools.get_repository import get_repository
from generated_mcp_server_github.tools.create_issue import create_issue

def test_list_repositories():
    """Test zero-argument tool."""
    result = list_repositories()
    print("list_repositories output:", result)

def test_get_repository():
    """Test single-parameter tool."""
    result = get_repository("example-repo")
    print("get_repository output:", result)

def test_create_issue():
    """Test three-parameter tool."""
    result = create_issue("example-repo", "Test Issue", "This is a test")
    print("create_issue output:", result)

if __name__ == "__main__":
    test_list_repositories()
    test_get_repository()
    test_create_issue()
