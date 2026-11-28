"""SP-R11E — matched sequential-path and thermal-endpoint diagnostics.

Displacement control solves all free force residuals including axial
equilibrium and the proportional load factor. Endpoint envelope uses one
thermal increment from the SAME committed predecessor, never commits
candidate states. It is not a sequential fire history or proof of absence
of other equilibria. All admission gates remain explicitly unresolved.
"""
import copy
import math
import numpy as np
from rc_fire.member import sp2026_r11d_sequential as d
from rc_fire.member import sp2026_r11c_continuation as c
from rc_fire.member import sp2026_r11a_history_member as m
from rc_fire.member import sp2026_r11b_extended_member as b
from rc_fire.mechanics import sp2026_r10c_quadrature as quad
from rc_fire.mechanics.sp2026_nominal_member import prepare_sp2026_design_section
from rc_fire.thermal.sp2026_heat import solve_sp2026_2d_heat,select_sp2026_snapshot

def curve(path,anchor_w):
    rows=[dict(path["path"]["rows"][0],midspan_x_mm=anchor_w)] + path["path"]["rows"][1:]
    if path["path"]["stop"] is not None or len(rows)<3 or any(
        y["midspan_x_mm"]<=x["midspan_x_mm"] for x,y in zip(rows,rows[1:])):
        return None
    if not all(math.isfinite(r[k]) for r in rows for k in ("lambda","midspan_x_mm")):raise ValueError("nonfinite path")
    return rows

def compare_paths(a,b,anchor_w,*,N):
    X=curve(a,anchor_w);Y=curve(b,anchor_w)
    if a["anchor_minute"]!=b["anchor_minute"] or a["initial_inventory"]!=b["initial_inventory"] or X is None or Y is None:
        return {"comparable":False,"research_pass":False,"reason":"incomplete or different anchor"}
    lo=max(X[0]["midspan_x_mm"],Y[0]["midspan_x_mm"])
    hi=min(X[-1]["midspan_x_mm"],Y[-1]["midspan_x_mm"])
    if hi<=lo:return {"comparable":False,"research_pass":False}
    xx=[r["midspan_x_mm"] for r in X];yy=[r["midspan_x_mm"] for r in Y]
    # Piecewise-linear interpolation is an evidence comparison only, not a
    # computed constitutive state; include knots of both paths.
    w=sorted({lo,hi}|{v for v in xx+yy if lo<=v<=hi})
    dx=np.interp(w,xx,[r["lambda"] for r in X]);dy=np.interp(w,yy,[r["lambda"] for r in Y])
    px=max(X,key=lambda r:r["lambda"]);py=max(Y,key=lambda r:r["lambda"])
    peak_delta=abs(px["lambda"]-py["lambda"])
    reserve=abs(py["lambda"]-1.)
    turns=bool(a["path"]["sampled_maximum_intervals"] and b["path"]["sampled_maximum_intervals"]
       and px["midspan_x_mm"]<hi and py["midspan_x_mm"]<hi)
    # Require relative agreement of the small reserve, not just total load.
    max_delta=float(np.max(np.abs(dx-dy)))
    return {"comparable":True,"common_displacement_mm":[lo,hi],"sampled_turns_on_both":turns,
        "max_interpolated_load_delta_kN":N*max_delta,"peak_load_delta_kN":N*peak_delta,
        "peak_reserve_relative_delta":peak_delta/reserve if reserve>0 else None,
        "peak_displacement_delta_mm":abs(px["midspan_x_mm"]-py["midspan_x_mm"]),
        "peak_factors":[px["lambda"],py["lambda"]],
        "research_pass":bool(turns and reserve>0 and peak_delta/reserve<=.05 and
            max_delta*N<=.5 and abs(px["midspan_x_mm"]-py["midspan_x_mm"])<=.5),
        "interpolation_not_equilibrium":True}

