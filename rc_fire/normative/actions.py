"""Project-wide action-input convention for Belarus RC fire resistance.

Every explicitly entered N, Mx and My is ALREADY a fire-design action for
the relevant fire situation. No second calculation or documentation of a
fire load combination is required inside this calculator.

This convention validates the *meaning* of entered values, not whether all
values are present or whether their distribution and structural supports
allow a particular member model.
"""
from __future__ import annotations

ACTION_INPUT_CONTRACT = "R0.6.8.3-user-supplied-fire-design-actions-v1"
DEFAULT_ACTION_PROVENANCE = (
    "N, Mx, My: user-entered design actions for the fire situation; "
    "no additional fire load combination performed in this application"
)


def action_source(explicit=None):
    """Optional traceability note; its absence is never a design blocker."""
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    return DEFAULT_ACTION_PROVENANCE
