"""SP-PROD.1 first normative-only engineering route.

Full Annex K temperature field, NOT critical isotherm. Ordinary heavy
rectangular concrete and symmetric four-face heat/reinforcement, no axial
restraint, independent scalar nominal-stiffness axes. SP5 section design
limits are fixed by class, SP fire characteristic resistance times k.
Input fire actions already combined. No research constitutive dependency.
Nonuniform EI integration is a transparent engineering extension of
8.56, not an explicitly prescribed SP formula. Retain all admission gates.
"""
import math
import numpy as np
from rc_fire.materials.normative import resolve_materials,ConcreteMix,Reinforcement
from rc_fire.materials.sp2026_fire import concrete_at_sp_fire,steel_at_sp_fire,concrete_free_thermal_strain_sp,steel_free_thermal_strain_sp
from rc_fire.thermal.sp2026_annex_k_field import build_annex_k_snapshot,sample_annex_k_temperature
from rc_fire.mechanics.sp_prod1_bounded_section import Section,utilization,PASS,FAIL,UNKNOWN
from rc_fire.mechanics.sp_prod1_geometry import circle_rectangle_area

CONTRACT=("first_order_fire_actions","imperfections_and_minimum_eccentricity_reconciled",
          "effective_lengths_and_critical_sections_confirmed","uniform_longitudinal_heating_confirmed",
          "free_axial_expansion_confirmed")
WITHIN="ALL_MODEL_CHECKS_WITHIN"
EXCEEDED="SECTION_RESISTANCE_EXCEEDED"
UNRESOLVED="UNRESOLVED"

def num(x,positive=False):
    if isinstance(x,bool):raise ValueError("finite number required")
    x=float(x)
    if not math.isfinite(x) or (positive and x<=0):raise ValueError("finite valid number required")
    return x

def require(ok,why):
    if not ok:raise ValueError(why)

