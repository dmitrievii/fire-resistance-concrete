"""SP-R9A: strict-domain material envelopes and independent SP/TKP comparison.

SP 2.02.05-2026 §§8.2.16,18–20; SP5 §§6.1.2.11,6.1.5.2–4,
8.1.2.1; TKP EN1992-1-2 §§3.2.2.1,3.2.3, Fig3.1/3.3.
Peak/ultimate strain scaling is a hypothesis, not a normative source.
No constitutive history, global stability, regulatory R or production switch.
"""
from __future__ import annotations
import math
import numpy as np
from rc_fire.materials.sp2026_fire import concrete_at_sp_fire, steel_at_sp_fire
from rc_fire.materials.sp2026_full_nonlinear import full_concrete_sp_parameters
from rc_fire.materials import tkp_en1992_fire as tkp
from rc_fire.mechanics.sp2026_nominal_member import design_parameters

VERSION="SP-R9A-strict-constitutive-envelope-v1"
PARABOLA="SP5_SECTION_FIXED_STRAIN"
RATIONAL="SP5_FULL_FIXED_STRAIN"
SCALED="SP5_FULL_CONSTANT_K_HYPOTHESIS"
TKP="TKP_INDEPENDENT"

def concrete_envelope_parameters(concrete,normal,normal_steel,T,mode):
    """Strength basis and strain basis remain explicit for every curve."""
    T=float(T)
    if not math.isfinite(T) or T<20:raise ValueError("invalid temperature")
    fck=float(normal["f_ck_MPa"])
    if mode==TKP:
        if fck>50:
            raise ValueError("R9A ordinary concrete comparison limited to fck<=50 MPa")
        p=tkp.concrete_parameters(T,aggregate=concrete.aggregate_family)
        return {"mode":mode,"temperature_C":T,"strength_MPa":fck*p.k_c/tkp.GAMMA_M_FI,
                "strength_basis":"TKP_fck_gamma_M_fi","peak_strain":p.eps_c1,
                "ultimate_strain":p.eps_cu1,
                "initial_tangent_MPa":1.5*fck*p.k_c/p.eps_c1/tkp.GAMMA_M_FI if p.eps_c1 else None,
                "defined":p.full_stress_strain_defined,"inactive":T==1200.,
                "hot_strain_source":"TKP Table3.1 (independent only)",
                "normative_claim":False}
    if mode not in (PARABOLA,RATIONAL,SCALED):
        raise ValueError("unknown SP envelope")
    m=concrete_at_sp_fire(concrete,T,normal)
    d=design_parameters(normal,normal_steel)
    base={"mode":mode,"temperature_C":T,"SP_kc":m.strength_factor,
          "SP_beta":m.modulus_factor,"SP_reduced_Ecm_MPa":m.elastic_modulus_MPa,
          "SP_characteristic_strength_MPa":fck*m.strength_factor,
          "SP5_accidental_design_strength_MPa":d["fcd_20_MPa"]*m.strength_factor,
          "normative_claim":False,"hot_strain_source_qualified":False}
    if T>800:
        return {**base,"inactive":True,"defined":True,"strength_MPa":0.,
                "initial_tangent_MPa":0.,"peak_strain":None,"ultimate_strain":None,
                "strength_basis":"USER_ZERO_CONCRETE_ABOVE_800"}
    if mode==PARABOLA:
        e1=float(normal["eps_c2_permille"])/1000.
        eu=float(normal["eps_cu2_permille"])/1000.
        n=float(normal["n_parabola"])
        f=base["SP5_accidental_design_strength_MPa"]
        return {**base,"strength_MPa":f,"strength_basis":"SP5_fcd_times_SP_kc",
                "peak_strain":e1,"ultimate_strain":eu,"exponent":n,
                "initial_tangent_MPa":n*f/e1,"defined":0<e1<=eu,
                "inactive":False,"hot_strain_source":"ambient SP5 Table6.1 held fixed"}
    p=full_concrete_sp_parameters(T,concrete,normal)
    e1=p["epsilon_c1_assumed_temperature_invariant"]
    eu=p["epsilon_cu1_assumed_temperature_invariant"]
    if mode==SCALED:
        # Keep the dimensionless ambient curve shape k, rescale both strain
        # coordinates by strength/modulus ratio. This matches the reduced
        # source nonlinear tangent algebraically, but does NOT prove hot ductility.
        scale=m.strength_factor/m.modulus_factor
        e1*=scale;eu*=scale
    else:scale=1.
    f=p["fcm_theta_MPa"]
    E=1.1*p["Ecm_n_hot_MPa"]
    k=E*e1/f
    # Rational envelope must have positive denominator and nonnegative
    # stress through its declared ultimate point, not just at the peak.
    z=eu/e1
    admissible=(0<e1<=eu and k>1. and 1+(k-2.)*z>0 and z<=k)
    return {**base,"strength_MPa":f,"strength_basis":"SP5_fcm_times_SP_kc",
            "peak_strain":e1,"ultimate_strain":eu,"shape_k":k,
            "initial_tangent_MPa":E,"SP5_nonlinear_modulus_MPa":p["Ecm_n_hot_MPa"],
            "strain_scale":scale,"defined":bool(admissible),"inactive":False,
            "hot_strain_source":("SP-only kc/beta shape-preservation hypothesis"
                                 if mode==SCALED else "ambient SP5 full strains held fixed")}

