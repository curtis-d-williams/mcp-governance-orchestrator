# SPDX-License-Identifier: MIT
"""Shared helper for simple template-driven artifact family builders."""

from pathlib import Path

from builder.spec_builder_support import require_capability_spec, default_generated_repo_name
from builder.template_renderer import read_template, render_template, write_file
from builder.result_contract import builder_result


REPO_ROOT = Path(__file__).resolve().parents[1]


def build_templated_artifact_family(
    *,
    capability,
    artifact_kind,
    template_dir,
    manifest_template_name,
    source_template_name,
    smoke_test_template_name,
    source_filename_template,
    manifest_output_name,
    smoke_test_output_name,
    module_suffix,
    name=None,
):
    spec = require_capability_spec(capability, artifact_kind)
    module_name = f"{spec['slug']}_{module_suffix}"

    if name is None:
        name = default_generated_repo_name(spec)

    root = REPO_ROOT / name

    variables = {
        "name": name,
        "capability": capability,
        "provider": spec["provider"],
        "title": spec["title"],
        "module_name": module_name,
    }

    readme = render_template(read_template(template_dir, "README.md.tpl"), variables)
    manifest = render_template(read_template(template_dir, manifest_template_name), variables)
    source_code = render_template(read_template(template_dir, source_template_name), variables)
    smoke_test = render_template(read_template(template_dir, smoke_test_template_name), variables)

    write_file(root / "README.md", readme)
    write_file(root / manifest_output_name, manifest)
    write_file(root / source_filename_template.format(module_name=module_name), source_code)
    write_file(root / smoke_test_output_name, smoke_test)

    return builder_result(
        generated_repo=str(root),
        artifact_kind=artifact_kind,
        capability=capability,
    )
