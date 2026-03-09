# SPDX-License-Identifier: MIT
"""Evaluate and compare multiple planner run envelopes.

Usage:
    python scripts/evaluate_planner_runs.py envelope1.json envelope2.json [...]
    python scripts/evaluate_planner_runs.py envelope1.json --output summary.json

Accepts one or more planner run envelope paths and outputs a deterministic
JSON comparison summary. Behavior is read-only: no files are modified except
the optional --output destination.

v0.35 addition. stdlib only.
"""

import argparse
import json
import sys
from pathlib import Path


def load_envelope(path):
    """Load a run envelope JSON file. Raises on missing or malformed file."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _selected_key(envelope):
    """Return a tuple representation of selected_actions for set comparison."""
    return tuple(envelope.get("selected_actions", []))


def evaluate_envelopes(envelopes):
    """Compare a list of loaded envelope dicts.

    Args:
        envelopes: list of envelope dicts (already loaded from JSON).

    Returns:
        A deterministic dict summary with keys:
          - envelope_count (int)
          - identical (bool): True when all runs selected the same actions in
            the same order.
          - ordering_differences (bool): True when runs have the same set of
            actions but in a different order (subset of non-identical).
          - runs (list): per-run summary entries.
    """
    if not envelopes:
        return {
            "envelope_count": 0,
            "identical": True,
            "ordering_differences": False,
            "runs": [],
        }

    runs = []
    for i, env in enumerate(envelopes):
        runs.append({
            "index": i,
            "inputs": env.get("inputs", {}),
            "planner_version": env.get("planner_version"),
            "selected_actions": env.get("selected_actions", []),
            "selection_count": env.get("selection_count", 0),
            "selection_detail": env.get("selection_detail", {}),
        })

    all_keys = [_selected_key(e) for e in envelopes]
    identical = len(set(all_keys)) == 1

    sorted_keys = [tuple(sorted(k)) for k in all_keys]
    ordering_differences = (not identical) and len(set(sorted_keys)) == 1

    return {
        "envelope_count": len(envelopes),
        "identical": identical,
        "ordering_differences": ordering_differences,
        "runs": runs,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Evaluate and compare planner run envelopes.",
        add_help=True,
    )
    parser.add_argument("envelopes", nargs="*", metavar="ENVELOPE",
                        help="Paths to planner run envelope JSON files.")
    parser.add_argument("--output", default=None, metavar="FILE",
                        help="Write comparison summary to this file (default: stdout).")
    args = parser.parse_args(argv)

    if not args.envelopes:
        parser.error("At least one envelope path is required.")

    loaded = [load_envelope(p) for p in args.envelopes]
    summary = evaluate_envelopes(loaded)
    output = json.dumps(summary, indent=2, sort_keys=True) + "\n"

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)


if __name__ == "__main__":
    main()
