"""R0.6.9D3 — transient 2D cross-sectional heat equation, Belarus TKP.

TKP EN 1992-1-2-2009 §§3.3.2–3.3.3, 4.3.2, Belarus National Annex:
  rho(T)*cp(T) * dT/dt = div(lambda(T) grad(T))
  q_fire = h_c*(T_g-T_surface)+eps*sigma*(T_r^4-T_surface^4).

Conservative cell-centred finite-volume, implicit in temperature and exact
temperature-enthalpy differences, using a nonlinear Picard iteration and
radiative surface heat balance. No numerical use of SP Annex K temperatures.
Actual standard fire *gas* curve is SP 2.02.05-2026 formula (3);
TKP Annex A gives reference h_c=25 W/m2/K and eps_concrete=.7. These boundary
choices MUST be selected explicitly. Full EN 1991-1-2 action approval and
experimental validation under TKP §4.3.4 are separate outstanding tasks.

Source allows ignoring moisture transport and direct bar heat-conduction
perturbation (§4.3.2(3)(4)). Moisture affects cp peak (§3.3.2).
No spalling, latent explicit transport, chemical degradation or loaded
thermo-mechanical feedback is simulated. Not an R(t) result.
"""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve

from rc_fire.materials.tkp_en1992_fire import (
    concrete_thermal_conductivity, concrete_specific_heat, concrete_density_ratio)

VERSION="R0.6.9D3-conservative-2D-TKP-thermal-FVM-v1"
SOURCE="ТКП EN 1992-1-2-2009 §§3.3.2,3.3.3,4.3.2; НП.1 lower lambda"
FIRE_SOURCE="СП 2.02.05-2026, формула (3): стандартный температурный режим"
ANNEX_A_BC_SOURCE="ТКП EN 1992-1-2-2009, приложение А: h_c=25, eps=0.7"
STEFAN_BOLTZMANN=5.670374419e-8
FACES=("left","right","bottom","top")


class TKPHeatError(ValueError):
    """Invalid boundary/source domain, energy conservation or nonlinear solve."""


def _finite(v,name,*,lo=None,hi=None):
    if isinstance(v,bool):
        raise TKPHeatError(name+": numeric value required")
    try: x=float(v)
    except (TypeError,ValueError) as exc:
        raise TKPHeatError(name+": numeric value required") from exc
    if not math.isfinite(x) or (lo is not None and x<lo) or (hi is not None and x>hi):
        raise TKPHeatError(name+": outside finite source domain")
    return x


def standard_fire_gas_temperature(t_minutes):
    """SP 2.02.05-2026 Eq. (3). Source choice is explicit, not EN1-1-2."""
    t=_finite(t_minutes,"t_minutes",lo=0)
    return 20.+345.*math.log10(8.*t+1.)


def reference_annex_a_boundary(*,moisture_mass_pct=1.5):
    """Make the Annex A reference assumption EXPLICIT in the calling code."""
    w=_finite(moisture_mass_pct,"moisture_mass_pct",lo=0,hi=3)
    return {
        'fire_curve':'sp2026_standard_formula_3',
        'fire_curve_source':FIRE_SOURCE,
        'convection_W_m2_K':25.,
        'surface_emissivity':.7,
        'gas_equals_radiation_temperature':True,
        'environment_source':ANNEX_A_BC_SOURCE,
        'moisture_mass_pct':w,
        'moisture_source':'user_selected_mass_pct_not_inferred_from_relative_humidity',
        'unexposed_faces':'adiabatic_assumption',
    }


def _check_boundary(boundary):
    if not isinstance(boundary,dict):
        raise TKPHeatError("explicit TKP fire boundary contract required")
    if boundary.get('fire_curve')!='sp2026_standard_formula_3':
        raise TKPHeatError("unknown fire curve; EN1991 fire action not declared")
    if boundary.get('gas_equals_radiation_temperature') is not True:
        raise TKPHeatError("gas/radiation profiles must be explicitly consistent")
    if boundary.get('unexposed_faces')!='adiabatic_assumption':
        raise TKPHeatError("unexposed face heat transfer not specified")
    hc=_finite(boundary.get('convection_W_m2_K'),'convection',lo=0,hi=200)
    eps=_finite(boundary.get('surface_emissivity'),'emissivity',lo=0,hi=1)
    moist=_finite(boundary.get('moisture_mass_pct'),'moisture',lo=0,hi=3)
    if not boundary.get('moisture_source'):
        raise TKPHeatError("moisture source declaration required")
    return hc,eps,moist


