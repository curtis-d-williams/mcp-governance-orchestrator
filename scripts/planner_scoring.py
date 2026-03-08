# SPDX-License-Identifier: MIT
"""Pure deterministic scoring logic for the planner (v0.33).

This module contains all scoring helpers extracted from
claude_dynamic_planner_loop.py so they can be tested and reused
independently of I/O, argument parsing, and task execution.

Public API (all importable from scripts.planner_scoring):
  Constants:   EFFECTIVENESS_WEIGHT, EFFECTIVENESS_CLAMP,
               SIGNAL_IMPACT_WEIGHT, SIGNAL_IMPACT_CLAMP,
               TARGETING_WEIGHT, TARGETING_CLAMP,
               CONFIDENCE_THRESHOLD,
               EXPLORATION_WEIGHT, EXPLORATION_CLAMP,
               POLICY_WEIGHT_CLAMP, POLICY_TOTAL_ABS_CAP
  Dataclass:   PriorityBreakdown
  Loaders:     load_effectiveness_ledger, load_portfolio_signals,
               load_planner_policy
  Helpers:     compute_confidence_factor, compute_learning_adjustment,
               compute_weak_signal_targeting_adjustment,
               compute_exploration_bonus, compute_policy_adjustment
  Builders:    _compute_priority_breakdown, _build_priority_breakdown,
               _apply_learning_adjustments
"""

import json
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# v0.26: Planner learning adjustment constants
# ---------------------------------------------------------------------------

EFFECTIVENESS_WEIGHT = 0.15
EFFECTIVENESS_CLAMP = 0.20

SIGNAL_IMPACT_WEIGHT = 0.05
SIGNAL_IMPACT_CLAMP = 0.15

# ---------------------------------------------------------------------------
# v0.27: Weak-signal targeting constants
# ---------------------------------------------------------------------------

TARGETING_WEIGHT = 0.10
TARGETING_CLAMP = 0.20

# ---------------------------------------------------------------------------
# v0.28: Confidence weighting constants
# ---------------------------------------------------------------------------

CONFIDENCE_THRESHOLD = 5.0

# ---------------------------------------------------------------------------
# v0.29: Uncertainty-driven exploration constants
# ---------------------------------------------------------------------------

EXPLORATION_WEIGHT = 0.05
EXPLORATION_CLAMP = 0.10

# ---------------------------------------------------------------------------
# v0.30: Policy-weighted signal optimization constants
# ---------------------------------------------------------------------------

POLICY_WEIGHT_CLAMP = 5.0

# ---------------------------------------------------------------------------
# v0.31: Policy total-magnitude guardrail
# ---------------------------------------------------------------------------

POLICY_TOTAL_ABS_CAP = 20.0


# ---------------------------------------------------------------------------
# v0.26: Ledger loading and learning adjustment helpers
# ---------------------------------------------------------------------------

def load_effectiveness_ledger(path):
    """Load ledger JSON and return {action_type: row_dict}.

    Returns an empty dict when:
    - path is None
    - file does not exist (fail-safe)
    - file is unreadable or malformed
    Never raises.
    """
    if path is None:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        rows = data.get("action_types", [])
        return {
            row["action_type"]: row
            for row in rows
            if isinstance(row, dict) and isinstance(row.get("action_type"), str)
        }
    except Exception:
        return {}


def compute_confidence_factor(action_type, ledger):
    """Return a confidence factor in [0.0, 1.0] based on times_executed.

    Logic:
    - action_type absent from ledger → 0.0
    - times_executed key absent from row → 1.0 (backward-compat: legacy entries
      without the field retain full learning effect)
    - invalid (non-numeric) or negative times_executed → 0.0
    - otherwise: min(1.0, times_executed / CONFIDENCE_THRESHOLD)

    Never raises.
    """
    row = ledger.get(action_type)
    if row is None:
        return 0.0
    if "times_executed" not in row:
        return 1.0  # backward-compat: field absent → full confidence
    try:
        te = float(row["times_executed"])
    except (TypeError, ValueError):
        return 0.0
    if te < 0:
        return 0.0
    return min(1.0, te / CONFIDENCE_THRESHOLD)


