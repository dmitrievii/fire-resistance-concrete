"""SP-R8C matched analytical/FVM quasistatic time histories.

No interpolation between thermal times, no conversion of numerical failures
to physical collapse, no regulatory R. All FVM studies share the same fine
output schedule so output-induced step truncation is not a hidden variable.
"""
from __future__ import annotations
import copy
import math
import numpy as np
from rc_fire.thermal.sp2026_annex_k_field import (
    ANNEX_K_METHOD, build_annex_k_snapshot, sample_annex_k_temperature)
from rc_fire.thermal.sp2026_heat import (
    solve_sp2026_2d_heat, select_sp2026_snapshot, sample_sp2026_temperature)
from rc_fire.mechanics.sp2026_coupled_first_limit import (
    assess_coupled_sp5_nominal_at_time, WITHIN, EXCEEDED, NOMINAL, UNKNOWN)

VERSION="SP-R8C-unified-time-history-v1"
FVM="SP2026_8.2.23_FVM"
LIMITS=(EXCEEDED,NOMINAL)
ERRORS=(ValueError,ArithmeticError,np.linalg.LinAlgError)

def _schedule(times, duration):
    ts=[float(t) for t in times]
    if (len(ts)<2 or len(ts)>240 or not all(math.isfinite(t) for t in ts)
        or ts[0]!=0 or ts[-1]!=duration
        or any(a>=b for a,b in zip(ts,ts[1:]))):
        raise ValueError("strict schedule from zero through full duration, 2..240 times required")
    return ts

def first_observed_model_event(rows):
    """Sampled evidence only. No continuity/monotonicity assumption."""
    prior_unknown=False
    for i,r in enumerate(rows):
        state=r["status"]
        if state==WITHIN:
            continue
        if state not in LIMITS:
            prior_unknown=True
            continue
        if i==0:
            return {"status":"LIMIT_AT_INITIAL_STATE","interval_min":[0.,0.],
                    "kind":state,"continuous_first_loss_proven":False}
        if prior_unknown:
            return {"status":"UNKNOWN_BEFORE_OBSERVED_LIMIT","interval_min":None,
                    "kind":state,"first_observed_limit_min":r["time_minutes"]}
        return {"status":"OBSERVED_BRACKET","kind":state,
                "interval_min":[rows[i-1]["time_minutes"],r["time_minutes"]],
                "continuous_first_loss_proven":False}
    return {"status":"UNRESOLVED_HISTORY" if prior_unknown else "NO_LIMIT_AT_SAMPLED_TIMES",
            "interval_min":None,"kind":None,"continuous_first_loss_proven":False}

def _temperature_inventory(column,field):
    method=field["thermal_method"]
    point=sample_annex_k_temperature if method==ANNEX_K_METHOD else sample_sp2026_temperature
    b,h=float(column["b_mm"]),float(column["h_mm"])
    # Common physical points independent of heat and mechanical grids.
    temps={f"concrete:{i}:{j}":point(field,b*i/4,h*j/4)
           for i in range(5) for j in range(5)}
    for bar in column["bars"]:
        x,y,d=bar["x_mm"],bar["y_mm"],bar["diameter_mm"]
        name=str(bar["id"])
        temps["bar_concrete:"+name]=point(field,x,y)
        temps["bar_steel:"+name]=(point(field,x,y,bar_diameter_mm=d)
                                  if method==ANNEX_K_METHOD else point(field,x,y))
    return temps

