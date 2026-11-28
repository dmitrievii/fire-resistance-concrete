"""SP-R10C fixed pilot-informed quadtree, positive net-cell centroid rule.

Geometry is frozen before t=0 mechanical preload. Thermal pilots select
resolution, not material history; no remapping, fitting, or changing grid
during history. Exact circle overlap area and first moments; centroid is
a quadrature representative, not a guarantee of pointwise solid location.
"""
from dataclasses import dataclass
from functools import lru_cache
import math
import numpy as np
from rc_fire.thermal.sp2026_heat import sample_sp2026_temperature
from rc_fire.thermal.sp2026_annex_k_field import ANNEX_K_METHOD,sample_annex_k_temperature

def circle_moments(cx,cy,r,x0,x1,y0,y1):
    """Return area, first moment x*dA, first moment y*dA (SI units)."""
    a=max(x0-cx,-r);b=min(x1-cx,r)
    if a>=b:return 0.,0.,0.
    lo=y0-cy;hi=y1-cy
    cuts=[a,b]
    for v in (lo,hi):
        if abs(v)<=r:
            z=math.sqrt(max(0.,r*r-v*v))
            cuts.extend(x for x in (-z,z) if a<x<b)
    def S(x):return .5*(x*math.sqrt(max(0.,r*r-x*x))+r*r*math.asin(max(-1.,min(1.,x/r))))
    def XS(x):return -max(0.,r*r-x*x)**1.5/3
    def S2(x):return r*r*x-x*x*x/3
    A=X=Y=0.
    cuts=sorted(set(cuts))
    for l,h in zip(cuts,cuts[1:]):
        z=math.sqrt(max(0.,r*r-((l+h)/2)**2))
        if min(hi,z)<=max(lo,-z):continue
        ts=z<hi;bs=-z>lo
        slope=int(ts)+int(bs)
        c=(0. if ts else hi)-(0. if bs else lo)
        A+=slope*(S(h)-S(l))+c*(h-l)
        X+=slope*(XS(h)-XS(l))+c*(h*h-l*l)/2
        Y+=.5*((int(ts)-int(bs))*(S2(h)-S2(l))+
               ((0. if ts else hi*hi)-(0. if bs else lo*lo))*(h-l))
    return A,X+cx*A,Y+cy*A

def bar_signature(p):
    return tuple((str(i),float(x),float(y),float(a)) for i,x,y,a in
                 zip(p.bar_ids,p.bar_x,p.bar_y,p.bar_area))

@dataclass(frozen=True)
class Quadrature:
    width:float
    height:float
    bars:tuple
    method:str
    cells:tuple
    points:tuple # x,y,positive A
    pilot_minutes:tuple
    max_level:int
    delta_C:float
    base_grid:int
    boundary_band_m:float
    unresolved_gradient_cells:int
    def evidence(self):
        return {"cell_count":len(self.cells),"point_count":len(self.points),
                "min_cell_width_mm":1000*min(min(x1-x0,y1-y0) for x0,x1,y0,y1 in self.cells),
                "max_cell_width_mm":1000*max(max(x1-x0,y1-y0) for x0,x1,y0,y1 in self.cells),
                "pilot_minutes":list(self.pilot_minutes),"max_level":self.max_level,
                "delta_C":self.delta_C,"unresolved_gradient_cells":self.unresolved_gradient_cells,
                "net_area_m2":sum(a for x,y,a in self.points),
                "net_centroid_m":[sum(x*a for x,y,a in self.points)/sum(a for x,y,a in self.points),
                                  sum(y*a for x,y,a in self.points)/sum(a for x,y,a in self.points)]}

def _sampler(field):
    if field["thermal_method"]==ANNEX_K_METHOD:return sample_annex_k_temperature
    if field["thermal_method"]=="SP2026_8.2.23_FVM":return sample_sp2026_temperature
    raise ValueError("explicit SP thermal route required")

