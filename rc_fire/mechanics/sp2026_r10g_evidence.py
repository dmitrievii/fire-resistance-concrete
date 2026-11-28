"""SP-R10G evidence-only consolidation. No solver calls or inferred R.

Inputs are saved GitHub run metadata and decoded job logs. Run identities
are pinned; caller must retrieve authentic metadata/logs. A successful CI
run is not synonymous with a successful numerical comparison.
"""
import json
import math
import argparse
from pathlib import Path

SOURCES={
 "D":(46088772938,"42a38c7b82c79d11102afd65459d241c4283368f"),
 "E":(46092467221,"3a3e8707a689353864cc7aefc30248c7d0d1fad8"),
 "F":(46093652224,"a386a3e72bfdf38c32bde4f8b5217cd9a0a75f69")}
COARSE=tuple(range(11))+tuple(range(15,91,5))
FINE=tuple(i*.5 for i in range(21))+tuple(10+i*2.5 for i in range(1,33))
SHORT=tuple(range(11))
LIMITS={"Nc_kN":5.,"D_alg_rel":.05,"D_unload_rel":.05,"damage_abs":.005,
        "q_abs":5e-5,"compressed_area_abs_m2":.001,"thermal_inactive_area_abs_m2":.001}

def read_evidence(stage,meta,log):
    run,sha=SOURCES[stage]
    if meta.get("id")!=run or meta.get("head_sha")!=sha:
        raise ValueError("unexpected run identity")
    receipt={"stage":stage,"run_id":run,"head_sha":sha,"status":meta.get("status"),
             "conclusion":meta.get("conclusion")}
    if receipt["status"]!="completed":return {**receipt,"evidence":None,"reason":"CI_NOT_COMPLETE"}
    if receipt["conclusion"]!="success":return {**receipt,"evidence":None,"reason":"CI_NOT_SUCCESS"}
    def unique(marker,required=True):
        lines=[s.split(marker+" ",1)[1] for s in log.splitlines() if marker+" " in s]
        if len(lines)!=1:
            if required:raise ValueError("missing or duplicate "+marker)
            return None
        return json.loads(lines[0])
    payload=unique("SP_R10"+stage+"_EVIDENCE")
    return {**receipt,"evidence":payload,
            "reuse":unique("SP_R10F_REUSE_EVIDENCE",False) if stage=="F" else None}

def finite(v):
    if type(v) not in (int,float) or not math.isfinite(v):raise ValueError("finite numeric evidence required")
    return float(v)

def norm(v):
    return math.sqrt(sum(finite(a)**2 for row in v for a in row))

def verify_history(run,expected):
    rows=run["rows"]
    if run["status"]!="DIAGNOSTIC_COMPLETE" or len(rows)!=len(expected):
        return False
    if tuple(r.get("time_minutes") for r in rows)!=tuple(expected):return False
    for r in rows:
        if r.get("status")!="EQUILIBRATED_RESEARCH_SECTION":return False
        if not 0<=finite(r["max_conjugate_residual_kN"])<=1e-6:return False
    return True

def compare(a,b,expected_a,expected_b,*,time_refinement=False):
    """Require every scheduled state, then compare every shared checkpoint.
    Algorithmic tangent is increment-dependent; report separately on
    time refinement. Strict original gate retained, alongside an explicitly
    proposed state/unloading-only diagnostic, not an accepted replacement.
    """
    if not verify_history(a,expected_a) or not verify_history(b,expected_b):
        return {"complete":False,"strict_pass":False,"reason":"MISSING_OR_UNRESOLVED_CHECKPOINT"}
    X={r["time_minutes"]:r for r in a["rows"]};Y={r["time_minutes"]:r for r in b["rows"]}
    common=sorted(set(X)&set(Y))
    if not common or common[0]!=0 or common[-1]!=min(expected_a[-1],expected_b[-1]):
        return {"complete":False,"strict_pass":False,"reason":"INCOMPLETE_COMMON_WINDOW"}
    rows=[]
    for t in common:
        x,y=X[t],Y[t]
        def rel(k):
            v,w=x[k],y[k]
            if len(v)!=2 or len(w)!=2 or any(len(z)!=2 for z in v+w):
                raise ValueError("2x2 stiffness evidence required")
            return norm([[finite(a)-finite(b) for a,b in zip(u,z)] for u,z in zip(v,w)])/max(1.,norm(w))
        if len(x["q"])!=3 or len(y["q"])!=3:raise ValueError("three deformation coordinates required")
        d=lambda k:abs(finite(x[k])-finite(y[k]))
        rows.append({"t":t,"Nc_kN":abs(finite(x["concrete_actions_kN_kNm"][0])-finite(y["concrete_actions_kN_kNm"][0])),
             "D_alg_rel":rel("condensed_D_kNm2"),"D_unload_rel":rel("frozen_elastic_unloading_D_kNm2"),
             "damage_abs":d("area_weighted_damage"),
             "q_abs":max(abs(finite(u)-finite(v)) for u,v in zip(x["q"],y["q"])),
             "compressed_area_abs_m2":d("compressed_net_area_m2"),
             "thermal_inactive_area_abs_m2":d("thermal_inactive_net_area_m2")})
    maxima={k:max(r[k] for r in rows) for k in LIMITS}
    failed=[k for k,v in LIMITS.items() if maxima[k]>v]
    return {"complete":True,"common_checkpoints":len(common),"maxima":maxima,
            "failed":failed,"strict_pass":not failed,
            "state_unloading_diagnostic_pass":not any(k!="D_alg_rel" for k in failed) if time_refinement else None}

