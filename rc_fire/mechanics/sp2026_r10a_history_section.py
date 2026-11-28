"""SP-R10A: first-order history-dependent reinforced concrete section.

Research only: positive net-concrete cell areas, fixed centre quadrature,
R9G independent concrete history, physical bar positions, elastic-only
SP steel. No steel yield history, member stability, physical t_R or
normative U. Fixed localization length is declared, NOT cell width.
All trial states derive from one committed state; no root switching.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import numpy as np
from rc_fire.mechanics import sp2026_r9g_hot_domain as hot
from rc_fire.mechanics import sp2026_r10b_steel_history as steel_history
from rc_fire.mechanics import sp2026_nonisothermal_coupling as material
from rc_fire.mechanics.sp2026_nominal_member import prepare_sp2026_design_section
from rc_fire.materials.sp2026_fire import steel_at_sp_fire
from rc_fire.thermal.sp2026_annex_k_field import build_annex_k_snapshot,ANNEX_K_METHOD
from rc_fire.thermal.sp2026_heat import solve_sp2026_2d_heat,select_sp2026_snapshot
import copy

VERSION="SP-R10A-positive-net-fibre-history-v1"
class SectionHistoryError(ValueError):pass

def _circle_rectangle_area(cx,cy,r,x0,x1,y0,y1):
    """Integrate circle/rectangle intersection exactly by piecewise primitives."""
    a=max(x0-cx,-r);b=min(x1-cx,r)
    if a>=b:return 0.
    lo=y0-cy;hi=y1-cy
    cuts=[a,b]
    for v in (lo,hi):
        if abs(v)<=r:  # include tangent split at x=0 for y=±r
            z=math.sqrt(max(0.,r*r-v*v))
            cuts.extend(x for x in (-z,z) if a<x<b)
    cuts=sorted(set(cuts))
    def primitive(x):
        return .5*(x*math.sqrt(max(0.,r*r-x*x))+r*r*math.asin(max(-1.,min(1.,x/r))))
    area=0.
    for l,h in zip(cuts,cuts[1:]):
        z=math.sqrt(max(0.,r*r-((l+h)/2)**2))
        top=min(hi,z);bottom=max(lo,-z)
        if top<=bottom:continue
        top_slope=1. if z<hi else 0.
        bottom_slope=-1. if -z>lo else 0.
        constant=(0. if top_slope else hi)-(0. if bottom_slope else lo)
        area+=(top_slope-bottom_slope)*(primitive(h)-primitive(l))+constant*(h-l)
    return max(0.,area)

def net_areas(p,grid):
    dx=p.b_m/grid;dy=p.h_m/grid
    A=np.asarray(p.area,dtype=float).copy()
    bars=list(zip(p.bar_x,p.bar_y,np.sqrt(p.bar_area/math.pi),p.bar_area))
    for i,(x,y,r,B) in enumerate(bars):
        for xx,yy,rr,_ in bars[:i]:
            if math.hypot(x-xx,y-yy)<r+rr-1e-12:
                raise SectionHistoryError("overlapping physical bars")
        removed=np.asarray([_circle_rectangle_area(x,y,r,xx-dx/2,xx+dx/2,yy-dy/2,yy+dy/2)
                            for xx,yy in zip(p.x,p.y)])
        if abs(removed.sum()-B)>1e-10*max(1.,B):
            raise SectionHistoryError("bar displacement area not conserved")
        A-=removed
    if np.min(A)<-1e-12:raise SectionHistoryError("negative net concrete cell area")
    A=np.maximum(A,0.)
    if abs(A.sum()+p.bar_area.sum()-p.b_m*p.h_m)>1e-10:
        raise SectionHistoryError("cross-section area conservation failed")
    return A

def _geometry(p,A):
    return (p.b_m,p.h_m,tuple(p.x),tuple(p.y),tuple(A),
            tuple(p.bar_ids),tuple(p.bar_x),tuple(p.bar_y),tuple(p.bar_area),
            tuple(p.sp_boundary_u),tuple(p.sp_boundary_v),p.aggregate,
            p.sp_concrete_normal["f_ck_MPa"],p.sp_concrete_normal["E_cm_GPa"],
            p.sp_steel_normal["f_yk_MPa"],p.sp_steel_normal["E_s_GPa"])

@dataclass(frozen=True)
class SectionState:
    geometry:tuple
    grid:int
    thermal_method:str
    time_s:float
    thermal_minutes:float
    q:tuple
    concrete:tuple
    probes:tuple
    steel_temperatures:tuple
    steel_states:tuple
    steel_mode:str
    steel_strain_limit:float
    quadrature:object=None

def make_initial(column,field,*,grid,mode,length_mm,Gwork_N_mm,yield_fraction,
                 strength_basis,steel_mode=steel_history.ELASTIC,steel_strain_limit=.02,quadrature=None):
    if steel_mode not in (steel_history.ELASTIC,steel_history.PLASTIC):raise SectionHistoryError("explicit steel mode required")
    if not math.isfinite(steel_strain_limit) or steel_strain_limit<=0:raise SectionHistoryError("positive steel research domain guard required")
    p=prepare_sp2026_design_section(column,field,grid=grid)
    if field["snapshot"]["time_minutes"]!=0.:
        raise SectionHistoryError("history must start at ambient time zero")
    if strength_basis not in ("SP5_ACCIDENTAL_FCD","SP_CHARACTERISTIC_FCK"):
        raise SectionHistoryError("explicit strength basis required")
    norm=p.sp_concrete_normal
    fc=(p.sp5_design_parameters["fcd_20_MPa"] if strength_basis=="SP5_ACCIDENTAL_FCD"
        else norm["f_ck_MPa"])
    pars=material.Parameters(p.aggregate,fc,1000*norm["E_cm_GPa"],
            norm["eps_c1_permille"]/1000.,yield_fraction,Gwork_N_mm,length_mm,2.35,None,
            "R10A research: "+strength_basis+"; unqualified peak scaling and softening")
    if quadrature is None:A=net_areas(p,grid)
    else:
        from rc_fire.mechanics.sp2026_r10c_quadrature import apply_quadrature
        A=apply_quadrature(p,field,quadrature)
    states=tuple(hot.initial_state(pars,mode) for _ in A)
    probes=tuple(hot.initial_state(pars,mode) for _ in p.sp_boundary_u)
    return SectionState(_geometry(p,A),grid,field["thermal_method"],0.,0.,
                        (0.,0.,0.),states,probes,tuple(p.theta_s),
                        tuple(steel_history.SteelState() for _ in p.theta_s),steel_mode,steel_strain_limit,quadrature)

def _shape(u,v):
    return np.column_stack((np.ones(len(u)),v,u))

def _prepare(s,column,field):
    p=prepare_sp2026_design_section(column,field,grid=s.grid)
    if s.quadrature is None:A=net_areas(p,s.grid)
    else:
        from rc_fire.mechanics.sp2026_r10c_quadrature import apply_quadrature
        A=apply_quadrature(p,field,s.quadrature)
    if _geometry(p,A)!=s.geometry or field["thermal_method"]!=s.thermal_method:
        raise SectionHistoryError("section geometry/material/thermal route changed")
    if np.any(np.asarray(p.theta_s)<np.asarray(s.steel_temperatures)-1e-8):
        raise SectionHistoryError("steel cooling history not qualified")
    E=[];fy=[]
    for T in p.theta_s:
        m=steel_at_sp_fire(p.sp_steel,float(T),p.sp_steel_normal)
        E.append(m.elastic_modulus_MPa)
        fy.append(p.sp5_design_parameters["fyd_20_MPa"]*m.strength_factor)
    return p,A,_shape(p.u,p.v),_shape(p.bar_u,p.bar_v),np.asarray(E),np.asarray(fy)

def _trial(s,p,A,C,B,E,fy,t,q,*,counts=None):
    ep=C@q
    cs=[];stress=[];tangent=[];rows=[]
    for old,T,e in zip(s.concrete,p.theta_c,ep):
        if counts is not None:counts['concrete_trials']+=1
        new,r=hot.trial_step(old,time_s=t,temperature_C=float(T),total_compression=float(e))
        cs.append(new);stress.append(r["stress_MPa"]);tangent.append(r["effective_tangent_MPa"]);rows.append(r)
    sc=np.asarray(stress);tc=np.asarray(tangent)
    es=B@q+p.eps_th_s
    trials=[steel_history.trial(old,temperature_C=T,mechanical_strain=e,E_MPa=ee,fy_MPa=f,mode=s.steel_mode)
            for old,T,e,ee,f in zip(s.steel_states,p.theta_s,es,E,fy)]
    steel_states=tuple(x[0] for x in trials)
    ss=np.asarray([x.stress_MPa for x in steel_states]);ts=np.asarray([x[1] for x in trials])
    predictor_ratios=np.asarray([x[2] for x in trials])
    Fc=1000*C.T@(A*sc);Fs=1000*B.T@(p.bar_area*ss)
    J=1000*((C.T*(A*tc))@C+(B.T*(p.bar_area*ts))@B)
    return Fc+Fs,J,cs,rows,sc,ss,Fc,Fs,es,steel_states,predictor_ratios

def advance(s,column,field,actions,*,time_s,tolerance_kN=1e-6,max_iterations=35,reuse_line_search=False):
    """Solve force control on locally positive tangent branch; atomic commit.

    q=[e0,kx,ky] normalized curvature; conjugate target [N,Mx/(h/2),My/(b/2)]
    in kN, making the algorithmic tangent symmetric. No member stability
    or load-capacity inference from loss of local positive definiteness.
    """
    t=float(time_s);minute=float(field["snapshot"]["time_minutes"])
    if not math.isfinite(t) or t<=s.time_s or minute<s.thermal_minutes:
        raise SectionHistoryError("time-ordered increments required")
    if abs((t-s.time_s)-60*(minute-s.thermal_minutes))>1e-8 and not (s.time_s==0. and minute==0.):
        raise SectionHistoryError("thermal snapshot and time increment mismatch")
    p,A,C,B,E,fy=_prepare(s,column,field)
    scale=np.array([1.,p.h_m/2,p.b_m/2])
    target=np.asarray(actions,dtype=float)/scale
    if target.shape!=(3,) or not np.all(np.isfinite(target)):raise SectionHistoryError("finite N/Mx/My required")
    q=np.asarray(s.q,dtype=float)
    counts={'section_trials':0,'concrete_trials':0,'reused_trials':0}
    cached=None
    def ev(q):
        counts['section_trials']+=1
        return _trial(s,p,A,C,B,E,fy,t,q,counts=counts)
    def residual(F):return float(np.max(np.abs(F-target)))
    for iteration in range(1,max_iterations+1):
        try:
            if cached is None:out=ev(q)
            else:
                out=cached;cached=None;counts['reused_trials']+=1
        except (ValueError,ArithmeticError) as exc:
            return s,{"status":"UNRESOLVED_MATERIAL_TRIAL","reason":str(exc)}
        F,J,cs,rows,sc,ss,Fc,Fs,es,steel_states,predictor_ratios=out
        err=residual(F)
        if err<=tolerance_kN:break
        try:dq=np.linalg.solve(J,target-F)
        except np.linalg.LinAlgError:return s,{"status":"UNRESOLVED_SINGULAR_SECTION"}
        if not np.all(np.isfinite(dq)):return s,{"status":"UNRESOLVED_NONFINITE_INCREMENT"}
        if np.max(np.abs(dq))>.004:dq*=.004/np.max(np.abs(dq))
        for i in range(14):
            candidate=q+dq*(.5**i)
            try:trial=ev(candidate)
            except (ValueError,ArithmeticError):continue
            if residual(trial[0])<err:
                q=candidate
                if reuse_line_search:cached=trial
                break
        else:return s,{"status":"UNRESOLVED_LINE_SEARCH","residual_kN":err}
    else:return s,{"status":"UNRESOLVED_ITERATION_LIMIT"}
    eig=np.linalg.eigvalsh(J)
    if eig[0]<=1e-9*max(1.,eig[-1]):
        return s,{"status":"UNRESOLVED_NONPOSITIVE_SECTION_TANGENT","eigenvalues_kN":eig.tolist()}
    yield_ratio=float(np.max(np.abs(ss)/fy))
    if not all(steel_history.admitted(a,s.steel_mode,float(f),diagnostic_strain_limit=s.steel_strain_limit) for a,f in zip(steel_states,fy)):
        return s,{"status":"UNRESOLVED_STEEL_YIELD_OR_RESEARCH_DOMAIN","steel_yield_ratio":yield_ratio}
    # Boundary samples carry independent histories but zero integration weight.
    probes=[];pr=[]
    try:
        for old,T,e in zip(s.probes,p.sp_boundary_temperature,_shape(p.sp_boundary_u,p.sp_boundary_v)@q):
            n,r=hot.trial_step(old,time_s=t,temperature_C=float(T),total_compression=float(e))
            probes.append(n);pr.append(r)
    except (ValueError,ArithmeticError) as exc:
        return s,{"status":"UNRESOLVED_BOUNDARY_HISTORY","reason":str(exc)}
    new=SectionState(s.geometry,s.grid,s.thermal_method,t,minute,tuple(q),
                     tuple(cs),tuple(probes),tuple(p.theta_s),steel_states,s.steel_mode,s.steel_strain_limit,s.quadrature)
    concrete_damage=np.array([a.active.damage for a in cs])
    inactive=np.array([a.thermal_cutoff for a in cs])
    D=J[1:,1:]-np.outer(J[1:,0],J[0,1:])/J[0,0]
    D=D*np.outer(scale[1:],scale[1:])
    # Frozen-state elastic unloading reference: only currently compressed concrete,
    # no history increments, full steel elastic unloading. Not a loading tangent.
    Eu=[]
    for a,r in zip(cs,rows):
        if a.thermal_cutoff or a.active.damage==1. or r["stress_MPa"]<=0.:Eu.append(0.)
        else:Eu.append((1-a.active.damage)*material._material(a.active.parameters,a.active.maximum_temperature_C)[0])
    Ju=1000*((C.T*(A*np.asarray(Eu)))@C+(B.T*(p.bar_area*E))@B)
    Du=(Ju[1:,1:]-np.outer(Ju[1:,0],Ju[0,1:])/Ju[0,0])*np.outer(scale[1:],scale[1:])
    return new,{"status":"EQUILIBRATED_RESEARCH_SECTION","time_minutes":minute,
        "q":q.tolist(),"actions_kN_kNm":(F*scale).tolist(),
        "concrete_actions_kN_kNm":(Fc*scale).tolist(),"steel_actions_kN_kNm":(Fs*scale).tolist(),
        "max_conjugate_residual_kN":err,"iterations":iteration,
        "trial_counts":dict(counts),
        "section_tangent_eigenvalues_kN":eig.tolist(),"condensed_D_kNm2":D.tolist(),
        "frozen_elastic_unloading_D_kNm2":Du.tolist(),"steel_mode":s.steel_mode,
        "steel_predictor_yield_ratio":float(np.max(predictor_ratios)),
        "steel_plastic_strains":[a.plastic_strain for a in steel_states],
        "steel_max_accumulated_plastic_strain":max(a.accumulated_plastic_strain for a in steel_states),
        "steel_yielded_bar_count":sum(a.accumulated_plastic_strain>0. for a in steel_states),
        "concrete_net_area_m2":float(A.sum()),"steel_area_m2":float(p.bar_area.sum()),
        "concrete_integration_points":len(A),
        "compressed_net_area_m2":float(A[sc>0.].sum()),
        "stress_inactive_noncutoff_area_m2":float(A[(sc<=0.)&(~inactive)].sum()),
        "area_weighted_damage":float(A@concrete_damage/A.sum()),
        "max_cell_damage":float(concrete_damage.max()),
        "max_boundary_damage":max(a.active.damage for a in probes),
        "crushed_net_area_m2":float(A[concrete_damage==1.].sum()),
        "thermal_inactive_net_area_m2":float(A[inactive].sum()),
        "max_cell_transient_strain":max(a.active.transient_compression for a in cs),
        "max_cell_plastic_strain":max(a.active.plastic_compression for a in cs),
        "steel_yield_ratio":yield_ratio,"steel_stress_MPa":ss.tolist(),
        "max_cell_temperature_C":float(np.max(p.theta_c)),
        "max_bar_temperature_C":float(np.max(p.theta_s)),
        "maximum_boundary_temperature_C":float(np.max(p.sp_boundary_temperature)),
        "steel_history_qualified":False,"boundary_continuum_qualified":False,
        "local_tangent_not_global_stability":True,"normative_claim":False,
        "actual_t_R_minutes":None}

def run_history(column,fields,actions,*,grid,mode,length_mm=50.,Gwork_N_mm=5.,
                yield_fraction=.4,strength_basis="SP5_ACCIDENTAL_FCD",
                steel_mode=steel_history.ELASTIC,steel_strain_limit=.02,quadrature=None,reuse_line_search=False):
    s=make_initial(column,fields[0],grid=grid,mode=mode,length_mm=length_mm,
                   Gwork_N_mm=Gwork_N_mm,yield_fraction=yield_fraction,strength_basis=strength_basis,
                   steel_mode=steel_mode,steel_strain_limit=steel_strain_limit,quadrature=quadrature)
    rows=[]
    for field in fields:
        minute=float(field["snapshot"]["time_minutes"])
        # Explicit ambient preload at 1 s with no conventional creep.
        try:new,r=advance(s,column,field,actions,time_s=1.+60*minute,reuse_line_search=reuse_line_search)
        except (ValueError,ArithmeticError,np.linalg.LinAlgError) as exc:
            new=s;r={"status":"UNRESOLVED_INPUT_OR_MATERIAL_DOMAIN","reason":str(exc)}
        rows.append({**r,"requested_time_minutes":minute})
        if r["status"]!="EQUILIBRATED_RESEARCH_SECTION":
            return {"status":"UNRESOLVED_HISTORY_STOP","rows":rows,"last_committed_minute":s.thermal_minutes,
                    "actual_t_R_minutes":None}
        s=new
    return {"status":"DIAGNOSTIC_COMPLETE","rows":rows,"last_committed_minute":s.thermal_minutes,
            "actual_t_R_minutes":None}

def campaign(column,boundary):
    c=copy.deepcopy(column);c["fire_minutes"]=10.
    times=[float(i) for i in range(11)]
    heat=solve_sp2026_2d_heat(c,boundary=boundary,cell_count_x=32,cell_count_y=32,
                             max_step_minutes=1.,sample_times_minutes=times)
    fields={"K":[build_annex_k_snapshot(c,t) for t in times],
            "FVM":[select_sp2026_snapshot(heat,t) for t in times]}
    runs=[]
    for route in fields:
      for mode in (hot.ZERO,hot.MODIFIED_AT):
        for actions in ((0.,0.,0.),(50.,1.,1.)):
            r=run_history(c,fields[route][::2],actions,grid=8,mode=mode)
            runs.append({"route":route,"mode":mode,"actions":actions,"grid":8,"step_min":2.,**r})
    for grid,step in ((8,1),(12,1)):
        r=run_history(c,fields["FVM"][::step],(50.,1.,1.),grid=grid,mode=hot.MODIFIED_AT)
        runs.append({"route":"FVM","mode":hot.MODIFIED_AT,"actions":(50.,1.,1.),"grid":grid,"step_min":float(step),**r})
    return {"version":VERSION,"runs":runs,"thermal_grid":32,
            "mesh_and_time_convergence_proven":False,"normative_claim":False,"actual_t_R_minutes":None}
