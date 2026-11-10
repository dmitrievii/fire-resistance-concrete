"""SP-R.2 — independent SP 2.02.05-2026 §8.2.23 transient heat solver.

Only *SP* concrete thermophysical laws are used:
    СП 2.02.05-2026 Appendix K, K.1.1–K.1.2, Table K.1:
      lambda(T) = A + B*T                 [W/(m K)]
      C(T) = D + E*T                     [kJ/(kg K)]
      a_red(T) = 3.6*lambda(T) /
                 (rho_dry * (C(T) + 0.05*Wc))  [m²/h]
    The additive 0.05*Wc term is reproduced from Eq K.1 as an
    *explicit effective heat-capacity approximation* for moisture Wc [%].
    No independent moisture movement or evaporation-front PDE is inferred.

Mathematics: nonlinear implicit cell-centred finite volumes, harmonic
interface conductivity, exact analytic enthalpy integral, locally
balanced convective/radiative surface temperature, conservative fluxes.
Source temperature curve: SP 2026 Eq (3), four optional exposed faces.

WARNING: SP §8.2.23 does not specify a unique external convection /
emissivity pair. The optional h=25 W/m²K and eps=0.7 comparison case is
the EXPLICIT external TKP Annex A boundary assumption, NOT an SP value.
This code supplies SP thermal MATERIAL LAWS but is not validated for
a legal whole-member R(t) on its own. Validate boundaries and reproduce
independent Annex Zh experiments before certification.

The simplified temperature formulas of Annex K and the strength
isotherm method are NOT used to calculate the temperature field.
"""
from __future__ import annotations

import math
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve

VERSION="SP-R2-2026-2D-enthalpy-FVM-v1"
SOURCE="СП 2.02.05-2026 §8.2.23, приложение К.1.1–К.1.2, таблица К.1"
SP_FIRE="СП 2.02.05-2026, формула (3)"
COMPARISON_BOUNDARY="ТКП EN 1992-1-2:2009, приложение А; explicit comparison assumption"
FACES=("left","right","bottom","top")
SIGMA=5.670374419e-8
T_LOW=20.
T_HIGH=1200.
# (A, B, D, E, reference moisture Wc as printed in K.1)
SP_K1={
    "siliceous":(1.20,-.00035,.71,.00083,2.5),
    "calcareous":(1.14,-.00055,.71,.00083,3.0),
}


class SPHeatError(ValueError):
    """SP material, boundary, nonlinear convergence or conservation error."""


def _number(value,name,*,minv=None,maxv=None):
    if isinstance(value,bool):
        raise SPHeatError(name+": finite number required")
    try: result=float(value)
    except (ValueError,TypeError) as exc:
        raise SPHeatError(name+": finite number required") from exc
    if not math.isfinite(result) or (minv is not None and result<minv) or (
        maxv is not None and result>maxv):
        raise SPHeatError(name+": outside declared source domain")
    return result


def _family(name):
    if name not in SP_K1:
        raise SPHeatError("SP Table K.1 only supports heavy siliceous/calcareous in this branch")
    return SP_K1[name]


def _temperature(theta):
    return _number(theta,"concrete temperature",minv=T_LOW,maxv=T_HIGH)


def sp_conductivity(theta_C,*,aggregate):
    """SP Appendix K Table K.1 conductivity, W/(m K)."""
    t=_temperature(theta_C)
    A,B,_,_,_=_family(aggregate)
    value=A+B*t
    if value<=0:
        raise SPHeatError("SP concrete conductivity nonpositive")
    return value


def sp_specific_heat(theta_C,*,aggregate,moisture_mass_pct):
    """SP K.1 C(T) + 0.05 Wc, converted from kJ/kg K to J/kg K."""
    t=_temperature(theta_C)
    _number(moisture_mass_pct,"mass moisture percentage",minv=0.,maxv=20.)
    _,_,D,E,_=_family(aggregate)
    return 1000.*(D+E*t+0.05*float(moisture_mass_pct))


