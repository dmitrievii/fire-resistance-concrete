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
from rc_fire.integration.r07_inputs import (
    make_column,perimeter_bars,explicit_pinned_uniform_sp2026_member)
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
    with st.expander("SP-R.3 · Полная колонна: подтверждённая расчётная схема",
                     expanded=False):
        st.caption("Дополнительный численный расчёт P–Δ по СП: только схема "
                   "шарнир–шарнир по двум осям, постоянная N, "
                   "равномерная поперечная нагрузка. Указанные Mx/My должны "
                   "быть моментами ПЕРВОГО порядка в середине пролёта, "
                   "созданными исключительно q=8M/L². Другие схемы требуют "
                   "отдельного задания всех узлов и нагрузок. "
                   "Это пока не подтверждённый нормативный R(t).")
        sp3_action_confirm=field.checkbox(
            "Подтверждаю: оба конца шарнирные, Mx/My от равномерных q",
            value=False,help="Никаких неучтённых концевых моментов, "
            "поперечных сил в узлах, рамных связей либо эксцентриситетов N.")
        sp3_heat_confirm=field.checkbox(
            "Подтверждаю равномерный прогрев колонны по всей длине",
            value=False,help="SP-R.2 2D поле распространяется на все "
            "узловые и гауссовы сечения только по вашему подтверждению.")
        sp3_cx,sp3_cy=st.columns(2)
        with sp3_cx:
            sp3_ex=field.number_input("Начальное отклонение по x, мм",
                min_value=0.,max_value=200.,value=0.,step=1.,
                help="Амплитуда полусинусоидального начального несовершенства; "
                "ноль допустим только как явно выбранный численный сценарий.")
        with sp3_cy:
            sp3_ey=field.number_input("Начальное отклонение по y, мм",
                min_value=0.,max_value=200.,value=0.,step=1.,
                help="Вторая независимая ось. Значение должно "
                "соответствовать проекту и применимой нормативной модели.")
        sp6_nominal=field.checkbox(
            "SP-R.6: расчёт сопротивления по СП 5 — §6.1.5.4 + §8.1.6",
            value=False,
            help="Отдельная расчетная ветвь без полной нелинейной "
                 "диаграммы SP-R5. Проверка N-Mx-My с нормативными "
                 "расчётными сопротивлениями и номинальной жесткостью. "
                 "Неравномерный прогрев учитывается численно, "
                 "но нормативная эквивалентность требует проверки.")
        sp7_coupled=False
        sp7_creep_by_moments=False
        sp7_creep_values={}
        sp7_history=False
        sp7_heat=False
        sp7_experiment=False
        sp6_phi=0.
        sp6_history=False
        sp6_grid=False
        sp6_capacity=False
        if sp6_nominal:
            sp6_phi=field.number_input(
                "Эффективный коэффициент ползучести φef, СП 5 §8.1.6.5",
                min_value=0.,max_value=100.,value=0.,step=.1,
                help="СП5 Eq8.64: φef=φ(∞,t0)·M0Eqp/M0Ed. "
                     "Ноль — явно выбранный кратковременный сценарий, "
                     "не автоматически нормативное значение.")
            sp6_history=field.checkbox(
                "SP-R.6: повторить проверку по времени пожара",
                value=False,
                help="Для сохранённых моментов времени 1/3, 2/3 "
                     "и требуемой продолжительности. "
                     "Не интерполирует температурные поля.")
            sp6_capacity=field.checkbox(
                "SP-R.6: найти коэффициент предельной нагрузки",
                value=False,
                help="В каждом расчёте по СП5 заново вычисляются "
                     "n, kc,ном, Ncrit и η, затем проверяются деформации "
                     "сечения. Выдаётся только условный интервал "
                     "сопротивления данной модели, не нормативное U(t).")
            sp7_coupled=field.checkbox(
                "SP-R.7: связанная матрица жесткости N–Mx–My при прогреве",
                value=False,
                help="Полная 3x3 матрица по §8.1.2, конденсация и "
                     "расчет главных форм устойчивости. Сопряжение с "
                     "номинальной жёсткостью §8.1.6 для неравномерного "
                     "нагрева — явно обозначенное численное расширение, "
                     "не нормативное R(t).")
            if sp7_coupled:
                sp7_creep_by_moments=field.checkbox(
                    "SP-R.7: вычислить φef,x и φef,y по формуле (8.64)",
                    value=False,
                    help="Требуются φ(∞,t0) и реальные моменты "
                         "первого порядка от практически постоянного "
                         "и расчётного сочетаний по обеим осям. "
                         "Это не моделирование высокотемпературной "
                         "переходной ползучести бетона.")
                if sp7_creep_by_moments:
                    st.caption("Все моменты — в одном расчётном сечении "
                               "и одной системе знаков. Не вводите "
                               "неизвестные величины как нулевые.")
                    sp7_phi_inf=field.number_input(
                        "φ(∞,t₀), СП 5 §6.1.4.3",
                        min_value=0.,max_value=100.,value=0.,step=.1)
                    sp7_mqp_x=field.number_input(
                        "M₀Eqp,x, кН·м",value=0.,step=1.)
                    sp7_med_x=field.number_input(
                        "M₀Ed,x, кН·м",value=0.,step=1.)
                    sp7_mqp_y=field.number_input(
                        "M₀Eqp,y, кН·м",value=0.,step=1.)
                    sp7_med_y=field.number_input(
                        "M₀Ed,y, кН·м",value=0.,step=1.)
                    sp7_msource=field.text_input(
                        "Источник моментов первого порядка",
                        value="",placeholder="Номер схемы / ведомости нагрузок")
                    sp7_creep_values={
                        "phi_infty":float(sp7_phi_inf),
                        "first_order_M0Eqp_x_kNm":float(sp7_mqp_x),
                        "first_order_M0Ed_x_kNm":float(sp7_med_x),
                        "first_order_M0Eqp_y_kNm":float(sp7_mqp_y),
                        "first_order_M0Ed_y_kNm":float(sp7_med_y),
                        "first_order_moment_source":sp7_msource}
                sp7_history=field.checkbox(
                    "SP-R.7: исследовать первый наблюдаемый предел модели по времени",
                    value=False,
                    help="Проверяет каждый сохранённый момент пожара. "
                         "Неточно датированный переход или неизвестное состояние "
                         "не объявляется физическим разрушением.")
                sp7_heat=field.checkbox(
                    "SP-R.7: аудит сходимости прогрева по сетке и шагу времени",
                    value=False,
                    help="Отдельные три тепловых расчёта до 15 минут "
                         "при одинаковом сравнительном граничном условии. "
                         "Сходимость не подтверждает нормативную "
                         "корректность h, ε, влаги, откола.")
                sp7_experiment=field.checkbox(
                    "SP-R.7: проверить пригодность экспериментальных эталонов",
                    value=False,
                    help="Сопоставляет исходные характеристики с каталогом "
                         "I3/T3/II10 и показывает отсутствующие данные; "
                         "не подменяет экспериментальную валидацию.")
            sp6_grid=field.checkbox(
                "SP-R.6: проверить сходимость сетки волокон (8/12/16)",
                value=False,
                help="Исследуется только дискретизация механического "
                     "сечения при одном замороженном температурном поле. "
                     "Сходимость тепловой сетки и физическая проверка R "
                     "этим не подтверждаются.")
            st.caption("При неравномерном нагреве интегрирование "
                       "βE(T) по волокнам — расчётная "
                       "гипотеза, а не буквально предписанная "
                       "формула §8.1.6.3. Ввод φef должен "
                       "соответствовать сочетанию нагрузок.")
        sp5_full_law=field.checkbox(
            "SP-R.5: исследовать полную нелинейную диаграмму бетона по СП 5",
            value=False,
            help="Формулы 6.13–6.16 + температурные коэффициенты СП2026. "
                 "Предельные деформации и пик кривой при пожаре еще "
                 "не квалифицированы; высокие температуры могут блокироваться.")
        sp4_scan=field.checkbox(
            "SP-R.4: исследовать несущую способность по нагрузочному множителю",
            value=False,
            help="Дополнительные независимые расчёты полной колонны при масштабировании "
                 "N, qx, qy. Результат — численная огибающая и возможный интервал "
                 "деформационного предела модели, НЕ нормативная U(t) или R(t).")
        sp5_global_requested=field.checkbox(
            "SP-R.5: независимая проверка глобальной устойчивости",
            value=False,
            disabled=not sp4_scan,
            help="Только для полной нагрузочной модели SP-R4: проверяет "
                 "свободную глобальную матрицу K−N G в фактическом "
                 "сошедшемся состоянии. Не является сертификатом t_R.")
        sp4_history_requested=False
        if sp4_scan:
            sp4_history_requested=field.checkbox(
                "SP-R.4: вычислить нагрузочную огибающую также по времени",
                value=False,
                help="Повторить независимый нагрузочный анализ на трёх сохранённых "
                     "временах пожара (1/3, 2/3 и Rrequired, если они доступны). "
                     "Никаких промежуточных нерассчитанных температур.")
            st.caption("По умолчанию проверяются нагрузочные множители 0,25–2,0 "
                       "с шагом 0,25 и уточняется обнаруженный интервал. "
                       "Случаи неустойчивой или несошедшейся задачи "
                       "обозначаются как НЕОПРЕДЕЛЁННОСТЬ, не разрушение.")
        st.caption("При включении схемы используются μx=μy=1. "
                   "Проверка эксплуатационной/пожарной несущей способности "
                   "остается НЕ УСТАНОВЛЕНА до завершения квалификации материалов "
                   "и критерия первого отказа.")
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
        if sp6_nominal and not (sp3_action_confirm and sp3_heat_confirm):
            raise ValueError("SP-R.6 требует подтвержденной расчётной схемы и нагрева")
        if sp5_full_law and not (sp3_action_confirm and sp3_heat_confirm):
            raise ValueError("SP-R.5 полная диаграмма требует полной подтвержденной схемы")
        if sp4_scan and not (sp3_action_confirm and sp3_heat_confirm):
            raise ValueError("SP-R.4 требует подтверждения опор и равномерного прогрева")
        if sp3_action_confirm or sp3_heat_confirm:
            column["member_spec"]=explicit_pinned_uniform_sp2026_member(
                column,
                confirmed_pinned_uniform_action_model=sp3_action_confirm,
                confirmed_uniform_longitudinal_fire=sp3_heat_confirm,
                imperfection_x_mm=sp3_ex,imperfection_y_mm=sp3_ey)
            if sp6_nominal:
                column["member_spec"]["nominal_sp5_requested"]=True
                column["member_spec"]["nominal_sp5_phi_eff"]=float(sp6_phi)
                column["member_spec"]["nominal_sp5_creep_provenance"]=(
                    "User explicitly selected phi_eff in Streamlit; "
                    "SP5 Eq8.64 load-combination provenance not independently qualified")
                if sp6_history:
                    column["member_spec"]["nominal_sp5_history_requested"]=True
                if sp6_grid:
                    column["member_spec"]["nominal_sp5_grid_study_requested"]=True
                if sp6_capacity:
                    column["member_spec"]["nominal_sp5_load_scan_requested"]=True
                if sp7_coupled:
                    column["member_spec"]["coupled_sp5_requested"]=True
                    if sp7_creep_by_moments:
                        column["member_spec"]["coupled_sp5_creep_input"]=sp7_creep_values
                    if sp7_history:
                        column["member_spec"]["coupled_sp5_history_requested"]=True
                    if sp7_heat:
                        column["member_spec"]["coupled_sp5_thermal_audit_requested"]=True
                    if sp7_experiment:
                        column["member_spec"]["coupled_sp5_experiment_audit_requested"]=True
            if sp5_full_law:
                column["member_spec"]["constitutive_model"]=(
                    "SP5_6_1_5_2_FULL_HOT_EXPLORATORY")
            if sp5_global_requested:
                column["member_spec"]["global_stability_requested"]=True
            if sp4_scan:
                column["member_spec"]["resistance_scan_requested"]=True
                if sp4_history_requested:
                    column["member_spec"]["resistance_time_history_requested"]=True
                column["member_spec"]["resistance_scan_first_factor"]=.25
                column["member_spec"]["resistance_scan_step"]=.25
                column["member_spec"]["resistance_scan_max_factor"]=2.
        with st.spinner("Рассчитываются прогрев, температурные деформации и работа сечения во времени"):
            result=fire_assessment(
                column,required_minutes=float(required),
                steel_route=steel_route,ductility_class=duct,
                moisture_mass_pct=float(moisture),
                grid=16,dt_minutes=3.,assess_member=False)
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
    sp3_report=r.get("sp2026_stage3_member_at_required_time")
    sp3_status=r.get("sp2026_stage3_member_status")
    if sp3_status!="SP_R3_EXPLICIT_MEMBER_INPUT_REQUIRED":
        st.subheader("SP-R.3 · Двухосная модель всей колонны (численная)")
        if sp3_report:
            st.write("Состояние расчёта:",sp3_report.get("status"))
            fe=sp3_report.get("member") or {}
            st.write("Нелинейный FE-решатель:",fe.get("status"))
            index=sp3_report.get("member_model_strain_limit_index")
            if index is not None:
                st.metric("Индекс локальных предельных деформаций",
                    f"{index:.4f}")
            st.caption("Это максимум исследованных локальных деформационных "
                       "отношений, а НЕ использование несущей способности U(t). "
                       "Время t_R и нормативная проверка Rrequired не определены.")
            history3=r.get("sp2026_stage3_member_history") or {}
            if history3.get("samples"):
                st.dataframe(pd.DataFrame([{
                    "Время, мин":s["time_minutes"],
                    "Расчётное состояние":s["status"],
                    "Деформационный индекс":s["member_model_strain_limit_index"]}
                    for s in history3["samples"]]),
                    hide_index=True,use_container_width=True)
        else:
            st.warning("SP-R.3 не выполнен: "+str(
                r.get("sp2026_stage3_member_blocker") or sp3_status))
    sp4_data=r.get("sp2026_stage4_resistance_scan_at_required_time")
    sp4_status=r.get("sp2026_stage4_resistance_scan_status")
    if sp4_status not in (None,"SP_R4_NOT_REQUESTED"):
        st.subheader("SP-R.4 · Нагрузочная огибающая колонны (численная)")
        if sp4_data:
            st.write("Состояние поиска:",sp4_data["status"])
            st.caption("Проверяется весь подтверждённый вектор пожарных "
                       "воздействий (N, qx, qy, узловые силы) при одном "
                       "множителе λ. Начальная геометрия не масштабируется.")
            check=sp4_data.get("at_declared_design_actions") or {}
            st.write("При фактической пожарной нагрузке (λ=1):",
                     check.get("state"))
            bracket=sp4_data.get("observed_model_resistance_bracket")
            if bracket:
                a,b=st.columns(2)
                with a:st.metric("Последний численно допустимый λ",
                                 f'{bracket["last_admissible_sample_factor"]:.4f}')
                with b:st.metric("Первое превышение деформационного критерия λ",
                                 f'{bracket["first_observed_exceedance_factor"]:.4f}')
                util=bracket["model_only_utilisation_interval"]
                st.write("Интервал индекса использования *расчётной модели*:",
                         f'{util["lower"]:.4f}–{util["upper"]:.4f}')
                st.caption("Это отношение 1/λ в рамках исследованной модели "
                           "и траектории нагружения. НЕ нормативное U(t).")
            elif sp4_data["status"].startswith("UNRESOLVED"):
                st.warning("Несходимость или непроверенное состояние не "
                           "классифицированы как разрушение колонны.")
            history4=r.get("sp2026_stage4_resistance_time_history") or {}
            if history4.get("samples"):
                st.markdown("**Изменение сопротивления расчётной модели во времени**")
                st.dataframe(pd.DataFrame([{
                    "Время, мин":s["time_minutes"],
                    "Номинальная пожарная нагрузка":s["nominal_fire_action_state"],
                    "λ допустимый":s["model_load_factor_low"],
                    "λ превышение":s["model_load_factor_high"],
                    "U модель, нижняя":(
                        (s["model_only_utilisation_interval"] or {}).get("lower")),
                    "N верхний предел модели, кН":s.get("source_model_N_kN_upper_bound"),
                    "U модель, верхняя":(
                        (s["model_only_utilisation_interval"] or {}).get("upper"))}
                    for s in history4["samples"]]),
                    hide_index=True,use_container_width=True)
                st.caption("Значения U модель по времени — только условные "
                           "численные интервалы. Предел огнестойкости t_R "
                           "не определяется по этой таблице.")
            elif r.get("sp2026_stage4_resistance_time_history_status") not in (
                    None,"SP_R4_HISTORY_NOT_REQUESTED"):
                st.warning("SP-R.4 временная серия: "+str(
                    r.get("sp2026_stage4_resistance_time_history_blocker") or
                    r.get("sp2026_stage4_resistance_time_history_status")))
            bound=sp4_data.get("stress_relaxed_axial_strength_upper_bound") or {}
            if bound.get("source_model_N_kN_upper_bound") is not None:
                st.metric("Верхняя оценка N в дискретной SP-модели",
                          f'{bound["source_model_N_kN_upper_bound"]:.1f} кН')
                st.caption("Это сумма индивидуальных максимальных сопротивлений "
                           "бетона и арматуры без совместности деформаций. "
                           "Она завышает фактическое сопротивление модели "
                           "и НЕ является несущей способностью колонны или R(t).")
            eccentric=sp4_data["minimum_eccentricity_check"]
            st.caption("СП 5.03.01-2020, §8.1.1.5: минимальный "
                       "эксцентриситет — "
                       f'{eccentric["minimum_eccentricity_about_x_mm"]:g} мм (x), '
                       f'{eccentric["minimum_eccentricity_about_y_mm"]:g} мм (y). '
                       "Его учёт в исходных усилиях не подтверждён автоматически.")
            rows=sp4_data.get("evaluations") or []
            if rows:
                st.dataframe(pd.DataFrame([{
                    "Множитель λ":p["load_factor"],
                    "Механический результат":p["state"],
                    "Макс. деформационный индекс":p.get("critical_model_strain_ratio"),
                    "FE-состояние":p.get("member_status")}
                    for p in rows]),hide_index=True,use_container_width=True)
        else:
            st.warning("SP-R.4 не выполнен: "+str(
                r.get("sp2026_stage4_resistance_scan_blocker") or sp4_status))
        st.caption("Фактические U(t), t_R и соответствие Rrequired пока не "
                   "установлены — требуется верификация материала, температур "
                   "и критерия первого физического отказа.")
    qualification=r.get("sp2026_stage4q_mechanical_qualification")
    qual_status=r.get("sp2026_stage4q_mechanical_qualification_status")
    if qual_status not in (None,"SP_R4Q_MEMBER_MODEL_NOT_REQUESTED"):
        with st.expander(
            "SP-R.4Q · Независимая квалификация механического расчёта",
            expanded=True):
            if qualification:
                st.write("Статус:",qual_status)
                passed=qualification.get("numerical_pass_count",0)
                st.metric("Независимые численные проверки",f"{passed}/5")
                st.caption("Проверяются независимые решения Эйлера, прогиб "
                           "при P–Δ, якобиан нагретого сечения и двухосная "
                           "конденсированная жесткость. PASS означает "
                           "численную согласованность, НЕ соответствие СП "
                           "и НЕ экспериментальную валидацию.")
                gates=qualification.get("gate_results") or []
                if gates:
                    st.dataframe(pd.DataFrame([{
                        "Проверка":g["id"],"Статус":g["status"],
                        "Основание / проблема":g["detail"]}
                        for g in gates]),hide_index=True,use_container_width=True)
                if qualification.get("remaining_blockers"):
                    st.warning("Нормативное механическое предельное состояние "
                               "не квалифицировано. U(t), t_R и Rrequired "
                               "не установлены.")
            else:
                st.warning("Проверка SP-R.4Q не выполнена: "+str(
                    r.get("sp2026_stage4q_mechanical_qualification_blocker")
                    or qual_status))
    stage5=r.get("sp2026_stage5_constitutive_status")
    stage5_global=r.get("sp2026_stage5_global_stability_at_design_actions")
    if stage5 not in (None,"NOT_REQUESTED"):
        with st.expander("SP-R.5 · Физический закон и глобальный критерий",
                         expanded=True):
            st.write("Полная конститутивная модель:",stage5)
            if r.get("sp2026_stage5_constitutive_blocker"):
                st.error("Нормативная область не подтверждена: "+str(
                    r["sp2026_stage5_constitutive_blocker"]))
            if stage5_global:
                st.write("Глобальная устойчивость при введённых нагрузках:",
                         stage5_global.get("status"))
                st.write("Остаток равновесия:",
                         stage5_global.get("equilibrium_relative_residual"))
                st.write("Минимальное собственное значение глобальной матрицы:",
                         stage5_global.get("smallest_global_tangent_eigenvalue"))
            st.caption("Положительная глобальная жесткость означает только "
                       "локально устойчивую ветвь численной модели. "
                       "Не подтверждены реальные температурные εc1(T), "
                       "εcu1(T), ползучесть, история повреждения и первое "
                       "физическое разрушение. Нормативное t_R отсутствует.")
    sp6=r.get("sp2026_stage6_sp5_nominal_at_required_time")
    sp6_status=r.get("sp2026_stage6_sp5_nominal_status")
    if sp6_status not in (None,"SP_R6_NOMINAL_METHOD_NOT_REQUESTED"):
        with st.expander(
            "SP-R.6 · Расчётная ветвь СП 5, §6.1.5.4 и §8.1.6",
            expanded=True):
            st.write("Результат проверки:",sp6_status)
            if sp6:
                st.caption("Бетон fcd=αcc·ktc·fck/γc; арматура "
                           "fyd=fyk/γs; при пожаре kc(T), ks(T), β(T). "
                           "Особая расчётная ситуация: γc=1,2, γs=1,0.")
                para=sp6["design_material_parameters"]
                st.write("Расчётное сопротивление бетона при 20 °C:",
                         f'{para["fcd_20_MPa"]:.2f} МПа')
                nom=sp6["nominal_second_order"]
                st.caption("Область численной модели: "+str(nom["scope"]))
                c1,c2=st.columns(2)
                for region,axis in ((c1,"x"),(c2,"y")):
                    with region:
                        v=nom.get(axis) or {}
                        st.metric("Ncrit, ось "+axis,
                                  f'{v["Ncrit_kN"]:.1f} кН'
                                  if v.get("Ncrit_kN") is not None
                                  else "Не определено")
                        st.write("Увеличение ηa:",
                                 f'{v["eta_a"]:.4f}'
                                 if v.get("eta_a") is not None
                                 else "Вне области формулы")
                ma=sp6.get("first_order_moment_reconciliation") or {}
                if ma:
                    st.write("Моменты до / после увеличения:",
                             {k:round(v,3) for k,v in ma.items()})
                sec=sp6.get("section") or {}
                st.write("Равновесие N–Mx–My:",
                         sec.get("model_status","Не установлено"))
                st.write("Максимальное отношение деформаций:",
                         sec.get("critical_ratio"))
                st.caption("Момент от начального отклонения N·e "
                           "учтён один раз; минимум e0≥max(h/30,20 мм) "
                           "применён как нижний предел, не добавлением "
                           "к уже учтённому эксцентриситету.")
                load_study=r.get("sp2026_stage6_sp5_nominal_load_scan") or {}
                if load_study:
                    st.markdown("**Нагрузочная огибающая именно по методу СП5**")
                    st.write("Состояние поиска:",
                             load_study["status"])
                    band=load_study.get(
                        "observed_conditional_SP5_section_factor_bracket")
                    if band:
                        st.write("Численный интервал предельного множителя:",
                                 {
                                    "λ внутри модели":
                                        band["last_admissible_sample_factor"],
                                    "λ превышение":
                                        band["first_observed_exceedance_factor"]})
                        u=band["model_only_utilisation_interval"]
                        st.write("Условный модельный U по этой ветви:",
                                 (round(u["lower"],4),round(u["upper"],4)))
                    st.caption("Ncrit и коэффициент η пересчитываются "
                               "для КАЖДОЙ величины λ; неизменным "
                               "остаётся только температурное поле. "
                               "Найденная граница относится к модели "
                               "сечения и не является подтверждённым "
                               "моментом разрушения колонны.")
                elif r.get("sp2026_stage6_sp5_nominal_load_status") not in (
                        None,"SP_R6_NOMINAL_LOAD_SCAN_NOT_REQUESTED"):
                    st.warning("Поиск предельной нагрузки: "+str(
                        r.get("sp2026_stage6_sp5_nominal_load_blocker") or
                        r.get("sp2026_stage6_sp5_nominal_load_status")))
                mesh_report=r.get("sp2026_stage6_sp5_nominal_grid_study") or {}
                if mesh_report.get("grids"):
                    st.markdown("**Численная сходимость механического сечения**")
                    st.dataframe(pd.DataFrame([{
                        "Сетка":p["fibre_grid"],
                        "Ncrit,x, кН":p["Ncrit_x_kN"],
                        "Ncrit,y, кН":p["Ncrit_y_kN"],
                        "ηa,x":p["eta_x"],"ηa,y":p["eta_y"]}
                        for p in mesh_report["grids"]]),
                        hide_index=True,use_container_width=True)
                    st.write("Изменение Ncrit между сетками:",
                             mesh_report["pairwise_comparisons"])
                    st.caption("Тепловая сетка SP-R2 остаётся неизменной; "
                               "физическая и нормативная сходимость R "
                               "отсюда не следует.")
                elif r.get("sp2026_stage6_sp5_nominal_grid_status") not in (
                        None,"SP_R6_GRID_STUDY_NOT_REQUESTED"):
                    st.warning("Исследование сетки: "+str(
                        r.get("sp2026_stage6_sp5_nominal_grid_blocker") or
                        r.get("sp2026_stage6_sp5_nominal_grid_status")))
                series=r.get("sp2026_stage6_sp5_nominal_history") or {}
                if series.get("samples"):
                    st.dataframe(pd.DataFrame([{
                        "Время, мин":s["time_minutes"],
                        "Статус сечения":s["status"],
                        "Ncrit,x, кН":(s["x_nominal"] or {}).get("Ncrit_kN"),
                        "Ncrit,y, кН":(s["y_nominal"] or {}).get("Ncrit_kN"),
                        "ηa,x":(s["x_nominal"] or {}).get("eta_a"),
                        "ηa,y":(s["y_nominal"] or {}).get("eta_a")}
                        for s in series["samples"]]),
                        hide_index=True,use_container_width=True)
                    if series.get("observed_strain_check_transitions"):
                        st.warning(
                            "Наблюдаемые между отсчётами переходы "
                            "деформационного критерия модели: "+
                            str(series["observed_strain_check_transitions"])+
                            ". Это НЕ первое физическое разрушение t_R.")
            else:
                st.warning("Ветвь не выполнена: "+str(
                    r.get("sp2026_stage6_sp5_nominal_blocker") or sp6_status))
            st.caption("Для неравномерных T(x,y) номинальная жёсткость "
                       "сформирована численной интеграцией; "
                       "нормативная эквивалентность, тепловая квалификация "
                       "и первое t_R ещё не доказаны. "
                       "Нормативный R PASS не выдаётся.")
    sp7=r.get("sp2026_stage7_coupled_at_required_time")
    sp7_status=r.get("sp2026_stage7_coupled_status")
    if sp7_status not in (None,"SP_R7_COUPLED_MODEL_NOT_REQUESTED"):
        with st.expander("SP-R.7 · Связанная двухосная механика и проверка первого предела",
                         expanded=True):
            st.write("Результат:",sp7_status)
            if sp7:
                matrix=sp7.get("nominal_coupled_evidence") or {}
                st.caption("Матрица §8.1.2 использует секущие модули; "
                           "температурная βE и номинальная жесткость "
                           "§8.1.6 показаны отдельно. Их сопряжение "
                           "при неравномерном нагреве ещё требует "
                           "нормативного и экспериментального обоснования.")
                st.write("Нагретая связанная матрица жесткости (3×3):")
                st.dataframe(pd.DataFrame(matrix.get("full_3x3_K") or []),
                             hide_index=True,use_container_width=True)
                st.write("Конденсированная номинальная матрица D (2×2), кН·м²:")
                st.dataframe(pd.DataFrame(matrix.get("nominal_2x2_D_kNm2") or []),
                             hide_index=True,use_container_width=True)
                st.write("Главные критические силы Ncrit, кН:",
                         [round(float(v),2) for v in (
                             matrix.get("principal_Euler_Ncrit_kN") or [])])
                st.write("Внедиагональная связанность:",
                         matrix.get("cross_axis_coupling_present"))
                if sp7.get("second_order_coupled_M2_kNm") is not None:
                    st.write("Связанные M2x, M2y, кН·м:",
                             [round(float(x),3) for x in
                              sp7["second_order_coupled_M2_kNm"]])
                section=sp7.get("source_section_check") or {}
                st.write("Состояние деформационной проверки:",
                         section.get("classification","Не определено"))
                st.write("Отношение деформаций в критических волокнах:",
                         section.get("critical_ratio"))
                secant=sp7.get("source_secant_3x3_at_section_root")
                if secant:
                    st.write("Секущая матрица §8.1.2 в найденном состоянии:")
                    st.dataframe(pd.DataFrame(secant.get("full_3x3_K") or []),
                                 hide_index=True,use_container_width=True)
            else:
                st.warning("Расчёт связанности: "+str(
                    r.get("sp2026_stage7_coupled_blocker") or sp7_status))
            history=r.get("sp2026_stage7_first_model_limit_history") or {}
            if history.get("samples"):
                st.markdown("**Временная проверка модельного предела**")
                st.dataframe(pd.DataFrame([{
                    "Время, мин":x.get("time_minutes"),
                    "Состояние":x.get("status"),
                    "Ncrit,min, кН":(x.get("nominal_coupled_evidence") or {}).get(
                        "minimum_nominal_Euler_Ncrit_kN")}
                    for x in history["samples"]]),
                    hide_index=True,use_container_width=True)
                if history.get("observed_first_model_limit_interval"):
                    st.warning("Обнаружен только интервал модельного предела: "+
                        str(history["observed_first_model_limit_interval"])+
                        ". Фактическое t_R НЕ установлено.")
            thermal=r.get("sp2026_stage7_thermal_mesh_time_audit")
            if thermal:
                st.markdown("**Независимая проверка тепловой сетки и шага**")
                st.write(thermal["status"])
                st.write("Максимальное отличие по сетке, °C:",
                         thermal["mesh_comparison"]["max_difference_C"])
                st.write("Максимальное отличие по времени, °C:",
                         thermal["time_comparison"]["max_difference_C"])
                st.caption("Граничные параметры — сравнительное допущение; "
                           "нормативная квалификация по СП не доказана.")
            experiments=r.get("sp2026_stage7_experiment_admissibility")
            if experiments:
                st.markdown("**Экспериментальные эталоны**")
                st.write("Допущены к независимой валидации:",
                         experiments["source_matched_cases_ready"],
                         "из",experiments["source_case_count"])
                st.dataframe(pd.DataFrame([{
                    "Испытание":x["id"],
                    "Наблюдаемое разрушение, мин":
                        x["observed_failure_time_min"],
                    "Статус":x["validation_execution_status"],
                    "Блокеры":len(x["admissibility_blockers"])}
                    for x in experiments["cases"]]),
                    hide_index=True,use_container_width=True)
            creep=r.get("sp2026_stage7_sp5_864_creep_source_audit")
            if creep:
                st.markdown("**Ползучесть по СП 5 §8.1.6.5**")
                st.write("φef,x:",
                         creep["axes"]["x"]["phi_eff"],
                         "φef,y:",creep["axes"]["y"]["phi_eff"])
                st.caption("Расчёт по формуле (8.64) выполнен, "
                           "но при пожаре температурно-зависимая "
                           "переходная ползучесть остаётся "
                           "неквалифицированной.")
            elif r.get("sp2026_stage7_sp5_864_creep_source_blocker"):
                st.warning("Источник φef: "+str(
                    r["sp2026_stage7_sp5_864_creep_source_blocker"]))
            ledger=r.get("sp2026_stage7_qualification_ledger") or {}
            st.write("Нормативный статус:",ledger.get("status"))
            st.caption("Собственные значения и пересечение деформационных "
                       "критериев относятся к расчетной модели. "
                       "Не подтверждены высокотемпературная ползучесть, "
                       "реальное первое глобальное разрушение, "
                       "теплофизические границы и сопоставление с испытаниями. "
                       "U(t) и t_R остаются НЕ УСТАНОВЛЕНЫ.")
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
    sp_thermal_available=bool(r.get("sp2026_stage2_thermal_timeline"))
    selected_thermal=(r.get("sp2026_stage2_thermal_timeline")
                      if sp_thermal_available else r.get("thermal_timeline")) or []
    chart_report={
        **r,
        "timeline":[x for x in (r.get("timeline") or [])
                    if float(x["minute"])<=max_chart_time+1.e-9],
        "thermal_timeline":[x for x in selected_thermal
                            if float(x["minute"])<=max_chart_time+1.e-9],
    }
    if sp_thermal_available:
        st.caption("Основные температурные графики и тепловая карта — "
                   "СП 2.02.05-2026 §8.2.23, приложение К.1, "
                   "двумерный конечно-объёмный решатель. "
                   "Граничные коэффициенты h=25 Вт/(м²·К), ε=0,7 "
                   "используются как явно указанное сравнительное "
                   "допущение из ТКП, не как табличные значения СП.")
    else:
        st.warning("Расчёт температуры по СП не получен. Ниже показана "
                   "только прежняя модель ТКП, которая НЕ подтверждает "
                   "теплотехническую часть СП. Причина: "+
                   str(r.get("sp2026_stage2_heat_blocker") or
                       "в сохранённом результате нет ветви SP-R.2"))
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
        st.markdown("**Механический ответ при заданных N–Mx–My (ТКП, сравнение)**")
        st.caption("Следующий деформационный график остаётся результатом "
                   "отдельной модели ТКП. Он НЕ рассчитывает нормативное "
                   "использование U(t) по СП 2.02.05-2026.")
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
        st.markdown("**Численное состояние сечения на Rrequired (ТКП, сравнение)**")
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
        sp_at=next((x for x in (r.get("sp2026_stage2_thermal_timeline") or [])
                    if abs(float(x["minute"])-
                           float(r["required_rating_minutes"]))<1e-8),None)
        legacy=r["required_time_temperatures"]
        temps=({
            "concrete_surface_max_C":sp_at["concrete_surface_C"],
            "concrete_centre_C":sp_at["concrete_centre_C"],
            "bars_C":sp_at["bars_C"]} if sp_at else legacy)
        st.write(f"Бетон, поверхность: "
                 f"{temps['concrete_surface_max_C']:.1f} °C")
        st.write(f"Бетон, центр: {temps['concrete_centre_C']:.1f} °C")
        st.dataframe(pd.DataFrame([
            {"Стержень":key,"Температура, °C":round(float(t),1)}
            for key,t in (temps["bars_C"] or {}).items()]),
            hide_index=True,use_container_width=True)
    st.divider()
    st.subheader("Температурное поле сечения")
    grid_spec=(r.get("sp2026_stage2_thermal_grid")
               if sp_thermal_available else r.get("thermal_grid"))
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
            help="Реальные сохранённые моменты конечно-объёмного решения. "
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
        st.caption("Тепловая карта по фактическим расчётным ячейкам "+(
                     "СП 2.02.05-2026 (2D FVM, приложение К.1). "
                     if sp_thermal_available else
                     "старой ветви ТКП EN 1992-1-2 (2D FVM). ")+
                   "Сетка: "+str(grid_spec['nx'])+"×"+str(grid_spec['ny'])+
                   ". Бирюзовые окружности показывают положение стержней; "
                   "температуры взяты из того же поля. Изотерма 500 °C — "
                   "только графическая, не нормативный расчёт R(t).")
    else:
        st.info("В сохранённом расчёте нет двухмерного температурного поля. "
                "Нажмите «Рассчитать огнестойкость» ещё раз, "
                "чтобы восстановить тепловую карту по СП.")

    st.divider()
    st.subheader("Температурные свойства и механика по СП 2.02.05-2026")
    sp_mech=r.get("sp2026_stage1_at_required_time") or {}
    if sp_mech.get("status") in (
        "SP_MATERIAL_AND_SECTION_NUMERICAL_DIAGNOSTIC",
        "SP2026_K1_FVM_AND_FIBRES_NUMERICAL_DIAGNOSTIC"):
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
    sp_energy=r.get("sp2026_stage2_heat_energy_balance") or {}
    if sp_thermal_available and sp_energy:
        st.metric("Относительная невязка теплового баланса СП",
            f"{100*float(sp_energy['relative_cumulative_residual']):.5f} %")
    st.caption("SP-R.2: температурное поле рассчитано по зависимостям "
               "теплопроводности и теплоёмкости приложения К.1 СП. "
               "Влажность учтена через эффективную теплоёмкость формулы К.1; "
               "перенос пара не моделируется. Граничные условия, "
               "сравнение с приложением Ж и сеточная/временная "
               "независимость требуют проверки. "
               "Нормативные U(t) и t_R всей колонны ещё не определены.")
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
