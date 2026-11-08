"""R0.6.1: normative material properties with explicit origin and no extrapolation.

Primary sources (user provided official PDFs):
  СП 5.03.01-2020, tables 6.1 and 6.3, §§6.1.3/6.2.2
  СП 2.02.05-2026, §8.2.18, tables 9/10; §8.2.19 tables 11/12 and eq. (6)

IMPORTANT: interpolating between listed temperatures and 20->200C for reinforcing
steel are engineering numerical interpolation contracts, not literally explicit
normative coefficients. Results from this catalog are not R(t) certification.
At >800C no coefficients are assigned by the cited tables.
The high-strength beta E curve is absent from Table 9 and remains unavailable.
"""
from __future__ import annotations
from dataclasses import dataclass
from bisect import bisect_left
import math

VERSION='R0.6.1-materials-v1'
FIRE_SOURCE='СП 2.02.05-2026 §8.2.18, таблицы 9, 10; §8.2.19, таблицы 11, 12'
RC_SOURCE='СП 5.03.01-2020, таблицы 6.1, 6.3; §6.2.2'

class MaterialError(ValueError):
    pass

C_CLASSES=('C12/15','C16/20','C20/25','C25/30','C30/37','C35/45','C40/50','C45/55',
           'C50/60','C55/67','C60/75','C70/85','C80/95','C90/105')
# Table 6.1 -- symbolic fck and concrete stress-strain parameters.
FCK=(12,16,20,25,30,35,40,45,50,55,60,70,80,90)
FCM=(20,24,28,33,38,43,48,53,58,63,68,78,88,98)
FCTM=(1.6,1.9,2.2,2.6,2.9,3.2,3.5,3.8,4.1,4.2,4.4,4.6,4.8,5.)
FCTK005=(1.1,1.3,1.5,1.8,2.,2.2,2.5,2.7,2.9,3.,3.1,3.2,3.4,3.5)
EPS_C1_PERMILLE=(1.8,1.9,2.,2.1,2.2,2.25,2.3,2.4,2.45,2.5,2.6,2.7,2.8,2.8)
EPS_CU2_PERMILLE=(3.5,)*9+(3.1,2.9,2.7,2.6,2.6)
EPS_C2_PERMILLE=(2.,)*9+(2.2,2.3,2.4,2.5,2.6)
PARABOLA_N=(2.,)*9+(1.75,1.60,1.45,1.40,1.40)

# Table 6.3; None represents a literal dash (application prohibited).
CONSISTENCY={
 'V3_V4':(None,38,39,40,41,42,43,44,45,46,47,49,50,52),
 'V1_V2':(31,35,37,38,40,41,42,43,44,45,46,47,49,51),
 'S1_S2':(27,31,32,35,37,38,39,40,41,42,43,45,46,48),
 'S3_S5':(24,28,29,32,33,35,37,38,39,None,None,None,None,None),
}

FIRE_TEMP=(20.,100.,200.,300.,400.,500.,600.,700.,800.)
# Table 9, concrete of normal density with explicitly specified aggregate family.
CONCRETE_K={
 'siliceous':(1.,.99,.98,.95,.85,.80,.60,.20,.10),
 'calcareous':(1.,1.,.98,.95,.90,.85,.65,.30,.15),
 'high_C55_60':(1.,.90,.90,.85,.75,.60,.45,.28,.10),
 'high_C70_80':(1.,.75,.70,.65,.50,.45,.30,.20,.05),
 'high_C90':(1.,.75,.70,.65,.45,.30,.25,.15,.05),
}
CONCRETE_BETA={
 'siliceous':(1.,.85,.70,.50,.40,.30,.20,.10,.05),
 'calcareous':(1.,.88,.75,.55,.45,.35,.25,.15,.10),
}
STEEL_TEMP=(200.,300.,400.,500.,600.,700.,800.)
STEEL_GROUPS={
 'S240_S500':{'k':(1.,1.,.85,.60,.37,.22,.10),
             'beta':(.92,.90,.85,.80,.77,.72,.65)},
 'S800_S1400':{'k':(1.,.96,.80,.55,.30,.12,.08),
              'beta':(.90,.85,.80,.76,.70,.66,.61)},
 'wire_or_heat_treated':{'k':(1.,.90,.65,.35,.15,.05,.02),
                         'beta':(.94,.86,.77,.64,.55,.45,.35)},
}
# Tables 11 and 12 -- 20..50 and 700..1100 are constant table intervals.
THERMAL_T=(50.,100.,300.,500.,700.)
ALPHA_BT_MICRO={
 'siliceous':(9.,9.,8.,11.,14.5),
 'calcareous':(10.,10.,9.,12.,15.5),
}
ALPHA_CS_MICRO={
 'siliceous':(.5,1.,1.,-1.8,-6.8),
 'calcareous':(.5,1.5,1.1,1.3,1.5),
}

