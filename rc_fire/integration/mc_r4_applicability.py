"""MC-R4: explicit scope audit and governing-load comparator.
No automatic fallback, clipped K.27 geometry, production routing or R claim.
"""
from __future__ import annotations

import copy
import math

from rc_fire.integration import mc_r3_reconciliation as mc3
from rc_fire.mechanics.critical_isotherm import _action_plane
from rc_fire.thermal.normative import (
    RectangularExposure, heating_depth_m, temperature_rectangle,
    square_four_face_reduced_section,
)


def early_heating_audit(ex, coeff, time_minutes, critical_C):
    """Distinguish cold, corner-only, and side-heated K.27 domains.

    Surface temperatures are independently checked by K.10. Raw K.21
    depths are retained; the zero-clipped result is a counterfactual only.
    For overlapping opposite heat layers no early-heating inference is made.
    """
    ex.validate()
    if set(ex.faces) != {"left", "right", "bottom", "top"} or abs(ex.b_mm-ex.h_mm)>1e-9:
        raise ValueError("K27_REQUIRES_SQUARE_FOUR_FACE_EXPOSURE")
    h=ex.h_mm/1000
    a=float(coeff["a_red_m2_h"])
    phi=float(coeff["phi_1"])
    T=float(critical_C)
    if not (20<T<1220 and a>0 and phi>=0):
        raise ValueError("INVALID_K27_PROFILE")
    rs=1-math.sqrt((T-20)/1200)
    rd=1-math.sqrt(1-math.sqrt((1220-T)/1200))
    tc=5*(phi/rd)**2
    tf=5*(phi/rs)**2
    t=float(time_minutes)
    l=heating_depth_m(a,t)
    off=phi*math.sqrt(a)
    lc=rs*l-off
    ld=rd*l-off
    side,sm=temperature_rectangle(ex,coeff,t,0,ex.h_mm/2)
    corner,cm=temperature_rectangle(ex,coeff,t,0,0)
    side,corner=float(side),float(corner)
    overlap=l>0 and l>h/2+off
    literal=square_four_face_reduced_section(ex,coeff,t,T)
    candidate=None
    if overlap or bool(sm["outside_approximation_C"]) or bool(cm["outside_approximation_C"]):
        state="EARLY_HEATING_ASSUMPTIONS_NOT_APPLICABLE"
    elif corner<=T:
        state="NO_CONCRETE_ABOVE_CRITICAL"
    elif side<T:
        state="CORNER_ONLY_K27_DOMAIN_UNRESOLVED"
        # Deliberately show why clipping is not an authorized transition.
        candidate=(1-max(ld,0)/(h/2)-.2)*h*h
    elif literal["status"]=="evaluated":
        state="K27_AREA_AVAILABLE_NOT_MECHANICAL_QUALIFICATION"
    else:
        state="K27_DOMAIN_UNRESOLVED"
    return {"time_minutes":t,"state":state,"corner_C":corner,"side_C":side,
            "corner_onset_min":tc,"side_onset_min":tf,
            "raw_lc_m":lc,"raw_ld_m":ld,"literal_K27":literal,
            "full_area_m2":h*h,"unauthorized_clip_counterfactual_m2":candidate,
            "normative_claim":False,"actual_t_R_minutes":None}


def k18_action_scope():
    """Frozen worksheet review actions; not invented real bar coordinates."""
    column={"b_mm":600.,"h_mm":600.,"length_m":13.7,"mu_x":.8,"mu_y":1.2,
            "sections":[{"id":"bottom","z_m":0.,"N_kN":527.16,"Mx_kNm":6.5,"My_kNm":0.},
                        {"id":"top","z_m":13.7,"N_kN":1134.,"Mx_kNm":16.,"My_kNm":-38.9}]}
    axis,issues=_action_plane(column)
    return {"source_actions":column,"axis":axis,"scope_issues":issues,
            "effective_lengths_m":{"x":13.7*.8,"y":13.7*1.2},
            "ambient_gross_slenderness":{"x":13.7*.8*math.sqrt(12)/.6,
                                         "y":13.7*1.2*math.sqrt(12)/.6},
            "complete_legacy_top_check":False,"normative_claim":False,
            "actual_t_R_minutes":None}


def governing_load_comparator(template, *, time_minutes=90., axial_kN=527.16,
                              moment_kNm=6.5, length_m=13.7, **kwargs):
    """K18-inspired uniaxial sensitivity, NOT physical K18 reconstruction.

    Preserve template bar coordinates/material/creep; use identical actions
    for both shapes and report unresolved states without hiding them.
    """
    c=copy.deepcopy(template)
    c.update(length_m=float(length_m),mu_x=.8,mu_y=1.2)
    c["sections"]=[{"id":"synthetic_station","z_m":0.,"N_kN":float(axial_kN),
                    "Mx_kNm":float(moment_kNm),"My_kNm":0.}]
    q=mc3.compare(c,time_minutes,**kwargs)
    return {"classification":"SYNTHETIC_K18_LOAD_SENSITIVITY_NOT_K18_PARITY",
            "inputs":{"N_kN":axial_kN,"Mx_kNm":moment_kNm,"length_m":length_m,
                      "time_minutes":time_minutes},"comparison":q,
            "normative_claim":False,"actual_t_R_minutes":None}
