"""SP-R10D compression-active front pilots and matched thermal refinement.

Pilot generalized strains are used ONLY for geometry selection. Each
probe independently replays R9G from ambient; no constitutive state
interpolation, no transfer of the pilot root to final equilibria.
Sampled mixed-class cells are refinement indicators, not certified bounds
on the true moving front or on the quadrature error.
"""
from functools import lru_cache
import copy
import math
import numpy as np
from rc_fire.mechanics import sp2026_r10a_history_section as h
from rc_fire.mechanics import sp2026_r10b_steel_history as st
from rc_fire.mechanics import sp2026_r9g_hot_domain as hot
from rc_fire.mechanics import sp2026_r10c_quadrature as quad
from rc_fire.mechanics.sp2026_r10c_campaign import compare
from rc_fire.mechanics.sp2026_nominal_member import prepare_sp2026_design_section
from rc_fire.thermal.sp2026_heat import solve_sp2026_2d_heat,select_sp2026_snapshot
from rc_fire.thermal.sp2026_annex_k_field import ANNEX_K_METHOD

VERSION="SP-R10D-pilot-front-and-thermal-refinement-v1"

def classify(signatures):
    """Time-aligned class signatures: 0 open, 1 compressed, 2 cutoff,
    3 crushed, None unknown. Unknown is never a successful classification."""
    if not signatures or not signatures[0] or len({len(v) for v in signatures})!=1:
        raise ValueError("nonempty aligned probe signatures required")
    unknown=any(x is None for v in signatures for x in v)
    mixed=any(len({x for x in at if x is not None})>1 for at in zip(*signatures))
    return mixed,unknown

def make_front_indicator(initial,fields,pilot_rows,*,width_m,height_m,stress_floor_MPa=1e-8):
    """Actual material-point replay at fixed pilot generalized strains.

    Fine thermal field can be used with coarse-mechanical pilot q, by
    design: it selects quadrature only, not a purported equilibrium.
    No successful future class is imputed after an unresolved trial.
    """
    if len(fields)!=len(pilot_rows) or not fields or stress_floor_MPa<0:
        raise ValueError("matched pilot histories required")
    for f,r in zip(fields,pilot_rows):
        if r["status"]!="EQUILIBRATED_RESEARCH_SECTION" or f["snapshot"]["time_minutes"]!=r["time_minutes"]:
            raise ValueError("pilot history incomplete or time-mismatched")
    @lru_cache(maxsize=None)
    def replay(x,y):
        s=initial;signature=[]
        B=np.array([1.,2*y/height_m-1,2*x/width_m-1])
        for f,r in zip(fields,pilot_rows):
            try:
                T=quad._sampler(f)(f,min(width_m*1000,max(0.,x*1000)),
                                    min(height_m*1000,max(0.,y*1000)))
                s,ledger=hot.trial_step(s,time_s=1.+60*r["time_minutes"],
                        temperature_C=float(T),total_compression=float(B@r["q"]))
            except (ValueError,ArithmeticError):
                return tuple(signature+[None]*(len(fields)-len(signature)))
            signature.append(2 if s.thermal_cutoff else 3 if s.active.damage==1.
                             else 1 if ledger["stress_MPa"]>stress_floor_MPa else 0)
        return tuple(signature)
    def indicator(points):
        return classify([replay(float(x),float(y)) for x,y in points])
    return indicator,replay

def thermal_comparison(column,coarse,fine,mesh):
    """Same physical centroid and bar probes, same time, no change of
    mechanical quadrature. No certification of the continuous T field."""
    if len(coarse)!=len(fine) or not coarse:raise ValueError("aligned thermal fields required")
    x,y,A=np.asarray(mesh.points).T
    rows=[]
    for f,g in zip(coarse,fine):
        if f["snapshot"]["time_minutes"]!=g["snapshot"]["time_minutes"]:
            raise ValueError("thermal checkpoint mismatch")
        sample1=quad._sampler(f);sample2=quad._sampler(g)
        d=np.asarray([sample1(f,float(a*1000),float(b*1000))-
                      sample2(g,float(a*1000),float(b*1000)) for a,b in zip(x,y)])
        p=prepare_sp2026_design_section(column,f,grid=8)
        r=prepare_sp2026_design_section(column,g,grid=8)
        rows.append({"t":float(f["snapshot"]["time_minutes"]),
                     "max_centroid_delta_C":float(np.max(np.abs(d))),
                     "area_weighted_RMSE_C":float(math.sqrt(A@(d*d)/A.sum())),
                     "max_bar_delta_C":float(np.max(np.abs(np.asarray(p.theta_s)-r.theta_s))),
                     "max_boundary_delta_C":float(np.max(np.abs(np.asarray(p.sp_boundary_temperature)-r.sp_boundary_temperature)))})
    return {"rows":rows,"max":{k:max(r[k] for r in rows) for k in rows[0] if k!="t"},
            "research_temperature_pass":all(r["max_centroid_delta_C"]<=10 and r["max_bar_delta_C"]<=10
                       and r["max_boundary_delta_C"]<=10 for r in rows),
            "thermal_time_convergence_proven":False,"normative_claim":False}

