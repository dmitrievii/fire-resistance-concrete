"""R0.6.9C — sampled proportional action-path reserve, not a normative R(t).

A fixed, user-supplied *fire-design* action vector (N, Mx, My) is multiplied
by lambda.  All equilibrium and limits are evaluated anew at each lambda.
Numerical nonconvergence is UNKNOWN, never mistaken for structural failure.
Multiple transitions, snap-through and unsampled load paths remain possible.
"""
from __future__ import annotations

import math

VERSION = 'R0.6.9C-fixed-action-path-bracketing-v1'
WITHIN = 'sampled_equilibrium_within_strain_limits'
EXCEEDED = 'sampled_equilibrium_strain_limits_exceeded'
UNKNOWN = 'unresolved_numerical_or_physical_state'
STATES = (WITHIN, EXCEEDED, UNKNOWN)


def _number(x, name, *, lower=None, strict=False):
    if isinstance(x,bool):
        raise ValueError(f'{name}: boolean not permitted')
    try:
        x=float(x)
    except (ValueError,TypeError) as exc:
        raise ValueError(f'{name}: expected a finite number') from exc
    if not math.isfinite(x) or (lower is not None and (x<=lower if strict else x<lower)):
        raise ValueError(f'{name}: outside supported range')
    return x


def scan_action_path(evaluate, *, max_factor=2., factor_step=.25,
                     max_bisection=6, max_evaluations=64):
    """Independently sample a fixed loading ray; bracket only known transitions.

    Includes the actual design point lambda=1 even if factor_step does not divide
    1. A bracket is numerical evidence between two sampled equilibrated states,
    *not* a certified capacity, R(t), or proof of monotonic resistance.
    """
    if not callable(evaluate):
        raise ValueError('evaluate must be callable')
    maximum=_number(max_factor,'max_factor',lower=1.)
    step=_number(factor_step,'factor_step',lower=0.,strict=True)
    if maximum>10. or step>maximum or type(max_bisection) is not int or not 0<=max_bisection<=12:
        raise ValueError('invalid load factor scan bounds')
    if type(max_evaluations) is not int or not 4<=max_evaluations<=200:
        raise ValueError('invalid evaluation budget')
    count=int(math.floor(maximum/step))
    if count>max_evaluations-max_bisection-3:
        raise ValueError('too many coarse factor samples')
    factors=sorted(set([0.,1.,maximum]+[min(maximum,k*step) for k in range(1,count+1)]))
    cache={}
    def run(factor):
        key=round(float(factor),12)
        if key in cache:
            return cache[key]
        if len(cache)>=max_evaluations:
            raise ValueError('evaluation budget exceeded')
        try:
            evidence=evaluate(float(key))
            if not isinstance(evidence,dict):
                raise ValueError('evaluator returned non-dictionary evidence')
            state=evidence.get('classification',UNKNOWN)
            if state not in STATES:
                state=UNKNOWN
            record={'lambda':key,'classification':state,
                    'model_status':str(evidence.get('model_status','unknown')),
                    'critical_ratio':evidence.get('critical_ratio'),
                    'reason':str(evidence.get('reason',''))}
        except (ValueError,TypeError,KeyError,ArithmeticError,RuntimeError) as exc:
            record={'lambda':key,'classification':UNKNOWN,'model_status':'EXCEPTION',
                    'critical_ratio':None,'reason':f'{type(exc).__name__}: {exc}'}
        cache[key]=record
        return record
    for f in factors:
        run(f)
    coarse=[cache[round(f,12)] for f in factors]
    brackets=[]
    for a,b in zip(coarse,coarse[1:]):
        if a['classification'] != WITHIN or b['classification'] != EXCEEDED:
            continue
        lo,hi=a,b
        intermediate_unknown=False
        for _ in range(max_bisection):
            mid=(lo['lambda']+hi['lambda'])/2
            if len(cache)>=max_evaluations or mid-lo['lambda']<1e-10:
                break
            point=run(mid)
            if point['classification']==WITHIN:
                lo=point
            elif point['classification']==EXCEEDED:
                hi=point
            else:
                intermediate_unknown=True
                break
        brackets.append({'lower_observed_within':lo['lambda'],
                         'upper_observed_exceeded':hi['lambda'],
                         'refinement_interrupted_by_unknown':intermediate_unknown,
                         'from_coarse':[a['lambda'],b['lambda']],
                         'proves_normative_failure':False})
    samples=sorted(cache.values(),key=lambda item:item['lambda'])
    reference=cache[1.0]
    return {'version':VERSION,'status':(
        'OBSERVED_STRAIN_TRANSITION_BRACKETS' if brackets else
        'UNRESOLVED_AT_DESIGN_ACTION' if reference['classification']==UNKNOWN else
        'NO_OBSERVED_TRANSITION'),
        'design_action_factor':1.,'design_action_evidence':reference,
        'samples':samples,'sample_count':len(samples),
        'transition_brackets_diagnostic':brackets,
        'unresolved_factors':[s['lambda'] for s in samples if s['classification']==UNKNOWN],
        'first_observed_exceedance_factor':next(
            (s['lambda'] for s in samples if s['classification']==EXCEEDED),None),
        'lambda_capacity_normative':None,'R_t_minutes':None,
        'normative_claim':False,'fire_resistance_status':'not_demonstrated',
        'interpretation':(
            'Only sampled equilibria along the proportional action path are known. '
            'Nonconvergence and missing materials are unknown states. '
            'No monotonicity, continuous-load-path or normative strength proof.'
        )}


