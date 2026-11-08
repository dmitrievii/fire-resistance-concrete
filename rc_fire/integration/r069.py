"""Fixed fire-design actions → Annex K at each time → coupled member ULS."""
from __future__ import annotations

import copy
import hashlib
import json

from .r067 import evaluate_uniform_fire_member, validate_member_spec
from rc_fire.member.time_history import VERSION, scan_fire_history, validate_time_controls
from rc_fire.thermal import evaluate_rectangular_column


def history_input_sha256(column):
    """All source data, not just the old mechanics signature, invalidate output."""
    return hashlib.sha256(json.dumps({"version": VERSION, "column": column},
        ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest()


def evaluate_uniform_fire_history(column, *, end_minutes=None, step_minutes=5.,
                                  tolerance_minutes=.25, max_refinements=20):
    """Preserve entered N/M and explicit support/load/uniformity assumptions.

    t=0 is always checked. Recompute Annex K and every Gauss/node law at each
    time. No 90-minute field is reused for another time, no material-table
    extrapolation and no removal of overheated fibres are introduced here.
    Longitudinally nonuniform histories need independently authored fields.
    """
    end = column.get("fire_minutes") if end_minutes is None else end_minutes
    validate_time_controls(end, step_minutes, tolerance_minutes, max_refinements)
    validate_member_spec(column.get("member_spec"))
    frozen = copy.deepcopy(column)
    source_hash = history_input_sha256(frozen)

    def evaluate(t):
        snapshot = copy.deepcopy(frozen)
        snapshot["fire_minutes"] = t
        thermal = evaluate_rectangular_column(snapshot, grid=12)
        return evaluate_uniform_fire_member(snapshot, thermal=thermal)

    result = scan_fire_history(evaluate, end_minutes=end, step_minutes=step_minutes,
        tolerance_minutes=tolerance_minutes, max_refinements=max_refinements)
    result.update({"column_id": frozen.get("id"), "source_sha256": source_hash,
        "input_column": frozen,
        "member_model": copy.deepcopy(frozen.get("member_spec") or {}),
        "section_actions": copy.deepcopy(frozen.get("sections") or []),
        "longitudinal_temperature_model": "uniform_cross_section_user_assumed",
        "initial_imperfection_model": "zero_inherited_R067_not_qualified",
        "load_pattern_constant_in_time": True})
    result["blockers"] = sorted(set(result["blockers"] + ["INITIAL_IMPERFECTION_NOT_QUALIFIED"]))
    return result
