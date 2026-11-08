"""R0.6.9A - sampled time history of heated-member limit states.

A time series is not a certificate of R(t). Unsupported temperatures, missing
stations and nonlinear solver failures are UNKNOWN, never failure or survival.
No temperature, strength or moment is extrapolated in time.

SP 2.02.05-2026 clauses 8.2.16--8.2.20. R_t_minutes is always None
until independent constitutive and continuous member-ULS qualification.
"""
from __future__ import annotations
import math
from typing import Callable

VERSION = 'R0.6.9A-sampled-time-history-diagnostic-v1'
WITHIN = 'sampled_strains_within_limits_diagnostic'
EXCEEDED = 'sampled_strain_limit_exceeded_diagnostic'
UNKNOWN = 'unresolved_or_unqualified'


def _finite_time(value, name):
    if isinstance(value, bool):
        raise ValueError(f'{name} must be a finite number')
    try:
        number = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f'{name} must be a finite number') from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f'{name} must be nonnegative and finite')
    return number


def timeline_points(duration_minutes: float, *, step_minutes: float = 10.,
                    start_minutes: float = 1., max_points: int = 180) -> list[float]:
    """Build increasing solver times; do not invent an Annex-K t=0 solution."""
    duration = _finite_time(duration_minutes, 'duration_minutes')
    step = _finite_time(step_minutes, 'step_minutes')
    start = _finite_time(start_minutes, 'start_minutes')
    if not (0 < start <= duration and step > 0):
        raise ValueError('require 0 < start_minutes <= duration_minutes and step_minutes > 0')
    if type(max_points) is not int or not 2 <= max_points <= 500:
        raise ValueError('max_points must be an integer in 2..500')
    times = [start]
    k = 1
    while k * step < duration - 1.e-9:
        t = k * step
        if t > start + 1.e-9:
            times.append(t)
        k += 1
        if k > max_points + 2:
            raise ValueError('too many requested time samples')
    if duration > times[-1] + 1.e-9:
        times.append(duration)
    if len(times) > max_points:
        raise ValueError('too many requested time samples')
    return times


def classify_evidence(data: dict) -> dict:
    """Classify only sufficiently resolved sampled numerical ULS evidence."""
    if not isinstance(data, dict):
        return {'class': UNKNOWN, 'reason': 'member evidence is not an object', 'critical_ratio': None}
    status = str(data.get('status', 'NOT_EVALUATED'))
    uls = data.get('uls') if isinstance(data.get('uls'), dict) else {}
    material = data.get('material_audit') if isinstance(data.get('material_audit'), dict) else {}
    uls_status = str(uls.get('status', status))
    blockers = list(data.get('blockers') or []) + list(uls.get('blockers') or []) + list(material.get('blockers') or [])
    hard = [str(b) for b in blockers if any(k in str(b) for k in (
        'MATERIAL_', 'NOT_QUALIFIED_STRENGTH', 'TEMPERATURE_', 'SECTION_EQUILIBRIUM_',
        'GAUSS_STATION_EVIDENCE_', 'NODE_SECTION_EQUILIBRIUM_',
        'LOCAL_STRAIN_LIMIT_INFORMATION_', 'END_AND_INTERIOR_NODES_',
    ))]
    if status.startswith('BLOCKED') or hard or uls_status == 'MODEL_NOT_SOLVED':
        return {'class': UNKNOWN, 'reason': str(data.get('reason') or '; '.join(hard) or status),
                'critical_ratio': None}
    if uls.get('node_coverage') is not True or uls.get('all_sampled_limits_resolved') is not True:
        return {'class': UNKNOWN, 'reason': 'complete Gauss and both-sided nodal strain checks required',
                'critical_ratio': None}
    critical = uls.get('critical_sample')
    ratio = critical.get('maximum_ratio') if isinstance(critical, dict) else None
    if ratio is not None:
        try:
            ratio = float(ratio)
            if not math.isfinite(ratio) or ratio < 0:
                ratio = None
        except (ValueError, TypeError):
            ratio = None
    if uls_status == 'DIAGNOSTIC_STRAIN_LIMIT_EXCEEDED' and uls.get('exceeded_count', 0) > 0:
        return {'class': EXCEEDED, 'reason': 'sampled strain limit exceeded (not global ULS)',
                'critical_ratio': ratio}
    if uls_status == 'SAMPLED_STRAINS_WITHIN_LIMITS_NOT_NORMATIVE_ULS' and uls.get('exceeded_count') == 0:
        return {'class': WITHIN, 'reason': 'all sampled strain limits within bounds (not R(t))',
                'critical_ratio': ratio}
    return {'class': UNKNOWN, 'reason': f'ULS diagnostic not conclusive: {uls_status}',
            'critical_ratio': ratio}


