"""R0.6.4C: fail-closed sampled ULS audit for heated beam-columns.

A finite-element equilibrium alone is not verification of ultimate resistance.
This file evaluates the *available numerical evidence* at every Gauss point
and at both sides of all element boundaries, PROVIDED separately prepared
nodal section laws exist. It never represents its finite point sampling as a
normative continuous-in-z ULS or R90 certificate.

Sources: СП 5.03.01-2020 §8.1.2.1–8.1.2.4; СП 2.02.05-2026
§8.2.18–8.2.20. Missing criteria remain explicit blockers.
"""
from __future__ import annotations
import math
import numpy as np

from .coupled import CoupledMemberError, _shape, _finite_vector
from rc_fire.normative.actions import action_source, ACTION_INPUT_CONTRACT

VERSION = 'R0.6.4C-ULS-evidence-audit-v1'


def _summarize_state(st:dict):
    if st.get('critical_mechanical_strain_ratio') is not None:
        # Temperature-dependent eps_cu(theta) varies by fibre under TKP.
        # The R0.6.3 single ambient eps_cu2 is invalid for TKP hot concrete.
        # A gap in the Table 3.1 law *cannot* produce positive ULS evidence.
        if st.get('constitutive_domain_qualified') is not True:
            return {'limit_check':'unavailable','ratio_concrete':None,
                    'ratio_steel':None,'maximum_ratio':None}
        try: ratio=float(st['critical_mechanical_strain_ratio'])
        except (TypeError,ValueError):ratio=math.nan
        if not math.isfinite(ratio) or ratio<0:
            return {'limit_check':'invalid','ratio_concrete':None,
                    'ratio_steel':None,'maximum_ratio':None}
        return {'limit_check':'exceeded' if ratio>1.+1e-8 else 'within_diagnostic_limits',
                'ratio_concrete':None,'ratio_steel':None,'maximum_ratio':ratio}
    ec = st.get('max_concrete_compressive_strain')
    es = st.get('max_steel_tensile_strain')
    limc = st.get('eps_cu2')
    lims = st.get('tensile_steel_limit')
    if st.get('section_model')=='nonlinear_R063C_fibres_with_explicit_eigenstrains' and st.get('corner_eigenstrain_explicit') is not True:
        return {'limit_check':'unavailable','ratio_concrete':None,'ratio_steel':None,'maximum_ratio':None}
    if ec is None or es is None or limc is None or lims is None:
        return {'limit_check':'unavailable', 'ratio_concrete':None,
                'ratio_steel':None,'maximum_ratio':None}
    vals=[float(v) for v in (ec,es,limc,lims)]
    if not all(math.isfinite(x) for x in vals) or vals[2]<=0 or vals[3]<=0:
        return {'limit_check':'invalid','ratio_concrete':None,
                'ratio_steel':None,'maximum_ratio':None}
    rc=max(0.,vals[0])/vals[2]
    rs=max(0.,vals[1])/vals[3]
    # Equality to specified strain bounds is admitted, exceeding them is not.
    return {'limit_check':'exceeded' if max(rc,rs)>1.+1.e-8 else 'within_diagnostic_limits',
            'ratio_concrete':rc,'ratio_steel':rs,'maximum_ratio':max(rc,rs)}


def _node_curvature(result,z,i,side):
    """Hermite element endpoint curvature; interior nodes have two distinct sides."""
    nodes=len(z)
    ei=i-1 if side=='left' else i
    if not 0<=ei<nodes-1:raise CoupledMemberError('invalid endpoint side')
    t=1. if side=='left' else 0.
    h=z[ei+1]-z[ei]
    _,_,hpp=_shape(t,h)
    out=[]
    for axis in ('x','y'):
        w=_finite_vector(result[f'w_{axis}_m'],(nodes,),f'w_{axis}_m')
        rot=_finite_vector(result[f'theta_{axis}_rad'],(nodes,),f'theta_{axis}_rad')
        de=np.array([w[ei],rot[ei],w[ei+1],rot[ei+1]])
        out.append(-float(hpp@de))
    return np.asarray(out)