def evaluate_history(column, member_spec, *, method, times_minutes,
                     effective_creep_phi, mechanical_grid=12,
                     boundary=None, heat_grid=16, max_step_minutes=1.,
                     bar_distance_convention="clear", fvm_heat=None):
    """One exact route. For FVM a precomputed field can be reused internally.

    Do not silently substitute another thermal method after a scope/domain stop.
    """
    c=copy.deepcopy(column)
    duration=float(c["fire_minutes"])
    ts=_schedule(times_minutes,duration)
    if method not in (ANNEX_K_METHOD,FVM):
        raise ValueError("explicit SP thermal method required")
    if type(mechanical_grid) is not int or not 8<=mechanical_grid<=80:
        raise ValueError("mechanical grid 8..80 required")
    heat=fvm_heat
    heat_problem=None
    if method==FVM:
        try:
            if heat is None:
                heat=solve_sp2026_2d_heat(c,boundary=boundary,cell_count_x=heat_grid,
                    cell_count_y=heat_grid,max_step_minutes=max_step_minutes,
                    sample_times_minutes=ts)
            # Guard internal reuse; exact schedule, physical metadata and boundary.
            g=heat["grid"]
            tp=c["thermal_spec"]
            if (heat["thermal_method"]!=FVM or heat["time_minutes"]!=duration
                or g["nx"]!=heat_grid or g["ny"]!=heat_grid
                or abs(g["width_mm"]-c["b_mm"])>1e-6
                or abs(g["height_mm"]-c["h_mm"])>1e-6
                or heat["boundary_parameters"]!=boundary
                or heat["material_family"]!=tp["concrete_family"]
                or heat["dry_density_kg_m3"]!=tp["dry_density_kg_m3"]
                or set(heat["exposed_faces"])!=set(tp["exposed_faces"])
                or any(step["dt_minutes"]>max_step_minutes+1e-8 for step in heat["step_log"])):
                raise ValueError("incompatible FVM source field")
        except ERRORS as exc:
            heat_problem=type(exc).__name__+": "+str(exc)
    rows=[]
    for t in ts:
        row={"time_minutes":t,"status":UNKNOWN,"temperature_method":method}
        if heat_problem is not None:
            row["reason"]=heat_problem
            rows.append(row)
            continue
        try:
            field=(build_annex_k_snapshot(c,t,bar_distance_convention=bar_distance_convention)
                   if method==ANNEX_K_METHOD else select_sp2026_snapshot(heat,t))
            row["temperatures_C"]=_temperature_inventory(c,field)
            result=assess_coupled_sp5_nominal_at_time(c,field,member_spec,
                         grid=mechanical_grid,effective_creep_phi=effective_creep_phi)
            r=result["nominal_coupled_evidence"]
            row.update(status=result["status"],
                       D_kNm2=r["nominal_2x2_D_kNm2"],
                       Ncrit_kN=r["principal_Euler_Ncrit_kN"],
                       N_over_Ncrit_nominal=coupled_ratio(result["N_kN"],r),
                       M2_kNm=result["second_order_coupled_M2_kNm"],
                       secant_available=result["source_secant_3x3_at_section_root"] is not None,
                       thermal_provenance=result["thermal_source_provenance"])
        except ERRORS as exc:
            row["reason"]=type(exc).__name__+": "+str(exc)
        rows.append(row)
    return {"version":VERSION,"method":method,"duration_minutes":duration,
            "mechanical_grid":mechanical_grid,
            "heat_grid":heat_grid if method==FVM else None,
            "max_step_minutes":max_step_minutes if method==FVM else None,
            "bar_distance_convention":bar_distance_convention if method==ANNEX_K_METHOD else None,
            "rows":rows,"first_event":first_observed_model_event(rows),
            "energy_balance":heat.get("energy_balance") if heat and heat_problem is None else None,
            "initial_state_sampled":True,"continuous_first_loss_proven":False,
            "actual_t_R_minutes":None,"U_member_t":None,"normative_claim":False}

def coupled_ratio(N,r):
    # This is Euler modal utilization only, not section or physical member U(t).
    return float(N)/float(r["minimum_nominal_Euler_Ncrit_kN"])

def _reldelta(a,b):
    if a is None or b is None:
        return None
    aa,bb=np.asarray(a,dtype=float),np.asarray(b,dtype=float)
    if aa.shape!=bb.shape or not np.all(np.isfinite(aa)) or not np.all(np.isfinite(bb)):
        return None
    return float(np.linalg.norm(aa-bb)/max(np.linalg.norm(bb),1e-12))