@lru_cache(maxsize=32)
def _enthalpy_nodes(moisture):
    """Volumetric energy/kg ambient density, J/kg (rho(T)/rho20 in integrand).

    Integrate pointwise rho(T)*cp(T); using H(Tn)-H(To) makes each
    heating step *energy conservative*. The temperature table is
    discretized at 0.25 °C (not a source material approximation).
    """
    t=np.linspace(20.,1200.,4721)
    cp=np.asarray([concrete_specific_heat(float(v),
               mass_moisture_pct=moisture) for v in t])
    density=np.asarray([concrete_density_ratio(float(v)) for v in t])
    volcap=cp*density
    cum=np.concatenate(([0.],np.cumsum(
             (volcap[:-1]+volcap[1:])*0.5*np.diff(t))))
    return t,cum


def _enthalpy(T,moist,rho20):
    nodes,integral=_enthalpy_nodes(moist)
    if np.any(T<20-1e-8) or np.any(T>1200+1e-8):
        raise TKPHeatError("temperature outside 20..1200 C material table")
    return rho20*np.interp(np.clip(T,20.,1200.),nodes,integral)


def _volumetric_capacity(T,moist,rho20):
    arr=np.asarray(T)
    return rho20*np.asarray([concrete_density_ratio(float(v))*
              concrete_specific_heat(float(v),mass_moisture_pct=moist)
              for v in arr.ravel()]).reshape(arr.shape)


def _conductivity(T):
    arr=np.asarray(T,dtype=float)
    if np.any(arr<20.-1e-6) or np.any(arr>1200.+1e-6):
        raise TKPHeatError('source conductivity temperature outside 20..1200 C')
    return np.asarray([concrete_thermal_conductivity(float(v))
            for v in np.clip(arr,20.,1200.).ravel()]).reshape(arr.shape)


def _surface_exchange(Tcell,k,d_half,T_gas,hc,emissivity):
    """Equivalent g per area and Tenv for conductive half-cell + radiation.

    Radiation is represented by the *exact secant* between gas and
    surface temperatures: eps*sigma*(TgK^4-TsK^4)=hrad*(Tg-Ts).
    Solve local nonlinear surface balance by fixed-point iteration.
    """
    cond=k/d_half
    Tsurf=Tcell
    hr=0.
    for _ in range(12):
        gk=T_gas+273.15; sk=Tsurf+273.15
        hr=emissivity*STEFAN_BOLTZMANN*(gk+sk)*(gk*gk+sk*sk)
        new=(cond*Tcell+(hc+hr)*T_gas)/(cond+hc+hr)
        if abs(new-Tsurf)<1e-10:
            Tsurf=new
            break
        Tsurf=new
    g=cond*(hc+hr)/(cond+hc+hr)
    return g,Tsurf, g*(T_gas-Tcell)


