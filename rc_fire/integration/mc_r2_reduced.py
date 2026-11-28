"""MC-R2: restricted reduced-section analytical engineering comparator.

Explicit opt-in only. SP §8.2.21 scope; no rating lookup or default
replacement of the user's full-temperature method. Annex K point
temperatures define a conservative inscribed strip geometry; K.27 is
an independent square-area comparison, NOT the strip inertia formula.
SP5 section strain law and nominal stiffness; engineering extensions
are documented and not admitted as regulatory R.
"""
import math
import numpy as np
from scipy.optimize import brentq
from rc_fire.thermal.sp2026_annex_k_field import build_annex_k_snapshot, sample_annex_k_temperature
from rc_fire.thermal.normative import (RectangularExposure,temperature_rectangle,
    critical_temperature_C,square_four_face_reduced_section)
from rc_fire.mechanics.critical_isotherm import _action_plane,_bar_layout_scope
from rc_fire.materials.normative import resolve_materials,Reinforcement
from rc_fire.materials.sp2026_fire import steel_at_sp_fire
from rc_fire.mechanics.sp2026_nominal_member import design_parameters
from rc_fire.integration.mc_r1_engineering import finite

MODE="MC_R2_REDUCED_SECTION_COMPARATOR"
CONTRACT=("first_order_fire_actions","imperfections_and_minimum_eccentricity_reconciled",
    "effective_lengths_and_critical_sections_confirmed","uniform_longitudinal_heating_confirmed")
def _base():
    return {"method":MODE,"normative_claim":False,"actual_t_R_minutes":None,
        "regulatory_result":"NOT_ESTABLISHED","actual_U_t":None}
def _guard(condition,reason):
    if not condition:raise ValueError(reason)
