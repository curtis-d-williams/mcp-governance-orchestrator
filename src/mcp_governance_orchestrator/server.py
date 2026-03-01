from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from fastmcp import FastMCP

mcp = FastMCP("mcp-governance-orchestrator")


# ---- Deterministic error codes ----
ERR_GUARDIANS_EMPTY = "fail-closed: guardians_empty"
ERR_GUARDIAN_UNKNOWN = "fail-closed: guardian_unknown"
ERR_REPO_PATH_INVALID = "fail-closed: repo_path_invalid"
ERR_GUARDIAN_IMPORT_FAILED = "fail-closed: guardian_import_failed"
ERR_GUARDIAN_CALL_FAILED = "fail-closed: guardian_call_failed"
ERR_GUARDIAN_OUTPUT_INVALID = "fail-closed: guardian_output_invalid"


# ---- Guardian routing (V1, in-process static table) ----
# Maps guardian_id -> (module_path, callable_name).
# Invocation: callable(repo_path). Unknown IDs fail-closed without import.
GUARDIAN_ROUTING_TABLE: Dict[str, tuple] = {
    "mcp-policy-guardian:v1": ("mcp_policy_guardian", "check_repo_policy"),
    # check_repo_release is the anticipated callable; update when package is published.
    "mcp-release-guardian:v1": ("mcp_release_guardian.server", "check_repo_hygiene"),
    "mcp-repo-hygiene-guardian:v1": ("mcp_repo_hygiene_guardian.server", "check_repo_hygiene"),
}

# Derived from routing table; preserved for fast membership tests.
KNOWN_GUARDIANS = set(GUARDIAN_ROUTING_TABLE.keys())

# Sentinel: _resolve_guardian_callable returns this when guardian_id is not
# in GUARDIAN_ROUTING_TABLE (distinct from None, which signals an import error).
_SENTINEL_NOT_MAPPED = object()


def _resolve_guardian_callable(guardian_id: str):
    """Return (callable, None) on success.
    Return (_SENTINEL_NOT_MAPPED, None) if not in routing table.
    Return (None, ERR_GUARDIAN_IMPORT_FAILED) if import/getattr/callable check fails.
    Does not import anything for unmapped IDs.
    """
    if guardian_id not in GUARDIAN_ROUTING_TABLE:
        return _SENTINEL_NOT_MAPPED, None
    module_path, callable_name = GUARDIAN_ROUTING_TABLE[guardian_id]
    try:
        module = importlib.import_module(module_path)
        fn = getattr(module, callable_name)
        if not callable(fn):
            raise TypeError(f"{callable_name!r} is not callable")
        return fn, None
    except Exception:
        return None, ERR_GUARDIAN_IMPORT_FAILED


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

        fn, import_err = _resolve_guardian_callable(gid)

        if fn is _SENTINEL_NOT_MAPPED:
            # Routing table and KNOWN_GUARDIANS are out of sync; fail-closed.
            results.append(_fail_guardian(gid, ERR_GUARDIAN_UNKNOWN))
            continue

        if fn is None:
            results.append(_fail_guardian(gid, import_err))  # type: ignore[arg-type]
            continue

        try:
            raw_output = fn(repo_path)  # type: ignore[operator]
        except Exception:
            results.append(_fail_guardian(gid, ERR_GUARDIAN_CALL_FAILED))
            continue

        # Output must be a dict containing key "tool"; no further interpretation.
        if not isinstance(raw_output, dict) or "tool" not in raw_output:
            results.append(_fail_guardian(gid, ERR_GUARDIAN_OUTPUT_INVALID))
            continue

        # Invocation and validation succeeded.
        # Tier 2 semantics require propagating guardian ok/fail_closed (booleans).
        g_ok = raw_output.get("ok")
        g_fail_closed = raw_output.get("fail_closed")
        if not isinstance(g_ok, bool) or not isinstance(g_fail_closed, bool):
            results.append(_fail_guardian(gid, ERR_GUARDIAN_OUTPUT_INVALID))
            continue

        results.append(
            GuardianResult(
                guardian_id=gid,
                invoked=True,
                ok=g_ok,
                fail_closed=g_fail_closed,
                output=raw_output,  # verbatim, no normalization
                details="",
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