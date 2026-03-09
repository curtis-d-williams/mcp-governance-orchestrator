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
v0.40: add total_action_task_collapse_count to action_selection aggregation.
v0.41: add selected_action_count, unique_selected_task_count, task_diversity_ratio
       to action_selection (additive — no existing keys removed or renamed).
v0.42: add collision_ratio = total_action_task_collapse_count / total_window_size
       to action_selection (additive).
v0.43: add task_entropy and action_entropy (Shannon entropy in bits) to
       action_selection (additive — no existing keys removed or renamed).
"""

import argparse
import json
import math
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

REPORT_VERSION = "0.43"

_DEFAULTS = {
    "output_json": "experiment_report.json",
    "output_md": "experiment_report.md",
}


def _load_json(path):
    """Load and return a JSON file as a dict."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _entropy(counts):
    """Compute Shannon entropy in bits from a label-frequency dict.

    Args:
        counts: dict mapping str labels to non-negative integer counts.

    Returns:
        Entropy in bits (float), rounded to 6 decimal places.
        Returns 0.0 when counts is empty or all counts are zero.

    Keys are iterated in sorted order for deterministic float accumulation.
    """
    total = sum(counts.values())
    if total == 0:
        return 0.0
    h = 0.0
    for key in sorted(counts):
        p = counts[key] / total
        if p > 0:
            h -= p * math.log2(p)
    return round(h, 6)


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
      unique_action_sets             - number of distinct selected_actions tuples observed
      most_common_actions            - list of actions from the most frequent selection;
                                       tie-broken by ascending lexicographic order of the tuple.
      total_action_task_collapse_count - sum of action_task_collapse_count across all runs
                                       that carry selection_detail.  0 when no runs have it.
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
    total_collapse = sum(
        r.get("selection_detail", {}).get("action_task_collapse_count", 0)
        for r in runs
    )
    # v0.41: selected_action_count, unique_selected_task_count, task_diversity_ratio
    selected_action_count = sum(r.get("selection_count", 0) for r in runs)
    unique_task_names = set(
        task
        for r in runs
        for task in r.get("selected_actions", [])
    )
    unique_selected_task_count = len(unique_task_names)
    diversity_values = []
    for r in runs:
        sel = r.get("selection_count", 0)
        collapse = r.get("selection_detail", {}).get("action_task_collapse_count", 0)
        window = sel + collapse
        diversity_values.append(sel / window if window > 0 else 0.0)
    task_diversity_ratio = (
        round(sum(diversity_values) / len(diversity_values), 6)
        if diversity_values else 0.0
    )
    # v0.42: collision_ratio = total collapse / total window size across all runs
    total_window = sum(
        len(r.get("selection_detail", {}).get("ranked_action_window", []))
        for r in runs
    )
    collision_ratio = round(total_collapse / total_window, 6) if total_window > 0 else 0.0
    # v0.43: task_entropy — Shannon entropy over selected task distribution
    task_counts: dict = {}
    for r in runs:
        for task in r.get("selected_actions", []):
            task_counts[task] = task_counts.get(task, 0) + 1
    task_entropy = _entropy(task_counts)
    # v0.43: action_entropy — Shannon entropy over ranked window action distribution
    action_counts: dict = {}
    for r in runs:
        for action in r.get("selection_detail", {}).get("ranked_action_window", []):
            action_counts[action] = action_counts.get(action, 0) + 1
    action_entropy = _entropy(action_counts)
    return {
        "action_entropy": action_entropy,
        "collision_ratio": collision_ratio,
        "most_common_actions": most_common,
        "selected_action_count": selected_action_count,
        "task_diversity_ratio": task_diversity_ratio,
        "task_entropy": task_entropy,
        "total_action_task_collapse_count": total_collapse,
        "unique_action_sets": unique_count,
        "unique_selected_task_count": unique_selected_task_count,
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
    lines.append(f"- Total action-task collapse count: {ac['total_action_task_collapse_count']}")
    lines.append(f"- Selected action count: {ac['selected_action_count']}")
    lines.append(f"- Unique selected task count: {ac['unique_selected_task_count']}")
    lines.append(f"- Task diversity ratio: {ac['task_diversity_ratio']}")
    lines.append(f"- Collision ratio: {ac['collision_ratio']}")
    lines.append(f"- Task entropy: {ac['task_entropy']}")
    lines.append(f"- Action entropy: {ac['action_entropy']}")
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