def displacement_scan(evaluate,initial,free,control,targets,*,force_scale=1.,max_iterations=25,tol=1e-7):
    """Fixed displacement continuation, full equilibrium in free DOFs.
    evaluate(x,lambda) returns R,K,dR/dlambda,record. Never commit.
    Stop at first unresolved target; no skipping or inferred turning.
    """
    x=np.asarray(initial,dtype=float).copy();free=np.asarray(free,dtype=int)
    if control not in free or force_scale<=0:raise ValueError("invalid displacement control")
    remaining=free[free!=control];lam=1.;rows=[];stop=None
    for target in targets:
        z=x.copy();z[control]=target;l=lam
        def residual(q,a):
            R,K,P,rec=evaluate(q,a)
            r=R[free]/force_scale
            J=np.column_stack([K[np.ix_(free,remaining)],P[free]])/force_scale
            if not np.all(np.isfinite(r)) or not np.all(np.isfinite(J)):raise ValueError("nonfinite response")
            return r,J,rec
        try:
            for j in range(max_iterations):
                r,J,rec=residual(z,l);err=float(np.max(np.abs(r)))
                if err*force_scale<=tol:break
                step=np.linalg.solve(J,-r)
                for k in range(12):
                    zz=z.copy();zz[remaining]+=step[:-1]*2.**(-k);ll=l+step[-1]*2.**(-k)
                    try:rr,_,_=residual(zz,ll)
                    except c.ERRORS:continue
                    if np.max(np.abs(rr))<err:z=zz;l=ll;break
                else:raise ValueError("displacement corrector line search")
            else:raise ValueError("displacement corrector iteration limit")
            rows.append({"control":float(target),"lambda":float(l),"residual":err*force_scale,"record":rec})
            x=z;lam=l
        except c.ERRORS as exc:stop={"target":float(target),"reason":str(exc)};break
    turns=[i for i in range(1,len(rows)-1) if rows[i-1]["lambda"]<rows[i]["lambda"]>rows[i+1]["lambda"]]
    return {"rows":rows,"stop":stop,"sampled_maxima_indices":turns}

