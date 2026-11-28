"""SP-R12C matched adaptive endpoint sampling, research evidence only.

Refinement of displacement samples does not prove a continuous resistance
upper bound, uniqueness, stability or physical failure. Thermal snapshots
are those of the original R11E matched replay. No interpolation of
temperature or committed material states.
"""
import math
from rc_fire.member import sp2026_r12b_endpoint as b
from rc_fire.member import sp2026_r12a_resistance as r

def reconcile(live,*,emit=lambda event,payload:None,levels=2):
    if len(live)!=2 or not 1<=levels<=3:raise ValueError("two endpoints and bounded refinement required")
    t0,t1=(float(v[0]) for v in live)
    if t1<=t0:raise ValueError("ordered endpoint times required")
    out={"times_min":[t0,t1],"levels":[],"stop":None,"sampled_threshold_pair":None,
         "refined_sampled_threshold_supported":False,
         "physical_failure_bracket_min":None,"actual_t_R_minutes":None}
    if not all(v[5]["complete"] and v[5]["stop"] is None and
               len(v[4])==v[5]["expected_count"] for v in live):
        out["stop"]="INCOMPLETE_BASE_SCAN";return out
    controls=[2*(v[1].n//2) for v in live]
    grids=[{float(sol[0][k]):(sol,row) for sol,row in v[4]} for v,k in zip(live,controls)]
    if any(len(g)!=v[5]["expected_count"] for g,v in zip(grids,live)) or sorted(grids[0])!=sorted(grids[1]):
        out["stop"]="NONMATCHING_CONTROL_GRID";return out
    N=float(live[0][1].N)
    if N<=0 or N!=float(live[1][1].N) or any(v[1].scale[k]!=live[0][1].scale[controls[0]] or
        v[1].initial[k]!=live[0][1].initial[controls[0]] for v,k in zip(live,controls)):
        out["stop"]="NONMATCHING_LOAD_OR_PHYSICAL_COORDINATE";return out
    def evidence(g):
        rows=[g[k][1] for k in sorted(g)]
        return r.endpoint({"rows":rows,"stop":None},N=N,expected_count=len(g))
    previous=None
    for level in range(levels+1):
        try:a,z=[evidence(g) for g in grids]
        except ValueError as exc:out["stop"]="EVIDENCE_CONTRACT:"+str(exc);break
        pair=r.sampled_threshold_pair(a,z,t0=t0,t1=t1,same_anchor_and_scan=True)
        rec={"level":level,"sample_count":len(grids[0]),"samples":[a,z],"pair":pair}
        if previous is not None:
            diffs=[]
            for old,new in zip(previous,[a,z]):
                x,y=old["sampled_peak_lambda"],new["sampled_peak_lambda"]
                if x is None or y is None:diffs.append(None);continue
                reserve=abs(y-1.)
                diffs.append({"peak_load_delta_kN":abs(x-y)*N,
                   "reserve_relative_delta":abs(x-y)/reserve if reserve>0 else None,
                   "peak_displacement_delta_mm":abs(old["sampled_peak_w_mm"]-new["sampled_peak_w_mm"]),
                   "same_side_of_unity":(x-1.)*(y-1.)>0})
            rec["successive_refinement"]=diffs
            rec["research_convergence_pass"]=all(d is not None and d["same_side_of_unity"] and
                d["reserve_relative_delta"] is not None and d["reserve_relative_delta"]<=.05 and
                d["peak_load_delta_kN"]<=.5 and d["peak_displacement_delta_mm"]<=.5 for d in diffs)
            out["refined_sampled_threshold_supported"]=bool(rec["research_convergence_pass"] and
                 pair["observed_sampled_crossing"] is not None)
        out["levels"].append(rec);out["sampled_threshold_pair"]=pair
        emit("matched_refinement_level",{"summary":rec,"rows":[[g[k][1] for k in sorted(g)] for g in grids]})
        if level==levels:break
        if any(s["sampled_peak_lambda"] is None for s in (a,z)):
            out["stop"]="OPEN_SCAN_OR_NO_INTERIOR_MAXIMUM";break
        # Bisect both neighborhoods on the identical physical control grid.
        # All new samples are solved, not interpolated. No partial level is
        # promoted if either endpoint cannot solve any of the new controls.
        ks=sorted(grids[0]);targets=set()
        for g in grids:
            i=max(range(len(ks)),key=lambda i:g[ks[i]][1]["lambda"])
            if not 0<i<len(ks)-1:raise ArithmeticError("interior maximum contract")
            targets.update(((ks[i-1]+ks[i])/2,(ks[i]+ks[i+1])/2))
        staged=[dict(g) for g in grids]
        failed=False
        for target in sorted(targets-set(ks)):
            for j,(v,g) in enumerate(zip(live,staged)):
                _,beam,ev,verify,_,_=v
                seed=g[min(g,key=lambda k:abs(k-target))][0]
                sol,row=b.controlled(beam,ev,verify,seed,target)
                if sol is None:
                    out["stop"]={"status":"UNRESOLVED_REFINEMENT","t":float(v[0]),
                                 "control":target,"reason":row}
                    emit("refinement_rejected",out["stop"]);failed=True;break
                g[target]=(sol,row)
            if failed:break
        if failed:break
        previous=[a,z];grids=staged
    if out["stop"] is not None or len(out["levels"])!=levels+1:
        out["refined_sampled_threshold_supported"]=False
    # A finite set of samples cannot exclude an unobserved peak or branch.
    out["continuous_capacity_upper_bound"]=None
    out["physical_failure_proven"]=False
    return out

def campaign(column,boundary,*,emit=None):
    out=b.campaign(column,boundary,emit=emit,refinement=reconcile)
    # R11E endpoints are adjacent snapshots (7.5 s). Further temporal
    # refinement requires a new matched thermal replay, not interpolation.
    stop=out.get("original_stop")
    out["thermal_time_refinement"]={"available_resolution_min":.125,
        "new_matched_thermal_replay_required":True,
        "original_interval_min":[stop["last_accepted_minute"],stop["unresolved_minute"]] if stop else None,
        "old_stop_recovered":bool(out.get("original_interval_recovered",False))}
    return out
