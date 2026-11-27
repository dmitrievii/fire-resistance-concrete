"""SP-R8D: isolate field discretization, equilibrium and local strain sampling.

The fixed-coordinate check is diagnostic, not a new approved material law.
Retain existing SP-R7 classification, record alternative probe evidence,
and do not resolve a disagreement by choosing the favorable result.
"""
from __future__ import annotations
import copy
import math
import numpy as np
from rc_fire.thermal.sp2026_heat import (
    solve_sp2026_2d_heat, select_sp2026_snapshot, sample_sp2026_temperature)
from rc_fire.thermal.sp2026_annex_k_field import (
    ANNEX_K_METHOD, build_annex_k_snapshot, sample_annex_k_temperature)
from rc_fire.materials.sp2026_fire import concrete_free_thermal_strain_sp
from rc_fire.mechanics.sp2026_nominal_member import prepare_sp2026_design_section
from rc_fire.mechanics.sp2026_coupled_first_limit import (
    assess_coupled_sp5_nominal_at_time, WITHIN, EXCEEDED, NOMINAL, UNKNOWN)
from rc_fire.mechanics.sp2026_unified_history import _temperature_inventory

VERSION="SP-R8D-discretization-diagnostic-v1"
ERRORS=(ValueError,ArithmeticError,np.linalg.LinAlgError)

def prepare_fixed_probes(column,field,prepared,*,divisions):
    """Common physical lattice and sampled 800 C isotherm crossings.

    Do not check displaced concrete at the bar center as if it were present.
    Concrete stress subtraction remains unchanged in equilibrium integration.
    The finite probe lattice is not an exact continuum maximization.
    """
    if type(divisions) is not int or not 4<=divisions<=100:
        raise ValueError("fixed probe divisions 4..100 required")
    point=sample_annex_k_temperature if field["thermal_method"]==ANNEX_K_METHOD else sample_sp2026_temperature
    b,h=float(column["b_mm"]),float(column["h_mm"])
    xs=np.linspace(0,b,divisions+1);ys=np.linspace(0,h,divisions+1)
    temp=np.array([[point(field,float(x),float(y)) for x in xs] for y in ys])
    coords=[(float(x),float(y),float(temp[j,i]),"lattice")
            for j,y in enumerate(ys) for i,x in enumerate(xs)]
    # Locate crossings from the active side. The user's T>800 zero
    # concrete policy is discontinuous; no interpolated strength tail.
    for j,y in enumerate(ys):
        for i,x in enumerate(xs):
            for ii,jj in ((i+1,j),(i,j+1)):
                if ii>divisions or jj>divisions:continue
                a=float(temp[j,i]);z=float(temp[jj,ii])
                if (a<=800)==(z<=800):continue
                low=np.array([x,y],dtype=float);high=np.array([xs[ii],ys[jj]],dtype=float)
                if a>800:low,high=high,low
                for _ in range(24):
                    mid=(low+high)/2.
                    if point(field,*mid)<=800:low=mid
                    else:high=mid
                coords.append((float(low[0]),float(low[1]),float(point(field,*low)),
                               "active_side_800C_crossing"))
    probes=[]
    for x,y,T,origin in coords:
        if any((x-float(bar["x_mm"]))**2+(y-float(bar["y_mm"]))**2
                <(float(bar["diameter_mm"])/2.)**2 for bar in column["bars"]):
            continue
        _,_,limit,_=prepared.sp_concrete_stress_fn(
            0.,T,prepared.sp_concrete,prepared.sp_concrete_normal)
        if limit is None:continue
        eps=concrete_free_thermal_strain_sp(T,prepared.aggregate)
        if eps is None:continue
        probes.append({"x_mm":x,"y_mm":y,"temperature_C":T,
                       "thermal_strain":float(eps),"ultimate_strain":float(limit),
                       "u":2*x/b-1,"v":2*y/h-1,"origin":origin})
    return {"divisions":divisions,"concrete":probes,
            "candidate_points":len(coords),"continuum_qualified":False}

