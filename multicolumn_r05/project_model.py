"""R0.5 shared project state: rectangular RC columns, sections and 2-way editing.

Units at UI boundary: mm, m, MPa, GPa, minutes, kN, kN*m.
None means load NOT supplied, and is intentionally distinct from zero.
This is a data/validation layer, not a normative fire-resistance algorithm.
"""
from __future__ import annotations
import copy
import json
import math
from pathlib import Path

SCHEMA = 'k18-multi-column-project-r05'
CONCRETE = {'C20/25': (20.0, 25.0), 'C25/30': (25.0, 27.0), 'C30/37': (30.0, 29.0), 'C35/45': (35.0, 31.0), 'C40/50': (40.0, 33.0)}
COLUMN_EDITABLE = ('name','b_mm','h_mm','length_m','concrete','steel_grade','f_y_MPa', 'cover_mm','stirrup_mm','bar_diameter_mm','mu_x','mu_y','fire_minutes')
LOAD_EDITABLE=('z_m','N_kN','Mx_kNm','My_kNm')


def default_bars(col):
    b=float(col['b_mm']);h=float(col['h_mm'])
    off=float(col['cover_mm'])+float(col['stirrup_mm'])+float(col['bar_diameter_mm'])/2
    pts=[(off,off),(b/2,off),(b-off,off),(off,h/2),(b-off,h/2),(off,h-off),(b/2,h-off),(b-off,h-off)]
    return [{'id':f'S{i+1}','x_mm':round(x,6),'y_mm':round(y,6),'diameter_mm':float(col['bar_diameter_mm'])} for i,(x,y) in enumerate(pts)]


def new_column(idx):
    c={'id':f'c{idx}','name':f'К{idx}','b_mm':600.0,'h_mm':600.0,'length_m':3.0,
       'concrete':'C30/37','steel_grade':'S500','f_y_MPa':500.0,
       'E_s_GPa':200.0,'cover_mm':20.0,'stirrup_mm':10.0,'bar_diameter_mm':20.0,
       'mu_x':1.0,'mu_y':1.0,'fire_minutes':90.0,'bar_mode':'perimeter8',
       'sections':[{'id':'bottom','name':'Низ','z_m':0.0,'N_kN':None,'Mx_kNm':None,'My_kNm':None},
                   {'id':'top','name':'Верх','z_m':3.0,'N_kN':None,'Mx_kNm':None,'My_kNm':None}]}
    c['bars']=default_bars(c)
    c['spalling']={'method':'sp468'}  # no assumed mix data
    c['material_spec']={'concrete':{},'steel':{}}  # R0.6.1: no fabricated composition
    return c


def new_project(count=1):
    if not 1<=count<=30:raise ValueError('Количество колонн: 1–30')
    return {'schema':SCHEMA,'title':'Расчёт огнестойкости железобетонных колонн',
        'next_id':count+1,'revision':0,'columns':[new_column(i+1) for i in range(count)]}


def get_column(project,cid):
    return next(c for c in project['columns'] if c['id']==cid)


def set_count(project,n):
    n=int(n)
    if not 1<=n<=30:raise ValueError('Количество колонн: 1–30')
    while len(project['columns'])<n:
        project['columns'].append(new_column(project['next_id']))
        project['next_id']+=1
    if len(project['columns'])>n:
        del project['columns'][n:]
    project['revision']+=1


def update_column(project,cid,fields):
    col=get_column(project,cid)
    for k,v in fields.items():
        if k not in COLUMN_EDITABLE:raise ValueError(f'Неизвестное поле колонны: {k}')
        if k=='concrete' and v not in CONCRETE:raise ValueError(f'Неизвестный класс бетона {v}')
        if k in ('name','concrete','steel_grade'):v=str(v)
        else:
            if v is None or str(v)=='':raise ValueError(f'{k}: числовое значение обязательно')
            v=float(v)
            if not math.isfinite(v):raise ValueError(f'{k}: число не конечно')
        col[k]=v
    if 'length_m' in fields:
        for s in col['sections']:
            if s['id']=='top':s['z_m']=float(col['length_m'])
    # Automatic layout recomputes positions when geometry, cover or diameter changes.
    if col['bar_mode']=='perimeter8' and any(k in fields for k in ('b_mm','h_mm','cover_mm','stirrup_mm','bar_diameter_mm')):
        col['bars']=default_bars(col)
    elif 'bar_diameter_mm' in fields:
        for bar in col['bars']:bar['diameter_mm']=float(col['bar_diameter_mm'])
    project['revision']+=1


