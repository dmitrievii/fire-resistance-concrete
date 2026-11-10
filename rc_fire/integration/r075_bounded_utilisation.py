"""R0.7.5 — rigorously bounded first-order heated-section utilization.

This is a *necessary* equilibrium feasibility bound, not the actual
N-Mx-My member ULS and not a Belarusian R(t) certificate.

From the TKP EN 1992-1-2 heated fibre material envelopes:
 concrete:  0 <= sigma_c <= f_ck * k_c(theta)/gamma_M,fi
 steel:    -f_y(theta) <= sigma_s <= f_y(theta)
 embedded concrete at a bar: 0 <= sigma_cb <= f_ck*k_c(theta_cb)/gamma_M,fi

The force equations in TKPPreparedFibres.force_and_tangent have gross
concrete cells plus bar stress (sigma_s - sigma_cb) at each bar. An LP
relaxes *only strain compatibility* and allows each fibre to take any
stress within the above constitutive envelopes. Its maximum proportional
load factor lambda_upper is therefore >= the capacity of any physically
compatible section state. The output U_lower=1/lambda_upper is a
mathematically defensible lower bound on actual section utilization
within this material/section model. It is generally NOT equal to U.

A lambda_upper<1 demonstrates that even the optimistic, incompatible
stress allocation cannot support the entered N/Mx/My (gross overload).
A converged Newton point or divergence is NEVER used as failure proof.
"""
from __future__ import annotations

import math
import numpy as np
from scipy.optimize import linprog

from rc_fire.materials.tkp_en1992_fire import (
    concrete_parameters, reinforcement_parameters, GAMMA_M_FI)

VERSION="R0.7.5-hot-section-interaction-envelope-bound-v1"


def _finite(v,name):
    if isinstance(v,bool):
        raise ValueError(f"{name} must be finite")
    try: z=float(v)
    except (TypeError,ValueError) as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not math.isfinite(z):
        raise ValueError(f"{name} must be finite")
    return z


def section_interaction_upper_bound(prepared,N_kN,Mx_kNm,My_kNm):
    """Bound lambda_max for one actual N-Mx-My direction.

    LP stress variables are [concrete cells, steel bars, displaced
    concrete at bars] plus lambda. Positions, areas and temperatures
    are the same as the nonlinear fibre model. No positivity assumption
    for Mx/My. A failed LP returns UNKNOWN, not a fabricated U value.
    """
    demand=np.array([_finite(N_kN,"N_kN"),
                     _finite(Mx_kNm,"Mx_kNm"),
                     _finite(My_kNm,"My_kNm")],dtype=float)
    if demand[0]<=0:
        raise ValueError("compression-positive fire-design N must be >0")
    n=len(prepared.area)
    m=len(prepared.bar_area)
    if not n or not m or len(prepared.theta_c)!=n or len(prepared.theta_s)!=m or len(prepared.theta_cb)!=m:
        raise ValueError("concrete and steel source fibres required")
    area_c=np.asarray(prepared.area,dtype=float)
    area_s=np.asarray(prepared.bar_area,dtype=float)
    if not np.all(np.isfinite(area_c)) or not np.all(np.isfinite(area_s)) or np.min(area_c)<=0 or np.min(area_s)<=0:
        raise ValueError("positive source fibre areas required")
    bounds=[]
    for theta in prepared.theta_c:
        p=concrete_parameters(float(theta),aggregate=prepared.aggregate)
        bounds.append((0.,float(prepared.fck_MPa)*p.k_c/GAMMA_M_FI))
    for theta in prepared.theta_s:
        p=reinforcement_parameters(float(theta),
            fyk_MPa=prepared.fyk_MPa,Es_MPa=prepared.Es_MPa,
            production_route=prepared.production_route,
            ductility_class=prepared.ductility_class)
        bounds.append((-p.f_sy_MPa,p.f_sy_MPa))
    for theta in prepared.theta_cb:
        p=concrete_parameters(float(theta),aggregate=prepared.aggregate)
        bounds.append((0.,float(prepared.fck_MPa)*p.k_c/GAMMA_M_FI))
    bounds.append((0.,None))
    # This matches force_and_tangent's [N,Mx,My] m2*MPa*1000
    # conversion exactly; the concrete at rebar centres is SUBTRACTED
    # (gross rather than net concrete area convention).
    xb=np.asarray(prepared.bar_x,dtype=float)-float(prepared.b_m)/2.
    yb=np.asarray(prepared.bar_y,dtype=float)-float(prepared.h_m)/2.
    xc=np.asarray(prepared.x,dtype=float)-float(prepared.b_m)/2.
    yc=np.asarray(prepared.y,dtype=float)-float(prepared.h_m)/2.
    cc=np.vstack((np.ones(n),yc,xc))*area_c[None,:]*1000.
    ss=np.vstack((np.ones(m),yb,xb))*area_s[None,:]*1000.
    A=np.column_stack((cc,ss,-ss,-demand))
    objective=np.zeros(n+2*m+1,dtype=float)
    objective[-1]=-1.
    try:
        sol=linprog(objective,A_eq=A,b_eq=np.zeros(3),
            bounds=bounds,method="highs")
    except (ValueError,ArithmeticError,RuntimeError) as exc:
        return _unknown(f"LP could not be evaluated: {type(exc).__name__}: {exc}")
    if not sol.success or sol.x is None:
        return _unknown("LP did not establish a valid interaction envelope: "
                        +str(sol.message))
    lam=float(sol.x[-1])
    if not math.isfinite(lam) or lam<0:
        return _unknown("nonfinite stress-relaxed interaction multiplier")
    residual=np.linalg.norm((A@sol.x)/np.maximum(
        np.abs(demand),[100.,10.,10.]))
    if not math.isfinite(float(residual)) or residual>1e-5:
        return _unknown("relaxed force equilibrium numerical residual invalid")
    if lam<=1e-12:
        utilization=None
        over=True
    else:
        utilization=100./lam
        over=lam<1.-1e-8
    return {
        "version":VERSION,
        "status":"STRESS_ENVELOPE_UPPER_BOUND_SOLVED",
        "entered_actions_N_Mx_My":demand.tolist(),
        "max_possible_load_factor_upper_bound":lam,
        "section_utilization_lower_bound_pct":utilization,
        "definite_section_overload_in_source_model":bool(over),
        "lp_equilibrium_relative_residual":float(residual),
        "includes_biaxial_interaction":True,
        "uses_actual_steel_and_concrete_temperatures":True,
        "actual_section_utilization_known":False,
        "actual_member_utilization_known":False,
        "normative_member_R_t_minutes":None,
        "bound_direction":"U_section >= 100/lambda_upper, not an equality",
        "interpretation":(
            "Relaxed interaction N-Mx-My envelope ignores compatible strain "
            "and second-order effects; this is a lower bound on use and "
            "a definitive overload test if its value exceeds 100%, "
            "not the actual utilization or fire rating."),
    }


def _unknown(reason):
    return {
        "version":VERSION,"status":"UNRESOLVED",
        "max_possible_load_factor_upper_bound":None,
        "section_utilization_lower_bound_pct":None,
        "definite_section_overload_in_source_model":False,
        "actual_section_utilization_known":False,
        "actual_member_utilization_known":False,
        "normative_member_R_t_minutes":None,
        "reason":reason
    }
