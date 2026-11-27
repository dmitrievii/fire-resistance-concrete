"""SP-R9C exploratory full-envelope discrimination with source provenance.

Graph anchors are approximate. Secondary concrete reproduction is not
primary validation. All shape comparisons conditioned on measured hot
peak; no prediction of hot peak, strength or global R is implied.
"""
from pathlib import Path
import json
import math
import numpy as np
from rc_fire.materials import tkp_en1992_fire as tkp

DATA=Path(__file__).resolve().parents[2]/"validation"/"sp_r9c_curve_anchors.json"
def load_data():
    with DATA.open(encoding="utf-8") as f:return json.load(f)

def normalized_curve(series):
    if series["units"]!=["strain_percent","stress_kgf_cm2"]:
        raise ValueError("not concrete material strain/stress")
    x,y=np.asarray(series["points"],dtype=float).T
    ep,fp=map(float,series["peak"])
    if ep<=0 or fp<=0 or not np.all(np.isfinite(x+y)) or np.any(np.diff(x)<=0) or np.any(y<0):
        raise ValueError("invalid graph coordinates")
    if not any(abs(a-ep)<1e-10 and abs(b-fp)<1e-10 for a,b in zip(x,y)):
        raise ValueError("explicit measured peak anchor required")
    return x/ep,y/fp

def shape(x,mode,*,r=3.,k=2.091170911468961,limit=3.5/2.2,tkp_ultimate_ratio=None):
    if x<0:raise ValueError("compression-only shape")
    if mode=="SP_PARABOLA":
        if x>1.75:return None
        return 2*x-x*x if x<=1 else 1.
    if mode=="SP_RATIONAL":
        if x>limit or x>k or 1+(k-2)*x<=0:return None
        return (k*x-x*x)/(1+(k-2)*x)
    if mode=="TKP_LINEAR":
        if tkp_ultimate_ratio is None or tkp_ultimate_ratio<=1:
            raise ValueError("TKP ultimate/peak ratio required")
        return 3*x/(2+x**3) if x<=1 else max(0.,(tkp_ultimate_ratio-x)/(tkp_ultimate_ratio-1))
    if mode=="POPOVICS":
        if r<=1:raise ValueError("r>1 required")
        return r*x/(r-1+x**r)
    if mode=="EXPONENTIAL":
        return x*math.exp(1-x)
    raise ValueError("unknown shape")

def _metrics(x,y,pred):
    # Strain-weighted RMSE avoids giving densely digitized parts extra weight.
    # Integrate squared residual of piecewise-linear residual on same knots.
    a=np.asarray(x); b=np.asarray(y)-np.asarray(pred)
    if len(a)<2 or a[-1]<=a[0]:return None
    h=np.diff(a)
    err=np.sum(h*(b[:-1]**2+b[:-1]*b[1:]+b[1:]**2)/3)
    return {"RMSE":float(math.sqrt(err/(a[-1]-a[0]))),
            "strain_span":float(a[-1]-a[0]),"count":len(a)}

def _predict(x,T,mode,r):
    p=tkp.concrete_parameters(T,aggregate="siliceous")
    return [shape(float(a),mode,r=r,tkp_ultimate_ratio=p.eps_cu1/p.eps_c1) for a in x]

def compare_curve(series,r_fit):
    x,y=normalized_curve(series);T=series["temperature_C"]
    modes={"SP_PARABOLA":("SP_PARABOLA",3.),"SP_RATIONAL":("SP_RATIONAL",3.),
           "TKP_LINEAR":("TKP_LINEAR",3.),"POPOVICS_R3":("POPOVICS",3.),
           "POPOVICS_AMBIENT_FIT":("POPOVICS",r_fit),"EXPONENTIAL":("EXPONENTIAL",3.)}
    preds={name:_predict(x,T,m,r) for name,(m,r) in modes.items()}
    common=np.array([all(p[i] is not None for p in preds.values()) for i in range(len(x))])
    out={}
    for name,p in preds.items():
        valid=np.array([v is not None for v in p])
        pv=np.array([np.nan if v is None else v for v in p])
        a=common&(x<=1);d=common&(x>=1)
        out[name]={"common_ascending":_metrics(x[a],y[a],pv[a]),
                   "common_descending":_metrics(x[d],y[d],pv[d]),
                   "own_supported_span_fraction":float((x[valid][-1]-x[valid][0])/(x[-1]-x[0])) if valid.any() else 0.,
                   "unsupported_anchors":int((~valid).sum()),
                   "full_observed_interval":_metrics(x,y,pv) if valid.all() else None}
    # First descending crossing at 0.2 peak stress; not an invented zero-stress endpoint.
    crossing=None
    for i in range(1,len(x)):
        if x[i-1]>=1 and y[i-1]>.2>=y[i]:
            crossing=float(x[i-1]+(x[i]-x[i-1])*(y[i-1]-.2)/(y[i-1]-y[i]))
            break
    return {"id":series["id"],"T_C":T,"models":out,
            "normalized_points":list(zip(x.tolist(),y.tolist())),
            "postpeak_20pct_crossing":crossing,
            "end_strain_ratio":float(x[-1]),"end_stress_ratio":float(y[-1]),
            "ultimate_strain_qualified":False,"source_tier":series["source_tier"],
            "peak_conditioned_not_peak_prediction":True}

def campaign():
    data=load_data()
    series=data["concrete"];x,y=normalized_curve(series[0])
    # Calibration at the 30 C curve only; 300/600 C withheld from fitting.
    # Same reproduced experiment family, not external specimen validation.
    r=min(np.linspace(1.05,10.,896),key=lambda r:_metrics(x,y,[shape(a,"POPOVICS",r=r) for a in x])["RMSE"])
    curves=[compare_curve(s,float(r)) for s in series]
    hsc=[{**a,"preloaded_to_unloaded_peak_ratio":a["preloaded_peak_strain"]/a["unloaded_peak_strain"]}
         for a in data["hsc_protocol_anchors"]["records"]]
    return {"curves":curves,"ambient_fit_r":float(r),"fit_parameters":1,
            "fit_curve_id":series[0]["id"],"holdout_ids":[s["id"] for s in series[1:]],
            "steel_extension_curves":data["steel"],"hsc_protocol_effect":hsc,
            "blocked_sources":data["blocked"],
            "independent_primary_full_concrete_curves":0,
            "damage_plasticity_identified":False,"SP_model_admitted":False,
            "actual_t_R_minutes":None,"normative_claim":False}
