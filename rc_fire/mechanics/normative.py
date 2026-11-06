"""R0.6.3: temperature-dependent RC *section* mechanics, Belarus СП.

Sources: СП 5.03.01-2020 §§4.2.5.3, 6.1.2.11, 6.1.5.4,
6.2.2.12--13, 8.1.2.1--4; СП 2.02.05-2026 §§8.2.16--8.2.20,
Tables 9--10. Numerical quadrature / Newton solver are implementations,
not a claim that an entire member passes R90.

Contract boundaries:
- rectangular sections / individual straight unprestressed bars;
- 1st-order N, Mx, My only, using plane-section compatibility;
- compression-positive, x rightward, y upward, positive Mx compresses +y,
  positive My compresses +x;
- no second-order member effects, thermal restraint forces, shear, bond or
  spalling; thermal free strains reserved for whole-member coupling;
- no extrapolation beyond 800 C in Tables 9/10; optional zero-strength
  cutoff above 800 C is explicitly NON-NORMATIVE and opt-in only;
- convergence means equilibrium is found, not a certified ULS PASS.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np

from rc_fire.materials import (ConcreteMix, Reinforcement, MaterialError,
    normal_concrete)
from rc_fire.materials.normative import (CONCRETE_K, CONCRETE_BETA, FIRE_TEMP,
    STEEL_TEMP, STEEL_GROUPS, _family, normal_reinforcement)
from rc_fire.thermal import (evaluate_rectangular_column, RectangularExposure,
    temperature_rectangle)

VERSION = "R0.6.3-section-mechanics-v1"
NORMATIVE_SOURCES = (
    "СП 5.03.01-2020: 4.2.5.3, 6.1.2.11, 6.1.5.4, 6.2.2.12-13, 8.1.2.1-4",
    "СП 2.02.05-2026: 8.2.16-8.2.20, таблицы 9-10",
)
GAMMA_C_ACCIDENTAL = 1.20  # SP 5.03.01-2020 Table 4.6
GAMMA_S_ACCIDENTAL = 1.00  # SP 5.03.01-2020 Table 4.6
K_TC_RECOMMENDED = 1.00   # SP 5.03.01-2020 §6.1.2.11
MAX_TABULATED_C = 800.
TENSILE_STEEL_LIMIT = 0.010  # SP 5.03.01-2020 §8.1.2.1 verification


class SectionMechanicsError(ValueError):
    """Input invalid or outside the explicitly supported model domain."""


def alpha_cc(f_ck_MPa: float) -> float:
    """SP 5.03.01-2020 (6.5), not a calibration to the K18 worksheet."""
    f = float(f_ck_MPa)
    if not math.isfinite(f) or f <= 0:
        raise SectionMechanicsError("fck должен быть положительным")
    return min(1.0, (40.0/f)**(1.0/3.0))


def design_strengths(f_ck_MPa:float, f_yk_MPa:float, *, k_tc:float=1.) -> dict:
    """Table 4.6 accidental values, (6.4)-(6.5), (6.28)."""
    f, fy, ktc = map(float, (f_ck_MPa, f_yk_MPa, k_tc))
    if not all(math.isfinite(v) and v > 0 for v in (f,fy,ktc)):
        raise SectionMechanicsError("Прочности и ktc должны быть положительными")
    ac=alpha_cc(f)
    return {'alpha_cc':ac,'k_tc':ktc,
        'gamma_c':GAMMA_C_ACCIDENTAL,'gamma_s':GAMMA_S_ACCIDENTAL,
        'f_cd_MPa':ac*ktc*f/GAMMA_C_ACCIDENTAL,
        'f_yd_MPa':fy/GAMMA_S_ACCIDENTAL,
        'source':'СП 5.03.01-2020 табл.4.6; (6.4), (6.5), (6.28)',
        'k_tc_provenance':'recommended_1.0_not_measured'}


def concrete_parabolic_linear(strain:Any, fcd_MPa:Any,
                              eps_c2:float, eps_cu2:float, n:float):
    """(6.17)-(6.18), compression-positive; return stress and tangent (MPa).

    A trial state beyond eps_cu2 is evaluated with a continued plateau ONLY
    to keep Newton smooth. The final state is explicitly rejected by the
    ultimate-strain check, never approved at that trial plateau.
    """
    e=np.asarray(strain,dtype=float)
    f=np.asarray(fcd_MPa,dtype=float)
    if not 0 < eps_c2 <= eps_cu2 or n <= 1:
        raise SectionMechanicsError("Некорректная параболически-линейная диаграмма")
    positive=np.maximum(e,0.)
    q=np.clip(positive/eps_c2,0.,1.)
    stress=np.where(e>0,f*(1.-np.power(1.-q,n)),0.)
    tangent=np.where((e>0)&(e<eps_c2),
        f*n/eps_c2*np.power(1.-q,n-1.),0.)
    return stress,tangent


def steel_bilinear(strain:Any, f_yd_theta_MPa:Any, E_s_theta_MPa:Any):
    """§6.2.2.13 horizontal upper-branch stress-strain option."""
    e=np.asarray(strain,dtype=float)
    fy=np.asarray(f_yd_theta_MPa,dtype=float)
    E=np.asarray(E_s_theta_MPa,dtype=float)
    stress=np.clip(E*e,-fy,fy)
    tangent=np.where(np.abs(E*e)<fy,E,0.)
    return stress,tangent


@dataclass
class PreparedSection:
    """Unchanging fibre inventory for all load cases of the same column."""
    b_m:float
    h_m:float
    u:np.ndarray
    v:np.ndarray
    x_m:np.ndarray
    y_m:np.ndarray
    concrete_area_m2:np.ndarray
    concrete_fcd_MPa:np.ndarray
    concrete_Ecm_theta_MPa:np.ndarray
    bar_u:np.ndarray
    bar_v:np.ndarray
    bar_x_m:np.ndarray
    bar_y_m:np.ndarray
    bar_area_m2:np.ndarray
    bar_fyd_MPa:np.ndarray
    bar_Es_theta_MPa:np.ndarray
    bar_displaced_concrete_fcd_MPa:np.ndarray
    eps_c2:float
    eps_cu2:float
    n_parabola:float
    bar_ids:tuple[str,...]
    concrete_temperature_C:np.ndarray
    bar_temperature_C:np.ndarray
    strength_data:dict
    issues:tuple[str,...]
    out_of_table_concrete_cells:int
    out_of_table_bars:int
    grid:int

    def response(self, unknown:Any, include_maps:bool=False):
        """N [kN], Mx/My [kNm], tangent 3x3 w.r.t scaled strains.

        Unknown = [eps0, g_x, g_y]; strain = eps0 + g_x*v + g_y*u,
        v=(y-h/2)/(h/2), u=(x-b/2)/(b/2).  Actual curvatures:
        kappa_x=2*g_x/h, kappa_y=2*g_y/b (1/m).
        """
        e0,gx,gy=np.asarray(unknown,dtype=float)
        ec=e0+gx*self.v+gy*self.u
        es=e0+gx*self.bar_v+gy*self.bar_u
        eb=es  # compatible concrete strain at individual bar positions
        sc,dc=concrete_parabolic_linear(ec,self.concrete_fcd_MPa,
                        self.eps_c2,self.eps_cu2,self.n_parabola)
        sb,db=concrete_parabolic_linear(eb,self.bar_displaced_concrete_fcd_MPa,
                        self.eps_c2,self.eps_cu2,self.n_parabola)
        ss,ds=steel_bilinear(es,self.bar_fyd_MPa,self.bar_Es_theta_MPa)
        # Concrete is integrated over the gross section; replace its area at
        # actual bar centres to avoid double counting the steel volume.
        wc=sc*self.concrete_area_m2*1000.   # MPa * m2 -> kN
        wb=(ss-sb)*self.bar_area_m2*1000.
        dcw=dc*self.concrete_area_m2*1000.
        dbw=(ds-db)*self.bar_area_m2*1000.
        # Mx = N*(y-y_mid), My = N*(x-x_mid). Positive means +face compression.
        yc=self.y_m-self.h_m/2
        xc=self.x_m-self.b_m/2
        yb=self.bar_y_m-self.h_m/2
        xb=self.bar_x_m-self.b_m/2
        forces=np.array([wc.sum()+wb.sum(),
                         wc@yc+wb@yb,
                         wc@xc+wb@xb],dtype=float)
        dc_recip=np.stack((np.ones_like(ec),self.v,self.u),axis=0)
        db_recip=np.stack((np.ones_like(es),self.bar_v,self.bar_u),axis=0)
        jrowc=np.stack((np.ones_like(ec),yc,xc),axis=0)
        jrowb=np.stack((np.ones_like(es),yb,xb),axis=0)
        tangent=(jrowc*dcw[None,:])@dc_recip.T + (jrowb*dbw[None,:])@db_recip.T
        meta={'max_concrete_compression':float(np.max(ec)),
              'min_steel_strain':float(np.min(es)),
              'max_steel_strain':float(np.max(es)),
              'eps_cu2':self.eps_cu2,
              'steel_tension_limit':TENSILE_STEEL_LIMIT,
              'curvature_x_per_m':float(2*gx/self.h_m),
              'curvature_y_per_m':float(2*gy/self.b_m),
              'min_concrete_strain':float(np.min(ec)),
              'max_concrete_stress_MPa':float(np.max(sc)),
              'max_steel_stress_MPa':float(np.max(ss)),
              'min_steel_stress_MPa':float(np.min(ss))}
        if include_maps:
            meta['map']={'grid':self.grid,
                'concrete_stress_MPa':np.asarray(sc).reshape(self.grid,self.grid).tolist(),
                'concrete_strain':np.asarray(ec).reshape(self.grid,self.grid).tolist(),
                'steel_stress_MPa':ss.tolist()}
        return forces,tangent,meta


def _require_finite(v, key:str):
    try:
        f=float(v)
        if not math.isfinite(f):raise ValueError
        return f
    except (ValueError,TypeError):raise SectionMechanicsError(f'{key}: ожидается конечное число')


def prepare_section(column:dict, thermal:dict, *, grid:int=26,
                     above_800_policy:str='reject') -> PreparedSection:
    """Resolve geometry, material strength and Annex K temperatures.

    An opt-in 'zero_strength_diagnostic' policy is a conservative *numerical
    assumption* above the last tabulated node, NOT a normative coefficient.
    It must NEVER be used to issue a positive fire-resistance conclusion.
    """
    if above_800_policy not in ('reject','zero_strength_diagnostic'):
        raise SectionMechanicsError('Unsupported >800 °C policy')
    if not isinstance(grid,int) or not 12 <= grid <= 100:
        raise SectionMechanicsError('Сетка сечения: 12...100')
    if thermal.get('status') not in ('evaluated','evaluated_with_scope_warnings'):
        raise SectionMechanicsError('Нормативная теплотехника приложения К не выполнена')
    mat=column.get('material_spec') or {}
    concrete_data=mat.get('concrete') or {}
    steel_data=mat.get('steel') or {}
    cm=ConcreteMix(strength_class=column['concrete'],**concrete_data)
    rm=Reinforcement(grade=column.get('steel_grade','S500'),**steel_data)
    try:
        normal_c=normal_concrete(cm)
        normal_s=normal_reinforcement(rm)
        family=_family(cm.strength_class,cm.aggregate_family)
    except (MaterialError,ValueError,TypeError) as exc:
        raise SectionMechanicsError(str(exc)) from exc
    if normal_c['E_cm_GPa'] is None:
        raise SectionMechanicsError('Ecm не определён по СП 5.03.01-2020: '+
                  '; '.join(normal_c.get('missing') or normal_c.get('notes') or []))
    if normal_s['f_yk_MPa'] is None:
        raise SectionMechanicsError('Не задано fyk арматуры')
    if family not in CONCRETE_BETA:
        raise SectionMechanicsError('Таблица 9 не содержит beta_E для данного высокопрочного бетона')
    if cm.aggregate_family not in ('siliceous','calcareous'):
        raise SectionMechanicsError('Нормативная модель реализована для тяжелого силикатного/карбонатного бетона')
    if not 0 < float(column['b_mm']) <= 2000 or not 0 < float(column['h_mm']) <= 2000:
        raise SectionMechanicsError('Неподдерживаемые размеры сечения')
    b=float(column['b_mm'])/1000;h=float(column['h_mm'])/1000
    xx=(np.arange(grid)+.5)*b/grid
    yy=(np.arange(grid)+.5)*h/grid
    X,Y=np.meshgrid(xx,yy,indexing='xy')
    ex=RectangularExposure(column['b_mm'],column['h_mm'],
                           tuple(thermal['exposed_faces']))
    coeff=thermal['coefficients'];t=float(column['fire_minutes'])
    theta,scope=temperature_rectangle(ex,coeff,t,X*1000,Y*1000)
    if not np.all(np.isfinite(theta)) or np.any(scope['outside_approximation_C']):
        raise SectionMechanicsError('Температуры приложения К вне области применимости')
    if not np.all(scope['in_one_face_0_7h']):
        raise SectionMechanicsError('К.6: часть сечения вне x<=0,7h')
    steel_group=normal_s['group']
    bar_ids=[];bar_x=[];bar_y=[];bar_d=[];bar_theta=[];concrete_at_bar_theta=[]
    for bar in column.get('bars',[]):
        d=_require_finite(bar['diameter_mm'],'диаметр')
        bx=_require_finite(bar['x_mm'],'координата x')/1000
        by=_require_finite(bar['y_mm'],'координата y')/1000
        if d<=0 or not (d/2000<bx<b-d/2000 and d/2000<by<h-d/2000):
            raise SectionMechanicsError('Арматура пересекает грань сечения')
        th,_=temperature_rectangle(ex,coeff,t,bx*1000,by*1000,d)
        cb,_=temperature_rectangle(ex,coeff,t,bx*1000,by*1000)
        bar_ids.append(str(bar['id']));bar_x.append(bx);bar_y.append(by)
        bar_d.append(d);bar_theta.append(float(th));concrete_at_bar_theta.append(float(cb))
    if not bar_ids:
        raise SectionMechanicsError('Не заданы продольные стержни')
    te=np.asarray(theta,dtype=float).ravel()
    bar_theta=np.asarray(bar_theta)
    tbarc=np.asarray(concrete_at_bar_theta)
    count_c=int(np.sum(te>MAX_TABULATED_C))
    count_b=int(np.sum(bar_theta>MAX_TABULATED_C))
    if above_800_policy=='reject' and (count_c or count_b or np.any(tbarc>MAX_TABULATED_C)):
        raise SectionMechanicsError(f'Таблицы 9/10 заканчиваются при 800 °C: '
                     f'{count_c} волокон бетона, {count_b} стержней выше 800 °C; '
                     'экстраполяция запрещена')
    if np.any(te<20) or np.any(bar_theta<20) or np.any(tbarc<20):
        raise SectionMechanicsError('Нормативные температуры ниже 20 °C не предусмотрены')
    cd=design_strengths(normal_c['f_ck_MPa'],normal_s['f_yk_MPa'])
    n=int(grid)*int(grid)
    # No extrapolation: optional out-of-table cells are explicitly discarded
    # (zero strength assumption), not assigned a fabricated table coefficient.
    def concrete_values(arr):
        t_eval=np.minimum(arr,MAX_TABULATED_C)
        k=np.interp(t_eval,FIRE_TEMP,CONCRETE_K[family])
        beta=np.interp(t_eval,FIRE_TEMP,CONCRETE_BETA[family])
        f=cd['f_cd_MPa']*k
        E=normal_c['E_cm_GPa']*1000*beta
        if above_800_policy=='zero_strength_diagnostic':
            f=np.where(arr>MAX_TABULATED_C,0.,f)
            E=np.where(arr>MAX_TABULATED_C,0.,E)
        return f,E
    fcd,Ecm=concrete_values(te)
    fb,_=concrete_values(tbarc)
    sht=np.minimum(bar_theta,MAX_TABULATED_C)
    data=STEEL_GROUPS[steel_group]
    ks=np.interp(sht,np.r_[20.,STEEL_TEMP],np.r_[1.,data['k']])
    beta_s=np.interp(sht,np.r_[20.,STEEL_TEMP],np.r_[1.,data['beta']])
    fyd=cd['f_yd_MPa']*ks
    Es=normal_s['E_s_GPa']*1000.*beta_s
    if above_800_policy=='zero_strength_diagnostic':
        fyd=np.where(bar_theta>MAX_TABULATED_C,0.,fyd)
        Es=np.where(bar_theta>MAX_TABULATED_C,0.,Es)
    xb=np.asarray(bar_x);yb=np.asarray(bar_y)
    bar_area=np.pi*(np.asarray(bar_d)/2000.)**2
    issues=[]
    if np.any((bar_theta>20)&(bar_theta<200)):
        issues.append('В интервале 20–200 °C для арматуры использована численная интерполяция beta, отсутствующая в таблице 10')
    if above_800_policy=='zero_strength_diagnostic' and (count_c or count_b):
        issues.append('Для T>800 °C принято нулевое сопротивление (вне нормативной таблицы; только диагностика)')
    if thermal.get('status')=='evaluated_with_scope_warnings':
        issues.extend(thermal.get('issues',[]))
    issues.append('Тепловые собственные деформации не включены: только сечение при заданных внешних усилиях')
    return PreparedSection(
        b_m=b,h_m=h,u=((X.ravel()-b/2)/(b/2)),v=((Y.ravel()-h/2)/(h/2)),
        x_m=X.ravel(),y_m=Y.ravel(),
        concrete_area_m2=np.full(n,b*h/n),
        concrete_fcd_MPa=fcd,concrete_Ecm_theta_MPa=Ecm,
        bar_u=(xb-b/2)/(b/2),bar_v=(yb-h/2)/(h/2),
        bar_x_m=xb,bar_y_m=yb,bar_area_m2=bar_area,
        bar_fyd_MPa=fyd,bar_Es_theta_MPa=Es,
        bar_displaced_concrete_fcd_MPa=fb,
        eps_c2=normal_c['eps_c2_permille']/1000.,
        eps_cu2=normal_c['eps_cu2_permille']/1000.,
        n_parabola=normal_c['n_parabola'],bar_ids=tuple(bar_ids),
        concrete_temperature_C=te,bar_temperature_C=bar_theta,
        strength_data={**cd,'concrete_class':cm.strength_class,
            'concrete_family':family,'steel_group':steel_group,
            'Ecm_ambient_GPa':normal_c['E_cm_GPa'],
            'E_s_ambient_GPa':normal_s['E_s_GPa'],
            'beta_from_table_9':True,'beta_from_table_10':True,
            'deformation_diagram':'(6.17)-(6.18) with fcd,theta; steel (6.2.2.13) plateau',
            'strain_limit_source':'8.1.2.1'},
        issues=tuple(issues),out_of_table_concrete_cells=count_c,
        out_of_table_bars=count_b,grid=grid)


def solve_load(prepared:PreparedSection, N_kN:float, Mx_kNm:float,
               My_kNm:float, *, with_maps:bool=False, max_iter:int=75) -> dict:
    """Damped 3-DOF Newton first-order section equilibrium, never a ULS PASS.

    Residuals are scaled by representative design loads; tangent comes from
    integrated constitutive laws, not guessed global stiffness. Inability to
    converge is reported as unresolved, not proof of member failure.
    """
    target=np.array([_require_finite(N_kN,'N'),_require_finite(Mx_kNm,'Mx'),
                     _require_finite(My_kNm,'My')],dtype=float)
    if not np.isfinite(target).all():raise SectionMechanicsError('Нагрузка не конечная')
    scales=np.array([max(100.,abs(target[0])),
                     max(20.,abs(target[1])),max(20.,abs(target[2]))])
    # Start with a physically small compatible compressive strain state and
    # independent signed moment gradients, then add a strain-uniform seed.
    seeds=[np.array([1.0e-4,0.,0.]),
           np.array([max(1.e-6,min(0.003,target[0]/max(1.,20000*prepared.b_m*prepared.h_m))),0.,0.]),
           np.array([0.,np.sign(target[1])*1.e-4,np.sign(target[2])*1.e-4])]
    best=None
    for seed in seeds:
        u=seed.copy();previous=math.inf
        for step in range(max_iter):
            forces,J,meta=prepared.response(u)
            residual=(forces-target)/scales
            err=float(np.linalg.norm(residual))
            if best is None or err<best[0]:best=(err,u.copy(),forces.copy(),meta,step)
            if err<3.e-7:
                _,_,details=prepared.response(u,include_maps=with_maps)
                ultimate=(details['max_concrete_compression']<=prepared.eps_cu2+1e-8
                    and details['min_steel_strain']>=-TENSILE_STEEL_LIMIT-1e-8)
                return {'status':'equilibrium_within_strain_limits' if ultimate else 'strain_limits_exceeded',
                        'equilibrium':True,'strain_limits_satisfied':bool(ultimate),
                        'normative_claim':False,'fire_resistance_status':'not_demonstrated',
                        'target':{'N_kN':target[0],'Mx_kNm':target[1],'My_kNm':target[2]},
                        'internal':{'N_kN':forces[0],'Mx_kNm':forces[1],'My_kNm':forces[2]},
                        'unknown_strains':u.tolist(),
                        'relative_residual':err,'iterations':step,
                        'tangent_matrix':J.tolist(),'details':details,
                        'source':'СП 5.03.01-2020 (8.1)-(8.3), (6.17)-(6.18); '
                                 'СП 2.02.05-2026 таблицы 9/10'}
            try:
                delta=np.linalg.solve(J/scales[:,None],-residual)
            except np.linalg.LinAlgError:
                delta=np.linalg.lstsq(J/scales[:,None],-residual,rcond=1e-12)[0]
            if not np.all(np.isfinite(delta)):break
            # Global damping and limited trial increments prevent excursions
            # into unphysical negative-tangent branches during iteration.
            delta=np.clip(delta,-0.0025,0.0025)
            success=False
            for damping in (1.,0.5,0.25,0.125,0.0625,0.03125,0.015625):
                trial=u+damping*delta
                if max(abs(trial))>.03:continue
                rtrial=(prepared.response(trial)[0]-target)/scales
                etrial=float(np.linalg.norm(rtrial))
                if etrial < err*(1.-1e-5) or etrial < 3e-7:
                    u=trial;previous=etrial;success=True;break
            if not success:break
    if best is None:
        return {'status':'unresolved','equilibrium':False,'normative_claim':False,
                'reason':'Нет допустимого начального состояния для решения'}
    error,state,forces,details,step=best
    return {'status':'equilibrium_not_converged','equilibrium':False,
            'normative_claim':False,'fire_resistance_status':'not_demonstrated',
            'relative_residual':error,'iterations':step,'unknown_strains':state.tolist(),
            'target':{'N_kN':target[0],'Mx_kNm':target[1],'My_kNm':target[2]},
            'internal':{'N_kN':forces[0],'Mx_kNm':forces[1],'My_kNm':forces[2]},
            'details':details,
            'reason':'Уравнения равновесия не сошлись; это не доказательство отказа элемента'}


def evaluate_column_mechanics(column:dict, thermal:dict|None=None, *,
                              grid:int=26, above_800_policy:str='reject',
                              include_maps:bool=False) -> dict:
    """Evaluate only fully specified load sections; explicitly fail closed."""
    base={'status':'not_evaluated','version':VERSION,
          'source_documents':list(NORMATIVE_SOURCES),
          'normative_claim':False,'fire_resistance_status':'not_demonstrated',
          'section_method':'simultaneous_3DOF_temperature_dependent_section_equilibrium',
          'member_stability':'not_implemented_R0.6.4',
          'partial_loads':'not_accepted','sections':{},'issues':[],
          'temperature_policy':above_800_policy}
    if thermal is None:
        thermal=evaluate_rectangular_column(column,grid=grid)
    if thermal.get('status') not in ('evaluated','evaluated_with_scope_warnings'):
        base['issues'].append('Приложение К: '+str(thermal.get('reason') or thermal.get('missing') or thermal.get('status')))
        return base
    try:
        section=prepare_section(column,thermal,grid=grid,above_800_policy=above_800_policy)
    except (SectionMechanicsError,MaterialError,KeyError,TypeError,ValueError) as exc:
        base['status']='blocked';base['issues'].append(str(exc));return base
    base['material_strengths']=section.strength_data
    base['issues'].extend(section.issues)
    base['thermal_summary']={'concrete_max_C':float(np.max(section.concrete_temperature_C)),
        'concrete_min_C':float(np.min(section.concrete_temperature_C)),
        'bar_max_C':float(np.max(section.bar_temperature_C)),
        'concrete_cells_above_800':section.out_of_table_concrete_cells,
        'bars_above_800':section.out_of_table_bars}
    loaded=[]
    for r in column.get('sections',[]):
        if any(r.get(key) is None for key in ('N_kN','Mx_kNm','My_kNm')):
            base['sections'][r.get('id','?')]={'status':'loads_missing'}
            continue
        rec=solve_load(section,r['N_kN'],r['Mx_kNm'],r['My_kNm'],with_maps=include_maps)
        base['sections'][r['id']]=rec
        loaded.append(rec)
    if not loaded:return base
    base['status']='evaluated_diagnostic' if all(r.get('equilibrium') for r in loaded) else 'partially_evaluated'
    if above_800_policy=='zero_strength_diagnostic':
        base['issues'].append('Ввод за пределами таблиц 9–10: эти результаты не нормативные')
    return base