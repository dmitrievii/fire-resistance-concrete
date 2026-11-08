"""R0.6.9: time-resolved Belarus Annex K + heated section/member evidence.

A chronological trace is NOT the same as a certified R(t). The first
unqualified material point is RIGHT CENSORING of evidence, never a fire
resistance failure. Iteration failure is likewise not a structural failure.

The existing FE member solver is invoked ONLY if the user has explicitly
defined a real member model under R0.6.7. No moments are converted into an
invented transverse-load distribution.
"""
from __future__ import annotations
import copy
import math
from rc_fire.thermal import evaluate_rectangular_column
from rc_fire.mechanics import evaluate_column_mechanics
from .table3 import evaluate_table3_class

VERSION="R0.6.9-temporal-evidence-v1"
GOOD="SAMPLED_SECTION_EQUILIBRIUM_DIAGNOSTIC"
EXCEEDED="SAMPLED_STRAIN_LIMIT_EXCEEDED_DIAGNOSTIC"
UNKNOWN="UNRESOLVED_NUMERICAL_EVIDENCE"
SCOPE="OUTSIDE_MATERIAL_OR_THERMAL_SCOPE"
MISSING="INCOMPLETE_INPUT"
MAX_STEPS=61


def _float(v,label,*,min_v=0.,max_v=240.,strict=False):
    if isinstance(v,bool):raise ValueError(label+": finite number required")
    try:x=float(v)
    except (TypeError,ValueError) as exc:raise ValueError(label+": finite number required") from exc
    if not math.isfinite(x) or (x<=min_v if strict else x<min_v) or x>max_v:
        raise ValueError(label+": outside allowed numerical interval")
    return x


def _times(horizon,step):
    if horizon==0:return [0.]
    n=int(math.floor(horizon/step))
    out=[round(i*step,9) for i in range(n+1)]
    if out[-1] < horizon-1e-7:out.append(horizon)
    if len(out)>MAX_STEPS:raise ValueError("Too many time stations; increase step")
    return out


def evaluate_station(column,minutes,*,grid=12,policy="reject",with_member=False):
    """One immutable snapshot at t, with all original fire-design loads."""
    c=copy.deepcopy(column)
    c["fire_minutes"]=float(minutes)
    thermal=evaluate_rectangular_column(c,grid=grid)
    note=list(thermal.get("issues") or [])
    status_th=thermal.get("status")
    record={
        "time_min":float(minutes),"state":UNKNOWN,
        "thermal_status":status_th,
        "temperature_max_C":thermal.get("max_temperature_C"),
        "bar_temperature_max_C":max((b["theta_C"] for b in thermal.get("reinforcement",[])),
                                    default=None),
        "area_after_critical_isotherm_m2":(thermal.get("critical_section") or {}).get("remaining_area_m2"),
        "thermal_warnings":note,
        "material_policy":policy,"section_solver_status":None,
        "section_results":{},"member_status":None,
    }
    if status_th not in ("evaluated","evaluated_with_scope_warnings"):
        record["state"]=SCOPE
        record["reasons"]=[str(thermal.get("reason") or thermal.get("missing") or status_th)]
        return record
    mechanics=evaluate_column_mechanics(c,thermal,grid=grid,above_800_policy=policy)
    record["section_solver_status"]=mechanics.get("status")
    record["reasons"]=list(mechanics.get("issues") or [])
    recs=mechanics.get("sections") or {}
    record["section_results"]={
        k:{"state":v.get("status"),"equilibrium":v.get("equilibrium"),
           "strain_limits_satisfied":v.get("strain_limits_satisfied"),
           "relative_residual":v.get("relative_residual")}
        for k,v in recs.items()
    }
    expected=len(column.get("sections") or [])
    if not expected or any(any(s.get(k) is None for k in ("N_kN","Mx_kNm","My_kNm"))
                           for s in column.get("sections",[])):
        record["state"]=MISSING
    elif mechanics.get("status")=="blocked":
        record["state"]=SCOPE
    elif len(recs)!=expected or any(v.get("status")=="loads_missing" for v in recs.values()):
        record["state"]=MISSING
    elif all(v.get("status")=="equilibrium_within_strain_limits" for v in recs.values()):
        record["state"]=GOOD
    elif all(v.get("status") in ("equilibrium_within_strain_limits","strain_limits_exceeded")
             for v in recs.values()) and any(v.get("status")=="strain_limits_exceeded"
                                            for v in recs.values()):
        record["state"]=EXCEEDED
    else:
        record["state"]=UNKNOWN
    if policy=="zero_strength_diagnostic":
        record["explicit_high_temperature_assumption"]=True
        record["research_only"]=True
        # Never mix a research extrapolation with the standard-scope evidence.
        record["state"]=("RESEARCH_"+record["state"])
    if with_member and not record["state"].startswith("OUTSIDE"):
        from rc_fire.integration.r067 import evaluate_uniform_fire_member
        member=evaluate_uniform_fire_member(c,thermal=thermal)
        record["member_status"]=member.get("status")
        record["member_uls_status"]=(member.get("uls") or {}).get("status")
        record["member_blockers"]=member.get("blockers") or (member.get("uls") or {}).get("blockers",[])
        record["member_normative_claim"]=False
    return record


