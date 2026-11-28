"""SP-R11B targeted member histories, not section or physical admission."""
import copy
import math
import time
import numpy as np
from rc_fire.member import sp2026_r11a_history_member as m
from rc_fire.thermal.sp2026_heat import solve_sp2026_2d_heat,select_sp2026_snapshot
from rc_fire.mechanics import sp2026_r10c_quadrature as quad
from rc_fire.mechanics.sp2026_nominal_member import prepare_sp2026_design_section

VERSION="SP-R11B-extended-member-v1"

def fixture_spec(column,*,length,N,nodes,support,imperfection_ratio=1/1000,eccentricity_m=.005):
    """Explicit synthetic loads, not inferred from entered section forces.

    Biaxial UDL is defined as 8*N*e/L² and half that in the other axis.
    N*e is the pinned first-order midspan moment only, NOT a fixed-end
    moment or literal eccentric axial end force. Section entries set to
    zero as they do not represent this imposed distributed load diagram.
    """
    if support not in ("pinned","fixed"):raise ValueError("supported benchmark restraint required")
    c=copy.deepcopy(column);c["length_m"]=float(length)
    for s in c["sections"]:s.update(N_kN=float(N),Mx_kNm=0.,My_kNm=0.)
    z=np.linspace(0,length,nodes);d=[]
    for a in (length*imperfection_ratio,length*imperfection_ratio/2):
        for x in z:
            if support=="pinned":w=a*math.sin(math.pi*x/length);slope=a*math.pi/length*math.cos(math.pi*x/length)
            else:w=a*(1-math.cos(2*math.pi*x/length))/2;slope=a*math.pi/length*math.sin(2*math.pi*x/length)
            d.extend((w,slope))
    q=8*N*eccentricity_m/length**2
    spec={"load_mode":"explicit_sp2026_beam","z_m":z.tolist(),
       "left_support":{"x":support,"y":support},"right_support":{"x":support,"y":support},
       "axial_restraint_mode":"free_axial_expansion","N_kN":float(N),
       "fire_design_action_source":"synthetic constant precombined compressive action",
       "distributed_load_kNpm":[[q,q/2] for _ in z],"nodal_forces":[0.]*(4*nodes),
       "initial_imperfection":d,"imperfection_source":"explicit synthetic support-compatible profile L/1000 and L/2000",
       "transverse_action_source":"explicit biaxial UDL, not actual eccentric end loading",
       "entered_section_moments_reconciled":True,"longitudinal_thermal_mode":"explicit_uniform_full_length",
       "uniform_exposure_confirmed":True}
    return c,spec

