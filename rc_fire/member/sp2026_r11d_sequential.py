"""SP-R11D sequential constitutive load-path continuation (research).

Fire time is frozen; synthetic increment clock only orders rate-independent
return maps. Separate branch state, never fed back into a fire history.
Proportional dead actions; no certified physical capacity or failure time.
"""
from dataclasses import dataclass
import copy
import math
import numpy as np
from rc_fire.member import sp2026_r11c_continuation as c
from rc_fire.member import sp2026_r11a_history_member as m
from rc_fire.member import sp2026_r11b_extended_member as b
from rc_fire.mechanics import sp2026_r10c_quadrature as quad
from rc_fire.mechanics.sp2026_nominal_member import prepare_sp2026_design_section
from rc_fire.thermal.sp2026_heat import solve_sp2026_2d_heat,select_sp2026_snapshot

def classify_stop(stop):
    if stop is None:return "REQUESTED_WINDOW_COMPLETE"
    k=stop.get("status","");reason=str(stop.get("reason","")).lower()
    if "steel temperature outside" in reason:return "STEEL_TEMPERATURE_DOMAIN"
    if "STEEL_HISTORY_DOMAIN" in k or "steel research strain domain" in reason:return "STEEL_STRAIN_DOMAIN"
    if "SMALL_ROTATION" in k or "small rotation domain" in reason:return "KINEMATIC_DOMAIN"
    if "NONPOSITIVE_GLOBAL" in k and stop.get("converged_equilibrium") is True:return "EQUILIBRATED_NONPOSITIVE_TANGENT"
    if "LINE_SEARCH" in k or "ITERATION_LIMIT" in k or "SINGULAR_GLOBAL" in k:return "NUMERICAL_EQUILIBRIUM_STOP"
    if "ATTEMPT_BUDGET" in k:return "COMPUTATIONAL_BUDGET"
    return "UNRESOLVED_OTHER_DOMAIN_OR_NUMERICS"

def sequential(initial,y0,operator,commit,*,steps=12,ds=.06,min_ds=.0075,tol=1e-10,anchor_tol=None,max_iterations=18):
    """Secant-predictor pseudo-arclength, fresh operator per committed state.

    operator(state) -> callable(y) -> (r, J, trial_record).
    commit(state,y,trial_record) returns (new_state, diagnostic).
    The commit callback must be pure and validate all material domains.
    No rejected candidate may affect state. Arclength step reduced on
    failed corrector or commit. Sampled turning points are path-specific.
    """
    y=np.asarray(y0,dtype=float).copy();state=initial;prev=None;rows=[];attempts=[];stop=None
    if y.ndim!=1 or len(y)<2 or steps<1 or not 0<min_ds<=ds or tol<=0:
        raise ValueError("invalid continuation controls")
    anchor_tol=tol if anchor_tol is None else float(anchor_tol)
    if not math.isfinite(anchor_tol) or anchor_tol<tol:raise ValueError("invalid anchor tolerance")
    def checked(ev,x):
        r,J,trial=ev(x);r=np.asarray(r);J=np.asarray(J)
        if r.shape!=(len(y)-1,) or J.shape!=(len(y)-1,len(y)) or not np.all(np.isfinite(r)) or not np.all(np.isfinite(J)):
            raise ValueError("invalid continuation residual or tangent")
        return r,J,trial
    for i in range(steps+1):
        try:
            ev=operator(state);r,J,_=checked(ev,y)
            if np.max(np.abs(r))>(anchor_tol if i==0 else tol):
                raise ValueError("committed state not re-equilibrated under zero-change return map")
            # At yield the exact endpoint tangent may choose unloading.
            # Use previous accepted secant to orient subsequent predictors.
            if prev is None:
                _,s,V=np.linalg.svd(J,full_matrices=True)
                if s[-1]<=1e-12*max(1.,s[0]):raise ValueError("rank-deficient initial augmented tangent")
                v=V[-1]
                if v[-1]<0:v=-v
                rows.append({"lambda":float(y[-1]),"coordinates":y.tolist(),"path_increment":0.,
                             "max_scaled_residual":float(np.max(np.abs(r)))})
            else:v=prev
            if i==steps:break
        except c.ERRORS as exc:stop={"status":"UNRESOLVED_ANCHOR","reason":str(exc)};break
        h=ds;success=False
        while h>=min_ds-1e-14:
            pred=y+h*v;z=pred.copy()
            def aug(x):
                rr,jj,tr=checked(ev,x)
                return np.r_[rr,v@(x-pred)],np.vstack([jj,v]),tr
            try:
                for it in range(max_iterations):
                    rr,A,tr=aug(z);err=float(np.max(np.abs(rr)))
                    if err<=tol:break
                    dz=np.linalg.solve(A,-rr)
                    for k in range(10):
                        zz=z+dz*2.**(-k)
                        try:rr2,_,_=aug(zz)
                        except c.ERRORS:continue
                        if np.max(np.abs(rr2))<err:z=zz;break
                    else:raise ValueError("sequential corrector line search")
                else:raise ValueError("sequential corrector iteration limit")
                new,diag=commit(state,z,tr)
                if new is state:raise ArithmeticError("commit did not create new history")
                # Recheck equilibrium from new committed state at zero
                # change. In particular, do not accept a material return
                # that changes stress upon immediate replay.
                post,_,_=checked(operator(new),z)
                if np.max(np.abs(post))>tol:raise ValueError("post-commit equilibrium mismatch")
                d=z-y;length=float(np.linalg.norm(d))
                if length<=1e-14 or d@v<=0:raise ValueError("non-forward continuation correction")
                prev=d/length
                rows.append({"lambda":float(z[-1]),"coordinates":z.tolist(),"path_increment":length,
                             "d_lambda_secant":float(prev[-1]),"max_scaled_residual":float(np.max(np.abs(rr[:-1]))),
                             "post_commit_residual":float(np.max(np.abs(post))),**diag})
                state=new;y=z;success=True
                attempts.append({"step":i+1,"ds":h,"status":"ACCEPTED"});break
            except c.ERRORS as exc:
                attempts.append({"step":i+1,"ds":h,"status":"REJECTED","reason":str(exc)})
                h/=2
        if not success:
            stop={"status":"UNRESOLVED_SEQUENTIAL_INCREMENT","reason":attempts[-1].get("reason","step limit")}
            break
    turns=[]
    for i in range(2,len(rows)):
        a,b=rows[i-1],rows[i]
        if a["d_lambda_secant"]>0 and b["d_lambda_secant"]<0:
            turns.append({"peak_sample_index":i-1,"neighbor_indices":[i-2,i],
                          "lambda_samples":[rows[i-2]["lambda"],a["lambda"],b["lambda"]],
                          "sampled_peak_lambda":a["lambda"]})
    return state,{"rows":rows,"attempts":attempts,"stop":stop,"sampled_maximum_intervals":turns,
                  "physical_failure_proven":False,"actual_t_R_minutes":None}