def scan_member_time_history(times_minutes, evaluate_at_time: Callable[[float], dict]) -> dict:
    """Run independent thermal/member states; do not infer results across gaps.

    Model nonconvergence is not failure. Only adjacent known within/exceeded
    samples provide an observed *diagnostic* bracket, never certified R(t).
    """
    if not callable(evaluate_at_time):
        raise ValueError('evaluate_at_time must be callable')
    if not isinstance(times_minutes, (list, tuple)) or not times_minutes:
        raise ValueError('at least one time sample is required')
    times = [_finite_time(t, f'times_minutes[{i}]') for i, t in enumerate(times_minutes)]
    if any(b <= a + 1.e-9 for a, b in zip(times, times[1:])):
        raise ValueError('times must be strictly increasing')
    records = []
    for t in times:
        try:
            evidence = evaluate_at_time(t)
            cls = classify_evidence(evidence)
            model_status = evidence.get('status') if isinstance(evidence, dict) else None
            uls_status = ((evidence.get('uls') or {}).get('status')
                          if isinstance(evidence, dict) and isinstance(evidence.get('uls'), dict) else None)
        except (ValueError, TypeError, ArithmeticError, RuntimeError, KeyError) as exc:
            cls = {'class': UNKNOWN, 'reason': f'{type(exc).__name__}: {exc}', 'critical_ratio': None}
            model_status, uls_status = 'EXCEPTION', None
        records.append({'time_minutes': t, 'class': cls['class'],
                        'reason': cls['reason'], 'critical_ratio': cls['critical_ratio'],
                        'member_status': model_status, 'uls_status': uls_status})
    brackets = [
        {'last_sampled_within_minutes': a['time_minutes'],
         'first_sampled_exceeded_minutes': b['time_minutes']}
        for a, b in zip(records, records[1:])
        if a['class'] == WITHIN and b['class'] == EXCEEDED
    ]
    uncertainty = [x['time_minutes'] for x in records if x['class'] == UNKNOWN]
    beyond = [x['time_minutes'] for x in records if x['class'] == EXCEEDED]
    status = ('SAMPLED_TRANSITION_BRACKET_FOUND' if brackets else
              'EXCEEDANCE_AT_FIRST_SAMPLE' if records[0]['class'] == EXCEEDED else
              'UNRESOLVED_HISTORY' if uncertainty else
              'NO_SAMPLED_EXCEEDANCE' if not beyond else 'UNBRACKETED_SAMPLED_EXCEEDANCE')
    return {'version': VERSION, 'status': status, 'samples': records,
            'sample_count': len(records), 'unresolved_times_minutes': uncertainty,
            'first_observed_exceedance_minutes': beyond[0] if beyond else None,
            'observed_transition_brackets_minutes': brackets,
            'R_t_minutes': None, 'normative_claim': False,
            'fire_resistance_status': 'not_demonstrated',
            'blockers': ['CONTINUOUS_MEMBER_ULS_NOT_QUALIFIED',
                         'HIGH_TEMPERATURE_CONSTITUTIVE_SCOPE_NOT_RESOLVED',
                         'DIAGNOSTIC_TIME_SAMPLING_NOT_NORMATIVE_R_T'],
            'interpretation': 'Observed sampled strains only; the true first failure time cannot be certified, especially across unresolved samples or unsampled time intervals.'}
