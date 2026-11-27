"""SP-R8E: thermal eigenstrain and self-equilibrated section stress audit.

SP 2.02.05-2026 §§8.2.16,18–20,22; SP5 §§6.1.5.4,8.1.2.
The existing source coefficients are not an independently validated hot
constitutive law. All alternatives below are labelled diagnostic; no
substitution of TKP strain limits, no irreversible damage or R certification.
"""
from __future__ import annotations
import copy
import math
import numpy as np
from rc_fire.materials.sp2026_fire import (
    concrete_free_thermal_strain_sp, concrete_at_sp_fire, steel_at_sp_fire)
from rc_fire.materials.normative import concrete_thermal_strain_coefficients
from rc_fire.thermal.sp2026_annex_k_field import build_annex_k_snapshot
from rc_fire.thermal.sp2026_heat import solve_sp2026_2d_heat, select_sp2026_snapshot
from rc_fire.mechanics.sp2026_nominal_member import prepare_sp2026_design_section
from rc_fire.mechanics.sp2026_coupled_first_limit import assess_coupled_sp5_nominal_at_time
from rc_fire.mechanics.action_capacity import UNKNOWN

VERSION="SP-R8E-eigenstrain-adjudication-v1"

def concrete_eigenstrain_components(T,family):
    """Separate signed expansion and shrinkage under differential interpretation.

    For monotonic heating only. A temperature-only shrinkage state is not a
    valid irreversible cooling/reheating history. Above 800 C inactive concrete
    is explicitly not assigned a constitutive strain.
    """
    T=float(T)
    expansion=concrete_free_thermal_strain_sp(T,family,signed_shrinkage=False)
    total=concrete_free_thermal_strain_sp(T,family,signed_shrinkage=True)
    if total is None:
        return None
    coeff=concrete_thermal_strain_coefficients(family,T)
    return {"expansion_integral":float(expansion),
            "signed_shrinkage_integral":float(total-expansion),
            "total_integral":float(total),
            "secant_coefficient_alternative":float(
                (coeff["alpha_bt_per_C"]+coeff["alpha_cs_per_C"])*(T-20.)),
            "source":"SP 8.2.19 Tables11/12; integration vs endpoint interpretation",
            "source_interpretation_qualified":False}

def elastic_compatibility_projection(shape,area,modulus,expansion):
    """Independent elastic compatibility projection, compression-positive.

    For positive physical quadrature weights only. shape rows are [1,v,u].
    Find q so shape.T @ (A E (shape q + expansion)) = 0.
    This is a linear reference problem, not the nonlinear SP stress law.
    """
    B=np.asarray(shape,dtype=float); A=np.asarray(area,dtype=float)
    E=np.asarray(modulus,dtype=float); e=np.asarray(expansion,dtype=float)
    if (B.ndim!=2 or B.shape[1]!=3 or
        any(x.shape!=(len(B),) for x in (A,E,e)) or
        not all(np.all(np.isfinite(x)) for x in (B,A,E,e)) or
        np.any(A<=0) or np.any(E<0)):
        raise ValueError("valid physical elastic quadrature required")
    w=A*E
    q=np.linalg.solve(B.T@(w[:,None]*B),-B.T@(w*e))
    incompatible=B@q+e
    stress=E*incompatible
    return {"generalized_strain":q,"mechanical_strain":incompatible,
            "stress":stress,"generalized_resultant":B.T@(A*stress),
            "weighted_strain_energy":float(.5*np.dot(w,incompatible**2))}

def _variant(prepared,mode):
    p=copy.deepcopy(prepared)
    if mode=="SP_SIGNED_INTEGRAL":
        return p
    if mode=="NO_EIGENSTRAIN_CONTROL":
        for key in ("eps_th_c","eps_th_cb","eps_th_s","sp_boundary_free_strain"):
            setattr(p,key,np.zeros_like(getattr(p,key)))
        return p
    if mode not in ("EXPANSION_ONLY_CONTROL","ENDPOINT_COEFFICIENT_SENSITIVITY"):
        raise ValueError("unrecognized diagnostic mode")
    key="expansion_integral" if mode=="EXPANSION_ONLY_CONTROL" else "secant_coefficient_alternative"
    def values(ts):
        a=[]
        for t in ts:
            data=concrete_eigenstrain_components(t,p.aggregate)
            a.append(0. if data is None else data[key])
        return np.asarray(a,dtype=float)
    p.eps_th_c=values(p.theta_c);p.eps_th_cb=values(p.theta_cb)
    p.sp_boundary_free_strain=values(p.sp_boundary_temperature)
    # Steel Eq.6 integral is unchanged in these concrete-only comparisons.
    return p