def prepare(column,t,grid,bar_distance_convention):
    require(type(grid) is int and 8<=grid<=80,"grid integer 8..80")
    b,h=num(column["b_mm"],True)/1000,num(column["h_mm"],True)/1000
    f=build_annex_k_snapshot(column,t,bar_distance_convention=bar_distance_convention)
    require(set(f["exposed_faces"])=={"left","right","bottom","top"},"four-face symmetric initial scope")
    mat=resolve_materials(column);require(mat["status"]=="resolved_for_property_lookup","material inputs: "+str(mat["issues"]))
    family=mat["fire_family"];c=mat["concrete"];s=mat["steel"]
    require(family==f["material_family"] and family in ("siliceous","calcareous"),"ordinary heavy concrete")
    require(c["f_ck_MPa"]<=50.,"concrete class > C50/60 outside initial scope")
    mix=ConcreteMix(column["concrete"],aggregate_family=family)
    steel=Reinforcement(column["steel_grade"],**((column.get("material_spec") or {}).get("steel") or {}))
    require(steel.product_type=="weldable_bar" and 240<=s["f_yk_MPa"]<=500,"ordinary nonprestressed S240-S500 bars")
    bars=[];ids=set()
    for v in column["bars"]:
        x=num(v["x_mm"])/1000;y=num(v["y_mm"])/1000;r=num(v["diameter_mm"],True)/2000
        require(r<=x<=b-r and r<=y<=h-r,"bar outside concrete")
        require(str(v["id"]) not in ids,"duplicate bar id");ids.add(str(v["id"]))
        require(all(math.hypot(x-z[0],y-z[1])>=r+z[2]-1e-12 for z in bars),"overlapping bars")
        bars.append((x,y,r,str(v["id"])))
    require(bool(bars),"reinforcement required")
    for x,y,r,_ in bars:
        for xx,yy in ((b-x,y),(x,h-y)):
            require(any(abs(xx-z[0])<1e-10 and abs(yy-z[1])<1e-10 and abs(r-z[2])<1e-10 for z in bars),"reflection symmetry of reinforcement required")
    dx,dy=b/grid,h/grid
    xy=[((i+.5)*dx,(j+.5)*dy) for j in range(grid) for i in range(grid)]
    x=np.array([v[0] for v in xy]);y=np.array([v[1] for v in xy])
    A=np.full(len(x),dx*dy)
    for bx,by,r,_ in bars:
        hole=np.array([circle_rectangle_area(bx,by,r,xx-dx/2,xx+dx/2,yy-dy/2,yy+dy/2) for xx,yy in xy])
        require(abs(hole.sum()-math.pi*r*r)<1e-10,"bar area conservation")
        A-=hole
    require(min(A)>=-1e-12,"negative net area");A=np.maximum(A,0.)
    As=np.array([math.pi*v[2]**2 for v in bars])
    require(abs(sum(A)+sum(As)-b*h)<1e-10,"net area conservation")
    def temp(x,y,d=0.):return sample_annex_k_temperature(f,1000*x,1000*y,bar_diameter_mm=1000*d)
    tc=np.array([temp(xx,yy) for xx,yy in xy])
    ts=np.array([temp(xx,yy,2*r) for xx,yy,r,_ in bars])
    cm=[concrete_at_sp_fire(mix,T,c) for T in tc]
    sm=[steel_at_sp_fire(steel,T,s) for T in ts]
    fc=np.array([v.strength_MPa for v in cm]);Ec=np.array([v.elastic_modulus_MPa/1.2 for v in cm])
    fy=np.array([v.strength_MPa for v in sm]);Es=np.array([v.elastic_modulus_MPa for v in sm])
    # Positive compression mechanical strain = total compression + free expansion.
    th=np.array([1000*(concrete_free_thermal_strain_sp(T,family) or 0.) for T in tc])
    ths=np.array([1000*steel_free_thermal_strain_sp(T) for T in ts])
    def shape(xx,yy):return np.array([1.,2*yy/h-1,2*xx/b-1])
    C=np.array([shape(xx,yy) for xx,yy in xy]);B=np.array([shape(xx,yy) for xx,yy,_,_ in bars])
    ep,eu,n=c["eps_c2_permille"],c["eps_cu2_permille"],c["n_parabola"]
    active=(fc>0)&(A>0)
    # Check every active cell and node (including boundary) at the same
    # temperature law. This is sampled, not a continuum extremum proof.
    D=list(C[active]);limit=list(eu-th[active])
    metadata=[{"kind":"concrete_cell","x_mm":1000*xx,"y_mm":1000*yy,
               "temperature_C":float(T),"free_strain_permille":float(e)}
              for xx,yy,T,e in zip(x[active],y[active],tc[active],th[active])]
    for j in range(grid+1):
        for i in range(grid+1):
            xx,yy=i*dx,j*dy;T=temp(xx,yy)
            if T<=800.:
                e=1000*concrete_free_thermal_strain_sp(T,family)
                D.append(shape(xx,yy));limit.append(eu-e)
                metadata.append({"kind":"concrete_boundary_node" if i in (0,grid) or j in (0,grid) else "concrete_interior_node",
                    "x_mm":1000*xx,"y_mm":1000*yy,"temperature_C":float(T),"free_strain_permille":float(e)})
    D.extend(-B);limit.extend(10.+ths)
    metadata.extend({"kind":"steel_tension","id":id,"x_mm":1000*xx,"y_mm":1000*yy,
                     "temperature_C":float(T),"free_strain_permille":float(e)}
                    for (xx,yy,_,id),T,e in zip(bars,ts,ths))
    section=Section(C,A,fc,th,B,As,fy,Es,ths,D,limit,ep,eu,n)
    section.constraint_metadata=metadata
    # Exact net gross geometry; temperature-weighted concrete stiffness
    # uses net cell areas and approximate own cell moments (mesh study).
    xx=x-b/2;yy=y-h/2
    sx=np.array([v[0]-b/2 for v in bars]);sy=np.array([v[1]-h/2 for v in bars])
    own=np.array([math.pi*v[2]**4/4 for v in bars])
    Ic={"x":b*h**3/12-float(As@sy**2+sum(own)),
        "y":h*b**3/12-float(As@sx**2+sum(own))}
    EIc={"x":float(1000*np.dot(A*Ec,yy**2+dy**2/12)),
         "y":float(1000*np.dot(A*Ec,xx**2+dx**2/12))}
    if np.max(Ec)-np.min(Ec)<1e-8:
        EIc={a:1000*float(Ec[0])*Ic[a] for a in Ic}
    EIs={"x":float(1000*Es@(As*sy**2+own)),
         "y":float(1000*Es@(As*sx**2+own))}
    # Separate symmetry checks prevent cancellation between concrete and steel.
    for weights,xv,yv in ((A*Ec,xx,yy),(As*Es,sx,sy)):
        W=float(sum(weights))
        if W>0:
            require(max(abs(weights@xv)/(W*b),abs(weights@yv)/(W*h),abs(weights@(xv*yv))/(W*b*h))<=1e-8,"coupled bending/axial stiffness outside scope")
    return section,{"b":b,"h":h,"Ac":float(sum(A)),"Ic":Ic,"EIc":EIc,"EIs":EIs,
        "fck":float(c["f_ck_MPa"]),"hot_axial_concrete_kN":float(1000*A@fc),
        "hot_axial_total_kN":float(1000*(A@fc+As@fy)),
        "bar_temperatures_C":{v[3]:float(T) for v,T in zip(bars,ts)},
        "max_concrete_cell_T_C":float(max(tc)),"max_concrete_boundary_T_C":float(f["snapshot"]["boundary_max_C"]),"strain_parameters_permille":{"eps_c2":ep,"eps_cu2":eu,"steel_tension":10.},
        "thermal_provenance":f["annex_k_provenance"],"grid":grid,
        "nonuniform_nominal_stiffness_extension":True}

