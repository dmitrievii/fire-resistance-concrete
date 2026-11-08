"""R0.6.9C — fire-time action-path reserve of sections and an optional member.

Section route directly uses *all* entered fire-design N, Mx, My at each
longitudinal section; no moments are silently converted to beam loads.
Member route independently uses explicit user-supplied N and distributed
transverse q, end supports and uniform longitudinal heating assumption, with
nonlinear fibre sections, P-delta and node/Gauss strain auditing.

These are two DISTINCT load paths. Their factors are NOT interchangeable.
Fire material and full continuous member strength remain unqualified; no R(t).
"""
from __future__ import annotations

import copy
import hashlib
import json
import math

import numpy as np

from rc_fire.mechanics.action_capacity import (
    WITHIN, EXCEEDED, UNKNOWN, scan_prepared_section, scan_action_path)
from rc_fire.mechanics.normative import prepare_section, SectionMechanicsError
from rc_fire.mechanics.fire_strength import select_fire_reference_strength, LITERAL
from rc_fire.member.time_scan import timeline_points
from rc_fire.thermal import evaluate_rectangular_column
from rc_fire.integration.r064d import (
    _signature, _validate_station_bundle, MemberEvidenceInputError)
from rc_fire.integration.r067 import (
    build_uniform_fire_bundle, validate_member_spec)
from rc_fire.member.coupled import (
    EndSupport, CoupledMemberError, heated_laws_from_explicit_thermal_stations,
    solve_coupled_beam)
from rc_fire.member.full_uls import _node_law_from_explicit_station
from rc_fire.member.uls import audit_heated_member_uls
from rc_fire.mechanics.fire_material_audit import audit_fire_material_stations

VERSION='R0.6.9C-section-and-member-action-path-v1'
R_STATUS='not_demonstrated'


def _finite(v,label,*,positive=False):
    if isinstance(v,bool):
        raise ValueError(f'{label}: boolean not allowed')
    try: n=float(v)
    except (TypeError,ValueError) as exc:
        raise ValueError(f'{label}: finite number required') from exc
    if not math.isfinite(n) or (positive and n<=0):
        raise ValueError(f'{label}: nonfinite or nonpositive')
    return n


def _action_sections(column):
    sections=column.get('sections')
    if not isinstance(sections,list) or not sections:
        raise ValueError('at least one actual fire-design action section required')
    out=[]
    zmax=_finite(column.get('length_m'),'length_m',positive=True)
    ids=set()
    for i,s in enumerate(sections):
        if not isinstance(s,dict):
            raise ValueError(f'sections[{i}]: object required')
        ident=str(s.get('id','')).strip()
        if not ident or ident in ids:
            raise ValueError('unique, nonempty section identifiers required')
        ids.add(ident)
        z=_finite(s.get('z_m'),f'{ident}.z_m')
        if z<0 or z>zmax:
            raise ValueError(f'{ident}: section outside member length')
        out.append({'id':ident,'z_m':z,
            'N_kN':_finite(s.get('N_kN'),f'{ident}.N_kN',positive=True),
            'Mx_kNm':_finite(s.get('Mx_kNm'),f'{ident}.Mx_kNm'),
            'My_kNm':_finite(s.get('My_kNm'),f'{ident}.My_kNm')})
    return out


