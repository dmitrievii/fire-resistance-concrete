"""R0.6.9B: strictly scoped critical-isotherm section assessment.

Uses the already implemented analytical Annex K.27 area, *never* substitutes a
numerically thresholded area for that formula. SP 2.02.05-2026 §8.2.21 requires
a simple symmetric section, longitudinal steel at the most compressed/tension
faces and actions in a symmetry plane. Biaxial actions are NOT included.

The optimistic axial force ceiling is a necessary-condition diagnostic,
NOT a section/member ULS, actual N_Rd, or R(t). It assumes all concrete and
steel can develop independent peak compressive stresses simultaneously, with
gross (non-subtracted) steel volume, and ignores moment and buckling.
"""
from __future__ import annotations

import copy
import math

from rc_fire.materials import resolve_materials
from rc_fire.materials.normative import STEEL_GROUPS, STEEL_TEMP
from rc_fire.thermal import evaluate_rectangular_column
from rc_fire.member.time_scan import timeline_points

VERSION = 'R0.6.9B-annex-K27-scope-and-axial-ceiling-v1'
SOURCE = 'СП 2.02.05-2026 §8.2.18, §8.2.21; приложение К, К.20–К.28'
NOT_DEMONSTRATED = 'not_demonstrated'
TOL_MM = 1.0e-5
TOL_FORCE = 1.0e-9


def _number(value, name, *, positive=False):
    if isinstance(value, bool):
        raise ValueError(f'{name}: boolean is not a number')
    try:
        val = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f'{name}: finite number required') from exc
    if not math.isfinite(val) or (positive and val <= 0):
        raise ValueError(f'{name}: invalid or nonpositive')
    return val


def _action_plane(column):
    """Require one and the same actual bending plane for every filled section."""
    sections = column.get('sections')
    if not isinstance(sections, list) or not sections:
        return None, ['COMPLETE_FIRE_DESIGN_SECTION_ACTIONS_REQUIRED']
    axes = set()
    errors = []
    for i, s in enumerate(sections):
        if not isinstance(s, dict):
            errors.append(f'SECTION_{i}_INVALID')
            continue
        try:
            n = _number(s.get('N_kN'), f'N[{i}]', positive=True)
            mx = _number(s.get('Mx_kNm'), f'Mx[{i}]')
            my = _number(s.get('My_kNm'), f'My[{i}]')
        except ValueError:
            errors.append(f'SECTION_{i}_ACTION_INCOMPLETE_OR_INVALID')
            continue
        # A zero moment at one station is allowed only when an axis is
        # established by nonzero moments at another station.
        if abs(mx) > TOL_FORCE:
            axes.add('x')
        if abs(my) > TOL_FORCE:
            axes.add('y')
        if n <= 0:
            errors.append(f'SECTION_{i}_NO_COMPRESSION')
    if not axes:
        errors.append('BENDING_SYMMETRY_PLANE_NOT_ESTABLISHED_PURE_AXIAL')
    if len(axes) > 1:
        errors.append('BIAXIAL_OR_MIXED_AXIS_BENDING_OUTSIDE_8_2_21')
    return (next(iter(axes)) if len(axes) == 1 and not errors else None), errors