def sp_nominal_diffusivity(theta_C,*,aggregate,rho_dry_kg_m3,
                           moisture_mass_pct):
    """Exact dimensional reproduction of K.1, in m²/h."""
    t=_temperature(theta_C)
    rho=_number(rho_dry_kg_m3,"rho_dry",minv=500.,maxv=3500.)
    lam=sp_conductivity(t,aggregate=aggregate)
    cp=sp_specific_heat(t,aggregate=aggregate,
                        moisture_mass_pct=moisture_mass_pct)
    return 3600.*lam/(rho*cp)


def _vol_enthalpy(temperature,rho,aggregate,moisture):
    """Analytic H(T) [J/m3], H(20°C)=0; no numerical table integration."""
    T=np.asarray(temperature,dtype=float)
    if not np.all(np.isfinite(T)) or np.min(T)<T_LOW-1e-6 or np.max(T)>T_HIGH+1e-6:
        raise SPHeatError("enthalpy requires temperatures in 20..1200°C")
    _,_,D,E,_=_family(aggregate)
    T=np.clip(T,T_LOW,T_HIGH)
    return rho*1000.*((D+0.05*moisture)*(T-T_LOW)+
                     0.5*E*(T*T-T_LOW*T_LOW))


def _vol_heat_capacity(temperature,rho,aggregate,moisture):
    T=np.asarray(temperature,dtype=float)
    if not np.all(np.isfinite(T)) or np.min(T)<T_LOW-1e-6 or np.max(T)>T_HIGH+1e-6:
        raise SPHeatError("heat-capacity temperature outside source domain")
    _,_,D,E,_=_family(aggregate)
    return rho*1000.*(D+E*np.clip(T,T_LOW,T_HIGH)+0.05*moisture)


def _conductivity_array(T,aggregate):
    arr=np.asarray(T,dtype=float)
    if not np.all(np.isfinite(arr)) or np.min(arr)<T_LOW-1e-6 or np.max(arr)>T_HIGH+1e-6:
        raise SPHeatError("conductivity field outside source temperature domain")
    A,B,_,_,_=_family(aggregate)
    values=A+B*np.clip(arr,T_LOW,T_HIGH)
    if np.min(values)<=0.:
        raise SPHeatError("nonpositive conductivity")
    return values


def standard_fire_sp(t_minutes):
    """SP 2.02.05-2026 Eq (3), °C."""
    t=_number(t_minutes,"standard fire minutes",minv=0.)
    return 20.+345.*math.log10(8.*t+1.)


def reference_sp2026_boundary(*,moisture_mass_pct,
                               convection_W_m2_K=25.,
                               surface_emissivity=.7,
                               convection_source=COMPARISON_BOUNDARY):
    """Explicit comparison choice; h and eps are NOT values from §8.2.23."""
    w=_number(moisture_mass_pct,"moisture",minv=0.,maxv=20.)
    h=_number(convection_W_m2_K,"convection",minv=0.,maxv=200.)
    eps=_number(surface_emissivity,"emissivity",minv=0.,maxv=1.)
    if not isinstance(convection_source,str) or not convection_source.strip():
        raise SPHeatError("actual boundary coefficient source must be declared")
    return {
        "fire_curve":"sp2026_standard_formula_3",
        "fire_curve_source":SP_FIRE,
        "convection_W_m2_K":h,
        "surface_emissivity":eps,
        "gas_equals_radiation_temperature":True,
        "environment_source":convection_source,
        "moisture_mass_pct":w,
        "moisture_source":"explicit_user_mass_percent_not_RH",
        "unexposed_faces":"adiabatic_assumption"}


