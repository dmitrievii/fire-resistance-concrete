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
from rc_fire.normative import audit_column
from multicolumn_r05.r056_engine import (
    member_envelope, enrich_with_biaxial, spalling_assessment, check_provenance,
)

_CACHE={}
MAX_CACHE=60


def evaluate_column(c,grid=48):
    issues=validate_column(c)
    states={s['id']:load_state(s) for s in c['sections']}
    spalling=spalling_assessment(c.get('spalling'))
    normative_preflight=audit_column(c)  # R0.6.0: immutable, never a PASS
    material_preflight=resolve_materials(c)
    base={
        'id':c['id'],'name':c['name'],'status':'pending',
        'issues':issues,'section_statuses':states,'results':{},'worst':None,
        'engine_inputs':None,'normative_claim':False,
        'model':'K18-derived temperature + R0.4 fiber / R0.5.6 diagnostics',
        'grid':grid,'spalling':spalling,'normative_preflight':normative_preflight,
        'material_preflight':material_preflight,
        'member':{'status':'not_evaluated'},
        'biaxial':{'status':'not_evaluated'},'provenance':check_provenance(),
        'fire_resistance_status':'not_demonstrated',
    }
    if issues:
        base['status']='invalid';return base
    ready=[s for s in c['sections'] if states[s['id']]=='ready']
    if any(s in ('invalid','incomplete') for s in states.values()):
        base['issues'].append('Некоторые нагрузки не заполнены полностью или N<=0')
    if not ready:return base
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


def evaluate_project(project,grid=48):
    return {c['id']:evaluate_column(c,grid) for c in project['columns']}