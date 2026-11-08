"""СП 2.02.05-2026 §8.2.11, Table 3: column tabular CLASS candidate.

A table R class is a discrete design classification, NOT the exact failure
instant t_R. This module checks the numeric table but never upgrades the
existing not-qualified normative contract to a positive certificate.
"""
from __future__ import annotations
import math
from rc_fire.normative.preflight import evaluate_tabular_column_scope

VERSION="R0.6.9-BY-table3-scoped-v1"
R_CLASSES=(30,60,90,120,180)
# Rows: coefficient of utilisation η at normal-temperature axial capacity;
# each alternative is (min b in mm, min axis distance c in mm).
TABLE_3={
    0.3:{
      30:((200,25),),60:((200,25),),
      90:((200,31),(300,25)),
      120:((250,40),(350,35)),180:((350,45),)},
    0.5:{
      30:((200,25),),60:((200,36),(300,31)),
      90:((300,45),(400,38)),
      120:((350,45),(450,40)),180:((350,63),)},
    0.7:{
      30:((200,32),(300,27)),60:((250,46),(350,40)),
      90:((350,53),(450,40)),
      120:((350,57),(450,51)),180:((450,70),)},
}


def _finite_positive(value):
    try:
        x=float(value)
        return x if math.isfinite(x) and x>0 else None
    except (ValueError,TypeError):
        return None


def reinforcement_axis_distance_mm(column):
    """Minimum from EVERY bar centre to any external face, conservative."""
    try:
        b,h=map(float,(column["b_mm"],column["h_mm"]))
        if b<=0 or h<=0 or not column.get("bars"):return None
        values=[]
        for bar in column["bars"]:
            x,y=float(bar["x_mm"]),float(bar["y_mm"])
            if not 0<x<b or not 0<y<h:return None
            values.extend((x,b-x,y,h-y))
        return min(values)
    except (KeyError,TypeError,ValueError):
        return None


def _geometric_classes(width_mm,axis_distance_mm,eta_band):
    if width_mm is None or axis_distance_mm is None:return []
    return [r for r in R_CLASSES if any(
        width_mm+1e-9>=req_b and axis_distance_mm+1e-9>=req_c
        for req_b,req_c in TABLE_3[eta_band][r])]


def evaluate_table3_class(column):
    """Evaluate conditional table-3 categories for the specified fire actions.

    N_Rd_normal_temperature_kN must be the separately calculated *normal*
    axial resistance of this member's section, not the diagnostic 0.5.6 u
    or a fabricated high-temperature strength. It is NEVER inferred here.
    """
    pre=evaluate_tabular_column_scope(column)
    b=_finite_positive(column.get("b_mm"))
    h=_finite_positive(column.get("h_mm"))
    width=min(b,h) if b is not None and h is not None else None
    c=reinforcement_axis_distance_mm(column)
    NRd=_finite_positive(column.get("N_Rd_normal_temperature_kN"))
    forces=[_finite_positive(x.get("N_kN")) for x in column.get("sections",())]
    if not forces or any(v is None for v in forces):nmax=None
    else:nmax=max(forces)
    eta=None if NRd is None or nmax is None else nmax/NRd
    all_bands={str(k):_geometric_classes(width,c,k) for k in TABLE_3}
    eband=next((k for k in TABLE_3 if eta is not None and eta<=k+1e-12),None)
    matches=_geometric_classes(width,c,eband) if eband is not None else []
    # This is not a general verified two-axis member ULS route.
    bi_axial=any(
        (s.get("Mx_kNm") is not None and s.get("My_kNm") is not None
         and abs(float(s["Mx_kNm"]))>1e-12 and abs(float(s["My_kNm"]))>1e-12)
        for s in column.get("sections",()))
    reasons=list(pre["failures"])+list(pre["missing"])
    if c is None:reasons.append("actual axis distance of all bars is unresolved")
    if bi_axial:reasons.append("simultaneous Mx/My: applicability of tabular uniaxial eccentricity rule unverified")
    if eta is not None and eta>0.7:reasons.append("eta exceeds maximum table 3 band 0.7")
    if not column.get("fire_exposure_provenance"):
        reasons.append("actual exposure to fire not verified against authored faces")
    status=("OUTSIDE_TABLE_SCOPE" if pre["failures"] or (eta is not None and eta>0.7)
            else "CONDITIONAL_TABLE_CANDIDATE" if matches and not reasons
            else "INSUFFICIENT_EVIDENCE")
    return {
        "version":VERSION,"status":status,
        "source":"СП 2.02.05-2026, 8.2.11, Table 3; notes and Eq. (5)",
        "eta":eta,"eta_band":eband,"fire_design_N_max_kN":nmax,
        "normal_temperature_N_Rd_kN":NRd,
        "reference_width_mm":width,"min_bar_axis_distance_mm":c,
        "geometric_classes_by_eta_band":all_bands,
        "conditional_class_max_min":max(matches) if matches else None,
        "conditional_classes_min":matches,"missing_or_unverified":sorted(set(reasons)),
        "two_axis_actions":bi_axial,
        "normative_claim":False,"fire_resistance_status":"not_demonstrated",
        "exact_failure_time_min":None,
        "method_notice":"Conditional Table 3 R class is not a computed failure time.",
    }
