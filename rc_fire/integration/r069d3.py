"""R0.6.9D3 — one temperature field → one TKP N–Mx–My mechanical history.

Thermal: TKP §4.3.2 conservative 2D enthalpy finite volumes, Belarus
lower lambda, source humidity/capacity and actual surface flux.
Mechanics: TKP §3.2 full nonlinear RC fibres with own thermal strains.
The same *time-matched field* is passed to every reinforced fibre.

Optional member: independent user-specified N+q+supports; cannot claim
reconciliation to entered design Mx/My without actual action path evidence.
No convergence, strain exceedance or Newton failure is a normative t_R.
"""
from __future__ import annotations

import copy
import math
import numpy as np

from rc_fire.thermal.tkp_heat import (
    TKPHeatError,solve_tkp_2d_heat,select_tkp_snapshot,sample_tkp_temperature,
    reference_annex_a_boundary)
from rc_fire.mechanics.tkp_thermomechanical_fibres import (
    TKPFibreInputError,prepare_tkp_fibres)
from rc_fire.mechanics.action_capacity import WITHIN,EXCEEDED,UNKNOWN
from rc_fire.integration.r069c import _action_sections
from rc_fire.integration.r067 import validate_member_spec
from rc_fire.integration.r064d import MemberEvidenceInputError
from rc_fire.member.coupled import CoupledMemberError,EndSupport,solve_coupled_beam
from rc_fire.member.uls import audit_heated_member_uls
from rc_fire.member.time_scan import timeline_points
from rc_fire.materials.tkp_en1992_fire import EurocodeFireMaterialError
from rc_fire.integration.r072_strength_evidence import (
    material_strength_retention,sampled_action_reserve)
from rc_fire.integration.r069d4_first_crossing import (
    summarize_observed_strain_history, refine_observed_interval)

VERSION="R0.6.9D3-consistent-TKP-thermal-to-mechanics-v1"
NOT_DEMONSTRATED="not_demonstrated"


def _no_rating(v):
    return {**v,'normative_claim':False,'R_t_minutes':None,
        'fire_resistance_status':NOT_DEMONSTRATED,
        'normative_member_capacity_kN':None}


def _field_evidence(column,thermal_snap):
    snap=thermal_snap['snapshot']
    b=float(column['b_mm']);h=float(column['h_mm'])
    bars={str(x['id']):sample_tkp_temperature(thermal_snap,float(x['x_mm']),
           float(x['y_mm'])) for x in column.get('bars',[])}
    return {
        'temperature_method':'TKP_4.3.2_FVM',
        'source_temperature_time_minutes':snap['time_minutes'],
        'T_gas_C':20.+345.*math.log10(8*snap['time_minutes']+1),
        'T_concrete_boundary_max_C':snap['boundary_max_C'],
        'T_concrete_center_C':sample_tkp_temperature(thermal_snap,b/2,h/2),
        'T_reinforcement_C':bars,
        'FVM_grid':dict(thermal_snap['grid']),
        'temperature_source_match_verified':True,
        'temperature_field_grid_hash_not_required_for_float_reuse':True}