def governing_constraint(sec,result):
    q=result.get("q_permille")
    if q is None:return None
    v=sec.D@np.asarray(q)-sec.d;i=int(np.argmax(v))
    point=sec.constraint_metadata[i]
    limit=10. if point["kind"]=="steel_tension" else sec.epsu
    return {**point,"limit_permille":limit,"checked_strain_permille":float(limit+v[i]),
            "excess_permille":float(v[i])}

def nominal(g,N,L,mu,phi):
    l0=L*mu;require(g["hot_axial_concrete_kN"]>0,"zero concrete compression capacity")
    a=phi[0];creep=phi[1]
    require(creep>=0,"nonnegative effective creep")
    slender=l0/math.sqrt(g["Ic"][a]/g["Ac"])
    n=N/g["hot_axial_concrete_kN"]
    k1=math.sqrt(g["fck"]/20);k2=min(.2,n*slender/170)
    kc=k1*k2/(1+creep);B=kc*g["EIc"][a]+g["EIs"][a];Ncr=math.pi**2*B/l0**2
    require(Ncr>0,"nonpositive nominal critical force")
    return {"l0_m":l0,"lambda_a":slender,"n":n,"k1a":k1,"k2a":k2,"kc_nominal":kc,
            "phi_eff":creep,"B_nom_kNm2":B,"Ncrit_kN":Ncr,"N_over_Ncrit":N/Ncr,
            "eta":1/(1-N/Ncr) if N<Ncr else None}

GATES=["ANNEX_K_K5_K11_SOURCE_INTERPRETATION","NONUNIFORM_SP5_NOMINAL_STIFFNESS_ENGINEERING_EXTENSION",
       "SP_8_2_19_SIGNED_COEFFICIENT_INTEGRATION_CONVENTION","THERMAL_AND_SECTION_MESH_CONVERGENCE",
       "ANNEX_L_APPLICABILITY_AND_SPALLING","PROJECT_INPUT_AND_NORMATIVE_REVIEW"]

