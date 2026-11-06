"""R0.6.4B: geometric second-order, two-axis Euler-Bernoulli beam-column.

This is a RESEARCH / DIAGNOSTIC beam finite-element model, NOT a prescriptive
Belarus fire-design procedure.  A full coupled sectional tangent matrix Dxy,
real end fixities and externally supplied or explicitly calculated thermal
FREE strains are supported.  The element has two transverse DOF (deflection,
rotation) per axis at each station.  Axial compression is held constant.

Conventions: N>0 compression; q>0 yields positive deflection; section
compression curvature kappa=-w''.  Bending moments and tangent are returned
in the R0.6.3 order (Mx, My).  Eigenstrain values mean *positive free
extension*, while R0.6.3 section mechanical strain is compression-positive.

NOT COVERED: shear deformation, warping/torsion, differential restraint in
axial direction, force redistribution by a global frame, transient thermal
creep/spalling, normative plastic ULS, and time-to-failure R(t). Never R90.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
from typing import Callable, Sequence
import numpy as np

VERSION='R0.6.4C-member-uls-audited-diagnostic-v1'

class CoupledMemberError(ValueError):
    """Invalid input, loss of stiffness, or nonconvergence."""


def _finite_vector(a, shape=None, name='value'):
    a=np.asarray(a,dtype=float)
    if (shape is not None and a.shape!=shape) or not np.all(np.isfinite(a)):
        raise CoupledMemberError(f'{name}: invalid array shape or nonfinite entries')
    return a


@dataclass(frozen=True)
class EndSupport:
    """Mechanical constraints at an end. `elastic` has both DOF free and springs.

    For fixed/guided/pinned a nonzero displacement/rotation is imposed exactly.
    Elastic transverse springs use kN/m, rotational springs kNm/rad.
    """
    kind:str='pinned'  # pinned, fixed, free, guided, elastic
    lateral_spring_kNpm:float=0.
    rotational_spring_kNm:float=0.
    displacement_m:float=0.
    rotation_rad:float=0.

    def validate(self):
        if self.kind not in ('pinned','fixed','free','guided','elastic'):
            raise CoupledMemberError(f'unsupported end condition {self.kind}')
        vals=(self.lateral_spring_kNpm,self.rotational_spring_kNm,
              self.displacement_m,self.rotation_rad)
        if any(np.asarray(v).size not in (1,2) for v in vals) or not all(np.all(np.isfinite(np.asarray(v,dtype=float))) for v in vals):
            raise CoupledMemberError('nonfinite spring/boundary value')
        if np.any(np.asarray(self.lateral_spring_kNpm,dtype=float)<0) or np.any(np.asarray(self.rotational_spring_kNm,dtype=float)<0):
            raise CoupledMemberError('spring stiffness must be nonnegative')
        if self.kind in ('pinned','fixed','guided') and (np.any(np.asarray(self.lateral_spring_kNpm,dtype=float)!=0) or np.any(np.asarray(self.rotational_spring_kNm,dtype=float)!=0)):
            raise CoupledMemberError('do not add unidentifiable spring to idealized constraint')
        if self.kind=='free' and (np.any(np.asarray(self.lateral_spring_kNpm,dtype=float)!=0) or np.any(np.asarray(self.rotational_spring_kNm,dtype=float)!=0)):
            raise CoupledMemberError('choose elastic when springs are specified')
        if self.kind in ('free','elastic') and (np.any(np.asarray(self.displacement_m,dtype=float)!=0) or np.any(np.asarray(self.rotation_rad,dtype=float)!=0)):
            raise CoupledMemberError('prescribed values on free/elastic boundary are ambiguous')
        if self.kind=='pinned' and np.any(np.asarray(self.rotation_rad,dtype=float)!=0):
            raise CoupledMemberError('pinned rotation cannot be imposed')
        if self.kind=='guided' and np.any(np.asarray(self.displacement_m,dtype=float)!=0):
            raise CoupledMemberError('guided translation cannot be imposed')


def _shape(t,h):
    t2=t*t;t3=t2*t
    H=np.array([1-3*t2+2*t3, h*(t-2*t2+t3),3*t2-2*t3,h*(-t2+t3)])
    Hp=np.array([(-6*t+6*t2)/h,1-4*t+3*t2,(6*t-6*t2)/h,-2*t+3*t2])
    Hpp=np.array([(-6+12*t)/h**2,(-4+6*t)/h,(6-12*t)/h**2,(-2+6*t)/h])
    return H,Hp,Hpp


@dataclass(frozen=True)
class LinearSectionLaw:
    """Symmetric 2-axis bending stiffness with possible coupling [kN*m²].

    Diagnostic free thermal curvature is an independent supplied vector
    (not a certified value inferred from temperature).
    """
    D_kNm2:object
    free_curvature_1pm:object=(0.,0.)
    provenance:str='external_linear_stiffness_not_normatively_qualified'

    def __post_init__(self):
        D=_finite_vector(self.D_kNm2,(2,2),'D_kNm2')
        _finite_vector(self.free_curvature_1pm,(2,),'free_curvature')
        if not np.allclose(D,D.T,atol=1e-8,rtol=1e-10) or np.linalg.eigvalsh(D).min()<=0:
            raise CoupledMemberError('section tangent must be symmetric positive definite')
        if not self.provenance:
            raise CoupledMemberError('source provenance is required')

    def evaluate(self,kappa,N_kN):
        D=_finite_vector(self.D_kNm2,(2,2),'D')
        free=_finite_vector(self.free_curvature_1pm,(2,),'free curvature')
        km=_finite_vector(kappa,(2,),'curvature')
        return D@(km-free),D,{'model':'linear_explicit','source':self.provenance,
                              'axial_force_kN':float(N_kN),'strain_limits_satisfied':None}


class FiberSectionLaw:
    """True two-axis fibre equilibrium at prescribed N, including eigenstrain.

    Uses R0.6.3 prepared fibre geometry and its EXISTING diagnostic hot material
    diagrams, but subtracts signed thermal free strains at every concrete fibre,
    steel bar and replaced-concrete bar location. All three fields are REQUIRED;
    silently setting them to zero is prohibited in a heated analysis.

    Tangent is the full 2x2 Schur complement of N-epsilon0 equilibrium, not
    beta*Ecm nor two independent effective flexural rigidities.  An ambient
    R0.6.3 parabola remains a diagnostic fire material law.
    """
    def __init__(self, prepared, *, free_concrete, free_steel,
                 free_concrete_at_bars, provenance:str, free_concrete_at_corners=None):
        from rc_fire.mechanics.normative import PreparedSection
        if not isinstance(prepared,PreparedSection):
            raise CoupledMemberError('PreparedSection from R0.6.3C required')
        if prepared.out_of_table_concrete_cells or prepared.out_of_table_bars or prepared.boundary_temperature_max_C>800:
            raise CoupledMemberError('thermal/material tables outside supported domain')
        if not provenance:
            raise CoupledMemberError('explicit thermal-eigenstrain provenance is required')
        self.p=prepared
        self.ec=_finite_vector(free_concrete,prepared.concrete_temperature_C.shape,'concrete eigenstrain')
        self.es=_finite_vector(free_steel,prepared.bar_temperature_C.shape,'steel eigenstrain')
        self.eb=_finite_vector(free_concrete_at_bars,prepared.bar_temperature_C.shape,'concrete bar eigenstrain')
        self.ecorners=(None if free_concrete_at_corners is None else
             _finite_vector(free_concrete_at_corners,(4,),'four concrete corner eigenstrains'))
        if max(float(np.max(np.abs(x))) for x in (self.ec,self.es,self.eb,*([self.ecorners] if self.ecorners is not None else [])))>.05:
            raise CoupledMemberError('unphysical free strain magnitude')
        self.provenance=provenance
        self._e0_hint=0.

    def _force_and_tangent(self,e0,kappa):
        from rc_fire.mechanics.normative import concrete_parabolic_linear,steel_bilinear
        p=self.p
        yc=p.y_m-p.h_m/2;xc=p.x_m-p.b_m/2
        yb=p.bar_y_m-p.h_m/2;xb=p.bar_x_m-p.b_m/2
        # Positive free extension reverses signed compression-positive strain.
        ec=e0+kappa[0]*yc+kappa[1]*xc+self.ec
        eb=e0+kappa[0]*yb+kappa[1]*xb+self.eb
        es=e0+kappa[0]*yb+kappa[1]*xb+self.es
        sc,tc=concrete_parabolic_linear(ec,p.concrete_fcd_MPa,p.eps_c2,p.eps_cu2,p.n_parabola)
        sb,tb=concrete_parabolic_linear(eb,p.bar_displaced_concrete_fcd_MPa,p.eps_c2,p.eps_cu2,p.n_parabola)
        ss,ts=steel_bilinear(es,p.bar_fyd_MPa,p.bar_Es_theta_MPa)
        wc=p.concrete_area_m2*1000;wb=p.bar_area_m2*1000
        rc=np.array([np.ones_like(yc),yc,xc]);rb=np.array([np.ones_like(yb),yb,xb])
        F=(rc@(wc*sc))+(rb@(wb*(ss-sb)))
        J=(rc*(wc*tc)[None,:])@rc.T + (rb*(wb*(ts-tb))[None,:])@rb.T
        # Check four *actual* corners when their thermal eigenstrains are
        # supplied. A maximum of centre-sampled thermal strains is NOT an
        # upper bound on true corner temperature; absent corner data remains
        # an explicitly UNVERIFIED estimate, never accepted as ULS evidence.
        if self.ecorners is not None:
            y4=np.array([-p.h_m/2,-p.h_m/2,p.h_m/2,p.h_m/2])
            x4=np.array([-p.b_m/2,p.b_m/2,-p.b_m/2,p.b_m/2])
            corners=e0+kappa[0]*y4+kappa[1]*x4+self.ecorners
            corner_max=float(np.max(corners))
        else:
            corner_max=float(e0 + abs(kappa[0])*p.h_m/2
                + abs(kappa[1])*p.b_m/2 + np.max(self.ec))
        return F,J,max(float(np.max(ec)),corner_max),float(np.min(es))

    def evaluate(self,kappa,N_kN):
        kappa=_finite_vector(kappa,(2,),'curvature')
        if not math.isfinite(float(N_kN)):
            raise CoupledMemberError('nonfinite axial force')
        # Fixed-curvature axial equilibrium. Unconstrained negative e0 allowed:
        # thermal expansion is a compressive-strain negative free length change.
        e0=self._e0_hint
        for iteration in range(70):
            f,J,ecmax,esmin=self._force_and_tangent(e0,kappa)
            res=f[0]-N_kN
            if abs(res)<max(1e-5,abs(N_kN)*1e-8):break
            if J[0,0]<1e-7:
                raise CoupledMemberError('section axial tangent vanished at fixed curvature')
            step=np.clip(res/J[0,0],-.001,.001)
            # Simple monotonic backtracking in the axial variable.
            for scale in (1.,.5,.25,.125,.0625,.03125):
                candidate=e0-scale*step
                rnew=self._force_and_tangent(candidate,kappa)[0][0]-N_kN
                if abs(rnew)<abs(res):
                    e0=candidate;break
            else:raise CoupledMemberError('no axial equilibrium: line search blocked')
        else:raise CoupledMemberError('no axial equilibrium in 70 steps')
        self._e0_hint=float(e0)
        a=float(J[0,0])
        if a<=0:raise CoupledMemberError('axial condensed stiffness not positive')
        D=J[1:,1:]-np.outer(J[1:,0],J[0,1:])/a
        D=(D+D.T)*.5
        ev=np.linalg.eigvalsh(D)
        if ev[0]<=max(1e-7,ev[-1]*1e-10):
            raise CoupledMemberError('section biaxial condensed tangent nonpositive')
        meta={'model':'nonlinear_R063C_fibres_with_explicit_eigenstrains',
              'axial_compressive_strain_e0':float(e0),
              'max_concrete_compressive_strain':ecmax,
              'concrete_max_method':('explicit_four_corners_and_fibre_centres' if self.ecorners is not None else 'unverified_centre_field_surrogate'),
              'corner_eigenstrain_explicit':self.ecorners is not None,
              'eps_cu2':float(self.p.eps_cu2),
              'tensile_steel_limit':0.010,
              'bar_temperature_min_C':float(np.min(self.p.bar_temperature_C)),
              'max_boundary_temperature_C':float(self.p.boundary_temperature_max_C),
              'reference_strength_mode':self.p.strength_data.get('reference_strength_mode','legacy_accidental_design_diagnostic'),
              'max_steel_tensile_strain':-esmin,
              'strain_limits_satisfied':bool(ecmax<=self.p.eps_cu2+1e-8 and esmin>=-.010-1e-8),
              'source':self.provenance,'normative_claim':False}
        return f[1:],D,meta


def integrated_free_strains_diagnostic(prepared,*, concrete_at_bars_C, source_provenance:str,
                                       accept_integration_convention:bool=False,
                                       concrete_at_corners_C=None):
    """EXPLICIT OPT-IN diagnostic integration of tabulated thermal coefficients.

    Assumes alpha_bt + alpha_cs are instantaneous d(eps_free)/dT. The tables
    do NOT independently establish this integration convention or a cyclic
    heating/cooling law. No claim of normative constitutive qualification.
    """
    from rc_fire.materials.normative import (THERMAL_T,ALPHA_BT_MICRO,ALPHA_CS_MICRO)
    if not accept_integration_convention:
        raise CoupledMemberError('thermal coefficient integration convention must be explicitly acknowledged')
    p=prepared
    if not source_provenance:raise CoupledMemberError('source_provenance required')
    family=p.strength_data.get('concrete_family')
    if family not in ALPHA_BT_MICRO:
        raise CoupledMemberError('unsupported aggregate family')
    cb=_finite_vector(concrete_at_bars_C,p.bar_temperature_C.shape,'concrete temperature at bars')
    corners=None if concrete_at_corners_C is None else _finite_vector(concrete_at_corners_C,(4,),'corner temperature')
    def concrete_integral(temp):
        arr=_finite_vector(temp,name='temperature')
        if np.any((arr<20)|(arr>800)):raise CoupledMemberError('temperature outside 20-800')
        # Integrate piecewise-linear coefficient values *exactly* across all
        # norm table breakpoints, assuming linear interpolation as a NUMERIC
        # ENGINEERING convention. Hold [20,50] and [700,800] endpoint values.
        knots=np.array([20.,50.,100.,300.,500.,700.,800.])
        coef=(np.interp(knots,THERMAL_T,ALPHA_BT_MICRO[family])+
              np.interp(knots,THERMAL_T,ALPHA_CS_MICRO[family]))*1e-6
        acc=np.zeros(len(knots))
        acc[1:]=np.cumsum((coef[1:]+coef[:-1])*.5*np.diff(knots))
        return np.interp(arr,knots,acc)
    def steel_integral(temp):
        arr=_finite_vector(temp,name='temperature')
        if np.any((arr<20)|(arr>800)):raise CoupledMemberError('steel temperature outside 20-800')
        return 1e-6*(.0025*(arr**2-20**2)+11.5*(arr-20))
    return {'free_concrete':concrete_integral(p.concrete_temperature_C),
            'free_steel':steel_integral(p.bar_temperature_C),
            'free_concrete_at_bars':concrete_integral(cb),
            'free_concrete_at_corners':None if corners is None else concrete_integral(corners),
            'provenance':source_provenance+';assumed_incremental_integral_not_normative',
            'normative_claim':False,'fire_resistance_status':'not_demonstrated',
            'convention':'integral_20_to_theta_of_alpha_bt_plus_alpha_cs_and_alpha_s'}


_GQ=(.5-.5*math.sqrt(3/5),.5,.5+.5*math.sqrt(3/5))
_GW=(5/18,8/18,5/18)


def _dofs(node,axis,nodes):
    return np.array([2*node+axis*2*nodes,2*node+1+axis*2*nodes],dtype=int)


def _beam_assembly(z,N,law_at_gauss,displacements,imperfection,q,point_forces):
    nodes=len(z);nd=4*nodes
    fint=np.zeros(nd);K=np.zeros((nd,nd));G=np.zeros((nd,nd));F=np.array(point_forces,copy=True)
    states=[]
    for i in range(nodes-1):
        h=z[i+1]-z[i]
        idx=np.r_[_dofs(i,0,nodes),_dofs(i+1,0,nodes),
                  _dofs(i,1,nodes),_dofs(i+1,1,nodes)]
        local=displacements[idx]
        local_imp=imperfection[idx]
        for j,(t,wt) in enumerate(zip(_GQ,_GW)):
            H,Hp,Hpp=_shape(t,h)
            B=np.zeros((2,8));B[0,:4]=-Hpp;B[1,4:]=-Hpp
            P=np.zeros((2,8));P[0,:4]=Hp;P[1,4:]=Hp
            shape=np.zeros((2,8));shape[0,:4]=H;shape[1,4:]=H
            law=law_at_gauss(i,j)
            M,D,meta=law.evaluate(B@local,N)
            M=_finite_vector(M,(2,),'moment vector')
            D=_finite_vector(D,(2,2),'tangent')
            if not np.allclose(D,D.T,rtol=1e-9,atol=1e-7) or np.linalg.eigvalsh(D)[0]<=0:
                raise CoupledMemberError('nonpositive or nonsymmetric sectional tangent')
            weight=h*wt
            fint[idx]+=weight*B.T@M
            K[np.ix_(idx,idx)]+=weight*(B.T@D@B)
            G[np.ix_(idx,idx)]+=weight*P.T@P
            qgp=(1-t)*q[i]+t*q[i+1]
            F[idx]+=weight*shape.T@qgp
            states.append({'z_m':float(z[i]+t*h),'curvature_1pm':(B@local).tolist(),
                           'moments_kNm':M.tolist(),'strain_limits_satisfied':meta.get('strain_limits_satisfied'),
                           'section_model':meta.get('model'),
                           'material_source':meta.get('source'),
                           'max_concrete_compressive_strain':meta.get('max_concrete_compressive_strain'),
                           'max_steel_tensile_strain':meta.get('max_steel_tensile_strain'),
                           'eps_cu2':meta.get('eps_cu2'),
                           'tensile_steel_limit':meta.get('tensile_steel_limit'),
                           'concrete_max_method':meta.get('concrete_max_method'),
                           'corner_eigenstrain_explicit':meta.get('corner_eigenstrain_explicit'),
                           'bar_temperature_min_C':meta.get('bar_temperature_min_C'),
                           'max_boundary_temperature_C':meta.get('max_boundary_temperature_C'),
                           'reference_strength_mode':meta.get('reference_strength_mode')})
    return fint,K,G,F,states


def _boundary_matrix(left,right,nodes):
    def as_pair(s):
        if isinstance(s,EndSupport):return (s,s)
        if not isinstance(s,(tuple,list)) or len(s)!=2 or any(not isinstance(v,EndSupport) for v in s):
            raise CoupledMemberError('end supports must be EndSupport or (support_x,support_y)')
        return tuple(s)
    left=as_pair(left);right=as_pair(right)
    for s in (*left,*right):s.validate()
    nd=4*nodes
    fixed={};springs=np.zeros(nd)
    for ni,pair in ((0,left),(nodes-1,right)):
        for axis,s in enumerate(pair):
            iw,ir=_dofs(ni,axis,nodes)
            if s.kind in ('pinned','fixed'):
                fixed[int(iw)]=float(np.asarray(s.displacement_m,dtype=float).reshape(-1)[axis if np.asarray(s.displacement_m).size==2 else 0])
            if s.kind in ('fixed','guided'):
                fixed[int(ir)]=float(np.asarray(s.rotation_rad,dtype=float).reshape(-1)[axis if np.asarray(s.rotation_rad).size==2 else 0])
            if s.kind=='elastic':
                kw=np.asarray(s.lateral_spring_kNpm,dtype=float).reshape(-1)
                kr=np.asarray(s.rotational_spring_kNm,dtype=float).reshape(-1)
                springs[iw]+=kw[axis if kw.size==2 else 0]
                springs[ir]+=kr[axis if kr.size==2 else 0]
    return fixed,springs


def solve_coupled_beam(z_m:Sequence[float], N_kN:float, *,
                       law_at_gauss:Callable[[int,int],object],
                       left:EndSupport=EndSupport('pinned'),
                       right:EndSupport=EndSupport('pinned'),
                       distributed_load_kNpm=None,
                       nodal_forces=None,
                       initial_imperfection=None,
                       max_iterations:int=30, tolerance:float=1e-7)->dict:
    """Small-rotation nonlinear section/geometric equilibrium, two axes.

    `law_at_gauss(element, gauss_index)` must return a section law with
    evaluate(curvature_vector [1/m], axial_force_kN) -> (M[2], D[2x2],meta).
    EVERY material integration point has its own explicitly supplied law;
    no hidden material/thermal interpolation along z.

    Result is diagnostic even for converged equilibrium, never normative ULS.
    """
    z=_finite_vector(z_m,name='stations')
    if z.ndim!=1 or len(z)<2 or abs(z[0])>1e-12 or np.any(np.diff(z)<=0):
        raise CoupledMemberError('increasing z starting at zero and >=2 nodes required')
    n=len(z);nd=4*n
    N=float(N_kN)
    if not math.isfinite(N) or N<0:raise CoupledMemberError('compression N must be finite and >=0')
    if max_iterations<1 or not 0<tolerance<.01:raise CoupledMemberError('invalid solver settings')
    q=np.zeros((n,2)) if distributed_load_kNpm is None else _finite_vector(distributed_load_kNpm,(n,2),'distributed loads')
    ff=np.zeros(nd) if nodal_forces is None else _finite_vector(nodal_forces,(nd,),'nodal loads')
    initial=np.zeros(nd) if initial_imperfection is None else _finite_vector(initial_imperfection,(nd,),'initial imperfections')
    fixed,springs=_boundary_matrix(left,right,n)
    free=np.asarray([i for i in range(nd) if i not in fixed],dtype=int)
    if len(free)==0:raise CoupledMemberError('no independent unknown degrees of freedom')
    d=np.zeros(nd)
    for k,v in fixed.items():d[k]=v
    # Enforce homogeneous imperfections at displacement-constrained DOFs;
    # rotational imperfection can be supplied in the remaining DOFs.
    if any(abs(initial[k])>1e-10 for k in fixed):
        raise CoupledMemberError('initial imperfection incompatible with constrained support DOF')
    evaluated=[]
    for it in range(max_iterations):
        try: fi,K,G,F,states=_beam_assembly(z,N,law_at_gauss,d,initial,q,ff)
        except (ArithmeticError,ValueError,np.linalg.LinAlgError) as exc:
            return {'status':'blocked_material','reason':str(exc),'normative_claim':False,
                    'fire_resistance_status':'not_demonstrated'}
        residual=fi-N*G@(d+initial)+springs*d-F
        tangent=K-N*G+np.diag(springs)
        T=tangent[np.ix_(free,free)];r=residual[free]
        eig=float(np.linalg.eigvalsh((T+T.T)/2)[0])
        if eig<=max(1e-9,1e-12*max(1.,float(np.linalg.eigvalsh(T)[-1]))):
            return {'status':'critical_or_nonpositive_tangent','iteration':it,
                    'tangent_min_eigenvalue':eig,'normative_claim':False,
                    'fire_resistance_status':'not_demonstrated'}
        scale=max(1.,np.linalg.norm(F[free]),np.linalg.norm(fi[free]))
        if np.linalg.norm(r)/scale<tolerance:
            crossed=any(s['strain_limits_satisfied'] is False for s in states)
            return {'status':'strain_limits_exceeded_diagnostic' if crossed else 'evaluated_diagnostic','iterations':it,
                    'w_x_m':d[:2*n:2].tolist(),'theta_x_rad':d[1:2*n:2].tolist(),
                    'w_y_m':d[2*n::2].tolist(),'theta_y_rad':d[2*n+1::2].tolist(),
                    'total_w_x_m':(d[:2*n:2]+initial[:2*n:2]).tolist(),
                    'total_w_y_m':(d[2*n::2]+initial[2*n::2]).tolist(),
                    'integration_stations':states,
                    'any_strain_limit_exceeded':crossed,
                    'tangent_min_eigenvalue':eig,
                    'relative_equilibrium_residual':float(np.linalg.norm(r)/scale),
                    'normative_claim':False,'fire_resistance_status':'not_demonstrated',
                    'missing_qualification':['fire constitutive law','ULS interaction',
                      'thermal path dependence','end restraint in full frame',
                      'spalling','fire load combinations','R(t)']}
        try:step=np.linalg.solve(T,-r)
        except np.linalg.LinAlgError as exc:
            return {'status':'singular','reason':str(exc),'normative_claim':False,
                    'fire_resistance_status':'not_demonstrated'}
        accepted=False
        for factor in (1.,.5,.25,.125,.0625,.03125):
            trial=d.copy();trial[free]+=factor*step
            try: nf,_,ng,nfext,_=_beam_assembly(z,N,law_at_gauss,trial,initial,q,ff)
            except (CoupledMemberError,ValueError,ArithmeticError):continue
            rr=nf-N*ng@(trial+initial)+springs*trial-nfext
            if np.linalg.norm(rr[free])<np.linalg.norm(r)*(1-1e-5):
                d=trial;accepted=True;break
        if not accepted:
            return {'status':'line_search_failed','iterations':it,
                    'relative_residual':float(np.linalg.norm(r)/scale),
                    'normative_claim':False,'fire_resistance_status':'not_demonstrated'}
    return {'status':'iteration_limit','iterations':max_iterations,
            'normative_claim':False,'fire_resistance_status':'not_demonstrated'}


def linear_laws_at_gauss(z_m, D_xx_kNm2:Sequence[float], D_yy_kNm2:Sequence[float], *,
                         D_xy_kNm2:Sequence[float]|None=None,
                         free_curvature_x=None,free_curvature_y=None,
                         provenance:str='external_diag'):
    """Piecewise linear nodal stiffness and eigen-curvature, explicitly DIAGNOSTIC.

    This is NOT a substitute for temperature-dependent fibre laws.  Interpolates
    only values supplied at every member station; no guess from temperature.
    """
    z=_finite_vector(z_m,name='z');n=len(z)
    xx=_finite_vector(D_xx_kNm2,(n,),'D_xx')
    yy=_finite_vector(D_yy_kNm2,(n,),'D_yy')
    xy=np.zeros(n) if D_xy_kNm2 is None else _finite_vector(D_xy_kNm2,(n,),'D_xy')
    kx=np.zeros(n) if free_curvature_x is None else _finite_vector(free_curvature_x,(n,),'kth_x')
    ky=np.zeros(n) if free_curvature_y is None else _finite_vector(free_curvature_y,(n,),'kth_y')
    if not provenance:raise CoupledMemberError('stiffness/curvature source must be explicit')
    laws=[]
    for i in range(n-1):
        gp=[]
        for t in _GQ:
            D=np.array([[np.interp(t,[0.,1.],[xx[i],xx[i+1]]),np.interp(t,[0.,1.],[xy[i],xy[i+1]])],
                        [np.interp(t,[0.,1.],[xy[i],xy[i+1]]),np.interp(t,[0.,1.],[yy[i],yy[i+1]])]])
            free=np.array([(1-t)*kx[i]+t*kx[i+1],(1-t)*ky[i]+t*ky[i+1]])
            gp.append(LinearSectionLaw(D,free,provenance))
        laws.append(gp)
    return lambda element,gauss: laws[element][gauss]


def fibre_laws_at_gauss(prepared_and_eigenstrain:Sequence[Sequence[FiberSectionLaw]]):
    """Capture explicit 3-gauss fibre sections PER ELEMENT; never interpolate."""
    laws=tuple(tuple(row) for row in prepared_and_eigenstrain)
    if not laws or any(len(row)!=3 or any(not isinstance(l,FiberSectionLaw) for l in row) for row in laws):
        raise CoupledMemberError('provide exactly three heated fibre laws per beam element')
    return lambda i,g: laws[i][g]


def heated_laws_from_explicit_thermal_stations(stations,*,grid=12,
                      accept_integration_convention=False,
                      strength_mode='legacy_accidental_design_diagnostic'):
    """End-to-end K-Annex field to R063C fibres to beam Gauss laws.

    `stations[i][g]` must be dict(column=<full column>,thermal=<Annex K result>)
    with exactly 3 integration sections per member segment. Every station is
    explicit; NO inference of missing temperature/thermal state along z.

    Owns only the *diagnostic* thermal eigenstrain integral. Other historical
    heat/maturity/creep effects, constraints and material-law uncertainty are
    not resolved. No R90, even if the FE solver converges.
    """
    from rc_fire.mechanics.normative import prepare_section
    from rc_fire.mechanics.fire_strength import select_fire_reference_strength
    from rc_fire.thermal import temperature_rectangle,RectangularExposure
    if not accept_integration_convention:
        raise CoupledMemberError('explicit opt-in for non-normative thermal eigenstrain required')
    if not stations:raise CoupledMemberError('at least one member element required')
    all_rows=[]; evidence=[]
    for i,row in enumerate(stations):
        if len(row)!=3:raise CoupledMemberError('each member element requires 3 explicit temperature stations')
        laws=[]
        for j,entry in enumerate(row):
            if not isinstance(entry,dict) or 'column' not in entry or 'thermal' not in entry:
                raise CoupledMemberError(f'missing full thermal input for element {i} Gauss {j}')
            c=entry['column'];th=entry['thermal']
            if abs(float(c['fire_minutes'])-float(th['fire_minutes']))>1e-9:
                raise CoupledMemberError(f'temperature exposure time inconsistent at element {i},Gauss {j}')
            if set(c['thermal_spec']['exposed_faces'])!=set(th['exposed_faces']):
                raise CoupledMemberError('exposed faces mismatch between column and thermal result')
            p=prepare_section(c,th,grid=grid,above_800_policy='reject')
            p,_=select_fire_reference_strength(p,mode=strength_mode)
            exp=RectangularExposure(c['b_mm'],c['h_mm'],tuple(th['exposed_faces']))
            bars=c['bars']
            cb,_=temperature_rectangle(exp,th['coefficients'],c['fire_minutes'],
                np.asarray([b['x_mm'] for b in bars],dtype=float),
                np.asarray([b['y_mm'] for b in bars],dtype=float))
            cx=np.array([0.,c['b_mm'],0.,c['b_mm']])
            cy=np.array([0.,0.,c['h_mm'],c['h_mm']])
            corner_theta,_=temperature_rectangle(exp,th['coefficients'],c['fire_minutes'],cx,cy)
            f=integrated_free_strains_diagnostic(p,concrete_at_bars_C=cb,
                concrete_at_corners_C=corner_theta,
                source_provenance='СП 2.02.05-2026 §8.2.19, tables 11,12, equation (6)',
                accept_integration_convention=True)
            laws.append(FiberSectionLaw(p,free_concrete=f['free_concrete'],
                free_steel=f['free_steel'],free_concrete_at_bars=f['free_concrete_at_bars'],
                free_concrete_at_corners=f['free_concrete_at_corners'],
                provenance=f['provenance']))
            evidence.append({'element':i,'gauss':j,'fire_minutes':float(c['fire_minutes']),
              'max_boundary_C':float(p.boundary_temperature_max_C),
              'concrete_family':p.strength_data['concrete_family'],
              'bar_count':len(p.bar_ids),'material_law':'R063C_diagnostic',
              'thermal_coefficients':'incremental_integration_assumed_not_normative',
              'strength_reference':strength_mode})
        all_rows.append(laws)
    return {'law_at_gauss':fibre_laws_at_gauss(all_rows),'evidence':evidence,
      'normative_claim':False,'fire_resistance_status':'not_demonstrated',
      'qualification':'diagnostic_thermomechanical_interaction_only'}