def summarize(run,expected):
    accepted=[r for r in run["rows"] if r["status"]=="EQUILIBRATED_RESEARCH_MEMBER"]
    if tuple(r["time_minutes"] for r in accepted)!=tuple(expected[:len(accepted)]):
        raise ValueError("unexpected accepted time sequence")
    rows=[]
    for r in accepted:
        n=len(r["total_w_x_m"])
        a=r["algorithmic_geometric_margin"];u=r["frozen_unloading_geometric_margin"]
        rows.append({"t":r["time_minutes"],"mid_w_x_mm":1000*r["total_w_x_m"][n//2],
            "mid_w_y_mm":1000*r["total_w_y_m"][n//2],
            "algorithmic_eigenload_kN":a["frozen_tangent_eigenload_kN"] if a else None,
            "unloading_eigenload_kN":u["frozen_tangent_eigenload_kN"] if u else None,
            "algorithmic_margin_kN":a["additive_geometric_margin_kN"] if a else None,
            "unloading_margin_kN":u["additive_geometric_margin_kN"] if u else None,
            "max_Mx_kNm":max(abs(s["actions_kN_kNm"][1]) for s in r["stations"]),
            "max_My_kNm":max(abs(s["actions_kN_kNm"][2]) for s in r["stations"]),
            "max_damage":max(s["max_concrete_damage"] for s in r["stations"]),
            "max_boundary_damage":max(s["max_boundary_damage"] for s in r["stations"]),
            "max_steel_plastic_strain":max(s["max_steel_plastic_strain"] for s in r["stations"]),
            "max_steel_yield_ratio":max(s["steel_yield_ratio"] for s in r["stations"]),
            "max_axial_residual_kN":r["max_axial_residual_kN"],
            "scaled_free_residual_kNm":r["scaled_free_residual_kNm"],
            "assembly_calls":r["assembly_calls"]})
    stop=None if len(accepted)==len(expected) else run["rows"][-1]
    return {"status":run["status"],"accepted":rows,"stop":stop,
            "requested_end":expected[-1],"last_accepted":rows[-1]["t"] if rows else None,
            "physical_failure_proven":False,"actual_t_R_minutes":None}

def compare(a,b,expected,*,axis):
    X={r["t"]:r for r in a["accepted"]};Y={r["t"]:r for r in b["accepted"]}
    common=sorted(set(X)&set(Y))
    rows=[]
    for t in common:
        x,y=X[t],Y[t]
        dx=max(abs(x[k]-y[k]) for k in ("mid_w_x_mm","mid_w_y_mm"))
        rel=lambda k:abs(x[k]-y[k])/max(1.,abs(y[k])) if x[k] is not None and y[k] is not None else None
        rows.append({"t":t,"midspan_mm":dx,"algorithmic_eigenload_rel":rel("algorithmic_eigenload_kN"),
            "unloading_eigenload_rel":rel("unloading_eigenload_kN"),
            "steel_plastic_abs":abs(x["max_steel_plastic_strain"]-y["max_steel_plastic_strain"]),
            "sampled_moment_abs_kNm":max(abs(x[k]-y[k]) for k in ("max_Mx_kNm","max_My_kNm"))})
    complete=common==list(expected) and a["status"]==b["status"]=="DIAGNOSTIC_COMPLETE"
    maxima={k:(max(r[k] for r in rows) if all(r[k] is not None for r in rows) else None)
            for k in rows[0] if k!="t"} if rows else {}
    passed=complete and maxima["midspan_mm"]<=.1 and maxima["unloading_eigenload_rel"] is not None and maxima["unloading_eigenload_rel"]<=.05 and maxima["steel_plastic_abs"]<=5e-5
    # Algorithmic pencil depends on constitutive increment, so state /
    # unloading agreement is a diagnostic only on temporal refinement.
    strict=passed and maxima["algorithmic_eigenload_rel"] is not None and maxima["algorithmic_eigenload_rel"]<=.05
    return {"a":a["id"],"b":b["id"],"axis":axis,"complete":complete,
            "last_common":common[-1] if common else None,"maxima":maxima,
            "strict_research_pass":strict,"state_unloading_diagnostic_pass":passed,
            "rows":rows}

def campaign(column,boundary):
    c=copy.deepcopy(column);c["fire_minutes"]=180.
    coarse=[0.,2.,5.,10.,20.,30.,45.,60.,75.,90.,120.,150.,180.]
    fine=sorted(set(coarse+[(a+b)/2 for a,b in zip(coarse,coarse[1:])]))
    heat=solve_sp2026_2d_heat(c,boundary=boundary,cell_count_x=16,cell_count_y=16,
                             max_step_minutes=1.,sample_times_minutes=fine)
    fs={t:select_sp2026_snapshot(heat,t) for t in fine}
    # One fixed net-centroid integration geometry, intentionally modest
    # resolution for structural research only; not a qualified section.
    p=prepare_sp2026_design_section(c,fs[0.],grid=8)
    mesh=quad.build(p,[fs[t] for t in (2.,5.,10.,30.,60.,90.,180.)],
                    base_grid=8,max_level=1,delta_C=100.)
    runs=[]
    def run(id,L,N,n,support,times):
        cc,spec=fixture_spec(c,length=L,N=N,nodes=n,support=support)
        start=time.perf_counter()
        h=m.history(cc,spec,[fs[t] for t in times],grid=8,quadrature=mesh)
        runs.append({"id":id,"length_m":L,"N_kN":N,"nodes":n,"support":support,
                     "geometric_L_over_i":L/(float(cc["h_mm"])/1000/math.sqrt(12)),
                     "nominal_KL_over_i":L/(float(cc["h_mm"])/1000/math.sqrt(12))*(.5 if support=="fixed" else 1.),
                     "wall_s":time.perf_counter()-start,**summarize(h,times)})
    run("STOCKY50",3.,50.,3,"pinned",coarse)
    run("SLENDER500",12.,500.,5,"pinned",coarse)
    run("SLENDER1500",12.,1500.,5,"pinned",coarse)
    run("SLENDER1500_FIXED",12.,1500.,5,"fixed",coarse)
    run("SLENDER500_N9",12.,500.,9,"pinned",coarse)
    run("SLENDER500_FINE_TIME",12.,500.,5,"pinned",fine)
    def get(id):return next(r for r in runs if r["id"]==id)
    comparisons=[compare(get("SLENDER500"),get("SLENDER500_N9"),coarse,axis="longitudinal"),
                 compare(get("SLENDER500"),get("SLENDER500_FINE_TIME"),coarse,axis="time")]
    return {"version":VERSION,"runs":runs,"comparisons":comparisons,
       "quadrature":mesh.evidence(),"thermal_grid":16,"thermal_step_min":1.,
       "section_numerically_admitted":False,"global_physical_failure_proven":False,
       "actual_U_t":None,"actual_t_R_minutes":None,"normative_claim":False}
