"""SP-R7: time-matched SP5 coupled-N/M design section and observed limit.

Full coupled matrix from SP5 §8.1.2, beta E Table9/10 and a
hypothesised nominal cross-axis extension of §8.1.6. This is distinct
from the full nonlinear constitutive physical-collapse algorithm.

Observing first MODEL loss is not the first PHYSICAL loss of the
load-bearing RC member. An unobserved time < first stored sample, an
unknown intermediate state, or any unresolved source validation makes
that claim impermissible. R_t_minutes remains None.
"""
from __future__ import annotations
import math
import numpy as np

from rc_fire.mechanics.sp2026_nominal_member import (
    SP5NominalMemberError,prepare_sp2026_design_section)
from rc_fire.mechanics.sp2026_coupled_rigidity import (
    coupled_sp5_hot_section_stiffness,magnify_coupled_first_order_moments)
from rc_fire.thermal.sp2026_heat import (
    SPHeatError,select_sp2026_snapshot)

VERSION="SP-R7-coupled-SP5-nominal-first-model-limit-v1"
WITHIN="EQUILIBRATED_WITHIN_COUPLED_SP5_SECTION_CHECK"
EXCEEDED="EQUILIBRATED_COUPLED_SP5_SECTION_LIMIT_EXCEEDED"
NOMINAL="FIRST_COUPLED_NOMINAL_EULER_MODE_REACHED"
UNKNOWN="UNRESOLVED_COUPLED_SP5_MEMBER_STATE"

def _finite(x,name):
    if isinstance(x,bool):
        raise SP5NominalMemberError(name+" must be a finite number")
    try:value=float(x)
    except (ValueError,TypeError) as exc:
        raise SP5NominalMemberError(name+" must be a finite number") from exc
    if not math.isfinite(value):
        raise SP5NominalMemberError(name+" must be finite")
    return value

def _public_pinned_actions(column,spec):
    """Exact restricted source-supported user-selected pin/pin q scheme."""
    if (not isinstance(spec,dict) or
        spec.get("load_mode")!="explicit_sp2026_beam" or
        spec.get("longitudinal_thermal_mode")!="explicit_uniform_full_length" or
        spec.get("uniform_exposure_confirmed") is not True or
        spec.get("entered_section_moments_reconciled") is not True or
        spec.get("axial_restraint_mode")!="free_axial_expansion"):
        raise SP5NominalMemberError("full explicit pin-pin uniformly heated SP member inputs required")
    L=_finite(column["length_m"],"L")
    if L<=0:raise SP5NominalMemberError("positive member length required")
    z=np.asarray(spec.get("z_m"),dtype=float)
    if z.shape!=(3,) or not np.allclose(z,[0,L/2,L],atol=1e-9,rtol=0):
        raise SP5NominalMemberError("source action diagram requires exactly 0,L/2,L stations")
    for end in ("left_support","right_support"):
        s=spec.get(end)
        if not isinstance(s,dict) or s.get("x")!="pinned" or s.get("y")!="pinned":
            raise SP5NominalMemberError("source model requires pin-pin on both axes")
    N=_finite(spec.get("N_kN"),"N")
    if N<=0:raise SP5NominalMemberError("positive axial design compression required")
    q=np.asarray(spec.get("distributed_load_kNpm"),dtype=float)
    f=np.asarray(spec.get("nodal_forces"),dtype=float)
    imp=np.asarray(spec.get("initial_imperfection"),dtype=float)
    if (q.shape!=(3,2) or f.shape!=(12,) or imp.shape!=(12,)
        or not np.all(np.isfinite(q)) or not np.all(np.isfinite(f)) or
        not np.all(np.isfinite(imp)) or not np.allclose(q,q[0]) or
        np.max(np.abs(f))>1e-12 or
        np.max(np.abs(imp[[0,4,6,10]]))>1e-10):
        raise SP5NominalMemberError("nominal route requires actual constant q, zero nodal F, support-compatible bow")
    # Numeric shape of initial bows follows 4*n vector: x=(w,theta)
    # interleaved, then y=(w,theta) interleaved. Midspan indices 2 and 8.
    ex=float(imp[2]);ey=float(imp[8])
    if max(abs(ex),abs(ey))>=L/10:
        raise SP5NominalMemberError("out-of-domain declared geometric bow")
    mx=N*ex+float(q[0,0])*L**2/8.
    my=N*ey+float(q[0,1])*L**2/8.
    e_min_x=max(float(column["h_mm"])/30.,20.)/1000.
    e_min_y=max(float(column["b_mm"])/30.,20.)/1000.
    mx=math.copysign(max(abs(mx),N*e_min_x),mx if mx else 1.)
    my=math.copysign(max(abs(my),N*e_min_y),my if my else 1.)
    return N,L,np.array([mx,my],dtype=float),{
        "minimum_e_x_m":e_min_x,"minimum_e_y_m":e_min_y,
        "initial_bow_x_m":ex,"initial_bow_y_m":ey,
        "first_order_midspan_from_uniform_q_plus_Ne_only":True,
        "minimum_eccentricity_not_added_twice":True,
        "any_additional_nodal_or_end_moments":False}