def evaluate_fixed_probes(prepared,unknowns,probes):
    q=np.asarray(unknowns,dtype=float)
    if q.shape!=(3,) or not np.all(np.isfinite(q)):
        raise ValueError("finite equilibrium state required")
    e0,kx,ky=q
    candidates=[]
    for p in probes["concrete"]:
        strain=e0+kx*p["v"]+ky*p["u"]+p["thermal_strain"]
        candidates.append({**p,"material":"concrete","mechanical_strain":float(strain),
                           "ratio":float(max(0.,strain)/p["ultimate_strain"])})
    for i,barid in enumerate(prepared.bar_ids):
        strain=e0+kx*prepared.bar_v[i]+ky*prepared.bar_u[i]+prepared.eps_th_s[i]
        candidates.append({"material":"reinforcement","bar_id":str(barid),
                           "x_mm":float(prepared.bar_x[i]*1000),
                           "y_mm":float(prepared.bar_y[i]*1000),
                           "temperature_C":float(prepared.theta_s[i]),
                           "thermal_strain":float(prepared.eps_th_s[i]),
                           "mechanical_strain":float(strain),
                           "ratio":float(max(0.,-strain)/.010)})
    if not candidates:raise ValueError("no active material probe")
    governing=max(candidates,key=lambda x:x["ratio"])
    return {"critical_ratio":governing["ratio"],"governing":governing,
            "classification":WITHIN if governing["ratio"]<=1.+1e-12 else EXCEEDED,
            "active_concrete_probes":len(probes["concrete"]),
            "continuum_qualified":False,"normative_claim":False}

def _state(column,field,spec,grid,phi):
    try:
        p=prepare_sp2026_design_section(column,field,grid=grid)
        m=assess_coupled_sp5_nominal_at_time(column,field,spec,grid=grid,
                                           effective_creep_phi=phi)
        s=m.get("source_section_check") or {}
        r=m["nominal_coupled_evidence"]
        q=s.get("unknowns")
        scope=s.get("scope") or {}
        info={"grid":grid,"original_status":m["status"],
              "critical_ratio":s.get("critical_ratio"),"unknowns":q,
              "equilibrium_residual":s.get("relative_residual"),
              "fibre_ratio":scope.get("maximum_concrete_fibre_ratio"),
              "boundary_ratio":scope.get("maximum_concrete_boundary_ratio"),
              "steel_ratio":scope.get("steel_check_tension_ratio"),
              "Ncrit_kN":r["principal_Euler_Ncrit_kN"],
              "D_kNm2":r["nominal_2x2_D_kNm2"],"M2_kNm":m["second_order_coupled_M2_kNm"]}
        return p,info
    except ERRORS as exc:
        return None,{"grid":grid,"original_status":UNKNOWN,"reason":str(exc),"unknowns":None}

def diagnose_section_sampling(column,field,spec,*,mechanical_grids=(8,16,24),
                              probe_divisions=(20,40),effective_creep_phi):
    """Freeze probes while varying equilibrium quadrature; then refine probes.

    Replay one identical generalized strain on all section grids, so root
    changes and local sampling changes can be distinguished.
    """
    prepared=[];rows=[]
    for g in mechanical_grids:
        p,row=_state(column,field,spec,g,effective_creep_phi)
        prepared.append(p);rows.append(row)
    if prepared[-1] is None or rows[-1]["unknowns"] is None:
        return {"rows":rows,"status":"UNRESOLVED_FINE_REFERENCE_ROOT",
                "normative_claim":False}
    p_ref=prepared[-1]
    q_ref=rows[-1]["unknowns"]
    probes=[prepare_fixed_probes(column,field,p_ref,divisions=d) for d in probe_divisions]
    for p,row in zip(prepared,rows):
        if p is None or row["unknowns"] is None:continue
        row["fixed_probe_checks"]=[evaluate_fixed_probes(p,row["unknowns"],v) for v in probes]
        _,_,replay=p.force_and_tangent(q_ref)
        row["same_fine_root_legacy_ratio"]=replay["critical_mechanical_strain_ratio"]
        row["same_fine_root_fixed_ratio"]=evaluate_fixed_probes(p,q_ref,probes[-1])["critical_ratio"]
        row["original_vs_fixed_agree"]=(row["original_status"]==row["fixed_probe_checks"][-1]["classification"])
    valid=[r for r in rows if "fixed_probe_checks" in r]
    stable=(len(valid)==len(rows) and
            len({r["fixed_probe_checks"][-1]["classification"] for r in valid})==1 and
            all(r["fixed_probe_checks"][0]["classification"]==
                r["fixed_probe_checks"][-1]["classification"] for r in valid))
    return {"rows":rows,"fixed_probe_classification_stable":stable,
            "status":"DIAGNOSTIC_COMPARISON_ONLY",
            "production_classification_overridden":False,
            "normative_claim":False}