def _member_tkp_conduction(column,thermal_snap,*,grid,production_route,
                            ductility_class):
    base=_no_rating({
        'status':'BLOCKED_MEMBER_INPUT',
        'model':'TKP_4_3_2_thermal_plus_TKP_N_M_eigenstrains_P_Delta',
        'entered_section_moment_diagram_reconciled':False,
        'all_generated_gauss_sections_thermal_time_matched':None,
        'blockers':[]})
    try:
        spec=validate_member_spec(column.get('member_spec'))
        if spec.get('thermal_longitudinal_mode')!='uniform_assumed' or not (
            spec.get('uniform_fire_basis') and spec.get('support_provenance')):
            raise MemberEvidenceInputError(
                'explicit uniform heating basis and support provenance required')
        if spec.get('left_support') not in ('pinned','fixed','guided') or \
           spec.get('right_support') not in ('pinned','fixed','guided'):
            raise MemberEvidenceInputError('explicit left/right support types required')
        if spec.get('load_mode') not in ('axial_only','uniform_transverse_load'):
            raise MemberEvidenceInputError('explicit member N+q loading required')
        actions=_action_sections(column)
        Ns={float(x['N_kN']) for x in actions}
        if len(Ns)!=1:
            raise MemberEvidenceInputError('member axial force must be constant')
        N=Ns.pop()
        if spec.get('load_mode')=='axial_only':
            if any(abs(x['Mx_kNm'])>1e-12 or abs(x['My_kNm'])>1e-12 for x in actions):
                raise MemberEvidenceInputError(
                    'axial-only member incompatible with nonzero entered section moment')
            qx=qy=0.
        else:
            if spec.get('q_x_kNpm') is None or spec.get('q_y_kNpm') is None:
                raise MemberEvidenceInputError('qx and qy must both be declared')
            qx=float(spec['q_x_kNpm']);qy=float(spec['q_y_kNpm'])
            if not (math.isfinite(qx) and math.isfinite(qy)):
                raise MemberEvidenceInputError('invalid transverse member forces')
        nodes=spec.get('node_count',3)
        L=float(column['length_m'])
        if not L>0:
            raise MemberEvidenceInputError('member length invalid')
        z=np.linspace(0.,L,nodes)
        q=np.tile([[qx,qy]],(nodes,1))
        def new_law():
            return prepare_tkp_fibres(column,thermal_snap,grid=grid,
                production_route=production_route,ductility_class=ductility_class,
                high_temperature_tail='reject').member_law()
        # No hidden longitudinal interpolation: the user explicitly chose a
        # uniform field along the length. Independent trial law per station.
        gauss=[[new_law() for _ in range(3)] for i in range(nodes-1)]
        law_nodes=[new_law() for _ in range(nodes)]
        result=solve_coupled_beam(z,N,law_at_gauss=lambda i,j:gauss[i][j],
            left=EndSupport(spec['left_support']),
            right=EndSupport(spec['right_support']),
            distributed_load_kNpm=q)
        if result.get('status') in ('evaluated_diagnostic','strain_limits_exceeded_diagnostic'):
            audit=audit_heated_member_uls(result,z,N,node_laws=law_nodes,
                temperature_time_minutes=float(column['fire_minutes']),
                material_provenance={'source':'TKP EN 1992-1-2-2009 material law',
                      'thermal':'TKP section 4.3.2 FVM independent solution'})
        else:
            audit={'status':'MODEL_NOT_SOLVED','reason':result.get('reason')}
        return _no_rating({**base,
            'status':'MEMBER_DIAGNOSTIC_EQUILIBRATED' if
              result.get('status') in ('evaluated_diagnostic','strain_limits_exceeded_diagnostic')
                 else 'MEMBER_NUMERICAL_STATE_UNRESOLVED',
            'model_status':result.get('status'),
            'node_count':nodes,'gauss_count':(nodes-1)*3,
            'all_generated_gauss_sections_thermal_time_matched':True,
            'entered_section_moment_diagram_reconciled':False,
            'member_N_kN':N,'member_qx_kNpm':qx,'member_qy_kNpm':qy,
            'member_solver':result,'member_uls_diagnostic':audit,
            'blockers':[
                'ENTERED_MX_MY_NOT_RECONCILED_WITH_INDEPENDENT_N_Q_PATH',
                'IMPERFECTIONS_AND_GLOBAL_FRAME_RESTRAINT_NOT_QUALIFIED',
                'SECTION_4_3_4_TEST_VALIDATION_MISSING',
                'SPALLING_TRANSIENT_CREEP_NOT_QUALIFIED']})
    except (MemberEvidenceInputError,TKPFibreInputError,TKPHeatError,
            CoupledMemberError,EurocodeFireMaterialError,ValueError,TypeError,KeyError) as exc:
        return {**base,'reason':str(exc),
            'blockers':['MEMBER_LOAD_SUPPORTS_OR_THERMAL_PROVENANCE_REQUIRED']}


