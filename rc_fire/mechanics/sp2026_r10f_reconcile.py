"""R10F: reconciliation of fixed pilot polygons and final histories.

All revisions restart at ambient; no constitutive state transfer. Probe
audit uses an independent fixed net-area quadrature, not polygon nodes.
Sample agreement does not certify continuous front location.
"""
import copy
import math
import time
import numpy as np
from rc_fire.mechanics import sp2026_r10a_history_section as h
from rc_fire.mechanics import sp2026_r10b_steel_history as st
from rc_fire.mechanics import sp2026_r9g_hot_domain as hot
from rc_fire.mechanics import sp2026_r10c_quadrature as q
from rc_fire.mechanics import sp2026_r10d_front as d
from rc_fire.mechanics import sp2026_r10e_cutcell as cut
from rc_fire.mechanics.sp2026_r10e_campaign import admission
from rc_fire.mechanics.sp2026_nominal_member import prepare_sp2026_design_section
from rc_fire.thermal.sp2026_heat import solve_sp2026_2d_heat,select_sp2026_snapshot

VERSION="SP-R10F-fixed-front-reconciliation-v1"

def classify(value):
    if value is None:return None
    gap,thermal,crushed=value
    if thermal<0:return 2
    if crushed:return 3
    if gap is None:return None
    return 1 if gap>0 else 0

def audit_signatures(points,times,left,right):
    """Weighted disagreement, not just difference of signed active areas.

    points fixed independently of both solutions; None is unknown, never
    treated as inactive. Net area represented by positive weights.
    """
    if not times or not points:raise ValueError("nonempty aligned audit required")
    total=sum(a for x,y,a in points)
    if total<=0 or any(a<=0 for x,y,a in points):raise ValueError("positive audit weights")
    rows=[{"t":t,"disagreement_m2":0.,"unknown_m2":0.,"pilot_active_m2":0.,
           "final_active_m2":0.,"max_gap_difference":0.} for t in times]
    for x,y,a in points:
        l=left(x,y);r=right(x,y)
        if l is None:l=[None]*len(times)
        if r is None:r=[None]*len(times)
        if len(l)!=len(times) or len(r)!=len(times):raise ValueError("unaligned probe signatures")
        for out,u,v in zip(rows,l,r):
            i,j=classify(u),classify(v)
            if i is None or j is None:out["unknown_m2"]+=a;continue
            if i!=j:out["disagreement_m2"]+=a
            if i==1:out["pilot_active_m2"]+=a
            if j==1:out["final_active_m2"]+=a
            if u[0] is not None and v[0] is not None:
                out["max_gap_difference"]=max(out["max_gap_difference"],abs(u[0]-v[0]))
    maximum={k:max(r[k] for r in rows) for k in ("disagreement_m2","unknown_m2","max_gap_difference")}
    return {"rows":rows,"max":maximum,"audit_net_area_m2":total,"audit_points":len(points),
            "sample_agreement":maximum["unknown_m2"]==0 and maximum["disagreement_m2"]<=.001
                          and maximum["max_gap_difference"]<=5e-5,
            "continuous_front_certified":False}

def efficiency(run):
    rows=[r for r in run["rows"] if r["status"]=="EQUILIBRATED_RESEARCH_SECTION"]
    return {"accepted_steps":len(rows),
            "accepted_section_trials":sum(r["trial_counts"]["section_trials"] for r in rows),
            "accepted_concrete_trial_calls":sum(r["trial_counts"]["concrete_trials"] for r in rows),
            "avoided_redundant_section_trials":sum(r["trial_counts"]["reused_trials"] for r in rows),
            "avoided_redundant_concrete_trial_calls":sum(r["trial_counts"]["reused_trials"]*r["concrete_integration_points"] for r in rows),
            "successful_history_only":run["status"]=="DIAGNOSTIC_COMPLETE"}

