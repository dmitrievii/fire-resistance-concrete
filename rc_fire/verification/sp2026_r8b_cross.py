"""SP-R8B cross-route evidence; identical actions, distinct temperature providers."""
from __future__ import annotations
import copy
import numpy as np
from rc_fire.thermal.sp2026_annex_k_field import build_annex_k_snapshot
from rc_fire.thermal.sp2026_heat import solve_sp2026_2d_heat,select_sp2026_snapshot
from rc_fire.mechanics.sp2026_nominal_member import prepare_sp2026_design_section
from rc_fire.mechanics.sp2026_coupled_first_limit import assess_coupled_sp5_nominal_at_time

def compare_annex_k_fvm_mechanics(column,member_spec,*,time_minutes,boundary,
                                 grid=12,heat_grid=16,step_minutes=1.,
                                 effective_creep_phi):
    t=float(time_minutes)
    c=copy.deepcopy(column)
    if not 0<t<=float(c["fire_minutes"]):
        raise ValueError("positive time inside declared duration required")
    k=build_annex_k_snapshot(c,t)
    if abs(float(boundary["moisture_mass_pct"])-
           k["annex_k_coefficients"]["Wc_mass_percent"])>1e-9:
        raise ValueError("K/FVM cross comparison requires equal moisture inputs")
    c["fire_minutes"]=t
    f=solve_sp2026_2d_heat(c,boundary=boundary,cell_count_x=heat_grid,
                          cell_count_y=heat_grid,max_step_minutes=step_minutes,
                          sample_times_minutes=[t])
    fields={"annex_K_clear":k,
            "annex_K_centre":build_annex_k_snapshot(c,t,bar_distance_convention="centre"),
            "FVM":select_sp2026_snapshot(f,t)}
    results={}
    for name,field in fields.items():
        try:
            p=prepare_sp2026_design_section(c,field,grid=grid)
            m=assess_coupled_sp5_nominal_at_time(c,field,member_spec,grid=grid,
                                               effective_creep_phi=effective_creep_phi)
            r=m["nominal_coupled_evidence"]
            results[name]={"status":m["status"],"thermal_method":field["thermal_method"],
                           "bar_steel_C":dict(zip(p.bar_ids,p.theta_s.tolist())),
                           "bar_concrete_C":dict(zip(p.bar_ids,p.theta_cb.tolist())),
                           "concrete_fibre_C":p.theta_c.tolist(),
                           "D_kNm2":r["nominal_2x2_D_kNm2"],
                           "Ncrit_kN":r["principal_Euler_Ncrit_kN"],
                           "M2_kNm":m["second_order_coupled_M2_kNm"],
                           "provenance":p.source}
        except (ValueError,ArithmeticError,np.linalg.LinAlgError) as exc:
            results[name]={"status":"UNRESOLVED","reason":str(exc)}
    def diff(a,b):
        aa,bb=results[a],results[b]
        if "D_kNm2" not in aa or "D_kNm2" not in bb:
            return {"resolved":False}
        return {"resolved":True,
                "max_bar_steel_delta_C":max(abs(v-bb["bar_steel_C"][k])
                                            for k,v in aa["bar_steel_C"].items()),
                "max_concrete_fibre_delta_C":float(np.max(np.abs(
                    np.array(aa["concrete_fibre_C"])-bb["concrete_fibre_C"]))),
                "Ncrit_difference_kN":(np.array(aa["Ncrit_kN"])-bb["Ncrit_kN"]).tolist(),
                "same_model_classification":aa["status"]==bb["status"]}
    return {"time_minutes":t,"routes":results,
            "K5_convention_sensitivity":diff("annex_K_clear","annex_K_centre"),
            "K_vs_FVM":diff("annex_K_clear","FVM"),
            "calibration_performed":False,"thermal_route_equivalence_proven":False,
            "actual_t_R_minutes":None,"normative_claim":False}
