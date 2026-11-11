"""R0.7 public calculation facade: one input, one fire-resistance assessment.

The installed advanced TKP heat/fibre modules calculate section equilibrium,
NOT the normative first loss of *member* carrying capacity. This API
deliberately does not manufacture an R(t) from Newton nonconvergence, an
isolated section strain, or the fact the user selected a required duration.

Numerical outputs include actual thermal/fibre histories and observed
transition intervals. The regulatory verdict is always NOT_ESTABLISHED until
a validated full-member fire ultimate limit state is integrated and qualified.
A later engine may add the verified member criterion without changing the UI.
"""
from __future__ import annotations

import copy
import math
from typing import Any

from multicolumn_r05.project_model import validate_column
from rc_fire.integration.r069d3 import evaluate_tkp_thermal_mechanical_history
from rc_fire.thermal.tkp_heat import reference_annex_a_boundary
from rc_fire.mechanics.action_capacity import WITHIN, EXCEEDED, UNKNOWN
from rc_fire.spalling.annex_l import evaluate_annex_l
from rc_fire.mechanics.sp2026_section import (
    evaluate_sp2026_section_at_time,SPSectionInputError)
from rc_fire.materials.sp2026_fire import (
    SPFireMaterialError,qualification_status as sp_material_qualification)
from rc_fire.thermal.sp2026_heat import (
    SPHeatError,solve_sp2026_2d_heat,select_sp2026_snapshot,
    sample_sp2026_temperature,standard_fire_sp,
    reference_sp2026_boundary)
from rc_fire.member.sp2026_member import (
    SP2026MemberInputError,evaluate_sp2026_member_at_time,
    scan_sp2026_member_history)
from rc_fire.mechanics.sp2026_stiffness_audit import audit_sp2026_concrete_stiffness
from rc_fire.member.sp2026_resistance import (
    evaluate_sp2026_member_resistance,scan_sp2026_resistance_time_history)
from rc_fire.mechanics.sp2026_section import prepare_sp2026_section,prepare_sp2026_full_nonlinear_section
from rc_fire.member.sp2026_mechanical_qualification import (
    verify_euler_critical_load,verify_biaxial_euler_coupling,
    verify_pdelta_midspan,
    verify_hot_section_jacobian,verify_condensed_hot_member_tangent,
    mechanical_uls_admissibility)

VERSION="R0.7-public-fire-workflow-v12-SP-R5-global-physical-gates"
SUPPORTED_R_MINUTES=(30,45,60,90,120,150,180)


class PublicFireInputError(ValueError):
    pass


def _positive(value,name):
    if isinstance(value,bool):
        raise PublicFireInputError(f"{name}: numeric input required")
    try: out=float(value)
    except (TypeError,ValueError) as exc:
        raise PublicFireInputError(f"{name}: numeric input required") from exc
    if not math.isfinite(out) or out<=0:
        raise PublicFireInputError(f"{name}: positive finite value required")
    return out


