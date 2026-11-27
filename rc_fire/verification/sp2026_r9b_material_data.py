"""SP-R9B independent material anchor reconstruction and no-fit comparison.

All measured data are in validation/sp_r9b_material_anchors.json.
Normalized comparisons are exploratory, not design safety checks.
No calibration, no conversion of cube strength to fck, no residual/hot
mixing, no inference of ultimate strain from peak strain or rupture temperature.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
from rc_fire.materials.normative import FIRE_TEMP, CONCRETE_K, CONCRETE_BETA, STEEL_TEMP, STEEL_GROUPS
from rc_fire.materials import tkp_en1992_fire as tkp

VERSION="SP-R9B-material-qualification-v1"
DEFAULT_DATA=Path(__file__).resolve().parents[2]/"validation"/"sp_r9b_material_anchors.json"

def load_anchors(path=DEFAULT_DATA):
    with open(path,encoding="utf-8") as f: data=json.load(f)
    if data["schema"]!="SP-R9B-material-anchors-v1":
        raise ValueError("unexpected material data schema")
    return data

def _positive(x):
    x=float(x)
    if not math.isfinite(x) or x<=0:raise ValueError("positive finite observation required")
    return x

def _metrics(rows,model,observed):
    residuals=[float(r[model])-float(r[observed]) for r in rows if r["temperature_C"]>20]
    if not residuals:return None
    return {"count":len(residuals),"bias":sum(residuals)/len(residuals),
            "RMSE":math.sqrt(sum(v*v for v in residuals)/len(residuals)),
            "max_abs":max(abs(v) for v in residuals)}

def compare_concrete_series(series):
    if series["protocol"]!="hot_uniaxial":
        raise ValueError("hot-state comparison requires hot uniaxial protocol")
    family=series["aggregate"]
    records=series["records"]
    if len({r["temperature_C"] for r in records})!=len(records):
        raise ValueError("aggregate group results first; duplicate temperature")
    baseline=[r for r in records if r["temperature_C"]==20]
    if len(baseline)!=1:raise ValueError("unique same-specimen ambient baseline required")
    f0=_positive(baseline[0]["peak_stress_MPa"])
    e0=_positive(baseline[0]["peak_strain"])
    rows=[]
    for r in records:
        T=float(r["temperature_C"])
        if T not in FIRE_TEMP:raise ValueError("initial comparison limited to SP nodes")
        i=FIRE_TEMP.index(T)
        kc=CONCRETE_K[family][i];beta=CONCRETE_BETA[family][i]
        p=tkp.concrete_parameters(T,aggregate=family)
        obs_f=_positive(r["peak_stress_MPa"])/f0
        obs_e=_positive(r["peak_strain"])/e0
        rows.append({"id":r["id"],"temperature_C":T,
            "measured_strength_ratio":obs_f,"measured_peak_strain_ratio":obs_e,
            "SP_strength_ratio":kc,"SP_beta_ratio":beta,
            "SP_fixed_peak_ratio":1.,
            "SP_constant_k_peak_ratio":kc/beta,
            "TKP_strength_ratio":p.k_c,
            "TKP_peak_strain_ratio":p.eps_c1/tkp.CONCRETE_EPS_C1[0],
            "measured_initial_modulus_MPa":r["initial_modulus_MPa"],
            "measured_ultimate_strain":r["ultimate_strain"],
            "provenance":r["provenance"]})
    metrics={key:_metrics(rows,key,obs) for key,obs in (
        ("SP_strength_ratio","measured_strength_ratio"),
        ("TKP_strength_ratio","measured_strength_ratio"),
        ("SP_fixed_peak_ratio","measured_peak_strain_ratio"),
        ("SP_constant_k_peak_ratio","measured_peak_strain_ratio"),
        ("TKP_peak_strain_ratio","measured_peak_strain_ratio"))}
    return {"id":series["id"],"rows":rows,"metrics_excluding_ambient":metrics,
            "ambient_anchor_only_no_hot_fit":True,
            "geometry_strength_basis_matched_to_design_model":False,
            "initial_modulus_qualified":False,"ultimate_strain_qualified":False,
            "constant_shape_qualified":False,"normative_claim":False}

def compare_steel_modulus(data):
    if data["protocol"]!="hot_steady_state":raise ValueError("wrong steel protocol")
    bars={x["id"]:x for x in data["bars"]}
    rows=[]
    for a in data["modulus_anchors"]:
        T=float(a["temperature_C"]);b=bars[a["bar"]]
        if T not in STEEL_TEMP:raise ValueError("use exact SP node for first comparison")
        obs=_positive(a["modulus_ratio"])
        allowance=_positive(a["reading_allowance"])
        sp=STEEL_GROUPS["S240_S500"]["beta"][STEEL_TEMP.index(T)]
        ec=tkp.STEEL_N[b["route"]]["E"][tkp.TEMP.index(T)]
        rows.append({**a,"SP_candidate_S240_S500_beta":sp,"TKP_route_beta":ec,
                     "SP_minus_observed":sp-obs,"TKP_minus_observed":ec-obs,
                     "SP_outside_graph_reading_allowance":abs(sp-obs)>allowance,
                     "TKP_outside_graph_reading_allowance":abs(ec-obs)>allowance,
                     "actual_SP_nominal_grade_verified":False})
    # Never pool incompatible bar grades/routes into a universal fit.
    by_bar={}
    for bar in sorted({r["bar"] for r in rows}):
        rr=[r for r in rows if r["bar"]==bar]
        by_bar[bar]={k:_metrics(rr,k,"modulus_ratio") for k in
                    ("SP_candidate_S240_S500_beta","TKP_route_beta")}
    transient=data["transient"]
    return {"rows":rows,"metrics_by_bar":by_bar,
            "transient_records":transient["records"],
            "transient_undisputed_count":sum(not r["disputed"] for r in transient["records"]),
            "rupture_prediction_performed":False,
            "yield_not_equated_with_rupture":True,
            "hot_steel_ductility_qualified":False,"normative_claim":False}

def run_material_campaign(data=None):
    data=load_anchors() if data is None else data
    return {"version":VERSION,
            "concrete":[compare_concrete_series(s) for s in data["concrete"]],
            "steel":compare_steel_modulus(data["steel"]),
            "unacquired_or_excluded":data["registry"],
            "parameters_fitted":0,"independent_full_curve_validation_completed":False,
            "SP_only_model_admitted":False,"actual_t_R_minutes":None,"normative_claim":False}