def update_section(project,cid,sid,fields):
    col=get_column(project,cid)
    sec=next(s for s in col['sections'] if s['id']==sid)
    for k,v in fields.items():
        if k not in ('name',)+LOAD_EDITABLE:raise ValueError(f'Неизвестное поле сечения: {k}')
        if k=='name': sec[k]=str(v); continue
        if v is None or (isinstance(v,str) and not v.strip()):sec[k]=None
        else:
            val=float(v)
            if not math.isfinite(val):raise ValueError('Неограниченная величина усилия/координаты')
            sec[k]=val
    project['revision']+=1


def update_material_spec(project,cid,fields):
    """Set canonical R0.6.1 concrete/rebar properties without silent defaults.

    Unknown values remain absent. Missing data is allowed; it blocks normative
    lookup, not the historic diagnostic calculator.
    """
    from rc_fire.materials.normative import (
        CONSISTENCY, ConcreteMix, Reinforcement, MaterialError,
    )
    col=get_column(project,cid)
    out=copy.deepcopy(col.get('material_spec') or {'concrete':{},'steel':{}})
    valid={
        'concrete':{'aggregate_family','consistency','curing','modulus_aggregate',
                    'fine_grained','saturated_freeze_C','independently_measured_Ecm_GPa'},
        'steel':{'product_type','fyk_MPa','E_s_GPa'},
    }
    for family,pairs in fields.items():
        if family not in valid or not isinstance(pairs,dict):
            raise ValueError('Недопустимая группа свойств материала')
        dest=out.setdefault(family,{})
        for key,value in pairs.items():
            if key not in valid[family]:
                raise ValueError('Неизвестное свойство: '+key)
            if value is None or (isinstance(value,str) and not value.strip()):
                dest.pop(key,None)
                continue
            if key=='fine_grained':
                if not isinstance(value,bool):raise ValueError('fine_grained: требуется bool')
            elif key in ('saturated_freeze_C','independently_measured_Ecm_GPa','fyk_MPa','E_s_GPa'):
                value=float(value)
                if not math.isfinite(value) or (key!='saturated_freeze_C' and value<=0):
                    raise ValueError(key+': недопустимое число')
            elif key=='aggregate_family' and value not in ('siliceous','calcareous'):
                raise ValueError('Неизвестный заполнитель')
            elif key=='consistency' and value not in CONSISTENCY:
                raise ValueError('Неизвестная консистенция')
            elif key=='curing' and value not in ('natural','heat'):
                raise ValueError('Неизвестный способ твердения')
            elif key=='modulus_aggregate' and value not in ('gravel_granite_upto40','other'):
                raise ValueError('Неизвестный заполнитель для Ecm')
            elif key=='product_type' and value not in ('weldable_bar','corrosion_resistant_bar','wire_or_heat_treated'):
                raise ValueError('Неизвестный вид арматуры')
            dest[key]=value
    # Enforce schema; combination admissibility is reported in material preflight.
    ConcreteMix(strength_class=col['concrete'],**out.get('concrete',{}))
    Reinforcement(grade=col['steel_grade'],**out.get('steel',{}))
    col['material_spec']=out
    project['revision']+=1


def update_spalling(project,cid,fields):
    """Switch SP468/manual methods; validate source and units without false defaults."""
    from multicolumn_r05.r056_engine import SPALLING_FIELDS
    from multicolumn_r05.sp468 import INPUT_FIELDS, ENUMS, NUMERIC_RANGES
    col=get_column(project,cid)
    current=dict(col.get('spalling') or {})
    if 'method' in fields:
        method=fields['method']
        if method not in ('sp468','manual_k18'):
            raise ValueError('Неизвестный метод оценки F')
        if method != current.get('method'):
            current={'method':method}  # never mix two methods' coefficients
    permitted=set(SPALLING_FIELDS)|set(INPUT_FIELDS)|{'method'}
    for k,v in fields.items():
        if k not in permitted:raise ValueError(f'Неизвестный параметр F: {k}')
        if k=='method':
            current[k]=v
        elif v is None or (isinstance(v,str) and not v.strip()):
            current.pop(k,None)
        elif k in ENUMS:
            if v not in ENUMS[k]:raise ValueError(f'{k}: нет в нормативной таблице')
            current[k]=v
        else:
            try:
                value=float(v)
                if not math.isfinite(value) or value<=0:raise ValueError()
                if k in NUMERIC_RANGES:
                    a,b=NUMERIC_RANGES[k]
                    if not a<=value<=b:raise ValueError(f'диапазон {a:g}–{b:g}')
                if k=='n_p_percent' and not 0<value<=100:raise ValueError('доля пор, %')
            except (TypeError,ValueError) as ex:
                raise ValueError(f'{k}: недопустимое значение {v} ({ex})') from ex
            current[k]=value
    col['spalling']=current
    project['revision']+=1