def _resultants(prepared,q,meta):
    """Reconstruct component forces from actual nonlinear stress map.

    MPa × m² × 1000 = kN. Concrete gross minus displaced concrete plus
    steel; distinguish resultant balance from local stresses.
    """
    p=prepared
    c=np.asarray(meta["map"]["concrete_stress_MPa"])
    s=np.asarray(meta["map"]["steel_stress_MPa"])
    ec=q[0]+q[1]*p.bar_v+q[2]*p.bar_u+p.eps_th_cb
    cb=np.asarray([p.sp_concrete_stress_fn(float(e),float(t),
                      p.sp_concrete,p.sp_concrete_normal)[0]
                   for e,t in zip(ec,p.theta_cb)])
    Bc=np.stack((np.ones(len(c)),p.y-p.h_m/2,p.x-p.b_m/2))
    Bs=np.stack((np.ones(len(s)),p.bar_y-p.h_m/2,p.bar_x-p.b_m/2))
    Fc=Bc@(1000*p.area*c); Fb=Bs@(1000*p.bar_area*cb)
    Fs=Bs@(1000*p.bar_area*s)
    return {"gross_concrete_N_Mx_My":Fc.tolist(),
            "displaced_concrete_N_Mx_My":Fb.tolist(),
            "steel_N_Mx_My":Fs.tolist(),
            "net_N_Mx_My":(Fc-Fb+Fs).tolist(),
            "concrete_stress_range_MPa":[float(c.min()),float(c.max())],
            "steel_stress_range_MPa":[float(s.min()),float(s.max())]}

def _governing(p,q):
    """Separate local stress-law strain checks and governing coordinate.

    Same inventory as SP-R7: integration centres, displaced bar-centre
    concrete check, eight boundary probes and actual steel tension.
    No proof of a continuous max or active material damage history.
    """
    candidates=[]
    for label,u,v,temps,thermal in (
        ("concrete_fibre",p.u,p.v,p.theta_c,p.eps_th_c),
        ("displaced_concrete_probe",p.bar_u,p.bar_v,p.theta_cb,p.eps_th_cb),
        ("concrete_boundary",p.sp_boundary_u,p.sp_boundary_v,
         p.sp_boundary_temperature,p.sp_boundary_free_strain)):
        for uu,vv,T,e in zip(u,v,temps,thermal):
            mech=float(q[0]+q[1]*vv+q[2]*uu+e)
            stress,_,lim,_=p.sp_concrete_stress_fn(mech,float(T),p.sp_concrete,
                                                  p.sp_concrete_normal)
            if lim is None:continue
            candidates.append({"kind":label,"x_mm":float((uu+1)*p.b_m*500),
                "y_mm":float((vv+1)*p.h_m*500),"temperature_C":float(T),
                "compatible_compression_strain":float(mech-e),
                "free_expansion_positive":float(e),"mechanical_compression_strain":mech,
                "stress_MPa":float(stress),"ambient_check_limit":float(lim),
                "ratio":float(max(0.,mech)/lim),
                "stress_plateau_extended_beyond_check_limit":bool(mech>lim)})
    for i,barid in enumerate(p.bar_ids):
        mech=float(q[0]+q[1]*p.bar_v[i]+q[2]*p.bar_u[i]+p.eps_th_s[i])
        stress,_,_=p.sp_steel_stress_fn(mech,float(p.theta_s[i]),p.sp_steel,p.sp_steel_normal)
        candidates.append({"kind":"steel_tension","bar_id":barid,
            "temperature_C":float(p.theta_s[i]),"mechanical_compression_strain":mech,
            "stress_MPa":float(stress),"ambient_check_limit":.010,
            "ratio":max(0.,-mech)/.010})
    return max(candidates,key=lambda x:x["ratio"])

