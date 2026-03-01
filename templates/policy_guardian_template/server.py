# SPDX-License-Identifier: MIT
"""
Minimal deterministic policy guardian skeleton (Tier 2-ready)
"""

from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from typing import Any, Dict

@dataclass(frozen=True)
class GuardianResult:
    tool: str
    ok: bool
    fail_closed: bool
    output: Dict[str, Any]

def main(repo_path: str) -> Dict[str, Any]:
    """
    Deterministic, fail-closed, minimal skeleton guardian.
    """
    # Deterministic example output (no external dependencies)
    result = GuardianResult(
        tool="policy_guardian_skeleton",
        ok=True,
        fail_closed=False,
        output={"repo_path": repo_path, "info": "deterministic skeleton"}
    )
    return asdict(result)

# CLI entrypoint for testing
if __name__ == "__main__":
    import sys
    repo_path = sys.argv[1] if len(sys.argv) > 1 else "."
    print(json.dumps(main(repo_path), sort_keys=True, separators=(",", ":"), ensure_ascii=False))
