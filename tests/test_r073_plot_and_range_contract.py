"""R0.7.3 regression: user-reported KeyError bars_C and helpful input ranges."""
import math
import unittest

from rc_fire.integration.r073_plot_contract import (
    prepare_temperature_chart,prepare_optional_percent_chart,
    engineering_input_help)


def _old_result():
    return {
        "timeline":[
            {"minute":1.,"gas_C":349.,"concrete_surface_C":180.,"concrete_centre_C":20.},
            {"minute":90.,"gas_C":1006.,"concrete_surface_C":990.,"concrete_centre_C":23.}
        ],
        "full_internal_audit":{"samples":[
            {"time_minutes":1.,"T_reinforcement_C":{"S1":29.,"S2":28.}},
            {"time_minutes":90.,"T_reinforcement_C":{"S1":671.6,"S2":448.5}}
        ]}
    }


class HistoricalPlotContractTests(unittest.TestCase):
    def test_legacy_timeline_no_bars_column_uses_same_time_physical_evidence(self):
        report=_old_result()
        chart,missing,count=prepare_temperature_chart(report,["S1","S2"])
        self.assertEqual(missing,[])
        self.assertEqual(count,2)
        self.assertEqual(chart.loc[90.,"Арматура S1"],671.6)
        self.assertEqual(chart.loc[90.,"Арматура S2"],448.5)
        self.assertEqual(chart.loc[90.,"Поверхность бетона"],990.)
        self.assertEqual(chart.loc[1.,"Арматура S1"],29.)

    def test_full_legacy_without_any_rebar_keeps_gas_and_concrete_no_invented_zero(self):
        report=_old_result()
        report.pop("full_internal_audit")
        chart,missing,count=prepare_temperature_chart(report,["S1","S2"])
        self.assertEqual(missing,["S1","S2"])
        self.assertEqual(count,0)
        self.assertEqual(set(chart.columns),
              {"Температура газа","Поверхность бетона","Центр бетона"})
        self.assertFalse(any(x.startswith("Арматура ") for x in chart.columns))

    def test_missing_strength_history_columns_do_not_raise_key_error(self):
        report=_old_result()
        chart=prepare_optional_percent_chart(report,{
            "concrete_retained_uniaxial_pct":"Бетон",
            "steel_retained_yield_pct":"Сталь"})
        self.assertTrue(chart.empty)
        mixed=prepare_optional_percent_chart(report,{
            "gas_C":"Газ",
            "steel_retained_yield_pct":"Сталь"})
        self.assertEqual(list(mixed.columns),["Газ"])
        self.assertEqual(mixed.loc[90.,"Газ"],1006.)

    def test_current_result_native_bars_take_precedence_over_old_source_audit(self):
        report=_old_result()
        report["timeline"][-1]["bars_C"]={"S1":650.,"S2":450.}
        chart,missing,source=prepare_temperature_chart(report,["S1","S2"])
        self.assertEqual(chart.loc[90.,"Арматура S1"],650.)
        self.assertEqual(chart.loc[90.,"Арматура S2"],450.)
        self.assertEqual(source,1)  # only 1 min used the original audit

    def test_do_not_interpolate_audit_with_inconsistent_time(self):
        report=_old_result()
        report["full_internal_audit"]["samples"][-1]["time_minutes"]=89.999
        chart,missing,source=prepare_temperature_chart(report,["S1"])
        self.assertTrue(math.isnan(chart.loc[90.,"Арматура S1"]))
        self.assertFalse(math.isnan(chart.loc[1.,"Арматура S1"]))
        self.assertEqual(missing,["S1"])
        self.assertEqual(source,1)

    def test_invalid_or_empty_legacy_rows_do_not_crash(self):
        report={"timeline":[None,{"minute":None,"bars_C":{}},
                            {"minute":0.,"gas_C":20.}],
                "full_internal_audit":{}}
        chart,missing,count=prepare_temperature_chart(report,["S1"])
        self.assertEqual(len(chart),1)
        self.assertEqual(missing,["S1"])
        self.assertEqual(count,0)
        self.assertTrue(prepare_temperature_chart({},["S1"])[0].empty)


class TooltipRangeTests(unittest.TestCase):
    def test_actual_control_limits_and_example_rendered_not_just_generic_text(self):
        txt=engineering_input_help(
            "Ширина b, мм","number_input",
            {"min_value":250.,"max_value":2000.,"value":600.,"step":25.},
            "Выберите фактическую ширину прямоугольного сечения.")
        self.assertIn("250–2000",txt)
        self.assertIn("Начальное значение: 600",txt)
        self.assertIn("Шаг ввода: 25",txt)
        self.assertIn("не универсальная нормативная рекомендация",txt)

    def test_moisture_limits_source_are_visible_with_decimal_comma(self):
        txt=engineering_input_help("Массовая влажность бетона, %",
              "number_input",{"min_value":0.,"max_value":3.,
              "value":1.5,"step":0.1},"Измерять по массе сухого бетона.")
        self.assertIn("0–3",txt)
        self.assertIn("1,5",txt)
        self.assertIn("0,1",txt)

    def test_selectors_report_actual_available_choices(self):
        txt=engineering_input_help("Класс пластичности","selectbox",
            {"_options_for_tooltip":("B","A","C"),"index":0},"Класс по сертификату.")
        self.assertIn("Доступные значения: B, A, C",txt)
        self.assertIn("Выбрано по умолчанию: B",txt)

    def test_source_options_show_human_readable_values(self):
        txt=engineering_input_help("Тип заполнителя","selectbox",
            {"_options_for_tooltip":("siliceous","calcareous"),
             "format_func":lambda x:{"siliceous":"Силикатный",
                                    "calcareous":"Карбонатный"}[x]},
            "Тепловые свойства по ТКП.")
        self.assertIn("Силикатный, Карбонатный",txt)


if __name__=="__main__":
    unittest.main()