def _equilibrium(p,target):
    r=p.solve_actions(*target)
    q=r.get("unknowns")
    if q is None:
        return {"classification":UNKNOWN,"reason":r.get("reason"),
                "target_N_Mx_My":list(target)}
    q=np.asarray(q,dtype=float)
    F,J,meta=p.force_and_tangent(q,include_maps=True)
    components=_resultants(p,q,meta)
    governing=_governing(p,q)
    return {"classification":r["classification"],"target_N_Mx_My":list(target),
            "generalized_strain":q.tolist(),"resultant_N_Mx_My":F.tolist(),
            "relative_residual":r.get("relative_residual"),
            "component_resultants":components,
            "component_reconstruction_max_error":float(
                np.max(np.abs(F-np.asarray(components["net_N_Mx_My"])))),
            "critical_ratio":float(meta["critical_mechanical_strain_ratio"]),
            "governing":governing,
            "governing_ratio_reconstruction_error":abs(
                governing["ratio"]-meta["critical_mechanical_strain_ratio"]),
            "hot_ultimate_strain_qualified":False,"normative_claim":False}

def audit_eigenstrain_section(column,field,member_spec,*,grid=24,effective_creep_phi):
    """Fixed thermal field and fixed mechanical actions across controls.

    Zero applied N/M case is a free section (no externally imposed axial
    restraint or moment). It can still develop incompatible thermal stress.
    No-eigenstrain and expansion-only runs are counterfactuals, not accepted
    fire calculation modes. Nonlinear stress fields are not superposable.
    """
    p=prepare_sp2026_design_section(column,field,grid=grid)
    m=assess_coupled_sp5_nominal_at_time(column,field,member_spec,grid=grid,
                                       effective_creep_phi=effective_creep_phi)
    M=m["second_order_coupled_M2_kNm"]
    target=None if M is None else [float(m["N_kN"]),*M]
    results={}
    for mode in ("SP_SIGNED_INTEGRAL","NO_EIGENSTRAIN_CONTROL",
                 "EXPANSION_ONLY_CONTROL","ENDPOINT_COEFFICIENT_SENSITIVITY"):
        v=_variant(p,mode)
        results[mode]={"free_section":_equilibrium(v,[0.,0.,0.]),
                       "loaded_section":_equilibrium(v,target) if target is not None else None}
    # Independent modulus/strain consistency audit. SP5 design parabola's
    # initial slope is n*fcd(T)/eps_c2, not automatically beta*Ecm.
    normal=p.sp_concrete_normal;params=p.sp5_design_parameters
    tangent=[]
    for t in (20.,300.,500.,600.,700.,800.):
        material=concrete_at_sp_fire(p.sp_concrete,t,normal)
        ep=float(normal["eps_c2_permille"])/1000.
        n=float(normal["n_parabola"])
        slope=n*params["fcd_20_MPa"]*material.strength_factor/ep
        tangent.append({"temperature_C":t,"SP5_design_parabola_initial_MPa":slope,
                        "SP_Table9_beta_Ecm_MPa":material.elastic_modulus_MPa,
                        "same_quantity":False})
    return {"version":VERSION,"time_minutes":field["snapshot"]["time_minutes"],
            "thermal_method":field["thermal_method"],"grid":grid,
            "fixed_loaded_actions":target,"variants":results,
            "tangent_audit":tangent,"nonlinear_superposition_used":False,
            "irreversible_thermal_history_qualified":False,
            "local_limit_is_global_failure":False,"actual_t_R_minutes":None,
            "normative_claim":False}

def run_eigenstrain_campaign(column,member_spec,*,boundary,times_minutes=(5.,10.,30.,45.),
                             heat_grid=64,step_minutes=1.,grid=24,effective_creep_phi):
    c=copy.deepcopy(column);ts=[float(t) for t in times_minutes]
    if not ts or not all(math.isfinite(t) for t in ts) or not 0<ts[0] or any(
        b<=a for a,b in zip(ts,ts[1:])):
        raise ValueError("positive increasing diagnostic times required")
    c["fire_minutes"]=ts[-1]
    h=solve_sp2026_2d_heat(c,boundary=boundary,cell_count_x=heat_grid,
            cell_count_y=heat_grid,max_step_minutes=step_minutes,sample_times_minutes=ts)
    rows=[]
    for t in ts:
        for route in ("K","FVM"):
            try:
                f=build_annex_k_snapshot(c,t) if route=="K" else select_sp2026_snapshot(h,t)
                result=audit_eigenstrain_section(c,f,member_spec,grid=grid,
                                                effective_creep_phi=effective_creep_phi)
            except (ValueError,ArithmeticError,np.linalg.LinAlgError) as exc:
                result={"status":"UNRESOLVED","reason":str(exc)}
            rows.append({"route":route,"time_minutes":t,"evidence":result})
    return {"rows":rows,"FVM_energy_balance":h["energy_balance"],
            "actual_t_R_minutes":None,"normative_claim":False}