def _member_load_path_at_time(column, thermal, *, factor_step,max_factor,max_bisection):
    """Independent nonlinear second-order beam action path, NEVER N-M table fit."""
    base={'status':'BLOCKED_INPUT','model':'nonlinear_two_axis_member_P_delta',
          'normative_claim':False,'fire_resistance_status':R_STATUS,
          'lambda_capacity_normative':None,'R_t_minutes':None,
          'entered_section_Mx_My_used_as_member_loads':False,
          'entered_section_moments_reconciled_with_explicit_q':False,
          'member_action_source':'constant N plus explicit qx,qy; no section moment inference',
          'blockers':[]}
    try:
        bundle=build_uniform_fire_bundle(column,thermal=thermal)
        z,n,grid=_validate_station_bundle(bundle,expected_column=column)
        spec=validate_member_spec(column.get('member_spec'))
        left=EndSupport(spec['left_support']);right=EndSupport(spec['right_support'])
        gauss=heated_laws_from_explicit_thermal_stations(
            bundle['gauss_stations'],grid=grid,
            accept_integration_convention=True,strength_mode=LITERAL)
        glaws=[[gauss['law_at_gauss'](i,j) for j in range(3)]
               for i in range(len(z)-1)]
        nlaws=[_node_law_from_explicit_station(e,grid=grid,strength_mode=LITERAL)
               for e in bundle['node_stations']]
        material_audit=audit_fire_material_stations(
            [p for row in glaws for p in row]+nlaws)
        q=np.asarray(bundle['distributed_load_kNpm'],dtype=float)
        if q.shape!=(len(z),2) or not np.all(np.isfinite(q)):
            raise ValueError('invalid independent member q array')
    except (MemberEvidenceInputError,SectionMechanicsError,
            CoupledMemberError,ValueError,KeyError,TypeError,IndexError) as exc:
        return {**base,'status':'BLOCKED_MEMBER_PATH_OR_MATERIAL',
                'blockers':['EXPLICIT_MEMBER_PATH_OR_SUPPORTED_MATERIAL_REQUIRED'],
                'reason':str(exc)}
    def evaluate(lam):
        # FibreSectionLaw caches an axial seed; fresh copies prevent one lambda
        # from numerically contaminating another independent equilibrium test.
        local=copy.deepcopy(glaws)
        nodes=copy.deepcopy(nlaws)
        r=solve_coupled_beam(z,n*lam,
            law_at_gauss=lambda i,j:local[i][j],left=left,right=right,
            distributed_load_kNpm=q*lam)
        status=r.get('status','unresolved')
        if status not in ('evaluated_diagnostic','strain_limits_exceeded_diagnostic'):
            return {'classification':UNKNOWN,'model_status':status,
                    'reason':r.get('reason') or 'member equilibrium/tangent unresolved'}
        uls=audit_heated_member_uls(r,z,n*lam,node_laws=nodes,
            temperature_time_minutes=float(column['fire_minutes']))
        if (uls.get('node_coverage') is not True
            or uls.get('all_sampled_limits_resolved') is not True
            or uls.get('gauss_count') != 3*(len(z)-1)
            or 'NODE_SECTION_TANGENT_NOT_POSITIVE' in uls.get('blockers',())):
            state=UNKNOWN
        elif (status=='strain_limits_exceeded_diagnostic'
              or (uls.get('status')=='DIAGNOSTIC_STRAIN_LIMIT_EXCEEDED'
                  and uls.get('exceeded_count',0)>0)):
            state=EXCEEDED
        elif uls.get('status')=='SAMPLED_STRAINS_WITHIN_LIMITS_NOT_NORMATIVE_ULS':
            state=WITHIN
        else:
            state=UNKNOWN
        critical=uls.get('critical_sample') or {}
        return {'classification':state,'model_status':uls.get('status'),
                'critical_ratio':critical.get('maximum_ratio'),
                'reason':'Gauss plus both-sided node strain audit; no continuous ULS proof'}
    try:
        scan=scan_action_path(evaluate,max_factor=max_factor,
               factor_step=factor_step,max_bisection=max_bisection)
    except (ValueError,TypeError) as exc:
        return {**base,'status':'BLOCKED_CAPACITY_SCAN','blockers':['INVALID_CAPACITY_SCAN'],
                'reason':str(exc)}
    has_m=any(abs(float(s[k]))>1e-10 for s in column['sections']
              for k in ('Mx_kNm','My_kNm'))
    return {**base,**scan,'status':'MEMBER_LOAD_PATH_SCAN_DIAGNOSTIC',
        'node_count':len(z),'gauss_count':3*(len(z)-1),
        'reference_axial_N_kN':n,'reference_transverse_q_kNpm':q.tolist(),
        'left_support':spec['left_support'],'right_support':spec['right_support'],
        'has_nonzero_user_section_moments':has_m,
        'reference_member_model_requires_section_M_reconciliation':has_m,
        'section_M_comparison':'NOT_PERFORMED_MEMBER_CAPACITY_NOT_FOR_ENTERED_MX_MY'
                             if has_m else 'NO_NONZERO_SECTION_MOMENTS_ENTERED',
        'thermal_longitudinal_assumption':bundle['r067_assumptions'],
        'initial_imperfection': 'none_supplied_not_normatively_qualified',
        'material_audit_status':material_audit['status'],
        'blockers':sorted(set([
            'MEMBER_GEOMETRIC_IMPERFECTIONS_NOT_QUALIFIED',
            'CONTINUOUS_SECOND_ORDER_ULS_NOT_QUALIFIED',
            'HOT_CONSTITUTIVE_LAW_UNQUALIFIED',
            'REFERENCE_ACTION_PATTERN_NOT_RECONCILED' if has_m else
                'AXIAL_ONLY_SECTION_ACTION_PATTERN',
            *material_audit['blockers']])),
        'normative_claim':False,'fire_resistance_status':R_STATUS}