def audit_heated_member_uls(result:dict,z_m,N_kN:float,*,
                            node_laws=None, action_provenance=None,
                            material_provenance=None,
                            temperature_time_minutes=None,
                            axial_restraint_qualified=False,
                            spalling_qualified=False):
    """Evaluate **diagnostic** ULS evidence for every existing FE integration point.

    node_laws: one actual section law per mesh node (not an interpolated or
    borrowed Gauss law). At interior nodes, both adjacent curvatures are tested
    against the same explicit node law. If absent, critical end sections are
    unassessed and the returned coverage flag is false.

    action_provenance/material_provenance are separately supplied traceability
    records and can never promote this diagnostic to a normative R(t) claim.
    """
    z=_finite_vector(z_m,name='z_m')
    if z.ndim!=1 or len(z)<2 or abs(z[0])>1e-12 or np.any(np.diff(z)<=0):
        raise CoupledMemberError('valid monotonically increasing stations required')
    nodes=len(z);N=float(N_kN)
    if not math.isfinite(N) or N<0:raise CoupledMemberError('N must be finite compression')
    if temperature_time_minutes is not None and (not math.isfinite(float(temperature_time_minutes)) or float(temperature_time_minutes)<0):
        raise CoupledMemberError('invalid time')
    # Project convention: all explicit N/M are already fire-design actions.
    # A redundant source field is not an independent qualification gate.
    action_provenance=action_source(action_provenance)
    blockers=[]
    if not material_provenance:blockers.append('HOT_MATERIAL_LAW_NOT_QUALIFIED')
    if not axial_restraint_qualified:blockers.append('AXIAL_RESTRAINT_OR_RELEASE_NOT_QUALIFIED')
    if not spalling_qualified:blockers.append('SPALLING_NOT_QUALIFIED')
    blockers.extend(['CONTINUOUS_MEMBER_ULS_NOT_QUALIFIED','FULL_FIRE_R_T_NOT_IMPLEMENTED'])
    status=result.get('status')
    if status not in ('evaluated_diagnostic','strain_limits_exceeded_diagnostic'):
        return {'version':VERSION,'status':'MODEL_NOT_SOLVED',
                'model_status':status,'blockers':sorted(set(blockers+['SECTION_EQUILIBRIUM_NOT_DEMONSTRATED'])),
                'normative_claim':False,'fire_resistance_status':'not_demonstrated'}
    states=result.get('integration_stations')
    if not isinstance(states,list) or len(states)!=3*(nodes-1):
        blockers.append('GAUSS_STATION_EVIDENCE_INCOMPLETE')
        states=[]
    sampled=[]
    for i,st in enumerate(states):
        evidence={**_summarize_state(st),'location':'gauss',
                  'z_m':float(st['z_m']),'element':i//3,
                  'moments_kNm':st.get('moments_kNm'),
                  'material_model':st.get('section_model'),
                  'strength_reference':st.get('reference_strength_mode')}
        sampled.append(evidence)
    node_coverage=node_laws is not None
    if node_coverage:
        if len(node_laws)!=nodes or any(l is None for l in node_laws):
            raise CoupledMemberError('exactly one explicit law for each node required')
        for i,law in enumerate(node_laws):
            for side in (('right',) if i==0 else ('left',) if i==nodes-1 else ('left','right')):
                kappa=_node_curvature(result,z,i,side)
                try: M,D,meta=law.evaluate(kappa,N)
                except (ValueError,ArithmeticError,np.linalg.LinAlgError) as exc:
                    blockers.append('NODE_SECTION_EQUILIBRIUM_NOT_RESOLVED')
                    sampled.append({'location':'node','z_m':float(z[i]),'side':side,
                        'limit_check':'invalid','reason':str(exc)})
                    continue
                D=_finite_vector(D,(2,2),'nodal tangent')
                if np.linalg.eigvalsh((D+D.T)/2)[0]<=0:
                    blockers.append('NODE_SECTION_TANGENT_NOT_POSITIVE')
                st={'max_concrete_compressive_strain':meta.get('max_concrete_compressive_strain'),
                    'max_steel_tensile_strain':meta.get('max_steel_tensile_strain'),
                    'eps_cu2':meta.get('eps_cu2'),
                    'tensile_steel_limit':meta.get('tensile_steel_limit'),
                    'section_model':meta.get('model'),
                    'corner_eigenstrain_explicit':meta.get('corner_eigenstrain_explicit'),
                    'critical_mechanical_strain_ratio':meta.get('critical_mechanical_strain_ratio'),
                    'constitutive_domain_qualified':meta.get('constitutive_domain_qualified')}
                sampled.append({**_summarize_state(st),'location':'node',
                  'z_m':float(z[i]),'side':side,'moments_kNm':np.asarray(M).tolist(),
                  'strength_reference':meta.get('reference_strength_mode'),
                  'material_model':meta.get('model')})
    else:blockers.append('END_AND_INTERIOR_NODES_NOT_ASSESSED')
    invalid=[s for s in sampled if s['limit_check'] in ('unavailable','invalid')]
    exceeded=[s for s in sampled if s['limit_check']=='exceeded']
    if invalid:blockers.append('LOCAL_STRAIN_LIMIT_INFORMATION_MISSING')
    if result.get('any_strain_limit_exceeded') or exceeded:
        code='DIAGNOSTIC_STRAIN_LIMIT_EXCEEDED'
    elif invalid or not node_coverage:
        code='INSUFFICIENT_ULS_EVIDENCE'
    else:
        code='SAMPLED_STRAINS_WITHIN_LIMITS_NOT_NORMATIVE_ULS'
    finite_ratios=[s for s in sampled if s.get('maximum_ratio') is not None]
    critical=max(finite_ratios,key=lambda s:s['maximum_ratio']) if finite_ratios else None
    return {'version':VERSION,'status':code,'model_status':status,
      'temperature_time_minutes':temperature_time_minutes,'sampled_locations':len(sampled),
      'gauss_count':len(states),'node_side_count':len(sampled)-len(states),
      'node_coverage':node_coverage,'all_sampled_limits_resolved':not invalid,
      'exceeded_count':len(exceeded),'critical_sample':critical,
      'numerical_second_order_tangent_min_eigenvalue':result.get('tangent_min_eigenvalue'),
      'equilibrium_relative_residual':result.get('relative_equilibrium_residual'),
      'action_provenance':action_provenance,
       'fire_action_input_contract':ACTION_INPUT_CONTRACT,
       'material_provenance':material_provenance,
      'blockers':sorted(set(blockers)),'samples':sampled,
      'normative_claim':False,'fire_resistance_status':'not_demonstrated'}
