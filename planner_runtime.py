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
import math
import subprocess
import sys
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
# v0.34: Capability synthesis reliability ranking constants
# ---------------------------------------------------------------------------

CAPABILITY_RELIABILITY_WEIGHT = 0.10


# ---------------------------------------------------------------------------
# v0.26: Ledger loading and learning adjustment helpers
# ---------------------------------------------------------------------------

def load_effectiveness_ledger(path):
    """Load effectiveness ledger JSON.

    Supports both:
    - legacy planner format: {"action_types": [{"action_type": "...", ...}, ...]}
    - current action ledger format: {"actions": {"task_name": {...}, ...}}

    Returns an empty dict when:
    - path is None
    - file does not exist
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

        actions = data.get("actions")
        if isinstance(actions, dict):
            return {"actions": actions}

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


def load_capability_effectiveness_ledger(path):
    """Load capability effectiveness ledger JSON.

    Expected schema:
        {
            "capabilities": {
                "<capability_name>": {
                    "total_syntheses": int,
                    "successful_syntheses": int
                }
            }
        }

    Returns {} when:
    - path is None
    - file does not exist
    - file is unreadable or malformed
    - schema does not contain a valid "capabilities" object

    Never raises.
    """
    if path is None:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        capabilities = data.get("capabilities")
        if isinstance(capabilities, dict):
            return {"capabilities": capabilities}
        return {}
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
    confidence_factor) where applicable so that:

        final_priority = (
            base_priority
            + effectiveness_component
            + signal_delta_component
            + weak_signal_targeting_component
            + policy_component
            + capability_reliability_component
            + exploration_component
        )

    confidence_factor is stored separately for reference / explain output.
    Never raises; all fields are float (or str for action_type).
    """
    action_type: str
    base_priority: float
    effectiveness_component: float
    signal_delta_component: float
    weak_signal_targeting_component: float
    policy_component: float
    capability_reliability_component: float
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
            "capability_reliability_component": round(
                self.capability_reliability_component, 6
            ),
            "confidence_factor": round(self.confidence_factor, 6),
            "exploration_component": round(self.exploration_component, 6),
            "final_priority": round(self.final_priority, 6),
        }


def _compute_priority_breakdown(
    action, ledger, current_signals, policy, capability_ledger=None
):
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

    capability_adj = _compute_capability_reliability_adjustment(
        action, capability_ledger
    )
        
    final = (
        base
        + confidence * (effectiveness_adj + signal_delta_adj + targeting_adj + policy_adj)
        + capability_adj
        + exploration
    )

    return PriorityBreakdown(
        action_type=at,
        base_priority=base,
        effectiveness_component=confidence * effectiveness_adj,
        signal_delta_component=confidence * signal_delta_adj,
        weak_signal_targeting_component=confidence * targeting_adj,
        policy_component=confidence * policy_adj,
        capability_reliability_component=capability_adj,
        confidence_factor=confidence,
        exploration_component=exploration,
        final_priority=final,
    )


def _build_priority_breakdown(
    actions, ledger, current_signals, policy, capability_ledger=None
):
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
        _compute_priority_breakdown(
            a, ledger, _signals, _policy, capability_ledger
        ).to_dict()
        for a in actions
    ]


def _compute_task_reliability(task_name, ledger):
    """Return success_rate for a task from the historical ledger.

    Ledger schema:
        {
            "actions": {
                "<task_name>": {
                    "total_runs": int,
                    "success_count": int,
                    "failure_count": int
                }
            }
        }

    Returns:
        float in [0,1] when history exists
        None when task has no historical data
    """
    if not ledger:
        return None

    actions = ledger.get("actions")
    if not isinstance(actions, dict):
        return None

    row = actions.get(task_name)
    if not isinstance(row, dict):
        return None

    total = row.get("total_runs")
    success = row.get("success_count")

    try:
        total = float(total)
        success = float(success)
    except (TypeError, ValueError):
        return None

    if total <= 0:
        return None

    return success / total



