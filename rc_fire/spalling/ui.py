"""Streamlit UI for Belarus Annex L, using ONE material/thermal source."""
from __future__ import annotations
import pandas as pd
from .annex_l import physical_inputs, TABLE_L2


# R0.6.8.2: field-level help refers exclusively to Belarus Annex L and
# actual calculator validation. Physical input ranges are distinguished
# from a table's narrower numerical applicability. Never reuse SP468 ranges.
RANGE_HINTS_RELEASE = "r0682-belarus-input-range-tooltips-v1"
RANGE_HINTS = {
    "coarse_aggregate_volume_pct":
        "Допустимый ввод состава: 0–100 % по объёму. Для расчёта F "
        "по таблице Л.1 применимы только 35–50 %; внутри этого интервала "
        "предусмотрена интерполяция K₁c. При 0 % бетон определяется как "
        "мелкозернистый, и проверка F по этой строке Л.1 неприменима.",
    "cement_kg_m3":
        "Допустимое числовое значение: Ц > 0 кг/м³. Таблица Л.2 содержит "
        "узлы Ц = 200, 300, 400, 500, 700 кг/м³. Ограничение таблицы "
        "не является границей формулы Л.5. При Ц = 100 кг/м³ расчёт "
        "по Л.5 диагностический, с предупреждением о единицах и "
        "выходе за табличный диапазон.",
    "max_aggregate_mm":
        "Введите положительную крупность (> 0 мм) по составу бетона. "
        "По примечанию к таблице Л.1 при крупности > 10 мм применяется "
        "множитель 1,14. Согласуйте размер с указанным заполнителем "
        "для Ecm (гравий/гранитный щебень до 40 мм).",
    "water_cement_ratio":
        "В/Ц > 0; это безразмерное отношение массы воды к массе цемента. "
        "При В/Ц ≥ 0,4 пористость определяется по Л.2, при В/Ц < 0,4 — "
        "по Л.3. Для Л.5 расход воды В = Ц × (В/Ц) в кг/м³. "
        "Не следует переносить диапазон российского СП 468.",
    "relative_humidity_pct":
        "Физически допустимый ввод 0 < RH ≤ 100 %. Таблица Л.2 "
        "имеет узлы RH = 15, 25, 50, 75 %. При промежуточных RH "
        "автоматически используется Л.5 с отдельным предупреждением "
        "об интерпретации единиц. Интерполяция Л.2 — только исследовательская.",
    "measured_Wc_kg_kg":
        "Если задана измеренная влажность: 0 < Wc < 1 кг/кг "
        "(например, 0,025 кг/кг = 2,5 %). Укажите источник измерения. "
        "Это отдельное поле от влажности воздуха RH и от Wc теплотехники К.",
    "moisture_measurement_source":
        "Заполняется обязательно при вводе измеренной Wc: "
        "протокол измерений, паспорт смеси или иной проверяемый источник.",
    "moisture_mode":
        "Авто: точный табличный узел Л.2, иначе формула Л.5. "
        "Л.5 использует Ц и В в кг/м³; перевод результата в кг/кг "
        "пока требует проверки. Интерполяция Л.2 доступна "
        "только в исследовательском режиме.",
}

def _float_text(v):
    return "" if v is None else f"{float(v):g}"


