"""R0.6.9D2 — TKP first-order heated-section and optional P-Delta member pathway.

Independent from SP §8.2.18 mechanics. This is NOT an R90/R(t) assertion.
Thermal field: SP 2.02.05-2026 Annex K (explicitly labelled hybrid until
the EN §4.3.2 heat-transfer route is qualified). Fire-design N/M actions
are used exactly as entered without recombination.

For the actual K18 JSON, hot/cold bar process and ductility are not stated;
the strict Eurocode route must remain BLOCKED rather than assume them.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math

import numpy as np

from rc_fire.thermal import evaluate_rectangular_column
from rc_fire.mechanics.action_capacity import WITHIN,EXCEEDED,UNKNOWN
from rc_fire.mechanics.tkp_thermomechanical_fibres import (
    VERSION as FIBRE_VERSION,
    TKPFibreInputError,prepare_tkp_fibres)
from rc_fire.materials.tkp_en1992_fire import EurocodeFireMaterialError,qualification
from rc_fire.integration.r069c import _action_sections
from rc_fire.integration.r067 import build_uniform_fire_bundle
from rc_fire.integration.r064d import MemberEvidenceInputError
from rc_fire.member.coupled import EndSupport,solve_coupled_beam,CoupledMemberError
from rc_fire.member.uls import audit_heated_member_uls
from rc_fire.member.time_scan import timeline_points

VERSION='R0.6.9D2-TKP-section-and-P-delta-adapter-v1'
UNQUALIFIED='not_demonstrated'


def _without_rating(data):
    return {**data,'R_t_minutes':None,'lambda_capacity_normative':None,
            'normative_claim':False,'fire_resistance_status':UNQUALIFIED}


def _member_from_tkp(column,thermal,*,grid,production_route,
                     ductility_class,high_temperature_tail):
    """Explicit N+q member loads only; no fabrication of a moment diagram."""
    base=_without_rating({'status':'BLOCKED_MEMBER_INPUT','blockers':[],
            'entered_Mx_My_reconciled_with_member_actions':False,
            'member_load_pattern':'N + explicitly declared qx/qy',
            'model':'TKP_thermal_fibre_sections_plus_existing_P_delta_beam',
            'node_uls_audit':None})
    try:
        bundle=build_uniform_fire_bundle(column,thermal=thermal)
        z=np.asarray(bundle['z_m'],dtype=float)
        N=float(bundle['N_kN'])
        q=np.asarray(bundle['distributed_load_kNpm'],dtype=float)
        if q.shape!=(len(z),2):
            raise TKPFibreInputError('member load array invalid')
        laws=[]
        for row in bundle['gauss_stations']:
            if len(row)!=3:
                raise TKPFibreInputError('every element requires 3 Gauss sections')
            laws.append([prepare_tkp_fibres(
                column,e['thermal'],grid=grid,
                production_route=production_route,
                ductility_class=ductility_class,
                high_temperature_tail=high_temperature_tail).member_law()
                for e in row])
        node_laws=[prepare_tkp_fibres(column,e['thermal'],grid=grid,
            production_route=production_route,ductility_class=ductility_class,
            high_temperature_tail=high_temperature_tail).member_law()
            for e in bundle['node_stations']]
        spec=column['member_spec']
        result=solve_coupled_beam(z,N,law_at_gauss=lambda i,j:laws[i][j],
            left=EndSupport(spec['left_support']),
            right=EndSupport(spec['right_support']),
            distributed_load_kNpm=q)
        if result.get('status') in ('evaluated_diagnostic','strain_limits_exceeded_diagnostic'):
            aud=audit_heated_member_uls(result,z,N,node_laws=node_laws,
                material_provenance={'tkp_fire_laws':FIBRE_VERSION},
                temperature_time_minutes=float(column['fire_minutes']))
        else:
            aud={'status':'MODEL_NOT_SOLVED',
                 'reason':result.get('reason') or result.get('status')}
        out=_without_rating({**base,
            'status':'MEMBER_EQUILIBRIUM_DIAGNOSTIC' if
                  result.get('status') in
                     ('evaluated_diagnostic','strain_limits_exceeded_diagnostic')
                  else 'MEMBER_EQUILIBRIUM_UNRESOLVED',
            'model_status':result.get('status'),
            'second_order_result':result,
            'node_uls_audit':aud,
            'source_thermal_assumption':bundle['r067_assumptions'],
            'bar_process':production_route,'steel_ductility':ductility_class,
            'blockers':[
                'MEMBER_ACTION_DIAGRAM_NOT_RECONCILED_WITH_ENTERED_Mx_My',
                'BEAM_GEOMETRIC_IMPERFECTIONS_NOT_DEFINED',
                'HEAT_TRANSFER_NOT_EN1992_4_3_2_QUALIFIED',
                'TKP_4_3_4_EXPERIMENTAL_VALIDATION_MISSING',
                'SPALLING_AND_TRANSIENT_CREEP_NOT_QUALIFIED']})
        return out
    except (MemberEvidenceInputError,TKPFibreInputError,EurocodeFireMaterialError,
            CoupledMemberError,ValueError,TypeError,KeyError,IndexError) as exc:
        return {**base,'reason':str(exc),
                'blockers':['EXPLICIT_MEMBER_ACTIONS_SUPPORTS_OR_TKP_MATERIAL_NOT_RESOLVED']}


def evaluate_tkp_fire_mechanics_at_time(column,*,grid=12,
        production_route=None,ductility_class=None,
        high_temperature_tail='reject',max_factor=2.,
        factor_step=.5,max_bisection=3,include_member=False):
    """Full TKP N/M fibres at one Annex K time; independently sourced inputs.

    Explicit declarations are required; optional hot tail is diagnostics only.
    The response of this combination of independently derived thermal and
    stress-strain methods remains unqualified until physical validation.
    """
    base=_without_rating({'version':VERSION,'status':'BLOCKED_INPUT',
        'section_model':FIBRE_VERSION,'fire_minutes':(
            column.get('fire_minutes') if isinstance(column,dict) else None),
        'steel_production_route':production_route,
        'steel_ductility_class':ductility_class,
        'high_temperature_tail':high_temperature_tail,
        'sections':[],'member':None,'blockers':[],
        'thermal_method':'СП 2.02.05-2026 приложение К (hybrid with TKP)'})
    if not isinstance(column,dict):
        return {**base,'reason':'column dictionary required'}
    try:
        actions=_action_sections(column)
        thermal=evaluate_rectangular_column(column,grid=grid)
        if thermal.get('status') not in ('evaluated','evaluated_with_scope_warnings'):
            return {**base,'status':'BLOCKED_THERMAL',
                    'reason':str(thermal.get('reason') or thermal.get('status'))}
        temperatures={str(x['id']):float(x['theta_C'])
                      for x in thermal.get('reinforcement',[])}
        th_data={'annex_K_status':thermal['status'],
                 'thermal_issues':list(thermal.get('issues') or []),
                 'bar_temperatures_C':temperatures,
                 'K27_area_m2_geometry_only':(thermal.get('critical_section') or {}).get(
                     'remaining_area_m2')}
        if production_route not in ('hot_rolled','cold_worked') or \
           ductility_class not in ('A','B','C'):
            return {**base,**th_data,'status':'BLOCKED_REBAR_DECLARATION',
                'reason':'Must declare actual reinforcing steel production route and '
                         'ductility class. S500 and weldable_bar are insufficient.',
                'blockers':['STEEL_PROCESS_AND_DUCTILITY_NOT_DEFINED']}
        p=prepare_tkp_fibres(column,thermal,grid=grid,
            production_route=production_route,ductility_class=ductility_class,
            high_temperature_tail=high_temperature_tail)
        report=[]
        for s in actions:
            scan=p.load_factor_scan(s['N_kN'],s['Mx_kNm'],s['My_kNm'],
                max_factor=max_factor,factor_step=factor_step,
                max_bisection=max_bisection)
            reference=scan['design_action_evidence']
            report.append({'id':s['id'],'z_m':s['z_m'],
                'entered_fire_design_actions':{
                    k:s[k] for k in ('N_kN','Mx_kNm','My_kNm')},
                'reference_at_lambda_1':reference,
                'sampled_action_path':scan})
        classes=[r['reference_at_lambda_1']['classification'] for r in report]
        state=('SAMPLED_TKP_STRAIN_EXCEEDED' if EXCEEDED in classes else
               'SAMPLED_TKP_STRAIN_WITHIN_LIMITS_DIAGNOSTIC' if
                    classes and all(x==WITHIN for x in classes) else
               'TKP_SECTION_STATE_UNRESOLVED')
        member=(_member_from_tkp(column,thermal,grid=grid,
            production_route=production_route,ductility_class=ductility_class,
            high_temperature_tail=high_temperature_tail)
            if include_member else None)
        return _without_rating({**base,**th_data,
            'status':state,'sections':report,'member':member,
            'tkp_material_source':qualification(),
            'boundary_temperature_max_C':p.boundary_max_C,
            'boundary_strain_domain_gap':p.boundary_gap,
            'hot_concrete_fibre_gap_count':p.hot_fibre_count,
            'thermomechanical_eigenstrains_in_fibre_section':True,
            'newton_equilibrium_is_not_true_failure':True,
            'source_thermal_mix_not_normatively_adjudicated':True,
            'blockers':[
                'SP_ANNEX_K_THERMAL_NOT_EUROCODE_ADVANCED_HEAT_TRANSFER',
                'MATERIAL_1100_1200_EPS_ENDPOINTS_MISSING' if
                    p.boundary_gap or p.hot_fibre_count else
                    'NO_HIGH_TEMP_STRAIN_GAP_AT_THIS_TIME',
                'SECTION_FIRST_ORDER_ONLY',
                'INDEPENDENT_LOAD_PATH_NOT_FULL_MEMBER_MX_MY',
                'SPALLING_TRANSIENT_CREEP_NOT_QUALIFIED',
                'TKP_4_3_4_VALIDATION_NOT_DONE',
            ]})
    except (ValueError,TypeError,KeyError,TKPFibreInputError,
            EurocodeFireMaterialError) as exc:
        return {**base,'status':'BLOCKED_TKP_MATERIAL_OR_ACTIONS',
                'reason':str(exc),
                'blockers':['CONSTITUTIVE_SOURCE_OR_ACTION_UNRESOLVED']}


def evaluate_tkp_fire_mechanics_history(column,*,production_route=None,
        ductility_class=None,step_minutes=30.,start_minutes=1.,grid=12,
        high_temperature_tail='reject',max_factor=1.,factor_step=1.,
        max_bisection=0,include_member=False,max_time_points=12):
    """Independent thermal+TKP mechanical recomputation. No R(t) interpolation."""
    if not isinstance(column,dict):
        raise ValueError('column dictionary required')
    _action_sections(column)
    times=timeline_points(column.get('fire_minutes'),step_minutes=step_minutes,
        start_minutes=start_minutes,max_points=max_time_points)
    rows=[]
    for t in times:
        col=copy.deepcopy(column)
        col['fire_minutes']=t
        r=evaluate_tkp_fire_mechanics_at_time(col,grid=grid,
            production_route=production_route,ductility_class=ductility_class,
            high_temperature_tail=high_temperature_tail,
            max_factor=max_factor,factor_step=factor_step,
            max_bisection=max_bisection,include_member=include_member)
        states=[x['reference_at_lambda_1']['classification']
                for x in r.get('sections',[])]
        rows.append({
            'time_minutes':t,
            'status':r['status'],
            'reference_classification':EXCEEDED if EXCEEDED in states else
                WITHIN if states and all(x==WITHIN for x in states) else UNKNOWN,
            'hot_boundary_C':r.get('boundary_temperature_max_C'),
            'bar_temperatures_C':r.get('bar_temperatures_C'),
            'source_boundary_gap':r.get('boundary_strain_domain_gap'),
            'section_evidence':[
                {'section_id':v['id'],
                 'at_lambda_1':v['reference_at_lambda_1'],
                 'numerical_transition_brackets':v['sampled_action_path'][
                     'transition_brackets_diagnostic']}
                 for v in r.get('sections',[])],
            'member_status':(r.get('member') or {}).get('status'),
            'reason':r.get('reason'),
            'normative_claim':False})
    return _without_rating({
        'version':VERSION,'status':'UNQUALIFIED_TKP_THERMOMECHANICAL_TIME_SCAN',
        'column_id':column.get('id'),
        'steel_production_route':production_route,
        'steel_ductility_class':ductility_class,
        'high_temperature_tail':high_temperature_tail,
        'samples':rows,'time_points_count':len(rows),
        'first_normative_failure_minute':None,
        'scope':'SP Annex K thermal + TKP EN1992 fire constitutive material; not a single '
                'qualified advanced-thermal member model',
        'blockers':[
            'NO_VALIDATED_CONTINUOUS_FIRST_FAILURE_TIME',
            'NO_NORMATIVE_FULL_MEMBER_FIRE_CALCULATION',
            'TKP_4_3_4_TEST_VALIDATION_NOT_ESTABLISHED',
            'FULL_STEEL_MATERIAL_DECLARATION_MAY_BE_MISSING',
            '1100_1200_CONCRETE_STRAIN_GAP_MAY_APPLY',
            'SPALLING_AND_THERMAL_TRANSIENT_CREEP_UNQUALIFIED']})
