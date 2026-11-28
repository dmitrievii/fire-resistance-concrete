"""SP-R12B: snapshot-driven thermal/load homotopy and endpoint recovery.

Fixed predecessor history for all homotopy trials; actual temperature and
elapsed physical increment at each snapshot. This is a numerical homotopy,
NOT a fire history under changing load. Only original applied-load member
advance can commit. No continuous capacity enclosure, no physical t_R.
"""
import copy
import math
import numpy as np
from rc_fire.member import sp2026_r11a_history_member as m
from rc_fire.member import sp2026_r11b_extended_member as b
from rc_fire.member import sp2026_r11c_continuation as c
from rc_fire.member import sp2026_r11d_sequential as d
from rc_fire.member import sp2026_r12a_resistance as r
from rc_fire.mechanics import sp2026_r10c_quadrature as quad
from rc_fire.mechanics.sp2026_nominal_member import prepare_sp2026_design_section
from rc_fire.thermal.sp2026_heat import solve_sp2026_2d_heat,select_sp2026_snapshot

def evidence_float(value):
    """Native finite scalar at numerical -> evidence boundary; never coerce
    booleans, strings, arrays, complex or nonfinite values."""
    if isinstance(value,(bool,np.bool_)) or not isinstance(value,(int,float,np.integer,np.floating)):
        raise ValueError("real numeric scalar required")
    result=float(value)
    if not math.isfinite(result):raise ValueError("nonfinite numeric evidence")
    return result

def correct(evaluate,x,lam,free,control,target,*,tol=1e-7,max_iterations=35):
    """Solve free force equilibrium with one controlled displacement.
    Carry the complete converged coordinates AND load factor forward.
    Returns no state on rejection; evaluate is a pure return map.
    """
    x=np.asarray(x,dtype=float).copy();free=np.asarray(free,dtype=int)
    if control not in free or len(set(free))!=len(free) or tol<=0:
        raise ValueError("invalid displacement control")
    x[control]=target;lam=float(lam);other=free[free!=control]
    cached=None;calls=0
    def ev(z,l):
        nonlocal calls
        R,K,P,record=evaluate(z,l);calls+=1
        R=np.asarray(R);K=np.asarray(K);P=np.asarray(P)
        J=np.column_stack([K[np.ix_(free,other)],P[free]])
        if not np.all(np.isfinite(R[free])) or not np.all(np.isfinite(J)):
            raise ValueError("nonfinite augmented equilibrium")
        return R[free],J,record,K
    try:
        for i in range(max_iterations):
            if cached is None:v=ev(x,lam)
            else:v=cached;cached=None
            rr,J,record,K=v;err=float(np.max(np.abs(rr)))
            if err<=tol:
                return (x,evidence_float(lam),record,K),{"status":"EQUILIBRATED_CONTROLLED_TRIAL",
                    "iterations":i+1,"calls":calls,"residual_kNm":err}
            step=np.linalg.solve(J,-rr)
            for k in range(14):
                z=x.copy();z[other]+=step[:-1]*2.**(-k);l=lam+step[-1]*2.**(-k)
                try:trial=ev(z,l)
                except c.ERRORS:continue
                if np.max(np.abs(trial[0]))<err:
                    x=z;lam=l;cached=trial;break
            else:raise ValueError("controlled corrector line search")
        raise ValueError("controlled corrector iteration limit")
    except c.ERRORS as exc:
        return None,{"status":"UNRESOLVED_CONTROLLED_TRIAL","reason":str(exc),"calls":calls}

