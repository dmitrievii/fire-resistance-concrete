"""MC-R3: normative-area comparator and whole-minute model history.
The area-matched cross is an engineering shape choice, not prescribed by
K.27. No promotion of model limit to regulatory R or physical failure.
"""
import math
from rc_fire.integration import mc_r2_reduced as r
from rc_fire.spalling.annex_l import evaluate_annex_l
from rc_fire.thermal.sp2026_annex_k_field import build_annex_k_snapshot

def spalling(column):
    q=evaluate_annex_l(column)
    gate="UNRESOLVED_ANNEX_L"
    if q["status"]=="calculated_method_scope":
        if q["protection_required"]:gate="PROTECTION_REQUIRED_NOT_MODELLED"
        elif not q["natural_sand_verified"] or not q["moisture_method_qualified"]:
            gate="UNQUALIFIED_ANNEX_L_INPUTS"
        else:
            f=build_annex_k_snapshot(column,0.)
            w=f["annex_k_coefficients"]["Wc_mass_percent"]/100
            v=q["coefficients"]["Wc_kg_kg"]
            gate="ANNEX_L_CRITERION_WITHIN" if abs(w-v)<=1e-10 else "THERMAL_ANNEX_L_MOISTURE_MISMATCH"
    return {"status":gate,"F":q.get("F"),"protection_required":q.get("protection_required"),
            "source":q.get("source"),"details":q,"normative_claim":False}

def compare(column,t,**kw):
    q={a:r.assess(column,t,area_method=a,**kw) for a in ("contour","k27_cross")}
    return {"time_minutes":t,"methods":q,"annex_l":spalling(column),
            "normative_claim":False,"actual_t_R_minutes":None}

def historical_reference():
    """Shift the original moment datum only, not a recalculation of K18
    with the new geometry. All legacy assumptions retained."""
    from multicolumn_r05.calculation_engine import Inputs,Geometry,Fire,Material,Mechanics,Variant,compute
    a=compute(Inputs(Geometry(),Fire(),Material(),Mechanics(),(
        Variant("v1",496.7,3.83,0.,20.),Variant("v2",527.16,6.5,0.,25.))))
    v=a["variants"]["v2"];rows={}
    for axis,x in v["axes"].items():
        lever=(x["d_fi_m"]-.05)/2
        shift=x["N_kN"]*lever
        rows[axis]={"N_kN":x["N_kN"],"legacy_area_m2":x["A_cfi_m2"],
            "legacy_Ic_m4":x["I_c_m4"],"legacy_Ncrit_kN":x["N_cr_kN"],
            "steel_reference_MEd_kNm":x["M_Ed_kNm"],"steel_reference_MRd_kNm":x["M_Rd_kNm"],
            "legacy_reference_shift_kNm":shift,"legacy_centroid_reference_MEd_kNm":x["M_Ed_kNm"]-shift,
            "legacy_centroid_reference_MRd_kNm":x["M_Rd_kNm"]-shift,
            "moment_margin_kNm":x["M_Rd_kNm"]-x["M_Ed_kNm"],"legacy_ratio":x["utilization"]}
    return {"axes":rows,"legacy_thermal":a["thermal"],"reference_shift_only":True,
            "not_identical_physical_geometry":True,"normative_claim":False}

def classify(q):
    if q["status"]=="ALL_MODEL_CHECKS_WITHIN":return "WITHIN"
    if q["status"]=="UNRESOLVED":return "UNKNOWN"
    rows=q.get("sections",[])
    # A model section capacity exceedance, rather than a numerical or
    # amplification domain stop. A single verified adverse section is enough.
    if any(v["status"] in ("AXIAL_MODEL_LIMIT_EXCEEDED","MODEL_MOMENT_LIMIT_EXCEEDED") for v in rows):
        return "EXCEEDED"
    return "UNKNOWN"

def history(column,*,end_minute,start_minute=0,area_method="contour",required_minutes=None,**kw):
    if type(start_minute) is not int or type(end_minute) is not int or not 0<=start_minute<=end_minute<=column["fire_minutes"]:
        raise ValueError("integer minute observation window")
    if required_minutes is not None and (type(required_minutes) is not int or not start_minute<=required_minutes<=end_minute):
        raise ValueError("required minute must lie in observation window")
    if area_method not in ("contour","k27_cross"):raise ValueError("explicit area method")
    annex=spalling(column)
    rows=[];last=None;bracket=None;unknown=None;required=None
    for t in range(start_minute,end_minute+1):
        q=r.assess(column,t,area_method=area_method,**kw);state=classify(q)
        ratios=[s["moment_ratio"] for s in q.get("sections",[]) if s["moment_ratio"] is not None]
        rows.append({"t":t,"state":state,"model_status":q["status"],"moment_ratio_max":max(ratios) if ratios else None,
                     "reason":q.get("reason"),"sections":q.get("sections",[])})
        if state=="WITHIN":
            last=t
            if required_minutes==t:required="WITHIN_AT_ALL_OBSERVED_MINUTES"
        elif state=="EXCEEDED":
            if last==t-1:bracket=[last,t]
            if required_minutes is not None and t<=required_minutes:required="MODEL_LIMIT_EXCEEDED"
            break
        else:unknown=t;break
    return {"area_method":area_method,"start_minute":start_minute,"end_minute":end_minute,
        "samples":rows,"last_within_minute":last,"first_unknown_minute":unknown,"sampled_limit_interval_min":bracket,
        "required_model_check":required or "NOT_ESTABLISHED","annex_l":annex,
        "whole_minute_model_result":last if bracket is not None and start_minute==0 else None,
        "actual_t_R_minutes":None,"normative_claim":False,
        "regulatory_result":"NOT_ESTABLISHED","section_limit_not_global_failure":True}