def evaluate_resistance_history(column,*,horizon_minutes=None,step_minutes=15.,
                                grid=12,policy="reject",with_member=False,
                                refine_passes=0):
    """Sample full temperature/section/member evidence from t=0 to horizon.

    An OBSERVED strain-boundary bracket is diagnostic numerical evidence; it
    cannot be called the physical R time without independently qualified
    constitutive response, buckling, spalling, and time continuity.
    """
    if policy not in ("reject","zero_strength_diagnostic"):
        raise ValueError("Unsupported high-temperature policy")
    if type(with_member) is not bool:raise ValueError("with_member must be boolean")
    if type(refine_passes) is not int or not 0<=refine_passes<=6:
        raise ValueError("refine_passes must be 0..6")
    h=_float(column.get("fire_minutes") if horizon_minutes is None else horizon_minutes,
             "time horizon",max_v=240.)
    dt=_float(step_minutes,"time step",min_v=0.,max_v=240.,strict=True)
    if type(grid) is not int or not 12<=grid<=48:
        raise ValueError("time-history calculation grid must be 12..48")
    times=_times(h,dt)
    evaluated=[evaluate_station(column,t,grid=grid,policy=policy,
                                with_member=with_member) for t in times]
    # A gap is not a failure; never interpolate through missing or undefined
    # numerical states. First observed (pass,exceeded) adjacent interval only.
    pair=None
    if policy=="reject":
        for prev,curr in zip(evaluated,evaluated[1:]):
            if prev["state"]==GOOD and curr["state"]==EXCEEDED:
                pair=[prev,curr]
                break
    refined=[]
    if pair and refine_passes:
        left,right=pair
        for _ in range(refine_passes):
            midpoint=(left["time_min"]+right["time_min"])/2.
            r=evaluate_station(column,midpoint,grid=grid,policy=policy,
                               with_member=with_member)
            refined.append(r)
            if r["state"]==GOOD:left=r
            elif r["state"]==EXCEEDED:right=r
            else:
                pair=None
                break
        else:pair=[left,right]
    trace=sorted(evaluated+refined,key=lambda x:x["time_min"])
    observed=([pair[0]["time_min"],pair[1]["time_min"]] if pair else None)
    first_outside=next((r["time_min"] for r in trace if r["state"]==SCOPE),None)
    first_unresolved=next((r["time_min"] for r in trace if r["state"] in (UNKNOWN,MISSING)),None)
    first_exceeded=next((r["time_min"] for r in trace if r["state"]==EXCEEDED),None)
    tabular=evaluate_table3_class(column)
    return {
        "version":VERSION,"status":("DIAGNOSTIC_LIMIT_BRACKETED" if observed
                   else "CENSORED_AT_MODEL_SCOPE" if first_outside is not None
                   else "INCOMPLETE_EVIDENCE" if first_unresolved is not None
                   else "NO_DIAGNOSTIC_LIMIT_OBSERVED"),
        "time_horizon_min":h,"time_step_min":dt,"grid":grid,
        "high_temperature_policy":policy,"with_member":with_member,
        "samples":trace,
        "sampled_time_count":len(trace),
        "first_outside_scope_min":first_outside,
        "first_unresolved_min":first_unresolved,
        "first_observed_strain_exceedance_min":first_exceeded,
        "diagnostic_limit_bracket_min":observed,
        "table3":tabular,
        "computed_exact_R_min":None,
        "normative_class_approved":None,
        "normative_claim":False,
        "fire_resistance_status":"not_demonstrated",
        "method_notes":[
            "Temperature from Belarus Annex K, simultaneous section N/Mx/My from R0.6.3.",
            "First solver nonconvergence is not structural failure.",
            "Hot-boundary material coefficients beyond 800 C censor the legal numerical evidence.",
            "Observed strain exceedance is not automatically a verified full-column failure.",
            "Member evaluation, when selected, uses explicit R0.6.7 inputs; section Mx/My do not generate a member load diagram.",
            "Table 3 returns conditional discrete R classes, never exact physical failure time.",
            "No normative resistance class is approved by this numerical evidence.",
        ],
    }
