"""R0.7 production-facing Streamlit interface for RC column fire calculation.

Only normal engineering inputs and results are visible. Old R0.5/0.6
research panels, independent test entrypoints and debug expanders are
deliberately not imported here.

A numerical section state is NOT by itself a valid Belarusian R rating.
The primary result remains "not established" until the whole-member
failure model and source qualification have been completed.
"""
from __future__ import annotations

import json
import pandas as pd
import streamlit as st

from multicolumn_r05.project_model import new_column
from multicolumn_r05.section_preview import make_section_figure
from rc_fire.integration.r07_inputs import make_column,perimeter_bars
from rc_fire.integration.r07_public import (
    fire_assessment,PublicFireInputError)
from rc_fire.mechanics.action_capacity import WITHIN,EXCEEDED,UNKNOWN
from rc_fire.spalling.ui import RANGE_HINTS as BELARUS_ANNEX_L_SOURCE_HELP
from rc_fire.thermal.tkp_section_plot import make_tkp_section_heatmap
from rc_fire.integration.r073_plot_contract import (
    prepare_temperature_chart,prepare_optional_percent_chart,
    split_temperature_chart,engineering_input_help)

st.set_page_config(
    page_title="Огнестойкость железобетонной колонны",
    page_icon="🏗️",layout="wide",initial_sidebar_state="collapsed")

# Multi-column authoring with independent session-state keys per construction.
# The public interface still has ONE simple set of fields for the selected
# column; old D-series panels are never exposed.
count=st.sidebar.number_input("Количество конструкций",
    min_value=1,max_value=30,value=1,step=1,key="r07_construction_count")
column_ids=[f"c{i+1}" for i in range(int(count))]
cid=st.sidebar.radio("Колонна",column_ids,
    format_func=lambda x:"К"+x[1:],key="r07_construction_select")

# Streamlit can retain the previous release's "Не установлено" widget
# value across reruns. Reset ONLY invalid legacy selections; retain any
# deliberate valid hot/cold and A/B/C choices.
for _field_name,_valid in (
    ("Изготовление арматуры",("hot_rolled","cold_worked")),
    ("Класс пластичности",("A","B","C"))):
    _widget_key=f"r07_{cid}_selectbox_{_field_name}"
    if _widget_key in st.session_state and st.session_state[_widget_key] not in _valid:
        del st.session_state[_widget_key]


# Every ordinary input has a (?) with source/meaning and a K1 example.
# Example values are NOT automatically normative recommendations.
_INPUT_HELP={
    "Обозначение колонны":"По умолчанию К1. Это имя конструкции, не нормативное значение.",
    "Ширина b, мм":"Пример К1: 600 мм; задайте фактическую ширину сечения.",
    "Высота сечения h, мм":"Пример К1: 600 мм; задайте фактический размер.",
    "Длина колонны L, м":"Пример К1: 3 м. Введите реальную длину между узлами.",
    "Расчётная длина: μx":"Пример: 1,0. Коэффициент определяется схемой закрепления и устойчивости, не автоматически.",
    "Расчётная длина: μy":"Пример: 1,0. При иной опорной схеме измените согласно проекту.",
    "Защитный слой до хомута, мм":"Пример: 20 мм до внешней поверхности хомута, НЕ до центра продольного стержня.",
    "Диаметр хомута, мм":"Пример: Ø10 мм. Укажите фактический хомут.",
    "Диаметр продольных стержней, мм":"Пример: Ø20 мм, номинальный диаметр.",
    "Стержней по верхней/нижней грани":"Пример: 3 на грани, включая углы; пересечения углов считаются один раз.",
    "Стержней по левой/правой грани":"Пример: 3 на грани, включая углы.",
    "Указать координаты отдельных стержней вместо равномерной схемы":"Включите для произвольного армирования; иначе стержни равномерно размещаются по четырём сторонам.",
    "Класс бетона":"Пример К1: C30/37. Используйте класс бетона по рабочему проекту.",
    "Тип крупного заполнителя":"Пример К1: силикатный; влияет на тепловые свойства и диаграммы бетона.",
    "Сухая плотность, кг/м³":"Пример: 2200 кг/м³. Укажите сухую плотность принятого бетона.",
    "Консистенция бетонной смеси":"Пример К1: V3–V4. Для выбора Ecm по СП 5.03.01-2020; подтвердите документацией.",
    "Твердение":"Пример: естественное. Для определения материала по СП.",
    "Основание для модуля Ecm":"Для силикатного заполнителя пример: табл. 6.3 СП (гравий/гранит до 40 мм); иначе измеренный модуль.",
    "Измеренный Ecm, ГПа":"Начальное значение 35 ГПа — демонстрационное, впишите подтверждённое испытанием значение.",
    "Класс арматуры":"Пример S500; в текущей модели используется именно S500.",
    "Изготовление арматуры":"Пример: горячекатаная S500. Температурные коэффициенты горячекатаной и холоднодеформированной арматуры различаются.",
    "Класс пластичности":"Пример: B; выбор A/B/C изменяет предельную деформацию и диаграмму.",
    "Массовая влажность бетона, %":"Пример: 1,5% от массы сухого бетона. Это не относительная влажность воздуха!",
    "Объёмная доля крупного заполнителя, %":"Пример К1: 40% объёма; параметр приложения Л СП.",
    "Наибольшая крупность заполнителя, мм":"Пример: 30 мм, фактический размер зерна для приложения Л.",
    "Расход цемента, кг/м³":"Пример К1: 500 кг/м³; нужен состав бетона.",
    "Водоцементное отношение В/Ц":"Пример К1: 0,45, безразмерное.",
    "Относительная влажность среды, %":"Пример: 44%. Нельзя подменять массовую влажность бетона этим значением.",
    "Nᶠⁱ, кН (сжатие положительно)":"Введите расчётную продольную силу при пожаре, кН. Положительная — сжатие. Пример К1: 50 кН, но нагрузка НЕ задаётся автоматически.",
    "Mxᶠⁱ, кН·м":"Введите расчётный момент относительно оси x при пожаре. Пример К1: 2 кН·м; 0 вводится явно.",
    "Myᶠⁱ, кН·м":"Введите расчётный момент относительно оси y при пожаре. Пример К1: 0 кН·м; 0 вводится явно.",
    "Требуемая огнестойкость":"Пример: R90 = 90 минут стандартного пожара. Нормативное требование берётся из задания.",
    "Слева":"По умолчанию обогрев слева; укажите реально обогреваемые поверхности.",
    "Справа":"По умолчанию обогрев справа.",
    "Снизу":"По умолчанию обогрев нижней грани сечения.",
    "Сверху":"По умолчанию обогрев верхней грани сечения.",
}


