"""SP-R10E: fixed pilot cut-cell quadrature, not moving-state interpolation.

Piecewise affine pilot elastic gap and max-temperature cutoff contours
partition bar-free rectangles into positive polygon centroid subcells.
Cut geometry selected before mechanical replay. No history transfer or
exact nonlinear front claim. Bar-overlapping cells keep R10C exact net
rectangle centroid. Unknown probes and skipped cuts reported explicitly.
"""
from dataclasses import dataclass,replace
from functools import lru_cache
import math
import numpy as np
from rc_fire.mechanics import sp2026_r10c_quadrature as q
from rc_fire.mechanics import sp2026_r9g_hot_domain as hot

VERSION="SP-R10E-fixed-pilot-polygon-cuts-v1"

def moments(poly):
    """CCW polygon area and first moments in local unit-square coordinates."""
    if len(poly)<3:return 0.,0.,0.
    z=[a[0]*b[1]-b[0]*a[1] for a,b in zip(poly,poly[1:]+poly[:1])]
    A=sum(z)/2
    if A< -1e-14:raise ArithmeticError("polygon orientation reversed")
    return max(0.,A),sum((a[0]+b[0])*c for a,b,c in zip(poly,poly[1:]+poly[:1],z))/6, sum((a[1]+b[1])*c for a,b,c in zip(poly,poly[1:]+poly[:1],z))/6

def clip(poly,coeff,side):
    """Half-plane clipping; both children share exactly the same cut."""
    a,b,c=coeff
    def val(p):return side*(a*p[0]+b*p[1]+c)
    out=[]
    for u,v in zip(poly,poly[1:]+poly[:1]):
        fu,fv=val(u),val(v)
        if fu>=0:out.append(u)
        if (fu>0 and fv<0) or (fu<0 and fv>0):
            t=fu/(fu-fv);out.append((u[0]+t*(v[0]-u[0]),u[1]+t*(v[1]-u[1])))
    return out

def partition_rectangle(values,*,max_polygons=64):
    """values: rows of four corner samples (00,10,11,01), signed fields.
    Split two triangles by each affine interpolant; retain tiny children
    only when positive to machine precision. Uncut cells stay one point.
    The input field is interpolated, not the actual constitutive history.
    """
    if max_polygons<2:raise ValueError("polygon cap too small")
    if any(len(v)!=4 or not all(math.isfinite(x) for x in v) for v in values):
        raise ValueError("finite four-corner fields required")
    mixed=[v for v in values if min(v)<0<max(v)]
    if not mixed:return [(0.5,0.5,1.)],0
    corners=[(0.,0.),(1.,0.),(1.,1.),(0.,1.)]
    result=[];skips=0
    for ids in ((0,1,2),(0,2,3)):
        tri=[corners[i] for i in ids];parts=[tri]
        matrix=np.array([[x,y,1.] for x,y in tri])
        for v in mixed:
            vv=[v[i] for i in ids]
            if not min(vv)<0<max(vv):continue
            co=np.linalg.solve(matrix,np.array(vv))
            new=[]
            for poly in parts:
                s=[co[0]*x+co[1]*y+co[2] for x,y in poly]
                if not min(s)<-1e-15 or not max(s)>1e-15:
                    new.append(poly);continue
                children=[clip(poly,co,k) for k in (1.,-1.)]
                children=[z for z in children if moments(z)[0]>1e-15]
                new.extend(children)
            if len(new)>max_polygons//2:
                skips+=1;continue
            parts=new
        result.extend(parts)
    pts=[]
    for poly in result:
        A,X,Y=moments(poly)
        if A>1e-15:pts.append((X/A,Y/A,A))
    M=np.array([sum(a for x,y,a in pts),sum(x*a for x,y,a in pts),sum(y*a for x,y,a in pts)])
    if not np.allclose(M,[1.,.5,.5],rtol=0.,atol=2e-12):
        raise ArithmeticError("cut polygon partition area/first moment error")
    return pts,skips