def _check_boundary(b):
    if not isinstance(b,dict) or b.get("fire_curve")!="sp2026_standard_formula_3":
        raise SPHeatError("SP standard-fire boundary must be explicit")
    if b.get("gas_equals_radiation_temperature") is not True:
        raise SPHeatError("gas and radiation temperatures not consistently declared")
    if b.get("unexposed_faces")!="adiabatic_assumption":
        raise SPHeatError("unexposed boundary unknown")
    if not b.get("environment_source") or not b.get("moisture_source"):
        raise SPHeatError("boundary and mass moisture sources must be declared")
    h=_number(b.get("convection_W_m2_K"),"convection",minv=0.,maxv=200.)
    eps=_number(b.get("surface_emissivity"),"emissivity",minv=0.,maxv=1.)
    w=_number(b.get("moisture_mass_pct"),"moisture",minv=0.,maxv=20.)
    return h,eps,w


def _boundary_flux(Tcell,k,dhalf,Tgas,hc,emissivity):
    """Local nonlinear heat-flux balance; secant radiation conductance."""
    cond=k/dhalf
    surf=Tcell
    for _ in range(18):
        gk=Tgas+273.15
        sk=surf+273.15
        hr=emissivity*SIGMA*(gk+sk)*(gk*gk+sk*sk)
        h=hc+hr
        updated=(cond*Tcell+h*Tgas)/(cond+h)
        if abs(updated-surf)<1e-11:
            surf=updated
            break
        surf=updated
    effective=cond*h/(cond+h)
    return effective,float(surf),effective*(Tgas-Tcell)


def _step(Told,*,time_step_s,dx,dy,rho,aggregate,moisture,
          hc,emissivity,Tgas,exposed,max_picard=70,tol=2e-4):
    ny,nx=Told.shape
    area=dx*dy
    eold=_vol_enthalpy(Told,rho,aggregate,moisture)
    guess=Told.copy()
    it_used=0
    for it in range(max_picard):
        k=_conductivity_array(guess,aggregate)
        enew=_vol_enthalpy(guess,rho,aggregate,moisture)
        diff=guess-Told
        cap=np.divide(enew-eold,diff,
            out=_vol_heat_capacity(guess,rho,aggregate,moisture),
            where=np.abs(diff)>1e-8)
        if np.any(cap<=0) or not np.all(np.isfinite(cap)):
            raise SPHeatError("nonpositive enthalpy secant capacity")
        diag=(cap*area/time_step_s).ravel().copy()
        rhs=(cap*area/time_step_s*Told).ravel().copy()
        rows=[];cols=[];values=[]
        for y in range(ny):
            for x in range(nx):
                i=y*nx+x
                ki=k[y,x]
                for xx,yy,length,distance in (
                    (x+1,y,dy,dx),(x,y+1,dx,dy)):
                    if xx>=nx or yy>=ny: continue
                    j=yy*nx+xx
                    kj=k[yy,xx]
                    g=2.*ki*kj/(ki+kj)*length/distance
                    diag[i]+=g;diag[j]+=g
                    rows.extend((i,j));cols.extend((j,i))
                    values.extend((-g,-g))
                for side,is_boundary,dhalf,length in (
                    ("left",x==0,dx/2,dy),
                    ("right",x==nx-1,dx/2,dy),
                    ("bottom",y==0,dy/2,dx),
                    ("top",y==ny-1,dy/2,dx)):
                    if is_boundary and side in exposed:
                        g,_,_=_boundary_flux(float(guess[y,x]),
                            float(ki),dhalf,Tgas,hc,emissivity)
                        g*=length
                        diag[i]+=g
                        rhs[i]+=g*Tgas
        indices_row=np.r_[np.arange(nx*ny),np.asarray(rows,dtype=int)]
        indices_col=np.r_[np.arange(nx*ny),np.asarray(cols,dtype=int)]
        coefs=np.r_[diag,np.asarray(values,dtype=float)]
        mat=coo_matrix((coefs,(indices_row,indices_col)),
                       shape=(nx*ny,nx*ny)).tocsr()
        result=np.asarray(spsolve(mat,rhs),dtype=float).reshape(ny,nx)
        if not np.all(np.isfinite(result)):
            raise SPHeatError("nonlinear SP FVM solve is nonfinite")
        if np.min(result)<T_LOW-1e-6 or np.max(result)>min(T_HIGH,Tgas)+1e-5:
            raise SPHeatError("SP FVM violates heat equation temperature bounds")
        result=np.maximum(result,T_LOW)
        delta=float(np.max(np.abs(result-guess)))
        guess=result
        it_used=it+1
        if delta<tol:
            break
    else:
        raise SPHeatError("SP FVM nonlinear Picard iteration did not converge")
    q=0.
    surfaces={face:[] for face in FACES}
    kval=_conductivity_array(guess,aggregate)
    for y in range(ny):
        for x in range(nx):
            for side,is_boundary,dhalf,length in (
                ("left",x==0,dx/2,dy),
                ("right",x==nx-1,dx/2,dy),
                ("bottom",y==0,dy/2,dx),
                ("top",y==ny-1,dy/2,dx)):
                if not is_boundary: continue
                if side in exposed:
                    _,Ts,local=_boundary_flux(float(guess[y,x]),
                            float(kval[y,x]),dhalf,Tgas,hc,emissivity)
                    q+=local*length
                else:
                    Ts=float(guess[y,x])
                surfaces[side].append(float(Ts))
    gain=q*time_step_s
    stored=float(np.sum((_vol_enthalpy(guess,rho,aggregate,moisture)-eold)*area))
    err=abs(gain-stored)/max(1.,abs(gain),abs(stored))
    if err>3e-4:
        raise SPHeatError(
            f"SP FVM energy residual {err:.3e} >3e-4; not accepted")
    return guess,{
        "picard_iterations":it_used,
        "max_delta_C":delta,
        "boundary_heat_J_per_m":gain,
        "enthalpy_change_J_per_m":stored,
        "relative_energy_residual":err,
        "surface_temperature_C":surfaces}


