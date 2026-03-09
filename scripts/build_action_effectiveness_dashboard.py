#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build a deterministic HTML dashboard from an action_effectiveness_ledger.json.

Usage:
    python3 scripts/build_action_effectiveness_dashboard.py
    python3 scripts/build_action_effectiveness_dashboard.py \
        --input action_effectiveness_ledger.json \
        --output action_effectiveness_dashboard.html

Fails closed on missing or malformed input.
Pure read-only: never modifies any repo state beyond the specified output file.
No external library dependencies.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

_CLASSIFICATION_COLORS: dict[str, str] = {
    "effective": "#2e7d32",   # green
    "neutral": "#757575",     # gray
    "ineffective": "#c62828", # red
}

_COLUMNS: list[tuple[str, str]] = [
    ("action_type",                    "Action Type"),
    ("times_recommended",              "Recommended"),
    ("times_executed",                 "Executed"),
    ("success_rate",                   "Success Rate"),
    ("avg_risk_delta",                 "Avg Risk Δ"),
    ("avg_health_delta",               "Avg Health Δ"),
    ("effectiveness_score",            "Effectiveness"),
    ("recommended_priority_adjustment","Priority Adj"),
    ("classification",                 "Classification"),
    ("effect_deltas",                  "Effect Deltas"),
]


def _fail(msg: str) -> int:
    sys.stderr.write(f"error: {msg}\n")
    return 1


def _load_ledger(path: Path) -> dict:
    if not path.exists():
        raise ValueError(f"input file not found: {path}")
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read input file: {exc}") from exc
    try:
        ledger = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON: {exc}") from exc
    if not isinstance(ledger, dict):
        raise ValueError("ledger must be a JSON object")
    if "action_types" not in ledger:
        raise ValueError("ledger missing required key 'action_types'")
    if not isinstance(ledger["action_types"], list):
        raise ValueError("ledger 'action_types' must be a list")
    return ledger


def _sort_rows(rows: list[dict]) -> list[dict]:
    """Sort deterministically: effectiveness_score desc, action_type asc."""
    return sorted(
        rows,
        key=lambda r: (
            -float(r.get("effectiveness_score", 0.0)),
            str(r.get("action_type", "")),
        ),
    )


def _render_effect_deltas(value: object) -> str:
    """Render effect_deltas dict as sorted signal:delta pairs, safe on empty/missing."""
    if not isinstance(value, dict) or not value:
        return "<td></td>"
    parts = [
        html.escape(f"{sig}: {delta:+.2f}")
        for sig, delta in sorted(value.items())
    ]
    return f"<td>{'<br>'.join(parts)}</td>"


def _cell(value: object, field: str) -> str:
    if field == "effect_deltas":
        return _render_effect_deltas(value)
    text = html.escape(str(value))
    if field == "classification":
        cls = str(value)
        color = _CLASSIFICATION_COLORS.get(cls, "#000000")
        return f'<td style="color:{color};font-weight:bold">{text}</td>'
    return f"<td>{text}</td>"


def _build_html(ledger: dict) -> str:
    summary = ledger.get("summary", {})
    rows = _sort_rows(ledger["action_types"])

    lines: list[str] = []
    lines.append("<!DOCTYPE html>")
    lines.append("<html><head>")
    lines.append('<meta charset="utf-8">')
    lines.append("<title>Action Effectiveness Dashboard</title>")
    lines.append("<style>")
    lines.append("body{font-family:sans-serif;margin:2em}")
    lines.append("h1{color:#1a237e}")
    lines.append(".summary{background:#e8eaf6;border-radius:6px;padding:1em;margin-bottom:1.5em;display:flex;gap:2em}")
    lines.append(".stat{text-align:center}")
    lines.append(".stat .val{font-size:2em;font-weight:bold;color:#1a237e}")
    lines.append(".stat .lbl{font-size:0.85em;color:#555}")
    lines.append("table{border-collapse:collapse;width:100%}")
    lines.append("th,td{border:1px solid #bbb;padding:8px 10px;text-align:left}")
    lines.append("th{background:#1a237e;color:#fff}")
    lines.append("tr:nth-child(even){background:#f5f5f5}")
    lines.append("</style>")
    lines.append("</head><body>")
    lines.append("<h1>Action Effectiveness Dashboard</h1>")

    # Summary section
    lines.append('<div class="summary">')
    for key, label in (
        ("actions_tracked",   "Actions Tracked"),
        ("effective_actions", "Effective"),
        ("neutral_actions",   "Neutral"),
        ("ineffective_actions","Ineffective"),
    ):
        val = html.escape(str(summary.get(key, 0)))
        lines.append(f'<div class="stat"><div class="val">{val}</div><div class="lbl">{html.escape(label)}</div></div>')
    lines.append("</div>")

    # Table
    lines.append("<table>")
    header_cells = "".join(f"<th>{html.escape(label)}</th>" for _, label in _COLUMNS)
    lines.append(f"<tr>{header_cells}</tr>")
    for row in rows:
        cells = "".join(_cell(row.get(field, ""), field) for field, _ in _COLUMNS)
        lines.append(f"<tr>{cells}</tr>")
    lines.append("</table>")
    lines.append("</body></html>")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a deterministic HTML dashboard from action_effectiveness_ledger.json.",
    )
    parser.add_argument("--input", default="action_effectiveness_ledger.json", metavar="FILE",
                        help="Path to action_effectiveness_ledger.json (default: action_effectiveness_ledger.json).")
    parser.add_argument("--output", default="action_effectiveness_dashboard.html", metavar="FILE",
                        help="Destination HTML file (default: action_effectiveness_dashboard.html).")
    args = parser.parse_args(argv)

    try:
        ledger = _load_ledger(Path(args.input))
    except ValueError as exc:
        return _fail(str(exc))

    html_content = _build_html(ledger)

    out = Path(args.output)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html_content, encoding="utf-8")
    except OSError as exc:
        return _fail(f"cannot write output: {exc}")

    sys.stdout.write(f"wrote: {out}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
