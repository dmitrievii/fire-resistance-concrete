"""SP-R11A mixed history-dependent biaxial beam-column, research only.

Small rotations, Euler-Bernoulli, constant dead compressive N, released
axial expansion. Independent axial strain at each longitudinal Gauss
station is statically condensed by the mixed equilibrium system. No
axial restraint, torsion, large rotations, shear, rupture, or R claim.
All trial states derive from immutable previously committed histories.
"""
from dataclasses import dataclass
import math
import numpy as np
from rc_fire.member.coupled import _shape,_dofs,_GQ,_GW,_boundary_matrix
from rc_fire.member.sp2026_member import _validate_spec,_snapshot_checked
from rc_fire.mechanics import sp2026_r10a_history_section as sec
from rc_fire.mechanics import sp2026_r10b_steel_history as steel
from rc_fire.mechanics import sp2026_r9g_hot_domain as hot

VERSION="SP-R11A-mixed-history-member-v1"

@dataclass(frozen=True)
class Station:
    z:float
    weight:float
    B:object # maps dimensionless mixed unknowns to normalized sectional strains

class Beam:
    """All unknowns dimensionless; transverse translations scaled by L.
    Work-conjugate residuals and tangent entries in kNm. Axial strain at
    each Gauss station is an independent local DOF, with residual w*(Nint-N).
    """
    def __init__(self,z,N,left,right,distributed,nodal,imperfection,shape):
        self.z=np.asarray(z,dtype=float);n=len(z);self.n=n;self.nd=4*n
        self.L=float(z[-1]);self.N=float(N);self.shape=np.asarray(shape,dtype=float)
        self.scale=np.ones(self.nd);self.scale[::2]=self.L
        self.total=self.nd+3*(n-1)
        self.stations=[];self.G=np.zeros((self.nd,self.nd));self.F=np.asarray(nodal,dtype=float)*self.scale
        self.initial=np.asarray(imperfection,dtype=float)/self.scale
        fixed,springs=_boundary_matrix(left,right,n)
        if any(abs(self.initial[k])>1e-10 for k in fixed):
            raise ValueError("imperfection incompatible with supports")
        self.fixed={k:v/self.scale[k] for k,v in fixed.items()}
        self.free=np.asarray([k for k in range(self.total) if k not in fixed],dtype=int)
        self.springs=springs*self.scale**2
        for i in range(n-1):
            le=z[i+1]-z[i]
            idx=np.r_[_dofs(i,0,n),_dofs(i+1,0,n),_dofs(i,1,n),_dofs(i+1,1,n)]
            for j,(t,w) in enumerate(zip(_GQ,_GW)):
                H,Hp,Hpp=_shape(t,le);weight=le*w
                B=np.zeros((3,self.total));B[0,self.nd+len(self.stations)]=1.
                B[1,idx[:4]]=-Hpp*self.scale[idx[:4]]*shape[0]
                B[2,idx[4:]]=-Hpp*self.scale[idx[4:]]*shape[1]
                P=np.zeros((2,8));P[0,:4]=Hp*self.scale[idx[:4]];P[1,4:]=Hp*self.scale[idx[4:]]
                Hm=np.zeros((2,8));Hm[0,:4]=H*self.scale[idx[:4]];Hm[1,4:]=H*self.scale[idx[4:]]
                self.G[np.ix_(idx,idx)]+=weight*P.T@P
                self.F[idx]+=weight*Hm.T@((1-t)*np.asarray(distributed[i])+t*np.asarray(distributed[i+1]))
                self.stations.append(Station(float(z[i]+t*le),weight,B))
        self.stations=tuple(self.stations)
    def zero(self):
        x=np.zeros(self.total)
        for k,v in self.fixed.items():x[k]=v
        return x
    def assemble(self,x,law):
        r=np.zeros(self.total);K=np.zeros((self.total,self.total));records=[]
        for i,g in enumerate(self.stations):
            F,J,record=law(i,g.B@x)
            F=np.asarray(F);J=np.asarray(J)
            if F.shape!=(3,) or J.shape!=(3,3) or not np.all(np.isfinite(F)) or not np.all(np.isfinite(J)) or not np.allclose(J,J.T,rtol=1e-9,atol=1e-7):
                raise ValueError("invalid section force/tangent")
            target=np.array([self.N,0.,0.])
            r+=g.weight*g.B.T@(F-target)
            K+=g.weight*g.B.T@J@g.B
            records.append((F,J,record))
        r[:self.nd]+=-self.N*self.G@(x[:self.nd]+self.initial)+self.springs*x[:self.nd]-self.F
        K[:self.nd,:self.nd]+=-self.N*self.G+np.diag(self.springs)
        return r,K,records
    def condensed(self,K):
        lat=np.asarray([k for k in range(self.nd) if k not in self.fixed],dtype=int)
        ax=np.arange(self.nd,self.total)
        A=K[np.ix_(ax,ax)]
        if np.linalg.eigvalsh(A)[0]<=0:raise ValueError("nonpositive local axial tangent")
        C=K[np.ix_(lat,ax)]
        T=K[np.ix_(lat,lat)]-C@np.linalg.solve(A,C.T)
        return (T+T.T)/2
    def solve(self,old,law,*,max_iterations=30,tolerance=1e-6):
        x=np.asarray(old,dtype=float).copy();cached=None;calls=0
        if x.shape!=(self.total,) or not np.all(np.isfinite(x)) or any(abs(x[k]-v)>1e-12 for k,v in self.fixed.items()):
            raise ValueError("invalid committed member coordinates")
        for it in range(1,max_iterations+1):
            try:
                if cached is None:out=self.assemble(x,law);calls+=1
                else:out=cached;cached=None
            except (ValueError,ArithmeticError,np.linalg.LinAlgError) as e:
                return None,{"status":"UNRESOLVED_MATERIAL_TRIAL","reason":str(e)}
            r,K,recs=out;err=float(np.max(np.abs(r[self.free])))
            axial=max(abs(float(F[0])-self.N) for F,J,R in recs)
            if err<=tolerance and axial<=tolerance:
                try:T=self.condensed(K);eig=np.linalg.eigvalsh(T)
                except (ValueError,np.linalg.LinAlgError) as e:
                    return None,{"status":"UNRESOLVED_AXIAL_CONDENSATION","reason":str(e)}
                if eig[0]<=max(1e-9,1e-12*max(1.,eig[-1])):
                    return None,{"status":"UNRESOLVED_NONPOSITIVE_GLOBAL_ALGORITHMIC_TANGENT",
                                 "eigen_min_scaled_kNm":float(eig[0])}
                return (x,recs,K),{"status":"EQUILIBRATED_RESEARCH_MEMBER","iterations":it,
                    "assembly_calls":calls,"scaled_free_residual_kNm":err,"max_axial_residual_kN":axial,
                    "algorithmic_global_eigen_min_scaled_kNm":float(eig[0]),
                    "algorithmic_global_eigen_max_scaled_kNm":float(eig[-1]),
                    "support_reactions_scaled_kNm":{str(k):float(r[k]) for k in self.fixed}}
            try:step=np.linalg.solve(K[np.ix_(self.free,self.free)],-r[self.free])
            except np.linalg.LinAlgError:return None,{"status":"UNRESOLVED_SINGULAR_GLOBAL_TANGENT"}
            if not np.all(np.isfinite(step)):return None,{"status":"UNRESOLVED_NONFINITE_STEP"}
            for j in range(14):
                y=x.copy();y[self.free]+=step*2.**(-j)
                try:trial=self.assemble(y,law);calls+=1
                except (ValueError,ArithmeticError,np.linalg.LinAlgError):continue
                if np.max(np.abs(trial[0][self.free]))<err:
                    x=y;cached=trial;break
            else:return None,{"status":"UNRESOLVED_GLOBAL_LINE_SEARCH","scaled_residual_kNm":err}
        return None,{"status":"UNRESOLVED_GLOBAL_ITERATION_LIMIT"}

