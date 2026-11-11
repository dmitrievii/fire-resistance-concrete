"""Independent mechanical verification and fire-ULS admissibility evidence.

Normative order: СП 2.02.05-2026 §8.2.16–8.2.23 -> SP5.03.01-2020
§§6.1.5.2,6.1.5.4,6.2.2.13,8.1.1.5,8.1.2.1–8.1.2.4,8.1.6.

The Euler buckling and P-Delta benchmarks verify *finite-element algebra*
on precisely defined linear beams, not heated reinforced concrete material
laws. The SP hot fibre Jacobian test independently verifies derivatives of
the implemented constitutive relation; it does NOT validate that relation
against a material experiment or independently prove SP compliance.

Mechanical ULS certification requires BOTH numerical and independent
physical/normative evidence. It is deliberately impossible to override a
physical gap merely with a user-entered 'verified' or a passing CI badge.
"""
from __future__ import annotations

import math
import numpy as np

from rc_fire.member.coupled import (
    LinearSectionLaw, EndSupport, _beam_assembly, _boundary_matrix,
    solve_coupled_beam,
)

VERSION = "SP-R4Q-2026-mechanical-qualification-v1"
SP_FIRE = "СП 2.02.05-2026 §§8.2.16–8.2.23, Table 9/10"
SP_MECHANICS = "СП 5.03.01-2020 §§6.1.5.2/4, 6.2.2.13, 8.1.2, 8.1.6"

# For a *perfect, linear*, constant-EI Euler-Bernoulli column, these
# correspond to the idealised support types defined in SP5 §8.1.6.6.
# Fixed-pinned is the ideal mathematical 0.699155... L, not the rounded
# 0.7 L design approximation. Only ideal boundary conditions are benchmarked.
_IDEAL_EFFECTIVE_LENGTH = {
    ("pinned", "pinned"): 1.,
    ("fixed", "fixed"): .5,
    ("fixed", "free"): 2.,
    ("free", "fixed"): 2.,
}


def _finite_positive(v, label):
    if isinstance(v, bool):
        raise ValueError(label + ": positive finite number required")
    try:
        x = float(v)
    except (TypeError, ValueError) as exc:
        raise ValueError(label + ": positive finite number required") from exc
    if not math.isfinite(x) or x <= 0.:
        raise ValueError(label + ": positive finite number required")
    return x


def _linear_reference_problem(length_m, EI_x_kNm2, EI_y_kNm2,
                              node_count, left_kind, right_kind):
    L = _finite_positive(length_m, "length")
    ex = _finite_positive(EI_x_kNm2, "EI_x")
    ey = _finite_positive(EI_y_kNm2, "EI_y")
    if type(node_count) is not int or not 3 <= node_count <= 129:
        raise ValueError("node_count must be 3..129")
    pair = (left_kind, right_kind)
    if pair not in _IDEAL_EFFECTIVE_LENGTH:
        raise ValueError("linear benchmark requires ideal pin-pin/fix-fix/fix-free")
    z = np.linspace(0., L, node_count)
    law = LinearSectionLaw(
        np.diag([ex, ey]), provenance="independent elastic Euler benchmark")
    def law_at_gauss(i, j):
        return law
    free_ends = _boundary_matrix(
        EndSupport(left_kind), EndSupport(right_kind), node_count)
    fixed, springs = free_ends
    free = np.asarray([i for i in range(4 * node_count)
                       if i not in fixed], dtype=int)
    fi, K, G, F, states = _beam_assembly(
        z, 0., law_at_gauss,
        np.zeros(4 * node_count), np.zeros(4 * node_count),
        np.zeros((node_count, 2)), np.zeros(4 * node_count))
    if any(abs(x) > 1.e-8 for x in (np.linalg.norm(fi),
                                         np.linalg.norm(F))):
        raise ValueError("nonzero internal/external force in zero-state elastic benchmark")
    return z, law_at_gauss, free, K, G, pair, ex, ey