def build(p,fields,*,base_grid=8,max_level=3,delta_C=60.,boundary_band_mm=25.,max_cells=24000):
    if (type(base_grid)!=int or not 1<=base_grid<=80 or type(max_level)!=int or not 0<=max_level<=5
        or not math.isfinite(delta_C) or delta_C<=0 or not math.isfinite(boundary_band_mm)
        or boundary_band_mm<0 or type(max_cells)!=int or max_cells<base_grid**2 or not fields):
        raise ValueError("valid fixed quadrature policy required")
    b,h=p.b_m,p.h_m;sig=bar_signature(p);method=fields[0]["thermal_method"]
    for field in fields:
        if (field["thermal_method"]!=method or abs(field["grid"]["width_mm"]-b*1000)>1e-6
            or abs(field["grid"]["height_mm"]-h*1000)>1e-6 or field["material_family"]!=p.aggregate):
            raise ValueError("inconsistent thermal pilot field")
    sample=_sampler(fields[0])
    @lru_cache(maxsize=None)
    def values(x,y):
        return tuple(float(sample(f,min(b*1000,max(0.,x*1000)),min(h*1000,max(0.,y*1000)))) for f in fields)
    cells=[];unresolved=0
    def visit(x0,x1,y0,y1,level):
        nonlocal unresolved
        xm=(x0+x1)/2;ym=(y0+y1)/2
        near=min(x0,b-x1,y0,h-y1)<boundary_band_mm/1000.-1e-12
        if max_level==0:variation=0.
        else:
            V=np.asarray([values(x,y) for x,y in ((x0,y0),(x1,y0),(x0,y1),(x1,y1),(xm,ym),
                                      (xm,y0),(xm,y1),(x0,ym),(x1,ym))])
            variation=float(np.ptp(V,axis=0).max())
        if level<max_level and (near or variation>delta_C):
            for a,c in ((x0,xm),(xm,x1)):
                for d,e in ((y0,ym),(ym,y1)):visit(a,c,d,e,level+1)
        else:
            cells.append((x0,x1,y0,y1))
            if variation>delta_C:unresolved+=1
            if len(cells)>max_cells:raise ValueError("quadrature resource cap exceeded")
    for j in range(base_grid):
        for i in range(base_grid):
            visit(b*i/base_grid,b*(i+1)/base_grid,h*j/base_grid,h*(j+1)/base_grid,0)
    # Reject overlapping bar discs; all source bars lie fully in section.
    bars=[(x,y,math.sqrt(a/math.pi),a) for _,x,y,a in sig]
    for i,(x,y,r,a) in enumerate(bars):
        if min(x,b-x,y,h-y)<r-1e-12:raise ValueError("bar outside section")
        if any(math.hypot(x-u,y-v)<r+s-1e-12 for u,v,s,_ in bars[:i]):
            raise ValueError("overlapping bars")
    pts=[];removed=np.zeros((len(bars),3))
    for x0,x1,y0,y1 in cells:
        A=(x1-x0)*(y1-y0);X=A*(x0+x1)/2;Y=A*(y0+y1)/2
        for i,(x,y,r,_) in enumerate(bars):
            if x+r<=x0 or x-r>=x1 or y+r<=y0 or y-r>=y1:continue
            a,u,v=circle_moments(x,y,r,x0,x1,y0,y1)
            removed[i]+=(a,u,v);A-=a;X-=u;Y-=v
        if A<-1e-12:raise ArithmeticError("negative net cell area")
        if A<=1e-15:continue
        x=X/A;y=Y/A
        if not (x0-1e-10<=x<=x1+1e-10 and y0-1e-10<=y<=y1+1e-10):
            raise ArithmeticError("net centroid outside cell")
        pts.append((min(x1,max(x0,x)),min(y1,max(y0,y)),A))
    for row,(x,y,r,a) in zip(removed,bars):
        if not np.allclose(row,[a,a*x,a*y],rtol=0.,atol=1e-10):
            raise ArithmeticError("bar area or first moment conservation failed")
    actual=np.array([sum(a for x,y,a in pts),sum(x*a for x,y,a in pts),sum(y*a for x,y,a in pts)])
    expected=np.array([b*h,b*h*b/2,b*h*h/2])-removed.sum(axis=0)
    if not np.allclose(actual,expected,rtol=0.,atol=1e-10):
        raise ArithmeticError("net concrete area/first moment not conserved")
    return Quadrature(b,h,sig,method,tuple(cells),tuple(pts),
                      tuple(float(f["snapshot"]["time_minutes"]) for f in fields),
                      max_level,float(delta_C),base_grid,boundary_band_mm/1000.,unresolved)

def apply_quadrature(p,field,q):
    if (p.b_m,p.h_m,bar_signature(p),field["thermal_method"])!=(q.width,q.height,q.bars,q.method):
        raise ValueError("fixed quadrature identity mismatch")
    x,y,A=np.asarray(q.points,dtype=float).T
    p.x=x;p.y=y;p.area=A;p.u=2*x/p.b_m-1;p.v=2*y/p.h_m-1
    sample=_sampler(field)
    p.theta_c=np.asarray([sample(field,float(xx*1000),float(yy*1000)) for xx,yy in zip(x,y)])
    # History solver uses theta_c directly; keep inherited field consistent.
    from rc_fire.materials.sp2026_fire import concrete_free_thermal_strain_sp
    p.eps_th_c=np.asarray([concrete_free_thermal_strain_sp(float(T),p.aggregate) or 0. for T in p.theta_c])
    return A
