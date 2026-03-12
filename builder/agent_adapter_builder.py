# SPDX-License-Identifier: MIT
"""
Deterministic agent adapter builder.

Generates a minimal adapter-style repository to prove that the capability
factory can build multiple artifact families.
"""

from pathlib import Path

from builder.artifact_registry import register_builder
from builder.templated_family_builder import build_templated_artifact_family


REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = REPO_ROOT / "templates" / "agent_adapter"


@register_builder("agent_adapter")
def build_agent_adapter(
    name=None,
    capability="slack_workspace_access",
):
    """
    Generate a deterministic agent adapter repo for Slack-style access.
    """

    return build_templated_artifact_family(
        capability=capability,
        artifact_kind="agent_adapter",
        template_dir=TEMPLATE_DIR,
        manifest_template_name="adapter_manifest.json.tpl",
        source_template_name="adapter.py.tpl",
        smoke_test_template_name="test_adapter_smoke.py.tpl",
        source_filename_template="{module_name}.py",
        manifest_output_name="adapter_manifest.json",
        smoke_test_output_name="tests/test_adapter_smoke.py",
        module_suffix="adapter",
        name=name,
    )
