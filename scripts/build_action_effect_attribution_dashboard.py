#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build a deterministic HTML Action Effect Attribution dashboard.

Reads action_effectiveness_ledger.json and renders a table showing how
each action type affects portfolio signals.

Usage:
    python3 scripts/build_action_effect_attribution_dashboard.py
    python3 scripts/build_action_effect_attribution_dashboard.py \
        --input  action_effectiveness_ledger.json \
        --output action_effect_attribution_dashboard.html

Fails closed on missing or malformed input.
No external library dependencies.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

# Row background by classification (light tones for readability).
_ROW_BG: dict[str, str] = {
    "effective":   "#e8f5e9",  # light green
    "neutral":     "#f5f5f5",  # light gray
    "ineffective": "#ffebee",  # light red
}

_COLUMNS: list[tuple[str, str]] = [
    ("action_type",        "Action Type"),
    ("times_executed",     "Times Executed"),
    ("success_rate",       "Success Rate"),
    ("effectiveness_score","Effectiveness Score"),
    ("observed_effects",   "Observed Effects"),
    ("effect_deltas",      "Effect Deltas"),
    ("classification",     "Classification"),
]


def _fail(msg: str) -> int:
    sys.stderr.write(f"error: {msg}\n")
    return 1


def _load_ledger(path: Path) -> dict:
    """Load and validate the ledger. Fail closed on any problem."""
    if not path.exists():
        raise ValueError(f"ledger file not found: {path}")
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read ledger file: {exc}") from exc
    try:
        ledger = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON in ledger: {exc}") from exc
    if not isinstance(ledger, dict):
        raise ValueError("ledger must be a JSON object")
    if "action_types" not in ledger:
        raise ValueError("ledger missing required key 'action_types'")
    if not isinstance(ledger["action_types"], list):
        raise ValueError("ledger 'action_types' must be a list")
    return ledger


def _sort_rows(rows: list[dict]) -> list[dict]:
    """Deterministic sort: effectiveness_score DESC, action_type ASC."""
    return sorted(
        rows,
        key=lambda r: (
            -float(r.get("effectiveness_score", 0.0)),
            str(r.get("action_type", "")),
        ),
    )


def _render_effect_deltas(value: object) -> str:
    """Render effect_deltas dict: sorted signal names, signed two-decimal floats.

    Empty or absent dict renders as em-dash. All values are HTML-escaped.
    """
    if not isinstance(value, dict) or not value:
        return "<td>&#8212;</td>"
    parts = [
        html.escape(f"{sig}: {delta:+.2f}")
        for sig, delta in sorted(value.items())
    ]
    return f"<td>{'<br>'.join(parts)}</td>"


def _render_cell(field: str, value: object) -> str:
    if field == "effect_deltas":
        return _render_effect_deltas(value)
    if field == "observed_effects":
        items = value if isinstance(value, list) else []
        text = html.escape(", ".join(str(e) for e in items))
        return f"<td>{text}</td>"
    if field == "classification":
        text = html.escape(str(value))
        return f"<td><strong>{text}</strong></td>"
    return f"<td>{html.escape(str(value))}</td>"


def _build_html(ledger: dict) -> str:
    rows = _sort_rows(ledger["action_types"])

    lines: list[str] = []
    lines.append("<!DOCTYPE html>")
    lines.append("<html><head>")
    lines.append('<meta charset="utf-8">')
    lines.append("<title>Action Effect Attribution</title>")
    lines.append("<style>")
    lines.append("body{font-family:sans-serif;margin:2em}")
    lines.append("h1{color:#1a237e}")
    lines.append("table{border-collapse:collapse;width:100%}")
    lines.append("th,td{border:1px solid #bbb;padding:8px 10px;text-align:left}")
    lines.append("th{background:#37474f;color:#fff}")
    lines.append("</style>")
    lines.append("</head><body>")
    lines.append("<h1>Action Effect Attribution</h1>")

    lines.append("<table>")
    header_cells = "".join(
        f"<th>{html.escape(label)}</th>" for _, label in _COLUMNS
    )
    lines.append(f"<tr>{header_cells}</tr>")

    for row in rows:
        cls = str(row.get("classification", ""))
        bg = _ROW_BG.get(cls, "#ffffff")
        _defaults: dict[str, object] = {"observed_effects": [], "effect_deltas": {}}
        cells = "".join(
            _render_cell(field, row.get(field, _defaults.get(field, "")))
            for field, _ in _COLUMNS
        )
        lines.append(f'<tr style="background:{bg}">{cells}</tr>')

    lines.append("</table>")
    lines.append("</body></html>")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build an Action Effect Attribution HTML dashboard.",
    )
    parser.add_argument(
        "--input", default="action_effectiveness_ledger.json", metavar="FILE",
        help="Path to action_effectiveness_ledger.json (default: action_effectiveness_ledger.json).",
    )
    parser.add_argument(
        "--output", default="action_effect_attribution_dashboard.html", metavar="FILE",
        help="Destination HTML file (default: action_effect_attribution_dashboard.html).",
    )
    args = parser.parse_args(argv)

    try:
        ledger = _load_ledger(Path(args.input))
    except ValueError as exc:
        return _fail(str(exc))

    content = _build_html(ledger)

    out = Path(args.output)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")
    except OSError as exc:
        return _fail(f"cannot write output: {exc}")

    sys.stdout.write(f"wrote: {out}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
