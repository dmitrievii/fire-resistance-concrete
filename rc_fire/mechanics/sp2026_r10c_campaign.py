"""SP-R10C matched fixed boundary-refined short/extended histories."""
import copy
import numpy as np
from rc_fire.mechanics import sp2026_r10a_history_section as h
from rc_fire.mechanics import sp2026_r10b_steel_history as st
from rc_fire.mechanics import sp2026_r9g_hot_domain as hot
from rc_fire.mechanics import sp2026_r10c_quadrature as q
from rc_fire.mechanics.sp2026_nominal_member import prepare_sp2026_design_section
from rc_fire.thermal.sp2026_heat import solve_sp2026_2d_heat,select_sp2026_snapshot
from rc_fire.thermal.sp2026_annex_k_field import build_annex_k_snapshot

def compare(a,b,*,end):
    X={r["time_minutes"]:r for r in a["rows"] if r["status"]=="EQUILIBRATED_RESEARCH_SECTION"}
    Y={r["time_minutes"]:r for r in b["rows"] if r["status"]=="EQUILIBRATED_RESEARCH_SECTION"}
    common=sorted(set(X)&set(Y));rows=[]
    for t in common:
        x,y=X[t],Y[t]
        def rel(k):return float(np.linalg.norm(np.asarray(x[k])-np.asarray(y[k]))/max(1.,np.linalg.norm(y[k])))
        rows.append({"t":t,"Nc_kN":abs(x["concrete_actions_kN_kNm"][0]-y["concrete_actions_kN_kNm"][0]),
                     "D_alg_rel":rel("condensed_D_kNm2"),"D_unload_rel":rel("frozen_elastic_unloading_D_kNm2"),
                     "damage_abs":abs(x["area_weighted_damage"]-y["area_weighted_damage"]),
                     "q_abs":float(np.max(np.abs(np.asarray(x["q"])-y["q"]))),
                     "compressed_area_abs_m2":abs(x["compressed_net_area_m2"]-y["compressed_net_area_m2"]),
                     "thermal_inactive_area_abs_m2":abs(x["thermal_inactive_net_area_m2"]-y["thermal_inactive_net_area_m2"])})
    # t=0 is a directional kink for free section; no such case here.
    complete=(a["status"]==b["status"]=="DIAGNOSTIC_COMPLETE" and bool(common) and common[-1]==end)
    maximum={k:max(r[k] for r in rows) for k in rows[0] if k!="t"} if rows else None
    passed=complete and maximum["Nc_kN"]<=5. and maximum["D_alg_rel"]<=.05 and maximum["D_unload_rel"]<=.05 and maximum["damage_abs"]<=.005 and maximum["q_abs"]<=5e-5
    return {"a":a["id"],"b":b["id"],"complete":complete,"last_common":common[-1] if common else None,
            "max_checkpoint_differences":maximum,"checkpoint_research_pass":passed,
            "last":rows[-1] if rows else None,"rows":rows}

def campaign(column,boundary):
    c=copy.deepcopy(column);c["fire_minutes"]=90.
    ts=sorted(set([float(i) for i in range(11)]+[float(i) for i in range(15,91,5)]))
    heat=solve_sp2026_2d_heat(c,boundary=boundary,cell_count_x=32,cell_count_y=32,
                             max_step_minutes=.5,sample_times_minutes=ts)
    ff={t:select_sp2026_snapshot(heat,t) for t in ts}
    kf={t:build_annex_k_snapshot(c,t) for t in range(11)}
    A=(50.,1.,1.);runs=[]
    def plan(route,pilots,level,delta):
        fs=ff if route=="FVM" else kf
        p=prepare_sp2026_design_section(c,fs[0],grid=8)
        return q.build(p,[fs[t] for t in pilots],max_level=level,delta_C=delta)
    def run(id,route,times,grid,mesh,mode=hot.MODIFIED_AT,actions=A):
        fs=ff if route=="FVM" else kf
        r=h.run_history(c,[fs[t] for t in times],actions,grid=grid,mode=mode,
                        steel_mode=st.PLASTIC,steel_strain_limit=.02,quadrature=mesh)
        runs.append({"id":id,"route":route,"grid":grid,"mode":mode,"actions":actions,
                     "quadrature":mesh.evidence() if mesh else {"point_count":grid*grid},**r})
    short=list(range(11));pilots=(1,3,5,10)
    coarse=plan("FVM",pilots,2,100.)
    medium=plan("FVM",pilots,3,60.)
    fine=plan("FVM",pilots,4,30.)
    run("U32","FVM",short,32,None)
    run("A2","FVM",short,8,coarse)
    run("A3","FVM",short,8,medium)
    run("A4","FVM",short,8,fine)
    run("A3_ZERO","FVM",short,8,medium,mode=hot.ZERO)
    run("K_A3","K",short,8,plan("K",pilots,3,60.))
    # Same thermal field and early history, long mesh planned against all pilots.
    longts=[0.,1.,2.,3.,4.,5.,6.,7.,8.,9.,10.]+[float(t) for t in range(15,91,5)]
    longpilots=(1,3,5,10,30,60,90)
    run("LONG_A2","FVM",longts,8,plan("FVM",longpilots,2,100.))
    run("LONG_A3","FVM",longts,8,plan("FVM",longpilots,3,60.))
    comparisons=[compare(next(r for r in runs if r["id"]==a),next(r for r in runs if r["id"]==b),end=end)
                 for a,b,end in (("U32","A2",10.),("A2","A3",10.),("A3","A4",10.),("LONG_A2","LONG_A3",90.))]
    return {"runs":runs,"comparisons":comparisons,"thermal_grid":32,"thermal_step_min":.5,
            "normative_claim":False,"actual_t_R_minutes":None}
