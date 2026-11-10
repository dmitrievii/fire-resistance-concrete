"""R0.7 Streamlit public UX acceptance, distinct from preserved R0.5–D4 tests."""
from pathlib import Path
import unittest
try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest=None

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(AppTest is not None,"Streamlit testing unavailable")
class PublicCalculatorScreen(unittest.TestCase):
    def _check(self,path):
        app=AppTest.from_file(str(path),default_timeout=90).run()
        self.assertFalse(app.exception,f"Startup error: {list(app.exception)}")
        self.assertFalse(app.error,f"UI error: {list(app.error)}")
        subs=[x.value for x in app.subheader]
        self.assertTrue(any("Геометрия и армирование" in x for x in subs))
        self.assertTrue(any("Материалы" in x for x in subs))
        self.assertTrue(any("Пожар и действующие усилия" in x for x in subs))
        self.assertFalse(any(item.label=="Разделы" for item in app.radio))
        self.assertFalse(any("R0.6.9D" in item.label for item in app.expander))
        self.assertTrue(any("Производ" in item.label or
                            "Изготовление арматуры" in item.label
                            for item in app.selectbox))
        self.assertTrue(any("Nᶠⁱ" in item.label for item in app.text_input))
        self.assertFalse(any("Соответствие требованиям" in x.value
                         for x in app.get("metric")))
        return app

    def test_public_main_is_one_clean_screen_without_old_debug_panels(self):
        self._check(ROOT/"streamlit_app.py")

    def test_historic_cloud_path_also_opens_clean_public_screen(self):
        self._check(ROOT/"K18_Streamlit_GitHub_MVP_R0.5"/"streamlit_app.py")

    def test_multiple_columns_keep_independent_simple_input_pages(self):
        app=self._check(ROOT/"streamlit_app.py")
        count=next(x for x in app.number_input if
                   x.label=="Количество конструкций")
        count.set_value(2).run()
        self.assertFalse(app.exception,f"Resizing constructions: {list(app.exception)}")
        nav=next(x for x in app.radio if x.label=="Колонна")
        nav.set_value("c2").run()
        self.assertFalse(app.exception,f"Second column page: {list(app.exception)}")
        name=next(x for x in app.text_input if
                  x.label=="Обозначение колонны")
        self.assertEqual(name.value,"К2")
        self.assertFalse(any(x.label=="Разделы" for x in app.radio))

    def test_steel_defaults_are_visible_and_unverified(self):
        app=self._check(ROOT/"streamlit_app.py")
        route=next(x for x in app.selectbox if x.label=="Изготовление арматуры")
        duct=next(x for x in app.selectbox if x.label=="Класс пластичности")
        self.assertEqual(route.value,"hot_rolled")
        self.assertEqual(duct.value,"B")
        self.assertTrue(any("исходными допущениями" in x.value.lower()
                            for x in app.get("caption")))
        # A Streamlit form commits changed widget values only on submit.
        route.set_value("cold_worked")
        next(b for b in app.button if
             "Рассчитать огнестойкость" in b.label).click().run()
        self.assertFalse(app.exception)
        self.assertEqual(next(x for x in app.selectbox
            if x.label=="Изготовление арматуры").value,"cold_worked")

    def test_material_confirmation_and_sand_checkboxes_are_not_in_public_UI(self):
        app=self._check(ROOT/"streamlit_app.py")
        visible={x.label for x in app.checkbox}
        self.assertNotIn("Природный песок подтверждён",visible)
        self.assertNotIn(
            "Технология изготовления и класс пластичности подтверждены документами",
            visible)
        self.assertEqual(next(x for x in app.selectbox
            if x.label=="Изготовление арматуры").value,"hot_rolled")
        self.assertEqual(next(x for x in app.selectbox
            if x.label=="Класс пластичности").value,"B")

    def test_original_normative_material_comments_are_still_exposed(self):
        app=self._check(ROOT/"streamlit_app.py")
        self.assertTrue(any("Нормативные пояснения к диапазонам материалов"
                            in x.label for x in app.expander))

    def test_recommended_example_help_mapping_is_present_for_all_major_inputs(self):
        script=(ROOT/"multicolumn_r05"/"simple_app.py").read_text(
            encoding="utf-8")
        self.assertIn("_INPUT_HELP={",script)
        self.assertIn('kwargs["help"]=',script)
        for label in ("Ширина b, мм","Защитный слой до хомута, мм",
                      "Класс бетона","Массовая влажность бетона, %",
                      "Изготовление арматуры","Nᶠⁱ, кН (сжатие положительно)",
                      "Mxᶠⁱ, кН·м","Требуемая огнестойкость"):
            self.assertIn('"'+label+'":',script)

    def test_real_public_results_render_rod_temperatures_and_strength_sections(self):
        # UI smoke for the actual result path, which the static input tests
        # cannot cover. R30 is the shortest supported fire duration.
        app=AppTest.from_file(str(ROOT/"streamlit_app.py"),
                              default_timeout=180).run()
        self.assertFalse(app.exception)
        def set_text(label,value):
            next(x for x in app.text_input if x.label==label).set_value(value)
        set_text("Nᶠⁱ, кН (сжатие положительно)","50")
        set_text("Mxᶠⁱ, кН·м","2")
        set_text("Myᶠⁱ, кН·м","0")
        next(x for x in app.selectbox if
             x.label=="Требуемая огнестойкость").set_value(30)
        next(x for x in app.button if
             x.label=="Рассчитать огнестойкость").click().run()
        self.assertFalse(app.exception,repr(list(app.exception)))
        self.assertFalse(app.error,repr(list(app.error)))
        self.assertTrue(any("Изменение прочности и проверенный запас сечения"
                            in x.value for x in app.subheader))
        self.assertTrue(any("Температурное поле сечения"
                            in x.value for x in app.subheader))
        self.assertTrue(any("Нормативные пояснения к диапазонам материалов"
                            in x.label for x in app.expander))
        self.assertTrue(any("Температура продольной арматуры"
                            in x.value for x in app.markdown))
        self.assertTrue(any("Сохранение прочности бетона" in x.label
                            for x in app.get("metric")))
        extended=next(x for x in app.checkbox
                      if x.label.startswith("Показывать дополнительно период"))
        self.assertFalse(extended.value)
        extended.set_value(True).run()
        self.assertFalse(app.exception,repr(list(app.exception)))
        self.assertTrue(any("Показан также прогрев после требуемого R"
                            in x.value for x in app.get("caption")))
        # Reproduce the user's exact failure: a previous deployment kept a
        # valid calculation in Streamlit session_state whose timeline had
        # no bars_C and no strength-percent fields. A rerun must not raise.
        saved=app.session_state["r07_last_public_result_c1"]["result"]
        for row in saved["timeline"]:
            row.pop("bars_C",None)
            row.pop("concrete_retained_uniaxial_pct",None)
            row.pop("steel_retained_yield_pct",None)
            row.pop("discrete_checked_section_extra_load_pct",None)
            row.pop("ratio_to_max_checked_load_pct_not_utilization",None)
        app.run()
        self.assertFalse(app.exception,
                         "Historical calculation must not raise KeyError: "+
                         repr(list(app.exception)))
        self.assertFalse(app.error,repr(list(app.error)))
        self.assertTrue(any("Температура продольной арматуры" in x.value
                            for x in app.markdown))
        self.assertTrue(any("Механический ответ при заданных N–Mx–My" in x.value
                            for x in app.markdown))

    def test_missing_load_stays_missing_and_does_not_display_R90_pass(self):
        app=self._check(ROOT/"streamlit_app.py")
        buttons=[b for b in app.button if "Рассчитать огнестойкость" in b.label]
        self.assertEqual(len(buttons),1)
        buttons[0].click().run()
        self.assertFalse(app.exception,f"Missing-load submit exception: {list(app.exception)}")
        self.assertTrue(any("Введите N" in str(getattr(e,"body",getattr(e,"value",""))) for e in app.error))
        self.assertFalse(any("R90 подтверждено" in t.value for t in app.markdown))