@dataclass(frozen=True)
class ConcreteMix:
    strength_class: str
    aggregate_family: str | None = None  # siliceous | calcareous
    consistency: str | None = None  # V3_V4, V1_V2, S1_S2, S3_S5
    curing: str | None = None  # natural | heat
    modulus_aggregate: str | None = None  # gravel_granite_upto40 | other
    fine_grained: bool | None = None
    saturated_freeze_C: float | None = None
    independently_measured_Ecm_GPa: float | None = None

@dataclass(frozen=True)
class Reinforcement:
    grade: str = 'S500'
    product_type: str | None = 'weldable_bar'  # weldable_bar, corrosion_resistant_bar, wire_or_heat_treated
    fyk_MPa: float | None = None
    E_s_GPa: float | None = None


def _finite_pos(value,name):
    try:
        f=float(value)
        if not math.isfinite(f) or f<=0:raise ValueError
    except (ValueError,TypeError):raise MaterialError(f'{name}: требуется положительное конечное значение')
    return f


def _interp(x,xs,ys,what):
    if not math.isfinite(x) or x<xs[0] or x>xs[-1]:
        raise MaterialError(f'{what}: температура {x} вне таблицы [{xs[0]}; {xs[-1]}] °C')
    i=bisect_left(xs,x)
    if i<len(xs) and x==xs[i]:return float(ys[i]), 'tabulated'
    if i<=0 or i>=len(xs):raise MaterialError(f'{what}: вне области применимости')
    y0,y1=ys[i-1],ys[i]
    return float(y0+(y1-y0)*(x-xs[i-1])/(xs[i]-xs[i-1])), 'linear_between_tabulated'


def _family(cls,aggregate_family):
    idx=C_CLASSES.index(cls)
    if idx<=8:
        if aggregate_family not in ('siliceous','calcareous'):
            raise MaterialError('Тип заполнителя обязателен для таблицы 9')
        return aggregate_family
    if idx<=10:return 'high_C55_60'
    if idx<=12:return 'high_C70_80'
    return 'high_C90'


def normal_concrete(mix:ConcreteMix):
    """Table 6.1 strength and table 6.3 verified Ecm, with explicit prerequisites."""
    if mix.strength_class not in C_CLASSES:raise MaterialError('Класс бетона вне таблицы 6.1')
    idx=C_CLASSES.index(mix.strength_class)
    missing=[]
    if mix.independently_measured_Ecm_GPa is not None:
        ecm=_finite_pos(mix.independently_measured_Ecm_GPa,'Ecm')
        origin='independently_measured';notes=['Ecm задан по внешним испытаниям, не принят автоматически из таблицы 6.3']
    else:
        if mix.consistency not in CONSISTENCY:missing.append('консистенция бетонной смеси')
        if mix.curing not in ('natural','heat'):missing.append('способ твердения')
        if mix.modulus_aggregate != 'gravel_granite_upto40':
            missing.append('подтверждение заполнителя гравий/гранит до 40 мм для таблицы 6.3')
        if mix.fine_grained is None:missing.append('признак мелкозернистости')
        if missing:ecm=None;origin='unresolved';notes=[]
        else:
            base=CONSISTENCY[mix.consistency][idx]
            if base is None:
                ecm=None;origin='out_of_table';notes=['Сочетание класса и консистенции отсутствует в таблице 6.3']
            else:
                ecm=float(base)
                notes=[]
                if mix.curing=='heat':ecm*=.9;notes.append('0,90: теплообработка, примечание 2 таблицы 6.3')
                if mix.fine_grained:ecm*=.85;notes.append('0,85: мелкозернистый бетон, примечание 3')
                if mix.saturated_freeze_C is not None:
                    t=mix.saturated_freeze_C
                    if t < -40 or t > 5:raise MaterialError('Поправка замораживания допускается при -40…+5 °C')
                    factor=.85 if t < -20 else (.90 if t < -5 else .95)
                    ecm*=factor;notes.append(f'{factor:.2f}: водонасыщенное замораживание, примечание 4')
                origin='SP 5.03.01-2020 table 6.3'
    return dict(strength_class=mix.strength_class, f_ck_MPa=float(FCK[idx]), f_cm_MPa=float(FCM[idx]),
                f_ctm_MPa=float(FCTM[idx]), f_ctk_005_MPa=float(FCTK005[idx]),
                eps_c1_permille=float(EPS_C1_PERMILLE[idx]),
                eps_c2_permille=float(EPS_C2_PERMILLE[idx]),
                eps_cu2_permille=float(EPS_CU2_PERMILLE[idx]),n_parabola=float(PARABOLA_N[idx]),
                E_cm_GPa=ecm, modulus_source=origin, missing=missing, notes=notes,
                source=RC_SOURCE, release=VERSION)


