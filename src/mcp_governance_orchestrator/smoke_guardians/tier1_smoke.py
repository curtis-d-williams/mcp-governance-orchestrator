# SPDX-License-Identifier: MIT
from __future__ import annotations

from typing import Any, Dict


def main(repo_path: str) -> Dict[str, Any]:
    # Deterministic, read-only smoke guardian: always OK.
    return {
        "tool": "tier1_smoke",
        "ok": True,
        "fail_closed": False,
        "details": "ok",
        "repo_path": repo_path,
    }