def scan_prepared_section(prepared, N_kN, Mx_kNm, My_kNm, *,
                          max_factor=2., factor_step=.25, max_bisection=6):
    """Use existing three-unknown fibre equilibrium for the actual input N/M."""
    from rc_fire.mechanics.normative import solve_load, PreparedSection
    if not isinstance(prepared,PreparedSection):
        raise ValueError('prepared fibre section required')
    N=_number(N_kN,'N_kN',lower=0.,strict=True)
    Mx=_number(Mx_kNm,'Mx_kNm')
    My=_number(My_kNm,'My_kNm')

    def assess(lam):
        # Each solve_load starts from its own canonical seeds, not from another
        # lambda's converged strains. No inferred fire action combination.
        r=solve_load(prepared,N*lam,Mx*lam,My*lam)
        status=r.get('status')
        if r.get('equilibrium') is True and status=='equilibrium_within_strain_limits':
            category=WITHIN
        elif r.get('equilibrium') is True and status=='strain_limits_exceeded':
            category=EXCEEDED
        else:
            category=UNKNOWN
        limit=None
        if r.get('equilibrium') is True and isinstance(r.get('details'),dict):
            d=r['details']
            try:
                limit=max(max(0.,float(d['max_concrete_compression']))/prepared.eps_cu2,
                          max(0.,-float(d['min_steel_strain']))/.010)
                if not math.isfinite(limit):limit=None
            except (TypeError,ValueError,KeyError,ZeroDivisionError):
                limit=None
        return {'classification':category,'model_status':status,
                'critical_ratio':limit,
                'reason':str(r.get('reason') or 'section equilibrium evidence')}

    result=scan_action_path(assess,max_factor=max_factor,factor_step=factor_step,
                            max_bisection=max_bisection)
    return {**result,'model':'first_order_biaxial_N_Mx_My_fibre_section',
            'design_actions':{'N_kN':N,'Mx_kNm':Mx,'My_kNm':My},
            'strength_reference':prepared.strength_data.get('reference_strength_mode'),
            'thermal_free_strains_in_section_solver':'not_included',
            'member_second_order_effects_in_section_solver':'not_included',
            'normative_claim':False,'fire_resistance_status':'not_demonstrated'}