def _geometry(ex,coeff,t,critical,axis,bars,strips,*,area_method='contour'):
    """Inner rectangular strips; full strip corner must be below critical.
    Integrate concrete width minus actual circular bar intersections.
    Coordinates centred; z is bending coordinate, u transverse.
    """
    depth=(ex.h_mm if axis=="x" else ex.b_mm)/1000.
    width=(ex.b_mm if axis=="x" else ex.h_mm)/1000.
    H=depth/2;W=width/2
    if t:
        l=math.sqrt(12*coeff["a_red_m2_h"]*t/60)
        off=coeff["phi_1"]*math.sqrt(coeff["a_red_m2_h"])
        p=lambda d:(1-min(1.,(d+off)/l))**2
        _guard(all(p(0)+p(d)<=1.+1e-12 for d in (depth,width)),
               "ANNEX_K_OVERLAPPING_HEAT_LAYER_DOMAIN")
    def temp(u,z):
        x,y=((u+W)*1000,(z+H)*1000) if axis=="x" else ((z+H)*1000,(u+W)*1000)
        v,meta=temperature_rectangle(ex,coeff,t,x,y)
        _guard(not bool(meta["outside_approximation_C"]),"ANNEX_K_TEMPERATURE_DOMAIN")
        return float(v)
    _guard(temp(0,0)<critical,"NO_POSITIVE_RETAINED_CONCRETE")
    if area_method=="k27_cross":
        _guard(abs(H-W)<=1e-10,"K27_REQUIRES_SQUARE_SECTION")
        if temp(W,H)<=critical:
            segments=[(-H,H,W)]
        else:
            k27=square_four_face_reduced_section(ex,coeff,t,critical)
            _guard(k27["status"]=="evaluated","K27_DOMAIN: "+str(k27.get("reason")))
            a=H-k27["lc_m"]
            target=k27["remaining_area_m2"]
            # The area of a cross cut from a 2a square by four
            # identical corner squares is 4a²-4(a-c)².
            c=a-math.sqrt(max(0.,a*a-target/4))
            _guard(0<c<=a<=H,"INVALID_K27_CROSS")
            _guard(max(temp(c,a),temp(a,c))<=critical+1e-7,
                   "K27_CROSS_NOT_INSIDE_CRITICAL_CONTOUR")
            segments=[(-a,-c,c),(-c,c,a),(c,a,c)]
    elif area_method=="contour":
        segments=None
    else:raise ValueError("UNKNOWN_AREA_METHOD")
    # Boundary of the retained domain along the symmetry axis.
    if segments is None:
        zmax=H if temp(0,H)<=critical else brentq(lambda z:temp(0,z)-critical,0,H,xtol=1e-13)
        # Equal strips, mirrored, evaluate the outer (hotter) edge. No
        # centre threshold or interpolation of a thermal field.
        segments=[]
        for lo,hi in zip(np.linspace(0,zmax,strips+1)[:-1],np.linspace(0,zmax,strips+1)[1:]):
            if temp(0,float(hi))>=critical-1e-9:continue
            w=W if temp(W,float(hi))<=critical else brentq(lambda u:temp(u,float(hi))-critical,0,W,xtol=1e-13)
            if w>0:segments.extend([(-float(hi),-float(lo),w),(float(lo),float(hi),w)])
    _guard(bool(segments),"EMPTY_STRIP_CORE")
    outer=max(hi for lo,hi,w in segments)
    # Integrate the circular hole chords at Gauss nodes, split at all
    # circle/strip edge events to avoid sampling discontinuities.
    nodes,weights=np.polynomial.legendre.leggauss(12)
    Z=[];A=[];Ix=[];Iy=[];gross=0.;Igx=0.;Igy=0.
    for lo,hi,w in sorted(segments):
        gross+=2*w*(hi-lo)
        Igx+=2*w*(hi**3-lo**3)/3
        Igy+=2*w**3*(hi-lo)/3
        # Even the analytic cross has a distributed stress field.
        split=set(float(v) for v in np.linspace(lo,hi,max(2,math.ceil((hi-lo)/(depth/(2*strips)))+1)))
        for bar in bars:
            u,z,r=bar["u"],bar["z"],bar["r"]
            for v in (z-r,z+r):
                if lo<v<hi:split.add(v)
            for edge in (-w,w):
                if abs(edge-u)<r:
                    q=math.sqrt(r*r-(edge-u)**2)
                    for v in (z-q,z+q):
                        if lo<v<hi:split.add(v)
        cuts=sorted(split)
        for a,b in zip(cuts,cuts[1:]):
            for n,g in zip(nodes,weights):
                z=(a+b)/2+(b-a)*float(n)/2;dw=(b-a)*float(g)/2
                width_net=2*w;iu=2*w**3/3
                for bar in bars:
                    dz=z-bar["z"];r=bar["r"];u=bar["u"]
                    if abs(dz)>=r:continue
                    q=math.sqrt(r*r-dz*dz);left=max(-w,u-q);right=min(w,u+q)
                    if right>left:
                        width_net-=right-left;iu-=(right**3-left**3)/3
                _guard(width_net>=-1e-12 and iu>=-1e-12,"NEGATIVE_NET_CONCRETE")
                Z.append(z);A.append(max(0.,width_net)*dw)
                Ix.append(max(0.,width_net)*dw*z*z);Iy.append(max(0.,iu)*dw)
    area=sum(A)
    _guard(area>0,"EMPTY_NET_CORE")
    return {"z":np.array(Z),"A":np.array(A),"zmax":outer,"area_method":area_method,
        "area":area,"gross_area":gross,"Ix":sum(Ix),"Iy":sum(Iy),
        "gross_Ix":Igx,"gross_Iy":Igy,"segments":len(segments)}

