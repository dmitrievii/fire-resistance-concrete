"""Plotly section view for one R0.5 project column.

Reuses the original R0.8 dimensioned drawing so single and multi-column
interfaces share the same physical coordinates, dimensions and hover logic.
The chart is derived from canonical project state; it never stores a second
editable copy of reinforcement or fabricates temperatures without a run.
"""
from __future__ import annotations

from section_drawing import dimensioned_figure


def section_data(column):
    return {
        "geometry": {
            "b_m": float(column["b_mm"])/1000.0,
            "h_m": float(column["h_mm"])/1000.0,
        },
        "variants": [{
            "id": "section",
            "bars": [{
                "id": str(bar["id"]),
                "x_m": float(bar["x_mm"])/1000.0,
                "y_m": float(bar["y_mm"])/1000.0,
                "diameter_mm": float(bar["diameter_mm"]),
            } for bar in column["bars"]],
        }],
    }


def make_section_figure(column, calculation=None, *,
                        show_dimensions=True, show_ids=True):
    data = section_data(column)
    result = None
    if calculation and calculation.get("results"):
        # Temperature field depends on geometry and fire, not section loads.
        # Use the first computed section, if one exists. Do not substitute
        # artificial zeros or reference temperatures when no section is ready.
        section = next(iter(calculation["results"].values()))
        if section.get("bars"):
            result = {
                "engine": "k18-parametric-experimental",
                "variants": {"section": section},
            }
    fig = dimensioned_figure(data, 0, result,
        show_dimensions=show_dimensions, show_ids=show_ids)
    fig.update_layout(title={"text":
        f"{column['name']} · {float(column['b_mm']):g} × "
        f"{float(column['h_mm']):g} мм · {len(column['bars'])} стержней"})
    return fig