def _generalized_critical(K, G, indices):
    # Solve generalized K v = N G v without scipy. If G has zero modes
    # the eigenvalues of K^-1 G at those modes are zero, not critical.
    ix = np.asarray(indices, dtype=int)
    if ix.size < 1:
        raise ValueError("no free Euler column DOFs")
    Kff = (K[np.ix_(ix, ix)] + K[np.ix_(ix, ix)].T) / 2.
    Gff = (G[np.ix_(ix, ix)] + G[np.ix_(ix, ix)].T) / 2.
    if np.linalg.eigvalsh(Kff)[0] <= 0:
        raise ValueError("zero-load elastic stiffness not positive")
    A = np.linalg.solve(Kff, Gff)
    eigen = np.linalg.eigvals(A)
    if np.max(np.abs(eigen.imag)) > 1.e-8:
        raise ValueError("generalized buckling spectrum not real")
    best = float(max(eigen.real))
    if best <= 0. or not math.isfinite(best):
        raise ValueError("no positive Euler geometric buckling eigenvalue")
    return 1. / best


def verify_euler_critical_load(*, length_m=3., EI_x_kNm2=1200.,
                               EI_y_kNm2=800., node_count=17,
                               left_kind="pinned", right_kind="pinned"):
    """Two independent bending-axis eigenvalue comparisons to Euler formula.

    This verifies FE element stiffness/geometric stiffness, boundary DOF
    ownership, N>0 sign convention, and convergence for *linear* EI.
    It does not show that nonlinear hot RC stiffness is physically correct.
    """
    z, laws, free, K, G, ends, ex, ey = _linear_reference_problem(
        length_m, EI_x_kNm2, EI_y_kNm2, node_count,
        left_kind, right_kind)
    l0 = _IDEAL_EFFECTIVE_LENGTH[ends] * float(z[-1])
    n = len(z)
    result = {}
    for axis, EI in (("x", ex), ("y", ey)):
        shift = 0 if axis == "x" else 2 * n
        indices = [i for i in free if shift <= i < shift + 2 * n]
        Nfe = _generalized_critical(K, G, indices)
        Nexact = math.pi**2 * EI / l0**2
        result[axis] = {
            "Ncrit_FE_kN":Nfe,
            "Ncrit_Euler_exact_kN":Nexact,
            "relative_error":(Nfe-Nexact)/Nexact,
        }
    return {
        "version": VERSION,
        "status":"EULER_LINEAR_REFERENCE_COMPUTED",
        "support_pair":list(ends),
        "node_count":node_count,
        "length_m":float(z[-1]),
        "source":"Euler exact ideal constant-EI beam, independent of SP RC fire",
        "axes":result,
        "is_hot_RC_material_qualification":False,
        "normative_mechanical_fire_qualified":False,
    }


