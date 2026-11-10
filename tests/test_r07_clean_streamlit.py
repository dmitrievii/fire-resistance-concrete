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
        confirmed=next(x for x in app.checkbox if
            x.label=="Технология изготовления и класс пластичности подтверждены документами")
        self.assertEqual(route.value,"hot_rolled")
        self.assertEqual(duct.value,"B")
        self.assertFalse(confirmed.value)
        self.assertTrue(any("демонстрац" in x.value.lower()
                            for x in app.get("caption")))
        # A Streamlit form commits changed widget values only on submit.
        route.set_value("cold_worked")
        next(b for b in app.button if
             "Рассчитать огнестойкость" in b.label).click().run()
        self.assertFalse(app.exception)
        self.assertEqual(next(x for x in app.selectbox
            if x.label=="Изготовление арматуры").value,"cold_worked")

    def test_missing_load_stays_missing_and_does_not_display_R90_pass(self):
        app=self._check(ROOT/"streamlit_app.py")
        buttons=[b for b in app.button if "Рассчитать огнестойкость" in b.label]
        self.assertEqual(len(buttons),1)
        buttons[0].click().run()
        self.assertFalse(app.exception,f"Missing-load submit exception: {list(app.exception)}")
        self.assertTrue(any("Введите N" in str(getattr(e,"body",getattr(e,"value",""))) for e in app.error))
        self.assertFalse(any("R90 подтверждено" in t.value for t in app.markdown))