def concrete_at_temperature(concrete:ConcreteMix,theta_C:float,normal=None):
    """Table 9: strength k_c and elastic beta at theta (not a ULS solver)."""
    norm=normal if normal is not None else normal_concrete(concrete)
    family=_family(concrete.strength_class,concrete.aggregate_family)
    t=float(theta_C)
    k,mode=_interp(t,FIRE_TEMP,CONCRETE_K[family], 'Таблица 9 — k_c')
    beta=None;beta_note='table9_no_high_strength_beta'
    if family in CONCRETE_BETA:
        beta,_=_interp(t,FIRE_TEMP,CONCRETE_BETA[family],'Таблица 9 — beta')
        beta_note='from_table9'
    ecm=norm['E_cm_GPa']
    return {'theta_C':t,'family':family,'k_c':k,'beta_E':beta,
            'f_ck_theta_MPa':norm['f_ck_MPa']*k,
            'E_cm_theta_GPa':None if beta is None or ecm is None else ecm*beta,
            'mode':mode,'beta_status':beta_note,'source':'СП 2.02.05-2026 §8.2.18, table 9'}


def _steel_group(rebar):
    if rebar.product_type=='wire_or_heat_treated':return 'wire_or_heat_treated'
    if rebar.product_type=='corrosion_resistant_bar':
        raise MaterialError('Таблица 10 не выделяет отдельную группу коррозионно-стойкой арматуры; необходима верификация')
    if rebar.product_type != 'weldable_bar':raise MaterialError('Неопределённый вид арматуры')
    try:strength=int(rebar.grade.removeprefix('S'))
    except (ValueError,AttributeError):raise MaterialError('Неизвестная марка S')
    if 240<=strength<=500:return 'S240_S500'
    if 800<=strength<=1400:return 'S800_S1400'
    raise MaterialError('Марка вне таблицы 10 (S240–S500, S800–S1400)')


def normal_reinforcement(rebar:Reinforcement):
    group=_steel_group(rebar)
    if rebar.product_type=='wire_or_heat_treated':
        fyk=_finite_pos(rebar.fyk_MPa,'fyk') if rebar.fyk_MPa is not None else None
    else:
        fyk=_finite_pos(rebar.fyk_MPa,'fyk') if rebar.fyk_MPa is not None else float(rebar.grade[1:])
    es=_finite_pos(rebar.E_s_GPa,'E_s') if rebar.E_s_GPa is not None else 200.
    if es is not None and rebar.product_type=='weldable_bar' and rebar.E_s_GPa is None:origin='§6.2.2.13 (200 GPa)'
    elif rebar.E_s_GPa is not None:origin='user_specified_verified_value_required'
    else:origin='unresolved'
    return {'group':group,'f_yk_MPa':fyk,'E_s_GPa':es,'E_s_origin':origin,'source':RC_SOURCE}


def reinforcement_at_temperature(rebar:Reinforcement,theta_C:float,normal=None):
    """Table 10; first temperature 200C. At 20..200C an explicit bridge is reported."""
    norm=normal if normal is not None else normal_reinforcement(rebar)
    group=norm['group'];t=float(theta_C)
    if not 20<=t<=800:raise MaterialError('Температура арматуры вне 20–800 °C (таблица 10 начинается с 200 °C)')
    if t<200:
        # 20C coefficients are ordinary-temperature values, interpolated to 200C;
        # neither the normative table nor §8.2.18 dictates the interpolation.
        k,_=_interp(t,(20.,200.),(1.,STEEL_GROUPS[group]['k'][0]),'Предтабличный диапазон ks')
        beta,_=_interp(t,(20.,200.),(1.,STEEL_GROUPS[group]['beta'][0]),'Предтабличный диапазон beta')
        mode='engineering_bridge_20_200_not_tabulated'
    else:
        k,mode=_interp(t,STEEL_TEMP,STEEL_GROUPS[group]['k'],'Таблица 10 — ks')
        beta,_=_interp(t,STEEL_TEMP,STEEL_GROUPS[group]['beta'],'Таблица 10 — beta')
    return {'theta_C':t,'group':group,'k_s':k,'beta_E':beta,
            'f_yk_theta_MPa':None if norm['f_yk_MPa'] is None else norm['f_yk_MPa']*k,
            'E_s_theta_GPa':norm['E_s_GPa']*beta,'mode':mode,
            'source':'СП 2.02.05-2026 §8.2.18, table 10'}


