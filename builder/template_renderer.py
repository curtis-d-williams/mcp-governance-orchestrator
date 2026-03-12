# SPDX-License-Identifier: MIT
"""Shared template rendering helpers for artifact builders."""

from pathlib import Path


def read_template(template_dir, name):
    return (Path(template_dir) / name).read_text(encoding="utf-8")


def write_file(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def render_template(template, variables):
    rendered = template
    for key, value in variables.items():
        rendered = rendered.replace("{{" + key + "}}", str(value))
    return rendered
