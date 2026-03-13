# SPDX-License-Identifier: MIT
"""Canonical builder result contract helper."""

def builder_result(
    *,
    generated_repo,
    artifact_kind,
    capability,
    status="ok",
    **extras,
):
    """
    Construct a normalized builder result payload.

    Canonical fields:
        status
        generated_repo
        artifact_kind
        capability

    Optional builder-specific fields are accepted via **extras.
    """
    result = {
        "status": status,
        "generated_repo": generated_repo,
        "artifact_kind": artifact_kind,
        "capability": capability,
    }

    if extras:
        result.update(extras)

    return result
