"""SP-R9E: isothermal uniaxial compression damage-plasticity research kernel.

Compression positive, tensile stress ignored. All material parameters must
be declared; no default hot ductility, yield fraction or crushing energy.
Effective-stress linear hardening followed by perfect plasticity; scalar
damage grows on the postpeak branch. This is a deliberately transparent
synthetic benchmark, NOT the Neuenschwander model, NOT an SP/TKP law.
Fixed temperature during a history; temperature-dependent parameter transfer,
LITS coupling, basic creep and multiaxial damage are not implemented here.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import math

VERSION="SP-R9E-isothermal-damage-plasticity-v1"
class DomainError(ValueError):pass

def _finite(x,name):
    x=float(x)
    if not math.isfinite(x):raise DomainError(name+" must be finite")
    return x

@dataclass(frozen=True)
class Parameters:
    temperature_C:float
    peak_stress_MPa:float
    elastic_modulus_MPa:float
    peak_strain:float
    initial_yield_fraction:float
    postpeak_work_N_mm:float
    characteristic_length_mm:float
    provenance:str
    def validate(self):
        for name in ("temperature_C","peak_stress_MPa","elastic_modulus_MPa",
                     "peak_strain","initial_yield_fraction","postpeak_work_N_mm",
                     "characteristic_length_mm"):
            _finite(getattr(self,name),name)
        if not (20<=self.temperature_C<=800 and self.peak_stress_MPa>0 and
                self.elastic_modulus_MPa>0 and self.peak_strain>self.peak_stress_MPa/self.elastic_modulus_MPa
                and 0<self.initial_yield_fraction<1 and self.postpeak_work_N_mm>0
                and self.characteristic_length_mm>0 and self.provenance.strip()):
            raise DomainError("positive admissible parameters and provenance required")
        return self
    @property
    def fy(self):return self.initial_yield_fraction*self.peak_stress_MPa
    @property
    def p_peak(self):return self.peak_strain-self.peak_stress_MPa/self.elastic_modulus_MPa
    @property
    def H(self):return (self.peak_stress_MPa-self.fy)/self.p_peak
    @property
    def p_soft(self):return 2*self.postpeak_work_N_mm/(self.characteristic_length_mm*self.peak_stress_MPa)
    @property
    def p_end(self):return self.p_peak+self.p_soft
    @property
    def end_strain(self):return self.peak_strain+self.p_soft

@dataclass(frozen=True)
class State:
    parameters:Parameters
    mechanical_compression:float=0.
    plastic_compression:float=0.
    step_index:int=0

def initial_state(p):
    return State(p.validate())

def _damage(p,z):
    return min(1.,max(0.,(z-p.p_peak)/p.p_soft))

def _stored(p,e,z):
    return .5*(1-_damage(p,z))*p.elastic_modulus_MPa*max(0.,e-z)**2

def _dissipation(p,z):
    """Cumulative analytic isothermal dissipation density in MPa.

    Plastic work integral sigma dp plus damage release Y dd.
    Peak elastic energy is released during postpeak damage; distinguish
    postpeak external work G_work from total postpeak dissipation.
    """
    pre=min(z,p.p_peak);a=max(0.,z-p.p_peak)
    d=_damage(p,z);fc=p.peak_stress_MPa;E=p.elastic_modulus_MPa
    plastic=p.fy*pre+.5*p.H*pre**2+fc*(a-.5*a*a/p.p_soft)
    damage=.5*fc*fc/E*d
    return plastic,damage

def trial_step(state,*,mechanical_compression,temperature_C):
    """Pure isothermal trial from committed state; returns state and ledger.

    Exact active-set update for piecewise linear effective yield law.
    No accumulated evolution on elastic unloading/reloading. Tension has
    zero stress and stiffness; no tension damage/reversal or fatigue model.
    No implicit TKP or LITS coupling. A material point with d=1 remains
    inactive; not evidence of global member collapse.
    """
    p=state.parameters.validate()
    e=_finite(mechanical_compression,"strain")
    if _finite(temperature_C,"temperature")!=p.temperature_C:
        raise DomainError("isothermal material state only; no hot parameter transfer")
    z=_finite(state.plastic_compression,"committed plastic strain")
    old_e=_finite(state.mechanical_compression,"committed strain")
    E=p.elastic_modulus_MPa;fc=p.peak_stress_MPa
    if not 0<=z<=p.p_end:raise DomainError("invalid committed plastic strain")
    if z<p.p_end and E*max(0.,old_e-z)>min(fc,p.fy+p.H*z)+1e-8:
        raise DomainError("committed effective stress outside yield domain")
    d0=_damage(p,z)
    q=E*max(0.,e-z);Y=min(fc,p.fy+p.H*z)
    zn=z;active=False
    if z>=p.p_end:
        tangent=0.;branch="CRUSHED_RETAINED"
    elif q<=Y:
        tangent=(1-d0)*E if e>z else 0.
        branch="ELASTIC_UNLOAD_RELOAD" if e>z else "OPEN_ZERO_TENSION"
    else:
        active=True
        if e<=p.peak_strain:
            zn=max(z,min(p.p_peak,(E*e-p.fy)/(E+p.H)))
            tangent=E*p.H/(E+p.H)
            branch="HARDENING"
        else:
            zn=max(z,min(p.p_end,e-fc/E))
            tangent=-fc/p.p_soft if zn<p.p_end else 0.
            branch="SOFTENING" if zn<p.p_end else "CRUSHED"
    # Exact endpoint state; avoid a one-ulp residual stiffness at crushing.
    if e>=p.end_strain and active:zn=p.p_end
    d=1. if zn>=p.p_end else _damage(p,zn)
    if d==1.:tangent=0.;branch="CRUSHED" if active else "CRUSHED_RETAINED"
    sigma=(1-d)*E*max(0.,e-zn)
    psi0=_stored(p,old_e,z);psi=0. if d==1. else _stored(p,e,zn)
    P0,D0=_dissipation(p,z);P,D=_dissipation(p,zn)
    deltaP=P-P0;deltaD=D-D0
    if min(deltaP,deltaD)<-1e-12:raise ArithmeticError("negative dissipation increment")
    new=State(p,e,zn,state.step_index+1)
    return new,{"temperature_C":p.temperature_C,"strain":e,"stress_MPa":sigma,
                "plastic_strain":zn,"damage":d,"unloading_modulus_MPa":(1-d)*E,
                "algorithmic_tangent_MPa":tangent,"branch":branch,
                "stored_energy_density_MPa":psi,"plastic_dissipation_density_MPa":P,
                "damage_dissipation_density_MPa":D,
                "delta_plastic_dissipation_MPa":deltaP,"delta_damage_dissipation_MPa":deltaD,
                "delta_external_work_exact_MPa":psi-psi0+deltaP+deltaD,
                "crushed_material_point":d==1.,"global_failure_proven":False,
                "normative_claim":False}

def run_history(p,strains):
    s=initial_state(p);rows=[]
    for e in strains:
        s,row=trial_step(s,mechanical_compression=e,temperature_C=p.temperature_C)
        rows.append(row)
    return {"rows":rows,"committed_state":asdict(s),"actual_t_R_minutes":None,"normative_claim":False}

def identify_unloading(*,elastic_modulus_MPa,peak_of_unload_strain,
                       peak_of_unload_stress_MPa,second_strain,second_stress_MPa):
    """Recover linear unloading slope, d and residual plastic strain.

    Both measured endpoints must be on the same positive-compression linear
    unloading branch at the same temperature. No fit to monotonic envelope.
    Reject inconsistent observations rather than clipping damage/plasticity.
    """
    E,a,s,b,t=(_finite(x,"unload input") for x in
               (elastic_modulus_MPa,peak_of_unload_strain,peak_of_unload_stress_MPa,
                second_strain,second_stress_MPa))
    if not (E>0 and a>b>=0 and s>t>=0):
        raise DomainError("two descending compression endpoints required")
    Eu=(s-t)/(a-b);d=1-Eu/E;z=a-s/Eu
    if not 0<=d<1 or z<0:
        raise DomainError("unloading observations inconsistent with model")
    return {"unloading_modulus_MPa":Eu,"damage":d,"plastic_strain":z,
            "linear_unload_assumption":True,"normative_claim":False}

def monotonic_nonidentifiability(*,elastic_modulus_MPa,strain,stress_MPa):
    """For sigma=(1-d)E(e-p), monotonic point alone cannot separate p and d."""
    E,e,s=(_finite(x,"envelope input") for x in (elastic_modulus_MPa,strain,stress_MPa))
    if not (E>0 and e>0 and 0<s<=E*e):raise DomainError("inadmissible compression point")
    return {"damage_interval":[0.,1-s/(E*e)],
            "plastic_strain_interval":[0.,e-s/E],
            "unique_damage_plasticity_identification":False}

def benchmark_parameters(T,length):
    """Synthetic ordinary concrete scenario; NOT measured or accepted inputs.

    SP table nodes for kc/beta; E0=30 GPa, reference 30 MPa; peak strain
    scales by kc/beta solely as a research hypothesis. Kinetic damage not
    inferred from heat reduction. Constant G_work and yield fraction are
    unqualified explicit controls, not temperature-dependent data.
    """
    from rc_fire.materials.normative import FIRE_TEMP,CONCRETE_K,CONCRETE_BETA
    i=FIRE_TEMP.index(float(T))
    kc=CONCRETE_K["siliceous"][i];beta=CONCRETE_BETA["siliceous"][i]
    return Parameters(float(T),30*kc,30000*beta,.0022*kc/beta,.4,5.,float(length),
                      "SYNTHETIC SP factors, fixed G_work=5 N/mm and yield fraction=.4")

def benchmark_campaign():
    rows=[];cycles=[]
    for T in (20.,400.,600.,800.):
      for l in (25.,50.,100.):
        p=benchmark_parameters(T,l)
        # Exact branch nodes, plus independent midpoint trapezoidal integration
        # of piecewise-linear monotonic stress; not the constitutive ledger.
        strains=[0.,p.fy/p.elastic_modulus_MPa,p.peak_strain,
                 p.peak_strain+.5*p.p_soft,p.end_strain]
        h=run_history(p,strains)["rows"]
        peak=h[2];end=h[-1]
        G=l*sum(.5*(a["stress_MPa"]+b["stress_MPa"])*(b["strain"]-a["strain"])
                for a,b in zip(h[2:],h[3:]))
        w=l*sum(r["delta_external_work_exact_MPa"] for r in h[3:])
        diss=l*((end["plastic_dissipation_density_MPa"]+end["damage_dissipation_density_MPa"])-
                (peak["plastic_dissipation_density_MPa"]+peak["damage_dissipation_density_MPa"]))
        rows.append({"T_C":T,"length_mm":l,"peak_stress_MPa":p.peak_stress_MPa,
                     "peak_strain":p.peak_strain,"crushing_strain":p.end_strain,
                     "postpeak_external_work_N_mm":G,"ledger_postpeak_work_N_mm":w,
                     "postpeak_total_dissipation_N_mm":diss,
                     "released_peak_elastic_energy_N_mm":l*.5*p.peak_stress_MPa**2/p.elastic_modulus_MPa,
                     "end_damage":end["damage"]})
        if l==50:
            half=p.peak_strain+.5*p.p_soft
            residual=p.p_peak+.5*p.p_soft
            c=run_history(p,[0.,p.peak_strain,half,residual,half,p.end_strain,0.,half])
            cycles.append({"T_C":T,"history":c["rows"]})
    return {"version":VERSION,"regularization":rows,"cycles":cycles,
            "synthetic_cases":len(rows),"primary_cyclic_curves_admitted":0,
            "parameters_fitted":0,"isothermal_only":True,
            "global_failure_proven":False,"actual_t_R_minutes":None,"normative_claim":False}
