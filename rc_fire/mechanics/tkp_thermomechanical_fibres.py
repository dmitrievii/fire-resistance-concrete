"""R0.6.9D2: thermomechanical N/Mx/My fibres with TKP EN 1992-1-2 laws.

Source: Belarus TKP EN 1992-1-2-2009 §§2.3, 3.2.2, 3.2.3,
3.3.1, 3.4, National Annex, user supplied. The *temperature field*
is provisionally from SP 2.02.05-2026 Annex K, NOT an EN heat-transfer solve.

Compression-positive total axial/curvature strains; thermal free extension
makes compression-positive mechanical strain e_mech=e_total+eps_free.
This reproduces a freely heated stress-free section with e_total=-eps_free.

Unknown endpoints of concrete strains for 1100<T<1200 are not fabricated.
An optional diagnostic-only zero tail and diagnostic-only boundary policy
permit sensitivity experiments but NEVER constitute normative strength.

The system is a general first-order fibre model, and a two-axis
second-order beam law can be constructed from it. Neither code path is
validated structural fire resistance by itself.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from rc_fire.materials import resolve_materials
from rc_fire.materials.tkp_en1992_fire import (
    EurocodeFireMaterialError, concrete_parameters, concrete_stress,
    concrete_free_thermal_strain, reinforcement_stress,
    reinforcement_parameters, rebar_free_thermal_strain,
    SOURCE as TKP_SOURCE, VERSION as TKP_MATERIAL_VERSION)
from rc_fire.thermal import RectangularExposure, temperature_rectangle
from rc_fire.member.coupled import CoupledMemberError
from rc_fire.mechanics.action_capacity import (
    WITHIN, EXCEEDED, UNKNOWN, scan_action_path)

VERSION="R0.6.9D2-TKP-thermomechanical-fibres-v1"


class TKPFibreInputError(ValueError):
    """No complete material, geometry, or source-qualified temperature field."""


def _finite(v,label,*,positive=False):
    if isinstance(v,bool):
        raise TKPFibreInputError(f'{label}: numeric required')
    try: n=float(v)
    except (TypeError,ValueError) as exc:
        raise TKPFibreInputError(f'{label}: numeric required') from exc
    if not math.isfinite(n) or (positive and n<=0):
        raise TKPFibreInputError(f'{label}: finite positive value required' if positive
                                else f'{label}: finite number required')
    return n


def _strains_for_temperature(temperature,aggregate):
    return np.asarray([concrete_free_thermal_strain(float(t),aggregate=aggregate)
                       for t in np.ravel(temperature)],dtype=float)


@dataclass
class TKPPreparedFibres:
    """An immutable-by-convention hot section inventory, one temperature time."""
    x:np.ndarray
    y:np.ndarray
    u:np.ndarray
    v:np.ndarray
    area:np.ndarray
    theta_c:np.ndarray
    eps_th_c:np.ndarray
    bar_x:np.ndarray
    bar_y:np.ndarray
    bar_u:np.ndarray
    bar_v:np.ndarray
    bar_area:np.ndarray
    theta_s:np.ndarray
    theta_cb:np.ndarray
    eps_th_s:np.ndarray
    eps_th_cb:np.ndarray
    b_m:float
    h_m:float
    fck_MPa:float
    fyk_MPa:float
    Es_MPa:float
    aggregate:str
    production_route:str
    ductility_class:str
    high_temperature_tail:str
    boundary_max_C:float
    boundary_gap:bool
    hot_fibre_count:int
    bar_ids:tuple
    source:dict

    def _concrete_at(self,eps,temperature):
        if temperature>1100. and temperature<1200.:
            if self.high_temperature_tail=="zero_tail_diagnostic":
                return 0.,0.,None
            raise TKPFibreInputError("TKP Table 3.1 omits strain endpoints for 1100<T<1200")
        p=concrete_parameters(temperature,aggregate=self.aggregate)
        sig,tan=concrete_stress(eps,temperature,fck_MPa=self.fck_MPa,
                                aggregate=self.aggregate)
        return sig,tan,p.eps_cu1

    def force_and_tangent(self,x,*,include_maps=False):
        """3-component equilibrium F=(N,Mx,My), tangent dF/d(e0,gx,gy)."""
        unknown=np.asarray(x,dtype=float)
        if unknown.shape!=(3,) or not np.all(np.isfinite(unknown)):
            raise TKPFibreInputError("section unknowns must be a finite 3-vector")
        e0,gx,gy=unknown
        # Strain compatibility: e_total=e0+gx*v+gy*u, compression positive.
        # Thermal free extension positive -> comp mechanical e_total+eps_th.
        ec=e0+gx*self.v+gy*self.u+self.eps_th_c
        es=e0+gx*self.bar_v+gy*self.bar_u+self.eps_th_s
        eb=e0+gx*self.bar_v+gy*self.bar_u+self.eps_th_cb
        sc=np.zeros(len(ec));dc=np.zeros(len(ec))
        sb=np.zeros(len(es));db=np.zeros(len(es))
        ss=np.zeros(len(es));ds=np.zeros(len(es))
        max_ratio=0.
        for i,(strain,theta) in enumerate(zip(ec,self.theta_c)):
            sc[i],dc[i],ultimate=self._concrete_at(float(strain),float(theta))
            if ultimate is not None:
                max_ratio=max(max_ratio,max(0.,float(strain))/ultimate)
        for i,(strain,theta) in enumerate(zip(eb,self.theta_cb)):
            sb[i],db[i],ultimate=self._concrete_at(float(strain),float(theta))
            if ultimate is not None:
                max_ratio=max(max_ratio,max(0.,float(strain))/ultimate)
        for i,(strain,theta) in enumerate(zip(es,self.theta_s)):
            ss[i],ds[i]=reinforcement_stress(float(strain),float(theta),
                fyk_MPa=self.fyk_MPa,Es_MPa=self.Es_MPa,
                production_route=self.production_route,
                ductility_class=self.ductility_class)
        eps_su=.10 if self.ductility_class=='A' else .20
        steel_ratio=max(abs(es))/eps_su
        max_ratio=max(max_ratio,float(steel_ratio))
        y=self.y-self.h_m/2;xc=self.x-self.b_m/2
        yb=self.bar_y-self.h_m/2;xb=self.bar_x-self.b_m/2
        A=self.area*1000.
        B=self.bar_area*1000.
        shape_c=np.stack((np.ones(len(ec)),self.v,self.u),axis=0)
        shape_s=np.stack((np.ones(len(es)),self.bar_v,self.bar_u),axis=0)
        moment_c=np.stack((np.ones(len(ec)),y,xc),axis=0)
        moment_s=np.stack((np.ones(len(es)),yb,xb),axis=0)
        forces=moment_c@(A*sc)+moment_s@(B*(ss-sb))
        tangent=(moment_c*(A*dc)[None,:])@shape_c.T + \
                (moment_s*(B*(ds-db))[None,:])@shape_s.T
        meta={
            'model':VERSION,'normative_claim':False,
            'critical_mechanical_strain_ratio':float(max_ratio),
            'max_concrete_mechanical_compression':float(max(0.,np.max(ec))),
            'max_steel_mechanical_strain_abs':float(np.max(np.abs(es))),
            'temperature_max_concrete_cell_C':float(np.max(self.theta_c)),
            'temperature_max_rebar_C':float(np.max(self.theta_s)),
            'boundary_temperature_max_C':self.boundary_max_C,
            'boundary_above_full_concrete_curve':self.boundary_gap,
            'zero_tail_diagnostic':self.high_temperature_tail=='zero_tail_diagnostic',
            'hot_concrete_fibres_without_curve':self.hot_fibre_count,
            'strain_limits_satisfied':None if (self.boundary_gap or self.hot_fibre_count) else bool(max_ratio<=1.),
            'model_only_strain_limits_satisfied':bool(max_ratio<=1.),
            'source':self.source,
        }
        if include_maps:
            meta['map']={'concrete_stress_MPa':sc.tolist(),
                'concrete_mechanical_strain':ec.tolist(),
                'steel_stress_MPa':ss.tolist(),
                'steel_mechanical_strain':es.tolist()}
        return np.asarray(forces),np.asarray(tangent),meta

    def solve_actions(self,N_kN,Mx_kNm,My_kNm,*,max_iterations=45):
        """Independent small 3×3 Newton solve; numerical state, NOT certified ULS.

        Intentionally no warm starts from earlier time or load factors. Every
        trial is deterministic and may yield UNKNOWN; line-search failure is
        never reclassified as physical failure.
        """
        target=np.asarray([_finite(N_kN,'N'),_finite(Mx_kNm,'Mx'),
                           _finite(My_kNm,'My')],dtype=float)
        scales=np.maximum(np.abs(target),[100.,10.,10.])
        seeds=[
            [-.002,0.,0.],[-.006,0.,0.],[-.012,0.,0.],
            [0.,0.,0.],[.001,0.,0.],[-.002,.0004,.0004],
            [-.002,-.0004,-.0004],[-.015,.002,-.002],
        ]
        best=None
        for guess in seeds:
            x=np.asarray(guess,dtype=float)
            for step_id in range(max_iterations):
                try:
                    F,J,meta=self.force_and_tangent(x)
                except (TKPFibreInputError,EurocodeFireMaterialError,ValueError) as exc:
                    return {'classification':UNKNOWN,'model_status':'BLOCKED_MATERIAL',
                            'reason':str(exc),'normative_claim':False}
                residual=(F-target)/scales
                error=float(np.linalg.norm(residual))
                if best is None or error<best[0]:
                    best=(error,x.copy())
                if error<1e-6:
                    model_only=WITHIN if meta['model_only_strain_limits_satisfied'] else EXCEEDED
                    classification=UNKNOWN if meta['strain_limits_satisfied'] is None else model_only
                    return {'classification':classification,
                        'model_only_classification':model_only,
                        'model_status':'equilibrated_fibre_section_diagnostic',
                        'unknowns':x.tolist(),
                        'forces_kN_kNm':F.tolist(),
                        'target_N_Mx_My':target.tolist(),
                        'relative_residual':error,
                        'critical_ratio':meta['critical_mechanical_strain_ratio'],
                        'scope':meta,
                        'reason':'Unresolved concrete Table 3.1 hot-boundary or tail law' if classification==UNKNOWN else '',
                        'normative_claim':False}
                try:delta=np.linalg.solve(J,(-target+F)*-1.)
                except np.linalg.LinAlgError:break
                if not np.all(np.isfinite(delta)):break
                magnitude=float(np.max(np.abs(delta)))
                if magnitude>.005:delta*=.005/magnitude
                progressed=False
                for factor in (1.,.5,.25,.125,.0625,.03125,.015625):
                    xx=x+factor*delta
                    try:
                        FF,_,_=self.force_and_tangent(xx)
                        err=float(np.linalg.norm((FF-target)/scales))
                    except (ValueError,ArithmeticError):
                        continue
                    if err<error*(1.-1e-6):
                        x=xx
                        progressed=True
                        break
                if not progressed:break
        return {'classification':UNKNOWN,'model_status':'newton_no_converged_root',
                'reason':'3x3 fibre equilibrium did not converge; this is NOT a failure mode',
                'best_residual_norm':best[0] if best else None,
                'normative_claim':False}

    def load_factor_scan(self,N_kN,Mx_kNm,My_kNm,*,max_factor=2.,
                         factor_step=.5,max_bisection=3):
        N=_finite(N_kN,'N',positive=True)
        Mx=_finite(Mx_kNm,'Mx');My=_finite(My_kNm,'My')
        result=scan_action_path(lambda lam:self.solve_actions(
            N*lam,Mx*lam,My*lam),max_factor=max_factor,
            factor_step=factor_step,max_bisection=max_bisection)
        return {**result,'material_model':VERSION,
            'source':self.source,
            'design_actions':{'N_kN':N,'Mx_kNm':Mx,'My_kNm':My},
            'actual_normative_R_t_minutes':None,'normative_claim':False,
            'fire_resistance_status':'not_demonstrated'}

    def member_law(self):
        """2×2 condensed N–M fibre tangent for existing P–Delta beam solver.

        The nonlinear solver assumes a continuous stable branch, so this remains
        an *exploratory* interface, not a collapse-time detector.
        """
        return TKPBeamSectionLaw(self)


class TKPBeamSectionLaw:
    def __init__(self,section):
        self.p=section

    def evaluate(self,kappa,N_kN):
        k=np.asarray(kappa,dtype=float)
        if k.shape!=(2,) or not np.all(np.isfinite(k)):
            raise CoupledMemberError("invalid curvature")
        # Mechanical e0+gx*v+gy*u, gx=kap_x*h/2, gy=kap_y*b/2
        gx=k[0]*self.p.h_m/2;gy=k[1]*self.p.b_m/2
        N=_finite(N_kN,'N',positive=True)
        last_error=None
        for seed in (-.002,-.006,-.012,0.,.001,-.02):
            e0=seed
            for _ in range(45):
                try:
                    F,J,m=self.p.force_and_tangent([e0,gx,gy])
                except (ValueError,ArithmeticError) as exc:
                    raise CoupledMemberError(str(exc)) from exc
                res=F[0]-N
                if abs(res)<max(1e-5,N*1e-7):
                    a=float(J[0,0])
                    if a<=1e-6:
                        raise CoupledMemberError('nonpositive axial fibre tangent')
                    condensed=J[1:,1:]-np.outer(J[1:,0],J[0,1:])/a
                    # J is d(M)/d(g); beam expects dM/d(kappa)
                    transform=np.diag([self.p.h_m/2,self.p.b_m/2])
                    D=condensed@transform
                    D=(D+D.T)*.5
                    if np.linalg.eigvalsh(D)[0]<=0:
                        raise CoupledMemberError('nonpositive condensed TKP tangent')
                    meta={'model':VERSION,'source':TKP_SOURCE,
                        'reference_strength_mode':'tkp_EN1992_fire_gamma_M_fi_1',
                        'strain_limits_satisfied':m['strain_limits_satisfied'],
                        'critical_mechanical_strain_ratio':m['critical_mechanical_strain_ratio'],
                        'constitutive_domain_qualified':not (self.p.boundary_gap or self.p.hot_fibre_count),
                        'max_concrete_compressive_strain':m['max_concrete_mechanical_compression'],
                        'max_steel_tensile_strain':m['max_steel_mechanical_strain_abs'],
                        'eps_cu2':None,'tensile_steel_limit':None,
                        'boundary_above_full_concrete_curve':m['boundary_above_full_concrete_curve'],
                        'normative_claim':False}
                    return F[1:],D,meta
                deriv=float(J[0,0])
                if not math.isfinite(deriv) or deriv<=0:break
                delta=max(-.004,min(.004,res/deriv))
                success=False
                for fac in (1.,.5,.25,.125,.0625):
                    next_e=e0-fac*delta
                    try:NF,_,_=self.p.force_and_tangent([next_e,gx,gy])
                    except (ValueError,ArithmeticError):continue
                    if abs(NF[0]-N)<abs(res):
                        e0=next_e;success=True;break
                if not success:break
            last_error=res
        raise CoupledMemberError(
            f"no stable axial equilibrium in heated TKP fibre law: residual={last_error}")


def prepare_tkp_fibres(column,thermal,*,grid=12,production_route,
                       ductility_class,high_temperature_tail='reject'):
    """Prepare a real 2D fibre inventory; never infer fabrication or ductility."""
    if type(grid) is not int or not 8<=grid<=80:
        raise TKPFibreInputError('grid must be integer 8..80')
    if high_temperature_tail not in ('reject','zero_tail_diagnostic'):
        raise TKPFibreInputError('invalid high_temperature_tail policy')
    if not isinstance(column,dict) or not isinstance(thermal,dict):
        raise TKPFibreInputError('column and independently calculated thermal field required')
    if thermal.get('status') not in ('evaluated','evaluated_with_scope_warnings'):
        raise TKPFibreInputError('Annex K thermal source not evaluated')
    if abs(_finite(thermal.get('fire_minutes'),'thermal time')-
           _finite(column.get('fire_minutes'),'column time'))>1e-9:
        raise TKPFibreInputError('thermal field time does not match column')
    spec=column.get('thermal_spec') or {}
    if set(thermal.get('exposed_faces') or [])!=set(spec.get('exposed_faces') or []):
        raise TKPFibreInputError('thermal exposure differs from column')
    mat=resolve_materials(column)
    if mat.get('status')!='resolved_for_property_lookup':
        raise TKPFibreInputError(
            'materials not fully resolved: '+str(mat.get('issues')))
    cb=mat.get('concrete') or {};st=mat.get('steel') or {}
    aggregate=mat.get('fire_family')
    if aggregate not in ('siliceous','calcareous'):
        raise TKPFibreInputError('TKP normal weight aggregate family unresolved')
    if aggregate!=(spec.get('concrete_family')):
        raise TKPFibreInputError('thermal and material aggregate mismatch')
    fck=_finite(cb.get('f_ck_MPa'),'fck',positive=True)
    fyk=_finite(st.get('f_yk_MPa'),'fyk',positive=True)
    Es=_finite(st.get('E_s_GPa'),'Es',positive=True)*1000.
    # Explicitly validate hot/cold processing and ductility, not just S500.
    reinforcement_parameters(20.,fyk_MPa=fyk,Es_MPa=Es,
        production_route=production_route,ductility_class=ductility_class)
    b=_finite(column.get('b_mm'),'b',positive=True)/1000.
    h=_finite(column.get('h_mm'),'h',positive=True)/1000.
    xx=(np.arange(grid)+.5)*b/grid
    yy=(np.arange(grid)+.5)*h/grid
    X,Y=np.meshgrid(xx,yy,indexing='xy')
    exp=RectangularExposure(b*1000,h*1000,tuple(thermal['exposed_faces']))
    coeff=thermal.get('coefficients')
    if not isinstance(coeff,dict):
        raise TKPFibreInputError('Annex K coefficients absent')
    t=float(column['fire_minutes'])
    cell,scope=temperature_rectangle(exp,coeff,t,X*1000,Y*1000)
    if np.any(scope['outside_approximation_C']) or not np.all(np.isfinite(cell)):
        raise TKPFibreInputError('Annex K centre temperatures outside thermal domain')
    # Crucial: use actual corners, not cell centres to check the hottest region.
    corners_x=np.asarray([0,b*1000,0,b*1000],dtype=float)
    corners_y=np.asarray([0,0,h*1000,h*1000],dtype=float)
    boundary,bscope=temperature_rectangle(exp,coeff,t,corners_x,corners_y)
    if np.any(bscope['outside_approximation_C']) or not np.all(np.isfinite(boundary)):
        raise TKPFibreInputError('Annex K corner boundary outside domain')
    bmax=float(np.max(boundary))
    if bmax>1200.:
        raise TKPFibreInputError('concrete corner exceeds 1200 °C source limit')
    gap=bool(1100.<bmax<1200.)
    if gap and high_temperature_tail=='reject':
        raise TKPFibreInputError(
            'UNRESOLVED_CONCRETE_BOUNDARY_1100_TO_1200: Table 3.1 strains absent')
    bar_ids=[];bx=[];by=[];ba=[];bt=[];bct=[]
    for i,bar in enumerate(column.get('bars') or []):
        x=_finite(bar.get('x_mm'),f'bar[{i}].x')/1000.
        y=_finite(bar.get('y_mm'),f'bar[{i}].y')/1000.
        dia=_finite(bar.get('diameter_mm'),f'bar[{i}].d',positive=True)
        if not dia/2000.<x<b-dia/2000. or not dia/2000.<y<h-dia/2000.:
            raise TKPFibreInputError('bar crosses concrete boundary')
        temp,_=temperature_rectangle(exp,coeff,t,x*1000.,y*1000.,dia)
        tc,_=temperature_rectangle(exp,coeff,t,x*1000.,y*1000.)
        bar_ids.append(str(bar.get('id') or f'bar{i}'))
        bx.append(x);by.append(y);ba.append(math.pi*(dia/2000.)**2)
        bt.append(float(temp));bct.append(float(tc))
    if not bar_ids or len(set(bar_ids))!=len(bar_ids):
        raise TKPFibreInputError('unique longitudinal reinforcing bars required')
    cells=np.asarray(cell).ravel();bt=np.asarray(bt);bct=np.asarray(bct)
    if min(float(np.min(cells)),float(np.min(bt)),float(np.min(bct)))<20.:
        raise TKPFibreInputError('material temperatures below 20°C unsupported')
    if max(float(np.max(cells)),float(np.max(bt)),float(np.max(bct)))>1200.:
        raise TKPFibreInputError('temperature exceeds 1200°C material source')
    badc=int(np.count_nonzero((cells>1100.)&(cells<1200.)))
    badb=int(np.count_nonzero((bct>1100.)&(bct<1200.)))
    if (badc or badb) and high_temperature_tail=='reject':
        raise TKPFibreInputError('UNRESOLVED_CONCRETE_FIBRES_1100_TO_1200')
    if 1100.<float(np.max(bt))<1200.:
        # Steel still defined here, do not conflate it with concrete gap.
        pass
    A=b*h/(grid*grid)
    bx=np.asarray(bx);by=np.asarray(by)
    return TKPPreparedFibres(
        x=X.ravel(),y=Y.ravel(),
        u=(X.ravel()-b/2)/(b/2),v=(Y.ravel()-h/2)/(h/2),
        area=np.full(grid*grid,A),theta_c=cells,
        eps_th_c=_strains_for_temperature(cells,aggregate),
        bar_x=bx,bar_y=by,bar_u=(bx-b/2)/(b/2),
        bar_v=(by-h/2)/(h/2),bar_area=np.asarray(ba),
        theta_s=bt,theta_cb=bct,
        eps_th_s=np.asarray([rebar_free_thermal_strain(x) for x in bt]),
        eps_th_cb=_strains_for_temperature(bct,aggregate),
        b_m=b,h_m=h,fck_MPa=fck,fyk_MPa=fyk,Es_MPa=Es,
        aggregate=aggregate,production_route=production_route,
        ductility_class=ductility_class,
        high_temperature_tail=high_temperature_tail,
        boundary_max_C=bmax,boundary_gap=gap,
        hot_fibre_count=badc+badb,bar_ids=tuple(bar_ids),
        source={'tkp':TKP_SOURCE,'tkp_material_version':TKP_MATERIAL_VERSION,
                'thermal':'СП 2.02.05-2026 приложение К (hybrid diagnostic)',
                'normal_temperature_materials':mat.get('source'),
                'reference_material_catalog':'СП 5.03.01-2020 values reused as explicit input',
                'strength_convention':'TkP gamma_M_fi=1; no SP accidental gamma',
                'validation':'not qualified under TKP 4.3.4; research diagnostics only'})