def evaluate_fire_action_capacity_at_time(column, *, grid=12,max_factor=2.,
                 factor_step=.5,max_bisection=4,include_member=True):
    """Compute BOTH separately identified mechanical models at exactly one time."""
    base={'version':VERSION,'status':'BLOCKED_INPUT',
        'normative_claim':False,'fire_resistance_status':R_STATUS,
        'R_t_minutes':None,'lambda_capacity_normative':None,
        'fire_minutes':column.get('fire_minutes') if isinstance(column,dict) else None,
        'sections':[],'member':None,'blockers':[]}
    try:
        if not isinstance(column,dict):
            raise ValueError('column must be an object')
        if type(grid) is not int or not 12<=grid<=64:
            raise ValueError('grid must be an integer in 12..64')
        _finite(column.get('fire_minutes'),'fire_minutes',positive=True)
        sections=_action_sections(column)
    except (ValueError,TypeError) as exc:
        return {**base,'status':'BLOCKED_INPUT','blockers':['INCOMPLETE_DESIGN_ACTIONS'],
                'reason':str(exc)}
    thermal=evaluate_rectangular_column(column,grid=grid)
    if thermal.get('status') not in ('evaluated','evaluated_with_scope_warnings'):
        return {**base,'status':'BLOCKED_THERMAL',
            'blockers':['ANNEX_K_NOT_RESOLVED'],'reason':str(
                thermal.get('reason') or thermal.get('missing') or thermal.get('status'))}
    critical=thermal.get('critical_section') or {}
    reduced_area=(critical.get('remaining_area_m2')
                  if critical.get('status')=='evaluated' else None)
    base={**base,'annex_K_status':thermal['status'],
          'temperature_max_C':thermal.get('max_temperature_C'),
          'steel_temperature_max_C':max((float(b['theta_C']) for b in
              thermal.get('reinforcement',[])),default=None),
          'K27_area_m2_geometry_only':reduced_area}
    try:
        pre=prepare_section(column,thermal,grid=grid,above_800_policy='reject')
        pre,reference=select_fire_reference_strength(pre,mode=LITERAL)
    except (SectionMechanicsError,ValueError,KeyError,TypeError) as exc:
        return {**base,'status':'BLOCKED_SECTION_MATERIAL_DOMAIN',
            'blockers':['SECTION_MATERIAL_TEMPERATURE_UNSUPPORTED'],
            'reason':str(exc)}
    report=[]
    for section in sections:
        path=scan_prepared_section(pre,section['N_kN'],section['Mx_kNm'],
            section['My_kNm'],max_factor=max_factor,
            factor_step=factor_step,max_bisection=max_bisection)
        report.append({'section_id':section['id'],'z_m':section['z_m'],
                       'entered_fire_design_actions':{
                           k:section[k] for k in ('N_kN','Mx_kNm','My_kNm')},
                       'action_path':path,
                       'at_design_actions':path['design_action_evidence']})
    classes=[s['at_design_actions']['classification'] for s in report]
    state=('SAMPLED_SECTION_STRAIN_EXCEEDANCE' if EXCEEDED in classes
        else 'SAMPLED_SECTIONS_WITHIN_DIAGNOSTIC_LIMITS' if
             classes and all(x==WITHIN for x in classes)
        else 'UNRESOLVED_SECTION_STRAIN_STATE')
    member=_member_load_path_at_time(column,thermal,
        factor_step=factor_step,max_factor=max_factor,max_bisection=max_bisection) \
        if include_member else None
    return {**base,'status':state,'sections':report,'member':member,
        'design_action_sections_count':len(report),
        'section_material_strength_reference':reference,
        'thermal_free_strains_in_section_solver':False,
        'second_order_effects_in_section_solver':False,
        'member_path_independent_from_entered_Mx_My':True,
        'blockers':[
            'SECTION_THERMAL_EIGENSTRAINS_NOT_INCLUDED',
            'HOT_MATERIAL_STRESS_STRAIN_UNQUALIFIED',
            'SECOND_ORDER_NOT_INCLUDED_IN_DIRECT_SECTION_SOLVER',
            'FULL_MEMBER_ULS_NOT_QUALIFIED',
            'NUMERICAL_SCAN_NOT_PROOF_OF_FIRST_FAILURE_TIME',
        ],'normative_claim':False,'fire_resistance_status':R_STATUS}


