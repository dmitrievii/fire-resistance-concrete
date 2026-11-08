"""Quasistatic fire-time search over independently evaluated member states.

The load pattern is fixed. Only complete, equilibrated, stable sampled ULS
evidence admits a time. Domain stops and Newton failures never become a
physical failure time. Finite time/z sampling and the inherited material
assumptions do not qualify a normative fire-resistance claim.
"""
from __future__ import annotations

import math

from rc_fire.normative.actions import ACTION_INPUT_CONTRACT

VERSION = "R0.6.9-fire-time-history-v1"
MAX_EVALUATIONS = 1000
LIMIT_STATES = {"strain_limit", "stability_limit"}


def _finite(value):
    if isinstance(value, bool):
        return None
    try:
        x = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return x if math.isfinite(x) else None


def validate_time_controls(end_minutes, step_minutes, tolerance_minutes,
                           max_refinements):
    end, step, tol = map(_finite, (end_minutes, step_minutes, tolerance_minutes))
    if end is None or not 0 < end <= 240:
        raise ValueError("end_minutes must be in (0, 240]")
    if step is None or not 0 < step <= 240:
        raise ValueError("step_minutes must be in (0, 240]")
    if tol is None or not 0 < tol <= step:
        raise ValueError("tolerance_minutes must be positive and <= step_minutes")
    if type(max_refinements) is not int or not 0 <= max_refinements <= 50:
        raise ValueError("max_refinements must be an integer in [0, 50]")
    if step < end / (MAX_EVALUATIONS - 1 - max_refinements):
        raise ValueError("time grid plus refinement exceeds 1000 evaluations")
    return end, step, tol


