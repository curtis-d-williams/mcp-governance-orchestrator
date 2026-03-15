"""
Minimal MCP server stub.
"""

from fastmcp import FastMCP

try:
    from .tools.list_repositories import list_repositories as _list_repositories
    from .tools.get_repository import get_repository as _get_repository
    from .tools.create_issue import create_issue as _create_issue
except ImportError:
    from tools.list_repositories import list_repositories as _list_repositories
    from tools.get_repository import get_repository as _get_repository
    from tools.create_issue import create_issue as _create_issue

mcp = FastMCP("generated_mcp_server_github")

TOOLS = {
  "list_repositories": {},
  "get_repository": {
    "params": [
      "repo"
    ]
  },
  "create_issue": {
    "params": [
      "repo",
      "title",
      "body"
    ]
  }
}

def list_tools():
    return TOOLS

@mcp.tool()
def list_tools_tool():
    return list_tools()

@mcp.tool()
def list_repositories():
    return _list_repositories()

@mcp.tool()
def get_repository(repo: str):
    return _get_repository(repo)

@mcp.tool()
def create_issue(repo: str, title: str, body: str):
    return _create_issue(repo, title, body)

def main():
    mcp.run()

if __name__ == "__main__":
    main()
