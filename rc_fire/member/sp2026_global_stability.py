"""SP-R5 independent GLOBAL second-variation / first-bifurcation evidence.

The assembled geometric nonlinear FE tangent is Kt=Kmaterial-N*G+Ksupport.
This module independently reconstructs full global equilibrium and computes
the smallest eigenvalue of the *free global DOF* tangent. Positive definite
after verified equilibrium demonstrates ONLY LOCAL STABILITY of a tracked
model branch. A negative eigenvalue at a numerically equilibrated state
demonstrates mathematical *instability of that branch*, not the observed
physical fire resistance of an uncalibrated hot RC member.

A failed Newton step, a singular section law, an unconverged state, or
a global tangent evaluated at a NON-equilibrium displacement is UNKNOWN.
For a real column, actual first failure also requires path following,
stiffness/strain history, complete material law, mesh and time convergence,
and experimental calibration.

The independent perfect-Euler pinned column demonstrates that the
global spectral criterion detects its exact FIRST bifurcation correctly.
"""
from __future__ import annotations

import math
import numpy as np

from rc_fire.member.coupled import (
    EndSupport, LinearSectionLaw, CoupledMemberError,
    _beam_assembly, _boundary_matrix, solve_coupled_beam)

VERSION="SP-R5-first-global-stability-spectral-branch-v1"
STABLE="EQUILIBRATED_STRICTLY_POSITIVE_GLOBAL_TANGENT"
UNSTABLE="EQUILIBRATED_NEGATIVE_GLOBAL_TANGENT_BRANCH"
AMBIGUOUS="GLOBAL_TANGENT_NEAR_SINGULAR_UNRESOLVED"
UNKNOWN="GLOBAL_STABILITY_UNRESOLVED"


def _finite_vec(value,shape,name):
    try: arr=np.asarray(value,dtype=float)
    except (TypeError,ValueError) as exc:
        raise ValueError(name+": nonnumeric") from exc
    if arr.shape!=shape or not np.all(np.isfinite(arr)):
        raise ValueError(name+": invalid shape or nonfinite")
    return arr