def _snapshot(T,surfaces,time):
    return {
        "time_minutes":float(time),
        "grid_temperature_C":T.tolist(),
        "surface_temperature_C":{name:list(v) for name,v in surfaces.items()},
        "cell_min_C":float(np.min(T)),
        "cell_max_C":float(np.max(T)),
        "boundary_max_C":max(float(np.max(T)),*[
            max(v) for v in surfaces.values() if v])}


def solve_sp2026_2d_heat(column,*,boundary,cell_count_x=12,
                         cell_count_y=12,max_step_minutes=3.,
                         sample_times_minutes=None,
                         max_picard_iterations=70):
    """SP-specific thermal source. Source/meta flags never assert normative R."""
    if not isinstance(column,dict):
        raise SPHeatError("physical column required")
    for n in (cell_count_x,cell_count_y):
        if type(n) is not int or not 4<=n<=80:
            raise SPHeatError("SP FVM grid must have 4..80 cells per axis")
    b=_number(column.get("b_mm"),"b_mm",minv=10.,maxv=2000.)/1000.
    h=_number(column.get("h_mm"),"h_mm",minv=10.,maxv=2000.)/1000.
    duration=_number(column.get("fire_minutes"),"duration",minv=.1,maxv=480.)
    dt=_number(max_step_minutes,"time step minutes",minv=.25,maxv=30.)
    if type(max_picard_iterations) is not int or not 3<=max_picard_iterations<=200:
        raise SPHeatError("invalid Picard iteration count")
    spec=column.get("thermal_spec") or {}
    aggregate=spec.get("concrete_family")
    _family(aggregate)
    density=_number(spec.get("dry_density_kg_m3"),"dry density",
                    minv=500.,maxv=3500.)
    faces=spec.get("exposed_faces")
    if not isinstance(faces,(list,tuple)) or len(faces)!=len(set(faces)) or (
        not set(faces).issubset(set(FACES))):
        raise SPHeatError("unique exposed faces required")
    hc,emissivity,moisture=_check_boundary(boundary)
    desired=sample_times_minutes
    if desired is None: desired=[duration]
    if not isinstance(desired,(tuple,list)) or not desired:
        raise SPHeatError("at least one explicit sample time required")
    wanted=sorted(set(_number(t,"sample time",minv=.000001,maxv=duration)
                      for t in desired))
    if wanted[-1]<duration-1e-9:
        wanted.append(duration)
    if len(wanted)>240:
        raise SPHeatError("too many source snapshots")
    dx=b/cell_count_x;dy=h/cell_count_y
    T=np.full((cell_count_y,cell_count_x),20.,dtype=float)
    surfaces={name:[20.]*(cell_count_y if name in ("left","right")
                          else cell_count_x) for name in FACES}
    time=0.;snapshots=[];step_log=[]
    total_energy=0.;worst_step_err=0.
    for target in wanted:
        while time<target-1e-9:
            step=min(dt,target-time)
            while True:
                try:
                    updated,evidence=_step(T,time_step_s=step*60.,
                        dx=dx,dy=dy,rho=density,aggregate=aggregate,
                        moisture=moisture,hc=hc,emissivity=emissivity,
                        Tgas=standard_fire_sp(time+step),exposed=set(faces),
                        max_picard=max_picard_iterations)
                    break
                except SPHeatError as exc:
                    if step<=.251:
                        raise SPHeatError(
                            f"SP thermal failed at t={time:g} min: {exc}") from exc
                    step*=.5
            T=updated
            time+=step
            surfaces=evidence["surface_temperature_C"]
            total_energy+=evidence["boundary_heat_J_per_m"]
            worst_step_err=max(worst_step_err,evidence["relative_energy_residual"])
            step_log.append({
                "time_minutes":round(time,10),
                "dt_minutes":step,
                "gas_C":standard_fire_sp(time),
                "relative_energy_residual":evidence["relative_energy_residual"],
                "picard_iterations":evidence["picard_iterations"]})
        snapshots.append(_snapshot(T,surfaces,target))
    stored=float(np.sum(_vol_enthalpy(T,density,aggregate,moisture)*dx*dy))
    err=abs(stored-total_energy)/max(1.,abs(stored),abs(total_energy))
    if err>3e-4:
        raise SPHeatError("SP cumulative energy balance did not close")
    return {
        "version":VERSION,
        "status":"evaluated_sp2026_thermal_diagnostic",
        "thermal_method":"SP2026_8.2.23_FVM",
        "governing_source":SOURCE,
        "fire_curve_source":SP_FIRE,
        "external_boundary_source":boundary["environment_source"],
        "time_minutes":duration,
        "fire_minutes":duration,
        "exposed_faces":list(faces),
        "column_id":column.get("id"),
        "material_family":aggregate,
        "dry_density_kg_m3":density,
        "moisture_mass_pct":moisture,
        "moisture_provenance":boundary["moisture_source"],
        "moisture_model":"SP_K1_EFFECTIVE_HEAT_CAPACITY_0.05W_NO_EXPLICIT_MASS_TRANSPORT",
        "boundary_parameters":dict(boundary),
        "grid":{"nx":cell_count_x,"ny":cell_count_y,
                "width_mm":b*1000.,"height_mm":h*1000.,
                "dx_mm":dx*1000.,"dy_mm":dy*1000.},
        "initial_temperature_C":20.,
        "snapshots":snapshots,
        "step_log":step_log,
        "energy_balance":{
            "enthalpy_change_J_per_m":stored,
            "integrated_boundary_heat_J_per_m":total_energy,
            "relative_cumulative_residual":err,
            "worst_step_relative_residual":worst_step_err},
        "source_property_coefficients":{
            "A":SP_K1[aggregate][0],"B":SP_K1[aggregate][1],
            "D":SP_K1[aggregate][2],"E":SP_K1[aggregate][3],
            "table_K1_reference_moisture_mass_pct":SP_K1[aggregate][4]},
        "model_limitations":[
            "SP K.1 effective moisture heat capacity is not a coupled heat-mass PDE",
            "SP §8.2.23 does not define h=25 W/m2K / eps=0.7; boundary source requires qualification",
            "no volumetric phase change, explicit moisture transport, shrinkage cracking or spalling",
            "steel does not perturb concrete thermal field",
            "no longitudinal heat transfer: each section requires separately supported exposure",
            "mesh/time independence and SP Appendix Zh comparisons require checking"],
        "source_transport_laws_independent_of_TKP":True,
        "mesh_time_convergence_qualified":False,
        "external_boundary_normative_qualified":False,
        "full_member_R_t_qualified":False,
        "R_t_minutes":None,
        "regulatory_result":"NOT_ESTABLISHED",
        "normative_claim":False}


