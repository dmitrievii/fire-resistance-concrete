"""SP-R11C adaptive fire-time stepping and anchored equilibrium continuation.

All calculations research only. Rejected time trials never commit. The
fixed-temperature continuation is a one-increment constitutive envelope
from one committed history, NOT a sequential load history, physical
postbuckling path or normative capacity. No extrapolation of temperatures.
"""
import copy
import math
import time
import numpy as np
from rc_fire.member import sp2026_r11a_history_member as m
from rc_fire.member import sp2026_r11b_extended_member as b
from rc_fire.mechanics import sp2026_r10c_quadrature as quad
from rc_fire.mechanics.sp2026_nominal_member import prepare_sp2026_design_section
from rc_fire.thermal.sp2026_heat import solve_sp2026_2d_heat,select_sp2026_snapshot

OK="EQUILIBRATED_RESEARCH_MEMBER"
ERRORS=(ValueError,ArithmeticError,np.linalg.LinAlgError)

def adaptive(initial,targets,available,advance,*,min_step=1.,max_attempts=150):
    """Use only supplied time snapshots, with recursive left-first recovery.
    An unresolved subinterval prevents all later advancement. A bracket
    describes a numerical stop only, not a physical failure time.
    """
    targets=tuple(float(t) for t in targets);available=tuple(sorted(set(float(t) for t in available)))
    if not targets or targets[0]!=0 or any(y<=x for x,y in zip(targets,targets[1:])) or any(t not in available for t in targets):
        raise ValueError("strict target and available schedule required")
    if min_step<=0 or max_attempts<1:raise ValueError("invalid adaptive policy")
    state=initial;accepted=[];attempts=[];stop=None
    def reach(t):
        nonlocal state,stop
        lo=state.thermal_minutes
        if len(attempts)>=max_attempts:
            stop={"last_accepted_minute":lo if accepted else None,"unresolved_minute":t,
                  "status":"UNRESOLVED_ATTEMPT_BUDGET"};return False
        try:new,r=advance(state,t)
        except ERRORS as exc:new=state;r={"status":"UNRESOLVED_MEMBER_INPUT_OR_DOMAIN","reason":str(exc)}
        attempts.append({"from_minute":lo,"to_minute":t,"status":r["status"],"reason":r.get("reason"),
                         "residual_kNm":r.get("scaled_residual_kNm")})
        if r["status"]==OK:
            if new is state or new.thermal_minutes!=t:raise ArithmeticError("invalid commit")
            state=new;accepted.append({**r,"requested_time_minutes":t});return True
        if new is not state:raise ArithmeticError("rejected trial changed state")
        middle=[x for x in available if lo+min_step-1e-10<=x<=t-min_step+1e-10 and lo<x<t]
        if accepted and middle:
            mid=min(middle,key=lambda x:(abs(x-(lo+t)/2),x))
            return reach(mid) and reach(t)
        stop={"last_accepted_minute":lo if accepted else None,"unresolved_minute":t,**r}
        return False
    for t in targets:
        if not reach(t):break
    return state,{"status":"DIAGNOSTIC_COMPLETE" if stop is None else "UNRESOLVED_HISTORY_STOP",
                  "accepted":accepted,"attempts":attempts,"stop":stop,
                  "recovered_attempts":sum(a["status"]!=OK and any(r["time_minutes"]>=a["to_minute"] for r in accepted) for a in attempts),
                  "actual_t_R_minutes":None,"physical_failure_proven":False}