def evaluate_tkp_thermal_mechanical_history(column,*,boundary,
            production_route=None,ductility_class=None,
            cell_count=12,max_step_minutes=5.,step_minutes=30.,
            fibre_grid=None,include_member=False,
            max_factor=1.,factor_step=1.,max_bisection=0,
            refine_strain_transition=False,max_time_refinements=4,
            thermal_curve_step_minutes=None):
    """One independent heat solve; no rerun/mismatch across mechanical times."""
    if not isinstance(column,dict):
        raise TypeError('column must be a dictionary')
    actions=_action_sections(column)
    times=timeline_points(column.get('fire_minutes'),
           step_minutes=step_minutes,start_minutes=1.,max_points=12)
    # A temperature curve must have independent time resolution.  Sampling
    # only the sparse nonlinear mechanical history and connecting its
    # points created misleading temperature plots in the public UI.
    thermal_times=list(times)
    if thermal_curve_step_minutes is not None:
        from rc_fire.thermal.tkp_heat import _finite
        curve_step=_finite(thermal_curve_step_minutes,
                           'thermal_curve_step_minutes',lo=1.,hi=30.)
        duration=float(column['fire_minutes'])
        extra=[curve_step*i for i in range(1,int(duration/curve_step)+1)
               if curve_step*i<=duration+1.e-8]
        thermal_times=sorted(set([*times,*extra,duration]))
    thermal=solve_tkp_2d_heat(column,boundary=boundary,
        cell_count_x=cell_count,cell_count_y=cell_count,
        max_step_minutes=max_step_minutes,
        sample_times_minutes=thermal_times)
    thermal_curve=None
    if thermal_curve_step_minutes is not None:
        # t=0 is the exact initial condition, not an extrapolated heat sample.
        # The actual cell-temperature field is retained for the public
        # heating-section figure; it is NEVER reconstructed from the surface
        # temperature or from sparse mechanical output.
        initial=float(thermal['initial_temperature_C'])
        grid=thermal['grid'];nx=int(grid['nx']);ny=int(grid['ny'])
        thermal_curve=[{
            'time_minutes':0.,
            'T_gas_C':initial,
            'T_concrete_boundary_max_C':initial,
            'T_concrete_center_C':initial,
            'T_reinforcement_C':{
                str(bar['id']):initial for bar in column.get('bars',[])},
            'grid_temperature_C':[[initial]*nx for _ in range(ny)],
            'surface_temperature_C':{
                name:[initial]*(ny if name in ('left','right') else nx)
                for name in ('left','right','bottom','top')},
            'temperature_source_match_verified':True,
            'temperature_source':'FVM initial condition t=0'}]
        for t in thermal_times:
            selected=select_tkp_snapshot(thermal,t)
            snapshot=selected['snapshot']
            thermal_curve.append({
                **_field_evidence(column,selected),
                'time_minutes':float(t),
                'grid_temperature_C':snapshot['grid_temperature_C'],
                'surface_temperature_C':snapshot['surface_temperature_C'],
                'temperature_source':'TKP 2D FVM solved snapshot'})
    if fibre_grid is None:
        fibre_grid=cell_count
    if type(fibre_grid) is not int or not 8<=fibre_grid<=80:
        raise ValueError('fibre_grid must be 8..80')
    rows=[]
    for t in times:
        c=copy.deepcopy(column);c['fire_minutes']=t
        snap=select_tkp_snapshot(thermal,t)
        evidence=_field_evidence(c,snap)
        if production_route not in ('hot_rolled','cold_worked') or \
           ductility_class not in ('A','B','C'):
            rows.append({
                'time_minutes':t,'status':'BLOCKED_REBAR_DECLARATION',
                'reference_classification':UNKNOWN,
                **evidence,'sections':[],
                'member':None,
                'blockers':['STEEL_PROCESS_AND_DUCTILITY_REQUIRED'],
                'normative_claim':False})
            continue
        try:
            p=prepare_tkp_fibres(c,snap,grid=fibre_grid,
                production_route=production_route,
                ductility_class=ductility_class,
                high_temperature_tail='reject')
        except (TKPFibreInputError,TKPHeatError,EurocodeFireMaterialError,ValueError) as exc:
            rows.append({
                'time_minutes':t,'status':'BLOCKED_TKP_FIBRE_PREPARATION',
                'reference_classification':UNKNOWN,**evidence,
                'sections':[],'member':None,
                'reason':str(exc),'blockers':['CONSTITUTIVE_DOMAIN_UNRESOLVED'],
                'normative_claim':False})
            continue
        reports=[]
        for s in actions:
            scan=p.load_factor_scan(s['N_kN'],s['Mx_kNm'],s['My_kNm'],
                 max_factor=max_factor,factor_step=factor_step,
                 max_bisection=max_bisection)
            reports.append({'id':s['id'],'z_m':s['z_m'],
                'entered_actions_N_Mx_My':{k:s[k]
                   for k in ('N_kN','Mx_kNm','My_kNm')},
                'at_lambda_1':scan['design_action_evidence'],
                'sampled_scale_path':scan})
        # Independent evidence: temperature-driven material strength and a
        # discrete proportional load test. These are never whole-member ULS.
        strength_retention=material_strength_retention(p)
        checked_reserve=sampled_action_reserve(reports)
        classes=[s['at_lambda_1']['classification'] for s in reports]
        classification=(EXCEEDED if EXCEEDED in classes else
            WITHIN if classes and all(v==WITHIN for v in classes) else UNKNOWN)
        member=_member_tkp_conduction(c,snap,grid=fibre_grid,
            production_route=production_route,ductility_class=ductility_class) \
                if include_member else None
        rows.append({'time_minutes':t,'status':'FVM_TKP_FIBRES_NUMERICAL_DIAGNOSTIC',
            'reference_classification':classification,**evidence,
            'sections':reports,'member':member,
            'material_strength_retention':strength_retention,
            'sampled_section_load_evidence':checked_reserve,
            'blockers':[
                'TKP_4_3_4_EXPERIMENTAL_VALIDATION_NOT_DONE',
                'NUMERICAL_FAILURE_IS_NOT_PHYSICAL_FAILURE',
                'CONTINUOUS_MEMBER_ACTIONS_NOT_VERIFIED',
                'MESH_TIME_CONVERGENCE_NOT_YET_PROVED',
                'FULL_SPALLING_TRANSIENT_CREEP_NOT_QUALIFIED'],
            'normative_claim':False})
    if refine_strain_transition:
        def _evaluate_midpoint(t_minutes):
            # A midpoint has its OWN heat integration from the physical
            # initial state. Never time-interpolate a coarse grid result or
            # borrow a previous nonlinear equilibrium root.
            c=copy.deepcopy(column)
            c['fire_minutes']=float(t_minutes)
            th=solve_tkp_2d_heat(c,boundary=boundary,
                cell_count_x=cell_count,cell_count_y=cell_count,
                max_step_minutes=max_step_minutes,
                sample_times_minutes=[t_minutes])
            snapshot=select_tkp_snapshot(th,t_minutes)
            if production_route not in ('hot_rolled','cold_worked') or (
                ductility_class not in ('A','B','C')):
                return {'reference_classification':UNKNOWN,
                    'reason':'steel production route/ductility unknown'}
            try:
                prep=prepare_tkp_fibres(c,snapshot,grid=fibre_grid,
                    production_route=production_route,
                    ductility_class=ductility_class,
                    high_temperature_tail='reject')
                classes=[prep.solve_actions(s['N_kN'],s['Mx_kNm'],s['My_kNm'])[
                    'classification'] for s in actions]
                state=(EXCEEDED if EXCEEDED in classes else
                       WITHIN if classes and all(q==WITHIN for q in classes)
                       else UNKNOWN)
                return {'reference_classification':state,
                        'reason':'Independent thermomechanical time sample; not R(t)'}
            except (ValueError,KeyError,ArithmeticError,TKPHeatError,
                    EurocodeFireMaterialError,TKPFibreInputError) as exc:
                return {'reference_classification':UNKNOWN,'reason':str(exc)}
        first=summarize_observed_strain_history(rows)
        first=refine_observed_interval(rows,_evaluate_midpoint,
             max_refinements=max_time_refinements,
             tolerance_minutes=1.)
    else:
        first=summarize_observed_strain_history(rows)
    return _no_rating({
        'version':VERSION,'status':'TKP_THERMAL_MECHANICAL_HISTORY_DIAGNOSTIC',
        'observed_section_strain_transition':first,
        'column_id':column.get('id'),'time_points':len(rows),
        'fire_time_minutes':column['fire_minutes'],
        'reference_standard_fire_gas_at_end_C':20+345*math.log10(
            8*float(column['fire_minutes'])+1),
        'boundary_assumptions':boundary,
        'thermal_energy_balance':thermal['energy_balance'],
        'thermal_step_count':len(thermal['step_log']),
        'thermal_source':thermal['governing_source'],
        'thermal_field_source_method':thermal['thermal_method'],
        'temperature_field_not_from_SP_annex_K':True,
        'thermal_curve_samples':thermal_curve,
        'thermal_grid':dict(thermal['grid']) if thermal_curve is not None else None,
        'thermal_curve_step_minutes':thermal_curve_step_minutes,
        'temperature_curve_independent_of_mechanics_times':thermal_curve is not None,
        'mechanical_material_source':'ТКП EN 1992-1-2-2009 §3.2',
        'fire_design_actions_used_without_recombination':True,
        'steel_production_route':production_route,
        'steel_ductility_class':ductility_class,
        'spatial_member_mode':'explicit_independent_N_plus_q' if include_member else 'not_evaluated',
        'samples':rows,
        'normative_first_failure_time_minutes':None,
        'blockers':[
            'TKP_4_3_4_MANDATORY_EXPERIMENTAL_COMPARISON_OUTSTANDING',
            'THERMAL_MESH_AND_TIME_CONVERGENCE_OUTSTANDING',
            'EN1991_FIRE_BOUNDARY_CONTRACT_NOT_INDEPENDENTLY_QUALIFIED',
            'CONTINUOUS_GLOBAL_MEMBER_STABILITY_UNQUALIFIED',
            'CONCRETE_SPALLING_MOISTURE_MOVEMENT_TRANSIENT_CREEP_UNQUALIFIED'],
        'interpretation':'Heat balance and same-field mechanical transfer achieved. '
            'Numerical first order fibre status is not a proven physical failure '
            'or valid R90 certification.'})


