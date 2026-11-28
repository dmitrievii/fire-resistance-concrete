"""SP-PROD.1 normative section check, bounded deformation domain.

SP 2.02.05-2026 8.2.16,18-20; SP 5.03.01-2020 6.1.5.4,
6.2.2.13, 8.1.2.1-.4. Compression positive, strain in per mille,
coordinates normalized by half dimensions, conjugate moments in kN.
The convex potential is ONLY a numerical device for the monotone
section-verification diagram. No damage, LITS, rupture, fitted parameters
or other constitutive law. The plateau extension used for trial iterates
never admits a strain outside the prescribed section domain.
"""
import math
import numpy as np
from scipy.optimize import linprog,least_squares,minimize

PASS="WITHIN_SECTION_DOMAIN"
FAIL="OUTSIDE_SECTION_ACTION_DOMAIN"
UNKNOWN="UNRESOLVED_SECTION_CHECK"

class Section:
    def __init__(self,C,A,fc,th,B,As,fy,E,ths,D,d,eps2,epsu,n):
        self.C,self.A,self.fc,self.th,self.B,self.As,self.fy,self.E,self.ths,self.D,self.d=(
            np.asarray(v,dtype=float) for v in (C,A,fc,th,B,As,fy,E,ths,D,d))
        self.eps2=float(eps2);self.epsu=float(epsu);self.n=float(n)
        if not (0<self.eps2<=self.epsu and self.n>1 and
                np.all(self.A>=0) and np.all(self.As>0) and np.all(self.fc>=0) and
                np.all(self.fy>0) and np.all(self.E>0)):
            raise ValueError("invalid bounded section data")
        for a in (self.C,self.A,self.fc,self.th,self.B,self.As,self.fy,self.E,self.ths,self.D,self.d):
            if not np.all(np.isfinite(a)):raise ValueError("nonfinite section data")
        self.Ac=1000*self.A;self.Ab=1000*self.As
        # F is the gradient of a convex potential (kN × per mille).
        # Global gradient Lipschitz bound from scalar maximum slopes.
        self.L=float(np.sum(self.Ac*self.fc*self.n/self.eps2*np.sum(self.C**2,axis=1))+
                    np.sum(self.Ab*self.E/1000*np.sum(self.B**2,axis=1)))
        if self.L<=0:raise ValueError("zero section stiffness")
        self.bounds=[];self.feasible_seed=None
        p=linprog(np.zeros(3),A_ub=self.D,b_ub=self.d,bounds=[(None,None)]*3,method="highs")
        if not p.success:
            self.domain_status="EMPTY_OR_UNRESOLVED_STRAIN_DOMAIN";return
        self.feasible_seed=p.x;self.domain_status="BOUNDED"
        for e in np.eye(3):
            limits=[]
            for sign in (1.,-1.):
                x=linprog(sign*e,A_ub=self.D,b_ub=self.d,bounds=[(None,None)]*3,method="highs")
                if not x.success:
                    self.domain_status="UNBOUNDED_OR_UNRESOLVED_STRAIN_DOMAIN";return
                limits.append(float(sign*x.fun))
            self.bounds.append((limits[0]-1e-7,limits[1]+1e-7))
    def evaluate(self,q):
        e=self.C@q+self.th;s=self.B@q+self.ths
        r=np.clip(e/self.eps2,0.,1.)
        fc=self.fc*(1-(1-r)**self.n)
        dc=np.where((e>0)&(e<self.eps2),self.fc*self.n/self.eps2*(1-r)**(self.n-1),0.)
        fy=np.clip(self.E*s/1000,-self.fy,self.fy)
        ds=np.where(abs(self.E*s/1000)<self.fy,self.E/1000,0.)
        F=self.C.T@(self.Ac*fc)+self.B.T@(self.Ab*fy)
        J=(self.C.T*(self.Ac*dc))@self.C+(self.B.T*(self.Ab*ds))@self.B
        wc=self.fc*(np.maximum(e,0)-self.eps2/(self.n+1)*(1-(1-r)**(self.n+1)))
        ey=1000*self.fy/self.E;z=np.minimum(abs(s),ey)
        ws=.5*self.E/1000*z*z+self.fy*np.maximum(abs(s)-ey,0)
        W=float(self.Ac@wc+self.Ab@ws)
        return F,J,W,e,s
    def admissible(self,q):
        return bool(np.max(self.D@q-self.d)<=1e-8)
    def check(self,target,seed=None):
        target=np.asarray(target,dtype=float)
        if target.shape!=(3,) or not np.all(np.isfinite(target)):raise ValueError("finite N/M vector")
        if self.domain_status!="BOUNDED":
            return {"status":UNKNOWN,"reason":self.domain_status}
        scale=max(1.,float(np.max(abs(target))))
        tol=max(1e-5,1e-8*scale)
        x0=np.asarray(self.feasible_seed if seed is None else seed,dtype=float)
        def res(q):return (self.evaluate(q)[0]-target)/scale
        def jac(q):return self.evaluate(q)[1]/scale
        def result(q):
            F,J,W,e,s=self.evaluate(q);err=float(np.max(abs(F-target)))
            if self.admissible(q) and err<=tol:
                return {"status":PASS,"q_permille":q.tolist(),"residual_kN":err,
                    "max_concrete_cell_compression_permille":float(max(0.,max(e[self.fc>0],default=0.))),
                    "max_steel_tension_permille":float(max(0.,-min(s))),
                    "max_constraint_excess_permille":float(np.max(self.D@q-self.d))}
            return None
        # A first unconstrained equilibrium attempt is cheap. Its stress
        # extension is merely a numerical device; never classify an
        # out-of-domain root as failure without independent certificate.
        unrestricted=None
        for x in (x0,np.zeros(3)):
            q=least_squares(res,x,jac=jac,ftol=1e-12,gtol=1e-12,xtol=1e-12,max_nfev=100).x
            out=result(q)
            if out:return out
            err=float(np.max(abs(self.evaluate(q)[0]-target)))
            if err<=tol:
                v={"q_permille":q.tolist(),"residual_kN":err,
                   "max_constraint_excess_permille":float(np.max(self.D@q-self.d)),
                   "diagnostic_only":True}
                if unrestricted is None or v["max_constraint_excess_permille"]<unrestricted["max_constraint_excess_permille"]:
                    unrestricted=v
        def objective(q):
            F,J,W,e,s=self.evaluate(q)
            return (W-target@q)/scale,(F-target)/scale
        p=minimize(objective,x0,jac=True,method="SLSQP",bounds=self.bounds,
            constraints=[{"type":"ineq","fun":lambda q:self.d-self.D@q,"jac":lambda q:-self.D}],
            options={"ftol":1e-12,"maxiter":150})
        q=np.asarray(p.x,dtype=float);out=result(q)
        if out:return out
        if not self.admissible(q):
            return {"status":UNKNOWN,"reason":"no admissible numerical candidate"}
        # Independent infeasibility test. If target=F(z) at any admissible
        # z, monotone scalar slopes bounded above imply
        # ||target-F(q)||²/L <= (target-F(q)) dot (z-q).
        # Bound RHS via a nonnegative LP dual and enclosing coordinate box.
        # This excludes ALL roots in the discrete admissible strain domain,
        # not merely the root Newton happened to reach.
        v=target-self.evaluate(q)[0]
        if float(np.max(abs(v)))<=tol:
            return {"status":UNKNOWN,"reason":"near equilibrium but not admitted"}
        p=linprog(-v,A_ub=self.D,b_ub=self.d,bounds=[(None,None)]*3,method="highs")
        if not p.success:return {"status":UNKNOWN,"reason":"support problem unresolved"}
        y=np.maximum(0.,-np.asarray(p.ineqlin.marginals))
        r=v-self.D.T@y
        upper=float(y@self.d-v@q+sum(max(a*l,a*h) for a,(l,h) in zip(r,self.bounds)))
        necessary=float(v@v/self.L)
        margin=necessary-upper
        rounding=1e-7*max(1.,abs(necessary),abs(upper),float(np.linalg.norm(v))*float(np.linalg.norm(q)))
        if margin>rounding:
            return {"status":FAIL,"certificate":"DISCRETE_MONOTONE_SUPPORT_EXCLUSION",
                    "q_permille":q.tolist(),"residual_kN":float(np.max(abs(v))),
                    "necessary_work_kN_permille":necessary,"support_upper_kN_permille":upper,
                    "certificate_margin":margin,"numerical_allowance":rounding,
                    "unrestricted_equilibrium_diagnostic":unrestricted}
        return {"status":UNKNOWN,"reason":"no equilibrium or positive exclusion margin established",
                "residual_kN":float(np.max(abs(v))),"certificate_margin":margin}

