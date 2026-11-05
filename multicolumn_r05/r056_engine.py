"""R0.5.6 structural audit and checks for RC columns in standard fire.

The EXACT K18 Mathcad replay remains in calculation_engine.py.
This module extends the four-face thermal model to bar-coordinate meshes and
performs (a) shared member slenderness/demand envelope, (b) a *numerical*
3-variable strain-plane equilibrium for simultaneous N, Mx, My, and (c) the
the SP468 tabular F method plus the separately labelled manual K18 index.

These are DIFFERENT method/provenance classes. They are not normative approval
and must never be displayed as certified R90. When inputs are missing, reports
must state NOT EVALUATED, not PASS.
"""
from __future__ import annotations

import math
from typing import Any
import numpy as np

from multicolumn_r05.parametric_engine import (
    GeneralInput, concrete_grid, temperature_field, factor,
    STEEL_K500, STEEL_BETA500,
)

SPALLING_FIELDS = (
    'alpha_F', 'alpha_bt_per_C', 'beta_E', 'E_c_MPa',
    'rho_kg_m3', 'W_e_volume_fraction', 'K_1C', 'lambda_250_W_mK',
    'n_p_percent',
)
SPALLING_UNITS = {
    'alpha_F': 'Вт·м^(5/2)/кг (как в исходном отчёте)',
    'alpha_bt_per_C': '1/°C',
    'beta_E': 'безразмерный коэффициент',
    'E_c_MPa': 'МПа',
    'rho_kg_m3': 'кг/м³',
    'W_e_volume_fraction': 'м³/м³',
    'K_1C': 'МН·м^(-3/2)',
    'lambda_250_W_mK': 'Вт/(м·°C)',
    'n_p_percent': '% (значение 10 означает 10%)',
}


def spalling_assessment(data: dict | None) -> dict:
    """SP468 table-based F or the manually parameterized K18 analogue.

    For manual K18, lambda has first power and n_p_percent is divided by
    100 in the denominator. Previously saved values are not silently certified.
    SP468 uses own source, B class and material-mix data with no placeholders.
    """
    data = data or {}
    from multicolumn_r05.sp468 import assessment as sp468_assessment
    if data.get('method') == 'sp468' or (not data.get('method') and not any(k in data for k in SPALLING_FIELDS)):
        return sp468_assessment(data)
    if data.get('method') not in (None, 'manual_k18'):
        return {'status':'invalid', 'F':None, 'error':'Неизвестный метод оценки хрупкого разрушения', 'source_type':'unknown'}
    missing = [name for name in SPALLING_FIELDS
               if data.get(name) is None or data.get(name) == '']
    result = {
        'method': 'K18 report §3.4 equation (3.4.1), Annex K citation; user-entered coefficients',
        'formula': 'F=(alpha_F*alpha_bt*beta_E*E_c*rho*W_e)/(K_1C*lambda_250*(n_p_percent/100))',
        'source_type':'K18_manual_provisional',
        'threshold': 4.0, 'units': SPALLING_UNITS,
        'status': 'not_evaluated', 'F': None, 'missing': missing,
        'claim_of_fire_resistance': False,
    }
    if missing:
        return result
    vals = {}
    for key in SPALLING_FIELDS:
        try:
            value = float(data[key])
        except (ValueError, TypeError):
            result.update(status='invalid',error=f'{key}: требуется числовое значение')
            return result
        if not math.isfinite(value) or value <= 0:
            result.update(status='invalid',error=f'{key}: требуется конечное положительное значение')
            return result
        vals[key] = value
    numer = vals['alpha_F']*vals['alpha_bt_per_C']*vals['beta_E']*vals['E_c_MPa']*vals['rho_kg_m3']*vals['W_e_volume_fraction']
    den = vals['K_1C']*vals['lambda_250_W_mK']*(vals['n_p_percent']/100.0)
    F = numer/den
    if not math.isfinite(F):
        return {**result, 'status': 'invalid', 'error': 'F: переполнение численного диапазона'}
    return {**result, 'F': F,
            'status': 'protection_required' if F > 4.0 else 'index_at_or_below_threshold',
            'missing': [], 'input_values': vals}