def _heat_step(Told,*,dt_seconds,dx,dy,rho20,moist,hc,eps,Tgas,
               exposed,nonlinear_tol=2e-4,max_picard=65):
    ny,nx=Told.shape
    m=nx*ny
    V=dx*dy
    old_enthalpy=_enthalpy(Told,moist,rho20)
    guess=Told.copy()
    last=None
    last_q=0.
    for it in range(max_picard):
        k=_conductivity(guess)
        hnew=_enthalpy(guess,moist,rho20)
        diff=guess-Told
        cap=np.divide(hnew-old_enthalpy,diff,
            out=_volumetric_capacity(guess,moist,rho20),
            where=np.abs(diff)>1e-8)
        if np.any(cap<=0) or not np.all(np.isfinite(cap)):
            raise TKPHeatError("nonpositive enthalpy secant heat capacity")
        diag=(cap*V/dt_seconds).ravel().copy()
        rhs=(cap*V/dt_seconds*Told).ravel().copy()
        ii=[];jj=[];vv=[]
        boundary_terms=[]
        # nearest-neighbour fluxes, equal and opposite by construction
        for y in range(ny):
            for x in range(nx):
                i=y*nx+x
                ki=k[y,x]
                for xx,yy,area,dist in ((x+1,y,dy,dx),(x,y+1,dx,dy)):
                    if xx>=nx or yy>=ny:continue
                    j=yy*nx+xx
                    kj=k[yy,xx]
                    harmonic=2*ki*kj/(ki+kj)
                    g=harmonic*area/dist
                    diag[i]+=g;diag[j]+=g
                    ii.extend((i,j));jj.extend((j,i));vv.extend((-g,-g))
                for side,active,dhalf,area in (
                  ('left',x==0,dx/2,dy),
                  ('right',x==nx-1,dx/2,dy),
                  ('bottom',y==0,dy/2,dx),
                  ('top',y==ny-1,dy/2,dx)):
                    if active and side in exposed:
                        g,ts,q=_surface_exchange(float(guess[y,x]),
                             float(ki),dhalf,Tgas,hc,eps)
                        g*=area
                        diag[i]+=g
                        rhs[i]+=g*Tgas
                        boundary_terms.append((side,x,y,ts))
        rows=np.r_[np.arange(m),np.asarray(ii,dtype=int)]
        cols=np.r_[np.arange(m),np.asarray(jj,dtype=int)]
        vals=np.r_[diag,np.asarray(vv,dtype=float)]
        from scipy.sparse import csr_matrix
        mat=coo_matrix((vals,(rows,cols)),shape=(m,m)).tocsr()
        nxt=np.asarray(spsolve(mat,rhs),dtype=float).reshape(ny,nx)
        if not np.all(np.isfinite(nxt)):
            raise TKPHeatError("nonlinear thermal matrix solve failed")
        if np.min(nxt)<20.-1e-6 or np.max(nxt)>max(Tgas,20.)+1e-5:
            raise TKPHeatError("heat equation maximum principle violated")
        # A linear solve of a perfectly adiabatic 20 °C section may round
        # to 19.99999999999999. Remove ONLY floating noise (<=1e-6 C);
        # do not accept genuinely below-source-temperature field values.
        nxt=np.maximum(nxt,20.)
        delta=float(np.max(np.abs(nxt-guess)))
        guess=nxt
        last=boundary_terms
        if delta<nonlinear_tol:
            break
    else:
        raise TKPHeatError("Picard thermal iterations did not converge")
    # Reevaluate the boundary with the converged final temperature and
    # calculate physically exact net surface heat flux.
    q_total=0.
    surfaces={face:[] for face in FACES}
    kval=_conductivity(guess)
    for y in range(ny):
        for x in range(nx):
            for face,active,dhalf,area in (
              ('left',x==0,dx/2,dy),
              ('right',x==nx-1,dx/2,dy),
              ('bottom',y==0,dy/2,dx),
              ('top',y==ny-1,dy/2,dx)):
                if not active:continue
                if face in exposed:
                    g,ts,q=_surface_exchange(float(guess[y,x]),
                             float(kval[y,x]),dhalf,Tgas,hc,eps)
                    q_total+=q*area
                else:
                    ts=float(guess[y,x])
                surfaces[face].append(float(ts))
    stored=float(np.sum((_enthalpy(guess,moist,rho20)-old_enthalpy)*V))
    gained=q_total*dt_seconds
    energy_err=abs(stored-gained)/max(1.,abs(stored),abs(gained))
    if energy_err>3e-4:
        raise TKPHeatError(
            f"nonlinear heat-step energy residual {energy_err:.3e} exceeds 3e-4")
    return guess,{'picard_iterations':it+1,'max_delta_C':delta,
        'energy_delta_J_per_m':stored,'boundary_heat_J_per_m':gained,
        'relative_energy_residual':energy_err,
        'surface_temperature_C':surfaces}


def _snapshot(T,surfaces,t,*,b,h,exposed):
    ny,nx=T.shape
    field={'time_minutes':float(t),'grid_temperature_C':T.tolist(),
       'surface_temperature_C':{k:list(v) for k,v in surfaces.items()},
       'boundary_max_C':max([float(np.max(T)),
           *[max(v) for v in surfaces.values() if v]]),
       'cell_max_C':float(np.max(T)),
       'cell_min_C':float(np.min(T))}
    return field


