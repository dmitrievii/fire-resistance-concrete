"""MC-R1: source replay and independent current-SP engineering candidate.

Historical Mathcad reduced-section method remains frozen for reproduction.
The engineering candidate does NOT use its 500C isotherm, fixed R90
temperature values, pseudo-bars, or separate uniaxial strength checks.
SP5 nominal stiffness on nonuniform fire is an explicit numerical extension.
No certification, physical first failure, or normative utilization.
"""
import math
from rc_fire.mechanics.sp2026_section import prepare_sp2026_section
from rc_fire.mechanics.sp2026_nominal_member import (
    prepare_sp2026_design_section,nonuniform_sp5_nominal_axis,design_parameters)
from rc_fire.mechanics.action_capacity import WITHIN,EXCEEDED
from rc_fire.thermal.sp2026_heat import select_sp2026_snapshot
from rc_fire.materials.sp2026_r13a_normative import CHARACTERISTIC,ACCIDENTAL

SOURCE_MAP=(
 ("3.2.4–3.2.12","Annex K.4–K.11 / SP §8.2.23","SP_FVM_REAL_BARS","source thermal qualification open"),
 ("3.2.14–3.2.22","SP §8.2.21","NOT_SELECTED_ISOTHERM","historical replay only"),
 ("3.3.1–3.3.2","SP5 §8.1.4.9 / §8.1.2","BIAXIAL_FIBRE_EQUILIBRIUM","not identical to large-eccentricity rectangular block"),
 ("3.3.3–3.3.4","SP §8.2.18 tables 9/10","EXPLICIT_STRENGTH_BASIS","characteristic versus accidental retained"),
 ("3.3.5–3.3.6","SP5 §8.1.3.5 / §8.1.2.1","SECTION_STRAIN_CHECK","ambient hot strain limit assumption open"),
 ("3.3.7–3.3.10","SP5 §8.1.6","NOMINAL_B_PER_AXIS","nonuniform homogenization open"),
 ("3.3.11–3.3.13","SP5 §8.1.1.5 / §8.1.6","SIGNED_AMPLIFIED_CENTROID_MOMENTS","first-order inputs including imperfections required"),
 ("3.4","SP Annex L","SEPARATE_SPALLING_GATE","no physical protection claim"),
)

def replay():
    from multicolumn_r05.calculation_engine import Inputs,Geometry,Fire,Material,Mechanics,Variant,compute
    x=compute(Inputs(Geometry(),Fire(),Material(),Mechanics(),(
        Variant("v1",496.7,3.83,0.,20.),Variant("v2",527.16,6.5,0.,25.))))
    v=x["variants"]["v2"]["axes"]
    return {"source":"XMCD saved regions 625 and 2909; no live Mathcad execution",
        "v2":{a:{k:v[a][k] for k in ("M_Rd_kNm","M_Ed_kNm","utilization","N_cr_kN")} for a in ("x","y")},
        "historical_only":True,"normative_claim":False}

def finite(x,name,positive=False):
    if isinstance(x,bool):raise ValueError(name)
    x=float(x)
    if not math.isfinite(x) or (positive and x<=0):raise ValueError(name)
    return x