def member_envelope(column: dict, computed_variants: dict) -> dict:
    """Conservative whole-column Nmax/Ncr-min amplification *diagnostic*.

    Uses the same eta=1/(1-N/Ncr) form as original K18. Unlike old R0.5
    per-load-section eta, takes Nmax across all computed sections to form a
    shared column envelope. This is not a spatially resolved second-order
    differential equilibrium, nor a validated national member method.
    """
    result = {'method': 'K18 eta formula, shared member envelope (Nmax / min Ncr)',
              'status': 'not_evaluated', 'Nmax_kN': None, 'axes': {},
              'sections': {}, 'worst': None, 'member_solver': 'conservative_uniform-amplification_diagnostic'}
    if not computed_variants:
        return result
    Nmax = max(float(v['N_kN']) for v in computed_variants.values())
    result['Nmax_kN'] = Nmax
    for axis in ('x','y'):
        ncr_min = min(float(v['axes'][axis]['N_cr_kN']) for v in computed_variants.values())
        if not (math.isfinite(ncr_min) and ncr_min > Nmax and Nmax > 0):
            result['status'] = 'instability_or_invalid'
            result['axes'][axis] = {'Ncr_min_kN': ncr_min, 'eta_member': None}
        else:
            result['axes'][axis] = {'Ncr_min_kN': ncr_min,
                                     'eta_member': 1/(1-Nmax/ncr_min)}
    scores=[]
    for sid,v in computed_variants.items():
        byaxis={}
        for axis in ('x','y'):
            a=v['axes'][axis]
            eta=result['axes'][axis]['eta_member']
            m0=float(a['M0_kNm'])
            N=float(v['N_kN'])
            ea=float(a['imperfection_e_m'])
            m_ed=(abs(m0)+N*ea)*eta if eta is not None else math.inf
            mrd=float(a['M_Rd_kNm'])
            use=m_ed/mrd if mrd>0 else math.inf
            direction = -1.0 if m0<0 else 1.0
            row={'M_Ed_kNm': m_ed, 'M_Ed_signed_kNm': direction*m_ed,
                 'M_Rd_kNm': mrd, 'utilization': use, 'eta_member': eta,
                 'N_kN': N}
            byaxis[axis]=row
            scores.append({'section_id':sid, 'axis':axis, 'u':use})
        result['sections'][sid]=byaxis
    result['worst']=max(scores,key=lambda r:r['u']) if scores else None
    if result['status'] != 'instability_or_invalid':
        result['status']='evaluated'
    return result


def _prepared_bars(spec: GeneralInput, variant: Any) -> dict[str, np.ndarray]:
    bx,by,As,k,beta=[],[],[],[],[]
    for bar in variant.bars:
        T=float(temperature_field(spec,bar.x_m,bar.y_m,bar.diameter_mm/1000))
        bx.append(bar.x_m-spec.b_m/2)
        by.append(bar.y_m-spec.h_m/2)
        As.append(math.pi*(bar.diameter_mm/1000)**2/4)
        k.append(factor(T,STEEL_K500))
        beta.append(factor(T,STEEL_BETA500))
    return {'x':np.asarray(bx,dtype=float), 'y':np.asarray(by,dtype=float),
            'a':np.asarray(As,dtype=float), 'k':np.asarray(k,dtype=float),
            'beta':np.asarray(beta,dtype=float)}