def solve_tkp_2d_heat(column,*,boundary,
        cell_count_x=12,cell_count_y=12,max_step_minutes=5.,
        sample_times_minutes=None,initial_temperature_C=20.,
        max_picard_iterations=65):
    """Conservative 2D transient response at user-requested sample times.

    The results are not globally normative without independent source
    boundary qualification, thermal validation and experimental comparisons.
    """
    if not isinstance(column,dict):
        raise TKPHeatError('column dictionary required')
    for n in (cell_count_x,cell_count_y):
        if type(n) is not int or not 4<=n<=80:
            raise TKPHeatError("mesh dimensions must be integer 4..80")
    b=_finite(column.get('b_mm'),'b_mm',lo=10,hi=2000)/1000.
    h=_finite(column.get('h_mm'),'h_mm',lo=10,hi=2000)/1000.
    duration=_finite(column.get('fire_minutes'),'fire_minutes',lo=0.1,hi=480.)
    initial=_finite(initial_temperature_C,'initial_temperature_C',lo=20,hi=20)
    dt=_finite(max_step_minutes,'max_step_minutes',lo=.25,hi=30.)
    if type(max_picard_iterations) is not int or not 3<=max_picard_iterations<=100:
        raise TKPHeatError("max_picard_iterations out of range")
    spec=column.get('thermal_spec') or {}
    faces=spec.get('exposed_faces')
    if not isinstance(faces,(list,tuple)) or len(faces)!=len(set(faces)) or \
       not set(faces).issubset(set(FACES)):
        raise TKPHeatError("exposed_faces must be a unique subset of four sides")
    if spec.get('concrete_family') not in ('siliceous','calcareous'):
        raise TKPHeatError("material family must be heavy siliceous/calcareous concrete")
    rho20=_finite(spec.get('dry_density_kg_m3'),'rho20_kg_m3',lo=800,hi=3000)
    hc,eps,moist=_check_boundary(boundary)
    req=sample_times_minutes
    if req is None:req=[duration]
    if not isinstance(req,(list,tuple)) or not req:
        raise TKPHeatError("at least one requested time point required")
    wanted=sorted(set(_finite(v,'sample time',lo=0.01,hi=duration)
                      for v in req))
    if abs(wanted[-1]-duration)>1e-8:
        wanted.append(duration)
    if len(wanted)>180:
        raise TKPHeatError("too many requested snapshots")
    dx=b/cell_count_x;dy=h/cell_count_y
    T=np.full((cell_count_y,cell_count_x),initial,dtype=float)
    surfaces={face:([initial]*(cell_count_y if face in ('left','right') else cell_count_x))
              for face in FACES}
    t=0.;snapshots=[];step_logs=[];total_in=0.;worst_error=0.
    for target in wanted:
        while t<target-1e-8:
            trial_dt=min(dt,target-t)
            # If the nonlinear peak at the 100-115 C moisture transition
            # causes Picard stiffness, reduce the step, NEVER override
            # the conservation check or accept a divergent state.
            while True:
                try:
                    now=T.copy()
                    updated,evidence=_heat_step(T,dt_seconds=trial_dt*60,
                        dx=dx,dy=dy,rho20=rho20,moist=moist,hc=hc,eps=eps,
                        Tgas=standard_fire_gas_temperature(t+trial_dt),
                        exposed=set(faces),max_picard=max_picard_iterations)
                    break
                except TKPHeatError as exc:
                    if trial_dt<=.251:
                        raise TKPHeatError(f'time {t:.3f} min: {exc}') from exc
                    trial_dt*=.5
            T=updated
            t+=trial_dt
            total_in+=evidence['boundary_heat_J_per_m']
            worst_error=max(worst_error,evidence['relative_energy_residual'])
            step_logs.append({'end_time_minutes':round(t,10),
                'dt_minutes':trial_dt,
                'gas_temperature_C':standard_fire_gas_temperature(t),
                'picard_iterations':evidence['picard_iterations'],
                'relative_energy_residual':evidence['relative_energy_residual'],
                'net_boundary_heat_J_per_m':evidence['boundary_heat_J_per_m']})
            surfaces=evidence['surface_temperature_C']
        snapshots.append(_snapshot(T,surfaces,target,b=b,h=h,exposed=faces))
    actual_energy=float(np.sum(_enthalpy(T,moist,rho20)-
               _enthalpy(np.full_like(T,initial),moist,rho20))*dx*dy)
    global_error=abs(actual_energy-total_in)/max(1.,abs(actual_energy),abs(total_in))
    if global_error>3e-4:
        raise TKPHeatError("cumulative heat balance does not close")
    return {
        'version':VERSION,'status':'evaluated_tkp_diagnostic',
        'thermal_method':'TKP_4.3.2_FVM',
        'governing_source':SOURCE,
        'boundary_source':boundary.get('environment_source'),
        'fire_curve_source':FIRE_SOURCE,
        'fire_time_minutes':duration,'fire_minutes':duration,
        'exposed_faces':list(faces),
        'column_id':column.get('id'),
        'material_family':spec['concrete_family'],
        'ambient_density_kg_m3':rho20,
        'initial_temperature_C':initial,
        'moisture_mass_pct':moist,
        'moisture_provenance':boundary['moisture_source'],
        'boundary_parameters':boundary,
        'grid':{'nx':cell_count_x,'ny':cell_count_y,
                'width_mm':1000*b,'height_mm':1000*h,
                'dx_mm':1000*dx,'dy_mm':1000*dy},
        'snapshots':snapshots,
        'step_log':step_logs,
        'last_boundary_max_C':snapshots[-1]['boundary_max_C'],
        'energy_balance':{
            'enthalpy_change_J_per_m':actual_energy,
            'integrated_boundary_heat_J_per_m':total_in,
            'relative_cumulative_residual':global_error,
            'worst_step_relative_residual':worst_error},
        'model_limitations':[
            'SP standard fire boundary assumed from equation (3), not independently verified EN1991 actions',
            'Annex A convection 25 and emissivity 0.7 are selected reference assumptions',
            'unexposed faces assumed adiabatic',
            'moisture effects via cp peak only; no explicit moisture migration',
            'reinforcement perturbation of heat flow neglected as permitted in TKP 4.3.2',
            'concrete spalling and material cracking not simulated',
            'TKP 4.3.4 experimental validation not established',
            'mesh and time convergence required for production interpretation'],
        'normative_claim':False,'R_t_minutes':None,
        'fire_resistance_status':'not_demonstrated'}