def compute_learning_adjustment(action_type, ledger):
    """Return the total learning priority adjustment for action_type.

    effectiveness_adj = clamp(effectiveness_score * EFFECTIVENESS_WEIGHT,
                              0.0, EFFECTIVENESS_CLAMP)
    signal_delta_adj  = clamp(sum(abs(effect_deltas)) * SIGNAL_IMPACT_WEIGHT,
                              0.0, SIGNAL_IMPACT_CLAMP)

    Returns 0.0 when action_type is absent from ledger.
    """
    row = ledger.get(action_type, {})

    effectiveness_score = float(row.get("effectiveness_score", 0.0))
    effectiveness_adj = min(
        max(0.0, effectiveness_score * EFFECTIVENESS_WEIGHT),
        EFFECTIVENESS_CLAMP,
    )

    effect_deltas = row.get("effect_deltas", {})
    signal_impact = sum(abs(v) for v in effect_deltas.values()) if effect_deltas else 0.0
    signal_delta_adj = min(
        max(0.0, signal_impact * SIGNAL_IMPACT_WEIGHT),
        SIGNAL_IMPACT_CLAMP,
    )

    return effectiveness_adj + signal_delta_adj


def load_portfolio_signals(portfolio_state_path):
    """Load portfolio-level signal averages from portfolio_state.json.

    Returns {signal_name: float_value} where values are averaged across all
    repos. Non-numeric (e.g. boolean) signal values are ignored.

    Returns {} when:
    - path is None
    - file does not exist (fail-safe)
    - file is unreadable or malformed
    Never raises.
    """
    if portfolio_state_path is None:
        return {}
    p = Path(portfolio_state_path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        repos = data.get("repos", [])
        totals = {}
        counts = {}
        for repo in repos:
            for name, value in repo.get("signals", {}).items():
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    continue
                totals[name] = totals.get(name, 0.0) + float(value)
                counts[name] = counts.get(name, 0) + 1
        return {name: totals[name] / counts[name] for name in totals}
    except Exception:
        return {}


def compute_weak_signal_targeting_adjustment(action_type, ledger, current_signals):
    """Return weak-signal targeting priority adjustment for action_type.

    weakness(signal) = max(0.0, 1.0 - signal_value)
    targeting_score  = sum(max(0.0, delta) * weakness
                           for each signal in effect_deltas)
    adjustment       = clamp(targeting_score * TARGETING_WEIGHT, ±TARGETING_CLAMP)

    Returns 0.0 when:
    - current_signals is empty
    - action_type is absent from ledger
    - effect_deltas is empty or no matching signals in current_signals
    - all deltas are non-positive
    """
    if not current_signals:
        return 0.0
    row = ledger.get(action_type, {})
    if not row:
        return 0.0
    effect_deltas = row.get("effect_deltas", {})
    if not effect_deltas:
        return 0.0
    targeting_score = sum(
        max(0.0, float(delta)) * max(0.0, 1.0 - current_signals[sig])
        for sig, delta in effect_deltas.items()
        if sig in current_signals
    )
    return max(-TARGETING_CLAMP, min(TARGETING_CLAMP, targeting_score * TARGETING_WEIGHT))


def load_planner_policy(path):
    """Load policy JSON and return {signal_name: weight}.

    v0.31 extensions (additive):
    - non-numeric weights are ignored (skipped silently)
    - each weight is clamped to ±POLICY_WEIGHT_CLAMP
    - if total absolute clamped weight exceeds POLICY_TOTAL_ABS_CAP,
      all weights are scaled proportionally so the total equals the cap

    Returns an empty dict when:
    - path is None
    - file does not exist (fail-safe)
    - file is unreadable or malformed
    Never raises.
    """
    if path is None:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        # Filter: string keys with numeric values only
        numeric = {}
        for k, v in data.items():
            if not isinstance(k, str):
                continue
            try:
                numeric[k] = float(v)
            except (TypeError, ValueError):
                continue  # non-numeric weight ignored
        if not numeric:
            return {}
        # Per-weight clamp
        clamped = {
            k: max(-POLICY_WEIGHT_CLAMP, min(POLICY_WEIGHT_CLAMP, v))
            for k, v in numeric.items()
        }
        # Total-magnitude cap: normalize proportionally if needed
        total_abs = sum(abs(v) for v in clamped.values())
        if total_abs > POLICY_TOTAL_ABS_CAP:
            scale = POLICY_TOTAL_ABS_CAP / total_abs
            return {k: v * scale for k, v in clamped.items()}
        return clamped
    except Exception:
        return {}


def compute_policy_adjustment(action_type, ledger, policy):
    """Return policy-weighted signal priority adjustment for action_type.

    policy_adjustment = sum(clamp(weight, ±POLICY_WEIGHT_CLAMP) * delta
                            for each (signal, weight) in policy
                            if signal in effect_deltas)

    Returns 0.0 when:
    - policy is empty or None
    - action_type is absent from ledger
    - effect_deltas is empty or no signals match the policy
    Non-numeric weights or deltas are skipped. Never raises.
    """
    if not policy:
        return 0.0
    row = ledger.get(action_type, {})
    if not row:
        return 0.0
    effect_deltas = row.get("effect_deltas", {})
    if not effect_deltas:
        return 0.0
    total = 0.0
    for signal, weight in policy.items():
        delta = effect_deltas.get(signal)
        if delta is None:
            continue
        try:
            w = float(weight)
            d = float(delta)
        except (TypeError, ValueError):
            continue
        clamped_w = max(-POLICY_WEIGHT_CLAMP, min(POLICY_WEIGHT_CLAMP, w))
        total += clamped_w * d
    return total


def compute_exploration_bonus(action_type, ledger):
    """Return a deterministic exploration bonus for action_type.

    uncertainty = 1 / (1 + times_executed)
    bonus       = clamp(uncertainty * EXPLORATION_WEIGHT, ±EXPLORATION_CLAMP)

    Missing ledger entry assumes times_executed = 0 (maximum uncertainty).
    Missing times_executed field in an existing row assumes times_executed = 0.
    Invalid (non-numeric) or negative times_executed assumes times_executed = 0.
    Never raises.
    """
    row = ledger.get(action_type)
    if row is None:
        times_executed = 0
    else:
        te_raw = row.get("times_executed", 0)
        try:
            te = float(te_raw)
        except (TypeError, ValueError):
            te = 0.0
        times_executed = max(0.0, te)

    uncertainty = 1.0 / (1.0 + times_executed)
    bonus = uncertainty * EXPLORATION_WEIGHT
    return max(-EXPLORATION_CLAMP, min(EXPLORATION_CLAMP, bonus))


# ---------------------------------------------------------------------------
# v0.32: PriorityBreakdown — single deterministic structure for all scoring
# ---------------------------------------------------------------------------

@dataclass
class PriorityBreakdown:
    """Internal per-action priority component record (v0.32).

    All weighted components are stored confidence-scaled (multiplied by
    confidence_factor) so that:

        final_priority = (
            base_priority
            + effectiveness_component
            + signal_delta_component
            + weak_signal_targeting_component
            + policy_component
            + exploration_component
        )

    confidence_factor is stored separately for reference / explain output.
    Never raises; all fields are float (or str for action_type).
    """
    action_type: str
    base_priority: float
    effectiveness_component: float        # = confidence_factor * raw_effectiveness_adj
    signal_delta_component: float         # = confidence_factor * raw_signal_delta_adj
    weak_signal_targeting_component: float  # = confidence_factor * raw_targeting_adj
    policy_component: float               # = confidence_factor * raw_policy_adj
    confidence_factor: float
    exploration_component: float
    final_priority: float

    def to_dict(self):
        """Return a rounded, JSON-serialisable dict matching the explain schema."""
        return {
            "action_type": self.action_type,
            "base_priority": round(self.base_priority, 6),
            "effectiveness_component": round(self.effectiveness_component, 6),
            "signal_delta_component": round(self.signal_delta_component, 6),
            "weak_signal_targeting_component": round(self.weak_signal_targeting_component, 6),
            "policy_component": round(self.policy_component, 6),
            "confidence_factor": round(self.confidence_factor, 6),
            "exploration_component": round(self.exploration_component, 6),
            "final_priority": round(self.final_priority, 6),
        }


def _compute_priority_breakdown(action, ledger, current_signals, policy):
    """Build a PriorityBreakdown for a single action. Read-only; never raises.

    Single canonical path for all priority arithmetic — used by both the
    ranking sort key and the explain artifact builder.

    Args:
        action:          action dict with at least 'action_type' and 'priority'.
        ledger:          {action_type: row_dict} from load_effectiveness_ledger.
        current_signals: {signal_name: float} portfolio signal averages.
        policy:          {signal_name: weight} from load_planner_policy.

    Returns:
        PriorityBreakdown instance with all components populated.
    """
    at = action.get("action_type", "")
    base = float(action.get("priority", 0.0))
    confidence = compute_confidence_factor(at, ledger)

    row = ledger.get(at, {})
    effectiveness_score = float(row.get("effectiveness_score", 0.0))
    effectiveness_adj = min(
        max(0.0, effectiveness_score * EFFECTIVENESS_WEIGHT),
        EFFECTIVENESS_CLAMP,
    )
    effect_deltas = row.get("effect_deltas", {})
    signal_impact = (
        sum(abs(v) for v in effect_deltas.values()) if effect_deltas else 0.0
    )
    signal_delta_adj = min(
        max(0.0, signal_impact * SIGNAL_IMPACT_WEIGHT),
        SIGNAL_IMPACT_CLAMP,
    )

    targeting_adj = compute_weak_signal_targeting_adjustment(at, ledger, current_signals)
    policy_adj = compute_policy_adjustment(at, ledger, policy)
    exploration = compute_exploration_bonus(at, ledger)

    final = (
        base
        + confidence * (effectiveness_adj + signal_delta_adj + targeting_adj + policy_adj)
        + exploration
    )

    return PriorityBreakdown(
        action_type=at,
        base_priority=base,
        effectiveness_component=confidence * effectiveness_adj,
        signal_delta_component=confidence * signal_delta_adj,
        weak_signal_targeting_component=confidence * targeting_adj,
        policy_component=confidence * policy_adj,
        confidence_factor=confidence,
        exploration_component=exploration,
        final_priority=final,
    )


def _build_priority_breakdown(actions, ledger, current_signals, policy):
    """Return a deterministic list of per-action priority component dicts.

    Delegates to _compute_priority_breakdown for each action so that explain
    mode and ranking share a single arithmetic path. Read-only; never mutates
    inputs.

    Each dict contains:
        action_type, base_priority, effectiveness_component,
        signal_delta_component, weak_signal_targeting_component,
        policy_component, confidence_factor, exploration_component,
        final_priority
    """
    _signals = current_signals or {}
    _policy = policy or {}
    return [
        _compute_priority_breakdown(a, ledger, _signals, _policy).to_dict()
        for a in actions
    ]


def _apply_learning_adjustments(actions, ledger, current_signals=None, policy=None):
    """Re-sort actions by base_priority + learning_adjustment (deterministic).

    Returns the original list unchanged when ledger is empty.
    Tiebreaker order: action_type asc, action_id asc, repo_id asc.

    current_signals: optional {signal_name: float} portfolio signal averages
        (v0.27). When absent or empty, targeting adjustment is zero and
        v0.26 behavior is preserved.

    policy: optional {signal_name: weight} governance policy weights (v0.30).
        When absent or empty, policy_adjustment is zero and v0.29 behavior
        is preserved.
    """
    if not ledger:
        return actions

    _signals = current_signals or {}
    _policy = policy or {}

    def _sort_key(a):
        bd = _compute_priority_breakdown(a, ledger, _signals, _policy)
        return (
            -bd.final_priority,
            bd.action_type,
            a.get("action_id", ""),
            a.get("repo_id", ""),
        )

    return sorted(actions, key=_sort_key)
