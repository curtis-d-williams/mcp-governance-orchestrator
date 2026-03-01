# orchestrator_helper.py
# Purpose: deterministic, automation-ready wrapper for running guardians
from typing import List, Dict, Any
import json
import sys
import os

# Ensure src layout is included if needed (for dev environments)
repo_root = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(repo_root, "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# Canonical import of the orchestrator API
from mcp_governance_orchestrator.server import run_guardians

def run_portfolio_guardians(guardian_list: List[str], repo_path: str = ".") -> Dict[str, Any]:
    """
    Run a deterministic set of guardians across the given repo path.

    Args:
        guardian_list: List of guardian identifiers (e.g., ["mcp-repo-hygiene-guardian:v1"])
        repo_path: Root path of the repo to check

    Returns:
        Canonical JSON-compliant dictionary with guardian results
    """
    return run_guardians(
        guardians=guardian_list,
        repo_path=repo_path
    )

if __name__ == "__main__":
    # Example usage: run all portfolio guardians and print canonical JSON
    repos = [
        "mcp-repo-hygiene-guardian:v1",
        "mcp-release-guardian:v1",
    ]
    out = run_portfolio_guardians(repos)
    print(json.dumps(out, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
