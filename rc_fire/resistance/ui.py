"""Streamlit presentation for independent time evidence and Table 3.

No automatic heavy scan on page load. All results are input-signature cached
to avoid silently showing a previous column's temperature/resistance history.
"""
from __future__ import annotations
import hashlib
import json
import pandas as pd
import plotly.graph_objects as go
from .history import evaluate_resistance_history,GOOD,EXCEEDED,SCOPE,UNKNOWN,MISSING
from .table3 import evaluate_table3_class

UI_RELEASE="R0.6.9-time-history-streamlit-v1"


def history_signature(column):
    src=json.dumps(column,sort_keys=True,ensure_ascii=False,
                   separators=(",",":"),allow_nan=False)
    return hashlib.sha256(src.encode("utf-8")).hexdigest()


def render_resistance(st,column,calc,*,project=None,safe_change=None,
                      update_fire_resistance_reference=None):
    cid=str(column["id"])
    with st.expander("R0.6.9 — R(t): проверка несущей способности во времени",expanded=False):
        st.caption("Отдельные маршруты: дискретный табличный класс по СП 2.02.05-2026, "
                   "таблица 3; и почасовая/поминутная диагностическая история "
                   "температур и механики. Это НЕ подтверждённое численное время разрушения.")
        tab=evaluate_table3_class(column)
        st.markdown("**Таблица 3 — возможные классы R30–R180**")
        b=tab.get("reference_width_mm")
        c=tab.get("min_bar_axis_distance_mm")
        st.caption("Консервативно: ширина min(b,h) = "+
                   ("—" if b is None else f"{b:.1f} мм")+
                   ", минимальное расстояние до оси стержня = "+
                   ("—" if c is None else f"{c:.1f} мм")+
                   ". Эти геометрические значения не доказывают полную применимость таблицы.")
        st.dataframe(pd.DataFrame([
            {"η не выше":eta,
             "Соответствующие только геометрии классы":
                 ", ".join("R"+str(t) for t in classes) if classes else "—"}
            for eta,classes in tab["geometric_classes_by_eta_band"].items()
        ]),hide_index=True,use_container_width=True)
        if tab["eta"] is not None:
            st.caption(f"η = N_Sd,fi / N_Rd = {tab['eta']:.5f}; "
                       f"табличный интервал η ≤ {tab['eta_band']}."
                       if tab["eta_band"] is not None else
                       f"η = {tab['eta']:.5f}: за пределами таблицы 3.")
        else:
            st.info("Для определения строки η необходимо нормальное осевое "
                    "сопротивление N_Rd при 20 °C по СП 5.03.01-2020. "
                    "Оно не рассчитывается по старому диагностическому коэффициенту u.")
        if tab["conditional_class_max_min"]:
            st.warning("Только условный табличный кандидат: R"+
                       str(tab["conditional_class_max_min"])+
                       ". Нормативное подтверждение НЕ сформировано.")
        if tab["missing_or_unverified"]:
            with st.popover("Условия таблицы 3, требующие проверки"):
                for reason in tab["missing_or_unverified"]:
                    st.write("• "+str(reason))
        if project is not None and safe_change is not None and update_fire_resistance_reference is not None:
            with st.form(f"r069_table3_{cid}_{project['revision']}"):
                value=column.get("N_Rd_normal_temperature_kN")
                nrd=st.text_input("N_Rd при нормальной температуре, кН (необязательно)",
                     value="" if value is None else f"{float(value):g}",
                     help="Нормативное сопротивление холодного поперечного сечения "
                          "по СП 5.03.01-2020, а НЕ приложенная нагрузка и не "
                          "диагностический Ncr. Ввод не создаёт автоматически сертификат R.")
                mu_source=st.text_input("Обоснование расчётной длины μ (необязательно)",
                     value=column.get("effective_length_provenance") or "",
                     help="Опирание и связи колонны, определяющие расчётную длину; "
                          "в §8.2.11 предел 3 м.")
                faces_source=st.text_input("Фактические огреваемые грани подтверждены (источник)",
                     value=column.get("fire_exposure_provenance") or "",
                     help="Проектная схема, пожарный отсек или документация. "
                          "Само наличие четырёх галочек не подтверждает огрев.")
                if st.form_submit_button("Сохранить исходные данные таблицы 3"):
                    try:
                        v=None if not nrd.strip() else float(nrd.replace(",","."))
                        safe_change(update_fire_resistance_reference,project,cid,{
                            "N_Rd_normal_temperature_kN":v,
                            "effective_length_provenance":mu_source or None,
                            "fire_exposure_provenance":faces_source or None,
                        })
                    except ValueError as exc:
                        st.error("N_Rd: "+str(exc))
        st.divider()
        st.markdown("**Численная история температур и несущей способности**")
        st.caption("При температуре выше границы таблиц 9–10 временная история "
                   "помечается «вне области»; это не время разрушения.")
        step=st.number_input("Шаг по времени, мин",min_value=1,max_value=60,
                             value=15,step=1,key=f"r069_step_{cid}",
                             help="До 61 станции (0 ... время пожара). "
                                  "Шаг влияет на дискретизацию, не на физическую достоверность.")
        grid=st.select_slider("Сетка поперечного сечения",
                              options=(12,16,24,32),value=12,
                              key=f"r069_grid_{cid}")
        with_member=st.checkbox("Проверять также модель колонны R0.6.7",
                                value=False,key=f"r069_member_{cid}",
                                help="Только при явно заданных опорах и схеме нагрузки. "
                                     "Одного N–Mx–My недостаточно для распределённых усилий.")
        research=st.checkbox("Исследовательский расчёт: исключать прочность T > 800 °C",
                             value=False,key=f"r069_research_{cid}",
                             help="Ненормативное допущение; такие результаты не считаются "
                                  "доказательством огнестойкости.")
        signature=history_signature(column)
        cache_key=f"r069_result_{cid}"
        cached=st.session_state.get(cache_key)
        if cached is not None and cached.get("signature")!=signature:
            st.session_state.pop(cache_key,None);cached=None
        if st.button("Рассчитать историю R(t) (диагностически)",
                     key=f"r069_evaluate_{cid}"):
            try:
                with st.spinner("Расчёт температур и N–Mx–My по всем станциям времени"):
                    result=evaluate_resistance_history(
                        column,step_minutes=float(step),grid=int(grid),
                        policy="zero_strength_diagnostic" if research else "reject",
                        with_member=bool(with_member))
                cached={"signature":signature,"result":result}
                st.session_state[cache_key]=cached
            except (ValueError,TypeError,KeyError) as exc:
                st.error("R0.6.9: исходные данные не приняты: "+str(exc))
        if cached is None:return
        result=cached["result"]
        st.caption("Временных станций: "+str(result["sampled_time_count"])+
                   "; статус: "+result["status"])
        st.warning("R(t) в нормативном смысле и точный момент разрушения "
                   "пока НЕ определены. Численные равновесия и пределы "
                   "деформаций — диагностические.")
        bracket=result.get("diagnostic_limit_bracket_min")
        if bracket:
            st.metric("Диагностический интервал первого превышения деформаций",
                      f"{bracket[0]:g}–{bracket[1]:g} мин")
            st.caption("Не является квалифицированным пределом огнестойкости.")
        member_bracket=result.get("member_diagnostic_limit_bracket_min")
        if member_bracket:
            st.metric("Второй порядок: диагностический интервал предельных деформаций",
                      f"{member_bracket[0]:g}–{member_bracket[1]:g} мин")
            st.caption("Отдельное численное наблюдение R0.6.7, не физический t_R.")
        if result.get("first_outside_scope_min") is not None:
            st.error("Материальная/тепловая область применимости впервые "
                     f"нарушена при t={result['first_outside_scope_min']:g} мин. "
                     "Это НЕ время разрушения.")
        if research:
            st.error("Режим T>800 °C с предполагаемой нулевой прочностью — "
                     "исключительно исследовательский.")
        rows=[{"t, мин":r["time_min"],
               "Класс состояния":r["state"],
               "Tmax бетона, °C":r["temperature_max_C"],
               "Tmax арматуры, °C":r["bar_temperature_max_C"],
               "A500, м²":r["area_after_critical_isotherm_m2"],
               "R0.6.7":r["member_status"]}
              for r in result["samples"]]
        st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
        ts=[r for r in result["samples"] if r["temperature_max_C"] is not None]
        if ts:
            fig=go.Figure()
            fig.add_scatter(x=[r["time_min"] for r in ts],
                y=[r["temperature_max_C"] for r in ts],
                mode="lines+markers",name="Tmax бетона, °C")
            fig.add_scatter(x=[r["time_min"] for r in ts],
                y=[r["bar_temperature_max_C"] for r in ts],
                mode="lines+markers",name="Tmax арматуры, °C")
            fig.add_hline(y=800,line_dash="dot",annotation_text="Таблицы 9–10: 800 °C")
            fig.update_layout(xaxis_title="Время огневого воздействия, мин",
                              yaxis_title="Температура, °C",height=350)
            st.plotly_chart(fig,use_container_width=True,key=f"r069_graph_{cid}")
        st.download_button("Скачать историю R(t) (JSON, без нормативного заключения)",
            json.dumps(result,ensure_ascii=False,indent=2),
            mime="application/json",file_name=f"{cid}_r069_history.json",
            key=f"r069_download_{cid}")
