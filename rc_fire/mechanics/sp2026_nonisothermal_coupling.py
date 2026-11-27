"""SP-R9F: explicit non-isothermal uniaxial research coupling.

Compression positive. Independent irreversible p,d; SP Table9 factors at
maximum temperature (cooling hypothesis). First-heating LITS from R9D,
optional declared synthetic Maxwell dashpot (no normative creep model).
R9E isothermal envelope recovered when LITS/dashpot disabled. All hot
ductility, cooling, hardening, localization energy and rate choices remain
hypotheses. Stop above 550 C; no implicit TKP addition or structural R.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import math
from rc_fire.mechanics import sp2026_transient_history as tr
from rc_fire.materials.normative import CONCRETE_K,CONCRETE_BETA

VERSION="SP-R9F-coupled-uniaxial-research-v1"
class DomainError(ValueError):pass

def finite(x,name):
    x=float(x)
    if not math.isfinite(x):raise DomainError(name+" must be finite")
    return x

@dataclass(frozen=True)
class Parameters:
    family:str
    fc20_MPa:float
    E20_MPa:float
    peak20:float
    yield_fraction:float
    Gwork_N_mm:float
    length_mm:float
    K:float
    viscosity_MPa_s:float|None
    provenance:str
    def validate(self):
        for k in ("fc20_MPa","E20_MPa","peak20","yield_fraction","Gwork_N_mm","length_mm","K"):
            finite(getattr(self,k),k)
        if not (self.family in CONCRETE_K and self.family in CONCRETE_BETA and
                self.fc20_MPa>0 and self.E20_MPa>0 and self.peak20>self.fc20_MPa/self.E20_MPa
                and 0<self.yield_fraction<1 and self.Gwork_N_mm>0 and self.length_mm>0
                and 0<=self.K<=2.35 and self.provenance.strip()):
            raise DomainError("explicit admissible material parameters required")
        if self.viscosity_MPa_s is not None and finite(self.viscosity_MPa_s,"viscosity")<=0:
            raise DomainError("positive declared viscosity required")
        return self

@dataclass(frozen=True)
class State:
    parameters:Parameters
    time_s:float=0.
    temperature_C:float=20.
    maximum_temperature_C:float=20.
    total_compression:float=0.
    stress_MPa:float=0.
    transient_compression:float=0.
    basic_creep_compression:float=0.
    plastic_compression:float=0.
    damage:float=0.

def initial_state(p):return State(p.validate())

def _material(p,H):
    kc=tr._interp(H,CONCRETE_K[p.family]);beta=tr._interp(H,CONCRETE_BETA[p.family])
    fc=p.fc20_MPa*kc;E=p.E20_MPa*beta
    peak=p.peak20*kc/beta # R9A explicit unvalidated hypothesis
    pp=peak-fc/E;fy=p.yield_fraction*fc
    return E,fc,fy,(fc-fy)/pp,pp,2*p.Gwork_N_mm/(p.length_mm*fc)

def _thermal(p,T,H):
    return sum(tr._thermal(p,T,H))

def _psi(E,e,z,d):
    return .5*(1-d)*E*max(0.,e-z)**2

def _return(E,fc,fy,Hk,pp,soft,e,z,d):
    """Update irreversible mechanical variables with new-temperature envelope.

    Old damage is independent of new p_peak/soft, so a changed temperature
    cannot erase or create damage solely by redefining the strain axis.
    Temperature-induced yield relaxation can still produce new plasticity.
    """
    if d==1.:return z,1.,0.,0.,"CRUSHED_RETAINED"
    q=E*max(0.,e-z);Y=min(fc,fy+Hk*z)
    if q<=Y+1e-12:
        return z,d,(1-d)*q,(1-d)*E if e>z else 0.,"ELASTIC_OR_OPEN"
    trial=(E*e-fy)/(E+Hk)
    if trial<=pp:
        zz=max(z,trial);dd=d
        tangent=(1-d)*E*Hk/(E+Hk)
        branch="HARDENING"
    else:
        start=max(z,pp)
        zz=max(z,e-fc/E)
        cap=start+(1-d)*soft
        if zz>=cap-1e-15:
            return cap,1.,0.,0.,"CRUSHED"
        dd=d+max(0.,zz-start)/soft
        tangent=-fc/soft
        branch="SOFTENING"
    return zz,dd,(1-dd)*E*max(0.,e-zz),tangent,branch

def _correction_dissipation(E,e,z,d,zz,dd,pp,soft):
    """Independent Gaussian integration of fixed-strain return correction.

    Integral sigma dp and Y dd. This is the numerical split path, not
    the actual continuous thermomechanical loading path.
    """
    start=max(z,pp)
    if zz<=z:return 0.,0.
    cuts=[z]+[a for a in (start,e) if z<a<zz]+[zz]
    cuts=sorted(set(cuts))
    Dp=Dd=0.
    for a,b in zip(cuts,cuts[1:]):
        mid=(a+b)/2;half=(b-a)/2
        for g in (-1/math.sqrt(3),1/math.sqrt(3)):
            q=mid+half*g
            dmg=min(dd,d+max(0.,q-start)/soft)
            elastic=max(0.,e-q)
            Dp+=half*(1-dmg)*E*elastic
            Dd+=half*.5*E*elastic**2*(1/soft if q>start else 0.)
    return Dp,Dd

def trial_step(s,*,time_s,temperature_C,total_compression):
    """Pure endpoint solve; guaranteed monotonic scalar bracket or refuse.

    LITS increment uses affine stress along temperature path as in R9D.
    Optional dashpot uses endpoint stress, backward Euler. Plasticity/damage
    are solved at end temperature, not updated inside root iterations.
    Sufficient global monotonicity bound 1-A fc/soft > 0; if not, report
    unresolved, never pick an arbitrary softening equilibrium.
    """
    p=s.parameters.validate();t=finite(time_s,"time");T=finite(temperature_C,"T")
    u=finite(total_compression,"total strain")
    if t<=s.time_s or not 20<=T<=550:
        raise DomainError("positive time increment and 20..550 C required")
    if not (20<=s.temperature_C<=s.maximum_temperature_C<=550 and
            0<=s.damage<=1 and min(s.stress_MPa,s.plastic_compression,
                         s.transient_compression,s.basic_creep_compression)>=0):
        raise DomainError("invalid committed history")
    H=max(T,s.maximum_temperature_C);E,fc,fy,Hk,pp,soft=_material(p,H)
    oldE=_material(p,s.maximum_temperature_C)[0]
    eth0=_thermal(p,s.temperature_C,s.maximum_temperature_C)
    eth=_thermal(p,T,H)
    oldm=s.total_compression+eth0-s.transient_compression-s.basic_creep_compression
    if abs((1-s.damage)*oldE*max(0.,oldm-s.plastic_compression)-s.stress_MPa)>1e-7:
        raise DomainError("inconsistent committed stress")
    # Reuse R9D quadrature; no mutation. Endpoint stress dependence affine.
    old=tr.State(time_s=s.time_s,temperature_C=s.temperature_C,
                 maximum_temperature_C=s.maximum_temperature_C,stress_MPa=s.stress_MPa,
                 transient_compression=s.transient_compression)
    tp=tr.Parameters(p.family,p.fc20_MPa,p.E20_MPa,p.K)
    B,_=tr._update_lits(tp,old,T,0.)
    one,_=tr._update_lits(tp,old,T,1.)
    a=max(0.,one-B)
    c=0. if p.viscosity_MPa_s is None else (t-s.time_s)/p.viscosity_MPa_s
    A=a+c
    rhs=u+eth-s.transient_compression-s.basic_creep_compression-B
    z,d=s.plastic_compression,s.damage
    if d<1. and 1-A*fc/soft<=1e-10:
        raise DomainError("nonmonotone coupled softening bound; subdivide increment or use path continuation")
    def ev(m):return _return(E,fc,fy,Hk,pp,soft,m,z,d)
    lo=rhs-A*fc-1e-14;hi=rhs+1e-14
    for _ in range(100):
        m=(lo+hi)/2
        zz,dd,sig,C,branch=ev(m)
        res=m+A*sig-rhs
        if abs(res)<=1e-14:break
        if res>0:hi=m
        else:lo=m
    else:raise DomainError("coupled local root did not converge")
    dtr,stresspath_work=tr._update_lits(tp,old,T,sig)
    dcr=c*sig
    # Recompute actual compatibility from independent R9D quadrature.
    compat=m+s.transient_compression+dtr+s.basic_creep_compression+dcr-eth-u
    if abs(compat)>1e-11:raise ArithmeticError("coupled compatibility error")
    if zz<z or dd<d or min(dtr,dcr)<-1e-14:
        raise ArithmeticError("irreversible state violated")
    # Discrete split-path energy audit: first modulus transfer, free
    # strain change, external strain change, LITS, basic creep, return.
    # These are exact potential differences for the declared artificial
    # split path, not a physical thermal/entropy or actual-path work proof.
    psi0=_psi(oldE,oldm,z,d)
    P0=_psi(E,oldm,z,d)
    m1=oldm+eth-eth0;P1=_psi(E,m1,z,d)
    m2=m1+u-s.total_compression;P2=_psi(E,m2,z,d)
    m3=m2-dtr;P3=_psi(E,m3,z,d)
    m4=m3-dcr;P4=_psi(E,m4,z,d)
    end=_psi(E,m,zz,dd)
    Dp,Dd=_correction_dissipation(E,m,z,d,zz,dd,pp,soft)
    mod=P0-psi0;eigen=P1-P0;work=P2-P1;Dtr=P2-P3;Dcr=P3-P4
    ledger=mod+eigen+work-(end-psi0)-Dtr-Dcr-Dp-Dd
    if min(Dtr,Dcr,Dp,Dd)<-1e-10 or abs(ledger)>1e-9:
        raise ArithmeticError("split-path energy balance failed")
    state=State(p,t,T,H,u,sig,s.transient_compression+dtr,
                s.basic_creep_compression+dcr,zz,dd)
    return state,{"time_s":t,"temperature_C":T,"maximum_temperature_C":H,
            "total_compression":u,"stress_MPa":sig,"mechanical_compression":m,
            "transient_compression":state.transient_compression,
            "basic_creep_compression":state.basic_creep_compression,
            "plastic_compression":zz,"damage":dd,"branch":branch,
            "effective_tangent_MPa":C/(1+A*C),"compatibility_residual":compat,
            "stored_energy_MPa":end,"modulus_transfer_MPa":mod,
            "eigenstrain_split_work_MPa":eigen,"external_split_work_MPa":work,
            "LITS_split_dissipation_MPa":Dtr,"basic_creep_split_dissipation_MPa":Dcr,
            "plastic_split_dissipation_MPa":Dp,"damage_split_dissipation_MPa":Dd,
            "LITS_affine_stress_path_work_MPa":stresspath_work,
            "basic_creep_endpoint_work_MPa":sig*dcr,
            "external_endpoint_trapezoid_MPa":.5*(s.stress_MPa+sig)*(u-s.total_compression),
            "split_energy_residual_MPa":ledger,"full_thermodynamic_qualification":False,
            "normative_claim":False}

def run_path(p,path,*,initial=None):
    s=initial_state(p) if initial is None else initial
    if s.parameters!=p:raise DomainError("parameter identity required")
    rows=[]
    for args in path:
        try:s,r=trial_step(s,**args)
        except (DomainError,ArithmeticError) as exc:
            return {"status":"UNRESOLVED_PATH_STOP","rows":rows,
                    "reason":str(exc),"blocked_point":args,"state":asdict(s)}
        rows.append(r)
    return {"status":"DIAGNOSTIC_COMPLETE","rows":rows,"state":asdict(s)}

def synthetic(K=2.35,viscosity=None):
    return Parameters("siliceous",30.,30000.,.0022,.4,5.,50.,K,viscosity,
                      "SYNTHETIC SP factors, unqualified hot strains, Gwork and dashpot")

def _path(nodes,n):
    out=[]
    for a,b in zip(nodes,nodes[1:]):
        for i in range(1,n+1):
            t,T,u=[x+(y-x)*i/n for x,y in zip(a,b)]
            out.append({"time_s":t,"temperature_C":T,"total_compression":u})
    return out

def campaign():
    runs=[]
    # Restrained point, then unload/cool/reheat. Different histories retained.
    nodes=[(0.,20.,0.),(600.,200.,0.),(1200.,400.,0.),
           (1800.,400.,.008),(2400.,200.,0.),(3000.,400.,.002),(3600.,500.,.006)]
    for K,eta in ((0.,None),(2.35,None),(2.35,1e8)):
      for n in (4,16,64):
        r=run_path(synthetic(K,eta),_path(nodes,n))
        rows=r["rows"];last=rows[-1] if rows else {}
        runs.append({"K":K,"viscosity_MPa_s":eta,"subdivisions":n,"status":r["status"],
                     "last":last,"reason":r.get("reason"),
                     "max_compatibility_residual":max((abs(x["compatibility_residual"]) for x in rows),default=0.),
                     "max_split_energy_residual":max((abs(x["split_energy_residual_MPa"]) for x in rows),default=0.),
                     "max_damage":max((x["damage"] for x in rows),default=0.),
                     "split_external_work_MPa":sum(x["external_split_work_MPa"] for x in rows),
                     "endpoint_trapezoid_work_MPa":sum(x["external_endpoint_trapezoid_MPa"] for x in rows)})
    return {"version":VERSION,"runs":runs,"parameters_fitted":0,
            "temperature_domain_C":[20,550],"full_thermodynamic_qualification":False,
            "actual_t_R_minutes":None,"normative_claim":False}