def assess(column,snapshot,*,basis,creep_by_axis,action_contract,grid=12):
    """Fixed-duration engineering candidate for explicit effective lengths.

    Each supplied section N/Mx/My is a simultaneous first-order fire action
    vector. Caller confirms minimum eccentricity, imperfections, uniform
    longitudinal heating and that the supplied sections/load envelope cover
    critical locations. No extra load factor or automatic second eccentricity.
    Scalar nominal magnification only for numerically decoupled hot stiffness.
    No alternative branch or physical failure proof.
    """
    required=("first_order_fire_actions","imperfections_and_minimum_eccentricity_reconciled",
              "effective_lengths_and_critical_sections_confirmed","uniform_longitudinal_heating_confirmed")
    if not all(action_contract.get(k) is True for k in required):
        raise ValueError("explicit first-order action and member idealization contract required")
    if basis not in (CHARACTERISTIC,ACCIDENTAL):raise ValueError("explicit strength basis")
    if snapshot.get("thermal_method")!="SP2026_8.2.23_FVM":raise ValueError("current-SP FVM snapshot required")
    L=finite(column["length_m"],"length",True)
    mu={a:finite(column["mu_"+a],"effective length factor",True) for a in ("x","y")}
    phi={a:finite(creep_by_axis[a],"explicit axis creep") for a in ("x","y")}
    if min(phi.values())<0:raise ValueError("negative creep")
    secs=column.get("sections") or []
    ids=[str(s["id"]) for s in secs]
    if not ids or len(ids)!=len(set(ids)):raise ValueError("unique actual sections required")
    p=(prepare_sp2026_section(column,snapshot,grid=grid) if basis==CHARACTERISTIC
       else prepare_sp2026_design_section(column,snapshot,grid=grid))
    params=design_parameters(p.sp_concrete_normal,p.sp_steel_normal)
    if basis==CHARACTERISTIC:
        params={**params,"fcd_20_MPa":params["f_ck_MPa"],"fyd_20_MPa":params["f_yk_MPa"],
                "source":"SP2026 §8.2.18 literal strengths; SP5 Ecd convention separately retained"}
    p.sp5_design_parameters=params
    # Reject overlapping bar discs even if each bar is within section.
    bars=column["bars"]
    for i,a in enumerate(bars):
        for z in bars[i+1:]:
            if math.hypot(float(a["x_mm"])-float(z["x_mm"]),float(a["y_mm"])-float(z["y_mm"])) < (
                 float(a["diameter_mm"])+float(z["diameter_mm"]))/2.:
                raise ValueError("overlapping bar geometry")
    rows=[]
    for s in secs:
        N=finite(s["N_kN"],"compressive N",True)
        M={a:finite(s["M"+a+"_kNm"],"first-order M"+a) for a in ("x","y")}
        z=finite(s["z_m"],"section position")
        if not 0<=z<=L:raise ValueError("section outside member")
        axes={}
        for a in ("x","y"):
            v=nonuniform_sp5_nominal_axis(p,N_kN=N,length_m=L,mu_x=mu["x"],mu_y=mu["y"],effective_creep_phi=phi[a])
            axes[a]={**v.get(a,{"status":v["status"] if "status" in v else "UNRESOLVED_NOMINAL"}),
                     "phi_eff_input":phi[a],"mu_input":mu[a]}
        row={"id":str(s["id"]),"z_m":z,"N_kN":N,"M0_kNm":M,"nominal":axes,
             "M2_kNm":None,"section":None}
        if any(axes[a].get("eta_a") is None for a in axes):
            row["status"]="UNRESOLVED_NOMINAL_AMPLIFICATION"
        else:
            M2={a:M[a]*axes[a]["eta_a"] for a in M}
            root=p.solve_actions(N,M2["x"],M2["y"])
            row.update({"M2_kNm":M2,"section":root,
                "status":("SECTION_MODEL_WITHIN" if root["classification"]==WITHIN else
                          "SECTION_MODEL_LIMIT_EXCEEDED" if root["classification"]==EXCEEDED else
                          "UNRESOLVED_SECTION")})
        rows.append(row)
    # A sampled strain index is NOT a utilization of whole-member resistance.
    valid=[r for r in rows if r["section"] is not None and r["section"].get("critical_ratio") is not None]
    governing=max(valid,key=lambda r:r["section"]["critical_ratio"])["id"] if valid else None
    status=("UNRESOLVED" if any(r["status"].startswith("UNRESOLVED") for r in rows) else
            "MODEL_LIMIT_EXCEEDED" if any(r["status"]=="SECTION_MODEL_LIMIT_EXCEEDED" for r in rows) else
            "ALL_SAMPLED_SECTIONS_WITHIN_MODEL_LIMITS")
    return {"method":"MC_R1_SP_FIBRE_NOMINAL_ENGINEERING_CANDIDATE","time_minutes":float(snapshot["snapshot"]["time_minutes"]),
        "status":status,"strength_basis":basis,"bar_temperatures_C":dict(zip(p.bar_ids,map(float,p.theta_s))),
        "section_count":len(rows),"sections":rows,"governing_sampled_strain_section":governing,
        "regulatory_result":"NOT_ESTABLISHED","actual_U_t":None,"actual_t_R_minutes":None,"normative_claim":False,
        "remaining_gates":["SP5_NONUNIFORM_NOMINAL_STIFFNESS_ADJUDICATION","SP_HOT_SECTION_STRAIN_ASSUMPTIONS",
          "THERMAL_AND_SECTION_CONVERGENCE","ANNEX_L_SPALLING","INDEPENDENT_REFERENCE_VALIDATION",
          "FIRST_PHYSICAL_FAILURE_AND_PRODUCTION_REPORT"]}

def history(column,heat,times,**kw):
    if not times or any(type(t) not in (int,float) or not math.isfinite(t) or t<0 or int(t)!=t for t in times):
        raise ValueError("actual whole-minute observations required")
    if any(b<=a for a,b in zip(times,times[1:])):raise ValueError("strict time order")
    rows=[]
    for t in times:
        try:rows.append(assess(column,select_sp2026_snapshot(heat,t),**kw))
        except ValueError as exc:
            rows.append({"time_minutes":t,"status":"UNRESOLVED","reason":str(exc),"normative_claim":False})
            break
        if rows[-1]["status"]!="ALL_SAMPLED_SECTIONS_WITHIN_MODEL_LIMITS":break
    return {"samples":rows,"actual_U_t":None,"actual_t_R_minutes":None,"normative_claim":False}
