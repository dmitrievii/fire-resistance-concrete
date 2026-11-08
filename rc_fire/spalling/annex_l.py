"""Belarus SP 2.02.05-2026 Annex L, equations L.1–L.6 and Tables L.1–L.2.

The only calculation sources are Belarus SP 2.02.05-2026 and SP 5.03.01-2020.
No Russian SP468 or historical Mathcad coefficient is used.

For exact, text-grounded evaluation of Wc, Table L.2 nodes are accepted
without interpolation. Equation L.5 has an unresolved percent-vs-fraction
presentation ambiguity, so it is NOT silently used as a default.
"""
from __future__ import annotations

import math
from rc_fire.materials import resolve_materials
from rc_fire.materials.normative import concrete_thermal_strain_coefficients
from rc_fire.thermal.normative import property_K1

VERSION="R0.6.8-BY-annex-L-source-first-v1"
SOURCE="СП 2.02.05-2026, приложение Л, с. 150–151, Л.1–Л.6"
ALPHA_F=1.16e-2
BETA=0.6
# Table L.1: K1c, MN m**(-3/2), natural sand plus identified coarse aggregate.
TABLE_L1={
    "siliceous":{35.:0.47,50.:0.53},
    "calcareous":{35.:0.39,50.:0.44},
    "expanded_clay":{35.:0.31,50.:0.32},
}
# Table L.2: Wc × 10^2, kg/kg. Columns RH 15, 25, 50, 75%.
TABLE_L2={
    200.:{15.:0.5,25.:0.6,50.:0.9,75.:1.2},
    300.:{15.:0.9,25.:1.0,50.:1.3,75.:2.5},
    400.:{15.:1.2,25.:1.5,50.:2.1,75.:3.0},
    500.:{15.:1.5,25.:2.0,50.:2.7,75.:3.8},
    700.:{15.:2.1,25.:3.0,50.:3.9,75.:5.4},
}
EXTRA_FIELDS={
    "natural_sand_confirmed","coarse_aggregate_volume_pct","max_aggregate_mm",
    "cement_kg_m3","water_cement_ratio","relative_humidity_pct",
    "measured_Wc_kg_kg","moisture_measurement_source",
}
LEGACY_INPUTS={
    "aggregate_pct":"coarse_aggregate_volume_pct",
    "cement_kg_m3":"cement_kg_m3",
    "water_cement_ratio":"water_cement_ratio",
    "design_relative_humidity_pct":"relative_humidity_pct",
    "max_aggregate_mm":"max_aggregate_mm",
}
class AnnexLError(ValueError):
    pass


def _positive_number(v,name,*,strict=True):
    if v is None or isinstance(v,bool):raise AnnexLError(f"{name}: отсутствует")
    try:x=float(v)
    except (TypeError,ValueError) as exc:raise AnnexLError(f"{name}: требуется число") from exc
    if not math.isfinite(x) or (x<=0 if strict else x<0):
        raise AnnexLError(f"{name}: недопустимое значение")
    return x


def physical_inputs(column):
    """Reuse the actual canonical material + thermal values once only.

    Pre-R0.6.8 user-entered physical quantities in the archived spalling
    editor may be adopted as *inputs*, never as foreign normative results.
    """
    explicit=dict(column.get("annex_l_spec") or {})
    if not isinstance(explicit,dict) or set(explicit)-EXTRA_FIELDS:
        raise AnnexLError("Недопустимые поля спецификации приложения Л")
    legacy=column.get("spalling") or {}
    old_used=[]
    for old,new in LEGACY_INPUTS.items():
        if explicit.get(new) is None and legacy.get(old) is not None:
            explicit[new]=legacy[old]
            old_used.append(new)
    if explicit.get("natural_sand_confirmed") is None:
        # Only explicitly selected physical composition can substantiate
        # 'natural sand' under Table L.1; never infer this from silica family.
        if legacy.get("aggregate_type") in (
            "natural_sand_granite","natural_sand_siliceous",
            "natural_sand_calcareous","natural_sand_limestone",
            "natural_sand_expanded_clay"):
            explicit["natural_sand_confirmed"]=True
            old_used.append("natural_sand_confirmed")
    tp=column.get("thermal_spec") or {}
    mat=(column.get("material_spec") or {}).get("concrete") or {}
    return {
        **explicit,
        "dry_density_kg_m3":tp.get("dry_density_kg_m3"),
        "aggregate_family":tp.get("concrete_family") or mat.get("aggregate_family"),
        "fine_grained":mat.get("fine_grained"),
        "concrete_strength_class":column.get("concrete"),
        "explicit_thermal_moisture_mass_pct":tp.get("moisture_mass_pct"),
        "legacy_user_input_fields":old_used,
    }


def coefficient_K1c(family,coarse_pct,max_size_mm):
    if family not in TABLE_L1:
        raise AnnexLError("Таблица Л.1: вид заполнителя не представлен")
    pct=_positive_number(coarse_pct,"Содержание крупного заполнителя")
    if not 35<=pct<=50:
        raise AnnexLError("Таблица Л.1 допускает 35–50 % крупного заполнителя")
    size=_positive_number(max_size_mm,"Наибольшая крупность заполнителя")
    lo,hi=TABLE_L1[family][35.],TABLE_L1[family][50.]
    k=lo+(hi-lo)*(pct-35)/15.
    factor=1.14 if size>10 else 1.
    # For lightweight mixes Annex L demands an additional factor 1.4;
    # lightweight also needs explicitly resolved Ec/porosity. Do not
    # accidentally allow a heavy-mix computation with expanded clay.
    if family=="expanded_clay":
        raise AnnexLError("Керамзитобетон: требуется дополнительная квалификация пористости и Eс")
    return k*factor,{"base":k,"grain_factor":factor,
                      "interpolation":"Л.1, примечание 3" if pct not in (35,50) else "таблица Л.1"}


