# SPDX-License-Identifier: MIT
"""
Capability artifact builder registry.

Builders register themselves via the @register_builder decorator.
"""

ARTIFACT_BUILDERS = {}


def register_builder(artifact_kind):
    """
    Decorator for registering capability builders.
    """

    def decorator(fn):
        ARTIFACT_BUILDERS[artifact_kind] = fn
        return fn

    return decorator


def build_capability_artifact(*, artifact_kind, capability, **kwargs):
    """
    Dispatch capability artifact generation.
    """

    if artifact_kind not in ARTIFACT_BUILDERS:
        raise ValueError(f"unknown artifact kind: {artifact_kind}")

    builder = ARTIFACT_BUILDERS[artifact_kind]

    return builder(capability=capability, **kwargs)
