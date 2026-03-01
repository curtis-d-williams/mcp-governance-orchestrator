# SPDX-License-Identifier: MIT
"""
mcp-governance-orchestrator

Public API surface is intentionally minimal and deterministic.
"""

from .server import run_guardians  # re-export stable deterministic core

__all__ = ["run_guardians"]