def render_annex_l_inputs(st,project,column,safe_change,update_annex_l_spec):
    cid=column["id"]
    try:
        inputs=physical_inputs(column)
    except ValueError as exc:
        st.error(f"Приложение Л: {exc}")
        return
    with st.expander("Хрупкое разрушение бетона — приложение Л СП 2.02.05-2026",expanded=False):
        st.caption("Используется только белорусский СП 2.02.05-2026, Л.1–Л.6 и таблицы Л.1–Л.2. "
                   "Плотность ρ₀, тип заполнителя, класс бетона, Ecm и теплофизические "
                   "коэффициенты берутся из общей карточки материала и расчёта нагрева.")
        shown=[
           ("Плотность сухого бетона, кг/м³",inputs.get("dry_density_kg_m3")),
           ("Заполнитель для теплотехники",inputs.get("aggregate_family")),
           ("Класс бетона",inputs.get("concrete_strength_class")),
           ("Явно введённая массовая влажность (теплотехника), %",inputs.get("explicit_thermal_moisture_mass_pct")),
        ]
        st.dataframe(pd.DataFrame([{"Параметр":k,"Общее значение":("—" if v is None else str(v))}
                                   for k,v in shown]),hide_index=True,use_container_width=True)
        st.caption("Общие свойства изменяются выше в разделах R0.6.1 и R0.6.2 — "
                   "второй экземпляр плотности или типа заполнителя отсутствует.")
        kind=inputs.get("fine_grained_classification") or {}
        if kind.get("status")=="resolved":
            st.caption("Тип бетона определён автоматически: "+
                ("мелкозернистый" if kind.get("fine_grained") else "с крупным заполнителем")+
                " ("+str(kind.get("source"))+").")
        else:
            st.warning("Тип бетона пока не определён из состава: "+
                       str(kind.get("reason","нет сведений о заполнителе")))
        if inputs.get("natural_sand_requires_confirmation"):
            st.warning("Для диагностического расчёта принято наличие природного песка "
                       "по умолчанию. Это не подтверждённый факт состава смеси: "
                       "проверьте проектную спецификацию и сохраните данные. "
                       "До подтверждения F помечается как рассчитанный с допущением.")
        if inputs.get("legacy_user_input_fields"):
            st.info("Ранее введённые физические данные смеси доступны для переноса: "+
                ", ".join(inputs["legacy_user_input_fields"])+". "
                "Результат и коэффициенты российского расчёта не используются.")
        with st.form(f"by_annex_l_{cid}_{project['revision']}"):
            sand=st.checkbox("В составе заполнителя действительно использован природный песок",
                value=inputs.get("natural_sand_confirmed") is True,
                help="Положительное значение по умолчанию — предположение для "
                     "диагностического расчёта. Сохранение подтверждает "
                     "состав со слов пользователя; проверка документации обязательна.")
            c1,c2,c3=st.columns(3)
            with c1:
                coarse=st.text_input("Объём крупного заполнителя, % (0–100)",
                    value=_float_text(inputs.get("coarse_aggregate_volume_pct")),
                    help=RANGE_HINTS["coarse_aggregate_volume_pct"])
                cement=st.text_input("Расход цемента, кг/м³",
                    value=_float_text(inputs.get("cement_kg_m3")),
                    help=RANGE_HINTS["cement_kg_m3"])
            with c2:
                size=st.text_input("Максимальная крупность заполнителя, мм",
                    value=_float_text(inputs.get("max_aggregate_mm")),
                    help=RANGE_HINTS["max_aggregate_mm"])
                wc=st.text_input("Водоцементное отношение В/Ц",
                    value=_float_text(inputs.get("water_cement_ratio")),
                    help=RANGE_HINTS["water_cement_ratio"])
            with c3:
                rh=st.text_input("Относительная влажность воздуха RH, %",
                    value=_float_text(inputs.get("relative_humidity_pct")),
                    help=RANGE_HINTS["relative_humidity_pct"])
                measured=st.text_input("Измеренная Wc, кг/кг (необязательно)",
                    value=_float_text(inputs.get("measured_Wc_kg_kg")),
                    help=RANGE_HINTS["measured_Wc_kg_kg"])
            moisture_source=st.text_input("Источник измеренной Wc (если указана)",
                value=inputs.get("moisture_measurement_source") or "",
                help=RANGE_HINTS["moisture_measurement_source"])
            methods=("auto","formula_L5","linear_L2_exploratory")
            mode=st.selectbox("Метод определения влажности Wc",
                methods,index=methods.index(inputs.get("moisture_mode")
                                              if inputs.get("moisture_mode") in methods else "auto"),
                format_func=lambda x:{
                    "auto":"Таблица Л.2 в точных узлах; иначе формула Л.5",
                    "formula_L5":"Формула Л.5 (с явной интерпретацией единиц)",
                    "linear_L2_exploratory":"Линейная интерполяция Л.2 (исследовательская)"}[x],
                help=RANGE_HINTS["moisture_mode"])
            st.caption("Для Л.5 вводятся расходы цемента Ц и воды В=Ц·(В/Ц), кг/м³. "
                       "Численный результат Л.5 находится в масштабе процентов; "
                       "перевод в кг/кг (/100) обозначен как интерпретация единиц, "
                       "не подтверждённая независимым нормативным разъяснением. "
                       "Интерполяция таблицы Л.2 прямо не предписана. "
                       "Оба нетабличных маршрута сохраняют предупреждение в Preflight.")
            if st.form_submit_button("Сохранить недостающие характеристики смеси по приложению Л"):
                def convert(x,title):
                    if not x.strip():return None
                    try:return float(x.replace(",","."))
                    except ValueError:raise ValueError(f"{title}: неверное число")
                try:
                    payload={
                        "natural_sand_confirmed":sand,
                        "coarse_aggregate_volume_pct":convert(coarse,"Содержание заполнителя"),
                        "max_aggregate_mm":convert(size,"Крупность заполнителя"),
                        "cement_kg_m3":convert(cement,"Расход цемента"),
                        "water_cement_ratio":convert(wc,"В/Ц"),
                        "relative_humidity_pct":convert(rh,"RH"),
                        "measured_Wc_kg_kg":convert(measured,"Wc"),
                        "moisture_measurement_source":moisture_source.strip() or None,
                        "moisture_mode":mode,
                    }
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    safe_change(update_annex_l_spec,project,cid,payload)