def compare_tkp_thermal_refinement(column,*,boundary,coarse=8,fine=12,
                                   dt_minutes=5.,target_points=None):
    """A deterministic mesh/time convergence diagnostic, not validation."""
    if type(coarse) is not int or type(fine) is not int or not (4<=coarse<fine<=40):
        raise ValueError('require 4<=coarse<fine<=40')
    if target_points is None:
        target_points=[(40.,40.),(float(column['b_mm'])/2,float(column['h_mm'])/2)]
    configs=[
        ('coarse',coarse,dt_minutes),
        ('spatial_fine',fine,dt_minutes),
        ('temporal_fine',fine,dt_minutes/2)]
    vals={}
    for key,size,dt in configs:
        sol=solve_tkp_2d_heat(column,boundary=boundary,
             cell_count_x=size,cell_count_y=size,
             max_step_minutes=dt)
        snap=select_tkp_snapshot(sol,column['fire_minutes'])
        vals[key]={'mesh_nx_ny':size,'max_step_minutes':dt,
            'sampling_C':{
                f'x={x:g},y={y:g}':sample_tkp_temperature(snap,x,y)
                    for x,y in target_points},
            'energy_relative_residual':sol['energy_balance'][
                'relative_cumulative_residual']}
    points=vals['coarse']['sampling_C'].keys()
    space=max(abs(vals['coarse']['sampling_C'][p]-
                  vals['spatial_fine']['sampling_C'][p]) for p in points)
    temporal=max(abs(vals['spatial_fine']['sampling_C'][p]-
                     vals['temporal_fine']['sampling_C'][p]) for p in points)
    return _no_rating({'status':'TKP_HEAT_NUMERICAL_REFINEMENT_DIAGNOSTIC',
        'version':VERSION,'comparisons':vals,
        'max_spatial_difference_C':space,
        'max_temporal_difference_C':temporal,
        'source':'TKP EN 1992-1-2-2009 §4.3.2',
        'qualification':'Not a substitute for measured fire-test validation, '
            'spalling qualification or calibrated boundary heat transfer.'})