def assess(column,t,*,grid=12,creep_by_axis,action_contract,bar_distance_convention,calculate_U=True):
    out={"t":num(t),"status":UNRESOLVED,"U":None,"sections":[],"normative_claim":False,"remaining_gates":GATES}
    try:
        require(all(action_contract.get(k) is True for k in CONTRACT),"explicit member action/geometry contract")
        require(bar_distance_convention in ("clear","centre"),"explicit K.5 distance convention")
        L=num(column["length_m"],True);mu={a:num(column["mu_"+a],True) for a in ("x","y")}
        phi={a:num(creep_by_axis[a]) for a in mu};require(min(phi.values())>=0,"nonnegative creep")
        sec,g=prepare(column,t,grid,bar_distance_convention);out["geometry"]=g
        seen=set()
        for v in column["sections"]:
            id=str(v["id"]);require(id not in seen,"duplicate section id");seen.add(id)
            N=num(v["N_kN"],True);z=num(v["z_m"]);require(0<=z<=L,"section position")
            M={a:num(v["M"+a+"_kNm"]) for a in mu}
            row={"id":id,"z_m":z,"N_kN":N,"M0_kNm":M,"U":None}
            if N>g["hot_axial_total_kN"]+1e-6:
                row.update(status=EXCEEDED,reason="SUM_OF_MAXIMUM_COMPRESSIVE_RESISTANCES_EXCEEDED")
            else:
                axes={a:nominal(g,N,L,mu[a],(a,phi[a])) for a in mu};row["nominal"]=axes
                if any(v["eta"] is None for v in axes.values()):
                    row.update(status=UNRESOLVED,reason="OUTSIDE_NOMINAL_AMPLIFICATION_DOMAIN")
                else:
                    M2={a:M[a]*axes[a]["eta"] for a in mu};row["M2_kNm"]=M2
                    target=[N,M2["x"]/(g["h"]/2),M2["y"]/(g["b"]/2)]
                    u=utilization(sec,target) if calculate_U else {"applied":sec.check(target),"U":None,"U_interval":None}
                    row["section"]=u;state=u["applied"]["status"]
                    u["applied"]["governing_constraint"]=governing_constraint(sec,u["applied"])
                    diagnostic=u["applied"].get("unrestricted_equilibrium_diagnostic")
                    if diagnostic is not None:
                        diagnostic["governing_constraint"]=governing_constraint(sec,diagnostic)
                    row["status"]=WITHIN if state==PASS else EXCEEDED if state==FAIL else UNRESOLVED
                    # Section utilization based on FIXED amplified actions,
                    # plus separate nominal stability ratio at actual load.
                    if u["U"] is not None:
                        stab=max(v["N_over_Ncrit"] for v in axes.values())
                        row["U"]=max(stab,u["U"])
                        row["U_interval"]=[max(stab,v) for v in u["U_interval"]]
            out["sections"].append(row)
        require(bool(seen),"actual critical sections required")
        rows=out["sections"]
        # A certified failure at any entered section suffices even if
        # another section is unresolved; never declare PASS with unknown.
        out["status"]=EXCEEDED if any(r["status"]==EXCEEDED for r in rows) else UNRESOLVED if any(r["status"]==UNRESOLVED for r in rows) else WITHIN
        if all(r["U"] is not None for r in rows):
            out["U"]=max(r["U"] for r in rows);out["U_interval"]=[max(r["U_interval"][i] for r in rows) for i in (0,1)]
        out["U_definition"]="MAX_FIXED_AMPLIFIED_SECTION_ACTION_UTILIZATION_AND_N_OVER_NCR; NOT GLOBAL_NONLINEAR_PROPORTIONAL_CAPACITY"
    except (ValueError,TypeError,KeyError,ArithmeticError) as exc:
        out.update(status=UNRESOLVED,reason=str(exc),U=None)
    return out

def history(column,*,end_minute,required_minutes=None,**kw):
    require(type(end_minute) is int and 0<=end_minute<=column["fire_minutes"],"whole-minute horizon")
    if required_minutes is not None:require(type(required_minutes) is int and 0<=required_minutes<=end_minute,"whole-minute required R")
    rows=[];last=None;bracket=None;first_unknown=None;required=None
    for t in range(end_minute+1):
        row=assess(column,t,**kw);rows.append(row)
        if row["status"]==WITHIN:last=t
        elif row["status"]==EXCEEDED:
            if last is not None and last==t-1:bracket=[last,t]
            if required_minutes is not None and t<=required_minutes:required="MODEL_FAIL"
            break
        else:first_unknown=t;break
        if required_minutes==t:required="MODEL_WITHIN_AT_ALL_SAMPLED_MINUTES"
    return {"samples":rows,"last_within_whole_minute":last,"first_unresolved_minute":first_unknown,
        "model_limit_interval_min":bracket,"first_sampled_section_check_interval_min":bracket,
        "R_model_whole_minutes":None,"section_check_limit_is_not_global_collapse":True,
        "required_minutes":required_minutes,"required_check":required or "NOT_ESTABLISHED",
        "actual_t_R_minutes":None,"normative_claim":False,
        "status":"SAMPLED_SECTION_CHECK_LIMIT" if bracket else "NO_ESTABLISHED_LIMIT",
        "remaining_gates":GATES}
