"""Current Streamlit reporting: Belarus SP only.

Historical R0.5.6 biaxial/member calculations remain explicitly
diagnostic. Foreign spalling criteria are not offered or displayed.
"""
from __future__ import annotations
import pandas as pd
from rc_fire.spalling.ui import render_annex_l_results

# The old constant name is retained only to avoid breaking the existing
# Streamlit Cloud hot-reload guard. It is NOT a normative source.
R056_SP468_RELEASE = "r056-sp468-20261105-hotfix1"


def render_r056_results(st,calc):
    contract=calc.get("normative_preflight")
    if contract:
        st.caption("Нормативный Preflight: "+contract["status"]+
            " · СП 2.02.05-2026 + СП 5.03.01-2020 · "+contract["contract_sha256"][:12])
        with st.expander("Нормативный протокол — источники, значения и ограничения",expanded=False):
            st.write("Нормативные источники: СП 2.02.05-2026 и СП 5.03.01-2020.")
            st.write("Отчёт о диагностике не является подтверждением R90.")
            resolved=contract.get("resolved_inputs") or {}
            if resolved:
                st.dataframe(pd.DataFrame([
                    {"Параметр":k,"Значение":"—" if v is None else str(v)}
                    for k,v in resolved.items()
                ]),hide_index=True,use_container_width=True)
            st.dataframe(pd.DataFrame([
                {"Код":x["code"],"Приоритет":x["severity"],
                 "Ограничение":x["message"],"Источник":x["clause"]}
                for x in contract["issues"]
            ]),hide_index=True,use_container_width=True)
    material=calc.get("material_preflight") or {}
    if material:
        st.subheader("R0.6.1 — нормативные характеристики материалов")
        st.caption("Каталог: "+material["status"]+"; расчёт R90 ещё не квалифицирован.")
        c=material.get("concrete")
        if c:
            st.write("Бетон: fck="+str(c["f_ck_MPa"])+" МПа; Ecm="+
                     ("не определён" if c["E_cm_GPa"] is None else str(c["E_cm_GPa"])+" ГПа"))
        rebar=material.get("steel")
        if rebar:
            st.write("Арматура: "+rebar["group"]+"; Es="+str(rebar["E_s_GPa"])+" ГПа")
        if material.get("issues"):
            st.info("Неразрешённые свойства: "+"; ".join(material["issues"]))
    st.subheader("Дополнительная диагностическая механика колонны")
    st.caption("Общий конверт η и равновесие N–Mx–My не заменяют "
               "проверку огнестойкости по белорусским СП.")
    member=calc.get("member") or {}
    if member.get("status")=="evaluated":
        st.markdown("**Диагностический конверт устойчивости по колонне**")
        st.dataframe(pd.DataFrame([
            {"Ось":axis.upper(),"Nmax, кН":member["Nmax_kN"],
             "Ncr,min, кН":v["Ncr_min_kN"],"η":v["eta_member"]}
            for axis,v in member["axes"].items()
        ]),hide_index=True,use_container_width=True)
    elif member.get("status")=="instability_or_invalid":
        st.error("Диагностическая устойчивость: Nmax ≥ Ncr,min или неверная жёсткость")
    else:
        st.info("Диагностический конверт устойчивости пока не рассчитан.")
    biax=calc.get("biaxial") or {}
    if biax.get("sections"):
        st.markdown("**Диагностическое равновесие N–Mx–My**")
        st.dataframe(pd.DataFrame([
            {"Сечение":sid,"Статус":r["status"],"Невязка":r.get("residual_norm"),
             "εc,max":r.get("eps_c_max"),"Mx, кН·м":r["Mx_demand_kNm"],
             "My, кН·м":r["My_demand_kNm"]}
            for sid,r in biax["sections"].items()
        ]),hide_index=True,use_container_width=True)
    else:
        st.info("Совместная проверка сечения ещё не рассчитана.")
    render_annex_l_results(st,calc)
    st.warning("R90 не подтверждено: диагностические результаты, включая F по приложению Л, "
               "не заменяют проверку устойчивости, огневого сочетания и предела R(t).")


def render_r056_overview(st,project,calculations):
    st.markdown("**Дополнительные диагностические проверки**")
    rows=[]
    for c in project["columns"]:
        calc=calculations[c["id"]]
        annex=calc.get("annex_l") or {}
        F=annex.get("F")
        rows.append({
            "Колонна":c["name"],
            "Общий конверт η":(calc.get("member") or {}).get("status","—"),
            "Совместное N–Mx–My":(calc.get("biaxial") or {}).get("status","не рассчитано"),
            "F (СП 2.02.05-2026, приложение Л)":round(F,4) if F is not None else annex.get("status","—"),
            "R90":"Не подтверждено"
        })
    st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