def campaign(column,boundary):
    c=copy.deepcopy(column);c["fire_minutes"]=90.
    ts=[i*.5 for i in range(21)]+[10.+i*2.5 for i in range(1,33)]
    coarse_times=[float(i) for i in range(11)]+[float(t) for t in range(15,91,5)]
    thermal=solve_sp2026_2d_heat(c,boundary=boundary,cell_count_x=80,cell_count_y=80,
                             max_step_minutes=.25,sample_times_minutes=ts)
    bytime={t:select_sp2026_snapshot(thermal,t) for t in ts}
    fs=[bytime[t] for t in coarse_times];fine=[bytime[t] for t in ts]
    p=prepare_sp2026_design_section(c,fs[0],grid=8)
    A=(50.,1.,1.)
    def run(id,fields,mesh):
        start=time.perf_counter()
        r=h.run_history(c,fields,A,grid=8,mode=hot.MODIFIED_AT,steel_mode=st.PLASTIC,
                        steel_strain_limit=.02,quadrature=mesh,reuse_line_search=True)
        return {"id":id,"quadrature":mesh.evidence(),"mechanical_wall_s":time.perf_counter()-start,
                **r,"efficiency":efficiency(r)}
    pilots=[bytime[t] for t in (1.,3.,5.,10.,30.,60.,90.)]
    m2=q.build(p,pilots,max_level=2,delta_C=100.)
    pilot=run("CENTROID2",fs,m2)
    runs=[pilot]
    def blocked(reason):
        return {"version":VERSION,"status":reason,"runs":runs,"comparisons":[],
                "admission":admission(thermal_spatial=False,thermal_temporal=False,
                     mechanical_spatial=False,mechanical_temporal=False,full_duration=False,front_evidence=False),
                "actual_t_R_minutes":None,"normative_claim":False}
    if pilot["status"]!="DIAGNOSTIC_COMPLETE":return blocked("BLOCKED_PILOT")
    seed=h.make_initial(c,fs[0],grid=8,mode=hot.MODIFIED_AT,length_mm=50.,Gwork_N_mm=5.,
                        yield_fraction=.4,strength_basis="SP5_ACCIDENTAL_FCD").concrete[0]
    selected=tuple(coarse_times[1:])
    def probe(r,fields=fs,times=selected):
        return cut.make_probe(seed,fields,r["rows"],width=p.b_m,height=p.h_m,selected_times=times)
    initial_probe=probe(pilot)
    start=time.perf_counter()
    first=cut.build(m2,initial_probe,selected_times=selected)
    plan1=time.perf_counter()-start
    a=run("CUT2_INITIAL",fs,first);runs.append(a)
    if a["status"]!="DIAGNOSTIC_COMPLETE":return blocked("BLOCKED_INITIAL_CUT")
    rec_probe=probe(a)
    start=time.perf_counter()
    rec=cut.build(m2,rec_probe,selected_times=selected)
    plan2=time.perf_counter()-start
    b=run("CUT2_RECONCILED",fs,rec);runs.append(b)
    if b["status"]!="DIAGNOSTIC_COMPLETE":return blocked("BLOCKED_RECONCILED_CUT")
    # Independent net-area audit lattice: not the vertices or centroids
    # used to build the cut overlay. Fixed across all pilot comparisons.
    audit=q.build(p,[fs[0]],base_grid=27,max_level=0,boundary_band_mm=0.)
    ap=probe(b)
    aud1=audit_signatures(audit.points,selected,initial_probe,rec_probe)
    aud2=audit_signatures(audit.points,selected,rec_probe,ap)
    # Spatial refinement with same reconciled pilot, short only to bound
    # work. Full-duration spatial convergence remains an explicit gate.
    medium=q.build(p,pilots,max_level=3,delta_C=60.)
    start=time.perf_counter()
    m3=cut.build(medium,rec_probe,selected_times=selected)
    plan3=time.perf_counter()-start
    z=run("CUT3_RECONCILED_SHORT",fs[:11],m3);runs.append(z)
    # Temporal refinement holds the final fixed quadrature unchanged.
    f=run("CUT2_RECONCILED_FINE_TIME",fine,rec);runs.append(f)
    bp={**b,"id":"CUT2_RECONCILED_SHORT","rows":b["rows"][:11]}
    comparisons=[d.front_comparison(a,b,90.),d.front_comparison(bp,z,10.),
                 d.front_comparison(b,f,90.)]
    # Compare algorithmic tangents across different dt as a diagnostic;
    # physically the discrete tangent depends on increment size.
    # No claim of full spatial or thermal qualification from this campaign.
    front_ok=aud2["sample_agreement"] and rec.unknown_cells==0 and rec.skipped_cuts==0
    gates=admission(thermal_spatial=False,thermal_temporal=False,mechanical_spatial=False,
             mechanical_temporal=comparisons[2]["joint_section_research_pass"],
             full_duration=b["status"]==f["status"]=="DIAGNOSTIC_COMPLETE",
             front_evidence=False)
    return {"version":VERSION,"status":"DIAGNOSTIC_COMPLETE","runs":runs,
            "comparisons":comparisons,"initial_front_audit":aud1,"reconciled_front_audit":aud2,
            "sample_front_gate":front_ok,
            "planning_wall_s":{"initial":plan1,"reconciled":plan2,"fine":plan3},
            "probe_counts":{"initial":initial_probe.cache_info().currsize,"reconciled":rec_probe.cache_info().currsize},
            "thermal_evidence_required_from_R10E":True,
            "admission":gates,"actual_t_R_minutes":None,"normative_claim":False}
