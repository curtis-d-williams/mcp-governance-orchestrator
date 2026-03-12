# SPDX-License-Identifier: MIT
"""
Deterministic data connector builder.

Generates a minimal connector-style repository to prove that the capability
factory can build artifact kinds beyond MCP servers and agent adapters.
"""

from pathlib import Path

from builder.artifact_registry import register_builder
from builder.templated_family_builder import build_templated_artifact_family


REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = REPO_ROOT / "templates" / "data_connector"


@register_builder("data_connector")
def build_data_connector(
    name=None,
    capability="postgres_data_access",
):
    """
    Generate a deterministic data connector repo.
    """

    return build_templated_artifact_family(
        capability=capability,
        artifact_kind="data_connector",
        template_dir=TEMPLATE_DIR,
        manifest_template_name="connector_manifest.json.tpl",
        source_template_name="connector.py.tpl",
        smoke_test_template_name="test_connector_smoke.py.tpl",
        source_filename_template="{module_name}.py",
        manifest_output_name="connector_manifest.json",
        smoke_test_output_name="tests/test_connector_smoke.py",
        module_suffix="connector",
        name=name,
    )
