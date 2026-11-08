"""R0.6.9C-K18: one-click, non-mutating source/project qualification audit.

Separates actual missing project data from arbitrary numerical implementation
limits, and independently exposes full thermal, Annex L, §8.2.21, material and
first-order section status. Never creates fictitious member loads or certifies R90.
"""
from __future__ import annotations

import copy
import math

from rc_fire.materials import resolve_materials
from rc_fire.thermal import evaluate_rectangular_column
from rc_fire.spalling.annex_l import evaluate_annex_l
from rc_fire.mechanics.critical_isotherm import evaluate_critical_isotherm_section
from rc_fire.integration.r069c import evaluate_fire_action_capacity_at_time

VERSION='R0.6.9C-K18-project-source-audit-v1'


def _issue(code,category,message,action,*,blocking_normative=True):
    return {'code':code,'category':category,'description':message,
            'required_action':action,'blocks_normative_R_t':blocking_normative}


def audit_rc_fire_project_column(column, *, grid=12, test_high_temp_model=True,
                                 density_sensitivity=True):
    """Actual-column audit; no fallback defaults or column input rewriting.

    A zero-strength assumption above 800 C is explicitly numerical and MAY
    only appear in the diagnostic branch. Its output is UNKNOWN at lambda=1
    regardless of successful numerical equilibrium.
    """
    if not isinstance(column,dict):
        raise TypeError('full column JSON required')
    column=copy.deepcopy(column)
    issues=[]
    details={'source_column_id':column.get('id'),
             'source_column_name':column.get('name'),
             'geometry_mm':{'b':column.get('b_mm'),'h':column.get('h_mm')},
             'fire_time_minutes':column.get('fire_minutes'),
             'entered_fire_design_sections':copy.deepcopy(column.get('sections') or []),
             'input_is_not_recombined':True}
    material=resolve_materials(column)
    details['material']={
        'status':material['status'],'issues':material['issues'],
        'fire_family':material.get('fire_family'),
        'fine_grained_classification':material.get('fine_grained_classification'),
        'E_cm_GPa':(material.get('concrete') or {}).get('E_cm_GPa'),
        'f_ck_MPa':(material.get('concrete') or {}).get('f_ck_MPa'),
        'f_yk_MPa':(material.get('steel') or {}).get('f_yk_MPa'),
        'steel_group':(material.get('steel') or {}).get('group')}
    if material['status']!='resolved_for_property_lookup':
        issues.append(_issue('MATERIAL_CATALOG_UNRESOLVED','missing_or_conflicting_input',
            'Бетон или арматура не разрешены по материальному каталогу.',
            'Проверить заполненные фактические свойства смеси; значения не подбирать автоматически.'))

    annex_l=evaluate_annex_l(column,material_result=material)
    details['annex_L']={
        'status':annex_l['status'],
        'F':annex_l.get('F'),
        'classification':annex_l.get('classification'),
        'protection_required_method_indicator':annex_l.get('protection_required'),
        'natural_sand_verified':annex_l.get('natural_sand_verified'),
        'moisture_method_qualified':annex_l.get('moisture_method_qualified'),
        'moisture_provenance':(annex_l.get('provenance') or {}).get('Wc'),
        'Wc_kg_kg':(annex_l.get('coefficients') or {}).get('Wc_kg_kg'),
        'reason':annex_l.get('reason')}
    if annex_l['status']=='blocked_input_or_scope':
        issues.append(_issue('ANNEX_L_INPUT_OR_SCOPE_BLOCKED','missing_or_conflicting_input',
            'Приложение Л не вычислено по фактическим входам.',
            str(annex_l.get('reason') or 'Проверить ввод приложения Л.')))
    elif annex_l.get('moisture_method_qualified') is not True:
        issues.append(_issue('ANNEX_L5_WC_UNIT_INTERPRETATION','normative_method_gap',
            'В формуле Л.5 результат численно интерпретируется как проценты и переводится в кг/кг.',
            'Проверить трактовку единиц с первоисточником либо указать измеренную Wc и источник.'))
    if annex_l.get('protection_required') is True:
        issues.append(_issue('ANNEX_L_FIRE_SPALLING_PROTECTION','physical_design_action',
            'Критерий F>4 в приложении Л требует защиты от хрупкого разрушения.',
            'Предусмотреть указанные в приложении Л меры и обосновать их действие.'))

    thermal=evaluate_rectangular_column(column,grid=grid)
    details['thermal']={'status':thermal.get('status'),
                        'issues':list(thermal.get('issues') or []),
                        'critical_section':copy.deepcopy(thermal.get('critical_section')),
                        'max_cell_temperature_C':thermal.get('max_temperature_C'),
                        'bar_temperatures_C':{
                            str(x['id']):float(x['theta_C'])
                            for x in thermal.get('reinforcement',[])},
                        'K2_density_status':(thermal.get('coefficients') or {}).get('K2_density_status'),
                        'coefficients_source':(thermal.get('coefficients') or {}).get('coefficients_source'),
                        'density_kg_m3':(column.get('thermal_spec') or {}).get('dry_density_kg_m3')}
    if thermal.get('status') not in ('evaluated','evaluated_with_scope_warnings'):
        issues.append(_issue('ANNEX_K_NOT_EVALUATED','missing_or_conflicting_input',
            'Температурное поле по приложению К не построено.',
            str(thermal.get('reason') or thermal.get('missing') or thermal.get('status'))))
    if not (thermal.get('coefficients') or {}).get('normative_table_nodes',False):
        issues.append(_issue('ANNEX_K2_INTERMEDIATE_DENSITY','normative_method_gap',
            'Плотность находится между табличными узлами К.2: применена численная интерполяция.',
            'Сохранить реальную плотность; сравнить расчёты на соседних узлах К.2. '
            'Не представлять интерполяцию как явно предписанный нормативный метод.'))

    if density_sensitivity and thermal.get('status') in ('evaluated','evaluated_with_scope_warnings'):
        dens=float((column.get('thermal_spec') or {}).get('dry_density_kg_m3') or math.nan)
        nodes=(800.,1100.,1400.,1700.,2000.,2400.)
        if math.isfinite(dens) and min(nodes)<=dens<=max(nodes):
            i=next((j for j in range(len(nodes)-1) if nodes[j]<=dens<=nodes[j+1]),len(nodes)-2)
            d0,d1=nodes[i:i+2]
            neighbors=[]
            for val in sorted(set([d0,d1])):
                c=copy.deepcopy(column)
                c['thermal_spec']['dry_density_kg_m3']=val
                th=evaluate_rectangular_column(c,grid=grid)
                neighbors.append({'density_kg_m3':val,
                   'temperature_max_cell_C':th.get('max_temperature_C'),
                   'K27_area_m2':(th.get('critical_section') or {}).get('remaining_area_m2'),
                   'steel_max_C':max((float(x['theta_C']) for x in th.get('reinforcement',[])),
                                    default=None)})
            details['thermal']['K2_neighbor_sensitivity_not_design_value']=neighbors

    if thermal.get('status') in ('evaluated','evaluated_with_scope_warnings'):
        isotherm=evaluate_critical_isotherm_section(column,grid=max(12,grid))
        details['critical_isotherm']={
            'status':isotherm['status'],'remaining_area_m2':isotherm.get('remaining_area_m2'),
            'scope':isotherm.get('scope'),
            'blockers':isotherm.get('blockers'),
            'upper_axial_ceiling_kN_not_NRd':isotherm.get('N_optimistic_upper_kN')}
        scope=isotherm.get('scope') or {}
        if not scope.get('conditions_8_2_21_verified',False):
            issues.append(_issue('CRITICAL_ISOTHERM_SECTION_SCOPE_UNQUALIFIED',
                 'normative_method_gap',
                 'Аналитическая площадь К.27 определена, но область применения §8.2.21 '
                 'для механического расчёта не полностью подтверждена.',
                 'Нельзя считать площадь К.27 готовой кривой взаимодействия N–Mx–My; '
                 'использовать отдельно квалифицированную механику.'))
    else:
        details['critical_isotherm']={'status':'not_evaluated'}

    strict=evaluate_fire_action_capacity_at_time(column,grid=grid,
           max_factor=1.,factor_step=1.,max_bisection=0,include_member=False,
           material_policy='reject')
    details['strict_section_capacity']={
        'status':strict.get('status'),
        'reason':strict.get('reason'),
        'blockers':strict.get('blockers'),
        'thermal_boundary_max_C':strict.get('thermal_boundary_max_C'),
        'bar_temperatures_C':strict.get('reference_bar_temperatures_C'),
        'normative_claim':False,
        'reference_status_by_section':{
            item['section_id']:item['at_design_actions']['classification']
            for item in strict.get('sections',[])}}
    hot_boundary=(strict.get('status')=='BLOCKED_SECTION_MATERIAL_DOMAIN'
       and strict.get('thermal_boundary_max_C') is not None
       and strict['thermal_boundary_max_C']>800.)
    if hot_boundary:
        issues.append(_issue('FULL_SECTION_MATERIALS_GT_800_NOT_TABULATED',
            'normative_method_gap',
            'Температура бетона на границе выше 800 °C; таблица 9 не содержит коэффициентов.',
            'Сохранять неизвестное нормативное сопротивление. Для исследования '
            'допускается отдельно обозначенный сценарий нулевой прочности T>800 °C.'))
        if test_high_temp_model:
            approximate=evaluate_fire_action_capacity_at_time(column,grid=grid,
                max_factor=1.,factor_step=1.,max_bisection=0,include_member=False,
                material_policy='zero_strength_diagnostic')
            details['high_temperature_research_only']={
                'status':approximate.get('status'),
                'raw_numerical_sections':[
                    {'id':row['section_id'],
                     'model_reference_classification':row['action_path'][
                         'design_action_evidence']['classification'],
                     'physical_reference_classification':row['at_design_actions']['classification'],
                     'model_reason':row['at_design_actions'].get('reason'),
                     'raw_model_status':row['action_path']['design_action_evidence']['model_status']}
                    for row in approximate.get('sections',[])],
                'zero_strength_concrete_cells_count':approximate.get('out_of_table_concrete_cells'),
                'steel_above_800_count':approximate.get('out_of_table_rebars'),
                'material_assumption':'Only exploratory: T>800 C assigned zero resistance',
                'normative_claim':False,'R_t_minutes':None}
    else:
        details['high_temperature_research_only']={'status':'not_requested_or_not_needed'}

    spec=column.get('member_spec') or {}
    configured=(spec.get('thermal_longitudinal_mode')=='uniform_assumed'
       and spec.get('left_support') is not None and spec.get('right_support') is not None
       and spec.get('load_mode') not in (None,'not_defined'))
    details['member']={
        'status':'CONFIGURED_FOR_INDEPENDENT_EVALUATION' if configured else
                 'OPTIONAL_MEMBER_MODEL_NOT_CONFIGURED',
        'is_blocker_for_section_calculation':False,
        'explicit_section_MxMy_not_equivalent_to_member_q':True,
        'thermal_longitudinal_mode':spec.get('thermal_longitudinal_mode'),
        'load_mode':spec.get('load_mode')}
    if not configured:
        issues.append(_issue('MEMBER_PATH_NOT_DEFINED','optional_calculation_not_configured',
             'Нет опор и непрерывной схемы нагрузок/нагрева для пространственной модели.',
             'Не подбирать q по одному Mx и не предполагать опоры. '
             'Считать имеющиеся сечения; пространственную модель оставить невычисленной.',
             blocking_normative=True))

    details['issues']=issues
    details['summary']={
        'source_inputs_preserved':True,
        'Annex_L_F_computed':annex_l.get('F') is not None,
        'K27_area_computed':(details['critical_isotherm'].get('remaining_area_m2') is not None),
        'full_section_normative_capacity_demonstrated':False,
        'spatial_member_normative_capacity_demonstrated':False,
        'R_t_minutes':None,
        'normative_claim':False,
        'fire_resistance_status':'not_demonstrated',
        'hard_input_blockers':[x['code'] for x in issues
          if x['category']=='missing_or_conflicting_input'],
        'normative_method_gaps':[x['code'] for x in issues
          if x['category']=='normative_method_gap'],
        'optional_model_inputs_not_set':[x['code'] for x in issues
          if x['category']=='optional_calculation_not_configured']}
    return {'version':VERSION,**details,
        'normative_claim':False,'R_t_minutes':None,
        'fire_resistance_status':'not_demonstrated'}
