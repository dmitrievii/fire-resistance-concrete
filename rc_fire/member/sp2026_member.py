"""SP-R.3: source-matched SP2026 2D hot fibres -> nonlinear two-axis member.

A real nonlinear Euler-Bernoulli beam-column is solved, NOT a first-order
section mislabelled as a member. Explicit supports, axial restraint mode,
a full nodal transverse-action pattern, initial imperfections, and a thermal
field for EACH node and beam Gauss station (or affirmatively declared
uniform exposure) are mandatory.

The numerical solution is a research/engineering diagnostic until the
thermal boundaries, irreversible SP constitutive laws, creep/shrinkage,
spalling, shear, and first-failure criteria are independently qualified.
Newton failure or a nonpositive tangent is UNKNOWN, never physical collapse.
No invented R(t), U(t), or R90 certification.
"""
from __future__ import annotations

import math
import numpy as np

from rc_fire.mechanics.sp2026_section import (
    SPSectionInputError, prepare_sp2026_section)
from rc_fire.thermal.sp2026_heat import SPHeatError
from rc_fire.member.coupled import (
    EndSupport, CoupledMemberError, solve_coupled_beam)
from rc_fire.member.uls import audit_heated_member_uls

VERSION = "SP-R3-2026-hot-member-euler-bernoulli-v1"
SOURCE = "СП 2.02.05-2026 §§8.2.16–8.2.23; СП 5.03.01-2020 §8.1.2, §8.1.6"
WITHIN = "MODEL_SAMPLED_STRAIN_LIMITS_WITHIN"
EXCEEDED = "MODEL_SAMPLED_STRAIN_LIMITS_EXCEEDED"
UNKNOWN = "MODEL_STATE_UNRESOLVED"


class SP2026MemberInputError(ValueError):
    """No physical action/support/temperature provenance or valid beam model."""


def _finite(value, label, *, positive=False):
    if isinstance(value, bool):
        raise SP2026MemberInputError(label + ": finite number required")
    try:
        v = float(value)
    except (ValueError, TypeError) as exc:
        raise SP2026MemberInputError(label + ": finite number required") from exc
    if not math.isfinite(v) or (positive and v <= 0.):
        raise SP2026MemberInputError(label + ": invalid value")
    return v


def _array(value, shape, label):
    try:
        a = np.asarray(value, dtype=float)
    except (ValueError, TypeError) as exc:
        raise SP2026MemberInputError(label + ": numeric array required") from exc
    if a.shape != shape or not np.all(np.isfinite(a)):
        raise SP2026MemberInputError(label + ": wrong shape or nonfinite entry")
    return a


def _support(spec, name):
    if not isinstance(spec, dict) or set(spec) != {"x", "y"}:
        raise SP2026MemberInputError(name + ": explicitly supply x and y supports")
    kinds = ("pinned", "fixed", "guided", "free")
    if any(spec[axis] not in kinds for axis in ("x", "y")):
        raise SP2026MemberInputError(
            name + ": only explicit ideal pinned/fixed/guided/free supports supported")
    supports = tuple(EndSupport(spec[axis]) for axis in ("x", "y"))
    for one in supports:
        one.validate()
    return supports