def operator(anchor,column,spec,field):
    beam=m.make_beam(column,spec)
    if m.contract(beam)!=anchor.contract:raise ValueError("member contract mismatch")
    minute=float(field["snapshot"]["time_minutes"]);m._snapshot_checked(field,minute,column)
    if minute<=anchor.thermal_minutes:raise ValueError("future actual snapshot required")
    t=1.+60*minute
    p,A,C,B,E,fy=m.sec._prepare(anchor.sections[0],column,field)
    P0=np.zeros(beam.total)
    for g in beam.stations:P0+=g.weight*g.B.T@np.array([beam.N,0.,0.])
    P0[:beam.nd]+=beam.F
    def evaluate(x,lam):
        if not math.isfinite(lam) or lam<0:raise ValueError("nonnegative load factor required")
        def law(i,q):
            old=anchor.sections[i];v=m.sec._trial(old,p,A,C,B,E,fy,t,q)
            if not all(m.steel.admitted(a,old.steel_mode,float(f),diagnostic_strain_limit=old.steel_strain_limit) for a,f in zip(v[9],fy)):
                raise ValueError("steel research strain domain")
            return v[0],v[1],(tuple(q),v)
        R,K,recs=beam.assemble(x,law);P=P0.copy()
        P[:beam.nd]+=beam.N*beam.G@(x[:beam.nd]+beam.initial)
        R+=(1-lam)*P;K[:beam.nd,:beam.nd]+=(1-lam)*beam.N*beam.G
        physical=(x[:beam.nd]+beam.initial)*beam.scale
        for i in range(beam.n-1):
            for u in (0.,*m._GQ,1.):
                _,Hp,_=m._shape(u,beam.z[i+1]-beam.z[i])
                for a in (0,1):
                    ids=np.r_[m._dofs(i,a,beam.n),m._dofs(i+1,a,beam.n)]
                    if abs(Hp@physical[ids])>.1:raise ValueError("small rotation domain")
        return R,K,-P,recs
    def verify(sol):
        x,lam,recs,K=sol
        axial=evidence_float(max(abs(float(F[0])-lam*beam.N) for F,J,rec in recs))
        if axial>1e-6:raise ValueError("axial equilibrium residual")
        for old,(_,_,(q,v)) in zip(anchor.sections,recs):
            for a,T,e in zip(old.probes,p.sp_boundary_temperature,m.sec._shape(p.sp_boundary_u,p.sp_boundary_v)@q):
                m.hot.trial_step(a,time_s=t,temperature_C=float(T),total_compression=float(e))
        try:eig=float(np.linalg.eigvalsh(beam.condensed(K))[0])
        except c.ERRORS:eig=None
        return {"axial_residual_kN":axial,"tangent_min_scaled_kNm":eig}
    return beam,evaluate,verify