def trace(residual,initial,*,steps=20,ds=.06,tol=1e-9,max_iterations=18):
    """Dimensionless pseudo-arclength continuation with hyperplane corrector.
    residual(y) returns r and full derivative [K,r_lambda], n by n+1.
    Every accepted point meets equilibrium and arclength residual. The
    load-coordinate turning event is sampled, not an exact critical point.
    """
    y=np.asarray(initial,dtype=float);prev=None;rows=[];stop=None
    if y.ndim!=1 or len(y)<2 or steps<1 or ds<=0:raise ValueError("invalid continuation settings")
    def evaluate(y):
        r,J=residual(y);r=np.asarray(r);J=np.asarray(J)
        if r.shape!=(len(y)-1,) or J.shape!=(len(y)-1,len(y)) or not np.all(np.isfinite(r)) or not np.all(np.isfinite(J)):
            raise ValueError("invalid continuation residual or tangent")
        return r,J
    try:r,J=evaluate(y)
    except ERRORS as exc:return {"rows":[],"stop":str(exc),"turning_intervals":[]}
    if np.max(np.abs(r))>tol:return {"rows":[],"stop":"ANCHOR_NOT_EQUILIBRATED","turning_intervals":[]}
    for i in range(steps+1):
        try:
            U,s,V=np.linalg.svd(J,full_matrices=True);v=V[-1]
            if s[-1]<=1e-12*max(1.,s[0]):raise ValueError("rank-deficient augmented equilibrium derivative")
            if prev is None:
                if v[-1]<0:v=-v
            elif v@prev<0:v=-v
        except ERRORS as exc:stop=str(exc);break
        rows.append({"coordinates":y.tolist(),"lambda":float(y[-1]),"d_lambda_ds":float(v[-1]),
                     "max_scaled_residual":float(np.max(np.abs(r)))})
        if i==steps:break
        pred=y+ds*v;candidate=pred.copy()
        def augmented(x):
            rr,jj=evaluate(x)
            return np.r_[rr,v@(x-pred)],np.vstack([jj,v])
        try:
            for j in range(max_iterations):
                z,A=augmented(candidate);err=np.max(np.abs(z))
                if err<=tol:break
                step=np.linalg.solve(A,-z)
                for k in range(10):
                    trial=candidate+step*2.**(-k)
                    try:zz,_=augmented(trial)
                    except ERRORS:continue
                    if np.max(np.abs(zz))<err:candidate=trial;break
                else:raise ValueError("continuation line search failed")
            else:raise ValueError("continuation corrector iteration limit")
            r,J=evaluate(candidate);y=candidate;prev=v
        except ERRORS as exc:stop=str(exc);break
    turns=[{"from_index":i,"to_index":i+1,"lambda_samples":[a["lambda"],b["lambda"]]}
           for i,(a,b) in enumerate(zip(rows,rows[1:])) if a["d_lambda_ds"]*b["d_lambda_ds"]<0]
    return {"rows":rows,"stop":stop,"turning_intervals":turns,"physical_failure_proven":False}

def anchored_operator(state,column,spec,field):
    """Same committed state for every fixed-temperature trial, no commits.
    All axial and transverse dead actions scaled together. Material creep
    time dependence is disabled in this particular R11A fixture (eta None).
    """
    beam=m.make_beam(column,spec)
    if m.contract(beam)!=state.contract or field["snapshot"]["time_minutes"]!=state.thermal_minutes:
        raise ValueError("anchor contract or temperature mismatch")
    p,A,C,B,E,fy=m.sec._prepare(state.sections[0],column,field)
    t=state.time_s+1.
    if any(v.active.parameters.viscosity_MPa_s is not None for s in state.sections for v in s.concrete):
        raise ValueError("anchored envelope requires no time-dependent dashpot")
    def base(x):
        def law(i,q):
            old=state.sections[i]
            r=m.sec._trial(old,p,A,C,B,E,fy,t,q)
            if not all(m.steel.admitted(a,old.steel_mode,float(f),diagnostic_strain_limit=old.steel_strain_limit) for a,f in zip(r[9],fy)):
                raise ValueError("steel research strain domain")
            return r[0],r[1],(tuple(q),r)
        r,K,recs=beam.assemble(x,law)
        # No accepted continuation point outside sampled rotation domain.
        physical=(x[:beam.nd]+beam.initial)*beam.scale
        for i in range(beam.n-1):
            for u in (0.,*m._GQ,1.):
                _,Hp,_=m._shape(u,beam.z[i+1]-beam.z[i])
                for a in (0,1):
                    ids=np.r_[m._dofs(i,a,beam.n),m._dofs(i+1,a,beam.n)]
                    if abs(Hp@physical[ids])>.1:raise ValueError("small rotation domain")
        return r,K,recs
    def evaluate(x,lam):
        if not math.isfinite(lam) or lam<0:raise ValueError("nonnegative load factor required")
        r,K,recs=base(x)
        P=np.zeros(beam.total)
        for g in beam.stations:P+=g.weight*g.B.T@np.array([beam.N,0.,0.])
        P[:beam.nd]+=beam.N*beam.G@(x[:beam.nd]+beam.initial)+beam.F
        r+=(1-lam)*P;K[:beam.nd,:beam.nd]+=(1-lam)*beam.N*beam.G
        return r,K,-P,recs
    def check_probes(recs):
        for old,(_,_,(q,r)) in zip(state.sections,recs):
            for a,T,e in zip(old.probes,p.sp_boundary_temperature,m.sec._shape(p.sp_boundary_u,p.sp_boundary_v)@q):
                m.hot.trial_step(a,time_s=t,temperature_C=float(T),total_compression=float(e))
    return beam,evaluate,check_probes

