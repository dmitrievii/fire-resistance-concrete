"""SP-R13A source-bounded constitutive audit, not a production solver.

Separate section resistance and nonlinear member material laws. The
ambient SP5 strain coordinates retained at hot T are an explicit
diagnostic assumption, not validated hot ultimate deformation data.
"""
import math
from rc_fire.materials.normative import normal_concrete,normal_reinforcement,concrete_at_temperature
from rc_fire.materials.sp2026_fire import concrete_at_sp_fire,steel_at_sp_fire
from rc_fire.materials.sp2026_full_nonlinear import full_concrete_sp_parameters
from rc_fire.mechanics.sp2026_nominal_member import design_parameters

CHARACTERISTIC="SP_CHARACTERISTIC_FCK"
ACCIDENTAL="SP5_ACCIDENTAL_FCD"

def section_concrete(mix,T,strain,*,basis=CHARACTERISTIC):
    """Eq6.17/18 restricted to its declared section strain domain.
    No silently extended plateau. Beyond-domain stress remains unknown.
    """
    T=float(T);e=float(strain)
    if not math.isfinite(T) or not math.isfinite(e) or T<20:raise ValueError("invalid input")
    if basis not in (CHARACTERISTIC,ACCIDENTAL):raise ValueError("explicit strength basis required")
    n=normal_concrete(mix)
    if T>800:
        return {"status":"USER_ZERO_CONCRETE_ABOVE_800","stress_MPa":0.,"tangent_MPa":0.,
                "hot_strain_qualified":False,"normative_claim":False}
    data=concrete_at_temperature(mix,T,n)
    f0=n["f_ck_MPa"]
    if basis==ACCIDENTAL:f0*=min(1.,(40./f0)**(1./3.))/1.2
    f=f0*data["k_c"];e2=n["eps_c2_permille"]/1000.;eu=n["eps_cu2_permille"]/1000.;ex=n["n_parabola"]
    E=data["E_cm_theta_GPa"]
    result={"basis":basis,"temperature_C":T,"strength_MPa":f,"peak_strain":e2,
          "ambient_section_limit":eu,"SP_beta_E_MPa":None if E is None else E*1000.,
          "parabola_initial_tangent_MPa":ex*f/e2,
          "hot_strain_qualified":T==20.,"normative_claim":False}
    if e>eu:return {**result,"status":"OUTSIDE_ASSUMED_SECTION_STRAIN_DOMAIN","stress_MPa":None,"tangent_MPa":None}
    if e<=0:s,d=0.,0.
    elif e>=e2:s,d=f,0.
    else:s,d=f*(1-(1-e/e2)**ex),ex*f/e2*(1-e/e2)**(ex-1)
    return {**result,"status":"AT_ASSUMED_SECTION_LIMIT" if e==eu else "EVALUATED_SECTION_DIAGNOSTIC",
            "stress_MPa":s,"tangent_MPa":d}

def steel_section(rebar,T,strain):
    """Horizontal bilinear stress envelope and separate section tension check.
    Positive compression. 10 permille is not a hot member rupture criterion.
    """
    e=float(strain)
    if not math.isfinite(e):raise ValueError("finite strain required")
    mat=steel_at_sp_fire(rebar,T)
    sig=max(-mat.strength_MPa,min(mat.strength_MPa,e*mat.elastic_modulus_MPa))
    return {"stress_MPa":sig,"tangent_MPa":mat.elastic_modulus_MPa if abs(e)*mat.elastic_modulus_MPa<mat.strength_MPa else 0.,
            "yield_strain":mat.strength_MPa/mat.elastic_modulus_MPa,
            "section_tension_limit":.010,"section_tension_limit_exceeded":e<-.010,
            "horizontal_envelope_has_intrinsic_strain_cap":False,
            "member_hot_rupture_strain":None,"normative_claim":False}

def audit(mix,rebar,temperatures=(20,100,200,300,400,500,600,700,800)):
    """Reconcile literal strengths, beta modulus and existing fixed-strain
    rational law; no fitting and no new high-temperature strain rule."""
    n=normal_concrete(mix);s=normal_reinforcement(rebar);rows=[]
    for T in temperatures:
        a=section_concrete(mix,T,0.,basis=CHARACTERISTIC)
        b=section_concrete(mix,T,0.,basis=ACCIDENTAL)
        st=steel_section(rebar,T,0.)
        full=full_concrete_sp_parameters(T,mix,n)
        k=full["shape_parameter_k"];eu=full["epsilon_cu1_assumed_temperature_invariant"]
        e1=full["epsilon_c1_assumed_temperature_invariant"];z=eu/e1
        E=a["SP_beta_E_MPa"]
        rows.append({"T":T,"fc_characteristic_MPa":a["strength_MPa"],
           "fc_accidental_MPa":b["strength_MPa"],"beta_E_MPa":E,
           "literal_parabola_tangent_MPa":a["parabola_initial_tangent_MPa"],
           "accidental_parabola_tangent_MPa":b["parabola_initial_tangent_MPa"],
           "parabola_to_beta_E_ratio":a["parabola_initial_tangent_MPa"]/E,
           "modulus_matched_peak_strain_hypothesis":n["n_parabola"]*a["strength_MPa"]/E,
           "ambient_section_peak_strain":a["peak_strain"],
           "ambient_section_limit":a["ambient_section_limit"],
           "fixed_full_shape_k":k,
           "fixed_full_curve_admissible":bool(k>1 and 1+(k-2)*z>0 and z<=k),
           "steel_yield_MPa":steel_at_sp_fire(rebar,T).strength_MPa,
           "steel_yield_strain":st["yield_strain"]})
    return {"rows":rows,"hot_peak_ultimate_strains_qualified":False,
            "irreversible_history_law_qualified":False,"steel_above_800_qualified":False,
            "global_failure_qualified":False,"actual_t_R_minutes":None,"normative_claim":False}
