"""SP-R9G literature-based extended LITS alternatives, not normative SP.

Lange/Jansson (2014) eq4 and Youssef/Moftah (2007) eq31b:
high-T modified Anderberg-Thelandersson rate 1e-4 per K per stress ratio.
Youssef/Moftah eq32/33: Nielsen and Diederichs (secondary citations).
Nielsen referenced to 20 C; all alternatives integrated on first heating
with affine stress over each segment. R9D low-T expansion convention
retained for modified AT; SP factors and all damage inputs still research.
No claim of experimental validation of the combined SP-based model.
"""
from dataclasses import dataclass,asdict
import math
from rc_fire.mechanics import sp2026_nonisothermal_coupling as base
from rc_fire.mechanics import sp2026_transient_history as tr
from rc_fire.materials.normative import concrete_thermal_strain_coefficients
from rc_fire.materials.sp2026_fire import concrete_free_thermal_strain_sp

VERSION="SP-R9G-extended-hot-domain-v1"
MODIFIED_AT="AT_MODIFIED_550"
NIELSEN="NIELSEN_AMBIENT_REFERENCED"
DIEDERICHS="DIEDERICHS_POLYNOMIAL"
ZERO="ZERO_LITS_CONTROL"
MODES=(MODIFIED_AT,NIELSEN,DIEDERICHS,ZERO)

def rate(mode,T,family,K):
    """d(phi)/dT, dimensionless strain/K at unit ambient stress ratio."""
    T=base.finite(T,"temperature")
    if mode not in MODES or not 20<=T<=800:
        raise base.DomainError("declared LITS mode and 20..800 C required")
    if mode==ZERO:return 0.
    if mode==NIELSEN:return 3.8e-5
    if mode==DIEDERICHS:
        x=T-20.
        return 9.9e-10*x*x-3.44e-7*x+4.12e-5
    return (K*concrete_thermal_strain_coefficients(family,T)["alpha_bt_per_C"]
            if T<=550 else 1e-4)

def increment(mode,p,s,T,stress):
    """Integrate affine stress times coefficient over newly reached T.
    Three-point Gauss exact for quadratic Diederichs rate times stress^2;
    split at all SP expansion knots and 550 C transition.
    """
    if mode not in MODES or not 20<=T<=800:
        raise base.DomainError("LITS domain")
    H=s.maximum_temperature_C
    if T<=H:return 0.,0.
    a=H;b=T
    cuts=[a]+[x for x in (50.,100.,300.,500.,550.,700.) if a<x<b]+[b]
    ds=dw=0.
    for l,r in zip(cuts,cuts[1:]):
        mid=(l+r)/2.;half=(r-l)/2.
        for xi,w in ((-math.sqrt(3/5),5/9),(0.,8/9),(math.sqrt(3/5),5/9)):
            theta=mid+half*xi
            u=(theta-s.temperature_C)/(T-s.temperature_C)
            sig=s.stress_MPa+u*(stress-s.stress_MPa)
            inc=half*w*sig/p.reference_compression_MPa*rate(mode,theta,p.family,p.K)
            ds+=inc;dw+=sig*inc
    return ds,dw

@dataclass(frozen=True)
class State:
    mode:str
    active:base.State
    time_s:float=0.
    temperature_C:float=20.
    maximum_temperature_C:float=20.
    total_compression:float=0.
    thermal_cutoff:bool=False

def initial_state(p,mode):
    if mode not in MODES:raise base.DomainError("explicit LITS model required")
    return State(mode,base.initial_state(p))

def _active(s,t,T,u):
    return base._trial_step(s.active,time_s=t,temperature_C=T,total_compression=u,
        max_temperature=800.,lits=lambda p,old,T,sig:increment(s.mode,p,old,T,sig))

