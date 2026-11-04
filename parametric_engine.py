"""R0.4 parametric rectangular RC section, explicit reinforcement coordinates.

Standalone experimental fibre-section calculation for four-sided standard fire.
The thermal formula follows the supplied K18 worksheet; the generalized
strain-compatibility and centroidal bending resistances are NEW calculations and
are NOT represented as normative Eurocode/Belarus fire design certification.

Coordinates: x from left face, y from bottom face; SI metres and kN/kNm.
Compression-positive stress; each bar may have its own diameter and location.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, asdict
from typing import Any
import numpy as np
from calculation_engine import ModelError, STEEL_T, STEEL_K500, STEEL_BETA500, interp

@dataclass(frozen=True)
class Bar:
    id: str
    x_m: float
    y_m: float
    diameter_mm: float

@dataclass(frozen=True)
class GeneralVariant:
    id: str
    N_kN: float
    M_x_kNm: float
    M_y_kNm: float
    bars: tuple[Bar,...]

@dataclass(frozen=True)
class GeneralInput:
    b_m: float
    h_m: float
    length_m: float
    f_ck_MPa: float
    E_cm_GPa: float
    f_y_MPa: float
    E_s_GPa: float
    fire_minutes: float
    fire_faces: tuple[str,...]
    a_red_m2_h: float
    phi_1: float
    phi_2: float
    critical_concrete_C: float
    mu_x: float
    mu_y: float
    variants: tuple[GeneralVariant,...]
    grid: int = 92

    @classmethod
    def from_dict(cls,d:dict):
        if d.get('schema') != 'k18-parametric-r04':
            raise ModelError('Parametric schema k18-parametric-r04 required')
        try:
            g=d['geometry'];m=d['material'];f=d['fire'];mech=d['mechanics']
            variants=tuple(GeneralVariant(id=v['id'],N_kN=float(v['N_kN']),
                M_x_kNm=float(v.get('M_x_kNm',0)),M_y_kNm=float(v.get('M_y_kNm',0)),
                bars=tuple(Bar(**bar) for bar in v['bars'])) for v in d['variants'])
            item=cls(b_m=float(g['b_m']),h_m=float(g['h_m']),length_m=float(g['length_m']),
                f_ck_MPa=float(m['f_ck_MPa']),E_cm_GPa=float(m['E_cm_GPa']),
                f_y_MPa=float(m['f_y_MPa']),E_s_GPa=float(m['E_s_GPa']),
                fire_minutes=float(f['minutes']),fire_faces=tuple(f['exposed_faces']),
                a_red_m2_h=float(f['a_red_m2_h']),phi_1=float(f['phi_1']),phi_2=float(f['phi_2']),
                critical_concrete_C=float(f.get('critical_concrete_C',500)),
                mu_x=float(mech['mu_x']),mu_y=float(mech['mu_y']),variants=variants,
                grid=int(d.get('grid',92)))
        except (KeyError,TypeError,ValueError) as exc:
            raise ModelError(f'Invalid parametric input: {exc}') from exc
        item.validate()
        return item

    def validate(self):
        if not (.25<=self.b_m<=2.0 and .25<=self.h_m<=2.0 and 1<=self.length_m<=40):
            raise ModelError('Section width/height must be .25..2m, length 1..40m')
        if not (0<self.a_red_m2_h<.02 and 0<self.fire_minutes<=240):
            raise ModelError('Invalid thermal diffusivity or fire duration')
        if self.fire_faces != ('left','right','bottom','top'):
            raise ModelError('R0.4 thermal solver only implements four-sided fire')
        if not (20<=self.critical_concrete_C<=800):raise ModelError('Critical concrete temperature invalid')
        if not (5<=self.f_ck_MPa<=100 and 100<=self.f_y_MPa<=800 and self.E_cm_GPa>0 and self.E_s_GPa>0):
            raise ModelError('Material values out of solver envelope')
        if not (0<self.mu_x<=2.5 and 0<self.mu_y<=2.5):raise ModelError('Invalid effective length factors')
        if not (48<=self.grid<=180):raise ModelError('Grid must be 48..180')
        if not (1<=len(self.variants)<=12):raise ModelError('Require 1..12 variants')
        if len(set(v.id for v in self.variants))!=len(self.variants):raise ModelError('Variant IDs must be unique')
        for v in self.variants:
            if not (0<v.N_kN<1e5):raise ModelError(f'{v.id}: positive axial force required')
            if not (4<=len(v.bars)<=64):raise ModelError(f'{v.id}: 4..64 bars required')
            if len(set(b.id for b in v.bars))!=len(v.bars):raise ModelError(f'{v.id}: bar IDs must be unique')
            for bar in v.bars:
                r=bar.diameter_mm/2000
                if not (6<=bar.diameter_mm<=50):raise ModelError(f'{v.id}/{bar.id}: diameter 6..50mm')
                if not (r+1e-4 < bar.x_m < self.b_m-r-1e-4 and r+1e-4 < bar.y_m < self.h_m-r-1e-4):
                    raise ModelError(f'{v.id}/{bar.id}: bar outside concrete cover')
            for i,bar in enumerate(v.bars):
                for other in v.bars[i+1:]:
                    distance=math.hypot(bar.x_m-other.x_m,bar.y_m-other.y_m)
                    if distance<(bar.diameter_mm+other.diameter_mm)/2000-1e-8:
                        raise ModelError(f'{v.id}: reinforcement overlap {bar.id}/{other.id}')


def temperature_field(s:GeneralInput,x,y,diameter_m=0.):
    """Legacy K18 four-face expression, generalized for rectangular coordinates.

    x,y can be NumPy arrays or floats. The equivalent depth correction is
    applied only for reinforcement (diameter>0), as in original x* formula.
    """
    l=math.sqrt(12*s.a_red_m2_h*s.fire_minutes/60)
    d=diameter_m
    off=s.phi_1*math.sqrt(s.a_red_m2_h)+s.phi_2*d
    distances=[np.asarray(x)-d/2+off,s.b_m-np.asarray(x)-d/2+off,
               np.asarray(y)-d/2+off,s.h_m-np.asarray(y)-d/2+off]
    rr=[np.clip(q/l,0,1) for q in distances]
    t=1220-1200*(1-(1-rr[0])**2-(1-rr[1])**2)*(1-(1-rr[2])**2-(1-rr[3])**2)
    return t


def factor(t,values):
    return float(np.interp(np.clip(t,20,1000),STEEL_T,values))


def concrete_grid(s):
    dx=s.b_m/s.grid;dy=s.h_m/s.grid
    xs=(np.arange(s.grid)+.5)*dx; ys=(np.arange(s.grid)+.5)*dy
    x,y=np.meshgrid(xs,ys,indexing='xy')
    temps=temperature_field(s,x,y)
    valid=temps<=s.critical_concrete_C
    x0=x[valid].ravel()-s.b_m/2;y0=y[valid].ravel()-s.h_m/2
    a=dx*dy
    if len(x0)<4:raise ModelError('Concrete effective section vanished at chosen fire exposure')
    area=len(x0)*a
    return {'x':x0,'y':y0,'a':a,'temperature':temps,'valid':valid,
       'area':area,'Ix':float((y0*y0).sum()*a),'Iy':float((x0*x0).sum()*a),
       'centroid_x':float(x0.sum()*a/area),'centroid_y':float(y0.sum()*a/area),
       'grid_m':max(dx,dy)}


def evaluate_section(s,mesh,bars,eps0,kappa,axis):
    """Numerical axial force and moments for plane strain with elastic-perfectly-plastic steel.

    Strain sign is compressive-positive. Concrete tensile stresses ignored.
    """
    pos=mesh['y'] if axis=='x' else mesh['x']
    ec=s.E_cm_GPa*1000/1.2  # MPa-to-GPa conversion consistent with K18 E_cd
    concrete=np.clip(ec*(eps0+kappa*pos),0,s.f_ck_MPa)
    n=float(concrete.sum()*mesh['a']*1000)
    moment=float(np.dot(concrete,pos)*mesh['a']*1000)
    for b in bars:
        yc=b['y_m']-s.h_m/2 if axis=='x' else b['x_m']-s.b_m/2
        e=eps0+kappa*yc
        sigma=float(np.clip(s.E_s_GPa*1000*b['beta']*e,-s.f_y_MPa*b['k'],s.f_y_MPa*b['k']))
        force=sigma*b['area_m2']*1000
        n+=force;moment+=force*yc
    return n,moment


def for_curvature(s,mesh,bars,axial_kN,kappa,axis):
    # monotone axial load N(eps0), bisect across physically generous bracket
    low,high=-.08,.08
    nlow,_=evaluate_section(s,mesh,bars,low,kappa,axis)
    nhigh,_=evaluate_section(s,mesh,bars,high,kappa,axis)
    if not nlow<=axial_kN<=nhigh:
        return None
    for _ in range(39):
        center=(low+high)/2
        n,_=evaluate_section(s,mesh,bars,center,kappa,axis)
        if n<axial_kN:low=center
        else:high=center
    eps0=(low+high)/2
    max_cstrain=float(np.max(eps0+kappa*(mesh['y'] if axis=='x' else mesh['x'])))
    if max_cstrain > .0035+1e-8: return None  # thermal fire method strain limitation
    n,m=evaluate_section(s,mesh,bars,eps0,kappa,axis)
    return {'N_kN':n,'M_kNm':m,'eps0':eps0,'kappa_1_m':kappa,'eps_c_max':max_cstrain}


def compute_one(s,v,mesh):
    bars=[]
    for b in v.bars:
        t=float(temperature_field(s,b.x_m,b.y_m,b.diameter_mm/1000))
        bars.append({**asdict(b),'temperature_C':t,'k':factor(t,STEEL_K500),
           'beta':factor(t,STEEL_BETA500),'area_m2':math.pi*(b.diameter_mm/1000)**2/4})
    Nmax=(mesh['area']*s.f_ck_MPa+sum(b['area_m2']*s.f_y_MPa*b['k'] for b in bars))*1000
    if v.N_kN>=Nmax-1e-6:raise ModelError(f'{v.id}: axial force {v.N_kN:g} exceeds nominal section capacity {Nmax:.3f}')
    axes={}
    for axis in ('x','y'):
        I=mesh['Ix'] if axis=='x' else mesh['Iy']
        is_=sum(b['area_m2']*(b['y_m']-s.h_m/2 if axis=='x' else b['x_m']-s.b_m/2)**2*b['beta'] for b in bars)
        B=(s.E_cm_GPa/1.2*I+s.E_s_GPa*is_)*1e9
        L0=s.length_m*(s.mu_x if axis=='x' else s.mu_y)
        ncrit=math.pi**2*B/(L0*L0*1000)
        eta=math.inf if v.N_kN>=ncrit else 1/(1-v.N_kN/ncrit)
        # calculate available centroidal bending capacity from strain-compatible section
        # (curvature signs tested both ways; limited to max concrete strain 0.0035)
        candidate=[]
        for sign in (-1,1):
            for curvature in np.geomspace(1e-8,.06,66):
                rec=for_curvature(s,mesh,bars,v.N_kN,sign*curvature,axis)
                if rec is not None:
                    candidate.append(rec)
        if not candidate:raise ModelError(f'{v.id}/{axis}: no admissible strain-compatible equilibrium')
        sign_load=1 if (v.M_x_kNm if axis=='x' else v.M_y_kNm)>=0 else -1
        candidates=[r for r in candidate if r['M_kNm']*sign_load>0]
        mrd=max((abs(r['M_kNm']) for r in candidates),default=0.)
        initial=v.M_x_kNm if axis=='x' else v.M_y_kNm
        # 1st-order initial geometric eccentricity, original Mathcad l0/400 and 20mm minimum
        ea=max(L0/400,.02)
        m_ed=(abs(initial)+v.N_kN*ea)*eta if math.isfinite(eta) else math.inf
        axes[axis]={'I_c_m4':I,'I_s_eff_m4':is_,'B_Nm2':B,'l0_m':L0,'N_cr_kN':ncrit,
          'eta':eta,'imperfection_e_m':ea,'M0_kNm':initial,'M_Ed_kNm':m_ed,
          'M_Rd_kNm':mrd,'utilization':(m_ed/mrd if mrd>0 else math.inf),
          'pass':bool(math.isfinite(m_ed) and mrd>0 and m_ed<=mrd),
          'capacity_method':'strain_compatible_fiber_uniaxial_experimental',
          'candidate_count':len(candidate)}
    return {'id':v.id,'bars':bars,'axes':axes,'N_kN':v.N_kN,
       'biaxial_diagnostic_sum':axes['x']['utilization']+axes['y']['utilization'],
       'axes_pass':all(a['pass'] for a in axes.values())}


def compute_general(s:GeneralInput)->dict[str,Any]:
    mesh=concrete_grid(s)
    variants={v.id:compute_one(s,v,mesh) for v in s.variants}
    # Mask is intentionally omitted from JSON. retain independently reproducible grid parameters.
    return {'engine':'k18-parametric-experimental','engine_version':'0.4.0',
        'schema':'k18-parametric-results-r04','inputs':asdict(s),
        'concrete':{'effective_area_m2':mesh['area'],'Ix_m4':mesh['Ix'],
          'Iy_m4':mesh['Iy'],'centroid_x_from_section_center_m':mesh['centroid_x'],
          'centroid_y_from_section_center_m':mesh['centroid_y'],
          'grid_m':mesh['grid_m'],'effective_cells':int(mesh['valid'].sum())},
        'variants':variants,'warnings':[
          'Experimental parametric generalization: NOT the original K18/Mathcad normative algorithm',
          'Four-sided legacy thermal field extrapolated to arbitrary rectangles; numerical 500C isotherm',
          'Fibre section assumes linear plane strain, elastic-perfectly plastic steel, no tensile concrete',
          'Finite numerical curvature samples: design resistance is approximate, convergence study required',
          'Ncr from centroidal nominal EI; second order effect approximate and not normative',
          'Biaxial diagnostic sum is NOT a code-defined interaction failure criterion',
          'No spalling, full 3D fire exposure, temperature-dependent concrete constitutive law, restraints',
          'Dynamic diagnostic DOCX replaces method-specific text/equations and retains original frame/stamp; it is not a normative K18 report',
          ]}