def assess_coupled_sp5_nominal_at_time(column,snapshot,member_spec, *,
                                       grid=12,effective_creep_phi):
    N,L,m0,actions=_public_pinned_actions(column,member_spec)
    if snapshot.get("thermal_method")!="SP2026_8.2.23_FVM":
        raise SP5NominalMemberError("SP-R2 time-matched heat only")
    prep=prepare_sp2026_design_section(column,snapshot,grid=grid)
    r=coupled_sp5_hot_section_stiffness(
        prep,N_kN=N,length_m=L,
        effective_creep_phi=effective_creep_phi)
    coupled=magnify_coupled_first_order_moments(r,m0)
    section=None
    if coupled["status"]!="COUPLED_NOMINAL_MOMENTS_COMPUTED":
        status=NOMINAL
    else:
        section=prep.solve_actions(N,*coupled["M2_kNm"])
        from rc_fire.mechanics.action_capacity import (
            WITHIN as SP_WITHIN,EXCEEDED as SP_EXCEEDED)
        if section.get("classification")==SP_WITHIN:
            status=WITHIN
        elif section.get("classification")==SP_EXCEEDED:
            status=EXCEEDED
        else:
            status=UNKNOWN
    return {
        "version":VERSION,
        "time_minutes":float(snapshot["snapshot"]["time_minutes"]),
        "status":status,
        "N_kN":N,
        "first_order_midspan_M0_kNm":m0.tolist(),
        "second_order_coupled_M2_kNm":coupled.get("M2_kNm"),
        "first_order_action_eccentricity_provenance":actions,
        "source_section_check":section,
        "source_secant_3x3_at_section_root":(
            coupled_sp5_hot_section_stiffness(
                prep,N_kN=N,length_m=L,
                effective_creep_phi=effective_creep_phi,
                kind="SP5_8_1_2_SOURCE_SECANT_AT_EQUILIBRIUM",
                unknowns=section["unknowns"])
            if section is not None and
            section.get("classification") not in (
                None,"unresolved_numerical_or_physical_state")
            and section.get("unknowns") is not None else None),
        "nominal_coupled_evidence":r,
        "coupled_action_transformation":coupled,
        "SP5_8_1_2_source_secant_not_equal_8_1_6_nominal":True,
        "thermal_free_curvature_effect_not_qualified":True,
        "SP5_nominal_coupled_extension_not_in_source":True,
        "model_only_first_limit_evidence":status in (EXCEEDED,NOMINAL),
        "first_physical_fire_failure_proven":False,
        "U_member_t":None,"R_t_minutes":None,
        "regulatory_result":"NOT_ESTABLISHED","normative_claim":False}


def scan_coupled_first_model_limit(column,heat,member_spec,
                                   times_minutes,*,grid=12,
                                   effective_creep_phi):
    if (not isinstance(times_minutes,(list,tuple)) or
        not 2<=len(times_minutes)<=24):
        raise SP5NominalMemberError("2..24 explicit stored fire times required")
    times=[_finite(t,"stored time") for t in times_minutes]
    if times[0]<=0 or any(b<=a for a,b in zip(times,times[1:])):
        raise SP5NominalMemberError("stored times must strictly increase")
    samples=[]
    for t in times:
        try:
            value=assess_coupled_sp5_nominal_at_time(
                column,select_sp2026_snapshot(heat,t),
                member_spec,grid=grid,effective_creep_phi=effective_creep_phi)
            samples.append(value)
        except (SP5NominalMemberError,SPHeatError,ValueError,
                ArithmeticError,np.linalg.LinAlgError) as exc:
            samples.append({"time_minutes":t,"status":UNKNOWN,
                            "reason":type(exc).__name__+": "+str(exc),
                            "normative_claim":False})
    bracket=None;prior_unknown=False;loss_before_first=False
    for i,row in enumerate(samples):
        if row["status"]==UNKNOWN:
            prior_unknown=True
        if row["status"] in (EXCEEDED,NOMINAL):
            if i==0:
                loss_before_first=True
            elif not prior_unknown and samples[i-1]["status"]==WITHIN and (
                    all(x["status"]==WITHIN for x in samples[:i])):
                bracket={
                    "last_sampled_model_within_min":samples[i-1]["time_minutes"],
                    "first_sampled_model_limit_min":row["time_minutes"],
                    "first_observed_model_limit_kind":row["status"],
                    "time_interval_unresolved":True,
                    "observed_before_earliest_snapshot":False,
                    "actual_physical_t_R_proven":False}
            break
    return {
        "version":VERSION,
        "status":("OBSERVED_BRACKET_FIRST_MODEL_LIMIT_AFTER_FIRST_SAMPLE"
                  if bracket else "FIRST_MODEL_LIMIT_NOT_BRACKETED"),
        "samples":samples,
        "observed_first_model_limit_interval":bracket,
        "any_unknown_before_candidate":prior_unknown,
        "unobserved_0_to_first_sample":True,
        "limit_already_at_first_sample":loss_before_first,
        "requires_first_physical_failure_validation":True,
        "t_R_minutes":None,
        "U_member_t":None,
        "regulatory_result":"NOT_ESTABLISHED","normative_claim":False}