@dataclass(frozen=True)
class MemberState:
    x:tuple
    sections:tuple
    time_s:float
    thermal_minutes:float
    contract:tuple

def contract(beam):
    return (tuple(beam.z),beam.N,tuple(beam.shape),tuple(beam.initial),tuple(beam.F),
            tuple(sorted(beam.fixed.items())),tuple(beam.springs))

def make_beam(column,spec):
    z,N,left,right,q,f,initial=_validate_spec(column,spec)
    if spec.get("longitudinal_thermal_mode")!="explicit_uniform_full_length" or spec.get("uniform_exposure_confirmed") is not True:
        raise ValueError("R11A requires explicit uniform longitudinal heating")
    return Beam(z,N,left,right,q,f,initial,(float(column["h_mm"])/2000,float(column["b_mm"])/2000))

def initial(column,spec,field,*,grid=8,mode=hot.MODIFIED_AT,quadrature=None):
    beam=make_beam(column,spec);_snapshot_checked(field,0.,column)
    # Independent immutable section histories. Identical initial values
    # are not a shared mutable constitutive state.
    states=tuple(sec.make_initial(column,field,grid=grid,mode=mode,length_mm=50.,
                    Gwork_N_mm=5.,yield_fraction=.4,strength_basis="SP5_ACCIDENTAL_FCD",
                    steel_mode=steel.PLASTIC,steel_strain_limit=.02,quadrature=quadrature)
                 for _ in beam.stations)
    return MemberState(tuple(beam.zero()),states,0.,0.,contract(beam))

