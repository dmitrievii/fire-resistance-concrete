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

st.set_page_config(
    page_title="Огнестойкость железобетонной колонны",
    page_icon="🏗️",layout="wide",initial_sidebar_state="collapsed")

st.title("Расчёт огнестойкости железобетонной колонны")
st.caption(
    "Беларусь · СП 2.02.05-2026 · СП 5.03.01-2020 · "
    "ТКП EN 1992-1-2-2009 с национальным приложением")
st.write(
    "Введите геометрию и материалы колонны, затем пожарные усилия и "
    "требуемую продолжительность. Все расчёты выполняются по фактически "
    "указанным значениям. Никакие комбинации усилий не создаются повторно.")

with st.form("column_fire_design_v07",clear_on_submit=False):
    st.subheader("1. Геометрия и армирование")
    a,b,c=st.columns(3)
    with a:
        name=st.text_input("Обозначение колонны",value="К1")
        b_mm=st.number_input("Ширина b, мм",min_value=250.,max_value=2000.,
            value=600.,step=25.)
        h_mm=st.number_input("Высота сечения h, мм",min_value=250.,max_value=2000.,
            value=600.,step=25.)
    with b:
        length=st.number_input("Длина колонны L, м",min_value=1.,max_value=40.,
            value=3.,step=.25)
        mu_x=st.number_input("Расчётная длина: μx",min_value=.2,max_value=2.5,
            value=1.,step=.1,
            help="Подтвердите по реальной схеме закрепления; не определяет автоматически поведение рамы.")
        mu_y=st.number_input("Расчётная длина: μy",min_value=.2,max_value=2.5,
            value=1.,step=.1)
    with c:
        cover=st.number_input("Защитный слой до хомута, мм",min_value=5.,
            max_value=150.,value=20.,step=5.)
        tie=st.number_input("Диаметр хомута, мм",min_value=6.,max_value=40.,
            value=10.,step=2.)
        dia=st.number_input("Диаметр продольных стержней, мм",min_value=6.,
            max_value=50.,value=20.,step=2.)
    n1,n2=st.columns(2)
    with n1:
        count_x=st.number_input("Стержней по верхней/нижней грани",
            min_value=2,max_value=20,value=3,step=1)
    with n2:
        count_y=st.number_input("Стержней по левой/правой грани",
            min_value=2,max_value=20,value=3,step=1)
    manual=st.checkbox(
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
                key="r07_custom_bar_positions")
            rows=data.to_dict("records")
        except (TypeError,ValueError) as exc:
            st.error("Геометрия арматуры: "+str(exc))

    st.divider()
    st.subheader("2. Материалы")
    c1,c2,c3=st.columns(3)
    with c1:
        strength=st.selectbox("Класс бетона",(
            "C20/25","C25/30","C30/37","C35/45","C40/50"),index=2)
        agg=st.selectbox("Тип крупного заполнителя",(
            "siliceous","calcareous"),
            format_func=lambda v:"Силикатный" if v=="siliceous" else "Карбонатный")
        density=st.number_input("Сухая плотность, кг/м³",min_value=800.,
            max_value=3000.,value=2200.,step=50.)
        consistency=st.selectbox("Консистенция бетонной смеси",(
            "V3_V4","V1_V2","S1_S2","S3_S5"),index=0,
            help="Для определения Ecm по таблице 6.3 СП 5.03.01-2020.")
        curing=st.selectbox("Твердение",("natural","heat"),
            format_func=lambda x:"Естественное" if x=="natural"
                                      else "Тепловая обработка")
        ecm_basis=st.selectbox("Основание для модуля Ecm",(
            "gravel_granite_upto40","measured"),
            format_func=lambda x:"СП 5.03.01, табл. 6.3 (гравий/гранит до 40 мм)"
                                 if x=="gravel_granite_upto40" else
                                 "Результат испытания бетона")
        measured_ecm=(st.number_input("Измеренный Ecm, ГПа",
            min_value=5.,max_value=90.,value=35.,step=1.)
            if ecm_basis=="measured" else None)
        if agg=="calcareous" and ecm_basis=="gravel_granite_upto40":
            st.caption("Для карбонатного заполнителя потребуется указать "
                       "доказанный модуль Ecm по испытанию.")
    with c2:
        st.text_input("Класс арматуры",value="S500",disabled=True,
            help="В этой версии нормативная библиотека допускает S500.")
        steel_route=st.selectbox("Изготовление арматуры",
            ("Не установлено","hot_rolled","cold_worked"),
            format_func=lambda x:{"Не установлено":"Выберите по паспорту",
                "hot_rolled":"Горячекатаная","cold_worked":"Холоднодеформированная"}[x],
            help="Разные температурные диаграммы по ТКП EN 1992-1-2.")
        duct=st.selectbox("Класс пластичности",
            ("Не установлен","A","B","C"))
        moisture=st.number_input("Массовая влажность бетона, %",min_value=0.,
            max_value=3.,value=1.5,step=.1,
            help="1,5% — исходное значение для демонстрационного сценария, "
                 "НЕ измеренное значение для вашей колонны.")
        st.caption("Тип арматуры и влажность должны соответствовать фактическим данным.")
    with c3:
        coarse_pct=st.number_input("Объёмная доля крупного заполнителя, %",
            min_value=1.,max_value=100.,value=40.,step=5.)
        grain=st.number_input("Наибольшая крупность заполнителя, мм",
            min_value=5.,max_value=80.,value=30.,step=5.)
        cement=st.number_input("Расход цемента, кг/м³",
            min_value=100.,max_value=800.,value=500.,step=25.)
        wc=st.number_input("Водоцементное отношение В/Ц",
            min_value=.1,max_value=1.,value=.45,step=.05)
        relative_humidity=st.number_input("Относительная влажность среды, %",
            min_value=1.,max_value=100.,value=44.,step=1.)
        natural_sand=st.checkbox(
            "Природный песок подтверждён",value=False,
            help="Влияет на оценку хрупкого разрушения по приложению Л.")

    st.divider()
    st.subheader("3. Пожар и действующие усилия")
    x,y,z=st.columns(3)
    with x:
        n_txt=st.text_input("Nᶠⁱ, кН (сжатие положительно)",
            value="",placeholder="Введите действующую силу",
            help="Готовое расчётное пожарное усилие, не нормативная обычная нагрузка.")
    with y:
        mx_txt=st.text_input("Mxᶠⁱ, кН·м",value="",
            placeholder="Можно указать 0",
            help="Момент в рассматриваемом сечении.")
    with z:
        my_txt=st.text_input("Myᶠⁱ, кН·м",value="",
            placeholder="Можно указать 0",
            help="Момент в рассматриваемом сечении.")
    e1,e2=st.columns([1,2])
    with e1:
        required=st.selectbox("Требуемая огнестойкость",
            (30,45,60,90,120),index=3,
            format_func=lambda v:f"R{v} · {v} мин")
    with e2:
        st.caption("Обогреваемые поверхности:")
        sx,sy,sz,sw=st.columns(4)
        with sx:left=st.checkbox("Слева",value=True)
        with sy:right=st.checkbox("Справа",value=True)
        with sz:bottom=st.checkbox("Снизу",value=True)
        with sw:top=st.checkbox("Сверху",value=True)
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
            "ductility_class":duct,"moisture_mass_pct":moisture,
            "coarse_aggregate_pct":coarse_pct,
            "max_aggregate_mm":grain,"cement_kg_m3":cement,
            "water_cement_ratio":wc,
            "relative_humidity_pct":relative_humidity,
            "natural_sand_confirmed":natural_sand,
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
        st.session_state["r07_last_public_result"]={
            "column":column,"result":result}
    except (ValueError,TypeError,KeyError,
            PublicFireInputError) as exc:
        st.error("Не удалось выполнить расчёт: "+str(exc))
        st.session_state.pop("r07_last_public_result",None)
    except Exception as exc:
        st.error("Расчёт остановлен. Нормативный результат не сформирован: "
                 +type(exc).__name__+": "+str(exc))
        st.session_state.pop("r07_last_public_result",None)

