"""MC-R4A: common-field cross verification, not an R admission route."""
import copy
import math
from scipy.integrate import quad
from rc_fire.integration import mc_r1_engineering as full
from rc_fire.integration import mc_r2_reduced as reduced
from rc_fire.integration import mc_r3_reconciliation as mc3
from rc_fire.integration import mc_r4_applicability as mc4
from rc_fire.thermal.sp2026_annex_k_field import build_annex_k_snapshot
from rc_fire.thermal.normative import RectangularExposure, heating_depth_m

METHODS=("contour","k27_cross","full_temperature")
FULL_STATES={"ALL_SAMPLED_SECTIONS_WITHIN_MODEL_LIMITS":"WITHIN",
             "MODEL_LIMIT_EXCEEDED":"EXCEEDED_STRAIN_MODEL"}

def integrated_isotherm_area(ex,coeff,t,critical_C):
    """Independent K.10 numerical integration in the non-overlap square domain.
    This is NOT a K.27 result. Distances are measured from nearest faces.
    """
    ex.validate()
    if set(ex.faces)!={"left","right","bottom","top"} or abs(ex.b_mm-ex.h_mm)>1e-9:
        raise ValueError("square four-sided comparator only")
    if not 20<critical_C<1220:
        raise ValueError("critical temperature")
    H=ex.h_mm/2000
    l=heating_depth_m(coeff["a_red_m2_h"],t)
    off=coeff["phi_1"]*math.sqrt(coeff["a_red_m2_h"])
    if l>H+off:
        raise ValueError("opposite heating layers overlap")
    if l<=off:
        return 4*H*H
    q=(critical_C-20)/1200
    def p(d):return max(0.,1-(d+off)/l)**2
    def lost_width(x):
        px=p(x)
        if px>=q:return H
        py=(q-px)/(1-px)
        return min(H,max(0.,l*(1-math.sqrt(py))-off))
    lc=l*(1-math.sqrt(q))-off
    knots=sorted(set(x for x in (lc,l-off) if 0<x<H))
    lost=quad(lost_width,0,H,points=knots,epsabs=1e-12,epsrel=1e-10)[0]
    return 4*(H*H-lost)

def matched_column(template,N,Mx,My=0.):
    c=copy.deepcopy(template)
    c.update(length_m=13.7,mu_x=.8,mu_y=1.2)
    c["sections"]=[{"id":"synthetic_station","z_m":0.,"N_kN":float(N),
                    "Mx_kNm":float(Mx),"My_kNm":float(My)}]
    return c

def compare_at_time(column,t,*,action_contract,creep_by_axis,grid=12,strips=48,
                    bar_distance_convention="clear"):
    # All methods see the identical thermal source and actual bar coordinates.
    # Characteristic strength is matched to MC-R2; no mixing of gamma bases.
    kw=dict(selected=True,action_contract=action_contract,creep_by_axis=creep_by_axis,
            strips=strips,bar_distance_convention=bar_distance_convention)
    results={}
    for mode in METHODS[:2]:
        q=reduced.assess(column,t,area_method=mode,**kw)
        results[mode]={"state":mc3.classify(q),"evidence":q}
    try:
        field=build_annex_k_snapshot(column,t,bar_distance_convention=bar_distance_convention)
        f=full.assess(column,field,basis=full.CHARACTERISTIC,
                      action_contract=action_contract,creep_by_axis=creep_by_axis,
                      grid=grid,annex_k_comparison=True)
        results["full_temperature"]={"state":FULL_STATES.get(f["status"],"UNKNOWN"),"evidence":f}
    except (ValueError,TypeError,KeyError,ArithmeticError,RuntimeError) as exc:
        results["full_temperature"]={"state":"UNKNOWN","evidence":{"reason":str(exc)}}
    return {"time_minutes":t,"results":results,"thermal_source":"SP2026_ANNEX_K_ANALYTICAL",
            "annex_l":mc3.spalling(column),"actual_t_R_minutes":None,"normative_claim":False,
            "ratio_comparability":"reduced moment ratio is not full fibre strain ratio"}

def history(column,*,end_minute,**kw):
    if type(end_minute) is not int or not 0<=end_minute<=column["fire_minutes"]:
        raise ValueError("whole minute range")
    rows=[]; transitions={m:[] for m in METHODS}; first={};prev={}
    for t in range(end_minute+1):
        row=compare_at_time(column,t,**kw); rows.append(row)
        for method,r in row["results"].items():
            state=r["state"]
            if state!=prev.get(method):
                transitions[method].append({"minute":t,"state":state})
            if state!="WITHIN" and method not in first:
                first[method]={"minute":t,"state":state}
            prev[method]=state
    return {"samples":rows,"transitions":transitions,"first_nonwithin":first,
            "unknowns_not_interpolated":True,"later_within_not_erasing_earlier_event":True,
            "actual_t_R_minutes":None,"normative_claim":False}
