"""R0.7.4 public heating-section plot from the ACTUAL TKP 2D FVM field.

Restores the useful R0.6.2 thermal cross-section visualization without
resurrecting the archived SP Annex K temperature model or its phase UI.
Every displayed value comes from one stored time-stamped solver snapshot;
no new heat solve, temperature lookup, fictitious radial fit, or normative
capacity inference is performed here.
"""
from __future__ import annotations

import math
import numpy as np
import plotly.graph_objects as go


def _finite(value,name):
    if isinstance(value,bool):
        raise ValueError(f"{name}: finite number required")
    try:
        n=float(value)
    except (ValueError,TypeError) as exc:
        raise ValueError(f"{name}: finite number required") from exc
    if not math.isfinite(n):
        raise ValueError(f"{name}: finite number required")
    return n


def make_tkp_section_heatmap(column,frame,grid,*,color_max_C=None,
                             draw_isotherm_500=True):
    """Physical cell-centred concrete heatmap with actual steel temperatures.

    The colour is the cell-centre temperature, not an arbitrarily smoothed
    nodal reconstruction. The 500 C isoline, when available, is interpolated
    for display only and does NOT imply the SP Annex K isotherm capacity
    method applies to this bar arrangement.
    """
    if not isinstance(column,dict) or not isinstance(frame,dict) or not isinstance(grid,dict):
        raise ValueError("column, thermal frame and grid must be dictionaries")
    source=frame.get("temperature_source")
    if source not in ("FVM initial condition t=0",
                      "TKP 2D FVM solved snapshot"):
        raise ValueError("Only a source-labelled TKP finite-volume temperature snapshot can be plotted")
    nx=int(grid["nx"]);ny=int(grid["ny"])
    if not 4<=nx<=80 or not 4<=ny<=80:
        raise ValueError("invalid TKP 2D grid size")
    b=_finite(column["b_mm"],"section b")
    h=_finite(column["h_mm"],"section h")
    if b<=0 or h<=0:
        raise ValueError("section dimensions must be positive")
    dx=_finite(grid["dx_mm"],"dx")
    dy=_finite(grid["dy_mm"],"dy")
    if abs(dx*nx-b)>1e-6 or abs(dy*ny-h)>1e-6:
        raise ValueError("source grid does not match the column geometry")
    z=np.asarray(frame.get("grid_temperature_C"),dtype=float)
    if z.shape!=(ny,nx) or not np.all(np.isfinite(z)):
        raise ValueError("missing or nonfinite 2D thermal cell field")
    gas=_finite(frame["gas_C"],"fire gas temperature")
    time=_finite(frame["minute"],"time")
    if time<0 or np.min(z)<20.-1e-5 or np.max(z)>gas+1e-5:
        raise ValueError("heat field violates the TKP temperature domain")
    if color_max_C is None:
        cmax=max(25.,gas)
    else:
        cmax=max(25.,_finite(color_max_C,"colour upper scale"))
    xs=(np.arange(nx)+.5)*dx
    ys=(np.arange(ny)+.5)*dy
    fig=go.Figure()
    fig.add_trace(go.Heatmap(
        x=xs.tolist(),y=ys.tolist(),z=z.tolist(),
        zmin=20.,zmax=cmax,colorscale="Inferno",
        colorbar={"title":"°C"},
        hovertemplate="x=%{x:.1f} мм; y=%{y:.1f} мм; "
                      "Tбетона=%{z:.1f} °C<extra></extra>",
        name="Поле бетона"))
    if draw_isotherm_500 and float(np.min(z))<500.<float(np.max(z)):
        fig.add_trace(go.Contour(
            x=xs.tolist(),y=ys.tolist(),z=z.tolist(),
            contours={"start":500.,"end":500.,"size":1.,"coloring":"none",
                      "showlabels":True,"labelfont":{"size":11,"color":"white"}},
            line={"color":"cyan","width":2},
            showscale=False,hoverinfo="skip",
            name="Изотерма 500 °C (только визуализация)"))
    fig.add_shape(type="rect",x0=0,y0=0,x1=b,y1=h,
                  line={"color":"white","width":2})
    bar_map=frame.get("bars_C") or {}
    if not isinstance(bar_map,dict):
        bar_map={}
    bx=[];by=[];labels=[];custom=[]
    for bar in column.get("bars") or []:
        name=str(bar["id"])
        x=_finite(bar["x_mm"],f"{name}.x")
        y=_finite(bar["y_mm"],f"{name}.y")
        diameter=_finite(bar["diameter_mm"],f"{name}.diameter")
        if diameter<=0 or not 0<=x<=b or not 0<=y<=h:
            raise ValueError(f"bar {name} outside the actual section")
        r=diameter/2.
        fig.add_shape(type="circle",
            x0=x-r,y0=y-r,x1=x+r,y1=y+r,
            line={"color":"#00d5e6","width":2},fillcolor="rgba(0,0,0,0)")
        temperature=bar_map.get(name)
        if temperature is None:
            description=f"{name}: температура отсутствует"
        else:
            th=_finite(temperature,name+" temperature")
            if th<20.-1e-5 or th>gas+1e-5:
                raise ValueError(f"{name}: bar temperature outside source domain")
            description=f"{name}: {th:.1f} °C"
        bx.append(x);by.append(y);labels.append(name)
        custom.append(description+f"; Ø{diameter:g} мм")
    if bx:
        fig.add_trace(go.Scatter(
            x=bx,y=by,mode="markers+text",
            text=labels,textposition="top center",
            marker={"size":8,"color":"#00d5e6",
                    "line":{"color":"black","width":1}},
            customdata=custom,hovertemplate="%{customdata}<extra></extra>",
            name="Расположение арматуры",showlegend=False))
    fig.update_layout(
        title={"text":f"Температурное поле бетона при t = {time:g} мин"},
        height=515,margin={"l":20,"r":20,"t":60,"b":20},
        xaxis={"title":"x, мм","range":[-max(20.,b*.06),b+max(20.,b*.06)]},
        yaxis={"title":"y, мм","range":[-max(20.,h*.06),h+max(20.,h*.06)],
               "scaleanchor":"x","scaleratio":1},
        plot_bgcolor="#151515",
        meta={"temperature_method":"TKP_4.3.2_FVM",
              "time_minutes":time,"grid_nx":nx,"grid_ny":ny,
              "visual_iso_500_is_not_normative_capacity":True},
        legend={"orientation":"h"})
    return fig