def moisture_wc(cement,humidity,measured=None,measurement_source=None):
    if measured is not None:
        if not measurement_source:
            raise AnnexLError("Укажите источник измеренной массовой влажности Wc")
        w=_positive_number(measured,"Измеренная влажность Wc")
        if not 0<w<1:raise AnnexLError("Wc должна быть долей кг/кг")
        return w,"documented_measurement",{"measurement_source":measurement_source}
    c=_positive_number(cement,"Расход цемента")
    rh=_positive_number(humidity,"Относительная влажность воздуха")
    if c not in TABLE_L2 or rh not in TABLE_L2[c]:
        raise AnnexLError("Таблица Л.2: указанная пара цемент/RH не табулирована. "
            "Интерполяция в Л.2 не предписана; требуется подтверждённая влажность Wc "
            "либо отдельное нормативное разрешение неоднозначности единиц формулы Л.5")
    return TABLE_L2[c][rh]*1e-2,"table_L2_exact",{"cement_kg_m3":c,"rh_pct":rh}


def porosity_np(cement,wc_ratio):
    c=_positive_number(cement,"Расход цемента")
    ratio=_positive_number(wc_ratio,"Водоцементное отношение")
    if ratio>=0.4:return c*(ratio-0.2)*1e-3,"Л.2"
    return c*ratio*0.8e-3,"Л.3"


def evaluate_annex_l(column,*,material_result=None):
    """Pure, source-specific criterion. No global R90 approval from this index."""
    out={"version":VERSION,"source":SOURCE,"status":"not_evaluated",
         "normative_claim":False,"fire_resistance_status":"not_demonstrated",
         "F":None,"protection_required":None}
    try:
        x=physical_inputs(column)
        out["resolved_inputs"]=x
        if x["natural_sand_confirmed"] is not True:
            raise AnnexLError("Таблица Л.1: подтвердите наличие природного песка")
        if x["fine_grained"] is True:
            raise AnnexLError("Мелкозернистый бетон: таблица Л.1 для крупного заполнителя неприменима")
        fam=x["aggregate_family"]
        tp=column.get("thermal_spec") or {}
        mat=(column.get("material_spec") or {}).get("concrete") or {}
        if tp.get("concrete_family") and mat.get("aggregate_family") and (
            tp["concrete_family"]!=mat["aggregate_family"]):
            raise AnnexLError("Заполнители материала и теплотехники не совпадают")
        density=_positive_number(x["dry_density_kg_m3"],"Сухая плотность ρ0")
        k1c,k_note=coefficient_K1c(fam,x.get("coarse_aggregate_volume_pct"),
                                  x.get("max_aggregate_mm"))
        cement=_positive_number(x.get("cement_kg_m3"),"Цемент")
        ratio=_positive_number(x.get("water_cement_ratio"),"В/Ц")
        n,por_src=porosity_np(cement,ratio)
        if n<=0:raise AnnexLError("Л.2/Л.3: нулевая или отрицательная пористость")
        wc,moist_src,moist_note=moisture_wc(cement,x.get("relative_humidity_pct"),
                x.get("measured_Wc_kg_kg"),x.get("moisture_measurement_source"))
        matres=material_result or resolve_materials(column)
        E=(matres.get("concrete") or {}).get("E_cm_GPa")
        if E is None or matres.get("status")!="resolved_for_property_lookup":
            raise AnnexLError("Eс не разрешён по СП 5.03.01-2020, табл. 6.3")
        E_MPa=float(E)*1000.
        Wz=wc*(density*(1+wc))*1e-3
        # Values in formulas L.1 are temperature-specific in 200–300 C.
        profiles=[]
        for temp in (200.,250.,300.):
            alpha=concrete_thermal_strain_coefficients(fam,temp)["alpha_bt_per_C"]
            lam=property_K1(fam,temp)["lambda_W_mK"]
            F=ALPHA_F*alpha*BETA*E_MPa*density*Wz/(k1c*lam*n)
            if not math.isfinite(F) or F<0:raise AnnexLError("Некорректный результат Л.1")
            profiles.append({"temperature_C":temp,"alpha_bt_1_C":alpha,
                             "lambda_W_mC":lam,"F":F})
        maximum=max(profiles,key=lambda r:r["F"])
        value=maximum["F"]
        out.update({"status":"calculated_method_scope","F":value,
            "classification":("F_le_4" if value<=4 else "F_4_to_6" if value<=6 else "F_gt_6"),
            "protection_required":value>4,
            "formula":"Л.1","temperature_range_C":[200,300],
            "temperature_profile":profiles,"critical_temperature_C":maximum["temperature_C"],
            "coefficients":{"alpha_F":ALPHA_F,"beta":BETA,"Ec_MPa":E_MPa,
                "rho0_kg_m3":density,"rho_kg_m3":density*(1+wc),
                "Wc_kg_kg":wc,"Wz_m3_m3":Wz,
                "K1c_MN_m3_2":k1c,"np_percent_from_L2_L3":n},
            "provenance":{"K1c":k_note,"porosity":por_src,
                "Wc":moist_src,"Wc_details":moist_note,
                "alpha_bt":"СП 2.02.05-2026, таблица 11",
                "lambda":"СП 2.02.05-2026, приложение К, таблица К.1/формула К.2",
                "Ecm":"СП 5.03.01-2020, таблица 6.3",
                "legacy_fields_reused_as_physical_inputs_only":x["legacy_user_input_fields"]}})
    except (AnnexLError,ValueError,TypeError,KeyError) as exc:
        out.update({"status":"blocked_input_or_scope","reason":str(exc),"protection_required":None})
    return out
