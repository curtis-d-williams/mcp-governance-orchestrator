# SPDX-License-Identifier: MIT
"""Run a deterministic mapping-repair validation cycle.

Flow:
  1. Evaluate the current planner configuration.
  2. If risk is not low_risk, generate a mapping repair proposal.
  3. Extract/write the proposed override artifact.
  4. Re-evaluate the planner using the override.
  5. Write a single cycle report JSON.

This script does not mutate the default mapping. It only produces artifacts.
"""

import argparse
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

# Ensure repo root is importable when invoked as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.evaluate_planner_config import evaluate_planner_config
from scripts.propose_mapping_repair import propose_mapping_repair


def _default_override_output(output_path):
    out = Path(output_path)
    return str(out.with_name(out.stem + "_override.json"))


def run_mapping_repair_cycle(
    portfolio_state_path,
    ledger_path=None,
    policy_path=None,
    top_k=3,
    exploration_offset=0,
    output_path="mapping_repair_cycle.json",
    override_output_path=None,
):
    """Run baseline eval -> repair proposal -> repaired eval and write a report."""
    output_path = str(output_path)
    override_output_path = override_output_path or _default_override_output(output_path)

    with redirect_stdout(io.StringIO()):
        baseline = evaluate_planner_config(
            policy_path=policy_path,
            top_k=top_k,
            portfolio_state_path=portfolio_state_path,
            ledger_path=ledger_path,
            mapping_override_path=None,
            output_path=None,
            exploration_offset=exploration_offset,
        )

    result = {
        "inputs": {
            "portfolio_state": portfolio_state_path,
            "ledger": ledger_path,
            "policy": policy_path,
            "top_k": top_k,
            "exploration_offset": exploration_offset,
        },
        "baseline_evaluation": baseline,
        "repair_proposal": None,
        "override_artifact_path": None,
        "override_artifact": None,
        "repaired_evaluation": None,
        "repair_attempted": False,
        "repair_success": False,
        "status": "baseline_only",
    }

    if baseline.get("risk_level") == "low_risk":
        result["status"] = "already_low_risk"
    else:
        with redirect_stdout(io.StringIO()):
            proposal = propose_mapping_repair(
                policy_path=policy_path,
                portfolio_state_path=portfolio_state_path,
                ledger_path=ledger_path,
                top_k=top_k,
                exploration_offset=exploration_offset,
                output_path=None,
                output_override_path=None,
            )
        result["repair_proposal"] = proposal
        result["repair_attempted"] = True

        override = proposal.get("proposed_mapping_override", {})
        result["override_artifact"] = override

        if override:
            override_out = Path(override_output_path)
            override_out.parent.mkdir(parents=True, exist_ok=True)
            override_out.write_text(
                json.dumps(override, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            result["override_artifact_path"] = str(override_out)

            with redirect_stdout(io.StringIO()):
                repaired = evaluate_planner_config(
                    policy_path=policy_path,
                    top_k=top_k,
                    portfolio_state_path=portfolio_state_path,
                    ledger_path=ledger_path,
                    mapping_override_path=str(override_out),
                    output_path=None,
                    exploration_offset=exploration_offset,
                )
            result["repaired_evaluation"] = repaired

            baseline_collision = baseline.get("collision_ratio", 1.0)
            repaired_collision = repaired.get("collision_ratio", 1.0)
            baseline_unique = baseline.get("unique_tasks", 0)
            repaired_unique = repaired.get("unique_tasks", 0)

            improved = (
                repaired.get("risk_level") == "low_risk"
                or repaired_collision < baseline_collision
                or repaired_unique > baseline_unique
            )

            result["repair_success"] = bool(improved)
            result["status"] = "repair_validated" if improved else "repair_no_improvement"
        else:
            result["status"] = "repair_unavailable"

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run a deterministic planner mapping-repair validation cycle.",
        add_help=True,
    )
    parser.add_argument(
        "--portfolio-state",
        required=True,
        metavar="FILE",
        help="Path to portfolio_state.json.",
    )
    parser.add_argument(
        "--ledger",
        default=None,
        metavar="FILE",
        help="Path to action_effectiveness_ledger.json (optional).",
    )
    parser.add_argument(
        "--policy",
        default=None,
        metavar="FILE",
        help="Path to planner_policy.json (optional).",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        metavar="INT",
        help="Number of top actions to consider (default: 3).",
    )
    parser.add_argument(
        "--exploration-offset",
        type=int,
        default=0,
        metavar="INT",
        help="Start index into the action queue window (default: 0).",
    )
    parser.add_argument(
        "--output",
        default="mapping_repair_cycle.json",
        metavar="FILE",
        help="Write cycle report JSON to this path.",
    )
    parser.add_argument(
        "--override-output",
        default=None,
        metavar="FILE",
        help="Write the override-only JSON artifact to this path.",
    )
    args = parser.parse_args(argv)

    result = run_mapping_repair_cycle(
        portfolio_state_path=args.portfolio_state,
        ledger_path=args.ledger,
        policy_path=args.policy,
        top_k=args.top_k,
        exploration_offset=args.exploration_offset,
        output_path=args.output,
        override_output_path=args.override_output,
    )

    print(
        f"Repair cycle complete: status={result['status']}, "
        f"repair_success={result['repair_success']}, "
        f"output={args.output}"
    )


if __name__ == "__main__":
    main()
