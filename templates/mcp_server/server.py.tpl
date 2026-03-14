"""
Minimal MCP server stub.
"""

from tools.list_repositories import list_repositories as _list_repositories
from tools.get_repository import get_repository as _get_repository
from tools.create_issue import create_issue as _create_issue

TOOLS = {{tools_json}}

def list_tools():
    return TOOLS

def list_repositories():
    return _list_repositories()

def get_repository():
    return _get_repository()

def create_issue():
    return _create_issue()
