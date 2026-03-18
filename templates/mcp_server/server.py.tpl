"""
Minimal MCP server stub.
"""

from fastmcp import FastMCP

try:
{{tool_imports}}
except ImportError:
{{tool_imports_fallback}}

mcp = FastMCP("{{name}}")

TOOLS = {{tools_json}}
ENABLED_FEATURES = {{features_json}}

def list_tools():
    return TOOLS

@mcp.tool()
def list_tools_tool():
    return list_tools()

{{tool_wrappers}}

def main():
    mcp.run()

if __name__ == "__main__":
    main()