def verify_pdelta_midspan(*, length_m=3., EI_kNm2=1200.,
                          distributed_q_kNpm=2., axial_ratio_to_euler=.4,
                          node_count=17):
    """Closed-form pinned beam under uniform q and constant compression.

    Exact small-deflection solution of EI w'''' + N w'' = q gives
       w(L/2) = q/N * [(sec(kL/2)-1)/k² - L²/8],
    where k=sqrt(N/EI). This analytic reference is independent of
    the FE discretisation. Test with N well below the first Euler pole.
    """
    L=_finite_positive(length_m,"length")
    EI=_finite_positive(EI_kNm2,"EI")
    q=_finite_positive(distributed_q_kNpm,"q")
    ratio=_finite_positive(axial_ratio_to_euler,"axial ratio")
    if not ratio < .9:
        raise ValueError("P-Delta benchmark must be within stable subcritical range")
    if type(node_count) is not int or node_count<3 or node_count%2!=1:
        raise ValueError("odd node count >=3 required to sample midspan")
    Nexact=math.pi**2 * EI/L**2
    N=ratio*Nexact
    k=math.sqrt(N/EI)
    theta=k*L/2.
    expected=q/N*((1./math.cos(theta)-1.)/(k*k)-L*L/8.)
    z=np.linspace(0.,L,node_count)
    constant=LinearSectionLaw(np.diag([EI,EI]),
        provenance="analytic Euler small-deflection 2-axis check")
    solved=solve_coupled_beam(
        z,N,law_at_gauss=lambda i,j:constant,
        left=EndSupport("pinned"),right=EndSupport("pinned"),
        distributed_load_kNpm=[[q,0.]]*node_count,
        initial_imperfection=np.zeros(4*node_count),
        tolerance=1.e-10,max_iterations=12)
    if solved.get("status")!="evaluated_diagnostic":
        raise ValueError("FE benchmark did not converge: "+str(solved.get("status")))
    mid=float(solved["w_x_m"][node_count//2])
    mirror=max(abs(float(v)) for v in solved["w_y_m"])
    return {
        "version":VERSION,
        "status":"ELASTIC_PDELTA_ANALYTICAL_REFERENCE_COMPUTED",
        "axial_ratio_to_euler":ratio,
        "N_kN":N,
        "q_kNpm":q,
        "midspan_FE_m":mid,
        "midspan_analytic_m":expected,
        "relative_error":abs(mid-expected)/abs(expected),
        "other_axis_leakage_m":mirror,
        "source":"closed-form Euler-Bernoulli pinned beam with constant q, N",
        "is_hot_RC_material_qualification":False,
        "normative_mechanical_fire_qualified":False,
    }


def verify_hot_section_jacobian(prepared, *,
                                state=(.001,.0002,-.0001),
                                perturbation=1.e-7):
    """Cross-check exact SP R1/R2 fibre 3x3 Jacobian by central differences.

    This independent derivative check catches thermal-unit/normalization
    mistakes in the implemented algebra. At yield/crushing kinks a central
    difference is not mathematically well-defined, and the result must be
    marked nonqualified rather than silently tolerated.
    """
    v = np.asarray(state,dtype=float)
    if v.shape!=(3,) or not np.all(np.isfinite(v)):
        raise ValueError("3 finite section unknowns required")
    h=_finite_positive(perturbation,"perturbation")
    if not 1.e-10 <= h <= 1.e-5:
        raise ValueError("finite-difference step out of valid scale")
    F,J,meta=prepared.force_and_tangent(v)
    J=np.asarray(J,dtype=float)
    if J.shape!=(3,3) or not np.all(np.isfinite(J)):
        raise ValueError("nonfinite SP fibre Jacobian")
    num=np.zeros((3,3))
    for j in range(3):
        vplus=v.copy();vminus=v.copy()
        vplus[j]+=h;vminus[j]-=h
        fplus,_,_=prepared.force_and_tangent(vplus)
        fminus,_,_=prepared.force_and_tangent(vminus)
        num[:,j]=(np.asarray(fplus)-np.asarray(fminus))/(2.*h)
    errors=np.abs(J-num)
    scale=max(1.,float(np.max(np.abs(J))),float(np.max(np.abs(num))))
    return {
        "version":VERSION,
        "status":"SP_FIBRE_JACOBIAN_FINITE_DIFFERENCE_COMPUTED",
        "state":[float(x) for x in v],
        "perturbation":h,
        "analytical_J":J.tolist(),
        "finite_difference_J":num.tolist(),
        "max_absolute_error":float(np.max(errors)),
        "max_relative_global_scale_error":float(np.max(errors))/scale,
        "max_concrete_temperature_C":meta.get("max_concrete_temperature_C"),
        "max_steel_temperature_C":meta.get("max_steel_temperature_C"),
        "source":"finite differences on the exact installed SP hot fibres",
        "material_law_is_experimentally_validated":False,
        "normative_mechanical_fire_qualified":False,
    }


def verify_condensed_hot_member_tangent(prepared, N_kN, *,
                                        curvature_1pm=(1.e-5,-2.e-5),
                                        perturbation_1pm=1.e-7):
    """Check independently the full axial Schur 2-axis bending tangent.

    Each finite-difference trial instantiates a fresh section law, so an
    axial Newton warm-start from another trial cannot give false agreement.
    The perturbation is in PHYSICAL curvature [1/m], not dimensionless
    normalized fibre curvature. This explicitly validates the h/2,b/2
    geometric mapping and the kN*m -> kN*m² derivative.
    """
    from rc_fire.member.sp2026_member import SP2026MemberFiberLaw
    N = _finite_positive(N_kN,"N")
    k = np.asarray(curvature_1pm,dtype=float)
    if k.shape!=(2,) or not np.all(np.isfinite(k)):
        raise ValueError("2 finite physical curvatures required")
    h=_finite_positive(perturbation_1pm,"curvature difference step")
    if not 1.e-10<=h<=1.e-4:
        raise ValueError("curvature finite-difference step out of range")
    M,D,meta=SP2026MemberFiberLaw(prepared).evaluate(k,N)
    fd=np.zeros((2,2))
    for j in range(2):
        plus=k.copy();minus=k.copy()
        plus[j]+=h;minus[j]-=h
        mp,_,_=SP2026MemberFiberLaw(prepared).evaluate(plus,N)
        mm,_,_=SP2026MemberFiberLaw(prepared).evaluate(minus,N)
        fd[:,j]=(mp-mm)/(2.*h)
    denom=max(1.,float(np.max(np.abs(D))),float(np.max(np.abs(fd))))
    symmetry=np.max(np.abs(D-D.T))/denom
    return {
        "version":VERSION,
        "status":"SP_HEATED_CONDENSED_TANGENT_FINITE_DIFFERENCE_COMPUTED",
        "N_kN":N,
        "physical_curvatures_1pm":k.tolist(),
        "member_tangent_kNm2":D.tolist(),
        "finite_difference_tangent_kNm2":fd.tolist(),
        "relative_global_scale_error":float(np.max(np.abs(D-fd)))/denom,
        "relative_symmetry_error":float(symmetry),
        "axial_force_solved_on_every_trial":True,
        "model_strain_ratio_at_state":meta["critical_mechanical_strain_ratio"],
        "thermal_eigenstrain_and_units_checked_numerically":True,
        "normative_mechanical_fire_qualified":False,
    }


def mechanical_uls_admissibility(column,member_spec, *,
                                numeric_evidence=None,
                                external_evidence=None):
    """Fail-closed independent source/physics gate, no self certification.

    Numeric FE convergence or user claims cannot close an unsolved physical
    law, actual eccentricity, heat exposure, nonlinear stability continuum,
    transient history, or experiment validation. All claims are machine
    readable, so later results cannot quietly replace null U(t) with a number.
    """
    numeric_evidence = numeric_evidence or {}
    external_evidence = external_evidence or {}
    if not isinstance(numeric_evidence,dict) or not isinstance(external_evidence,dict):
        raise ValueError("qualification evidence must be explicitly structured")
    gates=[]
    def gate(name, qualified, detail, source):
        gates.append({"id":name,"status":"PASS" if qualified else "BLOCKED",
                      "detail":detail,"source":source})
    euler=numeric_evidence.get("euler")
    pdelta=numeric_evidence.get("pdelta")
    jac=numeric_evidence.get("jacobian")
    condensed=numeric_evidence.get("condensed_tangent")
    gate("FE_EULER_BUCKLING",isinstance(euler,dict) and
         all(abs(euler.get("axes",{}).get(ax,{}).get("relative_error",float("inf")))<.005
             for ax in ("x","y")),
         "linear Euler compression eigenvalue requires <0.5% error on both axes",
         "independent analytic Euler benchmark")
    gate("FE_PDELTA_DEFLECTION",isinstance(pdelta,dict) and
         pdelta.get("relative_error",math.inf)<.005 and
         pdelta.get("other_axis_leakage_m",math.inf)<1.e-9,
         "pinned uniform-q P-Delta deflection requires <0.5% and axis isolation",
         "independent analytic pin-pin beam")
    gate("SP_HOT_FIBRE_JACOBIAN",isinstance(jac,dict) and
         jac.get("max_relative_global_scale_error",math.inf)<.001,
         "section Jacobian requires <0.1% global-scale FD consistency",
         SP_MECHANICS)
    gate("SP_HOT_CONDENSED_MEMBER_TANGENT",isinstance(condensed,dict) and
         condensed.get("relative_global_scale_error",math.inf)<.001 and
         condensed.get("relative_symmetry_error",math.inf)<.00001,
         "Schur 2-axis dM/dκ physically dimensional tangent must match independent finite differences",
         SP_MECHANICS)
    gate("ACTUAL_MIN_ECCENTRICITY",False,
         "source §8.1.1.5 e>=max(h/30,20mm) not independently reconciled with N/M and user imperfection",
         "СП 5.03.01-2020 §8.1.1.5")
    gate("SP_BETA_ELASTIC_VS_CONSTITUTIVE_STIFFNESS",False,
         "hot βE law and full 6.1.5.2 nonlinear curve not mechanically matched or validated; 6.1.5.4 is a section-check parabola",
         SP_FIRE+"; "+SP_MECHANICS)
    gate("STEEL_NONLINEAR_ULTIMATE",False,
         "SP5 10‰ SECTION verification is not full nonlinear ε_ud material failure law",
         "СП 5.03.01-2020 §§6.2.2.13,8.1.2.1")
    gate("CONCRETE_THERMAL_STRAIN_HISTORY",False,
         "time-dependent thermal shrinkage, transient creep and unloading path not independently calibrated",
         "СП 2.02.05-2026 Tables 11–12")
    gate("GLOBAL_FIRST_STABILITY_AND_POSTPEAK",False,
         "local sampled strain endpoint and SPD FE tangent are not global first bifurcation/postpeak limit",
         "СП 5.03.01-2020 §8.1.6")
    gate("LONGITUDINAL_CONTINUUM_AND_END_ACTIONS",False,
         "member z mesh, actual frame restraint/moment/axial-force diagrams and geometric imperfections unqualified",
         "СП 5.03.01-2020 §§5.4,8.1.6")
    gate("SP_THERMAL_AND_SPALLING",False,
         "source-matched h/epsilon, moisture, actual steel heat transfer and spalling/Annex L unqualified",
         "СП 2.02.05-2026 §8.2.23, Annexes К, Л")
    gate("INDEPENDENT_STRUCTURAL_FIRE_EXPERIMENTS",False,
         "no externally verified matched hot-column experimental data and convergence comparisons",
         "structural-fire validation requirement")
    blockers=[g["id"] for g in gates if g["status"]!="PASS"]
    return {
        "version":VERSION,
        "status":"NUMERICAL_MECHANICS_PARTIALLY_VERIFIED_NONQUALIFIED_FIRE_ULS"
             if len(blockers)<len(gates) else "MECHANICAL_QUALIFICATION_BLOCKED",
        "gate_results":gates,
        "numerical_pass_count":sum(g["status"]=="PASS" for g in gates[:4]),
        "normative_mechanical_uls_qualified":False,
        "source_qualified_fire_R":False,
        "U_member_t":None,
        "t_R":None,
        "regulatory_result":"NOT_ESTABLISHED",
        "remaining_blockers":blockers,
        "material_evidence_cannot_be_replaced_with_user_assertions":True,
        "normative_sources":[SP_FIRE,SP_MECHANICS],
    }
