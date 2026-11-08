"""R0.6.9D4 — observation-based first strain-limit crossing, not a fire rating.

Separate a valid *equilibrated sampled fibre strain exceedance* from
unresolved nonlinear equilibrium and from structural failure. No assumption
that the time response is monotone: all known transitions and recoveries are
preserved, and unknown samples break a bracket.

A callback can refine an observed bracket by computing a FRESH thermal and
mechanical state at the midpoint. Missing physical member conditions,
validation and temperature-domain support always prevent normative R(t).
"""
from __future__ import annotations

import math

from rc_fire.mechanics.action_capacity import WITHIN,EXCEEDED,UNKNOWN

VERSION="R0.6.9D4-observed-fire-strain-transition-bracketing-v1"


def _number(v, label):
    if isinstance(v,bool):
        raise ValueError(f"{label}: finite scalar required")
    try: out=float(v)
    except (ValueError,TypeError) as exc:
        raise ValueError(f"{label}: finite scalar required") from exc
    if not math.isfinite(out):
        raise ValueError(f"{label}: finite scalar required")
    return out


def _validate(rows):
    if not isinstance(rows,(list,tuple)) or not rows:
        raise ValueError("nonempty temperature/mechanics time records required")
    observations=[]
    last=-math.inf
    for entry in rows:
        if not isinstance(entry,dict):
            raise ValueError("history record must be dict")
        t=_number(entry.get('time_minutes'),'time_minutes')
        if t<0 or t<=last:
            raise ValueError("time samples must be strictly increasing >=0")
        last=t
        state=entry.get('reference_classification',UNKNOWN)
        if state not in (WITHIN,EXCEEDED,UNKNOWN):
            state=UNKNOWN
        observations.append({'time_minutes':t,'classification':state,
            'model_status':entry.get('status'),
            'reason':entry.get('reason')})
    return observations


def summarize_observed_strain_history(rows):
    """All sampled time states; no inference across unknown or recovery."""
    obs=_validate(rows)
    brackets=[]
    reversals=[]
    for a,b in zip(obs,obs[1:]):
        if a['classification']==WITHIN and b['classification']==EXCEEDED:
            brackets.append({
                'sampled_within_time_minutes':a['time_minutes'],
                'sampled_strain_exceeded_time_minutes':b['time_minutes'],
                'proof_of_physical_collapse':False,
                'normative_first_loss':False,
                'earlier_unknown_or_exceedance':any(
                    s['classification']!=WITHIN
                    for s in obs if s['time_minutes']<a['time_minutes'])})
        elif a['classification']==EXCEEDED and b['classification']==WITHIN:
            reversals.append({
                'sampled_exceeded_time_minutes':a['time_minutes'],
                'later_sampled_within_time_minutes':b['time_minutes']})
    unknown=[s['time_minutes'] for s in obs if s['classification']==UNKNOWN]
    first_exceeded=next((s['time_minutes'] for s in obs
                          if s['classification']==EXCEEDED),None)
    return {'version':VERSION,
       'status':('OBSERVED_STRAIN_TRANSITIONS' if brackets else
                 'UNRESOLVED_REFERENCE_STATE' if unknown else
                 'NO_ADJACENT_WITHIN_TO_EXCEEDED_TRANSITION'),
       'time_points':len(obs),'observations':obs,
       'observed_within_to_exceeded_intervals':brackets,
       'observed_exceeded_to_within_reversals':reversals,
       'first_observed_strain_exceedance_minutes':first_exceeded,
       'unknown_time_points_minutes':unknown,
       'first_observed_strain_transition_is_not_member_failure':True,
       'monotonic_failure_hypothesis_proved':False,
       'qualified_member_path_required':True,
       'normative_R_t_minutes':None,'R_t_minutes':None,
       'normative_claim':False,'fire_resistance_status':'not_demonstrated'}


def refine_observed_interval(rows,evaluate,*,max_refinements=5,
                             tolerance_minutes=1.):
    """Refine the first known adjacent WITHIN->EXCEEDED interval.

    The supplied evaluator MUST recompute the actual thermal-mechanical
    state from the original initial condition to the requested fire minute.
    No interpolation of temperatures/strains or warm-start of a Newton root.
    A numerical UNKNOWN stops refinement and is never treated as failure.
    """
    base=summarize_observed_strain_history(rows)
    if not callable(evaluate):
        raise ValueError("evaluate(t_minutes) callback required")
    if type(max_refinements) is not int or not 0<=max_refinements<=12:
        raise ValueError("max_refinements must be 0..12")
    tol=_number(tolerance_minutes,'tolerance_minutes')
    if tol<=0:
        raise ValueError("tolerance_minutes must be positive")
    pairs=base['observed_within_to_exceeded_intervals']
    if not pairs:
        return {**base,'refined_first_diagnostic_interval':None,
                'additional_time_samples':[]}
    selected=pairs[0]
    lo=selected['sampled_within_time_minutes']
    hi=selected['sampled_strain_exceeded_time_minutes']
    steps=[]
    stopped=False
    for _ in range(max_refinements):
        if hi-lo<=tol:
            break
        t=(lo+hi)/2.
        try:
            r=evaluate(t)
            if not isinstance(r,dict):
                raise ValueError('evaluator returned invalid evidence')
            classification=r.get('reference_classification',UNKNOWN)
            if classification not in (WITHIN,EXCEEDED,UNKNOWN):
                classification=UNKNOWN
            reason=r.get('reason')
        except (ValueError,TypeError,KeyError,RuntimeError,ArithmeticError) as exc:
            classification=UNKNOWN
            reason=f"{type(exc).__name__}: {exc}"
        steps.append({'time_minutes':t,'classification':classification,
            'reason':reason})
        if classification==WITHIN:
            lo=t
        elif classification==EXCEEDED:
            hi=t
        else:
            stopped=True
            break
    refined={'sampled_within_time_minutes':lo,
        'sampled_strain_exceeded_time_minutes':hi,
        'width_minutes':hi-lo,
        'interrupted_by_unknown_state':stopped,
        'earlier_unknown_or_exceedance':selected['earlier_unknown_or_exceedance'],
        'proof_of_physical_collapse':False,'normative_first_loss':False}
    return {**base,'refined_first_diagnostic_interval':refined,
        'additional_time_samples':steps,
        'R_t_minutes':None,'normative_claim':False}