def _input_preflight(c:dict,*,required_minutes,steel_route,ductility_class,
                     moisture_mass_pct):
    if not isinstance(c,dict):
        raise PublicFireInputError("column dictionary required")
    required=_positive(required_minutes,"Rrequired")
    if required>120.:
        # Current search to 2 x Rrequired would exceed the existing 240-min
        # source/thermal calculator horizon. Do NOT silently shorten scan.
        raise PublicFireInputError(
            "The current integrated time history supports Rrequired<=120 min. "
            "R150/R180 require an extended validated time solver.")
    if steel_route not in ("hot_rolled","cold_worked"):
        raise PublicFireInputError(
            "Actual rebar production route (hot_rolled/cold_worked) is required")
    if ductility_class not in ("A","B","C"):
        raise PublicFireInputError("Actual reinforcing ductility A/B/C is required")
    try: w=float(moisture_mass_pct)
    except (TypeError,ValueError) as exc:
        raise PublicFireInputError("mass moisture percentage required") from exc
    if isinstance(moisture_mass_pct,bool) or not math.isfinite(w) or not 0<=w<=3.:
        raise PublicFireInputError(
            "Thermal heat-capacity moisture source is tabulated for 0..3%")
    if not isinstance(c.get("bars"),list) or len(c["bars"])<4:
        raise PublicFireInputError("at least 4 real reinforcement bars required")
    if not isinstance(c.get("sections"),list) or not c["sections"]:
        raise PublicFireInputError("at least one load section required")
    for s in c["sections"]:
        if any(s.get(k) is None for k in ("N_kN","Mx_kNm","My_kNm")):
            raise PublicFireInputError(
                "N, Mx, My are all required as ALREADY FIRE-DESIGN actions")
        if _positive(s["N_kN"],f"{s.get('id')}.N")<=0:
            raise PublicFireInputError("axial force must be positive")
        for k in ("Mx_kNm","My_kNm"):
            try: v=float(s[k])
            except (ValueError,TypeError) as exc:raise PublicFireInputError(
                k+": finite numeric moment required") from exc
            if not math.isfinite(v):raise PublicFireInputError(k+": finite moment required")
    if not (c.get("thermal_spec") or {}).get("concrete_family"):
        raise PublicFireInputError("concrete aggregate family required")
    if (c.get("thermal_spec") or {}).get("dry_density_kg_m3") is None:
        raise PublicFireInputError("actual dry density required")
    if not (c.get("material_spec") or {}).get("concrete",{}).get("consistency"):
        raise PublicFireInputError("concrete mix consistency required for SP 5.03.01 Table 6.3")
    if not (c.get("annex_l_spec") or {}).get("coarse_aggregate_volume_pct"):
        raise PublicFireInputError("coarse aggregate fraction required for material classification")
    # Respect all existing canonical input validation without carrying tests
    # into the public interface.
    issues=validate_column(c)
    if issues:
        raise PublicFireInputError("; ".join(issues))