def prefix(run,times):
    return {**run,"rows":[r for r in run["rows"] if r.get("time_minutes") in times],
            "status":"DIAGNOSTIC_COMPLETE" if run["status"]=="DIAGNOSTIC_COMPLETE" else run["status"]}

def cost(run):
    """Observed accepted-step material calls, not elapsed-time speedup."""
    e=run.get("efficiency")
    if not e:return None
    actual=e["accepted_concrete_trial_calls"];avoided=e["avoided_redundant_concrete_trial_calls"]
    if any(type(x)!=int or x<0 for x in (actual,avoided)):raise ValueError("invalid trial counts")
    rows=[r for r in run["rows"] if r["status"]=="EQUILIBRATED_RESEARCH_SECTION"]
    if actual!=sum(r["trial_counts"]["concrete_trials"] for r in rows) or avoided!=sum(
       r["trial_counts"]["reused_trials"]*r["concrete_integration_points"] for r in rows):
        raise ValueError("trial counter mismatch")
    old=actual+avoided
    wall=finite(run["mechanical_wall_s"])
    if wall<0:raise ValueError("negative elapsed time")
    return {"actual_calls":actual,"avoided_calls":avoided,"counterfactual_uncached_calls":old,
            "call_reduction_fraction":avoided/old if old else None,"mechanical_wall_s":wall,
            "accepted_steps":len(rows),"full_history":run["status"]=="DIAGNOSTIC_COMPLETE"}

def consolidate(receipts):
    result={"sources":{},"comparisons":{},"costs":{},"front_audit":None,
            "numerical_section_admitted":False,"member_solver_admitted":False,
            "actual_t_R_minutes":None,"normative_claim":False}
    for stage in SOURCES:
        r=receipts.get(stage)
        if r is None:
            result["sources"][stage]={"status":"NOT_RETRIEVED"};continue
        if (r.get("run_id"),r.get("head_sha"))!=SOURCES[stage]:
            raise ValueError("receipt identity mismatch")
        result["sources"][stage]={k:v for k,v in r.items() if k not in ("evidence","reuse")}
        p=r.get("evidence")
        if r.get("status")!="completed" or r.get("conclusion")!="success" or p is None:continue
        runs={x["id"]:x for x in p["runs"]}
        if len(runs)!=len(p["runs"]):raise ValueError("duplicate run ids")
        specs={
          "D":[("T32_FRONT3","T64_FRONT3",COARSE,COARSE,False),
               ("T64_FRONT3","T64_FRONT4_SHORT",SHORT,SHORT,False)],
          "E":[("T64_CUT3","T80_CUT3",COARSE,COARSE,False),
               ("T80_CUT2","T80_CUT3",COARSE,COARSE,False),
               ("T80_CUT3","T80_DT025_CUT3",COARSE,COARSE,False),
               ("T80_CENTROID3_SHORT","T80_CUT3",SHORT,SHORT,False)],
          "F":[("CUT2_INITIAL","CUT2_RECONCILED",COARSE,COARSE,False),
               ("CUT2_RECONCILED","CUT3_RECONCILED_SHORT",SHORT,SHORT,False),
               ("CUT2_RECONCILED","CUT2_RECONCILED_FINE_TIME",COARSE,FINE,True)]}[stage]
        for a,b,ta,tb,temporal in specs:
            key=stage+":"+a+"->"+b
            if a not in runs or b not in runs:
                result["comparisons"][key]={"complete":False,"strict_pass":False,"reason":"CASE_NOT_AVAILABLE"};continue
            u,v=runs[a],runs[b]
            if ta==SHORT:u=prefix(u,SHORT)
            if tb==SHORT:v=prefix(v,SHORT)
            result["comparisons"][key]=compare(u,v,ta,tb,time_refinement=temporal)
        for id,run in runs.items():
            c=cost(run)
            if c is not None:result["costs"][stage+":"+id]=c
        if stage=="E":
            result["E_thermal_spatial"]=p.get("thermal_spatial")
            result["E_thermal_temporal"]=p.get("thermal_temporal")
        if stage=="F":
            result["front_audit"]=p.get("reconciled_front_audit")
            result["F_planning_wall_s"]=p.get("planning_wall_s")
            result["F_probe_counts"]=p.get("probe_counts")
            result["F_reuse_regression"]=r.get("reuse")
    # Cross-stage cases use different geometry and thermal/observation
    # schedules. Neither a reported PASS nor same point count constitutes
    # identity. A single final candidate needs matched full-duration runs.
    result["unresolved_candidate_gates"]=[
        "same_candidate_full_duration_thermal_spatial",
        "same_candidate_full_duration_thermal_temporal",
        "same_candidate_full_duration_mechanical_spatial",
        "same_candidate_full_duration_mechanical_temporal",
        "independent_front_resolution_with_bar_fallback_adjudication",
        "material_and_global_member_qualification"]
    result["cross_stage_pass_transfer_allowed"]=False
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt",action="append",default=[],help="STAGE=metadata.json,job.log")
    parser.add_argument("--output",required=True)
    args=parser.parse_args();receipts={}
    for spec in args.receipt:
        stage,paths=spec.split("=",1);meta,log=paths.split(",",1)
        if stage in receipts:raise ValueError("duplicate stage")
        receipts[stage]=read_evidence(stage,json.loads(Path(meta).read_text()),Path(log).read_text())
    Path(args.output).write_text(json.dumps(consolidate(receipts),indent=2,allow_nan=False)+"\n")

if __name__=="__main__":main()