def perturbation(beam,evaluate,x,*,amplitudes=(1e-5,1e-6,1e-7)):
    """Axial-compatible direction from condensed reference tangent.
    One-sided directional slopes on actual return maps, including kinks;
    neither direction is a general stability proof.
    """
    R,K,_,_=evaluate(x,1.)
    lat=np.array([k for k in range(beam.nd) if k not in beam.fixed]);ax=np.arange(beam.nd,beam.total)
    T=beam.condensed(K);eig,V=np.linalg.eigh(T)
    v=np.zeros(beam.total);v[lat]=V[:,0];v[ax]=-np.linalg.solve(K[np.ix_(ax,ax)],K[np.ix_(ax,lat)]@v[lat])
    rows=[]
    for h in amplitudes:
        for sign in (-1,1):
            rr,_,_,_=evaluate(x+sign*h*v,1.)
            slope=float(v@(rr-R)/(sign*h))
            rows.append({"amplitude":h,"sign":sign,"directional_work_slope_scaled_kNm":slope})
    return {"reference_rayleigh_scaled_kNm":float(v@K@v),"rows":rows,
            "directional_only":True,"physical_failure_proven":False}

def probe_anchor(state,column,spec,field,*,steps=12,ds=.08):
    beam,op,check=anchored_operator(state,column,spec,field)
    x=np.asarray(state.x);free=beam.free
    scale=.01;force=max(1.,beam.N*beam.L)
    def unpack(y):
        q=x.copy();q[free]=y[:-1]*scale;return q
    def residual(y):
        R,K,P,rec=op(unpack(y),float(y[-1]))
        return R[free]/force,np.column_stack([K[np.ix_(free,free)]*scale,P[free]])/force
    try:direction=perturbation(beam,op,x)
    except ERRORS as exc:direction={"status":"UNRESOLVED_DIRECTIONAL_PROBE","reason":str(exc)}
    out=trace(residual,np.r_[x[free]/scale,1.],steps=steps,ds=ds,tol=1e-10)
    rows=[]
    for r in out["rows"]:
        q=unpack(np.asarray(r["coordinates"]));lam=r["lambda"]
        try:
            R,K,_,recs=op(q,lam);check(recs)
        except ERRORS as exc:out["stop"]="UNRESOLVED_BOUNDARY_OR_MATERIAL:"+str(exc);break
        w=(q[:beam.nd]+beam.initial)*beam.scale
        rows.append({**{k:v for k,v in r.items() if k!="coordinates"},
            "midspan_x_mm":1000*float(w[2*(beam.n//2)]),
            "scaled_force_residual_kNm":float(np.max(np.abs(R[free]))),
            "max_axial_residual_kN":max(abs(float(F[0])-lam*beam.N) for F,J,R in recs)})
    out["rows"]=rows;out["turning_intervals"]=[r for r in out["turning_intervals"] if r["to_index"]<len(rows)]
    return {"anchor_minute":state.thermal_minutes,"directional":direction,"continuation":out,
            "anchored_envelope_only":True,"committed_state_changed":False,"actual_t_R_minutes":None}

def campaign(column,boundary):
    c=copy.deepcopy(column);c["fire_minutes"]=150.
    ts=sorted(set(float(i) for i in range(151))|{3.5,7.5,37.5,52.5,67.5,82.5,135.})
    heat=solve_sp2026_2d_heat(c,boundary=boundary,cell_count_x=16,cell_count_y=16,
                             max_step_minutes=1.,sample_times_minutes=ts)
    fields={t:select_sp2026_snapshot(heat,t) for t in ts}
    p=prepare_sp2026_design_section(c,fields[0.],grid=8)
    mesh=quad.build(p,[fields[t] for t in (2.,5.,10.,30.,60.,90.,150.)],base_grid=8,max_level=1,delta_C=100.)
    runs=[]
    for N in (500.,1500.):
        cc,spec=b.fixture_spec(c,length=12.,N=N,nodes=5,support="pinned")
        targets=[0.,2.,5.,10.,20.,30.,45.,60.,75.,90.,120.,135.,150.]
        def attempt(s,t):return m.advance(s,cc,spec,fields[t],max_iterations=30)
        initial=m.initial(cc,spec,fields[0.],grid=8,quadrature=mesh)
        start=time.perf_counter()
        state,r=adaptive(initial,targets,ts,attempt,min_step=1.,max_attempts=80)
        # Probe last committed state only; no probes at failed thermal state.
        diagnostic=probe_anchor(state,cc,spec,fields[state.thermal_minutes]) if r["accepted"] else None
        summary=b.summarize({"status":r["status"],"rows":r["accepted"]+([r["stop"]] if r["stop"] else [])},
              [x["time_minutes"] for x in r["accepted"]]+([r["stop"]["unresolved_minute"]] if r["stop"] else []))
        runs.append({"N_kN":N,"last_accepted":summary["last_accepted"],"accepted":summary["accepted"],
                     "attempts":r["attempts"],"stop":r["stop"],"recovered_attempts":r["recovered_attempts"],
                     "anchor":diagnostic,"wall_s":time.perf_counter()-start})
    return {"runs":runs,"thermal_grid":16,"thermal_step_min":1.,"quadrature":mesh.evidence(),
            "thermal_schedule_changed_from_R11B":True,"physical_failure_proven":False,
            "actual_U_t":None,"actual_t_R_minutes":None,"normative_claim":False}