def _compute_capability_reliability_adjustment(action, capability_ledger):
    """Return a bounded ranking adjustment for capability synthesis actions.

    Only applies to planner actions that request capability synthesis and carry
    args.capability metadata.

    Adjustment formula:
        success_rate == 1.0  -> +0.05
        success_rate == 0.5  ->  0.00
        success_rate == 0.0  -> -0.05

    Returns 0.0 when:
        - capability_ledger is empty
        - action is not a capability synthesis action
        - capability metadata missing
        - no historical data exists
    """
    if not capability_ledger:
        return 0.0

    action_type = action.get("action_type", "")
    if action_type not in ("build_capability_artifact", "build_mcp_server"):
        return 0.0

    args = action.get("args", {})
    if not isinstance(args, dict):
        return 0.0

    capability = args.get("capability")
    if not isinstance(capability, str) or not capability:
        return 0.0

    caps = capability_ledger.get("capabilities")
    if not isinstance(caps, dict):
        return 0.0

    row = caps.get(capability)
    if not isinstance(row, dict):
        return 0.0

    total = row.get("total_syntheses", 0)
    success = row.get("successful_syntheses", 0)

    try:
        total = float(total)
        success = float(success)
    except (TypeError, ValueError):
        return 0.0

    if total <= 0:
        return 0.0

    success_rate = max(0.0, min(1.0, success / total))
    return (success_rate - 0.5) * CAPABILITY_RELIABILITY_WEIGHT

def _apply_learning_adjustments(actions, ledger, current_signals=None, policy=None,
                                capability_ledger=None):
    """Re-sort actions by base_priority + learning_adjustment (deterministic).

    Returns the original list unchanged when both ledgers are empty.
    Tiebreaker order: action_type asc, action_id asc, repo_id asc.

    current_signals: optional {signal_name: float} portfolio signal averages
        (v0.27). When absent or empty, targeting adjustment is zero and
        v0.26 behavior is preserved.

    policy: optional {signal_name: weight} governance policy weights (v0.30).
        When absent or empty, policy_adjustment is zero and v0.29 behavior
        is preserved.

    capability_ledger: optional {"capabilities": {...}} aggregated capability
        synthesis history. When present, capability synthesis actions receive a
        small bounded boost/penalty based on historical synthesis success.
    """
    if not ledger and not capability_ledger:
        return actions

    _signals = current_signals or {}
    _policy = policy or {}

    def _sort_key(a):
        bd = _compute_priority_breakdown(
            a, ledger, _signals, _policy, capability_ledger
        )

        task_name = None
        if isinstance(a, dict):
            task_name = a.get("task_name")

        reliability = _compute_task_reliability(task_name, ledger)
        reliability_boost = reliability if reliability is not None else 0.0

        return (
            -(bd.final_priority + reliability_boost * 0.05),
            bd.action_type,
            a.get("action_id", ""),
            a.get("repo_id", ""),
        )

    return sorted(actions, key=_sort_key)


# ---------------------------------------------------------------------------
# Planner evaluation helpers (extracted from evaluate_planner_config)
# ---------------------------------------------------------------------------

_ENTROPY_DIVERGENCE_THRESHOLD = 0.3


def classify_risk(metrics, top_k):
    """Classify planner collision risk deterministically."""
    collision_ratio = metrics["collision_ratio"]
    unique_tasks = metrics["unique_tasks"]
    collapse_count = metrics["collapse_count"]
    task_entropy = metrics["task_entropy"]
    action_entropy = metrics["action_entropy"]
    window_size = len(metrics["ranked_action_window"])
    entropy_gap = action_entropy - task_entropy

    reasons = []
    recommendations = []

    if window_size == 0:
        return (
            "high_risk",
            ["planner produced no actions"],
            ["inspect portfolio state and mapping coverage"],
        )

    high = False

    if collision_ratio >= 0.5:
        high = True
        reasons.append(
            "collision_ratio >= 0.5: mapping collapse severely limits task diversity"
        )

    if unique_tasks <= 1 and top_k >= 3:
        high = True
        reasons.append(
            "unique_tasks <= 1 with large window: mapping collapse is near-total"
        )

    if entropy_gap >= 1.0:
        high = True
        reasons.append(
            "entropy_gap >= 1.0 bits: severe task diversity compression detected"
        )

    if high:
        recommendations.append("reduce mapping collisions")
        return "high_risk", reasons, recommendations

    moderate = False

    if collision_ratio > 0:
        moderate = True
        reasons.append("some action→task collisions detected")

    if entropy_gap > _ENTROPY_DIVERGENCE_THRESHOLD:
        moderate = True
        reasons.append("task entropy materially below action entropy")

    if moderate:
        recommendations.append("consider mapping override or policy change")
        return "moderate_risk", reasons, recommendations

    reasons.append("no collisions detected")
    recommendations.append("safe to use as-is")
    return "low_risk", reasons, recommendations


