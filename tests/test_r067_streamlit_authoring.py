"""Streamlit R0.6.7 end-to-end member-authoring state regression."""
import unittest
from pathlib import Path
from multicolumn_r05.project_model import load_json, export_json

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest=None


@unittest.skipUnless(AppTest is not None,"Streamlit test framework unavailable")
class R067StreamlitAuthoringTests(unittest.TestCase):
    def test_user_uniformity_and_load_choices_persist_in_project(self):
        root=Path(__file__).resolve().parents[1]/"streamlit_legacy_app.py"
        app=AppTest.from_file(str(root),default_timeout=120).run()
        self.assertFalse(app.exception,list(app.exception))
        nav=next(x for x in app.radio if x.label=="Разделы")
        nav.set_value("c1").run()
        self.assertFalse(app.exception,list(app.exception))
        self.assertEqual(app.session_state["project"]["columns"][0]["member_spec"]["load_mode"],
                         "not_defined")
        def sel(label):
            return next(x for x in app.selectbox if x.label==label)
        def inp(label):
            return next(x for x in app.text_input if x.label==label)
        sel("Температура по длине").set_value("uniform_assumed")
        inp("Обоснование одинакового нагрева по длине").set_value(
            "Одинаковые нагреваемые грани по всей длине колонны")
        sel("Нижняя опора").set_value("pinned")
        sel("Верхняя опора").set_value("fixed")
        inp("Обоснование опор (проект, схема закрепления)").set_value(
            "Диагностическая модель, схема опирания из чертежа")
        sel("Расчётная схема поперечной нагрузки").set_value("uniform_transverse_load")
        self.assertNotIn("Источник пожарного сочетания усилий",
                         [x.label for x in app.text_input])
        next(x for x in app.button if x.label=="Сохранить схему нагрева, опирания и нагрузок").click().run()
        self.assertFalse(app.exception,list(app.exception))
        c=app.session_state["project"]["columns"][0]
        spec=c["member_spec"]
        self.assertEqual(spec["thermal_longitudinal_mode"],"uniform_assumed")
        self.assertEqual(spec["left_support"],"pinned")
        self.assertEqual(spec["right_support"],"fixed")
        self.assertEqual(spec["load_mode"],"uniform_transverse_load")
        self.assertEqual((spec["q_x_kNpm"],spec["q_y_kNpm"]),(0.,0.))
        self.assertIn("Одинаковые",spec["uniform_fire_basis"])
        out=load_json(export_json(app.session_state["project"]))
        self.assertEqual(out["columns"][0]["member_spec"],spec)
        # No claims may appear merely because member model inputs were saved.
        self.assertFalse(any("R90 подтверждено" in str(x.value)
                             for x in app.success))


if __name__=="__main__":
    unittest.main()