def fire_assessment(column:dict,*,required_minutes:float,
    steel_route:str,ductility_class:str,moisture_mass_pct:float,
    grid:int=12,dt_minutes:float=5.,
    assess_member:bool=False)->dict[str,Any]:
    """Return numerical evidence AND independently qualified conclusion.

    Never mislabel an observed first-order strain-limit transition as
    full-member fire collapse. True t_R remains None if unqualified.
    """
    _input_preflight(column,required_minutes=required_minutes,
        steel_route=steel_route,ductility_class=ductility_class,
        moisture_mass_pct=moisture_mass_pct)
    source_meta=column.get("source_assumptions") or {}
    if (source_meta.get("steel_manufacturing_route",steel_route)!=steel_route or
        source_meta.get("steel_ductility_class",ductility_class)!=ductility_class):
        raise PublicFireInputError(
            "Steel processing/class mismatch between column source and "
            "TKP fire material selection")
    required=float(required_minutes)
    if type(grid) is not int or grid not in (8,12,16,24,32):
        raise PublicFireInputError("mesh grid must be one of 8/12/16/24/32")
    dt=_positive(dt_minutes,"time step")
    if dt<.25 or dt>10:
        raise PublicFireInputError("time step out of supported range [.25,10] min")
    # Exact multiple sampling ensures Rrequired itself is always a mechanical
    # sample, not interpolated between two unrelated Newton roots.
    horizon=required*2.
    step=required/5.
    c=copy.deepcopy(column)
    c["fire_minutes"]=horizon
    bound=reference_annex_a_boundary(moisture_mass_pct=float(moisture_mass_pct))
    history=evaluate_tkp_thermal_mechanical_history(c,
        boundary=bound,production_route=steel_route,
        ductility_class=ductility_class,
        cell_count=grid,fibre_grid=grid,
        max_step_minutes=dt,step_minutes=step,
        # Check independent sampled proportional-load factors 0..2.
        # This is section equilibrium evidence, NOT column capacity.
        max_factor=2.,factor_step=.5,max_bisection=0,
        include_member=bool(assess_member),
        refine_strain_transition=False,
        thermal_curve_step_minutes=5.)
    points=history.get("samples") or []
    exact=[p for p in points if abs(p["time_minutes"]-required)<1e-7]
    if len(exact)!=1:
        raise RuntimeError("Rrequired not evaluated at its exact fire time")
    at=exact[0]
    first=history.get("observed_section_strain_transition") or {}
    statuses=[p.get("reference_classification",UNKNOWN) for p in points]
    # Never pass an unknown/unstable point just because earlier times were
    # within strain limits. Equilibrium != normative carrying capacity.
    all_observed_within=all(s==WITHIN for s in statuses)
    any_unknown=any(s==UNKNOWN for s in statuses)
    any_exceeded=any(s==EXCEEDED for s in statuses)
    member=(at.get("member") or {}) if assess_member else {}
    spalling=evaluate_annex_l(column)
    source_meta=column.get("source_assumptions") or {}
    steel_confirmed=source_meta.get("steel_material_confirmed") is True
    blockers=[
       "FULL_COLUMN_FIRE_ULS_NOT_VALIDATED_TKP_4_3_4",
       "TEMPERATURE_AND_MECHANICAL_MESH_CONVERGENCE_NOT_ESTABLISHED",
       "SPALLING_ANNEX_L_OR_TKP_4_5_NOT_INDEPENDENTLY_CLOSED",
       "LONGITUDINAL_SUPPORT_RESTRAINT_AND_ACTION_PATH_MUST_BE_QUALIFIED",
       "OBSERVED_SECTION_STRAIN_IS_NOT_PHYSICAL_MEMBER_COLLAPSE",
    ]
    if not steel_confirmed:
        blockers.append("STEEL_S500_PRODUCTION_AND_DUCTILITY_NOT_DOCUMENTED")
    sand_source=(column.get("source_assumptions") or {}).get(
        "natural_sand","unspecified")
    if sand_source=="hidden_default_assumed_natural_unverified":
        blockers.append("NATURAL_SAND_IS_ASSUMED_NOT_DOCUMENTED")
    if spalling.get("status")!="calculated_method_scope":
        blockers.append("SP2026_ANNEX_L_SPALLING_NOT_RESOLVED")
    elif spalling.get("protection_required"):
        blockers.append("SP2026_ANNEX_L_SPALLING_PROTECTION_REQUIRED")
    if not spalling.get("moisture_method_qualified"):
        blockers.append("SP2026_ANNEX_L_MOISTURE_METHOD_REQUIRES_REVIEW")
    if at.get("status")!="FVM_TKP_FIBRES_NUMERICAL_DIAGNOSTIC":
        blockers.append("REQUIRED_TIME_SECTION_EQUILIBRIUM_NOT_SOLVED")
    if not assess_member or member.get("status")!="MEMBER_DIAGNOSTIC_EQUILIBRATED":
        blockers.append("FULL_MEMBER_EQUILIBRIUM_NOT_SOLVED")
    if any_unknown:blockers.append("UNKNOWN_SAMPLED_MECHANICAL_STATES")
    # Actual fixed-action strain demand is load-dependent, unlike the
    # thermal field and temperature-reduction material coefficients.
    def _strain_demand(row):
        if row.get("reference_classification") not in (WITHIN,EXCEEDED):
            return None
        reports=row.get("sections") or []
        if not reports:
            return None
        ratios=[]
        for report in reports:
            state=report.get("at_lambda_1") or {}
            if state.get("classification") not in (WITHIN,EXCEEDED):
                return None
            try: ratio=float(state.get("critical_ratio"))
            except (ValueError,TypeError):return None
            if not math.isfinite(ratio) or ratio<0:
                return None
            ratios.append(ratio)
        return 100.*max(ratios) if ratios else None
    thermal_rows=history.get("thermal_curve_samples") or []
    # SP-R.2: a SEPARATE source-controlled SP heat solve. Do not merely
    # relabel old TKP snapshots as SP. The SP properties come exclusively
    # from Appendix K.1 (A/B/D/E and mass moisture term K.1).
    # Boundary h/eps are explicitly a cross-standard comparison assumption.
    sp_preview={
        "status":"UNAVAILABLE","R_t_minutes":None,
        "regulatory_result":"NOT_ESTABLISHED",
        "source":"SP2026_TABLE9_10_SP5",
        "normative_claim":False}
    sp_heat=None
    sp_thermal_timeline=[]
    sp_heat_status="UNAVAILABLE"
    sp_heat_problem=None
    c_sp=copy.deepcopy(c)
    c_sp["fire_minutes"]=horizon
    # Preserve shared TKP section sample times for controlled comparison,
    # and independently record every 5 minutes for accurate SP plots.
    sp_samples=sorted(set([required,*(
        float(p["time_minutes"]) for p in points
        if 0<float(p["time_minutes"])<=horizon+1e-8
    ),*(
        5.*k for k in range(1,int(horizon/5.)+1)
        if 5.*k<=horizon+1e-8
    )]))
    try:
        sp_heat=solve_sp2026_2d_heat(
            c_sp,
            boundary=reference_sp2026_boundary(
                moisture_mass_pct=float(moisture_mass_pct)),
            cell_count_x=grid,cell_count_y=grid,
            max_step_minutes=dt,sample_times_minutes=sp_samples)
        sp_heat_status="SP2026_K1_FVM_EVALUATED_WITH_UNQUALIFIED_BOUNDARY"
        g=sp_heat["grid"]
        start_surface={
            face:[20.]*(g["ny"] if face in ("left","right") else g["nx"])
            for face in ("left","right","bottom","top")}
        sp_thermal_timeline=[{
            "minute":0., "gas_C":20.,"concrete_surface_C":20.,
            "concrete_centre_C":20.,
            "bars_C":{str(bar["id"]):20. for bar in c_sp.get("bars",[])},
            "grid_temperature_C":[[20.]*g["nx"] for _ in range(g["ny"])],
            "surface_temperature_C":start_surface,
            "temperature_source":"SP2026 2D FVM initial t=0"}]
        for time_value in sp_samples:
            view=select_sp2026_snapshot(sp_heat,time_value)
            snap=view["snapshot"]
            sp_thermal_timeline.append({
                "minute":time_value,
                "gas_C":standard_fire_sp(time_value),
                "concrete_surface_C":snap["boundary_max_C"],
                "concrete_centre_C":sample_sp2026_temperature(
                    view,c_sp["b_mm"]/2.,c_sp["h_mm"]/2.),
                "bars_C":{
                    str(bar["id"]):sample_sp2026_temperature(
                        view,bar["x_mm"],bar["y_mm"])
                    for bar in c_sp.get("bars",[])},
                "grid_temperature_C":snap["grid_temperature_C"],
                "surface_temperature_C":snap["surface_temperature_C"],
                "temperature_source":"SP2026 2D FVM solved snapshot"})
        hot=select_sp2026_snapshot(sp_heat,required)
        try:
            sp_preview=evaluate_sp2026_section_at_time(
                c_sp,hot,grid=grid)
            sp_preview["status"]="SP2026_K1_FVM_AND_FIBRES_NUMERICAL_DIAGNOSTIC"
        except (SPSectionInputError,SPFireMaterialError,
                ValueError,KeyError,TypeError) as exc:
            sp_preview={
                "status":"BLOCKED_SP2026_MECHANICAL_MATERIAL_OR_SOURCE",
                "source":"SP2026_TABLE9_10_SP5",
                "reason":str(exc),"R_t_minutes":None,
                "regulatory_result":"NOT_ESTABLISHED","normative_claim":False}
    except (SPHeatError,ValueError,TypeError,KeyError) as exc:
        # No fallback to TKP temperature for an SP-labelled mechanical
        # assessment. This is a real SP calculation blocker, not a PASS.
        sp_heat_problem=str(exc)
        sp_heat_status="BLOCKED_SP2026_THERMAL"
        sp_preview={
            "status":"BLOCKED_SP2026_THERMAL",
            "source":"SP2026_TABLE9_10_SP5",
            "reason":sp_heat_problem,"R_t_minutes":None,
            "regulatory_result":"NOT_ESTABLISHED","normative_claim":False}
    try:
        sp3_beta_audit=audit_sp2026_concrete_stiffness(c_sp)
        sp3_beta_problem=None
    except (ValueError,KeyError,TypeError) as exc:
        sp3_beta_audit=None
        sp3_beta_problem=str(exc)

    # SP-R.3: evaluate actual SP 2D fibre member only with a complete
    # explicit longitudinal load/support/imperfection/temperature contract.
    # A single N/Mx/My section from the public form is NOT a member model.
    stage3_spec=c_sp.get("member_spec") or {}
    sp3_status="SP_R3_EXPLICIT_MEMBER_INPUT_REQUIRED"
    sp3_at_required=None
    sp3_history=None
    sp3_blocker=None
    if stage3_spec.get("load_mode")=="explicit_sp2026_beam":
        if sp_heat is None:
            sp3_status="BLOCKED_SP_R3_NO_SOURCE_MATCHED_THERMAL_FIELD"
            sp3_blocker=sp_heat_problem or "SP-R2 heat unavailable"
        else:
            try:
                stage3_snapshot=select_sp2026_snapshot(sp_heat,required)
                sp3_at_required=evaluate_sp2026_member_at_time(
                    c_sp,stage3_snapshot,stage3_spec,grid=grid)
                sp3_status=sp3_at_required["status"]
                requested_times=stage3_spec.get("history_times_minutes")
                if requested_times is not None:
                    if (not isinstance(requested_times,(list,tuple)) or
                        not 1<=len(requested_times)<=24):
                        raise SP2026MemberInputError(
                            "explicit member history requires 1..24 times")
                    sp3_history=scan_sp2026_member_history(
                        c_sp,sp_heat,stage3_spec,requested_times,grid=grid)
            except (SP2026MemberInputError,SPHeatError,
                    ValueError,TypeError,KeyError) as exc:
                sp3_status="BLOCKED_SP_R3_MEMBER_INPUT_OR_SOLVER"
                sp3_blocker=str(exc)
                sp3_at_required=None
                sp3_history=None

    # SP-R.4 proportional fire-design action/resistance evidence; opt-in.
    # This is not a normative member capacity or first physical failure.
    sp4_status="SP_R4_NOT_REQUESTED"
    sp4_result=None
    sp4_blocker=None
    sp4_history=None
    sp4_history_status="SP_R4_HISTORY_NOT_REQUESTED"
    sp4_history_blocker=None
    if stage3_spec.get("resistance_scan_requested") is True:
        if stage3_spec.get("load_mode")!="explicit_sp2026_beam":
            sp4_status="BLOCKED_SP_R4_FULL_MEMBER_INPUT_REQUIRED"
            sp4_blocker="A complete SP-R3 member input is required before a load-path scan"
        elif sp_heat is None:
            sp4_status="BLOCKED_SP_R4_SP_HEAT_MISSING"
            sp4_blocker=sp_heat_problem or "SP-R2 temperature field unavailable"
        else:
            try:
                if stage3_spec.get("longitudinal_thermal_mode")!="explicit_uniform_full_length":
                    raise SP2026MemberInputError(
                        "public SP-R4 requires uniform full-length heating; "
                        "use standalone resistance API for explicit station fields")
                sp4_result=evaluate_sp2026_member_resistance(
                    c_sp,select_sp2026_snapshot(sp_heat,required),
                    stage3_spec,grid=grid,
                    first_factor=stage3_spec.get("resistance_scan_first_factor",.25),
                    step=stage3_spec.get("resistance_scan_step",.25),
                    max_factor=stage3_spec.get("resistance_scan_max_factor",2.),
                    relative_tolerance=.005,max_refinements=12)
                sp4_status=sp4_result["status"]
                if stage3_spec.get("resistance_time_history_requested") is True:
                    try:
                        times=stage3_spec.get("history_times_minutes")
                        if not isinstance(times,(list,tuple)) or not 1<=len(times)<=12:
                            raise SP2026MemberInputError(
                                "SP-R4 requires 1..12 explicit stored heat times for history")
                        sp4_history=scan_sp2026_resistance_time_history(
                            c_sp,sp_heat,stage3_spec,times,grid=grid,
                            first_factor=stage3_spec.get("resistance_scan_first_factor",.25),
                            step=stage3_spec.get("resistance_scan_step",.25),
                            max_factor=stage3_spec.get("resistance_scan_max_factor",2.),
                            relative_tolerance=.005,max_refinements=12)
                        sp4_history_status=sp4_history["status"]
                    except (SP2026MemberInputError,SPHeatError,
                            ValueError,TypeError,ArithmeticError,KeyError) as exc:
                        sp4_history_status="BLOCKED_SP_R4_TIME_HISTORY"
                        sp4_history_blocker=type(exc).__name__+": "+str(exc)
            except (SP2026MemberInputError,SPHeatError,
                    ValueError,TypeError,ArithmeticError,KeyError) as exc:
                sp4_status="BLOCKED_SP_R4_RESISTANCE_SCAN"
                sp4_blocker=type(exc).__name__+": "+str(exc)
                sp4_result=None

    # SP-R4Q: external analytical checks verify the numerical FE kernel,
    # not the physical hot RC law or global first physical failure.
    sp4q_evidence=None
    sp4q_status="SP_R4Q_MEMBER_MODEL_NOT_REQUESTED"
    sp4q_blocker=None
    if stage3_spec.get("load_mode")=="explicit_sp2026_beam":
        if sp_heat is None:
            sp4q_status="BLOCKED_SP_R4Q_SP_HEAT_MISSING"
            sp4q_blocker=sp_heat_problem or "source-matched SP heat unavailable"
        else:
            try:
                chosen_source=(
                    prepare_sp2026_full_nonlinear_section
                    if stage3_spec.get("constitutive_model")==(
                        "SP5_6_1_5_2_FULL_HOT_EXPLORATORY")
                    else prepare_sp2026_section)
                source_section=chosen_source(
                    c_sp,select_sp2026_snapshot(sp_heat,required),grid=grid)
                numeric={
                    "euler":verify_euler_critical_load(
                        left_kind="pinned",right_kind="pinned",node_count=17),
                    "coupled_euler":verify_biaxial_euler_coupling(node_count=17),
                    "pdelta":verify_pdelta_midspan(node_count=17),
                    "jacobian":verify_hot_section_jacobian(source_section),
                    "condensed_tangent":verify_condensed_hot_member_tangent(
                        source_section,
                        stage3_spec["N_kN"])}
                sp4q_evidence=mechanical_uls_admissibility(
                    c_sp,stage3_spec,numeric_evidence=numeric)
                sp4q_evidence["numerical_benchmarks"]=numeric
                sp4q_status=sp4q_evidence["status"]
            except Exception as exc:
                # No numerical or normative PASS if a benchmark is invalid.
                sp4q_evidence=mechanical_uls_admissibility(c_sp,stage3_spec)
                sp4q_status="BLOCKED_SP_R4Q_NUMERICAL_VERIFICATION"
                sp4q_blocker=type(exc).__name__+": "+str(exc)


    # SP-R5 source full law: the hot material history remains unqualified.
    sp5_full_model_status="NOT_REQUESTED"
    sp5_full_model_blocker=None
    sp5_full_model_evidence=None
    sp5_global_evidence=None
    if stage3_spec.get("load_mode")=="explicit_sp2026_beam":
        requested_mode=stage3_spec.get("constitutive_model",
                                      "SP5_6_1_5_4_SECTION_CHECK")
        if requested_mode=="SP5_6_1_5_2_FULL_HOT_EXPLORATORY":
            if sp_heat is None:
                sp5_full_model_status="BLOCKED_SOURCE_SP_HEAT_MISSING"
                sp5_full_model_blocker=sp_heat_problem or "SP-R2 heat unavailable"
            else:
                try:
                    p_full=prepare_sp2026_full_nonlinear_section(
                        c_sp,select_sp2026_snapshot(sp_heat,required),grid=grid)
                    sp5_full_model_evidence={
                        "model":p_full.sp_constitutive_mode,
                        "full_SP5_source_equation":"6.13-6.16",
                        "source_SP2026_temperature_factors":"Table 9 beta and k_c",
                        "sampled_temperature_material_parameters":
                            p_full.sp_full_nonlinear_material_evidence,
                        "hot_peak_ultimate_strain_and_creep_qualified":False,
                        "normative_claim":False}
                    sp5_full_model_status="RESEARCH_FULL_EQUATION_EVALUATED_HOT_STRAIN_UNQUALIFIED"
                except (SPSectionInputError,SPFireMaterialError,
                        ValueError,TypeError,KeyError) as exc:
                    sp5_full_model_status="BLOCKED_FULL_HOT_CONSTITUTIVE_DOMAIN"
                    sp5_full_model_blocker=type(exc).__name__+": "+str(exc)
        else:
            sp5_full_model_status="SP5_6_1_5_4_SECTION_BRANCH_RETAINED"
        if sp4_result is not None:
            sp5_global_evidence=(sp4_result.get(
                "at_declared_design_actions") or {}).get(
                "global_stability_evidence")

    thermal_timeline=[{
        "minute":row["time_minutes"],
        "gas_C":row.get("T_gas_C"),
        "concrete_surface_C":row.get("T_concrete_boundary_max_C"),
        "concrete_centre_C":row.get("T_concrete_center_C"),
        "bars_C":row.get("T_reinforcement_C") or {},
        "grid_temperature_C":row.get("grid_temperature_C"),
        "surface_temperature_C":row.get("surface_temperature_C"),
        "temperature_source":row.get("temperature_source"),
    } for row in thermal_rows]
    report={
      "release":VERSION,"status":"NUMERICAL_CALCULATION_COMPLETE",
      "required_rating_minutes":required,
      "calculated_member_failure_time_minutes":None,
      "R_t_minutes":None,
      "normative_R_at_least_required":None,
      "regulatory_result":"NOT_ESTABLISHED",
      "rating_matches_requirement":None,
      "observed_strain_limit_transition":first.get(
            "observed_within_to_exceeded_intervals",[]),
      "first_observed_section_strain_exceedance_minutes":first.get(
            "first_observed_strain_exceedance_minutes"),
      "numerical_section_at_required_time":at.get("reference_classification",UNKNOWN),
      "numerical_section_status_at_required_time":at.get("status"),
      "material_strength_at_required_time":at.get("material_strength_retention"),
      "design_action_strain_demand_pct_at_required_time":_strain_demand(at),
      "design_action_strain_demand_interpretation":
          "Load-dependent ratio of maximum calculated mechanical fibre strain "
          "to source material strain limit; NOT structural load utilization, "
          "strength capacity or verified failure time",
      "sampled_section_reserve_at_required_time":at.get("sampled_section_load_evidence"),
      "section_interaction_utilisation_bound_at_required_time":
          at.get("section_utilization_bound"),
      "definite_section_overload_at_required_time":
          (at.get("section_utilization_bound") or {}).get(
              "definite_section_overload_in_source_model",False),
      "utilisation_basis":
          "Rigorous minimum possible N-Mx-My section utilization from a "
          "stress-relaxed interaction envelope; actual section/member "
          "utilization remains unknown. Over 100% is a proven overload "
          "within source strength envelopes.",
      "capacity_scope":"Only a first-order section under discrete N-Mx-My scaling; "
                       "not verified whole-column capacity or fire-resistance R(t)",
      "numerical_section_all_times_within":all_observed_within,
      "numerical_some_times_unknown":any_unknown,
      "numerical_some_times_exceeded":any_exceeded,
      "required_time_temperatures":{
          "gas_C":at.get("T_gas_C"),
          "concrete_surface_max_C":at.get("T_concrete_boundary_max_C"),
          "concrete_centre_C":at.get("T_concrete_center_C"),
          "bars_C":at.get("T_reinforcement_C")},
      "energy_balance":history.get("thermal_energy_balance"),
      "sp2026_stage1_at_required_time":sp_preview,
      "sp2026_stage1_material_qualification":sp_material_qualification(),
      "sp2026_stage2_heat_status":sp_heat_status,
      "sp2026_stage2_heat_horizon_minutes":horizon,
      "sp2026_stage2_heat_blocker":sp_heat_problem,
      "sp2026_stage2_thermal_timeline":sp_thermal_timeline,
      "sp2026_stage2_thermal_grid":sp_heat.get("grid") if sp_heat else None,
      "sp2026_stage2_heat_energy_balance":(
          sp_heat.get("energy_balance") if sp_heat else None),
      "sp2026_stage2_thermal_source":(
          sp_heat.get("governing_source") if sp_heat else None),
      "sp2026_stage2_boundary_source":(
          sp_heat.get("external_boundary_source") if sp_heat else None),
      "sp2026_stage2_moisture_model":(
          sp_heat.get("moisture_model") if sp_heat else None),
      "sp2026_stage3_beta_stiffness_audit":sp3_beta_audit,
      "sp2026_stage3_beta_stiffness_audit_blocker":sp3_beta_problem,
      "sp2026_stage3_member_status":sp3_status,
      "sp2026_stage3_member_blocker":sp3_blocker,
      "sp2026_stage3_member_at_required_time":sp3_at_required,
      "sp2026_stage3_member_history":sp3_history,
      "sp2026_stage4_resistance_scan_status":sp4_status,
      "sp2026_stage4_resistance_scan_at_required_time":sp4_result,
      "sp2026_stage4_resistance_scan_blocker":sp4_blocker,
      "sp2026_stage4_resistance_time_history_status":sp4_history_status,
      "sp2026_stage4_resistance_time_history":sp4_history,
      "sp2026_stage4_resistance_time_history_blocker":sp4_history_blocker,
      "sp2026_stage4q_mechanical_qualification_status":sp4q_status,
      "sp2026_stage4q_mechanical_qualification":sp4q_evidence,
      "sp2026_stage4q_mechanical_qualification_blocker":sp4q_blocker,
      "sp2026_stage4q_mechanical_uls_qualified":False,
      "sp2026_stage5_constitutive_status":sp5_full_model_status,
      "sp2026_stage5_constitutive_blocker":sp5_full_model_blocker,
      "sp2026_stage5_constitutive_evidence":sp5_full_model_evidence,
      "sp2026_stage5_global_stability_at_design_actions":sp5_global_evidence,
      "sp2026_stage5_first_physical_failure_qualified":False,
      "sp2026_stage5_actual_t_R_minutes":None,
      "sp2026_stage4_actual_member_utilisation_U_t":None,
      "sp2026_calculated_R_t_status":(
          "NOT_ESTABLISHED_SP2026_MEMBER_ULS_QUALIFICATION_PENDING"
          if sp3_at_required else "NOT_ESTABLISHED_SP2026_MEMBER_INPUT_REQUIRED"),
      "spalling_annex_L":spalling,
      "natural_sand_assumed":sand_source=="hidden_default_assumed_natural_unverified",
      "natural_sand_selection_provenance":sand_source,
      "thermal_timeline":thermal_timeline,
      "thermal_grid":history.get("thermal_grid"),
      "thermal_timeline_independent_of_mechanics":bool(thermal_timeline),
      "timeline":[{
          "minute":p["time_minutes"],
          "design_action_strain_demand_pct":_strain_demand(p),
          "section_minimum_possible_utilisation_pct":(
              (p.get("section_utilization_bound") or {}).get(
                  "section_utilization_lower_bound_pct")),
          "section_stress_envelope_overload":(
              (p.get("section_utilization_bound") or {}).get(
                  "definite_section_overload_in_source_model",False)),
          "N_kN":(column.get("sections") or [{}])[0].get("N_kN"),
          "Mx_kNm":(column.get("sections") or [{}])[0].get("Mx_kNm"),
          "My_kNm":(column.get("sections") or [{}])[0].get("My_kNm"),
          "gas_C":p.get("T_gas_C"),
          "concrete_surface_C":p.get("T_concrete_boundary_max_C"),
          "concrete_centre_C":p.get("T_concrete_center_C"),
          "bars_C":p.get("T_reinforcement_C") or {},
          "concrete_retained_uniaxial_pct":(
              (p.get("material_strength_retention") or {}).get(
                  "concrete_uniaxial_strength_retained_pct")),
          "steel_retained_yield_pct":(
              (p.get("material_strength_retention") or {}).get(
                  "steel_yield_strength_retained_pct")),
          "max_checked_section_load_factor":(
              (p.get("sampled_section_load_evidence") or {}).get(
                  "max_consecutively_checked_load_factor")),
          "discrete_checked_section_extra_load_pct":(
              (p.get("sampled_section_load_evidence") or {}).get(
                  "discrete_extra_load_tested_pct")),
          "ratio_to_max_checked_load_pct_not_utilization":(
              (p.get("sampled_section_load_evidence") or {}).get(
                  "ratio_to_max_checked_load_pct")),
          "section_classification":p.get("reference_classification"),
          "section_solver_status":p.get("status"),
          "member_status":(p.get("member") or {}).get("status")}
          for p in points],
      "steel_material_confirmed":steel_confirmed,
      "steel_material_provenance":source_meta.get("steel_selection_provenance",
          "unrecorded_unverified"),
      "numerical_scenario_only":not steel_confirmed,
      "materials":{
          "concrete":column.get("concrete"),
          "density_kg_m3":column.get("thermal_spec",{}).get("dry_density_kg_m3"),
          "aggregate":column.get("thermal_spec",{}).get("concrete_family"),
          "steel_grade":column.get("steel_grade"),
          "steel_route":steel_route,
          "steel_ductility":ductility_class,
          "moisture_mass_pct":float(moisture_mass_pct)},
      "fire_design_actions":[
          {k:s.get(k) for k in ("id","z_m","N_kN","Mx_kNm","My_kNm")}
          for s in column["sections"]],
      "method_sources":[
          "ТКП EN 1992-1-2-2009 §3.2, §3.3, §4.3 and Belarus National Annex",
          "СП 2.02.05-2026 standard fire, formula (3)",
          "СП 5.03.01-2020 room-temperature material catalog"],
      "remaining_normative_blockers":blockers,
      "full_internal_audit":history,
    }
    return report
