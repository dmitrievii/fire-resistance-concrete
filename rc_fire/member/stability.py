"""R0.6.4 MEMBER stability candidate: Belarus RC fire calculation.

NORMATIVE REFERENCES, ambient only:
SP 5.03.01-2020 §5.4.4-5.4.6 (5.1)-(5.4), §8.1.6.2-8.1.6.6
(8.54)-(8.64) and §8.1.6.10. Stiffness (8.56) must not be used
as fire stiffness without a separately qualified thermal constitutive law.

The pin-pin finite-difference model is an INDEPENDENT NUMERICAL DIAGNOSTIC,
not the normative §8.1.6 method. It solves the two uncoupled geometric
P-Delta axes with externally furnished positive-definite bending stiffness.
It does NOT resolve non-linear heated constitutive curves, restraints,
concrete creep during fire, spalling, cross-section ULS or a R(t) verdict.
This module must NEVER return a 'PASS' fire resistance status.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite, pi, sqrt
from typing import Sequence
import numpy as np

VERSION = 'R0.6.4-member-diagnostic-candidate'

class MemberInputError(ValueError):
    pass

def _finite_pos(value, name: str) -> float:
    try: x=float(value)
    except (TypeError, ValueError) as exc: raise MemberInputError(f'{name}: finite positive required') from exc
    if not isfinite(x) or x<=0: raise MemberInputError(f'{name}: finite positive required')
    return x

_END_FACTORS = {
    # literal common isolated-member cases of §8.1.6.6; NOT universal frame values
    'pinned_pinned':1.0,
    'fixed_free':2.0,
    'pinned_fixed_non_sway':0.7,
    'pinned_partially_fixed_non_sway':0.9,
    'fixed_fixed_non_sway':0.5,
    'partially_fixed_both_non_sway':0.8,
    'fixed_fixed_limited_sway':0.8,
    'partially_fixed_both_limited_sway':1.2,
    'partially_pinned_fixed_sway':1.5,
    'partially_pinned_partially_fixed_sway':2.0,
}

def effective_length(length_m:float, *, condition:str | None=None,
                     k:float | None=None)->dict:
    """§8.1.6.6 isolated-column effective-length cases; no guessed supports."""
    L=_finite_pos(length_m,'length_m')
    if (condition is None) == (k is None):
        raise MemberInputError('Provide exactly one of condition or explicit k')
    if condition is not None:
        if condition not in _END_FACTORS: raise MemberInputError('Unsupported support condition')
        factor=_END_FACTORS[condition]; source='SP 5.03.01-2020 §8.1.6.6'
    else:
        factor=_finite_pos(k,'effective_length_factor')
        source='user_specified_not_independently_verified'
    return {'length_m':L,'effective_length_m':L*factor,'factor':factor,
            'support_condition':condition,'provenance':source,
            'normative_claim':False}

def imperfection_eccentricity(length_m:float, effective_length_m:float,
                              *, method:str='theta', m:int=1)->dict:
    """§5.4.4 (5.1)-(5.3), §5.4.6 (5.4): ei=theta_i*l0/2.

    `l/400` option limited to individual columns in braced systems as
    explicitly allowed in §5.4.6, NOT a universal imperfection.
    """
    L=_finite_pos(length_m,'length_m');L0=_finite_pos(effective_length_m,'effective_length_m')
    if method=='braced_column_l0_over_400':
        return {'e_i_m':L0/400.,'theta_i_rad':None,'method':method,
                'conditions':'individual column in braced system (SP §5.4.6)',
                'normative_claim':False}
    if method!='theta':raise MemberInputError('Unsupported imperfection method')
    if not isinstance(m,int) or m<1:raise MemberInputError('m must be a positive integer')
    alpha_h=min(1.0,max(2./5.,2./sqrt(L)))
    alpha_m=sqrt(.5*(1+1/m))  # SP 5.03.01-2020 (5.3)
    theta=alpha_h*alpha_m/200.
    return {'e_i_m':theta*L0/2.,'theta_i_rad':theta,'alpha_h':alpha_h,
            'alpha_m':alpha_m,'method':method,'normative_claim':False}

@dataclass(frozen=True)
class NominalStiffnessInput:
    fck_MPa:float
    fcd_MPa:float
    N_kN:float
    Ac_m2:float
    Ic_m4:float
    Is_m4:float
    Ecm_MPa:float
    Es_MPa:float
    effective_length_m:float
    phi_eff:float|None  # §8.1.6.5 externally determined; no invented creep

def nominal_stiffness(data:NominalStiffnessInput)->dict:
    """SP 5.03.01-2020 (8.55)-(8.62): ambient nominal-stiffness baseline.

    N and stiffness of one chosen bending axis. Fire stiffness is NOT
    established by this ambient formula; never promote output to fire PASS.
    """
    fck=_finite_pos(data.fck_MPa,'fck');fcd=_finite_pos(data.fcd_MPa,'fcd')
    N=_finite_pos(data.N_kN,'N_kN');Ac=_finite_pos(data.Ac_m2,'Ac_m2')
    Ic=_finite_pos(data.Ic_m4,'Ic_m4');Es=_finite_pos(data.Es_MPa,'Es_MPa')
    Ecm=_finite_pos(data.Ecm_MPa,'Ecm_MPa');L0=_finite_pos(data.effective_length_m,'l0')
    Is=float(data.Is_m4)
    if not isfinite(Is) or Is<0:raise MemberInputError('Is_m4 must be non-negative')
    if data.phi_eff is None:raise MemberInputError('phi_eff must be explicitly calculated/provided')
    phi=float(data.phi_eff)
    if not isfinite(phi) or phi<0:raise MemberInputError('phi_eff must be non-negative')
    # MPa * m^4 * 1000 = kN*m²
    i=sqrt(Ic/Ac)
    slenderness=L0/i
    n=N/(1000*Ac*fcd)
    k1=sqrt(fck/20.) # (8.59): critical square root verified in PDF
    k2=min(.20,n*slenderness/170.) # (8.60)
    kc=k1*k2/(1+phi) # (8.58)
    Bc=kc*(Ecm/1.2)*Ic*1000
    Bs=Es*Is*1000
    B=Bc+Bs
    if B<=0:raise MemberInputError('Bnom not positive')
    Ncrit=pi*pi*B/(L0*L0)
    nratio=N/Ncrit
    return {'slenderness':slenderness,'n':n,'k1a':k1,'k2a':k2,'kc':kc,
            'Bnom_kNm2':B,'B_concrete_kNm2':Bc,'B_steel_kNm2':Bs,
            'Ncrit_kN':Ncrit,'N_over_Ncrit':nratio,
            'eta_a':1/(1-nratio) if nratio<1 else None,
            'status':'stable_nominal' if nratio<1 else 'critical_or_beyond',
            'method':'SP 5.03.01-2020 ambient §8.1.6 (8.54)-(8.62)',
            'fire_stiffness_qualified':False,'normative_claim':False}

def slenderness_screen(*, N_kN:float, Ac_m2:float, Ic_m4:float,
                       effective_length_m:float, fcd_MPa:float,
                       phi_eff:float|None=None, omega:float|None=None,
                       moment_ratio:float|None=None,
                       moment_case:str='end_moments')->dict:
    """SP 5.03.01-2020 §8.1.6.10 (8.68)-(8.74), AMBIENT ONLY.

    The norm supplies defaults if phi/omega/moment ratio are unknown.
    For force from predominantly imperfections/transverse load or for
    unbraced element, pass moment_case='imperfections_or_transverse_or_unbraced'
    to set r_m=1 per §8.1.6.10. The output never certifies R90.
    """
    N=_finite_pos(N_kN,'N_kN')
    Ac=_finite_pos(Ac_m2,'Ac_m2');Ic=_finite_pos(Ic_m4,'Ic_m4')
    L0=_finite_pos(effective_length_m,'l0');fcd=_finite_pos(fcd_MPa,'fcd')
    n=N/(1000.*Ac*fcd)
    lam=L0/sqrt(Ic/Ac)
    if phi_eff is None:aN=.7
    else:
        phi=float(phi_eff)
        if not isfinite(phi) or phi<0:raise MemberInputError('phi_eff must be nonnegative')
        aN=1/(1+.2*phi)
    if omega is None:bN=1.1
    else:
        w=float(omega)
        if not isfinite(w) or w<0:raise MemberInputError('omega must be nonnegative')
        bN=sqrt(1+2*w)
    if moment_case=='imperfections_or_transverse_or_unbraced':cN=.7
    elif moment_case=='end_moments':
        if moment_ratio is None:cN=.7
        else:
            rm=float(moment_ratio)
            if not isfinite(rm) or abs(rm)>1+1e-10:
                raise MemberInputError('moment_ratio= M01/M02 with |M02| >= |M01|')
            cN=1.7-rm
    else:raise MemberInputError('Unknown moment_case')
    lam_lim=20*aN*bN*cN/sqrt(n)
    return {'lambda':lam,'lambda_lim':lam_lim,
            'second_order_may_be_ignored_ambient':bool(lam<lam_lim),
            'n':n,'aN':aN,'bN':bN,'cN':cN,
            'source':'SP 5.03.01-2020 §8.1.6.10 (8.68)-(8.74)',
            'fire_qualification':False,'normative_claim':False}

def amplify_moment(M0_kNm:float, N_kN:float, Ncrit_kN:float)->dict:
    """§8.1.6.2 amplified eccentricity/moment sensitivity (not R90)."""
    M=float(M0_kNm)
    if not isfinite(M):raise MemberInputError('Moment must be finite')
    N=_finite_pos(N_kN,'N');Nc=_finite_pos(Ncrit_kN,'Ncrit')
    if N>=Nc:
        return {'status':'critical_or_beyond','M_second_kNm':None,
                'eta':None,'normative_claim':False}
    return {'status':'amplified','M_second_kNm':M/(1-N/Nc),
            'eta':1/(1-N/Nc),'normative_claim':False}

def second_order_pin_pin(z_m:Sequence[float], M0_kNm:Sequence[float],
                         N_kN:float, B_kNm2:Sequence[float],
                         *, thermal_curvature_1pm:Sequence[float]|None=None)->dict:
    """Diagnostic P-Delta finite-difference boundary-value solve, one axis.

    w'' + (N/B) w = -M0/B + k_thermal, w(0)=w(L)=0,
    M_total(z)=M0(z)+N*w(z). z must be uniform, N is positive compression.
    B(z) is an explicitly provided POSITIVE tangent/nominal stiffness profile,
    not automatically derived from unqualified R0.6.3C material laws.
    Thermal curvature is external, optional, and NOT generated from Annex K.
    This is an idealised pin-pin model with no shear deformation.
    """
    z=np.asarray(z_m,dtype=float);M=np.asarray(M0_kNm,dtype=float)
    B=np.asarray(B_kNm2,dtype=float)
    N=float(N_kN)
    if z.ndim!=1 or len(z)<5 or z.shape!=M.shape or z.shape!=B.shape:
        raise MemberInputError('z/M/B must be 1D equal-length arrays, at least 5 stations')
    if not np.all(np.isfinite(z)) or not np.all(np.isfinite(M)) or not np.all(np.isfinite(B)) or not isfinite(N):
        raise MemberInputError('Non-finite member input')
    if N<0 or np.any(B<=0): raise MemberInputError('N>=0, B>0 required')
    dz=np.diff(z)
    if np.any(dz<=0) or not np.allclose(dz,dz[0],rtol=1e-9,atol=1e-12) or z[0]!=0.:
        raise MemberInputError('z must be uniformly spaced, starting at zero')
    if thermal_curvature_1pm is None: kth=np.zeros_like(z)
    else:
        kth=np.asarray(thermal_curvature_1pm,dtype=float)
        if kth.shape!=z.shape or not np.all(np.isfinite(kth)):
            raise MemberInputError('Invalid thermal curvature profile')
    # Difference boundary-value operator has first instability at
    # 4 sin²(pi/(2(n-1))) / dz² * B for constant B; inspect smallest
    # eigenvalue via symmetric similarity transform when B varies.
    h=float(dz[0]);q=N/B[1:-1]
    lap=np.diag(np.full(len(q),2./h**2)-q)
    off=-np.full(len(q)-1,1./h**2)
    lap+=np.diag(off,1)+np.diag(off,-1)
    eigen_min=float(np.linalg.eigvalsh(lap)[0])
    if eigen_min<=1e-10:
        return {'status':'critical_or_beyond','w_m':None,'M_total_kNm':None,
                'stability_eigenvalue':eigen_min,
                'normative_claim':False,'fire_resistance_status':'not_demonstrated'}
    rhs=M[1:-1]/B[1:-1]-kth[1:-1]
    w=np.zeros(len(z));w[1:-1]=np.linalg.solve(lap,rhs)
    Mt=M+N*w
    return {'status':'evaluated_diagnostic', 'w_m':w.tolist(),
            'M_total_kNm':Mt.tolist(),
            'max_displacement_m':float(np.max(np.abs(w))),
            'max_abs_M_total_kNm':float(np.max(np.abs(Mt))),
            'stability_eigenvalue':eigen_min,
            'method':'diagnostic_fd_pin_pin_geometric_PDelta',
            'thermal_curvature_source':'externally_specified_not_qualified' if thermal_curvature_1pm is not None else 'zero_assumed_diagnostic',
            'normative_claim':False,'fire_resistance_status':'not_demonstrated'}

def evaluate_member_diagnostic(z_m, N_kN, Mx_first_kNm, My_first_kNm,
                               Bx_kNm2, By_kNm2, *,
                               kth_x_1pm=None,kth_y_1pm=None)->dict:
    """Evaluate both bending directions with separate member BVPs.
    Assumes P-Delta directionally uncoupled; section N-Mx-My ULS
    MUST be evaluated separately at all stations with a qualified law.
    """
    x=second_order_pin_pin(z_m,Mx_first_kNm,N_kN,Bx_kNm2,
                           thermal_curvature_1pm=kth_x_1pm)
    y=second_order_pin_pin(z_m,My_first_kNm,N_kN,By_kNm2,
                           thermal_curvature_1pm=kth_y_1pm)
    return {'status':'evaluated_diagnostic' if x['status']==y['status']=='evaluated_diagnostic' else 'blocked',
            'axis_x':x,'axis_y':y,'normative_claim':False,
            'fire_resistance_status':'not_demonstrated',
            'missing_qualification':['thermal constitutive tangent stiffness',
                'thermal eigenstrain profile', 'combined section/member ULS',
                'loads and fire combination', 'supports and member instability beyond pin-pin',
                'spalling and fire failure time']}

def section_checks_at_stations(member_result:dict, z_m:Sequence[float],
                               prepared_section_by_station:dict[float,object],
                               N_kN:float, *, solver=None)->dict:
    """Couple R0.6.4 P-Delta moments to R0.6.3C first-order section solver.

    Every section must have its own qualified/prepared thermal inventory.
    Missing sections BLOCK the diagnostic coupling (no interpolation of hot
    materials along z). An equilibrium result is not a fire ULS verification.
    """
    z=np.asarray(z_m,dtype=float)
    x=member_result.get('axis_x',{});y=member_result.get('axis_y',{})
    if member_result.get('status')!='evaluated_diagnostic':
        return {'status':'blocked','reason':'member_second_order_not_evaluated',
                'normative_claim':False,'fire_resistance_status':'not_demonstrated'}
    Mx=np.asarray(x['M_total_kNm'],dtype=float)
    My=np.asarray(y['M_total_kNm'],dtype=float)
    if z.ndim!=1 or z.shape!=Mx.shape or z.shape!=My.shape:
        raise MemberInputError('Station positions incompatible with member output')
    if solver is None:
        from rc_fire.mechanics.normative import solve_load as solver
    station_results=[]
    for i,zi in enumerate(z):
        # Only explicitly available, not inferred thermal sections qualify.
        if float(zi) not in prepared_section_by_station:
            return {'status':'blocked','reason':f'No prepared section at z={zi}',
                    'checked_stations':len(station_results),
                    'normative_claim':False,'fire_resistance_status':'not_demonstrated'}
        result=solver(prepared_section_by_station[float(zi)],float(N_kN),
                      float(Mx[i]),float(My[i]))
        station_results.append({'z_m':float(zi),'Mx_total_kNm':float(Mx[i]),
                                'My_total_kNm':float(My[i]),'mechanics':result})
    return {'status':'evaluated_diagnostic', 'stations':station_results,
            'all_equilibria_solved':all(r['mechanics'].get('equilibrium',False)
                                       for r in station_results),
            'normative_claim':False,'fire_resistance_status':'not_demonstrated',
            'missing_qualification':['heated constitutive laws, member ULS, R(t)']}