def evaluate_fire_action_capacity_history(column, *, step_minutes=30.,
                 start_minutes=1.,max_factor=2.,factor_step=.5,
                 max_bisection=4,grid=12,include_member=True,max_time_points=12):
    """Fresh thermal + action-path scans at each time, with no extrapolated R(t)."""
    if not isinstance(column,dict):
        raise ValueError('column object required')
    _action_sections(column)  # Catch missing design actions at the entry boundary.
    times=timeline_points(column.get('fire_minutes'),step_minutes=step_minutes,
                          start_minutes=start_minutes,max_points=max_time_points)
    signature=hashlib.sha256(_signature(column).encode('utf-8')).hexdigest()
    rows=[]
    for t in times:
        c=copy.deepcopy(column)
        c['fire_minutes']=t
        try:
            r=evaluate_fire_action_capacity_at_time(c,grid=grid,
                max_factor=max_factor,factor_step=factor_step,
                max_bisection=max_bisection,include_member=include_member)
        except (ValueError,KeyError,TypeError,RuntimeError) as exc:
            r={'status':'UNRESOLVED_EXCEPTION','reason':f'{type(exc).__name__}: {exc}',
               'sections':[],'member':None}
        groups=[s['at_design_actions']['classification'] for s in r.get('sections',[])]
        section_class=(EXCEEDED if EXCEEDED in groups else
                 WITHIN if groups and all(x==WITHIN for x in groups) else UNKNOWN)
        mm=r.get('member')
        member_class=(mm.get('design_action_evidence',{}).get('classification',UNKNOWN)
                      if isinstance(mm,dict) else None)
        rows.append({'time_minutes':t,'status':r.get('status'),
            'section_classification_at_lambda_1':section_class,
            'member_classification_at_lambda_1':member_class,
            'K27_area_m2_geometry_only':r.get('K27_area_m2_geometry_only'),
            'temperature_max_C':r.get('temperature_max_C'),
            'steel_temperature_max_C':r.get('steel_temperature_max_C'),
            'section_count':len(r.get('sections',[])),
            'section_load_factors':[
                {'id':s['section_id'],
                 'observed_transition_brackets':s['action_path'][
                    'transition_brackets_diagnostic'],
                 'reference_state':s['at_design_actions']['classification']}
                for s in r.get('sections',[])],
            'member_action_path_brackets': (
                mm.get('transition_brackets_diagnostic',[]) if isinstance(mm,dict) else []),
            'member_action_pattern_reconciled':False if
                isinstance(mm,dict) and mm.get('has_nonzero_user_section_moments')
                else None,
            'reason':r.get('reason'),
            'normative_claim':False,
            'fire_resistance_status':R_STATUS})
    observed=[
        {'sampled_within_minutes':a['time_minutes'],
         'sampled_exceeded_minutes':b['time_minutes'],
         'proves_normative_failure':False}
        for a,b in zip(rows,rows[1:])
        if (a['section_classification_at_lambda_1']==WITHIN
            and b['section_classification_at_lambda_1']==EXCEEDED)]
    return {'version':VERSION,'status':'DIAGNOSTIC_CAPACITY_TIME_HISTORY',
        'column_id':column.get('id'),
        'column_signature_sha256':signature,
        'source_fire_design_actions_used_without_recombination':True,
        'section_model':'first_order_biaxial_N_Mx_My',
        'member_model':'second_order_N_plus_explicit_q_only' if include_member else 'not_evaluated',
        'member_section_moment_equivalence_not_inferred':True,
        'samples':rows,'sample_count':len(rows),
        'observed_section_reference_transitions_minutes':observed,
        'unresolved_times_minutes':[s['time_minutes'] for s in rows
            if s['section_classification_at_lambda_1']==UNKNOWN],
        'R_t_minutes':None,'lambda_capacity_normative':None,
        'normative_claim':False,'fire_resistance_status':R_STATUS,
        'blockers':['CONTINUOUS_N_M_MEMBER_ULS_NOT_QUALIFIED',
            'HEATED_CONSTITUTIVE_AND_THERMAL_EIGENSTRAIN_LAWS_UNQUALIFIED',
            'FULL_TEMPERATURE_DOMAIN_ABOVE_800_C_UNRESOLVED',
            'INITIAL_IMPERFECTION_AND_RESTRAINT_QUALIFICATION_MISSING',
            'NUMERICAL_ACTION_PATH_SAMPLING_NOT_NORMATIVE_R_T'],
        'interpretation':'First-order fire-design section N/M interaction and a separate '
             'explicit member N+q FE load path. Sampled bounds are not normative '
             'capacities; no failure time is inferred across unknown timestamps.'}