def check_global_equilibrium_tangent(z_m,N_kN,law_at_gauss, *,
                                     left,right,distributed_load_kNpm,
                                     nodal_forces,initial_imperfection,
                                     displacements, residual_tolerance=1.e-7,
                                     spectral_relative_tolerance=1.e-9):
    """Inspect actual specified global DOF state, no Newton substitution.

    The external caller MUST provide the physical load vector and
    displacements of the same source, time and beam discretisation.
    Mechanical history and source quality remain unqualified.
    """
    z=np.asarray(z_m,dtype=float)
    if (z.ndim!=1 or len(z)<3 or abs(z[0])>1.e-10 or
            np.any(np.diff(z)<=0)):
        raise ValueError("3+ increasing z stations from 0 needed")
    n=len(z);N=float(N_kN)
    if not math.isfinite(N) or N<0.:
        raise ValueError("finite nonnegative compression required")
    dofs=4*n
    d=_finite_vec(displacements,(dofs,),"displacements")
    q=_finite_vec(distributed_load_kNpm,(n,2),"distributed load")
    nodal=_finite_vec(nodal_forces,(dofs,),"nodal forces")
    imperfection=_finite_vec(initial_imperfection,(dofs,),"imperfection")
    rt=float(residual_tolerance);et=float(spectral_relative_tolerance)
    if not 0<rt<=1.e-3 or not 0<et<=1.e-5:
        raise ValueError("invalid verification tolerances")
    fixed,springs=_boundary_matrix(left,right,n)
    free=np.array([i for i in range(dofs) if i not in fixed],dtype=int)
    if not free.size:
        raise ValueError("all global DOFs restrained")
    if any(abs(d[i]-v)>1.e-8 for i,v in fixed.items()):
        return {"version":VERSION,"status":UNKNOWN,
                "reason":"displacements violate actual supports",
                "is_equilibrium":False,"normative_claim":False}
    try:
        fi,K,G,F,stations=_beam_assembly(
            z,N,law_at_gauss,d,imperfection,q,nodal)
        residual=fi-N*G@(d+imperfection)+springs*d-F
        tangent=K-N*G+np.diag(springs)
        T=tangent[np.ix_(free,free)]
        symmetric=(T+T.T)*.5
        eig=np.linalg.eigvalsh(symmetric)
        scale=max(1.,np.linalg.norm(F[free]),np.linalg.norm(fi[free]))
        equilibrium=float(np.linalg.norm(residual[free])/scale)
        tangent_norm=max(1.,float(np.max(np.abs(eig))))
        asymmetry=float(np.max(np.abs(T-T.T)))/tangent_norm
        eigen_min=float(eig[0])
        relative_min=eigen_min/tangent_norm
        if not (math.isfinite(equilibrium) and math.isfinite(relative_min)):
            raise ValueError("nonfinite equilibrium or eigenvalues")
        if equilibrium>rt or asymmetry>et*100.:
            state=UNKNOWN
            explanation="global system not in certified numerical equilibrium/symmetry"
        elif relative_min>et:
            state=STABLE
            explanation="strictly positive free global tangent at equilibrated state"
        elif relative_min< -et:
            state=UNSTABLE
            explanation="negative global tangent on an equilibrated model branch"
        else:
            state=AMBIGUOUS
            explanation="global tangent approaches zero; numerical refinement required"
        return {
            "version":VERSION,"status":state,"reason":explanation,
            "is_equilibrium":bool(equilibrium<=rt),
            "equilibrium_relative_residual":equilibrium,
            "smallest_global_tangent_eigenvalue":eigen_min,
            "smallest_relative_global_tangent_eigenvalue":relative_min,
            "global_tangent_symmetric_relative_error":asymmetry,
            "free_global_dof":int(free.size),
            "gauss_stations":len(stations),
            "verified_state":d.tolist(),
            "global_energy_second_variation_checked":True,
            "is_first_global_physical_failure":False,
            "constitutive_stiffness_independently_validated":False,
            "normative_claim":False}
    except (ValueError,ArithmeticError,np.linalg.LinAlgError) as exc:
        return {"version":VERSION,"status":UNKNOWN,
                "reason":type(exc).__name__+": "+str(exc),
                "is_equilibrium":False,"normative_claim":False}


def displacements_from_solved_member(result,n):
    if not isinstance(result,dict) or result.get("status") not in (
        "evaluated_diagnostic","strain_limits_exceeded_diagnostic"):
        raise ValueError("only actual converged full member result can be inspected")
    x=[]
    for axis in ("x","y"):
        w=_finite_vec(result["w_"+axis+"_m"],(n,),axis+" displacement")
        theta=_finite_vec(result["theta_"+axis+"_rad"],(n,),axis+" rotations")
        x.extend(v for pair in zip(w,theta) for v in pair)
    return np.asarray(x,dtype=float)


def inspect_solved_member_global_stability(
        result,z,N,law_at_gauss, *,left,right,
        distributed_load_kNpm,nodal_forces,initial_imperfection):
    """Actual FE solution: reconstruct stiffness using SAME heated Gauss laws."""
    z=np.asarray(z,dtype=float)
    try:
        d=displacements_from_solved_member(result,len(z))
    except (ValueError,KeyError,TypeError) as exc:
        return {"version":VERSION,"status":UNKNOWN,
                "reason":str(exc),"is_equilibrium":False,"normative_claim":False}
    return check_global_equilibrium_tangent(
        z,N,law_at_gauss,left=left,right=right,
        distributed_load_kNpm=distributed_load_kNpm,
        nodal_forces=nodal_forces,
        initial_imperfection=initial_imperfection,
        displacements=d)


