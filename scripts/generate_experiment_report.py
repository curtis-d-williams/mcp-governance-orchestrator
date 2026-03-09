# SPDX-License-Identifier: MIT
"""Generate deterministic human-readable experiment summaries.

Input:
    experiment_results.json        (required)
    policy_sweep_results.json      (optional)

Outputs:
    experiment_report.json
    experiment_report.md

Usage:
    python scripts/generate_experiment_report.py \\
        --experiment-results experiment_results.json \\
        [--policy-sweep policy_sweep_results.json] \\
        [--output-json experiment_report.json] \\
        [--output-md experiment_report.md]

v0.39: initial implementation. stdlib only.
"""

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

REPORT_VERSION = "0.39"

_DEFAULTS = {
    "output_json": "experiment_report.json",
    "output_md": "experiment_report.md",
}


def _load_json(path):
    """Load and return a JSON file as a dict."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _compute_stability(evaluation_summary):
    """Extract stability metrics from an evaluation_summary dict."""
    return {
        "envelope_count": evaluation_summary.get("envelope_count", 0),
        "identical": evaluation_summary.get("identical", True),
        "ordering_differences": evaluation_summary.get("ordering_differences", False),
    }


def _compute_action_consistency(evaluation_summary):
    """Compute action selection consistency metrics from an evaluation_summary dict.

    Returns a dict with:
      unique_action_sets  - number of distinct selected_actions tuples observed
      most_common_actions - list of actions from the most frequent selection;
                            tie-broken by ascending lexicographic order of the tuple.
    """
    runs = evaluation_summary.get("runs", [])
    action_tuples = [tuple(r.get("selected_actions", [])) for r in runs]
    counts: dict = {}
    for t in action_tuples:
        counts[t] = counts.get(t, 0) + 1
    unique_count = len(counts)
    # Deterministic ordering: highest count first, then lexicographically smallest tuple.
    candidates = sorted(counts.keys(), key=lambda t: (-counts[t], t))
    most_common = list(candidates[0]) if candidates else []
    return {
        "unique_action_sets": unique_count,
        "most_common_actions": most_common,
    }


def _compute_sweep_summary(sweep_data):
    """Summarize a policy_sweep_results dict into report-friendly form."""
    entries = sweep_data.get("entries", [])
    entry_summaries = []
    for entry in entries:
        ev = entry.get("evaluation_summary", {})
        consistency = _compute_action_consistency(ev)
        entry_summaries.append({
            "envelope_count": ev.get("envelope_count", 0),
            "identical": ev.get("identical", True),
            "most_common_actions": consistency["most_common_actions"],
            "name": entry.get("name", ""),
            "ordering_differences": ev.get("ordering_differences", False),
            "unique_action_sets": consistency["unique_action_sets"],
            "weights": entry.get("weights", {}),
        })
    return {
        "entries": entry_summaries,
        "sweep_count": sweep_data.get("sweep_count", len(entries)),
    }


def build_report(experiment_results, sweep_data=None):
    """Build the report dict from experiment_results and optional sweep_data.

    Args:
        experiment_results: dict loaded from experiment_results.json.
        sweep_data:         dict loaded from policy_sweep_results.json, or None.

    Returns:
        A deterministic report dict.
    """
    eval_summary = experiment_results.get("evaluation_summary", {})
    stability = _compute_stability(eval_summary)
    consistency = _compute_action_consistency(eval_summary)

    report = {
        "action_selection": consistency,
        "report_version": REPORT_VERSION,
        "run_count": experiment_results.get("run_count", 0),
        "stability": stability,
    }

    if sweep_data is not None:
        report["policy_sweep"] = _compute_sweep_summary(sweep_data)

    return report


def render_markdown(report):
    """Render a report dict to a deterministic markdown string.

    All values are drawn from *report* so that the markdown content is
    guaranteed to be consistent with the JSON output.
    """
    lines = []
    lines.append("# Experiment Report")
    lines.append("")
    lines.append(f"Report version: {report['report_version']}")
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Run count: {report['run_count']}")
    stability = report["stability"]
    lines.append(f"- Identical runs: {stability['identical']}")
    lines.append(f"- Ordering differences: {stability['ordering_differences']}")
    lines.append(f"- Envelope count: {stability['envelope_count']}")
    lines.append("")

    lines.append("## Action Selection Consistency")
    lines.append("")
    ac = report["action_selection"]
    lines.append(f"- Unique action sets: {ac['unique_action_sets']}")
    most_common = ac["most_common_actions"]
    if most_common:
        lines.append(f"- Most common actions: {', '.join(most_common)}")
    else:
        lines.append("- Most common actions: (none)")
    lines.append("")

    if "policy_sweep" in report:
        sweep = report["policy_sweep"]
        lines.append("## Policy Sweep Summary")
        lines.append("")
        lines.append(f"Sweep count: {sweep['sweep_count']}")
        lines.append("")
        lines.append("| Entry | Runs | Identical | Unique Sets | Most Common Actions |")
        lines.append("|-------|------|-----------|-------------|---------------------|")
        for entry in sweep["entries"]:
            name = entry["name"]
            runs = entry["envelope_count"]
            identical = entry["identical"]
            unique_sets = entry["unique_action_sets"]
            actions = (
                ", ".join(entry["most_common_actions"])
                if entry["most_common_actions"]
                else "(none)"
            )
            lines.append(f"| {name} | {runs} | {identical} | {unique_sets} | {actions} |")
        lines.append("")

    return "\n".join(lines) + "\n"


def generate_report(
    experiment_results_path,
    sweep_path=None,
    output_json_path=None,
    output_md_path=None,
):
    """Load inputs, build report, write JSON and Markdown outputs.

    Args:
        experiment_results_path: path to experiment_results.json.
        sweep_path:              path to policy_sweep_results.json, or None.
        output_json_path:        destination for report JSON
                                 (default: experiment_report.json).
        output_md_path:          destination for report Markdown
                                 (default: experiment_report.md).

    Returns:
        A dict with keys: report, json_path, md_path.
    """
    if output_json_path is None:
        output_json_path = _DEFAULTS["output_json"]
    if output_md_path is None:
        output_md_path = _DEFAULTS["output_md"]

    experiment_results = _load_json(experiment_results_path)
    sweep_data = _load_json(sweep_path) if sweep_path is not None else None

    report = build_report(experiment_results, sweep_data)

    json_path = Path(output_json_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    md_path = Path(output_md_path)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(report), encoding="utf-8")

    return {"json_path": str(json_path), "md_path": str(md_path), "report": report}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate experiment report from experiment results.",
        add_help=True,
    )
    parser.add_argument(
        "--experiment-results", required=True, metavar="FILE",
        help="Path to experiment_results.json.",
    )
    parser.add_argument(
        "--policy-sweep", default=None, metavar="FILE",
        help="Path to policy_sweep_results.json (optional).",
    )
    parser.add_argument(
        "--output-json", default=None, metavar="FILE",
        help="Destination for report JSON (default: experiment_report.json).",
    )
    parser.add_argument(
        "--output-md", default=None, metavar="FILE",
        help="Destination for report Markdown (default: experiment_report.md).",
    )
    args = parser.parse_args(argv)

    result = generate_report(
        experiment_results_path=args.experiment_results,
        sweep_path=args.policy_sweep,
        output_json_path=args.output_json,
        output_md_path=args.output_md,
    )
    sys.stdout.write(
        f"Report generated: {result['json_path']}, {result['md_path']}\n"
    )


if __name__ == "__main__":
    main()