class _Fields:
    def __getattr__(self,widget):
        fn=getattr(st,widget)
        def keyed(label,*args,**kwargs):
            kwargs.setdefault("key",f"r07_{cid}_{widget}_{label}")
            help_settings=dict(kwargs)
            if widget=="selectbox":
                help_settings["_options_for_tooltip"]=(
                    args[0] if args else kwargs.get("options"))
            # Deliberately ONE short range hint per field. The old
            # Belarus normative input comments are accessible in an
            # optional materials expander below, not duplicated here.
            kwargs["help"]=engineering_input_help(
                label,widget,help_settings,
                _INPUT_HELP.get(label,"") or kwargs.get("help",""))
            return fn(label,*args,**kwargs)
        return keyed


field=_Fields()
st.title("Расчёт огнестойкости железобетонной колонны")
st.caption("Выбрана колонна: К"+cid[1:])
st.caption(
    "Беларусь · СП 2.02.05-2026 · СП 5.03.01-2020 · "
    "ТКП EN 1992-1-2-2009 с национальным приложением")
st.write(
    "Введите геометрию и материалы колонны, затем пожарные усилия и "
    "требуемую продолжительность. Все расчёты выполняются по фактически "
    "указанным значениям. Никакие комбинации усилий не создаются повторно.")