def solve_biaxial_equilibrium(spec:GeneralInput, mesh:dict,
                               variant:Any, Mx_kNm:float, My_kNm:float,
                               *,max_iter:int=80) -> dict:
    """Numerical simultaneous N/Mx/My axial equilibrium under plane sections.

    E*strain capped to ±fy(T) for steel and [0,fc] for compression-only
    concrete. Uses the same constitutive assumptions as the R0.4 fiber model.
    An equilibrium is diagnostic; no national code-defined interaction theorem
    or temperature-dependent concrete plasticity has been established.
    """
    result={'method':'2D fiber strain-plane equilibrium, N+Mx+My, experimental',
            'status':'not_converged','equilibrium':False,'within_strain_limit':False,
            'normative_claim':False,'Mx_demand_kNm':float(Mx_kNm),
            'My_demand_kNm':float(My_kNm),'N_demand_kN':float(variant.N_kN)}
    coords=np.column_stack([np.ones(len(mesh['x'])),mesh['y'],mesh['x']])
    steel=_prepared_bars(spec,variant)
    s_coords=np.column_stack([np.ones(len(steel['x'])),steel['y'],steel['x']])
    fc=spec.f_ck_MPa
    ec=spec.E_cm_GPa*1000/1.2
    es=spec.E_s_GPa*1000*steel['beta']
    fy=spec.f_y_MPa*steel['k']
    steel_a=steel['a']
    area=mesh['a']
    target=np.array([float(variant.N_kN),float(Mx_kNm),float(My_kNm)])
    if not np.all(np.isfinite(target)):
        result['status']='invalid_demand';return result
    Nmax=(len(mesh['x'])*area*fc + np.dot(steel_a,fy))*1000
    result['Nmax_nominal_kN']=float(Nmax)
    if target[0]>Nmax*(1+1e-9) or target[0]<-float(np.dot(steel_a,fy))*1000*(1+1e-9):
        result['status']='axial_capacity_outside';return result

    def eval_state(q, with_jac=True):
        cstrain=coords@q
        sstrain=s_coords@q
        c_unclipped=ec*cstrain
        sigma_c=np.clip(c_unclipped,0,fc)
        sigma_s=np.clip(es*sstrain,-fy,fy)
        forces=(coords.T @ sigma_c)*area*1000 + (s_coords.T @ (sigma_s*steel_a))*1000
        if not with_jac:return forces
        Kc=ec*area*1000 * ((c_unclipped>0)&(c_unclipped<fc))
        Ks=es*steel_a*1000 * ((es*sstrain >-fy)&(es*sstrain<fy))
        J=coords.T@(coords*Kc[:,None]) + s_coords.T@(s_coords*Ks[:,None])
        return forces,J,cstrain,sstrain

    # Work with force/length-scaled equations to avoid ill-conditioning.
    scale=np.array([max(abs(target[0]),1000),max(abs(target[1]),20),max(abs(target[2]),20)])
    # Initial strain based on elastic stiffness of effective concrete + steel.
    q=np.zeros(3)
    ecst=ec*area*1000
    J0=ecst*coords.T@coords + s_coords.T@(s_coords*(es*steel_a*1000)[:,None])
    try:q=np.linalg.solve(J0+np.eye(3)*1e-10,target)
    except np.linalg.LinAlgError:pass
    best=None
    best_norm=math.inf
    for it in range(max_iter):
        force,J,cstrain,sstrain=eval_state(q)
        res=force-target
        err=float(np.linalg.norm(res/scale))
        if err<best_norm:
            best_norm=err;best=(q.copy(),force.copy(),it)
        if err<2e-6:
            maxeps=float(np.max(cstrain))
            passed=maxeps<=.0035+1e-8
            result.update({'status':'equilibrium_within_strain' if passed else 'concrete_strain_exceeded',
                           'equilibrium':True,'within_strain_limit':passed,
                           'residual_norm':err,'iterations':it,
                           'eps0':float(q[0]), 'kappa_x_1_m':float(q[1]),'kappa_y_1_m':float(q[2]),
                           'eps_c_max':maxeps,
                           'forces_kN_kNm':force.tolist(),
                           's_steel_strain_max':float(np.max(np.abs(sstrain)))})
            return result
        try:
            step=np.linalg.solve(J+np.diag([1e-7,1e-9,1e-9]),res)
        except np.linalg.LinAlgError:
            step=np.linalg.lstsq(J+np.diag([1e-5,1e-7,1e-7]),res,rcond=1e-10)[0]
        if not np.all(np.isfinite(step)):break
        # Damped Newton; never convert non-convergence into a positive result.
        improved=False
        for decay in (.9,.5,.2,.08,.02,.005):
            trial=q-decay*step
            if np.linalg.norm((eval_state(trial,False)-target)/scale) < err:
                q=trial;improved=True;break
        if not improved:break
    result['residual_norm']=best_norm
    result['iterations']=best[2] if best is not None else 0
    result['status']='equilibrium_not_found'
    return result


def enrich_with_biaxial(spec:GeneralInput,computed_variants:dict,member:dict):
    """Return section-wise simultaneous checks using member-amplified actions."""
    if not computed_variants or member.get('status')!='evaluated':
        return {'status':'not_evaluated','sections':{},'reason':'Member envelope unavailable'}
    mesh=concrete_grid(spec)
    byvar={v.id:v for v in spec.variants}
    sections={}
    for sid in computed_variants:
        target=member['sections'][sid]
        sections[sid]=solve_biaxial_equilibrium(spec,mesh,byvar[sid],
            target['x']['M_Ed_signed_kNm'], target['y']['M_Ed_signed_kNm'])
    statuses={x['status'] for x in sections.values()}
    status='evaluated' if statuses.issubset({'equilibrium_within_strain','concrete_strain_exceeded'}) else 'partial'
    return {'status':status,'sections':sections,
            'method':'experimental fiber equilibrium under shared member envelope',
            'normative_claim':False,
            'warnings':['Numerical 2D equilibrium is NOT a national-code biaxial capacity interaction verification',
                        'Member eta envelope is not a spatially coupled second-order solver']}


def check_provenance() -> dict:
    """Document which parts reproduce original XMCD and which do not."""
    return {
        'legacy_k18': 'calculation_engine.compute: frozen legacy worksheet replay; 44 archived scalars matched',
        'generalized_thermal': 'four-sided K18 thermal expression per-bar + discretized 500 C concrete, experimental extrapolation',
        'member': 'eta=1/(1-N/Ncr) from K18, Nmax/Ncrmin member envelope (new conservative extension)',
        'biaxial': 'new 2D strain-plane force equilibrium with R0.4 material assumptions; NOT the original XMCD',
        'spalling': 'Russian SP468 §9.7 tables 9.1-9.6 and F limits 4/6; K18 manual formula separately retained with corrected lambda power and porosity units',
        'certification': False,
    }