@dataclass(frozen=True)
class PathState:
    member:object
    lam:float
    increments:int=0

def material_inventory(s):
    """Irreversible-state summaries and exact per-point monotonic checks."""
    cs=[v.active for g in s.member.sections for v in g.concrete]
    steel=[v for g in s.member.sections for v in g.steel_states]
    return {"max_damage":max(v.damage for v in cs),
            "max_concrete_plastic_strain":max(v.plastic_compression for v in cs),
            "max_transient_strain":max(v.transient_compression for v in cs),
            "max_steel_accumulated_plastic_strain":max(v.accumulated_plastic_strain for v in steel)}

def trace_member(anchor,column,spec,field,*,steps=8,ds=.06):
    beam=m.make_beam(column,spec)
    free=beam.free;ref=np.asarray(anchor.x);scale=.01;force=max(1.,beam.N*beam.L)
    def unpack(y):
        x=ref.copy();x[free]=y[:-1]*scale;return x
    def operator(s):
        bb,op,check=c.anchored_operator(s.member,column,spec,field)
        def ev(y):
            x=unpack(y);lam=float(y[-1]);R,K,P,recs=op(x,lam)
            return R[free]/force,np.column_stack([K[np.ix_(free,free)]*scale,P[free]])/force,(x,lam,R,K,recs)
        return ev
    def commit(s,y,trial):
        x,lam,R,K,recs=trial;old=s.member
        err=float(np.max(np.abs(R[free])))
        axial=max(abs(float(F[0])-lam*beam.N) for F,J,rec in recs)
        if err>1e-6 or axial>1e-6:raise ValueError("unscaled global or axial residual")
        p,A,C,B,E,fy=m.sec._prepare(old.sections[0],column,field)
        clock=old.time_s+1.;new=[]
        for a,(F,J,(q,r)) in zip(old.sections,recs):
            _,_,cs,ledger,sc,ss,Fc,Fs,es,st,ratios=r
            probes=[]
            for v,T,e in zip(a.probes,p.sp_boundary_temperature,m.sec._shape(p.sp_boundary_u,p.sp_boundary_v)@q):
                n,_=m.hot.trial_step(v,time_s=clock,temperature_C=float(T),total_compression=float(e));probes.append(n)
            for u,v in zip(a.concrete+ a.probes,tuple(cs)+tuple(probes)):
                if u.thermal_cutoff!=v.thermal_cutoff or u.maximum_temperature_C!=v.maximum_temperature_C:
                    raise ValueError("thermal state changed on isothermal path")
                for k in ("damage","plastic_compression","transient_compression","basic_creep_compression"):
                    if getattr(v.active,k)<getattr(u.active,k)-1e-14:raise ArithmeticError("irreversible concrete state decreased")
                if abs(v.active.transient_compression-u.active.transient_compression)>1e-13 or abs(v.active.basic_creep_compression-u.active.basic_creep_compression)>1e-13:
                    raise ArithmeticError("spurious creep on isothermal rate-independent path")
            if any(v.accumulated_plastic_strain<u.accumulated_plastic_strain-1e-14 for u,v in zip(a.steel_states,st)):
                raise ArithmeticError("irreversible steel history decreased")
            new.append(m.sec.SectionState(a.geometry,a.grid,a.thermal_method,clock,a.thermal_minutes,tuple(q),
                       tuple(cs),tuple(probes),tuple(p.theta_s),st,a.steel_mode,a.steel_strain_limit,a.quadrature))
        n=PathState(m.MemberState(tuple(x),tuple(new),clock,old.thermal_minutes,old.contract),lam,s.increments+1)
        w=(x[:beam.nd]+beam.initial)*beam.scale
        try:eig=float(np.linalg.eigvalsh(beam.condensed(K))[0])
        except c.ERRORS:eig=None
        return n,{"midspan_x_mm":1000*float(w[2*(beam.n//2)]),"axial_residual_kN":axial,
                 "global_residual_kNm":err,"tangent_min_scaled_kNm":eig,**material_inventory(n)}
    start=PathState(anchor,1.)
    final,r=sequential(start,np.r_[ref[free]/scale,1.],operator,commit,steps=steps,ds=ds,min_ds=ds/8,tol=min(1e-10,5e-7/force),anchor_tol=1.1e-6/force)
    # Do not expose a branch state as a resumable fire MemberState.
    return {"anchor_minute":anchor.thermal_minutes,"initial_inventory":material_inventory(start),
            "final_inventory":material_inventory(final),"committed_path_increments":final.increments,
            "anchor_unchanged":start.member is anchor,"rate_independent_isothermal_path":True,
            "path":r,"actual_t_R_minutes":None}

def campaign(column,boundary):
    col=copy.deepcopy(column);col["fire_minutes"]=90.
    ts=[float(i) for i in range(91)]
    heat=solve_sp2026_2d_heat(col,boundary=boundary,cell_count_x=16,cell_count_y=16,
                             max_step_minutes=1.,sample_times_minutes=ts)
    fields={t:select_sp2026_snapshot(heat,t) for t in ts}
    p=prepare_sp2026_design_section(col,fields[0.],grid=8)
    mesh=quad.build(p,[fields[t] for t in (2.,5.,10.,30.,60.,90.)],base_grid=8,max_level=1,delta_C=100.)
    cc,spec=b.fixture_spec(col,length=12.,N=1500.,nodes=5,support="pinned")
    start=m.initial(cc,spec,fields[0.],grid=8,quadrature=mesh)
    def advance(s,t):return m.advance(s,cc,spec,fields[t],max_iterations=30)
    schedule=[0.,2.,5.,10.,20.,30.,45.,60.,75.,90.]
    last,r=c.adaptive(start,schedule,ts,advance,min_step=1.,max_attempts=65)
    a=None;f=None
    if r["accepted"]:
        a=trace_member(last,cc,spec,fields[last.thermal_minutes],steps=6,ds=.06)
        f=trace_member(last,cc,spec,fields[last.thermal_minutes],steps=12,ds=.03)
    stop=r["stop"]
    return {"fixture":"SLENDER1500_PINNED","quadrature":mesh.evidence(),"last_accepted_minute":last.thermal_minutes if r["accepted"] else None,
            "accepted":[{"t":v["time_minutes"],"midspan_x_mm":1000*v["total_w_x_m"][len(v["total_w_x_m"])//2],
                         "max_axial_residual_kN":v["max_axial_residual_kN"]} for v in r["accepted"]],
            "stop":stop,"stop_class":classify_stop(stop),"attempts":r["attempts"],"recovered_attempts":r["recovered_attempts"],
            "path_coarse":a,"path_fine":f,"same_nominal_arclength_budget":.36,
            "physical_failure_proven":False,"actual_t_R_minutes":None,"normative_claim":False}