def advance(s,column,spec,field,*,max_iterations=30):
    beam=make_beam(column,spec)
    if contract(beam)!=s.contract:raise ValueError("member contract changed")
    minute=float(field["snapshot"]["time_minutes"]);_snapshot_checked(field,minute,column)
    t=1.+60*minute
    if t<=s.time_s or minute<s.thermal_minutes or (s.time_s!=0 and minute<=s.thermal_minutes):
        raise ValueError("strict member time history required")
    # Same temperature and geometry at all sections by explicit contract.
    # Cache only prepared immutable inventory, never history.
    p,A,C,B,E,fy=sec._prepare(s.sections[0],column,field)
    if any(v.geometry!=s.sections[0].geometry or v.steel_temperatures!=s.sections[0].steel_temperatures for v in s.sections):
        raise ValueError("station inventory mismatch")
    def law(i,q):
        r=sec._trial(s.sections[i],p,A,C,B,E,fy,t,q)
        return r[0],r[1],(tuple(q),r)
    solved,report=beam.solve(s.x,law,max_iterations=max_iterations)
    if solved is None:return s,report
    x,recs,K=solved;new=[];stations=[];Ku=np.zeros_like(K)
    for i,(F,J,(q,r)) in enumerate(recs):
        _,_,cs,rows,sc,ss,Fc,Fs,es,st,ratios=r
        old=s.sections[i];g=beam.stations[i]
        if not all(steel.admitted(a,old.steel_mode,float(f),diagnostic_strain_limit=old.steel_strain_limit) for a,f in zip(st,fy)):
            return s,{"status":"UNRESOLVED_STEEL_HISTORY_DOMAIN","station":i}
        probes=[]
        try:
            for a,T,e in zip(old.probes,p.sp_boundary_temperature,sec._shape(p.sp_boundary_u,p.sp_boundary_v)@q):
                n,_=hot.trial_step(a,time_s=t,temperature_C=float(T),total_compression=float(e));probes.append(n)
        except (ValueError,ArithmeticError) as e:
            return s,{"status":"UNRESOLVED_BOUNDARY_HISTORY","station":i,"reason":str(e)}
        new.append(sec.SectionState(old.geometry,old.grid,old.thermal_method,t,minute,q,
              tuple(cs),tuple(probes),tuple(p.theta_s),st,old.steel_mode,old.steel_strain_limit,old.quadrature))
        Eu=np.asarray([0. if a.thermal_cutoff or a.active.damage==1. or sig<=0 else
             (1-a.active.damage)*sec.material._material(a.active.parameters,a.active.maximum_temperature_C)[0] for a,sig in zip(cs,sc)])
        Ju=1000*((C.T*(A*Eu))@C+(B.T*(p.bar_area*E))@B)
        Ku+=g.weight*g.B.T@Ju@g.B
        scale=np.r_[1.,beam.shape]
        stations.append({"z_m":g.z,"q":list(q),"actions_kN_kNm":(F*scale).tolist(),
            "concrete_actions_kN_kNm":(Fc*scale).tolist(),"steel_actions_kN_kNm":(Fs*scale).tolist(),
            "max_concrete_damage":max(a.active.damage for a in cs),
            "max_boundary_damage":max(a.active.damage for a in probes),
            "max_transient_strain":max(a.active.transient_compression for a in cs),
            "max_steel_plastic_strain":max(a.accumulated_plastic_strain for a in st),
            "steel_yield_ratio":float(np.max(np.abs(ss)/fy))})
    Ku[:beam.nd,:beam.nd]+=-beam.N*beam.G+np.diag(beam.springs)
    try:eig_u=float(np.linalg.eigvalsh(beam.condensed(Ku))[0])
    except (ValueError,np.linalg.LinAlgError):eig_u=None
    physical=(x[:beam.nd]+beam.initial)*beam.scale
    n=beam.n
    # Check longitudinal slopes at Gauss stations and element endpoints.
    slopes=[]
    for i in range(n-1):
        for u in (0.,*_GQ,1.):
            _,Hp,_=_shape(u,beam.z[i+1]-beam.z[i])
            slopes.extend(float(Hp@physical[np.r_[_dofs(i,a,n),_dofs(i+1,a,n)]]) for a in (0,1))
    maxs=max(abs(v) for v in slopes)
    if maxs>.1:return s,{"status":"UNRESOLVED_SMALL_ROTATION_DOMAIN","max_sampled_slope":maxs}
    newstate=MemberState(tuple(x),tuple(new),t,minute,s.contract)
    return newstate,{**report,"time_minutes":minute,"station_count":len(stations),"stations":stations,
        "total_w_x_m":physical[:2*n:2].tolist(),"total_w_y_m":physical[2*n::2].tolist(),
        "max_sampled_slope":maxs,"frozen_unloading_global_eigen_min_scaled_kNm":eig_u,
        "global_physical_failure_proven":False,"normative_claim":False,"actual_U_t":None,"actual_t_R_minutes":None}

def history(column,spec,fields,*,grid=8,quadrature=None):
    s=initial(column,spec,fields[0],grid=grid,quadrature=quadrature);rows=[]
    for f in fields:
        try:n,r=advance(s,column,spec,f)
        except (ValueError,ArithmeticError,np.linalg.LinAlgError) as e:
            n=s;r={"status":"UNRESOLVED_MEMBER_INPUT_OR_DOMAIN","reason":str(e)}
        rows.append({**r,"requested_time_minutes":f["snapshot"]["time_minutes"]})
        if r["status"]!="EQUILIBRATED_RESEARCH_MEMBER":
            return {"status":"UNRESOLVED_HISTORY_STOP","rows":rows,"last_committed_minute":s.thermal_minutes,
                    "actual_t_R_minutes":None,"normative_claim":False}
        s=n
    return {"status":"DIAGNOSTIC_COMPLETE","rows":rows,"last_committed_minute":s.thermal_minutes,
            "actual_t_R_minutes":None,"normative_claim":False}
