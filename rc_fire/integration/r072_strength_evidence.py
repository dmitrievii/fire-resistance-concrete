"""R0.7.2 transparent section-capacity evidence, NOT Belarusian R(t).

These quantities answer separate physical questions:
  1. Material retention from TKP EN 1992-1-2: a weighted reduction of
     concrete *uniaxial strength* and reinforcing-steel yield potential.
     Neither equals N-Mx-My section capacity.
  2. Discrete proportional-load equilibria: largest consecutive sampled
     multiplier lambda >=1 whose fibre equilibrium is WITHIN strain limits.
     There is no continuous-load-path, stability, or normative proof.
  3. Unknown/EXCEEDED at lambda=1: do not show a fabricated reserve or usage.

No Newton nonconvergence implies a physical collapse; no source-silent
interpolation/extrapolation or hidden transformation into whole-member R.
"""
from __future__ import annotations

import math

from rc_fire.materials.tkp_en1992_fire import (
    concrete_parameters, reinforcement_parameters)
from rc_fire.mechanics.action_capacity import WITHIN, EXCEEDED, UNKNOWN

VERSION="R0.7.2-section-strength-evidence-v1"


def material_strength_retention(prepared):
    """Exact source reduction factors, weighted by the actual input fibre areas.

    Uses theta_c for all concrete FVM fibre centres and theta_s for each
    actual bar. Concrete factor is area-weighted k_c(theta), assuming the
    same source f_ck throughout. Steel is sum(As*f_sy(theta)) / sum(As*f_yk),
    not a moment capacity, instability check or remaining member resistance.
    """
    c_weight=0.
    c_total=0.
    for theta,area in zip(prepared.theta_c,prepared.area):
        ratio=concrete_parameters(float(theta),aggregate=prepared.aggregate).k_c
        c_weight+=float(area)*ratio
        c_total+=float(area)
    s_weight=0.
    s_total=0.
    bar_strength_ratios={}
    for name,theta,area in zip(prepared.bar_ids,prepared.theta_s,prepared.bar_area):
        factor=reinforcement_parameters(
            float(theta),fyk_MPa=prepared.fyk_MPa,
            Es_MPa=prepared.Es_MPa,
            production_route=prepared.production_route,
            ductility_class=prepared.ductility_class).k_sy
        bar_strength_ratios[str(name)]=100.*factor
        s_weight+=float(area)*factor
        s_total+=float(area)
    if not c_total>0 or not s_total>0:
        raise ValueError("concrete/steel area must be positive")
    return {
        "version":VERSION,
        "concrete_uniaxial_strength_retained_pct":100.*c_weight/c_total,
        "steel_yield_strength_retained_pct":100.*s_weight/s_total,
        "steel_bar_yield_strength_retained_pct":bar_strength_ratios,
        "scope":"area-weighted source k_c(theta) and k_sy(theta), not N-Mx-My capacity",
        "is_member_capacity":False,
        "is_normative_resistance_check":False
    }


def sampled_action_reserve(section_scans):
    """Consecutive sampled lambda states from 1; never infer a collapse.

    For every entered section, lambda=1 MUST be an explicit converged
    equilibrium. Walk upwards, stopping at first unproved/failed state.
    The shared checked factor is the minimum factor supported in every
    separate section. This is only a discrete-model result; no missing
    point, alternative equilibrium branch or second-order member is proven.
    """
    if not section_scans:
        return _unknown("no section scan supplied")
    observed=[]
    for scan in section_scans:
        source=scan.get("sampled_scale_path") or scan
        samples=source.get("samples") or []
        points={}
        for x in samples:
            try: lam=float(x["lambda"])
            except (ValueError,TypeError,KeyError):continue
            if math.isfinite(lam) and lam>=1.-1e-9:
                points[round(lam,9)]=x.get("classification",UNKNOWN)
        if points.get(1.)!=WITHIN:
            return _unknown("design load factor lambda=1 has no proven within-strain equilibrium")
        ordered=sorted(k for k in points if k>=1.)
        last=1.
        for k in ordered:
            if points[k]!=WITHIN:
                break
            last=k
        observed.append(last)
    multiplier=min(observed)
    if not math.isfinite(multiplier) or multiplier<1.:
        return _unknown("incomplete sampled load path")
    # "upper bound" here refers only to the proportion of the HIGHEST
    # TESTED within-strain reference multiplier, not utilization of the
    # real member. Numeric >=0 means extra checked demand above lambda1.
    # Lambda=1 alone is NOT a capacity reserve, so show None for 0%.
    known_extra=multiplier>1.+1e-9
    return {
        "version":VERSION,
        "status":"SAMPLED_WITHIN_STRAIN_LIMITS",
        "max_consecutively_checked_load_factor":multiplier,
        "discrete_extra_load_tested_pct":100.*(multiplier-1.) if known_extra else None,
        "ratio_to_max_checked_load_pct":100./multiplier if known_extra else None,
        "true_capacity_or_utilization_known":False,
        "classification_at_design_actions":WITHIN,
        "reference_load_multiplier":1.,
        "is_normative_capacity":False,
        "reason":("Only independent sampled fibre-section equilibria were checked. "
                  "The actual member reserve and utilization are not established."),
    }


def _unknown(reason):
    return {"version":VERSION,"status":"UNRESOLVED",
        "max_consecutively_checked_load_factor":None,
        "discrete_extra_load_tested_pct":None,
        "ratio_to_max_checked_load_pct":None,
        "true_capacity_or_utilization_known":False,
        "classification_at_design_actions":UNKNOWN,
        "reference_load_multiplier":1.,
        "is_normative_capacity":False,"reason":reason}