def capacity(g,bars,N,fc,eps2,epsu,n):
    """Maximum positive moment on bounded, monotone uniaxial section law.
    At fixed curvature, solve axial equilibrium on the admissible strain
    interval. N_upper nonincreasing and N_lower nondecreasing with k
    for the admitted geometry and outer-bar yield condition. Nonnegative
    material tangents imply nondecreasing M at fixed N.
    """
    z=g["z"];A=g["A"];zb=np.array([b["z"] for b in bars])
    As=np.array([b["A"] for b in bars]);fy=np.array([b["fy"] for b in bars])
    E=np.array([b["E"] for b in bars])
    zmax=g["zmax"];zmin=float(min(zb));et=.010
    _guard(zmin<0 and zmax>0,"INVALID_SECTION_DEPTH")
    _guard(not np.any((zb>zmax)&(fy/E>epsu)),
           "OUTER_COMPRESSION_BAR_NOT_YIELDED_AT_CONCRETE_LIMIT")
    def forces(e,k):
        ec=np.clip((e+k*z)/eps2,0.,1.)
        sc=fc*(1-(1-ec)**n)
        ss=np.clip(E*(e+k*zb),-fy,fy)
        return float(1000*(np.dot(A,sc)+np.dot(As,ss))),float(1000*(np.dot(A*z,sc)+np.dot(As*zb,ss)))
    def bounds(k):
        lo=-et-k*zmin;hi=epsu-k*zmax
        return lo,hi,forces(lo,k)[0],forces(hi,k)[0]
    lo,hi,nlo,nhi=bounds(0.)
    if N>nhi or N<nlo:return {"status":"AXIAL_DOMAIN_EXCEEDED","N_limit_kN":nhi,"M_Rd_kNm":None}
    km=(epsu+et)/(zmax-zmin)
    def feasible(k):
        lo,hi,l,h=bounds(k)
        return lo<=hi+1e-13 and l<=N<=h
    if feasible(km):k=km
    else:
        a=0.;b=km
        for _ in range(60):
            mid=(a+b)/2
            if feasible(mid):a=mid
            else:b=mid
        k=a
    lo,hi,l,h=bounds(k)
    if abs(l-N)<1e-8:e=lo
    elif abs(h-N)<1e-8:e=hi
    else:e=brentq(lambda e:forces(e,k)[0]-N,lo,hi,xtol=1e-15)
    f,m=forces(e,k)
    _guard(abs(f-N)<=1e-5,"AXIAL_EQUILIBRIUM_RESIDUAL")
    return {"status":"BOUNDED_SECTION_CAPACITY","M_Rd_kNm":m,"N_kN":f,
        "axial_residual_kN":abs(f-N),"curvature_per_m":k,"centroid_strain":e,
        "max_concrete_strain":e+k*zmax,"max_steel_tension_strain":max(0.,-float(min(e+k*zb))),
        "governing_limit":"concrete" if abs(e+k*zmax-epsu)<=1e-9 else "steel_tension"}

