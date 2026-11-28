"""Exact circle-rectangle area integration, source-neutral geometry."""
import math

def circle_rectangle_area(cx,cy,r,x0,x1,y0,y1):
    """Integrate circle/rectangle intersection exactly by piecewise primitives."""
    a=max(x0-cx,-r);b=min(x1-cx,r)
    if a>=b:return 0.
    lo=y0-cy;hi=y1-cy
    cuts=[a,b]
    for v in (lo,hi):
        if abs(v)<=r:  # include tangent split at x=0 for y=±r
            z=math.sqrt(max(0.,r*r-v*v))
            cuts.extend(x for x in (-z,z) if a<x<b)
    cuts=sorted(set(cuts))
    def primitive(x):
        return .5*(x*math.sqrt(max(0.,r*r-x*x))+r*r*math.asin(max(-1.,min(1.,x/r))))
    area=0.
    for l,h in zip(cuts,cuts[1:]):
        z=math.sqrt(max(0.,r*r-((l+h)/2)**2))
        top=min(hi,z);bottom=max(lo,-z)
        if top<=bottom:continue
        top_slope=1. if z<hi else 0.
        bottom_slope=-1. if -z>lo else 0.
        constant=(0. if top_slope else hi)-(0. if bottom_slope else lo)
        area+=(top_slope-bottom_slope)*(primitive(h)-primitive(l))+constant*(h-l)
    return max(0.,area)