def endpoint_envelope(state,column,spec,field,*,offsets_mm):
    beam=m.make_beam(column,spec)
    if state.contract!=m.contract(beam):raise ValueError("member identity mismatch")
    minute=float(field["snapshot"]["time_minutes"])
    if minute<=state.thermal_minutes:raise ValueError("future actual thermal snapshot required")
    p,A,C,B,E,fy=m.sec._prepare(state.sections[0],column,field)
    t=1.+60*minute
    x=np.asarray(state.x);control=2*(beam.n//2)
    if beam.n%2!=1 or control not in beam.free:raise ValueError("free midspan node required")
    def evaluate(q,lam):
        if not math.isfinite(lam) or lam<0:raise ValueError("invalid proportional load factor")
        def law(i,v):
            old=state.sections[i];r=m.sec._trial(old,p,A,C,B,E,fy,t,v)
            if not all(m.steel.admitted(a,old.steel_mode,float(f),diagnostic_strain_limit=old.steel_strain_limit) for a,f in zip(r[9],fy)):
                raise ValueError("steel research strain domain")
            return r[0],r[1],(tuple(v),r)
        R,K,recs=beam.assemble(q,law)
        P=np.zeros(beam.total)
        for g in beam.stations:P+=g.weight*g.B.T@np.array([beam.N,0.,0.])
        P[:beam.nd]+=beam.N*beam.G@(q[:beam.nd]+beam.initial)+beam.F
        R+=(1-lam)*P;K[:beam.nd,:beam.nd]+=(1-lam)*beam.N*beam.G
        physical=(q[:beam.nd]+beam.initial)*beam.scale
        for i in range(beam.n-1):
            for u in (0.,*m._GQ,1.):
                _,Hp,_=m._shape(u,beam.z[i+1]-beam.z[i])
                for a in (0,1):
                    ids=np.r_[m._dofs(i,a,beam.n),m._dofs(i+1,a,beam.n)]
                    if abs(Hp@physical[ids])>.1:raise ValueError("small rotation domain")
        return R,K,-P,recs
    scan=displacement_scan(evaluate,x,beam.free,control,
        [x[control]+v/(1000*beam.scale[control]) for v in offsets_mm],force_scale=max(1.,beam.N*beam.L))
    rows=[]
    for r in scan["rows"]:
        recs=r["record"]
        try:
            axial=max(abs(float(F[0])-r["lambda"]*beam.N) for F,J,rec in recs)
            if axial>1e-6:raise ValueError("axial equilibrium residual")
            for old,(_,_,(q,z)) in zip(state.sections,recs):
                for a,T,e in zip(old.probes,p.sp_boundary_temperature,m.sec._shape(p.sp_boundary_u,p.sp_boundary_v)@q):
                    m.hot.trial_step(a,time_s=t,temperature_C=float(T),total_compression=float(e))
        except c.ERRORS as exc:scan["stop"]={"target":r["control"],"reason":str(exc)};break
        rows.append({"midspan_x_mm":1000*(r["control"]+beam.initial[control])*beam.scale[control],
          "lambda":r["lambda"],"residual_kNm":r["residual"],"axial_residual_kN":axial})
    turns=[i for i in scan["sampled_maxima_indices"] if i+1<len(rows)]
    peak=max((r["lambda"] for r in rows),default=None)
    return {"anchor_minute":state.thermal_minutes,"endpoint_minute":minute,"rows":rows,
            "stop":scan["stop"],"sampled_maxima_indices":turns,"sampled_peak_lambda":peak,
            "sampled_peak_below_applied":bool(turns and peak<1.),
            "one_increment_envelope_only":True,"physical_failure_proven":False}

def campaign(column,boundary):
    col=copy.deepcopy(column);col["fire_minutes"]=90.
    ints=[float(i) for i in range(91)]
    ts=sorted(set(ints)|{75.+i*.125 for i in range(121)})
    heat=solve_sp2026_2d_heat(col,boundary=boundary,cell_count_x=16,cell_count_y=16,
                             max_step_minutes=1.,sample_times_minutes=ts)
    fields={t:select_sp2026_snapshot(heat,t) for t in ts}
    p=prepare_sp2026_design_section(col,fields[0.],grid=8)
    mesh=quad.build(p,[fields[t] for t in (2.,5.,10.,30.,60.,90.)],base_grid=8,max_level=1,delta_C=100.)
    cc,spec=b.fixture_spec(col,length=12.,N=1500.,nodes=5,support="pinned")
    start=m.initial(cc,spec,fields[0.],grid=8,quadrature=mesh)
    def advance(s,t):return m.advance(s,cc,spec,fields[t],max_iterations=30)
    anchor,r=c.adaptive(start,[0.,2.,5.,10.,20.,30.,45.,60.,75.,90.],ints,advance,min_step=1.,max_attempts=65)
    out={"integer_stop":r["stop"],"integer_anchor_minute":anchor.thermal_minutes,
         "quarter":None,"eighth":None,"path_comparison":None,"endpoint":None,
         "section_numerically_admitted":False,"physical_failure_proven":False,"actual_t_R_minutes":None,"normative_claim":False}
    if not r["accepted"] or r["stop"] is None:return out
    # Both branches share exact preceding state, thermal solution, mesh.
    qa,q=d.refine_interval(anchor,r["stop"],[t for t in ts if t*4==round(t*4)],advance,resolution=.25)
    fa,f=d.refine_interval(anchor,r["stop"],ts,advance,resolution=.125)
    for k,s,v in (("quarter",qa,q),("eighth",fa,f)):
        out[k]={"last":s.thermal_minutes,"stop":v["stop"],"status":v["status"],
                "accepted_times":[z["time_minutes"] for z in v["rows"]]}
    # Matched sequential increment comparison from the finer accepted state.
    field=fields[fa.thermal_minutes]
    a=d.trace_member(fa,cc,spec,field,steps=12,ds=.03)
    bpath=d.trace_member(fa,cc,spec,field,steps=24,ds=.015)
    beam=m.make_beam(cc,spec);w=1000*(fa.x[2*(beam.n//2)]+beam.initial[2*(beam.n//2)])*beam.L
    out["paths"]={"coarse":a,"fine":bpath}
    out["path_comparison"]=compare_paths(a,bpath,w,N=1500.)
    if f["stop"] is not None and f["stop"]["unresolved_minute"]>fa.thermal_minutes:
        try:out["endpoint"]=endpoint_envelope(fa,cc,spec,fields[f["stop"]["unresolved_minute"]],
                    offsets_mm=[-4.+i*.5 for i in range(33)])
        except c.ERRORS as exc:out["endpoint"]={"status":"UNRESOLVED_ENDPOINT_OPERATOR","reason":str(exc)}
    return out
