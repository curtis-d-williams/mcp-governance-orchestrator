# tests/test_schema_aware_tools.py

import pytest
pytest.importorskip("generated_mcp_server_github", reason="generated_mcp_server_github not present — run factory pipeline first")
from generated_mcp_server_github.server import list_repositories, get_repository, create_issue

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