record=st.session_state.get("r07_last_public_result")
if record:
    c=record["column"];r=record["result"]
    st.divider()
    st.subheader("Результаты расчёта")
    a,b,d=st.columns(3)
    with a:st.metric("Требуемый предел",f"R{r['required_rating_minutes']:g}")
    with b:st.metric("Расчётное время утраты несущей способности",
                     "Не установлено")
    with d:st.metric("Соответствие требованиям","Не подтверждено")
    st.warning("Температурный и механический расчёты сечения выполнены, "
               "но ещё нет верифицированного критерия потери несущей "
               "способности всей колонны. Поэтому фактическое R(t) "
               "и соответствие Rrequired не определены. "
               "Это НЕ означает, что колонна не соответствует требованиям.")
    col1,col2=st.columns([1.2,1])
    with col1:
        st.markdown("**Поведение конструкции во времени**")
        timeline=pd.DataFrame(r["timeline"])
        if not timeline.empty:
            plot=timeline.set_index("minute")[[
                "gas_C","concrete_surface_C","concrete_centre_C"]]
            st.line_chart(plot)
            st.caption("Газовая температура, максимальная температура "
                       "поверхности и температура центра бетона, °C.")
        transition=r["observed_strain_limit_transition"]
        if transition:
            st.info("Обнаружен численный интервал достижения предельной "
                    "деформации сечения: "
                    +"; ".join(
                        f"{i['sampled_within_time_minutes']:g}–"
                        f"{i['sampled_strain_exceeded_time_minutes']:g} мин"
                        for i in transition)
                    +". Это не эквивалент разрушения всей колонны.")
        st.markdown("**Численное состояние сечения на Rrequired**")
        st.write(r["numerical_section_at_required_time"])
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