def select_tkp_snapshot(thermal, time_minutes):
    if not isinstance(thermal,dict) or thermal.get('thermal_method')!='TKP_4.3.2_FVM':
        raise TKPHeatError("TKP thermal solution required")
    t=_finite(time_minutes,'time_minutes',lo=0)
    snap=next((s for s in thermal['snapshots']
                if abs(s['time_minutes']-t)<1e-8),None)
    if snap is None:
        raise TKPHeatError('requested time not stored; no temporal interpolation')
    return {**thermal,'fire_minutes':t,'snapshot':snap}


def sample_tkp_temperature(field,x_mm,y_mm):
    """Bilinear actual centre/boundary field sampling, no Annex K fallback.

    Boundary at face centres is from implicit thermal-convective-radiative
    boundary balance. Corner temperature is an explicitly disclosed
    interpolation of the two adjacent face nodes; not a separately solved
    corner flux. The entire field is bounded by the applied gas heating.
    """
    if field.get('thermal_method')!='TKP_4.3.2_FVM' or \
       not isinstance(field.get('snapshot'),dict):
        raise TKPHeatError('time-resolved TKP snapshot required')
    snap=field['snapshot'];g=field['grid']
    b=g['width_mm'];h=g['height_mm']
    x=_finite(x_mm,'x_mm',lo=0,hi=b)
    y=_finite(y_mm,'y_mm',lo=0,hi=h)
    data=np.asarray(snap['grid_temperature_C'],dtype=float)
    ny,nx=data.shape
    surf=snap['surface_temperature_C']
    padded=np.zeros((ny+2,nx+2),dtype=float)
    padded[1:-1,1:-1]=data
    padded[1:-1,0]=surf['left'];padded[1:-1,-1]=surf['right']
    padded[0,1:-1]=surf['bottom'];padded[-1,1:-1]=surf['top']
    padded[0,0]=.5*(padded[1,0]+padded[0,1])
    padded[0,-1]=.5*(padded[1,-1]+padded[0,-2])
    padded[-1,0]=.5*(padded[-2,0]+padded[-1,1])
    padded[-1,-1]=.5*(padded[-2,-1]+padded[-1,-2])
    xp=np.r_[0.,(np.arange(nx)+.5)*g['dx_mm'],b]
    yp=np.r_[0.,(np.arange(ny)+.5)*g['dy_mm'],h]
    i=np.clip(np.searchsorted(xp,x,side='right')-1,0,nx)
    j=np.clip(np.searchsorted(yp,y,side='right')-1,0,ny)
    fx=(x-xp[i])/(xp[i+1]-xp[i])
    fy=(y-yp[j])/(yp[j+1]-yp[j])
    return float((1-fx)*(1-fy)*padded[j,i]+
       fx*(1-fy)*padded[j,i+1]+(1-fx)*fy*padded[j+1,i]+
       fx*fy*padded[j+1,i+1])
