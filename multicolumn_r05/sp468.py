"""SP 468.1325800.2019 (amendment 1, 2023), clause 9.7 reference F index.

This is a separately labelled Russian SP 468 reference calculation. It MUST NOT
silently claim Belarus TKP compliance or overall R90. An absent concrete mix
property stays absent. No Eurocode C-to-Russian B class mapping is assumed.

Grounding: Tables 9.1-9.6, equations (9.1)-(9.6), clauses 9.7-9.9.
All concentrations, porosity and moisture in the equation are volume fractions.
"""
from __future__ import annotations

import math
from typing import Any

SOURCE = 'СП 468.1325800.2019, Изменение № 1 (2023), §9.7, таблицы 9.1–9.6'
SOURCE_URL = 'https://internet-law.ru/documents/prod/pravila/0/sp_39284.html'
A_F = 1.16e-2  # equation (9.1), W m^(5/2) / kg

AGGREGATES = {
    'granite': 'Природный песок и гранитный щебень',
    'limestone_gravel': 'Природный песок и известняковый щебень',
    'limestone_all': 'Известняковые песок и щебень',
    'expanded_clay': 'Природный песок и крупный керамзит',
}
CURING = {
    'normal': 'Нормальное твердение',
    'steam_atmospheric': 'Тепловлажностная обработка при атмосферном давлении',
    'autoclave': 'Автоклавная обработка',
}
B_CLASSES = ('B7.5', 'B15', 'B22.5', 'B30', 'B40', 'B45', 'B55', 'B60')
ENUMS = {
    'aggregate_type': AGGREGATES,
    'strength_class_B': {x:x for x in B_CLASSES},
    'curing': CURING,
}
INPUT_FIELDS = (
    'aggregate_type', 'strength_class_B', 'curing',
    'aggregate_pct', 'dry_density_kg_m3', 'cement_kg_m3',
    'water_cement_ratio', 'design_relative_humidity_pct',
    'max_aggregate_mm',
    'aggregate_porosity_fraction', 'aggregate_volume_fraction',
)
NUMERIC_RANGES = {
    'aggregate_pct': (40.,60.),  # lambda table 9.3, don't extrapolate
    'dry_density_kg_m3': (1000.,3000.),
    'cement_kg_m3': (200.,700.), # humidity table 9.6
    'water_cement_ratio': (.3,.7), # porosity table 9.4
    'design_relative_humidity_pct': (15.,75.), # table 9.6
    'max_aggregate_mm': (1.,100.),
    'aggregate_porosity_fraction': (.000001,.999),
    'aggregate_volume_fraction': (.000001,1.0),
}
REQUIRED = INPUT_FIELDS[:9]
# Table 9.1: tabulated values αbt×10^6, 1/C at aggregate 40/60/80%.
ALPHA_BT_MICRO = {
    'granite': (9.2,9.3,9.5),
    'limestone_gravel': (6.2,5.2,4.4),
    'limestone_all': (4.7,4.3,4.0),
    'expanded_clay': (8.0,7.6,7.2),
}
# Table 9.3: λ at 40/60% aggregate content, W/(m K).
LAMBDA_250 = {
    'granite': (1.9,2.3),
    'limestone_gravel': (1.3,2.0),
    'limestone_all': (0.9,1.4),
    'expanded_clay': (0.4,0.3),
}
# Table 9.2: heated modulus Ebt ×10^-4, MPa, for B7.5...B60.
EBT_1E4_HEAVY = (1.0,1.4,1.7,2.0,2.2,2.3,2.3,2.4)
EBT_1E4_LIGHT = {
    1400: (0.6,0.7,0.8,None,None,None,None,None),
    1800: (0.7,0.9,1.1,1.2,None,None,None,None),
    2200: (None,1.1,1.3,1.4,None,None,None,None),
}
# Table 9.5: K'1 at 20 and 50% coarse aggregate, MN m^-3/2.
K1_ENDPOINTS = {
    'granite': (.42,.53),
    'limestone_gravel': (.35,.44),
}
# Table 9.6: Wb*100 (equilibrium moisture mass percent).
WB_MASS_PERCENT = {
    200: (.5,.6,.9,1.2),
    300: (.9,1.0,1.3,2.5),
    400: (1.2,1.5,2.1,3.0),
    500: (1.5,2.0,2.7,3.8),
    700: (2.1,3.0,3.9,5.4),
}
WB_HUMIDITY_GRID = (15.,25.,50.,75.)
# Table 9.7 for expanded clay aggregate alone, kg/kg.
CLAY_WB = {15.: .006,25.: .0075,50.: .012,75.: .015,100.: .028}


