"""R10B matched section histories with explicitly separate convergence axes."""
import copy
import numpy as np
from rc_fire.mechanics import sp2026_r10a_history_section as h
from rc_fire.mechanics import sp2026_r10b_steel_history as steel
from rc_fire.mechanics import sp2026_r9g_hot_domain as hot
from rc_fire.thermal.sp2026_heat import solve_sp2026_2d_heat,select_sp2026_snapshot
from rc_fire.thermal.sp2026_annex_k_field import build_annex_k_snapshot

def campaign(column,boundary):
    c=copy.deepcopy(column);c["fire_minutes"]=10.
    times=[i*.5 for i in range(21)]
    heat=solve_sp2026_2d_heat(c,boundary=boundary,cell_count_x=32,cell_count_y=32,
                             max_step_minutes=.5,sample_times_minutes=times)
    fields={"FVM":[select_sp2026_snapshot(heat,t) for t in times],
            "K":[build_annex_k_snapshot(c,t) for t in times]}
    runs=[]
    def run(id,route,mode,actions,grid,step,steel_mode=steel.PLASTIC):
        r=h.run_history(c,fields[route][::int(step/.5)],actions,grid=grid,mode=mode,
                        steel_mode=steel_mode,steel_strain_limit=.02)
        runs.append({"id":id,"route":route,"mode":mode,"grid":grid,"step_min":step,
                     "actions":actions,"steel_mode":steel_mode,**r})
    A=(50.,1.,1.)
    run("FVM16","FVM",hot.MODIFIED_AT,A,16,1.)
    run("FVM24","FVM",hot.MODIFIED_AT,A,24,1.)
    run("FVM32","FVM",hot.MODIFIED_AT,A,32,1.)
    run("FVM24_FINE_TIME","FVM",hot.MODIFIED_AT,A,24,.5)
    run("FVM24_ELASTIC","FVM",hot.MODIFIED_AT,A,24,1.,steel.ELASTIC)
    run("FVM24_ZERO","FVM",hot.ZERO,A,24,1.)
    run("FVM24_FREE","FVM",hot.MODIFIED_AT,(0.,0.,0.),24,1.)
    run("FVM24_FREE_ZERO","FVM",hot.ZERO,(0.,0.,0.),24,1.)
    run("K24","K",hot.MODIFIED_AT,A,24,1.)
    # One actual extended-duration diagnostic. No skipping an unknown step.
    long=copy.deepcopy(column);long["fire_minutes"]=90.
    ts=[float(i) for i in range(0,91,5)]
    heat_long=solve_sp2026_2d_heat(long,boundary=boundary,cell_count_x=32,cell_count_y=32,
            max_step_minutes=1.,sample_times_minutes=ts)
    rr=h.run_history(long,[select_sp2026_snapshot(heat_long,t) for t in ts],A,grid=16,
                     mode=hot.MODIFIED_AT,steel_mode=steel.PLASTIC,steel_strain_limit=.02)
    runs.append({"id":"FVM16_90MIN","route":"FVM","mode":hot.MODIFIED_AT,"grid":16,
                 "step_min":5.,"actions":A,"steel_mode":steel.PLASTIC,**rr})
    def compare(a,b):
        x=next(r for r in runs if r["id"]==a);y=next(r for r in runs if r["id"]==b)
        xx={r["time_minutes"]:r for r in x["rows"] if r["status"]=="EQUILIBRATED_RESEARCH_SECTION"}
        yy={r["time_minutes"]:r for r in y["rows"] if r["status"]=="EQUILIBRATED_RESEARCH_SECTION"}
        common=sorted(set(xx)&set(yy))
        diffs=[]
        for t in common:
            u=xx[t];v=yy[t]
            d=lambda k:float(np.linalg.norm(np.asarray(u[k])-np.asarray(v[k]))/max(1.,np.linalg.norm(v[k])))
            diffs.append({"time_minutes":t,"Nc_abs_kN":abs(u["concrete_actions_kN_kNm"][0]-v["concrete_actions_kN_kNm"][0]),
                          "D_algorithmic_rel":d("condensed_D_kNm2"),"D_unloading_rel":d("frozen_elastic_unloading_D_kNm2"),
                          "damage_abs":abs(u["area_weighted_damage"]-v["area_weighted_damage"]),
                          "q_abs":float(np.max(np.abs(np.asarray(u["q"])-v["q"])))})
        final=diffs[-1] if diffs else None
        complete=x["status"]==y["status"]=="DIAGNOSTIC_COMPLETE" and bool(common) and common[-1]==10.
        passed=complete and all(z["Nc_abs_kN"]<=5. and z["D_unloading_rel"]<=.05 and
                                z["damage_abs"]<=.005 and z["q_abs"]<=5e-5 for z in diffs)
        return {"a":a,"b":b,"complete":complete,"last_common":final,"checkpoints":diffs,
                "research_convergence_pass":passed}
    comparisons=[compare(a,b) for a,b in (("FVM16","FVM24"),("FVM24","FVM32"),
                          ("FVM24","FVM24_FINE_TIME"),("FVM24","FVM24_ELASTIC"))]
    return {"runs":runs,"comparisons":comparisons,
            "normative_claim":False,"actual_t_R_minutes":None}