class SP2026MemberFiberLaw:
    """Condense axial equilibrium of the actual SP heated fibre section.

    SPPreparedSection uses normalized strain curvature gx,gy whereas the beam
    solver uses dimensional curvature 1/m. The Schur complement MUST first
    eliminate epsilon0 and then multiply by diag(h/2,b/2) to obtain dM/dkappa
    in kN*m². No TKP mechanical material diagram is imported.
    """

    def __init__(self, prepared):
        self.p = prepared
        self._e0_hint = -0.001

    def evaluate(self, kappa, N_kN):
        k = _array(kappa, (2,), "curvature")
        N = _finite(N_kN, "compression")
        if N < 0.:
            raise CoupledMemberError("SP-R3 only supports constant compressive axial force")
        shape = np.array([self.p.h_m / 2., self.p.b_m / 2.])
        g = k * shape
        e0 = self._e0_hint
        converged = False
        for iteration in range(65):
            F, J, meta = self.p.force_and_tangent([e0, g[0], g[1]])
            r = float(F[0] - N)
            if abs(r) <= max(1.e-5, 1.e-7 * max(1., N)):
                converged = True
                break
            a = float(J[0, 0])
            if not math.isfinite(a) or a <= 1.e-8:
                raise CoupledMemberError("SP axial sectional tangent unavailable")
            step = max(-.006, min(.006, r / a))
            accepted = False
            for fraction in (1., .5, .25, .125, .0625, .03125):
                candidate = e0 - fraction * step
                trial, _, _ = self.p.force_and_tangent(
                    [candidate, g[0], g[1]])
                if abs(float(trial[0]) - N) < abs(r):
                    e0 = candidate
                    accepted = True
                    break
            if not accepted:
                raise CoupledMemberError("SP axial section line search did not converge")
        if not converged:
            raise CoupledMemberError("SP axial section iteration limit")
        a = float(J[0, 0])
        if a <= 1.e-8:
            raise CoupledMemberError("SP axial tangent vanished")
        schur = J[1:, 1:] - np.outer(J[1:, 0], J[0, 1:]) / a
        D = schur @ np.diag(shape)
        if not np.all(np.isfinite(D)) or not np.allclose(
                D, D.T, atol=1.e-5, rtol=1.e-7):
            raise CoupledMemberError("SP 2-axis condensed tangent nonsymmetric")
        D = (D + D.T) * .5
        if np.linalg.eigvalsh(D)[0] <= 1.e-9:
            raise CoupledMemberError("SP 2-axis condensed tangent nonpositive")
        self._e0_hint = float(e0)
        ratio = float(meta["critical_mechanical_strain_ratio"])
        evidence = {
            "model": VERSION,
            "source": SOURCE,
            "axial_strain": float(e0),
            "critical_mechanical_strain_ratio": ratio,
            "strain_limits_satisfied": bool(meta["model_only_strain_limits_satisfied"]),
            # True means the numerical law is resolved over its DECLARED
            # domain, including the explicit user concrete-zero tail.
            # This is NOT thermal/constitutive normative qualification.
            "constitutive_domain_qualified": True,
            "normative_claim": False,
            "steel_ultimate_failure_criterion_qualified": False,
            "thermal_shrinkage_history_qualified": False,
        }
        return np.asarray(F[1:], dtype=float), D, evidence