with st.form(f"column_fire_design_v07_{cid}",clear_on_submit=False):
    st.subheader("1. Геометрия и армирование")
    a,b,c=st.columns(3)
    with a:
        name=field.text_input("Обозначение колонны",value="К"+cid[1:])
        b_mm=field.number_input("Ширина b, мм",min_value=250.,max_value=2000.,
            value=600.,step=25.)
        h_mm=field.number_input("Высота сечения h, мм",min_value=250.,max_value=2000.,
            value=600.,step=25.)
    with b:
        length=field.number_input("Длина колонны L, м",min_value=1.,max_value=40.,
            value=3.,step=.25)
        mu_x=field.number_input("Расчётная длина: μx",min_value=.2,max_value=2.5,
            value=1.,step=.1,
            help="Подтвердите по реальной схеме закрепления; не определяет автоматически поведение рамы.")
        mu_y=field.number_input("Расчётная длина: μy",min_value=.2,max_value=2.5,
            value=1.,step=.1)
    with c:
        cover=field.number_input("Защитный слой до хомута, мм",min_value=5.,
            max_value=150.,value=20.,step=5.)
        tie=field.number_input("Диаметр хомута, мм",min_value=6.,max_value=40.,
            value=10.,step=2.)
        dia=field.number_input("Диаметр продольных стержней, мм",min_value=6.,
            max_value=50.,value=20.,step=2.)
    n1,n2=st.columns(2)
    with n1:
        count_x=field.number_input("Стержней по верхней/нижней грани",
            min_value=2,max_value=20,value=3,step=1)
    with n2:
        count_y=field.number_input("Стержней по левой/правой грани",
            min_value=2,max_value=20,value=3,step=1)
    manual=field.checkbox(
        "Указать координаты отдельных стержней вместо равномерной схемы",
        value=False)
    rows=None
    if manual:
        try:
            default=perimeter_bars(
                b_mm=b_mm,h_mm=h_mm,cover_mm=cover,tie_d_mm=tie,
                bar_d_mm=dia,bars_horizontal=int(count_x),
                bars_vertical=int(count_y))
            data=st.data_editor(pd.DataFrame(default),num_rows="dynamic",
                hide_index=True,use_container_width=True,
                column_config={
                    "id":st.column_config.TextColumn("№ стержня",required=True),
                    "x_mm":st.column_config.NumberColumn("x, мм",required=True),
                    "y_mm":st.column_config.NumberColumn("y, мм",required=True),
                    "diameter_mm":st.column_config.NumberColumn("Ø, мм",required=True)},
                key=f"r07_custom_bar_positions_{cid}")
            rows=data.to_dict("records")
        except (TypeError,ValueError) as exc:
            st.error("Геометрия арматуры: "+str(exc))

    st.divider()
    st.subheader("2. Материалы")
    c1,c2,c3=st.columns(3)
    with c1:
        strength=field.selectbox("Класс бетона",(
            "C20/25","C25/30","C30/37","C35/45","C40/50"),index=2)
        agg=field.selectbox("Тип крупного заполнителя",(
            "siliceous","calcareous"),
            format_func=lambda v:"Силикатный" if v=="siliceous" else "Карбонатный")
        density=field.number_input("Сухая плотность, кг/м³",min_value=800.,
            max_value=3000.,value=2200.,step=50.)
        consistency=field.selectbox("Консистенция бетонной смеси",(
            "V3_V4","V1_V2","S1_S2","S3_S5"),index=0,
            help="Для определения Ecm по таблице 6.3 СП 5.03.01-2020.")
        curing=field.selectbox("Твердение",("natural","heat"),
            format_func=lambda x:"Естественное" if x=="natural"
                                      else "Тепловая обработка")
        ecm_basis=field.selectbox("Основание для модуля Ecm",(
            "gravel_granite_upto40","measured"),
            format_func=lambda x:"СП 5.03.01, табл. 6.3 (гравий/гранит до 40 мм)"
                                 if x=="gravel_granite_upto40" else
                                 "Результат испытания бетона")
        measured_ecm=(field.number_input("Измеренный Ecm, ГПа",
            min_value=5.,max_value=90.,value=35.,step=1.)
            if ecm_basis=="measured" else None)
        if agg=="calcareous" and ecm_basis=="gravel_granite_upto40":
            st.caption("Для карбонатного заполнителя потребуется указать "
                       "доказанный модуль Ecm по испытанию.")
    with c2:
        field.text_input("Класс арматуры",value="S500",disabled=True,
            help="В этой версии нормативная библиотека допускает S500.")
        steel_route=field.selectbox("Изготовление арматуры",
            ("hot_rolled","cold_worked"),index=0,
            format_func=lambda x:{"hot_rolled":"Горячекатаная (пример)",
                "cold_worked":"Холоднодеформированная"}[x],
            help="По умолчанию горячекатаная S500 — ТОЛЬКО демонстрационное допущение. "
                 "Для действительной конструкции проверьте паспорт арматуры.")
        duct=field.selectbox("Класс пластичности",
            ("B","A","C"),index=0,
            help="По умолчанию B — ТОЛЬКО демонстрационное допущение. "
                 "Необходимо подтверждение по сертификату.")
        moisture=field.number_input("Массовая влажность бетона, %",min_value=0.,
            max_value=3.,value=1.5,step=.1,
            help="1,5% — исходное значение для демонстрационного сценария, "
                 "НЕ измеренное значение для вашей колонны.")
        st.caption("Принятый тип S500 и класс пластичности являются "
                   "исходными допущениями, пока не подтверждены документацией. "
                   "Расчёт по ним не считается нормативным заключением.")
        st.caption("Тип арматуры и влажность должны соответствовать фактическим данным.")
    with c3:
        coarse_pct=field.number_input("Объёмная доля крупного заполнителя, %",
            min_value=1.,max_value=100.,value=40.,step=5.)
        grain=field.number_input("Наибольшая крупность заполнителя, мм",
            min_value=5.,max_value=80.,value=30.,step=5.)
        cement=field.number_input("Расход цемента, кг/м³",
            min_value=100.,max_value=800.,value=500.,step=25.)
        wc=field.number_input("Водоцементное отношение В/Ц",
            min_value=.1,max_value=1.,value=.45,step=.05)
        relative_humidity=field.number_input("Относительная влажность среды, %",
            min_value=1.,max_value=100.,value=44.,step=1.)
        # User requested natural sand hidden and preset to Yes.
        # Keep the provenance of this unverified assumption in source JSON.
        natural_sand=True

    # The original well-sourced comments from R0.6.8.2 have NEVER been
    # deleted. Keep them readable separately from the single-line (?).
    with st.expander("Нормативные пояснения к диапазонам материалов",
                     expanded=False):
        st.caption("Сохранены исходные пояснения приложения Л СП 2.02.05-2026. "
                   "Это область применимости формул и таблиц, которая может "
                   "быть уже диапазона, допускаемого формой ввода.")
        for heading,source_key in (
            ("Объёмная доля крупного заполнителя",
             "coarse_aggregate_volume_pct"),
            ("Наибольшая крупность заполнителя",
             "max_aggregate_mm"),
            ("Расход цемента","cement_kg_m3"),
            ("Водоцементное отношение В/Ц","water_cement_ratio"),
            ("Относительная влажность RH","relative_humidity_pct"),
        ):
            st.markdown("**"+heading+"**")
            st.write(BELARUS_ANNEX_L_SOURCE_HELP[source_key])
        st.caption("Теплотехническое поле ниже рассчитывается по ТКП EN "
                   "1992-1-2, а не по ранее применявшемуся приложению К.")

    st.divider()
    st.subheader("3. Пожар и действующие усилия")
    x,y,z=st.columns(3)
    with x:
        n_txt=field.text_input("Nᶠⁱ, кН (сжатие положительно)",
            value="",placeholder="Введите действующую силу",
            help="Готовое расчётное пожарное усилие, не нормативная обычная нагрузка.")
    with y:
        mx_txt=field.text_input("Mxᶠⁱ, кН·м",value="",
            placeholder="Можно указать 0",
            help="Момент в рассматриваемом сечении.")
    with z:
        my_txt=field.text_input("Myᶠⁱ, кН·м",value="",
            placeholder="Можно указать 0",
            help="Момент в рассматриваемом сечении.")
    e1,e2=st.columns([1,2])
    with e1:
        required=field.selectbox("Требуемая огнестойкость",
            (30,45,60,90,120),index=3,
            format_func=lambda v:f"R{v} · {v} мин")
    with e2:
        st.caption("Обогреваемые поверхности:")
        sx,sy,sz,sw=st.columns(4)
        with sx:left=field.checkbox("Слева",value=True)
        with sy:right=field.checkbox("Справа",value=True)
        with sz:bottom=field.checkbox("Снизу",value=True)
        with sw:top=field.checkbox("Сверху",value=True)
    st.caption("Для подтверждения огнестойкости всей колонны также "
               "необходима согласованная схема усилий по её длине и закрепления. "
               "Введённые моменты относятся к одному расчётному сечению.")
    run=st.form_submit_button("Рассчитать огнестойкость",type="primary",
                               use_container_width=True)

