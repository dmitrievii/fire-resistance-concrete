"""R0.6.2: normative *analytical* thermal methods, SP 2.02.05-2026 Annex K.

Sources: supplied official PDF pp. 149-153, Annex K, eqs K.1--K.12,
K.20--K.28, tables K.1, K.2; sec. 8.2.21 for critical isotherm.
The formulas are steady analytical *standard-fire time approximation*, NOT
transient finite-element heat transfer. No custom fire curve is implied.

The following are intentionally NOT claimed here:
- Ring/hollow/centrifuged sections (K.14--K.19, table K.3): future adapter;
- a certified integration of 2D temperature fields into a ULS/second-order
  mechanical model (stages R0.6.3 onwards);
- valid temperatures for slender one-face sections beyond K.6's x<=0.7h;
- normative interpolation of tab K.2 density: in-between is explicitly
  flagged as engineering linear interpolation rather than exact table value;
- a numerical threshold-area integration as an Annex K.27 analytic result.

All coordinates in mm at public interfaces, coefficients in SI as indicated.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import math
import numpy as np

VERSION = 'R0.6.2-annex-K-v1'
SOURCE = 'СП 2.02.05-2026, приложение К, с. 145--149 (PDF с. 149--153)'
FIRE_SOURCE = 'СП 2.02.05-2026, п. 8.2.21'
FACE_NAMES = ('left', 'right', 'bottom', 'top')
CONCRETE_FAMILIES = ('siliceous', 'calcareous', 'expanded_clay')
MODEL_CHOICES = ('table_K1', 'formula_K1_450C')

# Table K.1: A [W/(m C)], B [W/(m C^2)], D [kJ/(kg C)],
# E [kJ/(kg C^2)], Wc [mass %], a_red [m^2/h].
TABLE_K1 = {
    'siliceous': {'A': 1.20, 'B': -0.00035, 'D': 0.71, 'E': 0.00083,
                  'Wc_pct': 2.5, 'a_red_m2_h': 0.00133},
    'calcareous': {'A': 1.14, 'B': -0.00055, 'D': 0.71, 'E': 0.00083,
                   'Wc_pct': 3.0, 'a_red_m2_h': 0.00116},
    'expanded_clay': {'A': 0.36, 'B': 0.00012, 'D': 0.83, 'E': 0.00042,
                       'Wc_pct': 5.0, 'a_red_m2_h': 0.000734},
}
# Table K.2, *discrete* dry densities and tabulated phi1,phi2.
TABLE_K2 = {
    'rho_kg_m3': (800., 1100., 1400., 1700., 2000., 2400.),
    'phi_1': (.52, .56, .57, .59, .61, .63),
    'phi_2': (.9, .8, .7, .6, .5, .5),
}

class ThermalError(ValueError):
    """Source, domain, or input violation for the normative thermal model."""

@dataclass(frozen=True)
class ThermalProfile:
    family: str
    dry_density_kg_m3: float
    a_red_mode: str = 'table_K1'
    moisture_mass_pct: float | None = None

    def validate(self) -> None:
        if self.family not in CONCRETE_FAMILIES:
            raise ThermalError('Приложение К, таблица К.1: неизвестный вид бетона')
        if self.a_red_mode not in MODEL_CHOICES:
            raise ThermalError('Приложение К: неизвестный метод определения a_red')
        rho = float(self.dry_density_kg_m3)
        if not math.isfinite(rho) or not TABLE_K2['rho_kg_m3'][0] <= rho <= TABLE_K2['rho_kg_m3'][-1]:
            raise ThermalError('Таблица К.2: сухая плотность только 800--2400 кг/м3, экстраполяция запрещена')
        if self.moisture_mass_pct is not None:
            w = float(self.moisture_mass_pct)
            if not math.isfinite(w) or not 0 <= w <= 30:
                raise ThermalError('Массовая влажность Wc должна быть конечной, 0--30 %')

@dataclass(frozen=True)
class RectangularExposure:
    b_mm: float
    h_mm: float
    faces: tuple[str, ...]

    def validate(self):
        if not math.isfinite(float(self.b_mm)) or not math.isfinite(float(self.h_mm)) or min(self.b_mm,self.h_mm)<=0:
            raise ThermalError('Размеры сечения должны быть положительными конечными')
        if not 1 <= len(self.faces) <= 4 or len(set(self.faces)) != len(self.faces):
            raise ThermalError('От 1 до 4 различных нагреваемых сторон')
        if any(face not in FACE_NAMES for face in self.faces):
            raise ThermalError('Неизвестная нагреваемая сторона')


def property_K1(family: str, theta_C: float):
    """Normative material relations K.2,K.3 for given theta in degrees Celsius."""
    if family not in TABLE_K1:raise ThermalError('Неизвестный бетон таблицы К.1')
    theta = float(theta_C)
    if not math.isfinite(theta) or theta < 20 or theta > 1220:
        raise ThermalError('Температура вне диапазона применимости проверенной формулы К.2--К.3 (20--1220 °C)')
    q=TABLE_K1[family]
    lam=q['A']+q['B']*theta
    cp=q['D']+q['E']*theta
    if lam<=0 or cp<=0:raise ThermalError('Теплопроводность/теплоёмкость не положительна')
    return {'lambda_W_mK':lam, 'C_kJ_kgK':cp, 'theta_C':theta, 'source': 'К.2, К.3; таблица К.1'}


def _between_table(x, keys, values, label):
    x=float(x)
    for i,key in enumerate(keys):
        if x==key:return float(values[i]),'tabulated'
    for i in range(1,len(keys)):
        if keys[i-1]<x<keys[i]:
            value=values[i-1]+(values[i]-values[i-1])*(x-keys[i-1])/(keys[i]-keys[i-1])
            return float(value),'engineering_linear_interpolation_not_explicit_in_K2'
    raise ThermalError(label+': экстраполяция запрещена')


def resolve_profile(profile: ThermalProfile):
    """K.1--K.3, K.2 table; SI consistent, with explicit interpolation provenance."""
    profile.validate()
    q=TABLE_K1[profile.family]
    phi1,src1=_between_table(profile.dry_density_kg_m3,TABLE_K2['rho_kg_m3'],TABLE_K2['phi_1'],'phi1')
    phi2,src2=_between_table(profile.dry_density_kg_m3,TABLE_K2['rho_kg_m3'],TABLE_K2['phi_2'],'phi2')
    w=profile.moisture_mass_pct if profile.moisture_mass_pct is not None else q['Wc_pct']
    if profile.a_red_mode=='table_K1':
        a=q['a_red_m2_h']
        source='таблица К.1, готовое a_red'
        if profile.moisture_mass_pct is not None and abs(w-q['Wc_pct'])>1e-12:
            raise ThermalError('a_red из таблицы К.1 нельзя совмещать с иной заданной влажностью; используйте формулу К.1')
    else:
        thermo=property_K1(profile.family,450.)
        # K.1: C in kJ/(kg C), W_c in MASS PERCENT, rho in kg/m3.
        # The factor 3.6 converts W/(m K) to kJ/(m h K).
        a=3.6*thermo['lambda_W_mK']/((thermo['C_kJ_kgK']+0.05*w)*profile.dry_density_kg_m3)
        source='формула К.1; K.2, K.3 при 450 °C (упрощение К.1.2)'
    if not math.isfinite(a) or a<=0:raise ThermalError('Недопустимая температуропроводность')
    return {'a_red_m2_h':a,'phi_1':phi1,'phi_2':phi2,
            'Wc_mass_percent':float(w),'rho_dry_kg_m3':float(profile.dry_density_kg_m3),
            'material_family':profile.family,'a_red_source':source,
            'K2_density_status':src1 if src1==src2 else f'{src1}; {src2}',
            'coefficients_source':SOURCE,'release':VERSION,
            'normative_table_nodes':src1=='tabulated' and src2=='tabulated'}


def heating_depth_m(a_red_m2_h:float,t_minutes:float):
    """K.12: sqrt(12 a_red tau), tau in HOURS."""
    t=float(t_minutes)
    if not math.isfinite(t) or t<0 or t>240:
        raise ThermalError('Стандартный огневой нагрев: время 0--240 мин; диапазон R0.6.2')
    if not math.isfinite(float(a_red_m2_h)) or a_red_m2_h<=0:raise ThermalError('Недопустимое a_red')
    return math.sqrt(12*a_red_m2_h*t/60.)


def _relative_distance(x_m:np.ndarray, a:float, phi1:float, phi2:float, d_m:float, l_m:float):
    if l_m==0:return np.ones_like(x_m,dtype=float)
    # xi = distance to concrete surface. For bar temperature, K.5 yi is
    # interpreted as clear distance to bar outer surface; preserve this choice
    # explicitly in the provenance and test against the K18 reference.
    equivalent=x_m-(d_m/2 if d_m>0 else 0)+phi1*math.sqrt(a)+(phi2*d_m if d_m>0 else 0)
    return np.minimum(1.,np.maximum(0.,equivalent/l_m))


def temperature_rectangle(exposure:RectangularExposure, coeff:dict, t_minutes:float,
                          x_mm:Any, y_mm:Any, bar_diameter_mm:float=0):
    """Equations K.4--K.12: temperatures at concrete points or bar surfaces.

    Input arrays broadcast; public values in mm, resulting temperatures in C.
    A one-face K.6 limit flag is returned separately, not silently ignored.
    """
    exposure.validate()
    b=exposure.b_mm/1000.;h=exposure.h_mm/1000.
    t=float(t_minutes); a=float(coeff['a_red_m2_h'])
    d=float(bar_diameter_mm)/1000.
    if not math.isfinite(d) or d<0:raise ThermalError('Диаметр стержня должен быть неотрицателен')
    x,y=np.broadcast_arrays(np.asarray(x_mm,dtype=float)/1000,np.asarray(y_mm,dtype=float)/1000)
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        raise ThermalError('Координаты должны быть конечными')
    if np.any(x<0) or np.any(y<0) or np.any(x>b) or np.any(y>h):
        raise ThermalError('Точка вне поперечного сечения')
    if d>0 and (np.any(x<d/2) or np.any(b-x<d/2) or np.any(y<d/2) or np.any(h-y<d/2)):
        raise ThermalError('Арматурный стержень пересекает поверхность бетона')
    l=heating_depth_m(a,t)
    if l==0:
        z=np.full(x.shape,20.,dtype=float)
        return z,{'K_equation':'initial_temperature','time_minutes':t,
                  'in_one_face_0_7h':np.ones(x.shape,dtype=bool),
                  'outside_approximation_C':np.zeros(x.shape,dtype=bool),'l_m':0.}
    phi1,phi2=float(coeff['phi_1']),float(coeff['phi_2'])
    dist={'left':x,'right':b-x,'bottom':y,'top':h-y}
    r={f:_relative_distance(dist[f],a,phi1,phi2,d,l) for f in exposure.faces}
    faces=set(exposure.faces)
    one_face_ok=np.ones(x.shape,dtype=bool)
    p=lambda f:(1-r[f])**2
    if len(faces)==1:
        f=next(iter(faces));depth=b if f in ('left','right') else h
        one_face_ok=dist[f]<=0.7*depth+1e-12
        theta=20+1200*p(f)
        eq='К.6'
    elif len(faces)==2:
        if faces in ({'left','right'},{'bottom','top'}):
            f1,f2=sorted(faces)
            theta=20+1200*(p(f1)+p(f2))
            eq='К.7'
        else:
            f1,f2=sorted(faces)
            theta=1220-1200*(1-p(f1))*(1-p(f2))
            eq='К.8'
    elif len(faces)==3:
        pair=('left','right') if {'left','right'}.issubset(faces) else ('bottom','top')
        f3=next(iter(faces-set(pair)))
        theta=1220-1200*(1-p(pair[0])-p(pair[1]))*(1-p(f3))
        eq='К.9'
    else:
        theta=1220-1200*(1-p('left')-p('right'))*(1-p('bottom')-p('top'))
        eq='К.10'
    # The strict validity filter is separate from the literal expression.
    # K.7/K.9 can exceed the 1220C approximation in overlapping heat layers.
    return theta,{'K_equation':eq,'time_minutes':t,
                  'in_one_face_0_7h':one_face_ok,
                  'outside_approximation_C':(theta<20-1e-8)|(theta>1220+1e-8),
                  'l_m':l}


def critical_temperature_C(concrete_class:str,family:str):
    """SP 2.02.05-2026, §8.2.21, heavy concrete only."""
    if family not in ('siliceous','calcareous'):return None
    if concrete_class in ('C12/15','C16/20','C20/25','C25/30','C30/37',
                          'C35/45','C40/50','C45/55','C50/60'):
        return 600. if family=='calcareous' else 500.
    if concrete_class in ('C55/67','C60/75'):return 460.
    if concrete_class in ('C70/85','C80/95'):return 400.
    return None


def _crit_single_relative(theta_critical_C):
    # Eq K.20: r for one heated face.
    return 1-math.sqrt((theta_critical_C-20)/1200)


def _crit_corner_relative(theta_critical_C):
    # Eq K.22: two perpendicular faces.
    return 1-math.sqrt(1-math.sqrt((1220-theta_critical_C)/1200))


def square_four_face_reduced_section(exposure:RectangularExposure,coeff:dict,t_minutes:float,
                                     theta_critical_C:float):
    """Annex K.3.4, K.20--K.28; square with FOUR heated sides only.

    K.27 obtains area without a generic rectangular assumption. Out-of-domain
    arithmetic returns status, not fabricated area. The profile can still be
    used for temperature-only evaluations when this formula cannot be used.
    """
    exposure.validate()
    if len(exposure.faces)!=4 or abs(exposure.b_mm-exposure.h_mm)>1e-9:
        return {'status':'not_applicable','reason':'К.27: только квадрат, нагреваемый с четырёх сторон',
                'source':SOURCE}
    t=float(t_minutes);l=heating_depth_m(coeff['a_red_m2_h'],t)
    if l==0:return {'status':'evaluated','remaining_area_m2':(exposure.b_mm/1000.)**2,
                   'lost_area_m2':0.,'theta_critical_C':float(theta_critical_C),
                   'psi':1.,'lc_m':0.,'ld_m':0.,'delta_m':0.,'source':'К.27 (t=0)' }
    if not 20<theta_critical_C<1220:raise ThermalError('Критическая температура вне К.20--К.22')
    side=exposure.h_mm/1000.;phi1=coeff['phi_1'];a=coeff['a_red_m2_h']
    offset=phi1*math.sqrt(a)
    r_side=_crit_single_relative(theta_critical_C)
    r_corner=_crit_corner_relative(theta_critical_C)
    lc=r_side*l-offset
    ld=r_corner*l-offset
    # eq K.26 relative depth in the centre; K.25 is defined for r<=1.
    r_mid=min(1.,(side/2+offset)/l)
    w=1-2*(1-r_mid*r_mid)**2
    if w<=0:
        return {'status':'out_of_scope','reason':'К.25: недопустимое w<=0 (прогретое сечение)',
                'source':SOURCE}
    discr=(1220*w-1220+theta_critical_C)/(1200*w)
    if discr<0:
        return {'status':'out_of_scope','reason':'К.24: отрицательный подкоренной аргумент',
                'source':SOURCE}
    r3=1-math.sqrt(discr)
    delta=r3*l-offset
    if min(lc,ld,delta)<0:
        # Do not silently clip Annex K.21; this is a model/domain note.
        return {'status':'out_of_scope','reason':'К.21/К.23: расчётная толщина отрицательна',
                'raw':{'lc_m':lc,'ld_m':ld,'delta_m':delta},'source':SOURCE}
    if max(lc,ld,delta)>=side/2 or abs(side/2-lc)<1e-12:
        return {'status':'out_of_scope','reason':'К.27--К.28: остаточное сечение отсутствует',
                'source':SOURCE}
    psi=(side/2-ld)/(side/2-lc)-.2
    if psi<=0:
        return {'status':'out_of_scope','reason':'К.28: psi<=0', 'source':SOURCE}
    psi=min(1.,psi)  # explicitly prescribed maximum in K.3.4
    area=psi*(side-2*lc)**2
    if area<0 or area>side*side+1e-9:raise ThermalError('К.27: недопустимая остаточная площадь')
    return {'status':'evaluated','remaining_area_m2':area,'lost_area_m2':side*side-area,
            'theta_critical_C':theta_critical_C,'lc_m':lc,'ld_m':ld,'delta_m':delta,
            'psi':psi,'r_parallel':r_mid,'r3':r3,'w':w,'source':'К.20--К.28',
            'release':VERSION}


def evaluate_rectangular_column(column:dict, grid=30):
    """Pure report/UI facade. Never asserts R(t) or a normative resistance PASS.

    Missing real aggregate or density remains 'not_evaluated'. Existing K18
    diagnostic mechanical solver is NOT replaced by this one.
    """
    c=column;tp=c.get('thermal_spec') or {}
    material=(c.get('material_spec') or {}).get('concrete') or {}
    family=tp.get('concrete_family') or material.get('aggregate_family')
    if family not in CONCRETE_FAMILIES:
        return {'status':'not_evaluated','missing':['тип заполнителя К.1'],
                'qualified_mechanics':False,'source':SOURCE,'release':VERSION}
    rho=tp.get('dry_density_kg_m3')
    if rho is None:
        return {'status':'not_evaluated','missing':['сухая плотность для таблицы К.2'],
                'qualified_mechanics':False,'source':SOURCE,'release':VERSION}
    if not 8<=int(grid)<=120:
        raise ThermalError('Размер сетки 8--120')
    if material.get('aggregate_family') and material['aggregate_family']!=family:
        return {'status':'invalid','reason':'Несовпадение заполнителя в материалах R0.6.1 и теплотехнике',
                'qualified_mechanics':False,'source':SOURCE}
    faces=tp.get('exposed_faces',FACE_NAMES)
    try:
        p=ThermalProfile(family=family,dry_density_kg_m3=float(rho),
                         a_red_mode=tp.get('a_red_mode','table_K1'),
                         moisture_mass_pct=tp.get('moisture_mass_pct'))
        coeff=resolve_profile(p)
        ex=RectangularExposure(b_mm=float(c['b_mm']),h_mm=float(c['h_mm']),faces=tuple(faces))
        ex.validate()
        minutes=float(c['fire_minutes'])
        # use cell CENTRES (not hot boundary), reporting full 2-D field
        x_mm=(np.arange(grid)+0.5)*ex.b_mm/grid
        y_mm=(np.arange(grid)+0.5)*ex.h_mm/grid
        xx,yy=np.meshgrid(x_mm,y_mm,indexing='xy')
        temp,metadata=temperature_rectangle(ex,coeff,minutes,xx,yy)
        if np.any(~np.isfinite(temp)):
            raise ThermalError('Нечисловая температура в области')
        bars=[]
        for bar in c.get('bars',[]):
            value,bar_scope=temperature_rectangle(ex,coeff,minutes,float(bar['x_mm']),
                float(bar['y_mm']),float(bar['diameter_mm']))
            bars.append({'id':str(bar['id']),'x_mm':float(bar['x_mm']),
                         'y_mm':float(bar['y_mm']),'diameter_mm':float(bar['diameter_mm']),
                         'theta_C':float(value),'in_scope_K6':bool(np.all(bar_scope['in_one_face_0_7h']))})
        critical=critical_temperature_C(c['concrete'],family)
        reduced=(square_four_face_reduced_section(ex,coeff,minutes,critical)
                 if critical is not None else {'status':'not_applicable','reason':'Критическая изотерма не задана в 8.2.21'})
        issues=[]
        if not np.all(metadata['in_one_face_0_7h']) or any(not x['in_scope_K6'] for x in bars):
            issues.append('К.6: точки вне x<=0,7h, требуются иные решения для полного поля')
        if np.any(metadata['outside_approximation_C']) or any(b['theta_C']>1220 for b in bars):
            issues.append('Результат К.7/К.9/К.10 вне интервала 20--1220 °C; не квалифицирован')
        if not coeff['normative_table_nodes']:
            issues.append('К.2: промежуточная плотность; линейная интерполяция не прописана в тексте')
        if reduced.get('status')=='out_of_scope':issues.append(reduced['reason'])
        if critical is None:issues.append('Критическая температура отсутствует для выбранного типа/класса')
        status='evaluated_with_scope_warnings' if issues else 'evaluated'
        return {'status':status,'source':SOURCE,'release':VERSION,'qualified_mechanics':False,
                'formula':metadata['K_equation'],'coefficients':coeff,
                'exposed_faces':list(ex.faces),'fire_minutes':minutes,
                'max_temperature_C':float(temp.max()),'min_temperature_C':float(temp.min()),
                'critical_temperature_C':critical,'critical_section':reduced,
                'reinforcement':bars,'issues':issues,
                'field':{'x_mm':x_mm.tolist(),'y_mm':y_mm.tolist(),
                         'temperature_C':temp.tolist(),'grid':int(grid)}}
    except (KeyError,TypeError,ValueError,ThermalError) as exc:
        return {'status':'invalid','source':SOURCE,'release':VERSION,
                'qualified_mechanics':False,'reason':str(exc)}