def concrete_thermal_strain_coefficients(family:str,theta_C:float):
    if family not in ALPHA_BT_MICRO:raise MaterialError('Таблицы 11–12: только тяжёлый силикатный/карбонатный бетон')
    t=float(theta_C)
    if not 20<=t<=1100:raise MaterialError('Таблицы 11–12 применимы для 20–1100 °C')
    tclamp=min(700.,max(50.,t))
    a,mode=_interp(tclamp,THERMAL_T,ALPHA_BT_MICRO[family],'Таблица 11')
    sh,_=_interp(tclamp,THERMAL_T,ALPHA_CS_MICRO[family],'Таблица 12')
    return {'theta_C':t,'alpha_bt_per_C':a*1e-6,'alpha_cs_per_C':sh*1e-6,
            'mode':'tabulated_plateau' if t<50 or t>700 else mode,
            'source':'СП 2.02.05-2026 §8.2.19, tables 11–12'}


def steel_thermal_expansion(theta_C:float):
    t=float(theta_C)
    if not math.isfinite(t) or not 20<=t<=800:raise MaterialError('§8.2.19 eq. 6 applies only for 20–800 °C')
    return {'theta_C':t,'alpha_s_per_C':(0.005*t+11.5)*1e-6,
            'source':'СП 2.02.05-2026 §8.2.19, eq. (6)'}



def classify_fine_grained(column:dict):
    """Derive concrete kind from *actual* coarse aggregate specification.

    Belarus SP 5.03.01-2020 §6.1.2.1 distinguishes fine-grained concrete
    separately; class C, dry density and siliceous family do NOT identify it.
    The old 'fine_grained' GUI switch is intentionally never authoritative.
    """
    m=(column.get('material_spec') or {}).get('concrete') or {}
    l=column.get('annex_l_spec') or {}
    old=column.get('spalling') or {}
    amount=l.get('coarse_aggregate_volume_pct')
    source='annex_l_spec.coarse_aggregate_volume_pct'
    if amount is None and old.get('aggregate_pct') is not None:
        amount=old['aggregate_pct']
        source='archived_user_mix.aggregate_pct'
    if amount is not None:
        try:q=float(amount)
        except (TypeError,ValueError):
            return {'status':'invalid','fine_grained':None,
                    'reason':'Некорректное содержание крупного заполнителя'}
        if not math.isfinite(q) or q<0 or q>100:
            return {'status':'invalid','fine_grained':None,
                    'reason':'Содержание крупного заполнителя должно быть 0–100 %'}
        if q==0 and m.get('modulus_aggregate')=='gravel_granite_upto40':
            return {'status':'conflict','fine_grained':None,
                    'reason':'В составе указано 0 % крупного заполнителя, но для Ecm выбран гранитный щебень'}
        return {'status':'resolved','fine_grained':q==0,'source':source,
                'explanation':('Крупного заполнителя нет' if q==0
                               else 'Крупный заполнитель указан в составе смеси')}
    if m.get('modulus_aggregate')=='gravel_granite_upto40':
        return {'status':'resolved','fine_grained':False,
                'source':'material_spec.concrete.modulus_aggregate',
                'explanation':'Указан крупный заполнитель: гравий/гранитный щебень до 40 мм'}
    return {'status':'unknown','fine_grained':None,
            'reason':'Требуется фактический состав заполнителя, без предположений по C и плотности'}


def resolve_materials(column:dict):
    """Pure preflight: never fabricate missing composition or approve the R-limit."""
    profile=column.get('material_spec') or {}
    concrete_spec=profile.get('concrete') or {}
    steel_spec=profile.get('steel') or {}
    issues=[]
    classification=classify_fine_grained(column)
    try:
        # Derived physical type overrides the obsolete manually stored switch.
        effective={k:v for k,v in concrete_spec.items() if k!='fine_grained'}
        effective['fine_grained']=classification['fine_grained']
        c=ConcreteMix(strength_class=column['concrete'],**effective)
        normal=normal_concrete(c)
        if classification['status'] in ('invalid','conflict'):
            normal['E_cm_GPa']=None
            normal['modulus_source']='unresolved_mix_conflict'
            issues.append(classification['reason'])
        if normal['E_cm_GPa'] is None:
            issues.extend(normal['missing'] or normal['notes'])
        # Regardless of Ecm selection, the fire-table family must be explicit.
        try:family=_family(c.strength_class,c.aggregate_family)
        except MaterialError as exc:family=None;issues.append(str(exc))
    except (MaterialError,TypeError,KeyError) as exc:
        normal=None;family=None;issues.append(str(exc))
    try:
        r=Reinforcement(grade=column.get('steel_grade','S500'),**steel_spec)
        steel=normal_reinforcement(r)
        if steel['f_yk_MPa'] is None:issues.append('fyk для данного арматурного изделия')
    except (MaterialError,TypeError) as exc:
        steel=None;issues.append(str(exc))
    return {'status':'resolved_for_property_lookup' if not issues else 'incomplete',
            'concrete':normal,'steel':steel,'fire_family':family,
            'fine_grained_classification':classification,
            'issues':issues,'source_documents':[RC_SOURCE,FIRE_SOURCE],
            'numeric_engine_qualified':False,'release':VERSION}