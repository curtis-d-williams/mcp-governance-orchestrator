from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from fastmcp import FastMCP

mcp = FastMCP("mcp-governance-orchestrator")


# ---- Deterministic error codes (V0) ----
ERR_GUARDIANS_EMPTY = "fail-closed: guardians_empty"
ERR_GUARDIAN_UNKNOWN = "fail-closed: guardian_unknown"
ERR_REPO_PATH_INVALID = "fail-closed: repo_path_invalid"


# ---- Guardian routing (V0, local-only, deterministic) ----
# NOTE: V0 is design-first. Implementations may be stubbed until real integration exists.
# These IDs are *selectors* only. Unknown IDs must fail-closed.
KNOWN_GUARDIANS = {
    # Intentionally start with placeholders. Concrete wiring comes later.
    "mcp-policy-guardian:v1",
    "mcp-release-guardian:v1",
}


@dataclass(frozen=True)
class GuardianResult:
    guardian_id: str
    invoked: bool
    ok: bool
    fail_closed: bool
    output: Optional[Dict[str, Any]]
    details: str


def _fail_guardian(guardian_id: str, details: str) -> GuardianResult:
    return GuardianResult(
        guardian_id=guardian_id,
        invoked=False,
        ok=False,
        fail_closed=True,
        output=None,
        details=details,
    )


def _repo_path_is_valid(repo_path: str) -> bool:
    # V0: do not touch filesystem beyond validating input shape.
    # True filesystem validation can be added only if explicitly allowed by contract later.
    return isinstance(repo_path, str) and len(repo_path.strip()) > 0


def run_guardians(repo_path: str, guardians: List[str]) -> Dict[str, Any]:
    """
    Guardian Orchestrator (V0): design-only aggregation.
    - Deterministic
    - Fail-closed
    - No interpretation
    - Preserves guardian outputs verbatim (when invoked)
    """
    # Orchestrator-level validation (fail-closed)
    if not _repo_path_is_valid(repo_path):
        return {
            "tool": "run_guardians",
            "repo_path": repo_path,
            "ok": False,
            "fail_closed": True,
            "guardians": [],
        }

    if not isinstance(guardians, list) or len(guardians) == 0:
        return {
            "tool": "run_guardians",
            "repo_path": repo_path,
            "ok": False,
            "fail_closed": True,
            "guardians": [
                {
                    "guardian_id": "",
                    "invoked": False,
                    "ok": False,
                    "fail_closed": True,
                    "output": None,
                    "details": ERR_GUARDIANS_EMPTY,
                }
            ],
        }

    results: List[GuardianResult] = []

    # Preserve input order; no sorting.
    for gid in guardians:
        if gid not in KNOWN_GUARDIANS:
            results.append(_fail_guardian(gid, ERR_GUARDIAN_UNKNOWN))
            continue

        # V0 wiring is stubbed: we *do not* invoke external MCPs yet.
        # This keeps the orchestrator deterministic and network-free.
        results.append(
            GuardianResult(
                guardian_id=gid,
                invoked=False,
                ok=False,
                fail_closed=True,
                output=None,
                details="fail-closed: guardian_not_wired",
            )
        )

    ok = all(r.ok for r in results) if results else False
    fail_closed = (not ok) or any(r.fail_closed for r in results)

    return {
        "tool": "run_guardians",
        "repo_path": repo_path,
        "ok": ok,
        "fail_closed": fail_closed,
        "guardians": [
            {
                "guardian_id": r.guardian_id,
                "invoked": r.invoked,
                "ok": r.ok,
                "fail_closed": r.fail_closed,
                "output": r.output,
                "details": r.details,
            }
            for r in results
        ],
    }


# MCP tool registration
@mcp.tool()
def run_guardians_tool(repo_path: str, guardians: List[str]) -> Dict[str, Any]:
    return run_guardians(repo_path=repo_path, guardians=guardians)


def main() -> None:
    mcp.run()