def evaluate_concrete_envelope(p, strain):
    """Never extrapolate an SP stress plateau or rational curve past its domain.

    TKP zero stress at/beyond eps_cu1 belongs to that independent envelope.
    Out-of-domain SP state is unresolved, not zero stress or global failure.
    """
    e=float(strain)
    if not math.isfinite(e):raise ValueError("finite strain required")
    if p["inactive"]:
        return {"status":"INACTIVE_CONCRETE","stress_MPa":0.,"tangent_MPa":0.}
    if not p["defined"]:
        return {"status":"UNRESOLVED_ENVELOPE","stress_MPa":None,"tangent_MPa":None}
    e1,eu,f=p["peak_strain"],p["ultimate_strain"],p["strength_MPa"]
    if e<=0:
        return {"status":"TENSION_IGNORED","stress_MPa":0.,"tangent_MPa":0.}
    if e>eu and p["mode"]!=TKP:
        return {"status":"OUTSIDE_SP_STRAIN_DOMAIN","stress_MPa":None,"tangent_MPa":None}
    x=e/e1
    if p["mode"]==PARABOLA:
        n=p["exponent"]
        s,d=(f,0.) if e>=e1 else (f*(1-(1-x)**n),f*n/e1*(1-x)**(n-1))
    elif p["mode"]==TKP:
        if e>=eu:s,d=0.,0.
        elif e<=e1:s,d=3*f*x/(2+x**3),3*f/e1*(2-2*x**3)/(2+x**3)**2
        else:s,d=f*(eu-e)/(eu-e1),-f/(eu-e1)
    else:
        k=p["shape_k"];a=1+(k-2)*x
        if a<=0:return {"status":"SINGULAR_RATIONAL_CURVE","stress_MPa":None,"tangent_MPa":None}
        s=f*(k*x-x*x)/a
        d=f/e1*(k-2*x-(k-2)*x*x)/a**2
    return {"status":"EVALUATED","stress_MPa":float(s),"tangent_MPa":float(d)}

def compare_materials(concrete,normal,steel,normal_steel,*,temperatures_C=(20.,100.,200.,300.,400.,500.,600.,700.,800.),
                      production_route,ductility_class):
    rows=[]
    for T in temperatures_C:
        ps=[concrete_envelope_parameters(concrete,normal,normal_steel,T,m)
            for m in (PARABOLA,RATIONAL,SCALED,TKP)]
        sm=steel_at_sp_fire(steel,T,normal_steel)
        sp5=design_parameters(normal,normal_steel)
        st=tkp.reinforcement_parameters(T,fyk_MPa=normal_steel["f_yk_MPa"],
               Es_MPa=1000*normal_steel["E_s_GPa"],production_route=production_route,
               ductility_class=ductility_class)
        rows.append({"temperature_C":T,"concrete":ps,
              "steel":{"SP_strength_MPa":sp5["fyd_20_MPa"]*sm.strength_factor,
                       "SP_E_MPa":sm.elastic_modulus_MPa,
                       "SP_section_tension_limit":.010,
                       "SP_hot_full_ductility_qualified":False,
                       "TKP_strength_MPa":st.f_sy_MPa,"TKP_E_MPa":st.E_s_MPa,
                       "TKP_eps_sy":st.eps_sy,"TKP_eps_su":st.eps_su,
                       "TKP_production_route":production_route,"TKP_ductility_class":ductility_class}})
    return {"version":VERSION,"rows":rows,"normative_claim":False,
            "independent_TKP_material_comparison":True,
            "reference_strength_SP_fck_vs_fcd_unadjudicated":True}

def replay_section_strain(prepared,unknowns):
    """Same compatible strains and SP thermal eigenstrains, alternative local laws.

    This is a material-only replay, not an equilibrated alternative section,
    not a full TKP structural calculation. No alternative result may replace
    the existing solver. Report unsupported fibre count and area, not only max.
    """
    p=prepared;q=np.asarray(unknowns,dtype=float)
    if q.shape!=(3,) or not np.all(np.isfinite(q)):raise ValueError("finite section root required")
    result={}
    for mode in (PARABOLA,RATIONAL,SCALED,TKP):
        records=[]
        cache={}
        for u,v,T,eth,A in zip(p.u,p.v,p.theta_c,p.eps_th_c,p.area):
            T=float(T)
            if T not in cache:
                cache[T]=concrete_envelope_parameters(p.sp_concrete,p.sp_concrete_normal,
                    p.sp_steel_normal,T,mode)
            pp=cache[T];e=float(q[0]+q[1]*v+q[2]*u+eth)
            ev=evaluate_concrete_envelope(pp,e)
            records.append((float(A),ev["stress_MPa"],ev["status"]))
        bad=[r for r in records if r[1] is None]
        result[mode]={"fibre_count":len(records),"unresolved_fibres":len(bad),
                      "unresolved_area_m2":sum(r[0] for r in bad),
                      "gross_concrete_force_kN_if_resolved":None if bad else
                          sum(1000*r[0]*r[1] for r in records),
                      "equilibrium_recomputed":False}
    return {"replay":result,"normative_claim":False,"actual_t_R_minutes":None}