def _relative(a,b):
    if a is None or b is None:return None
    aa,bb=np.asarray(a,dtype=float),np.asarray(b,dtype=float)
    if aa.shape!=bb.shape or not np.all(np.isfinite(aa)) or not np.all(np.isfinite(bb)):return None
    return float(np.linalg.norm(aa-bb)/max(np.linalg.norm(bb),1e-12))

def run_spatial_recovery(column,spec,*,boundary,times_minutes=(5.,10.),
                         thermal_grids=(16,32,64),step_minutes=1.,
                         mechanical_grids=(8,16,24),probe_divisions=(20,40),
                         effective_creep_phi,temperature_tolerance_C=10.,
                         relative_tolerance=.03):
    """Targeted finer uniform FVM solves; same observation times and actions."""
    c=copy.deepcopy(column)
    times=[float(t) for t in times_minutes]
    if not times or not 0<times[0] or any(b<=a for a,b in zip(times,times[1:])):
        raise ValueError("strict positive sample times required")
    if len(thermal_grids)!=3 or not 4<=thermal_grids[0]<thermal_grids[1]<thermal_grids[2]<=80:
        raise ValueError("three ascending thermal grids required")
    c["fire_minutes"]=times[-1]
    runs=[]
    for g in thermal_grids:
        data=solve_sp2026_2d_heat(c,boundary=boundary,cell_count_x=g,cell_count_y=g,
             max_step_minutes=step_minutes,sample_times_minutes=times)
        samples=[]
        for t in times:
            field=select_sp2026_snapshot(data,t)
            _,state=_state(c,field,spec,mechanical_grids[-1],effective_creep_phi)
            samples.append({"time_minutes":t,"temperatures_C":_temperature_inventory(c,field),
                            "mechanics":state})
        runs.append({"thermal_grid":g,"samples":samples,"energy_balance":data["energy_balance"]})
    comparisons=[]
    for a,b in zip(runs,runs[1:]):
        for x,y in zip(a["samples"],b["samples"]):
            diffs={k:abs(x["temperatures_C"][k]-y["temperatures_C"][k])
                   for k in x["temperatures_C"]}
            worst=max(diffs,key=diffs.get)
            am,bm=x["mechanics"],y["mechanics"]
            dn=_relative(am.get("Ncrit_kN"),bm.get("Ncrit_kN"))
            same=(am["original_status"]==bm["original_status"] and am["original_status"]!=UNKNOWN)
            comparisons.append({"from_grid":a["thermal_grid"],"to_grid":b["thermal_grid"],
                 "time_minutes":x["time_minutes"],"worst_location":worst,
                 "max_delta_C":diffs[worst],
                 "max_bar_steel_delta_C":max(v for k,v in diffs.items() if k.startswith("bar_steel:")),
                 "max_concrete_point_delta_C":max(v for k,v in diffs.items() if k.startswith("concrete:")),
                 "Ncrit_relative_delta":dn,
                 "same_original_classification":same,
                 "within_tolerances":bool(same and dn is not None and
                     dn<=relative_tolerance and diffs[worst]<=temperature_tolerance_C)})
    diagnostics={}
    for t in times:
        f=select_sp2026_snapshot(data,t)
        diagnostics["FVM:"+str(t)]=diagnose_section_sampling(c,f,spec,
            mechanical_grids=mechanical_grids,probe_divisions=probe_divisions,
            effective_creep_phi=effective_creep_phi)
        try:
            k=build_annex_k_snapshot(c,t)
            diagnostics["K:"+str(t)]=diagnose_section_sampling(c,k,spec,
                mechanical_grids=mechanical_grids,probe_divisions=probe_divisions,
                effective_creep_phi=effective_creep_phi)
        except ERRORS as exc:
            diagnostics["K:"+str(t)]={"status":"UNRESOLVED","reason":str(exc)}
    fine=[r for r in comparisons if r["to_grid"]==thermal_grids[-1]]
    return {"version":VERSION,"runs":runs,"thermal_comparisons":comparisons,
            "classification_diagnostics":diagnostics,
            "fine_thermal_comparisons_within_tolerances":all(r["within_tolerances"] for r in fine),
            "fixed_probe_continuum_qualified":False,"physical_failure_proven":False,
            "actual_t_R_minutes":None,"normative_claim":False}
