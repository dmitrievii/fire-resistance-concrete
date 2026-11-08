"""R0.6.9A automatic repeated Annex-K + coupled-member diagnostic.

Every time point is recomputed from original immutable column authoring.
No interpolated thermal field, carried-forward stress or ambient fallback.
"""
from __future__ import annotations
import copy
import hashlib
import json

from rc_fire.member.time_scan import timeline_points, scan_member_time_history
from rc_fire.thermal import evaluate_rectangular_column
from .r067 import evaluate_uniform_fire_member, validate_member_spec
from .r064d import MemberEvidenceInputError, _signature

VERSION = 'R0.6.9A-uniform-time-coupling-diagnostic-v1'


def evaluate_uniform_fire_time_history(column, *, step_minutes=10., start_minutes=1.):
    """Scan selected fire duration on a consistent, explicit structural model.

    The same prequalified fire-design N/M values are used at every time point.
    A thermal failure or >800 C is unresolved, not a physical ULS failure.
    """
    if not isinstance(column, dict):
        raise MemberEvidenceInputError('column object required')
    spec = validate_member_spec(column.get('member_spec'))
    end = column.get('fire_minutes')
    times = timeline_points(end, step_minutes=step_minutes, start_minutes=start_minutes)
    signature = _signature(column)
    def evaluate(t):
        c = copy.deepcopy(column)
        c['fire_minutes'] = float(t)
        thermal = evaluate_rectangular_column(c, grid=12)
        if thermal.get('status') not in ('evaluated', 'evaluated_with_scope_warnings'):
            return {'status': 'BLOCKED_MATERIAL_OR_TEMPERATURE_INPUT',
                    'reason': str(thermal.get('reason') or thermal.get('issues')
                                  or thermal.get('missing') or thermal.get('status'))}
        return evaluate_uniform_fire_member(c, thermal=thermal, member_spec=spec)
    result = scan_member_time_history(times, evaluate)
    return {**result,
        'integration_version': VERSION,
        'column_id': column.get('id'),
        'requested_fire_duration_minutes': float(end),
        'time_step_minutes': float(step_minutes),
        'fire_design_actions_reused_without_recombination': True,
        'longitudinal_thermal_mode': spec.get('thermal_longitudinal_mode'),
        'column_signature_sha256': hashlib.sha256(signature.encode()).hexdigest(),
        'normative_claim': False, 'fire_resistance_status': 'not_demonstrated'}
