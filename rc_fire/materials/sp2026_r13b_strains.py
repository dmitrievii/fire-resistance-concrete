"""SP-R13B: bounded shape compatibility and independent strain screening.

SP2026 factors are authoritative for the stated research comparison.
No inferred ultimate strain is a normative value. No fitted hot curves.
"""
import math
import json
from pathlib import Path
from rc_fire.materials.normative import ConcreteMix,Reinforcement,normal_concrete,CONCRETE_K,CONCRETE_BETA,FIRE_TEMP
from rc_fire.materials.sp2026_full_nonlinear import full_concrete_sp_parameters
from rc_fire.materials import sp2026_r13a_normative as a
from rc_fire.mechanics import sp2026_nonisothermal_coupling as history
from rc_fire.verification import sp2026_r9b_material_data as exp

DATA=Path(__file__).resolve().parents[2]/"validation"/"sp_r13b_fracture_ratios.json"

def rational_domain(f,E,peak,ultimate):
    """E is the SP5 rational-law Ecm,n parameter, not arbitrary tangent.
    Eq6.13: sigma/f=eta*(k-eta)/(1+(k-2)*eta), k=1.1 E peak/f.
    For k>1, nonnegative, nonsingular branch up to eta_u iff eta_u<=k.
    This is mathematical admissibility, not a physical ultimate strain.
    """
    vals=(f,E,peak,ultimate)
    if not all(math.isfinite(x) and x>0 for x in vals) or ultimate<peak:
        raise ValueError("positive strengths, modulus and ordered strains required")
    k=1.1*E*peak/f;eta=ultimate/peak
    return {"k":k,"eta_u":eta,"initial_tangent_MPa":1.1*E,
            "formal_zero_stress_strain":k*peak if k>1 else None,
            "admissible":bool(k>1 and eta<=k and 1+(k-2)*eta>0),
            "minimum_peak_for_fixed_ultimate":math.sqrt(f*ultimate/(1.1*E)),
            "peak_ultimate_qualified":False}

def rational_stress(f,E,peak,ultimate,e):
    d=rational_domain(f,E,peak,ultimate)
    if not d["admissible"] or not math.isfinite(e) or not 0<=e<=ultimate:
        raise ValueError("outside admitted mathematical strain domain")
    x=e/peak;k=d["k"];den=1+(k-2)*x
    return f*x*(k-x)/den,(f/peak)*(1-x)*(k+(k-2)*x)/den**2

def concrete_audit(family):
    mix=ConcreteMix("C30/37",aggregate_family=family,independently_measured_Ecm_GPa=41.)
    n=normal_concrete(mix);rows=[]
    for T,kc,beta in zip(FIRE_TEMP,CONCRETE_K[family],CONCRETE_BETA[family]):
        p=full_concrete_sp_parameters(T,mix,n)
        f=p["fcm_theta_MPa"];E=p["Ecm_n_hot_MPa"]
        e1=p["epsilon_c1_assumed_temperature_invariant"];eu=p["epsilon_cu1_assumed_temperature_invariant"]
        fixed=rational_domain(f,E,e1,eu)
        scaled=rational_domain(f,E,e1*kc/beta,eu*kc/beta)
        section=a.section_concrete(mix,T,0.)
        # Distinguish characteristic section fck from mean rational fcm;
        # initial slope equality of section parabola is a hypothesis.
        em=n["n_parabola"]*section["strength_MPa"]/section["SP_beta_E_MPa"]
        kernels=[]
        for basis,fc in ((a.CHARACTERISTIC,30.),(a.ACCIDENTAL,25.)):
            for length in (25.,50.,100.):
                pars=history.Parameters(family,fc,41000.,e1,.4,5.,length,2.35,None,
                     "R13B audit of existing R10A synthetic history parameters")
                Eh,fh,fy,H,pp,soft=history._material(pars,T)
                peak=pp+fh/Eh;end=peak+soft
                z,d,sig,tangent,kind=history._return(Eh,fh,fy,H,pp,soft,peak,0.,0.)
                z2,d2,sig2,_,_=history._return(Eh,fh,fy,H,pp,soft,end,z,d)
                kernels.append({"basis":basis,"length_mm":length,"E_MPa":Eh,"fc_MPa":fh,
                    "peak_strain":peak,"synthetic_zero_stress_strain":end,
                    "computed_peak_stress_MPa":sig,"computed_end_stress_MPa":sig2,
                    "end_damage":d2,"Gwork_N_mm":5.,"measured_ultimate":False})
        rows.append({"T":T,"kc":kc,"beta":beta,"fixed":fixed,"constant_shape":scaled,
            "constant_shape_peak":e1*kc/beta,"constant_shape_ultimate":eu*kc/beta,
            "section_modulus_matched_peak_hypothesis":em,
            "section_ambient_ultimate":section["ambient_section_limit"],
            "section_modulus_match_fits_ambient_limit":em<=section["ambient_section_limit"],
            "history_kernel":kernels})
    return {"family":family,"rows":rows,"normative_claim":False}

def fracture_screen(data):
    if data["schema"]!="SP-R13B-fracture-ratios-v1" or data["quantity"]!="fracture_strain_ratio_to_ambient":
        raise ValueError("explicit fracture measurement contract required")
    if data["protocol"]!="hot_steady_state_tensile_fracture_postcool_mark_measurement":
        raise ValueError("do not mix hot fracture and residual tension")
    seen=set();rows=[];by_bar={}
    for v in data["records"]:
        key=(v["bar"],v["T"])
        if key in seen or not 20<v["T"]<=800 or not all(math.isfinite(v[k]) and v[k]>0 for k in ("ratio","allowance")):
            raise ValueError("invalid fracture observation")
        seen.add(key)
        row={**v,"constant_fracture_ratio":1.,
             "constant_outside_reading_allowance":abs(v["ratio"]-1.)>v["allowance"],
             "SP_epsilon_uk":None,"SP_epsilon_ud":None,"rupture_model_qualified":False}
        rows.append(row);by_bar.setdefault(v["bar"],[]).append(row)
    return {"rows":rows,"by_bar":{k:{"count":len(v),
         "constant_ratio_RMSE":math.sqrt(sum((r["ratio"]-1.)**2 for r in v)/len(v)),
         "outside_reading_allowance":sum(r["constant_outside_reading_allowance"] for r in v)}
         for k,v in by_bar.items()},
         "fracture_is_not_uniform_elongation":True,"grade_transfer_admitted":False}

def campaign():
    ref=exp.load_anchors()
    concrete=[exp.compare_concrete_series(s) for s in ref["concrete"]]
    steel=fracture_screen(json.loads(DATA.read_text()))
    return {"concrete_compatibility":[concrete_audit(f) for f in ("siliceous","calcareous")],
       "independent_concrete_peak_screen":concrete,"independent_steel_fracture_screen":steel,
       "fitted_parameters":0,"concrete_hot_ultimate_qualified":False,
       "steel_hot_uniform_elongation_qualified":False,"history_law_qualified":False,
       "member_experimental_qualified":False,"actual_t_R_minutes":None,"normative_claim":False}