if run:
    try:
        # Empty loads remain truly missing; zero must be typed explicitly.
        def needed(s,label):
            if not s.strip():
                raise ValueError(f"Введите {label}. Нулевое значение обозначьте 0.")
            return float(s.replace(",","."))
        faces=[f for f,enabled in (
            ("left",left),("right",right),("bottom",bottom),("top",top))
            if enabled]
        physical={
            "name":name,"b_mm":b_mm,"h_mm":h_mm,"length_m":length,
            "mu_x":mu_x,"mu_y":mu_y,
            "cover_mm":cover,"stirrup_mm":tie,"bar_diameter_mm":dia,
            "bars_horizontal":int(count_x),"bars_vertical":int(count_y),
            "bars":rows if manual else None,
            "concrete_class":strength,"aggregate_family":agg,
            "dry_density_kg_m3":density,"consistency":consistency,
            "curing":curing,"modulus_aggregate":ecm_basis,
            "measured_Ecm_GPa":measured_ecm,"steel_route":steel_route,
            "ductility_class":duct,
            "moisture_mass_pct":moisture,
            "coarse_aggregate_pct":coarse_pct,
            "max_aggregate_mm":grain,"cement_kg_m3":cement,
            "water_cement_ratio":wc,
            "relative_humidity_pct":relative_humidity,
            "natural_sand_confirmed":natural_sand,
            "natural_sand_provenance":"hidden_default_assumed_natural_unverified",
            "required_minutes":float(required),
            "exposed_faces":faces,
            "N_kN":needed(n_txt,"N"),"Mx_kNm":needed(mx_txt,"Mx"),
            "My_kNm":needed(my_txt,"My"),
        }
        column=make_column(physical)
        with st.spinner("Рассчитываются прогрев, температурные деформации и работа сечения во времени"):
            result=fire_assessment(
                column,required_minutes=float(required),
                steel_route=steel_route,ductility_class=duct,
                moisture_mass_pct=float(moisture),
                grid=12,dt_minutes=5.,assess_member=False)
        st.session_state[f"r07_last_public_result_{cid}"]={
            "column":column,"result":result}
    except (ValueError,TypeError,KeyError,
            PublicFireInputError) as exc:
        st.error("Не удалось выполнить расчёт: "+str(exc))
        st.session_state.pop(f"r07_last_public_result_{cid}",None)
    except Exception as exc:
        st.error("Расчёт остановлен. Нормативный результат не сформирован: "
                 +type(exc).__name__+": "+str(exc))
        st.session_state.pop(f"r07_last_public_result_{cid}",None)