def _bar_layout_scope(column, axis):
    """Conservative, exact two-face and double-mirror symmetry admission.

    The code intentionally does not invent a permissible tolerance for where
    'concentrated at extreme faces' begins. Only two exact bar-centre layers
    and both mirror axes are accepted, without claiming this is sufficient
    proof of the normative design intent.
    """
    errors = []
    try:
        b = _number(column.get('b_mm'), 'b_mm', positive=True)
        h = _number(column.get('h_mm'), 'h_mm', positive=True)
        bars = column.get('bars')
        if not isinstance(bars, list) or not bars:
            return ['REINFORCEMENT_REQUIRED']
        positions = []
        for i, item in enumerate(bars):
            x = _number(item.get('x_mm'), f'bar[{i}].x_mm')
            y = _number(item.get('y_mm'), f'bar[{i}].y_mm')
            d = _number(item.get('diameter_mm'), f'bar[{i}].diameter_mm', positive=True)
            if not (d/2 < x < b-d/2 and d/2 < y < h-d/2):
                errors.append('BAR_CROSSES_SECTION_BOUNDARY')
            positions.append((x,y,d))
    except (ValueError, AttributeError, TypeError):
        return ['INVALID_REINFORCEMENT_GEOMETRY']
    if len({(round(x,5),round(y,5)) for x,y,_ in positions}) != len(positions):
        errors.append('DUPLICATED_BAR_CENTRES')
    depth = [y if axis == 'x' else x for x,y,_ in positions]
    layers = sorted({round(d,5) for d in depth})
    if len(layers) != 2:
        errors.append('REINFORCEMENT_NOT_IN_TWO_EXTREME_FACE_LAYERS')
    else:
        dimension = h if axis == 'x' else b
        if abs(layers[0] + layers[1] - dimension) > TOL_MM:
            errors.append('EXTREME_REINFORCEMENT_LAYERS_NOT_SYMMETRIC')
    def present(a,b_,diameter):
        return any(abs(x-a)<=TOL_MM and abs(y-b_)<=TOL_MM and abs(d-diameter)<=TOL_MM
                   for x,y,d in positions)
    for x,y,d in positions:
        if not present(b-x,y,d) or not present(x,h-y,d):
            errors.append('REINFORCEMENT_MIRROR_SYMMETRY_NOT_VERIFIED')
            break
    return sorted(set(errors))


