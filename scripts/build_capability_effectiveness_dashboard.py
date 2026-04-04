#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build a deterministic HTML dashboard from a capability_effectiveness_ledger.json.

Usage:
    python3 scripts/build_capability_effectiveness_dashboard.py
    python3 scripts/build_capability_effectiveness_dashboard.py \
        --input capability_effectiveness_ledger.json \
        --output capability_effectiveness_dashboard.html

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

_STATUS_COLORS: dict[str, str] = {
    "ok":     "#2e7d32",   # green
    "failed": "#c62828",   # red
}

_COLUMNS: list[tuple[str, str]] = [
    ("capability",                    "Capability"),
    ("artifact_kind",                 "Artifact Kind"),
    ("total_syntheses",               "Total"),
    ("successful_syntheses",          "Successful"),
    ("failed_syntheses",              "Failed"),
    ("success_rate",                  "Success Rate"),
    ("successful_evolved_syntheses",  "Evolved"),
    ("last_synthesis_status",         "Last Status"),
    ("last_synthesis_source",         "Last Source"),
    ("last_synthesis_used_evolution", "Used Evolution"),
    ("similarity_score",              "Similarity"),
    ("similarity_delta",              "Similarity Δ"),
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
    if "capabilities" not in ledger:
        raise ValueError("ledger missing required key 'capabilities'")
    if not isinstance(ledger["capabilities"], dict):
        raise ValueError("ledger 'capabilities' must be an object")
    return ledger


def _sort_rows(rows: list[dict]) -> list[dict]:
    """Sort deterministically: total_syntheses desc, capability asc."""
    return sorted(
        rows,
        key=lambda r: (
            -int(r.get("total_syntheses", 0)),
            str(r.get("capability", "")),
        ),
    )


def _cell(value: object, field: str) -> str:
    if value == "" or value is None:
        return "<td></td>"
    text = html.escape(str(value))
    if field == "last_synthesis_status":
        color = _STATUS_COLORS.get(str(value), "#000000")
        return f'<td style="color:{color};font-weight:bold">{text}</td>'
    if field == "success_rate":
        return f"<td>{html.escape(f'{float(value):.1%}')}</td>"
    if field in ("similarity_score", "similarity_delta"):
        try:
            return f"<td>{float(value):.3f}</td>"
        except (TypeError, ValueError):
            return f"<td>{text}</td>"
    return f"<td>{text}</td>"


def _build_rows(capabilities: dict) -> list[dict]:
    rows = []
    for name, entry in capabilities.items():
        if not isinstance(entry, dict):
            continue
        total = int(entry.get("total_syntheses", 0))
        successful = int(entry.get("successful_syntheses", 0))
        row = {
            "capability": name,
            "artifact_kind": entry.get("artifact_kind", ""),
            "total_syntheses": total,
            "successful_syntheses": successful,
            "failed_syntheses": int(entry.get("failed_syntheses", 0)),
            "success_rate": successful / total if total > 0 else 0.0,
            "successful_evolved_syntheses": int(entry.get("successful_evolved_syntheses", 0)),
            "last_synthesis_status": entry.get("last_synthesis_status", ""),
            "last_synthesis_source": entry.get("last_synthesis_source", ""),
            "last_synthesis_used_evolution": entry.get("last_synthesis_used_evolution", ""),
            "similarity_score": entry.get("similarity_score", ""),
            "similarity_delta": entry.get("similarity_delta", ""),
        }
        rows.append(row)
    return rows


def _build_html(ledger: dict) -> str:
    capabilities = ledger.get("capabilities", {})
    rows = _sort_rows(_build_rows(capabilities))

    total_caps = len(rows)
    total_syn = sum(r["total_syntheses"] for r in rows)
    total_ok = sum(r["successful_syntheses"] for r in rows)
    total_failed = sum(r["failed_syntheses"] for r in rows)

    lines: list[str] = []
    lines.append("<!DOCTYPE html>")
    lines.append("<html><head>")
    lines.append('<meta charset="utf-8">')
    lines.append("<title>Capability Effectiveness Dashboard</title>")
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
    lines.append("<h1>Capability Effectiveness Dashboard</h1>")

    lines.append('<div class="summary">')
    for val, label in (
        (total_caps,   "Capabilities Tracked"),
        (total_syn,    "Total Syntheses"),
        (total_ok,     "Successful"),
        (total_failed, "Failed"),
    ):
        lines.append(
            f'<div class="stat"><div class="val">{html.escape(str(val))}</div>'
            f'<div class="lbl">{html.escape(label)}</div></div>'
        )
    lines.append("</div>")

    lines.append("<table>")
    header_cells = "".join(f"<th>{html.escape(lbl)}</th>" for _, lbl in _COLUMNS)
    lines.append(f"<tr>{header_cells}</tr>")
    for row in rows:
        cells = "".join(_cell(row.get(field, ""), field) for field, _ in _COLUMNS)
        lines.append(f"<tr>{cells}</tr>")
    lines.append("</table>")
    lines.append("</body></html>")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a deterministic HTML dashboard from capability_effectiveness_ledger.json.",
    )
    parser.add_argument("--input", default="capability_effectiveness_ledger.json", metavar="FILE",
                        help="Path to capability_effectiveness_ledger.json (default: capability_effectiveness_ledger.json).")
    parser.add_argument("--output", default="capability_effectiveness_dashboard.html", metavar="FILE",
                        help="Destination HTML file (default: capability_effectiveness_dashboard.html).")
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