def replace_bars(project,cid,rows):
    col=get_column(project,cid)
    bars=[]
    for i,row in enumerate(rows):
        bars.append({'id':str(row.get('id') or f'S{i+1}'),
           'x_mm':float(row['x_mm']),'y_mm':float(row['y_mm']),
           'diameter_mm':float(row['diameter_mm'])})
    col['bars']=bars
    col['bar_mode']='manual'
    project['revision']+=1


def reset_auto_bars(project,cid):
    c=get_column(project,cid);c['bar_mode']='perimeter8';c['bars']=default_bars(c)
    project['revision']+=1


def add_section(project,cid):
    c=get_column(project,cid)
    if len(c['sections'])>=12:raise ValueError('Не более 12 сечений на колонну')
    used={s['id'] for s in c['sections']};i=1
    while f'mid{i}' in used:i+=1
    c['sections'].insert(-1,{'id':f'mid{i}','name':f'Промежуточное {i}',
              'z_m':float(c['length_m'])/2,'N_kN':None,'Mx_kNm':None,'My_kNm':None})
    project['revision']+=1


def remove_section(project,cid,sid):
    c=get_column(project,cid)
    if sid in ('bottom','top'):raise ValueError('Низ и верх нельзя удалить')
    c['sections']=[s for s in c['sections'] if s['id']!=sid]
    project['revision']+=1


def _number(x,field,issues,strict_positive=False):
    try:
        v=float(x)
        if not math.isfinite(v):raise ValueError()
        if strict_positive and v<=0:raise ValueError()
        return v
    except (TypeError,ValueError):
        issues.append(f'{field}: требуется конечное'+(' положительное' if strict_positive else '')+' число')
        return None


