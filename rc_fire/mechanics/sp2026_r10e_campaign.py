"""R10E targeted thermal/mechanical refinement with explicit admission gates."""
import copy
from rc_fire.mechanics import sp2026_r10a_history_section as h
from rc_fire.mechanics import sp2026_r10b_steel_history as st
from rc_fire.mechanics import sp2026_r9g_hot_domain as hot
from rc_fire.mechanics import sp2026_r10c_quadrature as q
from rc_fire.mechanics import sp2026_r10d_front as d
from rc_fire.mechanics import sp2026_r10e_cutcell as cut
from rc_fire.mechanics.sp2026_nominal_member import prepare_sp2026_design_section
from rc_fire.thermal.sp2026_heat import solve_sp2026_2d_heat,select_sp2026_snapshot

def admission(*,thermal_spatial,thermal_temporal,mechanical_spatial,mechanical_temporal,
              full_duration,front_evidence,material_qualified=False,global_model_qualified=False):
    gates={"thermal_spatial":thermal_spatial,"thermal_temporal":thermal_temporal,
           "mechanical_spatial":mechanical_spatial,"mechanical_temporal":mechanical_temporal,
           "full_duration":full_duration,"front_evidence":front_evidence,
           "material_qualified":material_qualified,"global_model_qualified":global_model_qualified}
    if any(type(x)!=bool for x in gates.values()):raise ValueError("explicit Boolean evidence required")
    numerical=all(gates[k] for k in ("thermal_spatial","thermal_temporal","mechanical_spatial","mechanical_temporal","full_duration","front_evidence"))
    return {"gates":gates,"numerical_section_admitted":numerical,
            "member_solver_admitted":numerical and material_qualified and global_model_qualified,
            "unresolved":[k for k,v in gates.items() if not v],"actual_t_R_minutes":None}

def campaign(column,boundary):
    c=copy.deepcopy(column);c["fire_minutes"]=90.
    ts=[float(i) for i in range(11)]+[float(t) for t in range(15,91,5)]
    def heat(n,dt):
        r=solve_sp2026_2d_heat(c,boundary=boundary,cell_count_x=n,cell_count_y=n,
                              max_step_minutes=dt,sample_times_minutes=ts)
        return [select_sp2026_snapshot(r,t) for t in ts]
    f64=heat(64,.5);f80=heat(80,.5);f80dt=heat(80,.25)
    p=prepare_sp2026_design_section(c,f64[0],grid=8)
    A=(50.,1.,1.)
    def run(id,fields,mesh):
        r=h.run_history(c,fields,A,grid=8,mode=hot.MODIFIED_AT,steel_mode=st.PLASTIC,
                        steel_strain_limit=.02,quadrature=mesh)
        return {"id":id,"quadrature":mesh.evidence(),**r}
    idx=[ts.index(t) for t in (1.,3.,5.,10.,30.,60.,90.)]
    coarse=q.build(p,[f80[i] for i in idx],max_level=2,delta_C=100.)
    pilot=run("PILOT80_A2",f80,coarse)
    if pilot["status"]!="DIAGNOSTIC_COMPLETE":
        return {"status":"BLOCKED_PILOT","runs":[pilot],"comparisons":[],
                "admission":admission(thermal_spatial=False,thermal_temporal=False,mechanical_spatial=False,
                      mechanical_temporal=False,full_duration=False,front_evidence=False),
                "actual_t_R_minutes":None,"normative_claim":False}
    seed=h.make_initial(c,f80[0],grid=8,mode=hot.MODIFIED_AT,length_mm=50.,Gwork_N_mm=5.,
                        yield_fraction=.4,strength_basis="SP5_ACCIDENTAL_FCD").concrete[0]
    # Keep cuts at every early checkpoint, then every 10 minutes plus
    # intermediate 15/45/75. Fixed polygon overlay, no moving weights.
    selected=tuple(t for t in ts if t!=0.)
    probe=cut.make_probe(seed,f80,pilot["rows"],width=p.b_m,height=p.h_m,selected_times=selected)
    medium=q.build(p,[f80[i] for i in idx],max_level=3,delta_C=60.)
    m2=cut.build(coarse,probe,selected_times=selected)
    m3=cut.build(medium,probe,selected_times=selected)
    a=run("T64_CUT3",f64,m3);b=run("T80_CUT3",f80,m3)
    e=run("T80_CUT2",f80,m2);f=run("T80_DT025_CUT3",f80dt,m3)
    base=run("T80_CENTROID3_SHORT",f80[:11],medium)
    bp={**b,"id":"T80_CUT3_SHORT","rows":b["rows"][:11],
        "status":"DIAGNOSTIC_COMPLETE" if len(b["rows"])>=11 and b["rows"][10]["status"]=="EQUILIBRATED_RESEARCH_SECTION" else "UNRESOLVED_HISTORY_STOP"}
    thermal=d.thermal_comparison(c,f64,f80,m3)
    dt=d.thermal_comparison(c,f80,f80dt,m3)
    comps=[d.front_comparison(a,b,90.),d.front_comparison(e,b,90.),
           d.front_comparison(b,f,90.),d.front_comparison(base,bp,10.)]
    gates=admission(thermal_spatial=thermal["research_temperature_pass"] and comps[0]["joint_section_research_pass"],
          thermal_temporal=dt["research_temperature_pass"] and comps[2]["joint_section_research_pass"],
          mechanical_spatial=comps[1]["joint_section_research_pass"],
          # Mechanical observation schedule unchanged; no false new temporal qualification.
          mechanical_temporal=False,
          full_duration=all(x["status"]=="DIAGNOSTIC_COMPLETE" for x in (a,b,e,f)),
          # Finite corner sampling and bar fallback cannot prove front closure.
          front_evidence=False)
    return {"status":"DIAGNOSTIC_COMPLETE","runs":[pilot,a,b,e,f,base],"comparisons":comps,
            "thermal_spatial":thermal,"thermal_temporal":dt,"pilot_probe_count":probe.cache_info().currsize,
            "admission":gates,"normative_claim":False,"actual_t_R_minutes":None}
