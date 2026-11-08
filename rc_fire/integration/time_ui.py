"""On-demand time history, with source-aware session and export handling."""
from __future__ import annotations

import csv
import io
import json

from .r069 import evaluate_uniform_fire_history, history_input_sha256
from rc_fire.member.time_history import VERSION

STATUS_RU = {
    "SAMPLED_INTERVAL_WITHIN_DIAGNOSTIC_LIMITS": "Во всех проверенных моментах ограничения модели выполнены",
    "OBSERVED_STRAIN_LIMIT_BRACKETED": "Найден интервал достижения предельной деформации",
    "OBSERVED_STABILITY_LIMIT_BRACKETED": "Найден интервал потери устойчивости равновесия",
    "LIMIT_AT_INITIAL_STATE_DIAGNOSTIC": "Предельное состояние уже при t=0",
    "LIMIT_BRACKET_TOLERANCE_NOT_REACHED": "Интервал найден, заданная точность ещё не достигнута",
    "MODEL_DOMAIN_REACHED": "Расчёт остановлен границей применимости материалов или температуры",
    "INPUT_NOT_READY": "Недостаточно исходных данных для временного расчёта",
    "NUMERICAL_SOLUTION_UNRESOLVED": "Равновесие численно не разрешено; разрушение не установлено",
    "ULS_EVIDENCE_INCOMPLETE": "Не завершена проверка предельных состояний всех сечений",
}
STATE_RU = {
    "admitted_sample": "Проверки в этом моменте выполнены",
    "strain_limit": "Предельная деформация превышена",
    "stability_limit": "Неположительная жёсткость в равновесии",
    "model_domain_stop": "Граница применимости модели",
    "input_unavailable": "Недостаточно данных",
    "numerical_unresolved": "Численное решение не найдено",
    "evidence_incomplete": "Проверка сечений неполна",
}


def time_history_csv(result):
    out = io.StringIO(newline="")
    fields = ("time_minutes", "state", "maximum_strain_ratio",
              "tangent_min_eigenvalue", "relative_equilibrium_residual", "reason")
    writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(result.get("samples", []))
    return out.getvalue()


def restore_history_results(session_state, columns, calculations):
    """Hydrate exports/overview only when the entire source matches this version."""
    active_keys = {"r069_result_" + str(c["id"]) for c in columns}
    for key in list(session_state):
        if str(key).startswith("r069_result_") and key not in active_keys:
            session_state.pop(key, None)
            session_state["exports"] = None
    for column in columns:
        key = "r069_result_" + str(column["id"])
        saved = session_state.get(key)
        if saved is None:
            continue
        if (saved.get("version") == VERSION
                and saved.get("source_sha256") == history_input_sha256(column)):
            calculations[column["id"]]["fire_history_r069"] = saved
        else:
            session_state.pop(key, None)
            session_state["exports"] = None


def render_fire_history(st, column, calculation):
    import pandas as pd
    from .r064d import MemberEvidenceInputError

    cid = str(column["id"])
    with st.expander("R0.6.9 · Несущая способность во времени R(t)", expanded=False):
        st.caption("При неизменных введённых пожарных усилиях проверяются t=0 и следующие "
            "моменты времени. Первый переход уточняется повторными расчётами. "
            "Используется схема опор, поперечных нагрузок и одинакового нагрева по длине, "
            "заданная выше. Результат диагностический; нормативный предел R не подтверждается.")
        a, b, c = st.columns(3)
        end = a.number_input("Расчёт до, мин", min_value=.25, max_value=240.,
            value=max(.25, min(240., float(column["fire_minutes"]))), step=5.,
            help="От начала стандартного пожара. Обязательно проверяется начальное состояние t=0.",
            key="r069_end_" + cid)
        step = b.number_input("Шаг времени, мин", min_value=.25, max_value=240.,
            value=5., step=.25,
            help="Промежуточные события между проверенными моментами не исключены. "
                 "Уменьшите шаг для проверки чувствительности результата.",
            key="r069_step_" + cid)
        tol = c.number_input("Точность границы, мин", min_value=.001, max_value=240.,
            value=.25, step=.05,
            help="Максимальная ширина уточнённого интервала; не больше шага времени.",
            key="r069_tol_" + cid)
        controls = {"end_minutes": float(end), "step_minutes": float(step),
                    "tolerance_minutes": float(tol), "max_refinements": 20}
        result = calculation.get("fire_history_r069")
        if result and result.get("controls") != controls:
            st.session_state.pop("r069_result_" + cid, None)
            st.session_state["exports"] = None
            calculation.pop("fire_history_r069", None)
            result = None
        if st.button("Рассчитать R(t)", key="r069_run_" + cid):
            try:
                with st.spinner("Пересчёт прогрева, равновесия, деформаций и устойчивости по времени"):
                    result = evaluate_uniform_fire_history(column, **controls)
                st.session_state["r069_result_" + cid] = result
                st.session_state["exports"] = None
                calculation["fire_history_r069"] = result
            except (MemberEvidenceInputError, ValueError) as exc:
                st.error("Временной расчёт не выполнен: " + str(exc))
        if result is None:
            return
        st.write("**Результат:** " + STATUS_RU.get(result["status"], result["status"]))
        boundary = result.get("boundary")
        if boundary:
            lo, hi = boundary["last_admitted_minutes"], boundary["first_nonadmitted_minutes"]
            if lo is None:
                st.info("Начальное состояние не допущено: " + STATE_RU[boundary["state"]])
            else:
                st.write(f"Последний допущенный момент: **{lo:g} мин**; "
                         f"первый недопущенный: **{hi:g} мин**.")
                st.caption("Это границы проверенных состояний. Непрерывная безопасность "
                    "между ними не доказана. Остановка по температуре или несходимости "
                    "не является установленным пределом огнестойкости.")
        rows = [{"t, мин": row["time_minutes"], "Состояние": STATE_RU[row["state"]],
                 "ε/εlim, макс.": row.get("maximum_strain_ratio"),
                 "Невязка": row.get("relative_equilibrium_residual"),
                 "Причина": row.get("reason")}
                for row in result["samples"]]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        plotted = [r for r in result["samples"] if r.get("maximum_strain_ratio") is not None]
        if plotted:
            import plotly.graph_objects as go
            fig = go.Figure(go.Scatter(x=[r["time_minutes"] for r in plotted],
                y=[r["maximum_strain_ratio"] for r in plotted], mode="markers",
                name="Проверенные состояния"))
            fig.add_hline(y=1., line_dash="dash")
            fig.update_layout(xaxis_title="Время, мин", yaxis_title="max(εc/εcu, εs/εsu)",
                title="Предельные деформации в проверенных сечениях")
            st.plotly_chart(fig, use_container_width=True, key="r069_plot_" + cid)
        st.download_button("Скачать временной расчёт JSON", json.dumps(result,
            ensure_ascii=False, indent=2, allow_nan=False), file_name=cid + "_fire_history.json",
            mime="application/json", key="r069_json_" + cid)
        st.download_button("Скачать временной расчёт CSV", time_history_csv(result),
            file_name=cid + "_fire_history.csv", mime="text/csv", key="r069_csv_" + cid)


def render_fire_history_overview(st, project, calculations):
    import pandas as pd
    rows = []
    for column in project["columns"]:
        result = calculations[column["id"]].get("fire_history_r069")
        if result:
            rows.append({"Колонна": column["name"],
                "Временной расчёт": STATUS_RU[result["status"]],
                "Последний допущенный t, мин": result.get("last_admitted_time_minutes"),
                "Проверенных моментов": result["evaluation_count"],
                "Нормативный предел R": "Не подтверждён"})
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