def validate_column(c):
    issues=[]
    for k in ('b_mm','h_mm','length_m','cover_mm','stirrup_mm','bar_diameter_mm','mu_x','mu_y','fire_minutes','f_y_MPa'):
        _number(c.get(k),k,issues,strict_positive=True)
    if issues:return issues
    b,h=c['b_mm'],c['h_mm']
    if not (250<=b<=2000 and 250<=h<=2000):issues.append('Сечение: размеры 250–2000 мм')
    if not 1<=c['length_m']<=40:issues.append('Длина: 1–40 м')
    if not (0<c['mu_x']<=2.5 and 0<c['mu_y']<=2.5):issues.append('Коэффициенты μ: (0; 2,5]')
    if c['concrete'] not in CONCRETE:issues.append('Неизвестный класс бетона')
    from multicolumn_r05.r056_engine import SPALLING_FIELDS
    from multicolumn_r05.sp468 import INPUT_FIELDS, ENUMS, NUMERIC_RANGES
    sp=c.get('spalling') or {}
    if not isinstance(sp,dict):issues.append('Параметры F должны быть объектом')
    else:
        permitted=set(SPALLING_FIELDS)|set(INPUT_FIELDS)|{'method'}
        for key,value in sp.items():
            if key not in permitted:issues.append('Неизвестный параметр F: '+key)
            elif key=='method' and value not in ('sp468','manual_k18'):issues.append('Неизвестный метод F')
            elif value is not None and key in ENUMS and value not in ENUMS[key]:issues.append('Нет нормативной таблицы для '+key)
            elif key not in ENUMS and key!='method' and value is not None:
                try:
                    x=float(value)
                    if not math.isfinite(x) or x<=0:raise ValueError()
                    if key in NUMERIC_RANGES:
                        lower,upper=NUMERIC_RANGES[key]
                        if not lower<=x<=upper:raise ValueError()
                    if key=='n_p_percent' and not 0<x<=100:raise ValueError()
                except (ValueError,TypeError):issues.append('Некорректный параметр F: '+key)

    if c.get('steel_grade')!='S500' or float(c.get('f_y_MPa',0))!=500.0:
        issues.append('R0.5 допускает только сталь S500 с f_y=500 МПа; для иных марок требуется калибровка температурных характеристик')
    if not(0<c['fire_minutes']<=240):issues.append('Продолжительность пожара: (0;240] мин')
    if c['stirrup_mm']<6:issues.append('Диаметр хомута меньше 6 мм')
    if len(c['bars'])<4 or len(c['bars'])>64:issues.append('От 4 до 64 стержней')
    ids=set()
    for x in c['bars']:
        bid=x.get('id')
        if bid in ids:issues.append('Дублируется идентификатор стержня '+str(bid))
        ids.add(bid)
        try:
            xx=float(x['x_mm']);yy=float(x['y_mm']); d=float(x['diameter_mm'])
            off=c['cover_mm']+c['stirrup_mm']+d/2
            if d<6 or d>50:issues.append(f'{bid}: Ø вне 6–50 мм')
            if not (off-1e-6<=xx<=b-off+1e-6 and off-1e-6<=yy<=h-off+1e-6):
                issues.append(f'{bid}: нарушен защитный слой до наружной грани хомута')
        except (KeyError,TypeError,ValueError):issues.append(f'{bid}: некорректные координаты/диаметр')
    for i,a in enumerate(c['bars']):
        for other in c['bars'][i+1:]:
            try:
                dist=math.hypot(a['x_mm']-other['x_mm'],a['y_mm']-other['y_mm'])
                if dist+1e-7<(a['diameter_mm']+other['diameter_mm'])/2:
                    issues.append(f"Пересечение стержней {a['id']}/{other['id']}")
            except (KeyError,TypeError,ValueError):pass
    if len(c['sections'])<2 or len(c['sections'])>12:issues.append('Необходимо 2–12 расчётных сечений')
    secids=set()
    for s in c['sections']:
        if s['id'] in secids:issues.append(f'Повтор сечения {s["id"]}')
        secids.add(s['id'])
        z=s.get('z_m')
        if z is None or not 0<=z<=c['length_m']:issues.append(f'{s["name"]}: z вне длины колонны')
    return issues


def load_state(section):
    vals=[section.get(k) for k in ('N_kN','Mx_kNm','My_kNm')]
    if all(x is None for x in vals):return 'empty'
    if any(x is None for x in vals):return 'incomplete'
    try:
        if not all(math.isfinite(float(x)) for x in vals):return 'invalid'
        if float(vals[0])<=0:return 'invalid' # R0.4 fibre model compression-only
    except (TypeError,ValueError):return 'invalid'
    return 'ready'


def to_engine_input(c,sections=None,grid=48):
    """Adapt one column and its ready load sections to existing R0.4 solver."""
    from multicolumn_r05.calculation_engine import ModelError
    issues=validate_column(c)
    if issues:raise ModelError('; '.join(issues))
    ss=list(sections if sections is not None else c['sections'])
    if not ss or any(load_state(s)!='ready' for s in ss):
        raise ModelError('Нагрузка по каждому выбранному сечению должна быть полной (N>0, Mx, My)')
    from rc_fire.materials import resolve_materials
    catalog=resolve_materials(c)
    fck,legacy_ecm=CONCRETE[c['concrete']]
    if catalog['concrete'] is not None:
        fck=catalog['concrete']['f_ck_MPa']
    ecm=legacy_ecm
    ecm_source='legacy_K18_diagnostic_fallback'
    if catalog['concrete'] is not None and catalog['concrete']['E_cm_GPa'] is not None:
        ecm=catalog['concrete']['E_cm_GPa']
        ecm_source=catalog['concrete']['modulus_source']
    return {'schema':'k18-parametric-r04','geometry':{'b_m':c['b_mm']/1000,'h_m':c['h_mm']/1000,'length_m':c['length_m']},
      'material':{'f_ck_MPa':fck,'E_cm_GPa':ecm,'f_y_MPa':c['f_y_MPa'],'E_s_GPa':c['E_s_GPa']},
      'material_resolution':{'E_cm_source':ecm_source,'normative_engine_qualified':False},
      'fire':{'minutes':c['fire_minutes'],'exposed_faces':['left','right','bottom','top'],
             'a_red_m2_h':0.00133,'phi_1':0.63,'phi_2':0.5,'critical_concrete_C':500},
      'mechanics':{'mu_x':c['mu_x'],'mu_y':c['mu_y']},'grid':int(grid),
      'variants':[{'id':s['id'],'N_kN':s['N_kN'],'M_x_kNm':s['Mx_kNm'],'M_y_kNm':s['My_kNm'],
                   'bars':[{'id':b['id'],'x_m':b['x_mm']/1000,'y_m':b['y_mm']/1000,
                            'diameter_mm':b['diameter_mm']} for b in c['bars']]} for s in ss]}


