"""SP-R10B: guarded steel history, symmetric elastic-perfectly plastic.

SP Table 10 supplies E and fy externally; SP5 §6.2.2.13 motivates the
instantaneous bilinear envelope. The return map is a research extension,
not a source-prescribed cyclic law. Compression positive, signed plastic
strain. First heating only; no creep, hardening, buckling, fatigue or
rupture. Explicit finite diagnostic strain domain is not normative eps_ud.
"""
from dataclasses import dataclass
import math

ELASTIC="ELASTIC_GUARD"
PLASTIC="EPP_HISTORY_RESEARCH"

@dataclass(frozen=True)
class SteelState:
    temperature_C:float=20.
    mechanical_strain:float=0.
    plastic_strain:float=0.
    accumulated_plastic_strain:float=0.
    stress_MPa:float=0.
    endpoint_plastic_work_MPa:float=0.

def trial(s,*,temperature_C,mechanical_strain,E_MPa,fy_MPa,mode):
    T,e,E,fy=map(float,(temperature_C,mechanical_strain,E_MPa,fy_MPa))
    if not all(math.isfinite(x) for x in (T,e,E,fy)) or not 20<=T<=800 or T<s.temperature_C-1e-8 or min(E,fy)<=0:
        raise ValueError("steel history domain: monotone 20..800 C, positive E/fy")
    if mode not in (ELASTIC,PLASTIC):raise ValueError("unknown steel history mode")
    sig0=E*(e-s.plastic_strain)
    if mode==ELASTIC or abs(sig0)<=fy:
        sig=sig0;dp=0.;C=E
    else:
        sig=math.copysign(fy,sig0)
        dp=(sig0-sig)/E;C=0.
    n=SteelState(T,e,s.plastic_strain+dp,s.accumulated_plastic_strain+abs(dp),sig,
                 s.endpoint_plastic_work_MPa+fy*abs(dp))
    return n,C,abs(sig0)/fy

def admitted(s,mode,fy,*,diagnostic_strain_limit):
    if mode==ELASTIC:return abs(s.stress_MPa)<=fy*(1+1e-10)
    if not math.isfinite(diagnostic_strain_limit) or diagnostic_strain_limit<=0:
        raise ValueError("explicit positive research strain guard required")
    return max(abs(s.mechanical_strain),s.accumulated_plastic_strain)<=diagnostic_strain_limit