def perfect_elastic_euler_global_stability(
        *,EI_kNm2=900.,length_m=3.,node_count=13,
        axial_ratio=0.9):
    """Independent ideal pin-pin perfect Euler equilibrium witness.

    w=0 is an exact equilibrium for q=0, zero imperfection, *even above*
    Euler's first bifurcation. A SIGNED global eigenvalue may cross zero
    while local constitutive bending stiffness stays positive.
    This tests global physics of the FE algebra, NOT RC in a real fire.
    """
    EI=float(EI_kNm2);L=float(length_m);ratio=float(axial_ratio)
    if (not all(math.isfinite(v) and v>0. for v in (EI,L,ratio))
            or type(node_count) is not int or not 3<=node_count<=129):
        raise ValueError("positive source properties and valid mesh required")
    z=np.linspace(0.,L,node_count)
    n=node_count
    law=LinearSectionLaw(
        np.diag([EI,EI]),
        provenance="independent perfect Euler column linear material")
    N=ratio*math.pi**2*EI/L**2
    evidence=check_global_equilibrium_tangent(
        z,N,lambda i,j:law,
        left=EndSupport("pinned"),right=EndSupport("pinned"),
        distributed_load_kNpm=np.zeros((n,2)),
        nodal_forces=np.zeros(4*n),
        initial_imperfection=np.zeros(4*n),
        displacements=np.zeros(4*n))
    return {**evidence,
        "ideal_euler_reference_Ncrit_kN":math.pi**2*EI/L**2,
        "test_N_kN":N,"N_over_analytic_Euler_Ncrit":ratio,
        "perfect_euler_bifurcation_not_material_crush":True}


def bracket_perfect_euler_first_global_instability(
        *,EI_kNm2=900.,length_m=3.,node_count=13,
        start_ratio=.75,end_ratio=1.25,
        tolerance_ratio=.001,max_refinements=20):
    """Demonstrate first physical *linear-elastic ideal model* instability.

    Both endpoints AND all bisections have exact perfect-beam equilibrium.
    Unresolved eigenvalues cannot silently be treated as instability.
    The interval is not promoted to actual SP fire R(t).
    """
    a=float(start_ratio);b=float(end_ratio);tol=float(tolerance_ratio)
    if not 0<a<b or not 0<tol<=.05:
        raise ValueError("invalid analytical Euler bracket")
    f=lambda ratio:perfect_elastic_euler_global_stability(
        EI_kNm2=EI_kNm2,length_m=length_m,node_count=node_count,
        axial_ratio=ratio)
    left=f(a);right=f(b)
    if left["status"]!=STABLE or right["status"]!=UNSTABLE:
        return {"version":VERSION,"status":"NO_RESOLVED_EULER_SPECTRAL_BRACKET",
                "left":left,"right":right,"normative_claim":False}
    record=[{"ratio":a,"status":left["status"]},
            {"ratio":b,"status":right["status"]}]
    for _ in range(max_refinements):
        if b-a<=tol:
            break
        mid=(a+b)/2.
        witness=f(mid)
        record.append({"ratio":mid,"status":witness["status"]})
        if witness["status"]==STABLE:
            a=mid
        elif witness["status"]==UNSTABLE:
            b=mid
        else:
            # Near the singular value, retain resolved bracketing data
            # without pretending an unknown midpoint is either sign.
            return {"version":VERSION,
                "status":"EULER_BIFURCATION_NEAR_SINGULAR_REFINEMENT_STOP",
                "last_strictly_stable_N_by_Ncrit":a,
                "first_unstable_N_by_Ncrit":b,
                "unresolved_ratio":mid,"records":record,
                "actual_hot_RC_failure_qualified":False,
                "normative_claim":False}
    return {
        "version":VERSION,
        "status":"EULER_FIRST_GLOBAL_SPECTRAL_BRACKET",
        "last_strictly_stable_N_by_Ncrit":a,
        "first_unstable_N_by_Ncrit":b,
        "relative_bracket_width":(b-a)/b,
        "analytical_first_bifurcation_N_by_Ncrit":1.,
        "records":record,
        "actual_hot_RC_failure_qualified":False,
        "normative_claim":False}
