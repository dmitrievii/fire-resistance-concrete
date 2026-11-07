"""R0.6.4C numerical load multiplier search; research diagnostic ONLY.

Scales a fixed user-provided action pattern at a single thermal state.
It can bracket the first observed numerical strain/stability limit, but cannot
establish normative resistance because the heated constitutive model and
fire load combinations are not fully qualified. Does not extrapolate time.
"""
from __future__ import annotations
import math
import numpy as np
from .coupled import solve_coupled_beam, EndSupport, CoupledMemberError
from .uls import audit_heated_member_uls

_PASS='evaluated_diagnostic'
_FAIL={'strain_limits_exceeded_diagnostic','critical_or_nonpositive_tangent',
       'line_search_failed','iteration_limit','singular','blocked_material'}


def scan_diagnostic_load_factor(z_m, base_N_kN, *, law_at_gauss, node_laws=None,
     left=EndSupport('pinned'),right=EndSupport('pinned'),
     distributed_load_kNpm=None,nodal_forces=None,initial_imperfection=None,
     factor_step=0.25,max_factor=3.,relative_bracket_tolerance=.002,
     max_bisection=20):
    """Find first numerical failure *observed* on increasing load factors.

    All non-convergent states are classified as 'numerical limit detected',
    NOT as a proven material failure. Multiple unstable branches and snap-back
    are not excluded. No normative resistance factor is reported.
    """
    z=np.asarray(z_m,dtype=float)
    if z.ndim!=1 or len(z)<2 or not np.all(np.isfinite(z)) or np.any(np.diff(z)<=0):
        raise CoupledMemberError('bad member stations')
    N=float(base_N_kN)
    if not math.isfinite(N) or N<0:raise CoupledMemberError('bad reference N')
    q=np.zeros((len(z),2)) if distributed_load_kNpm is None else np.asarray(distributed_load_kNpm,dtype=float)
    ff=np.zeros(4*len(z)) if nodal_forces is None else np.asarray(nodal_forces,dtype=float)
    if q.shape!=(len(z),2) or ff.shape!=(4*len(z),) or not np.all(np.isfinite(q)) or not np.all(np.isfinite(ff)):
        raise CoupledMemberError('non-finite or invalid reference load pattern')
    if N==0 and not np.any(q) and not np.any(ff):raise CoupledMemberError('no loading to scale')
    if not (0<factor_step<=max_factor and max_factor<=100 and 0<relative_bracket_tolerance<=.1 and 1<=max_bisection<=50):
        raise CoupledMemberError('invalid scan controls')
    tested=[]
    def evaluate(factor):
        r=solve_coupled_beam(z,N*factor,law_at_gauss=law_at_gauss,
                left=left,right=right,distributed_load_kNpm=q*factor,
                nodal_forces=ff*factor,initial_imperfection=initial_imperfection)
        # Verify concrete/steel limits too; a converged section with strains
        # beyond the prescribed reference limits is not an admitted state.
        if r['status']==_PASS and node_laws is not None:
            audit=audit_heated_member_uls(r,z,N*factor,node_laws=node_laws)
            if audit['exceeded_count'] or any(s['limit_check']=='invalid' for s in audit['samples']):
                state='strain_limit_or_node_invalid'
            else:state='equilibrium_found_diagnostic'
        elif r['status']==_PASS:
            state='equilibrium_found_diagnostic_nodes_missing'
        elif r['status'] in _FAIL:
            state='numerical_limit_or_nonconvergence'
        else:
            state='unsupported_result'
        tested.append({'lambda':float(factor),'member_status':r['status'],'classification':state})
        return state.startswith('equilibrium_found_diagnostic')
    lam=0.; last_ok=0.
    if not evaluate(lam):
        return {'status':'NO_ADMISSIBLE_BASELINE','tested':tested,
                'normative_claim':False,'fire_resistance_status':'not_demonstrated'}
    first_fail=None
    while lam+1e-12<max_factor:
        lam=min(max_factor,lam+factor_step)
        if not evaluate(lam):first_fail=lam;break
        last_ok=lam
    if first_fail is None:
        return {'status':'NO_NUMERICAL_LIMIT_THROUGH_MAX_FACTOR',
            'tested':tested,'max_tested_factor':max_factor,
            'normative_claim':False,'fire_resistance_status':'not_demonstrated'}
    lo=last_ok;hi=first_fail
    for _ in range(max_bisection):
        if (hi-lo)/max(hi,1.)<=relative_bracket_tolerance:break
        mid=(lo+hi)/2
        if evaluate(mid):lo=mid
        else:hi=mid
    return {'status':'FIRST_OBSERVED_NUMERICAL_LIMIT_BRACKETED',
            'lambda_low_diagnostic':lo,'lambda_high_diagnostic':hi,
            'lower_bound_proven_normative':False,'tested':tested,
            'interpretation':'numerical instability, nonlinear iteration failure, or reference strain limit; not normative ULS',
            'normative_claim':False,'fire_resistance_status':'not_demonstrated'}
