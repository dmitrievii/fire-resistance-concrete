"""Compact Word evidence for R0.6.9 with no unauthorized R claim."""
from multicolumn_r05.parametric_report import add_heading,add_text,add_table,number


def _display(value,places):
    return "не определено" if value is None else number(value,places)


def add_resistance_history_note(doc,calc):
    r=calc.get("resistance_r069") or {}
    if not r or not r.get("samples"):return
    add_heading(doc,"R0.6.9 — расчётная история R(t) (диагностическая)",2)
    add_text(doc,"СП 2.02.05-2026, приложение К, §8.2.11 и таблица 3; "
        "СП 5.03.01-2020. Время фактического отказа и нормативный "
        "класс R по этой истории НЕ установлены.",bold=True)
    add_text(doc,"Статус: "+str(r.get("status"))+
        "; время пожара до "+number(r.get("time_horizon_min"),1)+
        " мин; сетка "+str(r.get("grid"))+
        "; температурная политика: "+str(r.get("high_temperature_policy"))+".")
    if r.get("first_outside_scope_min") is not None:
        add_text(doc,"В t="+number(r["first_outside_scope_min"],2)+
            " мин впервые достигнута граница применимости температурной/"
            "материальной модели. ЭТО НЕ ВРЕМЯ РАЗРУШЕНИЯ.")
    if r.get("diagnostic_limit_bracket_min"):
        a,b=r["diagnostic_limit_bracket_min"]
        add_text(doc,"Только диагностический интервал превышения деформаций: "+
            number(a,2)+"–"+number(b,2)+" мин. Не нормативный предел R.")
    if r.get("member_diagnostic_limit_bracket_min"):
        m0,m1=r["member_diagnostic_limit_bracket_min"]
        add_text(doc,"Колонна R0.6.7 (узлы/точки Гаусса): диагностическое "
            "превышение предельных деформаций наблюдалось между "+
            number(m0,2)+" и "+number(m1,2)+" мин. Нормативная R(t) не определена.")
    if r.get("high_temperature_policy")=="zero_strength_diagnostic":
        add_text(doc,"ИССЛЕДОВАТЕЛЬСКИЙ РЕЖИМ: прочность T>800 °C "
            "принята нулевой без нормативного обоснования.",bold=True)
    add_table(doc,["t, мин","Tmax, °C","Tmax армат., °C","A500, м²",
                   "Состояние"],[
        (number(s["time_min"],1),
         _display(s["temperature_max_C"],1),
         _display(s["bar_temperature_max_C"],1),
         _display(s["area_after_critical_isotherm_m2"],5),
         str(s["state"]))
        for s in r["samples"]])
    tab=r.get("table3") or {}
    if tab:
        add_text(doc,"Таблица 3: η="+
            (number(tab.get("eta"),5) if tab.get("eta") is not None else "не определён")+
            "; условный класс="+
            (("R"+str(tab["conditional_class_max_min"])) if tab.get("conditional_class_max_min") else "не установлен")+
            ". Подтверждение применимости таблицы требуется отдельно.")
        if tab.get("missing_or_unverified"):
            add_text(doc,"Неподтверждённые условия: "+
                     "; ".join(tab["missing_or_unverified"]))
    add_text(doc,"Нормативный статус: предел огнестойкости не подтверждён. "
        "Сходимость уравнений и вычисленная изотерма сами по себе не означают R90.")
