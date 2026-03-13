# SPDX-License-Identifier: MIT
"""Planner scoring telemetry helpers.

This module provides optional, side-effect-free collection of registry-driven
planner scoring contributions. It is intentionally decoupled from ranking logic
so telemetry can be added without changing planner output ordering.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SignalContribution:
    """Telemetry record for a single scoring signal."""

    component_field: str
    raw_value: float
    scaled_value: float
    confidence_scaled: bool

    def to_dict(self) -> dict:
        """Return a deterministic JSON-serialisable representation."""
        return {
            "component_field": self.component_field,
            "raw_value": round(self.raw_value, 6),
            "scaled_value": round(self.scaled_value, 6),
            "confidence_scaled": self.confidence_scaled,
        }


@dataclass
class ActionScoringTelemetry:
    """Telemetry record for one action's scoring evaluation."""

    action_type: str
    base_priority: float
    confidence_factor: float
    signal_contributions: list[SignalContribution] = field(default_factory=list)

    def add(
        self,
        component_field: str,
        raw_value: float,
        scaled_value: float,
        confidence_scaled: bool,
    ) -> None:
        """Append a signal contribution record."""
        self.signal_contributions.append(
            SignalContribution(
                component_field=component_field,
                raw_value=float(raw_value),
                scaled_value=float(scaled_value),
                confidence_scaled=confidence_scaled,
            )
        )

    def to_dict(self) -> dict:
        """Return a deterministic JSON-serialisable representation."""
        return {
            "action_type": self.action_type,
            "base_priority": round(self.base_priority, 6),
            "confidence_factor": round(self.confidence_factor, 6),
            "signal_contributions": [
                contribution.to_dict()
                for contribution in self.signal_contributions
            ],
        }


@dataclass
class PlannerScoringTelemetry:
    """Mutable collector for per-action planner scoring telemetry."""

    actions: list[ActionScoringTelemetry] = field(default_factory=list)

    def start_action(
        self, action_type: str, base_priority: float, confidence_factor: float
    ) -> ActionScoringTelemetry:
        """Create and register an action telemetry record."""
        record = ActionScoringTelemetry(
            action_type=action_type,
            base_priority=float(base_priority),
            confidence_factor=float(confidence_factor),
        )
        self.actions.append(record)
        return record

    def to_dict(self) -> dict:
        """Return a deterministic JSON-serialisable representation."""
        return {
            "actions": [action.to_dict() for action in self.actions],
        }
