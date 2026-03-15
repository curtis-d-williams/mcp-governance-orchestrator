"""
Minimal MCP server stub.
"""

from fastmcp import FastMCP

{{tool_imports}}

mcp = FastMCP("{{name}}")

TOOLS = {{tools_json}}

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

