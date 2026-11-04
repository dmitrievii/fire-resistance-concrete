"""Independent K18 legacy calculation engine: no Mathcad runtime or cached values.

This explicitly implements the calculations traced to the provided K18 XMCD.
It is a reproduction of that worksheet/report, NOT a claim of normative verification.
Units: m, kN, kN*m, MPa, GPa and hours, noted on every field.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import math
from typing import Any

PI = 3.14  # XMCD uses the rounded constant 3.14, not math.pi
STEEL_T = [20,100,200,300,400,500,600,700,800,801,900,1000]
STEEL_K500 = [1,1,1,1,.85,.60,.37,.22,.1,.1,.05,0]
STEEL_BETA500 = [1,1,.92,.90,.85,.80,.77,.72,.65,.65,.5,0]

class ModelError(ValueError): pass


def interp(x: float, grid: list, values: list) -> float:
    """Piecewise-linear interpolation, no extrapolation beyond tabulated domain."""
    if x < grid[0] or x > grid[-1]:
        raise ModelError(f'Temperature {x} C outside interpolation interval [{grid[0]}, {grid[-1]}]')
    for i in range(len(grid)-1):
        if grid[i] <= x <= grid[i+1]:
            return values[i]+(values[i+1]-values[i])*(x-grid[i])/(grid[i+1]-grid[i])
    return values[-1]


def one_based_roundup(x: float) -> int:
    """Legacy worksheet stores manually rounded integers; ceil matches K18 recorded values.

    Non-integer values from the thermal model are retained separately for audit.
    This assumption must not be presented as a new normative rounding rule.
    """
    return math.ceil(x - 1e-12)

@dataclass(frozen=True)
class Geometry:
    b_m: float = .6
    h_m: float = .6
    length_m: float = 13.7
    c_x_m: float = .05
    c_y_m: float = .05
    reduction_delta_extra_m: float = .034
    section_area_correction_m2: float = .032  # worksheet literal 0.2*0.08*2

@dataclass(frozen=True)
class Fire:
    minutes: int = 90
    faces: int = 4
    a_red_m2_h: float = .00133
    phi_1: float = .63
    phi_2: float = .5
    concrete_critical_C: float = 500
    ambient_C: float = 20
    steel_reference_diameter_m: float = .025

@dataclass(frozen=True)
class Material:
    f_ck_MPa: float = 30
    f_y_MPa: float = 500
    E_cm_GPa: float = 29
    E_s_GPa: float = 200
    eps_cu2_permille: float = 3.5

@dataclass(frozen=True)
class Mechanics:
    mu_x: float = .8
    mu_y: float = 1.2
    e_a2x_m: float = .023
    e_a2y_m: float = .020
    phi_100_30_35: float = 2.2
    alpha_cs: float = .79
    creep_m_perm_kNm: float = 10
    creep_m_total_kNm: float = 16
    k_ks: float = 1
    compression_d_x_mm: float = .001
    compression_d_y_mm: float = .01
    compression_count: int = 2
    compression_temperature_C: float = 410
    minor_inertia_d_y_mm: float = 16

@dataclass(frozen=True)
class Variant:
    id: str
    N_kN: float
    M_x_kNm: float
    M_y_kNm: float
    bar_diameter_mm: float
    bars_per_face: int = 3

@dataclass(frozen=True)
class Inputs:
    geometry: Geometry
    fire: Fire
    material: Material
    mechanics: Mechanics
    variants: tuple[Variant,...]

    @classmethod
    def from_dict(cls,d:dict):
        if d.get('schema') != 'k18-independent-engine-v1':
            raise ModelError('Incorrect engine input schema')
        names={'geometry':Geometry,'fire':Fire,'material':Material,'mechanics':Mechanics}
        parts={k:t(**d.get(k,{})) for k,t in names.items()}
        parts['variants']=tuple(Variant(**x) for x in d['variants'])
        if {v.id for v in parts['variants']} != {'v1','v2'} or len(parts['variants'])!=2:
            raise ModelError('Two named variants v1/v2 are required for the fixed report')
        return cls(**parts)

    def serialize(self):
        return {'schema':'k18-independent-engine-v1',**asdict(self)}


def steel_area(d_mm:float) -> float:
    return PI*(d_mm/1000)**2/4


def thermal_calculation(g:Geometry,f:Fire) -> dict:
    if f.faces != 4:
        raise ModelError('Legacy temperature formula only supports four exposed faces')
    if f.minutes<=0:raise ModelError('Fire duration must be positive')
    a=f.a_red_m2_h;phi1=f.phi_1;phi2=f.phi_2;d=f.steel_reference_diameter_m
    if a<=0 or not 0<f.concrete_critical_C<1220:raise ModelError('Invalid fire material input')
    l=math.sqrt(12*a*f.minutes/60)
    xcorner = .05-d/2 + phi1*math.sqrt(a)+phi2*d
    xmid = .25-d/2 + phi1*math.sqrt(a)+phi2*d
    # The report prints 0.473 m opposite-face distances, not the erroneous
    # x12=0.673 m worksheet cell. Both clamp to relative distance 1.0,
    # so the thermal temperature and all downstream results are unaffected.
    x_far=.5-(.05-d/2)-d + phi1*math.sqrt(a)+phi2*d
    x_mid_far=.7-(.25-d/2)-d+phi1*math.sqrt(a)+phi2*d
    pts=[(xcorner,x_far,xcorner,x_far),(xmid,x_mid_far,xcorner,x_far)]
    def rel(x): return min(1.0,x/l)
    rr=[[rel(x) for x in p] for p in pts]
    def temp(r):
        return 1220-1200*(1-(1-r[0])**2-(1-r[1])**2)*(1-(1-r[2])**2-(1-r[3])**2)
    th=[temp(r) for r in rr]
    r1=1-math.sqrt((f.concrete_critical_C-20)/1200)
    # r333=1 for K18. Evaluate the general intermediate expression rather than hardcoding it.
    r333=min(1.0, (g.b_m/2+phi1*math.sqrt(a))/l)
    w=1-2*(1-r333**2)**2
    if w<=0:raise ModelError('Legacy heating intermediate w must be > 0')
    r3=1-math.sqrt((1220*w-1220+f.concrete_critical_C)/(1220*w))
    delta=r3*l-phi1*math.sqrt(a)
    rcorner=1-math.sqrt(1-math.sqrt((1220-f.concrete_critical_C)/1220))
    lcorner=rcorner*l-phi1*math.sqrt(a)
    if min(delta,lcorner)<0 or lcorner<=delta:
        raise ModelError('Reduced-section thermal geometry invalid for these inputs')
    return {'l_m':l,'a_red_m2_h':a,'x_points_m':pts,'r_points':rr,
            'raw_steel_temperatures_C':th,
            'reported_steel_temperatures_C':[one_based_roundup(t) for t in th],
            'r_1':r1,'r_333':r333,'r_3':r3,'r_corner':rcorner,
            'delta_m':delta,'l_corner_m':lcorner,
            'temperature_source':'Calculated 4-sided XMCD formula, with legacy integer presentation'}


def calculate_variant(v:Variant,g:Geometry,f:Fire,material:Material,mech:Mechanics,therm:dict)->dict:
    if v.N_kN<=0 or v.bar_diameter_mm<=0 or v.bars_per_face<1:
        raise ModelError(f'Invalid force/reinforcement in {v.id}')
    if material.f_ck_MPa<=0 or material.f_y_MPa<=0:raise ModelError('Invalid material strengths')
    if f.minutes!=90:
        # independent engine can still calculate thermal quantities, but the fixed DOCX
        # contains R90 in normative prose and the reinforcement temps are calibrated to R90.
        raise ModelError('Current legacy mechanical calibration restricted to R90')
    fc=material.f_ck_MPa;fy=material.f_y_MPa
    b,h=g.b_m,g.h_m
    d_ref=therm['reported_steel_temperatures_C']
    if v.bars_per_face != 3:
        raise ModelError('Original K18 three-bar-per-face template is required')
    if len(d_ref)!=2:raise ModelError('Three-bar steel temperature layout missing')
    # In the original report, both variants use the same three steel temperatures.
    # They are recalculated from the fixed 25 mm reference thermal scheme.
    steel_temps=[d_ref[0],d_ref[0],d_ref[1]]
    k_list=[interp(t,STEEL_T,STEEL_K500) for t in steel_temps]
    beta_list=[interp(t,STEEL_T,STEEL_BETA500) for t in steel_temps]
    k=sum(k_list)/len(k_list);beta=sum(beta_list)/len(beta_list)
    fyd=fy*k;esfi=material.E_s_GPa*beta
    epssy=fyd/esfi
    xi=material.eps_cu2_permille/(material.eps_cu2_permille+epssy)
    A_st=v.bars_per_face*steel_area(v.bar_diameter_mm)
    N_st_MN=A_st*fyd
    delta=therm['delta_m'];lc=therm['l_corner_m'];hf=lc-delta
    axes={}
    phi_eff=mech.phi_100_30_35*(35/fc)**mech.alpha_cs*mech.creep_m_perm_kNm/mech.creep_m_total_kNm
    hfi=h-2*lc;bfi=b-2*lc
    A_cfi=hfi*bfi-g.section_area_correction_m2+(lc-delta)*(hfi+bfi)
    if min(hfi,bfi,A_cfi)<=0:raise ModelError('Invalid effective concrete section')
    n=v.N_kN/(A_cfi*fc*1000)
    k1=math.sqrt(fc/20)
    k2x=min(n*(g.length_m*mech.mu_x/(.289*hfi))/170,.2)
    kc=k1*k2x/(1+phi_eff) # legacy shared k_c both axes
    for ax in ('x','y'):
        width = b if ax=='x' else h
        depth = h if ax=='x' else b
        cover = g.c_y_m if ax=='x' else g.c_x_m
        c2=cover
        dfi=depth-cover-g.reduction_delta_extra_m
        bw=width-2*delta;be=width-2*lc
        l0=g.length_m*(mech.mu_x if ax=='x' else mech.mu_y)
        e_a1=l0/400
        e_a2=mech.e_a2x_m if ax=='x' else mech.e_a2y_m
        M=v.M_x_kNm if ax=='x' else v.M_y_kNm
        d_compr=mech.compression_d_x_mm if ax=='x' else mech.compression_d_y_mm
        A_compr=steel_area(d_compr)*mech.compression_count
        fy_compr=fy*interp(mech.compression_temperature_C,STEEL_T,STEEL_K500)
        N_compr_MN=A_compr*fy_compr
        xeff=(v.N_kN/1000+N_st_MN-N_compr_MN-fc*(bw-be)*hf)/(fc*bw)
        xeff_inner=(v.N_kN/1000+N_st_MN-N_compr_MN)/(fc*be)
        if xeff>hf:
            Mrd=(fc*bw*xeff*(dfi-.5*xeff)-fc*hf*(bw-be)*(dfi-.5*hf)
                 +N_compr_MN*(dfi-c2))*1000
            effective_xeff=xeff
            capacity_branch='cross_section'
        else:
            effective_xeff=xeff_inner
            Mrd=(fc*be*effective_xeff*(dfi-.5*effective_xeff)+N_compr_MN*(dfi-c2))*1000
            capacity_branch='inner_rectangle'
        ybar=(depth-cover)/2 # legacy armature distance for inertia
        I_minor=PI*(mech.minor_inertia_d_y_mm/1000)**4/64
        I_steel=(v.bars_per_face*(PI*(v.bar_diameter_mm/1000)**4/64 +steel_area(v.bar_diameter_mm)*ybar*ybar)
                 if ax=='x' else v.bars_per_face*(I_minor +steel_area(v.bar_diameter_mm)*ybar*ybar))
        I_conc=(bfi*hfi**3/12 if ax=='x' else hfi*bfi**3/12)
        B=(kc*(material.E_cm_GPa/1.2)*I_conc+2*mech.k_ks*material.E_s_GPa*I_steel*beta)*1e9
        Ncrit=PI**2*B/(l0**2*1000)
        if Ncrit <= v.N_kN:raise ModelError(f'{v.id}.{ax}: elastic stability force exceeded: N={v.N_kN}, Ncrit={Ncrit}')
        eta=1/(1-v.N_kN/Ncrit)
        e0=abs(M)/v.N_kN
        e_total=e0+e_a1+e_a2  # 4-sided heating -> thermal eccentricity multiplied by 0 in XMCD
        es=eta*e_total+.5*(dfi-cover)
        Med=v.N_kN*es
        k2=min(n*(l0/(.289*(hfi if ax=='x' else bfi)))/170,.2)
        axes[ax]={
            'N_kN':v.N_kN,'M0_kNm':M,'bar_diameter_mm':v.bar_diameter_mm,'bar_count':v.bars_per_face,
            'f_y_MPa':fy,'fyd_MPa':fyd,'k_steel':k,'beta_steel':beta,'E_steel_GPa':esfi,
            'eps_sy_permille':epssy,'eps_cu2_permille':material.eps_cu2_permille,'xi_lim':xi,
            'xi_dfi_m':xi*dfi,'A_st_m2':A_st,'A_compr_m2':A_compr,
            'N_st_MN':N_st_MN,'N_compr_MN':N_compr_MN,
            'effective_width_m':be,'web_width_m':bw,'hf_m':hf,'d_fi_m':dfi,
            'x_eff_m':effective_xeff,'capacity_branch':capacity_branch,'M_Rd_kNm':Mrd,
            'A_cfi_m2':A_cfi,'n':n,'lambda':l0/(.289*(hfi if ax=='x' else bfi)),
            'k2':k2,'kc':kc,'I_c_m4':I_conc,'I_s_m4':I_steel,'I_s_total_m4':2*I_steel,
            'B_Nm2':B,'l0_m':l0,'N_cr_kN':Ncrit,'eta':eta,
            'e_a1_m':e_a1,'e_a2_m':e_a2,'e_0_m':e0,'e_m':e_total,'e_s_m':es,
            'M_Ed_kNm':Med,'utilization':Med/Mrd if Mrd>0 else math.inf,
            'pass':bool(Mrd>0 and Med<=Mrd and 0<effective_xeff<=xi*dfi),
            'steel_temps_C':steel_temps,
        }
    return {'id':v.id,'inputs':asdict(v),'axes':axes,
            'shared':{'phi_eff':phi_eff,'A_cfi_m2':A_cfi,'hfi_m':hfi,'bfi_m':bfi,
                      'k1':k1,'kc_legacy_shared':kc,'f_ck_MPa':fc}}


def compute(spec:Inputs)->dict[str,Any]:
    g,f,mat,mech=spec.geometry,spec.fire,spec.material,spec.mechanics
    th=thermal_calculation(g,f)
    results={v.id:calculate_variant(v,g,f,mat,mech,th) for v in spec.variants}
    return {'engine':'independent-k18-python','engine_version':'0.3.0',
            'inputs':spec.serialize(),'thermal':th,'variants':results,
            'assumptions':[
             'Legacy four-face R90 temperatures and Ø25 thermal reference used in both variants',
             'Original isotherm-500 C reduced section and effective geometry formulas reproduced',
             'Original k_c derived from k2x and reused in Y axis (worksheet behavior)',
             'Original manually constructed steel inertias incl. 16 mm secondary diameter reproduced',
             'Original pi=3.14, E_cd=E_cm/1.2, temperature interpolation and 0*e_t reproduced',
             'Legacy compression reinforcement has artificial 0.001/0.01 mm diameters; its force retained',
             'No independent compliance certification or biaxial interaction verification is asserted',
            ]}