def _validate_spec(column, spec):
    if not isinstance(column, dict) or not isinstance(spec, dict):
        raise SP2026MemberInputError("column and explicit member_spec required")
    if spec.get("load_mode") != "explicit_sp2026_beam":
        raise SP2026MemberInputError("explicit_sp2026_beam action input contract required")
    if spec.get("axial_restraint_mode") != "free_axial_expansion":
        raise SP2026MemberInputError(
            "only explicitly axially released columns supported; restrained thermal N unresolved")
    if not spec.get("fire_design_action_source"):
        raise SP2026MemberInputError("actual precombined fire-design actions provenance required")
    z0 = spec.get("z_m")
    if not isinstance(z0, (list, tuple)):
        raise SP2026MemberInputError("explicit beam station coordinates required")
    z = _array(z0, (len(z0),), "z_m")
    if len(z) < 3 or len(z) > 25 or abs(z[0]) > 1.e-10 or (
            np.any(np.diff(z) <= 0.)):
        raise SP2026MemberInputError("3..25 strictly increasing stations starting at z=0 required")
    if abs(float(z[-1]) - _finite(column.get("length_m"), "column length", positive=True)) > 1.e-8:
        raise SP2026MemberInputError("beam stations do not span actual column length")
    N = _finite(spec.get("N_kN"), "fire-design axial compression", positive=True)
    for section in column.get("sections") or []:
        if section.get("N_kN") is not None and abs(
                _finite(section["N_kN"], "section N") - N) > 1.e-6:
            raise SP2026MemberInputError("member N does not equal declared section fire-design N")
    left = _support(spec.get("left_support"), "left_support")
    right = _support(spec.get("right_support"), "right_support")
    n = len(z)
    q = _array(spec.get("distributed_load_kNpm"), (n, 2), "distributed_load_kNpm")
    f = _array(spec.get("nodal_forces"), (4*n,), "nodal_forces")
    imperfection = _array(spec.get("initial_imperfection"), (4*n,), "initial_imperfection")
    if not spec.get("imperfection_source"):
        raise SP2026MemberInputError("initial imperfection must have source, even if zero")
    if not spec.get("transverse_action_source"):
        raise SP2026MemberInputError("distributed/nodal transverse load pattern provenance required")
    for section in column.get("sections") or []:
        if (abs(_finite(section.get("Mx_kNm", 0.), "Mx")) > 1.e-10 or
                abs(_finite(section.get("My_kNm", 0.), "My")) > 1.e-10):
            if spec.get("entered_section_moments_reconciled") is not True:
                raise SP2026MemberInputError(
                    "entered section Mx/My must be reconciled to member nodal/distributed actions")
    # The two-dimensional beam cannot invent a 3-D frame, moving supports,
    # axial thermal restraint, connection stiffness or longitudinal exposure.
    return z, N, left, right, q, f, imperfection


def _snapshot_checked(field, time_minutes, column):
    if not isinstance(field, dict) or field.get("thermal_method") != "SP2026_8.2.23_FVM":
        raise SP2026MemberInputError("each station requires SP-R2 temperature, not TKP")
    if field.get("status") != "evaluated_sp2026_thermal_diagnostic":
        raise SP2026MemberInputError("SP station thermal solver not evaluated")
    snap = field.get("snapshot")
    if not isinstance(snap, dict) or abs(_finite(snap.get("time_minutes"), "snapshot time") - time_minutes) > 1.e-8:
        raise SP2026MemberInputError("SP station temperature time mismatch")
    if abs(_finite(field.get("fire_minutes"), "thermal time") - time_minutes) > 1.e-8:
        raise SP2026MemberInputError("station solution is not selected at requested time")
    grid = field.get("grid") or {}
    if abs(_finite(grid.get("width_mm"), "grid width") - float(column["b_mm"])) > 1.e-7 or abs(
            _finite(grid.get("height_mm"), "grid height") - float(column["h_mm"])) > 1.e-7:
        raise SP2026MemberInputError("SP station section geometry mismatch")
    if field.get("material_family") != (column.get("thermal_spec") or {}).get("concrete_family"):
        raise SP2026MemberInputError("SP station aggregate family mismatch")
    if set(field.get("exposed_faces") or []) != set(
            (column.get("thermal_spec") or {}).get("exposed_faces") or []):
        raise SP2026MemberInputError("SP station exposed faces inconsistent")
    return field


