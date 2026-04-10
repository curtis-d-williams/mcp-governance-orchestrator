#!/usr/bin/env python3
"""
portfolio_report.py

Read-only script: reads a capability_effectiveness_ledger JSON file and
emits a structured human-readable report to stdout.

Usage:
    python3 scripts/portfolio_report.py capability_effectiveness_ledger.json
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

CAPABILITY_CONFIDENCE_THRESHOLD = 5.0
CAPABILITY_RELIABILITY_WEIGHT = 0.10

SEP_WIDE = "=" * 70
SEP_NARROW = "-" * 50


def load_ledger(path):
    p = Path(path)
    if not p.exists():
        print(f"ERROR: ledger file not found: {path}", file=sys.stderr)
        sys.exit(1)
    with p.open() as f:
        return json.load(f)


def pct(numerator, denominator):
    if denominator == 0:
        return "N/A"
    return f"{100.0 * numerator / denominator:.1f}%"


def confidence_pct(total):
    return f"{min(1.0, total / CAPABILITY_CONFIDENCE_THRESHOLD) * 100:.1f}%"


def similarity_direction(delta):
    if delta > 0:
        return "improving"
    if delta < 0:
        return "regressing"
    return "stable"


def print_header(ledger_path, capabilities, repair):
    cap_count = len(capabilities)
    print(SEP_WIDE)
    print("CAPABILITY EFFECTIVENESS LEDGER REPORT")
    print(SEP_WIDE)
    print(f"  Ledger path    : {ledger_path}")
    print(f"  Report time    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Capabilities   : {cap_count}")
    if repair:
        total = repair.get("total_syntheses", 0)
        failed = repair.get("failed_syntheses", 0)
        print(f"  Repair cycle   : {total} total / {failed} failed")
    else:
        print("  Repair cycle   : not present")
    print()


def print_capability_block(name, entry):
    total = entry.get("total_syntheses", 0)
    successful = entry.get("successful_syntheses", 0)
    evolved = entry.get("successful_evolved_syntheses", 0)
    delta = entry.get("similarity_delta")

    if delta is not None:
        delta_str = f"{delta:+.4f} ({similarity_direction(delta)})"
    else:
        delta_str = "N/A"

    print(SEP_NARROW)
    print(f"  Capability     : {name}")
    print(f"  artifact_kind  : {entry.get('artifact_kind', 'N/A')}")
    print(f"  total_syntheses: {total}")
    print(f"  success_rate   : {pct(successful, total)}")
    print(f"  evolution_rate : {pct(evolved, successful) if successful else 'N/A'}")
    print(f"  confidence     : {confidence_pct(total)}")
    print(f"  similarity_delta: {delta_str}")
    print(f"  last_source    : {entry.get('last_synthesis_source', 'N/A')}")
    print(f"  last_status    : {entry.get('last_synthesis_status', 'N/A')}")
    print()


def print_similarity_summary(capabilities):
    with_scores = {
        name: entry
        for name, entry in capabilities.items()
        if "similarity_score" in entry
    }
    print(SEP_WIDE)
    print("SIMILARITY PROGRESSION SUMMARY")
    print(SEP_WIDE)
    if not with_scores:
        print("  No capabilities with similarity_score present.")
        print()
        return
    for name in sorted(with_scores):
        entry = with_scores[name]
        score = entry.get("similarity_score", "N/A")
        delta = entry.get("similarity_delta")
        if delta is not None:
            direction = similarity_direction(delta)
            print(f"  {name}: score={score:.4f}  delta={delta:+.4f}  ({direction})")
        else:
            print(f"  {name}: score={score:.4f}  delta=N/A")
    print()


def print_adaptation_summary(capabilities):
    print(SEP_WIDE)
    print("ADAPTATION SIGNAL SUMMARY")
    print(SEP_WIDE)
    evolved = [
        name
        for name, entry in capabilities.items()
        if entry.get("last_synthesis_used_evolution") is True
    ]
    regressing = [
        name
        for name, entry in capabilities.items()
        if (entry.get("similarity_delta") or 0) < 0
    ]
    if evolved:
        print("  Capabilities using evolution on last synthesis:")
        for name in sorted(evolved):
            print(f"    - {name}")
    else:
        print("  No capabilities used evolution on last synthesis.")
    print()
    if regressing:
        print("  Regression flags (similarity_delta < 0):")
        for name in sorted(regressing):
            delta = capabilities[name].get("similarity_delta", 0)
            print(f"    - {name}: delta={delta:+.4f}")
    else:
        print("  No regression flags.")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Emit a structured human-readable report from a capability effectiveness ledger."
    )
    parser.add_argument("ledger", help="Path to capability_effectiveness_ledger.json")
    args = parser.parse_args()

    ledger = load_ledger(args.ledger)
    all_caps = ledger.get("capabilities", {})

    repair = all_caps.get("_repair_cycle")
    capabilities = {k: v for k, v in all_caps.items() if k != "_repair_cycle"}

    print_header(args.ledger, capabilities, repair)

    print(SEP_WIDE)
    print("PER-CAPABILITY DETAIL")
    print(SEP_WIDE)
    print()
    for name in sorted(capabilities):
        print_capability_block(name, capabilities[name])

    print_similarity_summary(capabilities)
    print_adaptation_summary(capabilities)

    print(SEP_WIDE)
    print("END OF REPORT")
    print(SEP_WIDE)


if __name__ == "__main__":
    main()
