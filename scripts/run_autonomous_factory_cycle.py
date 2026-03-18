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


# ---------------------------------------------------------------------
# Repo path bootstrap
# ---------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from factory_pipeline import decide_action as _pipeline_decide_action
from factory_pipeline import run_factory_cycle


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
_cap_learn_mod = _load(
    _SCRIPT_DIR / "update_capability_effectiveness_ledger.py",
    "capability_learn",
)
_cap_artifact_mod = _load(
    _SCRIPT_DIR / "update_capability_artifact_registry.py",
    "capability_artifact_registry",
)

run_governed_loop = _governed_mod.run_governed_loop
run_mapping_repair_cycle = _repair_mod.run_mapping_repair_cycle
update_action_effectiveness_ledger = _learn_mod.update_action_effectiveness_ledger
update_capability_effectiveness_ledger = (
    _cap_learn_mod.update_capability_effectiveness_ledger
)
update_capability_artifact_registry = (
    _cap_artifact_mod.update_capability_artifact_registry
)


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
    capability_ledger=None,
    capability_ledger_output=None,
    capability_artifact_registry_output=None,
    policy=None,
    top_k=3,
    output="autonomous_factory_cycle.json",
):
    """
    Run a single autonomous factory cycle.
    """
    artifact = run_factory_cycle(
        portfolio_state=portfolio_state,
        ledger=ledger,
        capability_ledger=capability_ledger,
        policy=policy,
        top_k=top_k,
        output=output,
        evaluate_planner_config=evaluate_planner_config,
        run_mapping_repair_cycle=run_mapping_repair_cycle,
        run_governed_loop=run_governed_loop,
    )

    if capability_ledger_output or capability_ledger:
        update_capability_effectiveness_ledger(
            ledger_path=capability_ledger or capability_ledger_output,
            cycle_artifact_path=output,
            output_path=capability_ledger_output,
        )

    if capability_artifact_registry_output:
        update_capability_artifact_registry(
            registry_path=capability_artifact_registry_output,
            cycle_artifact_path=output,
        )

    # Post-cycle write-back: remove fulfilled capability gap from portfolio state
    try:
        cycle_result = artifact.get("cycle_result", {}) if isinstance(artifact, dict) else {}
        synthesis_source = cycle_result.get("synthesis_source")
        synthesis_status = cycle_result.get("synthesis_event", {}).get("status")
        if synthesis_source == "portfolio_gap" and synthesis_status == "ok":
            import json as _json
            ps_path = Path(portfolio_state)
            if ps_path.exists():
                ps_data = _json.loads(ps_path.read_text(encoding="utf-8"))
                if isinstance(ps_data, dict) and "capability_gaps" in ps_data:
                    fulfilled = cycle_result.get("synthesis_event", {}).get("capability")
                    if fulfilled and fulfilled in ps_data["capability_gaps"]:
                        ps_data["capability_gaps"].remove(fulfilled)
                        ps_path.write_text(
                            _json.dumps(ps_data, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8",
                        )
    except Exception:
        pass

    return artifact


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(description="Run autonomous MCP factory cycle.")
    parser.add_argument("--portfolio-state", required=True)
    parser.add_argument("--ledger")
    parser.add_argument("--capability-ledger")
    parser.add_argument("--capability-ledger-output")
    parser.add_argument("--policy")
    parser.add_argument("--capability-artifact-registry-output")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--output", default="autonomous_factory_cycle.json")

    args = parser.parse_args(argv)

    artifact = run_autonomous_factory_cycle(
        portfolio_state=args.portfolio_state,
        ledger=args.ledger,
        capability_ledger=args.capability_ledger,
        capability_ledger_output=args.capability_ledger_output,
        capability_artifact_registry_output=args.capability_artifact_registry_output,
        policy=args.policy,
        top_k=args.top_k,
        output=args.output,
    )

    print("Factory cycle completed:", artifact["decision"]["action"])


if __name__ == "__main__":
    main()