def evaluate_critical_isotherm_section(column, *, grid=40, thermal=None):
    """K.27 area and a separate, optimistic axial-capacity *ceiling*.

    For safe integration thermal can be supplied only by an already resolved
    same-column call. Public-facing integrations compute thermal here, to avoid
    accepting a stale heat field for the current time or geometry.
    """
    base = {
        'version': VERSION, 'status': 'BLOCKED_INPUT',
        'source': SOURCE, 'normative_claim': False,
        'fire_resistance_status': NOT_DEMONSTRATED, 'R_t_minutes': None,
        'N_Rd_kN': None, 'N_optimistic_upper_kN': None,
        'remaining_area_m2': None, 'analytic_K27': None, 'scope': {
            'conditions_8_2_21_verified': False, 'bending_axis': None},
        'blockers': [], 'notes': [
            'Annex K.27 gives an analytically reduced AREA, not a complete N–M strength interaction.',
            'An optimistic uniform-strength axial ceiling is not an actual resistance.',
            'Global second-order stability and the first failure time are not qualified.'],
    }
    try:
        if type(grid) is not int or not 12 <= grid <= 120:
            raise ValueError('grid: integer 12..120 required')
        b = _number(column.get('b_mm'), 'b_mm', positive=True)
        h = _number(column.get('h_mm'), 'h_mm', positive=True)
        _number(column.get('fire_minutes'), 'fire_minutes', positive=True)
    except (ValueError, AttributeError, TypeError) as exc:
        return {**base, 'blockers': ['INVALID_COLUMN_INPUT'], 'reason': str(exc)}
    # This release only implements the actual K.27 square/4-side analytical
    # geometry. Arbitrary rectangles require another geometric method.
    if abs(b-h) > TOL_MM:
        return {**base, 'blockers': ['K27_REQUIRES_SQUARE_SECTION']}
    faces = (column.get('thermal_spec') or {}).get('exposed_faces')
    if not isinstance(faces,(list,tuple)) or set(faces) != {'left','right','bottom','top'} or len(faces)!=4:
        return {**base, 'blockers': ['K27_REQUIRES_FOUR_HEATED_FACES']}
    th = thermal if thermal is not None else evaluate_rectangular_column(column, grid=grid)
    if not isinstance(th,dict) or th.get('status') not in ('evaluated','evaluated_with_scope_warnings'):
        return {**base, 'status':'BLOCKED_THERMAL', 'blockers':['ANNEX_K_NOT_RESOLVED'],
                'reason': str(th.get('reason') or th.get('missing') or th.get('status'))}
    if abs(float(th.get('fire_minutes',-1)) - float(column['fire_minutes']))>1.e-8 or set(th.get('exposed_faces') or ()) != set(faces):
        return {**base, 'status':'BLOCKED_THERMAL', 'blockers':['THERMAL_TIME_OR_EXPOSURE_MISMATCH']}
    section = th.get('critical_section') or {}
    if section.get('status')!='evaluated':
        return {**base,'status':'BLOCKED_K27_DOMAIN',
                'blockers':['K27_ANALYTIC_AREA_UNAVAILABLE'],
                'reason': section.get('reason','critical isotherm not evaluated')}
    area = float(section['remaining_area_m2'])
    if not math.isfinite(area) or not (0<area <= b*h/1e6):
        return {**base,'status':'BLOCKED_K27_DOMAIN',
                'blockers':['K27_ANALYTIC_AREA_INVALID']}
    result = {**base, 'status':'K27_ANALYTIC_AREA_ONLY', 'remaining_area_m2':area,
        'analytic_K27': {
            'remaining_area_m2': area, 'lost_area_m2': float(section['lost_area_m2']),
            'lc_m': section.get('lc_m'), 'ld_m':section.get('ld_m'),
            'psi': section.get('psi'), 'critical_temperature_C': section.get('theta_critical_C'),
            'formula':'K.27 (K.20–K.28), not numerical isotherm pixel integration'},
        'lost_area_fraction': 1.-area/(b*h/1e6),
        'blockers': []}
    axis, actions = _action_plane(column)
    layout = _bar_layout_scope(column, axis) if axis is not None else []
    blockers = actions + layout
    family = (th.get('coefficients') or {}).get('material_family')
    if family not in ('siliceous','calcareous'):
        blockers.append('CRITICAL_ISOTHERM_CONCRETE_FAMILY_UNRESOLVED')
    if th.get('issues'):
        blockers.append('THERMAL_METHOD_SCOPE_WARNINGS')
    elif th.get('status') != 'evaluated':
        blockers.append('THERMAL_METHOD_NOT_UNCONDITIONALLY_EVALUATED')
    if not (th.get('coefficients') or {}).get('normative_table_nodes', False):
        blockers.append('K2_DENSITY_INTERPOLATION_UNQUALIFIED')
    if not th.get('reinforcement'):
        blockers.append('REINFORCEMENT_TEMPERATURES_NOT_AVAILABLE')
    result['scope'] = {
        'conditions_8_2_21_verified': not blockers,
        'bending_axis':axis, 'two_extreme_layers_mirrored': not layout and axis is not None,
        'analytic_area_available':True,
        'thermal_time_minutes':float(th['fire_minutes']),
        'concrete_family':family}
    if blockers:
        result['status']='K27_GEOMETRY_ONLY_SECTION_SCOPE_BLOCKED'
        result['blockers']=sorted(set(blockers))
        return result
    # No material coefficients are assigned outside Tables 9/10. For the
    # ceiling we require all REAL bar temperatures within 20..800 C.
    mat=resolve_materials(column)
    concrete=mat.get('concrete') or {}
    steel=mat.get('steel') or {}
    try:
        fck=_number(concrete.get('f_ck_MPa'),'resolved fck',positive=True)
        fyk=_number(steel.get('f_yk_MPa'),'resolved fyk',positive=True)
        group=steel['group']
        if group not in STEEL_GROUPS:
            raise ValueError('unresolved normative reinforcing steel group')
        weights=STEEL_GROUPS[group]['k']
        steel_ceiling=0.
        steel_rows=[]
        for bar in th['reinforcement']:
            temp = _number(bar.get('theta_C'), 'steel bar temperature')
            if not 20 <= temp <= 800:
                raise ValueError('REINFORCEMENT_TEMPERATURE_OUTSIDE_TABLE_10')
            area_bar=math.pi/4*(_number(bar.get('diameter_mm'),'bar diameter',positive=True)/1000.)**2
            # 20 -> 200 C is an explicitly labelled numerical bridge, not
            # a source-tabulated coefficient (Table 10 begins at 200 C).
            low=[20., *STEEL_TEMP]
            kval=[1., *weights]
            j=next((i for i,x in enumerate(low) if x >= temp),len(low)-1)
            if j==0:ks=kval[0]
            else:
                f=(temp-low[j-1])/(low[j]-low[j-1])
                ks=kval[j-1]+f*(kval[j]-kval[j-1])
            steel_ceiling+=area_bar*fyk*ks*1000
            steel_rows.append({'id':bar['id'],'temperature_C':temp,
                               'k_s_interpolated':ks,
                               'upper_axial_force_kN':area_bar*fyk*ks*1000})
    except (ValueError,TypeError,KeyError) as exc:
        return {**result,'status':'K27_GEOMETRY_ONLY_STRENGTH_UNRESOLVED',
                'blockers':['MATERIAL_OR_REINFORCEMENT_TABLE_UNRESOLVED'],
                'reason':str(exc)}
    # This intentionally overestimates possible axial force by using fck
    # throughout the remaining concrete and NOT subtracting displaced concrete.
    # It also ignores moment and the member's slenderness. It is ONLY a
    # necessary-condition ceiling; never N_Rd or a fire-rating.
    ceiling=1000.*area*fck+steel_ceiling
    demands=[float(x['N_kN']) for x in column['sections']]
    result.update({
        'status':'K27_SECTION_SCOPE_CANDIDATE_DIAGNOSTIC',
        'N_optimistic_upper_kN':ceiling,
        'axial_force_max_entered_kN':max(demands),
        'optimistic_upper_to_axial_demand_ratio': ceiling/max(demands),
        'axial_necessary_condition': ('VIOLATED_DIAGNOSTIC' if max(demands)>ceiling else
                                       'NOT_VIOLATED_NO_STRENGTH_PROOF'),
        'steel_ceiling_kN':steel_ceiling,
        'concrete_ceiling_kN':1000.*area*fck,
        'bar_evidence':steel_rows,
        'strength_reference': 'fck and fyk, SP 2.02.05-2026 §8.2.18',
        'blockers': ['SECTION_N_M_INTERACTION_NOT_COMPUTED',
                     'SECOND_ORDER_MEMBER_STABILITY_NOT_QUALIFIED',
                     'TEMPERATURE_INTERPOLATION_NOT_NORMATIVELY_VERIFIED',
                     'AXIAL_CEILING_NOT_DESIGN_RESISTANCE'],
    })
    # conditions_8_2_21_verified flags only the geometrical/action preflight.
    # It cannot be read as approving actual mechanical resistance.
    return result