def make_probe(seed,fields,rows,*,width,height,selected_times):
    if len(fields)!=len(rows) or not fields:raise ValueError("aligned pilot required")
    selected=set(selected_times)
    if not selected or not selected.issubset({r["time_minutes"] for r in rows}):
        raise ValueError("selected times must be actual pilot checkpoints")
    for f,r in zip(fields,rows):
        if r["status"]!="EQUILIBRATED_RESEARCH_SECTION" or f["snapshot"]["time_minutes"]!=r["time_minutes"]:
            raise ValueError("pilot history incomplete")
    @lru_cache(maxsize=None)
    def probe(x,y):
        s=seed;out=[]
        B=np.array([1.,2*y/height-1,2*x/width-1])
        for f,r in zip(fields,rows):
            t=r["time_minutes"]
            try:
                T=q._sampler(f)(f,min(width*1000,max(0.,x*1000)),min(height*1000,max(0.,y*1000)))
                s,L=hot.trial_step(s,time_s=1.+60*t,temperature_C=float(T),total_compression=float(B@r["q"]))
            except (ValueError,ArithmeticError):
                return None
            if t not in selected:continue
            # Signed gap, including negative values in open concrete.
            # Cutoff contour kept independent; do not extrapolate gap
            # beyond material domain or treat cutoff as mechanical damage.
            gap=None if s.thermal_cutoff or s.active.damage==1. else L["mechanical_compression"]-s.active.plastic_compression
            out.append((gap,800.-s.maximum_temperature_C,s.active.damage==1.))
        return tuple(out)
    return probe

@dataclass(frozen=True)
class CutQuadrature(q.Quadrature):
    cut_cells:int=0
    bar_fallback_cells:int=0
    unknown_cells:int=0
    unavailable_gap_cells:int=0
    skipped_cuts:int=0
    selected_times:tuple=()
    def evidence(self):
        return {**super().evidence(),"cut_cells":self.cut_cells,"bar_fallback_cells":self.bar_fallback_cells,
                "unknown_cells":self.unknown_cells,"unavailable_gap_cells":self.unavailable_gap_cells,
                "skipped_cuts":self.skipped_cuts,"selected_cut_times":list(self.selected_times)}

def build(mesh,probe,*,selected_times,max_points=24000,max_polygons=64):
    pts=[];cut=barfallback=unknown=unavailable=skipped=0
    bars=[(x,y,math.sqrt(a/math.pi)) for _,x,y,a in mesh.bars]
    for x0,x1,y0,y1 in mesh.cells:
        dx=x1-x0;dy=y1-y0;A=dx*dy;X=A*(x0+x1)/2;Y=A*(y0+y1)/2
        overlaps=False
        for x,y,r in bars:
            if x+r<=x0 or x-r>=x1 or y+r<=y0 or y-r>=y1:continue
            a,u,v=q.circle_moments(x,y,r,x0,x1,y0,y1)
            if a>1e-15:overlaps=True
            A-=a;X-=u;Y-=v
        if A<-1e-12:raise ArithmeticError("negative net cut cell")
        if A<=1e-15:continue
        original=(min(x1,max(x0,X/A)),min(y1,max(y0,Y/A)),A)
        if overlaps:
            barfallback+=1;pts.append(original);continue
        v=[probe(x,y) for x,y in ((x0,y0),(x1,y0),(x1,y1),(x0,y1))]
        if any(z is None for z in v):
            unknown+=1;pts.append(original);continue
        if any(len(z)!=len(selected_times) for z in v):raise ValueError("probe signature length mismatch")
        fields=[];missing=False
        for at in zip(*v):
            gaps=[z[0] for z in at];Ts=[z[1] for z in at]
            fields.append(Ts)
            if all(g is not None for g in gaps):fields.append(gaps)
            elif any(g is not None for g in gaps) or len({z[2] for z in at})>1:missing=True
        if missing:unavailable+=1
        sub,sk=partition_rectangle(fields,max_polygons=max_polygons)
        skipped+=sk
        if len(sub)>1:cut+=1
        pts.extend((x0+dx*x,y0+dy*y,A*a) for x,y,a in sub)
        if len(pts)>max_points:raise ValueError("cut-cell point cap exceeded")
    if len(pts)>max_points:raise ValueError("cut-cell point cap exceeded")
    def M(p):return np.array([sum(a for x,y,a in p),sum(x*a for x,y,a in p),sum(y*a for x,y,a in p)])
    if not np.allclose(M(pts),M(mesh.points),rtol=0.,atol=1e-10):
        raise ArithmeticError("cut-cell net area/first moment conservation failed")
    return CutQuadrature(**{k:getattr(mesh,k) for k in q.Quadrature.__dataclass_fields__ if k!="points"},
             points=tuple(pts),cut_cells=cut,bar_fallback_cells=barfallback,unknown_cells=unknown,
             unavailable_gap_cells=unavailable,skipped_cuts=skipped,selected_times=tuple(selected_times))