def compute_expected_success_signal(mapped_tasks, ledger):
    """Return (expected_success_rate, historical_runs) from mapped tasks.

    Supports both:
    - current action ledger shape: {"actions": {task_name: {...}}}
    - legacy planner ledger shape: {action_type: row_dict}

    expected_success_rate is the fraction of unique matched tasks whose
    historical record is favorable (success_count > failure_count).

    Returns:
        (None, 0) when no mapped task has matching history.
    """
    if isinstance((ledger or {}).get("actions"), dict):
        actions = ledger.get("actions", {})
    else:
        actions = ledger or {}

    seen = set()
    favorable = 0
    considered = 0
    historical_runs = 0

    for task in mapped_tasks or []:
        if task is None or task in seen:
            continue
        seen.add(task)

        entry = actions.get(task)
        if not isinstance(entry, dict):
            continue

        total_runs = entry.get("total_runs", entry.get("times_executed", 0))
        success_count = entry.get("success_count")
        failure_count = entry.get("failure_count")

        if success_count is None and failure_count is None:
            effectiveness_score = entry.get("effectiveness_score")
            if isinstance(effectiveness_score, (int, float)):
                success_count = 1 if effectiveness_score > 0 else 0
                failure_count = 0 if effectiveness_score > 0 else 1
            else:
                success_count = 0
                failure_count = 0

        if not isinstance(total_runs, int) or total_runs < 0:
            total_runs = 0
        if not isinstance(success_count, int) or success_count < 0:
            success_count = 0
        if not isinstance(failure_count, int) or failure_count < 0:
            failure_count = 0

        considered += 1
        historical_runs += total_runs
        if success_count > failure_count:
            favorable += 1

    if considered == 0:
        return None, 0

    return favorable / considered, historical_runs


def build_planner_evaluation(metrics, top_k, expected_success_rate=None, historical_runs=0):
    """Attach risk classification to planner metrics."""
    risk_level, reasons, recommendations = classify_risk(metrics, top_k)

    return {
        **metrics,
        "risk_level": risk_level,
        "reasons": reasons,
        "recommendations": recommendations,
        "expected_success_rate": expected_success_rate,
        "historical_runs": historical_runs,
    }


# ---------------------------------------------------------------------------
# Planner collision-analysis runtime helpers
# ---------------------------------------------------------------------------

def load_mapping_override(path):
    if path is None:
        return None
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def entropy_from_counts(counts):
    total = sum(counts.values())
    if total == 0:
        return 0.0
    h = 0.0
    for key in sorted(counts):
        p = counts[key] / total
        if p > 0:
            h -= p * math.log2(p)
    return round(h, 6)


