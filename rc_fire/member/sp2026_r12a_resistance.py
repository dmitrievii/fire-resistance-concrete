"""SP-R12A: extract sampled proportional-load evidence, never normative R.

A sampled maximum is not an upper bound on the continuous path. An open
path gives observed load reach, not resistance. Accepted fire equilibrium,
sequential isothermal loading and anchored future-temperature envelopes
are distinct evidence types. No interpolation creates a constitutive state.
"""
import math
import json
import argparse
from pathlib import Path

def number(x):
    if type(x) not in (int,float) or not math.isfinite(x):
        raise ValueError("finite numeric evidence required")
    return float(x)

def sample(rows,*,family,expected_count,complete,N,anchor_w=None):
    if family not in ("sequential_isothermal","one_thermal_increment"):
        raise ValueError("explicit evidence family required")
    N=number(N)
    if N<=0 or type(expected_count)!=int or expected_count<3:
        raise ValueError("invalid load or expected sample count")
    w=[];lam=[]
    for i,r in enumerate(rows):
        if family=="sequential_isothermal" and i==0:
            w.append(number(anchor_w))
            if number(r["lambda"])!=1.:raise ValueError("invalid sequential anchor")
            if number(r["max_scaled_residual"])>1.1e-6/max(1.,N):
                raise ValueError("anchor residual")
        else:
            w.append(number(r["midspan_x_mm"]))
            rk="global_residual_kNm" if family=="sequential_isothermal" else "residual_kNm"
            if not 0<=number(r[rk])<=1e-6 or not 0<=number(r["axial_residual_kN"])<=1e-6:
                raise ValueError("unqualified sampled equilibrium")
        lam.append(number(r["lambda"]))
        if lam[-1]<0:raise ValueError("negative load factor")
    ok=bool(complete and len(rows)==expected_count and len(rows)>=3 and
            all(y>x for x,y in zip(w,w[1:])))
    p=max(range(len(lam)),key=lam.__getitem__) if lam else None
    peak=lam[p] if p is not None else None
    # Require unique interior global sampled maximum, both neighbors lower.
    turn=bool(ok and 0<p<len(lam)-1 and lam.count(peak)==1 and
              lam[p-1]<peak>lam[p+1])
    return {"family":family,"complete_requested_scan":ok,"sample_count":len(rows),
         "sampled_load_reach_lambda":peak,
         "sampled_load_reach_kN":N*peak if peak is not None else None,
         "sampled_peak_lambda":peak if turn else None,
         "sampled_peak_w_mm":w[p] if turn else None,
         "peak_neighbor_displacements_mm":[w[p-1],w[p+1]] if turn else None,
         "peak_neighbor_factors":[lam[p-1],peak,lam[p+1]] if turn else None,
         "U_sample":1./peak if turn and peak>0 else None,
         "reserve_sample_kN":N*(peak-1.) if turn else None,
         "status":"INTERIOR_SAMPLED_MAXIMUM" if turn else "OPEN_OR_UNRESOLVED_SCAN",
         "continuous_capacity_upper_bound":None,"normative_U":None,
         "displacement_range_mm":[w[0],w[-1]] if w else None}

def sequential(path,anchor_w,*,N,expected_steps):
    r=path["path"]
    return sample(r["rows"],family="sequential_isothermal",
        expected_count=expected_steps+1,complete=bool(r["stop"] is None and
        path["committed_path_increments"]==expected_steps and path["anchor_unchanged"]),
        N=N,anchor_w=anchor_w)

def endpoint(path,*,N,expected_count):
    return sample(path["rows"],family="one_thermal_increment",
        expected_count=expected_count,complete=path["stop"] is None,N=N)

def sampled_threshold_pair(a,b,*,t0,t1,same_anchor_and_scan):
    """First *observed* threshold change between matched sampled envelopes.
    No continuous capacity enclosure, no guarantee first global failure.
    In particular sequential and future-thermal scans cannot be paired.
    """
    t0,t1=number(t0),number(t1)
    if t1<=t0:raise ValueError("time order required")
    if (not same_anchor_and_scan or a["family"]!=b["family"] or
        a["family"]!="one_thermal_increment" or
        not a["complete_requested_scan"] or not b["complete_requested_scan"] or
        a["displacement_range_mm"]!=b["displacement_range_mm"]):
        return {"status":"NOT_COMPARABLE","observed_sampled_crossing":None,"actual_t_R_minutes":None}
    x,y=a["sampled_peak_lambda"],b["sampled_peak_lambda"]
    crossing=x is not None and y is not None and x>1. and y<1.
    return {"status":"OBSERVED_SAMPLED_THRESHOLD_CHANGE" if crossing else "NO_ESTABLISHED_SAMPLED_CHANGE",
        "observed_sampled_crossing":[t0,t1] if crossing else None,
        "peak_factors":[x,y],"continuous_crossing_proven":False,"actual_t_R_minutes":None}

def from_r11d(receipt):
    if (receipt.get("run_id"),receipt.get("head_sha"),receipt.get("status"),receipt.get("conclusion"))!=(
      46136773571,"6eb0c8cfb4b2b5111944f94292444ae7ee25a89c","completed","success"):
        raise ValueError("unexpected R11D receipt")
    d=receipt["evidence"];accepted=d["accepted"];t=number(d["last_accepted_minute"])
    if not accepted or accepted[-1]["t"]!=t or any(b["t"]<=a["t"] for a,b in zip(accepted,accepted[1:])):
        raise ValueError("invalid accepted history")
    if any(not 0<=number(r["max_axial_residual_kN"])<=1e-6 for r in accepted):
        raise ValueError("axial equilibrium evidence")
    w=accepted[-1]["midspan_x_mm"];N=1500.
    a=sequential(d["path_coarse"],w,N=N,expected_steps=6)
    b=sequential(d["path_fine"],w,N=N,expected_steps=12)
    if any(d[k]["anchor_minute"]!=t for k in ("path_coarse","path_fine")):
        raise ValueError("path anchor time mismatch")
    # Earlier accepted fire states demonstrate equilibrium at lambda=1
    # but provide NO peak resistance calculation.
    history=[{"t":r["t"],"status":"ACCEPTED_FIRE_EQUILIBRIUM",
        "applied_lambda":1.,"U_sample":None,"normative_U":None} for r in accepted]
    history[-1].update({"coarse_path":a,"refined_path":b,"U_sample":b["U_sample"]})
    stop=d["stop"]
    bracket=None
    if stop and stop["last_accepted_minute"]==t and number(stop["unresolved_minute"])>t:
        bracket=[t,stop["unresolved_minute"]]
        history.append({"t":bracket[1],"status":stop["status"],"U_sample":None,"normative_U":None})
    return {"source_run":receipt["run_id"],"history":history,"computational_stop_interval_min":bracket,
        "stop_class":d["stop_class"],"observed_sampled_crossing":None,"physical_failure_bracket_min":None,
        "section_admitted":False,"physical_material_admitted":False,"normative_claim":False,
        "actual_t_R_minutes":None}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("receipt");p.add_argument("--output",required=True)
    a=p.parse_args();Path(a.output).write_text(json.dumps(from_r11d(json.loads(Path(a.receipt).read_text())),indent=2,allow_nan=False)+"\n")

if __name__=="__main__":main()