record=st.session_state.get(f"r07_last_public_result_{cid}")
if record:
    c=record["column"];r=record["result"]
    st.divider()
    st.subheader("Результаты расчёта")
    a,b,d=st.columns(3)
    with a:st.metric("Требуемый предел",f"R{r['required_rating_minutes']:g}")
    with b:st.metric("Расчётное время утраты несущей способности",
                     "Не установлено")
    with d:st.metric("Соответствие требованиям","Не установлено")
    st.warning("Температурный и механический расчёты сечения выполнены, "
               "но ещё нет верифицированного критерия потери несущей "
               "способности всей колонны. Поэтому фактическое R(t) "
               "и соответствие Rrequired не определены. "
               "Это НЕ означает, что колонна не соответствует требованиям.")
    show_after_required=st.checkbox(
        "Показывать дополнительно период после Rrequired (до 2× Rrequired)",
        value=False,key=f"r074_extended_results_{cid}",
        help="По умолчанию графики ограничены требуемой продолжительностью "
             "пожара. Продлённый расчёт выполняется для исследования "
             "нагрева; он не означает, что конструкция сохраняет несущую "
             "способность после Rrequired.")
    max_chart_time=float("inf") if show_after_required else float(
        r["required_rating_minutes"])
    if show_after_required:
        st.caption("Показан также прогрев после требуемого R. "
                   "Этот период является исследовательским и сам по себе "
                   "не доказывает несущую способность после Rrequired.")
    chart_report={
        **r,
        "timeline":[x for x in (r.get("timeline") or [])
                    if float(x["minute"])<=max_chart_time+1.e-9],
        "thermal_timeline":[x for x in (r.get("thermal_timeline") or [])
                            if float(x["minute"])<=max_chart_time+1.e-9],
    }
    col1,col2=st.columns([1.2,1])
    with col1:
        timeline=pd.DataFrame(chart_report.get("timeline") or [])
        plot,missing_bars,audit_rows=prepare_temperature_chart(
            chart_report,[bar["id"] for bar in c.get("bars",[])])
        concrete_plot,steel_plot=split_temperature_chart(plot)
        st.markdown("**Газовая среда и температура бетона**")
        if not concrete_plot.empty:
            st.line_chart(concrete_plot,
                          x_label="Продолжительность пожара, мин",
                          y_label="Температура, °C")
        else:
            st.warning("В сохранённом результате нет временных температур. "
                       "Выполните расчёт ещё раз.")
        st.markdown("**Температура продольной арматуры**")
        if not steel_plot.empty:
            st.line_chart(steel_plot,
                          x_label="Продолжительность пожара, мин",
                          y_label="Температура арматуры, °C")
            st.caption("Стержни с одинаковой историей температур объединены "
                       "в одну кривую. Каждый стержень S1…Sn сохраняется "
                       "в таблице температур и выгруженном JSON.")
        if r.get("thermal_timeline_independent_of_mechanics"):
            st.caption("Температуры рассчитаны через 5 минут, включая "
                       "начальное состояние t=0 при 20 °C. "
                       "Механическое равновесие проверяется отдельно "
                       "в выбранные моменты времени.")
        if audit_rows:
            st.caption("Температуры арматуры восстановлены из сохранённого "
                       "расчётного аудита в те же моменты времени, без интерполяции.")
        if missing_bars:
            st.info("Для следующих стержней в сохранённом результате нет "
                    "достоверной истории температур: "+", ".join(missing_bars)
                    +". Повторно нажмите «Рассчитать огнестойкость», "
                    "чтобы обновить результат. Отсутствующие значения "
                    "не заменены нулями.")
        transition=r["observed_strain_limit_transition"]
        if transition:
            st.info("Обнаружен численный интервал достижения предельной "
                    "деформации сечения: "
                    +"; ".join(
                        f"{i['sampled_within_time_minutes']:g}–"
                        f"{i['sampled_strain_exceeded_time_minutes']:g} мин"
                        for i in transition)
                    +". Это не эквивалент разрушения всей колонны.")
        st.markdown("**Механический ответ при заданных N–Mx–My**")
        forces=r.get("fire_design_actions") or []
        if forces:
            force=forces[0]
            st.write("Расчётные усилия при пожаре: "
                     f"N = {force.get('N_kN',0):g} кН; "
                     f"Mx = {force.get('Mx_kNm',0):g} кН·м; "
                     f"My = {force.get('My_kNm',0):g} кН·м.")
        strain_ratio=r.get("design_action_strain_demand_pct_at_required_time")
        if strain_ratio is not None:
            st.metric("Отношение расчётной деформации к предельной "
                      "при Rrequired",f"{strain_ratio:.2f}%")
        strain_plot=prepare_optional_percent_chart(chart_report,{
            "design_action_strain_demand_pct":
                "Максимальная деформация / предельная, %"})
        if not strain_plot.empty:
            strain_plot["Предел деформации, 100%"]=100.
            st.line_chart(strain_plot,
                x_label="Продолжительность пожара, мин",
                y_label="Деформационный критерий, %")
        if strain_plot.empty:
            st.info("Деформационный график отсутствует: для введённой "
                    "комбинации усилий не найдено достоверное состояние "
                    "нелинейного равновесия. Это НЕ означает, что нагрузка "
                    "допустима. Ниже приведена независимая проверка "
                    "возможной несущей способности сечения без Ньютона.")
        st.caption("Эти деформации получены из равновесия N–Mx–My "
                   "при фактических введённых нагрузках. "
                   "Это нагрузкозависимый показатель расчётной модели "
                   "сечения, но НЕ процент использования несущей "
                   "способности всей колонны и НЕ нормативный R(t). "
                   "Отсутствующее состояние не приравнивается к нулю.")
        st.markdown("**Численное состояние сечения на Rrequired**")
        status_text={
            WITHIN:"Равновесие сечения найдено; в проверенной точке "
                   "предельные деформации не превышены",
            EXCEEDED:"Расчёт сечения показывает превышение предельной "
                     "деформации (не определяет момент обрушения)",
            UNKNOWN:"Состояние сечения не удалось достоверно определить"}
        st.write(status_text.get(r["numerical_section_at_required_time"],
                                  "Численное состояние не определено"))
    with col2:
        st.plotly_chart(make_section_figure(c),
            use_container_width=True,key="r07_section_diagram")
        st.markdown("**Температуры при требуемой продолжительности**")
        temps=r["required_time_temperatures"]
        st.write(f"Бетон, поверхность: "
                 f"{temps['concrete_surface_max_C']:.1f} °C")
        st.write(f"Бетон, центр: {temps['concrete_centre_C']:.1f} °C")
        st.dataframe(pd.DataFrame([
            {"Стержень":key,"Температура, °C":round(float(t),1)}
            for key,t in (temps["bars_C"] or {}).items()]),
            hide_index=True,use_container_width=True)
    st.divider()
    st.subheader("Температурное поле сечения")
    grid_spec=r.get("thermal_grid")
    available_frames=[
        entry for entry in (chart_report.get("thermal_timeline") or [])
        if isinstance(entry,dict) and
           isinstance(entry.get("grid_temperature_C"),list)
    ]
    if isinstance(grid_spec,dict) and available_frames:
        time_to_frame={float(x["minute"]):x for x in available_frames}
        options=sorted(time_to_frame)
        selected_default=min(options,key=lambda t:abs(
            t-float(r["required_rating_minutes"])))
        heat_slider_key=f"r074_heat_section_time_{cid}"
        if (heat_slider_key in st.session_state and
            st.session_state[heat_slider_key] not in options):
            st.session_state.pop(heat_slider_key,None)
        selected_time=st.select_slider(
            "Время нагрева сечения, мин",
            options=options,value=selected_default,
            format_func=lambda t:f"{t:g} мин",
            key=heat_slider_key,
            help="Реальные сохранённые моменты решения ТКП 2D. "
                 "Температуры между моментами не интерполируются.")
        frame=time_to_frame[selected_time]
        cmax=max(25.,*(float(x["gas_C"]) for x in available_frames))
        show_500=st.checkbox(
            "Показать изотерму 500 °C",
            value=True,key=f"r074_isotherm_{cid}",
            help="Только графическая изотерма. Она не рассчитывает "
                 "остаточную несущую способность по приложению К.")
        heat_left,heat_right=st.columns([1.35,1])
        with heat_left:
            try:
                fig=make_tkp_section_heatmap(c,frame,grid_spec,
                    color_max_C=cmax,draw_isotherm_500=show_500)
            except (ValueError,TypeError,KeyError) as exc:
                st.warning("Не удалось визуализировать температурное поле "
                           "этого расчётного шага: "+str(exc))
            else:
                st.plotly_chart(fig,use_container_width=True,
                    key=f"r074_tkp_section_{cid}")
        with heat_right:
            st.metric("Температура газа",f"{frame['gas_C']:.1f} °C")
            st.metric("Максимальная температура бетона",
                f"{frame['concrete_surface_C']:.1f} °C")
            st.metric("Температура в центре",
                f"{frame['concrete_centre_C']:.1f} °C")
            bars_now=frame.get("bars_C") or {}
            st.dataframe(pd.DataFrame([
                {"Стержень":str(bar["id"]),
                 "x, мм":float(bar["x_mm"]),
                 "y, мм":float(bar["y_mm"]),
                 "T, °C":(round(float(bars_now[str(bar["id"])]),1)
                          if str(bar["id"]) in bars_now else None)}
                for bar in c.get("bars",[])
            ]),hide_index=True,use_container_width=True)
        st.caption("Восстановленная тепловая карта сечения из исходных "
                   "расчётных ячеек ТКП EN 1992-1-2 (2D FVM). "
                   "Сетка: "+str(grid_spec['nx'])+"×"+str(grid_spec['ny'])+
                   ". Бирюзовые окружности показывают реальные положения "
                   "стержней; их температуры получены из того же поля. "
                   "Изотерма 500 °C — только для визуализации, "
                   "не самостоятельный расчёт R(t).")
    else:
        st.info("В сохранённом расчёте нет двухмерного температурного поля. "
                "Нажмите «Рассчитать огнестойкость» ещё раз, "
                "чтобы восстановить тепловую карту по ТКП.")

    st.divider()
    st.subheader("Температурные свойства и механика по СП 2.02.05-2026")
    sp_mech=r.get("sp2026_stage1_at_required_time") or {}
    if sp_mech.get("status")=="SP_MATERIAL_AND_SECTION_NUMERICAL_DIAGNOSTIC":
        c1,c2=st.columns(2)
        with c1:
            st.metric("Бетонные волокна без прочности при T > 800 °C",
                int(sp_mech.get("concrete_zero_strength_over_800_C_count",0)))
        with c2:
            st.metric("Максимальная температура арматуры",
                f"{sp_mech['max_steel_temperature_C']:.1f} °C")
        st.caption("Принятое вами правило: при T > 800 °C прочность "
                   "и жёсткость бетона равны нулю. При T = 800 °C "
                   "сохраняются значения таблицы 9. Это отдельное "
                   "инженерное допущение, не продолжение таблицы СП.")
        with st.expander("Равновесие сечений по СП 5.03.01-2020",
                         expanded=False):
            for item in sp_mech.get("sections",[]):
                eq=item.get("equilibrium") or {}
                st.write(f"{item.get('id')}: N={item.get('N_kN')} кН, "
                         f"Mx={item.get('Mx_kNm')} кН·м, "
                         f"My={item.get('My_kNm')} кН·м — "
                         f"{eq.get('model_status','не определено')}")
                if eq.get("classification") not in (
                    "sampled_equilibrium_within_strain_limits",
                    "sampled_equilibrium_strain_limits_exceeded"):
                    st.caption("Нелинейное равновесие не установлено; "
                               "это не является доказательством разрушения.")
    else:
        st.info("Расчётная механика СП на выбранное время не выполнена: "+
                str(sp_mech.get("reason","нет проверенного поля температуры")))
    st.caption("Этот блок использует материал СП 2.02.05-2026, "
               "но существующий температурный решатель пока использует "
               "теплофизические свойства ТКП. Это переходный этап SP-R.1, "
               "а не подтверждённая расчётная ветвь СП. "
               "Для U(t) всей колонны и t_R остаются необходимыми "
               "сопряжённая механика второго порядка, проверка сходимости "
               "и первый физически обоснованный предел несущей способности.")
    st.divider()
    st.subheader("Изменение прочности и проверенный запас сечения")
    st.warning("Следующие исторические графики построены по ТКП EN 1992-1-2, "
               "а НЕ по СП 2.02.05-2026. Это отдельное сопоставление, "
               "не использовать для нормативного определения R(t) по СП. "
               "Основной новый материал СП приведён выше.")
    st.caption("Материальные показатели по ТКП EN 1992-1-2:2009 относятся "
               "только к потере прочности бетона и стали при нагреве. "
               "Они НЕ являются несущей способностью всей колонны.")
    strengths=r.get("material_strength_at_required_time") or {}
    a,b=st.columns(2)
    with a:
        if strengths.get("concrete_uniaxial_strength_retained_pct") is not None:
            st.metric("Сохранение прочности бетона при Rrequired",
                f"{strengths['concrete_uniaxial_strength_retained_pct']:.1f}%")
    with b:
        if strengths.get("steel_yield_strength_retained_pct") is not None:
            st.metric("Сохранение предела текучести арматуры при Rrequired",
                f"{strengths['steel_yield_strength_retained_pct']:.1f}%")
    strength_columns={
        "concrete_retained_uniaxial_pct":"Бетон: сохранение fck, %",
        "steel_retained_yield_pct":"Арматура: сохранение fyk, %"}
    strength_history=prepare_optional_percent_chart(chart_report,strength_columns)
    if not strength_history.empty and strength_history.notna().any().any():
        st.line_chart(strength_history,
            x_label="Продолжительность пожара, мин",
            y_label="Сохранение прочности материала, %")
    st.caption("Средневзвешенные по площадям коэффициенты прочности отдельных "
               "материалов: бетон kc(θ), арматура ksy(θ). "
               "Они не включают изгибно-сжатую работу колонны или устойчивость.")
    st.subheader("Нижняя граница использования сечения U(t)")
    bounds=r.get("section_interaction_utilisation_bound_at_required_time") or {}
    lower=bounds.get("section_utilization_lower_bound_pct")
    overload=bool(bounds.get("definite_section_overload_in_source_model"))
    if lower is not None:
        st.metric("Использование сечения не менее (при Rrequired)",
                  f"≥ {lower:.1f}%")
        if overload:
            st.error(
                "Указанная комбинация N–Mx–My превышает даже оптимистическую "
                "верхнюю границу сопротивления сечения, рассчитанную по "
                "температурным характеристикам бетона и арматуры. "
                "Это подтверждённая перегрузка СЕЧЕНИЯ в используемой модели "
                "материалов, а не просто несходимость решателя.")
        else:
            st.caption(
                "Число является доказанной НИЖНЕЙ границей использования "
                "сечения: фактическое использование не меньше указанного. "
                "Точное U(t) определить из неё нельзя.")
    else:
        st.info("Граница возможной несущей способности сечения не определена "
                "из доступных температурных данных.")
    use_history=prepare_optional_percent_chart(
        chart_report,{"section_minimum_possible_utilisation_pct":
                      "Использование сечения не менее, %"})
    if not use_history.empty and use_history.notna().any().any():
        use_history["Предел использования 100%"]=100.
        st.line_chart(use_history,
            x_label="Продолжительность пожара, мин",
            y_label="Нижняя граница использования, %")
    st.caption(
        "Это вычисленная по ТКП N–Mx–My граница: линейное программирование "
        "ищет максимальную нагрузку даже при независимом выборе напряжений "
        "каждого бетонного волокна и арматурного стержня в пределах их "
        "температурной прочности. Отброшено только условие совместности "
        "деформаций, поэтому реальная несущая способность НЕ может быть "
        "выше вычисленного верхнего предела; U не может быть ниже кривой. "
        "Превышение кривой над 100% доказывает несущую недостаточность "
        "сечения в исходной модели. Ниже 100% соответствие НЕ доказано; "
        "ещё необходимо учесть совместность деформаций, эффекты второго "
        "порядка и устойчивость всей колонны.")
    st.caption(
        "Ранее отображавшийся постоянный график 50% удалён: "
        "он отражал лишь ограничение тестовых множителей λ≤2, "
        "а не действительное использование. Нормативный R(t) "
        "всей колонны ещё не квалифицирован.")

    if not r.get("steel_material_confirmed"):
        st.caption("Материал S500: технология изготовления и класс пластичности "
                   "использованы как исходные допущения, без проверки сертификата.")
    st.markdown("**Риск хрупкого разрушения бетона · приложение Л СП 2.02.05-2026**")
    if r.get("natural_sand_assumed"):
        st.caption("Для приложения Л по умолчанию принят природный песок. "
                   "Тип песка не подтверждён и является расчётным допущением.")
    sp=r.get("spalling_annex_L") or {}
    if sp.get("status")=="calculated_method_scope":
        st.write(f"Показатель F = {sp['F']:.3f}; "
                 +("требуются защитные мероприятия по Л.6" if
                    sp.get('protection_required') else
                    "F ≤ 4 при принятых параметрах"))
        if not sp.get("moisture_method_qualified"):
            st.caption("Вычисление влажности по Л.5 имеет нерешённую "
                       "оговорку о единицах; результат условный.")
    else:
        st.write("Оценка F не завершена: "
                 +str(sp.get("reason","недостаточно подтверждённых параметров.")))
    st.markdown("**Что препятствует окончательному выводу**")
    st.write(
        "Нужно подтвердить пространственную расчётную схему колонны, "
        "достоверность тепловой и механической модели, контроль "
        "хрупкого разрушения и критерий физической потери несущей "
        "способности. История температуры и равновесие одного сечения "
        "не заменяют эти проверки.")
    st.download_button("Скачать результат расчёта (JSON)",
        json.dumps(r,ensure_ascii=False,indent=2,default=str),
        file_name=f"{c['name']}_fire_resistance.json",
        mime="application/json")
else:
    st.info("После ввода данных нажмите «Рассчитать огнестойкость». "
            "Неизвестные нагрузки не заменяются нулём.")