def evaluate_sp2026_member_at_time(column, thermal_snapshot, member_spec, *,
                                   grid=12, node_snapshots=None,
                                   gauss_snapshots=None):
    """Evaluate actual two-axis FE equilibrium for a FULL column at one time.

    For explicit_uniform_full_length, a SP-R2 cross section is used at all
    member nodes and integration points ONLY after affirmative declaration.
    Alternatively 'explicit_per_station' requires 3 Gauss snapshots PER
    element and a separate snapshot for each node; no z interpolation.
    """
    z, N, left, right, q, f, imperfection = _validate_spec(column, member_spec)
    time = _finite((thermal_snapshot or {}).get("fire_minutes"), "fire time", positive=True)
    mode = member_spec.get("longitudinal_thermal_mode")
    if mode == "explicit_uniform_full_length":
        if member_spec.get("uniform_exposure_confirmed") is not True:
            raise SP2026MemberInputError("physical uniform full-length heating must be acknowledged")
        snap = _snapshot_checked(thermal_snapshot, time, column)
        gauss = [[snap]*3 for _ in range(len(z)-1)]
        nodes = [snap]*len(z)
        if node_snapshots is not None or gauss_snapshots is not None:
            raise SP2026MemberInputError("do not mix uniform and explicit station thermal fields")
    elif mode == "explicit_per_station":
        if not isinstance(node_snapshots, (list, tuple)) or len(node_snapshots) != len(z):
            raise SP2026MemberInputError("one explicit thermal snapshot per FE node required")
        if (not isinstance(gauss_snapshots, (list, tuple)) or
                len(gauss_snapshots) != len(z)-1 or
                any(not isinstance(row, (list, tuple)) or len(row) != 3
                    for row in gauss_snapshots)):
            raise SP2026MemberInputError("three explicit Gauss thermal snapshots per element required")
        nodes = [_snapshot_checked(s, time, column) for s in node_snapshots]
        gauss = [[_snapshot_checked(s, time, column) for s in row]
                 for row in gauss_snapshots]
    else:
        raise SP2026MemberInputError("unknown longitudinal heating: explicit uniform/stations required")
    if type(grid) is not int or not 8 <= grid <= 80:
        raise SP2026MemberInputError("mechanical fibre grid 8..80 required")
    try:
        # Cache the material inventory for identical thermal snapshots, not
        # the per-Gauss evolving axial strain state (independent laws).
        cache = {}
        def prepared(field):
            key = id(field)
            if key not in cache:
                cache[key] = prepare_sp2026_section(column, field, grid=grid)
            return cache[key]
        gauss_laws = [[SP2026MemberFiberLaw(prepared(field)) for field in row]
                      for row in gauss]
        node_laws = [SP2026MemberFiberLaw(prepared(field)) for field in nodes]
        result = solve_coupled_beam(z, N,
            law_at_gauss=lambda i, j: gauss_laws[i][j],
            left=left, right=right,
            distributed_load_kNpm=q, nodal_forces=f,
            initial_imperfection=imperfection,
            max_iterations=30, tolerance=1.e-7)
        audit = audit_heated_member_uls(result, z, N,
            node_laws=node_laws,
            action_provenance=member_spec["fire_design_action_source"],
            material_provenance=SOURCE,
            temperature_time_minutes=time,
            axial_restraint_qualified=False, spalling_qualified=False)
    except (SPHeatError, SPSectionInputError, CoupledMemberError,
            ValueError, ArithmeticError, np.linalg.LinAlgError) as exc:
        return {
            "version": VERSION, "status": UNKNOWN, "time_minutes": time,
            "reason": str(exc), "member": None, "uls": None,
            "member_model_strain_limit_index": None,
            "U_member_t": None, "R_t_minutes": None, "regulatory_result": "NOT_ESTABLISHED",
            "normative_claim": False,
            "blockers": ["SP2026_MEMBER_MODEL_OR_TEMPERATURE_UNRESOLVED"]}
    if audit.get("status") == "SAMPLED_STRAINS_WITHIN_LIMITS_NOT_NORMATIVE_ULS":
        status = WITHIN
    elif audit.get("status") == "DIAGNOSTIC_STRAIN_LIMIT_EXCEEDED":
        status = EXCEEDED
    else:
        status = UNKNOWN
    critical = audit.get("critical_sample") or {}
    index = critical.get("maximum_ratio") if status != UNKNOWN else None
    return {
        "version": VERSION, "status": status, "time_minutes": time,
        "full_member_model": "2AXIS_NONLINEAR_EULER_BERNOULLI_FIBRE_FEM_PDELTA",
        "temperature_method": "SP2026_8.2.23_FVM",
        "concrete_material_source": "SP2026_TABLE9_SP5_6.1.5.4",
        "steel_material_source": "SP2026_TABLE10_SP5_6.2.2.13",
        "member_thermal_longitudinal_mode": mode,
        "station_count": len(nodes)+sum(len(row) for row in gauss),
        "member": result, "uls": audit,
        "member_model_strain_limit_index": index,
        # The strain-limit index is NOT a load/capacity utilisation U(t).
        "U_member_t": None,
        "R_t_minutes": None, "regulatory_result": "NOT_ESTABLISHED",
        "normative_claim": False,
        "blockers": sorted(set(audit.get("blockers", []) + [
            "SP_R2_HEAT_EXCHANGE_AND_MOISTURE_NOT_PHYSICALLY_QUALIFIED",
            "SP_R1_IRREVERSIBLE_THERMAL_STRAIN_AND_STEEL_FAILURE_NOT_QUALIFIED",
            "LOCAL_SAMPLED_STRAIN_LIMIT_NOT_VERIFIED_MEMBER_COLLAPSE",
            "CONTINUOUS_MEMBER_STABILITY_AND_MESH_LIMIT_NOT_QUALIFIED",
            "SP_R3_TRUE_MEMBER_LOAD_RESISTANCE_U_T_NOT_ESTABLISHED",
            "SP_R3_FIRST_PHYSICAL_FAILURE_R_T_NOT_ESTABLISHED"])),
        "interpretation": "Observed FE equilibrium/strain evidence only; no structural fire rating."}


