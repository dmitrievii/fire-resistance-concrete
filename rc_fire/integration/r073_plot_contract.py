"""R0.7.3 public-result visualization contract and legacy JSON compatibility.

A previous Streamlit session may carry a valid calculation whose timeline
predates the bars_C and strength-retention fields. The current renderer
must NEVER raise KeyError or silently fabricate temperature / strength.
Fallback temperatures are taken only from the exact same-time, source
calculation audit already stored in that record, never interpolated.
"""
from __future__ import annotations

import math
import pandas as pd

TEMPERATURE_KEYS={
    "gas_C":"Температура газа",
    "concrete_surface_C":"Поверхность бетона",
    "concrete_centre_C":"Центр бетона",
}


def _real_number(value):
    if isinstance(value,bool) or value is None:
        return float("nan")
    try:
        result=float(value)
    except (ValueError,TypeError):
        return float("nan")
    return result if math.isfinite(result) else float("nan")


def _matching_audit_rebar_map(record, minute):
    audit=(record.get("full_internal_audit") or {}) if isinstance(record,dict) else {}
    for row in audit.get("samples") or []:
        if not isinstance(row,dict):
            continue
        try:
            t=float(row["time_minutes"])
        except (KeyError,TypeError,ValueError):
            continue
        if math.isfinite(t) and abs(t-minute)<1e-8:
            candidates=row.get("T_reinforcement_C")
            return candidates if isinstance(candidates,dict) else {}
    return {}


def prepare_temperature_chart(report,bar_ids):
    """Return (plot, absent_bar_ids, rows_using_source_audit).

    Only samples at the exact same fire minute can be borrowed from
    full_internal_audit. An older record may have no rod history at all:
    in that case the gas/concrete chart remains available and the bars
    are explicitly reported as unavailable, not set to zero.
    """
    raw=(report.get("timeline") or []) if isinstance(report,dict) else []
    if not isinstance(raw,(list,tuple)):
        raw=[]
    requested=[str(x) for x in bar_ids]
    names={bar_id:"Арматура "+bar_id for bar_id in requested}
    output=[]
    audit_source_rows=0
    for row in raw:
        if not isinstance(row,dict):
            continue
        minute=_real_number(row.get("minute"))
        if not math.isfinite(minute):
            continue
        values={"minute":minute}
        for key,label in TEMPERATURE_KEYS.items():
            values[label]=_real_number(row.get(key))
        bars=row.get("bars_C")
        if not isinstance(bars,dict):
            bars=_matching_audit_rebar_map(report,minute)
            if bars:
                audit_source_rows+=1
        for bar_id,display in names.items():
            values[display]=_real_number(bars.get(bar_id)) if isinstance(bars,dict) else float("nan")
        output.append(values)
    if not output:
        return pd.DataFrame(),requested,0
    plot=pd.DataFrame(output).set_index("minute").sort_index()
    # Retain only real calculated series; never plot a missing bar as zero.
    # Also signal a partial time history: missing a single sample is not
    # equivalent to a fully computed steel-temperature curve.
    missing=[bar_id for bar_id,display in names.items()
             if plot[display].isna().any()]
    absent=[bar_id for bar_id,display in names.items()
            if plot[display].isna().all()]
    for bar_id in absent:
        plot=plot.drop(columns=names[bar_id])
    plot=plot.dropna(axis=1,how="all")
    return plot,missing,audit_source_rows


def prepare_optional_percent_chart(report, field_to_label):
    """No KeyError for old result structures lacking new output columns."""
    raw=(report.get("timeline") or []) if isinstance(report,dict) else []
    if not isinstance(raw,(list,tuple)):
        raw=[]
    data=[]
    for row in raw:
        if not isinstance(row,dict):
            continue
        minute=_real_number(row.get("minute"))
        if not math.isfinite(minute):
            continue
        point={"minute":minute}
        for key,label in field_to_label.items():
            point[label]=_real_number(row.get(key))
        data.append(point)
    if not data:
        return pd.DataFrame()
    chart=pd.DataFrame(data).set_index("minute").sort_index()
    return chart.dropna(axis=1,how="all")


def _render_value(x):
    if isinstance(x,bool):
        return str(x)
    if isinstance(x,(int,float)) and math.isfinite(float(x)):
        if float(x).is_integer():
            return str(int(x))
        return f"{x:g}".replace(".",",")
    return str(x)


def engineering_input_help(label,widget,kwargs,existing_help):
    """Actual UI limits vs normative values; selectable enumerations shown."""
    items=[]
    if existing_help:
        items.append(str(existing_help))
    if widget=="number_input":
        lo=kwargs.get("min_value")
        hi=kwargs.get("max_value")
        if lo is not None and hi is not None:
            items.append(
                "Диапазон значений, допускаемый этой формой: "
                f"{_render_value(lo)}–{_render_value(hi)}.")
        elif lo is not None:
            items.append("Диапазон значений в форме: от "+_render_value(lo)+".")
        elif hi is not None:
            items.append("Диапазон значений в форме: до "+_render_value(hi)+".")
        value=kwargs.get("value")
        if value is not None:
            items.append("Начальное значение: "+_render_value(value)+
                         " (пример, не универсальная нормативная рекомендация).")
        step=kwargs.get("step")
        if step is not None:
            items.append("Шаг ввода: "+_render_value(step)+".")
    elif widget=="selectbox":
        opts=kwargs.get("_options_for_tooltip")
        if opts is not None:
            format_func=kwargs.get("format_func")
            rendered=[]
            for option in opts:
                try:
                    label_value=format_func(option) if callable(format_func) else option
                except (ValueError,TypeError):
                    label_value=option
                rendered.append(str(label_value))
            if rendered:
                items.append("Доступные значения: "+", ".join(rendered)+".")
            index=kwargs.get("index",0)
            if index is not None and 0<=index<len(rendered):
                items.append("Выбрано по умолчанию: "+rendered[index]+".")
    return "\n\n".join(items)
