#!/usr/bin/env python3
"""
Tier 3 (suggestion-only) template: sample_template

Contract: docs/TIER3_CONTRACT.md
- deterministic
- non-enforcing (fail_closed must be False)
- no side effects
"""

from __future__ import annotations


def generate_suggestions() -> dict:
    # Deterministic placeholder suggestions. Replace with real logic (read-only).
    return {
        "suggestion_id": "sample_template_example",
        "description": "Dry-run Tier 3 scaffold",
        "metrics": {"example_metric": 42},
        "notes": "Non-enforcing, deterministic"
    }


def main() -> dict:
    suggestions = generate_suggestions()
    return {
        "tool": "sample_template",
        "ok": True,
        "fail_closed": False,
        "suggestions": suggestions,
    }


if __name__ == "__main__":
    import json as _json
    out = main()
    print(_json.dumps(out, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
