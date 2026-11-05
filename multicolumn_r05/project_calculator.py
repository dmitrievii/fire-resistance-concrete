"""R0.5 project calculation facade with pending/error states and deterministic cache."""
import hashlib
import json
import math
from multicolumn_r05.project_model import validate_column,load_state,to_engine_input
from multicolumn_r05.parametric_engine import GeneralInput,compute_general

_CACHE={}  # ephemeral one-process cache; safe because key hashes all authoritative inputs
MAX_CACHE=60

def evaluate_column(c,grid=48):
    issues=validate_column(c)
    state={s['id']:load_state(s) for s in c['sections']}
    base={'id':c['id'],'name':c['name'],'status':'pending','issues':issues,
          'section_statuses':state,'results':{},'worst':None,'engine_inputs':None,
          'normative_claim':False,'model':'diagnostic / uniaxial sections','grid':grid}
    if issues:
        base['status']='invalid';return base
    ready=[s for s in c['sections'] if state[s['id']]=='ready']
    if any(x in ('invalid','incomplete') for x in state.values()):
        base['issues'].append('Некоторые нагрузки не заполнены полностью или N<=0')
    if not ready:return base
    try:
        data=to_engine_input(c,ready,grid)
        key=hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        if key not in _CACHE:
            _CACHE[key]=compute_general(GeneralInput.from_dict(data))
            if len(_CACHE)>MAX_CACHE:_CACHE.pop(next(iter(_CACHE)))
        result=_CACHE[key]
        base['results']=result['variants'];base['engine_inputs']=data;base['raw_results']=result
        scores=[]
        for sid,rec in result['variants'].items():
            for axis,a in rec['axes'].items():
                scores.append({'section_id':sid,'axis':axis,'u':a['utilization'],
                    'MEd_kNm':a['M_Ed_kNm'],'MRd_kNm':a['M_Rd_kNm']})
        base['worst']=max(scores,key=lambda x:x['u']) if scores else None
        base['status']='calculated' if len(ready)==len(c['sections']) else 'partial'
    except Exception as exc:
        base['status']='error';base['issues'].append(type(exc).__name__+': '+str(exc))
    return base


def evaluate_project(project,grid=48):
    return {c['id']:evaluate_column(c,grid) for c in project['columns']}