"""R0.5.6 project calculation facade with whole-member, biaxial and spalling checks.

The base 4-face 500C/steel model is inherited from R0.4. Its independent
single-axis resistances and the new member/biaxial results are diagnostics, not
an independent certified normative fire-resistance assessment.
"""
from __future__ import annotations
import hashlib
import json
from multicolumn_r05.project_model import validate_column,load_state,to_engine_input
from multicolumn_r05.parametric_engine import GeneralInput,compute_general
from rc_fire.materials import resolve_materials
from rc_fire.thermal import evaluate_rectangular_column
from rc_fire.mechanics import evaluate_column_mechanics
from rc_fire.normative import audit_column
from multicolumn_r05.r056_engine import (
    member_envelope, enrich_with_biaxial, spalling_assessment, check_provenance,
)

_CACHE={}
MAX_CACHE=60


def _evaluate_column_pre_r064d(c,grid=48):
    issues=validate_column(c)
    states={s['id']:load_state(s) for s in c['sections']}
    # Historical foreign-method spalling fields are archival input only.
    # The current calculator NEVER evaluates SP468 or historical K18 F.
    spalling={'status':'archived_legacy_inactive','F':None,'source':'not_used_in_current_calculation'}
    material_preflight=resolve_materials(c)
    thermal_normative=evaluate_rectangular_column(c,grid=min(40,max(8,int(grid))))
    from rc_fire.spalling import evaluate_annex_l
    annex_l=evaluate_annex_l(c,material_result=material_preflight)
    normative_preflight=audit_column(c,material_result=material_preflight,
        thermal_result=thermal_normative,annex_l_result=annex_l)
    # R0.6.3 is a separate first-order SECTION diagnostic, never the fire
    # resistance verdict. Keep it even if the R0.4 mechanics cannot run.
    try:
        mechanics_r063=evaluate_column_mechanics(c,thermal_normative,
            grid=min(28,max(12,int(grid))),above_800_policy='reject')
    except Exception as exc:
        mechanics_r063={'status':'error','issues':[type(exc).__name__+': '+str(exc)],
                         'normative_claim':False,'fire_resistance_status':'not_demonstrated',
                         'sections':{}}
    base={
        'id':c['id'],'name':c['name'],'status':'pending',
        'issues':issues,'section_statuses':states,'results':{},'worst':None,
        'engine_inputs':None,'normative_claim':False,
        'model':'K18-derived temperature + R0.4 fiber / R0.5.6 diagnostics',
        'grid':grid,'spalling':spalling,'annex_l':annex_l,
        'normative_preflight':normative_preflight,
        'material_preflight':material_preflight,
        'thermal_normative':thermal_normative,
        'mechanics_r063':mechanics_r063,
        'member':{'status':'not_evaluated'},
        'biaxial':{'status':'not_evaluated'},
        'provenance':{**{k:v for k,v in check_provenance().items()
                         if k!='spalling'},
                      'annex_l':'СП 2.02.05-2026, приложение Л'},
        'fire_resistance_status':'not_demonstrated',
        'load_summary':{'ready':sum(v=='ready' for v in states.values()),
                        'empty':sum(v=='empty' for v in states.values()),
                        'incomplete':sum(v=='incomplete' for v in states.values()),
                        'invalid':sum(v=='invalid' for v in states.values()),
                        'total':len(states)},
    }
    if issues:
        base['status']='invalid';return base
    ready=[s for s in c['sections'] if states[s['id']]=='ready']
    if any(s in ('invalid','incomplete') for s in states.values()):
        base['issues'].append('Некоторые нагрузки не заполнены полностью или N<=0')
    if not ready:return base
    # The inherited R0.4 fibre solver only supports 4-face heating. Avoid
    # quietly reporting a 4-face mechanical result for a user-selected
    # 1-, 2-, or 3-face fire configuration.
    tp=c.get('thermal_spec') or {}
    chosen=set(tp.get('exposed_faces',('left','right','bottom','top')))
    if chosen != {'left','right','bottom','top'}:
        base['status']='pending'
        base['issues'].append('R0.6.2: нагрузки введены, но диагностический расчёт '
            'R0.5.6 применим только для четырёхстороннего обогрева; '
            'нормативное заключение по выбранным сторонам не формируется.')
        return base
    # Explicitly selected material data may not be silently replaced by
    # siliceous 2400 kg/m3 K18 legacy constants if Annex K cannot resolve.
    if (tp.get('dry_density_kg_m3') is not None or tp.get('concrete_family') is not None):
        # The K.2 intermediate-density uncertainty is documented rather than
        # silently substituting reference K18 coefficients. Only that warning
        # permits a *diagnostic* legacy computation; all other scope warnings
        # remain blockers. There is never a normative R90 claim here.
        warnings=thermal_normative.get('issues',[]) or []
        diagnostic_k2=(thermal_normative.get('status')=='evaluated_with_scope_warnings'
                       and bool(warnings)
                       and all(str(x).startswith('К.2:') for x in warnings))
        if thermal_normative['status']!='evaluated' and not diagnostic_k2:
            base['status']='pending'
            base['issues'].append('Нагрузки введены, но механический расчёт '
                'приостановлен из-за ограничений теплотехники: '+
                str(thermal_normative.get('reason') or
                    '; '.join(warnings or thermal_normative.get('missing',[])) or
                    thermal_normative.get('status')))
            return base
        if diagnostic_k2:
            base['issues'].append('К.2: параметры интерполированы по плотности; '
                'результат механики только диагностический, нормативный R90 не подтверждён')
    try:
        data=to_engine_input(c,ready,grid)
        key=hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        if key not in _CACHE:
            _CACHE[key]=compute_general(GeneralInput.from_dict(data))
            if len(_CACHE)>MAX_CACHE:_CACHE.pop(next(iter(_CACHE)))
        result=_CACHE[key]
        base['results']=result['variants']
        base['engine_inputs']=data
        base['raw_results']=result
        member=member_envelope(c,result['variants'])
        base['member']=member
        biaxial=enrich_with_biaxial(GeneralInput.from_dict(data),result['variants'],member)
        base['biaxial']=biaxial
        scores=[]
        if member['status']=='evaluated':
            for sid,axes in member['sections'].items():
                for axis,rec in axes.items():
                    scores.append({'section_id':sid,'axis':axis,'u':rec['utilization'],
                        'MEd_kNm':rec['M_Ed_kNm'],'MRd_kNm':rec['M_Rd_kNm'],
                        'source':'member_envelope_diagnostic'})
        else:
            for sid,v in result['variants'].items():
                for axis,a in v['axes'].items():
                    scores.append({'section_id':sid,'axis':axis,'u':a['utilization'],
                        'MEd_kNm':a['M_Ed_kNm'],'MRd_kNm':a['M_Rd_kNm'],
                        'source':'section_only_diagnostic'})
        base['worst']=max(scores,key=lambda x:x['u']) if scores else None
        base['status']='calculated' if len(ready)==len(c['sections']) else 'partial'
        base['fire_resistance_status']='not_demonstrated'
        # Do not promote any diagnostic result, even a passed biaxial equilibrium,
        # to a normative R90 claim. The source worksheet lacks an authoritative
        # global member + biaxial interaction calculation and spalling inputs.
    except Exception as exc:
        base['status']='error'
        base['issues'].append(type(exc).__name__+': '+str(exc))
    return base


# R064D_REPOSITORY_HOOK: add evidence without modifying historical calculation.
def evaluate_column(c,grid=48):
    from rc_fire.integration import attach_member_evidence
    old = _evaluate_column_pre_r064d(c,grid)
    return attach_member_evidence(old,expected_column=c)


def evaluate_project(project,grid=48):
    return {c['id']:evaluate_column(c,grid) for c in project['columns']}