def controlled(beam,ev,verify,seed,target):
    control=2*(beam.n//2)
    if beam.n%2!=1:raise ValueError("free midspan node required")
    sol,rep=correct(ev,seed[0],seed[1],beam.free,control,target)
    if sol is None:return None,rep
    try:v=verify(sol)
    except c.ERRORS as exc:return None,{"status":"UNRESOLVED_DOMAIN_CHECK","reason":str(exc)}
    x,lam,_,_=sol
    try:
        # Explicit complete evidence schema, not piecemeal conversion.
        axial=evidence_float(v["axial_residual_kN"])
        residual=evidence_float(rep["residual_kNm"])
        tangent=v.get("tangent_min_scaled_kNm")
        lam=evidence_float(lam)
        w=evidence_float(1000*(x[control]+beam.initial[control])*beam.scale[control])
        if not 0<=axial<=1e-6 or not 0<=residual<=1e-7 or lam<0:
            raise ValueError("endpoint evidence outside accepted domain")
        row={"status":rep["status"],"iterations":int(rep["iterations"]),
             "calls":int(rep["calls"]),"residual_kNm":residual,
             "axial_residual_kN":axial,"lambda":lam,"midspan_x_mm":w,
             "tangent_min_scaled_kNm":None if tangent is None else evidence_float(tangent)}
    except c.ERRORS as exc:return None,{"status":"UNRESOLVED_EVIDENCE_CONTRACT","reason":str(exc)}
    return sol,row

def thermal_homotopy(anchor,column,spec,fields):
    """Same fixed predecessor across actual snapshots; no commits.
    At fixed accepted midspan displacement, solve load factor and all
    remaining coordinates. Stop at first unresolved snapshot.
    """
    beam=m.make_beam(column,spec);control=2*(beam.n//2)
    target=anchor.x[control];seed=(np.asarray(anchor.x),1.)
    rows=[];stop=None;last=None;previous=anchor.thermal_minutes
    for field in fields:
        t=float(field["snapshot"]["time_minutes"])
        if t<=previous:raise ValueError("strict homotopy snapshot order")
        try:
            bb,ev,verify=operator(anchor,column,spec,field)
            sol,rep=controlled(bb,ev,verify,seed,target)
        except c.ERRORS as exc:sol=None;rep={"status":"UNRESOLVED_OPERATOR","reason":str(exc)}
        if sol is None:stop={"t":t,**rep};break
        seed=(sol[0],sol[1]);last=sol;rows.append({"t":t,**rep});previous=t
    return last,{"rows":rows,"stop":stop,"fixed_predecessor_minute":anchor.thermal_minutes,
        "committed_fire_history_changed":False}

def scan_from_seed(beam,ev,verify,center,*,step_mm=.5,negative_mm=4.,positive_mm=12.):
    """Two outward scans from same corrected endpoint equilibrium.
    Never jump across failed targets. Joined ordered rows are diagnostic
    envelope only. Seed coordinates retained privately for recovery.
    """
    if step_mm<=0 or negative_mm<=0 or positive_mm<=0:raise ValueError("scan extent")
    control=2*(beam.n//2);unit=1000*beam.scale[control];x0=center[0][control]
    mid,rep=controlled(beam,ev,verify,center,x0)
    if mid is None:return [],{"rows":[],"stop":rep,"complete":False}
    sides=[];stops={}
    for name,sign,extent in (("negative",-1,negative_mm),("positive",1,positive_mm)):
        seed=mid;out=[];count=round(extent/step_mm)
        if abs(count*step_mm-extent)>1e-10:raise ValueError("extent must be multiple of step")
        for j in range(1,count+1):
            sol,row=controlled(beam,ev,verify,seed,x0+sign*j*step_mm/unit)
            if sol is None:stops[name]=row;break
            out.append((sol,row));seed=sol
        sides.append(out)
    points=list(reversed(sides[0]))+[(mid,rep)]+sides[1]
    return points,{"rows":[v for _,v in points],"stop":stops or None,"complete":not stops,
        "expected_count":1+round(negative_mm/step_mm)+round(positive_mm/step_mm)}

def recover_applied(anchor,column,spec,field,beam,ev,verify,points,*,max_trials=12):
    """Bracket lambda=1 on adjacent sampled equilibria; try actual
    force-controlled commit using corrected displacement seed.
    A descending solution is not automatically admitted by this process.
    """
    pairs=[]
    for (a,ra),(b,rb) in zip(points,points[1:]):
        if (a[1]-1.)*(b[1]-1.)<=0:pairs.append((a,b))
    # Prefer the nearest control displacement; no claim of uniqueness.
    control=2*(beam.n//2)
    pairs.sort(key=lambda pair:min(abs(v[0][control]-anchor.x[control]) for v in pair))
    results=[]
    for a,b in pairs[:2]:
        for i in range(max_trials):
            mid=(a[0][control]+b[0][control])/2
            seed=min((a,b),key=lambda q:abs(q[1]-1.))
            sol,rep=controlled(beam,ev,verify,seed,mid)
            if sol is None:results.append(rep);break
            if abs(sol[1]-1.)<=1e-5 or i==max_trials-1:
                try:n,row=m.advance(anchor,column,spec,field,initial_guess=sol[0])
                except c.ERRORS as exc:n=anchor;row={"status":"UNRESOLVED_RECOVERY","reason":str(exc)}
                results.append({"lambda_seed":sol[1],"status":row["status"],"reason":row.get("reason")})
                if row["status"]==c.OK:return n,{"status":"APPLIED_LOAD_RECOVERED","attempts":results,"accepted":row}
                if n is not anchor:raise ArithmeticError("rejected recovery changed history")
                break
            if (a[1]-1.)*(sol[1]-1.)<=0:b=sol
            else:a=sol
    return anchor,{"status":"NO_ADMITTED_APPLIED_LOAD_RECOVERY","attempts":results,
        "sampled_crossing_pairs":len(pairs)}

def campaign(column,boundary,*,emit=None,refinement=None):
    if emit is None:emit=lambda event,payload:None
    col=copy.deepcopy(column);col["fire_minutes"]=90.
    ints=[float(i) for i in range(91)]
    # Retain exact R11E snapshot schedule; no extra thermal integration
    # substeps silently alter the existing thermal history.
    ts=sorted(set(ints)|{75.+i*.125 for i in range(121)})
    heat=solve_sp2026_2d_heat(col,boundary=boundary,cell_count_x=16,cell_count_y=16,
                             max_step_minutes=1.,sample_times_minutes=ts)
    fields={t:select_sp2026_snapshot(heat,t) for t in ts}
    p=prepare_sp2026_design_section(col,fields[0.],grid=8)
    mesh=quad.build(p,[fields[t] for t in (2.,5.,10.,30.,60.,90.)],base_grid=8,max_level=1,delta_C=100.)
    cc,spec=b.fixture_spec(col,length=12.,N=1500.,nodes=5,support="pinned")
    start=m.initial(cc,spec,fields[0.],grid=8,quadrature=mesh)
    states={}
    def advance(s,t):
        n,v=m.advance(s,cc,spec,fields[t],max_iterations=30)
        if v["status"]==c.OK:states[t]=n
        return n,v
    anchor,h=c.adaptive(start,[0.,2.,5.,10.,20.,30.,45.,60.,75.,90.],ints,advance,min_step=1.,max_attempts=65)
    fine={"stop":h["stop"],"rows":[],"status":"NO_ACCEPTED_ANCHOR"}
    if h["accepted"]:anchor,fine=d.refine_interval(anchor,h["stop"],ts,advance,resolution=.125)
    out={"last_accepted_minute":anchor.thermal_minutes if states else None,"original_stop":fine["stop"],
         "homotopy":None,"envelopes":[],"recovery":None,"sampled_threshold_pair":None,
         "section_admitted":False,"physical_failure_bracket_min":None,"actual_t_R_minutes":None,"normative_claim":False}
    emit("fire_stop",{"last_accepted_minute":out["last_accepted_minute"],"original_stop":out["original_stop"]})
    if not states or not fine["stop"]:return out
    end=fine["stop"]["unresolved_minute"]
    earlier=[t for t in states if t<anchor.thermal_minutes]
    if not earlier:return out
    # Matched endpoint scans from previous accepted history: homotopy
    # carries temperature/load seeds, but never changes predecessor.
    base=states[max(earlier)]
    endpoint_times=[anchor.thermal_minutes,end]
    matched=[];live=[]
    for t in endpoint_times:
        fs=[fields[v] for v in ts if base.thermal_minutes<v<=t]
        sol,hom=thermal_homotopy(base,cc,spec,fs)
        row={"t":t,"homotopy":hom}
        emit("matched_homotopy",row)
        if sol is not None and hom["stop"] is None:
            bb,ev,verify=operator(base,cc,spec,fields[t])
            pts,scan=scan_from_seed(bb,ev,verify,sol)
            row["scan"]=scan
            emit("matched_raw_scan",{"t":t,"anchor_minute":base.thermal_minutes,"scan":scan})
            live.append((t,bb,ev,verify,pts,scan))
            if scan["rows"]:
                try:
                    sample=r.endpoint({"rows":scan["rows"],"stop":scan["stop"]},N=1500.,
                                      expected_count=scan.get("expected_count",33))
                    row["sample"]=sample;matched.append((t,sample))
                except ValueError as exc:
                    row["evidence_error"]=str(exc)
                    emit("evidence_error",{"t":t,"reason":str(exc)})
        out["envelopes"].append(row)
    if len(matched)==2:
        out["sampled_threshold_pair"]=r.sampled_threshold_pair(matched[0][1],matched[1][1],
            t0=matched[0][0],t1=matched[1][0],same_anchor_and_scan=True)
    if refinement is not None and len(live)==2:
        out["matched_refinement"]=refinement(live,emit=emit)
    # Recovery uses EXACT latest accepted state, not the matched
    # sensitivity predecessor. A future endpoint is a different increment.
    sol,hom=thermal_homotopy(anchor,cc,spec,[fields[v] for v in ts if anchor.thermal_minutes<v<=end])
    out["homotopy"]=hom
    emit("recovery_homotopy",hom)
    if sol is not None and hom["stop"] is None:
        bb,ev,verify=operator(anchor,cc,spec,fields[end])
        pts,scan=scan_from_seed(bb,ev,verify,sol)
        out["recovery_scan"]=scan
        emit("recovery_raw_scan",{"t":end,"anchor_minute":anchor.thermal_minutes,"scan":scan})
        new,recovery=recover_applied(anchor,cc,spec,fields[end],bb,ev,verify,pts)
        out["recovery"]=recovery
        emit("recovery_result",recovery)
        if new is not anchor:
            out["last_accepted_minute"]=new.thermal_minutes
            out["original_interval_recovered"]=True
    return out