def render_annex_l_results(st,calc):
    r=calc.get("annex_l") or {}
    st.markdown("**Хрупкое разрушение бетона — приложение Л СП 2.02.05-2026**")
    if r.get("status")!="calculated_method_scope":
        st.info("Расчёт F по приложению Л не завершён: "+r.get("reason","не хватает исходных данных"))
        return
    F=r["F"]
    st.metric("F — СП 2.02.05-2026, приложение Л",f"{F:.4f}")
    if not r.get("natural_sand_verified",True):
        st.warning("F рассчитан с предположением о природном песке, "
                   "которое принято положительным по умолчанию, "
                   "но ещё не подтверждено пользователем и проектной документацией.")
    if F<=4:st.caption("F ≤ 4: хрупкое разрушение по критерию не прогнозируется.")
    elif F<=6:st.warning("4 < F ≤ 6: потенциально опасный диапазон; по Л.6 меры защиты нужны уже при F>4.")
    else:st.error("F > 6: прогнозируется хрупкое разрушение; по Л.6 требуются защитные мероприятия.")
    m=(r.get("provenance") or {}).get("Wc") or ""
    w=(r.get("coefficients") or {}).get("Wc_kg_kg")
    st.caption("Источник Wc: "+str(m)+
        ("; Wc="+f"{w:.5f}"+" кг/кг" if w is not None else "")+".")
    if not r.get("moisture_method_qualified",True):
        st.warning("Метод определения Wc требует дополнительного нормативного обоснования: "
                   "либо Л.5 с явной интерпретацией единиц, либо инженерная интерполяция Л.2. "
                   "Результат F диагностический, не нормативное подтверждение.")
    st.caption("Вычислено для температур 200, 250, 300 °C; показано наибольшее F. "
               "Данные и формулы взяты только из белорусских СП. "
               "Критерий F не подтверждает огнестойкость R90.")
    st.dataframe(pd.DataFrame([
        {"T, °C":x["temperature_C"],"αbt, 1/°C":x["alpha_bt_1_C"],
         "λ, Вт/(м·°C)":x["lambda_W_mC"],"F":x["F"]}
        for x in r["temperature_profile"]
    ]),hide_index=True,use_container_width=True)
