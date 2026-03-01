from __future__ import annotations

from .guardian_registry import register_guardian
from typing import List, Dict, Any

# ---------------------------
# Tier 3 Registration
# ---------------------------
register_guardian(
    guardian_id="intelligence_layer_template:v1",
    module_path="templates.intelligence_layer_template.server",
    description="Tier 3 intelligence layer template - suggestion-only, deterministic"
)

# ---------------------------
# Existing server.py functions
# ---------------------------

def _resolve_guardian_callable(guardian_id: str):
    # Placeholder: actual implementation from original server.py
    pass

def _fail_guardian(guardian_id: str, details: str) -> Dict[str, Any]:
    # Placeholder: actual implementation from original server.py
    return {"guardian_id": guardian_id, "fail_closed": True, "details": details, "ok": False, "invoked": False, "output": None}

def _repo_path_is_valid(repo_path: str) -> bool:
    # Placeholder: actual implementation from original server.py
    return True

def run_guardians(repo_path: str, guardians: List[str]) -> Dict[str, Any]:
    results = []
    for gid in guardians:
        # Attempt to resolve guardian
        try:
            _resolve_guardian_callable(gid)
            results.append({
                "guardian_id": gid,
                "ok": True,
                "fail_closed": False,
                "invoked": True,
                "output": {}  # Placeholder for deterministic output
            })
        except Exception:
            results.append(_fail_guardian(gid, "guardian_unknown"))
    policy_ok = all(g["ok"] for g in results)
    policy_fail_closed = any(g["fail_closed"] for g in results)
    return {
        "ok": policy_ok,
        "fail_closed": policy_fail_closed,
        "repo_path": repo_path,
        "guardians": results,
        "tool": "run_guardians"
    }

def run_guardians_tool(repo_path: str, guardians: List[str]) -> Dict[str, Any]:
    return run_guardians(repo_path, guardians)

def main() -> None:
    import sys
    out = run_guardians(sys.argv[1:], [])
    print(out)