def evaluate_critical_isotherm_history(column, *, step_minutes=10., grid=40):
    """Independent time points, K.27 area + scoped upper bound, no R(t) claim."""
    times=timeline_points(float(column['fire_minutes']),step_minutes=step_minutes)
    rows=[]
    for t in times:
        c=copy.deepcopy(column)
        c['fire_minutes']=t
        r=evaluate_critical_isotherm_section(c,grid=grid)
        rows.append({'time_minutes':t,'status':r['status'],
            'K27_area_m2':r['remaining_area_m2'],
            'area_loss_fraction':r.get('lost_area_fraction'),
            'N_optimistic_upper_kN':r['N_optimistic_upper_kN'],
            'axial_necessary_condition':r.get('axial_necessary_condition'),
            'blockers':r['blockers']})
    return {'version': VERSION,'status':'DIAGNOSTIC_TIME_SERIES_ONLY',
        'column_id':column.get('id'),
        'requested_duration_minutes':float(column['fire_minutes']),
        'samples':rows, 'R_t_minutes':None,'normative_claim':False,
        'fire_resistance_status':NOT_DEMONSTRATED,
        'blockers':['TIME_CONTINUOUS_ULS_NOT_QUALIFIED',
                    'SECTION_N_M_INTERACTION_NOT_COMPUTED',
                    'MEMBER_SECOND_ORDER_LIMIT_NOT_QUALIFIED'],
        'notes':['No resistance time inferred from successive K.27 areas or optimistic axial ceilings.']}