def trial_step(s,*,time_s,temperature_C,total_compression):
    """Atomic state transfer. Exactly 800 C still active. Above 800 C the
    user cutoff makes concrete inactive; retain history, never infer collapse.
    Cooling after cutoff retains inactivity as declared research convention.
    No constitutive strain or energy extrapolation beyond material range.
    """
    t=base.finite(time_s,"time");T=base.finite(temperature_C,"T")
    u=base.finite(total_compression,"total strain")
    if t<=s.time_s or T<20:raise base.DomainError("increasing time and T>=20")
    H=max(T,s.maximum_temperature_C)
    if not s.thermal_cutoff and T<=800:
        a,r=_active(s,t,T,u)
        return State(s.mode,a,t,T,H,u,False),{**r,"LITS_mode":s.mode,
              "thermal_cutoff":False,"thermal_cutoff_energy_qualified":False}
    a=s.active;crossing=None;released=0.
    if not s.thermal_cutoff:
        frac=(800.-s.temperature_C)/(T-s.temperature_C)
        if frac<0 or frac>=1:raise base.DomainError("invalid cutoff crossing")
        if frac>0:
            tc=s.time_s+frac*(t-s.time_s)
            uc=s.total_compression+frac*(u-s.total_compression)
            a,crossing=_active(s,tc,800.,uc)
            released=crossing["stored_energy_MPa"]
        else:
            p=a.parameters
            E=base._material(p,a.maximum_temperature_C)[0]
            m=a.total_compression+base._thermal(p,a.temperature_C,a.maximum_temperature_C)-a.transient_compression-a.basic_creep_compression
            released=base._psi(E,m,a.plastic_compression,a.damage)
    new=State(s.mode,a,t,T,H,u,True)
    return new,{"time_s":t,"temperature_C":T,"maximum_temperature_C":H,
            "total_compression":u,"stress_MPa":0.,"effective_tangent_MPa":0.,
            "transient_compression":a.transient_compression,
            "basic_creep_compression":a.basic_creep_compression,
            "plastic_compression":a.plastic_compression,"damage":a.damage,
            "thermal_cutoff":True,"LITS_mode":s.mode,"branch":"USER_ZERO_ABOVE_800_RETAINED",
            "cutoff_crossing_active_ledger":crossing,
            "removed_stored_energy_MPa_not_qualified_dissipation":released,
            "thermal_cutoff_energy_qualified":False,"global_failure_proven":False,
            "normative_claim":False}

def run_path(p,mode,path):
    s=initial_state(p,mode);rows=[]
    for args in path:
        try:s,r=trial_step(s,**args)
        except (base.DomainError,ArithmeticError) as exc:
            return {"status":"UNRESOLVED_PATH_STOP","rows":rows,"state":asdict(s),
                    "reason":str(exc),"blocked_point":args}
        rows.append(r)
    return {"status":"DIAGNOSTIC_COMPLETE","rows":rows,"state":asdict(s)}

def campaign():
    # Keep some compression active through 800 C, then separately test cutoff.
    nodes=[(0.,20.,0.),(600.,200.,0.),(1200.,400.,0.),
           (1800.,550.,.003),(2400.,700.,.006),(3000.,800.,.010),
           (3600.,500.,.001),(4200.,800.,.005)]
    runs=[]
    keys=("stress_MPa","transient_compression","basic_creep_compression",
          "plastic_compression","damage")
    for mode in MODES:
      for n in (16,64,256):
        r=run_path(base.synthetic(),mode,base._path(nodes,n))
        rr=r["rows"];last=rr[-1] if rr else {}
        checkpoints=[{k:rr[i*n-1][k] for k in ("temperature_C",*keys)}
                     for i in range(1,len(nodes)) if i*n<=len(rr)]
        runs.append({"mode":mode,"subdivisions":n,"status":r["status"],
                     "reason":r.get("reason"),"last":{k:last.get(k) for k in keys},
                     "checkpoints":checkpoints,
                     "max_compatibility_residual":max((abs(x["compatibility_residual"]) for x in rr),default=0.),
                     "max_energy_residual":max((abs(x["split_energy_residual_MPa"]) for x in rr),default=0.),
                     "external_split_work_MPa":sum(x["external_split_work_MPa"] for x in rr),
                     "external_trapezoid_work_MPa":sum(x["external_endpoint_trapezoid_MPa"] for x in rr)})
    comparisons=[]
    for mode in MODES:
        for lo,hi in ((16,64),(64,256)):
            a=next(x for x in runs if x["mode"]==mode and x["subdivisions"]==lo)
            b=next(x for x in runs if x["mode"]==mode and x["subdivisions"]==hi)
            complete=a["status"]==b["status"]=="DIAGNOSTIC_COMPLETE"
            diff={k:max(abs(x[k]-y[k]) for x,y in zip(a["checkpoints"],b["checkpoints"]))
                  for k in keys} if complete else None
            # Explicit research tolerances, no relative division by zero.
            passed=complete and diff["stress_MPa"]<=.05 and diff["damage"]<=.005 and all(
                diff[k]<=5e-5 for k in keys if k.endswith("compression"))
            comparisons.append({"mode":mode,"lo":lo,"hi":hi,"max_checkpoint_differences":diff,
                                "checkpoint_convergence":passed})
    cut=run_path(base.synthetic(),MODIFIED_AT,base._path(
        [(0.,20.,0.),(1800.,800.,.008),(1860.,801.,.008),
         (1920.,400.,.01),(1980.,800.,.005)],32))
    return {"version":VERSION,"runs":runs,"comparisons":comparisons,
            "cutoff_status":cut["status"],"cutoff_last":cut["rows"][-1] if cut["rows"] else None,
            "parameters_fitted":0,"independent_high_temperature_experiment_validated":False,
            "full_thermodynamic_qualification":False,"actual_t_R_minutes":None,"normative_claim":False}