def _interpolate(x:float, xs, ys) -> float:
    """Only interpolate *inside* a tabulated interval; never extrapolate."""
    if not xs[0] <= x <= xs[-1]:
        raise ValueError(f'{x:g}: вне диапазона таблицы [{xs[0]}, {xs[-1]}]')
    for i,(a,b) in enumerate(zip(xs,xs[1:])):
        if a<=x<=b:
            return float(ys[i]+(ys[i+1]-ys[i])*(x-a)/(b-a))
    return float(ys[-1])


def required_fields(data:dict) -> list[str]:
    result=[k for k in REQUIRED if data.get(k) is None or data.get(k)=='']
    if data.get('aggregate_type')=='expanded_clay':
        result.extend(k for k in INPUT_FIELDS[9:] if data.get(k) is None or data.get(k)=='')
    return result


def _invalid_base(error,field=None):
    return {'method':SOURCE,'source':SOURCE_URL,'formula':'F=(a*alpha_bt*E_bt*rho*W_e)/(K1_prime*lambda*porosity)',
            'status':'invalid','F':None,'error':error,'field':field,'claim_of_fire_resistance':False,
            'thresholds':{'low':4.,'high':6.},'source_type':'SP468_reference'}


def assessment(data:dict|None) -> dict[str,Any]:
    data=data or {}
    base={'method':SOURCE,'source':SOURCE_URL,
          'source_type':'SP468_reference',
          'formula':'F=(a*alpha_bt*E_bt*rho*W_e)/(K1_prime*lambda*porosity)',
          'thresholds':{'low':4.0,'high':6.0},'threshold':4.,
          'status':'not_evaluated','F':None,'missing':[],
          'claim_of_fire_resistance':False,
          'warning':'СП 468 (РФ): справочный расчёт. Не заключение R90 и не проверка ТКП (РБ).'}
    missing=required_fields(data)
    base['missing']=missing
    if missing:return base
    vals={}
    for k in INPUT_FIELDS:
        v=data.get(k)
        if v is None or v=='':continue
        if k in ENUMS:
            if v not in ENUMS[k]:return {**base,**_invalid_base(f'Неизвестное значение {k}: {v}',k)}
            vals[k]=v
        else:
            try:
                x=float(v)
                if not math.isfinite(x):raise ValueError('нечисловое значение')
                lo,hi=NUMERIC_RANGES[k]
                if not lo<=x<=hi:raise ValueError(f'разрешено {lo:g}…{hi:g}')
                vals[k]=x
            except (ValueError,TypeError) as e:
                return {**base,**_invalid_base(f'{k}: {e}',k)}
    agg=vals['aggregate_type'];p=vals['aggregate_pct'];b=vals['strength_class_B'];curing=vals['curing']
    alpha=_interpolate(p,(40.,60.,80.),ALPHA_BT_MICRO[agg])*1e-6
    if curing!='normal':alpha*=1.1  # Table 9.1 note
    lam=_interpolate(p,(40.,60.),LAMBDA_250[agg])
    if agg=='expanded_clay':
        rho=vals['dry_density_kg_m3']
        if rho not in EBT_1E4_LIGHT:
            return {**base,**_invalid_base('Для керамзита плотность должна точно соответствовать строке 1400, 1800 или 2200 кг/м³ таблицы 9.2', 'dry_density_kg_m3')}
        e4=EBT_1E4_LIGHT[int(rho)][B_CLASSES.index(b)]
        if e4 is None:return {**base,**_invalid_base('Для выбранных плотности и класса B таблица 9.2 не содержит Ebt','strength_class_B')}
    else:
        if vals['dry_density_kg_m3']<2200:
            return {**base,**_invalid_base('Для тяжёлого бетона требуется плотность ≥ 2200 кг/м³','dry_density_kg_m3')}
        e4=EBT_1E4_HEAVY[B_CLASSES.index(b)]
    ebt=float(e4)*1e4
    if curing=='steam_atmospheric':ebt*=.9
    elif curing=='autoclave':ebt*=.77
    cement=vals['cement_kg_m3'];wc=vals['water_cement_ratio']
    porosity=cement*(wc-.2)*1e-3 if wc>=.4 else wc*cement*.8e-3
    wb_mass_pct=_interpolate(cement,list(WB_MASS_PERCENT),[
        _interpolate(vals['design_relative_humidity_pct'],WB_HUMIDITY_GRID,row)
        for row in WB_MASS_PERCENT.values()])
    wb=wb_mass_pct/100
    we=wb*vals['dry_density_kg_m3']/1000  # equation 9.5
    if agg in K1_ENDPOINTS:
        # K1 table 9.5 interpolation from 20 to 50%, saturation >=50.
        k1=_interpolate(min(max(p,20.),50.),(20.,50.),K1_ENDPOINTS[agg])
    elif agg=='expanded_clay':
        k1=.31
        porosity+=vals['aggregate_porosity_fraction']*vals['aggregate_volume_fraction']  # (9.4)
        wcl=_interpolate(vals['design_relative_humidity_pct'],list(CLAY_WB),list(CLAY_WB.values()))
        we+=(vals['aggregate_volume_fraction']*vals['dry_density_kg_m3']*wcl/1000)
    else:
        # Table 9.5 does not specify limestone sand+stone K1.
        return {**base,'missing':['K1_prime: not tabulated for limestone sand and stone in table 9.5'],
                'coefficients':{'alpha_bt_per_C':alpha,'E_bt_MPa':ebt,'lambda_W_mK':lam,'porosity_fraction':porosity,'W_e_fraction':we},
                'warning':'Таблица 9.5 не даёт K1 для известняковых песка и щебня — F не вычислен.'}
    if vals['max_aggregate_mm']>10:k1*=1.14
    if curing!='normal':k1/=1.4
    if not (0<porosity<1):return {**base,**_invalid_base('Расчётная пористость Π вне (0;1), проверьте В/Ц и состав','water_cement_ratio')}
    if not (0<we<1):return {**base,**_invalid_base('Расчётная объёмная влажность Wэ вне (0;1)','design_relative_humidity_pct')}
    F=A_F*alpha*ebt*vals['dry_density_kg_m3']*we/(k1*lam*porosity)
    if not math.isfinite(F):return {**base,**_invalid_base('Переполнение индекса F')}
    status=('index_at_or_below_threshold' if F<=4 else
            'requires_structural_check' if F<6 else 'protection_required')
    coeff={'a_W_m2p5_per_kg':A_F,'alpha_bt_per_C':alpha,'E_bt_MPa':ebt,
           'rho_kg_m3':vals['dry_density_kg_m3'],'K1_prime_MN_m_neg1p5':k1,
           'lambda_W_mK':lam,'porosity_fraction':porosity,'W_e_fraction':we,
           'W_b_mass_fraction':wb,'aggregate_fraction':p/100}
    return {**base,'status':status,'F':F,'missing':[],
            'coefficients':coeff,'input_values':vals,
            'provenance':{
                'alpha_bt':'table 9.1'+(' ×1.1 curing' if curing!='normal' else ''),
                'E_bt':'table 9.2'+(' ×0.9 atmospheric steam' if curing=='steam_atmospheric' else ' ×0.77 autoclaved' if curing=='autoclave' else ''),
                'lambda':'table 9.3',
                'porosity':'equations 9.2–9.4',
                'K1_prime':'table 9.5; >10mm ×1.14; heat treated ÷1.4',
                'W_e':'table 9.6 and equation 9.5'+(' plus table 9.7 and equation 9.6' if agg=='expanded_clay' else ''),
            }}