def front_comparison(a,b,end):
    r=compare(a,b,end=end)
    # Compression-active area is separately converged, not inferred from
    # force balance. Absolute 0.001 m² is a declared research tolerance.
    M=r["max_checkpoint_differences"]
    r["active_area_research_pass"]=bool(r["complete"] and M is not None and
        M["compressed_area_abs_m2"]<=.001 and M["thermal_inactive_area_abs_m2"]<=.001)
    r["joint_section_research_pass"]=bool(r["checkpoint_research_pass"] and r["active_area_research_pass"])
    return r

def campaign(column,boundary):
    c=copy.deepcopy(column);c["fire_minutes"]=90.
    ts=[float(i) for i in range(11)]+[float(t) for t in range(15,91,5)]
    def heat(n):
        r=solve_sp2026_2d_heat(c,boundary=boundary,cell_count_x=n,cell_count_y=n,
                              max_step_minutes=.5,sample_times_minutes=ts)
        return [select_sp2026_snapshot(r,t) for t in ts]
    f32=heat(32);f64=heat(64)
    A=(50.,1.,1.)
    p=prepare_sp2026_design_section(c,f32[0],grid=8)
    def run(id,fields,mesh):
        r=h.run_history(c,fields,A,grid=8,mode=hot.MODIFIED_AT,steel_mode=st.PLASTIC,
                        steel_strain_limit=.02,quadrature=mesh)
        return {"id":id,"quadrature":mesh.evidence(),**r}
    pilot_indices=[ts.index(t) for t in (1.,3.,5.,10.,30.,60.,90.)]
    pilot_mesh=quad.build(p,[f32[i] for i in pilot_indices],max_level=2,delta_C=100.)
    pilot=run("PILOT32_A2",f32,pilot_mesh)
    if pilot["status"]!="DIAGNOSTIC_COMPLETE":
        return {"version":VERSION,"status":"BLOCKED_PILOT","runs":[pilot],"comparisons":[],
                "thermal_comparison":None,"section_history_qualification_closed":False,
                "actual_t_R_minutes":None,"normative_claim":False}
    seed=h.make_initial(c,f32[0],grid=8,mode=hot.MODIFIED_AT,length_mm=50.,Gwork_N_mm=5.,
                        yield_fraction=.4,strength_basis="SP5_ACCIDENTAL_FCD").concrete[0]
    indicator,replay=make_front_indicator(seed,f64,pilot["rows"],width_m=p.b_m,height_m=p.h_m)
    m3=quad.build(p,[f64[i] for i in pilot_indices],max_level=3,delta_C=60.,front_indicator=indicator)
    # Fine spatial comparison on 0..10 min only, same pilot-selected geometry.
    m4=quad.build(p,[f64[i] for i in pilot_indices],max_level=4,delta_C=30.,front_indicator=indicator)
    a=run("T32_FRONT3",f32,m3);b=run("T64_FRONT3",f64,m3)
    # Reuse the full-history fine-thermal prefix for a matched short comparison.
    short=f64[:11];d=run("T64_FRONT4_SHORT",short,m4)
    bp={**b,"id":"T64_FRONT3_SHORT","rows":b["rows"][:11],
        "status":"DIAGNOSTIC_COMPLETE" if len(b["rows"])>=11 and b["rows"][10]["status"]=="EQUILIBRATED_RESEARCH_SECTION" else "UNRESOLVED_HISTORY_STOP"}
    thermal=thermal_comparison(c,f32,f64,m3)
    comparisons=[front_comparison(a,b,90.),front_comparison(bp,d,10.)]
    return {"version":VERSION,"status":"DIAGNOSTIC_COMPLETE","runs":[pilot,a,b,d],
            "comparisons":comparisons,"thermal_comparison":thermal,
            "pilot_probe_count":replay.cache_info().currsize,
            "section_spatial_research_pass":all(r["joint_section_research_pass"] for r in comparisons)
                  and thermal["research_temperature_pass"] and m3.unresolved_probe_cells==0 and m4.unresolved_probe_cells==0,
            "section_history_qualification_closed":False,
            "actual_t_R_minutes":None,"normative_claim":False}