def compare_events(a,b, tolerance_minutes):
    aa,bb=a["first_event"],b["first_event"]
    ia,ib=aa["interval_min"],bb["interval_min"]
    if aa["status"]==bb["status"]=="NO_LIMIT_AT_SAMPLED_TIMES":
        return {"status":"NO_LIMIT_OBSERVED_ON_EITHER_SCHEDULE","within_tolerance":True,
                "physical_survival_proven":False}
    if ia is None or ib is None:
        return {"status":"EVENT_COMPARISON_UNRESOLVED","within_tolerance":False}
    delta=max(abs(ia[0]-ib[0]),abs(ia[1]-ib[1]))
    overlap=max(ia[0],ib[0])<=min(ia[1],ib[1])
    same=aa["kind"]==bb["kind"] and aa["status"]==bb["status"]
    return {"status":"MODEL_EVENT_INTERVAL_COMPARISON","a_interval_min":ia,"b_interval_min":ib,
            "max_endpoint_delta_min":delta,"overlap":overlap,"same_kind":same,
            "within_tolerance":same and overlap and delta<=tolerance_minutes,
            "physical_failure_proven":False}

def compare_histories(a,b,*,temperature_tolerance_C=10.,relative_tolerance=.03,
                      event_tolerance_minutes=5.):
    aa={r["time_minutes"]:r for r in a["rows"]}
    bb={r["time_minutes"]:r for r in b["rows"]}
    shared=sorted(set(aa)&set(bb))
    records=[]
    for t in shared:
        x,y=aa[t],bb[t]
        tx,ty=x.get("temperatures_C"),y.get("temperatures_C")
        td=(max(abs(tx[k]-ty[k]) for k in tx) if tx and ty and tx.keys()==ty.keys()
            else None)
        delta={k:_reldelta(x.get(k),y.get(k)) for k in ("D_kNm2","Ncrit_kN","M2_kNm")}
        same=x["status"]==y["status"] and x["status"]!=UNKNOWN
        # Both Euler-limit states may lack amplified moments by definition.
        moment_ok=(delta["M2_kNm"] is not None and delta["M2_kNm"]<=relative_tolerance
                   or same and x["status"]==NOMINAL and
                   x.get("M2_kNm") is None and y.get("M2_kNm") is None)
        ok=(same and td is not None and td<=temperature_tolerance_C and moment_ok
            and all(delta[k] is not None and delta[k]<=relative_tolerance
                    for k in ("D_kNm2","Ncrit_kN")))
        records.append({"time_minutes":t,"a_state":x["status"],"b_state":y["status"],
                        "max_temperature_delta_C":td,"relative_deltas":delta,
                        "within_numerical_tolerances":bool(ok)})
    event=compare_events(a,b,event_tolerance_minutes)
    return {"shared_time_comparisons":records,"event_comparison":event,
            "all_shared_times_resolved_and_within_tolerance":bool(records) and
             all(r["within_numerical_tolerances"] for r in records),
            "both_complete_histories_resolved":all(
                r["status"] in (WITHIN,*LIMITS) for h in (a,b) for r in h["rows"]),
            "normative_claim":False}

def _subset(history,ts):
    rows=[r for r in history["rows"] if r["time_minutes"] in ts]
    return {**history,"rows":rows,"first_event":first_observed_model_event(rows)}

