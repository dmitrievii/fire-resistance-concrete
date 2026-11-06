"""R0.6.3 *research* directional capacity envelope at a fixed axial load.

Evaluates physically bounded plane-strain states using the normative
stress diagrams, but angular discretisation, gradient search and the missing
member effects are NOT an approved ULS procedure. This module explicitly
returns numeric diagnostic quantities rather than a compliance verdict.
"""
from __future__ import annotations

import math
import numpy as np
from .normative import (PreparedSection, TENSILE_STEEL_LIMIT,
    concrete_parabolic_linear, steel_bilinear)


def _axial(pre:PreparedSection,e0:float,gx:float,gy:float):
    e=e0+gx*pre.v+gy*pre.u
    es=e0+gx*pre.bar_v+gy*pre.bar_u
    stress,_=concrete_parabolic_linear(e,pre.concrete_fcd_MPa,
                    pre.eps_c2,pre.eps_cu2,pre.n_parabola)
    steel,_=steel_bilinear(es,pre.bar_fyd_MPa,pre.bar_Es_theta_MPa)
    conc_bar,_=concrete_parabolic_linear(es,pre.bar_displaced_concrete_fcd_MPa,
                    pre.eps_c2,pre.eps_cu2,pre.n_parabola)
    return float(1000*(np.dot(stress,pre.concrete_area_m2)+
                 np.dot(steel-conc_bar,pre.bar_area_m2)))


def _feasible_state(p:PreparedSection,N:float,gx:float,gy:float,*,tolN:float):
    # Enforce epsilon_c,most-compressed <= epsilon_cu2 and minimum rebar
    # tensile strain >= -10 per mille, Table 8.1/§8.1.2.1. Regions
    # with zero (assumed) concrete strength do not govern compression.
    mask=p.concrete_fcd_MPa>0
    gradient=gx*p.v+gy*p.u
    maxgrad=(abs(gx)+abs(gy)) if mask.all() else (float(np.max(gradient[mask])) if mask.any() else -math.inf)
    bargrad=gx*p.bar_v+gy*p.bar_u
    e0_max=p.eps_cu2-maxgrad
    e0_min=-TENSILE_STEEL_LIMIT-float(np.min(bargrad))
    if e0_min>e0_max+1e-11:return None
    nl=_axial(p,e0_min,gx,gy)
    nu=_axial(p,e0_max,gx,gy)
    if N < nl-tolN or N>nu+tolN:return None
    if abs(nu-nl)<tolN:
        return (e0_max,gx,gy)
    lo=e0_min;hi=e0_max
    for _ in range(29):
        mid=(lo+hi)/2
        nm=_axial(p,mid,gx,gy)
        if nm<N:lo=mid
        else:hi=mid
    return ((lo+hi)/2,gx,gy)


def _limit_point(p:PreparedSection,N:float,angle:float,iterations=20):
    dx,dy=math.cos(angle),math.sin(angle)
    lower=0.
    upper=.01
    for _ in range(8):
        if _feasible_state(p,N,upper*dx,upper*dy,tolN=.1) is None:break
        lower=upper;upper*=2.
    else:return None
    for _ in range(iterations):
        mid=(lower+upper)/2
        if _feasible_state(p,N,mid*dx,mid*dy,tolN=.1) is None:
            upper=mid
        else:lower=mid
    s=_feasible_state(p,N,lower*dx,lower*dy,tolN=.1)
    if s is None:return None
    forces,_,meta=p.response(s)
    if abs(forces[0]-N)>max(.2,abs(N)*1e-4):return None
    if meta['max_concrete_compression']>p.eps_cu2+2e-7:return None
    if meta['min_steel_strain'] < -TENSILE_STEEL_LIMIT-2e-7:return None
    return (float(forces[1]),float(forces[2]))


def approximate_biaxial_capacity(p:PreparedSection,N_kN:float,
                                   Mx_kNm:float,My_kNm:float,*,
                                   angular_samples:int=36)->dict:
    """Return approximate radial M-capacity and utilisation, NEVER ULS PASS.

    Numerical geometry: 36+ points on a strain-limited boundary; a ray from
    origin intersects an interpolated polygon at fixed compression N.
    Neither polygonal interpolation nor this optimisation is specified as an
    authoritative member-level method in the supplied СП.
    """
    if not 24<=angular_samples<=144:
        raise ValueError('angular_samples: 24..144')
    N=float(N_kN);mx=float(Mx_kNm);my=float(My_kNm)
    if not all(math.isfinite(v) for v in (N,mx,my)):
        raise ValueError('Нагрузки должны быть конечными')
    method='angular_strain_boundary_polygon_research_non_normative'
    base={'status':'not_evaluated','method':method,'normative_claim':False,
          'fire_resistance_status':'not_demonstrated',
          'angular_samples':angular_samples,'axial_N_kN':N,
          'assumptions':['пределы деформаций §8.1.2.1',
            'контур Mx–My восстановлен численной интерполяцией между направлениями',
            'не учитываются эффекты 2-го порядка и температурное защемление'],
          'capacity_directional_kNm':None,'utilization_diagnostic':None}
    at_rest=_feasible_state(p,N,0.,0.,tolN=.1)
    if at_rest is None:
        return {**base,'status':'axial_force_outside_supported_strain_domain'}
    if math.hypot(mx,my)<1e-12:
        return {**base,'status':'pure_axial_no_directional_moment_capacity_requested',
            'utilization_diagnostic':0.}
    points=[]
    for i in range(angular_samples):
        point=_limit_point(p,N,2*math.pi*i/angular_samples)
        if point is None:
            return {**base,'status':'envelope_incomplete',
                'reason':f'Не построена точка {i} из {angular_samples}'}
        points.append(point)
    direction=np.array([mx,my])/math.hypot(mx,my)
    capacities=[]
    for j in range(len(points)):
        p0=np.array(points[j]);p1=np.array(points[(j+1)%len(points)])
        d=p1-p0
        cross=lambda a,b:float(a[0]*b[1]-a[1]*b[0])
        denominator=cross(d,direction)
        if abs(denominator)<1e-13:continue
        u=-cross(p0,direction)/denominator
        if -1e-8<=u<=1+1e-8:
            point=p0+u*d
            radial=float(np.dot(point,direction))
            if radial>1e-6:capacities.append(radial)
    if not capacities:
        return {**base,'status':'direction_intersection_unresolved',
            'envelope_Mx_My_kNm':points}
    capacity=min(capacities)
    demand=math.hypot(mx,my)
    return {**base,'status':'approximate_capacity_diagnostic',
        'capacity_directional_kNm':capacity,
        'moment_demand_magnitude_kNm':demand,
        'utilization_diagnostic':demand/capacity,
        'envelope_Mx_My_kNm':points,
        'warning':'ПРОЧНОСТЬ НЕ ПОДТВЕРЖДЕНА: численный контур не квалифицирован; '
                  'высокотемпературные зоны >800 °C требуют отдельной нормативной процедуры'}
