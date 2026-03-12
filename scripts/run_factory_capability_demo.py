# SPDX-License-Identifier: MIT
"""
Factory Capability Demo

Demonstrates the MCP Automation Factory generating a new MCP server
when a capability gap is detected.
"""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PORTFOLIO_STATE = ROOT / "experiments" / "factory_demo" / "portfolio_state_missing_github.json"
LEDGER = ROOT / "experiments" / "factory_demo" / "action_effectiveness_ledger.json"
OUTPUT = ROOT / "experiments" / "factory_demo" / "factory_cycle_result.json"
GENERATED_REPO = ROOT / "generated_mcp_github"


def run_factory_cycle():
    cmd = [
        "python3",
        "scripts/run_autonomous_factory_cycle.py",
        "--portfolio-state",
        str(PORTFOLIO_STATE),
        "--ledger",
        str(LEDGER),
        "--top-k",
        "3",
        "--output",
        str(OUTPUT),
    ]

    subprocess.run(cmd, check=True)


def verify_generated_repo():
    if not GENERATED_REPO.exists():
        raise RuntimeError("Factory did not generate MCP server")

    expected_files = [
        "README.md",
        "manifest.json",
        "server.py",
        "tools/list_repositories.py",
        "tools/get_repository.py",
        "tools/create_issue.py",
        "tests/test_server_smoke.py",
    ]

    for rel in expected_files:
        p = GENERATED_REPO / rel
        if not p.exists():
            raise RuntimeError(f"Missing expected file: {p}")


def verify_factory_artifact():
    data = json.loads(OUTPUT.read_text())

    builder = data["cycle_result"].get("builder")
    if not builder:
        raise RuntimeError("Factory artifact missing builder output")

    if builder["status"] != "ok":
        raise RuntimeError("Builder reported failure")


def main():
    print("Running MCP Capability Factory demo...")

    run_factory_cycle()

    verify_generated_repo()
    verify_factory_artifact()

    print("Factory demo succeeded.")
    print(f"MCP server generated at: {GENERATED_REPO}")


if __name__ == "__main__":
    main()
