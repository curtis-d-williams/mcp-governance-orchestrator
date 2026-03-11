# SPDX-License-Identifier: MIT
"""
Autonomous MCP factory cycle controller.

This layer decides which orchestrator capability to run based on
current portfolio conditions and planner risk.

Capabilities used:
    run_governed_planner_loop
    run_mapping_repair_cycle
    update_action_effectiveness_ledger
"""

import argparse
import importlib.util
import sys
from pathlib import Path

from factory_pipeline import decide_action as _pipeline_decide_action
from factory_pipeline import run_factory_cycle


# ---------------------------------------------------------------------
# Repo path bootstrap
# ---------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# ---------------------------------------------------------------------
# Dynamic imports (same pattern used elsewhere)
# ---------------------------------------------------------------------

def _load(script, name):
    spec = importlib.util.spec_from_file_location(name, script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_SCRIPT_DIR = Path(__file__).resolve().parent

_governed_mod = _load(_SCRIPT_DIR / "run_governed_planner_loop.py", "governed")
_repair_mod = _load(_SCRIPT_DIR / "run_mapping_repair_cycle.py", "repair")
_learn_mod = _load(_SCRIPT_DIR / "update_action_effectiveness_ledger.py", "learn")

run_governed_loop = _governed_mod.run_governed_loop
run_mapping_repair_cycle = _repair_mod.run_mapping_repair_cycle
update_action_effectiveness_ledger = _learn_mod.update_action_effectiveness_ledger


# ---------------------------------------------------------------------
# Planner preflight helper
# ---------------------------------------------------------------------

_eval_mod = _load(_SCRIPT_DIR / "evaluate_planner_config.py", "eval")
evaluate_planner_config = _eval_mod.evaluate_planner_config


# ---------------------------------------------------------------------
# Policy engine
# ---------------------------------------------------------------------

def _decide_action(evaluation):
    """Backward-compatible wrapper around factory_pipeline.decide_action."""
    return _pipeline_decide_action(evaluation)


# ---------------------------------------------------------------------
# Core factory cycle
# ---------------------------------------------------------------------

def run_autonomous_factory_cycle(
    portfolio_state,
    ledger=None,
    policy=None,
    top_k=3,
    output="autonomous_factory_cycle.json",
):
    """
    Run a single autonomous factory cycle.
    """
    return run_factory_cycle(
        portfolio_state=portfolio_state,
        ledger=ledger,
        policy=policy,
        top_k=top_k,
        output=output,
        evaluate_planner_config=evaluate_planner_config,
        run_mapping_repair_cycle=run_mapping_repair_cycle,
        run_governed_loop=run_governed_loop,
    )


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(description="Run autonomous MCP factory cycle.")
    parser.add_argument("--portfolio-state", required=True)
    parser.add_argument("--ledger")
    parser.add_argument("--policy")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--output", default="autonomous_factory_cycle.json")

    args = parser.parse_args(argv)

    artifact = run_autonomous_factory_cycle(
        portfolio_state=args.portfolio_state,
        ledger=args.ledger,
        policy=args.policy,
        top_k=args.top_k,
        output=args.output,
    )

    print("Factory cycle completed:", artifact["decision"]["action"])


if __name__ == "__main__":
    main()