def scan_sp2026_member_history(column, heat_result, member_spec, times_minutes,
                               *, grid=12):
    """Time-matched member history without interpolating missing heat times.

    Only the explicitly uniform-longitudinal mode is supported by a single
    SP-R2 heat_result. Nonuniform exposure must be evaluated with separate
    per-station snapshots via evaluate_sp2026_member_at_time.
    """
    if not isinstance(times_minutes, (list, tuple)) or not times_minutes:
        raise SP2026MemberInputError("at least one member evaluation time required")
    times = [_finite(t, "member time", positive=True) for t in times_minutes]
    if any(b <= a for a, b in zip(times, times[1:])):
        raise SP2026MemberInputError("strictly increasing member times required")
    if member_spec.get("longitudinal_thermal_mode") != "explicit_uniform_full_length":
        raise SP2026MemberInputError("full longitudinal thermal histories must be supplied explicitly")
    from rc_fire.thermal.sp2026_heat import select_sp2026_snapshot
    samples = []
    for t in times:
        field = select_sp2026_snapshot(heat_result, t)
        report = evaluate_sp2026_member_at_time(column, field, member_spec, grid=grid)
        samples.append({
            "time_minutes": t,
            "status": report["status"],
            "member_model_strain_limit_index": report.get("member_model_strain_limit_index"),
            "member_solver_status": (report.get("member") or {}).get("status"),
            "member_result": report,
        })
    brackets = [
        {"last_model_within_minutes": a["time_minutes"],
         "first_model_exceeded_minutes": b["time_minutes"]}
        for a,b in zip(samples,samples[1:])
        if a["status"] == WITHIN and b["status"] == EXCEEDED]
    return {
        "version": VERSION,
        "status": "SAMPLED_MODEL_TRANSITION" if brackets else
                  "UNRESOLVED_SAMPLED_HISTORY" if any(s["status"] == UNKNOWN for s in samples)
                  else "NO_SAMPLED_MODEL_TRANSITION",
        "samples": samples,
        "observed_model_strain_brackets": brackets,
        "unknown_times_minutes": [
            row["time_minutes"] for row in samples if row["status"] == UNKNOWN],
        "U_t": None, "t_R": None, "R_t_minutes": None,
        "regulatory_result": "NOT_ESTABLISHED", "normative_claim": False,
        "interpretation": (
            "Adjacent sampled numerical strain-state brackets are not certified "
            "first loss of whole-member load bearing resistance. Unknown times "
            "may contain any physical transition; initial t=0 is not solved.") }