def fetch_planner_actions(portfolio_state_path, ledger_path=None):
    repo_root = Path(__file__).resolve().parent
    cmd = [
        sys.executable,
        str(repo_root / "scripts" / "list_portfolio_actions.py"),
        "--input", str(portfolio_state_path),
        "--json",
    ]
    if ledger_path is not None:
        cmd += ["--ledger", str(ledger_path)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            print(
                f"Action queue fetch failed (rc={result.returncode}): "
                f"{result.stderr.strip()}",
                file=sys.stderr,
            )
            return []
        return json.loads(result.stdout)
    except Exception as exc:
        print(f"Action queue fetch error: {exc}", file=sys.stderr)
        return []


def compute_planner_collision_risk(actions, top_k, ledger, signals, policy,
                                   active_mapping, exploration_offset=0,
                                   mapping_override=None, capability_ledger=None):
    from scripts.claude_dynamic_planner_loop import resolve_task_for_action

    ranked = _apply_learning_adjustments(actions, ledger, signals, policy, capability_ledger)

    start = max(0, min(exploration_offset, max(0, len(ranked) - top_k)))
    end = start + top_k
    window = ranked[start:end]

    ranked_action_window_detail = [
        {
            "action_id": a.get("action_id", ""),
            "action_type": a.get("action_type", ""),
            "repo_id": a.get("repo_id", ""),
        }
        for a in window
    ]
    ranked_action_window = [d["action_type"] for d in ranked_action_window_detail]

    mapped_tasks = []
    seen_tasks = set()
    for detail in ranked_action_window_detail:
        if mapping_override is not None:
            task = resolve_task_for_action(detail, mapping_override, active_mapping)
        else:
            task = active_mapping.get(detail["action_type"])
        mapped_tasks.append(task)
        if task is not None and task not in seen_tasks:
            seen_tasks.add(task)

    unique_tasks = len(seen_tasks)
    window_size = len(ranked_action_window)
    collapse_count = window_size - unique_tasks
    collision_ratio = round(collapse_count / window_size, 6) if window_size > 0 else 0.0

    task_counts = {}
    for task in mapped_tasks:
        if task is not None:
            task_counts[task] = task_counts.get(task, 0) + 1

    action_counts = {}
    for action_type in ranked_action_window:
        action_counts[action_type] = action_counts.get(action_type, 0) + 1

    return {
        "ranked_action_window": ranked_action_window,
        "ranked_action_window_detail": ranked_action_window_detail,
        "mapped_tasks": mapped_tasks,
        "unique_tasks": unique_tasks,
        "collapse_count": collapse_count,
        "collision_ratio": collision_ratio,
        "task_entropy": entropy_from_counts(task_counts),
        "action_entropy": entropy_from_counts(action_counts),
    }


def build_planner_risk_summary(policy_path, top_k, metrics):
    """Attach planner-analysis metadata to raw collision-risk metrics."""
    return {
        "policy": policy_path,
        "top_k": top_k,
        **metrics,
    }


def analyze_planner_configuration(policy_path, top_k, portfolio_state_path, ledger_path,
                                  mapping_override=None, exploration_offset=0,
                                  capability_ledger_path=None):
    """Return raw collision-risk summary for a planner configuration."""
    from scripts.claude_dynamic_planner_loop import (
        ACTION_TO_TASK,
        resolve_action_to_task_mapping,
    )

    ledger = load_effectiveness_ledger(ledger_path)
    capability_ledger = load_capability_effectiveness_ledger(capability_ledger_path)
    signals = load_portfolio_signals(portfolio_state_path)
    policy = load_planner_policy(policy_path)
    active_mapping = resolve_action_to_task_mapping(ACTION_TO_TASK, mapping_override)
    raw_actions = fetch_planner_actions(portfolio_state_path, ledger_path)

    metrics = compute_planner_collision_risk(
        raw_actions,
        top_k,
        ledger,
        signals,
        policy,
        active_mapping,
        exploration_offset=exploration_offset,
        mapping_override=mapping_override,
        capability_ledger=capability_ledger,
    )
    return build_planner_risk_summary(policy_path, top_k, metrics)


def evaluate_planner_configuration(policy_path, top_k, portfolio_state_path, ledger_path,
                                   mapping_override=None, exploration_offset=0):
    """Return operator-facing planner evaluation for a configuration."""
    summary = analyze_planner_configuration(
        policy_path,
        top_k,
        portfolio_state_path,
        ledger_path,
        mapping_override=mapping_override,
        exploration_offset=exploration_offset,
    )
    evaluation = build_planner_evaluation(
        {
            "ranked_action_window": summary["ranked_action_window"],
            "ranked_action_window_detail": summary["ranked_action_window_detail"],
            "mapped_tasks": summary["mapped_tasks"],
            "unique_tasks": summary["unique_tasks"],
            "collapse_count": summary["collapse_count"],
            "collision_ratio": summary["collision_ratio"],
            "task_entropy": summary["task_entropy"],
            "action_entropy": summary["action_entropy"],
        },
        top_k,
    )
    evaluation["policy"] = policy_path
    evaluation["top_k"] = top_k
    return evaluation
