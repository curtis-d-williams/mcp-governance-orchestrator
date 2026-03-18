# SPDX-License-Identifier: MIT
"""Deterministic MCP server generation entrypoint.

Thin wrapper over the canonical governed autonomous capability factory
MCP builder. This script exists as a developer-facing convenience layer
and does not duplicate generation logic.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from builder.mcp_builder import build_mcp_server


def main():
    parser = argparse.ArgumentParser(
        description="Generate a deterministic MCP server from the canonical builder"
    )
    parser.add_argument(
        "--name",
        default="generated_mcp_server_github",
        help="Output repository directory name",
    )
    parser.add_argument(
        "--capability",
        default="github_repository_management",
        help="Capability spec key to generate",
    )
    parser.add_argument(
        "--tools",
        nargs="*",
        default=None,
        help="Optional explicit tool list override",
    )

    args = parser.parse_args()

    result = build_mcp_server(
        name=args.name,
        capability=args.capability,
        tools=args.tools,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