def select_sp2026_snapshot(result,time_minutes):
    if not isinstance(result,dict) or result.get("thermal_method")!="SP2026_8.2.23_FVM":
        raise SPHeatError("SP 2026 solved thermal field required")
    t=_number(time_minutes,"time minutes",minv=0.)
    snap=next((x for x in result["snapshots"]
               if abs(float(x["time_minutes"])-t)<1e-8),None)
    if snap is None:
        raise SPHeatError("requested SP temperature time not stored; no synthetic interpolation")
    return {**result,"fire_minutes":t,"snapshot":snap}


def sample_sp2026_temperature(field,x_mm,y_mm):
    """Bilinear interpolation with actual solved boundary-face temperatures."""
    if field.get("thermal_method")!="SP2026_8.2.23_FVM" or not isinstance(
        field.get("snapshot"),dict):
        raise SPHeatError("time-matched SP thermal snapshot required")
    grid=field["grid"];snap=field["snapshot"]
    width=float(grid["width_mm"]);height=float(grid["height_mm"])
    x=_number(x_mm,"sample x",minv=0.,maxv=width)
    y=_number(y_mm,"sample y",minv=0.,maxv=height)
    data=np.asarray(snap["grid_temperature_C"],dtype=float)
    ny,nx=data.shape
    if nx!=grid["nx"] or ny!=grid["ny"]:
        raise SPHeatError("SP grid/sample shape mismatch")
    faces=snap["surface_temperature_C"]
    extended=np.empty((ny+2,nx+2),dtype=float)
    extended[1:-1,1:-1]=data
    extended[1:-1,0]=faces["left"]
    extended[1:-1,-1]=faces["right"]
    extended[0,1:-1]=faces["bottom"]
    extended[-1,1:-1]=faces["top"]
    for yside,xside,neighbors in (
        (0,0,((1,0),(0,1))),
        (0,-1,((1,-1),(0,-2))),
        (-1,0,((-2,0),(-1,1))),
        (-1,-1,((-2,-1),(-1,-2)))):
        extended[yside,xside]=.5*sum(extended[a,b] for a,b in neighbors)
    xp=np.r_[0.,(np.arange(nx)+.5)*float(grid["dx_mm"]),width]
    yp=np.r_[0.,(np.arange(ny)+.5)*float(grid["dy_mm"]),height]
    ix=max(0,min(nx,int(np.searchsorted(xp,x,side="right")-1)))
    iy=max(0,min(ny,int(np.searchsorted(yp,y,side="right")-1)))
    x0,x1=xp[ix],xp[ix+1];y0,y1=yp[iy],yp[iy+1]
    fx=(x-x0)/(x1-x0);fy=(y-y0)/(y1-y0)
    return float(
        (1-fx)*(1-fy)*extended[iy,ix]+
        fx*(1-fy)*extended[iy,ix+1]+
        (1-fx)*fy*extended[iy+1,ix]+
        fx*fy*extended[iy+1,ix+1])