def assess(column,time_minutes,*,selected=False,action_contract,creep_by_axis,strips=48,
           bar_distance_convention="clear",area_method="contour"):
    out={**_base(),"time_minutes":float(time_minutes)}
    try:
        _guard(selected is True,"EXPLICIT_REDUCED_SECTION_COMPARATOR_SELECTION_REQUIRED")
        _guard(all(action_contract.get(k) is True for k in CONTRACT),"ACTION_CONTRACT_REQUIRED")
        _guard(type(strips) is int and 8<=strips<=256,"STRIPS_8_TO_256")
        axis,issues=_action_plane(column)
        _guard(axis is not None,";".join(issues))
        issues=_bar_layout_scope(column,axis);_guard(not issues,";".join(issues))
        field=build_annex_k_snapshot(column,time_minutes,bar_distance_convention=bar_distance_convention)
        _guard(set(field["exposed_faces"])=={"left","right","bottom","top"},"FOUR_FACE_SYMMETRIC_HEATING_REQUIRED")
        mat=resolve_materials(column);_guard(mat["status"]=="resolved_for_property_lookup","MATERIAL_CATALOG_UNRESOLVED")
        c=mat["concrete"];s=mat["steel"];family=mat["fire_family"]
        _guard(family==field["material_family"],"MATERIAL_FAMILY_MISMATCH")
        _guard(c["f_ck_MPa"]<=50.,"ORDINARY_HEAVY_CONCRETE_ONLY")
        critical=critical_temperature_C(column["concrete"],family)
        _guard(critical is not None,"CRITICAL_TEMPERATURE_UNSUPPORTED")
        p=design_parameters(c,s)
        b=float(column["b_mm"]);h=float(column["h_mm"])
        ex=RectangularExposure(b,h,tuple(field["exposed_faces"]))
        steel=Reinforcement(grade=column["steel_grade"],**((column.get("material_spec") or {}).get("steel") or {}))
        bars=[]
        for bar in column["bars"]:
            x=float(bar["x_mm"]);y=float(bar["y_mm"]);d=float(bar["diameter_mm"])
            T=sample_annex_k_temperature(field,x,y,bar_diameter_mm=d)
            hot=steel_at_sp_fire(steel,T,normal=s)
            u,z=((x-b/2)/1000,(y-h/2)/1000) if axis=="x" else ((y-h/2)/1000,(x-b/2)/1000)
            r=d/2000
            _guard(all(math.hypot(u-v["u"],z-v["z"])>=r+v["r"] for v in bars),"OVERLAPPING_BARS")
            bars.append({"id":str(bar["id"]),"u":u,"z":z,"r":r,"A":math.pi*r*r,
                "T_C":T,"fy":hot.strength_MPa,"E":hot.elastic_modulus_MPa})
        _guard(len({v["id"] for v in bars})==len(bars),"DUPLICATE_BAR_IDS")
        g=_geometry(ex,field["annex_k_coefficients"],float(time_minutes),critical,axis,bars,strips,area_method=area_method)
        k27=square_four_face_reduced_section(ex,field["annex_k_coefficients"],time_minutes,critical)
        L=finite(column["length_m"],"L",True)
        rows=[]
        for sec in column["sections"]:
            N=finite(sec["N_kN"],"N",True);z=finite(sec["z_m"],"z")
            _guard(0<=z<=L,"SECTION_POSITION_OUTSIDE_COLUMN")
            m=finite(sec["M"+axis+"_kNm"],"M")
            rigid={}
            for a,I,coordinate in ((axis,g["Ix"],"z"),("y" if axis=="x" else "x",g["Iy"],"u")):
                phi=finite(creep_by_axis[a],"phi");_guard(phi>=0,"NEGATIVE_CREEP")
                l0=L*finite(column["mu_"+a],"mu",True)
                slender=l0/math.sqrt(I/g["area"])
                n=N/(1000*g["area"]*c["f_ck_MPa"])
                kc=math.sqrt(c["f_ck_MPa"]/20)*min(.2,n*slender/170)/(1+phi)
                Eis=sum(v["E"]*(v["A"]*v[coordinate]**2+math.pi*v["r"]**4/4) for v in bars)*1000
                B=kc*p["Ecd_20_MPa"]*1000*I+Eis
                Ncr=math.pi**2*B/l0**2
                rigid[a]={"B_kNm2":B,"Ncrit_kN":Ncr,"eta":1/(1-N/Ncr) if N<Ncr else None,
                    "phi_eff":phi,"l0_m":l0,"slenderness":slender}
            cap=capacity(g,bars,N,c["f_ck_MPa"],c["eps_c2_permille"]/1000,c["eps_cu2_permille"]/1000,c["n_parabola"])
            M2=m*rigid[axis]["eta"] if rigid[axis]["eta"] is not None else None
            ratio=abs(M2)/cap["M_Rd_kNm"] if M2 is not None and cap["M_Rd_kNm"] is not None and cap["M_Rd_kNm"]>0 else None
            status=("UNRESOLVED_NOMINAL_STABILITY" if any(v["eta"] is None for v in rigid.values()) else
                "AXIAL_MODEL_LIMIT_EXCEEDED" if cap["status"]=="AXIAL_DOMAIN_EXCEEDED" else
                "UNRESOLVED_RESISTANCE" if ratio is None else "MODEL_WITHIN" if ratio<=1 else "MODEL_MOMENT_LIMIT_EXCEEDED")
            rows.append({"id":str(sec["id"]),"N_kN":N,"M0_kNm":m,"M2_kNm":M2,"nominal":rigid,
                "capacity":cap,"moment_ratio":ratio,"status":status})
        _guard(len({r["id"] for r in rows})==len(rows),"DUPLICATE_SECTION_IDS")
        status="ALL_MODEL_CHECKS_WITHIN" if all(r["status"]=="MODEL_WITHIN" for r in rows) else "MODEL_LIMIT_OR_UNRESOLVED"
        return {**out,"status":status,"axis":axis,"critical_C":critical,
            "geometry":{"area_method":area_method,"gross_area_m2":g["gross_area"],"net_area_m2":g["area"],"I_bending_m4":g["Ix"],
                "I_other_m4":g["Iy"],"strips":g["segments"],"K27":k27},
            "bars":bars,"sections":rows,"thermal_provenance":field["annex_k_provenance"],
            "remaining_gates":["EXPLICIT_COMPARATOR_NOT_DEFAULT","ANNEX_K_K5_K11_INTERPRETATION",
               "K27_AREA_VERSUS_INSCRIBED_STRIPS_AND_INERTIA","RETAINED_CONCRETE_AMBIENT_STRENGTH_AND_ECD",
               "STEEL_BOND_AND_ANCHORAGE","NOMINAL_STIFFNESS_FIRE_QUALIFICATION","ANNEX_L_SPALLING",
               "INDEPENDENT_REFERENCE_AND_ENGINEERING_REVIEW"]}
    except (ValueError,TypeError,KeyError,ArithmeticError) as e:
        return {**out,"status":"UNRESOLVED","reason":str(e)}
