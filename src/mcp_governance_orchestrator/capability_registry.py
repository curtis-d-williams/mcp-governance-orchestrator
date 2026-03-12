# SPDX-License-Identifier: MIT
"""Canonical capability-to-artifact mapping for the capability factory."""

from .capability_spec_registry import CAPABILITY_SPECS, get_capability_spec

CAPABILITY_ARTIFACT_KIND = {
    capability: spec["artifact_kind"]
    for capability, spec in CAPABILITY_SPECS.items()
}


def artifact_kind_for_capability(capability):
    spec = get_capability_spec(capability)
    if spec is None:
        return None
    return spec["artifact_kind"]