def classify_member_state(result):
    """Do not equate convergence, missing ULS evidence, or failure of Newton."""
    if not isinstance(result, dict):
        raise TypeError("time evaluator must return a member-evidence dictionary")
    member = result.get("member") or {}
    uls = result.get("uls") or {}
    status = member.get("status")
    eigen = _finite(member.get("tangent_min_eigenvalue"))
    threshold = _finite(member.get("tangent_positivity_threshold", 0.))
    residual = _finite(member.get("relative_equilibrium_residual"))
    critical = uls.get("critical_sample")
    if isinstance(critical, dict):
        critical = {key: critical.get(key) for key in ('location', 'side')
                    if key in critical} | {
            key: _finite(critical[key]) for key in ('z_m', 'element', 'ratio_concrete',
                'ratio_steel', 'maximum_ratio') if key in critical}
    common = {
        "member_status": status,
        "uls_status": uls.get("status"),
        "reason": result.get("reason") or member.get("reason"),
        "maximum_strain_ratio": None,
        "critical_sample": critical,
        "relative_equilibrium_residual": residual,
        "tangent_min_eigenvalue": eigen,
        "blockers": sorted(set(result.get("blockers", []) + uls.get("blockers", []))),
    }
    if result.get("status") == "BLOCKED_INPUT":
        return {**common, "state": "input_unavailable"}
    if result.get("status") == "BLOCKED_MATERIAL_OR_TEMPERATURE_INPUT":
        return {**common, "state": "model_domain_stop"}
    # A nonpositive tangent at an unbalanced Newton trial does not prove
    # instability of an equilibrium branch. The solver supplies both facts.
    if status == "critical_or_nonpositive_tangent":
        resolved = (member.get("equilibrium_at_instability") is True
                    and residual is not None and residual < 1e-7
                    and eigen is not None and threshold is not None and threshold >= 0
                    and eigen <= threshold)
        return {**common, "state": "stability_limit" if resolved else "numerical_unresolved"}
    if status not in ("evaluated_diagnostic", "strain_limits_exceeded_diagnostic"):
        return {**common, "state": "numerical_unresolved"}
    samples = uls.get("samples") or []
    gauss, node = uls.get("gauss_count"), uls.get("node_side_count")
    coverage = (type(gauss) is int and gauss > 0 and gauss % 3 == 0
                and type(node) is int and node == 2 * (gauss // 3)
                and len(samples) == gauss + node == uls.get("sampled_locations")
                and uls.get("node_coverage") is True
                and uls.get("all_sampled_limits_resolved") is True)
    ratios = [_finite(s.get("maximum_ratio")) for s in samples]
    checks = all(s.get("limit_check") in ("within_diagnostic_limits", "exceeded")
                 for s in samples)
    local_blockers = {'NODE_SECTION_EQUILIBRIUM_NOT_RESOLVED',
                      'NODE_SECTION_TANGENT_NOT_POSITIVE',
                      'GAUSS_STATION_EVIDENCE_INCOMPLETE',
                      'END_AND_INTERIOR_NODES_NOT_ASSESSED',
                      'LOCAL_STRAIN_LIMIT_INFORMATION_MISSING'}
    if (not coverage or not checks or local_blockers.intersection(common['blockers'])
            or any(v is None or v < 0 for v in ratios)
            or residual is None or residual >= 1e-7
            or eigen is None or threshold is None or threshold < 0 or eigen <= threshold):
        return {**common, "state": "evidence_incomplete"}
    ratio = max(ratios)
    common["maximum_strain_ratio"] = ratio
    exceeded = sum(s["limit_check"] == "exceeded" for s in samples)
    if (uls.get("status") == "DIAGNOSTIC_STRAIN_LIMIT_EXCEEDED"
            and exceeded > 0 and exceeded == uls.get("exceeded_count")
            and ratio > 1 + 1e-8):
        return {**common, "state": "strain_limit"}
    if (uls.get("status") == "SAMPLED_STRAINS_WITHIN_LIMITS_NOT_NORMATIVE_ULS"
            and status == "evaluated_diagnostic" and exceeded == 0
            and uls.get("exceeded_count") == 0 and ratio <= 1 + 1e-8
            and not member.get("any_strain_limit_exceeded")):
        return {**common, "state": "admitted_sample"}
    return {**common, "state": "evidence_incomplete"}


def scan_fire_history(evaluate_at_minutes, *, end_minutes, step_minutes=5.,
                      tolerance_minutes=.25, max_refinements=20):
    """Locate the first *observed* non-admitted state, starting at t=0.

    Each midpoint is a fresh thermal/mechanical solve, never interpolated
    temperatures or utilization. A sampled transition is not a continuous
    lower bound: unobserved excursions between time samples are not excluded.
    Programming errors propagate instead of masquerading as physical limits.
    """
    end, step, tol = validate_time_controls(end_minutes, step_minutes,
                                           tolerance_minutes, max_refinements)
    records = {}

    def evaluate(t, phase):
        if t not in records:
            result = evaluate_at_minutes(t)
            row = classify_member_state(result)
            # The single-state audit's old missing-driver marker does not
            # describe this time driver. Keep every physical qualification.
            row["blockers"] = [b for b in row["blockers"]
                               if b != "FULL_FIRE_R_T_NOT_IMPLEMENTED"]
            records[t] = {**row, "time_minutes": t, "phase": phase}
        return records[t]

    baseline = evaluate(0., "initial")
    lo = 0. if baseline["state"] == "admitted_sample" else None
    hi = None if lo is not None else 0.
    if lo is not None:
        for i in range(1, math.ceil(end / step) + 1):
            t = min(end, i * step)
            if evaluate(t, "coarse")["state"] != "admitted_sample":
                hi = t
                break
            lo = t
    if hi is not None and lo is not None:
        for _ in range(max_refinements):
            if hi - lo <= tol:
                break
            mid = (lo + hi) / 2.
            if evaluate(mid, "refinement")["state"] == "admitted_sample":
                lo = mid
            else:
                hi = mid

    event = records[hi] if hi is not None else None
    event_state = event["state"] if event else None
    refined = hi is not None and lo is not None and hi - lo <= tol
    status = {
        "strain_limit": "OBSERVED_STRAIN_LIMIT_BRACKETED",
        "stability_limit": "OBSERVED_STABILITY_LIMIT_BRACKETED",
        "model_domain_stop": "MODEL_DOMAIN_REACHED",
        "input_unavailable": "INPUT_NOT_READY",
        "numerical_unresolved": "NUMERICAL_SOLUTION_UNRESOLVED",
        "evidence_incomplete": "ULS_EVIDENCE_INCOMPLETE",
        None: "SAMPLED_INTERVAL_WITHIN_DIAGNOSTIC_LIMITS",
    }[event_state]
    if event_state in LIMIT_STATES:
        if lo is None:
            status = "LIMIT_AT_INITIAL_STATE_DIAGNOSTIC"
        elif not refined:
            status = "LIMIT_BRACKET_TOLERANCE_NOT_REACHED"
    blockers = {"QUASISTATIC_TIME_HISTORY_NOT_NORMATIVELY_QUALIFIED",
                "CONTINUOUS_TIME_ULS_NOT_QUALIFIED"}
    for row in records.values():
        blockers.update(row["blockers"])
    boundary = ({"last_admitted_minutes": lo, "first_nonadmitted_minutes": hi,
                 "state": event_state, "width_minutes": hi - lo if lo is not None else None,
                 "tolerance_reached": refined} if event else None)
    observed_limit = ([lo, hi] if refined and event_state in LIMIT_STATES else None)
    return {
        "version": VERSION, "status": status,
        "controls": {"end_minutes": end, "step_minutes": step,
                     "tolerance_minutes": tol, "max_refinements": max_refinements},
        "samples": [records[t] for t in sorted(records)],
        "evaluation_count": len(records), "last_admitted_time_minutes": lo,
        "boundary": boundary, "observed_limit_bracket_minutes": observed_limit,
        "fire_resistance_minutes": None,
        "sampled_horizon_completed": event is None,
        "continuous_time_coverage": False, "continuous_lower_bound_proven": False,
        "thermal_path_model": "independent_quasistatic_states_no_creep_history",
        "fire_action_input_contract": ACTION_INPUT_CONTRACT,
        "fire_combination_recalculated": False,
        "blockers": sorted(blockers),
        "normative_claim": False, "fire_resistance_status": "not_demonstrated",
    }