def utilization(section,target,*,max_factor=16.,bisections=12):
    """Section proportional check on FIXED second-order action vector.
    Report observed factor bracket, not an asserted global nonlinear peak.
    Applied-load decision is independent of reserve search.
    """
    target=np.asarray(target,dtype=float)
    a=section.check(target)
    out={"applied":a,"factor_interval":None,"U_interval":None,"U":None}
    if a["status"]==UNKNOWN:return out
    if a["status"]==PASS:
        lo=1.;hi=2.;seed=a.get("q_permille")
        while hi<=max_factor:
            b=section.check(hi*target,seed)
            if b["status"]==FAIL:break
            if b["status"]!=PASS:return out
            lo=hi;seed=b.get("q_permille");hi*=2
        else:return out
    else:
        hi=1.;lo=.5;seed=None
        while lo>=1./1024:
            b=section.check(lo*target)
            if b["status"]==PASS:
                seed=b.get("q_permille");break
            if b["status"]!=FAIL:return out
            hi=lo;lo*=.5
        else:return out
    interrupted=False
    for _ in range(bisections):
        mid=(lo+hi)/2;b=section.check(mid*target,seed)
        if b["status"]==PASS:lo=mid;seed=b.get("q_permille")
        elif b["status"]==FAIL:hi=mid
        else:interrupted=True;break
    out.update({"factor_interval":[lo,hi],"U_interval":[1/hi,1/lo],
                "U":1/lo,"U_is_upper_reciprocal_of_observed_bracket":True,
                "refinement_interrupted_by_unknown":interrupted,
                "continuous_maximum_proven":False})
    return out
