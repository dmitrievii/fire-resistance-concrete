"""SP-R7 source-specific acceptance gates: thermal, creep, experiments.

These are executable reproducibility checks, NOT an engineering stamp.
All performed comparisons keep explicit model boundary and provenance;
no ad-hoc tuning of material constants to experiments is permitted.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import numpy as np

from rc_fire.thermal.sp2026_heat import (
    solve_sp2026_2d_heat,select_sp2026_snapshot,
    sample_sp2026_temperature,SPHeatError)
from rc_fire.mechanics.sp2026_nominal_member import (
    effective_creep_coefficient_sp5,SP5NominalMemberError)

VERSION="SP-R7-source-qualification-gates-v1"

def _f(x,name,positive=False):
    if isinstance(x,bool):
        raise ValueError(name+" must be finite")
    try:val=float(x)
    except (ValueError,TypeError) as exc:
        raise ValueError(name+" must be finite") from exc
    if not math.isfinite(val) or (positive and val<=0):
        raise ValueError(name+" must be positive finite")
    return val


def audit_sp2026_heat_mesh_and_time(column, boundary, *,
                                    time_minutes,coarse_grid=6,
                                    fine_grid=8,coarse_step_minutes=2.,
                                    fine_step_minutes=1.,
                                    numerical_temperature_tolerance_C=6.):
    """Independent (mesh and timestep) tests on same SP2026 boundary.

    THREE full solves:
      mesh: coarse grid coarse dt  VS fine grid coarse dt;
      time: fine grid coarse dt VS fine grid fine dt.
    Compare at exactly same physical locations and timestamp. Do not
    confuse small numerical differences with source calibration of
    h/epsilon, moisture/transport, spalling or Annex Zh temperatures.
    """
    t=_f(time_minutes,"time",positive=True)
    tol=_f(numerical_temperature_tolerance_C,"temperature tolerance",positive=True)
    if (type(coarse_grid) is not int or type(fine_grid) is not int or
        not 4<=coarse_grid<fine_grid<=80):
        raise ValueError("4<=coarse_grid<fine_grid<=80 required")
    coarse_dt=_f(coarse_step_minutes,"coarse step",positive=True)
    fine_dt=_f(fine_step_minutes,"fine step",positive=True)
    if not fine_dt<coarse_dt or coarse_dt>10.:
        raise ValueError("fine dt must be less than coarse dt <= 10 min")
    b=_f(column["b_mm"],"width",positive=True)
    h=_f(column["h_mm"],"height",positive=True)
    series={}
    for name,g,dt in (
        ("coarse",coarse_grid,coarse_dt),
        ("fine_grid",fine_grid,coarse_dt),
        ("fine_time",fine_grid,fine_dt)):
        cc={**column,"fire_minutes":t}
        solved=solve_sp2026_2d_heat(
            cc,boundary=boundary,cell_count_x=g,cell_count_y=g,
            max_step_minutes=dt,sample_times_minutes=[t])
        s=select_sp2026_snapshot(solved,t)
        points={
            "centre":(b/2.,h/2.),
            "quarter_LL":(b/4.,h/4.),
            "quarter_UR":(3*b/4.,3*h/4.),
            "left_mid":(0.,h/2.),
            "right_mid":(b,h/2.),
            "top_mid":(b/2.,h),
            "bottom_mid":(b/2.,0.)}
        temps={name:sample_sp2026_temperature(s,*xy)
               for name,xy in points.items()}
        # The exact FE bar inventory also has physically useful
        # temperature sampling locations.
        for bar in column.get("bars") or []:
            label="bar_"+str(bar.get("id","?"))
            if label in temps:raise ValueError("duplicate test location")
            temps[label]=sample_sp2026_temperature(
                s,_f(bar["x_mm"],"bar x"),_f(bar["y_mm"],"bar y"))
        series[name]={
            "grid_n":g,"step_minutes":dt,
            "sample_locations_C":temps,
            "energy_conservation":solved["energy_balance"],
            "boundary_source":solved["external_boundary_source"],
            "thermal_method":solved["thermal_method"],
            "retained_full_grid_in_report":False}
    keys=list(series["coarse"]["sample_locations_C"])
    def comparison(a,b):
        differences={k:abs(series[a]["sample_locations_C"][k]-
                             series[b]["sample_locations_C"][k])
                     for k in keys}
        return {"pair":[a,b],"differences_by_location_C":differences,
                "max_difference_C":float(max(differences.values())),
                "numerical_tolerance_C":tol,
                "numerical_change_within_tolerance":bool(
                    max(differences.values())<=tol)}
    mesh=comparison("coarse","fine_grid")
    time=comparison("fine_grid","fine_time")
    converged=(mesh["numerical_change_within_tolerance"] and
               time["numerical_change_within_tolerance"])
    source=boundary.get("environment_source")
    comparison_boundary=("COMPARISON" in str(source).upper() or
                         "TKP" in str(source).upper())
    return {
        "version":VERSION,
        "status":("NUMERICALLY_STABLE_WITHIN_USER_TOLERANCE"
                  if converged else "MESH_OR_TIME_SENSITIVITY_NOT_CLOSED"),
        "time_minutes":t,"same_specified_boundary_across_runs":True,
        "run_evidence":series,"mesh_comparison":mesh,"time_comparison":time,
        "numerical_grid_time_study_satisfied":converged,
        "boundary_is_comparison_assumption":comparison_boundary,
        "SP2026_external_boundary_normative_qualified":False,
        "moisture_spalling_and_longitudinal_heat_qualified":False,
        "SP_Annex_Zh_pointwise_reference_compared":False,
        "thermal_regulatory_qualification":False,
        "R_t_minutes":None,"normative_claim":False}


def audit_effective_creep_source(*,phi_infty,
                                  first_order_M0Eqp_x_kNm,
                                  first_order_M0Ed_x_kNm,
                                  first_order_M0Eqp_y_kNm,
                                  first_order_M0Ed_y_kNm,
                                  phi_temperature_history_source=None):
    """Compute SP5 Eq8.64 separately for two actual bending axes.

    The source 6.1.4.3 time-dependent isotherm ambient creep does not
    by itself specify the hot transient creep strain evolution.
    """
    axes={}
    for label,qp,design in (
        ("x",first_order_M0Eqp_x_kNm,first_order_M0Ed_x_kNm),
        ("y",first_order_M0Eqp_y_kNm,first_order_M0Ed_y_kNm)):
        axes[label]=effective_creep_coefficient_sp5(
            phi_infty=phi_infty,M0Eqp_kNm=qp,M0Ed_kNm=design)
    return {
        "version":VERSION,
        "source":"SP5 §8.1.6.5 Eq8.64 and §6.1.4.3",
        "axes":axes,
        "hot_creep_history_source":phi_temperature_history_source,
        "hot_concrete_transient_creep_qualified":False,
        "same_first_order_section_and_true_load_combinations_must_be_verified":True,
        "zero_creep_not_assumed_by_software":True,
        "regulatory_claim":False}


def audit_fire_column_experiment_admissibility(catalog):
    """Machine-auditable readiness, no fabricated model predictions.

    Reference I3,T3,II10 in existing catalog: observations from Lie
    and Woolerton credited by Kodur et al. (2009), not measurements
    performed by this calculator, and certainly not the same furnace
    curve and constitutive SP5 material.
    """
    if not isinstance(catalog,dict) or not isinstance(catalog.get("cases"),list):
        raise ValueError("source test catalog with cases required")
    rows=[]
    for case in catalog["cases"]:
        fields=["id","cross_section_mm","length_m",
            "longitudinal_bars","concrete_compressive_strength_reported_MPa",
            "steel_yield_strength_reported_MPa","applied_axial_load_kN",
            "fire_exposure","observed_fire_failure_time_min"]
        missing=[x for x in fields if case.get(x) is None]
        blockers=[]
        if case.get("fire_exposure")!="SP2026_STANDARD_FORMULA_3":
            blockers.append("FURNACE_CURVE_NOT_SP2026_STANDARD_FIRE_EQUIVALENCE_PROVED")
        if case.get("steel_yield_strength_reported_MPa")!=500:
            blockers.append("ACTUAL_STEEL_YIELD_NOT_SP5_S500_CATALOG_MATERIAL")
        if not case.get("original_primary_test_geometry_confirmed"):
            blockers.append("PRIMARY_BAR_CENTRES_STIRRUP_COVER_AND_SUPPORTS_UNVERIFIED")
        if not case.get("hot_measured_material_history_qualified"):
            blockers.append("HIGH_TEMPERATURE_CONCRETE_STEEL_CREEP_UNVERIFIED")
        if not case.get("actual_thermal_boundary_history_confirmed"):
            blockers.append("TEST_FURNACE_GAS_SURFACE_HEAT_FLUX_NOT_VERIFIED")
        if not case.get("source_matched_independent_prediction"):
            blockers.append("NO_SOURCE_MATCHED_ENGINE_PREDICTION_PERFORMED")
        ready=not missing and not blockers
        rows.append({
            "id":case.get("id"),
            "observed_failure_time_min":case.get("observed_fire_failure_time_min"),
            "original_reported_reference":
                catalog.get("reference",{}).get("doi"),
            "missing_required_fields":missing,
            "admissibility_blockers":blockers,
            "validation_execution_status":(
                "INPUTS_ADMISSIBLE_FOR_UNCALIBRATED_COMPARISON"
                if ready else "NOT_ADMISSIBLE_FOR_SOURCE_MATCHED_SP_FIRE_VALIDATION"),
            "model_prediction_min":None,
            "error_min":None,
            "measured_vs_model_compared":False,
            "normative_claim":False})
    return {
        "version":VERSION,
        "status":"EXPERIMENT_CATALOG_ADMISSIBILITY_ONLY",
        "cases":rows,"source_case_count":len(rows),
        "source_matched_cases_ready":sum(
            x["validation_execution_status"]==
            "INPUTS_ADMISSIBLE_FOR_UNCALIBRATED_COMPARISON" for x in rows),
        "validated_model_failure_predictions":0,
        "cannot_relabel_secondary_model_results_as_our_prediction":True,
        "physical_first_fire_failure_validated":False,
        "regulatory_claim":False}


def load_existing_fire_column_catalog(path=None):
    if path is None:
        path=Path(__file__).resolve().parents[2] / (
            "validation/sp_r4q_fire_column_reference_cases.json")
    with open(path,encoding="utf-8") as f:
        catalog=json.load(f)
    return audit_fire_column_experiment_admissibility(catalog)


def qualification_ledger(*,coupled_model=None,thermal_audit=None,
                          creep_audit=None,experiment_audit=None,
                          first_limit_history=None):
    """Five evidence families never conflated with a green numerical CI."""
    categories={
        "mechanical_equilibrium_and_coupled_stiffness":(
            "NUMERICALLY_EVALUATED_SOURCE_CONDITIONAL" if
            isinstance(coupled_model,dict) and
            coupled_model.get("nominal_coupled_evidence") else "NOT_EXECUTED"),
        "thermal_mesh_and_time":(
            "NUMERICALLY_STUDIED_NOT_PHYSICALLY_QUALIFIED" if
            isinstance(thermal_audit,dict) else "NOT_EXECUTED"),
        "hot_creep_from_actual_fire_history":(
            "SOURCE_EQ_8_64_EVALUATED_BUT_HOT_CREEP_UNQUALIFIED" if
            isinstance(creep_audit,dict) else "NOT_EXECUTED"),
        "source_matched_experimental_first_failure":(
            "CATALOG_ADMISSIBILITY_REVIEWED_NOT_VALIDATED" if
            isinstance(experiment_audit,dict) else "NOT_EXECUTED"),
        "first_global_physical_failure":(
            "FIRST_MODEL_EVENT_SAMPLED_NOT_PHYSICAL_FAILURE" if
            isinstance(first_limit_history,dict) else "NOT_EXECUTED")}
    blockers=[
        "NONUNIFORM_SP5_8_1_6_NOMINAL_COUPLED_SCALING_NOT_SOURCE_APPROVED",
        "HOT_SECANT_VS_ELASTIC_BETA_AND_THERMAL_PRESTRAIN_HYSTERESIS_UNQUALIFIED",
        "SP2026_HEAT_MESH_BOUNDARY_SPALLING_FULL_VALIDATION_REQUIRED",
        "TEMPERATURE_DEPENDENT_CREEP_AND_FIRE_ACTION_HISTORY_REQUIRED",
        "SP5_FIRST_GLOBAL_STABLE_BRANCH_AND_CONVERGENCE_REQUIRED",
        "INDEPENDENT_MATCHED_FIRE_COLUMN_EXPERIMENT_VALIDATION_REQUIRED"]
    return {
        "version":VERSION,"status":"NORMATIVE_FIRE_R_QUALIFICATION_BLOCKED",
        "categories":categories,"non_waivable_blockers":blockers,
        "conditional_model_evidence_is_not_normative_U_t":True,
        "actual_U_t":None,"actual_t_R_minutes":None,
        "regulatory_result":"NOT_ESTABLISHED","normative_claim":False}