def run_fire_duration_campaign(column,member_spec,*,boundary,coarse_times_minutes,
        fine_times_minutes,thermal_grids=(12,24),time_steps=(2.,1.),
        mechanical_grids=(12,24),effective_creep_phi,temperature_tolerance_C=10.,
        relative_tolerance=.03,event_tolerance_minutes=5.):
    """Independent spatial, integration-time, mechanical, output-sampling studies.

    Two nested observation schedules; all FVM integrations store fine times.
    No extra heat solve for the mechanical or observation refinement.
    """
    c=copy.deepcopy(column)
    duration=float(c["fire_minutes"])
    coarse=_schedule(coarse_times_minutes,duration)
    fine=_schedule(fine_times_minutes,duration)
    if not set(coarse)<set(fine):
        raise ValueError("strictly nested observation schedules required")
    g0,g1=thermal_grids
    d0,d1=time_steps
    m0,m1=mechanical_grids
    if not (4<=g0<g1<=80 and .25<=d1<d0<=30 and 8<=m0<m1<=80):
        raise ValueError("strict mesh and timestep refinements required")
    if not all(math.isfinite(x) and x>0 for x in
               (temperature_tolerance_C,relative_tolerance,event_tolerance_minutes)):
        raise ValueError("positive numerical tolerances required")
    # Match the physical moisture inputs; do not compare a default K table
    # moisture to an unrelated FVM value.
    initial=build_annex_k_snapshot(c,0.)
    if abs(initial["annex_k_coefficients"]["Wc_mass_percent"]-
           boundary["moisture_mass_pct"])>1e-9:
        raise ValueError("K and FVM moisture inputs must match")
    common=dict(times_minutes=fine,effective_creep_phi=effective_creep_phi)
    k0=evaluate_history(c,member_spec,method=ANNEX_K_METHOD,mechanical_grid=m0,**common)
    k1=evaluate_history(c,member_spec,method=ANNEX_K_METHOD,mechanical_grid=m1,**common)
    kc=evaluate_history(c,member_spec,method=ANNEX_K_METHOD,mechanical_grid=m1,
                        bar_distance_convention="centre",**common)
    histories={"K_coarse_mechanics":k0,"K_fine_mechanics":k1,"K_centre":kc}
    for name,g,dt in (("FVM_coarse_space",g0,d0),("FVM_fine_space",g1,d0),
                      ("FVM_fine_time",g1,d1)):
        try:
            solved=solve_sp2026_2d_heat(c,boundary=boundary,cell_count_x=g,cell_count_y=g,
                               max_step_minutes=dt,sample_times_minutes=fine)
        except ERRORS:
            # evaluate_history retains a complete unresolved schedule if the solve fails.
            solved=None
        histories[name]=evaluate_history(c,member_spec,method=FVM,boundary=boundary,
             heat_grid=g,max_step_minutes=dt,mechanical_grid=m0,fvm_heat=solved,**common)
        if name=="FVM_fine_time":
            histories["FVM_fine_mechanics"]=evaluate_history(c,member_spec,method=FVM,
                 boundary=boundary,heat_grid=g,max_step_minutes=dt,mechanical_grid=m1,
                 fvm_heat=solved,**common)
    kw=dict(temperature_tolerance_C=temperature_tolerance_C,
            relative_tolerance=relative_tolerance,event_tolerance_minutes=event_tolerance_minutes)
    comparisons={}
    for name,a,b in (
        ("K_mechanical_quadrature","K_coarse_mechanics","K_fine_mechanics"),
        ("FVM_spatial","FVM_coarse_space","FVM_fine_space"),
        ("FVM_integration_time","FVM_fine_space","FVM_fine_time"),
        ("FVM_mechanical_quadrature","FVM_fine_time","FVM_fine_mechanics"),
        ("K5_sensitivity","K_fine_mechanics","K_centre"),
        ("K_vs_FVM","K_fine_mechanics","FVM_fine_mechanics")):
        comparisons[name]=compare_histories(histories[a],histories[b],**kw)
    for route in ("K_fine_mechanics","K_centre","FVM_fine_mechanics"):
        h=histories[route]
        comparisons[route+"_observation_refinement"]=compare_histories(_subset(h,coarse),h,**kw)
    convergence_keys=("K_mechanical_quadrature","FVM_spatial","FVM_integration_time",
                      "FVM_mechanical_quadrature","K_fine_mechanics_observation_refinement",
                      "K_centre_observation_refinement","FVM_fine_mechanics_observation_refinement")
    numerical=all(comparisons[k]["all_shared_times_resolved_and_within_tolerance"]
                  and comparisons[k]["both_complete_histories_resolved"]
                  and comparisons[k]["event_comparison"]["within_tolerance"] for k in convergence_keys)
    return {"version":VERSION,"histories":histories,"comparisons":comparisons,
            "coarse_times_minutes":coarse,"fine_times_minutes":fine,
            "numerical_convergence_at_sampled_times":numerical,
            "tolerances_are_not_normative":True,
            "tolerances":kw,"thermal_equivalence_proven":False,
            "actual_t_R_minutes":None,"U_member_t":None,"normative_claim":False}