def validate_project(p):
    issues=[]
    if p.get('schema')!=SCHEMA:issues.append('Неверный формат проекта')
    cs=p.get('columns',[])
    if not (1<=len(cs)<=30):issues.append('Количество колонн: 1–30')
    ids=[c.get('id') for c in cs]
    if len(set(ids))!=len(ids):issues.append('Повторение идентификаторов колонн')
    for c in cs:
        issues.extend(f'{c.get("name","?")}: {m}' for m in validate_column(c))
    return issues


def export_json(p):
    return json.dumps(p,ensure_ascii=False,indent=2,allow_nan=False).encode('utf8')


def load_json(blob):
    data=json.loads(blob,parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Запрещено JSON значение '+x)))
    if not isinstance(data,dict) or data.get('schema')!=SCHEMA:
        raise ValueError('Неизвестная схема проекта; нужен '+SCHEMA)
    issues=validate_project(data)
    if issues:raise ValueError('Ошибки входных данных: '+'; '.join(issues[:12]))
    data['revision']=int(data.get('revision',0))+1
    return data


def overview_rows(project):
    out=[]
    for c in project['columns']:
        out.append({'ID':c['id'],'Колонна':c['name'],'b, мм':c['b_mm'],'h, мм':c['h_mm'],
        'L, м':c['length_m'],'Бетон':c['concrete'],'Арматура':c['steel_grade'],
        'Ø, мм':c['bar_diameter_mm'],'c, мм':c['cover_mm'],'Хомут Ø, мм':c['stirrup_mm'],
        'μx':c['mu_x'],'μy':c['mu_y'],'Пожар, мин':c['fire_minutes']})
    return out

OVERVIEW_COLUMNS={'Колонна':'name','b, мм':'b_mm','h, мм':'h_mm','L, м':'length_m',
    'Бетон':'concrete','Арматура':'steel_grade','Ø, мм':'bar_diameter_mm','c, мм':'cover_mm',
    'Хомут Ø, мм':'stirrup_mm','μx':'mu_x','μy':'mu_y','Пожар, мин':'fire_minutes'}


def update_from_overview(project,edited):
    """Accept editor rows as records, apply changed cells to canonical state."""
    updates=[]
    for r in edited:
        c=get_column(project,str(r['ID']))
        fields={v:r[k] for k,v in OVERVIEW_COLUMNS.items() if k in r and r[k]!=c.get(v)}
        if fields:
            update_column(project,c['id'],fields);updates.append(c['id'])
    return updates


def section_overview_rows(project):
    out=[]
    for c in project['columns']:
        for s in c['sections']:
            out.append({'ID':c['id'],'Сечение ID':s['id'],'Колонна':c['name'],
               'Сечение':s['name'],'z, м':s['z_m'],
               'N, кН':s['N_kN'],'Mx, кН·м':s['Mx_kNm'],'My, кН·м':s['My_kNm']})
    return out

SECTION_EDITOR_FIELDS={'z, м':'z_m','N, кН':'N_kN','Mx, кН·м':'Mx_kNm','My, кН·м':'My_kNm'}

def update_from_section_overview(project,edited):
    updates=[]
    for r in edited:
        c=get_column(project,str(r['ID']))
        s=next(t for t in c['sections'] if t['id']==str(r['Сечение ID']))
        fields={key:r[k] for k,key in SECTION_EDITOR_FIELDS.items() if k in r and r[k]!=s.get(key) and not (r[k] is None and s.get(key) is None)}
        if fields:
            update_section(project,c['id'],s['id'],fields);updates.append((c['id'],s['id']))
    return updates