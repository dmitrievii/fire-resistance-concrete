"""SP-R9D: explicit history operator, independent material-point research.

Compression-positive stress and total strain; free thermal elongation positive.
Anderberg/Thelandersson strain increment adapted to varying load and first
heating. SP Tables 11/12 expansion/shrinkage integral convention from R8E.
No validated damage/plasticity, basic creep or structural R. Only T<=550 C:
the cited proportional expansion law has known limitations above this range.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import math
import json
from rc_fire.materials.sp2026_fire import concrete_free_thermal_strain_sp
from rc_fire.materials.normative import FIRE_TEMP, CONCRETE_K, CONCRETE_BETA
from rc_fire.materials.normative import concrete_thermal_strain_coefficients

VERSION="SP-R9D-explicit-first-heating-v1"
DATA=Path(__file__).resolve().parents[2]/"validation"/"sp_r9d_transient_anchors.json"
EXPLICIT="EXPLICIT_LITS_ELASTIC_DIAGNOSTIC"
IMPLICIT="IMPLICIT_TKP_NO_ADDITIONAL_LITS"
class HistoryDomainError(ValueError):pass

def _finite(x,name):
    x=float(x)
    if not math.isfinite(x):raise HistoryDomainError(name+" must be finite")
    return x
def _interp(T,values):
    for i,t in enumerate(FIRE_TEMP):
        if T==t:return values[i]
        if T<t:
            a=FIRE_TEMP[i-1]
            return values[i-1]+(values[i]-values[i-1])*(T-a)/(t-a)
    raise HistoryDomainError("outside table")

@dataclass(frozen=True)
class Parameters:
    family:str
    reference_compression_MPa:float
    ambient_modulus_MPa:float
    K:float=2.35
    mode:str=EXPLICIT
    def validate(self):
        if self.family not in ("siliceous","calcareous"):raise HistoryDomainError("normal-weight family required")
        if self.mode!=EXPLICIT:
            raise HistoryDomainError("explicit LITS must not be added to implicit TKP hot law")
        if min(_finite(self.reference_compression_MPa,"f0"),
               _finite(self.ambient_modulus_MPa,"E0"))<=0:
            raise HistoryDomainError("positive f0, E0 required")
        if not 0<=_finite(self.K,"K")<=2.35:raise HistoryDomainError("K outside diagnostic range 0..2.35")
        return self

@dataclass(frozen=True)
class State:
    time_s:float=0.
    temperature_C:float=20.
    maximum_temperature_C:float=20.
    stress_MPa:float=0.
    transient_compression:float=0.
    thermal_work_MPa:float=0.
    max_instantaneous_compression:float=0.

def _thermal(p,T,H):
    exp=concrete_free_thermal_strain_sp(T,p.family,signed_shrinkage=False)
    signed=concrete_free_thermal_strain_sp(H,p.family,signed_shrinkage=True)
    expH=concrete_free_thermal_strain_sp(H,p.family,signed_shrinkage=False)
    # Research convention: freeze signed shrinkage contribution at H during
    # cooling; no independently qualified irreversible shrinkage law.
    return exp,signed-expH

def _update_lits(p,s,T,stress):
    H=s.maximum_temperature_C
    if T<=H:return 0.,0.
    # Stress linearly interpolated in time/temperature across a prescribed
    # straight segment. Only the new maximum temperature interval contributes.
    # Split at source alpha knots and zero stress (if relevant). Here stresses
    # are compression nonnegative; 2-point Gauss exactly integrates linear
    # stress times piecewise-linear coefficient, and stress^2 times coefficient.
    a=H;b=T
    cuts=[a]+[x for x in (50.,100.,300.,500.) if a<x<b]+[b]
    ds=0.;dw=0.
    for l,r in zip(cuts,cuts[1:]):
        mid=(l+r)/2.;half=(r-l)/2.
        for xi in (-1/math.sqrt(3),1/math.sqrt(3)):
            theta=mid+half*xi
            u=(theta-s.temperature_C)/(T-s.temperature_C)
            sig=s.stress_MPa+u*(stress-s.stress_MPa)
            alpha=concrete_thermal_strain_coefficients(p.family,theta)["alpha_bt_per_C"]
            inc=half*p.K*sig/p.reference_compression_MPa*alpha
            ds+=inc;dw+=sig*inc
    return ds,dw

def trial_step(p,s,*,time_s,temperature_C,stress_MPa):
    """Pure trial, no mutation. Return new immutable state and complete ledger.

    Piecewise-linear prescribed stress and temperature path; exact quadrature
    for new thermal interval under the assumed alpha law. This is a material
    point stress-controlled elastic diagnostic, not a full nonlinear law.
    No recovery in modulus/strength on cooling: max-temperature engineering
    envelope, not an SP cooling prescription. No strain-to-damage inference.
    """
    p.validate()
    t=_finite(time_s,"time");T=_finite(temperature_C,"T");sig=_finite(stress_MPa,"stress")
    if t<=s.time_s or not 20<=T<=550 or sig<0:
        raise HistoryDomainError("positive time increment, 20..550 C, compression only")
    if not (20<=s.temperature_C<=s.maximum_temperature_C<=550 and
            s.transient_compression>=0 and s.stress_MPa>=0):
        raise HistoryDomainError("invalid committed state")
    H=max(T,s.maximum_temperature_C)
    # Peak strength bound for the full linear path: test every SP node in
    # the newly reached temperature interval. Reject before committing.
    checkpoints=[0.,1.]
    if T!=s.temperature_C:
        checkpoints += [(x-s.temperature_C)/(T-s.temperature_C)
                        for x in FIRE_TEMP if min(T,s.temperature_C)<x<max(T,s.temperature_C)]
    for u in checkpoints:
        h=max(s.maximum_temperature_C,s.temperature_C+u*(T-s.temperature_C))
        ss=s.stress_MPa+u*(sig-s.stress_MPa)
        if ss>p.reference_compression_MPa*_interp(h,CONCRETE_K[p.family])+1e-10:
            raise HistoryDomainError("prescribed stress exceeds candidate peak resistance; no physical failure inference")
    dtr,dw=_update_lits(p,s,T,sig)
    E=p.ambient_modulus_MPa*_interp(H,CONCRETE_BETA[p.family])
    e_el=sig/E
    e_exp,e_sh=_thermal(p,T,H)
    e_tr=s.transient_compression+dtr
    e_tot=e_el+e_tr-e_exp-e_sh
    new=State(t,T,H,sig,e_tr,s.thermal_work_MPa+dw,
              max(s.max_instantaneous_compression,e_el))
    ledger={"time_s":t,"temperature_C":T,"maximum_temperature_C":H,
            "stress_MPa":sig,"elastic_compression":e_el,"transient_compression":e_tr,
            "delta_transient_compression":dtr,"free_expansion":e_exp,
            "signed_free_shrinkage_contribution":e_sh,
            "total_compression_strain":e_tot,"transient_stress_work_MPa":new.thermal_work_MPa,
            "elastic_modulus_MPa":E,"basic_creep":"NOT_MODELLED",
            "plasticity_damage":"NOT_MODELLED","normative_claim":False}
    return new,ledger

def strain_controlled_trial(p,s,*,time_s,temperature_C,total_compression_strain):
    """Solve compatible stress for prescribed total strain on compression branch.

    Bracketed bisection. No tension law, no invented postpeak law. Failed
    trial does not commit. The history integral uses endpoint stress in
    every trial so iteration cannot accumulate strain multiple times.
    """
    target=_finite(total_compression_strain,"target strain")
    T=_finite(temperature_C,"T")
    if not 20<=T<=550:raise HistoryDomainError("temperature outside scope")
    H=max(T,s.maximum_temperature_C)
    hi=p.reference_compression_MPa*_interp(H,CONCRETE_K[p.family])
    def ev(sig):return trial_step(p,s,time_s=time_s,temperature_C=T,stress_MPa=sig)
    a,la=ev(0.);b,lb=ev(hi)
    fa=la["total_compression_strain"]-target
    fb=lb["total_compression_strain"]-target
    if fa>1e-12 or fb< -1e-12:
        raise HistoryDomainError("target outside compression-only candidate branch")
    if abs(fa)<=1e-12:return a,{**la,"compatibility_residual":fa}
    if abs(fb)<=1e-12:return b,{**lb,"compatibility_residual":fb}
    lo=0.
    for _ in range(80):
        m=(lo+hi)/2.;c,lc=ev(m)
        f=lc["total_compression_strain"]-target
        if abs(f)<=1e-12:return c,{**lc,"compatibility_residual":f}
        if f>0:hi=m
        else:lo=m
    raise HistoryDomainError("strain-control convergence failed")

def run_path(p,path,*,initial=State()):
    state=initial;rows=[]
    for point in path:
        try:state,row=trial_step(p,state,**point)
        except HistoryDomainError as exc:
            return {"rows":rows,"committed_state":asdict(state),
                    "status":"UNRESOLVED_PATH_STOP","blocked_point":point,"reason":str(exc),
                    "actual_t_R_minutes":None}
        rows.append(row)
    return {"rows":rows,"committed_state":asdict(state),"status":"DIAGNOSTIC_COMPLETE",
            "actual_t_R_minutes":None}

def _path(stress,temps):
    return [{"time_s":float(i+1)*60,"temperature_C":T,"stress_MPa":sig}
            for i,(T,sig) in enumerate(zip(temps,stress))]

def benchmark_paths():
    p=Parameters("siliceous",30.,30000.)
    temps=[20.,200.,400.,200.,400.,500.,20.]
    stresses=[9.,9.,9.,0.,0.,9.,0.]
    loaded=run_path(p,_path(stresses,temps))
    unloaded=run_path(p,_path([0.,0.,0.,0.,0.,9.,0.],temps))
    restrained=[];s=State()
    for i,T in enumerate((100.,200.,300.,400.,500.)):
        try:s,r=strain_controlled_trial(p,s,time_s=(i+1)*60.,temperature_C=T,total_compression_strain=0.)
        except HistoryDomainError as exc:
            restrained.append({"temperature_C":T,"status":"UNRESOLVED","reason":str(exc)});break
        restrained.append(r)
    return {"loaded_heating_unload_reheat":loaded,"unloaded_first_heating":unloaded,
            "restrained_material_point":restrained,"normative_claim":False}

def screen_reproduced_tests():
    data=json.loads(DATA.read_text(encoding="utf-8"))
    rows=[]
    for family in ("siliceous","calcareous"):
      for E0 in (25000.,30000.,35000.):
       for K in (0.,1.8,2.35):
        for rec in data["records"]:
            f0=.75*rec["cube_strength_MPa"];sig=f0*rec["preload_ratio"]
            p=Parameters(family,f0,E0,K)
            state,_=trial_step(p,State(),time_s=1.,temperature_C=20.,stress_MPa=sig)
            initial=sig/E0
            for T,obs in rec["points"]:
                state,r=trial_step(p,state,time_s=1.+12*(T-20.),temperature_C=T,stress_MPa=sig)
                predicted=1000*(initial-r["total_compression_strain"])
                rows.append({"specimen":rec["id"],"T_C":T,"family_scenario":family,
                    "assumed_E0_MPa":E0,"K":K,"observed_extension_change_permille":obs,
                    "predicted_extension_change_permille":predicted,"error_permille":predicted-obs})
    summary=[]
    for family in ("siliceous","calcareous"):
      for E0 in (25000.,30000.,35000.):
       for K in (0.,1.8,2.35):
        rr=[r for r in rows if (r["family_scenario"],r["assumed_E0_MPa"],r["K"])==(family,E0,K)]
        summary.append({"family_scenario":family,"assumed_E0_MPa":E0,"K":K,
                        "count":len(rr),"RMSE_permille":math.sqrt(sum(r["error_permille"]**2 for r in rr)/len(rr))})
    return {"rows":rows,"summary":summary,"parameters_fitted":0,
            "coefficient_independent_holdout":False,"primary_raw_data_acquired":False,
            "aggregate_and_modulus_matched":False,"normative_claim":False}
